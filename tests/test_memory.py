#!/usr/bin/env python3
"""Run: python3 tests/test_memory.py  (exit 0 = pass, no network)."""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "scripts"))

with tempfile.TemporaryDirectory() as home:
    os.environ["BASIVO_JOURNAL_HOME"] = home
    import memory  # noqa: E402  (reads BASIVO_JOURNAL_HOME at import)

    root = os.path.join(home, "data")
    sid = "abcd1234-0000-0000-0000-000000000001"
    os.makedirs(os.path.join(root, "sessions", "2026", "09"))
    os.makedirs(os.path.join(root, "chats", "2026", "09"))
    json.dump({"session_id": sid, "started_at": "2026-09-23T10:00:00Z", "project": "~/code/chatbot",
               "title": "Fix CDK deploy", "minutes": 42, "user_msgs": 3, "languages": {"TypeScript": 4},
               "mcps": {}, "skills": {}, "model": "claude-x"},
              open(os.path.join(root, "sessions", "2026", "09", sid + ".json"), "w"))
    pasted = "config: postgres password: [REDACTED] neo4j port 7687"
    chat_file = os.path.join(root, "chats", "2026", "09", sid + ".json")
    json.dump({"session_id": sid, "project": "~/code/chatbot", "started_at": "2026-09-23T10:00:00Z", "messages": [
        {"role": "user", "ts": "2026-09-23T10:00:00Z", "text": "cdk bootstrap fails with my aws profile"},
        {"role": "assistant", "ts": "2026-09-23T10:01:00Z", "text": "Use `npm run cdk -- bootstrap` so the flag reaches CDK."},
        {"role": "user", "ts": "2026-09-23T10:02:00Z", "text": pasted},
        {"role": "user", "ts": "2026-09-23T10:03:00Z", "text": pasted},
    ]}, open(chat_file, "w"))
    with open(os.path.join(home, "config.json"), "w") as f:
        json.dump({"data_dir": root}, f)

    db, r = memory.open_index()
    assert r == root
    hit = memory.search(db, "cdk bootstrap")
    assert "Fix CDK deploy" in hit and "abcd1234" in hit and "«" in hit, hit
    assert memory.search(db, "neo4j").count("msg ") == 1, "duplicate pasted block should be indexed once"
    assert "No past chats" in memory.search(db, "kubernetes helm")
    assert memory.search(db, "cdk", project="other").startswith("No past chats")
    assert "cdk bootstrap fails" in memory.session(db, root, "abcd1234")
    assert "npm run cdk" in memory.session(db, root, "abcd1234", query="flag reaches")
    assert "No session" in memory.session(db, root, "zzzzzzzz")
    assert "Fix CDK deploy" in memory.recent(db, "chatbot")
    assert memory.project_recap(db, os.path.expanduser("~/code/chatbot")).startswith("Last time in this project")
    # incremental: unchanged files are skipped, edited ones re-indexed
    assert memory.refresh(db, root) == 0
    time.sleep(0.01)
    doc = json.load(open(chat_file))
    doc["messages"].append({"role": "user", "ts": "2026-09-23T10:04:00Z", "text": "also terraform drift"})
    json.dump(doc, open(chat_file, "w"))
    os.utime(chat_file, (time.time() + 5, time.time() + 5))
    assert memory.refresh(db, root) == 1 and "terraform" in memory.search(db, "terraform drift")
    print("PASS  index: search, dedupe, filters, session window, recent, recap, incremental refresh")

    # MCP server: handshake + tools/list + tools/call over stdio
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "journal_search", "arguments": {"query": "cdk bootstrap"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope", "arguments": {}}},
    ]
    out = subprocess.run([sys.executable, os.path.join(HERE, "scripts", "mcp_server.py")],
                         input="\n".join(json.dumps(x) for x in reqs) + "\n", capture_output=True, text=True,
                         env={**os.environ, "BASIVO_JOURNAL_HOME": home}, timeout=30).stdout
    res = {m["id"]: m for m in map(json.loads, out.strip().splitlines())}
    assert set(res) == {1, 2, 3, 4}, res.keys()                       # notification got no reply
    assert res[1]["result"]["serverInfo"]["name"] == "basivo-journal"
    assert {t["name"] for t in res[2]["result"]["tools"]} == {"journal_search", "journal_session", "journal_recent", "journal_stats"}
    assert "Fix CDK deploy" in res[3]["result"]["content"][0]["text"]
    assert res[4]["result"]["isError"] is True
    print("PASS  MCP server: initialize, tools/list, tools/call, error path")

print("\nAll memory tests passed.")
