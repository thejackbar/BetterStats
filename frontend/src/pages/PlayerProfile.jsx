import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

const TABS = ['batting', 'bowling', 'analysis', 'milestones', 'partnerships']

function usePlayerStats(playerId, { seasonId } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!playerId) return
    setLoading(true)
    api.getPlayerStats(playerId, { seasonId })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [playerId, seasonId])

  return { data, loading, error }
}

function StatCard({ label, value, accent, sub }) {
  return (
    <div className={clsx('card p-4 text-center', accent && 'border-accent/40')}>
      <div className={clsx('stat-number text-2xl font-bold', accent ? 'text-accent' : 'text-white')}>
        {value ?? '—'}
      </div>
      <div className="text-xs text-slate-500 mt-1 uppercase tracking-wider">{label}</div>
      {sub && <div className="text-xs text-slate-600 mt-0.5">{sub}</div>}
    </div>
  )
}

function SectionTitle({ children }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div className="accent-bar" />
      <h3 className="display-heading text-lg text-slate-300 uppercase tracking-wider">{children}</h3>
    </div>
  )
}

function DataTable({ columns, rows }) {
  if (!rows?.length) return <p className="text-slate-500 text-sm px-4 py-4">No data available</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-navy-700">
            {columns.map(col => (
              <th key={col.key} className="table-header text-right first:text-left px-4 py-2.5">
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
  { key: 'innings', label: 'Innings' },
  { key: 'runs', label: 'Runs', accent: true },
  { key: 'average', label: 'Average' },
  { key: 'strike_rate', label: 'SR' },
  { key: 'high_score', label: 'HS' },
]

const GRADE_COLS = [
  { key: 'grade_name', label: 'Grade' },
  { key: 'innings', label: 'Innings' },
  { key: 'runs', label: 'Runs', accent: true },
  { key: 'average', label: 'Average' },
  { key: 'wickets', label: 'Wkts' },
  { key: 'bowling_average', label: 'Bowl Avg' },
]

const SEASON_BAT_COLS = [
  { key: 'season_name', label: 'Season' },
  { key: 'matches', label: 'M' },
  { key: 'batting_innings', label: 'Inn' },
  { key: 'total_runs', label: 'Runs', accent: true },
  { key: 'high_score', label: 'HS' },
  { key: 'batting_average', label: 'Avg' },
  { key: 'strike_rate', label: 'SR' },
  { key: 'fifties', label: '50s' },
  { key: 'hundreds', label: '100s' },
]

const SEASON_BOWL_COLS = [
  { key: 'season_name', label: 'Season' },
  { key: 'total_wickets', label: 'Wkts', accent: true },
  { key: 'total_overs', label: 'Overs' },
  { key: 'economy', label: 'Econ' },
  { key: 'bowling_average', label: 'Avg' },
  { key: 'best_bowling_figures', label: 'Best' },
  { key: 'five_fors', label: '5W' },
]

const PARTNERSHIP_COLS = [
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

  const TYPE_ORDER = ['runs', 'wickets', 'matches', 'catches']
  const typeLabels = { runs: 'Runs', wickets: 'Wickets', matches: 'Matches', catches: 'Catches' }
  const orderedGroups = TYPE_ORDER.filter(t => grouped[t])
    .concat(Object.keys(grouped).filter(t => !TYPE_ORDER.includes(t)))
    .map(t => [t, [...grouped[t]].sort((a, b) => b.milestone_value - a.milestone_value)])

  return (
    <div className="px-4 py-4 space-y-6">
      {orderedGroups.map(([type, items]) => (
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
    if (!playerId) return
    api.getPlayerSeasons(playerId).then(setSeasons).catch(() => {})
  }, [playerId])

  const player = data?.player
  const cbat = data?.career_batting
  const cbw = data?.career_bowling
  const cfield = data?.career_fielding
  const activity = data?.activity

  const badgeMilestones = []
  if (cbat?.total_runs >= 1000) badgeMilestones.push(`${cbat.total_runs.toLocaleString()} runs`)
  if (cbw?.total_wickets >= 50) badgeMilestones.push(`${cbw.total_wickets} wickets`)
  if (cbw?.best_figures_wickets >= 5) badgeMilestones.push(`${cbw.best_figures_wickets}-wicket haul`)

  useEffect(() => {
    const t = tab
    if (t === 'analysis') {
      if (!dismissals) api.getPlayerDismissals(playerId).then(setDismissals).catch(() => setDismissals([]))
      if (!byPosition) api.getPlayerByPosition(playerId).then(setByPosition).catch(() => setByPosition([]))
      if (!byGrade) api.getPlayerByGrade(playerId).then(setByGrade).catch(() => setByGrade([]))
      if (!seasonStats) api.getPlayerSeasons(playerId).then(setSeasonStats).catch(() => setSeasonStats([]))
    } else if (t === 'milestones') {
      if (!milestones) api.getPlayerMilestones(playerId).then(setMilestones).catch(() => setMilestones([]))
    } else if (t === 'partnerships') {
      if (!partnerships) api.getPlayerPartnerships(playerId).then(setPartnerships).catch(() => setPartnerships([]))
    }
  }, [playerId, dismissals, byPosition, byGrade, seasonStats, milestones, partnerships])

  if (loading) return <LoadingSpinner message="Loading player profile…" />
  if (error) return <div className="text-red-400 p-8">{error}</div>
  if (!data) return null

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="accent-bar mb-3" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="display-heading text-4xl md:text-5xl text-white">{player?.name?.toUpperCase()}</h1>
            {badgeMilestones.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {badgeMilestones.map((b, i) => (
                  <span key={i} className="text-xs bg-accent/20 text-accent border border-accent/30 rounded-full px-2 py-0.5">{b}</span>
                ))}
              </div>
            )}
          </div>
          <div className="flex gap-2 flex-wrap">
            {player && !player.claimed && (
              <button
                onClick={() => api.claimPlayer(playerId).catch(() => {})}
                className="btn-ghost border border-accent/40 text-accent text-sm"
              >
                Claim Profile
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Upcoming milestones */}
      <div className="mb-6">
        <UpcomingMilestonesBar playerId={playerId} />
      </div>

      {/* Career summary tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <StatCard label="Career Runs" value={cbat?.total_runs?.toLocaleString()} accent />
        <StatCard label="Average" value={cbat?.average} />
        <StatCard label="Wickets" value={cbw?.total_wickets} accent />
        <StatCard label="Economy" value={cbw?.economy ?? '—'} />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-navy-700 overflow-x-auto">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              'px-4 py-2.5 text-xs uppercase tracking-widest font-medium transition-colors whitespace-nowrap',
              tab === t
                ? 'text-accent border-b-2 border-accent'
                : 'text-slate-500 hover:text-slate-300'
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Batting tab */}
      {tab === 'batting' && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <StatCard label="Innings" value={cbat?.innings} />
            <StatCard label="Highest Score" value={cbat?.high_score} />
            <StatCard label="Strike Rate" value={cbat?.strike_rate} />
            <StatCard label="Not Outs" value={cbat?.innings != null ? (cbat.innings - (cbat.innings - (cbat?.total_runs > 0 ? 1 : 0))) : null} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
            <StatCard label="50s" value={cbat?.fifties} />
            <StatCard label="100s" value={cbat?.hundreds} />
            <StatCard label="Fours" value={cbat?.total_fours} />
            <StatCard label="Sixes" value={cbat?.total_sixes} />
          </div>

          <div className="card overflow-hidden mb-4">
            <div className="px-5 py-4 border-b border-navy-700">
              <SectionTitle>Season by Season — Batting</SectionTitle>
            </div>
            {seasonStats === null
              ? <p className="text-slate-500 text-sm px-4 py-4">Select Analysis tab to load</p>
              : <DataTable columns={SEASON_BAT_COLS} rows={seasonStats} />
            }
          </div>
        </>
      )}

      {/* Bowling tab */}
      {tab === 'bowling' && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <StatCard label="Wickets" value={cbw?.total_wickets} accent />
            <StatCard label="Average" value={cbw?.average} />
            <StatCard label="Economy" value={cbw?.economy} />
            <StatCard label="Best Figures" value={cbw?.best_bowling_figures ?? (cbw?.best_figures_wickets ? `${cbw.best_figures_wickets} wkts` : '—')} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
            <StatCard label="Overs" value={cbw?.total_overs} />
            <StatCard label="Maidens" value={cbw?.total_maidens} />
            <StatCard label="Runs Conceded" value={cbw?.total_runs} />
            <StatCard label="Five-fors" value={cbw?.five_fors} />
          </div>

          <div className="card overflow-hidden mb-4">
            <div className="px-5 py-4 border-b border-navy-700">
              <SectionTitle>Season by Season — Bowling</SectionTitle>
            </div>
            {seasonStats === null
              ? <p className="text-slate-500 text-sm px-4 py-4">Select Analysis tab to load</p>
              : <DataTable columns={SEASON_BOWL_COLS} rows={seasonStats} />
            }
          </div>
        </>
      )}

      {/* Analysis tab */}
      {tab === 'analysis' && (
        <>
          <div className="card overflow-hidden mb-4">
            <div className="px-5 py-4 border-b border-navy-700">
              <SectionTitle>Season by Season — Batting</SectionTitle>
            </div>
            {!seasonStats ? <LoadingSpinner /> : <DataTable columns={SEASON_BAT_COLS} rows={seasonStats} />}
          </div>
          <div className="card overflow-hidden mb-4">
            <div className="px-5 py-4 border-b border-navy-700">
              <SectionTitle>Season by Season — Bowling</SectionTitle>
            </div>
            {!seasonStats ? <LoadingSpinner /> : <DataTable columns={SEASON_BOWL_COLS} rows={seasonStats} />}
          </div>
          <div className="card overflow-hidden mb-4">
            <div className="px-5 py-4 border-b border-navy-700">
              <SectionTitle>Batting by Position</SectionTitle>
            </div>
            {!byPosition ? <LoadingSpinner /> : <DataTable columns={POSITION_COLS} rows={byPosition} />}
          </div>
          <div className="card overflow-hidden mb-4">
            <div className="px-5 py-4 border-b border-navy-700">
              <SectionTitle>Performance by Grade</SectionTitle>
            </div>
            {!byGrade ? <LoadingSpinner /> : <DataTable columns={GRADE_COLS} rows={byGrade} />}
          </div>
        </>
      )}

      {/* Milestones tab */}
      {tab === 'milestones' && (
        <>
          <div className="card overflow-hidden">
            <div className="px-5 py-4 border-b border-navy-700">
              <SectionTitle>Career Milestones</SectionTitle>
            </div>
            {milestones === null
              ? <LoadingSpinner />
              : <MilestoneTimeline data={milestones} />
            }
          </div>
        </>
      )}

      {/* Partnerships tab */}
      {tab === 'partnerships' && (
        <>
          <div className="px-5 py-4 border-b border-navy-700"></div>
          <div className="card overflow-hidden">
            <div className="px-5 py-4 border-b border-navy-700">
              <SectionTitle>Batting Partnerships</SectionTitle>
            </div>
            {partnerships === null
              ? <LoadingSpinner />
              : <DataTable columns={PARTNERSHIP_COLS} rows={partnerships} />
            }
          </div>
        </>
      )}
    </div>
  )
}

function UpcomingMilestonesBar({ playerId }) {
  const [upcoming, setUpcoming] = useState([])

  useEffect(() => {
    api.getPlayerUpcomingMilestones(playerId).then(setUpcoming).catch(() => {})
  }, [playerId])

  if (!upcoming.length) return null

  return (
    <div className="flex flex-wrap gap-2">
      {upcoming.slice(0, 4).map((m, i) => (
        <div key={i} className="card px-3 py-2 flex items-center gap-2 border-navy-700">
          <span className="text-slate-400 text-xs uppercase tracking-wider">{m.type}</span>
          <span className="text-white stat-number text-sm font-bold">{m.target.toLocaleString()}</span>
          <span className="text-slate-500 text-xs">{m.needed} to go</span>
        </div>
      ))}
    </div>
  )
}
