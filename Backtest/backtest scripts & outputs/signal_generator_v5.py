"""
Institutional Flow Signal Generator v5
======================================

v5 keeps v4's data loaders, OHLCV features, and HMM implementation, but
replaces the scoring layer.

Design changes from v4:
  - One unified model path. Main-flow availability is feature quality, not a
    ticker category.
  - Missing flow is preserved with `flow_present`; it is not silently converted
    into a real zero before reliability is computed.
  - Flow weight is softly gated by recent/full coverage and recency.
  - Flow score blends raw signed flow direction with relative flow improvement,
    so "less negative flow" does not automatically become "accumulation".
  - Output keeps the legacy `signal` column for existing backtests, and adds
    `trade_signal`, `flow_regime`, `data_quality`, and `insight_label`.

Usage:
  US_STOCK_API_BASE_URL=http://74.208.124.247:8000 \
    python3 signal_generator_v5.py --ticker NVDA --interval 1d \
      --from-date 2025-08-01 --to-date 2026-08-09 --refresh-data
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime

import numpy as np
import pandas as pd

import signal_generator_v4 as v4


OUTPUT_DIR = v4.OUTPUT_DIR
RAW_CACHE_DIR = os.path.join(os.path.dirname(__file__), "raw_data_cache")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(RAW_CACHE_DIR, exist_ok=True)


# Conservative priors, not fitted parameters. The final effective weights are
# recomputed per run after flow reliability is measured.
MAX_FLOW_WEIGHT = 0.35
NON_FLOW_PRIOR = {
    "ofi": 0.45,
    "vwap": 0.35,
    "impact": 0.20,
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

    df = df.merge(flow_sub, on="date", how="left")
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
    threshold = (scale * present_count_5.clip(lower=1) * 0.10).fillna(0)

    regime = pd.Series("flow_unavailable", index=df.index, dtype=object)
    stale_or_missing = ~df["flow_present"].fillna(False).astype(bool)
    regime.loc[stale_or_missing] = "flow_missing_bar"

    pos = roll_5 > threshold
    neg = roll_5 < -threshold
    rel_pos = relative_flow > 0.20
    rel_neg = relative_flow < -0.20

    regime.loc[pos & rel_pos] = "true_accumulation"
    regime.loc[pos & rel_neg] = "buying_pressure_fading"
    regime.loc[neg & rel_neg] = "true_distribution"
    regime.loc[neg & rel_pos] = "selling_pressure_easing"
    regime.loc[df["flow_present"].fillna(False) & ~(pos | neg)] = "balanced_flow"
    return regime


def _classify_signal(score: float, flow_regime: str, reliability: float) -> str:
    """Legacy-compatible signal with flow sanity gates."""
    allow_strong = reliability >= 0.35
    if score > 0.35:
        if reliability >= 0.30 and flow_regime == "true_distribution":
            return "neutral"
        if reliability >= 0.30 and flow_regime == "selling_pressure_easing":
            return "accumulation"
        return "strong_accumulation" if allow_strong else "accumulation"
    if score > 0.10:
        if reliability >= 0.30 and flow_regime == "true_distribution":
            return "neutral"
        return "accumulation"
    if score < -0.35:
        if reliability >= 0.30 and flow_regime == "true_accumulation":
            return "neutral"
        if reliability >= 0.30 and flow_regime == "buying_pressure_fading":
            return "distribution"
        return "strong_distribution" if allow_strong else "distribution"
    if score < -0.10:
        if reliability >= 0.30 and flow_regime == "true_accumulation":
            return "neutral"
        return "distribution"
    return "neutral"


def _trade_signal(signal: str) -> str:
    if signal in ("accumulation", "strong_accumulation"):
        return "long"
    if signal in ("distribution", "strong_distribution"):
        return "short"
    return "neutral"


def _insight_label(signal: str, flow_regime: str, quality: str) -> str:
    if flow_regime == "selling_pressure_easing" and signal in ("accumulation", "strong_accumulation"):
        return "bullish_watch_selling_pressure_easing"
    if flow_regime == "buying_pressure_fading" and signal in ("distribution", "strong_distribution"):
        return "bearish_watch_buying_pressure_fading"
    if flow_regime == "true_accumulation" and signal in ("accumulation", "strong_accumulation"):
        return "confirmed_accumulation"
    if flow_regime == "true_distribution" and signal in ("distribution", "strong_distribution"):
        return "confirmed_distribution"
    if quality in ("low", "no_flow"):
        return "price_based_low_flow_quality"
    if signal == "neutral":
        return "neutral_or_conflicted"
    return "price_flow_mixed"


def compute_signal(df: pd.DataFrame, ticker: str = None) -> pd.DataFrame:
    df = df.copy()

    s_ofi = _norm_clip(df["ofi_z"])
    s_vwap = _norm_clip(df["vwap_dev"])
    s_impact = -_norm_clip(df["impact_eff_z"])

    quality = compute_flow_quality(df)
    flow_reliability = float(quality["flow_reliability"])
    relative_flow = _norm_clip(df["inst_net_z"]) if "inst_net_z" in df.columns else pd.Series(0.0, index=df.index)
    raw_flow = _flow_direction_score(df)
    s_flow = (0.70 * raw_flow + 0.30 * relative_flow).clip(-1, 1).fillna(0)

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
    df["raw_score"] = (base_score * (1.0 + rvol_boost)).clip(-1, 1)

    direction_sign = df["hmm_label"].map({"accumulation": 1, "distribution": -1, "neutral": 0}).fillna(0)
    hmm_strength = df["hmm_strength"] if "hmm_strength" in df.columns else pd.Series(0.0, index=df.index)
    df["hmm_boost"] = direction_sign * hmm_strength * 0.10
    df["final_score"] = (df["raw_score"] + df["hmm_boost"]).clip(-1, 1)

    df["flow_score_raw"] = raw_flow
    df["flow_score_relative"] = relative_flow
    df["flow_score"] = s_flow
    df["flow_regime"] = _flow_regime(df, relative_flow)
    df["flow_reliability"] = flow_reliability
    df["flow_weight"] = flow_weight
    df["data_quality"] = str(quality["data_quality"])
    df["flow_coverage_full"] = float(quality["flow_coverage_full"])
    df["flow_coverage_20"] = float(quality["flow_coverage_20"])
    df["flow_coverage_60"] = float(quality["flow_coverage_60"])
    df["flow_gap_bars"] = float(quality["flow_gap_bars"])

    df["signal"] = [
        _classify_signal(float(score), str(regime), flow_reliability)
        for score, regime in zip(df["final_score"], df["flow_regime"])
    ]
    df["trade_signal"] = df["signal"].map(_trade_signal)
    df["insight_label"] = [
        _insight_label(str(sig), str(regime), str(quality["data_quality"]))
        for sig, regime in zip(df["signal"], df["flow_regime"])
    ]

    # Keep confidence comparable to v4, but mark data quality separately.
    df["raw_confidence"] = (df["final_score"].abs() * 100).round(1)
    conflict = (
        ((df["final_score"] > 0.10) & df["flow_regime"].isin(["true_distribution"]))
        | ((df["final_score"] < -0.10) & df["flow_regime"].isin(["true_accumulation"]))
    )
    quality_multiplier = 0.65 + 0.35 * flow_reliability
    df["confidence"] = (df["raw_confidence"] * quality_multiplier).where(~conflict, df["raw_confidence"] * 0.50)
    df["confidence"] = df["confidence"].round(1)

    direction = np.where(df["trade_signal"] == "long", 1, np.where(df["trade_signal"] == "short", -1, 0))
    df["est_inst_participation"] = (
        (df["rvol"].clip(0, 3) / 3 * 0.5 + (-df["impact_eff_z"]).clip(0, 2) / 2 * 0.3 + s_ofi.abs() * 0.2)
        * 25
    ).clip(0, 25).round(2)
    df["delta_inventory"] = direction * df["est_inst_participation"] / 100 * df["volume"]
    df["cumulative_inventory"] = df["delta_inventory"].cumsum()

    print("[v5] Unified scoring; main-flow is feature quality, not a model category")
    print(
        "[v5] Flow quality: "
        f"reliability={flow_reliability:.2f}, "
        f"full={quality['flow_coverage_full']:.1%}, "
        f"20bar={quality['flow_coverage_20']:.1%}, "
        f"60bar={quality['flow_coverage_60']:.1%}, "
        f"quality={quality['data_quality']}"
    )
    print(
        "[v5] Effective weights: "
        + " | ".join(f"{k}={v:.2f}" for k, v in weights.items() if v > 0)
    )
    return df


def _merged_cache_path(ticker: str, interval: str, from_date, to_date) -> str:
    safe_from = from_date or "2025-07-01"
    safe_to = to_date or "latest"
    return os.path.join(RAW_CACHE_DIR, f"{ticker}_{interval}_{safe_from}_{safe_to}_v5.csv")


def load_merged_cached(ticker, interval, limit, from_date=None, to_date=None, use_cache=True, refresh=False):
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
    has_flow = fl is not None
    if has_flow:
        df = merge_flow(df, fl)
    else:
        df["flow_present"] = False

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
        "raw_score", "hmm_boost", "final_score",
        "signal", "trade_signal", "flow_regime", "data_quality", "insight_label",
        "confidence", "raw_confidence",
        "flow_reliability", "flow_weight", "flow_coverage_full",
        "flow_coverage_20", "flow_coverage_60", "flow_gap_bars",
        "flow_score", "flow_score_raw", "flow_score_relative",
        "est_inst_participation", "delta_inventory", "cumulative_inventory",
        "flow_present", "inst_net", "inst_net_raw", "xl_net", "l_net", "inst_net_z",
    ]
    out = df[[c for c in cols if c in df.columns]].copy().dropna(subset=["signal"])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{ticker}_{interval}_{ts}_v5_signals.csv"
    fpath = os.path.join(OUTPUT_DIR, fname)
    out.to_csv(fpath, index=False)
    return fpath


def print_summary(df: pd.DataFrame, ticker: str, interval: str):
    valid = df.dropna(subset=["signal"])
    counts = valid["signal"].value_counts()
    last = valid.iloc[-1]

    print(f"\n{'='*55}")
    print(f"  {ticker} | {interval} | {len(valid)} bars [v5]")
    print(f"{'='*55}")
    print("\n[Signal Distribution]")
    for sig, cnt in counts.items():
        print(f"  {sig:<25} {cnt:>4} bars  {cnt / len(valid) * 100:5.1f}%")

    print("\n[Latest]")
    print(f"  Time          : {last['datetime']}")
    print(f"  Close         : ${last['close']:.2f}")
    print(f"  Signal        : {last['signal']}")
    print(f"  Trade signal  : {last['trade_signal']}")
    print(f"  Flow regime   : {last['flow_regime']}")
    print(f"  Insight label : {last['insight_label']}")
    print(f"  Confidence    : {last['confidence']:.1f}%")
    print(f"  Final Score   : {last['final_score']:+.3f}")
    print(f"  Flow Quality  : {last['data_quality']} (reliability={last['flow_reliability']:.2f})")
    print(f"{'='*55}\n")


def main():
    parser = argparse.ArgumentParser(description="Institutional Flow Signal Generator v5")
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--limit", default=300, type=int)
    parser.add_argument("--hmm-states", default=3, type=int)
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--to-date", default=None)
    parser.add_argument("--train-end", default=None)
    parser.add_argument("--refresh-data", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    interval = args.interval
    mode = "OOS" if args.train_end else "FULL"
    print(f"\n[START] {ticker} | {interval} | v5 ({mode}) | unified flow-quality gate")
    print("-" * 50)

    df, _ = load_merged_cached(
        ticker,
        interval,
        args.limit,
        from_date=args.from_date,
        to_date=args.to_date,
        use_cache=not args.no_cache,
        refresh=args.refresh_data,
    )
    _ = v4.load_large_trades(ticker, limit=200)
    if df is None:
        print(f"[FATAL] Could not load data for {ticker}")
        return None

    print("[Training HMM (fixed 3 states)...]")
    df = v4.fit_hmm(df, n_states=args.hmm_states, train_end=args.train_end)
    print("[Scoring signals (v5 unified weights)...]")
    df = compute_signal(df, ticker=ticker)
    fpath = save_output(df, ticker, interval)
    print_summary(df, ticker, interval)
    print(f"[SAVED] {fpath}\n")
    return fpath


if __name__ == "__main__":
    main()
