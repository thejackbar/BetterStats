import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { getVisitorId, getAttribution } from '../lib/visitor'

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

    // Stable visitor id + first-touch acquisition (UTMs / ad-click ids) so the
    // Usage page can recognise returning visitors and tell where they came from.
    const attr = getAttribution()
    const body = JSON.stringify({
      path,
      referer: document.referrer || null,
      visitor_id: getVisitorId(),
      utm_source: attr.utm_source || null,
      utm_medium: attr.utm_medium || null,
      utm_campaign: attr.utm_campaign || null,
      utm_content: attr.utm_content || null,
      click_id: attr.click_id || null,
      click_source: attr.click_source || null,
      landing_referrer: attr.landing_referrer || null,
      landing_path: attr.landing_path || null,
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
