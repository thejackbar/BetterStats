import { useParams, useSearchParams, Link } from 'react-router-dom'
import { useState, useEffect, useCallback } from 'react'
import { useClub } from '../hooks/useClub'
import { useClubData } from '../hooks/useClubData'
import { api } from '../lib/api'
import clsx from 'clsx'
import ClubInactive from './ClubInactive'
import LoadingSpinner from '../components/LoadingSpinner'

// ─── Stat definitions ─────────────────────────────────────────────────────────

const PLAYER_STAT_GROUPS = [
  {
    key: 'participation', label: 'Participation', color: 'purple',
    stats: [
      { key: 'matches',        label: 'Matches',    decimal: false },
      { key: 'seasons_played', label: 'Seasons',    decimal: false },
    ],
  },
  {
    key: 'batting', label: 'Batting', color: 'emerald',
    stats: [
      { key: 'batting_innings',     label: 'Innings',     decimal: false },
      { key: 'runs',                label: 'Runs',        decimal: false },
      { key: 'not_outs',            label: 'Not Outs',    decimal: false },
      { key: 'batting_average',     label: 'Average',     decimal: true  },
      { key: 'batting_strike_rate', label: 'Strike Rate', decimal: true  },
      { key: 'high_score',          label: 'High Score',  decimal: false },
      { key: 'fifties',             label: '50s',         decimal: false },
      { key: 'hundreds',            label: '100s',        decimal: false },
      { key: 'ducks',               label: 'Ducks',       decimal: false },
      { key: 'fours',               label: '4s',          decimal: false },
      { key: 'sixes',               label: '6s',          decimal: false },
    ],
  },
  {
    key: 'bowling', label: 'Bowling', color: 'orange',
    stats: [
      { key: 'wickets',             label: 'Wickets',     decimal: false },
      { key: 'overs',               label: 'Overs',       decimal: true  },
      { key: 'bowling_average',     label: 'Avg',         decimal: true  },
      { key: 'bowling_economy',     label: 'Economy',     decimal: true  },
      { key: 'five_wicket_innings', label: '5-fors',      decimal: false },
      { key: 'maidens',             label: 'Maidens',     decimal: false },
      { key: 'best_bowling_wickets',label: 'Best (Wkts)', decimal: false },
    ],
  },
  {
    key: 'fielding', label: 'Fielding', color: 'sky',
    stats: [
      { key: 'catches',   label: 'Catches',   decimal: false },
      { key: 'run_outs',  label: 'Run Outs',  decimal: false },
      { key: 'stumpings', label: 'Stumpings', decimal: false },
    ],
  },
]

const GRADE_STAT_GROUPS = [
  {
    key: 'general', label: 'General', color: 'purple',
    stats: [
      { key: 'matches',        label: 'Matches',      decimal: false },
      { key: 'unique_players', label: 'Players Used', decimal: false },
    ],
  },
  {
    key: 'batting', label: 'Batting', color: 'emerald',
    stats: [
      { key: 'runs',     label: 'Total Runs', decimal: false },
      { key: 'hundreds', label: '100s',       decimal: false },
      { key: 'fifties',  label: '50s',        decimal: false },
      { key: 'ducks',    label: 'Ducks',      decimal: false },
    ],
  },
  {
    key: 'bowling', label: 'Bowling', color: 'orange',
    stats: [
      { key: 'wickets', label: 'Wickets', decimal: false },
    ],
  },
  {
    key: 'fielding', label: 'Fielding', color: 'sky',
    stats: [
      { key: 'catches',   label: 'Catches',   decimal: false },
      { key: 'run_outs',  label: 'Run Outs',  decimal: false },
      { key: 'stumpings', label: 'Stumpings', decimal: false },
    ],
  },
]

const OPERATORS = [
  { key: 'gte', label: '≥', title: 'At least' },
  { key: 'gt',  label: '>',  title: 'More than' },
  { key: 'eq',  label: '=',  title: 'Exactly' },
  { key: 'lte', label: '≤', title: 'At most' },
  { key: 'lt',  label: '<',  title: 'Less than' },
  { key: 'ne',  label: '≠', title: 'Not equal to' },
]

const GROUP_TABS = [
  { key: 'player', label: 'Players' },
  { key: 'team',   label: 'Team / Season' },
  { key: 'grade',  label: 'Grade' },
]

const COLOR_CLASSES = {
  purple:  { pill: 'bg-purple-900/60 text-purple-300 border border-purple-700', dot: 'bg-purple-400', badge: 'bg-purple-900/40 text-purple-400 border-purple-700/50' },
  emerald: { pill: 'bg-emerald-900/60 text-emerald-300 border border-emerald-700', dot: 'bg-emerald-400', badge: 'bg-emerald-900/40 text-emerald-400 border-emerald-700/50' },
  orange:  { pill: 'bg-orange-900/60 text-orange-300 border border-orange-700',   dot: 'bg-orange-400', badge: 'bg-orange-900/40 text-orange-400 border-orange-700/50' },
  sky:     { pill: 'bg-sky-900/60 text-sky-300 border border-sky-700',            dot: 'bg-sky-400', badge: 'bg-sky-900/40 text-sky-400 border-sky-700/50' },
}

// ─── Preset reports ────────────────────────────────────────────────────────────

const PRESETS = {
  popular: {
    label: 'Popular',
    presets: [
      { label: 'Run Scorers',        desc: 'All-time career runs',               group: 'player', mode: 'career', filters: [], sortBy: 'runs',             sortDir: 'desc' },
      { label: 'Wicket Takers',      desc: 'All-time career wickets',            group: 'player', mode: 'career', filters: [], sortBy: 'wickets',          sortDir: 'desc' },
      { label: 'Batting Averages',   desc: 'Min 20 innings',                     group: 'player', mode: 'career', filters: [{ field:'batting_innings', op:'gte', value:'20' }], sortBy: 'batting_average', sortDir: 'desc' },
      { label: 'Bowling Averages',   desc: 'Min 20 wickets',                     group: 'player', mode: 'career', filters: [{ field:'wickets', op:'gte', value:'20' }], sortBy: 'bowling_average', sortDir: 'asc' },
      { label: 'All-rounders',       desc: '500+ runs and 50+ wickets',          group: 'player', mode: 'career', filters: [{ field:'runs', op:'gte', value:'500' }, { field:'wickets', op:'gte', value:'50' }], sortBy: 'runs', sortDir: 'desc' },
      { label: 'Most Experienced',   desc: 'Most career matches played',         group: 'player', mode: 'career', filters: [], sortBy: 'matches', sortDir: 'desc' },
    ],
  },
  batting: {
    label: 'Batting',
    presets: [
      { label: 'Career Run Scorers',      desc: 'Sorted by total runs',                group: 'player', mode: 'career', filters: [], sortBy: 'runs',                sortDir: 'desc' },
      { label: 'Best Batting Average',    desc: 'Min 20 innings',                      group: 'player', mode: 'career', filters: [{ field:'batting_innings', op:'gte', value:'20' }], sortBy: 'batting_average', sortDir: 'desc' },
      { label: 'Best Strike Rate',        desc: 'Min 10 innings (requires ball-by-ball data)', group: 'player', mode: 'career', filters: [{ field:'batting_innings', op:'gte', value:'10' }], sortBy: 'batting_strike_rate', sortDir: 'desc' },
      { label: 'High Score Records',      desc: 'Highest individual innings',          group: 'player', mode: 'career', filters: [], sortBy: 'high_score', sortDir: 'desc' },
      { label: 'Century Makers',          desc: 'Players who have scored a 100',       group: 'player', mode: 'career', filters: [{ field:'hundreds', op:'gte', value:'1' }], sortBy: 'hundreds', sortDir: 'desc' },
      { label: 'Most Centuries',          desc: 'All-time 100s',                       group: 'player', mode: 'career', filters: [], sortBy: 'hundreds', sortDir: 'desc' },
      { label: 'Most Half-Centuries',     desc: 'All-time 50s',                        group: 'player', mode: 'career', filters: [], sortBy: 'fifties', sortDir: 'desc' },
      { label: '3+ Centuries Club',       desc: 'Players with 3 or more centuries',    group: 'player', mode: 'career', filters: [{ field:'hundreds', op:'gte', value:'3' }], sortBy: 'hundreds', sortDir: 'desc' },
      { label: 'Duck Brigade',            desc: 'Most career ducks',                   group: 'player', mode: 'career', filters: [], sortBy: 'ducks', sortDir: 'desc' },
      { label: 'Power Hitters',           desc: 'Most career sixes',                   group: 'player', mode: 'career', filters: [], sortBy: 'sixes', sortDir: 'desc' },
      { label: 'Boundary Hunters',        desc: 'Most career fours',                   group: 'player', mode: 'career', filters: [], sortBy: 'fours', sortDir: 'desc' },
      { label: 'Season Run Scorers',      desc: 'Most runs in a single season',        group: 'player', mode: 'season', filters: [], sortBy: 'runs', sortDir: 'desc' },
      { label: 'Season Batting Avg',      desc: 'Best avg in a single season (10+ inn)',group: 'player', mode: 'season', filters: [{ field:'batting_innings', op:'gte', value:'10' }], sortBy: 'batting_average', sortDir: 'desc' },
    ],
  },
  bowling: {
    label: 'Bowling',
    presets: [
      { label: 'Career Wicket Takers',    desc: 'Sorted by total wickets',             group: 'player', mode: 'career', filters: [], sortBy: 'wickets',            sortDir: 'desc' },
      { label: 'Best Bowling Average',    desc: 'Min 20 wickets',                      group: 'player', mode: 'career', filters: [{ field:'wickets', op:'gte', value:'20' }], sortBy: 'bowling_average', sortDir: 'asc' },
      { label: 'Best Economy Rate',       desc: 'Min 20 wickets',                      group: 'player', mode: 'career', filters: [{ field:'wickets', op:'gte', value:'20' }], sortBy: 'bowling_economy', sortDir: 'asc' },
      { label: 'Five-for Club',           desc: 'Players with 5-wicket hauls',         group: 'player', mode: 'career', filters: [{ field:'five_wicket_innings', op:'gte', value:'1' }], sortBy: 'five_wicket_innings', sortDir: 'desc' },
      { label: 'Most 5-Wicket Hauls',     desc: 'All-time 5-fors',                     group: 'player', mode: 'career', filters: [], sortBy: 'five_wicket_innings', sortDir: 'desc' },
      { label: 'Most Maidens',            desc: 'Career maiden overs',                 group: 'player', mode: 'career', filters: [], sortBy: 'maidens',            sortDir: 'desc' },
      { label: '100+ Wicket Club',        desc: 'Players with 100+ career wickets',    group: 'player', mode: 'career', filters: [{ field:'wickets', op:'gte', value:'100' }], sortBy: 'wickets', sortDir: 'desc' },
      { label: 'Prolific + Accurate',     desc: '50+ wkts, avg < 25',                  group: 'player', mode: 'career', filters: [{ field:'wickets', op:'gte', value:'50' }, { field:'bowling_average', op:'lte', value:'25' }], sortBy: 'bowling_average', sortDir: 'asc' },
      { label: 'Season Wicket Takers',    desc: 'Most wickets in a single season',     group: 'player', mode: 'season', filters: [], sortBy: 'wickets',            sortDir: 'desc' },
      { label: 'Season Bowling Avg',      desc: 'Best avg in a season (10+ wkts)',     group: 'player', mode: 'season', filters: [{ field:'wickets', op:'gte', value:'10' }], sortBy: 'bowling_average', sortDir: 'asc' },
    ],
  },
  fielding: {
    label: 'Fielding',
    presets: [
      { label: 'Top Fielders',            desc: 'Most career catches',                 group: 'player', mode: 'career', filters: [], sortBy: 'catches',   sortDir: 'desc' },
      { label: 'Run-Out Specialists',     desc: 'Most career run outs effected',       group: 'player', mode: 'career', filters: [], sortBy: 'run_outs',  sortDir: 'desc' },
      { label: '20+ Catch Club',          desc: 'Players with 20+ career catches',     group: 'player', mode: 'career', filters: [{ field:'catches', op:'gte', value:'20' }], sortBy: 'catches', sortDir: 'desc' },
      { label: 'Safe Pair of Hands',      desc: '30+ catches or 5+ run outs',          group: 'player', mode: 'career', filters: [{ field:'catches', op:'gte', value:'30' }], sortBy: 'catches', sortDir: 'desc' },
    ],
  },
  allround: {
    label: 'All-rounders',
    presets: [
      { label: 'True All-rounders',       desc: '500+ runs AND 50+ wickets',           group: 'player', mode: 'career', filters: [{ field:'runs', op:'gte', value:'500' }, { field:'wickets', op:'gte', value:'50' }], sortBy: 'runs', sortDir: 'desc' },
      { label: 'Elite All-rounders',      desc: '1000+ runs AND 50+ wickets',          group: 'player', mode: 'career', filters: [{ field:'runs', op:'gte', value:'1000' }, { field:'wickets', op:'gte', value:'50' }], sortBy: 'runs', sortDir: 'desc' },
      { label: 'Club Stalwarts',          desc: '100+ matches played',                 group: 'player', mode: 'career', filters: [{ field:'matches', op:'gte', value:'100' }], sortBy: 'matches', sortDir: 'desc' },
      { label: 'Century & Wickets',       desc: 'Scored a century AND 10+ wickets',    group: 'player', mode: 'career', filters: [{ field:'hundreds', op:'gte', value:'1' }, { field:'wickets', op:'gte', value:'10' }], sortBy: 'runs', sortDir: 'desc' },
      { label: '10-Season Veterans',      desc: 'Players with 10+ seasons',            group: 'player', mode: 'career', filters: [{ field:'seasons_played', op:'gte', value:'10' }], sortBy: 'seasons_played', sortDir: 'desc' },
      { label: 'Big Hitters Who Bowl',    desc: '20+ wickets and highest run scorers', group: 'player', mode: 'career', filters: [{ field:'wickets', op:'gte', value:'20' }], sortBy: 'runs', sortDir: 'desc' },
    ],
  },
  grade: {
    label: 'Grade / Team',
    presets: [
      { label: 'Highest Scoring Grades',  desc: 'Most runs across all seasons',        group: 'grade', mode: 'career', filters: [], sortBy: 'runs',    sortDir: 'desc' },
      { label: 'Most Wicket-Rich Grades', desc: 'Most wickets taken across all seasons',group: 'grade', mode: 'career', filters: [], sortBy: 'wickets', sortDir: 'desc' },
      { label: 'Busiest Grades',          desc: 'Most matches played in this grade',   group: 'grade', mode: 'career', filters: [], sortBy: 'matches', sortDir: 'desc' },
      { label: 'Season Team Runs',        desc: 'Highest-scoring teams in a season',   group: 'team',  mode: 'career', filters: [], sortBy: 'runs',    sortDir: 'desc' },
      { label: 'Season Team Wickets',     desc: 'Most wickets taken by a team in a season', group: 'team', mode: 'career', filters: [], sortBy: 'wickets', sortDir: 'desc' },
      { label: 'Century-Rich Seasons',    desc: 'Grade/seasons with the most centuries',   group: 'team', mode: 'career', filters: [], sortBy: 'hundreds', sortDir: 'desc' },
    ],
  },
}

const PRESET_TABS = [
  { key: 'popular',  label: 'Popular' },
  { key: 'batting',  label: 'Batting' },
  { key: 'bowling',  label: 'Bowling' },
  { key: 'fielding', label: 'Fielding' },
  { key: 'allround', label: 'All-rounders' },
  { key: 'grade',    label: 'Grade / Team' },
]

// ─── URL helpers ───────────────────────────────────────────────────────────────

function encodeFilters(filters) {
  return filters
    .filter(f => f.field && f.op && f.value !== '')
    .map(f => `${f.field}:${f.op}:${f.value}`)
    .join(',')
}

function decodeFilters(str) {
  if (!str) return []
  return str.split(',').flatMap((f, i) => {
    const p = f.split(':')
    return p.length === 3 ? [{ id: Date.now() + i, field: p[0], op: p[1], value: p[2] }] : []
  })
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function getAllStats(groups) {
  return groups.flatMap(g => g.stats.map(s => ({ ...s, group: g.key, color: g.color, groupLabel: g.label })))
}

function findStatMeta(key, groups) {
  for (const g of groups) {
    const s = g.stats.find(s => s.key === key)
    if (s) return { ...s, group: g.key, color: g.color, groupLabel: g.label }
  }
  return null
}

function fmt(v, decimal) {
  if (v === null || v === undefined) return '—'
  const n = parseFloat(v)
  if (isNaN(n)) return String(v)
  return decimal ? n.toFixed(2) : n.toLocaleString()
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function FilterRow({ filter, statGroups, onUpdate, onRemove }) {
  const meta = findStatMeta(filter.field, statGroups)
  const color = meta?.color || 'purple'
  const colors = COLOR_CLASSES[color]

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <select
        value={filter.field}
        onChange={e => onUpdate({ field: e.target.value })}
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

      <select
        value={filter.op}
        onChange={e => onUpdate({ op: e.target.value })}
        className="bg-navy-800 border border-navy-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 cursor-pointer w-16 text-center"
      >
        {OPERATORS.map(op => (
          <option key={op.key} value={op.key} title={op.title}>{op.label}</option>
        ))}
      </select>

      <input
        type="number"
        value={filter.value}
        onChange={e => onUpdate({ value: e.target.value })}
        placeholder="0"
        className="bg-navy-800 border border-navy-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 w-24"
        min="0"
        step="any"
      />

      {meta && (
        <span className={clsx('hidden sm:inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium', colors.pill)}>
          <span className={clsx('w-1.5 h-1.5 rounded-full', colors.dot)} />
          {meta.groupLabel}
        </span>
      )}

      <button
        onClick={onRemove}
        className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-950/40 rounded-md transition-colors"
        title="Remove"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  )
}

function SortIcon({ dir }) {
  if (!dir) return (
    <svg className="w-3 h-3 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" />
    </svg>
  )
  return dir === 'desc'
    ? <svg className="w-3 h-3 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
    : <svg className="w-3 h-3 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" /></svg>
}

// ─── Main page ─────────────────────────────────────────────────────────────────

export default function StatLab() {
  const { clubSlug } = useParams()
  const { club, orgId, loading: clubLoading, inactive } = useClub(clubSlug)
  const { seasons } = useClubData(orgId)
  const [searchParams, setSearchParams] = useSearchParams()

  const [mode,     setMode]     = useState(searchParams.get('mode')   || 'career')
  const [seasonId, setSeasonId] = useState(searchParams.get('sid')    || '')
  const [groupBy,  setGroupBy]  = useState(searchParams.get('group')  || 'player')
  const [sortBy,   setSortBy]   = useState(searchParams.get('sort')   || 'runs')
  const [sortDir,  setSortDir]  = useState(searchParams.get('dir')    || 'desc')
  const [filters,  setFilters]  = useState(() => decodeFilters(searchParams.get('f') || ''))

  const [rows,        setRows]        = useState([])
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState(null)
  const [hasQueried,  setHasQueried]  = useState(false)
  const [clientSort,  setClientSort]  = useState({ col: null, dir: null })

  const [presetTab,   setPresetTab]   = useState('popular')
  const [galleryOpen, setGalleryOpen] = useState(true)

  const statGroups = groupBy === 'player' ? PLAYER_STAT_GROUPS : GRADE_STAT_GROUPS

  useEffect(() => {
    const p = {}
    if (mode    !== 'career')  p.mode  = mode
    if (groupBy !== 'player')  p.group = groupBy
    if (sortBy  !== 'runs')    p.sort  = sortBy
    if (sortDir !== 'desc')    p.dir   = sortDir
    if (mode === 'season' && seasonId) p.sid = seasonId
    const encoded = encodeFilters(filters)
    if (encoded) p.f = encoded
    setSearchParams(p, { replace: true })
  }, [mode, seasonId, groupBy, sortBy, sortDir, filters])

  useEffect(() => { setClientSort({ col: null, dir: null }) }, [rows])

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

  const addFilter = () => {
    const firstField = statGroups[0]?.stats[0]?.key || 'matches'
    setFilters(prev => [...prev, { id: Date.now(), field: firstField, op: 'gte', value: '' }])
  }
  const updateFilter = (id, patch) => setFilters(prev => prev.map(f => f.id === id ? { ...f, ...patch } : f))
  const removeFilter = (id) => setFilters(prev => prev.filter(f => f.id !== id))

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

  const changeGroupBy = (g) => {
    setGroupBy(g)
    setRows([])
    setHasQueried(false)
    const newGroups = g === 'player' ? PLAYER_STAT_GROUPS : GRADE_STAT_GROUPS
    const validKeys = new Set(getAllStats(newGroups).map(s => s.key))
    setFilters(prev => prev.filter(f => validKeys.has(f.field)))
    setSortBy('runs')
  }

  // Apply a preset and immediately run the query with the new values
  const applyPreset = useCallback(async (preset) => {
    if (!orgId) return
    const newGroup   = preset.group    || 'player'
    const newMode    = preset.mode     || 'career'
    const newSortBy  = preset.sortBy   || 'runs'
    const newSortDir = preset.sortDir  || 'desc'
    const newFilters = preset.filters.map((f, i) => ({ ...f, id: Date.now() + i }))

    setGroupBy(newGroup)
    setMode(newMode)
    setSortBy(newSortBy)
    setSortDir(newSortDir)
    setFilters(newFilters)
    setGalleryOpen(false)
    setClientSort({ col: null, dir: null })
    setLoading(true)
    setError(null)
    setHasQueried(true)
    setRows([])

    const validFilters = newFilters
      .filter(f => f.field && f.op && f.value !== '')
      .map(f => `${f.field}:${f.op}:${f.value}`)
    try {
      const data = await api.statlabQuery(orgId, {
        mode: newMode,
        seasonId: newMode === 'season' ? seasonId : undefined,
        groupBy: newGroup,
        sortBy: newSortBy,
        sortDir: newSortDir,
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
  }, [orgId, seasonId])

  const handleColSort = (col) => {
    const newDir = clientSort.col === col && clientSort.dir === 'desc' ? 'asc' : 'desc'
    setClientSort({ col, dir: newDir })
  }

  const sortedRows = clientSort.col
    ? [...rows].sort((a, b) => {
        const va = parseFloat(a[clientSort.col]) || 0
        const vb = parseFloat(b[clientSort.col]) || 0
        return clientSort.dir === 'asc' ? va - vb : vb - va
      })
    : rows

  const resultColumns = (() => {
    if (groupBy === 'player') {
      const filteredKeys = filters.filter(f => f.value !== '').map(f => f.field)
      const allStats = getAllStats(PLAYER_STAT_GROUPS)
      const shown = new Set()
      const cols = []
      const add = (key) => {
        if (shown.has(key)) return
        const meta = allStats.find(s => s.key === key)
        if (!meta) return
        shown.add(key)
        cols.push(meta)
      }
      add('matches')
      filteredKeys.forEach(add)
      if (cols.length < 5) ['runs', 'batting_average', 'wickets', 'bowling_economy', 'catches'].forEach(add)
      return cols
    }
    const filteredKeys = filters.filter(f => f.value !== '').map(f => f.field)
    const allStats = getAllStats(GRADE_STAT_GROUPS)
    const shown = new Set()
    const cols = []
    const add = (key) => {
      if (shown.has(key)) return
      const meta = allStats.find(s => s.key === key)
      if (!meta) return
      shown.add(key)
      cols.push(meta)
    }
    add('matches')
    add('unique_players')
    filteredKeys.forEach(add)
    ;['runs', 'wickets', 'catches'].forEach(add)
    return cols
  })()

  if (clubLoading) return <div className="flex items-center justify-center h-64"><LoadingSpinner /></div>
  if (inactive) return <ClubInactive />

  const entityLabel = groupBy === 'player' ? 'players' : groupBy === 'team' ? 'teams' : 'grades'

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-5">

      <div className="flex items-start justify-between flex-wrap gap-4">
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

        <div className="flex items-center gap-1 bg-navy-800 rounded-xl p-1 border border-navy-700">
          {['career', 'season'].map(m => (
            <button key={m}
              onClick={() => { setMode(m); setRows([]); setHasQueried(false) }}
              className={clsx('px-4 py-1.5 rounded-lg text-sm font-medium transition-all',
                mode === m ? 'bg-accent text-navy-950 shadow-sm' : 'text-slate-400 hover:text-white'
              )}
            >
              {m === 'career' ? 'Career' : 'Season'}
            </button>
          ))}
        </div>
      </div>

      {mode === 'season' && (
        <div className="flex items-center gap-3 bg-navy-900/60 border border-navy-700 rounded-xl px-4 py-3">
          <span className="text-slate-400 text-sm font-medium shrink-0">Season:</span>
          <select value={seasonId}
            onChange={e => { setSeasonId(e.target.value); setRows([]); setHasQueried(false) }}
            className="bg-navy-800 border border-navy-600 text-slate-200 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 cursor-pointer flex-1 max-w-xs"
          >
            <option value="">All seasons</option>
            {[...seasons].sort((a, b) => (b.year || 0) - (a.year || 0)).map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-navy-700">
        {GROUP_TABS.map(tab => (
          <button key={tab.key} onClick={() => changeGroupBy(tab.key)}
            className={clsx('px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
              groupBy === tab.key
                ? 'border-accent text-accent'
                : 'border-transparent text-slate-400 hover:text-white hover:border-navy-500'
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Preset Report Gallery ── */}
      <div className="bg-navy-900/60 border border-navy-700 rounded-2xl overflow-hidden">
        <button
          onClick={() => setGalleryOpen(o => !o)}
          className="w-full flex items-center justify-between px-5 py-3 border-b border-navy-700/60 hover:bg-navy-800/40 transition-colors"
        >
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <span className="text-white text-sm font-semibold">Report Gallery</span>
            <span className="text-slate-500 text-xs">— click a report to run it instantly</span>
          </div>
          <svg className={clsx('w-4 h-4 text-slate-400 transition-transform', galleryOpen && 'rotate-180')} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {galleryOpen && (
          <div>
            <div className="flex gap-0 border-b border-navy-700/60 overflow-x-auto">
              {PRESET_TABS.map(t => (
                <button key={t.key} onClick={() => setPresetTab(t.key)}
                  className={clsx('px-4 py-2 text-xs font-semibold uppercase tracking-wider whitespace-nowrap transition-colors border-b-2 -mb-px',
                    presetTab === t.key
                      ? 'text-accent border-accent'
                      : 'text-slate-500 border-transparent hover:text-slate-300'
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              {(PRESETS[presetTab]?.presets || []).map((preset, i) => {
                const targetGroup = preset.group || 'player'
                const badgeColor = targetGroup === 'player' ? 'emerald'
                  : targetGroup === 'team' ? 'orange' : 'purple'
                const badgeClasses = COLOR_CLASSES[badgeColor]
                return (
                  <button key={i} onClick={() => applyPreset(preset)}
                    className="text-left p-3.5 bg-navy-800/50 hover:bg-navy-700/60 border border-navy-700 hover:border-navy-500 rounded-xl transition-all group"
                  >
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <span className="text-sm font-semibold text-slate-300 group-hover:text-white transition-colors leading-tight">
                        {preset.label}
                      </span>
                      <div className="flex gap-1 shrink-0">
                        <span className={clsx('px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase border', badgeClasses.badge)}>
                          {targetGroup}
                        </span>
                        {preset.mode === 'season' && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase border bg-slate-800/60 text-slate-400 border-slate-700/50">
                            season
                          </span>
                        )}
                      </div>
                    </div>
                    <p className="text-xs text-slate-500 group-hover:text-slate-400 transition-colors">{preset.desc}</p>
                    {preset.filters.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {preset.filters.map((f, fi) => {
                          const op = OPERATORS.find(o => o.key === f.op)
                          return (
                            <span key={fi} className="text-[10px] px-1.5 py-0.5 bg-navy-900 border border-navy-600 rounded text-slate-400 font-mono">
                              {f.field.replace(/_/g, ' ')} {op?.label} {f.value}
                            </span>
                          )
                        })}
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* ── Filter builder ── */}
      <div className="bg-navy-900/60 border border-navy-700 rounded-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-navy-700/60">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z" />
            </svg>
            <span className="text-white text-sm font-semibold">Custom Filters</span>
            {filters.length > 0 && (
              <span className="bg-accent/20 text-accent text-xs font-bold px-2 py-0.5 rounded-full">{filters.length}</span>
            )}
          </div>
          {filters.length > 0 && (
            <button onClick={() => setFilters([])} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
              Clear all
            </button>
          )}
        </div>

        <div className="p-5 space-y-3">
          {filters.length === 0 && (
            <p className="text-slate-500 text-sm py-1">
              No filters — pick a preset above, add one below, or run as-is to see all {entityLabel} ranked.
            </p>
          )}

          {filters.map(f => (
            <FilterRow key={f.id} filter={f} statGroups={statGroups}
              onUpdate={(patch) => updateFilter(f.id, patch)}
              onRemove={() => removeFilter(f.id)}
            />
          ))}

          <div className="flex items-center gap-3 pt-2 flex-wrap">
            <button onClick={addFilter}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-400 hover:text-white border border-dashed border-navy-600 hover:border-navy-400 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
              Add filter
            </button>
            <div className="flex-1" />
            <button onClick={resetAll}
              className="px-4 py-2 text-sm text-slate-400 hover:text-white border border-navy-600 hover:border-navy-400 rounded-lg transition-colors"
            >
              Reset
            </button>
            <button onClick={runQuery} disabled={loading || !orgId}
              className={clsx('flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold transition-all',
                loading || !orgId
                  ? 'bg-accent/40 text-navy-950/60 cursor-not-allowed'
                  : 'bg-accent hover:bg-accent/90 text-navy-950 shadow-lg shadow-accent/20'
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

      {error && (
        <div className="bg-red-950/40 border border-red-800 text-red-300 px-4 py-3 rounded-xl text-sm">
          Query failed: {error}
        </div>
      )}

      {hasQueried && !loading && !error && (
        <div className="bg-navy-900/60 border border-navy-700 rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-navy-700/60">
            <span className="text-white text-sm font-semibold">
              {sortedRows.length === 0
                ? 'No results matched your filters'
                : sortedRows.length >= 500
                  ? '500+ results (capped at 500)'
                  : `${sortedRows.length} ${entityLabel.slice(0, -1)}${sortedRows.length !== 1 ? (entityLabel.endsWith('s') ? 's' : '') : ''} found`}
            </span>
            {sortedRows.length > 0 && (
              <span className="text-xs text-slate-500 hidden sm:block">Click column headers to sort</span>
            )}
          </div>

          {sortedRows.length === 0 ? (
            <p className="py-12 text-center text-slate-500 text-sm">
              Try removing a filter or lowering the threshold.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-navy-700/60">
                    <th className="text-left px-5 py-3 text-slate-400 font-medium w-8">#</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium">
                      {groupBy === 'player' ? 'Player' : groupBy === 'team' ? 'Grade / Season' : 'Grade'}
                    </th>
                    {resultColumns.map(col => {
                      const active = clientSort.col === col.key
                      return (
                        <th key={col.key} onClick={() => handleColSort(col.key)}
                          className="text-right px-4 py-3 font-medium whitespace-nowrap cursor-pointer select-none group"
                        >
                          <div className="flex items-center justify-end gap-1">
                            <span className={clsx('text-xs', active ? 'text-accent' : 'text-slate-400 group-hover:text-slate-200')}>
                              {col.label}
                            </span>
                            <SortIcon dir={active ? clientSort.dir : null} />
                          </div>
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((row, idx) => (
                    <tr key={idx} className="border-b border-navy-800/60 hover:bg-navy-800/30 transition-colors group">
                      <td className="px-5 py-3 text-slate-600 text-xs tabular-nums">{idx + 1}</td>
                      <td className="px-4 py-3 font-medium whitespace-nowrap">
                        {groupBy === 'player' ? (
                          <Link to={`/players/${row.player_id}`}
                            className="text-slate-200 hover:text-accent transition-colors">
                            {row.player_name}
                          </Link>
                        ) : groupBy === 'team' ? (
                          <span className="text-slate-200">
                            {row.grade_name}
                            <span className="text-slate-500 text-xs ml-2">{row.season_name}</span>
                          </span>
                        ) : (
                          <span className="text-slate-200">{row.grade_name}</span>
                        )}
                      </td>
                      {resultColumns.map(col => (
                        <td key={col.key}
                          className={clsx('px-4 py-3 text-right tabular-nums whitespace-nowrap',
                            clientSort.col === col.key ? 'text-accent font-semibold' : 'text-slate-300'
                          )}>
                          {fmt(row[col.key], col.decimal)}
                        </td>
                      ))}
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
