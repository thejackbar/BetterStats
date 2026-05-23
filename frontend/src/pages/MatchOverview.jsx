import { useParams, useSearchParams } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { PbSpinner, ResultPill } from '../lib/presskit'

function ResultBanner({ game }) {
  const isWin = game.result === 'WIN'
  const isDraw = ['DRAW', 'TIE', 'NO_RESULT'].includes(game.result)

  return (
    <div className={`pb-card p-5 mb-5 ${
      isWin ? 'border-pb-accent/30' : isDraw ? 'border-pb-faintest' : 'border-pb-red/30'
    }`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {(game.season || game.grade?.name) && (
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">
              {[game.grade?.name, game.season, game.round].filter(Boolean).join(' · ')}
            </p>
          )}
          <h2 className="font-display font-bold text-[24px] md:text-[30px] text-pb-text leading-tight tracking-tight">
            {game.home_team}
            <span className="text-pb-faint font-sans font-normal text-lg mx-2">vs</span>
            {game.away_team}
          </h2>
          {game.played_at && (
            <p className="text-pb-faint text-sm mt-1">
              {new Date(game.played_at).toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
            </p>
          )}
          {game.venue && <p className="font-mono text-[10px] text-pb-faintest mt-0.5">{game.venue}</p>}
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          <ResultPill result={game.result || 'N/R'} />
          {game.winning_team && (
            <p className="font-mono text-[11px] text-pb-faint">{game.winning_team} won</p>
          )}
        </div>
      </div>
    </div>
  )
}

function CompetitorCard({ competitor, isWinner }) {
  const innings = competitor.innings || []
  const hasMultipleInnings = innings.length > 1

  return (
    <div className={`pb-card p-4 flex flex-col gap-2 ${isWinner ? 'border-pb-accent/40' : ''}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {isWinner && <span className="font-mono text-[10px] tracking-wide3 block mb-0.5" style={{ color: 'var(--pb-accent)' }}>WINNER</span>}
          <p className="text-pb-text font-medium text-sm leading-tight">{competitor.name}</p>
          <p className="font-mono text-[10px] text-pb-faint mt-0.5">{competitor.is_home ? 'Home' : 'Away'}</p>
        </div>
        <div className="text-right shrink-0">
          <p className={`font-mono text-[30px] font-bold leading-none pb-num ${isWinner ? '' : 'text-pb-text'}`}
            style={isWinner ? { color: 'var(--pb-accent)' } : {}}>
            {competitor.score ?? '—'}
          </p>
        </div>
      </div>

      {hasMultipleInnings && (
        <div className="pb-hairline-t pt-2 space-y-1">
          {innings.map((inn, i) => (
            <div key={i} className="flex justify-between items-baseline">
              <span className="font-mono text-[10px] text-pb-faint">
                {inn.innings_number === 1 ? '1st innings' : inn.innings_number === 2 ? '2nd innings' : `Innings ${inn.innings_number}`}
              </span>
              <span className="font-mono text-sm text-pb-dim">
                {inn.score ?? '—'}
                {inn.declared && <span className="font-mono text-[10px] text-pb-faint ml-1">dec</span>}
              </span>
            </div>
          ))}
        </div>
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

  if (loading) return <PbSpinner message="Loading match…" />
  if (error) return (
    <div className="min-h-screen bg-pb-bg flex items-center justify-center">
      <p className="text-pb-red font-mono text-sm">Error: {error}</p>
    </div>
  )
  if (!game) return null

  const competitors = game.competitors || []
  const hasCompetitors = competitors.length > 0
  const hasScores = hasCompetitors
    ? competitors.some(c => c.score != null)
    : (game.home_score != null || game.away_score != null)

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-4xl mx-auto px-4 py-8">
        <button
          onClick={() => window.history.back()}
          className="font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors mb-5 flex items-center gap-1"
        >
          ← BACK
        </button>

        <ResultBanner game={game} />

        {hasScores && (
          <div className="mb-5">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Scores</p>
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
                <div className="pb-card p-4">
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">
                    {game.home_team === game.winning_team ? 'WINNER · HOME' : 'HOME'}
                  </p>
                  <p className="text-pb-text text-sm font-medium mb-2 truncate">{game.home_team}</p>
                  <p className="font-mono text-[36px] font-bold leading-none pb-num" style={{ color: 'var(--pb-accent)' }}>{game.home_score ?? '—'}</p>
                </div>
                <div className="pb-card p-4">
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">
                    {game.away_team === game.winning_team ? 'WINNER · AWAY' : 'AWAY'}
                  </p>
                  <p className="text-pb-text text-sm font-medium mb-2 truncate">{game.away_team}</p>
                  <p className="font-mono text-[36px] font-bold text-pb-text leading-none pb-num">{game.away_score ?? '—'}</p>
                </div>
              </div>
            )}
          </div>
        )}

        {game.url && (
          <div className="pb-card p-4 mb-5 flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="text-pb-text text-sm font-medium">Full scorecard</p>
              <p className="font-mono text-[10px] text-pb-faint mt-0.5">Batting &amp; bowling figures online</p>
            </div>
            <a
              href={game.url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg shrink-0 flex items-center gap-2"
              style={{ background: 'var(--pb-accent)' }}
            >
              VIEW ON PLAYHQ
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </div>
        )}

        <div className="pb-card p-5">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">Match Details</p>
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
                <span className="font-mono text-[10px] tracking-wide2 text-pb-faint w-14 shrink-0 text-right">{label.toUpperCase()}</span>
                <span className="text-pb-dim text-sm">{value}</span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
