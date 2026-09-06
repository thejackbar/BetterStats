// What counts as a dismissal, in the browser.
//
// Mirrors backend/app/services/dismissal.py. Keep the two in step: a batting
// average is runs / (innings - not outs), and the flag this decides is what
// fills the denominator.
//
// MCC Law 25.4 splits the two retirements, and so does Cricket Australia's
// feed. "Retired - not out" (25.4.2, illness or injury, did not resume) is NOT
// a dismissal. "Retired - out" (25.4.3, retired for any other reason without
// consent) IS one. Never collapse them with a `startsWith('retired')` test.

export const NOT_OUT_DISMISSALS = new Set([
  'not out',
  'retired not out',
  'retired hurt',
])

export const RETIRED_OUT_DISMISSALS = new Set(['retired out'])

export const normaliseDismissal = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase()

// True when the innings ended without the batter being dismissed. Takes either
// a dismissal phrase ("retired not out") or one of the upload form's own mode
// values, which are deliberately the same strings.
export const isNotOutDismissal = text => NOT_OUT_DISMISSALS.has(normaliseDismissal(text))
