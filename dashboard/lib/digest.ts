import { DAY, type Row, projectName, round1, t } from "./stats";

type C = Record<string, number>;
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

function sum(list: Row[]) {
  const o = { sessions: list.length, hours: 0, projects: {} as C, langs: {} as C, mcps: {} as C, skills: {} as C, days: new Set<string>() };
  for (const r of list) {
    const h = (r.minutes || 0) / 60;
    o.hours += h;
    const p = projectName(r.project);
    o.projects[p] = (o.projects[p] || 0) + h;
    for (const [k, v] of Object.entries(r.languages || {})) o.langs[k] = (o.langs[k] || 0) + v;
    for (const [k, v] of Object.entries(r.mcps || {})) o.mcps[k] = (o.mcps[k] || 0) + v;
    for (const [k, v] of Object.entries(r.skills || {})) o.skills[k] = (o.skills[k] || 0) + v;
    o.days.add((r.started_at || "").slice(0, 10));
  }
  return o;
}

/** Weekly email: subject + inline-styled HTML (email clients ignore <style>). */
export function weeklyDigest(rows: Row[], now = Date.now(), dashboardUrl = "") {
  const inRange = (a: number, b: number) => rows.filter((r) => t(r) > now - a * DAY && t(r) <= now - b * DAY);
  const wk = sum(inRange(7, 0)), prev = sum(inRange(14, 7));
  const top = (o: C, n = 5) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, n);
  const before = new Set<string>();
  rows.filter((r) => t(r) <= now - 7 * DAY).forEach((r) => {
    Object.keys(r.languages || {}).forEach((k) => before.add("Language: " + k));
    Object.keys(r.mcps || {}).forEach((k) => before.add("MCP: " + k));
    Object.keys(r.skills || {}).forEach((k) => before.add("Skill: " + k));
  });
  const fresh = [
    ...Object.keys(wk.langs).map((k) => "Language: " + k),
    ...Object.keys(wk.mcps).map((k) => "MCP: " + k),
    ...Object.keys(wk.skills).map((k) => "Skill: " + k),
  ].filter((x) => !before.has(x));
  const h1 = (x: number) => round1(x).toFixed(1);
  const delta = wk.hours - prev.hours;
  const trend = prev.hours ? `${delta >= 0 ? "+" : ""}${h1(delta)} h vs last week`
    : rows.some((r) => t(r) <= now - 7 * DAY) ? "no sessions the week before" : "first tracked week";
  const li = (arr: [string, number][], unit: string) => arr.length
    ? arr.map(([k, v]) => `<li>${esc(k)} <span style="color:#6b7280">(${unit === "h" ? h1(v) + " h" : v + " " + unit})</span></li>`).join("")
    : '<li style="color:#6b7280">none</li>';
  const section = (title: string, body: string) => `<h3 style="margin:22px 0 6px;font-size:16px">${title}</h3><ul style="margin:0;padding-left:18px">${body}</ul>`;
  const topProject = top(wk.projects, 1)[0];
  const insight = !wk.sessions ? "No Claude sessions this week. A short one keeps the streak going."
    : fresh.length ? `You started something new: ${fresh.slice(0, 3).join(", ")}. Worth a small practice project to lock it in.`
    : topProject && topProject[1] > wk.hours * 0.6 ? `Most of your week went into ${topProject[0]} (${h1(topProject[1])} h). Deep focus week.`
    : `Time was spread across ${Object.keys(wk.projects).length} projects this week.`;
  const d = (ms: number) => new Date(ms).toISOString().slice(0, 10);
  const html = `<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:560px;color:#111827">`
    + `<h2 style="margin:0 0 4px">Your week on Claude</h2><p style="margin:0;color:#6b7280">${d(now - 7 * DAY)} to ${d(now)}</p>`
    + `<p style="font-size:18px;margin:18px 0 0"><b>${h1(wk.hours)} h</b> across <b>${wk.sessions}</b> sessions on <b>${wk.days.size}</b> days <span style="color:#6b7280">(${trend})</span></p>`
    + section("Where the time went", li(top(wk.projects), "h"))
    + section("Languages you wrote", li(top(wk.langs), "edits"))
    + section("Tools and MCPs you leaned on", li(top(wk.mcps), "calls"))
    + section("New this week", fresh.length ? fresh.map((x) => `<li>${esc(x)}</li>`).join("") : '<li style="color:#6b7280">nothing new</li>')
    + `<p style="margin:22px 0 0;padding:12px 14px;background:#fef3c7;border-radius:10px">${esc(insight)}</p>`
    + (dashboardUrl ? `<p style="margin:18px 0 0"><a href="${esc(dashboardUrl)}" style="color:#2a78d6">Open your dashboard</a></p>` : "")
    + `<p style="margin:18px 0 0;font-size:12px;color:#9ca3af">basivo-journal</p></div>`;
  return { subject: `Your week on Claude: ${h1(wk.hours)} h, ${wk.sessions} sessions`, html };
}
