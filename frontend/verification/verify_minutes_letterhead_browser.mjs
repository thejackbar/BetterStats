// The club's letterhead on the minutes it circulates — a band in its own
// colours and its crest — against the REAL meeting room with the API stubbed
// at the network layer.
//
// What is asserted, in BOTH formats, because a document that reads as the
// club's in Word and as the platform's in PDF is worse than neither:
//   * the band is drawn in the CLUB'S OWN colours, read out of the file rather
//     than assumed — the primary from `theme_config.accent` and the second
//     rule from `accent2`, never the platform green;
//   * the crest is really embedded: a JPEG media part with a relationship
//     pointing at it and a drawing referencing that relationship in the .docx,
//     and an /XObject image with a /DCTDecode stream that the page's own
//     /Resources names in the .pdf;
//   * THE BAND IS NOT A TABLE. A one-row table is the obvious way to draw one
//     and it puts a structure into the document that is not a table — the
//     meeting details must still be the document's FIRST table;
//   * a club with no crest still gets its band, and no image part is written
//     for a picture that does not exist;
//   * A CREST THAT CANNOT BE READ COSTS THE DOCUMENT NOTHING. The logo route
//     is failed outright and the letterhead still draws, with no image part;
//   * both files still open — the archive is valid and the PDF's xref still
//     points at its own objects, which is what a hand-built image object is
//     most likely to break;
//   * no page errors.
//
//   PW_CHROMIUM=/path/to/chrome node verify_minutes_letterhead_browser.mjs
//   (expects the dev server on :5199)
import { chromium } from 'playwright'
import fs from 'fs'
import { execFileSync } from 'child_process'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const MEETING_ID = 'mtg1'
const MEETING = {
  id: MEETING_ID, title: 'Mid Month', meeting_type: 'committee',
  scheduled_at: '2026-08-10T19:30:00Z', location: 'Clubrooms',
  status: 'in_progress', minutes: '', private_notes: '',
}
// Deliberately NOT the platform green (#16c784) or its blue (#3b82f6): a check
// against the default cannot tell a club's own colour from the fallback.
const ACCENT = '#7B1E3A'          // 7B1E3A → 0.482 0.118 0.227
const ACCENT2 = '#C9A227'         // C9A227 → 0.788 0.635 0.153
const ACCENT_RGB = ['0.482', '0.118', '0.227']
const ACCENT2_RGB = ['0.788', '0.635', '0.153']
const LOGO_URL = '/api/images/organisations/org1/logo'

// A 3x2 PNG, so the crest is a real decodable image with a known aspect ratio
// rather than a byte string the canvas would refuse.
const PNG_3x2 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAYAAACddGYaAAAAFUlEQVR4nGP8z8DwnwEJMOEUGRQyAMR' +
  'HAQlbaLxpAAAAAElFTkSuQmCC', 'base64')

const ATTENDANCE = [
  { member_id: 'm1', full_name: 'Hullett, Mark', status: 'chair' },
  { member_id: 'm2', full_name: 'Bairstow, Hayden', status: 'present' },
]
const MEMBERS = [
  { member_id: 'm1', full_name: 'Hullett, Mark', on_committee: true, position: 'President' },
  { member_id: 'm2', full_name: 'Bairstow, Hayden', on_committee: true, position: null },
]
const AGENDA = [
  { id: 'a1', title: 'Welcome & attendance', status: 'proposed', position: 0, section: null, outcome_notes: '' },
  { id: 'a2', title: "President's report", status: 'proposed', position: 1, section: 'Reports', outcome_notes: '' },
]

const room = (club) => ({
  meeting: MEETING, club,
  agenda_items: AGENDA, motions: [], actions: [],
  attendance: ATTENDANCE, attendee_pool: MEMBERS, previous_attendance: null,
})

const MINUTES_TEXT = "Welcome & attendance\nOpened 7:32pm.\nPresident's report\nThe Chair reported on sponsorship."

const routes = async (page, club, { failLogo = false } = {}) => {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) {
      return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
                    entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } })
    }
    if (/\/committee\/meetings\/[^/]+$/.test(url) && route.request().method() === 'PATCH') return json(MEETING)
    if (/\/committee\/meetings\/[^/?]+\/room/.test(url)) return json(room(club))
    if (/\/committee\/meetings\/[^/?]+(\?|$)/.test(url)) {
      return json({ ...MEETING, agenda_items: [], motions: [], attendance: [], tasks: [] })
    }
    if (/\/committee\/meetings/.test(url)) return json([MEETING])
    if (/\/committee\/positions/.test(url)) return json({ positions: [] })
    if (/\/committee\/tasks/.test(url)) return json([])
    if (/\/committee\/objectives/.test(url)) return json({ objectives: [] })
    if (/\/plans/.test(url)) return json({ plans: [] })
    if (/\/fees\/all-members/.test(url)) return json({ members: [] })
    if (/\/seasons/.test(url)) return json([{ id: 'se1', name: 'Summer 2025/26', year: 2025 }])
    if (/\/settings/.test(url)) return json({ diary_start_month: 7 })
    return json({})
  })
  // PLAYWRIGHT MATCHES ROUTES MOST-RECENTLY-REGISTERED FIRST, so the crest is
  // registered AFTER the catch-all above rather than before it. Registered the
  // other way round, `**/api/**` answers the <img> with `{}`, the canvas has
  // nothing to draw, and every "no crest" check passes for the wrong reason.
  await page.route('**' + LOGO_URL, (route) => failLogo
    ? route.fulfill({ status: 404, body: '' })
    : route.fulfill({ status: 200, contentType: 'image/png', body: PNG_3x2 }))
}

async function grab(page, label, dir) {
  const card = page.locator('div').filter({ has: page.locator('textarea[placeholder^="The record"]') }).last()
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 20000 }),
    card.getByRole('button', { name: label, exact: true }).click(),
  ])
  const to = `${dir}/${Math.random().toString(36).slice(2)}-${download.suggestedFilename()}`
  await download.saveAs(to)
  return to
}

// The two files for one club, downloaded from the real screen.
async function docsFor(browser, dir, club, opts) {
  const ctx = await browser.newContext({ acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
  // The same filter every browser suite here uses. This environment blocks the
  // Google Fonts / pixel / tag-manager requests the page makes, and a crest
  // route deliberately 404s in one of the scenarios below — none of which is
  // the app throwing. The crest is asserted directly, out of the file, rather
  // than inferred from the absence of a console line.
  const realErrors = () => errors.filter(e => !/favicon|ResizeObserver|Failed to load resource/i.test(e))
  await routes(page, club, opts)
  await page.addInitScript(() => { localStorage.setItem('bs_token', 'x'); localStorage.setItem('token', 'x') })
  await page.goto(`${BASE}/admin/clubhouse/committee/meeting/${MEETING_ID}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('textarea[placeholder^="The record"]', { timeout: 20000 })
  const ta = page.locator('textarea[placeholder^="The record"]')
  await ta.click()
  await ta.fill(MINUTES_TEXT)
  const docx = await grab(page, 'Word Doc', dir)
  const pdf = await grab(page, 'PDF', dir)
  await ctx.close()
  return { docx, pdf, errors: realErrors() }
}

const docxParts = (p) => execFileSync('unzip', ['-Z1', p]).toString().trim().split('\n')
// unzip glob-matches the member name itself, so [Content_Types].xml reads as a
// character class and matches nothing — the brackets have to be escaped even
// though no shell is involved.
const docxPart = (p, name) =>
  execFileSync('unzip', ['-p', p, name.replace(/[[\]]/g, m => '\\' + m)]).toString()
// The PDF is read as latin1 so the JPEG's own bytes cannot break the string,
// and the operators being looked for are all ASCII.
const pdfText = (p) => fs.readFileSync(p, 'latin1')

async function run() {
  const dir = fs.mkdtempSync('/tmp/minhead-')
  const browser = await chromium.launch(
    process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {})

  const CLUB = {
    name: 'Applecross Cricket Club', short_name: 'Applecross',
    accent: ACCENT, accent2: ACCENT2, logo: LOGO_URL,
  }

  // ── A club with its colours and its crest ────────────────────────────────
  const full = await docsFor(browser, dir, CLUB)
  const xml = docxPart(full.docx, 'word/document.xml')
  const parts = docxParts(full.docx)
  const rels = docxPart(full.docx, 'word/_rels/document.xml.rels')
  const types = docxPart(full.docx, '[Content_Types].xml')
  const pdf = pdfText(full.pdf)

  check('.docx: the band is drawn in the club\'s own primary colour',
    xml.includes(`w:fill="${ACCENT.slice(1).toUpperCase()}"`), 'no shading found')
  check('.docx: the second rule is the club\'s own secondary colour',
    xml.includes(`w:fill="${ACCENT2.slice(1).toUpperCase()}"`))
  // Paired with the club's own colour being PRESENT: "the default is absent" is
  // trivially true of a document with no band at all.
  check('.docx: the platform green is nowhere in the letterhead',
    !xml.includes('w:fill="16C784"') && xml.includes(`w:fill="${ACCENT.slice(1).toUpperCase()}"`))
  check('.docx: the band has an exact height rather than a line of text',
    /<w:spacing[^>]*w:line="\d+" w:lineRule="exact"/.test(xml))

  // THE REGRESSION THIS DESIGN EXISTS FOR. A band drawn as a one-row table
  // would make the letterhead the document's first table, and everything that
  // walks a document's tables would meet it before the meeting details.
  const tables = [...xml.matchAll(/<w:tbl>[\s\S]*?<\/w:tbl>/g)].map(m => m[0])
  const firstTableCells = tables.length
    ? [...tables[0].matchAll(/<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/g)].map(m => m[1])
    : []
  check('.docx: the band is NOT a table — meeting details is still the first one',
    firstTableCells.includes('Date') && firstTableCells.includes('Chair'),
    JSON.stringify(firstTableCells.slice(0, 6)))

  check('.docx: the crest is a real media part',
    parts.includes('word/media/image1.jpeg'), JSON.stringify(parts))
  check('.docx: a relationship points at that media part',
    /Type="[^"]*\/image" Target="media\/image1\.jpeg"/.test(rels), rels)
  check('.docx: jpeg is declared in [Content_Types]',
    /Extension="jpeg"/.test(types))
  const embed = /r:embed="(rId\d+)"/.exec(xml)
  check('.docx: the drawing references a relationship that exists',
    !!embed && rels.includes(`Id="${embed[1]}"`), embed ? embed[1] : 'no r:embed')
  check('.docx: the drawing namespaces are declared on the root element',
    xml.includes('wordprocessingDrawing') && xml.includes('officeDocument/2006/relationships'))
  // Guarded, not bare: a build with no crest at all must REPORT this check
  // rather than take the other twenty down with it.
  check('.docx: the media part really is a JPEG',
    (() => {
      try {
        const b = execFileSync('unzip', ['-p', full.docx, 'word/media/image1.jpeg'], { encoding: 'buffer' })
        return b[0] === 0xFF && b[1] === 0xD8 && b[b.length - 2] === 0xFF && b[b.length - 1] === 0xD9
      } catch { return false }
    })())
  check('.docx: the archive is valid',
    (() => { try { execFileSync('unzip', ['-t', full.docx]); return true } catch { return false } })())

  check('.pdf: the band is filled in the club\'s own primary colour',
    pdf.includes(`${ACCENT_RGB.join(' ')} rg`), 'no matching fill operator')
  check('.pdf: the second rule is the club\'s own secondary colour',
    pdf.includes(`${ACCENT2_RGB.join(' ')} rg`))
  check('.pdf: the band is a filled rectangle across the text column',
    /rg \d+(\.\d+)? \d+\.\d+ \d+\.\d+ \d+\.\d+ re f/.test(pdf))
  check('.pdf: the crest is an embedded image object',
    pdf.includes('/Subtype /Image') && pdf.includes('/Filter /DCTDecode'))
  check('.pdf: the image is 8-bit DeviceRGB, which is what a canvas JPEG is',
    /\/ColorSpace \/DeviceRGB \/BitsPerComponent 8/.test(pdf))
  check('.pdf: the image carries its real pixel dimensions',
    /\/Width (\d+) \/Height (\d+)/.test(pdf)
      && (() => { const m = /\/Width (\d+) \/Height (\d+)/.exec(pdf); return +m[1] > 0 && +m[2] > 0 })())
  check('.pdf: the page draws it', /\/Im0 Do/.test(pdf))
  // `[^>]*` cannot reach it: /Font's own `>>` closes before /XObject starts.
  check('.pdf: the page\'s own Resources name that XObject',
    /\/Resources <<[\s\S]{0,200}?\/XObject << \/Im0 \d+ 0 R >>/.test(pdf),
    (/\/Resources <<[^\n]*/.exec(pdf) || ['no /Resources'])[0])

  // A hand-built object is most likely to break the xref, and a PDF with a
  // wrong offset table opens as a blank or a repair prompt rather than an
  // error — so the offsets are checked against the file rather than trusted.
  const xrefOk = (() => {
    const m = /startxref\s+(\d+)/.exec(pdf)
    if (!m) return 'no startxref'
    const at = +m[1]
    if (pdf.slice(at, at + 4) !== 'xref') return `startxref points at ${JSON.stringify(pdf.slice(at, at + 10))}`
    const rows = [...pdf.slice(at).matchAll(/^(\d{10}) 00000 n $/gm)].map(r => +r[1])
    if (!rows.length) return 'no object rows'
    for (let i = 0; i < rows.length; i++) {
      if (!new RegExp(`^${i + 1} 0 obj`).test(pdf.slice(rows[i], rows[i] + 24))) {
        return `row ${i + 1} points at ${JSON.stringify(pdf.slice(rows[i], rows[i] + 20))}`
      }
    }
    return true
  })()
  check('.pdf: every xref row points at the object it claims', xrefOk === true, String(xrefOk))
  check('.pdf: starts %PDF and ends %%EOF',
    pdf.startsWith('%PDF-') && pdf.trimEnd().endsWith('%%EOF'))
  check('the club\'s name still heads the document',
    xml.includes('APPLECROSS CRICKET CLUB'))
  check('no page errors with a crest', full.errors.length === 0, full.errors.join(' | '))

  // ── A club with no crest at all ──────────────────────────────────────────
  const noLogo = await docsFor(browser, dir, { ...CLUB, logo: null })
  const nlParts = docxParts(noLogo.docx)
  const nlXml = docxPart(noLogo.docx, 'word/document.xml')
  const nlRels = docxPart(noLogo.docx, 'word/_rels/document.xml.rels')
  const nlPdf = pdfText(noLogo.pdf)
  check('no crest: the band is still drawn in the club\'s colours (.docx)',
    nlXml.includes(`w:fill="${ACCENT.slice(1).toUpperCase()}"`))
  check('no crest: the band is still drawn in the club\'s colours (.pdf)',
    nlPdf.includes(`${ACCENT_RGB.join(' ')} rg`))
  // Against the crested run in the same suite, so a build that never writes a
  // media part at all cannot pass this by doing nothing.
  check('no crest: no media part is written',
    !nlParts.some(p => p.startsWith('word/media/')) && parts.includes('word/media/image1.jpeg'),
    JSON.stringify(nlParts))
  check('no crest: no dangling image relationship',
    !/\/image"/.test(nlRels), nlRels)
  check('no crest: no image object in the .pdf',
    !nlPdf.includes('/Subtype /Image') && pdf.includes('/Subtype /Image'))
  check('no crest: the .pdf still has no XObject in its Resources',
    !/\/XObject/.test(nlPdf) && /\/XObject/.test(pdf))
  check('no crest: xref still consistent',
    (() => {
      const m = /startxref\s+(\d+)/.exec(nlPdf)
      return !!m && nlPdf.slice(+m[1], +m[1] + 4) === 'xref'
    })())
  check('no crest: no page errors', noLogo.errors.length === 0, noLogo.errors.join(' | '))

  // ── A crest that cannot be read ──────────────────────────────────────────
  const broken = await docsFor(browser, dir, CLUB, { failLogo: true })
  const bkParts = docxParts(broken.docx)
  const bkXml = docxPart(broken.docx, 'word/document.xml')
  check('unreadable crest: the document is still produced',
    bkXml.includes('APPLECROSS CRICKET CLUB'))
  check('unreadable crest: the band still draws',
    bkXml.includes(`w:fill="${ACCENT.slice(1).toUpperCase()}"`))
  check('unreadable crest: no empty media part is written',
    !bkParts.some(p => p.startsWith('word/media/')) && parts.includes('word/media/image1.jpeg'),
    JSON.stringify(bkParts))
  check('unreadable crest: no page errors', broken.errors.length === 0, broken.errors.join(' | '))

  // ── A club that has never set a theme ────────────────────────────────────
  // The server falls back to the platform pair, so the band is drawn either
  // way — a club with no colours must not get a document with no letterhead.
  const plain = await docsFor(browser, dir, { name: 'Plain CC', short_name: 'Plain' })
  const plXml = docxPart(plain.docx, 'word/document.xml')
  check('no colours set: a band is still drawn rather than nothing',
    /<w:shd w:val="clear" w:color="auto" w:fill="[0-9A-F]{6}"/.test(plXml))
  check('no colours set: no page errors', plain.errors.length === 0, plain.errors.join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:'); FAIL.forEach(f => console.log('  ' + f)); process.exitCode = 1 }
}

run().catch(e => { console.error(e); process.exitCode = 1 })
