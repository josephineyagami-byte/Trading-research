# Inventory Diagnostics: First Handoff Fix

Updated: 2026-10-20. Based on upstream commit `722865d` and its bundled historical
outputs, not a fresh two-year data pull or a production deployment.

## What Was Wrong

`signal_generator_v5_3.py` computes:

```text
direction = +1 for long, -1 for short, 0 otherwise
delta_inventory = direction * heuristic_participation / 100 * volume
cumulative_inventory = cumulative_sum(delta_inventory)
```

This is a zero-based **model-implied position change**, measured in shares.
It is not observed institutional holdings, measured dollar fund flow, or a
reconstruction of specific accounts. In v5.3 its direction even depends on a
trade recommendation, not verified institution-side transactions. A short
recommendation cannot establish that institutions sold that many shares.

A negative cumulative change can be legitimate. Institutions do not have to
be net buyers throughout every window, and a rising price does not prove
institutional accumulation. Taking an absolute value, clipping at zero, or
adding a balance selected to keep the graph positive would conceal the problem.

An actual inventory model needs a justified opening balance, consistent
participant coverage and share units, corporate-action handling, calibrated
transaction estimates, and out-of-sample validation. A 13F quarter-end snapshot
is delayed and covers a different population from aggressor-classified trades;
do not inject a future snapshot into past signals or assume the scopes match.

## Changes

- Keep v5.3's long/short scores, gates, and legacy columns unchanged.
- Export `model_position_change_shares` and
  `cumulative_model_position_change_shares` with explicit semantics.
- Add **20-bar model flow pressure** as a separate indicator:
  `100 * sum(model_position_change_shares, 20) / sum(volume, 20)`.
  Both numerator and denominator are shares. A positive number means positive
  heuristic direction over that window, not verified institutional buying.
  It is not a probability, position percentage, or an independent new source.
- Require a complete 20-bar window and positive total volume for pressure.
  Warm-up and missing changes remain unknown. Cumulative values stop after an
  interior gap instead of silently bridging it; rolling pressure may recover
  once its local window is complete again.
- Optional opening balances require an explicit source and timestamp before
  the first bar. `inventory_scenario_shares` is always a **scenario**, not
  observed holdings. Negative scenarios are retained and flagged as invalid;
  no amount is clipped or inferred just to maintain positivity.
- Reject unordered timestamps, duplicate bars, mixed tickers, negative volume,
  infinities, and share changes exceeding bar volume. These checks cannot
  detect missing whole sessions, all unit errors, or undisclosed splits.
- Relabel the chart's old inventory panel and add the pressure panel. The
  tooltip and zoom auto-fit include the new panel.
- Make the API base URL honor `US_STOCK_API_BASE_URL` (the old v4 loader ignored
  the v5.3 configuration and continued using a retired server address).
- Use the `America/New_York` timezone, including winter/summer DST, for the
  existing 9:35-16:00 regular-session filter. Apply the same filter to flow
  and intraday OHLCV. Daily OHLCV session scope still depends on the provider's
  contract. This is not a full exchange calendar or overnight model.
- Remove exact page-boundary repeats before summing flow. Conflicting revisions
  fail explicitly, and duplicate aggregate merge keys cannot multiply OHLCV rows.

The raw flow source's currency/unit contract still needs confirmation. Raw
`inst_net` is never added to a share inventory or multiplied into it here.

## Reproduction

Run from the repository root with Python 3.10 or newer:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v

.venv/bin/python 'Backtest/backtest scripts & outputs/inventory_diagnostics.py' \
  'Backtest/backtest scripts & outputs/outputs/MSFT_1d_20260602_133016_signals.csv' \
  --output-dir local-artifacts/inventory-audit

.venv/bin/python 'Backtest/backtest scripts & outputs/plot_inst_flow.py' \
  --file local-artifacts/inventory-audit/MSFT_1d_20260602_133016_signals_audited.csv \
  --ticker MSFT --interval 1d
```

The audit CLI does not contact a server, refit signals, or alter source files.
Use `--summary-only` to skip enriched CSV exports. JSON uses `null` for unknown
holdings and values; the website must not convert these to zero or a green status.
The v5.3 generator automatically includes the new diagnostics in fresh CSVs.
Refresh raw caches when testing the loader corrections; cached data may retain
old duplicates/session filtering. Other historical generator versions remain
research snapshots, not updated production paths.

## Historical Evidence

The checked-in [audit JSON](audits/20261020/inventory_audit.json) records six
existing CSVs for five tickers. All have 353 rows, spanning 2025-01-02 through
2026-06-01 (about 17 months, **not two years**). There are no duplicate
timestamps in those six files. Model-change coverage is 315/353 bars after
38 warm-up bars; this is **not** observed main-flow coverage.

| Saved output | Ending signed model change, shares |
| --- | ---: |
| AAPL, `20260602_131849` | +217,411,135 |
| NVDA, `20260602_151740` | +674,683,328 |
| MSFT, `20260602_133016` | -65,854,447 |
| MSFT, `20260602_151813` | +103,764,061 |
| GOOGL, `20260602_151837` | +156,636,428 |
| TSLA, `20260602_151630` | +142,298,628 |

Re-summing the saved changes matches all six saved cumulative series within
numerical tolerance. Thus the reproduced negative MSFT endpoint is not a
simple cumulative-sum sign error. Different saved MSFT runs also change sign;
they must not be pooled or presented as the same calibrated holdings series.
This does not reproduce or validate the user's current two-year run. The user
does not have that CSV, so further work should use a clearly identified fresh
run rather than requiring a lost file or claiming an exact reproduction.

Regression coverage includes negative relative changes, explicit anchors,
missing values, chronology, duplicates, units, DST, page overlap, merge grain,
JSON output, v5.3 score preservation/export, and chart traces. Synthetic test
fixtures are software checks, not financial evidence.

## Before Website Integration

1. If the original CSV is unavailable, acquire a fresh dated two-year dataset
   with explicit ticker, model version, interval, raw-flow unit contract,
   adjustment settings and source coverage. Inspect omitted sessions and
   splits; do not call a new run an exact reproduction of the original.
2. Separate trade recommendations from latent flow/inventory inference. Any
   new estimator must be calibrated against independent, scope-matched data.
3. Replace full-sample HMM and run-wide quality fitting with causal/walk-forward
   evaluation before claiming historical predictive accuracy. Today's audit
   tests accounting and semantics, not investment performance.
4. In the website, show the relative model-change and pressure metrics as
   experimental indicators with dates, units and data quality. Keep absolute
   holdings unavailable until the calibration and anchor requirements are met.
   Do not label the curve as verified main-fund capital or live WebSocket flow.

This handoff does not change the running US_stock website or add trading actions.

## Fresh Two-Year Data Access

Read-only checks on 2026-10-20 found that the configured server's `/healthz`
responded HTTP 200, while `/api/klines` (MSFT, 2024-10-20 to 2026-10-19) and
`/api/main-flow` (one recent session) both responded HTTP 401 with
`not authenticated`. No authenticated two-year download or refit was completed.
This is an application login issue, not evidence that all data is absent, nor
a determination about a market-data vendor's WebSocket subscription.

The research loader now supports the website's existing **`auth` session
cookie**, supplied explicitly as `US_STOCK_AUTH_COOKIE` in the local process.
It does not read browser cookies, create accounts, retrieve passwords, sign JWTs,
or disable server authentication. Do not send credentials in chat, URLs, CSVs,
notebooks or commits. Session values expire and must be renewed through normal
authorized login; the cookie is not a market-data provider API key.

Credentialed requests require an HTTPS API URL or a loopback tunnel such as
`http://127.0.0.1:8000`. They are refused for public plaintext HTTP. Redirects
are not followed, and errors do not print cookie values or response bodies.
HTTP 401/403/429 abort a fresh run instead of being downgraded to "no flow";
benchmark lookup also propagates these errors. A cache-only run is still only
historical cached data and must not be represented as newly downloaded data.

Explicit `--from-date` is no longer silently clamped to 2025-07-01. That date
remains the legacy default when no start is supplied, not a verified permanent
limit on the server's current coverage. Empty responses for older dates remain
unknown coverage, not observed zero flows. Verify returned dates before making
any two-year claim.

After authorized access is configured locally, a fresh run can use:

```bash
.venv/bin/python 'Backtest/backtest scripts & outputs/signal_generator_v5_3.py' \
  --ticker MSFT --interval 1d \
  --from-date 2024-10-20 --to-date 2026-10-19 \
  --no-cache --refresh-data
```

The date range ends on a completed session; reruns should use explicitly dated
windows. This command is not proof that two years of raw flow actually exists.
