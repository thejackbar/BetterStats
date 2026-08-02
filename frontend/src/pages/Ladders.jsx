import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { useClubData } from '../hooks/useClubData'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import ClubPinGate from './ClubPinGate'
import LadderBoard from '../components/LadderBoard'
import SeasonSelector from '../components/SeasonSelector'
import { PageHeader, PbSpinner } from '../lib/presskit'

// Contextual links from a grade ladder to its results / leaderboard for the
// same season, plus the club-wide fixture list (which is live from the CA feed
// and so isn't season/grade scoped).
function gradeNav(slug, seasonId, gradeId, gradeName) {
  const results = new URLSearchParams()
  if (seasonId) results.set('season', seasonId)
  if (gradeId) results.set('grade', gradeId)            // Games filters by gradeId
  const lb = new URLSearchParams()
  if (seasonId) lb.set('season', seasonId)
  if (gradeName) lb.set('grade', gradeName)             // Leaderboard filters by gradeName
  const cls = 'font-mono text-[10px] px-2 py-1 rounded border pb-hairline text-pb-faint hover:text-pb-accent hover:border-pb-accent/40 transition-colors'
  return [
    <Link key="r" to={`/${slug}/games?${results}`} className={cls}>↗ Results</Link>,
    <Link key="f" to={`/${slug}/fixtures`} className={cls}>↗ Fixtures</Link>,
    <Link key="l" to={`/${slug}/leaderboard?${lb}`} className={cls}>↗ Leaderboard</Link>,
  ]
}

export default function Ladders() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  useClubTheme(club)

  const { seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade } = useClubData(orgId)

  // Default to the latest season once seasons load.
  useEffect(() => {
    if (seasons.length > 0 && selectedSeason == null) setSelectedSeason(seasons[0].id)
  }, [seasons, selectedSeason, setSelectedSeason])

  const isLatest = selectedSeason && seasons[0]?.id === selectedSeason
  const gradeName = grades.find(g => g.id === selectedGrade)?.name || null

  // Per-team board (latest season, no specific grade chosen).
  const [board, setBoard] = useState(null)
  useEffect(() => {
    if (!clubSlug || !isLatest || selectedGrade) { setBoard(null); return }
    api.laddersPublic(clubSlug).then(setBoard).catch(() => setBoard({ teams: [] }))
  }, [clubSlug, isLatest, selectedGrade])

  // Single grade ladder (any season) when a grade is picked.
  const [grade, setGrade] = useState(null)
  useEffect(() => {
    if (!selectedGrade) { setGrade(null); return }
    setGrade('loading')
    api.laddersGrade(selectedGrade).then(setGrade).catch(() => setGrade(null))
  }, [selectedGrade])

  if (locked) return <ClubPinGate slug={clubSlug} lockInfo={locked} unlock={unlock} requestAccess={requestAccess} />
  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />

  // Wrap a single grade response into the board's item shape so we reuse LadderBoard.
  const gradeAsBoard = grade && grade !== 'loading'
    ? [{ team_id: grade.grade_id, team_name: grade.grade_name, grade_name: grade.season_name, available: grade.available, views: grade.views }]
    : []

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`LADDERS · ${club?.name?.toUpperCase() || ''}`}
          title="Where we stand."
          meta={[<span key="x">Live standings — pick a season and grade to dig into the history.</span>]}
        />

        <div className="mb-5">
          <SeasonSelector
            seasons={seasons}
            grades={grades}
            selectedSeason={selectedSeason}
            setSelectedSeason={setSelectedSeason}
            selectedGrade={selectedGrade}
            setSelectedGrade={setSelectedGrade}
          />
        </div>

        {selectedGrade ? (
          // ── Single grade ladder + cross-links ──
          grade === 'loading' || grade === null ? (
            grade === 'loading' ? <PbSpinner message="Loading ladder…" /> : null
          ) : (
            <LadderBoard
              teams={gradeAsBoard}
              navFor={() => gradeNav(clubSlug, selectedSeason, selectedGrade, gradeName)}
            />
          )
        ) : isLatest ? (
          // ── Current season: our teams at a glance ──
          board === null ? <PbSpinner message="Loading ladders…" /> : (
            <LadderBoard
              teams={board.teams}
              navFor={(t) => gradeNav(clubSlug, selectedSeason, t.grade_id, t.grade_name)}
            />
          )
        ) : (
          // ── Historical season, no grade picked yet ──
          <div className="pb-card px-5 py-10 text-center text-pb-faint text-sm">
            Pick a grade above to see its ladder for this season.
          </div>
        )}
      </main>
    </div>
  )
}
