#!/usr/bin/env python3
"""basivo-journal: turn Claude Code sessions into one small row each and keep
them in your own n8n (central, self-hosted).

Only counts and names leave the machine: time spent, project folder, file
languages, tool / MCP / skill names, site hostnames, model, token totals.
Never chat text, file contents, or tool inputs.

  journal.py send       SessionEnd hook: summarize this session, POST it
  journal.py card       SessionStart hook: flush queue, print the "about me" card
  journal.py backfill   send every past session found in ~/.claude/projects
  journal.py stats      print aggregated stats (JSON) from n8n
  journal.py summarize  <transcript.jsonl>  print the row (no network)
  journal.py setup      <endpoint> <key>  write ~/.basivo-journal/config.json
"""
import collections
import datetime as dt
import glob
import json
import os
import socket
import subprocess
import sys
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~")
DIR = os.path.join(HOME, ".basivo-journal")
CONFIG = os.path.join(DIR, "config.json")
QUEUE = os.path.join(DIR, "queue.jsonl")
CARD_CACHE = os.path.join(DIR, "card.txt")
PROJECTS = os.path.join(HOME, ".claude", "projects")
IDLE_CAP_S = 5 * 60  # gaps longer than this count as idle, not work

EXT_LANG = {
    "py": "Python", "ipynb": "Python", "js": "JavaScript", "mjs": "JavaScript", "cjs": "JavaScript",
    "jsx": "JavaScript", "ts": "TypeScript", "tsx": "TypeScript", "go": "Go", "rs": "Rust",
    "java": "Java", "kt": "Kotlin", "swift": "Swift", "rb": "Ruby", "php": "PHP", "cs": "C#",
    "c": "C", "h": "C", "cpp": "C++", "hpp": "C++", "sh": "Shell", "zsh": "Shell", "bash": "Shell",
    "sql": "SQL", "html": "HTML", "css": "CSS", "scss": "CSS", "md": "Markdown", "mdx": "Markdown",
    "json": "JSON", "yaml": "YAML", "yml": "YAML", "toml": "TOML", "tf": "Terraform", "dart": "Dart",
    "vue": "Vue", "svelte": "Svelte", "lua": "Lua", "r": "R",
}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


# ---------- summarize one transcript ----------

def _ts(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def mcp_server(tool_name):
    # mcp__plugin_figma_figma__use_figma -> figma ; mcp__claude_ai_Lucid__fetch -> Lucid
    parts = tool_name.split("__")
    if len(parts) < 3:
        return None
    server = parts[1]
    if server.startswith("claude_ai_"):
        return server[len("claude_ai_"):]
    if server.startswith("plugin_"):
        # plugin_<plugin>_<server>: figma_figma -> figma, basivo-qa_playwright -> basivo-qa/playwright
        plugin, _, inner = server[len("plugin_"):].partition("_")
        return plugin if not inner or inner == plugin else f"{plugin}/{inner}"
    return server


def _host(url):
    try:
        h = urllib.parse.urlparse(url).hostname or ""
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def summarize(path):
    times, models = [], collections.Counter()
    tools, mcps, skills = collections.Counter(), collections.Counter(), collections.Counter()
    langs, sites = collections.Counter(), collections.Counter()
    session_id = cwd = None
    user_msgs = tool_calls = tokens_out = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            session_id = session_id or d.get("sessionId")
            cwd = cwd or d.get("cwd")
            t = _ts(d.get("timestamp") or "")
            if t:
                times.append(t)
            typ, msg = d.get("type"), d.get("message") or {}
            if typ == "user" and d.get("turnOrigin", (d.get("origin") or {}).get("kind")) == "human":
                user_msgs += 1
            elif typ == "user" and not d.get("toolUseResult") and isinstance(msg.get("content"), str):
                user_msgs += 1
            if typ != "assistant":
                continue
            if msg.get("model") and not msg["model"].startswith("<"):
                models[msg["model"]] += 1
            tokens_out += int((msg.get("usage") or {}).get("output_tokens") or 0)
            for c in msg.get("content") or []:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                name, inp = c.get("name") or "", c.get("input") or {}
                tool_calls += 1
                srv = mcp_server(name) if name.startswith("mcp__") else None
                if srv:
                    mcps[srv] += 1
                else:
                    tools[name] += 1
                if name == "Skill" and inp.get("skill"):
                    skills[str(inp["skill"])] += 1
                if name in EDIT_TOOLS:
                    p = inp.get("file_path") or inp.get("notebook_path") or ""
                    ext = os.path.splitext(p)[1].lstrip(".").lower()
                    if ext in EXT_LANG:
                        langs[EXT_LANG[ext]] += 1
                url = inp.get("url") if isinstance(inp.get("url"), str) else ""
                if url and (name == "WebFetch" or "navigate" in name or "tabs_create" in name):
                    h = _host(url)
                    if h and h not in ("localhost", "127.0.0.1"):
                        sites[h] += 1
    if not session_id or not times:
        return None
    times.sort()
    active = sum(min((b - a).total_seconds(), IDLE_CAP_S) for a, b in zip(times, times[1:]))
    project = (cwd or "").replace(HOME, "~")
    return {
        "session_id": session_id,
        "started_at": times[0].isoformat().replace("+00:00", "Z"),
        "ended_at": times[-1].isoformat().replace("+00:00", "Z"),
        "machine": socket.gethostname().split(".")[0],
        "project": project,
        "minutes": round(active / 60, 1),
        "user_msgs": user_msgs,
        "tool_calls": tool_calls,
        "languages": dict(langs.most_common(10)),
        "tools": dict(tools.most_common(15)),
        "mcps": dict(mcps.most_common(10)),
        "skills": dict(skills.most_common(10)),
        "sites": dict(sites.most_common(10)),
        "model": models.most_common(1)[0][0] if models else "",
        "tokens_out": tokens_out,
    }


# ---------- config + network ----------

def load_config():
    try:
        with open(CONFIG) as f:
            c = json.load(f)
        return c if c.get("endpoint") and c.get("key") else None
    except Exception:
        return None


def _http(method, url, key, body=None, timeout=6):
    """Return (status, text). Falls back to curl: some macOS Pythons lack CA certs."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"x-journal-key": key, "content-type": "application/json"}
    try:
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception:
        cmd = ["curl", "-sS", "--max-time", str(timeout), "-X", method, "-w", "\n%{http_code}",
               "-H", f"x-journal-key: {key}", "-H", "content-type: application/json", url]
        if data is not None:
            cmd += ["--data-binary", "@-"]
        try:
            out = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout + 2).stdout.decode()
            text, _, code = out.rpartition("\n")
            return int(code or 0), text
        except Exception:
            return 0, ""


def post_events(cfg, events):
    if not events:
        return True
    status, _ = _http("POST", cfg["endpoint"], cfg["key"], {"events": events}, timeout=20)
    return status == 200


def queue_append(events):
    os.makedirs(DIR, exist_ok=True)
    with open(QUEUE, "a") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def flush_queue(cfg):
    if not os.path.exists(QUEUE):
        return 0
    with open(QUEUE) as f:
        pending = [json.loads(l) for l in f if l.strip()]
    latest = {e["session_id"]: e for e in pending}  # keep the newest per session
    events = list(latest.values())
    sent = 0
    for i in range(0, len(events), 100):
        if not post_events(cfg, events[i:i + 100]):
            with open(QUEUE, "w") as f:
                for e in events[i:]:
                    f.write(json.dumps(e) + "\n")
            return sent
        sent += len(events[i:i + 100])
    os.remove(QUEUE)
    return sent


def stats_url(cfg):
    return cfg.get("stats_endpoint") or cfg["endpoint"].rstrip("/") + "-stats"


# ---------- commands ----------

def cmd_send():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        hook = {}
    path = hook.get("transcript_path")
    row = summarize(path) if path and os.path.exists(path) else None
    cfg = load_config()
    if not row or not cfg:
        return
    row["source"] = "hook"
    if not post_events(cfg, [row]):
        queue_append([row])


def cmd_card():
    cfg = load_config()
    if not cfg:
        return
    flush_queue(cfg)
    card = ""
    status, text = _http("GET", stats_url(cfg), cfg["key"], timeout=4)
    if status == 200:
        try:
            card = json.loads(text).get("card", "")
            with open(CARD_CACHE, "w") as f:
                f.write(card)
        except Exception:
            pass
    if not card and os.path.exists(CARD_CACHE):
        card = open(CARD_CACHE).read()
    if card:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
              "additionalContext": "About this user (basivo-journal, their own activity history): " + card}}))


def cmd_backfill():
    cfg = load_config()
    if not cfg:
        sys.exit("No config. Run: journal.py setup <endpoint> <key>")
    rows = []
    for p in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        r = summarize(p)
        if r and r["minutes"] > 0:
            r["source"] = "backfill"
            rows.append(r)
    ok = 0
    for i in range(0, len(rows), 50):
        if post_events(cfg, rows[i:i + 50]):
            ok += len(rows[i:i + 50])
        else:
            queue_append(rows[i:i + 50])
    hours = round(sum(r["minutes"] for r in rows) / 60, 1)
    print(json.dumps({"sessions_found": len(rows), "sent": ok, "queued": len(rows) - ok, "hours": hours}))


def cmd_stats():
    cfg = load_config()
    if not cfg:
        sys.exit("No config. Run: journal.py setup <endpoint> <key>")
    flush_queue(cfg)
    status, text = _http("GET", stats_url(cfg), cfg["key"], timeout=15)
    if status != 200:
        sys.exit(f"stats endpoint returned {status}")
    print(text)


def cmd_setup(endpoint, key):
    os.makedirs(DIR, exist_ok=True)
    os.chmod(DIR, 0o700)
    with open(CONFIG, "w") as f:
        json.dump({"endpoint": endpoint, "key": key}, f, indent=2)
    os.chmod(CONFIG, 0o600)
    print(f"saved {CONFIG}")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    try:
        if cmd == "send":
            cmd_send()
        elif cmd == "card":
            cmd_card()
        elif cmd == "backfill":
            cmd_backfill()
        elif cmd == "stats":
            cmd_stats()
        elif cmd == "summarize" and len(args) == 2:
            print(json.dumps(summarize(args[1]), indent=2))
        elif cmd == "setup" and len(args) == 3:
            cmd_setup(args[1], args[2])
        else:
            print(__doc__)
    except SystemExit:
        raise
    except Exception as e:  # a hook must never break the user's session
        if cmd in ("send", "card"):
            sys.exit(0)
        raise
