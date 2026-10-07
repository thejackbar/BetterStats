// Round Highlights cover (RS8): the first slide of a round's photo dump. One
// full-bleed match photo carries the whole post. A grade label runs up the top
// left, the club mark sits top right, and the kicker, the title and a single
// score card for both teams sit over the foot of the photo, above a hatched
// strip. The rest of a highlights carousel is clean photos, so this is the only
// slide with type on it.
//
// The score card puts the side that batted first on top. The result data does
// not say who batted first, so unless `r.battedFirst` ('us' or 'them') is given
// the winner goes on top, which is where the batting-first side sits whenever it
// also won. The loser's row is dimmed and the winner's carries the trophy.
//
// No backdrop-filter: the PNG export (modern-screenshot) does not paint it, so
// the card is a plain tinted pane over a gradient that is dark where the type is.
//
// `highlightsSponsorSlot` is the ONE answer for where the sponsor grid goes (a
// white pill inside the hatched strip); the layout calls it so the strip's height
// and the place the grid sits cannot drift apart.
import { AutoFitText, ClubLogo, heroFocusStyle } from './cricket-templates'
import { aspectOf, pick } from './postAspect'
import { LayerRoot } from './postLayers'
import { hatch } from './card-kit'

const FONT = "var(--social-display-font, 'Anton', 'Hanken Grotesk', sans-serif)"
const WEIGHT = 'var(--social-display-font-weight, 700)'
export const HIGHLIGHTS_FOCUS = { x: 50, y: 30, scale: 1 }

export function highlightsGeo(width = 1080, height = 1080, count = 0) {
  const A = aspectOf(width, height)
  const f = pick(A, { square: 0.84, portrait: 1, story: 1.08 })
  // A story's last couple of hundred pixels sit under the app's reply bar.
  const lift = pick(A, { square: 0, portrait: 0, story: 230 })
  const stripH = count > 0 ? pick(A, { square: 92, portrait: 112, story: 124 }) : pick(A, { square: 44, portrait: 56, story: 64 })
  const stripTop = height - lift - stripH
  const cardH = Math.round(162 * f)
  const cardW = Math.min(width - 160, Math.round(730 * f))
  const cardTop = stripTop - Math.round(30 * f) - cardH
  const edge = Math.round(58 * f)
  const topM = pick(A, { square: 52, portrait: 112, story: 190 })
  const overlayH = pick(A, { square: 470, portrait: 560, story: 760 })
  return { A, f, lift, stripH, stripTop, cardH, cardW, cardTop, edge, topM, overlayH }
}

// The sponsor grid sits inside the strip: a slim white pill, centred.
export function highlightsSponsorSlot(width = 1080, height = 1080, count = 1) {
  const g = highlightsGeo(width, height, Math.max(1, count))
  const n = Math.max(1, count)
  const w = Math.min(width - 300, n <= 1 ? 340 : n <= 3 ? 560 : 720)
  const pad = 14
  return { x: Math.round((width - w) / 2), y: g.stripTop + pad, w, h: g.stripH - pad * 2, pad: 4, gap: 20, panel: 'light' }
}

const scoreOf = (s) => {
  const t = String(s || '').trim()
  return !t || t === '—' || t === '-' ? '' : t.replace('/', '-')
}
const oversOf = (o) => {
  const t = String(o || '').replace(/[()]/g, '').trim()
  return t ? `(${t})` : ''
}

const Trophy = ({ size, color }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ display: 'block', flexShrink: 0 }}>
    <path d="M7 3h10v5a5 5 0 0 1-10 0V3z" fill={color} />
    <path d="M7 4.5H4v1.5a3.5 3.5 0 0 0 3.2 3.5M17 4.5h3v1.5a3.5 3.5 0 0 1-3.2 3.5" fill="none" stroke={color} strokeWidth="1.6" />
    <rect x="10.8" y="12.5" width="2.4" height="4" fill={color} />
    <rect x="7.5" y="17" width="9" height="3" rx="1" fill={color} />
  </svg>
)
Trophy.displayName = 'Trophy'

export function ResultHighlights({
  width = 1080, height = 1080, palette = {}, result: r = {}, photo, focus, sponsorCount = 0,
}) {
  const g = highlightsGeo(width, height, sponsorCount)
  const { f } = g
  const accent = palette.accent || '#ffc233'
  const ink = palette.ink || '#ffffff'
  const fx = { ...HIGHLIGHTS_FOCUS, ...(focus || {}) }
  const us = r.us || {}
  const them = r.them || {}

  const first = r.battedFirst === 'us' || r.battedFirst === 'them' ? r.battedFirst : (r.winner === 'them' ? 'them' : 'us')
  const rows = (first === 'us' ? [['us', us], ['them', them]] : [['them', them], ['us', us]]).map(([k, t]) => ({
    key: k, name: String(t.name || '').toUpperCase(), score: scoreOf(t.score), overs: oversOf(t.overs),
    won: r.winner === k,
  }))
  const kicker = `${String(r.round || '').toUpperCase().replace(/^ROUND\s*/, 'RND ')}${them.name ? ` V ${String(them.name).toUpperCase()}` : ''}`.trim()
  const title = String(r.title || 'ROUND HIGHLIGHTS').toUpperCase()
  const compLine = String(r.comp && r.comp !== 'COMPETITION' ? r.comp : '').toUpperCase()
  const gradeLine = String(r.grade || '').toUpperCase()
  const labelLen = pick(g.A, { square: 380, portrait: 440, story: 460 })
  const rowFont = Math.round(32 * f)

  const sideLabel = (text, weight, size, x, opacity) => (
    <div style={{
      position: 'absolute', left: x, top: g.topM + labelLen, width: labelLen, height: size + 6,
      transform: 'rotate(-90deg)', transformOrigin: '0 0', textAlign: 'right', whiteSpace: 'nowrap', overflow: 'hidden',
      fontSize: size, lineHeight: `${size + 6}px`, fontWeight: weight, letterSpacing: 1, color: ink, opacity,
    }}>{text}</div>
  )

  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden', background: '#0a0a0a', color: ink, fontFamily: FONT, fontWeight: WEIGHT,
    }}>
      {photo && (
        <div data-layer="Photo" style={{ position: 'absolute', left: 0, top: 0, width, height }}>
          <img src={photo} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', ...heroFocusStyle(fx) }} />
        </div>
      )}

      <div data-layer="Corner shades" style={{
        position: 'absolute', left: 0, top: 0, width, height, pointerEvents: 'none',
        background: 'radial-gradient(ellipse 34% 22% at 4% 9%, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0) 100%), radial-gradient(ellipse 30% 18% at 94% 4%, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0) 100%)',
      }} />

      <div data-layer="Foot shade" style={{
        position: 'absolute', left: 0, right: 0, bottom: 0, height: g.overlayH, pointerEvents: 'none',
        background: 'linear-gradient(to bottom, rgba(0,0,0,0) 0%, rgba(0,0,0,0.46) 40%, rgba(0,0,0,0.88) 100%)',
      }} />

      <div data-layer="Kicker and title" style={{
        position: 'absolute', left: Math.round(width * 0.09), right: Math.round(width * 0.09), bottom: height - g.cardTop + Math.round(36 * f),
        display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: Math.round(16 * f),
      }}>
        {kicker && <div style={{ fontSize: Math.round(30 * f), letterSpacing: 5, opacity: 0.82, lineHeight: 1.1 }}>{kicker}</div>}
        <div style={{ width: '100%' }}>
          <AutoFitText text={title} max={Math.round(92 * f)} min={36} lines={1} measureDeps={[width, height]}
            style={{ color: ink, lineHeight: 1, letterSpacing: 1, textAlign: 'center', textShadow: '0 4px 26px rgba(0,0,0,0.5)' }} />
        </div>
      </div>

      {(compLine || gradeLine) && (
        <div data-layer="Side label" style={{ position: 'absolute', left: 0, top: 0, width: 0, height: 0 }}>
          {compLine && sideLabel(compLine, 700, Math.round(24 * f), g.edge + Math.round(34 * f), 1)}
          {gradeLine && sideLabel(gradeLine, 300, Math.round(20 * f), g.edge, 0.85)}
        </div>
      )}

      <div data-layer="Club logo" style={{ position: 'absolute', right: g.edge, top: g.topM, width: Math.round(84 * f), height: Math.round(84 * f) }}>
        <ClubLogo src={us.logo} monogram={us.mono} color={ink} size={Math.round(84 * f)} shape="shield" />
      </div>

      {hatch('Hatched strip', accent, { left: 0, top: g.stripTop, width, height: g.stripH, gap: 12, angle: -45, opacity: 0.6 })}

      <div data-layer="Score card" style={{
        position: 'absolute', left: Math.round((width - g.cardW) / 2), top: g.cardTop, width: g.cardW, height: g.cardH, boxSizing: 'border-box',
        border: '2px solid rgba(255,255,255,0.22)', borderRadius: 4, background: 'rgba(8,8,8,0.42)', padding: Math.round(28 * f),
        display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      }}>
        {rows.map((row, i) => (
          <div key={row.key} style={{
            display: 'flex', alignItems: 'center', gap: 14, minHeight: rowFont, opacity: row.won || !r.winner || r.winner === 'tie' ? 1 : 0.8,
            borderTop: i === 1 ? '2px dashed rgba(255,255,255,0.4)' : 'none', paddingTop: i === 1 ? Math.round(18 * f) : 0,
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <AutoFitText text={row.name} max={rowFont} min={14} lines={1} measureDeps={[width, height, row.name]}
                style={{ color: ink, lineHeight: 1.1, letterSpacing: 0.5, fontWeight: row.won ? 800 : 400 }} />
            </div>
            {row.won && <Trophy size={Math.round(24 * f)} color={accent} />}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, flexShrink: 0 }}>
              <span style={{ fontSize: rowFont, lineHeight: 1.1, fontWeight: row.won ? 800 : 500 }}>{row.score || '—'}</span>
              {row.overs && <span style={{ fontSize: Math.round(14 * f), opacity: 0.8 }}>{row.overs}</span>}
            </div>
          </div>
        ))}
      </div>
    </LayerRoot>
  )
}
ResultHighlights.displayName = 'ResultHighlights'

// Where this file's layouts keep the sponsor grid (see sponsorSlots.js).
export const SPONSOR_SLOTS = { RS8: highlightsSponsorSlot }
