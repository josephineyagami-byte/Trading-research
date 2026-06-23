# Institutional Flow Detection — Project Handoff & Progress Report
**Last updated: 2026-06-23**
**Server: 104.192.7.156 (API :8000 / ClickHouse :8123 / Export tool :3000)**
**Project directory: ~/Downloads/Quant Trading Research/**

---

## 1. Project Overview

**Goal:** Detect institutional accumulation/distribution behavior using HMM + order flow features. Validate signals against SEC 13F quarterly filings. Eventually build a classification-based weight system that adapts to different stock types, and test whether signals can generate alpha through appropriate trading strategies.

**Core pipeline:**
```
OHLCV + main-flow API → compute_features() → fit_hmm() → compute_signal() → signal CSV
                                                                                    ↓
                                                              validate_13f.py (13F + OOS + bootstrap)
                                                              backtest.py (event study + IC + signal-driven)
                                                              feature_ic_analysis.py (per-feature IC)
```

---

## 2. Current File Status

### Core scripts (all in project directory)

| File | Purpose | Status |
|---|---|---|
| `signal_generator_v3.py` | Main signal generator | ✅ HMM fix + dedup + oos column |
| `backtest.py` | 4-method backtest validation | ✅ Usable |
| `validate_13f.py` | 13F quarterly validation + bootstrap | ✅ --oos-only added |
| `feature_ic_analysis.py` | Per-feature IC analysis | ✅ Usable |
| `batch_feature_ic.py` | Multi-ticker batch IC analysis | ✅ Failed-ticker bug fixed |
| `fetch_candidate_features.py` | Pull short interest / dark pool / large trade total | ✅ Dedup + dark pool added |
| `plot_inst_flow.py` | Interactive Plotly chart (K-line + flow signals) | ✅ Linked hover + zoom + y-axis adaptive |
| `diagnose_coverage.py` | main-flow coverage diagnostic | ✅ Usable |

---

## 3. Completed Work This Session

### 3.1 Backtest Analysis (AAPL 1h)

Ran full 4-method backtest on AAPL 1h v3 signals. Key findings:

**Confidence tier inversion** — higher confidence → worse returns (a consistent pattern across all tickers):
```
Low  (0-25%):   57.8% win rate  +0.288%
Mid  (25-50%):  47.8% win rate  +0.089%
High (50-75%):  43.4% win rate  -0.114%
Very high (75%+): 36.4% win rate  -0.610%
```

**Root cause confirmed:** Not just HMM boost — the raw_score feature weighting itself is the primary source. `liq_abs_z` gets 0.10 weight but has avg|IC|=0.013. `ofi_z` gets 0.15 weight but has avg|IC|=0.096. The weight table does not reflect actual predictive power.

### 3.2 HMM Label Quality Fix (Applied)

**Problem:** `fit_hmm()` unconditionally used `idxmax()/idxmin()` to force-label states as accumulation/distribution, even when all states had `inst_mean ≤ 0`. This manufactured false accumulation signals with fake HMM boost.

**Fix applied to `signal_generator_v3.py`:**
1. Labels now require statistical significance (one-sample t-test p<0.05, correct direction) to be assigned
2. `hmm_boost` changed from flat ±0.15 to proportional: `direction_sign × hmm_strength × 0.15`
3. States that don't pass the bar are correctly labeled `neutral`

**Result after fix:**
```
[HMM] Quality-gated labels: {0: 'distribution', 1: 'neutral', 2: 'neutral'}
```
Previously all-negative `inst_mean` states were incorrectly labeled as accumulation. Now correctly rejected.

**Finding:** Confidence inversion persists after fix — confirming the root cause is deeper in `raw_score` weighting, not just HMM.

### 3.3 Per-Feature IC Analysis (5 tickers)

Results across AAPL, NVDA, PLTR, GOOGL, COIN:

| Feature | AAPL avg|IC| | Rank (OHLCV only) | Consistent sign |
|---|---|---|---|
| ofi_z | 0.0960 | 1/7 | ✅ |
| inst_net_z | 0.0506 | — (data quality issues) | ❌ |
| rvol | 0.0397 | 3/7 | ✅ |
| liq_abs_z | 0.0131 | 7/7 (worst) | ❌ |

**Key finding: Feature predictive power is ticker-specific.** `ofi_z` ranks 1st on AAPL and COIN, 4th on GOOGL. No single feature is universally best.

**Critical discovery:** `inst_net_z` (main-flow, 0.50 weight) shows **-0.80 Spearman correlation** between coverage rate and IC strength across 5 tickers. Low coverage = artificially high IC. This is a statistical artifact, not real predictive power.

### 3.4 Candidate Feature Testing

Tested 4 new candidate features (AAPL 1h):

| Feature | avg|IC| | 24bar IC | Consistent | Coverage | Verdict |
|---|---|---|---|---|---|
| dark_pool_pct | 0.0799 | **0.1911** | ✅ | 58.2% | ⚠️ Not usable in real-time |
| large_trade_total | 0.0304 | -0.0859 | ❌ | 47.7% | ❌ Noise |
| short_volume_pct | 0.0281 | 0.0074 | ❌ | 93.4% | ❌ Noise |
| short_interest | 0.0182 | -0.0098 | ❌ | 96.4% | ❌ Noise |

**Dark pool conclusion:**
- Has strong 24-bar IC (0.1911) with monotonically increasing pattern across horizons
- **Cannot be used in real-time signal generation** — FINRA data has ~2 week disclosure lag
- **Correct use:** Post-hoc validation tool ("high-frequency 13F") — verify whether HMM's institutional activity judgments align with actual dark pool activity
- Does not carry directional information (ats_shares doesn't distinguish buy vs sell)

### 3.5 Data Quality Findings

**Large-trades duplicate rates (confirmed via dedupe_large_trades.py):**

| Period | Duplicate rate | Notional inflation | Pattern |
|---|---|---|---|
| 2025-10~11 | 1.7% | 36.6% | Multi-channel reporting (different conditions) |
| 2026-03~04 | **20.8%** | **69.6%** | Batch re-insertion (identical id rows) |
| Full pull (latest) | **32.5%** | ~47% | Worsening over time |

**Fix applied:** `load_large_trades()` in `signal_generator_v3.py` now deduplicates on `(time, price, size, exchange)` before normalizing field names. Reduces noise in `inst_net` calculations.

**main-flow coverage vs IC correlation:**
```
Spearman r = -0.80 (5 tickers)
```
Higher coverage → lower apparent IC. This means NVDA (8% coverage, IC=0.2159) and PLTR (13.7%, IC=0.1363) show falsely strong inst_net_z IC — concentrated in the heavily-polluted 2026 data window.

### 3.6 13F Validation Results

**Full-data validation (no OOS, 4 tickers with sufficient data):**

| Ticker | Match rate | Bootstrap p | Conclusion |
|---|---|---|---|
| AAPL | 66.7% (4/6) | 0.3374 | Not significant |
| PLTR | 16.7% (1/6) | 0.9849 | Systematically reversed |
| GOOGL | 57.1% (4/7) | 0.4985 | Not significant |
| NVDA | 42.9% (3/7) | 0.7692 | Not significant |

**OOS validation (train-end 2026-03-01, only 1 comparable quarter):**

| Ticker | Model (OOS) | 13F actual | Correct |
|---|---|---|---|
| AAPL | distribution | distribution | ✅ |
| GOOGL | distribution | distribution | ✅ |
| NVDA | distribution | accumulation | ❌ |
| PLTR | neutral | distribution | ❌ indeterminate |

OOS pipeline confirmed working: `--train-end` → `oos` column → `--oos-only` filter chain is clean.

### 3.7 Multi-ticker Backtest Comparison

| Ticker | Acc signal (Event Study) | Dist signal | Signal-driven Sharpe | Confidence tier |
|---|---|---|---|---|
| AAPL | ✅ Correct (24bar +1.6%) | ✅ Correct | +0.21 | ❌ Inverted |
| GOOGL | ✅ Correct (24bar +1.9%) | ✅ Strong (5/5 significant) | -3.60 | Partially inverted |
| NVDA | ❌ No direction | ✅ Correct (3/5) | -1.46 | ✅ Normal (small sample) |
| PLTR | ❌ No direction | ❌ No direction | -1.83 | Partially normal |
| COIN | ❌ Reversed (24bar -2.0%) | ❌ Reversed (+3.0%) | -0.37 | Inverted |

**GOOGL insight:** Distribution signals are strong and consistent (5/5 horizons significant, -3.220% at 24bar). Accumulation signals are weak. The model is asymmetrically useful for GOOGL — useful for sell signals, blind to buy signals.

### 3.8 Interactive Chart (plot_inst_flow.py)

Final implementation: Plotly `make_subplots` + `hoversubplots="axis"` + custom `post_script` JS.

Features:
- 3-layer layout: K-line / raw_score vs final_score / cumulative_inventory
- Linked hover across all 3 panels (Plotly 5.21+ `hoversubplots="axis"`)
- Zoom/pan with y-axis auto-fit to visible window (embeds TS/INV/SCORE/HIGH/LOW arrays, JS computes visible-range min/max on relayout)
- NaN warmup handling (uses `.notna().any()` not `[0]` check)
- Cross-subplot zoom sync with infinite-loop guard (`_syncing` flag + `.then()`)

Usage:
```bash
python3 plot_inst_flow.py --file output/AAPL_1h_xxx_v3_signals.csv
open output/AAPL_1h_xxx_v3_signals_chart.html
```

---

## 4. Future Roadmap & Thinking

### 4.1 Core Strategic Direction

The fundamental insight from this session is that **feature predictive power is ticker-specific**, and a single fixed weight table cannot work well across all stocks. The proposed solution:

```
Ticker → Classify by type → Assign type-specific weight set → Signal generation
```

This avoids continuous retraining (v2 Lasso lesson) while allowing meaningful differentiation. Weight sets are determined offline from IC analysis, updated periodically (e.g. quarterly), not per-bar.

### 4.2 Ticker Classification Framework

**Classification dimensions (to be quantified):**

| Dimension | Metric | Example |
|---|---|---|
| Liquidity / size | Market cap, avg daily volume | AAPL/GOOGL = large cap |
| Institutional coverage | 13F institution count, inst. ownership % | AAPL = high, COIN = low |
| Volatility regime | 30-day realized vol, VIX beta | COIN/NVDA = high vol |
| Price driver | Fundamental vs narrative/sentiment | PLTR/COIN = narrative-driven |
| main-flow reliability | Coverage rate, duplicate rate | AAPL = most reliable |

**Preliminary classification (5 current tickers):**

| Type | Tickers | Characteristics | Weight emphasis |
|---|---|---|---|
| A | AAPL, GOOGL | Large cap, high inst., fundamentals | ofi_z high, liq low |
| B | NVDA, PLTR | Mid/large, mixed driver, moderate vol | Balanced |
| C | COIN | High vol, low inst., narrative-driven | rvol high, ofi low |

### 4.3 How Classification Affects Signal Generation

**Weight set selection:** Based on ticker type, `compute_signal()` uses a different `WEIGHTS_WITH_FLOW` / `WEIGHTS_NO_FLOW` dictionary. The weight set is fixed offline — not retrained in real time.

**HMM is NOT affected by weight sets:** `fit_hmm()` trains on raw `inst_net_z` + `ofi_z` regardless of ticker type. The weight set only affects `compute_signal()` — specifically the `raw_score = Σ(weight[i] × feature[i])` calculation.

**Indirect effect on confidence:** Since `final_score = raw_score + hmm_boost`, and `raw_score` is computed with type-specific weights, the same HMM state produces different `final_score` magnitude for different ticker types. Type A (high ofi_z weight) → raw_score more driven by OFI. Type C (high rvol weight) → raw_score more driven by relative volume.

### 4.4 Validation → Strategy → Backtest Chain

The correct order (do not skip steps):

```
Step 1: Validation — "Is the signal direction correct?"
        Tool: validate_13f.py --oos-only + bootstrap
        Target: p < 0.05 on multiple quarters, multiple tickers
        Current status: Not yet achieved (data quality blocker)

Step 2: IC analysis — "Does signal strength correlate with return magnitude?"
        Tool: feature_ic_analysis.py + backtest.py (confidence tier)
        Target: No confidence inversion, avg|IC| > 0.05 on 3+ tickers
        Current status: Partial (ofi_z moderate on AAPL/COIN)

Step 3: Strategy design — "Can correct signals generate profit?"
        Requires: Price confirmation layer (mentor feedback)
        Design: Signal must be confirmed by price action (e.g. close > VWAP,
                volume breakout) before entry. Reduces frequency, improves quality.
        Current status: Not implemented

Step 4: Backtest with strategy — "Does the full system make money?"
        Tool: backtest.py with custom entry/exit rules
        Target: Positive Sharpe, max drawdown < 20%, consistent across tickers
        Current status: All tickers negative Sharpe with current signals
```

### 4.5 Noise Identification & Removal

**Three tools for noise identification (already available):**

1. **IC sign consistency** — features with INCONSISTENT sign across horizons are noise sources (`clv`, `liq_abs_z`, `inst_net_z` all flagged)
2. **Event study direction** — if accumulation signal → price falls (COIN), the model is inverted for that ticker. Use ticker-specific IC to detect and exclude unreliable features
3. **Confidence tier analysis** — if high confidence → worse returns, the feature(s) pushing up final_score are noise, not signal

**Noise removal approach (data-driven, not automated training):**
- For features with avg|IC| < 0.03 AND sign inconsistent across 3+ tickers → set weight to 0 or near-0 for that ticker type
- This is a manual, evidence-based decision — not parameter optimization
- Prevents overfitting while improving signal quality

### 4.6 Dark Pool as High-Frequency 13F

**Proposed validation framework (to be built):**

Instead of using `dark_pool_pct` as a signal input, use it as a validation benchmark:

```
Hypothesis: When HMM detects high institutional activity (high hmm_strength,
            regardless of direction), dark_pool_pct should also be elevated
            in that week.

Test: Correlation between weekly hmm_strength (averaged per week) and
      weekly dark_pool_pct change.

If correlation is positive and significant → HMM is detecting real
institutional activity, even if direction judgment needs more work.

If no correlation → HMM states are driven by noise, not real institutional
flows. Stronger evidence to revisit HMM feature inputs.
```

This answers "is the model detecting real activity?" separately from "is the directional call correct?" — an important diagnostic distinction.

### 4.7 ClickHouse signal_scores Table (To Design with Teammate)

For teammate's frontend integration, need a table:

```sql
CREATE TABLE signal_scores (
    ticker        String,
    datetime      DateTime,
    interval      String,         -- '1h', '1d', '5m'
    raw_score     Float32,
    final_score   Float32,
    signal        String,         -- 'accumulation', 'distribution', 'neutral', etc.
    confidence    Float32,
    hmm_label     String,
    hmm_strength  Float32,
    cumulative_inventory Float64,
    est_inst_participation Float32,
    oos           UInt8,          -- 1 if out-of-sample bar
    generated_at  DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (ticker, interval, datetime);
```

Teammate needs to add API endpoint: `/api/signals?ticker=X&interval=1h&from=Y&to=Z`

---

## 5. Immediate Next Steps (Priority Order)

### Now (can do immediately)

1. **More ticker IC analysis** — extend to 10+ tickers to get enough data for ticker classification. Priority: SPY, QQQ (index baseline), TSLA, MSFT, AMD (different characteristics)

2. **Quantify classification metrics** — write a script that pulls volatility, institutional ownership %, and market cap for each ticker, outputs a classification table

3. **Design dark pool validation framework** — compute weekly `hmm_strength` averages, correlate with weekly `dark_pool_pct` changes for AAPL (most reliable data)

4. **OOS validation second quarter** — re-run when 2026-Q2 13F data is available (~August 2026). Will provide the second OOS data point needed for statistical power

### Waiting on teammate

5. **Trades table dedup** — fix at database level so duplicate rows don't re-enter on every fresh pull. Priority: 2026 batch re-insertion issue most severe

6. **main-flow coverage gaps** — investigate why Jul-Sep 2025 data is missing for most tickers. Fix monthly computation job scheduling

7. **ClickHouse signal_scores table + API endpoint** — for frontend integration

### After data cleaning

8. **Re-run all IC analysis** — get clean baseline numbers for feature weighting decisions

9. **Re-run 13F validation** — compare against current results. If AAPL/GOOGL improve, confirms data quality was the main blocker

10. **Weight table redesign** — based on clean IC results, design Type A/B/C weight sets. Use multi-ticker IC pooling within each type to get stable estimates

11. **Price confirmation layer** — implement mentor's feedback: signal + price confirmation gate before entry. Design specific rules (e.g. signal=accumulation AND close > 5-day VWAP AND volume > 1.2x average)

12. **Strategy backtest** — test the full pipeline (classification weights + price confirmation) against historical data for each ticker type

---

## 6. Known Issues & Constraints

### Data quality (blocking)
- main-flow duplicate rates: 1.7% (2025) → 20.8% (2026-Q1) → 32.5% (latest pull)
- main-flow coverage: AAPL 25-48%, NVDA 6-12%, PLTR 7%, GOOGL 5%
- 2025-07 to 2025-09: large-trades API returns 500 errors
- 2025-07 to 2026-01: main-flow has 122 missing trading days for AAPL 1h

### Model limitations (known)
- All 5 tickers show negative signal-driven Sharpe with current weights
- Confidence tier inversion persists after HMM fix — raw_score weighting is the root cause
- HMM fails to find real accumulation states when main-flow coverage is low
- PLTR signals are essentially uncorrelated with 13F (complete noise on this dataset)
- COIN signals are systematically reversed — not usable as-is

### Methodology constraints
- 13F validation limited to 1 OOS quarter (78 bars) with train-end 2026-03-01
- Cannot do true real-time trading with dark_pool_pct (2-week disclosure lag)
- IC analysis single-ticker samples too small for reliable weight estimation
- Signal-driven backtest assumes uniform position sizing — no risk management

---

## 7. Design Decisions Log

| Decision | Rationale |
|---|---|
| No trained weights (avoid v2 Lasso repeat) | Small samples + dirty data = overfitting noise. Data-driven manual adjustment instead |
| HMM quality threshold (statistical significance) | Prevents manufacturing fake accumulation states when all inst_mean ≤ 0 |
| dark_pool_pct as validation only, not signal input | 2-week disclosure lag makes real-time use impossible |
| OOS train-end 2026-03-01 | Covers ~8 months training, 3.5 months OOS, includes 2026-Q1 13F for validation |
| K-line from-date 2024-06-24 (not 2025-07-01) | K-line and main-flow are independent data sources. Using 2025-07-01 for K-lines was an unnecessary restriction |
| large-trades dedup in load_large_trades() | Fix at analysis layer even before DB-level fix — keeps our own analysis clean |
| Classification before weighting | Features don't generalize across ticker types. Must classify first, then determine weights per type |
