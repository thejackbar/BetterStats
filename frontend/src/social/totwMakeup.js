// Team of the week: picking a team to a make-up (four batters, a keeper, three
// all-rounders, three bowlers) instead of simply taking the best performers.
//
// The pool comes ranked best first from `GET /admin/social/totw`, and every
// entry carries the `kind` seat it earned that week (WK, BAT, AR, BOWL; see
// `social_rounds._totw_kind`). A seat is filled from the top of the ranking, so
// the team is still "the best of each", never a lesser player taken to fit.
//
// Pure functions, no React: the picker below is what the editor, the phone
// quick-post and the verification script all call.

export const MAKEUP_KINDS = ['WK', 'BAT', 'AR', 'BOWL']

export const MAKEUP_LABELS = {
  WK: 'Wicketkeeper',
  BAT: 'Batters',
  AR: 'All-rounders',
  BOWL: 'Bowlers',
  ANY: 'Best of the rest',
}

// The same shape BetterFantasyCricket asks for. 4 + 1 + 3 + 3 = 11.
export const FANTASY_MAKEUP = { WK: 1, BAT: 4, AR: 3, BOWL: 3, ANY: 0 }

// Scarce seats first, so a keeper or an all-rounder is never used up as a
// batter before their own seat is filled.
const FILL_ORDER = ['WK', 'AR', 'BAT', 'BOWL']

export function makeupSize(counts) {
  return [...MAKEUP_KINDS, 'ANY'].reduce((n, k) => n + Math.max(0, Number(counts?.[k]) || 0), 0)
}

// How many of each seat the pool can supply at most, so the editor can say
// "3 batters asked for, 2 played".
export function poolKinds(pool) {
  const out = { WK: 0, BAT: 0, AR: 0, BOWL: 0 }
  for (const p of pool || []) if (out[p.kind] != null) out[p.kind] += 1
  return out
}

// Fill the make-up from the ranked pool.
//   picks   the chosen players, best performance first (pool order)
//   short   {WK: 1, ...} seats the pool could not fill, by kind
//   missing how many seats in total went unfilled by kind and were backfilled
//           with the next best player of any kind (or left empty if the pool ran out)
//   wanted  the team size asked for
// A seat the pool cannot fill is a warning, not a refusal: a round with no
// recorded keeper still gets a team, with the next best performer in the gap.
export function pickMakeup(pool, counts) {
  const ranked = pool || []
  const taken = new Set()
  const short = {}
  for (const kind of FILL_ORDER) {
    const want = Math.max(0, Number(counts?.[kind]) || 0)
    let got = 0
    for (let i = 0; i < ranked.length && got < want; i++) {
      if (!taken.has(i) && ranked[i].kind === kind) { taken.add(i); got += 1 }
    }
    if (got < want) short[kind] = want - got
  }
  const gap = (Math.max(0, Number(counts?.ANY) || 0)) + Object.values(short).reduce((a, b) => a + b, 0)
  let filled = 0
  for (let i = 0; i < ranked.length && filled < gap; i++) {
    if (!taken.has(i)) { taken.add(i); filled += 1 }
  }
  const picks = [...taken].sort((a, b) => a - b).map(i => ranked[i])
  return { picks, short, wanted: makeupSize(counts) }
}

// One plain sentence for what could not be filled, '' when nothing is short.
export function shortfallText(short, pickedCount, wanted) {
  const parts = Object.entries(short || {}).map(([k, n]) => `${n} ${n === 1 ? singular(k) : MAKEUP_LABELS[k].toLowerCase()}`)
  const missing = Math.max(0, (wanted || 0) - (pickedCount || 0))
  if (!parts.length && !missing) return ''
  const list = parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}` : parts[0]
  const base = list ? `Short by ${list} this week, so the next best performers fill those places.` : ''
  const gap = missing ? ` Only ${pickedCount} players are in the pool for a team of ${wanted}.` : ''
  return `${base}${gap}`.trim()
}

function singular(kind) {
  return { WK: 'wicketkeeper', BAT: 'batter', AR: 'all-rounder', BOWL: 'bowler' }[kind] || kind.toLowerCase()
}
