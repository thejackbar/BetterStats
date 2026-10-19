// Drives the real BetterSelect Availability screen in Chromium with the API
// stubbed at the network layer. The report (Oct 2026): the Squad filter listed
// every squad and grade name the club has ever had (switched-off squads,
// juniors with Show juniors off, squads nobody current is in), and there was no
// way to find players who have not played for a while.
//
// Now the Squad filter lists only squads worth picking, and a "Hasn't played"
// dropdown keeps players whose last game was more than N years ago.
//
//   APP_URL=http://localhost:4173 node verify_availability_list_filters_browser.mjs
//   (serve a production build; never rebuild dist under a running server)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}
const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const iso = (daysAgo) => plusDays(-daysAgo)
const W1 = plusDays(3)

const P = (id, name, squads, lastDaysAgo, current = true) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null, is_player: true,
  player_role: null, status: 'active', is_current: current, is_dormant: !current, is_inactive: false,
  squads, last_played: lastDaysAgo == null ? null : iso(lastDaysAgo), age: null,
})
const MATRIX = {
  dates: [{ date: W1, fixtures: [{ id: 'f0', opponent_name: 'Opp', home_away: 'HOME', role: 'single', two_day: false }] }],
  players: [
    P('ann', 'Ann', ['1st XI'], 20),                 // played last month
    P('ben', 'Ben', ['1st XI', 'Old XI'], 450),      // a year and a bit, still inside the 24 month window
    P('cal', 'Cal', ['Ghost XI'], 900, false),       // dormant: only on the All roster
    P('dee', 'Dee', ['U11 Red'], 10),                // junior squad
    P('eve', 'Eve', ['1st XI'], null),               // never played
  ],
  all_squads: ['1st XI', 'Ghost XI', 'Old XI', 'U11 Red'],
  squad_meta: {
    '1st XI': { active: true, junior: false }, 'Ghost XI': { active: true, junior: false },
    'Old XI': { active: false, junior: false }, 'U11 Red': { active: true, junior: true },
  },
  dormancy_months: 24, rules: { active: false, applied: [] }, availability: {},
}
const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1',
  club_slug: 'verify-cc', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
async function stub(page, matrix = MATRIX) {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json(ME)
    if (url.includes('/availability/matrix')) return json(matrix)
    if (url.includes('/selection/selected-players')) return json({ player_ids: [] })
    return json({})
  })
}
const rows = (page) => page.evaluate(() =>
  [...document.querySelectorAll('tbody tr')].map((r) => r.querySelector('td .truncate')?.textContent.trim()).filter(Boolean))
const squadOpts = async (page) => {
  // Open the Filters panel (once) and read the Squad group's checkbox labels.
  if (!(await page.locator('text=Squad').filter({ hasText: /^Squad$/ }).count())) await page.locator('button', { hasText: 'Filters' }).click()
  return page.evaluate(() => {
    const g = [...document.querySelectorAll('div')].find((d) => d.children.length === 2 && d.children[0].textContent.trim().toLowerCase() === 'squad'
      && d.children[1].querySelector('input[type=checkbox]'))
    return g ? [...g.children[1].querySelectorAll('label')].map((l) => l.textContent.trim()) : null
  })
}
const lapsedSelect = (page) => page.locator('select', { has: page.locator('option', { hasText: "Hasn't played" }) })
const lapsedOpts = async (page) => (await lapsedSelect(page).count()) ? lapsedSelect(page).locator('option').allTextContents() : null
const setLapsedByLabel = async (page, label) => { await lapsedSelect(page).selectOption({ label }); await page.waitForTimeout(150) }
const setRoster = async (page, label) => { await page.locator('button', { hasText: new RegExp('^' + label + '$') }).click(); await page.waitForTimeout(150) }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const open = async (opts = {}) => {
    const ctx = await browser.newContext({ viewport: opts.viewport || { width: 1440, height: 1000 }, ...(opts.ctx || {}) })
    if (opts.juniors) await ctx.addInitScript(() => localStorage.setItem('bs_pref:select.juniors', 'true'))
    const page = await ctx.newPage()
    page.errors = []
    page.on('pageerror', (e) => page.errors.push(String(e)))
    await stub(page)
    await page.goto(`${BASE}/admin/betterselect/availability`)
    await page.waitForSelector('tbody tr', { timeout: 20000 })
    await page.waitForTimeout(300)
    return page
  }

  // ---- Squad filter ------------------------------------------------------
  let page = await open()
  let o = await squadOpts(page)
  check('Squad list is on screen to read', Array.isArray(o), String(o))
  check('Current squad, juniors off: only 1st XI is listed', (o || []).join() === '1st XI', (o || []).join())
  check('switched-off squad (Old XI) is not offered', !(o || []).includes('Old XI'))
  check('junior squad (U11 Red) is not offered with Show juniors off', !(o || []).includes('U11 Red'))
  check('squad with nobody current (Ghost XI) is not offered on Current squad', !(o || []).includes('Ghost XI'))
  await setRoster(page, 'All')
  o = await squadOpts(page)
  check('All roster: Ghost XI is offered (a dormant player is in it)', (o || []).join() === '1st XI,Ghost XI', (o || []).join())
  check('All roster: Old XI (switched off) and U11 Red (junior) still not offered', !(o || []).includes('Old XI') && !(o || []).includes('U11 Red'))
  await page.context().close()

  page = await open({ juniors: true })
  o = await squadOpts(page)
  check('Show juniors on: U11 Red is offered', (o || []).join() === '1st XI,U11 Red', (o || []).join())
  check('Show juniors on: a switched-off squad is still not offered', !(o || []).includes('Old XI'))
  await page.context().close()

  // A matrix from an older server (no squad_meta) lists every name, as before.
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  page = await ctx.newPage()
  await stub(page, { ...MATRIX, squad_meta: undefined })
  await page.goto(`${BASE}/admin/betterselect/availability`)
  await page.waitForSelector('tbody tr', { timeout: 20000 })
  await setRoster(page, 'All')
  o = await squadOpts(page)
  check('no squad_meta: every squad name stays listed (nothing guessed away)', (o || []).length === 4, (o || []).join())
  await ctx.close()

  // ---- Hasn't played -----------------------------------------------------
  page = await open()
  let r = await rows(page)
  check('Current squad default: Ann, Ben, Dee, Eve listed (Cal is dormant)', r.join() === 'Ann,Ben,Dee,Eve', r.join())
  o = await lapsedOpts(page)
  check('Hasn\'t played control is drawn', Array.isArray(o), String(o))
  check('Current squad (24 month window): offers only "> 1 yr" besides any time', (o || []).length === 2 && /> 1 yr/.test(o[1]), (o || []).join(' | '))
  await setLapsedByLabel(page, 'Last played > 1 yr ago')
  r = await rows(page)
  check('> 1 yr: only Ben (450 days ago); never-played Eve is not "lapsed"', r.join() === 'Ben', r.join())
  check('the count reads "1 of 5"', await page.locator('text=/^1 of 5$/').count() === 1)
  await setRoster(page, 'All')
  o = await lapsedOpts(page)
  check('All roster: wider choices appear (2, 3, 5, 10 yrs)', (o || []).length === 6, (o || []).join(' | '))
  await setLapsedByLabel(page, 'Last played > 2 yrs ago')
  r = await rows(page)
  check('All roster, > 2 yrs: only Cal (900 days ago)', r.join() === 'Cal', r.join())
  await setLapsedByLabel(page, "Hasn't played: any time")
  r = await rows(page)
  check('Any time: everyone is back on All', r.length === 5, r.join())
  // The choice is remembered, and a stored value that is no longer offered is ignored.
  await setLapsedByLabel(page, 'Last played > 2 yrs ago')
  await page.reload(); await page.waitForSelector('tbody tr', { timeout: 20000 })
  r = await rows(page)
  check('remembered on this device across a reload (All + > 2 yrs → Cal)', r.join() === 'Cal', r.join())
  await setRoster(page, 'Current squad')
  r = await rows(page)
  check('back on Current squad a stored "> 2 yrs" is not offered, so it filters nothing', r.join() === 'Ann,Ben,Dee,Eve', r.join())
  check('the page threw nothing', page.errors.length === 0, page.errors.join(' | '))
  await page.context().close()

  // ---- 390px -------------------------------------------------------------
  page = await open({ viewport: { width: 390, height: 844 }, ctx: { hasTouch: true, isMobile: true } })
  const over = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: screen.width }))
  check('390px: page does not overflow sideways', over.sw <= over.cw, JSON.stringify(over))
  if (process.env.SHOT_DIR) await page.screenshot({ path: process.env.SHOT_DIR + '/avail_list_filters_390.png' })
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
