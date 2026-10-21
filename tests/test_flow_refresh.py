import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"Backtest"/"backtest scripts & outputs"))
from flow_checkpoints import flow_page
from refresh_flow_checkpoints import refresh_checkpoints


class RefreshTests(unittest.TestCase):
    def test_only_overlapping_pages_are_refetched_and_originals_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            original, updated = Path(directory)/"old", Path(directory)/"new"
            for start, end in [("2026-09-01", "2026-09-08"), ("2026-09-08", "2026-09-15")]:
                params = {"ticker": "MSFT", "from": start, "to": end, "multiplier": 5, "timespan": "minute",
                          "super_min": 500000, "large_min": 100000, "mid_min": 20000}
                flow_page("http://localhost", params, lambda *_: [], original)
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in original.glob("flow-*.json")}
            calls = []
            def fetch(source, endpoint, params):
                calls.append(params["from"])
                return []
            receipts = refresh_checkpoints(original, updated, ["2026-09-09"], "MSFT", fetch)
            self.assertEqual(calls, ["2026-09-08"])
            self.assertEqual({r["source"] for r in receipts}, {"api", "retained"})
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in original.glob("flow-*.json")})
            refresh_checkpoints(original, updated, ["2026-09-09"], "MSFT", fetch)
            self.assertEqual(len(calls), 1)
            with self.assertRaises(ValueError):
                refresh_checkpoints(original, original, ["2026-09-09"], "MSFT", fetch)
            with self.assertRaises(ValueError):
                refresh_checkpoints(original, updated, ["2026-09-10"], "MSFT", fetch)
