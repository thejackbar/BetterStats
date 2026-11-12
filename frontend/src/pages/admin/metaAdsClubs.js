// One list of the clubs that typed into the trial page, with the furthest stage each
// reached. The API keeps two lists (clubs SELECTED, clubs SEARCHED) because they come
// from different beacons; a person asking "who did we lose, and where" wants one, so
// this folds them on the normalised club name the server already groups by.
//
// Stages, furthest last. A selected-clubs row says how far it got in words
// (`furthest_step`); a searched-clubs row only says whether the club was ever picked.
export const STAGES = {
  searched: { rank: 1, label: 'Searched only' },
  selected: { rank: 2, label: 'Selected a club' },
  terms: { rank: 3, label: 'Reached terms' },
  completed: { rank: 4, label: 'Completed' },
}
export const STAGE_ORDER = ['completed', 'terms', 'selected', 'searched']

// The labels the server writes (meta_ads._SELECTED_STEP_LABEL). Anything else a
// selected-clubs row carries is the first step, not a guess at something further.
export function stageOfStep(furthestStep) {
  if (furthestStep === 'Registration completed') return 'completed'
  if (furthestStep === 'Reached Terms & privacy') return 'terms'
  return 'selected'
}

const later = (a, b) => (a && b ? (a > b ? a : b) : a || b || null)

// Where a club came from, as the server classifies it (meta_ads.classify_origin) from the UTMs,
// the click id and the referrer. Most specific first: when several visitors touched one club the
// first channel in this list wins, and Direct only when nothing better is known (it is where the
// evidence runs out: a typed address, a bookmark and any app that strips the referrer look alike).
export const ORIGINS = {
  email: 'Email',
  meta: 'Meta ad',
  google: 'Google',
  ai: 'AI assistant',
  social: 'Shared link',
  referral: 'Other site',
  campaign_other: 'Other campaign',
  direct: 'Direct',
  unknown: 'Unknown',
}
export const ORIGIN_ORDER = Object.keys(ORIGINS)
const betterOrigin = (a, b) => {
  if (!a) return b || null
  if (!b) return a
  return ORIGIN_ORDER.indexOf(b.channel) < ORIGIN_ORDER.indexOf(a.channel) ? b : a
}

export function mergeClubs(selected, searched) {
  const out = new Map()
  const take = (c, stage, hidden) => {
    const key = (c.key || c.name || '').trim().toLowerCase()
    if (!key) return
    let m = out.get(key)
    if (!m) {
      m = {
        key, name: (c.name || '').trim(), stage, email: null, slug: null, org_id: null,
        via_meta: false, via_campaign: false, origin: null, last_at: null, hidden: false,
      }
      out.set(key, m)
    }
    if (STAGES[stage].rank > STAGES[m.stage].rank) m.stage = stage
    m.email = m.email || c.email || null
    m.slug = m.slug || c.slug || null
    m.org_id = m.org_id || c.org_id || null
    m.via_meta = m.via_meta || !!c.via_meta
    m.via_campaign = m.via_campaign || !!c.via_campaign
    m.last_at = later(m.last_at, c.last_at)
    m.origin = betterOrigin(m.origin, c.origin)
    // Flagged as test on either list is flagged: the server keys both on the same name.
    m.hidden = m.hidden || hidden
  }
  for (const c of selected?.clubs || []) take(c, stageOfStep(c.furthest_step), false)
  for (const c of selected?.hidden_clubs || []) take(c, stageOfStep(c.furthest_step), true)
  for (const c of searched?.clubs || []) take(c, c.selected ? 'selected' : 'searched', false)
  for (const c of searched?.hidden_clubs || []) take(c, c.selected ? 'selected' : 'searched', true)
  return [...out.values()].sort((a, b) => (b.last_at || '').localeCompare(a.last_at || ''))
}

// The chips. `terms` is "reached the Terms step and has NOT finished": the clubs worth a
// call. A club that reached terms and completed is `completed`, one stage on.
export const originOf = (row) => row.origin?.channel || 'unknown'

// How many clubs each channel brought, for the filter. Only channels that occur are listed.
export function originCounts(rows) {
  const counts = {}
  for (const r of rows) counts[originOf(r)] = (counts[originOf(r)] || 0) + 1
  return counts
}

export function stageCounts(rows) {
  const counts = { all: rows.length, completed: 0, terms: 0, selected: 0, searched: 0 }
  for (const r of rows) counts[r.stage] += 1
  return counts
}

export function applyClubFilters(rows, { stage = 'all', origin = 'all', q = '' } = {}) {
  const needle = q.trim().toLowerCase()
  return rows.filter((r) => {
    if (stage !== 'all' && r.stage !== stage) return false
    if (origin !== 'all' && originOf(r) !== origin) return false
    if (needle && !r.name.toLowerCase().includes(needle)) return false
    return true
  })
}
