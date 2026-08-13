import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import { useScoutAuth } from '../contexts/ScoutAuthContext'
import { WINDOW_OPTIONS, rollupSeasons } from '../lib/seasonRollup'
import ScoutModuleLayout from '../ScoutModuleLayout'
import { PlayerAvatar, Sparkline } from '../components/ScoutUi'
import { Btn, Chip, Search, Segmented } from '../../pages/admin/betterselect/ui'

const POLL_MS = 2500
const MAX_POLLS = 60 // bounded so a wedged build doesn't poll forever (~2.5min)

// Sortable/filterable numeric columns — key maps straight onto p.totals[key].
const COLUMNS = [
  { key: 'name', label: 'Player', numeric: false },
  { key: 'matches', label: 'Mat', numeric: true },
  { key: 'runs', label: 'Runs', numeric: true },
  { key: 'average', label: 'Avg', numeric: true },
  { key: 'strike_rate', label: 'SR', numeric: true },
  { key: 'wickets', label: 'Wkts', numeric: true },
  { key: 'bowling_average', label: 'Bowl', numeric: true },
  { key: 'economy', label: 'Econ', numeric: true },
]
const FILTER_FIELDS = [
  { key: 'runs', label: 'Runs' },
  { key: 'strike_rate', label: 'SR' },
  { key: 'wickets', label: 'Wkts' },
  { key: 'bowling_average', label: 'Bowl avg' },
  { key: 'economy', label: 'Econ' },
  { key: 'average', label: 'Bat avg' },
  { key: 'matches', label: 'Matches' },
]
const EMPTY_FILTERS = Object.fromEntries(FILTER_FIELDS.flatMap((c) => [[`${c.key}_min`, ''], [`${c.key}_max`, '']]))

const PRESETS = [
  { key: 'bat35', label: 'Bat avg 35+', fields: { average_min: '35' } },
  { key: 'bowl25', label: 'Bowl avg <25', fields: { bowling_average_max: '25' } },
  { key: 'sr85', label: 'SR 85+', fields: { strike_rate_min: '85' } },
  { key: 'allrounder', label: 'All-rounders', fields: { runs_min: '100', wickets_min: '5' } },
  { key: 'mat10', label: '10+ matches', fields: { matches_min: '10' } },
]

function getSortValue(p, key) {
  return key === 'name' ? p.name : p.totals?.[key]
}

function timeAgo(iso) {
  if (!iso) return null
  const ms = Date.now() - new Date(iso).getTime()
  const days = Math.floor(ms / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return '1 day ago'
  if (days < 14) return `${days} days ago`
  const weeks = Math.floor(days / 7)
  return `${weeks} week${weeks === 1 ? '' : 's'} ago`
}

export default function ScoutDiscover() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user } = useScoutAuth()
  const atCap = !!user?.usage?.at_cap
  const [query, setQuery] = useState('')
  const [clubs, setClubs] = useState([])
  const [searching, setSearching] = useState(false)
  const [club, setClub] = useState(null) // { id, name }
  const [roster, setRoster] = useState(null) // { status, players, grades, window, source, cached }
  const [rebuilding, setRebuilding] = useState(false)
  const [addingId, setAddingId] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [visibleFilterKeys, setVisibleFilterKeys] = useState(new Set())
  const [windowN, setWindowN] = useState(null) // null = full window
  const [selectedGrades, setSelectedGrades] = useState(new Set()) // empty = every grade
  const [clientSort, setClientSort] = useState({ col: 'matches', dir: 'desc' })
  const [error, setError] = useState(null)
  const [watchlists, setWatchlists] = useState([])
  const pollRef = useRef(null)
  const pollCount = useRef(0)

  useEffect(() => () => clearTimeout(pollRef.current), [])
  useEffect(() => { scoutApi.listWatchlists().then(setWatchlists).catch(() => {}) }, [])

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
    setClubs([])
    setQuery('')
    setRoster({ status: 'building' })
    setExpandedId(null)
    setFilters(EMPTY_FILTERS)
    setVisibleFilterKeys(new Set())
    setWindowN(null)
    setSelectedGrades(new Set())
    setClientSort({ col: 'matches', dir: 'desc' })
    setError(null)
    poll(c)
  }

  // The global search bar (ScoutGlobalSearch) hands off a club pick via
  // router state rather than a query param — consumed once, then dropped
  // from history so navigating back to Discover doesn't re-trigger it.
  const handledHandoff = useRef(false)
  useEffect(() => {
    if (handledHandoff.current) return
    const handoffClub = location.state?.club
    if (handoffClub?.id) {
      handledHandoff.current = true
      pickClub(handoffClub)
      navigate(location.pathname, { replace: true, state: null })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state])

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

  const rebuildRoster = async () => {
    if (!club) return
    setRebuilding(true)
    setError(null)
    try {
      const d = await scoutApi.refreshClubRoster(club.id, club.name)
      setRoster(d)
      if (d.status === 'building') {
        pollCount.current = 0
        poll(club)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setRebuilding(false)
    }
  }

  // Default board for "Add to watchlist" — whichever the org touched most
  // recently, per the design's "default to the org's most recently used
  // board" rule. Falls back to null (backend creates/uses the default).
  const defaultWatchlistId = useMemo(() => {
    if (!watchlists.length) return null
    return [...watchlists].sort((a, b) => new Date(b.last_used_at) - new Date(a.last_used_at))[0].id
  }, [watchlists])

  const addPlayer = async (player, watchlistId) => {
    setAddingId(player.player_id)
    setError(null)
    try {
      const added = await scoutApi.addPlayer(club.id, player.player_id, club.name, watchlistId)
      setRoster((r) => ({
        ...r,
        players: r.players.map((p) => p.player_id === player.player_id
          ? { ...p, scouted_player_id: added.id, watchlist_count: (p.watchlist_count || 0) + 1 }
          : p),
      }))
      return added
    } catch (err) {
      setError(err.message)
      return null
    } finally {
      setAddingId(null)
    }
  }

  const openFullProfile = async (player) => {
    let scoutedId = player.scouted_player_id
    if (!scoutedId) {
      const added = await addPlayer(player, defaultWatchlistId)
      scoutedId = added?.id
    }
    if (scoutedId) navigate(`/betterscout/app/players/${scoutedId}`)
  }

  const addToCompare = async (player) => {
    let scoutedId = player.scouted_player_id
    if (!scoutedId) {
      const added = await addPlayer(player, defaultWatchlistId)
      scoutedId = added?.id
    }
    if (scoutedId) navigate(`/betterscout/app/compare?players=${scoutedId}`)
  }

  const setFilter = (key, value) => setFilters((f) => ({ ...f, [key]: value }))
  const clearFilterKey = (key) => {
    setFilters((f) => ({ ...f, [`${key}_min`]: '', [`${key}_max`]: '' }))
    setVisibleFilterKeys((s) => { const n = new Set(s); n.delete(key); return n })
  }
  const revealFilter = (key) => setVisibleFilterKeys((s) => new Set(s).add(key))
  const clearAllFilters = () => { setFilters(EMPTY_FILTERS); setVisibleFilterKeys(new Set()) }

  const activeFilterKeys = FILTER_FIELDS.filter((c) => filters[`${c.key}_min`] !== '' || filters[`${c.key}_max`] !== '')
  const hasActiveFilters = activeFilterKeys.length > 0

  const activePresetKey = useMemo(() => {
    return PRESETS.find((p) => Object.entries(p.fields).every(([k, v]) => filters[k] === v))?.key || null
  }, [filters])

  const togglePreset = (preset) => {
    if (activePresetKey === preset.key) {
      setFilters((f) => {
        const next = { ...f }
        for (const k of Object.keys(preset.fields)) next[k] = ''
        return next
      })
    } else {
      setFilters((f) => ({ ...f, ...preset.fields }))
      setVisibleFilterKeys((s) => {
        const n = new Set(s)
        for (const k of Object.keys(preset.fields)) n.add(k.replace(/_(min|max)$/, ''))
        return n
      })
    }
  }

  const allPlayers = roster?.players || []

  // The anchor year for "last N seasons" — same real calendar year for every
  // player, not "each player's own last N appearances".
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

  const activeYears = useMemo(() => {
    if (cutoffYear == null || !latestActiveYear) return null
    const s = new Set()
    for (let y = cutoffYear; y <= latestActiveYear; y++) s.add(y)
    return s
  }, [cutoffYear, latestActiveYear])

  // Per-season grade only exists when the roster was built via the internal
  // (already-onboarded-club) link — see services/scout_internal_link.py.
  // iq_scout's public-API path has no per-season grade to filter by, so the
  // chips stay informational-only there rather than silently no-op-ing.
  const gradeFilterAvailable = roster?.source === 'internal'

  const toggleGrade = (name) => {
    if (!gradeFilterAvailable) return
    setSelectedGrades((s) => {
      const n = new Set(s)
      if (n.has(name)) n.delete(name)
      else n.add(name)
      return n
    })
  }

  const windowedPlayers = useMemo(() => {
    if (cutoffYear == null && selectedGrades.size === 0) return allPlayers
    return allPlayers.map((p) => ({
      ...p,
      totals: rollupSeasons((p.seasons || []).filter((s) =>
        (cutoffYear == null || s.year >= cutoffYear) &&
        (selectedGrades.size === 0 || selectedGrades.has(s.grade))
      )),
    }))
  }, [allPlayers, cutoffYear, selectedGrades])

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
      if (an !== bn) return an ? -1 : 1
      const sa = String(va ?? ''), sb = String(vb ?? '')
      return dir === 'asc' ? sa.localeCompare(sb) : sb.localeCompare(sa)
    })
  }, [filteredPlayers, clientSort])

  const onSort = (col) => {
    setClientSort((s) => ({ col, dir: s.col === col && s.dir === 'desc' ? 'asc' : 'desc' }))
  }

  const grades = roster?.grades || []
  const ready = roster?.status === 'ready'

  const header = club ? (
    <ScoutModuleLayout
      title={club.name}
      caption={ready ? [
        `${allPlayers.length} player${allPlayers.length === 1 ? '' : 's'}`,
        grades.length ? `${grades.length} grade${grades.length === 1 ? '' : 's'}` : null,
        roster.source === 'internal'
          ? 'from BetterCricket’s own synced records — always current'
          : `built from Cricket Australia records${roster.built_at ? `, ${timeAgo(roster.built_at)}` : ''}`,
      ].filter(Boolean).join(' · ') : undefined}
      filters={
        <div className="flex items-center gap-2">
          <Search value={query} onChange={setQuery} placeholder="Search another club…" className="w-56" />
          {query.trim().length >= 2 && (
            <Btn sm onClick={() => search({ preventDefault() {} })}>{searching ? '…' : 'Go'}</Btn>
          )}
        </div>
      }
      actions={<Btn variant="ghost" onClick={rebuildRoster} disabled={rebuilding}>{rebuilding ? 'Rebuilding…' : 'Rebuild roster'}</Btn>}
    >
      {renderBody()}
    </ScoutModuleLayout>
  ) : (
    <ScoutModuleLayout title="Discover clubs" caption="Search any Australian club to browse its roster and stats.">
      {renderBody()}
    </ScoutModuleLayout>
  )

  function renderBody() {
    return (
      <div className="space-y-5">
        {atCap && (
          <div className="text-sm px-3 py-2.5 rounded-lg border border-pb-red/40 text-pb-red bg-pb-red/5">
            You've reached your {user.usage.tier_label} plan's {user.usage.player_cap}-player limit. Contact us to upgrade before adding another player.
          </div>
        )}
        {error && <p className="text-sm text-pb-red">{error}</p>}

        {!club && (
          <div className="max-w-lg space-y-3">
            <form onSubmit={search} className="flex gap-2">
              <Search value={query} onChange={setQuery} placeholder="Search for a club…" className="flex-1" />
              <Btn variant="primary" onClick={search} disabled={searching || query.trim().length < 2}>
                {searching ? 'Searching…' : 'Search'}
              </Btn>
            </form>
            {clubs.length > 0 && (
              <div className="pb-card divide-y divide-pb-hairline">
                {clubs.map((c) => (
                  <button key={c.id} onClick={() => pickClub(c)} className="w-full text-left px-4 py-3 hover:bg-pb-surface2 text-sm">
                    {c.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {club && (
          <>
            {grades.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Grades</span>
                {grades.map((g) => {
                  const name = g.grade_name || g.team_name
                  const active = selectedGrades.has(name)
                  return (
                    <button
                      key={g.grade_id}
                      onClick={() => toggleGrade(name)}
                      disabled={!gradeFilterAvailable}
                      title={gradeFilterAvailable
                        ? `${active ? 'Showing' : 'Click to show'} only ${name} (${(g.years || []).join(', ')})`
                        : `Per-season grade isn't available for this club — ${(g.years || []).join(', ')}`}
                      className={`px-2 py-0.5 rounded-full text-[11.5px] transition-colors ${
                        gradeFilterAvailable ? 'cursor-pointer' : 'cursor-default'
                      } ${active ? 'bg-[var(--pb-accent)] text-[var(--pb-on-accent)]' : 'bg-pb-surface2 text-pb-dim hover:text-pb-text'}`}
                    >
                      {name}
                    </button>
                  )
                })}
                {selectedGrades.size > 0 && (
                  <button onClick={() => setSelectedGrades(new Set())} className="text-[11px] text-pb-faint hover:text-pb-text underline">
                    Clear
                  </button>
                )}
                {!gradeFilterAvailable && (
                  <span className="text-[11px] text-pb-faintest">— not filterable for this club (no per-season grade in the public data)</span>
                )}
              </div>
            )}

            {roster?.status === 'building' && (
              <p className="text-sm text-pb-dim">Building this club's roster from Cricket Australia's records — first load can take up to a minute…</p>
            )}
            {roster?.status === 'error' && (
              <p className="text-sm text-pb-red">{roster.message || 'Could not load this club’s roster.'}</p>
            )}
            {ready && allPlayers.length === 0 && (
              <p className="text-sm text-pb-dim">No player records found for this club.</p>
            )}

            {ready && allPlayers.length > 0 && (
              <>
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Window</span>
                  <Segmented
                    options={WINDOW_OPTIONS.map((o) => ({ value: o.n ?? 'full', label: o.label.replace('Last ', '').replace(' seasons', ' SEASONS').replace(' season', ' SEASON').toUpperCase() }))}
                    value={windowN ?? 'full'}
                    onChange={(v) => setWindowN(v === 'full' ? null : v)}
                    sm
                  />
                  <span className="text-xs text-pb-faint">
                    {cutoffYear != null && latestActiveYear
                      ? (cutoffYear === latestActiveYear ? `${latestActiveYear} only` : `${cutoffYear}–${latestActiveYear} only`)
                      : "Full window covers BetterScout's ~10-year pull, not necessarily a player's whole career."}
                  </span>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Presets</span>
                  {PRESETS.map((p) => (
                    <Chip key={p.key} label={p.label} active={activePresetKey === p.key} onClick={() => togglePreset(p)} />
                  ))}
                </div>

                <FilterBar
                  filters={filters} setFilter={setFilter} activeFilterKeys={activeFilterKeys}
                  clearFilterKey={clearFilterKey} clearAllFilters={clearAllFilters}
                  visibleFilterKeys={visibleFilterKeys} revealFilter={revealFilter}
                  shown={sortedPlayers.length} total={allPlayers.length}
                />

                <div className="pb-card overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-pb-hairline">
                        {COLUMNS.map((c) => (
                          <th key={c.key} onClick={() => onSort(c.key)}
                              className={`px-3 py-2 select-none cursor-pointer font-mono text-[10px] uppercase tracking-wide2 hover:text-pb-text ${c.numeric ? 'text-right' : 'text-left'}`}
                              style={{ color: clientSort.col === c.key ? 'var(--pb-accent)' : 'var(--pb-faintest)' }}>
                            {c.label}{clientSort.col === c.key ? (clientSort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
                          </th>
                        ))}
                        <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest text-left">Form</th>
                        <th className="px-3 py-2"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedPlayers.map((p) => (
                        <PlayerRow
                          key={p.player_id} player={p}
                          sortKey={clientSort.col}
                          activeYears={activeYears}
                          expanded={expandedId === p.player_id}
                          onToggle={() => setExpandedId((id) => (id === p.player_id ? null : p.player_id))}
                          onAdd={(wid) => addPlayer(p, wid)}
                          onOpenProfile={() => openFullProfile(p)}
                          onAddToCompare={() => addToCompare(p)}
                          adding={addingId === p.player_id}
                          disabled={atCap}
                          watchlists={watchlists}
                          defaultWatchlistId={defaultWatchlistId}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="font-mono text-[10.5px] uppercase tracking-wide2 text-pb-faintest">
                  Form column = last 5 seasons, the sorted metric · grey bars fall outside the chosen window
                </p>
              </>
            )}
          </>
        )}
      </div>
    )
  }

  return header
}

function FilterBar({ filters, setFilter, activeFilterKeys, clearFilterKey, clearAllFilters, visibleFilterKeys, revealFilter, shown, total }) {
  const addable = FILTER_FIELDS.filter((c) => !visibleFilterKeys.has(c.key) && filters[`${c.key}_min`] === '' && filters[`${c.key}_max`] === '')
  return (
    <div className="pb-card p-4 space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Filters</span>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] uppercase tracking-wide2 text-pb-dim">{shown} of {total} players</span>
          {(activeFilterKeys.length > 0) && (
            <button onClick={clearAllFilters} className="text-xs text-pb-dim hover:text-pb-text underline">Clear</button>
          )}
        </div>
      </div>
      {activeFilterKeys.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {activeFilterKeys.map((c) => {
            const min = filters[`${c.key}_min`], max = filters[`${c.key}_max`]
            const label = `${c.label} ${min || '−∞'} – ${max || '∞'}`
            return <Chip key={c.key} label={`${label} ×`} active onClick={() => clearFilterKey(c.key)} />
          })}
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        {FILTER_FIELDS.filter((c) => visibleFilterKeys.has(c.key)).map((c) => (
          <div key={c.key} className="flex items-center gap-1.5">
            <label className="text-xs text-pb-faint w-16">{c.label}</label>
            <input type="number" placeholder="Min" value={filters[`${c.key}_min`]}
                   onChange={(e) => setFilter(`${c.key}_min`, e.target.value)}
                   className="w-16 bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-sm" />
            <span className="text-pb-faint text-xs">–</span>
            <input type="number" placeholder="Max" value={filters[`${c.key}_max`]}
                   onChange={(e) => setFilter(`${c.key}_max`, e.target.value)}
                   className="w-16 bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-sm" />
            <button onClick={() => clearFilterKey(c.key)} className="text-pb-faint hover:text-pb-red text-xs">×</button>
          </div>
        ))}
        {addable.map((c) => (
          <button key={c.key} onClick={() => revealFilter(c.key)}
                  className="text-xs px-2 py-1 rounded border border-dashed border-pb-hairline2 text-pb-faint hover:text-pb-text hover:border-pb-faint">
            + {c.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function PlayerRow({ player: p, sortKey, activeYears, expanded, onToggle, onAdd, onOpenProfile, onAddToCompare, adding, disabled, watchlists, defaultWatchlistId }) {
  const t = p.totals || {}
  const tracked = !!p.scouted_player_id
  const identity = [p.grade_name].filter(Boolean).join(' · ')
  return (
    <>
      <tr className="border-b border-pb-hairline last:border-0 hover:bg-pb-surface2/40 cursor-pointer transition-colors" onClick={onToggle}>
        <td className="px-3 py-2">
          <div className="flex items-center gap-2.5">
            <PlayerAvatar name={p.name} size={32} dashed />
            <div className="min-w-0">
              <div className="font-medium text-[13.5px] truncate">{p.name}</div>
              {identity && <div className="font-mono text-[10.5px] text-pb-faint uppercase truncate">{identity}</div>}
            </div>
          </div>
        </td>
        <td className="px-3 py-2 text-right font-mono">{t.matches ?? '—'}</td>
        <td className="px-3 py-2 text-right font-mono">{t.runs ?? '—'}</td>
        <td className="px-3 py-2 text-right font-mono">{t.average ?? '—'}</td>
        <td className="px-3 py-2 text-right font-mono">{t.strike_rate ?? '—'}</td>
        <td className="px-3 py-2 text-right font-mono">{t.wickets ?? '—'}</td>
        <td className="px-3 py-2 text-right font-mono">{t.bowling_average ?? '—'}</td>
        <td className="px-3 py-2 text-right font-mono">{t.economy ?? '—'}</td>
        <td className="px-3 py-2">
          <Sparkline seasons={p.seasons} metricKey={sortKey === 'name' ? 'runs' : sortKey} activeYears={activeYears} height={20} />
        </td>
        <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
          <AddControl tracked={tracked} adding={adding} disabled={disabled} onAdd={() => onAdd(defaultWatchlistId)} watchlistCount={p.watchlist_count} />
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-pb-hairline last:border-0" style={{ background: 'var(--pb-surface2)' }}>
          <td colSpan={COLUMNS.length + 2} className="px-3 py-4">
            <PlayerPreview player={p} tracked={tracked} adding={adding} disabled={disabled}
              onAdd={onAdd} onOpenProfile={onOpenProfile} onAddToCompare={onAddToCompare}
              watchlists={watchlists} defaultWatchlistId={defaultWatchlistId} />
          </td>
        </tr>
      )}
    </>
  )
}

function AddControl({ tracked, adding, disabled, onAdd, watchlistCount }) {
  if (tracked) {
    return <span className="text-xs font-mono text-pb-accent whitespace-nowrap">Tracked ✓</span>
  }
  return (
    <Btn sm variant="primary" onClick={onAdd} disabled={adding || disabled}
         title={disabled ? "You've reached your plan's player limit." : undefined}>
      {adding ? 'Adding…' : 'Track'}
    </Btn>
  )
}

function WatchlistPicker({ watchlists, defaultWatchlistId, onPick }) {
  const [open, setOpen] = useState(false)
  if (!open) {
    return (
      <Btn sm variant="soft" onClick={() => setOpen(true)} className="w-full justify-center">
        Add to watchlist ▾
      </Btn>
    )
  }
  return (
    <select
      autoFocus defaultValue={defaultWatchlistId || ''}
      onChange={(e) => { onPick(e.target.value || undefined); setOpen(false) }}
      onBlur={() => setOpen(false)}
      className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-xs"
    >
      <option value="">My Players (default)</option>
      {watchlists.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
    </select>
  )
}

function PlayerPreview({ player: p, tracked, adding, disabled, onAdd, onOpenProfile, onAddToCompare, watchlists, defaultWatchlistId }) {
  const t = p.totals || {}
  const seasons = p.seasons || []
  const hasGrade = seasons.some((s) => s.grade)
  return (
    <div className="flex gap-5">
      <div className="w-[78px] h-[96px] shrink-0 rounded-lg border border-dashed border-pb-hairline2 flex flex-col items-center justify-center gap-1.5 bg-pb-surface">
        <PlayerAvatar name={p.name} size={40} dashed />
        <span className="font-mono text-[8px] text-pb-faintest text-center leading-tight px-1">No photo in CA data</span>
      </div>

      <div className="flex-1 min-w-0 space-y-3">
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          <Stat label="High score" value={t.high_score} />
          <Stat label="50s / 100s" value={`${t.fifties ?? 0} / ${t.hundreds ?? 0}`} />
          <Stat label="Best figures" value={t.best} />
          <Stat label="Catches" value={t.catches} />
          <Stat label="Grades played" value={new Set(seasons.map((s) => s.grade).filter(Boolean)).size || '—'} />
        </div>
        {seasons.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-pb-hairline font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faintest">
                  <th className="text-left px-2 py-1">Season</th>
                  {hasGrade && <th className="text-left px-2 py-1">Grade</th>}
                  <th className="text-right px-2 py-1">Mat</th>
                  <th className="text-right px-2 py-1">Runs</th>
                  <th className="text-right px-2 py-1">Avg</th>
                  <th className="text-right px-2 py-1">Wkts</th>
                  <th className="text-right px-2 py-1">Econ</th>
                </tr>
              </thead>
              <tbody>
                {seasons.map((s) => (
                  <tr key={s.year} className="border-b border-pb-hairline last:border-0">
                    <td className="px-2 py-1 font-mono">{s.year}</td>
                    {hasGrade && <td className="px-2 py-1">{s.grade || '—'}</td>}
                    <td className="px-2 py-1 text-right font-mono">{s.matches}</td>
                    <td className="px-2 py-1 text-right font-mono">{s.runs}</td>
                    <td className="px-2 py-1 text-right font-mono">{s.average ?? '—'}</td>
                    <td className="px-2 py-1 text-right font-mono">{s.wickets}</td>
                    <td className="px-2 py-1 text-right font-mono">{s.economy ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="w-[196px] shrink-0 space-y-2" onClick={(e) => e.stopPropagation()}>
        <Btn variant="primary" onClick={onOpenProfile} className="w-full justify-center">Open full profile</Btn>
        <WatchlistPicker watchlists={watchlists} defaultWatchlistId={defaultWatchlistId} onPick={onAdd} />
        <Btn variant="ghost" onClick={onAddToCompare} className="w-full justify-center">Add to compare</Btn>
        {tracked && (
          <div className="font-mono text-[10px] text-pb-faint text-center pt-1">
            On {p.watchlist_count} watchlist{p.watchlist_count === 1 ? '' : 's'}
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint">{label}</div>
      <div className="text-sm font-semibold mt-0.5">{value ?? '—'}</div>
    </div>
  )
}
