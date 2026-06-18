import { useState, useEffect, useCallback, useMemo } from 'react'
import BetterFantasyLayout from '../../../components/admin/BetterFantasyLayout'
import { api } from '../../../lib/api'

// BetterFantasyCricket admin overview — set up the season, build the priced
// pool, generate the weekly rounds and settle scores. The member-facing play
// (squad builder, ladder) is on the public link; this drives the engine. Built
// to verify the backend end to end, then grow into a fuller admin surface.

const ROLES = ['keeper', 'batter', 'allrounder', 'bowler']
const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }))

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
  const [sort, setSort] = useState({ key: 'current_price', dir: 'desc' })
  const [poolSearch, setPoolSearch] = useState('')
  const [showAllPool, setShowAllPool] = useState(false)

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

  const setRole = async (pp, role) => {
    try { await api.fantasyPatchPool(pp.id, { role }); await load() } catch (e) { fail(e) }
  }
  const settleOne = async (rid) => {
    setBusy(`r:${rid}`); try { const r = await api.fantasySettleRound(rid); flash(`Scored ${r.players_scored} players.`); await load() }
    catch (e) { fail(e) } finally { setBusy('') }
  }
  const removePool = async (id) => {
    if (!window.confirm('Remove this player from the pool?')) return
    try { await api.fantasyRemovePoolPlayer(id); await load() } catch (e) { fail(e) }
  }

  // Client-side sort of the pool table. Text columns sort A→Z by default,
  // numbers high→low; clicking a header toggles the direction.
  const toggleSort = (key) => setSort(s => (
    s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
                  : { key, dir: (key === 'name' || key === 'role') ? 'asc' : 'desc' }
  ))
  const sortedPool = useMemo(() => {
    const arr = [...(pool || [])]
    const { key, dir } = sort
    const text = key === 'name' || key === 'role'
    arr.sort((a, b) => {
      if (text) {
        const av = (a[key] || '').toString().toLowerCase(), bv = (b[key] || '').toString().toLowerCase()
        return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
      }
      return dir === 'asc' ? (Number(a[key]) || 0) - (Number(b[key]) || 0) : (Number(b[key]) || 0) - (Number(a[key]) || 0)
    })
    return arr
  }, [pool, sort])

  const filteredPool = useMemo(() => {
    const term = poolSearch.trim().toLowerCase()
    return term ? sortedPool.filter(p => p.name.toLowerCase().includes(term)) : sortedPool
  }, [sortedPool, poolSearch])
  const shownPool = (poolSearch || showAllPool) ? filteredPool : filteredPool.slice(0, 200)

  const Th = ({ k, children, right }) => (
    <th className={`py-1.5 pr-3 ${right ? 'text-right' : 'text-left'}`}>
      <button type="button" onClick={() => toggleSort(k)} className="inline-flex items-center gap-1 hover:text-pb-text">
        {children}{sort.key === k && <span className="text-[10px]">{sort.dir === 'asc' ? '▲' : '▼'}</span>}
      </button>
    </th>
  )

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

          <SettingsCard season={season} flash={flash} fail={fail} onSaved={load} />
          <PoolManager season={season} flash={flash} fail={fail} onChanged={load} />
          <ManagersCard flash={flash} fail={fail} />

          {/* Pool */}
          <div className="pb-card p-5">
            <div className="flex items-center justify-between gap-3 mb-3">
              <h3 className="font-display font-bold">Player pool {pool ? `(${pool.length})` : ''}</h3>
              {!!pool?.length && (
                <input value={poolSearch} onChange={e => setPoolSearch(e.target.value)} placeholder="Search pool…"
                  className="rounded border pb-hairline bg-pb-surface px-3 py-1.5 text-sm w-48" />
              )}
            </div>
            {!pool?.length ? (
              <p className="text-sm text-pb-faint">No pool yet — click “Build pool”.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-pb-faint">
                    <tr>
                      <Th k="name">Player</Th>
                      <Th k="role">Role</Th>
                      <Th k="current_price" right>Price</Th>
                      <Th k="total_points" right>Points</Th>
                      <Th k="owned_count" right>Owned</Th>
                      <th className="py-1.5"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {shownPool.map(p => (
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
                        <td className="py-1.5 text-right">
                          <button onClick={() => removePool(p.id)} title="Remove from pool"
                            className="text-pb-faintest hover:text-red-400">×</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!poolSearch && !showAllPool && filteredPool.length > 200 && (
                  <button onClick={() => setShowAllPool(true)} className="text-xs text-pb-accent underline mt-2">Show all {filteredPool.length}</button>
                )}
                {poolSearch && <p className="text-xs text-pb-faintest mt-2">{filteredPool.length} match{filteredPool.length === 1 ? '' : 'es'}.</p>}
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

function Field({ label, children }) {
  return <label className="flex flex-col gap-1"><span className="text-pb-faint text-xs">{label}</span>{children}</label>
}

function SettingsCard({ season, flash, fail, onSaved }) {
  const r = season.rules || {}
  const rq = r.role_quota || {}
  const [q, setQ] = useState({ keeper: rq.keeper ?? 1, batter: rq.batter ?? 4, allrounder: rq.allrounder ?? 3, bowler: rq.bowler ?? 4 })
  const [v, setV] = useState({
    budget: r.budget ?? 100, count_best_n: r.count_best_n ?? 11, transfer_hit: r.transfer_hit ?? 4,
    free_transfers_per_round: r.free_transfers_per_round ?? 1, max_banked_transfers: r.max_banked_transfers ?? 2,
    wildcards_per_half: r.wildcards_per_half ?? 1, triple_captains_per_half: r.triple_captains_per_half ?? 1,
    price_window_years: r.price_window_years ?? 3,
  })
  const [busy, setBusy] = useState(false)
  const size = ROLES.reduce((a, role) => a + Number(q[role] || 0), 0)
  const num = (val, set) => <input type="number" min="0" value={val} onChange={e => set(e.target.value)}
    className="w-full rounded border pb-hairline bg-pb-surface px-2 py-1.5 text-sm" />

  const save = async () => {
    setBusy(true)
    try {
      const windowChanged = +v.price_window_years !== (r.price_window_years ?? 3)
      await api.fantasyUpdateRules(season.id, {
        role_quota: { keeper: +q.keeper, batter: +q.batter, allrounder: +q.allrounder, bowler: +q.bowler },
        budget: +v.budget, count_best_n: +v.count_best_n, transfer_hit: +v.transfer_hit,
        free_transfers_per_round: +v.free_transfers_per_round, max_banked_transfers: +v.max_banked_transfers,
        wildcards_per_half: +v.wildcards_per_half, triple_captains_per_half: +v.triple_captains_per_half,
        price_window_years: +v.price_window_years,
      })
      // Changing the pricing window only takes effect once the pool is rebuilt;
      // do it here (forcing a price reset) so the new prices show straight away.
      if (windowChanged) {
        const res = await api.fantasyBuildPool(season.id, true)
        flash(`Settings saved. Prices recalculated for ${res.pool} players.`)
      } else {
        flash('Settings saved.')
      }
      await onSaved()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-5">
      <h3 className="font-display font-bold mb-1">Team make-up & budget</h3>
      <p className="text-xs text-pb-faint mb-3">
        Squad size is the sum of the roles ({size}). Score the best {v.count_best_n} each round. Change this before the season starts.
        Prices come from each player's runs, wickets, fielding and milestones over the last {v.price_window_years} season{+v.price_window_years === 1 ? '' : 's'}, role-weighted and fitted to the budget. Change the window and click Save settings to recalculate prices straight away.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Field label="Keepers">{num(q.keeper, x => setQ({ ...q, keeper: x }))}</Field>
        <Field label="Batters">{num(q.batter, x => setQ({ ...q, batter: x }))}</Field>
        <Field label="All-rounders">{num(q.allrounder, x => setQ({ ...q, allrounder: x }))}</Field>
        <Field label="Bowlers">{num(q.bowler, x => setQ({ ...q, bowler: x }))}</Field>
        <Field label="Budget">{num(v.budget, x => setV({ ...v, budget: x }))}</Field>
        <Field label="Price on last">
          <select value={v.price_window_years} onChange={e => setV({ ...v, price_window_years: e.target.value })}
            className="w-full rounded border pb-hairline bg-pb-surface px-2 py-1.5 text-sm">
            <option value="1">1 season</option>
            <option value="2">2 seasons</option>
            <option value="3">3 seasons</option>
            <option value="4">4 seasons</option>
          </select>
        </Field>
        <Field label="Score best N">{num(v.count_best_n, x => setV({ ...v, count_best_n: x }))}</Field>
        <Field label="Transfer hit">{num(v.transfer_hit, x => setV({ ...v, transfer_hit: x }))}</Field>
        <Field label="Free transfers / round">{num(v.free_transfers_per_round, x => setV({ ...v, free_transfers_per_round: x }))}</Field>
        <Field label="Max banked transfers">{num(v.max_banked_transfers, x => setV({ ...v, max_banked_transfers: x }))}</Field>
        <Field label="Wildcards / half">{num(v.wildcards_per_half, x => setV({ ...v, wildcards_per_half: x }))}</Field>
        <Field label="Triple captains / half">{num(v.triple_captains_per_half, x => setV({ ...v, triple_captains_per_half: x }))}</Field>
      </div>
      <button onClick={save} disabled={busy}
        className="mt-3 px-3 py-1.5 rounded bg-pb-accent text-white text-sm font-medium disabled:opacity-50">Save settings</button>
    </div>
  )
}

function PoolManager({ season, flash, fail, onChanged }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null)
  const [np, setNp] = useState({ name: '', role: 'batter', price: 5 })
  const [busy, setBusy] = useState(false)

  const search = async () => {
    setBusy(true)
    try { setResults((await api.fantasyAvailablePlayers(season.id, q)).players) } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const add = async (pid) => {
    try { await api.fantasyAddPoolPlayer(season.id, { player_id: pid }); flash('Added to pool.'); setResults(rs => (rs || []).filter(r => r.player_id !== pid)); await onChanged() }
    catch (e) { fail(e) }
  }
  const createNew = async () => {
    if (!np.name.trim()) return
    try { await api.fantasyAddNewPlayer(season.id, { name: np.name, role: np.role, price: +np.price }); flash('Player created and added.'); setNp({ name: '', role: 'batter', price: 5 }); await onChanged() }
    catch (e) { fail(e) }
  }

  return (
    <div className="pb-card p-5 space-y-4">
      <div>
        <h3 className="font-display font-bold mb-2">Add a returning player</h3>
        <div className="flex gap-2">
          <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && search()}
            placeholder="Search the club's players…" className="flex-1 rounded border pb-hairline bg-pb-surface px-3 py-1.5 text-sm" />
          <button onClick={search} disabled={busy} className="px-3 py-1.5 rounded bg-pb-surface2 text-pb-text text-sm">Search</button>
        </div>
        {results && (results.length ? (
          <div className="mt-2">
            {results.map(r => (
              <div key={r.player_id} className="flex justify-between items-center text-sm border-t pb-hairline py-1.5">
                <span>{r.name}</span>
                <button onClick={() => add(r.player_id)} className="text-xs px-2 py-1 rounded bg-pb-accent text-white">Add</button>
              </div>
            ))}
          </div>
        ) : <p className="text-xs text-pb-faint mt-2">No players found outside the pool.</p>)}
      </div>
      <div className="border-t pb-hairline pt-3">
        <h3 className="font-display font-bold mb-1">New player</h3>
        <p className="text-xs text-pb-faint mb-2">For someone not in the data yet. They score 0 until their games sync to this record.</p>
        <div className="flex flex-wrap gap-2 items-end">
          <input value={np.name} onChange={e => setNp({ ...np, name: e.target.value })} placeholder="Name"
            className="rounded border pb-hairline bg-pb-surface px-3 py-1.5 text-sm" />
          <select value={np.role} onChange={e => setNp({ ...np, role: e.target.value })}
            className="rounded border pb-hairline bg-pb-surface px-2 py-1.5 text-sm">
            {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
          <input type="number" min="0" value={np.price} onChange={e => setNp({ ...np, price: e.target.value })}
            className="w-24 rounded border pb-hairline bg-pb-surface px-2 py-1.5 text-sm" placeholder="Price" />
          <button onClick={createNew} className="px-3 py-1.5 rounded bg-pb-accent text-white text-sm">Create &amp; add</button>
        </div>
      </div>
    </div>
  )
}

// Manage the people who have registered to play (edit name/email, reset a locked
// PIN, or delete a tester/duplicate). Managers are club-scoped, not per season.
function ManagersCard({ flash, fail }) {
  const [managers, setManagers] = useState(null)
  const [q, setQ] = useState('')
  const [editing, setEditing] = useState(null)   // manager id
  const [form, setForm] = useState({ display_name: '', email: '', pin: '' })
  const [busy, setBusy] = useState('')

  const load = useCallback(() => api.fantasyManagers().then(d => setManagers(d.managers)).catch(() => setManagers([])), [])
  useEffect(() => { load() }, [load])

  const startEdit = (m) => { setEditing(m.id); setForm({ display_name: m.display_name || '', email: m.email || '', pin: '' }) }
  const save = async (id) => {
    setBusy(id)
    try {
      const body = { display_name: form.display_name, email: form.email }
      if (form.pin.trim()) body.pin = form.pin.trim()
      await api.fantasyUpdateManager(id, body)
      flash('Player updated.'); setEditing(null); await load()
    } catch (e) { fail(e) } finally { setBusy('') }
  }
  const remove = async (m) => {
    if (!window.confirm(`Delete ${m.display_name}? This removes their team and league entries. This can't be undone.`)) return
    setBusy(m.id)
    try { await api.fantasyDeleteManager(m.id); flash('Player deleted.'); await load() }
    catch (e) { fail(e) } finally { setBusy('') }
  }

  const list = (managers || []).filter(m => {
    const t = q.trim().toLowerCase()
    return !t || (m.display_name || '').toLowerCase().includes(t) || (m.email || '').toLowerCase().includes(t)
  })
  const inp = 'rounded border pb-hairline bg-pb-surface px-2 py-1.5 text-sm'

  return (
    <div className="pb-card p-5">
      <div className="flex items-center justify-between gap-3 mb-1">
        <h3 className="font-display font-bold">Registered players {managers ? `(${managers.length})` : ''}</h3>
        {!!managers?.length && (
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search players…" className={`${inp} w-48`} />
        )}
      </div>
      <p className="text-xs text-pb-faint mb-3">People who signed up on the public link. Edit a name or email, reset a forgotten PIN, or remove a tester or duplicate.</p>

      {managers === null ? <p className="text-sm text-pb-faint">Loading…</p>
        : !list.length ? <p className="text-sm text-pb-faint">{managers.length ? 'No players match.' : 'No one has signed up yet.'}</p>
          : (
            <div className="divide-y pb-hairline">
              {list.map(m => (
                <div key={m.id} className="py-2.5">
                  {editing === m.id ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <input value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} placeholder="Display name" className={`${inp} flex-1 min-w-[140px]`} />
                      <input value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="Email" className={`${inp} flex-1 min-w-[160px]`} />
                      <input value={form.pin} onChange={e => setForm(f => ({ ...f, pin: e.target.value }))} placeholder="New PIN (optional)" className={`${inp} w-36`} />
                      <Btn onClick={() => save(m.id)} busy={busy === m.id}>Save</Btn>
                      <Btn kind="ghost" onClick={() => setEditing(null)}>Cancel</Btn>
                    </div>
                  ) : (
                    <div className="flex items-center gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm truncate">{m.display_name}
                          {m.team_name && <span className="text-pb-faint font-normal"> · {m.team_name}</span>}
                          {!m.has_squad && <span className="ml-2 text-[11px] text-pb-faint">no squad</span>}
                        </div>
                        <div className="text-xs text-pb-faint truncate">{m.email || 'no email'}{m.total_points != null ? ` · ${fmt(m.total_points)} pts` : ''}</div>
                      </div>
                      <button onClick={() => startEdit(m)} className="text-xs underline text-pb-faint hover:text-pb-text">Edit</button>
                      <button onClick={() => remove(m)} disabled={busy === m.id} className="text-xs underline text-pb-red disabled:opacity-50">Delete</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
    </div>
  )
}
