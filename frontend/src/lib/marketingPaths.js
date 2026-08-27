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
