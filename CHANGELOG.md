# Changelog

## [0.1.0] - 2026-09-28

### Added
- `scripts/journal.py`: summarizes a Claude Code transcript into one row
  (active minutes with a 5-minute idle cap, project, languages, tools, MCP
  servers, skills, site hostnames, model, output tokens). No chat text, file
  contents, or tool inputs are sent.
- SessionEnd hook sends the row to your n8n; offline rows queue locally and
  flush on the next session.
- SessionStart hook adds a short "about me" card from your aggregated stats
  (cached for offline use).
- `/journal` and `/journal-setup` commands; `backfill` for past sessions.
- n8n workflows (Ingest, Stats, Weekly Digest) and the `claude_journal` data
  table schema under `n8n/`.
