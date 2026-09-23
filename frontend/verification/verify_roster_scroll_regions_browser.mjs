// The roster grid and the volunteer pool must scroll INDEPENDENTLY, against the
// real screen with the API stubbed at the network layer.
//
// The screen is bounded to the viewport (height: 100vh), so:
//   * the whole PAGE does not scroll — the grid and the pool each scroll within
//     their own region (the bug: with `minHeight: 100vh` the page scrolled as
//     one, so the day/date header and the pool moved with the shifts);
//   * the grid scroll region scrolls internally when its content is tall;
//   * scrolling the grid does NOT move the volunteer pool, and scrolling the
//     pool does NOT move the grid;
//   * the day/date header stays pinned to the top of the grid as it scrolls
//     (position: sticky engages only because the grid is the scroll container).
//
// The fixture is deliberately TALL (30 volunteers) so the content overflows the
// viewport — that is what makes the page-scroll regression observable. Control
// run (previous commit, minHeight: 100vh): the page scrolls as one, so the
// "page does not scroll" and "sticky header stays pinned" checks fail.
//
//   node verify_roster_scroll_regions_browser.mjs   (expects the dev server on :5199)
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
  roles: [{ role_id: 'r-ump', role_name: 'Umpire', required_qualification_type_id: null, required_qualification_name: null }],
  patterns: [],
}
const BAR = {
  id: 'ar2', name: 'Bar', department: 'Hospitality', color: '#f59e0b',
  required_role_id: 'r-bar', required_role_name: 'Bar Steward',
  roles: [{ role_id: 'r-bar', role_name: 'Bar Steward', required_qualification_type_id: null, required_qualification_name: null }],
  patterns: [],
}

// 30 volunteers, so both the grid (a row per person on the People view) and the
// pool (a card per person) overflow a short viewport.
const CANDS = Array.from({ length: 30 }, (_, i) => ({
  member_id: 'm' + i, name: `Volunteer ${String(i).padStart(2, '0')} Surname`,
  available_days: [5, 6], max_shifts: 5, role_ids: ['r-bar'], role_names: ['Bar Steward'], qual_type_ids: [],
}))

const WEEK = {
  week: {
    id: 'w1', week_start: '2026-08-17', status: 'draft', version: 1,
    shifts: [
      { id: 'sh1', area_id: 'ar1', area_name: 'Match Day', role_id: 'r-ump', role_name: 'Umpire',
        day_of_week: 5, start_time: 12, end_time: 18, headcount: 1, assignee_member_id: null,
        required_qualification_type_id: null, required_qualification_name: null },
      { id: 'sh2', area_id: 'ar2', area_name: 'Bar', role_id: 'r-bar', role_name: 'Bar Steward',
        day_of_week: 6, start_time: 17, end_time: 21, headcount: 1, assignee_member_id: null,
        required_qualification_type_id: null, required_qualification_name: null },
    ],
  },
  areas: [MATCH_DAY, BAR],
  candidates: CANDS,
  settings: {},
}

const routes = (page) => page.route('**/api/**', async (route) => {
  const url = route.request().url()
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

// Element metrics by test id (or null when the element is absent, so the control
// run reports rather than throwing).
const metrics = (page, tid) => page.evaluate((id) => {
  const el = document.querySelector(`[data-testid="${id}"]`)
  if (!el) return null
  const r = el.getBoundingClientRect()
  return { scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight, top: r.top }
}, tid)
const setScroll = (page, tid, v) => page.evaluate(({ id, v }) => {
  const el = document.querySelector(`[data-testid="${id}"]`)
  if (el) el.scrollTop = v
}, { id: tid, v })

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  // A short viewport so 30 rows overflow it.
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 760 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page)

  const open = async () => {
    await page.goto(BASE + '/admin/clubhouse/roster', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(1000)
  }

  // ── People view (default): the grid and pool are separate scroll regions ────
  await open()

  const pageScrolls = await page.evaluate(() => ({
    scrollHeight: document.documentElement.scrollHeight, innerHeight: window.innerHeight,
  }))
  // The whole page is bounded to the viewport — it does not grow past it, so the
  // day header and pool cannot scroll away with the shifts. FAILS on the old
  // minHeight:100vh layout, where 30 rows push the document taller than the view.
  check('the page itself does not scroll (bounded to the viewport)',
    pageScrolls.scrollHeight <= pageScrolls.innerHeight + 2,
    `scrollHeight=${pageScrolls.scrollHeight} innerHeight=${pageScrolls.innerHeight}`)

  const grid0 = await metrics(page, 'roster-grid-scroll')
  const pool0 = await metrics(page, 'roster-pool')
  check('the roster grid is its own scroll region', !!grid0 && grid0.scrollHeight > grid0.clientHeight + 2,
    JSON.stringify(grid0))
  check('the volunteer pool is its own scroll region', !!pool0 && pool0.scrollHeight > pool0.clientHeight + 2,
    JSON.stringify(pool0))

  // Scroll the grid: the pool must not move.
  await setScroll(page, 'roster-grid-scroll', 400)
  await page.waitForTimeout(150)
  const gridAfter = await metrics(page, 'roster-grid-scroll')
  const poolAfterGrid = await metrics(page, 'roster-pool')
  check('scrolling the grid actually scrolls the grid', !!gridAfter && gridAfter.scrollTop > 100,
    JSON.stringify(gridAfter))
  check('scrolling the grid does not move the volunteer pool',
    !!poolAfterGrid && poolAfterGrid.scrollTop === 0, JSON.stringify(poolAfterGrid))

  // The day/date header stays pinned to the top of the grid as it scrolls.
  const headerTop = await metrics(page, 'roster-day-header')
  check('the day/date header stays pinned to the top of the grid while it scrolls',
    !!headerTop && !!gridAfter && Math.abs(headerTop.top - gridAfter.top) <= 3,
    `header.top=${headerTop && headerTop.top} grid.top=${gridAfter && gridAfter.top}`)

  // Scroll the pool: the grid must not move (still at 400).
  await setScroll(page, 'roster-pool', 350)
  await page.waitForTimeout(150)
  const poolAfter = await metrics(page, 'roster-pool')
  const gridAfterPool = await metrics(page, 'roster-grid-scroll')
  check('scrolling the pool actually scrolls the pool', !!poolAfter && poolAfter.scrollTop > 100,
    JSON.stringify(poolAfter))
  check('scrolling the pool does not move the roster grid',
    !!gridAfterPool && Math.abs(gridAfterPool.scrollTop - 400) <= 2, JSON.stringify(gridAfterPool))

  // ── Same holds on the Areas view ────────────────────────────────────────────
  await page.getByRole('button', { name: 'Areas', exact: true }).first().click().catch(() => {})
  await page.waitForTimeout(400)
  const areasPage = await page.evaluate(() => ({
    scrollHeight: document.documentElement.scrollHeight, innerHeight: window.innerHeight,
  }))
  check('the Areas view is bounded to the viewport too',
    areasPage.scrollHeight <= areasPage.innerHeight + 2,
    `scrollHeight=${areasPage.scrollHeight} innerHeight=${areasPage.innerHeight}`)

  check('no page errors across the run', errors.length === 0, errors.join(' | '))

  // ── No horizontal overflow at 390px ─────────────────────────────────────────
  await page.setViewportSize({ width: 390, height: 780 })
  await open()
  const over = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check('Roster: no horizontal overflow at 390px', over <= 0, `${over}px`)

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch(e => { console.error(e); process.exit(1) })
