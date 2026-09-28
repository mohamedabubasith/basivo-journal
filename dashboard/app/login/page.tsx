export const metadata = { title: "Journal · Sign in" };

export default async function Login({ searchParams }: { searchParams: Promise<{ error?: string; next?: string }> }) {
  const { error, next } = await searchParams;
  return (
    <main className="login">
      <form method="post" action="/api/login" className="login-card">
        <h1>Claude Journal</h1>
        <p className="muted">Your personal activity dashboard.</p>
        <input type="hidden" name="next" value={next || "/"} />
        <label htmlFor="passcode">Passcode</label>
        <input id="passcode" name="passcode" type="password" autoComplete="current-password" required autoFocus />
        {error ? <p className="error" role="alert">That passcode didn&apos;t match.</p> : null}
        <button type="submit">Open dashboard</button>
      </form>
    </main>
  );
}
