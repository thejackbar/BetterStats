// Shared vote-screen constants. Colours are theme tokens (see lib/theme.js) so
// light/dark and club white-labelling both work without a second palette.
export const VOTE_STATES = {
  open:          { label: 'OPEN',      cssVar: 'var(--pb-positive)' },
  closed:        { label: 'CLOSED',    cssVar: 'var(--pb-faint)' },
  locked:        { label: 'LOCKED',    cssVar: 'var(--pb-red)' },
  awaiting_team: { label: 'NO TEAM',   cssVar: 'var(--pb-amber)' },
  upcoming:      { label: 'UPCOMING',  cssVar: 'var(--pb-faintest)' },
}

// Hub status filter → the fixture states it covers.
export const STATUS_FILTERS = [
  { key: 'all',      label: 'All',        states: null },
  { key: 'open',     label: 'Open',       states: ['open'] },
  { key: 'awaiting', label: 'Needs team', states: ['awaiting_team'] },
  { key: 'closed',   label: 'Closed',     states: ['closed', 'locked'] },
]

export const seasonLabel = (y) => `${y}/${String((y + 1) % 100).padStart(2, '0')}`

export const fmtDate = (d, opts = { day: 'numeric', month: 'short' }) => {
  if (!d) return ''
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, opts) }
  catch { return d }
}

export const initialsOf = (name = '') =>
  name.split(/[ ,]+/).filter(Boolean).slice(0, 2).map((s) => s[0]).join('').toUpperCase()

// Progress bar colour: complete = positive, halfway = accent, behind = amber.
export const progressColour = (inCount, expected) => {
  if (!expected) return 'var(--pb-hairline)'
  const pct = inCount / expected
  if (pct >= 1) return 'var(--pb-positive)'
  if (pct >= 0.5) return 'var(--pb-accent)'
  return 'var(--pb-amber)'
}
