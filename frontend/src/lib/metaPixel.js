import { getLandingParams } from './visitor'

// Meta Pixel <-> Conversions API dedup helpers.
//
// The browser pixel and the backend's server-side Conversions API call both
// report the same logical event (e.g. a Lead). Meta only counts it once if
// both copies carry the SAME event_name + event_id, so every place that fires
// `fbq('track', 'Lead', ...)` generates one event_id, passes it to fbq's
// eventID option, and sends it to the backend so the server copy matches.

export function newEventId() {
  try {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  } catch { /* ignore */ }
  return `${Date.now()}.${Math.random().toString(16).slice(2)}`
}

export function getCookie(name) {
  try {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
    return match ? decodeURIComponent(match[1]) : null
  } catch {
    return null
  }
}

// Meta's documented _fbc shape, built from the click id for the case where
// the pixel hasn't set the _fbc cookie (blocked, or not loaded yet). The URL
// is checked first; after a client-side hop (ad -> /trial -> a club's page)
// the fbclid has left the address bar, so the one remembered for this session
// is used instead, stamped with the time of the click rather than now.
export function buildFbcFromFbclid() {
  try {
    const fbclid = new URLSearchParams(window.location.search).get('fbclid')
    if (fbclid) return `fb.1.${Date.now()}.${fbclid}`
  } catch { /* fall through */ }
  const landing = getLandingParams()
  if (landing?.fbclid) return `fb.1.${landing.captured_at || Date.now()}.${landing.fbclid}`
  return null
}

// The dedup + match-quality context to send alongside a Lead: an event_id for
// the browser/server pair, plus fbp/fbc so both sides match on the same visitor.
export function getMetaEventContext() {
  return {
    eventId: newEventId(),
    eventSourceUrl: typeof window !== 'undefined' ? window.location.href : '',
    fbp: getCookie('_fbp'),
    fbc: getCookie('_fbc') || buildFbcFromFbclid(),
  }
}
