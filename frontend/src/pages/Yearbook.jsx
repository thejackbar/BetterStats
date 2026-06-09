import { useState, useEffect, useRef } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { PbSpinner, TabBar, Label, AnimatedNum } from '../lib/presskit'
import { fmtOvers, formatSeason } from '../lib/cricketFormat'
import { resolveAwardLabel } from '../lib/achievementOptions'
import { useClubTheme } from '../hooks/useClubTheme'
import { useAuth } from '../contexts/AuthContext'
import { usePageMeta } from '../hooks/usePageMeta'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip,
  AreaChart, Area, CartesianGrid,
  PieChart, Pie, Cell,
} from 'recharts'

// ─── Utility helpers ────────────────────────────────────────────────────────

// Yearbook image paths can be either legacy on-disk relative paths
// ("yearbooks/{org_id}/...") or new DB-backed serving URLs ("/api/images/...").
const imageSrc = (p) => !p ? null : (p.startsWith('/') ? p : `/uploads/${p}`)

function fmtDate(iso) {
  if (!iso) return null
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
}

function fmtRuns(n) {
  return n == null ? '—' : Number(n).toLocaleString()
}

function fmt(n, dec = 2) {
  if (n == null) return '—'
  const num = parseFloat(n)
  return isNaN(num) ? '—' : num.toFixed(dec)
}

function PlayerLink({ id, name, slug }) {
  if (!id) return <span>{name}</span>
  return (
    <Link to={`/players/${id}`} className="hover:underline" style={{ color: 'var(--pb-accent)' }}>
      {name}
    </Link>
  )
}

const ORDINALS = ['1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th']

const DISMISSAL_LABELS = {
  b: 'Bowled',
  bowled: 'Bowled',
  c: 'Caught',
  caught: 'Caught',
  'caught behind': 'Caught Behind',
  'caught and bowled': 'Caught & Bowled',
  lbw: 'LBW',
  'run out': 'Run Out',
  st: 'Stumped',
  stumped: 'Stumped',
  'hit wicket': 'Hit Wicket',
  'handled the ball': 'Handled the Ball',
  'obstructing the field': 'Obstructing the Field',
  'timed out': 'Timed Out',
  'retired hurt': 'Retired Hurt',
  'retired out': 'Retired Out',
  'did not bat': 'Did Not Bat',
  absent: 'Absent',
  dnb: 'Did Not Bat',
  unknown: 'Not Out / Unknown',
}
const DISMISSAL_COLORS = [
  'var(--pb-accent)', '#60a5fa', '#f59e0b', '#e879f9',
  '#fb923c', '#34d399', '#f87171', '#a78bfa', '#38bdf8', '#facc15',
]

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--pb-surface)', border: '1px solid var(--pb-hairline)', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
      <div style={{ color: 'var(--pb-faint)', marginBottom: 4 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color || '#4ade80', fontWeight: 600 }}>{p.value?.toLocaleString()} {p.name}</div>
      ))}
    </div>
  )
}

function abbrev(name) {
  if (!name) return ''
  const parts = name.split(' ')
  return parts.length <= 1 ? name.slice(0, 14) : `${parts[0]} ${parts[parts.length-1][0]}.`
}

// ─── Shared table components ─────────────────────────────────────────────────

function YbTable({ headers, rows, rowStyles = [], className = '' }) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-[10px] font-mono tracking-wide3 text-left border-b border-pb-hairline">
            {headers.map((h, i) => (
              <th key={i} className={`py-2.5 px-3 font-medium text-pb-faint ${i > 0 ? 'text-right' : ''}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-pb-hairline hover:bg-pb-surface2 transition-colors" style={rowStyles[i] || {}}>
              {row.map((cell, j) => (
                <td key={j} className={`py-2.5 px-3 font-mono whitespace-nowrap ${j > 0 ? 'text-right text-pb-dim' : 'text-pb-text'}`}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SectionCard({ title, label, children, className = '' }) {
  return (
    <div className={`rounded-xl border border-pb-hairline bg-pb-surface overflow-hidden ${className}`}>
      {title && (
        <div className="px-5 py-3 border-b border-pb-hairline flex items-baseline gap-3">
          <span className="font-mono text-[11px] tracking-wide3 font-semibold text-pb-faint uppercase">{title}</span>
          {label && <span className="font-mono text-[10px] text-pb-faintest">{label}</span>}
        </div>
      )}
      {children}
    </div>
  )
}

function StatCallout({ value, label, sub, accent = false, className = '' }) {
  return (
    <div className={`flex flex-col items-center justify-center py-6 px-4 text-center ${className}`}>
      <div
        className="text-3xl sm:text-5xl font-bold tabular-nums leading-none mb-2"
        style={{ color: accent ? 'var(--pb-accent)' : 'var(--pb-text)' }}
      >
        {value}
      </div>
      <div className="text-[11px] font-mono tracking-wide3 text-pb-faint uppercase">{label}</div>
      {sub && <div className="text-[11px] text-pb-faint mt-1">{sub}</div>}
    </div>
  )
}

// ─── Overview tab ────────────────────────────────────────────────────────────

function OverviewTab({ orgId, seasonId, gradeId, season, clubSlug, narrative, galleryImages }) {
  const [overview, setOverview] = useState(null)
  const [superlatives, setSuperlatives] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getYearbookOverview(orgId, seasonId, gradeId),
      api.getYearbookSuperlatives(orgId, seasonId, gradeId),
    ]).then(([ov, sup]) => {
      setOverview(ov)
      setSuperlatives(sup)
    }).finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId])

  if (loading) return <PbSpinner />

  const totalGames = parseInt(overview?.total_games || 0)
  const wins = parseInt(overview?.wins || 0)
  const losses = parseInt(overview?.losses || 0)
  const draws = parseInt(overview?.draws || 0)

  return (
    <div className="space-y-8">
      {/* Headline stat trio */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-px bg-pb-hairline rounded-xl overflow-hidden">
        <StatCallout value={overview?.total_players ?? '—'} label="Players" />
        <StatCallout value={fmtRuns(overview?.total_runs)} label="Club Runs" />
        <StatCallout value={fmtRuns(overview?.total_wickets)} label="Wickets" />
        <StatCallout value={`${wins}W ${draws}D ${losses}L`} label="Record" />
        <StatCallout
          value={totalGames > 0 ? `${Math.round(wins / totalGames * 100)}%` : '—'}
          label="Win Rate"
          className="col-span-2 sm:col-span-1"
        />
      </div>

      {/* Season Record chart */}
      {overview && parseInt(overview.total_games) > 0 && (
        <SectionCard title="Season Record">
          <div className="px-4 py-5">
            <ResponsiveContainer width="100%" height={80}>
              <BarChart data={[{
                name: 'Season',
                Won: parseInt(overview.wins || 0),
                Drew: parseInt(overview.draws || 0),
                Lost: parseInt(overview.losses || 0),
              }]} layout="vertical" margin={{ top: 0, right: 8, left: 8, bottom: 0 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" hide />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="Won" stackId="a" fill="#4ade80" radius={[4,0,0,4]} />
                <Bar dataKey="Drew" stackId="a" fill="var(--pb-faintest)" />
                <Bar dataKey="Lost" stackId="a" fill="#f87171" radius={[0,4,4,0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="flex justify-center gap-6 mt-2">
              {[['Won', '#4ade80'], ['Drew', 'var(--pb-faintest)'], ['Lost', '#f87171']].map(([l, c]) => (
                <div key={l} className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-sm" style={{ background: c }} />
                  <span className="text-[11px] font-mono text-pb-faint">{l}</span>
                </div>
              ))}
            </div>
          </div>
        </SectionCard>
      )}

      {/* Narrative / Season in Brief */}
      {narrative && (
        <div className="rounded-xl border border-pb-hairline bg-pb-surface px-6 py-5">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Season in Brief</p>
          <div className="prose prose-sm max-w-none text-pb-text leading-relaxed whitespace-pre-wrap">
            {narrative}
          </div>
        </div>
      )}

      {/* Photo gallery now lives in its own Photos tab. */}

      {/* By the Numbers */}
      {(() => {
        return (
          <div className="space-y-8">
            <p className="font-mono text-[11px] tracking-wide3 text-pb-faint uppercase">By The Numbers</p>
            {superlatives && <>

            {/* Match Stats */}
            {(overview?.total_games > 0 || superlatives.highest_team_innings?.team_runs > 0) && (
              <StatGroup title="Match Stats">
                {overview?.total_games > 0 && (
                  <SupCard label="Games Played" value={overview.total_games} />
                )}
                {overview?.total_players > 0 && (
                  <SupCard label="Players Used" value={overview.total_players} />
                )}
                {superlatives.highest_team_innings?.team_runs > 0 && (
                  <SupCard
                    label="Highest Team Innings"
                    value={fmtRuns(superlatives.highest_team_innings.team_runs)}
                    sub={superlatives.highest_team_innings.home_team}
                  />
                )}
              </StatGroup>
            )}

            {/* Batting Stats */}
            {(overview?.total_runs > 0 || superlatives?.most_runs?.player_id) && (
              <StatGroup title="Batting">
                {overview?.total_runs > 0 && (
                  <SupCard label="Total Runs" value={fmtRuns(overview.total_runs)} />
                )}
                {superlatives?.most_runs?.player_id && (
                  <SupCard
                    label="Most Runs"
                    value={fmtRuns(superlatives.most_runs.runs)}
                    name={superlatives.most_runs.name}
                    playerId={superlatives.most_runs.player_id}
                    clubSlug={clubSlug}
                  />
                )}
                {superlatives.highest_score?.player_id && (
                  <SupCard
                    label="Highest Score"
                    value={`${superlatives.highest_score.runs}${superlatives.highest_score.not_out ? '*' : ''}`}
                    name={superlatives.highest_score.name}
                    playerId={superlatives.highest_score.player_id}
                    clubSlug={clubSlug}
                    sub={superlatives.highest_score.away_team ? `vs ${superlatives.highest_score.away_team}` : null}
                  />
                )}
                {superlatives.best_partnership?.batter1_id && (
                  <SupCard
                    label={`${ORDINALS[(superlatives.best_partnership.wicket_number || 1) - 1]} Wkt Partnership`}
                    value={superlatives.best_partnership.runs}
                    name={`${superlatives.best_partnership.batter1_name} & ${superlatives.best_partnership.batter2_name}`}
                  />
                )}
                {overview?.total_hundreds > 0 && (
                  <SupCard label="Centuries" value={overview.total_hundreds} />
                )}
                {overview?.total_fifties > 0 && (
                  <SupCard label="Half Centuries" value={overview.total_fifties} />
                )}
                {superlatives?.most_ducks?.player_id && superlatives.most_ducks.ducks > 0 && (
                  <SupCard
                    label="Most Ducks"
                    value={superlatives.most_ducks.ducks}
                    name={superlatives.most_ducks.name}
                    playerId={superlatives.most_ducks.player_id}
                    clubSlug={clubSlug}
                    muted
                  />
                )}
              </StatGroup>
            )}

            {/* Bowling Stats */}
            {(overview?.total_wickets > 0 || superlatives?.most_wickets?.player_id) && (
              <StatGroup title="Bowling">
                {overview?.total_wickets > 0 && (
                  <SupCard label="Total Wickets" value={overview.total_wickets} />
                )}
                {superlatives?.most_wickets?.player_id && (
                  <SupCard
                    label="Most Wickets"
                    value={superlatives.most_wickets.wickets}
                    name={superlatives.most_wickets.name}
                    playerId={superlatives.most_wickets.player_id}
                    clubSlug={clubSlug}
                  />
                )}
                {superlatives.best_bowling?.player_id && (
                  <SupCard
                    label="Best Figures"
                    value={`${superlatives.best_bowling.wickets}/${superlatives.best_bowling.runs_conceded}`}
                    name={superlatives.best_bowling.name}
                    playerId={superlatives.best_bowling.player_id}
                    clubSlug={clubSlug}
                  />
                )}
                {superlatives?.best_bowling_average?.player_id && (
                  <SupCard
                    label="Best Average"
                    value={fmt(superlatives.best_bowling_average.average)}
                    name={superlatives.best_bowling_average.name}
                    playerId={superlatives.best_bowling_average.player_id}
                    clubSlug={clubSlug}
                    sub={`${superlatives.best_bowling_average.wickets} wkts`}
                  />
                )}
                {superlatives?.most_fifers?.player_id && (
                  <SupCard
                    label="Most 5-Wicket Hauls"
                    value={superlatives.most_fifers.fifers}
                    name={superlatives.most_fifers.name}
                    playerId={superlatives.most_fifers.player_id}
                    clubSlug={clubSlug}
                  />
                )}
              </StatGroup>
            )}

            </>}
          </div>
        )
      })()}
    </div>
  )
}

function SupCard({ label, value, name, playerId, clubSlug, sub, accent = false, muted = false }) {
  return (
    <div className="yb-futuristic-card">
      <div className="yb-fc-content">
        <div className="font-mono text-[11px] tracking-wide text-pb-faint uppercase leading-tight">{label}</div>
        <div
          className="text-xl font-bold tabular-nums leading-none"
          style={{ color: muted ? 'var(--pb-amber)' : 'var(--pb-accent)' }}
        >
          {value}
        </div>
        {name && playerId && clubSlug && (
          <div className="text-[12px] leading-tight"><PlayerLink id={playerId} name={name} slug={clubSlug} /></div>
        )}
        {name && !playerId && <span className="text-[12px] text-pb-dim leading-tight">{name}</span>}
        {sub && <div className="text-[11px] text-pb-faint leading-tight">{sub}</div>}
      </div>
    </div>
  )
}

function StatGroup({ title, children }) {
  return (
    <div>
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-3">{title}</p>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
        {children}
      </div>
    </div>
  )
}

// ─── Results tab ─────────────────────────────────────────────────────────────

function ResultsTab({ orgId, seasonId, gradeId, clubSlug }) {
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.getYearbookResults(orgId, seasonId, gradeId)
      .then(setResults)
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId])

  if (loading) return <PbSpinner />
  if (!results?.length) return <p className="text-pb-faintest text-sm italic py-8 text-center">No match results found for this selection.</p>

  // Group by grade
  const byGrade = results.reduce((acc, g) => {
    const key = g.grade_name || 'Unknown Grade'
    if (!acc[key]) acc[key] = []
    acc[key].push(g)
    return acc
  }, {})

  const allGames = results
    .filter(g => g.played_at)
    .sort((a, b) => new Date(a.played_at) - new Date(b.played_at))

  let cumWins = 0, cumLosses = 0
  const progressionData = allGames.map(g => {
    if (['win','won'].includes(g.result?.toLowerCase())) cumWins++
    else if (['loss','lost'].includes(g.result?.toLowerCase())) cumLosses++
    return {
      date: fmtDate(g.played_at),
      Wins: cumWins,
      Losses: cumLosses,
    }
  })

  return (
    <div className="space-y-6">
      {progressionData.length > 1 && (
        <SectionCard title="Season Progression">
          <div className="px-4 py-5">
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={progressionData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <defs>
                  <linearGradient id="winsGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4ade80" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#4ade80" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="lossesGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f87171" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#f87171" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--pb-hairline)" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: 'var(--pb-faintest)', fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fill: 'var(--pb-faintest)', fontSize: 10 }} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="Wins" stroke="#4ade80" strokeWidth={2} fill="url(#winsGrad)" dot={false} />
                <Area type="monotone" dataKey="Losses" stroke="#f87171" strokeWidth={1.5} fill="url(#lossesGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      )}
      {Object.entries(byGrade).map(([gradeName, games]) => (
        <SectionCard key={gradeName} title={gradeName}>
          <YbTable
            headers={['Date', 'Opponent', 'Result', 'Top Bat', 'Top Bowl']}
            rowStyles={games.map(g =>
              ['win','won'].includes(g.result?.toLowerCase())
                ? { background: 'rgba(74,222,128,0.07)' }
                : ['loss','lost'].includes(g.result?.toLowerCase())
                ? { background: 'rgba(248,113,113,0.07)' }
                : {}
            )}
            rows={games.map(g => {
              const resultColor = ['win','won'].includes(g.result?.toLowerCase()) ? '#4ade80' : ['loss','lost'].includes(g.result?.toLowerCase()) ? '#f87171' : 'var(--pb-dim)'
              return [
                <span className="text-pb-faint text-[12px]">{fmtDate(g.played_at) || '—'}</span>,
                <span>{g.home_team && g.away_team ? `${g.home_team} vs ${g.away_team}` : (g.home_team || g.away_team || '—')}</span>,
                <span className="font-semibold" style={{ color: resultColor }}>
                  {g.result ? g.result.charAt(0).toUpperCase() + g.result.slice(1).toLowerCase() : '—'}
                </span>,
                g.top_batter ? (
                  <span>
                    <PlayerLink id={g.top_batter_id} name={g.top_batter} slug={clubSlug} />
                    <span className="text-pb-faint ml-1">{g.top_runs}{g.top_batter_no ? '*' : ''}</span>
                  </span>
                ) : '—',
                g.top_bowler ? (
                  <span>
                    <PlayerLink id={g.top_bowler_id} name={g.top_bowler} slug={clubSlug} />
                    <span className="text-pb-faint ml-1">{g.top_wickets}/{g.top_bowl_runs}</span>
                  </span>
                ) : '—',
              ]
            })}
          />
        </SectionCard>
      ))}
    </div>
  )
}

// ─── Batting tab ─────────────────────────────────────────────────────────────

function BattingTab({ orgId, seasonId, gradeId, clubSlug }) {
  const [data, setData] = useState(null)
  const [dismissals, setDismissals] = useState(null)
  const [partnerships, setPartnerships] = useState(null)
  const [minInnings, setMinInnings] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getYearbookBatting(orgId, seasonId, { gradeId, minInnings }),
      api.getYearbookDismissals(orgId, seasonId, gradeId),
      api.getYearbookPartnerships(orgId, seasonId, gradeId),
    ]).then(([b, d, p]) => {
      setData(b)
      setDismissals(d)
      setPartnerships(p)
    }).finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId, minInnings])

  if (loading) return <PbSpinner />

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] font-mono text-pb-faint tracking-wide3 uppercase">Min innings:</span>
        {[1, 3, 5, 10].map(n => (
          <button
            key={n}
            onClick={() => setMinInnings(n)}
            className={`px-3 py-1 rounded font-mono text-[11px] tracking-wide border transition-colors ${
              minInnings === n
                ? 'border-pb-hairline2 bg-pb-surface2 text-pb-text'
                : 'border-pb-hairline text-pb-faint hover:border-pb-hairline2 hover:text-pb-dim'
            }`}
          >{n}+</button>
        ))}
      </div>

      {data?.length > 0 && (
        <SectionCard title="Batting Honours">
          <YbTable
            headers={['Player', 'M', 'Inn', 'Runs', 'Avg', 'SR', 'HS', '50s', '100s', 'Ducks']}
            rows={data.map((p, i) => [
              <span className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-pb-faintest w-5 text-right">{i + 1}</span>
                <PlayerLink id={p.player_id} name={p.name} slug={clubSlug} />
              </span>,
              p.matches ?? '—',
              p.innings ?? '—',
              <span style={{ color: 'var(--pb-accent)', fontWeight: 600 }}>{fmtRuns(p.runs)}</span>,
              fmt(p.average),
              fmt(p.strike_rate),
              p.high_score != null ? `${p.high_score}${p.hs_not_out ? '*' : ''}` : '—',
              p.fifties ?? '—',
              p.hundreds != null && p.hundreds > 0
                ? <span style={{ color: 'var(--pb-amber)' }}>{p.hundreds}</span>
                : (p.hundreds ?? '—'),
              p.ducks ?? '—',
            ])}
          />
        </SectionCard>
      )}

      {!data?.length && (
        <SectionCard title="Batting Honours">
          <p className="text-pb-faintest text-sm italic px-5 py-4">No batting data for this selection.</p>
        </SectionCard>
      )}

      {data?.length > 0 && (
        <SectionCard title="Runs Scored — Top Players">
          <div className="px-4 py-4">
            <ResponsiveContainer width="100%" height={Math.min(data.length, 15) * 28 + 20}>
              <BarChart
                data={data.slice(0, 15).map(p => ({ name: abbrev(p.name), runs: parseInt(p.runs || 0), id: p.player_id }))}
                layout="vertical"
                margin={{ top: 0, right: 40, left: 90, bottom: 0 }}
              >
                <XAxis type="number" tick={{ fill: 'var(--pb-faint)', fontSize: 10 }} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="name" tick={{ fill: 'var(--pb-dim)', fontSize: 11 }} tickLine={false} axisLine={false} width={88} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="runs" name="runs" fill="var(--pb-accent)" fillOpacity={0.8} radius={[0,3,3,0]} barSize={14} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      )}

      {dismissals?.length > 0 && (() => {
        const total = dismissals.reduce((s, x) => s + parseInt(x.count || 0), 0)
        const pieData = dismissals.map(d => ({
          name: DISMISSAL_LABELS[d.dismissal_type?.toLowerCase()] || d.dismissal_type?.replace(/_/g, ' ') || 'Unknown',
          value: parseInt(d.count || 0),
          pct: total > 0 ? Math.round(parseInt(d.count) / total * 100) : 0,
        }))
        return (
          <SectionCard title="How We Got Out">
            <div className="flex flex-col sm:flex-row items-center gap-4 px-4 py-5">
              <div className="shrink-0">
                <PieChart width={200} height={200}>
                  <Pie
                    data={pieData}
                    cx={100}
                    cy={100}
                    innerRadius={58}
                    outerRadius={90}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={DISMISSAL_COLORS[i % DISMISSAL_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null
                      const d = payload[0]
                      return (
                        <div style={{ background: 'var(--pb-surface)', border: '1px solid var(--pb-hairline)', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                          <div style={{ color: d.payload.fill, fontWeight: 600 }}>{d.name}</div>
                          <div style={{ color: 'var(--pb-dim)' }}>{d.value} ({d.payload.pct}%)</div>
                        </div>
                      )
                    }}
                  />
                </PieChart>
              </div>
              <div className="flex-1 space-y-1.5 min-w-0">
                {pieData.map((d, i) => (
                  <div key={i} className="flex items-center gap-2.5">
                    <span
                      className="shrink-0 w-2.5 h-2.5 rounded-full"
                      style={{ background: DISMISSAL_COLORS[i % DISMISSAL_COLORS.length] }}
                    />
                    <span className="text-[12px] text-pb-dim flex-1 truncate">{d.name}</span>
                    <span className="font-mono text-[11px] text-pb-faint shrink-0">{d.value}</span>
                    <span className="font-mono text-[11px] text-pb-faintest w-8 text-right shrink-0">{d.pct}%</span>
                  </div>
                ))}
              </div>
            </div>
          </SectionCard>
        )
      })()}

      {partnerships && (
        <div className="grid sm:grid-cols-2 gap-6">
          <SectionCard title="Top Partnerships">
            {partnerships.top_partnerships?.length ? (
              <YbTable
                headers={['Batters', 'Wkt', 'Runs']}
                rows={partnerships.top_partnerships.map((p, i) => [
                  <span>
                    <span className="font-mono text-[11px] text-pb-faintest mr-2">{i + 1}</span>
                    <PlayerLink id={p.batter1_id} name={p.batter1_name} slug={clubSlug} />
                    <span className="text-pb-faint mx-1">&amp;</span>
                    <PlayerLink id={p.batter2_id} name={p.batter2_name} slug={clubSlug} />
                  </span>,
                  ORDINALS[(p.wicket_number || 1) - 1],
                  <span style={{ color: 'var(--pb-accent)', fontWeight: 600 }}>{p.runs}</span>,
                ])}
              />
            ) : (
              <p className="text-pb-faintest text-sm italic px-5 py-4">No partnership data.</p>
            )}
          </SectionCard>

          <SectionCard title="Best Partnership by Wicket">
            {partnerships.by_wicket?.length ? (
              <YbTable
                headers={['Wicket', 'Batters', 'Runs']}
                rows={partnerships.by_wicket.map(p => [
                  <span className="text-pb-faint">{ORDINALS[(p.wicket_number || 1) - 1]}</span>,
                  <span>
                    <PlayerLink id={p.batter1_id} name={p.batter1_name} slug={clubSlug} />
                    <span className="text-pb-faint mx-1">&amp;</span>
                    <PlayerLink id={p.batter2_id} name={p.batter2_name} slug={clubSlug} />
                  </span>,
                  <span style={{ color: 'var(--pb-accent)', fontWeight: 600 }}>{p.runs}</span>,
                ])}
              />
            ) : (
              <p className="text-pb-faintest text-sm italic px-5 py-4">No partnership data.</p>
            )}
          </SectionCard>
        </div>
      )}
    </div>
  )
}

// ─── Bowling tab ──────────────────────────────────────────────────────────────

function BowlingTab({ orgId, seasonId, gradeId, clubSlug }) {
  const [data, setData] = useState(null)
  const [minWickets, setMinWickets] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.getYearbookBowling(orgId, seasonId, { gradeId, minWickets })
      .then(setData)
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId, minWickets])

  if (loading) return <PbSpinner />

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] font-mono text-pb-faint tracking-wide3 uppercase">Min wickets:</span>
        {[1, 5, 10, 20].map(n => (
          <button
            key={n}
            onClick={() => setMinWickets(n)}
            className={`px-3 py-1 rounded font-mono text-[11px] tracking-wide border transition-colors ${
              minWickets === n
                ? 'border-pb-hairline2 bg-pb-surface2 text-pb-text'
                : 'border-pb-hairline text-pb-faint hover:border-pb-hairline2 hover:text-pb-dim'
            }`}
          >{n}+</button>
        ))}
      </div>

      {data?.length > 0 && (
        <SectionCard title="Bowling Honours">
          <YbTable
            headers={['Player', 'M', 'Wkts', 'Overs', 'Avg', 'Econ', 'SR', 'Best', '5WI']}
            rows={data.map((p, i) => [
              <span className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-pb-faintest w-5 text-right">{i + 1}</span>
                <PlayerLink id={p.player_id} name={p.name} slug={clubSlug} />
              </span>,
              p.matches ?? '—',
              <span style={{ color: 'var(--pb-accent)', fontWeight: 600 }}>{p.wickets ?? '—'}</span>,
              fmtOvers(p.overs),
              fmt(p.average),
              fmt(p.economy),
              fmt(p.strike_rate),
              p.best_figures || '—',
              p.five_fors > 0
                ? <span style={{ color: 'var(--pb-amber)' }}>{p.five_fors}</span>
                : (p.five_fors ?? '—'),
            ])}
          />
        </SectionCard>
      )}

      {!data?.length && (
        <SectionCard title="Bowling Honours">
          <p className="text-pb-faintest text-sm italic px-5 py-4">No bowling data for this selection.</p>
        </SectionCard>
      )}

      {data?.length > 0 && (
        <SectionCard title="Wickets Taken — Top Bowlers">
          <div className="px-4 py-4">
            <ResponsiveContainer width="100%" height={Math.min(data.length, 15) * 28 + 20}>
              <BarChart
                data={data.slice(0, 15).map(p => ({ name: abbrev(p.name), wickets: parseInt(p.wickets || 0) }))}
                layout="vertical"
                margin={{ top: 0, right: 40, left: 90, bottom: 0 }}
              >
                <XAxis type="number" tick={{ fill: 'var(--pb-faint)', fontSize: 10 }} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="name" tick={{ fill: 'var(--pb-dim)', fontSize: 11 }} tickLine={false} axisLine={false} width={88} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="wickets" name="wickets" fill="var(--pb-accent)" fillOpacity={0.8} radius={[0,3,3,0]} barSize={14} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      )}

      {data?.length > 0 && (() => {
        const figRows = data
          .filter(p => p.best_wickets != null && p.best_wickets > 0)
          .slice()
          .sort((a, b) => {
            if (b.best_wickets !== a.best_wickets) return b.best_wickets - a.best_wickets
            const runsA = a.best_figures ? parseInt(a.best_figures.split('/')[1] || '9999') : 9999
            const runsB = b.best_figures ? parseInt(b.best_figures.split('/')[1] || '9999') : 9999
            return runsA - runsB
          })
          .slice(0, 20)
        return figRows.length > 0 ? (
          <SectionCard title="Best Bowling Figures">
            <YbTable
              headers={['Player', 'Best', 'Wkts', 'Overs', 'Avg']}
              rows={figRows.map((p, i) => [
                <span className="flex items-center gap-2">
                  <span className="font-mono text-[11px] text-pb-faintest w-5 text-right">{i + 1}</span>
                  <PlayerLink id={p.player_id} name={p.name} slug={clubSlug} />
                </span>,
                <span style={{ color: 'var(--pb-accent)', fontWeight: 600 }}>{p.best_figures || '—'}</span>,
                p.wickets ?? '—',
                fmtOvers(p.overs),
                fmt(p.average),
              ])}
            />
          </SectionCard>
        ) : null
      })()}

    </div>
  )
}

// ─── Fielding tab ─────────────────────────────────────────────────────────────

function FieldingTab({ orgId, seasonId, gradeId, clubSlug }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.getYearbookFielding(orgId, seasonId, { gradeId })
      .then(setData)
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId])

  if (loading) return <PbSpinner />

  return (
    <div className="space-y-6">
      <SectionCard title="Fielding Honours">
        {data?.length ? (
          <YbTable
            headers={['Player', 'M', 'Ct', 'Ct (WK)', 'ROs', 'Stpgs', 'Total']}
            rows={data.map((p, i) => [
              <span className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-pb-faintest w-5 text-right">{i + 1}</span>
                <PlayerLink id={p.player_id} name={p.name} slug={clubSlug} />
              </span>,
              p.matches ?? '—',
              p.catches_non_wk ?? '—',
              p.catches_wk > 0 ? p.catches_wk : '—',
              p.run_outs ?? '—',
              p.stumpings > 0 ? p.stumpings : '—',
              <span style={{ color: 'var(--pb-accent)', fontWeight: 600 }}>{p.total_dismissals ?? '—'}</span>,
            ])}
          />
        ) : (
          <p className="text-pb-faintest text-sm italic px-5 py-4">No fielding data for this selection.</p>
        )}
      </SectionCard>

    </div>
  )
}

// ─── All Rounders tab ─────────────────────────────────────────────────────────

function AllroundersTab({ orgId, seasonId, gradeId, clubSlug }) {
  const [data, setData] = useState(null)
  const [minRuns, setMinRuns] = useState(100)
  const [minWickets, setMinWickets] = useState(5)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.getYearbookAllrounders(orgId, seasonId, { gradeId, minRuns, minWickets })
      .then(setData)
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId, minRuns, minWickets])

  if (loading) return <PbSpinner />

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[11px] font-mono text-pb-faint tracking-wide3 uppercase">Min runs:</span>
          {[50, 100, 200, 300].map(n => (
            <button
              key={n}
              onClick={() => setMinRuns(n)}
              className={`px-3 py-1 rounded font-mono text-[11px] tracking-wide border transition-colors ${
                minRuns === n
                  ? 'border-pb-hairline2 bg-pb-surface2 text-pb-text'
                  : 'border-pb-hairline text-pb-faint hover:border-pb-hairline2 hover:text-pb-dim'
              }`}
            >{n}+</button>
          ))}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[11px] font-mono text-pb-faint tracking-wide3 uppercase">Min wickets:</span>
          {[3, 5, 10, 20].map(n => (
            <button
              key={n}
              onClick={() => setMinWickets(n)}
              className={`px-3 py-1 rounded font-mono text-[11px] tracking-wide border transition-colors ${
                minWickets === n
                  ? 'border-pb-hairline2 bg-pb-surface2 text-pb-text'
                  : 'border-pb-hairline text-pb-faint hover:border-pb-hairline2 hover:text-pb-dim'
              }`}
            >{n}+</button>
          ))}
        </div>
      </div>

      <SectionCard title="All Rounders">
        {data?.length ? (
          <YbTable
            headers={['Player', 'M', 'Runs', 'Bat Avg', 'Wkts', 'Bowl Avg', 'Index']}
            rows={data.map((p, i) => [
              <span className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-pb-faintest w-5 text-right">{i + 1}</span>
                <PlayerLink id={p.player_id} name={p.name} slug={clubSlug} />
              </span>,
              p.matches ?? '—',
              fmtRuns(p.runs),
              fmt(p.bat_avg),
              p.wickets ?? '—',
              fmt(p.bowl_avg),
              <span style={{ color: 'var(--pb-amber)', fontWeight: 600 }}>{p.allrounder_index ?? '—'}</span>,
            ])}
          />
        ) : (
          <p className="text-pb-faintest text-sm italic px-5 py-4">No all-rounders meet these thresholds. Try lowering the minimums.</p>
        )}
      </SectionCard>
    </div>
  )
}

// ─── Awards tab ───────────────────────────────────────────────────────────────

function AwardsTab({ orgId, seasonId, gradeId, clubSlug, yearbookData, awardDefs }) {
  const [milestones, setMilestones] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getYearbookMilestones(orgId, seasonId)
      .then(setMilestones)
      .finally(() => setLoading(false))
  }, [orgId, seasonId])

  const clubAwards = yearbookData?.awards || []
  const pulledAwards = yearbookData?.pulled_awards || []
  const featuredIds = new Set(yearbookData?.featured_achievement_ids || [])
  const featuredAwards = pulledAwards.filter(a => featuredIds.has(String(a.id)))
  const featuredByCategory = featuredAwards.reduce((acc, a) => {
    const cat = a.category || 'Other'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(a)
    return acc
  }, {})
  const CATEGORY_ORDER = [
    'Club Award', 'Premiership', 'Association Award',
    'Hall of Fame', 'Life Membership', 'Office Bearer', 'Milestone',
  ]
  const orderedCategories = [
    ...CATEGORY_ORDER.filter(c => featuredByCategory[c]),
    ...Object.keys(featuredByCategory).filter(c => !CATEGORY_ORDER.includes(c)),
  ]

  return (
    <div className="space-y-6">
      {/* Club Awards (added directly to the yearbook) */}
      {clubAwards.length > 0 && (
        <SectionCard title="Club Awards">
          <div className="grid sm:grid-cols-2 gap-px bg-pb-surface2">
            {clubAwards.map(a => (
              <div key={a.id} className="bg-pb-surface px-5 py-4">
                <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">{a.award_name}</div>
                <div className="text-[15px] font-semibold text-pb-text">
                  {a.player_id
                    ? <PlayerLink id={a.player_id} name={a.player_name || a.name_override} slug={clubSlug} />
                    : <span>{a.name_override}</span>
                  }
                </div>
                {a.notes && <div className="text-[12px] text-pb-faint mt-1 italic">{a.notes}</div>}
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {/* Toggled-on awards from /admin/awards, grouped by category */}
      {orderedCategories.map(cat => (
        <SectionCard key={cat} title={cat === 'Club Award' ? 'Club Awards' : (cat.endsWith('s') ? cat : `${cat}s`)}>
          <div className="grid sm:grid-cols-2 gap-px bg-pb-surface2">
            {featuredByCategory[cat].map(a => (
              <div key={`pulled-${a.id}`} className="bg-pb-surface px-5 py-4">
                <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">
                  {resolveAwardLabel(awardDefs, a.category, a.subcategory, a.achievement)}
                  {a.subcategory && <span className="text-pb-faintest normal-case ml-1.5">· {a.subcategory}</span>}
                </div>
                <div className="text-[15px] font-semibold text-pb-text">
                  {a.player_id
                    ? <PlayerLink id={a.player_id} name={a.player_name} slug={clubSlug} />
                    : <span>{a.player_name || '—'}</span>
                  }
                </div>
                {a.detail && <div className="text-[12px] text-pb-faint mt-1 italic">{a.detail}</div>}
              </div>
            ))}
          </div>
        </SectionCard>
      ))}

      {loading ? <PbSpinner /> : milestones?.length > 0 && (
        <SectionCard title="Career Milestones This Season">
          <div className="divide-y divide-pb-hairline">
            {milestones.map(m => (
              <div key={m.id} className="flex items-center gap-4 px-5 py-3">
                <div className="w-8 h-8 rounded-full flex items-center justify-center text-[14px]"
                     style={{ background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)' }}>
                  🏆
                </div>
                <div className="flex-1">
                  <PlayerLink id={m.player_id} name={m.player_name} slug={clubSlug} />
                  <div className="font-mono text-[11px] text-pb-faint mt-0.5">
                    {m.milestone_type} — {m.milestone_value?.toLocaleString()}
                    {m.achieved_at && <span className="ml-2">{fmtDate(m.achieved_at)}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {!loading && milestones?.length === 0 &&
       clubAwards.length === 0 && featuredAwards.length === 0 && (
        <div className="rounded-xl border border-pb-hairline border-dashed px-6 py-8 text-center">
          <p className="font-mono text-[11px] text-pb-faintest uppercase tracking-wide3">Awards</p>
          <p className="text-pb-faintest text-sm mt-2">
            Club admins can add award winners from the Yearbook admin panel.
          </p>
        </div>
      )}
    </div>
  )
}

// ─── Players tab ─────────────────────────────────────────────────────────────

function PlayersTab({ orgId, seasonId, gradeId, clubSlug }) {
  const [players, setPlayers] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.getYearbookPlayers(orgId, seasonId, gradeId)
      .then(setPlayers)
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId])

  if (loading) return <PbSpinner />
  if (!players?.length) return <p className="text-pb-faintest text-sm italic py-8 text-center">No player data for this selection.</p>

  const filteredPlayers = players.filter(p => p.name.toLowerCase().includes(search.toLowerCase()))

  return (
    <div>
      <input
        type="text"
        placeholder="Search players..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="w-full sm:w-64 bg-pb-surface2 border border-pb-hairline rounded px-3 py-1.5 text-[13px] text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-hairline2 mb-4"
      />
      <p className="text-[12px] text-pb-faintest mb-4 font-mono">{filteredPlayers.length} players · click any card for full breakdown</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {filteredPlayers.map(p => (
          <div
            key={p.player_id}
            onClick={() => setExpanded(expanded === p.player_id ? null : p.player_id)}
            className={`rounded-xl border cursor-pointer transition-all ${
              expanded === p.player_id
                ? 'border-pb-hairline2 bg-pb-surface2'
                : 'border-pb-hairline bg-pb-surface hover:border-pb-hairline2 hover:bg-pb-surface2'
            }`}
          >
            <div className="px-4 py-3">
              <div className="font-medium text-[13px] text-pb-text leading-tight mb-1.5">{p.name}</div>
              <div className="grid grid-cols-3 gap-x-2 gap-y-1">
                <div><span className="font-mono text-[10px] text-pb-faint">M </span><span className="font-mono text-[10px] text-pb-dim">{p.matches ?? '—'}</span></div>
                <div><span className="font-mono text-[10px] text-pb-faint">Runs </span><span className="font-mono text-[10px] text-pb-dim">{p.runs != null ? fmtRuns(p.runs) : '—'}</span></div>
                <div><span className="font-mono text-[10px] text-pb-faint">Avg </span><span className="font-mono text-[10px] text-pb-dim">{fmt(p.bat_avg)}</span></div>
                <div><span className="font-mono text-[10px] text-pb-faint">Wkts </span><span className="font-mono text-[10px] text-pb-dim">{p.wickets ?? '—'}</span></div>
                <div><span className="font-mono text-[10px] text-pb-faint">Bowl </span><span className="font-mono text-[10px] text-pb-dim">{fmt(p.bowl_avg)}</span></div>
                <div><span className="font-mono text-[10px] text-pb-faint">Ct </span><span className="font-mono text-[10px] text-pb-dim">{p.catches ?? p.dismissals ?? '—'}</span></div>
              </div>
            </div>
            {expanded === p.player_id && (
              <div className="border-t border-pb-hairline px-4 py-3 space-y-1">
                {p.runs > 0 && (
                  <div className="flex justify-between text-[12px]">
                    <span className="text-pb-faint">Runs</span>
                    <span style={{ color: 'var(--pb-accent)' }}>{fmtRuns(p.runs)} {p.high_score != null ? `(HS ${p.high_score})` : ''}</span>
                  </div>
                )}
                {p.bat_avg && (
                  <div className="flex justify-between text-[12px]">
                    <span className="text-pb-faint">Bat Avg</span>
                    <span className="text-pb-dim">{fmt(p.bat_avg)}</span>
                  </div>
                )}
                {p.wickets > 0 && (
                  <div className="flex justify-between text-[12px]">
                    <span className="text-pb-faint">Wickets</span>
                    <span style={{ color: 'var(--pb-accent)' }}>{p.wickets}</span>
                  </div>
                )}
                {p.bowl_avg && p.wickets > 0 && (
                  <div className="flex justify-between text-[12px]">
                    <span className="text-pb-faint">Bowl Avg</span>
                    <span className="text-pb-dim">{fmt(p.bowl_avg)}</span>
                  </div>
                )}
                {p.dismissals > 0 && (
                  <div className="flex justify-between text-[12px]">
                    <span className="text-pb-faint">Dismissals</span>
                    <span className="text-pb-dim">{p.dismissals}</span>
                  </div>
                )}
                <div className="pt-1">
                  <Link
                    to={`/players/${p.player_id}`}
                    className="text-[11px] font-mono tracking-wide"
                    style={{ color: 'var(--pb-accent)' }}
                    onClick={e => e.stopPropagation()}
                  >
                    Full profile →
                  </Link>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Grades tab ───────────────────────────────────────────────────────────────

function GradesTab({ orgId, seasonId, clubSlug }) {
  const [grades, setGrades] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getYearbookGrades(orgId, seasonId)
      .then(setGrades)
      .finally(() => setLoading(false))
  }, [orgId, seasonId])

  if (loading) return <PbSpinner />
  if (!grades?.length) return <p className="text-pb-faintest text-sm italic py-8 text-center">No grade data available.</p>

  return (
    <div className="grid sm:grid-cols-2 gap-4">
      {grades.map(g => (
        <SectionCard key={g.id} title={g.name}>
          <div className="grid grid-cols-2 divide-x divide-pb-hairline">
            <StatCallout value={fmtRuns(g.runs)} label="Runs" />
            <StatCallout value={g.wickets ?? '—'} label="Wickets" />
          </div>
          {(g.wins > 0 || g.losses > 0) && (
            <div className="flex gap-4 px-5 py-2 border-t border-pb-hairline">
              <span className="font-mono text-[11px]" style={{ color: '#4ade80' }}>{g.wins ?? 0}W</span>
              <span className="font-mono text-[11px]" style={{ color: '#f87171' }}>{g.losses ?? 0}L</span>
            </div>
          )}
          <div className="border-t border-pb-hairline px-5 py-3 space-y-2">
            {g.top_batter?.name && (
              <div className="flex items-center gap-3 text-[12px]">
                <span className="text-pb-faint w-24 font-mono text-[10px] uppercase tracking-wide">Top Bat</span>
                <span className="flex-1">
                  <PlayerLink id={g.top_batter.id} name={g.top_batter.name} slug={clubSlug} />
                  <span className="text-pb-faint ml-2">{fmtRuns(g.top_batter.runs)} runs</span>
                </span>
              </div>
            )}
            {g.top_bowler?.name && (
              <div className="flex items-center gap-3 text-[12px]">
                <span className="text-pb-faint w-24 font-mono text-[10px] uppercase tracking-wide">Top Bowl</span>
                <span className="flex-1">
                  <PlayerLink id={g.top_bowler.id} name={g.top_bowler.name} slug={clubSlug} />
                  <span className="text-pb-faint ml-2">{g.top_bowler.wickets} wickets</span>
                </span>
              </div>
            )}
            {g.high_score != null && (
              <div className="flex items-center gap-3 text-[12px]">
                <span className="text-pb-faint w-24 font-mono text-[10px] uppercase tracking-wide">HS</span>
                <span className="flex-1">
                  {g.high_score_player_id
                    ? <PlayerLink id={g.high_score_player_id} name={g.high_score_name} slug={clubSlug} />
                    : <span className="text-pb-dim">{g.high_score_name}</span>
                  }
                  <span className="text-pb-faint ml-2">{g.high_score}{g.high_score_not_out ? '*' : ''}</span>
                </span>
              </div>
            )}
            {g.best_bowling_wickets != null && (
              <div className="flex items-center gap-3 text-[12px]">
                <span className="text-pb-faint w-24 font-mono text-[10px] uppercase tracking-wide">Best Bowl</span>
                <span className="flex-1">
                  {g.best_bowling_player_id
                    ? <PlayerLink id={g.best_bowling_player_id} name={g.best_bowling_name} slug={clubSlug} />
                    : <span className="text-pb-dim">{g.best_bowling_name}</span>
                  }
                  <span className="text-pb-faint ml-2">{g.best_bowling_wickets}/{g.best_bowling_runs}</span>
                </span>
              </div>
            )}
          </div>
        </SectionCard>
      ))}
    </div>
  )
}

// ─── Main Yearbook page ───────────────────────────────────────────────────────

function ReportsTab({ customSections }) {
  return (
    <div className="space-y-8">
      {(customSections || []).map(s => (
        <div key={s.id} className="rounded-xl border border-pb-hairline bg-pb-surface px-6 py-5">
          <div className="prose prose-sm max-w-none text-pb-text leading-relaxed whitespace-pre-wrap">
            {s.content_markdown}
          </div>
        </div>
      ))}
    </div>
  )
}

function PhotosTab({ galleryImages }) {
  const [lightbox, setLightbox] = useState(null)
  if (!galleryImages?.length) return null

  return (
    <div>
      <div className="mb-6">
        <p className="font-mono text-[10px] tracking-wide3 text-white/40 uppercase mb-1">Photo Gallery</p>
        <p className="text-[12px] text-white/50">{galleryImages.length} {galleryImages.length === 1 ? 'photo' : 'photos'} from the season.</p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
        {galleryImages.map(img => (
          <button
            key={img.id}
            onClick={() => setLightbox(img)}
            className="aspect-square block overflow-hidden rounded border border-white/8 hover:border-white/20 transition-colors group"
          >
            <img
              src={imageSrc(img.file_path)}
              alt={img.caption || ''}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
            />
          </button>
        ))}
      </div>

      {lightbox && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4"
          onClick={() => setLightbox(null)}
        >
          <button
            onClick={() => setLightbox(null)}
            className="absolute top-4 right-4 text-white/60 hover:text-white text-2xl font-mono w-10 h-10 flex items-center justify-center"
            aria-label="Close"
          >
            ×
          </button>
          <img
            src={imageSrc(lightbox.file_path)}
            alt={lightbox.caption || ''}
            className="max-w-full max-h-[90vh] object-contain rounded"
            onClick={(e) => e.stopPropagation()}
          />
          {lightbox.caption && (
            <p className="absolute bottom-6 left-1/2 -translate-x-1/2 text-white/70 text-sm font-mono bg-black/40 px-3 py-1 rounded">
              {lightbox.caption}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Sponsors tab ─────────────────────────────────────────────────────────────

function SponsorsTab({ clubSlug }) {
  const [sponsors, setSponsors] = useState([])
  const [loading, setLoading] = useState(true)
  const [hidden, setHidden] = useState(new Set())

  useEffect(() => {
    api.getClubSponsors(clubSlug).then(data => {
      const list = data?.sponsors || []
      setSponsors(list)
      if (list.length > 5) {
        const shuffled = [...list].sort(() => Math.random() - 0.5)
        setHidden(new Set(shuffled.slice(5).map(s => s.id)))
      }
    }).finally(() => setLoading(false))
  }, [clubSlug])

  const toggle = (id) => setHidden(h => {
    const next = new Set(h)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  if (loading) return <PbSpinner />

  if (!sponsors.length) return (
    <div className="rounded-xl border border-pb-hairline border-dashed px-6 py-10 text-center">
      <p className="font-mono text-[11px] text-pb-faintest uppercase tracking-wide3">No sponsors</p>
      <p className="text-pb-faintest text-sm mt-2">Add sponsors in the Admin area to display them here.</p>
    </div>
  )

  const visibleCount = sponsors.filter(s => !hidden.has(s.id)).length

  return (
    <div className="space-y-4">
      {sponsors.length > 5 && (
        <p className="font-mono text-[11px] text-pb-faintest">
          Showing {visibleCount} of {sponsors.length} sponsors · random selection on load
        </p>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        {sponsors.map(s => {
          const isHidden = hidden.has(s.id)
          const inner = (
            <>
              <img src={s.logo_url} alt={s.name} className="w-full h-16 object-contain" />
              {s.name && <p className="text-center font-mono text-[10px] text-pb-faintest mt-2 truncate">{s.name}</p>}
            </>
          )
          return (
            <div
              key={s.id}
              className={`relative rounded-xl border p-4 transition-all ${
                isHidden ? 'border-pb-hairline opacity-40' : 'border-pb-hairline2 bg-pb-surface'
              }`}
            >
              <button
                type="button"
                onClick={() => toggle(s.id)}
                className="absolute top-1.5 right-1.5 w-6 h-6 flex items-center justify-center rounded text-pb-faintest hover:text-pb-faint hover:bg-pb-surface2 transition"
                title={isHidden ? 'Show' : 'Hide'}
              >
                {isHidden ? (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </button>
              {s.website_url
                ? <a href={s.website_url} target="_blank" rel="noopener noreferrer">{inner}</a>
                : inner
              }
            </div>
          )
        })}
      </div>
    </div>
  )
}

const BASE_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'results', label: 'Results' },
  { id: 'batting', label: 'Batting' },
  { id: 'bowling', label: 'Bowling' },
  { id: 'fielding', label: 'Fielding' },
  { id: 'allrounders', label: 'All Rounders' },
  { id: 'awards', label: 'Awards' },
  { id: 'players', label: 'Players' },
  { id: 'grades', label: 'Grades' },
  { id: 'sponsors', label: 'Sponsors' },
]

export default function Yearbook() {
  const { clubSlug, seasonSlug } = useParams()
  const navigate = useNavigate()
  const [club, setClub] = useState(null)
  const [yearbooks, setYearbooks] = useState(null)
  const [yearbook, setYearbook] = useState(null)
  const [grades, setGrades] = useState([])
  const [activeTab, setActiveTab] = useState('overview')
  const [gradeId, setGradeId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [copied, setCopied] = useState(false)
  const [awardDefs, setAwardDefs] = useState([])

  const handleShare = () => {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const handlePrint = () => window.print()

  const { user } = useAuth()
  useClubTheme(club)

  usePageMeta(club && yearbook?.season ? {
    title: `${club.name} — ${formatSeason(yearbook.season)} Yearbook | BetterStats`,
    description: `${formatSeason(yearbook.season)} season yearbook for ${club.name} — stats, honours, results and records.`,
    image: club.logo_url || 'https://betterstats.cricket/og-image.png',
    url: `https://betterstats.cricket/${clubSlug}/yearbook/${seasonSlug || ''}`,
  } : {})

  // Load club
  useEffect(() => {
    api.getClubBySlug(clubSlug)
      .then(c => { setClub(c); api.listAwardDefinitions(c.id).then(d => setAwardDefs(d || [])).catch(() => {}) })
      .catch(() => setNotFound(true))
  }, [clubSlug])

  // Load yearbook list and resolve the current season
  useEffect(() => {
    if (!club) return
    api.listYearbooks(club.id).then(ybs => {
      setYearbooks(ybs)

      if (!seasonSlug) {
        // Show index — stop loading so the index page renders
        setLoading(false)
        return
      }

      const matched = ybs.find(yb => _seasonSlug(yb.season_name) === seasonSlug)
      if (!matched) {
        setNotFound(true)
        setLoading(false)
        return
      }

      setLoading(true)
      Promise.all([
        api.getYearbook(club.id, matched.season_id),
        api.getSeasonGrades(club.id, matched.season_id),
      ]).then(([yb, gradeList]) => {
        setYearbook(yb)
        setGrades(gradeList)
      }).finally(() => setLoading(false))
    }).catch(() => {
      setNotFound(true)
      setLoading(false)
    })
  }, [club, clubSlug, seasonSlug])

  if (notFound) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-pb-faint font-mono text-[13px]">Yearbook not found</p>
          <Link to={`/${clubSlug}`} className="mt-4 text-sm underline" style={{ color: 'var(--pb-accent)' }}>
            Back to dashboard
          </Link>
        </div>
      </div>
    )
  }

  // Index page — no season selected
  if (!seasonSlug) {
    const published = (yearbooks || []).filter(yb => yb.status === 'published')
    return (
      <div className="min-h-screen" style={{ background: 'var(--pb-bg)' }}>
        <div className="max-w-3xl mx-auto px-4 py-12">
          <Link to={`/${clubSlug}`} className="font-mono text-[11px] text-pb-faintest hover:text-pb-faint transition mb-6 inline-block">
            ← Dashboard
          </Link>
          {club?.logo_url && (
            <img src={club.logo_url} alt={club.name} className="w-12 h-12 object-contain mb-4 opacity-80" />
          )}
          <div className="font-mono text-[11px] tracking-wide3 text-pb-faint uppercase mb-2">{club?.name}</div>
          <h1 className="text-3xl font-bold text-pb-text mb-1">Season Yearbooks</h1>
          <p className="text-pb-faint text-sm mb-8">Season-by-season editorial wrap-ups, stats, and club records.</p>

          {loading ? <PbSpinner /> : published.length === 0 ? (
            <div className="rounded-xl border border-pb-hairline border-dashed px-6 py-10 text-center">
              <p className="font-mono text-[11px] text-pb-faintest uppercase tracking-wide3">No yearbooks published yet</p>
              <p className="text-pb-faintest text-sm mt-2">Check back after the season wraps up.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {published.map(yb => {
                const slug = _seasonSlug(yb.season_name)
                return (
                  <Link
                    key={yb.season_id}
                    to={`/${clubSlug}/yearbook/${slug}`}
                    className="flex items-center justify-between gap-4 px-5 py-4 rounded-xl border border-pb-hairline bg-pb-surface hover:bg-pb-surface2 hover:border-pb-hairline2 transition-colors group"
                  >
                    <div>
                      <div className="text-[15px] font-semibold text-pb-text transition-colors">
                        {formatSeason(yb.season_name)}
                      </div>
                      {yb.published_at && (
                        <div className="font-mono text-[11px] text-pb-faintest mt-0.5">
                          Published {new Date(yb.published_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
                        </div>
                      )}
                    </div>
                    <span className="font-mono text-[13px] text-pb-faintest group-hover:text-pb-dim transition-colors shrink-0">→</span>
                  </Link>
                )
              })}
            </div>
          )}
        </div>
      </div>
    )
  }

  if (loading || !yearbook) return <PbSpinner message="Loading yearbook…" />

  if (yearbook.status !== 'published' && !user) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--pb-bg)' }}>
        <div className="text-center px-4">
          <div className="font-mono text-[11px] tracking-wide3 text-pb-faintest uppercase mb-3">
            {club?.name} · Season Yearbook
          </div>
          <h1 className="text-2xl font-bold text-pb-text mb-2">{yearbook.season?.name || seasonSlug}</h1>
          <p className="text-pb-faint text-sm mb-6">This yearbook hasn't been published yet.</p>
          <Link to={`/${clubSlug}`} className="font-mono text-[12px]" style={{ color: 'var(--pb-accent)' }}>
            ← Back to dashboard
          </Link>
        </div>
      </div>
    )
  }

  const season = yearbook.season
  const narrative = yearbook.sections?.find(s => s.section_type === 'narrative' && s.is_enabled)?.content_markdown
  const customSections = yearbook.sections?.filter(s => s.section_type !== 'narrative' && s.is_enabled && s.content_markdown) || []
  const galleryImages = yearbook.images?.filter(i => i.image_type === 'gallery') || []

  const orgId = club.id
  const seasonId = season?.id

  const TABS = [
    ...BASE_TABS,
    ...(galleryImages.length > 0 ? [{ id: 'photos', label: 'Photos' }] : []),
    ...customSections.map(s => ({ id: `section-${s.id}`, label: s.title })),
  ]

  return (
    <div className="min-h-screen" style={{ background: 'var(--pb-bg)' }}>
      {/* Hero */}
      <div
        className="relative overflow-hidden"
        style={{
          background: yearbook.hero_image_path
            ? `linear-gradient(to bottom, rgba(0,0,0,0.6), var(--pb-bg)), url('${imageSrc(yearbook.hero_image_path)}') center/cover no-repeat`
            : `linear-gradient(135deg, color-mix(in srgb, var(--pb-accent) 20%, var(--pb-bg)), var(--pb-bg))`,
        }}
      >
        <div className="max-w-5xl mx-auto px-4 py-10 sm:py-14">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              {club.logo_url && (
                <img src={club.logo_url} alt={club.name} className="w-12 h-12 sm:w-16 sm:h-16 object-contain mb-3 opacity-90" />
              )}
              <div className="font-mono text-[10px] sm:text-[11px] tracking-wide3 text-pb-faint uppercase mb-2">
                {club.name} · Season Yearbook
              </div>
              <h1 className="text-2xl sm:text-4xl font-bold text-white leading-tight mb-2">
                {season?.name || seasonSlug}
              </h1>
              <div className="flex items-center gap-2 flex-wrap">
                {yearbook.status === 'draft' && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono tracking-wide3 border border-pb-hairline2 text-pb-faint">
                    DRAFT
                  </span>
                )}
                {/* Season switcher */}
                {yearbooks?.filter(yb => yb.status === 'published').length > 1 && (
                  <select
                    value={seasonSlug || ''}
                    onChange={e => navigate(`/${clubSlug}/yearbook/${e.target.value}`)}
                    className="print:hidden text-[11px] font-mono bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-pb-dim focus:outline-none"
                  >
                    {yearbooks.filter(yb => yb.status === 'published').map(yb => {
                      const sl = _seasonSlug(yb.season_name)
                      return <option key={yb.season_id} value={sl}>{formatSeason(yb.season_name)}</option>
                    })}
                  </select>
                )}
              </div>
            </div>
            {/* Hero actions */}
            <div className="print:hidden flex flex-col sm:flex-row items-end sm:items-center gap-2 shrink-0 pt-1">
              <button
                onClick={handleShare}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-pb-hairline2 text-[11px] font-mono text-pb-faint hover:text-pb-dim hover:border-pb-hairline2 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                </svg>
                {copied ? 'Copied!' : 'Share'}
              </button>
              <button
                onClick={handlePrint}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-pb-hairline2 text-[11px] font-mono text-pb-faint hover:text-pb-dim hover:border-pb-hairline2 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                </svg>
                Print
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Tab bar + grade filter */}
      <div className="print:hidden sticky top-0 z-30 border-b border-pb-hairline backdrop-blur-sm"
           style={{ background: 'color-mix(in srgb, var(--pb-bg) 92%, transparent)' }}>
        <div className="max-w-5xl mx-auto px-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex-1 overflow-x-auto pb-no-scrollbar">
              <div className="flex gap-1 py-2">
                {TABS.map(t => (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    className={`px-3 py-1.5 rounded font-mono text-[11px] tracking-wide whitespace-nowrap transition-colors ${
                      activeTab === t.id
                        ? 'text-pb-text font-semibold'
                        : 'text-pb-faint hover:text-pb-dim'
                    }`}
                    style={activeTab === t.id ? { background: 'color-mix(in srgb, var(--pb-accent) 20%, transparent)', color: 'var(--pb-accent)' } : {}}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
            {grades.length > 1 && !['overview', 'grades'].includes(activeTab) && !activeTab.startsWith('section-') && (
              <div className="shrink-0">
                <select
                  value={gradeId || ''}
                  onChange={e => setGradeId(e.target.value || null)}
                  className="text-[11px] font-mono bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-pb-dim focus:outline-none"
                >
                  <option value="">All Grades</option>
                  {grades.map(g => (
                    <option key={g.id} value={g.id}>{g.name}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Tab content */}
      <div className="max-w-5xl mx-auto px-4 py-8">
        {activeTab === 'overview' && (
          <OverviewTab orgId={orgId} seasonId={seasonId} gradeId={gradeId} season={season} clubSlug={clubSlug} narrative={narrative} galleryImages={galleryImages} />
        )}
        {customSections.map(s => activeTab === `section-${s.id}` && (
          <ReportsTab key={s.id} customSections={[s]} />
        ))}
        {activeTab === 'results' && (
          <ResultsTab orgId={orgId} seasonId={seasonId} gradeId={gradeId} clubSlug={clubSlug} />
        )}
        {activeTab === 'batting' && (
          <BattingTab orgId={orgId} seasonId={seasonId} gradeId={gradeId} clubSlug={clubSlug} />
        )}
        {activeTab === 'bowling' && (
          <BowlingTab orgId={orgId} seasonId={seasonId} gradeId={gradeId} clubSlug={clubSlug} />
        )}
        {activeTab === 'fielding' && (
          <FieldingTab orgId={orgId} seasonId={seasonId} gradeId={gradeId} clubSlug={clubSlug} />
        )}
        {activeTab === 'allrounders' && (
          <AllroundersTab orgId={orgId} seasonId={seasonId} gradeId={gradeId} clubSlug={clubSlug} />
        )}
        {activeTab === 'awards' && (
          <AwardsTab orgId={orgId} seasonId={seasonId} gradeId={gradeId} clubSlug={clubSlug} yearbookData={yearbook} awardDefs={awardDefs} />
        )}
        {activeTab === 'players' && (
          <PlayersTab orgId={orgId} seasonId={seasonId} gradeId={gradeId} clubSlug={clubSlug} />
        )}
        {activeTab === 'grades' && (
          <GradesTab orgId={orgId} seasonId={seasonId} clubSlug={clubSlug} />
        )}
        {activeTab === 'sponsors' && (
          <SponsorsTab clubSlug={clubSlug} />
        )}
        {activeTab === 'photos' && (
          <PhotosTab galleryImages={galleryImages} />
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-pb-hairline mt-12 py-6 text-center">
        <p className="font-mono text-[10px] text-pb-faintest tracking-wide3">
          {club.name} · {season?.name} · Powered by BetterStats
        </p>
      </div>
    </div>
  )
}

function _seasonSlug(name) {
  if (!name) return ''
  const m1 = name.match(/(\d{4})\/(\d{2,4})/)
  if (m1) return `${m1[1]}-${m1[2].slice(-2)}`
  const m2 = name.match(/(\d{4})/)
  if (m2) return m2[1]
  return name.toLowerCase().replace(/\s+/g, '-')
}
