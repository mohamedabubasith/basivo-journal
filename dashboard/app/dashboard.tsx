"use client";
import { useMemo, useState } from "react";
import { Bars, Heatmap, RankList, Stacked } from "./charts";
import { DAY, type Row, dayKey, firsts, projectName, round1, streak, summarize, t, withinDays } from "@/lib/stats";

const RANGES = [
  { id: 7, label: "7 days" },
  { id: 30, label: "30 days" },
  { id: 90, label: "90 days" },
  { id: 365, label: "1 year" },
  { id: 0, label: "All" },
];
const MAX_SERIES = 5; // top projects get slots 1..5, the rest fold into "Other"

const weekStart = (ms: number) => {
  const d = new Date(ms);
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); // Monday
  return d.toISOString().slice(0, 10);
};

export default function Dashboard({ rows, generatedAt }: { rows: Row[]; generatedAt: string }) {
  const [range, setRange] = useState(30);
  const [project, setProject] = useState("all");
  const now = Date.parse(generatedAt); // server's request time keeps render pure

  const projects = useMemo(() => summarize(rows).projects.map((p) => p.name), [rows]);
  const scoped = useMemo(() => (project === "all" ? rows : rows.filter((r) => projectName(r.project) === project)), [rows, project]);
  const inRange = useMemo(() => withinDays(scoped, range, now), [scoped, range, now]);
  const prev = useMemo(() => (range ? scoped.filter((r) => now - t(r) > range * DAY && now - t(r) <= 2 * range * DAY) : []), [scoped, range, now]);
  const s = summarize(inRange), p = summarize(prev);

  const daily = useMemo(() => {
    const byDay: Record<string, number> = {};
    for (const r of inRange) byDay[dayKey(r.started_at)] = (byDay[dayKey(r.started_at)] || 0) + r.minutes / 60;
    const span = range || Math.max(30, Math.ceil((now - Math.min(...inRange.map(t), now)) / DAY));
    if (span > 120) {
      const byWeek: Record<string, number> = {};
      for (const [d, h] of Object.entries(byDay)) byWeek[weekStart(Date.parse(d))] = (byWeek[weekStart(Date.parse(d))] || 0) + h;
      const out = [];
      for (let ms = now - span * DAY; ms <= now; ms += 7 * DAY) { const k = weekStart(ms); out.push({ key: k, label: k, value: round1(byWeek[k] || 0) }); }
      return { unit: "per week", data: out };
    }
    const out = [];
    for (let i = span - 1; i >= 0; i--) { const k = new Date(now - i * DAY).toISOString().slice(0, 10); out.push({ key: k, label: k, value: round1(byDay[k] || 0) }); }
    return { unit: "per day", data: out };
  }, [inRange, range, now]);

  const weekly = useMemo(() => {
    const n = range && range <= 90 ? Math.max(4, Math.ceil(range / 7)) : 26;
    const src = scoped.filter((r) => now - t(r) <= n * 7 * DAY);
    const top = summarize(src).projects.slice(0, MAX_SERIES).map((x) => x.name);
    const series = src.some((r) => !top.includes(projectName(r.project))) ? [...top, "Other"] : top;
    const weeks: { key: string; label: string; parts: Record<string, number> }[] = [];
    for (let i = n - 1; i >= 0; i--) { const k = weekStart(now - i * 7 * DAY); if (!weeks.find((w) => w.key === k)) weeks.push({ key: k, label: k, parts: {} }); }
    for (const r of src) {
      const wk = weeks.find((w) => w.key === weekStart(t(r)));
      if (!wk) continue;
      const name = top.includes(projectName(r.project)) ? projectName(r.project) : "Other";
      wk.parts[name] = (wk.parts[name] || 0) + r.minutes / 60;
    }
    return { weeks, series };
  }, [scoped, range, now]);

  const heat = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of scoped) m[dayKey(r.started_at)] = (m[dayKey(r.started_at)] || 0) + r.minutes;
    return m;
  }, [scoped]);

  const learned = useMemo(() => firsts(scoped).slice(0, 18), [scoped]);
  const recent = useMemo(() => [...inRange].sort((a, b) => t(b) - t(a)).slice(0, 40), [inRange]);
  const diff = (a: number, b: number, unit = "") => (range && b ? `${a - b >= 0 ? "+" : ""}${round1(a - b)}${unit} vs previous` : range ? "no data before" : "all time");

  return (
    <main className="wrap">
      <header className="top">
        <div>
          <h1>Claude Journal</h1>
          <p className="muted" suppressHydrationWarning>Updated {new Date(generatedAt).toLocaleString()}</p>
        </div>
        <div className="filters">
          <div className="seg" role="group" aria-label="Time range">
            {RANGES.map((r) => <button key={r.id} aria-pressed={range === r.id} onClick={() => setRange(r.id)}>{r.label}</button>)}
          </div>
          <select value={project} onChange={(e) => setProject(e.target.value)} aria-label="Project">
            <option value="all">All projects</option>
            {projects.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </header>

      <section className="tiles">
        <Tile label="Hours" value={s.hours.toFixed(1)} note={diff(s.hours, p.hours, " h")} />
        <Tile label="Sessions" value={String(s.sessions)} note={diff(s.sessions, p.sessions)} />
        <Tile label="Active days" value={String(s.activeDays)} note={s.activeDays ? `${round1(s.hours / s.activeDays)} h per active day` : "none"} />
        <Tile label="Streak" value={`${streak(scoped, now)} d`} note="consecutive days" />
        <Tile label="Your messages" value={s.userMsgs.toLocaleString("en-US")} note={`${s.toolCalls.toLocaleString("en-US")} tool calls`} />
      </section>

      <section className="card">
        <h2>Hours {daily.unit}</h2>
        <Bars data={daily.data} label={`Hours ${daily.unit}`} />
      </section>

      <section className="card">
        <h2>Hours per week, by project</h2>
        <Stacked weeks={weekly.weeks} series={weekly.series} label="Hours per week by project" />
      </section>

      <section className="card">
        <h2>Last 12 months</h2>
        <Heatmap days={heat} now={now} label="Daily activity over the last year" />
      </section>

      <section className="grid3">
        <div className="card"><h2>Projects</h2><RankList items={s.projects.slice(0, 8)} unit="h" /></div>
        <div className="card"><h2>Languages <small>(files edited)</small></h2><RankList items={s.languages} unit="" /></div>
        <div className="card"><h2>MCP servers <small>(calls)</small></h2><RankList items={s.mcps} unit="" /></div>
        <div className="card"><h2>Skills</h2><RankList items={s.skills} unit="" /></div>
        <div className="card"><h2>Built-in tools <small>(calls)</small></h2><RankList items={s.tools} unit="" /></div>
        <div className="card"><h2>Sites</h2><RankList items={s.sites} unit="" /></div>
      </section>

      <section className="grid2">
        <div className="card">
          <h2>Learning timeline <small>(first time you used it)</small></h2>
          <ul className="timeline">
            {learned.map((f) => <li key={f.kind + f.name}><time>{f.first}</time><span className={`kind k-${f.kind}`}>{f.kind}</span>{f.name}</li>)}
          </ul>
        </div>
        <div className="card">
          <h2>Sessions</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Project</th><th className="num">Min</th><th className="num">Msgs</th><th>Top language</th></tr></thead>
              <tbody>
                {recent.map((r) => (
                  <tr key={r.session_id}>
                    <td>{dayKey(r.started_at)}</td>
                    <td>{projectName(r.project)}</td>
                    <td className="num">{Math.round(r.minutes)}</td>
                    <td className="num">{r.user_msgs}</td>
                    <td>{Object.entries(r.languages || {}).sort((a, b) => b[1] - a[1])[0]?.[0] || "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
      <footer className="muted foot">basivo-journal · data from your private repo · counts and names only</footer>
    </main>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      <div className="tile-note">{note}</div>
    </div>
  );
}
