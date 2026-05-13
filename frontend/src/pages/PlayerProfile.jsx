import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import { useClubTheme } from '../hooks/useClubTheme'
import { getSubcategories, getAchievements } from '../lib/achievementOptions'
import { usePlayerStats } from '../hooks/usePlayerStats'
import { CATEGORY_ICON_SRC, MILESTONE_ICON_SRC, ThiingIcon, thiings } from '../assets/thiings'
import {
  AnimatedNum, Sparkline, Label, Card, Btn,
  ResultPill, PageHeader, PbSpinner, TabBar,
} from '../lib/presskit'
import {
  BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  LineChart, Line, PieChart, Pie, Cell,
} from 'recharts'

const MAIN_TABS = [
  { key: 'batting',       label: 'BATTING' },
  { key: 'bowling',       label: 'BOWLING' },
  { key: 'fielding',      label: 'FIELDING' },
  { key: 'analysis',      label: 'ANALYSIS' },
  { key: 'milestones',    label: 'MILESTONES' },
  { key: 'achievements',  label: 'HONOURS' },
]

function fmt(val, dec = false) {
  if (val == null || val === '' || val === undefined) return '—'
  if (dec) return typeof val === 'number' ? val.toFixed(2) : val
  return val
}

function fmtNum(val) {
  if (val == null || val === '') return '—'
  return Number(val).toLocaleString()
}

function fmtDec(val, dec = 2) {
  if (val == null || val === '') return '—'
  return Number(val).toFixed(dec)
}

function formatSeasonShort(value, seasons) {
  if (!value) return null
  const match = seasons?.find(s => s.id === value)
  const name = match ? match.name : String(value)
  const m = name.match(/(\d{2})(\d{2})\s*[\/_-]\s*(\d{2})/)
  if (m) return `${m[2]}/${m[3]}`
  const single = name.match(/\b(\d{4})\b/)
  if (single) return single[1].slice(2)
  return name
}

function formatRange(inst, seasons) {
  const start = formatSeasonShort(inst.season, seasons)
  const end = formatSeasonShort(inst.season_end, seasons)
  if (start && end && start !== end) return `${start}–${end}`
  return start || end || null
}

function formatAchievementBadge(a, seasons) {
  const label = a.achievement || a.subcategory || a.category
  if (a.category === 'Milestone' && a.subcategory === 'Cap Number' && a.detail) return `${label} ${a.detail}`
  if (a._instances && a._instances.length > 1) {
    const ranges = a._instances.map(i => formatRange(i, seasons)).filter(Boolean)
    if (ranges.length) return `${label} ${ranges.join(', ')}`
  }
  const range = formatRange(a, seasons)
  return range ? `${label} (${range})` : label
}

const EXEC_RANK = { 'president': 1, 'vice president': 2, 'vice-president': 2, 'secretary': 3, 'treasurer': 3 }
function headerPriority(a) {
  if (a.category === 'Hall of Fame') return 0
  if (a.category === 'Life Membership') return 1.5
  if (a.category === 'Office Bearer' && a.subcategory === 'Executive Committee') {
    return EXEC_RANK[(a.achievement || '').toLowerCase()] ?? 3
  }
  if (a.category === 'Milestone') {
    if (a.subcategory === 'Cap Number') return 2.5
    if (a.subcategory === 'Games') {
      const n = parseInt((a.achievement || '').match(/(\d+)/)?.[1] || '0', 10)
      if (n >= 500) return 3; if (n >= 300) return 4.5; if (n >= 200) return 5
      return 9
    }
    return 9
  }
  if (a.category === 'Premiership') return 4
  if (a.category === 'Association Award') return 6
  if (a.category === 'Club Award') return 7
  if (a.category === 'Office Bearer') return 8
  return 99
}

function useSortable(rows, defaultKey, defaultDir = 'desc') {
  const [sortKey, setSortKey] = useState(defaultKey)
  const [sortDir, setSortDir] = useState(defaultDir)
  const sorted = useMemo(() => {
    if (!Array.isArray(rows) || !sortKey) return rows
    const dir = sortDir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = a?.[sortKey], bv = b?.[sortKey]
      if (av == null && bv == null) return 0
      if (av == null) return 1; if (bv == null) return -1
      const an = typeof av === 'number' ? av : Number(av)
      const bn = typeof bv === 'number' ? bv : Number(bv)
      if (!Number.isNaN(an) && !Number.isNaN(bn)) return (an - bn) * dir
      return String(av).localeCompare(String(bv)) * dir
    })
  }, [rows, sortKey, sortDir])
  function request(key, dDir = 'desc') {
    if (key === sortKey) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir(dDir) }
  }
  return { sorted, sortKey, sortDir, request }
}

function SortTh({ label, sKey, cur, dir, onSort, dDir = 'desc', right = false }) {
  const active = sKey === cur
  return (
    <th
      onClick={() => onSort(sKey, dDir)}
      className={`pb-2 font-mono text-[10px] tracking-wide3 cursor-pointer select-none hover:text-pb-text transition-colors ${right ? 'text-right' : 'text-left'}`}
      style={{ color: active ? 'var(--pb-accent)' : undefined }}
    >
      {label}{active ? (dir === 'asc' ? ' ↑' : ' ↓') : ''}
    </th>
  )
}

// ── Rank helpers for highlighting best/worst seasons ───────────────────────
function computeRankSets(rows, key, direction = 'desc') {
  if (!rows?.length) return { topIdx: new Set(), botIdx: new Set() }
  const valid = rows.map((r, i) => ({ i, v: r[key] })).filter(x => x.v != null && !Number.isNaN(Number(x.v)))
  if (valid.length < 2) return { topIdx: new Set(), botIdx: new Set() }
  const sorted = [...valid].sort((a, b) => direction === 'desc' ? b.v - a.v : a.v - b.v)
  const topN = Math.min(3, sorted.length - 1)
  const topIdx = new Set(sorted.slice(0, topN).map(x => x.i))
  const botIdx = new Set([sorted[sorted.length - 1]].filter(x => !topIdx.has(x.i)).map(x => x.i))
  return { topIdx, botIdx }
}

function rankCls(i, topIdx, botIdx, defaultCls = 'text-pb-dim') {
  if (topIdx.has(i)) return 'text-green-400 font-bold'
  if (botIdx.has(i)) return 'text-red-400'
  return defaultCls
}

// ── Charts ──────────────────────────────────────────────────────────────────
const PIE_COLORS = ['#16c784', '#3b82f6', '#f59e0b', '#a855f7', '#ef4444', '#06b6d4', '#84cc16', '#f97316']

const CHART_TOOLTIP_STYLE = {
  contentStyle: { background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 },
  labelStyle: { color: '#94a3b8' },
  itemStyle: { color: '#fff' },
}

function DismissalDonut({ dismissals }) {
  if (!dismissals?.length) return null
  const total = dismissals.reduce((s, d) => s + Number(d.count), 0)
  const pieData = dismissals.map(d => ({ name: d.dismissal_type || 'Unknown', value: Number(d.count) }))
  return (
    <div className="flex flex-col md:flex-row items-center gap-6">
      <div className="w-44 h-44 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={pieData} cx="50%" cy="50%" innerRadius={45} outerRadius={72} dataKey="value" paddingAngle={2}>
              {pieData.map((_, idx) => <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />)}
            </Pie>
            <Tooltip contentStyle={CHART_TOOLTIP_STYLE.contentStyle} formatter={(v) => [`${v} (${Math.round(v/total*100)}%)`, '']} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-col gap-1.5 flex-1 min-w-0">
        {dismissals.map((d, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
            <span className="capitalize text-pb-dim flex-1 truncate">{d.dismissal_type || 'Unknown'}</span>
            <span className="font-mono font-bold text-pb-text">{d.count}</span>
            <span className="font-mono text-pb-faint text-[11px] w-9 text-right">{Math.round(Number(d.count)/total*100)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function SeasonChart({ data }) {
  if (!data?.length) return null
  const chartData = [...data].reverse()
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="season_name" tick={{ fill: '#64748b', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis yAxisId="left" tick={{ fill: '#64748b', fontSize: 11 }} />
        <YAxis yAxisId="right" orientation="right" tick={{ fill: '#64748b', fontSize: 11 }} />
        <Tooltip {...CHART_TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
        <Bar yAxisId="left" dataKey="total_runs" name="Runs" fill="#16c784" radius={[3,3,0,0]} />
        <Bar yAxisId="right" dataKey="total_wickets" name="Wickets" fill="#3b82f6" radius={[3,3,0,0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function CumulativeRunsChart({ seasonStats }) {
  if (!seasonStats?.length) return null
  let cumulative = 0
  const chartData = [...seasonStats].reverse().map(s => {
    cumulative += (s.total_runs ?? 0)
    return { season: s.season_name?.replace('Summer ', '') ?? '', total: cumulative, season_runs: s.total_runs ?? 0 }
  })
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="season" tick={{ fill: '#64748b', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
        <Tooltip {...CHART_TOOLTIP_STYLE} formatter={(v, name) => [v.toLocaleString(), name === 'total' ? 'Career total' : 'Season runs']} />
        <Bar dataKey="season_runs" name="season_runs" fill="#16c78440" radius={[2,2,0,0]} />
        <Line type="monotone" dataKey="total" name="total" stroke="#16c784" strokeWidth={2} dot={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function AveragesChart({ seasonStats }) {
  if (!seasonStats?.length) return null
  const chartData = [...seasonStats].reverse()
    .filter(s => s.batting_average != null || s.bowling_average != null)
    .map(s => ({
      season: s.season_name?.replace('Summer ', '') ?? '',
      bat_avg: s.batting_average != null ? Number(Number(s.batting_average).toFixed(1)) : null,
      bowl_avg: s.bowling_average != null ? Number(Number(s.bowling_average).toFixed(1)) : null,
    }))
  if (!chartData.length) return null
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="season" tick={{ fill: '#64748b', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
        <Tooltip {...CHART_TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
        <Line type="monotone" dataKey="bat_avg" name="Batting Avg" stroke="#16c784" strokeWidth={2} dot={{ r: 3 }} connectNulls />
        <Line type="monotone" dataKey="bowl_avg" name="Bowling Avg" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  )
}

function RunsByGradeChart({ byGrade }) {
  if (!byGrade?.length) return null
  const sorted = [...byGrade].sort((a, b) => b.runs - a.runs).slice(0, 10)
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, sorted.length * 36)}>
      <BarChart data={sorted} layout="vertical" margin={{ top: 5, right: 60, left: 8, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
        <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
        <YAxis type="category" dataKey="grade_name" width={130} tick={{ fill: '#94a3b8', fontSize: 11 }} />
        <Tooltip {...CHART_TOOLTIP_STYLE} formatter={(v, _, props) => [`${v} runs (${props.payload.innings} inn, avg ${props.payload.average ?? '—'})`, '']} />
        <Bar dataKey="runs" fill="#16c784" radius={[0,3,3,0]} label={{ position: 'right', fill: '#64748b', fontSize: 11 }} />
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Batting tab ─────────────────────────────────────────────────────────
function BattingTab({ batting, seasonStats, seasons }) {
  const { sorted, sortKey, sortDir, request } = useSortable(seasonStats, 'season_name', 'desc')
  if (!batting) return <PbSpinner />

  return (
    <div className="space-y-6">
      {/* Career summary */}
      <Card title="CAREER BATTING">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-x-6 gap-y-4">
          {[
            ['INNINGS', batting.innings],
            ['RUNS', batting.total_runs, true],
            ['AVERAGE', fmtDec(batting.average)],
            ['HIGH SCORE', batting.high_score],
            ['100s · 50s', `${batting.hundreds ?? 0} · ${batting.fifties ?? 0}`],
            ['4s', batting.total_fours ?? 0],
            ['6s', batting.total_sixes ?? 0],
            ['DUCKS', batting.ducks ?? 0],
          ].map(([label, value, accent]) => (
            <div key={label} className="flex flex-col">
              <span className="font-mono text-[9.5px] tracking-wide3 text-pb-faint">{label}</span>
              <span className="font-mono font-bold text-[22px] pb-num leading-tight mt-0.5"
                    style={{ color: accent ? 'var(--pb-accent)' : 'var(--pb-text)' }}>
                {typeof value === 'number' ? <AnimatedNum value={value} /> : value}
              </span>
            </div>
          ))}
        </div>
      </Card>

      {/* Season-by-season */}
      {seasonStats?.length > 0 && (
        <Card title="SEASON BY SEASON" pad="p-0">
          <div className="overflow-x-auto pb-scroll">
            <table className="w-full min-w-[700px] text-[13px]">
              <thead className="text-pb-faint font-mono text-[10px] tracking-wide3">
                <tr>
                  <th className="py-3 pl-5 text-left pb-2">SEASON</th>
                  <SortTh label="INN" sKey="batting_innings" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="RUNS" sKey="total_runs" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="AVG" sKey="batting_average" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="HS" sKey="high_score" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="100s" sKey="hundreds" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="50s" sKey="fifties" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="4s" sKey="total_fours" cur={sortKey} dir={sortDir} onSort={request} right />
                  <th className="py-3 pr-5 text-right pb-2 font-mono text-[10px] tracking-wide3">0s</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((s, i) => (
                  <tr key={s.season_name || i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 pl-5 font-mono text-pb-dim text-[12px]">{s.season_name}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.batting_innings)}</td>
                    <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{fmt(s.total_runs)}</td>
                    <td className="py-2.5 font-mono text-pb-text text-right">{fmt(s.batting_average, true)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.high_score)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.hundreds)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.fifties)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.total_fours)}</td>
                    <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">{fmt(s.ducks)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}

// ── Bowling tab ──────────────────────────────────────────────────────────
function BowlingTab({ bowling, seasonStats }) {
  const { sorted, sortKey, sortDir, request } = useSortable(seasonStats, 'season_name', 'desc')
  if (!bowling) return <PbSpinner />

  return (
    <div className="space-y-6">
      <Card title="CAREER BOWLING">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-x-6 gap-y-4">
          {[
            ['WICKETS', bowling.total_wickets, true],
            ['OVERS', bowling.total_overs != null ? Number(bowling.total_overs).toFixed(1) : '—'],
            ['AVERAGE', fmtDec(bowling.average)],
            ['ECONOMY', fmtDec(bowling.economy)],
            ['5-FORS', bowling.five_fors ?? 0],
            ['MAIDENS', bowling.total_maidens ?? 0],
            ['BEST', bowling.best_bowling_figures || (bowling.best_figures_wickets ? `${bowling.best_figures_wickets}w` : '—')],
          ].map(([label, value, accent]) => (
            <div key={label} className="flex flex-col">
              <span className="font-mono text-[9.5px] tracking-wide3 text-pb-faint">{label}</span>
              <span className="font-mono font-bold text-[22px] pb-num leading-tight mt-0.5"
                    style={{ color: accent ? 'var(--pb-accent)' : 'var(--pb-text)' }}>
                {typeof value === 'number' ? <AnimatedNum value={value} /> : value}
              </span>
            </div>
          ))}
        </div>
      </Card>

      {seasonStats?.length > 0 && (
        <Card title="SEASON BY SEASON" pad="p-0">
          <div className="overflow-x-auto pb-scroll">
            <table className="w-full min-w-[640px] text-[13px]">
              <thead className="text-pb-faint font-mono text-[10px] tracking-wide3">
                <tr>
                  <th className="py-3 pl-5 text-left pb-2">SEASON</th>
                  <SortTh label="WKTS" sKey="total_wickets" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="OV" sKey="total_overs" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="AVG" sKey="bowling_average" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="ECON" sKey="economy" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="5W" sKey="five_fors" cur={sortKey} dir={sortDir} onSort={request} right />
                  <th className="py-3 pr-5 text-right pb-2 font-mono text-[10px] tracking-wide3">BEST</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((s, i) => (
                  <tr key={s.season_name || i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 pl-5 font-mono text-pb-dim text-[12px]">{s.season_name}</td>
                    <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{fmt(s.total_wickets)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{s.total_overs != null ? Number(s.total_overs).toFixed(1) : '—'}</td>
                    <td className="py-2.5 font-mono text-pb-text text-right">{fmt(s.bowling_average, true)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmtDec(s.economy)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.five_fors)}</td>
                    <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">
                      {s.best_bowling_figures || (s.best_bowling_wickets ? `${s.best_bowling_wickets}w` : '—')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}

// ── Fielding tab ─────────────────────────────────────────────────────────
function FieldingTab({ fielding, seasonStats }) {
  const { sorted, sortKey, sortDir, request } = useSortable(seasonStats, 'season_name', 'desc')
  if (!fielding) return <PbSpinner />

  return (
    <div className="space-y-6">
      <Card title="CAREER FIELDING">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-4">
          {[
            ['CATCHES', fielding.total_catches, true],
            ['RUN OUTS', fielding.total_run_outs],
            ['STUMPINGS', fielding.total_stumpings],
          ].map(([label, value, accent]) => (
            <div key={label} className="flex flex-col">
              <span className="font-mono text-[9.5px] tracking-wide3 text-pb-faint">{label}</span>
              <span className="font-mono font-bold text-[22px] pb-num leading-tight mt-0.5"
                    style={{ color: accent ? 'var(--pb-accent)' : 'var(--pb-text)' }}>
                {typeof value === 'number' ? <AnimatedNum value={value} /> : (value ?? '—')}
              </span>
            </div>
          ))}
        </div>
      </Card>

      {seasonStats?.length > 0 && (
        <Card title="SEASON BY SEASON" pad="p-0">
          <div className="overflow-x-auto pb-scroll">
            <table className="w-full min-w-[400px] text-[13px]">
              <thead className="text-pb-faint font-mono text-[10px] tracking-wide3">
                <tr>
                  <th className="py-3 pl-5 text-left pb-2">SEASON</th>
                  <SortTh label="CATCHES" sKey="total_catches" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="RUN OUTS" sKey="total_run_outs" cur={sortKey} dir={sortDir} onSort={request} right />
                  <th className="py-3 pr-5 text-right pb-2 font-mono text-[10px] tracking-wide3">STUMPINGS</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((s, i) => (
                  <tr key={s.season_name || i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 pl-5 font-mono text-pb-dim text-[12px]">{s.season_name}</td>
                    <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{fmt(s.total_catches)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.total_run_outs)}</td>
                    <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">{fmt(s.total_stumpings)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}

// ── Analysis tab ─────────────────────────────────────────────────────────
function AnalysisTab({ playerId, dismissals, partnerships, byGrade, byPosition, seasonStats }) {
  return (
    <div className="space-y-6">
      {/* Runs & Wickets by season */}
      {seasonStats?.length > 0 && (
        <Card title="RUNS & WICKETS BY SEASON">
          <SeasonChart data={seasonStats} />
        </Card>
      )}

      {/* Cumulative career runs */}
      {seasonStats?.some(s => (s.total_runs ?? 0) > 0) && (
        <Card title="CAREER RUNS ACCUMULATION">
          <p className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-3">Running total of career batting runs, season by season.</p>
          <CumulativeRunsChart seasonStats={seasonStats} />
        </Card>
      )}

      {/* Averages over time */}
      {seasonStats?.length > 0 && (
        <Card title="AVERAGES OVER TIME">
          <p className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-3">Batting and bowling averages season by season.</p>
          <AveragesChart seasonStats={seasonStats} />
        </Card>
      )}

      {/* Dismissal donut */}
      {dismissals?.length > 0 && (
        <Card title="HOW I GET OUT">
          <DismissalDonut dismissals={dismissals} />
        </Card>
      )}

      {/* Runs by grade chart */}
      {byGrade?.length > 1 && (
        <Card title="RUNS BY GRADE">
          <p className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-3">Career batting runs broken down by grade.</p>
          <RunsByGradeChart byGrade={byGrade} />
        </Card>
      )}

      {/* Partnerships */}
      {partnerships?.length > 0 && (
        <Card title="TOP PARTNERSHIPS" pad="p-0">
          <div className="overflow-x-auto pb-scroll">
            <table className="w-full min-w-[400px] text-[13px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                  <th className="py-3 pl-5 pb-2">PARTNER</th>
                  <th className="py-3 text-right pb-2">BEST</th>
                  <th className="py-3 text-right pb-2">TOTAL</th>
                  <th className="py-3 pr-5 text-right pb-2">TIMES</th>
                </tr>
              </thead>
              <tbody>
                {partnerships.slice(0, 10).map((p, i) => (
                  <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 pl-5">
                      {p.partner_id
                        ? <Link to={`/players/${p.partner_id}`} className="text-pb-text hover:text-pb-accent">{p.partner_name ?? '—'}</Link>
                        : <span className="text-pb-dim">{p.partner_name ?? '—'}</span>}
                    </td>
                    <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{p.best_runs ?? '—'}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{p.total_runs ?? '—'}</td>
                    <td className="py-2.5 pr-5 font-mono text-pb-faint text-right">{p.partnership_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* By grade detail table */}
      {byGrade?.length > 0 && (
        <Card title="BATTING BY GRADE" pad="p-0">
          <div className="overflow-x-auto pb-scroll">
            <table className="w-full min-w-[420px] text-[13px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                  <th className="py-3 pl-5 pb-2">GRADE</th>
                  <th className="py-3 text-right pb-2">INN</th>
                  <th className="py-3 text-right pb-2">RUNS</th>
                  <th className="py-3 text-right pb-2">AVG</th>
                  <th className="py-3 pr-5 text-right pb-2">HS</th>
                </tr>
              </thead>
              <tbody>
                {byGrade.map((r, i) => (
                  <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 pl-5 text-pb-text">{r.grade_name}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{r.innings}</td>
                    <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{r.runs}</td>
                    <td className="py-2.5 font-mono text-pb-text text-right">{fmt(r.average, true)}</td>
                    <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">{r.high_score ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* By position */}
      {byPosition?.length > 0 && (
        <Card title="BATTING BY POSITION" pad="p-0">
          <div className="overflow-x-auto pb-scroll">
            <table className="w-full min-w-[420px] text-[13px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                  <th className="py-3 pl-5 pb-2">POSITION</th>
                  <th className="py-3 text-right pb-2">INN</th>
                  <th className="py-3 text-right pb-2">RUNS</th>
                  <th className="py-3 text-right pb-2">AVG</th>
                  <th className="py-3 pr-5 text-right pb-2">HS</th>
                </tr>
              </thead>
              <tbody>
                {byPosition.map((r, i) => (
                  <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 pl-5 font-mono text-pb-text">#{r.batting_position}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{r.innings}</td>
                    <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{r.runs}</td>
                    <td className="py-2.5 font-mono text-pb-text text-right">{fmt(r.average, true)}</td>
                    <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">{r.high_score ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {!dismissals?.length && !partnerships?.length && !byGrade?.length && !byPosition?.length && !seasonStats?.length && (
        <p className="text-pb-faint text-sm py-4">No analysis data available. Game-level data may still be syncing.</p>
      )}
    </div>
  )
}

// ── Milestones tab ───────────────────────────────────────────────────────
function MilestonesTab({ playerId, upcomingMilestones, milestones }) {
  return (
    <div className="space-y-6">
      {/* Upcoming */}
      {upcomingMilestones?.length > 0 && (
        <Card title="MILESTONES IN REACH">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {upcomingMilestones.map((m, i) => {
              const pct = Math.min(100, Math.round((m.current / m.target) * 100))
              return (
                <div key={i} className="pb-card-2 p-4 rounded border border-pb-hairline">
                  <Label>{m.type?.toUpperCase() || 'MILESTONE'}</Label>
                  <div className="flex items-baseline justify-between mt-2 mb-2">
                    <span className="font-mono text-[26px] font-bold pb-num leading-none" style={{ color: 'var(--pb-accent)' }}>
                      <AnimatedNum value={m.current} />
                    </span>
                    <span className="font-mono text-[11px] text-pb-dim tracking-wide2">/ {m.target?.toLocaleString()}</span>
                  </div>
                  <div className="h-1 bg-pb-hairline rounded-sm overflow-hidden">
                    <div className="h-full" style={{ width: `${pct}%`, background: 'var(--pb-accent)' }} />
                  </div>
                  <div className="font-mono text-[10.5px] text-pb-faint tracking-wide2 mt-1.5">{pct}% · {m.needed?.toLocaleString()} to go</div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Achieved */}
      {milestones?.length > 0 && (
        <Card title="ACHIEVED MILESTONES" pad="p-0">
          <ul className="flex flex-col">
            {milestones.map((m, i) => {
              const typeLabel = { runs: 'Runs', wickets: 'Wickets', matches: 'Matches', catches: 'Catches' }[m.milestone_type] || m.milestone_type || 'Milestone'
              const title = m.milestone_value != null ? `${m.milestone_value.toLocaleString()} ${typeLabel}` : typeLabel
              const dateStr = m.achieved_at
                ? new Date(m.achieved_at + 'T00:00:00').toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
                : null
              return (
                <li key={i} className={`${i ? 'pb-hairline-t' : ''} flex items-center gap-4 px-5 py-3 hover:bg-pb-surface2`}>
                  <ThiingIcon src={MILESTONE_ICON_SRC[m.milestone_type] || thiings.trophy} alt="" className="w-6 h-6 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-pb-text text-[14px] font-semibold">{title}</div>
                    <div className="font-mono text-pb-faint text-[10.5px] tracking-wide2 mt-0.5">
                      {[m.detail, dateStr].filter(Boolean).join(' · ')}
                    </div>
                  </div>
                  <span className="font-mono text-[18px] font-bold pb-num" style={{ color: 'var(--pb-accent)' }}>
                    {m.milestone_value?.toLocaleString()}
                  </span>
                </li>
              )
            })}
          </ul>
        </Card>
      )}

      {!upcomingMilestones?.length && !milestones?.length && (
        <p className="text-pb-faint text-sm py-4">No milestone data available.</p>
      )}
    </div>
  )
}

// ── Achievements tab ──────────────────────────────────────────────────────
function AchievementsSection({ playerId, orgId, playerName }) {
  const { user } = useAuth()
  const canEdit = !!user
  const [achievements, setAchievements] = useState(null)
  const [seasons, setSeasons] = useState([])
  const [adding, setAdding] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState({ season: '', season_end: '', category: 'Club Award', subcategory: '', achievement: '', detail: '' })
  const [customSubcat, setCustomSubcat] = useState(false)
  const [customAchievement, setCustomAchievement] = useState(false)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState(null)

  useEffect(() => {
    if (!orgId) return
    api.listAchievements(orgId, { playerId }).then(setAchievements).catch(() => setAchievements([]))
    api.getOrgSeasons(orgId).then(data => setSeasons(data || [])).catch(() => {})
  }, [playerId, orgId])

  const subcatOptions = getSubcategories(form.category)
  const achievementOptions = getAchievements(form.category, form.subcategory)
  const seasonMap = Object.fromEntries(seasons.map(s => [s.id, s.name]))
  const seasonDisplay = (s) => !s || s === 'All Time' ? 'All Time' : (seasonMap[s] || s.replace(/_/g, '/'))

  const openEdit = (a) => {
    setForm({ season: a.season||'', season_end: a.season_end||'', category: a.category, subcategory: a.subcategory||'', achievement: a.achievement, detail: a.detail||'' })
    setCustomSubcat(false); setCustomAchievement(false)
    setEditId(a.id); setAdding(true)
  }

  const handleSave = async () => {
    if (!form.achievement.trim() || !form.category) return
    setSaving(true); setFormError(null)
    try {
      if (editId) {
        await api.updateAchievement(editId, form)
      } else {
        await api.createAchievement({ ...form, org_id: orgId, player_id: playerId, player_name: playerName || '' })
      }
      const updated = await api.listAchievements(orgId, { playerId })
      setAchievements(updated); setAdding(false); setEditId(null)
    } catch (e) { setFormError(e.message) } finally { setSaving(false) }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this achievement?')) return
    await api.deleteAchievement(id, orgId)
    setAchievements(prev => prev.filter(a => a.id !== id))
  }

  if (achievements === null) return <PbSpinner />

  const honours = [], roles = [], awards = [], milestones = []
  for (const a of achievements) {
    if (['Hall of Fame', 'Life Membership', 'Premiership'].includes(a.category) ||
        (a.category === 'Milestone' && a.subcategory === 'Cap Number')) honours.push(a)
    else if (a.category === 'Office Bearer') roles.push(a)
    else if (['Club Award', 'Association Award'].includes(a.category)) awards.push(a)
    else if (a.category === 'Milestone') milestones.push(a)
    else awards.push(a)
  }
  const bySeasonDesc = (a, b) => (b.season || '').localeCompare(a.season || '')
  honours.sort((a, b) => { const p = headerPriority(a) - headerPriority(b); return p || bySeasonDesc(a, b) })
  awards.sort(bySeasonDesc); milestones.sort(bySeasonDesc)

  const rolesGrouped = new Map()
  for (const r of roles) {
    const key = `${r.subcategory || ''}|${r.achievement}`
    if (!rolesGrouped.has(key)) rolesGrouped.set(key, { subcategory: r.subcategory, achievement: r.achievement, instances: [] })
    rolesGrouped.get(key).instances.push(r)
  }
  for (const g of rolesGrouped.values()) g.instances.sort(bySeasonDesc)
  const rolesList = [...rolesGrouped.values()].sort((a, b) =>
    (b.instances[0]?.season || '').localeCompare(a.instances[0]?.season || ''))

  const inputCls = 'w-full bg-pb-surface border border-pb-hairline2 text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faintest'
  const selectCls = inputCls + ' cursor-pointer'

  const seasonRange = (a) => {
    const s = seasonDisplay(a.season)
    if (a.season_end && a.season_end !== a.season) return `${s}–${seasonDisplay(a.season_end)}`
    return s
  }

  const AchievementCard = ({ a, accent = false }) => (
    <div className="relative group rounded border pb-hairline p-4 bg-pb-surface hover:bg-pb-surface2 transition-colors"
         style={accent ? { borderColor: 'color-mix(in srgb, var(--pb-amber) 40%, transparent)', background: 'color-mix(in srgb, var(--pb-amber) 5%, transparent)' } : {}}>
      <div className="flex items-start gap-3">
        <ThiingIcon src={CATEGORY_ICON_SRC[a.category] || thiings.trophy} alt="" className="w-7 h-7 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase mb-0.5">{a.category}</div>
          <div className="text-pb-text text-[14px] font-semibold leading-tight">{a.achievement}</div>
          {(a.subcategory || a.detail) && (
            <div className="font-mono text-[11px] text-pb-dim mt-0.5">
              {a.subcategory && <span>{a.subcategory}</span>}
              {a.detail && <span className="ml-1" style={{ color: 'var(--pb-accent)' }}>{a.detail}</span>}
            </div>
          )}
          <div className="font-mono text-[10px] text-pb-faint tracking-wide2 mt-1">{seasonRange(a)}</div>
        </div>
      </div>
      {canEdit && (
        <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={() => openEdit(a)} className="text-[10px] text-pb-faint hover:text-pb-text px-1.5 py-0.5 rounded hover:bg-pb-surface2">Edit</button>
          <button onClick={() => handleDelete(a.id)} className="text-[10px] text-pb-red hover:text-pb-red px-1.5 py-0.5 rounded hover:bg-pb-surface2">✕</button>
        </div>
      )}
    </div>
  )

  return (
    <div className="space-y-6">
      {canEdit && (
        <div className="flex justify-end">
          <Btn primary onClick={() => { setForm({ season: '', season_end: '', category: 'Club Award', subcategory: '', achievement: '', detail: '' }); setEditId(null); setAdding(true) }}>
            + Add Achievement
          </Btn>
        </div>
      )}

      {adding && (
        <Card title={editId ? 'EDIT ACHIEVEMENT' : 'ADD ACHIEVEMENT'}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <Label className="block mb-1">Category</Label>
              <select className={selectCls} value={form.category} onChange={e => { setForm(f => ({ ...f, category: e.target.value, subcategory: '', achievement: '' })); setCustomSubcat(false); setCustomAchievement(false) }}>
                {['Club Award','Association Award','Office Bearer','Premiership','Hall of Fame','Life Membership','Milestone'].map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <Label className="block mb-1">Season</Label>
              <select className={selectCls} value={form.season} onChange={e => setForm(f => ({ ...f, season: e.target.value }))}>
                <option value="">All Time</option>
                {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            {form.category === 'Office Bearer' && (
              <div>
                <Label className="block mb-1">Season End</Label>
                <select className={selectCls} value={form.season_end} onChange={e => setForm(f => ({ ...f, season_end: e.target.value }))}>
                  <option value="">Present</option>
                  {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            )}
            <div>
              <Label className="block mb-1">Subcategory</Label>
              {customSubcat
                ? <input className={inputCls} value={form.subcategory} onChange={e => setForm(f => ({ ...f, subcategory: e.target.value }))} placeholder="Subcategory" />
                : <select className={selectCls} value={form.subcategory} onChange={e => { if (e.target.value === '__other__') { setCustomSubcat(true); setForm(f => ({ ...f, subcategory: '' })) } else { setForm(f => ({ ...f, subcategory: e.target.value })) } }}>
                    <option value="">— none —</option>
                    {subcatOptions.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                    {subcatOptions.length > 0 && <option value="__other__">Other…</option>}
                  </select>
              }
            </div>
            <div>
              <Label className="block mb-1">Achievement *</Label>
              {customAchievement
                ? <input className={inputCls} value={form.achievement} onChange={e => setForm(f => ({ ...f, achievement: e.target.value }))} placeholder="Achievement" />
                : <select className={selectCls} value={form.achievement} onChange={e => { if (e.target.value === '__other__') { setCustomAchievement(true); setForm(f => ({ ...f, achievement: '' })) } else { setForm(f => ({ ...f, achievement: e.target.value })) } }}>
                    <option value="">— select —</option>
                    {achievementOptions.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                    <option value="__other__">Other…</option>
                  </select>
              }
            </div>
            <div>
              <Label className="block mb-1">Detail (optional)</Label>
              <input className={inputCls} value={form.detail} onChange={e => setForm(f => ({ ...f, detail: e.target.value }))} placeholder="e.g. #32, 436 runs at 39.64" />
            </div>
          </div>
          {formError && <p className="text-pb-red text-sm mt-2">{formError}</p>}
          <div className="flex gap-2 mt-4">
            <Btn primary onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : editId ? 'Update' : 'Save'}</Btn>
            <Btn onClick={() => { setAdding(false); setEditId(null) }}>Cancel</Btn>
          </div>
        </Card>
      )}

      {achievements.length === 0 && !adding && (
        <p className="text-pb-faint text-sm py-4">No achievements recorded yet.</p>
      )}

      {honours.length > 0 && (
        <div>
          <Label className="block mb-3">HONOURS</Label>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {honours.map(a => <AchievementCard key={a.id} a={a} accent />)}
          </div>
        </div>
      )}
      {rolesList.length > 0 && (
        <div>
          <Label className="block mb-3">ROLES</Label>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {rolesList.map((g, i) => {
              const seasons_str = g.instances.map(inst => formatSeasonShort(inst.season, seasons)).filter(Boolean).join(', ')
              return (
                <div key={i} className="relative group rounded border pb-hairline p-4 bg-pb-surface hover:bg-pb-surface2 transition-colors">
                  <div className="flex items-start gap-3">
                    <ThiingIcon src={CATEGORY_ICON_SRC['Office Bearer'] || thiings.necktie} alt="" className="w-7 h-7 shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase mb-0.5">Office Bearer</div>
                      <div className="text-pb-text text-[14px] font-semibold leading-tight">{g.achievement}</div>
                      {g.subcategory && <div className="font-mono text-[11px] text-pb-dim mt-0.5">{g.subcategory}</div>}
                      {seasons_str && <div className="font-mono text-[10px] text-pb-faint tracking-wide2 mt-1">{seasons_str}</div>}
                    </div>
                    <span className="font-mono text-[10px] text-pb-faintest shrink-0">{g.instances.length}×</span>
                  </div>
                  {canEdit && (
                    <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => openEdit(g.instances[0])} className="text-[10px] text-pb-faint hover:text-pb-text px-1.5 py-0.5 rounded hover:bg-pb-surface2">Edit</button>
                      <button onClick={() => handleDelete(g.instances[0].id)} className="text-[10px] text-pb-red px-1.5 py-0.5 rounded hover:bg-pb-surface2">✕</button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
      {awards.length > 0 && (
        <div>
          <Label className="block mb-3">AWARDS</Label>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {awards.map(a => <AchievementCard key={a.id} a={a} />)}
          </div>
        </div>
      )}
      {milestones.length > 0 && (
        <div>
          <Label className="block mb-3">MILESTONES</Label>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {milestones.map(a => <AchievementCard key={a.id} a={a} />)}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────
export default function PlayerProfile() {
  const { playerId } = useParams()
  const [seasonId, setSeasonId] = useState(null)
  const { data, loading, error } = usePlayerStats(playerId, { seasonId })
  const [org, setOrg] = useState(null)
  const [seasons, setSeasons] = useState([])
  const [seasonStats, setSeasonStats] = useState([])
  const [upcomingMilestones, setUpcomingMilestones] = useState([])
  const [milestones, setMilestones] = useState([])
  const [achievements, setAchievements] = useState([])
  const [dismissals, setDismissals] = useState([])
  const [partnerships, setPartnerships] = useState([])
  const [byGrade, setByGrade] = useState([])
  const [byPosition, setByPosition] = useState([])
  const [tab, setTab] = useState('batting')
  const [syncRequested, setSyncRequested] = useState(false)
  const [syncRequestLoading, setSyncRequestLoading] = useState(false)

  useClubTheme(org)

  useEffect(() => {
    if (!playerId) return
    api.getPlayerSeasons(playerId).then(setSeasonStats).catch(() => setSeasonStats([]))
    api.getPlayerUpcomingMilestones(playerId).then(setUpcomingMilestones).catch(() => setUpcomingMilestones([]))
  }, [playerId])

  useEffect(() => {
    if (!data?.player?.organisation_id) return
    const oid = data.player.organisation_id
    api.getOrgSeasons(oid).then(setSeasons).catch(() => {})
    api.getOrg(oid).then(setOrg).catch(() => {})
    api.listAchievements(oid, { playerId }).then(setAchievements).catch(() => setAchievements([]))
  }, [data?.player?.organisation_id, playerId])

  useEffect(() => {
    if (!data?.player || milestones.length > 0) return
    api.getPlayerMilestones(playerId).then(setMilestones).catch(() => setMilestones([]))
  }, [playerId, data?.player, milestones.length])

  useEffect(() => {
    if (!playerId || !data?.player) return
    if (partnerships.length > 0 || byGrade.length > 0) return
    Promise.allSettled([
      api.getPlayerPartnerships(playerId),
      api.getPlayerDismissals(playerId),
      api.getPlayerByGrade(playerId),
      api.getPlayerByPosition(playerId),
    ]).then(([p, d, g, pos]) => {
      if (p.status === 'fulfilled') setPartnerships(p.value)
      if (d.status === 'fulfilled') setDismissals(d.value)
      if (g.status === 'fulfilled') setByGrade(g.value)
      if (pos.status === 'fulfilled') setByPosition(pos.value)
    })
  }, [playerId, data?.player])

  if (loading) return <PbSpinner message="Loading player data…" />
  if (error) return <div className="max-w-7xl mx-auto px-4 py-16 text-pb-red">Error: {error}</div>
  if (!data?.player) return null

  const player = data.player
  const batting = data.career_batting
  const bowling = data.career_bowling
  const fielding = data.career_fielding
  const orgSlug = org ? (sessionStorage.getItem('bs_last_slug') || '') : ''

  // Ranked achievements for the header badges
  const headerAchievements = (() => {
    const map = new Map()
    for (const a of achievements) {
      const key = `${a.category}|${a.subcategory || ''}|${a.achievement}`
      if (!map.has(key)) map.set(key, { ...a, _instances: [a] })
      else {
        const cur = map.get(key); cur._instances.push(a)
        if ((a.season || '') > (cur.season || '')) Object.assign(cur, a, { _instances: cur._instances })
      }
    }
    for (const g of map.values()) g._instances.sort((x, y) => (x.season||'').localeCompare(y.season||''))
    return [...map.values()].sort((a, b) => {
      const diff = headerPriority(a) - headerPriority(b)
      return diff || (b.season||'').localeCompare(a.season||'')
    }).slice(0, 6)
  })()

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 font-mono text-[10.5px] tracking-wide2 text-pb-faint mb-4">
          {orgSlug && <Link to={`/${orgSlug}/players`} className="hover:text-pb-text">PLAYERS</Link>}
          {orgSlug && <span>/</span>}
          <span className="text-pb-dim">{player.name.toUpperCase()}</span>
        </div>

        {/* Hero */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-6 mb-6 items-end">
          <div>
            <Label>{org?.name || ''} · {player.role || 'PLAYER'}</Label>
            <h1 className="font-display text-[48px] sm:text-[72px] font-bold tracking-tight leading-[0.92] mt-1.5 text-pb-text">
              {player.name}
            </h1>
            {/* Header achievement badges */}
            {headerAchievements.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {headerAchievements.map(a => (
                  <span key={a.id} className="font-mono text-[10px] tracking-wide2 px-2.5 py-1 rounded-sm border text-[11px]" style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 40%, transparent)', color: 'var(--pb-accent)', background: 'color-mix(in srgb, var(--pb-accent) 10%, transparent)' }}>
                    {formatAchievementBadge(a, seasons)}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex gap-2 flex-wrap">
            {orgSlug && (
              <Link to={`/${orgSlug}/compare?playerA=${playerId}`}>
                <Btn>Compare</Btn>
              </Link>
            )}
            <Link to={`/players/${playerId}/share`}><Btn>Share card</Btn></Link>
            <Btn primary onClick={async () => {
              if (syncRequested || syncRequestLoading) return
              setSyncRequestLoading(true)
              try { await api.requestPlayerSync(playerId) } catch {}
              setSyncRequested(true); setSyncRequestLoading(false)
            }}>
              {syncRequestLoading ? 'Requesting…' : syncRequested ? '✓ Requested' : 'Sync player'}
            </Btn>
          </div>
        </div>

        {/* Season selector */}
        {seasons.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 mb-5">
            <Label>SEASON</Label>
            <select
              value={seasonId || ''}
              onChange={e => setSeasonId(e.target.value || null)}
              className="bg-pb-surface border border-pb-hairline2 text-pb-text text-[11px] font-mono rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent cursor-pointer"
            >
              <option value="">All Seasons</option>
              {seasons.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
        )}

        {/* Quick stat strip */}
        {(batting || bowling || fielding) && (
          <div className="space-y-3 mb-6">
            {/* Row 1 — Matches */}
            <div className="pb-card p-4 flex items-center gap-4">
              <div>
                <Label>MATCHES</Label>
                <span className="font-mono text-[36px] font-bold pb-num leading-none mt-1 text-pb-text">
                  <AnimatedNum value={batting?.games || bowling?.games || 0} />
                </span>
              </div>
            </div>

            {/* Row 2 — Batting */}
            {batting && (
              <div>
                <div className="font-mono text-[9px] tracking-wide3 text-pb-faintest mb-2 px-0.5">BATTING</div>
                <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>INNINGS</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1 text-pb-text">
                      <AnimatedNum value={batting.innings || 0} />
                    </span>
                  </div>
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>RUNS</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1" style={{ color: 'var(--pb-accent)' }}>
                      <AnimatedNum value={batting.total_runs || 0} />
                    </span>
                  </div>
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>AVG</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1 text-pb-text">
                      {batting.average != null ? Number(batting.average).toFixed(2) : '—'}
                    </span>
                  </div>
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>HIGH SCORE</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1 text-pb-text">
                      {batting.high_score ?? '—'}
                    </span>
                  </div>
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>50s</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1 text-pb-text">
                      {batting.fifties ?? '—'}
                    </span>
                  </div>
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>100s</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1" style={{ color: batting.hundreds > 0 ? 'var(--pb-amber)' : undefined }}>
                      {batting.hundreds ?? '—'}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Row 3 — Bowling + Fielding */}
            <div>
              <div className="font-mono text-[9px] tracking-wide3 text-pb-faintest mb-2 px-0.5">BOWLING & FIELDING</div>
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                {bowling && (<>
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>WICKETS</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1" style={{ color: 'var(--pb-accent)' }}>
                      <AnimatedNum value={bowling.total_wickets || 0} />
                    </span>
                  </div>
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>AVG</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1 text-pb-text">
                      {bowling.average != null ? Number(bowling.average).toFixed(2) : '—'}
                    </span>
                  </div>
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>ECON</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1 text-pb-text">
                      {bowling.economy != null ? Number(bowling.economy).toFixed(2) : '—'}
                    </span>
                  </div>
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>BEST</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1 text-pb-text">
                      {bowling.best_bowling_figures || (bowling.best_figures_wickets != null ? `${bowling.best_figures_wickets}w` : '—')}
                    </span>
                  </div>
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>5-FORS</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1 text-pb-text">
                      {bowling.five_fors ?? '—'}
                    </span>
                  </div>
                </>)}
                {fielding && (
                  <div className="pb-card p-3 flex flex-col gap-1">
                    <Label>DISMISSALS</Label>
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1 text-pb-text">
                      {fielding.total_dismissals ?? '—'}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Tabs */}
        <TabBar tabs={MAIN_TABS} active={tab} onChange={setTab} />

        {/* Tab content */}
        {tab === 'batting' && <BattingTab batting={batting} seasonStats={seasonStats} seasons={seasons} />}
        {tab === 'bowling' && <BowlingTab bowling={bowling} seasonStats={seasonStats} />}
        {tab === 'fielding' && <FieldingTab fielding={fielding} seasonStats={seasonStats} />}
        {tab === 'analysis' && <AnalysisTab playerId={playerId} dismissals={dismissals} partnerships={partnerships} byGrade={byGrade} byPosition={byPosition} seasonStats={seasonStats} />}
        {tab === 'milestones' && <MilestonesTab playerId={playerId} upcomingMilestones={upcomingMilestones} milestones={milestones} />}
        {tab === 'achievements' && <AchievementsSection playerId={playerId} orgId={player.organisation_id} playerName={player.name} />}
      </main>
    </div>
  )
}
