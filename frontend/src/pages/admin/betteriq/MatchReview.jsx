/* BetterIQ — Match review: an automatic post-match read of a completed game.
   Scorecard-derived only (no ball-by-ball), so the synthesis covers the
   scoreline, who delivered, the best stand, extras and any collapse. */
import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Card, Note, Tag, Btn, Empty, PageIntro, LoadingCard, fmtCount, fmtOvers } from './ui'
import { useIQFilter, effectiveSeasonId, effectiveSeasonIds } from './Context'
import { PlayerLink } from './PlayerLink'

const ord = (k) => ({ 1: '1st', 2: '2nd', 3: '3rd' }[k] || `${k}th`)

// Backend `result` is a full word (WIN | LOSS | DRAW | TIE) — normalise to a code.
const rc = (r) => { const s = String(r || '').toUpperCase(); return s.startsWith('W') ? 'W' : s.startsWith('L') ? 'L' : s.startsWith('T') ? 'T' : 'D' }
const RESULT_LABEL = { W: 'Won', L: 'Lost', D: 'Draw', T: 'Tie' }
const resultColor = (r) => { const k = rc(r); return k === 'W' ? 'var(--pb-brand)' : k === 'L' ? 'var(--pb-red)' : 'var(--pb-amber)' }
const resultTone = (r) => { const k = rc(r); return k === 'W' ? 'win' : k === 'L' ? 'red' : 'amber' }

/* ── Recent-games picker ─────────────────────────────────────────────────── */
function GamePicker({ games, selected, onPick }) {
  return (
    <div className="iq-card p-2 lg:sticky lg:top-20">
      <div className="iq-eyebrow px-2 py-2">Recent games</div>
      <div className="space-y-0.5">
        {games.map((g) => {
          const on = g.game_id === selected
          const c = resultColor(g.result)
          return (
            <button
              key={g.game_id}
              onClick={() => onPick(g.game_id)}
              className="w-full flex items-center gap-3 px-2.5 py-2.5 text-left transition"
              style={{ borderRadius: 9, background: on ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent' }}
              onMouseEnter={(e) => { if (!on) e.currentTarget.style.background = 'var(--pb-surface2)' }}
              onMouseLeave={(e) => { if (!on) e.currentTarget.style.background = 'transparent' }}
            >
              <span
                className="iq-mono inline-flex items-center justify-center font-bold shrink-0"
                style={{ width: 22, height: 22, fontSize: 11, borderRadius: 6, color: c, background: `color-mix(in srgb, ${c} 16%, transparent)` }}
              >
                {rc(g.result)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-[13.5px] truncate" style={{ color: on ? 'var(--pb-accent)' : 'var(--pb-text)' }}>
                  vs {g.opponent}
                </div>
                <div className="text-pb-faint text-[11px] iq-num">
                  {[g.grade, g.date].filter(Boolean).join(' · ')}{g.is_final ? ' · Final' : ''}
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/* ── Detail: an automatic post-match read of the selected game ───────────── */
function GameReviewDetail({ review }) {
  if (review === null) {
    return <LoadingCard label="Reviewing the game…" expectedMs={5000} />
  }
  if (review?.error || !review?.game) {
    return <div className="iq-card p-6"><Empty>Couldn't load this game.</Empty></div>
  }

  const g = review.game
  const color = resultColor(g.result)
  const bat = review.top_batting || []
  const bowl = review.top_bowling || []
  const bp = review.best_partnership
  const collapse = review.collapse
  const notes = review.coverage?.notes || []

  return (
    <div className="iq-fade space-y-5">
      {/* scoreline */}
      <Card accent>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <div className="iq-eyebrow" style={{ color: 'var(--pb-accent)' }}>
              Match review{g.date ? ` · ${g.date}` : ''}
            </div>
            <h2 className="iq-headline mt-2" style={{ fontSize: 'clamp(24px,3vw,34px)' }}>vs {g.opponent}</h2>
            <div className="text-pb-faint text-[12.5px] mt-1.5">{[g.grade, g.venue].filter(Boolean).join(' · ')}</div>
          </div>
          <div className="text-right shrink-0">
            <div className="iq-headline" style={{ fontSize: 26, color }}>{RESULT_LABEL[rc(g.result)] || '—'}</div>
            {g.is_final && <div className="mt-1.5"><Tag tone="amber">Final</Tag></div>}
          </div>
        </div>
        <div className="flex items-center gap-5 mt-5 pt-5" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
          <div>
            <div className="iq-eyebrow mb-1">Us</div>
            <div className="iq-headline iq-num" style={{ fontSize: 28 }}>{g.our_score ?? '—'}</div>
          </div>
          <div className="text-pb-faintest text-2xl">vs</div>
          <div className="min-w-0">
            <div className="iq-eyebrow mb-1 truncate">{g.opponent}</div>
            <div className="iq-headline iq-num" style={{ fontSize: 28, color: 'var(--pb-dim)' }}>{g.their_score ?? '—'}</div>
          </div>
        </div>
      </Card>

      {/* turning point (synthesised) */}
      {review.summary?.length > 0 && (
        <Card eyebrow="the synthesis" title="What changed the game">
          <ul className="space-y-1.5 text-[14.5px] leading-relaxed">
            {review.summary.map((s, i) => (
              <li key={i} className="flex gap-2">
                <span style={{ color: 'var(--pb-accent)' }}>›</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* top performers */}
      <div className="grid gap-5 lg:grid-cols-2 items-start">
        <Card eyebrow="top scorers" title="Batting">
          {bat.length === 0 ? <Empty>No batting recorded.</Empty> : (
            <div className="space-y-2.5">
              {bat.map((p, i) => (
                <div key={i} className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="iq-num text-pb-faint w-4 shrink-0">{i + 1}</span>
                    <span className="font-semibold text-[14px] truncate"><PlayerLink id={p.player_id}>{p.name}</PlayerLink></span>
                  </div>
                  <span className="iq-num text-pb-dim text-[13px] whitespace-nowrap">
                    {p.runs}{p.not_out ? '*' : ''}{p.balls != null ? ` (${p.balls})` : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card eyebrow="leading wicket-takers" title="Bowling">
          {bowl.length === 0 ? <Empty>No bowling recorded.</Empty> : (
            <div className="space-y-2.5">
              {bowl.map((p, i) => (
                <div key={i} className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="iq-num text-pb-faint w-4 shrink-0">{i + 1}</span>
                    <span className="font-semibold text-[14px] truncate"><PlayerLink id={p.player_id}>{p.name}</PlayerLink></span>
                  </div>
                  <span className="iq-num font-semibold text-[13.5px] whitespace-nowrap">
                    {p.wickets ?? 0}/{p.runs ?? 0}{p.overs != null ? ` (${fmtOvers(p.overs)})` : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* trio: best stand · extras · collapse */}
      <div className="grid gap-5 sm:grid-cols-3">
        <Card eyebrow="best stand">
          {bp ? (
            <>
              <div className="iq-headline iq-num" style={{ fontSize: 26 }}>{fmtCount(bp.runs)}</div>
              <div className="text-pb-dim text-[12.5px] mt-1 leading-snug">
                {bp.batters}{bp.wicket ? ` · ${ord(bp.wicket)} wkt` : ''}
              </div>
            </>
          ) : <Empty>—</Empty>}
        </Card>
        <Card eyebrow="extras conceded">
          <div className="iq-headline iq-num" style={{ fontSize: 26 }}>{fmtCount(review.extras_conceded ?? 0)}</div>
          <div className="text-pb-dim text-[12.5px] mt-1">wides + no-balls</div>
        </Card>
        <Card eyebrow="key collapse">
          {collapse ? (
            <>
              <div className="iq-headline iq-num" style={{ fontSize: 26, color: 'var(--pb-red)' }}>3 for {fmtCount(collapse.runs)}</div>
              <div className="text-pb-dim text-[12.5px] mt-1 leading-snug">from the {ord(collapse.start_wicket)} wicket</div>
            </>
          ) : (
            <div className="text-pb-faint text-[13px] leading-snug">No collapse — wickets fell steadily.</div>
          )}
        </Card>
      </div>

      <Note>
        {notes.length > 0
          ? notes.join(' ')
          : 'Read generated from the scorecard — no ball-by-ball, so phase/pressure detail isn’t available.'}
      </Note>
    </div>
  )
}

export default function MatchReview() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { ctx, seasons } = useIQFilter()
  const seasonId = effectiveSeasonId(ctx)
  const seasonIds = effectiveSeasonIds(ctx, seasons)  // Compare mode: the WHOLE range, not just its newest end
  const gradeId = ctx?.team?.id || undefined
  const [games, setGames] = useState(null)
  const [gameId, setGameId] = useState(searchParams.get('game') || null)
  const [review, setReview] = useState(null)

  // Follow the global Season + Team filter — the review list is the games it scopes.
  useEffect(() => {
    setGames(null)
    api.iqReviewGames(seasonIds ? undefined : seasonId, gradeId, seasonIds).then(setGames).catch(() => setGames([]))
  }, [seasonId, gradeId, seasonIds ? seasonIds.join(',') : ''])  // eslint-disable-line react-hooks/exhaustive-deps

  // Default to the most recent game once the list loads (the detail pane is
  // always populated, mirroring the design) — unless the URL already pins one.
  useEffect(() => {
    if (games && games.length > 0 && !gameId) {
      setGameId(games[0].game_id)
    }
  }, [games, gameId])

  useEffect(() => {
    if (!gameId) { setReview(null); return }
    let alive = true
    setReview(null)
    api.iqGameReview(gameId)
      .then((d) => { if (alive) setReview(d) })
      .catch(() => { if (alive) setReview({ error: true }) })
    return () => { alive = false }
  }, [gameId])

  const pick = (id) => { setGameId(id); setSearchParams({ game: id }, { replace: true }) }

  return (
    <IQLayout
      title="Match review"
      actions={gameId && <Btn variant="ghost" sm icon="refresh" onClick={() => pick(gameId)}>Re-read</Btn>}
    >
      <PageIntro>An automatic read of every completed game — the scoreline, what swung it, and who delivered.</PageIntro>

      {games === null ? (
        <LoadingCard label="Loading games…" expectedMs={4500} />
      ) : games.length === 0 ? (
        <div className="iq-card p-6"><Empty>No completed games to review yet.</Empty></div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[280px_1fr] items-start">
          <GamePicker games={games} selected={gameId} onPick={pick} />
          <GameReviewDetail review={review} />
        </div>
      )}
    </IQLayout>
  )
}
