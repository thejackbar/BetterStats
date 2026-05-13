import { useParams, useSearchParams } from 'react-router-dom'
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useClub } from '../hooks/useClub'
import { useClubData } from '../hooks/useClubData'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import { AnimatedNum, Label, Card, Btn, PageHeader, PbSpinner } from '../lib/presskit'
import { Link } from 'react-router-dom'

// ─── Stat definitions ──────────────────────────────────────────────────────────

const PLAYER_STAT_GROUPS = [
  { key: 'participation', label: 'Participation', stats: [
    { key: 'matches',            label: 'Matches',      decimal: false },
    { key: 'seasons_played',     label: 'Seasons',      decimal: false },
  ]},
  { key: 'batting', label: 'Batting', stats: [
    { key: 'batting_innings',    label: 'Innings',      decimal: false },
    { key: 'runs',               label: 'Runs',         decimal: false },
    { key: 'not_outs',           label: 'Not Outs',     decimal: false },
    { key: 'batting_average',    label: 'Average',      decimal: true  },
    { key: 'batting_strike_rate',label: 'Strike Rate',  decimal: true  },
    { key: 'high_score',         label: 'High Score',   decimal: false },
    { key: 'fifties',            label: '50s',          decimal: false },
    { key: 'hundreds',           label: '100s',         decimal: false },
    { key: 'ducks',              label: 'Ducks',        decimal: false },
    { key: 'fours',              label: '4s',           decimal: false },
    { key: 'sixes',              label: '6s',           decimal: false },
  ]},
  { key: 'bowling', label: 'Bowling', stats: [
    { key: 'wickets',            label: 'Wickets',      decimal: false },
    { key: 'overs',              label: 'Overs',        decimal: true  },
    { key: 'bowling_average',    label: 'Bowl Avg',     decimal: true  },
    { key: 'bowling_economy',    label: 'Economy',      decimal: true  },
    { key: 'five_wicket_innings',label: '5-fors',       decimal: false },
    { key: 'maidens',            label: 'Maidens',      decimal: false },
    { key: 'best_bowling_wickets',label: 'Best (Wkts)', decimal: false },
  ]},
  { key: 'fielding', label: 'Fielding', stats: [
    { key: 'catches',   label: 'Catches',   decimal: false },
    { key: 'run_outs',  label: 'Run Outs',  decimal: false },
    { key: 'stumpings', label: 'Stumpings', decimal: false },
  ]},
]

const GRADE_STAT_GROUPS = [
  { key: 'general', label: 'General', stats: [
    { key: 'matches',        label: 'Matches',      decimal: false },
    { key: 'unique_players', label: 'Players Used', decimal: false },
  ]},
  { key: 'batting', label: 'Batting', stats: [
    { key: 'runs',    label: 'Total Runs', decimal: false },
    { key: 'hundreds',label: '100s',       decimal: false },
    { key: 'fifties', label: '50s',        decimal: false },
    { key: 'ducks',   label: 'Ducks',      decimal: false },
  ]},
  { key: 'bowling', label: 'Bowling', stats: [
    { key: 'wickets', label: 'Wickets', decimal: false },
  ]},
  { key: 'fielding', label: 'Fielding', stats: [
    { key: 'catches',   label: 'Catches',   decimal: false },
    { key: 'run_outs',  label: 'Run Outs',  decimal: false },
    { key: 'stumpings', label: 'Stumpings', decimal: false },
  ]},
]

const OPERATORS = [
  { key: 'gte', label: 'at least' },
  { key: 'gt',  label: 'more than' },
  { key: 'eq',  label: 'exactly' },
  { key: 'lte', label: 'at most' },
  { key: 'lt',  label: 'less than' },
  { key: 'ne',  label: 'not equal' },
]

const GROUP_TABS = [
  { key: 'player', label: 'PLAYERS' },
  { key: 'team',   label: 'TEAM / SEASON' },
  { key: 'grade',  label: 'GRADE' },
]

function getAllStats(groups) {
  return groups.flatMap(g => g.stats)
}

// ─── Presets ───────────────────────────────────────────────────────────────────

const PRESETS = [
  { label: 'Run Scorers',       group: 'player', mode: 'career', filters: [], sortBy: 'runs',             sortDir: 'desc' },
  { label: 'Wicket Takers',     group: 'player', mode: 'career', filters: [], sortBy: 'wickets',          sortDir: 'desc' },
  { label: 'Batting Averages',  group: 'player', mode: 'career', filters: [{ field:'batting_innings', op:'gte', value:'20' }], sortBy: 'batting_average', sortDir: 'desc' },
  { label: 'Bowling Averages',  group: 'player', mode: 'career', filters: [{ field:'wickets', op:'gte', value:'20' }], sortBy: 'bowling_average', sortDir: 'asc' },
  { label: 'All-rounders',      group: 'player', mode: 'career', filters: [{ field:'runs', op:'gte', value:'500' }, { field:'wickets', op:'gte', value:'50' }], sortBy: 'runs', sortDir: 'desc' },
  { label: 'Most Matches',      group: 'player', mode: 'career', filters: [], sortBy: 'matches',          sortDir: 'desc' },
  { label: 'Centurions',        group: 'player', mode: 'career', filters: [{ field:'hundreds', op:'gte', value:'1' }], sortBy: 'hundreds', sortDir: 'desc' },
  { label: 'Five-for Club',     group: 'player', mode: 'career', filters: [{ field:'five_wicket_innings', op:'gte', value:'1' }], sortBy: 'five_wicket_innings', sortDir: 'desc' },
  { label: 'Season Runs',       group: 'player', mode: 'season', filters: [], sortBy: 'runs',             sortDir: 'desc' },
  { label: 'Season Wickets',    group: 'player', mode: 'season', filters: [], sortBy: 'wickets',          sortDir: 'desc' },
  { label: 'Best Economy',      group: 'player', mode: 'career', filters: [{ field:'wickets', op:'gte', value:'20' }], sortBy: 'bowling_economy', sortDir: 'asc' },
  { label: 'Power Hitters',     group: 'player', mode: 'career', filters: [], sortBy: 'sixes',            sortDir: 'desc' },
]

export default function StatLab() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  const { org, seasons, loading: clubLoading } = useClubData(orgId)
  const [searchParams, setSearchParams] = useSearchParams()

  const [mode, setMode] = useState(searchParams.get('mode') || 'career')
  const [seasonId, setSeasonId] = useState(searchParams.get('sid') || '')
  const [groupBy, setGroupBy] = useState(searchParams.get('group') || 'player')
  const [sortBy, setSortBy] = useState(searchParams.get('sort') || 'runs')
  const [sortDir, setSortDir] = useState(searchParams.get('dir') || 'desc')
  const [filters, setFilters] = useState([])
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [hasQueried, setHasQueried] = useState(false)
  const [error, setError] = useState(null)
  const [clientSort, setClientSort] = useState({ col: null, dir: null })

  if (inactive) return <ClubInactive />

  const statGroups = groupBy === 'player' ? PLAYER_STAT_GROUPS : GRADE_STAT_GROUPS
  const allStats = getAllStats(statGroups)

  const runQuery = useCallback(async (overrides = {}) => {
    if (!orgId) return
    const m = overrides.mode ?? mode
    const g = overrides.groupBy ?? groupBy
    const sb = overrides.sortBy ?? sortBy
    const sd = overrides.sortDir ?? sortDir
    const f = overrides.filters ?? filters
    const sid = overrides.seasonId ?? seasonId

    setLoading(true); setError(null); setHasQueried(true); setClientSort({ col: null, dir: null })
    const validFilters = f.filter(x => x.field && x.op && x.value !== '').map(x => `${x.field}:${x.op}:${x.value}`)
    try {
      const data = await api.statlabQuery(orgId, {
        mode: m, seasonId: m === 'season' ? sid : undefined,
        groupBy: g, sortBy: sb, sortDir: sd, limit: 500, filters: validFilters,
      })
      setRows(data)
    } catch (e) {
      setError(e.message); setRows([])
    } finally { setLoading(false) }
  }, [orgId, mode, groupBy, sortBy, sortDir, filters, seasonId])

  const applyPreset = useCallback(async (preset) => {
    const newFilters = (preset.filters || []).map((f, i) => ({ ...f, id: Date.now() + i }))
    setGroupBy(preset.group || 'player')
    setMode(preset.mode || 'career')
    setSortBy(preset.sortBy || 'runs')
    setSortDir(preset.sortDir || 'desc')
    setFilters(newFilters)
    setRows([])
    await runQuery({
      mode: preset.mode || 'career',
      groupBy: preset.group || 'player',
      sortBy: preset.sortBy || 'runs',
      sortDir: preset.sortDir || 'desc',
      filters: newFilters,
    })
  }, [runQuery])

  const addFilter = () => {
    setFilters(prev => [...prev, { id: Date.now(), field: statGroups[0]?.stats[0]?.key || 'matches', op: 'gte', value: '' }])
  }
  const updateFilter = (id, patch) => setFilters(prev => prev.map(f => f.id === id ? { ...f, ...patch } : f))
  const removeFilter = (id) => setFilters(prev => prev.filter(f => f.id !== id))
  const resetAll = () => { setFilters([]); setMode('career'); setGroupBy('player'); setSortBy('runs'); setSortDir('desc'); setRows([]); setHasQueried(false); setError(null) }

  const handleColSort = (col) => {
    const newDir = clientSort.col === col && clientSort.dir === 'desc' ? 'asc' : 'desc'
    setClientSort({ col, dir: newDir })
  }

  const sortedRows = useMemo(() => {
    if (!clientSort.col) return rows
    return [...rows].sort((a, b) => {
      const va = parseFloat(a[clientSort.col]) || 0
      const vb = parseFloat(b[clientSort.col]) || 0
      return clientSort.dir === 'asc' ? va - vb : vb - va
    })
  }, [rows, clientSort])

  const resultColumns = useMemo(() => {
    if (groupBy === 'player') {
      const filteredKeys = filters.filter(f => f.value !== '').map(f => f.field)
      const shown = new Set()
      const cols = []
      const add = (key) => {
        if (shown.has(key)) return
        const meta = allStats.find(s => s.key === key)
        if (!meta) return
        shown.add(key); cols.push(meta)
      }
      add('matches')
      filteredKeys.forEach(add)
      if (cols.length < 5) ['runs', 'batting_average', 'wickets', 'bowling_economy', 'catches'].forEach(add)
      return cols
    }
    const filteredKeys = filters.filter(f => f.value !== '').map(f => f.field)
    const shown = new Set()
    const cols = []
    const add = (key) => {
      if (shown.has(key)) return
      const meta = allStats.find(s => s.key === key)
      if (!meta) return
      shown.add(key); cols.push(meta)
    }
    add('matches'); add('unique_players')
    filteredKeys.forEach(add)
    ;['runs', 'wickets', 'catches'].forEach(add)
    return cols
  }, [groupBy, filters, allStats])

  if (clubLoading) return <PbSpinner message="Loading club data…" />

  const inputCls = 'bg-pb-surface border border-pb-hairline2 text-pb-text text-xs rounded px-2 py-1.5 focus:outline-none focus:border-pb-accent'
  const selectCls = inputCls + ' cursor-pointer'

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow="STAT LAB · CUSTOM QUERY"
          title="Build your own table."
          meta={[<span key="s">{org?.name || ''} · Filter, sort, discover.</span>]}
        />

        {/* Group by tabs */}
        <div className="flex gap-1 pb-hairline-b mb-5">
          {GROUP_TABS.map(t => (
            <button key={t.key} onClick={() => { setGroupBy(t.key); setRows([]); setHasQueried(false) }}
              className={`relative px-4 py-2.5 text-[11px] font-mono font-semibold tracking-wide3 transition ${groupBy === t.key ? 'text-pb-text' : 'text-pb-faint hover:text-pb-dim'}`}>
              {t.label}
              {groupBy === t.key && <span className="absolute left-2 right-2 -bottom-px h-[2px]" style={{ background: 'var(--pb-accent)' }} />}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[320px_1fr] gap-5">
          {/* Left panel: controls */}
          <div className="space-y-4">
            {/* Mode + season */}
            <Card title="MODE">
              <div className="flex gap-1 mb-3">
                {['career', 'season'].map(m => (
                  <button key={m} onClick={() => setMode(m)}
                    className={`flex-1 py-1.5 font-mono text-[10.5px] tracking-wide2 rounded border transition ${mode === m ? 'text-pb-text bg-pb-surface2 border-pb-hairline2' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}>
                    {m.toUpperCase()}
                  </button>
                ))}
              </div>
              {mode === 'season' && seasons?.length > 0 && (
                <select className={selectCls + ' w-full'} value={seasonId} onChange={e => setSeasonId(e.target.value)}>
                  <option value="">All seasons</option>
                  {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              )}
            </Card>

            {/* Sort by */}
            <Card title="SORT BY">
              <div className="grid grid-cols-2 gap-1.5 mb-2">
                {statGroups.flatMap(g => g.stats).slice(0, 12).map(s => (
                  <button key={s.key} onClick={() => setSortBy(s.key)}
                    className={`py-1.5 px-2 font-mono text-[10px] tracking-wide2 rounded border text-left truncate transition ${sortBy === s.key ? 'text-pb-text bg-pb-surface2 border-pb-hairline2' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}>
                    {s.label}
                  </button>
                ))}
              </div>
              <div className="flex gap-1">
                {['desc', 'asc'].map(d => (
                  <button key={d} onClick={() => setSortDir(d)}
                    className={`flex-1 py-1 font-mono text-[10px] tracking-wide2 rounded border transition ${sortDir === d ? 'text-pb-text bg-pb-surface2 border-pb-hairline2' : 'text-pb-faint border-transparent hover:border-pb-hairline'}`}>
                    {d === 'desc' ? 'HIGH → LOW' : 'LOW → HIGH'}
                  </button>
                ))}
              </div>
            </Card>

            {/* Filters */}
            <Card title="FILTERS" action={<button onClick={addFilter} className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">+ ADD</button>}>
              {filters.length === 0
                ? <p className="text-pb-faintest font-mono text-[10.5px] py-2">No filters. Click + ADD to filter results.</p>
                : (
                  <ul className="flex flex-col gap-2">
                    {filters.map(f => (
                      <li key={f.id} className="flex items-center gap-1">
                        <select className={selectCls + ' flex-1 min-w-0'} value={f.field} onChange={e => updateFilter(f.id, { field: e.target.value })}>
                          {statGroups.map(g => (
                            <optgroup key={g.key} label={g.label}>
                              {g.stats.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
                            </optgroup>
                          ))}
                        </select>
                        <select className={selectCls + ' w-24'} value={f.op} onChange={e => updateFilter(f.id, { op: e.target.value })}>
                          {OPERATORS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
                        </select>
                        <input className={inputCls + ' w-16'} type="number" value={f.value} placeholder="0" onChange={e => updateFilter(f.id, { value: e.target.value })} />
                        <button onClick={() => removeFilter(f.id)} className="text-pb-faint hover:text-pb-red font-mono text-base leading-none px-1">×</button>
                      </li>
                    ))}
                  </ul>
                )
              }
            </Card>

            {/* Actions */}
            <div className="flex gap-2">
              <Btn primary onClick={() => runQuery()} className="flex-1" disabled={loading}>
                {loading ? 'Running…' : 'Run query →'}
              </Btn>
              <Btn onClick={resetAll}>Reset</Btn>
            </div>

            {/* Presets */}
            <Card title="QUICK PRESETS">
              <div className="flex flex-col gap-1">
                {PRESETS.map((p, i) => (
                  <button key={i} onClick={() => applyPreset(p)}
                    className="text-left px-2 py-1.5 rounded hover:bg-pb-surface2 font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text transition">
                    {p.label}
                    <span className="ml-1.5 text-[10px] text-pb-faintest">{p.mode === 'season' ? '· SEASON' : ''}</span>
                  </button>
                ))}
              </div>
            </Card>
          </div>

          {/* Right panel: results */}
          <div>
            {!hasQueried && !loading && (
              <div className="pb-card p-8 flex flex-col items-center justify-center text-center gap-3" style={{ minHeight: 320 }}>
                <Label>READY</Label>
                <p className="text-pb-dim text-[15px]">Configure your query and hit <span className="text-pb-text font-semibold">Run query</span>, or pick a preset.</p>
              </div>
            )}

            {loading && <PbSpinner message="Querying…" />}

            {error && <p className="text-pb-red text-sm py-4">{error}</p>}

            {hasQueried && !loading && !error && sortedRows.length === 0 && (
              <div className="pb-card p-8 text-center">
                <p className="text-pb-faint">No results match your filters.</p>
              </div>
            )}

            {sortedRows.length > 0 && (
              <Card title={`${sortedRows.length} ${groupBy === 'player' ? 'PLAYERS' : groupBy === 'team' ? 'TEAM / SEASONS' : 'GRADES'}`}
                    action={<span className="font-mono text-2xs tracking-wide2 text-pb-faintest">SORTED BY {allStats.find(s => s.key === sortBy)?.label?.toUpperCase() || sortBy.toUpperCase()}</span>}
                    pad="p-0">
                <div className="overflow-x-auto pb-scroll">
                  <table className="w-full text-[13px]">
                    <thead>
                      <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
                        <th className="py-3 pl-5 w-8">#</th>
                        <th className="py-3 font-medium">{groupBy === 'player' ? 'PLAYER' : groupBy === 'team' ? 'TEAM · SEASON' : 'GRADE'}</th>
                        {resultColumns.map(col => (
                          <th key={col.key}
                            onClick={() => handleColSort(col.key)}
                            className="py-3 text-right font-medium cursor-pointer hover:text-pb-text pr-3 select-none"
                            style={{ color: (clientSort.col === col.key || sortBy === col.key) ? 'var(--pb-accent)' : undefined }}
                          >
                            {col.label}{clientSort.col === col.key ? (clientSort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedRows.map((row, i) => (
                        <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                          <td className="py-2.5 pl-5 font-mono text-pb-faintest">{i + 1}</td>
                          <td className="py-2.5 font-semibold">
                            {groupBy === 'player' && row.player_id
                              ? <Link to={`/players/${row.player_id}`} className="text-pb-text hover:text-pb-accent">{row.name || row.player_name}</Link>
                              : <span className="text-pb-text">{row.name || row.team_name || row.grade_name || '—'}</span>
                            }
                            {groupBy === 'player' && row.season_name && (
                              <span className="ml-2 font-mono text-[10px] text-pb-faintest">{row.season_name}</span>
                            )}
                            {groupBy === 'team' && row.season_name && (
                              <div className="font-mono text-[10px] text-pb-faintest">{row.season_name}</div>
                            )}
                          </td>
                          {resultColumns.map(col => (
                            <td key={col.key} className="py-2.5 pr-3 text-right">
                              <span className={`font-mono pb-num ${(clientSort.col === col.key || (sortBy === col.key && !clientSort.col)) ? 'font-bold' : ''}`}
                                    style={{ color: (clientSort.col === col.key || (sortBy === col.key && !clientSort.col)) ? 'var(--pb-accent)' : 'var(--pb-text)' }}>
                                {row[col.key] != null ? (col.decimal ? Number(row[col.key]).toFixed(2) : row[col.key]) : '—'}
                              </span>
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
