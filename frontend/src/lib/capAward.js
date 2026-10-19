// Which awards are a playing cap, and how a cap number reads on a badge.
// Same rule as backend/app/services/cap_awards.py; change them together.
// Only an award KNOWN to be a cap reads "Cap 186": the detail column also holds
// "436 runs at 39.64" on a Best Batter and "captain" on a premiership.

const CAP_NAME = /\bcap(?:\s+number)?\s*$/i
const NUMBER = /^\s*#?\s*(\d+)\s*$/

export function isCapAward(a) {
  const name = (a?.achievement || '').trim()
  if (a?.category === 'Milestone' && a?.subcategory === 'Cap Number' && name.toLowerCase() === 'player number') return true
  return CAP_NAME.test(name)
}

export function capNumber(detail) {
  const m = detail == null ? null : NUMBER.exec(String(detail))
  return m ? Number(m[1]) : null
}

// "A Grade Cap Number" + 186 -> "A Grade Cap 186". null when this is not a
// cap, or has no number to show, so the caller falls back to its usual badge.
export function capBadgeText(a, label) {
  if (!isCapAward(a)) return null
  const n = capNumber(a.detail)
  if (n == null) return null
  const base = (label || a.achievement || 'Cap').replace(/\s+number\s*$/i, '').trim()
  return /\bcap$/i.test(base) ? `${base} ${n}` : `Cap ${n}`
}
