#!/usr/bin/env python3
"""Run: python3 tests/test_storage.py  (exit 0 = pass, no network)."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "scripts"))
import report  # noqa: E402
import storage  # noqa: E402


def put(root, rel, obj):
    storage.write_local(root, rel, json.dumps(obj).encode())


def get(root, rel):
    with open(os.path.join(root, *rel.split("/"))) as f:
        return json.load(f)


with tempfile.TemporaryDirectory() as t:
    laptop_a, laptop_b, drive = (os.path.join(t, n) for n in ("a", "b", "drive"))
    remote = storage.FolderRemote(drive)

    # blob ids match git's, so local files compare directly with GitHub's tree listing
    assert storage.blob_sha(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"

    s1 = "sessions/2026/09/s1.json"
    put(laptop_a, s1, {"session_id": "s1", "ended_at": "2026-09-28T10:00:00Z", "user_msgs": 2})
    put(laptop_a, "chats/2026/09/s1.json", {"session_id": "s1", "messages": [{"role": "user", "ts": "2026-09-28T10:00:00Z", "text": "hi"}]})
    r = storage.sync(laptop_a, remote)
    assert r == {"remote": f"folder {drive}", "pushed": 2, "pulled": 0}, r

    # laptop B starts empty: gets everything
    os.makedirs(laptop_b)
    assert storage.sync(laptop_b, remote)["pulled"] == 2
    assert get(laptop_b, s1)["user_msgs"] == 2

    # B works on a new session, A continues s1: both end up with both, no conflicts
    put(laptop_b, "sessions/2026/09/s2.json", {"session_id": "s2", "ended_at": "2026-09-28T11:00:00Z"})
    put(laptop_a, s1, {"session_id": "s1", "ended_at": "2026-09-28T12:00:00Z", "user_msgs": 5})
    storage.sync(laptop_b, remote)
    storage.sync(laptop_a, remote)
    storage.sync(laptop_b, remote)
    for lap in (laptop_a, laptop_b):
        assert get(lap, s1)["user_msgs"] == 5 and get(lap, "sessions/2026/09/s2.json")["session_id"] == "s2"

    # an older copy never overwrites a newer one
    put(laptop_b, s1, {"session_id": "s1", "ended_at": "2026-09-28T09:00:00Z", "user_msgs": 1})
    storage.sync(laptop_b, remote)
    assert get(laptop_b, s1)["user_msgs"] == 5 and get(drive, s1)["user_msgs"] == 5

    # nothing to do -> nothing written
    assert storage.sync(laptop_a, remote) == {"remote": f"folder {drive}", "pushed": 0, "pulled": 0}
    print("PASS  folder sync: first push, new laptop pull, two laptops, newer wins, idempotent")

    # chat freshness: more messages / later ts wins
    older = json.dumps({"messages": [{"ts": "2026-09-28T10:00"}]}).encode()
    newer = json.dumps({"messages": [{"ts": "2026-09-28T10:00"}, {"ts": "2026-09-28T10:05"}]}).encode()
    assert storage.freshness(newer) > storage.freshness(older)
    print("PASS  freshness ordering")

    # offline report: one file, data embedded, no external URLs
    out = report.build(laptop_a, os.path.join(t, "r.html"), open_it=False)
    html = open(out, encoding="utf-8").read()
    assert '"session_id":"s1"' in html and "/*__DATA__*/" not in html
    assert "http://" not in html.replace("http://www.w3.org", "") and "https://" not in html, "report must work offline"
    print("PASS  offline report: self-contained, data embedded")

print("\nAll storage tests passed.")
