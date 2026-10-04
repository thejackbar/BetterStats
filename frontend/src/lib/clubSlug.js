// The club a page belongs to when its URL does not say so. Player profiles and
// scorecards live at /players/:id and /games/:id with no club slug in the path,
// so the page that loaded the player or game tells the rest of the app which
// club it is, and the sponsor list at the bottom follows.
const KEY = 'bs_last_slug'
const EVENT = 'bs-club-slug'

export function rememberClubSlug(slug) {
  if (!slug) return
  try {
    if (sessionStorage.getItem(KEY) !== slug) sessionStorage.setItem(KEY, slug)
  } catch { /* storage can be blocked; the event below still tells this tab */ }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: slug }))
}

export function readClubSlug() {
  try { return sessionStorage.getItem(KEY) || null } catch { return null }
}

export function onClubSlugChange(fn) {
  const handler = (e) => fn(e.detail)
  window.addEventListener(EVENT, handler)
  return () => window.removeEventListener(EVENT, handler)
}
