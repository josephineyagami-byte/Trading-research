"""
plot_inst_flow.py — 交互式图表：K线 + 模型预测的机构净流入/流出
"""

import argparse
import json
import sys

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def build_chart(df: pd.DataFrame, ticker: str, interval: str,
                 benchmark_df: pd.DataFrame = None, benchmark_name: str = None) -> go.Figure:
    has_raw = "raw_score" in df.columns and df["raw_score"].notna().any()
    has_final = "final_score" in df.columns and df["final_score"].notna().any()
    has_inv = "cumulative_inventory" in df.columns and df["cumulative_inventory"].notna().any()
    has_signal = "signal" in df.columns

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.5, 0.25, 0.25],
        vertical_spacing=0.04,
        specs=[[{"secondary_y": True}], [{}], [{}]],
        subplot_titles=(
            f"{ticker} ({interval}) — Price" + (f"  vs  {benchmark_name}" if benchmark_df is not None else ""),
            "raw_score (dotted) vs final_score (solid)",
            "Cumulative estimated institutional inventory (heuristic)",
        ),
    )

    fig.add_trace(go.Candlestick(
        x=df["datetime"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="Price",
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
    ), row=1, col=1, secondary_y=False)

    # ── Benchmark overlay (QQQ/SPY) ──────────────────────────────────
    # Plotted on a secondary y-axis as % change from the first bar, so it
    # can be visually compared against price action regardless of the
    # benchmark's absolute price level. This is a macro-trend reference
    # only — per the project's clustering work, SPY/QQQ's own OFI/VWAP/
    # impact features carry near-zero signal (ETF basket pricing
    # suppresses single-stock microstructure), so they're shown here
    # purely as a price/trend backdrop, never as a signal-generation target.
    if benchmark_df is not None and len(benchmark_df) > 0:
        bdf = benchmark_df.sort_values("datetime").reset_index(drop=True)
        base = bdf["close"].iloc[0]
        bench_pct = (bdf["close"] / base - 1) * 100
        fig.add_trace(go.Scatter(
            x=bdf["datetime"], y=bench_pct, name=f"{benchmark_name} (% chg)",
            line=dict(color="#ff9800", width=1.3, dash="dash"),
            hovertemplate=f"{benchmark_name}: " + "%{y:+.2f}%<extra></extra>",
        ), row=1, col=1, secondary_y=True)
        fig.update_yaxes(title_text=f"{benchmark_name} % chg", row=1, col=1,
                          secondary_y=True, showgrid=False)

    # ── Inst. Acc / Inst. Dist markers ───────────────────────────────
    # Two categories only (not 4) — accumulation/distribution, with
    # strong_accumulation/strong_distribution folded into the same
    # marker but shown with higher opacity + larger size, so strength
    # is visually distinguishable without adding marker-shape clutter.
    # Labeled "Inst. Acc" / "Inst. Dist" deliberately, not "Buy"/"Sell" —
    # this reflects detected institutional behavior, not a trade signal
    # (see project discussion: accumulation/distribution is not always
    # the same thing as a buy/sell recommendation).
    if has_signal:
        # Only strong_accumulation/strong_distribution are marked — at 1h
        # granularity, regular accumulation/distribution signals are dense
        # enough (often 60-80% of bars) that markers fully occlude the
        # candlesticks. Strong-only cuts density to a visually usable level
        # and aligns with "these are the higher-confidence calls" anyway.
        acc_mask  = df["signal"] == "strong_accumulation"
        dist_mask = df["signal"] == "strong_distribution"

        if acc_mask.any():
            fig.add_trace(go.Scatter(
                x=df.loc[acc_mask, "datetime"], y=df.loc[acc_mask, "low"] * 0.995,
                mode="markers", name="Inst. Acc",
                marker=dict(symbol="triangle-up", color="#26a69a",
                            size=5, opacity=0.85,
                            line=dict(width=0.4, color="#1b5e20")),
                hovertemplate="Inst. Acc<extra></extra>",
            ), row=1, col=1, secondary_y=False)

        if dist_mask.any():
            fig.add_trace(go.Scatter(
                x=df.loc[dist_mask, "datetime"], y=df.loc[dist_mask, "high"] * 1.005,
                mode="markers", name="Inst. Dist",
                marker=dict(symbol="triangle-down", color="#ef5350",
                            size=5, opacity=0.85,
                            line=dict(width=0.4, color="#7f0000")),
                hovertemplate="Inst. Dist<extra></extra>",
            ), row=1, col=1, secondary_y=False)

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
    parser.add_argument("--benchmark", default=None,
                        help="Path to a benchmark OHLCV CSV (e.g. QQQ or SPY klines) "
                             "to overlay as a % change reference line. Just needs "
                             "datetime/close columns — doesn't need signal columns.")
    parser.add_argument("--benchmark-name", default=None,
                        help="Display name for the benchmark (default: auto-detected from filename)")
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

    benchmark_df = None
    benchmark_name = args.benchmark_name
    if args.benchmark:
        benchmark_df = pd.read_csv(args.benchmark, parse_dates=["datetime"])
        if "close" not in benchmark_df.columns:
            sys.exit(f"[FATAL] Benchmark file missing 'close' column: {args.benchmark}")
        if not benchmark_name:
            import re as _re
            from pathlib import Path as _Path
            bm = _re.match(r"([A-Z]+)_", _Path(args.benchmark).name)
            benchmark_name = bm.group(1) if bm else "Benchmark"
        print(f"[OK] Loaded {len(benchmark_df)} benchmark rows ({benchmark_name}) from {args.benchmark}")

    fig = build_chart(df, ticker, interval, benchmark_df=benchmark_df, benchmark_name=benchmark_name)

    ts_ms     = [int(t.timestamp() * 1000) for t in df["datetime"]]
    inv_col   = df.get("cumulative_inventory", pd.Series([None]*len(df)))
    score_col = df.get("final_score", pd.Series([None]*len(df)))
    raw_col   = df.get("raw_score", pd.Series([None]*len(df)))
    inv_vals   = [None if pd.isna(v) else round(float(v))    for v in inv_col]
    score_vals = [None if pd.isna(v) else round(float(v), 4) for v in score_col]
    raw_vals   = [None if pd.isna(v) else round(float(v), 4) for v in raw_col]
    high_vals  = [None if pd.isna(v) else round(float(v), 4) for v in df["high"]]
    low_vals   = [None if pd.isna(v) else round(float(v), 4) for v in df["low"]]
    open_vals  = [None if pd.isna(v) else round(float(v), 4) for v in df["open"]]
    close_vals = [None if pd.isna(v) else round(float(v), 4) for v in df["close"]]

    data_js = (
        f"var TS={json.dumps(ts_ms)};\n"
        f"var INV={json.dumps(inv_vals)};\n"
        f"var SCORE={json.dumps(score_vals)};\n"
        f"var RAW={json.dumps(raw_vals)};\n"
        f"var HIGH={json.dumps(high_vals)};\n"
        f"var LOW={json.dumps(low_vals)};\n"
        f"var OPEN={json.dumps(open_vals)};\n"
        f"var CLOSE={json.dumps(close_vals)};"
    )

    post_script = data_js + r"""
var gd = document.getElementById('{plot_id}');
var _syncing = false;

// ── Custom unified tooltip overlay ──────────────────────────────
var tooltip = document.createElement('div');
tooltip.style.cssText = [
    'position:absolute','background:rgba(255,255,255,0.95)',
    'border:1px solid #ccc','border-radius:4px','padding:8px 12px',
    'font:12px/1.6 monospace','pointer-events:none',
    'box-shadow:0 2px 8px rgba(0,0,0,0.15)','display:none','z-index:999'
].join(';');
gd.style.position = 'relative';
gd.appendChild(tooltip);

function findIdx(tMs) {
    var best = 0, bestD = Infinity;
    for (var i = 0; i < TS.length; i++) {
        var d = Math.abs(TS[i] - tMs);
        if (d < bestD) { bestD = d; best = i; }
    }
    return best;
}

gd.on('plotly_hover', function(evt) {
    if (!evt.xvals && (!evt.points || !evt.points.length)) return;
    var xval = evt.xvals ? evt.xvals[0] : evt.points[0].x;
    var tMs  = new Date(xval).getTime();
    var i    = findIdx(tMs);

    var dt = new Date(TS[i]);
    var pad = function(n){ return String(n).padStart(2,'0'); };
    var dtStr = dt.getFullYear()+'-'+pad(dt.getMonth()+1)+'-'+pad(dt.getDate())
                +' '+pad(dt.getHours())+':'+pad(dt.getMinutes());

    var lines = ['<b>'+dtStr+'</b>'];
    if (OPEN[i]  !== null) lines.push('O: '+OPEN[i].toFixed(2)+'  H: '+HIGH[i].toFixed(2)+'  L: '+LOW[i].toFixed(2)+'  C: '+CLOSE[i].toFixed(2));
    if (RAW[i]   !== null) lines.push('raw_score:   '+(RAW[i]>=0?'+':'')+RAW[i].toFixed(3));
    if (SCORE[i] !== null) lines.push('final_score: '+(SCORE[i]>=0?'+':'')+SCORE[i].toFixed(3));
    if (INV[i]   !== null) lines.push('cum. inv:    '+INV[i].toLocaleString()+' sh');

    tooltip.innerHTML = lines.join('<br>');
    tooltip.style.display = 'block';

    // Position near cursor but keep inside chart
    var rect = gd.getBoundingClientRect();
    var ex = evt.event ? evt.event.clientX : (evt.points[0].event ? evt.points[0].event.clientX : rect.left+200);
    var ey = evt.event ? evt.event.clientY : (evt.points[0].event ? evt.points[0].event.clientY : rect.top+100);
    var lx = ex - rect.left + 14;
    var ly = ey - rect.top  - 10;
    if (lx + 240 > gd.offsetWidth)  lx = lx - 260;
    if (ly + 120 > gd.offsetHeight) ly = ly - 130;
    tooltip.style.left = lx + 'px';
    tooltip.style.top  = ly + 'px';
});

gd.on('plotly_unhover', function() {
    tooltip.style.display = 'none';
});

// ── Y-axis auto-fit on zoom ──────────────────────────────────────
// NOTE: row 1 has secondary_y=True (for the benchmark overlay), which
// shifts Plotly's y-axis numbering: yaxis=row1 primary, yaxis2=row1
// secondary (benchmark), yaxis3=row2 (score), yaxis4=row3 (inventory).
// This is NOT the same numbering as before the benchmark feature was
// added (used to be yaxis/yaxis2/yaxis3 for rows 1/2/3) — if removing
// the benchmark overlay in the future, this numbering needs to shift back.
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

    var axKeys = ['xaxis', 'xaxis2', 'xaxis3'];  // x-axes unaffected by secondary_y
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
            'yaxis3.autorange': true,
            'yaxis4.autorange': true
        };
        changed = true;
    } else if (r0 !== null && r1 !== null) {
        var t0ms = new Date(r0).getTime();
        var t1ms = new Date(r1).getTime();

        var pr = visiblePriceRange(t0ms, t1ms, 0.02);
        if (pr) { update['yaxis.range'] = [pr[0], pr[1]]; changed = true; }

        var sr = visibleYRange(SCORE, t0ms, t1ms, 0.15);
        if (sr) { update['yaxis3.range'] = [sr[0], sr[1]]; changed = true; }

        var ir = visibleYRange(INV, t0ms, t1ms, 0.15);
        if (ir) { update['yaxis4.range'] = [ir[0], ir[1]]; changed = true; }
    }

    if (changed) {
        _syncing = true;
        Plotly.relayout(gd, update).then(function() { _syncing = false; });
    }
});
"""

    suffix = f"_vs_{benchmark_name}" if benchmark_name else ""
    out_path = args.file.replace(".csv", f"{suffix}_chart.html")
    fig.write_html(out_path, post_script=post_script)
    print(f"[SAVED] {out_path}")
    print(f"[OPEN] open {out_path}")


if __name__ == "__main__":
    main()
