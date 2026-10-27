from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"Backtest"/"backtest scripts & outputs"))
from legacy_forward_replay import replay_forward
import signal_generator_v4 as v4
from test_flow_cases import fixture


class EndpointHMMTests(unittest.TestCase):
    def frame(self):
        n = 101
        return pd.DataFrame({"datetime": pd.date_range("2025-01-01", periods=n),
                             "ofi_z": np.sin(np.arange(n)), "rvol": 1+np.arange(n)/100,
                             "impact_eff_z": np.cos(np.arange(n)), "vwap_dev": .01*np.arange(n),
                             "inst_net_z": 1+.1*np.sin(np.arange(n)), "ret": np.zeros(n)})

    def test_training_decode_and_scaling_exclude_decision_bar(self):
        instances = []
        class FakeHMM:
            def __init__(self, **kwargs):
                self.monitor_ = SimpleNamespace(history=[0, .001])
                self.tol = .01
                instances.append(self)
            def fit(self, x):
                self.training = x.copy()
            def predict(self, x):
                self.decoded = x.copy()
                return np.zeros(len(x), dtype=int)
            def score_samples(self, x):
                self.filtered = x.copy()
                return 0., np.tile([0., 1., 0.], (len(x), 1))
        d = self.frame()
        d.loc[100, ["ofi_z", "rvol", "impact_eff_z", "vwap_dev", "inst_net_z"]] = 10000.
        with patch("hmmlearn.hmm.GaussianHMM", FakeHMM), redirect_stdout(io.StringIO()):
            result = v4.fit_hmm(d, train_end="2025-04-10", causal_endpoint=True)
        model = instances[0]
        self.assertEqual(len(model.training), 100)
        self.assertEqual(len(model.decoded), 100)
        self.assertEqual(len(model.filtered), 101)
        np.testing.assert_allclose(model.training.mean(axis=0), 0, atol=1e-12)
        self.assertTrue(result.hmm_state.iloc[:100].eq(0).all())
        self.assertEqual(result.hmm_state.iloc[-1], 1)
        self.assertEqual(result.hmm_label.iloc[-1], "neutral")

    def test_too_little_training_or_multiple_decision_bars_never_fall_back(self):
        d = self.frame()
        with patch("hmmlearn.hmm.GaussianHMM") as hmm, redirect_stdout(io.StringIO()):
            for frame, end in [(d.iloc[:100], "2025-04-09"), (d, "2025-04-09")]:
                with self.assertRaises(ValueError):
                    v4.fit_hmm(frame, train_end=end, causal_endpoint=True)
            hmm.assert_not_called()
        with self.assertRaises(ValueError):
            v4.fit_hmm(d, causal_endpoint=True)

    def test_nonconverging_fit_is_not_reported_as_a_signal(self):
        class FailedHMM:
            def __init__(self, **kwargs):
                self.monitor_ = SimpleNamespace(history=[0., -5.])
                self.tol = .01
            def fit(self, x):
                pass
            def predict(self, x):
                raise AssertionError("Unstable fit must not be decoded")
        with patch("hmmlearn.hmm.GaussianHMM", FailedHMM), redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                v4.fit_hmm(self.frame(), train_end="2025-04-10", causal_endpoint=True)


class ForwardReplayTests(unittest.TestCase):
    @staticmethod
    def neutral(frame, n_states, train_end, causal_endpoint):
        assert causal_endpoint is True
        assert pd.Timestamp(train_end) == frame.datetime.iloc[-2]
        return frame.assign(hmm_state=0, hmm_label="neutral", hmm_strength=0.)

    def test_append_future_prices_flow_and_missingness_cannot_rewrite_saved_endpoints(self):
        prices, rows = fixture("2025-01-02", "2025-06-30")
        cutoff = 105
        last = pd.Timestamp(prices.datetime.iloc[cutoff-1], tz="UTC")+pd.Timedelta(days=1)
        earlier = [r for r in rows if r["time"] < last.value//1_000_000]
        changed_prices = prices.copy()
        changed_prices.loc[cutoff:, ["open", "high", "low", "close"]] *= 4
        changed = [r for r in rows if r["time"] < last.value//1_000_000 or r["sample_count"] != 4]
        with patch("legacy_forward_replay.v4.fit_hmm", side_effect=self.neutral), patch("requests.get", side_effect=AssertionError("No network")):
            before, _ = replay_forward(prices.iloc[:cutoff], earlier, "TSLA")
            after, _ = replay_forward(changed_prices, changed, "TSLA")
        pd.testing.assert_frame_equal(before, after.iloc[:cutoff].reset_index(drop=True))
        self.assertTrue(before.decisionStatus.iloc[:100].eq("insufficient_training").all())
        self.assertTrue(before.delta_inventory.iloc[:100].isna().all())
        self.assertTrue(before.decisionStatus.iloc[100:].eq("available").all())
        self.assertEqual(after.decisionStatus.iloc[-1], "incomplete_recent_flow")

    def test_recomputed_prefix_history_cannot_change_cumulative_saved_deltas(self):
        prices, rows = fixture("2025-01-02", "2025-06-30")
        def scored(frame, ticker):
            out = frame.assign(final_score=.1, trade_signal="long", est_inst_participation=10.,
                               delta_inventory=999., cumulative_inventory=999999.,
                               flow_reliability=1., flow_weight=.35)
            out.loc[out.index[-1], "delta_inventory"] = 1.
            return out
        with patch("legacy_forward_replay.v4.fit_hmm", side_effect=self.neutral), patch("legacy_forward_replay.v53.compute_signal", side_effect=scored):
            result, meta = replay_forward(prices, rows, "TSLA")
        available = result.decisionStatus.eq("available")
        self.assertEqual(result.cumulative_inventory.iloc[-1], int(available.sum()))
        self.assertTrue(result.delta_inventory.loc[available].eq(1).all())
        self.assertIsNone(meta["performance"])

    def test_fit_failure_is_explicit_and_not_zero_or_neutral_fallback(self):
        prices, rows = fixture("2025-01-02", "2025-06-30")
        with patch("legacy_forward_replay.v4.fit_hmm", side_effect=ValueError("unstable")):
            result, meta = replay_forward(prices, rows, "INTC")
        self.assertTrue(result.decisionStatus.iloc[100:].eq("fit_unavailable").all())
        self.assertTrue(result.delta_inventory.isna().all())
        self.assertEqual(meta["decisionCounts"]["fit_unavailable"], len(result)-100)

    def test_case_builder_and_preview_keep_forward_diagnostic_separate(self):
        from run_flow_cases import build_case, build_pilot
        from plot_flow_cases import render
        protocol_path = Path(__file__).resolve().parents[1]/"Backtest"/"flow_case_protocol.json"
        protocol = json.loads(protocol_path.read_text())
        prices, rows = fixture(protocol["collectionStart"], protocol["analysisEnd"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root/"INTC"
            (folder/"flow-pages").mkdir(parents=True)
            prices.to_csv(folder/"prices.csv", index=False)
            page = {"schema":"flow-page-v1", "request":{"source":"test:checksum-prefix-0", "params":{
                "ticker":"INTC", "multiplier":5, "timespan":"minute", "super_min":500000, "large_min":100000, "mid_min":20000}}, "rows":rows}
            (folder/"flow-pages"/"flow-test.json").write_text(json.dumps(page))
            with patch("legacy_forward_replay.v4.fit_hmm", side_effect=self.neutral):
                case = build_case(protocol["primaryCases"][0], protocol, folder, forward_legacy=True)
            data = build_pilot(protocol_path, directory)
            data["cases"][0] = case
            html = render(data)
        self.assertEqual(case["legacy"]["status"], "unavailable")
        self.assertEqual(case["legacyForward"]["status"], "partial")
        self.assertEqual(case["legacyForward"]["analysisSessions"], 87)
        self.assertIn("insufficient_training", case["legacyForward"]["analysisDecisionCounts"])
        self.assertIn("Prefix-only forward diagnostic", html)
        self.assertIn("训练不足", html)
        self.assertIn("not unseen validation", html)
        self.assertFalse(data["productionEligible"])
        json.dumps(case, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
