import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import { useScoutAuth } from '../contexts/ScoutAuthContext'
import { WINDOW_OPTIONS, rollupSeasons } from '../lib/seasonRollup'

const POLL_MS = 2500
const MAX_POLLS = 60 // bounded so a wedged build doesn't poll forever (~2.5min)

// Sortable/filterable numeric columns — key maps straight onto p.totals[key].
const COLUMNS = [
  { key: 'name', label: 'Player', numeric: false },
  { key: 'matches', label: 'Matches', numeric: true },
  { key: 'runs', label: 'Runs', numeric: true },
  { key: 'average', label: 'Avg', numeric: true },
  { key: 'strike_rate', label: 'SR', numeric: true },
  { key: 'wickets', label: 'Wkts', numeric: true },
  { key: 'bowling_average', label: 'Bowl avg', numeric: true },
  { key: 'economy', label: 'Econ', numeric: true },
]
const FILTER_FIELDS = COLUMNS.filter((c) => c.numeric)
const EMPTY_FILTERS = Object.fromEntries(FILTER_FIELDS.flatMap((c) => [[`${c.key}_min`, ''], [`${c.key}_max`, '']]))

function getSortValue(p, key) {
  return key === 'name' ? p.name : p.totals?.[key]
}

export default function ScoutDiscover() {
  const { user } = useScoutAuth()
  const atCap = !!user?.usage?.at_cap
  const [query, setQuery] = useState('')
  const [clubs, setClubs] = useState([])
  const [searching, setSearching] = useState(false)
  const [club, setClub] = useState(null) // { id, name }
  const [roster, setRoster] = useState(null) // { status, players, grades, window }
  const [addingId, setAddingId] = useState(null)
  const [addedPlayers, setAddedPlayers] = useState({}) // player_id -> scoutedPlayer.id
  const [expandedId, setExpandedId] = useState(null)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [windowN, setWindowN] = useState(null) // null = full window (today's behaviour)
  const [clientSort, setClientSort] = useState({ col: 'matches', dir: 'desc' })
  const [error, setError] = useState(null)
  const pollRef = useRef(null)
  const pollCount = useRef(0)

  useEffect(() => () => clearTimeout(pollRef.current), [])

  const search = async (e) => {
    e.preventDefault()
    if (query.trim().length < 2) return
    setSearching(true)
    setError(null)
    try {
      setClubs(await scoutApi.searchClubs(query.trim()))
    } catch (err) {
      setError(err.message)
    } finally {
      setSearching(false)
    }
  }

  const pickClub = (c) => {
    clearTimeout(pollRef.current)
    pollCount.current = 0
    setClub(c)
    setRoster({ status: 'building' })
    setAddedPlayers({})
    setExpandedId(null)
    setFilters(EMPTY_FILTERS)
    setWindowN(null)
    setClientSort({ col: 'matches', dir: 'desc' })
    setError(null)
    poll(c)
  }

  const poll = (c) => {
    scoutApi.getClubRoster(c.id, c.name).then((d) => {
      setRoster(d)
      if (d.status === 'building') {
        if (++pollCount.current < MAX_POLLS) {
          pollRef.current = setTimeout(() => poll(c), POLL_MS)
        } else {
          setRoster({ status: 'error', message: 'Timed out waiting for the roster to build.' })
        }
      }
    }).catch((err) => setRoster({ status: 'error', message: err.message }))
  }

  const addPlayer = async (player) => {
    setAddingId(player.player_id)
    setError(null)
    try {
      const added = await scoutApi.addPlayer(club.id, player.player_id, club.name)
      // Stay put — a scout browsing a club's roster wants to keep adding
      // more from the same list, not get bounced to the first player's
      // profile the instant one Add succeeds.
      setAddedPlayers((prev) => ({ ...prev, [player.player_id]: added.id }))
    } catch (err) {
      setError(err.message)
    } finally {
      setAddingId(null)
    }
  }

  const setFilter = (key, value) => setFilters((f) => ({ ...f, [key]: value }))
  const clearFilters = () => setFilters(EMPTY_FILTERS)
  const hasActiveFilters = FILTER_FIELDS.some((c) => filters[`${c.key}_min`] !== '' || filters[`${c.key}_max`] !== '')

  const allPlayers = roster?.players || []

  // The anchor year for "last N seasons" — the same for every player, so
  // a "last 1 season" view means the same real calendar year for everyone,
  // not "each player's own last N appearances" (a player who stopped
  // playing two years ago should show as inactive, not have older stats
  // disguised as recent). Deliberately the latest year with any RECORDED
  // matches, not roster.window.to_year (the club's raw season list can
  // include a freshly-opened season with a real season id but zero played
  // matches yet — anchoring to that would make "last 1 season" silently
  // empty for every player the moment a new season is created upstream).
  const latestActiveYear = useMemo(() => {
    let max = null
    for (const p of allPlayers) {
      for (const s of p.seasons || []) {
        if (s.matches > 0 && (max === null || s.year > max)) max = s.year
      }
    }
    return max
  }, [allPlayers])

  const cutoffYear = useMemo(() => (
    windowN != null && latestActiveYear ? latestActiveYear - (windowN - 1) : null
  ), [windowN, latestActiveYear])

  // Recombines each player's totals from just the seasons within the
  // window — entirely client-side (the raw counts needed to re-derive
  // rates correctly, balls_faced/bowling_balls, already came down with
  // the roster), so switching windows never triggers a re-fetch or a
  // roster rebuild. p.seasons itself is left untouched, so the row-expand
  // preview always shows full multi-year history regardless of window.
  const windowedPlayers = useMemo(() => {
    if (cutoffYear == null) return allPlayers
    return allPlayers.map((p) => ({
      ...p,
      totals: rollupSeasons((p.seasons || []).filter((s) => s.year >= cutoffYear)),
    }))
  }, [allPlayers, cutoffYear])

  const filteredPlayers = useMemo(() => {
    return windowedPlayers.filter((p) => {
      for (const c of FILTER_FIELDS) {
        const min = filters[`${c.key}_min`]
        const max = filters[`${c.key}_max`]
        if (min === '' && max === '') continue
        const v = p.totals?.[c.key]
        if (v === null || v === undefined) return false
        if (min !== '' && v < parseFloat(min)) return false
        if (max !== '' && v > parseFloat(max)) return false
      }
      return true
    })
  }, [windowedPlayers, filters])

  const sortedPlayers = useMemo(() => {
    const { col, dir } = clientSort
    return [...filteredPlayers].sort((a, b) => {
      const va = getSortValue(a, col)
      const vb = getSortValue(b, col)
      const na = typeof va === 'number' ? va : parseFloat(va)
      const nb = typeof vb === 'number' ? vb : parseFloat(vb)
      const an = isFinite(na), bn = isFinite(nb)
      if (an && bn) return dir === 'asc' ? na - nb : nb - na
      if (an !== bn) return an ? -1 : 1 // numbers before nulls, either direction
      const sa = String(va ?? ''), sb = String(vb ?? '')
      return dir === 'asc' ? sa.localeCompare(sb) : sb.localeCompare(sa)
    })
  }, [filteredPlayers, clientSort])

  const onSort = (col) => {
    setClientSort((s) => ({ col, dir: s.col === col && s.dir === 'desc' ? 'asc' : 'desc' }))
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Discover players</h1>
        <p className="text-sm text-pb-dim">Search any Australian club to browse its roster and stats.</p>
      </div>

      {atCap && (
        <p className="text-sm px-3 py-2 rounded border border-[var(--pb-negative)] text-[var(--pb-negative)]">
          You've reached your {user.usage.tier_label} plan's {user.usage.player_cap}-player limit. Contact us to upgrade before adding another player.
        </p>
      )}

      <form onSubmit={search} className="flex gap-2">
        <input
          value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search for a club…"
          className="flex-1 bg-pb-surface2 border border-pb-hairline rounded px-3 py-2"
        />
        <button disabled={searching || query.trim().length < 2}
                className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
          {searching ? 'Searching…' : 'Search'}
        </button>
      </form>

      {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}

      {!club && clubs.length > 0 && (
        <div className="pb-card divide-y divide-pb-hairline">
          {clubs.map((c) => (
            <button key={c.id} onClick={() => pickClub(c)}
                    className="w-full text-left px-4 py-3 hover:bg-pb-surface2">
              {c.name}
            </button>
          ))}
        </div>
      )}

      {club && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">{club.name}</h2>
            <button onClick={() => { setClub(null); setRoster(null); clearTimeout(pollRef.current) }}
                    className="text-sm text-pb-dim hover:text-pb-text">
              ← Back to search
            </button>
          </div>

          {roster?.grades?.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-pb-dim">Grades:</span>
              {roster.grades.map((g) => (
                <span key={g.grade_id} className="px-2 py-0.5 rounded-full bg-pb-surface2 text-pb-dim" title={g.years?.join(', ')}>
                  {g.grade_name || g.team_name}
                </span>
              ))}
            </div>
          )}

          {roster?.status === 'building' && (
            <p className="text-sm text-pb-dim">Building this club's roster from Cricket Australia's records — first load can take up to a minute…</p>
          )}
          {roster?.status === 'error' && (
            <p className="text-sm text-[var(--pb-negative)]">{roster.message || 'Could not load this club’s roster.'}</p>
          )}
          {roster?.status === 'ready' && allPlayers.length === 0 && (
            <p className="text-sm text-pb-dim">No player records found for this club.</p>
          )}

          {roster?.status === 'ready' && allPlayers.length > 0 && (
            <>
              <CareerWindowPanel windowN={windowN} setWindowN={setWindowN} cutoffYear={cutoffYear} toYear={latestActiveYear} />

              <FilterPanel filters={filters} setFilter={setFilter} clearFilters={clearFilters} hasActiveFilters={hasActiveFilters} />

              <p className="text-xs text-pb-dim">
                Showing {sortedPlayers.length} of {allPlayers.length} players
              </p>

              <div className="pb-card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-pb-dim text-xs uppercase font-mono">
                    <tr className="border-b border-pb-hairline">
                      {COLUMNS.map((c) => (
                        <th key={c.key} onClick={() => onSort(c.key)}
                            className={`px-3 py-2 select-none cursor-pointer hover:text-pb-text ${c.numeric ? 'text-right' : 'text-left'}`}
                            style={{ color: clientSort.col === c.key ? 'var(--pb-accent)' : undefined }}>
                          {c.label}{clientSort.col === c.key ? (clientSort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
                        </th>
                      ))}
                      <th className="px-3 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedPlayers.map((p) => (
                      <PlayerRow
                        key={p.player_id} player={p}
                        expanded={expandedId === p.player_id}
                        onToggle={() => setExpandedId((id) => (id === p.player_id ? null : p.player_id))}
                        onAdd={() => addPlayer(p)}
                        adding={addingId === p.player_id}
                        addedPlayerId={addedPlayers[p.player_id]}
                        disabled={atCap}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function CareerWindowPanel({ windowN, setWindowN, cutoffYear, toYear }) {
  return (
    <div className="pb-card p-4 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-pb-dim uppercase font-mono">Career window</span>
        {WINDOW_OPTIONS.map((opt) => (
          <button key={opt.label} onClick={() => setWindowN(opt.n)}
                  className={`text-xs px-2.5 py-1 rounded-full border ${
                    windowN === opt.n
                      ? 'border-[var(--pb-accent)] text-[var(--pb-accent)]'
                      : 'border-pb-hairline text-pb-dim hover:text-pb-text'
                  }`}>
            {opt.label}
          </button>
        ))}
      </div>
      <p className="text-xs text-pb-dim">
        {cutoffYear != null && toYear
          ? `Stats and filters below are for ${cutoffYear === toYear ? toYear : `${cutoffYear}–${toYear}`} only.`
          : "Full window covers BetterScout's ~10-year pull, not necessarily a player's whole career."}
      </p>
    </div>
  )
}

function FilterPanel({ filters, setFilter, clearFilters, hasActiveFilters }) {
  return (
    <div className="pb-card p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-pb-dim uppercase font-mono">Filters</span>
        {hasActiveFilters && (
          <button onClick={clearFilters} className="text-xs text-pb-dim hover:text-pb-text underline">Clear filters</button>
        )}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {FILTER_FIELDS.map((c) => (
          <div key={c.key}>
            <label className="block text-xs text-pb-dim mb-1">{c.label}</label>
            <div className="flex items-center gap-1.5">
              <input type="number" placeholder="Min" value={filters[`${c.key}_min`]}
                     onChange={(e) => setFilter(`${c.key}_min`, e.target.value)}
                     className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-sm" />
              <span className="text-pb-dim text-xs">–</span>
              <input type="number" placeholder="Max" value={filters[`${c.key}_max`]}
                     onChange={(e) => setFilter(`${c.key}_max`, e.target.value)}
                     className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-sm" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function PlayerRow({ player: p, expanded, onToggle, onAdd, adding, addedPlayerId, disabled }) {
  const t = p.totals || {}
  return (
    <>
      <tr className="border-b border-pb-hairline last:border-0 hover:bg-pb-surface2/40 cursor-pointer" onClick={onToggle}>
        <td className="px-3 py-2">{p.name}</td>
        <td className="px-3 py-2 text-right">{t.matches ?? '—'}</td>
        <td className="px-3 py-2 text-right">{t.runs ?? '—'}</td>
        <td className="px-3 py-2 text-right">{t.average ?? '—'}</td>
        <td className="px-3 py-2 text-right">{t.strike_rate ?? '—'}</td>
        <td className="px-3 py-2 text-right">{t.wickets ?? '—'}</td>
        <td className="px-3 py-2 text-right">{t.bowling_average ?? '—'}</td>
        <td className="px-3 py-2 text-right">{t.economy ?? '—'}</td>
        <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
          <AddControl addedPlayerId={addedPlayerId} adding={adding} disabled={disabled} onAdd={onAdd} />
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-pb-hairline last:border-0 bg-pb-surface2/30">
          <td colSpan={COLUMNS.length + 1} className="px-3 py-3">
            <PlayerPreview player={p} addedPlayerId={addedPlayerId} adding={adding} disabled={disabled} onAdd={onAdd} />
          </td>
        </tr>
      )}
    </>
  )
}

function AddControl({ addedPlayerId, adding, disabled, onAdd }) {
  if (addedPlayerId) {
    return (
      <span className="text-xs flex items-center justify-end gap-2">
        <span className="text-[var(--pb-accent)]">Added ✓</span>
        <Link to={`/betterscout/app/players/${addedPlayerId}`} className="text-pb-dim hover:text-pb-text underline" onClick={(e) => e.stopPropagation()}>
          View profile →
        </Link>
      </span>
    )
  }
  return (
    <button onClick={onAdd} disabled={adding || disabled}
            title={disabled ? "You've reached your plan's player limit." : undefined}
            className="text-xs px-2 py-1 rounded bg-[var(--pb-accent)] text-black disabled:opacity-50">
      {adding ? 'Adding…' : 'Add'}
    </button>
  )
}

function PlayerPreview({ player: p, addedPlayerId, adding, disabled, onAdd }) {
  const t = p.totals || {}
  const seasons = p.seasons || []
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm flex-1">
          <Stat label="Best figures" value={t.best} />
          <Stat label="High score" value={t.high_score} />
          <Stat label="50s / 100s" value={`${t.fifties ?? 0} / ${t.hundreds ?? 0}`} />
          <Stat label="Catches" value={t.catches} />
        </div>
        <div onClick={(e) => e.stopPropagation()}>
          <AddControl addedPlayerId={addedPlayerId} adding={adding} disabled={disabled} onAdd={onAdd} />
        </div>
      </div>
      {seasons.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-pb-dim uppercase font-mono">
              <tr className="border-b border-pb-hairline">
                <th className="text-left px-2 py-1">Season</th>
                <th className="text-right px-2 py-1">Matches</th>
                <th className="text-right px-2 py-1">Runs</th>
                <th className="text-right px-2 py-1">Avg</th>
                <th className="text-right px-2 py-1">Wkts</th>
                <th className="text-right px-2 py-1">Econ</th>
              </tr>
            </thead>
            <tbody>
              {seasons.map((s) => (
                <tr key={s.year} className="border-b border-pb-hairline last:border-0">
                  <td className="px-2 py-1">{s.year}</td>
                  <td className="px-2 py-1 text-right">{s.matches}</td>
                  <td className="px-2 py-1 text-right">{s.runs}</td>
                  <td className="px-2 py-1 text-right">{s.average ?? '—'}</td>
                  <td className="px-2 py-1 text-right">{s.wickets}</td>
                  <td className="px-2 py-1 text-right">{s.economy ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="text-xs text-pb-dim uppercase font-mono">{label}</div>
      <div className="text-sm font-semibold">{value ?? '—'}</div>
    </div>
  )
}
