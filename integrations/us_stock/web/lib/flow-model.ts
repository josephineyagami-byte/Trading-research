export interface FlowDay {
  date: string; open: number; high: number; low: number; close: number; volume: number;
  sampledLargeNetUsd: number | null; dailyPressure: number | null;
  pressure5: number | null; pressure20: number | null;
  sessionComplete: boolean; status: "complete" | "partial" | "missing";
}
export interface FlowSnapshot {
  schema: "flow-model-v1"; ticker: string; method: string; generatedAt: string; dataThrough: string; firstDate: string;
  isLive: false; holdings: null;
  coverage: {priceSessions: number; completeFlowSessions: number; missingDates: string[]; partialDates: string[]; calendar: string};
  validation: {folds: number; realizedBars: number; forecastBars: number; forecastCoverage: number;
    feeBpsOneWay: number; totalReturn: number; benchmarkReturn: number; maxDrawdown: number; sharpe: number | null;
    trainSize: number; testSize: number; gap: number; evaluationStatus: string};
  folds: {fold: number; trainStart: string; trainEnd: string; testStart: string; testEnd: string; trainValid: number; forecastCount: number}[];
  series: FlowDay[];
  replay: {date: string; strategyEquity: number; benchmarkEquity: number}[];
}
export const validFlowTicker = (value: string) => /^[A-Z0-9][A-Z0-9.-]{0,11}$/.test(value);
export function flowLineSegments(rows: FlowDay[], field: "pressure5" | "pressure20") {
  const segments: {date: string; value: number}[][] = [];
  let current: {date: string; value: number}[] = [];
  for (const row of rows) {
    const value = row[field];
    if (value === null) { if (current.length) segments.push(current); current = []; }
    else current.push({date: row.date, value});
  }
  if (current.length) segments.push(current);
  return segments;
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid flow snapshot");
  return value as Record<string, unknown>;
}
function number(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error("Invalid flow number");
  return value;
}
function nullable(value: unknown): number | null { return value === null ? null : number(value); }
function date(value: unknown): string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)
    || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value) throw new Error("Invalid flow date");
  return value;
}
function dates(value: unknown): string[] {
  if (!Array.isArray(value) || value.length > 2000) throw new Error("Invalid flow dates");
  return value.map(date);
}
export function parseFlowSnapshot(value: unknown): FlowSnapshot {
  const d = object(value), c = object(d.coverage), v = object(d.validation);
  if (d.schema !== "flow-model-v1" || typeof d.ticker !== "string" || !validFlowTicker(d.ticker)
    || d.method !== "sampled-tick-rule-v1" || d.isLive !== false || d.holdings !== null
    || typeof d.generatedAt !== "string" || !Number.isFinite(Date.parse(d.generatedAt))) throw new Error("Invalid flow schema");
  if (!Array.isArray(d.series) || !d.series.length || d.series.length > 2000 || !Array.isArray(d.folds)
    || d.folds.length > 100 || !Array.isArray(d.replay) || d.replay.length > 2000) throw new Error("Invalid flow arrays");
  const series = d.series.map(raw => {
    const r = object(raw);
    if (!["complete", "partial", "missing"].includes(String(r.status)) || typeof r.sessionComplete !== "boolean"
      || r.sessionComplete !== (r.status === "complete")) throw new Error("Invalid flow coverage");
    const row: FlowDay = {date: date(r.date), open: number(r.open), high: number(r.high), low: number(r.low),
      close: number(r.close), volume: number(r.volume), sampledLargeNetUsd: nullable(r.sampledLargeNetUsd),
      dailyPressure: nullable(r.dailyPressure), pressure5: nullable(r.pressure5), pressure20: nullable(r.pressure20),
      sessionComplete: r.sessionComplete, status: r.status as FlowDay["status"]};
    if (Math.min(row.open, row.high, row.low, row.close) <= 0 || row.volume < 0
      || row.high < Math.max(row.open, row.close) || row.low > Math.min(row.open, row.close)
      || [row.dailyPressure, row.pressure5, row.pressure20].some(n => n !== null && Math.abs(n) > 1.000001)
      || !row.sessionComplete && row.dailyPressure !== null) throw new Error("Invalid flow values");
    return row;
  });
  if (series.some((r, i) => i > 0 && r.date <= series[i-1].date)) throw new Error("Unordered flow dates");
  const coverage = {priceSessions: number(c.priceSessions), completeFlowSessions: number(c.completeFlowSessions),
    missingDates: dates(c.missingDates), partialDates: dates(c.partialDates), calendar: String(c.calendar)};
  if (coverage.priceSessions !== series.length || coverage.completeFlowSessions !== series.filter(r => r.sessionComplete).length
    || JSON.stringify(coverage.missingDates) !== JSON.stringify(series.filter(r => r.status === "missing").map(r => r.date))
    || JSON.stringify(coverage.partialDates) !== JSON.stringify(series.filter(r => r.status === "partial").map(r => r.date))) throw new Error("Flow coverage mismatch");
  const validation = {folds: number(v.folds), realizedBars: number(v.realizedBars), forecastBars: number(v.forecastBars),
    forecastCoverage: number(v.forecastCoverage), feeBpsOneWay: number(v.feeBpsOneWay), totalReturn: number(v.totalReturn),
    benchmarkReturn: number(v.benchmarkReturn), maxDrawdown: number(v.maxDrawdown), sharpe: nullable(v.sharpe),
    trainSize: number(v.trainSize), testSize: number(v.testSize), gap: number(v.gap), evaluationStatus: String(v.evaluationStatus)};
  if (validation.forecastCoverage < 0 || validation.forecastCoverage > 1 || validation.feeBpsOneWay < 0
    || validation.evaluationStatus !== "research_replay_not_point_in_time_verified") throw new Error("Invalid flow validation");
  const folds = d.folds.map(raw => { const f = object(raw); return {fold: number(f.fold), trainStart: date(f.trainStart),
    trainEnd: date(f.trainEnd), testStart: date(f.testStart), testEnd: date(f.testEnd), trainValid: number(f.trainValid), forecastCount: number(f.forecastCount)}; });
  if (folds.length !== validation.folds || folds.some(f => f.trainEnd >= f.testStart || f.testEnd < f.testStart)) throw new Error("Leaking validation dates");
  const replay = d.replay.map(raw => {const r = object(raw); return {date: date(r.date), strategyEquity: number(r.strategyEquity), benchmarkEquity: number(r.benchmarkEquity)};});
  if (replay.length !== validation.realizedBars || replay.some((r, i) => r.strategyEquity <= 0 || r.benchmarkEquity <= 0 || i > 0 && r.date <= replay[i-1].date)) throw new Error("Invalid replay");
  const firstDate = date(d.firstDate), dataThrough = date(d.dataThrough);
  if (firstDate !== series[0].date || dataThrough !== series.at(-1)!.date) throw new Error("Snapshot date mismatch");
  return {schema: "flow-model-v1", ticker: d.ticker, method: d.method, generatedAt: d.generatedAt, dataThrough, firstDate,
    isLive: false, holdings: null, coverage, validation, folds, series, replay};
}

export function parseFlowIndex(value: unknown): {tickers: string[]} {
  const d = object(value);
  if (d.schema !== "flow-model-index-v1" || !Array.isArray(d.tickers) || d.tickers.length > 100
    || d.tickers.some(t => typeof t !== "string" || !validFlowTicker(t))) throw new Error("Invalid flow index");
  return {tickers: d.tickers as string[]};
}
