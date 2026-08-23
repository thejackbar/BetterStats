import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { usePageMeta } from '../hooks/usePageMeta'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import ClubPinGate from './ClubPinGate'
import { PageHeader, PbSpinner } from '../lib/presskit'
import { formatSeason } from '../lib/cricketFormat'

export default function Teams() {
  const { clubSlug } = useParams()
  const { club, loading: clubLoading, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  const orgId = club?.id

  const [seasons, setSeasons] = useState([])
  const [selectedSeason, setSelectedSeason] = useState(null)
  const [grades, setGrades] = useState([])
  const [loadingSeasons, setLoadingSeasons] = useState(true)
  const [loadingGrades, setLoadingGrades] = useState(false)

  useClubTheme(club)
  usePageMeta({ title: `Teams, ${club?.name || clubSlug}` })

  useEffect(() => {
    if (!orgId) return
    api.getOrgSeasons(orgId)
      .then(data => {
        setSeasons(data)
        if (data.length > 0) setSelectedSeason(data[0].id)
      })
      .catch(() => {})
      .finally(() => setLoadingSeasons(false))
  }, [orgId])

  useEffect(() => {
    if (!orgId || !selectedSeason) return
    setLoadingGrades(true)
    api.getSeasonGrades(orgId, selectedSeason)
      .then(setGrades)
      .catch(() => setGrades([]))
      .finally(() => setLoadingGrades(false))
  }, [orgId, selectedSeason])

  if (clubLoading) return <PbSpinner />
  if (locked) return <ClubPinGate slug={clubSlug} lockInfo={locked} unlock={unlock} requestAccess={requestAccess} />
  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />

  const selectedSeasonObj = seasons.find(s => s.id === selectedSeason)

  return (
    <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        eyebrow={club?.name}
        title="Teams"
      />

      {/* Season filter */}
      {seasons.length > 0 && (
        <div className="flex items-center gap-2 mb-8">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap">Season</label>
          <select
            value={selectedSeason || ''}
            onChange={e => setSelectedSeason(e.target.value || null)}
            className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
          >
            {seasons.map(s => (
              <option key={s.id} value={s.id}>{formatSeason(s)}</option>
            ))}
          </select>
        </div>
      )}

      {loadingSeasons || loadingGrades ? (
        <PbSpinner />
      ) : grades.length === 0 ? (
        <p className="text-pb-faint font-mono text-[13px]">No teams found for this season.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {grades.map(grade => (
            <Link
              key={grade.id}
              to={`/${clubSlug}/teams/${grade.id}`}
              className="block bg-pb-surface border pb-hairline rounded-lg p-5 hover:bg-pb-surface2 hover:border-pb-accent transition group"
            >
              <div className="text-pb-text font-semibold text-[17px] group-hover:text-pb-accent transition leading-tight mb-1">
                {grade.name}
              </div>
              <div className="text-pb-faint font-mono text-[10px] tracking-wide2 uppercase mb-4">
                {selectedSeasonObj?.name || ''}
              </div>
              <div className="flex items-center justify-between">
                <span className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">View stats</span>
                <span className="text-pb-faint group-hover:text-pb-accent transition text-[13px]">→</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
