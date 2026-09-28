import { NextResponse } from "next/server";
import { apiKeyOk } from "@/lib/auth";
import { loadRows } from "@/lib/data";
import { card, firsts, streak, summarize, withinDays } from "@/lib/stats";

export async function GET(req: Request) {
  if (!apiKeyOk(req)) return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  const rows = await loadRows();
  return NextResponse.json({
    ok: true,
    generated_at: new Date().toISOString(),
    streak_days: streak(rows),
    all_time: summarize(rows),
    last_7_days: summarize(withinDays(rows, 7)),
    last_30_days: summarize(withinDays(rows, 30)),
    new_in_last_30_days: firsts(rows).filter((f) => Date.now() - Date.parse(f.first) <= 30 * 864e5),
    card: card(rows),
  });
}
