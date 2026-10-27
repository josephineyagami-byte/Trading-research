"""Prefix-only v5.3 diagnostic, not unseen/vintage-verified strategy performance."""

import io
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

from flow_estimator import estimate_daily_flow
from inventory_diagnostics import add_inventory_diagnostics
from legacy_case_replay import prepare_repository_inputs
import signal_generator_v4 as v4
import signal_generator_v5_3 as v53


FIELDS = ["final_score", "trade_signal", "est_inst_participation", "delta_inventory",
          "hmm_state", "hmm_label", "hmm_strength", "flow_reliability", "flow_weight"]


def replay_forward(prices, raw_rows, ticker):
    daily = estimate_daily_flow(prices, raw_rows, ticker)
    prepared = prepare_repository_inputs(prices, raw_rows).reset_index(drop=True)
    output = []
    for position in range(len(prepared)):
        current = prepared.iloc[position]
        row = {"datetime": current.datetime, "volume": current.volume,
               "ticker": ticker, "trainingBars": position,
               "trainingEnd": prepared.datetime.iloc[position-1].strftime("%Y-%m-%d") if position else None,
               "decisionStatus": "insufficient_training", "errorType": None,
               **{name: None for name in FIELDS}}
        if position >= 100:
            if not daily.sessionComplete.iloc[position-19:position+1].all():
                row["decisionStatus"] = "incomplete_recent_flow"
            else:
                prefix = prepared.iloc[:position+1].copy()
                try:
                    with redirect_stdout(io.StringIO()):
                        fitted = v4.fit_hmm(prefix, n_states=3, train_end=row["trainingEnd"], causal_endpoint=True)
                        scored = v53.compute_signal(fitted, ticker=ticker)
                    endpoint = scored.iloc[-1]
                    if not np.isfinite(endpoint[["final_score", "est_inst_participation", "delta_inventory"]].astype(float)).all():
                        row["decisionStatus"] = "feature_unavailable"
                    else:
                        row.update({name: endpoint[name] for name in FIELDS})
                        row["decisionStatus"] = "available"
                except (ValueError, ArithmeticError, np.linalg.LinAlgError, ImportError) as exc:
                    row["decisionStatus"] = "fit_unavailable"
                    row["errorType"] = type(exc).__name__
        output.append(row)
    out = pd.DataFrame(output)
    # Score only the endpoint of each immutable prefix. Never copy cumulative
    # inventory recomputed under today's reliability weights over older rows.
    out["delta_inventory"] = pd.to_numeric(out.delta_inventory, errors="raise")
    out = add_inventory_diagnostics(out)
    out["cumulative_inventory"] = out.cumulative_model_position_change_shares
    metadata = {
        "mode": "repository_v5_3_causal_endpoint_diagnostic",
        "training": "Expanding prior observations only; minimum 100 bars; no full-sample fallback",
        "decoding": "Training-only state profiles; endpoint filtered from its own available prefix",
        "quality": "Reliability and scoring evaluated per prefix; only endpoint retained",
        "decisionCounts": {key: int(value) for key, value in out.decisionStatus.value_counts().items()},
        "evaluationStatus": "chronological_diagnostic_not_unseen_or_vintage_verified",
        "context": "Benchmark, short-volume and dark-pool context remain absent",
        "sourceRepresentativeness": "not_established", "performance": None, "holdings": None,
    }
    return out, metadata
