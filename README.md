# basivo-journal

**Your Claude Code memory and activity journal.** Every session is saved live
to **your own private GitHub repo**: the stats, and (optionally) the chat
itself with secrets masked. From that you get:

- **Memory for Claude**: tools that search your past work
  (`journal_search`, `journal_session`, `journal_recent`, `journal_stats`), so
  "how did I fix CDK bootstrap last time?" gets answered from your history,
  not guessed
- a short **start-of-session card**: who you are, what you've been working on,
  and what happened last time in the current project (about 110 tokens)
- a **dashboard** you can deploy free on Vercel: Overview, Chats, Projects,
  Tools and Learning tabs, light/dark mode, live refresh, and a searchable
  chat viewer
- `/journal` in Claude Code for a quick summary, and an optional Sunday email

---

## Contents

1. [How it works](#how-it-works)
2. [First-time setup](#first-time-setup)
3. [New laptop? (move or add a machine)](#new-laptop-move-or-add-a-machine)
4. [Memory: how Claude uses your history](#memory-how-claude-uses-your-history)
5. [Dashboard (Vercel)](#dashboard-vercel)
6. [Weekly email (optional)](#weekly-email-optional)
7. [What is recorded](#what-is-recorded)
8. [Files and folders](#files-and-folders)
9. [Troubleshooting](#troubleshooting)
10. [Turn things off / uninstall](#turn-things-off--uninstall)

---

## How it works

```
 Claude Code session
   │  after each reply (every ≤5 min), at session end, and at next start (catch-up sweep)
   ▼
 ~/.basivo-journal/data      ← full local clone of your private repo
   │  git push (background, batched)
   ▼
 github.com/<you>/basivo-journal-data  (PRIVATE)   ← the permanent copy
   ├─ sessions/YYYY/MM/<id>.json   stats for one session
   └─ chats/YYYY/MM/<id>.json      the conversation, secrets masked
        │
        ├─► ~/.basivo-journal/index.db   local search index (a cache, rebuilt automatically)
        │       └─► journal_* MCP tools → Claude
        └─► Vercel dashboard (read-only token) → you, in the browser
```

Nothing depends on a paid service. GitHub private repos are free, the index is
local, and the dashboard can be redeployed anywhere.

## First-time setup

You need: **Python 3**, **git**, the **GitHub CLI** (`gh`, logged in with
`gh auth login`), and Claude Code.

1. **Install the plugin** (from the Basivo marketplace):
   ```
   claude plugin marketplace add mohamedabubasith/basivo-plugins
   claude plugin install basivo-journal@basivo
   ```
2. **Restart Claude Code**, then run:
   ```
   /journal-setup <your-github-user>/basivo-journal-data
   ```
   It checks the repo is **private** (and creates it if it doesn't exist),
   clones it to `~/.basivo-journal/data`, and loads your past sessions.
3. **Keep Claude Code's history longer** than the 30-day default, so old
   sessions can always be rebuilt. Add to `~/.claude/settings.json`:
   ```json
   "cleanupPeriodDays": 3650
   ```
4. **Optional (macOS): hourly background sweep**, which catches sessions whose hooks didn't run:
   ```
   python3 ~/.claude/plugins/cache/basivo/basivo-journal/*/scripts/journal.py install-sweeper
   ```

## New laptop? (move or add a machine)

Your data is already in GitHub, so a new machine only needs the plugin and a
clone. Old sessions, chats and search all come back. Nothing is copied by hand.

1. **Install the tools**: Python 3, git, Claude Code, and the GitHub CLI.
   ```
   brew install gh        # macOS; see cli.github.com for others
   gh auth login          # sign in as the same GitHub user
   ```
2. **Install the plugin**:
   ```
   claude plugin marketplace add mohamedabubasith/basivo-plugins
   claude plugin install basivo-journal@basivo
   ```
3. **Restart Claude Code** and connect the **existing** repo (the same name as before):
   ```
   /journal-setup <your-github-user>/basivo-journal-data
   ```
   Or from a terminal:
   ```
   python3 ~/.claude/plugins/cache/basivo/basivo-journal/*/scripts/journal.py setup <your-github-user>/basivo-journal-data
   ```
   This clones your whole history. The search index builds itself on first use
   (about 0.1 s per 4,000 messages).
4. **Bring this machine's own sessions in** (only if you already used Claude Code on it):
   ```
   python3 ~/.claude/plugins/cache/basivo/basivo-journal/*/scripts/journal.py backfill
   ```
5. Settings from first-time setup: `cleanupPeriodDays`, and optionally
   `install-sweeper`.
6. **Check it**: start a new Claude Code session. The first message context
   should include "Journal: N sessions…". Then ask Claude: *"search my journal
   for <something you did before>"*.

**Using two laptops at once** works: each session is its own file, so machines
never edit the same file. Each machine pulls before it pushes. The `machine`
field shows where each session happened.

**Retiring the old laptop**: nothing to do. Optionally run
`journal.py uninstall-sweeper` there, then uninstall the plugin.

**The dashboard and weekly email don't change**: they read GitHub, not your laptop.

## Memory: how Claude uses your history

The plugin adds a local MCP server named `journal` with four tools. Claude
calls them only when past context helps, so nothing is loaded up front and
each lookup costs about 100–300 tokens:

| Tool | Use it for | Returns |
|---|---|---|
| `journal_search(query, project?, since?, role?, limit?)` | "how did I…", "what did we decide about…", "like last time" | Up to 10 short snippets: date · project · session title · id |
| `journal_session(id, query?, around?, max_messages?)` | Reading the relevant part of one past session | Session facts plus the matching messages (not the whole chat) |
| `journal_recent(project?, limit?)` | "What was I doing in X?" | Latest sessions: date, title, minutes, languages, id |
| `journal_stats(days?)` | "How much did I work this week?" | Sessions, hours, top projects and languages |

Examples you can type:

- *"Search my journal: how did I fix the CDK bootstrap profile issue?"*
- *"What did I work on in the chatbot project last week?"*
- *"Open the session where we set up the Vercel dashboard and remind me which env vars we used."*

The start-of-session card adds, for the folder you're in:
*"Last time in this project: 2026-09-28 'Blog on Medium using plugin'…"*

**Search details**: full-text (SQLite FTS5 with stemming, so "deploy"
matches "deployed"). It tries all words first, then any word. The same
pasted block within one session is indexed once, and results are spread
across sessions.

## Dashboard (Vercel)

The app is in [`dashboard/`](dashboard/). Deploy it with **Root Directory =
`dashboard`**, and set these environment variables:

| Variable | Value |
|---|---|
| `GITHUB_TOKEN` | fine-grained token, **only** your data repo, **Contents: read-only** |
| `DATA_REPO` | `<you>/basivo-journal-data` |
| `DASHBOARD_PASSCODE` | the passcode for the login page (12+ characters) |
| `JOURNAL_API_KEY` | a long random string, used by `/api/stats` and `/api/digest` (header `x-journal-key`) |

```
cd dashboard
npx vercel link
npx vercel env add GITHUB_TOKEN production
npx vercel env add DATA_REPO production
npx vercel env add DASHBOARD_PASSCODE production
npx vercel env add JOURNAL_API_KEY production
npx vercel deploy --prod
```

**Run it locally** against your clone instead of GitHub:
```
cd dashboard && npm install
LOCAL_DATA_DIR=~/.basivo-journal/data DASHBOARD_PASSCODE=dev JOURNAL_API_KEY=dev npm run dev
```

**New data appears without redeploying.** The dashboard reads GitHub on each
visit and refreshes every minute. To redeploy automatically when you change
the dashboard code, connect the repo under Vercel → Settings → Git.

## Weekly email (optional)

Schedule `GET https://<your-dashboard>/api/digest` with header
`x-journal-key: <JOURNAL_API_KEY>`. It returns `{ subject, html }`; send that
with any mail step. [`n8n/weekly-digest.workflow.js`](n8n/weekly-digest.workflow.js)
is a ready n8n workflow (Sunday 9 am → fetch → Gmail).

## What is recorded

| Recorded | Never recorded |
|---|---|
| session id, title, start/end, active minutes (idle gaps over 5 min don't count), minutes by hour and day | tool inputs and outputs, command output |
| project folder (`~/…`), machine name | file contents, diffs |
| file **languages** edited; tool / MCP / skill **names** and counts | full URLs, page content |
| site **hostnames**; model; output token total | |
| **chat history**: your messages and Claude's written replies, with **secrets masked** (tokens, API keys, `password: …`, `key=value` credentials, cards, emails) | |

Check what a session would store: `journal.py summarize <transcript.jsonl>`.

## Files and folders

| Path | What it is |
|---|---|
| `~/.basivo-journal/data/` | your private repo clone (the real data) |
| `~/.basivo-journal/config.json` | `data_dir`, `record_chat`, dashboard key (mode 600) |
| `~/.basivo-journal/index.db` | search index. Safe to delete; it rebuilds automatically. |
| `~/.basivo-journal/state.json` | last sweep/push times and hook throttling |
| `~/.basivo-journal/card.txt` | last start-of-session card (offline fallback) |
| `~/.basivo-journal/bin/` | copy of the scripts used by the hourly sweeper |
| `~/Library/LaunchAgents/in.basivo.journal.sweep.plist` | the hourly sweeper (macOS) |

## Troubleshooting

| Symptom | Fix |
|---|---|
| No "Journal: …" line at session start | `/journal-setup` wasn't run on this machine, or the plugin isn't enabled: `claude plugin list` |
| Claude doesn't use the journal tools | `claude mcp list` should show `plugin:basivo-journal:journal`. Restart Claude Code after installing or updating. |
| Sessions missing on the dashboard | Run `journal.py sweep` and then `journal.py sync`. Check `git -C ~/.basivo-journal/data status`. |
| Push fails | `gh auth status` and `git -C ~/.basivo-journal/data push` to see the error |
| Dashboard says "Couldn't load your data" | Check `GITHUB_TOKEN` (not expired, access to the data repo) and `DATA_REPO` in Vercel |
| Search misses something recent | The index refreshes on each query. If needed, delete `~/.basivo-journal/index.db`. |

## Turn things off / uninstall

- **Stop saving chat text** (stats only): add `"record_chat": false` to
  `~/.basivo-journal/config.json`. Already-saved chats stay in the repo until
  you delete `chats/` there.
- **Stop the hourly sweep**: `journal.py uninstall-sweeper`
- **Uninstall**: `claude plugin uninstall basivo-journal@basivo`. Your data
  stays in your GitHub repo and in `~/.basivo-journal/data`.

## Tests

```
python3 tests/test_journal.py
python3 tests/test_memory.py
```

Part of the [Basivo plugins](https://github.com/mohamedabubasith/basivo-plugins).
Made by [Basivo](https://basivo.in).
