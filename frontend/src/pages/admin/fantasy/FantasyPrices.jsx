import { useState, useEffect, useMemo, useCallback } from 'react'
import { api } from '../../../lib/api'
import { FantasyFrame, useFantasySeason } from './shared'

// Price movements: who has gone up and down, by how much, and how they got there.
// Prices move after every scored round (services/fantasy_pricing): a player's score is
// measured against what the other players in the round scored for their price, a
// century earns the 0.5 cap and an ordinary good day a tenth or two. A price typed in
// by hand on the Player pool page does not move and is marked here.

const money = (n) => `$${Number(n ?? 0).toFixed(1)}`
const ROLES = [['all', 'All roles'], ['batter', 'Batters'], ['bowler', 'Bowlers'], ['allrounder', 'All-rounders'], ['keeper', 'Keepers']]
const VIEWS = [['all', 'All'], ['up', '▲ Risers'], ['down', '▼ Fallers'], ['flat', 'Unchanged']]
const SORTS = [['rise', 'Biggest rise'], ['fall', 'Biggest fall'], ['price', 'Price'], ['points', 'Points'], ['owned', 'Most owned'], ['name', 'Name']]

// A price move with its arrow: green ▲ up, red ▼ down, a dash when it did not move.
function Move({ v, small }) {
  const c = Math.round(Number(v || 0) * 10) / 10
  if (!c) return <span className="text-pb-faintest">–</span>
  return (
    <span className={`${c > 0 ? 'text-green-500' : 'text-red-400'} font-semibold whitespace-nowrap ${small ? 'text-[11px]' : ''}`}>
      {c > 0 ? '▲' : '▼'}{Math.abs(c).toFixed(1)}
    </span>
  )
}

function Tile({ label, value, sub }) {
  return (
    <div className="pb-card p-4">
      <div className="text-[11px] uppercase tracking-wide text-pb-faint">{label}</div>
      <div className="text-2xl font-display font-bold mt-1">{value}</div>
      {sub && <div className="text-xs text-pb-faint mt-0.5">{sub}</div>}
    </div>
  )
}

export default function FantasyPrices() {
  const { season, loading, msg, err, fail } = useFantasySeason()
  const seasonId = season?.id
  const [data, setData] = useState(null)
  const [view, setView] = useState('all')
  const [role, setRole] = useState('all')
  const [sort, setSort] = useState('rise')
  const [search, setSearch] = useState('')
  const [span, setSpan] = useState('last')   // which move the filters use: last round or whole season

  const load = useCallback(async () => {
    if (!seasonId) return
    try { setData(await api.fantasyPriceMovements(seasonId)) } catch (e) { fail(e) }
  }, [seasonId, fail])
  useEffect(() => { load() }, [load])

  const key = span === 'last' ? 'last_change' : 'season_change'
  const rows = useMemo(() => {
    if (!data) return []
    const term = search.trim().toLowerCase()
    const l = data.players.filter(p =>
      (role === 'all' || p.role === role) && (!term || p.name.toLowerCase().includes(term)) &&
      (view === 'all' || (view === 'up' ? p[key] > 0 : view === 'down' ? p[key] < 0 : p[key] === 0)))
    const by = {
      rise: (a, b) => b[key] - a[key] || b.price - a.price,
      fall: (a, b) => a[key] - b[key] || b.price - a.price,
      price: (a, b) => b.price - a.price,
      points: (a, b) => b.total_points - a.total_points,
      owned: (a, b) => b.owned_count - a.owned_count,
      name: (a, b) => a.name.localeCompare(b.name),
    }[sort]
    return l.sort(by)
  }, [data, view, role, sort, search, key])

  const s = data?.summary
  const chip = (on) => `px-3 py-1 rounded text-xs font-semibold ${on ? 'bg-pb-accent text-white' : 'bg-pb-surface2 text-pb-dim hover:text-pb-text'}`

  return (
    <FantasyFrame title="Price movements" season={season} loading={loading} msg={msg} err={err}>
      {season && (
        <div className="space-y-6">
          {!data ? <p className="text-sm text-pb-faint">Loading…</p> : !data.rounds.length ? (
            <div className="pb-card p-5 text-sm text-pb-faint">
              No round has been scored yet, so no price has moved. Prices move after each scored round: a player who scores well
              goes up and one who has a quiet round goes down, by up to $0.5 a round.
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <Tile label={`Risers, round ${data.last_round}`} value={s.risers} sub={s.biggest_riser ? `Biggest: ${s.biggest_riser.name} ▲${s.biggest_riser.change.toFixed(1)}` : 'None'} />
                <Tile label={`Fallers, round ${data.last_round}`} value={s.fallers} sub={s.biggest_faller ? `Biggest: ${s.biggest_faller.name} ▼${Math.abs(s.biggest_faller.change).toFixed(1)}` : 'None'} />
                <Tile label="Up most this season" value={s.season_riser ? `▲${s.season_riser.change.toFixed(1)}` : '–'} sub={s.season_riser?.name || 'No one yet'} />
                <Tile label="Down most this season" value={s.season_faller ? `▼${Math.abs(s.season_faller.change).toFixed(1)}` : '–'} sub={s.season_faller?.name || 'No one yet'} />
              </div>

              <div className="pb-card p-5">
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <div className="flex gap-1">
                    {VIEWS.map(([k, l]) => <button key={k} onClick={() => setView(k)} className={chip(view === k)}>{l}</button>)}
                  </div>
                  <div className="flex gap-1 ml-2">
                    <button onClick={() => setSpan('last')} className={chip(span === 'last')} title="Use the latest scored round's move">Last round</button>
                    <button onClick={() => setSpan('season')} className={chip(span === 'season')} title="Use the move since the season's starting price">This season</button>
                  </div>
                  <select value={role} onChange={e => setRole(e.target.value)} className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-xs">
                    {ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                  <select value={sort} onChange={e => setSort(e.target.value)} className="bg-pb-surface border pb-hairline rounded px-2 py-1 text-xs">
                    {SORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                  <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search players…"
                    className="rounded border pb-hairline bg-pb-surface px-3 py-1 text-sm w-44 ml-auto" />
                </div>
                {!rows.length ? <p className="text-sm text-pb-faint">No players match.</p> : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-pb-faint text-left">
                        <tr>
                          <th className="py-1.5 pr-3">Player</th>
                          <th className="py-1.5 pr-3">Role</th>
                          <th className="py-1.5 pr-3 text-right">Start</th>
                          <th className="py-1.5 pr-3 text-right">Now</th>
                          <th className="py-1.5 pr-3 text-right">Last round</th>
                          <th className="py-1.5 pr-3 text-right">Season</th>
                          <th className="py-1.5 pr-3">Recent rounds</th>
                          <th className="py-1.5 pr-3 text-right">Owned</th>
                          <th className="py-1.5 text-right">Points</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map(p => (
                          <tr key={p.player_id} className="border-t pb-hairline">
                            <td className="py-1.5 pr-3">{p.name}{p.price_locked && <span className="ml-1 text-[10px] text-pb-accent" title="Price set by hand, so it does not move">set</span>}</td>
                            <td className="py-1.5 pr-3 text-pb-faint">{p.role}</td>
                            <td className="py-1.5 pr-3 text-right tabular-nums text-pb-faint">{money(p.base_price)}</td>
                            <td className="py-1.5 pr-3 text-right tabular-nums">{money(p.price)}</td>
                            <td className="py-1.5 pr-3 text-right tabular-nums"><Move v={p.last_change} /></td>
                            <td className="py-1.5 pr-3 text-right tabular-nums"><Move v={p.season_change} /></td>
                            <td className="py-1.5 pr-3">
                              <span className="inline-flex gap-2">
                                {p.history.length ? p.history.map(h => (
                                  <span key={h.round} title={`Round ${h.round}: ${money(h.price)}`} className="inline-flex items-baseline gap-0.5">
                                    <span className="text-[10px] text-pb-faintest">R{h.round}</span><Move v={h.move} small />
                                  </span>
                                )) : <span className="text-pb-faintest">–</span>}
                              </span>
                            </td>
                            <td className="py-1.5 pr-3 text-right tabular-nums">{p.owned_count}</td>
                            <td className="py-1.5 text-right tabular-nums">{Number(p.total_points).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="text-xs text-pb-faintest mt-3">
                  Showing {rows.length} of {data.players.length}. A player who did not play does not move. Prices are worked out from every
                  scored round, so a corrected scorecard changes them overnight.
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </FantasyFrame>
  )
}
