import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


path = Path(__file__).resolve().parents[1]/"ops"/"export_sequence_flow.py"
spec = importlib.util.spec_from_file_location("sequence_flow_export", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

START, END = "2025-10-01T14:00:00Z", "2025-10-01T14:10:00Z"


def row():
    left, _ = module.bounds("INTC", START, END, 30)
    return {"time": int(left.timestamp()*1000), **{key: 0. for key in module.AMOUNTS},
            "super_buy": 600000., "neutral_notional": 100., "total_notional": 600100., "sample_count": 2}


class SequenceFlowExportTests(unittest.TestCase):
    def test_direction_precedes_target_trimming_and_never_uses_checksum_sampling(self):
        sql = module.SQL
        self.assertNotIn("check_sum", sql)
        self.assertNotIn("startsWith", sql)
        self.assertIn("ORDER BY sip_timestamp, id", sql)
        self.assertIn("ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW", sql)
        self.assertIn("dateDiff('nanosecond'", sql)
        self.assertIn("> 60000000000", sql)
        self.assertGreater(sql.index("WHERE sip_timestamp >= {from_:String}"), sql.index("FROM classified"))
        self.assertIn("sip_timestamp < {to:String}", sql)
        for name in module.AMOUNTS:
            self.assertIn("AS "+name, sql)

    def test_exact_60_second_seed_and_canonical_utc_bounds(self):
        left, right = module.bounds("INTC", "2025-10-01T10:00:00-04:00", END, 30)
        request = module.request_for("INTC", left, right)
        self.assertEqual(request["params"]["from"], "2025-10-01 14:00:00")
        self.assertEqual(request["params"]["seed_from"], "2025-10-01 13:59:00")
        self.assertTrue(request["params"]["endExclusive"])

    def test_private_cache_is_atomic_verified_and_reused_without_a_new_query(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = Mock()
            observation = row()
            client.query.return_value = SimpleNamespace(column_names=list(observation), result_rows=[list(observation.values())])
            path, mode, count = module.export(root, root/".runtime-config"/"flow", "INTC", START, END, client=client)
            self.assertEqual((mode, count), ("server-query", 1))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            page = json.loads(path.read_text())
            self.assertFalse(page["rawTapeVerified"])
            self.assertFalse(page["productionEligible"])
            self.assertEqual(client.query.call_args.kwargs["settings"]["max_threads"], 2)
            self.assertEqual(client.query.call_args.kwargs["parameters"]["seed_from"], "2025-10-01 13:59:00")
            client.reset_mock()
            _, mode, count = module.export(root, path.parent, "INTC", START, END, client=client)
            self.assertEqual((mode, count), ("checkpoint", 1))
            client.query.assert_not_called()
            page["rows"][0]["sample_count"] = 999
            path.write_text(json.dumps(page))
            with self.assertRaises(ValueError):
                module.export(root, path.parent, "INTC", START, END, client=client)

    def test_query_failure_does_not_publish_a_complete_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = Mock()
            client.query.side_effect = TimeoutError("private connection details")
            output = root/".runtime-config"/"flow"
            with self.assertRaises(TimeoutError):
                module.export(root, output, "TSLA", START, END, client=client)
            self.assertEqual(list(output.glob("flow-*.json")), [])

    def test_unsafe_output_and_invalid_requests_fail_before_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = Mock()
            with self.assertRaises(ValueError):
                module.export(root, root/"public", "INTC", START, END, client=client)
            for ticker, start, end, seconds in [
                ("RGTI", START, END, 30), ("INTC", START, END, 100),
                ("INTC", "2025-10-01T14:01:00Z", END, 30),
                ("INTC", "2025-10-01T14:00:00", END, 30),
                ("INTC", START, "2025-10-03T14:00:00Z", 30),
                ("INTC", END, START, 30),
            ]:
                with self.assertRaises(ValueError):
                    module.export(root, root/".runtime-config"/"flow", ticker, start, end, seconds, client=client)
            client.query.assert_not_called()

    def test_invalid_totals_duplicates_and_bucket_bounds_are_rejected(self):
        left, right = module.bounds("INTC", START, END, 30)
        observation = row()
        for rows in [[{**observation, "total_notional": 1.}], [observation, observation],
                     [{**observation, "time": int(right.timestamp()*1000)}],
                     [{**observation, "sample_count": True}], [{**observation, "super_buy": float("inf")}]]:
            with self.assertRaises(ValueError):
                module.validate_rows(rows, left, right)

    def test_zero_observed_buckets_are_not_fabricated_zero_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = Mock()
            client.query.return_value = SimpleNamespace(column_names=[], result_rows=[])
            path, _, count = module.export(root, root/".runtime-config"/"flow", "INTC", START, END, client=client)
            self.assertEqual(count, 0)
            page = json.loads(path.read_text())
            self.assertEqual(page["rows"], [])
            self.assertIn("not zero", page["coverage"])

    def test_split_check_compares_all_tiers_and_requires_exact_adjacent_windows(self):
        left, right = module.bounds("INTC", START, END, 30)
        middle = left+(right-left)/2
        a = row()
        b = {**a, "time": a["time"]+300000}
        def page(start, end, rows):
            return {"schema":"flow-page-v1", "request":module.request_for("INTC", start, end),
                    "rows":rows, "rowsSha256":module.rows_hash(rows)}
        whole, first, second = page(left, right, [a,b]), page(left, middle, [a]), page(middle, right, [b])
        self.assertEqual(module.verify_split_pages(whole, first, second)["status"], "pass")
        changed = {**b, "super_buy": 0., "super_sell": 600000.}
        altered = page(middle, right, [changed])
        result = module.verify_split_pages(whole, first, altered)
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["mismatchTimes"], [b["time"]])
        with self.assertRaises(ValueError):
            module.verify_split_pages(whole, first, first)
        self.assertEqual(module.verify_split_pages(page(left, right, []), page(left, middle, []), page(middle, right, []))["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
