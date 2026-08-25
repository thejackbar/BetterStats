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
// The meeting reported off the live screen: a motion moved during the
// President's report, serving a plan objective, with the votes recorded by name
// — the detail the old draft dropped on the floor.
const MEETING = {
  id: MEETING_ID, title: 'Mid Month', meeting_type: 'committee',
  scheduled_at: '2026-08-10T19:30:00Z', location: 'Clubrooms',
  status: 'in_progress', minutes: '', private_notes: '',
}
const MEMBERS = [
  { member_id: 'm1', full_name: 'Hullett, Mark', on_committee: true, position: 'President' },
  { member_id: 'm2', full_name: 'Bairstow, Hayden', on_committee: true, position: null },
  { member_id: 'm3', full_name: 'Barendse, Jack', on_committee: true, position: 'Treasurer' },
  { member_id: 'm4', full_name: 'Fletcher, Tristram', on_committee: true, position: null },
  { member_id: 'm5', full_name: 'Monument, Darren', on_committee: true, position: null },
  { member_id: 'm6', full_name: 'Birbeck, James', on_committee: true, position: null },
  { member_id: 'm7', full_name: 'Brennan, Joshua', on_committee: true, position: null },
]
const ATTENDANCE = [
  { member_id: 'm1', full_name: 'Hullett, Mark', status: 'chair' },
  { member_id: 'm2', full_name: 'Bairstow, Hayden', status: 'present' },
  { member_id: 'm3', full_name: 'Barendse, Jack', status: 'present' },
  { member_id: 'm4', full_name: 'Fletcher, Tristram', status: 'present' },
  { member_id: 'm5', full_name: 'Monument, Darren', status: 'present' },
  { member_id: 'm6', full_name: 'Birbeck, James', status: 'absent' },
  { member_id: 'm7', full_name: 'Brennan, Joshua', status: 'apology' },
]
const AGENDA = [
  { id: 'a1', title: 'Welcome & attendance', status: 'proposed', position: 0, section: null, outcome_notes: '' },
  { id: 'a2', title: 'Apologies', status: 'proposed', position: 1, section: null, outcome_notes: '' },
  { id: 'a3', title: 'Minutes of previous meeting', status: 'proposed', position: 2, section: null, outcome_notes: '' },
  { id: 'a4', title: "President's report", status: 'proposed', position: 3, section: 'Reports', outcome_notes: '' },
  { id: 'a5', title: 'Sponsorship & Fundraising', status: 'proposed', position: 4, section: 'Reports', outcome_notes: '' },
]
const OBJECTIVES = [
  { id: 'o1', title: 'Diversify revenue streams through grants, sponsorships, canteen sales, and social memberships',
    plan_name: 'Strategic Plan - 2026/27', pillar_name: 'Financial Stability & Governance' },
  { id: 'o2', title: 'Host regular social events and volunteer appreciation days to build a strong club identity',
    plan_name: 'Strategic Plan - 2026/27', pillar_name: 'Community & Club Culture' },
]
const MOTIONS = [
  { id: 'mo1', meeting_id: MEETING_ID, agenda_item_id: 'a4', position: 0, motion_type: 'motion',
    description: 'That the club should have Premium Sponsorship package',
    proposed_by_member_id: 'm1', seconded_by_member_id: null,
    votes_for: 1, votes_against: 2, votes_abstain: 1, outcome: 'lost', notes: null,
    is_resolution: false, resolution_ref: null, resolved_at: null, objective_id: 'o1',
    votes: [{ member_id: 'm4', vote: 'for' }, { member_id: 'm1', vote: 'against' },
            { member_id: 'm5', vote: 'against' }, { member_id: 'm3', vote: 'abstain' }] },
]
const ACTIONS = [
  { id: 't1', title: 'Prepare plan for Sponsorship packages', description: null, category: null,
    status: 'done', due_date: '2026-10-01', budget_estimate: 500, objective_id: 'o2',
    agenda_item_id: 'a4', meeting_id: MEETING_ID, motion_id: null,
    assignee_member_ids: ['m3'], assigned_to_member_id: 'm3', depends_on: [], percent_complete: 100 },
  { id: 't2', title: 'Sign up 3 new sponsors before start of season', description: null, category: null,
    status: 'todo', due_date: '2026-09-10', budget_estimate: null, objective_id: null,
    agenda_item_id: null, meeting_id: MEETING_ID, motion_id: null,
    assignee_member_ids: ['m1'], assigned_to_member_id: 'm1', depends_on: [], percent_complete: 0 },
]
const ROOM = {
  meeting: MEETING, club: { name: 'Applecross Cricket Club', short_name: 'Applecross' },
  agenda_items: AGENDA, motions: MOTIONS, actions: ACTIONS,
  attendance: ATTENDANCE, attendee_pool: MEMBERS, previous_attendance: null,
}

// What gets typed. Deliberately awkward: XML metacharacters that would break a
// hand-built document.xml, and punctuation a phone keyboard produces.
const MINUTES_TEXT = [
  // The preamble the model writes despite being told not to: the club, the
  // document name and the date, all of which the document already heads itself
  // with. This is what came out mid-page as "APPLECROSS CRICKET CLUBCOMMITTEE
  // MEETING MINUTES10 August 2026".
  'APPLECROSS CRICKET CLUB',
  'COMMITTEE MEETING MINUTES',
  '10 August 2026',
  // Bare-line headings, which is how the draft actually writes them.
  "Welcome & attendance",
  'Opened 7:32pm. Apologies: J. Smith & R. Jones <away>.',
  "President's report",
  'The Chair reported on sponsorship. Balance $12,430.55.',
].join('\n')
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
  if (/\/committee\/objectives/.test(url)) return json({ objectives: OBJECTIVES })
  if (/\/plans/.test(url)) return json({ plans: [] })
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
  check('minutes .docx is named for the meeting and its date',
    /Mid Month/.test(files.minutesDocx.name) && /2026/.test(files.minutesDocx.name)
      && files.minutesDocx.name.endsWith('Minutes.docx'), files.minutesDocx.name)
  check('notes .pdf is named for the meeting and says Notes',
    /Mid Month/.test(files.notesPdf.name) && files.notesPdf.name.endsWith('Notes.pdf'),
    files.notesPdf.name)
  check('the stub never applied the autosave (the record stays empty)',
    ROOM.meeting.minutes === '' && ROOM.meeting.private_notes === '')


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
  // The paragraph texts in document order, which is what makes "under the right
  // heading" a measurable claim rather than a substring search.
  const paras = (xml) => [...xml.matchAll(/<w:p[ >][\s\S]*?<\/w:p>/g)]
    .map(m => [...m[0].matchAll(/<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/g)].map(t => t[1]).join(''))
    .map(t => t.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'))
  const mp = paras(minutesXml)
  const at = (re) => mp.findIndex(t => re.test(t))
  const joined = mp.join('\n')

  check('the document is headed by the CLUB, not just the meeting',
    mp.slice(0, 4).some(t => t === 'APPLECROSS CRICKET CLUB'), JSON.stringify(mp.slice(0, 4)))
  check('the title block names the meeting and its date',
    joined.includes('Mid Month Committee Meeting Minutes') && joined.includes('10 August 2026'))

  check('§1 is a Meeting Details section', at(/^1\. Meeting Details$/) >= 0)
  check('§2 is the Agenda', at(/^2\. Agenda$/) >= 0)
  check('the agenda is a bulleted list of the real items',
    mp.some(t => t.startsWith('\u2022') && t.includes("President's report")))

  // The details table, read out of the real table cells.
  const tables = [...minutesXml.matchAll(/<w:tbl>[\s\S]*?<\/w:tbl>/g)].map(m => m[0])
  check('the document carries real Word tables, not laid-out text', tables.length >= 2, `${tables.length}`)
  const unesc = t => t.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  const cellsOf = (tbl) => [...tbl.matchAll(/<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/g)].map(m => unesc(m[1]))
  const detailCells = tables.length ? cellsOf(tables[0]) : []
  for (const row of ['Date', 'Time', 'Location', 'Chair', 'Present', 'Apologies', 'Absent']) {
    check(`meeting details: ${row} is a row`, detailCells.includes(row), JSON.stringify(detailCells.slice(0, 8)))
  }
  check('meeting details: the chair is named', detailCells.some(c => c === 'Hullett, Mark'))
  check('meeting details: everyone present is listed',
    detailCells.some(c => c.includes('Bairstow, Hayden') && c.includes('Monument, Darren')))
  check('meeting details: the apology is not counted as present',
    detailCells.some(c => c === 'Brennan, Joshua'))
  check('meeting details: the absent member is recorded as absent',
    detailCells.some(c => c === 'Birbeck, James'))

  // THE REPORTED BUG: the motion belongs to the President's report, and it must
  // be written up there rather than under whichever heading its subject suits.
  const presIdx = at(/^\d+\. President's report$/)
  const nextIdx = at(/^\d+\. Sponsorship & Fundraising$/)
  const motionIdx = at(/Premium Sponsorship package/)
  check("the President's report has its own numbered section", presIdx >= 0)
  check('the motion is written up under the President\u2019s report, not Sponsorship',
    presIdx >= 0 && motionIdx > presIdx && motionIdx < nextIdx,
    `pres ${presIdx}, motion ${motionIdx}, next ${nextIdx}`)
  const inSection = mp.slice(presIdx, nextIdx).join('\n')
  check('the motion is labelled as a motion', inSection.includes('MOTION'))
  check('the motion records who moved it', inSection.includes('Moved by Hullett, Mark'))
  check('the motion names the strategic objective it serves',
    inSection.includes('Serves objective: Strategic Plan - 2026/27')
      && inSection.includes('Financial Stability & Governance')
      && inSection.includes('Diversify revenue streams'), inSection)
  check('the motion records its outcome and the tally',
    inSection.includes('Outcome: Lost. For 1, against 2, abstain 1.'), inSection)
  check('the motion records how each person voted',
    inSection.includes('Fletcher, Tristram') && inSection.includes('Monument, Darren')
      && inSection.includes('Barendse, Jack') && /Votes recorded\./.test(inSection)
      && /For: Fletcher, Tristram/.test(inSection)
      // Names read "Surname, First", so a comma-joined pair would read as four
      // people. The against pair has to be separated by something else.
      && /Against: Hullett, Mark; Monument, Darren/.test(inSection), inSection)
  check('the action raised in that item is recorded there too',
    inSection.includes('Prepare plan for Sponsorship packages')
      && inSection.includes('Barendse, Jack') && inSection.includes('$500'), inSection)
  check('the action names its own objective, which differs from the motion\u2019s',
    inSection.includes('Community & Club Culture'), inSection)

  // The actions table.
  const actionsTable = tables[tables.length - 1] || ''
  const actionCells = actionsTable ? cellsOf(actionsTable) : []
  for (const col of ['Owner', 'Action', 'Due', 'Budget', 'Serves objective', 'Status']) {
    check(`actions table: a ${col} column`, actionCells.includes(col), JSON.stringify(actionCells.slice(0, 8)))
  }
  check('actions table: every action is a row, including one raised outside the agenda',
    actionCells.some(c => c === 'Prepare plan for Sponsorship packages')
      && actionCells.some(c => c === 'Sign up 3 new sponsors before start of season'))
  check('actions table: an action with no objective says so rather than being blank',
    actionCells.filter(c => c === 'Not recorded').length >= 1)
  check('actions table: the objective is carried through',
    actionCells.some(c => c.includes('Community & Club Culture')))

  check('the narrative typed into the box is used, autosave or not',
    joined.includes('Opened 7:32pm'), joined.slice(0, 300))
  // The draft heads its sections with the agenda item's own title on a bare
  // line. Matching only markdown headings found none of them, so the whole
  // account landed in one lump under Record of Discussion instead of being
  // distributed. Measured by position, not by presence.
  const welcomeIdx = at(/^\d+\. Welcome & attendance$/)
  const narrativeIdx = at(/Opened 7:32pm/)
  const apologiesIdx = at(/^\d+\. Apologies$/)
  check('a bare-line heading files its prose under the matching agenda item',
    welcomeIdx >= 0 && narrativeIdx > welcomeIdx && narrativeIdx < apologiesIdx,
    `welcome ${welcomeIdx}, prose ${narrativeIdx}, next ${apologiesIdx}`)
  check("the President's own prose lands in the President's section",
    mp.slice(presIdx, nextIdx).join('\n').includes('The Chair reported on sponsorship'))
  check('nothing is left over in a Record of Discussion lump',
    at(/^\d+\. Record of Discussion$/) === -1)
  // The model's own title block repeated the club, the document name and the
  // date the document already carries.
  check('the drafted title block is not repeated mid-document',
    mp.filter(t => t === 'COMMITTEE MEETING MINUTES').length === 0
      && mp.filter(t => t === 'APPLECROSS CRICKET CLUB').length === 1,
    JSON.stringify(mp.filter(t => /COMMITTEE MEETING MINUTES|APPLECROSS/.test(t))))
  check('markdown asterisks are not printed literally', !joined.includes('**'))
  check('& and < are escaped rather than breaking the XML',
    minutesXml.includes('J. Smith &amp; R. Jones &lt;away&gt;'))
  check('the document closes off', joined.includes('End of minutes'))

  check('notes .docx carries the notes', notesXml.includes('Chase the grant form'))
  check('the notes document is marked as not part of the minutes',
    notesXml.includes('Not part of the minutes'))
  check('minutes and notes do not leak into each other',
    !minutesXml.includes('Chase the grant form') && !notesXml.includes('Premium Sponsorship'))

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
      s.includes('/F1') && s.includes(' Tj'))
  }
  const minutesPdfRaw = fs.readFileSync(files.minutesPdf.path).toString('latin1')
  const pdfText = [...minutesPdfRaw.matchAll(/\((.*?)\) Tj/g)].map(m => m[1]).join(' ')
  check('minutes .pdf carries the typed narrative', pdfText.includes('Opened 7:32pm'))
  check('minutes .pdf carries the motion, its objective and the vote',
    pdfText.includes('Premium Sponsorship') && pdfText.includes('Financial')
      && pdfText.includes('Outcome: Lost') && pdfText.includes('Votes recorded'), pdfText.slice(0, 200))
  check('minutes .pdf draws the tables it needs',
    / re S/.test(minutesPdfRaw) && pdfText.includes('Serves objective'))

  // LAYOUT, measured off the real draw operations. The indent was reported as
  // far too deep in the PDF and correct in Word: `indent` is twips, and the PDF
  // was reading the same number as points, so a 10pt Word indent drew at 200pt.
  const pageStreams = [...minutesPdfRaw.matchAll(/stream\n([\s\S]*?)\nendstream/g)].map(m => m[1])
  const draws = pageStreams.flatMap((ps, page) =>
    [...ps.matchAll(/BT (\/F\d) ([\d.]+) Tf ([\d.]+) ([\d.]+) Td \((.*?)\) Tj ET/g)]
      .map(m => ({ page, font: m[1], size: Number(m[2]), x: Number(m[3]), y: Number(m[4]), text: m[5] })))
  const MARGIN = 56
  const motionRow = draws.find(d => d.text === 'MOTION')
  const headingRow = draws.find(d => /^\d+\. President's report$/.test(d.text))
  check('minutes .pdf: the motion block is inset about a third of what it was',
    motionRow && Math.abs((motionRow.x - MARGIN) - 200 / 3) <= 2,
    motionRow ? `${(motionRow.x - MARGIN).toFixed(1)}pt from the margin` : 'no MOTION drawn')
  check('minutes .pdf: a section heading still starts at the margin',
    headingRow && Math.abs(headingRow.x - MARGIN) < 0.5, `${headingRow?.x}`)

  // A blank line in each of the three places asked for, measured as the gap
  // between one baseline and the next rather than read off the source.
  // Measured between two baselines ON THE SAME PAGE — y restarts at the top of
  // each page, so an element that happens to fall first on a page has no
  // meaningful gap and the next occurrence is used instead.
  const gapBefore = (pred) => {
    for (let i = 1; i < draws.length; i++) {
      if (!pred(draws[i])) continue
      const prev = draws[i - 1]
      if (prev.page === draws[i].page && prev.y > draws[i].y) return prev.y - draws[i].y
    }
    return null
  }
  const bodyStep = 10.5 * 1.32 + 3
  const beforeHeading = gapBefore(d => /^\d+\. Apologies$/.test(d.text))
  const afterHeading = gapBefore(d => d.text === 'Discussed.')
  const beforeMotion = gapBefore(d => d.text === 'MOTION' || d.text === 'ACTION')
  check('minutes .pdf: a blank line before an agenda item title',
    beforeHeading !== null && beforeHeading > bodyStep * 1.6, `${beforeHeading?.toFixed(1)}pt`)
  check('minutes .pdf: a blank line after the title, before the section text',
    afterHeading !== null && afterHeading > bodyStep * 1.6, `${afterHeading?.toFixed(1)}pt`)
  check('minutes .pdf: a blank line before a MOTION or ACTION block',
    beforeMotion !== null && beforeMotion > bodyStep * 1.4, `${beforeMotion?.toFixed(1)}pt`)

  // Arial, named on the font objects the pages actually reference.
  check('minutes .pdf is set in Arial',
    /\/BaseFont \/Arial\b/.test(minutesPdfRaw) && /\/BaseFont \/Arial,Bold/.test(minutesPdfRaw)
      && !/\/Helvetica/.test(minutesPdfRaw))
  check('minutes .pdf declares the widths its layout measured with',
    /\/FirstChar 32 \/LastChar 255/.test(minutesPdfRaw) && /\/FontDescriptor/.test(minutesPdfRaw))
  check('minutes .docx is set in Arial',
    (minutesXml.match(/w:ascii="Arial"/g) || []).length > 10)

  // PAGINATION, which the earlier checks never looked at and should have. A
  // rule under a heading reported no height, so every element after the first
  // landed on a page of its own: a two-page document came out as 19, half of
  // them blank, and every content check still passed.
  const pageCount = Number((minutesPdfRaw.match(/\/Count (\d+)/) || [])[1] || 0)
  const streams = [...minutesPdfRaw.matchAll(/stream\n([\s\S]*?)\nendstream/g)].map(m => m[1])
  check('minutes .pdf is a sensibly paged document, not one element per page',
    pageCount >= 1 && pageCount <= 4, `${pageCount} pages`)
  check('minutes .pdf has no blank pages',
    streams.length === pageCount && streams.every(s2 => / Tj/.test(s2)),
    `${streams.filter(s2 => !/ Tj/.test(s2)).length} blank of ${streams.length}`)

  // Nothing may be drawn outside the margins, text or table rule alike.
  const outside = []
  for (const s2 of streams) {
    for (const m of s2.matchAll(/([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re/g)) {
      const [x, y2, w, h] = m.slice(1).map(Number)
      if (x < 55.5 || x + w > 539.8 || y2 < 55.5 || y2 + h > 786.4) outside.push(['rect', x, y2, w, h])
    }
    for (const m of s2.matchAll(/([\d.]+) ([\d.]+) Td/g)) {
      const [x, y2] = m.slice(1).map(Number)
      if (x < 55.5 || x > 539.8 || y2 < 55.5 || y2 > 786.4) outside.push(['text', x, y2])
    }
  }
  check('minutes .pdf draws nothing outside the margins', outside.length === 0,
    JSON.stringify(outside.slice(0, 3)))
  // A table's cells must tile across the row: no gap, no overlap.
  const byRow = new Map()
  for (const s2 of streams) {
    for (const m of s2.matchAll(/([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re S/g)) {
      const [x, y2, w] = m.slice(1).map(Number)
      const k = `${streams.indexOf(s2)}:${y2.toFixed(1)}`
      byRow.set(k, [...(byRow.get(k) || []), [x, w]])
    }
  }
  const tiled = [...byRow.values()].every(cells => {
    const sorted = cells.sort((a, b) => a[0] - b[0])
    return sorted.every((c, i) => i === sorted.length - 1 || Math.abs(c[0] + c[1] - sorted[i + 1][0]) < 0.6)
  })
  check('minutes .pdf table cells tile across each row', byRow.size > 0 && tiled, `${byRow.size} rows`)
  // EVERY row of every table has to be drawn. The first cut spread a whole
  // table into a one-argument helper, so each table drew its first row and
  // dropped the rest, and a check that only asked "is a row drawn" passed.
  const drawnRows = byRow.size
  check('minutes .pdf draws every table row, not just the first',
    drawnRows >= 8 + 1 + ACTIONS.length, `${drawnRows} rows drawn`)
  const wide = [...byRow.values()].filter(c => c.length === 6).length
  check('minutes .pdf draws the six-column actions table in full',
    wide === 1 + ACTIONS.length, `${wide} six-column rows`)
  // A short column too narrow for its own placeholder breaks it across lines
  // ("Not recorde / d"), which reads as a fault in the document.
  const runs = [...minutesPdfRaw.matchAll(/\((.*?)\) Tj/g)].map(m => m[1])
  check('minutes .pdf: no short table column breaks a word',
    runs.includes('Not recorded') && !runs.some(r => /recorde$|^d$/.test(r)),
    JSON.stringify(runs.filter(r => r.includes('recorde'))))
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
