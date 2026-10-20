// Split poster — a pale panel with the player standing on it, beside a dark
// panel carrying the numbered XI. Built from a club's own "Starting XI" story:
// a competition and round tag, the cut-out figure, the side and the wordmark,
// the XI with its role and debut tags, the fixture in the foot, and a sponsor slot
// under the XI (the editor's sponsor grid goes there; see splitSponsorSlot).
//
// Every one of those is its own root child with a `data-layer` name, so each is
// a layer in the Layers panel and can be reordered or hidden.
//
// The size maths follows postAspect.js: all three post shapes are 1080 wide, so
// the question is only where the extra height goes. The photo and the list take
// it; the wordmark and the foot keep their pixels.
import { Halftone, AutoFitText, CreditMark, RoleChip, DebutTag, featuredOf, heroSrcOf, heroRowMark, isHeroRow, LINEUP_MAX } from './cricket-templates'
import { aspectOf, pick, share } from './postAspect'
import { LayerRoot } from './postLayers'
import { usePostLook } from './postLook'
import { pc, pt, inkOn, registerParts, colorPart as C, textPart as T, picked as partPicked } from './layoutParts'

const DISPLAY = "var(--social-display-font, 'Anton', sans-serif)"
const NAME_FONT = "'Hanken Grotesk', 'Inter', sans-serif"

function rgb(hex) {
  const h = String(hex || '').replace('#', '')
  if (h.length < 6) return [128, 128, 128]
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}
function toHex([r, g, b]) {
  return '#' + [r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')
}
// `a` moved `t` of the way toward `b`.
export function mixHex(a, b, t) {
  const A = rgb(a), B = rgb(b)
  return toHex(A.map((v, i) => v + (B[i] - v) * t))
}
function isLight(hex) {
  const [r, g, b] = rgb(hex)
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150
}

// The panel colour a club gets when it has not picked one: its accent, lifted
// toward white so the cut-out, the white type and the dark panel all read.
export function autoPanelColor(accent) {
  return mixHex(accent || '#16c784', '#ffffff', 0.55)
}

// The measurements the layout and its sponsor slot both read, so the grid sits
// exactly where the XI stops. All three post shapes are 1080 wide. `count` is how
// many players are listed: the rows share the same room, so a twelfth player
// makes every row a little shorter instead of being cut.
function splitGeo(width, height, count = 11) {
  const A = aspectOf(width, height)
  const LEFT_W = Math.round(width * 0.505)
  const EDGE = 40
  const DARK_W = width - LEFT_W - EDGE
  const headShift = pick(A, { square: 0, portrait: 18, story: 120 })
  const footBottom = pick(A, { square: 32, portrait: 40, story: 200 })
  const LIST_X = LEFT_W + 96
  const LIST_R = width - EDGE - 36
  const listTop = 312 + headShift
  const listGap = pick(A, { square: 257, portrait: 262, story: 400 })
  const avail = height - listTop - listGap
  const rows = Math.max(11, Math.min(count, LINEUP_MAX))
  const rowH = Math.min(pick(A, { square: 46.5, portrait: 60, story: 80 }), avail / rows)
  return { A, LEFT_W, EDGE, DARK_W, headShift, footBottom, LIST_X, LIST_R, listTop, listGap, rowH }
}

// Height of the platform credit that closes the dark panel, and the gap above it.
const CREDIT_H = 44
const CREDIT_GAP = 12

// Sponsor slot: on the dark panel, directly under the XI rows, as wide as the
// XI. It stops above the platform credit and never reaches into the list.
// `opts.players` is how many players the post lists (eleven when not given).
export function splitSponsorSlot(width = 1080, height = 1080, _count = 1, opts) {
  const g = splitGeo(width, height, opts?.players)
  const x = g.LIST_X - 34
  const bottom = height - g.footBottom - CREDIT_H - CREDIT_GAP
  const top = g.listTop + Math.max(11, Math.min(opts?.players || 11, LINEUP_MAX)) * g.rowH + 16
  // Taller posts have more room under the list, so the grid takes more of it.
  const h = Math.max(70, Math.min(pick(g.A, { square: 140, portrait: 170, story: 240 }), bottom - top))
  return { x, y: bottom - h, w: g.LIST_R - x, h, pad: 8, gap: 16, panel: 'light' }
}

export function SplitPoster({
  width = 1080, height = 1080, team, opponent, match, players, palette,
  heroImage, headline, featuredId, panelColor, markHero, background, parts,
}) {
  const texture = usePostLook().texture !== false
  const P = (players || []).slice(0, LINEUP_MAX)
  const A = aspectOf(width, height)
  const featured = featuredOf(players, featuredId)
  const photo = heroImage || heroSrcOf(featured)

  const accent = palette.accent
  const accentInk = isLight(accent) ? '#0b0b0c' : '#ffffff'
  const dark = palette.primary
  const panel = panelColor || autoPanelColor(accent)
  const deep = pc(parts, 't11Shade', mixHex(panel, '#050b18', 0.82))
  const band = pc(parts, 't11Bands', mixHex(panel, '#ffffff', 0.4))
  const debutBg = mixHex(panel, '#ffffff', 0.62)
  const debutInk = '#0a1a33'
  // The chips and the debut tag follow their background once the club has set one,
  // so a pale chip does not keep the white text a dark one had.
  const chipBg = pc(parts, 'badgeBg', accent)
  const chipInk = pc(parts, 'badgeColor', partPicked(parts, 'badgeBg') ? inkOn(chipBg) : accentInk)
  const tagBg = pc(parts, 't11DebutBg', debutBg)
  const tagInk = pc(parts, 't11DebutInk', partPicked(parts, 't11DebutBg') ? inkOn(tagBg) : debutInk)

  // Left panel and the dark one beside it. The strip of pale on the right edge
  // is the root's own background, so it needs no layer.
  // Where the height goes. The story's top and bottom carry the app's own
  // profile row and reply bar, so the type moves in from both edges there.
  const { LEFT_W, EDGE, DARK_W, headShift, footBottom, LIST_X, LIST_R, listTop, rowH } = splitGeo(width, height, P.length)
  const nameMax = Math.round(rowH * 0.52)

  const photoTop = share(height, 200)
  const photoH = share(height, 690) - (A === 'story' ? 120 : 0)

  // The editor fills an empty competition with this word so other layouts have
  // something to print. Here it would sit above the round as if it were data.
  const comp = (match.competition && match.competition !== 'COMPETITION' ? match.competition : '').toUpperCase()
  // A background picked in the editor (Design, Background) draws behind the post.
  // The pale panel's own layers then step aside so its colours are the ones
  // that show; the dark XI rail stays unless the picked one is Split Panels,
  // which draws that rail too.
  const ownPanels = !background
  const ownRail = !background || background !== 'split-panels'
  const round = (match.round || '').toUpperCase()
  const side = (headline || '').toUpperCase()
  const when = [match.date, match.time].filter(Boolean).join(', ').toUpperCase()

  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: ownPanels ? panel : 'transparent', color: '#ffffff', fontFamily: NAME_FONT,
    }}>
      {/* Two soft diagonal bands across the pale panel. */}
      {ownPanels && texture && <svg data-layer="Panel bands" width={LEFT_W} height={height} viewBox={`0 0 ${LEFT_W} ${height}`}
        style={{ position: 'absolute', left: 0, top: 0 }}>
        <line x1={-40} y1={110 + headShift} x2={LEFT_W + 20} y2={430 + headShift} stroke={band} strokeWidth={118} opacity={0.34} />
        <line x1={-40} y1={270 + headShift} x2={LEFT_W - 44} y2={568 + headShift} stroke={band} strokeWidth={84} strokeLinecap="round" opacity={0.4} />
      </svg>}
      {/* Dot texture, strongest low on the panel where it meets the shade. */}
      {ownPanels && texture && <div data-layer="Dot texture" style={{
        position: 'absolute', left: 0, top: share(height, 600), width: LEFT_W, height: share(height, 300), overflow: 'hidden',
        WebkitMaskImage: 'linear-gradient(180deg, transparent 0%, #000 70%)', maskImage: 'linear-gradient(180deg, transparent 0%, #000 70%)',
      }}>
        <Halftone color="#ffffff" opacity={0.5} size={9} />
      </div>}
      {ownRail && <div data-layer="XI panel" style={{ position: 'absolute', left: LEFT_W, top: 0, bottom: 0, width: DARK_W, background: pc(parts, 't11Dark', dark) }} />}
      {/* The outlined XI sits UNDER the wordmark, so the G of STARTING crosses it. */}
      <div data-layer="Outlined XI" style={{
        position: 'absolute', left: LEFT_W + 270, top: 48 + headShift, width: DARK_W - 270, textAlign: 'center',
        fontFamily: DISPLAY, fontSize: 250, lineHeight: 0.92, letterSpacing: -2,
        color: 'transparent', WebkitTextStroke: `3px ${pc(parts, 'title2Color', accent)}`, whiteSpace: 'nowrap',
      }}>{pt(parts, 'title2', 'XI')}</div>

      {/* The player. Contained, never cropped: a full-length cut-out stands on the
          panel with its feet in the shade. */}
      <div data-layer="Player photo" style={{ position: 'absolute', left: 16, width: LEFT_W - 32, top: photoTop, height: photoH, background: pc(parts, 'photoBg', undefined) }}>
        {photo
          ? <img src={photo} alt={featured ? `${featured.first} ${featured.last}` : (team.short || 'team')}
              style={{ width: '100%', height: '100%', objectFit: 'contain', objectPosition: 'center bottom' }} />
          : team.logo
            ? <img src={team.logo} alt={team.short || 'club'}
                style={{ width: '100%', height: '100%', objectFit: 'contain', objectPosition: 'center', opacity: 0.35, padding: 60, boxSizing: 'border-box' }} />
            : null}
      </div>
      {ownPanels && <div data-layer="Panel shade" style={{
        position: 'absolute', left: 0, bottom: 0, width: LEFT_W, height: share(height, 330),
        background: `linear-gradient(180deg, ${deep}00 0%, ${deep}cc 55%, ${deep} 100%)`,
      }} />}

      {/* Competition and round, top left. */}
      <div data-layer="Round heading" style={{
        position: 'absolute', left: 62, top: 40 + headShift, width: LEFT_W - 90,
        textShadow: '0 4px 18px rgba(6,22,56,0.38)',
      }}>
        {comp && (
          <AutoFitText text={comp} max={32} min={14} lines={1}
            style={{ fontFamily: DISPLAY, letterSpacing: 1.5, lineHeight: 1.05, color: pc(parts, 't11CompColor', '#ffffff') }} />
        )}
        <AutoFitText text={round || 'ROUND 1'} max={104} min={36} lines={1}
          style={{ fontFamily: DISPLAY, letterSpacing: -0.5, lineHeight: 1, color: pc(parts, 'roundColor', '#ffffff') }} />
      </div>

      {side && (
        <div data-layer="Side label" style={{ position: 'absolute', left: LIST_X - 34, top: 82 + headShift, width: 300 }}>
          <AutoFitText text={side} max={22} min={11} lines={1}
            style={{ fontFamily: DISPLAY, letterSpacing: 1.2, lineHeight: 1, color: pc(parts, 't11SideColor', '#ffffff') }} />
        </div>
      )}
      <div data-layer="Starting wordmark" style={{ position: 'absolute', left: LIST_X - 34, top: 120 + headShift, width: LIST_R - LIST_X + 30 }}>
        <AutoFitText text={pt(parts, 'title1', 'STARTING')} max={92} min={40} lines={1}
          style={{ fontFamily: DISPLAY, lineHeight: 1, letterSpacing: 1, color: pc(parts, 'title1Color', '#ffffff') }} />
      </div>

      {/* The XI. */}
      <div data-layer="Starting XI" style={{
        position: 'absolute', left: LIST_X, right: width - LIST_R, top: listTop, display: 'flex', flexDirection: 'column',
      }}>
        {P.map((p, i) => {
          const hero = isHeroRow(p, featured, markHero)
          return (
            <div key={i} style={{
              height: rowH, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8,
              ...heroRowMark(hero, pc(parts, 't11HeroMark', accent), { bleed: 12 }),
            }}>
              <div style={{
                width: Math.round(nameMax * 1.5), flexShrink: 0, textAlign: 'right', paddingRight: 4,
                fontFamily: NAME_FONT, fontWeight: 500, fontSize: nameMax, lineHeight: 1, color: pc(parts, 'numColor', '#ffffff'), opacity: 0.92,
              }}>{i + 1}.</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <AutoFitText max={nameMax} min={12} lines={1} pad={6}
                  measureDeps={[p.captain, p.viceCaptain, p.keeper, p.debut]}
                  style={{ fontFamily: NAME_FONT, fontWeight: 800, letterSpacing: 0.2, lineHeight: 1.1, color: pc(parts, 'nameColor', '#ffffff') }}>
                  {`${p.first || ''} ${p.last || ''}`.trim().toUpperCase()}
                </AutoFitText>
              </div>
              <div style={{ display: 'flex', gap: 5, flexShrink: 0, alignItems: 'center' }}>
                {p.captain && <RoleChip kind="C" accent={chipBg} ink={chipInk} />}
                {p.viceCaptain && <RoleChip kind="VC" accent={chipBg} ink={chipInk} />}
                {p.keeper && <RoleChip kind="WK" accent={chipBg} ink={chipInk} />}
                {p.debut && <DebutTag accent={tagBg} ink={tagInk} />}
              </div>
            </div>
          )
        })}
      </div>

      {/* The fixture, foot left. */}
      <div data-layer="Fixture" style={{
        position: 'absolute', left: 32, bottom: footBottom + 42, width: 280,
        textShadow: '0 3px 14px rgba(4,12,30,0.5)',
      }}>
        <AutoFitText text={(team.name || '').toUpperCase()} max={36} min={16} lines={1}
          style={{ fontFamily: NAME_FONT, fontWeight: 800, letterSpacing: 0.2, lineHeight: 1.12, color: pc(parts, 'clubColor', accent) }} />
        <AutoFitText text={`${pt(parts, 't11Vs', 'VS')} ${(opponent.name || '').toUpperCase()}`.trim()} max={36} min={16} lines={1}
          style={{ fontFamily: NAME_FONT, fontWeight: 800, letterSpacing: 0.2, lineHeight: 1.12, color: pc(parts, 'subColor', '#ffffff') }} />
      </div>
      <div data-layer="Venue and time" style={{
        position: 'absolute', left: 326, bottom: footBottom + 42, width: 200,
        fontFamily: NAME_FONT, fontWeight: 700, fontSize: 17, lineHeight: 1.3, letterSpacing: 0.3, color: pc(parts, 't11VenueColor', '#ffffff'),
        textShadow: '0 3px 14px rgba(4,12,30,0.5)',
      }}>
        <div>{(match.venue || '').toUpperCase()}</div>
        <div>{when}</div>
      </div>

      {/* The sponsor grid goes in splitSponsorSlot, above this credit. */}
      <div data-layer="Platform credit" style={{
        position: 'absolute', right: EDGE + 36, bottom: footBottom, height: CREDIT_H,
        display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
      }}>
        <CreditMark ink="#ffffff" h={CREDIT_H} />
      </div>
    </LayerRoot>
  )
}
SplitPoster.displayName = 'SplitPoster'

// What the club can set on the Split Poster (Brand, "Split Poster elements"). The pale
// panel's own colour stays the editor's Panel colour; these sit beside it.
const T11_HEAD = 'Heading', T11_PHOTO = 'Photo panel', T11_XI = 'Starting XI', T11_FIX = 'Fixture'
registerParts({
  T11: [
    T('title1', 'Wordmark text', T11_HEAD, () => 'STARTING'),
    C('title1Color', 'Wordmark colour', T11_HEAD, () => '#ffffff'),
    T('title2', 'Outlined letters text', T11_HEAD, () => 'XI'),
    C('title2Color', 'Outlined letters colour', T11_HEAD, (p) => p.accent),
    C('roundColor', 'Round', T11_HEAD, () => '#ffffff'),
    C('t11CompColor', 'Competition line', T11_HEAD, () => '#ffffff'),
    C('t11SideColor', 'Side label', T11_HEAD, () => '#ffffff'),
    C('t11Bands', 'Diagonal bands', T11_PHOTO, (p) => mixHex(autoPanelColor(p.accent), '#ffffff', 0.4)),
    C('t11Shade', 'Shade at the foot', T11_PHOTO, (p) => mixHex(autoPanelColor(p.accent), '#050b18', 0.82)),
    C('photoBg', 'Photo backdrop', T11_PHOTO, null, { autoLabel: 'None' }),
    C('t11Dark', 'Dark panel', T11_XI, (p) => p.primary),
    C('numColor', 'Number', T11_XI, () => '#ffffff'),
    C('nameColor', 'Name', T11_XI, () => '#ffffff'),
    C('badgeBg', 'Captain, vice and keeper tag', T11_XI, (p) => p.accent),
    C('badgeColor', 'Text on that tag', T11_XI, (p) => (isLight(p.accent) ? '#0b0b0c' : '#ffffff')),
    C('t11DebutBg', 'Debut tag', T11_XI, (p) => mixHex(autoPanelColor(p.accent), '#ffffff', 0.62)),
    C('t11DebutInk', 'Text on debut tag', T11_XI, () => '#0a1a33'),
    C('t11HeroMark', 'Photo player highlight', T11_XI, (p) => p.accent),
    T('t11Vs', 'Versus word', T11_FIX, () => 'VS'),
    C('clubColor', 'Club name', T11_FIX, (p) => p.accent),
    C('subColor', 'Opposition', T11_FIX, () => '#ffffff'),
    C('t11VenueColor', 'Venue and time', T11_FIX, () => '#ffffff'),
  ],
})

// Where this file's layouts keep the sponsor grid (see sponsorSlots.js).
export const SPONSOR_SLOTS = { T11: splitSponsorSlot }
