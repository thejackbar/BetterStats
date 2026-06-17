import { useState, useEffect, useCallback } from 'react'
import BetterFantasyLayout from '../../../components/admin/BetterFantasyLayout'
import { api } from '../../../lib/api'

// BetterFantasyCricket admin overview — set up the season, build the priced
// pool, generate the weekly rounds and settle scores. The member-facing play
// (squad builder, ladder) is on the public link; this drives the engine. Built
// to verify the backend end to end, then grow into a fuller admin surface.

const ROLES = ['keeper', 'batter', 'allrounder', 'bowler']
const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 }))

function Btn({ onClick, busy, children, kind = 'accent' }) {
  const base = 'px-3 py-1.5 rounded text-sm font-medium disabled:opacity-50 transition-opacity'
  const cls = kind === 'accent' ? 'bg-pb-accent text-white hover:opacity-90' : 'border pb-hairline text-pb-text hover:bg-pb-surface2'
  return <button onClick={onClick} disabled={busy} className={`${base} ${cls}`}>{busy ? '…' : children}</button>
}

export default function FantasyHome() {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)       // { season, link_token, counts }
  const [pool, setPool] = useState(null)
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
        const [p, r] = await Promise.all([
          api.fantasyListPool(d.season.id).catch(() => ({ players: [] })),
          api.fantasyListRounds(d.season.id).catch(() => ({ rounds: [] })),
        ])
        setPool(p.players); setRounds(r.rounds)
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

  const setRole = async (pp, role) => {
    try { await api.fantasyPatchPool(pp.id, { role }); await load() } catch (e) { fail(e) }
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
              </div>
            </div>
            {data.link_token && (
              <p className="mt-3 text-xs text-pb-faintest font-mono break-all">
                Public link: /fantasy/{data.link_token} (member play UI is a later phase)
              </p>
            )}
          </div>

          {/* Pool */}
          <div className="pb-card p-5">
            <h3 className="font-display font-bold mb-3">Player pool {pool ? `(${pool.length})` : ''}</h3>
            {!pool?.length ? (
              <p className="text-sm text-pb-faint">No pool yet — click “Build pool”.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-pb-faint text-left">
                    <tr>
                      <th className="py-1.5 pr-3">Player</th>
                      <th className="py-1.5 pr-3">Role</th>
                      <th className="py-1.5 pr-3 text-right">Price</th>
                      <th className="py-1.5 pr-3 text-right">Points</th>
                      <th className="py-1.5 pr-3 text-right">Owned</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pool.slice(0, 200).map(p => (
                      <tr key={p.id} className="border-t pb-hairline">
                        <td className="py-1.5 pr-3">{p.name}</td>
                        <td className="py-1.5 pr-3">
                          <select value={p.role} onChange={e => setRole(p, e.target.value)}
                            className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-xs">
                            {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                          </select>
                          {p.role_source === 'admin' && <span className="ml-1 text-[10px] text-pb-accent">set</span>}
                        </td>
                        <td className="py-1.5 pr-3 text-right tabular-nums">{fmt(p.current_price)}</td>
                        <td className="py-1.5 pr-3 text-right tabular-nums">{fmt(p.total_points)}</td>
                        <td className="py-1.5 pr-3 text-right tabular-nums">{p.owned_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {pool.length > 200 && <p className="text-xs text-pb-faintest mt-2">Showing top 200 by price.</p>}
              </div>
            )}
          </div>

          {/* Rounds */}
          <div className="pb-card p-5">
            <h3 className="font-display font-bold mb-3">Rounds {rounds ? `(${rounds.length})` : ''}</h3>
            {!rounds?.length ? (
              <p className="text-sm text-pb-faint">No rounds yet — click “Generate rounds”.</p>
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
