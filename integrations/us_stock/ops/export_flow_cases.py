"""Run on the teacher server: bounded read-only snapshots using its existing SQL.

Does not change services, source tables, vendor subscriptions or the website.
"""

import argparse
import csv
import fcntl
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


def atomic_json(path, data):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(data, handle, allow_nan=False)
        temporary = handle.name
    os.replace(temporary, path)


def sample_query(sql, params, prefix):
    if prefix is None:
        return sql, params
    marker = "FROM trades\n            WHERE ticker = {ticker:String}"
    if prefix != "0" or sql.count(marker) != 1:
        raise ValueError("The reviewed flow SQL changed; do not guess where to apply a sample")
    return sql.replace(marker, marker+"\n              AND startsWith(check_sum, {sample_prefix:String})"), {**params, "sample_prefix": prefix}


def export(root, protocol_path, output, seconds=45, price_source="repository"):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not output.is_relative_to(root/".runtime-config"):
        raise ValueError("Keep private exports under the site's .runtime-config directory")
    protocol = json.loads(Path(protocol_path).read_text())
    if protocol.get("schema") != "flow-case-protocol-v1" or [c["ticker"] for c in protocol["primaryCases"]] != ["INTC", "TSLA"]:
        raise ValueError("Use the fixed INTC / TSLA pilot protocol")
    sample = protocol.get("flowSample")
    if sample is not None and sample != {"kind": "checksum_prefix", "prefix": "0", "nominalFraction": .0625,
                                         "direction": "Adjacent selected trades; not full-tape neighbors", "fullMarketExtrapolation": False}:
        raise ValueError("Unsupported pilot sample policy")
    prefix = sample["prefix"] if sample is not None else None
    start = datetime.strptime(protocol["collectionStart"], "%Y-%m-%d")
    end = datetime.strptime(protocol["analysisEnd"], "%Y-%m-%d")+timedelta(days=1)
    if not 1 <= (end-start).days <= 200 or not 1 <= seconds <= 60 or price_source not in {"repository", "vendor-adjusted"}:
        raise ValueError("Limit this pilot to 200 days and 60 seconds per query")
    sys.path[:0] = [str(root), str(root/"api")]
    from dotenv import load_dotenv
    load_dotenv(root/".env")
    from repositories.market import main_flow, klines
    client = main_flow.get_client()

    class BoundedClient:
        def query(self, *args, **kwargs):
            if prefix is not None and "FROM trades" in args[0]:
                sql, params = sample_query(args[0], kwargs["parameters"], prefix)
                args, kwargs["parameters"] = (sql, *args[1:]), params
            kwargs["settings"] = {"max_execution_time": seconds, "max_threads": 2,
                                  "max_memory_usage": 2*1024**3, "max_rows_to_read": 2_000_000_000}
            return client.query(*args, **kwargs)

    main_flow.get_client = lambda: BoundedClient()
    klines.get_client = lambda: BoundedClient()
    source_hash = hashlib.sha256(Path(main_flow.__file__).read_bytes()).hexdigest()
    source = f"server-repository-main-flow-v1:{source_hash}"+(":checksum-prefix-0" if prefix is not None else "")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (output/".export.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    failures = []
    for case in protocol["primaryCases"]:
        ticker = case["ticker"]
        folder = output/ticker
        pages = folder/"flow-pages"
        pages.mkdir(parents=True, exist_ok=True, mode=0o700)
        prices_path = folder/"prices.csv"
        request = {"ticker": ticker, "from": protocol["collectionStart"], "to": protocol["analysisEnd"], "source": source}
        try:
            if not prices_path.exists():
                if price_source == "vendor-adjusted":
                    from shared.polygon import fetch_aggs
                    observations = list(fetch_aggs(ticker, 1, "day", protocol["collectionStart"], protocol["analysisEnd"]))
                    bars = [[b.timestamp, b.open, b.high, b.low, b.close, b.volume] for b in observations]
                else:
                    bars = klines.fetch_klines(ticker, 1, "day", protocol["collectionStart"], (end-timedelta(milliseconds=1)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
                if not bars:
                    raise ValueError("No daily price observations")
                with (folder/".prices.csv").open("w", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow(["datetime", "timestamp", "open", "high", "low", "close", "volume", "ticker"])
                    for bar in bars:
                        writer.writerow([datetime.fromtimestamp(bar[0]/1000, timezone.utc).strftime("%Y-%m-%d"), *bar, ticker])
                os.replace(folder/".prices.csv", prices_path)
                atomic_json(folder/"collection.json", {"request": request, "sha256": hashlib.sha256(prices_path.read_bytes()).hexdigest(),
                                                       "priceSource": price_source, "priceAdjusted": True if price_source == "vendor-adjusted" else None,
                                                       "fetchedAt": datetime.now(timezone.utc).isoformat()})
            else:
                receipt = json.loads((folder/"collection.json").read_text())
                if (receipt["request"] != request or receipt["sha256"] != hashlib.sha256(prices_path.read_bytes()).hexdigest()
                        or receipt.get("priceSource", "repository") != price_source):
                    raise ValueError("Price provenance mismatch; choose a fresh export directory")
            cursor = start
            while cursor < end:
                right = min(cursor+timedelta(days=7), end)
                params = {"ticker": ticker, "multiplier": 5, "timespan": "minute",
                          "from": cursor.strftime("%Y-%m-%d %H:%M:%S"),
                          "to": (right-timedelta(milliseconds=1)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                          "super_min": 500000, "large_min": 100000, "mid_min": 20000}
                if prefix is not None:
                    params["sample_prefix"] = prefix
                key = {"source": source, "params": params}
                digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
                path = pages/f"flow-{digest}.json"
                if path.exists():
                    saved = json.loads(path.read_text())
                    if saved.get("schema") != "flow-page-v1" or saved.get("request") != key or not isinstance(saved.get("rows"), list):
                        raise ValueError("Invalid saved flow page")
                    rows, mode = saved["rows"], "checkpoint"
                else:
                    rows = main_flow.fetch_main_flow(ticker, 5, "minute", params["from"], params["to"], 500000, 100000, 20000)
                    atomic_json(path, {"schema": "flow-page-v1", "request": key,
                                       "fetched_at": datetime.now(timezone.utc).isoformat(), "rows": rows})
                    mode = "server-query"
                print(json.dumps({"ticker": ticker, "from": params["from"], "to": params["to"], "rows": len(rows), "mode": mode}), flush=True)
                cursor = right
        except Exception as exc:
            failures.append({"ticker": ticker, "errorType": type(exc).__name__, "notZeroFlow": True})
            print(json.dumps({"ticker": ticker, "status": "stopped", "errorType": type(exc).__name__}), flush=True)
    atomic_json(output/"export-status.json", {"protocolId": protocol["id"], "source": source,
                                            "complete": not failures, "failures": failures})
    return not failures


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="/root/US_stock")
    p.add_argument("--protocol", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--max-query-seconds", type=int, default=45)
    p.add_argument("--price-source", choices=["repository", "vendor-adjusted"], default="repository")
    a = p.parse_args()
    raise SystemExit(0 if export(a.root, a.protocol, a.output, a.max_query_seconds, a.price_source) else 2)
