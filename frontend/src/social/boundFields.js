// Bound fields: a text block on the Blank canvas that prints a live value (the
// third player in the lineup, the opponent, the date) instead of typed words,
// and the template file that brings a set of them in from a design made
// elsewhere (the Canva app writes this file).
//
// A template file is JSON:
//   {
//     "format": "bettercricket-template", "version": 1, "name": "LineUp",
//     "postType": "lineup",                        // lineup | general (default). Decides where it imports.
//     "canvas": { "w": 1080, "h": 1350 },          // one of the Post size shapes
//     "background": "data:image/png;base64,...",   // the design with the field text taken out; optional
//     "fields": [
//       { "token": "player 1", "x": 80, "y": 300, "w": 600,
//         "fontFamily": "Anton", "fontSize": 54, "bold": true, "color": "#ffffff",
//         "colorRole": "ink",        // optional: ink | accent | primary | secondary | white | black
//         "fontRole": "display",     // optional: display | body
//         "align": "left", "uppercase": true, "lineHeight": 1, "letterSpacing": 0 }
//     ],
//     "texts": [ { "text": "LINE UP", ...same look keys as a field... } ],  // fixed words, optional
//     "panels": [ { "x": 70, "y": 130, "w": 450, "h": 950, "source": "picture", "color": "#7b3b3b" } ]
//                // surfaces behind the text; "color" only when the design's was a solid colour.
//                // A picture panel can carry its own picture: "image" (a data URL) and "box"
//                // ({x,y,w,h,rotation}, the picture's own rectangle before it was turned).
//     "background": "data:image/png;base64,..."   // the design's own background picture, optional
//   }
//
// STRUCTURE FIRST. By default an import uses the roles, not the designer's own
// values: a colour role becomes a palette token (so the club's palette tints it and
// a palette switch re-tints it) and a font role becomes the club's display font or
// Inter. The designer's colour and font name are kept in the file for a club that
// chooses "keep my Canva look". A panel is drawn as a rectangle behind the text, tinted
// with the club's accent (a flat copy of a picture's colour cannot be known).
//
// Tokens (case and spacing do not matter; an unknown one is kept as plain text
// and reported, never guessed):
//   player N | player N first | player N last | player N role   N = 1 to LINEUP_MAX
//   captain | keeper | opponent | team | headline
//   competition | round | venue | date | time | season
import { newBlankItem, withDesign, BLANK_FONTS, BLANK_STARTERS } from './blank-template'
import { bindFromToken, bindLabel } from './boundResolve'

// How much of the club's accent a panel carries: enough to show, not enough to fight the text.
export const PANEL_TINT = 0.22
const COLOR_ROLES = ['ink', 'accent', 'primary', 'secondary', 'white', 'black']
const FONT_ROLES = ['display', 'body']
const fontByKey = (key) => BLANK_FONTS.find((x) => x.key === key)
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
  const look = (f) => {
    const font = matchFont(f.fontFamily)
    return {
      x: Math.round(num(f.x, 0)), y: Math.round(num(f.y, 0)), w: Math.max(40, Math.round(num(f.w, 400))),
      // The designer's own values, used only when a club keeps the Canva look.
      hex: HEX.test(f.color || '') ? f.color.toLowerCase() : null,
      fontName: f.fontFamily ? String(f.fontFamily) : null,
      font,
      // What the colour and font are for, which a club's own branding fills in.
      colorRole: COLOR_ROLES.includes(f.colorRole) ? f.colorRole : null,
      fontRole: FONT_ROLES.includes(f.fontRole) ? f.fontRole : null,
      fontSize: Math.max(8, Math.round(num(f.fontSize, 40))),
      bold: f.bold !== false && !!f.bold,
      align: ['left', 'center', 'right'].includes(f.align) ? f.align : 'left',
      uppercase: !!f.uppercase, lineHeight: num(f.lineHeight, 1), letterSpacing: num(f.letterSpacing, 0),
    }
  }
  const fields = []
  for (const f of fieldsIn.slice(0, 80)) {
    if (!f || typeof f !== 'object') continue
    const bind = bindFromToken(f.token)
    fields.push({ token: String(f.token || ''), bind, ...look(f) })
    if (!bind) warnings.push(`“{{${f.token}}}” is not a field BetterCricket knows, so it stays as the text it is.`)
  }
  const texts = []
  for (const t of (Array.isArray(doc.texts) ? doc.texts : []).slice(0, 40)) {
    if (!t || typeof t !== 'object' || typeof t.text !== 'string' || !t.text.trim()) continue
    texts.push({ text: t.text.slice(0, 500), ...look(t) })
  }
  const panels = []
  for (const p of (Array.isArray(doc.panels) ? doc.panels : []).slice(0, 10)) {
    if (!p || typeof p !== 'object') continue
    const pw = Math.round(num(p.w, 0)), ph = Math.round(num(p.h, 0))
    if (pw < 20 || ph < 20) continue
    panels.push({
      x: Math.round(num(p.x, 0)), y: Math.round(num(p.y, 0)), w: pw, h: ph,
      hex: HEX.test(p.color || '') ? p.color.toLowerCase() : null,
      source: ['solid', 'picture', 'shape'].includes(p.source) ? p.source : 'picture',
      // A picture the panel carries (kept as a picture, positioned by its own box and turn).
      image: typeof p.image === 'string' ? p.image : null,
      box: p.box && typeof p.box === 'object' && Number(p.box.w) >= 20 && Number(p.box.h) >= 20
        ? { x: Math.round(num(p.box.x, 0)), y: Math.round(num(p.box.y, 0)), w: Math.round(num(p.box.w, 0)), h: Math.round(num(p.box.h, 0)), rotation: Math.round(num(p.box.rotation, 0)) }
        : null,
      imageUrl: null,
    })
  }
  const w = num(doc.canvas && doc.canvas.w, 1080), h = num(doc.canvas && doc.canvas.h, 1080)
  const postType = doc.postType === 'lineup' ? 'lineup' : 'general'
  if (postType === 'lineup' && !fields.some((f) => /^lineup\./.test(f.bind || ''))) {
    warnings.push('This is marked as a line up but has no player places, so nothing will fill from the players you add. In Canva, type {{player 1}}, {{player 2}} and so on.')
  }
  return {
    postType,
    name: String(doc.name || 'Imported template').slice(0, 80),
    canvas: { w, h }, background: typeof doc.background === 'string' ? doc.background : null,
    fields, texts, panels, warnings,
  }
}

// A font BetterPosts does not have is only a problem where the designer's font name
// is the one used: when the club keeps the Canva look, or a file carries no font role
// (an older one). Where the club's own font fills in, the name is never used.
export function templateWarnings(parsed, { clubStyle = true } = {}) {
  const out = [...parsed.warnings]
  for (const f of [...parsed.fields, ...parsed.texts]) {
    const nameIsUsed = !clubStyle || !f.fontRole
    if (nameIsUsed && f.fontName && !f.font) out.push(`The font “${f.fontName}” is not in BetterPosts, so “${f.token || f.text}” uses Inter.`)
  }
  return out
}

// The blocks for a parsed template: the design at the back, the fixed words, then a
// text block per field. `clubStyle` (default) fills the look from the club's own
// palette and fonts through roles; off keeps the designer's colours and fonts.
// `bind` is absent on a field that is not one (plain text).
export function itemsFromTemplate(parsed, { designUrl, designName, width, height, keep = [], clubStyle = true }) {
  const colorOf = (f) => (clubStyle && f.colorRole ? f.colorRole : (f.hex || 'ink'))
  const fontOf = (f) => {
    if (clubStyle && f.fontRole) return (fontByKey(f.fontRole === 'display' ? 'club' : 'inter') || fontByKey('inter')).family
    return (f.font || fontByKey('inter')).family
  }
  const make = (text, f) => newBlankItem('text', {
    text, x: f.x, y: f.y, w: f.w, fontFamily: fontOf(f), fontSize: f.fontSize, bold: f.bold,
    color: colorOf(f), align: f.align, lineHeight: f.lineHeight, letterSpacing: f.letterSpacing, uppercase: f.uppercase,
  })
  // A panel is a plain rectangle in the club's accent, kept faint so the text on it
  // reads in light or dark mode alike. Keeping the Canva look uses the designer's
  // colour, but only where the panel was a solid colour (a picture's colour is not known).
  const panelItems = parsed.panels.map((p) => {
    // A panel that brought its own picture (and the editor kept it) is that picture, as designed.
    if (p.imageUrl && p.box) {
      return {
        ...newBlankItem('image', { src: p.imageUrl, srcName: `${parsed.name} panel`, x: p.box.x, y: p.box.y, w: p.box.w, h: p.box.h, fit: 'cover' }),
        rotation: p.box.rotation, fromTemplate: true,
      }
    }
    const own = !clubStyle && p.hex
    return {
      ...newBlankItem('element', { shape: 'rect' }),
      x: p.x, y: p.y, w: p.w, h: p.h,
      color: own ? p.hex : 'accent', opacity: own ? 1 : PANEL_TINT, fill: true, radius: 0,
      fromTemplate: true,
    }
  })
  const fixed = parsed.texts.map((t) => ({ ...make(t.text, t), fromTemplate: true }))
  const fields = parsed.fields.map((f) => ({
    ...make(f.bind ? bindLabel(f.bind).toUpperCase() : f.token, f),
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
  return [...base, ...panelItems, ...fixed, ...fields]
}
