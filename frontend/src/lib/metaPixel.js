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

// Meta's documented _fbc shape, built from the URL click id for the case where
// the pixel hasn't set the _fbc cookie yet (e.g. this is the very first
// pageview and the click just landed).
export function buildFbcFromFbclid() {
  try {
    const fbclid = new URLSearchParams(window.location.search).get('fbclid')
    return fbclid ? `fb.1.${Date.now()}.${fbclid}` : null
  } catch {
    return null
  }
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
