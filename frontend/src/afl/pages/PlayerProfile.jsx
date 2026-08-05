import { Fragment, useEffect, useState } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import StatCard from '../../components/StatCard'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { SectionTitle, ResultPill } from '../components/bits'

// ── Charts — mirrors BetterStats (Core)'s player-profile chart language
// (pages/PlayerProfile.jsx: recharts, CSS-var colours, a single shared
// tooltip style) but kept to a single Y axis per chart throughout, rather
// than cricket's runs/wickets dual-axis SeasonChart — two measures of
// different scale get their own chart, not a second axis on one.
const CHART_TOOLTIP = {
  contentStyle: { background: 'var(--pb-surface)', border: '1px solid var(--pb-hairline2, var(--pb-hairline))', borderRadius: 8, fontSize: 12 },
  labelStyle: { color: 'var(--pb-dim)' },
  itemStyle: { color: 'var(--pb-text)' },
}

function SeasonBarChart({ rows, dataKey, name, color }) {
  const chartData = (rows || []).filter(r => r.season_id).slice().reverse()
  if (!chartData.length) return null
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" vertical={false} />
        <XAxis dataKey="season_name" tick={{ fill: 'var(--pb-faint)', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} allowDecimals={false} width={32} />
        <Tooltip {...CHART_TOOLTIP} />
        <Bar dataKey={dataKey} name={name} fill={color} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Sortable season table — mirrors BetterStats (Core)'s SEASON BY SEASON
// card (click a header to sort, hairline-top rows, hover highlight) rather
// than a bold-header-row-plus-always-expanded-sub-rows list, which reads as
// much denser for a player with 20+ seasons across several grades. The
// per-grade breakdown collapses behind a caret instead — only shown for a
// season actually split across more than one grade.
function useSortable(rows, defaultKey, defaultDir = 'desc') {
  const [sortKey, setSortKey] = useState(defaultKey)
  const [sortDir, setSortDir] = useState(defaultDir)
  const sorted = [...(rows || [])].sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (av < bv) return sortDir === 'asc' ? -1 : 1
    if (av > bv) return sortDir === 'asc' ? 1 : -1
    return 0
  })
  const request = (key, dDir = 'desc') => {
    if (sortKey === key) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir(dDir) }
  }
  return { sorted, sortKey, sortDir, request }
}

function SortTh({ label, sKey, cur, dir, onSort, dDir = 'desc' }) {
  const active = cur === sKey
  return (
    <th
      className={`px-3 py-2 text-right font-mono text-[10px] uppercase tracking-wide cursor-pointer select-none whitespace-nowrap ${active ? 'text-pb-text' : 'text-pb-faint hover:text-pb-dim'}`}
      onClick={() => onSort(sKey, dDir)}
    >
      {label}{active ? (dir === 'asc' ? ' ▲' : ' ▼') : ''}
    </th>
  )
}

function SeasonTable({ seasonRows, gradeRows }) {
  const { sorted, sortKey, sortDir, request } = useSortable(seasonRows, 'year', 'desc')
  const [expanded, setExpanded] = useState(() => new Set())
  const toggle = (sid) => setExpanded(prev => {
    const next = new Set(prev)
    if (next.has(sid)) next.delete(sid); else next.add(sid)
    return next
  })

  return (
    <div className="pb-card overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="pb-hairline-b">
          <tr>
            <th className="px-3 py-2 text-left font-mono text-[10px] uppercase tracking-wide text-pb-faint">Season</th>
            <SortTh label="GP" sKey="games" cur={sortKey} dir={sortDir} onSort={request} />
            <SortTh label="Goals" sKey="goals" cur={sortKey} dir={sortDir} onSort={request} />
            <SortTh label="BOG" sKey="bogs" cur={sortKey} dir={sortDir} onSort={request} />
          </tr>
        </thead>
        <tbody>
          {sorted.map((s, i) => {
            const grades = (gradeRows || []).filter(g => g.season_id === s.season_id)
            const hasBreakdown = grades.length > 1
            const isOpen = expanded.has(s.season_id)
            return (
              <Fragment key={s.season_id || i}>
                <tr
                  className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2/50 ${hasBreakdown ? 'cursor-pointer' : ''}`}
                  onClick={() => hasBreakdown && toggle(s.season_id)}
                >
                  <td className="px-3 py-2.5 font-medium">
                    <span className="flex items-center gap-1.5">
                      {hasBreakdown && (
                        <span className="text-pb-faint text-[9px] w-3 inline-block">{isOpen ? '▾' : '▸'}</span>
                      )}
                      {s.season_name}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right pb-num">{s.games}</td>
                  <td className="px-3 py-2.5 text-right pb-num font-semibold" style={{ color: 'var(--pb-accent)' }}>{s.goals}</td>
                  <td className="px-3 py-2.5 text-right pb-num">{s.bogs}</td>
                </tr>
                {hasBreakdown && isOpen && grades.map(g => (
                  <tr key={`${s.season_id}-${g.grade_id}`} className="text-pb-dim bg-pb-surface2/30">
                    <td className="px-3 py-1.5 pl-8 text-xs">{g.grade_name}</td>
                    <td className="px-3 py-1.5 text-right pb-num text-xs">{g.games}</td>
                    <td className="px-3 py-1.5 text-right pb-num text-xs">{g.goals}</td>
                    <td className="px-3 py-1.5 text-right pb-num text-xs">{g.bogs}</td>
                  </tr>
                ))}
              </Fragment>
            )
          })}
          {sorted.length === 0 && (
            <tr><td colSpan={4} className="px-3 py-4 text-center text-pb-faint text-sm">No seasons recorded yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

// ── Career split by the grade turned out in (Seniors, Reserves, Colts, …).
// The rows come from the API already folded across seasons and merge groups;
// all that's decided here is the leftover card. A season whose grade was
// never resolved — an Import Stats upload that only named the season —
// counts toward the career total but sits under no grade, so the difference
// is shown as its own card rather than quietly leaving the cards adding up
// to less than the totals directly above them.
function GradeBreakdown({ rows, career }) {
  const listed = rows || []
  if (!listed.length) return null

  const games = listed.reduce((a, r) => a + (r.games || 0), 0)
  const goals = listed.reduce((a, r) => a + (r.goals || 0), 0)
  const restGames = Math.max(0, (career.games || 0) - games)
  const restGoals = Math.max(0, (career.goals || 0) - goals)
  const cards = restGames > 0 || restGoals > 0
    ? [...listed, { grade: 'Grade not recorded', games: restGames, goals: restGoals, muted: true }]
    : listed

  return (
    <div>
      <SectionTitle>By grade</SectionTitle>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {cards.map(c => (
          <div key={c.grade} className="pb-card p-4">
            <span
              className={`font-mono text-[10px] tracking-wide3 uppercase block truncate ${c.muted ? 'text-pb-faintest' : 'text-pb-faint'}`}
              title={c.grade}
            >
              {c.grade}
            </span>
            <div className="flex items-baseline gap-5 mt-2.5">
              <span className="flex flex-col gap-1">
                <span className="pb-num text-2xl font-bold leading-none text-pb-text">{c.games}</span>
                <span className="font-mono text-[9px] tracking-wide3 uppercase text-pb-faintest">Games</span>
              </span>
              <span className="flex flex-col gap-1">
                <span className="pb-num text-2xl font-bold leading-none" style={{ color: 'var(--pb-accent)' }}>{c.goals}</span>
                <span className="font-mono text-[9px] tracking-wide3 uppercase text-pb-faintest">Goals</span>
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function PlayerProfile() {
  const { club } = useOutletContext()
  const { playerId } = useParams()
  const [data, setData] = useState(null)
  const [notFound, setNotFound] = useState(false)
  const base = `/${club.slug}`

  useEffect(() => {
    setData(null)
    aflApi.getPlayer(playerId).then(setData).catch(() => setNotFound(true))
  }, [playerId])

  if (notFound) return <p className="pt-16 text-center text-pb-dim">Player not found.</p>
  if (!data) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>
  const c = data.career || {}

  // Whole-season rows only for the season table + charts (per-grade rows nested under them).
  const seasonRows = (data.seasons || []).filter(s => !s.grade_id)
  const gradeRows = (data.seasons || []).filter(s => s.grade_id)
  const hasChartData = seasonRows.filter(s => s.season_id).length >= 2

  return (
    <div className="space-y-6">
      <div className="flex items-stretch gap-3.5">
        <span className="w-1 rounded-full shrink-0" style={{ background: 'var(--pb-gradient)' }} />
        <div className="flex items-center gap-4">
          {data.photo_url
            ? <img src={data.photo_url} alt="" className="h-20 w-20 rounded-full object-cover" />
            : <span className="h-20 w-20 rounded-full bg-pb-surface2 flex items-center justify-center text-2xl text-pb-faint">
                {(data.name || '?').split(' ').map(w => w[0]).slice(0, 2).join('')}
              </span>}
          <div>
            <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight text-pb-text">{data.name}</h1>
            <p className="text-sm text-pb-dim font-mono mt-1">
              {c.first_year ? (c.first_year === c.last_year ? c.first_year : `${c.first_year} – ${c.last_year}`) : ''}
              {c.seasons ? ` · ${c.seasons} season${c.seasons > 1 ? 's' : ''}` : ''}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Games" value={c.games} accent large />
        <StatCard label="Goals" value={c.goals} large />
        <StatCard label="Best on Ground" value={c.bogs} large />
        <StatCard
          label="Best haul"
          value={data.best_haul ? data.best_haul.goals : '—'}
          sub={data.best_haul ? `${data.best_haul.round_name || ''} ${data.best_haul.season_name || ''}`.trim() : null}
          large
        />
      </div>

      <GradeBreakdown rows={data.grade_breakdown} career={c} />

      {hasChartData && (
        <div>
          <SectionTitle>Career trajectory</SectionTitle>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="pb-card p-4">
              <p className="font-mono text-[10px] tracking-wide uppercase text-pb-faint mb-2">Goals by season</p>
              <SeasonBarChart rows={seasonRows} dataKey="goals" name="Goals" color="var(--pb-chart-1)" />
            </div>
            <div className="pb-card p-4">
              <p className="font-mono text-[10px] tracking-wide uppercase text-pb-faint mb-2">Games by season</p>
              <SeasonBarChart rows={seasonRows} dataKey="games" name="Games" color="var(--pb-chart-2)" />
            </div>
          </div>
        </div>
      )}

      <div>
        <SectionTitle right={<span className="hidden sm:inline text-[10px] text-pb-faintest font-mono normal-case tracking-normal">Click a season with a grade split to expand it</span>}>
          Season by season
        </SectionTitle>
        <SeasonTable seasonRows={seasonRows} gradeRows={gradeRows} />
      </div>

      <div>
        <SectionTitle>Game log</SectionTitle>
        <div className="pb-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="pb-hairline-b">
              <tr>
                {['Date', 'Round', 'Match', 'Goals', 'BOG', ''].map((h, i) => (
                  <th key={h + i} className={`px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-pb-faint ${i >= 3 ? 'text-right' : 'text-left'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data.game_log || []).map(g => (
                <tr key={g.game_id} className="pb-hairline-b last:border-0 hover:bg-pb-surface2/50">
                  <td className="px-3 py-2 pb-num text-pb-faint whitespace-nowrap">{g.played_at}</td>
                  <td className="px-3 py-2 text-pb-faint whitespace-nowrap">{g.round_name || (g.is_final ? 'Final' : '')}</td>
                  <td className="px-3 py-2">
                    <Link to={`${base}/games/${g.game_id}`} className="hover:text-[var(--pb-accent)]">
                      {g.home_team} v {g.away_team}
                    </Link>
                    <span className="block text-[11px] text-pb-faintest">{g.grade_name}</span>
                  </td>
                  <td className="px-3 py-2 text-right pb-num font-semibold">{g.goals}</td>
                  <td className="px-3 py-2 text-right">
                    {g.bog_ranking != null && (
                      <span className="font-mono text-[10px] font-bold px-1.5 py-0.5 rounded bg-[color-mix(in_srgb,var(--pb-amber)_20%,transparent)] text-[var(--pb-amber)]">
                        BOG{g.bog_ranking === 1 ? ' #1' : ''}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right"><ResultPill result={g.result} /></td>
                </tr>
              ))}
              {(data.game_log || []).length === 0 && (
                <tr><td colSpan={6} className="px-3 py-4 text-center text-pb-faint text-sm">
                  {(c.games || 0) > 0
                    ? "No individual game records — this player's history comes from an imported season-totals spreadsheet, which doesn't include a game-by-game breakdown."
                    : 'No games recorded yet.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
