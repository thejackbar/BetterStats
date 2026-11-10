import { useState, useEffect, useCallback } from 'react'
import BetterFantasyLayout from '../../../components/admin/BetterFantasyLayout'
import { api } from '../../../lib/api'
import { Btn } from './shared'

// BetterFantasyCricket admin Overview — create the season, mint and share the
// public link, run the engine (build pool, generate rounds, sync running scores,
// confirm final scores) and see the rounds. The other tools (team make-up, scoring, the pool, registered players)
// each have their own side-menu page.

// Casual date-time for a round's lock time, and an editor for it. After the lock
// time managers' XI, captain and chips are frozen and their transfers wait for the
// next round. A time set here is kept when the rounds are refreshed from the draw.
const fmtLock = (iso) => new Date(iso).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
const toInput = (iso) => {
  const d = new Date(iso), p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

const fmtTime = (iso) => new Date(iso).toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`
const fmtDay = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
const fmtSpan = ([a, b]) => (!b || a === b ? fmtDay(a) : `${fmtDay(a)} to ${fmtDay(b)}`)

// What the round's stored status is called on screen. The words "scored" and "unsettled" are the
// engine's; a club admin reads "confirmed" (final points are locked in) and "reopened".
const STATUS_WORD = { scored: 'confirmed', unsettled: 'reopened' }

// The three things an admin can do to a round's scores, in plain words. Shown above the table so the
// buttons are not guesswork.
const SCORE_ACTIONS = [
  ['Sync scores', 'Re-reads the scorecards from Play-Cricket now. Use it when a game has finished and a score looks missing. Points stay running scores, nothing is locked in.'],
  ['Confirm final scores', 'Locks in the round\'s points once its games are done. The ladder and prices move, and managers get their free transfer.'],
  ['Reopen round', 'Takes a confirmed round back to running scores, for one confirmed too early or by mistake. Chips and transfers managers made are kept.'],
]

function RowBtn({ onClick, busy, kind = 'ghost', children }) {
  const cls = kind === 'accent' ? 'bg-pb-accent text-white hover:opacity-90' : 'border pb-hairline text-pb-text hover:bg-pb-surface2'
  return <button onClick={onClick} disabled={busy} className={`px-2.5 py-1 rounded text-xs font-medium disabled:opacity-50 ${cls}`}>{busy ? '…' : children}</button>
}

function LockCell({ r, onChanged, flash, fail }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState('')
  const [busy, setBusy] = useState(false)
  if (!r.lock_at) return <span className="text-pb-faint">–</span>
  const save = async (iso) => {
    setBusy(true)
    try {
      const res = await api.fantasySetRoundLock(r.id, iso)
      flash(res.warning || (iso ? 'Lock time saved.' : 'Back to the default lock time.'))
      setEditing(false); await onChanged()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }
  if (r.status === 'scored') return <span className="text-pb-faint whitespace-nowrap">{fmtLock(r.lock_at)}</span>
  if (!editing) {
    return (
      <div className="whitespace-nowrap">
        {fmtLock(r.lock_at)}
        {r.lock_manual && <span className="ml-1 text-[10px] text-pb-accent">set</span>}
        <button onClick={() => { setVal(toInput(r.lock_at)); setEditing(true) }} className="ml-2 text-xs underline text-pb-faint hover:text-pb-text">Change</button>
      </div>
    )
  }
  return (
    <div className="space-y-1">
      <input type="datetime-local" value={val} onChange={e => setVal(e.target.value)}
        className="rounded border pb-hairline bg-pb-surface px-2 py-1 text-xs" />
      <div className="flex gap-2 text-xs">
        <button disabled={busy || !val} onClick={() => save(new Date(val).toISOString())} className="px-2 py-0.5 rounded bg-pb-accent text-white disabled:opacity-50">Save</button>
        {r.lock_manual && <button disabled={busy} onClick={() => save(null)} className="underline text-pb-faint hover:text-pb-text">Use the default</button>}
        <button disabled={busy} onClick={() => setEditing(false)} className="underline text-pb-faint hover:text-pb-text">Cancel</button>
      </div>
    </div>
  )
}

export default function FantasyHome() {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)       // { season, link_token, counts }
  const [rounds, setRounds] = useState(null)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState('')
  const [realign, setRealign] = useState(null)   // scored rounds whose dates disagree with the draw
  const [year, setYear] = useState(new Date().getFullYear())

  const flash = (m) => { setMsg(m); setErr(null); setTimeout(() => setMsg(null), Math.max(4000, String(m).length * 90)) }
  const fail = (e) => { setErr(e.message || String(e)); setMsg(null) }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.fantasyGetSeason()
      setData(d)
      if (d.season) {
        const r = await api.fantasyListRounds(d.season.id).catch(() => ({ rounds: [] }))
        setRounds(r.rounds)
        setRealign(await api.fantasyRealignPlan(d.season.id).catch(() => null))
      } else setRealign(null)
    } catch (e) { fail(e) } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const run = (key, fn, after) => async () => {
    setBusy(key); setErr(null)
    try { const res = await fn(); flash(after(res)); await load() }
    catch (e) { fail(e) } finally { setBusy('') }
  }

  const season = data?.season
  const createSeason = run('create', () => api.fantasyCreateSeason(Number(year)), () => 'Season created.')
  const buildPool = run('pool', () => api.fantasyBuildPool(season.id), (r) => `Pool built: ${r.pool} players.`)
  const genRounds = run('rounds', () => api.fantasyGenerateRounds(season.id), (r) => r.detail || `Generated ${r.rounds} rounds.`)
  const syncScores = run('sync', () => api.fantasySyncScores(season.id), (r) => {
    if (!r.ran) return r.message || 'Nothing to sync right now.'
    if (!r.players_moved) return `Checked ${plural(r.games_checked, 'game')} in play. No scores have changed since the last look.`
    return `Checked ${plural(r.games_checked, 'game')} in play. ${plural(r.players_moved, 'player')} moved. These points are running scores until the round is confirmed.`
  })
  const fixDates = async () => {
    const lines = realign.changes.map(c => `Round ${c.round_number}: ${fmtSpan(c.stored)} becomes ${fmtSpan(c.draw)}`).join('\n')
    if (!window.confirm(`Move these rounds to the draw's dates?\n\n${lines}\n\nA round that only gets longer is confirmed again with its extra games. A round that moves to different games is reopened first and shows running points. Nothing a manager did is changed.`)) return
    setBusy('realign'); setErr(null)
    try { const r = await api.fantasyRealignApply(season.id); flash(`Moved ${plural(r.realigned.length, 'round')} to the draw's dates.`); await load() }
    catch (e) { fail(e) } finally { setBusy('') }
  }
  const toggleLive = async () => {
    setBusy('live'); try { await api.fantasyUpdateRules(season.id, { live_sync: !(season.rules?.live_sync !== false) }); await load() }
    catch (e) { fail(e) } finally { setBusy('') }
  }
  const settleDue = run('settle', () => api.fantasySettleDue(season.id), (r) => `Confirmed ${plural(r.rounds_settled, 'finished round')}` + (r.rounds_refreshed ? `, updated points for ${r.rounds_refreshed} in progress` : '') + (r.rounds_refreshed_late ? `, brought ${r.rounds_refreshed_late} recent round(s) up to date with late scorecards` : '') + '.')
  const deleteSeason = async () => {
    if (!window.confirm('Delete this fantasy season and its pool and rounds? This cannot be undone.')) return
    setBusy('delete'); setErr(null)
    try { await api.fantasyDeleteSeason(season.id); flash('Season deleted.'); await load() }
    catch (e) { fail(e) } finally { setBusy('') }
  }

  const linkUrl = data?.link_token ? `${window.location.origin}/fantasy/${data.link_token}` : ''
  const copy = async (txt, label) => { try { await navigator.clipboard.writeText(txt); flash(`${label} copied.`) } catch { fail(new Error('Copy failed')) } }
  const toggleReg = async () => {
    setBusy('reg'); try { await api.fantasySetRegistration(season.id, !season.registration_open); await load() }
    catch (e) { fail(e) } finally { setBusy('') }
  }
  const regenerate = async () => {
    if (!window.confirm('Make a new link? The old one stops working.')) return
    setBusy('regen'); try { await api.fantasyRegenerateLink(); flash('New link created.'); await load() }
    catch (e) { fail(e) } finally { setBusy('') }
  }
  const unsettleOne = async (r) => {
    if (!window.confirm(`Reopen ${r.name || `Round ${r.round_number}`}? Its points come off the ladder and player totals and it goes back to running scores. Chips and transfers managers made are kept. An ended round stays reopened, and locked to managers, until you press Confirm final scores again.`)) return
    setBusy(`r:${r.id}`); setErr(null)
    try { await api.fantasyUnsettleRound(r.id); flash('Round reopened. Press Confirm final scores when its points are right.'); await load() }
    catch (e) { fail(e) } finally { setBusy('') }
  }
  const settleOne = async (r) => {
    const rid = r.id
    if (r.playing && r.status !== 'scored' && !window.confirm('Games are still being played in this round. Confirm the final scores now? You can reopen it again, and running scores carry on until then.')) return
    setBusy(`r:${rid}`); try { const r = await api.fantasySettleRound(rid); flash(`Confirmed scores for ${plural(r.players_scored, 'player')}.`); await load() }
    catch (e) { fail(e) } finally { setBusy('') }
  }

  return (
    <BetterFantasyLayout title="BetterFantasyCricket">
      {msg && <div className="mb-4 rounded bg-pb-accent/10 text-pb-accent px-4 py-2 text-sm">{msg}</div>}
      {err && <div className="mb-4 rounded bg-red-500/10 text-red-400 px-4 py-2 text-sm">{err}</div>}

      {loading ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : !season ? (
        <div className="pb-card p-5 max-w-lg">
          <h2 className="font-display font-bold text-lg mb-1">Start a fantasy season</h2>
          <p className="text-sm text-pb-faint mb-4">
            Pick the season year your club has games for. We seed the scoring and squad
            rules, create the club ladder and mint the public link.
          </p>
          <div className="flex items-end gap-3">
            <label className="text-sm">
              <span className="block text-pb-faint mb-1">Season year</span>
              <input type="number" value={year} onChange={e => setYear(e.target.value)}
                className="w-32 rounded border pb-hairline bg-pb-surface px-3 py-1.5" />
            </label>
            <Btn onClick={createSeason} busy={busy === 'create'}>Create season</Btn>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Season + actions */}
          <div className="pb-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-display font-bold text-lg">{season.name}</h2>
                <p className="text-sm text-pb-faint">
                  {season.year} · status <span className="text-pb-text">{season.status}</span> ·
                  {' '}{data.counts?.pool ?? 0} players · {data.counts?.rounds_scored ?? 0}/{data.counts?.rounds ?? 0} rounds scored
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Btn kind="ghost" onClick={buildPool} busy={busy === 'pool'}>Build pool</Btn>
                <Btn kind="ghost" onClick={genRounds} busy={busy === 'rounds'}>Generate rounds</Btn>
                <Btn onClick={syncScores} busy={busy === 'sync'}>Sync scores</Btn>
                <Btn kind="ghost" onClick={settleDue} busy={busy === 'settle'}>Confirm finished rounds</Btn>
                <Btn kind="ghost" onClick={deleteSeason} busy={busy === 'delete'}>Delete season</Btn>
              </div>
            </div>
            <div className="mt-4 border-t pb-hairline pt-3 flex flex-wrap items-center gap-2 text-xs">
              <span className={`px-2 py-0.5 rounded ${season.rules?.live_sync !== false ? 'bg-green-500/15 text-green-400' : 'bg-pb-surface2 text-pb-faint'}`}>
                Live scoring {season.rules?.live_sync !== false ? 'on' : 'off'}
              </span>
              <button onClick={toggleLive} disabled={busy === 'live'} className="px-2 py-1 rounded bg-pb-surface2 text-pb-text">
                {season.rules?.live_sync !== false ? 'Turn off' : 'Turn on'}
              </button>
              <span className="text-pb-faint basis-full sm:basis-auto">
                While a round is being played, scores refresh every 10 minutes, so managers see running points. They stay provisional until you confirm the round.
              </span>
            </div>
            {data.link_token && (
              <div className="mt-4 border-t pb-hairline pt-3 space-y-2">
                {data.link_active === false && (
                  <div className="rounded bg-amber-500/10 text-amber-400 px-3 py-2 text-xs">
                    BetterFantasyCricket isn't switched on for this club yet, so the public link won't work for members.
                    Turn it on in Super Admin → Clubs. (Admin pages work for you because super admins bypass the gate.)
                  </div>
                )}
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-pb-faint shrink-0">Public link</span>
                  <code className="flex-1 truncate font-mono text-pb-faintest">{linkUrl}</code>
                  <button onClick={() => copy(linkUrl, 'Link')} className="px-2 py-1 rounded bg-pb-surface2 text-pb-text shrink-0">Copy</button>
                  <button onClick={() => copy(`🏏 Play ${season.name}: ${linkUrl}`, 'Message')} className="px-2 py-1 rounded bg-pb-surface2 text-pb-text shrink-0">Copy message</button>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className={`px-2 py-0.5 rounded ${season.registration_open ? 'bg-green-500/15 text-green-400' : 'bg-pb-surface2 text-pb-faint'}`}>
                    Registration {season.registration_open ? 'open' : 'closed'}
                  </span>
                  <button onClick={toggleReg} disabled={busy === 'reg'} className="px-2 py-1 rounded bg-pb-surface2 text-pb-text">
                    {season.registration_open ? 'Close' : 'Open'}
                  </button>
                  <button onClick={regenerate} disabled={busy === 'regen'} className="px-2 py-1 rounded bg-pb-surface2 text-pb-text ml-auto">New link</button>
                </div>
              </div>
            )}
          </div>

          {/* Rounds */}
          <div className="pb-card p-5">
            <h3 className="font-display font-bold mb-3">Rounds {rounds ? `(${rounds.length})` : ''}</h3>
            {realign?.changes?.length > 0 && (
              <div className="mb-4 rounded bg-amber-500/10 text-amber-400 px-4 py-3 text-sm space-y-2" data-testid="realign">
                <p className="font-medium">The draw has changed since these rounds were scored.</p>
                <p className="text-xs">A game outside every round's dates scores for nobody, and Sync scores can't help it.</p>
                <ul className="text-xs space-y-1">
                  {realign.changes.map(c => (
                    <li key={c.round_id}>
                      Round {c.round_number} is stored as {fmtSpan(c.stored)}. The draw has it as {fmtSpan(c.draw)}.
                      {c.blockers?.length > 0 && <span className="block text-pb-faint">Left alone, because {c.blockers.join(', and ')}.</span>}
                    </li>
                  ))}
                </ul>
                {realign.can_apply
                  ? <div><Btn onClick={fixDates} busy={busy === 'realign'}>Fix round dates</Btn></div>
                  : <p className="text-xs text-pb-faint">These can't be moved automatically while managers' choices hang off them.</p>}
              </div>
            )}
            {rounds?.length > 0 && (
              <dl className="mb-4 grid gap-2 sm:grid-cols-3 text-xs" data-testid="score-actions">
                {SCORE_ACTIONS.map(([name, text]) => (
                  <div key={name} className="rounded border pb-hairline px-3 py-2">
                    <dt className="font-medium text-pb-text">{name}</dt>
                    <dd className="text-pb-faint mt-0.5">{text}</dd>
                  </div>
                ))}
              </dl>
            )}
            {!rounds?.length ? (
              <p className="text-sm text-pb-faint">No rounds yet. Click “Generate rounds”.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-pb-faint text-left">
                    <tr>
                      <th className="py-1.5 pr-3">Round</th>
                      <th className="py-1.5 pr-3">Window</th>
                      <th className="py-1.5 pr-3">Locks</th>
                      <th className="py-1.5 pr-3">Status</th>
                      <th className="py-1.5 pr-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rounds.map(r => (
                      <tr key={r.id} className="border-t pb-hairline">
                        <td className="py-1.5 pr-3">{r.name || `Round ${r.round_number}`}</td>
                        <td className="py-1.5 pr-3 text-pb-faint">{r.start_date}{r.end_date && r.end_date !== r.start_date ? ` – ${r.end_date}` : ''}</td>
                        <td className="py-1.5 pr-3 align-top">
                          <LockCell r={r} onChanged={load} flash={flash} fail={fail} />
                        </td>
                        <td className="py-1.5 pr-3">
                          <span className={r.status === 'scored' ? 'text-pb-accent' : r.status === 'unsettled' ? 'text-amber-400' : r.playing ? 'text-green-400' : 'text-pb-faint'}>
                            {r.playing && r.status !== 'scored' && r.status !== 'unsettled' ? 'live' : r.syncable && r.status === 'upcoming' ? 'ended, not confirmed' : (STATUS_WORD[r.status] || r.status)}
                          </span>
                          {r.syncable && r.status !== 'unsettled' && (
                            <div className="text-[11px] text-pb-faint mt-0.5 max-w-xs">
                              {r.playing ? 'Being played now.' : 'Games are over, and the next round has not started.'}
                              {' '}{r.live_checked_at ? `Scores last checked ${fmtTime(r.live_checked_at)}.` : 'Scores not checked yet.'}
                              {r.status === 'scored' ? ' Confirmed already, and still follows late scorecards.' : ' Running scores until you confirm the round.'}
                            </div>
                          )}
                          {r.syncable && r.status === 'upcoming' && !r.playing && (
                            <div className="text-[11px] text-amber-400 mt-0.5 max-w-xs">
                              This round is over. Press Confirm final scores to lock its points in.
                            </div>
                          )}
                          {r.status === 'unsettled' && (
                            <div className="text-[11px] text-amber-400 mt-0.5 max-w-xs">
                              This round was reopened and has no points. Press Confirm final scores to put them back.
                            </div>
                          )}
                          {r.drift && (
                            <div className="text-[11px] text-amber-400 mt-0.5 max-w-xs">
                              Scorecards have changed since this round was confirmed: {r.drift.count} player{r.drift.count === 1 ? '' : 's'} score differently now
                              ({r.drift.players.join(', ')}{r.drift.count > r.drift.players.length ? ', …' : ''}). Press Confirm final scores to bring it up to date; it also happens overnight.
                            </div>
                          )}
                        </td>
                        <td className="py-1.5 pr-3 text-right whitespace-nowrap">
                          <div className="flex flex-wrap justify-end gap-1.5">
                            {r.syncable && r.status !== 'unsettled' && (
                              <RowBtn onClick={syncScores} busy={busy === 'sync'}>Sync scores</RowBtn>
                            )}
                            <RowBtn kind={r.status === 'scored' ? 'ghost' : 'accent'} onClick={() => settleOne(r)} busy={busy === `r:${r.id}`}>Confirm final scores</RowBtn>
                            {r.status === 'scored' && (
                              <RowBtn onClick={() => unsettleOne(r)} busy={busy === `r:${r.id}`}>Reopen round</RowBtn>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </BetterFantasyLayout>
  )
}
