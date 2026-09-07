// Taking a piece of the meeting away as a document.
//
// The minutes and the secretary's own notes are plain text in a box, and a club
// routinely needs them OUT of here — circulated to a committee, filed with the
// association, printed for the folder somebody keeps. Word and PDF are what
// those people actually open.
//
// BOTH ARE WRITTEN IN THE BROWSER FROM WHAT IS ON SCREEN, not fetched back from
// the server, so a download always carries the last keystroke rather than
// whatever the 700ms autosave last managed to send.
//
// No library, deliberately. A .docx is a zip of three XML parts and a PDF is a
// handful of objects and a table of byte offsets; a document toolkit would cost
// more to carry than this file, which has no network, no fonts to ship and
// nothing to keep in step with a release.
//
// A CALLER HANDS OVER BLOCKS, NOT A STRING. Minutes are a structured document —
// a details table, a numbered section per agenda item, an actions table — and a
// textarea's worth of plain text cannot express any of that. `blocks` is that
// structure; `body` is still accepted for the plain-text case (the secretary's
// own notes), and is turned into paragraphs.

const enc = new TextEncoder()

function u16(n) { return new Uint8Array([n & 255, (n >>> 8) & 255]) }
function u32(n) { return new Uint8Array([n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255]) }

function concat(chunks) {
  let len = 0
  for (const c of chunks) len += c.length
  const out = new Uint8Array(len)
  let at = 0
  for (const c of chunks) { out.set(c, at); at += c.length }
  return out
}

function save(bytes, mime, filename) {
  const url = URL.createObjectURL(new Blob([bytes], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Revoked on a delay: Safari has been known to cancel a download whose object
  // URL is released in the same tick as the click.
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

// A filename a person reads, with the characters no filesystem wants taken out.
export function docFilename(...parts) {
  const name = parts.filter(Boolean).join(' - ')
    .replace(/[\\/:*?"<>|]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return name || 'document'
}

// Plain text becomes one paragraph per line, so a blank line survives the trip.
const textBlocks = (body) => String(body || '').split('\n').map(text => ({ type: 'para', text }))

// `header` is whatever sits ABOVE the title — the club's colour band and its
// crest. It is a separate argument rather than the head of `blocks` because
// `title` is ALSO the PDF's own /Info Title, so the caller has to keep passing
// it as a string; emitting a title block itself would print the club name
// twice.
function docBlocks({ title, subtitle, body, blocks, header }) {
  const out = []
  out.push(...(header || []))
  if (title) out.push({ type: 'title', text: title })
  if (subtitle) out.push({ type: 'subtitle', text: subtitle })
  out.push(...(blocks && blocks.length ? blocks : textBlocks(body)))
  return out
}

/* ── a club's own colours and crest ──────────────────────────────────────── */

// #RGB or #RRGGBB → 'RRGGBB' upper case, or null. Word wants the bare six
// characters and the PDF wants the three components, so both readers work off
// this one parse rather than each doing their own.
export function hex6(v) {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(v || '').trim())
  if (!m) return null
  const h = m[1]
  return (h.length === 3 ? h.split('').map(c => c + c).join('') : h).toUpperCase()
}

const rgb01 = (h) => [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255)

// A club crest, ready to embed, or null.
//
// JPEG, NOT the original file, and that is the whole reason this exists: a JPEG
// goes into a PDF verbatim under /DCTDecode and into a .docx as an ordinary
// media part, whereas a PNG would need its own decoder here to become either.
// The canvas does the decoding the browser already knows how to do.
//
// THE CANVAS IS FILLED WHITE FIRST. A club crest is almost always a
// transparent PNG and JPEG has no alpha, so without it every logo lands as a
// black box on a white page.
//
// Returns null rather than throwing on anything that can go wrong — a crest
// that will not load, an external URL that taints the canvas, a club with no
// logo at all. The document is still worth having without it.
export function clubLogoJpeg(url, { maxWidth = 260, maxHeight = 90 } = {}) {
  if (!url) return Promise.resolve(null)
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onerror = () => resolve(null)
    img.onload = () => {
      try {
        const nw = img.naturalWidth || img.width
        const nh = img.naturalHeight || img.height
        if (!nw || !nh) return resolve(null)
        // Rendered at 3x the printed size so the crest is not soft in print,
        // then placed at maxWidth/maxHeight points by the two writers.
        const scale = Math.min(maxWidth / nw, maxHeight / nh, 1) * 3
        const w = Math.max(1, Math.round(nw * scale))
        const h = Math.max(1, Math.round(nh * scale))
        const canvas = document.createElement('canvas')
        canvas.width = w
        canvas.height = h
        const ctx = canvas.getContext('2d')
        ctx.fillStyle = '#ffffff'
        ctx.fillRect(0, 0, w, h)
        ctx.drawImage(img, 0, 0, w, h)
        const data = canvas.toDataURL('image/jpeg', 0.92)
        const b64 = data.slice(data.indexOf(',') + 1)
        const bin = atob(b64)
        const bytes = new Uint8Array(bin.length)
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
        resolve({ jpeg: bytes, width: w, height: h, ptWidth: w / 3, ptHeight: h / 3 })
      } catch {
        // A tainted canvas (a crest served from another origin with no CORS
        // header) throws on toDataURL. No crest is a better document than none.
        resolve(null)
      }
    }
    img.src = url
  })
}

/* ── zip, stored ─────────────────────────────────────────────────────────── */

const CRC_TABLE = (() => {
  const t = new Uint32Array(256)
  for (let i = 0; i < 256; i++) {
    let c = i
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1
    t[i] = c >>> 0
  }
  return t
})()

function crc32(bytes) {
  let c = 0xFFFFFFFF
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8)
  return (c ^ 0xFFFFFFFF) >>> 0
}

// Entries are STORED rather than deflated. Word accepts either, the parts are a
// few kilobytes of XML, and storing them means no compressor to carry.
function zip(entries) {
  const now = new Date()
  const time = ((now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1)) & 0xFFFF
  const date = (((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate()) & 0xFFFF

  const local = []
  const central = []
  let offset = 0

  for (const e of entries) {
    const name = enc.encode(e.name)
    const crc = crc32(e.data)
    const head = concat([
      u32(0x04034b50), u16(20), u16(0), u16(0), u16(time), u16(date),
      u32(crc), u32(e.data.length), u32(e.data.length), u16(name.length), u16(0),
    ])
    local.push(head, name, e.data)
    central.push(concat([
      u32(0x02014b50), u16(20), u16(20), u16(0), u16(0), u16(time), u16(date),
      u32(crc), u32(e.data.length), u32(e.data.length),
      u16(name.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(offset),
    ]), name)
    offset += head.length + name.length + e.data.length
  }

  const dir = concat(central)
  return concat([
    ...local, dir,
    concat([
      u32(0x06054b50), u16(0), u16(0), u16(entries.length), u16(entries.length),
      u32(dir.length), u32(offset), u16(0),
    ]),
  ])
}

/* ── .docx ───────────────────────────────────────────────────────────────── */

const xml = s => String(s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // A control character is not legal XML at all and would make Word refuse the
  // whole document rather than skip the character.
  .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '')

// `w:sz` is HALF-points, so 32 reads as 16pt. `w:spacing w:after` is twentieths
// of a point, so 120 is 6pt.
// Arial throughout, named on every run. Word's own default is whatever the
// reader's template says, so the face has to be stated rather than assumed.
const FONT = '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>'

function run(text, { bold, size, colour, italic } = {}) {
  const rPr = `<w:rPr>${FONT}${bold ? '<w:b/>' : ''}${italic ? '<w:i/>' : ''}`
    + `${size ? `<w:sz w:val="${size}"/><w:szCs w:val="${size}"/>` : ''}`
    + `${colour ? `<w:color w:val="${colour}"/>` : ''}</w:rPr>`
  return `<w:r>${rPr}<w:t xml:space="preserve">${xml(text)}</w:t></w:r>`
}

function para(text, { bold, size, after = 0, before = 0, colour, italic, indent = 0, align } = {}) {
  const pPr = `<w:pPr>${align ? `<w:jc w:val="${align}"/>` : ''}`
    + `${indent ? `<w:ind w:left="${indent}"/>` : ''}`
    + `<w:spacing${before ? ` w:before="${before}"` : ''} w:after="${after}"/></w:pPr>`
  // An empty paragraph is how a blank line in the box survives the trip.
  return `<w:p>${pPr}${text ? run(text, { bold, size, colour, italic }) : ''}</w:p>`
}

const CELL_PAD = '<w:tcMar><w:top w:w="60" w:type="dxa"/><w:left w:w="90" w:type="dxa"/>'
  + '<w:bottom w:w="60" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tcMar>'
const BORDER = '<w:tblBorders>'
  + ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']
    .map(s => `<w:${s} w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>`).join('')
  + '</w:tblBorders>'

// A4 inside 2cm margins is 9638 twips of usable width.
const TABLE_WIDTH = 9638

function table(block) {
  const cols = Math.max(1, (block.header || block.rows[0] || []).length)
  const weights = block.widths && block.widths.length === cols ? block.widths : Array(cols).fill(1)
  const total = weights.reduce((a, b) => a + b, 0)
  const widths = weights.map(w => Math.round(TABLE_WIDTH * w / total))

  const cell = (text, { bold, shaded } = {}) =>
    `<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/>`
    + `${shaded ? '<w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>' : ''}${CELL_PAD}</w:tcPr>`
    + String(text ?? '').split('\n').map(line => para(line, { size: 19, bold })).join('')
    + `</w:tc>`

  const row = (cells, opts) => `<w:tr>${cells.map(c => cell(c, opts)).join('')}</w:tr>`
  return `<w:tbl><w:tblPr><w:tblW w:w="${TABLE_WIDTH}" w:type="dxa"/>${BORDER}</w:tblPr>`
    + `<w:tblGrid>${widths.map(w => `<w:gridCol w:w="${w}"/>`).join('')}</w:tblGrid>`
    + (block.header ? row(block.header, { bold: true, shaded: true }) : '')
    + block.rows.map(r => row(r)).join('')
    + `</w:tbl>${para('', { after: 80 })}`
}

// The club's colour band.
//
// A SHADED PARAGRAPH, NEVER A TABLE. A one-row table would let each half carry
// its own fill and is the obvious way to draw a two-colour band — and it puts a
// structure into the document that is not a table: Word counts it, a reader
// announces it, and anything walking the document's tables meets a band before
// it meets the meeting details. Two stacked single-colour paragraphs give the
// club both of its colours with none of that, and the PDF draws the identical
// pair of rectangles.
//
// `w:line` with `lineRule="exact"` is what sets the height — twentieths of a
// point, like every other spacing value here — and the tiny `w:sz` stops the
// run's own font from forcing the paragraph taller than the band.
function bandDocx(b) {
  const fill = hex6(b.colour)
  if (!fill) return ''
  const h = Math.max(20, Math.round((b.height ?? 8) * 20))
  return `<w:p><w:pPr><w:shd w:val="clear" w:color="auto" w:fill="${fill}"/>`
    + `<w:spacing w:before="0" w:after="${b.after ?? 0}" w:line="${h}" w:lineRule="exact"/>`
    + `<w:rPr>${FONT}<w:sz w:val="2"/></w:rPr></w:pPr></w:p>`
}

// An inline image, centred. EMU are 12700 to the point, which is the unit every
// size in a <w:drawing> is given in.
const EMU = 12700

function imageDocx(b, rid) {
  const cx = Math.round((b.ptWidth || 1) * EMU)
  const cy = Math.round((b.ptHeight || 1) * EMU)
  return `<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:after="${b.after ?? 100}"/></w:pPr><w:r>`
    + `<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">`
    + `<wp:extent cx="${cx}" cy="${cy}"/><wp:docPr id="${rid}" name="Club crest"/>`
    + `<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">`
    + `<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">`
    + `<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">`
    + `<pic:nvPicPr><pic:cNvPr id="${rid}" name="Club crest"/><pic:cNvPicPr/></pic:nvPicPr>`
    + `<pic:blipFill><a:blip r:embed="rId${rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>`
    + `<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm>`
    + `<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>`
    + `</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>`
}

function blockToDocx(b, ctx) {
  switch (b.type) {
    case 'band': return bandDocx(b)
    case 'image': {
      // Registered here rather than in a pre-pass, so an image block that never
      // reaches the document never mints a relationship pointing at a media
      // part that does not exist.
      if (!b.jpeg || !ctx) return ''
      const rid = ctx.images.push(b) + 100
      return imageDocx(b, rid)
    }
    case 'title':
      return String(b.text).split('\n')
        .map(t => para(t, { bold: true, size: 34, after: 40, align: 'center' })).join('')
    case 'subtitle':
      return String(b.text).split('\n')
        .map(t => para(t, { size: 20, colour: '595959', after: 60, align: 'center' })).join('')
    // A BLANK LINE EITHER SIDE of a heading and of a MOTION / ACTION label.
    // `w:spacing` is twentieths of a point and the body runs at 10.5pt, so ~240
    // is one clear line. The PDF path states the same thing as explicit gaps.
    case 'heading': return para(b.text, { bold: true, size: 26, before: 240, after: 200, colour: '1F3864' })
    case 'label':
      return para(b.text, { bold: true, size: 19, colour: '595959', before: 220, after: 160, indent: b.indent || 0 })
    case 'bullets':
      return (b.items || []).map(t => para(`•  ${t}`, { size: 21, after: 20, indent: 340 })).join('')
    case 'table': return table(b)
    case 'spacer': return para('', { after: b.after ?? 120 })
    case 'para':
    default:
      return para(b.text, {
        size: 21, after: b.after ?? 80, italic: b.italic,
        colour: b.muted ? '595959' : undefined, indent: b.indent || 0,
      })
  }
}

export function downloadDocx({ filename, title, subtitle, body, blocks, header }) {
  const ctx = { images: [] }
  const parts = docBlocks({ title, subtitle, body, blocks, header }).map(b => blockToDocx(b, ctx)).join('')

  // The drawing namespaces are declared on <w:document> whether or not an image
  // is present: Word reads the root element's declarations, and a namespace
  // used by a part it has already begun parsing cannot be introduced later.
  const document = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"><w:body>${parts}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>`

  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>${ctx.images.length ? '<Default Extension="jpeg" ContentType="image/jpeg"/>' : ''}<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`

  const rels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`

  const docRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${ctx.images.map((_, i) =>
    `<Relationship Id="rId${i + 101}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image${i + 1}.jpeg"/>`).join('')}</Relationships>`

  const bytes = zip([
    // [Content_Types].xml goes first, which is what a reader expects to meet.
    { name: '[Content_Types].xml', data: enc.encode(contentTypes) },
    { name: '_rels/.rels', data: enc.encode(rels) },
    { name: 'word/_rels/document.xml.rels', data: enc.encode(docRels) },
    { name: 'word/document.xml', data: enc.encode(document) },
    ...ctx.images.map((img, i) => ({ name: `word/media/image${i + 1}.jpeg`, data: img.jpeg })),
  ])

  save(bytes, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', `${filename}.docx`)
}

/* ── pdf ─────────────────────────────────────────────────────────────────── */

// Helvetica advance widths, per 1000 units, for the printable ASCII range. This
// is what makes the wrapping land where the text actually ends rather than at a
// guessed character count.
const HELVETICA = [
  278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
  556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
  1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
  667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
  333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
  556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]

// Helvetica-Bold, which Arial Bold matches. The bold face is genuinely wider
// per glyph, so a heading or a table header measured off the regular table and
// nudged by a flat percentage lands in the wrong place.
const HELVETICA_BOLD = [
  278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
  556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
  975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
  667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
  333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
  611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
]

// The punctuation a person actually types into minutes — curly quotes off a
// phone keyboard, a dash, an ellipsis — lives in WinAnsi's own 0x80–0x9F block
// rather than at its Unicode code point. Latin-1 above 160 passes straight
// through, and anything else becomes a question mark rather than a broken glyph.
const WINANSI = {
  0x20AC: 0x80, 0x201A: 0x82, 0x0192: 0x83, 0x201E: 0x84, 0x2026: 0x85,
  0x2020: 0x86, 0x2021: 0x87, 0x02C6: 0x88, 0x2030: 0x89, 0x0160: 0x8A,
  0x2039: 0x8B, 0x0152: 0x8C, 0x017D: 0x8E, 0x2018: 0x91, 0x2019: 0x92,
  0x201C: 0x93, 0x201D: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97,
  0x02DC: 0x98, 0x2122: 0x99, 0x0161: 0x9A, 0x203A: 0x9B, 0x0153: 0x9C,
  0x017E: 0x9E, 0x0178: 0x9F,
}
// A character with no WinAnsi slot of its own, folded onto the nearest thing the
// base-14 fonts can actually draw. The breadcrumb separator the plan labels use
// (a heavy angle quote) is the one that matters here.
const FOLD = { 0x276F: 0xBB, 0x276E: 0xAB, 0x2192: 0x3E }

function winAnsi(ch) {
  const c = ch.codePointAt(0)
  if (c === 9) return 32
  if (c >= 32 && c <= 126) return c
  if (WINANSI[c] != null) return WINANSI[c]
  if (FOLD[c] != null) return FOLD[c]
  if (c >= 160 && c <= 255) return c
  return 63
}

const advance = (code, bold) => (code >= 32 && code <= 126)
  ? (bold ? HELVETICA_BOLD : HELVETICA)[code - 32]
  : 556

function textWidth(s, size, bold) {
  let w = 0
  for (const ch of String(s)) w += advance(winAnsi(ch), bold)
  return w * size / 1000
}

// A line's own leading whitespace is kept and re-applied to every row it wraps
// onto, so a hand-indented list in the minutes still reads as a list.
function wrapLine(line, size, maxWidth, bold) {
  const lead = (String(line).match(/^[ \t]*/) || [''])[0].replace(/\t/g, '    ')
  const words = String(line).trim().split(/\s+/).filter(Boolean)
  if (!words.length) return ['']

  const rows = []
  let cur = lead
  for (let word of words) {
    // A single word too long for a line of its own (a pasted URL) is broken by
    // character, or it would overrun the margin silently.
    while (textWidth(lead + word, size, bold) > maxWidth && word.length > 1) {
      let cut = word.length
      while (cut > 1 && textWidth(lead + word.slice(0, cut), size, bold) > maxWidth) cut--
      if (cur.trim()) { rows.push(cur); cur = lead }
      rows.push(lead + word.slice(0, cut))
      word = word.slice(cut)
    }
    const next = cur.trim() ? `${cur} ${word}` : lead + word
    if (cur.trim() && textWidth(next, size, bold) > maxWidth) { rows.push(cur); cur = lead + word }
    else cur = next
  }
  if (cur.trim()) rows.push(cur)
  return rows.length ? rows : ['']
}

const wrapText = (text, size, maxWidth, bold) =>
  String(text ?? '').split('\n').flatMap(l => wrapLine(l, size, maxWidth, bold))

function pdfString(s) {
  const out = [0x28]
  for (const ch of String(s)) {
    const c = winAnsi(ch)
    if (c === 0x28 || c === 0x29 || c === 0x5C) out.push(0x5C)
    out.push(c)
  }
  out.push(0x29)
  return out
}

const ascii = s => Array.from(enc.encode(s))

// WinAnsi runs 32..255, and a simple font's Widths array must cover the whole
// range it declares or a reader falls back to guessing.
function widthsArray(bold) {
  const out = []
  for (let c = 32; c <= 255; c++) out.push(advance(c, bold))
  return out.join(' ')
}

const fontObj = (name, bold, descriptor) =>
  `<< /Type /Font /Subtype /TrueType /BaseFont /${name} /FirstChar 32 /LastChar 255 `
  + `/Widths [${widthsArray(bold)}] /Encoding /WinAnsiEncoding /FontDescriptor ${descriptor} 0 R >>`

// Flags 32 = non-symbolic. The metrics are Arial's own.
const descriptorObj = (name, stemV) =>
  `<< /Type /FontDescriptor /FontName /${name} /Flags 32 /FontBBox [-665 -325 2000 1006] `
  + `/ItalicAngle 0 /Ascent 905 /Descent -212 /CapHeight 716 /StemV ${stemV} >>`

const PAGE_W = 595.28, PAGE_H = 841.89, MARGIN = 56
const COL = PAGE_W - MARGIN * 2

// `indent` on a block is TWIPS, which is what Word takes. A PDF works in
// POINTS, and reading the same number as points is what drew a 10pt Word
// indent as a 200pt one. `indentPt` overrides it where the two formats are
// deliberately set apart.
const pdfIndent = b => Number.isFinite(b.indentPt) ? b.indentPt : (b.indent || 0) / 20

// Every block becomes drawing instructions with their own height, so paging is
// decided once over the whole document rather than per block.
function layout(blocks) {
  const ops = []
  // Variadic: `push(...tableOps(b))` was spreading a whole table into a
  // one-argument helper, so every table drew its first row and silently
  // dropped the rest.
  const push = (...o) => ops.push(...o)

  for (const b of blocks) {
    switch (b.type) {
      case 'title':
        for (const t of wrapText(b.text, 17, COL, true)) push({ kind: 'text', text: t, size: 17, bold: true, centre: true, gap: 3 })
        break
      case 'subtitle':
        for (const t of wrapText(b.text, 10, COL, false)) push({ kind: 'text', text: t, size: 10, grey: true, centre: true, gap: 3 })
        push({ kind: 'gap', height: 12 })
        break
      case 'heading':
        // A blank line ahead of every section heading, and another under it
        // before the section's own first line.
        push({ kind: 'gap', height: 18 })
        for (const t of wrapText(b.text, 13, COL, true)) push({ kind: 'text', text: t, size: 13, bold: true, keepNext: true, gap: 4 })
        push({ kind: 'rule', gap: 14 })
        break
      case 'label':
        // MOTION and ACTION each start a block of their own, so each gets a
        // blank line above it.
        push({ kind: 'gap', height: 11 })
        for (const t of wrapText(b.text, 9, COL - pdfIndent(b), true))
          push({ kind: 'text', text: t, size: 9, bold: true, grey: true, indent: pdfIndent(b), gap: 3 })
        // …and another under it, so the block reads as its own thing rather
        // than as a label stuck to the line beneath.
        push({ kind: 'gap', height: 5 })
        break
      case 'bullets':
        for (const item of (b.items || [])) {
          const rows = wrapText(item, 10.5, COL - 18, false)
          rows.forEach((t, i) => push({
            kind: 'text', text: i === 0 ? `•  ${t}` : `   ${t}`, size: 10.5, indent: 12, gap: 1,
          }))
        }
        push({ kind: 'gap', height: 4 })
        break
      case 'table':
        push(...tableOps(b))
        break
      case 'band':
        if (hex6(b.colour)) {
          push({ kind: 'band', colour: b.colour, height: b.height ?? 8 })
          push({ kind: 'gap', height: (b.after ?? 0) / 20 })
        }
        break
      case 'image':
        if (b.jpeg) {
          push({ kind: 'image', jpeg: b.jpeg, pxWidth: b.width, pxHeight: b.height,
                 height: b.ptHeight || 1, width: b.ptWidth || 1 })
          push({ kind: 'gap', height: (b.after ?? 100) / 20 })
        }
        break
      case 'spacer':
        push({ kind: 'gap', height: b.height ?? 8 })
        break
      case 'para':
      default: {
        const indent = pdfIndent(b)
        const rows = wrapText(b.text, 10.5, COL - indent, false)
        for (const t of rows) push({ kind: 'text', text: t, size: 10.5, grey: b.muted, italic: b.italic, indent, gap: 3 })
        push({ kind: 'gap', height: b.after ?? 7 })
      }
    }
  }
  return ops
}

// A table row is one op carrying every cell's already-wrapped lines, so it can
// be moved to the next page whole rather than split across the break.
function tableOps(b) {
  const cols = Math.max(1, (b.header || b.rows[0] || []).length)
  const weights = b.widths && b.widths.length === cols ? b.widths : Array(cols).fill(1)
  const total = weights.reduce((a, x) => a + x, 0)
  const widths = weights.map(w => COL * w / total)
  const PAD = 4
  const SIZE = 9

  const rowOp = (cells, header) => {
    const lines = cells.map((c, i) => wrapText(c, SIZE, widths[i] - PAD * 2, header))
    const height = Math.max(...lines.map(l => l.length)) * (SIZE * 1.32) + PAD * 2
    return { kind: 'row', lines, widths, height, header, size: SIZE, pad: PAD }
  }

  const ops = []
  if (b.header) ops.push({ ...rowOp(b.header, true), repeat: true })
  for (const r of b.rows) ops.push(rowOp(r, false))
  ops.push({ kind: 'gap', height: 12 })
  return ops
}

export function downloadPdf({ filename, title, subtitle, body, blocks, header }) {
  const ops = layout(docBlocks({ title, subtitle, body, blocks, header }))
  // One XObject per distinct image, collected before paging so every page's
  // /Resources can name them all — a band or a crest is only ever on page one
  // today, but a page whose resources omit an XObject it draws renders blank
  // with no error anywhere.
  const images = []
  const imageMeta = new Map()
  const imageIndex = (op) => {
    let i = images.indexOf(op.jpeg)
    if (i < 0) {
      i = images.push(op.jpeg) - 1
      imageMeta.set(op.jpeg, { pxWidth: op.pxWidth, pxHeight: op.pxHeight })
    }
    return i
  }

  // Paged before anything is drawn. A table header repeats on each page it runs
  // onto, or the columns on page two mean nothing.
  const pages = [[]]
  let y = PAGE_H - MARGIN
  // The table header that repeats onto the next page. Named apart from the
  // document's own `header` blocks (the club band and crest), which appear
  // once, at the top of page one.
  let repeatHeader = null
  const room = (h) => y - h >= MARGIN
  const newPage = () => {
    pages.push([])
    y = PAGE_H - MARGIN
    if (repeatHeader) {
      pages[pages.length - 1].push({ ...repeatHeader, y: y - repeatHeader.height })
      y -= repeatHeader.height
    }
  }

  // Every op has to report a NUMBER here. The rule under a heading carries no
  // font size, so working its height out from `op.size` produced NaN: `room()`
  // was then false for everything after it and `y` never recovered, which put
  // each element on a page of its own, 19 pages for a two-page document.
  const heightOf = (op) => {
    const h = (op.kind === 'row' || op.kind === 'band' || op.kind === 'image') ? op.height
      : op.kind === 'rule' ? (op.gap || 0)
        : (op.size || 0) * 1.32 + (op.gap || 0)
    return Number.isFinite(h) ? h : 0
  }

  for (const op of ops) {
    if (op.kind === 'gap') { y -= op.height || 0; continue }
    if (op.kind === 'row' && op.repeat) repeatHeader = op
    // A table that has finished resets the repeating header.
    if (op.kind !== 'row') repeatHeader = null

    const h = heightOf(op)
    // A heading alone at the foot of a page reads as a mistake, so it moves to
    // the next one with the first lines of its section.
    const need = op.keepNext ? h + 46 : h
    if (!room(need) && pages[pages.length - 1].length) newPage()
    pages[pages.length - 1].push({
      ...op,
      // A row, a band and an image are all boxes drawn from their BOTTOM-left,
      // so each sits a full height below the cursor; a line of text is drawn
      // from its baseline.
      y: (op.kind === 'row' || op.kind === 'band' || op.kind === 'image')
        ? y - op.height
        : y - (op.size || 0) * 1.02,
    })
    y -= h
  }

  const streams = pages.map(page => {
    let s = []
    for (const op of page) {
      if (op.kind === 'rule') {
        s = s.concat(ascii(`0.78 0.78 0.78 RG 0.6 w ${MARGIN} ${(op.y + 3).toFixed(2)} m ${(PAGE_W - MARGIN).toFixed(2)} ${(op.y + 3).toFixed(2)} l S\n`))
        continue
      }
      if (op.kind === 'band') {
        const [r, g, b2] = rgb01(hex6(op.colour))
        s = s.concat(ascii(`${r.toFixed(3)} ${g.toFixed(3)} ${b2.toFixed(3)} rg `
          + `${MARGIN} ${op.y.toFixed(2)} ${COL.toFixed(2)} ${op.height.toFixed(2)} re f\n0 g\n`))
        continue
      }
      if (op.kind === 'image') {
        // `cm` scales the unit square the image is drawn into, so the two
        // numbers are the printed SIZE in points, not the pixel dimensions.
        const w = op.width, h = op.height
        const ix = MARGIN + (COL - w) / 2
        s = s.concat(ascii(`q ${w.toFixed(2)} 0 0 ${h.toFixed(2)} ${ix.toFixed(2)} ${op.y.toFixed(2)} cm `
          + `/Im${imageIndex(op)} Do Q\n`))
        continue
      }
      if (op.kind === 'row') {
        let x = MARGIN
        if (op.header) {
          s = s.concat(ascii(`0.95 0.95 0.95 rg ${MARGIN} ${op.y.toFixed(2)} ${COL.toFixed(2)} ${op.height.toFixed(2)} re f\n`))
        }
        // The cell borders, drawn as a box per column.
        s = s.concat(ascii('0.75 0.75 0.75 RG 0.5 w\n'))
        for (let i = 0; i < op.widths.length; i++) {
          s = s.concat(ascii(`${x.toFixed(2)} ${op.y.toFixed(2)} ${op.widths[i].toFixed(2)} ${op.height.toFixed(2)} re S\n`))
          x += op.widths[i]
        }
        x = MARGIN
        for (let i = 0; i < op.lines.length; i++) {
          let ty = op.y + op.height - op.pad - op.size
          for (const line of op.lines[i]) {
            s = s.concat(ascii(`0 g BT ${op.header ? '/F2' : '/F1'} ${op.size} Tf ${(x + op.pad).toFixed(2)} ${ty.toFixed(2)} Td `))
            s = s.concat(pdfString(line))
            s = s.concat(ascii(' Tj ET\n'))
            ty -= op.size * 1.32
          }
          x += op.widths[i]
        }
        continue
      }
      if (!op.text) continue
      const font = op.bold ? '/F2' : '/F1'
      const x = op.centre
        ? MARGIN + (COL - textWidth(op.text, op.size, op.bold)) / 2
        : MARGIN + (op.indent || 0)
      if (op.grey) s = s.concat(ascii('0.42 0.42 0.42 rg\n'))
      s = s.concat(ascii(`BT ${font} ${op.size} Tf ${x.toFixed(2)} ${op.y.toFixed(2)} Td `))
      s = s.concat(pdfString(op.text))
      s = s.concat(ascii(' Tj ET\n'))
      if (op.grey) s = s.concat(ascii('0 g\n'))
    }
    return new Uint8Array(s)
  })

  // 1 catalog, 2 pages, 3 Arial, 4 Arial Bold, 5 info, 7/8 the font
  // descriptors, then a page object and a content object per page, then one
  // object per embedded image. 6 is deliberately unused so the pair of
  // descriptors can sit together.
  //
  // The image ids come LAST because `images` is only complete once every
  // stream has been written — an image is registered as it is drawn.
  const firstPage = 9
  const pageIds = pages.map((_, i) => firstPage + i * 2)
  const firstImage = firstPage + pages.length * 2
  const xobjects = images.length
    ? `/XObject << ${images.map((_, i) => `/Im${i} ${firstImage + i} 0 R`).join(' ')} >>`
    : ''
  const bodies = []
  const put = (n, data) => { bodies[n] = data instanceof Uint8Array ? data : enc.encode(data) }

  put(1, '<< /Type /Catalog /Pages 2 0 R >>')
  put(2, `<< /Type /Pages /Kids [${pageIds.map(n => `${n} 0 R`).join(' ')}] /Count ${pages.length} >>`)
  // ARIAL, not one of the base-14 aliases. A TrueType font with a descriptor
  // and its own Widths but NO embedded file: a reader uses the Arial it has,
  // and where it has none it substitutes a metrically compatible face. The
  // Widths declared here are the ones the layout above measured with, so the
  // glyphs land where they were positioned either way.
  put(3, fontObj('Arial', false, 7))
  put(4, fontObj('Arial,Bold', true, 8))
  put(5, new Uint8Array([...ascii('<< /Title '), ...pdfString(title || ''), ...ascii(' /Producer (BetterCricket) >>')]))
  put(7, descriptorObj('Arial', 88))
  put(8, descriptorObj('Arial,Bold', 165))

  pages.forEach((_, i) => {
    const id = pageIds[i]
    put(id, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_W} ${PAGE_H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> ${xobjects} >> /Contents ${id + 1} 0 R >>`)
    put(id + 1, new Uint8Array([
      ...ascii(`<< /Length ${streams[i].length} >>\nstream\n`),
      ...streams[i],
      ...ascii('\nendstream'),
    ]))
  })

  // A JPEG goes in verbatim under /DCTDecode — the canvas that produced it
  // always writes a 3-channel baseline image, so /DeviceRGB is exact rather
  // than a guess. This is the whole reason a crest is converted to JPEG before
  // it gets here: a PNG would need its own decoder in this file.
  images.forEach((jpeg, i) => {
    const meta = imageMeta.get(jpeg) || { pxWidth: 1, pxHeight: 1 }
    put(firstImage + i, new Uint8Array([
      ...ascii(`<< /Type /XObject /Subtype /Image /Width ${meta.pxWidth} /Height ${meta.pxHeight} `
        + `/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`),
      ...jpeg,
      ...ascii('\nendstream'),
    ]))
  })

  // Every slot in the object table must exist: the xref is indexed by number,
  // so a hole would make every later offset unreadable.
  if (!bodies[6]) put(6, '<< >>')
  const count = bodies.length - 1
  const chunks = [enc.encode('%PDF-1.4\n')]
  let at = chunks[0].length
  const offsets = []
  for (let n = 1; n <= count; n++) {
    offsets[n] = at
    const part = concat([enc.encode(`${n} 0 obj\n`), bodies[n], enc.encode('\nendobj\n')])
    chunks.push(part)
    at += part.length
  }

  // Every xref row is exactly 20 bytes, which is what makes the table indexable
  // by offset rather than parsed.
  let xref = `xref\n0 ${count + 1}\n0000000000 65535 f \n`
  for (let n = 1; n <= count; n++) xref += `${String(offsets[n]).padStart(10, '0')} 00000 n \n`
  chunks.push(enc.encode(`${xref}trailer\n<< /Size ${count + 1} /Root 1 0 R /Info 5 0 R >>\nstartxref\n${at}\n%%EOF\n`))

  save(concat(chunks), 'application/pdf', `${filename}.pdf`)
}
