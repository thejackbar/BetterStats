import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, Link, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

// ── tiny recharts wrapper ─────────────────────────────────────────────────────
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

function SeasonChart({ data }) {
  if (!data?.length) return null
  const chartData = [...data]
    .sort((a, b) => (a.season_year ?? 0) - (b.season_year ?? 0))
    .map(s => ({
      name: s.season_name?.replace('Summer ', '') ?? s.season_year ?? '?',
      Runs: s.total_runs ?? 0,
      Wickets: s.total_wickets ?? 0,
    }))
  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={chartData} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
        <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} axisLine={false} />
        <YAxis yAxisId="runs" tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} axisLine={false} />
        <YAxis yAxisId="wkts" orientation="right" tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} axisLine={false} />
        <Tooltip
          contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 12 }}
          labelStyle={{ color: '#94a3b8' }}
          itemStyle={{ color: '#e2e8f0' }}
        />
        <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
        <Bar yAxisId="runs" dataKey="Runs" fill="#22d3a5" radius={[2, 2, 0, 0]} maxBarSize={24} />
        <Bar yAxisId="wkts" dataKey="Wickets" fill="#3b82f6" radius={[2, 2, 0, 0]} maxBarSize={24} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function SeasonBattingTable({ data }) {
  if (!data?.length) return <p className="text-slate-600 text-sm px-5 py-4">No season data.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header">Season</th>
            <th className="table-header text-right">Mat</th>
            <th className="table-header text-right">Inn</th>
            <th className="table-header text-right">Runs</th>
            <th className="table-header text-right">Avg</th>
            <th className="table-header text-right">HS</th>
            <th className="table-header text-right">SR</th>
            <th className="table-header text-right">50s</th>
            <th className="table-header text-right">100s</th>
            <th className="table-header text-right hidden sm:table-cell">6s</th>
            <th className="table-header text-right hidden sm:table-cell">4s</th>
          </tr>
        </thead>
        <tbody>
          {[...data].sort((a, b) => (b.season_year ?? 0) - (a.season_year ?? 0)).map((s, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell text-white">{s.season_name}</td>
              <td className="table-cell stat-number text-right text-slate-400">{s.matches ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{s.batting_innings ?? '—'}</td>
              <td className="table-cell stat-number text-right text-accent font-bold">{s.total_runs ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{s.batting_average ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{s.high_score ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-500">{s.strike_rate ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{s.fifties ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{s.hundreds ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-600 hidden sm:table-cell">{s.sixes ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-600 hidden sm:table-cell">{s.fours ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SeasonBowlingTable({ data }) {
  const bowlingSeasons = data?.filter(s => (s.total_wickets ?? 0) > 0 || (s.overs_bowled ?? 0) > 0)
  if (!bowlingSeasons?.length) return <p className="text-slate-600 text-sm px-5 py-4">No bowling data recorded.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header">Season</th>
            <th className="table-header text-right">Mat</th>
            <th className="table-header text-right">Overs</th>
            <th className="table-header text-right">Wkts</th>
            <th className="table-header text-right">Avg</th>
            <th className="table-header text-right">Econ</th>
            <th className="table-header text-right">Best</th>
            <th className="table-header text-right">5W</th>
          </tr>
        </thead>
        <tbody>
          {[...bowlingSeasons].sort((a, b) => (b.season_year ?? 0) - (a.season_year ?? 0)).map((s, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell text-white">{s.season_name}</td>
              <td className="table-cell stat-number text-right text-slate-400">{s.matches ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{s.overs_bowled ?? '—'}</td>
              <td className="table-cell stat-number text-right text-accent font-bold">{s.total_wickets ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{s.bowling_average ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{s.economy ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">
                {s.best_bowling_wickets != null ? `${s.best_bowling_wickets}/${s.best_bowling_runs ?? '?'}` : '—'}
              </td>
              <td className="table-cell stat-number text-right text-slate-400">{s.five_wicket_hauls ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function PlayerProfile() {
  const { playerId } = useParams()
  const [searchParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('batting')
  const [seasonId, setSeasonId] = useState(null)
  const [seasons, setSeasons] = useState([])
  const [activity, setActivity] = useState({})
  const [upcomingMilestones, setUpcomingMilestones] = useState([])
  const [milestones, setMilestones] = useState(null)
  const [seasonStats, setSeasonStats] = useState(null)
  const [achievementsLoaded, setAchievementsLoaded] = useState(false)
  const [headerAchievements, setHeaderAchievements] = useState([])
  const [partnerships, setPartnerships] = useState(null)
  const [dismissals, setDismissals] = useState(null)
  const [byGrade, setByGrade] = useState(null)
  const [byPosition, setByPosition] = useState(null)

  // Load season stats and activity eagerly on mount
  useEffect(() => {
    if (!playerId) return
    api.getPlayerSeasons(playerId).then(setSeasonStats).catch(() => setSeasonStats([]))
    api.getPlayerActivity(playerId).then(setActivity).catch(() => setActivity({}))
    api.getPlayerUpcomingMilestones(playerId).then(setUpcomingMilestones).catch(() => setUpcomingMilestones([]))
  }, [playerId])

  useEffect(() => {
    if (!data?.player?.organisation_id) return
    api.getOrgSeasons(data.player.organisation_id).then(setSeasons).catch(() => {})
    sessionStorage.setItem('bs_last_org_id', data.player.organisation_id)
    window.dispatchEvent(new CustomEvent('bs_org_changed'))
    // Load achievements for header display
    api.listAchievements(data.player.organisation_id, { playerId })
      .then(list => setHeaderAchievements(list || []))
      .catch(() => {})
  }, [data?.player?.organisation_id, playerId])

  const handleTabChange = useCallback((t) => {
    setTab(t)
    if (t === 'milestones' && milestones === null) {
      api.getPlayerMilestones(playerId).then(setMilestones).catch(() => setMilestones([]))
    }
    if (t === 'achievements') setAchievementsLoaded(true)
    if (t === 'analysis' && partnerships === null) {
      api.getPlayerPartnerships(playerId).then(setPartnerships).catch(() => setPartnerships([]))
      api.getPlayerDismissals(playerId).then(setDismissals).catch(() => setDismissals([]))
      api.getPlayerByGrade(playerId).then(setByGrade).catch(() => setByGrade([]))
      api.getPlayerByPosition(playerId).then(setByPosition).catch(() => setByPosition([]))
    }
  }, [playerId, milestones, partnerships])

  // Hooks must run before any early returns — derive display stats for stat cards
  const rawData = data
  const cb = rawData?.career_batting
  const cbw = rawData?.career_bowling
  const cf = rawData?.career_fielding
  const player = rawData?.player

  const displayBatting = useMemo(() => {
    if (!seasonId || !seasonStats?.length) return cb
    const s = seasonStats.find(r => r.season_id === seasonId)
    if (!s) return cb
    return { matches: s.matches, innings: s.batting_innings, total_runs: s.total_runs, average: s.batting_average, high_score: s.high_score, strike_rate: s.strike_rate, hundreds: s.hundreds, fifties: s.fifties }
  }, [seasonId, seasonStats, cb])

  const displayBowling = useMemo(() => {
    if (!seasonId || !seasonStats?.length) return cbw
    const s = seasonStats.find(r => r.season_id === seasonId)
    if (!s) return cbw
    return { total_wickets: s.total_wickets, economy: s.economy, best_bowling_figures: s.best_bowling_figures, best_figures_wickets: s.best_bowling_wickets }
  }, [seasonId, seasonStats, cbw])

  useEffect(() => {
    if (!playerId) return
    setLoading(true)
    api.getPlayerStats(playerId)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [playerId])

  if (loading) return <LoadingSpinner message="Loading player stats…" />
  if (error) return <div className="max-w-7xl mx-auto px-4 py-16 text-red-400">Error: {error}</div>
  if (!data) return null

  const { career_batting: _cb, career_bowling: _cbw, career_fielding: _cf } = data

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
              {(player.display_name || player.name).toUpperCase()}
            </h1>
            {badgeMilestones.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {badgeMilestones.map((b, i) => (
                  <span key={i} className="badge-accent">{b}</span>
                ))}
              </div>
            )}
            {headerAchievements.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {headerAchievements.slice(0, 3).map((a, i) => (
                  <span key={i} className="badge-secondary text-xs uppercase tracking-wide">{a.title}</span>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              {seasons.length > 0 && (
                <select
                  value={seasonId || ''}
                  onChange={e => setSeasonId(e.target.value || null)}
                  className="bg-navy-800 border border-navy-600 text-slate-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-accent"
                >
                  <option value="">Career</option>
                  {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              )}
              <a
                href={`/players/${playerId}/share`}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-ghost text-sm"
              >
                Share ↗
              </a>
              <button className="btn-secondary text-sm">Claim Profile</button>
            </div>
          </div>
        </div>

        {/* Upcoming milestones */}
        {upcomingMilestones.length > 0 && (
          <div className="mt-4 space-y-2">
            <p className="section-label">CHASING</p>
            {upcomingMilestones.slice(0, 2).map((m, i) => (
              <div key={i} className="bg-navy-800/50 border border-navy-700 rounded-lg px-4 py-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-slate-300 text-sm">
                    <span className="text-accent font-mono">&#9998;</span> {m.label}
                  </span>
                  <span className="text-slate-500 text-xs">{m.remaining} to go</span>
                </div>
                <div className="w-full bg-navy-700 rounded-full h-1.5">
                  <div
                    className="bg-accent h-1.5 rounded-full transition-all"
                    style={{ width: `${Math.min(100, m.pct)}%` }}
                  />
                </div>
                <div className="flex justify-between mt-1">
                  <span className="text-slate-600 text-xs">{m.current?.toLocaleString()}</span>
                  <span className="text-slate-500 text-xs">{m.pct}%</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Stat cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 mt-6">
          {[
            { label: 'Matches', value: displayBatting?.matches ?? cb?.matches },
            { label: 'Innings', value: displayBatting?.innings ?? cb?.innings },
            { label: 'Runs', value: (displayBatting?.total_runs ?? cb?.total_runs)?.toLocaleString(), accent: true },
            { label: 'Average', value: displayBatting?.average ?? cb?.average },
            { label: 'High Score', value: displayBatting?.high_score ?? cb?.high_score },
            { label: 'Wickets', value: displayBowling?.total_wickets ?? cbw?.total_wickets },
            { label: 'Economy', value: displayBowling?.economy ?? cbw?.economy },
            { label: 'Best Spell', value: (displayBowling?.best_bowling_figures ?? cbw?.best_bowling_figures) },
          ].map(({ label, value, accent }) => (
            <div key={label} className="bg-navy-800/50 border border-navy-700 rounded-lg p-3 text-center">
              <p className="section-label text-xs mb-1">{label}</p>
              <p className={clsx('stat-number text-2xl font-bold', accent ? 'text-accent' : 'text-white')}>
                {value ?? '—'}
              </p>
            </div>
          ))}
        </div>

        {/* Fielding summary inline */}
        {(cf?.total_catches > 0 || cf?.run_outs > 0 || cf?.stumpings > 0) && (
          <p className="text-slate-500 text-sm mt-3">
            Catches: <span className="text-slate-300">{cf.total_catches ?? 0}</span>
            {cf.run_outs > 0 && <> Run outs: <span className="text-slate-300">{cf.run_outs}</span></>}
            {cf.stumpings > 0 && <> Stumpings: <span className="text-slate-300">{cf.stumpings}</span></>}
          </p>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-navy-700">
        {['batting', 'bowling', 'analysis', 'milestones', 'achievements'].map(t => (
          <button
            key={t}
            onClick={() => handleTabChange(t)}
            className={clsx(
              'px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px',
              tab === t ? 'text-accent border-accent' : 'text-slate-400 border-transparent hover:text-white'
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="card overflow-hidden">
        {tab === 'batting' && (
          <>
            <div className="px-5 py-4 border-b border-navy-700 flex items-center justify-between">
              <h3 className="display-heading text-lg text-white">BATTING BY SEASON</h3>
              <span className="section-label">{seasonStats?.length ?? 0} seasons</span>
            </div>
            {seasonStats === null
              ? <div className="p-5"><LoadingSpinner size="sm" /></div>
              : <SeasonBattingTable data={seasonStats} />
            }
            {/* Form charts if we have recent data */}
            {seasonStats !== null && seasonStats.length > 0 && (
              <div className="px-5 pt-4 pb-5 border-t border-navy-700">
                <h4 className="display-heading text-sm text-slate-400 mb-4">RUNS TREND</h4>
                <SeasonChart data={seasonStats} />
              </div>
            )}
          </>
        )}

        {tab === 'bowling' && (
          <>
            <div className="px-5 py-4 border-b border-navy-700 flex items-center justify-between">
              <h3 className="display-heading text-lg text-white">BOWLING BY SEASON</h3>
            </div>
            {seasonStats === null
              ? <div className="p-5"><LoadingSpinner size="sm" /></div>
              : <SeasonBowlingTable data={seasonStats} />
            }
          </>
        )}

        {tab === 'analysis' && (
          <div className="p-5 space-y-8">
            <div>
              <h3 className="display-heading text-lg text-white mb-4">SEASON BY SEASON</h3>
              {seasonStats === null
                ? <LoadingSpinner size="sm" />
                : <SeasonChart data={seasonStats} />
              }
            </div>
            {seasonStats !== null && seasonStats.length > 0 && (
              <div>
                <h3 className="display-heading text-lg text-white mb-4">FULL SEASON HISTORY</h3>
                <SeasonBattingTable data={seasonStats} />
              </div>
            )}
            {partnerships === null ? (
              <LoadingSpinner size="sm" />
            ) : partnerships.length === 0 ? null : (
              <div>
                <h3 className="display-heading text-lg text-white mb-4">TOP PARTNERSHIPS</h3>
                <div className="card overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-navy-700">
                        <th className="table-header">Partner</th>
                        <th className="table-header text-right">Runs</th>
                        <th className="table-header text-right">Wkt</th>
                        <th className="table-header text-right hidden sm:table-cell">Match</th>
                      </tr>
                    </thead>
                    <tbody>
                      {partnerships.slice(0, 20).map((p, i) => {
                        const partnerId = p.batter1_id === playerId ? p.batter2_id : p.batter1_id
                        const partnerName = p.batter1_id === playerId ? p.batter2_name : p.batter1_name
                        const myRuns = p.batter1_id === playerId ? p.batter1_runs : p.batter2_runs
                        return (
                          <tr key={i} className="table-row">
                            <td className="table-cell">
                              {partnerId
                                ? <Link to={`/players/${partnerId}`} className="text-white hover:text-accent transition-colors">{partnerName ?? '—'}</Link>
                                : <span className="text-slate-400">{partnerName ?? '—'}</span>}
                              {myRuns != null && <span className="text-slate-600 text-xs ml-1.5">({myRuns})</span>}
                            </td>
                            <td className="table-cell stat-number text-right font-bold text-accent">{p.runs ?? '—'}</td>
                            <td className="table-cell stat-number text-right text-slate-400">{p.wicket_number ?? '—'}</td>
                            <td className="table-cell text-right text-slate-600 text-xs hidden sm:table-cell">
                              {p.home_team && p.away_team ? `${p.home_team} v ${p.away_team}` : '—'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {dismissals !== null && byGrade !== null && byPosition !== null &&
              dismissals.length === 0 && byGrade.length === 0 && byPosition.length === 0 && (
              <p className="text-slate-600 text-sm italic">
                Game-level data not yet synced — dismissal breakdown, position, and grade splits will appear after the next admin sync.
              </p>
            )}

            {dismissals !== null && dismissals.length > 0 && (() => {
              const total = dismissals.reduce((s, d) => s + Number(d.count), 0)
              return (
                <div>
                  <h3 className="display-heading text-lg text-white mb-4">DISMISSAL BREAKDOWN</h3>
                  <div className="card p-5 space-y-2">
                    {dismissals.map((d, i) => {
                      const pct = total > 0 ? Math.round(Number(d.count) / total * 100) : 0
                      return (
                        <div key={i} className="flex items-center gap-3">
                          <span className="text-slate-400 text-sm capitalize w-28 shrink-0">{d.dismissal_type}</span>
                          <div className="flex-1 bg-navy-800 rounded-full h-2">
                            <div className="bg-accent h-2 rounded-full" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="stat-number text-white text-sm w-6 text-right">{d.count}</span>
                          <span className="text-slate-600 text-xs w-9 text-right">{pct}%</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })()}

            {byGrade !== null && byGrade.length > 1 && (
              <div>
                <h3 className="display-heading text-lg text-white mb-4">BATTING BY GRADE</h3>
                <div className="card overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-navy-700">
                        <th className="table-header">Grade</th>
                        <th className="table-header text-right">Inn</th>
                        <th className="table-header text-right">Runs</th>
                        <th className="table-header text-right">Avg</th>
                        <th className="table-header text-right">HS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {byGrade.map((r, i) => (
                        <tr key={i} className="table-row">
                          <td className="table-cell text-white">{r.grade_name}</td>
                          <td className="table-cell stat-number text-right text-slate-400">{r.innings}</td>
                          <td className="table-cell stat-number text-right text-accent font-bold">{r.runs}</td>
                          <td className="table-cell stat-number text-right text-slate-300">{r.average ?? '—'}</td>
                          <td className="table-cell stat-number text-right text-slate-300">{r.high_score ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {byPosition !== null && byPosition.length > 0 && (
              <div>
                <h3 className="display-heading text-lg text-white mb-4">BATTING BY POSITION</h3>
                <div className="card overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-navy-700">
                        <th className="table-header">Position</th>
                        <th className="table-header text-right">Inn</th>
                        <th className="table-header text-right">Runs</th>
                        <th className="table-header text-right">Avg</th>
                        <th className="table-header text-right">HS</th>
                        <th className="table-header text-right hidden sm:table-cell">SR</th>
                      </tr>
                    </thead>
                    <tbody>
                      {byPosition.map((r, i) => (
                        <tr key={i} className="table-row">
                          <td className="table-cell stat-number text-white">#{r.batting_position}</td>
                          <td className="table-cell stat-number text-right text-slate-400">{r.innings}</td>
                          <td className="table-cell stat-number text-right text-accent font-bold">{r.runs}</td>
                          <td className="table-cell stat-number text-right text-slate-300">{r.average ?? '—'}</td>
                          <td className="table-cell stat-number text-right text-slate-300">{r.high_score ?? '—'}</td>
                          <td className="table-cell stat-number text-right text-slate-500 hidden sm:table-cell">{r.avg_strike_rate ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {tab === 'milestones' && (
          <>
            <div className="px-5 py-4 border-b border-navy-700">
              <h3 className="display-heading text-lg text-white">CAREER MILESTONES</h3>
            </div>
            {milestones === null
              ? <div className="p-5"><LoadingSpinner size="sm" /></div>
              : milestones.length === 0
                ? <p className="text-slate-600 text-sm px-5 py-4">No milestones recorded yet.</p>
                : (
                  <div className="divide-y divide-navy-800">
                    {milestones.map((m, i) => (
                      <div key={i} className="px-5 py-3 flex items-center justify-between">
                        <div>
                          <p className="text-white text-sm font-medium">{m.label}</p>
                          {m.season_name && <p className="text-slate-500 text-xs mt-0.5">{m.season_name}</p>}
                        </div>
                        <span className="stat-number text-accent font-bold text-lg">{m.value?.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )
            }
          </>
        )}

        {tab === 'achievements' && (
          <AchievementsTab playerId={playerId} orgId={data?.player?.organisation_id} loaded={achievementsLoaded} />
        )}
      </div>
    </div>
  )
}

function AchievementsTab({ playerId, orgId, loaded }) {
  const [achievements, setAchievements] = useState(null)

  useEffect(() => {
    if (!loaded || !orgId) return
    api.listAchievements(orgId, { playerId })
      .then(setAchievements)
      .catch(() => setAchievements([]))
  }, [loaded, orgId, playerId])

  if (!loaded || achievements === null) return <div className="p-5"><LoadingSpinner size="sm" /></div>
  if (!achievements.length) return <p className="text-slate-600 text-sm px-5 py-4">No achievements recorded.</p>

  return (
    <div className="divide-y divide-navy-800">
      {achievements.map((a, i) => (
        <div key={i} className="px-5 py-4 flex items-start gap-4">
          {a.icon_url && (
            <img src={a.icon_url} alt="" className="w-10 h-10 rounded object-cover shrink-0" />
          )}
          <div className="flex-1 min-w-0">
            <p className="text-white font-medium text-sm">{a.title}</p>
            {a.description && <p className="text-slate-500 text-xs mt-0.5 leading-relaxed">{a.description}</p>}
            {a.awarded_at && (
              <p className="text-slate-600 text-xs mt-1">
                {new Date(a.awarded_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })}
              </p>
            )}
          </div>
          {a.season_name && (
            <span className="text-slate-600 text-xs shrink-0">{a.season_name}</span>
          )}
        </div>
      ))}
    </div>
  )
}
