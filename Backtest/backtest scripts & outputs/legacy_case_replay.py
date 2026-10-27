"""Offline repository-v5.3 diagnostic on the same price and flow snapshots.

Full-sample HMM/reliability and absent external context make this unsuitable
for predictive-performance claims or an exact reproduction of deck screenshots.
"""

import hashlib
from pathlib import Path

import pandas as pd

from market_data_quality import regular_session_mask
from flow_estimator import normalize_flow_samples
import signal_generator_v4 as v4
import signal_generator_v5_3 as v53


def replay_repository(prices, raw_rows, ticker):
    bars = prices.copy()
    bars["datetime"] = pd.to_datetime(bars.datetime, utc=True).dt.tz_localize(None)
    if "timestamp" not in bars:
        bars["timestamp"] = bars.datetime.astype("int64")//1_000_000
    bars = v4.compute_features(bars)
    raw = normalize_flow_samples(raw_rows)
    if len(raw):
        raw = raw.loc[regular_session_mask(raw.time)].copy()
        raw["xl_net"] = raw.super_buy-raw.super_sell
        raw["l_net"] = raw.large_buy-raw.large_sell
        raw = raw.loc[raw.xl_net.abs() <= 50_000_000].copy()
        raw["date"] = pd.to_datetime(raw.time, unit="ms").dt.normalize()
        flow = raw.groupby("date", as_index=False)[["xl_net", "l_net"]].sum()
    else:
        flow = pd.DataFrame(columns=["date", "xl_net", "l_net"])
        flow["date"] = pd.to_datetime(flow.date)
    flow["inst_net"] = flow.xl_net+flow.l_net
    bars = v53.merge_flow(bars, flow)
    bars = v53._empty_short_context(bars)
    bars = v53._empty_darkpool_context(bars)
    bars["relative_regime"] = "relative_unavailable"
    bars = v53.fit_hmm_safe(bars, n_states=3)
    bars = v53.compute_signal(bars, ticker=ticker)
    metadata = {
        "mode": "repository_v5_3_offline_diagnostic",
        "samePriceInputsVerified": True,
        "hmmFit": "full_sample_not_point_in_time_verified",
        "hmmFallbackRows": int(bars.hmm_state.eq(-1).sum()),
        "context": "Benchmark, short-volume and dark-pool context are absent, not zero; confirmation gates remain limited.",
        "legacySourceSha256": hashlib.sha256(Path(v53.__file__).read_bytes()).hexdigest(),
        "legacyFeatureSourceSha256": hashlib.sha256(Path(v4.__file__).read_bytes()).hexdigest(),
        "flowFilter": "Repository legacy 09:35-16:00 ET mask and absolute super-net <= $50M per 5m bar; differs from the new full regular-session estimator.",
        "reproducesCaseStudy": False,
    }
    return bars, metadata
