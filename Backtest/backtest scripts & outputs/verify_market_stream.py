"""Read-only protocol-2 acceptance check; transport success is not real-time data success."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from urllib.parse import urlencode

import websockets

from research_api import _endpoint, login_from_private_file


def finite_number(value, minimum=0):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= minimum


def valid_payload(frame, channel):
    source, row = frame.get("sourceTime"), frame.get("data")
    if not finite_number(source, 1) or not isinstance(row, list) or len(row) != (5 if channel == "trades" else 6):
        return False
    if not finite_number(row[0], 1) or row[0] > source:
        return False
    if channel == "trades":
        return (row[0] == source and finite_number(row[1], .00000001) and finite_number(row[2], .00000001)
                and isinstance(row[3], int) and not isinstance(row[3], bool) and row[3] >= 0
                and isinstance(row[4], (str, list)))
    return (all(finite_number(value, .00000001) for value in row[1:5]) and finite_number(row[5])
            and row[2] >= max(row[1], row[3], row[4]) and row[3] <= min(row[1], row[2], row[4])
            and source-row[0] < 60_000)


async def probe_channel(base, token, origin, ticker, channel, duration=15):
    endpoint = _endpoint(base, f"/ws/{channel}", credentialed=True).replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    query = urlencode({"ticker": ticker, "protocol": 2, **({"multiplier": 1, "timespan": "minute"} if channel == "klines" else {})})
    facts = {"connected": False, "subscribed": False, "pong": False, "dataFrames": 0, "freshDataFrames": 0,
             "invalidDataFrames": 0, "delaySeconds": None,
             "sourceTime": None, "sequenceValid": True}
    sequence = 0
    try:
        async with websockets.connect(endpoint+"?"+query, additional_headers={"Cookie": f"auth={token}"},
                                      origin=origin, open_timeout=10) as socket:
            facts["connected"] = True
            await socket.send(json.dumps({"type": "subscribe", "id": "acceptance-sub"}))
            await socket.send(json.dumps({"type": "ping", "id": "acceptance-ping"}))
            deadline = asyncio.get_running_loop().time()+duration
            while asyncio.get_running_loop().time() < deadline:
                try:
                    frame = json.loads(await asyncio.wait_for(socket.recv(), max(.001, deadline-asyncio.get_running_loop().time())))
                except TimeoutError:
                    break
                if not isinstance(frame, dict) or frame.get("protocol") != 2 or frame.get("ticker") != ticker or frame.get("channel") != channel:
                    continue
                delay = frame.get("delaySeconds")
                if finite_number(delay) and delay <= 86400:
                    facts["delaySeconds"] = delay
                facts["subscribed"] |= frame.get("type") == "subscribed" and frame.get("id") == "acceptance-sub"
                facts["pong"] |= frame.get("type") == "pong" and frame.get("id") == "acceptance-ping"
                if frame.get("type") == "resync_required":
                    facts["sequenceValid"] = False
                if frame.get("type") == "data":
                    current = frame.get("sequence")
                    if not isinstance(current, int) or isinstance(current, bool) or current <= sequence or sequence and current != sequence+1:
                        facts["sequenceValid"] = False
                    sequence = current if isinstance(current, int) and not isinstance(current, bool) else sequence
                    source = frame.get("sourceTime")
                    if valid_payload(frame, channel):
                        facts["sourceTime"] = source
                        facts["dataFrames"] += 1
                        age_ms = datetime.now(timezone.utc).timestamp()*1000-source
                        if delay == 0 and not isinstance(delay, bool) and -5_000 <= age_ms <= 30_000:
                            facts["freshDataFrames"] += 1
                    else:
                        facts["invalidDataFrames"] += 1
            await socket.send(json.dumps({"type": "unsubscribe", "id": "acceptance-unsub"}))
    except Exception as error:
        facts["errorType"] = type(error).__name__
        facts["httpStatus"] = getattr(getattr(error, "response", None), "status_code", None)
    facts["transportPassed"] = facts["connected"] and facts["subscribed"] and facts["pong"]
    facts["realtimeDataPassed"] = (facts["transportPassed"] and facts["delaySeconds"] == 0
                                   and facts["freshDataFrames"] > 0 and facts["invalidDataFrames"] == 0
                                   and facts["sequenceValid"])
    return facts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--credentials-file")
    parser.add_argument("--api-username")
    parser.add_argument("--ticker", default="MSFT")
    parser.add_argument("--duration", type=int, default=15, choices=range(1, 121))
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-realtime", action="store_true")
    args = parser.parse_args()
    if not args.ticker or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in args.ticker) or len(args.ticker) > 12:
        parser.error("Invalid ticker")
    token = login_from_private_file(args.api_base_url, args.credentials_file, args.api_username) if args.credentials_file else os.environ.get("US_STOCK_AUTH_COOKIE", "")
    if not token or any(c.isspace() or c in ";," for c in token):
        parser.error("Provide an authorized session locally")
    result = {"checkedAt": datetime.now(timezone.utc).isoformat(), "ticker": args.ticker, "channels": {}}
    for channel in ("trades", "klines"):
        result["channels"][channel] = asyncio.run(probe_channel(args.api_base_url, token, args.origin, args.ticker, channel, args.duration))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps(result))
    passed = all(f["realtimeDataPassed" if args.require_realtime else "transportPassed"] for f in result["channels"].values())
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
