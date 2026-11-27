// ─────────────────────────────────────────────────────────────────────────────
// DESIGN LAYOUTS: the poster styles from the design effects (v9.154.0) made
// into real layouts, each on its own post type and fed by that type's data.
//
//   DL1 Match Day V      Lineup        hero cut-out and opponent crest in V frames, XI below
//   DL2 Gameday Echo     Lineup        stacked GAMEDAY behind an outlined cut-out, XI and brush stroke
//   DL3 Final Score V    Final Score   both crests in V frames, scores, winner lit, POTM
//   DL4 Fixtures Echo    Fixtures      echo heading, one torn-paper strip per fixture
//   DL5 Results Echo     Results       echo heading, one torn-paper strip per result
//   DL6 Colour Pop       Player of the Match   photo in black and white but for the kit colour
//   DL7 Colour Pop       Announcement  the same look on the announcement fields
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
import { FRAMES, framePoints, frameClip, burstPaths, speedPaths, brushPaths, tornPaperPaths, grungePaths } from './designFx'

const FONT = "var(--social-display-font, 'Anton', 'Hanken Grotesk', sans-serif)"
const WEIGHT = 'var(--social-display-font-weight, 700)'
const MONO = "'JetBrains Mono', monospace"
const VBASE = framePoints(FRAMES.find((f) => f.key === 'vbottom'))

// Shared geometry: the safe top and bottom (a story's ends sit under the app's
// own bars), a size factor, and the sponsor strip along the bottom.
function geo(width, height) {
  const A = aspectOf(width, height)
  const f = pick(A, { square: 1, portrait: 1.06, story: 1.12 })
  const top = pick(A, { square: 40, portrait: 56, story: 210 })
  const bottom = pick(A, { square: 26, portrait: 40, story: 240 })
  const slotH = Math.round(84 * f)
  const slotY = height - bottom - slotH
  return { A, f, top, bottom, slotH, slotY }
}
const slotOf = (width, height) => {
  const g = geo(width, height)
  const w = Math.min(width - 220, 640)
  return { x: Math.round((width - w) / 2), y: g.slotY, w, h: g.slotH, pad: 6, gap: 22, panel: 'light' }
}

const hasText = (v) => v && v !== 'COMPETITION'
const joinDot = (...xs) => xs.filter(hasText).join(' · ')
const upper = (v) => String(v || '').toUpperCase()

function Paths({ layer, paths, color, width, height, left = 0, top = 0, opacity = 1, rotate = 0 }) {
  return (
    <svg data-layer={layer} width={width} height={height} viewBox={`0 0 ${width} ${height}`}
      style={{ position: 'absolute', left, top, opacity, overflow: 'visible', transform: rotate ? `rotate(${rotate}deg)` : undefined, pointerEvents: 'none' }}>
      {paths.map((p, i) => <path key={i} d={p.d} fill={color} fillOpacity={p.opacity} />)}
    </svg>
  )
}

// A crest drawn inside a V-base frame, on the frame's fill.
function CrestFrame({ layer, x, y, w, h, fill, logo, mono, ink, children }) {
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

const resolver = (palette) => (c) => ({
  primary: palette.primary, secondary: palette.secondary, accent: palette.accent, ink: palette.ink,
  white: '#ffffff', black: '#0a0a0a',
}[c] || c)

// The XI as names in columns, last names in capitals, (C) and (WK) marked.
function NameColumns({ players, cols, color, mark, fontSize, lineH }) {
  const per = Math.ceil(players.length / cols)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, columnGap: 24 }}>
      {Array.from({ length: cols }, (_, c) => (
        <div key={c}>
          {players.slice(c * per, (c + 1) * per).map((p, i) => (
            <div key={i} style={{ fontSize, lineHeight: `${lineH}px`, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color }}>
              {upper(p.last || p.first)}
              {p.captain && <span style={{ color: mark }}> (C)</span>}
              {p.keeper && <span style={{ color: mark }}> (WK)</span>}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

// ── DL1 Match Day V ──────────────────────────────────────────────────────────
export function MatchDayV({ width = 1080, height = 1080, team = {}, opponent = {}, match = {}, players = [], palette = {}, featuredId, heroImage, parts }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f } = g
  const base = palette.primary || '#0b1530'
  const ink = palette.ink || '#ffffff'
  const accent = palette.accent || '#ffc233'
  const hero = featuredOf(players, featuredId)
  const photo = heroImage || heroSrcOf(hero)
  const usFill = pc(parts, 'dl1UsFill', accent)
  const themFill = pc(parts, 'dl1ThemFill', '#ffffff')
  const titleH = Math.round(118 * f)
  const subY = g.top + titleH + 6
  const frameTop = subY + Math.round(46 * f)
  const cols = players.length > 8 ? 3 : 2
  const lineH = Math.round(36 * f)
  const listH = players.length ? Math.ceil(players.length / cols) * lineH : 0
  const dateY = g.slotY - Math.round(54 * f)
  const listY = dateY - 14 - listH
  const frameH = Math.max(200, listY - 24 - frameTop)
  const gap = Math.round(width * 0.06)
  const fw = Math.round((width - 96 - gap) / 2)
  const usName = upper(team.name || team.short)
  const themName = upper(opponent.name || opponent.short || 'OPPONENT')
  const resolve = resolver(palette)
  const nameIn = (fill) => ({ position: 'absolute', left: 12, right: 12, top: Math.round(frameH * 0.6), color: inkOn(fill), textAlign: 'center' })
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: base, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      {texture && <Paths layer="Burst" paths={burstPaths(width, height, 11)} color={ink} width={width} height={height} opacity={0.06} />}
      <div data-layer="Title" style={{ position: 'absolute', left: 48, right: 48, top: g.top, height: titleH }}>
        <AutoFitText text={pt(parts, 'dl1Title', 'MATCH DAY')} max={titleH} min={48} lines={1} measureDeps={[width, height]}
          style={{ textAlign: 'center', lineHeight: 1, color: pc(parts, 'dl1TitleColor', ink) }} />
      </div>
      <div data-layer="Competition" style={{ position: 'absolute', left: 48, right: 48, top: subY, textAlign: 'center', fontFamily: MONO, fontSize: Math.round(22 * f), letterSpacing: 3, color: accent }}>
        {upper(joinDot(match.competition, match.round))}
      </div>
      <div data-layer="Our frame" style={{ position: 'absolute', left: 48, top: frameTop, width: fw, height: frameH }}>
        {photo ? (
          <FramedImage item={{ w: fw, h: frameH, mask: 'vbottom', frameFill: usFill, popOut: 0.14, fit: 'contain', objPos: 'center bottom' }} src={photo} resolve={resolve} />
        ) : (
          <CrestFrame layer="Our crest" x={0} y={0} w={fw} h={frameH} fill={usFill} logo={team.logo} mono={team.monogram} ink={inkOn(usFill)} />
        )}
        <div style={nameIn(usFill)}>
          <AutoFitText text={usName} max={Math.round(60 * f)} min={22} lines={1} measureDeps={[usName, width]} style={{ textAlign: 'center', lineHeight: 1 }} />
        </div>
      </div>
      <CrestFrame layer="Opponent frame" x={48 + fw + gap} y={frameTop} w={fw} h={frameH} fill={themFill} logo={opponent.logo} mono={opponent.monogram} ink={inkOn(themFill)}>
        <div style={nameIn(themFill)}>
          <AutoFitText text={themName} max={Math.round(60 * f)} min={22} lines={1} measureDeps={[themName, width]} style={{ textAlign: 'center', lineHeight: 1 }} />
        </div>
      </CrestFrame>
      <div data-layer="Versus" style={{
        position: 'absolute', left: 48 + fw - 30, width: gap + 60, top: frameTop + frameH * 0.42, textAlign: 'center', fontSize: Math.round(110 * f), lineHeight: 1,
        color: pc(parts, 'dl1VsColor', ink), textShadow: Array.from({ length: 10 }, (_, i) => `${i + 1}px ${i + 1}px 0 #0a0a0a`).join(','),
      }}>V</div>
      {players.length > 0 && (
        <div data-layer="Team list" style={{ position: 'absolute', left: 60, right: 60, top: listY }}>
          <NameColumns players={players} cols={cols} color={ink} mark={accent} fontSize={Math.round(28 * f)} lineH={lineH} />
        </div>
      )}
      <div data-layer="Date and venue" style={{ position: 'absolute', left: 48, right: 48, top: dateY, textAlign: 'center', fontSize: Math.round(36 * f), letterSpacing: 1, color: pc(parts, 'dl1DateColor', accent), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {upper(joinDot(match.date, match.time, match.venue))}
      </div>
      <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink={ink} h={Math.round(30 * f)} /></div>
    </LayerRoot>
  )
}
MatchDayV.displayName = 'MatchDayV'

// ── DL2 Gameday Echo ─────────────────────────────────────────────────────────
export function GamedayEcho({ width = 1080, height = 1080, team = {}, opponent = {}, match = {}, players = [], palette = {}, featuredId, heroImage, parts }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f } = g
  const base = palette.primary || '#0b1530'
  const ink = palette.ink || '#ffffff'
  const accent = palette.accent || '#ffc233'
  const echoC = pc(parts, 'dl2EchoColor', accent)
  const brushC = pc(parts, 'dl2BrushColor', accent)
  const hero = featuredOf(players, featuredId)
  const photo = heroImage || heroSrcOf(hero)
  const word = upper(pt(parts, 'dl2Word', 'GAMEDAY'))
  const fs = Math.round(Math.min(200 * f, (width - 60) / Math.max(4, word.length) * 1.75))
  const step = Math.round(fs * 0.78)
  const echoN = pick(g.A, { square: 5, portrait: 6, story: 7 })
  const brushH = Math.round(230 * f)
  const brushY = g.slotY - brushH + Math.round(20 * f)
  const heroTop = g.top + Math.round(fs * 0.55)
  const heroBottom = brushY + Math.round(brushH * 0.55)
  const heroL = Math.round(width * 0.36)
  const heroW = width - heroL - 10
  const resolve = resolver(palette)
  const opp = upper(opponent.name || 'OPPONENT')
  const listTop = heroTop + Math.round(fs * 0.85)
  const lineH = Math.round(38 * f)
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: base, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      {texture && <Paths layer="Speed lines" paths={speedPaths(width, Math.round(height * 0.6), 9)} color={ink} width={width} height={Math.round(height * 0.6)} top={Math.round(height * 0.18)} opacity={0.16} rotate={-12} />}
      <div data-layer="Echo word" style={{ position: 'absolute', left: 0, right: 0, top: g.top, textAlign: 'center' }}>
        {Array.from({ length: echoN }, (_, i) => echoN - 1 - i).map((i) => (
          <div key={i} style={{
            position: i === 0 ? 'relative' : 'absolute', left: 0, right: 0, top: i === 0 ? 0 : i * step, fontSize: fs, lineHeight: 1, whiteSpace: 'nowrap',
            color: i === 0 ? echoC : 'transparent', WebkitTextStroke: i === 0 ? undefined : `${Math.max(2, Math.round(fs * 0.02))}px ${echoC}`,
            opacity: i === 0 ? 1 : Math.max(0.14, 1 - i * 0.18),
          }}>{word}</div>
        ))}
      </div>
      <Paths layer="Brush stroke" paths={brushPaths(width - 40, brushH, 21)} color={brushC} width={width - 40} height={brushH} left={20} top={brushY} rotate={-4} />
      {photo ? (
        <div data-layer="Player" style={{ position: 'absolute', left: heroL, top: heroTop, width: heroW, height: heroBottom - heroTop }}>
          <FramedImage item={{ w: heroW, h: heroBottom - heroTop, fit: 'contain', objPos: 'center bottom', fx: { outline: { width: Math.round(7 * f), color: 'white' }, shadow: { x: 0, y: 16, blur: 30, opacity: 55 } } }} src={photo} resolve={resolve} />
        </div>
      ) : (
        <div data-layer="Club mark" style={{ position: 'absolute', left: heroL + heroW / 2 - 170, top: heroTop + (heroBottom - heroTop) / 2 - 200, opacity: 0.95 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={340} shape="shield" />
        </div>
      )}
      {players.length > 0 && (
        <div data-layer="Team list" style={{ position: 'absolute', left: 48, top: listTop, width: heroL - 40, padding: '14px 18px', background: `${base}d9`, borderLeft: `6px solid ${accent}` }}>
          <NameColumns players={players} cols={1} color={ink} mark={accent} fontSize={Math.round(Math.min(30, (brushY - listTop - 40) / Math.max(1, players.length) * 0.78) * f)} lineH={Math.min(lineH, Math.floor((brushY - listTop - 40) / Math.max(1, players.length)))} />
        </div>
      )}
      <div data-layer="Opponent and time" style={{ position: 'absolute', left: 70, right: 70, top: brushY + Math.round(brushH * 0.22), textAlign: 'center', color: inkOn(brushC), transform: 'skewX(-8deg)' }}>
        <div style={{ fontSize: Math.round(60 * f), lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>V {opp}</div>
        <div style={{ fontSize: Math.round(32 * f), lineHeight: 1.2, marginTop: 6 }}>{upper(joinDot(match.date, match.time, match.venue))}</div>
      </div>
      <div data-layer="Club logo" style={{ position: 'absolute', left: 40, top: g.top - 10 }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(86 * f)} shape="shield" />
      </div>
      <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink={ink} h={Math.round(30 * f)} /></div>
    </LayerRoot>
  )
}
GamedayEcho.displayName = 'GamedayEcho'

// ── DL3 Final Score V ────────────────────────────────────────────────────────
export function FinalScoreV({ width = 1080, height = 1080, palette = {}, result: r = {}, parts }) {
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
  const potmY = metaY - 12 - potmH
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
// The photo full-bleed in black and white except the kit colour (the club's
// primary unless the Design panel picks another), a torn paper strip with the
// name, and the figures or the line under it.
function ColourPopPoster({ width, height, team = {}, palette, parts, player, chip, lines = [] }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f } = g
  const base = palette.primary || '#0b1530'
  const ink = palette.ink || '#ffffff'
  const accent = palette.accent || '#ffc233'
  const keep = pc(parts, 'dlKeepColor', base)
  const strip = pc(parts, 'dlStripColor', '#ffffff')
  const photo = heroSrcOf(player)
  const first = niceName(player?.first || '')
  const last = niceName(player?.last || '')
  const stripH = Math.round(pick(g.A, { square: 318, portrait: 330, story: 350 }) * f)
  const stripY = g.slotY - stripH - Math.round(10 * f)
  const resolve = resolver(palette)
  const photoH = stripY + Math.round(stripH * 0.4)
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: base, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      {photo ? (
        <div data-layer="Photo" style={{ position: 'absolute', left: 0, top: 0, width, height: photoH }}>
          <FramedImage item={{ w: width, h: photoH, fit: 'cover', objPos: 'center top', fx: { tone: 'mono', splash: [{ color: keep, range: 26, soft: 18 }], splashStrength: 100, contrast: 16 } }} src={photo} resolve={resolve} />
        </div>
      ) : (
        <div data-layer="Club mark" style={{ position: 'absolute', left: width / 2 - 200, top: stripY / 2 - 210, opacity: 0.9 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={400} shape="shield" />
        </div>
      )}
      {texture && <Paths layer="Grunge" paths={grungePaths(width, height, 8)} color="#ffffff" width={width} height={height} opacity={0.28} />}
      <Paths layer="Torn strip" paths={tornPaperPaths(width + 40, stripH, 17)} color={strip} width={width + 40} height={stripH} left={-20} top={stripY} rotate={-2.5} />
      <div data-layer="Name and line" style={{ position: 'absolute', left: 64, right: 64, top: stripY + Math.round(stripH * 0.11), color: inkOn(strip), transform: 'rotate(-2.5deg)' }}>
        {chip && <div style={{ display: 'inline-block', padding: `${Math.round(6 * f)}px ${Math.round(14 * f)}px`, background: accent, color: inkOn(accent), fontSize: Math.round(24 * f), letterSpacing: 3, lineHeight: 1, marginBottom: Math.round(10 * f) }}>{upper(chip)}</div>}
        {first && <div style={{ fontSize: Math.round(40 * f), lineHeight: 1, opacity: 0.8 }}>{upper(first)}</div>}
        <AutoFitText text={upper(last || '—')} max={Math.round(118 * f)} min={36} lines={1} measureDeps={[last, width, height]} style={{ lineHeight: 1 }} />
        {lines.length > 0 && (
          <div style={{ display: 'flex', gap: Math.round(22 * f), marginTop: Math.round(8 * f), flexWrap: 'wrap', color: base }}>
            {lines.map((t, i) => <span key={i} style={{ fontSize: Math.round(32 * f), lineHeight: 1.1 }}>{upper(t)}</span>)}
          </div>
        )}
      </div>
      <div data-layer="Club logo" style={{ position: 'absolute', left: 40, top: g.top }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(96 * f)} shape="shield" />
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
const keepPart = colorPart('dlKeepColor', 'Colour kept in the photo (the rest goes black and white)', 'Photo', (p) => p.primary || '#0b1530')
const stripPart = colorPart('dlStripColor', 'Torn paper strip', 'Strip', () => '#ffffff')
registerParts({
  DL1: [
    textPart('dl1Title', 'Title', 'Title', () => 'MATCH DAY'),
    colorPart('dl1TitleColor', 'Title colour', 'Title', (p) => p.ink || '#ffffff'),
    colorPart('dl1UsFill', 'Our frame', 'Frames', (p) => p.accent || '#ffc233'),
    colorPart('dl1ThemFill', 'Opposition frame', 'Frames', () => '#ffffff'),
    colorPart('dl1VsColor', 'The V', 'Frames', (p) => p.ink || '#ffffff'),
    colorPart('dl1DateColor', 'Date and venue', 'Details', (p) => p.accent || '#ffc233'),
  ],
  DL2: [
    textPart('dl2Word', 'Big word', 'Big word', () => 'GAMEDAY'),
    colorPart('dl2EchoColor', 'Big word colour', 'Big word', (p) => p.accent || '#ffc233'),
    colorPart('dl2BrushColor', 'Brush stroke', 'Brush stroke', (p) => p.accent || '#ffc233'),
  ],
  DL3: [
    textPart('dl3Title', 'Title', 'Title', () => 'FULL TIME'),
    colorPart('dl3TitleColor', 'Title colour', 'Title', (p) => p.ink || '#ffffff'),
    colorPart('dl3WinFill', 'Winner frame', 'Frames', (p) => p.accent || '#ffc233'),
    colorPart('dl3LoseFill', 'Other frame', 'Frames', () => '#2a2d33'),
  ],
  DL4: [textPart('dlRoundWord', 'Big word', 'Heading', () => 'FIXTURES'), colorPart('dlEchoColor', 'Heading colour', 'Heading', (p) => p.accent || '#ffc233'), stripPart],
  DL5: [textPart('dlRoundWord', 'Big word', 'Heading', () => 'RESULTS'), colorPart('dlEchoColor', 'Heading colour', 'Heading', (p) => p.accent || '#ffc233'), stripPart],
  DL6: [textPart('dlChip', 'Tag', 'Name strip', () => 'PLAYER OF THE MATCH'), keepPart, stripPart],
  DL7: [keepPart, stripPart],
})

// The Content panel each layout shares with the built-in layout of its type.
export const DESIGN_PANEL_ALIAS = { DL6: 'C3', DL7: 'C1' }

// Where each layout keeps the sponsor grid: a centred strip along the bottom,
// the same rectangle every layout above stops short of.
export const SPONSOR_SLOTS = { DL1: slotOf, DL2: slotOf, DL3: slotOf, DL4: slotOf, DL5: slotOf, DL6: slotOf, DL7: slotOf }
