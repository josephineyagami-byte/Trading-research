"""
diagnose_coverage.py — 诊断 main-flow coverage 偏低的原因

不改动 v3 的任何逻辑，只是把 klines 和 main-flow 两边的时间戳分布
单独打印出来，定位到底是：
  (a) main-flow 数据本身在某些时段稀疏/缺失
  (b) 还是合并对齐时把本该匹配上的 bar 错配成了 0

用法（和 signal_generator_v3.py 同目录运行）：
  python3 diagnose_coverage.py --ticker AAPL --interval 1h --from-date 2025-07-01
"""

import argparse
import pandas as pd
import numpy as np

from signal_generator_v3 import load_klines, load_main_flow, merge_flow

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--from-date", default="2025-07-01")
    parser.add_argument("--to-date", default=None)
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Diagnosing coverage: {args.ticker} | {args.interval}")
    print(f"{'='*60}\n")

    kl = load_klines(args.ticker, args.interval, limit=99999,
                      from_date=args.from_date, to_date=args.to_date)
    fl = load_main_flow(args.ticker, args.interval, limit=99999,
                         from_date=args.from_date, to_date=args.to_date)

    if fl is None:
        print("[FATAL] No main-flow data returned at all.")
        return

    # ── 1. Basic date range comparison
    print("\n[1] Date range comparison")
    print(f"  Klines    : {kl['datetime'].min()} -> {kl['datetime'].max()}  ({len(kl)} bars)")
    date_col = "hour" if "hour" in fl.columns else "date"
    print(f"  Main-flow : {fl[date_col].min()} -> {fl[date_col].max()}  ({len(fl)} bars)")

    # ── 2. Build the merge key exactly like merge_flow() does
    kl = kl.copy()
    if "hour" in fl.columns:
        kl["key"] = kl["datetime"].dt.floor("H")
        fl_key = fl["hour"]
    else:
        kl["key"] = kl["datetime"].dt.normalize()
        fl_key = fl["date"]

    kl_keys = set(kl["key"])
    fl_keys = set(fl_key)

    matched   = kl_keys & fl_keys
    kl_only   = kl_keys - fl_keys   # kline hours with NO matching flow bar at all
    fl_only   = fl_keys - kl_keys   # flow hours that don't correspond to any kline bar (off-hours flow data)

    print(f"\n[2] Key overlap (by hour bucket)")
    print(f"  Unique kline hours      : {len(kl_keys)}")
    print(f"  Unique main-flow hours  : {len(fl_keys)}")
    print(f"  Matched hours           : {len(matched)}  ({len(matched)/len(kl_keys):.1%} of kline hours)")
    print(f"  Kline hours w/ NO flow  : {len(kl_only)}  ({len(kl_only)/len(kl_keys):.1%})")
    print(f"  Flow hours w/ no kline  : {len(fl_only)}")

    # ── 3. Of the matched hours, how many actually have non-zero inst_net?
    fl_nonzero = fl[fl["inst_net"].abs() > 0.01]
    fl_nonzero_keys = set(fl_nonzero[date_col])
    print(f"\n[3] Of matched hours, how many have non-trivial inst_net?")
    print(f"  Flow hours with |inst_net| > 0.01 : {len(fl_nonzero_keys)} / {len(fl_keys)} "
          f"({len(fl_nonzero_keys)/max(len(fl_keys),1):.1%} of all flow hours)")

    effective_coverage = len(matched & fl_nonzero_keys) / len(kl_keys)
    print(f"  => Effective coverage (matched AND non-zero) : {effective_coverage:.1%}")

    # ── 4. Missing hours: are they clustered (specific dates/times) or scattered?
    if kl_only:
        missing = pd.Series(sorted(kl_only))
        print(f"\n[4] Sample of kline hours with NO main-flow match (first 15):")
        for t in missing.head(15):
            print(f"    {t}")
        # Group by date to see if whole days are missing
        missing_dates = pd.Series([t.date() for t in missing])
        date_counts = missing_dates.value_counts().sort_index()
        print(f"\n  Missing hours grouped by date (top 10 dates by missing count):")
        print(date_counts.sort_values(ascending=False).head(10).to_string())

        # Group by hour-of-day (ET) to see if specific hours are systematically missing
        missing_et_hour = pd.Series([((t - pd.Timedelta(hours=4)).hour) for t in missing])
        print(f"\n  Missing hours grouped by hour-of-day (UTC-4 approx ET):")
        print(missing_et_hour.value_counts().sort_index().to_string())

        # ── Full missing-date export ──
        # A trading day is counted "fully missing" if it has >= 5 missing hours
        # (out of ~6 expected hourly bars in the 9:35-16:00 ET window).
        # Days with 1-4 missing hours are "partial" (could be holidays, half-days,
        # or genuinely sparse flow, not necessarily a data gap).
        full_missing_threshold = 5
        full_missing_dates = date_counts[date_counts >= full_missing_threshold].sort_index()
        partial_missing_dates = date_counts[date_counts < full_missing_threshold].sort_index()

        print(f"\n[4b] FULL missing trading days (>={full_missing_threshold} of ~6 hourly bars gone): "
              f"{len(full_missing_dates)} days")
        print(full_missing_dates.to_string())

        print(f"\n[4c] PARTIAL missing days (<{full_missing_threshold} hourly bars gone, "
              f"likely holidays/half-days/sparse): {len(partial_missing_dates)} days")
        print(partial_missing_dates.to_string())

        # Find contiguous runs of fully-missing days (these are the most likely
        # candidates for "server was down" / "database truncated" gaps)
        full_dates_sorted = sorted(full_missing_dates.index)
        runs = []
        if full_dates_sorted:
            run_start = full_dates_sorted[0]
            prev = full_dates_sorted[0]
            for d in full_dates_sorted[1:]:
                # allow weekend gaps (up to 3 calendar days) to still count as "contiguous"
                if (d - prev).days <= 3:
                    prev = d
                else:
                    runs.append((run_start, prev))
                    run_start = d
                    prev = d
            runs.append((run_start, prev))

        print(f"\n[4d] Contiguous runs of fully-missing trading days "
              f"({len(runs)} run(s), weekend gaps tolerated):")
        for start, end in runs:
            span_days = (end - start).days + 1
            print(f"    {start} -> {end}  ({span_days} calendar days)")

        # Export full list to CSV
        out_path = f"missing_dates_{args.ticker}_{args.interval}.csv"
        export_df = pd.DataFrame({
            "date": list(full_missing_dates.index) + list(partial_missing_dates.index),
            "missing_hours": list(full_missing_dates.values) + list(partial_missing_dates.values),
            "category": (["full"] * len(full_missing_dates)) + (["partial"] * len(partial_missing_dates)),
        }).sort_values("date").reset_index(drop=True)
        export_df.to_csv(out_path, index=False)
        print(f"\n[SAVED] Full missing-date list -> {out_path}")

        # ── 4e. Cross-check against kline volume ──
        # main-flow is derived from the trades table with a size threshold filter
        # (exact threshold TBD — teammate is writing it up). So a day with NO
        # main-flow rows could simply mean no trade that day cleared the
        # super/large size cutoff — NOT a data gap. We can't know the threshold
        # yet, but we CAN check: did missing days also have unusually LOW volume
        # on the klines (consistent with "quiet day, nothing big traded") or
        # NORMAL/HIGH volume (more consistent with a pipeline gap, since normal
        # volume days should statistically produce at least some qualifying trades)?
        print(f"\n[4e] Cross-check: kline volume on missing days vs normal days")
        kl["trade_date"] = kl["datetime"].dt.date
        daily_vol = kl.groupby("trade_date")["volume"].sum()

        full_missing_set = set(full_missing_dates.index)
        normal_dates = set(daily_vol.index) - full_missing_set

        if full_missing_set and normal_dates:
            vol_missing = daily_vol.loc[daily_vol.index.isin(full_missing_set)]
            vol_normal  = daily_vol.loc[daily_vol.index.isin(normal_dates)]

            print(f"  Normal days     (n={len(vol_normal)}): "
                  f"median vol={vol_normal.median():,.0f}  "
                  f"mean vol={vol_normal.mean():,.0f}")
            print(f"  Fully-missing days (n={len(vol_missing)}): "
                  f"median vol={vol_missing.median():,.0f}  "
                  f"mean vol={vol_missing.mean():,.0f}")

            ratio = vol_missing.median() / vol_normal.median() if vol_normal.median() else float("nan")
            print(f"  Median volume ratio (missing/normal) : {ratio:.2f}x")

            print(f"\n  Per-missing-day volume (sorted by date):")
            print(vol_missing.sort_index().to_string())

            print(f"\n  Interpretation guide:")
            print(f"    ratio << 1  -> missing days were genuinely quiet (consistent with")
            print(f"                   threshold filtering, not a pipeline gap)")
            print(f"    ratio ~= 1 or > 1 -> missing days had normal/high volume but still")
            print(f"                   produced zero main-flow rows (more consistent with")
            print(f"                   a data pipeline gap, not a thresholding artifact)")
        else:
            print("  [SKIP] Not enough data on one side to compare.")

    # ── 5. Run the actual merge_flow() and cross-check against our manual calc
    merged = merge_flow(kl.drop(columns=["key"]), fl)
    actual_coverage = (merged["inst_net_z"].abs() > 0.01).mean()
    print(f"\n[5] Cross-check against actual merge_flow() output")
    print(f"  merge_flow() reported coverage : {actual_coverage:.1%}")
    print(f"  (for comparison) effective coverage from step 3 : {effective_coverage:.1%}")

    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
