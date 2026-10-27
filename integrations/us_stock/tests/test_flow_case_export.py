import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[1]/"ops"/"export_flow_cases.py"
spec = importlib.util.spec_from_file_location("flow_case_export", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FlowCaseExportSafetyTests(unittest.TestCase):
    def test_sample_predicate_is_parameterized_before_window_direction(self):
        sql = "SELECT lagInFrame(price) OVER (ORDER BY sip_timestamp) FROM trades\n            WHERE ticker = {ticker:String}"
        result, params = module.sample_query(sql, {"ticker":"TSLA"}, "0")
        self.assertIn("startsWith(check_sum, {sample_prefix:String})", result)
        self.assertEqual(params, {"ticker":"TSLA", "sample_prefix":"0"})
        with self.assertRaises(ValueError):
            module.sample_query("SELECT * FROM trades", {}, "0")
        with self.assertRaises(ValueError):
            module.sample_query(sql, {}, "0' OR 1=1")

    def test_refuses_outputs_outside_private_runtime_directory_before_connecting(self):
        with self.assertRaises(ValueError):
            module.export("/tmp/example-site", "/does-not-exist", "/tmp/public")

    def test_rejects_unapproved_tickers_before_loading_site_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol = root/"protocol.json"
            protocol.write_text(json.dumps({"schema":"flow-case-protocol-v1", "primaryCases":[{"ticker":"RGTI"}]}))
            with self.assertRaises(ValueError):
                module.export(root, protocol, root/".runtime-config"/"pilot")

    def test_rejects_unbounded_window_and_query_budget_before_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol = root/"protocol.json"
            data = {"schema":"flow-case-protocol-v1", "primaryCases":[{"ticker":"INTC"},{"ticker":"TSLA"}],
                    "collectionStart":"2024-01-01", "analysisEnd":"2025-12-31"}
            protocol.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                module.export(root, protocol, root/".runtime-config"/"pilot")
            data["collectionStart"] = "2025-12-01"
            protocol.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                module.export(root, protocol, root/".runtime-config"/"pilot", seconds=600)


if __name__ == "__main__":
    unittest.main()
