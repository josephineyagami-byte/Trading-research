import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "Backtest" / "backtest scripts & outputs"
sys.path.insert(0, str(SCRIPTS))
from flow_checkpoints import flow_page


class CheckpointTests(unittest.TestCase):
    def test_successful_page_is_private_resumable_and_has_provenance(self):
        fetch = Mock(return_value=[{"time": 1, "super_buy": 0}])
        params = {"ticker": "MSFT", "from": "2024-10-20", "to": "2024-11-19"}
        with tempfile.TemporaryDirectory() as directory:
            rows, source = flow_page("https://example.invalid", params, fetch, directory)
            again, resumed = flow_page("https://example.invalid", params, fetch, directory)
            self.assertEqual(rows, again)
            self.assertEqual((source, resumed), ("api", "checkpoint"))
            self.assertEqual(fetch.call_count, 1)
            path = next(Path(directory).glob("flow-*.json"))
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            saved = json.loads(path.read_text())
            self.assertIn("fetched_at", saved)
            self.assertEqual(saved["request"]["params"], params)

    def test_other_source_or_dates_do_not_reuse_checkpoint(self):
        fetch = Mock(return_value=[])
        with tempfile.TemporaryDirectory() as directory:
            flow_page("https://a.invalid", {"from": "2025-01-01"}, fetch, directory)
            flow_page("https://b.invalid", {"from": "2025-01-01"}, fetch, directory)
            flow_page("https://a.invalid", {"from": "2025-01-02"}, fetch, directory)
        self.assertEqual(fetch.call_count, 3)

    def test_failed_request_does_not_create_an_empty_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                flow_page("https://example.invalid", {}, Mock(return_value=None), directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_unknown_response_is_not_zero_flow(self):
        with self.assertRaises(ValueError):
            flow_page("https://example.invalid", {}, Mock(return_value={"error": "invalid"}))

    def test_date_only_end_includes_the_requested_final_session(self):
        import signal_generator_v4 as v4
        with patch.object(v4, "fetch", return_value=[[1, 1, 1, 1, 1, 1]]) as fetch:
            v4.load_klines("MSFT", "1d", 300, "2026-10-19", "2026-10-19")
        self.assertEqual(fetch.call_args.args[1]["to"], "2026-10-20")
        with patch.object(v4, "fetch", return_value=[]) as fetch:
            v4.load_main_flow("MSFT", "1d", 300, "2026-10-19", "2026-10-19")
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[1]["to"], "2026-10-20")

    def test_chunk_size_limits_individual_requests(self):
        import signal_generator_v4 as v4
        with patch.object(v4, "fetch", return_value=[]) as fetch:
            v4.load_main_flow("MSFT", "1d", 300, "2026-10-01", "2026-10-14", chunk_days=7)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args_list[0].args[1]["to"], "2026-10-08")
        self.assertEqual(fetch.call_args_list[1].args[1]["to"], "2026-10-15")
        with self.assertRaises(ValueError):
            v4.load_main_flow("MSFT", "1d", 300, chunk_days=0)

    def test_old_merged_snapshots_and_other_chunk_widths_are_not_reused(self):
        import signal_generator_v5_3 as v53
        monthly = v53._merged_cache_path("MSFT", "1d", "2024-10-20", "2026-10-19", 30)
        weekly = v53._merged_cache_path("MSFT", "1d", "2024-10-20", "2026-10-19", 7)
        self.assertNotEqual(monthly, weekly)
        self.assertIn("dates2", weekly)


if __name__ == "__main__":
    unittest.main()
