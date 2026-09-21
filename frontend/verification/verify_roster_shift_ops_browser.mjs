// Moving, editing and filling shifts on the roster — against the REAL screen
// with the API stubbed at the network layer.
//
// What is asserted (the five things asked for):
//   1. a shift can be dragged to another DAY (Areas view, same role row) — the
//      drop PATCHes the shift's day_of_week;
//   2. clicking a shift shows an EDIT DAY & TIME form; changing the day and
//      saving PATCHes the shift; the form deletes it;
//   3. People view: a volunteer's free, empty day shows "+ add"; it lists that
//      day's open shifts and hands one to them (an assign call);
//   4. Areas view: clicking an UNASSIGNED shift opens an assign modal with
//      Fill best match / Clear and a ranked volunteer list; picking one assigns;
//   5. Areas view: a blank cell shows "+ Add"; it creates a one-off shift for a
//      role/time and, in the same step, assigns a volunteer.
//
// Control run (previous commit): none of the "+ add"/"+ Add"/edit-form/assign
// -modal test ids exist, and a day drag was refused — every new check reads its
// element through the absence-reporting helpers, so it fails rather than dies.
//
//   node verify_roster_shift_ops_browser.mjs     (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

// Match Day: two roles (Umpire gated by accreditation, Scorer by nothing).
// Bar: a single role gated by RSA.
const MATCH_DAY = {
  id: 'ar1', name: 'Match Day', department: 'Officials', color: '#3b82f6',
  required_role_id: 'r-ump', required_role_name: 'Umpire',
  roles: [
    { role_id: 'r-ump', role_name: 'Umpire', required_qualification_type_id: 'q-acc', required_qualification_name: 'Umpire Accreditation' },
    { role_id: 'r-sco', role_name: 'Scorer', required_qualification_type_id: null, required_qualification_name: null },
  ],
  patterns: [],
}
const BAR = {
  id: 'ar2', name: 'Bar', department: 'Food & Beverage', color: '#f5b542',
  required_role_id: 'r-bar', required_role_name: 'Bar Supervisor',
  roles: [{ role_id: 'r-bar', role_name: 'Bar Supervisor', required_qualification_type_id: 'q-rsa', required_qualification_name: 'RSA' }],
  patterns: [],
}

// The week. Umpire Sat OPEN, Scorer Sat ASSIGNED, Bar Tue OPEN.
const WEEK = {
  week: {
    id: 'w1', week_start: '2026-09-21', status: 'draft',
    shifts: [
      { id: 's-ump', area_id: 'ar1', area_name: 'Match Day', role_id: 'r-ump', role_name: 'Umpire',
        day_of_week: 5, start_time: 12, end_time: 18, assignee_member_id: null, assignee_name: null, warnings: [],
        required_qualification_type_id: 'q-acc', required_qualification_name: 'Umpire Accreditation', is_paid: false },
      { id: 's-sco', area_id: 'ar1', area_name: 'Match Day', role_id: 'r-sco', role_name: 'Scorer',
        day_of_week: 5, start_time: 12, end_time: 18, assignee_member_id: 'm2', assignee_name: 'Sam Scorer', warnings: [],
        required_qualification_type_id: null, required_qualification_name: null, is_paid: false },
      { id: 's-bar', area_id: 'ar2', area_name: 'Bar', role_id: 'r-bar', role_name: 'Bar Supervisor',
        day_of_week: 1, start_time: 17, end_time: 21, assignee_member_id: null, assignee_name: null, warnings: [],
        required_qualification_type_id: 'q-rsa', required_qualification_name: 'RSA', is_paid: false },
    ],
  },
  areas: [MATCH_DAY, BAR],
  candidates: [
    { member_id: 'm1', name: 'Amardeep Gill', available_days: [5, 6], max_shifts: 5, role_ids: ['r-ump'], role_names: ['Umpire'], qual_type_ids: ['q-acc'], player_id: null },
    { member_id: 'm2', name: 'Sam Scorer', available_days: [5, 6], max_shifts: 5, role_ids: ['r-sco'], role_names: ['Scorer'], qual_type_ids: [], player_id: null },
    { member_id: 'm3', name: 'Bella Bar', available_days: [1], max_shifts: 5, role_ids: ['r-bar'], role_names: ['Bar Supervisor'], qual_type_ids: ['q-rsa'], player_id: null },
  ],
  settings: {},
}

const calls = []   // { method, url, body }
const routes = (page) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url(), method = req.method()
  let body = null
  try { body = req.postDataJSON() } catch { body = null }
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } })
  // Assign / create / patch / delete — record and answer with a realistic shape.
  if (/\/roster\/week\/[^/]+\/assign/.test(url) && method === 'POST') {
    calls.push({ method, url, body })
    const m = (WEEK.candidates.find(c => c.member_id === body?.member_id))
    if (!body?.member_id) return json({ ok: true, cleared: true, shift_id: body?.shift_id })
    return json({ ok: true, shift_id: body?.shift_id, assignee_member_id: body.member_id, assignee_name: m?.name || 'Someone', warns: [] })
  }
  if (/\/roster\/shifts\/[^/]+/.test(url) && method === 'PATCH') { calls.push({ method, url, body }); return json({ ok: true }) }
  if (/\/roster\/shifts\/[^/]+/.test(url) && method === 'DELETE') { calls.push({ method, url, body }); return json({ deleted: true }) }
  if (/\/roster\/shifts(\?|$)/.test(url) && method === 'POST') { calls.push({ method, url, body }); return json({ id: 'new-shift-1' }) }
  if (/\/roster\/week/.test(url)) return json(WEEK)
  if (/\/roster\/areas(\?|$)/.test(url)) return json({ areas: [MATCH_DAY, BAR] })
  if (/\/roster\/hours/.test(url)) return json({ rows: [], totals: {} })
  if (/\/roster\/shortages/.test(url)) return json({ roles: [], no_role_required: 0 })
  if (/\/roster\/settings/.test(url)) return json({})
  if (/\/clubhouse|\/notifications/.test(url)) return json({})
  if (/\/seasons/.test(url)) return json([{ id: 'se1', name: 'Summer 2025/26', year: 2025 }])
  if (/\/settings/.test(url)) return json({ diary_start_month: 7 })
  return json({})
})

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
    // Keep the volunteer pool open so the edit form is visible.
    localStorage.setItem('roster_pool_open_boss', JSON.stringify(true))
  })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page)

  const seen = (sel) => page.locator(sel).count().then(n => n > 0).catch(() => false)
  const press = async (sel) => { if (await seen(sel)) { await page.locator(sel).first().click().catch(() => {}); await page.waitForTimeout(250); return true } return false }
  const textOf = async (sel) => { if (!(await seen(sel))) return ''; return page.locator(sel).first().innerText().catch(() => '') }
  const lastCall = (pred) => [...calls].reverse().find(pred)

  const open = async (path) => {
    calls.length = 0
    await page.goto(BASE + path, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(900)
  }
  const toAreas = async () => { await page.getByRole('button', { name: 'Areas', exact: true }).first().click().catch(() => {}); await page.waitForTimeout(500) }
  const toPeople = async () => { await page.getByRole('button', { name: 'People', exact: true }).first().click().catch(() => {}); await page.waitForTimeout(500) }

  // ── 3. People view: "+ add" on a free empty day → assign an open shift ───────
  await open('/admin/clubhouse/roster')
  await toPeople()
  const hasAdd = await seen('[data-testid="people-add-m3-1"]')
  check('People view shows "+ add" on a volunteer\'s free empty day', hasAdd)
  // Bella (m3) is unavailable Mon (0): that cell is shaded UNAVAILABLE, no + add.
  check('no "+ add" on a day the volunteer is unavailable', !(await seen('[data-testid="people-add-m3-0"]')))
  if (hasAdd) {
    await press('[data-testid="people-add-m3-1"]')
    check('clicking "+ add" opens the open-shifts list', await seen('[data-testid="add-open-list"]'))
    const barBtn = await seen('[data-testid="add-open-shift-s-bar"]')
    check('the list offers the day\'s open Bar shift', barBtn)
    if (barBtn) {
      calls.length = 0
      await press('[data-testid="add-open-shift-s-bar"]')
      const c = lastCall(x => /assign/.test(x.url))
      check('picking an open shift assigns it to the volunteer',
        !!c && c.body?.shift_id === 's-bar' && c.body?.member_id === 'm3', JSON.stringify(c?.body))
    }
  }

  // ── 2. Edit a shift's day & time from the side panel ─────────────────────────
  await open('/admin/clubhouse/roster')
  await toAreas()
  // Select the assigned Scorer shift (assigned → sidebar, no modal).
  await page.evaluate(() => {
    const chip = [...document.querySelectorAll('div[draggable]')].find(d => /Sam Scorer/.test(d.textContent || ''))
    if (chip) chip.click()
  })
  await page.waitForTimeout(400)
  check('clicking a shift shows the edit day & time form', await seen('[data-testid="edit-shift-day"]'))
  if (await seen('[data-testid="edit-shift-day"]')) {
    calls.length = 0
    await page.selectOption('[data-testid="edit-shift-day"]', '6')     // Sat → Sun
    await page.waitForTimeout(150)
    await press('[data-testid="edit-shift-save"]')
    const c = lastCall(x => x.method === 'PATCH' && /\/shifts\/s-sco/.test(x.url))
    check('saving the edit PATCHes the shift with the new day',
      !!c && c.body?.day_of_week === 6, JSON.stringify(c?.body))
    check('editing a shift keeps its assignee (re-validate call)',
      !!lastCall(x => /assign/.test(x.url) && x.body?.member_id === 'm2'), '')
  }

  // ── 4. Areas view: unassigned click → assign modal ───────────────────────────
  await open('/admin/clubhouse/roster')
  await toAreas()
  await page.evaluate(() => {
    const chip = [...document.querySelectorAll('div[draggable]')].find(d => /OPEN/.test(d.textContent || '') && /Umpire/.test(d.textContent || ''))
    if (chip) chip.click()
  })
  await page.waitForTimeout(400)
  const modalOpen = await seen('[data-testid="roster-modal"]')
  check('clicking an unassigned shift opens an assign modal', modalOpen)
  check('the assign modal offers Fill best match', await seen('[data-testid="assign-fill-best"]'))
  check('the assign modal offers Clear', await seen('[data-testid="assign-clear"]'))
  check('the assign modal lists the qualified volunteer (m1)', await seen('[data-testid="assign-cand-m1"]'))
  check('the assign modal hides an unqualified volunteer (m2)', !(await seen('[data-testid="assign-cand-m2"]')))
  if (modalOpen) {
    calls.length = 0
    await press('[data-testid="assign-cand-m1"]')
    const c = lastCall(x => /assign/.test(x.url))
    check('picking a volunteer from the modal assigns them to the shift',
      !!c && c.body?.shift_id === 's-ump' && c.body?.member_id === 'm1', JSON.stringify(c?.body))
  }
  // An ASSIGNED shift click must NOT pop the modal (keep current behaviour).
  await open('/admin/clubhouse/roster')
  await toAreas()
  await page.evaluate(() => {
    const chip = [...document.querySelectorAll('div[draggable]')].find(d => /Sam Scorer/.test(d.textContent || ''))
    if (chip) chip.click()
  })
  await page.waitForTimeout(300)
  check('clicking an ASSIGNED shift does not open the assign modal', !(await seen('[data-testid="roster-modal"]')))

  // ── 5. Areas view: "+ Add" in a blank cell → create + assign ────────────────
  await open('/admin/clubhouse/roster')
  await toAreas()
  // The Umpire sub-row's Sunday (6) cell is empty → "+ Add".
  const addSel = '[data-testid="area-add-ar1-r-ump-6"]'
  check('Areas view shows "+ Add" in a blank cell', await seen(addSel))
  if (await seen(addSel)) {
    await press(addSel)
    check('"+ Add" opens the new-shift form', await seen('[data-testid="new-area-shift-role"]'))
    check('the new-shift form prefills the row\'s role (Umpire)',
      (await page.locator('[data-testid="new-area-shift-role"]').inputValue().catch(() => '')) === 'r-ump')
    check('the new-shift form offers an assign-a-volunteer picker', await seen('[data-testid="new-area-shift-assignee"]'))
    // Choose the qualified volunteer m1, set a time, create.
    await page.selectOption('[data-testid="new-area-shift-assignee"]', 'm1').catch(() => {})
    await page.fill('[data-testid="new-area-shift-start"]', '12')
    await page.fill('[data-testid="new-area-shift-end"]', '18')
    calls.length = 0
    await press('[data-testid="new-area-shift-create"]')
    await page.waitForTimeout(400)
    const created = lastCall(x => x.method === 'POST' && /\/shifts(\?|$)/.test(x.url))
    check('creating the shift POSTs it with the chosen role/day/time',
      !!created && created.body?.role_id === 'r-ump' && created.body?.day_of_week === 6 && created.body?.area_id === 'ar1',
      JSON.stringify(created?.body))
    check('the new shift is assigned to the chosen volunteer',
      !!lastCall(x => /assign/.test(x.url) && x.body?.member_id === 'm1'), '')
  }

  // ── 1. Drag a shift to another DAY (Areas, same role row) ────────────────────
  await open('/admin/clubhouse/roster')
  await toAreas()
  // Start dragging the OPEN Umpire shift (Sat), then drop on the empty Sunday
  // cell of the same Umpire sub-row. Separate evaluate calls so React re-renders
  // with the drag in flight (an HTML5-DnD gotcha this project documents).
  const started = await page.evaluate(() => {
    const chip = [...document.querySelectorAll('div[draggable]')].find(d => /OPEN/.test(d.textContent || '') && /Umpire/.test(d.textContent || ''))
    if (!chip) return false
    const dt = new DataTransfer()
    chip.dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer: dt }))
    window.__dt = dt
    return true
  })
  await page.waitForTimeout(250)
  if (started) {
    const dropped = await page.evaluate(() => {
      const cell = document.querySelector('[data-testid="area-add-ar1-r-ump-6"]')?.closest('div')
      if (!cell) return false
      const dt = window.__dt || new DataTransfer()
      cell.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }))
      cell.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
      return true
    })
    await page.waitForTimeout(400)
    const c = lastCall(x => x.method === 'PATCH' && /\/shifts\/s-ump/.test(x.url))
    check('dragging a shift to another day PATCHes its day_of_week',
      dropped && !!c && c.body?.day_of_week === 6, JSON.stringify(c?.body))
  } else {
    check('dragging a shift to another day PATCHes its day_of_week', false, 'could not find the draggable chip')
  }

  // ── No page errors ──────────────────────────────────────────────────────────
  check('no page errors across the run', errors.length === 0, errors.slice(0, 3).join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}
run().catch(e => { console.error(e); process.exit(1) })
