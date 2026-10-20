// Forgiving matching for the typeahead boxes: "richie" finds "Ritchie, Peter", "rich" does too
// while it is still being typed, and word order does not matter. Pure, so it can be tested alone.
//
// Each word the person typed must match some word of the name, scored 3 (a word starts with it),
// 2 (a word contains it) or 1 (within an edit or two: a typo, or the start of a word with one). A name
// is offered only if every typed word scores. Best total first, then the shorter name.
export const norm = s => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
  .replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim()

function distance(a, b, cap) {
  if (Math.abs(a.length - b.length) > cap) return cap + 1
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j)
  for (let i = 1; i <= a.length; i++) {
    const cur = [i]
    let best = i
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1))
      if (cur[j] < best) best = cur[j]
    }
    if (best > cap) return cap + 1
    prev = cur
  }
  return prev[b.length]
}

const tolerance = w => (w.length >= 7 ? 2 : w.length >= 4 ? 1 : 0)

function wordScore(q, words) {
  let best = 0
  for (const w of words) {
    if (w.startsWith(q)) return 3
    if (q.length >= 3 && w.includes(q)) best = Math.max(best, 2)
    const tol = tolerance(q)
    if (tol && (distance(q, w, tol) <= tol || distance(q, w.slice(0, q.length), tol) <= tol
      || distance(q, w.slice(0, q.length + 1), tol) <= tol)) best = Math.max(best, 1)
  }
  return best
}

export function suggest(items, query, { limit = 8, minChars = 1 } = {}) {
  const q = norm(query)
  if (q.length < minChars) return { shown: [], total: 0, closest: false }
  const qs = q.split(' ')
  const scored = []
  for (const item of items) {
    const words = norm(item).split(' ')
    let total = 0
    let ok = true
    for (const w of qs) {
      const s = wordScore(w, words)
      if (!s) { ok = false; break }
      total += s
    }
    if (ok) scored.push({ item, total, len: item.length })
  }
  scored.sort((a, b) => b.total - a.total || a.len - b.len || a.item.localeCompare(b.item))
  const strong = scored.length > 0 && scored[0].total >= qs.length * 2
  return { shown: scored.slice(0, limit).map(s => s.item), total: scored.length, closest: scored.length > 0 && !strong }
}
