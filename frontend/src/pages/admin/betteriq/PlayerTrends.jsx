/* BetterIQ — Player trends (v2 design).
   Form movers surfaced first (rising/sliding bat & bowl with Delta) + emerging
   players, then a player deep-dive with tabs:
     • Trajectory — AreaChart of runs/season + table, range-aware delta (dims
       out-of-range seasons when a season RANGE is active).
     • Deep dive — player Radar + reliability percentiles, conversion,
       milestones, selection value, similar players (+ the bowling deep dive).
     • Compare — pick two players → one overlaid Radar + a head-to-head career
       stat table, the stronger value highlighted per row.
   Reads the GLOBAL Season + Team filter (useIQFilter); all data is real
   (api.iqTrends*). ?player=<id> deep-links a player. Averages 2dp via a2(). */
import { useState, useEffect, useMemo, useRef } from 'react'
import Dropdown from '../../../components/Dropdown'
import { useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import {
  Sparkline,
  Card, Stat, Note, Tag, Btn, Segmented, Search, Empty, surname,
  Tabs, PageIntro, Delta, Initials, KV, a2, LoadingBar, LoadingCard,
  fmtCount, fmtPct, runsPhrase, wktsPhrase,
} from './ui'
import { Radar, AreaChart } from './viz'
import { DeepDiveTab } from './PlayerDeepDive'
import { useIQFilter, seasonsInRange, effectiveSeasonId } from './Context'
import { formatSeason } from '../../../lib/cricketFormat'
import { api } from '../../../lib/api'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)
const ACCENT = 'var(--pb-accent)'
const AMBER = 'var(--iq-c-amber)'

/* ── Form movers ─────────────────────────────────────────────────────────── */
function MoverList({ title, tone, items, kind, onPick }) {
  const color = tone === 'up' ? 'var(--pb-brand)' : 'var(--pb-red)'
  return (
    <div>
      <div className="iq-eyebrow mb-2.5" style={{ color }}>{title}</div>
      <div className="space-y-2">
        {(items || []).map((p) => {
          const delta = Number(p.latest) - Number(p.baseline)
          // For bowling, lower is better → invert the sign the Delta colours by.
          const dVal = kind === 'bowl' ? -delta : delta
          return (
            <button key={p.player_id} onClick={() => onPick(p.player_id)}
              className="w-full flex items-center justify-between gap-2 text-left transition-colors hover:text-pb-accent">
              <span className="font-medium text-[13.5px] truncate">{p.name}</span>
              <span className="flex items-center gap-2 shrink-0">
                <span className="iq-num text-pb-faint text-[12px] whitespace-nowrap">{a2(p.baseline)}→{a2(p.latest)}</span>
                <Delta value={dVal} decimals={2} />
              </span>
            </button>
          )
        })}
        {!items?.length && <Empty>—</Empty>}
      </div>
    </div>
  )
}

/* ── Current-season player picker (searchable, opens on focus) ───────────── */
function PlayerSearch({ players, onPick, placeholder = 'Search a player…' }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const t = q.trim().toLowerCase()
  const matches = (t ? players.filter(p => (p.name || '').toLowerCase().includes(t)) : players).slice(0, 30)
  return (
    <div ref={ref} className="relative" onFocusCapture={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}>
      <Search value={q} onChange={(v) => { setQ(v); setOpen(true) }} placeholder={placeholder} className="w-full" />
      <Dropdown
        anchorRef={ref}
        open={open}
        onClose={() => setOpen(false)}
        maxHeight={320}
        className="iq-card p-1.5 iq-scroll"
        style={{ boxShadow: 'var(--iq-card-shadow)' }}
      >
        {matches.length === 0 ? (
          <div className="px-2.5 py-2 text-pb-faint text-sm">{players.length === 0 ? 'No current-season players found.' : 'No match.'}</div>
        ) : matches.map(p => (
          <button key={p.player_id} type="button" onClick={() => { onPick(p.player_id); setQ(''); setOpen(false) }}
            className="w-full flex flex-col gap-0.5 px-2.5 py-2 text-left transition overflow-hidden" style={{ borderRadius: 8 }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--pb-surface2)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
            <span className="font-medium text-[13.5px] truncate w-full">{p.name}</span>
            <span className="iq-mono text-pb-faintest text-[11px] truncate w-full">
              {p.matches} {p.matches === 1 ? 'game' : 'games'}{p.runs ? ` · ${runsPhrase(p.runs, p.bat_avg)}` : ''}{p.wickets ? ` · ${wktsPhrase(p.wickets, p.bowl_avg)}` : ''}
            </span>
          </button>
        ))}
      </Dropdown>
    </div>
  )
}

/* ── Trend summary (header + season / career snapshot) ───────────────────── */
function VerdictTags({ verdict }) {
  if (!verdict) return null
  const map = { rising: ['Rising', 'win'], declining: ['Declining', 'red'], steady: ['Steady', 'faint'] }
  const out = []
  if (verdict.batting && map[verdict.batting]) out.push(['bat', ...map[verdict.batting]])
  if (verdict.bowling && map[verdict.bowling]) out.push(['bowl', ...map[verdict.bowling]])
  if (!out.length) return null
  return (
    <span className="flex items-center gap-1.5">
      {out.map(([k, label, tone]) => <Tag key={k} tone={tone}>{k === 'bowl' ? 'Bowl ' : 'Bat '}{label}</Tag>)}
    </span>
  )
}

function TrendSummary({ detail }) {
  const b = detail.career?.batting || {}
  const recentBat = (detail.recent_form?.batting || [])
  const form5 = recentBat.map(x => x.runs)
  const formTxt = recentBat.map(x => (x.not_out ? `${x.runs}*` : x.runs)).join('  ')
  const peakBat = detail.peak?.batting
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-4">
        <Initials name={detail.player?.name} size={56} tone="accent" />
        <div>
          <h2 className="iq-headline" style={{ fontSize: 30 }}>{detail.player?.name}</h2>
          <div className="flex items-center gap-2 mt-1.5">
            <VerdictTags verdict={detail.verdict} />
            {detail.consistency != null && <span className="text-pb-faint text-[12.5px] whitespace-nowrap">Consistency ±{detail.consistency}</span>}
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2 items-start">
        <Card eyebrow="career to date" title="Career">
          <div className="grid grid-cols-3 gap-y-4 gap-x-3">
            <Stat label="Runs" value={num(b.total_runs, 0)} />
            <Stat label="Average" value={a2(b.average)} count={false} />
            <Stat label="100s / 50s" value={`${num(b.hundreds, 0)}/${num(b.fifties, 0)}`} />
            <Stat label="Wickets" value={num(detail.career?.bowling?.total_wickets, 0)} />
            <Stat label="Bowl avg" value={a2(detail.career?.bowling?.average)} count={false} />
            <Stat label="Catches" value={num(detail.career?.fielding?.total_catches_non_wk, 0)} />
            {num(detail.career?.fielding?.total_catches_wk, 0) > 0 && (
              <Stat label="Ct (wk)" value={num(detail.career?.fielding?.total_catches_wk, 0)} />
            )}
          </div>
        </Card>
        <Card eyebrow="recent form" title="Form & peak">
          <div className="px-3 pt-3 pb-2" style={{ background: 'var(--pb-surface2)', borderRadius: 12 }}>
            <div className="flex items-center justify-between mb-1">
              <span className="iq-eyebrow" style={{ fontSize: 9 }}>Last innings</span>
              <span className="iq-mono text-pb-faint" style={{ fontSize: 10.5 }}>{formTxt || '—'}</span>
            </div>
            {form5.length >= 2 ? <Sparkline key={detail.player?.name} values={form5} h={50} dots />
              : <div className="text-pb-faintest text-[11px] py-3">Not enough recent innings.</div>}
          </div>
          <div className="mt-4 space-y-0.5">
            {peakBat && <KV label="Best batting season" value={`${peakBat.season} · ${runsPhrase(peakBat.runs, peakBat.average)}`} />}
            {detail.peak?.bowling && <KV label="Best bowling season" value={`${detail.peak.bowling.season} · ${wktsPhrase(detail.peak.bowling.wickets, detail.peak.bowling.average)}`} />}
            {!peakBat && !detail.peak?.bowling && <Empty>Not enough history yet.</Empty>}
          </div>
        </Card>
      </div>
    </div>
  )
}

/* ── Tab: Trajectory (range-aware) ───────────────────────────────────────── */
function TrajectoryTab({ detail, ctx, seasons }) {
  const rows = detail.seasons || []
  const isRange = ctx?.season?.mode === 'range'
  // In-range season labels (matched against the detail rows by label/year/name).
  // Computed unconditionally (before any early return) to keep hook order stable.
  const inRangeKeys = useMemo(() => {
    if (!isRange) return null
    const set = new Set()
    for (const s of seasonsInRange(ctx, seasons)) {
      if (s.label) set.add(String(s.label))
      if (s.year != null) set.add(String(s.year))
      if (s.name) set.add(String(s.name))
    }
    return set
  }, [isRange, ctx, seasons])

  if (!rows.length) return <Empty>No season data.</Empty>

  const inRange = (s) => {
    if (!isRange || !inRangeKeys) return true
    const n = String(s.season_name || '')
    if (inRangeKeys.has(n)) return true
    // match on the short "24/25" tail or the 4-digit start year embedded in the name
    const tail = n.match(/(\d{2})\s*[/\-]\s*(\d{2})\b/)
    if (tail && inRangeKeys.has(`${tail[1]}/${tail[2]}`)) return true
    const yr = n.match(/(\d{4})/)
    if (yr && inRangeKeys.has(yr[1])) return true
    return false
  }

  const spanRows = rows.filter(inRange)
  const dRuns = spanRows.length > 1 ? (spanRows[spanRows.length - 1].total_runs || 0) - (spanRows[0].total_runs || 0) : 0
  const dAvg = spanRows.length > 1 ? (Number(spanRows[spanRows.length - 1].batting_average) || 0) - (Number(spanRows[0].batting_average) || 0) : 0

  return (
    <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr] items-start">
      <Card eyebrow="runs per season" title="Trajectory" right={isRange ? <Delta value={dRuns} suffix=" runs" /> : null}>
        <AreaChart points={rows.map(s => s.total_runs || 0)} labels={rows.map(s => formatSeason(s.season_name))} h={190} />
        {isRange
          ? <Note>Over the selected range: <b style={{ color: 'var(--pb-text)' }}>{dRuns >= 0 ? '+' : ''}{fmtCount(dRuns)} runs</b> and <b style={{ color: 'var(--pb-text)' }}>{dAvg >= 0 ? '+' : ''}{a2(dAvg)} average</b> across {spanRows.length} season{spanRows.length === 1 ? '' : 's'}.</Note>
          : <Note>Runs scored each season, oldest → newest. Switch the season filter to <b style={{ color: 'var(--pb-text)' }}>Compare</b> for a range delta.</Note>}
      </Card>
      <Card eyebrow="the numbers" title="Season by season">
        <div className="overflow-x-auto -mx-1 iq-scroll">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="iq-eyebrow text-left" style={{ fontSize: 9 }}>
                <th className="py-2 px-1 font-medium">Season</th>
                <th className="py-2 px-1 font-medium text-right">M</th>
                <th className="py-2 px-1 font-medium text-right">Runs</th>
                <th className="py-2 px-1 font-medium text-right">Avg</th>
                <th className="py-2 px-1 font-medium text-right">Wkts</th>
                <th className="py-2 px-1 font-medium text-right">Avg</th>
                <th className="py-2 px-1 font-medium text-right">Econ</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s, i) => {
                const on = inRange(s)
                return (
                  <tr key={i} style={{ borderTop: '1px solid var(--pb-hairline)', opacity: on ? 1 : 0.4 }}>
                    <td className="py-2 px-1 iq-mono text-pb-dim whitespace-nowrap">
                      <span className="inline-flex items-center gap-2">{formatSeason(s.season_name)}{on && isRange && <span style={{ width: 6, height: 6, borderRadius: 99, background: ACCENT }} />}</span>
                    </td>
                    <td className="py-2 px-1 text-right iq-num text-pb-faint">{fmtCount(s.matches)}</td>
                    <td className="py-2 px-1 text-right iq-num font-semibold">{fmtCount(s.total_runs)}</td>
                    <td className="py-2 px-1 text-right iq-num">{a2(s.batting_average)}</td>
                    <td className="py-2 px-1 text-right iq-num font-semibold">{fmtCount(s.total_wickets)}</td>
                    <td className="py-2 px-1 text-right iq-num">{a2(s.bowling_average)}</td>
                    <td className="py-2 px-1 text-right iq-num text-pb-faint">{a2(s.economy)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

/* DeepDiveTab + its cards now live in ./PlayerDeepDive (imported above), shared
   with the Player search page. */

/* ── Tab: Compare ────────────────────────────────────────────────────────── */
function radarSeries(payload, kind) {
  const r = payload?.[kind]
  if (!r || !Array.isArray(r.values) || !r.values.length) return null
  return r
}

function careerRows(A, B) {
  const ab = A?.career?.batting || {}, bb = B?.career?.batting || {}
  const abo = A?.career?.bowling || {}, bbo = B?.career?.bowling || {}
  // cmp: which side is "stronger" — null when equal/incomparable. lower=true for bowling avg.
  const cmp = (x, y, lower = false) => {
    const nx = Number(x), ny = Number(y)
    if (!isFinite(nx) || !isFinite(ny) || nx === ny) return null
    if (lower) return nx < ny ? 'a' : 'b'
    return nx > ny ? 'a' : 'b'
  }
  return [
    { label: 'Runs', a: fmtCount(ab.total_runs ?? 0), b: fmtCount(bb.total_runs ?? 0), better: cmp(ab.total_runs, bb.total_runs) },
    { label: 'Bat avg', a: a2(ab.average), b: a2(bb.average), better: cmp(ab.average, bb.average) },
    { label: '100s / 50s', a: `${num(ab.hundreds, 0)}/${num(ab.fifties, 0)}`, b: `${num(bb.hundreds, 0)}/${num(bb.fifties, 0)}`, better: cmp(ab.hundreds, bb.hundreds) },
    { label: 'Wickets', a: fmtCount(abo.total_wickets ?? 0), b: fmtCount(bbo.total_wickets ?? 0), better: cmp(abo.total_wickets, bbo.total_wickets) },
    { label: 'Bowl avg', a: a2(abo.average), b: a2(bbo.average), better: cmp(abo.average, bbo.average, true) },
  ]
}

function CompareRow({ label, a, b, better }) {
  const c = (s) => (better === s ? 'var(--pb-brand)' : 'var(--pb-text)')
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 py-2.5" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
      <div className="iq-num font-semibold text-right text-[15px]" style={{ color: c('a') }}>{a}</div>
      <div className="iq-eyebrow text-center" style={{ fontSize: 9, minWidth: 92 }}>{label}</div>
      <div className="iq-num font-semibold text-[15px]" style={{ color: c('b') }}>{b}</div>
    </div>
  )
}

function CompareTab({ aId, players, detailA }) {
  const [bId, setBId] = useState(null)
  const [radarA, setRadarA] = useState(null)
  const [radarB, setRadarB] = useState(null)
  const [detailB, setDetailB] = useState(null)

  // Default the opponent to the first picker player that isn't player A.
  useEffect(() => {
    if (bId || !players.length) return
    const first = players.find(p => p.player_id !== aId) || players[0]
    if (first) setBId(first.player_id)
  }, [players, aId, bId])

  useEffect(() => {
    let alive = true
    setRadarA(null)
    api.iqPlayerRadar(aId).then(d => { if (alive) setRadarA(d) }).catch(() => { if (alive) setRadarA(null) })
    return () => { alive = false }
  }, [aId])

  useEffect(() => {
    if (!bId) { setRadarB(null); setDetailB(null); return }
    let alive = true
    setRadarB(null); setDetailB(null)
    api.iqPlayerRadar(bId).then(d => { if (alive) setRadarB(d) }).catch(() => { if (alive) setRadarB(null) })
    api.iqTrendsPlayer(bId).then(d => { if (alive) setDetailB(d) }).catch(() => { if (alive) setDetailB(null) })
    return () => { alive = false }
  }, [bId])

  const nameA = detailA?.player?.name || surname(players.find(p => p.player_id === aId)?.name || '')
  const nameB = detailB?.player?.name || surname(players.find(p => p.player_id === bId)?.name || '')
  const ra = radarSeries(radarA, 'bat')
  const rb = radarSeries(radarB, 'bat')
  const rows = useMemo(() => careerRows(detailA, detailB), [detailA, detailB])

  return (
    <Card eyebrow="head to head" title="Compare players">
      <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-3 mb-5">
        <span className="iq-display font-semibold text-[14px] inline-flex items-center gap-2" style={{ color: ACCENT }}>
          <span style={{ width: 11, height: 11, borderRadius: 99, background: ACCENT }} />{nameA}
        </span>
        <span className="iq-mono text-pb-faint text-[12px]">vs</span>
        <div className="min-w-[220px]">
          <PlayerSearch players={players.filter(p => p.player_id !== aId)} onPick={setBId} placeholder="Pick a player to compare…" />
        </div>
      </div>

      {!bId ? (
        <Empty>Pick a second player to compare.</Empty>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[auto_1fr] items-center">
          <div className="flex flex-col items-center">
            {ra && rb
              ? <Radar key={aId + bId} axes={ra.axes} values={ra.values} compareValues={rb.values} compareColor={AMBER} size={260} />
              : (radarA === null || radarB === null)
                ? <div className="py-16 w-[260px]"><LoadingBar label="Loading radar…" expectedMs={5000} /></div>
                : <div className="text-pb-faint text-sm py-16 w-[260px] text-center">No batting radar to overlay for this pair.</div>}
            <div className="flex items-center gap-4 mt-2 text-[11.5px]">
              <span className="inline-flex items-center gap-1.5"><span style={{ width: 14, height: 3, background: ACCENT, borderRadius: 2 }} />{surname(nameA)}</span>
              <span className="inline-flex items-center gap-1.5"><span style={{ width: 14, height: 3, background: AMBER, borderRadius: 2 }} />{surname(nameB)}</span>
            </div>
          </div>
          <div>
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 pb-1">
              <div className="text-right font-bold iq-display truncate" style={{ color: ACCENT }}>{surname(nameA)}</div>
              <div style={{ minWidth: 92 }} />
              <div className="font-bold iq-display truncate" style={{ color: AMBER }}>{surname(nameB)}</div>
            </div>
            {detailB === null ? <div className="py-6"><LoadingBar label="Loading stats…" expectedMs={4500} /></div>
              : rows.map(r => <CompareRow key={r.label} {...r} />)}
          </div>
        </div>
      )}
      <Note>Greener career figure is the stronger of the two. Radar axes are normalised against the squad average.</Note>
    </Card>
  )
}

/* ── Player detail (tabbed) ──────────────────────────────────────────────── */
function PlayerDetail({ playerId, players, ctx, seasons, onClear }) {
  const [detail, setDetail] = useState(null)
  const [deep, setDeep] = useState(null)
  const [bdeep, setBdeep] = useState(null)
  const [radar, setRadar] = useState(null)
  const [radarLoading, setRadarLoading] = useState(false)
  const [scouting, setScouting] = useState(null)
  const [tab, setTab] = useState('trajectory')

  // Career radar (career = omit season) unless a single season is active.
  const seasonId = ctx?.season?.mode === 'single' ? (ctx?.season?.to?.id || undefined) : undefined

  // The per-player cards follow the same filter the header shows — they used to
  // be all-career while the sticky bar overhead read "2024/25 · A Grade", so one
  // screen showed four different scopes. The payload's `scope` badges the rest.
  const detailGrade = ctx?.team?.id || undefined
  useEffect(() => {
    if (!playerId) return
    let alive = true
    setDetail(null); setDeep(null); setBdeep(null); setScouting(null)
    api.iqTrendsPlayer(playerId, seasonId, detailGrade).then(d => { if (alive) setDetail(d) }).catch(() => { if (alive) setDetail({ error: true }) })
    api.iqPlayerDeepDive(playerId, seasonId, detailGrade).then(d => { if (alive) setDeep(d) }).catch(() => { if (alive) setDeep(null) })
    api.iqBowlerDeepDive(playerId, seasonId, detailGrade).then(d => { if (alive) setBdeep(d) }).catch(() => { if (alive) setBdeep(null) })
    api.iqPlayerScouting(playerId).then(d => { if (alive) setScouting(d) }).catch(() => { if (alive) setScouting(null) })
    return () => { alive = false }
  }, [playerId, seasonId, detailGrade])

  const saveScouting = async (body) => {
    const saved = await api.iqSavePlayerScouting(playerId, body)
    setScouting(saved)
    return saved
  }

  useEffect(() => {
    if (!playerId) return
    let alive = true
    setRadar(null); setRadarLoading(true)
    api.iqPlayerRadar(playerId, seasonId)
      .then(d => { if (alive) setRadar(d) })
      .catch(() => { if (alive) setRadar(null) })
      .finally(() => { if (alive) setRadarLoading(false) })
    return () => { alive = false }
  }, [playerId, seasonId])

  if (detail === null) return <LoadingCard label="Loading trajectory…" expectedMs={5000} />
  if (detail?.error) return <div className="iq-card p-6"><Empty>Couldn't load this player.</Empty></div>

  return (
    <div className="iq-fade space-y-6">
      {/* What scope the cards below were actually built from (career vs the
          filtered season/grade) — stated, not implied by the header. */}
      {(detail?.scope || deep?.scope) && (
        <div className="flex items-center gap-2 -mb-2">
          <Tag>{(deep?.scope?.label || detail?.scope?.label) === 'filtered'
            ? 'Scoped to your filter'
            : 'Career · all grades'}</Tag>
          {detail?.auto_shown && <Tag tone="accent">Includes grades this player has actually played</Tag>}
        </div>
      )}
      <TrendSummary detail={detail} />

      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'trajectory', label: 'Trajectory' },
        { value: 'deep', label: 'Deep dive' },
        { value: 'compare', label: 'Compare' },
      ]} />

      {tab === 'trajectory' && <TrajectoryTab detail={detail} ctx={ctx} seasons={seasons} />}
      {tab === 'deep' && <DeepDiveTab detail={detail} deep={deep} bdeep={bdeep} radar={radar} radarLoading={radarLoading} scouting={scouting} onSaveScouting={saveScouting} />}
      {tab === 'compare' && <CompareTab aId={playerId} players={players} detailA={detail} />}
    </div>
  )
}

/* ── Overview (form movers + emerging + picker) ──────────────────────────── */
/* Squad filter chip — wraps to multiple rows (a club can field 16+ teams, which
   a single-row Segmented can't show without squashing the search bar). */
function SquadChip({ label, active, onClick }) {
  return (
    <button onClick={onClick} className="iq-display font-semibold text-[12.5px] transition whitespace-nowrap"
      style={{ padding: '6px 12px', borderRadius: 99,
        background: active ? 'color-mix(in srgb, var(--pb-accent) 16%, transparent)' : 'var(--pb-surface2)',
        color: active ? 'var(--pb-accent)' : 'var(--pb-dim)',
        border: `1px solid ${active ? 'color-mix(in srgb, var(--pb-accent) 40%, transparent)' : 'var(--pb-hairline2)'}` }}>{label}</button>
  )
}

function Overview({ overview, players, squads, squad, setSquad, pickerPlayers, onPick }) {
  const m = overview
  const noMovers = m && !m.batting?.risers?.length && !m.batting?.fallers?.length && !m.bowling?.risers?.length && !m.bowling?.fallers?.length
  const activeSquad = squads.find(s => s.id === squad)
  return (
    <>
      {/* Search — own full-width row so it always lays out cleanly */}
      <div className="mb-4 max-w-2xl"><PlayerSearch players={pickerPlayers} onPick={onPick} /></div>

      {/* Squad filter — wrapping chips */}
      {squads.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-6">
          <span className="iq-eyebrow mr-0.5" style={{ fontSize: 9 }}>Squad</span>
          <SquadChip label="All squads" active={squad === ''} onClick={() => setSquad('')} />
          {squads.map(s => <SquadChip key={s.id} label={s.name} active={squad === s.id} onClick={() => setSquad(s.id)} />)}
        </div>
      )}

      {/* Selected squad's players — the visible response to the squad filter */}
      {squad !== '' && (
        <Card className="mb-9" eyebrow={`${pickerPlayers.length} player${pickerPlayers.length === 1 ? '' : 's'} · this season`} title={activeSquad?.name || 'Squad'}>
          {pickerPlayers.length === 0 ? <Empty>No current-season players in this squad.</Empty> : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {pickerPlayers.map(p => (
                <button key={p.player_id} onClick={() => onPick(p.player_id)}
                  className="flex items-center gap-2.5 px-2.5 py-2 text-left transition" style={{ borderRadius: 10, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)' }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--pb-accent)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--pb-hairline)' }}>
                  <Initials name={p.name} size={32} />
                  <div className="min-w-0">
                    <div className="font-semibold text-[13px] truncate">{p.name}</div>
                    <div className="iq-mono text-pb-faintest text-[10.5px] truncate">{p.matches} {p.matches === 1 ? 'game' : 'games'}{p.runs ? ` · ${runsPhrase(p.runs)}` : ''}{p.wickets ? ` · ${wktsPhrase(p.wickets)}` : ''}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Form movers — surfaced first */}
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr] items-start mb-9">
        <Card eyebrow="this season vs career-before-it" title="Form movers">
          {m === null ? <LoadingBar label="Loading…" expectedMs={6000} />
            : noMovers ? <Empty>Not enough multi-season history among current players to spot movers yet.</Empty>
              : (
                <div className="grid sm:grid-cols-2 gap-x-8 gap-y-5">
                  <MoverList title="Batting — rising" tone="up" items={m.batting?.risers} kind="bat" onPick={onPick} />
                  <MoverList title="Batting — sliding" tone="down" items={m.batting?.fallers} kind="bat" onPick={onPick} />
                  <MoverList title="Bowling — improving" tone="up" items={m.bowling?.risers} kind="bowl" onPick={onPick} />
                  <MoverList title="Bowling — slipping" tone="down" items={m.bowling?.fallers} kind="bowl" onPick={onPick} />
                </div>
              )}
          <Note>Deltas compare this season to each player's career average before it (min sample applies). Lower bowling average = improving.</Note>
        </Card>
        <Card eyebrow="ones to watch" title="Emerging">
          {!overview?.emerging?.length ? <Empty>No emerging players to flag yet.</Empty> : (
            <div className="space-y-3.5">
              {overview.emerging.map(e => (
                <button key={e.player_id} onClick={() => onPick(e.player_id)} className="flex gap-3 w-full text-left transition hover:opacity-80">
                  <Initials name={e.name} size={38} />
                  <div className="min-w-0">
                    <div className="font-semibold text-[14px] truncate">{e.name}</div>
                    <div className="text-pb-dim text-[12.5px] mt-0.5 leading-snug iq-num">{runsPhrase(e.runs)} · {wktsPhrase(e.wickets)} · {e.seasons} season{e.seasons === 1 ? '' : 's'}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="text-pb-faint text-[13px]">Search a player above for their full trajectory, deep-dive and head-to-head compare.</div>
    </>
  )
}

/* ── Main ────────────────────────────────────────────────────────────────── */
export default function PlayerTrends() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { ctx, seasons } = useIQFilter()
  const seasonId = effectiveSeasonId(ctx)
  const gradeId = ctx?.team?.id || undefined
  const [overview, setOverview] = useState(null)
  const [players, setPlayers] = useState([])
  const [squad, setSquad] = useState('')
  const playerId = searchParams.get('player') || null

  // Form movers, emerging and the player list all follow the global Season + Team
  // filter — re-fetch whenever it changes.
  useEffect(() => {
    setOverview(null)
    api.iqTrendsOverview(seasonId, gradeId).then(setOverview).catch(() => setOverview({ batting: {}, bowling: {}, emerging: [] }))
    api.iqTrendsPlayers(seasonId, gradeId).then(d => setPlayers(d || [])).catch(() => setPlayers([]))
  }, [seasonId, gradeId])

  const pick = (id) => setSearchParams({ player: id }, { replace: true })
  const clear = () => setSearchParams({}, { replace: true })

  const squads = useMemo(() => {
    const map = new Map()
    players.forEach(p => { if (p.squad_id) map.set(p.squad_id, p.squad_name) })
    return [...map.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => (a.name || '').localeCompare(b.name || ''))
  }, [players])
  const pickerPlayers = useMemo(() => (squad ? players.filter(p => p.squad_id === squad) : players), [squad, players])

  return (
    <IQLayout title="Player trends" actions={playerId ? <Btn variant="ghost" sm icon="back" onClick={clear}>All players</Btn> : null}>
      {playerId ? (
        <PlayerDetail playerId={playerId} players={players} ctx={ctx} seasons={seasons} onClear={clear} />
      ) : (
        <>
          <PageIntro>Who's rising, who's sliding, and the full statistical picture on any player — surfaced up front, not buried.</PageIntro>
          <Overview overview={overview} players={players} squads={squads} squad={squad} setSquad={setSquad} pickerPlayers={pickerPlayers} onPick={pick} />
        </>
      )}
    </IQLayout>
  )
}
