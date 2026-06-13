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
import { useState, useEffect, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import {
  Card, Stat, Tag, Btn, Search, Empty, Note, PageIntro, Initials,
  Segmented, LoadingCard, a2, fmtCount, fmtPct, runsPhrase, wktsPhrase,
} from './ui'
import { AreaChart } from './viz'
import AnyClubSearch from './AnyClubSearch'
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
      <Note>Want the deep dive (conversion, dismissals, radar, milestones)? Open this player in <b style={{ color: 'var(--pb-text)' }}>Player trends</b>.</Note>
    </div>
  )
}

/* ── Our-player profile (career ↔ vs-club) ───────────────────────────────── */
function OurPlayerProfile({ pid }) {
  const [detail, setDetail] = useState(null)
  const [oppRows, setOppRows] = useState(null)
  const [view, setView] = useState('career')

  useEffect(() => {
    let alive = true
    setDetail(null); setOppRows(null)
    api.iqTrendsPlayer(pid).then(d => { if (alive) setDetail(d) }).catch(() => { if (alive) setDetail({ error: true }) })
    api.getPlayerByOpposition(pid).then(d => { if (alive) setOppRows(Array.isArray(d) ? d : []) }).catch(() => { if (alive) setOppRows([]) })
    return () => { alive = false }
  }, [pid])

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
        { value: 'vs', label: 'vs a club' },
      ]} />

      {view === 'career' && <CareerView detail={detail} />}
      {view === 'vs' && (oppRows === null
        ? <LoadingCard label="Loading head-to-head…" expectedMs={4000} />
        : <VsClubView rows={oppRows} />)}
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
        <Search value={q} onChange={setQ} placeholder="Search any player — yours or an opponent…" autoFocus className="w-full" />
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
              : ext.length === 0 ? <Empty>No opponent found — we index batters our bowlers have dismissed.</Empty>
              : (
                <div className="space-y-1">
                  {ext.slice(0, 12).map((r, i) => (
                    <button key={`${r.opp_key}-${i}`} onClick={() => onPickExternal({ opp_key: r.opp_key, name: r.club_name })}
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

/* ── Page ────────────────────────────────────────────────────────────────── */
export default function PlayerHub() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [ourPlayers, setOurPlayers] = useState([])
  const pid = searchParams.get('player') || null

  useEffect(() => {
    api.iqAllPlayers().then(d => setOurPlayers(Array.isArray(d) ? d : [])).catch(() => setOurPlayers([]))
  }, [])

  const pickOurs = (id) => setSearchParams({ player: id }, { replace: false })
  const clearPlayer = () => setSearchParams({}, { replace: false })
  const pickExternal = (club) => {
    const sp = new URLSearchParams({ opponent: club.opp_key })
    if (club.name) sp.set('name', club.name)
    navigate(`/admin/betteriq/opposition-player?${sp.toString()}`)
  }

  return (
    <IQLayout title="Player search" actions={pid ? <Btn variant="ghost" sm icon="back" onClick={clearPlayer}>All players</Btn> : null}>
      {pid ? (
        <OurPlayerProfile pid={pid} />
      ) : (
        <>
          <PageIntro>One search for any player. Pull up one of your own for their career and their record against any club, or scout an opposition player at any club in Australia.</PageIntro>
          <SearchLanes ourPlayers={ourPlayers} onPickOurs={pickOurs} onPickExternal={pickExternal} />
        </>
      )}
    </IQLayout>
  )
}
