# Changelog

## [0.5.0] - 2026-09-28

### Changed
- **No git, GitHub CLI or Homebrew needed.** Sync uses GitHub's REST API with
  a fine-grained token (Contents read/write on your data repo only), using
  standard-library Python. It works the same on Windows, macOS and Linux. A
  new laptop downloads its full history in one request (about 4 s for 76
  files, down from about 50 s).
- Hooks and the memory server start through `scripts/run`, which finds
  `python3`, `python` or `py`.
- Existing git clones keep working until a token is added.

### Added
- `journal.py set-token`: hidden prompt, and checks the token can write to the repo.
- **Google Drive (or any synced folder) mirror**: `journal.py mirror auto`
  finds Google Drive for desktop on Windows/macOS. You can also use a folder
  instead of GitHub with `journal.py setup <folder>`.
- **Offline report**: `/journal-report` writes one self-contained HTML file
  (Overview, Chats with search, Projects, light/dark). No server, no internet.
- `journal.py doctor`: a cross-OS checklist with the exact fix for each problem.
- **Token expiry handling**: saving continues locally, the session card says
  sync is paused, and everything catches up once a new token is saved.
- Background sweep for each OS: launchd (macOS), Task Scheduler (Windows), cron (Linux).
- README: "What you need", one setup flow for every OS, "Built to last".

## [0.4.0] - 2026-09-28

### Added
- **Memory for Claude**: a local MCP server (`journal`) with
  `journal_search`, `journal_session`, `journal_recent` and `journal_stats`.
  Claude calls them only when past context helps; each lookup returns short
  snippets (about 100–300 tokens), not whole chats.
- Local full-text index (`~/.basivo-journal/index.db`, SQLite FTS5 with
  stemming), refreshed incrementally before each query. Duplicate pasted
  blocks are indexed once and results are spread across sessions. It's a
  cache, so nothing extra to sync between machines.
- **Project recap** in the start-of-session card: the last sessions in the
  folder you're working in.
- README: full setup, **new-laptop guide**, memory usage, file map,
  troubleshooting, uninstall.

## [0.3.1] - 2026-09-28

### Fixed
- `install-sweeper` now copies the masker next to the script, so the hourly
  background sweep keeps working after 0.3.0 (it imports `mask_pii`).
- Writes use unique temp files, so a hook and the background sweep saving
  the same session at the same moment no longer collide.

## [0.3.0] - 2026-09-28

### Added
- **Chat history**: your messages and Claude's written replies are saved per
  session under `chats/YYYY/MM/<id>.json` in your private repo. Tool calls,
  command output and file contents are not stored. Secrets are masked first
  (tokens, API keys, `password: …`, `key=value`, cards, emails) with a new
  prose-safe masker mode that leaves normal words, paths and IDs alone.
  Turn it off with `"record_chat": false` in `~/.basivo-journal/config.json`.
- Session **titles** and first prompt, plus **active minutes by hour and by
  day** (local time) for "when you work" charts and correct midnight splits.
- **Dashboard v3**: tabs (Overview, Chats, Projects, Tools, Learning),
  light/dark/system theme with no flash, live refresh every minute, chat
  viewer with search, code blocks and copy, hour-of-day and weekday charts,
  best streak, project cards with trend lines, CSV export, count-up numbers,
  animated charts, mobile layout.
- `/api/rows` and `/api/chat` (passcode cookie required).

### Security
- Masker now recognizes GitHub fine-grained tokens (`github_pat_…`) and
  Anthropic keys (`sk-ant-…`).

## [0.2.0] - 2026-09-28

### Changed
- **Your data now lives in your own private GitHub repo**, one JSON file per
  session (`sessions/YYYY/MM/<id>.json`), with a full clone on every machine.
  No dependency on n8n or any paid service; nothing is lost if one goes away.
- Stats and the "about me" card are computed from the local copy, so they work
  offline.

### Added
- **Live saves**: the Stop hook saves the current session after Claude replies
  (throttled to every 5 minutes); SessionEnd saves once more.
- **Catch-up sweep** at every session start: re-saves any session file changed
  since the last sweep (crashes, killed windows, failed hooks).
- Optional **hourly background sweep** via launchd (`install-sweeper`).
- Pushes run in the background and are batched; offline changes go up on the
  next push.

### Removed
- n8n ingest/stats from the plugin. The workflows stay in `n8n/` for reference.

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
