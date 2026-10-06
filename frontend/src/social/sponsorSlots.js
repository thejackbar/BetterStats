// Where a post's sponsor grid goes, per layout.
//
// The sponsor grid is a block (blank-template.jsx, `sponsors`) that sits ABOVE a
// layout. With one generic spot for every layout, the grid landed wherever the
// bottom edge happened to be and covered whatever the layout had drawn there. So
// each layout now reserves a slot for it and says where that slot is, and the
// editor puts the grid in it.
//
// ONE definition per layout. A layout file exports `SPONSOR_SLOTS`, a map of
// template id to `(width, height, count) => { x, y, w, h, pad?, gap?, panel? }`
// in canvas pixels. The layout calls the SAME function to leave that rectangle
// empty (`const slot = SPONSOR_SLOTS.T2(width, height, count)`), so the space it
// keeps and the place the grid goes cannot drift apart. A layout with no entry
// here falls back to the generic bottom band in `defaultSponsorGeometry`.
//
// A layout whose slot moves with an option the editor holds (the Glass Card's
// position) gets that option as a fourth argument, `opts`; the others ignore it.
//
// `count` is how many logos the grid holds. A slot is a fixed rectangle; the grid
// lays its logos out inside it (`sponsorGridLayout`), so a slot only needs to read
// `count` when a layout wants a different shape for one logo and for four.
import { defaultSponsorGeometry } from './blank-template'
import { SPONSOR_SLOTS as CRICKET } from './cricket-templates'
import { SPONSOR_SLOTS as SPLIT } from './split-template'
import { SPONSOR_SLOTS as CARD } from './lineup-card-template'
import { SPONSOR_SLOTS as GLASS } from './result-glass-template'
import { SPONSOR_SLOTS as ROUND } from './round-templates'
import { SPONSOR_SLOTS as TOTW } from './totw-templates'
import { SPONSOR_SLOTS as EVENT } from './event-templates'

const SLOTS = { ...CRICKET, ...SPLIT, ...CARD, ...GLASS, ...ROUND, ...TOTW, ...EVENT }

/** Does this layout reserve a sponsor slot of its own? */
export function hasSponsorSlot(templateId) {
  return typeof SLOTS[templateId] === 'function'
}

/**
 * The rectangle for this layout's sponsor grid on a canvas of this size, as the
 * fields a `sponsors` block takes (x, y, w, h and, where the layout has a view,
 * pad, gap and panel). Layouts without a slot get the generic bottom band.
 */
export function sponsorSlotFor(templateId, width, height, count = 1, opts) {
  const fn = SLOTS[templateId]
  if (typeof fn === 'function') {
    const { _labelH, ...s } = fn(width, height, count, opts) || {}
    if (Object.keys(s).length) return { ...s, x: Math.round(s.x), y: Math.round(s.y), w: Math.round(s.w), h: Math.round(s.h) }
  }
  return defaultSponsorGeometry(width, height, count)
}
