// ─────────────────────────────────────────────────────────────────────────────
// MORE DESIGN LAYOUTS (v9.156.0), from the formats other clubs post most:
//
//   DL10 Signed Stamp     Announcement   duotone photo, a rubber stamp across it
//   DL11 Quote Card       Announcement   halftone portrait, giant quote marks, the quote
//   DL12 Birthday         Announcement   confetti, outlined cut-out, a handwritten greeting
//   DL13 Squad Update     Announcement   muted photo, a status pill, a plain sober layout
//   DL14 Countdown        Announcement   one huge 3D number, the event under it
//   DL15 Stat Hero        Player of the Match   the first figure huge, the player in front of it
//   DL16 Coin Toss        Toss           a split post, the toss winner's crest on a coin
//   DL17 Big Number       Milestones     the first milestone's number, the rest as rows
//   DL18 The Oval         Team of the Week   players round a cricket oval
//   DL19 Split Final      Final Score    a diagonal split in two colours, giant scores
//   DL20 Numbered List    Lineup         outlined numbers down the side, a duotone hero
//
// Same rules as design-templates.jsx: every root child carries data-layer, each
// layout keeps its sponsor strip clear (slotOf), photos go through FramedImage.
// ─────────────────────────────────────────────────────────────────────────────
import { AutoFitText, ClubLogo, CreditMark, heroSrcOf, featuredOf } from './cricket-templates'
import { pick } from './postAspect'
import { LayerRoot } from './postLayers'
import { niceName } from './card-kit'
import { pc, pt, inkOn, registerParts, colorPart, textPart } from './layoutParts'
import { usePostLook } from './postLook'
import FramedImage from './FramedImage'
import { halftoneDots, grungePaths, burstPaths, rng } from './designFx'
import { geo, slotOf, joinDot, upper, readable, Paths, resolver, keptLook, FONT, WEIGHT, MONO } from './design-templates'
import { PastStrip, hasPast } from './pastMeetings'

const Credit = ({ g, ink }) => (
  <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink={ink} h={Math.round(30 * g.f)} /></div>
)
const Root = ({ width, height, bg, ink, children }) => (
  <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: bg, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>{children}</LayerRoot>
)
const nameOf = (p) => ({ first: upper(niceName(p?.first || '')), last: upper(niceName(p?.last || '')) })
// A photo, or the club crest where there is none.
function Picture({ layer = 'Player', src, x, y, w, h, fx, fit = 'contain', pos = 'center bottom', resolve, team, ink, style }) {
  if (!src) {
    const size = Math.round(Math.min(w, h) * 0.6)
    return (
      <div data-layer="Club mark" style={{ position: 'absolute', left: x + (w - size) / 2, top: y + (h - size) / 2, opacity: 0.9 }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={size} shape="shield" />
      </div>
    )
  }
  return (
    <div data-layer={layer} style={{ position: 'absolute', left: x, top: y, width: w, height: h, ...style }}>
      <FramedImage item={{ w, h, fit, objPos: pos, fx }} src={src} resolve={resolve} />
    </div>
  )
}
function Halftone({ layer = 'Halftone', w, h, x = 0, y = 0, color, size = 20, opacity = 0.2 }) {
  return (
    <svg data-layer={layer} width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ position: 'absolute', left: x, top: y, opacity, pointerEvents: 'none' }}>
      <g fill={color}>{halftoneDots(w, h, size).map(([cx, cy, r], i) => <circle key={i} cx={cx} cy={cy} r={r} />)}</g>
    </svg>
  )
}

// ── DL10 Signed Stamp ────────────────────────────────────────────────────────
export function SignedStamp({ width = 1080, height = 1080, team = {}, palette = {}, announcement = {}, parts }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f, A } = g
  const a = announcement || {}
  const tone = pc(parts, 'dl10Tone', palette.primary || '#0b1530')
  const stampC = pc(parts, 'dl10Stamp', palette.accent || '#e1251b')
  const ink = '#ffffff'
  const resolve = resolver(palette)
  const { first, last } = nameOf(a.player)
  const word = upper(pt(parts, 'dl10Word', a.kind || 'SIGNED'))
  const nameY = g.slotY - Math.round(250 * f)
  return (
    <Root width={width} height={height} bg={tone} ink={ink}>
      <Picture layer="Photo" src={heroSrcOf(a.player)} x={0} y={0} w={width} h={nameY + Math.round(80 * f)} fit="cover" pos="center top" resolve={resolve} team={team} ink={ink}
        fx={{ tone: 'duotone', duoDark: '#050608', duoLight: tone, contrast: 18 }} />
      <div data-layer="Shade" style={{ position: 'absolute', left: 0, right: 0, top: nameY - Math.round(200 * f), bottom: 0, background: `linear-gradient(180deg, ${tone}00, ${tone} 45%)` }} />
      <div data-layer="Stamp" style={{
        position: 'absolute', left: width * 0.5 - Math.round(330 * f), top: Math.round(height * pick(A, { square: 0.3, portrait: 0.32, story: 0.34 })), width: Math.round(660 * f),
        border: `${Math.round(12 * f)}px solid ${stampC}`, outline: `${Math.round(4 * f)}px solid ${stampC}`, outlineOffset: Math.round(8 * f),
        transform: 'rotate(-12deg)', textAlign: 'center', color: stampC, padding: `${Math.round(10 * f)}px 0`, mixBlendMode: 'screen',
      }}>
        <AutoFitText text={word} max={Math.round(170 * f)} min={40} lines={1} measureDeps={[word, width]} style={{ lineHeight: 1, letterSpacing: 6 }} />
        {texture && <Paths layer="Stamp wear" paths={grungePaths(Math.round(640 * f), Math.round(190 * f), 3)} color={tone} width={Math.round(640 * f)} height={Math.round(190 * f)} opacity={0.9} />}
      </div>
      <div data-layer="Name" style={{ position: 'absolute', left: 56, right: 56, top: nameY }}>
        {first && <div style={{ fontSize: Math.round(44 * f), letterSpacing: 6, lineHeight: 1 }}>{first}</div>}
        <AutoFitText text={last || '—'} max={Math.round(140 * f)} min={40} lines={1} measureDeps={[last, width]} style={{ lineHeight: 1 }} />
        <div style={{ fontFamily: MONO, fontSize: Math.round(20 * f), letterSpacing: 2, color: stampC, marginTop: 10 }}>{upper([a.headline, a.subheadline].filter(Boolean).join(' · '))}</div>
      </div>
      <div data-layer="Club logo" style={{ position: 'absolute', left: 48, top: g.top }}><ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(90 * f)} shape="shield" /></div>
      <Credit g={g} ink={ink} />
    </Root>
  )
}
SignedStamp.displayName = 'SignedStamp'

// ── DL11 Quote Card ──────────────────────────────────────────────────────────
export function QuoteCard({ width = 1080, height = 1080, team = {}, palette = {}, announcement = {}, parts }) {
  const g = geo(width, height)
  const { f } = g
  const a = announcement || {}
  const ground = pc(parts, 'dl11Ground', palette.primary || '#0b1530')
  const markC = pc(parts, 'dl11Mark', readable(palette.accent || '#ffc233', ground, '#ffffff'))
  const ink = '#ffffff'
  const resolve = resolver(palette)
  const { first, last } = nameOf(a.player)
  const quote = a.headline || 'Add the quote as the headline.'
  const photoW = Math.round(width * 0.5)
  const photoTop = g.top + Math.round(40 * f)
  const photoH = g.slotY - photoTop
  const textW = width - photoW - 40
  return (
    <Root width={width} height={height} bg={ground} ink={ink}>
      <Halftone w={width} h={height} color={ink} size={Math.round(18 * f)} opacity={0.06} />
      <Picture src={heroSrcOf(a.player)} x={width - photoW + 20} y={photoTop} w={photoW} h={photoH} resolve={resolve} team={team} ink={ink}
        fx={{ tone: 'mono', contrast: 30, grain: 12 }} />
      <Halftone layer="Photo dots" x={width - photoW} y={photoTop} w={photoW} h={photoH} color={ground} size={Math.round(10 * f)} opacity={0.35} />
      <div data-layer="Quote marks" style={{ position: 'absolute', left: 40, top: g.top - Math.round(30 * f), fontSize: Math.round(340 * f), lineHeight: 1, color: markC, fontFamily: "'Abril Fatface', serif", fontWeight: 400 }}>“</div>
      <div data-layer="Quote" style={{ position: 'absolute', left: 56, width: textW - 20, top: g.top + Math.round(230 * f), height: Math.round(g.slotY - g.top - 470 * f) }}>
        <AutoFitText text={quote} max={Math.round(pick(g.A, { square: 70, portrait: 80, story: 92 }) * f)} min={24} lines={pick(g.A, { square: 7, portrait: 8, story: 10 })} measureDeps={[quote, width, height]} style={{ lineHeight: 1.08, textTransform: 'none' }} />
      </div>
      <div data-layer="Who said it" style={{ position: 'absolute', left: 56, width: textW - 20, top: g.slotY - Math.round(200 * f) }}>
        <div style={{ width: Math.round(70 * f), height: 6, background: markC, marginBottom: 14 }} />
        <div style={{ fontSize: Math.round(46 * f), lineHeight: 1 }}>{[first, last].filter(Boolean).join(' ') || upper(team.name)}</div>
        {a.subheadline && <div style={{ fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 2, opacity: 0.8, marginTop: 8 }}>{upper(a.subheadline)}</div>}
      </div>
      <div data-layer="Club logo" style={{ position: 'absolute', left: 56, top: g.slotY - Math.round(310 * f) }}><ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(70 * f)} shape="shield" /></div>
      <Credit g={g} ink={ink} />
    </Root>
  )
}
QuoteCard.displayName = 'QuoteCard'

// ── DL12 Birthday ────────────────────────────────────────────────────────────
function Confetti({ width, height, colors, seed = 4 }) {
  const r = rng(seed)
  const bits = Array.from({ length: 70 }, () => ({ x: r() * width, y: r() * height, w: 8 + r() * 18, h: 14 + r() * 26, rot: r() * 180, c: colors[Math.floor(r() * colors.length)], round: r() < 0.3 }))
  return (
    <svg data-layer="Confetti" width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
      {bits.map((b, i) => b.round
        ? <circle key={i} cx={b.x} cy={b.y} r={b.w * 0.6} fill={b.c} />
        : <rect key={i} x={b.x} y={b.y} width={b.w} height={b.h} fill={b.c} transform={`rotate(${b.rot} ${b.x} ${b.y})`} />)}
    </svg>
  )
}
export function Birthday({ width = 1080, height = 1080, team = {}, palette = {}, announcement = {}, parts }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f } = g
  const a = announcement || {}
  const ground = pc(parts, 'dl12Ground', palette.primary || '#0b1530')
  const accent = palette.accent || '#ffc233'
  const ink = '#ffffff'
  const resolve = resolver(palette)
  const { first, last } = nameOf(a.player)
  const greet = pt(parts, 'dl12Greet', 'Happy birthday')
  const heroTop = g.top + Math.round(190 * f)
  const heroH = g.slotY - Math.round(230 * f) - heroTop
  return (
    <Root width={width} height={height} bg={ground} ink={ink}>
      {texture && <Paths layer="Burst" paths={burstPaths(width, height, 9)} color={ink} width={width} height={height} opacity={0.06} />}
      <Confetti width={width} height={height} colors={[accent, '#ffffff', palette.secondary || '#3aa0ff', '#ff5d8f']} />
      <div data-layer="Greeting" style={{ position: 'absolute', left: 40, right: 40, top: g.top + Math.round(20 * f), textAlign: 'center', fontFamily: "'Permanent Marker', cursive", fontWeight: 400, fontSize: Math.round(110 * f), lineHeight: 1, color: readable(accent, ground, '#ffffff'), transform: 'rotate(-4deg)' }}>{greet}</div>
      <Picture src={heroSrcOf(a.player)} x={width * 0.18} y={heroTop} w={width * 0.64} h={heroH} resolve={resolve} team={team} ink={ink}
        fx={{ outline: { width: Math.round(10 * f), color: 'white' }, shadow: { x: 0, y: 18, blur: 30, opacity: 50 } }} />
      <div data-layer="Name" style={{ position: 'absolute', left: 48, right: 48, top: g.slotY - Math.round(210 * f), textAlign: 'center' }}>
        <AutoFitText text={[first, last].filter(Boolean).join(' ') || '—'} max={Math.round(110 * f)} min={36} lines={1} measureDeps={[first, last, width]} style={{ lineHeight: 1 }} />
        <div style={{ fontFamily: MONO, fontSize: Math.round(22 * f), letterSpacing: 3, color: readable(accent, ground, '#ffffff'), marginTop: 10 }}>{upper([a.headline, a.subheadline].filter(Boolean).join(' · ')) || upper(team.name)}</div>
      </div>
      <div data-layer="Club logo" style={{ position: 'absolute', left: 40, top: g.slotY - Math.round(100 * f) }}><ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(64 * f)} shape="shield" /></div>
      <Credit g={g} ink={ink} />
    </Root>
  )
}
Birthday.displayName = 'Birthday'

// ── DL13 Squad Update ────────────────────────────────────────────────────────
export function SquadUpdate({ width = 1080, height = 1080, team = {}, palette = {}, announcement = {}, parts }) {
  const g = geo(width, height)
  const { f } = g
  const a = announcement || {}
  const ground = pc(parts, 'dl13Ground', '#1b1d22')
  const pill = pc(parts, 'dl13Pill', '#d97706')
  const ink = '#f2f2f2'
  const resolve = resolver(palette)
  const { first, last } = nameOf(a.player)
  const photoH = Math.round((g.slotY - g.top) * 0.6)
  return (
    <Root width={width} height={height} bg={ground} ink={ink}>
      <Picture layer="Photo" src={heroSrcOf(a.player)} x={0} y={0} w={width} h={g.top + photoH} fit="cover" pos="center top" resolve={resolve} team={team} ink={ink}
        fx={{ saturation: -70, contrast: -6, brightness: -12 }} />
      <div data-layer="Shade" style={{ position: 'absolute', left: 0, right: 0, top: g.top + photoH - Math.round(260 * f), height: Math.round(262 * f), background: `linear-gradient(180deg, ${ground}00, ${ground})` }} />
      <div data-layer="Header" style={{ position: 'absolute', left: 48, right: 48, top: g.top, display: 'flex', alignItems: 'center', gap: 14, fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 3 }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(54 * f)} shape="shield" />
        <span>{upper(pt(parts, 'dl13Head', 'SQUAD UPDATE'))}</span>
      </div>
      <div data-layer="Status" style={{ position: 'absolute', left: 56, top: g.top + photoH - Math.round(40 * f) }}>
        <span style={{ display: 'inline-block', background: pill, color: inkOn(pill), padding: `${Math.round(8 * f)}px ${Math.round(18 * f)}px`, fontSize: Math.round(30 * f), letterSpacing: 2, borderRadius: 999 }}>{upper(a.kind || 'INJURY UPDATE')}</span>
      </div>
      <div data-layer="Name and detail" style={{ position: 'absolute', left: 56, right: 56, top: g.top + photoH + Math.round(40 * f) }}>
        <div style={{ fontSize: Math.round(36 * f), opacity: 0.8, lineHeight: 1 }}>{first}</div>
        <AutoFitText text={last || '—'} max={Math.round(110 * f)} min={36} lines={1} measureDeps={[last, width]} style={{ lineHeight: 1 }} />
        <div style={{ fontSize: Math.round(40 * f), color: pill, marginTop: 10, lineHeight: 1.1 }}>{upper(a.headline || '')}</div>
        {a.subheadline && <div style={{ fontFamily: "'Inter', sans-serif", fontWeight: 500, fontSize: Math.round(24 * f), lineHeight: 1.35, opacity: 0.85, marginTop: 8 }}>{a.subheadline}</div>}
      </div>
      <Credit g={g} ink={ink} />
    </Root>
  )
}
SquadUpdate.displayName = 'SquadUpdate'

// ── DL14 Countdown ───────────────────────────────────────────────────────────
export function Countdown({ width = 1080, height = 1080, team = {}, palette = {}, announcement = {}, parts }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f } = g
  const a = announcement || {}
  const ground = pc(parts, 'dl14Ground', palette.primary || '#0b1530')
  const numC = pc(parts, 'dl14Number', readable(palette.accent || '#ffc233', ground, '#ffffff'))
  const ink = '#ffffff'
  const resolve = resolver(palette)
  const num = String(a.headline || '3').toUpperCase()
  const numFs = Math.round(Math.min(620 * f, (width * 0.9) / Math.max(1, num.length) * 1.45))
  const numTop = g.top + Math.round(120 * f)
  const depth = Math.round(26 * f)
  return (
    <Root width={width} height={height} bg={ground} ink={ink}>
      {texture && <Paths layer="Burst" paths={burstPaths(width, height, 15)} color={ink} width={width} height={height} opacity={0.07} />}
      <Picture src={heroSrcOf(a.player)} x={width * 0.42} y={g.top + Math.round(40 * f)} w={width * 0.58} h={g.slotY - g.top - Math.round(200 * f)} resolve={resolve} team={team} ink={ink}
        fx={{ tone: 'mono', contrast: 20 }} style={{ opacity: a.player ? 0.85 : 0.35 }} />
      <div data-layer="Number" style={{
        position: 'absolute', left: 40, right: 40, top: numTop, textAlign: 'center', fontSize: numFs, lineHeight: 0.9, letterSpacing: -4, color: numC,
        textShadow: Array.from({ length: depth }, (_, i) => `${i + 1}px ${i + 1}px 0 #00000088`).join(','), WebkitTextStroke: `${Math.round(3 * f)}px #ffffff`, paintOrder: 'stroke fill',
      }}>{num}</div>
      <div data-layer="Unit" style={{ position: 'absolute', left: 48, right: 48, top: numTop + numFs * 0.92, textAlign: 'center', fontSize: Math.round(70 * f), letterSpacing: 8, lineHeight: 1 }}>{upper(a.kind || 'DAYS TO GO')}</div>
      <div data-layer="Event" style={{ position: 'absolute', left: 48, right: 48, top: g.slotY - Math.round(110 * f), textAlign: 'center', fontFamily: MONO, fontSize: Math.round(24 * f), letterSpacing: 3, color: numC }}>{upper(a.subheadline || team.name)}</div>
      <div data-layer="Club logo" style={{ position: 'absolute', left: 48, top: g.top }}><ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(80 * f)} shape="shield" /></div>
      <Credit g={g} ink={ink} />
    </Root>
  )
}
Countdown.displayName = 'Countdown'

// ── DL15 Stat Hero ───────────────────────────────────────────────────────────
export function StatHero({ width = 1080, height = 1080, team = {}, palette = {}, motm = {}, parts }) {
  const g = geo(width, height)
  const { f } = g
  const ground = pc(parts, 'dl15Ground', palette.primary || '#0b1530')
  const big = pc(parts, 'dl15Figure', readable(palette.accent || '#ffc233', ground, '#ffffff'))
  const ink = '#ffffff'
  const resolve = resolver(palette)
  const stats = (motm.stats || []).filter((s) => s.value)
  // With no figures typed yet the big word is the award itself.
  const lead = stats[0] || { value: pt(parts, 'dl15Empty', 'POTM'), label: '' }
  const { first, last } = nameOf(motm.player)
  const figTop = g.top + Math.round(60 * f)
  const figFs = Math.round(Math.min(560 * f, (width * 0.95) / Math.max(1, String(lead.value).length) * 1.5))
  return (
    <Root width={width} height={height} bg={ground} ink={ink}>
      <Halftone w={width} h={height} color={ink} size={Math.round(22 * f)} opacity={0.07} />
      <div data-layer="Big figure" style={{ position: 'absolute', left: 20, right: 20, top: figTop, textAlign: 'center', fontSize: figFs, lineHeight: 0.85, letterSpacing: -6, color: big }}>{upper(lead.value)}</div>
      <Picture src={heroSrcOf(motm.player)} x={width * 0.15} y={g.top + Math.round(120 * f)} w={width * 0.7} h={g.slotY - Math.round(250 * f) - g.top - Math.round(120 * f)} resolve={resolve} team={team} ink={ink}
        fx={{ outline: { width: Math.round(5 * f), color: 'white' }, shadow: { x: 0, y: 20, blur: 40, opacity: 60 } }} />
      <div data-layer="Big figure outline" style={{ position: 'absolute', left: 20, right: 20, top: figTop, textAlign: 'center', fontSize: figFs, lineHeight: 0.85, letterSpacing: -6, color: 'transparent', WebkitTextStroke: `${Math.round(3 * f)}px ${big}`, pointerEvents: 'none' }}>{upper(lead.value)}</div>
      <div data-layer="Name and figures" style={{ position: 'absolute', left: 48, right: 48, top: g.slotY - Math.round(230 * f), textAlign: 'center' }}>
        <div style={{ fontFamily: MONO, fontSize: Math.round(20 * f), letterSpacing: 4, color: big }}>{upper(pt(parts, 'dlChip', 'PLAYER OF THE MATCH'))}{lead.label ? ` · ${upper(lead.label)}` : ''}</div>
        <AutoFitText text={[first, last].filter(Boolean).join(' ') || '—'} max={Math.round(96 * f)} min={32} lines={1} measureDeps={[first, last, width]} style={{ lineHeight: 1.05 }} />
        <div style={{ display: 'flex', gap: Math.round(26 * f), justifyContent: 'center', fontSize: Math.round(28 * f), marginTop: 4 }}>
          {stats.slice(1, 4).map((s, i) => <span key={i}><span style={{ color: big }}>{upper(s.value)}</span> {upper(s.label)}</span>)}
        </div>
      </div>
      <div data-layer="Club logo" style={{ position: 'absolute', left: 48, top: g.top }}><ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(80 * f)} shape="shield" /></div>
      <Credit g={g} ink={ink} />
    </Root>
  )
}
StatHero.displayName = 'StatHero'

// ── DL16 Coin Toss ───────────────────────────────────────────────────────────
export function CoinToss({ width = 1080, height = 1080, team = {}, opponent = {}, match = {}, palette = {}, toss = {}, parts, past }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f } = g
  const usC = pc(parts, 'dl16Us', palette.primary || '#0b1530')
  const themC = pc(parts, 'dl16Them', '#2a2d33')
  const coinC = pc(parts, 'dl16Coin', '#e8c15a')
  const ink = '#ffffff'
  const theyWon = toss?.winner === 'OPPONENT'
  const winner = theyWon ? opponent : team
  const decision = upper(toss?.decision || 'BAT')
  const coin = Math.round(Math.min(width, height) * 0.42)
  const cy = g.top + Math.round((g.slotY - g.top) * 0.42)
  return (
    <Root width={width} height={height} bg={themC} ink={ink}>
      <div data-layer="Our half" style={{ position: 'absolute', inset: 0, background: usC, clipPath: 'polygon(0 0, 62% 0, 38% 100%, 0 100%)' }} />
      {texture && <Paths layer="Grain" paths={grungePaths(width, height, 6)} color="#000000" width={width} height={height} opacity={0.25} />}
      <div data-layer="Title" style={{ position: 'absolute', left: 48, right: 48, top: g.top, textAlign: 'center', fontSize: Math.round(64 * f), letterSpacing: 6 }}>{upper(pt(parts, 'dl16Title', 'THE TOSS'))}</div>
      <div data-layer="Coin" style={{
        position: 'absolute', left: width / 2 - coin / 2, top: cy - coin / 2, width: coin, height: coin, borderRadius: '50%',
        background: `radial-gradient(circle at 35% 30%, #fff6cf 0%, ${coinC} 45%, #8a6a1c 100%)`, boxShadow: `0 ${Math.round(18 * f)}px ${Math.round(40 * f)}px #00000080, inset 0 0 0 ${Math.round(14 * f)}px #00000022`,
        display: 'grid', placeItems: 'center',
      }}>
        <ClubLogo src={winner.logo} monogram={winner.monogram || ''} color="#3a2a05" size={Math.round(coin * 0.58)} shape="shield" />
      </div>
      <div data-layer="Result" style={{ position: 'absolute', left: 48, right: 48, top: cy + coin / 2 + Math.round(36 * f), textAlign: 'center' }}>
        <AutoFitText text={upper(winner.name || 'OPPONENT')} max={Math.round(84 * f)} min={30} lines={1} measureDeps={[winner.name, width]} style={{ lineHeight: 1 }} />
        <div style={{ fontSize: Math.round(44 * f), marginTop: 10, color: coinC }}>WON THE TOSS AND WILL {decision}</div>
        <div style={{ fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 2, marginTop: 12, opacity: 0.8 }}>{upper(joinDot(match.competition, match.round, match.venue))}</div>
      </div>
      <PastStrip past={past} x={48} y={g.slotY - Math.round(48 * f)} w={width - 96} f={f * 0.85} color={ink} />
      <Credit g={g} ink={ink} />
    </Root>
  )
}
CoinToss.displayName = 'CoinToss'

// ── DL17 Big Number ──────────────────────────────────────────────────────────
export function BigNumber({ width = 1080, height = 1080, team = {}, palette = {}, milestones = [], milestoneMeta = {}, parts }) {
  const g = geo(width, height)
  const { f } = g
  const ground = pc(parts, 'dl17Ground', palette.primary || '#0b1530')
  const numC = pc(parts, 'dl17Number', readable(palette.accent || '#ffc233', ground, '#ffffff'))
  const ink = '#ffffff'
  const resolve = resolver(palette)
  const [lead, ...rest] = milestones
  const others = rest.slice(0, 4)
  const rowH = Math.round(64 * f)
  const listH = others.length * rowH
  const listY = g.slotY - 14 - listH
  const nameY = listY - Math.round(150 * f)
  const value = upper(lead?.value || '100')
  const numFs = Math.round(Math.min(600 * f, (width * 0.95) / Math.max(1, value.length) * 1.5, (nameY - g.top) * 0.95))
  return (
    <Root width={width} height={height} bg={ground} ink={ink}>
      <div data-layer="Title" style={{ position: 'absolute', left: 48, right: 48, top: g.top, fontFamily: MONO, fontSize: Math.round(20 * f), letterSpacing: 4, textAlign: 'center' }}>{upper(milestoneMeta.title || 'MILESTONE')}</div>
      <div data-layer="Number" style={{ position: 'absolute', left: 20, right: 20, top: g.top + Math.round(30 * f), textAlign: 'center', fontSize: numFs, lineHeight: 0.9, letterSpacing: -8, color: numC }}>{value}</div>
      {lead && <Picture src={lead.headshot} x={width * 0.2} y={g.top + Math.round(120 * f)} w={width * 0.6} h={nameY - g.top - Math.round(100 * f)} resolve={resolve} team={team} ink={ink}
        fx={{ outline: { width: Math.round(5 * f), color: 'white' } }} />}
      <div data-layer="Lead milestone" style={{ position: 'absolute', left: 48, right: 48, top: nameY, textAlign: 'center' }}>
        <AutoFitText text={lead ? [lead.first, lead.last].filter(Boolean).join(' ').toUpperCase() : 'PICK A MILESTONE IN CONTENT'} max={Math.round(84 * f)} min={28} lines={1} measureDeps={[lead?.key, width]} style={{ lineHeight: 1 }} />
        <div style={{ fontSize: Math.round(36 * f), color: numC, marginTop: 6 }}>{upper([lead?.value, lead?.unit].filter(Boolean).join(' '))}</div>
      </div>
      <div data-layer="Other milestones" style={{ position: 'absolute', left: 60, right: 60, top: listY }}>
        {others.map((m, i) => (
          <div key={m.key || i} style={{ height: rowH, display: 'flex', alignItems: 'center', gap: 16, borderTop: `1px solid ${ink}26`, fontSize: Math.round(30 * f) }}>
            <span style={{ color: numC, width: Math.round(150 * f) }}>{upper(m.value)}</span>
            <span style={{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper([m.first, m.last].filter(Boolean).join(' '))}</span>
            <span style={{ fontFamily: MONO, fontSize: Math.round(16 * f), letterSpacing: 2, opacity: 0.8 }}>{upper(m.unit)}</span>
          </div>
        ))}
      </div>
      <div data-layer="Club logo" style={{ position: 'absolute', left: 48, top: g.top - 8 }}><ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(70 * f)} shape="shield" /></div>
      <Credit g={g} ink={ink} />
    </Root>
  )
}
BigNumber.displayName = 'BigNumber'

// ── DL18 The Oval ────────────────────────────────────────────────────────────
// The team stands round a cricket ground: an oval field with the pitch in the
// middle, the players on it in fielding-like spots, as many as were picked.
export function ovalSpots(n) {
  return Array.from({ length: n }, (_, i) => {
    const a = (-Math.PI / 2) + (i / Math.max(1, n)) * Math.PI * 2
    return { x: 0.5 + Math.cos(a) * 0.4, y: 0.5 + Math.sin(a) * 0.38 }
  })
}
export function TheOval({ width = 1080, height = 1080, team = {}, palette = {}, players = [], totw = {}, parts }) {
  const g = geo(width, height)
  const { f } = g
  const ground = pc(parts, 'dl18Ground', palette.primary || '#0b1530')
  const grass = pc(parts, 'dl18Grass', '#1f6b3a')
  const ink = '#ffffff'
  const accent = palette.accent || '#ffc233'
  const resolve = resolver(palette)
  const P = players.slice(0, 14)
  const top = g.top + Math.round(120 * f)
  const fh = g.slotY - 20 - top
  const fw = width - 80
  const chip = Math.round(Math.min(150 * f, fw / Math.max(5, P.length * 0.62)))
  const spots = ovalSpots(P.length)
  return (
    <Root width={width} height={height} bg={ground} ink={ink}>
      <div data-layer="Title" style={{ position: 'absolute', left: 48, right: 48, top: g.top, textAlign: 'center' }}>
        <div style={{ fontSize: Math.round(64 * f), lineHeight: 1 }}>{upper(pt(parts, 'dl18Title', 'TEAM OF THE WEEK'))}</div>
        <div style={{ fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 3, color: accent, marginTop: 6 }}>{upper(joinDot(totw.heading, totw.round, totw.date, totw.comp))}</div>
      </div>
      <div data-layer="Field" style={{ position: 'absolute', left: 40, top, width: fw, height: fh, borderRadius: '50%', background: `radial-gradient(ellipse at 50% 50%, ${grass} 0%, ${grass} 55%, #134a27 100%)`, border: `${Math.round(6 * f)}px solid #ffffff55` }}>
        <div style={{ position: 'absolute', left: '50%', top: '50%', width: Math.round(fw * 0.06), height: Math.round(fh * 0.26), transform: 'translate(-50%, -50%)', background: '#c9b27a', borderRadius: 4 }} />
        <div style={{ position: 'absolute', left: '50%', top: '50%', width: fw * 0.5, height: fh * 0.5, transform: 'translate(-50%, -50%)', borderRadius: '50%', border: '2px dashed #ffffff40' }} />
      </div>
      <div data-layer="Players" style={{ position: 'absolute', left: 40, top, width: fw, height: fh }}>
        {P.map((p, i) => {
          const s = spots[i]
          const src = heroSrcOf(p)
          return (
            <div key={p._id || i} data-oval-spot="" style={{ position: 'absolute', left: s.x * fw - chip / 2, top: s.y * fh - chip / 2, width: chip, textAlign: 'center' }}>
              <div style={{ width: chip, height: chip, borderRadius: '50%', overflow: 'hidden', background: ground, border: `${Math.max(3, Math.round(4 * f))}px solid ${accent}`, position: 'relative' }}>
                {src ? <FramedImage item={{ w: chip, h: chip, fit: 'cover', objPos: 'center top' }} src={src} resolve={resolve} /> : <div style={{ display: 'grid', placeItems: 'center', height: '100%' }}><ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={chip * 0.6} shape="shield" /></div>}
              </div>
              <div style={{ background: '#000000b3', padding: '3px 6px', marginTop: -10, position: 'relative', fontSize: Math.round(chip * 0.17), lineHeight: 1.1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper(p.last || p.first)}</div>
              {p.totw?.line && <div style={{ fontFamily: MONO, fontSize: Math.round(chip * 0.1), color: accent, background: '#000000b3', padding: '0 4px 3px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper(p.totw.line)}</div>}
            </div>
          )
        })}
        {!P.length && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', fontFamily: MONO, fontSize: 22, letterSpacing: 2, opacity: 0.8 }}>PULL THE ROUND IN DATA</div>}
      </div>
      <div data-layer="Club logo" style={{ position: 'absolute', left: width / 2 - 40 * f, top: top + fh / 2 - 40 * f, opacity: P.length ? 0 : 1 }}><ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(80 * f)} shape="shield" /></div>
      <Credit g={g} ink={ink} />
    </Root>
  )
}
TheOval.displayName = 'TheOval'

// ── DL19 Split Final ─────────────────────────────────────────────────────────
export function SplitFinal({ width = 1080, height = 1080, palette = {}, result: r = {}, parts, past }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f } = g
  const usC = pc(parts, 'dl19Us', palette.primary || '#0b1530')
  const themC = pc(parts, 'dl19Them', '#2a2d33')
  const ribbon = pc(parts, 'dl19Ribbon', palette.accent || '#ffc233')
  const ink = '#ffffff'
  const us = r.us || {}
  const them = r.them || {}
  const tied = r.winner === 'tie'
  const won = r.winner === 'us'
  const line = tied ? (r.resultLabel || 'MATCH TIED') : `${upper((won ? us.name : them.name) || '')} WIN ${upper(r.margin || '')}`.trim()
  const mid = g.top + Math.round((g.slotY - g.top) * 0.5)
  const scoreFs = Math.round(Math.min(220 * f, width * 0.2))
  const side = (t, isWin, top, align) => (
    <div style={{ position: 'absolute', left: 56, right: 56, top, textAlign: align }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, justifyContent: align === 'left' ? 'flex-start' : 'flex-end' }}>
        {align === 'left' && <ClubLogo src={t.logo} monogram={t.mono} color={ink} size={Math.round(70 * f)} shape="shield" />}
        <span style={{ fontSize: Math.round(40 * f), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: width * 0.6 }}>{upper(t.name)}{isWin && !tied ? ' ✓' : ''}</span>
        {align === 'right' && <ClubLogo src={t.logo} monogram={t.mono} color={ink} size={Math.round(70 * f)} shape="shield" />}
      </div>
      <div style={{ fontSize: scoreFs, lineHeight: 0.95, letterSpacing: -4, opacity: isWin || tied ? 1 : 0.7 }}>{t.score || '—'}</div>
      {t.overs && <div style={{ fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 2, opacity: 0.8 }}>{t.overs} OVERS</div>}
    </div>
  )
  return (
    <Root width={width} height={height} bg={themC} ink={ink}>
      <div data-layer="Our half" style={{ position: 'absolute', inset: 0, background: usC, clipPath: `polygon(0 0, 100% 0, 100% ${((mid - 80 * f) / height) * 100}%, 0 ${((mid + 80 * f) / height) * 100}%)` }} />
      {texture && <Paths layer="Grain" paths={grungePaths(width, height, 19)} color="#000000" width={width} height={height} opacity={0.22} />}
      {side(us, won, g.top + Math.round(40 * f), 'left')}
      {side(them, !won && !tied, mid + Math.round(60 * f), 'right')}
      <div data-layer="Ribbon" style={{ position: 'absolute', left: -40, right: -40, top: mid - Math.round(42 * f), height: Math.round(84 * f), background: ribbon, color: inkOn(ribbon), transform: 'rotate(-8.5deg)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 30, fontSize: Math.round(46 * f), letterSpacing: 3 }}>
        <span>{upper(pt(parts, 'dl19Word', 'FULL TIME'))}</span><span style={{ opacity: 0.6 }}>·</span><span style={{ whiteSpace: 'nowrap' }}>{line}</span>
      </div>
      <PastStrip past={past} x={56} y={g.slotY - Math.round(92 * f)} w={width - 112} f={f * 0.85} color={ink} />
      <div data-layer="Match details" style={{ position: 'absolute', left: 56, right: 56, top: g.slotY - Math.round(48 * f), fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 2, textAlign: 'center', opacity: 0.85 }}>
        {upper(joinDot(r.grade || r.comp, r.round, r.date, r.potm && (r.potm.first || r.potm.last) ? `POTM ${[r.potm.first, r.potm.last].filter(Boolean).join(' ')}` : ''))}
      </div>
      <Credit g={g} ink={ink} />
    </Root>
  )
}
SplitFinal.displayName = 'SplitFinal'

// ── DL20 Numbered List ───────────────────────────────────────────────────────
export function NumberedList({ width = 1080, height = 1080, team = {}, opponent = {}, match = {}, players = [], palette = {}, featuredId, heroImage, parts, past }) {
  const g = geo(width, height)
  const { f } = g
  const ground = pc(parts, 'dl20Ground', palette.primary || '#0b1530')
  const accent = pc(parts, 'dl20Accent', readable(palette.accent || '#ffc233', ground, '#ffffff'))
  const ink = '#ffffff'
  const resolve = resolver(palette)
  const hero = featuredOf(players, featuredId)
  const photo = heroImage || heroSrcOf(hero)
  const top = g.top + Math.round(150 * f)
  const pastH = hasPast(past) ? Math.round(50 * f) : 0
  const listH = g.slotY - 20 - top - pastH
  const n = Math.max(1, players.length)
  const rowH = Math.min(Math.round(76 * f), Math.floor(listH / n))
  return (
    <Root width={width} height={height} bg={ground} ink={ink}>
      <Halftone w={width} h={height} color={ink} size={Math.round(16 * f)} opacity={0.05} />
      <Picture src={photo} x={width * 0.42} y={g.top} w={width * 0.6} h={g.slotY - g.top} resolve={resolve} team={team} ink={ink}
        fx={{ tone: 'duotone', duoDark: '#050608', duoLight: accent, contrast: 14 }} style={{ opacity: 0.9 }} />
      <div data-layer="Title" style={{ position: 'absolute', left: 48, top: g.top, width: width * 0.6 }}>
        <div style={{ fontSize: Math.round(84 * f), lineHeight: 0.95 }}>{upper(pt(parts, 'dl20Title', 'THE TEAM'))}</div>
        <div style={{ fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 2, color: accent, marginTop: 6 }}>{upper(`V ${opponent.name || 'OPPONENT'} · ${joinDot(match.date, match.time)}`)}</div>
      </div>
      <div data-layer="Team list" style={{ position: 'absolute', left: 48, top, width: width * 0.62 }}>
        {players.map((p, i) => (
          <div key={p._id || i} style={{ height: rowH, display: 'flex', alignItems: 'center', gap: Math.round(16 * f) }}>
            <span style={{ width: Math.round(rowH * 1.1), fontSize: Math.round(rowH * 0.95), lineHeight: 1, color: 'transparent', WebkitTextStroke: `${Math.max(1.5, Math.round(2 * f))}px ${accent}`, textAlign: 'right' }}>{String(i + 1).padStart(2, '0')}</span>
            <span style={{ fontSize: Math.round(rowH * 0.58), lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {upper(p.first)} <span style={{ color: accent }}>{upper(p.last)}</span>{p.captain ? ' (C)' : ''}{p.keeper ? ' (WK)' : ''}
            </span>
          </div>
        ))}
        {!players.length && <div style={{ fontFamily: MONO, fontSize: 22, letterSpacing: 2, opacity: 0.8 }}>PICK THE TEAM IN PLAYERS</div>}
      </div>
      <div data-layer="Club logo" style={{ position: 'absolute', right: 40, top: g.top }}><ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(80 * f)} shape="shield" /></div>
      <PastStrip past={past} x={48} y={g.slotY - pastH} w={Math.round(width * 0.62)} f={f * 0.85} color={ink} align="left" />
      <Credit g={g} ink={ink} />
    </Root>
  )
}
NumberedList.displayName = 'NumberedList'

registerParts({
  DL10: [textPart('dl10Word', 'Stamp word (blank uses the announcement kind)', 'Stamp', () => ''), colorPart('dl10Stamp', 'Stamp colour', 'Stamp', (p) => p.accent || '#e1251b'), colorPart('dl10Tone', 'Photo tone', 'Photo', (p) => p.primary || '#0b1530')],
  DL11: [colorPart('dl11Ground', 'Background', 'Background', (p) => p.primary || '#0b1530'), colorPart('dl11Mark', 'Quote marks and rule', 'Quote', (p) => p.accent || '#ffc233')],
  DL12: [textPart('dl12Greet', 'Greeting', 'Words', () => 'Happy birthday'), colorPart('dl12Ground', 'Background', 'Background', (p) => p.primary || '#0b1530')],
  DL13: [textPart('dl13Head', 'Header', 'Words', () => 'SQUAD UPDATE'), colorPart('dl13Pill', 'Status pill', 'Status', () => '#d97706'), colorPart('dl13Ground', 'Background', 'Background', () => '#1b1d22')],
  DL14: [colorPart('dl14Number', 'The number', 'Number', (p) => p.accent || '#ffc233'), colorPart('dl14Ground', 'Background', 'Background', (p) => p.primary || '#0b1530')],
  DL15: [textPart('dlChip', 'Tag', 'Name', () => 'PLAYER OF THE MATCH'), textPart('dl15Empty', 'Big word before any figures', 'Figure', () => 'POTM'), colorPart('dl15Figure', 'Big figure', 'Figure', (p) => p.accent || '#ffc233'), colorPart('dl15Ground', 'Background', 'Background', (p) => p.primary || '#0b1530')],
  DL16: [textPart('dl16Title', 'Title', 'Words', () => 'THE TOSS'), colorPart('dl16Us', 'Our half', 'Halves', (p) => p.primary || '#0b1530'), colorPart('dl16Them', 'Their half', 'Halves', () => '#2a2d33'), colorPart('dl16Coin', 'Coin', 'Coin', () => '#e8c15a')],
  DL17: [colorPart('dl17Number', 'The number', 'Number', (p) => p.accent || '#ffc233'), colorPart('dl17Ground', 'Background', 'Background', (p) => p.primary || '#0b1530')],
  DL18: [textPart('dl18Title', 'Title', 'Words', () => 'TEAM OF THE WEEK'), colorPart('dl18Grass', 'Field', 'Ground', () => '#1f6b3a'), colorPart('dl18Ground', 'Background', 'Ground', (p) => p.primary || '#0b1530')],
  DL19: [textPart('dl19Word', 'Ribbon word', 'Ribbon', () => 'FULL TIME'), colorPart('dl19Ribbon', 'Ribbon', 'Ribbon', (p) => p.accent || '#ffc233'), colorPart('dl19Us', 'Our half', 'Halves', (p) => p.primary || '#0b1530'), colorPart('dl19Them', 'Their half', 'Halves', () => '#2a2d33')],
  DL20: [textPart('dl20Title', 'Title', 'Words', () => 'THE TEAM'), colorPart('dl20Accent', 'Numbers and surnames', 'Colours', (p) => p.accent || '#ffc233'), colorPart('dl20Ground', 'Background', 'Colours', (p) => p.primary || '#0b1530')],
})

// The Content panel each layout shares with its type's built-in one.
export const DESIGN_PANEL_ALIAS_2 = { DL10: 'C1', DL11: 'C1', DL12: 'C1', DL13: 'C1', DL14: 'C1', DL15: 'C3', DL16: 'C2' }
export const SPONSOR_SLOTS = Object.fromEntries(['DL10', 'DL11', 'DL12', 'DL13', 'DL14', 'DL15', 'DL16', 'DL17', 'DL18', 'DL19', 'DL20'].map((id) => [id, slotOf]))
