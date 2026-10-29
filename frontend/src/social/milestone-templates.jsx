// Player milestones — one post that celebrates a handful of them.
//
// The club ticks the milestones it wants to feature (a 100th game, 1,000 career
// runs, a 50th wicket) and the layout is given exactly those, so unlike the
// lineup layouts it does not draw a fixed number of slots: the grid picks its
// columns from the count and the board splits its height by it. Whatever the
// count, the cards fill the body and a ragged last row is centred.
//
// Same frame as the team of the week (totw-templates.jsx): a masthead, a body and
// the sponsor strip, on the club palette and display font, every element a layer.
import { GrainSVG as Grain, Halftone, Stripes, ClubLogo, AutoFitText } from './cricket-templates'
import { aspectOf, pick } from './postAspect'
import { LayerRoot } from './postLayers'
import { slotTW, bandFrame, bandFooter, PlayerFace as Face } from './totw-templates'
import { pc, pt, inkOn, registerParts, colorPart, textPart, picked as partPicked } from './layoutParts'
import { usePostLook } from './postLook'

const DISPLAY = "var(--social-display-font, 'Anton', sans-serif)"
const MONO = "'JetBrains Mono', monospace"
const BODY = "'Inter', sans-serif"

export const MILESTONE_MAX = 12

// Columns for the grid of `n` cards. A square post wants more columns than a
// tall one, which spends its height on rows instead.
const COLS_SQUARE = [1, 1, 2, 3, 2, 3, 3, 4, 4, 3, 4, 4, 4]
const COLS_TALL = [1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3]
export function milestoneColumns(n, aspect = 'square') {
  const i = Math.max(0, Math.min(MILESTONE_MAX, n))
  return (aspect === 'square' ? COLS_SQUARE : COLS_TALL)[i]
}

// What the body shows before any milestone is ticked, so an empty post says what
// to do rather than sitting blank.
function emptyState(pal) {
  return (
    <div style={{ flex: 1, display: 'grid', placeItems: 'center', border: `2px dashed ${pal.ink}33`, fontFamily: DISPLAY, fontSize: 34, letterSpacing: 2, color: pal.ink, opacity: 0.6, textAlign: 'center', padding: 24, width: '100%', boxSizing: 'border-box' }}>
      TICK THE MILESTONES TO FEATURE
    </div>
  )
}

// A player with no photo shows the club crest. On a card the number and unit sit
// over the lower part of the picture, so the crest is lifted into the top of it
// and kept off the figures; on a card too short to leave it any room it is left
// out (the club is on the masthead). A beside-the-text card has nothing over it.
function CardFace({ m, team, pal, lifted, room }) {
  if (m.headshot || !lifted) return <Face p={m} team={team} palette={pal} />
  if (room < 190) return null
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, top: '5%', height: '34%', display: 'grid', placeItems: 'center' }}>
      {team.logo
        ? <img src={team.logo} alt={team.short || 'club'} style={{ maxWidth: '58%', maxHeight: '100%', objectFit: 'contain', opacity: 0.85 }} />
        : <div style={{ fontFamily: DISPLAY, fontSize: 48, color: pal.accent, opacity: 0.85, letterSpacing: -1, lineHeight: 1 }}>{team.monogram || '?'}</div>}
    </div>
  )
}

// Plain function returning its root `div`, called inline, so it takes a z-index.
function masthead({ pal, team, meta, width, big, parts }) {
  const sub = [meta.round, meta.date].filter(Boolean).join(' · ')
  return (
    <div data-layer="Masthead" style={{
      position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 26px',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24, width,
      boxSizing: 'border-box',
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 3, color: pc(parts, 'roundColor', pal.accent), fontWeight: 600 }}>{`// ${sub || 'CLUB MILESTONES'}`.toUpperCase()}</div>
        <div style={{ fontFamily: DISPLAY, fontSize: big, letterSpacing: -1, lineHeight: 0.86, marginTop: 8, color: pc(parts, 'title1Color', undefined) }}>
          {meta.title ? String(meta.title).toUpperCase() : <>MILE<span style={{ color: pc(parts, 'title2Color', pal.accent) }}>STONES</span></>}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0 }}>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: DISPLAY, fontSize: 28, letterSpacing: 0.5, lineHeight: 0.95, maxWidth: 240, color: pc(parts, 'clubColor', undefined) }}>{team.fullName || team.name}</div>
          {meta.comp ? <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: 1.6, opacity: 0.6, marginTop: 6, color: pc(parts, 'compColor', undefined) }}>{meta.comp}</div> : null}
        </div>
        <ClubLogo src={team.logo || null} monogram={team.monogram} color={pal.ink} size={104} shape="shield" />
      </div>
    </div>
  )
}

const dateLine = (m) => [m.detail, m.dateLabel].filter(Boolean).join(' · ')

// ═══════════════════════════════════════════════════════════════════════════
// MS1 — Milestone cards: photo, the big number, the name
// ═══════════════════════════════════════════════════════════════════════════
export function MilestoneCards({ palette: pal, width = 1080, height = 1080, team = {}, milestones = [], milestoneMeta = {}, parts }) {
  const M = milestones.slice(0, MILESTONE_MAX)
  const n = M.length
  const F = bandFrame(width, height)
  const cols = milestoneColumns(n, F.A)
  const rows = Math.max(1, Math.ceil(n / cols))
  const gap = 14
  const gridW = width - 112
  const gridH = height - F.top - F.bottom
  const cardW = Math.floor((gridW - gap * (cols - 1)) / cols)
  const cardH = Math.floor((gridH - gap * (rows - 1)) / rows)
  // A wide card (one or two milestones on a square, or any single column) puts the
  // photo beside the text; a tall one stacks them.
  const wide = cardW > cardH * 1.15
  const short = Math.min(cardW, cardH)
  const bandH = Math.max(70, Math.min(116, Math.round(cardH * 0.3)))
  const nameMax = Math.max(18, Math.min(44, Math.round((wide ? cardH : cardW) * 0.16)))
  const unitSize = Math.max(11, Math.min(19, Math.round(short * 0.058)))
  const firstSize = Math.max(11, Math.round(nameMax * 0.42))
  // A wide card stacks the unit, the number, the date and the name band inside the card's own
  // height, so the number gets what the rest leaves it. Sized off the card alone it could ask
  // for more than that and push the name band out of the bottom of the card.
  const wideBandH = 28 + firstSize + 2 + nameMax
  const wideInfoRoom = cardH - wideBandH - 28 - Math.round(unitSize * 1.5) - Math.round((unitSize - 3) * 1.5) - 8
  const valueMax = wide
    ? Math.max(28, Math.min(Math.round(cardH * 0.46), Math.floor(wideInfoRoom / 0.95)))
    : Math.round(cardW * 0.4)
  const big = pick(F.A, { square: 78, portrait: 90, story: 104 })
  // The name band's text follows the band's colour once the club has set one, so a
  // white band does not keep the pale text the default band had.
  const bandBg = pc(parts, 'bandBg', pal.accent)
  const nameInk = pc(parts, 'nameColor', partPicked(parts, 'bandBg') ? inkOn(bandBg) : pal.primary)
  // The fade at the foot of a stacked photo runs into the card, so it follows a picked card colour.
  const fade = pc(parts, 'cardBg', pal.primary)
  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: pal.primary, color: pal.ink, fontFamily: BODY,
    }}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.035} gap={28} angle={45} />
      {masthead({ pal, team, meta: milestoneMeta, width, big, parts })}
      <div data-layer="Milestones" style={{
        position: 'absolute', left: 56, right: 56, top: F.top, bottom: F.bottom,
        display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignContent: 'flex-start', gap,
      }}>
        {n === 0 ? emptyState(pal) : null}
        {M.map((m, i) => {
          const info = (
            <>
              <div style={{ fontFamily: MONO, fontSize: unitSize, letterSpacing: 2, color: pc(parts, 'unitColor', pal.accent), fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(m.unit || '').toUpperCase()}</div>
              <AutoFitText text={m.value} max={valueMax} min={28} lines={1}
                style={{ fontFamily: DISPLAY, letterSpacing: -1, lineHeight: 0.95, color: pc(parts, 'numColor', pal.ink), maxWidth: '100%' }} />
              {dateLine(m) ? <div style={{ fontFamily: MONO, fontSize: Math.max(10, unitSize - 3), letterSpacing: 1.2, opacity: 0.6, color: pc(parts, 'subColor', undefined), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{dateLine(m).toUpperCase()}</div> : null}
            </>
          )
          const nameBand = (
            <div style={{ height: wide ? undefined : bandH, flexShrink: 0, background: bandBg, color: nameInk, padding: wide ? '14px 18px' : '0 12px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 2, boxSizing: 'border-box', minWidth: 0 }}>
              {m.first ? (
                <AutoFitText text={String(m.first).toUpperCase()} max={firstSize} min={9} lines={1}
                  style={{ fontFamily: DISPLAY, letterSpacing: 1.5, opacity: 0.75, lineHeight: 1, color: pc(parts, 'firstColor', undefined), maxWidth: '100%', textAlign: wide ? 'left' : 'center' }} />
              ) : null}
              <AutoFitText text={m.last} max={nameMax} min={12} lines={1}
                style={{ fontFamily: DISPLAY, letterSpacing: 1, lineHeight: 1, maxWidth: '100%', textAlign: wide ? 'left' : 'center' }} />
            </div>
          )
          return (
            <div key={m.key || i} style={{
              width: cardW, height: cardH, position: 'relative', overflow: 'hidden', boxSizing: 'border-box',
              background: pc(parts, 'cardBg', `linear-gradient(180deg, ${pal.secondary} 0%, ${pal.primary} 100%)`),
              border: `2px solid ${pc(parts, 'cardBorder', pal.accent)}`, display: 'flex', flexDirection: wide ? 'row' : 'column',
            }}>
              <div style={{ flex: wide ? '0 0 42%' : 1, position: 'relative', overflow: 'hidden', minHeight: 0, minWidth: 0, background: pc(parts, 'photoBg', undefined) }}>
                <Halftone color={pal.ink} opacity={0.08} size={6} />
                <CardFace m={m} team={team} pal={pal} lifted={!wide} room={cardH - bandH} />
                {!wide ? (
                  <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '28px 12px 8px', background: `linear-gradient(0deg, ${fade} 0%, ${fade}00 100%)`, display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0, boxSizing: 'border-box' }}>{info}</div>
                ) : null}
              </div>
              {wide ? (
                <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                  <div style={{ flex: 1, padding: '14px 18px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 4, minWidth: 0, minHeight: 0, overflow: 'hidden', boxSizing: 'border-box' }}>{info}</div>
                  {nameBand}
                </div>
              ) : nameBand}
            </div>
          )
        })}
      </div>
      {bandFooter({ pal, width, height, parts })}
      <Grain opacity={0.32} id="ms1-g" />
    </LayerRoot>
  )
}

// What the club can set on the milestone layouts (Brand). Same keys on both, so a heading or a
// name colour carries from the cards to the board. The heading is the masthead both share; the
// post's title itself is typed in the editor, so it is a colour here and not a text part.
const M_HEAD = 'Heading', M_CARD = 'Milestone cards', M_ROW = 'Milestone rows', M_FOOT = 'Footer'
const mastheadParts = () => [
  colorPart('roundColor', 'Round line', M_HEAD, (p) => p.accent),
  colorPart('title1Color', 'Heading', M_HEAD, (p) => p.ink),
  colorPart('title2Color', 'Second half of the heading (MILESTONES)', M_HEAD, (p) => p.accent),
  colorPart('clubColor', 'Club name', M_HEAD, (p) => p.ink),
  colorPart('compColor', 'Competition line', M_HEAD, (p) => p.ink),
]
const footerParts = () => [
  colorPart('footerBg', 'Footer bar', M_FOOT, (p) => p.primary),
  colorPart('footerRule', 'Footer line', M_FOOT, (p) => p.accent),
]
registerParts({
  MS1: [
    ...mastheadParts(),
    colorPart('cardBg', 'Card colour', M_CARD, null, { autoLabel: 'Club colour fade' }),
    colorPart('cardBorder', 'Card outline', M_CARD, (p) => p.accent),
    colorPart('photoBg', 'Photo backdrop', M_CARD, null, { autoLabel: 'Card colour' }),
    colorPart('unitColor', 'What it is for (Career runs, Club games)', M_CARD, (p) => p.accent),
    colorPart('numColor', 'Big number', M_CARD, (p) => p.ink),
    colorPart('subColor', 'Date line', M_CARD, (p) => p.ink),
    colorPart('bandBg', 'Name band', M_CARD, (p) => p.accent),
    colorPart('firstColor', 'First name', M_CARD, (p) => p.primary),
    colorPart('nameColor', 'Surname', M_CARD, (p) => p.primary),
    ...footerParts(),
  ],
})

// ═══════════════════════════════════════════════════════════════════════════
// MS2 — Milestone board: one row per milestone, the number first
// ═══════════════════════════════════════════════════════════════════════════
export function MilestoneBoard({ palette: pal, width = 1080, height = 1080, team = {}, milestones = [], milestoneMeta = {}, parts }) {
  const M = milestones.slice(0, MILESTONE_MAX)
  const n = M.length
  const F = bandFrame(width, height)
  const rowH = (height - F.top - F.bottom) / Math.max(1, n)
  // Everything in a row is sized off the row's own height, so 3 milestones get big
  // type and 12 get tight type on the same layout.
  const face = Math.max(34, Math.min(104, Math.round(rowH - 12)))
  const nameSize = Math.max(20, Math.min(44, Math.round(rowH * 0.46)))
  const firstSize = Math.max(11, Math.min(20, Math.round(rowH * 0.22)))
  const valueSize = Math.max(26, Math.min(88, Math.round(rowH * 0.66)))
  const unitSize = Math.max(10, Math.min(18, Math.round(rowH * 0.2)))
  // Tight rows (eight or more on a square) cannot stack first name, surname and
  // unit; the first name moves onto the surname's line instead.
  const tight = rowH < 76
  const big = pick(F.A, { square: 78, portrait: 90, story: 104 })
  const texture = usePostLook().texture !== false
  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: pal.primary, color: pal.ink, fontFamily: BODY,
    }}>
      <Halftone color={pal.ink} opacity={0.05} size={12} />
      {texture ? <div style={{ position: 'absolute', left: -120, top: -80, width: 640, height: Math.round(height * 1.3), background: pal.secondary, transform: 'rotate(8deg)', transformOrigin: 'top left', opacity: 0.55 }} /> : null}
      {masthead({ pal, team, meta: milestoneMeta, width, big, parts })}
      <div data-layer="Milestones" style={{
        position: 'absolute', left: 56, right: 56, top: F.top, bottom: F.bottom,
        display: 'flex', flexDirection: 'column', borderTop: `3px solid ${pc(parts, 'ruleColor', pal.accent)}`,
      }}>
        {n === 0 ? emptyState(pal) : null}
        {M.map((m, i) => (
          <div key={m.key || i} style={{
            flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', gap: 18,
            borderBottom: i < n - 1 ? `1px solid ${pc(parts, 'dividerColor', pal.ink)}${pc(parts, 'dividerColor', null) ? '' : '1f'}` : 'none',
          }}>
            <div style={{ width: '24%', flexShrink: 0, minWidth: 0 }}>
              <AutoFitText text={m.value} max={valueSize} min={20} lines={1}
                style={{ fontFamily: DISPLAY, letterSpacing: -0.5, lineHeight: 1, color: pc(parts, 'numColor', pal.accent), maxWidth: '100%' }} />
            </div>
            <div style={{ width: face, height: face, flexShrink: 0, position: 'relative', overflow: 'hidden', borderRadius: '50%', background: pc(parts, 'faceBg', `${pal.ink}14`), border: `2px solid ${pc(parts, 'faceBorder', pal.accent)}`, boxSizing: 'border-box' }}>
              <Face p={m} team={team} palette={pal} pos="center 12%" />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              {m.first && !tight ? <div style={{ fontFamily: DISPLAY, fontSize: firstSize, letterSpacing: 1.5, opacity: 0.7, lineHeight: 1, color: pc(parts, 'firstColor', undefined), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(m.first).toUpperCase()}</div> : null}
              <div style={{ fontFamily: DISPLAY, fontSize: nameSize, letterSpacing: 0.5, lineHeight: 1, color: pc(parts, 'nameColor', undefined), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {m.first && tight ? <span style={{ fontSize: Math.round(nameSize * 0.62), letterSpacing: 1.5, opacity: 0.7, marginRight: 8, color: pc(parts, 'firstColor', undefined) }}>{String(m.first).toUpperCase()}</span> : null}{m.last}
              </div>
              <div style={{ fontFamily: MONO, fontSize: unitSize, letterSpacing: 1.4, color: pc(parts, 'unitColor', pal.accent), fontWeight: 700, marginTop: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(m.unit || '').toUpperCase()}{m.dateLabel ? <span style={{ color: pc(parts, 'subColor', pal.ink), opacity: 0.55, fontWeight: 400 }}>{` · ${m.dateLabel}`.toUpperCase()}</span> : null}</div>
            </div>
          </div>
        ))}
      </div>
      {bandFooter({ pal, width, height, parts })}
      <Grain opacity={0.3} id="ms2-g" />
    </LayerRoot>
  )
}
registerParts({
  MS2: [
    ...mastheadParts(),
    colorPart('ruleColor', 'Top line', M_ROW, (p) => p.accent),
    colorPart('dividerColor', 'Row dividers', M_ROW, (p) => p.ink),
    colorPart('numColor', 'Big number', M_ROW, (p) => p.accent),
    colorPart('faceBg', 'Photo backdrop', M_ROW, null, { autoLabel: 'Soft tint' }),
    colorPart('faceBorder', 'Photo ring', M_ROW, (p) => p.accent),
    colorPart('firstColor', 'First name', M_ROW, (p) => p.ink),
    colorPart('nameColor', 'Surname', M_ROW, (p) => p.ink),
    colorPart('unitColor', 'What it is for (Career runs, Club games)', M_ROW, (p) => p.accent),
    colorPart('subColor', 'Date', M_ROW, (p) => p.ink),
    ...footerParts(),
  ],
})

CardFace.displayName = 'CardFace'
MilestoneCards.displayName = 'MilestoneCards'
MilestoneBoard.displayName = 'MilestoneBoard'

// Where this file's layouts keep the sponsor grid (see sponsorSlots.js). The
// strip is the team of the week's, so the room kept is the same.
export const SPONSOR_SLOTS = { MS1: slotTW, MS2: slotTW }
