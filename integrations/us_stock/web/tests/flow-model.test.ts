import {test} from "node:test";
import assert from "node:assert/strict";
import {mkdtemp, writeFile, symlink, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {parseFlowSnapshot, parseFlowIndex, validFlowTicker, flowLineSegments} from "../lib/flow-model";
import {readFlowSnapshot, readFlowIndex} from "../lib/server/flow-model-store";

function fixture() {
  return {schema: "flow-model-v1", ticker: "MSFT", method: "sampled-tick-rule-v1", generatedAt: "2026-10-20T23:00:00Z", firstDate: "2026-09-02", dataThrough: "2026-09-03", isLive: false, holdings: null,
    coverage: {priceSessions: 2, completeFlowSessions: 1, missingDates: ["2026-09-03"], partialDates: [], calendar: "XNYS"},
    validation: {folds: 1, realizedBars: 1, forecastBars: 1, forecastCoverage: 1, feeBpsOneWay: 10, totalReturn: -.1, benchmarkReturn: .1, maxDrawdown: -.2, sharpe: null, trainSize: 252, testSize: 21, gap: 5, evaluationStatus: "research_replay_not_point_in_time_verified"},
    folds: [{fold: 1, trainStart: "2024-01-02", trainEnd: "2025-01-02", testStart: "2025-01-10", testEnd: "2025-02-10", trainValid: 252, forecastCount: 21}],
    series: [{date: "2026-09-02", open: 100, high: 110, low: 90, close: 101, volume: 1000, sampledLargeNetUsd: -100, dailyPressure: -.1, pressure5: null, pressure20: null, sessionComplete: true, status: "complete"},
      {date: "2026-09-03", open: 101, high: 110, low: 90, close: 102, volume: 1000, sampledLargeNetUsd: null, dailyPressure: null, pressure5: null, pressure20: null, sessionComplete: false, status: "missing"}],
    replay: [{date: "2025-01-10", strategyEquity: .9, benchmarkEquity: 1.1}]};
}
test("signed values and unknowns are preserved; server-only extension fields are not exposed", () => {
  const raw = {...fixture(), privatePath: "/not-for-client"};
  const d = parseFlowSnapshot(raw);
  assert.equal(d.series[0].sampledLargeNetUsd, -100);
  assert.equal(d.series[1].sampledLargeNetUsd, null);
  assert.equal(d.validation.sharpe, null);
  assert.equal("privatePath" in d, false);
});
test("invalid numbers, holdings claims and fabricated coverage fail closed", () => {
  const bad = [()=>{const d=fixture(); d.series[0].close=NaN;return d;}, ()=>({...fixture(), holdings: 100}),
    ()=>({...fixture(), isLive: true}), ()=>{const d=fixture();d.coverage.completeFlowSessions=2;return d;},
    ()=>{const d=fixture();d.folds[0].trainEnd=d.folds[0].testStart;return d;}];
  for (const get of bad) assert.throws(()=>parseFlowSnapshot(get()));
});
test("date order, price validity and unknown ticker paths are rejected", () => {
  const d=fixture(); d.series.reverse(); assert.throws(()=>parseFlowSnapshot(d));
  for(const t of ["../MSFT", "/root", "MSFT.json", "", "aapl"]) assert.equal(validFlowTicker(t), false);
  assert.deepEqual(parseFlowIndex({schema:"flow-model-index-v1",tickers:["MSFT","BRK.B"]}).tickers,["MSFT","BRK.B"]);
});
test("chart lines cannot bridge unknown windows or turn missing values into zero", () => {
  const d=parseFlowSnapshot(fixture());
  d.series[0].pressure5=-.1;
  d.series.push({...d.series[0],date:"2026-09-04",pressure5:.2});
  assert.deepEqual(flowLineSegments(d.series,"pressure5"), [[{date:"2026-09-02",value:-.1}],[{date:"2026-09-04",value:.2}]]);
});
test("configured snapshot directory is read-only, bounded and refuses symlinks", async () => {
  const directory=await mkdtemp(join(tmpdir(), "flow-model-")); const old=process.env.FLOW_MODEL_SNAPSHOT_DIR;
  process.env.FLOW_MODEL_SNAPSHOT_DIR=directory;
  try {
    await writeFile(join(directory,"MSFT.json"),JSON.stringify(fixture()));
    assert.equal((await readFlowSnapshot("MSFT")).ticker,"MSFT");
    assert.deepEqual((await readFlowIndex()).tickers,["MSFT"]);
    await symlink(join(directory,"MSFT.json"),join(directory,"AAPL.json"));
    await assert.rejects(()=>readFlowSnapshot("AAPL"));
    await assert.rejects(()=>readFlowSnapshot("../MSFT"));
  } finally {
    if(old===undefined) delete process.env.FLOW_MODEL_SNAPSHOT_DIR; else process.env.FLOW_MODEL_SNAPSHOT_DIR=old;
    await rm(directory,{recursive:true,force:true});
  }
});
