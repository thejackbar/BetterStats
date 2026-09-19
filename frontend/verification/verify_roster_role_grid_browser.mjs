// Expand and collapse an operational area's ROLES on the roster grid, against
// the REAL screen with the API stubbed at the network layer.
//
// A shift is created and filled for a ROLE now (Umpire, Scorer…), not for the
// operational area as a whole — so on the Areas view a multi-role area draws a
// header that expands into a sub-row per role, each carrying only that role's
// shifts, and collapses to hide them.
//
// What is asserted:
//   * a multi-role area (Match Day: Umpire + Scorer) draws a header with a
//     collapse toggle, and BY DEFAULT both role sub-rows are shown;
//   * each role's shifts land in its OWN sub-row — the open Umpire shift under
//     Umpire, the assigned Scorer shift under Scorer;
//   * a single-role area (Bar) stays a plain row with no toggle and no header;
//   * an ASSIGNED shift whose area has since been ARCHIVED (its area is not in
//     the active list_areas set) still renders in the Areas view with its
//     volunteer named — it must not silently vanish the way it used to;
//   * the toggle collapses the roles away (both sub-rows gone, header stays) and
//     expands them back;
//   * the collapsed state survives a reload (it is a per-person preference);
//   * no page errors, and no horizontal overflow at 390px.
//
// Control run (previous commit, no per-role rows): every new check reads its
// element through the absence-reporting helpers, so it fails rather than dying.
//
//   node verify_roster_role_grid_browser.mjs   (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

// Match Day: a two-role palette (Umpire gated by accreditation, Scorer by
// nothing). Bar: a single role, so it must stay a plain row.
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
  id: 'ar2', name: 'Bar', department: 'Hospitality', color: '#f59e0b',
  required_role_id: 'r-bar', required_role_name: 'Bar Steward',
  roles: [{ role_id: 'r-bar', role_name: 'Bar Steward', required_qualification_type_id: null, required_qualification_name: null }],
  patterns: [],
}

// The week: Match Day has an OPEN Umpire shift and an ASSIGNED Scorer shift, so
// each role's sub-row draws its own chip. Bar has one shift.
const WEEK = {
  week: {
    id: 'w1', week_start: '2026-08-17', status: 'draft', version: 1,
    shifts: [
      { id: 'sh1', area_id: 'ar1', area_name: 'Match Day', role_id: 'r-ump', role_name: 'Umpire',
        day_of_week: 5, start_time: 12, end_time: 18, headcount: 1, assignee_member_id: null,
        required_qualification_type_id: 'q-acc', required_qualification_name: 'Umpire Accreditation' },
      { id: 'sh2', area_id: 'ar1', area_name: 'Match Day', role_id: 'r-sco', role_name: 'Scorer',
        day_of_week: 5, start_time: 12, end_time: 18, headcount: 1,
        assignee_member_id: 'm2', assignee_name: 'Sam Scorer',
        required_qualification_type_id: null, required_qualification_name: null },
      { id: 'sh3', area_id: 'ar2', area_name: 'Bar', role_id: 'r-bar', role_name: 'Bar Steward',
        day_of_week: 6, start_time: 17, end_time: 21, headcount: 1, assignee_member_id: null,
        required_qualification_type_id: null, required_qualification_name: null },
      // A shift on an area (ar3) that is NOT in `areas` — the area was archived
      // after this week generated. It carries its own name and an assigned
      // volunteer, and must still show on the Areas view.
      { id: 'sh4', area_id: 'ar3', area_name: 'Old Gate', role_id: 'r-gate', role_name: 'Gatekeeper',
        day_of_week: 5, start_time: 9, end_time: 12, headcount: 1,
        assignee_member_id: 'm1', assignee_name: 'Amardeep Gill',
        required_qualification_type_id: null, required_qualification_name: null },
    ],
  },
  areas: [MATCH_DAY, BAR],
  candidates: [
    { member_id: 'm1', name: 'Amardeep Gill', available_days: [5, 6], max_shifts: 5,
      role_ids: ['r-ump'], role_names: ['Umpire'], qual_type_ids: ['q-acc'] },
    { member_id: 'm2', name: 'Sam Scorer', available_days: [5, 6], max_shifts: 5,
      role_ids: ['r-sco'], role_names: ['Scorer'], qual_type_ids: [] },
  ],
  settings: {},
}

const routes = (page) => page.route('**/api/**', async (route) => {
  const url = route.request().url()
  const method = route.request().method()
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) {
    return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } })
  }
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

const noOverflow = (page) => page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth)

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
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page)

  // Absence-reporting helpers, so the control run (no such element) fails each
  // new check cleanly rather than throwing on a missing locator.
  const seen = (sel) => page.locator(sel).count().then(n => n > 0).catch(() => false)
  const press = async (sel) => { if (await seen(sel)) { await page.locator(sel).first().click().catch(() => {}); return true } return false }
  // The text inside an addressed sub-row / header (or '' when it is absent).
  const textOf = async (sel) => { if (!(await seen(sel))) return ''; return page.locator(sel).first().innerText().catch(() => '') }
  const attrOf = async (sel, name) => { if (!(await seen(sel))) return ''; return (await page.locator(sel).first().getAttribute(name).catch(() => '')) || '' }

  const open = async (path) => {
    await page.goto(BASE + path, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(1000)
  }
  const toAreas = async () => {
    await page.getByRole('button', { name: 'Areas', exact: true }).first().click().catch(() => {})
    await page.waitForTimeout(500)
  }

  // ── The Areas view, roles expanded by default ───────────────────────────────
  await open('/admin/clubhouse/roster')
  await toAreas()

  check('the multi-role area draws a header with a collapse toggle',
    await seen('[data-testid="area-toggle-ar1"]'))

  const umpRow0 = await textOf('[data-testid="area-role-row-ar1-r-ump"]')
  const scoRow0 = await textOf('[data-testid="area-role-row-ar1-r-sco"]')
  check('both role sub-rows are shown by default',
    !!umpRow0 && !!scoRow0, `ump=${JSON.stringify(umpRow0.slice(0, 40))} sco=${JSON.stringify(scoRow0.slice(0, 40))}`)
  check('the Umpire sub-row names the Umpire role', umpRow0.includes('Umpire'), JSON.stringify(umpRow0))
  check('the Scorer sub-row names the Scorer role', scoRow0.includes('Scorer'), JSON.stringify(scoRow0))

  // Each role's own shift lands in its own sub-row: the OPEN Umpire shift under
  // Umpire, the ASSIGNED Scorer shift under Scorer — not mixed into one row.
  check('the open Umpire shift is in the Umpire sub-row',
    umpRow0.includes('OPEN') && !umpRow0.includes('Sam Scorer'), JSON.stringify(umpRow0))
  check('the assigned Scorer shift is in the Scorer sub-row',
    scoRow0.includes('Sam Scorer') && !scoRow0.includes('OPEN'), JSON.stringify(scoRow0))

  // The single-role Bar is a plain row: no header, no toggle to fold.
  check('the single-role Bar area has no collapse toggle',
    !(await seen('[data-testid="area-toggle-ar2"]')))
  check('the single-role Bar area is not a role-expanding header',
    !(await seen('[data-testid="area-header-ar2"]')))

  // ── An assigned shift on an ARCHIVED area still shows in the Areas view ──────
  // ar3 is not in `areas`, so before the fix its shift (assigned volunteer and
  // all) never rendered here even though the People view showed it. It now
  // draws its own row, named off the shift's own area_name.
  const gateRow = await textOf('[data-testid="area-row-ar3"]')
  check('the archived area shift renders in the Areas view',
    !!gateRow, JSON.stringify(gateRow.slice(0, 60)))
  check('the archived area row is named off the shift own area name',
    gateRow.includes('Old Gate'), JSON.stringify(gateRow))
  check('the volunteer assigned to the archived-area shift is shown',
    gateRow.includes('Amardeep Gill'), JSON.stringify(gateRow))

  // Because a shift on a non-active area exists, the week predates the club's
  // latest areas & roles — a staleness banner says so and offers a reset.
  const banner = await textOf('[data-testid="roster-stale-banner"]')
  check('the stale-week banner is shown when a shift is on an archived area',
    !!banner, JSON.stringify(banner.slice(0, 80)))
  check('the banner offers to reset the week',
    banner.toLowerCase().includes('reset'), JSON.stringify(banner))

  // ── Collapse folds the roles away, the header stays ─────────────────────────
  // Each of these is a CONTRAST against the expanded state read above, so a
  // build that never draws a sub-row can't pass them vacuously: the toggle had
  // to have folded a genuinely-present row away.
  const wasExpanded = !!umpRow0 && !!scoRow0
  await press('[data-testid="area-toggle-ar1"]')
  await page.waitForTimeout(400)
  check('the header remains after collapsing', await seen('[data-testid="area-header-ar1"]'))
  check('collapsing folds away the Umpire sub-row that was shown',
    wasExpanded && !(await seen('[data-testid="area-role-row-ar1-r-ump"]')))
  check('collapsing folds away the Scorer sub-row that was shown',
    wasExpanded && !(await seen('[data-testid="area-role-row-ar1-r-sco"]')))

  // ── Collapsed, the header's day cells still show the shifts as dots ──────────
  // Match Day's Saturday (day 5) has an OPEN Umpire shift and a FILLED Scorer
  // shift, so its collapsed header cell must carry two dots — one filled, one
  // open — while a day with nothing shows none. This is what keeps it obvious
  // there are shifts on that day without expanding.
  const satCell = '[data-testid="area-collapsed-day-ar1-5"]'
  check('collapsing shows a per-day shift summary on the header',
    wasExpanded && (await attrOf(satCell, 'data-shift-count')) === '2')
  check('the collapsed summary marks the filled shift with a solid dot',
    await seen(satCell + ' [data-filled="1"]'))
  check('the collapsed summary marks the still-open shift with a ring',
    await seen(satCell + ' [data-open="1"]'))
  check('a day with no shifts draws an empty collapsed cell',
    (await attrOf('[data-testid="area-collapsed-day-ar1-0"]', 'data-shift-count')) === '0')

  // ── Expand brings them back ─────────────────────────────────────────────────
  await press('[data-testid="area-toggle-ar1"]')
  await page.waitForTimeout(400)
  check('expanding shows the Umpire sub-row again', await seen('[data-testid="area-role-row-ar1-r-ump"]'))
  check('expanding shows the Scorer sub-row again', await seen('[data-testid="area-role-row-ar1-r-sco"]'))

  // ── Collapse survives a reload (a per-person preference) ─────────────────────
  await press('[data-testid="area-toggle-ar1"]')
  await page.waitForTimeout(400)
  const collapsedBeforeReload = wasExpanded && !(await seen('[data-testid="area-role-row-ar1-r-ump"]'))
  await open('/admin/clubhouse/roster')
  await toAreas()
  check('the collapsed state survives a reload',
    collapsedBeforeReload && !(await seen('[data-testid="area-role-row-ar1-r-ump"]')))
  // Re-expand so the run leaves the preference clean.
  await press('[data-testid="area-toggle-ar1"]')

  // ── No page errors ──────────────────────────────────────────────────────────
  check('no page errors across the run', errors.length === 0, errors.join(' | '))

  // ── No overflow at 390px, with the roles expanded ───────────────────────────
  await page.setViewportSize({ width: 390, height: 900 })
  await open('/admin/clubhouse/roster')
  await toAreas()
  const over = await noOverflow(page)
  check('Roster Areas view: no overflow at 390px', over <= 0, `${over}px`)

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch(e => { console.error(e); process.exit(1) })
