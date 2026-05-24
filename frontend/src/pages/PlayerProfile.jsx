import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import { useClubTheme } from '../hooks/useClubTheme'
import { useNameFormat } from '../lib/nameFormat'
import { usePageMeta } from '../hooks/usePageMeta'
import { getSubcategoriesFromDefs, getAchievementsFromDefs, resolveAwardLabel } from '../lib/achievementOptions'
import { usePlayerStats } from '../hooks/usePlayerStats'
import { CATEGORY_ICON_SRC, MILESTONE_ICON_SRC, ThiingIcon, thiings } from '../assets/thiings'
import {
  AnimatedNum, Sparkline, Label, Card, Btn,
  ResultPill, PageHeader, PbSpinner, TabBar,
} from '../lib/presskit'
import '../styles/honour-badge.css'
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
  if (dec) return Number(val).toFixed(2)
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

function formatAchievementBadge(a, seasons, awardDefs) {
  const label = resolveAwardLabel(awardDefs, a.category, a.subcategory, a.achievement) || a.subcategory || a.category
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
  if (a.category === 'Club Award' && a.subcategory === 'Perpetual') return 3.5
  if (a.category === "Club Award" && a.subcategory === "Women's Perpetual") return 3.5
  if (a.category === 'Association Award') return 6
  if (a.category === 'Club Award') return 7
  if (a.category === 'Office Bearer') return 8
  return 99
}

// Classifies an achievement into a colour category. Keys match the
// --pb-cat-* theme variables and the HonourBadge `theme` prop.
function achievementType(a) {
  if (['Hall of Fame', 'Life Membership', 'Premiership'].includes(a.category) ||
      (a.category === 'Milestone' && a.subcategory === 'Cap Number')) return 'honour'
  if (a.category === 'Office Bearer') return 'role'
  if (a.category === 'Milestone') return 'milestone'
  return 'award'
}

// White-labelled badge styling — derives every shade from one --pb-cat-* var.
function badgeVars(type) {
  const c = `var(--pb-cat-${['honour', 'role', 'award', 'milestone'].includes(type) ? type : 'award'})`
  return {
    '--hb-accent-text':  c,
    '--hb-border':       `color-mix(in srgb, ${c} 30%, transparent)`,
    '--hb-border-hover': `color-mix(in srgb, ${c} 70%, transparent)`,
    '--hb-icon-bg':      `color-mix(in srgb, ${c} 15%, transparent)`,
    '--hb-wash':         `linear-gradient(135deg, color-mix(in srgb, ${c} 6%, transparent) 0%, transparent 60%)`,
    '--hb-shadow-b':     `color-mix(in srgb, ${c} 12%, transparent)`,
  }
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
const PIE_COLORS = ['var(--pb-chart-1)', 'var(--pb-chart-2)', 'var(--pb-chart-3)', 'var(--pb-chart-4)', 'var(--pb-chart-5)', 'var(--pb-chart-6)', 'var(--pb-chart-7)', 'var(--pb-chart-8)']

const CHART_TOOLTIP_STYLE = {
  contentStyle: { background: 'var(--pb-surface)', border: '1px solid var(--pb-hairline2)', borderRadius: 8, fontSize: 12 },
  labelStyle: { color: 'var(--pb-dim)' },
  itemStyle: { color: 'var(--pb-text)' },
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
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" />
        <XAxis dataKey="season_name" tick={{ fill: 'var(--pb-faint)', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis yAxisId="left" tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} />
        <YAxis yAxisId="right" orientation="right" tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} />
        <Tooltip {...CHART_TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ color: 'var(--pb-dim)', fontSize: 12 }} />
        <Bar yAxisId="left" dataKey="total_runs" name="Runs" fill="var(--pb-chart-runs, #16c784)" radius={[3,3,0,0]} />
        <Bar yAxisId="right" dataKey="total_wickets" name="Wickets" fill="var(--pb-chart-wickets, #3b82f6)" radius={[3,3,0,0]} />
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
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" />
        <XAxis dataKey="season" tick={{ fill: 'var(--pb-faint)', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} />
        <Tooltip {...CHART_TOOLTIP_STYLE} formatter={(v, name) => [v.toLocaleString(), name === 'total' ? 'Career total' : 'Season runs']} />
        <Bar dataKey="season_runs" name="season_runs" fill="var(--pb-chart-runs, #16c784)" fillOpacity={0.25} radius={[2,2,0,0]} />
        <Line type="monotone" dataKey="total" name="total" stroke="var(--pb-accent, #16c784)" strokeWidth={2} dot={false} />
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
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" />
        <XAxis dataKey="season" tick={{ fill: 'var(--pb-faint)', fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} />
        <Tooltip {...CHART_TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ color: 'var(--pb-dim)', fontSize: 12 }} />
        <Line type="monotone" dataKey="bat_avg" name="Batting Avg" stroke="var(--pb-accent, #16c784)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
        <Line type="monotone" dataKey="bowl_avg" name="Bowling Avg" stroke="var(--pb-chart-wickets, #3b82f6)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
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
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" horizontal={false} />
        <XAxis type="number" tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} />
        <YAxis type="category" dataKey="grade_name" width={130} tick={{ fill: 'var(--pb-dim)', fontSize: 11 }} />
        <Tooltip {...CHART_TOOLTIP_STYLE} formatter={(v, _, props) => [`${v} runs (${props.payload.innings} inn, avg ${props.payload.average ?? '—'})`, '']} />
        <Bar dataKey="runs" fill="var(--pb-chart-runs, #16c784)" radius={[0,3,3,0]} label={{ position: 'right', fill: 'var(--pb-faint)', fontSize: 11 }} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function WicketsByGradeChart({ bowlingByGrade }) {
  if (!bowlingByGrade?.length) return null
  const sorted = [...bowlingByGrade].sort((a, b) => b.wickets - a.wickets).slice(0, 10)
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, sorted.length * 36)}>
      <BarChart data={sorted} layout="vertical" margin={{ top: 5, right: 60, left: 8, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" horizontal={false} />
        <XAxis type="number" tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} />
        <YAxis type="category" dataKey="grade_name" width={130} tick={{ fill: 'var(--pb-dim)', fontSize: 11 }} />
        <Tooltip {...CHART_TOOLTIP_STYLE} formatter={(v, _, props) => [`${v} wkts (avg ${props.payload.average ?? '—'}, econ ${props.payload.economy ?? '—'})`, '']} />
        <Bar dataKey="wickets" fill="var(--pb-chart-wickets, #3b82f6)" radius={[0,3,3,0]} label={{ position: 'right', fill: 'var(--pb-faint)', fontSize: 11 }} />
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
            ['CATCHES', fielding.total_catches_non_wk ?? fielding.total_catches, true],
            ['CATCHES (WK)', fielding.total_catches_wk],
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
            <table className="w-full min-w-[480px] text-[13px]">
              <thead className="text-pb-faint font-mono text-[10px] tracking-wide3">
                <tr>
                  <th className="py-3 pl-5 text-left pb-2">SEASON</th>
                  <SortTh label="CATCHES" sKey="total_catches_non_wk" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="CT (WK)" sKey="total_catches_wk" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="RUN OUTS" sKey="total_run_outs" cur={sortKey} dir={sortDir} onSort={request} right />
                  <th className="py-3 pr-5 text-right pb-2 font-mono text-[10px] tracking-wide3">STUMPINGS</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((s, i) => (
                  <tr key={s.season_name || i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 pl-5 font-mono text-pb-dim text-[12px]">{s.season_name}</td>
                    <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{fmt(s.total_catches_non_wk ?? (s.total_catches - (s.total_catches_wk ?? 0)))}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.total_catches_wk)}</td>
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

// ── Career progression charts ────────────────────────────────────────────

// Running career batting average progression — one point per innings, chronological
function CareerAvgProgressionChart({ innings }) {
  if (!innings?.length) return null
  // innings arrives DESC, reverse to chronological ASC
  const asc = [...innings].reverse()
  let totalRuns = 0, dismissals = 0
  const points = asc.map((inn, i) => {
    totalRuns += (inn.runs ?? 0)
    if (!inn.not_out) dismissals++
    return {
      i: i + 1,
      avg: dismissals > 0 ? Math.round((totalRuns / dismissals) * 100) / 100 : null,
      runs: inn.runs,
      label: inn.played_at ? new Date(inn.played_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: '2-digit' }) : `#${i + 1}`,
    }
  })
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" />
        <XAxis dataKey="i" tick={{ fontSize: 10, fill: 'var(--pb-faint)', fontFamily: 'monospace' }} label={{ value: 'Innings', position: 'insideBottom', offset: -2, fontSize: 10, fill: 'var(--pb-faint)' }} />
        <YAxis tick={{ fontSize: 10, fill: 'var(--pb-faint)', fontFamily: 'monospace' }} width={36} />
        <Tooltip
          contentStyle={{ background: 'var(--pb-surface)', border: '1px solid var(--pb-hairline)', borderRadius: 6, fontSize: 11 }}
          formatter={(v) => [v != null ? v.toFixed(2) : '—', 'Average']}
          labelFormatter={(i) => points[i - 1] ? `Inn #${i} — ${points[i - 1].label} (${points[i - 1].runs})` : `Inn #${i}`}
        />
        <Line type="monotone" dataKey="avg" stroke="var(--pb-accent)" dot={false} strokeWidth={2} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  )
}

// Score distribution histogram
function ScoreDistributionChart({ innings }) {
  if (!innings?.length) return null
  const bands = [
    { label: '0–14', min: 0, max: 14 },
    { label: '15–29', min: 15, max: 29 },
    { label: '30–49', min: 30, max: 49 },
    { label: '50–64', min: 50, max: 64 },
    { label: '65–79', min: 65, max: 79 },
    { label: '80–99', min: 80, max: 99 },
    { label: '100+', min: 100, max: Infinity },
  ]
  const data = bands.map(b => ({
    label: b.label,
    count: innings.filter(i => (i.runs ?? 0) >= b.min && (i.runs ?? 0) <= b.max).length,
    highlight: b.min >= 50,
  }))
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'var(--pb-faint)', fontFamily: 'monospace' }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: 'var(--pb-faint)', fontFamily: 'monospace' }} width={28} />
        <Tooltip
          contentStyle={{ background: 'var(--pb-surface)', border: '1px solid var(--pb-hairline)', borderRadius: 6, fontSize: 11 }}
          formatter={(v) => [v, 'Innings']}
        />
        <Bar dataKey="count" radius={[3, 3, 0, 0]} fill="var(--pb-chart-runs, #16c784)" />
      </BarChart>
    </ResponsiveContainer>
  )
}

// Running career bowling average + economy progression
function CareerBowlingProgressionChart({ spells }) {
  if (!spells?.length) return null
  const asc = [...spells].reverse()
  let totalRuns = 0, totalWickets = 0, totalOvers = 0
  const points = asc.map((s, i) => {
    totalRuns += (s.runs ?? 0)
    totalWickets += (s.wickets ?? 0)
    totalOvers += parseFloat(s.overs ?? 0)
    return {
      i: i + 1,
      avg: totalWickets > 0 ? Math.round((totalRuns / totalWickets) * 100) / 100 : null,
      econ: totalOvers > 0 ? Math.round((totalRuns / totalOvers) * 100) / 100 : null,
    }
  })
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" />
        <XAxis dataKey="i" tick={{ fontSize: 10, fill: 'var(--pb-faint)', fontFamily: 'monospace' }} label={{ value: 'Spells', position: 'insideBottom', offset: -2, fontSize: 10, fill: 'var(--pb-faint)' }} />
        <YAxis tick={{ fontSize: 10, fill: 'var(--pb-faint)', fontFamily: 'monospace' }} width={36} />
        <Tooltip
          contentStyle={{ background: 'var(--pb-surface)', border: '1px solid var(--pb-hairline)', borderRadius: 6, fontSize: 11 }}
          formatter={(v, name) => [v != null ? v.toFixed(2) : '—', name]}
        />
        <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'monospace' }} />
        <Line type="monotone" dataKey="avg" name="Average" stroke="var(--pb-accent)" dot={false} strokeWidth={2} connectNulls />
        <Line type="monotone" dataKey="econ" name="Economy" stroke="var(--pb-chart-milestone, #f5b542)" dot={false} strokeWidth={2} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  )
}

// ── Innings / Spell history tables ───────────────────────────────────────

function InningsHistoryTable({ innings }) {
  return (
    <div className="overflow-x-auto pb-scroll">
      <table className="w-full min-w-[560px] text-[13px]">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3">
            <th className="py-3 pl-5 text-left pb-2">DATE</th>
            <th className="py-3 text-left pb-2">MATCH</th>
            <th className="py-3 text-left pb-2">GRADE</th>
            <th className="py-3 text-right pb-2">INN</th>
            <th className="py-3 text-right pb-2">R</th>
            <th className="py-3 text-right pb-2">B</th>
            <th className="py-3 text-right pb-2">SR</th>
            <th className="py-3 pr-5 text-right pb-2">HO</th>
          </tr>
        </thead>
        <tbody>
          {innings.map((row, i) => {
            const dateStr = row.played_at ? new Date(row.played_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: '2-digit' }) : '—'
            const match = row.home_team && row.away_team ? `${row.home_team} vs ${row.away_team}` : (row.home_team || row.away_team || '—')
            const ho = row.not_out ? 'not out' : (row.dismissal_type || '—')
            return (
              <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                <td className="py-2.5 pl-5 font-mono text-[11px] text-pb-faint whitespace-nowrap">
                  {row.game_id
                    ? <Link to={`/games/${row.game_id}`} className="hover:text-pb-accent transition-colors">{dateStr}</Link>
                    : dateStr}
                </td>
                <td className="py-2.5 font-mono text-[11px] text-pb-dim max-w-[180px] truncate">{match}</td>
                <td className="py-2.5 font-mono text-[11px] text-pb-faint">{row.grade_name || '—'}</td>
                <td className="py-2.5 font-mono text-[11px] text-pb-faint text-right">{row.innings_number ?? '—'}</td>
                <td className="py-2.5 text-right">
                  <span className="font-mono font-bold text-sm" style={{ color: (row.runs ?? 0) >= 100 ? 'var(--pb-chart-milestone, #f5b542)' : (row.runs ?? 0) >= 50 ? 'var(--pb-accent)' : 'var(--pb-text)' }}>
                    {row.runs ?? '—'}
                  </span>
                  {row.not_out && <span className="font-mono text-[10px] ml-0.5" style={{ color: 'var(--pb-accent)' }}>*</span>}
                </td>
                <td className="py-2.5 font-mono text-sm text-pb-dim text-right">{row.balls ?? '—'}</td>
                <td className="py-2.5 font-mono text-[11px] text-pb-faint text-right">{row.strike_rate != null ? Number(row.strike_rate).toFixed(2) : '—'}</td>
                <td className="py-2.5 pr-5 font-mono text-[11px] text-pb-faint text-right capitalize">{ho}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function SpellHistoryTable({ spells }) {
  return (
    <div className="overflow-x-auto pb-scroll">
      <table className="w-full min-w-[520px] text-[13px]">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3">
            <th className="py-3 pl-5 text-left pb-2">DATE</th>
            <th className="py-3 text-left pb-2">MATCH</th>
            <th className="py-3 text-left pb-2">GRADE</th>
            <th className="py-3 text-right pb-2">O</th>
            <th className="py-3 text-right pb-2">M</th>
            <th className="py-3 text-right pb-2">R</th>
            <th className="py-3 text-right pb-2">W</th>
            <th className="py-3 pr-5 text-right pb-2">ECON</th>
          </tr>
        </thead>
        <tbody>
          {spells.map((row, i) => {
            const dateStr = row.played_at ? new Date(row.played_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: '2-digit' }) : '—'
            const match = row.home_team && row.away_team ? `${row.home_team} vs ${row.away_team}` : (row.home_team || row.away_team || '—')
            return (
              <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                <td className="py-2.5 pl-5 font-mono text-[11px] text-pb-faint whitespace-nowrap">
                  {row.game_id
                    ? <Link to={`/games/${row.game_id}`} className="hover:text-pb-accent transition-colors">{dateStr}</Link>
                    : dateStr}
                </td>
                <td className="py-2.5 font-mono text-[11px] text-pb-dim max-w-[180px] truncate">{match}</td>
                <td className="py-2.5 font-mono text-[11px] text-pb-faint">{row.grade_name || '—'}</td>
                <td className="py-2.5 font-mono text-sm text-pb-dim text-right">{row.overs ?? '—'}</td>
                <td className="py-2.5 font-mono text-[11px] text-pb-faint text-right">{row.maidens ?? '—'}</td>
                <td className="py-2.5 font-mono text-sm text-pb-dim text-right">{row.runs ?? '—'}</td>
                <td className="py-2.5 text-right">
                  <span className="font-mono font-bold text-sm" style={{ color: (row.wickets ?? 0) >= 5 ? 'var(--pb-chart-milestone, #f5b542)' : (row.wickets ?? 0) >= 3 ? 'var(--pb-accent)' : 'var(--pb-text)' }}>
                    {row.wickets ?? '—'}
                  </span>
                </td>
                <td className="py-2.5 pr-5 font-mono text-[11px] text-pb-faint text-right">{row.economy != null ? Number(row.economy).toFixed(2) : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Analysis tab ─────────────────────────────────────────────────────────
const ANALYSIS_SUBTABS = [
  { key: 'batting',  label: 'BATTING' },
  { key: 'bowling',  label: 'BOWLING' },
  { key: 'team',     label: 'TEAM' },
  { key: 'captain',  label: 'CAPTAIN' },
  { key: 'venue',    label: 'VENUE' },
  { key: 'opposition', label: 'OPPOSITION' },
]

function CaptainTab({ captainStats }) {
  if (!captainStats) {
    return <div className="p-4 text-pb-faint font-mono text-sm">Loading captain stats…</div>
  }

  const { summary, batting_as_captain, batting_not_captain, bowling_as_captain, bowling_not_captain, by_season } = captainStats

  if (!summary?.games_captained) {
    return <div className="p-4 text-pb-faint font-mono text-sm">No captain data available.</div>
  }

  const winPct = summary.games_captained > 0
    ? Math.round((summary.wins / summary.games_captained) * 100)
    : 0

  const fmtV = v => v == null ? '—' : v

  return (
    <div className="space-y-8 p-4">
      {/* Summary */}
      <div className="flex gap-6 flex-wrap">
        <div>
          <div className="font-mono text-2xl text-pb-text">{summary.games_captained}</div>
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mt-0.5">Games as captain</div>
        </div>
        <div>
          <div className="font-mono text-2xl text-pb-text">{summary.wins}W / {summary.losses}L / {summary.draws}D</div>
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mt-0.5">Win / Loss / Draw  ·  {winPct}% win rate</div>
        </div>
      </div>

      {/* Batting comparison */}
      <div>
        <div className="font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-3">Batting</div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] text-[13px]">
            <thead>
              <tr className="border-b pb-hairline-b">
                <th className="text-left font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 pr-4"></th>
                <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Inn</th>
                <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Runs</th>
                <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Avg</th>
                <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">HS</th>
                <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">50s</th>
                <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">100s</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="py-2.5 pr-4 font-mono text-pb-text font-semibold text-[12px] whitespace-nowrap">As captain</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-text">{fmtV(batting_as_captain?.innings)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-text">{fmtV(batting_as_captain?.runs)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-text">{fmtV(batting_as_captain?.average)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-text">{fmtV(batting_as_captain?.high_score)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-text">{fmtV(batting_as_captain?.fifties)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-text">{fmtV(batting_as_captain?.hundreds)}</td>
              </tr>
              <tr className="border-t pb-hairline-t">
                <td className="py-2.5 pr-4 font-mono text-pb-dim text-[12px] whitespace-nowrap">Not captain</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-dim">{fmtV(batting_not_captain?.innings)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-dim">{fmtV(batting_not_captain?.runs)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-dim">{fmtV(batting_not_captain?.average)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-dim">{fmtV(batting_not_captain?.high_score)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-dim">{fmtV(batting_not_captain?.fifties)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-dim">{fmtV(batting_not_captain?.hundreds)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Bowling comparison */}
      <div>
        <div className="font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-3">Bowling</div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[380px] text-[13px]">
            <thead>
              <tr className="border-b pb-hairline-b">
                <th className="text-left font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 pr-4"></th>
                <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Games</th>
                <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Wkts</th>
                <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Avg</th>
                <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Econ</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="py-2.5 pr-4 font-mono text-pb-text font-semibold text-[12px] whitespace-nowrap">As captain</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-text">{fmtV(bowling_as_captain?.games)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-text">{fmtV(bowling_as_captain?.wickets)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-text">{fmtV(bowling_as_captain?.average)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-text">{fmtV(bowling_as_captain?.economy)}</td>
              </tr>
              <tr className="border-t pb-hairline-t">
                <td className="py-2.5 pr-4 font-mono text-pb-dim text-[12px] whitespace-nowrap">Not captain</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-dim">{fmtV(bowling_not_captain?.games)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-dim">{fmtV(bowling_not_captain?.wickets)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-dim">{fmtV(bowling_not_captain?.average)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-pb-dim">{fmtV(bowling_not_captain?.economy)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Season by season */}
      {by_season?.length > 0 && (
        <div>
          <div className="font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-3">By season as captain</div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[600px] text-[13px]">
              <thead>
                <tr className="border-b pb-hairline-b">
                  <th className="text-left font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 pr-4">Season</th>
                  <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">G</th>
                  <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">W/L/D</th>
                  <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Bat Inn</th>
                  <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Runs</th>
                  <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Bat Avg</th>
                  <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Wkts</th>
                  <th className="text-right font-mono text-pb-faint text-[11px] tracking-wide2 py-1.5 px-2">Bowl Avg</th>
                </tr>
              </thead>
              <tbody>
                {by_season.map((row, i) => (
                  <tr key={i} className={i % 2 === 1 ? 'bg-pb-surface' : ''}>
                    <td className="py-2 pr-4 font-mono text-pb-text text-[12px]">{row.season_name}</td>
                    <td className="py-2 px-2 text-right font-mono text-pb-dim">{row.games_captained}</td>
                    <td className="py-2 px-2 text-right font-mono text-pb-dim">{row.wins}/{row.losses}/{row.draws}</td>
                    <td className="py-2 px-2 text-right font-mono text-pb-dim">{fmtV(row.batting_innings)}</td>
                    <td className="py-2 px-2 text-right font-mono text-pb-dim">{fmtV(row.batting_runs)}</td>
                    <td className="py-2 px-2 text-right font-mono text-pb-dim">{fmtV(row.batting_avg)}</td>
                    <td className="py-2 px-2 text-right font-mono text-pb-dim">{fmtV(row.bowling_wickets)}</td>
                    <td className="py-2 px-2 text-right font-mono text-pb-dim">{fmtV(row.bowling_avg)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function AnalysisTab({ playerId, dismissals, partnerships, byGrade, byPosition, seasonStats, bowlingByGrade, bowlingDismissals = [], bowlingByBatterPosition = [], battingInnings = [], bowlingSpells = [], teamBreakdown = { rows: [], unattributed: 0 }, seasonLabel = null, captainStats, byVenue = [], byOpposition = [] }) {
  const [subTab, setSubTab] = useState('batting')

  const hasBattingData = dismissals?.length || partnerships?.length || byGrade?.length || byPosition?.length || seasonStats?.some(s => (s.total_runs ?? 0) > 0)
  const hasBowlingData = bowlingByGrade?.length || bowlingDismissals?.length || bowlingByBatterPosition?.some(p => (p.wickets ?? 0) > 0) || seasonStats?.some(s => (s.total_wickets ?? 0) > 0)

  return (
    <div className="space-y-6">
      {/* Sub-tab navigation */}
      <div className="flex gap-0 border-b border-pb-hairline">
        {ANALYSIS_SUBTABS.map(t => (
          <button
            key={t.key}
            onClick={() => setSubTab(t.key)}
            className={`relative px-4 py-2.5 text-[11px] font-mono font-semibold tracking-wide3 transition ${
              subTab === t.key ? 'text-pb-text' : 'text-pb-faint hover:text-pb-dim'
            }`}
          >
            {t.label}
            {subTab === t.key && <span className="absolute left-2 right-2 -bottom-px h-[2px]" style={{ background: 'var(--pb-accent)' }} />}
          </button>
        ))}
      </div>

      {subTab === 'batting' && (
        <div className="space-y-6">
          {/* Career average progression */}
          {battingInnings.length > 5 && (
            <Card title="CAREER BATTING AVERAGE PROGRESSION">
              <p className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-3">Running career average after each innings, chronological.</p>
              <CareerAvgProgressionChart innings={battingInnings} />
            </Card>
          )}

          {/* Score distribution */}
          {battingInnings.length > 0 && (
            <Card title="SCORE DISTRIBUTION">
              <p className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-3">How often scores fall in each run band.</p>
              <ScoreDistributionChart innings={battingInnings} />
            </Card>
          )}

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

          {/* Innings history */}
          {battingInnings.length > 0 && (
            <Card title="INNINGS HISTORY" pad="p-0">
              <InningsHistoryTable innings={battingInnings} />
            </Card>
          )}

          {!hasBattingData && (
            <p className="text-pb-faint text-sm py-4">No batting analysis data available. Game-level data may still be syncing.</p>
          )}
        </div>
      )}

      {subTab === 'bowling' && (
        <div className="space-y-6">
          {/* Wickets by season */}
          {seasonStats?.some(s => (s.total_wickets ?? 0) > 0) && (
            <Card title="WICKETS BY SEASON">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={[...seasonStats].reverse()} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" />
                  <XAxis dataKey="season_name" tick={{ fill: 'var(--pb-faint)', fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} />
                  <Tooltip {...CHART_TOOLTIP_STYLE} />
                  <Bar dataKey="total_wickets" name="Wickets" fill="var(--pb-chart-wickets, #3b82f6)" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          )}

          {/* How I take wickets — bowler-method-of-dismissal donut */}
          {bowlingDismissals?.length > 0 && (
            <Card title="HOW I TAKE WICKETS">
              <DismissalDonut dismissals={bowlingDismissals} />
            </Card>
          )}

          {/* Wickets by batter's batting position 1-11 */}
          {bowlingByBatterPosition?.some(p => (p.wickets ?? 0) > 0) && (
            <Card title="WICKETS BY BATTING POSITION DISMISSED">
              <p className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-3">The batting position of the batters you've dismissed — are most of your wickets openers or tail-enders?</p>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={bowlingByBatterPosition} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" />
                  <XAxis dataKey="batting_position" tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} tickFormatter={(v) => `#${v}`} />
                  <YAxis tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} allowDecimals={false} />
                  <Tooltip {...CHART_TOOLTIP_STYLE} labelFormatter={(v) => `Position #${v}`} formatter={(v) => [v, 'Wickets']} />
                  <Bar dataKey="wickets" name="Wickets" fill="var(--pb-chart-wickets, #3b82f6)" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          )}

          {/* Career bowling progression */}
          {bowlingSpells.length > 5 && (
            <Card title="CAREER BOWLING PROGRESSION">
              <p className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-3">Running career bowling average and economy after each spell, chronological.</p>
              <CareerBowlingProgressionChart spells={bowlingSpells} />
            </Card>
          )}

          {/* Bowling averages over time */}
          {seasonStats?.some(s => s.bowling_average != null) && (
            <Card title="BOWLING AVERAGE & ECONOMY OVER TIME">
              <p className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-3">Bowling average and economy rate season by season.</p>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart
                  data={[...seasonStats].reverse().filter(s => s.bowling_average != null || s.economy != null).map(s => ({
                    season: s.season_name?.replace('Summer ', '') ?? '',
                    bowl_avg: s.bowling_average != null ? Number(Number(s.bowling_average).toFixed(1)) : null,
                    economy: s.economy != null ? Number(Number(s.economy).toFixed(2)) : null,
                  }))}
                  margin={{ top: 5, right: 10, left: 0, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline)" />
                  <XAxis dataKey="season" tick={{ fill: 'var(--pb-faint)', fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: 'var(--pb-faint)', fontSize: 11 }} />
                  <Tooltip {...CHART_TOOLTIP_STYLE} />
                  <Legend wrapperStyle={{ color: 'var(--pb-dim)', fontSize: 12 }} />
                  <Line type="monotone" dataKey="bowl_avg" name="Bowling Avg" stroke="var(--pb-chart-wickets, #3b82f6)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                  <Line type="monotone" dataKey="economy" name="Economy" stroke="var(--pb-chart-milestone, #f5b542)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}

          {/* Wickets by grade chart */}
          {bowlingByGrade?.length > 1 && (
            <Card title="WICKETS BY GRADE">
              <p className="font-mono text-[10px] text-pb-faint tracking-wide2 mb-3">Career bowling wickets broken down by grade.</p>
              <WicketsByGradeChart bowlingByGrade={bowlingByGrade} />
            </Card>
          )}

          {/* Bowling by grade table */}
          {bowlingByGrade?.length > 0 && (
            <Card title="BOWLING BY GRADE" pad="p-0">
              <div className="overflow-x-auto pb-scroll">
                <table className="w-full min-w-[500px] text-[13px]">
                  <thead>
                    <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                      <th className="py-3 pl-5 pb-2">GRADE</th>
                      <th className="py-3 text-right pb-2">WKTS</th>
                      <th className="py-3 text-right pb-2">OV</th>
                      <th className="py-3 text-right pb-2">AVG</th>
                      <th className="py-3 text-right pb-2">ECON</th>
                      <th className="py-3 pr-5 text-right pb-2">BEST</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bowlingByGrade.map((r, i) => (
                      <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                        <td className="py-2.5 pl-5 text-pb-text">{r.grade_name}</td>
                        <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{r.wickets}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{r.total_overs != null ? Number(r.total_overs).toFixed(1) : '—'}</td>
                        <td className="py-2.5 font-mono text-pb-text text-right">{fmt(r.average, true)}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(r.economy, true)}</td>
                        <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">
                          {r.best_wickets != null ? `${r.best_wickets}/${r.best_runs ?? '?'}` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Spell history */}
          {bowlingSpells.length > 0 && (
            <Card title="SPELL HISTORY" pad="p-0">
              <SpellHistoryTable spells={bowlingSpells} />
            </Card>
          )}

          {!hasBowlingData && (
            <p className="text-pb-faint text-sm py-4">No bowling analysis data available. Game-level data may still be syncing.</p>
          )}
        </div>
      )}

      {subTab === 'captain' && <CaptainTab captainStats={captainStats} />}

      {subTab === 'venue' && (
        <div className="space-y-6">
          {byVenue.length > 0 ? (
            <Card title="STATS BY VENUE" pad="p-0">
              <p className="font-mono text-[10px] text-pb-faint tracking-wide2 px-5 pt-4 pb-2">Performance at each ground across all seasons.</p>
              <div className="overflow-x-auto pb-scroll">
                <table className="w-full min-w-[860px] text-[13px]">
                  <thead>
                    <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                      <th className="py-3 pl-5 pb-2">VENUE</th>
                      <th className="py-3 text-right pb-2">M</th>
                      <th className="py-3 text-right pb-2">W</th>
                      <th className="py-3 text-right pb-2">L</th>
                      <th className="py-3 text-right pb-2 border-l border-pb-hairline pl-3">INN</th>
                      <th className="py-3 text-right pb-2">RUNS</th>
                      <th className="py-3 text-right pb-2">AVG</th>
                      <th className="py-3 text-right pb-2">HS</th>
                      <th className="py-3 text-right pb-2 border-l border-pb-hairline pl-3">WKTS</th>
                      <th className="py-3 text-right pb-2">AVG</th>
                      <th className="py-3 text-right pb-2">ECO</th>
                      <th className="py-3 text-right pb-2 border-l border-pb-hairline pl-3">CT</th>
                      <th className="py-3 pr-5 text-right pb-2">ST</th>
                    </tr>
                  </thead>
                  <tbody>
                    {byVenue.map((r, i) => (
                      <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                        <td className="py-2.5 pl-5 text-pb-text max-w-[200px] truncate">{r.venue}</td>
                        <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{r.games}</td>
                        <td className="py-2.5 font-mono text-pb-text text-right">{r.wins ?? 0}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{r.losses ?? 0}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right border-l border-pb-hairline pl-3">{r.innings || '—'}</td>
                        <td className="py-2.5 font-mono text-pb-text text-right">{r.total_runs > 0 ? r.total_runs : '—'}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{r.batting_average != null ? Number(r.batting_average).toFixed(1) : '—'}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{r.high_score ?? '—'}</td>
                        <td className="py-2.5 font-mono text-pb-text text-right border-l border-pb-hairline pl-3">{r.wickets > 0 ? r.wickets : '—'}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{r.bowling_average != null ? Number(r.bowling_average).toFixed(1) : '—'}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{r.economy != null ? Number(r.economy).toFixed(1) : '—'}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right border-l border-pb-hairline pl-3">{r.catches_non_wk > 0 ? r.catches_non_wk : '—'}</td>
                        <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">{r.stumpings > 0 ? r.stumpings : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : (
            <p className="text-pb-faint text-sm py-4 font-mono">No venue data yet — venue tracking requires a Full Rebuild.</p>
          )}
        </div>
      )}

      {subTab === 'opposition' && (
        <div className="space-y-6">
          {byOpposition.length > 0 ? (
            <Card title="STATS BY OPPOSITION" pad="p-0">
              <p className="font-mono text-[10px] text-pb-faint tracking-wide2 px-5 pt-4 pb-2">Performance against each club across all seasons.</p>
              <div className="overflow-x-auto pb-scroll">
                <table className="w-full min-w-[860px] text-[13px]">
                  <thead>
                    <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                      <th className="py-3 pl-5 pb-2">OPPOSITION</th>
                      <th className="py-3 text-right pb-2">M</th>
                      <th className="py-3 text-right pb-2">W</th>
                      <th className="py-3 text-right pb-2">L</th>
                      <th className="py-3 text-right pb-2 border-l border-pb-hairline pl-3">INN</th>
                      <th className="py-3 text-right pb-2">RUNS</th>
                      <th className="py-3 text-right pb-2">AVG</th>
                      <th className="py-3 text-right pb-2">HS</th>
                      <th className="py-3 text-right pb-2 border-l border-pb-hairline pl-3">WKTS</th>
                      <th className="py-3 text-right pb-2">AVG</th>
                      <th className="py-3 text-right pb-2">ECO</th>
                      <th className="py-3 text-right pb-2 border-l border-pb-hairline pl-3">CT</th>
                      <th className="py-3 pr-5 text-right pb-2">ST</th>
                    </tr>
                  </thead>
                  <tbody>
                    {byOpposition.map((r, i) => (
                      <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                        <td className="py-2.5 pl-5 text-pb-text max-w-[200px] truncate">{r.opposition}</td>
                        <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{r.games}</td>
                        <td className="py-2.5 font-mono text-pb-text text-right">{r.wins ?? 0}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{r.losses ?? 0}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right border-l border-pb-hairline pl-3">{r.innings || '—'}</td>
                        <td className="py-2.5 font-mono text-pb-text text-right">{r.total_runs > 0 ? r.total_runs : '—'}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{r.batting_average != null ? Number(r.batting_average).toFixed(1) : '—'}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{r.high_score ?? '—'}</td>
                        <td className="py-2.5 font-mono text-pb-text text-right border-l border-pb-hairline pl-3">{r.wickets > 0 ? r.wickets : '—'}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{r.bowling_average != null ? Number(r.bowling_average).toFixed(1) : '—'}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right">{r.economy != null ? Number(r.economy).toFixed(1) : '—'}</td>
                        <td className="py-2.5 font-mono text-pb-dim text-right border-l border-pb-hairline pl-3">{r.catches_non_wk > 0 ? r.catches_non_wk : '—'}</td>
                        <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">{r.stumpings > 0 ? r.stumpings : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : (
            <p className="text-pb-faint text-sm py-4 font-mono">No opposition data available.</p>
          )}
        </div>
      )}

      {subTab === 'team' && (() => {
        const rows = teamBreakdown.rows || []
        const unattributed = teamBreakdown.unattributed || 0
        return (
          <div className="space-y-6">
            {rows.length > 0 ? (
              <Card
                title={`MATCHES BY GRADE${seasonLabel ? ` · ${seasonLabel.toUpperCase()}` : ''}`}
                pad="p-0"
              >
                <p className="font-mono text-[10px] text-pb-faint tracking-wide2 px-5 pt-4">
                  Every grade this player has appeared in (batting, bowling, or fielding), with result record.
                  {!seasonLabel && ' Use the season filter above to view a single season.'}
                </p>
                <div className="overflow-x-auto pb-scroll mt-3">
                  <table className="w-full min-w-[560px] text-[13px]">
                    <thead>
                      <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                        <th className="py-3 pl-5 pb-2">GRADE</th>
                        <th className="py-3 text-right pb-2">MATCHES</th>
                        <th className="py-3 text-right pb-2">SEASONS</th>
                        <th className="py-3 text-right pb-2">W</th>
                        <th className="py-3 text-right pb-2">L</th>
                        <th className="py-3 text-right pb-2">D</th>
                        <th className="py-3 pr-5 text-right pb-2">WIN %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                          <td className="py-2.5 pl-5 text-pb-text">{r.grade_name}</td>
                          <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}
                              title={r.attributed_unknown > 0 ? `${r.scorecard_matches} with scorecard + ${r.attributed_unknown} from CA aggregate (no scorecard yet)` : null}>
                            {r.matches}
                            {r.attributed_unknown > 0 && <span className="text-pb-faint font-normal"> *</span>}
                          </td>
                          <td className="py-2.5 font-mono text-pb-dim text-right">{r.seasons}</td>
                          <td className="py-2.5 font-mono text-pb-text text-right">{r.won}</td>
                          <td className="py-2.5 font-mono text-pb-dim text-right">{r.lost}</td>
                          <td className="py-2.5 font-mono text-pb-dim text-right">{r.drawn}</td>
                          <td className="py-2.5 pr-5 font-mono text-pb-text text-right">
                            {r.win_pct != null ? `${r.win_pct.toFixed(1)}%` : '—'}
                          </td>
                        </tr>
                      ))}
                      {unattributed > 0 && (
                        <tr className="pb-hairline-t hover:bg-pb-surface2"
                            title="Games CA's season aggregate counts but where we have no scorecard AND the player played in multiple grades that season, so we can't safely attribute them.">
                          <td className="py-2.5 pl-5 text-pb-faint italic">No scorecard data</td>
                          <td className="py-2.5 font-mono text-right pb-num text-pb-dim">{unattributed}</td>
                          <td className="py-2.5 text-right text-pb-faintest">—</td>
                          <td className="py-2.5 text-right text-pb-faintest">—</td>
                          <td className="py-2.5 text-right text-pb-faintest">—</td>
                          <td className="py-2.5 text-right text-pb-faintest">—</td>
                          <td className="py-2.5 pr-5 text-right text-pb-faintest">—</td>
                        </tr>
                      )}
                      {(rows.length > 1 || unattributed > 0) && (() => {
                        const totals = rows.reduce((acc, r) => {
                          acc.matches += r.matches || 0
                          acc.won += r.won || 0
                          acc.lost += r.lost || 0
                          acc.drawn += r.drawn || 0
                          return acc
                        }, { matches: 0, won: 0, lost: 0, drawn: 0 })
                        totals.matches += unattributed
                        const decided = totals.won + totals.lost + totals.drawn
                        const winPct = decided > 0 ? (totals.won / decided * 100) : null
                        return (
                          <tr className="pb-hairline-t bg-pb-surface2">
                            <td className="py-2.5 pl-5 font-mono text-[11px] tracking-wide2 text-pb-faint">TOTAL</td>
                            <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{totals.matches}</td>
                            <td className="py-2.5 text-right text-pb-faintest">—</td>
                            <td className="py-2.5 font-mono text-pb-text text-right">{totals.won}</td>
                            <td className="py-2.5 font-mono text-pb-dim text-right">{totals.lost}</td>
                            <td className="py-2.5 font-mono text-pb-dim text-right">{totals.drawn}</td>
                            <td className="py-2.5 pr-5 font-mono text-pb-text text-right">
                              {winPct != null ? `${winPct.toFixed(1)}%` : '—'}
                            </td>
                          </tr>
                        )
                      })()}
                    </tbody>
                  </table>
                </div>
                {(rows.some(r => r.attributed_unknown > 0) || unattributed > 0) && (
                  <p className="font-mono text-[10px] text-pb-faint tracking-wide2 px-5 pb-4 pt-2">
                    * = matches counted by CA&apos;s season aggregate but with no scorecard captured yet; attributed to a grade only when the player played in a single grade that season.
                    {unattributed > 0 && ` ${unattributed.toLocaleString()} ${unattributed === 1 ? 'match' : 'matches'} couldn't be attributed (mixed-grade season).`}
                  </p>
                )}
              </Card>
            ) : (
              <p className="text-pb-faint text-sm py-4">No grade appearances recorded{seasonLabel ? ` for ${seasonLabel}` : ''}.</p>
            )}
          </div>
        )
      })()}
    </div>
  )
}

// ── Milestones tab ───────────────────────────────────────────────────────
const MILESTONE_SUB_TABS = [
  { key: 'batting',  label: 'BATTING'  },
  { key: 'bowling',  label: 'BOWLING'  },
  { key: 'fielding', label: 'FIELDING' },
  { key: 'matches',  label: 'MATCHES'  },
]

const TYPE_LABELS = { runs: 'Runs', wickets: 'Wickets', matches: 'Matches', catches: 'Catches', grade_matches: 'Matches' }

function UpcomingCard({ items }) {
  if (!items?.length) return null
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {items.map((m, i) => {
        const pct = Math.min(100, Math.round((m.current / m.target) * 100))
        return (
          <div key={i} className="pb-card-2 p-4 rounded border border-pb-hairline">
            <Label>{m.label || m.type?.toUpperCase() || 'MILESTONE'}</Label>
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
  )
}

function AchievedList({ items }) {
  if (!items?.length) return null
  return (
    <ul className="flex flex-col">
      {items.map((m, i) => {
        const typeLabel = TYPE_LABELS[m.milestone_type] || m.milestone_type || 'Milestone'
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
  )
}

function MilestonesTab({ playerId, upcomingMilestones, milestones }) {
  const [sub, setSub] = useState('batting')

  const upcoming = upcomingMilestones || []
  const achieved = milestones || []

  // Bucket upcoming by sub-tab. Matches bucket holds both club total and per-grade.
  const upByCat = {
    batting:  upcoming.filter(m => m.type === 'runs'),
    bowling:  upcoming.filter(m => m.type === 'wickets'),
    fielding: upcoming.filter(m => m.type === 'catches'),
    matches:  upcoming.filter(m => m.type === 'matches'),
  }
  // For the matches tab, surface club total first, then per-grade by needed.
  upByCat.matches = upByCat.matches.slice().sort((a, b) => {
    if (!a.grade_name && b.grade_name) return -1
    if (a.grade_name && !b.grade_name) return 1
    return (a.needed ?? 9999) - (b.needed ?? 9999)
  })

  const sortByValueDesc = (a, b) => (b.milestone_value || 0) - (a.milestone_value || 0)
  const achByCat = {
    batting:  achieved.filter(m => m.milestone_type === 'runs').sort(sortByValueDesc),
    bowling:  achieved.filter(m => m.milestone_type === 'wickets').sort(sortByValueDesc),
    fielding: achieved.filter(m => m.milestone_type === 'catches').sort(sortByValueDesc),
  }
  const matchesClub = achieved.filter(m => m.milestone_type === 'matches').sort(sortByValueDesc)
  // Per-grade: group by grade name, sort each grade's thresholds desc, then sort grades alphabetically.
  const gradeBuckets = new Map()
  for (const m of achieved.filter(x => x.milestone_type === 'grade_matches')) {
    const key = m.detail || 'Unknown grade'
    if (!gradeBuckets.has(key)) gradeBuckets.set(key, [])
    gradeBuckets.get(key).push(m)
  }
  const matchesByGrade = Array.from(gradeBuckets.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .flatMap(([, rows]) => rows.sort(sortByValueDesc))

  const renderTab = () => {
    if (sub === 'matches') {
      const up = upByCat.matches
      const hasAny = up.length || matchesClub.length || matchesByGrade.length
      if (!hasAny) {
        return <p className="text-pb-faint text-sm py-4">No match milestones yet for this player.</p>
      }
      return (
        <div className="space-y-6">
          {up.length > 0 && (
            <Card title="MILESTONES IN REACH"><UpcomingCard items={up} /></Card>
          )}
          {matchesClub.length > 0 && (
            <Card title="ACHIEVED — CLUB TOTAL" pad="p-0"><AchievedList items={matchesClub} /></Card>
          )}
          {matchesByGrade.length > 0 && (
            <Card title="ACHIEVED — BY GRADE" pad="p-0"><AchievedList items={matchesByGrade} /></Card>
          )}
        </div>
      )
    }

    const up = upByCat[sub]
    const ach = achByCat[sub]
    const hasAny = (up?.length || 0) + (ach?.length || 0) > 0
    if (!hasAny) {
      const noun = { batting: 'batting', bowling: 'bowling', fielding: 'fielding' }[sub]
      return <p className="text-pb-faint text-sm py-4">No {noun} milestones yet for this player.</p>
    }
    return (
      <div className="space-y-6">
        {up.length > 0 && (
          <Card title="MILESTONES IN REACH"><UpcomingCard items={up} /></Card>
        )}
        {ach.length > 0 && (
          <Card title="ACHIEVED" pad="p-0"><AchievedList items={ach} /></Card>
        )}
      </div>
    )
  }

  return (
    <div>
      <TabBar tabs={MILESTONE_SUB_TABS} active={sub} onChange={setSub} />
      {renderTab()}
    </div>
  )
}

// ── Achievements tab ──────────────────────────────────────────────────────
function AchievementsSection({ playerId, orgId, playerName }) {
  const { user } = useAuth()
  const canEdit = !!user
  const [achievements, setAchievements] = useState(null)
  const [seasons, setSeasons] = useState([])
  const [awardDefs, setAwardDefs] = useState([])
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
    api.listAwardDefinitions(orgId).then(data => setAwardDefs(data || [])).catch(() => {})
  }, [playerId, orgId])

  const subcatOptions = getSubcategoriesFromDefs(awardDefs, form.category)
  const achievementOptions = getAchievementsFromDefs(awardDefs, form.category, form.subcategory)
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

  const HonourBadge = ({ a, theme = 'award', seasonsStr = null, onEdit, onDelete }) => {
    const iconSrc = CATEGORY_ICON_SRC[a.category] || thiings.trophy
    const label = resolveAwardLabel(awardDefs, a.category, a.subcategory, a.achievement)
    const sub = a.subcategory
    const detail = a.detail
    const season = seasonsStr || seasonRange(a)
    return (
      <div className="hb-parent" style={badgeVars(theme)}>
        <div className="hb-card">
          <div className="hb-icon">
            <img src={iconSrc} alt="" style={{ width: 14, height: 14, objectFit: 'contain', filter: 'brightness(0) invert(1)', opacity: 0.85 }} />
          </div>
          <div className="hb-content">
            <span className="hb-category">{a.category}</span>
            <span className="hb-title">{label}</span>
            {(sub || detail) && (
              <span className="hb-sub">
                {sub && <span>{sub}</span>}
                {detail && <span style={{ color: 'var(--hb-accent-text)', marginLeft: 3 }}>{detail}</span>}
              </span>
            )}
          </div>
          <div className="hb-season">{season}</div>
          {canEdit && (
            <div className="hb-admin-btns">
              {onEdit && <button className="hb-edit-btn" onClick={onEdit}>Edit</button>}
              {onDelete && <button className="hb-del-btn" onClick={onDelete}>✕</button>}
            </div>
          )}
        </div>
      </div>
    )
  }

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
                : <select className={selectCls} value={form.subcategory} onChange={e => { if (e.target.value === '__other__') { setCustomSubcat(true); setForm(f => ({ ...f, subcategory: '', achievement: '' })) } else { setForm(f => ({ ...f, subcategory: e.target.value, achievement: '' })) } }}>
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
                : <select className={selectCls} value={form.achievement} onChange={e => { if (e.target.value === '__other__') { setCustomAchievement(true); setForm(f => ({ ...f, achievement: '' })) } else { setCustomAchievement(false); setForm(f => ({ ...f, achievement: e.target.value })) } }}>
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
          <div className="flex flex-wrap gap-4">
            {honours.map(a => (
              <HonourBadge key={a.id} a={a} theme="honour"
                onEdit={() => openEdit(a)}
                onDelete={() => handleDelete(a.id)} />
            ))}
          </div>
        </div>
      )}
      {rolesList.length > 0 && (
        <div>
          <Label className="block mb-3">ROLES</Label>
          <div className="flex flex-wrap gap-4">
            {rolesList.map((g, i) => {
              // instances sorted most-recent-first
              const shorts = g.instances.map(inst => formatSeasonShort(inst.season, seasons)).filter(Boolean)
              const n = g.instances.length
              const seasons_str = n === 1
                ? shorts[0]
                : n === 2
                  ? shorts.join(', ')
                  : `${n}× · ${shorts[shorts.length - 1]}–${shorts[0]}`
              const synth = { ...g.instances[0], subcategory: g.subcategory, achievement: g.achievement, detail: null }
              return (
                <HonourBadge key={i} a={synth} theme="role"
                  seasonsStr={seasons_str || undefined}
                  onEdit={() => openEdit(g.instances[0])}
                  onDelete={() => handleDelete(g.instances[0].id)} />
              )
            })}
          </div>
        </div>
      )}
      {awards.length > 0 && (
        <div>
          <Label className="block mb-3">AWARDS</Label>
          <div className="flex flex-wrap gap-4">
            {awards.map(a => (
              <HonourBadge key={a.id} a={a} theme="award"
                onEdit={() => openEdit(a)}
                onDelete={() => handleDelete(a.id)} />
            ))}
          </div>
        </div>
      )}
      {milestones.length > 0 && (
        <div>
          <Label className="block mb-3">MILESTONES</Label>
          <div className="flex flex-wrap gap-4">
            {milestones.map(a => (
              <HonourBadge key={a.id} a={a} theme="milestone"
                onEdit={() => openEdit(a)}
                onDelete={() => handleDelete(a.id)} />
            ))}
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
  const [awardDefs, setAwardDefs] = useState([])
  const [dismissals, setDismissals] = useState([])
  const [partnerships, setPartnerships] = useState([])
  const [byGrade, setByGrade] = useState([])
  const [byPosition, setByPosition] = useState([])
  const [bowlingByGrade, setBowlingByGrade] = useState([])
  const [bowlingDismissals, setBowlingDismissals] = useState([])
  const [bowlingByBatterPosition, setBowlingByBatterPosition] = useState([])
  const [byVenue, setByVenue] = useState([])
  const [byOpposition, setByOpposition] = useState([])
  const [teamBreakdown, setTeamBreakdown] = useState({ rows: [], unattributed: 0, total_aggregate_matches: 0 })
  const [captainStats, setCaptainStats] = useState(null)
  const [tab, setTab] = useState('batting')
  // Track which playerId we last fetched aux data for, so navigating between
  // player profiles refetches instead of showing the prior player's data.
  const lastAuxFetchRef = useRef(null)
  const lastMilestonesFetchRef = useRef(null)

  useClubTheme(org)
  const fmtName = useNameFormat(org)

  const player = data?.player
  const batting = data?.career_batting
  const bowling = data?.career_bowling
  const metaName = player ? fmtName(player.display_name) : null
  const metaDesc = (() => {
    if (!player || !batting) return null
    const parts = []
    if (batting.total_runs != null) parts.push(`${batting.total_runs} runs`)
    if (batting.innings != null) parts.push(`${batting.innings} innings`)
    if (bowling?.total_wickets != null) parts.push(`${bowling.total_wickets} wickets`)
    if (batting.games != null) parts.push(`${batting.games} matches`)
    const club = org?.name ? `${org.name} cricket` : 'club cricket'
    return parts.length ? `${parts.join(' · ')} — ${club} statistics on BetterStats.` : null
  })()
  usePageMeta({
    title: metaName ? `${metaName} — BetterStats` : null,
    description: metaDesc,
    image: org?.logo_url || null,
  })

  useEffect(() => {
    if (!playerId) return
    api.getPlayerSeasons(playerId).then(setSeasonStats).catch(() => setSeasonStats([]))
    api.getPlayerUpcomingMilestones(playerId).then(setUpcomingMilestones).catch(() => setUpcomingMilestones([]))
    api.getPlayerCaptainStats(playerId).then(setCaptainStats).catch(() => setCaptainStats({}))
  }, [playerId])

  useEffect(() => {
    if (!data?.player?.organisation_id) return
    const oid = data.player.organisation_id
    api.getOrgSeasons(oid).then(setSeasons).catch(() => {})
    api.getOrg(oid).then(setOrg).catch(() => {})
    api.listAchievements(oid, { playerId }).then(setAchievements).catch(() => setAchievements([]))
    api.listAwardDefinitions(oid).then(d => setAwardDefs(d || [])).catch(() => {})
  }, [data?.player?.organisation_id, playerId])

  useEffect(() => {
    if (!data?.player) return
    if (lastMilestonesFetchRef.current === playerId) return
    lastMilestonesFetchRef.current = playerId
    setMilestones([])
    api.getPlayerMilestones(playerId).then(setMilestones).catch(() => setMilestones([]))
  }, [playerId, data?.player])

  useEffect(() => {
    if (!playerId || !data?.player) return
    if (lastAuxFetchRef.current === playerId) return
    lastAuxFetchRef.current = playerId
    // Reset stale state from previously-viewed player — otherwise navigating
    // between profiles would show the previous player's dismissal/grade data.
    setPartnerships([])
    setDismissals([])
    setByGrade([])
    setByPosition([])
    setBowlingByGrade([])
    setBowlingDismissals([])
    setBowlingByBatterPosition([])
    setByVenue([])
    setByOpposition([])
    Promise.allSettled([
      api.getPlayerPartnerships(playerId),
      api.getPlayerDismissals(playerId),
      api.getPlayerByGrade(playerId),
      api.getPlayerByPosition(playerId),
      api.getPlayerBowlingByGrade(playerId),
      api.getPlayerBowlingDismissals(playerId),
      api.getPlayerBowlingByBatterPosition(playerId),
      api.getPlayerByVenue(playerId),
      api.getPlayerByOpposition(playerId),
    ]).then(([p, d, g, pos, bg, bd, bbp, bv, bo]) => {
      if (p.status === 'fulfilled') setPartnerships(p.value)
      if (d.status === 'fulfilled') setDismissals(d.value)
      if (g.status === 'fulfilled') setByGrade(g.value)
      if (pos.status === 'fulfilled') setByPosition(pos.value)
      if (bg.status === 'fulfilled') setBowlingByGrade(bg.value)
      if (bd.status === 'fulfilled') setBowlingDismissals(bd.value)
      if (bbp.status === 'fulfilled') setBowlingByBatterPosition(bbp.value)
      if (bv.status === 'fulfilled') setByVenue(Array.isArray(bv.value) ? bv.value : [])
      if (bo.status === 'fulfilled') setByOpposition(Array.isArray(bo.value) ? bo.value : [])
    })
  }, [playerId, data?.player])

  useEffect(() => {
    if (!playerId || !data?.player) return
    api.getPlayerTeamBreakdown(playerId, { seasonId })
      .then(res => setTeamBreakdown(res && res.rows ? res : { rows: [], unattributed: 0, total_aggregate_matches: 0 }))
      .catch(() => setTeamBreakdown({ rows: [], unattributed: 0, total_aggregate_matches: 0 }))
  }, [playerId, data?.player, seasonId])

  if (loading) return <PbSpinner message="Loading player data…" />
  if (error) return <div className="max-w-7xl mx-auto px-4 py-16 text-pb-red">Error: {error}</div>
  if (!data?.player) return null

  // player, batting, bowling already declared above hooks for usePageMeta
  const fielding = data.career_fielding
  const battingInnings = data.batting_innings ?? []
  const bowlingSpells = data.bowling_spells ?? []
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
          <span className="text-pb-dim">{fmtName(player.display_name).toUpperCase()}</span>
        </div>

        {/* Hero */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-6 mb-6 items-end">
          <div>
            <Label>{org?.name || ''} · {player.role || 'PLAYER'}</Label>
            <h1 className="font-display text-[48px] sm:text-[72px] font-bold tracking-tight leading-[0.92] mt-1.5 text-pb-text">
              {fmtName(player.display_name)}
            </h1>
            {/* Header achievement badges */}
            {headerAchievements.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {headerAchievements.map(a => {
                  const c = `var(--pb-cat-${achievementType(a)})`
                  return (
                    <span key={a.id} className="font-mono text-[10px] tracking-wide2 px-2.5 py-1 rounded-sm border text-[11px]"
                      style={{
                        borderColor: `color-mix(in srgb, ${c} 40%, transparent)`,
                        color: c,
                        background: `color-mix(in srgb, ${c} 10%, transparent)`,
                      }}>
                      {formatAchievementBadge(a, seasons, awardDefs)}
                    </span>
                  )
                })}
              </div>
            )}
          </div>
          <div className="flex flex-col items-end gap-3">
            {player.photo_url && (
              <img
                src={player.photo_url}
                alt={fmtName(player.display_name)}
                className="w-24 h-24 rounded-full object-cover border border-pb-hairline2"
              />
            )}
            <div className="flex gap-2 flex-wrap justify-end">
              {orgSlug && (
                <Link to={`/${orgSlug}/compare?playerA=${playerId}`}>
                  <Btn>Compare</Btn>
                </Link>
              )}
              <Link to={`/players/${playerId}/share`}><Btn primary>Share card</Btn></Link>
            </div>
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
                    <span className="font-mono text-2xl font-bold pb-num leading-none mt-1" style={{ color: batting.hundreds > 0 ? 'var(--pb-chart-milestone, #f5b542)' : undefined }}>
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
        {tab === 'analysis' && <AnalysisTab playerId={playerId} dismissals={dismissals} partnerships={partnerships} byGrade={byGrade} byPosition={byPosition} seasonStats={seasonStats} bowlingByGrade={bowlingByGrade} bowlingDismissals={bowlingDismissals} bowlingByBatterPosition={bowlingByBatterPosition} battingInnings={battingInnings} bowlingSpells={bowlingSpells} teamBreakdown={teamBreakdown} seasonLabel={seasonId ? (seasons.find(s => s.id === seasonId)?.name || null) : null} captainStats={captainStats} byVenue={byVenue} byOpposition={byOpposition} />}
        {tab === 'milestones' && <MilestonesTab playerId={playerId} upcomingMilestones={upcomingMilestones} milestones={milestones} />}
        {tab === 'achievements' && <AchievementsSection playerId={playerId} orgId={player.organisation_id} playerName={player.display_name || player.name} />}
      </main>
    </div>
  )
}
