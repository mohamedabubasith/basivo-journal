"use client";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { Bars, Heatmap, Profile, RankList, Sparkline, Stacked } from "./charts";
import Chats from "./ui/chats";
import {
  DAY, type Row, bestStreak, dayKey, firsts, minutesByDay, minutesByHour, minutesByWeekday,
  projectName, round1, streak, summarize, t, withinDays,
} from "@/lib/stats";

const TABS = [
  { id: "overview", label: "Overview", icon: "◎" },
  { id: "chats", label: "Chats", icon: "💬" },
  { id: "projects", label: "Projects", icon: "▦" },
  { id: "tools", label: "Tools", icon: "⚙" },
  { id: "learning", label: "Learning", icon: "✦" },
] as const;
type Tab = (typeof TABS)[number]["id"];

const RANGES = [
  { id: 7, label: "7d" }, { id: 30, label: "30d" }, { id: 90, label: "90d" }, { id: 365, label: "1y" }, { id: 0, label: "All" },
];
const MAX_SERIES = 5;
const REFRESH_MS = 60_000;
const HOURS = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, "0")}:00`);
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const weekStart = (ms: number) => {
  const d = new Date(ms);
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
};

// ---------- small building blocks ----------

function useCountUp(target: number, ms = 700) {
  const [v, setV] = useState(target);
  useEffect(() => {
    let raf = 0;
    const start = performance.now();
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / ms);
      setV(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

function Tile({ label, value, decimals = 0, suffix = "", note, trend }: { label: string; value: number; decimals?: number; suffix?: string; note: string; trend?: number | null }) {
  const v = useCountUp(value);
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}{suffix}</div>
      <div className="tile-note">
        {trend != null && trend !== 0 && <span className={`trend ${trend > 0 ? "up" : "down"}`}>{trend > 0 ? "▲" : "▼"} {Math.abs(round1(trend))}</span>}
        {note}
      </div>
    </div>
  );
}

type Theme = "system" | "light" | "dark";
const themeListeners = new Set<() => void>();
const readTheme = (): Theme => { try { const v = localStorage.getItem("bj-theme"); return v === "light" || v === "dark" ? v : "system"; } catch { return "system"; } };
const subscribeTheme = (cb: () => void) => { themeListeners.add(cb); return () => { themeListeners.delete(cb); }; };

function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeTheme, readTheme, () => "system" as Theme);
  const apply = (next: Theme) => {
    const root = document.documentElement;
    try {
      if (next === "system") { localStorage.removeItem("bj-theme"); root.removeAttribute("data-theme"); }
      else { localStorage.setItem("bj-theme", next); root.setAttribute("data-theme", next); }
    } catch {}
    themeListeners.forEach((l) => l());
  };
  return (
    <div className="seg theme" role="group" aria-label="Theme">
      {(["light", "system", "dark"] as const).map((m) => (
        <button key={m} aria-pressed={theme === m} onClick={() => apply(m)} title={m[0].toUpperCase() + m.slice(1)}>
          {m === "light" ? "☀" : m === "dark" ? "☾" : "A"}
        </button>
      ))}
    </div>
  );
}

function ago(ms: number) {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s}s ago` : `${Math.round(s / 60)}m ago`;
}

function toCsv(rows: Row[]) {
  const cols = ["started_at", "ended_at", "project", "title", "minutes", "user_msgs", "tool_calls", "model", "tokens_out", "machine"] as const;
  const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const top = (o: Record<string, number> | undefined) => Object.entries(o || {}).sort((a, b) => b[1] - a[1]).map(([k]) => k).slice(0, 3).join(" ");
  return [cols.join(",") + ",languages,mcps", ...rows.map((r) => cols.map((c) => esc(r[c])).join(",") + "," + esc(top(r.languages)) + "," + esc(top(r.mcps)))].join("\n");
}

// ---------- main ----------

export default function Dashboard({ rows: initialRows, generatedAt }: { rows: Row[]; generatedAt: string }) {
  const [rows, setRows] = useState(initialRows);
  const [stamp, setStamp] = useState(generatedAt);
  const [clock, setClock] = useState(Date.parse(generatedAt));
  const [refreshing, setRefreshing] = useState(false);
  const [range, setRange] = useState(30);
  const [chatProject, setChatProject] = useState("all");
  const router = useRouter();
  const hash = useSyncExternalStore(
    (cb) => { window.addEventListener("hashchange", cb); return () => window.removeEventListener("hashchange", cb); },
    () => location.hash.slice(1),
    () => "",
  );
  const tab: Tab = TABS.some((x) => x.id === hash) ? (hash as Tab) : "overview";
  const go = (id: Tab) => { history.pushState(null, "", "#" + id); window.dispatchEvent(new HashChangeEvent("hashchange")); window.scrollTo({ top: 0, behavior: "smooth" }); };

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await fetch("/api/rows", { cache: "no-store" });
      if (res.status === 401) { router.push("/login"); return; }
      if (res.ok) { const d = await res.json(); setRows(d.rows); setStamp(d.generatedAt); }
    } finally { setRefreshing(false); }
  }, [router]);
  useEffect(() => {
    const id = setInterval(() => { if (document.visibilityState === "visible") refresh(); }, REFRESH_MS);
    const tick = setInterval(() => setClock(Date.now()), 5000);
    return () => { clearInterval(id); clearInterval(tick); };
  }, [refresh]);

  const now = Date.parse(stamp);
  const inRange = useMemo(() => withinDays(rows, range, now), [rows, range, now]);
  const prev = useMemo(() => (range ? rows.filter((r) => now - t(r) > range * DAY && now - t(r) <= 2 * range * DAY) : []), [rows, range, now]);
  const s = useMemo(() => summarize(inRange), [inRange]);
  const p = useMemo(() => summarize(prev), [prev]);
  const trend = (a: number, b: number) => (range && b ? a - b : null);

  const download = () => {
    const blob = new Blob([toCsv([...inRange].sort((a, b) => t(a) - t(b)))], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `claude-journal-${range || "all"}d.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="app">
      <header className="appbar">
        <div className="brand">
          <span className="logo" aria-hidden>◆</span>
          <div>
            <div className="brand-name">Claude Journal</div>
            <div className="live" suppressHydrationWarning>
              <span className={`dot${refreshing ? " busy" : ""}`} /> Live · updated {ago(clock - Date.parse(stamp))}
            </div>
          </div>
        </div>
        <nav className="tabs" aria-label="Sections">
          {TABS.map((x) => (
            <button key={x.id} aria-current={tab === x.id ? "page" : undefined} onClick={() => go(x.id)}>
              <span className="tab-icon" aria-hidden>{x.icon}</span>{x.label}
            </button>
          ))}
        </nav>
        <div className="actions">
          <button className="icon-btn" onClick={refresh} disabled={refreshing} title="Refresh now" aria-label="Refresh now">↻</button>
          <ThemeToggle />
        </div>
      </header>

      <main className="wrap">
        {tab !== "chats" && (
          <div className="toolbar">
            <h1>{TABS.find((x) => x.id === tab)!.label}</h1>
            <div className="toolbar-right">
              <div className="seg" role="group" aria-label="Time range">
                {RANGES.map((r) => <button key={r.id} aria-pressed={range === r.id} onClick={() => setRange(r.id)}>{r.label}</button>)}
              </div>
              <button className="ghost" onClick={download} title="Download sessions as CSV">⤓ CSV</button>
            </div>
          </div>
        )}

        <div className="fade" key={tab}>
          {tab === "overview" && <Overview rows={rows} inRange={inRange} s={s} p={p} range={range} now={now} trend={trend} />}
          {tab === "chats" && <Chats key={chatProject} rows={rows} initialProject={chatProject} />}
          {tab === "projects" && <Projects rows={rows} inRange={inRange} now={now} onOpen={(name) => { setChatProject(name); go("chats"); }} />}
          {tab === "tools" && <Tools s={s} inRange={inRange} />}
          {tab === "learning" && <Learning rows={rows} now={now} />}
        </div>
        <footer className="foot">basivo-journal · your private repo · secrets masked · auto-refresh every minute</footer>
      </main>
    </div>
  );
}

// ---------- tabs ----------

type S = ReturnType<typeof summarize>;

function Overview({ rows, inRange, s, p, range, now, trend }: { rows: Row[]; inRange: Row[]; s: S; p: S; range: number; now: number; trend: (a: number, b: number) => number | null }) {
  const byDay = useMemo(() => minutesByDay(inRange), [inRange]);
  const daily = useMemo(() => {
    const span = range || Math.max(30, Math.ceil((now - Math.min(...inRange.map(t), now)) / DAY));
    if (span > 120) {
      const byWeek: Record<string, number> = {};
      for (const [d, m] of Object.entries(byDay)) byWeek[weekStart(Date.parse(d))] = (byWeek[weekStart(Date.parse(d))] || 0) + m / 60;
      const out = [];
      for (let ms = now - span * DAY; ms <= now; ms += 7 * DAY) { const k = weekStart(ms); out.push({ key: k, label: k, value: round1(byWeek[k] || 0) }); }
      return { unit: "per week", data: out };
    }
    const out = [];
    for (let i = span - 1; i >= 0; i--) { const k = new Date(now - i * DAY).toISOString().slice(0, 10); out.push({ key: k, label: k, value: round1((byDay[k] || 0) / 60) }); }
    return { unit: "per day", data: out };
  }, [byDay, inRange, range, now]);

  const weekly = useMemo(() => {
    const n = range && range <= 90 ? Math.max(4, Math.ceil(range / 7)) : 26;
    const src = rows.filter((r) => now - t(r) <= n * 7 * DAY);
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
  }, [rows, range, now]);

  const hours = useMemo(() => minutesByHour(inRange).map((m) => m / 60), [inRange]);
  const weekdays = useMemo(() => minutesByWeekday(inRange).map((m) => m / 60), [inRange]);
  const heat = useMemo(() => minutesByDay(rows), [rows]);
  const avgSession = s.sessions ? (s.hours * 60) / s.sessions : 0;
  const peakHour = hours.indexOf(Math.max(...hours));
  const peakDay = weekdays.indexOf(Math.max(...weekdays));

  return (
    <>
      <section className="tiles">
        <Tile label="Hours" value={s.hours} decimals={1} note={range ? " vs previous period" : "all time"} trend={trend(s.hours, p.hours)} />
        <Tile label="Sessions" value={s.sessions} note={range ? " vs previous" : "all time"} trend={trend(s.sessions, p.sessions)} />
        <Tile label="Active days" value={s.activeDays} note={s.activeDays ? ` · ${round1(s.hours / s.activeDays)} h/day` : ""} />
        <Tile label="Streak" value={streak(rows, now)} suffix=" d" note={` · best ${bestStreak(rows)} d`} />
        <Tile label="Avg session" value={avgSession} suffix=" min" note=" active time" />
        <Tile label="Your messages" value={s.userMsgs} note={` · ${s.toolCalls.toLocaleString("en-US")} tool calls`} />
      </section>

      {s.hours > 0 && (
        <section className="insight">
          <span aria-hidden>✦</span>
          You do most of your work around <b>{HOURS[peakHour]}</b>, and <b>{WEEKDAYS[peakDay]}</b> is your busiest day.
          {s.projects[0] && <> Top project: <b>{s.projects[0].name}</b> ({s.projects[0].value} h).</>}
        </section>
      )}

      <section className="card">
        <div className="card-head"><h2>Hours {daily.unit}</h2><span className="muted small">{s.hours} h total</span></div>
        <Bars data={daily.data} label={`Hours ${daily.unit}`} />
      </section>

      <section className="grid2">
        <div className="card"><div className="card-head"><h2>When you work</h2><span className="muted small">by hour, local time</span></div>
          <Profile values={hours} labels={HOURS} label="Hours by hour of day" /></div>
        <div className="card"><div className="card-head"><h2>Busiest days</h2><span className="muted small">by weekday</span></div>
          <Profile values={weekdays} labels={WEEKDAYS} label="Hours by weekday" /></div>
      </section>

      <section className="card">
        <div className="card-head"><h2>Hours per week, by project</h2></div>
        <Stacked weeks={weekly.weeks} series={weekly.series} label="Hours per week by project" />
      </section>

      <section className="card">
        <div className="card-head"><h2>Last 12 months</h2><span className="muted small">every day you worked</span></div>
        <Heatmap days={heat} now={now} label="Daily activity over the last year" />
      </section>
    </>
  );
}

function Projects({ rows, inRange, now, onOpen }: { rows: Row[]; inRange: Row[]; now: number; onOpen: (name: string) => void }) {
  const cards = useMemo(() => {
    const byName = new Map<string, Row[]>();
    for (const r of inRange) { const n = projectName(r.project); byName.set(n, [...(byName.get(n) || []), r]); }
    return [...byName.entries()].map(([name, list]) => {
      const sum = summarize(list);
      const all = rows.filter((r) => projectName(r.project) === name);
      const weeks = Array.from({ length: 12 }, (_, i) => {
        const k = weekStart(now - (11 - i) * 7 * DAY);
        return all.filter((r) => weekStart(t(r)) === k).reduce((a, r) => a + r.minutes / 60, 0);
      });
      const last = Math.max(...list.map(t));
      return { name, sum, weeks, last, path: list[0].project };
    }).sort((a, b) => b.sum.hours - a.sum.hours);
  }, [rows, inRange, now]);
  if (!cards.length) return <p className="muted">No sessions in this period.</p>;
  const max = cards[0].sum.hours || 1;
  return (
    <section className="project-grid">
      {cards.map((c) => (
        <button key={c.name} className="project card" onClick={() => onOpen(c.name)} title="Open this project's chats">
          <div className="project-top">
            <div>
              <div className="project-name">{c.name}</div>
              <div className="muted small mono">{c.path}</div>
            </div>
            <Sparkline values={c.weeks} />
          </div>
          <div className="project-hours"><b>{c.sum.hours}</b> h <span className="muted">· {c.sum.sessions} sessions · last {dayKey(new Date(c.last).toISOString())}</span></div>
          <div className="meter"><span style={{ width: `${(c.sum.hours / max) * 100}%` }} /></div>
          <div className="chips">
            {c.sum.languages.slice(0, 4).map((l) => <span key={l.name} className="chip">{l.name}</span>)}
            {c.sum.mcps.slice(0, 2).map((l) => <span key={l.name} className="chip chip-alt">{l.name}</span>)}
          </div>
        </button>
      ))}
    </section>
  );
}

function Tools({ s, inRange }: { s: S; inRange: Row[] }) {
  const models = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of inRange) if (r.model) m[r.model] = (m[r.model] || 0) + r.minutes / 60;
    return Object.entries(m).sort((a, b) => b[1] - a[1]).map(([name, value]) => ({ name, value: round1(value) }));
  }, [inRange]);
  return (
    <>
      <section className="tiles">
        <Tile label="Tool calls" value={s.toolCalls} note=" in period" />
        <Tile label="MCP servers used" value={s.mcps.length} note="" />
        <Tile label="Skills used" value={s.skills.length} note="" />
        <Tile label="Output tokens" value={s.tokensOut / 1000} suffix="k" note=" Claude wrote" />
      </section>
      <section className="grid3">
        <div className="card"><h2>MCP servers <small>(calls)</small></h2><RankList items={s.mcps} unit="" /></div>
        <div className="card"><h2>Skills <small>(uses)</small></h2><RankList items={s.skills} unit="" /></div>
        <div className="card"><h2>Built-in tools <small>(calls)</small></h2><RankList items={s.tools} unit="" /></div>
        <div className="card"><h2>Languages <small>(files edited)</small></h2><RankList items={s.languages} unit="" /></div>
        <div className="card"><h2>Sites <small>(visits)</small></h2><RankList items={s.sites} unit="" /></div>
        <div className="card"><h2>Models <small>(hours)</small></h2><RankList items={models} unit="h" /></div>
      </section>
    </>
  );
}

function Learning({ rows, now }: { rows: Row[]; now: number }) {
  const all = useMemo(() => firsts(rows), [rows]);
  const recent = all.filter((f) => now - Date.parse(f.first) <= 30 * DAY);
  const byKind = (k: string) => all.filter((f) => f.kind === k).length;
  return (
    <>
      <section className="tiles">
        <Tile label="New in last 30 days" value={recent.length} note=" languages, MCPs, skills" />
        <Tile label="Languages" value={byKind("language")} note=" ever used" />
        <Tile label="MCP servers" value={byKind("mcp")} note=" ever used" />
        <Tile label="Skills" value={byKind("skill")} note=" ever used" />
      </section>
      <section className="card">
        <h2>Learning timeline <small>(the first day you used each)</small></h2>
        <ol className="timeline">
          {all.map((f) => (
            <li key={f.kind + f.name} className={now - Date.parse(f.first) <= 30 * DAY ? "is-new" : ""}>
              <time>{f.first}</time>
              <span className={`kind k-${f.kind}`}>{f.kind}</span>
              <span className="tl-name">{f.name}</span>
              {now - Date.parse(f.first) <= 30 * DAY && <span className="badge">new</span>}
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
