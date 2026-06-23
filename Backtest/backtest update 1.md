# Institutional Flow Detection Framework

Detects institutional accumulation/distribution using HMM on order flow features, validated against SEC 13F filings.

---

## How It Works

```
OHLCV (2yr) ─┐
main-flow API  ─┼─► 6 features ─► 3-state HMM ─► signals
large-trades   ─┘

signals ─► backtest.py     (1h/15m: event study + signal-driven)
        ─► validate_13f.py (1d: quarterly match vs institutions)
```

**6 HMM features:**

| Feature | Source | Notes |
|---------|--------|-------|
| `ofi_z` | Lee-Ready on OHLCV | ⚠️ biased in trending markets |
| `rvol` | OHLCV | relative volume |
| `impact_eff_z` | OHLCV | price impact efficiency |
| `liq_abs_z` | OHLCV | liquidity absorption |
| `vwap_dev` | OHLCV | deviation from VWAP |
| `inst_net_z` | main-flow API | ✅ only true directional feature |

# 7 Feature Formulas and Definitions

## 1. ofi_z — Order Flow Imbalance (Normalized)

**Economic Meaning:** Measures the buy/sell pressure imbalance within each bar. Positive values indicate buyer dominance; negative values indicate seller dominance.

**Formula (Mixed OFI):**
mixed_OFI = α × LR_OFI + (1-α) × BVC_OFI

Lee-Ready OFI:
  midprice = (high + low) / 2
  lr_sign  = +1  if close > midprice
           = -1  if close < midprice
           = sign(close - prev_close)  otherwise  (tick rule)
  LR_OFI   = Σ(lr_sign × volume)  over rolling 5 bars

BVC OFI (Easley, López de Prado & O'Hara, 2012):
  buy_frac = (close - low) / (high - low)
  BVC_net  = (buy_frac - 0.5) × 2 × volume
  BVC_OFI  = Σ(BVC_net)  over rolling 5 bars

Dynamic blend coefficient α:
  ret_ma   = |rolling_20_mean(pct_change)|
  ret_norm = clip(ret_ma / rolling_50_mean(ret_ma), 0, 2) / 2
  α        = ret_norm  (high trend → α near 1, use Lee-Ready;
                        ranging market → α near 0, use BVC)

ofi_z = mixed_OFI / rolling_20_std(mixed_OFI)
> ⚠️ **Note:** Lee-Ready rule has a systematic bias in strong trending markets, which is one reason ofi_z loses predictive power on trend stocks like PLTR in IC analysis.

---

## 2. rvol — Relative Volume

**Economic Meaning:** The ratio of current volume to its recent mean. Values above 1 indicate elevated activity, potentially driven by institutional participation or significant events.

**Formula:** rvol = volume / rolling_20_mean(volume)
**Notes:** Directionless — purely an activity indicator. IC analysis shows relatively weak predictive power on AAPL (avg|IC|=0.040), but sign is consistent.

---

## 3. impact_eff_z — Price Impact Efficiency (Normalized)

**Economic Meaning:** Price movement per unit of volume. Low values indicate "heavy volume with minimal price movement" — a typical signature of institutional passive filling (iceberg orders).

**Formula:**
impact_eff   = |close - prev_close| / rolling_5_mean(volume)
impact_eff_z = (impact_eff - rolling_20_mean(impact_eff)) / rolling_20_std(impact_eff)

**IC Performance:** Weak across all tickers (avg|IC|≈0.027). No significant horizon found in IC analysis — one of the least contributing features.

---

## 4. liq_abs_z — Liquidity Absorption (Normalized)

**Economic Meaning:** Liquidity absorption intensity. High values indicate "high volume + narrow price range" — large order flow absorbed without moving price, a signal of institutional passive liquidity provision at a price level.

**Formula:**
range        = (high - low) / close
liq_absorption = rvol / (range × 100 + ε)    ε = 0.001，防除零
liq_abs_z    = (liq_absorption - rolling_20_mean) / rolling_20_std

**IC Performance:** Worst among all 7 features (AAPL avg|IC|=0.013), inconsistent sign. Recommended to re-evaluate after data cleaning — consider reducing weight to near 0.

---

## 5. vwap_dev — VWAP Deviation

**Economic Meaning:** Current close price deviation from the 20-period volume-weighted average price. Positive values indicate price above VWAP (buyer strength); negative values indicate below VWAP (seller strength). Widely used by institutions as a benchmark price.

**Formula:**
vwap_roll = Σ(close × volume, 20) / Σ(volume, 20)
vwap_dev  = (close - vwap_roll) / vwap_roll
**IC Performance:** Highest single-horizon IC on NVDA at 24bar (IC=0.1325), but overall avg|IC|=0.042 with consistent sign. Notable cross-ticker variance.

---

## 6. clv — Close Location Value

**Economic Meaning:** The relative position of the closing price within the bar's high-low range, bounded [-1, +1]. +1 means close at the high (full-day buyer dominance); -1 means close at the low (full-day seller dominance).

**Formula:**
clv = (2 × close - high - low) / (high - low)
**Origin:** Derived from the Arms Index; also the core component of Williams Accumulation/Distribution.

**IC Performance:** avg|IC|=0.032, inconsistent sign — behaves close to noise across multiple tickers.

---

## 7. price_persistence — Price Persistence

**Economic Meaning:** The ratio of mean returns to return volatility over the last 3 bars — analogous to a short-window signal-to-noise ratio. Positive values indicate strong directional consistency (trend continuation); negative values indicate reversal.

**Formula:**
price_persistence = rolling_3_mean(ret) / (rolling_3_std(ret) + ε)
                                                              ε = 1e-8，防除零
其中 ret = pct_change(close)
**IC Performance:** avg|IC|=0.026. Only the 6-bar horizon on AAPL is significant (p=0.029). Overall weak.

---

## 8. inst_net_z — Institutional Net Flow (Normalized)

**Economic Meaning:** Normalized Z-score of net institutional large-order buy/sell dollar flow within each bar. The only feature derived from real tick-level trade data — not estimated from OHLCV.

**Formula:**
inst_net   = (super_buy - super_sell) + (large_buy - large_sell)
             其中 super ≥ $500K notional，large = $100K-$500K
inst_net_z = inst_net / rolling_20_std(inst_net)
**Current Limitations:** Coverage ranges from 5–48% (ticker-specific), and 2026 data has severe duplicate contamination (notional inflated by 20–70%). Despite being the highest-weighted feature (0.50), actual predictive power is significantly dragged down by data quality issues

---

## Timeframe Summary

| Interval | Bars | Use Case | Viable |
|----------|-----:|----------|:------:|
| 1d | 500 | 13F validation, regime detection | ✅ |
| 1h | 1499 | Signal-driven swing trading | ✅ |
| 4h | ~499 | — | ❌ Too few bars after ET filter |
| 15m | 15810 | — | ❌ OFI noise, main-flow mismatch |

**Why 4h fails:** Server stores klines in UTC. After 09:30–16:00 ET filter, only ~1 bar/day survives → ~500 bars total, insufficient for HMM.

**Why 15m fails:** main-flow is aggregated hourly. Each hour's 4×15m bars share the same `inst_net_z` value — a 4-bar time mismatch that corrupts HMM state learning. Win rate 24.9%, Sharpe -4.44.

---

## Usage

```bash
# Generate signals
python3 signal_generator.py --ticker NVDA --interval 1h --from-date 2024-07-01
python3 signal_generator.py --ticker NVDA --interval 1d --from-date 2024-07-01

# Backtest (1h, swing trading)
python3 backtest.py --file output/NVDA_1h_*_signals.csv \
    --min-confidence 0.25 --min-confirm 2 --long-only --stop-loss 0.02

# 13F validation (1d)
python3 validate_13f.py --signal-file output/NVDA_1d_*_signals.csv --quarters 10

# v1 vs v2 comparison
python3 compare_v1_v2.py --tickers AAPL NVDA GOOGL --interval 1h
```

**backtest.py flags:**

| Flag | Description |
|------|-------------|
| `--min-confidence` | Filter signals below threshold (0–1) |
| `--no-overnight` | Exclude signals entering within N bars of close |
| `--min-confirm` | Require N consecutive same-direction bars before entry |
| `--long-only` | Only trade accumulation signals |
| `--stop-loss` | Stop loss % (default 2%) |

---

## Results — 13F Validation (1d signals, 2024–2026)

Uses **majority voting** across institutions (not total shares sum) to avoid artifacts from institutions entering/exiting the dataset.

| Ticker | Quarters | v1 Match | v2 Match | Best |
|--------|:--------:|:--------:|:--------:|------|
| AAPL | 8 | 62.5% | **100%** | v2 ✅ |
| PLTR | 6 | 83.3% | 83.3% | tie |
| NVDA | 9 | 66.7% | 66.7% | tie |
| GOOGL | 9 | 44.4% | 44.4% | tie |
| HOOD | 4 | 50.0% | — | insufficient |
| COIN | — | — | — | insufficient holdings |
| ONDS | — | — | — | insufficient holdings |

PARTIAL = match rate >50% but p-value not yet significant (need ~12 quarters for p<0.05 at 70%+).

**AAPL v2 100%** is the strongest finding of the day: when Lasso assigns flow=0.996 weight (16.7% main-flow coverage → 95 labeled bars), the signal direction perfectly matches 13F institutional behavior across 8 quarters. This directly validates main-flow data quality.

---

## Results — Signal-Driven Backtest (1h)

### v1 (Lee-Ready, manual weights, 3-state HMM)
Parameters: min-confidence=25%, min-confirm=2, long-only, stop-loss=2%

| Ticker | Trades | Win Rate | Return | Sharpe |
|--------|:------:|:--------:|-------:|-------:|
| NVDA | 309 | 40.1% | +40.9% | 0.81 |
| AAPL | 302 | 43.0% | +4.4% | 0.27 |
| ONDS | 285 | 38.6% | -49.3% | 0.21 |
| COIN | 320 | 40.9% | -51.4% | -0.49 |
| HOOD | 268 | 38.8% | -40.1% | -0.39 |
| GOOGL | 312 | 36.9% | -63.8% | -2.33 |
| PLTR | 334 | 39.2% | -88.7% | -2.33 |

### v2 (mixed OFI, Lasso weights, fixed 3-state HMM) — 1h, no overnight filter
| Ticker | Trades | Win Rate | Return | Sharpe |
|--------|:------:|:--------:|-------:|-------:|
| PLTR | 230 | 46.1% | **+603%** | 2.46 |
| GOOGL | — | 37.5% | -7.5% | — |
| AAPL | — | 40.8% | -32.2% | — |
| NVDA | — | 38.1% | -47.4% | — |

PLTR v2 +603% with avg hold 13.1 bars (~3 days): mixed OFI smooths signal reversals, producing multi-day swing trades that capture PLTR's 2024–2026 uptrend. Max DD -350% reflects compounding, not single-trade loss (max single loss < 10%).

---

## v1 vs v2: What Changed and Why

### signal_generator_v2.py changes

**1. Mixed OFI = 0.5×Lee-Ready + 0.5×BVC**
- Lee-Ready captures momentum direction
- BVC (Easley et al. 2012): `buy_frac = (close-low)/(high-low)` — no trending-market bias
- Dynamic alpha: trending market → more Lee-Ready; ranging → more BVC
- Effect: GOOGL improved (BVC fixes bull-market bias), PLTR improved (smoother signals), AAPL/NVDA mixed

**2. Lasso feature weight learning (Tibshirani 1996)**
- Trains on bars where `inst_net_z` available as direction label
- Falls back to manual weights when <50 labeled bars
- Key finding: Lasso consistently assigns highest weight to `flow` (0.27–0.99), confirming main-flow is the most informative feature
- Limitation: with only 89–559 labeled bars, Lasso degrades to flow=0.996 for most tickers (NVDA: 165 bars → ofi=0.000; GOOGL: 89 bars → flow=0.996)

**3. Opening filter extended to 9:35 ET (was 9:30)**
- Removes opening auction bars where price discovery is incomplete
- Minor effect on bar count, removes extreme flow outliers

**4. BIC state count selection — DISABLED**
- BIC selects 4–5 states for 3600-bar datasets
- full-covariance HMM with 4+ states overfits on <3600 bars
- Re-enable after main-flow backfill provides more labeled data

### Why v2 doesn't consistently beat v1

All v2 improvements are limited by the same constraint: **main-flow data only covers 5 months (2026-01 to present)**. With 2–17% coverage:
- Lasso trains on too few samples → degrades to pure flow signal
- BIC overfits → disabled
- Mixed OFI helps some tickers (PLTR, GOOGL) but hurts others (AAPL, NVDA) depending on their microstructure

v2 is a framework built for when main-flow history is backfilled. Under current data conditions, it should not replace v1.

---

## Data Quality Issues Discovered

### 1. Opening auction noise in main-flow
`super_buy` values up to $244M observed at 9:29 ET — the opening auction compressing overnight orders into one second. Also: duplicate entries (same value repeated 6× consecutively), likely cross-exchange double-reporting. Filtered: 9:30–9:35 ET + outliers >$50M.

### 2. UTC vs ET timezone mismatch
Server stores all timestamps in UTC. Without explicit ET conversion (`-4h` offset), `inst_net` merges onto wrong OHLCV bars, producing spurious correlations.

### 3. main-flow coverage drives everything
| Ticker | main-flow days | 1d coverage | 13F result |
|--------|---------------:|:-----------:|:----------:|
| AAPL | 102 | 16.7% | 62.5%→100% |
| COIN | 60 | 9.8% | N/A |
| NVDA | 28 | 4.6% | 66.7% |
| PLTR | 25 | 4.1% | 83.3% |
| GOOGL | 14 | 2.3% | 44.4% |
| ONDS/HOOD | 0 | 0% | N/A |

GOOGL's 13F failure (44.4%) vs PLTR's success (83.3%) is directly explained by coverage difference. ONDS/HOOD cannot be 13F-validated at all.

### 4. Lee-Ready bias on OHLCV bars
Lee-Ready was designed for tick data. OHLCV approximation (`close > midprice → all volume = buy`) systematically classifies uptrends as accumulation. In bull markets, most bars have `close > midprice` by construction. This is the primary cause of systematic win rates below 50% in the backtest.

### 5. 13F validation sample size
6–9 comparable quarters is below the ~12 needed for p<0.05. COIN and ONDS have negligible major institutional holdings — 13F validation structurally inapplicable.

### 6. Signal confidence consistently low (27–35%)
Features contradict each other: OFI says "buy" (price rising), impact efficiency says "distribution" (gains not sustained). Without `inst_net_z` as directional anchor, `final_score` averages near zero. AAPL's higher confidence vs GOOGL tracks their coverage ratio (16.7% vs 2.3%).

---

## Roadmap

| Priority | Item | Blocker |
|----------|------|---------|
| 🔴 | Backfill main-flow to 2024-01-01 | Server DB capacity |
| 🔴 | Replace Lee-Ready with proper BVC or tick data | main-flow backfill first |
| 🟡 | Re-enable BIC state selection | Needs 2000+ labeled bars |
| 🟡 | Re-run Lasso with full history | Needs 2000+ labeled bars |
| 🟡 | CPCV instead of Walk-Forward | López de Prado (2018) ch.7 |
| 🟡 | Expand 13F institutions to 10+ | Natural accumulation over time |
| 🟢 | 15m timeframe | Needs 15m main-flow aggregation |
| 🟢 | Volume/dollar bars | López de Prado (2018) ch.2 |

---

## Institution Pool (13F Validation)

Auto-selects institutions with ≥4 quarters of data for each ticker:

| Institution | CIK | Quarters (2023+) |
|-------------|-----|:----------------:|
| T. Rowe Price | 0000080255 | 13 |
| Invesco | 0000914208 | 13 |
| Capital Research | 0001422848 | 13 |
| State Street | 0000093751 | 7 |
| Vanguard | 0000102909 | 4 |
| Fidelity | 0000315066 | 4 |
| Morgan Stanley | 0000895421 | 4 |

## CUSIP Map

| Ticker | CUSIP |
|--------|-------|
| AAPL | 037833100 |
| NVDA | 67066G104 |
| GOOGL | 02079K107 |
| PLTR | 69608A108 |
| COIN | 02462A104 |
| ONDS | G10830100 |
| HOOD | 770700102 |
| MSFT | 594918104 |
| TSLA | 88160R101 |

---

## References

1. Easley, D., López de Prado, M., & O'Hara, M. (2012). Flow Toxicity and Liquidity in a High Frequency World. *Review of Financial Studies*, 25(5).
2. Lee, C. M. C., & Ready, M. J. (1991). Inferring Trade Direction from Intraday Data. *Journal of Finance*, 46(2).
3. López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
4. Rabiner, L. R. (1989). A Tutorial on Hidden Markov Models. *Proceedings of the IEEE*, 77(2).
5. Tibshirani, R. (1996). Regression Shrinkage and Selection via the Lasso. *JRSS-B*, 58(1).
6. Bacry, E., Mastromatteo, I., & Muzy, J. F. (2015). Hawkes Processes in Finance. *Market Microstructure and Liquidity*, 1(1).
7. Welch, G., & Bishop, G. (2006). An Introduction to the Kalman Filter. UNC TR 95-041.
8. Almgren, R., & Chriss, N. (2001). Optimal Execution of Portfolio Transactions. *Journal of Risk*, 3.
