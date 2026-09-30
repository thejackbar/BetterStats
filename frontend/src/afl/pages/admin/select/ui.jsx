// Small shared pieces for football BetterSelect's screens. Plain football
// admin styling: the same tokens the rest of the football admin uses.

export function PageHead({ title, caption, right }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div className="min-w-0">
        <h1 className="text-xl font-bold">{title}</h1>
        {caption && <p className="text-sm text-pb-dim mt-1 max-w-2xl">{caption}</p>}
      </div>
      {right && <div className="flex flex-wrap items-center gap-2 max-w-full min-w-0">{right}</div>}
    </div>
  )
}

export function Btn({ children, onClick, primary, danger, disabled, small, type = 'button', title, ...rest }) {
  const tone = primary
    ? 'bg-[var(--pb-accent)] text-[var(--pb-on-accent,#08110b)] border-transparent hover:opacity-90'
    : danger
      ? 'border-[var(--pb-red,#e5484d)] text-[var(--pb-red,#e5484d)] hover:bg-[color-mix(in_srgb,var(--pb-red,#e5484d)_10%,transparent)]'
      : 'border-pb-hairline text-pb-text hover:bg-pb-surface2'
  return (
    <button type={type} onClick={onClick} disabled={disabled} title={title}
      className={`border rounded ${small ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm'} font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${tone}`}
      {...rest}>
      {children}
    </button>
  )
}

export function Card({ children, className = '', ...rest }) {
  return <div className={`bg-pb-surface border pb-hairline rounded-lg ${className}`} {...rest}>{children}</div>
}

export const INPUT = 'bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm text-pb-text focus:outline-none focus:border-[var(--pb-accent)]'

// Availability is a word as well as a colour, so it reads without the colour.
export const AVAIL = {
  AVAILABLE: { short: 'Yes', label: 'Available', color: 'var(--pb-positive, #3fb950)' },
  MAYBE: { short: 'Maybe', label: 'Maybe', color: 'var(--pb-amber, #d29922)' },
  UNAVAILABLE: { short: 'No', label: 'Unavailable', color: 'var(--pb-red, #e5484d)' },
  NO_RESPONSE: { short: '–', label: 'No answer', color: 'var(--pb-faint)' },
}

export function AvailPill({ status }) {
  const a = AVAIL[status] || AVAIL.NO_RESPONSE
  return (
    <span className="inline-block font-mono text-[10px] uppercase tracking-wide2 px-1.5 py-0.5 rounded border"
      style={{ color: a.color, borderColor: `color-mix(in srgb, ${a.color} 45%, transparent)` }}>
      {a.label}
    </span>
  )
}

export const POSITION_LABELS = {
  FB: 'Full back', HB: 'Half back', C: 'Centre', W: 'Wing', MID: 'Midfield',
  RUCK: 'Ruck', HF: 'Half forward', FF: 'Full forward', UTIL: 'Utility',
}

export function PositionChips({ positions }) {
  if (!positions?.length) return null
  return (
    <span className="inline-flex flex-wrap gap-1">
      {positions.map(p => (
        <span key={p} title={POSITION_LABELS[p] || p}
          className="font-mono text-[9px] px-1 py-px rounded bg-pb-surface2 text-pb-dim border pb-hairline">{p}</span>
      ))}
    </span>
  )
}

export const shortDate = (iso) => {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00`)
  return d.toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' })
}
