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

function InningsScoreCard({ label, team, score }) {
  return (
    <div className="card p-4">
      <p className="section-label mb-1">{label}</p>
      <p className="display-heading text-base text-white truncate mb-2">{team}</p>
      {score != null ? (
        <p className="stat-number text-4xl font-bold text-accent leading-none">{score}</p>
      ) : (
        <p className="stat-number text-3xl text-slate-700">—</p>
      )}
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

  if (loading) return <LoadingSpinner message="Loading match…" />
  if (error) return (
    <div className="max-w-4xl mx-auto px-4 py-16 text-center">
      <p className="text-red-400 mb-4">Error: {error}</p>
      <button onClick={() => window.history.back()} className="btn-ghost">← Back</button>
    </div>
  )
  if (!game) return null

  const hasScores = game.home_score != null || game.away_score != null

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <button onClick={() => window.history.back()} className="btn-ghost text-slate-500 text-sm mb-5 flex items-center gap-1">
        ← Back
      </button>

      <ResultBanner game={game} />

      {/* Innings score overview */}
      {hasScores && (
        <div className="grid grid-cols-2 gap-3 mb-5">
          <InningsScoreCard
            label={game.home_team === game.winning_team ? '🏆 Home' : 'Home'}
            team={game.home_team}
            score={game.home_score}
          />
          <InningsScoreCard
            label={game.away_team === game.winning_team ? '🏆 Away' : 'Away'}
            team={game.away_team}
            score={game.away_score}
          />
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

      {/* Scorecard unavailable notice + PlayHQ link */}
      <div className="card p-5 text-center border-navy-700/50">
        <p className="text-slate-400 text-sm mb-1 font-medium">Detailed scorecard not available</p>
        <p className="text-slate-600 text-xs mb-4">
          Per-player batting &amp; bowling data requires a higher PlayHQ API tier.
        </p>
        {game.url && (
          <a
            href={game.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary inline-flex items-center gap-2 text-sm"
          >
            View full scorecard on PlayHQ
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
        )}
      </div>
    </div>
  )
}
