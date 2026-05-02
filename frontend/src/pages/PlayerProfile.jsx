import { useParams } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { usePlayerStats } from '../hooks/usePlayerStats'
import StatCard from '../components/StatCard'
import BattingTable from '../components/BattingTable'
import BowlingTable from '../components/BowlingTable'
import TrendChart from '../components/TrendChart'
import RunsChart from '../components/RunsChart'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

const TABS = ['batting', 'bowling']

export default function PlayerProfile() {
  const { playerId } = useParams()
  const [tab, setTab] = useState('batting')
  const [seasonId, setSeasonId] = useState(null)
  const [seasons, setSeasons] = useState([])
  const { data, loading, error } = usePlayerStats(playerId, { seasonId })

  useEffect(() => {
    if (!data?.player?.organisation_id) return
    api.getOrgSeasons(data.player.organisation_id)
      .then(setSeasons)
      .catch(() => {})
  }, [data?.player?.organisation_id])

  if (loading) return <LoadingSpinner message="Loading player stats…" />
  if (error) return <div className="max-w-7xl mx-auto px-4 py-16 text-red-400">Error: {error}</div>
  if (!data) return null

  const { player, career_batting: cb, career_bowling: cbw, career_fielding: cf, batting_innings, bowling_spells } = data

  const milestones = []
  if (cb?.hundreds > 0) milestones.push(`${cb.hundreds} ${cb.hundreds === 1 ? 'century' : 'centuries'}`)
  if (cb?.fifties > 0) milestones.push(`${cb.fifties} ${cb.fifties === 1 ? 'fifty' : 'fifties'}`)
  if (cbw?.total_wickets >= 5) milestones.push(`${cbw.total_wickets} career wickets`)
  if (cbw?.best_figures_wickets >= 5) milestones.push(`${cbw.best_figures_wickets}-wicket haul`)

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
            {milestones.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {milestones.map(m => (
                  <span key={m} className="badge bg-accent/10 text-accent">{m}</span>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            {/* Season filter */}
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
        <StatCard label="High Score" value={cb?.high_score != null ? `${cb.high_score}${cb.high_score >= 100 ? '' : ''}` : '—'} />
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
      <div className="flex gap-1 mb-4 border-b border-navy-700">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
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

      {/* Innings tables */}
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
      </div>
    </div>
  )
}
