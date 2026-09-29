import { useMemo } from 'react'
import { Outlet, useParams } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import LoadingSpinner from '../components/LoadingSpinner'
import AflNavbar from './components/AflNavbar'
import ClubPinGate from '../pages/ClubPinGate'
import { rebaseApiUrl } from '../lib/api'
import { mediaUrl } from './aflApi'

/**
 * Resolves /:clubSlug, applies the club's white-label theme, renders the AFL
 * navbar and provides { club } to child routes via Outlet context.
 */
export default function ClubLayout() {
  const { clubSlug } = useParams()
  const { club: raw, loading, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  // Uploaded font URLs come back in cricket's "/api/images/..." shape; under
  // the /afl app that path belongs to the cricket backend, so re-root them.
  const club = useMemo(() => raw && {
    ...raw,
    font_display_url: rebaseApiUrl(raw.font_display_url),
    font_body_url: rebaseApiUrl(raw.font_body_url),
    font_mono_url: rebaseApiUrl(raw.font_mono_url),
  }, [raw])
  useClubTheme(club)

  if (loading) return <div className="pt-24 flex justify-center"><LoadingSpinner /></div>
  if (locked) {
    return <ClubPinGate slug={clubSlug} unlock={unlock} requestAccess={requestAccess}
      lockInfo={{ ...locked, logo_url: locked.logo_url ? mediaUrl(locked.logo_url) : null }} />
  }
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
