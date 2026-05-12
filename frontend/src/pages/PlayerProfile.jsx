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
            ['INNINGS', batting.batting_innings],
            ['RUNS', batting.total_runs, true],
            ['AVERAGE', fmt(batting.batting_average, true)],
            ['STRIKE RATE', fmt(batting.strike_rate, true)],
            ['HIGH SCORE', batting.high_score],
            ['100s · 50s', `${batting.hundreds ?? 0} · ${batting.fifties ?? 0}`],
            ['4s · 6s', `${batting.total_fours ?? 0} · ${batting.total_sixes ?? 0}`],
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
                  <SortTh label="SR" sKey="strike_rate" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="HS" sKey="high_score" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="100s" sKey="hundreds" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="50s" sKey="fifties" cur={sortKey} dir={sortDir} onSort={request} right />
                  <th className="py-3 pr-5 text-right pb-2 font-mono text-[10px] tracking-wide3">6s</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((s, i) => (
                  <tr key={s.season_name || i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 pl-5 font-mono text-pb-dim text-[12px]">{s.season_name}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.batting_innings)}</td>
                    <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{fmt(s.total_runs)}</td>
                    <td className="py-2.5 font-mono text-pb-text text-right">{fmt(s.batting_average, true)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.strike_rate, true)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.high_score)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.hundreds)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.fifties)}</td>
                    <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">{fmt(s.total_sixes)}</td>
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
            ['OVERS', fmt(bowling.bowling_overs, true)],
            ['AVERAGE', fmt(bowling.bowling_average, true)],
            ['ECONOMY', fmt(bowling.bowling_economy, true)],
            ['STRIKE RATE', fmt(bowling.bowling_strike_rate, true)],
            ['5-FORS', bowling.five_wicket_innings ?? 0],
            ['MAIDENS', bowling.total_maidens ?? 0],
            ['BEST', bowling.best_bowling_wickets ? `${bowling.best_bowling_wickets}/${bowling.best_bowling_runs ?? '?'}` : '—'],
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
                  <SortTh label="OV" sKey="bowling_overs" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="AVG" sKey="bowling_average" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="ECON" sKey="bowling_economy" cur={sortKey} dir={sortDir} onSort={request} right />
                  <SortTh label="5W" sKey="five_wicket_innings" cur={sortKey} dir={sortDir} onSort={request} right />
                  <th className="py-3 pr-5 text-right pb-2 font-mono text-[10px] tracking-wide3">BEST</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((s, i) => (
                  <tr key={s.season_name || i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 pl-5 font-mono text-pb-dim text-[12px]">{s.season_name}</td>
                    <td className="py-2.5 font-mono font-bold text-right pb-num" style={{ color: 'var(--pb-accent)' }}>{fmt(s.total_wickets)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.bowling_overs, true)}</td>
                    <td className="py-2.5 font-mono text-pb-text text-right">{fmt(s.bowling_average, true)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.bowling_economy, true)}</td>
                    <td className="py-2.5 font-mono text-pb-dim text-right">{fmt(s.five_wicket_innings)}</td>
                    <td className="py-2.5 pr-5 font-mono text-pb-dim text-right">
                      {s.best_bowling_wickets ? `${s.best_bowling_wickets}/${s.best_bowling_runs ?? '?'}` : '—'}
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
function AnalysisTab({ playerId, dismissals, partnerships, byGrade, byPosition }) {
  return (
    <div className="space-y-6">
      {/* Dismissal split */}
      {dismissals?.length > 0 && (
        <Card title="DISMISSAL SPLIT">
          <ul className="flex flex-col gap-2.5">
            {dismissals.map(d => (
              <li key={d.dismissal_type} className="flex items-center gap-3">
                <span className="w-28 font-mono text-[11px] tracking-wide2 text-pb-dim capitalize">{d.dismissal_type || 'Unknown'}</span>
                <div className="flex-1 h-1.5 bg-pb-hairline rounded-sm overflow-hidden">
                  <div className="h-full" style={{ width: `${d.pct ?? 0}%`, background: 'var(--pb-accent)', opacity: 0.8 }} />
                </div>
                <span className="font-mono text-[12px] text-pb-text pb-num w-12 text-right">{d.count} ({d.pct ?? 0}%)</span>
              </li>
            ))}
          </ul>
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

      {/* By grade */}
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

      {!dismissals?.length && !partnerships?.length && !byGrade?.length && !byPosition?.length && (
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
            {milestones.map((m, i) => (
              <li key={i} className={`${i ? 'pb-hairline-t' : ''} flex items-center gap-4 px-5 py-3 hover:bg-pb-surface2`}>
                <ThiingIcon src={MILESTONE_ICON_SRC[m.type] || thiings.trophy} alt="" className="w-6 h-6 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-pb-text text-[14px] font-semibold truncate">{m.name || m.description}</div>
                  <div className="font-mono text-pb-faint text-[10.5px] tracking-wide2 mt-0.5">
                    {m.season_name || ''}{m.achieved_at ? ` · ${new Date(m.achieved_at + 'T00:00:00').toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}` : ''}
                  </div>
                </div>
                <span className="font-mono text-[18px] font-bold pb-num" style={{ color: 'var(--pb-accent)' }}>
                  {m.milestone?.toLocaleString() ?? m.value?.toLocaleString()}
                </span>
              </li>
            ))}
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

  // Partition
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

  const renderBadge = (a) => (
    <span key={a.id}
      className="inline-flex items-center gap-1 font-mono text-[10.5px] tracking-wide2 px-2.5 py-1 rounded-sm border border-pb-hairline2 text-pb-dim bg-pb-surface2"
    >
      {formatAchievementBadge(a, seasons)}
      {canEdit && (
        <>
          <button onClick={() => { setForm({ season: a.season||'', season_end: a.season_end||'', category: a.category, subcategory: a.subcategory||'', achievement: a.achievement, detail: a.detail||'' }); setEditId(a.id); setAdding(true) }} className="ml-1 text-pb-faint hover:text-pb-text">✎</button>
          <button onClick={() => handleDelete(a.id)} className="text-pb-faint hover:text-pb-red">×</button>
        </>
      )}
    </span>
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
              <input className={inputCls} value={form.detail} onChange={e => setForm(f => ({ ...f, detail: e.target.value }))} placeholder="e.g. #32" />
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
          <div className="flex flex-wrap gap-2">{honours.map(renderBadge)}</div>
        </div>
      )}
      {rolesList.length > 0 && (
        <div>
          <Label className="block mb-3">ROLES</Label>
          <div className="flex flex-wrap gap-2">
            {rolesList.map((g, i) => {
              const seasons_str = g.instances.map(inst => formatSeasonShort(inst.season, seasons)).filter(Boolean).join(', ')
              return (
                <span key={i} className="inline-flex items-center gap-1 font-mono text-[10.5px] tracking-wide2 px-2.5 py-1 rounded-sm border border-pb-hairline2 text-pb-dim bg-pb-surface2">
                  {g.subcategory ? `${g.subcategory} – ` : ''}{g.achievement}{seasons_str ? ` (${seasons_str})` : ''}
                  {canEdit && <>
                    <button onClick={() => { const a = g.instances[0]; setForm({ season: a.season||'', season_end: a.season_end||'', category: a.category, subcategory: a.subcategory||'', achievement: a.achievement, detail: a.detail||'' }); setEditId(a.id); setAdding(true) }} className="ml-1 text-pb-faint hover:text-pb-text">✎</button>
                    <button onClick={() => handleDelete(g.instances[0].id)} className="text-pb-faint hover:text-pb-red">×</button>
                  </>}
                </span>
              )
            })}
          </div>
        </div>
      )}
      {awards.length > 0 && (
        <div>
          <Label className="block mb-3">AWARDS</Label>
          <div className="flex flex-wrap gap-2">{awards.map(renderBadge)}</div>
        </div>
      )}
      {milestones.length > 0 && (
        <div>
          <Label className="block mb-3">MILESTONES</Label>
          <div className="flex flex-wrap gap-2">{milestones.map(renderBadge)}</div>
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
  const batting = data.batting_career
  const bowling = data.bowling_career
  const fielding = data.fielding_career
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
                  <span key={a.id} className="font-mono text-[10px] tracking-wide2 px-2 py-0.5 rounded-sm border border-pb-hairline2 text-pb-dim">
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
            <div className="flex border border-pb-hairline2 rounded overflow-hidden">
              <button
                onClick={() => setSeasonId(null)}
                className={`px-2.5 py-1.5 font-mono text-[10.5px] tracking-wide2 ${!seasonId ? 'text-pb-text bg-pb-surface2' : 'text-pb-faint hover:text-pb-dim'}`}
              >
                ALL
              </button>
              {seasons.slice(0, 8).map(s => (
                <button
                  key={s.id}
                  onClick={() => setSeasonId(s.id)}
                  className={`px-2.5 py-1.5 font-mono text-[10.5px] tracking-wide2 ${seasonId === s.id ? 'text-pb-text bg-pb-surface2' : 'text-pb-faint hover:text-pb-dim'}`}
                >
                  {s.name?.replace(/Summer /i, '').replace(/Winter /i, '') || s.id}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Quick stat strip */}
        {batting && (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
            <div className="pb-card p-4 flex flex-col gap-1">
              <Label>RUNS</Label>
              <span className="font-mono text-3xl font-semibold pb-num leading-none mt-1" style={{ color: 'var(--pb-accent)' }}>
                <AnimatedNum value={batting.total_runs || 0} />
              </span>
            </div>
            <div className="pb-card p-4 flex flex-col gap-1">
              <Label>AVERAGE</Label>
              <span className="font-mono text-3xl font-semibold pb-num leading-none mt-1 text-pb-text">
                {batting.batting_average != null ? Number(batting.batting_average).toFixed(2) : '—'}
              </span>
            </div>
            <div className="pb-card p-4 flex flex-col gap-1">
              <Label>HIGH SCORE</Label>
              <span className="font-mono text-3xl font-semibold pb-num leading-none mt-1 text-pb-text">
                {batting.high_score ?? '—'}
              </span>
            </div>
            <div className="pb-card p-4 flex flex-col gap-1">
              <Label>WICKETS</Label>
              <span className="font-mono text-3xl font-semibold pb-num leading-none mt-1 text-pb-text">
                <AnimatedNum value={bowling?.total_wickets || 0} />
              </span>
            </div>
            <div className="pb-card p-4 flex flex-col gap-1">
              <Label>MATCHES</Label>
              <span className="font-mono text-3xl font-semibold pb-num leading-none mt-1 text-pb-text">
                <AnimatedNum value={player.matches_played || 0} />
              </span>
            </div>
          </div>
        )}

        {/* Tabs */}
        <TabBar tabs={MAIN_TABS} active={tab} onChange={setTab} />

        {/* Tab content */}
        {tab === 'batting' && <BattingTab batting={batting} seasonStats={seasonStats} seasons={seasons} />}
        {tab === 'bowling' && <BowlingTab bowling={bowling} seasonStats={seasonStats} />}
        {tab === 'fielding' && <FieldingTab fielding={fielding} seasonStats={seasonStats} />}
        {tab === 'analysis' && <AnalysisTab playerId={playerId} dismissals={dismissals} partnerships={partnerships} byGrade={byGrade} byPosition={byPosition} />}
        {tab === 'milestones' && <MilestonesTab playerId={playerId} upcomingMilestones={upcomingMilestones} milestones={milestones} />}
        {tab === 'achievements' && <AchievementsSection playerId={playerId} orgId={player.organisation_id} playerName={player.name} />}
      </main>
    </div>
  )
}
