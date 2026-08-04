import { Outlet, useParams } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import LoadingSpinner from '../components/LoadingSpinner'
import AflNavbar from './components/AflNavbar'

/**
 * Resolves /:clubSlug, applies the club's white-label theme, renders the AFL
 * navbar and provides { club } to child routes via Outlet context.
 */
export default function ClubLayout() {
  const { clubSlug } = useParams()
  const { club, loading, inactive, notFound } = useClub(clubSlug)
  useClubTheme(club)

  if (loading) return <div className="pt-24 flex justify-center"><LoadingSpinner /></div>
  if (inactive) {
    return (
      <div className="pt-24 text-center text-pb-dim">
        <h1 className="text-2xl font-bold text-pb-text mb-2">This club page isn't active</h1>
        <p>Check back soon.</p>
      </div>
    )
  }
  if (notFound || !club) {
    return (
      <div className="pt-24 text-center text-pb-dim">
        <h1 className="text-2xl font-bold text-pb-text mb-2">Club not found</h1>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <AflNavbar club={club} />
      <main className="max-w-6xl mx-auto px-4 py-6">
        <Outlet context={{ club }} />
      </main>
      <footer className="max-w-6xl mx-auto px-4 py-8 text-center text-xs text-pb-faintest">
        Powered by BetterFootball
      </footer>
    </div>
  )
}
