import { workflow, node, trigger, ifElse, expr } from '@n8n/workflow-sdk';

const statsWebhook = trigger({
  type: 'n8n-nodes-base.webhook',
  version: 2.1,
  config: { name: 'Stats Webhook', parameters: { httpMethod: 'GET', path: 'claude-journal-stats', responseMode: 'responseNode', options: {} } },
  output: [{ headers: { 'x-journal-key': 'k' }, query: {} }]
});

const checkKey = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: { name: 'Check Key', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: "\nconst h = $input.first().json.headers || {};\nreturn [{ json: { _ok: (h['x-journal-key'] || '') === '__JOURNAL_KEY__' } }];\n" } },
  output: [{ _ok: true }]
});

const isAllowed = ifElse({
  version: 2.2,
  config: {
    name: 'Key Valid?',
    parameters: {
      conditions: {
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose' },
        conditions: [{ leftValue: expr("{{ $json._ok ? 'yes' : 'no' }}"), rightValue: 'yes', operator: { type: 'string', operation: 'equals' } }],
        combinator: 'and'
      }
    }
  }
});

const loadRows = node({
  type: 'n8n-nodes-base.dataTable',
  version: 1.1,
  config: {
    name: 'Load Journal Rows',
    executeOnce: true,
    alwaysOutputData: true,
    parameters: { resource: 'row', operation: 'get', dataTableId: { __rl: true, mode: 'id', value: '__DATA_TABLE_ID__', cachedResultName: 'claude_journal' }, returnAll: true }
  },
  output: [{ session_id: 's1', started_at: '2026-09-28T10:00:00Z', minutes: 30, project: 'demo', languages: '{}' }]
});

const aggregate = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: { name: 'Aggregate Stats', parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: "\nconst rows = $input.all().map(i => i.json).filter(r => r.session_id && r.source !== 'test');\nconst P = (s) => { try { const v = typeof s === 'string' ? JSON.parse(s || '{}') : (s || {}); return v || {}; } catch { return {}; } };\nconst add = (acc, obj, w = 1) => { if (Array.isArray(obj)) obj.forEach(k => acc[k] = (acc[k] || 0) + w); else for (const [k, v] of Object.entries(obj)) acc[k] = (acc[k] || 0) + (+v || w); };\nconst top = (o, n = 8) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, n).map(([k, v]) => ({ name: k, value: Math.round(v * 10) / 10 }));\nconst day = (r) => String(r.started_at || r.ended_at || '').slice(0, 10);\nconst now = Date.now(), D = 864e5;\nconst within = (r, d) => { const t = Date.parse(r.started_at || r.ended_at || 0); return t && now - t <= d * D; };\nfunction summarize(list) {\n  const langs = {}, tools = {}, mcps = {}, skills = {}, sites = {}, projects = {};\n  let minutes = 0, msgs = 0, calls = 0, tokens = 0;\n  for (const r of list) {\n    minutes += +r.minutes || 0; msgs += +r.user_msgs || 0; calls += +r.tool_calls || 0; tokens += +r.tokens_out || 0;\n    add(langs, P(r.languages)); add(tools, P(r.tools)); add(mcps, P(r.mcps)); add(skills, P(r.skills)); add(sites, P(r.sites));\n    const p = (r.project || 'unknown').split('/').filter(Boolean).pop(); projects[p] = (projects[p] || 0) + (+r.minutes || 0) / 60;\n  }\n  return { sessions: list.length, hours: Math.round(minutes / 6) / 10, user_msgs: msgs, tool_calls: calls, tokens_out: tokens,\n    top_projects: top(projects), top_languages: top(langs), top_tools: top(tools), top_mcps: top(mcps), top_skills: top(skills), top_sites: top(sites) };\n}\nconst days = [...new Set(rows.map(day).filter(Boolean))].sort();\nlet streak = 0; for (let d = new Date(); ; d = new Date(d - D)) { if (days.includes(d.toISOString().slice(0, 10))) streak++; else if (streak || d.toISOString().slice(0,10) !== new Date().toISOString().slice(0,10)) break; }\nconst firstSeen = {};\nfor (const r of [...rows].sort((a, b) => String(a.started_at).localeCompare(String(b.started_at))))\n  for (const k of [...Object.keys(P(r.languages)).map(x => 'lang:' + x), ...[].concat(Object.keys(P(r.mcps))).map(x => 'mcp:' + x), ...[].concat(Object.keys(P(r.skills))).map(x => 'skill:' + x)])\n    if (!firstSeen[k]) firstSeen[k] = day(r);\nconst recentFirsts = Object.entries(firstSeen).filter(([, d]) => d && now - Date.parse(d) <= 30 * D).map(([k, d]) => ({ name: k, first: d })).slice(-15);\nconst last30 = {}; rows.filter(r => within(r, 30)).forEach(r => { const d = day(r); last30[d] = (last30[d] || 0) + (+r.minutes || 0); });\nconst all = summarize(rows), week = summarize(rows.filter(r => within(r, 7))), month = summarize(rows.filter(r => within(r, 30)));\nconst n = (a) => a.slice(0, 4).map(x => x.name).join(', ') || 'n/a';\nconst card = 'Journal: ' + all.sessions + ' sessions, ' + all.hours + ' h total since ' + (days[0] || 'n/a') + '; this week ' + week.hours + ' h, streak ' + streak + ' d. Main projects: ' + n(month.top_projects) + '. Languages: ' + n(all.top_languages) + '. Tools/MCPs: ' + n(month.top_mcps) + '.';\nreturn [{ json: { ok: true, generated_at: new Date().toISOString(), first_day: days[0] || null, active_days: days.length, streak_days: streak, all_time: all, last_7_days: week, last_30_days: month, minutes_by_day_30: last30, new_in_last_30_days: recentFirsts, card } }];\n" } },
  output: [{ ok: true, card: 'Journal: ...' }]
});

const respondStats = node({
  type: 'n8n-nodes-base.respondToWebhook',
  version: 1.5,
  config: { name: 'Respond Stats', parameters: { respondWith: 'firstIncomingItem', options: { responseCode: 200 } } },
  output: [{ ok: true }]
});

const respondDenied = node({
  type: 'n8n-nodes-base.respondToWebhook',
  version: 1.5,
  config: { name: 'Respond Denied', parameters: { respondWith: 'json', responseBody: '{"ok":false,"error":"unauthorized"}', options: { responseCode: 401 } } },
  output: [{ ok: false }]
});

export default workflow('claude-journal-stats', 'Claude Journal: Stats')
  .add(statsWebhook)
  .to(checkKey)
  .to(isAllowed
    .onTrue(loadRows.to(aggregate.to(respondStats)))
    .onFalse(respondDenied));
