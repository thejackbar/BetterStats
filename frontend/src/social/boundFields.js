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
//     "pictures": [ { "image": "data:...", "box": {x,y,w,h,rotation} } ]   // pictures nothing is written on, e.g. a cut-out player
//   }
//
// STRUCTURE FIRST. By default an import uses the roles, not the designer's own
// values: a colour role becomes a palette token (so the club's palette tints it and
// a palette switch re-tints it) and a font role becomes the post font (the club font,
// or whichever the club picks under Brand). The designer's colour and font name are kept in the file for a club that
// chooses "keep my Canva look". A panel is drawn as a rectangle behind the text, tinted
// with the club's accent (a flat copy of a picture's colour cannot be known).
//
// Tokens (case and spacing do not matter; an unknown one is kept as plain text
// and reported, never guessed):
//   player N | player N first | player N last | player N role   N = 1 to LINEUP_MAX
//   player N photo        a picture area bound to that player's photo (h is the area's height)
//   club logo | opponent logo   the crests (areas); aliases logo, crest, badge, opposition logo
//   photo                 the featured photo (the Hero Image panel's player or upload)
//   player N captain | vice | keeper | debut   print C, VC, WK or DEBUT when the player is one
//                          (without any of these, names carry (C), (WK) and DEBUT by themselves)
//   sponsors              a sponsors area (h is the area's height)
//   captain | vice | keeper | opponent | team | headline
//   competition | round | venue | date | time | season
import { newBlankItem, withDesign, BLANK_FONTS, BLANK_STARTERS } from './blank-template'
import { bindFromToken, bindLabel, isAreaBind } from './boundResolve'

// How much of the club's accent a panel carries: enough to show, not enough to fight the text.
export const PANEL_TINT = 0.22
const COLOR_ROLES = ['ink', 'accent', 'primary', 'secondary', 'white', 'black']
const FONT_ROLES = ['display', 'body']
const fontByKey = (key) => BLANK_FONTS.find((x) => x.key === key)
export { bindFromToken, bindLabel, resolveBind, boundSlotCount, isBoundPlayerSlot, isAreaBind, LINEUP_SLOTS } from './boundResolve'

export const FORMAT = 'bettercricket-template'

const norm = (s) => String(s || '').toLowerCase().replace(/[{}]/g, '').replace(/\s+/g, ' ').trim()

// A design tool names its fonts however it likes. Match on the font's name; a
// font the editor does not carry falls back to the post font and is reported.
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
      // Only an area (a photo, the sponsors) has a height of its own; text grows to fit.
      h: Math.max(0, Math.round(num(f.h, 0))),
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
  // Pictures on the design that no words sit on (a cut-out player, a logo): each with its own box and turn.
  const pictures = []
  for (const p of (Array.isArray(doc.pictures) ? doc.pictures : []).slice(0, 8)) {
    if (!p || typeof p !== 'object' || typeof p.image !== 'string' || !p.box || Number(p.box.w) < 20 || Number(p.box.h) < 20) continue
    pictures.push({
      image: p.image, imageUrl: null,
      box: { x: Math.round(num(p.box.x, 0)), y: Math.round(num(p.box.y, 0)), w: Math.round(num(p.box.w, 0)), h: Math.round(num(p.box.h, 0)), rotation: Math.round(num(p.box.rotation, 0)) },
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
    fields, texts, panels, pictures, warnings,
  }
}

// A font BetterPosts does not have is only a problem where the designer's font name
// is the one used: when the club keeps the Canva look, or a file carries no font role
// (an older one). Where the club's own font fills in, the name is never used. One line
// per missing font, saying how many pieces of text fall back to the post font.
export function templateWarnings(parsed, { clubStyle = true } = {}) {
  const out = [...parsed.warnings]
  const missing = new Map()
  for (const f of [...parsed.fields, ...parsed.texts]) {
    const nameIsUsed = (!clubStyle || !f.fontRole) && !isAreaBind(f.bind)
    if (nameIsUsed && f.fontName && !f.font) missing.set(f.fontName, (missing.get(f.fontName) || 0) + 1)
  }
  for (const [name, n] of missing) {
    out.push(`The font “${name}” is only in Canva, so ${n} piece${n === 1 ? '' : 's'} of text use${n === 1 ? 's' : ''} the post font instead. Change the post font under Brand, or use a font BetterPosts has.`)
  }
  return out
}

// The blocks for a parsed template: the design at the back, the fixed words, then a
// text block per field. `clubStyle` (default) fills the look from the club's own
// palette and fonts through roles; off keeps the designer's colours and fonts.
// `bind` is absent on a field that is not one (plain text).
export function itemsFromTemplate(parsed, { designUrl, designName, width, height, keep = [], clubStyle = true }) {
  const colorOf = (f) => (clubStyle && f.colorRole ? f.colorRole : (f.hex || 'ink'))
  // The post font (Design, Font) fills every role, so changing it restyles the whole
  // template. A Canva font BetterPosts does not have falls back to it as well.
  const fontOf = (f) => {
    if (clubStyle && f.fontRole) return fontByKey('club').family
    return (f.font || fontByKey('club')).family
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
  // Free-standing pictures stay pictures, drawn under the words, at their own place and turn.
  const pictureItems = (parsed.pictures || []).filter((p) => p.imageUrl).map((p) => ({
    ...newBlankItem('image', { src: p.imageUrl, srcName: `${parsed.name} picture`, x: p.box.x, y: p.box.y, w: p.box.w, h: p.box.h, fit: 'cover' }),
    rotation: p.box.rotation, fromTemplate: true,
  }))
  const fixed = parsed.texts.map((t) => ({ ...make(t.text, t), fromTemplate: true }))
  // Marks come after names on their own, unless the template placed marks itself.
  const placedMarks = parsed.fields.some((f) => /^lineup\.\d+\.(captain|vice|keeper|debut)$/.test(f.bind || ''))
  const fields = parsed.fields.map((f) => {
    // A photo or the sponsors is an area, not words: it takes the box the designer drew.
    if (f.bind === 'sponsors') {
      return {
        ...newBlankItem('sponsors', { x: f.x, y: f.y, w: f.w, h: f.h || Math.round(f.w * 0.2), panel: 'light' }),
        // Follows the sponsors the club has chosen for the post, without moving.
        followDefault: true, fromTemplate: true,
      }
    }
    if (isAreaBind(f.bind)) {
      // A photo fills its box; a crest keeps its shape.
      return { ...newBlankItem('image', { x: f.x, y: f.y, w: f.w, h: f.h || f.w, fit: /^logo\./.test(f.bind) ? 'contain' : 'cover' }), bind: f.bind, fromTemplate: true }
    }
    return {
      ...make(f.bind ? bindLabel(f.bind).toUpperCase() : f.token, f),
      // Every block an import makes is marked, including a word that is not a field,
      // so importing again replaces exactly these and leaves the club's own blocks.
      fromTemplate: true,
      ...(f.bind ? { bind: f.bind } : null),
      ...(!placedMarks && /^lineup\.\d+\.(name|last)$/.test(f.bind || '') ? { autoMarks: true } : null),
    }
  })
  // Whatever the club put on top before stays, except an earlier import's own
  // fields and design (so importing the same template again updates it) and the
  // editor's own starter blocks when nobody has touched them, which would only
  // sit over the template. One block the club added or edited keeps everything.
  const own = keep.filter((it) => !it.fromTemplate && !it.design && it.type !== 'sponsors')
  const sig = (it) => [it.type, it.x, it.y, it.w, it.size, it.text].join('|')
  const untouched = BLANK_STARTERS.some((st) => { const b = st.build(); return b.length === own.length && b.every((x, i) => sig(x) === sig(own[i])) })
  // The editor's own sponsor band is not the template's: it goes, and so does any sponsor grid
  // when the template has a sponsors box of its own.
  const hasSponsorBox = parsed.fields.some((f) => f.bind === 'sponsors')
  const others = keep.filter((it) => !it.fromTemplate && !it.design && !(untouched && own.includes(it)) && !(it.type === 'sponsors' && (it.auto || hasSponsorBox)))
  const base = designUrl ? withDesign(others, designUrl, designName, width, height) : [...keep.filter((it) => it.design), ...others]
  return [...base, ...panelItems, ...pictureItems, ...fixed, ...fields]
}
