import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useCallback } from 'react'
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { api } from '../lib/api'
import { usePlayerStats } from '../hooks/usePlayerStats'
import StatCard from '../components/StatCard'
import BattingTable from '../components/BattingTable'
import BowlingTable from '../components/BowlingTable'
import TrendChart from '../components/TrendChart'
import RunsChart from '../components/RunsChart'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

const TABS = ['batting', 'bowling', 'analysis', 'milestones', 'partnerships']

const DISMISSAL_COLORS = [
  '#16c784', '#3b82f6', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16',
]

function DismissalChart({ data }) {
  if (!data?.length) return <p className="text-slate-500 text-sm">No dismissal data</p>
  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie
          data={data}
          dataKey="count"
          nameKey="dismissal_type"
          cx="50%"
          cy="50%"
          outerRadius={80}
          label={({ dismissal_type, percent }) =>
            `${dismissal_type} (${(percent * 100).toFixed(0)}%)`
          }
          labelLine={false}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={DISMISSAL_COLORS[i % DISMISSAL_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
          labelStyle={{ color: '#94a3b8' }}
          itemStyle={{ color: '#fff' }}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}

function SeasonChart({ data }) {
  if (!data?.length) return <p className="text-slate-500 text-sm">No season data</p>
  const chartData = [...data].reverse()
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="season_name" tick={{ fill: '#64748b', fontSize: 11 }} />
        <YAxis yAxisId="left" tick={{ fill: '#64748b', fontSize: 11 }} />
        <YAxis yAxisId="right" orientation="right" tick={{ fill: '#64748b', fontSize: 11 }} />
        <Tooltip
          contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
          labelStyle={{ color: '#94a3b8' }}
          itemStyle={{ color: '#fff' }}
        />
        <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
        <Bar yAxisId="left" dataKey="total_runs" name="Runs" fill="#16c784" radius={[3, 3, 0, 0]} />
        <Bar yAxisId="right" dataKey="total_wickets" name="Wickets" fill="#3b82f6" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function StatsTable({ rows, columns }) {
  if (!rows?.length) return <p className="text-slate-500 text-sm px-4 py-4">No data available</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-navy-700">
            {columns.map(col => (
              <th key={col.key} className="px-4 py-2.5 text-left text-xs uppercase tracking-wider text-slate-500 font-medium">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-navy-700/50 hover:bg-navy-800/30 transition-colors">
              {columns.map(col => (
                <td key={col.key} className={clsx('px-4 py-2.5', col.accent ? 'stat-number text-white font-semibold' : 'text-slate-300')}>
                  {row[col.key] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const POSITION_COLS = [
  { key: 'batting_position', label: 'Position' },
  { key: 'innings', label: 'Inns' },
  { key: 'total_runs', label: 'Runs', accent: true },
  { key: 'high_score', label: 'HS' },
  { key: 'average', label: 'Ave' },
  { key: 'strike_rate', label: 'SR' },
  { key: 'fifties', label: '50s' },
  { key: 'hundreds', label: '100s' },
]

const GRADE_COLS = [
  { key: 'grade_name', label: 'Grade' },
  { key: 'innings', label: 'Inns' },
  { key: 'total_runs', label: 'Runs', accent: true },
  { key: 'high_score', label: 'HS' },
  { key: 'average', label: 'Ave' },
  { key: 'strike_rate', label: 'SR' },
  { key: 'fifties', label: '50s' },
  { key: 'hundreds', label: '100s' },
]

const PARTNERSHIP_COLS = [
  { key: 'game_date_fmt', label: 'Date' },
  { key: 'grade_name', label: 'Grade' },
  { key: 'wicket_number', label: 'Wkt' },
  { key: 'partner_name', label: 'Partner' },
  { key: 'runs', label: 'Partnership', accent: true },
  { key: 'player_runs', label: 'My Runs' },
  { key: 'balls', label: 'Balls' },
]

function MilestoneTimeline({ data }) {
  if (!data?.length) return <p className="text-slate-500 text-sm px-4 py-4">No milestones recorded yet</p>

  const grouped = data.reduce((acc, m) => {
    const key = m.milestone_type
    if (!acc[key]) acc[key] = []
    acc[key].push(m)
    return acc
  }, {})

  const typeLabels = { runs: 'Runs', wickets: 'Wickets', matches: 'Matches', catches: 'Catches' }

  return (
    <div className="px-4 py-4 space-y-6">
      {Object.entries(grouped).map(([type, items]) => (
        <div key={type}>
          <h4 className="display-heading text-sm text-slate-400 mb-3 uppercase">
            {typeLabels[type] || type}
          </h4>
          <div className="flex flex-wrap gap-2">
            {items.map((m, i) => (
              <div key={i} className="flex items-center gap-2 bg-navy-800 border border-navy-700 rounded-lg px-3 py-2">
                <span className="text-accent stat-number font-bold text-lg">
                  {m.milestone_value.toLocaleString()}
                </span>
                <div className="text-xs text-slate-400">
                  {m.detail && <div>{m.detail}</div>}
                  {m.game_date && <div className="text-slate-600">{m.game_date}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function PlayerProfile() {
  const { playerId } = useParams()
  const [tab, setTab] = useState('batting')
  const [seasonId, setSeasonId] = useState(null)
  const [seasons, setSeasons] = useState([])
  const { data, loading, error } = usePlayerStats(playerId, { seasonId })

  const [dismissals, setDismissals] = useState(null)
  const [byPosition, setByPosition] = useState(null)
  const [byGrade, setByGrade] = useState(null)
  const [seasonStats, setSeasonStats] = useState(null)
  const [milestones, setMilestones] = useState(null)
  const [partnerships, setPartnerships] = useState(null)

  useEffect(() => {
    if (!data?.player?.organisation_id) return
    api.getOrgSeasons(data.player.organisation_id)
      .then(setSeasons)
      .catch(() => {})
  }, [data?.player?.organisation_id])

  const loadTabData = useCallback((t) => {
    if (t === 'analysis') {
      if (!dismissals) api.getPlayerDismissals(playerId).then(setDismissals).catch(() => setDismissals([]))
      if (!byPosition) api.getPlayerByPosition(playerId).then(setByPosition).catch(() => setByPosition([]))
      if (!byGrade) api.getPlayerByGrade(playerId).then(setByGrade).catch(() => setByGrade([]))
      if (!seasonStats) api.getPlayerSeasons(playerId).then(setSeasonStats).catch(() => setSeasonStats([]))
    } else if (t === 'milestones') {
      if (!milestones) api.getPlayerMilestones(playerId).then(setMilestones).catch(() => setMilestones([]))
    } else if (t === 'partnerships') {
      if (!partnerships) {
        api.getPlayerPartnerships(playerId).then(rows => {
          setPartnerships(rows.map(r => ({
            ...r,
            game_date_fmt: r.played_at || '—',
          })))
        }).catch(() => setPartnerships([]))
      }
    }
  }, [playerId, dismissals, byPosition, byGrade, seasonStats, milestones, partnerships])

  const handleTabChange = (t) => {
    setTab(t)
    loadTabData(t)
  }

  if (loading) return <LoadingSpinner message="Loading player stats…" />
  if (error) return <div className="max-w-7xl mx-auto px-4 py-16 text-red-400">Error: {error}</div>
  if (!data) return null

  const { player, career_batting: cb, career_bowling: cbw, career_fielding: cf, batting_innings, bowling_spells } = data

  const badgeMilestones = []
  if (cb?.hundreds > 0) badgeMilestones.push(`${cb.hundreds} ${cb.hundreds === 1 ? 'century' : 'centuries'}`)
  if (cb?.fifties > 0) badgeMilestones.push(`${cb.fifties} ${cb.fifties === 1 ? 'fifty' : 'fifties'}`)
  if (cbw?.total_wickets >= 5) badgeMilestones.push(`${cbw.total_wickets} career wickets`)
  if (cbw?.best_figures_wickets >= 5) badgeMilestones.push(`${cbw.best_figures_wickets}-wicket haul`)

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Player header */}
      <div className="mb-8">
        <div className="accent-bar mb-4" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="display-heading text-5xl md:text-6xl text-white leading-none">
              {player.name.toUpperCase()}
            </h1>
            {badgeMilestones.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {badgeMilestones.map(m => (
                  <span key={m} className="badge bg-accent/10 text-accent">{m}</span>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            {seasons.length > 0 && (
              <select
                value={seasonId || ''}
                onChange={e => setSeasonId(e.target.value || null)}
                className="bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-accent"
              >
                <option value="">Career</option>
                {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            )}
            <Link to={`/players/${playerId}/share`} className="btn-ghost border border-navy-600 text-xs">
              Share ↗
            </Link>
            {!player.claimed && (
              <button
                onClick={() => api.claimPlayer(playerId)}
                className="btn-primary text-xs"
              >
                Claim Profile
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Career summary bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-10">
        <StatCard label="Innings" value={cb?.innings ?? '—'} />
        <StatCard label="Runs" value={cb?.total_runs ?? '—'} accent />
        <StatCard label="Average" value={cb?.average ?? '—'} />
        <StatCard label="High Score" value={cb?.high_score != null ? cb.high_score : '—'} />
        <StatCard label="Strike Rate" value={cb?.strike_rate ?? '—'} />
        <StatCard label="Wickets" value={cbw?.total_wickets ?? '—'} />
        <StatCard label="Economy" value={cbw?.economy ?? '—'} />
      </div>

      {/* Batting form charts */}
      {batting_innings && batting_innings.length > 0 && (
        <div className="grid md:grid-cols-2 gap-6 mb-10">
          <div className="card p-5">
            <h3 className="display-heading text-lg text-white mb-4">FORM (LAST 10 INNINGS)</h3>
            <TrendChart innings={batting_innings} />
          </div>
          <div className="card p-5">
            <h3 className="display-heading text-lg text-white mb-4">RUNS BY INNINGS</h3>
            <RunsChart innings={batting_innings} />
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 mb-4 border-b border-navy-700">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => handleTabChange(t)}
            className={clsx(
              'px-4 py-2.5 text-sm font-semibold uppercase tracking-wider transition-colors border-b-2 -mb-px',
              tab === t
                ? 'text-accent border-accent'
                : 'text-slate-500 border-transparent hover:text-white'
            )}
          >
            {t}
          </button>
        ))}
        {cf && (
          <div className="ml-auto flex items-center gap-4 pb-2 text-sm text-slate-400">
            <span>Catches: <strong className="text-white stat-number">{cf.total_catches ?? 0}</strong></span>
            <span>Run outs: <strong className="text-white stat-number">{cf.total_run_outs ?? 0}</strong></span>
            {cf.total_stumpings > 0 && <span>Stumpings: <strong className="text-white stat-number">{cf.total_stumpings}</strong></span>}
          </div>
        )}
      </div>

      {/* Tab content */}
      <div className="card overflow-hidden">
        {tab === 'batting' && (
          <>
            <div className="px-5 py-4 border-b border-navy-700">
              <h3 className="display-heading text-lg text-white">
                BATTING INNINGS
                <span className="text-slate-500 text-sm font-sans ml-2 normal-case font-normal">
                  {batting_innings?.length ?? 0} innings
                </span>
              </h3>
            </div>
            <BattingTable innings={batting_innings ?? []} />
          </>
        )}

        {tab === 'bowling' && (
          <>
            <div className="px-5 py-4 border-b border-navy-700">
              <h3 className="display-heading text-lg text-white">
                BOWLING SPELLS
                <span className="text-slate-500 text-sm font-sans ml-2 normal-case font-normal">
                  {bowling_spells?.length ?? 0} spells
                </span>
              </h3>
            </div>
            <BowlingTable spells={bowling_spells ?? []} />
          </>
        )}

        {tab === 'analysis' && (
          <div className="p-5 space-y-8">
            {/* Dismissal breakdown */}
            <div>
              <h3 className="display-heading text-lg text-white mb-4">DISMISSAL BREAKDOWN</h3>
              {dismissals === null
                ? <p className="text-slate-500 text-sm">Loading…</p>
                : (
                  <div className="grid md:grid-cols-2 gap-6 items-start">
                    <DismissalChart data={dismissals} />
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-navy-700">
                            <th className="px-3 py-2 text-left text-xs uppercase tracking-wider text-slate-500">Type</th>
                            <th className="px-3 py-2 text-right text-xs uppercase tracking-wider text-slate-500">Count</th>
                            <th className="px-3 py-2 text-right text-xs uppercase tracking-wider text-slate-500">%</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dismissals.map((d, i) => {
                            const total = dismissals.reduce((s, x) => s + x.count, 0)
                            return (
                              <tr key={i} className="border-b border-navy-700/50">
                                <td className="px-3 py-2 text-slate-300 capitalize">{d.dismissal_type}</td>
                                <td className="px-3 py-2 text-right stat-number text-white">{d.count}</td>
                                <td className="px-3 py-2 text-right text-slate-400">
                                  {total > 0 ? `${((d.count / total) * 100).toFixed(1)}%` : '—'}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )
              }
            </div>

            {/* Season by season */}
            <div>
              <h3 className="display-heading text-lg text-white mb-4">SEASON BY SEASON</h3>
              {seasonStats === null
                ? <p className="text-slate-500 text-sm">Loading…</p>
                : <SeasonChart data={seasonStats} />
              }
            </div>

            {/* Batting by position */}
            <div>
              <h3 className="display-heading text-lg text-white mb-4">BATTING BY POSITION</h3>
              {byPosition === null
                ? <p className="text-slate-500 text-sm">Loading…</p>
                : <StatsTable rows={byPosition} columns={POSITION_COLS} />
              }
            </div>

            {/* Batting by grade */}
            <div>
              <h3 className="display-heading text-lg text-white mb-4">BATTING BY GRADE</h3>
              {byGrade === null
                ? <p className="text-slate-500 text-sm">Loading…</p>
                : <StatsTable rows={byGrade} columns={GRADE_COLS} />
              }
            </div>
          </div>
        )}

        {tab === 'milestones' && (
          <>
            <div className="px-5 py-4 border-b border-navy-700">
              <h3 className="display-heading text-lg text-white">CAREER MILESTONES</h3>
            </div>
            {milestones === null
              ? <p className="text-slate-500 text-sm px-5 py-4">Loading…</p>
              : <MilestoneTimeline data={milestones} />
            }
          </>
        )}

        {tab === 'partnerships' && (
          <>
            <div className="px-5 py-4 border-b border-navy-700">
              <h3 className="display-heading text-lg text-white">
                PARTNERSHIPS
                <span className="text-slate-500 text-sm font-sans ml-2 normal-case font-normal">
                  {partnerships?.length ?? ''} recorded
                </span>
              </h3>
            </div>
            {partnerships === null
              ? <p className="text-slate-500 text-sm px-5 py-4">Loading…</p>
              : <StatsTable rows={partnerships} columns={PARTNERSHIP_COLS} />
            }
          </>
        )}
      </div>
    </div>
  )
}
