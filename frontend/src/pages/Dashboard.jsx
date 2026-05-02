import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useClubData, useRecentGames } from '../hooks/useClubData'
import { api } from '../lib/api'
import SeasonSelector from '../components/SeasonSelector'
import LoadingSpinner from '../components/LoadingSpinner'
import StatCard from '../components/StatCard'
import clsx from 'clsx'

function ResultBadge({ result, winningTeam }) {
  const cls = result === 'WIN' ? 'badge-win' : result === 'LOSS' ? 'badge-loss' : 'badge-draw'
  return <span className={cls}>{result || 'N/R'}</span>
}

function RecentResults({ games, loading }) {
  if (loading) return <LoadingSpinner size="sm" />
  if (!games.length) return <p className="text-slate-500 text-sm py-4">No recent games found.</p>

  return (
    <div className="divide-y divide-navy-700">
      {games.map(game => (
        <Link
          key={game.id}
          to={`/games/${game.id}`}
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
          <div className="flex items-center gap-3 ml-4">
            <ResultBadge result={game.result} winningTeam={game.winning_team} />
            <svg className="w-4 h-4 text-slate-600 group-hover:text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </Link>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const { orgId } = useParams()
  const { org, seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade, loading, error } = useClubData(orgId)
  const { games, loading: gamesLoading } = useRecentGames(orgId, { seasonId: selectedSeason, gradeId: selectedGrade })
  const [players, setPlayers] = useState([])
  const [topBatters, setTopBatters] = useState([])
  const [topBowlers, setTopBowlers] = useState([])
  const [statsLoading, setStatsLoading] = useState(true)

  useEffect(() => {
    if (!orgId) return
    Promise.all([
      api.listPlayers(orgId),
      api.battingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 5 }),
      api.bowlingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 5 }),
    ])
      .then(([p, b, bw]) => { setPlayers(p); setTopBatters(b); setTopBowlers(bw) })
      .catch(() => {})
      .finally(() => setStatsLoading(false))
  }, [orgId, selectedSeason, selectedGrade])

  if (loading) return <LoadingSpinner message="Loading club data…" />
  if (error) return <div className="max-w-7xl mx-auto px-4 py-16 text-red-400">Error: {error}</div>
  if (!org) return null

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
          <div className="flex gap-2">
            <Link to={`/leaderboard/${orgId}`} className="btn-primary">Leaderboard</Link>
            <button
              onClick={() => api.triggerSync(orgId)}
              className="btn-ghost border border-navy-600"
            >
              Sync ↻
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

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
        <StatCard label="Players" value={players.length} />
        <StatCard label="Seasons" value={seasons.length} />
        <StatCard label="Recent Games" value={games.length} />
        <StatCard label="Grades" value={grades.length} />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Recent results */}
        <div className="lg:col-span-2 card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="display-heading text-xl text-white">RECENT RESULTS</h2>
            <span className="section-label">Last {games.length}</span>
          </div>
          <RecentResults games={games} loading={gamesLoading} />
        </div>

        {/* Quick navigation */}
        <div className="space-y-6">
          {/* Top Batters */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="display-heading text-lg text-white">TOP BATTERS</h2>
              <Link to={`/leaderboard/${orgId}`} className="text-accent text-xs hover:underline">See all →</Link>
            </div>
            {statsLoading
              ? <LoadingSpinner size="sm" />
              : topBatters.length === 0
                ? <p className="text-slate-500 text-sm">No data yet.</p>
                : (
                  <div className="space-y-2">
                    {topBatters.map((p, i) => (
                      <Link
                        key={p.player_id}
                        to={`/players/${p.player_id}`}
                        className="flex items-center justify-between py-1.5 hover:opacity-80 transition-opacity"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-slate-600 font-mono text-sm w-5">{i + 1}</span>
                          <span className="text-sm text-white truncate">{p.name}</span>
                        </div>
                        <span className="stat-number text-accent font-bold ml-2">{p.total_runs}</span>
                      </Link>
                    ))}
                  </div>
                )
            }
          </div>

          {/* Top Bowlers */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="display-heading text-lg text-white">TOP BOWLERS</h2>
              <Link to={`/leaderboard/${orgId}`} className="text-accent text-xs hover:underline">See all →</Link>
            </div>
            {statsLoading
              ? <LoadingSpinner size="sm" />
              : topBowlers.length === 0
                ? <p className="text-slate-500 text-sm">No data yet.</p>
                : (
                  <div className="space-y-2">
                    {topBowlers.map((p, i) => (
                      <Link
                        key={p.player_id}
                        to={`/players/${p.player_id}`}
                        className="flex items-center justify-between py-1.5 hover:opacity-80 transition-opacity"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-slate-600 font-mono text-sm w-5">{i + 1}</span>
                          <span className="text-sm text-white truncate">{p.name}</span>
                        </div>
                        <span className="stat-number text-accent font-bold ml-2">{p.total_wickets}w</span>
                      </Link>
                    ))}
                  </div>
                )
            }
          </div>

          {/* All players */}
          <div className="card p-5">
            <h2 className="display-heading text-lg text-white mb-4">ALL PLAYERS</h2>
            <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
              {players.map(p => (
                <Link
                  key={p.id}
                  to={`/players/${p.id}`}
                  className="block text-sm text-slate-300 hover:text-accent py-1 transition-colors"
                >
                  {p.name}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
