// Split poster — a pale panel with the player standing on it, beside a dark
// panel carrying the numbered XI. Built from a club's own "Starting XI" story:
// a competition and round tag, the cut-out figure, the side and the wordmark,
// the XI with its role and debut tags, the fixture in the foot, a sponsor mark.
//
// Every one of those is its own root child with a `data-layer` name, so each is
// a layer in the Layers panel and can be reordered or hidden.
//
// The size maths follows postAspect.js: all three post shapes are 1080 wide, so
// the question is only where the extra height goes. The photo and the list take
// it; the wordmark and the foot keep their pixels.
import { Halftone, AutoFitText, CreditMark, RoleChip, DebutTag, featuredOf, heroSrcOf, heroRowMark, isHeroRow } from './cricket-templates'
import { aspectOf, pick, share } from './postAspect'
import { LayerRoot } from './postLayers'

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

export function SplitPoster({
  width = 1080, height = 1080, team, opponent, match, players, palette,
  heroImage, headline, featuredId, sponsors, panelColor, markHero, background,
}) {
  const P = (players || []).slice(0, 11)
  const A = aspectOf(width, height)
  const featured = featuredOf(players, featuredId)
  const photo = heroImage || heroSrcOf(featured)

  const accent = palette.accent
  const accentInk = isLight(accent) ? '#0b0b0c' : '#ffffff'
  const dark = palette.primary
  const panel = panelColor || autoPanelColor(accent)
  const deep = mixHex(panel, '#050b18', 0.82)
  const band = mixHex(panel, '#ffffff', 0.4)
  const debutBg = mixHex(panel, '#ffffff', 0.62)
  const debutInk = '#0a1a33'

  // Left panel and the dark one beside it. The strip of pale on the right edge
  // is the root's own background, so it needs no layer.
  const LEFT_W = Math.round(width * 0.505)
  const EDGE = 40
  const DARK_W = width - LEFT_W - EDGE

  // Where the height goes. The story's top and bottom carry the app's own
  // profile row and reply bar, so the type moves in from both edges there.
  const headShift = pick(A, { square: 0, portrait: 18, story: 120 })
  const footBottom = pick(A, { square: 32, portrait: 40, story: 200 })

  const LIST_X = LEFT_W + 96
  const LIST_R = width - EDGE - 36
  const listTop = 312 + headShift
  const listGap = pick(A, { square: 257, portrait: 262, story: 400 })
  const avail = height - listTop - listGap
  const rowH = Math.min(pick(A, { square: 46.5, portrait: 60, story: 80 }), avail / 11)
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
  const logos = (sponsors || []).filter((s) => s && s.url)

  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: ownPanels ? panel : 'transparent', color: '#ffffff', fontFamily: NAME_FONT,
    }}>
      {/* Two soft diagonal bands across the pale panel. */}
      {ownPanels && <svg data-layer="Panel bands" width={LEFT_W} height={height} viewBox={`0 0 ${LEFT_W} ${height}`}
        style={{ position: 'absolute', left: 0, top: 0 }}>
        <line x1={-40} y1={110 + headShift} x2={LEFT_W + 20} y2={430 + headShift} stroke={band} strokeWidth={118} opacity={0.34} />
        <line x1={-40} y1={270 + headShift} x2={LEFT_W - 44} y2={568 + headShift} stroke={band} strokeWidth={84} strokeLinecap="round" opacity={0.4} />
      </svg>}
      {/* Dot texture, strongest low on the panel where it meets the shade. */}
      {ownPanels && <div data-layer="Dot texture" style={{
        position: 'absolute', left: 0, top: share(height, 600), width: LEFT_W, height: share(height, 300), overflow: 'hidden',
        WebkitMaskImage: 'linear-gradient(180deg, transparent 0%, #000 70%)', maskImage: 'linear-gradient(180deg, transparent 0%, #000 70%)',
      }}>
        <Halftone color="#ffffff" opacity={0.5} size={9} />
      </div>}
      {ownRail && <div data-layer="XI panel" style={{ position: 'absolute', left: LEFT_W, top: 0, bottom: 0, width: DARK_W, background: dark }} />}
      {/* The outlined XI sits UNDER the wordmark, so the G of STARTING crosses it. */}
      <div data-layer="Outlined XI" style={{
        position: 'absolute', left: LEFT_W + 270, top: 48 + headShift, width: DARK_W - 270, textAlign: 'center',
        fontFamily: DISPLAY, fontSize: 250, lineHeight: 0.92, letterSpacing: -2,
        color: 'transparent', WebkitTextStroke: `3px ${accent}`, whiteSpace: 'nowrap',
      }}>XI</div>

      {/* The player. Contained, never cropped: a full-length cut-out stands on the
          panel with its feet in the shade. */}
      <div data-layer="Player photo" style={{ position: 'absolute', left: 16, width: LEFT_W - 32, top: photoTop, height: photoH }}>
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
            style={{ fontFamily: DISPLAY, letterSpacing: 1.5, lineHeight: 1.05, color: '#ffffff' }} />
        )}
        <AutoFitText text={round || 'ROUND 1'} max={104} min={36} lines={1}
          style={{ fontFamily: DISPLAY, letterSpacing: -0.5, lineHeight: 1, color: '#ffffff' }} />
      </div>

      {side && (
        <div data-layer="Side label" style={{ position: 'absolute', left: LIST_X - 34, top: 82 + headShift, width: 300 }}>
          <AutoFitText text={side} max={22} min={11} lines={1}
            style={{ fontFamily: DISPLAY, letterSpacing: 1.2, lineHeight: 1, color: '#ffffff' }} />
        </div>
      )}
      <div data-layer="Starting wordmark" style={{ position: 'absolute', left: LIST_X - 34, top: 120 + headShift, width: LIST_R - LIST_X + 30 }}>
        <AutoFitText text="STARTING" max={92} min={40} lines={1}
          style={{ fontFamily: DISPLAY, lineHeight: 1, letterSpacing: 1, color: '#ffffff' }} />
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
              ...heroRowMark(hero, accent, { bleed: 12 }),
            }}>
              <div style={{
                width: Math.round(nameMax * 1.5), flexShrink: 0, textAlign: 'right', paddingRight: 4,
                fontFamily: NAME_FONT, fontWeight: 500, fontSize: nameMax, lineHeight: 1, color: '#ffffff', opacity: 0.92,
              }}>{i + 1}.</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <AutoFitText max={nameMax} min={12} lines={1} pad={6}
                  measureDeps={[p.captain, p.viceCaptain, p.keeper, p.debut]}
                  style={{ fontFamily: NAME_FONT, fontWeight: 800, letterSpacing: 0.2, lineHeight: 1.1, color: '#ffffff' }}>
                  {`${p.first || ''} ${p.last || ''}`.trim().toUpperCase()}
                </AutoFitText>
              </div>
              <div style={{ display: 'flex', gap: 5, flexShrink: 0, alignItems: 'center' }}>
                {p.captain && <RoleChip kind="C" accent={accent} ink={accentInk} />}
                {p.viceCaptain && <RoleChip kind="VC" accent={accent} ink={accentInk} />}
                {p.keeper && <RoleChip kind="WK" accent={accent} ink={accentInk} />}
                {p.debut && <DebutTag accent={debutBg} ink={debutInk} />}
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
          style={{ fontFamily: NAME_FONT, fontWeight: 800, letterSpacing: 0.2, lineHeight: 1.12, color: accent }} />
        <AutoFitText text={`VS ${(opponent.name || '').toUpperCase()}`.trim()} max={36} min={16} lines={1}
          style={{ fontFamily: NAME_FONT, fontWeight: 800, letterSpacing: 0.2, lineHeight: 1.12, color: '#ffffff' }} />
      </div>
      <div data-layer="Venue and time" style={{
        position: 'absolute', left: 326, bottom: footBottom + 42, width: 200,
        fontFamily: NAME_FONT, fontWeight: 700, fontSize: 17, lineHeight: 1.3, letterSpacing: 0.3, color: '#ffffff',
        textShadow: '0 3px 14px rgba(4,12,30,0.5)',
      }}>
        <div>{(match.venue || '').toUpperCase()}</div>
        <div>{when}</div>
      </div>

      {/* Sponsors, or the platform credit when the club has none to show. */}
      <div data-layer="Sponsors" style={{
        position: 'absolute', right: EDGE + 36, bottom: footBottom, width: 290, height: 84,
        display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 18,
      }}>
        {logos.length
          ? logos.slice(0, 2).map((s, i) => (
              <img key={i} src={s.url} alt={s.name || 'sponsor'}
                style={{ flex: 1, minWidth: 0, maxHeight: '100%', maxWidth: logos.length > 1 ? '50%' : '100%', objectFit: 'contain', objectPosition: 'right center' }} />
            ))
          : <CreditMark ink="#ffffff" h={44} />}
      </div>
    </LayerRoot>
  )
}
SplitPoster.displayName = 'SplitPoster'
