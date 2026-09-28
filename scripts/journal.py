#!/usr/bin/env python3
"""basivo-journal: turn every Claude Code session into one small JSON file in
your own PRIVATE git repo (the permanent copy), updated live while you work.

Only counts and names are recorded: time spent, project folder, file
languages, tool / MCP / skill names, site hostnames, model, token totals.
Never chat text, file contents, or tool inputs.

Hooks (plain script, 0 tokens):
  journal.py checkpoint   Stop hook: save this session (throttled to 5 min)
  journal.py final        SessionEnd hook: save this session now
  journal.py start        SessionStart hook: catch-up sweep + "about me" card
Commands:
  journal.py sweep        save every session file changed since last sweep
  journal.py backfill     save every session found in ~/.claude/projects
  journal.py stats        print aggregated stats (JSON) from the local copy
  journal.py summarize <transcript.jsonl>   print one session's record
  journal.py setup <owner/repo>             clone your private data repo
  journal.py sync         commit + push now (foreground)
  journal.py install-sweeper / uninstall-sweeper   hourly sweep via launchd (macOS)
"""
import collections
import re
import datetime as dt
import glob
import json
import os
import socket
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mask_pii import mask, mask_prose  # noqa: E402  (same masker as basivo-operator)

HOME = os.path.expanduser("~")
DIR = os.environ.get("BASIVO_JOURNAL_HOME", os.path.join(HOME, ".basivo-journal"))
CONFIG = os.path.join(DIR, "config.json")
STATE = os.path.join(DIR, "state.json")
CARD_CACHE = os.path.join(DIR, "card.txt")
PROJECTS = os.path.join(HOME, ".claude", "projects")
IDLE_CAP_S = 5 * 60        # gaps longer than this count as idle, not work
CHECKPOINT_EVERY_S = 5 * 60
PUSH_EVERY_S = 3 * 60
PLIST = os.path.join(HOME, "Library", "LaunchAgents", "in.basivo.journal.sweep.plist")

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
MSG_MAX_CHARS = 6000        # per stored chat message
_NOISE = re.compile(r"<(system-reminder|ide_[a-z_]+|local-command-stdout|local-command-caveat|command-message|command-args)>.*?</\1>", re.S)


def clean_text(text):
    """Chat text as the user saw it: drop injected context tags, mask secrets, cap length."""
    text = _NOISE.sub("", text or "")
    text = re.sub(r"<command-name>(.*?)</command-name>", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > MSG_MAX_CHARS:
        text = text[:MSG_MAX_CHARS] + f"\n… [{len(text) - MSG_MAX_CHARS} more characters not stored]"
    return mask_prose(text)


def _content_text(content):
    if isinstance(content, str):
        return content
    return "\n".join(c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text")


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
    session_id = cwd = title = None
    user_msgs = tool_calls = tokens_out = 0
    chat = []
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
            if typ == "ai-title" and d.get("aiTitle"):
                title = d["aiTitle"]
            human = typ == "user" and not d.get("isSidechain") and (
                d.get("turnOrigin", (d.get("origin") or {}).get("kind")) == "human"
                or (not d.get("toolUseResult") and isinstance(msg.get("content"), str)))
            if human:
                user_msgs += 1
                txt = clean_text(_content_text(msg.get("content")))
                if txt:
                    chat.append({"role": "user", "ts": d.get("timestamp"), "text": txt})
            if typ == "assistant" and not d.get("isSidechain"):
                txt = _content_text(msg.get("content"))
                if txt.strip():
                    txt = clean_text(txt)
                    if chat and chat[-1]["role"] == "assistant":  # one reply may span several records
                        chat[-1]["text"] = (chat[-1]["text"] + "\n\n" + txt)[: MSG_MAX_CHARS * 2]
                    else:
                        chat.append({"role": "assistant", "ts": d.get("timestamp"), "text": txt})
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
    active = 0.0
    by_hour, by_day = collections.Counter(), collections.Counter()
    for a, b in zip(times, times[1:]):
        gap = min((b - a).total_seconds(), IDLE_CAP_S)
        active += gap
        local = a.astimezone()  # the machine's local time: "when you work"
        by_hour[str(local.hour)] += gap / 60
        by_day[local.date().isoformat()] += gap / 60
    first_prompt = next((m["text"] for m in chat if m["role"] == "user"), "")
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
        "title": mask(title or "")[:120],
        "first_prompt": " ".join(first_prompt.split())[:200],
        "active_by_hour": {k: round(v, 1) for k, v in sorted(by_hour.items(), key=lambda x: int(x[0])) if v >= 0.1},
        "active_by_day": {k: round(v, 1) for k, v in sorted(by_day.items()) if v >= 0.1},
        "_chat": chat,
    }


# ---------- config + state ----------

def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{time.time_ns()}.tmp"  # unique: hooks and the sweeper may write at once
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def data_dir():
    d = _load(CONFIG, {}).get("data_dir") or os.path.join(DIR, "data")
    return d if os.path.isdir(os.path.join(d, ".git")) else None


# ---------- storage: one file per session ----------

def session_path(root, row):
    y, m = (row.get("started_at") or "0000-00")[:7].split("-")
    return os.path.join(root, "sessions", y, m, row["session_id"] + ".json")


def write_row(root, row):
    """Write the session file if its content changed. Returns True if written."""
    path = session_path(root, row)
    old = _load(path, None)
    if old == row:
        return False
    _save(path, row)
    return True


def chat_path(root, row):
    return session_path(root, row).replace(os.sep + "sessions" + os.sep, os.sep + "chats" + os.sep, 1)


def record_chat():
    return _load(CONFIG, {}).get("record_chat", True)


def save_transcript(root, path, source):
    row = summarize(path) if path and os.path.exists(path) else None
    if not row or row["minutes"] <= 0:
        return False
    chat = row.pop("_chat", [])
    wrote_chat = False
    if record_chat() and chat:
        doc = {"session_id": row["session_id"], "title": row["title"], "project": row["project"],
               "started_at": row["started_at"], "messages": chat}
        cp = chat_path(root, row)
        if _load(cp, None) != doc:
            _save(cp, doc)
            wrote_chat = True
    row["source"] = source
    old = _load(session_path(root, row), None)
    if old and old.get("source") != source and source == "sweep":
        row["source"] = old["source"]  # keep hook/backfill label on a sweep refresh
    return write_row(root, row) or wrote_chat


def _git(root, *args, timeout=60):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=timeout)


def commit(root, msg):
    _git(root, "add", "-A", "sessions", "chats")
    if _git(root, "diff", "--cached", "--quiet").returncode == 0:
        return False
    _git(root, "commit", "-q", "-m", msg)
    return True


def push_now(root):
    _git(root, "pull", "-q", "--rebase", "--autostash", timeout=60)
    ok = _git(root, "push", "-q", "-u", "origin", "HEAD", timeout=90).returncode == 0
    if ok:
        st = _load(STATE, {})
        st["last_push"] = time.time()
        _save(STATE, st)
    return ok


def push_background(root, force=False):
    st = _load(STATE, {})
    if not force and time.time() - st.get("last_push_try", 0) < PUSH_EVERY_S:
        return
    st["last_push_try"] = time.time()
    _save(STATE, st)
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "sync"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                     start_new_session=True)


# ---------- stats (computed from the local copy) ----------

def load_rows(root):
    rows = []
    for p in glob.glob(os.path.join(root, "sessions", "*", "*", "*.json")):
        r = _load(p, None)
        if r and r.get("session_id"):
            rows.append(r)
    return rows


def _top(counter, n=8):
    return [{"name": k, "value": round(v, 1)} for k, v in counter.most_common(n)]


def aggregate(rows, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)

    def t(r):
        return _ts(r.get("started_at") or "") or now

    def summary(sel):
        c = {k: collections.Counter() for k in ("projects", "languages", "tools", "mcps", "skills", "sites")}
        tot = collections.Counter()
        for r in sel:
            tot["minutes"] += r.get("minutes", 0)
            for k in ("user_msgs", "tool_calls", "tokens_out"):
                tot[k] += r.get(k, 0)
            c["projects"][(r.get("project") or "unknown").rstrip("/").split("/")[-1]] += r.get("minutes", 0) / 60
            for k in ("languages", "tools", "mcps", "skills", "sites"):
                c[k].update(r.get(k) or {})
        return {"sessions": len(sel), "hours": round(tot["minutes"] / 60, 1), "user_msgs": tot["user_msgs"],
                "tool_calls": tot["tool_calls"], "tokens_out": tot["tokens_out"],
                **{"top_" + k: _top(v) for k, v in c.items()}}

    within = lambda d: [r for r in rows if (now - t(r)).total_seconds() <= d * 86400]
    days = sorted({t(r).date().isoformat() for r in rows})
    streak, d = 0, now.date()
    if d.isoformat() not in days:
        d -= dt.timedelta(days=1)  # today not worked yet doesn't break the streak
    while d.isoformat() in days:
        streak, d = streak + 1, d - dt.timedelta(days=1)
    first = {}
    for r in sorted(rows, key=t):
        for kind in ("languages", "mcps", "skills"):
            for k in r.get(kind) or {}:
                first.setdefault(f"{kind[:-1]}:{k}", t(r).date().isoformat())
    recent = [{"name": k, "first": v} for k, v in first.items()
              if (now.date() - dt.date.fromisoformat(v)).days <= 30]
    by_day = collections.Counter()
    for r in within(30):
        by_day[t(r).date().isoformat()] += r.get("minutes", 0)
    all_, week, month = summary(rows), summary(within(7)), summary(within(30))
    names = lambda lst: ", ".join(x["name"] for x in lst[:4]) or "n/a"
    card = (f"Journal: {all_['sessions']} sessions, {all_['hours']} h since {days[0] if days else 'n/a'}; "
            f"this week {week['hours']} h, streak {streak} d. Main projects: {names(month['top_projects'])}. "
            f"Languages: {names(all_['top_languages'])}. Tools/MCPs: {names(month['top_mcps'])}.")
    return {"ok": True, "generated_at": now.isoformat(), "first_day": days[0] if days else None,
            "active_days": len(days), "streak_days": streak, "all_time": all_, "last_7_days": week,
            "last_30_days": month, "minutes_by_day_30": dict(sorted(by_day.items())),
            "new_in_last_30_days": recent, "card": card}


# ---------- commands ----------

def _hook_input():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def cmd_checkpoint(force=False):
    root = data_dir()
    hook = _hook_input()
    sid, path = hook.get("session_id"), hook.get("transcript_path")
    if not root or not path:
        return
    st = _load(STATE, {})
    last = st.setdefault("checkpoints", {}).get(sid or path, 0)
    if not force and time.time() - last < CHECKPOINT_EVERY_S:
        return
    st["checkpoints"][sid or path] = time.time()
    # keep state small: forget checkpoints older than a week
    st["checkpoints"] = {k: v for k, v in st["checkpoints"].items() if time.time() - v < 7 * 86400}
    _save(STATE, st)
    if save_transcript(root, path, "hook"):
        commit(root, f"session {sid or 'update'}")
    push_background(root, force=force)


def sweep(root, all_files=False):
    st = _load(STATE, {})
    since = 0 if all_files else st.get("last_sweep", 0)
    started = time.time()
    changed = 0
    for p in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        try:
            if os.path.getmtime(p) < since:
                continue
        except OSError:
            continue
        if save_transcript(root, p, "backfill" if all_files else "sweep"):
            changed += 1
    st = _load(STATE, {})
    st["last_sweep"] = started
    _save(STATE, st)
    if changed:
        commit(root, f"{'backfill' if all_files else 'sweep'}: {changed} session(s)")
    return changed


def cmd_start():
    hook = _hook_input()
    root = data_dir()
    if not root:
        return
    sweep(root)
    push_background(root, force=True)
    card = aggregate(load_rows(root))["card"]
    try:
        import memory
        db = memory.connect()
        memory.refresh(db, root)
        recap = memory.project_recap(db, hook.get("cwd") or os.getcwd())
        if recap:
            card += " " + recap
    except Exception:
        pass  # the card must never break session start
    with open(CARD_CACHE, "w") as f:
        f.write(card)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
          "additionalContext": "About this user (basivo-journal, their own activity history): " + card}}))


def cmd_setup(repo):
    os.makedirs(DIR, exist_ok=True)
    os.chmod(DIR, 0o700)
    target = os.path.join(DIR, "data")
    if not os.path.isdir(os.path.join(target, ".git")):
        url = repo if "://" in repo or repo.startswith("git@") else f"https://github.com/{repo}.git"
        r = subprocess.run(["git", "clone", "-q", url, target], capture_output=True, text=True)
        if r.returncode:
            sys.exit("clone failed: " + r.stderr.strip())
    cfg = _load(CONFIG, {})
    cfg["data_dir"] = target
    _save(CONFIG, cfg)
    os.chmod(CONFIG, 0o600)
    print(f"data repo ready at {target}")


def cmd_install_sweeper():
    # copy the script to a stable path: plugin cache paths change on every update
    stable = os.path.join(DIR, "bin", "journal.py")
    os.makedirs(os.path.dirname(stable), exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("journal.py", "mask_pii.py", "memory.py"):  # journal.py imports these
        with open(os.path.join(here, name)) as src, open(os.path.join(os.path.dirname(stable), name), "w") as dst:
            dst.write(src.read())
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>in.basivo.journal.sweep</string>
  <key>ProgramArguments</key><array>
    <string>{sys.executable}</string><string>{stable}</string><string>sweep-push</string>
  </array>
  <key>StartInterval</key><integer>3600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string>{os.path.join(DIR, 'sweeper.log')}</string>
</dict></plist>
"""
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, "w") as f:
        f.write(plist)
    subprocess.run(["launchctl", "unload", PLIST], capture_output=True)
    subprocess.run(["launchctl", "load", PLIST], check=True)
    print(f"hourly sweep installed: {PLIST}")


def cmd_uninstall_sweeper():
    subprocess.run(["launchctl", "unload", PLIST], capture_output=True)
    if os.path.exists(PLIST):
        os.remove(PLIST)
    print("hourly sweep removed")


def main(args):
    cmd = args[0] if args else ""
    root = data_dir()
    need_root = {"sweep", "sweep-push", "backfill", "stats", "sync"}
    if cmd in need_root and not root:
        sys.exit("No data repo. Run: journal.py setup <owner/repo>")
    if cmd == "checkpoint":
        cmd_checkpoint()
    elif cmd == "final":
        cmd_checkpoint(force=True)
    elif cmd == "start":
        cmd_start()
    elif cmd == "sweep":
        print(json.dumps({"changed": sweep(root)}))
    elif cmd == "sweep-push":
        sweep(root)
        push_now(root)
    elif cmd == "backfill":
        n = sweep(root, all_files=True)
        ok = push_now(root)
        rows = load_rows(root)
        print(json.dumps({"sessions_saved_or_updated": n, "sessions_total": len(rows),
                          "hours": round(sum(r.get("minutes", 0) for r in rows) / 60, 1), "pushed": ok}))
    elif cmd == "stats":
        print(json.dumps(aggregate(load_rows(root))))
    elif cmd == "sync":
        commit(root, "sync")
        push_now(root)
    elif cmd == "summarize" and len(args) == 2:
        row = summarize(args[1]) or {}
        chat = row.pop("_chat", [])
        print(json.dumps({**row, "chat_messages": len(chat)}, indent=2))
    elif cmd == "setup" and len(args) == 2:
        cmd_setup(args[1])
    elif cmd == "install-sweeper":
        cmd_install_sweeper()
    elif cmd == "uninstall-sweeper":
        cmd_uninstall_sweeper()
    else:
        print(__doc__)


if __name__ == "__main__":
    hook_cmds = {"checkpoint", "final", "start", "sync", "sweep-push"}
    try:
        main(sys.argv[1:])
    except SystemExit:
        raise
    except Exception:
        if (sys.argv[1:2] or [""])[0] in hook_cmds:
            sys.exit(0)  # a hook must never break the user's session
        raise
