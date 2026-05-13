import { useState, useEffect, useRef } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { PbSpinner, TabBar, Label, AnimatedNum } from '../lib/presskit'
import { useClubTheme } from '../hooks/useClubTheme'

// ─── Utility helpers ────────────────────────────────────────────────────────

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
    <Link to={`/${slug}/players/${id}`} className="hover:underline" style={{ color: 'var(--pb-accent)' }}>
      {name}
    </Link>
  )
}

const ORDINALS = ['1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th']

// ─── Shared table components ─────────────────────────────────────────────────

function YbTable({ headers, rows, className = '' }) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-[10px] font-mono tracking-wide3 text-left border-b border-white/5">
            {headers.map((h, i) => (
              <th key={i} className={`py-2.5 px-3 font-medium text-white/40 ${i > 0 ? 'text-right' : ''}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-white/5 hover:bg-white/3 transition-colors">
              {row.map((cell, j) => (
                <td key={j} className={`py-2.5 px-3 font-mono ${j > 0 ? 'text-right text-white/60' : 'text-white/90'}`}>
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
    <div className={`rounded-xl border border-white/8 bg-white/3 overflow-hidden ${className}`}>
      {title && (
        <div className="px-5 py-3 border-b border-white/8 flex items-baseline gap-3">
          <span className="font-mono text-[11px] tracking-wide3 font-semibold text-white/50 uppercase">{title}</span>
          {label && <span className="font-mono text-[10px] text-white/25">{label}</span>}
        </div>
      )}
      {children}
    </div>
  )
}

function StatCallout({ value, label, sub, accent = false }) {
  return (
    <div className="flex flex-col items-center justify-center py-6 px-4 text-center">
      <div
        className="text-5xl font-bold tabular-nums leading-none mb-2"
        style={{ color: accent ? 'var(--pb-accent)' : 'white' }}
      >
        {value}
      </div>
      <div className="text-[11px] font-mono tracking-wide3 text-white/50 uppercase">{label}</div>
      {sub && <div className="text-[11px] text-white/35 mt-1">{sub}</div>}
    </div>
  )
}

// ─── Overview tab ────────────────────────────────────────────────────────────

function OverviewTab({ orgId, seasonId, gradeId, season, clubSlug, narrative, customSections }) {
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
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-px bg-white/8 rounded-xl overflow-hidden">
        <StatCallout value={overview?.total_players ?? '—'} label="Players" accent />
        <StatCallout value={fmtRuns(overview?.total_runs)} label="Club Runs" />
        <StatCallout value={fmtRuns(overview?.total_wickets)} label="Wickets" />
        <StatCallout value={`${wins}W ${draws}D ${losses}L`} label="Record" />
        <StatCallout
          value={totalGames > 0 ? `${Math.round(wins / totalGames * 100)}%` : '—'}
          label="Win Rate"
        />
      </div>

      {/* Narrative / Season in Brief */}
      {narrative ? (
        <div className="rounded-xl border border-white/8 bg-white/3 px-6 py-5">
          <p className="font-mono text-[10px] tracking-wide3 text-white/40 uppercase mb-3">Season in Brief</p>
          <div className="prose prose-invert prose-sm max-w-none text-white/80 leading-relaxed whitespace-pre-wrap">
            {narrative}
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-white/8 border-dashed bg-white/2 px-6 py-5 text-center">
          <p className="font-mono text-[11px] text-white/30 uppercase tracking-wide3">Season in Brief</p>
          <p className="text-white/25 text-sm mt-1">Editorial content coming in v4.1 — admin can write or AI-generate this section.</p>
        </div>
      )}

      {/* Custom editorial sections (Presidents Report, etc.) */}
      {customSections?.length > 0 && customSections.map(s => (
        <div key={s.id} className="rounded-xl border border-white/8 bg-white/3 px-6 py-5">
          <p className="font-mono text-[10px] tracking-wide3 text-white/40 uppercase mb-3">{s.title}</p>
          <div className="prose prose-invert prose-sm max-w-none text-white/80 leading-relaxed whitespace-pre-wrap">
            {s.content_markdown}
          </div>
        </div>
      ))}

      {/* By the Numbers */}
      {superlatives && (
        <div>
          <p className="font-mono text-[11px] tracking-wide3 text-white/40 uppercase mb-4">By The Numbers</p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {superlatives.highest_score?.player_id && (
              <SupCard
                label="Highest Score"
                value={`${superlatives.highest_score.runs}${superlatives.highest_score.not_out ? '*' : ''}`}
                name={superlatives.highest_score.name}
                playerId={superlatives.highest_score.player_id}
                clubSlug={clubSlug}
                sub={superlatives.highest_score.home_team && superlatives.highest_score.away_team
                  ? `vs ${superlatives.highest_score.home_team === 'unknown' ? superlatives.highest_score.away_team : superlatives.highest_score.away_team}`
                  : null}
              />
            )}
            {superlatives.best_bowling?.player_id && (
              <SupCard
                label="Best Bowling"
                value={`${superlatives.best_bowling.wickets}/${superlatives.best_bowling.runs_conceded}`}
                name={superlatives.best_bowling.name}
                playerId={superlatives.best_bowling.player_id}
                clubSlug={clubSlug}
              />
            )}
            {superlatives.best_partnership?.batter1_id && (
              <SupCard
                label={`${ORDINALS[(superlatives.best_partnership.wicket_number || 1) - 1]} Wicket Partnership`}
                value={superlatives.best_partnership.runs}
                name={`${superlatives.best_partnership.batter1_name} & ${superlatives.best_partnership.batter2_name}`}
                clubSlug={clubSlug}
              />
            )}
            {superlatives.highest_team_innings?.team_runs > 0 && (
              <SupCard
                label="Highest Team Innings"
                value={fmtRuns(superlatives.highest_team_innings.team_runs)}
                sub={superlatives.highest_team_innings.home_team}
              />
            )}
            {overview?.total_fifties > 0 && (
              <SupCard label="Half Centuries" value={overview.total_fifties} />
            )}
            {overview?.total_hundreds > 0 && (
              <SupCard label="Centuries" value={overview.total_hundreds} accent />
            )}
            {superlatives.most_ducks?.player_id && (
              <SupCard
                label="Golden Ducks (Season)"
                value={superlatives.most_ducks.ducks}
                name={superlatives.most_ducks.name}
                playerId={superlatives.most_ducks.player_id}
                clubSlug={clubSlug}
                muted
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function SupCard({ label, value, name, playerId, clubSlug, sub, accent = false, muted = false }) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/3 px-5 py-4">
      <div className="font-mono text-[10px] tracking-wide3 text-white/40 uppercase mb-2">{label}</div>
      <div
        className="text-3xl font-bold tabular-nums leading-none mb-1"
        style={{ color: muted ? 'var(--pb-amber)' : accent ? 'var(--pb-accent)' : 'white' }}
      >
        {value}
      </div>
      {name && playerId && clubSlug && (
        <PlayerLink id={playerId} name={name} slug={clubSlug} />
      )}
      {name && !playerId && <span className="text-[13px] text-white/60">{name}</span>}
      {sub && <div className="text-[12px] text-white/35 mt-0.5">{sub}</div>}
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
  if (!results?.length) return <p className="text-white/30 text-sm italic py-8 text-center">No match results found for this selection.</p>

  // Group by grade
  const byGrade = results.reduce((acc, g) => {
    const key = g.grade_name || 'Unknown Grade'
    if (!acc[key]) acc[key] = []
    acc[key].push(g)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      {Object.entries(byGrade).map(([gradeName, games]) => (
        <SectionCard key={gradeName} title={gradeName}>
          <YbTable
            headers={['Date', 'Opponent', 'Result', 'Top Bat', 'Top Bowl']}
            rows={games.map(g => {
              const resultColor = g.result === 'won' ? 'var(--pb-accent)' : g.result === 'lost' ? '#f87171' : 'var(--pb-amber)'
              return [
                <span className="text-white/40 text-[12px]">{fmtDate(g.played_at) || '—'}</span>,
                <span>{g.home_team && g.away_team ? `${g.home_team} vs ${g.away_team}` : (g.home_team || g.away_team || '—')}</span>,
                <span className="font-semibold" style={{ color: resultColor }}>
                  {g.result ? g.result.charAt(0).toUpperCase() + g.result.slice(1) : '—'}
                </span>,
                g.top_batter ? (
                  <span>
                    <PlayerLink id={g.top_batter_id} name={g.top_batter} slug={clubSlug} />
                    <span className="text-white/40 ml-1">{g.top_runs}{g.top_batter_no ? '*' : ''}</span>
                  </span>
                ) : '—',
                g.top_bowler ? (
                  <span>
                    <PlayerLink id={g.top_bowler_id} name={g.top_bowler} slug={clubSlug} />
                    <span className="text-white/40 ml-1">{g.top_wickets}/{g.top_bowl_runs}</span>
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
  const [minInnings, setMinInnings] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getYearbookBatting(orgId, seasonId, { gradeId, minInnings }),
      api.getYearbookDismissals(orgId, seasonId, gradeId),
    ]).then(([b, d]) => {
      setData(b)
      setDismissals(d)
    }).finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId, minInnings])

  if (loading) return <PbSpinner />

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] font-mono text-white/40 tracking-wide3 uppercase">Min innings:</span>
        {[1, 3, 5, 10].map(n => (
          <button
            key={n}
            onClick={() => setMinInnings(n)}
            className={`px-3 py-1 rounded font-mono text-[11px] tracking-wide border transition-colors ${
              minInnings === n
                ? 'border-white/30 bg-white/10 text-white'
                : 'border-white/10 text-white/40 hover:border-white/20 hover:text-white/60'
            }`}
          >{n}+</button>
        ))}
      </div>

      <SectionCard title="Batting Honours">
        {data?.length ? (
          <YbTable
            headers={['Player', 'M', 'Inn', 'Runs', 'Avg', 'SR', 'HS', '50s', '100s', 'Ducks']}
            rows={data.map((p, i) => [
              <span className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-white/25 w-5 text-right">{i + 1}</span>
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
        ) : (
          <p className="text-white/30 text-sm italic px-5 py-4">No batting data for this selection.</p>
        )}
      </SectionCard>

      {dismissals?.length > 0 && (
        <SectionCard title="How We Got Out">
          <div className="p-5">
            <div className="space-y-2">
              {dismissals.map(d => {
                const total = dismissals.reduce((s, x) => s + parseInt(x.count || 0), 0)
                const pct = total > 0 ? Math.round(parseInt(d.count) / total * 100) : 0
                return (
                  <div key={d.dismissal_type} className="flex items-center gap-3">
                    <span className="text-[12px] text-white/60 w-32 capitalize">{d.dismissal_type.replace(/_/g, ' ')}</span>
                    <div className="flex-1 h-2 rounded-full bg-white/8 overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{ width: `${pct}%`, background: 'var(--pb-accent)', opacity: 0.7 }}
                      />
                    </div>
                    <span className="font-mono text-[11px] text-white/40 w-12 text-right">{d.count}</span>
                    <span className="font-mono text-[11px] text-white/25 w-8 text-right">{pct}%</span>
                  </div>
                )
              })}
            </div>
          </div>
        </SectionCard>
      )}
    </div>
  )
}

// ─── Bowling tab ──────────────────────────────────────────────────────────────

function BowlingTab({ orgId, seasonId, gradeId, clubSlug }) {
  const [data, setData] = useState(null)
  const [partnerships, setPartnerships] = useState(null)
  const [minWickets, setMinWickets] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getYearbookBowling(orgId, seasonId, { gradeId, minWickets }),
      api.getYearbookPartnerships(orgId, seasonId, gradeId),
    ]).then(([b, p]) => {
      setData(b)
      setPartnerships(p)
    }).finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId, minWickets])

  if (loading) return <PbSpinner />

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] font-mono text-white/40 tracking-wide3 uppercase">Min wickets:</span>
        {[1, 5, 10, 20].map(n => (
          <button
            key={n}
            onClick={() => setMinWickets(n)}
            className={`px-3 py-1 rounded font-mono text-[11px] tracking-wide border transition-colors ${
              minWickets === n
                ? 'border-white/30 bg-white/10 text-white'
                : 'border-white/10 text-white/40 hover:border-white/20 hover:text-white/60'
            }`}
          >{n}+</button>
        ))}
      </div>

      <SectionCard title="Bowling Honours">
        {data?.length ? (
          <YbTable
            headers={['Player', 'M', 'Wkts', 'Overs', 'Avg', 'Econ', 'SR', 'Best', '5WI']}
            rows={data.map((p, i) => [
              <span className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-white/25 w-5 text-right">{i + 1}</span>
                <PlayerLink id={p.player_id} name={p.name} slug={clubSlug} />
              </span>,
              p.matches ?? '—',
              <span style={{ color: 'var(--pb-accent)', fontWeight: 600 }}>{p.wickets ?? '—'}</span>,
              fmt(p.overs, 1),
              fmt(p.average),
              fmt(p.economy),
              fmt(p.strike_rate, 1),
              p.best_figures || '—',
              p.five_fors > 0
                ? <span style={{ color: 'var(--pb-amber)' }}>{p.five_fors}</span>
                : (p.five_fors ?? '—'),
            ])}
          />
        ) : (
          <p className="text-white/30 text-sm italic px-5 py-4">No bowling data for this selection.</p>
        )}
      </SectionCard>

      {partnerships && (
        <div className="grid sm:grid-cols-2 gap-6">
          <SectionCard title="Top Partnerships">
            {partnerships.top_partnerships?.length ? (
              <YbTable
                headers={['Batters', 'Wkt', 'Runs']}
                rows={partnerships.top_partnerships.map((p, i) => [
                  <span>
                    <span className="font-mono text-[11px] text-white/25 mr-2">{i + 1}</span>
                    <PlayerLink id={p.batter1_id} name={p.batter1_name} slug={clubSlug} />
                    <span className="text-white/40 mx-1">&amp;</span>
                    <PlayerLink id={p.batter2_id} name={p.batter2_name} slug={clubSlug} />
                  </span>,
                  ORDINALS[(p.wicket_number || 1) - 1],
                  <span style={{ color: 'var(--pb-accent)', fontWeight: 600 }}>{p.runs}</span>,
                ])}
              />
            ) : (
              <p className="text-white/30 text-sm italic px-5 py-4">No partnership data.</p>
            )}
          </SectionCard>

          <SectionCard title="Best Partnership by Wicket">
            {partnerships.by_wicket?.length ? (
              <YbTable
                headers={['Wicket', 'Batters', 'Runs']}
                rows={partnerships.by_wicket.map(p => [
                  <span className="text-white/50">{ORDINALS[(p.wicket_number || 1) - 1]}</span>,
                  <span>
                    <PlayerLink id={p.batter1_id} name={p.batter1_name} slug={clubSlug} />
                    <span className="text-white/40 mx-1">&amp;</span>
                    <PlayerLink id={p.batter2_id} name={p.batter2_name} slug={clubSlug} />
                  </span>,
                  <span style={{ color: 'var(--pb-accent)', fontWeight: 600 }}>{p.runs}</span>,
                ])}
              />
            ) : (
              <p className="text-white/30 text-sm italic px-5 py-4">No partnership data.</p>
            )}
          </SectionCard>
        </div>
      )}
    </div>
  )
}

// ─── Fielding tab ─────────────────────────────────────────────────────────────

function FieldingTab({ orgId, seasonId, gradeId, clubSlug }) {
  const [data, setData] = useState(null)
  const [allrounders, setAllrounders] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getYearbookFielding(orgId, seasonId, { gradeId }),
      api.getYearbookAllrounders(orgId, seasonId, { gradeId }),
    ]).then(([f, a]) => {
      setData(f)
      setAllrounders(a)
    }).finally(() => setLoading(false))
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
                <span className="font-mono text-[11px] text-white/25 w-5 text-right">{i + 1}</span>
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
          <p className="text-white/30 text-sm italic px-5 py-4">No fielding data for this selection.</p>
        )}
      </SectionCard>

      {allrounders?.length > 0 && (
        <SectionCard title="All-Rounder Index" label="100+ runs & 5+ wickets">
          <YbTable
            headers={['Player', 'M', 'Runs', 'Bat Avg', 'Wkts', 'Bowl Avg', 'Index']}
            rows={allrounders.map((p, i) => [
              <span className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-white/25 w-5 text-right">{i + 1}</span>
                <PlayerLink id={p.player_id} name={p.name} slug={clubSlug} />
              </span>,
              p.matches ?? '—',
              fmtRuns(p.runs),
              fmt(p.bat_avg),
              p.wickets ?? '—',
              fmt(p.bowl_avg),
              <span style={{ color: 'var(--pb-accent)', fontWeight: 600 }}>{p.allrounder_index ?? '—'}</span>,
            ])}
          />
        </SectionCard>
      )}
    </div>
  )
}

// ─── Awards tab (Honour Board + Club Awards from achievements) ────────────────

function AwardsTab({ orgId, seasonId, gradeId, clubSlug, yearbookData }) {
  const [milestones, setMilestones] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getYearbookMilestones(orgId, seasonId)
      .then(setMilestones)
      .finally(() => setLoading(false))
  }, [orgId, seasonId])

  const honourBoard = yearbookData?.honour_board || []

  // Group honour board by position
  const hbByPos = honourBoard.reduce((acc, h) => {
    if (!acc[h.position_title]) acc[h.position_title] = []
    acc[h.position_title].push(h)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      {honourBoard.length > 0 && (
        <SectionCard title="Honour Board">
          <div className="divide-y divide-white/5">
            {Object.entries(hbByPos).map(([pos, holders]) => (
              <div key={pos} className="flex items-start gap-4 px-5 py-3">
                <span className="font-mono text-[11px] text-white/40 uppercase tracking-wide w-40 shrink-0">{pos}</span>
                <span className="text-[13px] text-white/80">
                  {holders.map((h, i) => (
                    <span key={h.id}>
                      {i > 0 && <span className="text-white/30 mx-1">&amp;</span>}
                      {h.player_id
                        ? <PlayerLink id={h.player_id} name={h.player_name || h.name_override} slug={clubSlug} />
                        : <span>{h.name_override}</span>
                      }
                    </span>
                  ))}
                </span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {loading ? <PbSpinner /> : milestones?.length > 0 && (
        <SectionCard title="Career Milestones This Season">
          <div className="divide-y divide-white/5">
            {milestones.map(m => (
              <div key={m.id} className="flex items-center gap-4 px-5 py-3">
                <div className="w-8 h-8 rounded-full flex items-center justify-center text-[14px]"
                     style={{ background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)' }}>
                  🏆
                </div>
                <div className="flex-1">
                  <PlayerLink id={m.player_id} name={m.player_name} slug={clubSlug} />
                  <div className="font-mono text-[11px] text-white/40 mt-0.5">
                    {m.milestone_type} — {m.milestone_value?.toLocaleString()}
                    {m.achieved_at && <span className="ml-2">{fmtDate(m.achieved_at)}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {honourBoard.length === 0 && !loading && milestones?.length === 0 && (
        <div className="rounded-xl border border-white/8 border-dashed px-6 py-8 text-center">
          <p className="font-mono text-[11px] text-white/30 uppercase tracking-wide3">Awards & Honour Board</p>
          <p className="text-white/25 text-sm mt-2">
            Club admins can add honour board positions and award winners from the Yearbook admin panel.
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
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.getYearbookPlayers(orgId, seasonId, gradeId)
      .then(setPlayers)
      .finally(() => setLoading(false))
  }, [orgId, seasonId, gradeId])

  if (loading) return <PbSpinner />
  if (!players?.length) return <p className="text-white/30 text-sm italic py-8 text-center">No player data for this selection.</p>

  return (
    <div>
      <p className="text-[12px] text-white/30 mb-4 font-mono">{players.length} players · click any card for full breakdown</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {players.map(p => (
          <div
            key={p.player_id}
            onClick={() => setExpanded(expanded === p.player_id ? null : p.player_id)}
            className={`rounded-xl border cursor-pointer transition-all ${
              expanded === p.player_id
                ? 'border-white/25 bg-white/8'
                : 'border-white/8 bg-white/3 hover:border-white/15 hover:bg-white/5'
            }`}
          >
            <div className="px-4 py-3">
              <div className="font-medium text-[13px] text-white/90 leading-tight">{p.name}</div>
              <div className="font-mono text-[11px] text-white/40 mt-0.5">{p.matches}M</div>
            </div>
            {expanded === p.player_id && (
              <div className="border-t border-white/8 px-4 py-3 space-y-1">
                {p.runs > 0 && (
                  <div className="flex justify-between text-[12px]">
                    <span className="text-white/50">Runs</span>
                    <span style={{ color: 'var(--pb-accent)' }}>{fmtRuns(p.runs)} {p.high_score != null ? `(HS ${p.high_score})` : ''}</span>
                  </div>
                )}
                {p.bat_avg && (
                  <div className="flex justify-between text-[12px]">
                    <span className="text-white/50">Bat Avg</span>
                    <span className="text-white/70">{fmt(p.bat_avg)}</span>
                  </div>
                )}
                {p.wickets > 0 && (
                  <div className="flex justify-between text-[12px]">
                    <span className="text-white/50">Wickets</span>
                    <span style={{ color: 'var(--pb-accent)' }}>{p.wickets}</span>
                  </div>
                )}
                {p.bowl_avg && p.wickets > 0 && (
                  <div className="flex justify-between text-[12px]">
                    <span className="text-white/50">Bowl Avg</span>
                    <span className="text-white/70">{fmt(p.bowl_avg)}</span>
                  </div>
                )}
                {p.dismissals > 0 && (
                  <div className="flex justify-between text-[12px]">
                    <span className="text-white/50">Dismissals</span>
                    <span className="text-white/70">{p.dismissals}</span>
                  </div>
                )}
                <div className="pt-1">
                  <Link
                    to={`/${clubSlug}/players/${p.player_id}`}
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
  if (!grades?.length) return <p className="text-white/30 text-sm italic py-8 text-center">No grade data available.</p>

  return (
    <div className="grid sm:grid-cols-2 gap-4">
      {grades.map(g => (
        <SectionCard key={g.id} title={g.name}>
          <div className="grid grid-cols-2 divide-x divide-white/5">
            <StatCallout value={fmtRuns(g.runs)} label="Runs" />
            <StatCallout value={g.wickets ?? '—'} label="Wickets" />
          </div>
          <div className="border-t border-white/5 px-5 py-3 space-y-2">
            {g.top_batter?.name && (
              <div className="flex items-center gap-3 text-[12px]">
                <span className="text-white/40 w-24 font-mono text-[10px] uppercase tracking-wide">Top Bat</span>
                <span className="flex-1">
                  <PlayerLink id={g.top_batter.id} name={g.top_batter.name} slug={clubSlug} />
                  <span className="text-white/40 ml-2">{fmtRuns(g.top_batter.runs)} runs</span>
                </span>
              </div>
            )}
            {g.top_bowler?.name && (
              <div className="flex items-center gap-3 text-[12px]">
                <span className="text-white/40 w-24 font-mono text-[10px] uppercase tracking-wide">Top Bowl</span>
                <span className="flex-1">
                  <PlayerLink id={g.top_bowler.id} name={g.top_bowler.name} slug={clubSlug} />
                  <span className="text-white/40 ml-2">{g.top_bowler.wickets} wickets</span>
                </span>
              </div>
            )}
            <div className="flex items-center gap-3 text-[12px]">
              <span className="text-white/40 w-24 font-mono text-[10px] uppercase tracking-wide">HS</span>
              <span className="text-white/60">{g.high_score ?? '—'}</span>
            </div>
          </div>
        </SectionCard>
      ))}
    </div>
  )
}

// ─── Main Yearbook page ───────────────────────────────────────────────────────

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'results', label: 'Results' },
  { id: 'batting', label: 'Batting' },
  { id: 'bowling', label: 'Bowling' },
  { id: 'fielding', label: 'Fielding' },
  { id: 'awards', label: 'Awards' },
  { id: 'players', label: 'Players' },
  { id: 'grades', label: 'Grades' },
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

  useClubTheme(club)

  // Load club
  useEffect(() => {
    api.getClubBySlug(clubSlug)
      .then(setClub)
      .catch(() => setNotFound(true))
  }, [clubSlug])

  // Load yearbook list and resolve the current season
  useEffect(() => {
    if (!club) return
    Promise.all([
      api.listYearbooks(club.id),
      api.getOrgSeasons(club.id),
    ]).then(([ybs, seasons]) => {
      setYearbooks(ybs)

      // Find the matching season by slug
      const matched = ybs.find(yb => {
        const slug = _seasonSlug(yb.season_name)
        return slug === seasonSlug
      })

      if (!matched) {
        // If no slug given, redirect to latest published or latest draft
        if (!seasonSlug) {
          const published = ybs.filter(y => y.status === 'published')
          const target = published[0] || ybs[0]
          if (target) {
            navigate(`/${clubSlug}/yearbook/${_seasonSlug(target.season_name)}`, { replace: true })
          }
          return
        }
        setNotFound(true)
        return
      }

      setLoading(true)
      Promise.all([
        api.getYearbook(club.id, matched.season_id),
        api.getSeasonGrades(club.id, matched.season_id),
      ]).then(([yb, gradeList]) => {
        if (yb.status !== 'published') {
          // Still show draft to club admins — for now show it to all (auth check in v4.1)
        }
        setYearbook(yb)
        setGrades(gradeList)
      }).finally(() => setLoading(false))
    }).catch(() => {
      setNotFound(true)
      setLoading(false)
    })
  }, [club, clubSlug, seasonSlug, navigate])

  if (notFound) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-white/40 font-mono text-[13px]">Yearbook not found</p>
          <Link to={`/${clubSlug}/dashboard`} className="mt-4 text-sm underline" style={{ color: 'var(--pb-accent)' }}>
            Back to dashboard
          </Link>
        </div>
      </div>
    )
  }

  if (loading || !yearbook) return <PbSpinner message="Loading yearbook…" />

  const season = yearbook.season
  const narrative = yearbook.sections?.find(s => s.section_type === 'narrative' && s.is_enabled)?.content_markdown
  const customSections = yearbook.sections?.filter(s => s.section_type !== 'narrative' && s.is_enabled && s.content_markdown) || []

  const orgId = club.id
  const seasonId = season?.id

  return (
    <div className="min-h-screen" style={{ background: 'var(--pb-bg)' }}>
      {/* Hero */}
      <div
        className="relative overflow-hidden"
        style={{
          background: yearbook.hero_image_path
            ? `linear-gradient(to bottom, rgba(0,0,0,0.6), var(--pb-bg)), url('/uploads/${yearbook.hero_image_path}') center/cover no-repeat`
            : `linear-gradient(135deg, color-mix(in srgb, var(--pb-accent) 20%, var(--pb-bg)), var(--pb-bg))`,
        }}
      >
        <div className="max-w-5xl mx-auto px-4 py-12 sm:py-16">
          {club.logo_url && (
            <img src={club.logo_url} alt={club.name} className="w-16 h-16 object-contain mb-4 opacity-90" />
          )}
          <div className="font-mono text-[11px] tracking-wide3 text-white/40 uppercase mb-2">
            {club.name} · Season Yearbook
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold text-white leading-tight mb-1">
            {season?.name || seasonSlug}
          </h1>
          {yearbook.status === 'draft' && (
            <span className="inline-block mt-2 px-2 py-0.5 rounded text-[10px] font-mono tracking-wide3 border border-white/20 text-white/40">
              DRAFT — not published
            </span>
          )}
        </div>
      </div>

      {/* Tab bar + grade filter */}
      <div className="sticky top-0 z-30 border-b border-white/8 backdrop-blur-sm"
           style={{ background: 'color-mix(in srgb, var(--pb-bg) 92%, transparent)' }}>
        <div className="max-w-5xl mx-auto px-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex-1 overflow-x-auto">
              <div className="flex gap-1 py-2">
                {TABS.map(t => (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    className={`px-3 py-1.5 rounded font-mono text-[11px] tracking-wide whitespace-nowrap transition-colors ${
                      activeTab === t.id
                        ? 'text-white font-semibold'
                        : 'text-white/40 hover:text-white/60'
                    }`}
                    style={activeTab === t.id ? { background: 'color-mix(in srgb, var(--pb-accent) 20%, transparent)', color: 'var(--pb-accent)' } : {}}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
            {grades.length > 1 && (
              <div className="shrink-0">
                <select
                  value={gradeId || ''}
                  onChange={e => setGradeId(e.target.value || null)}
                  className="text-[11px] font-mono bg-white/5 border border-white/15 rounded px-2 py-1.5 text-white/70 focus:outline-none"
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
          <OverviewTab orgId={orgId} seasonId={seasonId} gradeId={gradeId} season={season} clubSlug={clubSlug} narrative={narrative} customSections={customSections} />
        )}
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
        {activeTab === 'awards' && (
          <AwardsTab orgId={orgId} seasonId={seasonId} gradeId={gradeId} clubSlug={clubSlug} yearbookData={yearbook} />
        )}
        {activeTab === 'players' && (
          <PlayersTab orgId={orgId} seasonId={seasonId} gradeId={gradeId} clubSlug={clubSlug} />
        )}
        {activeTab === 'grades' && (
          <GradesTab orgId={orgId} seasonId={seasonId} clubSlug={clubSlug} />
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-white/5 mt-12 py-6 text-center">
        <p className="font-mono text-[10px] text-white/20 tracking-wide3">
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
