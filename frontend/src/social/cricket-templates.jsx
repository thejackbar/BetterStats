// Cricket social media templates — ES module port of the Cricket Scorecards 2 design system.
// All templates render at exactly 1080×1080px using inline styles.
// Font stack: Anton, Bebas Neue, Archivo Black, Inter, JetBrains Mono (loaded in index.html)

import { useRef, useState, useLayoutEffect } from 'react'
import brandBlack from '../assets/bettercricket-black.svg'
import brandWhite from '../assets/bettercricket-white.svg'

// The BetterCricket credit mark used in every template's footer — the real
// brand logo (black on a light footer, white on a dark one), no wordmark text.
// Sits where each template already places its credit so it's vertically centred
// in that footer section.
function _isLight(hex) {
  const h = String(hex || '').replace('#', '')
  if (h.length < 6) return false
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16)
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150
}
export function CreditMark({ ink = '#ffffff', h = 46, style = {} }) {
  // `ink` is the footer's text colour, which already contrasts the background —
  // so the logo matches it: a light ink (dark post) → white logo, dark ink → black.
  return <img src={_isLight(ink) ? brandWhite : brandBlack} alt="BetterCricket" style={{ height: h, width: 'auto', display: 'block', opacity: 0.92, ...style }} />
}

// ─────────────────────────────────────────────────────────────────────────────
// AUTO-FIT TEXT
// Shrinks the font size until the text fits its container, so long names /
// headlines never clip or wrap unexpectedly. Measures after layout and on every
// content/size change. `max` is the design size, `min` the floor. By default it
// fits on a single line (nowrap); pass `lines` to allow up to N wrapped lines
// and fit by height instead. Works inside the modern-screenshot export because
// the measure runs synchronously via useLayoutEffect before the capture clones
// the DOM (the computed fontSize is inlined on the node).
// ─────────────────────────────────────────────────────────────────────────────
export function AutoFitText({ text, children, max, min = 8, lines = 1, pad = 0, style = {}, measureDeps = [], ...rest }) {
  const ref = useRef(null)
  const [size, setSize] = useState(max)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el || !el.parentElement) return
    let cancelled = false
    // Always measure from the design size down, so growing the box (or
    // shortening the text) lets the size recover.
    const fit = () => {
      const node = ref.current
      const parent = node && node.parentElement
      if (cancelled || !node || !parent) return
      // For multi-line (clamped) text, measure against a plain block. A
      // -webkit-box clamps its own scrollWidth to the box width, so a wide
      // unbreakable word ("SQUAD") never trips the width-overflow check and the
      // headline renders at full size, clipped on the edge. Flip to a block for
      // the measurement only; the render style restores the clamp.
      const prevDisplay = node.style.display
      const prevClamp = node.style.webkitLineClamp
      if (lines > 1) { node.style.display = 'block'; node.style.webkitLineClamp = 'unset' }
      let next = max
      node.style.fontSize = next + 'px'
      let guard = 0
      while (guard++ < 400 && next > min) {
        const overflowW = node.scrollWidth > parent.clientWidth + 0.5
        const overflowH = lines > 1 && node.scrollHeight > parent.clientHeight + 0.5
        if (!overflowW && !overflowH) break
        next -= 1
        node.style.fontSize = next + 'px'
      }
      if (lines > 1) { node.style.display = prevDisplay; node.style.webkitLineClamp = prevClamp }
      setSize(next)
    }
    fit()
    // Custom display fonts (Anton, Caveat, …) frequently load AFTER first
    // layout; their glyphs are wider than the fallback, so the first pass can
    // commit a size that then overflows once the real face swaps in. Re-fit once
    // the fonts are ready.
    if (typeof document !== 'undefined' && document.fonts && document.fonts.status !== 'loaded') {
      document.fonts.ready.then(fit)
    }
    return () => { cancelled = true }
  }, [text, max, min, lines, pad, ...measureDeps])

  return (
    <div
      ref={ref}
      style={{
        fontSize: size,
        whiteSpace: lines > 1 ? 'normal' : 'nowrap',
        display: lines > 1 ? '-webkit-box' : 'block',
        WebkitLineClamp: lines > 1 ? lines : undefined,
        WebkitBoxOrient: lines > 1 ? 'vertical' : undefined,
        overflow: 'hidden',
        // border-box + a touch of right padding gives slanted/cursive faces room
        // so the final glyph's overhang isn't sheared off by overflow:hidden.
        boxSizing: 'border-box',
        paddingRight: pad || undefined,
        ...style,
      }}
      {...rest}
    >
      {children != null ? children : text}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SHARED VISUAL PRIMITIVES
// ─────────────────────────────────────────────────────────────────────────────

export function GrainSVG({ opacity = 0.35, id = 'grain' }) {
  return (
    <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', mixBlendMode: 'overlay', opacity }}>
      <filter id={id}>
        <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" />
        <feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.55 0" />
      </filter>
      <rect width="100%" height="100%" filter={`url(#${id})`} />
    </svg>
  )
}

export function Halftone({ color = '#fff', size = 14, opacity = 0.12, angle = 0, style = {} }) {
  return (
    <div style={{
      position: 'absolute', inset: 0, pointerEvents: 'none', opacity,
      backgroundImage: `radial-gradient(${color} 1.2px, transparent 1.6px)`,
      backgroundSize: `${size}px ${size}px`,
      transform: `rotate(${angle}deg) scale(1.4)`,
      transformOrigin: 'center',
      ...style,
    }} />
  )
}

export function Stripes({ color = '#fff', angle = -45, gap = 14, opacity = 0.06, style = {} }) {
  return (
    <div style={{
      position: 'absolute', inset: 0, pointerEvents: 'none', opacity,
      backgroundImage: `repeating-linear-gradient(${angle}deg, ${color} 0 1px, transparent 1px ${gap}px)`,
      ...style,
    }} />
  )
}

export function ClubLogo({ monogram = 'NG', color = '#fff', bg = 'transparent', size = 120, shape = 'shield', src = null }) {
  if (src) {
    return <img src={src} alt={monogram + ' logo'} style={{ width: size, height: size, objectFit: 'contain', display: 'block' }} />
  }
  const stroke = Math.max(2, size * 0.04)
  const fontSize = size * 0.42
  if (shape === 'circle') {
    return (
      <div style={{
        width: size, height: size, borderRadius: '50%',
        background: bg, border: `${stroke}px solid ${color}`,
        display: 'grid', placeItems: 'center', color,
        fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize, letterSpacing: 1,
      }}>{monogram}</div>
    )
  }
  return (
    <svg width={size} height={size * 1.08} viewBox="0 0 100 108" style={{ display: 'block' }}>
      <path d="M5 8 L50 0 L95 8 L92 60 Q88 88 50 104 Q12 88 8 60 Z"
        fill={bg === 'transparent' ? 'none' : bg}
        stroke={color} strokeWidth="3" />
      <text x="50" y="62" textAnchor="middle"
        fontFamily="'Anton', sans-serif" fontSize="38" fill={color} letterSpacing="1">{monogram}</text>
    </svg>
  )
}

// Prominent club identity lockup — the club's own logo paired with its full
// name. Used across the post templates so a club's brand reads first (these
// posts double as recruitment ads, so the club — not the layout chrome — has
// to be the loudest thing on the card). `layout` is 'row' (logo beside name)
// or 'stack' (logo above name); `align` flips a row lockup to the right.
export function BrandLockup({
  team, palette, size = 120, layout = 'row', align = 'left',
  showName = true, showLogo = true, nameSize, nameColor, nameOpacity = 1, gap, style = {},
}) {
  const name = (team?.fullName || team?.name || '').toUpperCase()
  const col = nameColor || (palette && palette.ink) || '#fff'
  const ns = nameSize || Math.round(size * (layout === 'stack' ? 0.24 : 0.3))
  const stack = layout === 'stack'
  const g = gap != null ? gap : (stack ? Math.round(size * 0.1) : Math.round(size * 0.16))
  return (
    <div style={{
      display: 'flex', alignItems: 'center',
      flexDirection: stack ? 'column' : (align === 'right' ? 'row-reverse' : 'row'),
      gap: g, textAlign: stack ? 'center' : (align === 'right' ? 'right' : 'left'),
      ...style,
    }}>
      {showLogo && <ClubLogo src={team?.logo} monogram={team?.monogram} color={col} size={size} shape="shield" />}
      {showName && name && (
        <div style={{
          fontFamily: "var(--social-display-font, 'Anton', sans-serif)",
          fontSize: ns, letterSpacing: 1, lineHeight: 0.92,
          color: col, opacity: nameOpacity, maxWidth: stack ? size * 2.6 : size * 3.4,
        }}>{name}</div>
      )}
    </div>
  )
}

export function RoleChip({ kind, accent = '#ffc233', ink = '#0b1530' }) {
  if (!kind) return null
  const labels = { C: 'C', VC: 'VC', WK: 'WK' }
  const label = labels[kind]
  if (!label) return null
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      minWidth: 32, height: 24, padding: '0 8px',
      background: accent, color: ink,
      fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 16, fontWeight: 400,
      letterSpacing: 1, lineHeight: 1, borderRadius: 2,
      verticalAlign: 'middle',
    }}>{label}</span>
  )
}

export function PlayerSilhouette({ team, role, ink = '#fff', style = {} }) {
  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', display: 'grid', placeItems: 'center', ...style }}>
      <div style={{
        fontFamily: "var(--social-display-font, 'Anton', sans-serif)",
        fontSize: 'min(60%, 280px)',
        lineHeight: 0.85,
        color: ink,
        opacity: 0.18,
        letterSpacing: -2,
        userSelect: 'none',
      }}>{team.monogram}</div>
    </div>
  )
}

export function VsBlock({ accent = '#ffc233', ink = '#fff', size = 18 }) {
  return (
    <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: size, color: ink, letterSpacing: 2, opacity: 0.85 }}>VS</div>
  )
}

export function PlayerImage({ player, team, palette, fit = 'contain', size = 200, style = {} }) {
  if (player && player.headshot) {
    return (
      <img src={player.headshot} alt={(player.first || '') + ' ' + (player.last || '')}
        style={{ width: '100%', height: '100%', objectFit: fit, objectPosition: 'bottom', ...style }} />
    )
  }
  if (team && team.logo) {
    return (
      <div style={{ width: '100%', height: '100%', display: 'grid', placeItems: 'center', ...style }}>
        <img src={team.logo} alt={team.short || 'club'}
          style={{ width: '65%', height: '65%', objectFit: 'contain', opacity: 0.92 }} />
      </div>
    )
  }
  return (
    <div style={{
      width: '100%', height: '100%', display: 'grid', placeItems: 'center',
      fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: size * 0.5, color: palette && palette.accent || '#fff',
      opacity: 0.85, letterSpacing: -2, lineHeight: 1, ...style,
    }}>{team && team.monogram || '?'}</div>
  )
}

// Picks the player shown in the hero image slot. An explicit `featuredId`
// (the chosen player's id) wins; otherwise it falls back to the captain, then
// the first player in the order.
export function featuredOf(players, featuredId) {
  if (!players || !players.length) return null
  if (featuredId != null && featuredId !== '') {
    const chosen = players.find(p => p._id === featuredId)
    if (chosen) return chosen
  }
  return players.find(p => p.captain) || players[0]
}

// ─────────────────────────────────────────────────────────────────────────────
// ROLE STYLING (templates B)
// ─────────────────────────────────────────────────────────────────────────────
const ROLE_LABEL = { BAT: 'BAT', BOWL: 'BOWL', AR: 'AR', WK: 'WK' }
// Normalise any role value (a code like 'AR'/'WK' OR free text like
// 'Bowler'/'Wicketkeeper'/'All-Rounder') to a short, consistent badge label.
function roleShort(role) {
  if (!role) return ''
  const r = String(role).toUpperCase()
  if (r.startsWith('WK') || r.includes('KEEP')) return 'WK'
  if (r === 'AR' || r.startsWith('ALL') || r.includes('ROUND')) return 'ALL'
  if (r.startsWith('BOWL')) return 'BOWL'
  if (r.startsWith('BAT')) return 'BAT'
  return r.slice(0, 4)
}
const ROLE_COLOR_BG = (palette, role) => {
  switch (role) {
    case 'BAT': return palette.accent
    case 'BOWL': return palette.ink + '1a'
    case 'AR': return palette.secondary
    case 'WK': return palette.ink + '33'
    default: return palette.ink + '1a'
  }
}
const ROLE_COLOR_INK = (palette, role) => {
  switch (role) {
    case 'BAT': return palette.primary
    case 'BOWL': return palette.ink
    case 'AR': return palette.accent
    case 'WK': return palette.ink
    default: return palette.ink
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// BUILT-IN PALETTES
// ─────────────────────────────────────────────────────────────────────────────
export const PALETTES = {
  midnight: { name: 'Midnight', primary: '#0b1530', secondary: '#1a2647', accent: '#ffc233', ink: '#ffffff' },
  crimson:  { name: 'Crimson',  primary: '#2a0a0e', secondary: '#5a0f1a', accent: '#ff3344', ink: '#fff4e6' },
  forest:   { name: 'Forest',   primary: '#0c2418', secondary: '#163828', accent: '#c4ff4d', ink: '#f4fbe8' },
  cobalt:   { name: 'Cobalt',   primary: '#0b1f4a', secondary: '#17336b', accent: '#00c2ff', ink: '#ffffff' },
  rust:     { name: 'Rust',     primary: '#1e0f08', secondary: '#3a1a0a', accent: '#ff7a1a', ink: '#fff1e3' },
  graphite: { name: 'Graphite', primary: '#101113', secondary: '#1d1f23', accent: '#e8ff00', ink: '#ffffff' },
}

// The club's own accent colour, resolved the same way the site theme is:
// theme_config.accent (what the branding/settings pages actually edit),
// then the accent_color column it's mirrored into, then the legacy
// primary_color, then brand green. Reading primary_color first (the old
// behaviour) left most clubs stuck on the default green, since nothing
// edits that column any more.
export function orgAccent(org) {
  return org?.theme_config?.accent || org?.accent_color || org?.primary_color || '#16c784'
}

export function orgToPalette(org) {
  // Neutral dark background pair with the club's primary colour as the
  // accent only — club colours rarely make a good post background, and the
  // light theme swaps in its own paper/ink via applyTheme anyway. Anyone
  // who wants a club-coloured background can build it as a Custom palette.
  return { name: 'Club', primary: '#101113', secondary: '#1d1f23', accent: orgAccent(org), ink: '#ffffff' }
}

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE 1 — Hero cutout + bold name list
// ─────────────────────────────────────────────────────────────────────────────
export function T1_HeroList({ team, opponent, match, players, palette, heroImage, headline, featuredId }) {
  const P = players.slice(0, 13)
  // Size the name rows down as the squad grows so a full 13 always fits the
  // available space (sized for the worst case: a tall headline + a wrapped vs
  // row). Rows are then distributed to fill the column for larger squads.
  const rowMax = P.length >= 13 ? 28 : P.length >= 11 ? 32 : P.length >= 9 ? 36 : 42
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: `linear-gradient(135deg, ${palette.primary} 0%, ${palette.secondary} 100%)`,
      color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <div style={{
        position: 'absolute', left: 0, top: 0, bottom: 0, width: 56,
        background: palette.secondary,
        borderRight: `1px solid ${palette.ink}1a`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <div style={{
          transform: 'rotate(-90deg)',
          whiteSpace: 'nowrap',
          fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 27, letterSpacing: 8,
          color: palette.ink, opacity: 0.92,
        }}>{(team.fullName || team.name).toUpperCase()}</div>
      </div>
      <div style={{
        position: 'absolute', left: 70, top: 80,
        fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 160, lineHeight: 0.88,
        color: palette.ink, opacity: 0.06, letterSpacing: -2, userSelect: 'none',
        maxWidth: 540,
      }}>{(team.fullName || team.name + ' CRICKET CLUB').toUpperCase()}</div>
      <Halftone color={palette.ink} opacity={0.08} size={12} />
      <Stripes color={palette.ink} opacity={0.04} gap={20} angle={-30} />
      <div style={{
        position: 'absolute', left: 64, top: 210, width: 480, height: 845,
        display: 'grid', placeItems: 'end center', overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', left: -60, bottom: -120, width: 620, height: 620,
          background: `radial-gradient(circle at 45% 45%, ${palette.accent}33 0%, transparent 60%)`,
        }} />
        {(() => {
          const featured = featuredOf(players, featuredId)
          const src = heroImage || (featured && featured.headshot ? featured.headshot : null) || team.logo
          return (
            <img src={src} alt={featured ? (featured.first + ' ' + featured.last) : team.short}
              style={{
                position: 'absolute', inset: 0,
                width: '100%', height: '100%',
                objectFit: 'cover', objectPosition: 'center top',
                filter: `drop-shadow(0 30px 60px ${palette.primary}cc)`,
              }} />
          )
        })()}
      </div>
      <div style={{
        position: 'absolute', left: 80, top: 40, zIndex: 5,
        fontFamily: "var(--social-display-font, 'Anton', sans-serif)", letterSpacing: 3,
        color: palette.ink, lineHeight: 1.1, maxWidth: 240,
      }}>
        <div style={{ background: palette.accent, color: palette.primary, padding: '4px 10px', display: 'inline-block', fontSize: 16 }}>MATCH DAY</div>
        <div style={{ marginTop: 10, fontSize: 16 }}>{match.venue.toUpperCase()}</div>
        <div style={{ opacity: 0.65, marginTop: 2, fontSize: 14, fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1.5 }}>{match.date} · {match.time}</div>
      </div>
      <div style={{ position: 'absolute', right: 40, top: 56, bottom: 100, width: 480, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'flex-start' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{
              fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, letterSpacing: 2,
              color: palette.ink, opacity: 0.85, lineHeight: 1,
            }}>{match.competition}</div>
            <div style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
              color: palette.accent, marginTop: 6,
            }}>{match.season}</div>
          </div>
        </div>
        <div style={{ maxHeight: 300, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', marginTop: 20, overflow: 'hidden' }}>
          <AutoFitText
            text={(headline || 'SQUAD').toUpperCase()} max={180} min={48} lines={2} pad={14}
            style={{
              fontFamily: "var(--social-display-font, 'Anton', sans-serif)", lineHeight: 0.85,
              letterSpacing: -2, color: palette.ink, textAlign: 'right', width: '100%',
            }} />
        </div>
        <div style={{ width: 60, height: 4, background: palette.accent, marginTop: 10, marginBottom: 24 }} />
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
          gap: 16, marginBottom: 26, flexWrap: 'wrap',
        }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 34, letterSpacing: 1.5, lineHeight: 1 }}>{team.name}</div>
          </div>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.accent} size={80} shape="shield" />
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, opacity: 0.7 }}>V</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={52} shape="shield" />
          <div style={{ textAlign: 'left' }}>
            <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, letterSpacing: 1.5, lineHeight: 1 }}>{opponent.name}</div>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1, textAlign: 'right', flex: 1, minHeight: 0, overflow: 'hidden', justifyContent: P.length >= 9 ? 'space-between' : 'flex-start' }}>
          {P.map((p, i) => {
            const chip = p.captain ? 'C' : p.viceCaptain ? 'VC' : p.keeper ? 'WK' : null
            return (
              <div key={i} style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 10, width: '100%' }}>
                <div style={{ flex: 1, minWidth: 0, display: 'flex', justifyContent: 'flex-end' }}>
                  <AutoFitText max={rowMax} min={16} lines={1} pad={8} measureDeps={[chip ? 1 : 0]}
                    style={{
                      fontFamily: "var(--social-display-font, 'Anton', sans-serif)", lineHeight: 1.05,
                      letterSpacing: 0.5, color: palette.ink,
                    }}>
                    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: '0.25em', whiteSpace: 'nowrap' }}>
                      <span style={{ fontWeight: 300, opacity: 0.72, fontSize: '0.75em' }}>{p.first.toUpperCase()}</span>
                      <span>{p.last}</span>
                    </span>
                  </AutoFitText>
                </div>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
            )
          })}
        </div>
      </div>
      <div style={{
        position: 'absolute', right: 40, bottom: 36,
        display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6,
      }}>
        <CreditMark ink={palette.ink} h={44} />
      </div>
      <GrainSVG opacity={0.35} id="g1" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE 2 — Trading card grid (4×3)
// ─────────────────────────────────────────────────────────────────────────────
export function T2_CardGrid({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 12)
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.05} size={10} />
      <Stripes color={palette.accent} opacity={0.04} gap={30} angle={45} />
      <div style={{
        position: 'absolute', left: -50, bottom: -60,
        fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 320, lineHeight: 0.8,
        color: palette.ink, opacity: 0.04, letterSpacing: -6,
        transform: 'rotate(-8deg)', userSelect: 'none', whiteSpace: 'nowrap',
      }}>LINEUP</div>
      <svg style={{ position: 'absolute', left: -180, top: -180, width: 560, height: 560, opacity: 0.08 }}>
        <circle cx="280" cy="280" r="260" fill="none" stroke={palette.ink} strokeWidth="2" />
        <circle cx="280" cy="280" r="200" fill="none" stroke={palette.ink} strokeWidth="2" />
        <circle cx="280" cy="280" r="140" fill="none" stroke={palette.ink} strokeWidth="2" />
      </svg>
      <svg style={{ position: 'absolute', right: -160, bottom: -160, width: 480, height: 480, opacity: 0.06 }}>
        <circle cx="240" cy="240" r="220" fill="none" stroke={palette.accent} strokeWidth="3" />
        <circle cx="240" cy="240" r="160" fill="none" stroke={palette.accent} strokeWidth="3" />
      </svg>
      <div style={{ position: 'absolute', left: -40, bottom: 80, width: 240, height: 4, background: palette.accent, transform: 'rotate(-30deg)', opacity: 0.7 }} />
      <div style={{
        position: 'absolute', top: -20, right: -40, width: 380, height: 180,
        background: palette.accent, opacity: 0.9,
        clipPath: 'polygon(0% 30%, 100% 0%, 100% 70%, 18% 100%)',
      }} />
      <svg style={{ position: 'absolute', left: 40, top: 16, width: 220, height: 60, opacity: 0.55 }}>
        {Array.from({ length: 36 }).map((_, i) => (
          <circle key={i} cx={(i % 12) * 18 + 6} cy={Math.floor(i / 12) * 18 + 6} r={2.4} fill={palette.accent} />
        ))}
      </svg>
      <div style={{ position: 'absolute', left: 260, top: 36, width: 220, height: 3, background: palette.accent, opacity: 0.7 }} />
      <div style={{ position: 'absolute', left: 482, top: 30, width: 14, height: 14, background: palette.accent, borderRadius: '50%' }} />
      <div style={{ position: 'absolute', left: 40, top: 90, display: 'flex', gap: 6, alignItems: 'center' }}>
        {[20, 32, 14, 28, 22, 36, 18, 26].map((h, i) => (
          <div key={i} style={{ width: 5, height: h, background: palette.accent, opacity: 0.6 }} />
        ))}
      </div>
      <div style={{ position: 'relative', padding: '44px 56px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', zIndex: 2 }}>
        <div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 96, lineHeight: 0.85, color: palette.ink, letterSpacing: -1 }}>LINEUP</div>
          <div style={{ width: 84, height: 4, background: palette.accent, margin: '10px 0 14px' }} />
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, letterSpacing: 2, color: palette.ink, opacity: 0.95 }}>
            {team.name} <span style={{ opacity: 0.5 }}>×</span> {opponent.name}
          </div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 16, letterSpacing: 1.8, color: palette.accent, marginTop: 10, fontWeight: 500 }}>
            {match.round} · {match.date} · {match.time}
          </div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 1.5, color: palette.ink, opacity: 0.7, marginTop: 4 }}>
            {match.venue.toUpperCase()}
          </div>
        </div>
      </div>
      <div style={{ position: 'absolute', top: 24, right: 32, zIndex: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', width: 260 }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={200} shape="shield" />
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 26, letterSpacing: 1, color: palette.ink, lineHeight: 0.95, textAlign: 'center', marginTop: 8 }}>{(team.fullName || team.name).toUpperCase()}</div>
      </div>
      <div style={{
        position: 'absolute', left: 56, right: 56, top: 380, bottom: 100,
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gridTemplateRows: 'repeat(3, 1fr)',
        gap: 14,
      }}>
        {P.map((p, i) => {
          const chip = p.captain ? 'C' : p.viceCaptain ? 'VC' : p.keeper ? 'WK' : null
          return (
            <div key={i} style={{
              position: 'relative', overflow: 'hidden',
              background: `linear-gradient(180deg, ${palette.secondary} 0%, ${palette.primary} 100%)`,
              border: `2px solid ${palette.accent}`,
              display: 'flex', flexDirection: 'column',
            }}>
              <div style={{ height: '75%', display: 'grid', placeItems: 'center', position: 'relative', overflow: 'hidden' }}>
                <Halftone color={palette.ink} opacity={0.08} size={6} />
                {p.headshot ? (
                  <img src={p.headshot} alt={p.first + ' ' + p.last}
                    style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', objectPosition: 'center top' }} />
                ) : team.logo ? (
                  <img src={team.logo} alt={team.short}
                    style={{ width: '68%', height: '68%', objectFit: 'contain', opacity: 0.92 }} />
                ) : (
                  <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 96, color: palette.accent, opacity: 0.85, letterSpacing: -2, lineHeight: 1 }}>{team.monogram}</div>
                )}
                {chip && <div style={{ position: 'absolute', top: 8, right: 8 }}><RoleChip kind={chip} accent={palette.accent} ink={palette.primary} /></div>}
                <div style={{ position: 'absolute', top: 8, left: 8, fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: palette.ink, opacity: 0.4, letterSpacing: 1.5 }}>#{String(i + 1).padStart(2, '0')}</div>
              </div>
              <div style={{
                height: '25%', background: palette.accent, color: palette.primary,
                display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 10px',
              }}>
                <AutoFitText text={p.last} max={26} min={11} lines={1}
                  style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", letterSpacing: 1, lineHeight: 1, maxWidth: '100%', textAlign: 'center' }} />
              </div>
            </div>
          )
        })}
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, bottom: 32, display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
        <CreditMark ink={palette.ink} h={44} />
      </div>
      <GrainSVG opacity={0.4} id="g2" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE 3 — Side image + numbered XI
// ─────────────────────────────────────────────────────────────────────────────
export function T3_SideNumbered({ team, opponent, match, players, palette, heroImage, headline, featuredId }) {
  const P = players.slice(0, 11)
  // The vertical spine label echoes the post headline (defaults to STARTING XI).
  // Scale it down for longer headlines so it never runs off the top edge.
  const spine = (headline || 'STARTING XI').toUpperCase()
  const spineSize = Math.max(34, Math.min(80, Math.floor(1000 / Math.max(spine.length, 1))))
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <svg width="1080" height="1080" style={{ position: 'absolute', inset: 0 }}>
        <defs>
          <linearGradient id="bgwv" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={palette.primary} />
            <stop offset="1" stopColor={palette.secondary} />
          </linearGradient>
        </defs>
        <rect width="1080" height="1080" fill="url(#bgwv)" />
        <path d="M 900 0 C 1050 200 950 400 1080 600 L 1080 0 Z" fill={palette.ink} opacity="0.04" />
        <path d="M 1000 1080 C 850 900 1100 700 980 500 L 1080 500 L 1080 1080 Z" fill={palette.accent} opacity="0.06" />
      </svg>
      <div style={{
        position: 'absolute', left: 0, top: 0, width: 380, height: 1080,
        background: `linear-gradient(180deg, ${palette.secondary} 0%, ${palette.primary} 100%)`,
        overflow: 'hidden',
      }}>
        <Halftone color={palette.ink} opacity={0.1} size={8} />
        <div style={{ position: 'absolute', left: -120, bottom: -120, width: 600, height: 600, background: `radial-gradient(circle at center, ${palette.accent}33 0%, transparent 60%)` }} />
        {(() => {
          const featured = featuredOf(players, featuredId)
          const hasHead = !!(heroImage || (featured && featured.headshot))
          const src = heroImage || (featured && featured.headshot ? featured.headshot : null) || team.logo
          return (
            <img src={src} alt={featured ? (featured.first + ' ' + featured.last) : team.short}
              style={{
                position: 'absolute', inset: 0,
                width: '100%', height: '100%',
                objectFit: hasHead ? 'cover' : 'contain',
                objectPosition: hasHead ? 'top center' : 'center',
                padding: hasHead ? 0 : 40,
              }} />
          )
        })()}
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 240, background: `linear-gradient(180deg, transparent 0%, ${palette.primary}ee 100%)` }} />
        {(() => {
          const featured = featuredOf(players, featuredId)
          if (!featured) return null
          const chip = featured.captain ? 'C' : featured.viceCaptain ? 'VC' : featured.keeper ? 'WK' : null
          return (
            <div style={{ position: 'absolute', left: 16, right: 16, bottom: 22, zIndex: 2 }}>
              <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 20, letterSpacing: 1, color: palette.ink, opacity: 0.78, lineHeight: 1 }}>{featured.first.toUpperCase()}</div>
              <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 44, letterSpacing: 0.5, color: palette.ink, lineHeight: 1, marginTop: 2, display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span>{featured.last}</span>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
            </div>
          )
        })()}
      </div>
      <div style={{
        position: 'absolute', left: 360, top: 540,
        transform: 'rotate(-90deg)', transformOrigin: 'left top',
        fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: spineSize, letterSpacing: 4,
        color: 'transparent', WebkitTextStroke: `2px ${palette.accent}`,
        whiteSpace: 'nowrap', lineHeight: 0.8,
      }}>{spine}</div>
      <div style={{ position: 'absolute', left: 460, top: 50, right: 40, bottom: 40, display: 'flex', flexDirection: 'column' }}>
        <div style={{ textAlign: 'center', fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, letterSpacing: 2, color: palette.ink, lineHeight: 1, marginBottom: 14 }}>{(team.fullName || team.name).toUpperCase()}</div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 26, marginBottom: 24 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={132} shape="circle" />
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 28, letterSpacing: 3, color: palette.accent }}>VS</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={104} shape="circle" />
        </div>
        <div style={{ textAlign: 'center', fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.8, color: palette.ink, opacity: 0.7, marginBottom: 4 }}>
          {match.competition} · {match.round} · {match.date}
        </div>
        <div style={{ textAlign: 'center', fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 16, letterSpacing: 2, color: palette.accent, marginBottom: 22, lineHeight: 1 }}>
          {match.venue.toUpperCase()}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
          {P.map((p, i) => {
            const chip = p.captain ? 'C' : p.viceCaptain ? 'VC' : p.keeper ? 'WK' : null
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '7px 0', borderBottom: `1px solid ${palette.ink}1c` }}>
                <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 42, color: palette.accent, lineHeight: 1, width: 50, textAlign: 'right', flexShrink: 0 }}>{i + 1}</div>
                <div style={{ flex: 1, minWidth: 0, display: 'flex', justifyContent: 'flex-start' }}>
                  <AutoFitText max={38} min={16} lines={1} pad={8}
                    style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", letterSpacing: 0.5, color: palette.ink, lineHeight: 1 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: '0.26em', whiteSpace: 'nowrap' }}>
                      <span style={{ opacity: 0.65, fontWeight: 300, fontSize: '0.74em' }}>{p.first.toUpperCase()}</span>
                      <span>{p.last}</span>
                    </span>
                  </AutoFitText>
                </div>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
            )
          })}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', marginTop: 12, paddingTop: 10, borderTop: `2px solid ${palette.accent}` }}>
          <CreditMark ink={palette.ink} h={44} />
        </div>
      </div>
      <GrainSVG opacity={0.3} id="g3" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE 4 — Batting order with role-coded rows
// ─────────────────────────────────────────────────────────────────────────────
export function T4_BattingOrder({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 13)
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Stripes color={palette.ink} opacity={0.04} gap={40} angle={0} />
      <Halftone color={palette.ink} opacity={0.04} size={11} />
      <div style={{ position: 'relative', padding: '32px 56px 18px', borderBottom: `3px solid ${palette.accent}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 2, color: palette.accent, marginBottom: 4 }}>// PROBABLE XI</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 68, lineHeight: 0.85, color: palette.ink, letterSpacing: -1 }}>BATTING ORDER</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={116} shape="shield" />
      </div>
      <div style={{ padding: '16px 56px', background: palette.secondary, borderBottom: `1px solid ${palette.ink}22`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={58} shape="shield" />
            <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 28, letterSpacing: 1, color: palette.accent }}>v</div>
            <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={44} shape="shield" />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1, fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5, color: palette.ink, opacity: 0.78 }}>
            <span>{match.competition} · {match.round}</span>
            <span style={{ opacity: 0.7 }}>{match.venue.toUpperCase()}</span>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 28, letterSpacing: 1, lineHeight: 1, color: palette.accent }}>{match.date}</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5, color: palette.ink, opacity: 0.7, marginTop: 4 }}>{match.time}</div>
        </div>
      </div>
      <div style={{ padding: '16px 56px 0', display: 'flex', flexDirection: 'column', gap: 4 }}>
        {P.map((p, i) => {
          const chip = p.captain ? 'C' : p.viceCaptain ? 'VC' : p.keeper ? 'WK' : null
          const isRole = p.role || 'BAT'
          return (
            <div key={i} style={{
              display: 'grid', gridTemplateColumns: '60px 1fr 76px', alignItems: 'center', gap: 14,
              padding: '8px 16px',
              background: i % 2 === 0 ? `${palette.ink}08` : 'transparent',
              borderLeft: `3px solid ${i === 10 ? palette.accent : 'transparent'}`,
            }}>
              <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 40, color: palette.accent, lineHeight: 1, textAlign: 'center' }}>{i + 1}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                <div style={{ flex: 1, minWidth: 0, display: 'flex', justifyContent: 'flex-start' }}>
                  <AutoFitText max={30} min={14} lines={1} measureDeps={[chip ? 1 : 0]}
                    style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", letterSpacing: 0.5, color: palette.ink, lineHeight: 1 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: '0.28em', whiteSpace: 'nowrap' }}>
                      <span style={{ opacity: 0.62, fontWeight: 300, fontSize: '0.73em' }}>{p.first.toUpperCase()}</span>
                      <span>{p.last}</span>
                    </span>
                  </AutoFitText>
                </div>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
              <div style={{ width: 64, justifySelf: 'end', textAlign: 'center', padding: '5px 0', background: 'transparent', border: `1.5px solid ${palette.ink}55`, color: palette.ink, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 14, letterSpacing: 1.5, lineHeight: 1, borderRadius: 2 }}>
                {roleShort(isRole)}
              </div>
            </div>
          )
        })}
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, bottom: 22, display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 12, borderTop: `1px solid ${palette.ink}22` }}>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 16, letterSpacing: 1.5, color: palette.ink, opacity: 0.9 }}>{(team.fullName || team.name).toUpperCase()} · {match.season}</div>
        <CreditMark ink={palette.ink} h={44} />
      </div>
      <GrainSVG opacity={0.25} id="g4" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE 5 — Brutalist typographic
// ─────────────────────────────────────────────────────────────────────────────
export function T5_Brutalist({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 11)
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Stripes color={palette.ink} opacity={0.06} gap={6} angle={0} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: 320, textAlign: 'center', fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 520, lineHeight: 0.8, color: palette.ink, opacity: 0.05, letterSpacing: -10, userSelect: 'none' }}>XI</div>
      <Halftone color={palette.ink} opacity={0.08} size={14} angle={-20} />
      <div style={{ position: 'absolute', left: -100, top: 360, width: 1300, height: 100, background: palette.accent, opacity: 0.08, transform: 'rotate(-3deg)' }} />
      <div style={{ position: 'absolute', left: -120, top: 700, width: 1300, height: 60, background: palette.accent, opacity: 0.1, transform: 'rotate(2deg)' }} />
      <svg style={{ position: 'absolute', right: -180, top: 220, width: 520, height: 520, opacity: 0.08 }}>
        <circle cx="260" cy="260" r="240" fill="none" stroke={palette.accent} strokeWidth="3" />
        <circle cx="260" cy="260" r="180" fill="none" stroke={palette.accent} strokeWidth="3" />
      </svg>
      <div style={{ background: palette.accent, color: palette.primary, padding: '24px 44px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', position: 'relative', zIndex: 2 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20, minWidth: 0 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.primary} size={96} shape="shield" />
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 52, letterSpacing: 2, lineHeight: 1 }}>{team.name} XI</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, letterSpacing: 1.5, lineHeight: 1 }}>VS {opponent.name}</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2, marginTop: 6 }}>{match.round} · {match.date}</div>
        </div>
      </div>
      <div style={{ padding: '32px 44px 0', display: 'flex', flexDirection: 'column', gap: 0 }}>
        {P.map((p, i) => {
          const chip = p.captain ? 'C' : p.viceCaptain ? 'VC' : p.keeper ? 'WK' : null
          return (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '56px 1fr 70px 60px', alignItems: 'center', gap: 14, borderBottom: `1px solid ${palette.ink}1a`, padding: '4px 0' }}>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 1.5, color: palette.accent, opacity: 0.9 }}>{String(i + 1).padStart(2, '0')}</div>
              <div style={{ minWidth: 0, display: 'flex', justifyContent: 'flex-start' }}>
                <AutoFitText max={64} min={22} lines={1}
                  style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", color: palette.ink, letterSpacing: -1, lineHeight: 0.95 }}>
                  <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: '0.2em', whiteSpace: 'nowrap' }}>
                    <span style={{ opacity: 0.5, letterSpacing: 0.5, fontSize: '0.47em' }}>{p.first.toUpperCase()}</span>
                    <span>{p.last}</span>
                  </span>
                </AutoFitText>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5, color: palette.ink, opacity: 0.5, textAlign: 'right', whiteSpace: 'nowrap' }}>{roleShort(p.role)}</div>
            </div>
          )
        })}
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, background: palette.secondary, padding: '22px 44px', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', alignItems: 'center', borderTop: `3px solid ${palette.accent}`, zIndex: 2 }}>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, letterSpacing: 2, color: palette.ink, lineHeight: 1, textAlign: 'left' }}>STARTING XI</div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, letterSpacing: 2, color: palette.accent, lineHeight: 1 }}>{match.venue.toUpperCase()}</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2, color: palette.ink, opacity: 0.85, marginTop: 6 }}>{match.competition} · {match.time}</div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <CreditMark ink={palette.ink} h={44} />
        </div>
      </div>
      <GrainSVG opacity={0.32} id="g5" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE 6 — Diagonal poster
// ─────────────────────────────────────────────────────────────────────────────
export function T6_Diagonal({ team, opponent, match, players, palette, heroImage, featuredId }) {
  const P = players.slice(0, 11)
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.07} size={10} />
      <div style={{
        position: 'absolute', left: -200, width: 1500, height: 220,
        background: palette.accent, transform: 'rotate(-5deg)', transformOrigin: 'top left', top: 28, padding: '60px 0px 0px',
      }}>
        <div style={{ padding: '30px 240px 0', color: palette.primary, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 100, lineHeight: 0.9, letterSpacing: -1, transform: 'rotate(0deg)', display: 'flex', alignItems: 'center', gap: 28 }}>
          1ST XI
          <span style={{ fontSize: 22, letterSpacing: 3, opacity: 0.85 }}>· {match.date.toUpperCase()} ·</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <ClubLogo src={team.logo} monogram={team.monogram} color={palette.primary} size={92} shape="shield" />
            <span style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 56, letterSpacing: 1, lineHeight: 1 }}>v</span>
            <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.primary} size={70} shape="shield" />
          </span>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 56, top: 230, right: 56, height: 370, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 24 }}>
        <div style={{ flexShrink: 0, maxWidth: 320, paddingBottom: 24 }}>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 2, color: palette.accent, marginBottom: 14 }}>// 1ST XI</div>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={272} shape="shield" />
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 34, letterSpacing: 1, color: palette.ink, opacity: 1, marginTop: 14 }}>{(team.fullName || team.name).toUpperCase()}</div>
        </div>
        <div style={{ flex: 1, height: 370, display: 'grid', placeItems: 'end center', position: 'relative', overflow: 'hidden' }}>
          {(() => {
            const featured = featuredOf(players, featuredId)
            const hasHead = !!(heroImage || (featured && featured.headshot))
            const src = heroImage || (featured && featured.headshot ? featured.headshot : null) || team.logo
            return (
              <img src={src} alt={featured?.last || team.short}
                style={{
                  maxHeight: '100%', maxWidth: '100%', width: 'auto', height: 'auto',
                  objectFit: 'contain', objectPosition: 'bottom',
                  filter: `drop-shadow(0 20px 40px ${palette.primary}cc)`,
                }} />
            )
          })()}
        </div>
      </div>
      <div style={{ position: 'absolute', left: 56, right: 56, top: 620, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {P.map((p, i) => {
          const chip = p.captain ? 'C' : p.viceCaptain ? 'VC' : p.keeper ? 'WK' : null
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 0', borderBottom: `1px solid ${palette.ink}1a` }}>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5, color: palette.accent, width: 26 }}>{String(i + 1).padStart(2, '0')}</div>
              <div style={{ flex: 1, minWidth: 0, display: 'flex', justifyContent: 'flex-start' }}>
                <AutoFitText max={26} min={13} lines={1}
                  style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", letterSpacing: 0.5, color: palette.ink, lineHeight: 1.1 }}>
                  <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: '0.28em', whiteSpace: 'nowrap' }}>
                    <span style={{ opacity: 0.55, fontWeight: 300 }}>{p.first.toUpperCase()}</span>
                    <span>{p.last}</span>
                  </span>
                </AutoFitText>
              </div>
              {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
            </div>
          )
        })}
      </div>
      <div style={{ position: 'absolute', left: -200, bottom: -30, width: 1500, height: 150, background: palette.secondary, transform: 'rotate(-3deg)', transformOrigin: 'bottom left', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', alignItems: 'center', padding: '0 290px' }}>
        <div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5, color: palette.accent, opacity: 0.85 }}>VENUE</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, letterSpacing: 1.5, color: palette.ink, marginTop: 2 }}>{match.venue.toUpperCase()}</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5, color: palette.accent, opacity: 0.85 }}>{match.competition} · {match.round}</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 24, letterSpacing: 1.5, color: palette.ink, marginTop: 2 }}>{match.date.toUpperCase()} · {match.time}</div>
        </div>
        <CreditMark ink={palette.ink} h={44} />
      </div>
      <GrainSVG opacity={0.35} id="g6" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE 7 — Milestone spotlight
// ─────────────────────────────────────────────────────────────────────────────
export function T7_CaptainSpotlight({ team, opponent, match, players, palette, milestone, heroImage }) {
  const player = milestone?.player || featuredOf(players)
  const value = milestone?.value || '1ST'
  const unit = milestone?.unit || 'XI'
  const reason = milestone?.reason || 'NAMED IN THE STARTING XI'
  const detail = milestone?.detail || `${player?.roleLong || ''}`
  const rest = players.slice(0, 13).filter(p => p !== player)
  const hasHead = !!(player && player.headshot)
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: `linear-gradient(135deg, ${palette.primary} 0%, ${palette.secondary} 100%)`,
      color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.06} size={11} />
      <Stripes color={palette.accent} opacity={0.04} gap={26} angle={-22} />
      <div style={{ position: 'absolute', right: -40, top: -50, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 720, lineHeight: 0.8, color: palette.accent, opacity: 0.08, letterSpacing: -16, userSelect: 'none' }}>{value}</div>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '28px 40px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 4 }}>
        <div><div style={{ display: 'inline-block', padding: '5px 12px', background: palette.accent, color: palette.primary, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 16, letterSpacing: 3 }}>★ MILESTONE</div></div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={82} shape="shield" />
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 18, opacity: 0.7 }}>VS</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={60} shape="shield" />
        </div>
      </div>
      <div style={{ position: 'absolute', right: 0, top: 60, width: 540, height: 660, display: 'grid', placeItems: 'end center', overflow: 'hidden' }}>
        {(heroImage || hasHead) ? (
          <img src={heroImage || player.headshot} alt={player.last} style={{ height: 720, width: 'auto', objectFit: 'contain', objectPosition: 'bottom', filter: `drop-shadow(0 40px 80px ${palette.primary}ee)` }} />
        ) : (
          <img src={team.logo} alt={team.short} style={{ width: 380, height: 380, objectFit: 'contain', marginBottom: 40 }} />
        )}
      </div>
      <div style={{ position: 'absolute', left: 40, top: 96, width: 540, zIndex: 3 }}>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 3, color: palette.accent, marginBottom: 10 }}>// {reason}</div>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 320, lineHeight: 0.82, color: palette.ink, letterSpacing: -8 }}>{value}</div>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 80, letterSpacing: 2, color: palette.accent, lineHeight: 1, marginTop: -8 }}>{unit}</div>
        <div style={{ marginTop: 22, paddingTop: 16, borderTop: `2px solid ${palette.accent}` }}>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 32, letterSpacing: 1, color: palette.ink, opacity: 0.78, lineHeight: 1 }}>{(player?.first || '').toUpperCase()}</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 76, letterSpacing: -1, color: palette.ink, lineHeight: 0.9, marginTop: 2 }}>{player?.last || ''}</div>
          {detail && <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.2, color: palette.ink, opacity: 0.7, marginTop: 10, lineHeight: 1.4 }}>{detail}</div>}
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 270, background: palette.primary, borderTop: `3px solid ${palette.accent}`, padding: '18px 40px', zIndex: 3 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2, color: palette.accent }}>// JOINED BY THE XI</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5, color: palette.ink, opacity: 0.6 }}>{match.venue.toUpperCase()} · {match.date} · {match.time}</div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 4, columnGap: 24 }}>
          {rest.slice(0, 12).map((p, i) => {
            const chip = p.captain ? 'C' : p.viceCaptain ? 'VC' : p.keeper ? 'WK' : null
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 8, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", lineHeight: 1.1, color: palette.ink, borderBottom: `1px solid ${palette.ink}1c`, paddingBottom: 5, whiteSpace: 'nowrap', overflow: 'hidden' }}>
                <span style={{ color: palette.accent, fontSize: 13, opacity: 0.85, width: 22 }}>{String(i + 1).padStart(2, '0')}</span>
                <span style={{ fontSize: 16, opacity: 0.6, fontWeight: 300 }}>{p.first[0]}.</span>
                <span style={{ fontSize: 22, overflow: 'hidden', textOverflow: 'ellipsis', flex: 1 }}>{p.last}</span>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
            )
          })}
        </div>
      </div>
      <GrainSVG opacity={0.32} id="g7" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE 8 — Asymmetric mosaic
// ─────────────────────────────────────────────────────────────────────────────
export function T8_Mosaic({ team, opponent, match, players, palette, featuredIdx = 0 }) {
  const playersXI = players.slice(0, 11)
  const featuredP = playersXI[featuredIdx] || playersXI.find(p => p.captain) || playersXI[0]
  const rest = playersXI.filter(p => p !== featuredP)
  // featuredP is undefined when no players are picked yet (the empty initial
  // state) — drop the empty slot so the grid renders nothing instead of
  // dereferencing an undefined player below.
  const P = [featuredP, ...rest].filter(Boolean)
  const ROLE_BG = { BAT: palette.accent, BOWL: palette.ink, AR: palette.secondary, WK: palette.primary }
  const ROLE_INK = { BAT: palette.primary, BOWL: palette.primary, AR: palette.ink, WK: palette.ink }
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.05} size={9} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 220, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: -40, top: -40, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 280, lineHeight: 0.8, color: palette.ink, opacity: 0.07, letterSpacing: -6, userSelect: 'none' }}>THE XI</div>
      </div>
      <div style={{ position: 'relative', padding: '36px 36px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 2 }}>
        <div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2, color: palette.accent, marginBottom: 6 }}>// STARTING XI · {match.competition}</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 60, lineHeight: 0.9, color: palette.ink, letterSpacing: -1 }}>
            {team.name} <span style={{ color: palette.accent }}>v</span> {opponent.name}
          </div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={104} shape="shield" />
      </div>
      <div style={{ margin: '0 36px', padding: '14px 18px', background: palette.secondary, borderLeft: `3px solid ${palette.accent}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 18, position: 'relative', zIndex: 2 }}>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, letterSpacing: 1, color: palette.ink }}>{match.round}</div>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, letterSpacing: 1, color: palette.accent }}>{match.date}</div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.5, color: palette.ink, opacity: 0.85 }}>{match.time}</div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.5, color: palette.ink, opacity: 0.85 }}>{match.venue.toUpperCase()}</div>
      </div>
      <div style={{ position: 'absolute', left: 28, right: 28, top: 280, bottom: 80, display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gridTemplateRows: 'repeat(4, 1fr)', gap: 10 }}>
        {P.map((p, i) => {
          const isFeatured = i === 0
          const role = p.role || 'BAT'
          const bg = ROLE_BG[role] || palette.accent
          const ink = ROLE_INK[role] || palette.primary
          const chip = p.captain ? 'C' : p.viceCaptain ? 'VC' : p.keeper ? 'WK' : null
          return (
            <div key={i} style={{
              gridColumn: isFeatured ? 'span 2' : 'span 1',
              gridRow: isFeatured ? 'span 2' : 'span 1',
              background: bg, color: ink,
              position: 'relative', overflow: 'hidden',
              display: 'flex', flexDirection: 'column',
              border: `1.5px solid ${palette.ink}1a`,
            }}>
              <div style={{ flex: 1, position: 'relative', display: 'grid', placeItems: 'center', background: `linear-gradient(180deg, ${bg} 0%, ${palette.primary}aa 100%)`, overflow: 'hidden' }}>
                {p.headshot ? (
                  <img src={p.headshot} alt={p.last} style={{ height: '85%', width: '85%', objectFit: 'contain', objectPosition: 'center bottom' }} />
                ) : (
                  <img src={team.logo} alt={team.short} style={{ width: isFeatured ? 200 : 80, height: isFeatured ? 200 : 80, objectFit: 'contain', opacity: 0.85 }} />
                )}
                <div style={{ position: 'absolute', top: 6, left: 6, fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5, color: ink, opacity: 0.7 }}>#{String(i + 1).padStart(2, '0')}</div>
                {chip && <div style={{ position: 'absolute', top: 6, right: 6 }}><RoleChip kind={chip} accent={palette.accent} ink={palette.primary} /></div>}
              </div>
              <div style={{ padding: isFeatured ? '10px 12px' : '5px 8px', background: ink, color: bg, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: isFeatured ? 32 : 14, letterSpacing: 0.5, lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.last}</div>
            </div>
          )
        })}
      </div>
      <div style={{ position: 'absolute', left: 36, right: 36, bottom: 22, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          {[['BAT', palette.accent], ['BOWL', palette.ink], ['AR', palette.secondary]].map(([lbl, clr]) => (
            <div key={lbl} style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5, color: palette.ink, opacity: 0.7 }}>
              <span style={{ width: 14, height: 14, background: clr, border: lbl === 'AR' ? `1px solid ${palette.ink}55` : 'none', display: 'inline-block' }} /> {lbl}
            </div>
          ))}
        </div>
        <CreditMark ink={palette.ink} h={44} />
      </div>
      <GrainSVG opacity={0.28} id="g8" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TEMPLATE 9 — Festival flyer
// ─────────────────────────────────────────────────────────────────────────────
export function T9_Flyer({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 11)
  const tier1 = P.slice(0, 2)
  const tier2 = P.slice(2, 5)
  const tier3 = P.slice(5, 11)
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.08} size={10} />
      <Stripes color={palette.accent} opacity={0.06} gap={20} angle={0} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: 130, textAlign: 'center', fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 520, lineHeight: 0.8, color: palette.accent, opacity: 0.07, letterSpacing: -10, userSelect: 'none' }}>XI</div>
      {[['left', 'top'], ['right', 'top'], ['left', 'bottom'], ['right', 'bottom']].map(([h, v], i) => (
        <div key={i} style={{
          position: 'absolute',
          [h]: 32, [v]: v === 'bottom' ? 160 : 32,
          width: 40, height: 40,
          borderTop: v === 'top' ? `3px solid ${palette.accent}` : undefined,
          borderBottom: v === 'bottom' ? `3px solid ${palette.accent}` : undefined,
          borderLeft: h === 'left' ? `3px solid ${palette.accent}` : undefined,
          borderRight: h === 'right' ? `3px solid ${palette.accent}` : undefined,
        }} />
      ))}
      <div style={{ textAlign: 'center', padding: '44px 40px 12px', position: 'relative', zIndex: 2 }}>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 4, color: palette.accent, marginBottom: 14 }}>★ {match.competition} · {match.season} · PRESENTS ★</div>
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 20 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={90} shape="shield" />
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 74, letterSpacing: 1, color: palette.ink, lineHeight: 1 }}>{team.name}</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, letterSpacing: 3, color: palette.accent, padding: '0 8px' }}>vs</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 46, letterSpacing: 1, color: palette.ink, lineHeight: 1, opacity: 0.85 }}>{opponent.name}</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={48} shape="shield" />
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12, margin: '8px 0 16px', fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 18, letterSpacing: 6, color: palette.accent }}>
        <span style={{ flex: '0 1 180px', height: 2, background: palette.accent, opacity: 0.5 }} />
        <span>★ ★ ★ THE LINEUP ★ ★ ★</span>
        <span style={{ flex: '0 1 180px', height: 2, background: palette.accent, opacity: 0.5 }} />
      </div>
      <div style={{ textAlign: 'center', padding: '0 40px', lineHeight: 0.88, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", color: palette.ink, letterSpacing: -1 }}>
        <div style={{ fontSize: 108, marginBottom: 6 }}>
          {tier1.map((p, i) => (
            <span key={i}>
              <span>{p.last}</span>
              {i < tier1.length - 1 && <span style={{ color: palette.accent, margin: '0 18px' }}>·</span>}
            </span>
          ))}
        </div>
        <div style={{ fontSize: 68, marginTop: 16, opacity: 0.95 }}>
          {tier2.map((p, i) => (
            <span key={i}>
              <span>{p.last}</span>
              {i < tier2.length - 1 && <span style={{ color: palette.accent, margin: '0 16px' }}>·</span>}
            </span>
          ))}
        </div>
        <div style={{ fontSize: 40, marginTop: 18, opacity: 0.88, letterSpacing: 0 }}>
          <div>
            {tier3.slice(0, 3).map((p, i) => (
              <span key={i}>
                <span>{p.last}</span>
                {i < 2 && <span style={{ color: palette.accent, margin: '0 14px', opacity: 0.7 }}>·</span>}
              </span>
            ))}
          </div>
          <div style={{ marginTop: 6 }}>
            {tier3.slice(3).map((p, i, arr) => (
              <span key={i}>
                <span>{p.last}</span>
                {i < arr.length - 1 && <span style={{ color: palette.accent, margin: '0 14px', opacity: 0.7 }}>·</span>}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, background: palette.accent, color: palette.primary, padding: '22px 40px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 40, letterSpacing: 1, lineHeight: 1 }}>{match.date}</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5, marginTop: 4 }}>GATES {match.time}</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 32, letterSpacing: 2, lineHeight: 1 }}>{match.venue.toUpperCase()}</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5, marginTop: 4 }}>{match.round}</div>
        </div>
        <CreditMark ink={palette.ink} h={44} />
      </div>
      <GrainSVG opacity={0.4} id="g9" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPANION 1 — Generic announcement
// ─────────────────────────────────────────────────────────────────────────────
export function C1_CaptainAnnounce({ announcement, team, opponent, match, palette, player: legacyPlayer }) {
  const a = announcement || { kind: 'ANNOUNCEMENT', headline: 'NAMED', subheadline: '', player: legacyPlayer }
  const player = a.player || legacyPlayer
  const hasHead = !!(player && player.headshot)
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: `linear-gradient(160deg, ${palette.primary} 0%, ${palette.secondary} 100%)`,
      color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.07} size={11} />
      <Stripes color={palette.accent} opacity={0.04} gap={28} angle={-22} />
      <div style={{ position: 'absolute', left: -40, top: -30, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 360, lineHeight: 0.82, color: palette.accent, opacity: 0.09, letterSpacing: -8, userSelect: 'none', whiteSpace: 'nowrap' }}>{(a.kind || 'ANNOUNCEMENT')}</div>
      <div style={{ position: 'absolute', left: 60, top: 90, right: 60, bottom: 200, display: 'grid', placeItems: 'end center', overflow: 'hidden' }}>
        {hasHead ? (
          <img src={player.headshot} alt={player.last} style={{ height: 820, width: 'auto', objectFit: 'contain', objectPosition: 'bottom', filter: `drop-shadow(0 40px 80px ${palette.primary}ee)` }} />
        ) : (
          <img src={team.logo} alt={team.short} style={{ width: 460, height: 460, objectFit: 'contain', marginBottom: 60 }} />
        )}
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '36px 40px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', zIndex: 3 }}>
        <div><div style={{ display: 'inline-block', padding: '7px 14px', background: palette.accent, color: palette.primary, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, letterSpacing: 3 }}>{(a.kind || 'ANNOUNCEMENT').toUpperCase()}</div></div>
        <BrandLockup team={team} palette={palette} size={184} align="right" nameSize={30} style={{ maxWidth: 560 }} />
      </div>
      <div style={{ position: 'absolute', left: 40, bottom: 130, right: 40, zIndex: 3 }}>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 56, letterSpacing: 3, color: palette.accent, marginBottom: 8, lineHeight: 1 }}>{(a.headline || '').toUpperCase()}</div>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 64, letterSpacing: 1, color: palette.ink, opacity: 0.78, lineHeight: 1 }}>{(player?.first || '').toUpperCase()}</div>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 200, letterSpacing: -3, color: palette.ink, lineHeight: 0.84, marginTop: -6 }}>{player?.last || '—'}</div>
        {a.subheadline && <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 28, letterSpacing: 2, color: palette.accent, marginTop: 10 }}>{a.subheadline.toUpperCase()}</div>}
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '16px 40px', background: palette.primary, borderTop: `2px solid ${palette.accent}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 3 }}>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, letterSpacing: 2, color: palette.ink }}>{(team.fullName || team.name).toUpperCase()}</div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5, color: palette.ink, opacity: 0.65 }}>{match.competition} · {match.season}</div>
        <CreditMark ink={palette.ink} h={44} />
      </div>
      <GrainSVG opacity={0.32} id="ca1" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPANION 2 — Toss
// ─────────────────────────────────────────────────────────────────────────────
export function C2_TossWon({ toss, team, opponent, match, palette }) {
  const winnerIsOpponent = toss?.winner === 'OPPONENT'
  const decision = (toss?.decision || 'BAT').toUpperCase()
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.07} size={10} />
      <Stripes color={palette.accent} opacity={0.04} gap={24} angle={-20} />
      <div style={{ position: 'absolute', right: -100, top: -100, width: 660, height: 660, borderRadius: '50%', background: `radial-gradient(circle at 35% 30%, ${palette.accent} 0%, ${palette.accent}dd 50%, ${palette.accent}88 100%)`, boxShadow: `inset 0 0 0 14px ${palette.primary}, inset 0 0 0 20px ${palette.accent}` }} />
      <div style={{ position: 'absolute', right: 90, top: 130, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 280, letterSpacing: -4, color: palette.primary, lineHeight: 0.85, transform: 'rotate(-6deg)' }}>TOSS</div>
      <div style={{ position: 'absolute', left: -50, bottom: 180, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 460, lineHeight: 0.8, color: palette.ink, opacity: 0.05, letterSpacing: -10, userSelect: 'none' }}>{decision}</div>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '32px 40px', display: 'flex', justifyContent: 'flex-start', alignItems: 'center', gap: 14, zIndex: 3 }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={96} shape="shield" />
        <div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2, color: palette.accent }}>// {match.competition} · {match.round}</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 28, letterSpacing: 1.5, marginTop: 2, color: palette.ink }}>{team.name} <span style={{ color: palette.accent }}>v</span> {opponent.name}</div>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 40, top: 320, right: 40 }}>
        <div style={{ display: 'inline-block', padding: '6px 14px', background: palette.accent, color: palette.primary, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 20, letterSpacing: 3, marginBottom: 12 }}>
          {winnerIsOpponent ? `${opponent.name} WON THE TOSS` : `${team.name} WON THE TOSS`}
        </div>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 88, letterSpacing: 2, color: palette.ink, opacity: 0.55, lineHeight: 1, marginTop: 16 }}>{winnerIsOpponent ? "THEY'RE" : "WE'RE"}</div>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 280, letterSpacing: -6, color: palette.ink, lineHeight: 0.85, marginTop: -4 }}>{decision}</div>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 72, letterSpacing: 3, color: palette.accent, lineHeight: 1, marginTop: -8 }}>FIRST</div>
      </div>
      <div style={{ position: 'absolute', left: 40, right: 40, bottom: 100, display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '20px 28px', background: palette.secondary, borderLeft: `4px solid ${palette.accent}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={84} shape="shield" />
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, color: palette.accent }}>VS</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={64} shape="shield" />
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, letterSpacing: 1, color: palette.ink, lineHeight: 1 }}>{match.date}</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.5, color: palette.ink, opacity: 0.75, marginTop: 4 }}>{match.time} · {match.venue.toUpperCase()}</div>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '16px 40px', background: palette.primary, borderTop: `2px solid ${palette.accent}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 3 }}>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 24, letterSpacing: 2, color: palette.ink, opacity: 1 }}>{(team.fullName || team.name).toUpperCase()}</div>
        <CreditMark ink={palette.ink} h={44} />
      </div>
      <GrainSVG opacity={0.3} id="ca2" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPANION 3 — Man of the Match
// ─────────────────────────────────────────────────────────────────────────────
export function C3_ManOfMatch({ motm, team, opponent, match, palette }) {
  const player = motm?.player
  const stats = motm?.stats || []
  const hasHead = !!(player && player.headshot)
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <div style={{ position: 'absolute', left: -100, top: -100, width: 700, height: 1400, background: palette.secondary, transform: 'rotate(8deg)', transformOrigin: 'top left' }} />
      <Halftone color={palette.ink} opacity={0.06} size={11} />
      <Stripes color={palette.accent} opacity={0.04} gap={28} angle={-22} />
      <div style={{ position: 'absolute', right: 60, top: 90, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 320, lineHeight: 0.8, color: palette.accent, opacity: 0.18, letterSpacing: -8, userSelect: 'none' }}>★</div>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, padding: '32px 40px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', zIndex: 3 }}>
        <div>
          <div style={{ display: 'inline-block', padding: '6px 14px', background: palette.accent, color: palette.primary, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 18, letterSpacing: 3 }}>★ MAN OF THE MATCH</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 32, letterSpacing: 1.5, marginTop: 14, color: palette.ink }}>{team.name} <span style={{ color: palette.accent }}>v</span> {opponent.name}</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5, color: palette.ink, opacity: 0.7, marginTop: 6 }}>{match.competition} · {match.round} · {match.date}</div>
        </div>
        <BrandLockup team={team} palette={palette} size={150} layout="stack" nameSize={22} style={{ maxWidth: 320 }} />
      </div>
      <div style={{ position: 'absolute', left: 0, top: 220, width: 520, height: 700, display: 'grid', placeItems: 'end center', overflow: 'hidden' }}>
        {hasHead ? (
          <img src={player.headshot} alt={player?.last} style={{ height: 760, width: 'auto', objectFit: 'contain', objectPosition: 'bottom', filter: `drop-shadow(0 40px 80px ${palette.primary}ee)` }} />
        ) : (
          <img src={team.logo} alt={team.short} style={{ width: 400, height: 400, objectFit: 'contain', marginBottom: 80 }} />
        )}
      </div>
      <div style={{ position: 'absolute', right: 36, top: 230, width: 520, zIndex: 3 }}>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 44, letterSpacing: 1, color: palette.ink, opacity: 0.78, lineHeight: 1 }}>{(player?.first || '').toUpperCase()}</div>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 124, letterSpacing: -1, color: palette.ink, lineHeight: 0.88, marginTop: -2 }}>{player?.last || ''}</div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 2, color: palette.accent, marginTop: 8 }}>{(player?.roleLong || player?.role || '').toUpperCase()}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 22 }}>
          {stats.map((s, i) => (
            <div key={i} style={{ padding: '14px 18px', background: i === 0 ? palette.accent : `${palette.ink}0c`, border: `1.5px solid ${palette.accent}`, color: i === 0 ? palette.primary : palette.ink }}>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2, opacity: 0.75 }}>{s.label.toUpperCase()}</div>
              <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 76, lineHeight: 0.9, letterSpacing: -1, marginTop: 4 }}>{s.value}</div>
            </div>
          ))}
        </div>
        {motm?.summary && (
          <div style={{ marginTop: 16, fontFamily: "'Inter', sans-serif", fontSize: 15, lineHeight: 1.4, color: palette.ink, opacity: 0.78, fontStyle: 'italic', borderLeft: `3px solid ${palette.accent}`, paddingLeft: 14 }}>
            "{motm.summary}"
          </div>
        )}
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '16px 40px', background: palette.primary, borderTop: `2px solid ${palette.accent}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 3 }}>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 18, letterSpacing: 2, color: palette.ink }}>{match.venue.toUpperCase()}</div>
        <CreditMark ink={palette.ink} h={44} />
      </div>
      <GrainSVG opacity={0.3} id="ca3" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPANION 4 — Final score with top performers
// ─────────────────────────────────────────────────────────────────────────────
export function C4_FinalScore({ result, team, opponent, match, palette }) {
  const winnerSide = result?.winner === 'OPPONENT' ? 'opponent' : (result?.winner === 'TIE' ? 'tie' : 'team')
  const tb = result?.topBatters || {}
  const tw = result?.topBowlers || {}
  const teamBatters = tb.team || []
  const teamBowlers = tw.team || []
  const oppBatters = tb.opponent || []
  const oppBowlers = tw.opponent || []
  // C4 feedback: shrink the result/score blocks, blow the performers up. These
  // rows are the focus now, so name + figures are markedly larger.
  const Perf = ({ p, accent }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', borderBottom: `1px solid ${palette.ink}1a`, padding: '9px 0', fontFamily: "var(--social-display-font, 'Anton', sans-serif)", color: palette.ink, lineHeight: 1.05, whiteSpace: 'nowrap', overflow: 'hidden' }}>
      <span style={{ fontSize: 30, letterSpacing: 0.5, overflow: 'hidden', textOverflow: 'ellipsis', paddingRight: 8 }}>{p.last}</span>
      <span style={{ fontSize: 24, color: accent || palette.accent, letterSpacing: 1 }}>{p.line}</span>
    </div>
  )
  const metaLine = [result?.grade || match.competition, match.round, match.date]
    .filter((v, i, a) => v && a.indexOf(v) === i).join(' · ')
  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.06} size={10} />
      <Stripes color={palette.accent} opacity={0.03} gap={28} angle={0} />
      <div style={{ position: 'absolute', inset: 0, paddingBottom: 64, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '32px 48px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: `3px solid ${palette.accent}` }}>
          <div>
            <div style={{ display: 'inline-block', padding: '7px 15px', background: palette.accent, color: palette.primary, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 20, letterSpacing: 3 }}>FULL TIME</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 1.5, color: palette.ink, opacity: 0.7, marginTop: 9 }}>{metaLine}</div>
          </div>
          <BrandLockup team={team} palette={palette} size={92} align="right" nameSize={26} style={{ maxWidth: 460 }} />
        </div>
        <div style={{ padding: '18px 48px 12px', display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 20, alignItems: 'center' }}>
          <div style={{ textAlign: 'center', padding: '13px 16px', background: winnerSide === 'team' ? `${palette.accent}22` : 'transparent', border: `2px solid ${winnerSide === 'team' ? palette.accent : palette.ink + '22'}`, position: 'relative' }}>
            {winnerSide === 'team' && <div style={{ position: 'absolute', top: -13, left: '50%', transform: 'translateX(-50%)', padding: '3px 11px', background: palette.accent, color: palette.primary, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 14, letterSpacing: 2 }}>WINNER</div>}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
              <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={84} shape="shield" />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, letterSpacing: 1, color: palette.ink, lineHeight: 1 }}>{team.name}</div>
                <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 46, letterSpacing: -0.5, lineHeight: 1, color: palette.ink, marginTop: 4 }}>{result?.teamScore || '—'}</div>
              </div>
            </div>
          </div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 38, letterSpacing: 2, color: palette.accent }}>VS</div>
          <div style={{ textAlign: 'center', padding: '13px 16px', background: winnerSide === 'opponent' ? `${palette.accent}22` : 'transparent', border: `2px solid ${winnerSide === 'opponent' ? palette.accent : palette.ink + '22'}`, position: 'relative' }}>
            {winnerSide === 'opponent' && <div style={{ position: 'absolute', top: -13, left: '50%', transform: 'translateX(-50%)', padding: '3px 11px', background: palette.accent, color: palette.primary, fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 14, letterSpacing: 2 }}>WINNER</div>}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
              <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={64} shape="shield" />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, letterSpacing: 1, color: palette.ink, lineHeight: 1 }}>{opponent.name}</div>
                <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 46, letterSpacing: -0.5, lineHeight: 1, color: palette.ink, marginTop: 4 }}>{result?.oppScore || '—'}</div>
              </div>
            </div>
          </div>
        </div>
        <div style={{ margin: '6px 48px 18px', flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, minHeight: 0 }}>
          <div style={{ padding: '24px 26px', background: `${palette.ink}08`, borderLeft: `4px solid ${palette.accent}`, display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 27, letterSpacing: 2, lineHeight: 1, color: palette.accent, marginBottom: 16 }}>{team.short} · TOP PERFORMERS</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.5, color: palette.ink, opacity: 0.6, marginBottom: 6 }}>BATTING</div>
            {teamBatters.slice(0, 3).map((p, i) => <Perf key={i} p={p} />)}
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.5, color: palette.ink, opacity: 0.6, marginTop: 16, marginBottom: 6 }}>BOWLING</div>
            {teamBowlers.slice(0, 3).map((p, i) => <Perf key={i} p={p} />)}
          </div>
          <div style={{ padding: '24px 26px', background: `${palette.ink}08`, borderLeft: `4px solid ${palette.ink}55`, display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 27, letterSpacing: 2, lineHeight: 1, color: palette.ink, opacity: 0.85, marginBottom: 16 }}>{opponent.short} · TOP PERFORMERS</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.5, color: palette.ink, opacity: 0.6, marginBottom: 6 }}>BATTING</div>
            {oppBatters.slice(0, 3).map((p, i) => <Perf key={i} p={p} />)}
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.5, color: palette.ink, opacity: 0.6, marginTop: 16, marginBottom: 6 }}>BOWLING</div>
            {oppBowlers.slice(0, 3).map((p, i) => <Perf key={i} p={p} />)}
          </div>
        </div>
        <div style={{ margin: '0 48px 18px', padding: '15px 24px', background: palette.secondary, borderLeft: `4px solid ${palette.accent}`, textAlign: 'center' }}>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2, color: palette.accent, marginBottom: 5 }}>// MATCH RESULT</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 38, letterSpacing: -0.5, lineHeight: 1.05, color: palette.ink }}>
            {result?.winner === 'TIE' ? 'MATCH TIED' : `${winnerSide === 'team' ? team.name : opponent.name} WIN ${result?.margin || ''}`.trim()}
          </div>
          {result?.motmLast && (
            <div style={{ display: 'inline-block', marginTop: 9, padding: '6px 14px', background: `${palette.ink}10`, border: `1px solid ${palette.accent}`, fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.5, color: palette.ink, opacity: 0.85 }}>★ MOTM · {result.motmLast}</div>
          )}
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '18px 48px', background: palette.primary, borderTop: `2px solid ${palette.accent}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 18, letterSpacing: 2, color: palette.ink }}>{match.venue.toUpperCase()}</div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5, color: palette.ink, opacity: 0.65 }}>{match.season} SEASON</div>
        <CreditMark ink={palette.ink} h={44} />
      </div>
      <GrainSVG opacity={0.3} id="ca4" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SCORECARD TEMPLATES — 1920×1080 full match scorecards
// Props: { match, palette }  where match = { meta, home, away }
// ─────────────────────────────────────────────────────────────────────────────

const SC_FONT = "var(--social-display-font, 'Barlow Condensed', sans-serif)"
const SC_MONO = "'JetBrains Mono', monospace"
const SC_BODY = "'Inter', sans-serif"

function _scIsDark(hex) {
  if (!hex || !hex.startsWith('#')) return true
  const r = parseInt(hex.slice(1, 3), 16) / 255
  const g = parseInt(hex.slice(3, 5), 16) / 255
  const b = parseInt(hex.slice(5, 7), 16) / 255
  return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.4
}

function _toRgba(hex, alpha) {
  if (!hex || !hex.startsWith('#')) return `rgba(255,255,255,${alpha})`
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

function ScSponsorFooter({ bg, ink, dim, dimmer, rule, style = {}, sponsors = [] }) {
  const slots = [0, 1]
  return (
    <div style={{
      position: 'absolute', left: 32, right: 32, bottom: 16, height: 56,
      display: 'grid', gridTemplateColumns: 'auto 1fr auto', alignItems: 'center', gap: 24,
      padding: '0 22px', borderRadius: 12, background: bg, border: `1px solid ${rule}`, ...style,
    }}>
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 40, fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 18, letterSpacing: 3, color: dimmer }}>
        {slots.map(i => {
          const s = sponsors?.[i]
          return s?.url
            ? <img key={i} src={s.url} alt={s.name || `Sponsor ${i+1}`} style={{ maxHeight: 36, maxWidth: 180, objectFit: 'contain', borderRadius: 4 }} />
            : <div key={i} style={{ padding: '6px 18px', border: `1px dashed ${dimmer}`, borderRadius: 6 }}>SPONSOR LOGO</div>
        })}
      </div>
      {/* `ink` is the footer's OWN text colour, handed in by each SC template.
          SC2 inverts the bar (bg={ink} ink={bg}), so read the prop, never the
          palette: this component is not given one, and reaching for it is what
          made every scorecard post throw "palette is not defined". */}
      <CreditMark ink={ink} h={44} />
    </div>
  )
}

// ─── SC1: Broadcast ───────────────────────────────────────────────────────────
export function SC1_Broadcast({ match, palette = {} }) {
  const m = match
  const dark   = _scIsDark(palette.primary)
  const bg     = palette.primary   || (dark ? '#0a1224' : '#f4f3ee')
  const panel  = palette.secondary || (dark ? '#101c38' : '#ffffff')
  const panel2 = bg
  const ink    = palette.ink       || (dark ? '#f4f3ee' : '#0a1224')
  const dim    = _toRgba(ink, 0.55)
  const dimmer = _toRgba(ink, 0.35)
  const rule   = _toRgba(ink, 0.10)
  const accent = palette.accent    || '#ffc233'

  const TeamPanel = ({ team, accentC, side }) => {
    const headerInk = team.headerInk || '#0a0a0a'
    const batCount = (team.batting || []).length
    const bowlCount = (team.bowling || []).length
    const totalRows = Math.max(1, batCount + bowlCount)
    const rp = 3
    const bnf = Math.max(12, Math.min(24, Math.floor((590 / totalRows - 2 * rp) / 1.2)))
    const bff = Math.max(9,  Math.round(bnf * 0.68))
    const brf = Math.max(12, Math.round(bnf * 1.09))
    const bsf = Math.max(9,  Math.round(bnf * 0.59))
    const wnf = bnf
    const wff = bff
    const wwf = Math.max(12, Math.round(bnf * 1.0))
    const wsf = bsf
    return (
    <div style={{ background: panel, border: `1px solid ${rule}`, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', alignItems: 'center', gap: 18, padding: '14px 22px', background: `linear-gradient(90deg, ${accentC}, ${accentC}aa 60%, transparent)`, color: headerInk, borderBottom: `1px solid ${rule}` }}>
        <ClubLogo monogram={team.short} color={headerInk} src={team.logo || null} size={76} shape='shield' />
        <div>
          <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 42, letterSpacing: 1.5, lineHeight: 1 }}>{team.name}</div>
          <div style={{ fontFamily: SC_MONO, fontSize: 12, letterSpacing: 2, marginTop: 4, opacity: 0.75 }}>{side === 'home' ? '1ST INNINGS' : '2ND INNINGS · CHASE'} · {team.overs} OV</div>
        </div>
        <div style={{ textAlign: 'right', lineHeight: 0.9 }}>
          <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 68, letterSpacing: -1 }}>{team.total}{team.wickets < 10 ? `/${team.wickets}` : ''}</div>
        </div>
      </div>
      <div style={{ padding: '8px 18px 4px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '28px 1fr 1.1fr 46px 40px 34px 34px', gap: 8, fontFamily: SC_MONO, fontSize: 11, letterSpacing: 1.5, color: dim, padding: '0 2px 6px', borderBottom: `1px solid ${rule}` }}>
          <div>#</div><div>BATTER</div><div>HOW OUT</div>
          <div style={{ textAlign: 'right' }}>R</div><div style={{ textAlign: 'right' }}>B</div><div style={{ textAlign: 'right' }}>4s</div><div style={{ textAlign: 'right' }}>6s</div>
        </div>
        {(team.batting || []).map((p, i) => {
          const dnb = p.didNotBat
          return (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '28px 1fr 1.1fr 46px 40px 34px 34px', gap: 8, padding: `${rp}px 2px`, alignItems: 'center', borderBottom: i < team.batting.length - 1 ? `1px solid ${rule}` : 'none', opacity: dnb ? 0.4 : 1 }}>
              <div style={{ fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{p.num}</div>
              <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: bnf, letterSpacing: 0.5, lineHeight: 1.2, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
                {p.first && <span style={{ color: dim, fontSize: bff, fontWeight: 300 }}>{p.first} </span>}
                <span>{p.last}</span>
                {p.role && <span style={{ fontFamily: SC_MONO, fontSize: 10, color: accent, letterSpacing: 1, marginLeft: 4 }}>({p.role})</span>}
              </div>
              <div style={{ fontFamily: SC_BODY, fontSize: bsf, color: dim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{dnb ? 'did not bat' : (p.notOut ? 'not out' : p.out)}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: brf, lineHeight: 1, color: dnb ? dim : ink }}>{dnb ? '—' : (p.notOut ? `${p.r}*` : p.r)}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{dnb ? '—' : p.b}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{dnb ? '—' : p.fours}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{dnb ? '—' : p.sixes}</div>
            </div>
          )
        })}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 56px', padding: '7px 2px', borderTop: `1px solid ${rule}`, fontFamily: SC_MONO, fontSize: 12, color: dim, letterSpacing: 1 }}>
          <div>EXTRAS · b {team.extras?.b ?? 0} · lb {team.extras?.lb ?? 0} · nb {team.extras?.nb ?? 0} · wd {team.extras?.wd ?? 0}</div>
          <div style={{ textAlign: 'right', color: ink }}>{team.extras?.total ?? 0}</div>
        </div>
      </div>
      <div style={{ padding: '6px 18px 14px', background: panel2 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 46px 40px 46px 40px 54px', gap: 8, fontFamily: SC_MONO, fontSize: 11, letterSpacing: 2, color: dim, padding: '7px 2px 4px', borderBottom: `1px solid ${rule}` }}>
          <div style={{ color: accent }}>{side === 'home' ? `${m.away?.short ?? 'AWAY'} BOWLING` : `${m.home?.short ?? 'HOME'} BOWLING`}</div>
          <div style={{ textAlign: 'right' }}>O</div><div style={{ textAlign: 'right' }}>M</div><div style={{ textAlign: 'right' }}>R</div><div style={{ textAlign: 'right' }}>W</div><div style={{ textAlign: 'right' }}>ECON</div>
        </div>
        {(team.bowling || []).map((p, i) => (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 46px 40px 46px 40px 54px', gap: 8, padding: `${rp}px 2px`, alignItems: 'center', borderBottom: i < team.bowling.length - 1 ? `1px solid ${rule}` : 'none' }}>
            <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: wnf, letterSpacing: 0.5, lineHeight: 1.2, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
              {p.first && <span style={{ color: dim, fontSize: wff, fontWeight: 300 }}>{p.first} </span>}<span>{p.last}</span>
            </div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: wsf }}>{p.o}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: wsf, color: dim }}>{p.m}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: wsf }}>{p.r}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: wwf, color: p.w > 0 ? accent : ink }}>{p.w}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: wsf, color: dim }}>{(p.econ || 0).toFixed(2)}</div>
          </div>
        ))}
      </div>
    </div>
  )}

  return (
    <div style={{ width: 1920, height: 1080, position: 'relative', overflow: 'hidden', background: bg, color: ink, fontFamily: SC_BODY }}>
      <Halftone color={ink} opacity={dark ? 0.04 : 0.05} size={12} />
      <div style={{ padding: '18px 24px 12px' }}>
        <div style={{ padding: '16px 24px', background: panel, border: `1px solid ${rule}`, display: 'grid', gridTemplateColumns: '1.4fr 1fr auto', alignItems: 'center', gap: 28 }}>
          <div>
            <div style={{ display: 'inline-block', padding: '4px 10px', background: accent, color: '#0a0a0a', fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 13, letterSpacing: 3 }}>{m.meta?.competition} · {m.meta?.round} · {m.meta?.format}</div>
            <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 42, letterSpacing: 1, lineHeight: 1.02, color: ink, marginTop: 8 }}>{m.meta?.result}</div>
            <div style={{ fontFamily: SC_MONO, fontSize: 12, letterSpacing: 1.5, color: dim, marginTop: 4 }}>{m.meta?.date} · {m.meta?.venue}</div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '3px 14px', paddingLeft: 24, borderLeft: `1px solid ${rule}`, fontFamily: SC_MONO, fontSize: 12 }}>
            <span style={{ color: accent, fontWeight: 600, letterSpacing: 1.5 }}>TOSS</span><span style={{ color: ink, fontFamily: SC_BODY }}>{m.meta?.toss}</span>
            <span style={{ color: accent, fontWeight: 600, letterSpacing: 1.5 }}>GROUND</span><span style={{ color: ink, fontFamily: SC_BODY }}>{m.meta?.venue}</span>
            <span style={{ color: accent, fontWeight: 600, letterSpacing: 1.5 }}>COMPETITION</span><span style={{ color: ink, fontFamily: SC_BODY }}>{m.meta?.competition}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', background: `${accent}1a`, border: `1px solid ${accent}66` }}>
            <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 26, color: accent, lineHeight: 1 }}>★</div>
            <div>
              <div style={{ fontFamily: SC_MONO, fontSize: 10, color: accent, letterSpacing: 2, fontWeight: 600 }}>PLAYER OF THE MATCH</div>
              <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 22, color: ink, letterSpacing: 1, lineHeight: 1, marginTop: 4 }}>{(m.meta?.motm?.first || '').toUpperCase()} {m.meta?.motm?.last}</div>
              <div style={{ fontFamily: SC_MONO, fontSize: 11, color: dim, marginTop: 4 }}>{m.meta?.motm?.line}</div>
            </div>
          </div>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, padding: '0 24px', height: 800 }}>
        <TeamPanel team={m.home || {}} accentC={m.home?.color || '#1a4eb8'} side='home' />
        <TeamPanel team={m.away || {}} accentC={m.away?.color || '#cc1f2c'} side='away' />
      </div>
      <ScSponsorFooter bg={panel} ink={ink} dim={dim} dimmer={dimmer} rule={rule} sponsors={m.meta?.sponsors} />
      <GrainSVG opacity={dark ? 0.22 : 0.16} id='sc1g' />
    </div>
  )
}

// ─── SC2: Brutalist ───────────────────────────────────────────────────────────
export function SC2_Brutalist({ match, palette = {} }) {
  const m = match
  const dark     = _scIsDark(palette.primary)
  const bg       = palette.primary   || (dark ? '#0a0a0c' : '#f0ece2')
  const ink      = palette.ink       || (dark ? '#f0ece2' : '#0a0a0c')
  const dim      = _toRgba(ink, 0.55)
  const dimmer   = _toRgba(ink, 0.32)
  const rule     = _toRgba(ink, 0.18)
  const ruleStrong = _toRgba(ink, dark ? 0.7 : 0.85)
  const accent   = palette.accent    || (dark ? '#ffc233' : '#cc1f2c')
  const stripe   = _toRgba(ink, 0.04)

  const TeamCol = ({ team, side }) => {
    const batCount = (team.batting || []).length
    const bowlCount = (team.bowling || []).length
    const totalRows = Math.max(1, batCount + bowlCount)
    const rp = 3
    const bnf = Math.max(12, Math.min(22, Math.floor((520 / totalRows - 2 * rp) / 1.2)))
    const bff = Math.max(9,  Math.round(bnf * 0.65))
    const brf = Math.max(12, Math.round(bnf * 1.1))
    const bsf = Math.max(9,  Math.round(bnf * 0.60))
    const wnf = bnf
    const wff = bff
    const wwf = Math.max(12, Math.round(bnf * 1.0))
    const wsf = bsf
    return (
    <div style={{ borderLeft: `2px solid ${ruleStrong}`, borderRight: `2px solid ${ruleStrong}`, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ background: ink, color: bg, padding: '16px 22px', display: 'grid', gridTemplateColumns: 'auto 1fr auto', alignItems: 'center', gap: 18, borderBottom: `2px solid ${ruleStrong}` }}>
        <ClubLogo monogram={team.short} color={bg} src={team.logo || null} size={70} shape='shield' />
        <div>
          <div style={{ fontFamily: SC_MONO, fontSize: 11, letterSpacing: 3, opacity: 0.65 }}>{side === 'home' ? '1ST INNINGS' : '2ND INNINGS'} · {team.overs} OV</div>
          <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 52, letterSpacing: 1, lineHeight: 0.95, marginTop: 2 }}>{team.name}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 64, letterSpacing: -1, lineHeight: 0.9, color: accent }}>{team.total}{team.wickets < 10 ? `/${team.wickets}` : ''}</div>
        </div>
      </div>
      <div style={{ padding: '10px 18px 0' }}>
        <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 18, letterSpacing: 2, color: accent, paddingBottom: 6, borderBottom: `2px solid ${ruleStrong}` }}>BATTING</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.1fr 44px 38px 32px 32px', gap: 8, fontFamily: SC_MONO, fontSize: 10, letterSpacing: 1.5, color: dim, padding: '6px 0', borderBottom: `1px solid ${rule}` }}>
          <div>BATTER</div><div>HOW OUT</div><div style={{ textAlign: 'right' }}>R</div><div style={{ textAlign: 'right' }}>B</div><div style={{ textAlign: 'right' }}>4s</div><div style={{ textAlign: 'right' }}>6s</div>
        </div>
        {(team.batting || []).map((p, i) => {
          const dnb = p.didNotBat
          return (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1.1fr 44px 38px 32px 32px', gap: 8, padding: `${rp}px 0`, alignItems: 'center', borderBottom: i < team.batting.length - 1 ? `1px solid ${rule}` : 'none', background: i % 2 === 0 ? stripe : 'transparent', opacity: dnb ? 0.35 : 1 }}>
              <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: bnf, letterSpacing: 0.5, lineHeight: 1.2, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
                {p.first && <span style={{ color: dim, fontSize: bff, fontWeight: 300 }}>{p.first} </span>}<span>{p.last}</span>
                {p.role && <span style={{ fontFamily: SC_MONO, fontSize: 9, color: accent, letterSpacing: 1 }}> ({p.role})</span>}
              </div>
              <div style={{ fontFamily: SC_BODY, fontSize: bsf, color: dim, fontStyle: 'italic', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{dnb ? 'did not bat' : (p.notOut ? 'not out' : p.out)}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: brf, lineHeight: 1, color: dnb ? dim : ink, letterSpacing: -0.5 }}>{dnb ? '—' : (p.notOut ? `${p.r}*` : p.r)}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{dnb ? '—' : p.b}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{dnb ? '—' : p.fours}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{dnb ? '—' : p.sixes}</div>
            </div>
          )
        })}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 56px', padding: '6px 0', borderTop: `2px solid ${ruleStrong}`, fontFamily: SC_MONO, fontSize: 11, color: dim, letterSpacing: 1 }}>
          <div>EXTRAS · b {team.extras?.b ?? 0} · lb {team.extras?.lb ?? 0} · nb {team.extras?.nb ?? 0} · wd {team.extras?.wd ?? 0}</div>
          <div style={{ textAlign: 'right', color: ink, fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 18 }}>{team.extras?.total ?? 0}</div>
        </div>
      </div>
      <div style={{ padding: '10px 18px 14px' }}>
        <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 18, letterSpacing: 2, color: accent, paddingBottom: 6, borderBottom: `2px solid ${ruleStrong}` }}>{side === 'home' ? `${m.away?.short ?? 'AWAY'} BOWLING` : `${m.home?.short ?? 'HOME'} BOWLING`}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 42px 38px 42px 38px 56px', gap: 8, fontFamily: SC_MONO, fontSize: 10, letterSpacing: 1.5, color: dim, padding: '6px 0', borderBottom: `1px solid ${rule}` }}>
          <div>BOWLER</div><div style={{ textAlign: 'right' }}>O</div><div style={{ textAlign: 'right' }}>M</div><div style={{ textAlign: 'right' }}>R</div><div style={{ textAlign: 'right' }}>W</div><div style={{ textAlign: 'right' }}>ECON</div>
        </div>
        {(team.bowling || []).map((p, i) => (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 42px 38px 42px 38px 56px', gap: 8, padding: `${rp}px 0`, alignItems: 'center', borderBottom: i < team.bowling.length - 1 ? `1px solid ${rule}` : 'none', background: i % 2 === 0 ? stripe : 'transparent' }}>
            <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: wnf, letterSpacing: 0.5, lineHeight: 1.2, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
              {p.first && <span style={{ color: dim, fontSize: wff, fontWeight: 300 }}>{p.first} </span>}<span>{p.last}</span>
            </div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: wsf }}>{p.o}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: wsf, color: dim }}>{p.m}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: wsf }}>{p.r}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: wwf, color: p.w > 0 ? accent : ink, lineHeight: 1 }}>{p.w}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: wsf, color: dim }}>{(p.econ || 0).toFixed(2)}</div>
          </div>
        ))}
      </div>
    </div>
  )}

  return (
    <div style={{ width: 1920, height: 1080, position: 'relative', overflow: 'hidden', background: bg, color: ink, fontFamily: SC_BODY }}>
      <Stripes color={ink} opacity={0.04} gap={6} angle={0} />
      <Halftone color={ink} opacity={dark ? 0.05 : 0.06} size={12} />
      <div style={{ position: 'absolute', right: -30, top: 200, fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 360, lineHeight: 0.8, color: ink, opacity: 0.04, letterSpacing: -10, userSelect: 'none' }}>FINAL</div>
      <div style={{ background: accent, color: dark ? '#0a0a0c' : '#f0ece2', padding: '18px 32px', display: 'grid', gridTemplateColumns: '1.4fr 1fr auto', alignItems: 'center', gap: 32, borderBottom: `2px solid ${ruleStrong}` }}>
        <div>
          <div style={{ fontFamily: SC_MONO, fontSize: 12, letterSpacing: 3, opacity: 0.85 }}>// {m.meta?.competition} · {m.meta?.round} · {m.meta?.format}</div>
          <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 52, letterSpacing: 1, lineHeight: 1, marginTop: 4 }}>{m.meta?.result}</div>
          <div style={{ fontFamily: SC_MONO, fontSize: 12, letterSpacing: 2, opacity: 0.85, marginTop: 4 }}>{m.meta?.date} · {(m.meta?.venue || '').toUpperCase()}</div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '3px 14px', fontFamily: SC_BODY, fontSize: 12, paddingLeft: 24, borderLeft: `2px solid ${ruleStrong}` }}>
          <span style={{ fontWeight: 700, letterSpacing: 1.5, fontFamily: SC_MONO }}>TOSS</span><span>{m.meta?.toss}</span>
          <span style={{ fontWeight: 700, letterSpacing: 1.5, fontFamily: SC_MONO }}>GROUND</span><span>{m.meta?.venue}</span>
          <span style={{ fontWeight: 700, letterSpacing: 1.5, fontFamily: SC_MONO }}>COMPETITION</span><span>{m.meta?.competition}</span>
        </div>
        <div style={{ padding: '10px 16px', background: bg, color: accent, border: `2px solid ${ruleStrong}` }}>
          <div style={{ fontFamily: SC_MONO, fontSize: 10, letterSpacing: 2, fontWeight: 700, color: ink }}>★ PLAYER OF THE MATCH</div>
          <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 28, color: ink, letterSpacing: 1, lineHeight: 1, marginTop: 4 }}>{(m.meta?.motm?.first || '').toUpperCase()} {m.meta?.motm?.last}</div>
          <div style={{ fontFamily: SC_MONO, fontSize: 11, color: ink, opacity: 0.7, marginTop: 4 }}>{m.meta?.motm?.line}</div>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', height: 760 }}>
        <TeamCol team={m.home || {}} side='home' />
        <TeamCol team={m.away || {}} side='away' />
      </div>
      <ScSponsorFooter bg={ink} ink={bg} dim={_toRgba(bg, 0.55)} dimmer={_toRgba(bg, 0.35)} rule={ruleStrong} sponsors={m.meta?.sponsors} style={{ borderRadius: 0, borderTop: `3px solid ${accent}` }} />
      <GrainSVG opacity={dark ? 0.28 : 0.18} id='sc2g' />
    </div>
  )
}

// ─── SC3: Dashboard ───────────────────────────────────────────────────────────
export function SC3_Dashboard({ match, palette = {} }) {
  const m = match
  const dark   = _scIsDark(palette.primary)
  const bg     = palette.primary   || (dark ? '#0e1116' : '#f3f4f6')
  const card   = palette.secondary || (dark ? '#171b22' : '#ffffff')
  const ink    = palette.ink       || (dark ? '#e5e7eb' : '#111827')
  const dim    = _toRgba(ink, 0.55)
  const dimmer = _toRgba(ink, 0.40)
  const rule   = _toRgba(ink, 0.08)
  const accent = palette.accent    || '#2563eb'
  const win    = palette.accent    || '#10b981'

  const Card = ({ children, style }) => (
    <div style={{ background: card, borderRadius: 16, border: `1px solid ${rule}`, boxShadow: dark ? '0 1px 0 rgba(255,255,255,0.04)' : '0 1px 2px rgba(17,24,39,0.06)', padding: 18, ...style }}>{children}</div>
  )

  const TeamCard = ({ team, accentC, side }) => {
    const batCount = (team.batting || []).length
    const bowlCount = (team.bowling || []).length
    const totalRows = Math.max(1, batCount + bowlCount)
    const rowH = Math.max(20, Math.min(28, Math.floor(590 / totalRows)))
    const sc = rowH / 28
    const rp = Math.max(2, Math.round(5 * sc))
    const bnf = Math.max(11, Math.round(14 * sc))
    const bff = Math.max(9, Math.round(12 * sc))
    const brf = Math.max(12, Math.round(16 * sc))
    const bsf = Math.max(9, Math.round(11 * sc))
    const wwf = Math.max(12, Math.round(16 * sc))
    return (
    <Card style={{ display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr auto', alignItems: 'center', gap: 16, padding: '18px 20px', borderBottom: `1px solid ${rule}` }}>
        {team.logo
          ? <img src={team.logo} alt={team.short} style={{ width: 68, height: 68, objectFit: 'contain', borderRadius: 8 }} />
          : <div style={{ width: 68, height: 68, borderRadius: 12, background: `${accentC}22`, color: accentC, display: 'grid', placeItems: 'center', fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 26, letterSpacing: 1 }}>{team.short}</div>
        }
        <div>
          <div style={{ fontFamily: SC_BODY, fontSize: 12, letterSpacing: 1.5, color: dim, fontWeight: 500 }}>{side === 'home' ? '1ST INNINGS' : '2ND INNINGS'} · {team.overs} ov</div>
          <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 28, letterSpacing: 0.5, lineHeight: 1.1, color: ink }}>{team.name}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 44, lineHeight: 0.9, color: ink, letterSpacing: -1 }}>{team.total}{team.wickets < 10 ? `/${team.wickets}` : ''}</div>
        </div>
      </div>
      <div style={{ padding: '10px 20px 4px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.1fr 42px 38px 32px 32px', gap: 10, alignItems: 'center', marginBottom: 4, paddingBottom: 4, borderBottom: `1px solid ${rule}` }}>
          {['BATTER','HOW OUT','R','B','4s','6s'].map((h, i) => <div key={i} style={{ textAlign: i > 1 ? 'right' : 'left', fontFamily: SC_BODY, fontSize: 10, letterSpacing: 2, color: dim, fontWeight: 600 }}>{h}</div>)}
        </div>
        {(team.batting || []).map((p, i) => {
          const dnb = p.didNotBat
          return (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1.1fr 42px 38px 32px 32px', gap: 10, padding: `${rp}px 0`, alignItems: 'center', borderBottom: i < team.batting.length - 1 ? `1px solid ${rule}` : 'none', opacity: dnb ? 0.4 : 1 }}>
              <div style={{ fontFamily: SC_BODY, fontSize: bnf, fontWeight: 600, color: ink, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
                {p.first && <span style={{ color: dim, fontSize: bff, fontWeight: 400 }}>{p.first} </span>}<span>{p.last}</span>
                {p.role && <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: 1, padding: '1px 5px', borderRadius: 4, background: `${accent}22`, color: accent }}> {p.role}</span>}
              </div>
              <div style={{ fontFamily: SC_BODY, fontSize: bsf, color: dim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{dnb ? 'did not bat' : (p.notOut ? 'not out' : p.out)}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_BODY, fontSize: brf, fontWeight: 700, color: dnb ? dim : ink, lineHeight: 1 }}>{dnb ? '—' : (p.notOut ? `${p.r}*` : p.r)}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{dnb ? '—' : p.b}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{dnb ? '—' : p.fours}</div>
              <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{dnb ? '—' : p.sixes}</div>
            </div>
          )
        })}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', padding: '6px 0', borderTop: `1px solid ${rule}`, fontFamily: SC_BODY, fontSize: 11, color: dim }}>
          <div>Extras · b {team.extras?.b ?? 0} · lb {team.extras?.lb ?? 0} · nb {team.extras?.nb ?? 0} · wd {team.extras?.wd ?? 0}</div>
          <div style={{ fontWeight: 700, color: ink }}>{team.extras?.total ?? 0}</div>
        </div>
      </div>
      <div style={{ padding: '6px 20px 14px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 42px 38px 42px 38px 50px', gap: 10, alignItems: 'center', paddingTop: 8, paddingBottom: 4, borderTop: `1px solid ${rule}`, borderBottom: `1px solid ${rule}` }}>
          {[side === 'home' ? `${m.away?.short ?? 'AWAY'} BOWLING` : `${m.home?.short ?? 'HOME'} BOWLING`, 'O','M','R','W','ECON'].map((h, i) => (
            <div key={i} style={{ textAlign: i > 0 ? 'right' : 'left', fontFamily: SC_BODY, fontSize: 10, letterSpacing: i === 0 ? 2 : 1.5, color: i === 0 ? dim : dimmer, fontWeight: i === 0 ? 600 : 500 }}>{h}</div>
          ))}
        </div>
        {(team.bowling || []).map((p, i) => (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 42px 38px 42px 38px 50px', gap: 10, padding: `${rp}px 0`, alignItems: 'center', borderBottom: i < team.bowling.length - 1 ? `1px solid ${rule}` : 'none' }}>
            <div style={{ fontFamily: SC_BODY, fontSize: bnf, fontWeight: 600, color: ink, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
              {p.first && <span style={{ color: dim, fontSize: bff, fontWeight: 400 }}>{p.first} </span>}<span>{p.last}</span>
            </div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{p.o}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{p.m}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{p.r}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_BODY, fontSize: wwf, fontWeight: 700, color: p.w > 0 ? accent : ink, lineHeight: 1 }}>{p.w}</div>
            <div style={{ textAlign: 'right', fontFamily: SC_MONO, fontSize: bsf, color: dim }}>{(p.econ || 0).toFixed(2)}</div>
          </div>
        ))}
      </div>
    </Card>
  )}

  return (
    <div style={{ width: 1920, height: 1080, position: 'relative', overflow: 'hidden', background: bg, color: ink, fontFamily: SC_BODY }}>
      <div style={{ padding: '20px 32px 12px' }}>
        <Card style={{ padding: '16px 24px', display: 'grid', gridTemplateColumns: '1.4fr 1fr auto', alignItems: 'center', gap: 28 }}>
          <div>
            <div style={{ fontFamily: SC_BODY, fontSize: 11, letterSpacing: 2, color: dim, fontWeight: 600 }}>{m.meta?.competition} · {m.meta?.round} · {m.meta?.format}</div>
            <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 42, letterSpacing: 0.5, lineHeight: 1.02, color: ink, marginTop: 4 }}>{m.meta?.result}</div>
            <div style={{ fontFamily: SC_BODY, fontSize: 13, color: dim, marginTop: 4 }}>{m.meta?.date} · {m.meta?.venue}</div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '3px 14px', fontFamily: SC_BODY, fontSize: 12, paddingLeft: 24, borderLeft: `1px solid ${rule}` }}>
            <span style={{ color: dim, fontWeight: 600, letterSpacing: 1 }}>TOSS</span><span style={{ color: ink }}>{m.meta?.toss}</span>
            <span style={{ color: dim, fontWeight: 600, letterSpacing: 1 }}>GROUND</span><span style={{ color: ink }}>{m.meta?.venue}</span>
            <span style={{ color: dim, fontWeight: 600, letterSpacing: 1 }}>COMPETITION</span><span style={{ color: ink }}>{m.meta?.competition}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderRadius: 12, background: `${win}14`, border: `1px solid ${win}55` }}>
            <div style={{ fontSize: 22, lineHeight: 1, color: win }}>★</div>
            <div>
              <div style={{ fontFamily: SC_BODY, fontSize: 10, letterSpacing: 2, color: win, fontWeight: 700 }}>PLAYER OF THE MATCH</div>
              <div style={{ fontFamily: SC_FONT, fontWeight: "var(--social-display-font-weight, 800)", fontSize: 22, color: ink, letterSpacing: 0.5, lineHeight: 1, marginTop: 4 }}>{(m.meta?.motm?.first || '').toUpperCase()} {m.meta?.motm?.last}</div>
              <div style={{ fontFamily: SC_BODY, fontSize: 11, color: dim, marginTop: 4 }}>{m.meta?.motm?.line}</div>
            </div>
          </div>
        </Card>
      </div>
      <div style={{ padding: '0 32px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, height: 820 }}>
        <TeamCard team={m.home || {}} accentC={m.home?.color || '#2563eb'} side='home' />
        <TeamCard team={m.away || {}} accentC={m.away?.color || '#10b981'} side='away' />
      </div>
      <ScSponsorFooter bg={card} ink={ink} dim={dim} dimmer={dimmer} rule={rule} sponsors={m.meta?.sponsors} />
    </div>
  )
}
