"""Build a finite JSON snapshot for the website without rerunning v5.3 or publishing raw ticks."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

import pandas as pd

from flow_estimator import METHOD, estimate_daily_flow, load_flow_checkpoints
from flow_walk_forward import walk_forward


def records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def build_snapshot(prices, raw_rows, ticker):
    daily = estimate_daily_flow(prices, raw_rows, ticker)
    decisions, replay, folds, validation = walk_forward(daily)
    joined = daily.merge(decisions[["date", "inTest", "forecastAvailable", "position", "fold"]], on="date", validate="one_to_one")
    joined["date"] = joined.date.dt.strftime("%Y-%m-%d")
    replay = replay.copy()
    replay["date"] = pd.to_datetime(replay.date).dt.strftime("%Y-%m-%d")
    missing = joined.loc[joined.status.eq("missing"), "date"].tolist()
    partial = joined.loc[joined.status.eq("partial"), "date"].tolist()
    return {
        "schema": "flow-model-v1", "method": METHOD, "ticker": ticker,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataThrough": joined.date.iloc[-1], "firstDate": joined.date.iloc[0],
        "isLive": False, "holdings": None,
        "coverage": {"priceSessions": len(joined), "completeFlowSessions": int(joined.sessionComplete.sum()),
                     "missingDates": missing, "partialDates": partial, "calendar": "XNYS"},
        "validation": validation, "folds": folds, "series": records(joined), "replay": records(replay),
        "limitations": ["sampled tick-rule direction, not identified institutions or verified aggressors",
                        "amounts are sampled USD notional; no full-market extrapolation or conversion to holdings",
                        "historical raw data revisions/availability and price adjustment basis are not point-in-time verified",
                        "replay excludes borrow fees, slippage beyond the stated one-way fee, and financing costs",
                        "missing or partial sessions invalidate rolling estimates; a cumulative series stops at an interior gap"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", required=True)
    parser.add_argument("--flow-checkpoint-dir", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    ticker = args.ticker.strip().upper()
    if not ticker or len(ticker) > 12 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in ticker):
        parser.error("Invalid ticker")
    prices = pd.read_csv(args.prices)
    snapshot = build_snapshot(prices, load_flow_checkpoints(args.flow_checkpoint_dir, ticker), ticker)
    snapshot["sourcePriceSha256"] = hashlib.sha256(Path(args.prices).read_bytes()).hexdigest()
    pages = sorted(Path(args.flow_checkpoint_dir).glob("flow-*.json"))
    snapshot["sourceFlowFingerprint"] = hashlib.sha256(b"".join(path.name.encode()+hashlib.sha256(path.read_bytes()).digest() for path in pages)).hexdigest()
    # Strict JSON must fail rather than publish NaN or a guessed zero.
    snapshot = json.loads(json.dumps(snapshot, allow_nan=False))
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, delete=False) as handle:
        json.dump(snapshot, handle, allow_nan=False)
        temporary = Path(handle.name)
    os.replace(temporary, destination)
    print(json.dumps({"coverage": snapshot["coverage"], "validation": snapshot["validation"]}))


if __name__ == "__main__":
    main()
