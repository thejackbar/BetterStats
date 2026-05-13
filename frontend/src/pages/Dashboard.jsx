import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useClubData, useRecentGames } from '../hooks/useClubData'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import SeasonSelector from '../components/SeasonSelector'
import ClubInactive from './ClubInactive'
import { MILESTONE_ICON_SRC, ThiingIcon, thiings } from '../assets/thiings'
import {
  AnimatedNum, Sparkline, MiniBars, Label, Card, Btn,
  ResultPill, Kpi, PageHeader, PbSpinner,
} from '../lib/presskit'

const SPONSOR_IMAGE = import.meta.env.VITE_SPONSOR_IMAGE || ''
const SPONSOR_URL = import.meta.env.VITE_SPONSOR_URL || ''
const SPONSOR_TEXT = import.meta.env.VITE_SPONSOR_TEXT || ''

function SponsorBanner() {
  if (!SPONSOR_IMAGE && !SPONSOR_TEXT) return null
  const inner = (
    <div className="flex items-center justify-center gap-4 py-3 px-5">
      {SPONSOR_IMAGE && <img src={SPONSOR_IMAGE} alt="Sponsor" className="h-10 object-contain" />}
      {SPONSOR_TEXT && <span className="text-pb-dim text-sm">{SPONSOR_TEXT}</span>}
    </div>
  )
  return (
    <div className="pb-card mb-6">
      <Label className="block text-center pt-3 pb-0">PROUDLY SPONSORED BY</Label>
      {SPONSOR_URL ? <a href={SPONSOR_URL} target="_blank" rel="noopener noreferrer">{inner}</a> : inner}
    </div>
  )
}

function MilestoneRow({ m }) {
  const pct = Math.round((m.current / m.target) * 100)
  const milestoneLabel = m.target ? `${m.target?.toLocaleString()} ${m.type || ''}` : ''
  return (
    <Link to={`/players/${m.player_id}`} className="block hover:opacity-80 transition-opacity">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2 min-w-0">
          <ThiingIcon src={MILESTONE_ICON_SRC[m.type] || thiings.target} alt="" className="w-4 h-4" />
          <div className="min-w-0">
            <span className="text-pb-text text-[13px] font-semibold truncate block">{m.name}</span>
            {milestoneLabel && <span className="font-mono text-[10px] text-pb-faint tracking-wide2">{milestoneLabel}</span>}
          </div>
        </div>
        <span className="font-mono text-[11px] text-pb-dim ml-2 whitespace-nowrap">
          <span className="text-pb-text font-bold">{m.needed?.toLocaleString()}</span> to go
        </span>
      </div>
      <div className="h-1 bg-pb-hairline rounded-sm overflow-hidden">
        <div className="h-full" style={{ width: `${Math.min(100, pct)}%`, background: "var(--pb-accent)" }} />
      </div>
    </Link>
  )
}

function AchievedRow({ m }) {
  const dateLabel = m.achieved_at
    ? new Date(m.achieved_at + 'T00:00:00').toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
    : m.season_name || null
  return (
    <Link to={`/players/${m.player_id}`} className="block hover:opacity-80 transition-opacity">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <ThiingIcon src={MILESTONE_ICON_SRC[m.type] || thiings.trophy} alt="" className="w-4 h-4" />
          <span className="text-pb-text text-[13px] font-semibold truncate">{m.name}</span>
        </div>
        <div className="ml-2 text-right whitespace-nowrap">
          <span className="font-mono font-bold text-pb-text" style={{ color: "var(--pb-accent)" }}>{m.milestone?.toLocaleString()}</span>
          <span className="font-mono text-[10px] text-pb-faint ml-1">{m.type}</span>
        </div>
      </div>
      {dateLabel && <div className="font-mono text-[10px] text-pb-faint tracking-wide2 mt-0.5">{dateLabel}</div>}
    </Link>
  )
}

const MILESTONE_CATS = { batting: 'Batting', bowling: 'Bowling', fielding: 'Fielding', matches: 'Matches Played' }

function MilestonesSection({ milestones, achieved, loading, achievedLoading }) {
  const [tab, setTab] = useState('batting')
  const [page, setPage] = useState(1)
  const PER_PAGE = 10

  const grouped = {}
  for (const m of milestones) {
    const cat = m.category || 'batting'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(m)
  }
  const upcomingTabs = ['batting', 'bowling', 'fielding', 'matches'].filter(c => grouped[c])
  const allTabs = achieved.length > 0 ? [...upcomingTabs, 'achieved'] : upcomingTabs
  const activeTab = allTabs.includes(tab) ? tab : (allTabs[0] || 'batting')
  const isAchieved = activeTab === 'achieved'
  const items = isAchieved ? achieved : (grouped[activeTab] || [])
  const totalPages = Math.max(1, Math.ceil(items.length / PER_PAGE))
  const safePage = Math.min(page, totalPages)
  const pageItems = items.slice((safePage - 1) * PER_PAGE, safePage * PER_PAGE)

  if ((loading && achievedLoading) || !allTabs.length) {
    return loading ? <PbSpinner message="Loading milestones…" /> : <p className="text-pb-faint text-sm py-4">No milestones found.</p>
  }

  return (
    <div>
      <div className="flex items-center justify-between pb-hairline-b mb-4 flex-wrap gap-y-2">
        <div className="flex gap-1 flex-wrap">
          {allTabs.map(cat => (
            <button
              key={cat}
              onClick={() => { setTab(cat); setPage(1) }}
              className={`px-3 py-2 text-[11px] font-mono font-semibold tracking-wide3 relative ${
                cat === activeTab ? 'text-pb-text' : 'text-pb-faint hover:text-pb-dim'
              }`}
            >
              {cat === 'achieved' ? '★ ACHIEVED' : (MILESTONE_CATS[cat] || cat).toUpperCase()}
              {cat === activeTab && <span className="absolute left-0 right-0 -bottom-px h-[2px]" style={{ background: "var(--pb-accent)" }} />}
            </button>
          ))}
        </div>
      </div>
      {(isAchieved ? achievedLoading : loading) ? <PbSpinner /> : (
        <>
          <ul className="flex flex-col gap-3">
            {pageItems.length === 0
              ? <p className="text-pb-faint text-sm py-4">{isAchieved ? 'No milestones achieved this season.' : 'No upcoming milestones.'}</p>
              : pageItems.map((m, i) => (
                  <li key={i} className={i ? "pb-hairline-t pt-3" : ""}>
                    {isAchieved ? <AchievedRow m={m} /> : <MilestoneRow m={m} />}
                  </li>
                ))
            }
          </ul>
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 pt-3 pb-hairline-t">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={safePage === 1}
                className="font-mono text-[11px] text-pb-faint hover:text-pb-text disabled:opacity-30 px-2 py-1">← PREV</button>
              <span className="font-mono text-[11px] text-pb-faint">{safePage} / {totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={safePage === totalPages}
                className="font-mono text-[11px] text-pb-faint hover:text-pb-text disabled:opacity-30 px-2 py-1">NEXT →</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  useClubTheme(club)

  if (inactive) return <ClubInactive />

  const { org, seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade, loading, error } = useClubData(orgId)
  const { games, loading: gamesLoading } = useRecentGames(orgId, { seasonId: selectedSeason, gradeId: selectedGrade })

  const [topBatters, setTopBatters] = useState([])
  const [topBowlers, setTopBowlers] = useState([])
  const [summary, setSummary] = useState(null)
  const [milestones, setMilestones] = useState([])
  const [achievedMilestones, setAchievedMilestones] = useState([])
  const [fixtures, setFixtures] = useState([])
  const [statsLoading, setStatsLoading] = useState(true)
  const [milestonesLoading, setMilestonesLoading] = useState(true)
  const [achievedLoading, setAchievedLoading] = useState(true)
  const [fixturesLoading, setFixturesLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [syncDone, setSyncDone] = useState(false)

  useEffect(() => {
    if (!orgId) return
    setStatsLoading(true)
    Promise.allSettled([
      api.battingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 5 }),
      api.bowlingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 5 }),
      api.getOrgSummary(orgId, { seasonId: selectedSeason, gradeId: selectedGrade }),
    ])
      .then(([b, bw, s]) => {
        if (b.status === 'fulfilled') setTopBatters(b.value)
        if (bw.status === 'fulfilled') setTopBowlers(bw.value)
        if (s.status === 'fulfilled') setSummary(s.value)
      })
      .finally(() => setStatsLoading(false))
  }, [orgId, selectedSeason, selectedGrade])

  useEffect(() => {
    if (!orgId) return
    api.getUpcomingMilestones(orgId, 200)
      .then(setMilestones).catch(() => setMilestones([]))
      .finally(() => setMilestonesLoading(false))
    api.getRecentlyAchievedMilestones(orgId)
      .then(setAchievedMilestones).catch(() => setAchievedMilestones([]))
      .finally(() => setAchievedLoading(false))
    api.getOrgFixtures(orgId)
      .then(setFixtures).catch(() => setFixtures([]))
      .finally(() => setFixturesLoading(false))
  }, [orgId])

  if (loading) return <PbSpinner message="Loading club data…" />
  if (error) return <div className="max-w-7xl mx-auto px-4 py-16 text-pb-red">Error: {error}</div>
  if (!org) return null

  const handleSync = async () => {
    if (syncing) return
    setSyncing(true); setSyncDone(false)
    try {
      await api.triggerSync(orgId)
      await new Promise(r => setTimeout(r, 8000))
      setSyncDone(true)
      setTimeout(() => setSyncDone(false), 3000)
    } finally { setSyncing(false) }
  }

  const currentSeason = seasons?.find(s => s.id === selectedSeason)
  const seasonLabel = currentSeason?.name || (seasons?.[0]?.name) || 'All Seasons'

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`${org.short_name || org.name} · CLUB DASHBOARD`}
          title={org.name}
          meta={[
            summary && <span key="m">PLAYED <span className="text-pb-text">{summary.total_games}</span></span>,
            summary && <span key="r"><span className="text-pb-text">{summary.total_runs?.toLocaleString()}</span> RUNS</span>,
            summary && <span key="w"><span className="text-pb-text">{summary.total_wickets}</span> WICKETS</span>,
            summary && <span key="p"><span className="text-pb-text">{summary.total_players}</span> PLAYERS</span>,
          ].filter(Boolean)}
          actions={[
            <Btn key="sync" onClick={handleSync} disabled={syncing}>
              {syncing ? 'Syncing…' : syncDone ? '✓ Synced' : 'Sync ↻'}
            </Btn>,
            <Link key="lb" to={`/${clubSlug}/leaderboard`} className="font-mono text-[11px] tracking-wide2 px-3.5 py-2 rounded text-[#08110b] hover:opacity-90 transition" style={{ background: "var(--pb-accent)" }}>
              Leaderboard →
            </Link>,
          ]}
        />

        {/* Season / Grade filter */}
        <div className="mb-6">
          <SeasonSelector
            seasons={seasons}
            grades={grades}
            selectedSeason={selectedSeason}
            setSelectedSeason={setSelectedSeason}
            selectedGrade={selectedGrade}
            setSelectedGrade={setSelectedGrade}
          />
        </div>

        {/* Summary KPIs */}
        {summary && (
          <>
            <div className={`grid gap-3 mb-3 ${summary.total_games > 0 ? 'grid-cols-2 lg:grid-cols-4' : 'grid-cols-1 sm:grid-cols-3'}`}>
              {summary.total_games > 0 && <Kpi label="WIN RATE" value={parseInt(summary.win_rate) || 0} suffix="%" accent />}
              <Kpi label="TOTAL RUNS" value={summary.total_runs || 0} />
              <Kpi label="TOTAL WICKETS" value={summary.total_wickets || 0} />
              <Kpi label="PLAYERS" value={summary.total_players || 0} />
            </div>

            {/* W/L/D breakdown */}
            <div className="pb-card p-4 mb-6 flex items-center gap-4 flex-wrap">
              <Label>RESULTS BREAKDOWN</Label>
              <div className="flex gap-4 font-mono text-[12px]">
                <span style={{ color: "var(--pb-accent)" }}><span className="font-bold">{summary.wins}</span> W</span>
                <span style={{ color: "var(--pb-red)" }}><span className="font-bold">{summary.losses}</span> L</span>
                <span className="text-pb-dim"><span className="font-bold">{summary.draws}</span> D</span>
              </div>
              {summary.highest_score && (
                <div className="ml-auto font-mono text-[11px] text-pb-dim tracking-wide2">
                  HS <span className="text-pb-text">{summary.highest_score}</span>
                </div>
              )}
            </div>
          </>
        )}

        {/* Two-col: leaders + milestones */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 mb-6">
          {/* Top run-scorers */}
          <Card className="xl:col-span-1" title={`TOP BATTERS · ${seasonLabel.toUpperCase()}`}
                action={<Link to={`/${clubSlug}/leaderboard`} className="text-2xs font-mono tracking-wide2 text-pb-dim hover:text-pb-text">ALL →</Link>}>
            {statsLoading ? <PbSpinner /> : topBatters.length === 0 ? (
              <p className="text-pb-faint text-sm py-2">No data yet.</p>
            ) : (
              <ol className="flex flex-col">
                {topBatters.map((p, i) => (
                  <li key={p.player_id} className={`flex items-center gap-3 py-2.5 ${i ? "pb-hairline-t" : ""}`}>
                    <span className="font-mono text-[10px] text-pb-faint w-4">{i + 1}</span>
                    <Link to={`/players/${p.player_id}`} className="flex-1 min-w-0">
                      <div className="text-pb-text text-[14px] font-semibold truncate">{p.name}</div>
                      <div className="text-pb-faint font-mono text-[10.5px] tracking-wide2">
                        AVG {p.average ?? '—'} · HS {p.high_score ?? '—'}
                      </div>
                    </Link>
                    <span className="font-mono text-pb-text text-[14px] font-bold pb-num w-12 text-right" style={{ color: "var(--pb-accent)" }}>
                      {p.total_runs}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          {/* Top wicket-takers */}
          <Card title={`TOP BOWLERS · ${seasonLabel.toUpperCase()}`}
                action={<Link to={`/${clubSlug}/leaderboard`} className="text-2xs font-mono tracking-wide2 text-pb-dim hover:text-pb-text">ALL →</Link>}>
            {statsLoading ? <PbSpinner /> : topBowlers.length === 0 ? (
              <p className="text-pb-faint text-sm py-2">No data yet.</p>
            ) : (
              <ol className="flex flex-col">
                {topBowlers.map((p, i) => (
                  <li key={p.player_id} className={`flex items-center gap-3 py-2.5 ${i ? "pb-hairline-t" : ""}`}>
                    <span className="font-mono text-[10px] text-pb-faint w-4">{i + 1}</span>
                    <Link to={`/players/${p.player_id}`} className="flex-1 min-w-0">
                      <div className="text-pb-text text-[14px] font-semibold truncate">{p.name}</div>
                      <div className="text-pb-faint font-mono text-[10.5px] tracking-wide2">
                        AVG {p.average ?? '—'} · ECON {p.economy ?? '—'} · BEST {
                          p.best_bowling_figures ? p.best_bowling_figures.replace('-', '/') :
                          p.best_figures_wickets != null ? `${p.best_figures_wickets}w` : '—'
                        }
                      </div>
                    </Link>
                    <span className="font-mono text-pb-text text-[14px] font-bold pb-num w-12 text-right" style={{ color: "var(--pb-accent)" }}>
                      {p.total_wickets}w
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          {/* Upcoming milestones preview */}
          <Card title="MILESTONES IN REACH"
                action={<span className="text-2xs font-mono tracking-wide2 text-pb-faint">CLOSEST FIRST</span>}>
            {milestonesLoading ? <PbSpinner /> : (
              <ul className="flex flex-col gap-3">
                {milestones.slice(0, 5).length === 0
                  ? <p className="text-pb-faint text-sm py-2">No upcoming milestones.</p>
                  : milestones.slice(0, 5).map((m, i) => (
                      <li key={i} className={i ? "pb-hairline-t pt-3" : ""}><MilestoneRow m={m} /></li>
                    ))
                }
              </ul>
            )}
          </Card>
        </div>

        {/* Recent results */}
        <Card title="RECENT MATCHES" className="mb-6"
              action={<span className="text-2xs font-mono tracking-wide2 text-pb-faint">{games.length} GAMES</span>}>
          {gamesLoading ? <PbSpinner /> : games.length === 0 ? (
            <p className="text-pb-faint text-sm py-2">No recent games found.</p>
          ) : (
            <div className="overflow-x-auto pb-scroll -mx-2">
              <table className="w-full min-w-[560px] text-[13px]">
                <thead>
                  <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                    <th className="font-medium pb-2 pl-2">DATE</th>
                    <th className="font-medium pb-2">MATCH</th>
                    <th className="font-medium pb-2">GRADE</th>
                    <th className="font-medium pb-2 pr-2">RESULT</th>
                  </tr>
                </thead>
                <tbody>
                  {games.map((g, i) => (
                    <tr key={g.id} className={`${i ? "pb-hairline-t" : ""} hover:bg-pb-surface2 cursor-pointer`}>
                      <td className="py-2.5 pl-2 font-mono text-pb-dim text-[12px]">
                        {g.played_at ? new Date(g.played_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : '—'}
                      </td>
                      <td className="py-2.5">
                        <Link to={`/games/${g.id}?org=${orgId}`} className="text-pb-text hover:text-pb-accent font-medium">
                          {g.home_team} <span className="text-pb-faint text-[11px]">v</span> {g.away_team}
                        </Link>
                      </td>
                      <td className="py-2.5 font-mono text-pb-faint text-[11px] tracking-wide2">{g.grade?.name || '—'}</td>
                      <td className="py-2.5 pr-2"><ResultPill result={g.result} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Upcoming fixtures */}
        {!fixturesLoading && fixtures.length > 0 && (
          <Card title="UPCOMING FIXTURES" className="mb-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {fixtures.slice(0, 6).map((f, i) => (
                <div key={f.id || i} className="pb-card-2 p-4 rounded border border-pb-hairline">
                  <Label>{f.grade}</Label>
                  <div className="text-pb-text font-display text-[20px] font-semibold leading-tight mt-2.5">
                    {f.home_team} <span className="text-pb-faint text-base">v</span> {f.away_team}
                  </div>
                  <div className="font-mono text-pb-faint text-[11px] tracking-wide2 mt-1">
                    {new Date(f.date).toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' })}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        <SponsorBanner />

        {/* Full milestones */}
        <Card title="MILESTONES" className="mb-6">
          <MilestonesSection
            milestones={milestones}
            achieved={achievedMilestones}
            loading={milestonesLoading}
            achievedLoading={achievedLoading}
          />
        </Card>

        <div className="mt-10 pt-6 pb-hairline-t text-center">
          <p className="font-mono text-[10px] tracking-wide2 text-pb-faintest">
            POWERED BY <Link to="/" className="hover:text-pb-dim transition-colors">BETTERSTATS</Link>
          </p>
        </div>
      </main>
    </div>
  )
}
