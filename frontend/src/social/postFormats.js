// The post sizes BetterSocials renders at, in ONE place.
//
// Every template composes its artwork at a fixed 1080×1080 square (ART_W ×
// ART_H). A format is therefore only ever a CANVAS: the same width, a taller
// height, with the artwork sitting centred inside it and the template's own
// background carried out to the new edges. That is what makes one definition
// serve all three sizes — a template does not get re-laid-out per format, so
// three separately-tuned copies of a layout can never drift apart.
//
// WIDTH IS 1080 IN ALL THREE, which is the whole reason this works. Adding a
// format that is NOT 1080 wide means deciding how the artwork scales, and that
// is a different change from this one.
//
// The scorecard templates are the exception and say so themselves: they compose
// at 1920×1080 landscape and already carry a `square` prop of their own.

export const ART_W = 1080
export const ART_H = 1080

export const POST_FORMATS = [
  {
    key: 'square',
    label: 'Square',
    ratio: '1:1',
    w: 1080,
    h: 1080,
    // What a club is actually choosing between, in their words rather than ours.
    note: 'Feed post. Works everywhere.',
  },
  {
    key: 'portrait',
    label: 'Portrait',
    ratio: '4:5',
    w: 1080,
    h: 1350,
    note: 'Tallest a feed post can go — takes up more of the screen.',
  },
  {
    key: 'story',
    label: 'Story',
    ratio: '9:16',
    w: 1080,
    h: 1920,
    note: 'Full screen for Stories and Reels.',
  },
]

export const DEFAULT_POST_FORMAT = 'square'

const BY_KEY = Object.fromEntries(POST_FORMATS.map((f) => [f.key, f]))

// An unknown key reads as the square, never as a broken canvas — a stored draft
// or a `?format=` on the URL is not something to trust into a style object.
export function postFormat(key) {
  return BY_KEY[key] || BY_KEY[DEFAULT_POST_FORMAT]
}

// The band above and below the artwork, per side. 0 for the square.
export function matteFor(h) {
  return Math.max(0, Math.round(((h || ART_H) - ART_H) / 2))
}

export default POST_FORMATS
