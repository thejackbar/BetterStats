import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

function ResultBanner({ game }) {
  const isWin = game.result === 'WIN'
  const isDraw = ['DRAW', 'TIE', 'NO_RESULT'].includes(game.result)

  return (
    <div className={clsx(
      'rounded-xl p-6 mb-6 border',
      isWin ? 'bg-accent/10 border-accent/30' : isDraw ? 'bg-slate-500/10 border-slate-500/30' : 'bg-red-500/10 border-red-500/30'
    )}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="section-label mb-1">{game.season?.name} · {game.grade?.name}</p>
          <h2 className="display-heading text-2xl md:text-3xl text-white">
            {game.home_team} <span className="text-slate-500 font-sans font-normal text-xl">vs</span> {game.away_team}
          </h2>
          {game.played_at && (
            <p className="text-slate-400 text-sm mt-1">
              {new Date(game.played_at).toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
            </p>
          )}
        </div>
        <div className="text-right">
          <div className={clsx(
            'display-heading text-2xl',
            isWin ? 'text-accent' : isDraw ? 'text-slate-400' : 'text-red-400'
          )}>
            {game.result || 'N/R'}
          </div>
          {game.winning_team && (
            <p className="text-sm text-slate-400 mt-1">{game.winning_team} won</p>
          )}
        </div>
      </div>
    </div>
  )
}

function InningsTotal({ batting }) {
  const runs = batting.reduce((s, r) => s + (r.runs ?? 0), 0)
  const wickets = batting.filter(r => !r.not_out && r.dismissal_type && r.dismissal_type !== '').length
  return (
    <div className="flex items-center gap-2 text-sm text-slate-400">
      <span className="stat-number text-white font-bold text-lg">{runs}/{wickets}</span>
    </div>
  )
}

function BattingScorecard({ batting = [] }) {
  if (!batting.length) return <p className="text-slate-500 text-sm py-4 px-4">No batting data.</p>

  const total = batting.reduce((s, r) => s + (r.runs ?? 0), 0)
  const wickets = batting.filter(r => !r.not_out && r.dismissal_type && r.dismissal_type !== '').length

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header">Batter</th>
            <th className="table-header text-slate-500 font-normal normal-case tracking-normal">Dismissal</th>
            <th className="table-header text-right">R</th>
            <th className="table-header text-right">B</th>
            <th className="table-header text-right">4s</th>
            <th className="table-header text-right">6s</th>
            <th className="table-header text-right">SR</th>
          </tr>
        </thead>
        <tbody>
          {batting.map((row, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell">
                <Link to={`/players/${row.player_id}`} className="text-white hover:text-accent transition-colors font-medium">
                  {row.player_name}
                </Link>
              </td>
              <td className="table-cell text-slate-500 text-xs capitalize">
                {row.not_out ? 'not out' : row.dismissal_type || '—'}
              </td>
              <td className="table-cell text-right">
                <span className={clsx(
                  'stat-number font-bold',
                  row.runs >= 100 ? 'text-amber-cricket' : row.runs >= 50 ? 'text-accent' : 'text-white'
                )}>
                  {row.runs ?? '—'}
                </span>
                {row.not_out && <span className="text-accent text-xs">*</span>}
              </td>
              <td className="table-cell stat-number text-right text-slate-300">{row.balls ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.fours ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.sixes ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">
                {row.strike_rate != null ? Number(row.strike_rate).toFixed(1) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-navy-600">
            <td colSpan={2} className="table-cell text-slate-400 font-semibold text-sm">Total</td>
            <td className="table-cell stat-number text-right font-bold text-white text-base">
              {total}/{wickets}
            </td>
            <td colSpan={4} />
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function BowlingScorecard({ bowling = [] }) {
  if (!bowling.length) return <p className="text-slate-500 text-sm py-4 px-4">No bowling data.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header">Bowler</th>
            <th className="table-header text-right">O</th>
            <th className="table-header text-right">M</th>
            <th className="table-header text-right">R</th>
            <th className="table-header text-right">W</th>
            <th className="table-header text-right">Econ</th>
            <th className="table-header text-right">Wd</th>
            <th className="table-header text-right">NB</th>
          </tr>
        </thead>
        <tbody>
          {bowling.map((row, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell">
                <Link to={`/players/${row.player_id}`} className="text-white hover:text-accent transition-colors font-medium">
                  {row.player_name}
                </Link>
              </td>
              <td className="table-cell stat-number text-right text-slate-300">{row.overs ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.maidens ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.runs ?? '—'}</td>
              <td className="table-cell text-right">
                <span className={clsx(
                  'stat-number font-bold',
                  row.wickets >= 5 ? 'text-amber-cricket' : row.wickets >= 3 ? 'text-accent' : 'text-white'
                )}>
                  {row.wickets ?? '—'}
                </span>
              </td>
              <td className="table-cell stat-number text-right text-slate-300">
                {row.economy != null ? Number(row.economy).toFixed(2) : '—'}
              </td>
              <td className="table-cell stat-number text-right text-slate-400">{row.wides ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.no_balls ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FallOfWicketsSection({ fow = [] }) {
  if (!fow.length) return null

  const byInnings = fow.reduce((acc, f) => {
    const k = f.innings_number
    if (!acc[k]) acc[k] = []
    acc[k].push(f)
    return acc
  }, {})

  return (
    <div className="card p-5">
      <h3 className="display-heading text-lg text-white mb-4">FALL OF WICKETS</h3>
      {Object.entries(byInnings).map(([inn, items]) => (
        <div key={inn} className="mb-4 last:mb-0">
          {Object.keys(byInnings).length > 1 && (
            <p className="section-label mb-2">Innings {inn}</p>
          )}
          <div className="flex flex-wrap gap-2">
            {items.map((f, i) => (
              <div key={i} className="bg-navy-800 border border-navy-700 rounded px-3 py-1.5 text-sm">
                <span className="stat-number text-accent font-bold">{f.score_at_fall ?? '?'}</span>
                <span className="text-slate-500 mx-1">-</span>
                <span className="stat-number text-white">{f.wicket_number}</span>
                {f.player_name && (
                  <Link to={`/players/${f.player_id}`} className="text-slate-400 text-xs ml-2 hover:text-accent transition-colors">
                    ({f.player_name})
                  </Link>
                )}
                {f.overs_at_fall != null && (
                  <span className="text-slate-600 text-xs ml-1">{f.overs_at_fall} ov</span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function PartnershipsSection({ partnerships = [] }) {
  if (!partnerships.length) return null

  const byInnings = partnerships.reduce((acc, p) => {
    const k = p.innings_number
    if (!acc[k]) acc[k] = []
    acc[k].push(p)
    return acc
  }, {})

  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-navy-700">
        <h3 className="display-heading text-lg text-white">PARTNERSHIPS</h3>
      </div>
      {Object.entries(byInnings).map(([inn, items]) => (
        <div key={inn}>
          {Object.keys(byInnings).length > 1 && (
            <p className="section-label px-5 pt-4 pb-1">Innings {inn}</p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-navy-700">
                  <th className="table-header">Wkt</th>
                  <th className="table-header">Batters</th>
                  <th className="table-header text-right">Runs</th>
                  <th className="table-header text-right">Balls</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p, i) => (
                  <tr key={i} className="table-row">
                    <td className="table-cell stat-number text-slate-400">{p.wicket_number}</td>
                    <td className="table-cell text-slate-300">
                      <span className="flex flex-col gap-0.5">
                        <span>
                          {p.batter1_name && (
                            <Link to={`/players/${p.batter1_id}`} className="hover:text-accent transition-colors">
                              {p.batter1_name}
                            </Link>
                          )}
                          {p.batter1_runs != null && (
                            <span className="text-slate-500 text-xs ml-1">({p.batter1_runs})</span>
                          )}
                        </span>
                        <span>
                          {p.batter2_name && (
                            <Link to={`/players/${p.batter2_id}`} className="hover:text-accent transition-colors">
                              {p.batter2_name}
                            </Link>
                          )}
                          {p.batter2_runs != null && (
                            <span className="text-slate-500 text-xs ml-1">({p.batter2_runs})</span>
                          )}
                        </span>
                      </span>
                    </td>
                    <td className="table-cell stat-number text-right font-bold text-white">{p.runs ?? '—'}</td>
                    <td className="table-cell stat-number text-right text-slate-400">{p.balls ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}

function FieldingSection({ fielding = [] }) {
  const notable = fielding.filter(f => (f.catches + f.run_outs + f.stumpings) > 0)
  if (!notable.length) return null

  return (
    <div className="card p-5">
      <h3 className="display-heading text-lg text-white mb-4">FIELDING</h3>
      <div className="flex flex-wrap gap-4">
        {notable.map((row, i) => (
          <div key={i} className="flex items-center gap-2">
            <Link to={`/players/${row.player_id}`} className="text-sm text-white hover:text-accent transition-colors">
              {row.player_name}
            </Link>
            <span className="text-slate-500 text-xs">
              {row.catches > 0 && `${row.catches}ct`}
              {row.run_outs > 0 && ` ${row.run_outs}ro`}
              {row.stumpings > 0 && ` ${row.stumpings}st`}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function InningsBlock({ title, subtitle, batting, bowling, accentTitle = false }) {
  const [showBowling, setShowBowling] = useState(false)
  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-navy-700 flex items-center justify-between">
        <div>
          <h3 className={clsx('display-heading text-xl', accentTitle ? 'text-accent' : 'text-white')}>
            {title}
          </h3>
          {subtitle && <p className="text-slate-500 text-xs mt-0.5">{subtitle}</p>}
        </div>
        {batting.length > 0 && (
          <div className="text-right">
            <InningsTotal batting={batting} />
          </div>
        )}
      </div>

      {/* Batting */}
      <div>
        <div className="px-4 py-2 bg-navy-800/40 border-b border-navy-700/50">
          <span className="text-xs text-slate-500 uppercase tracking-wider font-medium">Batting</span>
        </div>
        <BattingScorecard batting={batting} />
      </div>

      {/* Bowling toggle */}
      {bowling.length > 0 && (
        <div>
          <button
            onClick={() => setShowBowling(s => !s)}
            className="w-full px-4 py-2 bg-navy-800/40 border-t border-navy-700/50 flex items-center justify-between hover:bg-navy-700/30 transition-colors"
          >
            <span className="text-xs text-slate-500 uppercase tracking-wider font-medium">Bowling</span>
            <svg
              className={clsx('w-4 h-4 text-slate-500 transition-transform', showBowling && 'rotate-180')}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {showBowling && <BowlingScorecard bowling={bowling} />}
        </div>
      )}
    </div>
  )
}

export default function MatchScorecard() {
  const { gameId } = useParams()
  const [game, setGame] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getScorecard(gameId)
      .then(setGame)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [gameId])

  if (loading) return <LoadingSpinner message="Loading scorecard…" />
  if (error) return <div className="max-w-7xl mx-auto px-4 py-16 text-red-400">Error: {error}</div>
  if (!game) return null

  // Group batting and bowling by innings_number
  const inningsNums = [...new Set([
    ...(game.batting || []).map(r => r.innings_number || 1),
    ...(game.bowling || []).map(r => r.innings_number || 1),
  ])].sort()

  const inningsMap = inningsNums.map(num => {
    const batting = (game.batting || []).filter(r => (r.innings_number || 1) === num)
    // Bowling for this innings is the *other* team bowling — stored under the innings that was bowled AT
    // The bowling rows for innings N are bowlers bowling in innings N
    const bowling = (game.bowling || []).filter(r => (r.innings_number || 1) === num)
    const teamName = game.innings_teams?.[num] || (num === 1 ? game.home_team : game.away_team)
    return { num, batting, bowling, teamName }
  })

  const hasMultipleInnings = inningsMap.length > 1

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <ResultBanner game={game} />

      {/* Match overview strip */}
      {hasMultipleInnings && (
        <div className="grid grid-cols-2 gap-3 mb-6">
          {inningsMap.map(({ num, batting, teamName }) => (
            <div key={num} className="card p-3 text-center">
              <p className="section-label mb-1">Innings {num}</p>
              <p className="text-white text-sm font-medium truncate mb-1">{teamName}</p>
              <InningsTotal batting={batting} />
            </div>
          ))}
        </div>
      )}

      <div className="space-y-6">
        {hasMultipleInnings ? (
          inningsMap.map(({ num, batting, bowling, teamName }) => (
            <InningsBlock
              key={num}
              title={`INNINGS ${num} — ${teamName?.toUpperCase() || ''}`}
              batting={batting}
              bowling={bowling}
              accentTitle={num === 1}
            />
          ))
        ) : (
          /* Single-innings fallback: show flat batting + bowling */
          <>
            <div className="card overflow-hidden">
              <div className="px-5 py-4 border-b border-navy-700">
                <h3 className="display-heading text-xl text-white">BATTING</h3>
              </div>
              <BattingScorecard batting={game.batting} />
            </div>
            <div className="card overflow-hidden">
              <div className="px-5 py-4 border-b border-navy-700">
                <h3 className="display-heading text-xl text-white">BOWLING</h3>
              </div>
              <BowlingScorecard bowling={game.bowling} />
            </div>
          </>
        )}

        <FallOfWicketsSection fow={game.fall_of_wickets ?? []} />
        <PartnershipsSection partnerships={game.partnerships ?? []} />
        <FieldingSection fielding={game.fielding} />
      </div>
    </div>
  )
}
