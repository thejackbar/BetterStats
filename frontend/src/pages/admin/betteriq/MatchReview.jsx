import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Btn, Tag, Empty } from '../betterselect/ui'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)
const ord = (k) => ({ 1: '1st', 2: '2nd', 3: '3rd' }[k] || `${k}th`)

function Card({ title, right, children, accent = false }) {
  return (
    <div className="pb-card p-4 md:p-5" style={accent ? { borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' } : undefined}>
      {(title || right) && (
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="font-display font-bold">{title}</h3>
          {right}
        </div>
      )}
      {children}
    </div>
  )
}

const RESULT_TONE = { WIN: 'var(--pb-brand)', LOSS: 'var(--pb-red)', DRAW: 'var(--pb-faint)', TIE: 'var(--pb-faint)' }
const RESULT_LABEL = { WIN: 'Won', LOSS: 'Lost', DRAW: 'Draw', TIE: 'Tie' }

function ResultDot({ result }) {
  return <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: RESULT_TONE[result] || 'var(--pb-faintest)' }} />
}

export default function MatchReview() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [games, setGames] = useState(null)
  const [gameId, setGameId] = useState(searchParams.get('game') || null)
  const [review, setReview] = useState(null)

  useEffect(() => {
    api.iqReviewGames().then(setGames).catch(() => setGames([]))
  }, [])

  useEffect(() => {
    if (!gameId) { setReview(null); return }
    let alive = true
    setReview(null)
    api.iqGameReview(gameId).then(d => { if (alive) setReview(d) }).catch(() => { if (alive) setReview({ error: true }) })
    return () => { alive = false }
  }, [gameId])

  const pick = (id) => { setGameId(id); setSearchParams({ game: id }, { replace: true }) }
  const clear = () => { setGameId(null); setReview(null); setSearchParams({}, { replace: true }) }

  // ── Detail view ──
  if (gameId) {
    const g = review?.game
    return (
      <IQLayout title="Match review" actions={<Btn variant="ghost" sm icon="back" onClick={clear}>All games</Btn>}>
        {review === null && <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Reviewing the game…</div>}
        {review?.error && <div className="pb-card p-5"><Empty>Couldn't load this game.</Empty></div>}
        {review && !review.error && g && (
          <>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <h2 className="font-display font-bold text-2xl">vs {g.opponent}</h2>
              {g.result && <Tag tone={g.result === 'WIN' ? 'accent' : undefined}>{RESULT_LABEL[g.result] || g.result}</Tag>}
              {g.is_final && <Tag>Final</Tag>}
            </div>
            <div className="text-pb-faint text-sm mb-4 flex flex-wrap gap-x-4 gap-y-1">
              {g.date && <span>{g.date}</span>}
              {g.grade && <span>{g.grade}</span>}
              {g.venue && <span>{g.venue}</span>}
            </div>

            <Card title="Scoreline">
              <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
                <div><div className="font-display font-bold text-2xl pb-num leading-none">{g.our_score ?? '—'}</div><div className="text-pb-faint text-[10px] uppercase tracking-wide2 mt-1">Us</div></div>
                <div className="text-pb-faintest font-display text-xl">vs</div>
                <div><div className="font-display font-bold text-2xl pb-num leading-none">{g.their_score ?? '—'}</div><div className="text-pb-faint text-[10px] uppercase tracking-wide2 mt-1">{g.opponent}</div></div>
              </div>
            </Card>

            {review.summary?.length > 0 && (
              <div className="mt-4"><Card title="What changed the game" accent>
                <ul className="space-y-1.5 text-sm">
                  {review.summary.map((s, i) => <li key={i} className="flex gap-2"><span style={{ color: 'var(--pb-accent)' }}>›</span><span>{s}</span></li>)}
                </ul>
              </Card></div>
            )}

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              {review.top_batting?.length > 0 && (
                <Card title="Top batting">
                  <table className="w-full text-sm">
                    <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left"><th className="py-1 font-medium">Batter</th><th className="py-1 font-medium text-right">Runs</th><th className="py-1 font-medium text-right">Balls</th><th className="py-1 font-medium text-right">4s/6s</th></tr></thead>
                    <tbody>
                      {review.top_batting.map((b, i) => (
                        <tr key={i} className="border-t pb-hairline">
                          <td className="py-1.5 truncate max-w-[160px]">{b.name}</td>
                          <td className="py-1.5 text-right pb-num font-semibold">{b.runs}{b.not_out ? '*' : ''}</td>
                          <td className="py-1.5 text-right pb-num text-pb-faint">{num(b.balls)}</td>
                          <td className="py-1.5 text-right pb-num text-pb-faint">{num(b.fours, 0)}/{num(b.sixes, 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
              )}
              {review.top_bowling?.length > 0 && (
                <Card title="Top bowling">
                  <table className="w-full text-sm">
                    <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left"><th className="py-1 font-medium">Bowler</th><th className="py-1 font-medium text-right">O</th><th className="py-1 font-medium text-right">M</th><th className="py-1 font-medium text-right">R</th><th className="py-1 font-medium text-right">W</th></tr></thead>
                    <tbody>
                      {review.top_bowling.map((b, i) => (
                        <tr key={i} className="border-t pb-hairline">
                          <td className="py-1.5 truncate max-w-[160px]">{b.name}</td>
                          <td className="py-1.5 text-right pb-num text-pb-faint">{num(b.overs)}</td>
                          <td className="py-1.5 text-right pb-num text-pb-faint">{num(b.maidens, 0)}</td>
                          <td className="py-1.5 text-right pb-num">{num(b.runs)}</td>
                          <td className="py-1.5 text-right pb-num font-semibold">{num(b.wickets, 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
              )}
            </div>

            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <Card title="Best partnership">
                {review.best_partnership ? (
                  <div>
                    <div className="font-display font-bold text-2xl pb-num leading-none">{review.best_partnership.runs}</div>
                    <div className="text-pb-faint text-[12px] mt-1">{review.best_partnership.batters}{review.best_partnership.wicket ? ` · ${ord(review.best_partnership.wicket)} wkt` : ''}</div>
                  </div>
                ) : <Empty>—</Empty>}
              </Card>
              <Card title="Extras conceded">
                <div className="font-display font-bold text-2xl pb-num leading-none">{num(review.extras_conceded, 0)}</div>
                <div className="text-pb-faint text-[12px] mt-1">wides + no-balls</div>
              </Card>
              <Card title="Collapse">
                {review.collapse ? (
                  <div>
                    <div className="font-display font-bold text-2xl pb-num leading-none" style={{ color: 'var(--pb-red)' }}>3 for {review.collapse.runs}</div>
                    <div className="text-pb-faint text-[12px] mt-1">from the {ord(review.collapse.start_wicket)} wicket</div>
                  </div>
                ) : <div className="text-pb-faint text-sm">No collapse — wickets fell steadily.</div>}
              </Card>
            </div>

            {review.coverage?.notes?.length > 0 && (
              <div className="text-pb-faintest text-[11px] mt-4">{review.coverage.notes.join(' ')}</div>
            )}
          </>
        )}
      </IQLayout>
    )
  }

  // ── Overview / picker ──
  return (
    <IQLayout title="Match review">
      <p className="text-pb-faint text-sm mb-4 max-w-2xl">Pick a recent game for an automatic post-match read — top contributions, the best stand, extras, any collapse, and what changed the game.</p>
      {games === null ? (
        <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Loading games…</div>
      ) : games.length === 0 ? (
        <div className="pb-card p-5"><Empty>No completed games to review yet.</Empty></div>
      ) : (
        <div className="pb-card divide-y pb-hairline">
          {games.map(g => (
            <button key={g.game_id} onClick={() => pick(g.game_id)}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-pb-surface2 transition-colors">
              <ResultDot result={g.result} />
              <span className="font-medium truncate flex-1">vs {g.opponent}{g.is_final ? <span className="text-pb-faintest text-[11px] ml-2">Final</span> : ''}</span>
              <span className="text-pb-faintest text-[11px] whitespace-nowrap hidden sm:block">{g.grade}</span>
              <span className="text-pb-faint text-[12px] pb-num whitespace-nowrap w-24 text-right">{g.date || ''}</span>
            </button>
          ))}
        </div>
      )}
    </IQLayout>
  )
}
