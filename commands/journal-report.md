---
description: Open an offline dashboard of your journal (one HTML file, no server or internet) with charts, projects and your searchable chat history.
argument-hint: [output.html]
---

Run:

```
sh "${CLAUDE_PLUGIN_ROOT}/scripts/run" journal.py report $ARGUMENTS
```

It writes one self-contained HTML file (default `~/.basivo-journal/journal-report.html`),
prints its path, and opens it in the browser. Tell the user the path in one line.
The file contains their chat history, so suggest they keep it private and don't
upload or share it.
