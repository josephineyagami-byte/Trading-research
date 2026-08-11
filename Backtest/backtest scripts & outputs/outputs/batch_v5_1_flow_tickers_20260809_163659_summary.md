# v5.1 Flow Ticker Batch Summary

- Generated: 20260809_163659
- Universe: 9 tickers with known raw-trades coverage
- OK: 8 / 9

| Ticker | Latest Signal | Regimes | Confidence | WF | SDB | Insight |
|---|---|---|---:|---|---|---|
| NVDA | neutral / watch_long | price=bullish_price_confirmation<br>flow=raw_distribution_pressure<br>short=low_and_falling_short_pressure<br>dark=normal_delayed_darkpool_activity | 18.5 | 3.31% / Sharpe 1.39 |  / Sharpe  | bullish_watch_flow_not_confirmed |
| AAPL | distribution / short | price=short_term_rebound_inside_weak_trend<br>flow=raw_distribution_pressure<br>short=stable_short_pressure<br>dark=normal_delayed_darkpool_activity | 15.2 | 8.42% / Sharpe nan |  / Sharpe  | confirmed_distribution |
| ABBV | neutral / watch_short | price=bearish_price_confirmation<br>flow=flow_missing_bar<br>short=short_volume_missing<br>dark=below_normal_delayed_darkpool_activity | 44.3 | -23.54% / Sharpe -7.40 |  / Sharpe  | bearish_watch_flow_not_confirmed |
| XLK | neutral / neutral | price=bullish_price_confirmation<br>flow=raw_distribution_pressure<br>short=stable_short_pressure<br>dark=normal_delayed_darkpool_activity | 12.2 | 6.24% / Sharpe 1.99 |  / Sharpe  | neutral_or_conflicted |
| XLF | neutral / neutral | price=bullish_price_confirmation<br>flow=buying_pressure_fading<br>short=high_short_pressure<br>dark=normal_delayed_darkpool_activity | 8.5 | 15.69% / Sharpe 6.75 |  / Sharpe  | neutral_or_conflicted |
| XLE | neutral / neutral | price=short_term_pullback_inside_strong_trend<br>flow=selling_pressure_easing<br>short=stable_short_pressure<br>dark=normal_delayed_darkpool_activity | 4.9 | -7.70% / Sharpe -2.03 |  / Sharpe  | neutral_or_conflicted |
| XLV | strong_accumulation / long | price=bullish_price_confirmation<br>flow=raw_accumulation_pressure<br>short=high_and_rising_short_pressure<br>dark=normal_delayed_darkpool_activity | 58.5 | -2.43% / Sharpe -1.16 |  / Sharpe  | squeeze_or_absorption_watch |
| XLY | distribution / short | price=bullish_price_confirmation<br>flow=raw_distribution_pressure<br>short=high_and_rising_short_pressure<br>dark=normal_delayed_darkpool_activity | 19.2 | -3.57% / Sharpe -1.72 |  / Sharpe  | confirmed_distribution |
| SOXS | ERROR |  |  |  |  | 45/256 bars
[CACHED] SOXS 1d -> /Users/zz/Downloads/Quant Trading Research/raw_data_cache/SOXS_1d_2025-08-01_2026-08-09_v5_1.csv
[Training HMM (fixed 3 states)...]

[HMM] State profiles (training period):
           ofi_mean  rvol_mean  inst_mean  ret_mean  count
hmm_state                                                 
0         -3.242818   1.441622        NaN -0.040073     34
1         -2.822118   1.392446        NaN -0.012795     34
2         -0.327590   1.147591        NaN -0.004903    187
Traceback (most recent call last):
  File "/Users/zz/Library/Python/3.9/lib/python/site-packages/pandas/core/indexes/base.py", line 3812, in get_loc
    return self._engine.get_loc(casted_key)
  File "pandas/_libs/index.pyx", line 167, in pandas._libs.index.IndexEngine.get_loc
  File "pandas/_libs/index.pyx", line 175, in pandas._libs.index.IndexEngine.get_loc
  File "pandas/_libs/index_class_helper.pxi", line 70, in pandas._libs.index.Int64Engine._check_type
KeyError: nan

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/Users/zz/Downloads/Quant Trading Research/signal_generator_v5_1.py", line 862, in <module>
    main()
  File "/Users/zz/Downloads/Quant Trading Research/signal_generator_v5_1.py", line 852, in main
    df = v4.fit_hmm(df, n_states=args.hmm_states, train_end=args.train_end)
  File "/Users/zz/Downloads/Quant Trading Research/signal_generator_v4.py", line 747, in fit_hmm
    mean_val = state_profiles.loc[state_id, ofi_col]
  File "/Users/zz/Library/Python/3.9/lib/python/site-packages/pandas/core/indexing.py", line 1184, in __getitem__
    return self.obj._get_value(*key, takeable=self._takeable)
  File "/Users/zz/Library/Python/3.9/lib/python/site-packages/pandas/core/frame.py", line 4232, in _get_value
    row = self.index.get_loc(index)
  File "/Users/zz/Library/Python/3.9/lib/python/site-packages/pandas/core/indexes/base.py", line 3819, in get_loc
    raise KeyError(key) from err
KeyError: nan
 |

## Latest Explanation

### NVDA
- Why: 偏多观察信号: price=bullish_price_confirmation, flow=raw_distribution_pressure, short=low_and_falling_short_pressure, darkpool=normal_delayed_darkpool_activity, flow_quality=low, score=+0.531.
- Risk: mainflow/trades 覆盖不足，信号主要来自价格和 OHLCV；raw flow 仍是净流出，不能当 confirmed accumulation
- Next: 下一步先等 raw flow 从净流出/卖压缓和转为净流入；确认前只作为 bullish watch，不作为正式 long candidate。

### AAPL
- Why: 偏空信号: price=short_term_rebound_inside_weak_trend, flow=raw_distribution_pressure, short=stable_short_pressure, darkpool=normal_delayed_darkpool_activity, flow_quality=medium, score=-0.174.
- Risk: 主要风险是后续 price/flow 不能延续同向确认
- Next: 下一步看 raw flow 是否继续净流出、价格是否维持弱势；若 short pressure 同时上升，空头 conviction 才能提高。

### ABBV
- Why: 偏空观察信号: price=bearish_price_confirmation, flow=flow_missing_bar, short=short_volume_missing, darkpool=below_normal_delayed_darkpool_activity, flow_quality=high, score=-0.531.
- Risk: 缺少 short_volume，无法确认 short pressure/squeeze
- Next: 下一步先等 raw flow 从净流入/买盘衰退转为净流出；确认前只作为 bearish watch，不作为正式 short candidate。

### XLK
- Why: 中性/冲突信号: price=bullish_price_confirmation, flow=raw_distribution_pressure, short=stable_short_pressure, darkpool=normal_delayed_darkpool_activity, flow_quality=high, score=+0.245.
- Risk: 主要风险是后续 price/flow 不能延续同向确认
- Next: 下一步等 price、raw flow、short volume 至少两个方向一致后再升级为 long/short candidate。

### XLF
- Why: 中性/冲突信号: price=bullish_price_confirmation, flow=buying_pressure_fading, short=high_short_pressure, darkpool=normal_delayed_darkpool_activity, flow_quality=high, score=+0.085.
- Risk: 主要风险是后续 price/flow 不能延续同向确认
- Next: 下一步等 price、raw flow、short volume 至少两个方向一致后再升级为 long/short candidate。

### XLE
- Why: 中性/冲突信号: price=short_term_pullback_inside_strong_trend, flow=selling_pressure_easing, short=stable_short_pressure, darkpool=normal_delayed_darkpool_activity, flow_quality=high, score=-0.049.
- Risk: 主要风险是后续 price/flow 不能延续同向确认
- Next: 下一步等 price、raw flow、short volume 至少两个方向一致后再升级为 long/short candidate。

### XLV
- Why: 偏多信号: price=bullish_price_confirmation, flow=raw_accumulation_pressure, short=high_and_rising_short_pressure, darkpool=normal_delayed_darkpool_activity, flow_quality=high, score=+0.585.
- Risk: 主要风险是后续 price/flow 不能延续同向确认
- Next: 下一步看 raw flow 是否维持净流入、价格是否守住 5/20 bar 趋势；若 short pressure 高但价格不跌，可升级为 squeeze/absorption watch。

### XLY
- Why: 偏空信号: price=bullish_price_confirmation, flow=raw_distribution_pressure, short=high_and_rising_short_pressure, darkpool=normal_delayed_darkpool_activity, flow_quality=high, score=-0.192.
- Risk: 主要风险是后续 price/flow 不能延续同向确认
- Next: 下一步看 raw flow 是否继续净流出、价格是否维持弱势；若 short pressure 同时上升，空头 conviction 才能提高。

