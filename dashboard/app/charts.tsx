"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";

export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.floor(e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

type Tip = { x: number; y: number; body: ReactNode } | null;

function Tooltip({ tip }: { tip: Tip }) {
  if (!tip) return null;
  return (
    <div className="tip" style={{ left: tip.x, top: tip.y }} role="status">
      {tip.body}
    </div>
  );
}

const niceMax = (v: number) => {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
};

const H = 220, PAD = { l: 36, r: 8, t: 10, b: 26 };

/** Single-series bars (hours per day / week). */
export function Bars({ data, unit = "h", label }: { data: { key: string; label: string; value: number }[]; unit?: string; label: string }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip>(null);
  const max = niceMax(Math.max(0, ...data.map((d) => d.value)));
  const iw = Math.max(0, w - PAD.l - PAD.r), ih = H - PAD.t - PAD.b;
  const step = data.length ? iw / data.length : 0;
  const bw = Math.max(1, Math.min(28, step - 2));
  const every = Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(iw / 56))));
  return (
    <div ref={ref} className="chart" aria-label={label}>
      {w > 0 && (
        <svg width={w} height={H} role="img" aria-label={label}>
          {[0, 0.5, 1].map((f) => (
            <g key={f}>
              <line x1={PAD.l} x2={w - PAD.r} y1={PAD.t + ih * (1 - f)} y2={PAD.t + ih * (1 - f)} className="grid" />
              <text x={PAD.l - 6} y={PAD.t + ih * (1 - f) + 4} className="axis" textAnchor="end">{Math.round(max * f * 10) / 10}</text>
            </g>
          ))}
          {data.map((d, i) => {
            const h = (d.value / max) * ih;
            const x = PAD.l + i * step + (step - bw) / 2;
            return (
              <g key={d.key}
                onMouseEnter={() => setTip({ x: x + bw / 2, y: PAD.t + ih - h, body: <><b>{d.label}</b><br />{d.value.toFixed(1)} {unit}</> })}
                onMouseLeave={() => setTip(null)}>
                <rect x={PAD.l + i * step} y={PAD.t} width={step} height={ih} fill="transparent" />
                {h > 0 && <path d={roundedTop(x, PAD.t + ih - h, bw, h)} className="bar s1" />}
                {i % every === 0 && <text x={x + bw / 2} y={H - 8} className="axis" textAnchor="middle">{d.label.slice(5)}</text>}
              </g>
            );
          })}
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}

function roundedTop(x: number, y: number, w: number, h: number, r = 4) {
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

/** Stacked bars: hours per week by project (fixed series order, legend always shown). */
export function Stacked({ weeks, series, label }: { weeks: { key: string; label: string; parts: Record<string, number> }[]; series: string[]; label: string }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip>(null);
  const totals = weeks.map((wk) => series.reduce((s, k) => s + (wk.parts[k] || 0), 0));
  const max = niceMax(Math.max(0, ...totals));
  const iw = Math.max(0, w - PAD.l - PAD.r), ih = H - PAD.t - PAD.b;
  const step = weeks.length ? iw / weeks.length : 0;
  const bw = Math.max(2, Math.min(34, step - 4));
  const every = Math.max(1, Math.ceil(weeks.length / Math.max(1, Math.floor(iw / 60))));
  return (
    <div>
      <ul className="legend">
        {series.map((s, i) => <li key={s}><span className={`swatch s${i + 1}`} />{s}</li>)}
      </ul>
      <div ref={ref} className="chart">
        {w > 0 && (
          <svg width={w} height={H} role="img" aria-label={label}>
            {[0, 0.5, 1].map((f) => (
              <g key={f}>
                <line x1={PAD.l} x2={w - PAD.r} y1={PAD.t + ih * (1 - f)} y2={PAD.t + ih * (1 - f)} className="grid" />
                <text x={PAD.l - 6} y={PAD.t + ih * (1 - f) + 4} className="axis" textAnchor="end">{Math.round(max * f)}</text>
              </g>
            ))}
            {weeks.map((wk, i) => {
              const x = PAD.l + i * step + (step - bw) / 2;
              let y = PAD.t + ih;
              const segs = series.map((s, si) => {
                const v = wk.parts[s] || 0;
                const h = (v / max) * ih;
                y -= h;
                return h > 0 ? <rect key={s} x={x} y={y + 1} width={bw} height={Math.max(0, h - 2)} rx={2} className={`bar s${si + 1}`} /> : null;
              });
              return (
                <g key={wk.key}
                  onMouseEnter={() => setTip({ x: x + bw / 2, y: PAD.t + ih - (totals[i] / max) * ih, body: (
                    <><b>Week of {wk.label}</b> · {totals[i].toFixed(1)} h
                      {series.filter((s) => wk.parts[s]).map((s) => <div key={s}><span className={`swatch s${series.indexOf(s) + 1}`} />{s}: {wk.parts[s].toFixed(1)} h</div>)}</>) })}
                  onMouseLeave={() => setTip(null)}>
                  <rect x={PAD.l + i * step} y={PAD.t} width={step} height={ih} fill="transparent" />
                  {segs}
                  {i % every === 0 && <text x={x + bw / 2} y={H - 8} className="axis" textAnchor="middle">{wk.label.slice(5)}</text>}
                </g>
              );
            })}
          </svg>
        )}
        <Tooltip tip={tip} />
      </div>
    </div>
  );
}

/** Year heatmap: one cell per day, sequential blue by minutes. */
export function Heatmap({ days, now, label }: { days: Record<string, number>; now: number; label: string }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip>(null);
  const today = new Date(now);
  const start = new Date(today.getTime() - 52 * 7 * 864e5 - today.getDay() * 864e5);
  const cells: { key: string; col: number; row: number; v: number }[] = [];
  for (let d = new Date(start), i = 0; d <= today; d = new Date(d.getTime() + 864e5), i++)
    cells.push({ key: d.toISOString().slice(0, 10), col: Math.floor(i / 7), row: i % 7, v: days[d.toISOString().slice(0, 10)] || 0 });
  const cols = Math.max(...cells.map((c) => c.col)) + 1;
  const size = w ? Math.max(6, Math.min(14, Math.floor((w - 28) / cols) - 2)) : 10;
  const max = Math.max(1, ...cells.map((c) => c.v));
  const level = (v: number) => (v <= 0 ? 0 : v < max * 0.25 ? 1 : v < max * 0.5 ? 2 : v < max * 0.75 ? 3 : 4);
  return (
    <div ref={ref} className="chart heat">
      {w > 0 && (
        <svg width={28 + cols * (size + 2)} height={7 * (size + 2) + 4} role="img" aria-label={label}>
          {["Mon", "Wed", "Fri"].map((dname, i) => <text key={dname} x={0} y={(i * 2 + 1) * (size + 2) + size - 2} className="axis">{dname}</text>)}
          {cells.map((c) => (
            <rect key={c.key} x={28 + c.col * (size + 2)} y={c.row * (size + 2)} width={size} height={size} rx={2}
              className={`heat-${level(c.v)}`}
              onMouseEnter={() => setTip({ x: 28 + c.col * (size + 2) + size / 2, y: c.row * (size + 2), body: <><b>{c.key}</b><br />{c.v ? (c.v / 60).toFixed(1) + " h" : "no sessions"}</> })}
              onMouseLeave={() => setTip(null)} />
          ))}
        </svg>
      )}
      <div className="heat-scale"><span>less</span>{[0, 1, 2, 3, 4].map((l) => <i key={l} className={`heat-${l}`} />)}<span>more</span></div>
      <Tooltip tip={tip} />
    </div>
  );
}

/** Ranked horizontal bars with direct value labels. */
export function RankList({ items, unit }: { items: { name: string; value: number }[]; unit: string }) {
  if (!items.length) return <p className="muted">Nothing yet in this period.</p>;
  const max = Math.max(...items.map((i) => i.value)) || 1;
  return (
    <ol className="rank">
      {items.map((it) => (
        <li key={it.name} title={`${it.name}: ${it.value} ${unit}`}>
          <span className="rank-name">{it.name}</span>
          <span className="rank-track"><span className="rank-bar" style={{ width: `${Math.max(2, (it.value / max) * 100)}%` }} /></span>
          <span className="rank-val">{Number.isInteger(it.value) ? it.value : it.value.toFixed(1)} {unit}</span>
        </li>
      ))}
    </ol>
  );
}

/** Small labelled profile bars: hour-of-day or weekday distribution. */
export function Profile({ values, labels, unit = "h", label, highlight }: { values: number[]; labels: string[]; unit?: string; label: string; highlight?: number }) {
  const [tip, setTip] = useState<Tip>(null);
  const max = Math.max(1e-9, ...values);
  const peak = values.indexOf(Math.max(...values));
  return (
    <div className="profile" role="img" aria-label={label}>
      <div className="profile-bars">
        {values.map((v, i) => (
          <div key={i} className="profile-col"
            onMouseEnter={(e) => { const el = e.currentTarget; setTip({ x: el.offsetLeft + el.offsetWidth / 2, y: el.offsetTop, body: <><b>{labels[i]}</b><br />{v.toFixed(1)} {unit}</> }); }}
            onMouseLeave={() => setTip(null)}>
            <span className={`profile-bar${i === (highlight ?? peak) ? " is-peak" : ""}`} style={{ height: `${Math.max(v > 0 ? 3 : 0, (v / max) * 100)}%` }} />
          </div>
        ))}
      </div>
      <div className="profile-labels">
        {labels.map((l, i) => <span key={i}>{labels.length > 12 ? (i % 3 === 0 ? l : "") : l}</span>)}
      </div>
      <Tooltip tip={tip} />
    </div>
  );
}

/** Inline trend line for cards. */
export function Sparkline({ values, width = 120, height = 32 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const max = Math.max(1e-9, ...values);
  const pts = values.map((v, i) => [(i / (values.length - 1)) * width, height - 2 - (v / max) * (height - 4)]);
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join("");
  return (
    <svg width={width} height={height} className="spark" aria-hidden>
      <path d={`${d}L${width},${height}L0,${height}Z`} className="spark-fill" />
      <path d={d} className="spark-line" />
    </svg>
  );
}
