import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { getVisitorId } from '../lib/visitor'

const BASE = import.meta.env.VITE_API_URL || '/api'
const INTERVAL_MS = 25000

// Pings /usage/heartbeat every ~25s while a public page is open AND the tab
// is actually visible (Page Visibility API) — stops the moment it's hidden,
// backgrounded, or closed. This is what lets the Usage page's "Active now"
// and the live-feed's green dot mean "someone genuinely has this page open
// right now", instead of guessing from how recently their last page_view
// landed (which stayed "on" for minutes after someone actually left).
export function useHeartbeat() {
  const location = useLocation()

  useEffect(() => {
    const path = location.pathname + (location.search || '')

    const ping = () => {
      if (document.visibilityState !== 'visible') return
      const body = JSON.stringify({ path, visitor_id: getVisitorId() })
      try {
        if (navigator.sendBeacon) {
          const blob = new Blob([body], { type: 'application/json' })
          navigator.sendBeacon(`${BASE}/usage/heartbeat`, blob)
          return
        }
      } catch (_) {
        // fall through
      }
      try {
        fetch(`${BASE}/usage/heartbeat`, {
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

    // Fire immediately (covers a tab that's been open on this page for a
    // while with no navigation), then keep pinging while visible.
    ping()
    const id = setInterval(ping, INTERVAL_MS)
    const onVisibility = () => { if (document.visibilityState === 'visible') ping() }
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [location.pathname, location.search])
}
