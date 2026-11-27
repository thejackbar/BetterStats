// ─────────────────────────────────────────────────────────────────────────────
// DESIGN LAYOUTS: the poster styles from the design effects (v9.154.0) made
// into real layouts, each on its own post type and fed by that type's data.
//
//   DL1 Match Day V      Lineup        pale striped poster, our player and their crest in V panels
//   DL2 Gameday Echo     Lineup        stacked outlined GAMEDAY, player in black and white, kit colour kept
//   DL8 Game Day Card    Lineup        duotone photo, bordered card, GAME DAY with the player breaking out
//   DL9 Squad Collage    Lineup        one to seven players stacked on a torn poster, reorderable
//   DL3 Final Score V    Final Score   both crests in V frames, scores, winner lit, POTM
//   DL4 Fixtures Echo    Fixtures      echo heading, one torn-paper strip per fixture
//   DL5 Results Echo     Results       echo heading, one torn-paper strip per result
//   DL6 Colour Pop       Player of the Match   faded face behind, brush strokes, kit colour kept
//   DL7 Colour Pop       Announcement  the same look on the announcement fields
//
// DL1, DL2, DL8, DL9 and DL6 follow five reference posters the club supplied,
// as closely as the club's own data and colours allow.
//
// The frames, looks and textures are the same code the blocks use
// (designFx.js, FramedImage.jsx), so the PNG export paints them the same way.
// Every root child carries `data-layer` so the Layers panel can name it, and
// each layout keeps its sponsor slot clear by calling the function it exports
// in SPONSOR_SLOTS.
// ─────────────────────────────────────────────────────────────────────────────
import { AutoFitText, ClubLogo, CreditMark, heroSrcOf, featuredOf } from './cricket-templates'
import { aspectOf, pick } from './postAspect'
import { LayerRoot } from './postLayers'
import { niceName } from './card-kit'
import { pc, pt, inkOn, registerParts, colorPart, textPart } from './layoutParts'
import { usePostLook } from './postLook'
import FramedImage from './FramedImage'
import { PastStrip, hasPast, RowForm } from './pastMeetings'
import { FRAMES, framePoints, frameClip, burstPaths, speedPaths, brushPaths, tornPaperPaths, grungePaths, splatterPaths } from './designFx'

export const FONT = "var(--social-display-font, 'Anton', 'Hanken Grotesk', sans-serif)"
export const WEIGHT = 'var(--social-display-font-weight, 700)'
export const MONO = "'JetBrains Mono', monospace"
const VBASE = framePoints(FRAMES.find((f) => f.key === 'vbottom'))

// Shared geometry: the safe top and bottom (a story's ends sit under the app's
// own bars), a size factor, and the sponsor strip along the bottom.
export function geo(width, height) {
  const A = aspectOf(width, height)
  const f = pick(A, { square: 1, portrait: 1.06, story: 1.12 })
  const top = pick(A, { square: 40, portrait: 56, story: 210 })
  const bottom = pick(A, { square: 26, portrait: 40, story: 240 })
  const slotH = Math.round(84 * f)
  const slotY = height - bottom - slotH
  return { A, f, top, bottom, slotH, slotY }
}
export const slotOf = (width, height) => {
  const g = geo(width, height)
  const w = Math.min(width - 220, 640)
  return { x: Math.round((width - w) / 2), y: g.slotY, w, h: g.slotH, pad: 6, gap: 22, panel: 'light' }
}

export const hasText = (v) => v && v !== 'COMPETITION'

// A colour that reads on `ground`: `want` when the two differ enough in
// lightness, else `fallback` (a navy kit colour on a black poster is invisible).
const lum = (hex) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ''))
  if (!m) return 0.5
  const n = parseInt(m[1], 16)
  const ch = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }
  return 0.2126 * ch((n >> 16) & 255) + 0.7152 * ch((n >> 8) & 255) + 0.0722 * ch(n & 255)
}
const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) }
export const readable = (want, ground, fallback) => (contrast(want, ground) >= 2.2 ? want : fallback)
export const joinDot = (...xs) => xs.filter(hasText).join(' · ')
export const upper = (v) => String(v || '').toUpperCase()

export function Paths({ layer, paths, color, width, height, left = 0, top = 0, opacity = 1, rotate = 0 }) {
  return (
    <svg data-layer={layer} width={width} height={height} viewBox={`0 0 ${width} ${height}`}
      style={{ position: 'absolute', left, top, opacity, overflow: 'visible', transform: rotate ? `rotate(${rotate}deg)` : undefined, pointerEvents: 'none' }}>
      {paths.map((p, i) => <path key={i} d={p.d} fill={color} fillOpacity={p.opacity} />)}
    </svg>
  )
}

// A crest drawn inside a V-base frame, on the frame's fill.
export function CrestFrame({ layer, x, y, w, h, fill, logo, mono, ink, children }) {
  const clip = frameClip(VBASE, h, 0)
  const size = Math.round(Math.min(w * 0.62, h * 0.42))
  return (
    <div data-layer={layer} style={{ position: 'absolute', left: x, top: y, width: w, height: h }}>
      <div style={{ position: 'absolute', inset: 0, background: fill, clipPath: clip, WebkitClipPath: clip }} />
      <div style={{ position: 'absolute', left: 0, right: 0, top: Math.round(h * 0.1), display: 'flex', justifyContent: 'center' }}>
        <ClubLogo src={logo} monogram={mono || ''} color={ink} size={size} shape="shield" />
      </div>
      {children}
    </div>
  )
}

export const resolver = (palette) => (c) => ({
  primary: palette.primary, secondary: palette.secondary, accent: palette.accent, ink: palette.ink,
  white: '#ffffff', black: '#0a0a0a',
}[c] || c)

// Small line icons for the details rows (drawn here; the app kit has none that
// survive the PNG export at poster scale).
export function CalendarIcon({ size, color }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.2" strokeLinejoin="round">
      <rect x="3" y="5" width="18" height="16" rx="1" /><path d="M3 10h18M8 3v4M16 3v4" />
      <rect x="7" y="13" width="3" height="3" fill={color} stroke="none" /><rect x="14" y="13" width="3" height="3" fill={color} stroke="none" />
    </svg>
  )
}
export function PinIcon({ size, color }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.2">
      <path d="M12 22s7-7.4 7-12.5A7 7 0 0 0 5 9.5C5 14.6 12 22 12 22Z" /><circle cx="12" cy="9.5" r="2.6" fill={color} stroke="none" />
    </svg>
  )
}

// A cut-out in black and white with the kit colour kept: the look all the
// photo-led layouts here share. `edge` adds a thin outline round it.
export const keptLook = (keep, { edge = 0, glow = null, contrast = 18 } = {}) => ({
  tone: 'mono', splash: [{ color: keep, range: 34, soft: 34 }], splashStrength: 100, contrast,
  ...(edge ? { outline: { width: edge, color: 'white' } } : null),
  ...(glow ? { glow } : null),
})

// ── DL1 Match Day V ──────────────────────────────────────────────────────────
// After the Nations League "MATCH DAY" poster: pale striped paper, the title in
// dark type, our player in a V-based panel in the club colour with their head
// out of the top, the opposition crest in the other, the club crest where the
// panels meet, the date and the ground along the bottom.
export function MatchDayV({ width = 1080, height = 1080, team = {}, opponent = {}, match = {}, players = [], palette = {}, featuredId, heroImage, parts, past }) {
  const g = geo(width, height)
  const { f, A } = g
  const paper = pc(parts, 'dl1Paper', '#ebe8e1')
  const ink = pc(parts, 'dl1Ink', '#16181d')
  const usFill = pc(parts, 'dl1UsFill', palette.primary || '#0b1530')
  const themFill = pc(parts, 'dl1ThemFill', '#1f3f8f')
  const hero = featuredOf(players, featuredId)
  const photo = heroImage || heroSrcOf(hero)
  const keep = pc(parts, 'dlKeepColor', palette.primary || '#0b1530')
  const resolve = resolver(palette)
  const kickH = Math.round(20 * f)
  const titleTop = g.top + kickH + 10
  const titleH = Math.round(pick(A, { square: 104, portrait: 118, story: 132 }) * f)
  const subY = titleTop + titleH + Math.round(26 * f)
  const panelTop = subY + Math.round(pick(A, { square: 96, portrait: 150, story: 190 }) * f)
  const footH = Math.round(118 * f)
  const footY = g.slotY - footH - 8
  const names = players.map((p) => upper(p.last || p.first) + (p.captain ? ' (C)' : '') + (p.keeper ? ' (WK)' : ''))
  const namesH = names.length ? Math.round(68 * f) : 0
  const pastH = hasPast(past) ? Math.round(46 * f) : 0
  const panelH = Math.max(260, footY - namesH - 18 - pastH - panelTop)
  const gap = Math.round(width * 0.025)
  const pw = Math.round((width - 140 - gap) / 2)
  const usName = upper(team.name || team.short)
  const themName = upper(opponent.name || opponent.short || 'OPPONENT')
  const clip = frameClip(VBASE, panelH, 0)
  const crest = Math.round(Math.min(140 * f, gap * 4.2 + 50))
  // The names sit clear of the crest, which stands where the V points meet.
  const nameBox = (fill, side) => ({ position: 'absolute', left: side === 'us' ? 18 : Math.round(crest * 0.2), right: side === 'us' ? Math.round(crest * 0.2) : 18, top: Math.round(panelH * 0.5), color: inkOn(fill), textAlign: 'center' })
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: paper, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      <div data-layer="Paper stripes" style={{ position: 'absolute', inset: 0, background: `repeating-linear-gradient(90deg, ${ink}00 0, ${ink}00 ${Math.round(width / 9)}px, ${ink}0a ${Math.round(width / 9)}px, ${ink}0a ${Math.round(width / 9) * 2}px)`, pointerEvents: 'none' }} />
      <div data-layer="Competition" style={{ position: 'absolute', left: 48, right: 48, top: g.top, textAlign: 'center', fontFamily: MONO, fontSize: kickH * 0.8, letterSpacing: 3, color: `${ink}b3` }}>
        {upper(joinDot(match.season, match.competition)) || upper(team.name)}
      </div>
      <div data-layer="Title" style={{ position: 'absolute', left: 60, right: 60, top: titleTop, height: titleH }}>
        <AutoFitText text={pt(parts, 'dl1Title', 'MATCH DAY')} max={titleH} min={48} lines={1} measureDeps={[width, height]}
          style={{ textAlign: 'center', lineHeight: 1, color: pc(parts, 'dl1TitleColor', ink) }} />
      </div>
      <div data-layer="Rule" style={{ position: 'absolute', left: width / 2 - 170, width: 340, top: subY - Math.round(12 * f), height: 2, background: `${ink}40` }}>
        <div style={{ position: 'absolute', left: 164, top: -5, width: 12, height: 12, background: ink, transform: 'rotate(45deg)' }} />
      </div>
      <div data-layer="Versus line" style={{ position: 'absolute', left: 48, right: 48, top: subY, textAlign: 'center', fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 4, color: `${ink}99` }}>
        {upper(`${hero ? (hero.last || hero.first) : team.name} v ${opponent.name || 'OPPONENT'}`)}
      </div>

      <div data-layer="Our panel" style={{ position: 'absolute', left: 70, top: panelTop, width: pw, height: panelH }}>
        {photo ? (
          <FramedImage item={{ w: pw, h: panelH, mask: 'vbottom', frameFill: usFill, popOut: pick(A, { square: 0.2, portrait: 0.26, story: 0.3 }), fit: 'contain', objPos: 'center top', fx: keptLook(keep) }} src={photo} resolve={resolve} />
        ) : (
          <CrestFrame layer="Our crest" x={0} y={0} w={pw} h={panelH} fill={usFill} logo={team.logo} mono={team.monogram} ink={inkOn(usFill)} />
        )}
        <div style={nameBox(usFill, 'us')}>
          <AutoFitText text={usName} max={Math.round(66 * f)} min={22} lines={1} measureDeps={[usName, width, height]} style={{ textAlign: 'center', lineHeight: 1 }} />
          <div style={{ width: Math.round(pw * 0.2), height: 4, background: inkOn(usFill), margin: `${Math.round(12 * f)}px auto 0`, opacity: 0.8 }} />
        </div>
      </div>
      <div data-layer="Opposition panel" style={{ position: 'absolute', left: 70 + pw + gap, top: panelTop, width: pw, height: panelH }}>
        <div style={{ position: 'absolute', inset: 0, background: themFill, clipPath: clip, WebkitClipPath: clip }} />
        <div style={{ position: 'absolute', left: 0, right: 0, top: Math.round(panelH * 0.1), display: 'flex', justifyContent: 'center' }}>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram || ''} color={inkOn(themFill)} size={Math.round(Math.min(pw * 0.6, panelH * 0.42))} shape="shield" />
        </div>
        <div style={nameBox(themFill, 'them')}>
          <AutoFitText text={themName} max={Math.round(66 * f)} min={22} lines={1} measureDeps={[themName, width, height]} style={{ textAlign: 'center', lineHeight: 1 }} />
          <div style={{ width: Math.round(pw * 0.2), height: 4, background: inkOn(themFill), margin: `${Math.round(12 * f)}px auto 0`, opacity: 0.8 }} />
        </div>
      </div>
      <div data-layer="Club crest" style={{ position: 'absolute', left: width / 2 - crest / 2, top: panelTop + panelH - crest * 0.95, width: crest, height: crest, display: 'grid', placeItems: 'center', background: paper, borderRadius: '50%', boxShadow: `0 0 0 6px ${paper}` }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(crest * 0.78)} shape="shield" />
      </div>

      <PastStrip past={past} x={60} y={panelTop + panelH + Math.round(16 * f)} w={width - 120} f={f * 0.9} color={ink} />
      {names.length > 0 && (
        <div data-layer="Team list" style={{ position: 'absolute', left: 70, right: 70, top: footY - namesH - 6, height: namesH, textAlign: 'center', fontSize: Math.round(23 * f), lineHeight: 1.35, color: ink, overflow: 'hidden' }}>
          {names.join('  ·  ')}
        </div>
      )}
      <div data-layer="Match details" style={{ position: 'absolute', left: 60, right: 60, top: footY, height: footH, display: 'grid', gridTemplateColumns: '1fr 1.3fr 1fr', alignItems: 'center', borderTop: `2px solid ${ink}26`, paddingTop: Math.round(14 * f) }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <CalendarIcon size={Math.round(40 * f)} color={ink} />
          <div style={{ fontFamily: MONO, fontSize: Math.round(17 * f), letterSpacing: 1.5, lineHeight: 1.35 }}>{upper(match.date)}<br />{upper(match.time)}</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: Math.round(26 * f), lineHeight: 1.1 }}>{upper(`${team.name || ''} V ${opponent.name || 'OPPONENT'}`)}</div>
          <div style={{ fontFamily: MONO, fontSize: Math.round(14 * f), letterSpacing: 3, color: `${ink}99`, marginTop: 4 }}>{upper(joinDot(match.round, match.competition))}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'flex-end' }}>
          <div style={{ fontFamily: MONO, fontSize: Math.round(17 * f), letterSpacing: 1.5, lineHeight: 1.35, textAlign: 'right' }}>{upper(match.venue)}</div>
          <PinIcon size={Math.round(40 * f)} color={ink} />
        </div>
      </div>
      <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink={ink} h={Math.round(30 * f)} /></div>
    </LayerRoot>
  )
}
MatchDayV.displayName = 'MatchDayV'

// ── DL2 Gameday Echo ─────────────────────────────────────────────────────────
// After the "GAMEDAY" stack poster: near-black ground, the word stacked down the
// post in outline with one copy filled, the player in black and white with the
// kit colour kept, a tagline and the date in the top corners, the two crests
// with VS at the foot and the player's name beside them.
export function GamedayEcho({ width = 1080, height = 1080, team = {}, opponent = {}, match = {}, players = [], palette = {}, featuredId, heroImage, parts, past }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f, A } = g
  const ground = pc(parts, 'dl2Ground', '#0e0e10')
  const ink = '#ffffff'
  const red = pc(parts, 'dl2EchoColor', palette.accent || '#e1251b')
  const keep = pc(parts, 'dlKeepColor', palette.primary || '#0b1530')
  const hero = featuredOf(players, featuredId)
  const photo = heroImage || heroSrcOf(hero)
  const word = upper(pt(parts, 'dl2Word', 'GAMEDAY'))
  const fs = Math.round(Math.min(210 * f, (width * 0.9) / Math.max(4, word.length) * 1.85))
  const step = Math.round(fs * 0.8)
  const echoTop = g.top + Math.round(pick(A, { square: 120, portrait: 160, story: 200 }) * f)
  const footH = Math.round((hasPast(past) ? 186 : 150) * f)
  const footY = g.slotY - footH
  const echoN = Math.max(4, Math.min(9, Math.floor((footY - echoTop) / step)))
  const filled = Math.min(echoN - 1, Math.max(1, Math.round(echoN * 0.6)))
  const resolve = resolver(palette)
  const heroTop = g.top + Math.round(30 * f)
  const heroH = footY + Math.round(40 * f) - heroTop
  const heroW = Math.round(width * 0.74)
  const crest = Math.round(96 * f)
  const name = hero ? upper([hero.first, hero.last].filter(Boolean).join(' ')) : ''
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: ground, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      {texture && <Paths layer="Paint streaks" paths={brushPaths(width * 1.2, Math.round(height * 0.5), 41)} color={red} width={Math.round(width * 1.2)} height={Math.round(height * 0.5)} left={-width * 0.1} top={height * 0.18} opacity={0.12} rotate={-24} />}
      {texture && <Paths layer="Grunge" paths={grungePaths(width, height, 12)} color={ink} width={width} height={height} opacity={0.14} />}
      <div data-layer="Echo word" style={{ position: 'absolute', left: 0, right: 0, top: echoTop, textAlign: 'center' }}>
        {Array.from({ length: echoN }, (_, i) => i).sort((a, b) => (a === filled) - (b === filled)).map((i) => (
          <div key={i} style={{
            position: i === 0 ? 'relative' : 'absolute', left: 0, right: 0, top: i === 0 ? 0 : i * step, fontSize: fs, lineHeight: 1, whiteSpace: 'nowrap', letterSpacing: -2,
            color: i === filled ? red : 'transparent', WebkitTextStroke: i === filled ? undefined : `${Math.max(2, Math.round(fs * 0.018))}px ${red}`,
          }}>{word}</div>
        ))}
      </div>
      {photo ? (
        <div data-layer="Player" style={{ position: 'absolute', left: Math.round((width - heroW) / 2), top: heroTop, width: heroW, height: heroH }}>
          <FramedImage item={{ w: heroW, h: heroH, fit: 'contain', objPos: 'center bottom', fx: keptLook(keep, { contrast: 24 }) }} src={photo} resolve={resolve} />
        </div>
      ) : (
        <div data-layer="Club mark" style={{ position: 'absolute', left: width / 2 - 180, top: heroTop + heroH / 2 - 200, opacity: 0.95 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={360} shape="shield" />
        </div>
      )}
      <div data-layer="Tagline" style={{ position: 'absolute', left: 44, top: g.top, fontFamily: "'Permanent Marker', cursive", fontWeight: 400, fontSize: Math.round(34 * f), color: ink, transform: 'rotate(-4deg)', transformOrigin: 'left' }}>
        {pt(parts, 'dl2Tag', team.name ? `${String(team.name).split(' ')[0]} together` : 'Together')}
      </div>
      <div data-layer="Date" style={{ position: 'absolute', right: 44, top: g.top, textAlign: 'right', color: red, transform: 'rotate(-4deg)', transformOrigin: 'right' }}>
        <div style={{ fontFamily: "'Permanent Marker', cursive", fontWeight: 400, fontSize: Math.round(36 * f), lineHeight: 1.05 }}>{match.date || ''}</div>
        <div style={{ fontFamily: "'Permanent Marker', cursive", fontWeight: 400, fontSize: Math.round(26 * f), lineHeight: 1.2, borderTop: `3px solid ${red}`, paddingTop: 4, marginTop: 4 }}>{[match.time, match.venue].filter(hasText).join(' · ')}</div>
      </div>
      <div data-layer="Crests" style={{ position: 'absolute', left: 0, right: 0, top: footY + Math.round(30 * f), display: 'flex', alignItems: 'center', justifyContent: 'center', gap: Math.round(26 * f) }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={crest} shape="circle" />
        <span style={{ fontSize: Math.round(46 * f), color: ink, letterSpacing: 2 }}>VS</span>
        <ClubLogo src={opponent.logo} monogram={opponent.monogram || ''} color={ink} size={crest} shape="circle" />
      </div>
      <PastStrip past={past} x={48} y={footY + Math.round(30 * f) + crest + Math.round(12 * f)} w={width - 96} f={f * 0.85} color={ink} />
      {name && (
        <div data-layer="Player name" style={{ position: 'absolute', right: 48, top: footY - Math.round(10 * f), textAlign: 'right', fontSize: Math.round(40 * f), lineHeight: 0.95, color: ink, maxWidth: width * 0.34 }}>{name.split(' ').map((w, i) => <div key={i}>{w}</div>)}</div>
      )}
      <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink={ink} h={Math.round(30 * f)} /></div>
    </LayerRoot>
  )
}
GamedayEcho.displayName = 'GamedayEcho'

// ── DL8 Game Day Card ────────────────────────────────────────────────────────
// After the teal "GAME DAY" flyer: the player photo blurred and duotoned across
// the whole post, a bordered card on top, GAME DAY in giant type with the
// player cut out over it and breaking out of the card, a live badge, the date
// in a box, a tagline, and the ground and opposition along the foot.
export function GameDayCard({ width = 1080, height = 1080, team = {}, opponent = {}, match = {}, players = [], palette = {}, featuredId, heroImage, parts, past }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f, A } = g
  const tone = pc(parts, 'dl8Tone', palette.primary || '#0b6e66')
  const accent = pc(parts, 'dl8Accent', palette.accent || '#2ee6c8')
  const ink = '#ffffff'
  const hero = featuredOf(players, featuredId)
  const photo = heroImage || heroSrcOf(hero)
  const resolve = resolver(palette)
  const inset = Math.round(pick(A, { square: 90, portrait: 80, story: 70 }) * f)
  const cardTop = g.top + Math.round(30 * f)
  const cardBottom = g.slotY - 18
  const cardH = cardBottom - cardTop
  const cardW = width - inset * 2
  const wordFs = Math.round(Math.min(cardW * 0.52, cardH * 0.3))
  const wordTop = cardTop + Math.round(cardH * 0.26)
  const parsed = String(match.date || '').match(/(\d{1,2})\s+([A-Za-z]+)/)
  const dayNum = parsed ? parsed[1] : ''
  const month = parsed ? upper(parsed[2]) : upper(match.date)
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: tone, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      {photo && (
        <div data-layer="Photo backdrop" style={{ position: 'absolute', inset: -40, filter: 'blur(18px)', opacity: 0.85 }}>
          <FramedImage item={{ w: width + 80, h: height + 80, fit: 'cover', fx: { tone: 'duotone', duoDark: '#020707', duoLight: tone, contrast: 10 } }} src={photo} resolve={resolve} />
        </div>
      )}
      <div data-layer="Shade" style={{ position: 'absolute', inset: 0, background: `radial-gradient(ellipse at 50% 40%, ${tone}33 0%, #000000b3 100%)` }} />
      {texture && <Paths layer="Speed lines" paths={speedPaths(width, Math.round(height * 0.4), 3)} color={accent} width={width} height={Math.round(height * 0.4)} top={height * 0.05} opacity={0.12} rotate={-8} />}
      <div data-layer="Card" style={{ position: 'absolute', left: inset, top: cardTop, width: cardW, height: cardH, border: `4px solid ${ink}`, background: `linear-gradient(180deg, ${tone}cc 0%, #031615ee 100%)`, boxSizing: 'border-box' }} />
      <div data-layer="Live badge" style={{ position: 'absolute', left: inset + 26, top: cardTop + 26, border: `2px solid ${ink}`, padding: `${Math.round(6 * f)}px ${Math.round(10 * f)}px`, textAlign: 'center', lineHeight: 1 }}>
        <div style={{ fontFamily: MONO, fontSize: Math.round(13 * f), letterSpacing: 2 }}>{upper(pt(parts, 'dl8BadgeTop', 'WATCH US'))}</div>
        <div style={{ background: accent, color: inkOn(accent), fontSize: Math.round(28 * f), padding: '2px 8px', marginTop: 4 }}>{upper(pt(parts, 'dl8Badge', 'LIVE'))}</div>
      </div>
      <div data-layer="Presents" style={{ position: 'absolute', left: inset + 160, right: inset + 160, top: cardTop + 36, textAlign: 'center', fontFamily: MONO, fontSize: Math.round(17 * f), letterSpacing: 4, color: accent }}>
        {upper(`${team.name || ''} presents`)}
      </div>
      <div data-layer="Date box" style={{ position: 'absolute', right: inset + 26, top: cardTop + 26, width: Math.round(104 * f), border: `2px solid ${ink}`, textAlign: 'center', padding: `${Math.round(8 * f)}px 0`, lineHeight: 1 }}>
        {dayNum && <div style={{ fontSize: Math.round(56 * f) }}>{dayNum}</div>}
        <div style={{ fontFamily: MONO, fontSize: Math.round(dayNum ? 16 : 14) * f, letterSpacing: 2, marginTop: 4, padding: '0 6px' }}>{month}</div>
      </div>
      <div data-layer="Tagline" style={{ position: 'absolute', left: inset + 40, top: wordTop - Math.round(46 * f), fontSize: Math.round(26 * f), letterSpacing: 2 }}>
        {upper(pt(parts, 'dl8Tag', `V ${opponent.name || 'OPPONENT'}`))}
      </div>
      <div data-layer="Game day word" style={{ position: 'absolute', left: inset + 30, top: wordTop, fontSize: wordFs, lineHeight: 0.86, letterSpacing: -2, color: ink }}>
        <div>{upper(pt(parts, 'dl8Word1', 'GAME'))}</div>
        <div style={{ color: 'transparent', WebkitTextStroke: `${Math.max(3, Math.round(wordFs * 0.018))}px ${ink}` }}>{upper(pt(parts, 'dl8Word2', 'DAY'))}</div>
      </div>
      {photo && (
        <div data-layer="Player" style={{ position: 'absolute', left: Math.round(width * 0.36), top: cardTop - Math.round(40 * f), width: Math.round(width * 0.66), height: cardH + Math.round(20 * f) }}>
          <FramedImage item={{ w: Math.round(width * 0.66), h: cardH + Math.round(20 * f), fit: 'contain', objPos: 'center bottom', fx: { contrast: 8, shadow: { x: 0, y: 24, blur: 40, opacity: 60 } } }} src={photo} resolve={resolve} />
        </div>
      )}
      <PastStrip past={past} x={inset + 34} y={cardBottom - Math.round(140 * f)} w={Math.round(width * 0.52)} f={f * 0.85} color={ink} align="left" />
      <div data-layer="Ground and time" style={{ position: 'absolute', left: inset + 34, bottom: height - cardBottom + Math.round(30 * f), fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 2, lineHeight: 1.6 }}>
        <div>{upper(`GROUND : ${match.venue || ''}`)}</div>
        <div style={{ color: accent }}>{upper(joinDot(match.time, match.round, match.competition))}</div>
      </div>
      <div data-layer="Club logo" style={{ position: 'absolute', right: inset + 30, bottom: height - cardBottom + Math.round(26 * f) }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(78 * f)} shape="shield" />
      </div>
      <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink={ink} h={Math.round(30 * f)} /></div>
    </LayerRoot>
  )
}
GameDayCard.displayName = 'GameDayCard'

// ── DL9 Squad Collage ────────────────────────────────────────────────────────
// After the torn-poster collage: several players cut out, black and white with
// the kit colour kept, stacked in rows that rearrange for one to seven of them,
// on a torn paper poster pasted over a worn wall, a brush stroke and the club
// crest behind them, a tagline in a colour block and the match in the corner.
//
// Rows, back to front, for each count; the first player in the order takes
// the most prominent place (the middle of the back row), the rest follow.
export const COLLAGE_MAX = 7
const COLLAGE_ROWS = { 1: [1], 2: [2], 3: [1, 2], 4: [2, 2], 5: [3, 2], 6: [3, 3], 7: [3, 2, 2] }
export function collageSlots(n, w, h) {
  const rows = COLLAGE_ROWS[Math.max(1, Math.min(COLLAGE_MAX, n))]
  const R = rows.length
  const heights = R === 1 ? [0.96] : R === 2 ? [0.7, 0.56] : [0.58, 0.46, 0.4]
  const slots = []
  rows.forEach((k, r) => {
    const sh = h * heights[r]
    const bottom = R === 1 ? h : h * (0.6 + (0.4 * r) / (R - 1))
    const spread = Math.min(0.34, 0.86 / Math.max(k, 1.6))
    const order = k === 3 ? [1, 0, 2] : k === 2 ? [0, 1] : [0]
    order.forEach((j, rank) => {
      const cx = w * (0.5 + (j - (k - 1) / 2) * spread)
      // A middle player in a row of three stands a little taller.
      const lift = k === 3 && j === 1 ? 1.08 : 1
      slots.push({ row: r, rank, cx, bottom, h: sh * lift, w: sh * lift * 0.72 })
    })
  })
  return slots
}

export function SquadCollage({ width = 1080, height = 1080, team = {}, opponent = {}, match = {}, heroes = [], palette = {}, parts, past }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f, A } = g
  const wall = '#2a2b2e'
  const paper = pc(parts, 'dl9Paper', '#ece9e3')
  const keep = pc(parts, 'dlKeepColor', palette.primary || '#c8102e')
  const brushC = pc(parts, 'dl9Brush', keep)
  const resolve = resolver(palette)
  const px = Math.round(width * 0.06)
  const py = g.top
  const pw = width - px * 2
  const ph = g.slotY - 14 - py
  const stageTop = Math.round(ph * pick(A, { square: 0.17, portrait: 0.16, story: 0.16 }))
  const stageH = Math.round(ph * 0.8) - stageTop
  const list = heroes.filter((p) => heroSrcOf(p)).slice(0, COLLAGE_MAX)
  const slots = collageSlots(list.length || 1, pw, stageH)
  const byRank = [...slots].sort((a, b) => a.row - b.row || a.rank - b.rank)
  const placed = list.map((p, i) => ({ p, s: byRank[i] }))
  const draw = [...placed].sort((a, b) => a.s.row - b.s.row || b.s.rank - a.s.rank)
  const tag = pt(parts, 'dl9Tag', team.name ? `Proud to be ${String(team.name).split(' ')[0]}` : 'One club')
  const crest = Math.round(64 * f)
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: wall, color: '#111', fontFamily: FONT, fontWeight: WEIGHT }}>
      {texture && [0, 1, 2, 3].map((i) => (
        <Paths key={i} layer={`Old poster ${i + 1}`} paths={tornPaperPaths(width * 0.7, height * 0.4, 50 + i)} color={['#3a3b3f', '#46474b', '#313236', '#505155'][i]}
          width={Math.round(width * 0.7)} height={Math.round(height * 0.4)} left={[-80, width * 0.45, -60, width * 0.4][i]} top={[-60, -40, height * 0.62, height * 0.7][i]} rotate={[8, -6, -4, 7][i]} />
      ))}
      {texture && <Paths layer="Wall grunge" paths={grungePaths(width, height, 21)} color="#000000" width={width} height={height} opacity={0.4} />}
      <div data-layer="Poster" style={{ position: 'absolute', left: px, top: py, width: pw, height: ph, transform: 'rotate(-1.2deg)' }}>
        <svg width={pw} height={ph} viewBox={`0 0 ${pw} ${ph}`} style={{ position: 'absolute', inset: 0 }}>
          {tornPaperPaths(pw, ph, 61).map((p, i) => <path key={i} d={p.d} fill={paper} />)}
        </svg>
        {texture && <Paths layer="Poster grain" paths={grungePaths(pw, ph, 33)} color="#000000" width={pw} height={ph} opacity={0.16} />}
        <Paths layer="Brush stroke" paths={brushPaths(pw * 0.9, stageH * 0.42, 77)} color={brushC} width={Math.round(pw * 0.9)} height={Math.round(stageH * 0.42)} left={pw * 0.05} top={stageTop - stageH * 0.02} rotate={-8} />
        <div data-layer="Club crest" style={{ position: 'absolute', left: pw / 2 - 40 * f, top: Math.round(ph * 0.012), opacity: 0.95 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={readable('#ffffff', paper, '#111111')} size={Math.round(80 * f)} shape="shield" />
        </div>
        <div data-layer="Players" style={{ position: 'absolute', left: 0, top: stageTop, width: pw, height: stageH }}>
          {draw.map(({ p, s }, i) => (
            <div key={p._id || i} data-collage-slot={s.row} style={{ position: 'absolute', left: Math.round(s.cx - s.w / 2), top: Math.round(s.bottom - s.h), width: Math.round(s.w), height: Math.round(s.h) }}>
              <FramedImage item={{ w: Math.round(s.w), h: Math.round(s.h), fit: 'contain', objPos: 'center bottom', fx: keptLook(keep, { edge: 3, contrast: 22 }) }} src={heroSrcOf(p)} resolve={resolve} />
            </div>
          ))}
          {!list.length && (
            <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', fontFamily: MONO, fontSize: 22, letterSpacing: 2, color: '#555', textAlign: 'center', padding: 40 }}>
              PICK PLAYERS WITH PHOTOS<br />THEY STACK HERE, UP TO {COLLAGE_MAX}
            </div>
          )}
        </div>
        <div data-layer="Tagline block" style={{ position: 'absolute', left: Math.round(pw * 0.03), top: Math.round(ph * 0.8), width: Math.round(pw * 0.36), height: Math.round(ph * 0.17), background: keep, display: 'flex', alignItems: 'center', padding: `0 ${Math.round(18 * f)}px`, boxSizing: 'border-box' }}>
          <span style={{ fontFamily: "'Permanent Marker', cursive", fontWeight: 400, fontSize: Math.round(36 * f), lineHeight: 1.05, color: inkOn(keep), transform: 'rotate(-3deg)' }}>{tag}</span>
        </div>
        <div data-layer="Match" style={{ position: 'absolute', right: Math.round(pw * 0.04), top: Math.round(ph * 0.83), textAlign: 'right', color: '#111' }}>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', alignItems: 'center' }}>
            <ClubLogo src={team.logo} monogram={team.monogram} color="#111" size={crest} shape="shield" />
            <span style={{ fontSize: Math.round(26 * f) }}>V</span>
            <ClubLogo src={opponent.logo} monogram={opponent.monogram || ''} color="#111" size={crest} shape="shield" />
          </div>
          <div style={{ fontFamily: MONO, fontSize: Math.round(15 * f), letterSpacing: 2, marginTop: 8 }}>{upper(joinDot(match.date, match.time))}</div>
          <div style={{ fontFamily: MONO, fontSize: Math.round(13 * f), letterSpacing: 2, opacity: 0.7 }}>{upper(match.venue)}</div>
        </div>
        <PastStrip past={past} x={Math.round(pw * 0.03)} y={Math.round(ph * 0.8 - 44 * f)} w={Math.round(pw * 0.7)} f={f * 0.8} color="#111111" align="left" bg={paper} />
      </div>
      <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink="#ffffff" h={Math.round(30 * f)} /></div>
    </LayerRoot>
  )
}
SquadCollage.displayName = 'SquadCollage'

// ── DL3 Final Score V ────────────────────────────────────────────────────────
export function FinalScoreV({ width = 1080, height = 1080, palette = {}, result: r = {}, parts, past }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f } = g
  const base = palette.primary || '#0b1530'
  const ink = palette.ink || '#ffffff'
  const accent = palette.accent || '#ffc233'
  const us = r.us || {}
  const them = r.them || {}
  const tied = r.winner === 'tie'
  const won = r.winner === 'us'
  const winFill = pc(parts, 'dl3WinFill', accent)
  const loseFill = pc(parts, 'dl3LoseFill', '#2a2d33')
  const line = tied ? (r.resultLabel || 'MATCH TIED') : `${upper((won ? us.name : them.name) || '')} WIN ${upper(r.margin || '')}`.trim()
  const titleH = Math.round(116 * f)
  const lineY = g.top + titleH + 8
  const frameTop = lineY + Math.round(60 * f)
  const potm = r.potm || {}
  const potmName = [potm.first, potm.last].filter(Boolean).join(' ')
  const potmH = potmName ? Math.round(86 * f) : 0
  const metaY = g.slotY - Math.round(48 * f)
  const pastH = hasPast(past) ? Math.round(44 * f) : 0
  const potmY = metaY - 12 - potmH - pastH
  const frameH = Math.max(240, potmY - 22 - frameTop)
  const gap = Math.round(width * 0.05)
  const fw = Math.round((width - 96 - gap) / 2)
  const side = (t, fill, x, layer) => (
    <CrestFrame layer={layer} x={x} y={frameTop} w={fw} h={frameH} fill={fill} logo={t.logo} mono={t.mono} ink={inkOn(fill)}>
      <div style={{ position: 'absolute', left: 14, right: 14, top: Math.round(frameH * 0.52), textAlign: 'center', color: inkOn(fill) }}>
        <AutoFitText text={upper(t.name || '')} max={Math.round(40 * f)} min={18} lines={1} measureDeps={[t.name, width]} style={{ textAlign: 'center', lineHeight: 1 }} />
        <div style={{ fontSize: Math.round(84 * f), lineHeight: 1, marginTop: 6 }}>{t.score || '—'}</div>
        {t.overs && <div style={{ fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 2, opacity: 0.75 }}>{t.overs} OVERS</div>}
      </div>
    </CrestFrame>
  )
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: base, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      {texture && <Paths layer="Burst" paths={burstPaths(width, height, 5)} color={ink} width={width} height={height} opacity={0.06} />}
      <div data-layer="Title" style={{ position: 'absolute', left: 48, right: 48, top: g.top, height: titleH }}>
        <AutoFitText text={pt(parts, 'dl3Title', tied ? (r.resultWord || 'FULL TIME') : 'FULL TIME')} max={titleH} min={48} lines={1} measureDeps={[width, height]}
          style={{ textAlign: 'center', lineHeight: 1, color: pc(parts, 'dl3TitleColor', ink) }} />
      </div>
      <div data-layer="Result line" style={{ position: 'absolute', left: 48, right: 48, top: lineY, textAlign: 'center', fontSize: Math.round(44 * f), color: accent, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{line}</div>
      {side(us, tied || won ? winFill : loseFill, 48, 'Our side')}
      {side(them, tied || !won ? winFill : loseFill, 48 + fw + gap, 'Opposition side')}
      {potmName && (
        <div data-layer="Player of the match" style={{ position: 'absolute', left: 48, right: 48, top: potmY, height: potmH, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 18, background: '#ffffff', color: '#0a0a0a', transform: 'rotate(-1.5deg)' }}>
          <span style={{ fontFamily: MONO, fontSize: Math.round(16 * f), letterSpacing: 2 }}>PLAYER OF THE MATCH</span>
          <span style={{ fontSize: Math.round(40 * f), whiteSpace: 'nowrap' }}>{upper(potmName)}</span>
          {potm.line && <span style={{ fontSize: Math.round(26 * f), color: base, whiteSpace: 'nowrap' }}>{upper(potm.line)}</span>}
        </div>
      )}
      <PastStrip past={past} x={48} y={metaY - pastH + 4} w={width - 96} f={f * 0.85} color={ink} />
      <div data-layer="Match details" style={{ position: 'absolute', left: 48, right: 48, top: metaY, textAlign: 'center', fontFamily: MONO, fontSize: Math.round(20 * f), letterSpacing: 2, opacity: 0.85 }}>
        {upper(joinDot(r.grade || r.comp, r.round, r.date))}
      </div>
      <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink={ink} h={Math.round(30 * f)} /></div>
    </LayerRoot>
  )
}
FinalScoreV.displayName = 'FinalScoreV'

// ── DL4 / DL5 Fixtures and Results Echo ──────────────────────────────────────
function RoundEcho({ width, height, palette, meta = {}, rows = [], club = {}, parts, kind }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f } = g
  const base = palette.primary || '#0b1530'
  const ink = palette.ink || '#ffffff'
  const accent = palette.accent || '#ffc233'
  const word = upper(pt(parts, 'dlRoundWord', kind === 'fixtures' ? 'FIXTURES' : 'RESULTS'))
  const fs = Math.round(Math.min(170 * f, (width - 80) / Math.max(4, word.length) * 1.7))
  const step = Math.round(fs * 0.62)
  const headH = fs + step * 2
  const top = g.top + headH + Math.round(28 * f)
  const avail = g.slotY - 20 - top
  const n = Math.max(1, rows.length)
  const rowH = Math.min(Math.round(118 * f), Math.floor(avail / n))
  const strip = pc(parts, 'dlStripColor', '#ffffff')
  const stripInk = inkOn(strip)
  const outcomeC = (o) => (/^W/.test(o) ? '#16a34a' : /^L/.test(o) ? '#dc2626' : '#6b7280')
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: base, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      {texture && <Paths layer="Grunge" paths={grungePaths(width, height, 4)} color={ink} width={width} height={height} opacity={0.22} />}
      <div data-layer="Echo heading" style={{ position: 'absolute', left: 48, right: 48, top: g.top }}>
        {[2, 1, 0].map((i) => (
          <div key={i} style={{
            position: i === 0 ? 'relative' : 'absolute', left: 0, top: i === 0 ? 0 : i * step, fontSize: fs, lineHeight: 1, whiteSpace: 'nowrap',
            color: i === 0 ? pc(parts, 'dlEchoColor', accent) : 'transparent', WebkitTextStroke: i === 0 ? undefined : `${Math.max(2, Math.round(fs * 0.02))}px ${pc(parts, 'dlEchoColor', accent)}`,
            opacity: i === 0 ? 1 : 0.5 - i * 0.14,
          }}>{word}</div>
        ))}
      </div>
      <div data-layer="Round and date" style={{ position: 'absolute', right: 48, top: g.top + 14, textAlign: 'right', fontFamily: MONO, fontSize: Math.round(20 * f), letterSpacing: 2, color: ink, opacity: 0.85 }}>
        {upper(joinDot(meta.round, meta.date))}
        <div style={{ marginTop: 10, display: 'flex', justifyContent: 'flex-end' }}><ClubLogo src={club.logo} monogram={club.mono} color={ink} size={Math.round(70 * f)} shape="shield" /></div>
      </div>
      <div data-layer="Rows" style={{ position: 'absolute', left: 30, right: 30, top }}>
        {rows.map((r, i) => {
          const h = rowH - 10
          const paths = tornPaperPaths(width - 60, h, 31 + i)
          return (
            <div key={i} style={{ position: 'relative', height: rowH, transform: `rotate(${i % 2 ? 0.6 : -0.6}deg)` }}>
              <svg width={width - 60} height={h} viewBox={`0 0 ${width - 60} ${h}`} style={{ position: 'absolute', left: 0, top: 0 }}>
                {paths.map((p, k) => <path key={k} d={p.d} fill={strip} />)}
              </svg>
              <div style={{ position: 'absolute', left: 28, right: 28, top: 0, height: h, display: 'flex', alignItems: 'center', gap: 18, color: stripInk }}>
                <span style={{ fontFamily: MONO, fontSize: Math.round(Math.min(18, h * 0.2) * f), letterSpacing: 1.5, width: Math.round(150 * f), flexShrink: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper(r.grade)}</span>
                <ClubLogo src={r.oppLogo} monogram={r.oppMono || ''} color={stripInk} size={Math.round(Math.min(56, h * 0.62))} shape="shield" />
                <span style={{ flex: 1, minWidth: 0, fontSize: Math.round(Math.min(40, h * 0.42) * f), lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {kind === 'fixtures' ? `${r.ha === 'A' ? '@ ' : 'V '}${upper(r.opp)}` : upper(r.opp)}
                </span>
                <RowForm past={r.past} size={Math.round(Math.min(24, h * 0.3) * f)} />
                {kind === 'fixtures' ? (
                  <span style={{ fontSize: Math.round(Math.min(30, h * 0.34) * f), whiteSpace: 'nowrap', color: base }}>{upper(joinDot(r.time, r.venue))}</span>
                ) : (
                  <>
                    <span style={{ fontSize: Math.round(Math.min(30, h * 0.34) * f), whiteSpace: 'nowrap' }}>{[r.us, r.them].filter(Boolean).join(' – ')}</span>
                    {r.outcome && <span style={{ padding: '4px 10px', background: outcomeC(upper(r.outcome)), color: '#fff', fontSize: Math.round(Math.min(24, h * 0.28) * f), lineHeight: 1 }}>{upper(r.outcome).slice(0, 1)}</span>}
                  </>
                )}
              </div>
            </div>
          )
        })}
        {!rows.length && <div style={{ fontFamily: MONO, fontSize: 24, letterSpacing: 2, opacity: 0.7 }}>{kind === 'fixtures' ? 'NO FIXTURES PULLED YET' : 'NO RESULTS PULLED YET'}</div>}
      </div>
      <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink={ink} h={Math.round(30 * f)} /></div>
    </LayerRoot>
  )
}
export function FixturesEcho({ width = 1080, height = 1080, palette = {}, meta, fixtures = [], club, parts }) {
  return <RoundEcho width={width} height={height} palette={palette} meta={meta} rows={fixtures} club={club} parts={parts} kind="fixtures" />
}
FixturesEcho.displayName = 'FixturesEcho'
export function ResultsEcho({ width = 1080, height = 1080, palette = {}, meta, results = [], club, parts }) {
  return <RoundEcho width={width} height={height} palette={palette} meta={meta} rows={results} club={club} parts={parts} kind="results" />
}
ResultsEcho.displayName = 'ResultsEcho'

// ── DL6 / DL7 Colour Pop ─────────────────────────────────────────────────────
// After the brush-stroke player poster: a dark ground, the same photo again,
// huge and faded, behind; brush strokes in the kit colour slashing across;
// the player in front in black and white with the kit colour kept; the name
// in giant worn type at the foot.
function ColourPopPoster({ width, height, team = {}, palette, parts, player, chip, lines = [] }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f, A } = g
  const ground = pc(parts, 'dlGround', '#111214')
  const keep = pc(parts, 'dlKeepColor', palette.primary || '#c8102e')
  const brushC = pc(parts, 'dlBrushColor', readable(keep, ground, palette.accent || '#e1251b'))
  const ink = '#ffffff'
  const photo = heroSrcOf(player)
  const first = upper(niceName(player?.first || ''))
  const last = upper(niceName(player?.last || ''))
  const resolve = resolver(palette)
  const nameH = Math.round(pick(A, { square: 170, portrait: 190, story: 210 }) * f)
  const linesH = (lines.length ? Math.round(46 * f) : 0) + (chip ? Math.round(40 * f) : 0)
  const nameY = g.slotY - 10 - linesH - nameH
  const heroTop = g.top + Math.round(pick(A, { square: 70, portrait: 110, story: 150 }) * f)
  const heroH = nameY + Math.round(nameH * 0.55) - heroTop
  const heroW = Math.round(width * 0.66)
  const ghostH = Math.round(height * 0.78)
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: ground, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      {photo && (
        <div data-layer="Faded photo" style={{
          position: 'absolute', left: -Math.round(width * 0.12), top: -Math.round(ghostH * 0.08), width: Math.round(width * 0.9), height: ghostH, opacity: 0.42,
          WebkitMaskImage: 'linear-gradient(90deg, #000 30%, transparent 92%)', maskImage: 'linear-gradient(90deg, #000 30%, transparent 92%)',
        }}>
          <FramedImage item={{ w: Math.round(width * 0.9), h: ghostH, fit: 'cover', objPos: 'center top', fx: { tone: 'mono', contrast: 30, brightness: -10 } }} src={photo} resolve={resolve} />
        </div>
      )}
      <Paths layer="Brush stroke 1" paths={brushPaths(width * 1.1, Math.round(height * 0.2), 13)} color={brushC} width={Math.round(width * 1.1)} height={Math.round(height * 0.2)} left={-width * 0.02} top={height * 0.2} rotate={-28} />
      <Paths layer="Brush stroke 2" paths={brushPaths(width * 0.8, Math.round(height * 0.12), 29)} color={brushC} width={Math.round(width * 0.8)} height={Math.round(height * 0.12)} left={width * 0.3} top={height * 0.46} rotate={-30} opacity={0.85} />
      {texture && <Paths layer="Splatter" paths={splatterPaths(Math.round(width * 0.4), Math.round(width * 0.4), 8)} color={brushC} width={Math.round(width * 0.4)} height={Math.round(width * 0.4)} left={width * 0.62} top={height * 0.08} opacity={0.5} />}
      {photo ? (
        <div data-layer="Player" style={{ position: 'absolute', left: Math.round(width * 0.5 - heroW / 2 + width * 0.06), top: heroTop, width: heroW, height: heroH }}>
          <FramedImage item={{ w: heroW, h: heroH, fit: 'contain', objPos: 'center bottom', fx: keptLook(keep, { contrast: 22 }) }} src={photo} resolve={resolve} />
        </div>
      ) : (
        <div data-layer="Club mark" style={{ position: 'absolute', left: width / 2 - 190, top: heroTop + heroH / 2 - 210, opacity: 0.9 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={380} shape="shield" />
        </div>
      )}
      <div data-layer="Name" style={{ position: 'absolute', left: 40, right: 40, top: nameY, height: nameH }}>
        <AutoFitText text={last || first || '—'} max={nameH} min={40} lines={1} measureDeps={[last, first, width, height]}
          style={{ textAlign: 'center', lineHeight: 1, color: pc(parts, 'nameColor', '#e8e8e8'), letterSpacing: 2 }} />
        {texture && <Paths layer="Worn type" paths={grungePaths(width - 80, nameH, 5)} color={ground} width={width - 80} height={nameH} opacity={0.9} />}
      </div>
      <div data-layer="First name and line" style={{ position: 'absolute', left: 48, right: 48, top: nameY + nameH + 4, textAlign: 'center' }}>
        {last && first && <div style={{ fontSize: Math.round(34 * f), letterSpacing: 10, lineHeight: 1.1, color: ink }}>{first}</div>}
        {chip && <div style={{ display: 'inline-block', marginTop: 8, padding: `${Math.round(5 * f)}px ${Math.round(14 * f)}px`, background: brushC, color: inkOn(brushC), fontSize: Math.round(22 * f), letterSpacing: 3, lineHeight: 1 }}>{upper(chip)}</div>}
        {lines.length > 0 && (
          <div style={{ display: 'flex', gap: Math.round(22 * f), justifyContent: 'center', marginTop: 8, flexWrap: 'wrap' }}>
            {lines.map((t, i) => <span key={i} style={{ fontSize: Math.round(28 * f), lineHeight: 1.1, color: i === 0 ? brushC : ink }}>{upper(t)}</span>)}
          </div>
        )}
      </div>
      <div data-layer="Club logo" style={{ position: 'absolute', left: 40, top: g.top }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(88 * f)} shape="shield" />
      </div>
      <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink={ink} h={Math.round(30 * f)} /></div>
    </LayerRoot>
  )
}
export function ColourPopSpotlight({ width = 1080, height = 1080, team, palette = {}, motm = {}, parts }) {
  const stats = (motm.stats || []).map((s) => `${s.value} ${s.label}`).slice(0, 3)
  return <ColourPopPoster width={width} height={height} team={team} palette={palette} parts={parts} player={motm.player}
    chip={pt(parts, 'dlChip', 'PLAYER OF THE MATCH')} lines={stats.length ? stats : (motm.summary ? [motm.summary] : [])} />
}
ColourPopSpotlight.displayName = 'ColourPopSpotlight'
export function ColourPopAnnounce({ width = 1080, height = 1080, team, palette = {}, announcement = {}, parts }) {
  const a = announcement || {}
  const lines = [a.headline, a.subheadline].filter(Boolean)
  return <ColourPopPoster width={width} height={height} team={team} palette={palette} parts={parts} player={a.player} chip={a.kind} lines={lines} />
}
ColourPopAnnounce.displayName = 'ColourPopAnnounce'

// The Design panel's colour and wording pickers for each layout.
const keepPart = colorPart('dlKeepColor', 'Colour kept in the photos (the rest goes black and white)', 'Photo', (p) => p.primary || '#0b1530')
const stripPart = colorPart('dlStripColor', 'Torn paper strip', 'Strip', () => '#ffffff')
registerParts({
  DL1: [
    textPart('dl1Title', 'Title', 'Title', () => 'MATCH DAY'),
    colorPart('dl1Paper', 'Paper background', 'Background', () => '#ebe8e1'),
    colorPart('dl1Ink', 'Type and icons', 'Background', () => '#16181d'),
    colorPart('dl1TitleColor', 'Title colour', 'Title', () => '#16181d'),
    colorPart('dl1UsFill', 'Our panel', 'Panels', (p) => p.primary || '#0b1530'),
    colorPart('dl1ThemFill', 'Opposition panel', 'Panels', () => '#1f3f8f'),
    keepPart,
  ],
  DL2: [
    textPart('dl2Word', 'Big word', 'Big word', () => 'GAMEDAY'),
    colorPart('dl2EchoColor', 'Big word colour', 'Big word', (p) => p.accent || '#e1251b'),
    textPart('dl2Tag', 'Tagline (top left)', 'Words', () => ''),
    colorPart('dl2Ground', 'Background', 'Background', () => '#0e0e10'),
    keepPart,
  ],
  DL3: [
    textPart('dl3Title', 'Title', 'Title', () => 'FULL TIME'),
    colorPart('dl3TitleColor', 'Title colour', 'Title', (p) => p.ink || '#ffffff'),
    colorPart('dl3WinFill', 'Winner frame', 'Frames', (p) => p.accent || '#ffc233'),
    colorPart('dl3LoseFill', 'Other frame', 'Frames', () => '#2a2d33'),
  ],
  DL4: [textPart('dlRoundWord', 'Big word', 'Heading', () => 'FIXTURES'), colorPart('dlEchoColor', 'Heading colour', 'Heading', (p) => p.accent || '#ffc233'), stripPart],
  DL5: [textPart('dlRoundWord', 'Big word', 'Heading', () => 'RESULTS'), colorPart('dlEchoColor', 'Heading colour', 'Heading', (p) => p.accent || '#ffc233'), stripPart],
  DL6: [textPart('dlChip', 'Tag', 'Name', () => 'PLAYER OF THE MATCH'), keepPart, colorPart('dlBrushColor', 'Brush strokes', 'Photo', (p) => p.primary || '#c8102e'), colorPart('dlGround', 'Background', 'Background', () => '#111214')],
  DL7: [keepPart, colorPart('dlBrushColor', 'Brush strokes', 'Photo', (p) => p.primary || '#c8102e'), colorPart('dlGround', 'Background', 'Background', () => '#111214')],
  DL8: [
    textPart('dl8Word1', 'Big word, first line', 'Big word', () => 'GAME'),
    textPart('dl8Word2', 'Big word, second line', 'Big word', () => 'DAY'),
    textPart('dl8Tag', 'Line above it', 'Big word', () => ''),
    textPart('dl8BadgeTop', 'Badge top line', 'Badge', () => 'WATCH US'),
    textPart('dl8Badge', 'Badge word', 'Badge', () => 'LIVE'),
    colorPart('dl8Tone', 'Photo tone', 'Colours', (p) => p.primary || '#0b6e66'),
    colorPart('dl8Accent', 'Accent', 'Colours', (p) => p.accent || '#2ee6c8'),
  ],
  DL9: [
    textPart('dl9Tag', 'Tagline', 'Words', () => ''),
    keepPart,
    colorPart('dl9Brush', 'Brush stroke', 'Poster', (p) => p.primary || '#c8102e'),
    colorPart('dl9Paper', 'Poster paper', 'Poster', () => '#ece9e3'),
  ],
})

// The Content panel each layout shares with the built-in layout of its type.
export const DESIGN_PANEL_ALIAS = { DL6: 'C3', DL7: 'C1' }

// Where each layout keeps the sponsor grid: a centred strip along the bottom,
// the same rectangle every layout above stops short of.
export const SPONSOR_SLOTS = { DL1: slotOf, DL2: slotOf, DL3: slotOf, DL4: slotOf, DL5: slotOf, DL6: slotOf, DL7: slotOf, DL8: slotOf, DL9: slotOf }
