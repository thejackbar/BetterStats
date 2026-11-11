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
import { usePostLook } from './postLook'
import { pc, pt, inkOn, registerParts, colorPart as C, textPart as T } from './layoutParts'

// What the club can set on each layout (Brand, "Team Sheet elements"). Same keys
// across the two, so a heading or a name colour carries from one to the other.
const HEAD = 'Heading', CARD = 'Player cards', ROW = 'Player rows', FOOT = 'Footer'
const HEADING_PARTS = [
  T('title1', 'First word(s)', HEAD, () => 'TEAM OF'),
  C('title1Color', 'First word colour', HEAD, (p) => p.ink),
  T('title2', 'Second word(s)', HEAD, () => 'THE WEEK'),
  C('title2Color', 'Second word colour', HEAD, (p) => p.accent),
  C('roundColor', 'Round line', HEAD, (p) => p.accent),
  C('clubColor', 'Club name', HEAD, (p) => p.ink),
]
const FOOTER_PARTS = [
  C('footerBg', 'Footer bar', FOOT, (p) => p.primary),
  C('footerRule', 'Footer line', FOOT, (p) => p.accent),
]
registerParts({
  TW1: [
    ...HEADING_PARTS,
    C('photoBg', 'Photo backdrop', CARD, null, { autoLabel: 'Card colour' }),
    C('cardBorder', 'Card outline', CARD, (p) => p.accent),
    C('numColor', 'Card number', CARD, (p) => p.ink),
    C('bandBg', 'Name band', CARD, (p) => p.accent),
    C('nameColor', 'Surname', CARD, (p) => p.primary),
    C('statColor', 'Score line', CARD, (p) => p.primary),
    C('gradeColor', 'Grade line', CARD, (p) => p.primary),
    C('pointsBg', 'Points tag', CARD, (p) => p.accent),
    C('pointsColor', 'Points text', CARD, (p) => p.primary),
    ...FOOTER_PARTS,
  ],
  TW2: [
    ...HEADING_PARTS,
    C('ruleColor', 'Top line', ROW, (p) => p.accent),
    C('dividerColor', 'Row dividers', ROW, (p) => p.ink),
    C('numColor', 'Row number', ROW, (p) => p.accent),
    C('faceBg', 'Photo backdrop', ROW, null, { autoLabel: 'Soft tint' }),
    C('faceBorder', 'Photo ring', ROW, (p) => p.accent),
    C('firstColor', 'First name', ROW, (p) => p.ink),
    C('nameColor', 'Surname', ROW, (p) => p.ink),
    C('statColor', 'Score line', ROW, (p) => p.accent),
    C('subColor', 'Grade and opposition', ROW, (p) => p.ink),
    ...FOOTER_PARTS,
  ],
  TW3: [
    T('title1', 'First word(s)', HEAD, () => 'TEAM OF'),
    C('title1Color', 'First word colour', HEAD, (p) => p.ink),
    T('title2', 'Second word(s)', HEAD, () => 'THE WEEK'),
    C('title2Color', 'Second word colour', HEAD, (p) => p.ink),
    C('roundColor', 'Round line', HEAD, (p) => p.accent),
    C('frameColor', 'Top and bottom bands', FOOT, (p) => p.accent),
    C('photoBg', 'Photo backdrop', CARD, null, { autoLabel: 'White' }),
    C('tabBg', 'Number tab', CARD, (p) => p.accent),
    C('numColor', 'Card number', CARD, (p) => p.primary),
    C('bandBg', 'Name band', CARD, (p) => p.accent),
    C('nameColor', 'Name', CARD, (p) => p.primary),
    C('panelBg', 'Score panel', CARD, null, { autoLabel: 'Dark' }),
    C('statColor', 'Score line', CARD, (p) => p.ink),
    C('pointsBg', 'Points tag', CARD, (p) => p.accent),
    C('pointsColor', 'Points text', CARD, (p) => p.primary),
  ],
})

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
function masthead({ pal, team, meta, width, big, parts }) {
  // `meta.heading` is 'JUNIOR' or 'SENIOR' on a scoped team and absent otherwise,
  // so an unscoped post stays byte for byte what it was.
  const round = [meta.heading, meta.round, meta.date].filter(Boolean).join(' · ')
  // `meta.basis` is 'round' on a team that counted games still in play and absent
  // otherwise; a heading the club typed wins over either.
  const title2 = meta.basis === 'round' ? 'THE ROUND' : 'THE WEEK'
  return (
    <div data-layer="Masthead" style={{
      position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 26px',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24, width,
      boxSizing: 'border-box',
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 3, color: pc(parts, 'roundColor', pal.accent), fontWeight: 600 }}>{`// ${round}`.toUpperCase()}</div>
        <div style={{ fontFamily: DISPLAY, fontSize: big, letterSpacing: -1, lineHeight: 0.86, marginTop: 8 }}>
          <span style={{ color: pc(parts, 'title1Color', pal.ink) }}>{pt(parts, 'title1', 'TEAM OF')}</span>
          {pt(parts, 'title1', 'TEAM OF') && pt(parts, 'title2', title2) ? ' ' : null}
          <span style={{ color: pc(parts, 'title2Color', pal.accent) }}>{pt(parts, 'title2', title2)}</span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0 }}>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: DISPLAY, fontSize: 28, letterSpacing: 0.5, lineHeight: 0.95, maxWidth: 240, color: pc(parts, 'clubColor', undefined) }}>{team.fullName || team.name}</div>
          {meta.comp ? <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1.6, opacity: 0.6, marginTop: 6 }}>{meta.comp}</div> : null}
        </div>
        <ClubLogo src={team.logo || null} monogram={team.monogram} color={pal.ink} size={104} shape="shield" />
      </div>
    </div>
  )
}

// The footer strip. The left is the sponsor slot, left empty for the grid; the
// platform credit sits at the right.
function footer({ pal, width, height, parts }) {
  return (
    <div data-layer="Sponsors" style={{
      position: 'absolute', left: 0, right: 0, bottom: 0, height: frame(width, height).strip, boxSizing: 'border-box',
      padding: '0 56px', display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
      background: pc(parts, 'footerBg', pal.primary), borderTop: `2px solid ${pc(parts, 'footerRule', pal.accent)}`,
    }}>
      <CreditMark ink={pal.ink} h={40} />
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TW1 — Team sheet: a grid of photo cards
// ═══════════════════════════════════════════════════════════════════════════
export function TeamOfWeekGrid({ palette: pal, width = 1080, height = 1080, team = {}, players = [], totw = {}, sponsors, parts }) {
  const texture = usePostLook().texture !== false
  const P = players.slice(0, TOTW_MAX)
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
  // The name band's text follows the band's colour once the club has set one, so
  // a white band does not keep the pale text the default red band had.
  const bandBg = pc(parts, 'bandBg', pal.accent)
  const nameInk = pc(parts, 'nameColor', pc(parts, 'bandBg', null) ? inkOn(bandBg) : pal.primary)
  const statInk = pc(parts, 'statColor', nameInk)
  const gradeInk = pc(parts, 'gradeColor', statInk)
  const cardBorder = pc(parts, 'cardBorder', pal.accent)
  const photoBg = pc(parts, 'photoBg', undefined)
  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: pal.primary, color: pal.ink, fontFamily: BODY,
    }}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.035} gap={28} angle={45} />
      {texture ? <div style={{ position: 'absolute', left: -50, bottom: F.strip + 64, fontFamily: DISPLAY, fontSize: 300, lineHeight: 0.8, color: pal.ink, opacity: 0.04, letterSpacing: -6, transform: 'rotate(-8deg)', userSelect: 'none', whiteSpace: 'nowrap' }}>TOTW</div> : null}
      {masthead({ pal, team, meta: totw, width, big, parts })}
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
              border: `2px solid ${cardBorder}`, display: 'flex', flexDirection: 'column',
            }}>
              <div style={{ flex: 1, position: 'relative', overflow: 'hidden', minHeight: 0, background: photoBg }}>
                <Halftone color={pal.ink} opacity={0.08} size={6} />
                <Face p={p} team={team} palette={pal} />
                <div style={{ position: 'absolute', top: 7, left: 9, fontFamily: MONO, fontSize: 11, color: pc(parts, 'numColor', pal.ink), opacity: 0.55, letterSpacing: 1.5 }}>#{String(i + 1).padStart(2, '0')}</div>
                {totw.showPoints && t.points != null ? (
                  <div style={{ position: 'absolute', top: 6, right: 6, padding: '2px 7px', background: pc(parts, 'pointsBg', pal.accent), color: pc(parts, 'pointsColor', pal.primary), fontFamily: DISPLAY, fontSize: 15, letterSpacing: 1, lineHeight: 1.2 }}>{t.points} PTS</div>
                ) : null}
              </div>
              <div style={{ height: bandH, background: bandBg, color: nameInk, padding: '0 10px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 3, boxSizing: 'border-box' }}>
                <AutoFitText text={p.last} max={nameMax} min={11} lines={1}
                  style={{ fontFamily: DISPLAY, letterSpacing: 1, lineHeight: 1, maxWidth: '100%', textAlign: 'center' }} />
                <Line text={t.line} size={lineSize} color={statInk} style={{ textAlign: 'center', fontWeight: 600 }} />
                {t.grade ? <Line text={t.grade} size={Math.max(9, lineSize - 2)} color={gradeInk} style={{ textAlign: 'center', opacity: 0.7 }} /> : null}
              </div>
            </div>
          )
        })}
      </div>
      {footer({ pal, width, height, parts })}
      <Grain opacity={0.32} id="tw1-g" />
    </LayerRoot>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TW2 — Ranked board: one row per player
// ═══════════════════════════════════════════════════════════════════════════
export function TeamOfWeekBoard({ palette: pal, width = 1080, height = 1080, team = {}, players = [], totw = {}, sponsors, parts }) {
  const texture = usePostLook().texture !== false
  const P = players.slice(0, TOTW_MAX)
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
      {texture ? <div style={{ position: 'absolute', left: -120, top: -80, width: 640, height: Math.round(height * 1.3), background: pal.secondary, transform: 'rotate(8deg)', transformOrigin: 'top left', opacity: 0.55 }} /> : null}
      {masthead({ pal, team, meta: totw, width, big, parts })}
      <div data-layer="Players" style={{
        position: 'absolute', left: 56, right: 56, top: F.top, bottom: F.bottom,
        display: 'flex', flexDirection: 'column', borderTop: `3px solid ${pc(parts, 'ruleColor', pal.accent)}`,
      }}>
        {n === 0 ? emptyState(pal) : null}
        {P.map((p, i) => {
          const t = p.totw || {}
          return (
            <div key={p._id || i} style={{
              flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', gap: 16,
              borderBottom: i < n - 1 ? `1px solid ${pc(parts, 'dividerColor', pal.ink)}${pc(parts, 'dividerColor', null) ? '' : '1f'}` : 'none',
            }}>
              <div style={{ width: numSize * 1.7, flexShrink: 0, fontFamily: DISPLAY, fontSize: numSize, letterSpacing: 0.5, color: pc(parts, 'numColor', pal.accent), lineHeight: 1 }}>{String(i + 1).padStart(2, '0')}</div>
              <div style={{ width: face, height: face, flexShrink: 0, position: 'relative', overflow: 'hidden', borderRadius: '50%', background: pc(parts, 'faceBg', `${pal.ink}14`), border: `2px solid ${pc(parts, 'faceBorder', pal.accent)}`, boxSizing: 'border-box' }}>
                <Face p={p} team={team} palette={pal} pos="center 12%" />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                {p.first ? <div style={{ fontFamily: DISPLAY, fontSize: firstSize, letterSpacing: 1.5, opacity: 0.7, lineHeight: 1, color: pc(parts, 'firstColor', undefined), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(p.first).toUpperCase()}</div> : null}
                <div style={{ fontFamily: DISPLAY, fontSize: nameSize, letterSpacing: 0.5, lineHeight: 1, color: pc(parts, 'nameColor', undefined), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.last}</div>
                {t.grade || t.opp ? (
                  <Line text={[t.grade, t.opp ? `v ${t.opp}` : ''].filter(Boolean).join(' · ')} size={subSize} color={pc(parts, 'subColor', pal.ink)} style={{ opacity: 0.6, marginTop: 2, letterSpacing: 1.2 }} />
                ) : null}
              </div>
              <div style={{ flexShrink: 0, textAlign: 'right', maxWidth: '38%' }}>
                <Line text={t.line} size={lineSize} color={pc(parts, 'statColor', pal.accent)} style={{ fontWeight: 700 }} />
                {totw.showPoints && t.points != null ? (
                  <div style={{ fontFamily: MONO, fontSize: subSize, letterSpacing: 1.5, opacity: 0.6, marginTop: 2 }}>{t.points} PTS</div>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
      {footer({ pal, width, height, parts })}
      <Grain opacity={0.3} id="tw2-g" />
    </LayerRoot>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TW3 — Round cards: crest and sponsor over the heading, white photo cards
// ═══════════════════════════════════════════════════════════════════════════
// A poster rather than a sheet: a patterned band top and bottom, the crest in the
// middle of the header with the round at its left and the sponsor at its right,
// a worn heading underneath, then white cards (number tab, photo, name band, a dark
// score panel). Colours come from the palette (`primary` ground, `accent` bands and
// tabs, `ink` type); the sponsor sits in its own slot at the right of the header.
const TW3_M = 54
const TW3_SCALLOP = 12
const tw3Band = (height) => grow(height, 34, 0.012)
const tw3Foot = (height) => grow(height, 46, 0.012)

function frame3(width, height) {
  const A = aspectOf(width, height)
  const band = tw3Band(height)
  const crest = pick(A, { square: 124, portrait: 142, story: 170 })
  const titleH = pick(A, { square: 72, portrait: 86, story: 104 })
  const crestTop = band + TW3_SCALLOP + 6
  const titleTop = crestTop + crest + 10
  const foot = tw3Foot(height)
  return { A, band, crest, titleH, crestTop, titleTop, top: titleTop + titleH + 14, foot, bottom: foot + 22 }
}

// The sponsor's room: the right of the header, as tall as the crest and heading
// together. It is one rectangle whatever the count, because the grid fits its
// logos inside it. `slotTW3` is the one function the layout and SPONSOR_SLOTS share.
const TW3_SLOT_W = 190
function slotTW3(width = 1080, height = 1080) {
  const F = frame3(width, height)
  const y = F.crestTop - 2
  return { x: width - TW3_M - TW3_SLOT_W, y, w: TW3_SLOT_W, h: F.top - 14 - y, pad: 0, gap: 12, panel: 'none' }
}

// The scuffed look of the heading: a mask with small holes and a few scratches
// punched out of it, drawn once from a fixed seed so the post is the same every
// time it is drawn and exported. A mask (not a filter) because the PNG export
// paints masks.
const DISTRESS_MASK = (() => {
  let seed = 20260
  const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296 }
  const W = 1000, H = 120
  let d = `M0 0H${W}V${H}H0Z`
  for (let i = 0; i < 300; i++) {
    const x = rnd() * W, y = rnd() * H, r = 0.7 + rnd() * rnd() * 5.5
    d += `M${(x - r).toFixed(1)} ${y.toFixed(1)}a${r.toFixed(1)} ${r.toFixed(1)} 0 1 0 ${(2 * r).toFixed(1)} 0a${r.toFixed(1)} ${r.toFixed(1)} 0 1 0 ${(-2 * r).toFixed(1)} 0Z`
  }
  for (let i = 0; i < 16; i++) {
    const x = rnd() * W, y = rnd() * H, w = 18 + rnd() * 80
    d += `M${x.toFixed(1)} ${y.toFixed(1)}h${w.toFixed(1)}v${(1 + rnd() * 1.6).toFixed(1)}h${(-w).toFixed(1)}Z`
  }
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 ${W} ${H}' preserveAspectRatio='none'><path fill-rule='evenodd' d='${d}'/></svg>`
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`
})()

// "202* (150)" becomes "202* RUNS", "2/19 (4)" becomes "2/19": the card says what
// happened, the balls and overs stay on the scorecard. Anything else (a line the
// club typed, "2 ct") is printed as it is.
export function cardStat(line) {
  return String(line || '').split('·').map((seg) => {
    const t = seg.trim()
    const bat = /^(\d+\*?)\s*\(\d+\)$/.exec(t)
    if (bat) return `${bat[1]} RUNS`
    return t.replace(/\s*\([\d.]+\)$/, '')
  }).filter(Boolean).join(' · ').toUpperCase()
}

const DOTS = 'rgba(0,0,0,0.2)'
function bandDots(texture) {
  return texture ? {
    backgroundImage: `radial-gradient(circle at 50% 50%, ${DOTS} 0 3px, transparent 3.5px), radial-gradient(circle at 50% 50%, ${DOTS} 0 3px, transparent 3.5px)`,
    backgroundSize: '24px 24px', backgroundPosition: '0 0, 12px 12px',
  } : {}
}

// Plain functions returning their root `div` (a component child only takes a
// z-index if it spreads `style`).
function topBand({ pal, width, F, parts, texture }) {
  const c = pc(parts, 'frameColor', pal.accent)
  return (
    <div data-layer="Top band" style={{ position: 'absolute', left: 0, top: 0, width, height: F.band + TW3_SCALLOP }}>
      <div style={{ height: F.band, background: c, ...bandDots(texture) }} />
      <div style={{ height: TW3_SCALLOP, backgroundImage: `radial-gradient(circle at 50% 0, ${c} 0 11.5px, transparent 12px)`, backgroundSize: '24px 12px', backgroundRepeat: 'repeat-x' }} />
    </div>
  )
}

function bottomBand({ pal, width, F, parts, texture }) {
  const c = pc(parts, 'frameColor', pal.accent)
  return (
    <div data-layer="Footer" style={{ position: 'absolute', left: 0, bottom: 0, width, height: F.foot + TW3_SCALLOP }}>
      <div style={{ height: TW3_SCALLOP, backgroundImage: `radial-gradient(circle at 50% 100%, ${c} 0 11.5px, transparent 12px)`, backgroundSize: '24px 12px', backgroundRepeat: 'repeat-x' }} />
      <div style={{ height: F.foot, background: c, ...bandDots(texture), position: 'relative' }}>
        <div style={{ position: 'absolute', right: TW3_M, top: '50%', transform: 'translateY(-50%)', padding: '3px 10px', background: c, display: 'flex', alignItems: 'center' }}>
          <CreditMark ink={inkOn(c)} h={Math.round(F.foot * 0.5)} />
        </div>
      </div>
    </div>
  )
}

export function TeamOfWeekCards({ palette: pal, width = 1080, height = 1080, team = {}, players = [], totw = {}, sponsors, parts }) {
  const texture = usePostLook().texture !== false
  const P = players.slice(0, TOTW_MAX)
  const n = P.length
  const F = frame3(width, height)
  const cols = totwColumns(n)
  const rows = Math.max(1, Math.ceil(n / cols))
  const gap = 14
  const gridW = width - TW3_M * 2
  const gridH = height - F.top - F.bottom
  const cardW = Math.floor((gridW - gap * (cols - 1)) / cols)
  const cardH = Math.floor((gridH - gap * (rows - 1)) / rows)
  const radius = 14
  // Everything on a card is sized from the card, so a 5-wide card of fourteen is
  // not set like a 3-wide card of six.
  const bandH = Math.max(28, Math.min(46, Math.round(cardH * 0.125)))
  const statH = Math.max(36, Math.min(72, Math.round(cardH * 0.19)))
  const tabW = Math.max(34, Math.min(62, Math.round(cardW * 0.2)))
  const tabH = Math.round(tabW * 0.92)
  const nameMax = Math.max(11, Math.min(22, Math.round(cardW * 0.08)))
  const statMax = Math.max(13, Math.min(30, Math.round(cardW * 0.115)))
  const titleW = width - TW3_M * 2 - TW3_SLOT_W - 24
  const leftW = Math.floor((width - F.crest) / 2) - TW3_M - 24
  const roundSize = pick(F.A, { square: 76, portrait: 88, story: 104 })
  const round = String(totw.round || '').toUpperCase()
  const kicker = [totw.heading, totw.date, totw.comp].filter(Boolean).join(' · ').toUpperCase()
  const title2Default = totw.basis === 'round' ? 'THE ROUND' : 'THE WEEK'
  const t1 = pt(parts, 'title1', 'TEAM OF'), t2 = pt(parts, 'title2', title2Default)
  const bandBg = pc(parts, 'bandBg', pal.accent)
  const nameInk = pc(parts, 'nameColor', pc(parts, 'bandBg', null) ? inkOn(bandBg) : pal.primary)
  const photoBg = pc(parts, 'photoBg', '#ffffff')
  const panelBg = pc(parts, 'panelBg', null)
  const tabBg = pc(parts, 'tabBg', pal.accent)
  const numInk = pc(parts, 'numColor', pc(parts, 'tabBg', null) ? inkOn(tabBg) : pal.primary)
  const statInk = pc(parts, 'statColor', panelBg ? inkOn(panelBg) : pal.ink)
  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: pal.primary, color: pal.ink, fontFamily: BODY,
    }}>
      <Halftone color={pal.ink} opacity={0.04} size={9} />
      {topBand({ pal, width, F, parts, texture })}
      <div data-layer="Round" style={{
        position: 'absolute', left: TW3_M, top: F.crestTop, width: leftW, height: F.crest,
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 6,
      }}>
        {kicker ? <div style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 3, fontWeight: 600, opacity: 0.75, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{kicker}</div> : null}
        {round ? (
          <AutoFitText text={round} max={roundSize} min={24}
            style={{ fontFamily: DISPLAY, letterSpacing: 1, lineHeight: 0.92, color: pc(parts, 'roundColor', pal.accent) }} />
        ) : null}
      </div>
      <div data-layer="Club crest" style={{ position: 'absolute', left: Math.round((width - F.crest) / 2), top: F.crestTop, width: F.crest, height: F.crest }}>
        <ClubLogo src={team.logo || null} monogram={team.monogram} color={pal.ink} size={F.crest} shape="shield" />
      </div>
      <div data-layer="Title" style={{
        position: 'absolute', left: TW3_M, top: F.titleTop, width: titleW, height: F.titleH,
        ...(texture ? { WebkitMaskImage: DISTRESS_MASK, maskImage: DISTRESS_MASK, WebkitMaskSize: '100% 100%', maskSize: '100% 100%' } : null),
      }}>
        <AutoFitText max={Math.round(F.titleH * 1.15)} min={20} text={`${t1} ${t2}`} measureDeps={[t1, t2]}
          style={{ fontFamily: DISPLAY, letterSpacing: 3, lineHeight: 0.85, textTransform: 'uppercase' }}>
          <span style={{ color: pc(parts, 'title1Color', pal.ink) }}>{t1}</span>
          {t1 && t2 ? ' ' : null}
          <span style={{ color: pc(parts, 'title2Color', pal.ink) }}>{t2}</span>
        </AutoFitText>
      </div>
      <div data-layer="Players" style={{
        position: 'absolute', left: TW3_M, right: TW3_M, top: F.top, bottom: F.bottom,
        display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignContent: 'flex-start', gap,
      }}>
        {n === 0 ? emptyState(pal) : null}
        {P.map((p, i) => {
          const t = p.totw || {}
          const name = [p.first, p.last].filter(Boolean).join(' ').toUpperCase()
          return (
            <div key={p._id || i} style={{
              width: cardW, height: cardH, position: 'relative', overflow: 'hidden', boxSizing: 'border-box',
              borderRadius: radius, background: photoBg, display: 'flex', flexDirection: 'column',
            }}>
              <div style={{ flex: 1, position: 'relative', overflow: 'hidden', minHeight: 0 }}>
                <Face p={p} team={team} palette={pal} pos="center bottom" />
                <div style={{
                  position: 'absolute', top: 0, left: 0, width: tabW, height: tabH, display: 'grid', placeItems: 'center',
                  background: tabBg, color: numInk, borderBottomRightRadius: 12,
                  fontFamily: DISPLAY, fontSize: Math.round(tabH * 0.62), lineHeight: 1,
                }}>{i + 1}</div>
                {totw.showPoints && t.points != null ? (
                  <div style={{ position: 'absolute', top: 0, right: 0, padding: '3px 8px', borderBottomLeftRadius: 10, background: pc(parts, 'pointsBg', pal.accent), color: pc(parts, 'pointsColor', pal.primary), fontFamily: DISPLAY, fontSize: 15, letterSpacing: 1, lineHeight: 1.2 }}>{t.points} PTS</div>
                ) : null}
              </div>
              <div style={{ height: bandH, background: bandBg, color: nameInk, padding: '0 8px', display: 'flex', flexDirection: 'column', justifyContent: 'center', boxSizing: 'border-box' }}>
                <AutoFitText text={name} max={nameMax} min={8} measureDeps={[cardW]}
                  style={{ fontFamily: BODY, fontWeight: 600, letterSpacing: 0.8, lineHeight: 1.1, textAlign: 'center' }} />
              </div>
              <div style={{
                height: statH, color: statInk, padding: '0 8px', display: 'flex', flexDirection: 'column', justifyContent: 'center', boxSizing: 'border-box',
                ...(panelBg ? { background: panelBg } : { backgroundColor: pal.primary, backgroundImage: 'linear-gradient(rgba(0,0,0,0.34), rgba(0,0,0,0.34))' }),
              }}>
                <AutoFitText text={cardStat(t.line)} max={statMax} min={9} measureDeps={[cardW]}
                  style={{ fontFamily: BODY, fontWeight: 600, letterSpacing: 1, lineHeight: 1.1, textAlign: 'center' }} />
              </div>
            </div>
          )
        })}
      </div>
      {bottomBand({ pal, width, F, parts, texture })}
      <Grain opacity={0.45} id="tw3-g" />
    </LayerRoot>
  )
}

TeamOfWeekGrid.displayName = 'TeamOfWeekGrid'
TeamOfWeekBoard.displayName = 'TeamOfWeekBoard'
TeamOfWeekCards.displayName = 'TeamOfWeekCards'
Line.displayName = 'Line'
Face.displayName = 'Face'

// Where this file's layouts keep the sponsor grid (see sponsorSlots.js).
export const SPONSOR_SLOTS = { TW1: slotTW, TW2: slotTW, TW3: slotTW3 }

// The milestone layouts (milestone-templates.jsx) are built on the same frame: a
// masthead, a body and the sponsor strip along the foot. One definition of the
// strip and the face, so the two post types cannot drift apart.
export { slotTW, frame as bandFrame, footer as bandFooter, Face as PlayerFace, Line as StatLine }
