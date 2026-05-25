import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { usePageMeta } from '../hooks/usePageMeta'
import { useNameFormat } from '../lib/nameFormat'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import { Card, PageHeader, PbSpinner, TabBar, ResultPill, Kpi } from '../lib/presskit'

// ── Helpers ────────────────────────────────────────────────────────────────

function fmt(v, decimals = 1) {
  if (v == null || v === '') return '—'
  const n = parseFloat(v)
  return isNaN(n) ? '—' : n.toFixed(decimals)
}

function fmtDate(dateStr) {
  if (!dateStr) return '—'
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-AU', {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}

// ── Chart tooltip ──────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-pb-surface border pb-hairline rounded px-3 py-2 text-sm shadow-lg">
      <p className="font-mono text-[10px] text-pb-faint mb-1">{label}</p>
      <p className="font-mono font-bold text-pb-text">{payload[0].value} {unit}</p>
    </div>
  )
}

// ── Horizontal bar chart ───────────────────────────────────────────────────

function HorizBarChart({ data, dataKey, unit, color = 'var(--pb-accent)' }) {
  if (!data?.length) return <p className="text-pb-faint font-mono text-[11px] py-6 text-center">No data.</p>

  return (
    <ResponsiveContainer width="100%" height={Math.max(data.length * 36, 100)}>
      <BarChart
        layout="vertical"
        data={data}
        margin={{ top: 0, right: 12, left: 0, bottom: 0 }}
      >
        <XAxis
          type="number"
          tick={{ fill: 'var(--pb-faint)', fontSize: 9 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={110}
          tick={{ fill: 'var(--pb-dim)', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          content={<ChartTooltip unit={unit} />}
          cursor={{ fill: 'var(--pb-surface2)' }}
        />
        <Bar dataKey={dataKey} radius={[0, 3, 3, 0]}>
          {data.map((_, i) => (
            <Cell
              key={i}
              fill={color}
              opacity={1 - i * 0.08}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Stat tables ────────────────────────────────────────────────────────────

function BattingTable({ rows, fmt: fmtName }) {
  if (!rows.length) return <p className="text-pb-faint font-mono text-[12px] py-8 text-center">No batting data.</p>
  return (
    <div className="overflow-x-auto pb-scroll">
      <table className="w-full min-w-[500px] text-[13px]">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
            <th className="font-medium py-3 pl-4 w-8">#</th>
            <th className="font-medium py-3">PLAYER</th>
            <th className="font-medium py-3 text-right pr-4">INN</th>
            <th className="font-medium py-3 text-right pr-4">RUNS</th>
            <th className="font-medium py-3 text-right pr-4">AVG</th>
            <th className="font-medium py-3 text-right pr-4">HS</th>
            <th className="font-medium py-3 text-right pr-4">50s</th>
            <th className="font-medium py-3 text-right pr-4">100s</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.player_id} className="pb-hairline-t hover:bg-pb-surface2/50 transition">
              <td className="py-3 pl-4 font-mono text-[10px] text-pb-faint">{i + 1}</td>
              <td className="py-3">
                <Link to={`/players/${r.player_id}`} className="font-semibold text-pb-text hover:text-pb-accent transition">
                  {fmtName(r.name)}
                </Link>
              </td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{r.innings ?? '—'}</td>
              <td className="py-3 text-right pr-4 font-mono font-semibold text-pb-text">{r.total_runs ?? '—'}</td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{fmt(r.average)}</td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{r.high_score ?? '—'}</td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{r.fifties ?? '—'}</td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{r.hundreds ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BowlingTable({ rows, fmt: fmtName }) {
  if (!rows.length) return <p className="text-pb-faint font-mono text-[12px] py-8 text-center">No bowling data.</p>
  return (
    <div className="overflow-x-auto pb-scroll">
      <table className="w-full min-w-[500px] text-[13px]">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
            <th className="font-medium py-3 pl-4 w-8">#</th>
            <th className="font-medium py-3">PLAYER</th>
            <th className="font-medium py-3 text-right pr-4">OVERS</th>
            <th className="font-medium py-3 text-right pr-4">WKTS</th>
            <th className="font-medium py-3 text-right pr-4">AVG</th>
            <th className="font-medium py-3 text-right pr-4">ECON</th>
            <th className="font-medium py-3 text-right pr-4">BEST</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.player_id} className="pb-hairline-t hover:bg-pb-surface2/50 transition">
              <td className="py-3 pl-4 font-mono text-[10px] text-pb-faint">{i + 1}</td>
              <td className="py-3">
                <Link to={`/players/${r.player_id}`} className="font-semibold text-pb-text hover:text-pb-accent transition">
                  {fmtName(r.name)}
                </Link>
              </td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{fmt(r.overs, 1)}</td>
              <td className="py-3 text-right pr-4 font-mono font-semibold text-pb-text">{r.total_wickets ?? '—'}</td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{fmt(r.average)}</td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{fmt(r.economy)}</td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">
                {r.best_figures_wickets != null ? `${r.best_figures_wickets}/${r.best_figures_runs}` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FieldingTable({ rows, fmt: fmtName }) {
  if (!rows.length) return <p className="text-pb-faint font-mono text-[12px] py-8 text-center">No fielding data.</p>
  return (
    <div className="overflow-x-auto pb-scroll">
      <table className="w-full min-w-[460px] text-[13px]">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left bg-pb-surface2/40">
            <th className="font-medium py-3 pl-4 w-8">#</th>
            <th className="font-medium py-3">PLAYER</th>
            <th className="font-medium py-3 text-right pr-4">CT</th>
            <th className="font-medium py-3 text-right pr-4">CT (WK)</th>
            <th className="font-medium py-3 text-right pr-4">RO</th>
            <th className="font-medium py-3 text-right pr-4">ST</th>
            <th className="font-medium py-3 text-right pr-4">TOTAL</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.player_id} className="pb-hairline-t hover:bg-pb-surface2/50 transition">
              <td className="py-3 pl-4 font-mono text-[10px] text-pb-faint">{i + 1}</td>
              <td className="py-3">
                <Link to={`/players/${r.player_id}`} className="font-semibold text-pb-text hover:text-pb-accent transition">
                  {fmtName(r.name)}
                </Link>
              </td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{r.total_catches_non_wk ?? '—'}</td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{r.total_catches_wk ?? '—'}</td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{r.total_run_outs ?? '—'}</td>
              <td className="py-3 text-right pr-4 font-mono text-pb-dim">{r.total_stumpings ?? '—'}</td>
              <td className="py-3 text-right pr-4 font-mono font-semibold text-pb-text">{r.total_dismissals ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Match results list ──────────────────────────────────────────────────────

function ResultRow({ game }) {
  return (
    <Link
      to={`/games/${game.id}`}
      className="flex items-center gap-3 py-3 px-4 hover:bg-pb-surface2 transition group pb-hairline-t first:border-t-0"
    >
      <span className="w-28 shrink-0 font-mono text-[11px] text-pb-faint">{fmtDate(game.played_at)}</span>
      <div className="flex-1 min-w-0">
        <span className="font-semibold text-[13px] text-pb-text group-hover:text-pb-accent transition truncate block">
          {game.home_team || '—'} <span className="font-normal text-pb-dim text-[11px]">vs</span> {game.away_team || '—'}
        </span>
        {game.winning_team && (
          <span className="font-mono text-[10px] text-pb-faint block truncate">{game.winning_team} won</span>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <ResultPill result={game.result} />
        <span className="text-pb-faint text-[12px] group-hover:text-pb-accent transition">→</span>
      </div>
    </Link>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

const PERF_TABS = [
  { key: 'batting',  label: 'BATTING' },
  { key: 'bowling',  label: 'BOWLING' },
  { key: 'fielding', label: 'FIELDING' },
]

export default function TeamDetail() {
  const { clubSlug, gradeId } = useParams()
  const { club, loading: clubLoading, inactive } = useClub(clubSlug)
  const orgId = club?.id
  const fmtName = useNameFormat(club)

  const [gradeInfo, setGradeInfo] = useState(null)
  const [results, setResults] = useState([])
  const [batters, setBatters] = useState([])
  const [bowlers, setBowlers] = useState([])
  const [fielders, setFielders] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('batting')

  useClubTheme(club)

  useEffect(() => {
    if (!orgId || !gradeId) return
    setLoading(true)
    Promise.all([
      api.getGradeInfo(orgId, gradeId),
      api.getOrgResults(orgId, { gradeId }),
      api.battingLeaderboard(orgId, { gradeId, limit: 15, minRuns: 0 }),
      api.bowlingLeaderboard(orgId, { gradeId, limit: 15, minWickets: 0, minOvers: 0 }),
      api.fieldingLeaderboard(orgId, { gradeId, limit: 15 }),
    ])
      .then(([info, res, bat, bowl, field]) => {
        setGradeInfo(info)
        setResults(res)
        setBatters(bat)
        setBowlers(bowl)
        setFielders(field)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [orgId, gradeId])

  usePageMeta({
    title: gradeInfo
      ? `${gradeInfo.name} — ${gradeInfo.season_name || ''} — ${club?.name || clubSlug}`
      : `Team — ${club?.name || clubSlug}`,
  })

  if (clubLoading || loading) return <PbSpinner />
  if (inactive) return <ClubInactive />

  // Win/Loss/Draw from results
  const wins   = results.filter(g => g.result === 'WIN').length
  const losses = results.filter(g => g.result === 'LOSS').length
  const draws  = results.filter(g => g.result === 'DRAW' || g.result === 'TIE' || g.result === 'NO_RESULT').length
  const played = results.length

  // Chart data — top 6 batters by runs, top 6 bowlers by wickets
  const topBatChart = batters.slice(0, 6).map(r => ({
    name: fmtName(r.name),
    runs: r.total_runs ?? 0,
  }))
  const topBowlChart = bowlers.slice(0, 6).map(r => ({
    name: fmtName(r.name),
    wickets: r.total_wickets ?? 0,
  }))

  return (
    <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-8">

      {/* Breadcrumb */}
      <div className="flex items-center gap-2 mb-4 font-mono text-[10px] tracking-wide2 text-pb-faint">
        <Link to={`/${clubSlug}/teams`} className="hover:text-pb-accent transition">Teams</Link>
        <span>/</span>
        <span className="text-pb-dim">{gradeInfo?.name || '…'}</span>
      </div>

      <PageHeader
        eyebrow={gradeInfo?.season_name || ''}
        title={gradeInfo?.name || '…'}
      />

      {/* Season record stat tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
        <Kpi label="Wins"   value={wins}   accent />
        <Kpi label="Losses" value={losses} />
        <Kpi label="Draws"  value={draws}  />
        <Kpi label="Played" value={played} />
      </div>

      {/* Charts */}
      {(topBatChart.length > 0 || topBowlChart.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          <Card title="Top Run Scorers">
            <HorizBarChart
              data={topBatChart}
              dataKey="runs"
              unit="runs"
              color="var(--pb-accent)"
            />
          </Card>
          <Card title="Top Wicket Takers">
            <HorizBarChart
              data={topBowlChart}
              dataKey="wickets"
              unit="wkts"
              color="var(--pb-chart-series-2, #818cf8)"
            />
          </Card>
        </div>
      )}

      {/* Performers tables */}
      <Card className="mb-8" pad="p-0">
        <div className="px-4 sm:px-[18px] pt-4 sm:pt-[18px]">
          <TabBar tabs={PERF_TABS} active={activeTab} onChange={setActiveTab} />
        </div>
        <div className="pb-4">
          {activeTab === 'batting'  && <BattingTable  rows={batters}  fmt={fmtName} />}
          {activeTab === 'bowling'  && <BowlingTable  rows={bowlers}  fmt={fmtName} />}
          {activeTab === 'fielding' && <FieldingTable rows={fielders} fmt={fmtName} />}
        </div>
      </Card>

      {/* Results list */}
      {results.length > 0 && (
        <Card title={`Results (${results.length})`} pad="p-0">
          <div className="pt-2">
            {results.map(g => <ResultRow key={g.id} game={g} />)}
          </div>
        </Card>
      )}
    </div>
  )
}
