// ─────────────────────────────────────────────────────────────────────────────
// LADDER & LEADERS layouts (v9.157.0), on the Ladder & Leaders post type.
//
//   DL21 Ladder         the grade's live ladder, our row lit
//   DL22 Head to Head   our ladder row against the opponent's, as mirrored bars
//   DL23 Stat Leaders   the club's top run scorers, wicket takers or fielders
//
// All three read one `standings` prop the editor builds from the club's team
// ladders (/ladders/teams, Cricket Australia's live ladder per team) and the
// club's own leaderboards (/leaderboard/batting|bowling|fielding). A figure the
// ladder does not carry is left out, never filled in.
// ─────────────────────────────────────────────────────────────────────────────
import { AutoFitText, ClubLogo, CreditMark } from './cricket-templates'
import { pick } from './postAspect'
import { LayerRoot } from './postLayers'
import { pc, pt, inkOn, registerParts, colorPart, textPart } from './layoutParts'
import { usePostLook } from './postLook'
import FramedImage from './FramedImage'
import { grungePaths, halftoneDots } from './designFx'
import { geo, slotOf, joinDot, upper, readable, Paths, resolver, FONT, WEIGHT, MONO } from './design-templates'
import { PastBlock, hasPast } from './pastMeetings'

const Credit = ({ g, ink }) => (
  <div data-layer="Platform credit" style={{ position: 'absolute', right: 30, bottom: g.bottom, pointerEvents: 'none' }}><CreditMark ink={ink} h={Math.round(30 * g.f)} /></div>
)
const fmt = (v) => (v === null || v === undefined || v === '' ? '' : (typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(3).replace(/0+$/, '').replace(/\.$/, '') : String(v)))
// Initials of the club, not of the grade words after it ("North Perth 4th XI"
// is NP, "WSCC One Day 4's" is WSCC's first two letters).
const GRADE_WORD = /^(\d+(st|nd|rd|th)?|xi|one|day|t20|grade|div(ision)?|[ivx]+|\d+'?s|-|women'?s|men'?s|u\d+|colts|res|reserves|club)$/i
const mono = (name) => {
  const words = String(name || '').replace(/[()]/g, ' ').split(/\s+/).filter(Boolean)
  const club = words.filter((w) => !GRADE_WORD.test(w))
  const use = club.length ? club : words
  if (use[0] && /^[A-Z]{3,6}$/.test(use[0])) return use[0].slice(0, 3)
  return use.slice(0, 2).map((w) => w[0]).join('').toUpperCase()
}

function Empty({ text, g }) {
  return (
    <div data-layer="Waiting for data" style={{ position: 'absolute', left: 60, right: 60, top: g.top + 260 * g.f, textAlign: 'center', fontFamily: MONO, fontSize: 22, letterSpacing: 2, opacity: 0.8, lineHeight: 1.6 }}>{text}</div>
  )
}

// ── DL21 Ladder ──────────────────────────────────────────────────────────────
// Rows to show: the top of the ladder, and our row even when it sits below the
// cut (the row above the cut then gives way to it).
export function ladderRowsShown(rows, max) {
  const list = rows || []
  if (list.length <= max) return list
  const top = list.slice(0, max)
  if (top.some((r) => r.is_club)) return top
  const ours = list.find((r) => r.is_club)
  return ours ? [...top.slice(0, max - 1), ours] : top
}
export function DesignLadder({ width = 1080, height = 1080, team = {}, palette = {}, standings = {}, parts }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f, A } = g
  const ground = pc(parts, 'dl21Ground', palette.primary || '#0b1530')
  const lit = pc(parts, 'dl21Lit', readable(palette.accent || '#ffc233', ground, '#ffffff'))
  const ink = '#ffffff'
  const s = standings || {}
  const cols = (s.columns || []).filter((c) => ['played', 'won', 'lost', 'competitionPoints', 'netRunRate', 'quotient'].includes(c.id)).slice(0, 5)
  const headH = Math.round(150 * f)
  const top = g.top + headH
  const avail = g.slotY - 20 - top - Math.round(84 * f)
  const max = pick(A, { square: 10, portrait: 12, story: 14 })
  const rows = ladderRowsShown(s.rows, max)
  const rowH = Math.min(Math.round(pick(A, { square: 84, portrait: 96, story: 118 }) * f), Math.floor(avail / Math.max(1, rows.length)))
  const fs = Math.round(Math.min(pick(A, { square: 30, portrait: 32, story: 36 }) * f, rowH * 0.4))
  const numFs = Math.round(fs * 0.9)
  const pad = Math.round(16 * f)
  const crestBox = Math.round(rowH * 0.62)
  // Each figure column is as wide as its longest entry (heading included), so a
  // net run rate like -0.071 never runs into the points beside it.
  const colW = (c) => {
    const longest = Math.max(...rows.map((r) => fmt(r.stats?.[c.id]).length), 2)
    return Math.max(Math.round(52 * f), Math.round(longest * numFs * 0.62 + 14 * f))
  }
  const widths = cols.map(colW)
  const bright = (id) => id === 'competitionPoints'
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: ground, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      {texture && <Paths layer="Grain" paths={grungePaths(width, height, 27)} color="#000000" width={width} height={height} opacity={0.25} />}
      <div data-layer="Title" style={{ position: 'absolute', left: 48, right: 48, top: g.top, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 20 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: Math.round(110 * f), lineHeight: 0.9 }}>{upper(pt(parts, 'dl21Title', 'LADDER'))}</div>
          <div style={{ fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 3, color: lit, marginTop: 8, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper(joinDot(s.grade, s.view !== 'Overall' ? s.view : '', s.round))}</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(90 * f)} shape="shield" />
      </div>
      {rows.length ? (
        <div data-layer="Table" style={{ position: 'absolute', left: 40, right: 40, top: top + Math.round(10 * f) }}>
          <div style={{ display: 'flex', alignItems: 'center', height: Math.round(36 * f), padding: `0 ${pad}px`, fontFamily: MONO, fontSize: Math.round(14 * f), letterSpacing: 2, opacity: 0.7 }}>
            <span style={{ width: Math.round(46 * f) }}>#</span>
            <span style={{ width: crestBox + Math.round(16 * f) }} />
            <span style={{ flex: 1 }}>TEAM</span>
            {cols.map((c, k) => <span key={c.id} style={{ width: widths[k], textAlign: 'right' }}>{upper(c.heading)}</span>)}
          </div>
          {rows.map((r, i) => {
            const ours = !!r.is_club
            const gap = i > 0 && rows[i - 1].rank != null && r.rank != null && r.rank - rows[i - 1].rank > 1
            const rowInk = ours ? inkOn(lit) : ink
            return (
              <div key={`${r.team_name}-${i}`} data-ladder-row={ours ? 'club' : ''} style={{
                display: 'flex', alignItems: 'center', height: rowH - 6, marginTop: gap ? 16 : 6, padding: `0 ${pad}px`, borderRadius: 4,
                background: ours ? lit : (i % 2 ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.09)'), color: rowInk, fontSize: fs,
              }}>
                <span style={{ width: Math.round(46 * f), fontVariantNumeric: 'tabular-nums' }}>{r.rank ?? ''}</span>
                <span data-ladder-crest="" style={{ width: crestBox, height: crestBox, marginRight: Math.round(16 * f), display: 'grid', placeItems: 'center', flexShrink: 0 }}>
                  <ClubLogo src={ours ? (team.logo || r.logo_url) : r.logo_url} monogram={ours ? (team.monogram || mono(r.team_name)) : mono(r.team_name)} color={rowInk} size={Math.round(crestBox * 0.92)} shape="shield" />
                </span>
                <span style={{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper(r.team_name)}</span>
                {cols.map((c, k) => (
                  <span key={c.id} style={{ width: widths[k], flexShrink: 0, textAlign: 'right', fontSize: numFs, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', opacity: bright(c.id) || ours ? 1 : 0.78 }}>{fmt(r.stats?.[c.id])}</span>
                ))}
              </div>
            )
          })}
        </div>
      ) : <Empty g={g} text={s.status === 'loading' ? 'READING THE LADDER…' : 'PICK A TEAM IN DATA TO PULL ITS LADDER'} />}
      <div data-layer="Source" style={{ position: 'absolute', left: 48, top: g.slotY - Math.round(34 * f), fontFamily: MONO, fontSize: Math.round(13 * f), letterSpacing: 2, opacity: 0.6 }}>{s.rows?.length ? 'LIVE LADDER · CRICKET AUSTRALIA' : ''}</div>
      <Credit g={g} ink={ink} />
    </LayerRoot>
  )
}
DesignLadder.displayName = 'DesignLadder'

// ── DL22 Head to Head ────────────────────────────────────────────────────────
const H2H_STATS = [
  { id: 'rank', label: 'POSITION', lowerWins: true },
  { id: 'played', label: 'PLAYED' },
  { id: 'won', label: 'WON' },
  { id: 'lost', label: 'LOST', lowerWins: true },
  { id: 'competitionPoints', label: 'POINTS' },
  { id: 'netRunRate', label: 'NET RUN RATE', signed: true },
  { id: 'quotient', label: 'QUOTIENT', signed: true },
]
// How long each side's bar is, 0 to 1. Counts (played, won, points) scale from
// zero; a rate that can go below zero, and a "fewer is better" figure, scale
// across the two values, so the better side is always the longer bar and no
// bar ever passes full length (a side on 0 losses drew one twice as long).
export function h2hShares(st, a, b) {
  const clamp = (v) => Math.max(0.06, Math.min(1, v))
  if (a === null && b === null) return [0, 0]
  if (st.lowerWins || st.signed) {
    if (a === null || b === null) return [a === null ? 0 : 1, b === null ? 0 : 1]
    if (a === b) return [1, 1]
    const lo = Math.min(a, b), hi = Math.max(a, b)
    const of = (v) => clamp(0.3 + 0.7 * (st.lowerWins ? (hi - v) : (v - lo)) / (hi - lo))
    return [of(a), of(b)]
  }
  const mag = Math.max(Math.abs(a ?? 0), Math.abs(b ?? 0))
  if (!mag) return [a === null ? 0 : 0.06, b === null ? 0 : 0.06]
  return [a === null ? 0 : clamp(Math.abs(a) / mag), b === null ? 0 : clamp(Math.abs(b) / mag)]
}
const statOf = (row, id) => (id === 'rank' ? row?.rank : row?.stats?.[id])
const num = (v) => (v === null || v === undefined || v === '' || Number.isNaN(Number(v)) ? null : Number(v))
export function HeadToHead({ width = 1080, height = 1080, team = {}, opponent = {}, match = {}, palette = {}, standings = {}, parts }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f, A } = g
  const ground = pc(parts, 'dl22Ground', '#101114')
  const usC = pc(parts, 'dl22Us', readable(palette.accent || '#ffc233', ground, '#ffffff'))
  const themC = pc(parts, 'dl22Them', '#9aa3b2')
  const ink = '#ffffff'
  const s = standings || {}
  const us = s.us
  const them = s.them
  const stats = H2H_STATS.filter((st) => num(statOf(us, st.id)) !== null || num(statOf(them, st.id)) !== null)
  const crest = Math.round(150 * f)
  const top = g.top + Math.round(330 * f)
  // Past meetings take the foot of the post when there are any; the ladder bars fill the rest.
  const past = s.past
  const pastH = hasPast(past) ? Math.round(Math.min(5, (past.recent || []).length) * 44 * f + 70 * f) : 0
  const pastY = g.slotY - 56 - pastH
  const avail = (pastH ? pastY - 16 : g.slotY - 70) - top
  const rowH = Math.min(Math.round(pick(A, { square: 96, portrait: 118, story: 150 }) * f), Math.floor(avail / Math.max(1, stats.length)))
  const numFs = Math.round(Math.min(36 * f, rowH * 0.5))
  // Room for the widest figure on each side, so the bars start in one line.
  const figW = Math.round(Math.max(2, ...stats.flatMap((st) => [fmt(statOf(us, st.id)).length, fmt(statOf(them, st.id)).length])) * numFs * 0.6 + 6)
  // Each side's column, less room for its figure, so a full bar never pushes the number off the post.
  const half = (width - 96 - Math.round(180 * f)) / 2 - figW - 24
  const usName = upper(us?.team_name || team.name)
  const themName = upper(them?.team_name || opponent.name || 'OPPONENT')
  // Match Info's opponent may be another club than the one picked off the
  // ladder: its crest is used only when the names share their first word.
  const first = (v) => String(v || '').trim().split(/\s+/)[0].toLowerCase()
  const sameOpp = !them || (opponent.name && first(opponent.name) === first(them.team_name))
  const themLogo = them?.logo_url || (sameOpp ? opponent.logo : null)
  const themMono = them ? mono(them.team_name) : (opponent.monogram || mono(themName))
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: ground, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      <div data-layer="Our side" style={{ position: 'absolute', inset: 0, background: `linear-gradient(90deg, ${usC}22, transparent 50%)` }} />
      <div data-layer="Their side" style={{ position: 'absolute', inset: 0, background: `linear-gradient(270deg, ${themC}22, transparent 50%)` }} />
      {texture && <Paths layer="Grain" paths={grungePaths(width, height, 44)} color="#000000" width={width} height={height} opacity={0.3} />}
      <div data-layer="Title" style={{ position: 'absolute', left: 48, right: 48, top: g.top, textAlign: 'center' }}>
        <div style={{ fontSize: Math.round(80 * f), lineHeight: 1, letterSpacing: 2 }}>{upper(pt(parts, 'dl22Title', 'HEAD TO HEAD'))}</div>
        <div style={{ fontFamily: MONO, fontSize: Math.round(17 * f), letterSpacing: 3, opacity: 0.75, marginTop: 6 }}>{upper(joinDot(s.grade, match.date, match.venue))}</div>
      </div>
      <div data-layer="Crests" style={{ position: 'absolute', left: 48, right: 48, top: g.top + Math.round(120 * f), display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center', gap: 20 }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center' }}><ClubLogo src={team.logo || us?.logo_url} monogram={team.monogram} color={usC} size={crest} shape="shield" /></div>
          <div style={{ fontSize: Math.round(30 * f), marginTop: 8, color: usC, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{usName}</div>
        </div>
        <div style={{ fontSize: Math.round(64 * f) }}>VS</div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center' }}><ClubLogo src={themLogo} monogram={themMono} color={themC} size={crest} shape="shield" /></div>
          <div style={{ fontSize: Math.round(30 * f), marginTop: 8, color: themC, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{themName}</div>
        </div>
      </div>
      {us && them && stats.length ? (
        <div data-layer="Comparison" style={{ position: 'absolute', left: 48, right: 48, top }}>
          {stats.map((st) => {
            const a = num(statOf(us, st.id))
            const b = num(statOf(them, st.id))
            const [shA, shB] = h2hShares(st, a, b)
            const aWins = a !== null && b !== null && (st.lowerWins ? a < b : a > b)
            const bWins = a !== null && b !== null && (st.lowerWins ? b < a : b > a)
            return (
              <div key={st.id} data-h2h-row={st.id} style={{ height: rowH, display: 'grid', gridTemplateColumns: `1fr ${Math.round(180 * f)}px 1fr`, alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 12 }}>
                  <span data-h2h-fig="us" style={{ fontSize: numFs, color: aWins ? usC : ink, width: figW, textAlign: 'right', flexShrink: 0, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{fmt(statOf(us, st.id))}</span>
                  <span data-h2h-bar="us" style={{ width: Math.round(half * shA), height: Math.round(Math.min(rowH * 0.28, 30 * f)), background: usC, opacity: aWins ? 1 : 0.45, borderRadius: 3, flexShrink: 0 }} />
                </div>
                <div style={{ textAlign: 'center', fontFamily: MONO, fontSize: Math.round(14 * f), letterSpacing: 2, opacity: 0.8 }}>{st.label}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span data-h2h-bar="them" style={{ width: Math.round(half * shB), height: Math.round(Math.min(rowH * 0.28, 30 * f)), background: themC, opacity: bWins ? 1 : 0.45, borderRadius: 3, flexShrink: 0 }} />
                  <span data-h2h-fig="them" style={{ fontSize: numFs, color: bWins ? themC : ink, width: figW, flexShrink: 0, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{fmt(statOf(them, st.id))}</span>
                </div>
              </div>
            )
          })}
        </div>
      ) : (!pastH && <Empty g={{ ...g, top: g.top + 120 * f }} text={s.status === 'loading' ? 'READING THE LADDER…' : !us ? 'PICK A TEAM IN DATA' : 'PICK THE OPPONENT FROM THE LADDER IN DATA'} />)}
      {pastH > 0 && <PastBlock past={past} x={48} y={pastY} w={width - 96} h={pastH} f={f} color={ink} usC={usC} rows={5} />}
      <div data-layer="Source" style={{ position: 'absolute', left: 48, right: 48, top: g.slotY - Math.round(40 * f), textAlign: 'center', fontFamily: MONO, fontSize: Math.round(13 * f), letterSpacing: 2, opacity: 0.6 }}>{[us && them ? 'LADDER: CRICKET AUSTRALIA' : '', pastH ? 'PAST MEETINGS: YOUR CLUB\'S RESULTS' : ''].filter(Boolean).join(' · ')}</div>
      <Credit g={g} ink={ink} />
    </LayerRoot>
  )
}
HeadToHead.displayName = 'HeadToHead'

// ── DL23 Stat Leaders ────────────────────────────────────────────────────────
export function StatLeaders({ width = 1080, height = 1080, team = {}, palette = {}, standings = {}, parts }) {
  const g = geo(width, height)
  const { f, A } = g
  const ground = pc(parts, 'dl23Ground', palette.primary || '#0b1530')
  const lit = pc(parts, 'dl23Lit', readable(palette.accent || '#ffc233', ground, '#ffffff'))
  const ink = '#ffffff'
  const resolve = resolver(palette)
  const L = (standings || {}).leaders || {}
  const rows = (L.rows || []).slice(0, pick(A, { square: 5, portrait: 6, story: 7 }))
  const [lead, ...rest] = rows
  const heroTop = g.top + Math.round(150 * f)
  const rowH = Math.round(pick(A, { square: 78, portrait: 86, story: 100 }) * f)
  const restH = rest.length * rowH
  const valFs = Math.round(pick(A, { square: 44, portrait: 46, story: 52 }) * f)
  const nameFs = Math.round(pick(A, { square: 36, portrait: 38, story: 42 }) * f)
  const subFs = Math.round(14 * f)
  const valW = Math.round(Math.max(2, ...rest.map((r) => String(r.value).length)) * valFs * 0.6 + 8)
  const subW = rest.some((r) => r.sub) ? Math.min(Math.round(width * 0.36), Math.round(Math.max(...rest.map((r) => String(r.sub || '').length)) * subFs * 0.66 + 8)) : 0
  const restY = g.slotY - 20 - restH
  const heroH = restY - 20 - heroTop
  const dots = halftoneDots(width, height, Math.round(20 * f))
  return (
    <LayerRoot style={{ width, height, position: 'relative', overflow: 'hidden', background: ground, color: ink, fontFamily: FONT, fontWeight: WEIGHT }}>
      <svg data-layer="Halftone" width={width} height={height} style={{ position: 'absolute', inset: 0, opacity: 0.06 }}><g fill={ink}>{dots.map(([x, y, r], i) => <circle key={i} cx={x} cy={y} r={r} />)}</g></svg>
      <div data-layer="Title" style={{ position: 'absolute', left: 48, right: 48, top: g.top, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 20 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: Math.round(96 * f), lineHeight: 0.92 }}>{upper(pt(parts, 'dl23Title', L.title || 'STAT LEADERS'))}</div>
          <div style={{ fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 3, color: lit, marginTop: 8, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper(L.scope || '')}</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(84 * f)} shape="shield" />
      </div>
      {lead ? (
        <>
          <div data-layer="Leader" style={{ position: 'absolute', left: 48, right: 48, top: heroTop, height: heroH }}>
            {lead.photo && (
              <div style={{ position: 'absolute', right: -20, top: 0, width: Math.round(width * 0.55), height: heroH }}>
                <FramedImage item={{ w: Math.round(width * 0.55), h: heroH, fit: 'contain', objPos: 'center bottom', fx: { outline: { width: Math.round(5 * f), color: 'white' } } }} src={lead.photo} resolve={resolve} />
              </div>
            )}
            <div style={{ position: 'absolute', left: 0, bottom: 10, width: lead.photo ? '55%' : '100%' }}>
              <div style={{ fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 3, color: lit }}>#1</div>
              <div style={{ fontSize: Math.round(Math.min(260 * f, heroH * 0.6)), lineHeight: 0.9, color: lit, letterSpacing: -4 }}>{lead.value}</div>
              <div style={{ fontFamily: MONO, fontSize: Math.round(18 * f), letterSpacing: 3, opacity: 0.85 }}>{upper(L.unit)}</div>
              <AutoFitText text={upper(lead.name)} max={Math.round(64 * f)} min={24} lines={1} measureDeps={[lead.name, width]} style={{ lineHeight: 1.05, marginTop: 8 }} />
              {lead.sub && <div style={{ fontFamily: MONO, fontSize: Math.round(16 * f), letterSpacing: 2, opacity: 0.75, marginTop: 4 }}>{upper(lead.sub)}</div>}
            </div>
          </div>
          <div data-layer="Others" style={{ position: 'absolute', left: 48, right: 48, top: restY }}>
            {rest.map((r, i) => (
              <div key={`${r.name}-${i}`} data-leader-row="" style={{ height: rowH, display: 'flex', alignItems: 'center', gap: 18, borderTop: `1px solid ${ink}26` }}>
                <span style={{ fontFamily: MONO, fontSize: Math.round(18 * f), width: Math.round(40 * f), opacity: 0.7, flexShrink: 0 }}>{i + 2}</span>
                <span style={{ flex: 1, minWidth: 0, fontSize: nameFs, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper(r.name)}</span>
                {subW > 0 && <span data-leader-sub="" style={{ fontFamily: MONO, fontSize: subFs, letterSpacing: 1, opacity: 0.7, width: subW, flexShrink: 0, textAlign: 'right', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper(r.sub || '')}</span>}
                <span data-leader-value="" style={{ fontSize: valFs, color: lit, width: valW, flexShrink: 0, textAlign: 'right', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{r.value}</span>
              </div>
            ))}
          </div>
        </>
      ) : <Empty g={g} text={L.status === 'loading' ? 'READING THE LEADERBOARD…' : L.status === 'error' ? 'THE LEADERBOARD COULD NOT BE READ' : 'NO FIGURES FOR THIS CHOICE YET'} />}
      <Credit g={g} ink={ink} />
    </LayerRoot>
  )
}
StatLeaders.displayName = 'StatLeaders'

registerParts({
  DL21: [textPart('dl21Title', 'Title', 'Title', () => 'LADDER'), colorPart('dl21Lit', 'Our row', 'Table', (p) => p.accent || '#ffc233'), colorPart('dl21Ground', 'Background', 'Background', (p) => p.primary || '#0b1530')],
  DL22: [textPart('dl22Title', 'Title', 'Title', () => 'HEAD TO HEAD'), colorPart('dl22Us', 'Our colour', 'Sides', (p) => p.accent || '#ffc233'), colorPart('dl22Them', 'Their colour', 'Sides', () => '#9aa3b2'), colorPart('dl22Ground', 'Background', 'Background', () => '#101114')],
  DL23: [textPart('dl23Title', 'Title (blank uses the stat)', 'Title', () => ''), colorPart('dl23Lit', 'Figures', 'Colours', (p) => p.accent || '#ffc233'), colorPart('dl23Ground', 'Background', 'Colours', (p) => p.primary || '#0b1530')],
})

export const SPONSOR_SLOTS = { DL21: slotOf, DL22: slotOf, DL23: slotOf }
