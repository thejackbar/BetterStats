import { useState, useEffect, useCallback } from 'react'
import BetterFantasyLayout from '../../../components/admin/BetterFantasyLayout'
import { api } from '../../../lib/api'
import { Btn } from './shared'

// BetterFantasyCricket admin Overview — create the season, mint and share the
// public link, run the engine (build pool, generate rounds, settle) and see the
// rounds. The other tools (team make-up, scoring, the pool, registered players)
// each have their own side-menu page.

export default function FantasyHome() {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)       // { season, link_token, counts }
  const [rounds, setRounds] = useState(null)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState('')
  const [year, setYear] = useState(new Date().getFullYear())

  const flash = (m) => { setMsg(m); setErr(null); setTimeout(() => setMsg(null), 4000) }
  const fail = (e) => { setErr(e.message || String(e)); setMsg(null) }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.fantasyGetSeason()
      setData(d)
      if (d.season) {
        const r = await api.fantasyListRounds(d.season.id).catch(() => ({ rounds: [] }))
        setRounds(r.rounds)
      }
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
  const genRounds = run('rounds', () => api.fantasyGenerateRounds(season.id), (r) => `Generated ${r.rounds} rounds.`)
  const settleDue = run('settle', () => api.fantasySettleDue(season.id), (r) => `Settled ${r.rounds_settled} rounds.`)
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
  const settleOne = async (rid) => {
    setBusy(`r:${rid}`); try { const r = await api.fantasySettleRound(rid); flash(`Scored ${r.players_scored} players.`); await load() }
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
                <Btn onClick={settleDue} busy={busy === 'settle'}>Settle due rounds</Btn>
                <Btn kind="ghost" onClick={deleteSeason} busy={busy === 'delete'}>Delete season</Btn>
              </div>
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
            {!rounds?.length ? (
              <p className="text-sm text-pb-faint">No rounds yet. Click “Generate rounds”.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-pb-faint text-left">
                    <tr>
                      <th className="py-1.5 pr-3">Round</th>
                      <th className="py-1.5 pr-3">Window</th>
                      <th className="py-1.5 pr-3">Status</th>
                      <th className="py-1.5 pr-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rounds.map(r => (
                      <tr key={r.id} className="border-t pb-hairline">
                        <td className="py-1.5 pr-3">{r.name || `Round ${r.round_number}`}</td>
                        <td className="py-1.5 pr-3 text-pb-faint">{r.start_date}{r.end_date && r.end_date !== r.start_date ? ` – ${r.end_date}` : ''}</td>
                        <td className="py-1.5 pr-3">
                          <span className={r.status === 'scored' ? 'text-pb-accent' : 'text-pb-faint'}>{r.status}</span>
                        </td>
                        <td className="py-1.5 pr-3 text-right">
                          <button onClick={() => settleOne(r.id)} disabled={busy === `r:${r.id}`}
                            className="text-xs underline text-pb-faint hover:text-pb-text disabled:opacity-50">
                            {busy === `r:${r.id}` ? '…' : 'Settle'}
                          </button>
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
