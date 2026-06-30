"""
validate_cluster_coverage.py — 检验现有4组分类能否泛化到新 ticker

核心问题：现有 G0-G3 (基于23个ticker训练) 是否已经覆盖了市面上
大部分美股的 IC 模式，还是只覆盖了科技+金融这个偏科子集？

方法：
  1. 对一批"没见过"的新 ticker 跑同样的 IC 分析
  2. 不重新聚类 —— 而是计算新 ticker 的 IC 向量到现有4个质心的欧式距离
  3. 分配到最近的质心，记录距离
  4. 对比：新 ticker 的距离分布 vs 原23个ticker到自己质心的距离分布
     - 如果分布相近 → 4组有泛化能力，覆盖了这些新 ticker 的模式
     - 如果新 ticker 普遍距离远 → 4组没覆盖住，存在"真空地带"
  5. 额外做一次：把新+老 ticker 一起重新聚类，看 k=4 是否还是最优、
     质心是否大幅漂移 —— 这是更严格的检验

用法：
  python3 validate_cluster_coverage.py \
      --train-file ic_analysis_results.csv \
      --train-cls-file ic_analysis_results_classification.csv
"""

import argparse
import warnings
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError:
    raise ImportError("请先安装 yfinance：pip3 install yfinance")

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    raise ImportError("请先安装 scikit-learn：pip3 install scikit-learn")

FEATURES = ["ofi_z", "rvol", "vwap_dev", "impact_eff_z"]
HORIZONS = [1, 3, 6, 12, 24]

# 新 ticker：覆盖现有23个里没怎么涉及的板块
NEW_TICKERS = [
    # 医疗保健
    "UNH", "LLY", "PFE",
    # 必需消费品
    "WMT", "KO", "PG",
    # 工业
    "CAT", "BA",
    # 小盘 / 新兴
    "RIVN", "ARM",
    # REIT
    "O", "PLD",
]

INTERVAL_MAP = {
    "1h": {"period": "2y", "yf_interval": "1h"},
    "1d": {"period": "5y", "yf_interval": "1d"},
}


# ══════════════════════════════════════════════
# 1. 数据拉取 + 特征计算（与 ic_analysis_yfinance.py 一致）
# ══════════════════════════════════════════════

def fetch_ohlcv(ticker: str, interval: str) -> Optional[pd.DataFrame]:
    cfg = INTERVAL_MAP.get(interval, INTERVAL_MAP["1d"])
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period=cfg["period"], interval=cfg["yf_interval"], auto_adjust=True)
        if df.empty:
            print(f"  [WARN] {ticker}: empty data")
            return None
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        time_col = "datetime" if "datetime" in df.columns else "date"
        df = df.rename(columns={time_col: "datetime"})
        df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)
        df = df[["datetime", "open", "high", "low", "close", "volume"]].dropna()
        df = df.sort_values("datetime").reset_index(drop=True)
        print(f"  [OK] {ticker}: {len(df)} bars")
        return df
    except Exception as e:
        print(f"  [ERROR] {ticker}: {e}")
        return None


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ret"] = df["close"].pct_change()

    df["vwap_roll"] = (
        (df["close"] * df["volume"]).rolling(20).sum() /
        df["volume"].rolling(20).sum()
    )
    df["vwap_dev"] = (df["close"] - df["vwap_roll"]) / df["vwap_roll"]

    df["midprice"]  = (df["high"] + df["low"]) / 2
    df["tick_sign"] = np.sign(df["close"] - df["close"].shift(1))
    df["lr_sign"]   = np.where(
        df["close"] > df["midprice"],  1,
        np.where(df["close"] < df["midprice"], -1, df["tick_sign"])
    )
    df["signed_vol"] = df["lr_sign"] * df["volume"]
    ofi_lr = df["signed_vol"].rolling(5).sum()

    bar_range = (df["high"] - df["low"]).replace(0, np.nan)
    df["bvc_buy_frac"] = ((df["close"] - df["low"]) / bar_range).fillna(0.5)
    bvc_net  = (df["bvc_buy_frac"] - 0.5) * 2 * df["volume"]
    ofi_bvc  = bvc_net.rolling(5).sum()

    ret_ma   = df["close"].pct_change().rolling(20).mean().abs()
    ret_norm = (ret_ma / (ret_ma.rolling(50).mean() + 1e-8)).clip(0, 2) / 2
    alpha    = ret_norm.fillna(0.5)
    df["ofi_raw"] = alpha * ofi_lr + (1 - alpha) * ofi_bvc
    ofi_std       = df["ofi_raw"].rolling(20).std().replace(0, np.nan)
    df["ofi_z"]   = (df["ofi_raw"] / ofi_std).clip(-3, 3)

    df["rvol"] = df["volume"] / df["volume"].rolling(20).mean()

    adv       = df["volume"].rolling(20).mean().replace(0, np.nan)
    sigma     = df["ret"].rolling(20).std().replace(0, np.nan)
    part_rate = (df["volume"] / adv).clip(0.01, 100)
    df["price_chg_abs"] = df["close"].diff().abs()
    sqrt_impact = df["price_chg_abs"] / (sigma * df["close"] * np.sqrt(part_rate) + 1e-8)
    ie_std = sqrt_impact.rolling(20).std().replace(0, np.nan)
    df["impact_eff_z"] = ((sqrt_impact - sqrt_impact.rolling(20).mean()) / ie_std).clip(-3, 3)

    return df


def add_forward_returns(df: pd.DataFrame, horizons: list) -> pd.DataFrame:
    df = df.copy()
    for h in horizons:
        df[f"fwd_ret_{h}"] = df["close"].pct_change(h).shift(-h)
    return df


def single_feature_ic(df: pd.DataFrame, feature: str, horizons: list) -> pd.DataFrame:
    results = []
    if feature not in df.columns:
        return pd.DataFrame()
    for h in horizons:
        col = f"fwd_ret_{h}"
        sub = df[[feature, col]].dropna()
        if len(sub) < 10:
            continue
        ic, p = stats.spearmanr(sub[feature], sub[col])
        results.append({"feature": feature, "horizon": h, "n": len(sub),
                        "ic": ic, "p_value": p, "abs_ic": abs(ic)})
    return pd.DataFrame(results)


def get_ic_vector(ticker: str, interval: str = "1d") -> Optional[np.ndarray]:
    df = fetch_ohlcv(ticker, interval)
    if df is None or len(df) < 50:
        return None
    df = compute_features(df)
    df = add_forward_returns(df, HORIZONS)

    vec = []
    for feat in FEATURES:
        res = single_feature_ic(df, feat, HORIZONS)
        vec.append(res["abs_ic"].mean() if not res.empty else 0.0)
    return np.array(vec)


# ══════════════════════════════════════════════
# 2. 核心验证逻辑
# ══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-file",     default="ic_analysis_results.csv")
    parser.add_argument("--train-cls-file", default="ic_analysis_results_classification.csv")
    parser.add_argument("--interval",       default="1d")
    parser.add_argument("--new-tickers",    nargs="+", default=NEW_TICKERS)
    args = parser.parse_args()

    # ── 加载训练数据，重建质心 ──────────────────────────────────
    ic_df  = pd.read_csv(args.train_file)
    cls_df = pd.read_csv(args.train_cls_file)

    cluster_col = "ic_cluster" if "ic_cluster" in cls_df.columns else "type"
    summary = ic_df.groupby(["ticker", "feature"])["abs_ic"].mean().reset_index()
    pivot = summary.pivot_table(index="ticker", columns="feature", values="abs_ic").fillna(0)
    pivot = pivot[FEATURES]  # 保证列顺序一致

    cluster_map = cls_df.set_index("ticker")[cluster_col].to_dict()
    pivot["cluster"] = pivot.index.map(cluster_map)
    pivot = pivot.dropna(subset=["cluster"])

    print(f"[OK] Loaded {len(pivot)} training tickers, "
          f"clusters: {sorted(pivot['cluster'].unique())}")

    # 标准化用训练数据的 scaler（新ticker要用同一个尺度）
    scaler = StandardScaler()
    X_train = scaler.fit_transform(pivot[FEATURES].values)
    pivot_scaled = pd.DataFrame(X_train, index=pivot.index, columns=FEATURES)
    pivot_scaled["cluster"] = pivot["cluster"].values

    # 计算每组质心（标准化后空间）
    centroids = pivot_scaled.groupby("cluster")[FEATURES].mean()
    print(f"\n  训练集质心 (standardized space):")
    print(centroids.round(3).to_string())

    # 训练集内部：每个 ticker 到自己质心的距离（作为基准分布）
    train_distances = []
    for t in pivot_scaled.index:
        c = pivot_scaled.loc[t, "cluster"]
        vec = pivot_scaled.loc[t, FEATURES].values.astype(float)
        cen = centroids.loc[c].values.astype(float)
        dist = np.linalg.norm(vec - cen)
        train_distances.append(dist)
    train_distances = np.array(train_distances)

    print(f"\n{'='*65}")
    print("  训练集内部：ticker 到自己质心的距离分布（基准）")
    print(f"{'='*65}")
    print(f"  Mean: {train_distances.mean():.3f} | Median: {np.median(train_distances):.3f} "
          f"| Std: {train_distances.std():.3f} | Max: {train_distances.max():.3f}")

    # ── 拉取新 ticker 数据，计算 IC 向量 ─────────────────────────
    print(f"\n{'='*65}")
    print(f"  拉取 {len(args.new_tickers)} 个新 ticker 的 IC 数据")
    print(f"{'='*65}")

    new_vectors = {}
    for t in args.new_tickers:
        print(f"\n── {t} ──")
        vec = get_ic_vector(t, args.interval)
        if vec is not None:
            new_vectors[t] = vec
        else:
            print(f"  [SKIP] {t}: insufficient data")

    if not new_vectors:
        print("[FATAL] No new ticker data — check network")
        return

    # ── 新 ticker 标准化（用训练集的 scaler）+ 分配到最近质心 ──────
    new_df = pd.DataFrame(new_vectors, index=FEATURES).T
    X_new = scaler.transform(new_df.values)  # 用训练集的均值/方差
    new_scaled = pd.DataFrame(X_new, index=new_df.index, columns=FEATURES)

    assignments = []
    for t in new_scaled.index:
        vec = new_scaled.loc[t].values.astype(float)
        dists = {c: np.linalg.norm(vec - centroids.loc[c].values.astype(float))
                 for c in centroids.index}
        nearest = min(dists, key=dists.get)
        assignments.append({
            "ticker": t,
            "assigned_cluster": nearest,
            "distance": round(dists[nearest], 3),
            **{f"dist_to_{c}": round(d, 3) for c, d in dists.items()},
        })

    assign_df = pd.DataFrame(assignments).sort_values("distance")

    print(f"\n{'='*65}")
    print("  新 TICKER 分配结果（按到最近质心的距离排序）")
    print(f"{'='*65}")
    print(assign_df.to_string(index=False))

    # ── 对比新老分布 ──────────────────────────────────────────
    new_distances = assign_df["distance"].values

    print(f"\n{'='*65}")
    print("  覆盖能力对比：新 ticker 距离 vs 训练集基准分布")
    print(f"{'='*65}")
    print(f"  训练集基准 — Mean: {train_distances.mean():.3f}, "
          f"P90: {np.percentile(train_distances, 90):.3f}, Max: {train_distances.max():.3f}")
    print(f"  新 ticker  — Mean: {new_distances.mean():.3f}, "
          f"P90: {np.percentile(new_distances, 90):.3f}, Max: {new_distances.max():.3f}")

    # Mann-Whitney U test：两组距离分布是否有显著差异
    stat, p = stats.mannwhitneyu(train_distances, new_distances, alternative="two-sided")
    print(f"\n  Mann-Whitney U test: p={p:.4f}")
    if p > 0.05:
        print("  ✅ 新老距离分布无显著差异 — 4组对新 ticker 有良好泛化能力")
    else:
        if new_distances.mean() > train_distances.mean():
            print("  ⚠️  新 ticker 距离显著更远 — 现有4组未能很好覆盖这些新板块")
            print("      → 可能存在第5个聚类未被发现")
        else:
            print("  ⚠️  新 ticker 距离显著更近 — 不寻常，检查数据")

    # 标记"游离" ticker：距离超过训练集 P90
    threshold = np.percentile(train_distances, 90)
    orphans = assign_df[assign_df["distance"] > threshold]
    if not orphans.empty:
        print(f"\n  ⚠️  以下新 ticker 距离超过训练集 P90 ({threshold:.3f})，"
              f"可能不属于任何现有组：")
        print(orphans[["ticker", "assigned_cluster", "distance"]].to_string(index=False))
    else:
        print(f"\n  ✅ 所有新 ticker 距离均在训练集 P90 范围内 ({threshold:.3f})")

    # ── 第二步：新老合并重新聚类，看 k=4 是否仍最优 ──────────────
    print(f"\n{'='*65}")
    print("  严格检验：新老 ticker 合并后重新聚类")
    print(f"  （看 k=4 是否仍是最优，质心是否大幅漂移）")
    print(f"{'='*65}")

    combined_raw = pd.concat([
        pivot[FEATURES],
        new_df,
    ])
    X_combined = StandardScaler().fit_transform(combined_raw.values)

    print(f"\n  Silhouette scores for k=2 to 6 (n={len(combined_raw)} tickers):")
    best_k, best_sil = None, -1
    for k in range(2, min(7, len(combined_raw))):
        km = KMeans(n_clusters=k, random_state=42, n_init=20)
        labels = km.fit_predict(X_combined)
        sil = silhouette_score(X_combined, labels)
        bar = "█" * int(sil * 30)
        marker = " <-- was optimal before" if k == 4 else ""
        print(f"    k={k}: {sil:.3f} {bar}{marker}")
        if sil > best_sil:
            best_k, best_sil = k, sil

    print(f"\n  原最优 k=4 (silhouette=0.322, 23 tickers)")
    print(f"  新最优 k={best_k} (silhouette={best_sil:.3f}, "
          f"{len(combined_raw)} tickers)")

    if best_k == 4:
        print("  ✅ k=4 在加入新 ticker 后仍是最优 — 4组结构稳健")
    else:
        print(f"  ⚠️  最优 k 从 4 变为 {best_k} — 加入新板块后分组结构发生变化，"
              f"建议用全部 {len(combined_raw)} 个 ticker 重新聚类")

    out_path = "cluster_coverage_validation.csv"
    assign_df.to_csv(out_path, index=False)
    print(f"\n[SAVED] {out_path}")


if __name__ == "__main__":
    main()
