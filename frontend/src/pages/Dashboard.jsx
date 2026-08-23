import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useClubData, useRecentGames } from '../hooks/useClubData'
import { useGradeFilters } from '../hooks/useGradeCategories'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { useAuth } from '../contexts/AuthContext'
import { CAP } from '../lib/capabilities'
import { api } from '../lib/api'
import SeasonSelector from '../components/SeasonSelector'
import ClubInactive from './ClubInactive'
import ClubPinGate from './ClubPinGate'
import { useNameFormat } from '../lib/nameFormat'
import { usePageMeta } from '../hooks/usePageMeta'
import { MILESTONE_ICON_SRC, ThiingIcon, thiings } from '../assets/thiings'
import {
  AnimatedNum, Sparkline, MiniBars, Label, Card, Btn,
  ResultPill, Kpi, PageHeader, PbSpinner,
} from '../lib/presskit'
import { fmt2, fmtCount } from '../lib/cricketFormat'

const SPONSOR_IMAGE = import.meta.env.VITE_SPONSOR_IMAGE || ''
const SPONSOR_URL = import.meta.env.VITE_SPONSOR_URL || ''
const SPONSOR_TEXT = import.meta.env.VITE_SPONSOR_TEXT || ''

function SponsorBanner() {
  if (!SPONSOR_IMAGE && !SPONSOR_TEXT) return null
  const inner = (
    <div className="flex items-center justify-center gap-4 py-3 px-5">
      {SPONSOR_IMAGE && <img src={SPONSOR_IMAGE} alt="Sponsor" className="h-10 object-contain" />}
      {SPONSOR_TEXT && <span className="text-pb-dim text-sm">{SPONSOR_TEXT}</span>}
    </div>
  )
  return (
    <div className="pb-card mb-6">
      <Label className="block text-center pt-3 pb-0">PROUDLY SPONSORED BY</Label>
      {SPONSOR_URL ? <a href={SPONSOR_URL} target="_blank" rel="noopener noreferrer">{inner}</a> : inner}
    </div>
  )
}

function MilestoneRow({ m }) {
  const pct = Math.round((m.current / m.target) * 100)
  const milestoneLabel = m.target ? `${m.target?.toLocaleString()} ${m.type || ''}` : ''
  return (
    <Link to={`/players/${m.player_id}`} className="block hover:opacity-80 transition-opacity">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2 min-w-0">
          <ThiingIcon src={MILESTONE_ICON_SRC[m.type] || thiings.target} alt="" className="w-4 h-4" />
          <div className="min-w-0">
            <span className="text-pb-text text-[13px] font-semibold truncate block">{m.name}</span>
            {milestoneLabel && <span className="font-mono text-[10px] text-pb-faint tracking-wide2">{milestoneLabel}</span>}
          </div>
        </div>
        <span className="font-mono text-[11px] text-pb-dim ml-2 whitespace-nowrap">
          <span className="text-pb-text font-bold">{m.needed?.toLocaleString()}</span> to go
        </span>
      </div>
      <div className="h-1 bg-pb-hairline rounded-sm overflow-hidden">
        <div className="h-full" style={{ width: `${Math.min(100, pct)}%`, background: "var(--pb-accent)" }} />
      </div>
    </Link>
  )
}

const MILESTONE_CATS = { batting: 'Batting', bowling: 'Bowling', fielding: 'Fielding', matches: 'Matches Played' }

function MilestonesSection({ milestones, loading }) {
  const PER_COL = 8

  const grouped = {}
  for (const m of milestones) {
    const cat = m.category || 'batting'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(m)
  }
  const cats = ['batting', 'bowling', 'fielding', 'matches'].filter(c => grouped[c])

  if (loading) return <PbSpinner message="Loading milestones…" />
  if (!cats.length) return <p className="text-pb-faint text-sm py-4">No upcoming milestones.</p>

  return (
    <div className={`grid gap-4 ${cats.length >= 3 ? 'md:grid-cols-2 xl:grid-cols-4' : cats.length === 2 ? 'md:grid-cols-2' : 'grid-cols-1'}`}>
      {cats.map(cat => (
        <div key={cat}>
          <Label className="block mb-3">{(MILESTONE_CATS[cat] || cat).toUpperCase()}</Label>
          <ul className="flex flex-col gap-3">
            {(grouped[cat] || []).slice(0, PER_COL).map((m, i) => (
              <li key={i} className={i ? "pb-hairline-t pt-3" : ""}>
                <MilestoneRow m={m} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  useClubTheme(club)
  const fmt = useNameFormat(club)

  const clubJsonLd = club?.name ? {
    '@context': 'https://schema.org',
    '@type': 'SportsTeam',
    name: club.name,
    sport: 'Cricket',
    url: `https://betterat.cricket/${clubSlug}`,
    ...(club.logo_url ? { logo: club.logo_url } : {}),
    areaServed: { '@type': 'Country', name: 'Australia' },
  } : null
  usePageMeta({
    title: club?.name
      ? `${club.name} - Cricket Stats, Records & Players | BetterCricket`
      : 'Club Cricket Stats | BetterCricket',
    description: club?.name
      ? `Live cricket statistics, leaderboards, all-time records and player profiles for ${club.name}, updated automatically on BetterCricket.`
      : null,
    image: club?.logo_url || null,
    url: `https://betterat.cricket/${clubSlug}`,
    jsonLd: clubJsonLd,
  })

  const { org, seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade, finalsOnly, setFinalsOnly, loading, error } = useClubData(orgId)
  const gradeFilters = useGradeFilters(orgId)
  const {
    gradeType, setGradeType, matchFormat, setMatchFormat,
    available: availableCategories, availableFormats, defaultCategories,
    categoriesParam, formatsParam,
  } = gradeFilters
  const { games, loading: gamesLoading } = useRecentGames(orgId, {
    seasonId: selectedSeason,
    gradeId: selectedGrade,
    categories: categoriesParam,
    formats: formatsParam,
  })

  const [topBatters, setTopBatters] = useState([])
  const [topBowlers, setTopBowlers] = useState([])
  const [summary, setSummary] = useState(null)
  const [milestones, setMilestones] = useState([])
  const [fixtures, setFixtures] = useState([])
  const [statsLoading, setStatsLoading] = useState(true)
  const [milestonesLoading, setMilestonesLoading] = useState(true)
  const [fixturesLoading, setFixturesLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [syncDone, setSyncDone] = useState(false)

  // Sync is an admin-only action — only show it to a signed-in admin who can
  // actually run it for THIS club. Super admins can sync any club; everyone
  // else only their own. Public visitors (and admins of other clubs) never see it.
  const { user, hasCapability } = useAuth()
  const canSync = hasCapability(CAP.RUN_SYNC) &&
    (user?.role === 'super_admin' || user?.club_id === orgId)

  useEffect(() => {
    if (!orgId) return
    setStatsLoading(true)
    const scope = { categories: categoriesParam, formats: formatsParam }
    Promise.allSettled([
      api.battingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 5, finalsOnly, ...scope }),
      api.bowlingLeaderboard(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, limit: 5, finalsOnly, ...scope }),
      api.getOrgSummary(orgId, { seasonId: selectedSeason, gradeId: selectedGrade, ...scope }),
    ])
      .then(([b, bw, s]) => {
        if (b.status === 'fulfilled') setTopBatters(b.value)
        if (bw.status === 'fulfilled') setTopBowlers(bw.value)
        if (s.status === 'fulfilled') setSummary(s.value)
      })
      .finally(() => setStatsLoading(false))
  }, [orgId, selectedSeason, selectedGrade, finalsOnly, categoriesParam, formatsParam])

  useEffect(() => {
    if (!orgId) return
    api.getUpcomingMilestones(orgId, 200)
      .then(setMilestones).catch(() => setMilestones([]))
      .finally(() => setMilestonesLoading(false))
    api.getOrgFixtures(orgId)
      .then(setFixtures).catch(() => setFixtures([]))
      .finally(() => setFixturesLoading(false))
  }, [orgId])

  if (locked) return <ClubPinGate slug={clubSlug} lockInfo={locked} unlock={unlock} requestAccess={requestAccess} />
  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />
  if (loading) return <PbSpinner message="Loading club data…" />
  if (error) return <div className="max-w-7xl mx-auto px-4 py-16 text-pb-red">Error: {error}</div>
  if (!org) return null

  const handleSync = async () => {
    if (syncing) return
    setSyncing(true); setSyncDone(false)
    try {
      await api.triggerSync(orgId)
      await new Promise(r => setTimeout(r, 8000))
      setSyncDone(true)
      setTimeout(() => setSyncDone(false), 3000)
    } finally { setSyncing(false) }
  }

  const currentSeason = seasons?.find(s => s.id === selectedSeason)
  const seasonLabel = selectedSeason ? (currentSeason?.name || 'All Seasons') : 'All Seasons'

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          gradient
          eyebrow={`${org.short_name || org.name} · CLUB DASHBOARD`}
          title={org.name}
          logo={club?.public_header_logo ? club.logo_url : null}
          logoAlt={`${org.name} crest`}
          meta={[
            summary && <span key="m">PLAYED <span className="text-pb-text">{fmtCount(summary.total_games)}</span></span>,
            summary && <span key="r"><span className="text-pb-text">{fmtCount(summary.total_runs)}</span> RUNS</span>,
            summary && <span key="w"><span className="text-pb-text">{fmtCount(summary.total_wickets)}</span> WICKETS</span>,
            summary && <span key="p"><span className="text-pb-text">{fmtCount(summary.total_players)}</span> PLAYERS</span>,
          ].filter(Boolean)}
          actions={[
            canSync && (
              <Btn key="sync" onClick={handleSync} disabled={syncing}>
                {syncing ? 'Syncing…' : syncDone ? '✓ Synced' : 'Sync ↻'}
              </Btn>
            ),
            <Link key="lb" to={`/${clubSlug}/leaderboard`} className="font-mono text-[11px] tracking-wide2 px-3.5 py-2 rounded hover:opacity-90 transition" style={{ background: "var(--pb-accent)", color: "var(--pb-on-accent)" }}>
              Leaderboard →
            </Link>,
          ].filter(Boolean)}
        />

        {/* Season / Grade filter */}
        <div className="mb-6">
          <SeasonSelector
            seasons={seasons}
            grades={grades}
            selectedSeason={selectedSeason}
            setSelectedSeason={setSelectedSeason}
            selectedGrade={selectedGrade}
            setSelectedGrade={setSelectedGrade}
            finalsOnly={finalsOnly}
            setFinalsOnly={setFinalsOnly}
            gradeType={gradeType}
            setGradeType={setGradeType}
            matchFormat={matchFormat}
            setMatchFormat={setMatchFormat}
            availableCategories={availableCategories}
            availableFormats={availableFormats}
            defaultCategories={defaultCategories}
            showGradeTypeFilter
            showMatchFormatFilter
            showGenderFilter={false}
            showCaptainFilter={false}
          />
        </div>

        {/* Summary KPIs */}
        {summary && (
          <>
            <div className={`grid gap-3 mb-3 ${summary.total_games > 0 ? 'grid-cols-2 lg:grid-cols-4' : 'grid-cols-1 sm:grid-cols-3'}`}>
              {summary.total_games > 0 && <Kpi label="WIN RATE" value={parseInt(summary.win_rate) || 0} suffix="%" accent />}
              <Kpi label="TOTAL RUNS" value={summary.total_runs || 0} />
              <Kpi label="TOTAL WICKETS" value={summary.total_wickets || 0} />
              <Kpi label="PLAYERS" value={summary.total_players || 0} />
            </div>

            {/* W/L/D breakdown */}
            <div className="pb-card p-4 mb-6 flex items-center gap-4 flex-wrap">
              <Label>RESULTS BREAKDOWN</Label>
              <div className="flex gap-4 font-mono text-[12px]">
                <span style={{ color: "var(--pb-accent)" }}><span className="font-bold">{summary.wins}</span> W</span>
                <span style={{ color: "var(--pb-red)" }}><span className="font-bold">{summary.losses}</span> L</span>
                <span className="text-pb-dim"><span className="font-bold">{summary.draws}</span> D</span>
              </div>
              {summary.highest_score && (
                <div className="ml-auto font-mono text-[11px] text-pb-dim tracking-wide2">
                  HS <span className="text-pb-text">{summary.highest_score}</span>
                </div>
              )}
            </div>
          </>
        )}

        {/* Two-col: leaders + milestones */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 mb-6">
          {/* Top run-scorers */}
          <Card className="xl:col-span-1" title={`TOP BATTERS · ${seasonLabel.toUpperCase()}`}
                action={<Link to={`/${clubSlug}/leaderboard`} className="text-2xs font-mono tracking-wide2 text-pb-dim hover:text-pb-text">ALL →</Link>}>
            {statsLoading ? <PbSpinner /> : topBatters.length === 0 ? (
              <p className="text-pb-faint text-sm py-2">No data yet.</p>
            ) : (
              <ol className="flex flex-col">
                {topBatters.map((p, i) => (
                  <li key={p.player_id} className={`flex items-center gap-3 py-2.5 ${i ? "pb-hairline-t" : ""}`}>
                    <span className="font-mono text-[10px] text-pb-faint w-4">{i + 1}</span>
                    <Link to={`/players/${p.player_id}`} className="flex-1 min-w-0">
                      <div className="text-pb-text text-[14px] font-semibold truncate">{fmt(p.name)}</div>
                      <div className="text-pb-faint font-mono text-[10.5px] tracking-wide2">
                        AVG {fmt2(p.average)} · HS {p.high_score ?? '—'}
                      </div>
                    </Link>
                    <span className="font-mono text-pb-text text-[14px] font-bold pb-num w-12 text-right" style={{ color: "var(--pb-accent)" }}>
                      {fmtCount(p.total_runs)}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          {/* Top wicket-takers */}
          <Card title={`TOP BOWLERS · ${seasonLabel.toUpperCase()}`}
                action={<Link to={`/${clubSlug}/leaderboard`} className="text-2xs font-mono tracking-wide2 text-pb-dim hover:text-pb-text">ALL →</Link>}>
            {statsLoading ? <PbSpinner /> : topBowlers.length === 0 ? (
              <p className="text-pb-faint text-sm py-2">No data yet.</p>
            ) : (
              <ol className="flex flex-col">
                {topBowlers.map((p, i) => (
                  <li key={p.player_id} className={`flex items-center gap-3 py-2.5 ${i ? "pb-hairline-t" : ""}`}>
                    <span className="font-mono text-[10px] text-pb-faint w-4">{i + 1}</span>
                    <Link to={`/players/${p.player_id}`} className="flex-1 min-w-0">
                      <div className="text-pb-text text-[14px] font-semibold truncate">{fmt(p.name)}</div>
                      <div className="text-pb-faint font-mono text-[10.5px] tracking-wide2">
                        AVG {fmt2(p.average)} · ECON {fmt2(p.economy)} · BEST {
                          p.best_bowling_figures ? p.best_bowling_figures.replace('-', '/') :
                          p.best_figures_wickets != null ? `${fmtCount(p.best_figures_wickets)} wickets` : '—'
                        }
                      </div>
                    </Link>
                    <span className="font-mono text-pb-text text-[14px] font-bold pb-num w-12 text-right" style={{ color: "var(--pb-accent)" }}>
                      {fmtCount(p.total_wickets)}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          {/* Upcoming milestones preview */}
          <Card title="MILESTONES IN REACH"
                action={<span className="text-2xs font-mono tracking-wide2 text-pb-faint">CLOSEST FIRST</span>}>
            {milestonesLoading ? <PbSpinner /> : (
              <ul className="flex flex-col gap-3">
                {milestones.slice(0, 5).length === 0
                  ? <p className="text-pb-faint text-sm py-2">No upcoming milestones.</p>
                  : milestones.slice(0, 5).map((m, i) => (
                      <li key={i} className={i ? "pb-hairline-t pt-3" : ""}><MilestoneRow m={m} /></li>
                    ))
                }
              </ul>
            )}
          </Card>
        </div>

        {/* Recent results */}
        <Card title="RECENT MATCHES" className="mb-6"
              action={<span className="text-2xs font-mono tracking-wide2 text-pb-faint">{games.length} GAMES</span>}>
          {gamesLoading ? <PbSpinner /> : games.length === 0 ? (
            <p className="text-pb-faint text-sm py-2">No recent games found.</p>
          ) : (
            <div className="overflow-x-auto pb-scroll -mx-2">
              <table className="w-full min-w-[560px] text-[13px]">
                <thead>
                  <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                    <th className="font-medium pb-2 pl-2">DATE</th>
                    <th className="font-medium pb-2">MATCH</th>
                    <th className="font-medium pb-2">GRADE</th>
                    <th className="font-medium pb-2 pr-2">RESULT</th>
                  </tr>
                </thead>
                <tbody>
                  {games.map((g, i) => (
                    <tr key={g.id} className={`${i ? "pb-hairline-t" : ""} hover:bg-pb-surface2 cursor-pointer`}>
                      <td className="py-2.5 pl-2 font-mono text-pb-dim text-[12px]">
                        {g.played_at ? new Date(g.played_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : '—'}
                      </td>
                      <td className="py-2.5">
                        <Link to={`/games/${g.id}`} className="text-pb-text hover:text-pb-accent font-medium">
                          {g.home_team} <span className="text-pb-faint text-[11px]">v</span> {g.away_team}
                        </Link>
                      </td>
                      <td className="py-2.5 font-mono text-pb-faint text-[11px] tracking-wide2">{g.grade?.name || '—'}</td>
                      <td className="py-2.5 pr-2"><ResultPill result={g.result} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Upcoming fixtures */}
        {!fixturesLoading && fixtures.length > 0 && (
          <Card title="UPCOMING FIXTURES" className="mb-6"
                action={<Link to={`/${clubSlug}/fixtures`} className="text-2xs font-mono tracking-wide2 text-pb-dim hover:text-pb-text">SEE ALL →</Link>}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {fixtures.slice(0, 3).map((f, i) => {
                const roundLabel = f.round != null ? `Rd ${f.round}` : null
                const meta = [f.grade, roundLabel].filter(Boolean).join(' · ')
                const time = f.time ? (() => {
                  const [h, m] = f.time.split(':')
                  const hour = parseInt(h, 10)
                  return `${hour > 12 ? hour - 12 : hour || 12}:${m}${hour >= 12 ? 'pm' : 'am'}`
                })() : null
                return (
                  <div key={f.id || i} className="pb-card-2 p-4 rounded border border-pb-hairline flex flex-col gap-1.5">
                    {meta && <Label>{meta}</Label>}
                    <div className="text-pb-text text-[15px] font-semibold leading-tight mt-1">
                      {f.home_team} <span className="text-pb-faint text-sm font-normal">v</span> {f.away_team}
                    </div>
                    <div className="font-mono text-pb-faint text-[10.5px] tracking-wide2">
                      {new Date(f.date + 'T00:00:00').toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' })}
                      {time && ` · ${time}`}
                    </div>
                    {f.venue && (
                      <div className="font-mono text-pb-faint text-[10.5px] tracking-wide2 truncate">{f.venue}</div>
                    )}
                    {f.id && (
                      <Link to={`/games/${f.id}`} className="mt-1 font-mono text-[10px] tracking-wide2 text-pb-dim hover:text-pb-accent transition self-start">
                        SCORECARD →
                      </Link>
                    )}
                  </div>
                )
              })}
            </div>
          </Card>
        )}

        <SponsorBanner />

        {/* Full milestones */}
        <Card title="MILESTONES IN REACH" className="mb-6">
          <MilestonesSection
            milestones={milestones}
            loading={milestonesLoading}
          />
        </Card>

        {/* Yearbook CTA */}
        <Link
          to={`/${clubSlug}/yearbook`}
          className="flex items-center justify-between gap-4 mb-6 px-5 py-4 rounded-xl border border-white/8 bg-white/2 hover:bg-white/4 hover:border-white/15 transition-colors group"
        >
          <div>
            <div className="font-mono text-[10px] tracking-wide3 text-pb-text/40 uppercase mb-1">Season Yearbook</div>
            <div className="text-[15px] font-semibold text-pb-text/80 group-hover:text-pb-text transition-colors">
              View the Season Yearbook
            </div>
            <div className="text-[12px] text-pb-text/35 mt-0.5">
              Stats, honour board, editorial reports &amp; season highlights
            </div>
          </div>
          <div className="shrink-0 font-mono text-[12px] text-pb-text/30 group-hover:text-pb-text/60 transition-colors">
            →
          </div>
        </Link>

        <div className="mt-4 pt-6 pb-hairline-t text-center">
          <p className="font-mono text-[10px] tracking-wide2 text-pb-faintest">
            POWERED BY <Link to="/" className="hover:text-pb-dim transition-colors">BETTER CRICKET</Link>
          </p>
        </div>
      </main>
    </div>
  )
}
