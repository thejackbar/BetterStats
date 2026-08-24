// Taking a piece of the meeting away as a document.
//
// The minutes and the secretary's own notes are plain text in a box, and a club
// routinely needs them OUT of here — circulated to a committee, filed with the
// association, printed for the folder somebody keeps. Word and PDF are what
// those people actually open.
//
// BOTH ARE WRITTEN IN THE BROWSER FROM WHAT IS ON SCREEN, not fetched back from
// the server, so a download always carries the last keystroke rather than
// whatever the 700ms autosave last managed to send. Downloading the minutes a
// second after typing the final sentence must not hand back the version without
// it.
//
// No library, deliberately. A .docx is a zip of three XML parts and a PDF is a
// handful of objects and a table of byte offsets; a document toolkit would cost
// more to carry than this whole file, which is ~250 lines and has no network,
// no fonts to ship and nothing to keep in step with a release.

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
function para(text, { bold = false, size = null, after = 0, colour = null } = {}) {
  const rPr = (bold || size || colour)
    ? `<w:rPr>${bold ? '<w:b/>' : ''}${size ? `<w:sz w:val="${size}"/><w:szCs w:val="${size}"/>` : ''}${colour ? `<w:color w:val="${colour}"/>` : ''}</w:rPr>`
    : ''
  // An empty paragraph is how a blank line in the box survives the trip.
  const run = text ? `<w:r>${rPr}<w:t xml:space="preserve">${xml(text)}</w:t></w:r>` : ''
  return `<w:p><w:pPr><w:spacing w:after="${after}"/></w:pPr>${run}</w:p>`
}

export function downloadDocx({ filename, title, subtitle, body }) {
  const paras = [
    para(title, { bold: true, size: 32, after: subtitle ? 40 : 200 }),
    ...(subtitle ? [para(subtitle, { size: 19, colour: '595959', after: 200 })] : []),
    // Each line of the box becomes its own paragraph, so the text reads in Word
    // exactly as it is laid out on screen.
    ...String(body || '').split('\n').map(line => para(line, { size: 22 })),
  ]

  const document = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${paras.join('')}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>`

  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`

  const rels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`

  const docRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>`

  const bytes = zip([
    // [Content_Types].xml goes first, which is what a reader expects to meet.
    { name: '[Content_Types].xml', data: enc.encode(contentTypes) },
    { name: '_rels/.rels', data: enc.encode(rels) },
    { name: 'word/_rels/document.xml.rels', data: enc.encode(docRels) },
    { name: 'word/document.xml', data: enc.encode(document) },
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

function winAnsi(ch) {
  const c = ch.codePointAt(0)
  if (c === 9) return 32
  if (c >= 32 && c <= 126) return c
  if (WINANSI[c] != null) return WINANSI[c]
  if (c >= 160 && c <= 255) return c
  return 63
}

function textWidth(s, size, bold) {
  let w = 0
  for (const ch of s) {
    const c = winAnsi(ch)
    w += (c >= 32 && c <= 126) ? HELVETICA[c - 32] : 556
  }
  // Helvetica-Bold runs a little wider than the table above; the title is the
  // only bold line, so an approximation is enough to keep it inside the margin.
  return (w * size / 1000) * (bold ? 1.06 : 1)
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

function pdfString(s) {
  const out = [0x28]
  for (const ch of s) {
    const c = winAnsi(ch)
    if (c === 0x28 || c === 0x29 || c === 0x5C) out.push(0x5C)
    out.push(c)
  }
  out.push(0x29)
  return out
}

const ascii = s => Array.from(enc.encode(s))

export function downloadPdf({ filename, title, subtitle, body }) {
  const PAGE_W = 595.28, PAGE_H = 841.89, MARGIN = 56
  const maxWidth = PAGE_W - MARGIN * 2
  const BODY_SIZE = 11

  const lines = [
    ...wrapLine(title, 16, maxWidth, true).map(text => ({ text, size: 16, bold: true, after: subtitle ? 3 : 10 })),
    ...(subtitle ? wrapLine(subtitle, 9.5, maxWidth, false).map(text => ({ text, size: 9.5, grey: true, after: 10 })) : []),
    ...String(body || '').split('\n').flatMap(raw =>
      wrapLine(raw, BODY_SIZE, maxWidth, false).map(text => ({ text, size: BODY_SIZE }))),
  ]

  // Paged before anything is drawn, so the page objects and their content
  // streams are built from one agreed layout.
  const pages = [[]]
  let y = PAGE_H - MARGIN
  for (const line of lines) {
    const height = line.size * 1.42 + (line.after || 0)
    if (y - height < MARGIN && pages[pages.length - 1].length) {
      pages.push([])
      y = PAGE_H - MARGIN
    }
    pages[pages.length - 1].push({ ...line, baseline: y - line.size * 1.05 })
    y -= height
  }

  const streams = pages.map(page => {
    let ops = []
    for (const line of page) {
      if (!line.text) continue
      const font = line.bold ? '/F2' : '/F1'
      if (line.grey) ops = ops.concat(ascii('0.42 0.42 0.42 rg\n'))
      ops = ops.concat(ascii(`BT ${font} ${line.size} Tf ${MARGIN.toFixed(2)} ${line.baseline.toFixed(2)} Td `))
      ops = ops.concat(pdfString(line.text))
      ops = ops.concat(ascii(' Tj ET\n'))
      if (line.grey) ops = ops.concat(ascii('0 g\n'))
    }
    return new Uint8Array(ops)
  })

  // 1 catalog, 2 pages, 3 Helvetica, 4 Helvetica-Bold, 5 info, then a page
  // object and a content object per page.
  const firstPage = 6
  const pageIds = pages.map((_, i) => firstPage + i * 2)
  const bodies = []
  const put = (n, data) => { bodies[n] = data instanceof Uint8Array ? data : enc.encode(data) }

  put(1, '<< /Type /Catalog /Pages 2 0 R >>')
  put(2, `<< /Type /Pages /Kids [${pageIds.map(n => `${n} 0 R`).join(' ')}] /Count ${pages.length} >>`)
  put(3, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
  put(4, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>')
  put(5, new Uint8Array([...ascii('<< /Title '), ...pdfString(title || ''), ...ascii(' /Producer (BetterCricket) >>')]))

  pages.forEach((_, i) => {
    const id = pageIds[i]
    put(id, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_W} ${PAGE_H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${id + 1} 0 R >>`)
    put(id + 1, new Uint8Array([
      ...ascii(`<< /Length ${streams[i].length} >>\nstream\n`),
      ...streams[i],
      ...ascii('\nendstream'),
    ]))
  })

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
