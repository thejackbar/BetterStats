// Small pieces shared by the player's own page (the availability link's dashboard).
// Declared at module level, never inside a render function.
import { createContext, useContext } from 'react'
import { DEFAULT_WEEK_NAMES } from '../../lib/availability'

export function fmtDay(d) {
  try {
    return new Date(d + 'T00:00:00').toLocaleDateString(undefined, {
      weekday: 'long', day: 'numeric', month: 'short',
    })
  } catch { return d }
}

// "13:00" → "1:00pm". The time is the club's own local display string, so an
// unexpected format is shown as it came rather than guessed at.
export function fmtTime(t) {
  const m = /^(\d{1,2}):(\d{2})(?::\d{2})?$/.exec((t || '').trim())
  if (!m) return (t || '').trim()
  const h = Number(m[1])
  if (h > 23) return t
  return `${h % 12 === 0 ? 12 : h % 12}:${m[2]}${h >= 12 ? 'pm' : 'am'}`
}

export function Tag({ children, tone }) {
  return (
    <span className="font-mono text-[9.5px] tracking-wide2 uppercase rounded px-1.5 py-0.5 shrink-0"
      style={tone
        ? { background: `color-mix(in srgb, ${tone} 16%, transparent)`, color: tone }
        : { background: 'var(--pb-surface2)', color: 'var(--pb-faint)' }}>
      {children}
    </span>
  )
}

export function fmtShort(d) {
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) } catch { return d }
}

// "W1 · 2-day game" (the club's own week name) for the days of a two-day game,
// '' for an ordinary date.
export function weekLabel(d, names) {
  const f = (d.fixtures || []).find((x) => x.two_day)
  if (!f) return ''
  const n = { ...DEFAULT_WEEK_NAMES, ...(names || {}) }
  return `${f.role === 'day2' ? n.w2 : n.w1} · 2-day game`
}

// A card on its own, or (inside a collapsible group, which sets this context) a
// plain block under the group's header: no second border, and no label when the
// group's own title already says it.
export const GroupContext = createContext(null)

export function Section({ title, children, className = '' }) {
  const group = useContext(GroupContext)
  if (group) {
    return (
      <section className={`py-3 border-t pb-hairline first:border-t-0 first:pt-0 min-w-0 ${className}`}>
        {!group.hideTitle && <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-2">{title}</div>}
        {children}
      </section>
    )
  }
  return (
    <section className={`rounded-xl border pb-hairline p-3.5 mb-3 min-w-0 break-inside-avoid ${className}`}>
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-2">{title}</div>
      {children}
    </section>
  )
}

export const money = (n) => `${n < 0 ? '-' : ''}$${Math.abs(Number(n) || 0).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export function Muted({ children, ...rest }) {
  return <div className="text-sm text-pb-faint" {...rest}>{children}</div>
}

// A line of label and value, for the small figure grids.
export function Stat({ label, value }) {
  return (
    <div className="rounded-lg px-3 py-2" style={{ background: 'var(--pb-surface2)' }}>
      <div className="font-display font-bold text-[18px] leading-tight">{value ?? '-'}</div>
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint mt-0.5">{label}</div>
    </div>
  )
}
