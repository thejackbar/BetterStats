import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import { FantasyFrame, useFantasySeason } from './shared'

// Round winners: who topped each scored round on the club-wide ladder, the full table for any round,
// and how many rounds each team has won. Worked out from the stored round scores on every load
// (services/fantasy_round_rank), so every round already scored is here with nothing to backfill, and
// a round that is unsettled drops out until it is settled again. A tie for first is a shared win.

const CHIP = { wildcard: 'Wildcard', free_hit: 'Free hit', bench_boost: 'Bench boost', triple_captain: 'Triple captain' }
const pts = (n) => (Number.isInteger(Number(n)) ? String(Number(n)) : Number(n).toFixed(1))
const fmtDay = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
const span = (r) => (!r.start_date ? '' : (!r.end_date || r.end_date === r.start_date ? fmtDay(r.start_date) : `${fmtDay(r.start_date)} to ${fmtDay(r.end_date)}`))

export default function FantasyWinners() {
  const { season, loading, msg, err, fail } = useFantasySeason()
  const seasonId = season?.id
  const [data, setData] = useState(null)
  const [sel, setSel] = useState(null)

  const load = useCallback(async () => {
    if (!seasonId) return
    try {
      const d = await api.fantasyRoundWinners(seasonId)
      setData(d)
      setSel(prev => (prev != null && d.rounds.some(r => r.number === prev)) ? prev : (d.rounds.length ? d.rounds[d.rounds.length - 1].number : null))
    } catch (e) { fail(e) }
  }, [seasonId, fail])
  useEffect(() => { load() }, [load])

  const rounds = data?.rounds || []
  const idx = rounds.findIndex(r => r.number === sel)
  const cur = idx >= 0 ? rounds[idx] : null
  const btn = 'w-8 h-8 rounded-full border pb-hairline bg-pb-surface text-pb-faint hover:text-pb-text disabled:opacity-30 disabled:cursor-default'

  return (
    <FantasyFrame title="Round winners" season={season} loading={loading} msg={msg} err={err}>
      {season && (
        <div className="space-y-6">
          {!data ? <p className="text-sm text-pb-faint">Loading…</p> : !rounds.length ? (
            <div className="pb-card p-5 text-sm text-pb-faint">
              No round has been scored yet. Winners show up here as each round is confirmed on the Overview page, and
              any round already confirmed appears straight away.
            </div>
          ) : (
            <div className="grid lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 space-y-4">
                <div className="flex items-center gap-2">
                  <button aria-label="Previous round" className={btn} disabled={idx <= 0} onClick={() => setSel(rounds[idx - 1].number)}>‹</button>
                  <select aria-label="Round" value={sel ?? ''} onChange={e => setSel(Number(e.target.value))}
                    className="flex-1 min-w-0 bg-pb-surface border pb-hairline rounded px-2 py-1.5 text-sm font-medium">
                    {rounds.map(r => <option key={r.number} value={r.number}>{`Round ${r.number}${span(r) ? ` · ${span(r)}` : ''}`}</option>)}
                  </select>
                  <button aria-label="Next round" className={btn} disabled={idx < 0 || idx >= rounds.length - 1} onClick={() => setSel(rounds[idx + 1].number)}>›</button>
                </div>

                {cur && (
                  <>
                    <div className="pb-card p-5" data-testid="admin-round-winner">
                      <div className="text-[11px] uppercase tracking-wide text-pb-faint">
                        {cur.winners.length > 1 ? `Round ${cur.number} shared win` : `Round ${cur.number} winner`}
                      </div>
                      {!cur.winners.length ? <p className="text-sm text-pb-faint mt-1">No winner. Nobody scored in this round.</p> : cur.winners.map(w => (
                        <div key={w.squad_id} className="flex items-baseline gap-3 mt-1">
                          <div className="flex-1 min-w-0">
                            <span className="font-display font-bold text-lg">{w.team_name}</span>
                            <span className="text-sm text-pb-faint ml-2">{w.manager}{w.chip ? ` · ${CHIP[w.chip] || w.chip}` : ''}</span>
                          </div>
                          <span className="font-display font-bold text-2xl">{pts(w.points)}</span>
                        </div>
                      ))}
                      {cur.margin != null && <div className="text-xs text-pb-faint mt-2">{pts(cur.margin)} {cur.margin === 1 ? 'point' : 'points'} clear of second.</div>}
                    </div>

                    <div className="pb-card p-5">
                      <div className="text-xs text-pb-faint mb-2">{cur.teams} {cur.teams === 1 ? 'team' : 'teams'} played this round. Points are after any transfer hit.</div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead className="text-pb-faint text-left">
                            <tr><th className="py-1.5 pr-3 w-10">#</th><th className="py-1.5 pr-3">Team</th><th className="py-1.5 pr-3">Manager</th><th className="py-1.5 pr-3">Chip</th><th className="py-1.5 pr-3 text-right">Hit</th><th className="py-1.5 text-right">Points</th></tr>
                          </thead>
                          <tbody>
                            {cur.ranking.map(r => (
                              <tr key={r.squad_id} className="border-t pb-hairline">
                                <td className="py-1.5 pr-3 font-semibold">{r.rank}</td>
                                <td className="py-1.5 pr-3 font-medium">{r.winner && <span aria-label="Round winner" className="mr-1">🏆</span>}{r.team_name}</td>
                                <td className="py-1.5 pr-3 text-pb-faint">{r.manager}</td>
                                <td className="py-1.5 pr-3 text-pb-faint">{r.chip ? CHIP[r.chip] || r.chip : '–'}</td>
                                <td className="py-1.5 pr-3 text-right text-pb-faint">{r.transfer_hit ? `-${r.transfer_hit}` : '–'}</td>
                                <td className="py-1.5 text-right font-semibold">{pts(r.points)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                )}
              </div>

              <div className="space-y-4">
                <div className="pb-card p-5">
                  <h3 className="font-display font-bold mb-2">Round by round</h3>
                  <div data-testid="admin-round-history">
                    {[...rounds].reverse().map(r => (
                      <button key={r.number} onClick={() => setSel(r.number)} aria-label={`Show round ${r.number}`}
                        className={`flex items-center gap-2 w-full text-left py-1.5 border-t pb-hairline text-sm ${r.number === sel ? 'text-pb-accent' : ''}`}>
                        <span className="w-8 text-pb-faint font-semibold">R{r.number}</span>
                        <span className="flex-1 min-w-0 truncate">{r.winners.length ? r.winners.map(w => w.team_name).join(' and ') : 'No winner'}</span>
                        {r.winners.length > 0 && <span className="text-pb-faint">{pts(r.top_points)}</span>}
                      </button>
                    ))}
                  </div>
                </div>
                {data.tally.length > 0 && (
                  <div className="pb-card p-5">
                    <h3 className="font-display font-bold mb-2">Most round wins</h3>
                    <div data-testid="admin-round-tally">
                      {data.tally.map(t => (
                        <div key={t.squad_id} className="flex items-center gap-2 py-1.5 border-t pb-hairline text-sm">
                          <div className="flex-1 min-w-0">
                            <div className="truncate font-medium">{t.team_name}</div>
                            <div className="text-xs text-pb-faint truncate">Rounds {t.rounds.join(', ')}</div>
                          </div>
                          <span className="font-display font-bold text-lg">{t.wins}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </FantasyFrame>
  )
}
