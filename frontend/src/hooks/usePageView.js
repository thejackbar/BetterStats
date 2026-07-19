import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { getVisitorId, getAttribution, getLinkCode, getCurrentUtm } from '../lib/visitor'

const BASE = import.meta.env.VITE_API_URL || '/api'

// Below this many ms an "exit" isn't worth recording — strict-mode double
// effects and near-instant redirects would otherwise write noise rows.
const MIN_DWELL_MS = 250
// Above this, treat it as a stuck timer (laptop asleep, tab backgrounded for
// hours) rather than genuine time-on-page — caps the outlier so it can't
// blow out an average. Matches the server-side clamp in usage_tracker.py.
const MAX_DWELL_MS = 24 * 60 * 60 * 1000

function send(path, body) {
  // Prefer sendBeacon for fire-and-forget semantics (won't block page
  // navigation/unload, won't show up in the network tab as a pending
  // request). Falls back to fetch keepalive on browsers without sendBeacon.
  try {
    if (navigator.sendBeacon) {
      const blob = new Blob([body], { type: 'application/json' })
      navigator.sendBeacon(`${BASE}${path}`, blob)
      return
    }
  } catch (_) {
    // fall through
  }
  try {
    fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      credentials: 'include',
      keepalive: true,
    }).catch(() => {})
  } catch (_) {
    // swallow
  }
}

// Drop a breadcrumb to /usage/event whenever the route changes, and a second
// breadcrumb to /usage/event/exit recording how long the visitor stayed on
// the PREVIOUS page — captured on navigation-away, tab-hide and unload/close
// (visibilitychange + pagehide), since a plain unload handler alone is
// unreliable on mobile browsers. Anonymous-friendly (no auth required);
// silently ignored on failure so a flaky beacon never breaks a page render.
//
// We debounce repeated same-path fires from React 18 strict-mode double
// effects and from query-string only changes that aren't real navigations.
export function usePageView() {
  const location = useLocation()
  const lastPath = useRef(null)
  const lastSentAt = useRef(0)
  // The page currently "open" for dwell-time purposes, and when it opened.
  // Read/written by both the route-change effect and the mount-once
  // visibility/unload listeners below, so they're refs (not state) — no
  // re-render should ever follow from a beacon firing.
  const activePath = useRef(null)
  const enteredAt = useRef(0)

  const sendExit = (path, elapsedMs) => {
    if (!path || elapsedMs < MIN_DWELL_MS) return
    const ms = Math.min(elapsedMs, MAX_DWELL_MS)
    send('/usage/event/exit', JSON.stringify({
      path,
      time_on_page_ms: Math.round(ms),
      visitor_id: getVisitorId(),
    }))
  }

  useEffect(() => {
    const path = location.pathname + (location.search || '')
    const now = Date.now()
    // Debounce: skip duplicate same-path fires within 500ms (strict-mode).
    if (path === lastPath.current && now - lastSentAt.current < 500) return
    lastPath.current = path
    lastSentAt.current = now

    // Close out the previous page's dwell time before opening the new one.
    if (activePath.current && activePath.current !== path) {
      sendExit(activePath.current, now - enteredAt.current)
    }
    activePath.current = path
    enteredAt.current = now

    // Stable visitor id + first-touch acquisition (UTMs / ad-click ids) so the
    // Usage page can recognise returning visitors and tell where they came from.
    const attr = getAttribution()
    // THIS click's own UTM params (not sticky) win over the first-touch
    // snapshot whenever the current URL actually carries them — so a visit
    // tagged with a club's utm_id also carries ITS OWN utm_campaign, even for
    // a returning visitor whose stored first-touch attribution is older/blank.
    const cur = getCurrentUtm()
    const body = JSON.stringify({
      path,
      referer: document.referrer || null,
      visitor_id: getVisitorId(),
      utm_source: cur.utm_source || attr.utm_source || null,
      utm_medium: cur.utm_medium || attr.utm_medium || null,
      utm_campaign: cur.utm_campaign || attr.utm_campaign || null,
      utm_content: cur.utm_content || attr.utm_content || null,
      utm_id: getLinkCode(),
      click_id: cur.click_id || attr.click_id || null,
      click_source: cur.click_source || attr.click_source || null,
      landing_referrer: attr.landing_referrer || null,
      landing_path: attr.landing_path || null,
    })
    send('/usage/event', body)
  }, [location.pathname, location.search])

  // Mount-once: catch the dwell time on the LAST page — a route-change
  // effect can only close out a PREVIOUS page, never the final one before the
  // tab is hidden/closed. `pagehide` covers navigation away / tab close;
  // `visibilitychange` also covers a mobile browser backgrounding the tab
  // without ever firing pagehide. Resetting enteredAt after each send means
  // coming back to the tab and leaving again later reports only the new
  // increment, not a re-count of time already sent.
  useEffect(() => {
    const flush = () => {
      const now = Date.now()
      sendExit(activePath.current, now - enteredAt.current)
      enteredAt.current = now
    }
    const onVisibility = () => { if (document.visibilityState === 'hidden') flush() }
    window.addEventListener('pagehide', flush)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('pagehide', flush)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])
}
