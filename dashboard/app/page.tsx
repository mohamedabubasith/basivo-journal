import { connection } from "next/server";
import { loadRows } from "@/lib/data";
import type { Row } from "@/lib/stats";
import Dashboard from "./dashboard";

export default async function Home() {
  await connection(); // always read fresh data at request time
  let rows: Row[] | null = null;
  let error = "";
  try {
    rows = await loadRows();
  } catch (e) {
    error = (e as Error).message;
  }
  if (!rows)
    return (
      <main className="wrap">
        <h1>Claude Journal</h1>
        <p className="error">Couldn&apos;t load your data: {error}</p>
        <p className="muted">Check GITHUB_TOKEN and DATA_REPO in the deployment settings.</p>
      </main>
    );
  return <Dashboard rows={rows} generatedAt={new Date().toISOString()} />;
}
