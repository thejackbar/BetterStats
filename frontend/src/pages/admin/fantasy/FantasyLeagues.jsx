import { useState, useEffect, useCallback } from 'react'
import BetterFantasyLayout from '../../../components/admin/BetterFantasyLayout'
import { api } from '../../../lib/api'

// Admin: create draft leagues (snake or auction), watch them fill, start the
// draft and run the waiver wire. Members join and draft from the public link.
// The salary-cap club ladder and member-created mini-leagues need no admin
// setup, so this page is just the draft side.

export default function FantasyLeagues() {
  const [season, setSeason] = useState(null)
  const [leagues, setLeagues] = useState(null)
  const [form, setForm] = useState({ name: '', draft_type: 'snake', scoring_type: 'total' })
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState('')

  const flash = (m) => { setMsg(m); setErr(null); setTimeout(() => setMsg(null), 4000) }
  const fail = (e) => { setErr(e.message || String(e)); setMsg(null) }

  const load = useCallback(async () => {
    try {
      const s = await api.fantasyGetSeason()
      setSeason(s.season)
      if (s.season) setLeagues((await api.fantasyListDraftLeagues(s.season.id)).leagues)
    } catch (e) { fail(e) }
  }, [])
  useEffect(() => { load() }, [load])

  const create = async () => {
    setBusy('create')
    try { const r = await api.fantasyCreateDraftLeague(season.id, form); flash(`Created, code ${r.league.join_code}`); setForm({ ...form, name: '' }); await load() }
    catch (e) { fail(e) } finally { setBusy('') }
  }
  const start = async (id) => { setBusy(id); try { await api.fantasyStartDraft(id); flash('Draft started.'); await load() } catch (e) { fail(e) } finally { setBusy('') } }
  const advance = async (id) => { setBusy(id); try { const r = await api.fantasyAdvanceDraft(id); flash(r.status === 'complete' ? 'Draft complete.' : 'Draft clock advanced.'); await load() } catch (e) { fail(e) } finally { setBusy('') } }
  const waivers = async (id) => { setBusy(id); try { const r = await api.fantasyProcessWaivers(id); flash(`Granted ${r.granted} waiver claims.`); await load() } catch (e) { fail(e) } finally { setBusy('') } }

  return (
    <BetterFantasyLayout title="Draft leagues">
      {msg && <div className="mb-4 rounded bg-pb-accent/10 text-pb-accent px-4 py-2 text-sm">{msg}</div>}
      {err && <div className="mb-4 rounded bg-red-500/10 text-red-400 px-4 py-2 text-sm">{err}</div>}

      {!season ? (
        <p className="text-sm text-pb-faint">Create a fantasy season on the Overview tab first.</p>
      ) : (
        <div className="space-y-6">
          <div className="pb-card p-5">
            <h2 className="font-display font-bold mb-3">New draft league</h2>
            <div className="grid sm:grid-cols-4 gap-3 items-end">
              <label className="text-sm sm:col-span-2">
                <span className="block text-pb-faint mb-1">Name</span>
                <input className="w-full rounded border pb-hairline bg-pb-surface px-3 py-1.5" value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Saturday draft" />
              </label>
              <label className="text-sm">
                <span className="block text-pb-faint mb-1">Type</span>
                <select className="w-full rounded border pb-hairline bg-pb-surface px-3 py-1.5"
                  value={form.draft_type} onChange={e => setForm({ ...form, draft_type: e.target.value })}>
                  <option value="snake">Snake</option>
                  <option value="auction">Auction</option>
                </select>
              </label>
              <label className="text-sm">
                <span className="block text-pb-faint mb-1">Scoring</span>
                <select className="w-full rounded border pb-hairline bg-pb-surface px-3 py-1.5"
                  value={form.scoring_type} onChange={e => setForm({ ...form, scoring_type: e.target.value })}>
                  <option value="total">Total points</option>
                  <option value="h2h">Head-to-head</option>
                </select>
              </label>
            </div>
            <button onClick={create} disabled={busy === 'create'}
              className="mt-3 px-3 py-1.5 rounded bg-pb-accent text-white text-sm font-medium disabled:opacity-50">Create league</button>
          </div>

          <div className="pb-card p-5">
            <h3 className="font-display font-bold mb-3">Leagues</h3>
            {!leagues?.length ? <p className="text-sm text-pb-faint">No draft leagues yet.</p> : (
              <div className="space-y-2">
                {leagues.map(lg => (
                  <div key={lg.id} className="flex flex-wrap items-center justify-between gap-2 border-t pb-hairline pt-2 text-sm">
                    <div>
                      <span className="font-medium">{lg.name}</span>
                      <span className="text-pb-faint"> · {lg.draft_type} · {lg.scoring_type === 'h2h' ? 'head-to-head' : 'total points'} · code {lg.join_code}</span>
                      <div className="text-xs text-pb-faint">{lg.members} members · draft {lg.draft_status || 'not started'}</div>
                    </div>
                    <div className="flex gap-2">
                      {(!lg.draft_status || lg.draft_status === 'scheduled') && (
                        <button onClick={() => start(lg.id)} disabled={busy === lg.id || lg.members < 2}
                          className="px-3 py-1.5 rounded bg-pb-accent text-white text-xs font-medium disabled:opacity-50">Start draft</button>
                      )}
                      {lg.draft_status === 'in_progress' && (
                        <button onClick={() => advance(lg.id)} disabled={busy === lg.id}
                          className="px-3 py-1.5 rounded border pb-hairline text-xs disabled:opacity-50">Advance clock</button>
                      )}
                      {lg.draft_status === 'complete' && (
                        <button onClick={() => waivers(lg.id)} disabled={busy === lg.id}
                          className="px-3 py-1.5 rounded border pb-hairline text-xs disabled:opacity-50">Process waivers</button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </BetterFantasyLayout>
  )
}
