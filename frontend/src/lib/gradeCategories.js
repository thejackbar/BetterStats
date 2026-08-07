// Grade categories, mirroring backend/app/services/grade_labels.py's
// GRADE_CATEGORIES + CATEGORY_LABELS. Keep the two in step: the backend is the
// authority on what a category means, this file only decides how it reads.

export const GRADE_CATEGORIES = ['senior', 'junior', 'womens', 'masters', 'mixed']

export const CATEGORY_LABELS = {
  senior: 'Senior',
  junior: 'Juniors',
  womens: "Women's",
  masters: 'Masters',
  mixed: 'Mixed',
}

// Senior is deliberately absent: it is the baseline the others are added to.
// Offering it as a toggle invites someone to switch off the bulk of a club's
// cricket and be left staring at an empty page.
export const TOGGLEABLE_CATEGORIES = ['junior', 'womens', 'masters', 'mixed']

// What counts when nobody has chosen — everything except junior. Mirrors
// grade_scope.DEFAULT_CATEGORIES. Only used to seed local state before the
// first response comes back; the server's own answer wins from then on.
export const DEFAULT_CATEGORIES = GRADE_CATEGORIES.filter(c => c !== 'junior')

// The wire format the API takes: a comma-separated include list. Null when the
// selection is the whole set, so the request carries no filter at all and the
// server takes its untouched default path.
export function categoriesParam(categories) {
  if (!categories || categories.length === 0) return null
  const set = new Set(categories)
  if (GRADE_CATEGORIES.every(c => set.has(c))) return 'all'
  return GRADE_CATEGORIES.filter(c => set.has(c)).join(',')
}

function joinLabels(keys) {
  const labels = (keys || []).map(c => CATEGORY_LABELS[c] || c)
  if (labels.length <= 1) return labels[0] || ''
  return `${labels.slice(0, -1).join(', ')} and ${labels[labels.length - 1]}`
}

// A short line for a page to explain what its figures currently cover.
// Returns null when nothing is excluded, so a club with no junior grades never
// sees a note about a filter that is not doing anything.
export function scopeNote(scope) {
  if (!scope || !scope.active) return null
  const left = joinLabels(scope.excluded_categories)
  if (!left) return null
  return `${left} grades are not counted here. Use Include above to add them back.`
}

// The profile-only case: this player has never played in any category the club
// counts by default, so the grades they DID play were switched on for them.
// Worth saying out loud — otherwise their figures look inconsistent with the
// Leaderboard, and nobody would know why.
export function autoShownNote(scope) {
  if (!scope || !scope.auto_shown) return null
  const shown = joinLabels((scope.categories || []).filter(c => c !== 'senior'))
  return shown
    ? `This player has only played ${shown} cricket, so those grades are being counted. `
      + 'Elsewhere on the site they are left out by default.'
    : null
}
