import { useParams, useNavigate, useLocation, Link } from 'react-router-dom'
import { useState, useEffect, useCallback, useRef } from 'react'
import { useClub } from '../hooks/useClub'
import { useClubData } from '../hooks/useClubData'
import { api } from '../lib/api'
import clsx from 'clsx'
import ClubInactive from './ClubInactive'
import LoadingSpinner from '../components/LoadingSpinner'

// ─── Stat definitions ─────────────────────────────────────────────────────────

const PLAYER_STAT_GROUPS = [
  {
    key: 'participation',
    label: 'Participation',
    color: 'purple',
    stats: [
      { key: 'matches',       label: 'Matches',      decimal: false },
      { key: 'seasons_played',label: 'Seasons',       decimal: false },
    ],
  },
  {
    key: 'batting',
    label: 'Batting',
    color: 'emerald',
    stats: [
      { key: 'batting_innings',     label: 'Innings',       decimal: false },
      { key: 'runs',                label: 'Runs',          decimal: false },
      { key: 'not_outs',            label: 'Not Outs',      decimal: false },
      { key: 'batting_average',     label: 'Average',       decimal: true  },
      { key: 'batting_strike_rate', label: 'Strike Rate',   decimal: true  },
      { key: 'high_score',          label: 'High Score',    decimal: false },
      { key: 'fifties',             label: '50s',           decimal: false },
      { key: 'hundreds',            label: '100s',          decimal: false },
      { key: 'ducks',               label: 'Ducks',         decimal: false },
      { key: 'fours',               label: '4s',            decimal: false },
      { key: 'sixes',               label: '6s',            decimal: false },
    ],
  },
  {
    key: 'bowling',
    label: 'Bowling',
    color: 'orange',
    stats: [
      { key: 'wickets',             label: 'Wickets',       decimal: false },
      { key: 'overs',               label: 'Overs',         decimal: true  },
      { key: 'bowling_average',     label: 'Avg',           decimal: true  },
      { key: 'bowling_economy',     label: 'Economy',       decimal: true  },
      { key: 'five_wicket_innings', label: '5-fors',        decimal: false },
      { key: 'maidens',             label: 'Maidens',       decimal: false },
      { key: 'best_bowling_wickets',label: 'Best (Wkts)',   decimal: false },
    ],
  },
  {
    key: 'fielding',
    label: 'Fielding',
    color: 'sky',
    stats: [
      { key: 'catches',   label: 'Catches',   decimal: false },
      { key: 'run_outs',  label: 'Run Outs',  decimal: false },
      { key: 'stumpings', label: 'Stumpings', decimal: false },
    ],
  },
]

const GRADE_STAT_GROUPS = [
  {
    key: 'general',
    label: 'General',
    color: 'purple',
    stats: [
      { key: 'matches',        label: 'Matches',        decimal: false },
      { key: 'unique_players', label: 'Players Used',   decimal: false },
    ],
  },
  {
    key: 'batting',
    label: 'Batting',
    color: 'emerald',
    stats: [
      { key: 'runs',     label: 'Total Runs', decimal: false },
      { key: 'hundreds', label: '100s',       decimal: false },
      { key: 'fifties',  label: '50s',        decimal: false },
      { key: 'ducks',    label: 'Ducks',      decimal: false },
    ],
  },
  {
    key: 'bowling',
    label: 'Bowling',
    color: 'orange',
    stats: [
      { key: 'wickets', label: 'Wickets', decimal: false },
    ],
  },
  {
    key: 'fielding',
    label: 'Fielding',
    color: 'sky',
    stats: [
      { key: 'catches',   label: 'Catches',   decimal: false },
      { key: 'run_outs',  label: 'Run Outs',  decimal: false },
      { key: 'stumpings', label: 'Stumpings', decimal: false },
    ],
  },
]

const OPERATORS = [
  { key: 'gte', label: '≥', title: 'Greater than or equal to' },
  { key: 'gt',  label: '>',  title: 'Greater than' },
  { key: 'eq',  label: '=',  title: 'Equal to' },
  { key: 'lte', label: '≤', title: 'Less than or equal to' },
  { key: 'lt',  label: '<',  title: 'Less than' },
  { key: 'ne',  label: '≠', title: 'Not equal to' },
]

const GROUP_TABS = [
  { key: 'player', label: 'Players' },
  { key: 'team',   label: 'Team / Season' },
  { key: 'grade',  label: 'Grade' },
]

const GROUP_COLOR_CLASSES = {
  purple:  { pill: 'bg-purple-900/60 text-purple-300 border border-purple-700',  dot: 'bg-purple-400' },
  emerald: { pill: 'bg-emerald-900/60 text-emerald-300 border border-emerald-700', dot: 'bg-emerald-400' },
  orange:  { pill: 'bg-orange-900/60 text-orange-300 border border-orange-700',   dot: 'bg-orange-400' },
  sky:     { pill: 'bg-sky-900/60 text-sky-300 border border-sky-700',            dot: 'bg-sky-400' },
}

// ─── URL state helpers ─────────────────────────────────────────────────────────

function encodeFiltersToUrl(filters) {
  return filters
    .filter(f => f.field && f.op && f.value !== '')
    .map(f => `${f.field}:${f.op}:${f.value}`)
    .join(',')
}

function decodeFiltersFromUrl(str) {
  if (!str) return []
  return str.split(',').flatMap((f, i) => {
    const parts = f.split(':')
    if (parts.length !== 3) return []
    return [{ id: Date.now() + i, field: parts[0], op: parts[1], value: parts[2] }]
  })
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function getAllStats(groups) {
  return groups.flatMap(g => g.stats.map(s => ({ ...s, group: g.key, color: g.color, groupLabel: g.label })))
}

function findStatMeta(statKey, groups) {
  for (const g of groups) {
    const s = g.stats.find(s => s.key === statKey)
    if (s) return { ...s, group: g.key, color: g.color, groupLabel: g.label }
  }
  return null
}

function findGroupColor(statKey, groups) {
  const meta = findStatMeta(statKey, groups)
  return meta?.color || 'purple'
}

function fmt(v, decimal) {
  if (v === null || v === undefined) return '—'
  const n = parseFloat(v)
  if (isNaN(n)) return v
  return decimal ? n.toFixed(2) : n.toLocaleString()
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function FilterRow({ filter, statGroups, onUpdate, onRemove }) {
  const allStats = getAllStats(statGroups)
  const meta = findStatMeta(filter.field, statGroups)
  const color = meta?.color || 'purple'
  const colors = GROUP_COLOR_CLASSES[color]

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Category + stat selector */}
      <select
        value={filter.field}
        onChange={e => onUpdate({ field: e.target.value, op: filter.op, value: filter.value })}
        className="bg-navy-800 border border-navy-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 cursor-pointer"
      >
        {statGroups.map(g => (
          <optgroup key={g.key} label={g.label}>
            {g.stats.map(s => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </optgroup>
        ))}
      </select>

      {/* Operator */}
      <select
        value={filter.op}
        onChange={e => onUpdate({ field: filter.field, op: e.target.value, value: filter.value })}
        className="bg-navy-800 border border-navy-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 cursor-pointer w-16 text-center"
      >
        {OPERATORS.map(op => (
          <option key={op.key} value={op.key} title={op.title}>{op.label}</option>
        ))}
      </select>

      {/* Value */}
      <input
        type="number"
        value={filter.value}
        onChange={e => onUpdate({ field: filter.field, op: filter.op, value: e.target.value })}
        placeholder="0"
        className="bg-navy-800 border border-navy-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 w-24"
        min="0"
        step="any"
      />

      {/* Category badge */}
      {meta && (
        <span className={clsx('hidden sm:inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium', colors.pill)}>
          <span className={clsx('w-1.5 h-1.5 rounded-full', colors.dot)} />
          {meta.groupLabel}
        </span>
      )}

      {/* Remove */}
      <button
        onClick={onRemove}
        className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-950/40 rounded-md transition-colors"
        title="Remove filter"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  )
}

function SortIcon({ direction }) {
  if (!direction) return (
    <svg className="w-3.5 h-3.5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" />
    </svg>
  )
  return direction === 'desc'
    ? <svg className="w-3.5 h-3.5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
      </svg>
    : <svg className="w-3.5 h-3.5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
      </svg>
}

// ─── Main component ────────────────────────────────────────────────────────────

export default function StatLab() {
  const { clubSlug } = useParams()
  const { club, orgId, loading: clubLoading, inactive } = useClub(clubSlug)
  const { seasons } = useClubData(orgId)
  const location = useLocation()
  const navigate = useNavigate()

  // ── State initialised from URL ──
  const searchParams = new URLSearchParams(location.search)
  const [mode, setMode] = useState(searchParams.get('mode') || 'career')
  const [seasonId, setSeasonId] = useState(searchParams.get('season_id') || '')
  const [groupBy, setGroupBy] = useState(searchParams.get('group') || 'player')
  const [sortBy, setSortBy] = useState(searchParams.get('sort') || 'runs')
  const [sortDir, setSortDir] = useState(searchParams.get('dir') || 'desc')
  const [filters, setFilters] = useState(() => decodeFiltersFromUrl(searchParams.get('filters') || ''))
  const [pendingRun, setPendingRun] = useState(false)

  // ── Results state ──
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [hasQueried, setHasQueried] = useState(false)
  const [clientSort, setClientSort] = useState({ col: null, dir: null })

  const statGroups = groupBy === 'player' ? PLAYER_STAT_GROUPS : GRADE_STAT_GROUPS

  // ── Sync state → URL ──
  useEffect(() => {
    const p = new URLSearchParams()
    p.set('mode', mode)
    p.set('group', groupBy)
    p.set('sort', sortBy)
    p.set('dir', sortDir)
    if (mode === 'season' && seasonId) p.set('season_id', seasonId)
    const encoded = encodeFiltersToUrl(filters)
    if (encoded) p.set('filters', encoded)
    navigate(`?${p.toString()}`, { replace: true })
  }, [mode, seasonId, groupBy, sortBy, sortDir, filters])

  // ── Reset sort when server result changes ──
  useEffect(() => { setClientSort({ col: null, dir: null }) }, [rows])

  // ── Query execution ──
  const runQuery = useCallback(async () => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    setHasQueried(true)
    setClientSort({ col: null, dir: null })

    const validFilters = filters
      .filter(f => f.field && f.op && f.value !== '')
      .map(f => `${f.field}:${f.op}:${f.value}`)

    try {
      const data = await api.statlabQuery(orgId, {
        mode,
        seasonId: mode === 'season' ? seasonId : undefined,
        groupBy,
        sortBy,
        sortDir,
        limit: 500,
        filters: validFilters,
      })
      setRows(data)
    } catch (e) {
      setError(e.message)
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [orgId, mode, seasonId, groupBy, sortBy, sortDir, filters])

  // ── Filter management ──
  const addFilter = () => {
    const firstField = statGroups[0]?.stats[0]?.key || 'matches'
    setFilters(prev => [...prev, { id: Date.now(), field: firstField, op: 'gte', value: '' }])
  }

  const updateFilter = (id, updates) => {
    setFilters(prev => prev.map(f => f.id === id ? { ...f, ...updates } : f))
  }

  const removeFilter = (id) => {
    setFilters(prev => prev.filter(f => f.id !== id))
  }

  const resetAll = () => {
    setFilters([])
    setMode('career')
    setSeasonId('')
    setGroupBy('player')
    setSortBy('runs')
    setSortDir('desc')
    setRows([])
    setHasQueried(false)
    setError(null)
  }

  // ── Group-by change resets incompatible filters ──
  const changeGroupBy = (g) => {
    setGroupBy(g)
    setRows([])
    setHasQueried(false)
    // Keep only filters whose field is valid for the new group
    const newGroups = g === 'player' ? PLAYER_STAT_GROUPS : GRADE_STAT_GROUPS
    const validKeys = new Set(getAllStats(newGroups).map(s => s.key))
    setFilters(prev => prev.filter(f => validKeys.has(f.field)))
    // Reset sort to a safe default
    setSortBy(g === 'player' ? 'runs' : 'runs')
  }

  // ── Client-side column sort of already-fetched rows ──
  const handleColumnSort = (col) => {
    const newDir = clientSort.col === col && clientSort.dir === 'desc' ? 'asc' : 'desc'
    setClientSort({ col, dir: newDir })
  }

  const sortedRows = (() => {
    if (!clientSort.col) return rows
    return [...rows].sort((a, b) => {
      const va = parseFloat(a[clientSort.col]) || 0
      const vb = parseFloat(b[clientSort.col]) || 0
      return clientSort.dir === 'asc' ? va - vb : vb - va
    })
  })()

  // ── Column definitions for results table ──
  const resultColumns = (() => {
    if (groupBy === 'player') {
      const filteredStatKeys = filters
        .filter(f => f.field && f.value !== '')
        .map(f => f.field)
      const allPlayerStats = getAllStats(PLAYER_STAT_GROUPS)
      // Always show matches; then filtered stats; then a few key defaults
      const shown = new Set()
      const cols = []
      const addCol = (key) => {
        if (shown.has(key)) return
        const meta = allPlayerStats.find(s => s.key === key)
        if (!meta) return
        shown.add(key)
        cols.push(meta)
      }
      addCol('matches')
      filteredStatKeys.forEach(addCol)
      // Fill with sensible defaults if few filtered columns
      if (cols.length < 5) {
        ['runs', 'batting_average', 'wickets', 'bowling_economy', 'catches'].forEach(addCol)
      }
      return cols
    }

    // Grade / Team mode
    const filteredKeys = filters.filter(f => f.value !== '').map(f => f.field)
    const allGradeStats = getAllStats(GRADE_STAT_GROUPS)
    const shown = new Set()
    const cols = []
    const addCol = (key) => {
      if (shown.has(key)) return
      const meta = allGradeStats.find(s => s.key === key)
      if (!meta) return
      shown.add(key)
      cols.push(meta)
    }
    addCol('matches')
    addCol('unique_players')
    filteredKeys.forEach(addCol)
    ['runs', 'wickets', 'catches'].forEach(addCol)
    return cols
  })()

  if (clubLoading) return (
    <div className="flex items-center justify-center h-64">
      <LoadingSpinner />
    </div>
  )
  if (inactive) return <ClubInactive />

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">

      {/* ── Header ── */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-accent/10 rounded-xl border border-accent/20">
              <svg className="w-6 h-6 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <div>
              <h1 className="text-2xl font-display font-bold text-white tracking-wide">StatLab</h1>
              <p className="text-slate-400 text-sm">Build complex queries across all club statistics</p>
            </div>
          </div>
        </div>

        {/* Mode toggle */}
        <div className="flex items-center gap-1 bg-navy-800 rounded-xl p-1 border border-navy-700">
          {['career', 'season'].map(m => (
            <button
              key={m}
              onClick={() => { setMode(m); setRows([]); setHasQueried(false) }}
              className={clsx(
                'px-4 py-1.5 rounded-lg text-sm font-medium transition-all',
                mode === m
                  ? 'bg-accent text-navy-950 shadow-sm'
                  : 'text-slate-400 hover:text-white'
              )}
            >
              {m === 'career' ? 'Career' : 'Season'}
            </button>
          ))}
        </div>
      </div>

      {/* Season picker — shown when mode=season */}
      {mode === 'season' && (
        <div className="flex items-center gap-3 bg-navy-900/60 border border-navy-700 rounded-xl px-4 py-3">
          <span className="text-slate-400 text-sm font-medium shrink-0">Filter to season:</span>
          <select
            value={seasonId}
            onChange={e => { setSeasonId(e.target.value); setRows([]); setHasQueried(false) }}
            className="bg-navy-800 border border-navy-600 text-slate-200 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 cursor-pointer flex-1 max-w-xs"
          >
            <option value="">All seasons</option>
            {seasons
              .slice()
              .sort((a, b) => (b.year || 0) - (a.year || 0))
              .map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
          </select>
        </div>
      )}

      {/* ── Group-by tabs ── */}
      <div className="flex items-center gap-1 border-b border-navy-700 pb-0">
        {GROUP_TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => changeGroupBy(tab.key)}
            className={clsx(
              'px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
              groupBy === tab.key
                ? 'border-accent text-accent'
                : 'border-transparent text-slate-400 hover:text-white hover:border-navy-500'
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Filter builder ── */}
      <div className="bg-navy-900/60 border border-navy-700 rounded-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-navy-700/60">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z" />
            </svg>
            <span className="text-white text-sm font-semibold">Filters</span>
            {filters.length > 0 && (
              <span className="bg-accent/20 text-accent text-xs font-bold px-2 py-0.5 rounded-full">
                {filters.length}
              </span>
            )}
          </div>
          {filters.length > 0 && (
            <button
              onClick={() => setFilters([])}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              Clear all
            </button>
          )}
        </div>

        <div className="p-5 space-y-3">
          {filters.length === 0 && (
            <p className="text-slate-500 text-sm py-2">
              No filters applied — add one below, or run without filters to see all {groupBy === 'player' ? 'players' : groupBy === 'team' ? 'teams' : 'grades'} ranked.
            </p>
          )}

          {filters.map(f => (
            <FilterRow
              key={f.id}
              filter={f}
              statGroups={statGroups}
              onUpdate={(updates) => updateFilter(f.id, updates)}
              onRemove={() => removeFilter(f.id)}
            />
          ))}

          <div className="flex items-center gap-3 pt-2 flex-wrap">
            <button
              onClick={addFilter}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-400 hover:text-white border border-dashed border-navy-600 hover:border-navy-400 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add filter
            </button>

            <div className="flex-1" />

            <button
              onClick={resetAll}
              className="px-4 py-2 text-sm text-slate-400 hover:text-white border border-navy-600 hover:border-navy-400 rounded-lg transition-colors"
            >
              Reset
            </button>

            <button
              onClick={runQuery}
              disabled={loading || !orgId}
              className={clsx(
                'flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold transition-all',
                loading
                  ? 'bg-accent/40 text-navy-950/60 cursor-not-allowed'
                  : 'bg-accent hover:bg-accent/90 text-navy-950 shadow-lg shadow-accent/20 hover:shadow-accent/30'
              )}
            >
              {loading
                ? <><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> Running…</>
                : <><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg> Run Query</>
              }
            </button>
          </div>
        </div>
      </div>

      {/* ── Quick-start examples (shown before first query) ── */}
      {!hasQueried && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[
            {
              label: 'All-rounders',
              desc: '500+ runs & 50+ wickets',
              filters: [
                { id: 1, field: 'runs',    op: 'gte', value: '500' },
                { id: 2, field: 'wickets', op: 'gte', value: '50'  },
              ],
              group: 'player', mode: 'career',
            },
            {
              label: 'Century makers',
              desc: 'Scored at least one 100',
              filters: [
                { id: 1, field: 'hundreds', op: 'gte', value: '1' },
              ],
              group: 'player', mode: 'career',
            },
            {
              label: 'Prolific bowlers',
              desc: '100+ wickets at avg < 20',
              filters: [
                { id: 1, field: 'wickets',         op: 'gte', value: '100' },
                { id: 2, field: 'bowling_average',  op: 'lte', value: '20'  },
              ],
              group: 'player', mode: 'career',
            },
            {
              label: 'Long-serving players',
              desc: '100+ matches played',
              filters: [
                { id: 1, field: 'matches', op: 'gte', value: '100' },
              ],
              group: 'player', mode: 'career',
            },
            {
              label: 'Elite strike rates',
              desc: 'SR ≥ 100, 20+ innings',
              filters: [
                { id: 1, field: 'batting_strike_rate', op: 'gte', value: '100' },
                { id: 2, field: 'batting_innings',      op: 'gte', value: '20'  },
              ],
              group: 'player', mode: 'career',
            },
            {
              label: 'Safe pairs of hands',
              desc: '30+ career catches',
              filters: [
                { id: 1, field: 'catches', op: 'gte', value: '30' },
              ],
              group: 'player', mode: 'career',
            },
          ].map((ex, i) => (
            <button
              key={i}
              onClick={() => {
                setFilters(ex.filters.map(f => ({ ...f, id: Date.now() + f.id })))
                setGroupBy(ex.group)
                setMode(ex.mode)
              }}
              className="text-left p-4 bg-navy-900/40 hover:bg-navy-800/60 border border-navy-700 hover:border-navy-500 rounded-xl transition-all group"
            >
              <div className="text-sm font-semibold text-slate-300 group-hover:text-white transition-colors">{ex.label}</div>
              <div className="text-xs text-slate-500 mt-0.5">{ex.desc}</div>
            </button>
          ))}
        </div>
      )}

      {/* ── Error ── */}
      {error && (
        <div className="bg-red-950/40 border border-red-800 text-red-300 px-4 py-3 rounded-xl text-sm">
          Query failed: {error}
        </div>
      )}

      {/* ── Results table ── */}
      {hasQueried && !loading && !error && (
        <div className="bg-navy-900/60 border border-navy-700 rounded-2xl overflow-hidden">
          {/* Table header */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-navy-700/60">
            <div className="flex items-center gap-2">
              <span className="text-white text-sm font-semibold">
                {sortedRows.length === 0 ? 'No results' :
                  sortedRows.length === 500
                    ? '500+ results (showing first 500)'
                    : `${sortedRows.length} ${groupBy === 'player' ? 'player' : groupBy === 'team' ? 'team/season' : 'grade'}${sortedRows.length !== 1 ? 's' : ''} found`
                }
              </span>
              {clientSort.col && (
                <span className="text-xs text-slate-500">
                  sorted by {findStatMeta(clientSort.col, statGroups)?.label || clientSort.col} {clientSort.dir}
                </span>
              )}
            </div>
            {sortedRows.length > 0 && (
              <span className="text-xs text-slate-500">Click column headers to sort</span>
            )}
          </div>

          {sortedRows.length === 0 ? (
            <div className="py-12 text-center text-slate-500 text-sm">
              No {groupBy === 'player' ? 'players' : groupBy === 'team' ? 'teams' : 'grades'} match your filters.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-navy-700/60">
                    <th className="text-left px-5 py-3 text-slate-400 font-medium whitespace-nowrap">
                      {groupBy === 'player' ? '#' : '#'}
                    </th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium whitespace-nowrap">
                      {groupBy === 'player' ? 'Player' : groupBy === 'team' ? 'Grade / Season' : 'Grade'}
                    </th>
                    {resultColumns.map(col => {
                      const sortActive = clientSort.col === col.key
                      const colors = GROUP_COLOR_CLASSES[col.color]
                      return (
                        <th
                          key={col.key}
                          onClick={() => handleColumnSort(col.key)}
                          className="text-right px-4 py-3 text-slate-400 font-medium whitespace-nowrap cursor-pointer hover:text-white select-none group"
                        >
                          <div className="flex items-center justify-end gap-1.5">
                            <span className={clsx(
                              'text-xs',
                              sortActive ? 'text-accent' : 'text-slate-400 group-hover:text-slate-200'
                            )}>
                              {col.label}
                            </span>
                            <SortIcon direction={sortActive ? clientSort.dir : null} />
                          </div>
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((row, idx) => (
                    <tr
                      key={idx}
                      className="border-b border-navy-800/60 hover:bg-navy-800/30 transition-colors group"
                    >
                      <td className="px-5 py-3 text-slate-500 text-xs tabular-nums">{idx + 1}</td>
                      <td className="px-4 py-3 font-medium whitespace-nowrap">
                        {groupBy === 'player' ? (
                          <Link
                            to={`/players/${row.player_id}`}
                            className="text-slate-200 hover:text-accent transition-colors group-hover:text-accent/90"
                          >
                            {row.player_name}
                          </Link>
                        ) : groupBy === 'team' ? (
                          <span className="text-slate-200">
                            {row.grade_name}
                            <span className="text-slate-500 text-xs ml-1.5">{row.season_name}</span>
                          </span>
                        ) : (
                          <span className="text-slate-200">{row.grade_name}</span>
                        )}
                      </td>
                      {resultColumns.map(col => {
                        const v = row[col.key]
                        const sortActive = clientSort.col === col.key
                        return (
                          <td
                            key={col.key}
                            className={clsx(
                              'px-4 py-3 text-right tabular-nums whitespace-nowrap',
                              sortActive ? 'text-accent font-semibold' : 'text-slate-300'
                            )}
                          >
                            {fmt(v, col.decimal)}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
