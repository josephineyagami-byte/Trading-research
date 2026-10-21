"""Chronological, next-open execution replay of one fixed flow rule, not a fitted inventory model."""

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit


def walk_forward(frame, train_size=252, test_size=21, gap=5, fee_bps=10.0, min_train_valid=120):
    for value in (train_size, test_size, gap, min_train_valid):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("Positive integer split sizes are required")
    if isinstance(fee_bps, bool) or not np.isfinite(fee_bps) or not 0 <= fee_bps <= 100:
        raise ValueError("Invalid one-way fee")
    d = frame.copy().reset_index(drop=True)
    dates = pd.to_datetime(d.date)
    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("Chronological unique dates are required")
    if not np.isfinite(d.open).all() or (d.open <= 0).any():
        raise ValueError("Valid opens are required for execution")
    pressure = d.pressure5.dropna()
    if not np.isfinite(pressure).all() or (pressure.abs() > 1.000001).any():
        raise ValueError("Flow pressure must be a bounded sampled notional ratio")
    splits = min(10, (len(d) - train_size - gap) // test_size)
    if splits < 2:
        raise ValueError("Not enough history for at least two full out-of-sample folds")
    splitter = TimeSeriesSplit(n_splits=splits, max_train_size=train_size, test_size=test_size, gap=gap)
    decisions = pd.DataFrame({"date": dates, "inTest": False, "forecastAvailable": False,
                              "position": np.nan, "lower": np.nan, "upper": np.nan, "fold": np.nan})
    folds = []
    for number, (train, test) in enumerate(splitter.split(d), 1):
        if train[-1] + gap >= test[0]:
            raise ValueError("Training/test overlap")
        scores = d.loc[train, "pressure5"].dropna()
        sufficient = len(scores) >= min_train_valid
        lower, upper = (float(scores.quantile(.2)), float(scores.quantile(.8))) if sufficient else (np.nan, np.nan)
        current = d.loc[test, "pressure5"]
        available = current.notna() & sufficient
        positions = pd.Series(0.0, index=test)
        if sufficient:
            positions.loc[available & (current > max(0, upper))] = 1
            positions.loc[available & (current < min(0, lower))] = -1
        decisions.loc[test, "inTest"] = True
        decisions.loc[test, "forecastAvailable"] = available
        decisions.loc[test, "position"] = positions
        decisions.loc[test, "lower"], decisions.loc[test, "upper"] = lower, upper
        decisions.loc[test, "fold"] = number
        folds.append({"fold": number, "trainStart": dates.iloc[train[0]].strftime("%Y-%m-%d"),
                      "trainEnd": dates.iloc[train[-1]].strftime("%Y-%m-%d"),
                      "testStart": dates.iloc[test[0]].strftime("%Y-%m-%d"),
                      "testEnd": dates.iloc[test[-1]].strftime("%Y-%m-%d"),
                      "trainValid": len(scores), "forecastCount": int(available.sum()),
                      "lower": lower if sufficient else None, "upper": upper if sufficient else None})
    # A close-of-day estimate cannot earn that day's return. Entry is next open,
    # exit/next rebalance the following open. Missing forecasts explicitly mean cash.
    next_return = d.open.shift(-2) / d.open.shift(-1) - 1
    realized = decisions.inTest & next_return.notna()
    positions = decisions.position.fillna(0)
    turnover = positions.diff().abs().fillna(positions.abs())
    fee = fee_bps / 10_000
    gross = positions * next_return
    net = gross - turnover * fee
    last = np.flatnonzero(realized)
    if len(last):
        net.iloc[last[-1]] -= abs(positions.iloc[last[-1]]) * fee
    replay = decisions.loc[realized].copy()
    replay["entryDate"] = dates.shift(-1).loc[realized].dt.strftime("%Y-%m-%d")
    replay["exitDate"] = dates.shift(-2).loc[realized].dt.strftime("%Y-%m-%d")
    replay["grossReturn"] = gross.loc[realized]
    replay["netReturn"] = net.loc[realized]
    replay["benchmarkReturn"] = next_return.loc[realized]
    if replay.empty:
        raise ValueError("No realized out-of-sample returns")
    if (replay.netReturn <= -1).any():
        raise ValueError("Replay lost all equity; no unbounded leverage assumption allowed")
    replay["strategyEquity"] = (1 + replay.netReturn).cumprod()
    benchmark = replay.benchmarkReturn.copy()
    benchmark.iloc[0] -= fee
    benchmark.iloc[-1] -= fee
    replay["benchmarkEquity"] = (1 + benchmark).cumprod()
    equity = replay.strategyEquity.to_numpy()
    peaks = np.maximum.accumulate(np.r_[1, equity])[1:]
    std = replay.netReturn.std(ddof=1)
    summary = {
        "folds": len(folds), "realizedBars": len(replay), "forecastBars": int(replay.forecastAvailable.sum()),
        "forecastCoverage": float(replay.forecastAvailable.mean()), "feeBpsOneWay": fee_bps,
        "totalReturn": float(equity[-1] - 1), "benchmarkReturn": float(replay.benchmarkEquity.iloc[-1] - 1),
        "maxDrawdown": float(np.min(equity / peaks - 1)),
        "sharpe": float(replay.netReturn.mean() / std * np.sqrt(252)) if std > 0 else None,
        "evaluationStatus": "research_replay_not_point_in_time_verified",
        "execution": "decision at close; enter next session open; mark/rebalance following open",
        "missingForecastPolicy": "cash; missing forecasts retained in coverage denominator",
        "trainSize": train_size, "testSize": test_size, "gap": gap,
    }
    return decisions, replay, folds, summary
