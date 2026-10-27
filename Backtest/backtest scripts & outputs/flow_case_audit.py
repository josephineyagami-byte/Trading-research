"""Case diagnostics with explicit units and session-anchored aggregation checks."""

import numpy as np
import pandas as pd

from flow_estimator import AMOUNTS, estimate_daily_flow, session_schedule


FORMULAS = {
    "legacyRepository": "signal_direction(long=1, short=-1, otherwise=0) * participation_pct / 100 * volume_shares",
    "caseStudySlide3": "continuous_model_bias[-1,1] * participation_pct / 100 * volume_shares",
    "formulaVersionAligned": False,
    "sampledFlow": "super_buy_usd + large_buy_usd - super_sell_usd - large_sell_usd",
    "pressure": "sum(sampled_large_net_usd, window) / sum(all_sampled_notional_usd, window)",
    "interpretation": "Legacy share-change proxies and sampled USD notional are different quantities; do not subtract their levels.",
}


def legacy_formula_audit(frame):
    """Check the saved repository formula without refitting or repairing the output."""
    required = {"datetime", "trade_signal", "est_inst_participation", "volume", "delta_inventory", "cumulative_inventory"}
    if not required <= set(frame):
        return {"status": "unavailable", "reason": "Saved legacy formula inputs are absent."}
    dates = pd.to_datetime(frame.datetime, utc=True, errors="raise")
    if frame.empty or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("Legacy observations must have unique chronological timestamps")
    fields = ["est_inst_participation", "volume", "delta_inventory", "cumulative_inventory"]
    if frame[fields].map(lambda v: isinstance(v, (bool, np.bool_))).any().any():
        raise ValueError("Boolean legacy values are invalid")
    values = frame[fields].apply(pd.to_numeric, errors="raise")
    if np.isinf(values.to_numpy()).any():
        raise ValueError("Infinite legacy values are invalid")
    if ((values.est_inst_participation.dropna() < 0).any()
            or (values.est_inst_participation.dropna() > 25).any()
            or (values.volume.dropna() < 0).any()):
        raise ValueError("Invalid legacy participation or share volume")
    if not frame.trade_signal.dropna().isin(["long", "short", "neutral", "watch_long", "watch_short", "absorption_watch"]).all():
        raise ValueError("Unknown legacy trade signal")
    direction = pd.Series(np.select([frame.trade_signal.eq("long"), frame.trade_signal.eq("short")], [1, -1], 0), index=frame.index)
    predicted = direction * values.est_inst_participation / 100 * values.volume
    eligible = values.notna().all(axis=1) & frame.trade_signal.notna()
    delta_mismatch = eligible & ~np.isclose(predicted, values.delta_inventory, rtol=1e-7, atol=.01, equal_nan=False)
    cumulative = values.delta_inventory.cumsum()
    cumulative_mismatch = eligible & ~np.isclose(cumulative, values.cumulative_inventory, rtol=1e-7, atol=.01, equal_nan=False)
    return {
        "status": "pass" if eligible.any() and not delta_mismatch.any() and not cumulative_mismatch.any() else "mismatch" if eligible.any() else "unavailable",
        "checkedRows": int(eligible.sum()), "totalRows": len(frame),
        "deltaMismatchRows": int(delta_mismatch.sum()), "cumulativeMismatchRows": int(cumulative_mismatch.sum()),
        "zeroDirectionRows": int((eligible & direction.eq(0)).sum()),
        "firstDate": dates.iloc[0].strftime("%Y-%m-%d"), "lastDate": dates.iloc[-1].strftime("%Y-%m-%d"),
        "reproducesCaseStudy": False,
        "meaning": "Arithmetic check of saved repository output, not a reproduction of the deck's continuous-bias formula or proof of holdings.",
    }


def timeframe_audit(prices, raw_rows, ticker):
    """Use one validated 5m source; compare direct daily sums with sums via 1h."""
    daily = estimate_daily_flow(prices, raw_rows, ticker)
    schedule = session_schedule(daily.date.iloc[0], daily.date.iloc[-1])
    fields = [*AMOUNTS, "total_notional", "neutral_notional", "sample_count"]
    raw = pd.DataFrame(raw_rows, columns=["time", *fields]).drop_duplicates()
    hourly_rows, reconciliation = [], []
    for session in schedule.itertuples():
        start = session.open.value // 1_000_000
        end = session.close.value // 1_000_000
        observed = raw[(raw.time >= start) & (raw.time < end)].copy()
        expected = int((end-start)//300000)
        for offset in range(0, expected, 12):
            left, right = start+offset*300000, min(start+(offset+12)*300000, end)
            chunk = observed[(observed.time >= left) & (observed.time < right)]
            row = {"date": session.Index, "time": left, "endTime": right,
                   "expectedBars": int((right-left)//300000), "sourceBars": len(chunk)}
            row.update({name: float(chunk[name].sum()) if len(chunk) else np.nan for name in fields})
            row["sampledLargeNetUsd"] = row["super_buy"]+row["large_buy"]-row["super_sell"]-row["large_sell"]
            row["sessionComplete"] = row["sourceBars"] == row["expectedBars"]
            row["pressure"] = row["sampledLargeNetUsd"]/row["total_notional"] if row["sessionComplete"] else np.nan
            hourly_rows.append(row)
        hours = hourly_rows[-((expected+11)//12):]
        row = daily.loc[daily.date.eq(session.Index)].iloc[0]
        counts_match = sum(h["sourceBars"] for h in hours) == int(row.sourceBars) if pd.notna(row.sourceBars) else all(h["sourceBars"] == 0 for h in hours)
        errors = {}
        for name, column in [("total_notional", "sampledNotionalUsd"), ("sampledLargeNetUsd", "sampledLargeNetUsd"), ("sample_count", "sampleCount")]:
            total = sum(h[name] for h in hours if pd.notna(h[name]))
            direct = row[column]
            errors[name] = float(total-direct) if pd.notna(direct) else None
        identity = counts_match and all(value is None or abs(value) <= (0 if name == "sample_count" else max(.01, abs(float(row["sampledNotionalUsd"]))*1e-9)) for name, value in errors.items())
        reconciliation.append({"date": session.Index, "sessionComplete": bool(row.sessionComplete),
                               "sourceBarsMatch": counts_match, "amountsMatch": identity, "errors": errors})
    hours = pd.DataFrame(hourly_rows)
    summary = {
        "status": "pass" if all(r["amountsMatch"] for r in reconciliation) else "mismatch",
        "basis": "Same supplied 5m sample; session-open anchored 60m buckets, final bucket may be 30m.",
        "independentSourceVerification": False,
        "checkedSessions": len(daily), "completeSessions": int(daily.sessionComplete.sum()),
        "completeHourlyBuckets": int(hours.sessionComplete.sum()), "totalHourlyBuckets": len(hours),
        "mismatchDates": [r["date"].strftime("%Y-%m-%d") for r in reconciliation if not r["amountsMatch"]],
        "allSessionsCovered": bool(daily.sessionComplete.all()),
    }
    return daily, hours, reconciliation, summary


def describe_price_flow(daily):
    """Past-only descriptive states; no account identity, recommendation or target."""
    out = daily.copy()
    out["priceReturn5"] = out.close / out.close.shift(5) - 1
    out["state"] = "data_unavailable"
    valid = out.sessionComplete & out.pressure5.notna() & out.priceReturn5.notna()
    for flow_up, price_up, state in [
        (True, True, "positive_pressure_price_rising"),
        (False, False, "negative_pressure_price_falling"),
        (False, True, "negative_pressure_price_resilient_candidate"),
        (True, False, "positive_pressure_price_weak_candidate"),
    ]:
        mask = valid & (out.pressure5 > 0 if flow_up else out.pressure5 < 0) & (out.priceReturn5 > 0 if price_up else out.priceReturn5 < 0)
        out.loc[mask, "state"] = state
    out.loc[valid & ((out.pressure5 == 0) | (out.priceReturn5 == 0)), "state"] = "mixed"
    return out
