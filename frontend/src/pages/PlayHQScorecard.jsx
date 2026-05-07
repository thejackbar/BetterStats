import { useParams, useSearchParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(iso) {
  if (!iso) return null
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-AU', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  })
}

// ── Result banner ─────────────────────────────────────────────────────────────

function ResultBanner({ game, toss }) {
  if (!game) return null
  const isWin = game.result === 'WIN'
  const isDraw = ['DRAW', 'TIE', 'NO_RESULT'].includes(game.result)

  return (
    <div className={clsx(
      'rounded-xl p-6 mb-6 border',
      isWin  ? 'bg-accent/10 border-accent/30'
             : isDraw ? 'bg-slate-500/10 border-slate-500/30'
                      : 'bg-red-500/10 border-red-500/30',
    )}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {(game.season || game.grade?.name) && (
            <p className="section-label mb-1">
              {[game.season, game.grade?.name].filter(Boolean).join(' · ')}
              {game.round && <span> · {game.round}</span>}
            </p>
          )}
          <h2 className="display-heading text-2xl md:text-3xl text-white">
            {game.home_team}
            <span className="text-slate-500 font-sans font-normal text-xl mx-2">vs</span>
            {game.away_team}
          </h2>
          {game.played_at && (
            <p className="text-slate-400 text-sm mt-1">{fmtDate(game.played_at)}</p>
          )}
          {game.venue && (
            <p className="text-slate-500 text-xs mt-0.5">{game.venue}</p>
          )}
          {toss && (
            <p className="text-slate-500 text-xs mt-2 italic">{toss}</p>
          )}
        </div>

        <div className="text-right shrink-0">
          {(game.competitors || []).map((c, i) => (
            <div key={i} className="mb-1">
              <span className="text-xs text-slate-400 mr-2">{c.name}</span>
              {(c.innings || []).map((inn, j) => (
                <span key={j} className="stat-number text-white font-bold text-sm mr-2">
                  {inn.score ?? '—'}{inn.declared ? '*' : ''}
                </span>
              ))}
              {!c.innings?.length && c.score != null && (
                <span className="stat-number text-white font-bold text-sm">{c.score}</span>
              )}
            </div>
          ))}
          <div className={clsx(
            'display-heading text-xl mt-2',
            isWin ? 'text-accent' : isDraw ? 'text-slate-400' : 'text-red-400',
          )}>
            {game.result || 'N/R'}
          </div>
          {game.winning_team && (
            <p className="text-xs text-slate-400 mt-0.5">{game.winning_team} won</p>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Score summary line ────────────────────────────────────────────────────────

function ScoreLine({ innings }) {
  const runs = innings.total_runs ?? innings.batting.reduce((s, r) => s + (r.runs ?? 0), 0)
  const wickets = innings.total_wickets ?? innings.batting.filter(r => !r.not_out && !r.did_not_bat).length
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span className="stat-number text-white font-bold text-xl">{runs}/{wickets}</span>
      {innings.overs != null && (
        <span className="text-slate-400 text-sm">({innings.overs} ov)</span>
      )}
      {innings.extras != null && (
        <span className="text-slate-500 text-xs">Extras: {innings.extras}</span>
      )}
    </div>
  )
}

// ── Batting table ─────────────────────────────────────────────────────────────

function BattingTable({ batting = [] }) {
  if (!batting.length) return <p className="text-slate-500 text-sm py-4 px-4">No batting data.</p>

  const dnb = batting.filter(r => r.did_not_bat)
  const batted = batting.filter(r => !r.did_not_bat)

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="table-header">Batter</th>
            <th className="table-header text-slate-500 font-normal normal-case tracking-normal min-w-[120px]">Dismissal</th>
            <th className="table-header text-right">R</th>
            <th className="table-header text-right">B</th>
            <th className="table-header text-right">4s</th>
            <th className="table-header text-right">6s</th>
            <th className="table-header text-right">SR</th>
          </tr>
        </thead>
        <tbody>
          {batted.map((row, i) => (
            <tr key={i} className="table-row">
              <td className="table-cell font-medium">
                {row.player_id ? (
                  <Link to={`/players/${row.player_id}`} className="text-white hover:text-accent transition-colors">
                    {row.name}
                  </Link>
                ) : (
                  <span className="text-white">{row.name}</span>
                )}
              </td>
              <td className="table-cell text-slate-400 text-xs">
                {row.how_out || (row.not_out ? 'not out' : '—')}
              </td>
              <td className="table-cell text-right">
                <span className={clsx(
                  'stat-number font-bold',
                  (row.runs ?? 0) >= 100 ? 'text-amber-cricket'
                    : (row.runs ?? 0) >= 50 ? 'text-accent'
                    : 'text-white',
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
        {dnb.length > 0 && (
          <tfoot>
            <tr className="border-t border-navy-700/50">
              <td colSpan={7} className="table-cell text-slate-600 text-xs italic">
                DNB: {dnb.map(r => r.name).join(', ')}
              </td>
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}

// ── Bowling table ─────────────────────────────────────────────────────────────

function BowlingTable({ bowling = [] }) {
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
              <td className="table-cell font-medium">
                {row.player_id ? (
                  <Link to={`/players/${row.player_id}`} className="text-white hover:text-accent transition-colors">
                    {row.name}
                  </Link>
                ) : (
                  <span className="text-white">{row.name}</span>
                )}
              </td>
              <td className="table-cell stat-number text-right text-slate-300">{row.overs ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-400">{row.maidens ?? '—'}</td>
              <td className="table-cell stat-number text-right text-slate-300">{row.runs ?? '—'}</td>
              <td className="table-cell text-right">
                <span className={clsx(
                  'stat-number font-bold',
                  (row.wickets ?? 0) >= 5 ? 'text-amber-cricket'
                    : (row.wickets ?? 0) >= 3 ? 'text-accent'
                    : 'text-white',
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

// ── Single innings card ───────────────────────────────────────────────────────

function InningsCard({ innings, accentTitle }) {
  const label = innings.batting_team || `Innings ${innings.innings_number}`

  return (
    <div className="card overflow-hidden flex flex-col">
      {/* Header */}
      <div className="px-5 py-4 border-b border-navy-700">
        <h3 className={clsx('display-heading text-lg', accentTitle ? 'text-accent' : 'text-white')}>
          {label.toUpperCase()}
        </h3>
        {innings.bowling_team && (
          <p className="text-slate-500 text-xs mt-0.5">Bowling: {innings.bowling_team}</p>
        )}
        <div className="mt-2">
          <ScoreLine innings={innings} />
        </div>
      </div>

      {/* Batting */}
      <div className="border-b border-navy-700/60">
        <div className="px-4 py-1.5 bg-navy-800/40">
          <span className="text-xs text-slate-500 uppercase tracking-wider font-medium">Batting</span>
        </div>
        <BattingTable batting={innings.batting} />
      </div>

      {/* Bowling — always visible */}
      {innings.bowling.length > 0 && (
        <div>
          <div className="px-4 py-1.5 bg-navy-800/40 border-b border-navy-700/60">
            <span className="text-xs text-slate-500 uppercase tracking-wider font-medium">Bowling</span>
          </div>
          <BowlingTable bowling={innings.bowling} />
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PlayHQScorecard() {
  const { gameId } = useParams()
  const [searchParams] = useSearchParams()
  const orgId = searchParams.get('org')

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!orgId) {
      setError('Missing org parameter')
      setLoading(false)
      return
    }
    api.getPlayHQScorecard(orgId, gameId)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [gameId, orgId])

  if (loading) return <LoadingSpinner message="Loading scorecard…" />
  if (error) return (
    <div className="max-w-5xl mx-auto px-4 py-16 text-red-400">
      <p>Error: {error}</p>
      {orgId && (
        <Link to={`/dashboard/${orgId}`} className="text-accent text-sm mt-4 block hover:underline">
          ← Back to dashboard
        </Link>
      )}
    </div>
  )
  if (!data) return null

  const { innings = [], game, toss, status } = data

  if (!innings.length) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 text-center">
        <p className="text-slate-400 text-lg mb-2">Scorecard not available</p>
        <p className="text-slate-600 text-sm mb-6">
          {status === 'FINAL'
            ? 'The match is complete but scorecard data could not be loaded.'
            : 'This match may not have started yet or data is still being processed.'}
        </p>
        {orgId && (
          <Link to={`/dashboard/${orgId}`} className="text-accent text-sm hover:underline">
            ← Back to dashboard
          </Link>
        )}
      </div>
    )
  }

  const isTwoInnings = innings.length >= 2

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {orgId && (
        <Link to={`/dashboard/${orgId}`} className="text-slate-500 text-sm hover:text-accent transition-colors mb-6 block">
          ← Back to dashboard
        </Link>
      )}

      <ResultBanner game={game} toss={toss} />

      {/* Two-innings: side-by-side on large screens */}
      {isTwoInnings ? (
        <div className="grid lg:grid-cols-2 gap-6">
          {innings.map((inn, i) => (
            <InningsCard key={inn.innings_number} innings={inn} accentTitle={i === 0} />
          ))}
        </div>
      ) : (
        /* Single innings: full width */
        innings.map((inn, i) => (
          <InningsCard key={inn.innings_number} innings={inn} accentTitle={i === 0} />
        ))
      )}
    </div>
  )
}
