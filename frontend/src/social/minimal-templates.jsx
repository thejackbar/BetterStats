// ─────────────────────────────────────────────────────────────────────────────
// MINIMAL LAYOUTS (v9.165.0), after the clean college and pro posts clubs share
// most: one strong photo, one big word, small quiet type, nothing else.
//
//   DL24 Clean Match Day     Lineup              the player big, the opponent big, the details small
//   DL25 Clean Final         Final Score         two crests, two scores, one result line
//   DL26 Clean Spotlight     Announcement        the player beside their name, the news small
//   DL27 Clean Player of the Match   Player of the Match   the same, with the figures
//   DL28 Clean Fixtures      Fixtures roundup    hairline rows
//   DL29 Clean Results       Results roundup     hairline rows, W or L
//
// Written for the Club Colour backgrounds (SocialBackgrounds.jsx): the root is
// the club's fill, which the editor turns fully transparent over a clean ground,
// and every mark is drawn in the post's ink (white on dark, dark on light) at a
// few strengths. No accent colour is used by default, because a Club Colour
// ground IS the accent colour and accent type would vanish on it. The big
// word behind the player is the ink at low strength, so it reads tone on tone on
// any ground. No textures. The photo is shown as it is: looks come from Effects.
//
// Same rules as design-templates.jsx: every root child carries data-layer, the
// sponsor strip stays clear (slotOf), photos go through FramedImage.
// ─────────────────────────────────────────────────────────────────────────────
import { AutoFitText, ClubLogo, CreditMark, heroSrcOf, featuredOf } from './cricket-templates'
import { pick } from './postAspect'
import { LayerRoot } from './postLayers'
import { niceName } from './card-kit'
import { pc, pt, registerParts, colorPart, textPart } from './layoutParts'
import FramedImage from './FramedImage'
import { geo, slotOf, joinDot, upper, resolver, hasText, FONT, WEIGHT, MONO } from './design-templates'
import { PastStrip, hasPast, RowForm } from './pastMeetings'

const BODY = "'Hanken Grotesk', 'Inter', sans-serif"

const Root = ({ width, height, bg, ink, children }) => (
  <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: bg, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>{children}</LayerRoot>
)
const Credit = ({ g, ink }) => (
  <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink={ink} h={Math.round(30 * g.f)} /></div>
)
// Small spaced capitals: the one secondary type style these layouts use.
const small = (f, size = 20) => ({ fontFamily: MONO, fontWeight: 500, fontSize: Math.round(size * f), letterSpacing: Math.round(3 * f), lineHeight: 1.3 })
// A 6-digit hex at a strength (other colour forms come back as they are).
const soft = (hex, a) => (/^#[0-9a-f]{6}$/i.test(hex || '') ? hex + Math.round(a * 255).toString(16).padStart(2, '0') : hex)
const nameOf = (p) => ({ first: upper(niceName(p?.first || '')), last: upper(niceName(p?.last || '')) })

// The big word behind the photo: the ink at low strength, tone on tone.
// Sized from the word's length (a condensed display face runs about 0.6 em
// a letter), so a long word shrinks to the width instead of running off it.
function GhostWord({ layer = 'Big word', text, x, y, w, h, color, opacity }) {
  if (!text) return null
  const fs = Math.max(40, Math.round(Math.min(h / 0.86, w / (Math.max(3, text.length) * 0.62))))
  return (
    <div data-layer={layer} style={{ position: 'absolute', left: x, top: y, width: w, height: h, opacity, color, pointerEvents: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
      <span style={{ fontSize: fs, lineHeight: 0.86, letterSpacing: -2, whiteSpace: 'nowrap' }}>{text}</span>
    </div>
  )
}

function Photo({ src, x, y, w, h, resolve, team, ink, pos = 'center bottom' }) {
  if (!src) {
    const size = Math.round(Math.min(w, h) * 0.5)
    return (
      <div data-layer="Club mark" style={{ position: 'absolute', left: x + (w - size) / 2, top: y + (h - size) / 2 }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={size} shape="shield" />
      </div>
    )
  }
  return (
    <div data-layer="Player" style={{ position: 'absolute', left: x, top: y, width: w, height: h }}>
      <FramedImage item={{ w, h, fit: 'contain', objPos: pos }} src={src} resolve={resolve} />
    </div>
  )
}

// ── DL24 Clean Match Day ─────────────────────────────────────────────────────
export function CleanMatchDay({ width = 1080, height = 1080, team = {}, opponent = {}, match = {}, players = [], palette = {}, featuredId, heroImage, parts, past }) {
  const g = geo(width, height)
  const { f, A } = g
  const ink = palette.ink || '#ffffff'
  const base = palette.primary || '#0b1530'
  const hi = pc(parts, 'mlHighlight', ink)
  const resolve = resolver(palette)
  const hero = featuredOf(players, featuredId)
  const photo = heroImage || heroSrcOf(hero)
  const word = upper(pt(parts, 'mlWord', 'MATCH DAY'))
  const opp = upper(opponent.name || opponent.short || '')
  const pastH = hasPast(past) ? Math.round(46 * f) : 0
  const footH = Math.round(150 * f)
  const footY = g.slotY - Math.round(18 * f) - footH - pastH
  const ghostTop = g.top + Math.round(pick(A, { square: 90, portrait: 130, story: 170 }) * f)
  const ghostH = Math.round(pick(A, { square: 300, portrait: 380, story: 440 }) * f)
  const heroTop = g.top + Math.round(40 * f)
  const heroH = footY + Math.round(30 * f) - heroTop
  const heroW = Math.round(width * 0.8)
  const crest = Math.round(74 * f)
  const list = players.length > 1 ? players.slice(0, 12) : []
  return (
    <Root width={width} height={height} bg={base} ink={ink}>
      <GhostWord text={word} x={40} y={ghostTop} w={width - 80} h={ghostH} color={ink} opacity={0.14} />
      <Photo src={photo} x={Math.round((width - heroW) / 2)} y={heroTop} w={heroW} h={heroH} resolve={resolve} team={team} ink={ink} />
      <div data-layer="Club logo" style={{ position: 'absolute', left: 48, top: g.top }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={crest} shape="shield" />
      </div>
      <div data-layer="Round" style={{ position: 'absolute', right: 48, top: g.top + Math.round(10 * f), textAlign: 'right', ...small(f, 18), opacity: 0.85 }}>
        {upper(joinDot(match.round, match.competition))}
      </div>
      {list.length > 0 && (
        <div data-layer="Team list" style={{ position: 'absolute', left: 48, top: g.top + crest + Math.round(36 * f), fontFamily: BODY, fontWeight: 600, fontSize: Math.round(19 * f), lineHeight: 1.45, letterSpacing: 1, opacity: 0.9, maxWidth: Math.round(width * 0.3) }}>
          {list.map((p, i) => <div key={i} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper([p.first, p.last].filter(Boolean).join(' '))}</div>)}
        </div>
      )}
      <div data-layer="Opponent" style={{ position: 'absolute', left: 48, right: 48, top: footY, height: Math.round(96 * f), display: 'flex', alignItems: 'flex-end', gap: Math.round(20 * f) }}>
        <span style={{ ...small(f, 22), paddingBottom: Math.round(12 * f), color: hi, flexShrink: 0 }}>VS</span>
        <div style={{ flex: 1, minWidth: 0, height: Math.round(96 * f) }}>
          <AutoFitText text={opp || 'OPPONENT'} max={Math.round(96 * f)} min={30} lines={1} measureDeps={[opp, width]} style={{ lineHeight: 1, textAlign: 'left' }} />
        </div>
        {opponent.logo && <ClubLogo src={opponent.logo} monogram={opponent.monogram || ''} color={ink} size={Math.round(70 * f)} shape="shield" />}
      </div>
      <div data-layer="Rule" style={{ position: 'absolute', left: 48, right: 48, top: footY + Math.round(108 * f), height: 2, background: hi, opacity: 0.6 }} />
      <div data-layer="Match details" style={{ position: 'absolute', left: 48, right: 48, top: footY + Math.round(122 * f), display: 'flex', justifyContent: 'space-between', gap: 20, ...small(f, 20) }}>
        <span style={{ whiteSpace: 'nowrap' }}>{upper(joinDot(match.date, match.time))}</span>
        <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', opacity: 0.85 }}>{upper(hasText(match.venue) ? match.venue : '')}</span>
      </div>
      <PastStrip past={past} x={48} y={footY + footH + Math.round(4 * f)} w={width - 96} f={f * 0.85} color={ink} />
      <Credit g={g} ink={ink} />
    </Root>
  )
}
CleanMatchDay.displayName = 'CleanMatchDay'

// ── DL25 Clean Final ─────────────────────────────────────────────────────────
export function CleanFinal({ width = 1080, height = 1080, palette = {}, result: r = {}, parts, past }) {
  const g = geo(width, height)
  const { f, A } = g
  const ink = palette.ink || '#ffffff'
  const base = palette.primary || '#0b1530'
  const hi = pc(parts, 'mlHighlight', ink)
  const us = r.us || {}
  const them = r.them || {}
  const tied = r.winner === 'tie'
  const won = r.winner === 'us'
  const word = upper(pt(parts, 'mlWord', tied ? 'TIED' : r.winner ? (won ? 'WIN' : 'LOSS') : 'FULL TIME'))
  const line = tied ? upper(r.resultLabel || 'MATCH TIED') : r.winner ? `${upper((won ? us.name : them.name) || '')} WON ${upper(r.margin || '')}`.trim() : ''
  const potm = r.potm || {}
  const potmName = upper([potm.first, potm.last].filter(Boolean).join(' '))
  const pastH = hasPast(past) ? Math.round(46 * f) : 0
  const metaY = g.slotY - Math.round(56 * f) - pastH
  const ghostH = Math.round(pick(A, { square: 330, portrait: 400, story: 460 }) * f)
  const ghostY = g.top + Math.round(pick(A, { square: 40, portrait: 120, story: 330 }) * f)
  const midY = ghostY + Math.round(ghostH * 0.38)
  const crest = Math.round(pick(A, { square: 170, portrait: 200, story: 240 }) * f)
  const colW = Math.round((width - 96) / 2)
  // The result line and the player of the match follow the scores, not the foot.
  const colBottom = midY + crest + Math.round(170 * f) + (us.overs || them.overs ? Math.round(24 * f) : 0)
  const lineY = Math.min(colBottom + Math.round(34 * f), metaY - Math.round((potmName ? 104 : 54) * f))
  const side = (t, x, lit, layer) => (
    <div data-layer={layer} style={{ position: 'absolute', left: x, top: midY, width: colW, textAlign: 'center', opacity: lit ? 1 : 0.62 }}>
      <div style={{ display: 'flex', justifyContent: 'center' }}><ClubLogo src={t.logo} monogram={t.mono} color={ink} size={crest} shape="shield" /></div>
      <div style={{ height: Math.round(40 * f), marginTop: Math.round(18 * f), padding: '0 12px' }}>
        <AutoFitText text={upper(t.name || '')} max={Math.round(36 * f)} min={16} lines={1} measureDeps={[t.name, width]} style={{ textAlign: 'center', lineHeight: 1 }} />
      </div>
      <div style={{ fontSize: Math.round(108 * f), lineHeight: 1, marginTop: Math.round(6 * f), color: lit ? hi : ink }}>{t.score || '—'}</div>
      {t.overs && <div style={{ ...small(f, 17), opacity: 0.75 }}>{t.overs} OVERS</div>}
    </div>
  )
  return (
    <Root width={width} height={height} bg={base} ink={ink}>
      <GhostWord text={word} x={40} y={ghostY} w={width - 80} h={ghostH} color={ink} opacity={0.12} />
      {side(us, 48, tied || won || !r.winner, 'Our side')}
      {side(them, 48 + colW, tied || !won || !r.winner, 'Opposition side')}
      <div data-layer="Divider" style={{ position: 'absolute', left: width / 2 - 1, top: midY + Math.round(crest * 0.1), height: Math.round(crest * 1.6), width: 2, background: ink, opacity: 0.3 }} />
      {line && <div data-layer="Result line" style={{ position: 'absolute', left: 48, right: 48, top: lineY, textAlign: 'center', fontSize: Math.round(40 * f), lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{line}</div>}
      {potmName && (
        <div data-layer="Player of the match" style={{ position: 'absolute', left: 48, right: 48, top: lineY + Math.round(54 * f), textAlign: 'center', ...small(f, 19), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          PLAYER OF THE MATCH <span style={{ color: hi, fontWeight: 700 }}>{potmName}</span>{potm.line ? ` · ${upper(potm.line)}` : ''}
        </div>
      )}
      <div data-layer="Rule" style={{ position: 'absolute', left: width / 2 - Math.round(60 * f), width: Math.round(120 * f), top: metaY - Math.round(8 * f), height: 2, background: hi, opacity: 0.6 }} />
      <div data-layer="Match details" style={{ position: 'absolute', left: 48, right: 48, top: metaY + Math.round(6 * f), textAlign: 'center', ...small(f, 18), opacity: 0.85 }}>
        {upper(joinDot(r.grade || r.comp, r.round, r.date))}
      </div>
      <PastStrip past={past} x={48} y={metaY + Math.round(40 * f)} w={width - 96} f={f * 0.85} color={ink} />
      <Credit g={g} ink={ink} />
    </Root>
  )
}
CleanFinal.displayName = 'CleanFinal'

// ── DL26 / DL27 Clean Spotlight and Player of the Match ─────────────────────
function CleanPlayerPoster({ width, height, team = {}, palette, parts, player, tag, lines = [], stats = [] }) {
  const g = geo(width, height)
  const { f, A } = g
  const ink = palette.ink || '#ffffff'
  const base = palette.primary || '#0b1530'
  const hi = pc(parts, 'mlHighlight', ink)
  const resolve = resolver(palette)
  const { first, last } = nameOf(player)
  const heroW = Math.round(width * pick(A, { square: 0.62, portrait: 0.68, story: 0.78 }))
  const heroTop = g.top + Math.round(pick(A, { square: 30, portrait: 60, story: 120 }) * f)
  const heroH = g.slotY - Math.round(10 * f) - heroTop
  const ghost = upper(pt(parts, 'mlWord', last || first || ''))
  const ghostH = Math.round(pick(A, { square: 280, portrait: 340, story: 400 }) * f)
  const textW = Math.round(width * 0.46)
  const statsH = stats.length ? Math.round(118 * f) : 0
  const linesH = lines.length ? Math.round(lines.length * 34 * f + 14 * f) : 0
  const nameH = Math.round(pick(A, { square: 210, portrait: 230, story: 250 }) * f)
  const blockBottom = g.slotY - Math.round(26 * f)
  const linesY = blockBottom - linesH - statsH
  const nameY = linesY - nameH
  const tagY = nameY - Math.round(40 * f)
  return (
    <Root width={width} height={height} bg={base} ink={ink}>
      <GhostWord text={ghost} x={20} y={g.top + Math.round(pick(A, { square: 60, portrait: 110, story: 200 }) * f)} w={width - 40} h={ghostH} color={ink} opacity={0.12} />
      <Photo src={heroSrcOf(player)} x={width - heroW + Math.round(width * 0.04)} y={heroTop} w={heroW} h={heroH} resolve={resolve} team={team} ink={ink} />
      <div data-layer="Club logo" style={{ position: 'absolute', left: 48, top: g.top }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(74 * f)} shape="shield" />
      </div>
      {tag && <div data-layer="Tag" style={{ position: 'absolute', left: 48, top: tagY, ...small(f, 20), color: hi, maxWidth: textW, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper(tag)}</div>}
      <div data-layer="Name" style={{ position: 'absolute', left: 48, top: nameY, width: textW, height: nameH, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
        {first && last && <div style={{ fontFamily: BODY, fontWeight: 500, fontSize: Math.round(44 * f), lineHeight: 1.05, letterSpacing: 1 }}>{first}</div>}
        <div style={{ height: Math.round(nameH * 0.62) }}>
          <AutoFitText text={last || first || '—'} max={Math.round(nameH * 0.62)} min={36} lines={1} measureDeps={[last, first, width, height]} style={{ lineHeight: 0.95, textAlign: 'left' }} />
        </div>
      </div>
      {lines.length > 0 && (
        <div data-layer="Words" style={{ position: 'absolute', left: 48, top: linesY + Math.round(14 * f), width: textW, fontFamily: BODY, fontWeight: 500, fontSize: Math.round(24 * f), lineHeight: 1.4 }}>
          {lines.map((t, i) => <div key={i} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', opacity: i === 0 ? 1 : 0.8 }}>{t}</div>)}
        </div>
      )}
      {stats.length > 0 && (
        <div data-layer="Figures" style={{ position: 'absolute', left: 48, top: blockBottom - statsH + Math.round(10 * f), width: textW, display: 'flex', gap: Math.round(30 * f), borderTop: `2px solid ${hi}`, paddingTop: Math.round(14 * f) }}>
          {stats.slice(0, 3).map((s, i) => (
            <div key={i} style={{ minWidth: 0 }}>
              <div style={{ fontSize: Math.round(54 * f), lineHeight: 1, whiteSpace: 'nowrap' }}>{s.value}</div>
              <div style={{ ...small(f, 15), opacity: 0.8, whiteSpace: 'nowrap' }}>{upper(s.label)}</div>
            </div>
          ))}
        </div>
      )}
      <Credit g={g} ink={ink} />
    </Root>
  )
}
export function CleanSpotlight({ width = 1080, height = 1080, team, palette = {}, announcement = {}, parts }) {
  const a = announcement || {}
  return <CleanPlayerPoster width={width} height={height} team={team} palette={palette} parts={parts} player={a.player}
    tag={pt(parts, 'mlTag', a.kind || '')} lines={[a.headline, a.subheadline].filter(Boolean)} />
}
CleanSpotlight.displayName = 'CleanSpotlight'
export function CleanPlayerOfMatch({ width = 1080, height = 1080, team, palette = {}, motm = {}, parts }) {
  const stats = (motm.stats || []).filter((s) => s && (s.value || s.value === 0))
  return <CleanPlayerPoster width={width} height={height} team={team} palette={palette} parts={parts} player={motm.player}
    tag={pt(parts, 'mlTag', 'PLAYER OF THE MATCH')} stats={stats} lines={stats.length ? [] : (motm.summary ? [motm.summary] : [])} />
}
CleanPlayerOfMatch.displayName = 'CleanPlayerOfMatch'

// ── DL28 / DL29 Clean Fixtures and Results ───────────────────────────────────
function CleanRound({ width, height, palette, meta = {}, rows = [], club = {}, parts, kind }) {
  const g = geo(width, height)
  const { f } = g
  const ink = palette.ink || '#ffffff'
  const base = palette.primary || '#0b1530'
  const hi = pc(parts, 'mlHighlight', ink)
  const word = upper(pt(parts, 'mlWord', kind === 'fixtures' ? 'FIXTURES' : 'RESULTS'))
  const titleH = Math.round(130 * f)
  const top = g.top + titleH + Math.round(64 * f)
  const avail = g.slotY - Math.round(24 * f) - top
  const n = Math.max(1, rows.length)
  const rowMax = pick(g.A, { square: 112, portrait: 130, story: 150 })
  const rowH = Math.min(Math.round(rowMax * f), Math.floor(avail / n))
  const t = (k) => Math.round(Math.min(k * f * 1.25, rowH * (k / 112)))
  return (
    <Root width={width} height={height} bg={base} ink={ink}>
      <div data-layer="Title" style={{ position: 'absolute', left: 48, right: 200, top: g.top, height: titleH }}>
        <AutoFitText text={word} max={titleH} min={48} lines={1} measureDeps={[word, width]} style={{ lineHeight: 1, textAlign: 'left' }} />
      </div>
      <div data-layer="Round and date" style={{ position: 'absolute', left: 48, right: 200, top: g.top + titleH + Math.round(10 * f), ...small(f, 19), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', opacity: 0.85 }}>{upper(joinDot(meta.round, meta.date))}</div>
      <div data-layer="Club logo" style={{ position: 'absolute', right: 48, top: g.top + Math.round(10 * f) }}>
        <ClubLogo src={club.logo} monogram={club.mono} color={ink} size={Math.round(96 * f)} shape="shield" />
      </div>
      <div data-layer="Rows" style={{ position: 'absolute', left: 48, right: 48, top }}>
        {rows.map((r, i) => {
          const o = upper(r.outcome || '').slice(0, 1)
          return (
            <div key={i} style={{ height: rowH, display: 'flex', alignItems: 'center', gap: Math.round(18 * f), borderTop: i === 0 ? `2px solid ${hi}` : `1px solid ${soft(ink, 0.35)}` }}>
              <span style={{ ...small(f, Math.min(17, t(17))), width: Math.round(150 * f), flexShrink: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', opacity: 0.8 }}>{upper(r.grade)}</span>
              <span style={{ flex: 1, minWidth: 0, fontSize: t(40), lineHeight: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {kind === 'fixtures' ? `${r.ha === 'A' ? '@ ' : 'V '}${upper(r.opp)}` : upper(r.opp)}
              </span>
              <RowForm past={r.past} size={t(22)} />
              {kind === 'fixtures' ? (
                <span style={{ ...small(f, Math.min(19, t(19))), whiteSpace: 'nowrap', textAlign: 'right' }}>{upper(joinDot(r.time, r.venue))}</span>
              ) : (
                <>
                  <span style={{ fontSize: t(30), whiteSpace: 'nowrap', opacity: 0.9 }}>{[r.us, r.them].filter(Boolean).join(' – ')}</span>
                  {o && <span style={{ width: t(40), height: t(40), display: 'inline-flex', alignItems: 'center', justifyContent: 'center', border: `2px solid ${o === 'W' ? hi : ink}`, background: o === 'W' ? hi : 'transparent', color: o === 'W' ? base : ink, fontSize: t(22), lineHeight: 1, flexShrink: 0, opacity: o === 'W' ? 1 : 0.75 }}>{o}</span>}
                </>
              )}
            </div>
          )
        })}
        {!rows.length && <div style={{ ...small(f, 22), opacity: 0.7 }}>{kind === 'fixtures' ? 'NO FIXTURES PULLED YET' : 'NO RESULTS PULLED YET'}</div>}
      </div>
      <Credit g={g} ink={ink} />
    </Root>
  )
}
export function CleanFixtures({ width = 1080, height = 1080, palette = {}, meta, fixtures = [], club, parts }) {
  return <CleanRound width={width} height={height} palette={palette} meta={meta} rows={fixtures} club={club} parts={parts} kind="fixtures" />
}
CleanFixtures.displayName = 'CleanFixtures'
export function CleanResults({ width = 1080, height = 1080, palette = {}, meta, results = [], club, parts }) {
  return <CleanRound width={width} height={height} palette={palette} meta={meta} rows={results} club={club} parts={parts} kind="results" />
}
CleanResults.displayName = 'CleanResults'

// The Design panel's pickers. "Highlight" is the one extra colour: Auto is the
// post's ink, so the layout stays one colour on any ground until a club picks.
const hiPart = colorPart('mlHighlight', 'Highlight (rule, VS, winning score)', 'Colours', (p) => p.ink || '#ffffff', { autoLabel: 'Same as the words' })
registerParts({
  DL24: [textPart('mlWord', 'Big word behind the player', 'Words', () => 'MATCH DAY'), hiPart],
  DL25: [textPart('mlWord', 'Big word (Auto: WIN, LOSS or TIED)', 'Words', () => ''), hiPart],
  DL26: [textPart('mlWord', 'Big word (Auto: their surname)', 'Words', () => ''), textPart('mlTag', 'Line above the name (Auto: the kind)', 'Words', () => ''), hiPart],
  DL27: [textPart('mlWord', 'Big word (Auto: their surname)', 'Words', () => ''), textPart('mlTag', 'Line above the name', 'Words', () => 'PLAYER OF THE MATCH'), hiPart],
  DL28: [textPart('mlWord', 'Title', 'Words', () => 'FIXTURES'), hiPart],
  DL29: [textPart('mlWord', 'Title', 'Words', () => 'RESULTS'), hiPart],
})

export const DESIGN_PANEL_ALIAS_MIN = { DL26: 'C1', DL27: 'C3' }
export const SPONSOR_SLOTS = Object.fromEntries(['DL24', 'DL25', 'DL26', 'DL27', 'DL28', 'DL29'].map((id) => [id, slotOf]))
