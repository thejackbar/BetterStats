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

export function mergeClubs(selected, searched) {
  const out = new Map()
  const take = (c, stage, hidden) => {
    const key = (c.key || c.name || '').trim().toLowerCase()
    if (!key) return
    let m = out.get(key)
    if (!m) {
      m = {
        key, name: (c.name || '').trim(), stage, email: null, slug: null, org_id: null,
        via_meta: false, via_campaign: false, queries: [], searches: 0, visitors: 0,
        last_at: null, hidden: false,
      }
      out.set(key, m)
    }
    if (STAGES[stage].rank > STAGES[m.stage].rank) m.stage = stage
    m.email = m.email || c.email || null
    m.slug = m.slug || c.slug || null
    m.org_id = m.org_id || c.org_id || null
    m.via_meta = m.via_meta || !!c.via_meta
    m.via_campaign = m.via_campaign || !!c.via_campaign
    for (const q of c.queries || []) if (q && !m.queries.includes(q)) m.queries.push(q)
    m.searches = Math.max(m.searches, c.searches || 0)
    m.visitors = Math.max(m.visitors, c.visitors || 0)
    m.last_at = later(m.last_at, c.last_at)
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
export function stageCounts(rows) {
  const counts = { all: rows.length, completed: 0, terms: 0, selected: 0, searched: 0 }
  for (const r of rows) counts[r.stage] += 1
  return counts
}

export function applyClubFilters(rows, { stage = 'all', source = 'all', q = '' } = {}) {
  const needle = q.trim().toLowerCase()
  return rows.filter((r) => {
    if (stage !== 'all' && r.stage !== stage) return false
    if (source === 'meta' && !r.via_meta) return false
    if (needle && !r.name.toLowerCase().includes(needle)) return false
    return true
  })
}
