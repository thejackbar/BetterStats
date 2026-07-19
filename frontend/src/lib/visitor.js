// First-party visitor identity + acquisition attribution.
//
// We give every browser a random UUID kept in localStorage (`bs_visitor_id`).
// Unlike the hashed IP the backend already records, this survives an IP change
// and a new session, so returning visitors group correctly on the Usage page.
// It is NOT a tracking pixel and carries no personal data — just a random id so
// "the same browser" can be recognised across visits.
//
// We also remember each visitor's FIRST-TOUCH acquisition (`bs_attr`): the UTM
// tags and ad-network click id (fbclid → Facebook, gclid → Google …) from the
// URL they first arrived on. That's how the Usage page knows a visit came from
// a Facebook share or a club's outreach link even after they browse on.

const VISITOR_KEY = 'bs_visitor_id'
const ATTR_KEY = 'bs_attr'
const LINK_CODE_KEY = 'bs_link_code'

function uuid() {
  try {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  } catch (_) { /* fall through */ }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export function getVisitorId() {
  try {
    let v = localStorage.getItem(VISITOR_KEY)
    if (!v) {
      v = uuid()
      localStorage.setItem(VISITOR_KEY, v)
    }
    return v
  } catch (_) {
    // Private mode / storage blocked — fall back to anonymous (IP-hash only).
    return null
  }
}

// Known ad-network click-id params → the source they imply. Checked in order;
// the first present wins.
const CLICK_IDS = [
  ['fbclid', 'facebook'],
  ['gclid', 'google'], ['gbraid', 'google'], ['wbraid', 'google'],
  ['msclkid', 'bing'],
  ['ttclid', 'tiktok'],
  ['igshid', 'instagram'],
  ['li_fat_id', 'linkedin'],
  ['twclid', 'twitter'],
  ['yclid', 'yandex'],
]

function parseAcquisition() {
  let params
  try {
    params = new URLSearchParams(window.location.search || '')
  } catch (_) {
    params = new URLSearchParams('')
  }
  const get = (k) => {
    const v = params.get(k)
    return v ? v.slice(0, 200) : null
  }
  let clickId = null
  let clickSource = null
  for (const [key, source] of CLICK_IDS) {
    const v = params.get(key)
    if (v) {
      clickId = v.slice(0, 300)
      clickSource = source
      break
    }
  }
  const utmSource = get('utm_source')
  return {
    utm_source: utmSource,
    utm_medium: get('utm_medium'),
    utm_campaign: get('utm_campaign'),
    utm_content: get('utm_content'),
    click_id: clickId,
    click_source: clickSource,
    has_signal: !!(utmSource || clickId),
  }
}

// The per-club outreach code (utm_id) from a BetterCricket email link, captured
// for the rest of the browser session. A marketing email tags its links with the
// recipient club's utm_code as ?utm_id=…; we remember it so every page the
// visitor then browses (not just the one they landed on) is attributable to that
// club. Session-scoped on purpose: a later organic visit shouldn't inherit it.
export function getLinkCode() {
  let current = null
  try {
    current = new URLSearchParams(window.location.search || '').get('utm_id')
  } catch (_) { /* ignore */ }
  if (current) current = current.slice(0, 200)
  try {
    if (current) {
      sessionStorage.setItem(LINK_CODE_KEY, current)
      return current
    }
    return sessionStorage.getItem(LINK_CODE_KEY) || null
  } catch (_) {
    return current
  }
}

// Raw UTM params straight off the CURRENT URL — no first-touch stickiness.
// Used alongside getAttribution() so a returning visitor's page-view beacon
// still carries THIS click's own utm_campaign (e.g. a club outreach link's
// ?utm_id=CODE&utm_campaign=NAME) instead of whatever campaign their first
// ever visit happened to carry. Without this, a visitor who first arrived
// organically (or from an older campaign) and later clicks a NEW campaigned
// link would have that new visit's utm_id recorded (session-scoped, always
// fresh) but its utm_campaign silently dropped back to the stale first-touch
// value — so "which campaign does this utm_code visit belong to" couldn't be
// answered for anyone but a brand-new visitor.
export function getCurrentUtm() {
  return parseAcquisition()
}

// Returns the visitor's first-touch attribution, capturing it on the first
// visit. If that first visit carried no source (a plain direct hit) and a later
// visit arrives via a real campaign/share, we upgrade it once to that source —
// the acquisition that actually mattered for a lead.
export function getAttribution() {
  let stored = null
  try {
    stored = JSON.parse(localStorage.getItem(ATTR_KEY) || 'null')
  } catch (_) { /* ignore */ }

  const current = parseAcquisition()
  const landing = {
    landing_path: (window.location.pathname || '/') + (window.location.search || ''),
    landing_referrer: (typeof document !== 'undefined' && document.referrer) || null,
  }

  let next = stored
  if (!stored) {
    next = { ...current, ...landing }
  } else if (!stored.has_signal && current.has_signal) {
    next = { ...current, ...landing }
  }

  if (next !== stored) {
    try {
      localStorage.setItem(ATTR_KEY, JSON.stringify(next))
    } catch (_) { /* ignore */ }
  }
  return next || { has_signal: false, ...landing }
}

// Called on login so a staff member's admin browsing can't keep inheriting
// whatever marketing UTM happened to be sitting in this tab (e.g. from
// testing/copying a club's own outreach link) — the backend now also guards
// against this (usage_events with a user_id are excluded from UTM
// attribution), but clearing it here stops a stale value being sent at all.
// bs_visitor_id is untouched — that's a stable anonymous-browser id, not
// attribution, and losing it would just fragment the same visitor's history.
export function clearAttribution() {
  try {
    sessionStorage.removeItem(LINK_CODE_KEY)
    localStorage.removeItem(ATTR_KEY)
  } catch (_) { /* ignore */ }
}
