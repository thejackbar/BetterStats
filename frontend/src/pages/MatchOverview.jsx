import { useParams, useSearchParams, Link } from 'react-router-dom'
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
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="section-label mb-1">
            {game.season} · {game.grade?.name}
            {game.round && <span> · {game.round}</span>}
          </p>
          <h2 className="display-heading text-2xl md:text-3xl text-white">
            {game.home_team} <span className="text-slate-500 font-sans font-normal text-xl">vs</span> {game.away_team}
          </h2>
          {game.played_at && (
            <p className="text-slate-400 text-sm mt-1">
              {new Date(game.played_at).toLocaleDateString('en-AU', {
                weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
              })}
              {game.time && <span className="ml-2 text-slate-500">{game.time}</span>}
            </p>
          )}
          {game.venue && (
            <p className="text-slate-500 text-sm mt-0.5">{game.venue}</p>
          )}
        </div>
        <div className="text-right">
          <div className={clsx(
            'display-heading text-3xl font-bold',
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

function ScoreCard({ team, score, isHome }) {
  return (
    <div className="card p-5 text-center">
      <p className="section-label mb-2">{isHome ? 'HOME' : 'AWAY'}</p>
      <p className="text-white font-semibold text-sm mb-3 truncate">{team}</p>
      {score != null ? (
        <p className="stat-number text-4xl font-bold text-white">{score}</p>
      ) : (
        <p className="text-slate-600 text-sm">—</p>
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
    <div className="max-w-5xl mx-auto px-4 py-16 text-center">
      <p className="text-red-400 mb-4">Error: {error}</p>
      <button onClick={() => window.history.back()} className="btn-ghost">← Back</button>
    </div>
  )
  if (!game) return null

  const hasScores = game.home_score != null || game.away_score != null

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <button onClick={() => window.history.back()} className="btn-ghost text-slate-500 text-sm mb-6 flex items-center gap-1">
        ← Back
      </button>

      <ResultBanner game={game} />

      {hasScores && (
        <div className="grid grid-cols-2 gap-4 mb-6">
          <ScoreCard team={game.home_team} score={game.home_score} isHome />
          <ScoreCard team={game.away_team} score={game.away_score} isHome={false} />
        </div>
      )}

      <div className="card p-5 space-y-3 mb-6">
        <h3 className="display-heading text-lg text-white mb-2">MATCH DETAILS</h3>
        {[
          ['Grade', game.grade?.name],
          ['Season', game.season],
          ['Round', game.round],
          ['Venue', game.venue],
          ['Date', game.played_at ? new Date(game.played_at).toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) : null],
          ['Time', game.time],
        ].filter(([, v]) => v).map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-3">
            <span className="section-label w-20 shrink-0">{label}</span>
            <span className="text-slate-300 text-sm">{value}</span>
          </div>
        ))}
      </div>

      <div className="card p-5 border-dashed">
        <p className="text-slate-500 text-sm text-center">
          Detailed batting &amp; bowling scorecards are not available at this data tier.
          {game.url && (
            <> View the full scorecard on{' '}
              <a href={game.url} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                PlayHQ ↗
              </a>
            </>
          )}
        </p>
      </div>
    </div>
  )
}
