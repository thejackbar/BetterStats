import { useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import StatCard from '../../components/StatCard'
import LoadingSpinner from '../../components/LoadingSpinner'
import { thiings, ThiingIcon } from '../../assets/thiings'
import { aflApi } from '../aflApi'
import { SectionTitle, Select, GameRow, ClubCrest, displayName } from '../components/bits'

const MILESTONE_ICON = { games: thiings.calendar, goals: thiings.target }

function seasonSpan(r) {
  if (!r.first_year) return null
  return r.first_year === r.last_year ? String(r.first_year) : `${r.first_year}–${r.last_year}`
}

function MilestoneRow({ m, base }) {
  const pct = Math.round((m.current / m.target) * 100)
  return (
    <Link to={`${base}/players/${m.player_id}`} className="block hover:opacity-80 transition-opacity">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2 min-w-0">
          <ThiingIcon src={MILESTONE_ICON[m.type] || thiings.target} alt="" className="w-4 h-4" />
          <div className="min-w-0">
            <span className="text-pb-text text-[13px] font-semibold truncate block">{m.name}</span>
            <span className="font-mono text-[10px] text-pb-faint tracking-wide2">
              {m.target?.toLocaleString()} {m.type}
            </span>
          </div>
        </div>
        <span className="font-mono text-[11px] text-pb-dim ml-2 whitespace-nowrap">
          <span className="text-pb-text font-bold">{m.needed?.toLocaleString()}</span> to go
        </span>
      </div>
      <div className="h-1 bg-pb-hairline rounded-sm overflow-hidden">
        <div className="h-full" style={{ width: `${Math.min(100, pct)}%`, background: 'var(--pb-accent)' }} />
      </div>
    </Link>
  )
}

const MILESTONE_CATS = { games: 'Games', goals: 'Goals' }

function MilestonesSection({ milestones, base }) {
  const PER_COL = 6
  const grouped = {}
  for (const m of milestones) {
    if (!grouped[m.type]) grouped[m.type] = []
    grouped[m.type].push(m)
  }
  const cats = ['games', 'goals'].filter(c => grouped[c]?.length)
  if (!cats.length) return null

  return (
    <div>
      <SectionTitle>Milestones in reach</SectionTitle>
      <div className={`grid gap-4 ${cats.length === 2 ? 'md:grid-cols-2' : 'grid-cols-1'}`}>
        {cats.map(cat => (
          <div key={cat} className="pb-card p-4">
            <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-3">
              {MILESTONE_CATS[cat]}
            </span>
            <ul className="flex flex-col gap-3">
              {grouped[cat].slice(0, PER_COL).map((m, i) => (
                <li key={i} className={i ? 'pb-hairline-t pt-3' : ''}>
                  <MilestoneRow m={m} base={base} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { club } = useOutletContext()
  const [seasonId, setSeasonId] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const base = `/${club.slug}`

  useEffect(() => {
    setLoading(true)
    aflApi.getSummary(club.id, { season_id: seasonId })
      .then(setData)
      .finally(() => setLoading(false))
  }, [club.id, seasonId])

  if (loading && !data) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>
  const s = data?.summary || {}

  // A result card is only shown when it's trustworthy: a specific season
  // that actually has real synced match data, or — with no season picked —
  // a club whose entire history is synced (no Import Stats upload sitting
  // underneath it). Otherwise "Games: 145" reads as the whole story when
  // it's really just the synced sliver of a much longer real history.
  const showResults = seasonId ? (s.played || 0) > 0 : !data?.has_imported_history

  // Sub-line under each player mirrors where BetterStats (Core)'s equivalent
  // board shows "AVG · HS" — AFL has no batting-style average, so a career
  // span (debut season – final season) fills the same slot.
  //
  // `cols` is the numeric columns on the right, so the goal kickers board can
  // carry games alongside goals and a goals-per-game average without the games
  // board growing columns it has no use for.
  const board = (title, rows, cols) => (
    <div className="pb-card p-4">
      <SectionTitle>{title}</SectionTitle>
      {(rows || []).length === 0 && <p className="text-sm text-pb-faint">No data yet.</p>}
      {(rows || []).length > 0 && (
        <div className="flex items-center gap-2.5 pb-1.5 mb-2 pb-hairline-b">
          <span className="w-4 shrink-0" />
          <span className="w-8 shrink-0" />
          <span className="flex-1" />
          {cols.map(c => (
            <span key={c.key} className="w-11 shrink-0 text-right font-mono text-[9px] uppercase tracking-wide text-pb-faintest">
              {c.label}
            </span>
          ))}
        </div>
      )}
      <ol className="space-y-2.5">
        {(rows || []).map((r, i) => (
          <li key={r.player_id} className="flex items-center gap-2.5 text-sm">
            <span className="font-mono text-pb-faintest w-4 shrink-0">{i + 1}</span>
            {r.photo_url
              ? <img src={r.photo_url} alt="" className="h-8 w-8 rounded-full object-cover shrink-0" />
              : <span className="h-8 w-8 rounded-full bg-pb-surface2 text-[11px] flex items-center justify-center text-pb-faint shrink-0">
                  {(displayName(r) || '?').split(' ').map(w => w[0]).slice(0, 2).join('')}
                </span>}
            <Link to={`${base}/players/${r.player_id}`} className="flex-1 min-w-0 hover:text-[var(--pb-accent)]">
              <span className="block truncate">{displayName(r)}</span>
              {seasonSpan(r) && <span className="block font-mono text-[10px] text-pb-faintest">{seasonSpan(r)}</span>}
            </Link>
            {cols.map(c => (
              <span
                key={c.key}
                className={`w-11 shrink-0 text-right pb-num ${c.lead ? 'font-bold' : 'text-pb-dim'}`}
                style={c.lead ? { color: 'var(--pb-accent)' } : undefined}
              >
                {c.get(r)}
              </span>
            ))}
          </li>
        ))}
      </ol>
    </div>
  )

  // A career goals-per-game rate. Guarded rather than shown as 0.00, since a
  // player carrying goals with no games recorded (an older import) would
  // otherwise read as if he never scored.
  const avgGoals = (r) => (r.games > 0 ? (r.goals / r.games).toFixed(2) : '—')

  return (
    <div className="space-y-6">
      {/* Sized to match BetterCricket's PageHeader (lib/presskit.jsx) so the
          two sports' club pages open the same way: gradient bar, crest,
          eyebrow, then the club name at 40/56px. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-stretch gap-3.5 min-w-0">
          <span className="w-1 rounded-full shrink-0" style={{ background: 'var(--pb-gradient)' }} />
          <div className="flex items-center gap-4 min-w-0">
            <ClubCrest club={club} />
            <div className="min-w-0">
              <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block">
                {club.short_name || club.name} · Club dashboard
              </span>
              <h1 className="font-display text-[40px] sm:text-[56px] font-bold tracking-tight leading-[0.95] mt-1.5 text-pb-text">
                {club.name}
              </h1>
            </div>
          </div>
        </div>
        <Select
          value={seasonId}
          onChange={setSeasonId}
          placeholder="All seasons"
          options={(club.seasons || []).map(x => ({ value: x.id, label: x.name }))}
        />
      </div>

      {showResults && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Games" value={s.played} accent large />
          <StatCard label="Wins" value={s.wins} large />
          <StatCard label="Losses" value={s.losses} large />
          <StatCard label="Draws" value={s.draws} large />
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        {board('Most games', data?.most_games, [
          { key: 'games', label: 'Games', lead: true, get: r => r.games },
        ])}
        {board('Leading goal kickers', data?.top_goal_kickers, [
          { key: 'games', label: 'GP', get: r => r.games },
          { key: 'goals', label: 'Goals', lead: true, get: r => r.goals },
          { key: 'avg', label: 'Avg', get: avgGoals },
        ])}
      </div>

      {(data?.milestones_in_reach || []).length > 0 && (
        <MilestonesSection milestones={data.milestones_in_reach} base={base} />
      )}

      <div className="grid lg:grid-cols-2 gap-4">
        <div>
          <SectionTitle right={<Link to={`${base}/games`} className="text-xs text-[var(--pb-accent)]">All games →</Link>}>
            Recent results
          </SectionTitle>
          <div className="space-y-2">
            {(data?.recent_games || []).map(g => <GameRow key={g.id} game={g} base={base} />)}
            {(data?.recent_games || []).length === 0 && <p className="text-sm text-pb-faint">No results synced yet.</p>}
          </div>
        </div>
        <div>
          <SectionTitle>Upcoming</SectionTitle>
          <div className="space-y-2">
            {(data?.upcoming_games || []).map(g => (
              <div key={g.id} className="pb-card p-3 text-sm flex flex-wrap gap-x-4 gap-y-1 items-center">
                <div className="w-28 shrink-0">
                  <div className="text-[11px] text-pb-faint font-mono">{g.round_name}</div>
                  <div className="text-[11px] text-pb-faintest font-mono">{g.played_at} {g.start_time ? g.start_time.slice(0, 5) : ''}</div>
                </div>
                <div className="flex-1">
                  <div>{g.home_team} <span className="text-pb-faint">v</span> {g.away_team}</div>
                  <div className="text-[11px] text-pb-faint">{g.venue || ''}</div>
                </div>
                <span className="text-[11px] text-pb-faint">{g.grade_name}</span>
              </div>
            ))}
            {(data?.upcoming_games || []).length === 0 && <p className="text-sm text-pb-faint">No upcoming fixtures.</p>}
          </div>
        </div>
      </div>
    </div>
  )
}
