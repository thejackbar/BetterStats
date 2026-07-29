// Public club Fixtures — what's coming up, grouped by date.
//
// Sourced live from Cricket Australia's Grassroots feed (the club's own grades
// → each grade's match list, filtered to matches that haven't been played),
// so it needs no sync and appears the moment the association publishes the
// draw. Results live on the Games page; this is the forward-looking half.
import { useState, useEffect, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { usePageMeta } from '../hooks/usePageMeta'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import { PageHeader, PbSpinner } from '../lib/presskit'

function fmtDay(d) {
  if (!d) return 'Date TBC'
  try {
    return new Date(d + 'T00:00:00').toLocaleDateString(undefined, {
      weekday: 'long', day: 'numeric', month: 'long',
    })
  } catch { return d }
}

function fmtTime(t) {
  if (!t) return null
  const [h, m] = t.split(':').map(Number)
  if (Number.isNaN(h)) return t
  const ampm = h >= 12 ? 'pm' : 'am'
  const hr = h % 12 || 12
  return m ? `${hr}.${String(m).padStart(2, '0')}${ampm}` : `${hr}${ampm}`
}

// Days until a fixture, for the "this weekend" style caption.
function countdown(d) {
  if (!d) return null
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const then = new Date(d + 'T00:00:00')
  const days = Math.round((then - today) / 86400000)
  if (days < 0) return null
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  if (days <= 7) return `In ${days} days`
  return null
}

function FixtureRow({ fx, clubSlug }) {
  const time = fmtTime(fx.time)
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-3.5 border-t pb-hairline first:border-0">
      <div className="min-w-0 flex-1">
        <div className="font-display font-bold text-[15px]">
          {fx.home_team} <span className="text-pb-faint font-normal">v</span> {fx.away_team}
        </div>
        <div className="text-[12px] text-pb-faint mt-0.5">
          {[fx.grade, fx.round, fx.venue].filter(Boolean).join(' · ') || '—'}
        </div>
      </div>
      {time && <span className="font-mono text-[12px] text-pb-dim shrink-0">{time}</span>}
      <Link to={`/${clubSlug}/lineups?match=${fx.id}`}
        className="font-mono text-[10px] px-2 py-1 rounded border pb-hairline text-pb-faint hover:text-pb-accent hover:border-pb-accent/40 transition-colors shrink-0">
        ↗ Lineup
      </Link>
    </div>
  )
}

export default function FixturesPage() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive, notFound } = useClub(clubSlug)
  useClubTheme(club)
  usePageMeta({
    title: club?.name ? `${club.name} Fixtures — BetterCricket` : null,
    description: club?.name ? `Upcoming matches for ${club.name}.` : null,
    image: club?.logo_url || null,
  })

  const [fixtures, setFixtures] = useState(null)
  useEffect(() => {
    if (!orgId) return
    let alive = true
    api.getOrgFixtures(orgId)
      .then((d) => { if (alive) setFixtures(Array.isArray(d) ? d : []) })
      .catch(() => { if (alive) setFixtures([]) })
    return () => { alive = false }
  }, [orgId])

  // Group by playing date so a weekend's games read as one block.
  const days = useMemo(() => {
    const by = new Map()
    for (const fx of fixtures || []) {
      const key = fx.date || 'tbc'
      if (!by.has(key)) by.set(key, [])
      by.get(key).push(fx)
    }
    return [...by.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1))
  }, [fixtures])

  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`FIXTURES · ${club?.name?.toUpperCase() || ''}`}
          title="What's coming up."
        />

        {fixtures === null ? <PbSpinner message="Loading fixtures…" /> : days.length === 0 ? (
          <div className="pb-card px-5 py-10 text-center text-pb-faint text-sm">
            No fixtures scheduled right now. They'll appear here as soon as the association publishes the next round.
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {days.map(([date, list]) => {
              const soon = countdown(date)
              return (
                <div key={date} className="pb-card overflow-hidden">
                  <div className="flex items-baseline justify-between gap-3 px-4 py-2.5 border-b pb-hairline">
                    <span className="font-display font-bold text-[15px]">{fmtDay(date === 'tbc' ? null : date)}</span>
                    {soon && (
                      <span className="font-mono text-[10px] px-2 py-0.5 rounded-full"
                        style={{ background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)' }}>
                        {soon.toUpperCase()}
                      </span>
                    )}
                  </div>
                  {list.map((fx) => <FixtureRow key={fx.id} fx={fx} clubSlug={clubSlug} />)}
                </div>
              )
            })}
          </div>
        )}
      </main>
    </div>
  )
}
