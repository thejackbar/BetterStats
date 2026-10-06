// Glass Card (RS7): a match result drawn over the club's own photo.
//
// The photo fills the post. Where the scorecards sit, the photo is blurred and
// tinted black so the card reads, and each team's panel is a pane of glass: a
// frosted copy of the same photo, a sheen and a bright hairline edge. The card
// can sit top centre, bottom centre, or in any of the four side corners, and the
// rest of the post follows it: the sponsor logo and the BetterCricket logo take
// the free end of the photo, opposite the card.
//
// Why a blurred COPY of the photo rather than `backdrop-filter`: the export runs
// through modern-screenshot (an SVG foreignObject), which does not paint
// backdrop-filter. A second image with `filter: blur` and a gradient mask paints
// the same in the editor and in the PNG.
//
// Everything the card and the sponsor slot share is `glassGeo`: the layout reads
// it to place things and `glassSponsorSlot` reads it to keep the grid where the
// layout left room, so the two cannot drift apart.
//
// Every part is a root child with a `data-layer` name, so each is a layer in
// the Layers panel and can be reordered or hidden.
import { AutoFitText, CreditMark, heroFocusStyle } from './cricket-templates'
import { mixHex } from './split-template'
import { aspectOf, pick } from './postAspect'
import { LayerRoot } from './postLayers'

const FONT = "'Hanken Grotesk', 'Inter', sans-serif"
const GOLD = '#f2d94e'

export const GLASS_POSITIONS = [
  { key: 'top-left', label: 'Top left' },
  { key: 'top-center', label: 'Top centre' },
  { key: 'top-right', label: 'Top right' },
  { key: 'bottom-left', label: 'Bottom left' },
  { key: 'bottom-center', label: 'Bottom centre' },
  { key: 'bottom-right', label: 'Bottom right' },
]
export const GLASS_DEFAULTS = { position: 'top-center', tint: 0.55, perfUs: 'bat', perfThem: 'bat' }
export const GLASS_FOCUS = { x: 50, y: 50, scale: 1 }

const parts = (position) => {
  const [v, h] = String(position || '').split('-')
  return { top: v !== 'bottom', side: h === 'left' || h === 'right' ? h : 'center' }
}

// Every measurement the layout and its sponsor slot share. All three post
// shapes are 1080 wide; the card keeps its width and the extra height goes to
// type size and breathing room, and the story keeps clear of the app's chrome.
export function glassGeo(width = 1080, height = 1080, position = 'top-center') {
  const A = aspectOf(width, height)
  const { top, side } = parts(position)
  const f = pick(A, { square: 1, portrait: 1.06, story: 1.2 })
  const edge = pick(A, { square: 52, portrait: 54, story: 56 })
  // A story's top carries the profile row and its bottom the reply bar.
  const topM = pick(A, { square: 52, portrait: 56, story: 210 })
  const botM = pick(A, { square: 52, portrait: 56, story: 270 })
  const gapP = Math.round(20 * f)
  const bw = side === 'center' ? width - edge * 2 : pick(A, { square: 500, portrait: 520, story: 560 })
  const panelW = side === 'center' ? (bw - gapP) / 2 : bw
  const s = (panelW / 482) * f
  const headH = Math.round(70 * f)
  const headGap = Math.round(28 * f)
  const panelH = Math.round(246 * s)
  const blockH = headH + headGap + (side === 'center' ? panelH : panelH * 2 + gapP)
  const x = side === 'right' ? width - edge - bw : edge
  const y = top ? topM : height - botM - blockH
  return { A, f, s, top, side, edge, topM, botM, gapP, bw, panelW, headH, headGap, panelH, blockH, x, y }
}

// The sponsor grid sits at the free end of the photo, on the card's own side
// (right for a centred card), with a small label above it. Wider for more logos.
export function glassSponsorSlot(width = 1080, height = 1080, count = 1, opts = {}) {
  const g = glassGeo(width, height, opts.position)
  const n = Math.max(1, count)
  const w = Math.round((n <= 1 ? 300 : 480) * g.f)
  const h = Math.round((n <= 4 ? 110 : 210) * g.f)
  const labelH = Math.round(34 * g.f)
  const x = g.side === 'left' ? g.edge : width - g.edge - w
  // Free end: the bottom when the card is at the top, the top when it is at the bottom.
  const y = g.top ? height - g.botM - h : g.topM + labelH
  return { x, y, w, h, pad: 4, gap: 22, panel: 'none', _labelH: labelH }
}

// 'MINTER-BROWN' -> 'Minter-Brown'. Names that already carry lower case are left alone.
function nice(s) {
  const t = String(s || '').trim()
  if (!t || t !== t.toUpperCase()) return t
  return t.toLowerCase().replace(/(^|[\s\-'])([a-z])/g, (m, a, b) => a + b.toUpperCase()).replace(/^Mc([a-z])/, (m, c) => 'Mc' + c.toUpperCase())
}

// One performer as a first name and a surname. The scorecard import carries
// both; a hand-typed "J. BARENDSE" is split on its last word.
function nameParts(p) {
  if (p.first && p.sn) return { first: nice(p.first), last: nice(p.sn) }
  const words = String(p.n || '').trim().split(/\s+/).filter(Boolean)
  if (words.length <= 1) return { first: '', last: nice(words[0] || '') }
  return { first: words.slice(0, -1).join(' '), last: nice(words[words.length - 1]) }
}

// Figures: batters carry "53 (100)" already (runs, balls); a bowler's "2/42"
// becomes "2-42" with the overs in the brackets when the import has them.
function figures(p, kind) {
  const line = String(p.l || '').trim()
  if (kind === 'bowl') {
    const main = line.replace('/', '-')
    return { main, sub: p.o ? String(p.o) : '', hot: parseInt(line, 10) >= 5 }
  }
  const m = line.match(/^(.*?)\s*\((.*)\)\s*$/)
  const main = m ? m[1] : line
  return { main, sub: m ? m[2] : '', hot: parseInt(main, 10) >= 100 }
}

// "4/242" reads "4-242"; nothing at all (or a dash) means that side has not batted.
function scoreOf(score) {
  const s = String(score || '').trim()
  return !s || s === '—' || s === '-' ? '' : s.replace('/', '-')
}

const Trophy = ({ size }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ display: 'block', flexShrink: 0 }}>
    <path d="M7 3h10v5a5 5 0 0 1-10 0V3z" fill={GOLD} />
    <path d="M7 4.5H4v1.5a3.5 3.5 0 0 0 3.2 3.5M17 4.5h3v1.5a3.5 3.5 0 0 1-3.2 3.5" fill="none" stroke={GOLD} strokeWidth="1.6" />
    <rect x="10.8" y="12.5" width="2.4" height="4" fill={GOLD} />
    <rect x="7.5" y="17" width="9" height="3" rx="1" fill={GOLD} />
  </svg>
)
Trophy.displayName = 'Trophy'

export function ResultGlass({
  palette = {}, width = 1080, height = 1080, result: r = {}, look, photo, focus, sponsorCount = 0,
}) {
  const L = { ...GLASS_DEFAULTS, ...(look || {}) }
  const g = glassGeo(width, height, L.position)
  const { s, f, panelW, panelH, top, side } = g
  const tint = Math.max(0, Math.min(1, Number(L.tint)))
  const fx = { ...GLASS_FOCUS, ...(focus || {}) }
  const us = r.us || {}
  const them = r.them || {}

  // The photo, drawn at the post's own size wherever it is wanted. The glass
  // panes use the same box and the same framing, offset so each shows the part
  // of the photo that is behind it.
  const photoImg = (style) => (
    <img src={photo} alt="" style={{
      position: 'absolute', left: 0, top: 0, width, height, objectFit: 'cover', display: 'block',
      ...heroFocusStyle(fx), ...style,
    }} />
  )

  // Which end of the post the card, the blur and the free end are.
  const cardX = g.x, cardY = g.y
  const fade = Math.round(pick(g.A, { square: 190, portrait: 230, story: 320 }))
  let maskImage
  if (side === 'center') {
    maskImage = top
      ? `linear-gradient(180deg, #000 0, #000 ${cardY + g.blockH + 30}px, transparent ${cardY + g.blockH + 30 + fade}px)`
      : `linear-gradient(0deg, #000 0, #000 ${height - cardY + 30}px, transparent ${height - cardY + 30 + fade}px)`
  } else {
    // A side card gets a soft pool of blur around itself, not a band across the post.
    const cx = cardX + g.bw / 2
    const cy = cardY + g.blockH / 2
    maskImage = `radial-gradient(ellipse ${Math.round(g.bw * 0.95)}px ${Math.round(g.blockH * 0.82)}px at ${Math.round(cx)}px ${Math.round(cy)}px, #000 58%, transparent 100%)`
  }
  // A soft shade at the free end so a white logo and the BetterCricket mark hold.
  const endShade = Math.round(pick(g.A, { square: 300, portrait: 340, story: 420 }))

  const sp = glassSponsorSlot(width, height, Math.max(1, sponsorCount), { position: L.position })
  const creditH = Math.round(46 * f)
  const creditY = top ? height - g.botM - creditH : g.topM
  // The BetterCricket logo takes the other side from the sponsors.
  const creditLeft = side === 'left' ? false : true

  // AutoFitText only re-measures when its own props change, so a move to another
  // position (new column widths) has to arrive as a dependency.
  const fitKey = [L.position, width, height]

  const winUs = r.winner === 'us'
  const winThem = r.winner === 'them'
  const headParts = {
    grade: String(r.grade || r.comp || '').toUpperCase(),
    venue: String(r.venue || '').toUpperCase(),
    round: String(r.round || '').toUpperCase(),
    date: String(r.date || '').toUpperCase(),
  }

  // One type size for every row on the card, from the longest name.
  const rowFs = Math.round(21 * s)
  const nameRoom = panelW - Math.round(44 * s) - Math.round(150 * s)
  const all = [...(r.topBat?.us || []), ...(r.topBat?.them || []), ...(r.topBowl?.us || []), ...(r.topBowl?.them || [])]
  const longest = all.reduce((m, p) => { const n = nameParts(p); return Math.max(m, `${n.first} ${n.last}`.trim().length) }, 10)
  const nameFs = Math.max(12, Math.min(rowFs, Math.floor(nameRoom / (0.56 * longest))))

  // One size for both team names too, from the longer: a name that shrinks on its
  // own beside one that did not reads as a mistake. AutoFitText stays as the net.
  const teamRoom = panelW - Math.round(44 * s) - Math.round(34 * s) - Math.round(165 * s)
  const longTeam = Math.max(String(us.name || '').length, String(them.name || '').length, 8)
  const teamFs = Math.max(13, Math.min(Math.round(25 * s), Math.floor(teamRoom / (0.66 * longTeam))))

  const glassPane = (x, y, w, h, key, body) => (
    <div key={key} data-layer={key} style={{
      position: 'absolute', left: x, top: y, width: w, height: h, boxSizing: 'border-box', overflow: 'hidden',
      borderRadius: Math.round(14 * s), border: '1.5px solid rgba(255,255,255,0.34)',
      boxShadow: '0 14px 40px rgba(0,0,0,0.38), inset 0 1.5px 0 rgba(255,255,255,0.5), inset 0 -1px 0 rgba(255,255,255,0.12)',
      background: photo ? 'transparent' : 'rgba(255,255,255,0.09)',
    }}>
      {photo && (
        <div style={{ position: 'absolute', left: 0, top: 0, width: w, height: h, overflow: 'hidden' }}>
          {photoImg({ left: -x - 1.5, top: -y - 1.5, filter: 'blur(26px) saturate(1.4) brightness(0.78)' })}
        </div>
      )}
      <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(135deg, rgba(255,255,255,0.26) 0%, rgba(255,255,255,0.08) 38%, rgba(255,255,255,0.03) 62%, rgba(255,255,255,0.16) 100%)' }} />
      <div style={{ position: 'absolute', inset: 0, background: 'rgba(8,12,20,0.16)' }} />
      <div style={{ position: 'relative', width: '100%', height: '100%' }}>{body}</div>
    </div>
  )

  const teamPanel = (t, other, win, kind, rows, key, x, y) => {
    const score = scoreOf(t.score)
    // Yet to bat only when the other side has a score; with neither, the rows just wait for data.
    const yet = !score && !!scoreOf(other.score)
    const bat = kind !== 'bowl'
    const pad = Math.round(22 * s)
    const headHt = Math.round(76 * s)
    const rowHt = Math.round(46 * s)
    return glassPane(x, y, panelW, panelH, key, (
      <>
        <div style={{ height: headHt, padding: `0 ${pad}px`, display: 'flex', alignItems: 'center', gap: Math.round(10 * s), boxSizing: 'border-box' }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: Math.round(10 * s) }}>
            <div style={{ minWidth: 0, flexShrink: 1 }}>
              <AutoFitText text={String(t.name || '').toUpperCase()} max={teamFs} min={12} lines={1} measureDeps={[teamFs, ...fitKey]}
                style={{ fontWeight: win ? 800 : 500, letterSpacing: 0.4, lineHeight: 1.1, color: '#fff' }} />
            </div>
            {win && <Trophy size={Math.round(22 * s)} />}
          </div>
          {score && (
            <div style={{ flexShrink: 0, display: 'flex', alignItems: 'baseline', gap: Math.round(5 * s), fontWeight: win ? 800 : 500, color: '#fff' }}>
              <span style={{ fontSize: Math.round(31 * s), lineHeight: 1, letterSpacing: 0.3 }}>{score}</span>
              {t.overs ? <span style={{ fontSize: Math.round(14 * s), fontWeight: 500, opacity: 0.7 }}>({t.overs})</span> : null}
            </div>
          )}
        </div>
        <div style={{ margin: `0 ${pad}px`, borderTop: '1.5px dashed rgba(255,255,255,0.4)' }} />
        <div style={{ padding: `${Math.round(8 * s)}px ${pad}px 0` }}>
          {yet ? (
            <div style={{ height: rowHt * 3, display: 'flex', alignItems: 'center', fontSize: Math.round(20 * s), fontWeight: 500, color: '#fff', opacity: 0.75 }}>Yet to bat</div>
          ) : rows.slice(0, 3).map((p, i) => {
            const n = nameParts(p)
            const fg = figures(p, bat ? 'bat' : 'bowl')
            return (
              <div key={i} style={{ height: rowHt, display: 'flex', alignItems: 'center', gap: Math.round(10 * s), color: '#fff' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <AutoFitText max={nameFs} min={11} lines={1} measureDeps={[p.n, p.first, p.sn, nameFs, ...fitKey]}
                    style={{ lineHeight: 1.1, letterSpacing: 0.2, color: '#fff' }}>
                    {n.first ? <span style={{ fontWeight: 400, opacity: 0.92 }}>{n.first} </span> : null}
                    <span style={{ fontWeight: 800 }}>{n.last}</span>
                  </AutoFitText>
                </div>
                <div style={{ flexShrink: 0, display: 'flex', alignItems: 'baseline', gap: Math.round(4 * s), color: fg.hot ? GOLD : '#fff' }}>
                  <span style={{ fontSize: Math.round(22 * s), fontWeight: 700, lineHeight: 1 }}>{fg.main}</span>
                  {fg.sub ? <span style={{ fontSize: Math.round(12 * s), fontWeight: 500, opacity: 0.7, color: '#fff' }}>({fg.sub})</span> : null}
                </div>
              </div>
            )
          })}
        </div>
      </>
    ))
  }

  const rowsFor = (who, kind) => (kind === 'bowl' ? (r.topBowl?.[who] || []) : (r.topBat?.[who] || []))
  const usY = cardY + g.headH + g.headGap
  const usX = cardX
  const themX = side === 'center' ? cardX + panelW + g.gapP : cardX
  const themY = side === 'center' ? usY : usY + panelH + g.gapP

  const headFs = Math.round(30 * f)
  const subFs = Math.round(19 * f)
  const leftW = side === 'center' ? Math.round(g.bw * 0.5) : Math.round(g.bw * 0.56)
  const rightW = side === 'center' ? Math.round(g.bw * 0.5) : g.bw - leftW - Math.round(16 * f)

  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden', color: '#fff', fontFamily: FONT,
      background: `linear-gradient(160deg, ${mixHex(palette.primary || '#10243f', '#ffffff', 0.1)} 0%, ${palette.primary || '#10243f'} 55%, ${mixHex(palette.primary || '#10243f', '#000000', 0.35)} 100%)`,
    }}>
      {photo && (
        <div data-layer="Background photo" style={{ position: 'absolute', left: 0, top: 0, width, height, overflow: 'hidden' }}>
          {photoImg({})}
        </div>
      )}

      <div data-layer="Blur and tint" style={{
        position: 'absolute', left: 0, top: 0, width, height, overflow: 'hidden',
        WebkitMaskImage: maskImage, maskImage,
      }}>
        {photo && photoImg({ filter: 'blur(22px)', transform: `${heroFocusStyle(fx).transform || ''} scale(1.06)`.trim(), transformOrigin: heroFocusStyle(fx).transformOrigin || 'center' })}
        <div style={{ position: 'absolute', inset: 0, background: `rgba(0,0,0,${tint})` }} />
      </div>

      <div data-layer="Edge shade" style={{
        position: 'absolute', left: 0, width, height: endShade,
        ...(top ? { bottom: 0, background: 'linear-gradient(0deg, rgba(0,0,0,0.5), rgba(0,0,0,0))' } : { top: 0, background: 'linear-gradient(180deg, rgba(0,0,0,0.5), rgba(0,0,0,0))' }),
      }} />

      <div data-layer="Match header" style={{
        position: 'absolute', left: cardX, top: cardY, width: g.bw, height: g.headH, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: Math.round(16 * f),
        textShadow: '0 2px 14px rgba(0,0,0,0.5)',
      }}>
        <div style={{ width: leftW, minWidth: 0 }}>
          <AutoFitText text={headParts.grade} max={headFs} min={14} lines={1} measureDeps={fitKey} style={{ fontWeight: 800, letterSpacing: 0.6, lineHeight: 1.15, color: '#fff' }} />
          <AutoFitText text={headParts.venue} max={subFs} min={11} lines={1} measureDeps={fitKey} style={{ fontWeight: 400, letterSpacing: 1.2, lineHeight: 1.3, color: '#fff', opacity: 0.78 }} />
        </div>
        <div style={{ width: rightW, minWidth: 0, textAlign: 'right' }}>
          <AutoFitText text={headParts.round} max={headFs} min={14} lines={1} measureDeps={fitKey} style={{ fontWeight: 800, letterSpacing: 0.6, lineHeight: 1.15, color: '#fff' }} />
          <AutoFitText text={headParts.date} max={subFs} min={11} lines={1} measureDeps={fitKey} style={{ fontWeight: 400, letterSpacing: 1.2, lineHeight: 1.3, color: '#fff', opacity: 0.78 }} />
        </div>
      </div>

      {teamPanel(us, them, winUs, L.perfUs, rowsFor('us', L.perfUs), 'Our scorecard', usX, usY)}
      {teamPanel(them, us, winThem, L.perfThem, rowsFor('them', L.perfThem), 'Their scorecard', themX, themY)}

      {sponsorCount > 0 && (
        <div data-layer="Sponsor label" style={{
          position: 'absolute', left: sp.x, width: sp.w, top: sp.y - sp._labelH, height: sp._labelH,
          display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center',
          fontSize: Math.round(14 * f), fontWeight: 600, letterSpacing: 1.4, textTransform: 'uppercase', textShadow: '0 1px 8px rgba(0,0,0,0.6)',
        }}>Proudly sponsored by</div>
      )}

      <div data-layer="BetterCricket logo" style={{
        position: 'absolute', top: creditY, height: creditH, display: 'flex', alignItems: 'center',
        ...(creditLeft ? { left: g.edge } : { right: g.edge }),
      }}>
        <CreditMark ink="#ffffff" h={creditH} />
      </div>
    </LayerRoot>
  )
}
ResultGlass.displayName = 'ResultGlass'

// Where this file's layout keeps the sponsor grid (see sponsorSlots.js).
export const SPONSOR_SLOTS = { RS7: glassSponsorSlot }
