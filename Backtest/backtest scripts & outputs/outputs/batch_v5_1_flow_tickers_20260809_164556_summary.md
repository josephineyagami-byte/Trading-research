# v5.1 Flow Ticker Batch Summary

- Generated: 20260809_164556
- Universe: 9 tickers with known raw-trades coverage
- OK: 9 / 9

| Ticker | Latest Signal | Regimes | Confidence | WF | SDB | Insight |
|---|---|---|---:|---|---|---|
| NVDA | neutral / watch_long | price=bullish_price_confirmation<br>flow=raw_distribution_pressure<br>short=low_and_falling_short_pressure<br>dark=normal_delayed_darkpool_activity | 18.5 | 3.31% / Sharpe 1.39 | -1.78% / Sharpe -0.70 | bullish_watch_flow_not_confirmed |
| AAPL | distribution / short | price=short_term_rebound_inside_weak_trend<br>flow=raw_distribution_pressure<br>short=stable_short_pressure<br>dark=normal_delayed_darkpool_activity | 15.2 | 8.42% / Sharpe nan | 0.49% / Sharpe 0.74 | confirmed_distribution |
| ABBV | neutral / watch_short | price=bearish_price_confirmation<br>flow=flow_missing_bar<br>short=short_volume_missing<br>dark=below_normal_delayed_darkpool_activity | 44.3 | -23.54% / Sharpe -7.40 | -0.02% / Sharpe 0.17 | bearish_watch_flow_not_confirmed |
| XLK | neutral / neutral | price=bullish_price_confirmation<br>flow=raw_distribution_pressure<br>short=stable_short_pressure<br>dark=normal_delayed_darkpool_activity | 12.2 | 6.24% / Sharpe 1.99 | -11.74% / Sharpe -4.67 | neutral_or_conflicted |
| XLF | neutral / neutral | price=bullish_price_confirmation<br>flow=buying_pressure_fading<br>short=high_short_pressure<br>dark=normal_delayed_darkpool_activity | 8.5 | 15.69% / Sharpe 6.75 | -5.95% / Sharpe -4.87 | neutral_or_conflicted |
| XLE | neutral / neutral | price=short_term_pullback_inside_strong_trend<br>flow=selling_pressure_easing<br>short=stable_short_pressure<br>dark=normal_delayed_darkpool_activity | 4.9 | -7.70% / Sharpe -2.03 | -17.89% / Sharpe -8.16 | neutral_or_conflicted |
| XLV | strong_accumulation / long | price=bullish_price_confirmation<br>flow=raw_accumulation_pressure<br>short=high_and_rising_short_pressure<br>dark=normal_delayed_darkpool_activity | 58.5 | -2.43% / Sharpe -1.16 | -8.08% / Sharpe -4.59 | squeeze_or_absorption_watch |
| XLY | distribution / short | price=bullish_price_confirmation<br>flow=raw_distribution_pressure<br>short=high_and_rising_short_pressure<br>dark=normal_delayed_darkpool_activity | 19.2 | -3.57% / Sharpe -1.72 | -1.74% / Sharpe -0.98 | confirmed_distribution |
| SOXS | neutral / watch_short | price=short_term_pullback_inside_strong_trend<br>flow=flow_missing_bar<br>short=rising_short_pressure<br>dark=normal_delayed_darkpool_activity | 35.2 |  / Sharpe  |  / Sharpe  | bearish_watch_flow_not_confirmed |

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

### SOXS
- Why: 偏空观察信号: price=short_term_pullback_inside_strong_trend, flow=flow_missing_bar, short=rising_short_pressure, darkpool=normal_delayed_darkpool_activity, flow_quality=low, score=-0.586.
- Risk: mainflow/trades 覆盖不足，信号主要来自价格和 OHLCV
- Next: 下一步先等 raw flow 从净流入/买盘衰退转为净流出；确认前只作为 bearish watch，不作为正式 short candidate。

