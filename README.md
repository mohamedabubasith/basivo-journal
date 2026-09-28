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
2. [What you need](#what-you-need)
3. [Setup (first laptop or new laptop, any OS)](#setup-first-laptop-or-new-laptop-any-os)
4. [Built to last](#built-to-last)
5. [Memory: how Claude uses your history](#memory-how-claude-uses-your-history)
6. [Offline report and dashboard](#offline-report-and-dashboard)
7. [Weekly email (optional)](#weekly-email-optional)
8. [What is recorded](#what-is-recorded)
9. [Files and folders](#files-and-folders)
10. [Troubleshooting](#troubleshooting)
11. [Turn things off / uninstall](#turn-things-off--uninstall)

---

## How it works

```
 Claude Code session
   │  after each reply (every ≤5 min), at session end, and at next start (catch-up sweep)
   ▼
 ~/.basivo-journal/data      ← full local clone of your private repo
   │  sync in the background (GitHub API + optional Google Drive folder)
   ▼
 github.com/<you>/basivo-journal-data  (PRIVATE)   ← shared copy for all your laptops
 My Drive/basivo-journal                (optional) ← second backup
   ├─ sessions/YYYY/MM/<id>.json   stats for one session
   └─ chats/YYYY/MM/<id>.json      the conversation, secrets masked
        │
        ├─► ~/.basivo-journal/index.db   local search index (a cache, rebuilt automatically)
        │       └─► journal_* MCP tools → Claude
        └─► Vercel dashboard (read-only token) → you, in the browser
```

Nothing depends on a paid service, and no single service can lose your data
(see [Built to last](#built-to-last)).

## What you need

| | Windows | macOS | Linux |
|---|---|---|---|
| **Claude Code** | ✔ | ✔ | ✔ |
| **Python 3.8+** | `winget install Python.Python.3.12` (or the Microsoft Store) | usually built in; otherwise `xcode-select --install` | built in |
| **A free GitHub account** | ✔ | ✔ | ✔ |

That's all. **No git, GitHub CLI or Homebrew.** The plugin talks to GitHub's
API itself.

## Setup (first laptop or new laptop, any OS)

1. **Install the plugin**:
   ```
   claude plugin marketplace add mohamedabubasith/basivo-plugins
   claude plugin install basivo-journal@basivo
   ```
2. **Restart Claude Code** and run:
   ```
   /journal-setup <your-github-user>/basivo-journal-data
   ```
   Claude walks you through it:
   - **First time:** create the repo at https://github.com/new and make it
     **Private**.
   - **Create a token:** setup gives you a link with the settings filled in.
     Choose *Only select repositories →* your data repo, set
     *Contents: Read and write*, then click Generate.
   - **Save it** in your own terminal (hidden input, never in the chat):
     ```
     python3 <plugin>/scripts/journal.py set-token        # Windows: py instead of python3
     ```
   - **Setup downloads your whole history** (about 4 s for 40 sessions).
     Memory and the offline report work right away.
3. **Optional extras** (setup offers these):
   - **Google Drive backup:** `journal.py mirror auto`. It needs *Google Drive
     for desktop* (Windows/macOS), and keeps a second copy in
     `My Drive/basivo-journal`.
   - **Hourly background sweep:** `journal.py install-sweeper` (launchd /
     Task Scheduler / cron).
   - **Keep Claude Code's history:** add `"cleanupPeriodDays": 3650` to
     `~/.claude/settings.json`.

**New laptop = the same three steps.** Use the same repo name; a new token is
fine, and you can use one token per laptop. Two laptops can work at the same
time: each session is its own file, and the newer copy of a file always wins.

**Retiring a laptop:** optionally run `journal.py uninstall-sweeper`, then
revoke that laptop's token at https://github.com/settings/personal-access-tokens .

## Built to last

| Piece | If it goes away | Your data |
|---|---|---|
| **Every laptop** keeps a full copy in `~/.basivo-journal/data` | other laptops, GitHub and Drive still have it | safe |
| **GitHub private repo** (free) | switch to a synced folder: `journal.py setup <folder>` | safe |
| **Google Drive mirror** (optional) | GitHub and your laptops still have it | safe |
| **Vercel dashboard** (optional) | use `/journal-report` (offline, one HTML file) or redeploy anywhere | safe (Vercel only *reads*) |
| **GitHub token expires** | saving continues locally; the session card tells you, and a new token (`set-token`) catches everything up | safe |

Everything is plain JSON (`sessions/…`, `chats/…`), so you can move it
anywhere, forever.

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

## Offline report and dashboard

**Offline report** (works forever, no server): `/journal-report` writes one
HTML file with Overview, Chats (with search) and Projects, light/dark, and
opens it in your browser. It contains your chats, so keep it private.

**Web dashboard** (optional, Vercel free plan):

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
| `~/.basivo-journal/data/` | your full local copy (`sessions/`, `chats/`) |
| `~/.basivo-journal/config.json` | repo, **GitHub token**, mirror folder, `record_chat`, dashboard key (readable only by you) |
| `~/.basivo-journal/index.db` | search index. Safe to delete; it rebuilds automatically. |
| `~/.basivo-journal/state.json` | last sweep/push times and hook throttling |
| `~/.basivo-journal/card.txt` | last start-of-session card (offline fallback) |
| `~/.basivo-journal/bin/` | copy of the scripts used by the hourly sweeper |
| `~/Library/LaunchAgents/in.basivo.journal.sweep.plist` | the hourly sweeper (macOS) |

## Troubleshooting

| Symptom | Fix |
|---|---|
| Not sure what's wrong | `journal.py doctor` lists what this machine still needs, with the fix for each |
| No "Journal: …" line at session start | `/journal-setup` wasn't run on this machine, or the plugin isn't enabled: `claude plugin list` |
| "journal sync to GitHub is paused" | The token expired: create a new one (link in `doctor`), then run `journal.py set-token` |
| Python not found (Windows) | `winget install Python.Python.3.12`, then restart Claude Code |
| Claude doesn't use the journal tools | `claude mcp list` should show `plugin:basivo-journal:journal`. Restart Claude Code after installing or updating. |
| Sessions missing on the dashboard | Run `journal.py sweep` and then `journal.py sync`, which prints each remote's result |
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
python3 tests/test_storage.py
```

Part of the [Basivo plugins](https://github.com/mohamedabubasith/basivo-plugins).
Made by [Basivo](https://basivo.in).
