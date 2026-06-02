## Overview 1

## Methodology

### Data Pipeline

```
OHLCV K-lines (via API)
        ↓
Feature Engineering (6 dimensions)
        ↓
HMM State Segmentation (unsupervised)
        ↓
Composite Scoring (weighted combination)
        ↓
Signal Output + Confidence Score
        ↓
Backtest Validation + 13F Verification
```

### Feature Engineering

#### 1. Lee-Ready Trade Direction Classification

Approximates tick-level trade direction from OHLCV data:

```python
midprice = (high + low) / 2

if close > midprice:
    direction = +1   # buyer-initiated
elif close < midprice:
    direction = -1   # seller-initiated
else:
    direction = sign(close - prev_close)  # tick rule fallback
```

**Limitation:** Original Lee-Ready (1991) requires tick-level data. This OHLCV approximation introduces systematic directional bias, particularly on the accumulation side. Future work will replace this with Bulk Volume Classification (Easley, López de Prado & O'Hara, 2012).

#### 2. Order Flow Imbalance (OFI)

```
signed_volume = direction × volume
OFI_raw = Σ(signed_volume, window=5)
OFI_z   = OFI_raw / rolling_std(OFI_raw, window=20)
```

Persistent positive OFI indicates sustained buy-side pressure, consistent with institutional accumulation via POV execution.

#### 3. VWAP Deviation (vwap_dev)

```
vwap_roll = Σ(close × volume, 20) / Σ(volume, 20)
vwap_dev  = (close - vwap_roll) / vwap_roll
```

Institutional algorithms benchmark to VWAP. Sustained positive deviation indicates large passive buyers supporting price.

#### 4. Relative Volume (RVOL)

```
rvol = volume / rolling_mean(volume, 20)
```

Institutional execution is volume-driven. RVOL > 1.5 combined with low price impact indicates institutional participation.

#### 5. Impact Efficiency (impact_eff_z)

```
impact_eff = |ΔPrice| / volume
```

Institutional hallmark: high volume, low price movement. Low impact efficiency during elevated volume indicates passive liquidity absorption.

#### 6. Liquidity Absorption (liq_abs_z)

```
liq_absorption = RVOL / (price_range × 100)
```

High volume with suppressed volatility indicates a large passive counterparty continuously absorbing supply — the strongest institutional accumulation signature.

#### 7. Price Persistence

```
price_persistence = mean(ret, 3) / std(ret, 3)
```

Institutional impact is partially permanent (Gatheral, 2010). Rapid full reversions indicate temporary liquidity shocks rather than institutional positioning.

#### 8. Institutional Net Flow (inst_net_z)

Sourced directly from the `main-flow` API endpoint:

```
inst_net = super_buy + large_buy - super_sell - large_sell
```

Where trades are classified by notional value:
- Super: ≥ $500K
- Large: $100K–$500K  
- Mid: $20K–$100K
- Small: < $20K

Direction determined by tick rule. Available from 2026-01-01 onward.

### Hidden Markov Model State Segmentation

The HMM learns to identify 3 latent market regimes from the 6 features above.

**What the HMM learns (unsupervised):**

1. **Feature distributions per state** — the mean and covariance of each feature in each state
2. **Transition probabilities** — how likely the market is to remain in or switch between states
3. **State assignment** — which bars belong to which regime

**Learning algorithm: Baum-Welch (EM)**

```
Initialize → random parameters
E-step    → compute P(state | observations, parameters)
M-step    → update parameters to maximize log-likelihood
Repeat    → until convergence
```

**State labeling** (post-hoc, based on feature profiles):

```
State with highest OFI + inst_net mean → "accumulation"
State with lowest  OFI + inst_net mean → "distribution"
Remaining state                        → "neutral"
```

**HMM contribution to final score:**

```python
hmm_boost = {
    "accumulation":  +0.15,
    "distribution":  -0.15,
    "neutral":        0.00
}
final_score = clip(raw_score + hmm_boost, -1, +1)
```

### Composite Scoring

Six features are normalized to [-1, +1] and combined with fixed weights:

```python
raw_score = (
    0.25 × OFI_z
  + 0.20 × liq_abs_z
  + 0.15 × RVOL
  + 0.15 × (-impact_eff_z)   # inverted: low efficiency = institutional
  + 0.10 × CLV
  + 0.10 × price_persistence
  + 0.05 × inst_net_z         # weight increases when main-flow available
)
```

**Signal classification:**

| Score Range | Signal |
|-------------|--------|
| > +0.35 | `strong_accumulation` |
| +0.10 to +0.35 | `accumulation` |
| -0.10 to +0.10 | `neutral` |
| -0.35 to -0.10 | `distribution` |
| < -0.35 | `strong_distribution` |

---

## Validation Framework

### Two-Layer Validation Logic

```
Layer 1: 13F Validation  →  Proves methodology direction (quarterly)
Layer 2: Backtest        →  Proves signal operability (daily)
```

These are complementary, not substitutes. 13F passing means the framework captures real institutional behavior. Backtest passing means the signal generates alpha.

### Layer 1: SEC 13F Validation

**Logic:**

```
signal_generator daily signals
        ↓
Aggregate to quarterly direction
(accumulation if acc_bars > dist_bars)
        ↓
Compare against SEC EDGAR 13F net change
(Vanguard + State Street + Fidelity)
        ↓
Direction match rate + binomial test
```

**Data sources:** SEC EDGAR `submissions` API (free, no API key required), Vanguard (CIK 0000102909), State Street (CIK 0000093751), Fidelity (CIK 0000315066).

**CUSIP mapping** auto-resolved from Vanguard 13F XML for any ticker.

### Layer 2: Backtest Validation

Four modules:

**Event Study** — Average return in N bars following each signal type, with t-test significance.

**Information Coefficient (IC)** — Spearman rank correlation between `final_score` and forward returns. Measures whether signal strength predicts return magnitude, not just direction.

```
IC > +0.05  → signal has predictive power (direction correct)
IC < -0.05  → signal has predictive power (direction inverted)
IC ≈ 0      → no predictive relationship
```

**Walk-Forward Validation** — Rolling 60-bar training window, predict next N bars. Simulates real-world out-of-sample performance without look-ahead bias.

**Confidence Tier Analysis** — Whether higher-confidence signals produce better outcomes. Monotonically increasing returns by confidence tier indicates the confidence score itself is informative.

---

## Results (2025-01-02 to 2026-06-01)

### Backtest Results Summary

| Ticker | Distribution 10bar | Accum 20bar | WF Sharpe | main-flow |
|--------|-------------------|-------------|-----------|-----------|
| AAPL | -2.84% ✅ p<0.001 | +2.15% ✅ | -3.21 ❌ | 20 days |
| TSLA | -2.02% ✅ p<0.05 | +1.19% ❌ | -0.77 ❌ | 14 days |
| NVDA | -2.52% ✅ p<0.001 | +3.65% ✅ | +1.32 ✅ | none |
| MSFT | -0.80% ❌ | +0.60% ❌ | +2.10 ✅ | 10 days |
| GOOGL | -3.81% ✅ p<0.001 | +5.73% ✅ | +1.33 ✅ | 10 days |

**Key finding:** Distribution signals are statistically significant across AAPL, TSLA, NVDA, and GOOGL. Accumulation signals show significance only at longer horizons (20 bar), consistent with the slow, persistent nature of institutional building.

**IC Analysis (AAPL):**

| Horizon | IC | p-value | Rating |
|---------|-----|---------|--------|
| 3 bar | -0.114 | 0.033 | ⭐⭐⭐ |
| 5 bar | -0.160 | 0.003 | ⭐⭐⭐ |
| 10 bar | -0.188 | 0.001 | ⭐⭐⭐ |

Negative IC reflects Lee-Ready directional bias on daily data. The distribution direction is captured correctly; accumulation direction requires improvement.

### 13F Validation Results

| Ticker | Q2 2025 | Q3 2025 | Q4 2025 | Match Rate | Conclusion |
|--------|---------|---------|---------|------------|------------|
| AAPL | ✅ | ✅* | ❌ | 66.7% | PARTIAL |
| TSLA | ❌ | ❌ | ❌ | 0.0% | FAIL |
| NVDA | ✅ | ❌ | ✅ | 66.7% | PARTIAL |
| MSFT | ✅ | ✅ | ✅ | **100%** | PARTIAL† |
| GOOGL | ❌ | ❌ | ❌ | 0.0% | FAIL |

*AAPL Q3 2025: corrected from FAIL to PASS after main-flow data integration  
†Statistical significance not reached due to n=3 quarters (minimum 6 required)

**Critical finding — Q3 2025 systematic correction:**

All tickers without main-flow data incorrectly predicted accumulation in Q3 2025, while the actual 13F showed institutional distribution of -1.99% to -4.51%. This quarter coincided with a major market drawdown. Tickers with even limited main-flow data (AAPL: 20 days, MSFT: 10 days) correctly identified distribution. This directly demonstrates main-flow is essential for detecting systematic institutional de-risking.

**MSFT anomaly:**

MSFT showed 100% 13F match rate (3/3 quarters) and Walk-Forward Sharpe of 2.10 after main-flow integration. This is the only ticker where both validation layers pass simultaneously. MSFT's institutional-dominated, low-volatility profile is the ideal environment for this framework.

**GOOGL paradox:**

GOOGL has the strongest backtest performance (Sharpe 1.33, distribution 20bar -7.92%) but 0% 13F match rate. The model captures real price predictability in GOOGL, but this signal appears to reflect short-term price momentum rather than institutional positioning per se.

---

## Known Limitations

| Limitation | Root Cause | Planned Fix |
|------------|-----------|-------------|
| Accumulation direction bias | Lee-Ready OHLCV approximation | Replace with BVC (Easley et al., 2012) |
| HMM non-convergence | Insufficient sample size for 6D features | Requires main-flow backfill to 2025 |
| Fixed feature weights | Not data-driven | Lasso regression for optimal weights |
| Fixed 3 HMM states | May not be optimal | BIC/AIC automatic selection |
| main-flow only from 2026-01 | Data collection start date | Historical backfill required |
| 3 quarters 13F sample | Too small for statistical significance | Need 6+ quarters minimum |
| Negative IC | Direction inversion on accumulation | Tied to Lee-Ready fix |

---

## Files

```
signal_generator.py   — Feature engineering, HMM training, signal output
backtest.py           — Event study, IC, Walk-Forward, confidence analysis
validate_13f.py       — SEC EDGAR 13F data fetch and comparison
output/               — Generated signal CSV files
reports/              — Backtest and validation text reports
```

### Usage

```bash
# Install dependencies
pip install numpy pandas scipy hmmlearn requests scikit-learn

# Step 1: Generate signals
python signal_generator.py --ticker AAPL --interval 1d --from-date 2025-01-01

# Step 2: Backtest validation
python backtest.py --file output/AAPL_1d_xxx_signals.csv

# Step 3: 13F methodology validation
python validate_13f.py --signal-file output/AAPL_1d_xxx_signals.csv --quarters 8

# Optional: specify main-flow date range
python signal_generator.py --ticker MSFT --interval 1d --from-date 2025-01-01 --flow-from 2026-01-01
```

---

## Roadmap

**Priority 1 — Data**
- [ ] main-flow historical backfill to 2025-01-01
- [ ] Extend to additional tickers: META, AMZN, SPY

**Priority 2 — Methodology**
- [ ] Replace Lee-Ready with Bulk Volume Classification
- [ ] Volume Bar / Dollar Bar construction (López de Prado, 2018 Ch.2)
- [ ] BIC/AIC automatic HMM state selection
- [ ] Lasso regression for feature weight optimization
- [ ] Kalman Filter for dynamic state tracking

**Priority 3 — Validation**
- [ ] Expand to 8+ quarters for statistically significant 13F test
- [ ] Combinatorial Purged Cross-Validation (López de Prado, 2018 Ch.7)
- [ ] Walk-Forward window extended from 60 to 120 bars

---

## References

**Market Impact & Order Flow**
- Bouchaud, J.P., Gefen, Y., Potters, M., & Wyart, M. (2004). *Fluctuations and Response in Financial Markets.* Quantitative Finance, 4(2), 176–190.
- Kyle, A.S. (1985). *Continuous Auctions and Insider Trading.* Econometrica, 53(6), 1315–1335.
- Gatheral, J. (2010). *No-Dynamic-Arbitrage and Market Impact.* Market Microstructure and Liquidity, 1(1).

**Trade Classification**
- Lee, C.M.C. & Ready, M.J. (1991). *Inferring Trade Direction from Intraday Data.* Journal of Finance, 46(2), 733–746.
- Easley, D., López de Prado, M.M., & O'Hara, M. (2012). *Flow Toxicity and Liquidity in a High Frequency World.* Review of Financial Studies, 25(5), 1457–1493.

**Institutional Execution**
- Almgren, R. & Chriss, N. (2001). *Optimal Execution of Portfolio Transactions.* Journal of Risk, 3(2), 5–39.
- Anand, A., Irvine, P., Puckett, A., & Venkataraman, K. (2012). *Institutional Trading and Stock Resiliency.* Journal of Financial Economics, 104(3), 646–663.

**Machine Learning in Finance**
- López de Prado, M.M. (2018). *Advances in Financial Machine Learning.* Wiley. *(Primary reference for Volume Bars, feature importance, and CPCV)*
- Rabiner, L.R. (1989). *A Tutorial on Hidden Markov Models and Selected Applications in Speech Recognition.* Proceedings of the IEEE, 77(2), 257–286.

**Latent State Estimation**
- Welch, G. & Bishop, G. (2006). *An Introduction to the Kalman Filter.* UNC Chapel Hill Technical Report TR 95-041.
- Bacry, E., Mastromatteo, I., & Muzy, J.F. (2015). *Hawkes Processes in Finance.* Market Microstructure and Liquidity, 1(1).

---

## Notes on Interpretation

13F validation proves **quarterly-level methodological credibility** — that the framework captures real institutional positioning direction. It does not validate individual daily signal operability. For daily signal usability, refer to the backtest report.

Statistical significance in the 13F test requires a minimum of 6 comparable quarters. Current results (n=3) should be interpreted as preliminary, with PARTIAL conclusions pending additional data.

