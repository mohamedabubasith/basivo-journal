---
description: Connect basivo-journal to your n8n (ingest + stats webhooks), then backfill past sessions.
argument-hint: <ingest-webhook-url> <key>
---

Goal: write `~/.basivo-journal/config.json` and load past sessions.

1. If `$ARGUMENTS` has a URL and a key, run:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/journal.py" setup <url> <key>
   ```
   Otherwise explain what's needed, in two lines:
   - the n8n **ingest** webhook URL (workflow "Claude Journal: Ingest", path
     `/webhook/claude-journal`); the stats URL is the same with `-stats`;
   - the shared key that workflow checks in the `x-journal-key` header.
   Suggest they run the setup command in their own terminal so the key never
   appears in the chat, then stop.
2. Check it works: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/journal.py" stats`
   must return JSON with `"ok": true`. A 401 means the key doesn't match.
3. Offer the backfill (reads `~/.claude/projects`, sends one row per past
   session, safe to re-run — rows upsert by session id):
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/journal.py" backfill
   ```
   Report sessions found, sent, queued, and total hours.

Never echo the key back to the user.
