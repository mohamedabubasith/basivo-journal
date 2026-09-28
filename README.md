# basivo-journal

A personal activity journal for Claude Code. Every session becomes **one small
row** in your own self-hosted **n8n**: how long you worked, in which project,
which languages you edited, which tools, MCP servers and skills you used, and
which sites you touched. From that you get:

- `/journal`: your hours, streak, top projects, strengths, and what you
  started learning recently
- a short **"about me" card** added to every new session, on every machine,
  so Claude knows your background without you repeating it
- a **Sunday email digest** ("Your week on Claude") straight from n8n

Your data lives on your n8n server, not on a third-party cloud, and there is
nothing to pay for.

## What leaves your machine (and what never does)

| Sent (counts and names only) | Never sent |
|---|---|
| session id, start/end time, active minutes (idle gaps over 5 min don't count) | your messages or Claude's replies |
| project folder (`~/…`), machine name | file contents, diffs, commands |
| file **languages** edited (by extension) | tool inputs or outputs |
| tool / MCP server / skill **names** and call counts | passwords, keys, tokens |
| site **hostnames** visited through browser tools | full URLs, page content |
| model name, output token total | |

## How it works

```
Session ends   → hook runs scripts/journal.py send (no AI, 0 tokens)
               → POST one row to n8n "Claude Journal: Ingest" (x-journal-key header)
               → offline? queued in ~/.basivo-journal/queue.jsonl, sent next session
Session starts → hook runs journal.py card → GET "Claude Journal: Stats"
               → adds a ~80-token "about me" card to the session
Sunday 9am     → n8n "Claude Journal: Weekly Digest" → email
```

## Install

```
claude plugin marketplace add mohamedabubasith/basivo-plugins
claude plugin install basivo-journal@basivo
```

Needs Python 3 (standard library only).

## Set up n8n (once)

1. Create a data table named `claude_journal` with the columns in
   [`n8n/claude_journal.table.json`](n8n/claude_journal.table.json).
2. Import the three workflows in [`n8n/`](n8n/) (they're n8n Workflow SDK code;
   paste them via n8n's AI builder / MCP, or rebuild by hand). Replace the
   placeholders: `__JOURNAL_KEY__` (a long random secret),
   `__DATA_TABLE_ID__`, `__GMAIL_CREDENTIAL_ID__`, `__YOUR_EMAIL__`.
3. Publish **Ingest** and **Stats**. Publish **Weekly Digest** when you want
   the email.
4. Point the plugin at it (run in your own terminal so the key stays out of chat):
   ```
   python3 ~/.claude/plugins/cache/basivo/basivo-journal/*/scripts/journal.py \
     setup https://YOUR-N8N/webhook/claude-journal YOUR_KEY
   ```
   or use `/journal-setup` inside Claude Code.
5. Load your history: `journal.py backfill` (safe to re-run; rows upsert by
   session id).

## Commands

| Command | What it does |
|---|---|
| `/journal [week\|month\|all]` | Summary of your activity, strengths, and what's new |
| `/journal-setup <url> <key>` | Connect to n8n and backfill past sessions |

`scripts/journal.py summarize <transcript.jsonl>` prints the exact row a session
would send, with no network, so you can check what's shared.

## Tests

```
python3 tests/test_journal.py
```

Part of the [Basivo plugins](https://github.com/mohamedabubasith/basivo-plugins).
Made by [Basivo](https://basivo.in).
