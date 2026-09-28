import { workflow, node, trigger, expr } from '@n8n/workflow-sdk';

const everySunday = trigger({
  type: 'n8n-nodes-base.scheduleTrigger',
  version: 1.3,
  config: { name: 'Every Sunday 9am', parameters: { rule: { interval: [{ field: 'weeks', triggerAtDay: [0], triggerAtHour: 9 }] } } },
  output: [{}]
});

const loadRows = node({
  type: 'n8n-nodes-base.dataTable',
  version: 1.1,
  config: {
    name: 'Load Journal Rows',
    executeOnce: true,
    parameters: { resource: 'row', operation: 'get', dataTableId: { __rl: true, mode: 'id', value: '__DATA_TABLE_ID__', cachedResultName: 'claude_journal' }, returnAll: true }
  },
  output: [{ session_id: 's1', started_at: '2026-09-28T10:00:00Z', minutes: 30, project: '~/code/app', languages: '{}', mcps: '{}', skills: '{}' }]
});

const buildDigest = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: { name: 'Build Weekly Digest', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: "\nconst rows = $input.all().map(i => i.json).filter(r => r.session_id && r.source !== 'test');\nconst P = (s) => { try { return (typeof s === 'string' ? JSON.parse(s || '{}') : s) || {}; } catch { return {}; } };\nconst D = 864e5, now = Date.now();\nconst t = (r) => Date.parse(r.started_at || r.ended_at || 0) || 0;\nconst inRange = (a, b) => rows.filter(r => t(r) > now - a * D && t(r) <= now - b * D);\nfunction sum(list) {\n  const o = { sessions: list.length, hours: 0, projects: {}, langs: {}, mcps: {}, skills: {}, days: new Set() };\n  for (const r of list) {\n    const h = (+r.minutes || 0) / 60; o.hours += h;\n    const p = (r.project || 'unknown').split('/').filter(Boolean).pop(); o.projects[p] = (o.projects[p] || 0) + h;\n    for (const [k, v] of Object.entries(P(r.languages))) o.langs[k] = (o.langs[k] || 0) + +v;\n    for (const [k, v] of Object.entries(P(r.mcps))) o.mcps[k] = (o.mcps[k] || 0) + +v;\n    for (const [k, v] of Object.entries(P(r.skills))) o.skills[k] = (o.skills[k] || 0) + +v;\n    o.days.add(String(r.started_at || '').slice(0, 10));\n  }\n  return o;\n}\nconst wk = sum(inRange(7, 0)), prev = sum(inRange(14, 7));\nconst top = (o, n = 5) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, n);\nconst seenBefore = new Set();\nrows.filter(r => t(r) <= now - 7 * D).forEach(r => { Object.keys(P(r.languages)).forEach(k => seenBefore.add('Language: ' + k)); Object.keys(P(r.mcps)).forEach(k => seenBefore.add('MCP: ' + k)); Object.keys(P(r.skills)).forEach(k => seenBefore.add('Skill: ' + k)); });\nconst fresh = [...Object.keys(wk.langs).map(k => 'Language: ' + k), ...Object.keys(wk.mcps).map(k => 'MCP: ' + k), ...Object.keys(wk.skills).map(k => 'Skill: ' + k)].filter(x => !seenBefore.has(x));\nconst h1 = (x) => (Math.round(x * 10) / 10).toFixed(1);\nconst delta = wk.hours - prev.hours;\nconst trend = prev.hours ? (delta >= 0 ? '+' : '') + h1(delta) + ' h vs last week' : rows.some(r => t(r) <= now - 7 * D) ? 'no sessions the week before' : 'first tracked week';\nconst li = (arr, unit) => arr.length ? arr.map(([k, v]) => '<li>' + k + ' <span style=\"color:#6b7280\">(' + (unit === 'h' ? h1(v) + ' h' : v + ' ' + unit) + ')</span></li>').join('') : '<li style=\"color:#6b7280\">none</li>';\nconst section = (title, body) => '<h3 style=\"margin:22px 0 6px;font-size:16px\">' + title + '</h3><ul style=\"margin:0;padding-left:18px\">' + body + '</ul>';\nconst topProject = top(wk.projects, 1)[0];\nconst insight = !wk.sessions ? 'No Claude sessions this week. A short one keeps the streak going.'\n  : fresh.length ? 'You started something new: ' + fresh.slice(0, 3).join(', ') + '. Worth a small practice project to lock it in.'\n  : topProject && topProject[1] > wk.hours * 0.6 ? 'Most of your week went into ' + topProject[0] + ' (' + h1(topProject[1]) + ' h). Deep focus week.'\n  : 'Time was spread across ' + Object.keys(wk.projects).length + ' projects this week.';\nconst html = '<div style=\"font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:560px;color:#111827\">'\n  + '<h2 style=\"margin:0 0 4px\">Your week on Claude</h2>'\n  + '<p style=\"margin:0;color:#6b7280\">' + new Date(now - 7 * D).toISOString().slice(0, 10) + ' to ' + new Date(now).toISOString().slice(0, 10) + '</p>'\n  + '<p style=\"font-size:18px;margin:18px 0 0\"><b>' + h1(wk.hours) + ' h</b> across <b>' + wk.sessions + '</b> sessions on <b>' + wk.days.size + '</b> days <span style=\"color:#6b7280\">(' + trend + ')</span></p>'\n  + section('Where the time went', li(top(wk.projects), 'h'))\n  + section('Languages you wrote', li(top(wk.langs), 'edits'))\n  + section('Tools and MCPs you leaned on', li(top(wk.mcps), 'calls'))\n  + section('New this week', fresh.length ? fresh.map(x => '<li>' + x + '</li>').join('') : '<li style=\"color:#6b7280\">nothing new</li>')\n  + '<p style=\"margin:22px 0 0;padding:12px 14px;background:#fef3c7;border-radius:10px\">' + insight + '</p>'\n  + '<p style=\"margin:18px 0 0;font-size:12px;color:#9ca3af\">basivo-journal \u00b7 from your own n8n</p></div>';\nreturn [{ json: { subject: 'Your week on Claude: ' + h1(wk.hours) + ' h, ' + wk.sessions + ' sessions', html } }];\n" } },
  output: [{ subject: 'Your week on Claude: 7.3 h, 4 sessions', html: '<div>...</div>' }]
});

const emailDigest = node({
  type: 'n8n-nodes-base.gmail',
  version: 2.2,
  config: {
    name: 'Email Digest',
    parameters: { resource: 'message', operation: 'send', sendTo: '__YOUR_EMAIL__', subject: expr('{{ $json.subject }}'), emailType: 'html', message: expr('{{ $json.html }}'), options: { appendAttribution: false, senderName: 'basivo-journal' } },
    credentials: { gmailOAuth2: { id: '__GMAIL_CREDENTIAL_ID__', name: 'Gmail account' } }
  },
  output: [{ id: 'msg1' }]
});

export default workflow('claude-journal-weekly', 'Claude Journal: Weekly Digest')
  .add(everySunday)
  .to(loadRows)
  .to(buildDigest)
  .to(emailDigest);
