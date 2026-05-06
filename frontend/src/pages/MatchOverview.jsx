import { useParams, useSearchParams } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

function ResultBanner({ game }) {
  const isWin = game.result === 'WIN'
  const isDraw = ['DRAW', 'TIE', 'NO_RESULT'].includes(game.result)

  return (
    <div className={clsx(
      'rounded-xl p-5 mb-5 border',
      isWin ? 'bg-accent/10 border-accent/30' : isDraw ? 'bg-slate-500/10 border-slate-500/30' : 'bg-red-500/10 border-red-500/30'
    )}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="section-label mb-1">
            {[game.grade?.name, game.season, game.round].filter(Boolean).join(' · ')}
          </p>
          <h2 className="display-heading text-2xl md:text-3xl text-white leading-tight">
            {game.home_team} <span className="text-slate-500 font-sans font-normal text-lg">vs</span> {game.away_team}
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            {game.played_at && new Date(game.played_at).toLocaleDateString('en-AU', {
              weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
            })}
            {game.time && <span className="ml-2 text-slate-500">{game.time}</span>}
          </p>
          {game.venue && <p className="text-slate-500 text-xs mt-0.5">{game.venue}</p>}
        </div>
        <div className="text-right shrink-0">
          <div className={clsx(
            'display-heading text-4xl font-bold',
            isWin ? 'text-accent' : isDraw ? 'text-slate-400' : 'text-red-400'
          )}>
            {game.result || 'N/R'}
          </div>
          {game.winning_team && (
            <p className="text-xs text-slate-400 mt-1">{game.winning_team} won</p>
          )}
        </div>
      </div>
    </div>
  )
}

function ScoreDisplay({ score }) {
  if (score == null) return <span className="text-slate-700">—</span>
  return <span>{score}</span>
}

function CompetitorCard({ competitor, isWinner }) {
  const hasMultipleInnings = competitor.innings && competitor.innings.length > 1

  return (
    <div className={clsx(
      'card p-4 flex flex-col gap-2',
      isWinner && 'border-accent/40 bg-accent/5'
    )}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {isWinner && <span className="text-xs text-accent font-medium block mb-0.5">WINNER</span>}
          <p className="text-white font-medium text-sm leading-tight truncate">{competitor.name}</p>
          <p className="text-xs text-slate-500 mt-0.5">{competitor.is_home ? 'Home' : 'Away'}</p>
        </div>
        <div className="text-right shrink-0">
          <p className={clsx(
            'stat-number text-3xl font-bold leading-none',
            isWinner ? 'text-accent' : 'text-white'
          )}>
            <ScoreDisplay score={competitor.score} />
          </p>
        </div>
      </div>

      {hasMultipleInnings && (
        <div className="border-t border-navy-700 pt-2 space-y-1">
          {competitor.innings.map((inn, i) => (
            <div key={i} className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">Innings {inn.innings_number ?? i + 1}</span>
              <span className="text-sm text-slate-300 font-mono">
                {inn.score ?? '—'}
                {inn.declared && <span className="text-xs text-slate-500 ml-1">dec</span>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function BattingTable({ rows }) {
  if (!rows || rows.length === 0) return null
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm min-w-[480px]">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="text-left text-xs text-slate-500 font-medium pb-2 pr-3 w-1/4">Batsman</th>
            <th className="text-left text-xs text-slate-500 font-medium pb-2 pr-3 w-1/4">How Out</th>
            <th className="text-left text-xs text-slate-500 font-medium pb-2 pr-3 w-1/4">Bowler</th>
            <th className="text-right text-xs text-slate-500 font-medium pb-2 pr-3">R</th>
            <th className="text-right text-xs text-slate-500 font-medium pb-2 pr-3">B</th>
            <th className="text-right text-xs text-slate-500 font-medium pb-2 pr-3">4s</th>
            <th className="text-right text-xs text-slate-500 font-medium pb-2">6s</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b, i) => (
            <tr key={i} className="border-b border-navy-800/50 hover:bg-navy-800/20">
              <td className={clsx('py-1.5 pr-3 font-medium', b.not_out ? 'text-accent' : 'text-white')}>
                {b.name || '—'}
                {b.not_out && <span className="text-xs text-slate-500 ml-1">*</span>}
              </td>
              <td className="py-1.5 pr-3 text-slate-400">{b.how_out || (b.not_out ? 'not out' : '—')}</td>
              <td className="py-1.5 pr-3 text-slate-400">{b.bowled_by || ''}</td>
              <td className={clsx('py-1.5 pr-3 text-right font-mono font-bold', b.not_out ? 'text-accent' : 'text-white')}>
                {b.runs ?? '—'}
              </td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-400">{b.balls ?? '—'}</td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-400">{b.fours ?? '—'}</td>
              <td className="py-1.5 text-right font-mono text-slate-400">{b.sixes ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BowlingTable({ rows }) {
  if (!rows || rows.length === 0) return null
  return (
    <div className="overflow-x-auto mt-4">
      <table className="w-full text-sm min-w-[400px]">
        <thead>
          <tr className="border-b border-navy-700">
            <th className="text-left text-xs text-slate-500 font-medium pb-2 pr-3 w-2/5">Bowler</th>
            <th className="text-right text-xs text-slate-500 font-medium pb-2 pr-3">O</th>
            <th className="text-right text-xs text-slate-500 font-medium pb-2 pr-3">M</th>
            <th className="text-right text-xs text-slate-500 font-medium pb-2 pr-3">R</th>
            <th className="text-right text-xs text-slate-500 font-medium pb-2 pr-3">W</th>
            <th className="text-right text-xs text-slate-500 font-medium pb-2 pr-3">Wd</th>
            <th className="text-right text-xs text-slate-500 font-medium pb-2">Nb</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b, i) => (
            <tr key={i} className="border-b border-navy-800/50 hover:bg-navy-800/20">
              <td className="py-1.5 pr-3 text-white font-medium">{b.name || '—'}</td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-300">{b.overs ?? '—'}</td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-400">{b.maidens ?? '—'}</td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-300">{b.runs ?? '—'}</td>
              <td className={clsx('py-1.5 pr-3 text-right font-mono font-bold', b.wickets > 0 ? 'text-accent' : 'text-white')}>
                {b.wickets ?? '—'}
              </td>
              <td className="py-1.5 pr-3 text-right font-mono text-slate-500">{b.wides ?? '—'}</td>
              <td className="py-1.5 text-right font-mono text-slate-500">{b.no_balls ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function InningsCard({ innings }) {
  const wkt = innings.total_wickets
  const totalStr = innings.total_runs != null
    ? `${wkt != null && wkt !== 10 ? wkt + '/' : ''}${innings.total_runs}`
    : null

  return (
    <div className="card p-5 mb-4">
      <div className="flex items-baseline justify-between mb-4">
        <h4 className="display-heading text-sm text-white">
          {innings.batting_team || `Innings ${innings.innings_number}`}
          {innings.innings_number > 1 && (
            <span className="text-slate-500 font-sans font-normal text-xs ml-2">
              {innings.innings_number === 2 ? '2nd' : innings.innings_number === 3 ? '3rd' : `${innings.innings_number}th`} innings
            </span>
          )}
        </h4>
        <div className="text-right shrink-0">
          {totalStr && <span className="stat-number text-2xl font-bold text-accent">{totalStr}</span>}
          {innings.overs && <span className="text-slate-500 text-xs ml-2">({innings.overs} ov)</span>}
          {innings.extras != null && innings.extras > 0 && (
            <span className="text-slate-500 text-xs ml-2">+{innings.extras} extras</span>
          )}
        </div>
      </div>

      <BattingTable rows={innings.batting} />
      <BowlingTable rows={innings.bowling} />
    </div>
  )
}

export default function MatchOverview() {
  const { gameId } = useParams()
  const [searchParams] = useSearchParams()
  const orgId = searchParams.get('org')

  const [game, setGame] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [scorecard, setScorecard] = useState(null)
  const [scorecardLoading, setScorecardLoading] = useState(false)
  const [scorecardError, setScorecardError] = useState(null)

  useEffect(() => {
    if (!orgId) {
      setError('Organisation ID required')
      setLoading(false)
      return
    }
    api.getPlayHQGame(orgId, gameId)
      .then(setGame)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [gameId, orgId])

  useEffect(() => {
    if (!game || !orgId) return
    setScorecardLoading(true)
    api.getPlayHQScorecard(orgId, gameId)
      .then(data => {
        if (data?.innings?.length > 0) setScorecard(data)
        else setScorecardError('No scorecard data available')
      })
      .catch(e => setScorecardError(e.message))
      .finally(() => setScorecardLoading(false))
  }, [game, gameId, orgId])

  if (loading) return <LoadingSpinner message="Loading match…" />
  if (error) return (
    <div className="max-w-4xl mx-auto px-4 py-16 text-center">
      <p className="text-red-400 mb-4">Error: {error}</p>
      <button onClick={() => window.history.back()} className="btn-ghost">← Back</button>
    </div>
  )
  if (!game) return null

  const competitors = game.competitors || []
  const hasCompetitors = competitors.length > 0
  const hasScores = hasCompetitors
    ? competitors.some(c => c.score != null)
    : (game.home_score != null || game.away_score != null)

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <button onClick={() => window.history.back()} className="btn-ghost text-slate-500 text-sm mb-5 flex items-center gap-1">
        ← Back
      </button>

      <ResultBanner game={game} />

      {/* Team totals */}
      {hasScores && (
        <div className="mb-5">
          <h3 className="display-heading text-base text-white mb-3">SCORECARD</h3>
          {hasCompetitors ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {competitors.map((c, i) => (
                <CompetitorCard
                  key={i}
                  competitor={c}
                  isWinner={game.winning_team && c.name === game.winning_team}
                />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div className="card p-4">
                <p className="section-label mb-1">{game.home_team === game.winning_team ? 'WINNER · HOME' : 'HOME'}</p>
                <p className="text-white text-sm font-medium mb-2 truncate">{game.home_team}</p>
                <p className="stat-number text-4xl font-bold text-accent leading-none">
                  <ScoreDisplay score={game.home_score} />
                </p>
              </div>
              <div className="card p-4">
                <p className="section-label mb-1">{game.away_team === game.winning_team ? 'WINNER · AWAY' : 'AWAY'}</p>
                <p className="text-white text-sm font-medium mb-2 truncate">{game.away_team}</p>
                <p className="stat-number text-4xl font-bold text-white leading-none">
                  <ScoreDisplay score={game.away_score} />
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Full innings scorecard */}
      {scorecardLoading && (
        <div className="card p-5 mb-4 flex items-center gap-3 text-slate-400">
          <svg className="w-4 h-4 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <span className="text-sm">Loading batting &amp; bowling figures…</span>
        </div>
      )}

      {scorecard && scorecard.innings.map((inn, i) => (
        <InningsCard key={i} innings={inn} />
      ))}

      {scorecardError && !scorecardLoading && (
        <div className="card p-4 mb-4 border-navy-700/50">
          <p className="text-xs text-slate-500">Batting &amp; bowling figures not available for this match.</p>
        </div>
      )}

      {/* Match details */}
      <div className="card p-5 mb-5">
        <h3 className="display-heading text-base text-white mb-4">MATCH DETAILS</h3>
        <div className="grid grid-cols-2 gap-x-6 gap-y-2.5">
          {[
            ['Grade', game.grade?.name],
            ['Round', game.round],
            ['Season', game.season],
            ['Venue', game.venue],
            ['Date', game.played_at ? new Date(game.played_at).toLocaleDateString('en-AU', {
              weekday: 'short', day: 'numeric', month: 'long', year: 'numeric'
            }) : null],
            ['Time', game.time],
          ].filter(([, v]) => v).map(([label, value]) => (
            <div key={label} className="flex items-baseline gap-2">
              <span className="section-label w-14 shrink-0 text-right">{label}</span>
              <span className="text-slate-300 text-sm">{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* PlayHQ link */}
      {game.url && (
        <div className="card p-4 flex items-center justify-between border-navy-700/50">
          <div>
            <p className="text-sm text-white font-medium">Full scorecard on PlayHQ</p>
            <p className="text-xs text-slate-500 mt-0.5">Batting &amp; bowling figures, partnerships and more</p>
          </div>
          <a
            href={game.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary inline-flex items-center gap-2 text-sm shrink-0 ml-4"
          >
            View
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
        </div>
      )}
    </div>
  )
}
