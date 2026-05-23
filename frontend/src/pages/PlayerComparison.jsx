import React, { useState, useEffect, useMemo, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import { PageHeader, PbSpinner, Card } from '../lib/presskit'
import { useNameFormat, nameMatchesSearch } from '../lib/nameFormat'

function PlayerSearch({ players, playersLoading, selected, onSelect, label, fmt = n => n }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const blurTimer = useRef(null)

  const filtered = useMemo(() => {
    if (!query.trim()) return players.slice(0, 20)
    return players.filter(p => nameMatchesSearch(p.display_name || p.name, query)).slice(0, 20)
  }, [players, query])

  const handleFocus = () => {
    if (blurTimer.current) clearTimeout(blurTimer.current)
    setOpen(true)
  }
  const handleBlur = () => {
    blurTimer.current = setTimeout(() => setOpen(false), 200)
  }

  const showDropdown = open && (filtered.length > 0 || playersLoading)

  return (
    <div className="relative">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">{label}</p>
      {selected ? (
        <div className="flex items-center gap-2 bg-pb-surface border pb-hairline rounded px-3 py-2.5">
          <span className="text-pb-text font-semibold flex-1 text-sm">{fmt(selected.display_name || selected.name)}</span>
          <button
            onClick={() => { onSelect(null); setQuery('') }}
            className="text-pb-faint hover:text-pb-text text-lg leading-none"
          >
            ×
          </button>
        </div>
      ) : (
        <>
          <div className="relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-pb-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder={`Search ${label.toLowerCase()}…`}
              value={query}
              onChange={e => { setQuery(e.target.value); setOpen(true) }}
              onFocus={handleFocus}
              onBlur={handleBlur}
              className="w-full bg-pb-surface border pb-hairline text-pb-text text-sm rounded pl-9 pr-4 py-2.5 focus:outline-none focus:border-pb-accent placeholder-pb-faint"
            />
          </div>
          {showDropdown && (
            <div className="absolute z-50 w-full mt-1 bg-pb-surface border pb-hairline rounded shadow-xl max-h-60 overflow-y-auto pb-scroll">
              {playersLoading && filtered.length === 0 ? (
                <p className="px-3 py-2 text-sm text-pb-faint">Loading players…</p>
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
        </>
      )}
    </div>
  )
}

const BATTING_METRICS = [
  { key: 'innings', label: 'INNINGS', higher: true },
  { key: 'total_runs', label: 'CAREER RUNS', higher: true },
  { key: 'average', label: 'BATTING AVG', higher: true },
  { key: 'strike_rate', label: 'STRIKE RATE', higher: true },
  { key: 'high_score', label: 'HIGH SCORE', higher: true },
  { key: 'fifties', label: 'FIFTIES', higher: true },
  { key: 'hundreds', label: 'CENTURIES', higher: true },
  { key: 'total_sixes', label: 'SIXES', higher: true },
  { key: 'total_fours', label: 'FOURS', higher: true },
  { key: 'ducks', label: 'DUCKS', higher: false },
]

const BOWLING_METRICS = [
  { key: 'total_wickets', label: 'WICKETS', higher: true },
  { key: 'average', label: 'BOWLING AVG', higher: false },
  { key: 'economy', label: 'ECONOMY', higher: false },
  { key: 'best_figures_wickets', label: 'BEST SPELL', higher: true },
  { key: 'five_fors', label: 'FIVE-FORS', higher: true },
  { key: 'total_maidens', label: 'MAIDENS', higher: true },
]

const FIELDING_METRICS = [
  { key: 'total_catches', label: 'CATCHES', higher: true },
  { key: 'total_run_outs', label: 'RUN OUTS', higher: true },
  { key: 'total_stumpings', label: 'STUMPINGS', higher: true },
  { key: 'total_dismissals', label: 'TOTAL DISMISSALS', higher: true },
]

const FILTER_PRESETS = [
  { id: 'career', label: 'All Time' },
  { id: 'current_season', label: 'This Season' },
  { id: 'last_season', label: 'Last Season' },
  { id: 'last_1', label: 'Last Game' },
  { id: 'last_3', label: 'Last 3 Games' },
  { id: 'last_5', label: 'Last 5 Games' },
  { id: 'custom', label: 'Custom' },
]

function CompareBar({ v1, v2, higher }) {
  const n1 = parseFloat(v1)
  const n2 = parseFloat(v2)
  if (isNaN(n1) || isNaN(n2) || (n1 === 0 && n2 === 0)) return null
  const total = n1 + n2
  const pct1 = total > 0 ? (n1 / total) * 100 : 50
  const pct2 = 100 - pct1
  const p1wins = higher ? n1 > n2 : n1 < n2
  const p2wins = higher ? n2 > n1 : n2 < n1
  return (
    <div className="flex h-1 rounded overflow-hidden mt-1.5">
      <div
        className="transition-all duration-500"
        style={{ width: `${pct1}%`, background: p1wins ? 'var(--pb-accent)' : 'var(--pb-hairline2)' }}
      />
      <div
        className="transition-all duration-500"
        style={{ width: `${pct2}%`, background: p2wins ? 'var(--pb-accent)' : 'var(--pb-hairline2)' }}
      />
    </div>
  )
}

function CompareRow({ label, v1, v2, higher, isFirst }) {
  const n1 = parseFloat(v1)
  const n2 = parseFloat(v2)
  const bothValid = !isNaN(n1) && !isNaN(n2) && v1 != null && v2 != null && n1 !== n2

  const p1win = bothValid && (higher ? n1 > n2 : n1 < n2)
  const p2win = bothValid && (higher ? n2 > n1 : n2 < n1)

  return (
    <tr className={isFirst ? '' : 'pb-hairline-t'}>
      <td className="py-3 pl-5 w-[38%]">
        <span className={`font-mono text-[15px] font-bold pb-num transition-colors ${p1win ? '' : 'text-pb-dim'}`}
          style={p1win ? { color: 'var(--pb-accent)' } : {}}>
          {v1 ?? '—'}
        </span>
        {p1win && <span className="ml-1.5 text-[10px] font-mono" style={{ color: 'var(--pb-accent)' }}>▲</span>}
      </td>
      <td className="py-3 text-center w-[24%]">
        <span className="font-mono text-[10px] tracking-wide2 text-pb-faint">{label}</span>
        <CompareBar v1={v1} v2={v2} higher={higher} />
      </td>
      <td className="py-3 pr-5 text-right w-[38%]">
        {p2win && <span className="mr-1.5 text-[10px] font-mono" style={{ color: 'var(--pb-accent)' }}>▲</span>}
        <span className={`font-mono text-[15px] font-bold pb-num transition-colors ${p2win ? '' : 'text-pb-dim'}`}
          style={p2win ? { color: 'var(--pb-accent)' } : {}}>
          {v2 ?? '—'}
        </span>
      </td>
    </tr>
  )
}

function SectionDivider({ label }) {
  return (
    <tr>
      <td colSpan={3} className="pt-5 pb-2 pl-5 font-mono text-[10px] tracking-wide3 text-pb-faint bg-pb-surface2/40 border-t border-b pb-hairline-t pb-hairline-b uppercase">
        {label}
      </td>
    </tr>
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

function filterCaption(filterMode, seasons) {
  if (filterMode === 'career') return 'ALL TIME'
  if (filterMode === 'current_season') return seasons[0] ? seasons[0].name.toUpperCase() : 'CURRENT SEASON'
  if (filterMode === 'last_season') return seasons[1] ? seasons[1].name.toUpperCase() : 'LAST SEASON'
  if (filterMode === 'last_1') return 'LAST GAME'
  if (filterMode === 'last_3') return 'LAST 3 GAMES'
  if (filterMode === 'last_5') return 'LAST 5 GAMES'
  if (filterMode === 'custom') return 'CUSTOM DATE RANGE'
  return 'ALL TIME'
}

export default function PlayerComparison() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  useClubTheme(club)
  const fmt = useNameFormat(club)

  if (inactive) return <ClubInactive />

  const [players, setPlayers] = useState([])
  const [playersLoading, setPlayersLoading] = useState(false)
  const [seasons, setSeasons] = useState([])
  const [player1, setPlayer1] = useState(null)
  const [player2, setPlayer2] = useState(null)
  const [bat1, setBat1] = useState(null)
  const [bat2, setBat2] = useState(null)
  const [bowl1, setBowl1] = useState(null)
  const [bowl2, setBowl2] = useState(null)
  const [field1, setField1] = useState(null)
  const [field2, setField2] = useState(null)
  const [loading1, setLoading1] = useState(false)
  const [loading2, setLoading2] = useState(false)
  const [filterMode, setFilterMode] = useState('career')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')

  useEffect(() => {
    if (!orgId) return
    setPlayersLoading(true)
    api.listPlayers(orgId)
      .then(data => { setPlayers(data); setPlayersLoading(false) })
      .catch(() => { setPlayers([]); setPlayersLoading(false) })
    api.getOrgSeasons(orgId).then(setSeasons).catch(() => setSeasons([]))
  }, [orgId])

  const filterParamsKey = useMemo(
    () => JSON.stringify(buildFilterParams(filterMode, seasons, customStart, customEnd)),
    [filterMode, seasons, customStart, customEnd]
  )

  const customReady = filterMode !== 'custom' || customStart || customEnd

  useEffect(() => {
    if (!player1 || !customReady) { if (!player1) { setBat1(null); setBowl1(null); setField1(null) }; return }
    setLoading1(true)
    api.getPlayerStats(player1.id, JSON.parse(filterParamsKey)).then(data => {
      setBat1(data.career_batting || {})
      setBowl1(data.career_bowling || {})
      setField1(data.career_fielding || {})
    }).catch(() => {}).finally(() => setLoading1(false))
  }, [player1, filterParamsKey]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!player2 || !customReady) { if (!player2) { setBat2(null); setBowl2(null); setField2(null) }; return }
    setLoading2(true)
    api.getPlayerStats(player2.id, JSON.parse(filterParamsKey)).then(data => {
      setBat2(data.career_batting || {})
      setBowl2(data.career_bowling || {})
      setField2(data.career_fielding || {})
    }).catch(() => {}).finally(() => setLoading2(false))
  }, [player2, filterParamsKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const showComparison = player1 && player2 && bat1 && bat2 && !loading1 && !loading2

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1300px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow="HEAD TO HEAD"
          title="Compare players."
          meta={[<span key="s">Stats side by side.</span>]}
        />

        {/* Player pickers */}
        <div className="grid md:grid-cols-2 gap-4 mb-4">
          <PlayerSearch players={players} playersLoading={playersLoading} selected={player1} onSelect={setPlayer1} label="Player 1" fmt={fmt} />
          <PlayerSearch players={players} playersLoading={playersLoading} selected={player2} onSelect={setPlayer2} label="Player 2" fmt={fmt} />
        </div>

        {/* Filter bar */}
        <div className="pb-card p-3 mb-6">
          <div className="flex flex-wrap gap-2 items-center">
            <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mr-1">Filter</span>
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
                  value={customStart}
                  onChange={e => setCustomStart(e.target.value)}
                  className="bg-pb-surface border pb-hairline text-pb-text text-xs rounded px-2 py-1 focus:outline-none focus:border-pb-accent"
                />
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-pb-faint">TO</span>
                <input
                  type="date"
                  value={customEnd}
                  onChange={e => setCustomEnd(e.target.value)}
                  className="bg-pb-surface border pb-hairline text-pb-text text-xs rounded px-2 py-1 focus:outline-none focus:border-pb-accent"
                />
              </div>
            </div>
          )}
        </div>

        {/* Empty state */}
        {!player1 && !player2 && (
          <Card>
            <div className="py-12 text-center">
              <p className="text-pb-faint text-sm">Select two players above to compare their stats.</p>
              <p className="text-pb-faintest text-xs mt-1">Accent colour highlights the superior stat.</p>
            </div>
          </Card>
        )}

        {/* Custom date prompt */}
        {player1 && player2 && filterMode === 'custom' && !customReady && (
          <Card>
            <div className="py-8 text-center">
              <p className="text-pb-faint text-sm">Enter a date range above to filter stats.</p>
            </div>
          </Card>
        )}

        {/* Loading */}
        {(loading1 || loading2) && player1 && player2 && <PbSpinner message="Loading stats…" />}

        {/* Comparison */}
        {showComparison && (
          <>
            {/* Player headers */}
            <div className="grid grid-cols-[1fr_auto_1fr] gap-0 mb-0">
              <Link to={`/players/${player1.id}`} className="pb-card rounded-b-none border-b-0 p-4 text-left hover:bg-pb-surface2 transition-colors">
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-0.5">PLAYER 1</p>
                <p className="font-semibold text-pb-text text-base">{fmt(player1.display_name || player1.name)}</p>
              </Link>
              <div className="flex items-center justify-center px-4 bg-pb-surface border-t border-b pb-hairline-t pb-hairline-b">
                <span className="font-mono text-[11px] tracking-wide3 text-pb-faintest font-bold">VS</span>
              </div>
              <Link to={`/players/${player2.id}`} className="pb-card rounded-b-none border-b-0 p-4 text-right hover:bg-pb-surface2 transition-colors">
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-0.5">PLAYER 2</p>
                <p className="font-semibold text-pb-text text-base">{fmt(player2.display_name || player2.name)}</p>
              </Link>
            </div>

            {/* Table */}
            <div className="pb-card rounded-t-none border-t-0 overflow-hidden">
              <table className="w-full">
                <tbody>
                  <SectionDivider label="Batting" />
                  {BATTING_METRICS.map((m, i) => (
                    <CompareRow
                      key={m.key}
                      label={m.label}
                      v1={bat1[m.key]}
                      v2={bat2[m.key]}
                      higher={m.higher}
                      isFirst={i === 0}
                    />
                  ))}
                  <SectionDivider label="Bowling" />
                  {BOWLING_METRICS.map((m, i) => (
                    <CompareRow
                      key={m.key}
                      label={m.label}
                      v1={bowl1?.[m.key]}
                      v2={bowl2?.[m.key]}
                      higher={m.higher}
                      isFirst={i === 0}
                    />
                  ))}
                  <SectionDivider label="Fielding" />
                  {FIELDING_METRICS.map((m, i) => (
                    <CompareRow
                      key={m.key}
                      label={m.label}
                      v1={field1?.[m.key]}
                      v2={field2?.[m.key]}
                      higher={m.higher}
                      isFirst={i === 0}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-center text-pb-faintest font-mono text-[10px] mt-3 tracking-wide2">
              ACCENT = SUPERIOR STAT · {filterCaption(filterMode, seasons)}
            </p>
          </>
        )}
      </main>
    </div>
  )
}
