// The Club Diary landing — Overview / List / Calendar / Timeline / By-role, the
// responsibility linkage (task → committee seat → current holder), and the
// actionable drawer — against the REAL screen with the API stubbed at the
// network layer.
//
// What is asserted:
//   * the landing opens on OVERVIEW: a stat strip, a "needs attention now" list
//     (an overdue and a blocked task), and each row carries role → holder;
//   * a VACANT committee seat that owns tasks is called out (Secretary);
//   * "coming up" honours the window toggle (this month lists the near task, not
//     the far one; Next 90 days adds it) — a CONTRAST, so it can't pass vacuously;
//   * a standing (weekly) duty shows as an ongoing duty, not a dated task;
//   * status is a COLOUR AND A WORD (protanopia rule): the badge has a label and
//     a coloured border;
//   * List renders rows and its search keeps focus per character;
//   * Calendar (Month) draws a task that SPANS more than one day cell, and Year
//     zoom places it in a month cell;
//   * By role lists a seat's tasks, flags the vacant seat, and lists a seat with
//     no diary tasks separately;
//   * the drawer opens from any view, names the responsible seat + holder, and
//     "Done" sends a PATCH {status:'done'} on the wire AND the task then reads DONE;
//   * Timeline renders the gantt; Setup opens the templates surface;
//   * no page errors, and no horizontal overflow at 390px.
//
// Control run (previous commit): the old screen has none of these views/testids,
// so every new check reads through the absence-reporting helpers and fails
// rather than throwing.
//
//   node verify_club_diary_browser.mjs          (dev/preview server on :5199)
//   node verify_club_diary_browser.mjs http://localhost:4173
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://localhost:5199'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

// ── Stub data ────────────────────────────────────────────────────────────────
// Session date is 2026-09-21; dates are chosen relative to it. A quarterly BAS
// is overdue (10 Sep) and owned by the Treasurer (held by Jane Doe); an Annual
// return is due soon (24 Sep) and owned by the Secretary (a VACANT seat); File
// financials depends on the overdue BAS so it reads BLOCKED; a weekly wicket-prep
// is a standing duty (no occurrence); insurance is done.
const ROLES = [
  { id: 'role-treas', title: 'Treasurer', is_committee: true },
  { id: 'role-sec', title: 'Secretary', is_committee: true },
  { id: 'role-grounds', title: 'Grounds', is_committee: true },
  { id: 'role-social', title: 'Social', is_committee: true },
  { id: 'role-vol', title: 'Volunteer', is_committee: false },
]
const POSITIONS = [
  { id: 'p-treas', name: 'Treasurer', role_id: 'role-treas', responsibilities: 'Money', is_active: true, current_term: { holder_name: 'Jane Doe', member_id: 'm1', is_current: true } },
  { id: 'p-sec', name: 'Secretary', role_id: 'role-sec', responsibilities: 'Minutes', is_active: true, current_term: null },
  { id: 'p-grounds', name: 'Grounds', role_id: 'role-grounds', responsibilities: 'Pitch & outfield', is_active: true, current_term: { holder_name: 'Bob Roe', member_id: 'm2', is_current: true } },
  { id: 'p-social', name: 'Social', role_id: 'role-social', responsibilities: 'Events', is_active: true, current_term: { holder_name: 'Sue Poe', member_id: null, is_current: true } },
]
const MEMBERS = [{ member_id: 'm1', full_name: 'Jane Doe' }, { member_id: 'm2', full_name: 'Bob Roe' }]

const occ = (o) => ({ percent_complete: 0, is_late: false, over_budget: false, budget_estimate: 0, actual_expenditure: 0, assigned_to_member_id: null, start_date: null, ...o })
const BOARD = [
  { id: 'd1', title: 'BAS lodgement', description: 'Lodge the quarter BAS', frequency: 'quarterly', responsibility_role_id: 'role-treas', default_assignee_member_id: null, budget_estimate: 0, depends_on: [], occurrence: occ({ id: 'o1', definition_id: 'd1', due_date: '2026-09-10', status: 'pending', is_late: true, assigned_to_role_id: 'role-treas' }) },
  { id: 'd2', title: 'Annual return', frequency: 'annual', responsibility_role_id: 'role-sec', budget_estimate: 0, depends_on: [], occurrence: occ({ id: 'o2', definition_id: 'd2', due_date: '2026-09-24', status: 'pending', assigned_to_role_id: 'role-sec' }) },
  { id: 'd3', title: 'Ground preparation', frequency: 'annual', responsibility_role_id: 'role-grounds', budget_estimate: 500, depends_on: [], occurrence: occ({ id: 'o3', definition_id: 'd3', due_date: '2026-10-30', status: 'in_progress', percent_complete: 40, assigned_to_role_id: 'role-grounds', budget_estimate: 500, actual_expenditure: 120 }) },
  { id: 'd4', title: 'Weekly wicket prep', frequency: 'weekly', responsibility_role_id: 'role-grounds', budget_estimate: 0, depends_on: [], occurrence: null },
  { id: 'd5', title: 'Insurance renewal', frequency: 'annual', responsibility_role_id: 'role-treas', budget_estimate: 0, depends_on: [], occurrence: occ({ id: 'o5', definition_id: 'd5', due_date: '2026-09-05', status: 'done', percent_complete: 100, assigned_to_role_id: 'role-treas' }) },
  { id: 'd6', title: 'File financials', frequency: 'annual', responsibility_role_id: 'role-treas', budget_estimate: 0, depends_on: ['d1'], occurrence: occ({ id: 'o6', definition_id: 'd6', due_date: '2026-11-10', status: 'pending', assigned_to_role_id: 'role-treas' }) },
]
// The full-year dated occurrences (List / Calendar / Timeline). "Season launch
// project" spans 1–19 Sep 2026, so on the Month calendar it covers several day
// cells within a week.
const sk = (o) => ({ percent_complete: 0, is_late: false, over_budget: false, budget_estimate: 0, actual_expenditure: 0, assigned_to_member_id: null, start_date: null, depends_on: [], category_name: null, category_color: '#8b7cf6', ...o })
const SEASON_TASKS = [
  sk({ id: 'o1', definition_id: 'd1', title: 'BAS lodgement', frequency: 'quarterly', due_date: '2026-09-10', status: 'pending', is_late: true, assigned_to_role_id: 'role-treas', category_name: 'Tax & Finance', category_color: '#22c55e' }),
  sk({ id: 'o2', definition_id: 'd2', title: 'Annual return', frequency: 'annual', due_date: '2026-09-24', status: 'pending', assigned_to_role_id: 'role-sec', category_name: 'Compliance', category_color: '#ef4444' }),
  sk({ id: 'sp', definition_id: 'd7', title: 'Season launch project', frequency: 'once', start_date: '2026-09-01', due_date: '2026-09-19', status: 'in_progress', percent_complete: 30, assigned_to_role_id: 'role-social', category_name: 'Events', category_color: '#8b7cf6' }),
  sk({ id: 'o3', definition_id: 'd3', title: 'Ground preparation', frequency: 'annual', due_date: '2026-10-30', status: 'in_progress', percent_complete: 40, assigned_to_role_id: 'role-grounds', category_name: 'Ground', category_color: '#f59e0b' }),
]

// The PATCH the drawer sends is recorded, and the occurrence's new status is
// applied on the next board/season read so the UI genuinely updates.
const patched = {}

const routes = (page, calls) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url()
  const method = req.method()
  const body = req.postData() || ''
  calls.push({ url, method, body })
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  const applyPatch = (o) => (o && patched[o.id] ? { ...o, ...patched[o.id] } : o)

  if (/\/club-diary\/occurrences\//.test(url) && method === 'PATCH') {
    const id = url.split('/occurrences/')[1].split(/[?#]/)[0]
    let f = {}; try { f = JSON.parse(body || '{}') } catch { /* */ }
    patched[id] = { ...(patched[id] || {}), ...f }
    return json({ id, ...f })
  }
  if (/\/auth\/me/.test(url)) {
    return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } })
  }
  if (/\/club-diary\/board/.test(url)) return json({ tasks: BOARD.map(t => ({ ...t, occurrence: applyPatch(t.occurrence) })) })
  if (/\/club-diary\/season-years/.test(url)) return json({ years: [2026] })
  if (/\/club-diary\/season\/\d+/.test(url)) return json({ year: 2026, tasks: SEASON_TASKS.map(applyPatch) })
  if (/\/club-diary\/definitions/.test(url)) return json({ definitions: BOARD.map(t => ({ id: t.id, title: t.title, frequency: t.frequency, responsibility_role_id: t.responsibility_role_id, budget_estimate: t.budget_estimate, depends_on: t.depends_on })) })
  if (/\/committee\/positions\/current/.test(url)) return json({ positions: POSITIONS })
  if (/\/roles-activities\/roles/.test(url)) return json({ roles: ROLES })
  if (/\/fees\/all-members/.test(url)) return json({ members: MEMBERS })
  if (/\/settings/.test(url)) return json({ diary_start_month: 7 })
  if (/\/clubhouse|\/notifications/.test(url)) return json({})
  return json({})
})

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  // Short default so a missing control (a view/tab that the old screen doesn't
  // have) fails a click in seconds rather than the 30s Playwright default.
  page.setDefaultTimeout(5000)
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  const calls = []
  await routes(page, calls)

  // Absence-reporting helpers, so the control run fails cleanly.
  const seen = (sel) => page.locator(sel).count().then(n => n > 0).catch(() => false)
  const countOf = (sel) => page.locator(sel).count().catch(() => 0)
  const textOf = async (sel) => { if (!(await seen(sel))) return ''; return page.locator(sel).first().innerText().catch(() => '') }
  const attrOf = async (sel, name) => { if (!(await seen(sel))) return ''; return (await page.locator(sel).first().getAttribute(name).catch(() => '')) || '' }
  const bodyText = () => page.locator('body').innerText().catch(() => '')
  const press = async (sel) => { if (await seen(sel)) { await page.locator(sel).first().click().catch(() => {}); await page.waitForTimeout(300); return true } return false }
  const tab = async (name) => { await page.getByRole('button', { name, exact: true }).first().click().catch(() => {}); await page.waitForTimeout(400) }
  const noOverflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)

  await page.goto(BASE + '/admin/club-diary', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(1400)

  // ── Overview ────────────────────────────────────────────────────────────────
  const overviewBody = await bodyText()
  check('opens on the Overview (stat strip present)', /OVERDUE/.test(overviewBody) && /ON TRACK/.test(overviewBody), overviewBody.slice(0, 60))

  const attnCount = await countOf('[data-testid="diary-attn"]')
  check('needs-attention lists the overdue and the blocked task', attnCount === 2, `attn=${attnCount}`)

  const attnAll = await page.locator('[data-testid="diary-attn"]').allInnerTexts().catch(() => [])
  const attnJoined = attnAll.join(' | ')
  check('an attention row carries role → holder (Treasurer → Jane Doe)', /Treasurer/.test(attnJoined) && /Jane Doe/.test(attnJoined), attnJoined.slice(0, 120))
  check('the blocked task reads BLOCKED', attnAll.some(x => /BLOCKED/.test(x)), attnJoined.slice(0, 120))
  check('the overdue task reads OVERDUE', attnAll.some(x => /OVERDUE/.test(x)), attnJoined.slice(0, 120))

  check('a VACANT committee seat is surfaced on the landing', /VACANT/.test(overviewBody), 'no VACANT on overview')

  // coming up — scoped to the coming section itself, so it's a genuine contrast:
  // "this month" (default) lists the near task and NOT the far one; widening to
  // Next 90 days adds the far one.
  const comingMonth = await textOf('[data-testid="diary-coming"]')
  check('coming-up (this month) shows the near due task', /Annual return/.test(comingMonth), comingMonth.slice(0, 120))
  check('coming-up (this month) excludes the far task', !/Ground preparation/.test(comingMonth), comingMonth.slice(0, 120))
  await page.getByRole('button', { name: 'Next 90 days', exact: true }).click().catch(() => {})
  await page.waitForTimeout(400)
  const coming90 = await textOf('[data-testid="diary-coming"]')
  check('widening to Next 90 days adds the far task (contrast)', /Ground preparation/.test(coming90), coming90.slice(0, 120))

  check('the weekly standing task shows as an ongoing duty', /ONGOING DUTIES/.test(overviewBody) && /Weekly wicket prep/.test(overviewBody))

  // status is a colour AND a word
  const badgeText = await textOf('[data-testid="diary-status"]')
  const badgeBorder = await page.locator('[data-testid="diary-status"]').first().evaluate(el => getComputedStyle(el).borderColor).catch(() => '')
  check('status is shown as a word', badgeText.trim().length > 0, JSON.stringify(badgeText))
  check('status is also shown as a colour (coloured border)', badgeBorder && badgeBorder !== 'rgba(0, 0, 0, 0)' && badgeBorder !== 'transparent', badgeBorder)

  const ovf = await noOverflow()
  check('overview: no horizontal overflow at 1500px', ovf <= 1, `overflow ${ovf}px`)

  // ── List ─────────────────────────────────────────────────────────────────────
  await tab('List')
  const rows = await countOf('[data-testid="diary-list-row"]')
  check('List renders task rows', rows >= 3, `rows=${rows}`)
  const rowStatuses = await page.locator('[data-testid="diary-list-row"]').evaluateAll(els => els.map(e => e.getAttribute('data-status'))).catch(() => [])
  check('a List row carries its status', rowStatuses.some(s => s === 'overdue'), JSON.stringify(rowStatuses))
  // search keeps focus per character
  await page.fill('input[placeholder*="Search tasks"]', '').catch(() => {})
  let held = true
  for (const ch of 'BAS') {
    await page.type('input[placeholder*="Search tasks"]', ch, { delay: 30 }).catch(() => { held = false })
    const active = await page.evaluate(() => document.activeElement && document.activeElement.tagName).catch(() => '')
    if (active !== 'INPUT') held = false
  }
  const searchVal = await page.inputValue('input[placeholder*="Search tasks"]').catch(() => '')
  check('List search keeps focus per character', held && searchVal === 'BAS', `held=${held} val=${searchVal}`)
  await page.fill('input[placeholder*="Search tasks"]', '').catch(() => {})
  await page.waitForTimeout(200)

  // season selector present on List
  check('the season selector is shown on a date view', await seen('select'), 'no select on List')

  // ── Calendar ─────────────────────────────────────────────────────────────────
  await tab('Calendar')
  await page.waitForTimeout(500)
  const bandCount = await countOf('[data-testid="diary-cal-band"]')
  const spans = await page.locator('[data-testid="diary-cal-band"]').evaluateAll(els => els.map(e => Number(e.getAttribute('data-span')))).catch(() => [])
  check('Month calendar draws task bands', bandCount >= 1, `bands=${bandCount}`)
  check('a multi-week task spans more than one day cell', spans.some(n => n >= 2), JSON.stringify(spans))
  // Year zoom places the task in a month cell
  await page.getByRole('button', { name: 'Year', exact: true }).click().catch(() => {})
  await page.waitForTimeout(400)
  const yearBands = await countOf('[data-testid="diary-cal-year-band"]')
  check('Year calendar places tasks in month cells', yearBands >= 1, `yearBands=${yearBands}`)

  // ── By role ──────────────────────────────────────────────────────────────────
  await tab('By role')
  await page.waitForTimeout(400)
  const seatCount = await countOf('[data-testid="diary-seat"]')
  check('By role draws a seat card per owning seat', seatCount >= 2, `seats=${seatCount}`)
  const treasCard = await page.locator('[data-testid="diary-seat"]', { hasText: 'Treasurer' }).first().innerText().catch(() => '')
  check('the Treasurer card names the current holder', /Jane Doe/.test(treasCard), treasCard.slice(0, 80))
  check('the Treasurer card lists its tasks (the overdue BAS)', /BAS lodgement/.test(treasCard), treasCard.slice(0, 120))
  const vacantSeats = await countOf('[data-testid="diary-seat"][data-vacant="1"]')
  const vacantText = await textOf('[data-testid="diary-seat"][data-vacant="1"]')
  check('a vacant seat that owns tasks is flagged', vacantSeats >= 1 && /VACANT/.test(vacantText), `vacant=${vacantSeats} ${vacantText.slice(0, 60)}`)
  const rolesBody = await bodyText()
  check('a seat with no diary tasks is listed separately', /SEATS WITH NO DIARY TASKS/.test(rolesBody) && /Social/.test(rolesBody))

  // ── Timeline ─────────────────────────────────────────────────────────────────
  await tab('Timeline')
  await page.waitForTimeout(500)
  const timelineBody = await bodyText()
  check('Timeline renders the gantt with the tasks', /Annual return/.test(timelineBody) || /BAS lodgement/.test(timelineBody), timelineBody.slice(0, 80))

  // ── Setup → templates ────────────────────────────────────────────────────────
  await page.getByRole('button', { name: /Setup/, exact: false }).first().click().catch(() => {})
  await page.waitForTimeout(300)
  await page.getByText('Task templates', { exact: true }).click().catch(() => {})
  await page.waitForTimeout(500)
  const tplBody = await bodyText()
  check('Setup opens the templates & season-setup surface', /TEMPLATES & SEASON SETUP/.test(tplBody) || /GENERATE A SEASON/.test(tplBody), tplBody.slice(0, 80))
  await page.getByRole('button', { name: /Back to diary/, exact: false }).first().click().catch(() => {})
  await page.waitForTimeout(400)

  // ── Actionable drawer (open from Overview, mark Done → PATCH on the wire) ─────
  await tab('Overview')
  await page.waitForTimeout(400)
  await press('[data-testid="diary-attn"]')  // opens the first attention task (overdue BAS)
  check('the task drawer opens from a view', await seen('[data-testid="diary-drawer"]'))
  const drawerText = await textOf('[data-testid="diary-drawer"]')
  check('the drawer names the responsible seat + holder', /Treasurer/.test(drawerText) && /Jane Doe/.test(drawerText), drawerText.slice(0, 120))

  calls.length = 0
  await page.locator('[data-testid="diary-drawer"]').getByRole('button', { name: 'Done', exact: true }).click().catch(() => {})
  await page.waitForTimeout(900)
  const patch = calls.find(c => c.method === 'PATCH' && /\/occurrences\/o1/.test(c.url))
  let patchBody = {}; try { patchBody = JSON.parse(patch?.body || '{}') } catch { /* */ }
  check('marking Done sends a PATCH to the occurrence', !!patch, patch ? patch.url : 'no PATCH sent')
  check('the PATCH sets status=done on the wire', patchBody.status === 'done', JSON.stringify(patchBody))
  const drawerStatus = await attrOf('[data-testid="diary-drawer"]', 'data-status')
  check('the task then reads DONE (the change is reflected)', drawerStatus === 'done', `drawer data-status=${drawerStatus}`)

  // ── 390px + page errors ──────────────────────────────────────────────────────
  await page.setViewportSize({ width: 390, height: 844 })
  await page.keyboard.press('Escape').catch(() => {})
  await tab('Overview')
  await page.waitForTimeout(400)
  const ovfPhone = await noOverflow()
  check('no horizontal overflow at 390px (Overview)', ovfPhone <= 1, `overflow ${ovfPhone}px`)
  await tab('List')
  const ovfList = await noOverflow()
  check('no horizontal overflow at 390px (List has an inner scroll, page does not)', ovfList <= 1, `overflow ${ovfList}px`)

  check('no page errors', errors.length === 0, errors.slice(0, 3).join(' ; '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:'); FAIL.forEach(f => console.log('  - ' + f)) }
  process.exit(FAIL.length ? 1 : 0)
}

run().catch(e => { console.error(e); process.exit(2) })
