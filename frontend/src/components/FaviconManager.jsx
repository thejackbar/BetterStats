// Keeps the browser tab icon (and the home-screen manifest) in step with where the visitor is:
//   - club public pages (/{slug}, /{slug}/players, /{slug}/website, …) → the
//     club's uploaded logo when they have one, else the BetterCricket mark
//   - everything else (marketing, admin, login, global game/player routes) →
//     the BetterCricket mark
// Mounted once at the App root; it renders nothing.
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../lib/api'
import { setClubFavicon, setDefaultFavicon, setManifest } from '../lib/favicon'
import { publicClubSlug } from '../lib/clubPath'

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

  // The manifest follows the slug alone, so it is right even before the club
  // lookup returns or when the club has no logo.
  useEffect(() => { setManifest(slug) }, [slug])

  useEffect(() => {
    if (slug && logoUrl) setClubFavicon(logoUrl)
    else setDefaultFavicon()
  }, [slug, logoUrl])

  return null
}
