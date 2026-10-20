"""
Institutional Flow Signal Generator v4
=======================================
Changes from v3:
  - Removed liq_abs_z: lowest IC across all tickers (avg|IC|=0.013),
    sign inconsistent, measurement approach flawed.
  - Removed clv: weak IC (0.032), no microstructure theory backing.
  - Removed price_persistence: weak IC (0.026), 3-bar window too narrow.
  - Upgraded impact_eff_z: sqrt market impact model (Almgren/Gatheral).
  - Rebalanced weights: ofi_z raised 0.15->0.30, inst_net_z 0.50->0.45.

Feature set (5 with flow, 4 without):
  WITH flow:    inst_net_z=0.45, ofi_z=0.30, rvol=0.10,
                vwap_dev=0.10, impact_eff_z=0.05
  WITHOUT flow: ofi_z=0.50, rvol=0.20, vwap_dev=0.20, impact_eff_z=0.10

Usage:
  python signal_generator_v4.py --ticker AAPL --interval 1h --from-date 2024-06-24

  1. REMOVED Lasso weight learning
     - Weights were unstable across different data periods
     - Required training → not suitable for real-time analysis
     - Risk of overfitting on short main-flow history (89-559 bars)
     - Replaced with: fixed adaptive weights based on main-flow coverage

  2. FIXED ADAPTIVE WEIGHTS (no training required)
     - When main-flow available: flow=0.50, OHLCV features share 0.50
     - When main-flow unavailable: OHLCV features share equally
     - Weights are transparent, interpretable, and consistent across tickers

  3. KEPT: Mixed OFI (Lee-Ready + BVC blend)
     - Dynamic alpha based on trend strength
     - Trending market → more Lee-Ready; ranging → more BVC

  4. KEPT: 9:35 ET open filter (removes auction noise)

  5. KEPT: Fixed 3-state HMM (BIC disabled — insufficient samples)

Usage:
  python signal_generator_v3.py --ticker AAPL --interval 1h --from-date 2024-01-01
  python signal_generator_v3.py --ticker NVDA --interval 1d --from-date 2024-01-01
"""

import argparse
import os
import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats
from market_data_quality import regular_session_mask, unique_timestamp_bars
from research_api import ResearchAPIError, fetch_api

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
BASE_URL   = os.environ.get("US_STOCK_API_BASE_URL", "http://74.208.124.247:8000").rstrip("/")
TIMEOUT    = 60
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
RAW_CACHE_DIR = os.path.join(os.path.dirname(__file__), "raw_data_cache")
os.makedirs(RAW_CACHE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Fixed adaptive weights (no training needed)
# Rationale: inst_net_z is the only feature with true directional information.
# When available, it dominates. OHLCV features provide supporting context.
#
# v4 fallback weights — used when ticker is not in TICKER_CLUSTER_MAP and
# no cluster can be inferred. Evidence-based from 23-ticker IC analysis.
WEIGHTS_WITH_FLOW = {
    "flow": 0.45, "ofi": 0.35, "vwap": 0.15, "impact": 0.05
}
WEIGHTS_NO_FLOW = {
    "flow": 0.00, "ofi": 0.55, "vwap": 0.30, "impact": 0.15
}
# rvol is no longer a fixed-weight directional feature.
# IC sign is inconsistent across tickers (0/23 on 1d data, 23-ticker study) —
# meaning high volume has no stable directional bias.
# Instead, rvol acts as a multiplicative amplifier.
RVOL_BOOST_SCALE = 0.10   # max ±10% amplification
RVOL_BOOST_CLIP  = 0.10   # hard cap on boost magnitude

# ══════════════════════════════════════════════
# IC-Pattern Cluster Weights (v4 — derived from ic_analysis_yfinance.py)
# ══════════════════════════════════════════════
# Method: Hierarchical clustering (k=5, silhouette=0.307) on each ticker's
# 4-dim avg|IC| vector [ofi_z, rvol, vwap_dev, impact_eff_z], computed
# from 42 tickers on 1d yfinance OHLCV data (expanded from an initial
# 23-ticker run after validate_cluster_coverage.py showed 6/12 new-sector
# tickers fell outside the original 4 clusters' coverage). Validated via:
#   - Kruskal-Wallis: 4/4 features significant (all p<0.05) — stronger
#     than the prior 23-ticker/k=4 run (2/4 significant)
#   - F-ratio: 4/4 features > 1 (between-group var > within-group var)
#   - Bootstrap stability (100 resamples): mean co-occurrence = 0.768
#
# Known caveats (documented, not yet resolved):
#   - G0 has only 2 tickers (UNH, EQIX) — bootstrap shows its boundary
#     with G3 is somewhat blurry (UNH-XOM and EQIX-XOM co-occurrence
#     >0.7 despite being in different clusters). Treat G0 weights as
#     lower-confidence until more healthcare/REIT-pattern tickers are added.
#   - RIVN sits in G2 but has low co-occurrence (<0.3) with every other
#     G2 member — it's an isolated point, not a confirmed part of that
#     cluster's pattern. More high-volatility growth tickers needed to
#     confirm its true grouping.
#
# These are NO-FLOW weights only. Flow (inst_net_z) weight design is
# deferred until server data quality is resolved and per-ticker flow
# sensitivity can be measured (see project handoff doc section 6).
#
# rvol_amp_scale: relative rvol IC strength vs strongest cluster (G2) —
# clusters with higher rvol IC get a stronger amplifier effect.
# overall_scale: relative total IC strength (sum of all 4 features) vs
# strongest cluster (G0) — clusters with weak IC overall (G4) get signal
# strength dialed down rather than overweighted.
CLUSTER_WEIGHTS = {
    "G0": {"ofi": 0.53, "vwap": 0.30, "impact": 0.17,
           "rvol_amp_scale": 0.61, "overall_scale": 1.00},
    "G1": {"ofi": 0.35, "vwap": 0.22, "impact": 0.42,
           "rvol_amp_scale": 0.51, "overall_scale": 0.82},
    "G2": {"ofi": 0.46, "vwap": 0.34, "impact": 0.19,
           "rvol_amp_scale": 1.00, "overall_scale": 0.72},
    "G3": {"ofi": 0.31, "vwap": 0.48, "impact": 0.21,
           "rvol_amp_scale": 0.58, "overall_scale": 0.70},
    "G4": {"ofi": 0.41, "vwap": 0.32, "impact": 0.26,
           "rvol_amp_scale": 0.38, "overall_scale": 0.47},
}

# Ticker -> cluster lookup, from 42-ticker IC clustering run (2026-06-23,
# k=5). Tickers not in this map fall back to soft cluster assignment
# (see CLUSTER_CENTROIDS below) rather than a flat global default.
TICKER_CLUSTER_MAP = {
    "UNH": "G0", "EQIX": "G0",
    "TSLA": "G1", "GS": "G1",
    "GOOGL": "G2", "AAPL": "G2", "LLY": "G2", "PFE": "G2", "PLD": "G2",
    "O": "G2", "RBLX": "G2", "SOFI": "G2", "RIVN": "G2",
    "AMZN": "G3", "WMT": "G3", "JPM": "G3", "AMD": "G3", "JNJ": "G3",
    "XOM": "G3", "ARM": "G3", "MRK": "G3", "UBER": "G3", "AMT": "G3",
    "MSTR": "G3", "IWM": "G3",
    "NVDA": "G4", "MSFT": "G4", "META": "G4", "BRK-B": "G4", "CAT": "G4",
    "ABBV": "G4", "KO": "G4", "PG": "G4", "NFLX": "G4", "PLTR": "G4",
    "BA": "G4", "CRM": "G4", "COIN": "G4", "SMCI": "G4", "DKNG": "G4",
    "SPY": "G4", "QQQ": "G4",
}
# SPY/QQQ land in G4 for structural reasons (ETF basket pricing suppresses
# single-stock microstructure signals), not a data quality issue. See
# project doc section 3.4 for full explanation. Treat as benchmark
# references for chart overlay, not signal generation targets.

# ══════════════════════════════════════════════
# WITH-FLOW Cluster Weights — VALIDATED, WIRED INTO compute_signal()
# ══════════════════════════════════════════════
# History: an earlier 3-ticker draft (AAPL/GOOGL/NVDA only) was staged
# here but explicitly NOT wired in, pending more data and validation.
# This is the follow-up: 19 tickers (2026-06-30 run), confidence-weighted
# IC over 5 dims [ofi_z, rvol, vwap_dev, impact_eff_z, inst_net_z],
# k=3 clustering (silhouette=0.306, highest across k=2-6 tested).
#
# Validation (validate_clustering_with_flow.py):
#   - Kruskal-Wallis: 2/5 significant (rvol p=0.035, inst_net_z p=0.027;
#     vwap_dev p=0.073 borderline)
#   - F-ratio: 5/5 features > 1 (inst_net_z highest at F=16.30)
#   - Bootstrap stability (100 resamples): mean co-occurrence = 0.846
#     (0 unstable pairs, 0 ambiguous cross-cluster pairs — strongest
#     stability result of any clustering run so far, no-flow or with-flow)
#   - Pairwise Mann-Whitney confirms each cluster's claimed dominant
#     feature is significantly different from at least one other cluster:
#     F0 vs F2 on inst_net_z (p=0.0036) and ofi_z (p=0.0250);
#     F1 vs F2 on vwap_dev (p=0.0393) and rvol (p=0.0143)
#
# ⚠️ STILL CARRYING THE SAME DATA-QUALITY CAVEAT AS BEFORE — not resolved,
# just no longer blocking. main-flow coverage numbers used here are the
# TRIMMED ("effective start") values from ic_analysis_with_flow.py, which
# corrects for pipeline-not-yet-deployed gaps (most tickers' raw coverage
# jumped from 10-20% to 94-99% after trimming to when the pipeline
# actually started producing data for that ticker). This does NOT fix the
# underlying large-trades duplicate-rate issue (still 32.5% for AAPL,
# unresolved at the DB level) — duplicates inside the "effective" window
# are still uncorrected at the source, only caught by the in-script
# dedup in load_large_trades(), which operates on a different table than
# the main-flow hourly aggregates these IC numbers are computed from.
# Treat this as the best available data, not as clean data.
#
# F0 = SPY/NVDA/MSFT pattern — flow-dominant, ofi weak (3 tickers)
# F1 = TSLA/GOOGL/WMT pattern — vwap-dominant (3 tickers)
# F2 = everyone else (14 tickers) — ofi-dominant, the largest/most
#      heterogeneous group; bootstrap stability for this group is still
#      strong (no unstable pairs) despite its size, but it likely
#      contains sub-structure that more tickers + a higher k would reveal
#
# Flow weight capped at 0.45 (same ceiling as global WEIGHTS_WITH_FLOW)
# — F0's raw pooled-IC-implied flow share was 0.60, capped down.
WITH_FLOW_CLUSTER_WEIGHTS = {
    "F0": {"flow": 0.45, "ofi": 0.14, "vwap": 0.28, "impact": 0.13, "rvol_amp_scale": 1.00},
    "F1": {"flow": 0.09, "ofi": 0.20, "vwap": 0.56, "impact": 0.15, "rvol_amp_scale": 0.94},
    "F2": {"flow": 0.14, "ofi": 0.44, "vwap": 0.31, "impact": 0.11, "rvol_amp_scale": 0.50},
}
TICKER_CLUSTER_MAP_WITH_FLOW = {
    "SPY": "F0", "NVDA": "F0", "MSFT": "F0",
    "TSLA": "F1", "GOOGL": "F1", "WMT": "F1",
    "AAPL": "F2", "UBER": "F2", "QQQ": "F2", "PLTR": "F2", "META": "F2",
    "GS": "F2", "CRM": "F2", "COIN": "F2", "CAT": "F2", "BA": "F2",
    "AMD": "F2", "JPM": "F2", "XOM": "F2",
}
# TODO: re-run with more tickers once DB-level dedup is fixed, especially
# to test whether F2 (14 tickers) splits into sub-clusters at a higher k.
# Tickers not in this map fall back to the flat global WEIGHTS_WITH_FLOW
# (no soft-assignment system built for the with-flow case yet — the
# no-flow soft assignment via CLUSTER_CENTROIDS doesn't apply here since
# it's a 4-dim space, not 5-dim with inst_net_z).

# ══════════════════════════════════════════════
# Soft Cluster Assignment (for tickers NOT in TICKER_CLUSTER_MAP)
# ══════════════════════════════════════════════
# Design choice: fixed centroids + softmax distance weighting, NOT
# online-updated centroids and NOT full re-clustering on every new ticker.
#
# Why not online-updated centroids: centroids would drift based on the
# ORDER tickers are added (path dependency) — hard to debug, and
# philosophically the same risk as the v2 Lasso mistake (letting historical
# data continuously reshape model parameters introduces instability when
# the ticker count is still small).
#
# Why not full re-clustering every time: cluster labels (G0/G1/G2/G3) are
# arbitrary from k-means and can swap on every re-run, breaking any
# downstream weight table that references "G0" by name. Also expensive.
#
# Fixed centroids + softmax gives a deterministic, order-independent
# result: the same ticker always gets the same weight blend, and a ticker
# that sits between two clusters gets a sensible mix instead of being
# forced into one bucket. Target accuracy for this system is ~70%, not
# 100% — softmax blending is appropriate at that precision level; a more
# complex online-learning system would be over-engineering for the
# accuracy actually needed.
#
# Centroids below are in STANDARDIZED space — computed from the 23-ticker
# training set's mean/std for [ofi_z, rvol, vwap_dev, impact_eff_z].
# These must be regenerated (via ic_analysis_yfinance.py) if the training
# ticker set changes materially.
CLUSTER_CENTROIDS_MEAN_STD = {
    # mean/std used to standardize a new ticker's raw avg|IC| vector
    # before computing distance to centroids — must match the scaler
    # used when CLUSTER_CENTROIDS was computed (sklearn StandardScaler
    # fit on the 42-ticker training set, 1d interval, 2026-06-23 run).
    "ofi_z":         {"mean": 0.0410, "std": 0.0198},
    "rvol":          {"mean": 0.0346, "std": 0.0169},
    "vwap_dev":      {"mean": 0.0382, "std": 0.0159},
    "impact_eff_z":  {"mean": 0.0240, "std": 0.0116},
}
CLUSTER_CENTROIDS = {
    # Centroid position in standardized space, order: [ofi_z, rvol, vwap_dev, impact_eff_z]
    # Computed via StandardScaler + groupby-mean on the 42-ticker IC matrix (k=5).
    "G0": np.array([ 2.8514,  0.0678,  1.0377,  0.5621]),
    "G1": np.array([ 0.5765, -0.2631, -0.3082,  3.3101]),
    "G2": np.array([ 0.2469,  1.4295, -0.2573, -0.4274]),
    "G3": np.array([-0.1746, -0.0243,  1.1846,  0.0719]),
    "G4": np.array([-0.4107, -0.7167, -0.7858, -0.2800]),
}
SOFTMAX_TEMPERATURE = 1.0  # higher = softer/more blended, lower = harder/closer to nearest-only


def get_soft_cluster_weights(ic_vector: dict) -> dict:
    """
    Given a new ticker's raw avg|IC| vector (keys: ofi_z, rvol, vwap_dev,
    impact_eff_z), return a blended weight dict using softmax-weighted
    distance to the fixed cluster centroids.

    This is used for tickers NOT in TICKER_CLUSTER_MAP — i.e. any ticker
    outside the original 23-ticker training set. Target precision ~70%,
    so a soft blend across the nearest clusters is preferred over forcing
    a hard assignment.
    """
    # Standardize using training set's mean/std
    std_vec = np.array([
        (ic_vector.get(f, 0.0) - CLUSTER_CENTROIDS_MEAN_STD[f]["mean"])
        / CLUSTER_CENTROIDS_MEAN_STD[f]["std"]
        for f in ["ofi_z", "rvol", "vwap_dev", "impact_eff_z"]
    ])

    # Distance to each centroid
    dists = {c: np.linalg.norm(std_vec - cen) for c, cen in CLUSTER_CENTROIDS.items()}

    # Softmax over negative distance (closer = higher weight)
    neg_d = np.array([-d / SOFTMAX_TEMPERATURE for d in dists.values()])
    neg_d = neg_d - neg_d.max()  # numerical stability
    exp_d = np.exp(neg_d)
    membership = exp_d / exp_d.sum()
    membership = dict(zip(dists.keys(), membership))

    # Blend the cluster weight tables by membership
    blended = {"ofi": 0.0, "vwap": 0.0, "impact": 0.0,
               "rvol_amp_scale": 0.0, "overall_scale": 0.0}
    for c, m in membership.items():
        cw = CLUSTER_WEIGHTS[c]
        for k in blended:
            blended[k] += m * cw[k]

    blended["_membership"] = {c: round(float(m), 3) for c, m in membership.items()}
    return blended


# ══════════════════════════════════════════════
# 1. Data Fetching
# ══════════════════════════════════════════════

def fetch(path: str, params: dict = None):
    return fetch_api(BASE_URL, path, params=params, timeout=TIMEOUT)


def load_klines(ticker, interval, limit, from_date=None, to_date=None):
    interval_map = {
        "1m":  (1,"minute"), "5m":  (5,"minute"),
        "15m": (15,"minute"),"30m": (30,"minute"),
        "1h":  (1,"hour"),   "4h":  (4,"hour"),
        "1d":  (1,"day"),    "1w":  (1,"week"),
    }
    multiplier, timespan = interval_map.get(interval, (1, "minute"))

    from datetime import timedelta
    days_per_bar = {"minute": 1/1440, "hour": 1/24, "day": 1, "week": 7}
    date_to   = to_date if to_date else datetime.now().strftime("%Y-%m-%d")
    if from_date:
        date_from = from_date
    else:
        delta_days = int(limit * days_per_bar.get(timespan, 1)) + 30
        date_from  = (datetime.now() - timedelta(days=delta_days)).strftime("%Y-%m-%d")

    raw = fetch("/api/klines", {
        "ticker": ticker, "multiplier": multiplier, "timespan": timespan,
        "from": date_from, "to": date_to,
    })
    if raw is None:
        sys.exit("[FATAL] Cannot fetch klines")

    arr = raw if isinstance(raw, list) else (raw.get("bars") or raw.get("data") or raw.get("klines") or [])
    if not arr:
        sys.exit("[FATAL] Empty klines")

    rows = []
    for b in arr:
        if isinstance(b, list):
            rows.append({"timestamp": int(b[0]), "open": float(b[1]),
                         "high": float(b[2]),  "low": float(b[3]),
                         "close": float(b[4]), "volume": float(b[5])})
        else:
            rows.append({"timestamp": int(b.get("t") or b.get("time") or b.get("timestamp")),
                         "open":  float(b.get("o") or b.get("open")),
                         "high":  float(b.get("h") or b.get("high")),
                         "low":   float(b.get("l") or b.get("low")),
                         "close": float(b.get("c") or b.get("close")),
                         "volume":float(b.get("v") or b.get("volume"))})

    df = unique_timestamp_bars(pd.DataFrame(rows))
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")

    # Filter to market hours: 9:35–16:00 ET (9:30–9:35 excluded = opening auction noise)
    if timespan in ("minute", "hour"):
        before = len(df)
        df = df.loc[regular_session_mask(df["timestamp"])].reset_index(drop=True)
        if df.empty:
            raise ValueError("No regular-session klines after the auction filter")
        print(f"[OK] Klines (9:35–16:00 ET): {len(df)} bars (removed {before-len(df)})  "
              f"[{df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]}]")
    else:
        print(f"[OK] Klines: {len(df)} bars  [{df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]}]")
    return df


def load_main_flow(ticker, interval, limit, from_date=None, to_date=None):
    from datetime import timedelta
    MAINFLOW_START = datetime(2025, 7, 1)  # default only; not a permanent source boundary
    dt_to   = datetime.strptime(to_date,   "%Y-%m-%d") if to_date   else datetime.now()
    dt_from = datetime.strptime(from_date, "%Y-%m-%d") if from_date else MAINFLOW_START

    all_rows = []
    cursor = dt_from
    while cursor < dt_to:
        next_cursor = min(cursor + timedelta(days=30), dt_to)
        seg_from = cursor.strftime("%Y-%m-%d")
        seg_to   = next_cursor.strftime("%Y-%m-%d")
        raw = fetch("/api/main-flow", {
            "ticker": ticker, "multiplier": 5, "timespan": "minute",
            "from": seg_from, "to": seg_to,
        })
        if raw:
            arr = raw if isinstance(raw, list) else (raw.get("bars") or raw.get("data") or [])
            all_rows.extend(arr)
            print(f"  main-flow {seg_from} → {seg_to}: {len(arr)} bars")
        cursor = next_cursor

    if not all_rows:
        print("[WARN] No main-flow data")
        return None

    rows = []
    for b in all_rows:
        t = b.get("time") or b.get("t") or b.get("timestamp") or 0
        xl_net = float(b.get("super_buy", 0)) - float(b.get("super_sell", 0))
        l_net  = float(b.get("large_buy",  0)) - float(b.get("large_sell",  0))
        m_net  = float(b.get("mid_buy",    0)) - float(b.get("mid_sell",    0))
        s_net  = float(b.get("small_buy",  0)) - float(b.get("small_sell",  0))
        # Session filtering is applied below using the ET timezone, including DST.
        is_outlier = abs(xl_net) > 50_000_000
        if is_outlier:
            continue
        rows.append({"timestamp": int(t), "xl_net": xl_net,
                     "l_net": l_net, "m_net": m_net, "s_net": s_net})

    if not rows:
        return None
    df = unique_timestamp_bars(pd.DataFrame(rows))
    df = df.loc[regular_session_mask(df["timestamp"])].reset_index(drop=True)
    if df.empty:
        return None
    df["inst_net"] = df["xl_net"] + df["l_net"]
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["date"]     = df["datetime"].dt.normalize()

    if interval == "1d":
        agg = df.groupby("date").agg(
            inst_net=("inst_net", "sum"),
            xl_net=("xl_net", "sum"),
            l_net=("l_net", "sum"),
        ).reset_index()
        agg["timestamp"] = agg["date"].astype("int64") // 10**6
        print(f"[OK] main-flow: {len(all_rows)} raw bars → {len(agg)} daily bars")
        return agg
    else:
        df["hour"] = df["datetime"].dt.floor("H")
        agg = df.groupby("hour").agg(
            inst_net=("inst_net", "sum"),
            xl_net=("xl_net", "sum"),
            l_net=("l_net", "sum"),
        ).reset_index()
        agg["timestamp"] = agg["hour"].astype("int64") // 10**6
        print(f"[OK] main-flow: {len(all_rows)} raw bars → {len(agg)} hourly bars")
        return agg


def load_large_trades(ticker, limit=500):
    raw = fetch("/api/large-trades", {"ticker": ticker, "limit": limit})
    if raw is None:
        return None
    arr = raw if isinstance(raw, list) else raw.get("trades") or raw.get("data") or []
    if not arr:
        return None

    # ── Deduplicate on raw fields BEFORE renaming ──────────────────────
    # The API returns duplicate rows for the same trade (confirmed: up to
    # 20.8% duplicate rate in 2026 data, with identical time/price/size/
    # exchange rows written multiple times in batch). Dedup here so every
    # downstream calculation (inst_net, large_trade_total, etc.) uses only
    # real unique trades, not inflated counts.
    import pandas as _pd
    raw_df = _pd.DataFrame(arr)
    dedup_keys = [k for k in ["time", "price", "size", "exchange"]
                  if k in raw_df.columns]
    if dedup_keys:
        before = len(raw_df)
        raw_df = raw_df.drop_duplicates(subset=dedup_keys).reset_index(drop=True)
        after = len(raw_df)
        if before != after:
            print(f"[Dedup] large-trades: {before} -> {after} rows "                  f"({before - after} duplicates removed, "                  f"{(before-after)/before:.1%})")
    arr = raw_df.to_dict(orient="records")
    # ────────────────────────────────────────────────────────────────────

    rows = []
    for t in arr:
        side = str(t.get("side") or t.get("taker_side") or "").lower()
        rows.append({
            "timestamp": int(t.get("timestamp") or t.get("t") or t.get("time") or 0),
            "price":  float(t.get("price") or t.get("p") or 0),
            "size":   float(t.get("size")  or t.get("s") or t.get("quantity") or 0),
            "is_buy": side in ("buy", "b", "1"),
        })
    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    print(f"[OK] large-trades: {len(df)} records")
    return df


# ══════════════════════════════════════════════
# 2. Feature Engineering
# ══════════════════════════════════════════════

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute 6 features for HMM input.

    Features and formulas:
    ──────────────────────────────────────────────
    1. ofi_z — Order Flow Imbalance (normalized)
       Mixed OFI = α × LR_OFI + (1-α) × BVC_OFI
       where α = f(trend strength): high trend → more Lee-Ready, ranging → more BVC

       Lee-Ready signed volume:
         lr_sign = +1 if close > midprice, -1 if close < midprice, tick_sign otherwise
         LR_OFI  = Σ(lr_sign × volume) over rolling 5 bars

       BVC (Bulk Volume Classification, Easley et al. 2012):
         buy_frac = (close - low) / (high - low)
         BVC_net  = (buy_frac - 0.5) × 2 × volume
         BVC_OFI  = Σ(BVC_net) over rolling 5 bars

       ofi_z = mixed_OFI / rolling_20_std(mixed_OFI)

    2. rvol — Relative Volume
       rvol = volume / rolling_20_mean(volume)
       >1 = above-average volume (potential institutional activity)

    3. impact_eff_z — Price Impact Efficiency (normalized)
       impact_eff = |Δclose| / rolling_5_mean(volume)
       Low value = large volume with small price move = passive institutional filling
       impact_eff_z = (impact_eff - rolling_20_mean) / rolling_20_std

    4. liq_abs_z — Liquidity Absorption (normalized)
       range = (high - low) / close
       liq_absorption = rvol / (range × 100 + ε)
       High value = high volume + small range = absorption of order flow
       liq_abs_z = (liq_absorption - rolling_20_mean) / rolling_20_std

    5. vwap_dev — VWAP Deviation
       vwap_roll = Σ(close × volume, 20) / Σ(volume, 20)
       vwap_dev  = (close - vwap_roll) / vwap_roll
       Positive = price above VWAP (buy pressure); Negative = below (sell pressure)

    6. inst_net_z — Institutional Net Flow (normalized)  [only when main-flow available]
       inst_net = (super_buy - super_sell) + (large_buy - large_sell)
       inst_net_z = inst_net / rolling_20_std(inst_net)
       This is the ONLY feature computed from actual tick-level trade data.
    ──────────────────────────────────────────────
    """
    df = df.copy()

    # Returns and range
    df["ret"]     = df["close"].pct_change()
    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    df["range"]   = (df["high"] - df["low"]) / df["close"]

    # VWAP (rolling 20 bars)
    df["vwap_roll"] = (
        (df["close"] * df["volume"]).rolling(20).sum() /
        df["volume"].rolling(20).sum()
    )
    df["vwap_dev"] = (df["close"] - df["vwap_roll"]) / df["vwap_roll"]

    # ── Mixed OFI: Lee-Ready + BVC
    # Lee-Ready component
    df["midprice"]  = (df["high"] + df["low"]) / 2
    df["tick_sign"] = np.sign(df["close"] - df["close"].shift(1))
    df["lr_sign"]   = np.where(
        df["close"] > df["midprice"],  1,
        np.where(df["close"] < df["midprice"], -1, df["tick_sign"])
    )
    df["signed_vol"] = df["lr_sign"] * df["volume"]
    ofi_lr = df["signed_vol"].rolling(5).sum()

    # BVC component (Easley, López de Prado & O'Hara, 2012)
    bar_range = (df["high"] - df["low"]).replace(0, np.nan)
    df["bvc_buy_frac"] = ((df["close"] - df["low"]) / bar_range).fillna(0.5)
    bvc_net  = (df["bvc_buy_frac"] - 0.5) * 2 * df["volume"]
    ofi_bvc  = bvc_net.rolling(5).sum()

    # Dynamic blend: α scales with trend strength
    # Strong trend → more Lee-Ready (follows momentum)
    # Ranging market → more BVC (less directional bias)
    ret_ma   = df["close"].pct_change().rolling(20).mean().abs()
    ret_norm = (ret_ma / (ret_ma.rolling(50).mean() + 1e-8)).clip(0, 2) / 2
    alpha    = ret_norm.fillna(0.5)
    df["ofi_raw"] = alpha * ofi_lr + (1 - alpha) * ofi_bvc
    ofi_std       = df["ofi_raw"].rolling(20).std().replace(0, np.nan)
    df["ofi_z"]   = df["ofi_raw"] / ofi_std

    # Relative Volume
    df["rvol"] = df["volume"] / df["volume"].rolling(20).mean()

    # Square-Root Market Impact (Almgren/Gatheral)
    # Replaces linear |Dclose|/volume — empirical evidence shows
    # impact proportional to sigma x sqrt(Q/V), not Q/V.
    # Low value = large normalised volume, small move = passive filling.
    adv       = df["volume"].rolling(20).mean().replace(0, np.nan)
    sigma     = df["ret"].rolling(20).std().replace(0, np.nan)
    part_rate = (df["volume"] / adv).clip(0.01, 100)
    df["price_chg_abs"] = df["close"].diff().abs()
    # sigma is in return (%) units; multiply by close to convert to price ($) units
    # so low-price and high-price stocks are on the same scale before z-scoring.
    sqrt_impact = df["price_chg_abs"] / (sigma * df["close"] * np.sqrt(part_rate) + 1e-8)
    ie_std = sqrt_impact.rolling(20).std().replace(0, np.nan)
    df["impact_eff_z"] = (sqrt_impact - sqrt_impact.rolling(20).mean()) / ie_std

    return df


def merge_flow(df: pd.DataFrame, flow_df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    date_col = "date" if "date" in flow_df.columns else "hour"
    flow_sub = flow_df[[date_col, "inst_net", "xl_net", "l_net"]].copy()
    if date_col == "hour":
        flow_sub = flow_sub.rename(columns={"hour": "date"})
    if "hour" in flow_df.columns:
        df["date"] = df["datetime"].dt.floor("H")
    else:
        df["date"] = df["datetime"].dt.normalize()
    df = df.merge(flow_sub, left_on="date", right_on="date", how="left")
    df[["inst_net", "xl_net", "l_net"]] = df[["inst_net", "xl_net", "l_net"]].fillna(0)
    inst_std = df["inst_net"].rolling(20).std().replace(0, np.nan)
    df["inst_net_z"] = df["inst_net"] / inst_std
    return df


# ══════════════════════════════════════════════
# 3. HMM State Detection
# ══════════════════════════════════════════════

def fit_hmm(df: pd.DataFrame, n_states: int = 3,
            train_end: str = None) -> pd.DataFrame:
    """
    3-state Gaussian HMM trained on 5-6 features.

    Out-of-sample split (anti-overfitting):
      train_end: if provided (e.g. "2025-06-30"), HMM is trained ONLY on data
                 up to this date. The trained model then predicts states for
                 the entire dataset including future bars it has never seen.

      This prevents the model from "memorizing" the validation period and
      gives a true out-of-sample estimate of signal quality.

    Example:
      train_end="2025-06-30"
      → HMM trained on 2024-01 to 2025-06 (18 months)
      → States predicted for 2025-07 to 2026-06 (12 months, unseen)
      → 13F validation uses only the unseen period

    Note: BIC-based state selection disabled — overfits on <3600 bars.
    """
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        print("[WARN] hmmlearn not installed, skipping HMM")
        df["hmm_state"] = 0
        df["hmm_label"] = "neutral"
        return df

    feature_cols = ["ofi_z", "rvol", "impact_eff_z", "vwap_dev"]
    if "inst_net_z" in df.columns:
        feature_cols.append("inst_net_z")

    sub = df[feature_cols].copy().replace([np.inf, -np.inf], np.nan).fillna(0)
    X_all = sub.values

    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()

    # Out-of-sample split
    if train_end:
        train_mask = df["datetime"] <= pd.Timestamp(train_end)
        n_train = train_mask.sum()
        n_test  = (~train_mask).sum()
        print(f"[HMM] Out-of-sample split: train={n_train} bars (≤{train_end}), "
              f"test={n_test} bars (>{train_end})")
        if n_train < 100:
            print("[WARN] Too few training bars, using full dataset")
            train_end = None

    if train_end:
        X_train = X_all[train_mask.values]
        scaler.fit(X_train)
        X_scaled_train = scaler.transform(X_train)
        X_scaled_all   = scaler.transform(X_all)

        model = GaussianHMM(n_components=n_states, covariance_type="full",
                            n_iter=200, random_state=42)
        model.fit(X_scaled_train)
        states = model.predict(X_scaled_all)  # predict on ALL bars
        print(f"[HMM] Model trained on train set only → predicting full dataset")
    else:
        scaler.fit(X_all)
        X_scaled_all = scaler.transform(X_all)
        model = GaussianHMM(n_components=n_states, covariance_type="full",
                            n_iter=200, random_state=42)
        model.fit(X_scaled_all)
        states = model.predict(X_scaled_all)

    df = df.copy()
    df["hmm_state"] = states

    # Label states using training period profiles only (avoid leakage)
    if train_end:
        profile_df = df[df["datetime"] <= pd.Timestamp(train_end)]
    else:
        profile_df = df

    state_profiles = profile_df.groupby("hmm_state").agg(
        ofi_mean=("ofi_z", "mean"),
        rvol_mean=("rvol", "mean"),
        inst_mean=("inst_net_z", "mean") if "inst_net_z" in df.columns else ("ofi_z","mean"),
        ret_mean=("ret", "mean"),
        count=("ret","count")
    )
    print("\n[HMM] State profiles (training period):")
    print(state_profiles.to_string())

    ofi_col = "inst_mean" if "inst_mean" in state_profiles.columns else "ofi_mean"

    # ── Quality-gated labeling (fixes a real bug found via backtest review) ──
    # The old version did unconditional idxmax()/idxmin() — it ALWAYS picked
    # some state as "accumulation" and some as "distribution", even when every
    # state's inst_mean was negative (i.e. the HMM never actually found a real
    # buying regime; it just found "mild selling" vs "heavy selling" and the
    # less-negative one got mislabeled "accumulation"). This produced a state
    # with a near-zero or even negative true signal getting a flat +0.15 boost,
    # which manufactured false high-confidence signals — confirmed in backtest
    # as an inverted confidence/return relationship (higher confidence = worse
    # returns) and accumulation/distribution direction errors.
    #
    # Fix: only label a state accumulation/distribution if its inst_mean is
    # BOTH the most extreme in its direction AND statistically distinguishable
    # from zero (one-sample t-test on the per-bar inst_net_z values within that
    # state, training period only). States that don't clear this bar — even if
    # they're technically the max/min — are labeled neutral instead of having
    # a direction invented for them.
    SIG_ALPHA = 0.05  # significance threshold for "this state has a real direction"

    def state_inst_values(state_id):
        mask = (profile_df["hmm_state"] == state_id)
        col = "inst_net_z" if "inst_net_z" in profile_df.columns else "ofi_z"
        return profile_df.loc[mask, col].dropna().values

    candidate_acc  = state_profiles[ofi_col].idxmax()
    candidate_dist = state_profiles[ofi_col].idxmin()

    label_map = {}
    for state_id, candidate_dir in [(candidate_acc, "accumulation"), (candidate_dist, "distribution")]:
        vals = state_inst_values(state_id)
        mean_val = state_profiles.loc[state_id, ofi_col]
        if len(vals) < 10:
            continue  # not enough samples in this state to trust a direction call
        t_stat, p_val = stats.ttest_1samp(vals, 0)
        direction_ok = (mean_val > 0) if candidate_dir == "accumulation" else (mean_val < 0)
        if p_val < SIG_ALPHA and direction_ok:
            label_map[state_id] = candidate_dir
        # else: this state doesn't have a statistically real direction —
        # leave it unlabeled here, it will fall through to "neutral" below

    for s in state_profiles.index:
        if s not in label_map:
            label_map[s] = "neutral"
    df["hmm_label"] = df["hmm_state"].map(label_map).fillna("neutral")

    n_labeled = sum(1 for v in label_map.values() if v != "neutral")
    if n_labeled == 0:
        print("[HMM] [WARN] No state cleared the significance bar — all states "
              "labeled neutral. The HMM did not find a statistically real "
              "accumulation or distribution regime in this training window.")
    else:
        print(f"[HMM] Quality-gated labels: {label_map}")

    # ── Proportional strength (replaces the old flat ±0.15 boost) ──
    # Map each state's |inst_mean| to a 0-1 strength, scaled relative to the
    # strongest labeled state in this training window. A state that barely
    # cleared the significance bar gets a small boost; a state with a large,
    # clearly real inst_mean gets close to the full boost. Neutral states get 0.
    labeled_means = [abs(state_profiles.loc[s, ofi_col]) for s, lbl in label_map.items() if lbl != "neutral"]
    max_abs_mean = max(labeled_means) if labeled_means else 1.0
    if max_abs_mean == 0:
        max_abs_mean = 1.0  # avoid div by zero; strength will be 0 anyway since means are 0

    strength_map = {}
    for s in state_profiles.index:
        if label_map.get(s, "neutral") == "neutral":
            strength_map[s] = 0.0
        else:
            strength_map[s] = min(abs(state_profiles.loc[s, ofi_col]) / max_abs_mean, 1.0)
    df["hmm_strength"] = df["hmm_state"].map(strength_map).fillna(0.0)

    if train_end:
        df["oos"] = df["datetime"] > pd.Timestamp(train_end)
        oos_pct   = df["oos"].mean() * 100
        print(f"[HMM] Out-of-sample bars: {df['oos'].sum()} ({oos_pct:.1f}%)")

    return df


# ══════════════════════════════════════════════
# 4. Signal Scoring — Fixed Adaptive Weights
# ══════════════════════════════════════════════

def compute_signal(df: pd.DataFrame, ticker: str = None) -> pd.DataFrame:
    """
    Signal scoring formula:

    Step 1 — Normalize each feature to [-1, +1]:
      s_i = clip( (x_i - rolling_50_mean(x_i)) / rolling_50_std(x_i), -1, +1 )

    Step 2 — Weighted sum + rvol amplifier:
      With main-flow:
        base_score = 0.45×flow + 0.35×ofi + 0.15×vwap + 0.05×impact
        rvol_boost = clip((rvol - 1) × 0.10, -0.10, +0.10)
        raw_score  = clip(base_score × (1 + rvol_boost), -1, +1)

      Without main-flow:
        base_score = 0.55×ofi + 0.30×vwap + 0.15×impact
        raw_score  = clip(base_score × (1 + rvol_boost), -1, +1)

    Weight rationale (v4 — evidence-based from 13-ticker IC analysis on 1d data):
      - inst_net_z (flow): highest weight — only real tick-level data
      - ofi_z: raised 0.30→0.35 (with flow) / 0.50→0.55 (no flow)
               sign consistent on 10/13 tickers at 1d — most reliable OHLCV feature
      - vwap_dev: raised 0.10→0.15 — sign consistent 8/13 tickers
      - impact_eff_z: kept small (0.05/0.15)
      - rvol: REMOVED from fixed weights — sign inconsistent on 0/13 tickers at 1d.
              Repurposed as multiplicative amplifier: high volume → amplify signal,
              low volume → dampen signal. Max ±10% effect.
      - liq_abs_z, clv, price_persistence: removed in v4 — IC < 0.03, sign inconsistent

    Step 3 — HMM state correction (proportional, not flat):
      hmm_boost = direction_sign × hmm_strength × 0.15
      where hmm_strength ∈ [0,1] = |state inst_mean| / max(|labeled state inst_means|)
      Neutral states → boost = 0. States that didn't pass t-test → labeled neutral.

    Step 4 — Final score and signal:
      final_score = clip(raw_score + hmm_boost, -1, +1)

      final_score > +0.35 → strong_accumulation
      final_score > +0.10 → accumulation
      final_score in [-0.10, +0.10] → neutral
      final_score < -0.10 → distribution
      final_score < -0.35 → strong_distribution

    confidence = abs(final_score) × 100%
    """
    df = df.copy()

    def norm_clip(s):
        mu, sd = s.rolling(50).mean(), s.rolling(50).std().replace(0, np.nan)
        return ((s - mu) / sd).clip(-1, 1).fillna(0)

    s_ofi    = norm_clip(df["ofi_z"])
    s_vwap   = norm_clip(df["vwap_dev"])
    s_impact = -norm_clip(df["impact_eff_z"])  # low impact = passive fill = bullish

    # ── rvol as multiplicative amplifier (not directional feature)
    # IC sign is 0/13 consistent on 1d data — rvol has no stable direction.
    # High volume amplifies other features; low volume dampens them.
    rvol_raw   = df["rvol"].clip(0, 5).fillna(1.0)
    rvol_boost = ((rvol_raw - 1) * RVOL_BOOST_SCALE).clip(-RVOL_BOOST_CLIP, RVOL_BOOST_CLIP)

    # ── Cluster-based weights (v4) — checks WITH-FLOW cluster map first
    # when flow is present, falls back to flat global WEIGHTS_WITH_FLOW
    # for tickers not yet covered by the with-flow clustering (19 tickers
    # validated as of 2026-06-30 — see WITH_FLOW_CLUSTER_WEIGHTS comment).
    has_flow      = "inst_net_z" in df.columns and df["inst_net_z"].abs().sum() > 0
    cluster       = TICKER_CLUSTER_MAP.get(ticker) if ticker else None
    flow_cluster  = TICKER_CLUSTER_MAP_WITH_FLOW.get(ticker) if ticker else None

    if has_flow and flow_cluster and flow_cluster in WITH_FLOW_CLUSTER_WEIGHTS:
        fw = WITH_FLOW_CLUSTER_WEIGHTS[flow_cluster]
        s_flow   = norm_clip(df["inst_net_z"])
        weights  = {"flow": fw["flow"], "ofi": fw["ofi"], "vwap": fw["vwap"], "impact": fw["impact"]}
        rvol_amp_scale = fw["rvol_amp_scale"]
        overall_scale  = 1.0
        coverage = (df["inst_net_z"].abs() > 0.01).mean()
        print(f"[v4] Ticker {ticker} -> with-flow cluster {flow_cluster} "
              f"(main-flow coverage: {coverage:.1%}) — using validated with-flow cluster weights")
    elif has_flow:
        # Ticker has flow data but isn't in the validated with-flow cluster
        # map yet (only 19 tickers covered so far) — fall back to the flat
        # global weights rather than guessing via soft assignment, since
        # no soft-assignment system has been built for the 5-dim with-flow
        # space (the existing CLUSTER_CENTROIDS soft assignment is 4-dim,
        # no-flow only).
        s_flow   = norm_clip(df["inst_net_z"])
        weights  = WEIGHTS_WITH_FLOW
        rvol_amp_scale = 1.0
        overall_scale  = 1.0
        coverage = (df["inst_net_z"].abs() > 0.01).mean()
        print(f"[v4] Using flow-weighted scoring (main-flow coverage: {coverage:.1%})")
        if ticker:
            print(f"[v4] Ticker {ticker} not in TICKER_CLUSTER_MAP_WITH_FLOW "
                  f"(only 19 tickers validated so far) — using global WEIGHTS_WITH_FLOW")
    elif cluster and cluster in CLUSTER_WEIGHTS:
        cw = CLUSTER_WEIGHTS[cluster]
        s_flow   = pd.Series(0.0, index=df.index)
        weights  = {"flow": 0.0, "ofi": cw["ofi"], "vwap": cw["vwap"], "impact": cw["impact"]}
        rvol_amp_scale = cw["rvol_amp_scale"]
        overall_scale  = cw["overall_scale"]
        print(f"[v4] Ticker {ticker} -> cluster {cluster} — using IC-pattern cluster weights")
    elif ticker:
        # Unknown ticker (not in TICKER_CLUSTER_MAP) — use soft cluster
        # assignment instead of falling back to a flat global default.
        # Computes this ticker's own IC vector from the data we already
        # have, then blends cluster weights via softmax distance.
        s_flow = pd.Series(0.0, index=df.index)
        try:
            ic_vec = {}
            for feat in ["ofi_z", "rvol", "vwap_dev", "impact_eff_z"]:
                fwd_ret = df["close"].pct_change(6).shift(-6)
                sub = pd.concat([df[feat], fwd_ret], axis=1).dropna()
                if len(sub) >= 30:
                    ic_vec[feat] = abs(sub.iloc[:, 0].corr(sub.iloc[:, 1], method="spearman"))
                else:
                    ic_vec[feat] = 0.0
            blend = get_soft_cluster_weights(ic_vec)
            weights = {"flow": 0.0, "ofi": blend["ofi"], "vwap": blend["vwap"],
                       "impact": blend["impact"]}
            rvol_amp_scale = blend["rvol_amp_scale"]
            overall_scale  = blend["overall_scale"]
            mem_str = ", ".join(f"{c}={m:.0%}" for c, m in blend["_membership"].items())
            print(f"[v4] Ticker {ticker} not in TICKER_CLUSTER_MAP — "
                  f"soft cluster assignment: {mem_str}")
        except Exception as e:
            print(f"[v4] Soft cluster assignment failed for {ticker} ({e}) — "
                  f"using global WEIGHTS_NO_FLOW")
            weights = WEIGHTS_NO_FLOW
            rvol_amp_scale = 1.0
            overall_scale  = 1.0
    else:
        s_flow   = pd.Series(0.0, index=df.index)
        weights  = WEIGHTS_NO_FLOW
        rvol_amp_scale = 1.0
        overall_scale  = 1.0
        print(f"[v4] No ticker provided — using global WEIGHTS_NO_FLOW")

    print(f"[v4] Weights: " + " | ".join(f"{k}={v:.2f}" for k, v in weights.items() if v > 0)
          + f" | rvol_amp_scale={rvol_amp_scale:.2f} | overall_scale={overall_scale:.2f}")

    base_score = (
        weights["flow"]   * s_flow   +
        weights["ofi"]    * s_ofi    +
        weights["vwap"]   * s_vwap   +
        weights["impact"] * s_impact
    )
    scaled_rvol_boost = rvol_boost * rvol_amp_scale
    df["raw_score"] = (base_score * (1 + scaled_rvol_boost) * overall_scale).clip(-1, 1)

    # HMM state correction — proportional to how statistically strong the
    # labeled state actually is (see fit_hmm's hmm_strength), not a flat
    # ±0.15 regardless of whether the state's direction was even real.
    # Max boost magnitude kept at 0.15 (same ceiling as before) so this is
    # a strictly more conservative version of the old behavior, not a
    # different scale.
    MAX_HMM_BOOST = 0.15
    direction_sign = df["hmm_label"].map({"accumulation": 1, "distribution": -1, "neutral": 0}).fillna(0)
    hmm_strength = df["hmm_strength"] if "hmm_strength" in df.columns else pd.Series(0.0, index=df.index)
    df["hmm_boost"]   = direction_sign * hmm_strength * MAX_HMM_BOOST
    df["final_score"] = (df["raw_score"] + df["hmm_boost"]).clip(-1, 1)

    # Signal classification
    df["signal"] = pd.cut(
        df["final_score"],
        bins=[-1.01, -0.35, -0.10, 0.10, 0.35, 1.01],
        labels=["strong_distribution", "distribution", "neutral",
                "accumulation", "strong_accumulation"]
    )

    df["confidence"] = (df["final_score"].abs() * 100).round(1)

    # Estimated institutional participation (heuristic)
    # v4: liq_abs_z removed, replaced with inverted impact_eff_z
    df["est_inst_participation"] = (
        (df["rvol"].clip(0, 3) / 3 * 0.5 +
         (-df["impact_eff_z"]).clip(0, 2) / 2 * 0.3 +
         s_ofi.abs() * 0.2) * 25
    ).clip(0, 25).round(2)

    direction = np.where(df["signal"].isin(["accumulation","strong_accumulation"]),  1,
                np.where(df["signal"].isin(["distribution","strong_distribution"]), -1, 0))
    df["delta_inventory"]      = direction * df["est_inst_participation"] / 100 * df["volume"]
    df["cumulative_inventory"] = df["delta_inventory"].cumsum()

    return df


# ══════════════════════════════════════════════
# 5. Output
# ══════════════════════════════════════════════

def save_output(df: pd.DataFrame, ticker: str, interval: str) -> str:
    cols = [
        "datetime", "timestamp",
        "open", "high", "low", "close", "volume",
        "vwap_roll", "vwap_dev",
        "ofi_z", "rvol", "impact_eff_z",
        "bvc_buy_frac",
        "hmm_state", "hmm_label",
        "raw_score", "hmm_boost", "final_score",
        "signal", "confidence", "oos",
        "est_inst_participation", "delta_inventory", "cumulative_inventory",
    ]
    if "inst_net" in df.columns:
        cols += ["inst_net", "xl_net", "l_net", "inst_net_z"]

    out   = df[[c for c in cols if c in df.columns]].copy().dropna(subset=["signal"])
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{ticker}_{interval}_{ts}_v4_signals.csv"
    fpath = os.path.join(OUTPUT_DIR, fname)
    out.to_csv(fpath, index=False)
    return fpath


def print_summary(df: pd.DataFrame, ticker: str, interval: str):
    valid  = df.dropna(subset=["signal"])
    counts = valid["signal"].value_counts()

    print(f"\n{'='*55}")
    print(f"  {ticker} | {interval} | {len(valid)} bars [v4]")
    print(f"{'='*55}")
    print("\n[Signal Distribution]")
    for sig, cnt in counts.items():
        pct = cnt / len(valid) * 100
        bar = "█" * int(pct / 3)
        print(f"  {sig:<25} {cnt:>4} bars  {pct:5.1f}%  {bar}")

    last = valid.iloc[-1]
    print(f"\n[Latest]")
    print(f"  Time        : {last['datetime']}")
    print(f"  Close       : ${last['close']:.2f}")
    print(f"  Signal      : {last['signal']}")
    print(f"  Confidence  : {last['confidence']:.1f}%")
    print(f"  HMM State   : {last['hmm_label']}")
    print(f"  Final Score : {last['final_score']:+.3f}")
    print(f"  Inst. Part. : ~{last['est_inst_participation']:.1f}%")

    acc  = valid[valid["signal"].isin(["accumulation","strong_accumulation"])]
    dist = valid[valid["signal"].isin(["distribution","strong_distribution"])]
    if len(acc):
        print(f"\n  Avg acc confidence  : {acc['confidence'].mean():.1f}%")
    if len(dist):
        print(f"  Avg dist confidence : {dist['confidence'].mean():.1f}%")
    print(f"{'='*55}\n")


# ══════════════════════════════════════════════
# 6. Main
# ══════════════════════════════════════════════

def _merged_cache_path(ticker: str, interval: str, from_date, to_date) -> str:
    safe_from = from_date or "2025-07-01"
    safe_to   = to_date or "latest"
    return os.path.join(RAW_CACHE_DIR, f"{ticker}_{interval}_{safe_from}_{safe_to}.csv")


def load_merged_cached(ticker, interval, limit, from_date=None, to_date=None,
                        use_cache=True, refresh=False):
    """
    Cache wrapper around the klines + compute_features + main-flow merge
    pipeline. Independent cache from ic_analysis_with_flow.py's
    ic_flow_cache/ — kept separate on purpose: sharing one cache dir
    between two scripts would couple their data formats together (any
    future change to compute_features()/merge_flow() in one script could
    silently break the other reading a cached file it didn't produce),
    and it wouldn't actually save fetches for genuinely new tickers
    anyway — only ever helps when both scripts happen to touch the exact
    same ticker, which isn't reliably the case as new tickers get added
    to either workflow over time.

    Returns (df, has_flow).
    """
    cache_file = _merged_cache_path(ticker, interval, from_date, to_date)

    if use_cache and not refresh and os.path.exists(cache_file):
        print(f"[CACHE HIT] {ticker} {interval}: {cache_file}")
        df = pd.read_csv(cache_file, parse_dates=["datetime"])
        has_flow = "inst_net_z" in df.columns and df["inst_net_z"].abs().sum() > 0
        return df, has_flow

    kl = load_klines(ticker, interval, limit, from_date=from_date, to_date=to_date)
    if kl is None or len(kl) < 50:
        return None, False

    fl = load_main_flow(ticker, interval, limit, from_date=from_date, to_date=to_date)

    df = compute_features(kl)
    has_flow = fl is not None
    if has_flow:
        df = merge_flow(df, fl)

    if use_cache:
        df.to_csv(cache_file, index=False)
        print(f"[CACHED] {ticker} {interval} -> {cache_file}")

    return df, has_flow


def main():
    parser = argparse.ArgumentParser(description="Institutional Flow Signal Generator v4")
    parser.add_argument("--ticker",     default="AAPL")
    parser.add_argument("--interval",   default="1d")
    parser.add_argument("--limit",      default=300, type=int)
    parser.add_argument("--hmm-states", default=3,   type=int)
    parser.add_argument("--from-date",  default=None)
    parser.add_argument("--to-date",    default=None)
    parser.add_argument("--flow-from",  default=None)
    parser.add_argument("--train-end",  default=None,
                        help="Out-of-sample split date (e.g. 2025-06-30). "
                             "HMM trained on data up to this date only, "
                             "then predicts on full dataset. "
                             "13F validation should use only post-train-end quarters.")
    parser.add_argument("--refresh-data", action="store_true",
                        help="忽略本地缓存，强制重新拉取 klines/main-flow")
    parser.add_argument("--no-cache",     action="store_true",
                        help="完全不使用缓存（既不读也不写）")
    args = parser.parse_args()

    ticker   = args.ticker.upper()
    interval = args.interval

    mode = "OOS" if args.train_end else "FULL"
    print(f"\n[START] {ticker} | {interval} | v4 ({mode}) | sqrt impact + evidence-based weights")
    if args.train_end:
        print(f"[OOS]   Train: ≤{args.train_end} | Validate: >{args.train_end}")
    print("-" * 50)

    df, has_flow = load_merged_cached(ticker, interval, args.limit,
                            from_date=args.from_date, to_date=args.to_date,
                            use_cache=not args.no_cache, refresh=args.refresh_data)
    _         = load_large_trades(ticker, limit=200)

    if df is None:
        print(f"[FATAL] Could not load data for {ticker}")
        return None

    print("[Training HMM (fixed 3 states)...]")
    df = fit_hmm(df, n_states=args.hmm_states, train_end=args.train_end)

    print("[Scoring signals (fixed adaptive weights)...]")
    df = compute_signal(df, ticker=ticker)

    fpath = save_output(df, ticker, interval)
    print_summary(df, ticker, interval)

    if args.train_end:
        oos_df = df[df["datetime"] > pd.Timestamp(args.train_end)]
        print(f"[OOS] Out-of-sample period: {len(oos_df)} bars")
        print(f"[OOS] For 13F validation, use quarters after {args.train_end}")

    print(f"[SAVED] {fpath}\n")
    return fpath


if __name__ == "__main__":
    main()
