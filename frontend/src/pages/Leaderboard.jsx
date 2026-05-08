import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useClubData } from '../hooks/useClubData'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import SeasonSelector from '../components/SeasonSelector'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

const MAIN_TABS = [
  { key: 'batting', label: 'Batting' },
  { key: 'bowling', label: 'Bowling' },
  { key: 'fielding', label: 'Fielding' },
]

const BATTING_SORTS = [
  { key: 'total_runs', label: 'Runs' },
  { key: 'average', label: 'Average' },
  { key: 'strike_rate', label: 'Strike Rate' },
  { key: 'high_score', label: 'High Score' },
  { key: 'fifties', label: 'Fifties' },
  { key: 'hundreds', label: 'Centuries' },
  { key: 'total_sixes', label: 'Sixes' },
  { key: 'total_fours', label: 'Fours' },
  { key: 'ducks', label: 'Ducks' },
]

const BOWLING_SORTS = [
  { key: 'total_wickets', label: 'Wickets' },
  { key: 'economy', label: 'Economy' },
  { key: 'average', label: 'Average' },
  { key: 'best_figures_wickets', label: 'Best Spell' },
  { key: 'five_fors', label: 'Five-fors' },
  { key: 'total_maidens', label: 'Maidens' },
]

function SubTabBar({ tabs, active, onSelect }) {
  return (
    <div className="flex flex-wrap gap-1 px-4 py-3 border-b border-navy-700 bg-navy-800/50">
      {tabs.map(t => (
        <button
          key={t.key}
          onClick={() => onSelect(t.key)}
          className={clsx(
            'px-3 py-1.5 text-xs font-semibold uppercase tracking-wider rounded-md transition-colors',
            active === t.key
              ? 'bg-accent text-navy-950'
              : 'text-slate-400 hover:text-white hover:bg-navy-700'
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

function BattingLeaderboard({ orgId, seasonId, gradeId, sortBy }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.battingLeaderboard(orgId, { seasonId, gradeId, sortBy, limit: 30 })
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId, sortBy])

  if (loading) return <LoadingSpinner />
  if (!rows.length) return <p className="text-slate-500 text-sm py-8 text-center">No batting data yet.</p>

  const primaryCol = sortBy || 'total_runs'

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header w-8">#</th>
            <th className="table-header">Player</th>
            <th className="table-header text-right">Inn</th>
            <th className={clsx('table-header text-right', primaryCol === 'total_runs' && 'text-accent')}>Runs</th>
            <th className={clsx('table-header text-right', primaryCol === 'average' && 'text-accent')}>Avg</th>
            <th className={clsx('table-header text-right', primaryCol === 'strike_rate' && 'text-accent')}>SR</th>
            <th className={clsx('table-header text-right', primaryCol === 'high_score' && 'text-accent')}>HS</th>
            <th className={clsx('table-header text-right', primaryCol === 'fifties' && 'text-accent')}>50s</th>
            <th className={clsx('table-header text-right', primaryCol === 'hundreds' && 'text-accent')}>100s</th>
            <th className={clsx('table-header text-right', primaryCol === 'total_sixes' && 'text-accent')}>6s</th>
            <th className={clsx('table-header text-right', primaryCol === 'total_fours' && 'text-accent')}>4s</th>
            <th className={clsx('table-header text-right', primaryCol === 'ducks' && 'text-accent')}>0s</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.player_id} className="table-row">
              <td className="table-cell text-slate-600 font-mono">{i + 1}</td>
              <td className="table-cell">
                <Link to={`/players/${row.player_id}`} className="text-white hover:text-accent transition-colors font-medium">
                  {row.name}
                </Link>
              </td>
              <td className="table-cell stat-number text-right text-slate-400">{row.innings ?? '—'}</td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'total_runs' ? 'font-bold text-accent' : 'text-slate-300')}>
                {row.total_runs ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'average' ? 'font-bold text-accent' : 'text-white')}>
                {row.average ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'strike_rate' ? 'font-bold text-accent' : 'text-slate-300')}>
                {row.strike_rate ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'high_score' ? 'font-bold text-accent' : 'text-slate-300')}>
                {row.high_score ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'fifties' ? 'font-bold text-accent' : 'text-slate-300')}>
                {row.fifties ?? '—'}
              </td>
              <td className="table-cell stat-number text-right">
                <span className={row.hundreds > 0 ? 'text-amber-cricket font-bold' : (primaryCol === 'hundreds' ? 'text-accent font-bold' : 'text-slate-500')}>
                  {row.hundreds ?? '—'}
                </span>
              </td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'total_sixes' ? 'font-bold text-accent' : 'text-slate-400')}>
                {row.total_sixes ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'total_fours' ? 'font-bold text-accent' : 'text-slate-400')}>
                {row.total_fours ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'ducks' ? 'font-bold text-red-400' : 'text-slate-500')}>
                {row.ducks ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BowlingLeaderboard({ orgId, seasonId, gradeId, sortBy }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.bowlingLeaderboard(orgId, { seasonId, gradeId, sortBy, limit: 30 })
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId, sortBy])

  if (loading) return <LoadingSpinner />
  if (!rows.length) return <p className="text-slate-500 text-sm py-8 text-center">No bowling data yet.</p>

  const primaryCol = sortBy || 'total_wickets'

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header w-8">#</th>
            <th className="table-header">Player</th>
            <th className="table-header text-right">Games</th>
            <th className="table-header text-right">Overs</th>
            <th className={clsx('table-header text-right', primaryCol === 'total_wickets' && 'text-accent')}>Wkts</th>
            <th className={clsx('table-header text-right', primaryCol === 'average' && 'text-accent')}>Avg</th>
            <th className={clsx('table-header text-right', primaryCol === 'economy' && 'text-accent')}>Econ</th>
            <th className={clsx('table-header text-right', primaryCol === 'best_figures_wickets' && 'text-accent')}>Best</th>
            <th className={clsx('table-header text-right', primaryCol === 'total_maidens' && 'text-accent')}>Mdns</th>
            <th className={clsx('table-header text-right', primaryCol === 'five_fors' && 'text-accent')}>5W</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.player_id} className="table-row">
              <td className="table-cell text-slate-600 font-mono">{i + 1}</td>
              <td className="table-cell">
                <Link to={`/players/${row.player_id}`} className="text-white hover:text-accent transition-colors font-medium">
                  {row.name}
                </Link>
              </td>
              <td className="table-cell stat-number text-right text-slate-400">{row.games ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.total_overs ?? '—'}</td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'total_wickets' ? 'font-bold text-accent' : 'text-white')}>
                {row.total_wickets ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'average' ? 'font-bold text-accent' : 'text-slate-300')}>
                {row.average ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'economy' ? 'font-bold text-accent' : 'text-slate-300')}>
                {row.economy ?? '—'}
              </td>
              <td className="table-cell stat-number text-right">
                <span className={row.best_figures_wickets >= 5 ? 'text-amber-cricket font-bold' : (primaryCol === 'best_figures_wickets' ? 'text-accent font-bold' : 'text-slate-300')}>
                  {row.best_figures_wickets ?? '—'}
                </span>
              </td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'total_maidens' ? 'font-bold text-accent' : 'text-slate-400')}>
                {row.total_maidens ?? '—'}
              </td>
              <td className={clsx('table-cell stat-number text-right', primaryCol === 'five_fors' ? 'font-bold text-accent' : 'text-slate-400')}>
                {row.five_fors ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FieldingLeaderboard({ orgId, seasonId, gradeId }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.fieldingLeaderboard(orgId, { seasonId, gradeId, limit: 30 })
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId])

  if (loading) return <LoadingSpinner />
  if (!rows.length) return <p className="text-slate-500 text-sm py-8 text-center">No fielding data yet.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header w-8">#</th>
            <th className="table-header">Player</th>
            <th className="table-header text-right">Games</th>
            <th className="table-header text-right">Catches</th>
            <th className="table-header text-right">Run Outs</th>
            <th className="table-header text-right">Stumpings</th>
            <th className="table-header text-right">Total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.player_id} className="table-row">
              <td className="table-cell text-slate-600 font-mono">{i + 1}</td>
              <td className="table-cell">
                <Link to={`/players/${row.player_id}`} className="text-white hover:text-accent transition-colors font-medium">
                  {row.name}
                </Link>
              </td>
              <td className="table-cell stat-number text-right text-slate-400">{row.games ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.total_catches ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.total_run_outs ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.total_stumpings ?? '—'}</td>
              <td className="table-cell stat-number text-right font-bold text-accent">{row.total_dismissals ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Leaderboard() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  useClubTheme(club)
  const { org, seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade, loading } = useClubData(orgId)

  if (inactive) return <ClubInactive />
  const [tab, setTab] = useState('batting')
  const [battingSort, setBattingSort] = useState('total_runs')
  const [bowlingSort, setBowlingSort] = useState('total_wickets')

  if (loading) return <LoadingSpinner message="Loading leaderboard…" />

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="accent-bar mb-3" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="section-label mb-1">{org?.name}</p>
            <h1 className="display-heading text-4xl md:text-5xl text-white">LEADERBOARD</h1>
          </div>
          <div className="flex gap-2">
            <Link to={`/${clubSlug}/compare`} className="btn-ghost border border-navy-600 text-sm">Compare →</Link>
            <Link to={`/${clubSlug}/dashboard`} className="btn-ghost border border-navy-600 text-sm">← Dashboard</Link>
          </div>
        </div>
      </div>

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

      {/* Main tabs */}
      <div className="flex gap-1 border-b border-navy-700">
        {MAIN_TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              'px-5 py-3 text-sm font-semibold uppercase tracking-wider transition-colors border-b-2 -mb-px',
              tab === t.key
                ? 'text-accent border-accent'
                : 'text-slate-500 border-transparent hover:text-white'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="card rounded-t-none border-t-0 overflow-hidden">
        {tab === 'batting' && (
          <>
            <SubTabBar tabs={BATTING_SORTS} active={battingSort} onSelect={setBattingSort} />
            <BattingLeaderboard orgId={orgId} seasonId={selectedSeason} gradeId={selectedGrade} sortBy={battingSort} />
          </>
        )}
        {tab === 'bowling' && (
          <>
            <SubTabBar tabs={BOWLING_SORTS} active={bowlingSort} onSelect={setBowlingSort} />
            <BowlingLeaderboard orgId={orgId} seasonId={selectedSeason} gradeId={selectedGrade} sortBy={bowlingSort} />
          </>
        )}
        {tab === 'fielding' && (
          <FieldingLeaderboard orgId={orgId} seasonId={selectedSeason} gradeId={selectedGrade} />
        )}
      </div>
    </div>
  )
}
