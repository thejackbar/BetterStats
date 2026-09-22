// Roster: the "To fill" worklist, carry-selection across the toggle, and the
// single-day Match-day board — against the REAL screen, API stubbed.
//
//   1. To fill  — a ranked list of the week's gaps; assign the best fit in one
//      tap, or choose someone else. The tab carries an open-count badge.
//   2. Carry state — selecting a shift and switching People⇄Areas⇄Match day
//      keeps the selection (the chip keeps its ring on the other view).
//   3. Match day — one day at a time; a day picker; areas/roles down the side;
//      an OPEN cell opens the assign modal (the same areaDayCol as Areas view).
//
// Control run (previous commit): the day/fill tabs, roster-fill, dayboard-* and
// fill-* test ids don't exist; every new check reads through the absence helpers
// and FAILS rather than dies.
//   node verify_roster_combined_views_browser.mjs   (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

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
// Umpire Sat OPEN, Scorer Sat ASSIGNED, Bar Tue OPEN → two gaps (Tue, Sat).
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

const calls = []
const routes = (page) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url(), method = req.method()
  let body = null
  try { body = req.postDataJSON() } catch { body = null }
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } })
  if (/\/roster\/week\/[^/]+\/assign/.test(url) && method === 'POST') {
    calls.push({ method, url, body })
    const m = WEEK.candidates.find(c => c.member_id === body?.member_id)
    if (!body?.member_id) return json({ ok: true, cleared: true, shift_id: body?.shift_id })
    return json({ ok: true, shift_id: body?.shift_id, assignee_member_id: body.member_id, assignee_name: m?.name || 'Someone', warns: [] })
  }
  if (/\/roster\/shifts\/[^/]+/.test(url) && method === 'PATCH') { calls.push({ method, url, body }); return json({ ok: true }) }
  if (/\/roster\/shifts\/[^/]+/.test(url) && method === 'DELETE') { calls.push({ method, url, body }); return json({ deleted: true }) }
  if (/\/roster\/shifts(\?|$)/.test(url) && method === 'POST') { calls.push({ method, url, body }); return json({ id: 'new-shift-1' }) }
  if (/\/roster\/week/.test(url)) {
    // Honour the requested week_start so the paging pills read realistically.
    const ws = new URL(url).searchParams.get('week_start') || '2026-09-21'
    calls.push({ method: 'GET', url, weekStart: ws })
    return json({ ...WEEK, week: { ...WEEK.week, week_start: ws } })
  }
  if (/\/roster\/areas(\?|$)/.test(url)) return json({ areas: [MATCH_DAY, BAR] })
  if (/\/roster\/hours/.test(url)) return json({ rows: [], totals: {} })
  if (/\/roster\/shortages/.test(url)) return json({ roles: [], no_role_required: 0 })
  if (/\/roster\/settings/.test(url)) return json({})
  if (/\/volunteers\/members(\?|$)/.test(url)) return json({ members: [], more: false })
  if (/\/roles-activities\/roles/.test(url)) return json({ roles: [] })
  if (/\/qualifications\/types/.test(url)) return json({ types: [] })
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
  })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page)

  const seen = (sel) => page.locator(sel).count().then(n => n > 0).catch(() => false)
  const press = async (sel) => { if (await seen(sel)) { await page.locator(sel).first().click().catch(() => {}); await page.waitForTimeout(250); return true } return false }
  const textOf = async (sel) => { if (!(await seen(sel))) return ''; return page.locator(sel).first().innerText().catch(() => '') }
  const lastCall = (pred) => [...calls].reverse().find(pred)
  // Non-exact: the "To fill" tab carries a count badge, so its accessible name
  // is "To fill 2", not "To fill".
  const tab = async (label) => { await page.getByRole('button', { name: label }).first().click().catch(() => {}); await page.waitForTimeout(450) }

  await page.goto(BASE + '/admin/clubhouse/roster', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(900)

  // ── The two new tabs exist ────────────────────────────────────────────────
  check('a "Match day" tab is offered', await seen('button:has-text("Match day")'))
  check('a "To fill" tab is offered', await seen('button:has-text("To fill")'))

  // ── 1. To fill worklist ───────────────────────────────────────────────────
  await tab('To fill')
  check('the To fill tab shows the worklist', await seen('[data-testid="roster-fill"]'))
  check('both gaps are listed (Umpire Sat, Bar Tue)',
    await seen('[data-testid="fill-row-s-ump"]') && await seen('[data-testid="fill-row-s-bar"]'))
  // Bar Tue sorts before Umpire Sat (soonest first): the Bar row is above.
  const order = await page.evaluate(() => {
    const ids = [...document.querySelectorAll('[data-testid^="fill-row-"]')].map(d => d.getAttribute('data-testid'))
    return ids
  })
  check('gaps are ordered soonest first (Tue before Sat)',
    order.indexOf('fill-row-s-bar') > -1 && order.indexOf('fill-row-s-bar') < order.indexOf('fill-row-s-ump'), JSON.stringify(order))
  check('the Umpire gap suggests its best fit (m1) to assign', await seen('[data-testid="fill-assign-s-ump"]'))
  const bestTxt = await textOf('[data-testid="fill-row-s-ump"]')
  check('the suggested best fit is the qualified, available volunteer', /Amardeep/.test(bestTxt), bestTxt)
  // Assign the best fit in one tap.
  calls.length = 0
  await press('[data-testid="fill-assign-s-ump"]')
  const ac = lastCall(x => /assign/.test(x.url))
  check('tapping Assign rosters the best fit onto that shift',
    !!ac && ac.body?.shift_id === 's-ump' && ac.body?.member_id === 'm1', JSON.stringify(ac?.body))
  // Choose someone else opens the assign modal.
  await press('[data-testid="fill-choose-s-bar"]')
  check('"Choose…" opens the assign modal for that shift', await seen('[data-testid="roster-modal"]'))
  await page.keyboard.press('Escape').catch(() => {})
  await page.waitForTimeout(200)

  // ── 3. Match day board ────────────────────────────────────────────────────
  // Reload first: the To-fill section above assigned s-ump (optimistic local
  // state), so a fresh WEEK is needed for it to read OPEN again.
  await page.goto(BASE + '/admin/clubhouse/roster', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(800)
  await tab('Match day')
  check('the Match day board shows a day picker', await seen('[data-testid="dayboard-picker"]'))
  check('the board lists the areas down the side', await seen('[data-testid="dayboard-area-ar1"]') && await seen('[data-testid="dayboard-area-ar2"]'))
  // Default opens on the soonest day with a gap — Tuesday (Bar), day 1.
  const barTue = await textOf('[data-testid="dayboard-role-ar2-r-bar"]')
  check('it opens on the soonest gap day (Tue), Bar shift OPEN', /OPEN/.test(barTue), barTue)
  // Switch to Saturday: the Umpire cell now shows its OPEN shift.
  await press('[data-testid="dayboard-pick-5"]')
  const umpSat = await textOf('[data-testid="dayboard-role-ar1-r-ump"]')
  check('picking Saturday shows that day\'s shifts (Umpire OPEN)', /OPEN/.test(umpSat), umpSat)
  const scoSat = await textOf('[data-testid="dayboard-role-ar1-r-sco"]')
  check('the assigned Scorer shows on the same day', /Sam Scorer/.test(scoSat), scoSat)
  // Clicking the OPEN Umpire chip opens the assign modal (reused areaDayCol).
  await page.evaluate(() => {
    const cell = document.querySelector('[data-testid="dayboard-role-ar1-r-ump"]')
    const chip = cell && [...cell.querySelectorAll('div[draggable]')].find(d => /OPEN/.test(d.textContent || ''))
    if (chip) chip.click()
  })
  await page.waitForTimeout(300)
  check('clicking an OPEN cell on the board opens the assign modal', await seen('[data-testid="roster-modal"]'))
  await page.keyboard.press('Escape').catch(() => {})
  await page.waitForTimeout(200)

  // ── 2. Carry selection across the toggle ─────────────────────────────────
  // Select the assigned Scorer on Areas (opens its detail modal), close it, and
  // the chip keeps its selected ring. Switch to People and the SAME shift's chip
  // there carries the ring too — selection is not cleared on a view change.
  await page.goto(BASE + '/admin/clubhouse/roster', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(800)
  await tab('Areas')
  await page.evaluate(() => {
    const chip = [...document.querySelectorAll('div[draggable]')].find(d => /Sam Scorer/.test(d.textContent || ''))
    if (chip) chip.click()
  })
  await page.waitForTimeout(300)
  check('clicking a shift opens its detail modal', await seen('[data-testid="roster-modal"]'))
  await page.keyboard.press('Escape').catch(() => {})
  await page.waitForTimeout(200)
  const selectedOnAreas = await seen('[data-shift-chip="s-sco"][data-shift-selected="true"]')
  check('the selected shift keeps its ring on Areas', selectedOnAreas)
  await tab('People')
  await page.waitForTimeout(300)
  const selectedOnPeople = await seen('[data-shift-chip="s-sco"][data-shift-selected="true"]')
  check('switching Areas⇄People keeps the selected shift (its chip stays ringed)', selectedOnPeople)

  // ── Volunteer column removed; its controls relocated ─────────────────────
  await page.goto(BASE + '/admin/clubhouse/roster', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(800)
  check('the persistent volunteer pool column is gone', !(await seen('[data-testid="roster-pool"]')))
  // The Roles filter now sits on the detail page and narrows the LEFT list.
  check('the Roles filter sits on the detail page', await seen('[data-testid="role-filter"]'))
  await page.selectOption('[data-testid="role-filter"]', 'Umpire').catch(() => {})
  await page.waitForTimeout(300)
  check('filtering to a role keeps only that role\'s volunteers in the list',
    (await seen('[data-testid="people-roles-m1"]')) && !(await seen('[data-testid="people-roles-m3"]')))
  await press('[data-testid="role-filter-clear"]')
  check('clearing the role filter restores the full list', await seen('[data-testid="people-roles-m3"]'))
  // "+ Add a shift" is a toolbar button opening a modal (was a pool panel).
  await press('[data-testid="add-shift-open"]')
  check('"+ Add a shift" is a toolbar button that opens a modal',
    (await seen('[data-testid="roster-modal"]')) && (await seen('[data-testid="add-shift-role"]')))
  await page.keyboard.press('Escape').catch(() => {})
  await page.waitForTimeout(200)

  // ── Week paging pills ─────────────────────────────────────────────────────
  const weekFetch = () => [...calls].reverse().find(x => x.weekStart)
  check('week paging pills are shown', await seen('[data-testid="week-prior"]') && await seen('[data-testid="week-this"]') && await seen('[data-testid="week-next"]'))
  calls.length = 0
  await press('[data-testid="week-prior"]'); await page.waitForTimeout(300)
  check('Prior loads the previous week', weekFetch()?.weekStart === '2026-09-14', weekFetch()?.weekStart)
  calls.length = 0
  await press('[data-testid="week-next"]'); await page.waitForTimeout(300)   // 14th → 21st
  check('Next pages forward a week', weekFetch()?.weekStart === '2026-09-21', weekFetch()?.weekStart)
  calls.length = 0
  await press('[data-testid="week-next"]'); await page.waitForTimeout(300)   // 21st → 28th
  check('Next again reaches the following week', weekFetch()?.weekStart === '2026-09-28', weekFetch()?.weekStart)
  calls.length = 0
  await press('[data-testid="week-this"]'); await page.waitForTimeout(300)   // back to this Monday
  check('This week returns to the current week (this Monday)', weekFetch()?.weekStart === '2026-09-21', weekFetch()?.weekStart)

  check('no page errors across the run', errors.length === 0, errors.slice(0, 3).join(' | '))
  await page.close()

  // ── No horizontal overflow at phone width on the two new views ────────────
  const narrow = await ctx.newPage()
  await narrow.setViewportSize({ width: 390, height: 780 })
  const nerr = []
  narrow.on('pageerror', e => nerr.push(String(e)))
  await routes(narrow)
  await narrow.goto(BASE + '/admin/clubhouse/roster', { waitUntil: 'domcontentloaded' })
  await narrow.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
  await narrow.waitForTimeout(900)
  const noOverflow = async () => narrow.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)
  await narrow.getByRole('button', { name: 'To fill' }).first().click().catch(() => {})
  await narrow.waitForTimeout(400)
  check('the To fill worklist does not overflow at 390px', await noOverflow())
  await narrow.getByRole('button', { name: 'Match day' }).first().click().catch(() => {})
  await narrow.waitForTimeout(400)
  check('the Match day board does not overflow at 390px', await noOverflow())
  check('no page errors at phone width', nerr.length === 0, nerr.slice(0, 3).join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}
run().catch(e => { console.error(e); process.exit(1) })
