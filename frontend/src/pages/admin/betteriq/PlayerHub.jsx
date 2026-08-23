/* BetterIQ — Player search: the unified entry point for any player.
 *
 * One search spans THREE worlds:
 *   • Your club's players (full history, from /iq/players) — instant filter.
 *   • Opposition players we've faced (/iq/opposition/player-search).
 *   • Any club in Australia (AnyClubSearch → CA registry).
 *
 * Picking one of YOUR players opens an in-page profile with the toggle the brief
 * asks for: "Career (all clubs)" ↔ "vs a club" (their full head-to-head record
 * against every side, your club included). Opposition / any-club picks open the
 * existing opposition scout, which already carries career + record-vs-us.
 */
import { Fragment, useState, useEffect, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import {
  Card, Stat, Tag, Btn, Search, Empty, Note, PageIntro, Initials, surname,
  Segmented, LoadingCard, LoadingBar, a2, fmtCount, fmtPct, runsPhrase, wktsPhrase,
} from './ui'
import { AreaChart, Radar } from './viz'
import AnyClubSearch from './AnyClubSearch'
import { OppPlayerDetail, buildOppPlayerIndex } from './OppPlayerProfile'
import { DeepDiveTab } from './PlayerDeepDive'
import { useClubPlayers, careerOnlyEntries, entryWithThreat, bestNameMatch, isOrgGuid } from './clubPlayers'
import { formatSeason } from '../../../lib/cricketFormat'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)

/* ── vs-a-club head-to-head (one opponent row) ───────────────────────────── */
function HeadToHead({ row }) {
  if (!row) return <Empty>No record against this club yet.</Empty>
  const dec = (row.wins || 0) + (row.losses || 0)
  const winPct = dec ? (100 * row.wins) / dec : null
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <div>
          <span className="iq-headline iq-num" style={{ fontSize: 30 }}>{row.wins}–{row.losses}</span>
          <span className="iq-eyebrow ml-2">W–L from {fmtCount(row.games)}</span>
        </div>
        {winPct != null && <Tag tone={winPct >= 50 ? 'win' : 'faint'}>{fmtPct(winPct)} win</Tag>}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-3" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
        <Stat label="Runs" value={fmtCount(row.total_runs)} />
        <Stat label="Bat avg" value={a2(row.batting_average)} count={false} />
        <Stat label="High score" value={num(row.high_score)} count={false} />
        <Stat label="Innings" value={fmtCount(row.innings)} />
        <Stat label="Wickets" value={fmtCount(row.wickets)} />
        <Stat label="Bowl avg" value={a2(row.bowling_average)} count={false} />
        <Stat label="Economy" value={a2(row.economy)} count={false} />
        <Stat label="Catches" value={fmtCount((row.catches_non_wk || 0) + (row.catches_wk || 0) + (row.stumpings || 0))} />
      </div>
    </div>
  )
}

/* ── vs-a-club view: picker + selected head-to-head + full opponent table ─── */
function VsClubView({ rows }) {
  const [sel, setSel] = useState(null)
  const [q, setQ] = useState('')
  useEffect(() => { if (!sel && rows.length) setSel(rows[0].opposition) }, [rows, sel])
  if (!rows.length) return <Card><Empty>No opposition data for this player yet.</Empty></Card>
  const selRow = rows.find(r => r.opposition === sel) || rows[0]
  const ql = q.trim().toLowerCase()
  const list = ql ? rows.filter(r => (r.opposition || '').toLowerCase().includes(ql)) : rows
  return (
    <div className="space-y-5">
      <Card eyebrow="head to head" title={selRow.opposition || 'vs club'}
        right={<div className="w-48"><Search value={q} onChange={setQ} placeholder="Pick a club…" /></div>}>
        {ql && (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {list.slice(0, 12).map(r => (
              <button key={r.opposition} onClick={() => { setSel(r.opposition); setQ('') }}
                className="iq-display font-semibold text-[11.5px] transition" style={{ padding: '5px 9px', borderRadius: 8,
                  background: r.opposition === sel ? 'color-mix(in srgb, var(--pb-accent) 16%, transparent)' : 'var(--pb-surface2)',
                  color: r.opposition === sel ? 'var(--pb-accent)' : 'var(--pb-dim)', border: '1px solid var(--pb-hairline2)' }}>
                {r.opposition} <span className="iq-num text-pb-faintest">{fmtCount(r.games)}</span>
              </button>
            ))}
          </div>
        )}
        <HeadToHead row={selRow} />
      </Card>

      <Card eyebrow="every opponent" title="Record vs all clubs">
        <div className="overflow-x-auto -mx-1 iq-scroll">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="iq-eyebrow text-left" style={{ fontSize: 9 }}>
                <th className="py-2 px-1 font-medium">Club</th>
                <th className="py-2 px-1 font-medium text-right">M</th>
                <th className="py-2 px-1 font-medium text-right">W–L</th>
                <th className="py-2 px-1 font-medium text-right">Runs</th>
                <th className="py-2 px-1 font-medium text-right">Avg</th>
                <th className="py-2 px-1 font-medium text-right">Wkts</th>
                <th className="py-2 px-1 font-medium text-right">Avg</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} onClick={() => setSel(r.opposition)} className="cursor-pointer"
                  style={{ borderTop: '1px solid var(--pb-hairline)', background: r.opposition === sel ? 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' : 'transparent' }}>
                  <td className="py-2 px-1 truncate max-w-[200px]">{r.opposition}</td>
                  <td className="py-2 px-1 text-right iq-num text-pb-faint">{fmtCount(r.games)}</td>
                  <td className="py-2 px-1 text-right iq-num">{r.wins}–{r.losses}</td>
                  <td className="py-2 px-1 text-right iq-num font-semibold">{fmtCount(r.total_runs)}</td>
                  <td className="py-2 px-1 text-right iq-num">{a2(r.batting_average)}</td>
                  <td className="py-2 px-1 text-right iq-num font-semibold">{fmtCount(r.wickets)}</td>
                  <td className="py-2 px-1 text-right iq-num text-pb-faint">{a2(r.bowling_average)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Note>Click any club for the full head-to-head above. Runs/averages are this player's, over games against that club.</Note>
      </Card>
    </div>
  )
}

/* ── Career (all clubs) view ─────────────────────────────────────────────── */
function CareerView({ detail }) {
  const b = detail.career?.batting || {}
  const bo = detail.career?.bowling || {}
  const fl = detail.career?.fielding || {}
  const rows = detail.seasons || []
  return (
    <div className="space-y-5">
      <Card eyebrow="career to date" title="Career (all clubs)">
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-y-4 gap-x-3">
          <Stat label="Runs" value={fmtCount(b.total_runs)} />
          <Stat label="Bat avg" value={a2(b.average)} count={false} />
          <Stat label="100s / 50s" value={`${num(b.hundreds, 0)}/${num(b.fifties, 0)}`} />
          <Stat label="Wickets" value={fmtCount(bo.total_wickets)} />
          <Stat label="Bowl avg" value={a2(bo.average)} count={false} />
          <Stat label="Catches" value={fmtCount((fl.total_catches_non_wk || 0) + (fl.total_catches_wk || 0))} />
        </div>
      </Card>

      {rows.length > 0 && (
        <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr] items-start">
          <Card eyebrow="runs per season" title="Trajectory">
            <AreaChart points={rows.map(s => s.total_runs || 0)} labels={rows.map(s => formatSeason(s.season_name))} h={190} />
            <Note>Runs each season across the player's whole recorded career, oldest to newest.</Note>
          </Card>
          <Card eyebrow="the numbers" title="Season by season">
            <div className="overflow-x-auto -mx-1 iq-scroll" style={{ maxHeight: 320 }}>
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="iq-eyebrow text-left" style={{ fontSize: 9 }}>
                    <th className="py-2 px-1 font-medium">Season</th>
                    <th className="py-2 px-1 font-medium text-right">M</th>
                    <th className="py-2 px-1 font-medium text-right">Runs</th>
                    <th className="py-2 px-1 font-medium text-right">Avg</th>
                    <th className="py-2 px-1 font-medium text-right">Wkts</th>
                    <th className="py-2 px-1 font-medium text-right">Avg</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s, i) => (
                    <tr key={i} style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                      <td className="py-2 px-1 iq-mono text-pb-dim whitespace-nowrap">{formatSeason(s.season_name)}</td>
                      <td className="py-2 px-1 text-right iq-num text-pb-faint">{fmtCount(s.matches)}</td>
                      <td className="py-2 px-1 text-right iq-num font-semibold">{fmtCount(s.total_runs)}</td>
                      <td className="py-2 px-1 text-right iq-num">{a2(s.batting_average)}</td>
                      <td className="py-2 px-1 text-right iq-num font-semibold">{fmtCount(s.total_wickets)}</td>
                      <td className="py-2 px-1 text-right iq-num text-pb-faint">{a2(s.bowling_average)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
      <Note>Open the <b style={{ color: 'var(--pb-text)' }}>Deep dive</b> tab for conversion, dismissals, radar, reliability and milestones.</Note>
    </div>
  )
}

/* ── Cross-club compare (your player vs anyone) ──────────────────────────── */
// Fold an internal trends payload / external career blob into one career shape.
function normInternal(detail) {
  const b = detail?.career?.batting || {}, bo = detail?.career?.bowling || {}, fl = detail?.career?.fielding || {}
  return {
    name: detail?.player?.name,
    runs: b.total_runs ?? 0, batAvg: b.average, hundreds: b.hundreds ?? 0, fifties: b.fifties ?? 0,
    wickets: bo.total_wickets ?? 0, bowlAvg: bo.average, econ: bo.economy,
    catches: (fl.total_catches_non_wk ?? 0) + (fl.total_catches_wk ?? 0),
  }
}
function normExternal(player) {
  const t = player?.totals || {}
  return {
    name: player?.name,
    runs: t.runs ?? 0, batAvg: t.average, hundreds: t.hundreds ?? 0, fifties: t.fifties ?? 0,
    wickets: t.wickets ?? 0, bowlAvg: t.bowling_average, econ: t.economy, catches: t.catches ?? 0,
  }
}
// Which side is stronger for a metric (null when equal/incomparable).
function cmp(a, b, dir) {
  const na = Number(a), nb = Number(b)
  if (!isFinite(na) || !isFinite(nb) || na === nb) return null
  return dir === 'low' ? (na < nb ? 'a' : 'b') : (na > nb ? 'a' : 'b')
}
function CmpRow({ label, a, b, better }) {
  const col = (s) => (better === s ? 'var(--pb-brand)' : 'var(--pb-text)')
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 py-2.5" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
      <div className="iq-num font-semibold text-right text-[15px]" style={{ color: col('a') }}>{a}</div>
      <div className="iq-eyebrow text-center" style={{ fontSize: 9, minWidth: 92 }}>{label}</div>
      <div className="iq-num font-semibold text-[15px]" style={{ color: col('b') }}>{b}</div>
    </div>
  )
}

function ComparePanel({ aId, aDetail, ourPlayers }) {
  const [src, setSrc] = useState('ours')     // 'ours' | 'opp'
  const [b, setB] = useState(null)           // { kind:'internal'|'external', id, org?, name }
  const [bClub, setBClub] = useState(null)   // { org, name } for the opposition drill
  const [bCareer, setBCareer] = useState(null)
  const [q, setQ] = useState('')
  // Radars only exist for OUR players (normalised against our squad), so the
  // overlay shows when both sides are internal; an external opponent has none.
  const [radarA, setRadarA] = useState(null)
  const [radarB, setRadarB] = useState(null)

  const roster = useClubPlayers(bClub?.org || null, bClub?.name)

  useEffect(() => {
    let alive = true
    setRadarA(null)
    api.iqPlayerRadar(aId).then(d => { if (alive) setRadarA(d) }).catch(() => { if (alive) setRadarA(null) })
    return () => { alive = false }
  }, [aId])
  useEffect(() => {
    if (b?.kind !== 'internal') { setRadarB(null); return }
    let alive = true
    setRadarB(null)
    api.iqPlayerRadar(b.id).then(d => { if (alive) setRadarB(d) }).catch(() => { if (alive) setRadarB(null) })
    return () => { alive = false }
  }, [b])

  // B's career: internal in one call; external is the polled career blob (the
  // same one the roster builds, so it's usually ready by the time you pick).
  useEffect(() => {
    if (!b) { setBCareer(null); return }
    let alive = true, timer = null
    setBCareer({ loading: true })
    if (b.kind === 'internal') {
      api.iqTrendsPlayer(b.id).then(d => { if (alive) setBCareer({ ready: true, ...normInternal(d) }) }).catch(() => { if (alive) setBCareer({ error: true }) })
    } else {
      const poll = () => api.iqPlayerCareer({ org: b.org, player: b.id, clubName: b.name }).then(d => {
        if (!alive) return
        if (d.status === 'building') { setBCareer({ building: true }); timer = setTimeout(poll, 2500); return }
        if (d.status === 'ready' && d.player) setBCareer({ ready: true, ...normExternal(d.player) })
        else setBCareer({ error: true, message: d.message })
      }).catch(() => { if (alive) setBCareer({ error: true }) })
      poll()
    }
    return () => { alive = false; if (timer) clearTimeout(timer) }
  }, [b])

  const A = useMemo(() => normInternal(aDetail), [aDetail])
  const B = bCareer?.ready ? bCareer : null
  const rows = [
    { label: 'Runs', a: fmtCount(A.runs), b: B ? fmtCount(B.runs) : '—', better: B ? cmp(A.runs, B.runs, 'high') : null },
    { label: 'Bat avg', a: a2(A.batAvg), b: B ? a2(B.batAvg) : '—', better: B ? cmp(A.batAvg, B.batAvg, 'high') : null },
    { label: '100s / 50s', a: `${A.hundreds}/${A.fifties}`, b: B ? `${B.hundreds}/${B.fifties}` : '—', better: null },
    { label: 'Wickets', a: fmtCount(A.wickets), b: B ? fmtCount(B.wickets) : '—', better: B ? cmp(A.wickets, B.wickets, 'high') : null },
    { label: 'Bowl avg', a: a2(A.bowlAvg), b: B ? a2(B.bowlAvg) : '—', better: B ? cmp(A.bowlAvg, B.bowlAvg, 'low') : null },
    { label: 'Economy', a: a2(A.econ), b: B ? a2(B.econ) : '—', better: B ? cmp(A.econ, B.econ, 'low') : null },
    { label: 'Catches', a: fmtCount(A.catches), b: B ? fmtCount(B.catches) : '—', better: B ? cmp(A.catches, B.catches, 'high') : null },
  ]

  const ql = q.trim().toLowerCase()
  const ourMatches = ql ? ourPlayers.filter(p => p.player_id !== aId && (p.name || '').toLowerCase().includes(ql)).slice(0, 10) : []
  const rosterList = roster?.status === 'ready' ? (roster.players || []) : []
  const rosterMatches = (ql ? rosterList.filter(p => (p.name || '').toLowerCase().includes(ql)) : rosterList).slice(0, 14)

  const pickSrc = (v) => { setSrc(v); setB(null); setBClub(null); setBCareer(null); setQ('') }

  return (
    <Card eyebrow="head to head" title={`${A.name || 'Your player'} vs ${B?.name || (b ? b.name : 'pick a player')}`}>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <Segmented sm value={src} onChange={pickSrc} options={[{ value: 'ours', label: 'Your club' }, { value: 'opp', label: 'Opposition' }]} />
        {src === 'ours'
          ? <div className="flex-1 min-w-[220px] max-w-sm"><Search value={q} onChange={setQ} placeholder="Search your players…" /></div>
          : <div className="flex-1 min-w-[220px] max-w-sm"><AnyClubSearch placeholder="Pick a club to compare against…" onPick={(org) => { setBClub({ org: org.id, name: org.name }); setB(null); setBCareer(null); setQ('') }} /></div>}
      </div>

      {src === 'ours' && ql && (
        <div className="mb-4 flex flex-wrap gap-2">
          {ourMatches.length === 0 ? <Empty>No match in your squad.</Empty> : ourMatches.map(p => (
            <button key={p.player_id} onClick={() => { setB({ kind: 'internal', id: p.player_id, name: p.name }); setQ('') }}
              className="text-[12.5px] px-2.5 py-1.5" style={{ background: 'var(--pb-surface2)', borderRadius: 8, border: '1px solid var(--pb-hairline2)' }}>{p.name}</button>
          ))}
        </div>
      )}
      {src === 'opp' && bClub && (
        <div className="mb-4">
          <div className="iq-eyebrow mb-2">{bClub.name}{roster?.status === 'building' ? ' · pulling roster…' : ''}</div>
          <Search value={q} onChange={setQ} placeholder={`Search ${bClub.name} players…`} className="max-w-sm mb-2.5" />
          <div className="flex flex-wrap gap-2">
            {rosterMatches.length === 0
              ? <Empty>{roster?.status === 'building' ? 'Pulling their player list…' : 'No players found.'}</Empty>
              : rosterMatches.map(p => (
                <button key={p.player_id} onClick={() => setB({ kind: 'external', id: p.player_id, org: bClub.org, name: p.name })}
                  className="text-[12.5px] px-2.5 py-1.5" style={{ background: b?.id === p.player_id ? 'color-mix(in srgb, var(--pb-accent) 14%, transparent)' : 'var(--pb-surface2)', borderRadius: 8, border: '1px solid var(--pb-hairline2)' }}>
                  {p.name}{p.runs ? ` · ${runsPhrase(p.runs)}` : ''}</button>
              ))}
          </div>
        </div>
      )}

      {!b ? <Empty>Pick a player to compare {A.name || 'your player'} against.</Empty>
        : bCareer?.building ? <LoadingCard label={`Building ${b.name}'s career…`} expectedMs={30000} />
        : bCareer?.error ? <Empty>{bCareer.message || "Couldn't load that player's career."}</Empty>
        : bCareer?.loading ? <LoadingCard label="Loading…" expectedMs={4000} />
        : (() => {
          const ra = radarA?.bat && radarA.bat.values?.length ? radarA.bat : null
          const rb = radarB?.bat && radarB.bat.values?.length ? radarB.bat : null
          return (
            <div className="max-w-xl mx-auto mt-1">
              {ra && rb && (
                <div className="flex flex-col items-center mb-5">
                  <Radar key={`${aId}-${b.id}`} axes={ra.axes} values={ra.values} compareValues={rb.values} compareColor="var(--iq-c-amber)" size={240} />
                  <div className="flex items-center gap-4 mt-2 text-[11.5px]">
                    <span className="inline-flex items-center gap-1.5"><span style={{ width: 14, height: 3, background: 'var(--pb-accent)', borderRadius: 2 }} />{surname(A.name || '')}</span>
                    <span className="inline-flex items-center gap-1.5"><span style={{ width: 14, height: 3, background: 'var(--iq-c-amber)', borderRadius: 2 }} />{surname(B?.name || b.name || '')}</span>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 pb-1">
                <div className="text-right font-bold iq-display truncate" style={{ color: 'var(--pb-accent)' }}>{surname(A.name || '')}</div>
                <div style={{ minWidth: 92 }} />
                <div className="font-bold iq-display truncate" style={{ color: 'var(--iq-c-amber)' }}>{surname(B?.name || b.name || '')}</div>
              </div>
              {rows.map(r => <CmpRow key={r.label} {...r} />)}
            </div>
          )
        })()}
      <Note>Career totals on each side, greener figure the stronger. Your player is their full recorded history; an opposition player is the last ~10 years from Cricket Australia, so a long career can read low.</Note>
    </Card>
  )
}

/* ── Our-player profile (career ↔ vs-club ↔ compare) ─────────────────────── */
function OurPlayerProfile({ pid, ourPlayers }) {
  const [detail, setDetail] = useState(null)
  const [oppRows, setOppRows] = useState(null)
  const [view, setView] = useState('career')
  // Deep-dive data, lazy-loaded the first time the Deep dive tab is opened.
  const [deep, setDeep] = useState(null)
  const [bdeep, setBdeep] = useState(null)
  const [radar, setRadar] = useState(null)
  const [radarLoading, setRadarLoading] = useState(false)
  const [scouting, setScouting] = useState(null)
  const deepFetched = useRef(false)

  useEffect(() => {
    let alive = true
    setDetail(null); setOppRows(null)
    deepFetched.current = false; setDeep(null); setBdeep(null); setRadar(null); setScouting(null)
    api.iqTrendsPlayer(pid).then(d => { if (alive) setDetail(d) }).catch(() => { if (alive) setDetail({ error: true }) })
    api.getPlayerByOpposition(pid).then(d => { if (alive) setOppRows(Array.isArray(d) ? d : []) }).catch(() => { if (alive) setOppRows([]) })
    return () => { alive = false }
  }, [pid])

  useEffect(() => {
    if (view !== 'deep' || deepFetched.current) return
    deepFetched.current = true
    let alive = true
    setRadarLoading(true)
    api.iqPlayerDeepDive(pid).then(d => { if (alive) setDeep(d) }).catch(() => { if (alive) setDeep(null) })
    api.iqBowlerDeepDive(pid).then(d => { if (alive) setBdeep(d) }).catch(() => { if (alive) setBdeep(null) })
    api.iqPlayerRadar(pid).then(d => { if (alive) setRadar(d) }).catch(() => { if (alive) setRadar(null) }).finally(() => { if (alive) setRadarLoading(false) })
    api.iqPlayerScouting(pid).then(d => { if (alive) setScouting(d) }).catch(() => { if (alive) setScouting(null) })
    return () => { alive = false }
  }, [view, pid])

  const saveScouting = async (body) => {
    const saved = await api.iqSavePlayerScouting(pid, body)
    setScouting(saved)
    return saved
  }

  if (detail === null) return <LoadingCard label="Loading player…" expectedMs={4000} />
  if (detail?.error) return <Card><Empty>Couldn't load this player.</Empty></Card>

  return (
    <div className="iq-fade space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <Initials name={detail.player?.name} size={56} tone="accent" />
        <div className="min-w-0">
          <h2 className="iq-headline" style={{ fontSize: 28 }}>{detail.player?.name}</h2>
          <div className="text-pb-faint text-[12.5px] mt-1">
            {fmtCount(detail.career?.batting?.total_runs)} runs · {fmtCount(detail.career?.bowling?.total_wickets)} wkts
            {oppRows?.length ? ` · faced ${oppRows.length} clubs` : ''}
          </div>
        </div>
        <div className="ml-auto">
          <Btn variant="ghost" sm icon="trend" onClick={() => window.open(`/admin/betteriq/trends?player=${encodeURIComponent(pid)}`, '_self')}>Full trends</Btn>
        </div>
      </div>

      <Segmented value={view} onChange={setView} options={[
        { value: 'career', label: 'Career (all clubs)' },
        { value: 'deep', label: 'Deep dive' },
        { value: 'vs', label: 'vs a club' },
        { value: 'compare', label: 'Compare' },
      ]} />

      {view === 'career' && <CareerView detail={detail} />}
      {view === 'deep' && (deep === null && !deepFetched.current
        ? <LoadingCard label="Loading deep dive…" expectedMs={5000} />
        : <DeepDiveTab detail={detail} deep={deep} bdeep={bdeep} radar={radar} radarLoading={radarLoading} scouting={scouting} onSaveScouting={saveScouting} />)}
      {view === 'vs' && (oppRows === null
        ? <LoadingCard label="Loading head-to-head…" expectedMs={4000} />
        : <VsClubView rows={oppRows} />)}
      {view === 'compare' && <ComparePanel aId={pid} aDetail={detail} ourPlayers={ourPlayers} />}
    </div>
  )
}

/* ── Unified search ──────────────────────────────────────────────────────── */
function SearchLanes({ ourPlayers, onPickOurs, onPickExternal }) {
  const [q, setQ] = useState('')
  const [ext, setExt] = useState([])
  const [extLoading, setExtLoading] = useState(false)
  const t = q.trim().toLowerCase()

  // Debounced opposition-player search (players our bowlers have dismissed).
  useEffect(() => {
    const s = q.trim()
    if (s.length < 2) { setExt([]); return }
    let alive = true
    setExtLoading(true)
    const timer = setTimeout(() => {
      api.iqSearchOpponentPlayers(s)
        .then(d => { if (alive) setExt(Array.isArray(d) ? d : []) })
        .catch(() => { if (alive) setExt([]) })
        .finally(() => { if (alive) setExtLoading(false) })
    }, 280)
    return () => { alive = false; clearTimeout(timer) }
  }, [q])

  const ourMatches = useMemo(() => {
    if (!t) return []
    return ourPlayers.filter(p => (p.name || '').toLowerCase().includes(t)).slice(0, 12)
  }, [t, ourPlayers])

  const recent = useMemo(() => ourPlayers.slice(0, 18), [ourPlayers])

  return (
    <div className="space-y-6">
      <div className="max-w-2xl">
        <Search value={q} onChange={setQ} placeholder="Search any player: yours or an opponent…" autoFocus className="w-full" />
      </div>

      {/* Any club in Australia */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="iq-eyebrow">Any club</span>
        <AnyClubSearch className="flex-1 min-w-[260px] max-w-md"
          placeholder="Scout a whole club (any club in Australia)…"
          onPick={(org) => onPickExternal({ opp_key: org.id, name: org.name })} />
      </div>

      {t && (
        <div className="grid gap-6 lg:grid-cols-2 items-start">
          <Card eyebrow="your club" title="Your players">
            {ourMatches.length === 0 ? <Empty>No match in your squad.</Empty> : (
              <div className="space-y-1">
                {ourMatches.map(p => (
                  <button key={p.player_id} onClick={() => onPickOurs(p.player_id)}
                    className="w-full flex items-center justify-between gap-3 px-2 py-2 text-left transition" style={{ borderRadius: 9 }}
                    onMouseEnter={e => { e.currentTarget.style.background = 'var(--pb-surface2)' }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
                    <span className="flex items-center gap-2.5 min-w-0">
                      <Initials name={p.name} size={30} />
                      <span className="font-medium text-[13.5px] truncate">{p.name}</span>
                    </span>
                    <span className="iq-mono text-pb-faintest text-[10.5px] whitespace-nowrap">
                      {p.runs ? runsPhrase(p.runs) : ''}{p.wickets ? ` · ${wktsPhrase(p.wickets)}` : ''}{p.last_year ? ` · ${p.last_year}` : ''}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </Card>

          <Card eyebrow="opponents" title="Opposition players">
            {extLoading && ext.length === 0 ? <Empty>Searching…</Empty>
              : ext.length === 0 ? <Empty>No opponent found: we index batters our bowlers have dismissed.</Empty>
              : (
                <div className="space-y-1">
                  {ext.slice(0, 12).map((r, i) => (
                    <button key={`${r.opp_key}-${i}`} onClick={() => onPickExternal({ opp_key: r.opp_key, name: r.club_name }, r.name)}
                      className="w-full flex items-center justify-between gap-3 px-2 py-2 text-left transition" style={{ borderRadius: 9 }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'var(--pb-surface2)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
                      <span className="min-w-0">
                        <span className="font-medium text-[13.5px] truncate block">{r.name}</span>
                        <span className="text-pb-faintest text-[11px] truncate block">{r.club_name}</span>
                      </span>
                      <span className="iq-mono text-pb-faint text-[10.5px] whitespace-nowrap">{runsPhrase(r.runs)} vs us</span>
                    </button>
                  ))}
                </div>
              )}
            <Note>Opens the full opposition scout: their form, history, dismissals and record against you.</Note>
          </Card>
        </div>
      )}

      {!t && (
        <Card eyebrow={`${ourPlayers.length} players · your club`} title="Your players">
          {recent.length === 0 ? <Empty>No players found.</Empty> : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {recent.map(p => (
                <button key={p.player_id} onClick={() => onPickOurs(p.player_id)}
                  className="flex items-center gap-2.5 px-2.5 py-2 text-left transition" style={{ borderRadius: 10, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)' }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--pb-accent)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--pb-hairline)' }}>
                  <Initials name={p.name} size={32} />
                  <div className="min-w-0">
                    <div className="font-semibold text-[13px] truncate">{p.name}</div>
                    <div className="iq-mono text-pb-faintest text-[10.5px] truncate">{p.matches ? `${fmtCount(p.matches)} games` : ''}{p.runs ? ` · ${runsPhrase(p.runs)}` : ''}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
          <Note>Type above to search your whole squad and opponents, or pick any club in Australia.</Note>
        </Card>
      )}
    </div>
  )
}

/* ── External club / player profile (in-page, reuses the opposition scout) ─── */
function ExternalClubView({ club, initialPlayerName }) {
  const [dossier, setDossier] = useState(null)
  const [status, setStatus] = useState('building')
  const [sel, setSel] = useState(null)
  const [playerQ, setPlayerQ] = useState('')
  const [tags, setTags] = useState({})
  const pollRef = useRef(null)
  const pendingNameRef = useRef(null)

  useEffect(() => { api.iqOpponentTags().then(d => setTags(d || {})).catch(() => setTags({})) }, [])

  // Build/poll the club's live dossier (same contract as the opposition scout).
  useEffect(() => {
    let alive = true
    setDossier(null); setStatus('building'); setSel(null)
    pendingNameRef.current = (initialPlayerName || '').trim().toLowerCase() || null
    const params = { opponent: club.opp_key, name: club.name }
    const poll = () => {
      api.iqOppositionDossier(params).then(d => {
        if (!alive) return
        setDossier(d); setStatus(d.status)
        if (d.status === 'building') pollRef.current = setTimeout(poll, 2500)
      }).catch(() => { if (alive) setStatus('error') })
    }
    poll()
    return () => { alive = false; if (pollRef.current) clearTimeout(pollRef.current) }
  }, [club.opp_key, club.name, initialPlayerName])

  const saveTag = async (playerId, body) => {
    const saved = await api.iqSaveOpponentTag(playerId, body)
    setTags(t => ({ ...t, [playerId]: saved }))
    return saved
  }

  const index = useMemo(() => buildOppPlayerIndex(dossier), [dossier])
  const enriched = useMemo(() => {
    const m = new Map()
    for (const d of [...(dossier?.danger_batters || []), ...(dossier?.danger_bowlers || [])]) m.set(d.player_id, d)
    return m
  }, [dossier])
  const all = useMemo(() => [...index.entries()].map(([id, v]) => ({ id, ...v }))
    .sort((a, b) => (b.bat?.runs || 0) - (a.bat?.runs || 0) || (b.bowl?.wickets || 0) - (a.bowl?.wickets || 0)), [index])
  const orgGuid = dossier?.opponent?.org_id || (isOrgGuid(club.opp_key) ? club.opp_key : null)
  const clubPlayers = useClubPlayers(orgGuid, club.name)
  const careerOnly = useMemo(() => careerOnlyEntries(index, clubPlayers), [index, clubPlayers])
  const everyone = useMemo(() => [...all, ...careerOnly], [all, careerOnly])
  const selected = useMemo(() => {
    if (!sel) return null
    const e = index.get(sel) || careerOnly.find(p => p.id === sel) || null
    return entryWithThreat(e, dossier)
  }, [sel, index, careerOnly, dossier])

  // Once the squad is ready, resolve a pending player name (from the search) and
  // select them — names come in several shapes, so this is a token scorer.
  useEffect(() => {
    if (status !== 'ready' || !pendingNameRef.current || !everyone.length) return
    const hit = bestNameMatch(pendingNameRef.current, everyone)
    const rosterPending = orgGuid && (!clubPlayers || clubPlayers.status === 'building')
    if (!hit && rosterPending) return
    pendingNameRef.current = null
    if (hit) setSel(hit.id)
  }, [status, everyone, clubPlayers])  // eslint-disable-line react-hooks/exhaustive-deps

  const pq = playerQ.trim().toLowerCase()
  const playerMatches = pq ? everyone.filter(p => p.name.toLowerCase().includes(pq)) : everyone

  if (status === 'building') return (
    <div className="iq-card iq-accent-card p-8 text-center iq-fade">
      <div className="iq-display font-bold text-[16px]">Building {club.name}'s squad…</div>
      <div className="text-pb-faint text-[13px] mt-1.5 max-w-md mx-auto">Pulling their recent scorecards live. The first time can take up to a minute.</div>
      <div className="max-w-md mx-auto mt-5"><LoadingBar expectedMs={35000} /></div>
    </div>
  )
  if (status === 'error' || status === 'unavailable') return (
    <div className="iq-card p-6"><Empty>Couldn't build a live dossier for {club.name} right now. Try again shortly.</Empty></div>
  )

  return (
    <div className="iq-fade">
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <span className="iq-eyebrow">Club</span>
        <span className="px-3 py-1.5 iq-display font-semibold text-[13px]" style={{ borderRadius: 99, background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)', border: '1px solid color-mix(in srgb, var(--pb-accent) 35%, transparent)' }}>{club.name}</span>
        <div className="flex-1 min-w-[220px] max-w-xs"><Search value={playerQ} onChange={setPlayerQ} placeholder={`Search ${club.name} players…`} className="w-full" /></div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[260px_1fr] items-start">
        <div className="iq-card p-2 lg:sticky lg:top-20">
          <div className="iq-eyebrow px-2 py-2">Squad ({all.length})</div>
          <div className="max-h-[64vh] overflow-y-auto iq-scroll">
            {playerMatches.length === 0
              ? <Empty className="px-2.5 py-2">{everyone.length === 0
                  ? (clubPlayers?.status === 'building' ? 'Pulling their player history…' : 'No players found.')
                  : 'No match.'}</Empty>
              : playerMatches.map((p, i) => {
                const on = p.id === sel
                const danger = tags[p.id]?.is_danger || enriched.get(p.id)?.alert?.level === 'danger'
                const firstCareer = p.careerOnly && (i === 0 || !playerMatches[i - 1].careerOnly)
                return (
                  <Fragment key={p.id}>
                    {firstCareer && <div className="iq-eyebrow px-2 pt-3 pb-1">Earlier years</div>}
                    <button onClick={() => setSel(p.id)}
                      className="w-full flex items-center justify-between gap-2 px-2.5 py-2 text-left transition"
                      style={{ borderRadius: 9, background: on ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent' }}>
                      <span className="font-medium text-[13.5px] truncate flex items-center gap-1.5" style={{ color: on ? 'var(--pb-accent)' : 'var(--pb-text)' }}>
                        {p.name}
                        {danger && <span style={{ width: 6, height: 6, borderRadius: 99, background: 'var(--pb-red)' }} />}
                      </span>
                      <span className="iq-mono text-pb-faint shrink-0" style={{ fontSize: 10.5 }}>
                        {p.careerOnly ? (p.career?.runs ? runsPhrase(p.career.runs) : '') : (p.bat?.runs ? runsPhrase(p.bat.runs) : '')}
                      </span>
                    </button>
                  </Fragment>
                )
              })}
          </div>
        </div>
        <div>
          {selected
            ? <OppPlayerDetail entry={selected} enriched={enriched.get(sel)} opponentName={club.name} playerId={sel} tag={tags[sel]} onSaveTag={saveTag}
                dossierBatting={dossier?.batting || []} dossierBowling={dossier?.bowling || []} orgGuid={orgGuid} />
            : <div className="iq-card p-8"><Empty>Pick one of {club.name}'s players for their full profile: career, dismissal patterns and record against you.</Empty></div>}
        </div>
      </div>
      {dossier?.coverage?.notes?.length > 0 && <Note>{dossier.coverage.notes.join(' ')}</Note>}
    </div>
  )
}

/* ── Page ────────────────────────────────────────────────────────────────── */
export default function PlayerHub() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [ourPlayers, setOurPlayers] = useState([])
  const [external, setExternal] = useState(null)  // { club, playerName }
  const pid = searchParams.get('player') || null

  useEffect(() => {
    api.iqAllPlayers().then(d => setOurPlayers(Array.isArray(d) ? d : [])).catch(() => setOurPlayers([]))
  }, [])

  const pickOurs = (id) => { setExternal(null); setSearchParams({ player: id }, { replace: false }) }
  const pickExternal = (club, playerName) => { setSearchParams({}, { replace: false }); setExternal({ club, playerName: playerName || null }) }
  const clearAll = () => { setExternal(null); setSearchParams({}, { replace: false }) }

  const showingProfile = pid || external
  return (
    <IQLayout title="Player search" actions={showingProfile ? <Btn variant="ghost" sm icon="back" onClick={clearAll}>All players</Btn> : null}>
      {pid ? (
        <OurPlayerProfile pid={pid} ourPlayers={ourPlayers} />
      ) : external ? (
        <ExternalClubView club={external.club} initialPlayerName={external.playerName} />
      ) : (
        <>
          <PageIntro>One search for any player. Pull up one of your own for their career and their record against any club, or scout an opposition player at any club in Australia.</PageIntro>
          <SearchLanes ourPlayers={ourPlayers} onPickOurs={pickOurs} onPickExternal={pickExternal} />
        </>
      )}
    </IQLayout>
  )
}
