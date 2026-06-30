"""
fetch_benchmark.py — 只拉 OHLCV，不算特征/HMM/聚类权重，专门给
plot_inst_flow.py 的 --benchmark 参数准备数据（比如 QQQ/SPY）。

比直接跑 signal_generator_v4.py 快很多——后者会顺带拉 main-flow、
large-trades、算 compute_features/fit_hmm/compute_signal，这些
benchmark overlay 完全用不上。

用法：
  python3 fetch_benchmark.py --ticker QQQ --interval 1h --from-date 2025-07-01
  python3 fetch_benchmark.py --ticker SPY --interval 1h --from-date 2025-07-01
"""

import argparse
import os

from signal_generator_v4 import load_klines, OUTPUT_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker",    required=True)
    parser.add_argument("--interval",  default="1h")
    parser.add_argument("--from-date", default="2025-07-01")
    parser.add_argument("--to-date",   default=None)
    parser.add_argument("--limit",     default=99999, type=int)
    args = parser.parse_args()

    ticker = args.ticker.upper()
    df = load_klines(ticker, args.interval, args.limit,
                      from_date=args.from_date, to_date=args.to_date)
    if df is None or len(df) == 0:
        print(f"[FATAL] Could not load klines for {ticker}")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{ticker}_{args.interval}_benchmark.csv")
    df[["datetime", "open", "high", "low", "close", "volume"]].to_csv(out_path, index=False)
    print(f"[SAVED] {out_path}  ({len(df)} bars)")


if __name__ == "__main__":
    main()
