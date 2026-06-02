import { useState } from 'react'

/* KeyPlayersCard — a "showcase" card for a club's key players, adapted from the
 * Uiverse crypto-card pattern (segmented toggle → featured panel → animated
 * sparkline), themed to BetterIQ's violet accent + pb-* tokens. Flick between
 * the top players; each shows a headline number, supporting stats, their record
 * vs us, and a drawn form sparkline. */

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)

function surname(name) {
  const s = (name || '').split(',')[0].trim()
  return s || name || '?'
}

function RiskBadge({ risk }) {
  if (!risk) return null
  const color = risk === 'high' ? 'var(--pb-red)' : 'var(--pb-amber)'
  return <span className="font-mono text-[9px] px-1.5 py-0.5 rounded uppercase" style={{ background: `color-mix(in srgb, ${color} 16%, transparent)`, color }}>{risk} risk</span>
}

function ConfChip({ c }) {
  if (!c) return null
  return <span className="font-mono text-[9px] px-1.5 py-0.5 rounded uppercase text-pb-faint border pb-hairline" title="confidence from sample size">{c} conf</span>
}

function AlertBadge({ alert }) {
  if (!alert?.level) return null
  const danger = alert.level === 'danger'
  const color = danger ? 'var(--pb-red)' : 'var(--pb-amber)'
  const reasons = (danger ? alert.danger : alert.caution) || []
  return (
    <span title={reasons.join(' · ')} className="font-mono text-[9px] px-1.5 py-0.5 rounded uppercase font-bold" style={{ background: `color-mix(in srgb, ${color} 18%, transparent)`, color }}>
      {danger ? 'Danger' : 'Paper tiger?'}
    </span>
  )
}

function sparkPath(values, w = 100, h = 40) {
  const vals = (values || []).filter(v => v !== null && v !== undefined)
  if (vals.length < 2) return { line: '', area: '' }
  const max = Math.max(1, ...vals)
  const stepX = w / (vals.length - 1)
  const pts = vals.map((v, i) => [i * stepX, h - (v / max) * (h - 4) - 2])
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  return { line, area: `${line} L${w},${h} L0,${h} Z` }
}

export default function KeyPlayersCard({ title, subtitle, players, kind = 'bat' }) {
  const [sel, setSel] = useState(0)
  if (!players?.length) return null
  const list = players.slice(0, 5)
  const i = Math.min(sel, list.length - 1)
  const p = list[i]
  const n = list.length

  const spark = kind === 'bat'
    ? (p.recent_scores || []).map(s => parseInt(String(s).replace('*', ''), 10) || 0)
    : (p.recent_wickets || [])
  const { line, area } = sparkPath(spark)

  const headline = kind === 'bat' ? p.runs : p.wickets
  const unit = kind === 'bat' ? 'runs' : 'wkts'
  const sub = kind === 'bat'
    ? `avg ${num(p.average)} · SR ${num(p.strike_rate)}`
    : `avg ${num(p.average)} · econ ${num(p.economy)}`
  const formLabel = p.form === 'hot' ? 'In form' : p.form === 'cold' ? 'Out of form' : null
  const vs = p.vs_us

  return (
    <div className="rounded-3xl p-5 border"
      style={{ background: 'color-mix(in srgb, var(--pb-accent) 6%, var(--pb-surface))', borderColor: 'color-mix(in srgb, var(--pb-accent) 25%, transparent)' }}>
      <style>{`@keyframes iqDraw{to{stroke-dashoffset:0}}`}</style>

      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-wide3" style={{ color: 'var(--pb-accent)' }}>{title}</div>
          {subtitle && <div className="text-pb-faint text-[11px] truncate">{subtitle}</div>}
        </div>
        <span className="flex items-center gap-1.5 shrink-0">
          <AlertBadge alert={p.alert} />
          {formLabel && (
            <span className="font-mono text-[10px] px-2 py-0.5 rounded-full whitespace-nowrap"
              style={{ background: 'color-mix(in srgb, var(--pb-accent) 16%, transparent)', color: 'var(--pb-accent)' }}>{formLabel}</span>
          )}
        </span>
      </div>

      {/* segmented toggle with sliding pill */}
      <div className="relative flex rounded-2xl p-1 mb-4" style={{ background: 'var(--pb-surface2)' }}>
        <div className="absolute top-1 bottom-1 rounded-xl transition-all duration-300 ease-out"
          style={{
            left: `calc(${i} * ${100 / n}% + 3px)`, width: `calc(${100 / n}% - 6px)`,
            background: 'color-mix(in srgb, var(--pb-accent) 22%, transparent)',
            border: '1px solid color-mix(in srgb, var(--pb-accent) 45%, transparent)',
          }} />
        {list.map((pl, idx) => (
          <button key={pl.player_id || idx} onClick={() => setSel(idx)}
            className="relative z-10 flex-1 text-center py-1.5 rounded-xl text-[12px] font-medium truncate px-1 transition-colors"
            style={{ color: idx === i ? 'var(--pb-text)' : 'var(--pb-faint)' }}>
            {surname(pl.name)}
          </button>
        ))}
      </div>

      {/* featured */}
      <div className="flex items-end justify-between gap-3 mb-2">
        <div className="min-w-0">
          <div className="font-display font-bold text-lg leading-tight truncate">{p.name}</div>
          <div className="text-pb-faint text-xs mt-0.5">{sub}</div>
        </div>
        <div className="text-right shrink-0">
          <div className="font-display font-bold text-3xl pb-num leading-none">
            {num(headline, 0)}<span className="text-pb-faint text-sm font-normal ml-1">{unit}</span>
          </div>
          {vs && (kind === 'bat'
            ? (vs.runs ? <div className="text-pb-faintest text-[11px] pb-num mt-1">{vs.runs} @ {num(vs.average)} vs us</div> : null)
            : (vs.wickets ? <div className="text-pb-faintest text-[11px] pb-num mt-1">{vs.wickets}w @ {num(vs.average)} vs us</div> : null))}
        </div>
      </div>

      {/* drawn sparkline */}
      <div className="rounded-xl overflow-hidden mt-2" style={{ background: 'var(--pb-surface2)', height: 64 }}>
        {line ? (
          <svg key={p.player_id || i} viewBox="0 0 100 40" preserveAspectRatio="none" className="w-full h-full block">
            <path d={area} stroke="none" style={{ fill: 'color-mix(in srgb, var(--pb-accent) 18%, transparent)' }} />
            <path d={line} fill="none" stroke="var(--pb-accent)" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round"
              style={{ strokeDasharray: 320, strokeDashoffset: 320, animation: 'iqDraw 1.1s ease forwards' }} />
          </svg>
        ) : (
          <div className="h-full flex items-center justify-center text-pb-faintest text-[11px]">recent form unavailable</div>
        )}
      </div>
      <div className="text-pb-faintest text-[10px] mt-1.5 pb-num truncate">
        {kind === 'bat'
          ? ((p.recent_scores || []).join('  ') || '—')
          : ((p.recent_wickets || []).map(w => `${w}w`).join('  ') || '—')}
      </div>

      {/* scouting note — the rule-based analyst read */}
      {p.key_note && (
        <div className="mt-3 pt-3 border-t" style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 18%, transparent)' }}>
          <div className="text-[13px] leading-snug">{p.key_note}</div>
          {p.alert && (
            <div className="text-[11px] mt-1" style={{ color: p.alert.level === 'danger' ? 'var(--pb-red)' : 'var(--pb-amber)' }}>
              {p.alert.level === 'danger' ? '⚑ ' : '⚠ '}{(p.alert.level === 'danger' ? p.alert.danger : p.alert.caution).join(' · ')}
            </div>
          )}
          <div className="flex items-center justify-between gap-2 mt-2">
            {p.plan && <span className="text-[12px] min-w-0 truncate"><span className="text-pb-faint">Plan:</span> <span className="font-medium">{p.plan}</span></span>}
            <span className="flex items-center gap-1.5 shrink-0"><RiskBadge risk={p.risk} /><ConfChip c={p.confidence} /></span>
          </div>
        </div>
      )}
    </div>
  )
}
