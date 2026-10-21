import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Backtest" / "backtest scripts & outputs"))
from flow_estimator import AMOUNTS, estimate_daily_flow, load_flow_checkpoints, session_schedule
from flow_walk_forward import walk_forward


def fixture(start="2025-03-06", end="2025-03-12", net=-2):
    schedule = session_schedule(start, end)
    prices = pd.DataFrame({"datetime": schedule.index, "open": 100., "high": 110., "low": 90., "close": 101., "volume": 10000.})
    rows = []
    for day in schedule.itertuples():
        for t in pd.date_range(day.open, day.close, freq="5min", inclusive="left"):
            row = {name: 0. for name in AMOUNTS}
            row.update(time=t.value // 1_000_000, super_buy=(10+net)/2, super_sell=(10-net)/2,
                       total_notional=10., neutral_notional=0., sample_count=10)
            rows.append(row)
    return prices, rows


def replay_frame(count=350):
    dates = session_schedule("2024-01-02", "2026-01-01").index[:count]
    return pd.DataFrame({"date": dates, "open": 100+np.arange(len(dates))*.2,
                         "pressure5": .1 + np.sin(np.arange(len(dates))*.2)*.05})


class FlowEstimatorTests(unittest.TestCase):
    def test_signed_sampled_dollars_not_share_holdings_or_trade_recommendations(self):
        prices, raw = fixture()
        first = estimate_daily_flow(prices.assign(trade_signal="long"), raw, "MSFT")
        second = estimate_daily_flow(prices.assign(trade_signal="short", final_score=-1), raw, "MSFT")
        pd.testing.assert_frame_equal(first, second)
        self.assertTrue(first.sampledLargeNetUsd.lt(0).all())
        self.assertAlmostEqual(first.dailyPressure.iloc[0], -.2)
        self.assertLess(first.contiguousSampledNetUsd.iloc[-1], 0)

    def test_full_window_requires_every_complete_session(self):
        prices, raw = fixture()
        out = estimate_daily_flow(prices, raw, "MSFT")
        self.assertTrue(out.pressure5.iloc[:4].isna().all())
        self.assertAlmostEqual(out.pressure5.iloc[4], -.2)
        incomplete = estimate_daily_flow(prices, raw[1:], "MSFT")
        self.assertEqual(incomplete.status.iloc[0], "partial")
        self.assertTrue(incomplete.pressure5.isna().all())

    def test_missing_is_not_zero_and_cumulative_does_not_bridge_gap(self):
        prices, raw = fixture()
        opening = session_schedule("2025-03-06", "2025-03-12").open.iloc[2].value // 1_000_000
        raw = [r for r in raw if not opening <= r["time"] < opening+390*60000]
        out = estimate_daily_flow(prices, raw, "MSFT")
        self.assertEqual(out.status.iloc[2], "missing")
        self.assertTrue(pd.isna(out.sampledLargeNetUsd.iloc[2]))
        self.assertTrue(out.contiguousSampledNetUsd.iloc[2:].isna().all())

    def test_zero_observation_is_distinct_from_missing(self):
        prices, raw = fixture(net=0)
        out = estimate_daily_flow(prices, raw, "MSFT")
        self.assertTrue(out.sessionComplete.all())
        self.assertTrue(out.dailyPressure.eq(0).all())

    def test_early_close_and_dst_use_exchange_calendar(self):
        prices, raw = fixture("2025-11-28", "2025-12-01")
        out = estimate_daily_flow(prices, raw, "MSFT")
        self.assertEqual(out.expectedBars.tolist(), [42, 78])
        self.assertTrue(out.sessionComplete.all())
        schedule = session_schedule("2025-03-07", "2025-03-10")
        self.assertEqual(schedule.open.dt.hour.tolist(), [14, 13])

    def test_after_hours_and_close_boundary_are_excluded(self):
        prices, raw = fixture()
        close = session_schedule("2025-03-06", "2025-03-12").close.iloc[0].value // 1_000_000
        extra = {**raw[0], "time": close}
        first = estimate_daily_flow(prices, raw, "MSFT")
        pd.testing.assert_frame_equal(first, estimate_daily_flow(prices, raw+[extra], "MSFT"))

    def test_duplicates_reconcile_and_conflicting_revisions_fail(self):
        prices, raw = fixture()
        pd.testing.assert_frame_equal(estimate_daily_flow(prices, raw, "MSFT"), estimate_daily_flow(prices, raw+[raw[0]], "MSFT"))
        with self.assertRaises(ValueError):
            estimate_daily_flow(prices, raw+[{**raw[0], "sample_count": 20}], "MSFT")

    def test_invalid_amounts_and_missing_price_sessions_fail(self):
        prices, raw = fixture()
        for bad in [{**raw[0], "super_buy": -1}, {**raw[0], "total_notional": 1}, {**raw[0], "sample_count": 0}]:
            with self.assertRaises(ValueError):
                estimate_daily_flow(prices, [bad]+raw[1:], "MSFT")
        with self.assertRaises(ValueError):
            estimate_daily_flow(prices.drop(index=2), raw, "MSFT")

    def test_empty_source_retains_unknown(self):
        prices, _ = fixture()
        out = estimate_daily_flow(prices, [], "MSFT")
        self.assertTrue(out.status.eq("missing").all())
        self.assertTrue(out.pressure5.isna().all())

    def test_future_data_cannot_change_past_feature(self):
        prices, raw = fixture()
        before = estimate_daily_flow(prices, raw, "MSFT")
        cutoff = session_schedule("2025-03-06", "2025-03-12").open.iloc[-1].value // 1_000_000
        changed = [{**r, "super_buy": r["super_sell"], "super_sell": r["super_buy"]} if r["time"] >= cutoff else r for r in raw]
        after = estimate_daily_flow(prices, changed, "MSFT")
        pd.testing.assert_frame_equal(before.iloc[:-1], after.iloc[:-1])

    def test_checkpoint_ticker_and_units_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"flow-test.json"
            page = {"schema": "flow-page-v1", "request": {"source": "http://localhost", "params": {"ticker": "MSFT", "multiplier": 5, "timespan": "minute", "super_min": 500000, "large_min": 100000, "mid_min": 20000}}, "rows": []}
            path.write_text(json.dumps(page))
            self.assertEqual(load_flow_checkpoints(directory, "MSFT"), [])
            with self.assertRaises(ValueError):
                load_flow_checkpoints(directory, "AAPL")
            page["request"]["params"]["super_min"] = 5000
            path.write_text(json.dumps(page))
            with self.assertRaises(ValueError):
                load_flow_checkpoints(directory, "MSFT")


class WalkForwardTests(unittest.TestCase):
    def test_folds_are_disjoint_and_thresholds_use_training_only(self):
        d = replay_frame()
        decisions, replay, folds, summary = walk_forward(d)
        self.assertEqual(summary["folds"], len(folds))
        self.assertEqual(decisions.inTest.sum(), len(folds)*21)
        for fold in folds:
            self.assertLess(fold["trainEnd"], fold["testStart"])
            train = d[d.date.between(fold["trainStart"], fold["trainEnd"])].pressure5
            self.assertAlmostEqual(fold["upper"], train.quantile(.8))
        self.assertTrue((pd.to_datetime(replay.entryDate) > replay.date).all())
        self.assertTrue((pd.to_datetime(replay.exitDate) > pd.to_datetime(replay.entryDate)).all())

    def test_future_changes_do_not_change_earlier_decisions(self):
        d = replay_frame()
        before = walk_forward(d)[0]
        d.loc[d.index[-10:], "pressure5"] = -.9
        after = walk_forward(d)[0]
        pd.testing.assert_frame_equal(before.iloc[:-10], after.iloc[:-10])

    def test_next_open_returns_not_same_day_returns(self):
        d = replay_frame()
        d["open"] = 100+np.arange(len(d))**2*.01
        _, replay, _, _ = walk_forward(d)
        for i, row in replay.iterrows():
            self.assertAlmostEqual(row.benchmarkReturn, d.open.iloc[i+2]/d.open.iloc[i+1]-1)

    def test_missing_forecasts_are_cash_not_removed_from_denominator(self):
        d = replay_frame()
        d.loc[d.index[-40:], "pressure5"] = np.nan
        _, replay, _, summary = walk_forward(d)
        unavailable = replay[~replay.forecastAvailable]
        self.assertGreater(len(unavailable), 0)
        self.assertTrue(unavailable.position.eq(0).all())
        self.assertLess(summary["forecastCoverage"], 1)
        self.assertEqual(summary["realizedBars"], len(replay))

    def test_fees_and_liquidation_reduce_equity(self):
        d = replay_frame()
        free = walk_forward(d, fee_bps=0)[3]
        paid = walk_forward(d, fee_bps=10)[3]
        self.assertLess(paid["totalReturn"], free["totalReturn"])
        self.assertLess(paid["benchmarkReturn"], free["benchmarkReturn"])

    def test_insufficient_training_is_not_fabricated_forecast(self):
        d = replay_frame()
        d["pressure5"] = np.nan
        decisions, replay, folds, summary = walk_forward(d)
        self.assertFalse(decisions.forecastAvailable.any())
        self.assertEqual(summary["forecastCoverage"], 0)
        self.assertIsNone(summary["sharpe"])
        self.assertTrue(all(f["upper"] is None for f in folds))
        json.dumps({"folds": folds, "summary": summary}, allow_nan=False)

    def test_invalid_dates_and_parameters_fail(self):
        for d in [replay_frame().iloc[::-1], replay_frame(20), replay_frame().assign(open=0)]:
            with self.assertRaises(ValueError):
                walk_forward(d)
        with self.assertRaises(ValueError):
            walk_forward(replay_frame(), fee_bps=-1)
        for invalid in [np.inf, -np.inf, 2.]:
            with self.assertRaises(ValueError):
                walk_forward(replay_frame().assign(pressure5=invalid))


if __name__ == "__main__":
    unittest.main()
