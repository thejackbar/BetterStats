import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import BetterFantasyLayout from '../../../components/admin/BetterFantasyLayout'
import { api } from '../../../lib/api'
import { useAuth } from '../../../contexts/AuthContext'
import { CAP } from '../../../lib/capabilities'

// Shared pieces for the BetterFantasyCricket admin surface. Each tool (team
// make-up, scoring, the pool, registered players) is its own page now, so the
// cards, the season loader and the page frame live here and are imported by the
// thin page components.

export const ROLES = ['keeper', 'batter', 'allrounder', 'bowler']
export const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }))

export function Btn({ onClick, busy, children, kind = 'accent' }) {
  const base = 'px-3 py-1.5 rounded text-sm font-medium disabled:opacity-50 transition-opacity'
  const cls = kind === 'accent' ? 'bg-pb-accent text-white hover:opacity-90' : 'border pb-hairline text-pb-text hover:bg-pb-surface2'
  return <button onClick={onClick} disabled={busy} className={`${base} ${cls}`}>{busy ? '…' : children}</button>
}

export function Field({ label, children }) {
  return <label className="flex flex-col gap-1"><span className="text-pb-faint text-xs">{label}</span>{children}</label>
}

// Load the club's current fantasy season once for a page, with flash/fail
// banners. Pages reuse it so navigating between tools each loads its own copy
// (cheap), keeping the pages independent.
export function useFantasySeason() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const flash = useCallback((m) => { setMsg(m); setErr(null); setTimeout(() => setMsg(null), 4000) }, [])
  const fail = useCallback((e) => { setErr(e?.message || String(e)); setMsg(null) }, [])
  const reload = useCallback(async () => {
    setLoading(true)
    try { setData(await api.fantasyGetSeason()) }
    catch (e) { setErr(e?.message || String(e)) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { reload() }, [reload])
  return { data, season: data?.season, loading, reload, msg, err, flash, fail }
}

function NoSeasonNotice() {
  return (
    <div className="pb-card p-5 max-w-lg">
      <h2 className="font-display font-bold text-lg mb-1">No fantasy season yet</h2>
      <p className="text-sm text-pb-faint mb-4">Start a season on the Overview page first. The pool, scoring and team rules all hang off it.</p>
      <Link to="/admin/fantasy" className="px-3 py-1.5 rounded bg-pb-accent text-white text-sm font-medium">Go to Overview</Link>
    </div>
  )
}

// Common chrome for a fantasy admin page: the layout, the message banners, the
// loading state, and (unless needSeason is false) the "no season yet" notice.
export function FantasyFrame({ title, season, loading = false, needSeason = true, msg, err, children }) {
  return (
    <BetterFantasyLayout title={title}>
      {msg && <div className="mb-4 rounded bg-pb-accent/10 text-pb-accent px-4 py-2 text-sm">{msg}</div>}
      {err && <div className="mb-4 rounded bg-red-500/10 text-red-400 px-4 py-2 text-sm">{err}</div>}
      {loading ? <div className="text-pb-faint text-sm">Loading…</div>
        : (needSeason && !season) ? <NoSeasonNotice />
          : children}
    </BetterFantasyLayout>
  )
}

// ── Team make-up & budget ───────────────────────────────────────────────────────

export function SettingsCard({ season, flash, fail, onSaved }) {
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

// ── Scoring system ────────────────────────────────────────────────────────────

// Fallback points table, used before the season's own scoring loads and as the
// base to spread over (so a key the backend added later still has a value).
// The live values come from season.scoring; this just guards holes.
export const DEFAULT_SCORING_FALLBACK = {
  run: 1, four: 1, six: 2, fifty: 16, hundred: 32, duck: -4,
  wicket: 25, three_wickets: 8, five_wickets: 16, maiden: 8,
  catch: 8, stumping: 12, run_out: 12, appearance: 4,
  off_role_multiplier: 1.5, captain_multiplier: 2, triple_captain_multiplier: 3,
}

// Grouped for the editor; the keys match the backend scoring blob.
export const SCORING_GROUPS = [
  ['Batting', [
    ['run', 'Per run'], ['four', 'Per four'], ['six', 'Per six'],
    ['fifty', 'Reaching 50'], ['hundred', 'Reaching 100'], ['duck', 'Duck (out for 0)'],
  ]],
  ['Bowling', [
    ['wicket', 'Per wicket'], ['three_wickets', '3-wicket haul'],
    ['five_wickets', '5-wicket haul'], ['maiden', 'Per maiden over'],
  ]],
  ['Fielding & appearance', [
    ['catch', 'Per catch'], ['stumping', 'Per stumping'],
    ['run_out', 'Per run-out'], ['appearance', 'Took the field'],
  ]],
  ['Multipliers', [
    ['off_role_multiplier', 'Off-role ×'], ['captain_multiplier', 'Captain ×'],
    ['triple_captain_multiplier', 'Triple captain ×'],
  ]],
]

// Edit the points table — what a run, wicket, catch, milestone etc. is worth,
// plus the off-role and captain multipliers. Saves the season's JSONB scoring
// blob; new values apply to rounds settled from here on.
export function ScoringCard({ season, flash, fail, onSaved }) {
  const [v, setV] = useState(() => ({ ...DEFAULT_SCORING_FALLBACK, ...(season.scoring || {}) }))
  const [defaults, setDefaults] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.fantasyConfig().then(d => setDefaults(d.defaults?.scoring || null)).catch(() => {}) }, [])

  const set = (k, val) => setV(s => ({ ...s, [k]: val }))
  const numInput = (k) => (
    <input type="number" step="any" value={v[k] ?? ''} onChange={e => set(k, e.target.value)}
      className="w-full rounded border pb-hairline bg-pb-surface px-2 py-1.5 text-sm tabular-nums" />
  )

  const save = async () => {
    setBusy(true)
    try {
      const payload = {}
      for (const [, fields] of SCORING_GROUPS) for (const [k] of fields) {
        const n = Number(v[k])
        if (Number.isFinite(n)) payload[k] = n
      }
      const res = await api.fantasyUpdateScoring(season.id, payload)
      setV({ ...DEFAULT_SCORING_FALLBACK, ...res.scoring })
      flash('Scoring saved. New values apply to rounds settled from now on.')
      await onSaved()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const resetDefaults = () => { if (defaults) setV({ ...DEFAULT_SCORING_FALLBACK, ...defaults }) }

  return (
    <div className="pb-card p-5">
      <h3 className="font-display font-bold mb-1">Scoring system</h3>
      <p className="text-xs text-pb-faint mb-3">
        How many fantasy points each thing is worth. A player's output outside their role (a bowler's
        runs, a batter's wickets, a keeper's batting and dismissals) is multiplied by the off-role number,
        and the captain's round total is multiplied before each squad's best {season.rules?.count_best_n ?? 11} are counted.
        New values apply to rounds settled from now on, and to any round scored in the last fortnight the next time it is brought up to date. Settle an older scored round again to apply them there too.
      </p>
      <div className="space-y-4">
        {SCORING_GROUPS.map(([group, fields]) => (
          <div key={group}>
            <div className="text-[11px] font-medium uppercase tracking-wide text-pb-faintest mb-1.5">{group}</div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {fields.map(([k, label]) => <Field key={k} label={label}>{numInput(k)}</Field>)}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center gap-3">
        <button onClick={save} disabled={busy}
          className="px-3 py-1.5 rounded bg-pb-accent text-white text-sm font-medium disabled:opacity-50">Save scoring</button>
        <button onClick={resetDefaults} disabled={!defaults}
          className="text-xs underline text-pb-faint hover:text-pb-text disabled:opacity-40">Reset to defaults</button>
      </div>
    </div>
  )
}

// ── Player pool ─────────────────────────────────────────────────────────────────

export function PoolManager({ season, flash, fail, onChanged }) {
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

// The priced pool, sortable and searchable. Role is editable inline (stamps the
// admin override server-side) and a player can be removed from the pool.
export function PoolTable({ pool, onRoleChange, onRemove }) {
  const [sort, setSort] = useState({ key: 'current_price', dir: 'desc' })
  const [poolSearch, setPoolSearch] = useState('')
  const [showAll, setShowAll] = useState(false)

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
  const shownPool = (poolSearch || showAll) ? filteredPool : filteredPool.slice(0, 200)

  const Th = ({ k, children, right }) => (
    <th className={`py-1.5 pr-3 ${right ? 'text-right' : 'text-left'}`}>
      <button type="button" onClick={() => toggleSort(k)} className="inline-flex items-center gap-1 hover:text-pb-text">
        {children}{sort.key === k && <span className="text-[10px]">{sort.dir === 'asc' ? '▲' : '▼'}</span>}
      </button>
    </th>
  )

  return (
    <div className="pb-card p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="font-display font-bold">Player pool {pool ? `(${pool.length})` : ''}</h3>
        {!!pool?.length && (
          <input value={poolSearch} onChange={e => setPoolSearch(e.target.value)} placeholder="Search pool…"
            className="rounded border pb-hairline bg-pb-surface px-3 py-1.5 text-sm w-48" />
        )}
      </div>
      {pool === null ? (
        <p className="text-sm text-pb-faint">Loading…</p>
      ) : !pool.length ? (
        <p className="text-sm text-pb-faint">No pool yet. Build it from the Overview page.</p>
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
                    <select value={p.role} onChange={e => onRoleChange(p, e.target.value)}
                      className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-xs">
                      {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                    {p.role_source === 'admin' && <span className="ml-1 text-[10px] text-pb-accent">set</span>}
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmt(p.current_price)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmt(p.total_points)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{p.owned_count}</td>
                  <td className="py-1.5 text-right">
                    <button onClick={() => onRemove(p.id)} title="Remove from pool"
                      className="text-pb-faintest hover:text-red-400">×</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!poolSearch && !showAll && filteredPool.length > 200 && (
            <button onClick={() => setShowAll(true)} className="text-xs text-pb-accent underline mt-2">Show all {filteredPool.length}</button>
          )}
          {poolSearch && <p className="text-xs text-pb-faintest mt-2">{filteredPool.length} match{filteredPool.length === 1 ? '' : 'es'}.</p>}
        </div>
      )}
    </div>
  )
}

// ── Registered players (with their picked teams) ─────────────────────────────────

const ROLE_RANK = { keeper: 0, batter: 1, allrounder: 2, bowler: 3 }

// Inline panel showing a manager's picked squad(s): the club-ladder team and any
// draft teams, with captain/vice and each pick's season points.
// Search the club's players by name (in the pool or not) and pick one.
function PlayerPicker({ seasonId, onPick, placeholder = 'Search players…' }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  useEffect(() => {
    if (q.trim().length < 2) { setRows([]); return }
    let on = true
    const t = setTimeout(() => {
      api.fantasyPlayerSearch(seasonId, q.trim()).then(d => on && setRows(d.players || [])).catch(() => on && setRows([]))
    }, 250)
    return () => { on = false; clearTimeout(t) }
  }, [q, seasonId])
  return (
    <div className="relative min-w-0">
      <input value={q} onChange={e => setQ(e.target.value)} placeholder={placeholder}
        className="w-full rounded border pb-hairline bg-pb-surface px-2 py-1.5 text-sm" />
      {!!rows.length && (
        <div className="absolute z-20 mt-1 w-full max-h-56 overflow-auto rounded border pb-hairline bg-pb-surface shadow-lg">
          {rows.map(r => (
            <button key={r.player_id} type="button" onClick={() => { onPick(r); setQ(''); setRows([]) }}
              className="w-full text-left px-2 py-1.5 text-sm hover:bg-pb-surface2 flex items-center gap-2">
              <span className="truncate flex-1">{r.name}</span>
              <span className="text-[11px] text-pb-faint shrink-0">{r.in_pool ? r.role : 'not in pool yet'}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// Put right a team the rules could not: add a player (optionally in place of
// another), or take one out. Scored rounds from "From round" on are scored again.
function SquadEditor({ squad, onChanged, flash, fail }) {
  const [pick, setPick] = useState(null)
  const [replace, setReplace] = useState('')
  const [fromRound, setFromRound] = useState(1)
  const [busy, setBusy] = useState(false)
  const [warn, setWarn] = useState([])

  const report = (r, msg) => { setWarn(r.warnings || []); flash(msg); onChanged?.() }
  const add = async () => {
    if (!pick) return
    setBusy(true)
    try {
      const r = await api.fantasyAddSquadPlayer(squad.squad_id, {
        player_id: pick.player_id, replace_player_id: replace || null, from_round: Number(fromRound) || 1,
      })
      setPick(null); setReplace('')
      report(r, `${pick.name} is in the team.`)
    } catch (e) { fail(e) } finally { setBusy(false) }
  }
  return (
    <div className="mt-3 border-t pb-hairline pt-3">
      <div className="text-xs text-pb-faint mb-1.5">
        Add a player to this team. The lock, budget and role quota are ignored, and the rounds already scored from the round you choose are scored again, so they count as if picked then.
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex-1 min-w-[200px]">
          {pick
            ? <div className="flex items-center gap-2 rounded border pb-hairline px-2 py-1.5 text-sm"><span className="truncate flex-1">{pick.name}</span>
                <button onClick={() => setPick(null)} className="text-xs underline text-pb-faint">Change</button></div>
            : <PlayerPicker seasonId={squad.season_id} onPick={setPick} />}
        </div>
        <label className="text-xs text-pb-faint flex flex-col gap-1">Replacing
          <select value={replace} onChange={e => setReplace(e.target.value)}
            className="rounded border pb-hairline bg-pb-surface px-2 py-1.5 text-sm max-w-[180px]">
            <option value="">Nobody (add)</option>
            {squad.players.map(p => <option key={p.player_id} value={p.player_id}>{p.name}</option>)}
          </select>
        </label>
        <label className="text-xs text-pb-faint flex flex-col gap-1">From round
          <input type="number" min="1" value={fromRound} onChange={e => setFromRound(e.target.value)}
            className="w-20 rounded border pb-hairline bg-pb-surface px-2 py-1.5 text-sm" />
        </label>
        <Btn onClick={add} busy={busy}>Add to team</Btn>
      </div>
      {warn.map((w, i) => <div key={i} className="mt-1.5 text-xs text-amber-400">{w}</div>)}
    </div>
  )
}

function ManagerTeams({ squads, busy, onChanged, flash, fail }) {
  if (busy && !squads) return <p className="text-xs text-pb-faint">Loading team…</p>
  if (!squads) return null
  if (!squads.length) return <p className="text-xs text-pb-faint">No team selected yet.</p>
  return (
    <div className="space-y-3">
      {squads.map(sq => {
        const players = [...sq.players].sort((a, b) =>
          (a.is_captain ? -2 : a.is_vice_captain ? -1 : 0) - (b.is_captain ? -2 : b.is_vice_captain ? -1 : 0)
          || (ROLE_RANK[a.role] ?? 9) - (ROLE_RANK[b.role] ?? 9)
          || a.name.localeCompare(b.name))
        return (
          <div key={sq.squad_id} className="rounded border pb-hairline bg-pb-surface2/40 p-3">
            <div className="text-sm font-medium">
              {sq.team_name}
              {sq.players.length !== sq.squad_size && <span className="ml-2 text-xs font-normal text-amber-400">{sq.players.length} of {sq.squad_size} players</span>}
              <span className="text-pb-faint font-normal"> · {sq.league} · {sq.season_year}/{String((sq.season_year + 1) % 100).padStart(2, '0')} · {fmt(sq.total_points)} pts{sq.budget_remaining != null ? ` · $${fmt(sq.budget_remaining)} bank` : ''}</span>
            </div>
            <div className="mt-2 grid sm:grid-cols-2 gap-x-6 gap-y-0.5">
              {players.map(p => (
                <div key={p.player_id} className="flex items-center gap-2 text-xs py-0.5 border-t pb-hairline first:border-t-0 sm:border-t-0">
                  <span className="w-16 text-pb-faintest shrink-0 capitalize">{p.role}</span>
                  <span className="flex-1 truncate text-pb-text">
                    {p.name}
                    {p.is_captain && <span className="ml-1 text-pb-accent font-semibold">(C)</span>}
                    {p.is_vice_captain && <span className="ml-1 text-pb-faint font-semibold">(V)</span>}
                  </span>
                  <span className="tabular-nums text-pb-faint shrink-0">{fmt(p.total_points)} pts</span>
                  <button onClick={async () => {
                    if (!window.confirm(`Take ${p.name} out of ${sq.team_name}? Scored rounds are scored again without them.`)) return
                    try { const r = await api.fantasyRemoveSquadPlayer(sq.squad_id, p.player_id, 1); flash(`${p.name} removed.${(r.warnings || []).length ? ' ' + r.warnings.join(' ') : ''}`); onChanged?.() }
                    catch (e) { fail(e) }
                  }} className="text-[11px] underline text-pb-faint hover:text-pb-text shrink-0">Remove</button>
                </div>
              ))}
            </div>
            {sq.kind === 'global_salary_cap' && flash && <SquadEditor squad={sq} onChanged={onChanged} flash={flash} fail={fail} />}
          </div>
        )
      })}
    </div>
  )
}

// Manage the people who have registered to play (view their picked team, edit
// name/email, reset a locked PIN, or delete a tester/duplicate). Managers are
// club-scoped, not per season.
export function ManagersCard({ flash, fail }) {
  const [managers, setManagers] = useState(null)
  const [q, setQ] = useState('')
  const [editing, setEditing] = useState(null)   // manager id
  const [form, setForm] = useState({ display_name: '', email: '', pin: '' })
  const [busy, setBusy] = useState('')
  const [openId, setOpenId] = useState(null)      // manager whose team is shown
  const [teams, setTeams] = useState({})          // managerId -> squads[]
  const [teamsBusy, setTeamsBusy] = useState('')

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
  const viewAs = async (m) => {
    // Open the tab first (a popup opened after an await is blocked), then point it at the public pages.
    const w = window.open('', '_blank')
    setBusy(`v:${m.id}`)
    try {
      const r = await api.fantasyViewAs(m.id)
      const url = window.location.origin + r.url
      if (w) w.location.href = url; else window.location.assign(url)
    } catch (e) { w?.close(); fail(e) } finally { setBusy('') }
  }
  const reloadTeams = async (m) => {
    try { const d = await api.fantasyManagerTeams(m.id); setTeams(t => ({ ...t, [m.id]: d.squads })); await load() }
    catch (e) { fail(e) }
  }
  const viewTeams = async (m) => {
    if (openId === m.id) { setOpenId(null); return }
    setOpenId(m.id)
    if (!teams[m.id]) {
      setTeamsBusy(m.id)
      try { const d = await api.fantasyManagerTeams(m.id); setTeams(t => ({ ...t, [m.id]: d.squads })) }
      catch (e) { fail(e) } finally { setTeamsBusy('') }
    }
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
      <p className="text-xs text-pb-faint mb-3">People who signed up on the public link. View the team they picked, open the whole game as them (read only) with View as, edit a name or email, reset a forgotten PIN, or remove a tester or duplicate.</p>

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
                          {m.has_squad && m.squad_size != null && m.pick_count < m.squad_size && (
                            <span className="ml-2 text-[11px] text-amber-400">{m.pick_count} of {m.squad_size} players</span>
                          )}
                        </div>
                        <div className="text-xs text-pb-faint truncate">{m.email || 'no email'}{m.total_points != null ? ` · ${fmt(m.total_points)} pts` : ''}</div>
                      </div>
                      {m.has_squad && (
                        <button onClick={() => viewTeams(m)} className="text-xs underline text-pb-faint hover:text-pb-text">
                          {openId === m.id ? 'Hide team' : 'View team'}
                        </button>
                      )}
                      <button onClick={() => viewAs(m)} disabled={busy === `v:${m.id}`}
                        title="Open the public Fantasy pages as this player, read only"
                        className="text-xs underline text-pb-faint hover:text-pb-text disabled:opacity-50">View as</button>
                      <button onClick={() => startEdit(m)} className="text-xs underline text-pb-faint hover:text-pb-text">Edit</button>
                      <button onClick={() => remove(m)} disabled={busy === m.id} className="text-xs underline text-pb-red disabled:opacity-50">Delete</button>
                    </div>
                  )}
                  {openId === m.id && editing !== m.id && (
                    <div className="mt-2.5"><ManagerTeams squads={teams[m.id]} busy={teamsBusy === m.id} onChanged={() => reloadTeams(m)} flash={flash} fail={fail} /></div>
                  )}
                </div>
              ))}
            </div>
          )}
    </div>
  )
}


// Type in a player's fantasy points for a round, for someone whose games are not
// in the data. Settlement leaves these alone; Remove hands the round back to the
// scorecards.
export function ManualScoresCard({ season, flash, fail }) {
  const [rounds, setRounds] = useState([])
  const [scores, setScores] = useState(null)
  const [roundId, setRoundId] = useState('')
  const [pick, setPick] = useState(null)
  const [points, setPoints] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => api.fantasyManualScores(season.id).then(d => setScores(d.scores)).catch(() => setScores([])), [season.id])
  useEffect(() => {
    load()
    api.fantasyListRounds(season.id).then(d => { setRounds(d.rounds || []); setRoundId(r => r || d.rounds?.[0]?.id || '') }).catch(() => {})
  }, [season.id, load])

  const save = async () => {
    if (!pick || !roundId || points === '' || Number.isNaN(Number(points))) return
    setBusy(true)
    try {
      await api.fantasySetManualScore(roundId, pick.player_id, { points: Number(points), note: note.trim() || null })
      flash(`${pick.name}: ${points} points saved.`); setPick(null); setPoints(''); setNote(''); await load()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }
  const remove = async (r) => {
    try { await api.fantasyClearManualScore(r.round_id, r.player_id); flash('Typed-in score removed.'); await load() }
    catch (e) { fail(e) }
  }
  const inp = 'rounded border pb-hairline bg-pb-surface px-2 py-1.5 text-sm'
  return (
    <div className="pb-card p-5">
      <h3 className="font-display font-bold mb-1">Typed-in scores</h3>
      <p className="text-xs text-pb-faint mb-3">
        For a player whose games are not in the data yet. The points you type replace the scorecard figure for that round, and a round that is already scored is scored again. The player has to be in the pool. Settling never changes a typed-in score.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-pb-faint flex flex-col gap-1">Round
          <select value={roundId} onChange={e => setRoundId(e.target.value)} className={`${inp} max-w-[180px]`}>
            {rounds.map(r => <option key={r.id} value={r.id}>{r.name || `Round ${r.round_number}`}</option>)}
          </select>
        </label>
        <div className="flex-1 min-w-[200px]">
          {pick
            ? <div className="flex items-center gap-2 rounded border pb-hairline px-2 py-1.5 text-sm"><span className="truncate flex-1">{pick.name}</span>
                <button onClick={() => setPick(null)} className="text-xs underline text-pb-faint">Change</button></div>
            : <PlayerPicker seasonId={season.id} onPick={setPick} />}
        </div>
        <label className="text-xs text-pb-faint flex flex-col gap-1">Points
          <input type="number" step="0.5" value={points} onChange={e => setPoints(e.target.value)} className={`${inp} w-24`} />
        </label>
        <label className="text-xs text-pb-faint flex flex-col gap-1 flex-1 min-w-[140px]">Note (optional)
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="e.g. 42 off 30, 2 wickets" className={inp} />
        </label>
        <Btn onClick={save} busy={busy}>Save score</Btn>
      </div>
      {!!scores?.length && (
        <div className="mt-4 divide-y pb-hairline">
          {scores.map(r => (
            <div key={`${r.round_id}-${r.player_id}`} className="py-2 flex items-center gap-3 text-sm">
              <span className="w-24 text-pb-faint shrink-0">{r.round_name || `Round ${r.round_number}`}</span>
              <span className="flex-1 min-w-0 truncate">{r.name}{r.note && <span className="text-pb-faint"> · {r.note}</span>}</span>
              <span className="tabular-nums shrink-0">{fmt(r.points)}</span>
              <button onClick={() => remove(r)} className="text-xs underline text-pb-faint hover:text-pb-text shrink-0">Remove</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


// Players added to Fantasy by hand have no games of their own. When their real games
// sync they land on a separate profile with the same name, so the hand-added one
// scores nothing. This lists those pairs with a Merge button. The merge is the
// club's normal player merge (team picks, pool entry and round points follow the
// kept profile, and it can be undone from the merge log), then the scored rounds are
// scored again so the stats show at once.
export function HandAddedPlayersCard({ season, flash, fail }) {
  const { hasCapability } = useAuth()
  const canMerge = hasCapability(CAP.MANAGE_MERGES)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState('')
  const load = useCallback(() => api.fantasyUnmatched(season.id).then(setData).catch(e => { setData({ pairs: [], waiting: [] }); fail(e) }), [season.id, fail])
  useEffect(() => { load() }, [load])

  const merge = async (p, t) => {
    if (!window.confirm(
      `Merge ${p.name} into ${t.name} (${t.games} game${t.games === 1 ? '' : 's'} this season)?\n\n` +
      `${t.name} is kept. ${p.name}${p.picked_by ? `, picked in ${p.picked_by} team${p.picked_by === 1 ? '' : 's'},` : ''} is removed, and those teams keep the player under ${t.name}. ` +
      `Scored rounds are scored again. It can be undone from the merge log.`)) return
    setBusy(`${p.player_id}:${t.player_id}`)
    try {
      await api.fantasyMergePlayer(season.id, t.player_id, p.player_id)
      flash(`${p.name} merged into ${t.name}. Scored rounds were scored again.`)
      await load()
    } catch (e) { fail(e); await load() } finally { setBusy('') }
  }

  if (!data) return null
  if (!data.pairs.length && !data.waiting.length) return null
  return (
    <div className="pb-card p-5">
      <h3 className="font-display font-bold mb-1">Hand-added players with stats on another profile</h3>
      <p className="text-xs text-pb-faint mb-3">
        These players were added to Fantasy by hand, so they have no games of their own. A profile with the same name has played in {data.season_year},
        so their points are sitting there. Merge the pair and the stats come through.
        {!canMerge && ' You need the Merge data permission to merge players.'}
      </p>
      {!!data.pairs.length && (
        <div className="divide-y pb-hairline">
          {data.pairs.map(p => (
            <div key={p.player_id} className="py-2.5">
              <div className="text-sm font-medium min-w-0 break-words">
                {p.name}
                <span className="text-pb-faint font-normal text-xs"> · {p.added_by_hand ? 'added by hand' : 'in the pool'} · picked in {p.picked_by} team{p.picked_by === 1 ? '' : 's'} · no games</span>
              </div>
              {p.twins.map(t => (
                <div key={t.player_id} className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm">
                  <span className="flex-1 min-w-[12rem] break-words text-pb-dim">Stats are on <span className="text-pb-text">{t.name}</span> ({t.games} game{t.games === 1 ? '' : 's'})</span>
                  <Btn kind="ghost" onClick={() => merge(p, t)} busy={busy === `${p.player_id}:${t.player_id}`}>
                    {canMerge ? 'Merge' : 'Merge (no permission)'}
                  </Btn>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
      {!!data.waiting.length && (
        <div className="mt-3 text-xs text-pb-faint">
          Picked by teams, but with no games counted this season and no same-name profile to merge:{' '}
          {data.waiting.map(w => `${w.name} (${w.picked_by} team${w.picked_by === 1 ? '' : 's'}${w.added_by_hand ? ', added by hand' : ''})`).join(', ')}.
          <div className="mt-1">
            If one of them has played, their game may be on a different profile (look for a duplicate on the Players page), in a grade that is switched off, or not synced yet.
          </div>
        </div>
      )}
    </div>
  )
}
