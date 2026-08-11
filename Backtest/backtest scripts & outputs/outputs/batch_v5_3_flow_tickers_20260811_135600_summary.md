# v5.3 Flow Ticker Batch Summary

- Generated: 20260811_135600
- Universe: 4 tickers with known raw-trades coverage
- OK: 4 / 4

| Ticker | Latest Signal | Regimes | Confidence | WF | SDB | Insight |
|---|---|---|---:|---|---|---|
| INTC | neutral / watch_long | price=short_term_rebound_inside_weak_trend<br>flow=raw_distribution_pressure<br>dist=supply_absorption<br>relative=short_term_relative_rebound vs SMH<br>L/S=0.5663640086001407/0.0944315965580994<br>short=stable_short_pressure<br>dark=normal_delayed_darkpool_activity | 22.6 |  / Sharpe  | 24.88% / Sharpe nan | bullish_watch_flow_not_confirmed |
| AMD | neutral / absorption_watch | price=short_term_rebound_inside_weak_trend<br>flow=raw_distribution_pressure<br>dist=supply_absorption<br>relative=relative_weakness vs SMH<br>L/S=0.1285267373720011/0.5439182216895665<br>short=stable_short_pressure<br>dark=normal_delayed_darkpool_activity | 21.8 | 19.62% / Sharpe 11.26 | 12.59% / Sharpe nan | supply_absorption_watch |
| NVDA | neutral / absorption_watch | price=bullish_price_confirmation<br>flow=raw_distribution_pressure<br>dist=supply_absorption<br>relative=relative_strength vs SMH<br>L/S=0.5454257724847514/0.1206629105203409<br>short=low_and_falling_short_pressure<br>dark=normal_delayed_darkpool_activity | 3.8 |  / Sharpe  |  / Sharpe  | supply_absorption_watch |
| AAPL | neutral / absorption_watch | price=short_term_rebound_inside_weak_trend<br>flow=raw_distribution_pressure<br>dist=supply_absorption<br>relative=relative_mixed vs QQQ<br>L/S=0.0/0.1737052094981131<br>short=stable_short_pressure<br>dark=normal_delayed_darkpool_activity | 12.2 |  / Sharpe  |  / Sharpe  | supply_absorption_watch |

## Latest Explanation

### INTC
- Why: 偏多观察信号: price=short_term_rebound_inside_weak_trend, flow=raw_distribution_pressure, distribution_context=supply_absorption, short=stable_short_pressure, relative=short_term_relative_rebound, darkpool=normal_delayed_darkpool_activity, flow_quality=high, score=+0.472.
- Risk: raw flow 仍是净流出，不能当 confirmed accumulation；raw distribution 可能是供给吸收/事件消化，价格未转弱前不能当 confirmed short
- Next: 下一步先等 raw flow 从净流出/卖压缓和转为净流入；确认前只作为 bullish watch，不作为正式 long candidate。

### AMD
- Why: 供给吸收观察信号: price=short_term_rebound_inside_weak_trend, flow=raw_distribution_pressure, distribution_context=supply_absorption, short=stable_short_pressure, relative=relative_weakness, darkpool=normal_delayed_darkpool_activity, flow_quality=high, score=-0.415.
- Risk: raw distribution 可能是供给吸收/事件消化，价格未转弱前不能当 confirmed short
- Next: 下一步看卖压是否被价格继续吸收；若 raw flow 转正且价格守住趋势，可升级为 long，若价格跌破趋势且 short pressure 上升才转 short。

### NVDA
- Why: 供给吸收观察信号: price=bullish_price_confirmation, flow=raw_distribution_pressure, distribution_context=supply_absorption, short=low_and_falling_short_pressure, relative=relative_strength, darkpool=normal_delayed_darkpool_activity, flow_quality=medium, score=+0.425.
- Risk: raw distribution 可能是供给吸收/事件消化，价格未转弱前不能当 confirmed short
- Next: 下一步看卖压是否被价格继续吸收；若 raw flow 转正且价格守住趋势，可升级为 long，若价格跌破趋势且 short pressure 上升才转 short。

### AAPL
- Why: 供给吸收观察信号: price=short_term_rebound_inside_weak_trend, flow=raw_distribution_pressure, distribution_context=supply_absorption, short=stable_short_pressure, relative=relative_mixed, darkpool=normal_delayed_darkpool_activity, flow_quality=medium, score=-0.174.
- Risk: raw distribution 可能是供给吸收/事件消化，价格未转弱前不能当 confirmed short
- Next: 下一步看卖压是否被价格继续吸收；若 raw flow 转正且价格守住趋势，可升级为 long，若价格跌破趋势且 short pressure 上升才转 short。

