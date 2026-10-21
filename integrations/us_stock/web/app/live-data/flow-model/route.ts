import { NextRequest, NextResponse } from "next/server";
import { authorizeDataRequest } from "@/lib/server-access";
import { validFlowTicker } from "@/lib/flow-model";
import { readFlowIndex, readFlowSnapshot } from "@/lib/server/flow-model-store";

export const runtime = "nodejs";
export async function GET(request: NextRequest) {
  const denied = await authorizeDataRequest();
  if (denied) return denied;
  const ticker = request.nextUrl.searchParams.get("ticker")?.trim().toUpperCase();
  const headers = {"Cache-Control": "private, no-store"};
  if (ticker !== undefined && !validFlowTicker(ticker)) return NextResponse.json({error: "Invalid ticker"}, {status: 400, headers});
  try {
    return NextResponse.json(ticker ? await readFlowSnapshot(ticker) : await readFlowIndex(), {headers});
  } catch (error) {
    const missing = (error as NodeJS.ErrnoException).code === "ENOENT";
    return NextResponse.json({error: missing ? "Flow snapshot not available" : "Flow snapshot service unavailable"}, {status: missing ? 404 : 503, headers});
  }
}
