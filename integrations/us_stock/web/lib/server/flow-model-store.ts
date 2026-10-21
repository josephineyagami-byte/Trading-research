import { open, readdir } from "node:fs/promises";
import { constants } from "node:fs";
import { resolve } from "node:path";
import { parseFlowSnapshot, validFlowTicker } from "../flow-model";

function directory() {
  const path = process.env.FLOW_MODEL_SNAPSHOT_DIR;
  if (!path) throw new Error("Flow snapshots not configured");
  return resolve(path);
}
export async function readFlowSnapshot(ticker: string) {
  if (!validFlowTicker(ticker)) throw new Error("Invalid ticker");
  const file = await open(resolve(directory(), ticker + ".json"), constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.size > 2_000_000) throw new Error("Invalid snapshot file");
    const snapshot = parseFlowSnapshot(JSON.parse(await file.readFile({encoding: "utf8"})));
    if (snapshot.ticker !== ticker) throw new Error("Ticker mismatch");
    return snapshot;
  } finally { await file.close(); }
}
export async function readFlowIndex() {
  const entries = await readdir(directory());
  return {schema: "flow-model-index-v1", tickers: entries.filter(n => n.endsWith(".json") && validFlowTicker(n.slice(0, -5))).map(n => n.slice(0, -5)).sort().slice(0, 100)};
}
