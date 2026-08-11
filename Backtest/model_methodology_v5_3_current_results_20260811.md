# Institutional Flow Model v5.3 Methodology and Current Results

Generated: 2026-08-11  
Model version: v5.3  
Test interval: 1D bars  
Primary use case: portfolio-manager-facing institutional behavior inference and investment insight generation

## 1. Model Purpose

This model does not directly observe account-level institutional ownership. It infers short- to medium-term institutional behavior bias from market microstructure and market-context data:

- raw trades / mainflow
- OHLCV bars
- price regime
- relative strength versus benchmark ETF
- short volume context
- delayed darkpool context

The output should be interpreted as institutional behavior inference, not confirmed 13F ownership truth.

Correct language:

- "The model infers institutional accumulation pressure."
- "The model flags potential distribution risk."
- "The model sees supply absorption and needs further confirmation."

Avoid language like:

- "Institutions definitely bought."
- "Institutions definitely sold."
- "This is confirmed 13F accumulation."

13F data can be used later for low-frequency validation, but it should not be mixed into the real-time signal logic because 13F is delayed and quarterly.

## 2. Data Inputs

| Data | Purpose | Current Usage |
|---|---|---|
| `trades` | Tick-level transaction tape | Used to derive mainflow and large-trade behavior |
| `mainflow` / flow fields | Net institutional-scale buy/sell pressure | Core input for accumulation/distribution inference |
| `aggs` / kline | OHLCV price bars | Used for price regime, trend, returns, event study, backtest |
| `short_volume` | Daily short-sale activity proxy | Used to identify rising/easing short pressure |
| `darkpool` | Delayed ATS/off-exchange background | Used as context only, not immediate timing |
| benchmark ETF | Relative strength/weakness context | Example: semis versus `SMH`, large-cap tech versus `QQQ` |
| 13F | Institutional holdings validation | Future validation layer, not live signal input |

## 3. Important Data Caveats

`short_volume` is not the same as `short_interest`.

- Short volume measures daily short-sale activity.
- Short interest measures outstanding short positions and is lower frequency.
- High short volume can mean bearish pressure, hedging, market-making, or short covering dynamics. It needs price and flow confirmation.

`darkpool` is delayed.

- Current darkpool data can lag by around 2-3 weeks.
- It should be used as background participation context.
- It should not be used as an intraday or immediate entry trigger.

`mainflow` is an inference from trades.

- It depends on trade classification and large-trade thresholds.
- It can identify institutional-scale pressure, but not account identity.
- Raw sell pressure with price resilience can mean absorption, not necessarily distribution.

## 4. Core Terms

### Flow Regime

`raw_accumulation_pressure`

- Large-trade/mainflow evidence is net positive.
- Indicates possible institutional accumulation, short covering, ETF/basket inflow, or event-driven buying.
- Becomes more meaningful when price is also strong.

`raw_distribution_pressure`

- Large-trade/mainflow evidence is net negative.
- Indicates active sell pressure.
- It is not automatically bearish. If price holds up, this may be supply absorption or event-related turnover.

`selling_pressure_easing`

- Selling pressure is still present or recently present, but the intensity is fading.
- This can be an early bullish watch condition if price stabilizes and relative strength improves.

`buying_pressure_fading`

- Buying pressure is weakening.
- This can be an early bearish watch condition if price also starts to break down.

`balanced_flow`

- Flow evidence is not clearly positive or negative.
- Usually not enough for a strong directional conclusion.

`flow_missing_bar` / `flow_unavailable`

- Flow data is missing or not reliable for the bar.
- Signals should be capped or treated as low confidence.

### Price Regime

`bullish_price_confirmation`

- Price action confirms upward trend or constructive momentum.
- This strengthens long signals and weakens raw short interpretation.

`bearish_price_confirmation`

- Price action confirms downside pressure.
- This is required before raw distribution can become a credible short candidate.

`short_term_rebound_inside_weak_trend`

- Price is rebounding, but broader trend structure is still weak.
- Useful for watch signals, not enough by itself for high conviction.

`short_term_pullback_inside_strong_trend`

- Price is pulling back inside a stronger trend.
- Raw selling pressure here may be absorption rather than true distribution.

`mixed_price_action`

- Price evidence is not decisive.

### Relative Regime

`relative_strength`

- Ticker is outperforming its benchmark ETF.
- Supports long bias.

`relative_weakness`

- Ticker is underperforming its benchmark ETF.
- Supports short or de-risking bias.

`short_term_relative_rebound`

- Relative performance has recently improved.
- Useful for watch-long setups.

`short_term_relative_pullback`

- Relative performance has recently weakened.
- Useful for watch-short setups, but needs more confirmation.

`relative_mixed`

- Relative evidence is not decisive.

`relative_unavailable`

- Benchmark comparison is missing.

### Short Regime

`low_short_pressure`

- Short-sale activity is low.
- Raw distribution is less likely to represent confirmed short pressure.

`low_and_falling_short_pressure`

- Short pressure is low and easing.
- Supports absorption / no-short interpretation.

`stable_short_pressure`

- Short pressure is not clearly rising or falling.
- Usually neutral.

`rising_short_pressure`

- Short-sale activity is increasing.
- Raises risk of bearish pressure, but still needs price/relative confirmation.

`high_short_pressure`

- Short activity is elevated.
- Can be bearish, but can also create squeeze risk if price does not break.

`high_and_rising_short_pressure`

- Strongest short-pressure warning.
- For confirmed short, this should align with bearish price and relative weakness.

`easing_short_pressure` / `high_but_easing_short_pressure`

- Short pressure is falling.
- Reduces conviction in short signals and can support absorption/squeeze watch.

### Distribution Context

`supply_absorption`

- Raw sell pressure exists, but price is holding up or rebounding.
- This often means supply is being absorbed by buyers.
- It should not be treated as an automatic short.

`event_sell_the_news_watch`

- Selling appears after a major event or strong move.
- Could be profit-taking, turnover, or risk re-pricing.
- Needs price breakdown before becoming bearish.

`bearish_watch_distribution`

- Distribution pressure exists and some bearish evidence is present.
- Still not enough for confirmed short unless price, short pressure, relative weakness, and flow align.

`conflicted_distribution`

- Some distribution evidence exists, but context is mixed.
- Usually a risk flag, not a trade signal.

`not_distribution`

- No special distribution context.

### Signal Labels

`neutral`

- No confirmed directional signal.
- May still have watch-level observations.

`watch_long`

- Potential bullish setup.
- Evidence is incomplete, often because flow has not fully confirmed.
- PM interpretation: add to watchlist, do not treat as confirmed buy.

`absorption_watch`

- Sell pressure is being absorbed or not translating into price weakness.
- PM interpretation: do not short only because raw flow is negative; wait for either flow turn-up or price breakdown.

`watch_short`

- Potential bearish risk.
- PM interpretation: de-risking watch or short candidate watch, not direct short.

`long`

- Confirmed long candidate from the model.
- Means large-flow, price, and context are sufficiently aligned.

`short`

- Confirmed short candidate from the model.
- Requires stricter confirmation because current short-side performance has been weak.

### Confidence and Reliability

`confidence`

- A capped confidence score derived from signal strength and data quality.
- It is not a probability of profit.
- It should be used for ranking and filtering, not as a standalone trading rule.

`flow_reliability`

- Measures mainflow/trades coverage quality.
- Low flow reliability means the model should reduce confidence and avoid strong institutional conclusions.

`flow_coverage_20` / `flow_coverage_60`

- Recent flow coverage over 20/60 bars.
- Values close to 1.0 are strong.
- Values below around 0.5 mean flow-driven conclusions are less reliable.

### Score Calculation

The model uses separate long and short engines. The score fields are not probabilities. They are normalized rule-based evidence scores between 0 and 1, then combined into a signed final score.

Core normalized inputs:

| Component | Meaning | Direction |
|---|---|---|
| `flow_score` | 5-bar institutional flow pressure, blended with standardized flow | Positive supports long, negative supports short |
| `ofi_z` | order-flow imbalance z-score | Positive supports long |
| `vwap_dev` | price deviation versus rolling VWAP | Positive supports long |
| `impact_eff_z` | impact/efficiency measure | Inverted in the model, so lower adverse impact supports long |
| `rvol` | relative volume | Boosts or dampens base score |
| `short_context_score` | short-volume context | Positive or negative adjustment |
| `darkpool_context_score` | delayed darkpool context | Small positive or negative adjustment |
| `hmm_boost` | HMM state adjustment | Small trend-state adjustment |

Current base weights:

| Component | Weight Logic |
|---|---|
| Flow | Up to 35%, scaled by `flow_reliability` |
| OFI | 45% of remaining non-flow weight |
| VWAP | 35% of remaining non-flow weight |
| Impact | 20% of remaining non-flow weight |

Simplified formula:

```text
flow_weight = 0.35 * flow_reliability
non_flow_weight = 1 - flow_weight

base_score =
    flow_weight * flow_score
  + non_flow_weight * 0.45 * normalized_ofi
  + non_flow_weight * 0.35 * normalized_vwap
  + non_flow_weight * 0.20 * normalized_impact

base_score is then adjusted by relative volume.
```

Then the model separates long and short evidence:

```text
long_base_score =
    positive part of flow/ofi/vwap/impact evidence
    + positive context score

short_base_score =
    negative part of flow/ofi/vwap/impact evidence
    + negative context score

long_score = long_base_score + positive HMM boost
short_score = short_base_score + negative HMM boost

final_score = long_score - short_score
```

Interpretation:

| Field | Meaning |
|---|---|
| `long_score` | Strength of bullish evidence |
| `short_score` | Strength of bearish evidence |
| `final_score` | Net directional score, positive means long evidence dominates, negative means short evidence dominates |

Example: INTC latest bar on 2026-08-07:

| Field | Value |
|---|---:|
| `long_score` | 0.566 |
| `short_score` | 0.094 |
| `final_score` | +0.472 |
| `context_score` | 0.000 |
| `hmm_boost` | 0.000 |
| `flow_score` | -0.279 |
| `flow_net_current` | -76.9M |
| `flow_net_5` | -129.3M |

Because `context_score` and `hmm_boost` are both zero on this bar:

```text
final_score = 0.566 - 0.094 = +0.472
```

This does not mean there is no selling. In fact, `flow_score` is negative and the flow regime is `raw_distribution_pressure`. The positive final score comes from stronger non-flow bullish evidence, while the model still labels the trade state as `watch_long` rather than confirmed long because raw flow remains negative and the distribution context is `supply_absorption`.

## 5. Signal Hierarchy

The model separates three levels:

| Level | Meaning | PM Action |
|---|---|---|
| Neutral | No strong directional evidence | Do nothing or monitor |
| Watch | Possible institutional behavior, incomplete evidence | Add to watchlist, require confirmation |
| Confirmed | Multiple evidence layers align | Candidate for backtest/trade evaluation |

Important rule:

Raw distribution is not enough for a short. A confirmed short should require bearish price confirmation, relative weakness, short-pressure confirmation, and bearish flow context.

## 6. Trading and Backtest Modes

### Event Study

Event Study tests what happens after every signal over fixed horizons.

Example:

- If there are 16 accumulation signals, it calculates forward returns after each one.
- It does not merge overlapping signals into trades.
- It is useful for measuring whether the signal has directional information.

### Confirmed Signal Backtest

This is the strict trading mode.

Current parameters:

- Only uses confirmed `accumulation` / `strong_accumulation` / `distribution` / `strong_distribution`.
- Requires `min_confirm = 3` consecutive same-direction bars.
- Maximum holding period: `20` daily bars.
- Stop loss: `2%`.
- Cost: `0.10%` one way.

Why INTC only had one confirmed trade:

- INTC had 16 long signals.
- Most were single-day or short clusters.
- Only the 2025-09 signal cluster satisfied the consecutive confirmation rule.
- The backtest merged that cluster into one real position.

### Walk-Forward

Walk-Forward tests rolling out-of-sample signal stability.

Current parameters:

- Training window: `60` bars.
- Forward holding window: `5` bars.
- Step size: `5` bars.

Walk-Forward is useful when there are enough confirmed signals. If confirmed signals are too sparse, Walk-Forward may have no valid trades.

### Watch-to-Trade

Watch-to-Trade, or WTT, tests whether watch signals can become tradable after confirmation.

WTT is not immediate trading on `watch_long`, `watch_short`, or `absorption_watch`.

Current WTT parameters:

- Watch confirmation window: `5` bars.
- Maximum holding period: `20` bars.
- Stop loss: `2%`.
- Cost: `0.10%` one way.

Current WTT long confirmation:

- `watch_long` can upgrade when price, relative strength, and flow confirm.
- `absorption_watch` can upgrade only if price holds and flow turns positive or selling pressure clearly eases.
- A later confirmed `long` can also upgrade the watch into a trade.

Current WTT short confirmation:

- `watch_short` must have bearish price confirmation.
- It also needs relative weakness.
- It also needs short pressure confirmation.
- It also needs bearish flow confirmation.

Current finding:

- WTT works best so far on INTC, an event-driven stock.
- WTT is not stable on AMD/NVDA/AAPL under current rules.
- Short-side WTT remains weak and should be treated as risk warning first.

## 7. WTT Parameter Sweep

WTT parameter sweep means testing multiple WTT rule combinations instead of choosing parameters by intuition.

Parameters to sweep:

| Parameter | Candidate Values |
|---|---|
| Watch confirmation window | 3 / 5 / 10 bars |
| Maximum holding period | 10 / 20 / 30 bars |
| Stop loss | 2% / 3% / 5% |
| Direction mode | long-only / long-short |
| Absorption entry | confirmed long only / flow current positive / 5D flow positive |
| Short entry | price+relative only / price+relative+short / full confirmation |

Goal:

- Check whether WTT is robust across tickers.
- Avoid overfitting INTC only.
- Separate useful PM insight generation from actual tradable alpha.

## 8. Event-Driven Regime

Event-driven regime means the ticker is affected by major non-routine catalysts, such as:

- government investment or policy support
- strategic investment
- restructuring
- major financing
- M&A or regulatory decision
- AI infrastructure / defense / national-strategy themes
- earnings or guidance shock

Why it matters:

Event stocks often show heavy selling pressure without immediate price weakness. That can happen because early holders take profit while new strategic or momentum buyers absorb supply.

In normal stocks:

- raw distribution + weak price can be bearish.

In event-driven stocks:

- raw distribution + resilient price can mean supply absorption.
- sell-the-news flow may not be a short.
- WTT may be more useful than strict confirmed-only signals.

INTC is the clearest current example because the U.S. government equity stake created an event-driven regime.

## 9. Current Test Setup

Signal files:

| Ticker | Signal File | Bars | Date Range |
|---|---|---:|---|
| INTC | `output/INTC_1d_20260811_135707_v5_3_signals.csv` | 278 | 2025-07-01 to 2026-08-07 |
| AMD | `output/AMD_1d_20260811_135813_v5_3_signals.csv` | 278 | 2025-07-01 to 2026-08-07 |
| NVDA | `output/NVDA_1d_20260811_140405_v5_3_signals.csv` | 278 | 2025-07-01 to 2026-08-07 |
| AAPL | `output/AAPL_1d_20260811_140415_v5_3_signals.csv` | 68 | 2026-05-01 to 2026-08-07 |

Backtest settings:

| Setting | Value |
|---|---|
| Interval | 1D |
| Forward horizon | 5 bars |
| Walk-forward train window | 60 bars |
| Confirmed min confirm | 3 bars |
| Max hold | 20 bars |
| Stop loss | 2% |
| One-way cost | 0.10% |
| WTT confirmation window | 5 bars |

## 10. Summary Results

| Ticker | Latest Model Read | Confirmed Backtest | Walk-Forward | WTT |
|---|---|---|---|---|
| INTC | `watch_long`, supply absorption, high flow coverage | 1 trade, +24.88%, Sharpe nan | No valid WF trades | 8 trades, +51.28%, Sharpe 3.91 |
| AMD | `absorption_watch`, relative weakness vs SMH | 1 trade, +12.59%, Sharpe nan | 3 trades, +19.62%, Sharpe 11.26 | 10 trades, -2.46%, Sharpe 0.94 |
| NVDA | `absorption_watch`, medium flow coverage | No confirmed trades | No valid WF trades | 2 trades, -6.41%, Sharpe -83.88 |
| AAPL | `absorption_watch`, short sample | No confirmed trades | No valid WF trades | No WTT trades |

## 11. INTC Detailed Result

Latest signal:

| Field | Value |
|---|---|
| Latest close | 101.65 |
| Latest signal | `neutral` |
| Latest trade signal | `watch_long` |
| Confidence | 22.6 |
| Final score | +0.472 |
| Long score | 0.566 |
| Short score | 0.094 |
| Price regime | `short_term_rebound_inside_weak_trend` |
| Flow regime | `raw_distribution_pressure` |
| Distribution context | `supply_absorption` |
| Relative regime | `short_term_relative_rebound` vs `SMH` |
| Short regime | `stable_short_pressure` |
| Darkpool regime | `normal_delayed_darkpool_activity` |
| Flow reliability | 1.00 |
| Flow coverage 20 / 60 | 1.00 / 1.00 |

Known event anchor:

| Event | Detail |
|---|---|
| Public catalyst | U.S. government strategic investment in Intel |
| Source | Intel announcement / SEC 8-K exhibit |
| Date | 2025-08-22 announcement; 2025-08-25 8-K filing |
| Deal terms | About $8.9B investment, 433.3M primary shares at $20.47/share |
| Ownership impact | Equivalent to a 9.9% stake, according to Intel's announcement |
| Model relevance | This creates an event-driven regime where raw sell pressure can reflect turnover/profit-taking rather than clean bearish distribution |

Source links:

- Intel Newsroom: [Intel and Trump Administration Reach Historic Agreement to Accelerate American Technology and Manufacturing Leadership](https://newsroom.intel.com/corporate/intel-and-trump-administration-reach-historic-agreement)
- SEC exhibit: [Intel 8-K Exhibit 99.1, August 2025](https://www.sec.gov/Archives/edgar/data/50863/000005086325000129/a08222025form8-kex991.htm)

Signal counts:

| Signal Type | Count |
|---|---:|
| `neutral` | 262 |
| `accumulation` | 11 |
| `strong_accumulation` | 5 |
| `watch_short` | 116 |
| `absorption_watch` | 64 |
| `watch_long` | 22 |
| `long` | 16 |

Event Study:

| Horizon | Avg Return | Win Rate | Sharpe | p-value | Read |
|---|---:|---:|---:|---:|---|
| 1 bar | +2.698% | 56.2% | 6.52 | 0.1211 | Not significant |
| 3 bar | +4.829% | 62.5% | 5.30 | 0.0352 | Significant |
| 5 bar | +8.723% | 81.2% | 5.76 | 0.0054 | Significant |
| 10 bar | +19.433% | 87.5% | 5.51 | 0.0005 | Significant |
| 20 bar | +40.637% | 100.0% | 5.78 | 0.0000 | Significant |

IC:

| Horizon | IC | p-value | Read |
|---|---:|---:|---|
| 1 bar | 0.0525 | 0.3839 | Weak/normal |
| 3 bar | 0.1542 | 0.0104 | Strong |
| 5 bar | 0.1323 | 0.0288 | Strong |
| 10 bar | 0.0751 | 0.2201 | Normal |
| 20 bar | 0.1182 | 0.0580 | Good but marginal |

Confirmed Backtest:

| Metric | Value |
|---|---:|
| Trades | 1 |
| Win rate | 100.0% |
| Avg hold | 7.0 bars |
| Avg trade return | +24.882% |
| Cumulative return | +24.88% |
| Max drawdown | 0.00% |
| Sharpe | nan |

Sharpe is `nan` because there is only one confirmed trade.

WTT Backtest:

| Metric | Value |
|---|---:|
| Confirmation window | 5 bars |
| Trades | 8 |
| Win rate | 37.5% |
| Avg hold | 6.9 bars |
| Avg trade return | +9.565% |
| Cumulative return | +51.28% |
| Max drawdown | -32.80% |
| Sharpe | 3.91 |
| Long win rate | 37.5% (3/8) |
| Short win rate | N/A |

WTT setup breakdown:

| Direction | Watch Signal | Entry Reason | Trades | Win Rate | Avg Return |
|---|---|---|---:|---:|---:|
| long | `absorption_watch` | `confirmed_long` | 1 | 100.0% | +6.605% |
| long | `absorption_watch` | `watch_long_price_flow_confirmed` | 3 | 0.0% | -8.725% |
| long | `watch_long` | `confirmed_long` | 2 | 50.0% | +49.249% |
| long | `watch_long` | `watch_long_price_flow_confirmed` | 2 | 50.0% | -1.202% |

INTC interpretation:

INTC is currently the best example of event-driven supply absorption. The model often sees raw distribution, but price and relative behavior do not confirm a clean short. This is exactly why raw distribution should not automatically become bearish.

This is consistent with the known government-stake event. A strategic public-sector investment can create a major re-pricing regime: old holders may sell into strength, short-term traders may take profit, and new buyers may absorb that supply. In that environment, `raw_distribution_pressure` does not necessarily mean institutions are abandoning the stock. The more important question is whether price breaks down or whether supply is absorbed.

The model output lines up with that interpretation:

- The latest flow regime is `raw_distribution_pressure`, showing active sell pressure.
- The latest distribution context is `supply_absorption`, meaning the sell pressure has not translated into clean bearish price confirmation.
- The latest relative regime is `short_term_relative_rebound` versus `SMH`, which argues against treating the tape as a confirmed short.
- Short regime is `stable_short_pressure`, so short activity is not confirming a high-conviction bearish setup.
- Flow reliability and 20/60 bar flow coverage are both 1.00, so this is not simply a missing-data artifact.
- Event Study after accumulation signals is strongly positive from 3D to 20D, matching the idea that confirmed accumulation phases captured the post-event upside regime.

Important limitation:

The model is not proving that the U.S. government purchase itself caused every later signal. It is saying the market behavior after the known event is consistent with an event-driven absorption/re-pricing regime. This is why the PM-facing interpretation should say "model evidence is consistent with the known strategic investment catalyst," not "the model proves government buying."

The strongest INTC evidence is on the long side:

- Event Study is significant from 3D onward.
- 5D and 10D forward returns are strong.
- WTT improves trade count from 1 to 8 and produces positive cumulative return.
- The best WTT setup is not generic absorption, but watch signals that later upgrade into confirmed long.

PM read:

INTC should be treated as an event-driven bullish watch / long-candidate stock, not a confirmed short. Current latest read is still `watch_long`, not confirmed long, because raw flow remains net negative.

## 12. AMD Detailed Result

Latest signal:

| Field | Value |
|---|---|
| Latest close | 483.36 |
| Latest signal | `neutral` |
| Latest trade signal | `absorption_watch` |
| Confidence | 21.8 |
| Final score | -0.415 |
| Long score | 0.129 |
| Short score | 0.544 |
| Price regime | `short_term_rebound_inside_weak_trend` |
| Flow regime | `raw_distribution_pressure` |
| Distribution context | `supply_absorption` |
| Relative regime | `relative_weakness` vs `SMH` |
| Short regime | `stable_short_pressure` |
| Darkpool regime | `normal_delayed_darkpool_activity` |
| Flow reliability | 1.00 |
| Flow coverage 20 / 60 | 1.00 / 1.00 |

Signal counts:

| Signal Type | Count |
|---|---:|
| `neutral` | 266 |
| `strong_accumulation` | 6 |
| `accumulation` | 2 |
| `distribution` | 2 |
| `strong_distribution` | 2 |
| `watch_short` | 119 |
| `absorption_watch` | 64 |
| `watch_long` | 18 |
| `long` | 8 |
| `short` | 4 |

Event Study:

| Horizon | Avg Return | Win Rate | Sharpe | p-value | Read |
|---|---:|---:|---:|---:|---|
| 1 bar | +2.233% | 87.5% | 13.94 | 0.0420 | Significant |
| 3 bar | +6.613% | 100.0% | 15.25 | 0.0022 | Significant |
| 5 bar | +9.709% | 87.5% | 9.10 | 0.0085 | Significant |
| 10 bar | +26.139% | 100.0% | 11.36 | 0.0004 | Significant |
| 20 bar | +66.291% | 100.0% | 12.43 | 0.0000 | Significant |

IC:

| Horizon | IC | p-value | Read |
|---|---:|---:|---|
| 1 bar | 0.0966 | 0.1086 | Normal |
| 3 bar | 0.1614 | 0.0073 | Strong |
| 5 bar | 0.1475 | 0.0147 | Strong |
| 10 bar | 0.2947 | 0.0000 | Very strong |
| 20 bar | 0.2678 | 0.0000 | Very strong |

Confirmed Backtest:

| Metric | Value |
|---|---:|
| Trades | 1 |
| Win rate | 100.0% |
| Avg hold | 4.0 bars |
| Avg trade return | +12.586% |
| Cumulative return | +12.59% |
| Max drawdown | 0.00% |
| Sharpe | nan |

Walk-Forward:

| Metric | Value |
|---|---:|
| Trades | 3 |
| Win rate | 66.7% |
| Avg trade return | +6.417% |
| Cumulative return | +19.62% |
| Max drawdown | 0.00% |
| Sharpe | 11.26 |

Walk-Forward by signal:

| Signal | Trades | Win Rate | Avg Return |
|---|---:|---:|---:|
| `strong_accumulation` | 2 | 100.0% | +11.517% |
| `strong_distribution` | 1 | 0.0% | -3.783% |

WTT Backtest:

| Metric | Value |
|---|---:|
| Confirmation window | 5 bars |
| Trades | 10 |
| Win rate | 10.0% |
| Avg hold | 5.9 bars |
| Avg trade return | +1.236% |
| Cumulative return | -2.46% |
| Max drawdown | -34.25% |
| Sharpe | 0.94 |
| Long win rate | 14.3% (1/7) |
| Short win rate | 0.0% (0/3) |

AMD interpretation:

AMD has strong confirmed long-side evidence in Event Study and IC. Walk-Forward also looks good, although the sample is still small.

However, WTT performs poorly. This means watch signals are not yet reliable for AMD under current rules. The model should not turn every AMD watch setup into a trade.

PM read:

AMD confirmed/strong accumulation signals are useful. Current latest signal is `absorption_watch`, but because AMD is relatively weak versus `SMH`, it should be treated as a watch state, not an immediate long.

## 13. NVDA Detailed Result

Latest signal:

| Field | Value |
|---|---|
| Latest close | 223.96 |
| Latest signal | `neutral` |
| Latest trade signal | `absorption_watch` |
| Confidence | 3.8 |
| Final score | +0.425 |
| Long score | 0.545 |
| Short score | 0.121 |
| Price regime | `bullish_price_confirmation` |
| Flow regime | `raw_distribution_pressure` |
| Distribution context | `supply_absorption` |
| Relative regime | `relative_strength` vs `SMH` |
| Short regime | `low_and_falling_short_pressure` |
| Darkpool regime | `normal_delayed_darkpool_activity` |
| Flow reliability | 0.468 |
| Flow coverage 20 / 60 | 0.45 / 0.467 |

Signal counts:

| Signal Type | Count |
|---|---:|
| `neutral` | 278 |
| `watch_short` | 115 |
| `absorption_watch` | 81 |
| `watch_long` | 27 |

IC:

| Horizon | IC | p-value | Read |
|---|---:|---:|---|
| 1 bar | 0.0112 | 0.8534 | Weak |
| 3 bar | -0.0704 | 0.2444 | Normal but negative |
| 5 bar | -0.1294 | 0.0326 | Statistically meaningful but wrong direction for current score interpretation |
| 10 bar | -0.0078 | 0.8992 | Weak |
| 20 bar | 0.0575 | 0.3574 | Normal |

WTT Backtest:

| Metric | Value |
|---|---:|
| Trades | 2 |
| Win rate | 0.0% |
| Avg hold | 2.0 bars |
| Avg trade return | -3.258% |
| Cumulative return | -6.41% |
| Max drawdown | -2.72% |
| Sharpe | -83.88 |
| Long win rate | N/A |
| Short win rate | 0.0% (0/2) |

NVDA interpretation:

NVDA has no confirmed accumulation or distribution signals in the current v5.3 output. Most signals are watch-level only. Flow reliability is below 0.5, so institutional-flow conclusions should be capped.

The WTT short tests failed. This supports the earlier conclusion that watch-short is not yet a tradable short signal.

PM read:

NVDA should be treated as insufficient confirmed flow evidence. The latest `absorption_watch` means raw selling pressure is being absorbed while price/relative strength remain constructive. It is not a short.

## 14. AAPL Detailed Result

Latest signal:

| Field | Value |
|---|---|
| Latest close | 313.33 |
| Latest signal | `neutral` |
| Latest trade signal | `absorption_watch` |
| Confidence | 12.2 |
| Final score | -0.174 |
| Long score | 0.000 |
| Short score | 0.174 |
| Price regime | `short_term_rebound_inside_weak_trend` |
| Flow regime | `raw_distribution_pressure` |
| Distribution context | `supply_absorption` |
| Relative regime | `relative_mixed` vs `QQQ` |
| Short regime | `stable_short_pressure` |
| Darkpool regime | `normal_delayed_darkpool_activity` |
| Flow reliability | 0.688 |
| Flow coverage 20 / 60 | 0.95 / 0.517 |

Signal counts:

| Signal Type | Count |
|---|---:|
| `neutral` | 68 |
| `watch_short` | 12 |
| `absorption_watch` | 11 |

IC:

| Horizon | IC | p-value | Read |
|---|---:|---:|---|
| 1 bar | 0.0892 | 0.4729 | Normal |
| 3 bar | 0.1450 | 0.2491 | Good but not significant |
| 5 bar | 0.1846 | 0.1475 | Good but not significant |
| 10 bar | 0.2750 | 0.0367 | Significant |
| 20 bar | 0.4588 | 0.0010 | Significant |

Backtest:

- No confirmed signal-driven trades.
- No valid Walk-Forward trades.
- No WTT trades after stricter confirmation.

AAPL interpretation:

AAPL has only 68 daily bars in this current test file, so the result is sample-limited. The IC looks positive at 10D and 20D, but there are no confirmed trade signals. This should not be overinterpreted until more data is available.

PM read:

AAPL is currently an absorption watch / neutral state. It should not be treated as confirmed long or confirmed short.

## 15. Cross-Ticker Findings

### Long Side

The long side is currently much stronger than the short side.

Evidence:

- INTC Event Study is significant from 3D onward.
- AMD Event Study is significant across all tested horizons.
- AMD Walk-Forward is positive.
- INTC WTT is positive and captures event-driven upside.

### Short Side

The short side remains weak.

Evidence:

- AMD WTT short setups had 0.0% win rate.
- NVDA WTT short setups had 0.0% win rate.
- INTC short signals were filtered out by stricter logic, which is appropriate because INTC has event-driven absorption.

Current conclusion:

`watch_short` should remain a risk flag, not a direct short signal.

### Absorption

Absorption is useful as an interpretation layer, but not always as an entry rule.

Good use:

- Prevent raw distribution from becoming a false short.
- Identify possible event-driven supply absorption.
- Move ticker into PM watchlist.

Bad use:

- Buying every `absorption_watch` immediately.

Current conclusion:

Absorption needs either confirmed long, positive flow turn, or stronger relative confirmation before becoming a trade.

### Confidence

Confidence is useful but not enough alone.

INTC confidence tiers are not perfectly monotonic. AMD confidence tiers look better, with higher-confidence signals producing better forward returns. This means confidence should be used with regime filters, not as a standalone threshold.

## 16. Current Model Problems

1. Short-side logic is still too weak for trading.

`watch_short` often identifies risk, but not profitable short entries. The model needs stricter short confirmation or should separate "de-risk" from "short trade".

2. WTT can overtrade if absorption confirmation is too loose.

The first WTT version traded too many absorption setups. The stricter version improved INTC interpretability but still does not generalize to AMD/NVDA.

3. Confirmed backtest has too few trades.

Confirmed mode is clean but sparse. This limits Sharpe and Walk-Forward usefulness, especially for INTC.

4. Flow coverage matters heavily.

NVDA has only medium flow coverage in the current signal file. That reduces confidence in institutional-flow interpretation.

5. Event-driven stocks need a separate regime layer.

INTC should not be interpreted the same way as normal mega-cap tech because policy/strategic investment changed the flow-price relationship.

6. Sector-level insight layer is not finished.

The model currently gives ticker-level insights. To meet the mentor's goal, we need sector aggregation and group-level ranking.

## 17. Recommended Next Steps

1. Keep two official result tracks.

- Confirmed Signal Backtest: strict, clean, fewer trades.
- Watch-to-Trade: PM insight discovery, needs regime filters.

2. Add WTT parameter sweep.

Test watch windows, max hold, stop loss, long-only versus long-short, and absorption/short confirmation rules.

3. Add event-driven regime.

Flag stocks with major catalysts and apply different interpretation rules for raw distribution and absorption.

4. Keep short-side signals as risk alerts for now.

Do not present `watch_short` as a direct short recommendation until short backtests improve.

5. Build sector aggregation.

Aggregate ticker-level signals into sector-level scores:

- semiconductors
- mega-cap tech
- financials
- energy
- healthcare
- consumer discretionary
- crypto proxies

6. Add PM-facing outputs.

For each ticker/sector, output:

- current signal
- reason
- risk
- next confirmation condition
- suggested PM action: monitor / avoid chase / add candidate / reduce risk / short candidate

7. Use 13F as delayed validation.

13F should validate whether low-frequency ownership trends align with model-inferred institutional behavior, but it should not be treated as real-time input.

## 18. Practical PM Interpretation Rules

`confirmed long`

- Candidate for long/add.
- Needs normal portfolio risk controls.

`watch_long`

- Add to watchlist.
- Wait for flow and price confirmation.

`absorption_watch`

- Do not short just because raw flow is negative.
- Watch whether price continues to hold and flow turns positive.

`watch_short`

- Risk warning.
- Consider reducing chase/position size.
- Do not short unless price, relative weakness, short pressure, and flow all confirm.

`confirmed short`

- Potential short/reduce candidate.
- Current model should be conservative here because short-side backtests are weak.

## 19. Current Bottom Line

INTC is the strongest current example for the mentor's desired insight style:

> Event-driven stock, raw selling pressure, price resilience, and eventual upside. The model should describe this as supply absorption / bullish watch rather than bearish distribution.

AMD shows the confirmed long side can work, but WTT is not stable enough yet.

NVDA shows why flow coverage and short-side confirmation matter.

AAPL is too sample-limited for a strong conclusion.

The model is moving in the right direction for PM-facing insights, but the next major improvement should be regime-aware WTT plus sector-level aggregation, not more complex training.
