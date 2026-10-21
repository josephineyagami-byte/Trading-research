"""Check completed private staging files without querying or mutating the production tape."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--day")
    args = parser.parse_args()
    receipts = []
    for path in sorted(Path(args.directory).glob("MSFT-*.sqlite")):
        if args.day and path.name != f"MSFT-{args.day}.sqlite":
            continue
        connection = sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)
        try:
            identity = json.loads(connection.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0])
            complete = connection.execute("SELECT value FROM meta WHERE key='complete'").fetchone() is not None
            if not complete:
                receipts.append({"date": identity["day"], "complete": False})
                continue
            count, first, last = connection.execute("SELECT count(*), min(json_extract(payload,'$[0]')), max(json_extract(payload,'$[0]')) FROM rows").fetchone()
            start = datetime.combine(date.fromisoformat(identity["day"]), datetime.min.time(), timezone.utc)
            inside = (not count or start <= datetime.fromisoformat(first) <= datetime.fromisoformat(last) < start+timedelta(days=1))
            receipts.append({"date": identity["day"], "complete": True, "rows": count,
                             "firstTimestamp": first, "lastTimestamp": last, "timestampsInsideRequestedDay": inside})
        finally:
            connection.close()
    print(json.dumps({"files": receipts, "completedDates": sum(row["complete"] for row in receipts),
                      "allCompletedDatesInBounds": all(row.get("timestampsInsideRequestedDay", True) for row in receipts)}))


if __name__ == "__main__":
    main()
