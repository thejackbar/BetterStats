import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useClubData } from '../hooks/useClubData'
import { api } from '../lib/api'
import SeasonSelector from '../components/SeasonSelector'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

const TABS = [
  { key: 'batting', label: 'Batting' },
  { key: 'bowling', label: 'Bowling' },
  { key: 'fielding', label: 'Fielding' },
]

function Sparkline({ values = [] }) {
  if (values.length < 2) return null
  const max = Math.max(...values) || 1
  const w = 40
  const h = 18
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w
    const y = h - (v / max) * h
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={w} height={h} className="inline-block">
      <polyline points={pts} fill="none" stroke="#16c784" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function BattingLeaderboard({ orgId, seasonId, gradeId }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.battingLeaderboard(orgId, { seasonId, gradeId, limit: 20 })
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId])

  if (loading) return <LoadingSpinner />
  if (!rows.length) return <p className="text-slate-500 text-sm py-8 text-center">No batting data yet.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header w-8">#</th>
            <th className="table-header">Player</th>
            <th className="table-header text-right">Inn</th>
            <th className="table-header text-right">Runs</th>
            <th className="table-header text-right">Avg</th>
            <th className="table-header text-right">SR</th>
            <th className="table-header text-right">HS</th>
            <th className="table-header text-right">50s</th>
            <th className="table-header text-right">100s</th>
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
              <td className="table-cell stat-number text-right font-bold text-accent">{row.total_runs ?? '—'}</td>
              <td className="table-cell stat-number text-right text-white">{row.average ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.strike_rate ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.high_score ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.fifties ?? '—'}</td>
              <td className="table-cell stat-number text-right">
                <span className={row.hundreds > 0 ? 'text-amber-cricket font-bold' : 'text-slate-500'}>
                  {row.hundreds ?? '—'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BowlingLeaderboard({ orgId, seasonId, gradeId }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.bowlingLeaderboard(orgId, { seasonId, gradeId, limit: 20 })
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId])

  if (loading) return <LoadingSpinner />
  if (!rows.length) return <p className="text-slate-500 text-sm py-8 text-center">No bowling data yet.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header w-8">#</th>
            <th className="table-header">Player</th>
            <th className="table-header text-right">Games</th>
            <th className="table-header text-right">Overs</th>
            <th className="table-header text-right">Wkts</th>
            <th className="table-header text-right">Avg</th>
            <th className="table-header text-right">Econ</th>
            <th className="table-header text-right">Best</th>
            <th className="table-header text-right">Mdns</th>
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
              <td className="table-cell stat-number text-right font-bold text-accent">{row.total_wickets ?? '—'}</td>
              <td className="table-cell stat-number text-right text-white">{row.average ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.economy ?? '—'}</td>
              <td className="table-cell stat-number text-right">
                <span className={row.best_figures_wickets >= 5 ? 'text-amber-cricket font-bold' : 'text-slate-300'}>
                  {row.best_figures_wickets ?? '—'}
                </span>
              </td>
              <td className="table-cell stat-number text-right text-slate-400">{row.total_maidens ?? '—'}</td>
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
    api.fieldingLeaderboard(orgId, { seasonId, gradeId, limit: 20 })
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
  const { orgId } = useParams()
  const { org, seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade, loading } = useClubData(orgId)
  const [tab, setTab] = useState('batting')

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
          <Link to={`/dashboard/${orgId}`} className="btn-ghost border border-navy-600 text-sm">
            ← Dashboard
          </Link>
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

      {/* Tabs */}
      <div className="flex gap-1 mb-0 border-b border-navy-700">
        {TABS.map(t => (
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

      <div className="card rounded-t-none border-t-0">
        {tab === 'batting' && <BattingLeaderboard orgId={orgId} seasonId={selectedSeason} gradeId={selectedGrade} />}
        {tab === 'bowling' && <BowlingLeaderboard orgId={orgId} seasonId={selectedSeason} gradeId={selectedGrade} />}
        {tab === 'fielding' && <FieldingLeaderboard orgId={orgId} seasonId={selectedSeason} gradeId={selectedGrade} />}
      </div>
    </div>
  )
}
