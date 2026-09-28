# basivo-journal

A personal activity journal for Claude Code. Every session becomes **one small
JSON file** in **your own private GitHub repo**, saved live while you work.
From that you get:

- a **dashboard** (Next.js, deploy free on Vercel, passcode-protected): hours
  per day and week, hours by project, a yearly heat map, languages, MCP
  servers, skills, tools, sites, a learning timeline, and a session list
- `/journal` in Claude Code: your hours, streak, strengths, and what's new
- a short **"about me" card** added to every new session (about 80 tokens)
- an optional **Sunday email digest** (any scheduler: n8n, cron, GitHub Actions)

## Nothing depends on a paid service

| Piece | If it goes away |
|---|---|
| **Private GitHub repo** (your data) | Free and permanent. Plain JSON, so `git clone` takes it anywhere. Every machine also has a full copy in `~/.basivo-journal/data`. |
| Dashboard on Vercel | Redeploy anywhere, or run it locally with `LOCAL_DATA_DIR`. No data lost. |
| Digest scheduler (n8n etc.) | Only the email stops. It just calls `GET /api/digest`. |

## Nothing gets missed

1. **Live saves**: after each Claude reply, the Stop hook saves the session
   (throttled to every 5 minutes). SessionEnd saves once more.
2. **Catch-up sweep** at every session start re-saves any session file that
   changed since the last sweep: crashes, killed windows, failed hooks.
3. Optional **hourly sweep** in the background (`install-sweeper`, macOS).
4. Every save is recomputed from Claude Code's own session file, so repeating
   it is harmless. Keep that history longer than the 30-day default with
   `"cleanupPeriodDays": 3650` in `~/.claude/settings.json`.

Files are pushed in the background, batched every few minutes. Offline changes
go up with the next push. One file per session means two laptops never
conflict.

## What is recorded (and what never is)

| Recorded (counts and names only) | Never recorded |
|---|---|
| session id, start/end, active minutes (idle gaps over 5 min don't count) | your messages or Claude's replies |
| project folder (`~/…`), machine name | file contents, diffs, commands |
| file **languages** edited (by extension) | tool inputs or outputs |
| tool / MCP server / skill **names** and call counts | passwords, keys, tokens |
| site **hostnames** from browser/fetch tools | full URLs, page content |
| model name, output token total | |

Check it yourself: `scripts/journal.py summarize <transcript.jsonl>` prints the
exact record for a session.

## Install

```
claude plugin marketplace add mohamedabubasith/basivo-plugins
claude plugin install basivo-journal@basivo
```

Then in Claude Code: `/journal-setup <you>/basivo-journal-data`. It checks the
repo is **private** (or creates it), clones it, loads your past sessions, and
offers the hourly sweep. Needs Python 3 and git; `gh` for repo creation.

## Dashboard (Vercel)

The app is in [`dashboard/`](dashboard/). Deploy it with **Root Directory =
`dashboard`** and these environment variables:

| Variable | Value |
|---|---|
| `GITHUB_TOKEN` | fine-grained token, **only** your data repo, **Contents: read-only** |
| `DATA_REPO` | `you/basivo-journal-data` |
| `DASHBOARD_PASSCODE` | the passcode for the login page |
| `JOURNAL_API_KEY` | long random string for `/api/stats` and `/api/digest` (header `x-journal-key`) |

Run locally with your clone instead of GitHub:

```
cd dashboard && npm install
LOCAL_DATA_DIR=~/.basivo-journal/data DASHBOARD_PASSCODE=dev JOURNAL_API_KEY=dev npm run dev
```

**Weekly email:** schedule `GET https://<your-app>/api/digest` with header
`x-journal-key`. It returns `{subject, html}`; send that with any mail step.
[`n8n/`](n8n/) has example workflows.

## Commands

| Command | What it does |
|---|---|
| `/journal [week\|month\|all]` | Summary of your activity, strengths, and what's new |
| `/journal-setup <owner/repo>` | Connect your private data repo and load history |

## Tests

```
python3 tests/test_journal.py
```

Part of the [Basivo plugins](https://github.com/mohamedabubasith/basivo-plugins).
Made by [Basivo](https://basivo.in).
