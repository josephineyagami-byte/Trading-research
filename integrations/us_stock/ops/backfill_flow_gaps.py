"""Targeted, resumable tick repair. Stage a whole day before writing; never delete existing trades."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

UTC = timezone.utc
TIMESTAMP_COLUMNS = (0, 10, 11)


def decode_row(text):
    row = json.loads(text)
    for index in TIMESTAMP_COLUMNS:
        if row[index] is not None:
            row[index] = datetime.fromisoformat(row[index])
    return row


def stage_day(path, identity, trades, convert, maximum=2_000_000):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(path) as db:
        os.chmod(path, 0o600)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS rows (checksum TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        previous = db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
        encoded = json.dumps(identity, sort_keys=True)
        if previous and previous[0] != encoded:
            raise ValueError("Staging identity mismatch")
        db.execute("INSERT OR IGNORE INTO meta VALUES ('identity', ?)", (encoded,))
        if db.execute("SELECT value FROM meta WHERE key='complete'").fetchone():
            return db.execute("SELECT count(*) FROM rows").fetchone()[0]
        for count, trade in enumerate(trades(), 1):
            if count > maximum:
                raise ValueError("Daily trade safety cap exceeded; nothing applied")
            row = convert(trade)
            encoded_row = json.dumps(row, default=lambda value: value.isoformat(), allow_nan=False)
            db.execute("INSERT OR REPLACE INTO rows VALUES (?, ?)", (row[-1], encoded_row))
            if count % 5000 == 0:
                db.commit()
        db.execute("INSERT OR REPLACE INTO meta VALUES ('complete', '1')")
        db.commit()
        return db.execute("SELECT count(*) FROM rows").fetchone()[0]


def apply_day(path, existing_checksums, insert, batch_size=5000):
    written, batch = 0, []
    with sqlite3.connect(path) as db:
        if not db.execute("SELECT value FROM meta WHERE key='complete'").fetchone():
            raise ValueError("Refuse incomplete staged day")
        for checksum, payload in db.execute("SELECT checksum,payload FROM rows ORDER BY checksum"):
            if checksum in existing_checksums:
                continue
            batch.append(decode_row(payload))
            if len(batch) == batch_size:
                insert(batch)
                written += len(batch)
                batch = []
        if batch:
            insert(batch)
            written += len(batch)
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--stage-dir", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--include-partial", action="store_true")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=2)
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    sys.path.insert(0, str(root))
    from dotenv import load_dotenv
    load_dotenv(root/".env")
    from shared.db import get_client
    from shared.db.trades import TRADES_COLUMNS, trade_to_row
    from shared.db.tickers import get_or_create_ticker
    from shared.job_lock import job_lock
    from shared.polygon import fetch_trades

    snapshot = json.loads(Path(args.snapshot).read_text())
    ticker = snapshot["ticker"]
    days = snapshot["coverage"]["missingDates"] + (snapshot["coverage"]["partialDates"] if args.include_partial else [])
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,11}", ticker) or len(set(days)) > 40:
        parser.error("Expected one ticker and at most 40 explicit repair dates")
    days = sorted(set(days))
    if any(date.fromisoformat(d) >= datetime.now(UTC).date() for d in days):
        parser.error("Only completed historical dates may be repaired")
    print(json.dumps({"ticker": ticker, "dates": days, "apply": args.apply}), flush=True)
    if not args.apply:
        return
    with job_lock("market-backfill") as acquired:
        if not acquired:
            raise RuntimeError("Another market backfill is running")
        ticker_id = get_or_create_ticker(ticker)
        report = []

        def repair(day):
            client = get_client()
            end = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
            params = {"ticker": ticker, "start": day, "end": end}
            existing = {r[0] for r in client.query("SELECT check_sum FROM trades WHERE ticker={ticker:String} "
                "AND sip_timestamp >= {start:String} AND sip_timestamp < {end:String}", parameters=params,
                settings={"max_execution_time": 60}).result_rows}
            path = Path(args.stage_dir)/f"{ticker}-{day}.sqlite"
            total = stage_day(path, {"ticker": ticker, "day": day, "schema": 1},
                lambda: fetch_trades(ticker=ticker, total_limit=None, per_page=50000,
                    timestamp_gte=day, timestamp_lte=int(datetime.fromisoformat(end).replace(tzinfo=UTC).timestamp()*1e9)-1),
                lambda t: trade_to_row(ticker, t, ticker_id))
            written = apply_day(path, existing, lambda batch: client.insert("trades", batch, column_names=TRADES_COLUMNS))
            entry = {"date": day, "staged": total, "existingChecksums": len(existing), "inserted": written,
                     "sourceEmpty": total == 0}
            return entry

        pool = ThreadPoolExecutor(max_workers=args.workers)
        try:
            futures = [pool.submit(repair, day) for day in days]
            for future in as_completed(futures):
                entry = future.result()
                report.append(entry)
                print(json.dumps(entry), flush=True)
                (Path(args.stage_dir)/"report.json").write_text(json.dumps(report, indent=2))
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        print(json.dumps({"complete": True, "days": len(report), "inserted": sum(r["inserted"] for r in report)}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"failed": True, "errorType": type(error).__name__}), flush=True)
        sys.exit(1)
