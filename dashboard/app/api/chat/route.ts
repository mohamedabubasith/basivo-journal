import { NextResponse } from "next/server";
import { loadChat } from "@/lib/data";

// Behind the passcode cookie (proxy.ts). ?month=YYYY/MM&id=<session id>
export async function GET(req: Request) {
  const u = new URL(req.url);
  const chat = await loadChat(u.searchParams.get("month") || "", u.searchParams.get("id") || "");
  if (!chat) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  return NextResponse.json(chat, { headers: { "Cache-Control": "private, max-age=60" } });
}
