#!/usr/bin/env python3
"""Offline dashboard: one self-contained HTML file (data embedded, no server,
no internet) built from your local journal. Works forever, on any OS."""
import glob
import json
import os
import webbrowser

HOME = os.path.expanduser("~")


def _load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def build(root, out=None, open_it=True, with_chats=True):
    rows = [r for r in (_load(p) for p in glob.glob(os.path.join(root, "sessions", "*", "*", "*.json"))) if r]
    chats = {}
    if with_chats:
        for p in glob.glob(os.path.join(root, "chats", "*", "*", "*.json")):
            c = _load(p)
            if c and c.get("session_id"):
                chats[c["session_id"]] = [{"r": m["role"][0], "t": (m.get("ts") or "")[:16], "x": m["text"]} for m in c.get("messages") or []]
    data = json.dumps({"rows": rows, "chats": chats}, separators=(",", ":")).replace("</", "<\\/")
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_template.html"), encoding="utf-8") as f:
        html = f.read().replace("/*__DATA__*/null", data)
    out = out or os.path.join(os.path.dirname(root.rstrip("/\\")) or HOME, "journal-report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    if open_it:
        try:
            webbrowser.open("file://" + os.path.abspath(out).replace(os.sep, "/"))
        except Exception:
            pass
    return out
