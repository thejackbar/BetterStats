import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useMemo } from 'react'
import { useClubData } from '../hooks/useClubData'
import { useClub } from '../hooks/useClub'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import ClubInactive from './ClubInactive'
import clsx from 'clsx'

export default function Players() {
  const { clubSlug } = useParams()
  const { orgId, inactive } = useClub(clubSlug)
  const { org, seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade, loading: clubLoading } = useClubData(orgId)

  if (inactive) return <ClubInactive />

  const [players, setPlayers] = useState([])
  const [battingStats, setBattingStats] = useState({})
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    api.listPlayers(orgId)
      .then(setPlayers)
      .catch(() => setPlayers([]))
      .finally(() => setLoading(false))
  }, [orgId])

  useEffect(() => {
    if (!orgId) return
    api.battingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 50 })
      .then(rows => {
        const map = {}
        rows.forEach(r => { map[r.player_id] = r })
        setBattingStats(map)
      })
      .catch(() => {})
  }, [orgId, selectedSeason, selectedGrade])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return players
    return players.filter(p => p.name.toLowerCase().includes(q))
  }, [players, search])

  if (clubLoading) return <LoadingSpinner message="Loading players…" />

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="accent-bar mb-3" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="section-label mb-1">{org?.name}</p>
            <h1 className="display-heading text-4xl md:text-5xl text-white">PLAYERS</h1>
          </div>
          <div className="flex gap-2">
            <Link to={`/${clubSlug}/dashboard`} className="btn-ghost border border-navy-600 text-sm">← Dashboard</Link>
            <Link to={`/${clubSlug}/compare`} className="btn-primary text-sm">Compare Players</Link>
          </div>
        </div>
      </div>

      {/* Search + filters */}
      <div className="flex flex-wrap gap-3 mb-6 items-center">
        <div className="relative flex-1 min-w-48">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Search players…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg pl-9 pr-4 py-2 focus:outline-none focus:border-accent placeholder-slate-500"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white"
            >
              ×
            </button>
          )}
        </div>

        {seasons.length > 0 && (
          <div className="flex items-center gap-2">
            <label className="section-label whitespace-nowrap">Season</label>
            <select
              value={selectedSeason || ''}
              onChange={e => setSelectedSeason(e.target.value || null)}
              className="bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent"
            >
              <option value="">All seasons</option>
              {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
        )}

        {grades.length > 0 && (
          <div className="flex items-center gap-2">
            <label className="section-label whitespace-nowrap">Grade</label>
            <select
              value={selectedGrade || ''}
              onChange={e => setSelectedGrade(e.target.value || null)}
              className="bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent"
            >
              <option value="">All grades</option>
              {grades.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
        )}

        <span className="text-slate-500 text-sm">{filtered.length} players</span>
      </div>

      {loading ? <LoadingSpinner /> : (
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-navy-700">
                <th className="table-header">Player</th>
                <th className="table-header text-right">Inn</th>
                <th className="table-header text-right">Runs</th>
                <th className="table-header text-right">Avg</th>
                <th className="table-header text-right">SR</th>
                <th className="table-header text-right">HS</th>
                <th className="table-header text-right">50s</th>
                <th className="table-header text-right">100s</th>
                <th className="table-header text-right">6s</th>
                <th className="table-header w-16"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={10} className="table-cell text-center text-slate-500 py-8">
                    {search ? `No players matching "${search}"` : 'No players found.'}
                  </td>
                </tr>
              ) : filtered.map(player => {
                const stats = battingStats[player.id]
                return (
                  <tr key={player.id} className="table-row">
                    <td className="table-cell">
                      <Link to={`/players/${player.id}`} className="text-white hover:text-accent transition-colors font-medium">
                        {player.name}
                      </Link>
                    </td>
                    <td className="table-cell stat-number text-right text-slate-400">{stats?.innings ?? '—'}</td>
                    <td className="table-cell stat-number text-right font-bold text-accent">{stats?.total_runs ?? '—'}</td>
                    <td className="table-cell stat-number text-right text-white">{stats?.average ?? '—'}</td>
                    <td className="table-cell stat-number text-right text-slate-300">{stats?.strike_rate ?? '—'}</td>
                    <td className="table-cell stat-number text-right text-slate-300">{stats?.high_score ?? '—'}</td>
                    <td className="table-cell stat-number text-right text-slate-400">{stats?.fifties ?? '—'}</td>
                    <td className="table-cell stat-number text-right">
                      <span className={stats?.hundreds > 0 ? 'text-amber-cricket font-bold' : 'text-slate-500'}>
                        {stats?.hundreds ?? '—'}
                      </span>
                    </td>
                    <td className="table-cell stat-number text-right text-slate-400">{stats?.total_sixes ?? '—'}</td>
                    <td className="table-cell text-right">
                      <Link to={`/players/${player.id}`} className="text-slate-500 hover:text-accent text-xs">
                        View →
                      </Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
