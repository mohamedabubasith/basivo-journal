import { workflow, node, trigger, expr } from '@n8n/workflow-sdk';

const everySunday = trigger({
  type: 'n8n-nodes-base.scheduleTrigger',
  version: 1.3,
  config: { name: 'Every Sunday 9am', parameters: { rule: { interval: [{ field: 'weeks', triggerAtDay: [0], triggerAtHour: 9 }] } } },
  output: [{}]
});

const fetchDigest = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Fetch Digest From Dashboard',
    parameters: {
      method: 'GET',
      url: 'https://__YOUR_DASHBOARD__/api/digest',
      authentication: 'none',
      sendHeaders: true,
      specifyHeaders: 'keypair',
      headerParameters: { parameters: [{ name: 'x-journal-key', value: '__JOURNAL_API_KEY__' }] },
      options: { response: { response: { responseFormat: 'json' } } }
    }
  },
  output: [{ ok: true, subject: 'Your week on Claude: 7.6 h, 6 sessions', html: '<div>...</div>' }]
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

export default workflow('claude-journal-weekly-v2', 'Claude Journal: Weekly Digest')
  .add(everySunday)
  .to(fetchDigest)
  .to(emailDigest);
