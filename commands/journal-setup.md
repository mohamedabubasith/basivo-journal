---
description: Set up basivo-journal on this machine (any OS). Connects your private GitHub data repo with a token, optionally mirrors to Google Drive, and loads your history. No git, gh or brew needed.
argument-hint: <owner/repo>   e.g. yourname/basivo-journal-data
---

Run the plugin's script through its launcher (it finds python3 / python / py):

```
J='sh "${CLAUDE_PLUGIN_ROOT}/scripts/run" journal.py'
```

Work through these steps in order. Keep replies short. **Never ask the user to
paste a token into the chat, and never echo one.**

1. **Check the machine**: `$J doctor`. It prints JSON with `python`, `os`,
   `github`, `google_drive`, `fix`.
   - If the command fails because Python is missing, give the install command
     for their OS and stop until they've installed it:
     Windows `winget install Python.Python.3.12` (or the Microsoft Store);
     macOS `xcode-select --install` or python.org; Linux: their package
     manager (`sudo apt install python3`).

2. **Connect the repo** (`$ARGUMENTS`, or ask for it; suggest
   `<their-github-user>/basivo-journal-data`): `$J setup <owner/repo>`
   - If it returns `"need": "token"`, walk them through the token:
     1. Open the `create_token` link it printed (settings are pre-filled).
     2. **Repository access → Only select repositories →** their data repo.
        **Permissions → Contents: Read and write.** Generate.
        If the repo doesn't exist yet, they create it first at
        https://github.com/new, and it **must be Private**.
     3. In **their own terminal** (not the chat), run the exact command:
        `python3 "<plugin path>/scripts/journal.py" set-token`
        (Windows: `py` instead of `python3`). They paste the token at the hidden
        prompt. Give them the absolute path from `${CLAUDE_PLUGIN_ROOT}`.
     4. When they say done, run `$J setup <owner/repo>` again.
   - Success prints `"ok": true` plus how many sessions were pulled. On a new
     laptop that's the whole history, and memory search works right away.

3. **Load this machine's own past sessions** (safe to re-run): `$J backfill`

4. **Offer the Google Drive backup**: `$J mirror auto`
   - If Google Drive for desktop isn't installed, say: install it from
     https://www.google.com/drive/download/ , sign in, then run it again.
   - Linux has no official Drive app: offer `$J mirror <any synced folder>` or skip.

5. **Offer the hourly background sweep** (optional; live saves already cover
   most cases): `$J install-sweeper`. It uses launchd on macOS, Task Scheduler
   on Windows and cron on Linux.

6. **Suggest keeping Claude Code's history** longer than 30 days: add
   `"cleanupPeriodDays": 3650` to `~/.claude/settings.json` (ask before editing).

7. Finish with: restart Claude Code so memory (`journal_search`, …) loads, and
   they can open an offline report any time with `/journal-report`.
