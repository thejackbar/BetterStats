import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import LadderBoard from '../components/LadderBoard'
import { PageHeader, PbSpinner } from '../lib/presskit'

export default function Ladders() {
  const { clubSlug } = useParams()
  const { club, inactive } = useClub(clubSlug)
  useClubTheme(club)

  const [data, setData] = useState(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!clubSlug) return
    setData(null); setError(false)
    api.laddersPublic(clubSlug)
      .then(setData)
      .catch(() => { setError(true); setData({ teams: [] }) })
  }, [clubSlug])

  if (inactive) return <ClubInactive />

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`LADDERS · ${club?.name?.toUpperCase() || ''}`}
          title="Where we stand."
          meta={[<span key="x">Live grade standings for every team.</span>]}
        />
        {data === null ? (
          <PbSpinner message="Loading ladders…" />
        ) : error ? (
          <div className="pb-card px-5 py-10 text-center text-pb-faint text-sm">Couldn’t load ladders right now.</div>
        ) : (
          <LadderBoard teams={data.teams} />
        )}
      </main>
    </div>
  )
}
