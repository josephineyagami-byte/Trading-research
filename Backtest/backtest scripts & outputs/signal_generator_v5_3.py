"""
Institutional Flow Signal Generator v5.3
========================================

v5.3 keeps v5.2's distribution-aware gate and separates the long and short
engines. The main fix is that short signals must pass hard confirmation filters
instead of being the negative side of a symmetric long score.

Design changes from v5.2:
  - Adds separate `long_score` and `short_score`.
  - Adds benchmark-relative strength context for short confirmation.
  - Formal short labels require price breakdown + raw distribution + high/rising
    short pressure + relative weakness.
  - Short failures degrade to `watch_short` or `absorption_watch`, not
    confirmed distribution.

Retained from v5.2:
  - Adds `distribution_context` so raw distribution can be classified as
    `bearish_distribution`, `supply_absorption`, `event_sell_the_news_watch`,
    `bearish_watch_distribution`, or `conflicted_distribution`.
  - Formal short labels require bearish distribution context, not just raw
    active sell pressure.
  - Strong/event stocks with price strength + raw sell pressure are routed to
    absorption/watch labels instead of confirmed shorts.
  - Adds `flow_net_current` and `flow_net_5` to make rolling-flow decisions
    easier to audit.

Retained from v5.1:
  - One unified model path. Main-flow availability is feature quality, not a
    ticker category.
  - Raw-flow regimes are explicit, so "less negative flow" is not mislabeled as
    confirmed accumulation.
  - Strong labels require actual directional flow confirmation.
  - Short volume and delayed darkpool data are merged as explainable context,
    with small score adjustments and larger confidence/risk effects.
  - Output keeps the legacy `signal` column for existing backtests, and adds
    `trade_signal`, `flow_regime`, `short_regime`, `darkpool_regime`,
    `data_quality`, `insight_label`, and PM-facing Chinese explanation columns.

Usage:
  US_STOCK_API_BASE_URL=http://74.208.124.247:8000 \
    python3 signal_generator_v5_3.py --ticker NVDA --interval 1d \
      --from-date 2025-08-01 --to-date 2026-08-09 --refresh-data
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime

import numpy as np
import pandas as pd

# The restored server is the current default for this project. Users can still
# override it with US_STOCK_API_BASE_URL before running the script.
os.environ.setdefault("US_STOCK_API_BASE_URL", "http://74.208.124.247:8000")

import signal_generator_v4 as v4
from inventory_diagnostics import DIAGNOSTIC_COLUMNS, add_inventory_diagnostics


OUTPUT_DIR = v4.OUTPUT_DIR
RAW_CACHE_DIR = os.path.join(os.path.dirname(__file__), "raw_data_cache")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(RAW_CACHE_DIR, exist_ok=True)


# Conservative priors, not fitted parameters. The final effective weights are
# recomputed per run after flow reliability is measured.
MAX_FLOW_WEIGHT = 0.35
SHORT_CONTEXT_WEIGHT = 0.08
DARKPOOL_CONTEXT_WEIGHT = 0.06
NON_FLOW_PRIOR = {
    "ofi": 0.45,
    "vwap": 0.35,
    "impact": 0.20,
}

SHORT_CONFIRMING_REGIMES = {
    "high_short_pressure",
    "high_and_rising_short_pressure",
}
SHORT_LOW_OR_EASING_REGIMES = {
    "low_short_pressure",
    "low_and_falling_short_pressure",
    "high_but_easing_short_pressure",
    "easing_short_pressure",
    "stable_short_pressure",
}
PRICE_HOLDING_REGIMES = {
    "bullish_price_confirmation",
    "short_term_pullback_inside_strong_trend",
    "short_term_rebound_inside_weak_trend",
    "mixed_price_action",
}
EVENT_DARKPOOL_REGIMES = {
    "elevated_delayed_darkpool_activity",
    "very_elevated_delayed_darkpool_activity",
}
RELATIVE_WEAK_REGIMES = {"relative_weakness"}
RELATIVE_SUPPORTIVE_REGIMES = {"relative_strength", "short_term_relative_pullback"}

BENCHMARK_BY_TICKER = {
    "AMD": "SMH",
    "INTC": "SMH",
    "NVDA": "SMH",
    "MU": "SMH",
    "TSM": "SMH",
    "SMH": "QQQ",
    "SOXX": "QQQ",
    "SOXL": "SMH",
    "SOXS": "SMH",
    "AAPL": "QQQ",
    "MSFT": "QQQ",
    "GOOGL": "QQQ",
    "META": "QQQ",
    "AMZN": "QQQ",
    "TSLA": "QQQ",
    "PLTR": "QQQ",
    "QQQ": "SPY",
    "SPY": "SPY",
    "XLK": "QQQ",
    "XLF": "SPY",
    "XLE": "SPY",
    "XLV": "SPY",
    "XLY": "SPY",
    "ABBV": "XLV",
}


def _soft_score(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def _norm_clip(s: pd.Series, window: int = 50) -> pd.Series:
    mu = s.rolling(window).mean()
    sd = s.rolling(window).std().replace(0, np.nan)
    return ((s - mu) / sd).clip(-1, 1).fillna(0)


def _safe_last_true_index(mask: pd.Series) -> int | None:
    if mask.empty or not bool(mask.any()):
        return None
    return int(np.flatnonzero(mask.to_numpy())[-1])


def merge_flow(df: pd.DataFrame, flow_df: pd.DataFrame) -> pd.DataFrame:
    """Merge main-flow while preserving missingness separately from true zero."""
    df = df.copy()
    flow_df = flow_df.copy()

    date_col = "date" if "date" in flow_df.columns else "hour"
    flow_sub = flow_df[[date_col, "inst_net", "xl_net", "l_net"]].copy()
    if date_col == "hour":
        flow_sub = flow_sub.rename(columns={"hour": "date"})

    if "hour" in flow_df.columns:
        df["date"] = df["datetime"].dt.floor("H")
    else:
        df["date"] = df["datetime"].dt.normalize()

    df = df.merge(flow_sub, on="date", how="left", validate="many_to_one")
    df["flow_present"] = df["inst_net"].notna()

    # Keep raw nullable flow for quality/scoring. Filled columns remain for
    # existing downstream inventory output compatibility.
    df["inst_net_raw"] = df["inst_net"]
    df["xl_net_raw"] = df["xl_net"]
    df["l_net_raw"] = df["l_net"]
    df[["inst_net", "xl_net", "l_net"]] = df[["inst_net", "xl_net", "l_net"]].fillna(0.0)

    present_inst = df["inst_net_raw"].where(df["flow_present"])
    inst_std = present_inst.rolling(20, min_periods=10).std().replace(0, np.nan)
    df["inst_net_z"] = present_inst / inst_std
    return df


def _benchmark_for(ticker: str) -> str | None:
    ticker = ticker.upper()
    bench = BENCHMARK_BY_TICKER.get(ticker)
    if not bench or bench == ticker:
        return None
    return bench


def merge_relative_strength(
    df: pd.DataFrame,
    ticker: str,
    interval: str,
    limit: int,
    from_date: str | None = None,
    to_date: str | None = None,
) -> pd.DataFrame:
    """Merge benchmark-relative returns for short confirmation.

    Relative weakness is only a hard short confirm when both 5-bar and 20-bar
    returns lag the benchmark. If the benchmark is missing, official shorts are
    blocked rather than inferred from single-name weakness alone.
    """
    df = df.copy()
    bench = _benchmark_for(ticker)
    df["benchmark_ticker"] = bench or ""
    df["rel_ret_5"] = np.nan
    df["rel_ret_20"] = np.nan
    df["relative_regime"] = "relative_unavailable"
    if not bench:
        df["benchmark_close"] = np.nan
        return df

    try:
        bench_df = v4.load_klines(bench, interval, limit, from_date=from_date, to_date=to_date)
    except v4.ResearchAPIError:
        raise
    except SystemExit:
        print(f"[WARN] benchmark klines unavailable for {ticker} vs {bench}")
        return df
    except Exception as exc:
        print(f"[WARN] benchmark klines failed for {ticker} vs {bench}: {exc}")
        return df

    if bench_df is None or bench_df.empty:
        print(f"[WARN] empty benchmark klines for {ticker} vs {bench}")
        return df

    bench_sub = bench_df[["datetime", "close"]].rename(columns={"close": "benchmark_close"})
    out = df.merge(bench_sub, on="datetime", how="left")
    ret5 = out["close"].pct_change(5)
    ret20 = out["close"].pct_change(20)
    bret5 = out["benchmark_close"].pct_change(5)
    bret20 = out["benchmark_close"].pct_change(20)
    out["rel_ret_5"] = ret5 - bret5
    out["rel_ret_20"] = ret20 - bret20

    rel = pd.Series("relative_unavailable", index=out.index, dtype=object)
    available = out["rel_ret_5"].notna() & out["rel_ret_20"].notna()
    weak = (out["rel_ret_5"] < -0.01) & (out["rel_ret_20"] < -0.02)
    strong = (out["rel_ret_5"] > 0.01) & (out["rel_ret_20"] > 0.02)
    pullback = (out["rel_ret_5"] < -0.01) & (out["rel_ret_20"] > 0.02)
    rebound = (out["rel_ret_5"] > 0.01) & (out["rel_ret_20"] < -0.02)
    rel.loc[available] = "relative_mixed"
    rel.loc[available & weak] = "relative_weakness"
    rel.loc[available & strong] = "relative_strength"
    rel.loc[available & pullback] = "short_term_relative_pullback"
    rel.loc[available & rebound] = "short_term_relative_rebound"
    out["relative_regime"] = rel
    return out


def _api_rows(path: str, params: dict) -> list[dict]:
    raw = v4.fetch(path, params)
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    for key in ("data", "rows", "bars", "trades"):
        arr = raw.get(key)
        if isinstance(arr, list):
            return arr
    return []


def _date_bounds(df: pd.DataFrame, from_date: str | None, to_date: str | None) -> tuple[str, str]:
    start = from_date or df["datetime"].min().date().isoformat()
    end = to_date or df["datetime"].max().date().isoformat()
    return start, end


def _empty_short_context(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["short_context_present"] = False
    df["short_date"] = pd.NaT
    df["short_data_lag_days"] = np.nan
    df["short_volume_ratio"] = np.nan
    df["short_volume_delta_10d"] = np.nan
    df["short_volume"] = np.nan
    df["short_total_volume"] = np.nan
    return df


def merge_short_volume(
    df: pd.DataFrame,
    ticker: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> pd.DataFrame:
    """Merge FINRA daily short-volume as confirmation/risk context."""
    start, end = _date_bounds(df, from_date, to_date)
    rows = _api_rows("/api/short-volume", {"ticker": ticker, "from": start, "to": end})
    if not rows:
        print(f"[WARN] No short-volume context for {ticker} {start}->{end}")
        return _empty_short_context(df)

    sv = pd.DataFrame(rows)
    if "date" not in sv.columns:
        print(f"[WARN] short-volume response missing date column for {ticker}")
        return _empty_short_context(df)

    sv["date"] = pd.to_datetime(sv["date"]).dt.normalize()
    sv["short_volume"] = pd.to_numeric(sv.get("short_volume"), errors="coerce")
    sv["short_total_volume"] = pd.to_numeric(sv.get("total_volume"), errors="coerce")
    if "short_ratio" in sv.columns:
        sv["short_volume_ratio"] = pd.to_numeric(sv["short_ratio"], errors="coerce")
    else:
        sv["short_volume_ratio"] = sv["short_volume"] / sv["short_total_volume"].replace(0, np.nan)

    sv = sv.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    prior10 = sv["short_volume_ratio"].shift(1).rolling(10, min_periods=3).mean()
    sv["short_volume_delta_10d"] = sv["short_volume_ratio"] - prior10

    out = df.copy()
    out["_date"] = out["datetime"].dt.normalize()
    out["_orig_order"] = np.arange(len(out))
    sv = sv.rename(columns={"date": "short_date"})
    out = pd.merge_asof(
        out.sort_values("_date"),
        sv[["short_date", "short_volume_ratio", "short_volume_delta_10d", "short_volume", "short_total_volume"]].sort_values("short_date"),
        left_on="_date",
        right_on="short_date",
        direction="backward",
    )
    out["short_data_lag_days"] = (out["_date"] - out["short_date"]).dt.days
    stale = out["short_data_lag_days"] > 10
    for col in ["short_volume_ratio", "short_volume_delta_10d", "short_volume", "short_total_volume"]:
        out.loc[stale, col] = np.nan
    out["short_context_present"] = out["short_volume_ratio"].notna() & ~stale
    out = out.sort_values("_orig_order").drop(columns=["_date", "_orig_order"]).reset_index(drop=True)
    print(
        f"[OK] short-volume context: {len(sv)} daily rows "
        f"[{sv['short_date'].min().date()} -> {sv['short_date'].max().date()}], "
        f"merged {int(out['short_context_present'].sum())}/{len(out)} bars"
    )
    return out


def _empty_darkpool_context(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["darkpool_context_present"] = False
    df["dark_4w_ratio"] = np.nan
    df["dark_ats_shares"] = np.nan
    df["dark_ats_trades"] = np.nan
    return df


def merge_darkpool_context(
    df: pd.DataFrame,
    ticker: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> pd.DataFrame:
    """Merge delayed weekly darkpool activity as background context only."""
    start, end = _date_bounds(df, from_date, to_date)
    try:
        days = max(180, min(900, (pd.to_datetime(end) - pd.to_datetime(start)).days + 90))
    except Exception:
        days = 365
    rows = _api_rows("/api/dark-pool/ticker", {"ticker": ticker, "days": days})
    if not rows:
        print(f"[WARN] No darkpool context for {ticker}")
        return _empty_darkpool_context(df)

    dp = pd.DataFrame(rows)
    required = {"week_start", "ats_shares", "ats_trades"}
    if not required.issubset(dp.columns):
        print(f"[WARN] darkpool response missing columns for {ticker}: {required - set(dp.columns)}")
        return _empty_darkpool_context(df)

    dp["week_start"] = pd.to_datetime(dp["week_start"]).dt.normalize()
    dp["dark_ats_shares"] = pd.to_numeric(dp["ats_shares"], errors="coerce")
    dp["dark_ats_trades"] = pd.to_numeric(dp["ats_trades"], errors="coerce")
    dp = dp.sort_values("week_start").drop_duplicates("week_start", keep="last").reset_index(drop=True)
    prior4 = dp["dark_ats_shares"].shift(1).rolling(4, min_periods=2).mean()
    dp["dark_4w_ratio"] = dp["dark_ats_shares"] / prior4.replace(0, np.nan)

    out = df.sort_values("datetime").reset_index(drop=True).copy()
    out = pd.merge_asof(
        out,
        dp[["week_start", "dark_4w_ratio", "dark_ats_shares", "dark_ats_trades"]],
        left_on="datetime",
        right_on="week_start",
        direction="backward",
    )
    out = out.drop(columns=["week_start"])
    out["darkpool_context_present"] = out["dark_4w_ratio"].notna()
    print(
        f"[OK] darkpool context: {len(dp)} weekly rows "
        f"[{dp['week_start'].min().date()} -> {dp['week_start'].max().date()}], "
        f"merged {int(out['darkpool_context_present'].sum())}/{len(out)} bars"
    )
    return out


def compute_flow_quality(df: pd.DataFrame) -> dict[str, float | str]:
    if "flow_present" not in df.columns:
        return {
            "flow_reliability": 0.0,
            "flow_coverage_full": 0.0,
            "flow_coverage_20": 0.0,
            "flow_coverage_60": 0.0,
            "flow_recency_score": 0.0,
            "flow_gap_bars": float("nan"),
            "flow_outlier_rate": 0.0,
            "data_quality": "no_flow",
        }

    present = df["flow_present"].fillna(False).astype(bool)
    full = float(present.mean()) if len(present) else 0.0
    cov20 = float(present.tail(20).mean()) if len(present) else 0.0
    cov60 = float(present.tail(min(60, len(present))).mean()) if len(present) else 0.0

    last_idx = _safe_last_true_index(present)
    if last_idx is None:
        gap_bars = float("inf")
        recency = 0.0
    else:
        gap_bars = len(df) - 1 - last_idx
        recency = float(np.clip(1.0 - gap_bars / 10.0, 0.0, 1.0))

    z = df.get("inst_net_z", pd.Series(dtype=float))
    outlier_rate = float((z.abs() > 6).mean()) if len(z) else 0.0

    reliability = (
        0.35 * _soft_score(cov20, 0.30, 0.85)
        + 0.30 * _soft_score(cov60, 0.30, 0.85)
        + 0.20 * _soft_score(full, 0.20, 0.80)
        + 0.15 * recency
    )
    reliability *= max(0.0, 1.0 - min(outlier_rate, 0.25) * 2.0)
    reliability = float(np.clip(reliability, 0.0, 1.0))

    if reliability >= 0.75:
        quality = "high"
    elif reliability >= 0.35:
        quality = "medium"
    elif full > 0:
        quality = "low"
    else:
        quality = "no_flow"

    return {
        "flow_reliability": reliability,
        "flow_coverage_full": full,
        "flow_coverage_20": cov20,
        "flow_coverage_60": cov60,
        "flow_recency_score": recency,
        "flow_gap_bars": float(gap_bars),
        "flow_outlier_rate": outlier_rate,
        "data_quality": quality,
    }


def _flow_direction_score(df: pd.DataFrame) -> pd.Series:
    if "flow_present" not in df.columns:
        return pd.Series(0.0, index=df.index)

    present_inst = df["inst_net_raw"].where(df["flow_present"])
    present_count_5 = df["flow_present"].rolling(5, min_periods=1).sum().replace(0, np.nan)
    roll_5 = present_inst.rolling(5, min_periods=2).sum()
    scale = present_inst.abs().rolling(60, min_periods=10).median()
    denom = (scale * present_count_5).replace(0, np.nan)
    return (roll_5 / denom).clip(-1, 1).fillna(0)


def _flow_regime(df: pd.DataFrame, relative_flow: pd.Series) -> pd.Series:
    if "flow_present" not in df.columns:
        return pd.Series("flow_unavailable", index=df.index)

    present_inst = df["inst_net_raw"].where(df["flow_present"])
    present_count_5 = df["flow_present"].rolling(5, min_periods=1).sum()
    roll_5 = present_inst.rolling(5, min_periods=2).sum()
    scale = present_inst.abs().rolling(60, min_periods=10).median()
    fallback_scale = present_inst.abs().expanding(min_periods=3).median()
    scale = scale.fillna(fallback_scale)
    threshold = scale * present_count_5.clip(lower=1) * 0.10
    threshold = threshold.where(present_count_5 >= 2, np.inf)
    rel = relative_flow.fillna(0)

    regime = pd.Series("flow_unavailable", index=df.index, dtype=object)
    stale_or_missing = ~df["flow_present"].fillna(False).astype(bool)
    regime.loc[stale_or_missing] = "flow_missing_bar"

    pos = roll_5 > threshold
    neg = roll_5 < -threshold
    rel_pos = rel > 0.20
    rel_neg = rel < -0.20

    regime.loc[pos & ~rel_neg] = "raw_accumulation_pressure"
    regime.loc[neg & ~rel_pos] = "raw_distribution_pressure"
    regime.loc[neg & rel_pos] = "selling_pressure_easing"
    regime.loc[pos & rel_neg] = "buying_pressure_fading"
    regime.loc[df["flow_present"].fillna(False) & ~(pos | neg)] = "balanced_flow"
    return regime


def _price_regime(df: pd.DataFrame) -> pd.Series:
    ret_5 = df["close"].pct_change(5)
    ret_20 = df["close"].pct_change(20)
    regime = pd.Series("price_data_incomplete", index=df.index, dtype=object)
    bullish = (ret_5 > 0) & (ret_20 > 0)
    bearish = (ret_5 < 0) & (ret_20 < 0)
    rebound = (ret_5 > 0) & (ret_20 < 0)
    pullback = (ret_5 < 0) & (ret_20 > 0)
    mixed = ret_5.notna() & ret_20.notna() & ~(bullish | bearish | rebound | pullback)
    regime.loc[bullish] = "bullish_price_confirmation"
    regime.loc[bearish] = "bearish_price_confirmation"
    regime.loc[rebound] = "short_term_rebound_inside_weak_trend"
    regime.loc[pullback] = "short_term_pullback_inside_strong_trend"
    regime.loc[mixed] = "mixed_price_action"
    return regime


def _short_regime_series(df: pd.DataFrame) -> pd.Series:
    if "short_volume_ratio" not in df.columns:
        return pd.Series("short_volume_missing", index=df.index)
    ratio = df["short_volume_ratio"]
    delta = df["short_volume_delta_10d"] if "short_volume_delta_10d" in df.columns else pd.Series(np.nan, index=df.index)
    regime = pd.Series("short_volume_missing", index=df.index, dtype=object)
    present = ratio.notna()
    high = ratio >= 0.55
    low = ratio <= 0.40
    rising = delta > 0.03
    falling = delta < -0.03

    regime.loc[present] = "stable_short_pressure"
    regime.loc[present & high] = "high_short_pressure"
    regime.loc[present & high & rising] = "high_and_rising_short_pressure"
    regime.loc[present & high & falling] = "high_but_easing_short_pressure"
    regime.loc[present & low] = "low_short_pressure"
    regime.loc[present & low & falling] = "low_and_falling_short_pressure"
    regime.loc[present & ~high & ~low & rising] = "rising_short_pressure"
    regime.loc[present & ~high & ~low & falling] = "easing_short_pressure"
    return regime


def _darkpool_regime_series(df: pd.DataFrame) -> pd.Series:
    if "dark_4w_ratio" not in df.columns:
        return pd.Series("darkpool_missing", index=df.index)
    ratio = df["dark_4w_ratio"]
    regime = pd.Series("darkpool_missing", index=df.index, dtype=object)
    present = ratio.notna()
    regime.loc[present] = "normal_delayed_darkpool_activity"
    regime.loc[present & (ratio >= 2.0)] = "very_elevated_delayed_darkpool_activity"
    regime.loc[present & (ratio >= 1.4) & (ratio < 2.0)] = "elevated_delayed_darkpool_activity"
    regime.loc[present & (ratio <= 0.6)] = "below_normal_delayed_darkpool_activity"
    return regime


def _short_context_score(short_regime: pd.Series, price_regime: pd.Series, flow_regime: pd.Series) -> pd.Series:
    scores = pd.Series(0.0, index=short_regime.index)
    bullish_price = price_regime.eq("bullish_price_confirmation")
    bearish_price = price_regime.eq("bearish_price_confirmation")
    bullish_flow = flow_regime.eq("raw_accumulation_pressure")
    bearish_flow = flow_regime.eq("raw_distribution_pressure")

    high_rising = short_regime.eq("high_and_rising_short_pressure")
    rising = short_regime.eq("rising_short_pressure")
    easing = short_regime.isin(["high_but_easing_short_pressure", "easing_short_pressure", "low_and_falling_short_pressure"])

    absorbed = high_rising & bullish_price & bullish_flow
    confirmed_pressure = high_rising & (bearish_price | bearish_flow)
    scores.loc[absorbed] = 0.04
    scores.loc[confirmed_pressure] = -SHORT_CONTEXT_WEIGHT
    scores.loc[high_rising & ~(absorbed | confirmed_pressure)] = -0.03
    scores.loc[rising & ~(bullish_price & bullish_flow)] = -0.04
    scores.loc[rising & bullish_price & bullish_flow] = 0.02
    scores.loc[easing & (bullish_price | bullish_flow)] = 0.03
    return scores.clip(-SHORT_CONTEXT_WEIGHT, SHORT_CONTEXT_WEIGHT)


def _darkpool_context_score(darkpool_regime: pd.Series, price_regime: pd.Series, flow_regime: pd.Series) -> pd.Series:
    scores = pd.Series(0.0, index=darkpool_regime.index)
    elevated = darkpool_regime.isin([
        "very_elevated_delayed_darkpool_activity",
        "elevated_delayed_darkpool_activity",
    ])
    bullish = price_regime.eq("bullish_price_confirmation") & flow_regime.eq("raw_accumulation_pressure")
    bearish = price_regime.eq("bearish_price_confirmation") & flow_regime.eq("raw_distribution_pressure")
    scores.loc[elevated & bullish] = DARKPOOL_CONTEXT_WEIGHT
    scores.loc[elevated & bearish] = -DARKPOOL_CONTEXT_WEIGHT
    return scores


def _distribution_context_series(
    price_regime: pd.Series,
    flow_regime: pd.Series,
    short_regime: pd.Series,
    darkpool_regime: pd.Series,
    relative_regime: pd.Series,
    score: pd.Series,
) -> pd.Series:
    """Separate true bearish distribution from supply absorption/event digestion."""
    context = pd.Series("not_distribution", index=flow_regime.index, dtype=object)
    raw_dist = flow_regime.eq("raw_distribution_pressure")
    if not bool(raw_dist.any()):
        return context

    price_bearish = price_regime.eq("bearish_price_confirmation")
    price_holding = price_regime.isin(PRICE_HOLDING_REGIMES)
    short_confirm = short_regime.isin(SHORT_CONFIRMING_REGIMES)
    short_low_or_easing = short_regime.isin(SHORT_LOW_OR_EASING_REGIMES)
    event_dark = darkpool_regime.isin(EVENT_DARKPOOL_REGIMES)
    relative_weak = relative_regime.isin(RELATIVE_WEAK_REGIMES)

    context.loc[raw_dist] = "conflicted_distribution"
    context.loc[raw_dist & price_holding & short_low_or_easing] = "supply_absorption"
    context.loc[raw_dist & price_holding & event_dark] = "event_sell_the_news_watch"
    context.loc[raw_dist & price_holding & short_confirm] = "bearish_watch_distribution"
    context.loc[raw_dist & price_bearish & ~(short_confirm & relative_weak)] = "bearish_watch_distribution"
    context.loc[raw_dist & price_bearish & short_confirm & relative_weak] = "bearish_distribution"
    return context


def _classify_signal(
    long_score: float,
    short_score: float,
    flow_regime: str,
    reliability: float,
    price_regime: str,
    distribution_context: str = "not_distribution",
) -> str:
    """Legacy-compatible signal with separated long/short gates."""
    bullish_flow = flow_regime == "raw_accumulation_pressure"
    price_bearish = price_regime == "bearish_price_confirmation"
    bearish_distribution = distribution_context == "bearish_distribution"
    allow_strong_long = reliability >= 0.35 and bullish_flow
    allow_strong_short = reliability >= 0.35 and bearish_distribution
    score_gap = 0.05

    if bearish_distribution and short_score >= 0.35 and short_score >= long_score + score_gap:
        return "strong_distribution" if allow_strong_short else "distribution"
    if bearish_distribution and short_score >= 0.10 and short_score >= long_score + score_gap:
        return "distribution"

    if bullish_flow and not price_bearish and long_score >= 0.35 and long_score >= short_score + score_gap:
        return "strong_accumulation" if allow_strong_long else "accumulation"
    if bullish_flow and not price_bearish and long_score >= 0.10 and long_score >= short_score + score_gap:
        return "accumulation"
    return "neutral"


def _trade_signal(
    signal: str,
    long_score: float,
    short_score: float,
    flow_regime: str,
    price_regime: str,
    distribution_context: str = "not_distribution",
) -> str:
    if signal in ("accumulation", "strong_accumulation"):
        return "long"
    if signal in ("distribution", "strong_distribution"):
        return "short"
    if short_score > 0.10 and distribution_context == "supply_absorption":
        return "absorption_watch"
    if short_score > 0.10 and distribution_context in (
        "event_sell_the_news_watch",
        "bearish_watch_distribution",
        "conflicted_distribution",
    ):
        return "watch_short"
    if long_score > 0.35 and long_score >= short_score:
        return "watch_long"
    if long_score > 0.10 and flow_regime == "raw_accumulation_pressure" and price_regime == "bearish_price_confirmation":
        return "watch_long"
    if short_score > 0.35 and short_score > long_score:
        return "watch_short"
    if short_score > 0.10 and flow_regime == "raw_distribution_pressure" and price_regime == "bullish_price_confirmation":
        return "watch_short"
    return "neutral"


def _insight_label(
    signal: str,
    trade_signal: str,
    flow_regime: str,
    short_regime: str,
    darkpool_regime: str,
    distribution_context: str,
    quality: str,
) -> str:
    if trade_signal == "absorption_watch":
        return "supply_absorption_watch"
    if trade_signal == "watch_long":
        if flow_regime == "selling_pressure_easing":
            return "bullish_watch_selling_pressure_easing"
        return "bullish_watch_flow_not_confirmed"
    if trade_signal == "watch_short":
        if distribution_context == "event_sell_the_news_watch":
            return "event_sell_the_news_watch"
        if distribution_context == "bearish_watch_distribution":
            return "bearish_distribution_watch"
        if flow_regime == "buying_pressure_fading":
            return "bearish_watch_buying_pressure_fading"
        return "bearish_watch_flow_not_confirmed"
    if short_regime == "high_and_rising_short_pressure" and signal in ("accumulation", "strong_accumulation"):
        return "squeeze_or_absorption_watch"
    if darkpool_regime in ("elevated_delayed_darkpool_activity", "very_elevated_delayed_darkpool_activity"):
        if flow_regime == "raw_accumulation_pressure" and signal in ("accumulation", "strong_accumulation"):
            return "delayed_darkpool_accumulation_context"
        if flow_regime == "raw_distribution_pressure" and signal in ("distribution", "strong_distribution"):
            return "delayed_darkpool_distribution_context"
    if flow_regime == "raw_accumulation_pressure" and signal in ("accumulation", "strong_accumulation"):
        return "confirmed_accumulation"
    if flow_regime == "raw_distribution_pressure" and signal in ("distribution", "strong_distribution"):
        return "confirmed_distribution"
    if quality in ("low", "no_flow"):
        return "price_based_low_flow_quality"
    if signal == "neutral":
        return "neutral_or_conflicted"
    return "price_flow_mixed"


def _build_explanation(row: pd.Series) -> tuple[str, str, str]:
    signal = str(row.get("signal", "neutral"))
    trade_signal = str(row.get("trade_signal", "neutral"))
    flow_regime = str(row.get("flow_regime", "flow_unavailable"))
    price_regime = str(row.get("price_regime", "price_data_incomplete"))
    short_regime = str(row.get("short_regime", "short_volume_missing"))
    darkpool_regime = str(row.get("darkpool_regime", "darkpool_missing"))
    distribution_context = str(row.get("distribution_context", "not_distribution"))
    relative_regime = str(row.get("relative_regime", "relative_unavailable"))
    quality = str(row.get("data_quality", "no_flow"))

    if trade_signal == "long":
        lead = "偏多信号"
    elif trade_signal == "short":
        lead = "偏空信号"
    elif trade_signal == "watch_long":
        lead = "偏多观察信号"
    elif trade_signal == "watch_short":
        lead = "偏空观察信号"
    elif trade_signal == "absorption_watch":
        lead = "供给吸收观察信号"
    else:
        lead = "中性/冲突信号"

    why = (
        f"{lead}: price={price_regime}, flow={flow_regime}, "
        f"distribution_context={distribution_context}, "
        f"short={short_regime}, relative={relative_regime}, darkpool={darkpool_regime}, "
        f"flow_quality={quality}, score={float(row.get('final_score', 0)):+.3f}."
    )

    risks = []
    if quality in ("low", "no_flow"):
        risks.append("mainflow/trades 覆盖不足，信号主要来自价格和 OHLCV")
    if flow_regime == "raw_distribution_pressure" and trade_signal in ("long", "watch_long"):
        risks.append("raw flow 仍是净流出，不能当 confirmed accumulation")
    if flow_regime == "raw_accumulation_pressure" and trade_signal in ("short", "watch_short"):
        risks.append("raw flow 仍是净流入，空头信号需要等待 flow 转弱")
    if distribution_context in ("supply_absorption", "event_sell_the_news_watch"):
        risks.append("raw distribution 可能是供给吸收/事件消化，价格未转弱前不能当 confirmed short")
    if distribution_context == "bearish_watch_distribution":
        risks.append("存在卖压但 short 条件未完全确认，先按 watch 而不是正式 short")
    if trade_signal in ("short", "watch_short") and relative_regime not in RELATIVE_WEAK_REGIMES:
        risks.append("缺少相对板块走弱确认，不能提高空头 conviction")
    if short_regime == "short_volume_missing":
        risks.append("缺少 short_volume，无法确认 short pressure/squeeze")
    if darkpool_regime == "darkpool_missing":
        risks.append("缺少 darkpool 背景")
    if darkpool_regime in ("elevated_delayed_darkpool_activity", "very_elevated_delayed_darkpool_activity"):
        risks.append("darkpool 有 2-3 周发布延迟，只能作为背景，不能当即时择时")
    risk = "；".join(risks) if risks else "主要风险是后续 price/flow 不能延续同向确认"

    if trade_signal == "long":
        next_check = "下一步看 raw flow 是否维持净流入、价格是否守住 5/20 bar 趋势；若 short pressure 高但价格不跌，可升级为 squeeze/absorption watch。"
    elif trade_signal == "watch_long":
        next_check = "下一步先等 raw flow 从净流出/卖压缓和转为净流入；确认前只作为 bullish watch，不作为正式 long candidate。"
    elif trade_signal == "short":
        next_check = "下一步看 raw flow 是否继续净流出、价格是否维持弱势，并确认相对板块继续走弱；若 short pressure 同时上升，空头 conviction 才能提高。"
    elif trade_signal == "watch_short":
        next_check = "下一步先等价格转弱或 short pressure 上升；确认前只作为 bearish watch，不作为正式 short candidate。"
    elif trade_signal == "absorption_watch":
        next_check = "下一步看卖压是否被价格继续吸收；若 raw flow 转正且价格守住趋势，可升级为 long，若价格跌破趋势且 short pressure 上升才转 short。"
    else:
        next_check = "下一步等 price、raw flow、short volume 至少两个方向一致后再升级为 long/short candidate。"

    if signal.startswith("strong_") and quality in ("low", "no_flow"):
        risk = f"{risk}；当前不应给 strong label"
    return why, risk, next_check


def _institutional_holding_read(row: pd.Series) -> tuple[str, str, str]:
    """PM-facing interpretation of institutional flow as a holding proxy.

    This is not 13F ownership data. It translates short-horizon trade/main-flow
    evidence into a holding-bias read that a portfolio manager can act on.
    """
    signal = str(row.get("signal", "neutral"))
    trade_signal = str(row.get("trade_signal", "neutral"))
    flow_regime = str(row.get("flow_regime", "flow_unavailable"))
    price_regime = str(row.get("price_regime", "price_data_incomplete"))
    short_regime = str(row.get("short_regime", "short_volume_missing"))
    distribution_context = str(row.get("distribution_context", "not_distribution"))
    relative_regime = str(row.get("relative_regime", "relative_unavailable"))
    quality = str(row.get("data_quality", "no_flow"))

    if quality in ("low", "no_flow") or flow_regime in ("flow_unavailable", "flow_missing_bar"):
        return (
            "insufficient_flow_evidence",
            "机构持仓解读不足：mainflow/trades 覆盖不够，不能判断机构是在加仓还是减仓。",
            "PM 动作：不基于该 ticker 的 flow 做仓位调整，先补数据或只作为价格技术信号参考。",
        )

    if trade_signal == "long" and signal in ("accumulation", "strong_accumulation"):
        return (
            "institutional_accumulation",
            "机构持仓倾向：trades/mainflow 显示机构级资金净流入，且价格结构未明显反向，短中期更像加仓/回补/重新建仓。",
            "PM 动作：可列入做多或加仓候选；优先等待 flow 连续性、价格守住 5/20 bar 趋势后提高仓位。",
        )

    if trade_signal == "short":
        return (
            "institutional_distribution_reduction_risk",
            "机构持仓倾向：raw distribution、价格转弱、short pressure 和相对板块走弱同时确认，存在机构减仓/派发风险。",
            "PM 动作：可列入减仓/做空候选；需要设置止损，并持续确认相对板块弱势没有修复。",
        )

    if trade_signal == "absorption_watch":
        return (
            "supply_absorption_no_short",
            "机构持仓倾向：虽然 tape 上有大额主动卖压，但价格仍能承接，当前更像供给吸收/换手/事件消化，不足以判定机构系统性减仓。",
            "PM 动作：不要因为 raw distribution 直接做空；观察后续 flow 是否转正，若价格继续守住趋势，可转为做多候选。",
        )

    if trade_signal == "watch_short":
        if distribution_context == "event_sell_the_news_watch":
            return (
                "event_distribution_watch",
                "机构持仓倾向：事件落地后出现大额卖压，可能是获利了结、换手或风险再定价；但价格/short pressure 尚未确认正式减仓趋势。",
                "PM 动作：降低追多意愿，保留风险警戒；只有价格跌破趋势且 short pressure 上升时才升级为空头候选。",
            )
        return (
            "institutional_distribution_watch",
            "机构持仓倾向：出现机构级卖压观察信号，但缺少价格破坏或 short pressure 确认，暂不能定性为 confirmed distribution。",
            "PM 动作：不追多，跟踪价格是否转弱、short volume 是否升高；确认前只作为减仓风险提示。",
        )

    if trade_signal == "watch_long":
        return (
            "institutional_accumulation_watch",
            "机构持仓倾向：价格或部分 context 偏多，但 raw flow 尚未完全确认加仓，属于潜在加仓观察而非 confirmed accumulation。",
            "PM 动作：可放入观察池；等 raw flow 转为持续净流入后再升级为加仓候选。",
        )

    if flow_regime == "raw_distribution_pressure" and distribution_context in (
        "supply_absorption",
        "event_sell_the_news_watch",
    ):
        return (
            "distribution_absorbed_neutral",
            "机构持仓倾向：有卖压但被价格承接，当前更像换手/供给消化，不能直接解读为机构减仓。",
            "PM 动作：维持观察，不把它作为空头信号；等 flow 和价格方向一致后再行动。",
        )

    return (
        "neutral_or_mixed_institutional_read",
        f"机构持仓倾向：price={price_regime}, flow={flow_regime}, short={short_regime}, relative={relative_regime} 信息不一致，暂无明确加仓/减仓结论。",
        "PM 动作：维持观察；等待 price、mainflow、short volume 至少两项同向确认。",
    )


def compute_signal(df: pd.DataFrame, ticker: str = None) -> pd.DataFrame:
    df = df.copy()

    s_ofi = _norm_clip(df["ofi_z"])
    s_vwap = _norm_clip(df["vwap_dev"])
    s_impact = -_norm_clip(df["impact_eff_z"])

    quality = compute_flow_quality(df)
    flow_reliability = float(quality["flow_reliability"])
    relative_flow = _norm_clip(df["inst_net_z"]) if "inst_net_z" in df.columns else pd.Series(0.0, index=df.index)
    raw_flow = _flow_direction_score(df)
    s_flow = (0.75 * raw_flow + 0.25 * relative_flow).clip(-1, 1).fillna(0)

    flow_weight = MAX_FLOW_WEIGHT * flow_reliability
    non_flow_total = 1.0 - flow_weight
    weights = {
        "flow": flow_weight,
        "ofi": non_flow_total * NON_FLOW_PRIOR["ofi"],
        "vwap": non_flow_total * NON_FLOW_PRIOR["vwap"],
        "impact": non_flow_total * NON_FLOW_PRIOR["impact"],
    }

    rvol_raw = df["rvol"].clip(0, 5).fillna(1.0)
    rvol_boost = ((rvol_raw - 1.0) * v4.RVOL_BOOST_SCALE).clip(
        -v4.RVOL_BOOST_CLIP, v4.RVOL_BOOST_CLIP
    )

    base_score = (
        weights["flow"] * s_flow
        + weights["ofi"] * s_ofi
        + weights["vwap"] * s_vwap
        + weights["impact"] * s_impact
    )
    df["base_score"] = (base_score * (1.0 + rvol_boost)).clip(-1, 1)
    df["long_base_score"] = (
        weights["flow"] * s_flow.clip(lower=0)
        + weights["ofi"] * s_ofi.clip(lower=0)
        + weights["vwap"] * s_vwap.clip(lower=0)
        + weights["impact"] * s_impact.clip(lower=0)
    ).mul(1.0 + rvol_boost).clip(0, 1)
    df["short_base_score"] = (
        weights["flow"] * (-s_flow).clip(lower=0)
        + weights["ofi"] * (-s_ofi).clip(lower=0)
        + weights["vwap"] * (-s_vwap).clip(lower=0)
        + weights["impact"] * (-s_impact).clip(lower=0)
    ).mul(1.0 + rvol_boost).clip(0, 1)

    direction_sign = df["hmm_label"].map({"accumulation": 1, "distribution": -1, "neutral": 0}).fillna(0)
    hmm_strength = df["hmm_strength"] if "hmm_strength" in df.columns else pd.Series(0.0, index=df.index)
    df["hmm_boost"] = direction_sign * hmm_strength * 0.10

    df["flow_score_raw"] = raw_flow
    df["flow_score_relative"] = relative_flow
    df["flow_score"] = s_flow
    if "inst_net_raw" in df.columns and "flow_present" in df.columns:
        present_inst = df["inst_net_raw"].where(df["flow_present"])
        df["flow_net_current"] = present_inst
        df["flow_net_5"] = present_inst.rolling(5, min_periods=2).sum()
    else:
        df["flow_net_current"] = np.nan
        df["flow_net_5"] = np.nan
    df["flow_regime"] = _flow_regime(df, relative_flow)
    df["price_regime"] = _price_regime(df)
    if "relative_regime" not in df.columns:
        df["relative_regime"] = "relative_unavailable"
    df["short_regime"] = _short_regime_series(df)
    df["darkpool_regime"] = _darkpool_regime_series(df)
    df["short_context_score"] = _short_context_score(df["short_regime"], df["price_regime"], df["flow_regime"])
    df["darkpool_context_score"] = _darkpool_context_score(df["darkpool_regime"], df["price_regime"], df["flow_regime"])
    df["context_score"] = (df["short_context_score"] + df["darkpool_context_score"]).clip(
        -(SHORT_CONTEXT_WEIGHT + DARKPOOL_CONTEXT_WEIGHT),
        SHORT_CONTEXT_WEIGHT + DARKPOOL_CONTEXT_WEIGHT,
    )
    df["raw_score"] = (df["base_score"] + df["context_score"]).clip(-1, 1)
    df["signed_score_pre_hmm"] = df["raw_score"]
    df["long_score_raw"] = (df["long_base_score"] + df["context_score"].clip(lower=0)).clip(0, 1)
    df["short_score_raw"] = (df["short_base_score"] + (-df["context_score"]).clip(lower=0)).clip(0, 1)
    df["long_score"] = (df["long_score_raw"] + df["hmm_boost"].clip(lower=0)).clip(0, 1)
    df["short_score"] = (df["short_score_raw"] + (-df["hmm_boost"]).clip(lower=0)).clip(0, 1)
    df["final_score"] = (df["long_score"] - df["short_score"]).clip(-1, 1)
    df["distribution_context"] = _distribution_context_series(
        df["price_regime"],
        df["flow_regime"],
        df["short_regime"],
        df["darkpool_regime"],
        df["relative_regime"],
        df["short_score"],
    )

    df["flow_reliability"] = flow_reliability
    df["flow_weight"] = flow_weight
    df["data_quality"] = str(quality["data_quality"])
    df["flow_coverage_full"] = float(quality["flow_coverage_full"])
    df["flow_coverage_20"] = float(quality["flow_coverage_20"])
    df["flow_coverage_60"] = float(quality["flow_coverage_60"])
    df["flow_gap_bars"] = float(quality["flow_gap_bars"])

    df["signal"] = [
        _classify_signal(float(long_score), float(short_score), str(flow), flow_reliability, str(price), str(dist))
        for long_score, short_score, flow, price, dist in zip(
            df["long_score"],
            df["short_score"],
            df["flow_regime"],
            df["price_regime"],
            df["distribution_context"],
        )
    ]
    df["trade_signal"] = [
        _trade_signal(str(sig), float(long_score), float(short_score), str(flow), str(price), str(dist))
        for sig, long_score, short_score, flow, price, dist in zip(
            df["signal"],
            df["long_score"],
            df["short_score"],
            df["flow_regime"],
            df["price_regime"],
            df["distribution_context"],
        )
    ]
    df["insight_label"] = [
        _insight_label(str(sig), str(trade), str(flow), str(short), str(dark), str(dist), str(quality["data_quality"]))
        for sig, trade, flow, short, dark, dist in zip(
            df["signal"],
            df["trade_signal"],
            df["flow_regime"],
            df["short_regime"],
            df["darkpool_regime"],
            df["distribution_context"],
        )
    ]

    # Confidence is still a calibrated rule score, not a predicted probability.
    selected_strength = pd.Series(np.maximum(df["long_score"], df["short_score"]), index=df.index)
    selected_strength = selected_strength.where(
        ~df["trade_signal"].isin(["long", "watch_long"]),
        df["long_score"],
    )
    selected_strength = selected_strength.where(
        ~df["trade_signal"].isin(["short", "watch_short", "absorption_watch"]),
        df["short_score"],
    )
    df["raw_confidence"] = (selected_strength * 100).round(1)
    conflict = (
        ((df["long_score"] > 0.10) & df["flow_regime"].isin(["raw_distribution_pressure"]))
        | ((df["short_score"] > 0.10) & df["flow_regime"].isin(["raw_accumulation_pressure"]))
    )
    missing_short = df["short_regime"].eq("short_volume_missing")
    missing_dark = df["darkpool_regime"].eq("darkpool_missing")
    non_bearish_distribution = df["distribution_context"].isin([
        "supply_absorption",
        "event_sell_the_news_watch",
        "bearish_watch_distribution",
        "conflicted_distribution",
    ])
    context_multiplier = 1.0 - missing_short.astype(float) * 0.08 - missing_dark.astype(float) * 0.04
    quality_multiplier = 0.60 + 0.40 * flow_reliability
    confidence = df["raw_confidence"] * quality_multiplier * context_multiplier
    confidence = confidence.where(~conflict, confidence * 0.50)
    confidence = confidence.where(~non_bearish_distribution, confidence * 0.80)
    if quality["data_quality"] == "no_flow":
        confidence = confidence.clip(upper=35.0)
    elif quality["data_quality"] == "low":
        confidence = confidence.clip(upper=45.0)
    confidence = confidence.where(~conflict, confidence.clip(upper=35.0))
    row_cap = pd.Series(100.0, index=df.index)
    row_cap = row_cap.where(~df["flow_regime"].eq("flow_missing_bar"), 35.0)
    row_cap = row_cap.where(~df["trade_signal"].isin(["watch_long", "watch_short", "absorption_watch"]), 45.0)
    row_cap = row_cap.where(~non_bearish_distribution, 40.0)
    row_cap = row_cap.where(~df["short_regime"].eq("short_volume_missing"), 40.0)
    confidence = np.minimum(confidence, row_cap)
    df["confidence"] = confidence.round(1)

    explanations = df.apply(_build_explanation, axis=1)
    df["why_signal_cn"] = [x[0] for x in explanations]
    df["risk_cn"] = [x[1] for x in explanations]
    df["next_check_cn"] = [x[2] for x in explanations]

    institutional_reads = df.apply(_institutional_holding_read, axis=1)
    df["institutional_holding_signal"] = [x[0] for x in institutional_reads]
    df["institutional_holding_read_cn"] = [x[1] for x in institutional_reads]
    df["pm_action_cn"] = [x[2] for x in institutional_reads]

    direction = np.where(df["trade_signal"] == "long", 1, np.where(df["trade_signal"] == "short", -1, 0))
    df["est_inst_participation"] = (
        (df["rvol"].clip(0, 3) / 3 * 0.5 + (-df["impact_eff_z"]).clip(0, 2) / 2 * 0.3 + s_ofi.abs() * 0.2)
        * 25
    ).clip(0, 25).round(2)
    df["delta_inventory"] = direction * df["est_inst_participation"] / 100 * df["volume"]
    df["cumulative_inventory"] = df["delta_inventory"].cumsum()
    df = add_inventory_diagnostics(df)

    print("[v5.3] Split long/short scoring; formal shorts require relative-weakness confirmation")
    print(
        "[v5.3] Flow quality: "
        f"reliability={flow_reliability:.2f}, "
        f"full={quality['flow_coverage_full']:.1%}, "
        f"20bar={quality['flow_coverage_20']:.1%}, "
        f"60bar={quality['flow_coverage_60']:.1%}, "
        f"quality={quality['data_quality']}"
    )
    print(
        "[v5.3] Effective weights: "
        + " | ".join(f"{k}={v:.2f}" for k, v in weights.items() if v > 0)
    )
    print(
        "[v5.3] Context coverage: "
        f"short={1.0 - missing_short.mean():.1%}, "
        f"darkpool={1.0 - missing_dark.mean():.1%}"
    )
    return df


def _merged_cache_path(ticker: str, interval: str, from_date, to_date) -> str:
    safe_from = from_date or "2025-07-01"
    safe_to = to_date or "latest"
    return os.path.join(RAW_CACHE_DIR, f"{ticker}_{interval}_{safe_from}_{safe_to}_v5_3.csv")


def load_merged_cached(
    ticker,
    interval,
    limit,
    from_date=None,
    to_date=None,
    use_cache=True,
    refresh=False,
    include_context=True,
):
    cache_file = _merged_cache_path(ticker, interval, from_date, to_date)
    if use_cache and not refresh and os.path.exists(cache_file):
        print(f"[CACHE HIT] {ticker} {interval}: {cache_file}")
        df = pd.read_csv(cache_file, parse_dates=["datetime"])
        has_flow = "flow_present" in df.columns and bool(df["flow_present"].any())
        return df, has_flow

    kl = v4.load_klines(ticker, interval, limit, from_date=from_date, to_date=to_date)
    if kl is None or len(kl) < 50:
        return None, False

    fl = v4.load_main_flow(ticker, interval, limit, from_date=from_date, to_date=to_date)
    df = v4.compute_features(kl)
    df = merge_relative_strength(df, ticker, interval, limit, from_date=from_date, to_date=to_date)
    has_flow = fl is not None
    if has_flow:
        df = merge_flow(df, fl)
    else:
        df["flow_present"] = False

    if include_context:
        df = merge_short_volume(df, ticker, from_date=from_date, to_date=to_date)
        df = merge_darkpool_context(df, ticker, from_date=from_date, to_date=to_date)
    else:
        df = _empty_short_context(df)
        df = _empty_darkpool_context(df)

    if use_cache:
        df.to_csv(cache_file, index=False)
        print(f"[CACHED] {ticker} {interval} -> {cache_file}")
    return df, has_flow


def save_output(df: pd.DataFrame, ticker: str, interval: str) -> str:
    cols = [
        "datetime", "timestamp",
        "open", "high", "low", "close", "volume",
        "vwap_roll", "vwap_dev",
        "ofi_z", "rvol", "impact_eff_z",
        "bvc_buy_frac",
        "hmm_state", "hmm_label",
        "base_score", "long_base_score", "short_base_score",
        "context_score", "short_context_score", "darkpool_context_score",
        "raw_score", "signed_score_pre_hmm", "hmm_boost", "final_score",
        "long_score_raw", "short_score_raw", "long_score", "short_score",
        "signal", "trade_signal", "price_regime", "flow_regime", "short_regime",
        "darkpool_regime", "distribution_context", "relative_regime",
        "benchmark_ticker", "benchmark_close", "rel_ret_5", "rel_ret_20",
        "data_quality", "insight_label",
        "confidence", "raw_confidence",
        "flow_reliability", "flow_weight", "flow_coverage_full",
        "flow_coverage_20", "flow_coverage_60", "flow_gap_bars",
        "flow_score", "flow_score_raw", "flow_score_relative", "flow_net_current", "flow_net_5",
        "short_date", "short_data_lag_days", "short_volume_ratio", "short_volume_delta_10d",
        "dark_4w_ratio", "dark_ats_shares", "dark_ats_trades",
        "est_inst_participation", "delta_inventory", "cumulative_inventory",
        "flow_present", "inst_net", "inst_net_raw", "xl_net", "l_net", "inst_net_z",
        "short_context_present", "darkpool_context_present",
        "institutional_holding_signal", "institutional_holding_read_cn", "pm_action_cn",
        "why_signal_cn", "risk_cn", "next_check_cn",
    ]
    cols += DIAGNOSTIC_COLUMNS
    out = df[[c for c in cols if c in df.columns]].copy().dropna(subset=["signal"])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{ticker}_{interval}_{ts}_v5_3_signals.csv"
    fpath = os.path.join(OUTPUT_DIR, fname)
    out.to_csv(fpath, index=False)
    return fpath


def print_summary(df: pd.DataFrame, ticker: str, interval: str):
    valid = df.dropna(subset=["signal"])
    counts = valid["signal"].value_counts()
    last = valid.iloc[-1]

    print(f"\n{'='*55}")
    print(f"  {ticker} | {interval} | {len(valid)} bars [v5.3]")
    print(f"{'='*55}")
    print("\n[Signal Distribution]")
    for sig, cnt in counts.items():
        print(f"  {sig:<25} {cnt:>4} bars  {cnt / len(valid) * 100:5.1f}%")
    if "trade_signal" in valid.columns:
        print("\n[Trade Signal Distribution]")
        for sig, cnt in valid["trade_signal"].value_counts().items():
            print(f"  {sig:<25} {cnt:>4} bars  {cnt / len(valid) * 100:5.1f}%")

    print("\n[Latest]")
    print(f"  Time          : {last['datetime']}")
    print(f"  Close         : ${last['close']:.2f}")
    print(f"  Signal        : {last['signal']}")
    print(f"  Trade signal  : {last['trade_signal']}")
    print(f"  Price regime  : {last['price_regime']}")
    print(f"  Flow regime   : {last['flow_regime']}")
    print(f"  Short regime  : {last['short_regime']}")
    print(f"  Darkpool      : {last['darkpool_regime']}")
    if "distribution_context" in last.index:
        print(f"  Distribution : {last['distribution_context']}")
    if "relative_regime" in last.index:
        print(f"  Relative      : {last['relative_regime']} vs {last.get('benchmark_ticker', '')}")
    print(f"  Insight label : {last['insight_label']}")
    print(f"  Confidence    : {last['confidence']:.1f}%")
    print(f"  Final Score   : {last['final_score']:+.3f}")
    if "long_score" in last.index and "short_score" in last.index:
        print(f"  Long/Short    : {last['long_score']:.3f} / {last['short_score']:.3f}")
    print(f"  Flow Quality  : {last['data_quality']} (reliability={last['flow_reliability']:.2f})")
    print(f"  Why           : {last['why_signal_cn']}")
    if "institutional_holding_read_cn" in last.index:
        print(f"  Inst holding  : {last['institutional_holding_read_cn']}")
    if "pm_action_cn" in last.index:
        print(f"  PM action     : {last['pm_action_cn']}")
    print(f"  Risk          : {last['risk_cn']}")
    print(f"  Next check    : {last['next_check_cn']}")
    print(f"{'='*55}\n")


def fit_hmm_safe(df: pd.DataFrame, n_states: int, train_end: str | None = None) -> pd.DataFrame:
    """Use v4 HMM when stable; fall back to neutral labels on bad state fits."""
    try:
        return v4.fit_hmm(df, n_states=n_states, train_end=train_end)
    except Exception as exc:
        print(f"[HMM] [WARN] HMM failed ({type(exc).__name__}: {exc}); using neutral fallback.")
        out = df.copy()
        out["hmm_state"] = -1
        out["hmm_label"] = "neutral"
        out["hmm_strength"] = 0.0
        return out


def main():
    parser = argparse.ArgumentParser(description="Institutional Flow Signal Generator v5.3")
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--limit", default=300, type=int)
    parser.add_argument("--hmm-states", default=3, type=int)
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--to-date", default=None)
    parser.add_argument("--train-end", default=None)
    parser.add_argument("--refresh-data", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--no-context", action="store_true", help="Skip short-volume and darkpool context fetches")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    interval = args.interval
    mode = "OOS" if args.train_end else "FULL"
    print(f"\n[START] {ticker} | {interval} | v5.3 ({mode}) | split long/short + relative short gate")
    print("-" * 50)

    df, _ = load_merged_cached(
        ticker,
        interval,
        args.limit,
        from_date=args.from_date,
        to_date=args.to_date,
        use_cache=not args.no_cache,
        refresh=args.refresh_data,
        include_context=not args.no_context,
    )
    _ = v4.load_large_trades(ticker, limit=200)
    if df is None:
        print(f"[FATAL] Could not load data for {ticker}")
        return None

    print("[Training HMM (fixed 3 states)...]")
    df = fit_hmm_safe(df, n_states=args.hmm_states, train_end=args.train_end)
    print("[Scoring signals (v5.3 split long/short context weights)...]")
    df = compute_signal(df, ticker=ticker)
    fpath = save_output(df, ticker, interval)
    print_summary(df, ticker, interval)
    print(f"[SAVED] {fpath}\n")
    return fpath


if __name__ == "__main__":
    main()
