import { useParams, Link, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useClubData, useRecentGames } from '../hooks/useClubData'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import SeasonSelector from '../components/SeasonSelector'
import LoadingSpinner from '../components/LoadingSpinner'
import ClubInactive from './ClubInactive'
import clsx from 'clsx'

const SPONSOR_IMAGE = import.meta.env.VITE_SPONSOR_IMAGE || ''
const SPONSOR_URL = import.meta.env.VITE_SPONSOR_URL || ''
const SPONSOR_TEXT = import.meta.env.VITE_SPONSOR_TEXT || ''

function SponsorBanner() {
  if (!SPONSOR_IMAGE && !SPONSOR_TEXT) return null
  const inner = (
    <div className="flex items-center justify-center gap-4 py-3 px-5">
      {SPONSOR_IMAGE && <img src={SPONSOR_IMAGE} alt="Sponsor" className="h-10 object-contain" />}
      {SPONSOR_TEXT && <span className="text-slate-400 text-sm">{SPONSOR_TEXT}</span>}
    </div>
  )
  return (
    <div className="card border border-navy-700/50 mb-6">
      <p className="section-label text-center pt-2 pb-0">PROUDLY SPONSORED BY</p>
      {SPONSOR_URL ? <a href={SPONSOR_URL} target="_blank" rel="noopener noreferrer">{inner}</a> : inner}
    </div>
  )
}

function ResultBadge({ result }) {
  const cls = result === 'WIN' ? 'badge-win' : result === 'LOSS' ? 'badge-loss' : 'badge-draw'
  return <span className={cls}>{result || 'N/R'}</span>
}

function ClickableStatCard({ label, value, sub, accent = false, active = false, onClick }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'card p-4 flex flex-col gap-1 text-left w-full transition-all',
        accent && 'border-accent/30 bg-accent/5',
        active && 'ring-2 ring-accent',
        onClick && 'hover:border-accent/50 cursor-pointer',
      )}
    >
      <span className="section-label">{label}</span>
      <span className={clsx(
        'stat-number font-bold leading-none text-2xl',
        accent ? 'text-accent' : 'text-white',
      )}>
        {value ?? '—'}
      </span>
      {sub && <span className="text-xs text-slate-500">{sub}</span>}
    </button>
  )
}

function RecentResults({ games, loading, orgId }) {
  if (loading) return <LoadingSpinner size="sm" />
  if (!games.length) return <p className="text-slate-500 text-sm py-4">No recent games found.</p>

  return (
    <div className="divide-y divide-navy-700">
      {games.map(game => (
        <Link
          key={game.id}
          to={`/scorecards/${game.id}?org=${orgId}`}
          className="flex items-center justify-between py-3 px-1 hover:bg-navy-700/30 transition-colors group"
        >
          <div className="min-w-0">
            <div className="text-sm text-white font-medium truncate">
              {game.home_team} <span className="text-slate-500">vs</span> {game.away_team}
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-slate-500">{game.grade?.name}</span>
              {game.played_at && (
                <span className="text-xs text-slate-600">
                  {new Date(game.played_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3 ml-4 shrink-0">
            <ResultBadge result={game.result} />
            <svg className="w-4 h-4 text-slate-600 group-hover:text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </Link>
      ))}
    </div>
  )
}

function UpcomingFixtures({ fixtures, loading }) {
  if (loading) return <LoadingSpinner size="sm" />
  if (!fixtures.length) return <p className="text-slate-500 text-sm py-4">No upcoming fixtures found.</p>

  return (
    <div className="divide-y divide-navy-700">
      {fixtures.map((f, i) => (
        <div key={f.id || i} className="py-3 px-1">
          <div className="text-sm text-white font-medium">
            {f.home_team} <span className="text-slate-500">vs</span> {f.away_team}
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs text-slate-500">{f.grade}</span>
            <span className="text-xs text-accent font-mono">
              {new Date(f.date).toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' })}
            </span>
            {f.venue && <span className="text-xs text-slate-600 truncate">{f.venue}</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

const MILESTONE_ICONS = { runs: '🏏', wickets: '⚡', matches: '📅', catches: '🤝' }
const CATEGORY_LABELS = { batting: 'Batting', bowling: 'Bowling', fielding: 'Fielding', matches: 'Matches Played' }
const CATEGORY_ORDER = ['batting', 'bowling', 'fielding', 'matches']

function MilestoneCard({ m }) {
  const pct = Math.round((m.current / m.target) * 100)
  return (
    <Link to={`/players/${m.player_id}`} className="block hover:opacity-80 transition-opacity">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-base">{MILESTONE_ICONS[m.type] || '🎯'}</span>
          <span className="text-sm text-white font-medium truncate">{m.name}</span>
        </div>
        <span className="text-xs text-slate-400 ml-2 whitespace-nowrap">
          <span className="stat-number text-accent font-bold">{m.needed.toLocaleString()}</span> {m.type} to go
        </span>
      </div>
      <div className="h-1.5 bg-navy-700 rounded-full overflow-hidden">
        <div className="h-full bg-accent rounded-full transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="flex justify-between mt-0.5">
        <span className="text-xs text-slate-600">{m.current.toLocaleString()} {m.type}</span>
        <span className="text-xs text-slate-600">{m.target.toLocaleString()}</span>
      </div>
    </Link>
  )
}

function AchievedMilestoneCard({ m }) {
  const overBy = m.current - m.milestone
  const dateLabel = m.achieved_at
    ? new Date(m.achieved_at + 'T00:00:00').toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
    : m.season_name || null
  return (
    <Link to={`/players/${m.player_id}`} className="block hover:opacity-80 transition-opacity">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-base">{MILESTONE_ICONS[m.type] || '🏆'}</span>
          <span className="text-sm text-white font-medium truncate">{m.name}</span>
        </div>
        <div className="ml-2 text-right whitespace-nowrap">
          <span className="stat-number text-accent font-bold">{m.milestone.toLocaleString()}</span>
          <span className="text-xs text-slate-400 ml-1">{m.type}</span>
        </div>
      </div>
      <div className="flex justify-between mt-0.5">
        <span className="text-xs text-slate-500">Career total: {m.current.toLocaleString()}</span>
        <span className="text-xs text-slate-600">
          {dateLabel && `${m.achieved_at ? '' : 'Season: '}${dateLabel}`}
          {overBy > 0 && ` · +${overBy.toLocaleString()} past`}
        </span>
      </div>
    </Link>
  )
}

function UpcomingMilestones({ milestones, achieved, loading, achievedLoading }) {
  const [activeTab, setActiveTab] = useState('batting')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(10)

  if (loading && achievedLoading) return <LoadingSpinner size="sm" />

  const grouped = {}
  for (const m of milestones) {
    const cat = m.category || 'batting'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(m)
  }

  const upcomingTabs = CATEGORY_ORDER.filter(c => grouped[c])
  const allTabs = achieved.length > 0 ? [...upcomingTabs, 'achieved'] : upcomingTabs
  const tab = allTabs.includes(activeTab) ? activeTab : (allTabs[0] || 'batting')
  const isAchievedTab = tab === 'achieved'
  const items = isAchievedTab ? achieved : (grouped[tab] || [])
  const totalPages = Math.max(1, Math.ceil(items.length / perPage))
  const safePage = Math.min(page, totalPages)
  const pageItems = items.slice((safePage - 1) * perPage, safePage * perPage)

  if (!allTabs.length) return <p className="text-slate-500 text-sm py-4">No milestones found.</p>

  const switchTab = (cat) => { setActiveTab(cat); setPage(1) }
  const changePerPage = (n) => { setPerPage(n); setPage(1) }

  const tabLoading = isAchievedTab ? achievedLoading : loading

  return (
    <div>
      <div className="flex items-center justify-between border-b border-navy-700 mb-4 flex-wrap gap-y-2">
        <div className="flex gap-1 flex-wrap">
          {allTabs.map(cat => (
            <button
              key={cat}
              onClick={() => switchTab(cat)}
              className={`px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
                tab === cat
                  ? 'border-accent text-accent'
                  : 'border-transparent text-slate-400 hover:text-white'
              }`}
            >
              {cat === 'achieved' ? '🏆 Recently Achieved' : CATEGORY_LABELS[cat]}
              <span className="ml-1.5 text-slate-600 font-mono">
                {cat === 'achieved' ? achieved.length : (grouped[cat]?.length || 0)}
              </span>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 pb-1">
          <span className="text-xs text-slate-500">Show</span>
          {[10, 25, 50].map(n => (
            <button
              key={n}
              onClick={() => changePerPage(n)}
              className={`text-xs px-2 py-1 rounded transition-colors ${
                perPage === n ? 'bg-accent text-navy-950 font-bold' : 'text-slate-400 hover:text-white'
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {tabLoading ? <LoadingSpinner size="sm" /> : (
        <>
          <div className="space-y-3">
            {pageItems.length === 0
              ? <p className="text-slate-500 text-sm py-4">
                  {isAchievedTab ? 'No milestones achieved this season.' : 'No upcoming milestones.'}
                </p>
              : pageItems.map((m, i) => (
                  isAchievedTab
                    ? <AchievedMilestoneCard key={i} m={m} />
                    : <MilestoneCard key={i} m={m} />
                ))
            }
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-navy-700">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={safePage === 1}
                className="text-xs text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1"
              >
                ← Prev
              </button>
              <span className="text-xs text-slate-500 font-mono">
                {safePage} / {totalPages}
                <span className="ml-2 text-slate-600">({items.length} total)</span>
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={safePage === totalPages}
                className="text-xs text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1"
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

const STAT_PANELS = {
  batting: 'batting',
  bowling: 'bowling',
  results: 'results',
  players: 'players',
}

export default function Dashboard() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  useClubTheme(club)
  const navigate = useNavigate()

  if (inactive) return <ClubInactive />
  const { org, seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade, loading, error } = useClubData(orgId)
  const { games, loading: gamesLoading } = useRecentGames(orgId, { seasonId: selectedSeason, gradeId: selectedGrade })

  const [players, setPlayers] = useState([])
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
  const [activePanel, setActivePanel] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [syncDone, setSyncDone] = useState(false)

  useEffect(() => {
    if (!orgId) return
    setStatsLoading(true)
    Promise.allSettled([
      api.listPlayers(orgId),
      api.battingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 5 }),
      api.bowlingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 5 }),
      api.getOrgSummary(orgId, { seasonId: selectedSeason, gradeId: selectedGrade }),
    ])
      .then(([p, b, bw, s]) => {
        if (p.status === 'fulfilled') setPlayers(p.value)
        if (b.status === 'fulfilled') setTopBatters(b.value)
        if (bw.status === 'fulfilled') setTopBowlers(bw.value)
        if (s.status === 'fulfilled') setSummary(s.value)
      })
      .finally(() => setStatsLoading(false))
  }, [orgId, selectedSeason, selectedGrade])

  useEffect(() => {
    if (!orgId) return
    api.getUpcomingMilestones(orgId, 200)
      .then(setMilestones)
      .catch(() => setMilestones([]))
      .finally(() => setMilestonesLoading(false))
    api.getRecentlyAchievedMilestones(orgId)
      .then(setAchievedMilestones)
      .catch(() => setAchievedMilestones([]))
      .finally(() => setAchievedLoading(false))
    api.getOrgFixtures(orgId)
      .then(setFixtures)
      .catch(() => setFixtures([]))
      .finally(() => setFixturesLoading(false))
  }, [orgId])

  if (loading) return <LoadingSpinner message="Loading club data…" />
  if (error) return <div className="max-w-7xl mx-auto px-4 py-16 text-red-400">Error: {error}</div>
  if (!org) return null

  const winRate = summary ? `${summary.win_rate}%` : '—'

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="accent-bar mb-3" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="display-heading text-4xl md:text-5xl text-white">{org.name.toUpperCase()}</h1>
            {org.short_name && <p className="text-slate-500 font-mono text-sm mt-1">{org.short_name}</p>}
          </div>
          <div className="flex gap-2 flex-wrap">
            <Link to={`/${clubSlug}/players`} className="btn-ghost border border-navy-600">Players</Link>
            <Link to={`/${clubSlug}/leaderboard`} className="btn-primary">Leaderboard</Link>
            <Link to={`/${clubSlug}/compare`} className="btn-ghost border border-navy-600">Compare</Link>
            <button
              onClick={async () => {
                if (syncing) return
                setSyncing(true)
                setSyncDone(false)
                try {
                  await api.triggerSync(orgId)
                  await new Promise(r => setTimeout(r, 8000))
                  setSyncDone(true)
                  setTimeout(() => setSyncDone(false), 3000)
                } finally {
                  setSyncing(false)
                }
              }}
              disabled={syncing}
              className="btn-ghost border border-navy-600 flex items-center gap-2 disabled:opacity-60"
            >
              {syncing ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                  </svg>
                  Syncing…
                </>
              ) : syncDone ? (
                <>✓ Synced</>
              ) : (
                <>Sync ↻</>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Season filter */}
      <div className="mb-8">
        <SeasonSelector
          seasons={seasons}
          grades={grades}
          selectedSeason={selectedSeason}
          setSelectedSeason={setSelectedSeason}
          selectedGrade={selectedGrade}
          setSelectedGrade={setSelectedGrade}
        />
      </div>

      {/* Summary stat tiles — clickable */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3 mb-6">
        {selectedSeason && (
          <div className="lg:col-span-2">
            <ClickableStatCard
              label="Win Rate"
              value={winRate}
              sub={summary ? `${summary.wins}W ${summary.losses}L ${summary.draws}D` : null}
              accent
              active={activePanel === 'results'}
              onClick={() => setActivePanel(p => p === 'results' ? null : 'results')}
            />
          </div>
        )}
        <div className="lg:col-span-2">
          <ClickableStatCard
            label="Club Runs"
            value={summary ? summary.total_runs?.toLocaleString() : '—'}
            sub={summary ? `HS: ${summary.highest_score}` : null}
            active={activePanel === 'batting'}
            onClick={() => setActivePanel(p => p === 'batting' ? null : 'batting')}
          />
        </div>
        <div className="lg:col-span-2">
          <ClickableStatCard
            label="Club Wickets"
            value={summary ? summary.total_wickets?.toLocaleString() : '—'}
            active={activePanel === 'bowling'}
            onClick={() => setActivePanel(p => p === 'bowling' ? null : 'bowling')}
          />
        </div>
        <div className="lg:col-span-2">
          <ClickableStatCard
            label="Players"
            value={summary ? summary.total_players : players.length}
            sub={selectedSeason
              ? (summary ? `${summary.total_players} this season` : null)
              : `${summary ? summary.seasons : seasons.length} seasons`}
            active={activePanel === 'players'}
            onClick={() => setActivePanel(p => p === 'players' ? null : 'players')}
          />
        </div>
      </div>

      {/* Expandable stat panel */}
      {activePanel && (
        <div className="card p-5 mb-6 border-accent/30">
          {activePanel === 'batting' && (
            <>
              <div className="flex items-center justify-between mb-4">
                <h2 className="display-heading text-lg text-white">TOP BATTERS</h2>
                <Link to={`/${clubSlug}/leaderboard`} className="text-accent text-xs hover:underline">Full leaderboard →</Link>
              </div>
              {statsLoading ? <LoadingSpinner size="sm" /> : topBatters.length === 0 ? (
                <p className="text-slate-500 text-sm">No data yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-navy-700">
                        <th className="table-header">#</th>
                        <th className="table-header">Player</th>
                        <th className="table-header text-right">Runs</th>
                        <th className="table-header text-right">Avg</th>
                        <th className="table-header text-right">SR</th>
                        <th className="table-header text-right">HS</th>
                        <th className="table-header text-right">6s</th>
                        <th className="table-header text-right">4s</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topBatters.map((p, i) => (
                        <tr key={p.player_id} className="table-row">
                          <td className="table-cell text-slate-600 font-mono">{i + 1}</td>
                          <td className="table-cell">
                            <Link to={`/players/${p.player_id}`} className="text-white hover:text-accent">{p.name}</Link>
                          </td>
                          <td className="table-cell stat-number text-right font-bold text-accent">{p.total_runs}</td>
                          <td className="table-cell stat-number text-right text-white">{p.average ?? '—'}</td>
                          <td className="table-cell stat-number text-right text-slate-300">{p.strike_rate ?? '—'}</td>
                          <td className="table-cell stat-number text-right text-slate-300">{p.high_score ?? '—'}</td>
                          <td className="table-cell stat-number text-right text-slate-400">{p.total_sixes ?? '—'}</td>
                          <td className="table-cell stat-number text-right text-slate-400">{p.total_fours ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          {activePanel === 'bowling' && (
            <>
              <div className="flex items-center justify-between mb-4">
                <h2 className="display-heading text-lg text-white">TOP BOWLERS</h2>
                <Link to={`/${clubSlug}/leaderboard`} className="text-accent text-xs hover:underline">Full leaderboard →</Link>
              </div>
              {statsLoading ? <LoadingSpinner size="sm" /> : topBowlers.length === 0 ? (
                <p className="text-slate-500 text-sm">No data yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-navy-700">
                        <th className="table-header">#</th>
                        <th className="table-header">Player</th>
                        <th className="table-header text-right">Wkts</th>
                        <th className="table-header text-right">Avg</th>
                        <th className="table-header text-right">Econ</th>
                        <th className="table-header text-right">Best</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topBowlers.map((p, i) => (
                        <tr key={p.player_id} className="table-row">
                          <td className="table-cell text-slate-600 font-mono">{i + 1}</td>
                          <td className="table-cell">
                            <Link to={`/players/${p.player_id}`} className="text-white hover:text-accent">{p.name}</Link>
                          </td>
                          <td className="table-cell stat-number text-right font-bold text-accent">{p.total_wickets}</td>
                          <td className="table-cell stat-number text-right text-white">{p.average ?? '—'}</td>
                          <td className="table-cell stat-number text-right text-slate-300">{p.economy ?? '—'}</td>
                          <td className="table-cell stat-number text-right text-slate-300">{p.best_figures_wickets ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          {activePanel === 'results' && (
            <>
              <h2 className="display-heading text-lg text-white mb-4">RESULTS BREAKDOWN</h2>
              {statsLoading || !summary ? <LoadingSpinner size="sm" /> : (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="text-center">
                    <div className="stat-number text-4xl font-bold text-accent">{summary.wins}</div>
                    <div className="section-label mt-1">WINS</div>
                  </div>
                  <div className="text-center">
                    <div className="stat-number text-4xl font-bold text-red-400">{summary.losses}</div>
                    <div className="section-label mt-1">LOSSES</div>
                  </div>
                  <div className="text-center">
                    <div className="stat-number text-4xl font-bold text-slate-400">{summary.draws}</div>
                    <div className="section-label mt-1">DRAWS</div>
                  </div>
                  <div className="text-center">
                    <div className="stat-number text-4xl font-bold text-white">{summary.total_games}</div>
                    <div className="section-label mt-1">TOTAL GAMES</div>
                  </div>
                </div>
              )}
            </>
          )}

          {activePanel === 'players' && (
            <>
              <div className="flex items-center justify-between mb-4">
                <h2 className="display-heading text-lg text-white">ALL PLAYERS</h2>
                <Link to={`/${clubSlug}/players`} className="text-accent text-xs hover:underline">Player search →</Link>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1 max-h-60 overflow-y-auto pr-1">
                {players.map(p => (
                  <Link
                    key={p.id}
                    to={`/players/${p.id}`}
                    className="text-sm text-slate-300 hover:text-accent py-1.5 px-2 rounded hover:bg-navy-700/30 transition-colors truncate"
                  >
                    {p.name}
                  </Link>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <SponsorBanner />

      <div className="grid lg:grid-cols-3 gap-6 mb-6">
        {/* Recent results */}
        <div className="lg:col-span-2 card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="display-heading text-xl text-white">RECENT RESULTS</h2>
            <span className="section-label">Last {games.length}</span>
          </div>
          <RecentResults games={games} loading={gamesLoading} orgId={orgId} />
        </div>

        {/* Upcoming fixtures */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="display-heading text-lg text-white">UPCOMING FIXTURES</h2>
          </div>
          <UpcomingFixtures fixtures={fixtures} loading={fixturesLoading} />
        </div>
      </div>

      {/* Milestones */}
      <div className="card p-5 mb-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="display-heading text-xl text-white">MILESTONES</h2>
          <span className="section-label">Closest first</span>
        </div>
        <UpcomingMilestones
          milestones={milestones}
          achieved={achievedMilestones}
          loading={milestonesLoading}
          achievedLoading={achievedLoading}
        />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Top Batters quick view */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="display-heading text-lg text-white">TOP BATTERS</h2>
            <Link to={`/${clubSlug}/leaderboard`} className="text-accent text-xs hover:underline">See all →</Link>
          </div>
          {statsLoading ? <LoadingSpinner size="sm" /> : topBatters.length === 0 ? (
            <p className="text-slate-500 text-sm">No data yet.</p>
          ) : (
            <div className="space-y-2">
              {topBatters.map((p, i) => (
                <Link key={p.player_id} to={`/players/${p.player_id}`} className="flex items-center justify-between py-1.5 hover:opacity-80 transition-opacity">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-slate-600 font-mono text-sm w-5">{i + 1}</span>
                    <span className="text-sm text-white truncate">{p.name}</span>
                  </div>
                  <div className="flex items-center gap-3 ml-2">
                    <span className="text-xs text-slate-500">avg {p.average ?? '—'}</span>
                    <span className="stat-number text-accent font-bold">{p.total_runs}</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Top Bowlers quick view */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="display-heading text-lg text-white">TOP BOWLERS</h2>
            <Link to={`/${clubSlug}/leaderboard`} className="text-accent text-xs hover:underline">See all →</Link>
          </div>
          {statsLoading ? <LoadingSpinner size="sm" /> : topBowlers.length === 0 ? (
            <p className="text-slate-500 text-sm">No data yet.</p>
          ) : (
            <div className="space-y-2">
              {topBowlers.map((p, i) => (
                <Link key={p.player_id} to={`/players/${p.player_id}`} className="flex items-center justify-between py-1.5 hover:opacity-80 transition-opacity">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-slate-600 font-mono text-sm w-5">{i + 1}</span>
                    <span className="text-sm text-white truncate">{p.name}</span>
                  </div>
                  <div className="flex items-center gap-3 ml-2">
                    <span className="text-xs text-slate-500">econ {p.economy ?? '—'}</span>
                    <span className="stat-number text-accent font-bold">{p.total_wickets}w</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="mt-16 pt-6 border-t border-navy-800 text-center">
        <p className="text-slate-700 text-xs">
          Powered by{' '}
          <a href="/" className="hover:text-slate-500 transition-colors">BetterStats</a>
        </p>
      </div>
    </div>
  )
}
