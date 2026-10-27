"""Private, bounded five-minute cache from all available stored trade neighbors.

Read-only database access. No checksum subset, service change or table migration.
Raw tape completeness/corrections are not certified by this derived cache.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


TIERS = {"super": (500000, None), "large": (100000, 500000),
         "mid": (20000, 100000), "small": (0, 20000)}
AMOUNTS = [f"{tier}_{side}" for tier in TIERS for side in ("buy", "sell")]


def flow_sql():
    sums = []
    for tier, (low, high) in TIERS.items():
        size = f"dollar >= {low}"+(f" AND dollar < {high}" if high else "")
        for side, comparison in [("buy", ">"), ("sell", "<")]:
            sums.append(f"sum(if(dp {comparison} 0 AND {size}, dollar, 0)) AS {tier}_{side}")
    return """
WITH classified AS (
    SELECT sip_timestamp,
        toStartOfInterval(sip_timestamp, INTERVAL 5 MINUTE) AS bar_ts,
        price * size AS dollar,
        if(dateDiff('nanosecond',
               lagInFrame(sip_timestamp, 1, sip_timestamp) OVER ordered, sip_timestamp) > 60000000000,
           0, price - lagInFrame(price, 1, price) OVER ordered) AS dp
    FROM trades
    WHERE ticker = {ticker:String}
      AND sip_timestamp >= {seed_from:String}
      AND sip_timestamp < {to:String}
      AND price > 0 AND size > 0
    WINDOW ordered AS (ORDER BY sip_timestamp, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
)
SELECT toUnixTimestamp64Milli(toDateTime64(bar_ts, 3, 'UTC')) AS time,
    """+",\n    ".join(sums)+""",
    sum(dollar) AS total_notional,
    sum(if(dp = 0, dollar, 0)) AS neutral_notional,
    count() AS sample_count
FROM classified
WHERE sip_timestamp >= {from_:String}
GROUP BY bar_ts ORDER BY bar_ts
"""


SQL = flow_sql()
SOURCE = "full-sequence-tick-rule-v2:"+hashlib.sha256(SQL.encode()).hexdigest()


def bounds(ticker, start, end, seconds):
    if ticker not in {"INTC", "TSLA"} or isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 45:
        raise ValueError("Only INTC/TSLA and query budgets up to 45 seconds are approved")
    left, right = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in (start, end)]
    if left.tzinfo is None or right.tzinfo is None:
        raise ValueError("Explicit UTC offsets are required")
    left, right = left.astimezone(timezone.utc), right.astimezone(timezone.utc)
    if not timedelta(minutes=5) <= right-left <= timedelta(days=1):
        raise ValueError("Use a bounded window from five minutes to one day")
    if any(dt.second or dt.microsecond or dt.minute % 5 for dt in (left, right)):
        raise ValueError("Window bounds must align to complete five-minute buckets")
    if right > datetime.now(timezone.utc):
        raise ValueError("Do not cache an unfinished future window")
    return left, right


def request_for(ticker, left, right):
    fmt = lambda value: value.strftime("%Y-%m-%d %H:%M:%S")
    return {"source": SOURCE, "params": {
        "ticker": ticker, "multiplier": 5, "timespan": "minute",
        "from": fmt(left), "to": fmt(right), "endExclusive": True,
        "super_min": 500000, "large_min": 100000, "mid_min": 20000,
        "seed_from": fmt(left-timedelta(seconds=60)),
    }}


def validate_rows(rows, left, right):
    import math
    previous = None
    for row in rows:
        if not set(["time", *AMOUNTS, "total_notional", "neutral_notional", "sample_count"]) <= set(row):
            raise ValueError("Incomplete flow cache fields")
        if any(isinstance(row[key], bool) or not math.isfinite(row[key]) or row[key] < 0
               for key in ["time", *AMOUNTS, "total_notional", "neutral_notional", "sample_count"]):
            raise ValueError("Invalid flow cache values")
        t = row["time"]
        if (t % 300000 or not left.timestamp()*1000 <= t < right.timestamp()*1000
                or (previous is not None and t <= previous)):
            raise ValueError("Flow cache is unordered or outside its complete bucket bounds")
        if row["sample_count"] < 1 or row["sample_count"] % 1 or row["total_notional"] <= 0:
            raise ValueError("Invalid sample count/notional")
        if not math.isclose(sum(row[key] for key in AMOUNTS)+row["neutral_notional"], row["total_notional"], rel_tol=1e-7, abs_tol=.01):
            raise ValueError("Flow cache buckets do not reconcile")
        previous = t


def rows_hash(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, allow_nan=False).encode()).hexdigest()


def verify_split_pages(whole, first, second):
    """Compare completed, adjacent split caches with the uninterrupted query."""
    import math
    ranges = []
    for page in (whole, first, second):
        params = page["request"]["params"]
        left, right = bounds(params["ticker"], params["from"]+"+00:00", params["to"]+"+00:00", 30)
        if (page.get("schema") != "flow-page-v1"
                or page["request"] != request_for(params["ticker"], left, right)
                or page.get("rowsSha256") != rows_hash(page["rows"])):
            raise ValueError("Split checks require verified same-rule cache receipts")
        validate_rows(page["rows"], left, right)
        ranges.append((left, right, params["ticker"]))
    if (ranges[0][0] != ranges[1][0] or ranges[1][1] != ranges[2][0]
            or ranges[2][1] != ranges[0][1] or len({r[2] for r in ranges}) != 1):
        raise ValueError("Split windows must exactly partition one same-ticker query")
    combined = first["rows"]+second["rows"]
    same_times = [r["time"] for r in whole["rows"]] == [r["time"] for r in combined]
    mismatches = []
    if same_times:
        for a, b in zip(whole["rows"], combined):
            if (a["sample_count"] != b["sample_count"] or
                    any(not math.isclose(a[key], b[key], rel_tol=1e-9, abs_tol=.01)
                        for key in [*AMOUNTS, "total_notional", "neutral_notional"])):
                mismatches.append(a["time"])
    return {"status": "unavailable" if not combined and not whole["rows"] else
                      "pass" if same_times and not mismatches else "mismatch",
            "sameBucketTimes": same_times, "checkedBuckets": len(combined) if same_times else 0,
            "mismatchTimes": mismatches, "rawTapeVerified": False, "productionEligible": False}


def export(root, output, ticker, start, end, seconds=30, client=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not output.is_relative_to(root/".runtime-config"):
        raise ValueError("Keep caches under the site's private .runtime-config directory")
    left, right = bounds(ticker, start, end, seconds)
    request = request_for(ticker, left, right)
    digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    path = output/f"flow-{digest}.json"
    if path.exists():
        page = json.loads(path.read_text())
        if (page.get("schema") != "flow-page-v1" or page.get("request") != request
                or page.get("rowsSha256") != rows_hash(page["rows"])):
            raise ValueError("Existing cache provenance or row hash mismatch")
        validate_rows(page["rows"], left, right)
        return path, "checkpoint", len(page["rows"])
    if client is None:
        sys.path[:0] = [str(root), str(root/"api")]
        from dotenv import load_dotenv
        load_dotenv(root/".env")
        from db import get_client
        client = get_client()
    params = request["params"]
    result = client.query(SQL, parameters={"ticker": ticker, "from_": params["from"],
                                          "to": params["to"], "seed_from": params["seed_from"]},
                          settings={"max_execution_time": seconds, "max_threads": 2,
                                    "max_memory_usage": 1024**3, "max_rows_to_read": 100_000_000})
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
    validate_rows(rows, left, right)
    page = {"schema": "flow-page-v1", "request": request, "rows": rows,
            "rowsSha256": rows_hash(rows), "fetched_at": datetime.now(timezone.utc).isoformat(),
            "direction": "All available stored neighbors before aggregation; equal prices and gaps over 60s (nanosecond precision) neutral; timestamp/id tie order",
            "rawTapeVerified": False, "productionEligible": False,
            "coverage": "Observed five-minute buckets only; missing buckets are not zero"}
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output, delete=False) as handle:
            os.chmod(handle.name, 0o600)
            json.dump(page, handle, allow_nan=False)
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path, "server-query", len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/root/US_stock")
    parser.add_argument("--output", required=True)
    parser.add_argument("--ticker", required=True, choices=["INTC", "TSLA"])
    parser.add_argument("--from", dest="start", required=True, help="UTC/offset ISO bound, inclusive")
    parser.add_argument("--to", dest="end", required=True, help="UTC/offset ISO bound, exclusive")
    parser.add_argument("--max-query-seconds", type=int, default=30)
    parser.add_argument("--verify-split", action="store_true", help="Also compare two adjacent halves; up to three bounded queries")
    args = parser.parse_args()
    try:
        middle = None
        if args.verify_split:
            left, right = bounds(args.ticker, args.start, args.end, args.max_query_seconds)
            buckets = int((right-left).total_seconds()/300)
            if buckets < 2:
                raise ValueError("Split verification needs at least two five-minute buckets")
            middle = left+timedelta(minutes=5*(buckets//2))
        path, mode, count = export(args.root, args.output, args.ticker, args.start, args.end, args.max_query_seconds)
        result = {"path": str(path), "mode": mode, "buckets": count, "source": SOURCE, "productionEligible": False}
        if args.verify_split:
            split_output = Path(args.output)/".split-checks"
            a, _, _ = export(args.root, split_output, args.ticker, left.isoformat(), middle.isoformat(), args.max_query_seconds)
            b, _, _ = export(args.root, split_output, args.ticker, middle.isoformat(), right.isoformat(), args.max_query_seconds)
            result["splitVerification"] = verify_split_pages(*(json.loads(p.read_text()) for p in (path, a, b)))
        print(json.dumps(result))
        if args.verify_split and result["splitVerification"]["status"] != "pass":
            raise SystemExit(2)
    except Exception as exc:
        print(json.dumps({"status": "unavailable", "errorType": type(exc).__name__, "notZeroFlow": True}))
        raise SystemExit(2)
