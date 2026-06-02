"""
Institutional Flow Signal Generator
=====================================
基于以下方法论生成机构行为信号：
  - Lee-Ready 交易方向分类
  - Volume Bucket 分析
  - VWAP 锚点检测
  - Impact Efficiency
  - 主力资金流 (main-flow API)
  - HMM 元订单状态分割

输出：每根 bar 的机构信号，保存为 CSV，供回测使用。

用法：
  python signal_generator.py --ticker AAPL --interval 1d --limit 200
  python signal_generator.py --ticker TSLA --interval 1h --limit 500
"""

import argparse
import json
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
BASE_URL = "http://104.192.7.156:8000"
TIMEOUT  = 60
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ══════════════════════════════════════════════
# 1. 数据拉取
# ══════════════════════════════════════════════

def fetch(path: str, params: dict = None) -> any:
    url = BASE_URL + path
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] fetch {path}: {e}")
        return None


def load_klines(ticker: str, interval: str, limit: int,
               from_date: str = None, to_date: str = None) -> pd.DataFrame:
    interval_map = {
        "1m":  (1,"minute"), "5m":  (5,"minute"),
        "15m": (15,"minute"),"30m": (30,"minute"),
        "1h":  (1,"hour"),   "4h":  (4,"hour"),
        "1d":  (1,"day"),    "1w":  (1,"week"),
    }
    multiplier, timespan = interval_map.get(interval, (1, "minute"))

    from datetime import datetime, timedelta
    days_per_bar = {"minute": 1/1440, "hour": 1/24, "day": 1, "week": 7}
    date_to   = to_date   if to_date   else datetime.now().strftime("%Y-%m-%d")
    if from_date:
        date_from = from_date
    else:
        delta_days = int(limit * days_per_bar.get(timespan, 1)) + 30
        date_from  = (datetime.now() - timedelta(days=delta_days)).strftime("%Y-%m-%d")

    raw = fetch("/api/klines", {
        "ticker":     ticker,
        "multiplier": multiplier,
        "timespan":   timespan,
        "from":       date_from,
        "to":         date_to,
    })
    if raw is None:
        sys.exit("[FATAL] 无法获取 K 线数据，请检查 API 连接")

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

    print(f"[OK] K线: {len(df)} bars  [{df['datetime'].iloc[0]} -> {df['datetime'].iloc[-1]}]")
    return df


def load_main_flow(ticker: str, interval: str, limit: int,
                  from_date: str = None, to_date: str = None) -> object:
    from datetime import datetime, timedelta
    interval_map = {
        "1m":  (1,"minute"), "5m":  (5,"minute"),
        "15m": (15,"minute"),"30m": (30,"minute"),
        "1h":  (1,"hour"),   "4h":  (4,"hour"),
        "1d":  (1,"day"),    "1w":  (1,"week"),
    }
    multiplier, timespan = interval_map.get(interval, (1, "minute"))
    date_to   = to_date   if to_date   else datetime.now().strftime("%Y-%m-%d")
    date_from = from_date if from_date else (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    raw = fetch("/api/main-flow", {
        "ticker":     ticker,
        "multiplier": multiplier,
        "timespan":   timespan,
        "from":       date_from,
        "to":         date_to,
    })
    if raw is None:
        print("[WARN] main-flow 接口不可用，跳过")
        return None

    arr = raw if isinstance(raw, list) else (raw.get("bars") or raw.get("data") or raw.get("flow") or [])
    if not arr:
        print("[WARN] main-flow 数据为空")
        return None

    rows = []
    for b in arr:
        t = b.get("time") or b.get("t") or b.get("timestamp") or 0
        if "super_buy" in b:
            xl_net = float(b.get("super_buy", 0)) - float(b.get("super_sell", 0))
            l_net  = float(b.get("large_buy",  0)) - float(b.get("large_sell",  0))
            m_net  = float(b.get("mid_buy",    0)) - float(b.get("mid_sell",    0))
            s_net  = float(b.get("small_buy",  0)) - float(b.get("small_sell",  0))
        else:
            g = lambda *ks: next((float(b[k]) for k in ks if b.get(k) is not None), 0.0)
            xl_net = g("super_large_net", "xl_net", "tier1_net")
            l_net  = g("large_net", "l_net", "tier2_net")
            m_net  = g("medium_net", "m_net", "tier3_net")
            s_net  = g("small_net", "s_net", "tier4_net")
        rows.append({"timestamp": int(t), "xl_net": xl_net,
                     "l_net": l_net, "m_net": m_net, "s_net": s_net})

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    df["inst_net"] = df["xl_net"] + df["l_net"]
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["date"]     = df["datetime"].dt.normalize()

    # 聚合到日线
    agg = df.groupby("date").agg(
        inst_net=("inst_net", "sum"),
        xl_net=("xl_net", "sum"),
        l_net=("l_net", "sum"),
    ).reset_index()
    agg["timestamp"] = agg["date"].astype("int64") // 10**6

    print(f"[OK] main-flow: {len(arr)} bars → 聚合为 {len(agg)} 日线")
    return agg


def load_large_trades(ticker: str, limit: int = 500) -> object:
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
# 2. 特征工程
# ══════════════════════════════════════════════

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # ── 2.1 收益率 & 波动率
    df["ret"]     = df["close"].pct_change()
    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    df["range"]   = (df["high"] - df["low"]) / df["close"]   # 相对振幅

    # ── 2.2 VWAP（滚动 20 bar）
    df["vwap_roll"] = (
        (df["close"] * df["volume"]).rolling(20).sum() /
        df["volume"].rolling(20).sum()
    )
    df["vwap_dev"] = (df["close"] - df["vwap_roll"]) / df["vwap_roll"]  # 偏离度

    # ── 2.3 Lee-Ready 方向分类（用中间价判断）
    df["midprice"]  = (df["high"] + df["low"]) / 2
    df["tick_sign"] = np.sign(df["close"] - df["close"].shift(1))  # tick rule
    df["lr_sign"]   = np.where(
        df["close"] > df["midprice"],  1,
        np.where(df["close"] < df["midprice"], -1, df["tick_sign"])
    )

    # ── 2.4 签名成交量 & 订单流失衡 (OFI)
    df["signed_vol"] = df["lr_sign"] * df["volume"]
    df["ofi_raw"]    = df["signed_vol"].rolling(5).sum()
    # 标准化 OFI
    ofi_std = df["ofi_raw"].rolling(20).std().replace(0, np.nan)
    df["ofi_z"]      = df["ofi_raw"] / ofi_std

    # ── 2.5 相对成交量 (RVOL)
    df["rvol"] = df["volume"] / df["volume"].rolling(20).mean()

    # ── 2.6 Impact Efficiency = |ΔPrice| / Volume
    df["price_chg_abs"] = df["close"].diff().abs()
    vol_ma = df["volume"].rolling(5).mean().replace(0, np.nan)
    df["impact_eff"] = df["price_chg_abs"] / vol_ma
    # 标准化
    ie_std = df["impact_eff"].rolling(20).std().replace(0, np.nan)
    df["impact_eff_z"] = (df["impact_eff"] - df["impact_eff"].rolling(20).mean()) / ie_std

    # ── 2.7 Close Location Value (CLV)
    denom = (df["high"] - df["low"]).replace(0, np.nan)
    df["clv"] = (2 * df["close"] - df["high"] - df["low"]) / denom

    # ── 2.8 流动性吸收指标
    # 高成交量 + 低价格变动 = 流动性吸收（机构被动挂单）
    df["liq_absorption"] = df["rvol"] / (df["range"].replace(0, np.nan) * 100 + 0.001)
    la_std = df["liq_absorption"].rolling(20).std().replace(0, np.nan)
    df["liq_abs_z"] = (df["liq_absorption"] - df["liq_absorption"].rolling(20).mean()) / la_std

    # ── 2.9 价格持久性（impact decay）
    # 如果价格在大成交量后维持方向 → 永久冲击（机构）
    # 如果快速回撤 → 临时冲击（零售）
    df["price_persistence"] = df["ret"].rolling(3).mean() / (df["ret"].rolling(3).std().replace(0, np.nan) + 1e-8)

    return df


def merge_flow(df: pd.DataFrame, flow_df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    flow_sub = flow_df[["date", "inst_net", "xl_net", "l_net"]].copy()
    df["date"] = df["datetime"].dt.normalize()
    df = df.merge(flow_sub, left_on="date", right_on="date", how="left")
    df[["inst_net", "xl_net", "l_net"]] = df[["inst_net", "xl_net", "l_net"]].fillna(0)

    # 标准化机构净流入
    inst_std = df["inst_net"].rolling(20).std().replace(0, np.nan)
    df["inst_net_z"] = df["inst_net"] / inst_std
    return df


# ══════════════════════════════════════════════
# 3. HMM 元订单状态分割
# ══════════════════════════════════════════════

def fit_hmm(df: pd.DataFrame, n_states: int = 3) -> pd.DataFrame:
    """
    用 HMM 将市场分割为 n_states 个隐藏状态：
      通常对应：安静期 / 机构积累 / 机构派发（或高波动期）
    """
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        print("[WARN] hmmlearn 未安装，跳过 HMM 分析")
        df["hmm_state"] = 0
        return df

    feature_cols = ["ofi_z", "rvol", "impact_eff_z", "liq_abs_z", "vwap_dev"]
    if "inst_net_z" in df.columns:
        feature_cols.append("inst_net_z")

    sub = df[feature_cols].copy()
    sub = sub.replace([np.inf, -np.inf], np.nan)
    sub = sub.fillna(0)

    X = sub.values
    # 标准化
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = GaussianHMM(n_components=n_states, covariance_type="full",
                        n_iter=200, random_state=42)
    model.fit(X_scaled)
    states = model.predict(X_scaled)
    df = df.copy()
    df["hmm_state"] = states

    # 给状态贴标签：用 OFI 均值 + inst_net 均值判断哪个状态是积累/派发
    state_profiles = df.groupby("hmm_state").agg(
        ofi_mean=("ofi_z", "mean"),
        rvol_mean=("rvol", "mean"),
        inst_mean=("inst_net_z", "mean") if "inst_net_z" in df.columns else ("ofi_z","mean"),
        ret_mean=("ret", "mean"),
        count=("ret","count")
    )
    print("\n[HMM] 状态分布:")
    print(state_profiles.to_string())

    # 标记积累 / 派发 / 中性
    # 积累：高 OFI + 高机构净流入 → 倾向于正
    # 派发：低 OFI + 负机构净流入 → 倾向于负
    ofi_col = "inst_mean" if "inst_mean" in state_profiles.columns else "ofi_mean"
    best_acc   = state_profiles[ofi_col].idxmax()
    best_dist  = state_profiles[ofi_col].idxmin()
    best_neut  = [s for s in state_profiles.index if s not in (best_acc, best_dist)][0] if n_states >= 3 else -1

    label_map = {best_acc: "accumulation", best_dist: "distribution"}
    if best_neut != -1:
        label_map[best_neut] = "neutral"
    df["hmm_label"] = df["hmm_state"].map(label_map).fillna("neutral")

    return df


# ══════════════════════════════════════════════
# 4. 机构信号评分
# ══════════════════════════════════════════════

def compute_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # ── 各维度得分 (−1 到 +1)
    def norm_clip(s):
        """把一个 Series 标准化后 clip 到 [-1, 1]"""
        mu, sd = s.rolling(50).mean(), s.rolling(50).std().replace(0, np.nan)
        return ((s - mu) / sd).clip(-1, 1).fillna(0)

    s_ofi  = norm_clip(df["ofi_z"])
    s_rvol = norm_clip(df["rvol"] - 1)          # >1 = 放量
    s_liq  = norm_clip(df["liq_abs_z"])
    s_vwap = -norm_clip(df["impact_eff_z"])      # 低冲击效率 = 高机构概率
    s_clv  = df["clv"].fillna(0)
    s_pers = norm_clip(df["price_persistence"])

    weights = {"ofi": 0.25, "rvol": 0.15, "liq": 0.20,
               "vwap": 0.15, "clv": 0.10, "pers": 0.10, "flow": 0.05}

    if "inst_net_z" in df.columns:
        s_flow = norm_clip(df["inst_net_z"])
        weights["flow"] = 0.15
        # 重新归一化权重
        total = sum(weights.values())
        weights = {k: v/total for k, v in weights.items()}
    else:
        s_flow = pd.Series(0.0, index=df.index)

    df["raw_score"] = (
        weights["ofi"]  * s_ofi  +
        weights["rvol"] * s_rvol +
        weights["liq"]  * s_liq  +
        weights["vwap"] * s_vwap +
        weights["clv"]  * s_clv  +
        weights["pers"] * s_pers +
        weights["flow"] * s_flow
    )

    # ── HMM 状态修正
    hmm_boost = {"accumulation": 0.15, "distribution": -0.15, "neutral": 0.0}
    df["hmm_boost"] = df["hmm_label"].map(hmm_boost).fillna(0)
    df["final_score"] = (df["raw_score"] + df["hmm_boost"]).clip(-1, 1)

    # ── 信号分类
    df["signal"] = pd.cut(
        df["final_score"],
        bins=[-1.01, -0.35, -0.10, 0.10, 0.35, 1.01],
        labels=["strong_distribution", "distribution", "neutral",
                "accumulation", "strong_accumulation"]
    )

    # ── 置信度（0~100%）
    df["confidence"] = (df["final_score"].abs() * 100).round(1)

    # ── 估算机构参与率（简化）
    df["est_inst_participation"] = (
        (df["rvol"].clip(0, 3) / 3 * 0.5 +
         df["liq_abs_z"].clip(0, 2) / 2 * 0.3 +
         s_ofi.abs() * 0.2) * 25  # 上限约 25%
    ).clip(0, 25).round(2)

    # ── 累积仓位变化估算 (Δ Inventory)
    direction = np.where(df["signal"].isin(["accumulation","strong_accumulation"]), 1,
                np.where(df["signal"].isin(["distribution","strong_distribution"]), -1, 0))
    df["delta_inventory"] = direction * df["est_inst_participation"] / 100 * df["volume"]
    df["cumulative_inventory"] = df["delta_inventory"].cumsum()

    return df


# ══════════════════════════════════════════════
# 5. 输出
# ══════════════════════════════════════════════

def save_output(df: pd.DataFrame, ticker: str, interval: str) -> str:
    cols = [
        "datetime", "timestamp",
        "open", "high", "low", "close", "volume",
        "vwap_roll", "vwap_dev",
        "ofi_z", "rvol", "impact_eff_z", "liq_abs_z",
        "clv", "price_persistence",
        "hmm_state", "hmm_label",
        "raw_score", "hmm_boost", "final_score",
        "signal", "confidence",
        "est_inst_participation", "delta_inventory", "cumulative_inventory",
    ]
    if "inst_net" in df.columns:
        cols += ["inst_net", "xl_net", "l_net", "inst_net_z"]

    out = df[[c for c in cols if c in df.columns]].copy()
    out = out.dropna(subset=["signal"])

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{ticker}_{interval}_{ts}_signals.csv"
    fpath = os.path.join(OUTPUT_DIR, fname)
    out.to_csv(fpath, index=False)
    return fpath


def print_summary(df: pd.DataFrame, ticker: str, interval: str):
    valid = df.dropna(subset=["signal"])
    counts = valid["signal"].value_counts()

    print(f"\n{'='*55}")
    print(f"  {ticker} | {interval} | {len(valid)} bars 分析完成")
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

    acc_bars = valid[valid["signal"].isin(["accumulation","strong_accumulation"])]
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
    parser = argparse.ArgumentParser(description="Institutional Flow Signal Generator")
    parser.add_argument("--ticker",   default="AAPL",  help="股票代码")
    parser.add_argument("--interval", default="1d",    help="时间间隔 (1d/1h/15m/5m/1m)")
    parser.add_argument("--limit",    default=300, type=int, help="K 线数量")
    parser.add_argument("--hmm-states", default=3, type=int, help="HMM 状态数 (2-4)")
    parser.add_argument("--from-date", default=None, help="K线起始日期 YYYY-MM-DD")
    parser.add_argument("--to-date",   default=None, help="结束日期 YYYY-MM-DD，不填则为今天")
    parser.add_argument("--flow-from", default=None, help="main-flow起始日期 YYYY-MM-DD，不填则用2026-01-01")
    args = parser.parse_args()

    ticker   = args.ticker.upper()
    interval = args.interval
    limit    = args.limit

    print(f"\n[START] {ticker} | {interval} | limit={limit}")
    print("-" * 40)

    # 1. 拉数据
    df        = load_klines(ticker, interval, limit,
                          from_date=args.from_date, to_date=args.to_date)
    flow_df   = load_main_flow(ticker, interval, limit,
                              from_date=args.flow_from, to_date=args.to_date)
    trades_df = load_large_trades(ticker, limit=200)

    # 2. 特征工程
    print("\n[计算特征...]")
    df = compute_features(df)

    # 3. 合并资金流
    if flow_df is not None:
        df = merge_flow(df, flow_df)

    # 4. HMM 状态分割
    print("[训练 HMM...]")
    df = fit_hmm(df, n_states=args.hmm_states)

    # 5. 综合信号评分
    print("[生成信号...]")
    df = compute_signal(df)

    # 6. 输出
    fpath = save_output(df, ticker, interval)
    print_summary(df, ticker, interval)
    print(f"[SAVED] {fpath}\n")

    return fpath


if __name__ == "__main__":
    main()
