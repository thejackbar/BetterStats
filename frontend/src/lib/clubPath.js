// Resolve a pathname to the public club slug it belongs to, or null when it
// isn't a club page. Shared by FaviconManager (the tab icon) and ClubCTABar
// (the prospect call to action), so the two cannot disagree about what counts
// as a club's public site.

// Second path segment for the white-labelled club surface (keep in sync with
// the /:clubSlug/* routes in App.jsx).
const CLUB_SECTIONS = new Set([
  'players', 'compare', 'leaderboard', 'records', 'premierships', 'honour-board',
  'ladders', 'statlab', 'competitions', 'games', 'fixtures', 'lineups',
  'yearbook', 'website',
])

// Single-segment paths that are NOT club slugs (marketing + app routes).
const RESERVED_ROOTS = new Set([
  'login', 'admin', 'onboard', 'club-inactive', 'avail', 'games', 'players',
  'overview', 'features', 'pricing', 'compare', 'modules', 'about', 'contact',
  'faq', 'terms', 'privacy', 'blog', 'videos', 'betterscout', 'trial', 'demo',
])

export function publicClubSlug(pathname) {
  const seg = (pathname || '').split('/').filter(Boolean)
  if (seg.length === 0) return null
  if (seg.length === 1) return RESERVED_ROOTS.has(seg[0]) ? null : seg[0]
  return CLUB_SECTIONS.has(seg[1]) && !RESERVED_ROOTS.has(seg[0]) ? seg[0] : null
}
