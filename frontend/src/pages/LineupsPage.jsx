// Public club Lineups — published team lists, home v away.
//
// Clubs name their side on play.cricket.com.au and Cricket Australia serves it
// on the match record, so this is live: a team appears the moment its club
// publishes it, and reads "not named yet" until then. Both sides are shown so
// supporters can see who they're up against; our own players carry their club
// photo and link to their profile, everyone else falls back to the team crest.
//
// The match header deliberately mirrors MatchScorecard's (same TeamBadge, same
// home-left / away-right rule regardless of who bats first) so a fixture reads
// the same before the game as it does after it.
//
// Nothing here is stored. The record of who actually played still comes from
// the scorecard once the game is synced.
import { useState, useEffect, useCallback } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { useClubData } from '../hooks/useClubData'
import { usePageMeta } from '../hooks/usePageMeta'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import ClubPinGate from './ClubPinGate'
import TeamBadge from '../components/TeamBadge'
import SeasonSelector from '../components/SeasonSelector'
import { PageHeader, PbSpinner, Btn } from '../lib/presskit'

const PAGE = 6

function fmtDay(d) {
  if (!d) return 'Date TBC'
  try {
    return new Date(d + 'T00:00:00').toLocaleDateString(undefined, {
      weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
    })
  } catch { return d }
}

function fmtTime(t) {
  if (!t) return null
  const [h, m] = t.split(':').map(Number)
  if (Number.isNaN(h)) return t
  const ampm = h >= 12 ? 'pm' : 'am'
  return `${h % 12 || 12}${m ? `.${String(m).padStart(2, '0')}` : ''}${ampm}`
}

/* ── Category (Senior/Junior/Women's/…) + Finals — both server-filtered,
   based on how the GRADE is classified, not a per-player attribute. ────── */

function CategoryFilters({ category, setCategory, categories, finalsOnly, setFinalsOnly }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {categories.length > 0 && (
        <div className="flex items-center border pb-hairline rounded overflow-hidden">
          {[{ key: '', label: 'All' }, ...categories].map((c) => (
            <button key={c.key || 'all'} onClick={() => setCategory(c.key)}
              className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
                category === c.key ? 'bg-pb-accent/15 text-pb-accent' : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'}`}>
              {c.label}
            </button>
          ))}
        </div>
      )}
      <div className="flex items-center border pb-hairline rounded overflow-hidden">
        {[{ v: false, label: 'All games' }, { v: true, label: 'Finals' }].map((o) => (
          <button key={o.label} onClick={() => setFinalsOnly(o.v)}
            className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold tracking-wide3 transition-colors border-r pb-hairline-r last:border-r-0 ${
              finalsOnly === o.v ? 'bg-pb-accent/15 text-pb-accent' : 'text-pb-faint hover:text-pb-dim hover:bg-pb-surface2'}`}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── A player's face: their photo, else the team crest ──────────────────── */

function PlayerAvatar({ photoUrl, logoUrl, name, size = 28 }) {
  const [failed, setFailed] = useState(false)
  const src = (!failed && photoUrl) || null
  if (src) {
    return (
      <img src={src} alt="" onError={() => setFailed(true)}
        className="shrink-0 rounded-full object-cover bg-pb-surface2"
        style={{ width: size, height: size }} />
    )
  }
  // No player photo — the club crest stands in, so a row is never a blank hole.
  return <TeamBadge name={name} logoUrl={logoUrl} size={size} />
}

function RoleTag({ children, title }) {
  return (
    <span title={title} className="font-mono text-[8.5px] px-1 py-0.5 rounded shrink-0 leading-none"
      style={{ background: 'color-mix(in srgb, var(--pb-accent) 16%, transparent)', color: 'var(--pb-accent)' }}>
      {children}
    </span>
  )
}

function PlayerRow({ p, logoUrl, linkable }) {
  const inner = (
    <>
      <PlayerAvatar photoUrl={p.photo_url} logoUrl={logoUrl} name={p.name} />
      <span className={`truncate text-[13px] ${p.redacted ? 'text-pb-faintest font-mono' : ''}`}>{p.name}</span>
      {p.is_captain && <RoleTag title="Captain">C</RoleTag>}
      {p.is_wicket_keeper && <RoleTag title="Wicket keeper">WK</RoleTag>}
    </>
  )
  const cls = 'flex items-center gap-2 py-1 min-w-0'
  return linkable && p.player_id
    ? <Link to={`/players/${p.player_id}`} className={`${cls} hover:text-pb-accent transition-colors`}>{inner}</Link>
    : <div className={cls}>{inner}</div>
}

/* ── One side's team list ───────────────────────────────────────────────── */

function TeamLineup({ team }) {
  return (
    <div className={`rounded-xl border px-3.5 py-3 ${team.is_ours ? 'border-pb-accent/40' : 'pb-hairline'}`}>
      <div className="flex items-center gap-2 mb-2 pb-2 border-b pb-hairline">
        <TeamBadge name={team.name} logoUrl={team.logo_url} size={24} />
        <div className="min-w-0 flex-1">
          <div className="font-display font-bold text-[13px] truncate leading-tight">{team.name}</div>
          {team.is_ours && <div className="font-mono text-[8.5px] text-pb-accent tracking-wide2">OUR SIDE</div>}
        </div>
        {team.published && (
          <span className="font-mono text-[10px] text-pb-faint shrink-0">{team.players.length}</span>
        )}
      </div>

      {team.published ? (
        // Two columns on wider cards so an XI reads in one glance.
        <div className="grid gap-x-4 sm:grid-cols-2">
          {team.players.map((p, i) => (
            <PlayerRow key={p.participant_id || i} p={p} logoUrl={team.logo_url} linkable={team.is_ours} />
          ))}
        </div>
      ) : (
        <div className="text-pb-faint text-[12.5px] py-2">Not named yet.</div>
      )}

      {team.staff?.length > 0 && (
        <div className="mt-2 pt-2 border-t pb-hairline text-[11px] text-pb-faint">
          {team.staff.map((s) => `${s.name}${s.roles?.length ? ` (${s.roles.join(', ')})` : ''}`).join(' · ')}
        </div>
      )}
    </div>
  )
}

/* ── Match header — same shape as the scorecard's ───────────────────────── */

function MatchCard({ m }) {
  // Home left, away right, always — matching MatchScorecard's header rule.
  // The feed's own isHome flag decides; if it's missing on both sides (rare)
  // the array order stands in.
  const teams = [...m.teams]
  const homeIdx = teams.findIndex((t) => t.is_home)
  const ordered = homeIdx > 0 ? [teams[homeIdx], ...teams.filter((_, i) => i !== homeIdx)] : teams
  const [home, away] = ordered
  const meta = [m.round, m.venue].filter(Boolean).join(' · ')
  const played = m.status === 'COMPLETED'

  const Side = ({ team, align }) => (
    <div className={`flex items-center gap-2.5 min-w-0 ${align === 'right' ? 'flex-row-reverse text-right' : ''}`}>
      <TeamBadge name={team?.name} logoUrl={team?.logo_url} size={30} />
      <div className="min-w-0">
        <div className="font-display font-bold text-[13px] sm:text-[15px] truncate leading-tight">{team?.name || '—'}</div>
        {team?.score_text && (
          <div className="font-mono text-[13px] sm:text-[15px] leading-tight"
            style={{ color: team.is_winner ? 'var(--pb-positive)' : 'var(--pb-dim)' }}>
            {team.score_text}
          </div>
        )}
      </div>
    </div>
  )

  return (
    <div className="pb-card overflow-hidden">
      {(m.grade || meta) && (
        <div className="px-4 pt-2.5 font-mono text-[9.5px] tracking-wide3 text-pb-faint truncate">
          {[m.grade, meta].filter(Boolean).join(' · ')}
        </div>
      )}
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:gap-4 px-3 sm:px-4 py-3">
        <Side team={home} align="left" />
        <div className="flex flex-col items-center gap-0.5 px-1 min-w-[76px] text-center">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">
            {played ? 'RESULT' : 'V'}
          </span>
          <span className="font-mono text-[9.5px] text-pb-faint leading-snug">
            {fmtDay(m.date)}{m.time && !played ? <><br />{fmtTime(m.time)}</> : null}
          </span>
        </div>
        <Side team={away} align="right" />
      </div>
      {/* Only once it's played: on an unplayed match the feed puts the
          scheduled start time in resultText, which the header already shows. */}
      {played && m.result_text && (
        <div className="px-4 pb-2 font-mono text-[10px] text-pb-faint text-center">
          {m.result_text}
        </div>
      )}
      {played && (
        <div className="px-4 pb-3 text-center">
          <Link to={`/games/${m.match_id}`}
            className="font-mono text-[10px] px-2 py-1 rounded border pb-hairline text-pb-faint hover:text-pb-accent hover:border-pb-accent/40 transition-colors">
            ↗ Full scorecard
          </Link>
        </div>
      )}

      <div className="grid gap-3 px-3 sm:px-4 pb-4 lg:grid-cols-2">
        {ordered.map((t) => <TeamLineup key={t.id || t.name} team={t} />)}
      </div>

      {m.officials?.length > 0 && (
        <div className="px-4 pb-3 text-[11px] text-pb-faint">
          {m.officials.map((o) => `${o.name}${o.role ? ` (${o.role})` : ''}`).join(' · ')}
        </div>
      )}
    </div>
  )
}

/* ── Single-match view — deep-linked from a Fixtures-page row ("↗ Lineup"),
   so a supporter lands straight on that game rather than searching the list. */

function SingleMatch({ orgId, matchId, clubSlug }) {
  const [match, setMatch] = useState(undefined) // undefined = loading, null = not found

  useEffect(() => {
    let alive = true
    setMatch(undefined)
    api.getOrgLineup(orgId, matchId)
      .then((d) => { if (alive) setMatch(d) })
      .catch(() => { if (alive) setMatch(null) })
    return () => { alive = false }
  }, [orgId, matchId])

  return (
    <>
      <Link to={`/${clubSlug}/lineups`}
        className="inline-block mb-4 font-mono text-[11px] text-pb-faint hover:text-pb-accent">
        ← All lineups
      </Link>
      {match === undefined ? <PbSpinner message="Loading lineup…" /> : match === null ? (
        <div className="pb-card px-5 py-10 text-center text-pb-faint text-sm">
          No lineup found for that match.
        </div>
      ) : (
        <MatchCard m={match} />
      )}
    </>
  )
}

/* ── Page ───────────────────────────────────────────────────────────────── */

export default function LineupsPage() {
  const { clubSlug } = useParams()
  const [searchParams] = useSearchParams()
  const matchId = searchParams.get('match')
  const { club, orgId, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  useClubTheme(club)
  usePageMeta({
    title: club?.name ? `${club.name} Lineups — BetterCricket` : null,
    description: club?.name ? `Published team lists for ${club.name}.` : null,
    image: club?.logo_url || null,
  })

  const { seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade } = useClubData(orgId)
  const [mode, setMode] = useState('upcoming')
  const [category, setCategory] = useState('')       // '' | senior | junior | womens | masters | mixed
  const [finalsOnly, setFinalsOnly] = useState(false)
  const [data, setData] = useState(null)
  // Kept separately from `data` (which resets to null on every refetch) so the
  // Category pill row doesn't flash empty while a filter change is loading.
  const [availableCategories, setAvailableCategories] = useState([])
  const [more, setMore] = useState([])      // pages loaded beyond the first
  const [loadingMore, setLoadingMore] = useState(false)

  const params = useCallback((offset) => ({
    mode,
    limit: PAGE,
    offset,
    category: category || undefined,
    finalsOnly,
    ...(mode === 'past' ? { seasonId: selectedSeason, gradeId: selectedGrade } : {}),
  }), [mode, selectedSeason, selectedGrade, category, finalsOnly])

  useEffect(() => {
    if (!orgId || matchId) return // a single deep-linked match skips the list entirely
    let alive = true
    setData(null); setMore([])
    api.getOrgLineups(orgId, params(0))
      .then((d) => { if (alive) { setData(d); if (d.categories) setAvailableCategories(d.categories) } })
      .catch(() => { if (alive) setData({ matches: [], source: mode, has_more: false }) })
    return () => { alive = false }
  }, [orgId, matchId, params, mode])

  const loadMore = async () => {
    const loaded = (data?.matches?.length || 0) + more.reduce((n, p) => n + p.matches.length, 0)
    setLoadingMore(true)
    try {
      const next = await api.getOrgLineups(orgId, params(loaded))
      setMore((m) => [...m, next])
    } catch { /* the button simply stays put on a failed page fetch */ }
    finally { setLoadingMore(false) }
  }

  if (locked) return <ClubPinGate slug={clubSlug} lockInfo={locked} unlock={unlock} requestAccess={requestAccess} />
  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />

  const pages = data ? [data, ...more] : []
  const matches = pages.flatMap((p) => p.matches || [])
  const hasMore = pages.length ? pages[pages.length - 1].has_more : false
  // 'recent' = asked for upcoming, but nothing is scheduled.
  const fellBack = data?.source === 'recent'

  const tab = (key, label) => (
    <button key={key} onClick={() => setMode(key)}
      className={`px-3.5 py-1.5 text-[12px] font-mono tracking-wide2 rounded-lg transition-colors ${
        mode === key ? 'bg-pb-accent/12 text-pb-accent' : 'text-pb-faint hover:text-pb-text'}`}>
      {label}
    </button>
  )

  if (matchId) {
    return (
      <div className="min-h-screen bg-pb-bg text-pb-text">
        <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
          <PageHeader eyebrow={`LINEUP · ${club?.name?.toUpperCase() || ''}`} title="This game." />
          <SingleMatch orgId={orgId} matchId={matchId} clubSlug={clubSlug} />
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`LINEUPS · ${club?.name?.toUpperCase() || ''}`}
          title={mode === 'past' || fellBack ? 'Who took the field.' : "Who's playing."}
        />

        <div className="flex flex-wrap items-center gap-2 mb-4">
          <div className="flex items-center gap-1 p-1 rounded-xl bg-pb-surface2">
            {tab('upcoming', 'UPCOMING')}
            {tab('past', 'PAST')}
          </div>
          <Link to={`/${clubSlug}/fixtures`}
            className="font-mono text-[10px] px-2 py-1 rounded border pb-hairline text-pb-faint hover:text-pb-accent hover:border-pb-accent/40 transition-colors">
            ↗ Fixtures
          </Link>
        </div>

        {mode === 'past' && (
          <div className="mb-3">
            <SeasonSelector
              seasons={seasons}
              grades={grades}
              selectedSeason={selectedSeason}
              setSelectedSeason={setSelectedSeason}
              selectedGrade={selectedGrade}
              setSelectedGrade={setSelectedGrade}
              showGenderFilter={false}
              showFinalsFilter={false}
              showCaptainFilter={false}
            />
          </div>
        )}

        <div className="mb-5">
          <CategoryFilters
            category={category} setCategory={setCategory}
            categories={availableCategories}
            finalsOnly={finalsOnly} setFinalsOnly={setFinalsOnly}
          />
        </div>

        {fellBack && (
          <div className="mb-4 text-[12.5px] text-pb-faint">
            Nothing scheduled right now, so these are the most recent sides.
          </div>
        )}

        {data === null ? <PbSpinner message="Loading lineups…" /> : matches.length === 0 ? (
          <div className="pb-card px-5 py-10 text-center text-pb-faint text-sm">
            {mode === 'past'
              ? 'No team lists for this season and grade.'
              : "No team lists to show yet. They'll appear once the next round is scheduled and sides are named."}
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-4">
              {matches.map((m) => <MatchCard key={m.match_id} m={m} />)}
            </div>
            {hasMore && (
              <div className="text-center mt-5">
                <Btn onClick={loadMore} disabled={loadingMore}>
                  {loadingMore ? 'Loading…' : 'Load more'}
                </Btn>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
