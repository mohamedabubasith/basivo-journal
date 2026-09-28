import { NextResponse } from "next/server";
import { apiKeyOk } from "@/lib/auth";
import { loadRows } from "@/lib/data";
import { weeklyDigest } from "@/lib/digest";

export async function GET(req: Request) {
  if (!apiKeyOk(req)) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const origin = new URL(req.url).origin;
  return NextResponse.json({ ok: true, ...weeklyDigest(await loadRows(), Date.now(), origin) });
}
