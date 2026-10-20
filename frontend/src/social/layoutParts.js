// Per-element colours and words for a layout (Brand, "This layout's elements").
//
// A palette has four roles (background, panel, accent, text) and a layout spends
// them in fixed places: the name band is the accent, the text on it is the
// background. That is a good default and a trap the moment a club's accent is
// dark, or a photo sits behind it. A layout that lists its parts here lets the
// club set each one on its own, so the title can be two colours, the names can
// be white on a red band, and the photo backdrop can be anything.
//
// The editor holds `{ [partsKey]: { [partKey]: value } }`. A part that is absent
// means "what the layout always drew", so a post nobody touched is byte for byte
// what it was, and an old saved template (no `parts`) opens unchanged. A layout
// reads a value with `pc` / `pt`, never directly, so the fallback is written
// once next to the element it belongs to.
//
// Each template file lists its own layouts' parts with `registerParts({...})`
// right under the layout, so a layout and its part list are edited together.
// This file imports nothing from the templates (they import it).

export const PART_KINDS = ['color', 'text']

// id -> [{ key, label, kind, group, auto, autoLabel? }]
export const LAYOUT_PARTS = {}

// Layouts of one family share their picks, so a heading colour or a name colour
// set on one layout is still there when the club tries its neighbour. A part a
// layout does not have is simply not read by it. The SAME KEY MUST MEAN THE SAME
// THING across a family (see STANDARD_KEYS); a part that means something only
// here takes a key of its own.
export const PARTS_FAMILY = {
  T1: 'LINEUP', T2: 'LINEUP', T3: 'LINEUP', T4: 'LINEUP', T5: 'LINEUP', T6: 'LINEUP', T7: 'LINEUP',
  T8: 'LINEUP', T9: 'LINEUP', T10: 'LINEUP', T11: 'LINEUP', T12: 'LINEUP', T13: 'LINEUP',
  C1: 'ANNOUNCE', C5: 'ANNOUNCE', C2: 'TOSS', C3: 'MOTM', C4: 'RESULT',
  RS1: 'RESULT', RS2: 'RESULT', RS3: 'RESULT', RS4: 'RESULT', RS5: 'RESULT', RS6: 'RESULT', RS7: 'RESULT', RS8: 'RESULT',
  FX1: 'FIXTURES', FX2: 'FIXTURES', FX3: 'FIXTURES', FX4: 'FIXTURES', FX5: 'FIXTURES', FX6: 'FIXTURES',
  RR1: 'RESULTS', RR2: 'RESULTS', RR3: 'RESULTS', RR4: 'RESULTS', RR5: 'RESULTS', RR6: 'RESULTS', RR7: 'RESULTS',
  TW1: 'TOTW', TW2: 'TOTW', MS1: 'MILESTONES', MS2: 'MILESTONES',
  SC1: 'SCORECARD', SC2: 'SCORECARD', SC3: 'SCORECARD',
  EV1: 'EVENT', EV2: 'EVENT', EV3: 'EVENT', EV4: 'EVENT', EV5: 'EVENT', EV6: 'EVENT', EV7: 'EVENT',
  EV8: 'EVENT', EV9: 'EVENT', EV10: 'EVENT', EV11: 'EVENT',
  EL1: 'EVENTLIST', EL2: 'EVENTLIST', EL3: 'EVENTLIST',
}

// The keys that recur across families. A layout that has the element uses the key,
// so the picks carry between its neighbours. Labels may differ per layout.
export const STANDARD_KEYS = {
  title1: 'first heading word(s) (text)', title1Color: 'its colour',
  title2: 'second heading word(s) (text)', title2Color: 'its colour',
  roundColor: 'the round / date / competition line', clubColor: 'the club name',
  nameColor: 'a player or team name', firstColor: 'a first name', numColor: 'a number or rank',
  statColor: 'the main figure (score, runs, wickets)', subColor: 'secondary text (grade, opposition, venue)',
  cardBg: 'a card or row panel', cardBorder: 'its outline', photoBg: 'the backdrop behind a photo',
  bandBg: 'a name or label band', badgeBg: 'a tag or chip', badgeColor: 'text on it',
  winColor: 'a win', lossColor: 'a loss', dividerColor: 'rules between rows',
  headerBg: 'the header bar', headerRule: 'the line under the header',
  footerBg: 'the footer bar', footerRule: 'the line over the footer',
}

export function registerParts(map) {
  Object.keys(map || {}).forEach((id) => { LAYOUT_PARTS[id] = map[id] })
}

// Spec helpers, so a layout's list reads as a list.
export const colorPart = (key, label, group, auto, extra) => ({ key, label, kind: 'color', group, auto, ...extra })
export const textPart = (key, label, group, auto, extra) => ({ key, label, kind: 'text', group, auto, ...extra })

export function partsFor(templateId) {
  return LAYOUT_PARTS[templateId] || null
}

export function partsKey(templateId) {
  return PARTS_FAMILY[templateId] || templateId
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

// True when the club has picked this colour (used where a pick changes a
// dependent default, e.g. text on a band whose colour was changed).
export function picked(parts, key) {
  const v = parts && parts[key]
  return typeof v === 'string' && HEX.test(v)
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
// hand-edited saved template cannot put junk into a style attribute. Validates
// against every layout in the family, so one layout's picks survive being
// cleaned for its neighbour.
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
