from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

path = Path(__file__).resolve().parents[1]/"ops/backfill_flow_gaps.py"
spec = importlib.util.spec_from_file_location("flow_gap_backfill", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(key):
    return [datetime(2026,9,15,tzinfo=timezone.utc), "MSFT", 1, key, 100., 10., 1, None, None, None, None, None, None, None, None, key]


class FlowGapBackfillTests(unittest.TestCase):
    def test_deduplicates_staging_and_preserves_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"day.sqlite"
            self.assertEqual(module.stage_day(path, {"day": "2026-09-15"}, lambda: iter(["a","a","b"]), row), 2)
            batches = []
            self.assertEqual(module.apply_day(path, {"a"}, batches.append), 1)
            self.assertEqual(batches[0][0][0], datetime(2026,9,15,tzinfo=timezone.utc))
            self.assertEqual(batches[0][0][-1], "b")

    def test_failure_during_download_cannot_apply_partial_day(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"day.sqlite"
            def trades():
                yield "a"
                raise RuntimeError("simulated failure")
            with self.assertRaises(RuntimeError):
                module.stage_day(path, {}, trades, row)
            with self.assertRaises(ValueError):
                module.apply_day(path, set(), lambda _: self.fail("must not insert"))

    def test_complete_download_resumes_without_new_vendor_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"day.sqlite"
            module.stage_day(path, {"day": 1}, lambda: iter(["a"]), row)
            self.assertEqual(module.stage_day(path, {"day": 1}, lambda: self.fail("must reuse completed stage"), row), 1)
            with self.assertRaises(ValueError):
                module.stage_day(path, {"day": 2}, lambda: iter([]), row)

    def test_safety_cap_keeps_stage_unapplied_and_retry_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"day.sqlite"
            with self.assertRaises(ValueError):
                module.stage_day(path, {}, lambda: iter(["a","b"]), row, maximum=1)
            module.stage_day(path, {}, lambda: iter(["a","b"]), row)
            self.assertEqual(module.apply_day(path, {"a","b"}, lambda _: self.fail("duplicate")), 0)


if __name__ == "__main__":
    unittest.main()
