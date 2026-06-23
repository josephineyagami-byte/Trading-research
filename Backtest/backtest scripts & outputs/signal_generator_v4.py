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
import requests
from scipy import stats

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
BASE_URL   = "http://104.192.7.156:8000"
TIMEOUT    = 60
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Fixed adaptive weights (no training needed)
# Rationale: inst_net_z is the only feature with true directional information.
# When available, it dominates. OHLCV features provide supporting context.
#
# v4 evidence-based weights — removed liq/clv/pers, raised ofi 0.15->0.30
# With main-flow:    flow=0.45 | ofi=0.30 | rvol=0.10 | vwap=0.10 | impact=0.05
# Without main-flow: flow=0.00 | ofi=0.50 | rvol=0.20 | vwap=0.20 | impact=0.10
WEIGHTS_WITH_FLOW = {
    "flow": 0.45, "ofi": 0.30, "rvol": 0.10,
    "vwap": 0.10, "impact": 0.05
}
WEIGHTS_NO_FLOW = {
    "flow": 0.00, "ofi": 0.50, "rvol": 0.20,
    "vwap": 0.20, "impact": 0.10
}


# ══════════════════════════════════════════════
# 1. Data Fetching
# ══════════════════════════════════════════════

def fetch(path: str, params: dict = None):
    url = BASE_URL + path
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] fetch {path}: {e}")
        return None


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

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")

    # Filter to market hours: 9:35–16:00 ET (9:30–9:35 excluded = opening auction noise)
    if timespan in ("minute", "hour"):
        before = len(df)
        df["_et"] = df["datetime"] - pd.Timedelta(hours=4)
        df["_hm"] = df["_et"].dt.hour * 100 + df["_et"].dt.minute
        df = df[(df["_hm"] >= 935) & (df["_hm"] < 1600)].drop(columns=["_hm","_et"]).reset_index(drop=True)
        print(f"[OK] Klines (9:35–16:00 ET): {len(df)} bars (removed {before-len(df)})  "
              f"[{df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]}]")
    else:
        print(f"[OK] Klines: {len(df)} bars  [{df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]}]")
    return df


def load_main_flow(ticker, interval, limit, from_date=None, to_date=None):
    from datetime import timedelta
    MAINFLOW_START = datetime(2025, 7, 1)  # confirmed via export tool preview
    dt_to   = datetime.strptime(to_date,   "%Y-%m-%d") if to_date   else datetime.now()
    dt_from = datetime.strptime(from_date, "%Y-%m-%d") if from_date else MAINFLOW_START
    if dt_from < MAINFLOW_START:
        print(f"[INFO] main-flow starts {MAINFLOW_START.date()}, adjusting from-date")
        dt_from = MAINFLOW_START

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
        dt_utc = pd.Timestamp(int(t), unit="ms")
        dt_et  = dt_utc - pd.Timedelta(hours=4)
        # Filter opening auction (9:30–9:35 ET) and outliers
        is_auction = (dt_et.hour == 9 and dt_et.minute <= 35)
        is_outlier = abs(xl_net) > 50_000_000
        if is_auction or is_outlier:
            continue
        rows.append({"timestamp": int(t), "xl_net": xl_net,
                     "l_net": l_net, "m_net": m_net, "s_net": s_net})

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
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
    sqrt_impact = df["price_chg_abs"] / (sigma * np.sqrt(part_rate) + 1e-8)
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

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    Signal scoring formula:

    Step 1 — Normalize each feature to [-1, +1]:
      s_i = clip( (x_i - rolling_50_mean(x_i)) / rolling_50_std(x_i), -1, +1 )

    Step 2 — Weighted sum (fixed adaptive weights, no training):
      With main-flow:    raw_score = 0.50×flow + 0.15×ofi + 0.10×rvol
                                   + 0.10×liq  + 0.10×vwap + 0.03×clv + 0.02×pers
      Without main-flow: raw_score = 0.30×ofi  + 0.20×rvol + 0.20×liq
                                   + 0.15×vwap + 0.10×clv  + 0.05×pers

    Weight rationale:
      - inst_net_z (flow): highest weight — only feature from real tick-level data
      - ofi_z: second — directional OFI, but estimated from OHLCV
      - liq_abs_z, rvol: volume-based signals, less directional bias
      - vwap_dev, clv, pers: price-based, lowest weights (most correlated with trend)

    Step 3 — HMM state correction:
      hmm_boost = +0.15 if state=accumulation
                  -0.15 if state=distribution
                   0.00 if state=neutral

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
    s_rvol   = norm_clip(df["rvol"] - 1)
    s_vwap   = norm_clip(df["vwap_dev"])
    s_impact = -norm_clip(df["impact_eff_z"])  # low impact = passive fill = bullish

    # ── Fixed adaptive weights (v4)
    has_flow = "inst_net_z" in df.columns and df["inst_net_z"].abs().sum() > 0
    if has_flow:
        s_flow  = norm_clip(df["inst_net_z"])
        weights = WEIGHTS_WITH_FLOW
        coverage = (df["inst_net_z"].abs() > 0.01).mean()
        print(f"[v4] Using flow-weighted scoring (main-flow coverage: {coverage:.1%})")
    else:
        s_flow  = pd.Series(0.0, index=df.index)
        weights = WEIGHTS_NO_FLOW
        print(f"[v4] No main-flow data — using OHLCV-only weights")

    print(f"[v4] Weights: " + " | ".join(f"{k}={v:.2f}" for k, v in weights.items() if v > 0))

    df["raw_score"] = (
        weights["flow"]   * s_flow   +
        weights["ofi"]    * s_ofi    +
        weights["rvol"]   * s_rvol   +
        weights["vwap"]   * s_vwap   +
        weights["impact"] * s_impact
    )

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
        "signal", "confidence", "oos", "oos",
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

def main():
    parser = argparse.ArgumentParser(description="Institutional Flow Signal Generator v3")
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
    args = parser.parse_args()

    ticker   = args.ticker.upper()
    interval = args.interval

    mode = "OOS" if args.train_end else "FULL"
    print(f"\n[START] {ticker} | {interval} | v4 ({mode}) | sqrt impact + evidence-based weights")
    if args.train_end:
        print(f"[OOS]   Train: ≤{args.train_end} | Validate: >{args.train_end}")
    print("-" * 50)

    df        = load_klines(ticker, interval, args.limit,
                            from_date=args.from_date, to_date=args.to_date)
    flow_df   = load_main_flow(ticker, interval, args.limit,
                               from_date=args.flow_from, to_date=args.to_date)
    _         = load_large_trades(ticker, limit=200)

    print("\n[Computing features...]")
    df = compute_features(df)

    if flow_df is not None:
        df = merge_flow(df, flow_df)

    print("[Training HMM (fixed 3 states)...]")
    df = fit_hmm(df, n_states=args.hmm_states, train_end=args.train_end)

    print("[Scoring signals (fixed adaptive weights)...]")
    df = compute_signal(df)

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
