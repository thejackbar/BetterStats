// Team of the week — the round's best performers across every grade, one post.
//
// A team of the week is ANY size from 6 to 14 (11 by default), so unlike the
// lineup layouts these do not draw a fixed number of slots: the grid picks its
// columns from the count and the board splits its height by it. Whatever the
// count, the players fill the whole body and the last row of a grid is centred
// rather than left ragged against one edge.
//
// Same vocabulary as the roundup family (round-templates.jsx): a masthead, a
// body and the sponsor strip, drawn on the club palette and the display font,
// with every element addressable as a layer.
import { GrainSVG as Grain, Halftone, Stripes, ClubLogo, AutoFitText, CreditMark } from './cricket-templates'
import { FOOT_BUG_W } from './round-templates'
import { aspectOf, pick, grow } from './postAspect'
import { LayerRoot } from './postLayers'

const DISPLAY = "var(--social-display-font, 'Anton', sans-serif)"
const MONO = "'JetBrains Mono', monospace"
const BODY = "'Inter', sans-serif"

export const TOTW_MIN = 6
export const TOTW_MAX = 14
export const TOTW_DEFAULT = 11

// Columns for a grid of `n` cards. Chosen so the last row is never a lone card
// and no row is wider than the card can carry a surname and a stat line.
//   6 -> 3x2   7,8 -> 4x2   9 -> 3x3   10-12 -> 4x3   13,14 -> 5x3
export function totwColumns(n) {
  if (n <= 6) return 3
  if (n <= 8) return 4
  if (n === 9) return 3
  if (n <= 12) return 4
  return 5
}

// The sponsor slot. The grid gets a bar of its own along the foot: the strip is as
// tall as the grid needs (a logo reads at about 90px), the credit mark sits at
// its right and the body stops above it, whatever the player count. `slotTW` is
// the ONE function both this layout and SPONSOR_SLOTS call, so the room kept and
// the place the editor puts the grid cannot drift apart. `count` only sets the
// panel's width (one logo, a short panel; three, the bar); the layout reserves
// the widest.
const TW_PANEL_W = [0, 380, 600, 882]
const twPadV = (height) => grow(height, 12, 0.02)
function slotTW(width = 1080, height = 1080, count = 3) {
  const h = grow(height, 96, 0.06)
  const room = width - 56 * 2 - FOOT_BUG_W - 22
  return {
    x: 56, y: height - twPadV(height) - h, w: Math.min(room, TW_PANEL_W[Math.max(1, Math.min(3, count))]), h,
    pad: 8, gap: 20, panel: 'light',
  }
}

// Where the body starts and how much it leaves clear for the sponsor strip.
// `grow` keeps the masthead and footer from ballooning on a taller post; the
// body absorbs the rest, which is more room for the players.
function frame(width, height) {
  const A = aspectOf(width, height)
  const s = slotTW(width, height, 3)
  // The strip's real height (its padding twice, the slot, the rule): derived from
  // the slot so the body always ends above it.
  const strip = height - s.y + twPadV(height) + 2
  return {
    A,
    top: grow(height, 244, 0.14),
    strip,
    bottom: strip + grow(height, 14, 0.03),
  }
}

// The stat line under a name. Empty when the performance has none.
function Line({ text, size, color, style = {} }) {
  if (!text) return null
  return (
    <div style={{
      fontFamily: MONO, fontSize: size, letterSpacing: 0.6, color, lineHeight: 1.15,
      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', ...style,
    }}>{text}</div>
  )
}

// What the body shows before any player is picked, so an empty post says what
// to do rather than sitting blank.
function emptyState(pal) {
  return (
    <div style={{ flex: 1, display: 'grid', placeItems: 'center', border: `2px dashed ${pal.ink}33`, fontFamily: DISPLAY, fontSize: 34, letterSpacing: 2, color: pal.ink, opacity: 0.6, textAlign: 'center', padding: 24 }}>
      PICK {TOTW_MIN} TO {TOTW_MAX} PLAYERS
    </div>
  )
}

// One face: the player's photo, else the club crest, else the monogram.
function Face({ p, team, palette, fit = 'contain', pos = 'center top' }) {
  if (p.headshot) {
    return <img src={p.headshot} alt={`${p.first || ''} ${p.last || ''}`.trim()}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: fit, objectPosition: pos }} />
  }
  if (team.logo) {
    return (
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}>
        <img src={team.logo} alt={team.short || 'club'} style={{ width: '62%', height: '62%', objectFit: 'contain', opacity: 0.9 }} />
      </div>
    )
  }
  return (
    <div style={{
      position: 'absolute', inset: 0, display: 'grid', placeItems: 'center',
      fontFamily: DISPLAY, fontSize: 72, color: palette.accent, opacity: 0.85, letterSpacing: -2, lineHeight: 1,
    }}>{team.monogram || '?'}</div>
  )
}

// Plain functions returning their root `div`, called inline: a component child of
// the layer root only takes a z-index if it spreads `style`, and a `div` always does.
function masthead({ pal, team, meta, width, big }) {
  const round = [meta.round, meta.date].filter(Boolean).join(' · ')
  return (
    <div data-layer="Masthead" style={{
      position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 26px',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24, width,
      boxSizing: 'border-box',
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 3, color: pal.accent, fontWeight: 600 }}>{`// ${round}`.toUpperCase()}</div>
        <div style={{ fontFamily: DISPLAY, fontSize: big, letterSpacing: -1, lineHeight: 0.86, marginTop: 8 }}>
          TEAM OF <span style={{ color: pal.accent }}>THE WEEK</span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0 }}>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: DISPLAY, fontSize: 28, letterSpacing: 0.5, lineHeight: 0.95, maxWidth: 240 }}>{team.fullName || team.name}</div>
          {meta.comp ? <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1.6, opacity: 0.6, marginTop: 6 }}>{meta.comp}</div> : null}
        </div>
        <ClubLogo src={team.logo || null} monogram={team.monogram} color={pal.ink} size={104} shape="shield" />
      </div>
    </div>
  )
}

// The footer strip. The left is the sponsor slot, left empty for the grid; the
// platform credit sits at the right.
function footer({ pal, width, height }) {
  return (
    <div data-layer="Sponsors" style={{
      position: 'absolute', left: 0, right: 0, bottom: 0, height: frame(width, height).strip, boxSizing: 'border-box',
      padding: '0 56px', display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
      background: pal.primary, borderTop: `2px solid ${pal.accent}`,
    }}>
      <CreditMark ink={pal.ink} h={40} />
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TW1 — Team sheet: a grid of photo cards
// ═══════════════════════════════════════════════════════════════════════════
export function TeamOfWeekGrid({ palette: pal, width = 1080, height = 1080, team = {}, players = [], totw = {}, sponsors }) {
  const P = (typeof window !== 'undefined' && window.__TWN) ? Array.from({ length: window.__TWN }, (_, i) => players[i % Math.max(1, players.length)] || {}) : players.slice(0, TOTW_MAX) // TEMP-E
  const n = P.length
  const F = frame(width, height)
  const cols = totwColumns(n)
  const rows = Math.max(1, Math.ceil(n / cols))
  const gap = 14
  const gridW = width - 112
  const gridH = height - F.top - F.bottom
  const cardW = Math.floor((gridW - gap * (cols - 1)) / cols)
  const cardH = Math.floor((gridH - gap * (rows - 1)) / rows)
  // The name band scales with the card so a 5-wide card is not set like a
  // 3-wide one; the photo takes the rest.
  const bandH = Math.max(64, Math.min(104, Math.round(cardH * 0.34)))
  const nameMax = Math.max(18, Math.min(38, Math.round(cardW * 0.17)))
  const lineSize = cardW < 200 ? 11 : 13
  const big = pick(F.A, { square: 78, portrait: 90, story: 104 })
  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: pal.primary, color: pal.ink, fontFamily: BODY,
    }}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.035} gap={28} angle={45} />
      <div style={{ position: 'absolute', left: -50, bottom: F.strip + 64, fontFamily: DISPLAY, fontSize: 300, lineHeight: 0.8, color: pal.ink, opacity: 0.04, letterSpacing: -6, transform: 'rotate(-8deg)', userSelect: 'none', whiteSpace: 'nowrap' }}>TOTW</div>
      {masthead({ pal, team, meta: totw, width, big })}
      <div data-layer="Players" style={{
        position: 'absolute', left: 56, right: 56, top: F.top, bottom: F.bottom,
        display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignContent: 'flex-start', gap,
      }}>
        {n === 0 ? emptyState(pal) : null}
        {P.map((p, i) => {
          const t = p.totw || {}
          return (
            <div key={p._id || i} style={{
              width: cardW, height: cardH, position: 'relative', overflow: 'hidden', boxSizing: 'border-box',
              background: `linear-gradient(180deg, ${pal.secondary} 0%, ${pal.primary} 100%)`,
              border: `2px solid ${pal.accent}`, display: 'flex', flexDirection: 'column',
            }}>
              <div style={{ flex: 1, position: 'relative', overflow: 'hidden', minHeight: 0 }}>
                <Halftone color={pal.ink} opacity={0.08} size={6} />
                <Face p={p} team={team} palette={pal} />
                <div style={{ position: 'absolute', top: 7, left: 9, fontFamily: MONO, fontSize: 11, color: pal.ink, opacity: 0.55, letterSpacing: 1.5 }}>#{String(i + 1).padStart(2, '0')}</div>
                {totw.showPoints && t.points != null ? (
                  <div style={{ position: 'absolute', top: 6, right: 6, padding: '2px 7px', background: pal.accent, color: pal.primary, fontFamily: DISPLAY, fontSize: 15, letterSpacing: 1, lineHeight: 1.2 }}>{t.points} PTS</div>
                ) : null}
              </div>
              <div style={{ height: bandH, background: pal.accent, color: pal.primary, padding: '0 10px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 3, boxSizing: 'border-box' }}>
                <AutoFitText text={p.last} max={nameMax} min={11} lines={1}
                  style={{ fontFamily: DISPLAY, letterSpacing: 1, lineHeight: 1, maxWidth: '100%', textAlign: 'center' }} />
                <Line text={t.line} size={lineSize} color={pal.primary} style={{ textAlign: 'center', fontWeight: 600 }} />
                {t.grade ? <Line text={t.grade} size={Math.max(9, lineSize - 2)} color={pal.primary} style={{ textAlign: 'center', opacity: 0.7 }} /> : null}
              </div>
            </div>
          )
        })}
      </div>
      {footer({ pal, width, height })}
      <Grain opacity={0.32} id="tw1-g" />
    </LayerRoot>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TW2 — Ranked board: one row per player
// ═══════════════════════════════════════════════════════════════════════════
export function TeamOfWeekBoard({ palette: pal, width = 1080, height = 1080, team = {}, players = [], totw = {}, sponsors }) {
  const P = (typeof window !== 'undefined' && window.__TWN) ? Array.from({ length: window.__TWN }, (_, i) => players[i % Math.max(1, players.length)] || {}) : players.slice(0, TOTW_MAX) // TEMP-E
  const n = P.length
  const F = frame(width, height)
  const rowH = (height - F.top - F.bottom) / Math.max(1, n)
  // Everything in a row is sized off the row's own height, so 6 players get big
  // type and 14 get tight type on the same layout.
  const face = Math.max(34, Math.min(96, Math.round(rowH - 12)))
  const nameSize = Math.max(22, Math.min(46, Math.round(rowH * 0.52)))
  const firstSize = Math.max(11, Math.min(20, Math.round(rowH * 0.24)))
  const lineSize = Math.max(13, Math.min(24, Math.round(rowH * 0.36)))
  const subSize = Math.max(10, Math.min(14, Math.round(rowH * 0.2)))
  const numSize = Math.max(18, Math.min(40, Math.round(rowH * 0.48)))
  const big = pick(F.A, { square: 78, portrait: 90, story: 104 })
  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: pal.primary, color: pal.ink, fontFamily: BODY,
    }}>
      <Halftone color={pal.ink} opacity={0.05} size={12} />
      <div style={{ position: 'absolute', left: -120, top: -80, width: 640, height: Math.round(height * 1.3), background: pal.secondary, transform: 'rotate(8deg)', transformOrigin: 'top left', opacity: 0.55 }} />
      {masthead({ pal, team, meta: totw, width, big })}
      <div data-layer="Players" style={{
        position: 'absolute', left: 56, right: 56, top: F.top, bottom: F.bottom,
        display: 'flex', flexDirection: 'column', borderTop: `3px solid ${pal.accent}`,
      }}>
        {n === 0 ? emptyState(pal) : null}
        {P.map((p, i) => {
          const t = p.totw || {}
          return (
            <div key={p._id || i} style={{
              flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', gap: 16,
              borderBottom: i < n - 1 ? `1px solid ${pal.ink}1f` : 'none',
            }}>
              <div style={{ width: numSize * 1.7, flexShrink: 0, fontFamily: DISPLAY, fontSize: numSize, letterSpacing: 0.5, color: pal.accent, lineHeight: 1 }}>{String(i + 1).padStart(2, '0')}</div>
              <div style={{ width: face, height: face, flexShrink: 0, position: 'relative', overflow: 'hidden', borderRadius: '50%', background: `${pal.ink}14`, border: `2px solid ${pal.accent}`, boxSizing: 'border-box' }}>
                <Face p={p} team={team} palette={pal} pos="center 12%" />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                {p.first ? <div style={{ fontFamily: DISPLAY, fontSize: firstSize, letterSpacing: 1.5, opacity: 0.7, lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(p.first).toUpperCase()}</div> : null}
                <div style={{ fontFamily: DISPLAY, fontSize: nameSize, letterSpacing: 0.5, lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.last}</div>
                {t.grade || t.opp ? (
                  <Line text={[t.grade, t.opp ? `v ${t.opp}` : ''].filter(Boolean).join(' · ')} size={subSize} color={pal.ink} style={{ opacity: 0.6, marginTop: 2, letterSpacing: 1.2 }} />
                ) : null}
              </div>
              <div style={{ flexShrink: 0, textAlign: 'right', maxWidth: '38%' }}>
                <Line text={t.line} size={lineSize} color={pal.accent} style={{ fontWeight: 700 }} />
                {totw.showPoints && t.points != null ? (
                  <div style={{ fontFamily: MONO, fontSize: subSize, letterSpacing: 1.5, opacity: 0.6, marginTop: 2 }}>{t.points} PTS</div>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
      {footer({ pal, width, height })}
      <Grain opacity={0.3} id="tw2-g" />
    </LayerRoot>
  )
}

TeamOfWeekGrid.displayName = 'TeamOfWeekGrid'
TeamOfWeekBoard.displayName = 'TeamOfWeekBoard'
Line.displayName = 'Line'
Face.displayName = 'Face'

// Where this file's layouts keep the sponsor grid (see sponsorSlots.js).
export const SPONSOR_SLOTS = { TW1: slotTW, TW2: slotTW }
