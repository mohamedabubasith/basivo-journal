import { NextResponse } from "next/server";
import { COOKIE, safeEqual, sessionToken } from "@/lib/auth";

export async function POST(req: Request) {
  const form = await req.formData();
  const pass = String(form.get("passcode") || "");
  const next = String(form.get("next") || "/");
  const expected = process.env.DASHBOARD_PASSCODE || "";
  const dest = new URL(next.startsWith("/") && !next.startsWith("//") ? next : "/", req.url);
  if (!expected || !safeEqual(pass, expected)) {
    await new Promise((r) => setTimeout(r, 800)); // slow down guessing
    return NextResponse.redirect(new URL("/login?error=1", req.url), 303);
  }
  const res = NextResponse.redirect(dest, 303);
  res.cookies.set(COOKIE, sessionToken()!, {
    httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 90,
  });
  return res;
}
