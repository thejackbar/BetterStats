// Keeps the browser tab icon in step with where the visitor is:
//   - club public pages (/{slug}, /{slug}/players, /{slug}/website, …) → the
//     club's uploaded logo when they have one, else the BetterCricket mark
//   - everything else (marketing, admin, login, global game/player routes) →
//     the BetterCricket mark
// Mounted once at the App root; it renders nothing.
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../lib/api'
import { setClubFavicon, setDefaultFavicon } from '../lib/favicon'

// Second path segment for the white-labelled club surface (keep in sync with the
// /:clubSlug/* routes in App.jsx).
const CLUB_SECTIONS = new Set([
  'players', 'compare', 'leaderboard', 'records', 'ladders',
  'statlab', 'games', 'yearbook', 'website',
])
// Single-segment paths that are NOT club slugs (marketing + app routes).
const RESERVED_ROOTS = new Set([
  'login', 'admin', 'onboard', 'club-inactive', 'avail', 'games', 'players',
  'overview', 'features', 'pricing', 'compare', 'modules', 'about', 'contact',
  'faq', 'terms', 'privacy', 'blog',
])

// Resolve a pathname to a public club slug, or null when it isn't a club page.
function publicClubSlug(pathname) {
  const seg = pathname.split('/').filter(Boolean)
  if (seg.length === 0) return null
  if (seg.length === 1) return RESERVED_ROOTS.has(seg[0]) ? null : seg[0]
  return CLUB_SECTIONS.has(seg[1]) && !RESERVED_ROOTS.has(seg[0]) ? seg[0] : null
}

export default function FaviconManager() {
  const { pathname } = useLocation()
  const slug = publicClubSlug(pathname)
  const [logoUrl, setLogoUrl] = useState(null)

  // Look up the club's logo when we land on its pages. Keyed on slug, so moving
  // between a club's pages (dashboard → players → …) doesn't refetch.
  useEffect(() => {
    if (!slug) { setLogoUrl(null); return }
    let cancelled = false
    api.getClubBySlug(slug)
      .then((c) => { if (!cancelled) setLogoUrl(c?.logo_url || null) })
      .catch(() => { if (!cancelled) setLogoUrl(null) })
    return () => { cancelled = true }
  }, [slug])

  useEffect(() => {
    if (slug && logoUrl) setClubFavicon(logoUrl)
    else setDefaultFavicon()
  }, [slug, logoUrl])

  return null
}
