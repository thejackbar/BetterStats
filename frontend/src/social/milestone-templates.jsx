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
function masthead({ pal, team, meta, width, big }) {
  const sub = [meta.round, meta.date].filter(Boolean).join(' · ')
  return (
    <div data-layer="Masthead" style={{
      position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 26px',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24, width,
      boxSizing: 'border-box',
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 3, color: pal.accent, fontWeight: 600 }}>{`// ${sub || 'CLUB MILESTONES'}`.toUpperCase()}</div>
        <div style={{ fontFamily: DISPLAY, fontSize: big, letterSpacing: -1, lineHeight: 0.86, marginTop: 8 }}>
          {meta.title ? String(meta.title).toUpperCase() : <>MILE<span style={{ color: pal.accent }}>STONES</span></>}
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

const dateLine = (m) => [m.detail, m.dateLabel].filter(Boolean).join(' · ')

// ═══════════════════════════════════════════════════════════════════════════
// MS1 — Milestone cards: photo, the big number, the name
// ═══════════════════════════════════════════════════════════════════════════
export function MilestoneCards({ palette: pal, width = 1080, height = 1080, team = {}, milestones = [], milestoneMeta = {} }) {
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
  const valueMax = wide ? Math.round(cardH * 0.46) : Math.round(cardW * 0.4)
  const big = pick(F.A, { square: 78, portrait: 90, story: 104 })
  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: pal.primary, color: pal.ink, fontFamily: BODY,
    }}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.035} gap={28} angle={45} />
      {masthead({ pal, team, meta: milestoneMeta, width, big })}
      <div data-layer="Milestones" style={{
        position: 'absolute', left: 56, right: 56, top: F.top, bottom: F.bottom,
        display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignContent: 'flex-start', gap,
      }}>
        {n === 0 ? emptyState(pal) : null}
        {M.map((m, i) => {
          const info = (
            <>
              <div style={{ fontFamily: MONO, fontSize: unitSize, letterSpacing: 2, color: pal.accent, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(m.unit || '').toUpperCase()}</div>
              <AutoFitText text={m.value} max={valueMax} min={28} lines={1}
                style={{ fontFamily: DISPLAY, letterSpacing: -1, lineHeight: 0.95, color: pal.ink, maxWidth: '100%' }} />
              {dateLine(m) ? <div style={{ fontFamily: MONO, fontSize: Math.max(10, unitSize - 3), letterSpacing: 1.2, opacity: 0.6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{dateLine(m).toUpperCase()}</div> : null}
            </>
          )
          const nameBand = (
            <div style={{ height: wide ? undefined : bandH, flexShrink: 0, background: pal.accent, color: pal.primary, padding: wide ? '14px 18px' : '0 12px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 2, boxSizing: 'border-box', minWidth: 0 }}>
              {m.first ? <div style={{ fontFamily: DISPLAY, fontSize: Math.max(11, Math.round(nameMax * 0.42)), letterSpacing: 1.5, opacity: 0.75, lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textAlign: wide ? 'left' : 'center' }}>{String(m.first).toUpperCase()}</div> : null}
              <AutoFitText text={m.last} max={nameMax} min={12} lines={1}
                style={{ fontFamily: DISPLAY, letterSpacing: 1, lineHeight: 1, maxWidth: '100%', textAlign: wide ? 'left' : 'center' }} />
            </div>
          )
          return (
            <div key={m.key || i} style={{
              width: cardW, height: cardH, position: 'relative', overflow: 'hidden', boxSizing: 'border-box',
              background: `linear-gradient(180deg, ${pal.secondary} 0%, ${pal.primary} 100%)`,
              border: `2px solid ${pal.accent}`, display: 'flex', flexDirection: wide ? 'row' : 'column',
            }}>
              <div style={{ flex: wide ? '0 0 42%' : 1, position: 'relative', overflow: 'hidden', minHeight: 0, minWidth: 0 }}>
                <Halftone color={pal.ink} opacity={0.08} size={6} />
                <CardFace m={m} team={team} pal={pal} lifted={!wide} room={cardH - bandH} />
                {!wide ? (
                  <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '28px 12px 8px', background: `linear-gradient(0deg, ${pal.primary} 0%, ${pal.primary}00 100%)`, display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0, boxSizing: 'border-box' }}>{info}</div>
                ) : null}
              </div>
              {wide ? (
                <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                  <div style={{ flex: 1, padding: '14px 18px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 4, minWidth: 0, boxSizing: 'border-box' }}>{info}</div>
                  {nameBand}
                </div>
              ) : nameBand}
            </div>
          )
        })}
      </div>
      {bandFooter({ pal, width, height })}
      <Grain opacity={0.32} id="ms1-g" />
    </LayerRoot>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// MS2 — Milestone board: one row per milestone, the number first
// ═══════════════════════════════════════════════════════════════════════════
export function MilestoneBoard({ palette: pal, width = 1080, height = 1080, team = {}, milestones = [], milestoneMeta = {} }) {
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
  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: pal.primary, color: pal.ink, fontFamily: BODY,
    }}>
      <Halftone color={pal.ink} opacity={0.05} size={12} />
      <div style={{ position: 'absolute', left: -120, top: -80, width: 640, height: Math.round(height * 1.3), background: pal.secondary, transform: 'rotate(8deg)', transformOrigin: 'top left', opacity: 0.55 }} />
      {masthead({ pal, team, meta: milestoneMeta, width, big })}
      <div data-layer="Milestones" style={{
        position: 'absolute', left: 56, right: 56, top: F.top, bottom: F.bottom,
        display: 'flex', flexDirection: 'column', borderTop: `3px solid ${pal.accent}`,
      }}>
        {n === 0 ? emptyState(pal) : null}
        {M.map((m, i) => (
          <div key={m.key || i} style={{
            flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', gap: 18,
            borderBottom: i < n - 1 ? `1px solid ${pal.ink}1f` : 'none',
          }}>
            <div style={{ width: '24%', flexShrink: 0, minWidth: 0 }}>
              <AutoFitText text={m.value} max={valueSize} min={20} lines={1}
                style={{ fontFamily: DISPLAY, letterSpacing: -0.5, lineHeight: 1, color: pal.accent, maxWidth: '100%' }} />
            </div>
            <div style={{ width: face, height: face, flexShrink: 0, position: 'relative', overflow: 'hidden', borderRadius: '50%', background: `${pal.ink}14`, border: `2px solid ${pal.accent}`, boxSizing: 'border-box' }}>
              <Face p={m} team={team} palette={pal} pos="center 12%" />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              {m.first && !tight ? <div style={{ fontFamily: DISPLAY, fontSize: firstSize, letterSpacing: 1.5, opacity: 0.7, lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(m.first).toUpperCase()}</div> : null}
              <div style={{ fontFamily: DISPLAY, fontSize: nameSize, letterSpacing: 0.5, lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {m.first && tight ? <span style={{ fontSize: Math.round(nameSize * 0.62), letterSpacing: 1.5, opacity: 0.7, marginRight: 8 }}>{String(m.first).toUpperCase()}</span> : null}{m.last}
              </div>
              <div style={{ fontFamily: MONO, fontSize: unitSize, letterSpacing: 1.4, color: pal.accent, fontWeight: 700, marginTop: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(m.unit || '').toUpperCase()}{m.dateLabel ? <span style={{ color: pal.ink, opacity: 0.55, fontWeight: 400 }}>{` · ${m.dateLabel}`.toUpperCase()}</span> : null}</div>
            </div>
          </div>
        ))}
      </div>
      {bandFooter({ pal, width, height })}
      <Grain opacity={0.3} id="ms2-g" />
    </LayerRoot>
  )
}

CardFace.displayName = 'CardFace'
MilestoneCards.displayName = 'MilestoneCards'
MilestoneBoard.displayName = 'MilestoneBoard'

// Where this file's layouts keep the sponsor grid (see sponsorSlots.js). The
// strip is the team of the week's, so the room kept is the same.
export const SPONSOR_SLOTS = { MS1: slotTW, MS2: slotTW }
