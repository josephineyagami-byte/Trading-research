import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parents[1] / "Backtest" / "backtest scripts & outputs"
sys.path.insert(0, str(SCRIPTS))
from inventory_diagnostics import add_inventory_diagnostics, audit_summary
from market_data_quality import regular_session_mask, unique_timestamp_bars


def bars(changes):
    return pd.DataFrame({
        "datetime": pd.date_range("2025-01-01", periods=len(changes), freq="D"),
        "delta_inventory": changes,
        "volume": [100.0] * len(changes),
    })


class InventoryDiagnosticsTests(unittest.TestCase):
    def test_negative_is_valid_relative_change_not_negative_holdings(self):
        df = bars([-20, 5, -10])
        df["cumulative_inventory"] = [-20, -15, -25]
        out = add_inventory_diagnostics(df, window=2)
        self.assertEqual(out.cumulative_model_position_change_shares.tolist(), [-20, -15, -25])
        self.assertTrue(out.inventory_scenario_shares.isna().all())
        self.assertTrue(out.inventory_anchor_status.eq("missing_anchor").all())
        pd.testing.assert_frame_equal(out[df.columns], df)

    def test_new_pressure_indicator_uses_share_volume_not_price_or_usd(self):
        df = bars([20, -10, 0])
        df["close"] = [2, 500, 10000]
        out = add_inventory_diagnostics(df, window=2)
        np.testing.assert_allclose(out.model_flow_pressure_pct, [np.nan, 5, -5], equal_nan=True)

    def test_warmup_is_not_interpreted_as_zero(self):
        out = add_inventory_diagnostics(bars([np.nan, 10, -20]), window=2)
        np.testing.assert_allclose(out.cumulative_model_position_change_shares,
                                   [np.nan, 10, -10], equal_nan=True)
        self.assertTrue(pd.isna(out.model_flow_pressure_pct.iloc[1]))

    def test_interior_gap_does_not_silently_resume_cumulative_sum(self):
        out = add_inventory_diagnostics(bars([10, np.nan, 20, 10]), window=2)
        self.assertTrue(out.cumulative_model_position_change_shares.iloc[1:].isna().all())
        self.assertEqual(out.inventory_data_status.iloc[-1], "incomplete_after_gap")
        self.assertEqual(out.model_flow_pressure_pct.iloc[-1], 15)

    def test_missing_volume_also_invalidates_change(self):
        df = bars([10, 20, 30])
        df.loc[1, "volume"] = np.nan
        out = add_inventory_diagnostics(df)
        self.assertTrue(out.cumulative_model_position_change_shares.iloc[1:].isna().all())

    def test_zero_volume_is_not_divided_by_zero(self):
        df = bars([0, 0])
        df["volume"] = 0
        self.assertTrue(add_inventory_diagnostics(df, window=1).model_flow_pressure_pct.isna().all())

    def test_anchor_is_explicit_scenario_not_observed_inventory(self):
        out = add_inventory_diagnostics(bars([-20, 5]), initial_inventory_shares=100,
                                        anchor_source="synthetic test anchor", anchor_as_of="2024-12-31")
        self.assertEqual(out.inventory_scenario_shares.tolist(), [80, 85])
        self.assertTrue(out.inventory_anchor_status.eq("anchored_scenario_not_observed_holdings").all())

    def test_invalid_anchor_is_flagged_not_clipped(self):
        out = add_inventory_diagnostics(bars([-20, 40]), initial_inventory_shares=5,
                                        anchor_source="synthetic test anchor", anchor_as_of="2024-12-31")
        self.assertEqual(out.inventory_scenario_shares.tolist(), [-15, 25])
        self.assertTrue(out.inventory_anchor_status.eq("invalid_negative_scenario").all())

    def test_anchor_cannot_use_future_holdings_or_omit_provenance(self):
        for kwargs in [
            {"initial_inventory_shares": 100},
            {"initial_inventory_shares": -1, "anchor_source": "test", "anchor_as_of": "2024-12-31"},
            {"initial_inventory_shares": 100, "anchor_source": "test", "anchor_as_of": "2025-01-01"},
            {"anchor_source": "test"},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                add_inventory_diagnostics(bars([10]), **kwargs)

    def test_anchor_does_not_bridge_unknown_changes(self):
        out = add_inventory_diagnostics(bars([np.nan, 10]), initial_inventory_shares=100,
                                        anchor_source="synthetic", anchor_as_of="2024-12-31")
        self.assertTrue(out.inventory_scenario_shares.isna().all())
        self.assertTrue(out.inventory_anchor_status.eq("incomplete_scenario").all())

    def test_invalid_grain_order_units_and_window_fail(self):
        bad_inputs = [bars([10, 20]).iloc[::-1], bars([10, 20]).assign(datetime="2025-01-01"),
                      bars([101]), bars([10]).assign(volume=-1), bars([np.inf]),
                      bars([10, 20]).assign(ticker=["AAPL", "MSFT"]), bars([10]).assign(datetime=pd.NaT)]
        for df in bad_inputs:
            with self.subTest(df=df), self.assertRaises(ValueError):
                add_inventory_diagnostics(df)
        for window in [0, -1, True, 1.5]:
            with self.subTest(window=window), self.assertRaises(ValueError):
                add_inventory_diagnostics(bars([10]), window=window)

    def test_all_missing_remains_unknown_and_json_safe(self):
        summary = audit_summary(bars([np.nan, np.nan]), "synthetic")
        self.assertIsNone(summary["cumulative_model_position_change_shares"])
        json.dumps(summary, allow_nan=False)

    def test_repository_negative_msft_output_is_preserved(self):
        path = SCRIPTS / "outputs/MSFT_1d_20260602_133016_signals.csv"
        df = pd.read_csv(path)
        summary = audit_summary(df, path.name)
        self.assertEqual(summary["rows"], 353)
        self.assertLess(summary["cumulative_model_position_change_shares"], -65_000_000)
        self.assertEqual(summary["legacy_cumulative_mismatch_rows"], 0)
        self.assertIsNone(summary["institutional_holdings_shares"])


class MarketDataTests(unittest.TestCase):
    def test_loader_honors_api_base_url_override(self):
        result = subprocess.run(
            [sys.executable, "-c", "import signal_generator_v4 as v4; print(v4.BASE_URL)"],
            cwd=SCRIPTS, env={**os.environ, "US_STOCK_API_BASE_URL": "https://example.invalid/api/"},
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout.strip(), "https://example.invalid/api")

    def test_et_session_filter_handles_winter_and_summer_dst(self):
        times = pd.to_datetime(["2025-01-06T13:35Z", "2025-01-06T14:35Z",
                                "2025-07-07T13:35Z", "2025-07-07T20:00Z",
                                "2025-07-05T14:00Z"])
        ms = pd.Series(times.astype("int64") // 1_000_000)
        self.assertEqual(regular_session_mask(ms).tolist(), [False, True, True, False, False])

    def test_exact_overlap_is_counted_once_and_conflict_fails(self):
        df = pd.DataFrame({"timestamp": [1, 2, 2], "inst_net": [10, -20, -20]})
        self.assertEqual(unique_timestamp_bars(df).inst_net.sum(), -10)
        df.loc[2, "inst_net"] = 30
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            unique_timestamp_bars(df)

    def test_v53_merge_does_not_multiply_ohlcv_rows(self):
        from signal_generator_v5_3 import merge_flow
        dates = pd.date_range("2025-01-01", periods=2)
        df = pd.DataFrame({"datetime": dates})
        flow = pd.DataFrame({"date": [dates[0], dates[0]], "inst_net": [1, 2],
                             "xl_net": [1, 2], "l_net": [0, 0]})
        with self.assertRaises(pd.errors.MergeError):
            merge_flow(df, flow)

    def test_main_flow_loader_deduplicates_page_boundaries(self):
        import signal_generator_v4 as v4
        stamp = int(pd.Timestamp("2025-07-02T14:00Z").timestamp() * 1000)
        row = {"timestamp": stamp, "super_buy": 100, "super_sell": 200}
        with patch.object(v4, "fetch", side_effect=[[row], [row]]):
            with contextlib.redirect_stdout(io.StringIO()):
                out = v4.load_main_flow("TEST", "1d", 100, "2025-07-01", "2025-08-02")
        self.assertEqual(len(out), 1)
        self.assertEqual(out.inst_net.iloc[0], -100)

    def test_v53_exports_new_columns_without_changing_scores(self):
        import signal_generator_v5_3 as v53
        df = pd.read_csv(SCRIPTS / "outputs/MSFT_1d_20260602_151813_signals.csv")
        df["datetime"] = pd.to_datetime(df["datetime"])
        with contextlib.redirect_stdout(io.StringIO()):
            out = v53.compute_signal(df, "MSFT")
            with patch.object(v53, "add_inventory_diagnostics", side_effect=lambda frame: frame):
                baseline = v53.compute_signal(df, "MSFT")
        pd.testing.assert_frame_equal(out[baseline.columns], baseline)
        self.assertIn("model_flow_pressure_pct", out)
        expected = (out.trade_signal.map({"long": 1, "short": -1}).fillna(0)
                    * out.est_inst_participation / 100 * out.volume)
        pd.testing.assert_series_equal(out.delta_inventory, expected, check_names=False)
        with tempfile.TemporaryDirectory() as tmp, patch.object(v53, "OUTPUT_DIR", tmp):
            saved = pd.read_csv(v53.save_output(out, "MSFT", "1d"))
        self.assertIn("model_flow_pressure_pct", saved)
        self.assertTrue(saved.inventory_semantics.eq("model_change_not_holdings").all())

    def test_plot_uses_relative_change_label_and_new_indicator(self):
        from plot_inst_flow import build_chart
        df = bars([-10, 5] * 15)
        df = df.assign(open=10, high=11, low=9, close=10)
        fig = build_chart(df, "TEST", "1d")
        self.assertEqual(len(fig.layout.annotations), 4)
        self.assertIn("not holdings", fig.layout.annotations[2].text)
        trace = next(t for t in fig.data if t.name == "Model position change")
        self.assertEqual(trace.y[-1], -75)
        self.assertTrue(any(t.name == "20-bar model flow pressure" for t in fig.data))


if __name__ == "__main__":
    unittest.main()
