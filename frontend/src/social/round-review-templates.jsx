// Round Review posts (Association Socials): four layouts fed from a round saved
// in the Performance Tracker (pages/admin/AdminPerformanceTracker.jsx,
// routers/performance.py).
//
//   RV1 Round Wrap        the round's headlines, one per line
//   RV2 Top Performers    the round's top scores and best bowling, every competition
//   RV3 Player of Round   one player: name, figures, club crest
//   RV4 Match of Round    each competition's match of the round for next week
//
// The editor builds one `review` object from the round (reviewPost in
// social/roundReviewPost.js) and every layout reads only that, so a field typed
// in the Data step shows on whichever layout is open.
//
// Same frame as the team of the week and milestones (totw-templates.jsx): a
// masthead, a body and the sponsor strip, on the workspace palette and display
// font, every element a layer.
import { GrainSVG as Grain, Halftone, Stripes, ClubLogo, AutoFitText } from './cricket-templates'
import { pick } from './postAspect'
import { LayerRoot } from './postLayers'
import { slotTW, bandFrame, bandFooter } from './totw-templates'
import { pc, registerParts, colorPart } from './layoutParts'

const DISPLAY = "var(--social-display-font, 'Anton', sans-serif)"
const MONO = "'JetBrains Mono', monospace"
const BODY = "'Inter', sans-serif"

export const REVIEW_MAX_ROWS = 5

const up = (s) => String(s || '').toUpperCase()

function Crest({ src, name, size, pal }) {
  if (src) return <img src={src} alt={name || 'crest'} style={{ width: size, height: size, objectFit: 'contain', flexShrink: 0, display: 'block' }} />
  const mono = up(name).split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('') || '?'
  return (
    <div style={{ width: size, height: size, flexShrink: 0, borderRadius: '50%', display: 'grid', placeItems: 'center', background: `${pal.ink}14`, border: `2px solid ${pal.accent}`, boxSizing: 'border-box', fontFamily: DISPLAY, fontSize: Math.round(size * 0.38), color: pal.ink }}>{mono}</div>
  )
}

function empty(pal, text) {
  return (
    <div style={{ flex: 1, display: 'grid', placeItems: 'center', border: `2px dashed ${pal.ink}33`, fontFamily: DISPLAY, fontSize: 34, letterSpacing: 2, color: pal.ink, opacity: 0.6, textAlign: 'center', padding: 24, width: '100%', boxSizing: 'border-box' }}>
      {text}
    </div>
  )
}

// Plain function returning its root `div`, called inline, so it takes a z-index.
function masthead({ pal, team, kicker, title1, title2, width, big, parts }) {
  return (
    <div data-layer="Masthead" style={{
      position: 'absolute', left: 0, right: 0, top: 0, padding: '44px 56px 26px',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 24, width, boxSizing: 'border-box',
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 3, color: pc(parts, 'roundColor', pal.accent), fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{`// ${up(kicker)}`}</div>
        <div style={{ fontFamily: DISPLAY, fontSize: big, letterSpacing: -1, lineHeight: 0.86, marginTop: 8, color: pc(parts, 'title1Color', undefined), whiteSpace: 'nowrap' }}>
          {up(title1)}{title2 ? <span style={{ color: pc(parts, 'title2Color', pal.accent) }}>{` ${up(title2)}`}</span> : null}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0 }}>
        <div style={{ fontFamily: DISPLAY, fontSize: 26, letterSpacing: 0.5, lineHeight: 0.95, maxWidth: 230, textAlign: 'right', color: pc(parts, 'clubColor', undefined) }}>{team.fullName || team.name}</div>
        <ClubLogo src={team.logo || null} monogram={team.monogram} color={pal.ink} size={100} shape="shield" />
      </div>
    </div>
  )
}

const kickerOf = (p, lead) => [lead, p.round, p.date].filter(Boolean).join(' · ')

// ═══════════════════════════════════════════════════════════════════════════
// RV1 — Round wrap: the round's headlines
// ═══════════════════════════════════════════════════════════════════════════
export function ReviewWrap({ palette: pal, width = 1080, height = 1080, team = {}, review = {}, parts }) {
  const F = bandFrame(width, height)
  const lines = (review.headlines || []).filter(Boolean).slice(0, 6)
  const n = lines.length
  const bodyH = height - F.top - F.bottom - (review.cta ? 70 : 0)
  const lineMax = Math.max(22, Math.min(50, Math.round(bodyH / Math.max(1, n) * 0.36)))
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: pal.primary, color: pal.ink, fontFamily: BODY }}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.035} gap={28} angle={45} />
      {masthead({ pal, team, kicker: kickerOf({ ...review, round: '' }, review.comps || 'ROUND WRAP'), title1: review.title || review.round || 'ROUND', title2: review.title ? '' : 'WRAP', width, big: pick(F.A, { square: 78, portrait: 90, story: 104 }), parts })}
      <div data-layer="Headlines" style={{ position: 'absolute', left: 56, right: 56, top: F.top, bottom: F.bottom, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', borderTop: `3px solid ${pc(parts, 'ruleColor', pal.accent)}` }}>
          {n === 0 ? empty(pal, 'PULL THE ROUND IN THE TRACKER') : null}
          {lines.map((t, i) => (
            <div key={i} style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', gap: 20, borderBottom: i < n - 1 ? `1px solid ${pc(parts, 'dividerColor', `${pal.ink}1f`)}` : 'none' }}>
              <div style={{ fontFamily: MONO, fontSize: Math.round(lineMax * 0.55), color: pc(parts, 'numColor', pal.accent), fontWeight: 700, flexShrink: 0, width: Math.round(lineMax * 1.25) }}>{String(i + 1).padStart(2, '0')}</div>
              <AutoFitText text={up(t)} max={lineMax} min={16} lines={2}
                style={{ fontFamily: DISPLAY, letterSpacing: 0.5, lineHeight: 1.02, color: pc(parts, 'nameColor', undefined), flex: 1, minWidth: 0 }} />
            </div>
          ))}
        </div>
        {review.cta ? (
          <div data-layer="Call to action" style={{ flexShrink: 0, alignSelf: 'flex-start', background: pc(parts, 'bandBg', pal.accent), color: pc(parts, 'bandInk', pal.primary), padding: '12px 22px', fontFamily: DISPLAY, fontSize: 30, letterSpacing: 2, lineHeight: 1, maxWidth: '100%', boxSizing: 'border-box', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{up(review.cta)}</div>
        ) : null}
      </div>
      {bandFooter({ pal, width, height, parts })}
      <Grain opacity={0.3} id="rv1-g" />
    </LayerRoot>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// RV2 — Top performers: top scores and best bowling
// ═══════════════════════════════════════════════════════════════════════════
function StatList({ label, rows, pal, parts, rowH, nameMax, figMax, crest }) {
  return (
    <div style={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 3, fontWeight: 700, color: pc(parts, 'roundColor', pal.accent), paddingBottom: 8, borderBottom: `3px solid ${pc(parts, 'ruleColor', pal.accent)}`, flexShrink: 0 }}>{up(label)}</div>
      {rows.length === 0 ? <div style={{ fontFamily: MONO, fontSize: 14, opacity: 0.5, paddingTop: 12 }}>NONE THIS ROUND</div> : null}
      {rows.map((r, i) => (
        <div key={i} style={{ height: rowH, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 14, borderBottom: `1px solid ${pc(parts, 'dividerColor', `${pal.ink}1f`)}`, minWidth: 0 }}>
          <Crest src={r.logo} name={r.team} size={crest} pal={pal} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <AutoFitText text={up(r.name)} max={nameMax} min={14} lines={1}
              style={{ fontFamily: DISPLAY, letterSpacing: 0.5, lineHeight: 1, color: pc(parts, 'nameColor', undefined), maxWidth: '100%' }} />
            <div style={{ fontFamily: MONO, fontSize: Math.max(11, Math.round(nameMax * 0.4)), letterSpacing: 1, opacity: 0.65, marginTop: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: pc(parts, 'subColor', undefined) }}>
              {up([r.team, r.opp ? `V ${r.opp}` : '', r.comp].filter(Boolean).join(' · '))}
            </div>
          </div>
          <div style={{ fontFamily: DISPLAY, fontSize: figMax, lineHeight: 1, letterSpacing: -0.5, color: pc(parts, 'statColor', pal.accent), flexShrink: 0, whiteSpace: 'nowrap' }}>{r.figure}</div>
        </div>
      ))}
    </div>
  )
}

export function ReviewPerformers({ palette: pal, width = 1080, height = 1080, team = {}, review = {}, parts }) {
  const F = bandFrame(width, height)
  const scores = (review.scores || []).slice(0, REVIEW_MAX_ROWS)
  const bowling = (review.bowling || []).slice(0, REVIEW_MAX_ROWS)
  // A square post sets the two lists side by side; a taller one stacks them.
  const side = F.A === 'square'
  const bodyH = height - F.top - F.bottom
  const listH = side ? bodyH - 40 : (bodyH - 40 - 30) / 2
  const rowH = Math.floor(listH / REVIEW_MAX_ROWS)
  const nameMax = Math.max(18, Math.min(side ? 30 : 38, Math.round(rowH * 0.34)))
  const figMax = Math.max(24, Math.min(side ? 44 : 60, Math.round(rowH * 0.5)))
  const crest = Math.max(34, Math.min(70, Math.round(rowH * 0.62)))
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: pal.primary, color: pal.ink, fontFamily: BODY }}>
      <Halftone color={pal.ink} opacity={0.05} size={12} />
      {masthead({ pal, team, kicker: kickerOf(review, 'ROUND REVIEW'), title1: review.title || 'TOP', title2: review.title ? '' : 'PERFORMERS', width, big: pick(F.A, { square: 78, portrait: 90, story: 104 }), parts })}
      <div data-layer="Stats" style={{ position: 'absolute', left: 56, right: 56, top: F.top, bottom: F.bottom, display: 'flex', flexDirection: side ? 'row' : 'column', gap: side ? 36 : 30 }}>
        <StatList label="Top scores" rows={scores} pal={pal} parts={parts} rowH={rowH} nameMax={nameMax} figMax={figMax} crest={crest} />
        <StatList label="Best bowling" rows={bowling} pal={pal} parts={parts} rowH={rowH} nameMax={nameMax} figMax={figMax} crest={crest} />
      </div>
      {bandFooter({ pal, width, height, parts })}
      <Grain opacity={0.3} id="rv2-g" />
    </LayerRoot>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// RV3 — Player of the round
// ═══════════════════════════════════════════════════════════════════════════
export function ReviewPlayer({ palette: pal, width = 1080, height = 1080, team = {}, review = {}, parts }) {
  const F = bandFrame(width, height)
  const p = review.potr || null
  const bodyW = width - 112
  const crest = pick(F.A, { square: 330, portrait: 400, story: 520 })
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: pal.primary, color: pal.ink, fontFamily: BODY }}>
      <Halftone color={pal.ink} opacity={0.06} size={11} />
      <Stripes color={pal.accent} opacity={0.035} gap={28} angle={45} />
      {masthead({ pal, team, kicker: kickerOf(review, 'ROUND REVIEW'), title1: review.title || 'PLAYER OF', title2: review.title ? '' : 'THE ROUND', width, big: pick(F.A, { square: 70, portrait: 80, story: 92 }), parts })}
      <div data-layer="Player" style={{ position: 'absolute', left: 56, right: 56, top: F.top, bottom: F.bottom, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 10 }}>
        {!p ? empty(pal, 'PICK THE PLAYER OF THE ROUND') : (
          <>
            <div data-layer="Crest" style={{ position: 'absolute', right: 0, top: 0, opacity: 0.95 }}>
              <Crest src={p.logo} name={p.team} size={crest} pal={pal} />
            </div>
            <div style={{ position: 'relative', minWidth: 0 }}>
              {p.first ? <div style={{ fontFamily: DISPLAY, fontSize: 54, letterSpacing: 2, lineHeight: 1, opacity: 0.8, color: pc(parts, 'firstColor', undefined) }}>{up(p.first)}</div> : null}
              <AutoFitText text={up(p.last || p.name)} max={pick(F.A, { square: 170, portrait: 190, story: 210 })} min={48} lines={1}
                style={{ fontFamily: DISPLAY, letterSpacing: -2, lineHeight: 0.9, color: pc(parts, 'nameColor', undefined), maxWidth: bodyW }} />
            </div>
            {p.line ? (
              <div data-layer="Figures" style={{ position: 'relative', alignSelf: 'flex-start', background: pc(parts, 'bandBg', pal.accent), color: pc(parts, 'bandInk', pal.primary), padding: '14px 24px', fontFamily: DISPLAY, fontSize: pick(F.A, { square: 54, portrait: 60, story: 66 }), letterSpacing: 1, lineHeight: 1, maxWidth: '100%', boxSizing: 'border-box', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{up(p.line)}</div>
            ) : null}
            <div style={{ position: 'relative', fontFamily: MONO, fontSize: 20, letterSpacing: 2, fontWeight: 700, color: pc(parts, 'subColor', pal.ink), opacity: 0.8, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {up([p.team, p.opp ? `V ${p.opp}` : '', p.comp].filter(Boolean).join(' · '))}
            </div>
          </>
        )}
      </div>
      {bandFooter({ pal, width, height, parts })}
      <Grain opacity={0.3} id="rv3-g" />
    </LayerRoot>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// RV4 — Match of the round: next week's pick per competition
// ═══════════════════════════════════════════════════════════════════════════
const ord = (n) => {
  if (typeof n !== 'number') return ''
  const s = ['TH', 'ST', 'ND', 'RD']; const v = n % 100
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`
}

export function ReviewMatch({ palette: pal, width = 1080, height = 1080, team = {}, review = {}, parts }) {
  const F = bandFrame(width, height)
  const games = (review.ahead || []).slice(0, 4)
  const bodyH = height - F.top - F.bottom
  // One competition gets a big card in the middle; several share the height.
  const gameH = games.length === 1 ? Math.round(bodyH * 0.62) : Math.floor(bodyH / Math.max(1, games.length)) - 10
  const crest = Math.max(44, Math.min(games.length === 1 ? 230 : 150, Math.round(gameH * 0.5)))
  const nameMax = Math.max(18, Math.min(games.length === 1 ? 64 : 48, Math.round(gameH * 0.2)))
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: pal.primary, color: pal.ink, fontFamily: BODY }}>
      <Halftone color={pal.ink} opacity={0.05} size={12} />
      {masthead({ pal, team, kicker: kickerOf({ ...review, round: review.nextRound || 'NEXT ROUND', date: '' }, 'COMING UP'), title1: review.title || 'MATCH OF', title2: review.title ? '' : 'THE ROUND', width, big: pick(F.A, { square: 78, portrait: 90, story: 104 }), parts })}
      <div data-layer="Matches" style={{ position: 'absolute', left: 56, right: 56, top: F.top, bottom: F.bottom, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 10 }}>
        {games.length === 0 ? empty(pal, 'PULL THE ROUND IN THE TRACKER') : null}
        {games.map((g, i) => (
          <div key={i} style={{ height: gameH, flexShrink: 0, position: 'relative', background: pc(parts, 'cardBg', `${pal.secondary}`), border: `2px solid ${pc(parts, 'cardBorder', pal.accent)}`, boxSizing: 'border-box', padding: '10px 22px', display: 'flex', flexDirection: 'column', justifyContent: 'center', minWidth: 0 }}>
            <div style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 2.5, fontWeight: 700, color: pc(parts, 'roundColor', pal.accent), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {up([g.comp, g.when, g.venue].filter(Boolean).join(' · '))}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 6, minWidth: 0 }}>
              <Crest src={g.homeLogo} name={g.home} size={crest} pal={pal} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <AutoFitText text={up(g.home)} max={nameMax} min={14} lines={1} style={{ fontFamily: DISPLAY, lineHeight: 1, color: pc(parts, 'nameColor', undefined), maxWidth: '100%' }} />
                {g.homeRank ? <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 1.5, opacity: 0.65 }}>{`${ord(g.homeRank)} ON THE LADDER`}</div> : null}
              </div>
              <div style={{ fontFamily: DISPLAY, fontSize: Math.round(nameMax * 1.1), color: pc(parts, 'numColor', pal.accent), flexShrink: 0 }}>V</div>
              <div style={{ flex: 1, minWidth: 0, textAlign: 'right' }}>
                <AutoFitText text={up(g.away)} max={nameMax} min={14} lines={1} style={{ fontFamily: DISPLAY, lineHeight: 1, color: pc(parts, 'nameColor', undefined), maxWidth: '100%', textAlign: 'right' }} />
                {g.awayRank ? <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 1.5, opacity: 0.65 }}>{`${ord(g.awayRank)} ON THE LADDER`}</div> : null}
              </div>
              <Crest src={g.awayLogo} name={g.away} size={crest} pal={pal} />
            </div>
          </div>
        ))}
      </div>
      {bandFooter({ pal, width, height, parts })}
      <Grain opacity={0.3} id="rv4-g" />
    </LayerRoot>
  )
}

const P_HEAD = 'Heading', P_BODY = 'Body', P_FOOT = 'Footer'
const headParts = () => [
  colorPart('roundColor', 'Small lines (round, labels)', P_HEAD, (p) => p.accent),
  colorPart('title1Color', 'Heading', P_HEAD, (p) => p.ink),
  colorPart('title2Color', 'Second half of the heading', P_HEAD, (p) => p.accent),
  colorPart('clubColor', 'Workspace name', P_HEAD, (p) => p.ink),
]
const footParts = () => [
  colorPart('footerBg', 'Footer bar', P_FOOT, (p) => p.primary),
  colorPart('footerRule', 'Footer line', P_FOOT, (p) => p.accent),
]
registerParts({
  RV1: [...headParts(),
    colorPart('numColor', 'Line numbers', P_BODY, (p) => p.accent),
    colorPart('nameColor', 'Headlines', P_BODY, (p) => p.ink),
    colorPart('ruleColor', 'Line over the headlines', P_BODY, (p) => p.accent),
    colorPart('dividerColor', 'Row dividers', P_BODY, (p) => p.ink),
    colorPart('bandBg', 'Call to action band', P_BODY, (p) => p.accent),
    colorPart('bandInk', 'Text on the band', P_BODY, (p) => p.primary),
    ...footParts()],
  RV2: [...headParts(),
    colorPart('ruleColor', 'Line under each list title', P_BODY, (p) => p.accent),
    colorPart('nameColor', 'Player names', P_BODY, (p) => p.ink),
    colorPart('subColor', 'Club and competition line', P_BODY, (p) => p.ink),
    colorPart('statColor', 'Figures', P_BODY, (p) => p.accent),
    colorPart('dividerColor', 'Row dividers', P_BODY, (p) => p.ink),
    ...footParts()],
  RV3: [...headParts(),
    colorPart('firstColor', 'First name', P_BODY, (p) => p.ink),
    colorPart('nameColor', 'Surname', P_BODY, (p) => p.ink),
    colorPart('bandBg', 'Figures band', P_BODY, (p) => p.accent),
    colorPart('bandInk', 'Text on the figures band', P_BODY, (p) => p.primary),
    colorPart('subColor', 'Club and competition line', P_BODY, (p) => p.ink),
    ...footParts()],
  RV4: [...headParts(),
    colorPart('cardBg', 'Match card', P_BODY, (p) => p.secondary),
    colorPart('cardBorder', 'Match card outline', P_BODY, (p) => p.accent),
    colorPart('nameColor', 'Team names', P_BODY, (p) => p.ink),
    colorPart('numColor', 'The V', P_BODY, (p) => p.accent),
    ...footParts()],
})

Crest.displayName = 'ReviewCrest'
StatList.displayName = 'ReviewStatList'
ReviewWrap.displayName = 'ReviewWrap'
ReviewPerformers.displayName = 'ReviewPerformers'
ReviewPlayer.displayName = 'ReviewPlayer'
ReviewMatch.displayName = 'ReviewMatch'

// Same sponsor strip as the team of the week, so the room kept is the same.
export const SPONSOR_SLOTS = { RV1: slotTW, RV2: slotTW, RV3: slotTW, RV4: slotTW }
