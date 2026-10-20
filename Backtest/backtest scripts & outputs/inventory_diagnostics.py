"""Separate signed model changes from unobserved institutional holdings.

No institution identity, execution or ownership is inferred by this module.
Negative changes are retained. An optional anchor is a user-supplied scenario,
not a calibration or a recovered holdings estimate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


DIAGNOSTIC_COLUMNS = [
    "model_position_change_shares", "cumulative_model_position_change_shares",
    "model_flow_pressure_pct", "model_flow_pressure_window",
    "inventory_data_status", "inventory_semantics", "inventory_scenario_shares",
    "inventory_anchor_status", "inventory_anchor_source", "inventory_anchor_as_of",
]


def validate_bars(df: pd.DataFrame) -> None:
    required = {"datetime", "volume", "delta_inventory"}
    if missing := required - set(df.columns):
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if df.empty:
        raise ValueError("No bars to audit")
    dates = pd.to_datetime(df["datetime"], utc=True, errors="raise")
    if dates.isna().any() or dates.duplicated().any():
        raise ValueError("Missing or duplicate bar timestamps; repair the source first")
    if not dates.is_monotonic_increasing:
        raise ValueError("Bars must be ordered oldest first")
    for column in ("ticker", "symbol"):
        if column in df and (df[column].isna().any() or df[column].nunique() != 1):
            raise ValueError("Audit one identified ticker at a time")
    volume = pd.to_numeric(df["volume"], errors="raise")
    delta = pd.to_numeric(df["delta_inventory"], errors="raise")
    if np.isinf(volume).any() or (volume.dropna() < 0).any() or np.isinf(delta).any():
        raise ValueError("Volume/change must be finite; volume cannot be negative")
    if (delta.abs() > volume + 1e-6).any():
        raise ValueError("Model share change exceeds bar share volume; check units")


def add_inventory_diagnostics(
    df: pd.DataFrame,
    *,
    window: int = 20,
    initial_inventory_shares: float | None = None,
    anchor_source: str | None = None,
    anchor_as_of: str | None = None,
) -> pd.DataFrame:
    """Add diagnostics without changing any legacy score or inventory column.

    The relative series begins at the first computable change. An interior
    missing change invalidates subsequent cumulative values. The anchor must
    describe inventory immediately before the first input bar, in the same
    split-adjusted share units and participant scope as all subsequent deltas.
    """
    validate_bars(df)
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise ValueError("window must be a positive integer")
    out = df.copy()
    delta = pd.to_numeric(out["delta_inventory"], errors="raise").astype(float)
    volume = pd.to_numeric(out["volume"], errors="raise").astype(float)
    delta = delta.where(volume.notna())
    started = delta.notna().cummax()
    gap = (started & delta.isna()).cummax()
    relative = delta.cumsum().mask(gap)
    out["model_position_change_shares"] = delta
    out["cumulative_model_position_change_shares"] = relative
    # This is a signed share-of-volume proxy, not a measured ownership ratio.
    total_volume = volume.rolling(window, min_periods=window).sum()
    out["model_flow_pressure_pct"] = (
        100 * delta.rolling(window, min_periods=window).sum()
        / total_volume.where(total_volume > 0)
    )
    out["model_flow_pressure_window"] = window
    out["inventory_data_status"] = np.select(
        [~started, started & delta.isna(), gap],
        ["warmup_or_missing", "missing_change", "incomplete_after_gap"],
        default="ok",
    )
    out["inventory_semantics"] = "model_change_not_holdings"
    out["inventory_scenario_shares"] = np.nan
    out["inventory_anchor_status"] = "missing_anchor"
    out["inventory_anchor_source"] = ""
    out["inventory_anchor_as_of"] = ""
    if initial_inventory_shares is None:
        if anchor_source is not None or anchor_as_of is not None:
            raise ValueError("Anchor metadata requires initial_inventory_shares")
        return out
    if not np.isfinite(initial_inventory_shares) or initial_inventory_shares < 0:
        raise ValueError("Initial inventory must be finite and nonnegative")
    if not anchor_source or not anchor_source.strip() or not anchor_as_of:
        raise ValueError("An anchor requires a source and as-of timestamp")
    anchor_date = pd.to_datetime(anchor_as_of, utc=True, errors="raise")
    first_date = pd.to_datetime(out["datetime"].iloc[0], utc=True)
    if pd.isna(anchor_date) or anchor_date >= first_date:
        raise ValueError("Anchor must predate the first input bar; no future holdings")
    scenario = initial_inventory_shares + delta.cumsum(skipna=False)
    breached = (scenario < 0).cummax()
    out["inventory_scenario_shares"] = scenario
    out["inventory_anchor_status"] = np.select(
        [scenario.isna(), breached],
        ["incomplete_scenario", "invalid_negative_scenario"],
        default="anchored_scenario_not_observed_holdings",
    )
    out["inventory_anchor_source"] = anchor_source
    out["inventory_anchor_as_of"] = anchor_date.isoformat()
    return out


def audit_summary(df: pd.DataFrame, source: str) -> dict:
    """JSON-safe, source-linked diagnostics for a future website adapter."""
    out = add_inventory_diagnostics(df)
    delta = out["model_position_change_shares"]
    relative = out["cumulative_model_position_change_shares"]
    legacy = pd.to_numeric(out.get("cumulative_inventory", pd.Series(np.nan, index=out.index)), errors="raise")
    overlap = relative.notna() & legacy.reindex(out.index).notna()
    mismatch = (int((~np.isclose(relative[overlap], legacy[overlap], rtol=1e-8, atol=1e-4)).sum())
                if overlap.any() else None)
    def number(value):
        return None if pd.isna(value) else float(value)
    return {
        "schema_version": "inventory-diagnostics-v1",
        "source_file": source,
        "rows": len(out),
        "start": str(out["datetime"].iloc[0]),
        "end": str(out["datetime"].iloc[-1]),
        "model_change_coverage": float(delta.notna().mean()),
        "cumulative_model_position_change_shares": number(relative.iloc[-1]),
        "minimum_cumulative_model_position_change_shares": number(relative.min()),
        "legacy_cumulative_mismatch_rows": mismatch,
        "legacy_cumulative_compared_rows": int(overlap.sum()),
        "model_flow_pressure_pct": number(out["model_flow_pressure_pct"].iloc[-1]),
        "model_flow_pressure_window": 20,
        "inventory_data_status": out["inventory_data_status"].iloc[-1],
        "institutional_holdings_shares": None,
        "holdings_status": "unidentifiable_without_calibration_and_anchor",
        "warnings": [
            "Signed model changes are not observed institutional positions or fund flows.",
            "No forced positivity, zero-filled gaps, or inferred opening balance.",
            "Bar validation cannot detect omitted sessions or unreported stock splits.",
            "Historical signals may use full-sample HMM/quality fits; this audit is not a causal backtest.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--summary-only", action="store_true", help="Skip the per-file CSV exports")
    args = parser.parse_args()
    # Validate the entire batch before creating any exports.
    inputs = [(path, pd.read_csv(path)) for path in args.files]
    if len({p.stem for p, _ in inputs}) != len(inputs):
        parser.error("Input filenames must have unique stems")
    audited = [(p, add_inventory_diagnostics(df), audit_summary(df, p.as_posix())) for p, df in inputs]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.summary_only:
        for path, frame, _ in audited:
            frame.to_csv(args.output_dir / f"{path.stem}_audited.csv", index=False)
    report = {"files": [summary for _, _, summary in audited]}
    (args.output_dir / "inventory_audit.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
