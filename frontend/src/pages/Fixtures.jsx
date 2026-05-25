import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useMemo } from 'react'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { usePageMeta } from '../hooks/usePageMeta'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import { Card, PageHeader, PbSpinner, Label } from '../lib/presskit'

function formatDate(dateStr) {
  if (!dateStr) return '—'
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-AU', {
    weekday: 'short', day: 'numeric', month: 'short',
  })
}

function formatTime(timeStr) {
  if (!timeStr) return null
  const [h, m] = timeStr.split(':')
  const hour = parseInt(h, 10)
  const ampm = hour >= 12 ? 'pm' : 'am'
  const h12 = hour > 12 ? hour - 12 : hour === 0 ? 12 : hour
  return `${h12}:${m}${ampm}`
}

function FixtureRow({ fixture, i }) {
  const roundLabel = fixture.round != null ? `Rd ${fixture.round}` : null
  const meta = [fixture.grade, roundLabel].filter(Boolean).join(' · ')
  const time = formatTime(fixture.time)

  return (
    <div className={`flex items-start gap-4 py-3 px-4 ${i ? 'pb-hairline-t' : ''}`}>
      {/* Date / Time */}
      <div className="w-28 shrink-0 pt-0.5">
        <div className="font-mono text-[12px] text-pb-dim">{formatDate(fixture.date)}</div>
        {time && <div className="font-mono text-[11px] text-pb-faint mt-0.5">{time}</div>}
      </div>

      {/* Teams + meta */}
      <div className="flex-1 min-w-0">
        <div className="text-pb-text text-[14px] font-semibold truncate">
          {fixture.home_team || '—'} <span className="text-pb-dim font-normal text-[12px]">v</span> {fixture.away_team || '—'}
        </div>
        {meta && (
          <div className="font-mono text-pb-faint text-[10.5px] tracking-wide2 mt-0.5">{meta}</div>
        )}
        {fixture.venue && (
          <div className="font-mono text-pb-faint text-[10.5px] tracking-wide2 mt-0.5 truncate">{fixture.venue}</div>
        )}
      </div>

      {/* Scorecard link */}
      {fixture.id && (
        <Link
          to={`/scorecards/${fixture.id}`}
          className="shrink-0 self-center font-mono text-[10px] tracking-wide2 px-2.5 py-1.5 rounded border border-pb-hairline text-pb-dim hover:text-pb-accent hover:border-pb-accent transition"
        >
          SCORECARD →
        </Link>
      )}
    </div>
  )
}

export default function Fixtures() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  useClubTheme(club)
  usePageMeta({
    title: club?.name ? `${club.name} Fixtures — BetterStats` : null,
    description: club?.name ? `Upcoming fixtures for ${club.name}.` : null,
    image: club?.logo_url || null,
  })

  const [fixtures, setFixtures] = useState([])
  const [loading, setLoading] = useState(true)
  const [gradeFilter, setGradeFilter] = useState('')
  const [teamFilter, setTeamFilter] = useState('')

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    api.getOrgFixtures(orgId)
      .then(setFixtures)
      .catch(() => setFixtures([]))
      .finally(() => setLoading(false))
  }, [orgId])

  const grades = useMemo(() => {
    const seen = new Set()
    return fixtures.map(f => f.grade).filter(g => g && !seen.has(g) && seen.add(g))
  }, [fixtures])

  const teams = useMemo(() => {
    const seen = new Set()
    const all = []
    for (const f of fixtures) {
      if (f.home_team && !seen.has(f.home_team)) { seen.add(f.home_team); all.push(f.home_team) }
      if (f.away_team && !seen.has(f.away_team)) { seen.add(f.away_team); all.push(f.away_team) }
    }
    return all.sort()
  }, [fixtures])

  const filtered = useMemo(() => fixtures.filter(f => {
    if (gradeFilter && f.grade !== gradeFilter) return false
    if (teamFilter && f.home_team !== teamFilter && f.away_team !== teamFilter) return false
    return true
  }), [fixtures, gradeFilter, teamFilter])

  if (inactive) return <ClubInactive />

  const selectCls = "font-mono text-[11px] tracking-wide2 px-3 py-2 rounded border border-pb-hairline bg-pb-surface text-pb-dim hover:border-pb-accent focus:outline-none focus:border-pb-accent cursor-pointer transition"

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1300px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow="UPCOMING MATCHES"
          title="Fixtures."
          meta={[
            !loading && <span key="c">{filtered.length} upcoming</span>,
          ].filter(Boolean)}
        />

        {/* Filters */}
        {!loading && fixtures.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 mb-5">
            <select value={gradeFilter} onChange={e => setGradeFilter(e.target.value)} className={selectCls}>
              <option value="">All Grades</option>
              {grades.map(g => <option key={g} value={g}>{g}</option>)}
            </select>
            <select value={teamFilter} onChange={e => setTeamFilter(e.target.value)} className={selectCls}>
              <option value="">All Teams</option>
              {teams.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            {(gradeFilter || teamFilter) && (
              <button
                onClick={() => { setGradeFilter(''); setTeamFilter('') }}
                className="font-mono text-[11px] tracking-wide2 px-3 py-2 rounded border border-pb-hairline text-pb-dim hover:text-pb-text transition"
              >
                Clear
              </button>
            )}
          </div>
        )}

        {loading ? (
          <PbSpinner />
        ) : filtered.length === 0 ? (
          <p className="text-pb-faint text-sm py-8 text-center">
            {fixtures.length === 0
              ? 'No upcoming fixtures found.'
              : 'No fixtures match the current filter.'}
          </p>
        ) : (
          <Card pad="p-0">
            {filtered.map((f, i) => <FixtureRow key={f.id || i} fixture={f} i={i} />)}
          </Card>
        )}

        {!loading && (
          <p className="font-mono text-[10px] tracking-wide2 text-pb-faintest text-center mt-6">
            Fixtures sourced from PlayHQ · recent seasons only
          </p>
        )}
      </main>
    </div>
  )
}
