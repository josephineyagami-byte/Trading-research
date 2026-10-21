import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

import websockets

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"Backtest"/"backtest scripts & outputs"))
from verify_market_stream import probe_channel


class AcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def check_feed(self, delay, data, age_seconds=0, malformed=False):
        async def handler(socket):
            async for raw in socket:
                command = json.loads(raw)
                if command["type"] == "unsubscribe":
                    return
                kind = "subscribed" if command["type"] == "subscribe" else "pong"
                frame = {"protocol":2,"ticker":"MSFT","channel":"trades","type":kind,"id":command["id"],"delaySeconds":delay}
                await socket.send(json.dumps(frame))
                if data and kind == "pong":
                    timestamp = int((datetime.now(timezone.utc).timestamp()-age_seconds)*1000)
                    await socket.send(json.dumps({**frame,"type":"data","sequence":1,"sourceTime":timestamp,
                                                  "data": [] if malformed else [timestamp,100,20,4,""]}))
        async with websockets.serve(handler,"127.0.0.1",0) as server:
            port = server.sockets[0].getsockname()[1]
            return await probe_channel(f"http://127.0.0.1:{port}","isolated-test","http://localhost","MSFT","trades",.05)

    async def test_heartbeat_without_data_is_not_realtime_acceptance(self):
        result=await self.check_feed(0,False)
        self.assertTrue(result["transportPassed"])
        self.assertFalse(result["realtimeDataPassed"])

    async def test_delayed_frames_cannot_pass_realtime_gate(self):
        result=await self.check_feed(900,True)
        self.assertEqual(result["dataFrames"],1)
        self.assertFalse(result["realtimeDataPassed"])

    async def test_missing_latency_cannot_silently_default_to_realtime(self):
        result=await self.check_feed(None,True)
        self.assertFalse(result["realtimeDataPassed"])

    async def test_fresh_valid_frames_pass(self):
        result=await self.check_feed(0,True)
        self.assertEqual(result["freshDataFrames"],1)
        self.assertTrue(result["realtimeDataPassed"])

    async def test_old_frame_with_zero_delay_label_is_not_live(self):
        result=await self.check_feed(0,True,age_seconds=900)
        self.assertEqual(result["dataFrames"],1)
        self.assertEqual(result["freshDataFrames"],0)
        self.assertFalse(result["realtimeDataPassed"])

    async def test_invalid_payload_is_not_live(self):
        result=await self.check_feed(0,True,malformed=True)
        self.assertEqual(result["invalidDataFrames"],1)
        self.assertFalse(result["realtimeDataPassed"])

    async def test_future_timestamp_is_not_live(self):
        result=await self.check_feed(0,True,age_seconds=-60)
        self.assertEqual(result["freshDataFrames"],0)
        self.assertFalse(result["realtimeDataPassed"])
