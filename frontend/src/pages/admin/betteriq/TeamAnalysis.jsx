import { useState, useEffect } from 'react'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Icon, Empty } from '../betterselect/ui'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'batting', label: 'Batting' },
  { key: 'bowling', label: 'Bowling' },
  { key: 'players', label: 'Players' },
]

function Card({ title, right, children, accent = false }) {
  return (
    <div className="pb-card p-4 md:p-5" style={accent ? { borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' } : undefined}>
      {(title || right) && (
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="font-display font-bold">{title}</h3>
          {right}
        </div>
      )}
      {children}
    </div>
  )
}

function Stat({ label, value, sub, tone }) {
  return (
    <div className="text-center px-2.5 py-1.5">
      <div className="font-display font-bold text-xl pb-num leading-none" style={tone ? { color: tone } : undefined}>{value}</div>
      <div className="text-pb-faint text-[10px] mt-1 uppercase tracking-wide2">{label}</div>
      {sub && <div className="text-pb-faintest text-[10px] mt-0.5">{sub}</div>}
    </div>
  )
}

function Bullets({ items, dir }) {
  if (!items?.length) return <Empty>—</Empty>
  const sym = dir === 'win' ? '▲' : '▼'
  const color = dir === 'win' ? 'var(--pb-brand)' : 'var(--pb-red)'
  return (
    <ul className="space-y-1.5 text-sm">
      {items.map((b, i) => <li key={i} className="flex gap-2"><span style={{ color }}>{sym}</span><span>{b}</span></li>)}
    </ul>
  )
}

// A small "how this is worked out" footnote for a card.
function Note({ children }) {
  return <div className="text-pb-faintest text-[11px] mt-2.5 leading-snug">{children}</div>
}

export default function TeamAnalysis() {
  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState(null)   // null = not chosen yet; '' = all-time
  const [grades, setGrades] = useState([])
  const [gradeId, setGradeId] = useState('')       // '' = all teams
  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)
  const [tab, setTab] = useState('overview')

  // Default to the latest season (a whole-history overview isn't very useful).
  useEffect(() => {
    api.iqTeamSeasons().then(ss => {
      setSeasons(ss || [])
      setSeasonId(prev => (prev === null ? (ss?.[0]?.season_id || '') : prev))
    }).catch(() => { setSeasons([]); setSeasonId('') })
  }, [])

  // Teams (grades) available for the chosen season.
  useEffect(() => {
    if (seasonId === null) return
    setGradeId('')
    api.iqTeamGrades(seasonId || undefined).then(g => setGrades(g || [])).catch(() => setGrades([]))
  }, [seasonId])

  useEffect(() => {
    if (seasonId === null) return
    let alive = true
    setData(null); setErr(false)
    api.iqTeamOverview(seasonId || undefined, gradeId || undefined)
      .then(d => { if (alive) setData(d) })
      .catch(() => { if (alive) setErr(true) })
    return () => { alive = false }
  }, [seasonId, gradeId])

  const r = data?.record
  const b = data?.batting
  const bw = data?.bowling
  const inn = data?.innings
  const maxP = Math.max(1, ...((data?.partnerships || []).map(p => p.avg_partnership || 0)))
  const ord = (k) => ({ 1: '1st', 2: '2nd', 3: '3rd' }[k] || `${k}th`)

  const selClass = "bg-pb-surface2 text-sm font-medium rounded-lg border px-3 h-[40px] text-pb-text border-pb-hairline focus:outline-none focus:border-pb-accent"

  return (
    <IQLayout title="Team analysis">
      <p className="text-pb-faint text-sm mb-4 max-w-2xl">The opposition lens, pointed at us — how we win and lose, our batting & bowling shape, and where we're strong or fragile.</p>

      {/* Prominent season + team filters */}
      <div className="flex flex-wrap items-center gap-2 mb-5">
        <div className="flex items-center gap-1.5">
          <span className="text-pb-faint text-[11px] uppercase tracking-wide2">Season</span>
          <select value={seasonId ?? ''} onChange={e => setSeasonId(e.target.value)} className={selClass}>
            {seasons.map(s => <option key={s.season_id} value={s.season_id} className="bg-pb-surface">{s.name}</option>)}
            <option value="" className="bg-pb-surface">All-time</option>
          </select>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-pb-faint text-[11px] uppercase tracking-wide2">Team</span>
          <select value={gradeId} onChange={e => setGradeId(e.target.value)} className={selClass} disabled={!grades.length}>
            <option value="" className="bg-pb-surface">All teams</option>
            {grades.map(g => <option key={g.grade_id} value={g.grade_id} className="bg-pb-surface">{g.name}</option>)}
          </select>
        </div>
      </div>

      {data === null && !err && <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Crunching our games…</div>}
      {err && <div className="pb-card p-5"><Empty>Couldn't load team analysis.</Empty></div>}
      {data && r && (
        <>
          {/* Tab bar */}
          <div className="flex items-center gap-1 mb-4 border-b pb-hairline overflow-x-auto">
            {TABS.map(t => (
              <button key={t.key} onClick={() => setTab(t.key)}
                className="px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors"
                style={tab === t.key ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : { borderColor: 'transparent', color: 'var(--pb-faint)' }}>
                {t.label}
              </button>
            ))}
          </div>

          {/* ── Overview ─────────────────────────────────────────────────── */}
          {tab === 'overview' && (
            <div className="space-y-4">
              <Card title="Record" right={<span className="text-pb-faint text-xs">{r.matches} matches</span>}>
                <div className="flex flex-wrap items-center gap-1 sm:gap-2">
                  <Stat label="Won" value={r.wins} />
                  <Stat label="Lost" value={r.losses} />
                  <Stat label="Drawn" value={r.draws} />
                  <Stat label="Win %" value={r.win_pct === null ? '—' : r.win_pct} tone="var(--pb-accent)" />
                  <Stat label="At home" value={`${r.home.wins}/${r.home.played}`} sub="W/P" />
                  <Stat label="Away" value={`${r.away.wins}/${r.away.played}`} sub="W/P" />
                </div>
              </Card>

              <div className="grid gap-4 lg:grid-cols-2">
                <Card title="How we win"><Bullets items={data.how_we_win} dir="win" /></Card>
                <Card title="How we lose"><Bullets items={data.how_we_lose} dir="lose" /></Card>
              </div>

              <Card title="Bat first vs chase">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl p-3" style={{ background: 'var(--pb-surface2)' }}>
                    <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Batting first</div>
                    <div className="font-display font-bold text-2xl pb-num">{inn.bat_first.win_pct === null ? '—' : `${inn.bat_first.win_pct}%`}</div>
                    <div className="text-pb-faintest text-[11px]">{inn.bat_first.wins}/{inn.bat_first.played} won · avg {num(inn.bat_first.avg_score)}</div>
                  </div>
                  <div className="rounded-xl p-3" style={{ background: 'var(--pb-surface2)' }}>
                    <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Chasing</div>
                    <div className="font-display font-bold text-2xl pb-num">{inn.chasing.win_pct === null ? '—' : `${inn.chasing.win_pct}%`}</div>
                    <div className="text-pb-faintest text-[11px]">{inn.chasing.wins}/{inn.chasing.played} won · avg target {num(inn.chasing.avg_target)}</div>
                  </div>
                </div>
              </Card>

              {data.score_bands?.length > 0 && (
                <Card title="What score wins" right={<span className="text-pb-faint text-xs">batting first</span>}>
                  <div className="space-y-1.5">
                    {data.score_bands.map(s => (
                      <div key={s.band} className="flex items-center gap-2 text-sm">
                        <span className="w-16 text-pb-faint shrink-0">{s.band}</span>
                        <div className="flex-1 h-2 rounded-full bg-pb-surface2 overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${s.win_pct || 0}%`, background: 'var(--pb-accent)' }} />
                        </div>
                        <span className="w-20 text-right pb-num shrink-0">{s.win_pct === null ? '—' : `${s.win_pct}%`} <span className="text-pb-faintest">({s.played})</span></span>
                      </div>
                    ))}
                  </div>
                  <Note>Win rate when we post a first-innings total in each band — the count of such games in brackets.</Note>
                </Card>
              )}

              {data.venues?.length > 0 && (
                <Card title="By venue">
                  <div className="overflow-x-auto -mx-1">
                    <table className="w-full text-sm">
                      <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left">
                        <th className="py-1 px-1 font-medium">Ground</th>
                        <th className="py-1 px-1 font-medium text-right">Played</th>
                        <th className="py-1 px-1 font-medium text-right">W–L</th>
                        <th className="py-1 px-1 font-medium text-right">Avg score</th>
                      </tr></thead>
                      <tbody>
                        {data.venues.map(v => (
                          <tr key={v.venue} className="border-t pb-hairline">
                            <td className="py-1.5 px-1 truncate max-w-[220px]">{v.venue}</td>
                            <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{v.played}</td>
                            <td className="py-1.5 px-1 text-right pb-num">{v.wins}–{v.losses}</td>
                            <td className="py-1.5 px-1 text-right pb-num">{num(v.avg_score)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}
            </div>
          )}

          {/* ── Batting ──────────────────────────────────────────────────── */}
          {tab === 'batting' && (
            <div className="space-y-4">
              <Card title="Batting profile">
                <div className="flex flex-wrap items-center gap-1 sm:gap-2 mb-3">
                  <Stat label="Avg score" value={num(b.avg_score)} />
                  <Stat label="High" value={num(b.high_score)} />
                  <Stat label="Low" value={num(b.low_score)} />
                  <Stat label="Wkts lost" value={num(b.avg_wickets_lost)} sub="avg" />
                  <Stat label="Boundary %" value={b.boundary_pct === null ? '—' : `${b.boundary_pct}%`} />
                </div>
                {b.top_order_pct !== null && (
                  <div>
                    <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1.5">Where our runs come from</div>
                    <div className="flex h-2.5 rounded-full overflow-hidden bg-pb-surface2">
                      <div title={`Top 3: ${b.top_order_pct}%`} style={{ flexGrow: b.top_order_pct, background: 'var(--pb-accent)' }} />
                      <div title={`Middle: ${b.middle_pct}%`} style={{ flexGrow: b.middle_pct, background: 'var(--pb-amber)' }} />
                      <div title={`Lower: ${b.lower_pct}%`} style={{ flexGrow: b.lower_pct, background: 'var(--pb-dim)' }} />
                    </div>
                    <div className="flex justify-between text-[11px] text-pb-faint mt-1">
                      <span>Top 3 · {b.top_order_pct}%</span><span>Middle · {b.middle_pct}%</span><span>Lower · {b.lower_pct}%</span>
                    </div>
                  </div>
                )}
              </Card>

              {data.partnerships?.length > 0 && (
                <Card title="Our partnerships" right={<span className="text-pb-faint text-xs">avg by wicket</span>}>
                  <div className="space-y-1">
                    {data.partnerships.map(p => (
                      <div key={p.wicket} className="flex items-center gap-2 text-[12px]">
                        <span className="w-7 text-pb-faint shrink-0">{ord(p.wicket)}</span>
                        <div className="flex-1 h-2 rounded-full bg-pb-surface2 overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${Math.round((p.avg_partnership / maxP) * 100)}%`, background: 'var(--pb-accent)' }} />
                        </div>
                        <span className="w-9 text-right pb-num shrink-0">{p.avg_partnership}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {data.batting_pairs?.length > 0 && (
                <Card title="Best partnerships" right={<span className="text-pb-faint text-xs">by pair</span>}>
                  <div className="space-y-0.5">
                    {data.batting_pairs.map((p, i) => (
                      <div key={i} className="flex items-center justify-between gap-3 text-sm py-0.5">
                        <div className="min-w-0 flex items-baseline gap-2">
                          <span className="truncate">{p.a} &amp; {p.b}</span>
                          {p.opening && <span className="text-pb-faintest text-[11px] shrink-0">opening</span>}
                        </div>
                        <div className="flex items-center gap-3 whitespace-nowrap text-pb-faint pb-num">
                          <span>{p.stands} stands</span>
                          <span className="font-semibold">{p.runs} @ {p.avg ?? '—'}</span>
                          <span className="w-20 text-right">best {p.best}{p.fifties ? ` · ${p.fifties}×50` : ''}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <Note>Average is runs per stand together (not a batting average).</Note>
                </Card>
              )}

              {data.collapses && data.collapses.innings_analysed > 0 && (
                <Card title="Collapse analysis" right={<span className="text-pb-faint text-xs">3 wkts for ≤{data.collapses.threshold}</span>}>
                  <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
                    <div>
                      <span className="font-display font-bold text-2xl pb-num">{data.collapses.collapse_pct}%</span>
                      <span className="text-pb-faint text-sm ml-2">of innings ({data.collapses.collapse_count}/{data.collapses.innings_analysed})</span>
                    </div>
                    {data.collapses.worst && (
                      <div className="text-sm text-pb-faint">Worst: <span className="pb-num font-semibold">3 for {data.collapses.worst.runs}</span> from the {ord(data.collapses.worst.start_wicket)} wkt</div>
                    )}
                  </div>
                  {data.collapses.by_start_wicket?.length > 0 && (
                    <div className="mt-3 pt-3 border-t pb-hairline">
                      <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1.5">Where the wheels come off</div>
                      <div className="flex flex-wrap gap-2">
                        {data.collapses.by_start_wicket.map(w => (
                          <span key={w.wicket} className="text-[12px] px-2 py-0.5 rounded-full" style={{ background: 'var(--pb-surface2)' }}>{ord(w.wicket)} wkt <span className="pb-num text-pb-faint">×{w.count}</span></span>
                        ))}
                      </div>
                    </div>
                  )}
                  <Note>A collapse = losing any 3 wickets in a row for ≤{data.collapses.threshold} runs, reconstructed from stored partnerships.</Note>
                </Card>
              )}
            </div>
          )}

          {/* ── Bowling ──────────────────────────────────────────────────── */}
          {tab === 'bowling' && (
            <div className="space-y-4">
              <Card title="Bowling summary">
                <div className="flex flex-wrap items-center gap-1 sm:gap-2">
                  <Stat label="Avg conceded" value={num(bw.avg_conceded)} />
                  <Stat label="Wkts / game" value={num(bw.avg_wickets_taken)} />
                </div>
              </Card>

              {data.attack && data.attack.bowlers?.length > 0 && (
                <Card title="Bowling attack" right={<span className="text-pb-faint text-xs">pace vs spin</span>}>
                  <div className="flex items-center gap-2 text-[11px] mb-3">
                    <span className="text-pb-faint w-9">Mix</span>
                    <div className="flex-1 h-3 rounded-full overflow-hidden flex bg-pb-surface2">
                      <div className="h-full" style={{ width: `${data.attack.pace_pct}%`, background: 'var(--pb-accent)' }} title={`Pace ${data.attack.pace_pct}%`} />
                      <div className="h-full" style={{ width: `${data.attack.spin_pct}%`, background: 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' }} title={`Spin ${data.attack.spin_pct}%`} />
                    </div>
                    <span className="pb-num text-pb-faint whitespace-nowrap">{data.attack.pace_pct}% pace · {data.attack.spin_pct}% spin</span>
                  </div>
                  <div className="overflow-x-auto -mx-1">
                    <table className="w-full text-sm">
                      <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left">
                        <th className="py-1 px-1 font-medium">Bowler</th>
                        <th className="py-1 px-1 font-medium text-right">Overs</th>
                        <th className="py-1 px-1 font-medium text-right">Wkts</th>
                        <th className="py-1 px-1 font-medium text-right">Avg</th>
                        <th className="py-1 px-1 font-medium text-right">Econ</th>
                        <th className="py-1 px-1 font-medium">Role</th>
                      </tr></thead>
                      <tbody>
                        {data.attack.bowlers.map(bl => (
                          <tr key={bl.player_id} className="border-t pb-hairline">
                            <td className="py-1.5 px-1 font-medium whitespace-nowrap">{bl.name} {bl.spin ? <span className="text-pb-faintest text-[10px]">spin</span> : bl.pace ? <span className="text-pb-faintest text-[10px]">pace</span> : null}</td>
                            <td className="py-1.5 px-1 text-right pb-num">{bl.overs}</td>
                            <td className="py-1.5 px-1 text-right pb-num">{bl.wickets}</td>
                            <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{bl.avg ?? '—'}</td>
                            <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{bl.econ}</td>
                            <td className="py-1.5 px-1 text-[11px] text-pb-faint">{bl.role}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <Note>Role: <b>Strike</b> takes wickets quickly · <b>Containment</b> restricts runs · <b>Stock</b> workhorse. Frontline bowlers only.</Note>
                </Card>
              )}

              {data.discipline && (
                <Card title="Bowling discipline" right={<span className="text-pb-faint text-xs">extras conceded</span>}>
                  <div className="flex flex-wrap items-center gap-1 sm:gap-2 mb-3">
                    <Stat label="Extras/over" value={num(data.discipline.extras_per_over)} />
                    <Stat label="Wides/over" value={num(data.discipline.wides_per_over)} />
                    <Stat label="Extras" value={num(data.discipline.extras)} sub={`${data.discipline.wides}w · ${data.discipline.no_balls}nb`} />
                    <Stat label="% of runs" value={data.discipline.extras_pct == null ? '—' : `${data.discipline.extras_pct}%`} sub="conceded" />
                  </div>
                  {data.discipline.bowlers?.length > 0 && (
                    <div className="overflow-x-auto -mx-1">
                      <table className="w-full text-sm">
                        <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left">
                          <th className="py-1 px-1 font-medium">Bowler</th>
                          <th className="py-1 px-1 font-medium text-right">Overs</th>
                          <th className="py-1 px-1 font-medium text-right">Wd</th>
                          <th className="py-1 px-1 font-medium text-right">Nb</th>
                          <th className="py-1 px-1 font-medium text-right">Extras/over</th>
                        </tr></thead>
                        <tbody>
                          {data.discipline.bowlers.map(bl => (
                            <tr key={bl.player_id} className="border-t pb-hairline">
                              <td className="py-1.5 px-1 font-medium whitespace-nowrap">{bl.name}</td>
                              <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{bl.overs}</td>
                              <td className="py-1.5 px-1 text-right pb-num">{bl.wides}</td>
                              <td className="py-1.5 px-1 text-right pb-num">{bl.no_balls}</td>
                              <td className="py-1.5 px-1 text-right pb-num font-semibold">{num(bl.extras_per_over)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <Note>Wides + no-balls per over, most disciplined first (min {seasonId || gradeId ? '10' : '50'} overs). Hidden when the scorecards don't record extras.</Note>
                </Card>
              )}
            </div>
          )}

          {/* ── Players ──────────────────────────────────────────────────── */}
          {tab === 'players' && (
            <div className="space-y-4">
              {data.captaincy?.length > 0 && (
                <Card title="Captaincy" right={<span className="text-pb-faint text-xs">record as skipper</span>}>
                  <div className="overflow-x-auto -mx-1">
                    <table className="w-full text-sm">
                      <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left">
                        <th className="py-1 px-1 font-medium">Captain</th>
                        <th className="py-1 px-1 font-medium text-right">Led</th>
                        <th className="py-1 px-1 font-medium text-right">W–L–D</th>
                        <th className="py-1 px-1 font-medium text-right">Win %</th>
                        <th className="py-1 px-1 font-medium text-right">Avg score</th>
                        <th className="py-1 px-1 font-medium text-right">Finals</th>
                      </tr></thead>
                      <tbody>
                        {data.captaincy.map(c => (
                          <tr key={c.player_id} className="border-t pb-hairline">
                            <td className="py-1.5 px-1 font-medium whitespace-nowrap">{c.name}</td>
                            <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{c.led}</td>
                            <td className="py-1.5 px-1 text-right pb-num">{c.wins}–{c.losses}–{c.draws}</td>
                            <td className="py-1.5 px-1 text-right pb-num font-semibold" style={c.win_pct != null && c.win_pct >= 50 ? { color: 'var(--pb-brand)' } : undefined}>{c.win_pct == null ? '—' : `${c.win_pct}%`}</td>
                            <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{num(c.avg_score)}</td>
                            <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{c.finals ? `${c.finals_won}/${c.finals}` : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <Note>Win % is over decided games (draws/ties excluded); avg score is our total in games they led. Min 3 games as captain. Toss decisions aren't in our data.</Note>
                </Card>
              )}

              {data.all_rounders?.length > 0 && (
                <Card title="All-rounders" right={<span className="text-pb-faint text-xs">bat avg − bowl avg</span>}>
                  <div className="space-y-0.5">
                    {data.all_rounders.map(a => (
                      <div key={a.player_id} className="flex items-center justify-between gap-3 text-sm py-0.5">
                        <div className="min-w-0 flex items-baseline gap-2">
                          <span className="truncate">{a.name}</span>
                          <span className="text-pb-faintest text-[11px] shrink-0">{a.role}</span>
                        </div>
                        <div className="flex items-center gap-3 whitespace-nowrap pb-num text-pb-faint">
                          <span>{a.runs} @ {a.bat_avg ?? '—'}</span>
                          <span>{a.wickets}w @ {a.bowl_avg ?? '—'}</span>
                          {a.diff != null && <span className="font-semibold w-12 text-right" style={{ color: a.diff >= 0 ? 'var(--pb-brand)' : 'var(--pb-amber)' }}>{a.diff >= 0 ? '+' : ''}{a.diff}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                  <Note>Ranked by batting average − bowling average; a positive figure leans batting.</Note>
                </Card>
              )}

              {data.fielding && (data.fielding.fielders?.length > 0 || data.fielding.keepers?.length > 0) && (
                <div className="grid gap-4 lg:grid-cols-2">
                  <Card title="Top fielders">
                    {data.fielding.fielders?.length ? data.fielding.fielders.map(f => (
                      <div key={f.player_id} className="flex justify-between gap-2 py-0.5 text-sm"><span className="truncate">{f.name}</span><span className="pb-num text-pb-faint whitespace-nowrap">{f.catches}c{f.run_outs ? ` · ${f.run_outs} ro` : ''}</span></div>
                    )) : <Empty>—</Empty>}
                    {data.fielding.combos?.length > 0 && (
                      <div className="mt-3 pt-3 border-t pb-hairline">
                        <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-1">Catching combos</div>
                        {data.fielding.combos.slice(0, 5).map((c, i) => <div key={i} className="text-[12px] text-pb-faint py-0.5">{c.fielder} off {c.bowler} <span className="pb-num">×{c.count}</span></div>)}
                      </div>
                    )}
                  </Card>
                  <Card title="Wicketkeepers">
                    {data.fielding.keepers?.length ? data.fielding.keepers.map(k => (
                      <div key={k.player_id} className="flex justify-between gap-2 py-0.5 text-sm"><span className="truncate">{k.name}</span><span className="pb-num text-pb-faint whitespace-nowrap">{k.catches}c · {k.stumpings}st</span></div>
                    )) : <Empty>No keeper data.</Empty>}
                  </Card>
                </div>
              )}

              {!data.all_rounders?.length && !data.captaincy?.length && !(data.fielding?.fielders?.length || data.fielding?.keepers?.length) && (
                <Card><Empty>Not enough per-player data in this period.</Empty></Card>
              )}
            </div>
          )}

          {data.coverage?.notes?.length > 0 && (
            <div className="text-pb-faintest text-[11px] mt-3 flex items-start gap-1.5">
              <Icon name="info" size={13} className="mt-0.5 shrink-0" />
              <span>{data.coverage.notes.join(' ')}</span>
            </div>
          )}
        </>
      )}
    </IQLayout>
  )
}
