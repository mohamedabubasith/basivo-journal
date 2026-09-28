import "server-only";
import { promises as fs } from "fs";
import path from "path";
import type { Row } from "./stats";

// Rows come from your PRIVATE data repo (one JSON file per session).
// Production: GitHub GraphQL with a read-only token (env GITHUB_TOKEN, DATA_REPO).
// Local dev: point LOCAL_DATA_DIR at your clone (~/.basivo-journal/data).

type Entry = { name: string; type: string; object?: { text?: string; entries?: Entry[] } | null };

const QUERY = `query($owner:String!,$name:String!,$expr:String!){
  repository(owner:$owner,name:$name){ object(expression:$expr){ ... on Tree { entries {
    name type object { ... on Tree { entries {
      name type object { ... on Tree { entries {
        name type object { ... on Blob { text } } } } } } } } } } } } }`;

function parse(text: string | undefined): Row | null {
  try {
    const r = JSON.parse(text || "");
    return r && r.session_id ? (r as Row) : null;
  } catch {
    return null;
  }
}

async function fromGitHub(): Promise<Row[]> {
  const token = process.env.GITHUB_TOKEN;
  const [owner, name] = (process.env.DATA_REPO || "").split("/");
  if (!token || !owner || !name) throw new Error("Set GITHUB_TOKEN and DATA_REPO (owner/name).");
  const res = await fetch("https://api.github.com/graphql", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ query: QUERY, variables: { owner, name, expr: `${process.env.DATA_BRANCH || "main"}:sessions` } }),
    cache: "no-store",
  });
  const body = await res.json();
  if (!res.ok || body.errors) throw new Error("GitHub: " + JSON.stringify(body.errors || res.status));
  const years: Entry[] = body.data?.repository?.object?.entries || [];
  const rows: Row[] = [];
  for (const y of years)
    for (const m of y.object?.entries || [])
      for (const f of m.object?.entries || []) {
        const r = f.name.endsWith(".json") ? parse(f.object?.text) : null;
        if (r) rows.push(r);
      }
  return rows;
}

async function fromDisk(dir: string): Promise<Row[]> {
  const rows: Row[] = [];
  async function walk(d: string) {
    for (const e of await fs.readdir(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) await walk(p);
      else if (e.name.endsWith(".json")) {
        const r = parse(await fs.readFile(p, "utf8"));
        if (r) rows.push(r);
      }
    }
  }
  await walk(path.join(dir.replace(/^~/, process.env.HOME || ""), "sessions"));
  return rows;
}

export async function loadRows(): Promise<Row[]> {
  const local = process.env.LOCAL_DATA_DIR;
  return local ? fromDisk(local) : fromGitHub();
}
