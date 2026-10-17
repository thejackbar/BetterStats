// How a side's number of players is judged, in one place. A side has a SIZE
// (the most it may name, 0 = no limit) and optionally a MIN (the fewest it may
// field, for a women's or junior side that needs 8 but may name 12). With no
// minimum a side is complete only when it is full.

// What a count needs to reach before the side is complete.
export const sideNeed = (size, min) => (min > 0 ? min : size > 0 ? size : 0)

// { short, over, off }: how many players short of the need, how many over the
// size, and whether either is true.
export function sideFit(count, size, min) {
  const need = sideNeed(size, min)
  const short = need > 0 && count < need ? need - count : 0
  const over = size > 0 && count > size ? count - size : 0
  return { short, over, off: short > 0 || over > 0, need }
}

// "11-a-side", "8 to 12 players", "at least 8 players".
export function sideLabel(size, min) {
  if (min > 0 && size > 0) return `${min} to ${size} players`
  if (min > 0) return `at least ${min} players`
  return `${size}-a-side`
}

// The sentence a confirm prompt or banner uses for a count that is off.
export function sideProblem(count, size, min) {
  const { short, over } = sideFit(count, size, min)
  if (short) return min > 0 ? `${short} short of the minimum of ${min}` : `${short} short of ${size}`
  if (over) return `${over} over the ${size}`
  return ''
}
