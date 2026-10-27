"""Build a fixed-window pilot from private snapshots; never manufacture inputs."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

import pandas as pd

from flow_case_audit import FORMULAS, describe_price_flow, legacy_formula_audit, sampling_sensitivity, timeframe_audit
from flow_estimator import estimate_daily_flow, load_flow_checkpoints


def records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def build_case(case, protocol, folder, legacy_path=None, replay_legacy=False, reference_flow_dir=None, forward_legacy=False):
    prices_path, flow_path = folder/"prices.csv", folder/"flow-pages"
    result = {"ticker": case["ticker"], "question": case["question"], "events": case["events"],
              "status": "unavailable", "reproducesCaseStudy": False}
    if not prices_path.exists() or not flow_path.exists() or not any(flow_path.glob("flow-*.json")):
        result["reason"] = "Price or five-minute flow snapshots have not been collected. Missing data is not zero."
        return result
    prices = pd.read_csv(prices_path)
    collection_path = folder/"collection.json"
    collection = json.loads(collection_path.read_text()) if collection_path.exists() else {}
    if collection and collection.get("sha256") != hashlib.sha256(prices_path.read_bytes()).hexdigest():
        raise ValueError("Price snapshot hash differs from its collection receipt")
    dates = pd.to_datetime(prices.datetime, utc=True).dt.strftime("%Y-%m-%d")
    if dates.min() != protocol["collectionStart"] or dates.max() != protocol["analysisEnd"]:
        raise ValueError(f"{case['ticker']}: price bounds do not match the frozen protocol")
    raw = load_flow_checkpoints(flow_path, case["ticker"])
    source_page = json.loads(next(flow_path.glob("flow-*.json")).read_text())
    source_id = source_page["request"]["source"]
    expected_sample = protocol.get("flowSample")
    if expected_sample and not source_id.endswith(":checksum-prefix-0"):
        raise ValueError("The frozen sampled protocol cannot use unfiltered or unidentified flow pages")
    daily, hourly, checks, audit = timeframe_audit(prices, raw, case["ticker"])
    daily = describe_price_flow(daily)
    daily["date"] = daily.date.dt.strftime("%Y-%m-%d")
    included = daily.date.between(protocol["analysisStart"], protocol["analysisEnd"])
    selected = daily.loc[included].copy()
    if selected.empty:
        raise ValueError("No daily observations in the fixed analysis window")
    selected_hourly = hourly[hourly.date.between(pd.Timestamp(protocol["analysisStart"]), pd.Timestamp(protocol["analysisEnd"]))]
    complete = int(selected.sessionComplete.sum())
    audit["analysisCheckedSessions"] = len(selected)
    audit["analysisCompleteSessions"] = complete
    pages = sorted(flow_path.glob("flow-*.json"))
    result.update({
        "status": "available" if complete == len(selected) else "partial" if complete else "unavailable",
        "firstDate": selected.date.iloc[0], "dataThrough": selected.date.iloc[-1],
        "coverage": {"priceSessions": len(selected), "completeFlowSessions": complete,
                     "missingDates": selected.loc[selected.status.eq("missing"), "date"].tolist(),
                     "partialDates": selected.loc[selected.status.eq("partial"), "date"].tolist()},
        "timeframeAudit": audit,
        "hourly": records(selected_hourly.assign(date=selected_hourly.date.dt.strftime("%Y-%m-%d"))),
        "reconciliation": [{**r, "date": r["date"].strftime("%Y-%m-%d")} for r in checks],
        "series": records(selected), "stateCounts": {key: int(value) for key, value in selected.state.value_counts().items()},
        "priceSha256": hashlib.sha256(prices_path.read_bytes()).hexdigest(),
        "priceSource": collection.get("priceSource", "unverified"), "priceAdjusted": collection.get("priceAdjusted"),
        "flowSource": source_id, "flowSample": protocol.get("flowSample"),
        "flowFingerprint": hashlib.sha256(b"".join(p.name.encode()+hashlib.sha256(p.read_bytes()).digest() for p in pages)).hexdigest(),
        "legacy": {"status": "unavailable", "reason": "No same-window legacy output was supplied."},
        "performance": None,
    })
    if reference_flow_dir is not None:
        reference_flow_dir = Path(reference_flow_dir)
        reference_page = json.loads(next(reference_flow_dir.glob("flow-*.json")).read_text())
        if reference_page["request"]["source"]+":checksum-prefix-0" != source_id:
            raise ValueError("Use the same repository formula without the checksum subset as reference")
        reference = estimate_daily_flow(prices, load_flow_checkpoints(reference_flow_dir, case["ticker"]), case["ticker"])
        sampled = daily.copy()
        sampled["date"] = pd.to_datetime(sampled.date)
        result["samplingSensitivity"] = sampling_sensitivity(reference, sampled, protocol["analysisStart"], protocol["analysisEnd"])
        reference_pages = sorted(reference_flow_dir.glob("flow-*.json"))
        result["samplingSensitivity"]["referenceFingerprint"] = hashlib.sha256(b"".join(p.name.encode()+hashlib.sha256(p.read_bytes()).digest() for p in reference_pages)).hexdigest()
        ref = reference[["date", "pressure5", "pressure20"]].copy()
        ref["date"] = ref.date.dt.strftime("%Y-%m-%d")
        ref = ref.rename(columns={"pressure5":"referencePressure5", "pressure20":"referencePressure20"})
        result["series"] = records(selected.merge(ref, on="date", validate="one_to_one"))
        result["samplingSensitivity"]["interpretationReadiness"] = "source_sensitive_do_not_substitute"
    if legacy_path is not None or replay_legacy:
        metadata = {}
        if legacy_path is not None:
            legacy = pd.read_csv(legacy_path)
            metadata["sourceSha256"] = hashlib.sha256(Path(legacy_path).read_bytes()).hexdigest()
        else:
            from legacy_case_replay import replay_repository
            legacy, metadata = replay_repository(prices, raw, case["ticker"])
        if "ticker" in legacy and not legacy.ticker.eq(case["ticker"]).all():
            raise ValueError("Legacy ticker mismatch")
        audit = legacy_formula_audit(legacy)
        legacy_dates = pd.to_datetime(legacy.datetime, utc=True).dt.strftime("%Y-%m-%d")
        view = legacy.loc[legacy_dates.between(protocol["analysisStart"], protocol["analysisEnd"])].copy()
        view["date"] = legacy_dates.loc[view.index]
        columns = [name for name in ["date", "final_score", "trade_signal", "delta_inventory", "cumulative_inventory", "model_flow_pressure_pct"] if name in view]
        result["legacy"] = {**audit, "rowsInAnalysisWindow": len(view), "samePriceInputsVerified": False,
                            **metadata,
                            "series": records(view[columns])}
        if metadata.get("samePriceInputsVerified"):
            paired = selected.merge(view[["date", "trade_signal", "delta_inventory"]], on="date", validate="one_to_one")
            eligible = paired.sessionComplete & paired.delta_inventory.notna()
            result["comparison"] = {"status": "descriptive_only", "pairedSessions": int(eligible.sum()),
                "zeroLegacyDeltaWithNonzeroSampledNet": int((eligible & paired.delta_inventory.abs().le(.01) & paired.sampledLargeNetUsd.abs().gt(.01)).sum()),
                "meaning": "Zero modeled share change can reflect an unconfirmed trade signal, not absent sampled trading. This is not a predictive-accuracy comparison."}
    if forward_legacy:
        from legacy_forward_replay import replay_forward
        forward, metadata = replay_forward(prices, raw, case["ticker"])
        dates = pd.to_datetime(forward.datetime, utc=True).dt.strftime("%Y-%m-%d")
        view = forward.loc[dates.between(protocol["analysisStart"], protocol["analysisEnd"])].copy()
        view["date"] = dates.loc[view.index]
        counts = {key: int(value) for key, value in view.decisionStatus.value_counts().items()}
        available = counts.get("available", 0)
        result["legacyForward"] = {**metadata,
            "status": "available" if available == len(view) else "partial" if available else "unavailable",
            "analysisDecisionCounts": counts, "analysisSessions": len(view),
            "arithmeticAudit": legacy_formula_audit(forward),
            "series": records(view)}
    return result


def build_pilot(protocol_path, root, legacy_paths=None, replay_legacy=False, reference_intc_flow_dir=None, forward_legacy=False):
    protocol_path = Path(protocol_path)
    protocol = json.loads(protocol_path.read_text())
    if protocol.get("schema") != "flow-case-protocol-v1" or protocol.get("evaluationStatus") != "descriptive_case_study_not_out_of_sample":
        raise ValueError("Unsupported case protocol")
    if protocol["collectionStart"] >= protocol["analysisStart"] or protocol["analysisStart"] > protocol["analysisEnd"]:
        raise ValueError("Invalid case window")
    if protocol.get("priceResponseBars") != 5 or protocol.get("modelPressureWindows") != [5, 20]:
        raise ValueError("This pilot implements only frozen 5/20-session definitions")
    if protocol.get("thresholdsUsd") != {"super": 500000, "large": 100000, "mid": 20000}:
        raise ValueError("Unsupported threshold contract")
    cases = protocol["primaryCases"]
    if [c["ticker"] for c in cases] != ["INTC", "TSLA"]:
        raise ValueError("Keep the approved INTC / TSLA primary cases")
    return {
        "schema": "flow-case-pilot-v1", "protocol": protocol,
        "protocolSha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        "generatedAt": datetime.now(timezone.utc).isoformat(), "isLive": False, "holdings": None,
        "productionEligible": False,
        "formulas": FORMULAS,
        "cases": [build_case(c, protocol, Path(root)/c["ticker"], (legacy_paths or {}).get(c["ticker"]), replay_legacy,
                             reference_intc_flow_dir if c["ticker"] == "INTC" else None, forward_legacy) for c in cases],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--protocol", default=str(Path(__file__).resolve().parents[1]/"flow_case_protocol.json"))
    p.add_argument("--input-root", required=True)
    p.add_argument("--legacy-intc")
    p.add_argument("--legacy-tsla")
    p.add_argument("--replay-repository", action="store_true", help="Offline full-sample legacy diagnostic; not a predictive backtest")
    p.add_argument("--forward-repository", action="store_true", help="Separate prefix-only endpoint diagnostic; not unseen/vintage-verified performance")
    p.add_argument("--reference-intc-flow-dir", help="More-complete stored INTC snapshots for a sampling-sensitivity check")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    data = build_pilot(a.protocol, a.input_root, {k: v for k, v in [("INTC", a.legacy_intc), ("TSLA", a.legacy_tsla)] if v}, a.replay_repository, a.reference_intc_flow_dir, a.forward_repository)
    destination = Path(a.output)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, delete=False) as handle:
        json.dump(data, handle, allow_nan=False)
        temporary = handle.name
    os.replace(temporary, destination)
    print(json.dumps({"protocol": data["protocol"]["id"], "cases": [{"ticker": c["ticker"], "status": c["status"], "coverage": c.get("coverage")} for c in data["cases"]]}))


if __name__ == "__main__":
    main()
