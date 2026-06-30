# Institutional Flow Detection — Progress Report
**Updated: 2026-06-30**
**Server: 104.192.7.156 (confirmed working — new server 74.208.124.247 not yet configured)**
**Project directory: ~/Downloads/Quant Trading Research/**

---

## Executive Summary (for 2026-06-30 review)

**What's new and validated:**
- With-flow ticker clustering (19 tickers, F0/F1/F2) is statistically the strongest result in the project's history — Bootstrap stability 0.846, all 5 features show significant between-cluster variance (F-ratio test).
- Found and fixed the actual bottleneck in Signal-Driven backtests: it was the signal-confirmation window (`min_confirm`), not stop-loss as previously suspected. Changing the default from 2→3 flipped AAPL's Signal-Driven Sharpe from -0.44 to **+0.97** and NVDA's from -0.47 to **+0.11**.
- Chart tooling upgraded: QQQ/SPY benchmark overlay + institutional accumulation/distribution markers, for visual sanity-checking of signals against price/macro context.

**What's NOT yet resolved — read before treating any ticker as "working":**
- AAPL's positive Sharpe holds under the Signal-Driven method but **reverses to -0.96 under Walk-Forward** (a different, simpler validation method). The improvement is conditional on one specific trading-rule set, not yet shown to be a general signal-quality win.
- GOOGL's accumulation signal is confirmed (by two independent methods: IC analysis and a 90-combination parameter sweep) to be undetectable with current features. Distribution signal is strong and usable; accumulation is not. This is a feature-level limitation, not fixable by reweighting or parameter tuning.
- The F2 cluster (13 of 19 with-flow tickers, including AAPL) has confirmed internal sub-structure — it's not one homogeneous group. This likely explains why AAPL did worse under F2's averaged weights than under simpler flat weights, and means F2-based results for any of its 13 members should be treated as provisional pending sub-group re-weighting.
- 13F validation is paused — main-flow's usable history (~2025-07 onward) only supports 3 comparable quarters, not enough for statistical significance regardless of match rate.
- Main-flow data quality is unresolved at the database level (32.5% duplicate rate for AAPL) — all with-flow results in this report are "best available," not "clean."

**Bottom line:** real progress on methodology and diagnostic capability this session, but no ticker yet has a fully cross-validated positive result. AAPL is the closest, with one major open caveat (Walk-Forward disagreement).

---

## 1. Project Overview

Detect institutional accumulation/distribution behavior using HMM + order flow features. Validate signals against SEC 13F quarterly filings. Build a classification-based weight system that adapts to different stock types.

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

| File | Purpose | Status |
|---|---|---|
| `signal_generator_v4.py` | Main signal generator | ✅ With-flow cluster weights wired in (19-ticker validated); raw_data_cache/ added |
| `backtest.py` | 4-method backtest validation | ✅ Win rate shows success/total; `min_confirm` default changed 2→3 (see section 3.10) |
| `validate_13f.py` | 13F quarterly validation + bootstrap | ✅ --oos-only supported |
| `feature_ic_analysis.py` | Per-feature IC analysis | ✅ Usable |
| `batch_feature_ic.py` | Multi-ticker batch IC analysis | ⚠️ Needs v4 import update — superseded by ic_analysis_with_flow.py for with-flow work |
| `ic_analysis_yfinance.py` | yfinance-based IC + clustering (no-flow) | ✅ Confidence-weighted IC added; 42 tickers, k=5 |
| `ic_analysis_with_flow.py` | Real-server IC + clustering WITH inst_net_z | ✅ New — 19 tickers validated, ic_flow_cache/ added, effective-coverage trimming |
| `validate_clustering.py` | No-flow clustering statistical validation | ✅ Re-validated for k=5 |
| `validate_clustering_with_flow.py` | With-flow clustering statistical validation | ✅ New — adapted for 5-dim weighted IC |
| `validate_cluster_coverage.py` | Test if clusters generalize to new sectors | ✅ Run — found gaps, led to 42-ticker expansion |
| `recompute_v4_from_v3csv.py` | Control-variable experiment from existing v3 CSVs | ✅ Used for early diagnostic comparisons |
| `sweep_strategy_params.py` | Signal-Driven backtest parameter grid sweep | ✅ New — isolated min_confirm as the dominant parameter; led to backtest.py default change |
| `batch_sweep_all_tickers.py` | Batch parameter sweep across all 19 with-flow tickers | ⚠️ New — written, NOT yet run (sequencing: F2 sub-structure should be resolved first, see section 5) |
| `diagnose_coverage.py` | main-flow coverage diagnostic | ✅ Usable (server IP patched in-script) |
| `plot_inst_flow.py` | Interactive Plotly chart | ✅ Custom JS unified hover |
| `fetch_candidate_features.py` | Pull short interest / dark pool | ✅ Usable |

---

## 3. Key Findings This Session

### 3.1 Signal Generator: v3 → v4

**Features removed** (IC < 0.03, sign inconsistent across tickers):
- `liq_abs_z` — avg|IC|=0.013, measurement approach flawed (division instability)
- `clv` — avg|IC|=0.032, no microstructure theory backing, redundant with OFI
- `price_persistence` — avg|IC|=0.026, 3-bar window too narrow

**Features upgraded:**
- `impact_eff_z` — linear division → square-root market impact model (Almgren/Gatheral). Unit fix: `sigma × close × sqrt(part_rate)` to normalize across price levels.
- `rvol` — removed from fixed weights. IC sign inconsistent on **0/23 tickers** at 1d. Repurposed as **multiplicative amplifier**: `raw_score × (1 + clip((rvol-1)×0.10, -0.10, +0.10))`

**Weight rebalance:**

| | v3 (with flow) | v4 (with flow) |
|---|---|---|
| inst_net_z | 0.50 | 0.45 |
| ofi_z | 0.15 | 0.35 |
| rvol | 0.10 | amplifier only |
| vwap_dev | 0.10 | 0.15 |
| impact_eff_z | 0.05 | 0.05 |
| liq_abs_z | 0.10 | removed |

### 3.2 v3 Backtest Baseline (3 tickers, 1h)

**Event Study — Forward Returns (after cost 0.10%)**

| Ticker | Direction | 1bar | 6bar | 24bar | Significance |
|---|---|---|---|---|---|
| AAPL | Acc | -0.064% | +0.217% | **+0.722%** | ✅ 6/12/24bar significant |
| AAPL | Dist | -0.136% | -0.113% | **-0.554%** | ✅ 1/24bar significant |
| GOOGL | Acc | -0.021% | +0.100% | **+0.999%** | ✅ 12/24bar significant |
| GOOGL | Dist | -0.152% | -0.599% | **-1.504%** | ✅ all horizons significant |
| NVDA | Acc | -0.059% | +0.002% | -0.079% | ❌ none significant |
| NVDA | Dist | -0.086% | -0.234% | **-0.902%** | ✅ all horizons significant |

**Win Rate by Confidence Tier (forward=6bar)**

| Ticker | 低(0-25%) | 中(25-50%) | 高(50-75%) | 极高(75%+) |
|---|---|---|---|---|
| AAPL | 53.0% (263/496) | 50.2% (166/331) | 54.3% (57/105) | 45.5% (10/22) |
| GOOGL | 48.2% (279/579) | 46.8% (109/233) | 45.0% (9/20) | 60.0% (3/5) |
| NVDA | 48.6% (308/634) | 51.3% (101/197) | 83.3% (5/6) | 33.3% (1/3) |

*Note: 极高(75%+) sample sizes too small (5/22/3 trades) — statistically unreliable.*

**Signal-Driven Backtest**

| Ticker | Total Trades | Long Win Rate | Short Win Rate | Sharpe | Max DD |
|---|---|---|---|---|---|
| AAPL | 214 | 38.5% (40/104) | 30.0% (33/110) | -1.37 | -25.78% |
| GOOGL | 180 | 33.7% (30/89) | 28.6% (26/91) | -3.28 | -36.42% |
| NVDA | 190 | 35.2% (31/88) | 29.4% (30/102) | -1.77 | -24.21% |

**Walk-Forward (window=500, hold=6)**

| Ticker | Total Trades | Win Rate | Avg Return | Sharpe |
|---|---|---|---|---|
| AAPL | 119 | 44.5% (53/119) | -0.071% | -1.05 |
| GOOGL | 91 | 40.7% (37/91) | -0.139% | -1.68 |
| NVDA | 95 | 46.3% (44/95) | -0.099% | -1.09 |

**Key findings:**
- Distribution signals are consistently stronger than accumulation across all tickers
- GOOGL distribution is the strongest: 5/5 horizons significant, -1.504% at 24bar
- NVDA accumulation completely failed — no directional signal at any horizon
- Confidence tier inversion persists (high confidence → worse performance in most cases)
- Avg hold = 2.1-2.5 bar — signals reversed too quickly, stopped out before directional move materializes
- Root cause: no price confirmation layer — entry too early, needs volume/VWAP gate

### 3.3 IC Analysis: 23-Ticker yfinance Study (1d)

Ran IC analysis on 23 tickers using yfinance OHLCV data (no main-flow). Features: `ofi_z`, `rvol`, `vwap_dev`, `impact_eff_z`. Horizons: 1/3/6/12/24 bars.

**Cross-ticker avg|IC| (1d):**

| Feature | Mean | Std | Sign Consistent |
|---|---|---|---|
| ofi_z | 0.0398 | 0.0169 | 15/23 ✅ |
| vwap_dev | 0.0373 | 0.0166 | 14/23 ✅ |
| rvol | 0.0294 | 0.0139 | **0/23 ❌** |
| impact_eff_z | 0.0244 | 0.0145 | 5/23 ❌ |

`ofi_z` sign consistent on 15/23 tickers — most reliable directional feature. `rvol` 0/23 confirms it has no stable directional bias.

### 3.4 Ticker Classification via IC-Pattern Clustering

**Method:** Hierarchical / K-Means clustering on each ticker's 4-dimensional avg|IC| vector. Classified by IC pattern similarity, not subjective market features.

**Iteration history:** An initial run on 23 tickers found k=4 optimal (silhouette=0.322), but `validate_cluster_coverage.py` showed 6 of 12 new-sector test tickers (healthcare, REITs, small-cap) fell outside the training distribution's P90 distance (Mann-Whitney p=0.0012) — the 4 clusters did not generalize to underrepresented sectors. The training set was expanded to **42 tickers** (added healthcare, consumer staples, industrials, REITs, additional high-volatility growth names), and re-running `--find-k` showed **k=5 is now optimal** (silhouette=0.307, vs 0.283 for k=4 on the same 42-ticker set).

**Cluster results (k=5, 42 tickers, final):**

| Cluster | Tickers | Dominant IC | Characteristic |
|---|---|---|---|
| G0 | UNH, EQIX | ofi very high | Strongest OFI signal (small sample, see caveats) |
| G1 | TSLA, GS | impact high | High market impact sensitivity |
| G2 | GOOGL, AAPL, LLY, PFE, PLD, O, RBLX, SOFI, RIVN | rvol high | Volume-amplified signal |
| G3 | AMZN, WMT, JPM, AMD, JNJ, XOM, ARM, MRK, UBER, AMT, MSTR, IWM | vwap high | VWAP-driven |
| G4 | NVDA, MSFT, META, BRK-B, CAT, ABBV, KO, PG, NFLX, PLTR, BA, CRM, COIN, SMCI, DKNG, SPY, QQQ | all weak | Low IC across all features |

**Why SPY and QQQ land in G4:**

SPY and QQQ are ETFs that track the S&P 500 and Nasdaq-100 respectively. Their placement in G4 is structural, not a data quality issue:

- **Price is determined by basket composition, not single-stock microstructure.** OFI, VWAP deviation, and market impact features are designed to detect order flow imbalances of a single institution trading a single stock. For ETFs, price moves are driven by the weighted average of hundreds of constituents — no single participant's order flow dominates the price, so these features have very low predictive power.
- **Arbitrage mechanism suppresses microstructure signals.** ETF prices are kept close to NAV by authorized participants through continuous creation/redemption. This arbitrage dampens any deviation that VWAP or OFI signals would otherwise capture.
- **yfinance returns no market cap or institutional ownership for ETFs**, which also confirms they are structurally different from equities and should not be classified by the same rules.

**Implication:** SPY and QQQ should be treated as **benchmark references** for macro trend context (as planned for the chart overlay), not as signal generation targets.

**Pooled IC by cluster:**

| Cluster | ofi_z | rvol | vwap_dev | impact_eff_z |
|---|---|---|---|---|
| G0 | **0.0975** | 0.0357 | 0.0548 | 0.0305 |
| G1 | 0.0524 | 0.0302 | 0.0333 | **0.0625** |
| G2 | 0.0459 | **0.0588** | 0.0341 | 0.0190 |
| G3 | 0.0376 | 0.0342 | **0.0571** | 0.0248 |
| G4 | 0.0329 | 0.0225 | 0.0257 | 0.0207 |

### 3.5 Clustering Validation (3 Statistical Tests)

| Test | k=4 (23 tickers) | k=5 (42 tickers, final) |
|---|---|---|
| Kruskal-Wallis | 2/4 features significant | **4/4 features significant** (all p<0.05) |
| F-ratio | 4/4 features F>1 (rvol F=26.4, vwap F=19.9) | **4/4 features F>1**, higher magnitudes (ofi F=10.2, rvol F=19.5, vwap F=27.1, impact F=16.4) |
| Bootstrap stability | Mean co-occurrence = 0.794 | Mean co-occurrence = **0.768** (167/240 pairs >0.7) |

**The 42-ticker/k=5 result is statistically stronger than the original 23-ticker/k=4 run** — all 4 features now show significant between-group differences, not just 2. Expanding the training set didn't just add coverage, it improved the grouping's statistical validity.

**Known caveats (documented, to revisit with more data):**
- **G0 has only 2 tickers** (UNH, EQIX). Bootstrap shows its boundary with G3 is blurry — UNH–XOM and EQIX–XOM co-occurrence rates are >0.7 despite being assigned to different clusters. G0's weights should be treated as lower-confidence until more healthcare/REIT-pattern tickers are added.
- **RIVN is an isolated point** within G2 — its co-occurrence with every other G2 member (LLY, O, PLD, PFE, SOFI, GOOGL, RBLX) is below 0.3. It was assigned to G2 because it's the nearest cluster, not because bootstrap confirms it belongs there. More high-volatility growth/EV tickers are needed to determine its true grouping.

**Conclusion: Clustering is statistically valid and stronger than the initial pass. Weight design based on these 5 groups is justified, with the above two caveats flagged for future refinement.**

### 3.6 IC Methodology: Confidence-Weighted IC and Time-Granularity Sensitivity

IC is now computed as `weighted_IC = |raw_IC| × (1 - p_value)²` rather than raw `avg|IC|`. This down-weights correlations that are large but not statistically significant, so a feature that looks predictive only by chance doesn't get treated the same as a genuinely reliable one. Squared penalty (not linear) gives a cleaner separation between noise and real signal in the 0.05–0.5 p-value range. This is the standard method used in both `ic_analysis_yfinance.py` (no-flow) and `ic_analysis_with_flow.py` (with-flow).

**IC is time-granularity dependent — 1d and 1h must be analyzed and clustered separately, never interchanged.** The same feature on the same ticker can be a real, significant signal at one bar interval and statistically indistinguishable from noise at another (e.g. `ofi_z` on GOOGL: significant at 1d, noise at 1h). No-flow clustering (section 3.4–3.5) is trained on 1d data; with-flow clustering (section 3.8) is trained on 1h data. Weights derived at one granularity should not be applied at the other.

### 3.7 Main-Flow Coverage: Two Distinct Meanings

Main-flow only records trades ≥$100K notional, bucketed by size into super/large/mid/small, with `inst_net = (super_buy+large_buy) - (super_sell+large_sell)`. A bar with no qualifying large trade legitimately has `inst_net=0` — that's expected market behavior, not missing data.

Separately, several tickers' main-flow pipeline simply hadn't been backfilled until a recent date (e.g. GOOGL has almost no main-flow data before 2026-05-18). Counting that pre-backfill period in the coverage denominator understates true coverage. `detect_effective_flow_start()` in `ic_analysis_with_flow.py` finds each ticker's actual pipeline start date and trims to it before computing coverage/IC — this is now standard practice for any with-flow analysis. With trimming applied, most tickers show 94–99% effective coverage; NVDA is a genuine exception at 33%, reflecting real market sparsity rather than a pipeline gap.

**Known unresolved issue:** large-trades duplicate rate is still 32.5% for AAPL at the database level (not yet fixed by the data team). Effective-coverage trimming does not address this — it's a separate problem. All with-flow analysis in this report should be read as "best available data," not "clean data."

### 3.8 With-Flow Clustering (19 Tickers, Validated)

A 5-dimensional clustering (`ofi_z`, `rvol`, `vwap_dev`, `impact_eff_z`, `inst_net_z`) on 19 tickers, 1h data, k=3, is the project's strongest validated clustering result to date:

- **F-ratio: 5/5 features > 1** (`inst_net_z` highest at F=16.30)
- **Bootstrap stability: 0.846** mean co-occurrence, 0 unstable pairs, 0 ambiguous cross-cluster pairs
- **Kruskal-Wallis: 2/5 features significant**, with pairwise Mann-Whitney confirming each cluster's dominant feature is distinct from at least one other cluster

**Clusters:**

| Cluster | Tickers | Dominant pattern | Pooled weighted IC (top feature) |
|---|---|---|---|
| F0 | SPY, NVDA, MSFT | flow-dominant, ofi weak | inst_net_z = 0.1456 |
| F1 | TSLA, GOOGL, WMT | vwap-dominant | vwap_dev = 0.1984 |
| F2 | AAPL, UBER, QQQ, PLTR, META, GS, CRM, COIN, CAT, BA, AMD, JPM, XOM (13 tickers) | ofi-dominant | ofi_z = 0.0998 |

F2 is large and likely contains unresolved sub-structure (e.g. CAT's ofi_z=0.26 vs QQQ's ofi_z=0.01, both in F2) — bootstrap-stable as a group, but more tickers and a higher k would likely split it further.

### 3.9 Backtest Validation: With-Flow Cluster Weights vs Flat Weights

| Ticker | v3 (flat) Sharpe | v4 flat-flow Sharpe | v4 with-flow cluster Sharpe |
|---|---|---|---|
| AAPL (→F2) | -1.37 | -0.12 | -0.44 |
| GOOGL (→F1) | -3.28 | -3.28 | -3.35 |
| NVDA (→F0) | -1.77 | -3.30 | **-0.47** |

With-flow cluster weights substantially improve NVDA (correctly identified as flow-dominant, F0) and remain better than v3 for AAPL, though slightly behind v4's flat weights — likely because AAPL sits in the large, heterogeneous F2 cluster rather than having dedicated weights.

**GOOGL is not fixable by reweighting.** Its distribution signal is strong and significant across all horizons; accumulation is consistently weak/noise regardless of which weighting scheme is used. This is a feature-detection limitation, not a weight allocation problem — see section 7 for the implication.

### 3.10 Strategy Parameter Sensitivity: The Real Bottleneck Was min_confirm, Not Stop-Loss

Despite AAPL reaching "excellent" IC (0.11+) and NVDA reaching "general" IC, Signal-Driven Sharpe remained negative for both. A grid sweep (`sweep_strategy_params.py`) over `stop_loss` (1–8%), `min_confirm` (1–3), and `max_hold` (6–96 bars) — 90 combinations per ticker — isolated the cause.

**`min_confirm` is the dominant parameter by a wide margin; `stop_loss` barely matters:**

| Ticker | stop_loss sensitivity (Sharpe spread) | min_confirm sensitivity | max_hold sensitivity |
|---|---|---|---|
| AAPL | 0.077 | **1.961** | 0.779 |
| NVDA | 0.193 | **0.948** | 0.640 |
| GOOGL | 0.150 | 0.436 | 0.168 |

For AAPL and NVDA, raising `min_confirm` from 2 to 3 (requiring three consecutive same-direction bars before entry, instead of two) flips Signal-Driven Sharpe from negative to positive:

| Ticker | Sharpe @ min_confirm=2 (prior default) | Sharpe @ min_confirm=3 (new default) |
|---|---|---|
| AAPL | -0.44 | **+0.97** |
| NVDA | -0.47 | **+0.11** |
| GOOGL | -3.35 | still negative (best of 90 combos: -2.51) |

26/90 combinations were profitable for AAPL, 17/90 for NVDA, **0/90 for GOOGL** — confirming GOOGL's problem is not an execution-parameter issue at all, consistent with section 3.9's conclusion. `max_hold=6` was consistently the worst choice for both AAPL and NVDA; performance plateaus at `max_hold≥24` with no further gain from 48 or 96, so the existing default (`forward×4` = 24 bars at 1h) was already a reasonable choice and didn't need changing.

**Action taken:** `backtest.py`'s `min_confirm` default changed from 2 to 3 (both the CLI flag default and the `signal_driven_backtest()` function default), with the rationale documented inline in the code.

### 3.11 Important Caveat: AAPL's Positive Sharpe Doesn't Hold Up Under Walk-Forward

A full re-read of AAPL's backtest report (all 5 methods, not just Signal-Driven) surfaced a contradiction that needs to be flagged before treating AAPL as "working":

| Method | What it tests | AAPL result |
|---|---|---|
| Signal-Driven (min_confirm=3) | A specific trading rule set (confirmation filter + stop-loss + reversal exit) | Sharpe **+0.97**, cum. return +13.51% |
| Walk-Forward | Simple rolling re-entry on the latest signal, no confirmation filter or stop-loss | Sharpe **-0.96**, cum. return -8.79% |

These two methods disagree because they test fundamentally different things — Signal-Driven benefits from `min_confirm`, Walk-Forward doesn't use that parameter at all. **This means AAPL's positive result is conditional on the specific Signal-Driven rule set, not a general improvement in signal usability.** A simpler strategy (open on signal, hold for a fixed period, no confirmation filtering) would still lose money on AAPL with the current signal.

This doesn't invalidate the min_confirm finding — the finding itself (that confirmation window matters more than stop-loss) is solid. But it means the project does not yet have a single ticker where signal quality is good enough to produce a positive result under *every* independent validation method. The honest summary: **min_confirm=3 made one specific strategy profitable on AAPL; it has not yet been shown that AAPL's underlying signal is robust across different ways of trading it.**

### 3.12 F2 Cluster Sub-Structure: Confirmed, Not Just Suspected

Running k-means on F2's 13 tickers in isolation (rather than as part of the full 19-ticker space) confirms the sub-structure that was flagged as a risk in section 3.8. k=3 is silhouette-optimal within F2 (0.299, vs 0.268 for k=2), and produces three distinguishable sub-groups:

| Sub-group | Tickers | Pattern |
|---|---|---|
| F2-A | UBER, PLTR, META, GS, JPM | vwap_dev-dominant (0.07–0.16) |
| F2-B | CAT, BA, XOM | ofi_z-dominant, very strong (0.12–0.26) |
| F2-C | AAPL, QQQ, CRM, COIN, AMD | weak across the board; closer to QQQ's "near-zero everywhere" pattern than to F2-B's strong ofi signal |

**This directly explains a previously unresolved puzzle: why AAPL performed worse under F2's pooled weights (ofi=0.44) than under the flat global weights (ofi=0.35).** AAPL's own `ofi_z` (0.097) is much weaker than CAT's (0.26) or XOM's (0.156), which are pulling F2's pooled ofi weight up. AAPL sits in F2-C, a sub-group where no feature is particularly strong — averaging it in with F2-B's powerful ofi signal overweights AAPL's ofi component beyond what its own data supports.

**This is not yet acted on** — re-deriving weights at the sub-group level (F2-A/F2-B/F2-C) and re-testing AAPL under F2-C-specific weights is the logical next step, but requires re-running the validation pipeline (Kruskal-Wallis/F-ratio/bootstrap) on each sub-group, which needs more tickers per sub-group than are currently available (F2-C only has 5).

---

## 4. Weight Design (No-Flow and With-Flow)

### 4.1 Cluster Weights for the 42 Trained Tickers (No-Flow)

Based on pooled IC, weights derived algorithmically by normalizing each cluster's IC vector (excluding rvol, which acts as an amplifier — see section 3.2 rvol discussion):

| Cluster | ofi | vwap | impact | rvol_amp_scale | overall_scale |
|---|---|---|---|---|---|
| G0 | 0.53 | 0.30 | 0.17 | 0.61 | 1.00 |
| G1 | 0.35 | 0.22 | 0.42 | 0.51 | 0.82 |
| G2 | 0.46 | 0.34 | 0.19 | 1.00 | 0.72 |
| G3 | 0.31 | 0.48 | 0.21 | 0.58 | 0.70 |
| G4 | 0.41 | 0.32 | 0.26 | 0.38 | 0.47 |

`rvol_amp_scale` is each cluster's rvol IC relative to the strongest cluster (G2). `overall_scale` is each cluster's total IC strength (sum of all 4 features) relative to the strongest cluster (G0) — G4's weak overall IC means its signal magnitude is dialed down to 47% rather than treated with full confidence.

These weights are now implemented in `signal_generator_v4.py` (`CLUSTER_WEIGHTS` dict) and looked up automatically via `TICKER_CLUSTER_MAP` when `compute_signal(df, ticker=...)` is called with one of the 42 trained tickers.

### 4.2 Handling Tickers Outside the Trained Set: Soft Cluster Assignment

**The problem:** the 42-ticker training set won't cover every ticker the system eventually needs to score. A new ticker could sit clearly inside one cluster's IC pattern, or — more commonly — somewhere between two clusters. Forcing a hard assignment ("nearest cluster wins") discards that boundary information.

**Design options considered:**

| Option | Description | Why rejected / accepted |
|---|---|---|
| A. Online-updated centroids | New ticker's IC vector nudges the cluster centroid it's assigned to, so centroids drift over time | **Rejected** — introduces path dependency (the order tickers are added changes the result) and reintroduces the v2 Lasso risk: letting historical data continuously reshape model parameters, which is unstable with small ticker counts (23–40 range) |
| B. Full re-clustering on every new ticker | Re-run k-means on all tickers (old + new) each time one is added | **Rejected** — cluster labels (G0/G1/G2/G3/G4) are arbitrary outputs of k-means and can swap identity between runs, breaking any weight table that references a cluster by name. Also computationally wasteful for one new ticker. |
| C. Fixed centroids + softmax-weighted blend | Centroids stay fixed (from the validated 42-ticker run). A new ticker's own IC vector is compared to all 5 centroids by distance; weights from each cluster are blended proportionally to closeness (softmax) | **Chosen** |

**Why option C fits the project's accuracy target:** the team is not aiming for 100% classification precision — **~70% is the working target**. At that precision level, a deterministic soft blend is the right amount of sophistication: it handles boundary tickers gracefully (e.g. a ticker 60% similar to G2 and 30% similar to G3 gets a 60/30 weight blend, not a coin-flip hard assignment), it's reproducible (same ticker → same result, always), and it avoids the instability and engineering overhead of online learning or repeated re-clustering — which would be over-engineering relative to the precision actually needed.

**How it works (`get_soft_cluster_weights()` in `signal_generator_v4.py`):**

```
1. New ticker's raw avg|IC| vector [ofi_z, rvol, vwap_dev, impact_eff_z]
   is computed from its own OHLCV history (same method as the 42-ticker study)
2. Standardize using the TRAINING SET's mean/std (not the new ticker's own —
   this keeps the new ticker's position comparable to the fixed centroids)
3. Compute Euclidean distance to each of the 5 fixed centroids
4. Apply softmax over negative distance → membership weights summing to 1
   (closer centroid = higher membership; SOFTMAX_TEMPERATURE controls
   how "hard" vs "soft" the blend is)
5. Final weight table = membership-weighted average of the 5 clusters'
   {ofi, vwap, impact, rvol_amp_scale, overall_scale} values
```

This is implemented and wired into `compute_signal()`: when a ticker is not found in `TICKER_CLUSTER_MAP`, the function automatically falls back to soft assignment instead of a flat global default — meaning **every new ticker gets a weight blend informed by IC pattern similarity, not a one-size-fits-all fallback.**

**Centroids (standardized space, from 42-ticker training set):**

| Cluster | ofi_z | rvol | vwap_dev | impact_eff_z |
|---|---|---|---|---|
| G0 | 2.851 | 0.068 | 1.038 | 0.562 |
| G1 | 0.577 | -0.263 | -0.308 | 3.310 |
| G2 | 0.247 | 1.430 | -0.257 | -0.427 |
| G3 | -0.175 | -0.024 | 1.185 | 0.072 |
| G4 | -0.411 | -0.717 | -0.786 | -0.280 |

**Smoke test:** a synthetic ticker with a vwap-dominant IC pattern `[ofi=0.030, rvol=0.030, vwap=0.065, impact=0.025]` was assigned membership `{G0: 4%, G1: 3%, G2: 9%, G3: 73%, G4: 11%}` — correctly identified as primarily G3-like (the vwap-dominant cluster) while still reflecting minor influence from the other clusters.

**Maintenance note:** `CLUSTER_CENTROIDS` and `CLUSTER_CENTROIDS_MEAN_STD` must be regenerated (via `ic_analysis_yfinance.py`) if the training ticker set changes materially — e.g. if G0 or the RIVN-in-G2 issue (section 3.5 caveats) is resolved with more data, or after main-flow data is incorporated and IC patterns shift.

### 4.3 Cluster Coverage Validation — Completed

`validate_cluster_coverage.py` was run on 12 new tickers from sectors underrepresented in the original 23-ticker training set (healthcare, staples, industrials, small-cap, REITs). Results:

- **6/12 new tickers** (RIVN, PLD, O, ARM, LLY, UNH) fell outside the 23-ticker training distribution's P90 distance — the original 4 clusters did not generalize well (Mann-Whitney p=0.0012)
- Re-clustering all 35 tickers (23+12) together still found k=4 silhouette-optimal, meaning the new tickers didn't form an obvious 5th cluster on their own — they were scattered between existing clusters rather than clumped together
- **Action taken:** expanded the training set further to 42 tickers (added more tickers per underrepresented sector — e.g. ABBV/JNJ/MRK for healthcare, AMT/EQIX for REITs, RBLX/DKNG for high-volatility growth) to give each potential new pattern enough samples to either confirm or rule out a 5th cluster
- **Result:** with 42 tickers, k=5 became silhouette-optimal (0.307 vs 0.283 for k=4) and validated significantly better than the prior k=4 run (4/4 vs 2/4 features significant in Kruskal-Wallis) — see sections 3.4–3.5 for the final result

### 4.4 With-Flow Cluster Weights (19 Tickers, Validated)

Weights derived from the with-flow clustering in section 3.8.

**Weights (flow share capped at 0.45, same ceiling as the global default, even where raw pooled IC implied higher — F0's raw flow share was 0.60):**

| Cluster | flow | ofi | vwap | impact | rvol_amp_scale |
|---|---|---|---|---|---|
| F0 | 0.45 | 0.14 | 0.28 | 0.13 | 1.00 |
| F1 | 0.09 | 0.20 | 0.56 | 0.15 | 0.94 |
| F2 | 0.14 | 0.44 | 0.31 | 0.11 | 0.50 |

This is wired into `signal_generator_v4.py`'s `compute_signal()`: tickers in `TICKER_CLUSTER_MAP_WITH_FLOW` use their cluster's weights; tickers with flow but not yet in this map fall back to the flat global `WEIGHTS_WITH_FLOW` (no soft-assignment system has been built for the 5-dimensional with-flow space yet — building one before the 19-ticker base clustering is more mature, especially before F2's possible sub-structure is investigated, would be premature, following the same "don't over-engineer relative to current confidence" principle applied elsewhere in this project).

**Remaining caveat:** these weights are trained on data with the effective-coverage trimming applied (section 3.7) but the underlying large-trades duplicate rate (32.5% for AAPL) is still unresolved at the database level. This is the best available data, not clean data — if/when the duplicate rate is fixed at the source, this clustering should be re-run to confirm the result holds.

**Next step for expanding this:** re-run `ic_analysis_with_flow.py` with more tickers, particularly to test whether the 13-ticker F2 cluster splits into sub-clusters at a higher k once there's enough data to support it.

---

## 5. Immediate Next Steps (No Server Required)

**Priority order reflects current diagnosis: IC was "excellent" for AAPL (0.11+) and "general" for NVDA, but Signal-Driven Sharpe was still negative for both — this gap pointed to the trading-rule layer as the likely bottleneck, not the signal itself.**

1. ~~**Signal-Driven backtest parameter sensitivity analysis**~~ ✅ Done — see section 3.10. Root cause was `min_confirm` (signal confirmation window), not `stop_loss`. Raising it from 2→3 flipped AAPL Sharpe to +0.97 and NVDA to +0.11; GOOGL stayed negative across all 90 combinations tested, confirming its issue is in the signal itself, not execution rules. `backtest.py`'s default updated accordingly.
2. ~~**Chart upgrade**~~ ✅ Done — QQQ/SPY overlay (on a secondary y-axis, % change from first bar) and Inst. Acc/Dist markers (strong-only, to avoid visual clutter at 1h's signal density) added to `plot_inst_flow.py`. Benchmark data fetched via new lightweight `fetch_benchmark.py` (OHLCV-only, skips the full feature/HMM/clustering pipeline).
3. **Lock in GOOGL's limitation** — stop further reweighting/parameter-tuning attempts; document it as accumulation-undetectable, usable for distribution/short signals only.
4. ~~**Investigate F2 with-flow sub-structure**~~ ✅ Confirmed, not just suspected (section 3.12) — k-means within F2 alone finds 3 sub-groups (k=3 silhouette-optimal at 0.299): F2-A (vwap-dominant: UBER/PLTR/META/GS/JPM), F2-B (ofi-dominant: CAT/BA/XOM), F2-C (weak across the board: AAPL/QQQ/CRM/COIN/AMD). This explains why AAPL underperformed under F2's pooled weights — its own ofi_z is much weaker than F2-B's, so averaging inflates AAPL's ofi weight beyond what its data supports. **Next: re-derive weights at the F2-A/B/C level and re-test AAPL under F2-C-specific weights** — not yet done, blocked on needing more tickers per sub-group (F2-C only has 5) before the usual validation tests (Kruskal-Wallis/F-ratio/bootstrap) would be meaningful.
5. **Auto-generate `weights_by_cluster.json`** for both no-flow and with-flow systems.
6. **Resolve the Walk-Forward vs Signal-Driven contradiction for AAPL** (section 3.11) before treating any ticker as validated — run Walk-Forward and Signal-Driven side by side across more tickers once F2 sub-grouping is fixed, to see whether this disagreement is AAPL-specific or a general pattern across the with-flow signal set.

**Deferred until item 4's sub-grouping is complete:**
- Batch parameter sweep across all 19 with-flow tickers (`batch_sweep_all_tickers.py`) — written and ready, but intentionally not run yet. Running it now, while 13 tickers still use F2's un-split pooled weights, would produce "best min_confirm per ticker" results built on potentially miscalibrated signals (see item 4).

**Deprioritized for now:**
- No-flow cluster weights (G0–G4) have never been backtested against v3 on equal footing — the closest comparison (forcing no-flow on tickers that should have flow) showed worse results than v3. This needs its own validation before being trusted as a fallback, but is not urgent while with-flow coverage (19 tickers) is the focus.
- G0/RIVN no-flow sample-size caveats — same reasoning, not urgent until no-flow itself is re-validated.

---

## 6. Waitlist (Requires Server / DB Fix)

### Still blocked on teammate's DB-level dedup fix:

| Priority | Task |
|---|---|
| 🔴 High | Re-run with-flow IC analysis once large-trades duplicate rate (still 32.5% for AAPL) is fixed at the DB level — current with-flow clustering is the best available but explicitly not clean data |
| 🟡 Medium | Re-run 13F validation with clean data — **on hold, see note below** |
| 🟡 Medium | OOS second quarter (~Aug 2026, Q2 13F data) |

**13F validation finding (2026-06-30):** Ran `validate_13f.py` on AAPL/GOOGL/NVDA using with-flow cluster signals (1h). Only **3 comparable quarters** were available, because main-flow data only goes back to ~2025-07 — klines can be pulled from 2024-06-24 but main-flow can't, so signal generation with flow is bottlenecked by main-flow's shorter history. With n=3, no result can reach statistical significance regardless of match rate (NVDA hit 100% match but p=0.123 — the theoretical minimum p-value at n=3 is already 0.125). Additionally, AAPL and NVDA's 13F holdings data showed suspicious single-quarter swings (AAPL total shares +144% then -52% across consecutive quarters) that look more like a data/CUSIP-matching issue than real institutional activity — this needs to be checked before trusting any 13F-based conclusion for these tickers. **Decision: 13F validation is paused, not abandoned** — it will become viable once main-flow accumulates more history (a few more quarters of real-time data collection), at which point it should be re-run with both more quarters and the holdings-data anomaly resolved.

### Newly unblocked / in progress (server confirmed working again as of 2026-06-30):

| Priority | Task |
|---|---|
| 🔴 High | Expand with-flow clustering beyond 19 tickers — especially to test whether F2 splits at higher k |
| 🟡 Medium | Validate no-flow cluster weights against v3 on equal footing (currently unvalidated — see section 5 deprioritized note) |
| 🟡 Medium | batch_feature_ic.py → update to v4 imports (lower priority now that ic_analysis_with_flow.py covers the with-flow use case) |
| 🟡 Medium | Price confirmation layer (signal + VWAP/volume gate before entry) — sequence after strategy parameter diagnosis (section 5, item 1), not before |
| 🟡 Medium | Full strategy backtest (cluster weights + price confirmation) |
| 🟢 Low | Dark pool validation framework (weekly hmm_strength vs dark_pool_pct) |
| 🟢 Low | ClickHouse signal_scores table + API endpoint |
| 🟢 Low | Frontend chart integration |

---

## 7. Known Issues & Constraints

### Data quality (partially mitigated, not resolved)
- main-flow duplicate rate: still **32.5%** for AAPL at the source (DB-level fix not done by teammate as of 2026-06-30) — only caught by in-script dedup in `load_large_trades()`, which operates on a different table than the main-flow hourly aggregates
- **Raw coverage numbers were misleading** for most tickers — fixed via effective-start trimming (section 3.7). 8/9 re-tested tickers jumped from 10-30% raw to 94-99% effective coverage once pipeline-backfill gaps were excluded from the denominator
- NVDA remains a genuine low-coverage case (33% even after trimming) — likely real market sparsity, not a pipeline gap
- 2025-07 to 2025-09: large-trades API returns 500 errors (unchanged from earlier report)

### Model limitations
- **GOOGL's accumulation signal appears structurally undetectable** with current features — distribution is strong and significant, accumulation is consistently weak/noise across all weighting schemes (v3, v4 flat, v4 with-flow cluster) AND all 90 strategy-parameter combinations tested (section 3.10). Two independent diagnostic methods (IC/Event-Study and parameter sweep) now agree: this is a feature-detection limitation, not a weighting or execution-rule problem.
- F2 with-flow cluster (13 tickers) likely has unresolved sub-structure — bootstrap-stable as a whole, but contains tickers with very different feature magnitudes (e.g. CAT ofi_z=0.26 vs QQQ ofi_z=0.01)
- G1 no-flow cluster has only 2 tickers (TSLA, GS) — pooled IC less reliable
- 13F OOS validation limited to 1 quarter (insufficient statistical power); separately, a 2026-06-30 attempt to run 13F validation found only 3 comparable quarters are available regardless of OOS settings, because main-flow's usable history (~2025-07 onward) is shorter than klines' — not enough for statistical significance at any match rate. 13F validation is paused pending more main-flow history.

### Methodology constraints (resolved this session, noted for history)
- ~~IC analysis done on 1d data (yfinance) — 1h IC weaker due to noise~~ → now understood as a **time-granularity dependency**, not just "1h is noisier" — some features are genuinely non-significant at 1h for specific tickers (see section 3.6)
- ~~Cluster weights derived from OHLCV only (no main-flow) — flow dimension missing~~ → resolved via `ic_analysis_with_flow.py`, validated 19-ticker with-flow clustering now wired in (see section 3.9)
- rvol as amplifier: ±10% max effect, now tested in live backtest as part of cluster weights (rvol_amp_scale varies 0.50-1.00 across with-flow clusters)

---

## 8. Design Decisions Log

| Decision | Rationale |
|---|---|
| Remove liq_abs_z, clv, price_persistence | IC < 0.03, sign inconsistent, no theory backing |
| rvol as amplifier not directional feature | 0/23 sign consistent on 1d — no stable directional bias |
| impact_eff_z: sqrt model + unit fix | Almgren/Gatheral empirical evidence; price-unit normalization prevents cross-stock bias |
| IC-pattern clustering (not market-feature rules) | Grouping based on what the data shows, not assumptions |
| k=5 clusters (42 tickers) | Initial k=4/23-ticker grouping failed coverage validation (6/12 new-sector tickers outside P90 distance); expanded training set to 42 tickers, k=5 became silhouette-optimal (0.307) and statistically stronger (4/4 vs 2/4 Kruskal-Wallis significant) |
| Flow weight design (19-ticker clustering, capped at 0.45) | Per-ticker sensitivity varies; capping prevents overcorrection from clusters whose high flow IC might still partly reflect residual data quality issues |
| Soft cluster assignment (fixed centroids + softmax) for new tickers | Online-updated centroids = path dependency + v2 Lasso-style instability risk. Full re-clustering = unstable cluster labels + computational waste. Target accuracy is ~70%, not 100% — deterministic soft blending is the appropriately-scoped solution, not over-engineering |
| No trained weights (avoid v2 Lasso repeat) | Small samples + dirty data = overfitting noise |
| HMM quality threshold (t-test p<0.05) | Prevents manufacturing fake accumulation states |
| dark_pool_pct as validation only | 2-week disclosure lag makes real-time use impossible |
| Confidence-weighted IC: \|raw_IC\| × (1-p)² | Raw avg\|IC\| can't distinguish real signal from non-significant noise (GOOGL/AAPL's ofi_z had near-identical raw IC at 1h despite one being p=0.0000 and the other p=0.73); squared penalty chosen over linear after direct comparison showed linear was too forgiving in the 0.05-0.5 p-range |
| Effective-coverage trimming for main-flow | Raw coverage conflated "pipeline never backfilled this ticker" with "genuinely sparse large-trade activity" — these require opposite interpretations. Trimming to the pipeline's actual stable start date corrected 8/9 tickers from 10-30% to 94-99% coverage |
| With-flow clustering wired into compute_signal() | 19-ticker validated clustering (Bootstrap stability 0.846, best of any run) replaced an earlier 3-ticker unvalidated draft; backtest confirmed real improvement (NVDA Sharpe -3.30→-0.47) before wiring in, not just statistical validation alone |
| Did not build with-flow soft assignment yet | 5-dim with-flow space + F2 cluster's unresolved sub-structure make this premature; same over-engineering concern as elsewhere in the project — wait until the base clustering is more mature |
| GOOGL flagged as requiring non-reweighting fix | Three different weighting schemes (v3, v4 flat, v4 with-flow cluster) all failed to fix GOOGL's Sharpe — the asymmetry between strong distribution signal and weak accumulation signal is a feature-detection problem, not a weighting problem |
| backtest.py min_confirm default: 2 → 3 | Grid sweep (90 combos) showed min_confirm has the largest Sharpe sensitivity of any tested parameter (spread 1.96 for AAPL, vs 0.08 for stop_loss) — raising it to 3 flipped AAPL/NVDA from negative to positive Signal-Driven Sharpe. max_hold's existing default (forward×4=24 at 1h) was already near-optimal and left unchanged. |
