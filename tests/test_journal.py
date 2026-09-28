#!/usr/bin/env python3
"""Run: python3 tests/test_journal.py  (exit 0 = pass, no network)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import journal  # noqa: E402

SECRET_TEXT = "my password is hunter2 and this is private chat"


def rec(ts, **kw):
    return json.dumps({"sessionId": "sess-1", "cwd": os.path.expanduser("~/code/app"), "timestamp": ts, **kw})


def tool(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


lines = [
    rec("2026-09-28T10:00:00Z", type="user", turnOrigin="human", message={"content": SECRET_TEXT}),
    rec("2026-09-28T10:01:00Z", type="assistant", message={"model": "claude-x", "usage": {"output_tokens": 100},
        "content": [tool("Edit", file_path="/a/b.py", old_string=SECRET_TEXT), tool("Write", file_path="/a/c.tsx"),
                    tool("mcp__plugin_figma_figma__use_figma"), tool("mcp__claude_ai_Lucid__fetch"),
                    tool("Skill", skill="basivo-operator:basivo-draft"),
                    tool("mcp__playwright-attached__browser_navigate", url="https://www.medium.com/new-story")]}),
    rec("2026-09-28T10:02:00Z", type="user", toolUseResult={"x": 1}, message={"content": [{"type": "tool_result"}]}),
    # 2 hour idle gap: must count as 5 minutes, not 120
    rec("2026-09-28T12:02:00Z", type="assistant", message={"model": "claude-x", "usage": {"output_tokens": 50},
        "content": [tool("Bash", command="rm -rf " + SECRET_TEXT)]}),
    "not json at all",
]

with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
    f.write("\n".join(lines))
row = journal.summarize(f.name)
os.unlink(f.name)

assert row["session_id"] == "sess-1"
assert row["project"] == "~/code/app", row["project"]
assert row["minutes"] == 7.0, row["minutes"]            # 1 + 1 + capped 5
assert row["user_msgs"] == 1, row["user_msgs"]          # tool results aren't user messages
assert row["tool_calls"] == 7
assert row["languages"] == {"Python": 1, "TypeScript": 1}
assert row["mcps"] == {"figma": 1, "Lucid": 1, "playwright-attached": 1}, row["mcps"]
assert row["skills"] == {"basivo-operator:basivo-draft": 1}
assert row["sites"] == {"medium.com": 1}
assert row["tokens_out"] == 150 and row["model"] == "claude-x"
assert "hunter2" not in json.dumps(row), "chat text or tool input leaked into the row"
assert journal.mcp_server("mcp__playwright__browser_click") == "playwright"
assert journal.mcp_server("mcp__plugin_basivo-qa_playwright__browser_click") == "basivo-qa/playwright"
assert journal.mcp_server("mcp__plugin_context-mode_context-mode__ctx_search") == "context-mode"
print("PASS  summarize: counts, idle cap, MCP names, languages, sites, no text leak")

# No config -> hooks are silent no-ops.
journal.CONFIG = "/nonexistent/config.json"
assert journal.load_config() is None
print("PASS  missing config is a silent no-op")
print("\nAll basivo-journal tests passed.")
