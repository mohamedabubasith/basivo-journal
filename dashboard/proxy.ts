import { NextResponse, type NextRequest } from "next/server";
import { COOKIE, safeEqual, sessionToken } from "@/lib/auth";

// Every page needs the passcode cookie. /login and the key-protected APIs
// (/api/stats, /api/digest check x-journal-key themselves) are let through.
export function proxy(request: NextRequest) {
  const token = sessionToken();
  const cookie = request.cookies.get(COOKIE)?.value || "";
  if (token && safeEqual(cookie, token)) return NextResponse.next();
  const url = new URL("/login", request.url);
  if (request.nextUrl.pathname !== "/") url.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!login|api/login|api/stats|api/digest|_next/static|_next/image|favicon.ico).*)"],
};
