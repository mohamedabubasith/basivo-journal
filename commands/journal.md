---
description: Show your Claude Code activity journal — hours, streak, projects, languages, tools, MCPs, skills, and what you started using recently.
argument-hint: [week|month|all]  (default: week)
---

Run this and read its JSON output (it is small; do not print it raw):

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/journal.py" stats
```

If it fails with "No config", tell the user to run `/journal-setup` and stop.

Focus period: `$ARGUMENTS` → `week` = `last_7_days`, `month` = `last_30_days`,
`all` = `all_time`. Default `week`.

Reply in this shape, short and plain (no tables wider than 3 columns):

1. **Headline** — sessions, hours, active days, current streak for the period.
2. **Where the time went** — top 3–5 projects with hours.
3. **Strengths** — top languages and the tools/MCPs used most; say what that
   suggests the user is strong in (one line, based only on the numbers).
4. **New this month** — items from `new_in_last_30_days` (first use of a
   language, MCP, or skill): frame as "started learning / started using".
5. **One suggestion** — a single, concrete next step drawn from the data
   (e.g. a skill used once and dropped, a project with long sessions but few
   commits). No generic advice.

Never invent numbers that aren't in the JSON. If the period is empty, say so and
show the all-time headline instead.
