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
const mono = (name) => String(name || '').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()

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
  const avail = g.slotY - 20 - top - Math.round(46 * f)
  const max = pick(A, { square: 10, portrait: 12, story: 14 })
  const rows = ladderRowsShown(s.rows, max)
  const rowH = Math.min(Math.round(78 * f), Math.floor(avail / Math.max(1, rows.length)))
  const colW = Math.round(92 * f)
  const fs = Math.round(Math.min(34 * f, rowH * 0.46))
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
        <div data-layer="Table" style={{ position: 'absolute', left: 40, right: 40, top }}>
          <div style={{ display: 'flex', alignItems: 'center', height: Math.round(40 * f), fontFamily: MONO, fontSize: Math.round(15 * f), letterSpacing: 2, opacity: 0.75 }}>
            <span style={{ width: Math.round(64 * f) }}>#</span>
            <span style={{ flex: 1 }}>TEAM</span>
            {cols.map((c) => <span key={c.id} style={{ width: colW, textAlign: 'right' }}>{upper(c.heading)}</span>)}
          </div>
          {rows.map((r, i) => {
            const ours = !!r.is_club
            const gap = i > 0 && rows[i - 1].rank != null && r.rank != null && r.rank - rows[i - 1].rank > 1
            return (
              <div key={`${r.team_name}-${i}`} data-ladder-row={ours ? 'club' : ''} style={{
                display: 'flex', alignItems: 'center', height: rowH - 6, marginTop: gap ? 14 : 6, padding: `0 ${Math.round(14 * f)}px`,
                background: ours ? lit : 'rgba(255,255,255,0.07)', color: ours ? inkOn(lit) : ink, fontSize: fs,
                clipPath: 'polygon(0 0, 100% 0, calc(100% - 14px) 100%, 0 100%)',
              }}>
                <span style={{ width: Math.round(50 * f) }}>{r.rank ?? ''}</span>
                <span style={{ width: Math.round(rowH * 0.7), height: Math.round(rowH * 0.7), marginRight: 14, display: 'grid', placeItems: 'center' }}>
                  <ClubLogo src={r.logo_url} monogram={mono(r.team_name)} color={ours ? inkOn(lit) : ink} size={Math.round(rowH * 0.62)} shape="shield" />
                </span>
                <span style={{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper(r.team_name)}</span>
                {cols.map((c) => <span key={c.id} style={{ width: colW, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{fmt(r.stats?.[c.id])}</span>)}
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
  { id: 'netRunRate', label: 'NET RUN RATE' },
  { id: 'quotient', label: 'QUOTIENT' },
]
const statOf = (row, id) => (id === 'rank' ? row?.rank : row?.stats?.[id])
const num = (v) => (v === null || v === undefined || v === '' || Number.isNaN(Number(v)) ? null : Number(v))
export function HeadToHead({ width = 1080, height = 1080, team = {}, opponent = {}, match = {}, palette = {}, standings = {}, parts }) {
  const texture = usePostLook().texture !== false
  const g = geo(width, height)
  const { f } = g
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
  const rowH = Math.min(Math.round(100 * f), Math.floor(avail / Math.max(1, stats.length)))
  // Each side's column, less room for its figure, so a full bar never pushes the number off the post.
  const half = (width - 96 - Math.round(180 * f)) / 2 - Math.round(110 * f)
  const usName = upper(us?.team_name || team.name)
  const themName = upper(them?.team_name || opponent.name || 'OPPONENT')
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
          <div style={{ display: 'flex', justifyContent: 'center' }}><ClubLogo src={us?.logo_url || team.logo} monogram={team.monogram} color={usC} size={crest} shape="shield" /></div>
          <div style={{ fontSize: Math.round(30 * f), marginTop: 8, color: usC, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{usName}</div>
        </div>
        <div style={{ fontSize: Math.round(64 * f) }}>VS</div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center' }}><ClubLogo src={them?.logo_url || opponent.logo} monogram={opponent.monogram || mono(themName)} color={themC} size={crest} shape="shield" /></div>
          <div style={{ fontSize: Math.round(30 * f), marginTop: 8, color: themC, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{themName}</div>
        </div>
      </div>
      {us && them && stats.length ? (
        <div data-layer="Comparison" style={{ position: 'absolute', left: 48, right: 48, top }}>
          {stats.map((st) => {
            const a = num(statOf(us, st.id))
            const b = num(statOf(them, st.id))
            const mag = Math.max(Math.abs(a ?? 0), Math.abs(b ?? 0)) || 1
            // Position: the smaller number is the better place, so the bar is flipped.
            const share = (v) => (v === null ? 0 : st.lowerWins ? (mag - v + 1) / mag : Math.max(0.04, Math.abs(v) / mag))
            const aWins = a !== null && b !== null && (st.lowerWins ? a < b : a > b)
            const bWins = a !== null && b !== null && (st.lowerWins ? b < a : b > a)
            return (
              <div key={st.id} data-h2h-row={st.id} style={{ height: rowH, display: 'grid', gridTemplateColumns: `1fr ${Math.round(180 * f)}px 1fr`, alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 12 }}>
                  <span style={{ fontSize: Math.round(36 * f), color: aWins ? usC : ink }}>{fmt(statOf(us, st.id))}</span>
                  <span style={{ width: Math.round(half * share(a)), height: Math.round(rowH * 0.28), background: usC, opacity: aWins ? 1 : 0.45 }} />
                </div>
                <div style={{ textAlign: 'center', fontFamily: MONO, fontSize: Math.round(14 * f), letterSpacing: 2, opacity: 0.8 }}>{st.label}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{ width: Math.round(half * share(b)), height: Math.round(rowH * 0.28), background: themC, opacity: bWins ? 1 : 0.45 }} />
                  <span style={{ fontSize: Math.round(36 * f), color: bWins ? themC : ink }}>{fmt(statOf(them, st.id))}</span>
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
  const restH = rest.length * Math.round(78 * f)
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
              <div key={`${r.name}-${i}`} data-leader-row="" style={{ height: Math.round(78 * f), display: 'flex', alignItems: 'center', gap: 18, borderTop: `1px solid ${ink}26` }}>
                <span style={{ fontFamily: MONO, fontSize: Math.round(18 * f), width: Math.round(40 * f), opacity: 0.7 }}>{i + 2}</span>
                <span style={{ flex: 1, minWidth: 0, fontSize: Math.round(36 * f), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{upper(r.name)}</span>
                {r.sub && <span style={{ fontFamily: MONO, fontSize: Math.round(14 * f), letterSpacing: 1, opacity: 0.7 }}>{upper(r.sub)}</span>}
                <span style={{ fontSize: Math.round(44 * f), color: lit, width: Math.round(130 * f), textAlign: 'right' }}>{r.value}</span>
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
