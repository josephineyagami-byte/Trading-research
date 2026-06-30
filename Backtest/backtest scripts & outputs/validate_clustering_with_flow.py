"""
validate_clustering.py — 验证 IC 聚类分组是否 make sense

三个检验：
  1. 组间 IC 差异显著性 (Kruskal-Wallis + pairwise Mann-Whitney)
  2. 组内 vs 组间方差比 (F-statistic analog)
  3. Bootstrap stability test (100次重采样，看配对稳定性)

用法：
  python3 validate_clustering.py --ic-file ic_analysis_results.csv \
                                  --cls-file ic_analysis_results_classification.csv
  python3 validate_clustering.py --ic-file ic_analysis_results.csv \
                                  --cls-file ic_analysis_results_classification.csv \
                                  --n-bootstrap 200 --n-clusters 4
"""

import argparse
import warnings
from itertools import combinations
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    print("[WARN] scikit-learn not found — bootstrap test disabled")

FEATURES = ["ofi_z", "rvol", "vwap_dev", "impact_eff_z", "inst_net_z"]


# ══════════════════════════════════════════════
# 1. 加载数据
# ══════════════════════════════════════════════

def load_data(ic_file: str, cls_file: str):
    ic_df  = pd.read_csv(ic_file)
    cls_df = pd.read_csv(cls_file)

    # 取每个 ticker × feature 的 avg_weighted|IC|（confidence-weighted，
    # 不是原始 abs_ic —— 这次的聚类用的就是 weighted 版本，验证也要用
    # 同一套数字，否则验证的不是实际驱动聚类的那个量）
    ic_col = "weighted_abs_ic" if "weighted_abs_ic" in ic_df.columns else "abs_ic"
    summary = ic_df.groupby(["ticker", "feature"])[ic_col].mean().reset_index()
    summary.columns = ["ticker", "feature", "avg_abs_ic"]

    # 合并分组信息
    cluster_col = "ic_cluster" if "ic_cluster" in cls_df.columns else "type"
    summary = summary.merge(cls_df[["ticker", cluster_col]], on="ticker", how="left")
    summary = summary.rename(columns={cluster_col: "cluster"})

    # 构建 ticker × feature 矩阵
    pivot = summary.pivot_table(index="ticker", columns="feature",
                                 values="avg_abs_ic").fillna(0)

    cluster_map = cls_df.set_index("ticker")[cluster_col].to_dict()

    print(f"[OK] Loaded {summary['ticker'].nunique()} tickers, "
          f"{summary['feature'].nunique()} features")
    print(f"     Clusters: {sorted(summary['cluster'].dropna().unique())}")

    return summary, pivot, cluster_map


# ══════════════════════════════════════════════
# 2. 检验一：组间 IC 差异显著性
# ══════════════════════════════════════════════

def test_between_group_difference(summary: pd.DataFrame) -> pd.DataFrame:
    """
    对每个特征，检验各组的 avg|IC| 分布是否有显著差异。
    用 Kruskal-Wallis（非参数，不假设正态）。
    H0: 所有组的 IC 分布相同
    H1: 至少有一组不同
    p < 0.05 → 分组有意义（组间差异不是随机的）
    """
    results = []
    clusters = sorted(summary["cluster"].dropna().unique())

    for feat in FEATURES:
        sub = summary[summary["feature"] == feat].dropna(subset=["cluster"])
        groups = [sub[sub["cluster"] == c]["avg_abs_ic"].values for c in clusters]
        groups = [g for g in groups if len(g) > 0]

        if len(groups) < 2:
            continue

        stat, p = stats.kruskal(*groups)

        # 组均值
        group_means = {c: sub[sub["cluster"] == c]["avg_abs_ic"].mean()
                       for c in clusters}

        results.append({
            "feature":       feat,
            "kruskal_stat":  round(stat, 3),
            "p_value":       round(p, 4),
            "significant":   "✅" if p < 0.05 else "❌",
            **{f"mean_{c}": round(v, 4) for c, v in group_means.items()},
        })

    return pd.DataFrame(results)


def test_pairwise(summary: pd.DataFrame) -> pd.DataFrame:
    """
    Pairwise Mann-Whitney U test between all cluster pairs, per feature.
    看哪两个组之间差异最显著。
    """
    results = []
    clusters = sorted(summary["cluster"].dropna().unique())

    for feat in FEATURES:
        sub = summary[summary["feature"] == feat].dropna(subset=["cluster"])
        for c1, c2 in combinations(clusters, 2):
            g1 = sub[sub["cluster"] == c1]["avg_abs_ic"].values
            g2 = sub[sub["cluster"] == c2]["avg_abs_ic"].values
            if len(g1) < 2 or len(g2) < 2:
                continue
            stat, p = stats.mannwhitneyu(g1, g2, alternative="two-sided")
            results.append({
                "feature":   feat,
                "pair":      f"{c1} vs {c2}",
                "mean_diff": round(g1.mean() - g2.mean(), 4),
                "p_value":   round(p, 4),
                "significant": "✅" if p < 0.05 else "❌",
            })

    return pd.DataFrame(results)


# ══════════════════════════════════════════════
# 3. 检验二：组内 vs 组间方差比
# ══════════════════════════════════════════════

def test_variance_ratio(summary: pd.DataFrame) -> pd.DataFrame:
    """
    F-statistic analog：组间方差 / 组内方差
    好的分组：组间方差大（组之间差异明显），组内方差小（组内相似）
    F > 1 表示组间差异大于组内差异
    F >> 1 表示分组质量高
    """
    results = []
    clusters = sorted(summary["cluster"].dropna().unique())
    grand_mean = summary.groupby("feature")["avg_abs_ic"].mean()

    for feat in FEATURES:
        sub = summary[summary["feature"] == feat].dropna(subset=["cluster"])
        overall_mean = grand_mean[feat]

        # 组间方差 (between-group variance)
        between = sum(
            len(sub[sub["cluster"] == c]) *
            (sub[sub["cluster"] == c]["avg_abs_ic"].mean() - overall_mean) ** 2
            for c in clusters
        ) / (len(clusters) - 1)

        # 组内方差 (within-group variance)
        within_vals = []
        for c in clusters:
            g = sub[sub["cluster"] == c]["avg_abs_ic"]
            within_vals.extend((g - g.mean()) ** 2)
        within = np.mean(within_vals) if within_vals else 0

        f_ratio = between / (within + 1e-10)

        results.append({
            "feature":        feat,
            "between_var":    round(between, 6),
            "within_var":     round(within, 6),
            "F_ratio":        round(f_ratio, 2),
            "interpretation": "✅ 组间>组内" if f_ratio > 1 else "❌ 组间<组内",
        })

    return pd.DataFrame(results)


# ══════════════════════════════════════════════
# 4. 检验三：Bootstrap Stability Test
# ══════════════════════════════════════════════

def bootstrap_stability(pivot: pd.DataFrame, cluster_map: dict,
                         n_bootstrap: int = 100,
                         n_clusters: int = 4) -> pd.DataFrame:
    """
    随机抽样重跑聚类 n_bootstrap 次。
    统计每对 ticker 被分到同一组的频率（co-occurrence rate）。
    高频率（>0.7）= 配对稳定，分组可信
    低频率（<0.3）= 边界模糊，分组不稳定
    """
    if not HAS_SKLEARN:
        print("[SKIP] scikit-learn not available")
        return pd.DataFrame()

    tickers = pivot.index.tolist()
    n = len(tickers)
    co_occurrence = np.zeros((n, n))
    count_matrix  = np.zeros((n, n))

    X_full = StandardScaler().fit_transform(pivot.values)

    for _ in range(n_bootstrap):
        # 随机抽取 80% ticker（有放回）
        sample_idx = np.random.choice(n, size=int(n * 0.8), replace=False)
        X_sample   = X_full[sample_idx]

        if len(sample_idx) < n_clusters:
            continue

        km = KMeans(n_clusters=n_clusters, random_state=np.random.randint(10000),
                    n_init=10)
        labels = km.fit_predict(X_sample)

        # 记录同组配对
        for i, ii in enumerate(sample_idx):
            for j, jj in enumerate(sample_idx):
                count_matrix[ii, jj] += 1
                if labels[i] == labels[j]:
                    co_occurrence[ii, jj] += 1

    # 计算共现率
    with np.errstate(divide="ignore", invalid="ignore"):
        rate_matrix = np.where(count_matrix > 0,
                               co_occurrence / count_matrix, np.nan)

    # 转成 DataFrame
    rate_df = pd.DataFrame(rate_matrix, index=tickers, columns=tickers)

    return rate_df


def summarize_stability(rate_df: pd.DataFrame, cluster_map: dict,
                         threshold_stable: float = 0.70,
                         threshold_unstable: float = 0.30) -> None:
    """
    输出稳定配对和不稳定配对的汇总
    """
    tickers = rate_df.index.tolist()
    same_cluster_pairs   = []
    diff_cluster_pairs   = []

    for t1, t2 in combinations(tickers, 2):
        rate = rate_df.loc[t1, t2]
        if np.isnan(rate):
            continue
        same = cluster_map.get(t1) == cluster_map.get(t2)
        entry = (t1, t2, round(rate, 3), cluster_map.get(t1), cluster_map.get(t2))
        if same:
            same_cluster_pairs.append(entry)
        else:
            diff_cluster_pairs.append(entry)

    # 同组配对中稳定率低的（潜在问题）
    same_df = pd.DataFrame(same_cluster_pairs,
                            columns=["t1", "t2", "co_rate", "cluster_t1", "cluster_t2"])
    same_df = same_df.sort_values("co_rate")

    # 不同组配对中稳定率高的（边界模糊）
    diff_df = pd.DataFrame(diff_cluster_pairs,
                            columns=["t1", "t2", "co_rate", "cluster_t1", "cluster_t2"])
    diff_df = diff_df.sort_values("co_rate", ascending=False)

    print(f"\n  同组配对稳定率分布：")
    bins = [0, 0.3, 0.5, 0.7, 1.01]
    labels = ["<0.3 (不稳定)", "0.3-0.5 (边界)", "0.5-0.7 (中等)", ">0.7 (稳定)"]
    same_df["bin"] = pd.cut(same_df["co_rate"], bins=bins, labels=labels)
    print(same_df["bin"].value_counts().sort_index().to_string())

    unstable_same = same_df[same_df["co_rate"] < threshold_unstable]
    if not unstable_same.empty:
        print(f"\n  ⚠️  同组内但共现率低（<{threshold_unstable}）的配对（边界模糊）：")
        print(unstable_same[["t1", "t2", "co_rate", "cluster_t1"]].to_string(index=False))
    else:
        print(f"\n  ✅ 所有同组配对共现率 >= {threshold_unstable}，组内边界清晰")

    ambiguous_diff = diff_df[diff_df["co_rate"] > threshold_stable]
    if not ambiguous_diff.empty:
        print(f"\n  ⚠️  不同组但共现率高（>{threshold_stable}）的配对（分组边界模糊）：")
        print(ambiguous_diff[["t1", "t2", "co_rate", "cluster_t1", "cluster_t2"]]
              .head(10).to_string(index=False))
    else:
        print(f"\n  ✅ 无跨组高共现率配对，组间边界清晰")

    # 整体稳定性分数
    overall = same_df["co_rate"].mean()
    print(f"\n  整体同组稳定性均值: {overall:.3f}")
    print(f"  （>0.65 = 分组稳定，0.5-0.65 = 中等，<0.5 = 不稳定）")


# ══════════════════════════════════════════════
# 5. 主程序
# ══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Validate IC-based clustering")
    parser.add_argument("--ic-file",     required=True, help="ic_analysis_results.csv")
    parser.add_argument("--cls-file",    required=True, help="ic_analysis_results_classification.csv")
    parser.add_argument("--n-bootstrap", default=100, type=int)
    parser.add_argument("--n-clusters",  default=4,   type=int)
    parser.add_argument("--skip-bootstrap", action="store_true",
                        help="跳过 bootstrap（速度慢）")
    args = parser.parse_args()

    summary, pivot, cluster_map = load_data(args.ic_file, args.cls_file)

    # ── 检验一：组间差异显著性 ─────────────────────────────────────
    print(f"\n{'='*65}")
    print("  TEST 1: 组间 IC 差异显著性 (Kruskal-Wallis)")
    print(f"  H0: 各组 IC 分布相同  |  p<0.05 → 分组有意义")
    print(f"{'='*65}")
    kw_results = test_between_group_difference(summary)
    print(kw_results.to_string(index=False))

    n_sig = (kw_results["significant"] == "✅").sum()
    print(f"\n  {n_sig}/{len(kw_results)} 个特征的组间差异显著")
    if n_sig == len(kw_results):
        print("  ✅ 所有特征组间差异显著 — 分组捕捉到了真实的IC模式差异")
    elif n_sig >= len(kw_results) // 2:
        print("  ⚠️  部分特征显著 — 分组有一定意义，但不完全")
    else:
        print("  ❌ 大多数特征不显著 — 分组可能是随机的")

    # Pairwise
    print(f"\n{'='*65}")
    print("  TEST 1b: Pairwise 组间差异 (Mann-Whitney)")
    print(f"{'='*65}")
    pw_results = test_pairwise(summary)
    if not pw_results.empty:
        sig_pairs = pw_results[pw_results["significant"] == "✅"]
        print(f"  显著配对 ({len(sig_pairs)}/{len(pw_results)}):")
        print(pw_results[pw_results["significant"] == "✅"]
              .sort_values(["feature", "p_value"])
              .to_string(index=False))
        if len(pw_results) - len(sig_pairs) > 0:
            print(f"\n  不显著配对 ({len(pw_results)-len(sig_pairs)}):")
            print(pw_results[pw_results["significant"] == "❌"]
                  .sort_values(["feature", "p_value"])
                  .to_string(index=False))

    # ── 检验二：方差比 ────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  TEST 2: 组内 vs 组间方差比 (F-ratio)")
    print(f"  F > 1 → 组间差异 > 组内差异 → 分组有意义")
    print(f"{'='*65}")
    var_results = test_variance_ratio(summary)
    print(var_results.to_string(index=False))
    good_f = (var_results["F_ratio"] > 1).sum()
    print(f"\n  {good_f}/{len(var_results)} 个特征的 F-ratio > 1")

    # ── 检验三：Bootstrap Stability ───────────────────────────────
    if not args.skip_bootstrap and HAS_SKLEARN:
        print(f"\n{'='*65}")
        print(f"  TEST 3: Bootstrap Stability ({args.n_bootstrap} 次重采样)")
        print(f"  同组配对的共现率越高 → 分组越稳定")
        print(f"{'='*65}")
        print(f"  Running {args.n_bootstrap} bootstrap iterations...")
        rate_df = bootstrap_stability(pivot, cluster_map,
                                       n_bootstrap=args.n_bootstrap,
                                       n_clusters=args.n_clusters)
        if not rate_df.empty:
            summarize_stability(rate_df, cluster_map)

            # 保存共现率矩阵
            out_path = "clustering_stability_matrix.csv"
            rate_df.round(3).to_csv(out_path)
            print(f"\n[SAVED] {out_path}")
    elif args.skip_bootstrap:
        print(f"\n[SKIP] Bootstrap test skipped (--skip-bootstrap)")

    # ── 综合结论 ─────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  综合结论")
    print(f"{'='*65}")
    print(f"  Test 1 (组间显著性): {n_sig}/{len(kw_results)} 特征显著")
    print(f"  Test 2 (方差比):     {good_f}/{len(var_results)} 特征 F>1")
    print()
    if n_sig >= 2 and good_f >= 2:
        print("  ✅ 分组整体有统计意义 — 可以基于这个分组设计权重")
    elif n_sig >= 1 or good_f >= 2:
        print("  ⚠️  分组部分有意义 — 建议增加 ticker 数量后重新验证")
    else:
        print("  ❌ 分组统计意义不足 — 考虑调整特征或聚类方法")
    print()
    print("  [下一步] 服务器恢复后加入 inst_net_z，重跑聚类验证")
    print("  [下一步] 用各组 pooled IC 权重生成信号，对比 backtest 结果")


if __name__ == "__main__":
    main()
