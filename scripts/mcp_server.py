#!/usr/bin/env python3
"""Minimal MCP server (stdio, JSON-RPC, standard library only) exposing your
journal as tools Claude can call when it needs past context."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import memory  # noqa: E402

TOOLS = [
    {
        "name": "journal_search",
        "description": (
            "Search the user's own past Claude Code conversations (their private journal) by keywords. "
            "Use when the user refers to earlier work ('like last time', 'how did I fix X', 'what did we decide about Y') "
            "or when past context would help. Returns short snippets with session ids; open one with journal_session."),
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "A few keywords, e.g. 'cdk bootstrap profile'"},
            "project": {"type": "string", "description": "Optional project folder name, e.g. 'chatbot'"},
            "since": {"type": "string", "description": "Optional YYYY-MM-DD lower bound"},
            "role": {"type": "string", "enum": ["user", "assistant"], "description": "Optional: only the user's or only Claude's messages"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}},
            "required": ["query"]},
    },
    {
        "name": "journal_session",
        "description": "Read part of one past session from the journal: its facts plus the messages that match `query`, or those around message `around`, or the start.",
        "inputSchema": {"type": "object", "properties": {
            "id": {"type": "string", "description": "Session id or its first 8 characters (from journal_search / journal_recent)"},
            "query": {"type": "string", "description": "Optional keywords to jump to the relevant messages"},
            "around": {"type": "integer", "description": "Optional message number to read around"},
            "max_messages": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8}},
            "required": ["id"]},
    },
    {
        "name": "journal_recent",
        "description": "List the user's most recent sessions (optionally for one project): date, title, active minutes, languages, id.",
        "inputSchema": {"type": "object", "properties": {
            "project": {"type": "string", "description": "Optional project folder name"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 15, "default": 5}}},
    },
    {
        "name": "journal_stats",
        "description": "The user's Claude Code activity over the last N days: sessions, hours, top projects and languages.",
        "inputSchema": {"type": "object", "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 3650, "default": 7}}},
    },
]


def call(name, args):
    db, root = memory.open_index()
    if not db:
        return "The journal isn't set up on this machine yet. Run /journal-setup."
    if name == "journal_search":
        return memory.search(db, args.get("query", ""), args.get("project"), args.get("since"), args.get("role"), args.get("limit", 5))
    if name == "journal_session":
        return memory.session(db, root, args.get("id", ""), args.get("query"), args.get("around"), args.get("max_messages", 8))
    if name == "journal_recent":
        return memory.recent(db, args.get("project"), args.get("limit", 5))
    if name == "journal_stats":
        return memory.stats(db, args.get("days", 7))
    raise ValueError(f"unknown tool {name}")


def reply(msg_id, result=None, error=None):
    out = {"jsonrpc": "2.0", "id": msg_id}
    out["error" if error else "result"] = error or result
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:  # notification (e.g. notifications/initialized)
            continue
        if method == "initialize":
            reply(mid, {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2025-03-26"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "basivo-journal", "version": "0.4.0"}})
        elif method == "tools/list":
            reply(mid, {"tools": TOOLS})
        elif method == "tools/call":
            p = msg.get("params") or {}
            try:
                text = call(p.get("name"), p.get("arguments") or {})
                reply(mid, {"content": [{"type": "text", "text": text}]})
            except Exception as e:
                reply(mid, {"content": [{"type": "text", "text": f"journal error: {e}"}], "isError": True})
        elif method == "ping":
            reply(mid, {})
        else:
            reply(mid, error={"code": -32601, "message": f"method not found: {method}"})


if __name__ == "__main__":
    main()
