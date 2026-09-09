// Public BetterCricket marketing routes — separate module so both App.jsx
// (nav suppression, CTA bar) and ThemeContext (forced dark mode) can read it
// without an App <-> contexts circular import.
export const MARKETING_PATHS = ['/', '/overview', '/features', '/pricing', '/compare', '/modules', '/about', '/contact', '/faq', '/terms', '/privacy', '/blog', '/videos']

export function isMarketingPath(pathname) {
  return MARKETING_PATHS.includes(pathname)
    || pathname.startsWith('/blog/')
    || pathname.startsWith('/videos/')
    || pathname.startsWith('/modules/')
}

// Marketing pages that render their OWN MarketingNav but are deliberately NOT
// in MARKETING_PATHS above.
//
// THE TWO LISTS ARE NOT INTERCHANGEABLE, and that is the whole reason this one
// exists. MARKETING_PATHS carries three behaviours at once — suppress the club
// Navbar, force the dark marketing theme, and show ClubCTABar's "get your club
// on BetterCricket" bar. /trial and /demo want only the first: each forces
// LIGHT with its own `data-theme` wrapper, and each IS a conversion page with
// its own call to action, so a second competing CTA bar across the bottom is
// exactly the friction they are built to avoid.
//
// Without this they were resolving as club slugs, so the club Navbar drew ON
// TOP of their own MarketingNav — two lockups overlapping at y=0, which reads
// as "iiB Be…Cricket". The trap this repo already records for /videos: a new
// top-level route is a club slug until FOUR separate lists say otherwise
// (og_preview.RESERVED_ROOT_SEGMENTS, FaviconManager.RESERVED_ROOTS,
// SponsorFooter.RESERVED_ROOT_SEGMENTS, and here). /trial and /demo were added
// to three of the four; this was the one that got missed.
export const OWN_NAV_PATHS = ['/trial', '/demo']

export function rendersOwnMarketingNav(pathname) {
  return OWN_NAV_PATHS.includes(pathname)
}
