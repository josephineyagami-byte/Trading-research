"""
fetch_candidate_features.py — 拉取候选新特征并对齐到已有 signal CSV 的时间轴

四个候选特征：
  1. short_interest, days_to_cover — FINRA 双周空头持仓
  2. short_volume_pct — FINRA 每日做空量占比
  3. dark_pool_pct — FINRA 暗池周度占比，自算（ats_shares / 自己的周度K线volume）
  4. large_trade_total — 复用已验证的去重+tick rule逻辑，统计总活跃度（不分方向）

用法：
  python3 fetch_candidate_features.py --file output/AAPL_1h_xxx_v3_signals.csv
"""

import argparse
import sys
import time as time_module
from datetime import datetime, timedelta

import pandas as pd
import requests

from recompute_mainflow_v2 import (
    fetch_with_resume, dedupe, apply_tick_rule,
)

BASE_URL = "http://104.192.7.156:8000"
TIMEOUT = 60


def fetch_json(path, params, max_retries=3, retry_delay=3):
    url = BASE_URL + path
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            arr = data if isinstance(data, list) else (data.get("data") or data.get("rows") or [])
            return arr, True
        except requests.exceptions.RequestException as e:
            print(f"  [WARN] attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                time_module.sleep(retry_delay)
    print(f"  [ERROR] giving up on {path} {params} after {max_retries} attempts")
    return [], False


def fetch_short_interest(ticker, from_date, to_date):
    arr, ok = fetch_json("/api/short-interest",
                          {"ticker": ticker, "from": from_date, "to": to_date})
    if not ok or not arr:
        print(f"[WARN] No short-interest data for {ticker} {from_date}->{to_date}")
        return None
    df = pd.DataFrame(arr)
    required = {"settlement_date", "short_interest", "avg_daily_volume", "days_to_cover"}
    missing = required - set(df.columns)
    if missing:
        print(f"[WARN] short-interest response missing columns: {missing}. Got: {list(df.columns)}")
        return None
    df["settlement_date"] = pd.to_datetime(df["settlement_date"])
    df = df.sort_values("settlement_date").reset_index(drop=True)
    print(f"[OK] short-interest: {len(df)} bi-weekly settlement records "
          f"[{df['settlement_date'].min().date()} -> {df['settlement_date'].max().date()}]")
    return df


def merge_short_interest(signal_df, si_df):
    if si_df is None:
        signal_df["short_interest"] = pd.NA
        signal_df["days_to_cover"] = pd.NA
        return signal_df

    signal_df = signal_df.sort_values("datetime").reset_index(drop=True)
    si_sorted = si_df.sort_values("settlement_date").reset_index(drop=True)

    merged = pd.merge_asof(
        signal_df, si_sorted[["settlement_date", "short_interest", "days_to_cover"]],
        left_on="datetime", right_on="settlement_date",
        direction="backward",
    )
    merged = merged.drop(columns=["settlement_date"])

    n_filled = merged["short_interest"].notna().sum()
    print(f"[OK] short-interest merged: {n_filled}/{len(merged)} bars have a value "
          f"({n_filled/len(merged):.1%})")
    return merged


def fetch_short_volume(ticker, from_date, to_date):
    arr, ok = fetch_json("/api/short-volume",
                          {"ticker": ticker, "from": from_date, "to": to_date})
    if not ok or not arr:
        print(f"[WARN] No short-volume data for {ticker} {from_date}->{to_date}")
        return None
    df = pd.DataFrame(arr)
    required = {"date", "short_volume", "total_volume"}
    missing = required - set(df.columns)
    if missing:
        print(f"[WARN] short-volume response missing columns: {missing}. Got: {list(df.columns)}")
        return None
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["short_volume_pct"] = df["short_volume"] / df["total_volume"].replace(0, pd.NA)
    df = df.sort_values("date").reset_index(drop=True)
    print(f"[OK] short-volume: {len(df)} daily records "
          f"[{df['date'].min().date()} -> {df['date'].max().date()}]")
    return df[["date", "short_volume_pct"]]


def merge_short_volume(signal_df, sv_df):
    if sv_df is None:
        signal_df["short_volume_pct"] = pd.NA
        return signal_df
    signal_df = signal_df.copy()
    signal_df["_date"] = signal_df["datetime"].dt.normalize()
    merged = signal_df.merge(sv_df, left_on="_date", right_on="date", how="left")
    merged = merged.drop(columns=["_date", "date"])
    n_filled = merged["short_volume_pct"].notna().sum()
    print(f"[OK] short-volume merged: {n_filled}/{len(merged)} bars have a value "
          f"({n_filled/len(merged):.1%})")
    return merged


def fetch_dark_pool(ticker, days=400):
    arr, ok = fetch_json("/api/dark-pool/ticker", {"ticker": ticker, "days": days})
    if not ok or not arr:
        print(f"[WARN] No dark-pool data for {ticker}")
        return None
    df = pd.DataFrame(arr)
    required = {"week_start", "ats_shares", "ats_trades"}
    missing = required - set(df.columns)
    if missing:
        print(f"[WARN] dark-pool response missing columns: {missing}. Got: {list(df.columns)}")
        return None
    df["week_start"] = pd.to_datetime(df["week_start"])
    df = df.sort_values("week_start").reset_index(drop=True)
    print(f"[OK] dark-pool: {len(df)} weekly records "
          f"[{df['week_start'].min().date()} -> {df['week_start'].max().date()}]")
    return df[["week_start", "ats_shares", "ats_trades"]]


def merge_dark_pool(signal_df, dp_df):
    if dp_df is None:
        signal_df["dark_pool_pct"] = pd.NA
        signal_df["ats_shares"] = pd.NA
        return signal_df

    signal_df = signal_df.sort_values("datetime").reset_index(drop=True)

    vol_by_week = signal_df.copy()
    vol_by_week["week_start"] = vol_by_week["datetime"].dt.to_period("W-SUN").dt.start_time
    weekly_volume = vol_by_week.groupby("week_start")["volume"].sum().reset_index()
    weekly_volume = weekly_volume.rename(columns={"volume": "weekly_kline_volume"})

    dp_sorted = dp_df.sort_values("week_start").reset_index(drop=True)
    dp_with_vol = dp_sorted.merge(weekly_volume, on="week_start", how="left")
    dp_with_vol["dark_pool_pct"] = (
        dp_with_vol["ats_shares"] / dp_with_vol["weekly_kline_volume"].replace(0, pd.NA)
    )

    n_missing_denom = dp_with_vol["weekly_kline_volume"].isna().sum()
    if n_missing_denom:
        print(f"[INFO] {n_missing_denom} dark-pool week(s) have no matching kline volume "
              f"in this file's date range — dark_pool_pct will be NaN for those weeks")

    merged = pd.merge_asof(
        signal_df, dp_with_vol[["week_start", "dark_pool_pct", "ats_shares"]],
        left_on="datetime", right_on="week_start",
        direction="backward",
    )
    merged = merged.drop(columns=["week_start"])

    n_filled = merged["dark_pool_pct"].notna().sum()
    print(f"[OK] dark-pool merged: {n_filled}/{len(merged)} bars have a value "
          f"({n_filled/len(merged):.1%})")
    return merged


def fetch_large_trade_total(ticker, from_date, to_date, interval,
                            fetch_min_size=1000, chunk_days=7):
    print(f"\n[Large Trade Total] Fetching + deduping for {ticker} "
          f"({from_date} -> {to_date})...")
    raw, failed_segments, _paths = fetch_with_resume(
        ticker, from_date, to_date, fetch_min_size=fetch_min_size,
        chunk_days=chunk_days, retry_failed_only=False)

    if failed_segments:
        print(f"[WARN] {len(failed_segments)} segment(s) failed — large_trade_total "
              f"will be INCOMPLETE for those periods, treat with caution")

    if not raw:
        print("[WARN] No large-trades data fetched for large_trade_total")
        return None

    df = pd.DataFrame(raw)
    required_cols = {"time", "price", "size", "exchange"}
    if required_cols - set(df.columns):
        print(f"[WARN] large-trades response missing expected columns")
        return None

    df = dedupe(df)
    df = apply_tick_rule(df)
    df["datetime"] = pd.to_datetime(df["time"], unit="ms")

    if interval == "1d":
        df["bucket"] = df["datetime"].dt.normalize()
    else:
        df["bucket"] = df["datetime"].dt.floor("h")

    agg = df.groupby("bucket").agg(
        large_trade_total=("notional", "sum"),
        large_trade_count=("notional", "count"),
    ).reset_index()
    print(f"[OK] large_trade_total: {len(agg)} {interval} bars aggregated "
          f"from {len(df)} deduped trades")
    return agg


def merge_large_trade_total(signal_df, ltt_df, interval):
    if ltt_df is None:
        signal_df["large_trade_total"] = 0.0
        signal_df["large_trade_count"] = 0
        return signal_df
    signal_df = signal_df.copy()
    if interval == "1d":
        signal_df["_key"] = signal_df["datetime"].dt.normalize()
    else:
        signal_df["_key"] = signal_df["datetime"].dt.floor("h")
    merged = signal_df.merge(ltt_df, left_on="_key", right_on="bucket", how="left")
    merged = merged.drop(columns=["_key", "bucket"])
    merged["large_trade_total"] = merged["large_trade_total"].fillna(0.0)
    merged["large_trade_count"] = merged["large_trade_count"].fillna(0).astype(int)
    n_nonzero = (merged["large_trade_total"] > 0).sum()
    print(f"[OK] large_trade_total merged: {n_nonzero}/{len(merged)} bars have activity "
          f"({n_nonzero/len(merged):.1%})")
    return merged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Existing signal_generator output CSV")
    parser.add_argument("--ticker", default=None, help="Override ticker (auto-detected from filename)")
    parser.add_argument("--interval", default="1h", choices=["1h", "1d"])
    parser.add_argument("--skip-large-trade-total", action="store_true",
                        help="Skip the large-trade-total fetch (slowest part)")
    args = parser.parse_args()

    df = pd.read_csv(args.file, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    print(f"[OK] Loaded {len(df)} rows from {args.file}")

    ticker = args.ticker
    if not ticker:
        import re
        from pathlib import Path
        m = re.match(r"([A-Z]+)_", Path(args.file).name)
        ticker = m.group(1) if m else None
        if not ticker:
            sys.exit("[FATAL] Could not auto-detect ticker from filename — pass --ticker")
    ticker = ticker.upper()

    from_date = df["datetime"].min().strftime("%Y-%m-%d")
    to_date = df["datetime"].max().strftime("%Y-%m-%d")
    print(f"[Range] {ticker} | {from_date} -> {to_date}")

    print(f"\n{'='*60}\n  1. Short Interest\n{'='*60}")
    si_df = fetch_short_interest(ticker, from_date, to_date)
    df = merge_short_interest(df, si_df)

    print(f"\n{'='*60}\n  2. Short Volume\n{'='*60}")
    sv_df = fetch_short_volume(ticker, from_date, to_date)
    df = merge_short_volume(df, sv_df)

    print(f"\n{'='*60}\n  2b. Dark Pool\n{'='*60}")
    dp_df = fetch_dark_pool(ticker)
    df = merge_dark_pool(df, dp_df)

    if not args.skip_large_trade_total:
        print(f"\n{'='*60}\n  3. Large Trade Total\n{'='*60}")
        ltt_df = fetch_large_trade_total(ticker, from_date, to_date, args.interval)
        df = merge_large_trade_total(df, ltt_df, args.interval)
    else:
        print("\n[SKIPPED] large_trade_total (--skip-large-trade-total)")
        df["large_trade_total"] = 0.0
        df["large_trade_count"] = 0

    out_path = args.file.replace(".csv", "_with_candidates.csv")
    df.to_csv(out_path, index=False)
    print(f"\n[SAVED] {out_path}")
    print(f"\n[NEXT STEP] Test these candidates with the same IC framework as core features:")
    print(f"  python3 feature_ic_analysis.py --file {out_path} \\")
    print(f"      --extra-features short_interest days_to_cover short_volume_pct "
          f"dark_pool_pct large_trade_total")


if __name__ == "__main__":
    main()
