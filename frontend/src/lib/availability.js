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
    short: 'In',
    glyph: '✓',
    chip: 'bg-pb-accent/20 text-pb-accent border-pb-accent/40',
    dot: 'bg-pb-accent',
    cssVar: 'var(--pb-accent)',
    rank: 0,
  },
  UNAVAILABLE: {
    label: 'Unavailable',
    short: 'Out',
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
    short: 'No reply',
    glyph: '–',
    chip: 'bg-pb-surface2 text-pb-faintest border-pb-hairline',
    dot: 'bg-pb-faintest',
    cssVar: 'var(--pb-faintest)',
    rank: 2,
  },
}

// Statuses in display order (available → maybe → no-response → unavailable),
// derived from `rank` so this stays in lockstep with the map above.
export const AVAIL_ORDER = [...AVAIL_STATUSES].sort(
  (a, b) => (AVAILABILITY[a]?.rank ?? 99) - (AVAILABILITY[b]?.rank ?? 99),
)

// Lowercase label, e.g. for inline sentences ("marked unavailable").
export const availLabel = (s) => (AVAILABILITY[s]?.label ?? String(s ?? ''))
export const availRank = (s) => (AVAILABILITY[s]?.rank ?? 99)
