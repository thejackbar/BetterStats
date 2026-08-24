// The MINUTES and YOUR NOTES download buttons, against the REAL meeting room
// with the API stubbed at the network layer.
//
// What is asserted:
//   * a DOWNLOAD row of exactly two buttons — Word Doc and PDF — sits BELOW
//     each of the two text boxes, measured off the real boxes rather than off
//     source order;
//   * both are disabled while the field is empty and enabled once it is not;
//   * pressing each one actually produces a file, with a name carrying the
//     meeting and the date rather than a bare "Minutes.pdf";
//   * THE FILE CARRIES WHAT IS IN THE BOX, NOT WHAT THE SERVER HOLDS. The
//     autosave is 700ms behind, so the suite types and downloads immediately
//     with the PATCH deliberately blocked — the whole point of writing the
//     document in the browser;
//   * the minutes file does not carry the private notes, and the notes file
//     does not carry the minutes;
//   * a .docx really is a zip whose parts are the OOXML a reader expects, and
//     a .pdf really does start %PDF and end %%EOF with an xref table;
//   * the same two rows are present with the room EMBEDDED in the Committee
//     screen, which is where this was asked for;
//   * no page errors, and no horizontal overflow at 390px.
//
//   node verify_minutes_download_browser.mjs   (expects the dev server on :5199)
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
// A meeting with a name and a date, since both are meant to reach the filename.
const MEETING = {
  id: MEETING_ID, title: 'August Committee Meeting', meeting_type: 'committee',
  scheduled_at: '2026-08-18T19:30:00Z', location: 'Clubrooms',
  status: 'in_progress', minutes: '', private_notes: '',
}
const ROOM = {
  meeting: MEETING, agenda_items: [], motions: [], actions: [],
  attendance: [], attendee_pool: [], previous_attendance: null,
}

// What gets typed. Deliberately awkward: XML metacharacters that would break a
// hand-built document.xml, and punctuation a phone keyboard produces.
const MINUTES_TEXT = 'Opened 7:32pm. Apologies: J. Smith & R. Jones <away>.\n\nTreasurer’s report — balance $12,430.55.'
const NOTES_TEXT = 'Chase the grant form. Ring Bev about the roster.'

const routes = (page, state) => page.route('**/api/**', async (route) => {
  const url = route.request().url()
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

  if (url.includes('/auth/me')) {
    return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
                  entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } })
  }
  // The autosave. Recorded and NEVER applied to the stub's record, so the room
  // still believes both fields are empty — which is what makes "the download
  // carries the box, not the record" a real assertion rather than a coincidence.
  if (/\/committee\/meetings\/[^/]+$/.test(url) && route.request().method() === 'PATCH') {
    state.patches.push(JSON.parse(route.request().postData() || '{}'))
    return json(MEETING)
  }
  if (/\/committee\/meetings\/[^/?]+\/room/.test(url)) return json(ROOM)
  // The Committee screen pulls each meeting's full detail after the list, so a
  // single-meeting GET must answer with the MEETING and not the list — handing
  // back the array leaves every card without an id and no OPEN button to press.
  if (/\/committee\/meetings\/[^/?]+(\?|$)/.test(url)) {
    return json({ ...MEETING, agenda_items: [], motions: [], attendance: [], tasks: [] })
  }
  if (/\/committee\/meetings/.test(url)) return json([MEETING])
  if (/\/committee\/positions/.test(url)) return json({ positions: [] })
  if (/\/committee\/tasks/.test(url)) return json([])
  if (/\/committee\/objectives|\/plans/.test(url)) return json({ objectives: [], plans: [] })
  if (/\/fees\/all-members/.test(url)) return json({ members: [] })
  if (/\/seasons/.test(url)) return json([{ id: 'se1', name: 'Summer 2025/26', year: 2025 }])
  if (/\/settings/.test(url)) return json({ diary_start_month: 7 })
  return json({})
})

// The two boxes and the buttons under them, found from the caption above each.
// A real function, not a string: `page.evaluate` treats a string as an
// expression, so a function-expression string comes back unevaluated.
const PROBE = () => {
  const cards = [...document.querySelectorAll('div')].filter(d => d.querySelector(':scope > textarea'))
  const out = {}
  for (const card of cards) {
    const label = card.textContent || ''
    const key = /MINUTES/.test(label) ? 'minutes' : /YOUR NOTES/.test(label) ? 'notes' : null
    if (!key || out[key]) continue
    const ta = card.querySelector(':scope > textarea')
    const btns = [...card.querySelectorAll('button')].filter(b => /^(Word Doc|PDF)$/.test((b.textContent || '').trim()))
    const tr = ta.getBoundingClientRect()
    out[key] = {
      labels: btns.map(b => b.textContent.trim()),
      disabled: btns.map(b => b.disabled),
      // Below the box: every button's top edge sits under the textarea's bottom.
      below: btns.length > 0 && btns.every(b => b.getBoundingClientRect().top >= tr.bottom - 1),
      // And left-aligned with it, so the row reads as belonging to the field.
      aligned: btns.length > 0 && btns.every(b => b.getBoundingClientRect().left >= tr.left - 1),
      hasCaption: /DOWNLOAD/.test(label),
    }
  }
  return out
}

async function typeInto(page, which, text) {
  const ta = page.locator(which === 'minutes'
    ? 'textarea[placeholder^="The record"]'
    : 'textarea[placeholder^="Not part"]')
  await ta.click()
  await ta.fill(text)
}

async function grab(page, which, label, dir) {
  const card = page.locator('div').filter({ has: page.locator(`textarea[placeholder^="${which === 'minutes' ? 'The record' : 'Not part'}"]`) }).last()
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15000 }),
    card.getByRole('button', { name: label, exact: true }).click(),
  ])
  const name = download.suggestedFilename()
  const to = `${dir}/${name}`
  await download.saveAs(to)
  return { name, path: to }
}

async function run() {
  const dir = fs.mkdtempSync('/tmp/mindl-')
  // PW_CHROMIUM lets a machine whose Chromium is not the build this Playwright
  // ships with point at the one it has, rather than downloading a second copy.
  const browser = await chromium.launch(
    process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {})
  const ctx = await browser.newContext({ acceptDownloads: true })
  const page = await ctx.newPage()
  const state = { patches: [] }
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
  await routes(page, state)
  await page.addInitScript(() => {
    localStorage.setItem('bs_token', 'x')
    localStorage.setItem('token', 'x')
  })

  // ── The standalone room ───────────────────────────────────────────────────
  await page.goto(`${BASE}/admin/clubhouse/committee/meeting/${MEETING_ID}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('textarea[placeholder^="The record"]', { timeout: 20000 })

  let probe = await page.evaluate(PROBE)
  for (const key of ['minutes', 'notes']) {
    const p = probe[key]
    check(`${key}: a DOWNLOAD row is drawn`, !!p && p.hasCaption, JSON.stringify(p))
    check(`${key}: exactly Word Doc and PDF, in that order`,
      !!p && JSON.stringify(p.labels) === JSON.stringify(['Word Doc', 'PDF']), JSON.stringify(p?.labels))
    check(`${key}: the buttons sit BELOW the text field`, !!p && p.below)
    check(`${key}: the row starts at the field's own left edge`, !!p && p.aligned)
    check(`${key}: both are disabled while the field is empty`,
      !!p && p.disabled.length === 2 && p.disabled.every(Boolean), JSON.stringify(p?.disabled))
  }

  // ── Type, then download IMMEDIATELY ──────────────────────────────────────
  await typeInto(page, 'minutes', MINUTES_TEXT)
  await typeInto(page, 'notes', NOTES_TEXT)
  probe = await page.evaluate(PROBE)
  for (const key of ['minutes', 'notes']) {
    check(`${key}: both enable once the field has text`,
      probe[key].disabled.length === 2 && probe[key].disabled.every(d => d === false),
      JSON.stringify(probe[key].disabled))
  }

  const files = {
    minutesDocx: await grab(page, 'minutes', 'Word Doc', dir),
    minutesPdf: await grab(page, 'minutes', 'PDF', dir),
    notesDocx: await grab(page, 'notes', 'Word Doc', dir),
    notesPdf: await grab(page, 'notes', 'PDF', dir),
  }

  // The record the server holds is still empty, so anything found in these
  // files can only have come from the box.
  check('the stub never applied the autosave (the record stays empty)',
    ROOM.meeting.minutes === '' && ROOM.meeting.private_notes === '')

  check('minutes .docx is named for the meeting and its date',
    /August Committee Meeting/.test(files.minutesDocx.name) && /2026/.test(files.minutesDocx.name)
      && files.minutesDocx.name.endsWith('Minutes.docx'), files.minutesDocx.name)
  check('notes .pdf is named for the meeting and says Notes',
    /August Committee Meeting/.test(files.notesPdf.name) && files.notesPdf.name.endsWith('Notes.pdf'),
    files.notesPdf.name)

  // ── The files themselves ─────────────────────────────────────────────────
  const readDocx = (p) => {
    const parts = execFileSync('unzip', ['-Z1', p]).toString().trim().split('\n')
    const xml = execFileSync('unzip', ['-p', p, 'word/document.xml']).toString()
    execFileSync('unzip', ['-t', p])   // throws on a malformed archive
    return { parts, xml }
  }
  for (const [key, f] of [['minutes', files.minutesDocx], ['notes', files.notesDocx]]) {
    let d = null, ok = true
    try { d = readDocx(f.path) } catch (e) { ok = false }
    check(`${key} .docx: a valid archive with the OOXML parts a reader expects`,
      ok && d.parts.includes('[Content_Types].xml') && d.parts.includes('word/document.xml')
        && d.parts.includes('_rels/.rels'), String(d && d.parts))
    check(`${key} .docx: declares the wordprocessingml namespace`,
      ok && d.xml.includes('wordprocessingml/2006/main'))
  }
  const minutesXml = readDocx(files.minutesDocx.path).xml
  const notesXml = readDocx(files.notesDocx.path).xml
  check('minutes .docx carries the typed text, autosave or not',
    minutesXml.includes('Opened 7:32pm') && minutesXml.includes('balance $12,430.55'))
  check('minutes .docx escapes & and < rather than breaking the XML',
    minutesXml.includes('J. Smith &amp; R. Jones &lt;away&gt;'))
  check('minutes .docx keeps the blank line as an empty paragraph',
    (minutesXml.match(/<w:p>/g) || []).length >= 4)
  check('minutes .docx names the meeting and the date at the top',
    minutesXml.includes('August Committee Meeting') && minutesXml.includes('Minutes'))
  check('notes .docx carries the notes', notesXml.includes('Chase the grant form'))
  check('the notes document is marked as not part of the minutes',
    notesXml.includes('Not part of the minutes'))
  check('minutes and notes do not leak into each other',
    !minutesXml.includes('Chase the grant form') && !notesXml.includes('Opened 7:32pm'))

  for (const [key, f] of [['minutes', files.minutesPdf], ['notes', files.notesPdf]]) {
    const buf = fs.readFileSync(f.path)
    const s = buf.toString('latin1')
    check(`${key} .pdf: starts %PDF and ends %%EOF`,
      s.startsWith('%PDF-') && s.trimEnd().endsWith('%%EOF'))
    check(`${key} .pdf: has an xref table and a startxref that points inside the file`,
      s.includes('\nxref\n') && (() => {
        const m = s.match(/startxref\s+(\d+)/)
        return m && Number(m[1]) > 0 && Number(m[1]) < buf.length
          && s.slice(Number(m[1]), Number(m[1]) + 4) === 'xref'
      })())
    check(`${key} .pdf: draws its text with a real font resource`,
      s.includes('/Helvetica') && s.includes(' Tj'))
  }
  const minutesPdfText = fs.readFileSync(files.minutesPdf.path).toString('latin1')
  check('minutes .pdf carries the typed text', minutesPdfText.includes('Opened 7:32pm'))
  check('minutes .pdf escapes the brackets a PDF string cannot hold raw',
    !/\([^)]*<away>[^)]*\)/.test(minutesPdfText) || minutesPdfText.includes('away'))
  check('notes .pdf carries the notes',
    fs.readFileSync(files.notesPdf.path).toString('latin1').includes('Chase the grant form'))

  // The autosave is a 700ms debounce, so it lands AFTER a download taken
  // straight after the last keystroke — which is the whole reason the document
  // is written from the box. Waited for rather than raced, since the point of
  // the check is that downloading did not break the save, not when it arrives.
  const savedBoth = async () => {
    for (let i = 0; i < 40; i++) {
      if (state.patches.some(x => 'minutes' in x) && state.patches.some(x => 'private_notes' in x)) return true
      await page.waitForTimeout(100)
    }
    return false
  }
  check('the autosave still fires for both fields, after the download',
    await savedBoth(), JSON.stringify(state.patches))

  // ── The embedded room, which is where this was asked for ─────────────────
  await page.goto(`${BASE}/admin/committee`, { waitUntil: 'networkidle' })
  const open = page.getByRole('button', { name: /^OPEN$/i }).first()
  let embedded = false
  try {
    await open.click({ timeout: 8000 })
    await page.waitForSelector('textarea[placeholder^="The record"]', { timeout: 8000 })
    embedded = true
  } catch { /* reported below */ }
  if (embedded) {
    const p = await page.evaluate(PROBE)
    check('embedded in Committee: the minutes row is drawn below the box',
      !!p.minutes && p.minutes.below && JSON.stringify(p.minutes.labels) === JSON.stringify(['Word Doc', 'PDF']))
    check('embedded in Committee: the notes row is drawn below the box',
      !!p.notes && p.notes.below && JSON.stringify(p.notes.labels) === JSON.stringify(['Word Doc', 'PDF']))
  } else {
    check('embedded in Committee: the room opens from a meeting card', false, 'no OPEN button reached')
  }

  // ── The usual two ────────────────────────────────────────────────────────
  await page.goto(`${BASE}/admin/clubhouse/committee/meeting/${MEETING_ID}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('textarea[placeholder^="The record"]')
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(300)
  const over = await page.evaluate(() =>
    Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth))
  check('no horizontal overflow at 390px', over === 0, `${over}px`)

  const real = errors.filter(e => !/favicon|ResizeObserver|Failed to load resource/i.test(e))
  check('no page errors', real.length === 0, real.slice(0, 3).join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch(e => { console.error(e); process.exit(1) })
