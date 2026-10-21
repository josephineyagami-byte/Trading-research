"use client";

import { useEffect, useRef, useState } from "react";
import { CandlestickSeries, HistogramSeries, LineSeries, ColorType, createChart, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { Maximize2, SkipForward } from "lucide-react";
import { useI18n } from "@/components/i18n/LocaleProvider";
import { useTheme } from "@/hooks/useTheme";
import { getChartColors } from "@/lib/chartTheme";
import { flowLineSegments, type FlowSnapshot } from "@/lib/flow-model";

export default function FlowModelChart({snapshot}: {snapshot: FlowSnapshot}) {
  const host = useRef<HTMLDivElement>(null), chart = useRef<IChartApi | null>(null);
  const {locale} = useI18n(), {resolvedTheme} = useTheme();
  const zh = locale === "zh-CN";
  const [range, setRange] = useState(126), [position, setPosition] = useState(1000);
  const [hover, setHover] = useState(snapshot.series.at(-1)!);
  const current = snapshot.series.find(row => row.date === hover.date) ?? snapshot.series.at(-1)!;
  useEffect(() => {
    if (!host.current) return;
    const colors = getChartColors(resolvedTheme === "dark");
    const api = createChart(host.current, {autoSize: true, layout: {background: {type: ColorType.Solid, color: colors.background}, textColor: colors.text},
      grid: {vertLines: {color: colors.grid}, horzLines: {color: colors.grid}},
      localization: {locale: zh ? "zh-CN" : "en-US"},
      rightPriceScale: {minimumWidth: 85, borderColor: colors.border}, timeScale: {borderColor: colors.border}});
    chart.current = api;
    const time = (date: string) => Math.floor(Date.parse(date)/1000) as UTCTimestamp;
    const candles = api.addSeries(CandlestickSeries, {upColor: "#13a980", downColor: "#e65068", borderVisible: false, wickUpColor: "#13a980", wickDownColor: "#e65068"}, 0);
    candles.setData(snapshot.series.map(row => ({time: time(row.date), open: row.open, high: row.high, low: row.low, close: row.close})));
    const flow = api.addSeries(HistogramSeries, {title: zh ? "样本差额 USD" : "Sample net USD", priceFormat: {type: "volume"}}, 1);
    flow.setData(snapshot.series.map(row => row.sessionComplete && row.sampledLargeNetUsd !== null
      ? {time: time(row.date), value: row.sampledLargeNetUsd, color: row.sampledLargeNetUsd >= 0 ? "#13a980" : "#e65068"} : {time: time(row.date)}));
    for (const [field, color, title] of [["pressure5", "#48a1ec", "5D"], ["pressure20", "#dca825", "20D"]] as const) {
      for (const segment of flowLineSegments(snapshot.series, field)) {
        const line = api.addSeries(LineSeries, {color, lineWidth: 2, title, lastValueVisible: false, priceLineVisible: false,
          priceFormat: {type: "custom", minMove: .0001, formatter: (value: number) => `${(value*100).toFixed(1)}%`}}, 2);
        line.setData(segment.map(row => ({time: time(row.date), value: row.value})));
      }
    }
    api.panes()[0].setHeight(310); api.panes()[1].setHeight(140); api.panes()[2].setHeight(150);
    api.subscribeCrosshairMove(event => {
      const row = snapshot.series.find(r => time(r.date) === event.time);
      setHover(row ?? snapshot.series.at(-1)!);
    });
    const scale = api.timeScale();
    scale.setVisibleLogicalRange({from: Math.max(0, snapshot.series.length-126), to: snapshot.series.length-1});
    return () => {api.remove(); chart.current = null;};
  }, [snapshot, resolvedTheme, zh]);
  useEffect(() => {
    const end = range-1 + Math.max(0, snapshot.series.length-range) * position/1000;
    chart.current?.timeScale().setVisibleLogicalRange({from: Math.max(0, end-range+1), to: end});
  }, [range, position, snapshot, resolvedTheme, zh]);
  const pressure = (n: number | null) => n === null ? "—" : `${(n*100).toFixed(2)}%`;
  return <div className="border-y border-border">
    <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 py-3">
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs tabular-nums"><strong>{snapshot.ticker}</strong><span>{current.date}</span><span>${current.close.toFixed(2)}</span><span className="text-sky-500">5D {pressure(current.pressure5)}</span><span className="text-amber-500">20D {pressure(current.pressure20)}</span></div>
      <div className="flex items-center gap-1" aria-label={zh ? "日期范围" : "Date range"}>{[[63,"3M"], [126,"6M"], [252,"1Y"], [snapshot.series.length,"All"]].map(([value,label]) => <button key={String(label)} type="button" className={`h-8 px-3 text-xs ${range === value ? "bg-surface-hover text-primary" : "text-muted"}`} aria-pressed={range === value} onClick={() => {setRange(Number(value)); setPosition(1000);}}>{label === "All" && zh ? "全部" : label}</button>)}</div>
    </div>
    <div ref={host} className="h-[600px] w-full" aria-label={zh ? "股价、样本大额成交差额与资金压力" : "Price, sampled large-trade net notional and flow pressure"} />
    <div className="flex items-center gap-3 border-t border-border py-3">
      <button type="button" className="grid h-8 w-8 shrink-0 place-items-center" aria-label={zh ? "显示全部" : "Fit all"} title={zh ? "显示全部" : "Fit all"} onClick={() => {setRange(snapshot.series.length); setPosition(1000);}}><Maximize2 size={15}/></button>
      <input className="min-w-0 flex-1 accent-teal-500" type="range" min="0" max="1000" value={position} disabled={range >= snapshot.series.length} onChange={e => setPosition(Number(e.target.value))} aria-label={zh ? "历史日期" : "Historical date"}/>
      <button type="button" className="grid h-8 w-8 shrink-0 place-items-center" aria-label={zh ? "最新日期" : "Latest date"} title={zh ? "最新日期" : "Latest date"} onClick={() => setPosition(1000)}><SkipForward size={15}/></button>
    </div>
  </div>;
}
