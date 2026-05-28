import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'

const BASE = import.meta.env.VITE_API_URL || '/api'

// Drop a breadcrumb to /usage/event whenever the route changes.
// Anonymous-friendly (no auth required); silently ignored on failure so a
// flaky beacon never breaks a page render. Backed by /api/usage/event
// which writes a row in `usage_events` with event_type='page_view'.
//
// We debounce repeated same-path fires from React 18 strict-mode double
// effects and from query-string only changes that aren't real navigations.
export function usePageView() {
  const location = useLocation()
  const lastPath = useRef(null)
  const lastSentAt = useRef(0)

  useEffect(() => {
    const path = location.pathname + (location.search || '')
    const now = Date.now()
    // Debounce: skip duplicate same-path fires within 500ms (strict-mode).
    if (path === lastPath.current && now - lastSentAt.current < 500) return
    lastPath.current = path
    lastSentAt.current = now

    const body = JSON.stringify({
      path,
      referer: document.referrer || null,
    })

    // Prefer sendBeacon for fire-and-forget semantics (won't block page
    // navigation, won't show up in the network tab as a pending request).
    // Falls back to fetch keepalive on browsers without sendBeacon.
    try {
      if (navigator.sendBeacon) {
        const blob = new Blob([body], { type: 'application/json' })
        navigator.sendBeacon(`${BASE}/usage/event`, blob)
        return
      }
    } catch (_) {
      // fall through
    }
    try {
      fetch(`${BASE}/usage/event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        credentials: 'include',
        keepalive: true,
      }).catch(() => {})
    } catch (_) {
      // swallow
    }
  }, [location.pathname, location.search])
}
