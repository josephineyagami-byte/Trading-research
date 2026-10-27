"""Sampled large-trade direction, independent of trade recommendations or holdings."""

import json
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

AMOUNTS = [f"{tier}_{side}" for tier in ("super", "large", "mid", "small") for side in ("buy", "sell")]
METHOD = "sampled-tick-rule-v1"


def load_flow_checkpoints(directory, ticker):
    rows, signature = [], None
    for path in sorted(Path(directory).glob("flow-*.json")):
        page = json.loads(path.read_text(encoding="utf-8"))
        if page.get("schema") != "flow-page-v1" or not isinstance(page.get("rows"), list):
            raise ValueError("Invalid flow checkpoint")
        params = page.get("request", {}).get("params", {})
        if params.get("ticker") != ticker:
            raise ValueError("Mixed ticker checkpoints")
        current = tuple(params.get(k) for k in ("multiplier", "timespan", "super_min", "large_min", "mid_min"))
        if current != (5, "minute", 500_000, 100_000, 20_000):
            raise ValueError("Use comparable five-minute checkpoints with the documented USD thresholds")
        source = page.get("request", {}).get("source")
        if signature is not None and signature != (source, current):
            raise ValueError("Mixed flow sources or thresholds")
        signature = source, current
        rows.extend(page["rows"])
    if signature is None:
        raise ValueError("No completed flow checkpoints")
    return rows


def session_schedule(start, end):
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    calendar = xcals.get_calendar("XNYS", start=start - pd.Timedelta(days=10), end=end + pd.Timedelta(days=10))
    return calendar.schedule.loc[start:end, ["open", "close"]].copy()


def normalize_flow_samples(raw_rows):
    """Validate and deduplicate numeric 5m samples before any aggregation."""
    columns = ["time", *AMOUNTS, "total_notional", "neutral_notional", "sample_count"]
    raw = pd.DataFrame(raw_rows, columns=columns)
    if raw.empty:
        return raw
    if raw.map(lambda value: isinstance(value, (bool, np.bool_))).any().any():
        raise ValueError("Boolean flow values are not amounts or counts")
    raw = raw.apply(pd.to_numeric, errors="raise")
    if not np.isfinite(raw).all().all() or (raw < 0).any().any():
        raise ValueError("Invalid flow amounts")
    if ((raw.time % 300_000 != 0).any() or (raw.sample_count <= 0).any()
            or (raw.sample_count % 1 != 0).any() or (raw.total_notional <= 0).any()):
        raise ValueError("Invalid five-minute flow grain or sample count")
    if not np.allclose(raw[AMOUNTS + ["neutral_notional"]].sum(axis=1), raw.total_notional, rtol=1e-7, atol=.01):
        raise ValueError("Flow buckets do not reconcile to total sampled notional")
    raw = raw.drop_duplicates()
    if raw.time.duplicated().any():
        raise ValueError("Conflicting repeated flow bars")
    return raw


def estimate_daily_flow(prices, raw_rows, ticker):
    """Aggregate samples without inferring missing trades or full-market flow."""
    return estimate_daily_flow_with_samples(prices, raw_rows, ticker)[0]


def estimate_daily_flow_with_samples(prices, raw_rows, ticker):
    """Return daily estimates and the same normalized regular-session samples."""
    required = ["datetime", "open", "high", "low", "close", "volume"]
    if not set(required) <= set(prices):
        raise ValueError("Price OHLCV and datetime are required")
    p = prices[required].copy()
    dt = pd.to_datetime(p.pop("datetime"), errors="raise", utc=True)
    p.index = pd.DatetimeIndex(dt.dt.tz_localize(None).dt.normalize(), name="date")
    if p.empty or not p.index.is_unique or not p.index.is_monotonic_increasing:
        raise ValueError("Prices must be nonempty, unique and chronological")
    if "ticker" in prices and not prices["ticker"].eq(ticker).all():
        raise ValueError("Mixed price tickers")
    if p.map(lambda value: isinstance(value, (bool, np.bool_))).any().any():
        raise ValueError("Boolean price values are not market observations")
    values = p.apply(pd.to_numeric, errors="raise")
    if (not np.isfinite(values).all().all() or (values[["open", "high", "low", "close"]] <= 0).any().any()
            or (values.volume < 0).any() or (values.high < values[["open", "close", "low"]].max(axis=1)).any()
            or (values.low > values[["open", "close", "high"]].min(axis=1)).any()):
        raise ValueError("Invalid price values")
    schedule = session_schedule(p.index[0], p.index[-1])
    if not p.index.equals(schedule.index.rename("date")):
        raise ValueError("Price dates must match the exchange calendar; repair missing sessions first")
    p = values
    expected = ((schedule.close - schedule.open).dt.total_seconds() / 300).astype(int)
    raw = normalize_flow_samples(raw_rows)
    if len(raw):
        opens = schedule.open.astype("int64").to_numpy() // 1_000_000
        closes = schedule.close.astype("int64").to_numpy() // 1_000_000
        location = np.searchsorted(opens, raw.time.to_numpy(), side="right") - 1
        safe = np.maximum(location, 0)
        regular = (location >= 0) & (raw.time.to_numpy() < closes[safe])
        raw = raw.loc[regular].copy()
        raw["date"] = schedule.index[safe[regular]]
        raw["large_net_usd"] = raw.super_buy + raw.large_buy - raw.super_sell - raw.large_sell
        daily = raw.groupby("date").agg(
            sampledLargeNetUsd=("large_net_usd", "sum"), sampledNotionalUsd=("total_notional", "sum"),
            sampleCount=("sample_count", "sum"), sourceBars=("time", "count"),
        )
        if not np.isfinite(daily).all().all() or (daily.sampledNotionalUsd <= 0).any() or (daily.sampleCount <= 0).any():
            raise ValueError("Daily aggregation overflow or invalid totals")
    else:
        daily = pd.DataFrame(columns=["sampledLargeNetUsd", "sampledNotionalUsd", "sampleCount", "sourceBars"])
    out = p.join(daily)
    out["expectedBars"] = expected.to_numpy()
    out["sessionComplete"] = out.sourceBars.eq(out.expectedBars)
    out["status"] = np.where(out.sourceBars.isna(), "missing", np.where(out.sessionComplete, "complete", "partial"))
    valid_net = out.sampledLargeNetUsd.where(out.sessionComplete)
    valid_total = out.sampledNotionalUsd.where(out.sessionComplete)
    out["dailyPressure"] = valid_net / valid_total
    for window in (5, 20):
        out[f"pressure{window}"] = valid_net.rolling(window, min_periods=window).sum() / valid_total.rolling(window, min_periods=window).sum()
    # An interior gap invalidates a continuous cumulative total; no offset or positivity clamp.
    out["contiguousSampledNetUsd"] = valid_net.cumsum(skipna=False)
    out["ticker"] = ticker
    return out.reset_index(), raw
