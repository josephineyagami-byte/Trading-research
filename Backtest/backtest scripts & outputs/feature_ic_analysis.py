"""
feature_ic_analysis.py — 单特征 IC 分析：每个特征单独的预测力到底有多强

背景：
  backtest 结果显示 confidence tier 存在倒挂（置信度越高，胜率/收益反而越差），
  且这个现象在修复 HMM 标签 bug 后依然存在 —— 说明问题更可能出在 raw_score
  本身（6个特征加权求和那部分），而不是 HMM boost。

  这个脚本不看最终的 final_score / signal，而是把 compute_features() 算出来的
  每一个原始特征单独拎出来，各自和未来收益做 IC 分析（Spearman相关系数），
  方法和 backtest.py 的 information_coefficient() 完全一致，这样结果可以
  直接和已有的 final_score IC（之前测出来普遍偏弱）做对比。

  同时这个脚本也是"候选新特征"的统一测试框架 —— 如果之后要评估 short
  interest / large trade total 这类候选特征该不该加进权重表，应该先用
  这同一套方法测出它们各自的 IC，而不是凭直觉加进固定权重表（这正是
  v2 用 Lasso 训练权重失败的教训：先验证信号本身有没有价值，再决定权重）。

用法：
  python3 feature_ic_analysis.py --file output/AAPL_1h_xxx_v3_signals.csv

如果要测试候选新特征，把对应数据合并进同一个 CSV（按 datetime 对齐），
加一列，再用 --extra-features 指定列名，例如：
  python3 feature_ic_analysis.py --file output/AAPL_with_short_interest.csv \\
      --extra-features short_interest_z short_volume_pct
"""

import argparse
import pandas as pd
import numpy as np
from scipy import stats

# These are the 6 (or 7 incl. inst_net_z) raw features compute_features()
# produces in signal_generator_v3.py — kept in sync manually since the CSV
# output already contains them as columns.
CORE_FEATURES = [
    "ofi_z", "rvol", "impact_eff_z", "liq_abs_z",
    "vwap_dev", "clv", "price_persistence",
]
FLOW_FEATURE = "inst_net_z"  # only present when main-flow was available


def add_forward_returns(df: pd.DataFrame, horizons: list) -> pd.DataFrame:
    df = df.copy()
    for h in horizons:
        df[f"fwd_ret_{h}"] = df["close"].pct_change(h).shift(-h)
    return df


def single_feature_ic(df: pd.DataFrame, feature: str, horizons: list) -> pd.DataFrame:
    """
    Same method as backtest.py's information_coefficient(), but applied to
    one raw feature directly instead of the blended final_score. This tells
    us whether THIS feature, on its own, has any relationship to future
    returns — independent of how much weight it's currently given.
    """
    results = []
    if feature not in df.columns:
        return pd.DataFrame()

    for h in horizons:
        col = f"fwd_ret_{h}"
        sub = df[[feature, col]].dropna()
        if len(sub) < 10:
            continue
        # Some features are directional (positive = bullish), check correlation
        # sign too — a feature with a strong NEGATIVE ic might still be useful
        # if used with a flipped sign, so we report sign explicitly.
        ic, p = stats.spearmanr(sub[feature], sub[col])
        results.append({
            "feature": feature,
            "horizon": f"{h} bar",
            "n": len(sub),
            "ic": ic,
            "p_value": p,
            "abs_ic": abs(ic),
            "significant": p < 0.05,
        })
    return pd.DataFrame(results)


def rate_ic(abs_ic: float) -> str:
    if abs_ic > 0.10:
        return "⭐⭐⭐ strong"
    elif abs_ic > 0.05:
        return "⭐⭐ moderate"
    else:
        return "⭐ weak"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="signal_generator output CSV")
    parser.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 6, 12, 24])
    parser.add_argument("--extra-features", nargs="*", default=[],
                        help="Additional column names to test (e.g. candidate new "
                             "features like short_interest_z, large_trade_total_z — "
                             "these must already be present as columns in --file)")
    args = parser.parse_args()

    df = pd.read_csv(args.file, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    print(f"[OK] Loaded {len(df)} rows from {args.file}")

    df = add_forward_returns(df, args.horizons)

    features_to_test = list(CORE_FEATURES)
    if FLOW_FEATURE in df.columns and df[FLOW_FEATURE].abs().sum() > 0:
        features_to_test.append(FLOW_FEATURE)
    else:
        print(f"[INFO] {FLOW_FEATURE} not present or all-zero — skipping (no main-flow in this file)")

    missing_core = [f for f in features_to_test if f not in df.columns]
    if missing_core:
        print(f"[WARN] Expected features missing from file: {missing_core}")
        features_to_test = [f for f in features_to_test if f in df.columns]

    for extra in args.extra_features:
        if extra not in df.columns:
            print(f"[WARN] --extra-features '{extra}' not found in file columns — skipping")
            continue
        features_to_test.append(extra)

    print(f"\n[Testing {len(features_to_test)} features]: {features_to_test}\n")

    all_results = []
    for feat in features_to_test:
        res = single_feature_ic(df, feat, args.horizons)
        if not res.empty:
            all_results.append(res)

    if not all_results:
        print("[FATAL] No IC results computed — check that features exist and have valid data")
        return

    full = pd.concat(all_results, ignore_index=True)

    # ── Per-feature summary: average |IC| across horizons, and how many
    #    horizons were statistically significant. This is the headline
    #    number for "does this feature actually carry information".
    print("=" * 70)
    print("  PER-FEATURE SUMMARY (averaged across horizons)")
    print("=" * 70)
    summary = full.groupby("feature").agg(
        avg_abs_ic=("abs_ic", "mean"),
        max_abs_ic=("abs_ic", "max"),
        n_significant=("significant", "sum"),
        n_horizons=("horizon", "count"),
    ).reset_index()
    summary["rating"] = summary["avg_abs_ic"].apply(rate_ic)
    summary = summary.sort_values("avg_abs_ic", ascending=False)
    summary["avg_abs_ic"] = summary["avg_abs_ic"].round(4)
    summary["max_abs_ic"] = summary["max_abs_ic"].round(4)
    summary["sig_horizons"] = summary["n_significant"].astype(str) + "/" + summary["n_horizons"].astype(str)
    print(summary[["feature", "avg_abs_ic", "max_abs_ic", "sig_horizons", "rating"]].to_string(index=False))

    # ── Full breakdown by horizon, for features that pass a minimum bar ──
    print(f"\n{'='*70}")
    print("  FULL BREAKDOWN BY HORIZON")
    print(f"{'='*70}")
    for feat in summary["feature"]:
        sub = full[full["feature"] == feat].copy()
        sub["ic"] = sub["ic"].round(4)
        sub["p_value"] = sub["p_value"].round(4)
        print(f"\n  {feat}")
        print(sub[["horizon", "n", "ic", "p_value", "significant"]].to_string(index=False))

    # ── Sign consistency check: does the feature's correlation flip sign
    #    across horizons? A feature that's +IC at 1bar and -IC at 24bar is
    #    unstable and risky to assign a fixed weight to.
    print(f"\n{'='*70}")
    print("  SIGN CONSISTENCY (flip = unstable, risky for a FIXED weight)")
    print(f"{'='*70}")
    for feat in summary["feature"]:
        sub = full[full["feature"] == feat]
        signs = np.sign(sub["ic"])
        consistent = (signs == signs.iloc[0]).all()
        flag = "" if consistent else "  [WARN: sign flips across horizons]"
        print(f"  {feat:<20} {'consistent' if consistent else 'INCONSISTENT'}{flag}")

    out_path = args.file.replace(".csv", "_feature_ic.csv")
    full.to_csv(out_path, index=False)
    print(f"\n[SAVED] Full results -> {out_path}")
    print(f"\n[NOTE] Compare avg_abs_ic here against the blended final_score's IC")
    print(f"       from backtest.py's output. If a core feature's IC is much")
    print(f"       weaker than its current fixed weight implies, that's a")
    print(f"       candidate for re-weighting (not retraining — see v2's Lasso")
    print(f"       lesson on why NOT to auto-learn weights from small samples).")


if __name__ == "__main__":
    main()
