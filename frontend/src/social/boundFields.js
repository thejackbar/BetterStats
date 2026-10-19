// Bound fields: a text block on the Blank canvas that prints a live value (the
// third player in the lineup, the opponent, the date) instead of typed words,
// and the template file that brings a set of them in from a design made
// elsewhere (the Canva app writes this file).
//
// A template file is JSON:
//   {
//     "format": "bettercricket-template", "version": 1, "name": "LineUp",
//     "canvas": { "w": 1080, "h": 1350 },          // one of the Post size shapes
//     "background": "data:image/png;base64,...",   // the design with the field text taken out; optional
//     "fields": [
//       { "token": "player 1", "x": 80, "y": 300, "w": 600,
//         "fontFamily": "Anton", "fontSize": 54, "bold": true, "color": "#ffffff",
//         "align": "left", "uppercase": true, "lineHeight": 1, "letterSpacing": 0 }
//     ]
//   }
//
// Tokens (case and spacing do not matter; an unknown one is kept as plain text
// and reported, never guessed):
//   player N | player N first | player N last | player N role   N = 1 to LINEUP_MAX
//   captain | keeper | opponent | team | headline
//   competition | round | venue | date | time | season
import { newBlankItem, withDesign, BLANK_FONTS, BLANK_STARTERS } from './blank-template'
import { bindFromToken, bindLabel } from './boundResolve'
export { bindFromToken, bindLabel, resolveBind, boundSlotCount, isBoundPlayerSlot, LINEUP_SLOTS } from './boundResolve'

export const FORMAT = 'bettercricket-template'

const norm = (s) => String(s || '').toLowerCase().replace(/[{}]/g, '').replace(/\s+/g, ' ').trim()

// A design tool names its fonts however it likes. Match on the font's name; a
// font the editor does not carry falls back to Inter and is reported.
export function matchFont(name) {
  const n = norm(name)
  if (!n) return null
  const hit = BLANK_FONTS.find((f) => n === f.name.toLowerCase() || n === f.key || n.startsWith(f.name.toLowerCase().split(' (')[0]))
  return hit || null
}

const HEX = /^#[0-9a-f]{6}$/i
const num = (v, d) => (Number.isFinite(Number(v)) ? Number(v) : d)

// Reads and checks a template file. Never throws on content: returns the problem.
export function parseTemplateFile(raw) {
  let doc = raw
  if (typeof raw === 'string') {
    try { doc = JSON.parse(raw) } catch { return { error: 'That file is not JSON. Export the template from the BetterCricket Canva app again.' } }
  }
  if (!doc || typeof doc !== 'object' || doc.format !== FORMAT) return { error: 'That file is not a BetterCricket template (it should say "format": "bettercricket-template").' }
  if (doc.version !== 1) return { error: `This template is version ${doc.version}, and this editor reads version 1. Update the Canva app or the editor.` }
  const fieldsIn = Array.isArray(doc.fields) ? doc.fields : []
  if (!fieldsIn.length) return { error: 'The template has no fields. In Canva, type {{player 1}}, {{opponent}} and so on into text boxes first.' }
  const warnings = []
  const fields = []
  for (const f of fieldsIn.slice(0, 80)) {
    if (!f || typeof f !== 'object') continue
    const bind = bindFromToken(f.token)
    const font = matchFont(f.fontFamily)
    if (f.fontFamily && !font) warnings.push(`The font “${f.fontFamily}” is not in BetterPosts, so “${f.token}” uses Inter.`)
    fields.push({
      token: String(f.token || ''), bind,
      x: Math.round(num(f.x, 0)), y: Math.round(num(f.y, 0)), w: Math.max(40, Math.round(num(f.w, 400))),
      fontFamily: (font || BLANK_FONTS.find((x) => x.key === 'inter')).family,
      fontSize: Math.max(8, Math.round(num(f.fontSize, 40))),
      bold: f.bold !== false && !!f.bold,
      color: HEX.test(f.color || '') ? f.color.toLowerCase() : 'ink',
      align: ['left', 'center', 'right'].includes(f.align) ? f.align : 'left',
      uppercase: !!f.uppercase, lineHeight: num(f.lineHeight, 1), letterSpacing: num(f.letterSpacing, 0),
    })
    if (!bind) warnings.push(`“{{${f.token}}}” is not a field BetterCricket knows, so it stays as the text it is.`)
  }
  const w = num(doc.canvas && doc.canvas.w, 1080), h = num(doc.canvas && doc.canvas.h, 1080)
  return {
    name: String(doc.name || 'Imported template').slice(0, 80),
    canvas: { w, h }, background: typeof doc.background === 'string' ? doc.background : null,
    fields, warnings,
  }
}

// The blocks for a parsed template: the design at the back, a text block per
// field above it. `bind` is absent on a field that is not one (plain text).
export function itemsFromTemplate(parsed, { designUrl, designName, width, height, keep = [] }) {
  const fields = parsed.fields.map((f) => ({
    ...newBlankItem('text', {
      text: f.bind ? bindLabel(f.bind).toUpperCase() : f.token,
      x: f.x, y: f.y, w: f.w, fontFamily: f.fontFamily, fontSize: f.fontSize, bold: f.bold,
      color: f.color, align: f.align, lineHeight: f.lineHeight, letterSpacing: f.letterSpacing, uppercase: f.uppercase,
    }),
    // Every block an import makes is marked, including a word that is not a field,
    // so importing again replaces exactly these and leaves the club's own blocks.
    fromTemplate: true,
    ...(f.bind ? { bind: f.bind } : null),
  }))
  // Whatever the club put on top before stays, except an earlier import's own
  // fields and design (so importing the same template again updates it) and the
  // editor's own starter blocks when nobody has touched them, which would only
  // sit over the template. One block the club added or edited keeps everything.
  const own = keep.filter((it) => !it.fromTemplate && !it.design && it.type !== 'sponsors')
  const sig = (it) => [it.type, it.x, it.y, it.w, it.size, it.text].join('|')
  const untouched = BLANK_STARTERS.some((st) => { const b = st.build(); return b.length === own.length && b.every((x, i) => sig(x) === sig(own[i])) })
  const others = keep.filter((it) => !it.fromTemplate && !it.design && !(untouched && own.includes(it)))
  const base = designUrl ? withDesign(others, designUrl, designName, width, height) : [...keep.filter((it) => it.design), ...others]
  return [...base, ...fields]
}
