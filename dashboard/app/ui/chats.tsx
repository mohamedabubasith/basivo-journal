"use client";
import { useMemo, useRef, useState } from "react";
import { Markdown } from "./md";
import { type Row, dayKey, monthKey, projectName, t } from "@/lib/stats";

type Msg = { role: "user" | "assistant"; ts: string; text: string };
type Chat = { session_id: string; title: string; project: string; started_at: string; messages: Msg[] };

const fmtTime = (iso: string) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "");

export default function Chats({ rows, initialProject }: { rows: Row[]; initialProject: string }) {
  const [q, setQ] = useState("");
  const [project, setProject] = useState(initialProject);
  const [openId, setOpenId] = useState<string | null>(null);
  const [chat, setChat] = useState<Chat | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [find, setFind] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  const projects = useMemo(() => [...new Set(rows.map((r) => projectName(r.project)))].sort(), [rows]);
  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return [...rows]
      .filter((r) => project === "all" || projectName(r.project) === project)
      .filter((r) => !needle || [r.title, r.first_prompt, r.project].some((s) => (s || "").toLowerCase().includes(needle)))
      .sort((a, b) => t(b) - t(a));
  }, [rows, q, project]);

  const open = async (r: Row) => {
    setOpenId(r.session_id);
    setChat(null);
    setErr("");
    setFind("");
    setLoading(true);
    try {
      const res = await fetch(`/api/chat?month=${encodeURIComponent(monthKey(r))}&id=${encodeURIComponent(r.session_id)}`);
      if (!res.ok) throw new Error(res.status === 404 ? "No chat saved for this session (recorded before chat history was on, or turned off)." : `Error ${res.status}`);
      setChat(await res.json());
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const current = rows.find((r) => r.session_id === openId);
  const needle = find.trim().toLowerCase();
  const shown = chat?.messages.filter((m) => !needle || m.text.toLowerCase().includes(needle)) || [];

  return (
    <div className={`chats${openId ? " has-open" : ""}`}>
      <aside className="chat-list card" ref={listRef}>
        <div className="chat-tools">
          <input type="search" placeholder="Search titles and prompts…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search sessions" />
          <select value={project} onChange={(e) => setProject(e.target.value)} aria-label="Project">
            <option value="all">All projects</option>
            {projects.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <p className="muted small">{list.length} session{list.length === 1 ? "" : "s"}</p>
        <ul>
          {list.map((r) => (
            <li key={r.session_id}>
              <button className={`chat-item${r.session_id === openId ? " active" : ""}`} onClick={() => open(r)}>
                <span className="chat-item-title">{r.title || r.first_prompt || "Untitled session"}</span>
                <span className="chat-item-meta">
                  <span className="chip">{projectName(r.project)}</span>
                  {dayKey(r.started_at)} · {Math.round(r.minutes)} min · {r.user_msgs} msgs
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="chat-view card">
        {!openId && (
          <div className="empty">
            <div className="empty-icon" aria-hidden>💬</div>
            <p><b>Pick a session</b> to read the conversation.</p>
            <p className="muted small">Secrets were masked before saving. Tool calls and file contents aren&apos;t stored.</p>
          </div>
        )}
        {openId && (
          <>
            <header className="chat-head">
              <button className="back" onClick={() => setOpenId(null)} aria-label="Back to list">←</button>
              <div className="chat-head-text">
                <h2>{current?.title || current?.first_prompt || "Session"}</h2>
                <p className="muted small">
                  {current ? `${projectName(current.project)} · ${new Date(current.started_at).toLocaleString()} · ${Math.round(current.minutes)} active min · ${current.model}` : ""}
                </p>
              </div>
              <input type="search" className="find" placeholder="Find in chat" value={find} onChange={(e) => setFind(e.target.value)} aria-label="Find in chat" />
            </header>
            {current && (
              <div className="chat-facts">
                {Object.keys(current.languages || {}).slice(0, 4).map((k) => <span key={k} className="chip">{k}</span>)}
                {Object.keys(current.mcps || {}).slice(0, 4).map((k) => <span key={k} className="chip chip-alt">{k}</span>)}
                {Object.keys(current.skills || {}).slice(0, 3).map((k) => <span key={k} className="chip chip-alt2">{k}</span>)}
              </div>
            )}
            <div className="messages">
              {loading && <div className="skeleton-list">{[0, 1, 2].map((i) => <div key={i} className="skeleton" />)}</div>}
              {err && <p className="muted">{err}</p>}
              {chat && !shown.length && <p className="muted">No messages match “{find}”.</p>}
              {shown.map((m, i) => (
                <div key={i} className={`msg msg-${m.role}`}>
                  <div className="msg-meta">{m.role === "user" ? "You" : "Claude"} · {fmtTime(m.ts)}</div>
                  <div className="bubble"><Markdown text={m.text} /></div>
                </div>
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
