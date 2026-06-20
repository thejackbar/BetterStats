// Document favicon manager.
//
// Default is the BetterCricket mark — an adaptive SVG that flips white/black
// with the OS light/dark scheme (mirroring BrandLogo), with PNG fallbacks for
// older browsers and iOS home screens. On a club's white-labelled public pages
// we swap the tab icon to the club's own uploaded logo when they have one, so
// the browser tab matches the club site the visitor is on.
//
// Assets live in /public so they keep stable, cacheable URLs.

const DEFAULT_ICONS = [
  { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
  { rel: 'icon', type: 'image/png', href: '/favicon.png' },
  { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' },
]

// Track what's currently applied so repeat navigations don't churn the <head>
// (re-adding identical links can make some browsers re-fetch the icon).
let current = null // 'default' | <club logo url>

function clearIconLinks() {
  document
    .querySelectorAll('link[rel~="icon"], link[rel="apple-touch-icon"], link[rel="shortcut icon"]')
    .forEach((el) => el.remove())
}

function addIconLink({ rel, type, href }) {
  const el = document.createElement('link')
  el.rel = rel
  if (type) el.type = type
  el.href = href
  document.head.appendChild(el)
}

/** Restore the BetterCricket brand favicon (admin, marketing, anything off a club page). */
export function setDefaultFavicon() {
  if (current === 'default') return
  current = 'default'
  clearIconLinks()
  DEFAULT_ICONS.forEach(addIconLink)
}

/** Use a club's uploaded logo as the tab icon. Falls back to the brand mark when the club has none. */
export function setClubFavicon(logoUrl) {
  if (!logoUrl) return setDefaultFavicon()
  if (current === logoUrl) return
  current = logoUrl
  clearIconLinks()
  addIconLink({ rel: 'icon', href: logoUrl })
  addIconLink({ rel: 'apple-touch-icon', href: logoUrl })
}
