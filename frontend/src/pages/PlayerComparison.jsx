import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import { PageHeader, PbSpinner } from '../lib/presskit'
import { useNameFormat, nameMatchesSearch } from '../lib/nameFormat'

const MAX_PLAYERS = 5
const PLAYER_COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444']

const BATTING_METRICS = [
  { key: 'innings',        label: 'INNINGS',      higher: true  },
  { key: 'total_runs',     label: 'RUNS',          higher: true  },
  { key: 'average',        label: 'BATTING AVG',   higher: true  },
  { key: 'strike_rate',    label: 'STRIKE RATE',   higher: true  },
  { key: 'high_score',     label: 'HIGH SCORE',    higher: true  },
  { key: 'fifties',        label: 'FIFTIES',       higher: true  },
  { key: 'hundreds',       label: 'CENTURIES',     higher: true  },
  { key: 'total_sixes',    label: 'SIXES',         higher: true  },
  { key: 'total_fours',    label: 'FOURS',         higher: true  },
  { key: 'ducks',          label: 'DUCKS',         higher: false },
]

const BOWLING_METRICS = [
  { key: 'total_wickets',       label: 'WICKETS',      higher: true  },
  { key: 'average',             label: 'BOWLING AVG',  higher: false },
  { key: 'economy',             label: 'ECONOMY',      higher: false },
  { key: 'best_figures_wickets',label: 'BEST FIGURES', higher: true  },
  { key: 'five_fors',           label: 'FIVE-FORS',    higher: true  },
  { key: 'total_maidens',       label: 'MAIDENS',      higher: true  },
  { key: 'bowling_strike_rate', label: 'BOWL S/R',     higher: false },
]

const FIELDING_METRICS = [
  { key: 'total_catches',    label: 'CATCHES',     higher: true },
  { key: 'total_run_outs',   label: 'RUN OUTS',    higher: true },
  { key: 'total_stumpings',  label: 'STUMPINGS',   higher: true },
  { key: 'total_dismissals', label: 'DISMISSALS',  higher: true },
]

// Cross-discipline career overview
const GAMES_METRICS = [
  { key: 'games',            label: 'MATCHES',      higher: true, src: 'bat'   },
  { key: 'innings',          label: 'BAT INNINGS',  higher: true, src: 'bat'   },
  { key: 'total_runs',       label: 'TOTAL RUNS',   higher: true, src: 'bat'   },
  { key: 'total_wickets',    label: 'WICKETS',      higher: true, src: 'bowl'  },
  { key: 'total_catches',    label: 'CATCHES',      higher: true, src: 'field' },
  { key: 'total_dismissals', label: 'DISMISSALS',   higher: true, src: 'field' },
]

const FILTER_PRESETS = [
  { id: 'career',         label: 'All Time'     },
  { id: 'current_season', label: 'This Season'  },
  { id: 'last_season',    label: 'Last Season'  },
  { id: 'last_1',         label: 'Last Game'    },
  { id: 'last_3',         label: 'Last 3 Games' },
  { id: 'last_5',         label: 'Last 5 Games' },
  { id: 'custom',         label: 'Custom'       },
]

const TABS = [
  { id: 'batting',  label: 'BATTING'  },
  { id: 'bowling',  label: 'BOWLING'  },
  { id: 'fielding', label: 'FIELDING' },
  { id: 'games',    label: 'GAMES'    },
]

function getInitials(name) {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
  return parts[0].slice(0, 2).toUpperCase()
}

function PlayerAvatar({ player, size = 40, colorIndex = 0 }) {
  const [imgError, setImgError] = useState(false)
  const photoUrl = player?.photo_url
  const color = PLAYER_COLORS[colorIndex % PLAYER_COLORS.length]
  const initials = getInitials(player?.display_name || player?.name)

  if (photoUrl && !imgError) {
    return (
      <img
        src={photoUrl}
        alt={player?.name}
        style={{ width: size, height: size }}
        className="rounded-full object-cover border border-pb-hairline flex-shrink-0"
        onError={() => setImgError(true)}
      />
    )
  }
  return (
    <div
      style={{ width: size, height: size, background: color }}
      className="rounded-full flex items-center justify-center flex-shrink-0 select-none"
    >
      <span className="text-white font-bold" style={{ fontSize: Math.round(size * 0.36) }}>
        {initials}
      </span>
    </div>
  )
}

function PlayerSearch({ players, playersLoading, onSelect, excludeIds = [], fmt = n => n }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const blurTimer = useRef(null)

  const filtered = useMemo(() => {
    const available = players.filter(p => !excludeIds.includes(p.id))
    if (!query.trim()) return available.slice(0, 20)
    return available.filter(p => nameMatchesSearch(p.display_name || p.name, query)).slice(0, 20)
  }, [players, query, excludeIds])

  return (
    <div className="relative">
      <div className="relative">
        <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-pb-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          type="text"
          placeholder="Add player…"
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => { if (blurTimer.current) clearTimeout(blurTimer.current); setOpen(true) }}
          onBlur={() => { blurTimer.current = setTimeout(() => setOpen(false), 200) }}
          className="w-full bg-pb-surface border pb-hairline text-pb-text text-sm rounded pl-8 pr-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faint"
        />
      </div>
      {open && (filtered.length > 0 || playersLoading) && (
        <div className="absolute z-50 w-full mt-1 bg-pb-surface border pb-hairline rounded shadow-xl max-h-56 overflow-y-auto pb-scroll">
          {playersLoading && filtered.length === 0 ? (
            <p className="px-3 py-2 text-sm text-pb-faint">Loading…</p>
          ) : (
            filtered.map(p => (
              <button
                key={p.id}
                onMouseDown={() => { onSelect(p); setQuery(''); setOpen(false) }}
                className="w-full text-left px-3 py-2 text-sm text-pb-dim hover:bg-pb-surface2 hover:text-pb-text transition-colors"
              >
                {fmt(p.display_name || p.name)}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

function buildFilterParams(filterMode, seasons, customStart, customEnd) {
  if (filterMode === 'career') return {}
  if (filterMode === 'current_season') {
    const s = seasons[0]
    return s ? { seasonId: s.id } : {}
  }
  if (filterMode === 'last_season') {
    const s = seasons[1]
    return s ? { seasonId: s.id } : {}
  }
  if (filterMode === 'last_1') return { lastNGames: 1 }
  if (filterMode === 'last_3') return { lastNGames: 3 }
  if (filterMode === 'last_5') return { lastNGames: 5 }
  if (filterMode === 'custom') {
    const p = {}
    if (customStart) p.startDate = customStart
    if (customEnd) p.endDate = customEnd
    return p
  }
  return {}
}

function filterCaption(filterMode, seasons, appliedStart, appliedEnd) {
  if (filterMode === 'career') return 'ALL TIME'
  if (filterMode === 'current_season') return seasons[0] ? seasons[0].name.toUpperCase() : 'CURRENT SEASON'
  if (filterMode === 'last_season') return seasons[1] ? seasons[1].name.toUpperCase() : 'LAST SEASON'
  if (filterMode === 'last_1') return 'LAST GAME'
  if (filterMode === 'last_3') return 'LAST 3 GAMES'
  if (filterMode === 'last_5') return 'LAST 5 GAMES'
  if (filterMode === 'custom') {
    if (appliedStart && appliedEnd) return `${appliedStart} – ${appliedEnd}`
    if (appliedStart) return `FROM ${appliedStart}`
    if (appliedEnd) return `TO ${appliedEnd}`
    return 'CUSTOM DATE RANGE'
  }
  return 'ALL TIME'
}

// Returns 'best' | 'worst' | null for each value in the array.
// Only marks unique best/worst (ties get null).
function getRowHighlights(values, higher) {
  const nums = values.map(v => {
    const n = parseFloat(v)
    return isNaN(n) ? null : n
  })
  const valid = nums.filter(n => n !== null)
  if (valid.length < 2) return values.map(() => null)

  const best  = higher ? Math.max(...valid) : Math.min(...valid)
  const worst = higher ? Math.min(...valid) : Math.max(...valid)
  if (best === worst) return values.map(() => null)

  const bestCount  = valid.filter(n => n === best).length
  const worstCount = valid.filter(n => n === worst).length

  return nums.map(n => {
    if (n === null) return null
    if (n === best  && bestCount  === 1) return 'best'
    if (n === worst && worstCount === 1) return 'worst'
    return null
  })
}

export default function PlayerComparison() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  useClubTheme(club)
  const fmt = useNameFormat(club)

  const [players,        setPlayers]        = useState([])
  const [playersLoading, setPlayersLoading] = useState(false)
  const [seasons,        setSeasons]        = useState([])

  const [selectedPlayers, setSelectedPlayers] = useState([])
  const [statsMap,         setStatsMap]        = useState({}) // { playerId: { bat, bowl, field } }
  const [loadingIds,       setLoadingIds]      = useState(new Set())

  const [filterMode,    setFilterMode]    = useState('career')
  const [draftStart,    setDraftStart]    = useState('')
  const [draftEnd,      setDraftEnd]      = useState('')
  const [appliedStart,  setAppliedStart]  = useState('')
  const [appliedEnd,    setAppliedEnd]    = useState('')
  const [activeTab,     setActiveTab]     = useState('batting')
  const [statsError,    setStatsError]    = useState(null)

  useEffect(() => {
    if (!orgId) return
    setPlayersLoading(true)
    api.listPlayers(orgId)
      .then(data => { setPlayers(data); setPlayersLoading(false) })
      .catch(() => { setPlayers([]); setPlayersLoading(false) })
    api.getOrgSeasons(orgId).then(setSeasons).catch(() => setSeasons([]))
  }, [orgId])

  const filterParamsKey = useMemo(
    () => JSON.stringify(buildFilterParams(filterMode, seasons, appliedStart, appliedEnd)),
    [filterMode, seasons, appliedStart, appliedEnd],
  )

  const customReady = filterMode !== 'custom' || appliedStart || appliedEnd
  const draftDirty  = draftStart !== appliedStart || draftEnd !== appliedEnd

  const fetchPlayerStats = useCallback((playerId, filterParams) => {
    setLoadingIds(prev => new Set([...prev, playerId]))
    api.getPlayerStats(playerId, filterParams)
      .then(data => {
        setStatsMap(prev => ({
          ...prev,
          [playerId]: {
            bat:   data.career_batting  || {},
            bowl:  data.career_bowling  || {},
            field: data.career_fielding || {},
          },
        }))
        setStatsError(null)
      })
      .catch(e => setStatsError(e?.message || 'Failed to load stats'))
      .finally(() => setLoadingIds(prev => { const n = new Set(prev); n.delete(playerId); return n }))
  }, [])

  // Re-fetch all players on filter change
  useEffect(() => {
    if (!customReady || selectedPlayers.length === 0) return
    const params = JSON.parse(filterParamsKey)
    selectedPlayers.forEach(p => fetchPlayerStats(p.id, params))
  }, [filterParamsKey, customReady]) // eslint-disable-line react-hooks/exhaustive-deps

  const currentMetrics = useMemo(() => {
    if (activeTab === 'batting')  return BATTING_METRICS.map(m => ({ ...m, src: 'bat'   }))
    if (activeTab === 'bowling')  return BOWLING_METRICS.map(m => ({ ...m, src: 'bowl'  }))
    if (activeTab === 'fielding') return FIELDING_METRICS.map(m => ({ ...m, src: 'field'}))
    return GAMES_METRICS
  }, [activeTab])

  const addPlayer = (player) => {
    setSelectedPlayers(prev => [...prev, player])
    if (customReady) fetchPlayerStats(player.id, JSON.parse(filterParamsKey))
  }

  const removePlayer = (playerId) => {
    setSelectedPlayers(prev => prev.filter(p => p.id !== playerId))
    setStatsMap(prev => { const n = { ...prev }; delete n[playerId]; return n })
    setLoadingIds(prev => { const n = new Set(prev); n.delete(playerId); return n })
  }

  const anyLoading     = loadingIds.size > 0
  const canAddMore     = selectedPlayers.length < MAX_PLAYERS
  const hasEnough      = selectedPlayers.length >= 2
  const excludeIds     = selectedPlayers.map(p => p.id)

  if (inactive) return <ClubInactive />

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1300px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow="HEAD TO HEAD"
          title="Compare players."
          meta={[<span key="s">Up to {MAX_PLAYERS} players · Stats side by side.</span>]}
        />

        {/* ── Player selection ── */}
        <div className="pb-card p-4 mb-4">
          <div className="flex flex-wrap items-center gap-3">
            {selectedPlayers.map((player, idx) => (
              <div
                key={player.id}
                className="flex items-center gap-2.5 bg-pb-surface2 rounded-lg px-3 py-2 border pb-hairline"
              >
                <PlayerAvatar player={player} size={34} colorIndex={idx} />
                <div className="min-w-0">
                  <p
                    className="font-semibold text-sm leading-tight truncate max-w-[110px]"
                    style={{ color: PLAYER_COLORS[idx % PLAYER_COLORS.length] }}
                  >
                    {fmt(player.display_name || player.name)}
                  </p>
                  {player.player_role && (
                    <p className="font-mono text-[9px] text-pb-faint uppercase tracking-wide leading-tight mt-0.5">
                      {player.player_role}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => removePlayer(player.id)}
                  className="text-pb-faint hover:text-red-400 transition-colors text-lg leading-none ml-1 flex-shrink-0"
                  aria-label="Remove player"
                >
                  ×
                </button>
              </div>
            ))}
            {canAddMore && (
              <div className="w-full sm:w-48">
                <PlayerSearch
                  players={players}
                  playersLoading={playersLoading}
                  onSelect={addPlayer}
                  excludeIds={excludeIds}
                  fmt={fmt}
                />
              </div>
            )}
          </div>
          {selectedPlayers.length === 0 && (
            <p className="text-pb-faintest text-xs font-mono mt-2 tracking-wide">
              SEARCH ABOVE · ADD UP TO {MAX_PLAYERS} PLAYERS · GREEN = BEST · RED = WORST
            </p>
          )}
        </div>

        {/* ── Filter bar ── */}
        <div className="pb-card p-3 mb-4">
          <div className="flex flex-wrap gap-2 items-center">
            <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mr-1 hidden sm:inline">Filter</span>
            {FILTER_PRESETS.map(p => (
              <button
                key={p.id}
                onClick={() => setFilterMode(p.id)}
                className={`font-mono text-[10px] tracking-wide2 px-2.5 py-1 rounded border transition-colors ${
                  filterMode === p.id
                    ? 'border-transparent text-white'
                    : 'border-pb-hairline text-pb-dim hover:text-pb-text hover:border-pb-faint'
                }`}
                style={filterMode === p.id ? { background: 'var(--pb-accent)', borderColor: 'var(--pb-accent)' } : {}}
              >
                {p.label}
              </button>
            ))}
          </div>
          {filterMode === 'custom' && (
            <div className="flex flex-wrap gap-3 mt-3 items-center">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-pb-faint">FROM</span>
                <input
                  type="date"
                  value={draftStart}
                  onChange={e => setDraftStart(e.target.value)}
                  className="bg-pb-surface border pb-hairline text-pb-text text-xs rounded px-2 py-1 focus:outline-none focus:border-pb-accent"
                />
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-pb-faint">TO</span>
                <input
                  type="date"
                  value={draftEnd}
                  onChange={e => setDraftEnd(e.target.value)}
                  className="bg-pb-surface border pb-hairline text-pb-text text-xs rounded px-2 py-1 focus:outline-none focus:border-pb-accent"
                />
              </div>
              <button
                onClick={() => { setAppliedStart(draftStart); setAppliedEnd(draftEnd) }}
                disabled={!draftStart && !draftEnd}
                className="font-mono text-[10px] tracking-wide2 px-3 py-1 rounded border transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                style={draftDirty && (draftStart || draftEnd)
                  ? { background: 'var(--pb-accent)', borderColor: 'var(--pb-accent)', color: 'white' }
                  : { borderColor: 'var(--pb-hairline)', color: 'var(--pb-dim)' }}
              >
                Apply
              </button>
            </div>
          )}
        </div>

        {/* ── Error ── */}
        {statsError && (
          <div className="mb-4 px-4 py-3 rounded border border-red-500/40 bg-red-500/10 text-red-400 font-mono text-xs">
            Error loading stats: {statsError}
          </div>
        )}

        {/* ── Empty state ── */}
        {!hasEnough && (
          <div className="pb-card py-12 text-center">
            <p className="text-pb-faint text-sm">
              {selectedPlayers.length === 0
                ? 'Add at least 2 players to start comparing.'
                : 'Add one more player to start comparing.'}
            </p>
            <p className="text-pb-faintest text-xs mt-1 font-mono tracking-wide">
              GREEN = BEST · RED = WORST · UP TO {MAX_PLAYERS} PLAYERS
            </p>
          </div>
        )}

        {/* ── Custom-range prompt ── */}
        {hasEnough && filterMode === 'custom' && !customReady && (
          <div className="pb-card py-8 text-center">
            <p className="text-pb-faint text-sm">Enter a date range above to filter stats.</p>
          </div>
        )}

        {/* ── Comparison card ── */}
        {hasEnough && customReady && (
          <div className="pb-card overflow-hidden">
            {/* Tab bar */}
            <div className="flex overflow-x-auto pb-no-scrollbar" style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`font-mono text-[11px] tracking-wide2 px-5 py-3 transition-colors ${
                    activeTab === tab.id ? 'text-pb-text' : 'text-pb-faint hover:text-pb-dim'
                  }`}
                  style={
                    activeTab === tab.id
                      ? { borderBottom: '2px solid var(--pb-accent)', marginBottom: '-1px' }
                      : { borderBottom: '2px solid transparent', marginBottom: '-1px' }
                  }
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Loading */}
            {anyLoading && (
              <div className="py-8 flex justify-center">
                <PbSpinner message="Loading stats…" />
              </div>
            )}

            {/* Table */}
            {!anyLoading && (
              <div className="overflow-x-auto">
                <table
                  className="w-full"
                  style={{
                    tableLayout: 'fixed',
                    minWidth: `${110 + selectedPlayers.length * 130}px`,
                  }}
                >
                  <colgroup>
                    <col style={{ width: '110px' }} />
                    {selectedPlayers.map((_, i) => <col key={i} />)}
                  </colgroup>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--pb-hairline)' }}>
                      <th className="py-4 pl-4 text-left align-bottom">
                        <span className="font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">STAT</span>
                      </th>
                      {selectedPlayers.map((player, idx) => (
                        <th
                          key={player.id}
                          className="py-4 px-3 text-center align-bottom"
                          style={{ borderLeft: '1px solid var(--pb-hairline)' }}
                        >
                          <div className="flex flex-col items-center gap-1.5">
                            <PlayerAvatar player={player} size={42} colorIndex={idx} />
                            <Link
                              to={`/players/${player.id}`}
                              className="font-semibold text-xs leading-tight hover:opacity-75 transition-opacity block"
                              style={{ color: PLAYER_COLORS[idx % PLAYER_COLORS.length] }}
                            >
                              {fmt(player.display_name || player.name)}
                            </Link>
                            {player.player_role && (
                              <span className="font-mono text-[9px] text-pb-faint uppercase tracking-wide leading-none">
                                {player.player_role}
                              </span>
                            )}
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {currentMetrics.map((metric, rowIdx) => {
                      const rawValues = selectedPlayers.map(p => {
                        const s = statsMap[p.id]
                        if (!s) return null
                        const obj = metric.src === 'bat' ? s.bat : metric.src === 'bowl' ? s.bowl : s.field
                        return obj?.[metric.key] ?? null
                      })
                      const highlights = getRowHighlights(rawValues, metric.higher)

                      return (
                        <tr
                          key={`${metric.src}-${metric.key}-${rowIdx}`}
                          style={rowIdx > 0 ? { borderTop: '1px solid var(--pb-hairline)' } : {}}
                        >
                          <td className="py-3 pl-4 align-middle">
                            <span className="font-mono text-[10px] tracking-wide text-pb-faint">
                              {metric.label}
                            </span>
                          </td>
                          {selectedPlayers.map((player, pIdx) => {
                            const val       = rawValues[pIdx]
                            const highlight = highlights[pIdx]
                            return (
                              <td
                                key={player.id}
                                className="py-3 px-3 text-center align-middle"
                                style={{
                                  borderLeft:  '1px solid var(--pb-hairline)',
                                  background:
                                    highlight === 'best'  ? 'rgba(34,197,94,0.14)'  :
                                    highlight === 'worst' ? 'rgba(239,68,68,0.14)'  : undefined,
                                  transition: 'background 0.2s',
                                }}
                              >
                                <span
                                  className="font-mono text-[14px] font-bold pb-num"
                                  style={{
                                    color:
                                      highlight === 'best'  ? '#86efac' :   // green-300
                                      highlight === 'worst' ? '#fca5a5' :   // red-300
                                      val != null           ? 'var(--pb-text)' : 'var(--pb-faintest)',
                                  }}
                                >
                                  {val ?? '—'}
                                </span>
                              </td>
                            )
                          })}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {hasEnough && customReady && !anyLoading && (
          <p className="text-center text-pb-faintest font-mono text-[10px] mt-3 tracking-wide2">
            GREEN = BEST · RED = WORST · {filterCaption(filterMode, seasons, appliedStart, appliedEnd)}
          </p>
        )}
      </main>
    </div>
  )
}
