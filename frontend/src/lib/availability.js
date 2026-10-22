// Single source of truth for availability-status presentation.
//
// Both the Availability matrix (chip glyph + cell colour) and the Selection
// board (status dot + sort rank) render the same four statuses. Keeping the
// colour/label/rank identity here stops the two screens from drifting apart.

export const AVAIL_STATUSES = ['AVAILABLE', 'UNAVAILABLE', 'MAYBE', 'NO_RESPONSE']

// Each status carries: `label` (full), `short` (compact, e.g. button copy),
// `glyph` (cell symbol), `chip`/`dot` (Tailwind class strings for legacy
// consumers), `cssVar` (a CSS custom-property string for inline styling so the
// BetterSelect atom kit can colour dots/bars without dynamic Tailwind classes
// the JIT can't see), and `rank` (sort order — available first).
export const AVAILABILITY = {
  AVAILABLE: {
    label: 'Available',
    short: 'Available',
    glyph: '✓',
    // Semantic green — uses --pb-positive (fixed), NOT --pb-accent (the club's
    // white-label colour). "Available = green" must never re-colour per club;
    // applyClubTheme only overrides --pb-accent. Same for amber/red below.
    chip: 'bg-pb-positive/20 text-pb-positive border-pb-positive/40',
    dot: 'bg-pb-positive',
    cssVar: 'var(--pb-positive)',
    rank: 0,
  },
  UNAVAILABLE: {
    label: 'Unavailable',
    short: 'Unavailable',
    glyph: '✕',
    chip: 'bg-pb-red/20 text-pb-red border-pb-red/40',
    dot: 'bg-pb-red',
    cssVar: 'var(--pb-red)',
    rank: 3,
  },
  MAYBE: {
    label: 'Maybe',
    short: 'Maybe',
    glyph: '?',
    chip: 'bg-pb-amber/20 text-pb-amber border-pb-amber/40',
    dot: 'bg-pb-amber',
    cssVar: 'var(--pb-amber)',
    rank: 1,
  },
  NO_RESPONSE: {
    label: 'No response',
    short: 'No response',
    glyph: '–',
    chip: 'bg-pb-surface2 text-pb-faintest border-pb-hairline',
    dot: 'bg-pb-faintest',
    cssVar: 'var(--pb-faintest)',
    rank: 2,
  },
}

// "Half available": a two-day game is answered one weekend at a time, and a
// player can be free for one and away for the other. These are not answers (they
// are never stored or sent); they are how a card DRAWS that case, in a colour the
// club picks in BetterSelect Settings, so it is neither the green of Available nor
// the red of Unavailable. `HALF_W1` is "only week 1 is a yes", `HALF_W2` the other.
AVAILABILITY.HALF_W1 = {
  label: 'W1 Only', short: 'W1 Only', glyph: '½',
  chip: 'bg-pb-surface2 text-pb-text border-pb-hairline', dot: 'bg-pb-surface2',
  cssVar: 'var(--pb-half-w1)', rank: 1.5,
}
AVAILABILITY.HALF_W2 = {
  label: 'W2 Only', short: 'W2 Only', glyph: '½',
  chip: 'bg-pb-surface2 text-pb-text border-pb-hairline', dot: 'bg-pb-surface2',
  cssVar: 'var(--pb-half-w2)', rank: 1.5,
}

// The half-available state for a two-day game's per-weekend answers
// ([{date, status}], in order), or '' when it does not apply: one weekend is a
// plain yes and the other a plain no. A maybe or no answer yet is not "half":
// those keep their own colour until the player has said.
export function halfStatus(days) {
  if (!Array.isArray(days) || days.length < 2) return ''
  const yes = days.map((d) => d.status === 'AVAILABLE')
  const no = days.map((d) => d.status === 'UNAVAILABLE')
  if (yes[0] && no[1]) return 'HALF_W1'
  if (no[0] && yes[1]) return 'HALF_W2'
  return ''
}
// The status to DRAW for a player: the half state when it applies, else their
// availability. Colour and dot only; never use this for a rule or a filter.
export const viewStatus = (p, days) => halfStatus(days ?? p?.availability_days) || p?.availability || 'NO_RESPONSE'

// What the club calls the two weeks of a two-day game: "W1" and "W2" unless it
// chose its own (many say A and B) in BetterSelect Settings. Every screen that
// names a week takes the names from here or from `useWeekNames()`, never a literal.
export const DEFAULT_WEEK_NAMES = { w1: 'W1', w2: 'W2' }
export const weekNameOf = (names, i) => (i === 0 ? names?.w1 : names?.w2) || DEFAULT_WEEK_NAMES[i === 0 ? 'w1' : 'w2']
// The half-available answers carry the names in their labels too (dot titles and
// any other place that reads `AVAILABILITY[s].label`).
export function applyWeekNames(names) {
  const n = { ...DEFAULT_WEEK_NAMES, ...(names || {}) }
  AVAILABILITY.HALF_W1.label = AVAILABILITY.HALF_W1.short = `${n.w1} Only`
  AVAILABILITY.HALF_W2.label = AVAILABILITY.HALF_W2.short = `${n.w2} Only`
}

// The quick answers for a two-day game: one tap says which weeks the player can
// do. `statuses` is [week 1, week 2]; a pattern is only an input, the store still
// holds one answer per date.
export function weekPatterns(names) {
  const n = { ...DEFAULT_WEEK_NAMES, ...(names || {}) }
  return [
    { key: 'both', title: 'Both weeks', statuses: ['AVAILABLE', 'AVAILABLE'], tone: 'AVAILABLE' },
    { key: 'w1', title: `${n.w1} Only`, statuses: ['AVAILABLE', 'UNAVAILABLE'], tone: 'HALF_W1' },
    { key: 'w2', title: `${n.w2} Only`, statuses: ['UNAVAILABLE', 'AVAILABLE'], tone: 'HALF_W2' },
    { key: 'none', title: 'Not available', statuses: ['UNAVAILABLE', 'UNAVAILABLE'], tone: 'UNAVAILABLE' },
  ]
}
// Which quick answer the two weeks' statuses spell out, or null (a maybe, or no
// answer yet for a week, is not any of the four).
export function weekPatternOf(statuses) {
  if (!Array.isArray(statuses) || statuses.length !== 2) return null
  return weekPatterns().find((w) => w.statuses[0] === statuses[0] && w.statuses[1] === statuses[1])?.key || null
}

// The one tag every screen puts beside a player for a two-day game, or null when
// there is nothing to say (the weeks match, or a week has no answer yet).
//   free one week, away the other  -> "W2 ONLY" in that half's colour
//   otherwise a week that is away  -> "W1 OUT"  (red), or unsure "W2 ?" (amber)
// The colour is always the one the card's own dot and edge are drawn in, so the
// same words never come in two colours. Drawing only: never a rule or a filter.
export function weekFlag(days, names) {
  if (!Array.isArray(days) || days.length < 2) return null
  if (days.every((d) => d.status === days[0].status)) return null
  const n = { ...DEFAULT_WEEK_NAMES, ...(names || {}) }
  const half = halfStatus(days)
  if (half) return { text: `${half === 'HALF_W1' ? n.w1 : n.w2} ONLY`, status: half }
  const parts = days
    .map((d, i) => ({ week: i + 1, name: i === 0 ? n.w1 : n.w2, status: d.status }))
    .filter((w) => w.status === 'UNAVAILABLE' || w.status === 'MAYBE')
  if (!parts.length) return null
  return {
    text: parts.map((w) => `${w.name} ${w.status === 'UNAVAILABLE' ? 'OUT' : '?'}`).join(' '),
    status: parts.some((w) => w.status === 'UNAVAILABLE') ? 'UNAVAILABLE' : 'MAYBE',
  }
}

// One status for a game played over several days: the least favourable, the same
// rule as `services/fixture_days.combine_status` on the server.
export function combineStatus(statuses) {
  const seen = new Set((statuses || []).map((s) => s || 'NO_RESPONSE'))
  return ['UNAVAILABLE', 'NO_RESPONSE', 'MAYBE', 'AVAILABLE'].find((s) => seen.has(s)) || 'NO_RESPONSE'
}

// Statuses in display order (available → maybe → no-response → unavailable),
// derived from `rank` so this stays in lockstep with the map above.
export const AVAIL_ORDER = [...AVAIL_STATUSES].sort(
  (a, b) => (AVAILABILITY[a]?.rank ?? 99) - (AVAILABILITY[b]?.rank ?? 99),
)

// Lowercase label, e.g. for inline sentences ("marked unavailable").
export const availLabel = (s) => (AVAILABILITY[s]?.label ?? String(s ?? ''))
export const availRank = (s) => (AVAILABILITY[s]?.rank ?? 99)
// THE availability sort, used by every screen that orders people by their answer
// (Selection board, its phone search, the Whiteboard pool, the Squads board): a
// player free ONE weekend of a two-day game and away the other leads, because they
// are nearly a yes and the selector has to decide; then Available, Maybe, no
// response, Unavailable. `status` is the combined answer, `days` the per-weekend
// answers ([{date, status}], two-day games only). Ordering only: never use it for a
// rule, count or filter. The server mirrors it in selection_pool.pool_sort_key.
export const availSortRank = (status, days) => (halfStatus(days) ? -1 : availRank(status))
