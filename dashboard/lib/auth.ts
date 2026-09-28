import { createHmac, timingSafeEqual } from "crypto";

export const COOKIE = "bj_session";

// Cookie value = HMAC of a fixed label with the passcode: changing the passcode
// logs every browser out, and the passcode itself is never stored in the cookie.
export function sessionToken(): string | null {
  const pass = process.env.DASHBOARD_PASSCODE;
  return pass ? createHmac("sha256", pass).update("basivo-journal-session").digest("hex") : null;
}

export function safeEqual(a: string, b: string) {
  const x = Buffer.from(a), y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

/** For machine callers (n8n digest): header x-journal-key must equal JOURNAL_API_KEY. */
export function apiKeyOk(req: Request) {
  const key = process.env.JOURNAL_API_KEY;
  return !!key && safeEqual(req.headers.get("x-journal-key") || "", key);
}
