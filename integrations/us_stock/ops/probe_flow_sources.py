"""Read-only vendor entitlement and collector-log checks. Never print credentials or raw exceptions."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--ticker", default="MSFT")
    parser.add_argument("--date", default="2026-09-15")
    parser.add_argument("--latest", action="store_true")
    args = parser.parse_args()
    if not args.ticker.isalnum() or len(args.ticker) > 12:
        parser.error("Use one ticker")
    day = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    root = Path(args.project_root)
    load_dotenv(root / ".env")
    key = os.environ.get("POLYGON_API_KEY")
    result = {"checkedAt": datetime.now(timezone.utc).isoformat(), "ticker": args.ticker, "date": args.date}
    result["configuredWebsocketFeed"] = os.environ.get("POLYGON_WS_FEED", "delayed")
    if not key:
        result["history"] = {"status": "no_configured_key"}
    else:
        try:
            response = requests.get(f"https://api.massive.com/v3/trades/{args.ticker}",
                headers={"Authorization": f"Bearer {key}"}, params={"timestamp.gte": int(day.timestamp()*1e9),
                "timestamp.lt": int(day.timestamp()*1e9)+86_400_000_000_000, "limit": 1, "sort": "timestamp", "order": "asc"}, timeout=20)
            payload = response.json()
            result["history"] = {"httpStatus": response.status_code, "resultCount": len(payload.get("results", [])),
                                 "vendorStatus": payload.get("status")}
        except Exception as exc:
            result["history"] = {"errorType": type(exc).__name__}
        if args.latest:
            for name, endpoint in (("lastTrade", "trade"), ("lastQuote", "nbbo")):
                try:
                    response = requests.get(f"https://api.massive.com/v2/last/{endpoint}/{args.ticker}",
                        headers={"Authorization": f"Bearer {key}"}, timeout=20)
                    payload = response.json()
                    row = payload.get("results")
                    timestamp = row.get("t") if isinstance(row, dict) else None
                    result[name] = {"httpStatus": response.status_code, "vendorStatus": payload.get("status"),
                                    "hasResult": isinstance(row, dict) and bool(row),
                                    "sourceTimeNs": timestamp if isinstance(timestamp, int) else None}
                except Exception as exc:
                    result[name] = {"errorType": type(exc).__name__}
    path = root / "logs/ws_trades.log"
    if path.exists():
        with path.open("rb") as source:
            source.seek(max(0, path.stat().st_size-100_000))
            tail = source.read().decode("utf-8", errors="replace").lower()
        words = ("auth_success", "auth_failed", "not_authorized", "not entitled", "subscribed", "max_connections", "connecting stocks feed=")
        result["collectorTail"] = {"logModifiedAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
                                   "markers": {word: tail.count(word) for word in words}}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
