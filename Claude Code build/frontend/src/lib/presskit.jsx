// src/lib/presskit.jsx
// Press Box shared primitives: design vocabulary used across every page.
// All components Tailwind-first; the only inline styles are dynamic (animation
// timing, sparkline geometry, white-label accent that comes from CSS vars).

import React, { useEffect, useRef, useState } from "react";

// ── White-label accent hook ────────────────────────────────────────────
// Reads --pb-accent from CSS. Your existing useClubTheme writes it.
// If you don't have useClubTheme yet, just hard-set --pb-accent in theme.css
// or override it on <body style={{ '--pb-accent': club.accent }}>.
export function useAccent() {
  if (typeof window === "undefined") return "#16c784";
  return getComputedStyle(document.documentElement).getPropertyValue("--pb-accent").trim() || "#16c784";
}

// ── Animated number ────────────────────────────────────────────────────
export function useAnimatedNumber(target, { duration = 1100, decimals = 0, enabled = true } = {}) {
  const [value, setValue] = useState(enabled ? 0 : target);
  useEffect(() => {
    if (!enabled) { setValue(target); return; }
    const t0 = performance.now();
    let raf;
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(target * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
      else setValue(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, enabled]);
  return decimals > 0 ? value.toFixed(decimals) : Math.round(value).toLocaleString();
}

export function AnimatedNum({ value, decimals = 0, suffix = "", prefix = "", duration = 1100, enabled = true, className }) {
  // Skip animation for non-numeric values (e.g. "5/22").
  if (typeof value !== "number") return <span className={className}>{prefix}{value}{suffix}</span>;
  const v = useAnimatedNumber(value, { decimals, duration, enabled });
  return <span className={className}>{prefix}{v}{suffix}</span>;
}

// ── Sparkline ──────────────────────────────────────────────────────────
export function Sparkline({ data, w = 80, h = 22, stroke = "currentColor", fill = "none", strokeWidth = 1.4, smooth = true, dot = false, className }) {
  if (!data || !data.length) return null;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = Math.max(max - min, 1);
  const step = w / Math.max(data.length - 1, 1);
  const pts = data.map((d, i) => [i * step, h - ((d - min) / range) * h]);
  const d = smooth
    ? pts.reduce((acc, [x, y], i) => {
        if (i === 0) return `M${x},${y}`;
        const [px, py] = pts[i - 1];
        const cx = (px + x) / 2;
        return `${acc} C${cx},${py} ${cx},${y} ${x},${y}`;
      }, "")
    : pts.map(([x, y], i) => (i === 0 ? `M${x},${y}` : `L${x},${y}`)).join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg width={w} height={h} className={className} style={{ display: "block", overflow: "visible" }}>
      {fill !== "none" && <path d={`${d} L${w},${h} L0,${h} Z`} fill={fill} opacity={0.18} />}
      <path d={d} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
      {dot && <circle cx={last[0]} cy={last[1]} r={2.2} fill={stroke} />}
    </svg>
  );
}

// ── Mini bar chart ─────────────────────────────────────────────────────
export function MiniBars({ data, w = 220, h = 56, color = "currentColor", gap = 2, accentLast = false, accentColor = "var(--pb-accent)" }) {
  if (!data || !data.length) return null;
  const values = data.map(d => (typeof d === "number" ? d : d.v));
  const max = Math.max(...values, 1);
  const bw = (w - gap * (data.length - 1)) / data.length;
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      {values.map((v, i) => {
        const bh = (v / max) * h;
        const isLast = i === values.length - 1;
        return (
          <rect key={i}
            x={i * (bw + gap)} y={h - bh}
            width={bw} height={bh}
            rx={1.5}
            fill={accentLast && isLast ? accentColor : color}
            opacity={accentLast && !isLast ? 0.55 : 1}
          />
        );
      })}
    </svg>
  );
}

// ── Ticker ─────────────────────────────────────────────────────────────
export function Ticker({ items, speed = 38, sep = "  ◆  ", motion = true, className = "" }) {
  const content = items.join(sep) + sep;
  const dur = `${speed}s`;
  return (
    <div className={`overflow-hidden whitespace-nowrap ${className}`}>
      <div className="inline-block whitespace-nowrap" style={{
        animation: motion ? `pb-ticker ${dur} linear infinite` : "none",
      }}>
        <span>{content}</span><span>{content}</span>
      </div>
    </div>
  );
}

// ── Label (all-caps tiny eyebrow used everywhere) ──────────────────────
export function Label({ children, className = "", style }) {
  return (
    <span
      className={`text-2xs font-semibold uppercase tracking-wide3 text-pb-faint ${className}`}
      style={style}
    >
      {children}
    </span>
  );
}

// ── Card ──────────────────────────────────────────────────────────────
export function Card({ children, className = "", title, action, pad = "p-4 sm:p-[18px]" }) {
  return (
    <div className={`pb-card ${pad} ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between mb-3 sm:mb-3.5">
          {title && <Label>{title}</Label>}
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

// ── Buttons ───────────────────────────────────────────────────────────
export function Btn({ children, primary = false, onClick, className = "", icon }) {
  if (primary) {
    return (
      <button
        onClick={onClick}
        className={`text-xs font-semibold px-3.5 py-2 rounded text-[#08110b] hover:opacity-90 transition ${className}`}
        style={{ background: "var(--pb-accent)" }}
      >
        {icon}{children}
      </button>
    );
  }
  return (
    <button
      onClick={onClick}
      className={`text-xs font-medium px-3.5 py-2 rounded border border-pb-hairline2 text-pb-text bg-transparent hover:bg-pb-surface2 transition ${className}`}
    >
      {icon}{children}
    </button>
  );
}

// ── Result pill (WIN / LOSS / DRAW / TIE) ─────────────────────────────
export function ResultPill({ result }) {
  const map = {
    WIN:  { color: "var(--pb-accent)",  bg: "rgba(22,199,132,0.10)" },
    LOSS: { color: "var(--pb-red)",     bg: "rgba(239,91,91,0.10)" },
    DRAW: { color: "var(--pb-faint)",   bg: "rgba(138,144,162,0.10)" },
    TIE:  { color: "var(--pb-amber)",   bg: "rgba(245,181,66,0.10)" },
  };
  const s = map[result] || map.DRAW;
  return (
    <span
      className="font-mono text-2xs font-bold tracking-wide2 px-2 py-0.5 rounded-sm inline-flex items-center"
      style={{ color: s.color, background: s.bg, border: `1px solid ${s.color}33` }}
    >
      {result}
    </span>
  );
}

// ── KPI tile ──────────────────────────────────────────────────────────
export function Kpi({ label, value, sub, accent = false, suffix = "", decimals = 0, spark, sparkColor, motion = true }) {
  return (
    <div className="pb-card pb-rise p-4 flex flex-col gap-1 relative overflow-hidden">
      <Label>{label}</Label>
      <div className="flex items-baseline gap-2 mt-1">
        <span
          className="font-mono text-3xl font-semibold tracking-tight leading-none pb-num"
          style={{ color: accent ? "var(--pb-accent)" : "var(--pb-text)" }}
        >
          <AnimatedNum value={value} decimals={decimals} suffix={suffix} enabled={motion} />
        </span>
        {spark && (
          <span className="ml-auto" style={{ color: sparkColor || "var(--pb-accent)" }}>
            <Sparkline data={spark} w={80} h={20} stroke="currentColor" strokeWidth={1.3} dot />
          </span>
        )}
      </div>
      {sub && <span className="text-[11px] text-pb-dim font-mono mt-1">{sub}</span>}
    </div>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────────
export function Skeleton({ className = "", w, h }) {
  return (
    <div
      className={`pb-card animate-pulse ${className}`}
      style={{ width: w, height: h, background: "var(--pb-surface)" }}
    />
  );
}

// ── Section heading (h1 + eyebrow) ─────────────────────────────────────
export function PageHeader({ eyebrow, title, meta, actions }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between mb-5">
      <div>
        {eyebrow && <Label>{eyebrow}</Label>}
        <h1 className="font-display text-[40px] sm:text-[56px] font-bold tracking-tight leading-[0.95] mt-1.5 text-pb-text">
          {title}
        </h1>
        {meta && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-pb-dim font-mono text-[13px] mt-1.5">
            {meta}
          </div>
        )}
      </div>
      {actions && <div className="flex gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}
