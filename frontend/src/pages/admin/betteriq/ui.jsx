/* BetterIQ — shared UI kit (premium elevation)
   Atoms + signature data-viz primitives, ported from the v2 design handoff to
   real ES modules. Every BetterIQ screen imports its chrome from here so the
   broadcast look stays consistent. */
import { useState, useEffect, useRef, useMemo } from 'react'
import LoadingBarInner from '../../../components/ProgressBar'

/* ── Icons ─────────────────────────────────────────────────────────────────── */
const ICONS = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
  fixtures: <><rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v3M16 3v3"/></>,
  teams: <><circle cx="9" cy="8" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><path d="M16 6.5a3 3 0 0 1 0 6M17.5 19a5.5 5.5 0 0 0-3-4.9"/></>,
  player: <><circle cx="12" cy="8" r="3.4"/><path d="M5.5 20a6.5 6.5 0 0 1 13 0"/></>,
  selection: <><path d="M12 3l2.4 5.3L20 9l-4 4 1 6-5-2.8L7 19l1-6-4-4 5.6-.7z"/></>,
  ladders: <><path d="M5 21V9M12 21V4M19 21v-8"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></>,
  check: <><path d="M5 12.5l4.5 4.5L19 7"/></>,
  close: <><path d="M6 6l12 12M18 6L6 18"/></>,
  share: <><circle cx="6" cy="12" r="2.4"/><circle cx="17" cy="6" r="2.4"/><circle cx="17" cy="18" r="2.4"/><path d="M8.1 11l6.8-3.9M8.1 13l6.8 3.9"/></>,
  bolt: <><path d="M13 3L5 13h6l-1 8 8-10h-6z"/></>,
  back: <><path d="M19 12H5M11 6l-6 6 6 6"/></>,
  arrow: <><path d="M5 12h14M13 6l6 6-6 6"/></>,
  info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></>,
  print: <><path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="7" rx="1"/></>,
  target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/></>,
  flame: <><path d="M12 3c2 3 4 4.5 4 8a4 4 0 0 1-8 0c0-1.2.4-2 1-2.8C8 9 8.5 5.5 12 3z"/></>,
  shield: <><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/></>,
  chevron: <><path d="M9 6l6 6-6 6"/></>,
  trend: <><path d="M3 17l6-6 4 4 8-8M21 7v5M21 7h-5"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  refresh: <><path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v5h-5"/></>,
  edit: <><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></>,
}
export function Icon({ name, size = 18, sw = 1.6, strokeWidth, className = '', style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={strokeWidth || sw} strokeLinecap="round" strokeLinejoin="round" className={className} style={style} aria-hidden="true">
      {ICONS[name] || null}
    </svg>
  )
}

/* ── CountUp — animated tabular number ──────────────────────────────────────── */
function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3) }
export function CountUp({ value, decimals = 0, duration = 1000, prefix = '', suffix = '', className = '', style }) {
  const [disp, setDisp] = useState(0)
  const raf = useRef(null)
  const target = Number(value) || 0
  useEffect(() => {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setDisp(target); return }
    const start = performance.now()
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration)
      setDisp(target * easeOutCubic(p))
      if (p < 1) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    const fallback = setTimeout(() => setDisp(target), duration + 300)
    return () => { cancelAnimationFrame(raf.current); clearTimeout(fallback) }
  }, [target, duration])
  const txt = decimals ? disp.toFixed(decimals) : Math.round(disp).toLocaleString()
  return <span className={`iq-num ${className}`} style={style}>{prefix}{txt}{suffix}</span>
}

/* ── Sparkline — draw-in area+line ──────────────────────────────────────────── */
export function Sparkline({ values, w = 120, h = 44, stroke = 'var(--pb-accent)', fill = true, strokeWidth = 1.6, dots = false }) {
  const vals = (values || []).filter(v => v !== null && v !== undefined && !Number.isNaN(v))
  const id = useMemo(() => 'sg' + Math.random().toString(36).slice(2, 8), [])
  if (vals.length < 2) return <div style={{ height: h }} className="flex items-center text-pb-faintest text-[11px]">—</div>
  const max = Math.max(1, ...vals), min = Math.min(0, ...vals)
  const range = max - min || 1
  const stepX = w / (vals.length - 1)
  const pts = vals.map((v, i) => [i * stepX, h - ((v - min) / range) * (h - 6) - 3])
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const area = `${line} L${w},${h} L0,${h} Z`
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" width="100%" height={h} className="block">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.30"/>
          <stop offset="100%" stopColor={stroke} stopOpacity="0"/>
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#${id})`} />}
      <path d={line} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round"
        style={{ strokeDasharray: 600, strokeDashoffset: 600, animation: 'iq-draw 1.1s ease forwards' }} />
      {dots && pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="1.6" fill={stroke} style={{ opacity: 0, animation: `iq-fade .3s ease forwards ${0.6 + i * 0.05}s` }} />)}
    </svg>
  )
}

/* ── Bar — animated horizontal proportion bar ───────────────────────────────── */
export function Bar({ pct, color = 'var(--pb-accent)', h = 8, track = 'var(--pb-surface2)', delay = 0 }) {
  return (
    <div style={{ height: h, background: track, borderRadius: 99, overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${Math.max(0, Math.min(100, pct))}%`, background: color, borderRadius: 99,
        transformOrigin: 'left', animation: `iq-grow .9s cubic-bezier(.22,.61,.36,1) ${delay}s both` }} />
    </div>
  )
}

/* ── Gauge — win% arc dial ──────────────────────────────────────────────────── */
export function Gauge({ value = 0, size = 132, label, sub, color = 'var(--pb-accent)' }) {
  const r = (size - 14) / 2, c = 2 * Math.PI * r, cx = size / 2
  const pct = Math.max(0, Math.min(100, value))
  const [shown, setShown] = useState(0)
  useEffect(() => { const t = setTimeout(() => setShown(pct), 60); return () => clearTimeout(t) }, [pct])
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={cx} cy={cx} r={r} fill="none" stroke="var(--pb-surface3)" strokeWidth="9" />
        <circle cx={cx} cy={cx} r={r} fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c - (shown / 100) * c}
          style={{ transition: 'stroke-dashoffset 1.1s cubic-bezier(.22,.61,.36,1)' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <div className="iq-headline iq-num" style={{ fontSize: size * 0.3 }}><CountUp value={value} suffix="%" /></div>
        {label && <div className="iq-eyebrow mt-0.5" style={{ fontSize: 9 }}>{label}</div>}
        {sub && <div className="text-pb-faint text-[10px]">{sub}</div>}
      </div>
    </div>
  )
}

/* ── ResultPills — W/L/D recent form ────────────────────────────────────────── */
const RESULT_C = { W: 'var(--pb-brand)', L: 'var(--pb-red)', D: 'var(--pb-amber)', T: 'var(--pb-amber)' }
export function ResultPills({ form, size = 22 }) {
  return (
    <div className="flex gap-1">
      {(form || []).map((r, i) => {
        const col = RESULT_C[r] || 'var(--pb-faint)'
        return (
          <span key={i} className="iq-mono inline-flex items-center justify-center font-bold iq-fade"
            style={{ width: size, height: size, fontSize: size * 0.45, borderRadius: 6, color: col,
              background: `color-mix(in srgb, ${col} 16%, transparent)`,
              border: `1px solid color-mix(in srgb, ${col} 34%, transparent)`,
              animationDelay: `${i * 60}ms` }}>{r}</span>
        )
      })}
    </div>
  )
}

/* ── SplitBar — proportional segmented bar (H2H, win/lose) ───────────────────── */
export function SplitBar({ segments, h = 12 }) {
  return (
    <div className="flex w-full overflow-hidden" style={{ height: h, borderRadius: 99, gap: 2 }}>
      {segments.filter(s => s.value > 0).map((s, i) => (
        <div key={i} title={`${s.label}: ${s.value}`} style={{ flexGrow: s.value, background: s.color, borderRadius: 3,
          transformOrigin: 'left', animation: `iq-grow .9s cubic-bezier(.22,.61,.36,1) ${i * 0.08}s both` }} />
      ))}
    </div>
  )
}

/* ── StackedBar w/ legend (how they get out) ─────────────────────────────────── */
export function StackedBar({ data, palette }) {
  const pal = palette || ['var(--pb-accent)', 'var(--iq-c-amber)', 'var(--pb-brand)', 'var(--pb-red)', 'var(--iq-c-cyan)', 'var(--pb-dim)']
  return (
    <div>
      <SplitBar h={16} segments={data.map((d, i) => ({ label: d.type, value: d.count, color: pal[i % pal.length] }))} />
      <div className="mt-4 space-y-2.5">
        {data.map((d, i) => (
          <div key={d.type} className="flex items-center gap-2.5 text-[13px]">
            <span style={{ width: 9, height: 9, borderRadius: 99, background: pal[i % pal.length] }} className="shrink-0" />
            <span className="capitalize text-pb-dim flex-1">{d.type}</span>
            <span className="iq-num text-pb-faint text-[11.5px]">{d.count}</span>
            <span className="iq-num font-semibold w-9 text-right">{d.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Heatmap — bowler × batter dismissal matrix ──────────────────────────────── */
export function Heatmap({ rows }) {
  const { bowlers, batters, cells, maxC } = useMemo(() => {
    const bt = {}, bat = {}, cl = {}
    for (const r of rows) { bt[r.bowler] = (bt[r.bowler] || 0) + r.dismissals; bat[r.batter] = (bat[r.batter] || 0) + r.dismissals; cl[`${r.bowler}|${r.batter}`] = r }
    return {
      bowlers: Object.keys(bt).sort((a, b) => bt[b] - bt[a]).slice(0, 6),
      batters: Object.keys(bat).sort((a, b) => bat[b] - bat[a]).slice(0, 8),
      cells: cl, maxC: Math.max(1, ...rows.map(r => r.dismissals)),
    }
  }, [rows])
  let k = 0
  return (
    <div className="overflow-x-auto iq-scroll -mx-1 px-1">
      <table className="text-[11px] border-separate" style={{ borderSpacing: 3 }}>
        <thead><tr>
          <th className="sticky left-0" style={{ background: 'var(--pb-surface)' }} />
          {batters.map(b => (
            <th key={b} className="align-bottom h-24 p-0">
              <div className="iq-mono text-pb-dim font-medium whitespace-nowrap mx-auto" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', fontSize: 10.5 }}>{b}</div>
            </th>
          ))}
        </tr></thead>
        <tbody>
          {bowlers.map(bw => (
            <tr key={bw}>
              <td className="pr-2.5 text-right font-semibold whitespace-nowrap sticky left-0" style={{ background: 'var(--pb-surface)', fontSize: 12 }}>{bw}</td>
              {batters.map(bt => {
                const c = cells[`${bw}|${bt}`]; const n = c?.dismissals || 0
                const intensity = n ? 0.16 + 0.74 * (n / maxC) : 0
                const delay = (k++) * 14
                return (
                  <td key={bt} className="p-0 text-center">
                    <div className="w-8 h-8 flex items-center justify-center iq-num font-bold mx-auto iq-fade"
                      title={c ? `${bw} dismissed ${bt} ${n}× (${c.runs_made} runs)` : `${bw} vs ${bt}`}
                      style={{ borderRadius: 7, animationDelay: `${delay}ms`,
                        background: n ? `color-mix(in srgb, var(--pb-accent) ${Math.round(intensity * 100)}%, transparent)` : 'var(--pb-surface2)',
                        color: intensity > 0.5 ? '#fff' : (n ? 'var(--pb-text)' : 'var(--pb-faintest)'),
                        boxShadow: intensity > 0.6 ? `0 0 16px -4px color-mix(in srgb, var(--pb-accent) 70%, transparent)` : 'none' }}>
                      {n || '·'}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── Card / Stat / Note ──────────────────────────────────────────────────────── */
export function Card({ title, eyebrow, right, children, accent = false, className = '', style }) {
  return (
    <div className={`iq-card ${accent ? 'iq-accent-card' : ''} ${className}`} style={style}>
      <div className="relative p-5 md:p-6">
        {(title || right || eyebrow) && (
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="min-w-0 flex-1">
              {eyebrow && <div className="iq-eyebrow mb-1.5">{eyebrow}</div>}
              {title && <h3 className="iq-display font-bold text-[17px] leading-tight" style={{ letterSpacing: '-0.01em' }}>{title}</h3>}
            </div>
            {right && <div className="shrink-0">{right}</div>}
          </div>
        )}
        {children}
      </div>
    </div>
  )
}
export function Stat({ label, value, sub, tone, big = false, decimals = 0, suffix = '', count = true }) {
  const color = tone === 'win' ? 'var(--pb-brand)' : tone === 'loss' ? 'var(--pb-red)' : tone === 'draw' ? 'var(--pb-amber)' : tone === 'accent' ? 'var(--pb-accent)' : 'var(--pb-text)'
  const numeric = typeof value === 'number'
  return (
    <div>
      <div className="iq-headline iq-num" style={{ fontSize: big ? 'clamp(34px,4vw,52px)' : 26, color }}>
        {numeric && count ? <CountUp value={value} decimals={decimals} suffix={suffix} /> : value}
      </div>
      <div className="iq-eyebrow mt-1.5">{label}</div>
      {sub && <div className="text-pb-faint text-[11px] mt-0.5">{sub}</div>}
    </div>
  )
}
export function Note({ children }) {
  // Notes carry every caveat and sample-size disclosure in BetterIQ — they must
  // be readable, not the faintest type on the page under a 24px bold claim.
  return (
    <div className="flex items-start gap-1.5 text-pb-faint text-[11.5px] mt-3 leading-relaxed">
      <Icon name="info" size={12} className="mt-0.5 shrink-0" /><span>{children}</span>
    </div>
  )
}

/* ── Tag / Btn / Segmented / Search / Empty ─────────────────────────────────── */
const TAG_TONE = {
  accent: { bg: 'color-mix(in srgb, var(--pb-accent) 16%, transparent)', c: 'var(--pb-accent)' },
  win:    { bg: 'color-mix(in srgb, var(--pb-brand) 16%, transparent)', c: 'var(--pb-brand)' },
  amber:  { bg: 'color-mix(in srgb, var(--pb-amber) 16%, transparent)', c: 'var(--pb-amber)' },
  red:    { bg: 'color-mix(in srgb, var(--pb-red) 16%, transparent)', c: 'var(--pb-red)' },
  faint:  { bg: 'var(--pb-surface2)', c: 'var(--pb-faint)' },
}
export function Tag({ children, tone = 'accent', className = '' }) {
  const t = TAG_TONE[tone] || TAG_TONE.accent
  return <span className={`iq-mono inline-flex items-center font-bold uppercase whitespace-nowrap ${className}`}
    style={{ fontSize: 9.5, letterSpacing: '0.1em', padding: '3px 7px', borderRadius: 6, background: t.bg, color: t.c }}>{children}</span>
}
const BTN = {
  primary: { background: 'var(--pb-accent)', color: '#0a0814', border: '1px solid transparent' },
  soft:    { background: 'var(--pb-surface2)', color: 'var(--pb-text)', border: '1px solid var(--pb-hairline2)' },
  ghost:   { background: 'transparent', color: 'var(--pb-dim)', border: '1px solid var(--pb-hairline2)' },
}
export function Btn({ children, variant = 'ghost', sm = false, icon, onClick, disabled, className = '', title, type = 'button' }) {
  return (
    <button type={type} onClick={disabled ? undefined : onClick} disabled={disabled} title={title}
      className={`iq-display inline-flex items-center justify-center font-semibold whitespace-nowrap transition disabled:opacity-40 hover:brightness-110 ${className}`}
      style={{ ...BTN[variant], gap: sm ? 6 : 8, fontSize: sm ? 12.5 : 13.5, padding: sm ? '7px 11px' : '9px 15px', borderRadius: 10 }}>
      {icon && <Icon name={icon} size={sm ? 14 : 16} />}{children}
    </button>
  )
}
export function Segmented({ options, value, onChange, sm = false }) {
  return (
    <div className="inline-flex p-[3px] gap-0.5" style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 10 }}>
      {options.map(o => {
        const active = o.value === value
        return (
          <button key={o.value} type="button" onClick={() => onChange(o.value)}
            className="iq-display font-semibold transition"
            style={{ fontSize: sm ? 12 : 13, padding: sm ? '4px 10px' : '6px 13px', borderRadius: 7,
              color: active ? 'var(--pb-accent)' : 'var(--pb-faint)',
              background: active ? 'color-mix(in srgb, var(--pb-accent) 15%, transparent)' : 'transparent' }}>
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
export function Search({ value, onChange, placeholder = 'Search…', className = '', autoFocus, onKeyDown }) {
  return (
    <div className={`flex items-center gap-2.5 px-3.5 ${className}`}
      style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 10, height: 42, color: 'var(--pb-faint)' }}>
      <Icon name="search" size={16} />
      <input value={value} onChange={e => onChange(e.target.value)} onKeyDown={onKeyDown} placeholder={placeholder} autoFocus={autoFocus}
        className="bg-transparent border-0 outline-none w-full" style={{ color: 'var(--pb-text)', fontSize: 14 }} />
    </div>
  )
}
export function Empty({ children, className = '' }) {
  return <div className={`text-pb-faint text-sm ${className}`}>{children}</div>
}

/* ── Loading — percentage bars for every fetch ──────────────────────────────
   LoadingBar = bare bar + % (drop inside a Card or column while loading).
   LoadingCard = the iq-card placeholder that used to be the "Loading…" pulse.
   expectedMs tunes the climb to the call's typical duration. */
export { default as LoadingBar, ProgressBar, useLoadingProgress } from '../../../components/ProgressBar'
export function LoadingCard({ label = 'Loading…', expectedMs = 6000, className = '' }) {
  return (
    <div className={`iq-card p-6 ${className}`}>
      <LoadingBarInner label={label} expectedMs={expectedMs} />
    </div>
  )
}

/* surname helper */
export function surname(name) { const s = (name || '').split(',')[0].trim(); return s || name || '?' }

/* ── Tabs — primary in-page section nav (underline) ──────────────────────── */
export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="flex items-center gap-0.5 overflow-x-auto iq-scroll" style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
      {tabs.map(t => {
        const active = t.value === value
        return (
          <button key={t.value} onClick={() => onChange(t.value)}
            className="iq-display font-semibold relative whitespace-nowrap transition-colors"
            style={{ padding: '11px 15px', fontSize: 14, color: active ? 'var(--pb-text)' : 'var(--pb-dim)' }}
            onMouseEnter={e => { if (!active) e.currentTarget.style.color = 'var(--pb-text)' }}
            onMouseLeave={e => { if (!active) e.currentTarget.style.color = 'var(--pb-dim)' }}>
            {t.label}
            {active && <span className="absolute left-3 right-3" style={{ bottom: -1, height: 2, background: 'var(--pb-accent)', borderRadius: 2 }} />}
          </button>
        )
      })}
    </div>
  )
}

/* ── Page intro — one quiet sentence under the header ────────────────────── */
export function PageIntro({ children }) {
  return <p className="text-pb-dim leading-relaxed mb-7" style={{ maxWidth: 580, fontSize: 14.5 }}>{children}</p>
}

/* ── Delta — coloured up/down indicator ──────────────────────────────────── */
export function Delta({ value, suffix = '', decimals = 0, neutralBand = 0 }) {
  const v = Number(value) || 0
  const flat = Math.abs(v) <= neutralBand
  const up = v >= 0
  const color = flat ? 'var(--pb-faint)' : up ? 'var(--pb-brand)' : 'var(--pb-red)'
  return <span className="iq-num font-semibold inline-flex items-center gap-1" style={{ color, fontSize: 12.5 }}>{flat ? '—' : up ? '▲' : '▼'} {Math.abs(v).toFixed(decimals)}{suffix}</span>
}

/* ── Initials chip ───────────────────────────────────────────────────────── */
export function Initials({ name, size = 36, tone }) {
  const init = (name || '?').replace(/^[A-Z]\.\s*/, '').slice(0, 2).toUpperCase()
  return (
    <div className="flex items-center justify-center shrink-0 iq-display font-bold"
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.28), fontSize: size * 0.34,
        background: tone === 'accent' ? 'color-mix(in srgb, var(--pb-accent) 14%, transparent)' : 'var(--pb-surface2)',
        border: '1px solid var(--pb-hairline2)', color: tone === 'accent' ? 'var(--pb-accent)' : 'var(--pb-dim)' }}>
      {init}
    </div>
  )
}

/* ── KV — label/value row ────────────────────────────────────────────────── */
export function KV({ label, value, tone }) {
  const color = tone === 'win' ? 'var(--pb-brand)' : tone === 'loss' ? 'var(--pb-red)' : tone === 'amber' ? 'var(--pb-amber)' : 'var(--pb-text)'
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-pb-dim text-[13px]">{label}</span>
      <span className="iq-num font-semibold text-[13.5px] whitespace-nowrap" style={{ color }}>{value}</span>
    </div>
  )
}

/* ── Number formatting — re-exported from the app-wide single source of truth.
   a2 stays the BetterIQ alias for "average to 2dp"; the rest let IQ screens
   spell out runs/wickets, format overs (base-6) and counts (commas) the same
   way every other surface does. See src/lib/cricketFormat.js. ───────────────── */
export {
  fmt2 as a2,
  fmt2, fmtAverage, fmtEconomy, fmtStrikeRate, fmtRunRate,
  fmtCount, fmtRuns, fmtWickets, fmtNum,
  fmtOvers, oversToBalls, ballsToOvers, sumOvers,
  fmtPct, runsPhrase, wktsPhrase, DASH,
} from '../../../lib/cricketFormat'
