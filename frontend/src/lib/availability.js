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
  label: 'Week 1 only', short: 'Week 1 only', glyph: '½',
  chip: 'bg-pb-surface2 text-pb-text border-pb-hairline', dot: 'bg-pb-surface2',
  cssVar: 'var(--pb-half-w1)', rank: 1.5,
}
AVAILABILITY.HALF_W2 = {
  label: 'Week 2 only', short: 'Week 2 only', glyph: '½',
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

// Statuses in display order (available → maybe → no-response → unavailable),
// derived from `rank` so this stays in lockstep with the map above.
export const AVAIL_ORDER = [...AVAIL_STATUSES].sort(
  (a, b) => (AVAILABILITY[a]?.rank ?? 99) - (AVAILABILITY[b]?.rank ?? 99),
)

// Lowercase label, e.g. for inline sentences ("marked unavailable").
export const availLabel = (s) => (AVAILABILITY[s]?.label ?? String(s ?? ''))
export const availRank = (s) => (AVAILABILITY[s]?.rank ?? 99)
