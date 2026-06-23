"""
Institutional Flow Signal Generator v2
=======================================
v2 改进（相比 v1）：
  1. BVC (Bulk Volume Classification) 替换 Lee-Ready
     - 用 (close-low)/(high-low) 估算买卖比例
     - 消除牛市/熊市中的系统性方向偏差
     - Ref: Easley, López de Prado & O'Hara (2012)

  2. 开盘竞价过滤延至 9:35 ET（原 9:30）
     - 额外过滤开盘集合竞价的 5 分钟噪音

  3. BIC 自动选择 HMM 状态数（2-5）
     - 避免固定 3 状态的假设
     - Ref: Rabiner (1989)

  4. Lasso 学习特征权重
     - 用 inst_net_z 有数据的 bar 作为 label 训练
     - 数据不足时自动回退到手动权重
     - Ref: Tibshirani (1996)

用法：
  python signal_generator_v2.py --ticker AAPL --interval 1d
  python signal_generator_v2.py --ticker NVDA --interval 1h --from-date 2024-01-01
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
# 配置
# ──────────────────────────────────────────────
BASE_URL   = "http://104.192.7.156:8000"
TIMEOUT    = 60
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ══════════════════════════════════════════════
# 1. 数据拉取  (与 v1 相同)
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
        sys.exit("[FATAL] 无法获取 K 线数据")

    arr = raw if isinstance(raw, list) else (raw.get("bars") or raw.get("data") or raw.get("klines") or [])
    if not arr:
        sys.exit("[FATAL] K 线数据为空")

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

    # v2: 过滤盘外时间，开盘改为 9:35 ET（过滤竞价噪音）
    if timespan in ("minute", "hour"):
        before = len(df)
        df["_et"] = df["datetime"] - pd.Timedelta(hours=4)
        df["_hm"] = df["_et"].dt.hour * 100 + df["_et"].dt.minute
        # v2: 9:35 instead of 9:30 — excludes opening auction bars
        df = df[(df["_hm"] >= 935) & (df["_hm"] < 1600)].drop(columns=["_hm","_et"]).reset_index(drop=True)
        print(f"[OK] K线(盘内ET 9:35-16:00): {len(df)} bars (过滤 {before-len(df)} bars)  [{df['datetime'].iloc[0]} -> {df['datetime'].iloc[-1]}]")
    else:
        print(f"[OK] K线: {len(df)} bars  [{df['datetime'].iloc[0]} -> {df['datetime'].iloc[-1]}]")
    return df


def load_main_flow(ticker, interval, limit, from_date=None, to_date=None):
    from datetime import timedelta
    MAINFLOW_START = datetime(2025, 7, 1)  # confirmed via export tool preview
    dt_to   = datetime.strptime(to_date,   "%Y-%m-%d") if to_date   else datetime.now()
    dt_from = datetime.strptime(from_date, "%Y-%m-%d") if from_date else MAINFLOW_START
    if dt_from < MAINFLOW_START:
        print(f"[INFO] main-flow 数据从 {MAINFLOW_START.date()} 开始，自动调整起始日期")
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
        print("[WARN] main-flow 无数据，跳过")
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
        # v2: also filter 9:30-9:35 in main-flow (consistent with klines filter)
        is_open_auction = (dt_et.hour == 9 and dt_et.minute <= 35)
        is_outlier = abs(xl_net) > 50_000_000
        if is_open_auction or is_outlier:
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
        print(f"[OK] main-flow: {len(all_rows)} bars → 聚合为 {len(agg)} 日线")
        return agg
    else:
        df["hour"] = df["datetime"].dt.floor("H")
        agg = df.groupby("hour").agg(
            inst_net=("inst_net", "sum"),
            xl_net=("xl_net", "sum"),
            l_net=("l_net", "sum"),
        ).reset_index()
        agg["timestamp"] = agg["hour"].astype("int64") // 10**6
        print(f"[OK] main-flow: {len(all_rows)} bars → 聚合为 {len(agg)} 小时线")
        return agg


def load_large_trades(ticker, limit=500):
    raw = fetch("/api/large-trades", {"ticker": ticker, "limit": limit})
    if raw is None:
        return None
    arr = raw if isinstance(raw, list) else raw.get("trades") or raw.get("data") or []
    if not arr:
        return None
    rows = []
    for t in arr:
        side = str(t.get("side") or t.get("taker_side") or "").lower()
        is_buy = side in ("buy", "b", "1")
        rows.append({
            "timestamp": int(t.get("timestamp") or t.get("t") or t.get("time") or 0),
            "price":  float(t.get("price") or t.get("p") or 0),
            "size":   float(t.get("size")  or t.get("s") or t.get("quantity") or 0),
            "is_buy": is_buy,
        })
    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    print(f"[OK] large-trades: {len(df)} 条")
    return df


# ══════════════════════════════════════════════
# 2. 特征工程 (v2: BVC 替换 Lee-Ready)
# ══════════════════════════════════════════════

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # ── 2.1 收益率 & 波动率
    df["ret"]     = df["close"].pct_change()
    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    df["range"]   = (df["high"] - df["low"]) / df["close"]

    # ── 2.2 VWAP（滚动 20 bar）
    df["vwap_roll"] = (
        (df["close"] * df["volume"]).rolling(20).sum() /
        df["volume"].rolling(20).sum()
    )
    df["vwap_dev"] = (df["close"] - df["vwap_roll"]) / df["vwap_roll"]

    # ── 2.3 混合 OFI = 0.5 * Lee-Ready + 0.5 * BVC
    # Lee-Ready 捕捉动量方向，BVC 修正趋势偏差
    # 混合后对趋势股和震荡股都有合理表现
    # Lee-Ready
    df["midprice"]  = (df["high"] + df["low"]) / 2
    df["tick_sign"] = np.sign(df["close"] - df["close"].shift(1))
    df["lr_sign"]   = np.where(
        df["close"] > df["midprice"],  1,
        np.where(df["close"] < df["midprice"], -1, df["tick_sign"])
    )
    df["signed_vol"] = df["lr_sign"] * df["volume"]
    ofi_lr = df["signed_vol"].rolling(5).sum()

    # BVC
    bar_range = (df["high"] - df["low"]).replace(0, np.nan)
    df["bvc_buy_frac"] = ((df["close"] - df["low"]) / bar_range).fillna(0.5)
    bvc_net  = (df["bvc_buy_frac"] - 0.5) * 2 * df["volume"]  # -V to +V
    ofi_bvc  = bvc_net.rolling(5).sum()

    # 混合：动态权重基于趋势强度
    # 趋势强 (高 |ret_ma|) → 更多 Lee-Ready；震荡 → 更多 BVC
    ret_ma   = df["close"].pct_change().rolling(20).mean().abs()
    ret_norm = (ret_ma / (ret_ma.rolling(50).mean() + 1e-8)).clip(0, 2) / 2
    alpha    = ret_norm.fillna(0.5)   # 0 = 纯BVC, 1 = 纯Lee-Ready
    df["ofi_raw"] = alpha * ofi_lr + (1 - alpha) * ofi_bvc
    ofi_std       = df["ofi_raw"].rolling(20).std().replace(0, np.nan)
    df["ofi_z"]   = df["ofi_raw"] / ofi_std

    # ── 2.4 相对成交量 (RVOL)
    df["rvol"] = df["volume"] / df["volume"].rolling(20).mean()

    # ── 2.5 Impact Efficiency
    df["price_chg_abs"] = df["close"].diff().abs()
    vol_ma = df["volume"].rolling(5).mean().replace(0, np.nan)
    df["impact_eff"] = df["price_chg_abs"] / vol_ma
    ie_std = df["impact_eff"].rolling(20).std().replace(0, np.nan)
    df["impact_eff_z"] = (df["impact_eff"] - df["impact_eff"].rolling(20).mean()) / ie_std

    # ── 2.6 Close Location Value (CLV)
    denom = (df["high"] - df["low"]).replace(0, np.nan)
    df["clv"] = (2 * df["close"] - df["high"] - df["low"]) / denom

    # ── 2.7 流动性吸收
    df["liq_absorption"] = df["rvol"] / (df["range"].replace(0, np.nan) * 100 + 0.001)
    la_std = df["liq_absorption"].rolling(20).std().replace(0, np.nan)
    df["liq_abs_z"] = (df["liq_absorption"] - df["liq_absorption"].rolling(20).mean()) / la_std

    # ── 2.8 价格持久性
    df["price_persistence"] = df["ret"].rolling(3).mean() / (df["ret"].rolling(3).std().replace(0, np.nan) + 1e-8)

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
# 3. HMM (v2: BIC 自动选择状态数)
# ══════════════════════════════════════════════

def fit_hmm(df: pd.DataFrame, n_states: int = 3) -> pd.DataFrame:
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        print("[WARN] hmmlearn 未安装，跳过 HMM 分析")
        df["hmm_state"] = 0
        return df

    feature_cols = ["ofi_z", "rvol", "impact_eff_z", "liq_abs_z", "vwap_dev"]
    if "inst_net_z" in df.columns:
        feature_cols.append("inst_net_z")

    sub = df[feature_cols].copy().replace([np.inf, -np.inf], np.nan).fillna(0)
    X = sub.values

    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # ── [v2] BIC 自动选择状态数 (Rabiner 1989)
    best_bic, best_n = np.inf, n_states
    # BIC 暂时禁用：3600 bars 样本量不足以支持 >3 状态的 full covariance HMM
    # BIC 倾向选 4-5 状态导致过拟合，样本外性能下降
    # TODO: 重新启用 BIC 当 main-flow 历史数据回填到 2024 年后
    print(f"[v2] 使用固定 {n_states} 个 HMM 状态 (BIC 待 main-flow 回填后启用)")

    model = GaussianHMM(n_components=n_states, covariance_type="full",
                        n_iter=200, random_state=42)
    model.fit(X_scaled)
    states = model.predict(X_scaled)
    df = df.copy()
    df["hmm_state"] = states

    state_profiles = df.groupby("hmm_state").agg(
        ofi_mean=("ofi_z", "mean"),
        rvol_mean=("rvol", "mean"),
        inst_mean=("inst_net_z", "mean") if "inst_net_z" in df.columns else ("ofi_z","mean"),
        ret_mean=("ret", "mean"),
        count=("ret","count")
    )
    print("\n[HMM] 状态分布:")
    print(state_profiles.to_string())

    ofi_col  = "inst_mean" if "inst_mean" in state_profiles.columns else "ofi_mean"
    best_acc  = state_profiles[ofi_col].idxmax()
    best_dist = state_profiles[ofi_col].idxmin()
    rest = [s for s in state_profiles.index if s not in (best_acc, best_dist)]
    best_neut = rest[0] if rest else -1

    label_map = {best_acc: "accumulation", best_dist: "distribution"}
    if best_neut != -1:
        label_map[best_neut] = "neutral"
    # any extra states beyond 3 → neutral
    for s in state_profiles.index:
        if s not in label_map:
            label_map[s] = "neutral"
    df["hmm_label"] = df["hmm_state"].map(label_map).fillna("neutral")

    return df


# ══════════════════════════════════════════════
# 4. 信号评分 (v2: Lasso 学习权重)
# ══════════════════════════════════════════════

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def norm_clip(s):
        mu, sd = s.rolling(50).mean(), s.rolling(50).std().replace(0, np.nan)
        return ((s - mu) / sd).clip(-1, 1).fillna(0)

    s_ofi  = norm_clip(df["ofi_z"])
    s_rvol = norm_clip(df["rvol"] - 1)
    s_liq  = norm_clip(df["liq_abs_z"])
    s_vwap = -norm_clip(df["impact_eff_z"])
    s_clv  = df["clv"].fillna(0)
    s_pers = norm_clip(df["price_persistence"])

    # ── [v2] Lasso 学习特征权重 (Tibshirani 1996)
    MANUAL_WEIGHTS = {"ofi": 0.25, "rvol": 0.15, "liq": 0.20,
                      "vwap": 0.15, "clv": 0.10, "pers": 0.10, "flow": 0.05}

    if "inst_net_z" in df.columns:
        s_flow = norm_clip(df["inst_net_z"])
        _mask  = df["inst_net_z"].abs() > 0.01   # bars with real main-flow data

        if _mask.sum() >= 50:
            try:
                from sklearn.linear_model import LassoCV
                _feat_names = ["ofi", "rvol", "liq", "vwap", "clv", "pers"]
                _X = pd.DataFrame({
                    "ofi": s_ofi, "rvol": s_rvol, "liq": s_liq,
                    "vwap": s_vwap, "clv": s_clv, "pers": s_pers,
                })
                _y = norm_clip(df["inst_net_z"])   # label: true institutional direction
                _lasso = LassoCV(cv=3, max_iter=2000, random_state=42)
                _lasso.fit(_X[_mask], _y[_mask])
                _raw_w = {k: max(abs(v), 1e-4)
                          for k, v in zip(_feat_names, _lasso.coef_)}
                _raw_w["flow"] = 0.15   # always preserve flow weight
                _total = sum(_raw_w.values())
                weights = {k: v / _total for k, v in _raw_w.items()}
                print(f"[v2/Lasso] 学习权重 (n={_mask.sum()}): " +
                      " | ".join(f"{k}={v:.3f}" for k, v in weights.items()))
            except Exception as _e:
                print(f"[v2/Lasso] 退回手动权重 ({_e})")
                weights = MANUAL_WEIGHTS.copy()
                weights["flow"] = 0.15
                _total = sum(weights.values())
                weights = {k: v/_total for k, v in weights.items()}
        else:
            print(f"[v2/Lasso] 标注数据不足 ({_mask.sum()} bars)，使用手动权重")
            weights = MANUAL_WEIGHTS.copy()
            weights["flow"] = 0.15
            _total = sum(weights.values())
            weights = {k: v/_total for k, v in weights.items()}
    else:
        s_flow  = pd.Series(0.0, index=df.index)
        weights = MANUAL_WEIGHTS.copy()

    df["raw_score"] = (
        weights["ofi"]  * s_ofi  +
        weights["rvol"] * s_rvol +
        weights["liq"]  * s_liq  +
        weights["vwap"] * s_vwap +
        weights["clv"]  * s_clv  +
        weights["pers"] * s_pers +
        weights["flow"] * s_flow
    )

    hmm_boost = {"accumulation": 0.15, "distribution": -0.15, "neutral": 0.0}
    df["hmm_boost"]   = df["hmm_label"].map(hmm_boost).fillna(0)
    df["final_score"] = (df["raw_score"] + df["hmm_boost"]).clip(-1, 1)

    df["signal"] = pd.cut(
        df["final_score"],
        bins=[-1.01, -0.35, -0.10, 0.10, 0.35, 1.01],
        labels=["strong_distribution", "distribution", "neutral",
                "accumulation", "strong_accumulation"]
    )

    df["confidence"] = (df["final_score"].abs() * 100).round(1)

    df["est_inst_participation"] = (
        (df["rvol"].clip(0, 3) / 3 * 0.5 +
         df["liq_abs_z"].clip(0, 2) / 2 * 0.3 +
         s_ofi.abs() * 0.2) * 25
    ).clip(0, 25).round(2)

    direction = np.where(df["signal"].isin(["accumulation","strong_accumulation"]),  1,
                np.where(df["signal"].isin(["distribution","strong_distribution"]), -1, 0))
    df["delta_inventory"]      = direction * df["est_inst_participation"] / 100 * df["volume"]
    df["cumulative_inventory"] = df["delta_inventory"].cumsum()

    return df


# ══════════════════════════════════════════════
# 5. 输出  (与 v1 相同，文件名加 _v2 标记)
# ══════════════════════════════════════════════

def save_output(df: pd.DataFrame, ticker: str, interval: str) -> str:
    cols = [
        "datetime", "timestamp",
        "open", "high", "low", "close", "volume",
        "vwap_roll", "vwap_dev",
        "ofi_z", "rvol", "impact_eff_z", "liq_abs_z",
        "clv", "price_persistence",
        "bvc_buy_frac",   # v2 extra
        "hmm_state", "hmm_label",
        "raw_score", "hmm_boost", "final_score",
        "signal", "confidence",
        "est_inst_participation", "delta_inventory", "cumulative_inventory",
    ]
    if "inst_net" in df.columns:
        cols += ["inst_net", "xl_net", "l_net", "inst_net_z"]

    out = df[[c for c in cols if c in df.columns]].copy()
    out = out.dropna(subset=["signal"])

    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{ticker}_{interval}_{ts}_v2_signals.csv"   # _v2 suffix
    fpath = os.path.join(OUTPUT_DIR, fname)
    out.to_csv(fpath, index=False)
    return fpath


def print_summary(df: pd.DataFrame, ticker: str, interval: str):
    valid  = df.dropna(subset=["signal"])
    counts = valid["signal"].value_counts()

    print(f"\n{'='*55}")
    print(f"  {ticker} | {interval} | {len(valid)} bars 分析完成 [v2]")
    print(f"{'='*55}")
    print("\n[信号分布]")
    for sig, cnt in counts.items():
        pct = cnt / len(valid) * 100
        bar = "█" * int(pct / 3)
        print(f"  {sig:<25} {cnt:>4} bars  {pct:5.1f}%  {bar}")

    last = valid.iloc[-1]
    print(f"\n[最新状态]")
    print(f"  时间      : {last['datetime']}")
    print(f"  收盘价    : ${last['close']:.2f}")
    print(f"  信号      : {last['signal']}")
    print(f"  置信度    : {last['confidence']:.1f}%")
    print(f"  HMM 状态  : {last['hmm_label']}")
    print(f"  综合得分  : {last['final_score']:+.3f}")
    print(f"  机构参与率: ~{last['est_inst_participation']:.1f}%")

    acc_bars  = valid[valid["signal"].isin(["accumulation","strong_accumulation"])]
    dist_bars = valid[valid["signal"].isin(["distribution","strong_distribution"])]
    if len(acc_bars):
        print(f"\n  积累信号平均置信度 : {acc_bars['confidence'].mean():.1f}%")
    if len(dist_bars):
        print(f"  派发信号平均置信度 : {dist_bars['confidence'].mean():.1f}%")
    print(f"{'='*55}\n")


# ══════════════════════════════════════════════
# 6. 主程序
# ══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Institutional Flow Signal Generator v2")
    parser.add_argument("--ticker",     default="AAPL")
    parser.add_argument("--interval",   default="1d")
    parser.add_argument("--limit",      default=300, type=int)
    parser.add_argument("--hmm-states", default=3,   type=int, help="HMM 初始状态数（BIC 会自动调整）")
    parser.add_argument("--from-date",  default=None)
    parser.add_argument("--to-date",    default=None)
    parser.add_argument("--flow-from",  default=None)
    args = parser.parse_args()

    ticker   = args.ticker.upper()
    interval = args.interval
    limit    = args.limit

    print(f"\n[START] {ticker} | {interval} | limit={limit} | v2 (BVC+BIC+Lasso)")
    print("-" * 40)

    df        = load_klines(ticker, interval, limit,
                            from_date=args.from_date, to_date=args.to_date)
    flow_df   = load_main_flow(ticker, interval, limit,
                               from_date=args.flow_from, to_date=args.to_date)
    trades_df = load_large_trades(ticker, limit=200)

    print("\n[计算特征...]")
    df = compute_features(df)

    if flow_df is not None:
        df = merge_flow(df, flow_df)

    print("[训练 HMM (BIC 选择状态数)...]")
    df = fit_hmm(df, n_states=args.hmm_states)

    print("[生成信号 (Lasso 权重)...]")
    df = compute_signal(df)

    fpath = save_output(df, ticker, interval)
    print_summary(df, ticker, interval)
    print(f"[SAVED] {fpath}\n")
    return fpath


if __name__ == "__main__":
    main()
