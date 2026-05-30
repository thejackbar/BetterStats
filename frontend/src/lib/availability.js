// Single source of truth for availability-status presentation.
//
// Both the Availability matrix (chip glyph + cell colour) and the Selection
// board (status dot + sort rank) render the same four statuses. Keeping the
// colour/label/rank identity here stops the two screens from drifting apart.

export const AVAIL_STATUSES = ['AVAILABLE', 'UNAVAILABLE', 'MAYBE', 'NO_RESPONSE']

export const AVAILABILITY = {
  AVAILABLE: {
    label: 'Available',
    glyph: '✓',
    chip: 'bg-pb-accent/20 text-pb-accent border-pb-accent/40',
    dot: 'bg-pb-accent',
    rank: 0,
  },
  UNAVAILABLE: {
    label: 'Unavailable',
    glyph: '✕',
    chip: 'bg-pb-red/20 text-pb-red border-pb-red/40',
    dot: 'bg-pb-red',
    rank: 3,
  },
  MAYBE: {
    label: 'Maybe',
    glyph: '?',
    chip: 'bg-amber-400/20 text-amber-300 border-amber-400/40',
    dot: 'bg-amber-400',
    rank: 1,
  },
  NO_RESPONSE: {
    label: 'No response',
    glyph: '–',
    chip: 'bg-pb-surface2 text-pb-faintest border-pb-hairline',
    dot: 'bg-pb-faintest',
    rank: 2,
  },
}

// Lowercase label, e.g. for inline sentences ("marked unavailable").
export const availLabel = (s) => (AVAILABILITY[s]?.label ?? String(s ?? ''))
export const availRank = (s) => (AVAILABILITY[s]?.rank ?? 99)
