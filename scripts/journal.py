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
  journal.py setup <owner/repo>             sync with your private GitHub repo (API, no git)
  journal.py setup <folder>                 or use a folder (e.g. Google Drive) instead
  journal.py set-token                      save a GitHub token (typed hidden)
  journal.py mirror auto|<folder>|off       also keep a copy in Google Drive (or any folder)
  journal.py report [out.html]              offline HTML dashboard, opens in your browser
  journal.py sync         commit + push now (foreground)
  journal.py doctor       what this machine still needs (git, GitHub login, repo)
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
    return d if os.path.isdir(d) else None


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


def is_git(root):
    return os.path.isdir(os.path.join(root, ".git"))


def commit(root, msg):
    """Legacy git clones only: record changes locally before a git push."""
    if not is_git(root):
        return False
    _git(root, "add", "-A", "sessions", "chats")
    if _git(root, "diff", "--cached", "--quiet").returncode == 0:
        return False
    _git(root, "commit", "-q", "-m", msg)
    return True


def remotes():
    import storage
    cfg = _load(CONFIG, {})
    out = []
    if cfg.get("github_repo") and cfg.get("github_token"):
        out.append(storage.GitHubRemote(cfg["github_repo"], cfg["github_token"], cfg.get("github_branch", "main")))
    if cfg.get("mirror_dir"):
        out.append(storage.FolderRemote(cfg["mirror_dir"]))
    return out


def push_now(root):
    """Sync with every configured remote (GitHub API, Google Drive folder, ...).
    Returns (all_ok, results). A git clone without a token still syncs via git."""
    import storage
    results = []
    if is_git(root) and not _load(CONFIG, {}).get("github_token"):
        commit(root, "sync")
        _git(root, "pull", "-q", "--rebase", "--autostash", timeout=60)
        ok = _git(root, "push", "-q", "-u", "origin", "HEAD", timeout=90).returncode == 0
        results.append({"remote": "git origin", "ok": ok})
    for rm in remotes():
        try:
            r = storage.sync(root, rm, f"journal sync from {socket.gethostname().split('.')[0]}")
            r["ok"] = True
        except storage.HttpError as e:
            r = {"remote": rm.label, "ok": False, "status": e.status, "error": str(e)[:160]}
        except Exception as e:  # offline, drive not mounted, ...: try again next time
            r = {"remote": rm.label, "ok": False, "error": str(e)[:160]}
        results.append(r)
    ok = all(r["ok"] for r in results)
    st = _load(STATE, {})
    st["last_sync"] = {"at": time.time(), "results": results}
    if ok and results:
        st["last_push"] = time.time()
    _save(STATE, st)
    return ok, results


def push_background(root, force=False):
    st = _load(STATE, {})
    if not force and time.time() - st.get("last_push_try", 0) < PUSH_EVERY_S:
        return
    st["last_push_try"] = time.time()
    _save(STATE, st)
    kw = {"creationflags": 0x00000008} if os.name == "nt" else {"start_new_session": True}  # DETACHED_PROCESS
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "sync"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, **kw)


def sync_notice():
    """One line for the session card when syncing is failing, else ''."""
    res = (_load(STATE, {}).get("last_sync") or {}).get("results") or []
    bad = [r for r in res if not r.get("ok")]
    if not bad:
        return ""
    if any(r.get("status") == 401 for r in bad):
        return "Note: journal sync to GitHub is paused because the token expired; sessions are kept locally. Tell the user to run /journal-setup to add a new token."
    return "Note: journal sync is failing (" + "; ".join(r["remote"] for r in bad) + "); sessions are kept locally and retried."


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
    notice = sync_notice()
    if notice:
        card += " " + notice
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


def _write_config(**changes):
    os.makedirs(DIR, exist_ok=True)
    try:
        os.chmod(DIR, 0o700)
    except OSError:
        pass
    cfg = _load(CONFIG, {})
    for k, v in changes.items():
        if v is None:
            cfg.pop(k, None)
        else:
            cfg[k] = v
    _save(CONFIG, cfg)
    try:
        os.chmod(CONFIG, 0o600)
    except OSError:
        pass
    return cfg


def token_url(repo=""):
    # contents / metadata / expires_in are honored by GitHub's form; target_name is left out on
    # purpose (it only pre-fills visually: github.com/orgs/community/discussions/188111)
    q = ("name=basivo-journal&description=basivo-journal+sync+for+your+private+data+repo"
         "&expires_in=365&contents=write&metadata=read")
    return "https://github.com/settings/personal-access-tokens/new?" + q


def cmd_setup(target):
    """setup <owner/repo> : GitHub repo via API (token needed first: journal.py set-token)
    setup <folder>       : use a folder (e.g. Google Drive) as the only sync place"""
    import storage
    local = os.path.join(DIR, "data")
    os.makedirs(os.path.join(local, "sessions"), exist_ok=True)
    looks_repo = "/" in target and not os.path.exists(os.path.expanduser(target)) and target.count("/") == 1 and not target.startswith(("~", "/", "."))
    if looks_repo:
        cfg = _write_config(data_dir=local, github_repo=target)
        if not cfg.get("github_token"):
            print(json.dumps({"ok": False, "need": "token", "repo": target, "create_token": token_url(target),
                              "then_run": "journal.py set-token"}))
            return
        ok, msg = storage.GitHubRemote(target, cfg["github_token"]).check()
        if not ok:
            print(json.dumps({"ok": False, "repo": target, "error": msg, "create_token": token_url(target)}))
            return
    else:
        _write_config(data_dir=local, mirror_dir=os.path.expanduser(target))
    ok, results = push_now(local)
    rows = load_rows(local)
    print(json.dumps({"ok": ok, "data_dir": local, "sessions": len(rows), "sync": results}))


def cmd_set_token(token=None):
    """Save a GitHub token (typed hidden, never echoed) and check it can write to the repo."""
    import getpass
    import storage
    token = (token or os.environ.get("BASIVO_JOURNAL_TOKEN") or getpass.getpass("Paste your GitHub token (hidden): ")).strip()
    if not token:
        sys.exit("no token given")
    cfg = _load(CONFIG, {})
    repo = cfg.get("github_repo")
    if repo:
        ok, msg = storage.GitHubRemote(repo, token).check()
        if not ok:
            sys.exit(f"token not saved: {msg}")
    _write_config(github_token=token)
    print(f"token saved to {CONFIG} (readable only by you)" + (f"; it can write to {repo}" if repo else ""))


def cmd_mirror(arg):
    """mirror auto | <folder> | off : keep a copy in a synced folder such as Google Drive."""
    import storage
    if arg == "off":
        _write_config(mirror_dir=None)
        print("mirror turned off (existing copy left in place)")
        return
    if arg == "auto":
        gd = storage.find_google_drive()
        if not gd:
            sys.exit("Google Drive for desktop not found. Install it from https://www.google.com/drive/download/ , "
                     "sign in, then run: journal.py mirror auto   (or pass the folder path)")
        arg = os.path.join(gd, "basivo-journal")
    _write_config(mirror_dir=os.path.expanduser(arg))
    root = data_dir()
    if root:
        ok, results = push_now(root)
        print(json.dumps({"ok": ok, "mirror": arg, "sync": results}))
    else:
        print(json.dumps({"ok": True, "mirror": arg}))


def cmd_doctor():
    """What this machine still needs, as JSON for /journal-setup. No git/gh/brew required."""
    import storage
    cfg = _load(CONFIG, {})
    root = data_dir()
    checks = {"os": sys.platform, "python": sys.version.split()[0], "python_path": sys.executable,
              "data_dir": root, "sessions_local": len(load_rows(root)) if root else 0,
              "record_chat": record_chat(), "google_drive": storage.find_google_drive(),
              "sweeper_installed": sweeper_installed()}
    fix = []
    if not root:
        fix.append("no journal data yet: run /journal-setup <owner/repo>")
    if cfg.get("github_repo"):
        if cfg.get("github_token"):
            ok, msg = storage.GitHubRemote(cfg["github_repo"], cfg["github_token"]).check()
            checks["github"] = {"repo": cfg["github_repo"], "ok": ok, "detail": msg}
            if not ok:
                fix.append(f"GitHub: {msg}. Create a token: {token_url(cfg['github_repo'])} then run: journal.py set-token")
        else:
            checks["github"] = {"repo": cfg["github_repo"], "ok": False, "detail": "no token on this machine"}
            fix.append(f"add a GitHub token: create it at {token_url(cfg['github_repo'])} then run: journal.py set-token")
    elif root and is_git(root):
        checks["github"] = {"mode": "legacy git clone", "ok": True, "detail": "works; add a token to drop the git dependency"}
    if cfg.get("mirror_dir"):
        checks["mirror"] = {"dir": cfg["mirror_dir"], "ok": os.path.isdir(cfg["mirror_dir"])}
        if not checks["mirror"]["ok"]:
            fix.append("mirror folder missing (is Google Drive running and signed in?)")
    last = (_load(STATE, {}).get("last_sync") or {})
    checks["last_sync"] = last.get("results")
    checks["ready"] = not fix
    checks["fix"] = fix
    print(json.dumps(checks, indent=1))


# ---------- background sweep, per OS ----------

TASK = "basivo-journal-sweep"


def sweeper_installed():
    if sys.platform == "darwin":
        return os.path.exists(PLIST)
    if os.name == "nt":
        return subprocess.run(["schtasks", "/Query", "/TN", TASK], capture_output=True).returncode == 0
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return TASK in (r.stdout or "")


def cmd_install_sweeper():
    # copy the script to a stable path: plugin cache paths change on every update
    stable = os.path.join(DIR, "bin", "journal.py")
    os.makedirs(os.path.dirname(stable), exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("journal.py", "mask_pii.py", "memory.py", "storage.py"):  # journal.py imports these
        with open(os.path.join(here, name)) as src, open(os.path.join(os.path.dirname(stable), name), "w") as dst:
            dst.write(src.read())
    cmd = [sys.executable, stable, "sweep-push"]
    if os.name == "nt":
        tr = " ".join(f'"{c}"' for c in cmd)
        subprocess.run(["schtasks", "/Create", "/F", "/SC", "HOURLY", "/TN", TASK, "/TR", tr], check=True, capture_output=True)
        print(f"hourly sweep installed (Task Scheduler: {TASK})")
        return
    if sys.platform != "darwin":
        line = " ".join(f"'{c}'" for c in cmd) + f" >/dev/null 2>&1 # {TASK}"
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout or ""
        keep = [l for l in cur.splitlines() if TASK not in l]
        subprocess.run(["crontab", "-"], input="\n".join(keep + [f"17 * * * * {line}"]) + "\n", text=True, check=True)
        print("hourly sweep installed (crontab)")
        return
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
    if os.name == "nt":
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK], capture_output=True)
    elif sys.platform != "darwin":
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout or ""
        subprocess.run(["crontab", "-"], input="\n".join(l for l in cur.splitlines() if TASK not in l) + "\n", text=True)
    else:
        subprocess.run(["launchctl", "unload", PLIST], capture_output=True)
        if os.path.exists(PLIST):
            os.remove(PLIST)
    print("hourly sweep removed")


def main(args):
    cmd = args[0] if args else ""
    root = data_dir()
    need_root = {"sweep", "sweep-push", "backfill", "stats", "sync"}
    if cmd in need_root and not root:
        sys.exit("No journal data on this machine. Run: journal.py setup <owner/repo>")
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
        ok, _ = push_now(root)
        rows = load_rows(root)
        print(json.dumps({"sessions_saved_or_updated": n, "sessions_total": len(rows),
                          "hours": round(sum(r.get("minutes", 0) for r in rows) / 60, 1), "pushed": ok}))
    elif cmd == "stats":
        print(json.dumps(aggregate(load_rows(root))))
    elif cmd == "sync":
        ok, results = push_now(root)
        print(json.dumps({"ok": ok, "sync": results}))
    elif cmd == "summarize" and len(args) == 2:
        row = summarize(args[1]) or {}
        chat = row.pop("_chat", [])
        print(json.dumps({**row, "chat_messages": len(chat)}, indent=2))
    elif cmd == "setup" and len(args) == 2:
        cmd_setup(args[1])
    elif cmd == "doctor":
        cmd_doctor()
    elif cmd == "set-token":
        cmd_set_token(args[1] if len(args) > 1 else None)
    elif cmd == "mirror" and len(args) == 2:
        cmd_mirror(args[1])
    elif cmd == "report":
        import report
        print(report.build(root or sys.exit("No journal data on this machine."), args[1] if len(args) > 1 else None))
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
