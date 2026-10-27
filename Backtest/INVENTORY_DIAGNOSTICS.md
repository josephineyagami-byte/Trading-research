# Inventory Diagnostics and Independent Flow Research

Updated: 2026-10-20. The first audit below uses upstream commit `722865d` and its
bundled outputs. Later sections separately document the fresh data pull,
independent estimator, chronological replay and website integration.

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

### Normal Account Login

The v5.3 CLI also accepts an existing private account file instead of asking
the user to extract a browser cookie. The JSON may be a single object with
`username` and `password`, or a list of accounts with `--api-username` selecting
exactly one. The file must be private (`0600`). It is never modified, no password
is passed on the command line, and the returned session is held only in process
memory. Failed logins are not retried across accounts.

```bash
.venv/bin/python 'Backtest/backtest scripts & outputs/signal_generator_v5_3.py' \
  --api-base-url http://127.0.0.1:18080 \
  --credentials-file /path/to/existing/private-accounts.json \
  --api-username YOUR_EXISTING_USERNAME \
  --ticker MSFT --interval 1d \
  --from-date 2024-10-20 --to-date 2026-10-19 \
  --no-cache --refresh-data
```

Before using the loopback example, the server owner can establish an encrypted
SSH tunnel in a separate terminal, entering the SSH password only there:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:18080:127.0.0.1:8000 root@74.208.124.247
```

Keep that terminal open during collection. No remote service restart, account
creation, firewall change, JWT signing or authentication bypass is needed.
Use the server's ordinary authorized SSH account if root is unavailable. The
existing default server address in this repository currently uses public HTTP;
do not pass an account file to that address directly.

On 2026-10-20 the previous local SSH control socket was absent, noninteractive
SSH had no usable identity, and the server's HTTPS endpoint was unavailable.
An existing project account file was found locally, but it has **not** been
validated against the server: without the secure connection, no login attempt
using those credentials or full two-year collection was performed. The user
was asked to establish the tunnel. Do not describe local/mocked tests as a
successful production connection.

### Live Connection and Date-Boundary Verification

Later on 2026-10-20 the user established the loopback tunnel. The health endpoint
returned HTTP 200, normal existing-account login succeeded, and protected K-line
and flow requests returned data. No credentials were logged or committed.

A live boundary check found an additional bug: the date-only `to` value was
interpreted as midnight at the beginning of that day. A request ending
`2026-10-19` returned 499 MSFT daily bars ending on October 16; requesting through
`2026-10-20` included the October 19 daily bar. The research client's date-only
`--to-date` is now inclusive, with the transport bound advanced to the following
midnight. This correction returned 500 daily bars for the requested two-year
window. A full UTC-day flow request for October 19 returned 190 five-minute rows
before the model's regular-session filter; an empty same-date request was not
evidence that the day lacked flow data.

The first long run returned 18 monthly flow pages before being interrupted.
A subsequent monthly request failed; do not interpret these attempts as a
completed two-year model result. The client now supports smaller requests with
`--flow-chunk-days 7` and opt-in `--flow-checkpoint-dir` storage. Successful pages
are written atomically with source, exact parameters, thresholds and fetch time;
cache hits are explicitly labeled `checkpoint`, not new API reads. Failed or
unrecognized responses cannot create zero-filled checkpoints. Error messages
identify HTTP status or exception type without printing URLs, bodies or secrets.

To resume an interrupted download, retain the same checkpoint directory and
parameters. To request entirely new snapshots, use a new directory. The
`--refresh-data` and `--no-cache` flags concern the merged model cache; an
explicit flow checkpoint directory is a separate opt-in snapshot. Chunk width
is recorded in the page date bounds. Source tick-rule classification restarts
at query boundaries, so runs with different chunk widths are not guaranteed
bit-for-bit identical; retain the width when comparing runs.
Merged-cache filenames now include the corrected date-boundary schema and chunk
width so an older snapshot cannot silently bypass this fix or option.

### Completed Fresh MSFT Baseline

The dated 2024-10-20 through 2026-10-19 request completed successfully using
seven-day pages: 105 successful page snapshots contained 90,304 five-minute flow
rows, and the final price dataset contained 500 daily bars. After the legacy
clock-session/outlier filters, 472 daily dates had flow inputs. There were 28
price dates without flow, spanning 2026-09-02 through 2026-10-12; recent 20-bar
flow presence was only 25%. These are source gaps, not authentication failures,
and neither the output nor its model rating should be called fully complete.

The QQQ benchmark ended on 2026-10-13. Inspection found that pandas' default
`pct_change` behavior forward-filled missing benchmark quotes and gave the last
four price dates an apparently available relative regime. Returns now use
`fill_method=None`, and duplicate benchmark keys cannot expand stock rows.
Unavailable benchmark dates stay `relative_unavailable`. The model was rerun
successfully with this correction, reusing the same 105 explicitly labeled flow
checkpoints instead of repeating heavy database requests. The merged-cache key
also marks the no-forward-fill schema, and CSVs retain `hmm_strength` for replay.

The short-volume source ended on 2026-08-04; delayed darkpool inputs began in
2025-08 and ended in 2026-09. Full-sample HMM fitting and these source limitations
remain: this is a new descriptive research baseline, not a validated backtest,
proof of actual institutional holdings, or an exact recovery of the missing
original CSV. No signal was forced positive. The raw and filtered signed dollar
flow and the model's cumulative share-change proxy are different quantities.

The actual downloaded pages, CSVs and detailed source-quality audit are retained
locally in ignored output/checkpoint folders, not redistributed in this public
fork. No production website release was performed for this research change.

## Independent Sampled-Flow Estimator

The new `flow_estimator.py` / `run_flow_model.py` path does **not** call v5.3,
read `trade_signal`, reuse its HMM, or turn recommendations into share changes.
The original v5.3 path remains available for historical compatibility; it has
not become a calibrated inventory estimator.

The new quantity is signed **sampled USD notional**, method
`sampled-tick-rule-v1`. For each regular session:

```text
sampledLargeNetUsd = sum(super_buy + large_buy - super_sell - large_sell)
dailyPressure = sampledLargeNetUsd / sampledNotionalUsd
pressure5/20 = sum(sampledLargeNetUsd, 5/20 sessions)
               / sum(sampledNotionalUsd, 5/20 sessions)
```

Buckets retain the source's fixed USD thresholds: super >= 500,000, large >=
100,000, mid >= 20,000. The source is the teacher server's `/api/main-flow`
tick-rule classification of available stored trades, not verified aggressors
or identified institutions. Unlike the separate large-trades widget, this
endpoint does not apply a checksum-prefix 1/16 filter; do not infer that sample
rate or multiply these values by 16. The aggregate response cannot independently
establish raw trade-ID deduplication, correction eligibility or complete capture.
The inspected legacy source queries stored `price * size`, does not explicitly
deduplicate raw ticks or exclude correction flags, and stores `decimal_size`
as an integer. It is therefore not an exact fractional-share notional series.
These are remaining source-quality risks, not evidence that every repeated
checksum is a duplicate or that zero integer size means an invalid execution.
[Massive's fractional-share documentation](https://massive.com/knowledge-base/article/how-does-massive-handle-fractional-share-trades)
explains why a valid fractional execution can have integer `size = 0` and needs
its decimal-size field. Resolving the historical source precision requires a
separately reconciled ingestion migration, not a silent interpretation change
halfway through this repair. The current research page exposes this limitation.
No full-tape extrapolation, holdings reconstruction, positivity clamp or
conversion of dollars into shares is performed. A negative result is allowed.

The XNYS calendar validates every price session and applies DST, holidays and
early closes. A covered session has every expected five-minute sample bucket
(78 on a full day, 42 on a 13:00 ET close). This means five-minute **sample
coverage**, not proof of complete trade capture. Duplicate identical buckets
are counted once; conflicting revisions, invalid units, amounts, grain and
non-reconciling bucket totals fail. Missing and partial sessions invalidate
rolling pressure, and continuous cumulative notional stops at an interior gap.

The pre-repair fresh baseline has 471 fully five-minute-covered sessions, 28
missing sessions and one partial session (2026-10-13). The earlier legacy
472-date count measures any filtered flow presence, not full-session coverage.
Historical backfill must be re-queried and these counts recomputed before
claiming the gaps are repaired. Do not use insertion counts alone as coverage.

### Chronological Replay, Not Proven Predictive Alpha

`flow_walk_forward.py` uses scikit-learn `TimeSeriesSplit`, up to ten folds,
252-bar rolling training, 21-bar tests and a five-bar gap. Training-only 20th
and 80th percentiles of five-session pressure define one fixed illustrative
rule. At least 120 valid training estimates are required. Values above the
positive upper threshold are long, below the negative lower threshold short,
and otherwise cash. This rule has not been optimized on the held-out results.

A close-of-day decision enters at the next session open and earns the return
to the following open. One-way cost is 10 bps, including turnover, flips and
terminal liquidation; the same-date buy-and-hold comparator pays entry/exit
costs. Missing predictions explicitly hold cash and remain in the coverage
denominator. Fold boundaries and per-date decisions are exported for inspection.
Tests mutate future prices/estimates and verify that past estimates and decisions
do not change. This does not make historical data point-in-time valid.

The required status is `research_replay_not_point_in_time_verified`: historical
vendor revisions/availability and adjusted-price basis are not independently
verified. Borrow fees, financing and extra slippage are excluded. Do not treat
this as a production strategy, evidence of institutional ownership or a reason
to trade. A prospective frozen-data evaluation is still required.

### Rebuild Without Repeating Heavy Requests

The following paths are examples for local, ignored research artifacts:

```bash
.venv/bin/python 'Backtest/backtest scripts & outputs/run_flow_model.py' \
  --ticker MSFT --prices /path/to/dated-prices.csv \
  --flow-checkpoint-dir /path/to/private/flow-pages \
  --output local-artifacts/flow-model/MSFT.json
```

After an authorized historical repair, use `refresh_flow_checkpoints.py` with
`--original`, a separate versioned `--output`, `--repair-snapshot`,
`--api-base-url`, `--credentials-file` and `--api-username`. Only requests that
overlap the repair dates are refreshed. Unaffected pages retain their original
fetch time; the old directory is never changed. A private manifest records
retained/refreshed pages and SHA256 hashes. Repeat the snapshot command with
the new directory. The JSON includes both price and flow fingerprints.

### Website and WebSocket Acceptance

The website's authenticated `/flow-model` page reads precomputed JSON snapshots
from `FLOW_MODEL_SNAPSHOT_DIR`, never a public directory. Opening the page does
not rerun the estimator or request millions of trades. The three chart panes
show price, sampled large-trade imbalance and 5/20-session pressure. Missing
windows are not connected or filled with zero. Available tickers come from the
published backend snapshot files, not an assumed universe of supported models.
The page is bilingual and explicitly marked experimental/not live. Anonymous
access is rejected before reading snapshots; path traversal and symlinks fail.

`verify_market_stream.py` checks normal authenticated protocol-2 subscriptions,
subscribe acknowledgement, ping/pong, contiguous sequence and actual payloads.
`--require-realtime` also requires advertised delay zero, valid data and a source
timestamp within 30 seconds (at most five seconds of future clock skew). A
working socket or heartbeat alone cannot pass. A stale replay labeled zero
delay cannot pass either. Login uses only the secure API/tunnel and the existing
private account file, with session secrets held in memory.

Actual MSFT trades and K-line probes on 2026-10-20 passed connection, subscribe
and ping/pong, but advertised **900 seconds of delay** and delivered no market
frames in the bounded 15-second window per channel. Real-time and overnight
acceptance therefore remain **unpassed**. The existing upstream collector was
not duplicated, and no vendor package, account credential or security policy
was changed. The page's HTTP tests passed after deployment; browser visual
acceptance remains subject to the user's saved website browsing permission.

A separate read-only vendor check returned historical trades HTTP 200 and
latest trade HTTP 200 with vendor status `DELAYED`; the latest NBBO endpoint
returned HTTP 403 `NOT_AUTHORIZED`. Thus restored historical access does not
establish real-time or quote entitlement. The selected upstream WebSocket feed
is also configured `delayed`. No second upstream socket was started, avoiding
interference with the existing collector's connection allowance.

### Website Integration Source

`integrations/us_stock/` contains the reviewed website addition and operations
scripts, separate from the existing website repository's unrelated changes.
The `web/` files use that application's existing authentication, i18n, remote
data hooks and Lightweight Charts dependency. They are not a standalone site.
`ops/install_flow_page.py` backs up files and applies the five new page/data
files plus four narrow navigation/config edits. It refuses a different existing
flow file unless its hash matches a previously recorded install manifest.

`ops/activate_flow_page.py` checks a completed build and model snapshot, keeps
hashed assets for already-open pages, restarts only the web service, and restores
the previous service override if its readiness check fails. Production was
returned to the normal `.next` build directory after alternate-build testing;
the only persistent service setting for this feature is
`FLOW_MODEL_SNAPSHOT_DIR`. The previous `.next` build and install/activation
receipts are retained on the server for rollback. Future ordinary website
builds therefore do not silently keep serving an old alternate release.

The gap-repair helper targets only explicit past dates from one snapshot. It
uses at most three workers, stages a complete vendor day privately, and inserts
only absent checksums. It never deletes existing tape records. Incomplete
downloads cannot be applied. `inspect_flow_stages.py` independently checks the
completed stage date bounds; `probe_flow_sources.py` reports entitlement status
without printing keys. Run the four staging safety tests with:

```bash
.venv/bin/python -m unittest discover -s integrations/us_stock/tests -v
```

Do not publish raw trade staging files, website account files, `.env` values,
session cookies or model snapshot datasets to this public source repository.

## INTC / TSLA Case Pilot

`flow_case_protocol.json` fixes a descriptive pilot from July 1 through
October 31, 2025, with data from May 1 for rolling-window warm-up. These dates
were chosen after reading the supplied v0.7 case study; the cases are not unseen
test data. RGTI and BBAI remain `not_run`, with no established manipulation label.

The first unfiltered server export completed INTC but timed out on TSLA under
the bounded query budget. A separate versioned export uses checksum prefix `0`
for **both** tickers, nominally 1/16 of checksum space. Direction is computed
between selected trades, not full-tape neighbors. Representativeness is unknown;
there is no multiplication by 16 or conversion to holdings. The original INTC
export is retained separately. Current website MSFT snapshots are not changed
to this sampling policy.

`integrations/us_stock/ops/export_flow_cases.py` runs using the teacher server's
existing read-only repository SQL, with a parameterized sample predicate. It
refuses an unexpected SQL shape, unapproved tickers, public output paths, long
windows and query budgets over 60 seconds. It stages only completed queries,
uses at most two threads per query, caps memory at 2 GiB, and uses a job lock.
No production table, API source, website service or vendor subscription is
changed. The successful pilot uses the server's existing authorized adjusted
daily-aggregate vendor helper; price provenance and adjustment flags are saved.

The new `flow_case_audit.py` checks calendar/session coverage and reconciles
direct 5m-to-day sampled notional with 5m-to-session-anchored-hour-to-day sums.
The final hourly bucket can be 30 minutes. This checks the aggregation path,
not independent tape completeness or the old screenshot's hourly calculation.
Missing observations remain unavailable. Past-only five-session price response
and 5/20-session sampled pressure produce descriptive conflict candidates, not
institutional identity or trade instructions.

The deck's slide 3 uses a continuous model bias, while the inspected repository
uses `long=1`, `short=-1`, otherwise zero for modeled share changes. The pilot
records this unresolved formula-version difference. Optional offline v5.3 replay
uses the same price and flow snapshots but preserves its original auction and
outlier filters. It fits its existing full-sample HMM and reliability; benchmark,
short-volume and dark-pool context are explicitly absent. It is an arithmetic
and semantics comparison, not an exact reproduction of the deck or a predictive
backtest. No return, Sharpe, accuracy or manipulation probability is fabricated.

After downloading the private completed export into a local ignored directory:

```bash
.venv/bin/python 'Backtest/backtest scripts & outputs/run_flow_cases.py' \
  --input-root local-artifacts/flow-cases-20261027/inputs-prefix0 \
  --replay-repository \
  --output local-artifacts/flow-cases-20261027/pilot.json

.venv/bin/python 'Backtest/backtest scripts & outputs/plot_flow_cases.py' \
  --input local-artifacts/flow-cases-20261027/pilot.json \
  --output local-artifacts/flow-cases-20261027/case-preview.html \
  --png local-artifacts/flow-cases-20261027/case-preview.png
```

The standalone Plotly preview embeds its JavaScript, offers English/Chinese
labels and a date-range slider, and does not contact the production website.
The optional PNG uses Matplotlib without browser/network access. A static
figure check does not verify HTML interaction or mobile layout. Browser policy
currently blocks agent navigation to `file:` URLs; do not bypass that restriction.
Raw snapshots and derived case datasets stay local/private, not in this fork.
