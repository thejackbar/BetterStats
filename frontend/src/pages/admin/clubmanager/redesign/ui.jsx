import { useState, useCallback, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../../../contexts/AuthContext'

// Shared tokens + small primitives for the BetterClubManager redesign.
//
// Surfaces and text reference the repo's `--pb-*` theme variables (they hold the
// exact hex the prototype used in dark mode), so the module inherits the admin
// app's theme instead of hard-coding a palette. The module accent, status and
// area colours stay as their semantic values.

// The indigo these screens used to carry is retired: they render inside the
// BetterAdmin shell now, which sets --pb-accent to the merged module's
// amber. Everything here just follows the surrounding surface's accent.
export const ACCENT = 'var(--pb-accent)'

export const C = {
  bg: 'var(--pb-bg)',
  surface: 'var(--pb-surface)',
  surface2: 'var(--pb-surface2)',
  hair: 'var(--pb-hairline)',
  hair2: 'var(--pb-hairline2)',
  text: 'var(--pb-text)',
  dim: 'var(--pb-dim)',        // #8a90a2 — secondary
  faint: 'var(--pb-faint)',    // #5b6072 — tertiary / meta
  faintest: 'var(--pb-faintest)', // #3a3f50 — captions
  accent: ACCENT,
  ok: '#16c784',
  warn: '#f5b542',
  block: '#ef5b5b',
}

export const MONO = "'JetBrains Mono', monospace"

// A JetBrains Mono all-caps caption. `dim` picks the faint tone; default is the
// faintest (section-caption) tone.
export function Caption({ children, tone, style }) {
  return (
    <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: tone || C.faintest, textTransform: 'uppercase', ...style }}>
      {children}
    </div>
  )
}

// The chrome of the segmented control, on its own.
//
// `SegTabs` below is the common case — one row, one value, pick exactly one.
// Plenty of header rows are not that: the Directory's Membership / Role / More
// are MENUS, and the Club Diary's "Overdue & blocked only" is an independent
// toggle. Those rows still have to read as Committee's, so the box is exported
// separately and they fill it with their own controls rather than inventing a
// lookalike.
export const SEG_GROUP = {
  display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 2,
  background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 8, padding: 3,
}
// The one button inside that box, as a style rather than a component, so a
// <button> and a MenuButton's own trigger can both wear it.
export const segItemStyle = (active, tone) => ({
  padding: '5px 12px', borderRadius: 6, fontSize: 12.5, fontWeight: 600, border: 'none',
  cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
  background: active ? (tone === 'red' ? 'rgba(239,91,91,0.18)' : 'color-mix(in srgb, var(--pb-accent) 15%, transparent)') : 'transparent',
  color: active ? (tone === 'red' ? C.block : C.accent) : C.faint,
})

export function SegGroup({ children, style }) {
  return <div style={{ ...SEG_GROUP, ...style }}>{children}</div>
}

// One button inside a SegGroup, for a row whose buttons are not one
// mutually-exclusive value.
export function SegItem({ active, onClick, children, tone }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={!!active} style={segItemStyle(active, tone)}>
      {children}
    </button>
  )
}

// The segmented tab control used in every screen header. Wraps rather than
// running off the side of a phone — the Directory's filter chips already wrap,
// and a control you have to scroll sideways to reach hides its own options.
export function SegTabs({ tabs, value, onChange, style }) {
  return (
    <SegGroup style={style}>
      {tabs.map(t => (
        <button key={t.key} onClick={() => onChange(t.key)} type="button"
          aria-pressed={t.key === value} style={segItemStyle(t.key === value)}>
          {t.label}
          {t.badge != null && t.badge > 0 && (
            <span style={{ fontFamily: MONO, fontSize: 9, padding: '1px 5px', borderRadius: 999, background: 'rgba(245,181,66,0.18)', color: C.warn, marginLeft: 5 }}>{t.badge}</span>
          )}
        </button>
      ))}
    </SegGroup>
  )
}

// CENTRING A BUTTON ROW ON THE TITLE LINE TAKES THREE PARTS, NOT ONE. The title
// block and the right-hand group each claim an equal share of what is left
// (`flex: 1 1 0`), so the row between them lands in the middle of the header
// rather than wherever the title happens to end. Same rule `ModuleLayout`'s own
// `tabs` prop follows, so a Clubhouse screen built on either shell centres its
// buttons the same way.
//
// The title carries its own `minWidth: 0` + ellipsis, since with a zero basis
// it is the side that gives way first on a phone.
export const HEAD_SIDE = { flex: '1 1 0', minWidth: 0 }
// The centre group MAY SHRINK, and that is load-bearing rather than a detail:
// `flex-wrap` on the header cannot save a child that has been told not to
// shrink, so a `flexShrink: 0` here pushed Areas & Roles 68px sideways at 390px
// the moment its four buttons no longer fitted. Because both sides have a ZERO
// basis, they give way first — so the centre only ever shrinks once there is
// genuinely nothing left, which is exactly when its own buttons should wrap.
export const HEAD_CENTRE = { display: 'flex', alignItems: 'center', justifyContent: 'center', flex: '0 1 auto', minWidth: 0 }
export const HEAD_SIDE_END = { ...HEAD_SIDE, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 10, flexWrap: 'wrap' }

// The search box on its own line under the heading — the place Committee and
// the Directory both carry theirs. `flex: 1 1 100%` is what makes the wrapping
// header break before it; `box-sizing` is what stops the padding being added on
// top of the cap and pushing the page sideways on a phone.
export function HeaderSearch({ value, onChange, placeholder, width = 380 }) {
  const q = (value || '').trim()
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: '1 1 100%', maxWidth: '100%' }}>
      <input value={value || ''} onChange={e => onChange(e.target.value)}
        placeholder={placeholder} aria-label={placeholder}
        style={{ width, maxWidth: '100%', minWidth: 0, boxSizing: 'border-box', background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 8, padding: '8px 12px', color: C.text, fontSize: 13.5, outline: 'none', fontFamily: 'inherit' }} />
      {q && (
        <button onClick={() => onChange('')} type="button"
          style={{ background: 'transparent', border: 'none', color: C.faint, fontFamily: MONO, fontSize: 10, cursor: 'pointer' }}>CLEAR</button>
      )}
    </div>
  )
}

// Case-folded substring over any number of fields — the one search rule, so no
// two screens narrow their lists differently.
export function matchesQuery(q, ...vals) {
  if (!q) return true
  const needle = q.trim().toLowerCase()
  if (!needle) return true
  return vals.some(v => v != null && String(v).toLowerCase().includes(needle))
}

// Right-aligned stat readouts in a screen header.
export function StatReadout({ value, label, fg }) {
  return (
    <div style={{ whiteSpace: 'nowrap' }}>
      <div style={{ fontWeight: 700, fontSize: 19, fontVariantNumeric: 'tabular-nums', color: fg || C.text }}>{value}</div>
      <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint }}>{label}</div>
    </div>
  )
}

const TONE = {
  ok: { bg: 'rgba(22,199,132,0.12)', fg: '#16c784' },
  warn: { bg: 'rgba(245,181,66,0.12)', fg: '#f5b542' },
  block: { bg: 'rgba(239,91,91,0.12)', fg: '#ef5b5b' },
  info: { bg: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)', fg: 'var(--pb-accent)' },
}

// The toast / feedback strip that sits directly under a screen header.
export function Toast({ toast, onClear }) {
  if (!toast) return null
  const t = TONE[toast.tone] || TONE.info
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 20px', fontSize: 13, borderBottom: `1px solid ${C.hair}`, background: t.bg, color: t.fg }}>
      <span style={{ fontWeight: 600 }}>{toast.title}</span>
      <span style={{ opacity: 0.85 }}>{toast.body}</span>
      <span style={{ marginLeft: 'auto', cursor: 'pointer', opacity: 0.6 }} onClick={onClear}>✕</span>
    </div>
  )
}

// The ☰ button shown in each screen header below 1280px.
export function NavToggle({ narrow, onClick }) {
  if (!narrow) return null
  return (
    <button onClick={onClick}
      style={{ background: 'transparent', border: `1px solid ${C.hair2}`, borderRadius: 7, color: C.dim, fontSize: 15, lineHeight: 1, padding: '7px 9px', cursor: 'pointer' }}>
      ☰
    </button>
  )
}

// The sticky screen header wrapper — establishes a stacking context above the
// off-canvas drawer (z-index 80) so its ☰ button is never painted over.
export function ScreenHeader({ children }) {
  return (
    <header style={{ position: 'sticky', top: 0, zIndex: 80, borderBottom: `1px solid ${C.hair}`, background: C.surface, padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
      {children}
    </header>
  )
}

export function HeaderTitle({ title, sub }) {
  return (
    <div>
      <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>{title}</h1>
      {sub && <Caption tone={C.faint} style={{ marginTop: 2 }}>{sub}</Caption>}
    </div>
  )
}

// A right-hand overlay drawer (person record, diary task). Clicking the scrim
// closes; clicks inside stop propagation. Enters with the riseIn keyframe.
export function Drawer({ width = 440, zIndex = 90, onClose, children }) {
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex, display: 'flex', justifyContent: 'flex-end', background: 'rgba(0,0,0,0.55)' }} onClick={onClose}>
      <div className="pb-scroll" onClick={e => e.stopPropagation()}
        style={{ width, maxWidth: '92vw', background: C.surface, borderLeft: `1px solid ${C.hair2}`, overflowY: 'auto', animation: 'chRise 180ms ease both', boxShadow: '0 0 40px rgba(0,0,0,0.5)' }}>
        {children}
      </div>
    </div>
  )
}

export function initials(name) { return name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase() }

// A screen preference that belongs to the PERSON, not the club — how wide they
// want a column, whether a panel is open. Two people sharing a club admin login
// is common, so these key on the user id the same way the screen introductions
// do, and survive the browser being closed.
//
// The initial read happens in the state initialiser rather than an effect: read
// it afterwards and the screen renders once at the default first, which reads
// as the panel snapping shut a frame after it opened.
export function usePref(key, fallback) {
  const { user } = useAuth()
  const full = `bs_pref_${key}_${user?.id || 'anon'}`
  const [value, setValue] = useState(() => {
    try { const v = localStorage.getItem(full); return v == null ? fallback : JSON.parse(v) } catch { return fallback }
  })
  const set = useCallback(next => {
    setValue(prev => {
      const v = typeof next === 'function' ? next(prev) : next
      try { localStorage.setItem(full, JSON.stringify(v)) } catch { /* private mode */ }
      return v
    })
  }, [full])
  return [value, set]
}

// A button that opens a small menu under itself.
//
// The reason this exists: a screen whose filters are one flat row of pills does
// not scale. The Directory's row reached ~26 controls, and the membership ones
// come from the club's own catalogue, so a club with a long catalogue got a
// longer row again. A menu holds the same options in one control, and the count
// of controls stops depending on the club's data.
//
// `value` is the current selection, shown on the button so the menu never has
// to be opened to read the state. `children` is called with `close`, so an item
// decides for itself whether picking it dismisses the menu.
export function MenuButton({ label, value, width = 250, align = 'left', disabled, seg = false, children }) {
  const [open, setOpen] = useState(false)
  // Which edge the panel hangs off, decided from where the button actually sits
  // when it opens. A left-aligned panel on a button near the right of the screen
  // runs off the page — which is what the Directory's and Accounts' "More" menu
  // did, since both sit at the end of their row.
  const [side, setSide] = useState(align)
  const wrap = useRef(null)
  useEffect(() => {
    if (!open) return
    // Pointerdown, not click: a click listener fires after React has already
    // handled the item's own onClick, so a menu that re-renders its trigger
    // would reopen itself.
    const onDown = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('pointerdown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  // Measured on open rather than assumed: the same button is near the middle on
  // a wide screen and hard right on a narrow one, and a filter row wraps.
  const place = () => {
    const r = wrap.current?.getBoundingClientRect()
    if (!r) return setSide(align)
    const room = window.innerWidth - r.left - 8
    setSide(room < width ? 'right' : align)
  }

  const on = !!value
  return (
    <div ref={wrap} style={{ position: 'relative', flexShrink: 0 }}>
      {/* `seg` wears the segmented control's own button styling, for a menu
          sitting inside a SegGroup — that is what lets the Directory's and
          Payments' filter menus read as Committee's section buttons rather
          than as a second, differently-shaped control beside them. */}
      <button type="button" disabled={disabled} onClick={() => { if (!open) place(); setOpen(o => !o) }}
        style={seg ? { ...segItemStyle(on), display: 'inline-flex', alignItems: 'center', gap: 6, maxWidth: 230, opacity: disabled ? 0.5 : 1 } : {
          display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 11px', borderRadius: 8,
          fontSize: 12.5, cursor: disabled ? 'default' : 'pointer', maxWidth: 230,
          border: `1px solid ${on ? 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' : C.hair2}`,
          background: on ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent',
          color: on ? C.accent : C.dim, opacity: disabled ? 0.5 : 1,
        }}>
        <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {label}{on ? ': ' + value : ''}
        </span>
        <span style={{ fontSize: 9, opacity: 0.7 }}>▾</span>
      </button>
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 5px)', [side]: 0, zIndex: 60,
          width, maxWidth: 'calc(100vw - 24px)',
          maxHeight: 340, overflowY: 'auto', background: C.surface,
          border: `1px solid ${C.hair2}`, borderRadius: 10, padding: 5,
          boxShadow: '0 10px 28px rgba(0,0,0,0.34)',
        }}>
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  )
}

// One row inside a MenuButton. `on` draws the tick, so a menu reads as its own
// state rather than needing the button's label to carry everything.
export function MenuItem({ on, onClick, children, tone, disabled }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left',
        padding: '7px 9px', borderRadius: 7, fontSize: 13, border: 'none', background: 'transparent',
        color: disabled ? C.faintest : (tone || (on ? C.accent : C.text)),
        cursor: disabled ? 'default' : 'pointer',
      }}
      onMouseEnter={e => { if (!disabled) e.currentTarget.style.background = C.surface2 }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
      {/* The glyph is only RENDERED when on, not just faded out: left in the
          DOM at opacity 0 it lands in every item's accessible name, so a
          screen reader announces a tick on an unticked row. The span keeps its
          width either way so the labels stay aligned. */}
      <span aria-hidden="true" style={{ width: 12, flexShrink: 0, fontSize: 11 }}>{on ? '✓' : ''}</span>
      <span style={{ minWidth: 0, flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{children}</span>
    </button>
  )
}

// A heading inside a MenuButton, for a menu holding more than one kind of thing.
export function MenuHeading({ children }) {
  return (
    <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.12em', color: C.faintest, padding: '8px 9px 4px' }}>
      {children}
    </div>
  )
}

export function MenuDivider() {
  return <div style={{ height: 1, background: C.hair, margin: '5px 4px' }} />
}

// One active filter, shown under the controls with the ✕ that clears it.
//
// The menus keep the CONTROLS few; these keep the STATE visible, which is what
// a menu costs you. Nothing draws when nothing is filtered, so the quiet case
// stays quiet.
export function FilterChip({ children, onClear }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 6px 3px 10px', borderRadius: 999,
      fontSize: 12, border: '1px solid color-mix(in srgb, var(--pb-accent) 45%, transparent)',
      background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)', color: C.accent,
    }}>
      {children}
      <span onClick={onClear} title="Clear" style={{ cursor: 'pointer', opacity: 0.75, fontSize: 13, lineHeight: 1 }}>×</span>
    </span>
  )
}

// The link from a read-only screen to the editor that owns its data.
//
// These screens are viewers; the create/edit/delete for meetings, motions,
// events, bookings and the diary lives in the older full editors, which lost
// their routes when these screens took the URLs. Rather than leave that CRUD
// unreachable, every viewer points at its editor until the two are folded
// together. `margin-left: auto` puts it at the right-hand end of the header.
export function ManageLink({ to, children = 'Manage' }) {
  return (
    <Link to={to} style={{
      marginLeft: 'auto', flexShrink: 0, padding: '7px 13px', borderRadius: 8,
      fontSize: 12.5, fontWeight: 600, border: `1px solid ${C.hair2}`,
      color: C.dim, textDecoration: 'none', whiteSpace: 'nowrap',
    }}>{children}</Link>
  )
}
