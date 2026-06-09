/* BetterIQ — signature visualisations.
   Radar (player profile), WagonWheel (scoring zones), AreaChart (trajectory),
   PhaseStrip (innings phases), DonutStat. All draw-in animated, theme-aware.
   Ported from the v2 design handoff to real ES modules. */
import { useState, useEffect, useMemo } from 'react'
import { CountUp, fmtOvers, fmtCount } from './ui'

function useMounted(delay = 60) {
  const [on, setOn] = useState(false)
  useEffect(() => { const t = setTimeout(() => setOn(true), delay); return () => clearTimeout(t) }, [])
  return on
}

/* Default radar axes (kept here so callers can pass normalised 0–100 values
   without re-stating the axis labels). */
export const BAT_AXES = [
  { key: 'volume', label: 'Volume' },
  { key: 'average', label: 'Average' },
  { key: 'strike', label: 'Strike rate' },
  { key: 'consistency', label: 'Consistency' },
  { key: 'conversion', label: 'Conversion' },
  { key: 'impact', label: 'Match impact' },
]
export const BOWL_AXES = [
  { key: 'wickets', label: 'Wickets' },
  { key: 'average', label: 'Average' },
  { key: 'economy', label: 'Economy' },
  { key: 'strike', label: 'Strike rate' },
  { key: 'hauls', label: 'Big hauls' },
  { key: 'top_order', label: 'Top-order' },
]

/* buildRadar — normalise a player's metrics vs a peer group so the peer mean
   sits on the 50 ring (values 0–100; lower-is-better axes inverted). Used for
   OPPONENT radars, whose stats live only in the live dossier (not our DB) — our
   own players get the same shape from the backend /radar endpoint.
   items: peer-group array · axisDefs: [{label, value:(it)=>number, lower?}] */
export function buildRadar(items, axisDefs, target) {
  const axes = axisDefs.map(a => ({ key: a.label, label: a.label }))
  const values = axisDefs.map(a => {
    const xs = (items || []).map(a.value).filter(v => typeof v === 'number' && isFinite(v) && v > 0)
    const mean = xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : 0
    const v = a.value(target)
    let score = 50
    if (!isFinite(v) || v <= 0) score = 0
    else if (a.lower) score = mean ? (mean / v) * 50 : 50
    else score = mean ? (v / mean) * 50 : 50
    return Math.max(0, Math.min(100, Math.round(score * 10) / 10))
  })
  return { axes, values, baseline: axisDefs.map(() => 50) }
}

/* ── Radar — multi-axis player profile vs a baseline ring ─────────────────── */
export function Radar({ axes, values, baseline, compareValues, compareColor = 'var(--iq-c-amber)', color = 'var(--pb-accent)', size = 240, max = 100, label }) {
  const on = useMounted()
  const cx = size / 2, cy = size / 2, R = size / 2 - 40
  const n = axes.length
  const ang = i => (-90 + i * 360 / n) * Math.PI / 180
  const pt = (i, v) => [cx + Math.cos(ang(i)) * (v / max) * R, cy + Math.sin(ang(i)) * (v / max) * R]
  const poly = vals => vals.map((v, i) => pt(i, v).map(x => x.toFixed(1)).join(',')).join(' ')
  const rings = [0.25, 0.5, 0.75, 1]

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} className="overflow-visible">
        {rings.map((r, ri) => (
          <polygon key={ri} points={axes.map((_, i) => pt(i, r * max).join(',')).join(' ')}
            fill="none" stroke="var(--pb-hairline2)" strokeWidth="1" opacity={ri === rings.length - 1 ? 0.9 : 0.5} />
        ))}
        {axes.map((a, i) => {
          const [x, y] = pt(i, max)
          const [lx, ly] = [cx + Math.cos(ang(i)) * (R + 18), cy + Math.sin(ang(i)) * (R + 18)]
          const anchor = Math.abs(lx - cx) < 6 ? 'middle' : lx > cx ? 'start' : 'end'
          return (
            <g key={a.key}>
              <line x1={cx} y1={cy} x2={x} y2={y} stroke="var(--pb-hairline)" strokeWidth="1" />
              <text x={lx} y={ly} textAnchor={anchor} dominantBaseline="middle"
                style={{ fontSize: 10.5, fill: 'var(--pb-faint)', fontFamily: 'var(--iq-font-mono)' }}>{a.label}</text>
            </g>
          )
        })}
        {baseline && (
          <polygon points={poly(baseline)} fill="none" stroke="var(--pb-faint)" strokeWidth="1.3" strokeDasharray="3 3" opacity="0.7" />
        )}
        {compareValues && (
          <polygon points={poly(compareValues)} fill={compareColor} fillOpacity="0.12" stroke={compareColor} strokeWidth="2"
            style={{ transformOrigin: 'center', transform: on ? 'scale(1)' : 'scale(0.05)', opacity: on ? 1 : 0, transition: 'transform .9s cubic-bezier(.22,.61,.36,1) .1s, opacity .5s ease' }} />
        )}
        <polygon points={poly(values)} fill={color} fillOpacity="0.16" stroke={color} strokeWidth="2"
          style={{ transformOrigin: 'center', transform: on ? 'scale(1)' : 'scale(0.05)', opacity: on ? 1 : 0,
            transition: 'transform .9s cubic-bezier(.22,.61,.36,1), opacity .5s ease' }} />
        {values.map((v, i) => { const [x, y] = pt(i, v); return <circle key={i} cx={x} cy={y} r="2.6" fill={color}
          style={{ opacity: on ? 1 : 0, transition: `opacity .3s ease ${0.5 + i * 0.05}s` }} /> })}
      </svg>
      {label && <div className="iq-eyebrow mt-1">{label}</div>}
    </div>
  )
}

/* ── WagonWheel — scoring zones, batter's view (scout-entered) ─────────────── */
export const ZONE_LABELS = ['Straight', 'Cover', 'Point', 'Third man', 'Fine leg', 'Sq leg', 'Mid-wkt', 'Long-on']
export function WagonWheel({ sectors, hand = 'RH', size = 230, color = 'var(--pb-accent)' }) {
  const on = useMounted()
  const cx = size / 2, cy = size / 2, R = size / 2 - 26
  const n = sectors.length
  const max = Math.max(...sectors, 1)
  const wedge = (i, frac) => {
    const span = (2 * Math.PI) / n
    const a0 = -Math.PI / 2 + i * span - span / 2
    const a1 = a0 + span
    const r = (frac) * R
    const x0 = cx + Math.cos(a0) * r, y0 = cy + Math.sin(a0) * r
    const x1 = cx + Math.cos(a1) * r, y1 = cy + Math.sin(a1) * r
    return `M${cx},${cy} L${x0.toFixed(1)},${y0.toFixed(1)} A${r.toFixed(1)},${r.toFixed(1)} 0 0 1 ${x1.toFixed(1)},${y1.toFixed(1)} Z`
  }
  const strongest = sectors.indexOf(max)
  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} className="overflow-visible">
        <circle cx={cx} cy={cy} r={R} fill="var(--pb-surface2)" stroke="var(--pb-hairline2)" strokeWidth="1" />
        {[0.33, 0.66, 1].map((r, i) => <circle key={i} cx={cx} cy={cy} r={R * r} fill="none" stroke="var(--pb-hairline)" strokeWidth="1" opacity="0.6" />)}
        {sectors.map((v, i) => {
          const frac = (v / max) * 0.96
          const hot = i === strongest
          return <path key={i} d={wedge(i, frac)} fill={color}
            fillOpacity={hot ? 0.85 : 0.2 + 0.5 * (v / max)} stroke={color} strokeOpacity="0.5" strokeWidth="0.5"
            style={{ transformOrigin: 'center', transform: on ? 'scale(1)' : 'scale(0)', transition: `transform .7s cubic-bezier(.34,1.3,.5,1) ${i * 0.05}s` }} />
        })}
        <rect x={cx - 4} y={cy - 16} width="8" height="32" rx="2" fill="var(--pb-text)" opacity="0.55" />
        {ZONE_LABELS.slice(0, n).map((lab, i) => {
          const span = (2 * Math.PI) / n
          const a = -Math.PI / 2 + i * span
          const lx = cx + Math.cos(a) * (R + 14), ly = cy + Math.sin(a) * (R + 14)
          const anchor = Math.abs(lx - cx) < 8 ? 'middle' : lx > cx ? 'start' : 'end'
          return <text key={i} x={lx} y={ly} textAnchor={anchor} dominantBaseline="middle"
            style={{ fontSize: 9, fill: 'var(--pb-faint)', fontFamily: 'var(--iq-font-mono)' }}>{lab}</text>
        })}
      </svg>
      <div className="iq-eyebrow mt-1">{hand} · % of runs by area</div>
    </div>
  )
}

/* ── AreaChart — trajectory with gridlines + axis ────────────────────────── */
export function AreaChart({ points, labels, h = 170, color = 'var(--pb-accent)', format = v => v }) {
  const on = useMounted()
  const w = 560
  const pad = { l: 38, r: 12, t: 14, b: 24 }
  const vals = points
  const max = Math.max(...vals) * 1.1, min = Math.min(0, ...vals)
  const range = max - min || 1
  const ix = i => pad.l + (i / (vals.length - 1)) * (w - pad.l - pad.r)
  const iy = v => pad.t + (1 - (v - min) / range) * (h - pad.t - pad.b)
  const line = vals.map((v, i) => `${i ? 'L' : 'M'}${ix(i).toFixed(1)},${iy(v).toFixed(1)}`).join(' ')
  const area = `${line} L${ix(vals.length - 1)},${h - pad.b} L${pad.l},${h - pad.b} Z`
  const gid = useMemo(() => 'ac' + Math.random().toString(36).slice(2, 7), [])
  const ticks = 3
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} className="overflow-visible">
      <defs><linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={color} stopOpacity="0.28" /><stop offset="100%" stopColor={color} stopOpacity="0" />
      </linearGradient></defs>
      {Array.from({ length: ticks + 1 }).map((_, i) => {
        const v = min + (range / ticks) * i; const y = iy(v)
        return <g key={i}>
          <line x1={pad.l} y1={y} x2={w - pad.r} y2={y} stroke="var(--pb-hairline)" strokeWidth="1" opacity="0.5" />
          <text x={pad.l - 6} y={y} textAnchor="end" dominantBaseline="middle" style={{ fontSize: 9.5, fill: 'var(--pb-faint)', fontFamily: 'var(--iq-font-mono)' }}>{format(Math.round(v))}</text>
        </g>
      })}
      <path d={area} fill={`url(#${gid})`} style={{ opacity: on ? 1 : 0, transition: 'opacity .8s ease .3s' }} />
      <path d={line} fill="none" stroke={color} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"
        style={{ strokeDasharray: 1400, strokeDashoffset: on ? 0 : 1400, transition: 'stroke-dashoffset 1.2s ease' }} />
      {vals.map((v, i) => <circle key={i} cx={ix(i)} cy={iy(v)} r="3" fill="var(--pb-surface)" stroke={color} strokeWidth="2"
        style={{ opacity: on ? 1 : 0, transition: `opacity .3s ease ${0.6 + i * 0.04}s` }} />)}
      {labels && labels.map((l, i) => <text key={i} x={ix(i)} y={h - 6} textAnchor="middle" style={{ fontSize: 9.5, fill: 'var(--pb-faint)', fontFamily: 'var(--iq-font-mono)' }}>{l}</text>)}
    </svg>
  )
}

/* ── PhaseStrip — innings phases (powerplay / middle / death) ─────────────── */
const _PHASE_COLOR = (i) => (i === 0 ? 'var(--iq-c-wkts)' : i === 1 ? 'var(--pb-accent)' : 'var(--iq-c-amber)')
const _PHASE_RANGE = { Powerplay: 'First 10 overs', Middle: 'Middle overs', Death: 'Last 10 overs' }

export function PhaseStrip({ phases }) {
  // Run rate is the metric that actually compares phases, so it's the hero here;
  // runs / wickets / overs sit underneath as supporting detail.
  return (
    <div className="space-y-3.5">
      <div className="flex w-full overflow-hidden" style={{ height: 12, borderRadius: 99, gap: 2 }}>
        {phases.map((p, i) => <div key={i} title={`${p.label}: ${p.runs} runs`}
          style={{ flexGrow: Math.max(p.runs, 1), background: _PHASE_COLOR(i), borderRadius: 3,
            transformOrigin: 'left', animation: `iq-grow .8s cubic-bezier(.22,.61,.36,1) ${i * 0.1}s both` }} />)}
      </div>
      <div className="grid grid-cols-3 gap-3">
        {phases.map((p, i) => (
          <div key={i} className="p-3.5" style={{ background: 'var(--pb-surface2)', borderRadius: 12 }}>
            <div className="iq-eyebrow" style={{ fontSize: 9, color: _PHASE_COLOR(i) }}>{p.label}</div>
            <div className="text-pb-faintest iq-mono mt-0.5" style={{ fontSize: 9.5 }}>{_PHASE_RANGE[p.label] || ''}</div>
            <div className="flex items-baseline gap-1.5 mt-2">
              <span className="iq-headline iq-num" style={{ fontSize: 24, lineHeight: 1 }}><CountUp value={p.rr} decimals={2} /></span>
              <span className="text-pb-faint text-[10px]">runs/over</span>
            </div>
            <div className="text-pb-faint text-[11px] mt-1.5 iq-num">{fmtCount(p.runs)} runs · {p.wkts} wickets · {fmtOvers(p.overs)} ov</div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── DonutStat — single percentage ring with centred figure ──────────────── */
export function DonutStat({ value, size = 92, color = 'var(--pb-accent)', label, sub }) {
  const r = (size - 12) / 2, c = 2 * Math.PI * r, cx = size / 2
  const on = useMounted()
  return (
    <div className="flex items-center gap-3">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          <circle cx={cx} cy={cx} r={r} fill="none" stroke="var(--pb-surface3)" strokeWidth="7" />
          <circle cx={cx} cy={cx} r={r} fill="none" stroke={color} strokeWidth="7" strokeLinecap="round"
            strokeDasharray={c} strokeDashoffset={on ? c - (value / 100) * c : c}
            style={{ transition: 'stroke-dashoffset 1.1s cubic-bezier(.22,.61,.36,1)' }} />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center iq-headline iq-num" style={{ fontSize: size * 0.26 }}><CountUp value={value} suffix="%" /></div>
      </div>
      {(label || sub) && <div><div className="font-semibold text-[13.5px]">{label}</div>{sub && <div className="text-pb-faint text-[12px] mt-0.5">{sub}</div>}</div>}
    </div>
  )
}
