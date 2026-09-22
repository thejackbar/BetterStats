// The People-view left column — against the REAL screen with the API stubbed.
//
// What is asserted (the three things asked for):
//   1. a volunteer's ROLES show beneath their name, always, with a "+ Add" that
//      opens a role picker; picking a role POSTs the merged role set to the
//      volunteer's profile;
//   2. clicking a volunteer expands their AVAILABILITY buttons inline on the
//      left; toggling a day PUTs the new availability;
//   3. an "+ Add volunteer" launcher above the list opens a modal that searches
//      every club member; picking one, giving them roles/availability (and,
//      where the user holds MANAGE_QUALIFICATIONS, qualifications) POSTs a
//      volunteer profile (+ a qualification per ticked accreditation).
//   Plus the capability gate: the qualifications section shows for a club_admin
//   and NOT for a club_member without MANAGE_QUALIFICATIONS.
//
// Control run (previous commit): none of the people-roles/add-role/
// people-avail/add-volunteer test ids exist, so every new check reads its
// element through the absence-reporting helpers and FAILS rather than dies:
//   git stash push -- src/pages/.../screens/Roster.jsx  (then re-run, expect fails)
//
//   node verify_roster_left_column_browser.mjs      (expects the dev server on :5199)
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

// m1 holds the Umpire role and is available Sat/Sun; m2 holds Scorer.
const WEEK = {
  week: {
    id: 'w1', week_start: '2026-09-21', status: 'draft',
    shifts: [
      { id: 's-sco', area_id: 'ar1', area_name: 'Match Day', role_id: 'r-sco', role_name: 'Scorer',
        day_of_week: 5, start_time: 12, end_time: 18, assignee_member_id: 'm2', assignee_name: 'Sam Scorer', warnings: [], is_paid: false },
    ],
  },
  areas: [MATCH_DAY],
  candidates: [
    { member_id: 'm1', name: 'Amardeep Gill', available_days: [5, 6], max_shifts: 5, role_ids: ['r-ump'], role_names: ['Umpire'], qual_type_ids: ['q-acc'], player_id: null },
    { member_id: 'm2', name: 'Sam Scorer', available_days: [5, 6], max_shifts: 5, role_ids: ['r-sco'], role_names: ['Scorer'], qual_type_ids: [], player_id: null },
  ],
  settings: {},
}

// The club's role catalogue (raRoles) and qualification types (qualListTypes).
// r-gnd is a role m1 does NOT hold, so the "+ Add role" picker has something.
const ROLES = [
  { id: 'r-ump', title: 'Umpire' },
  { id: 'r-sco', title: 'Scorer' },
  { id: 'r-gnd', title: 'Groundskeeper' },
]
const QUAL_TYPES = [
  { id: 'q-acc', name: 'Umpire Accreditation' },
  { id: 'q-rsa', name: 'RSA' },
]
// Club members for the add-volunteer search: an existing volunteer and a new one.
const MEMBERS = [
  { member_id: 'm1', full_name: 'Amardeep Gill', email: 'a@x.co', is_volunteer: true },
  { member_id: 'm9', full_name: 'Nina New', email: 'nina@x.co', is_volunteer: false },
]

const calls = []
const routes = (page, user) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url(), method = req.method()
  let body = null
  try { body = req.postDataJSON() } catch { body = null }
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) return json(user)
  // Task-3 writes — record and answer realistically.
  if (/\/volunteers\/members(\?|$)/.test(url) && method === 'GET') {
    const u = new URL(url); const q = (u.searchParams.get('q') || '').toLowerCase()
    const members = q ? MEMBERS.filter(m => m.full_name.toLowerCase().includes(q) || (m.email || '').toLowerCase().includes(q)) : MEMBERS
    return json({ members, more: false })
  }
  if (/\/volunteers\/profiles(\?|$)/.test(url) && method === 'POST') { calls.push({ method, url, body }); return json({ member_id: body?.member_id, role_ids: body?.role_ids || [] }) }
  if (/\/qualifications\/members\/qualification(\?|$)/.test(url) && method === 'POST') { calls.push({ method, url, body }); return json({ id: 'newq' }) }
  if (/\/roster\/members\/[^/]+\/availability/.test(url) && method === 'PUT') { calls.push({ method, url, body }); return json({ days: body?.days || [] }) }
  if (/\/roles-activities\/roles/.test(url)) return json({ roles: ROLES })
  if (/\/qualifications\/types/.test(url)) return json({ types: QUAL_TYPES })
  // Shift ops (unused here but keep them answering).
  if (/\/roster\/week\/[^/]+\/assign/.test(url) && method === 'POST') { calls.push({ method, url, body }); return json({ ok: true, assignee_member_id: body?.member_id, assignee_name: 'Someone', warns: [] }) }
  if (/\/roster\/shifts/.test(url)) { calls.push({ method, url, body }); return json({ id: 'ns', ok: true }) }
  if (/\/roster\/week/.test(url)) return json(WEEK)
  if (/\/roster\/areas(\?|$)/.test(url)) return json({ areas: [MATCH_DAY] })
  if (/\/roster\/hours/.test(url)) return json({ rows: [], totals: {} })
  if (/\/roster\/shortages/.test(url)) return json({ roles: [], no_role_required: 0 })
  if (/\/roster\/settings/.test(url)) return json({})
  if (/\/roster\/members\/[^/]+(\?|$)/.test(url)) return json({ member_id: 'm1', full_name: 'Amardeep Gill', available_days: [5, 6], qualifications: [], roles: [] })
  if (/\/clubhouse|\/notifications/.test(url)) return json({})
  if (/\/seasons/.test(url)) return json([{ id: 'se1', name: 'Summer 2025/26', year: 2025 }])
  if (/\/settings/.test(url)) return json({ diary_start_month: 7 })
  return json({})
})

const ADMIN = { id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } }
// A club_member whose allowlist has volunteers but NOT qualifications.
const MEMBER_USER = { id: 'vol', username: 'vol', display_name: 'Vol', role: 'club_member', club_slug: 'test-cc', capabilities: ['manage_volunteers'], entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_vol', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
    localStorage.setItem('roster_pool_open_boss', JSON.stringify(true))
  })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page, ADMIN)

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
  const toPeople = async () => { await page.getByRole('button', { name: 'People', exact: true }).first().click().catch(() => {}); await page.waitForTimeout(500) }

  await open('/admin/clubhouse/roster')
  await toPeople()

  // ── 1. Roles beneath the name, always, with "+ Add" ─────────────────────────
  const rolesText = await textOf('[data-testid="people-roles-m1"]')
  check('a volunteer\'s roles show beneath their name', /UMPIRE/.test(rolesText), rolesText)
  check('the roles line carries a "+ Add" role link', await seen('[data-testid="add-role-m1"]'))

  if (await seen('[data-testid="add-role-m1"]')) {
    await press('[data-testid="add-role-m1"]')
    check('"+ Add" opens the role picker', await seen('[data-testid="add-role-list"]'))
    // The picker offers a role m1 does NOT already hold (Groundskeeper), and
    // NOT one they do (Umpire).
    check('the picker offers a role they don\'t already hold', await seen('[data-testid="add-role-opt-r-gnd"]'))
    check('the picker hides a role they already hold', !(await seen('[data-testid="add-role-opt-r-ump"]')))
    calls.length = 0
    await press('[data-testid="add-role-opt-r-gnd"]')
    const c = lastCall(x => /\/volunteers\/profiles/.test(x.url) && x.method === 'POST')
    check('picking a role POSTs the merged role set to the profile',
      !!c && c.body?.member_id === 'm1' && (c.body?.role_ids || []).includes('r-ump') && (c.body?.role_ids || []).includes('r-gnd'),
      JSON.stringify(c?.body))
    // Optimistic: the new role chip appears without a reload.
    check('the new role chip appears on the rail', /GROUNDSKEEPER/.test(await textOf('[data-testid="people-roles-m1"]')))
  }

  // ── 2. Click a volunteer → inline availability; toggle a day → PUT ──────────
  // Availability is hidden until the row is clicked.
  check('availability is not shown until the volunteer is clicked', !(await seen('[data-testid="people-avail-m1"]')))
  // Click the rail cell itself — the parent of the roles row (the fragment is
  // transparent, so the roles div's parentElement IS the cell that carries the
  // onClick). The roles row stopPropagations its own clicks, so target the cell.
  await page.evaluate(() => {
    const roles = document.querySelector('[data-testid="people-roles-m1"]')
    const cell = roles && roles.parentElement
    if (cell) cell.click()
  })
  await page.waitForTimeout(350)
  check('clicking a volunteer expands their availability inline', await seen('[data-testid="people-avail-m1"]'))
  if (await seen('[data-testid="people-avail-m1"]')) {
    // m1 is available Sat(5)/Sun(6); toggle Monday(0) ON → PUT includes 0.
    calls.length = 0
    await press('[data-testid="people-avail-m1-0"]')
    const c = lastCall(x => /\/roster\/members\/m1\/availability/.test(x.url) && x.method === 'PUT')
    check('toggling a day PUTs the new availability',
      !!c && Array.isArray(c.body?.days) && c.body.days.includes(0) && c.body.days.includes(5) && c.body.days.includes(6),
      JSON.stringify(c?.body))
  }

  // ── 3. "+ Add volunteer" launcher → search members → add ────────────────────
  check('an "+ Add volunteer" launcher shows above the list', await seen('[data-testid="add-volunteer-open"]'))
  if (await press('[data-testid="add-volunteer-open"]')) {
    check('the launcher opens a member-search modal', await seen('[data-testid="add-vol-search"]'))
    check('the modal lists a club member to add (a non-volunteer)', await seen('[data-testid="add-vol-member-m9"]'))
    check('the modal also lists an existing volunteer', await seen('[data-testid="add-vol-member-m1"]'))
    // Search narrows.
    await page.fill('[data-testid="add-vol-search"]', 'nina')
    await page.waitForTimeout(400)
    check('searching narrows the member list', await seen('[data-testid="add-vol-member-m9"]') && !(await seen('[data-testid="add-vol-member-m1"]')))
    // Pick the new member.
    await press('[data-testid="add-vol-member-m9"]')
    check('picking a member shows the role picker', await seen('[data-testid="add-vol-role-r-ump"]'))
    check('picking a member shows the availability picker', await seen('[data-testid="add-vol-day-5"]'))
    // A club_admin holds MANAGE_QUALIFICATIONS → the quals section is offered.
    check('the qualifications section shows for a club admin', await seen('[data-testid="add-vol-qual-q-acc"]'))
    // Choose a role, two days, and a qualification, then save.
    await press('[data-testid="add-vol-role-r-sco"]')
    await press('[data-testid="add-vol-day-5"]')
    await press('[data-testid="add-vol-day-6"]')
    await press('[data-testid="add-vol-qual-q-acc"]')
    calls.length = 0
    await press('[data-testid="add-vol-save"]')
    await page.waitForTimeout(400)
    const prof = lastCall(x => /\/volunteers\/profiles/.test(x.url) && x.method === 'POST')
    check('saving POSTs a profile with the chosen role and availability',
      !!prof && prof.body?.member_id === 'm9' && (prof.body?.role_ids || []).includes('r-sco') && (prof.body?.available_days || []).includes(5) && (prof.body?.available_days || []).includes(6),
      JSON.stringify(prof?.body))
    const qual = lastCall(x => /\/qualifications\/members\/qualification/.test(x.url) && x.method === 'POST')
    check('saving records the ticked qualification',
      !!qual && qual.body?.member_id === 'm9' && qual.body?.qualification_type_id === 'q-acc',
      JSON.stringify(qual?.body))
  }

  check('no page errors across the run', errors.length === 0, errors.slice(0, 3).join(' | '))
  await page.close()

  // ── The capability gate: a club_member without MANAGE_QUALIFICATIONS ─────────
  const page2 = await ctx.newPage()
  const errors2 = []
  page2.on('pageerror', e => errors2.push(String(e)))
  await routes(page2, MEMBER_USER)
  const seen2 = (sel) => page2.locator(sel).count().then(n => n > 0).catch(() => false)
  await page2.goto(BASE + '/admin/clubhouse/roster', { waitUntil: 'domcontentloaded' })
  await page2.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
  await page2.waitForTimeout(900)
  await page2.getByRole('button', { name: 'People', exact: true }).first().click().catch(() => {})
  await page2.waitForTimeout(500)
  if (await seen2('[data-testid="add-volunteer-open"]')) {
    await page2.locator('[data-testid="add-volunteer-open"]').first().click().catch(() => {})
    await page2.waitForTimeout(300)
    await page2.locator('[data-testid="add-vol-member-m9"]').first().click().catch(() => {})
    await page2.waitForTimeout(300)
    check('a volunteer-only user still gets roles/availability', await seen2('[data-testid="add-vol-role-r-ump"]') && await seen2('[data-testid="add-vol-day-5"]'))
    check('the qualifications section is HIDDEN without MANAGE_QUALIFICATIONS', !(await seen2('[data-testid="add-vol-qual-q-acc"]')))
  } else {
    check('a volunteer-only user still gets roles/availability', false, 'launcher missing for club_member')
    check('the qualifications section is HIDDEN without MANAGE_QUALIFICATIONS', false, 'launcher missing for club_member')
  }
  check('no page errors on the club_member run', errors2.length === 0, errors2.slice(0, 3).join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}
run().catch(e => { console.error(e); process.exit(1) })
