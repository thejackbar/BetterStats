// Per-element colours and words for a layout (Brand, "This layout's elements").
//
// A palette has four roles (background, panel, accent, text) and a layout spends
// them in fixed places: the name band is the accent, the text on it is the
// background. That is a good default and a trap the moment a club's accent is
// dark, or a photo sits behind it. A layout that lists its parts here lets the
// club set each one on its own, so the title can be two colours, the names can
// be white on a red band, and the photo backdrop can be anything.
//
// The editor holds `{ [templateId]: { [partKey]: value } }`. A part that is
// absent means "what the layout always drew", so a post nobody touched is byte
// for byte what it was, and an old saved template (no `parts`) opens unchanged.
// A layout reads a value with `pc` / `pt`, never directly, so the fallback is
// written once next to the element it belongs to.

const HEAD = 'Heading'
const CARD = 'Player cards'
const ROW = 'Player rows'
const FOOT = 'Footer'

const HEADING_PARTS = [
  { key: 'title1', label: 'First word(s)', kind: 'text', group: HEAD, auto: () => 'TEAM OF' },
  { key: 'title1Color', label: 'First word colour', kind: 'color', group: HEAD, auto: (p) => p.ink },
  { key: 'title2', label: 'Second word(s)', kind: 'text', group: HEAD, auto: () => 'THE WEEK' },
  { key: 'title2Color', label: 'Second word colour', kind: 'color', group: HEAD, auto: (p) => p.accent },
  { key: 'roundColor', label: 'Round line', kind: 'color', group: HEAD, auto: (p) => p.accent },
  { key: 'clubColor', label: 'Club name', kind: 'color', group: HEAD, auto: (p) => p.ink },
]

const FOOTER_PARTS = [
  { key: 'footerBg', label: 'Footer bar', kind: 'color', group: FOOT, auto: (p) => p.primary },
  { key: 'footerRule', label: 'Footer line', kind: 'color', group: FOOT, auto: (p) => p.accent },
]

export const LAYOUT_PARTS = {
  TW1: [
    ...HEADING_PARTS,
    { key: 'photoBg', label: 'Photo backdrop', kind: 'color', group: CARD, auto: null, autoLabel: 'Card colour' },
    { key: 'cardBorder', label: 'Card outline', kind: 'color', group: CARD, auto: (p) => p.accent },
    { key: 'numColor', label: 'Card number', kind: 'color', group: CARD, auto: (p) => p.ink },
    { key: 'bandBg', label: 'Name band', kind: 'color', group: CARD, auto: (p) => p.accent },
    { key: 'nameColor', label: 'Surname', kind: 'color', group: CARD, auto: (p) => p.primary },
    { key: 'statColor', label: 'Score line', kind: 'color', group: CARD, auto: (p) => p.primary },
    { key: 'gradeColor', label: 'Grade line', kind: 'color', group: CARD, auto: (p) => p.primary },
    { key: 'pointsBg', label: 'Points tag', kind: 'color', group: CARD, auto: (p) => p.accent },
    { key: 'pointsColor', label: 'Points text', kind: 'color', group: CARD, auto: (p) => p.primary },
    ...FOOTER_PARTS,
  ],
  TW2: [
    ...HEADING_PARTS,
    { key: 'ruleColor', label: 'Top line', kind: 'color', group: ROW, auto: (p) => p.accent },
    { key: 'dividerColor', label: 'Row dividers', kind: 'color', group: ROW, auto: (p) => p.ink },
    { key: 'numColor', label: 'Row number', kind: 'color', group: ROW, auto: (p) => p.accent },
    { key: 'faceBg', label: 'Photo backdrop', kind: 'color', group: ROW, auto: null, autoLabel: 'Soft tint' },
    { key: 'faceBorder', label: 'Photo ring', kind: 'color', group: ROW, auto: (p) => p.accent },
    { key: 'firstColor', label: 'First name', kind: 'color', group: ROW, auto: (p) => p.ink },
    { key: 'nameColor', label: 'Surname', kind: 'color', group: ROW, auto: (p) => p.ink },
    { key: 'statColor', label: 'Score line', kind: 'color', group: ROW, auto: (p) => p.accent },
    { key: 'subColor', label: 'Grade and opposition', kind: 'color', group: ROW, auto: (p) => p.ink },
    ...FOOTER_PARTS,
  ],
}

export function partsFor(templateId) {
  return LAYOUT_PARTS[templateId] || null
}

// Layouts of one post type share their picks, so a heading or a name colour set
// on the Team Sheet is still there when the club tries the Ranked Board. A part
// a layout does not have is simply not read by it.
const SHARED = { TW1: 'TOTW', TW2: 'TOTW' }
export function partsKey(templateId) {
  return SHARED[templateId] || templateId
}

const HEX = /^#[0-9a-fA-F]{6}$/

// A colour part: the club's pick when it is a real colour, else the layout's own.
export function pc(parts, key, fallback) {
  const v = parts && parts[key]
  return typeof v === 'string' && HEX.test(v) ? v : fallback
}

// A text part: an empty string is a pick ("print nothing"), absent is not.
export function pt(parts, key, fallback) {
  const v = parts && parts[key]
  return typeof v === 'string' ? v : fallback
}

// White or near-black, whichever reads better on `hex` (WCAG relative luminance).
export function inkOn(hex) {
  if (!HEX.test(hex || '')) return '#ffffff'
  const c = [1, 3, 5].map((i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
  })
  const L = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
  return L > 0.4 ? '#0b0b0b' : '#ffffff'
}

// Drop anything that is not a known part with a sane value, so a stale or
// hand-edited saved template cannot put junk into a style attribute.
export function cleanParts(templateId, raw) {
  if (!LAYOUT_PARTS[templateId] || !raw || typeof raw !== 'object') return {}
  const group = partsKey(templateId)
  const spec = Object.keys(LAYOUT_PARTS).filter((id) => partsKey(id) === group).flatMap((id) => LAYOUT_PARTS[id])
  const out = {}
  spec.forEach(({ key, kind }) => {
    const v = raw[key]
    if (kind === 'color' && typeof v === 'string' && HEX.test(v)) out[key] = v
    if (kind === 'text' && typeof v === 'string') out[key] = v.slice(0, 24)
  })
  return out
}
