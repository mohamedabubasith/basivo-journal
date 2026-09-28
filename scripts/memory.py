#!/usr/bin/env python3
"""basivo-journal memory: a local full-text index over your saved chats, so
Claude can look up past work instead of re-reading whole transcripts.

The index is a cache: ~/.basivo-journal/index.db (SQLite FTS5). It is rebuilt
incrementally from ~/.basivo-journal/data (your private repo clone) whenever a
query runs, so it never needs syncing between machines.
"""
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sqlite3

HOME = os.path.expanduser("~")
DIR = os.environ.get("BASIVO_JOURNAL_HOME", os.path.join(HOME, ".basivo-journal"))
SNIPPET_WORDS = 24
MAX_OUT = 6000  # hard cap on characters returned to Claude per call


def data_dir():
    try:
        with open(os.path.join(DIR, "config.json")) as f:
            d = json.load(f).get("data_dir")
    except Exception:
        d = None
    d = d or os.path.join(DIR, "data")
    return d if os.path.isdir(d) else None


def connect(path=None):
    db = sqlite3.connect(path or os.path.join(DIR, "index.db"))
    db.executescript("""
      create table if not exists files(path text primary key, mtime real);
      create table if not exists sessions(sid text primary key, day text, started text, project text,
        title text, minutes real, msgs integer, langs text, mcps text, skills text, model text);
      create virtual table if not exists msgs using fts5(
        sid unindexed, day unindexed, project unindexed, role unindexed, pos unindexed, text,
        tokenize='porter unicode61');
    """)
    return db


def _load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def refresh(db, root):
    """Re-index only files that changed since last time. Returns files updated."""
    known = dict(db.execute("select path, mtime from files"))
    seen, changed = set(), 0
    for kind in ("sessions", "chats"):
        for p in glob.glob(os.path.join(root, kind, "*", "*", "*.json")):
            seen.add(p)
            m = os.path.getmtime(p)
            if known.get(p) == m:
                continue
            doc = _load(p)
            if not doc or not doc.get("session_id"):
                continue
            sid = doc["session_id"]
            if kind == "sessions":
                top = lambda k: ",".join(sorted(doc.get(k) or {}, key=lambda x: -(doc.get(k) or {})[x])[:5])
                db.execute("insert or replace into sessions values (?,?,?,?,?,?,?,?,?,?,?)", (
                    sid, (doc.get("started_at") or "")[:10], doc.get("started_at"), doc.get("project", ""),
                    doc.get("title") or doc.get("first_prompt") or "", doc.get("minutes", 0), doc.get("user_msgs", 0),
                    top("languages"), top("mcps"), top("skills"), doc.get("model", "")))
            else:
                db.execute("delete from msgs where sid = ?", (sid,))
                seen_hash = set()
                project = (doc.get("project") or "").rstrip("/").split("/")[-1]
                for i, msg in enumerate(doc.get("messages") or []):
                    text = msg.get("text") or ""
                    h = hashlib.sha1(text.encode()).hexdigest()
                    if not text.strip() or h in seen_hash:  # same pasted block repeated = index once
                        continue
                    seen_hash.add(h)
                    day = (msg.get("ts") or doc.get("started_at") or "")[:10]
                    db.execute("insert into msgs values (?,?,?,?,?,?)", (sid, day, project, msg.get("role"), i, text))
            db.execute("insert or replace into files values (?,?)", (p, m))
            changed += 1
    for p in set(known) - seen:  # file deleted in the repo
        db.execute("delete from files where path = ?", (p,))
    db.commit()
    return changed


def _fts_query(q, mode="and"):
    words = re.findall(r"[\w][\w.+#-]*", q.lower())
    words = [w for w in words if len(w) > 1][:12]
    if not words:
        return None
    return (" AND " if mode == "and" else " OR ").join('"' + w.replace('"', "") + '"' for w in words)


def _clip(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _cap(text):
    return text if len(text) <= MAX_OUT else text[:MAX_OUT] + "\n… [truncated]"


def search(db, query, project=None, since=None, role=None, limit=5):
    limit = max(1, min(int(limit or 5), 10))
    where, args = ["msgs match ?"], []
    if project:
        where.append("project = ?")
        args.append(project)
    if since:
        where.append("day >= ?")
        args.append(since)
    if role in ("user", "assistant"):
        where.append("role = ?")
        args.append(role)
    hits = []
    for mode in ("and", "or"):  # all words first, then any word
        fq = _fts_query(query, mode)
        if not fq:
            return "Give me a few words to search for."
        sql = (f"select sid, day, project, role, pos, snippet(msgs, 5, '«', '»', '…', {SNIPPET_WORDS}) "
               f"from msgs where {' and '.join(where)} order by rank limit ?")
        hits = db.execute(sql, [fq, *args, limit * 3]).fetchall()
        if hits:
            break
    out, per_session = [], {}
    for sid, day, proj, r, pos, snip in hits:
        if per_session.get(sid, 0) >= 2:  # spread results across sessions
            continue
        per_session[sid] = per_session.get(sid, 0) + 1
        title = (db.execute("select title from sessions where sid = ?", (sid,)).fetchone() or [""])[0]
        out.append(f"- {day} · {proj} · \"{_clip(title, 70)}\" · {r} · id {sid[:8]} msg {pos}\n  {_clip(snip, 260)}")
        if len(out) >= limit:
            break
    if not out:
        return f"No past chats match “{query}”."
    return _cap(f"{len(out)} match(es) for “{query}” (open one with journal_session):\n" + "\n".join(out))


def _find_sid(db, sid):
    sid = (sid or "").strip()
    if len(sid) < 6:
        return None
    row = db.execute("select sid from sessions where sid like ? limit 2", (sid + "%",)).fetchall()
    if len(row) == 1:
        return row[0][0]
    row = db.execute("select distinct sid from msgs where sid like ? limit 2", (sid + "%",)).fetchall()
    return row[0][0] if len(row) == 1 else None


def session(db, root, sid, query=None, around=None, max_messages=8):
    full = _find_sid(db, sid)
    if not full:
        return f"No session with id starting “{sid}”."
    meta = db.execute("select day, project, title, minutes, msgs, langs, mcps, skills, model from sessions where sid = ?", (full,)).fetchone()
    doc = None
    for p in glob.glob(os.path.join(root, "chats", "*", "*", full + ".json")):
        doc = _load(p)
    msgs = (doc or {}).get("messages") or []
    head = ""
    if meta:
        day, proj, title, minutes, n, langs, mcps, skills, model = meta
        head = (f"Session {full[:8]} · {day} · {proj.replace(HOME, '~')} · \"{title}\" · {round(minutes)} active min · "
                f"{n} user msgs · {model}\nlanguages: {langs or '-'} · MCPs: {mcps or '-'} · skills: {skills or '-'}\n")
    if not msgs:
        return head + "(no chat saved for this session)"
    max_messages = max(1, min(int(max_messages or 8), 20))
    if around is not None:
        c = int(around)
        pick = range(max(0, c - 2), min(len(msgs), c + 3))
    elif query:
        fq = _fts_query(query, "or")
        hit = [r[0] for r in db.execute("select pos from msgs where sid = ? and msgs match ? order by rank limit 3", (full, fq))] if fq else []
        pick = sorted({j for c in hit for j in range(max(0, c - 1), min(len(msgs), c + 2))})
        if not pick:
            pick = range(0, min(len(msgs), max_messages))
    else:
        pick = range(0, min(len(msgs), max_messages))
    per = max(400, MAX_OUT // max(1, len(list(pick))))
    body = "\n".join(f"[{i}] {msgs[i]['role']} {(msgs[i].get('ts') or '')[:16]}: {_clip(msgs[i]['text'], per)}" for i in list(pick)[:max_messages])
    more = f"\n({len(msgs)} messages in total; pass around=<n> to read elsewhere)" if len(msgs) > max_messages else ""
    return _cap(head + body + more)


def recent(db, project=None, limit=5):
    limit = max(1, min(int(limit or 5), 15))
    if project:
        rows = db.execute("select sid, day, project, title, minutes, langs from sessions where project like ? order by started desc limit ?",
                          ("%" + project, limit)).fetchall()
    else:
        rows = db.execute("select sid, day, project, title, minutes, langs from sessions order by started desc limit ?", (limit,)).fetchall()
    if not rows:
        return "No sessions found" + (f" for project “{project}”." if project else ".")
    return "\n".join(f"- {d} · {p.rstrip('/').split('/')[-1]} · \"{_clip(t, 80)}\" · {round(m)} min · {l or '-'} · id {s[:8]}"
                     for s, d, p, t, m, l in rows)


def stats(db, days=7):
    days = max(1, min(int(days or 7), 3650))
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    tot = db.execute("select count(*), coalesce(sum(minutes),0) from sessions where day >= ?", (since,)).fetchone()
    proj = db.execute("select project, sum(minutes) m from sessions where day >= ? group by project order by m desc limit 5", (since,)).fetchall()
    langs = {}
    for (l,) in db.execute("select langs from sessions where day >= ?", (since,)):
        for x in (l or "").split(","):
            if x:
                langs[x] = langs.get(x, 0) + 1
    top_l = ", ".join(k for k, _ in sorted(langs.items(), key=lambda kv: -kv[1])[:5]) or "-"
    top_p = ", ".join(f"{p.rstrip('/').split('/')[-1]} ({round(m / 60, 1)} h)" for p, m in proj) or "-"
    return f"Last {days} days: {tot[0]} sessions, {round(tot[1] / 60, 1)} h. Projects: {top_p}. Languages: {top_l}."


def project_recap(db, cwd, limit=2):
    """One short line about the last sessions in this folder (for the start-of-session card)."""
    if not cwd:
        return ""
    proj = cwd.replace(HOME, "~").rstrip("/")
    rows = db.execute("select day, title from sessions where project = ? order by started desc limit ?", (proj, limit)).fetchall()
    if not rows:
        return ""
    parts = [f"{d} “{_clip(t, 60)}”" for d, t in rows]
    return "Last time in this project: " + "; before that: ".join(parts) + ". Use journal_search to look up details."


def open_index():
    root = data_dir()
    if not root:
        return None, None
    os.makedirs(DIR, exist_ok=True)
    db = connect()
    refresh(db, root)
    return db, root
