import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import io

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"Backtest"/"backtest scripts & outputs"))
from flow_case_audit import describe_price_flow, legacy_formula_audit, sampling_sensitivity, timeframe_audit
from flow_estimator import AMOUNTS, session_schedule
from run_flow_cases import build_pilot


def fixture(start="2025-03-06", end="2025-04-10"):
    schedule = session_schedule(start, end)
    n = len(schedule)
    prices = pd.DataFrame({"datetime": schedule.index, "open": 100+np.arange(n), "high": 102+np.arange(n),
                           "low": 99+np.arange(n), "close": 101+np.arange(n), "volume": 10000.})
    rows = []
    for s in schedule.itertuples():
        for t in pd.date_range(s.open, s.close, freq="5min", inclusive="left"):
            row = {name: 0. for name in AMOUNTS}
            row.update(time=t.value//1000000, super_buy=3., large_sell=5., neutral_notional=2., total_notional=10., sample_count=4)
            rows.append(row)
    return prices, rows


def legacy():
    return pd.DataFrame({"datetime": pd.date_range("2025-01-02", periods=3),
                         "trade_signal": ["long", "watch_short", "short"], "est_inst_participation": [10., 20., 10.],
                         "volume": [100., 200., 200.], "delta_inventory": [10., 0., -20.],
                         "cumulative_inventory": [10., 10., -10.]})


class CaseAuditTests(unittest.TestCase):
    def test_hourly_daily_amount_identity_is_not_independent_tape_validation(self):
        prices, rows = fixture()
        daily, hourly, checks, audit = timeframe_audit(prices, rows, "INTC")
        self.assertEqual(audit["status"], "pass")
        self.assertFalse(audit["independentSourceVerification"])
        self.assertTrue(audit["allSessionsCovered"])
        self.assertEqual(len(hourly), len(daily)*7)
        self.assertAlmostEqual(hourly.sampledLargeNetUsd.sum(), daily.sampledLargeNetUsd.sum())
        self.assertTrue(all(c["amountsMatch"] for c in checks))

    def test_open_anchored_hours_last_half_hour_and_early_close(self):
        prices, rows = fixture("2025-11-28", "2025-12-01")
        _, hourly, _, _ = timeframe_audit(prices, rows, "TSLA")
        self.assertEqual(hourly.groupby("date").expectedBars.apply(list).tolist(), [[12,12,12,6], [12,12,12,12,12,12,6]])

    def test_missing_bucket_can_reconcile_but_does_not_pass_coverage(self):
        prices, rows = fixture()
        daily, hourly, _, audit = timeframe_audit(prices, rows[1:], "INTC")
        self.assertEqual(audit["status"], "pass")
        self.assertFalse(audit["allSessionsCovered"])
        self.assertFalse(hourly.iloc[0].sessionComplete)
        self.assertTrue(pd.isna(hourly.iloc[0].pressure))
        self.assertEqual(daily.iloc[0].status, "partial")

    def test_no_source_retains_unavailable_amounts(self):
        prices, _ = fixture()
        daily, hourly, _, audit = timeframe_audit(prices, [], "INTC")
        self.assertTrue(daily.sampledLargeNetUsd.isna().all())
        self.assertTrue(hourly.sampledLargeNetUsd.isna().all())
        self.assertFalse(audit["allSessionsCovered"])

    def test_conflicting_duplicate_and_invalid_units_fail(self):
        prices, rows = fixture()
        with self.assertRaises(ValueError):
            timeframe_audit(prices, rows+[{**rows[0], "sample_count": 8}], "TSLA")
        with self.assertRaises(ValueError):
            timeframe_audit(prices, [{**rows[0], "total_notional": 1}]+rows[1:], "TSLA")

    def test_future_changes_cannot_change_earlier_descriptive_states(self):
        prices, rows = fixture()
        before = describe_price_flow(timeframe_audit(prices, rows, "TSLA")[0])
        boundary = session_schedule(prices.datetime.iloc[-1], prices.datetime.iloc[-1]).open.iloc[0].value//1000000
        changed = [{**r, "super_buy": 5., "large_sell": 3.} if r["time"] >= boundary else r for r in rows]
        after = describe_price_flow(timeframe_audit(prices, changed, "TSLA")[0])
        pd.testing.assert_frame_equal(before.iloc[:-1], after.iloc[:-1])
        self.assertEqual(before.iloc[-2].state, "negative_pressure_price_resilient_candidate")

    def test_legacy_arithmetic_is_not_the_deck_formula_or_holdings(self):
        result = legacy_formula_audit(legacy())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["zeroDirectionRows"], 1)
        self.assertFalse(result["reproducesCaseStudy"])

    def test_legacy_mismatch_does_not_silently_repair_saved_values(self):
        d = legacy()
        d.loc[1, "delta_inventory"] = 40.
        before = d.copy(deep=True)
        result = legacy_formula_audit(d)
        self.assertEqual(result["status"], "mismatch")
        self.assertGreater(result["deltaMismatchRows"], 0)
        pd.testing.assert_frame_equal(d, before)

    def test_missing_legacy_or_nonfinite_values_do_not_pass(self):
        self.assertEqual(legacy_formula_audit(pd.DataFrame())["status"], "unavailable")
        with self.assertRaises(ValueError):
            legacy_formula_audit(legacy().assign(volume=np.inf))

    def test_repository_diagnostic_never_fetches_missing_external_context(self):
        from legacy_case_replay import replay_repository
        prices, rows = fixture("2025-01-02", "2025-06-30")
        def neutral(frame, n_states):
            return frame.assign(hmm_state=-1, hmm_label="neutral", hmm_strength=0.)
        with patch("legacy_case_replay.v53.fit_hmm_safe", side_effect=neutral), patch("requests.get", side_effect=AssertionError("No network in offline replay")), redirect_stdout(io.StringIO()):
            out, metadata = replay_repository(prices, rows, "TSLA")
        self.assertEqual(legacy_formula_audit(out)["status"], "pass")
        self.assertTrue(metadata["samePriceInputsVerified"])
        self.assertFalse(metadata["reproducesCaseStudy"])
        self.assertTrue(out.relative_regime.eq("relative_unavailable").all())
        self.assertTrue(out.short_regime.eq("short_volume_missing").all())

    def test_sampling_sensitivity_is_not_reported_as_prediction_accuracy(self):
        prices, rows = fixture()
        daily = timeframe_audit(prices, rows, "INTC")[0]
        subset = daily.copy()
        subset["sampledNotionalUsd"] *= .5
        subset["pressure5"] *= -1
        subset["pressure20"] *= -1
        result = sampling_sensitivity(daily, subset, "2025-03-06", "2025-04-10")
        self.assertAlmostEqual(result["measuredNotionalFraction"], .5)
        self.assertEqual(result["windows"]["pressure5"]["sameSignSessions"], 0)
        self.assertIsNone(result["predictiveAccuracy"])
        subset["sampledNotionalUsd"] *= 3
        with self.assertRaises(ValueError):
            sampling_sensitivity(daily, subset, "2025-03-06", "2025-04-10")

    def test_html_preview_is_self_contained_and_retains_qualifications(self):
        from plot_flow_cases import render
        protocol = Path(__file__).resolve().parents[1]/"Backtest"/"flow_case_protocol.json"
        with tempfile.TemporaryDirectory() as directory:
            output = build_pilot(protocol, directory)
            html = render(output)
        self.assertIn('lang="en"', html)
        self.assertIn('data-locale="zh"', html)
        self.assertIn('not out-of-sample validation', html)
        self.assertIn('RGTI and BBAI: not run', html)
        self.assertNotIn('src="https://cdn.plot.ly', html)

    def test_uncollected_cases_remain_unavailable_and_pending_not_manipulated(self):
        protocol = Path(__file__).resolve().parents[1]/"Backtest"/"flow_case_protocol.json"
        with tempfile.TemporaryDirectory() as directory:
            output = build_pilot(protocol, directory)
            self.assertTrue(all(c["status"] == "unavailable" for c in output["cases"]))
            self.assertEqual(output["protocol"]["evaluationStatus"], "descriptive_case_study_not_out_of_sample")
            self.assertTrue(all(c["status"] == "not_run" for c in output["protocol"]["pendingCases"]))
            json.dumps(output, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
