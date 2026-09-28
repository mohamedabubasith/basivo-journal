export type Counts = Record<string, number>;
export type Row = {
  session_id: string;
  started_at: string;
  ended_at: string;
  machine: string;
  project: string;
  minutes: number;
  user_msgs: number;
  tool_calls: number;
  languages: Counts;
  tools: Counts;
  mcps: Counts;
  skills: Counts;
  sites: Counts;
  model: string;
  tokens_out: number;
  source?: string;
  title?: string;
  first_prompt?: string;
  active_by_hour?: Counts;
  active_by_day?: Counts;
};

export type Ranked = { name: string; value: number };
export const DAY = 864e5;

export const projectName = (p: string) => (p || "unknown").replace(/\/+$/, "").split("/").pop() || "unknown";
export const dayKey = (iso: string) => (iso || "").slice(0, 10);
export const t = (r: Row) => Date.parse(r.started_at) || 0;
export const round1 = (n: number) => Math.round(n * 10) / 10;

function rank(c: Counts, n = 8): Ranked[] {
  return Object.entries(c)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([name, value]) => ({ name, value: round1(value) }));
}

function add(into: Counts, from: Counts | undefined, weight = 1) {
  for (const [k, v] of Object.entries(from || {})) into[k] = (into[k] || 0) + (Number(v) || 0) * weight;
}

export function summarize(rows: Row[]) {
  const projects: Counts = {}, languages: Counts = {}, tools: Counts = {}, mcps: Counts = {}, skills: Counts = {}, sites: Counts = {};
  let minutes = 0, userMsgs = 0, toolCalls = 0, tokens = 0;
  const days = new Set<string>();
  for (const r of rows) {
    minutes += r.minutes || 0;
    userMsgs += r.user_msgs || 0;
    toolCalls += r.tool_calls || 0;
    tokens += r.tokens_out || 0;
    days.add(dayKey(r.started_at));
    const p = projectName(r.project);
    projects[p] = (projects[p] || 0) + (r.minutes || 0) / 60;
    add(languages, r.languages);
    add(tools, r.tools);
    add(mcps, r.mcps);
    add(skills, r.skills);
    add(sites, r.sites);
  }
  return {
    sessions: rows.length,
    hours: round1(minutes / 60),
    activeDays: days.size,
    userMsgs,
    toolCalls,
    tokensOut: tokens,
    projects: rank(projects, 12),
    languages: rank(languages),
    tools: rank(tools),
    mcps: rank(mcps),
    skills: rank(skills),
    sites: rank(sites),
  };
}

export function streak(rows: Row[], now = Date.now()) {
  const days = new Set(rows.map((r) => dayKey(r.started_at)));
  let d = new Date(now);
  if (!days.has(d.toISOString().slice(0, 10))) d = new Date(now - DAY);
  let n = 0;
  while (days.has(d.toISOString().slice(0, 10))) {
    n++;
    d = new Date(d.getTime() - DAY);
  }
  return n;
}

/** First date each language / MCP / skill appears: the "learning" timeline. */
export function firsts(rows: Row[]) {
  const seen = new Map<string, { kind: string; name: string; first: string }>();
  for (const r of [...rows].sort((a, b) => t(a) - t(b)))
    for (const kind of ["languages", "mcps", "skills"] as const)
      for (const name of Object.keys(r[kind] || {})) {
        const key = kind + ":" + name;
        if (!seen.has(key)) seen.set(key, { kind: kind.slice(0, -1), name, first: dayKey(r.started_at) });
      }
  return [...seen.values()].sort((a, b) => b.first.localeCompare(a.first));
}

export function withinDays(rows: Row[], days: number, now = Date.now()) {
  return days <= 0 ? rows : rows.filter((r) => now - t(r) <= days * DAY);
}

export function card(rows: Row[], now = Date.now()) {
  const all = summarize(rows), week = summarize(withinDays(rows, 7, now)), month = summarize(withinDays(rows, 30, now));
  const first = rows.map((r) => dayKey(r.started_at)).sort()[0] || "n/a";
  const names = (l: Ranked[]) => l.slice(0, 4).map((x) => x.name).join(", ") || "n/a";
  return `Journal: ${all.sessions} sessions, ${all.hours} h since ${first}; this week ${week.hours} h, streak ${streak(rows, now)} d. ` +
    `Main projects: ${names(month.projects)}. Languages: ${names(all.languages)}. Tools/MCPs: ${names(month.mcps)}.`;
}

export function bestStreak(rows: Row[]) {
  const days = [...new Set(rows.flatMap((r) => Object.keys(r.active_by_day || { [dayKey(r.started_at)]: 1 })))].sort();
  let best = 0, run = 0, prev = 0;
  for (const d of days) {
    const ms = Date.parse(d);
    run = prev && ms - prev === DAY ? run + 1 : 1;
    best = Math.max(best, run);
    prev = ms;
  }
  return best;
}

/** Minutes per calendar day (uses per-day buckets when present, so midnight-spanning sessions split correctly). */
export function minutesByDay(rows: Row[]) {
  const m: Counts = {};
  for (const r of rows) {
    const days = r.active_by_day && Object.keys(r.active_by_day).length ? r.active_by_day : { [dayKey(r.started_at)]: r.minutes };
    for (const [d, v] of Object.entries(days)) m[d] = (m[d] || 0) + v;
  }
  return m;
}

export function minutesByHour(rows: Row[]) {
  const h = Array(24).fill(0) as number[];
  for (const r of rows) for (const [k, v] of Object.entries(r.active_by_hour || {})) h[+k] += v;
  return h;
}

export function minutesByWeekday(rows: Row[]) {
  const w = Array(7).fill(0) as number[]; // Mon..Sun
  for (const [d, v] of Object.entries(minutesByDay(rows))) w[(new Date(d + "T12:00:00Z").getUTCDay() + 6) % 7] += v;
  return w;
}

export function monthKey(r: Row) {
  return (r.started_at || "").slice(0, 7).replace("-", "/");
}
