"""
plot_inst_flow.py — 交互式图表：K线 + 模型预测的机构净流入/流出
"""

import argparse
import json
import sys

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def build_chart(df: pd.DataFrame, ticker: str, interval: str) -> go.Figure:
    has_raw = "raw_score" in df.columns and df["raw_score"].notna().any()
    has_final = "final_score" in df.columns and df["final_score"].notna().any()
    has_inv = "cumulative_inventory" in df.columns and df["cumulative_inventory"].notna().any()

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.5, 0.25, 0.25],
        vertical_spacing=0.04,
        subplot_titles=(
            f"{ticker} ({interval}) — Price",
            "raw_score (dotted) vs final_score (solid)",
            "Cumulative estimated institutional inventory (heuristic)",
        ),
    )

    fig.add_trace(go.Candlestick(
        x=df["datetime"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="Price",
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
    ), row=1, col=1)

    if has_raw:
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=df["raw_score"], name="raw_score",
            line=dict(color="#888888", width=1, dash="dot"),
            hovertemplate="raw_score: %{y:.3f}<extra></extra>",
        ), row=2, col=1)

    if has_final:
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=df["final_score"], name="final_score",
            line=dict(color="#1f77b4", width=1.5),
            hovertemplate="final_score: %{y:.3f}<extra></extra>",
        ), row=2, col=1)

    if has_inv:
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=df["cumulative_inventory"],
            name="cumulative_inventory",
            line=dict(color="#9467bd", width=1.5),
            fill="tozeroy", fillcolor="rgba(148,103,189,0.15)",
            hovertemplate="cum. inventory: %{y:,.0f} sh (est.)<extra></extra>",
        ), row=3, col=1)

    fig.update_layout(
        title=f"{ticker} {interval} — Model-Predicted Institutional Flow vs Price",
        hoversubplots="axis",
        hovermode="x",
        height=900,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_rangeslider_visible=False,
    )

    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=0.8, row=2, col=1)
    for v in [0.35, -0.35]:
        fig.add_hline(y=v, line_dash="dot",
                      line_color="rgba(150,150,150,0.4)", line_width=0.6, row=2, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=0.8, row=3, col=1)

    fig.update_xaxes(
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikecolor="rgba(0,0,0,0.3)", spikethickness=1,
    )
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    fig.update_yaxes(title_text="Score [-1,1]", row=2, col=1)
    fig.update_yaxes(title_text="Est. shares", row=3, col=1)
    fig.update_xaxes(title_text="Date", row=3, col=1)

    return fig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--interval", default=None)
    args = parser.parse_args()

    df = pd.read_csv(args.file, parse_dates=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    print(f"[OK] Loaded {len(df)} rows from {args.file}")

    required = {"datetime", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        sys.exit(f"[FATAL] Missing required columns: {missing}")

    ticker = args.ticker
    interval = args.interval
    if not ticker or not interval:
        import re
        from pathlib import Path
        m = re.match(r"([A-Z]+)_(\w+)_", Path(args.file).name)
        if m:
            ticker = ticker or m.group(1)
            interval = interval or m.group(2)
    ticker = ticker or "UNKNOWN"
    interval = interval or "?"

    fig = build_chart(df, ticker, interval)

    ts_ms     = [int(t.timestamp() * 1000) for t in df["datetime"]]
    inv_col   = df.get("cumulative_inventory", pd.Series([None]*len(df)))
    score_col = df.get("final_score", pd.Series([None]*len(df)))
    inv_vals   = [None if pd.isna(v) else round(float(v))    for v in inv_col]
    score_vals = [None if pd.isna(v) else round(float(v), 4) for v in score_col]
    high_vals  = [None if pd.isna(v) else round(float(v), 4) for v in df["high"]]
    low_vals   = [None if pd.isna(v) else round(float(v), 4) for v in df["low"]]

    data_js = (
        f"var TS={json.dumps(ts_ms)};\n"
        f"var INV={json.dumps(inv_vals)};\n"
        f"var SCORE={json.dumps(score_vals)};\n"
        f"var HIGH={json.dumps(high_vals)};\n"
        f"var LOW={json.dumps(low_vals)};"
    )

    post_script = data_js + r"""
var gd = document.getElementById('{plot_id}');
var _syncing = false;

function rangeOk(lo, hi) {
    return lo !== undefined && hi !== undefined &&
           lo !== null && hi !== null &&
           isFinite(lo) && isFinite(hi);
}

function visiblePriceRange(t0ms, t1ms, pad) {
    var lo = 1e18, hi = -1e18;
    for (var i = 0; i < TS.length; i++) {
        if (TS[i] >= t0ms && TS[i] <= t1ms) {
            if (HIGH[i] !== null && HIGH[i] > hi) hi = HIGH[i];
            if (LOW[i]  !== null && LOW[i]  < lo) lo = LOW[i];
        }
    }
    if (lo === 1e18) return null;
    var span = (hi - lo) || hi * 0.02 || 1;
    return [lo - span * pad, hi + span * pad];
}

function visibleYRange(vals, t0ms, t1ms, pad) {
    var lo = 1e18, hi = -1e18;
    for (var i = 0; i < TS.length; i++) {
        if (TS[i] >= t0ms && TS[i] <= t1ms && vals[i] !== null) {
            if (vals[i] < lo) lo = vals[i];
            if (vals[i] > hi) hi = vals[i];
        }
    }
    if (lo === 1e18) return null;
    var span = (hi - lo) || Math.abs(hi) * 0.1 || 1;
    return [lo - span * pad, hi + span * pad];
}

gd.on('plotly_relayout', function(eventData) {
    if (_syncing) return;
    var update = {};
    var changed = false;
    var r0 = null, r1 = null, isReset = false;

    var axKeys = ['xaxis', 'xaxis2', 'xaxis3'];
    for (var k = 0; k < axKeys.length; k++) {
        var ax = axKeys[k];
        if (eventData[ax + '.range[0]'] !== undefined) {
            r0 = eventData[ax + '.range[0]'];
            r1 = eventData[ax + '.range[1]'];
        }
        if (eventData[ax + '.autorange'] === true) { isReset = true; }
    }

    if (isReset) {
        update = {
            'yaxis.autorange':  true,
            'yaxis2.autorange': true,
            'yaxis3.autorange': true
        };
        changed = true;
    } else if (r0 !== null && r1 !== null) {
        var t0ms = new Date(r0).getTime();
        var t1ms = new Date(r1).getTime();

        var pr = visiblePriceRange(t0ms, t1ms, 0.02);
        if (pr) { update['yaxis.range'] = [pr[0], pr[1]]; changed = true; }

        var sr = visibleYRange(SCORE, t0ms, t1ms, 0.15);
        if (sr) { update['yaxis2.range'] = [sr[0], sr[1]]; changed = true; }

        var ir = visibleYRange(INV, t0ms, t1ms, 0.15);
        if (ir) { update['yaxis3.range'] = [ir[0], ir[1]]; changed = true; }
    }

    if (changed) {
        _syncing = true;
        Plotly.relayout(gd, update).then(function() { _syncing = false; });
    }
});
"""

    out_path = args.file.replace(".csv", "_chart.html")
    fig.write_html(out_path, post_script=post_script)
    print(f"[SAVED] {out_path}")
    print(f"[OPEN] open {out_path}")


if __name__ == "__main__":
    main()
