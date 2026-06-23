"""
batch_feature_ic.py — 批量跑多个 ticker 的 signal generation + 单特征 IC 分析
"""

import argparse
import traceback

import pandas as pd
import numpy as np
from scipy import stats

from signal_generator_v3 import (
    load_klines, load_main_flow, load_large_trades,
    compute_features, merge_flow, fit_hmm, compute_signal, save_output,
)

CORE_FEATURES = [
    "ofi_z", "rvol", "impact_eff_z", "liq_abs_z",
    "vwap_dev", "clv", "price_persistence",
]
FLOW_FEATURE = "inst_net_z"
HORIZONS = [1, 3, 6, 12, 24]


def add_forward_returns(df, horizons):
    df = df.copy()
    for h in horizons:
        df[f"fwd_ret_{h}"] = df["close"].pct_change(h).shift(-h)
    return df


def single_feature_ic(df, feature, horizons):
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
                        "ic": ic, "p_value": p, "abs_ic": abs(ic),
                        "significant": p < 0.05})
    return pd.DataFrame(results)


def run_one_ticker(ticker, interval, from_date, to_date, limit):
    print(f"\n{'='*60}\n  {ticker}\n{'='*60}")

    df = load_klines(ticker, interval, limit, from_date=from_date, to_date=to_date)
    flow_df = load_main_flow(ticker, interval, limit, from_date=None, to_date=to_date)
    _ = load_large_trades(ticker, limit=200)

    df = compute_features(df)
    has_flow = flow_df is not None
    if has_flow:
        df = merge_flow(df, flow_df)

    df = fit_hmm(df, n_states=3)
    df = compute_signal(df)

    fpath = save_output(df, ticker, interval)
    print(f"[SAVED] {fpath}")

    coverage = 0.0
    if "inst_net_z" in df.columns:
        coverage = (df["inst_net_z"].abs() > 0.01).mean()

    return df, fpath, coverage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--from-date", default="2025-07-01")
    parser.add_argument("--to-date", default=None)
    parser.add_argument("--limit", default=300, type=int)
    args = parser.parse_args()

    all_summaries = []
    per_ticker_full = {}
    failures = []

    for ticker in args.tickers:
        try:
            df, fpath, coverage = run_one_ticker(
                ticker, args.interval, args.from_date, args.to_date, args.limit)
        except Exception as e:
            print(f"[ERROR] {ticker} failed: {e}")
            traceback.print_exc()
            failures.append((ticker, str(e)))
            continue

        df = add_forward_returns(df, HORIZONS)

        features_to_test = list(CORE_FEATURES)
        if FLOW_FEATURE in df.columns and df[FLOW_FEATURE].abs().sum() > 0:
            features_to_test.append(FLOW_FEATURE)

        ticker_results = []
        for feat in features_to_test:
            res = single_feature_ic(df, feat, HORIZONS)
            if not res.empty:
                ticker_results.append(res)

        if not ticker_results:
            print(f"[WARN] {ticker}: no IC results computed")
            continue

        full = pd.concat(ticker_results, ignore_index=True)
        per_ticker_full[ticker] = full

        summary = full.groupby("feature").agg(
            avg_abs_ic=("abs_ic", "mean"),
            n_significant=("significant", "sum"),
            n_horizons=("horizon", "count"),
        ).reset_index()
        summary["ticker"] = ticker
        summary["mainflow_coverage"] = coverage
        all_summaries.append(summary)

    if failures:
        print(f"\n[FAILURES] {len(failures)} ticker(s) failed and were skipped:")
        for t, err in failures:
            print(f"    {t}: {err}")

    if not all_summaries:
        print("[FATAL] No successful ticker runs — nothing to summarize")
        return

    combined = pd.concat(all_summaries, ignore_index=True)

    print(f"\n{'='*70}")
    print("  CROSS-TICKER COMPARISON: avg|IC| per feature per ticker")
    print(f"{'='*70}")
    pivot = combined.pivot(index="feature", columns="ticker", values="avg_abs_ic")
    successful_tickers = [t for t in args.tickers if t in combined["ticker"].values]
    if len(successful_tickers) != len(args.tickers):
        skipped = set(args.tickers) - set(successful_tickers)
        print(f"\n[NOTE] Cross-ticker stats below only include the "
              f"{len(successful_tickers)} ticker(s) that succeeded: {successful_tickers}")
        print(f"       Excluded (failed earlier): {sorted(skipped)}")
    pivot["mean_across_tickers"] = pivot[successful_tickers].mean(axis=1)
    pivot["std_across_tickers"] = pivot[successful_tickers].std(axis=1) if len(successful_tickers) > 1 else 0
    pivot = pivot.sort_values("mean_across_tickers", ascending=False).round(4)
    print(pivot.to_string())

    print(f"\n[Interpretation]")
    print(f"  High mean_across_tickers + low std_across_tickers = consistently useful feature")
    print(f"  High mean but high std = feature works great on SOME tickers, not others")

    print(f"\n{'='*70}")
    print("  ofi_z RANK PER TICKER (1 = strongest feature for that ticker)")
    print(f"{'='*70}")
    for ticker in args.tickers:
        if ticker not in combined["ticker"].values:
            continue
        sub = combined[combined["ticker"] == ticker].sort_values("avg_abs_ic", ascending=False).reset_index(drop=True)
        sub_core = sub[sub["feature"] != FLOW_FEATURE].reset_index(drop=True)
        if "ofi_z" in sub_core["feature"].values:
            rank = sub_core[sub_core["feature"] == "ofi_z"].index[0] + 1
            print(f"  {ticker:<8} ofi_z rank: {rank}/{len(sub_core)} "
                  f"(avg|IC|={sub_core[sub_core['feature']=='ofi_z']['avg_abs_ic'].values[0]:.4f})")

    if FLOW_FEATURE in combined["feature"].values:
        print(f"\n{'='*70}")
        print(f"  {FLOW_FEATURE} RESULTS (flagged — main-flow data quality unresolved)")
        print(f"{'='*70}")
        flow_rows = combined[combined["feature"] == FLOW_FEATURE]
        print(flow_rows[["ticker", "avg_abs_ic", "n_significant", "n_horizons", "mainflow_coverage"]]
              .assign(mainflow_coverage=lambda d: (d["mainflow_coverage"]*100).round(1).astype(str)+"%")
              .to_string(index=False))

    out_path = f"batch_feature_ic_summary_{args.interval}.csv"
    combined.to_csv(out_path, index=False)
    print(f"\n[SAVED] {out_path}")


if __name__ == "__main__":
    main()
