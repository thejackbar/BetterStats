// The one admin UI language — the primitives every BetterAdmin screen is
// built from, and the replacement for the four local copies that used to live
// in `bettermerch/ui.jsx`, `betterselect/ui.jsx`, `clubmanager/redesign/ui.jsx`
// and inline in the Fees and Comms pages.
//
// Sizes, radii, spacing and tones follow the design handoff in
// `docs/design_handoff_betterclubhouse/README.md`. Everything reads the `--pb-*`
// theme tokens, so a surface that re-points `--pb-accent` (every module layout
// does) restyles all of it with no per-component wiring.
//
// Two rules worth keeping:
//   1. Mono is for labels and figures. Never a button, heading or body copy.
//   2. Text on an amber fill is ON_ACCENT — one answer everywhere.

import { useEffect, forwardRef } from 'react'
import { Icon } from '../../pages/admin/betterselect/ui'

// The single ink colour for text sitting on an accent fill. Deliberately the
// dark page background rather than white/black — it reads on every module
// accent in the family.
export const ON_ACCENT = '#0a0d14'

// Accent-tinted fills, by the role each opacity plays. `color-mix` rather than
// `rgba(var(--pb-accent-rgb) …)` because `--pb-accent-rgb` is space-separated
// (`245 158 11`), which the comma-form rgba() can't parse — and because this
// mixes against whatever accent the surrounding module surface has set.
const mix = pct => `color-mix(in srgb, var(--pb-accent) ${pct}%, transparent)`
export const TINT = {
  rowWash: mix(4),
  panel: mix(8),
  nav: mix(10),
  pill: mix(12),
  chip: mix(15),
  badge: mix(18),
  border: mix(40),
  borderStrong: mix(50),
}

// Semantic tones. `ink` is the text colour (light mode darkens it), `hex` the
// fill, so a badge and its label can differ where they need to.
export const TONES = {
  ok: { ink: 'var(--pb-positive-ink)', hex: '#16c784', soft: 'rgba(22,199,132,0.12)', edge: 'rgba(22,199,132,0.28)' },
  warn: { ink: '#f5b542', hex: '#f5b542', soft: 'rgba(245,181,66,0.12)', edge: 'rgba(245,181,66,0.28)' },
  block: { ink: 'var(--pb-red-ink)', hex: '#ef5b5b', soft: 'rgba(239,91,91,0.12)', edge: 'rgba(239,91,91,0.28)' },
  accent: { ink: 'var(--pb-accent-ink)', hex: 'var(--pb-accent)', soft: TINT.pill, edge: TINT.border },
  calm: { ink: 'var(--pb-dim)', hex: 'var(--pb-dim)', soft: 'var(--pb-surface2)', edge: 'var(--pb-hairline)' },
}

export const tone = k => TONES[k] || TONES.calm

/* ── Captions and labels ─────────────────────────────────────────────── */

// A screen or section caption. `screen` picks the brighter of the two tones —
// a screen caption carries live counts, a section caption only names a group.
export function Caption({ children, screen = false, className = '', style }) {
  if (!children) return null
  return (
    <div
      className={`font-mono text-[10px] tracking-wide3 uppercase ${screen ? 'text-pb-faint' : 'text-pb-faintest'} ${className}`}
      style={style}
    >
      {children}
    </div>
  )
}

// The label above an input.
export function FieldLabel({ children, className = '' }) {
  return (
    <div className={`font-mono text-[9.5px] tracking-[0.1em] uppercase text-pb-faint mb-[5px] ${className}`}>
      {children}
    </div>
  )
}

// The label under a stat value.
export function StatLabel({ children, className = '' }) {
  return (
    <div className={`font-mono text-[9px] tracking-[0.1em] uppercase text-pb-faint ${className}`}>{children}</div>
  )
}

export function SectionHeading({ children, className = '' }) {
  return <h2 className={`font-display font-semibold text-[15.5px] text-pb-text ${className}`}>{children}</h2>
}

/* ── Buttons ─────────────────────────────────────────────────────────── */

const BTN_SIZE = {
  md: 'px-3.5 py-2 text-[13px]',
  lg: 'px-[18px] py-2.5 text-[13.5px]',
  inline: 'px-[13px] py-[7px] text-[12.5px]',
  sm: 'px-3 py-1.5 text-[12px]',
}

// Sentence case, 8px radius, never mono. `nowrap` defaults on because most of
// these labels grow from data ("Email these 34") and a wrapped label breaks out
// of its fill.
export function Button({
  children, variant = 'secondary', size = 'md', icon, onClick, disabled = false,
  type = 'button', title, className = '', style, nowrap = true, as: As = 'button', ...rest
}) {
  const base = `inline-flex items-center justify-center gap-2 rounded-lg font-body transition-colors ${BTN_SIZE[size] || BTN_SIZE.md} ${nowrap ? 'whitespace-nowrap' : ''} ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`
  const variants = {
    primary: 'font-semibold border border-transparent hover:opacity-90',
    secondary: 'border border-pb-hairline2 bg-transparent text-pb-dim hover:text-pb-text',
    soft: 'border border-pb-hairline bg-pb-surface2 text-pb-text hover:border-pb-hairline2',
    danger: 'border border-pb-red/40 bg-transparent text-pb-red hover:bg-pb-red/10',
    quiet: 'border border-transparent bg-transparent text-pb-faint hover:text-pb-text',
    // A destructive action sitting in a row of quiet ones. Same weight as its
    // neighbours until you reach for it — a bordered Delete among three
    // borderless actions reads as the important one, which it is not.
    'quiet-danger': 'border border-transparent bg-transparent text-pb-faint hover:text-pb-red',
  }
  const accentStyle = variant === 'primary' ? { background: 'var(--pb-accent)', color: ON_ACCENT } : undefined
  return (
    <As
      type={As === 'button' ? type : undefined}
      onClick={disabled ? undefined : onClick}
      disabled={As === 'button' ? disabled : undefined}
      title={title}
      className={`${base} ${variants[variant] || variants.secondary} ${className}`}
      style={{ ...accentStyle, ...style }}
      {...rest}
    >
      {icon && <Icon name={icon} size={15} />}
      {children}
    </As>
  )
}

// The 18px `?` beside a screen title that reopens its introduction.
export function HelpDot({ onClick, title = 'What is this screen for?' }) {
  return (
    <button
      type="button" onClick={onClick} title={title} aria-label={title}
      className="w-[18px] h-[18px] shrink-0 rounded-full border border-pb-hairline2 font-mono text-[10px] leading-none text-pb-faint hover:text-pb-text hover:border-pb-faint transition-colors"
    >
      ?
    </button>
  )
}

/* ── Filters ─────────────────────────────────────────────────────────── */

// Replaces the bare mono-labelled checkboxes the Fees screens used. `warn`
// gives warning-flavoured filters ("Owes money", "Quals to renew") the amber
// treatment instead of the accent one.
export function FilterPill({ active, onClick, children, warn = false, count, className = '' }) {
  const activeStyle = warn
    ? { borderColor: 'rgba(245,181,66,0.45)', background: 'rgba(245,181,66,0.12)', color: '#f5b542' }
    : { borderColor: TINT.borderStrong, background: TINT.pill, color: 'var(--pb-accent-ink)' }
  return (
    <button
      type="button" onClick={onClick} aria-pressed={!!active}
      className={`px-[11px] py-[5px] rounded-full text-[12px] border transition-colors ${active ? '' : 'border-pb-hairline2 bg-transparent text-pb-dim hover:text-pb-text'} ${className}`}
      style={active ? activeStyle : undefined}
    >
      {children}
      {count != null && <span className="font-mono text-[10px] ml-1.5 opacity-70">{count}</span>}
    </button>
  )
}

/* ── Inputs ──────────────────────────────────────────────────────────── */

// Exported so a screen that still builds an input by hand (a date cell in a
// table, a width-constrained control inside a row) dresses it the same way
// rather than inventing a fifth padding/radius pair.
export const INPUT_CLS =
  'w-full bg-pb-surface2 border border-pb-hairline2 rounded-lg px-3 py-2 text-[13.5px] text-pb-text outline-none transition-colors placeholder:text-pb-faintest focus:border-pb-accent'

// Forwards its ref, so a caller that needs the real element can have it — the
// email composer's Insert bar places a merge variable at the cursor in the
// subject field, which needs selectionStart/focus on the input itself.
export const TextInput = forwardRef(function TextInput({ className = '', ...rest }, ref) {
  return <input ref={ref} className={`${INPUT_CLS} ${className}`} {...rest} />
})

export function Select({ className = '', children, ...rest }) {
  return <select className={`${INPUT_CLS} cursor-pointer ${className}`} {...rest}>{children}</select>
}

export function TextArea({ className = '', ...rest }) {
  return <textarea className={`${INPUT_CLS} min-h-[80px] leading-[1.55] ${className}`} {...rest} />
}

export function Field({ label, children, hint, className = '', composite = false }) {
  // A field is a <label> wrapping its control, which is what gives an ordinary
  // input its accessible name and its click-the-caption-to-focus behaviour.
  //
  // `composite` turns that off, and it is NOT cosmetic. A picker is a group of
  // buttons, not one labelled control, and a <label> forwards a click on ANY
  // descendant to whichever labelable control the field holds at that moment.
  // The instant a pick re-renders the field into "the chosen name + a clear
  // button", that control is CLEAR — so the browser wipes the selection the
  // person just made, before they ever see it. Pass `composite` for anything
  // holding its own buttons; the caption then names the group instead.
  const Tag = composite ? 'div' : 'label'
  const groupProps = composite ? { role: 'group', 'aria-label': label || undefined } : {}
  return (
    <Tag className={`block ${className}`} {...groupProps}>
      {label && <FieldLabel>{label}</FieldLabel>}
      {children}
      {hint && <div className="text-[11.5px] text-pb-faintest mt-1 leading-[1.5]">{hint}</div>}
    </Tag>
  )
}

// A checkbox and its label as one target. The label is body font, not mono —
// it is a sentence the officer reads, not a column heading.
export function Checkbox({ checked, onChange, children, hint, disabled = false, className = '' }) {
  return (
    <label className={`flex items-start gap-2.5 text-[13px] text-pb-dim ${disabled ? 'opacity-50' : 'cursor-pointer'} ${className}`}>
      <input
        type="checkbox" checked={!!checked} disabled={disabled}
        onChange={e => onChange?.(e.target.checked, e)}
        className="mt-0.5 accent-pb-accent cursor-pointer shrink-0"
      />
      <span className="min-w-0">
        {children}
        {hint && <span className="block text-[11.5px] text-pb-faintest mt-0.5 leading-[1.5]">{hint}</span>}
      </span>
    </label>
  )
}

// The header search box. Capped narrow so it never crowds the stat readouts.
export function SearchInput({ value, onChange, placeholder = 'Search…', className = '' }) {
  return (
    <input
      value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      className={`${INPUT_CLS} max-w-[280px] ${className}`}
    />
  )
}

/* ── Readouts and cards ──────────────────────────────────────────────── */

// The right-hand figures in a screen header.
export function StatReadout({ value, label, ink }) {
  return (
    <div className="whitespace-nowrap">
      <div className="font-display font-bold text-[19px] pb-num" style={ink ? { color: ink } : undefined}>{value}</div>
      <StatLabel>{label}</StatLabel>
    </div>
  )
}

export function StatCard({ value, label, detail, accent = false, ink, onClick, className = '' }) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag
      onClick={onClick}
      className={`text-left bg-pb-surface border rounded-[10px] px-4 py-3.5 ${onClick ? 'cursor-pointer hover:border-pb-hairline2 transition-colors' : ''} ${accent ? '' : 'border-pb-hairline'} ${className}`}
      style={accent ? { borderColor: TINT.border } : undefined}
    >
      <div className="font-display font-bold text-[21px] pb-num" style={{ color: ink || 'var(--pb-accent-ink)' }}>{value}</div>
      <StatLabel className="mt-1">{label}</StatLabel>
      {detail && <div className="text-[12px] text-pb-dim mt-[7px] leading-[1.45]">{detail}</div>}
    </Tag>
  )
}

// A Today row. `count` is the number that makes it worth reading; `area` names
// which part of the club it came from, so one list can speak for all of them.
export function AttentionRow({ count, toneKey = 'calm', title, area, detail, children }) {
  const t = tone(toneKey)
  return (
    <div
      className="flex items-start gap-3.5 rounded-[10px] px-[17px] py-[15px] bg-pb-surface border"
      style={{ borderColor: toneKey === 'calm' ? 'var(--pb-hairline)' : t.edge }}
    >
      {count != null && (
        <div className="font-display font-bold text-[26px] leading-none pb-num shrink-0 w-11" style={{ color: t.ink }}>
          {count}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2.5 flex-wrap">
          <div className="font-display font-semibold text-[14.5px] text-pb-text">{title}</div>
          {area && (
            <span className="font-mono text-[9px] tracking-wide2 uppercase text-pb-faint bg-pb-surface2 border border-pb-hairline2 rounded px-1.5 py-0.5">
              {area}
            </span>
          )}
        </div>
        {detail && <div className="text-[12.5px] text-pb-dim mt-1 leading-[1.6]">{detail}</div>}
        {children && <div className="flex items-center gap-2 flex-wrap mt-[11px]">{children}</div>}
      </div>
    </div>
  )
}

/* ── Badges, chips, avatars ──────────────────────────────────────────── */

export function Badge({ children, toneKey = 'calm', className = '' }) {
  const t = tone(toneKey)
  return (
    <span
      className={`inline-block font-mono text-[9px] tracking-wide2 uppercase rounded px-1.5 py-0.5 border whitespace-nowrap ${className}`}
      style={{ color: t.ink, borderColor: `${t.edge}`, background: t.soft }}
    >
      {children}
    </span>
  )
}

// An accent chip — club roles, segments, family tags.
export function Chip({ children, className = '' }) {
  return (
    <span
      className={`inline-block text-[12.5px] rounded-[5px] px-2.5 py-[3px] ${className}`}
      style={{ background: TINT.chip, color: 'var(--pb-accent-ink)' }}
    >
      {children}
    </span>
  )
}

export function initials(name) {
  return (name || '?')
    .split(/\s+/).filter(Boolean).map(w => w[0]).slice(0, 2).join('').toUpperCase() || '?'
}

export function Initials({ name, size = 30, className = '' }) {
  return (
    <span
      className={`inline-flex items-center justify-center rounded-full bg-pb-surface2 border border-pb-hairline2 text-pb-dim font-display font-semibold shrink-0 ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.36) }}
    >
      {initials(name)}
    </span>
  )
}

/* ── Lists ───────────────────────────────────────────────────────────── */

// A master-list row: avatar, name, sub-line, optional flag dot and figure. The
// avatar is for people — pass `avatar={false}` for a list of things.
export function ListRow({ name, sub, figure, flag = false, selected = false, avatar = true, onClick }) {
  return (
    <button
      type="button" onClick={onClick} title={sub || undefined}
      className={`w-full flex items-center gap-2.5 px-[11px] py-[9px] rounded-lg text-left border transition-colors ${selected ? '' : 'border-transparent hover:bg-pb-surface2'}`}
      style={selected ? { borderColor: TINT.border, background: TINT.panel } : undefined}
    >
      {avatar && <Initials name={name} />}
      <span className="min-w-0 flex-1">
        <span className="block text-[13.5px] font-semibold text-pb-text truncate">{name}</span>
        {sub && <span className="block font-mono text-[9.5px] uppercase text-pb-faint truncate">{sub}</span>}
      </span>
      {flag && <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: '#f5b542' }} />}
      {figure != null && (
        <span className="font-mono text-[10px] shrink-0 pb-num"
          style={{ color: selected ? 'var(--pb-accent-ink)' : 'var(--pb-faintest)' }}>
          {figure}
        </span>
      )}
    </button>
  )
}

/* ── Tables ──────────────────────────────────────────────────────────── */

// Grid tables: the head, every row and the footer share one
// `grid-template-columns` and a `min-width` that clears the fixed tracks, and
// the whole thing scrolls horizontally rather than collapsing. The first track
// is always `minmax(<real px>, 1fr)` — `minmax(0, 1fr)` collapses to nothing
// once the fixed tracks exceed the container.
export function TableWrap({ children, className = '' }) {
  return (
    <div className={`bg-pb-surface border border-pb-hairline rounded-[10px] overflow-x-auto pb-scroll ${className}`}>
      {children}
    </div>
  )
}

export function TableHead({ cols, minWidth, children }) {
  return (
    <div
      className="grid items-center bg-pb-surface2 font-mono text-[9px] tracking-[0.12em] uppercase text-pb-faint"
      style={{ gridTemplateColumns: cols, minWidth }}
    >
      {children}
    </div>
  )
}

export function TableRow({ cols, minWidth, onClick, selected = false, attention = false, children }) {
  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(e) } } : undefined}
      className={`grid items-center border-t border-pb-hairline ${onClick ? 'cursor-pointer' : ''}`}
      style={{
        gridTemplateColumns: cols,
        minWidth,
        background: selected ? TINT.panel : attention ? TINT.rowWash : undefined,
      }}
    >
      {children}
    </div>
  )
}

export function TableFootRow({ cols, minWidth, children }) {
  return (
    <div
      className="grid items-center border-t border-pb-hairline2 bg-pb-surface2"
      style={{ gridTemplateColumns: cols, minWidth }}
    >
      {children}
    </div>
  )
}

// One cell. `head` switches to the head's padding; `num` right-aligns and sets
// tabular mono, which is what every money and count column wants.
export function Cell({ children, num = false, head = false, first = false, last = false, className = '', style }) {
  return (
    <div
      className={`min-w-0 ${head ? 'py-2.5' : 'py-[11px]'} px-3 ${num ? 'text-right font-mono text-[11px] pb-num' : 'text-[13px]'} ${first ? 'pl-4' : ''} ${last ? 'pr-4' : ''} ${className}`}
      style={style}
    >
      {children}
    </div>
  )
}

/* ── Overlays ────────────────────────────────────────────────────────── */

// The one dialog in BetterAdmin, lifted from the Directory's "+ Add person"
// so every modal in the module reads the same: a 0.55 scrim, a surface card on
// a 12px radius with the stronger hairline, a 17px title with an optional
// sentence under it, and the actions right-aligned in a footer that ends in the
// one primary button.
//
// `onClose` fires on the scrim, on Escape and on the ✕ — a dialog you can only
// leave by finding the Cancel button is the thing this replaces. Pass
// `dismissable={false}` for a step that must be finished or explicitly
// cancelled (a running import), which leaves the ✕ and Cancel as the only ways
// out.
export function Modal({
  open = true, onClose, title, subtitle, footer, width = 460,
  dismissable = true, children, className = '',
}) {
  useEffect(() => {
    if (!open || !dismissable) return
    const onKey = e => { if (e.key === 'Escape') onClose?.() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, dismissable, onClose])

  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-5"
      style={{ background: 'rgba(0,0,0,0.55)' }}
      onClick={dismissable ? e => { if (e.target === e.currentTarget) onClose?.() } : undefined}
      role="dialog" aria-modal="true"
    >
      <div
        className={`ch-rise bg-pb-surface border border-pb-hairline2 rounded-xl w-full flex flex-col max-h-[88vh] ${className}`}
        style={{ maxWidth: width, boxShadow: '0 12px 48px rgba(0,0,0,0.45)' }}
      >
        {(title || onClose) && (
          <div className="flex items-start gap-3 px-5 pt-[18px] pb-3 shrink-0">
            <div className="min-w-0 flex-1">
              {title && <h2 className="font-display font-bold text-[17px] text-pb-text leading-snug">{title}</h2>}
              {subtitle && <div className="text-[12.5px] text-pb-faint mt-1 leading-[1.55]">{subtitle}</div>}
            </div>
            {onClose && (
              <button
                type="button" onClick={onClose} aria-label="Close"
                className="shrink-0 -mt-1 -mr-1 p-1.5 rounded-lg text-pb-faint hover:text-pb-text hover:bg-pb-surface2 transition-colors"
              >
                ✕
              </button>
            )}
          </div>
        )}
        <div className="px-5 pb-1 overflow-y-auto pb-scroll">{children}</div>
        {footer && (
          <div className="flex items-center justify-end gap-2 flex-wrap px-5 py-4 mt-1 shrink-0">{footer}</div>
        )}
      </div>
    </div>
  )
}

export function Drawer({ width = 440, onClose, children }) {
  return (
    <div
      className="fixed inset-0 z-[90] flex justify-end"
      style={{ background: 'rgba(0,0,0,0.55)' }}
      onClick={onClose}
    >
      <div
        className="pb-scroll ch-rise bg-pb-surface border-l border-pb-hairline2 overflow-y-auto"
        style={{ width, maxWidth: '92vw', boxShadow: '0 0 40px rgba(0,0,0,0.5)' }}
        onClick={e => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}

// Dismissed by hand, never on a timer — it usually reports something the
// officer just caused and may want to read twice.
export function Toast({ toast, onClose }) {
  if (!toast) return null
  return (
    <div
      className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[120] bg-pb-surface border rounded-[10px] px-[18px] py-[13px] flex items-center gap-3 ch-rise"
      style={{ borderColor: TINT.borderStrong, boxShadow: '0 8px 40px rgba(0,0,0,0.6)' }}
      role="status"
    >
      <span className="min-w-0">
        <span className="block text-[13.5px] font-semibold" style={{ color: 'var(--pb-accent-ink)' }}>{toast.title}</span>
        {toast.body && <span className="block text-[13px] text-pb-dim">{toast.body}</span>}
      </span>
      <button onClick={onClose} className="text-pb-faint hover:text-pb-text shrink-0" aria-label="Dismiss">✕</button>
    </div>
  )
}

/* ── Misc ────────────────────────────────────────────────────────────── */

// An accent-tinted explanatory panel — the consolidation notes, the "what this
// does" consequence preview, the notice strip above a table.
export function Note({ children, title, toneKey = 'accent', className = '' }) {
  const t = tone(toneKey)
  return (
    <div
      className={`rounded-lg px-3.5 py-3 text-[12.5px] leading-[1.6] ${className}`}
      style={{ background: t.soft, border: `1px solid ${toneKey === 'accent' ? mix(35) : t.edge}`, color: 'var(--pb-dim)' }}
    >
      {title && <div className="font-mono text-[9px] tracking-wide2 uppercase mb-1.5" style={{ color: t.ink }}>{title}</div>}
      {children}
    </div>
  )
}

export function Empty({ children, className = '' }) {
  return <div className={`text-[13px] text-pb-faint py-8 text-center ${className}`}>{children}</div>
}

export { Icon }
