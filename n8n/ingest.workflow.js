import { workflow, node, trigger, ifElse, expr } from '@n8n/workflow-sdk';

const journalWebhook = trigger({
  type: 'n8n-nodes-base.webhook',
  version: 2.1,
  config: {
    name: 'Journal Webhook',
    parameters: { httpMethod: 'POST', path: 'claude-journal', responseMode: 'responseNode', options: {} }
  },
  output: [{ headers: { 'x-journal-key': 'k' }, body: { session_id: 's1', project: 'demo', minutes: 5 } }]
});

const verifyAndNormalize = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Verify Key and Normalize',
    parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: "\nconst KEY = '__JOURNAL_KEY__';\nconst req = $input.first().json;\nconst headers = req.headers || {};\nif ((headers['x-journal-key'] || '') !== KEY) return [{ json: { _denied: true } }];\nconst body = req.body || {};\nconst list = Array.isArray(body.events) ? body.events : [body];\nconst S = (v, n = 500) => (v === undefined || v === null ? '' : typeof v === 'string' ? v : JSON.stringify(v)).slice(0, n);\nconst N = (v) => (Number.isFinite(+v) ? +v : 0);\nreturn list.filter(e => e && e.session_id).slice(0, 500).map(e => ({ json: {\n  session_id: S(e.session_id, 80),\n  started_at: S(e.started_at, 40) || null,\n  ended_at: S(e.ended_at, 40) || null,\n  machine: S(e.machine, 80),\n  project: S(e.project, 200),\n  minutes: N(e.minutes),\n  user_msgs: N(e.user_msgs),\n  tool_calls: N(e.tool_calls),\n  languages: S(e.languages),\n  tools: S(e.tools),\n  mcps: S(e.mcps),\n  skills: S(e.skills),\n  sites: S(e.sites),\n  model: S(e.model, 80),\n  tokens_out: N(e.tokens_out),\n  source: S(e.source, 40) || 'hook'\n}}));\n" }
  },
  output: [{ session_id: 's1', project: 'demo', minutes: 5 }]
});

const isAuthorized = ifElse({
  version: 2.2,
  config: {
    name: 'Authorized?',
    parameters: {
      conditions: {
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose' },
        conditions: [{ leftValue: expr("{{ $json._denied ? 'no' : 'yes' }}"), rightValue: 'yes', operator: { type: 'string', operation: 'equals' } }],
        combinator: 'and'
      }
    }
  }
});

const saveSession = node({
  type: 'n8n-nodes-base.dataTable',
  version: 1.1,
  config: {
    name: 'Upsert Session Row',
    parameters: {
      resource: 'row',
      operation: 'upsert',
      dataTableId: { __rl: true, mode: 'id', value: '__DATA_TABLE_ID__', cachedResultName: 'claude_journal' },
      matchType: 'allConditions',
      filters: { conditions: [{ keyName: 'session_id', condition: 'eq', keyValue: expr('{{ $json.session_id }}') }] },
      columns: { mappingMode: 'autoMapInputData', value: null }
    }
  },
  output: [{ id: 1, session_id: 's1' }]
});

const respondOk = node({
  type: 'n8n-nodes-base.respondToWebhook',
  version: 1.5,
  config: {
    name: 'Respond OK',
    parameters: { respondWith: 'json', responseBody: expr('{{ JSON.stringify({ ok: true, saved: $input.all().length }) }}'), options: { responseCode: 200 } }
  },
  output: [{ ok: true }]
});

const respondUnauthorized = node({
  type: 'n8n-nodes-base.respondToWebhook',
  version: 1.5,
  config: {
    name: 'Respond Unauthorized',
    parameters: { respondWith: 'json', responseBody: '{"ok":false,"error":"unauthorized"}', options: { responseCode: 401 } }
  },
  output: [{ ok: false }]
});

export default workflow('claude-journal-ingest', 'Claude Journal: Ingest')
  .add(journalWebhook)
  .to(verifyAndNormalize)
  .to(isAuthorized
    .onTrue(saveSession.to(respondOk))
    .onFalse(respondUnauthorized));
