---
description: Connect basivo-journal to your PRIVATE GitHub data repo, load past sessions, and (optionally) turn on the hourly background sweep.
argument-hint: <owner/repo>   e.g. yourname/basivo-journal-data
---

Goal: one private git repo holds a JSON file per session; this machine keeps a
full clone at `~/.basivo-journal/data`.

1. If `$ARGUMENTS` names a repo, check it exists and is **private**:
   `gh repo view $ARGUMENTS --json visibility --jq .visibility` must print
   `PRIVATE`. If it doesn't exist, offer to create it:
   `gh repo create $ARGUMENTS --private`. Never use a public repo.
   If no repo was given, ask for one (suggest `<their-user>/basivo-journal-data`).
2. Clone it: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/journal.py" setup $ARGUMENTS`
3. Load past sessions (safe to re-run; same session = same file):
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/journal.py" backfill`
   Report sessions saved, total hours, and whether the push succeeded.
4. Offer the hourly sweep (macOS; catches sessions whose hooks didn't run):
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/journal.py" install-sweeper`
5. Suggest keeping Claude Code's own history longer than the 30-day default so
   old sessions can always be rebuilt: set `"cleanupPeriodDays": 3650` in
   `~/.claude/settings.json` (ask before editing it).
