"""Refresh gap-overlapping requests into a new private version without changing old evidence."""

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil

from flow_checkpoints import flow_page
from flow_estimator import load_flow_checkpoints
from research_api import fetch_api, login_from_private_file


def refresh_checkpoints(original, destination, days, ticker, fetch):
    original, destination = Path(original).resolve(), Path(destination).resolve()
    if original == destination or original in destination.parents:
        raise ValueError("Use a separate versioned checkpoint directory")
    load_flow_checkpoints(original, ticker)
    days = sorted({date.fromisoformat(day) for day in days})
    if not days:
        raise ValueError("No repair dates to refresh")
    pages = [(path, path.read_bytes()) for path in sorted(original.glob("flow-*.json"))]
    fingerprint = hashlib.sha256(b"".join(path.name.encode()+hashlib.sha256(data).digest() for path, data in pages)).hexdigest()
    identity = {"schema": "flow-refresh-v1", "sourceFingerprint": fingerprint, "ticker": ticker,
                "dates": [day.isoformat() for day in days]}
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest_path = destination/"refresh-manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()).get("identity") != identity:
            raise ValueError("Refresh directory belongs to different evidence")
    elif any(destination.iterdir()):
        raise ValueError("Refuse a nonempty unowned checkpoint directory")
    manifest_path.write_text(json.dumps({"identity": identity, "complete": False}))
    os.chmod(manifest_path, 0o600)
    receipts = []
    for path, data in pages:
        page = json.loads(data)
        request = page["request"]
        params = request["params"]
        start, end = date.fromisoformat(params["from"]), date.fromisoformat(params["to"])
        refresh = any(start <= day < end for day in days)
        target = destination/path.name
        if refresh:
            rows, source = flow_page(request["source"], params,
                                     lambda endpoint, query: fetch(request["source"], endpoint, query), destination)
        else:
            if target.exists() and target.read_bytes() != data:
                raise ValueError("Retained checkpoint changed unexpectedly")
            if not target.exists():
                shutil.copy2(path, target)
                os.chmod(target, 0o600)
            rows, source = page["rows"], "retained"
        receipts.append({"file": path.name, "from": params["from"], "to": params["to"],
                         "rows": len(rows), "source": source,
                         "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        print(json.dumps({"from": params["from"], "to": params["to"], "rows": len(rows), "source": source}), flush=True)
    load_flow_checkpoints(destination, ticker)
    manifest_path.write_text(json.dumps({"identity": identity, "complete": True, "pages": receipts}, indent=2))
    return receipts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repair-snapshot", required=True)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--credentials-file", required=True)
    parser.add_argument("--api-username", required=True)
    args = parser.parse_args()
    snapshot = json.loads(Path(args.repair_snapshot).read_text())
    # Existing authenticated API sessions remain process-local, never stored in checkpoints.
    os.environ["US_STOCK_AUTH_COOKIE"] = login_from_private_file(args.api_base_url, args.credentials_file, args.api_username)
    def fetch(source, endpoint, params):
        if source != args.api_base_url:
            raise ValueError("Refresh must use the original trusted source")
        return fetch_api(source, endpoint, params, timeout=120)
    refresh_checkpoints(args.original, args.output,
                        snapshot["coverage"]["missingDates"]+snapshot["coverage"]["partialDates"], snapshot["ticker"], fetch)


if __name__ == "__main__":
    main()
