// BetterFantasyCricket — shared UI primitives for the FPL-style member app.
//
// Everything reads the `.bfc-root` token vars (theme.js), so each piece flips
// light/dark and white-labels off `--pb-accent`. Display numbers/titles use
// Saira Condensed; body copy uses Hanken Grotesk. The look mirrors the design
// board in docs/design_handoff_betterfantasy_redesign.
import { createContext, useContext, useState, useEffect } from 'react'

export const DISP = "'Saira Condensed', sans-serif"
export const numSx = { fontFamily: DISP, fontVariantNumeric: 'tabular-nums' }

export const ROLE_ORDER = ['batter', 'allrounder', 'keeper', 'bowler']  // squad display order
export const ROLE_LABEL = { keeper: 'Wicketkeeper', batter: 'Batter', allrounder: 'All-rounder', bowler: 'Bowler' }
export const ROLE_GROUP = { keeper: 'Wicketkeeper', batter: 'Batters', allrounder: 'All-rounders', bowler: 'Bowlers' }
export const ROLE_SHORT = { keeper: 'WK', batter: 'BAT', allrounder: 'AR', bowler: 'BWL' }

export const money = (n) => `$${Number(n ?? 0).toFixed(1)}`
export const pts = (n) => {
  const v = Number(n ?? 0)
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}
export const cx = (...a) => a.filter(Boolean).join(' ')

export function initialsOf(name) {
  const parts = String(name || '').split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

// Accent tint helpers (the soft `color-mix` washes used all over the design).
export const tintBg = (pct, base = 'transparent') => `color-mix(in srgb, var(--pb-accent, #8C82F0) ${pct}%, ${base})`
export const tintBorder = (pct) => `1px solid ${tintBg(pct)}`
export const mix = (color, pct, base = 'transparent') => `color-mix(in srgb, ${color} ${pct}%, ${base})`

export const GREEN = '#16c784'
export const RED = '#ef5b5b'
export const AMBER = '#f5b542'
export const CYAN = '#22D3EE'
export const PINK = '#EC4899'

export const cardSx = {
  background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 14,
}

// Live breakpoint hook so inline-styled screens can switch to a desktop layout.
export function useIsDesktop(bp = 1024) {
  const q = `(min-width: ${bp}px)`
  const [is, setIs] = useState(() => typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(q).matches : false)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia(q)
    const on = () => setIs(mq.matches)
    on()
    mq.addEventListener?.('change', on)
    return () => mq.removeEventListener?.('change', on)
  }, [q])
  return is
}

// Light/dark switch button for the app chrome. Shows the sun when dark (tap for
// light) and the moon when light.
export function ThemeToggle({ theme, onToggle, size = 30 }) {
  return (
    <button onClick={onToggle} aria-label="Switch light or dark" title="Theme" style={{
      width: size, height: size, borderRadius: '50%', cursor: 'pointer', flex: 'none',
      background: 'var(--surface2)', border: '1px solid var(--hairline2)', color: 'var(--dim)', font: `400 14px 'Hanken Grotesk'`,
    }}>{theme === 'light' ? '☾' : '☀'}</button>
  )
}

// ── context (club crest + accent + token) ────────────────────────────────────
export const FantasyCtx = createContext({ club: null, crest: 'ACC', token: '' })
export const useFantasy = () => useContext(FantasyCtx)

export function crestText(club) {
  if (!club) return 'BFC'
  if (club.short_name) return club.short_name.slice(0, 4).toUpperCase()
  return (club.name || 'Club').split(/\s+/).map(w => w[0]).join('').slice(0, 3).toUpperCase()
}

// ── aurora glow (CSS only; honours reduced-motion via .bfc-aurora-blob) ───────
const DEFAULT_BLOBS = [
  { c: 'var(--pb-accent, #8C82F0)', a: 'bfcAuroraA', s: 18, pos: { width: '55%', height: '60%', left: '2%', top: '0' } },
  { c: CYAN, a: 'bfcAuroraB', s: 22, pos: { width: '50%', height: '55%', right: '2%', top: '6%' } },
  { c: PINK, a: 'bfcAuroraC', s: 20, pos: { width: '52%', height: '52%', left: '18%', top: '20%' } },
]

export function Aurora({ style, opacity, blur = 46, blobs = DEFAULT_BLOBS }) {
  return (
    <div aria-hidden style={{
      position: 'absolute', inset: '-20% -20% auto', height: '180%',
      pointerEvents: 'none', filter: `blur(${blur}px)`, opacity: opacity ?? 'var(--aurora)', ...style,
    }}>
      {blobs.map((b, i) => (
        <div key={i} className="bfc-aurora-blob" style={{
          position: 'absolute', borderRadius: '50%',
          background: `radial-gradient(circle, ${b.c}, transparent 66%)`,
          animation: `${b.a} ${b.s}s ease-in-out infinite alternate`, ...b.pos,
        }} />
      ))}
    </div>
  )
}

export function GradientRule({ className }) {
  return (
    <div className={className} style={{
      height: 3, borderRadius: 3, marginTop: 12,
      background: 'linear-gradient(90deg, var(--pb-accent, #8C82F0), #22D3EE 50%, #00E58E 78%, #EC4899)',
    }} />
  )
}

// ── crest + avatar ───────────────────────────────────────────────────────────
export function Crest({ size = 38, radius = 11, fontSize, text }) {
  const { crest } = useFantasy()
  return (
    <div style={{
      width: size, height: size, borderRadius: radius, flex: 'none',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--pb-accent, #8C82F0)', color: 'var(--ink)',
      font: `800 ${fontSize || Math.round(size * 0.34)}px ${DISP}`,
      boxShadow: 'inset 0 0 0 1px rgba(255,255,255,.18)',
    }}>{text || crest}</div>
  )
}

// Player avatar: real photo when we have one, club crest ("ACC") otherwise.
export function Avatar({ name, photoUrl, size = 38, accentRing = true, dim = false }) {
  const { crest } = useFantasy()
  const common = { width: size, height: size, borderRadius: '50%', flex: 'none', objectFit: 'cover' }
  if (photoUrl) return <img src={photoUrl} alt="" style={{ ...common, boxShadow: accentRing ? `inset 0 0 0 1px ${tintBg(32)}` : undefined }} />
  return (
    <div style={{
      ...common, display: 'flex', alignItems: 'center', justifyContent: 'center',
      font: `800 ${Math.round(size * 0.24)}px ${DISP}`, color: 'var(--faint)',
      background: 'var(--surface2)', boxShadow: dim ? undefined : 'inset 0 0 0 1px var(--hairline2)',
    }} title="No photo — club crest">{crest}</div>
  )
}

export function CapBadge({ vice }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      width: 16, height: 16, borderRadius: 5, font: `800 8.5px ${DISP}`,
      background: vice ? 'var(--hairline2)' : 'var(--pb-accent, #8C82F0)',
      color: vice ? 'var(--dim)' : 'var(--ink)',
    }}>{vice ? 'V' : 'C'}</span>
  )
}

// ── label + tiles ─────────────────────────────────────────────────────────────
export function Kicker({ children, color = 'var(--faint)', className }) {
  return <div className={className} style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color }}>{children}</div>
}

export function StatTile({ label, value, color = 'var(--text)' }) {
  return (
    <div style={{ ...cardSx, borderRadius: 12, padding: '9px 11px' }}>
      <div style={{ font: `600 8.5px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)' }}>{label}</div>
      <div style={{ font: `700 19px ${DISP}`, color, fontVariantNumeric: 'tabular-nums', marginTop: 2 }}>{value}</div>
    </div>
  )
}

// ── buttons + inputs ───────────────────────────────────────────────────────────
export function Btn({ children, onClick, variant = 'accent', full, disabled, type = 'button', style }) {
  const base = {
    borderRadius: 11, padding: '12px 16px', font: `700 13.5px 'Hanken Grotesk'`,
    textAlign: 'center', cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.5 : 1,
    border: 'none', width: full ? '100%' : undefined,
  }
  const variants = {
    accent: { background: 'var(--pb-accent, #8C82F0)', color: 'var(--ink)' },
    soft: { background: 'var(--surface2)', color: 'var(--text)' },
    ghost: { background: 'var(--surface)', color: 'var(--text)', border: '1px solid var(--hairline)' },
    danger: { background: mix(RED, 12, 'var(--surface)'), color: RED, border: `1px solid ${mix(RED, 30)}` },
  }
  return <button type={type} onClick={onClick} disabled={disabled} style={{ ...base, ...variants[variant], ...style }}>{children}</button>
}

export function Field({ value, onChange, placeholder, type = 'text', inputMode, style, ...rest }) {
  return (
    <input
      value={value} onChange={onChange} placeholder={placeholder} type={type} inputMode={inputMode}
      style={{
        width: '100%', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 11,
        padding: '13px 14px', font: `500 13.5px 'Hanken Grotesk'`, color: 'var(--text)', outline: 'none', ...style,
      }}
      {...rest}
    />
  )
}

// Segmented control (the New player / Sign in, Dark / Light / Auto toggles).
export function Segmented({ options, value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 6, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 12, padding: 4 }}>
      {options.map(([k, label]) => {
        const on = value === k
        return (
          <button key={k} onClick={() => onChange(k)} style={{
            flex: 1, textAlign: 'center', padding: 9, borderRadius: 9, border: 'none', cursor: 'pointer',
            font: `${on ? 700 : 600} 12.5px 'Hanken Grotesk'`,
            background: on ? 'var(--pb-accent, #8C82F0)' : 'transparent', color: on ? 'var(--ink)' : 'var(--dim)',
          }}>{label}</button>
        )
      })}
    </div>
  )
}

export function Toggle({ on, onClick }) {
  return (
    <button onClick={onClick} aria-pressed={on} style={{
      width: 42, height: 24, borderRadius: 12, border: 'none', cursor: 'pointer', flex: 'none', position: 'relative',
      background: on ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)',
    }}>
      <span style={{
        position: 'absolute', top: 2, left: on ? 20 : 2, width: 20, height: 20, borderRadius: '50%',
        background: on ? '#fff' : 'var(--faint)', transition: 'left .15s ease',
      }} />
    </button>
  )
}

// A movement arrow for ladders (▲ n / ▼ n / –).
export function MoveArrow({ delta, width = 18 }) {
  let color = 'var(--faintest)', txt = '–'
  if (delta > 0) { color = GREEN; txt = `▲${delta}` }
  else if (delta < 0) { color = RED; txt = `▼${Math.abs(delta)}` }
  return <span style={{ width, textAlign: 'center', font: `700 11px 'Hanken Grotesk'`, color }}>{txt}</span>
}
