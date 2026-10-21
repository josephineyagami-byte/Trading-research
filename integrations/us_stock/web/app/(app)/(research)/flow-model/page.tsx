"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { RefreshCw, AlertTriangle } from "lucide-react";
import { useI18n } from "@/components/i18n/LocaleProvider";
import { useRemoteData } from "@/hooks/useRemoteData";
import { parseFlowIndex, parseFlowSnapshot } from "@/lib/flow-model";
import { ResearchWorkspace } from "@/components/research/ResearchWorkspace";
import { DataLoadError } from "@/components/ui/DataLoadError";
import FlowModelChart from "@/components/research/FlowModelChart";

const pct = (n: number) => `${(n*100).toFixed(1)}%`;
export default function FlowModelPage() {return <Suspense fallback={<div className="p-8">Loading…</div>}><Content/></Suspense>;}
function Content() {
  const {locale} = useI18n(), zh = locale === "zh-CN", search = useSearchParams();
  const [selected, setSelected] = useState(search.get("ticker")?.toUpperCase() ?? "");
  const index = useRemoteData("/live-data/flow-model", parseFlowIndex, true);
  const ticker = selected || index.data?.tickers[0] || "";
  const result = useRemoteData(ticker ? `/live-data/flow-model?ticker=${encodeURIComponent(ticker)}` : null, parseFlowSnapshot, true);
  const snapshot = result.data, validation = snapshot?.validation;
  const refresh = () => {index.reload(); result.reload();};
  return <ResearchWorkspace eyebrow="SAMPLED FLOW · WALK-FORWARD" title={zh ? "资金流模型" : "Flow model"}
    description={zh ? "独立成交方向估计与时序验证" : "Independent trade-direction estimates and chronological validation"}
    meta={snapshot ? [{label: zh ? "截至" : "Through", value: snapshot.dataThrough}, {label: zh ? "五分钟样本覆盖" : "5m sample coverage", value: `${snapshot.coverage.completeFlowSessions}/${snapshot.coverage.priceSessions}`, tone: "warning"}] : []}>
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3"><select aria-label={zh ? "股票" : "Ticker"} className="h-9 min-w-32 border border-border bg-page px-3 text-sm" value={ticker} onChange={e => setSelected(e.target.value)}>
        {!index.data?.tickers.length && <option value="">{zh ? "暂无快照" : "No snapshots"}</option>}
        {selected && !index.data?.tickers.includes(selected) && <option value={selected}>{selected}</option>}
        {index.data?.tickers.map(t => <option key={t} value={t}>{t}</option>)}
      </select><span className="text-xs text-amber-500">{zh ? "实验性 · 非实时" : "Experimental · Not live"}</span></div>
      <button aria-label={zh ? "刷新" : "Refresh"} title={zh ? "刷新" : "Refresh"} type="button" className="grid h-9 w-9 place-items-center border border-border" onClick={refresh}><RefreshCw size={15}/></button>
    </div>
    {index.error && <DataLoadError error={index.error} onRetry={refresh}/>}
    {result.error && <DataLoadError error={result.error} onRetry={refresh}/>}
    {(index.loading || result.loading) && <p role="status" className="py-8 text-sm text-muted">{zh ? "正在读取模型快照…" : "Loading model snapshot…"}</p>}
    {!index.loading && !index.error && !ticker && <p className="py-10 text-muted">{zh ? "尚无已发布的模型快照。" : "No model snapshots have been published."}</p>}
    {snapshot && validation && <>
      <div className="mb-5 flex items-start gap-3 border-y border-amber-500/30 py-4 text-sm"><AlertTriangle size={17} className="mt-0.5 shrink-0 text-amber-500"/><p>{zh ? "按样本价格变动估计的大额成交差额，不是真实机构持仓或买卖建议。覆盖率仅表示五分钟样本齐全，不代表全市场逐笔完整。缺失和不完整样本保留为空白。" : "Large-trade imbalance estimated from sampled price changes, not actual institutional holdings or trading advice. Coverage means all five-minute sample buckets are present, not a complete market tape. Missing and partial samples remain unavailable."}</p></div>
      <FlowModelChart snapshot={snapshot}/>
      <section className="mt-7 border-b border-border pb-6">
        <h2 className="mb-4 text-base font-semibold">{zh ? "按时间顺序的样本外验证" : "Chronological out-of-sample replay"}</h2>
        <div className="grid grid-cols-2 gap-5 lg:grid-cols-5">{[
          [zh ? "策略回放收益" : "Strategy replay", pct(validation.totalReturn)],
          [zh ? "同期持有基准" : "Buy-and-hold", pct(validation.benchmarkReturn)],
          [zh ? "最大回撤" : "Max drawdown", pct(validation.maxDrawdown)],
          [zh ? "可用预测覆盖" : "Forecast coverage", `${validation.forecastBars}/${validation.realizedBars}`],
          [zh ? "单边成本" : "One-way cost", `${validation.feeBpsOneWay} bps`],
        ].map(([label,value]) => <div key={label}><p className="text-xs text-muted">{label}</p><p className="mt-2 font-mono text-xl tabular-nums">{value}</p></div>)}</div>
        <p className="mt-5 text-xs leading-6 text-muted">{zh ? `滚动训练 ${validation.trainSize} 根，测试 ${validation.testSize} 根，间隔 ${validation.gap} 根；日终估计，下一交易日开盘执行。缺失预测持有现金。历史数据可得性与复权口径尚未完成时点核验；未计借券费、融资及额外滑点。` : `${validation.trainSize}-bar rolling training, ${validation.testSize}-bar tests, ${validation.gap}-bar gap. Close-of-day estimates execute at the next session open. Missing forecasts hold cash. Historical data availability and adjustment basis are not point-in-time verified; borrow fees, financing and additional slippage are excluded.`}</p>
        <p className="mt-2 text-xs leading-6 text-amber-500">{zh ? "原始逐笔的去重、撤单更正及小数股精度尚未独立核验；当前回放仅用于研究诊断。" : "Raw-trade deduplication, cancel/correction handling and fractional-share precision are not independently verified. This replay is for research diagnostics only."}</p>
      </section>
      <section className="mt-6 overflow-x-auto"><h2 className="mb-3 text-base font-semibold">{zh ? "验证分段" : "Validation folds"}</h2><table className="w-full min-w-[630px] text-left text-xs"><thead className="text-muted"><tr>{["#", zh ? "训练起止" : "Training", zh ? "测试起止" : "Test", zh ? "训练有效数" : "Valid training", zh ? "测试预测数" : "Test forecasts"].map(label => <th className="py-3" key={label}>{label}</th>)}</tr></thead><tbody>{snapshot.folds.map(f => <tr key={f.fold} className="border-t border-border font-mono"><td className="py-3">{f.fold}</td><td>{f.trainStart} / {f.trainEnd}</td><td>{f.testStart} / {f.testEnd}</td><td>{f.trainValid}</td><td>{f.forecastCount}</td></tr>)}</tbody></table></section>
      <details className="mt-6 border-y border-border py-4 text-xs"><summary className="text-amber-500">{zh ? "数据缺口" : "Data gaps"} · {snapshot.coverage.missingDates.length} {zh ? "缺失" : "missing"} · {snapshot.coverage.partialDates.length} {zh ? "不完整" : "partial"}</summary><p className="mt-3 break-words font-mono leading-6">{snapshot.coverage.missingDates.join(" · ") || "—"}</p><p className="mt-2 font-mono">{snapshot.coverage.partialDates.join(" · ") || "—"}</p></details>
    </>}
  </ResearchWorkspace>;
}
