// One ordering for names that carry a number: squads, teams and grades.
// Digits are read as numbers, so "1st XI" comes before "2nd XI" and both before
// "10th XI" (alphabetical puts "10th" between "1st" and "2nd"). Backend twin:
// backend/app/services/natural_order.py. Anything that sorts a squad, team or
// grade name for display should use this and nothing else.
const collator = new Intl.Collator('en', { numeric: true, sensitivity: 'base' })
export const naturalCompare = (a, b) => collator.compare(String(a ?? ''), String(b ?? ''))
export const sortNatural = (list, pick = (x) => x) => [...list].sort((a, b) => naturalCompare(pick(a), pick(b)))
