"use client";
import { Fragment, useState, type ReactNode } from "react";

// Tiny, safe markdown: fenced code, headings, lists, quotes, tables-as-text,
// **bold**, *italic*, `code`, [links](url). Builds React nodes; never injects HTML.

function inline(text: string, key = 0): ReactNode[] {
  const out: ReactNode[] = [];
  const rx = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\[[^\]]+\]\((https?:\/\/[^)\s]+)\))/g;
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = rx.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const k = `${key}-${i++}`;
    if (tok.startsWith("`")) out.push(<code key={k}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("**")) out.push(<strong key={k}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("[")) out.push(<a key={k} href={m[2]} target="_blank" rel="noreferrer">{tok.slice(1, tok.indexOf("]"))}</a>);
    else out.push(<em key={k}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="code">
      <div className="code-bar">
        <span>{lang || "text"}</span>
        <button onClick={() => { navigator.clipboard?.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1200); }}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const parts = text.split(/```/);
  parts.forEach((part, pi) => {
    if (pi % 2 === 1) {
      const nl = part.indexOf("\n");
      blocks.push(<CodeBlock key={"c" + pi} lang={nl > -1 ? part.slice(0, nl).trim() : ""} code={nl > -1 ? part.slice(nl + 1).replace(/\n$/, "") : part} />);
      return;
    }
    const lines = part.split("\n");
    let list: { ordered: boolean; items: string[] } | null = null;
    const flush = (k: string) => {
      if (!list) return;
      const Tag = list.ordered ? "ol" : "ul";
      blocks.push(<Tag key={k}>{list.items.map((it, i) => <li key={i}>{inline(it, i)}</li>)}</Tag>);
      list = null;
    };
    lines.forEach((ln, li) => {
      const k = `${pi}-${li}`;
      const bullet = ln.match(/^\s*[-*]\s+(.*)/), num = ln.match(/^\s*\d+[.)]\s+(.*)/);
      if (bullet || num) {
        const ordered = !!num;
        if (!list || list.ordered !== ordered) { flush(k + "f"); list = { ordered, items: [] }; }
        list.items.push((bullet || num)![1]);
        return;
      }
      flush(k + "f");
      if (!ln.trim()) return;
      const h = ln.match(/^(#{1,4})\s+(.*)/);
      if (h) blocks.push(<p key={k} className={`md-h md-h${h[1].length}`}>{inline(h[2])}</p>);
      else if (ln.startsWith(">")) blocks.push(<blockquote key={k}>{inline(ln.replace(/^>\s?/, ""))}</blockquote>);
      else if (/^\s*\|.*\|\s*$/.test(ln)) { if (!/^\s*\|[\s:-|]+\|\s*$/.test(ln)) blocks.push(<p key={k} className="md-row">{inline(ln.replace(/^\s*\||\|\s*$/g, "").split("|").map((c) => c.trim()).join("  ·  "))}</p>); }
      else blocks.push(<p key={k}>{inline(ln)}</p>);
    });
    flush(`${pi}-end`);
  });
  return <Fragment>{blocks}</Fragment>;
}
