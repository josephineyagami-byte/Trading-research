"""Standalone Plotly diagnostic preview, following the repository's HTML plots."""

import argparse
from html import escape
import json
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots


def label(en, zh, tag="span"):
    return f'<{tag} data-en="{escape(en, quote=True)}" data-zh="{escape(zh, quote=True)}">{escape(en)}</{tag}>'


def check_preview_contract(data):
    from urllib.parse import urlsplit
    policy = data["protocol"].get("flowSample", {})
    if (data.get("schema") != "flow-case-pilot-v1" or policy.get("kind") != "checksum_prefix"
            or policy.get("prefix") != "0" or policy.get("fullMarketExtrapolation") is not False
            or [c["ticker"] for c in data["cases"]] != ["INTC", "TSLA"]):
        raise ValueError("This preview is scoped to the fixed checksum-prefix-0 pilot")
    for case in data["cases"]:
        for event in case["events"]:
            url = urlsplit(event["sourceUrl"])
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("Event sources require plain HTTPS links")


def figure(case):
    rows = case.get("series", [])
    if not rows:
        return ""
    x = [r["date"] for r in rows]
    legacy = case.get("legacy", {}).get("series", [])
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=.035,
                        row_heights=[.43, .19, .21, .17])
    fig.add_trace(go.Candlestick(x=x, open=[r["open"] for r in rows], high=[r["high"] for r in rows],
                                low=[r["low"] for r in rows], close=[r["close"] for r in rows],
                                increasing_line_color="#13b981", decreasing_line_color="#ef5b66",
                                hovertext=[f"O {r['open']:.2f} / H {r['high']:.2f} / L {r['low']:.2f} / C {r['close']:.2f}" for r in rows], hoverinfo="text",
                                name="Price (USD)", showlegend=False), row=1, col=1)
    amounts = [r["sampledLargeNetUsd"] if r["sessionComplete"] else None for r in rows]
    fig.add_trace(go.Bar(x=x, y=amounts, name="Sampled large net (USD)",
                        marker_color=["#13b981" if (v or 0) >= 0 else "#ef5b66" for v in amounts], showlegend=False), row=2, col=1)
    for field, name, color in [("pressure5", "5-session pressure", "#21c6c9"), ("pressure20", "20-session pressure", "#e4b44e")]:
        fig.add_trace(go.Scatter(x=x, y=[r[field]*100 if r[field] is not None else None for r in rows],
                                name=name, mode="lines", connectgaps=False, line={"color":color,"width":2}), row=3, col=1)
    fig.add_trace(go.Scatter(x=[r["date"] for r in legacy], y=[r.get("model_flow_pressure_pct") for r in legacy],
                            name="Legacy modeled share pressure", mode="lines", connectgaps=False,
                            line={"color":"#b0a3e7","width":1.6}), row=4, col=1)
    for n, title in enumerate(["Price (USD)", "Sampled net (USD)", "Flow pressure (%)", "Legacy pressure (%)"], 1):
        fig.update_yaxes(title_text=title, row=n, col=1, zeroline=True, zerolinecolor="#52606b", fixedrange=False)
    fig.update_xaxes(rangeslider_visible=False, tickformat="%Y-%m-%d", gridcolor="#293138")
    fig.update_xaxes(rangeslider={"visible":True,"thickness":.065}, row=4, col=1)
    fig.update_layout(height=790, template="plotly_dark", paper_bgcolor="#11171c", plot_bgcolor="#11171c",
                      font={"family":"Arial, sans-serif","size":12,"color":"#dbe2e7"},
                      margin={"l":75,"r":28,"t":58,"b":45}, hovermode="x unified", dragmode="pan",
                      legend={"orientation":"h","y":1.08,"x":0}, uirevision=case["ticker"])
    for event in case["events"]:
        fig.add_vline(x=event["publicationDate"], line_dash="dot", line_color="#e4b44e", line_width=1)
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=f"chart-{case['ticker']}",
                       config={"responsive":True,"scrollZoom":True,"displaylogo":False})


def render(data):
    check_preview_contract(data)
    from plotly.offline import get_plotlyjs
    p = data["protocol"]
    sections = []
    states = {
        "positive_pressure_price_rising": ("Positive pressure / price rising", "正向压力且价格上涨"),
        "negative_pressure_price_falling": ("Negative pressure / price falling", "负向压力且价格下跌"),
        "negative_pressure_price_resilient_candidate": ("Negative pressure / price rising (candidate)", "负向压力但价格上涨（待核实）"),
        "positive_pressure_price_weak_candidate": ("Positive pressure / price falling (candidate)", "正向压力但价格下跌（待核实）"),
        "mixed": ("Mixed", "混合"), "data_unavailable": ("Data unavailable", "数据不足"),
    }
    for case in data["cases"]:
        coverage, audit, legacy = case.get("coverage", {}), case.get("timeframeAudit", {}), case.get("legacy", {})
        n, complete = coverage.get("priceSessions", 0), coverage.get("completeFlowSessions", 0)
        rows = "".join(f'<tr><td>{label(*states[k])}</td><td>{v}</td></tr>' for k,v in case.get("stateCounts", {}).items())
        events = "".join(f'<p>{escape(e["date"])} / <a href="{escape(e["sourceUrl"],quote=True)}" rel="noreferrer">{escape(e["label"])}</a></p>' for e in case["events"])
        gaps = ", ".join(coverage.get("missingDates", [])+coverage.get("partialDates", [])) or "None"
        question_zh = "政府协议前后，样本大额成交压力与价格反应如何变化？" if case["ticker"] == "INTC" else "当负向成交压力与上涨价格背离时，模型能否保留冲突而不机械判定做空？"
        status_zh = {"available":"样本可用", "partial":"样本不完整", "unavailable":"数据不足"}[case["status"]]
        audit_status = audit.get('status','unavailable')
        legacy_status = legacy.get('status','unavailable')
        status_map = {"pass":"通过", "mismatch":"不一致", "unavailable":"暂无结果"}
        section = f'''<section><div class="section-heading"><h2>{case['ticker']}</h2>{label(case['status'],status_zh)}</div>
<p class="question">{label(case['question'],question_zh)}</p>
<dl><div><dt data-en="Complete 5m sample sessions" data-zh="五分钟样本完整交易日">Complete 5m sample sessions</dt><dd>{complete}/{n}</dd></div>
<div><dt data-en="5m → 1h → 1d amount identity" data-zh="五分钟至小时至日线金额对账">5m → 1h → 1d amount identity</dt><dd>{label(audit_status,status_map[audit_status])}</dd></div>
<div><dt data-en="Legacy formula arithmetic" data-zh="旧版公式算术检查">Legacy formula arithmetic</dt><dd>{label(legacy_status,status_map[legacy_status])}</dd></div></dl>
{figure(case) if case.get('series') else '<p class="warning">No validated flow snapshot is available. Missing observations are not zero.</p>'}
{events}<p class="muted" data-en="Different units: the legacy panel is modeled share pressure; the new panels use sampled USD notional. Their levels are not interchangeable. No trading-performance result is claimed." data-zh="单位不同：旧版是模拟股份压力，新版按样本美元成交额计算，数值不可直接互换。本页不宣称交易绩效。">Different units: the legacy panel is modeled share pressure; the new panels use sampled USD notional. Their levels are not interchangeable. No trading-performance result is claimed.</p>
<p class="muted" data-en="Legacy HMM fitting and reliability use the full sample. Benchmark, short-volume and dark-pool context are absent in this offline replay. This is not an exact reproduction of the case-study screenshots." data-zh="本次旧版诊断采用全样本 HMM 与可靠度计算；未接入基准、做空成交量及暗池背景，不是案例截图的精确复现。">Legacy HMM fitting and reliability use the full sample. Benchmark, short-volume and dark-pool context are absent in this offline replay. This is not an exact reproduction of the case-study screenshots.</p>
<details><summary data-en="Descriptive states and source evidence" data-zh="描述性状态与来源依据">Descriptive states and source evidence</summary>
<table><thead><tr><th>{label('State','描述性状态')}</th><th>{label('Sessions','交易日数')}</th></tr></thead><tbody>{rows}</tbody></table><p>Missing / partial dates: {escape(gaps)}</p>
<p>Price SHA256: <code>{escape(case.get('priceSha256','unavailable'))}</code></p><p>Flow fingerprint: <code>{escape(case.get('flowFingerprint','unavailable'))}</code></p>
<p>Price source: {escape(case.get('priceSource','unavailable'))}; adjusted: {escape(str(case.get('priceAdjusted')))}</p>
<p>Legacy context: {escape(legacy.get('context',legacy.get('reason','unavailable')))}</p>
<p>Aggregation source: {escape(audit.get('basis','unavailable'))}</p><p>Independent tape verification: false</p></details></section>'''
        sections.append(section)
    title = "INTC / TSLA Flow Cases"
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#0c1013;color:#dbe2e7;font:15px/1.6 Arial,sans-serif}}main{{max-width:1380px;margin:auto;padding:24px}}header{{display:flex;justify-content:space-between;align-items:center;gap:16px}}h1{{font-size:25px;margin:0}}h2{{font-size:22px;margin:0}}h3{{font-size:17px}}button{{background:#172127;color:#dbe2e7;border:1px solid #46535c;border-radius:4px;padding:7px 12px;cursor:pointer}}button[aria-pressed=true]{{color:#21c6c9;border-color:#21c6c9}}section{{border-top:1px solid #34414a;margin-top:28px;padding-top:20px}}.section-heading{{display:flex;align-items:center;justify-content:space-between}}.section-heading span,.muted,dt{{color:#9aa8b2}}.warning{{padding:14px 0;border-block:1px solid #8d742b;color:#edc76c}}.question{{max-width:950px}}dl{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin:20px 0}}dd{{font-size:20px;margin:6px 0;font-variant-numeric:tabular-nums}}dt{{font-size:13px}}a{{color:#52cbd4}}details{{padding:15px 0}}summary{{cursor:pointer}}table{{border-collapse:collapse;width:100%;margin:12px 0}}td,th{{text-align:left;padding:9px;border-bottom:1px solid #293138}}code{{overflow-wrap:anywhere}}.plotly-graph-div{{width:100%}}@media(max-width:650px){{main{{padding:16px 10px}}header{{align-items:flex-start}}h1{{font-size:21px}}dl{{grid-template-columns:1fr;gap:10px}}dl>div{{display:flex;justify-content:space-between;gap:12px}}dd{{font-size:17px;margin:0}}dt{{max-width:70%}}}}</style>
<script>{get_plotlyjs()}</script></head><body><main><header><h1 data-en="{title}" data-zh="INTC / TSLA 资金流案例">{title}</h1><div><button type="button" data-locale="en" aria-pressed="true">EN</button> <button type="button" data-locale="zh" aria-pressed="false">中文</button></div></header>
<p>{escape(p['analysisStart'])} / {escape(p['analysisEnd'])}</p>
<p class="warning" data-en="Historical case diagnostic. Parameters were frozen for this pilot, but the window was selected after reading the case studies. This is not out-of-sample validation, verified institutional holdings or live market data." data-zh="历史案例诊断。本轮参数固定，但窗口在阅读案例后选定，不属于未见数据验证，也不代表真实机构持仓或实时行情。">Historical case diagnostic. Parameters were frozen for this pilot, but the window was selected after reading the case studies. This is not out-of-sample validation, verified institutional holdings or live market data.</p>
<p class="warning" data-en="Both tickers use the same checksum-prefix-0 subset (nominally 1/16). Direction compares selected trades, not full-tape neighbors. Representativeness is unverified; amounts are not extrapolated to the full market." data-zh="两只股票均使用校验和前缀 0 的子样本，名义比例约 1/16。方向比较的是所选样本成交，不是全量相邻成交。代表性尚未验证，金额不外推为全市场资金。">Both tickers use the same checksum-prefix-0 subset (nominally 1/16). Direction compares selected trades, not full-tape neighbors. Representativeness is unverified; amounts are not extrapolated to the full market.</p>
{''.join(sections)}<section><h2 data-en="Formula version remains unresolved" data-zh="公式版本仍需确认">Formula version remains unresolved</h2>
<p data-en="Slide 3 uses continuous model bias. The repository uses long / short / otherwise direction. This preview preserves the repository calculation; it does not silently replace it with the slide formula." data-zh="第 3 页使用连续模型倾向，仓库按 long / short / 其他状态确定方向。本页保留仓库算法，没有悄悄换成幻灯片公式。">Slide 3 uses continuous model bias. The repository uses long / short / otherwise direction. This preview preserves the repository calculation; it does not silently replace it with the slide formula.</p>
<p data-en="RGTI and BBAI: not run. Unusual trading is a hypothesis to test, not an established manipulation label." data-zh="RGTI、BBAI：尚未运行。异常交易是待检验假设，不能认定存在操纵。">RGTI and BBAI: not run. Unusual trading is a hypothesis to test, not an established manipulation label.</p>
<details><summary>Protocol and reproducibility</summary><p>Protocol SHA256: <code>{escape(data['protocolSha256'])}</code></p><ul>{''.join('<li>'+escape(t)+'</li>' for t in p['limitations'])}</ul></details></section>
</main><script>document.querySelectorAll('[data-locale]').forEach(b=>b.addEventListener('click',()=>{{const locale=b.dataset.locale;document.documentElement.lang=locale==='zh'?'zh-CN':'en';document.querySelectorAll('[data-en]').forEach(e=>e.textContent=e.dataset[locale]);document.querySelectorAll('[data-locale]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));const titles=locale==='zh'?['价格（美元）','样本净额（美元）','资金压力（%）','旧版压力（%）']:['Price (USD)','Sampled net (USD)','Flow pressure (%)','Legacy pressure (%)'];const names=locale==='zh'?['价格','样本大单净额','五日压力','二十日压力','旧版模拟股份压力']:['Price (USD)','Sampled large net (USD)','5-session pressure','20-session pressure','Legacy modeled share pressure'];document.querySelectorAll('.plotly-graph-div').forEach(g=>{{const update={{}};titles.forEach((t,i)=>update['yaxis'+(i?i+1:'')+'.title.text']=t);Plotly.relayout(g,update);Plotly.restyle(g,{{name:names}},[0,1,2,3,4]);}});}}));</script></body></html>'''


def export_static(data, destination):
    check_preview_contract(data)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from datetime import datetime
    import numpy as np

    fig, axes = plt.subplots(4, 2, figsize=(15, 10), sharex="col", gridspec_kw={"height_ratios":[2.2,1,1.2,1]})
    for column, case in enumerate(data["cases"]):
        rows = case.get("series", [])
        if not rows:
            axes[0,column].text(.5,.5,"Data unavailable",transform=axes[0,column].transAxes,ha="center")
            continue
        dates = [datetime.fromisoformat(r["date"]) for r in rows]
        axes[0,column].plot(dates,[r["close"] for r in rows],color="#263742",linewidth=1.7)
        axes[0,column].set_title(case["ticker"]+" | daily close and sampled pressure",fontsize=13,loc="left")
        amounts = [r["sampledLargeNetUsd"]/1e6 if r["sessionComplete"] and r["sampledLargeNetUsd"] is not None else np.nan for r in rows]
        axes[1,column].bar(dates,amounts,color=["#079d77" if v>=0 else "#df5363" for v in amounts],width=1.1)
        for field, name, color in [("pressure5","5 sessions","#089ba6"),("pressure20","20 sessions","#b77a11")]:
            values = [r[field]*100 if r[field] is not None else np.nan for r in rows]
            axes[2,column].plot(dates,values,label=name,color=color,linewidth=1.4)
        axes[2,column].legend(loc="upper left",fontsize=8,frameon=False,ncol=2)
        legacy = case.get("legacy",{}).get("series",[])
        axes[3,column].plot([datetime.fromisoformat(r["date"]) for r in legacy],
                           [r.get("model_flow_pressure_pct") if r.get("model_flow_pressure_pct") is not None else np.nan for r in legacy],
                           color="#8066ac",linewidth=1.4)
        for row, title in enumerate(["Close (USD)","Sampled net (USD M)","USD pressure (%)","Legacy share pressure (%)"]):
            ax = axes[row,column]
            ax.set_ylabel(title,fontsize=9)
            ax.tick_params(labelsize=8)
            ax.grid(True,color="#e0e5e8",linewidth=.6)
            ax.spines[["top","right"]].set_visible(False)
            if row:
                ax.axhline(0,color="#98a3ac",linewidth=.7)
        axes[3,column].xaxis.set_major_locator(mdates.MonthLocator())
        axes[3,column].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        for event in case["events"]:
            axes[0,column].axvline(datetime.fromisoformat(event["publicationDate"]),color="#b77a11",linestyle=":",linewidth=1)
    fig.suptitle("INTC / TSLA: historical sampled-flow pilot",fontsize=17,x=.07,ha="left")
    counts = "; ".join(c["ticker"]+" "+str(c.get("coverage",{}).get("completeFlowSessions",0))+"/"+str(c.get("coverage",{}).get("priceSessions",0)) for c in data["cases"])
    fig.text(.07,.925,data["protocol"]["analysisStart"]+" to "+data["protocol"]["analysisEnd"]+" | complete 5m sample sessions: "+counts+" | not out-of-sample validation",fontsize=10)
    fig.text(.07,.045,"Both tickers: checksum-prefix-0 subset, nominally 1/16. Direction uses selected trades; no full-market extrapolation.",fontsize=9)
    fig.text(.07,.025,"Legacy: modeled share pressure, full-sample HMM, external context absent. New flow: sampled USD notional. Neither is observed institutional holdings.",fontsize=9)
    fig.subplots_adjust(left=.075,right=.975,top=.88,bottom=.105,hspace=.13,wspace=.24)
    fig.savefig(destination,dpi=160,facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--png", help="Optional offline static figure; does not verify browser rendering")
    a = p.parse_args()
    data = json.loads(Path(a.input).read_text())
    if data.get("schema") != "flow-case-pilot-v1":
        raise SystemExit("Unsupported case snapshot")
    Path(a.output).write_text(render(data), encoding="utf-8")
    if a.png:
        export_static(data, a.png)
