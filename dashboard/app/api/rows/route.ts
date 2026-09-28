import { NextResponse } from "next/server";
import { loadRows } from "@/lib/data";

// Behind the passcode cookie (proxy.ts). Used by the dashboard's live refresh.
export async function GET() {
  const rows = await loadRows();
  return NextResponse.json({ generatedAt: new Date().toISOString(), rows }, { headers: { "Cache-Control": "no-store" } });
}
