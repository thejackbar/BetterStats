// Drives the real BetterSelect Availability matrix in Chromium with the API
// stubbed at the network layer. The report (Oct 2026): filtering for "Available"
// showed players who are free in three weeks but out for the upcoming game,
// because the filter matched ANY shown week.
//
// The filter now judges the selected column (the next game by default). Header
// click moves it, week chips pick several, "Every week" / "Any week" combines.
//
//   APP_URL=http://localhost:4173 node verify_availability_column_filter_browser.mjs
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
const W1 = plusDays(3), W2 = plusDays(10), W3 = plusDays(17)
const dayWord = (d) => new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

const P = (id, name) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null, is_player: true,
  player_role: null, status: 'active', is_current: true, is_dormant: false, is_inactive: false,
  squads: [], last_played: iso(20), age: null,
})
const st = (status) => ({ status, source: 'admin' })
const MATRIX = {
  dates: [W1, W2, W3].map((date, i) => ({ date, fixtures: [{ id: 'f' + i, opponent_name: 'Opp ' + i, home_away: 'HOME', role: 'single', two_day: false }] })),
  players: [P('ann', 'Ann'), P('ben', 'Ben'), P('cal', 'Cal'), P('dee', 'Dee')],
  all_squads: [], dormancy_months: 24, rules: { active: false, applied: [] },
  availability: {
    ann: { [W1]: st('UNAVAILABLE'), [W2]: st('UNAVAILABLE'), [W3]: st('AVAILABLE') },   // the reported case
    ben: { [W1]: st('AVAILABLE'), [W2]: st('MAYBE'), [W3]: st('UNAVAILABLE') },
    cal: { [W1]: st('AVAILABLE'), [W2]: st('AVAILABLE'), [W3]: st('AVAILABLE') },
    dee: {},
  },
}
const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1',
  club_slug: 'verify-cc', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
async function stub(page) {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json(ME)
    if (url.includes('/availability/matrix')) return json(MATRIX)
    if (url.includes('/selection/selected-players')) return json({ player_ids: [] })
    return json({})
  })
}
const rows = (page) => page.evaluate(() =>
  [...document.querySelectorAll('tbody tr')].map((r) => r.querySelector('td .truncate')?.textContent.trim()).filter(Boolean))
const chip = (page, d) => page.locator('button', { hasText: dayWord(d) }).filter({ hasNot: page.locator('th') })

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await stub(page)
  await page.goto(`${BASE}/admin/betterselect/availability?avail=AVAILABLE`)
  await page.waitForSelector('tbody tr', { timeout: 20000 })
  await page.waitForTimeout(300)

  // Default: judged on the next game only. Ann is out for it (in only 3 weeks on).
  let r = await rows(page)
  check('default: Available shows people free for the NEXT game (Ben, Cal)', r.join() === 'Ben,Cal', r.join())
  check('default: Ann (free in 3 weeks, out for the next game) is not shown', !r.includes('Ann'))
  const scope = page.locator('text=Availability for')
  check('a scope row names the weeks being judged', await scope.count() === 1)

  // Clicking the third column header moves the filter there.
  await page.locator('th', { hasText: dayWord(W3) }).click()
  await page.waitForTimeout(200)
  r = await rows(page)
  check('click the third column: Available now judges that week (Ann, Cal)', r.join() === 'Ann,Cal', r.join())

  // Pick several weeks from the chips: Every week (default) vs Any week.
  await page.locator('.pb-card button', { hasText: dayWord(W1) }).filter({ hasText: /^\s*\S/ }).first().click()
  await page.waitForTimeout(200)
  r = await rows(page)
  check('weeks 1 and 3 with "Every week": only Cal is free for both', r.join() === 'Cal', r.join())
  await page.getByRole('button', { name: 'Any week' }).click()
  await page.waitForTimeout(200)
  r = await rows(page)
  check('"Any week": Ann, Ben and Cal (each free in at least one)', r.join() === 'Ann,Ben,Cal', r.join())

  // Back to following the selected week.
  await page.getByRole('button', { name: 'Use selected week' }).click()
  await page.waitForTimeout(200)
  r = await rows(page)
  check('"Use selected week" goes back to the one column (week 3: Ann, Cal)', r.join() === 'Ann,Cal', r.join())

  // No response is judged on the column too: Dee has no answer anywhere.
  await page.goto(`${BASE}/admin/betterselect/availability?avail=NO_RESPONSE`)
  await page.waitForSelector('tbody tr', { timeout: 20000 })
  r = await rows(page)
  check('No response: only Dee, on the selected column', r.join() === 'Dee', r.join())

  // No availability filter: scope row absent, everyone listed.
  await page.goto(`${BASE}/admin/betterselect/availability`)
  await page.waitForSelector('tbody tr', { timeout: 20000 })
  r = await rows(page)
  check('no filter: all four players, no scope row', r.length === 4 && await page.locator('text=Availability for').count() === 0, r.join())

  // 390px: no horizontal overflow with the scope row open.
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  const m = await phone.newPage()
  await stub(m)
  await m.goto(`${BASE}/admin/betterselect/availability?avail=AVAILABLE`)
  await m.waitForSelector('tbody tr', { timeout: 20000 })
  await m.waitForTimeout(300)
  const over = await m.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: screen.width }))
  check('390px: page does not overflow sideways', over.sw <= over.cw, JSON.stringify(over))
  if (process.env.SHOT_DIR) { await m.screenshot({ path: process.env.SHOT_DIR + '/avail_390.png' }); await page.screenshot({ path: process.env.SHOT_DIR + '/avail_desktop.png' }) }

  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
