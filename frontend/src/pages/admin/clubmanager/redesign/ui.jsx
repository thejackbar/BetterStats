import { Link } from 'react-router-dom'

// Shared tokens + small primitives for the BetterClubManager redesign.
//
// Surfaces and text reference the repo's `--pb-*` theme variables (they hold the
// exact hex the prototype used in dark mode), so the module inherits the admin
// app's theme instead of hard-coding a palette. The module accent, status and
// area colours stay as their semantic values.

// The indigo these screens used to carry is retired: they render inside the
// BetterClubhouse shell now, which sets --pb-accent to the merged module's
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

// The segmented tab control used in every screen header.
export function SegTabs({ tabs, value, onChange }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 2, background: C.surface2, border: `1px solid ${C.hair}`, borderRadius: 8, padding: 3 }}>
      {tabs.map(t => {
        const active = t.key === value
        return (
          <button key={t.key} onClick={() => onChange(t.key)}
            style={{ padding: '5px 12px', borderRadius: 6, fontSize: 12.5, fontWeight: 600, border: 'none', cursor: 'pointer', fontFamily: 'inherit',
              background: active ? 'color-mix(in srgb, var(--pb-accent) 15%, transparent)' : 'transparent', color: active ? C.accent : C.faint }}>
            {t.label}
            {t.badge != null && t.badge > 0 && (
              <span style={{ fontFamily: MONO, fontSize: 9, padding: '1px 5px', borderRadius: 999, background: 'rgba(245,181,66,0.18)', color: C.warn, marginLeft: 5 }}>{t.badge}</span>
            )}
          </button>
        )
      })}
    </div>
  )
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
