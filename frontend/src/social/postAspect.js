// What SHAPE a post is, and the handful of primitives a template uses to design
// for it. One definition, because a template that invents its own breakpoint is
// how two layouts in the same family start disagreeing about what "portrait" is.
//
// Reflow (v9.74.0) made every layout DRAW correctly at 4:5 and 9:16 — the boxes
// grow and nothing overlaps. That is not the same as being designed for the
// shape: a fixture row that is 45px of content in a 200px slot reads as a square
// design with air pushed through it. These primitives are what let a template
// spend the extra height deliberately instead.

/** 1080×1080 → 'square', 1080×1350 → 'portrait', 1080×1920 → 'story'. */
export function aspectOf(width = 1080, height = 1080) {
  const r = height / (width || 1080)
  if (r <= 1.05) return 'square'
  if (r <= 1.45) return 'portrait'
  return 'story'
}

/**
 * Pick a value per shape. `portrait` falls back to `square` and `story` falls
 * back to `portrait`, so a template only names the shapes it actually redesigns
 * for and every other one keeps exactly what it had.
 */
export function pick(aspect, values = {}) {
  const sq = values.square
  const po = 'portrait' in values ? values.portrait : sq
  if (aspect === 'story') return 'story' in values ? values.story : po
  if (aspect === 'portrait') return po
  return sq
}

/**
 * A band that was N pixels tall on the square, kept at the same SHARE of a
 * taller canvas. A photo band fixed at 680 is two thirds of a square and barely
 * a third of a story, which reads as the design falling apart rather than as a
 * taller post. Exact at 1080, so the square is untouched.
 */
export const share = (canvasH, at1080) => Math.round((canvasH * at1080) / 1080)

/**
 * A band that keeps its pixels up to a ceiling, then grows at a fraction of the
 * extra height. For a masthead or a footer: `share` would balloon a 150px footer
 * to 267px on a story, and a fixed 150 leaves it looking mean under 1920px of
 * post. `grow(h, 150, 0.35)` lands at 150 / 244 / 444.
 */
export const grow = (canvasH, at1080, rate = 0.35) =>
  Math.round(at1080 + Math.max(0, canvasH - 1080) * rate)

// A `type(canvasH, at1080)` was written alongside these and is deliberately NOT
// here: every template that steps its type up does so with `pick`, because the
// right size at 4:5 is a design decision per layout rather than one curve. An
// exported helper nothing calls is worse than none.

export default aspectOf
