// BetterSelect Availability: "Include inactive players" / "Include dormant players"
// in the Filters panel. Current squad hides both; the only way back was switching
// the whole roster to All (which brings both at once). Drives the real screen in
// Chromium with the API stubbed at the network layer.
//
//   APP_URL=http://localhost:4173 node verify_availability_roster_toggles_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}
const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const W1 = plusDays(3)
const P = (id, name, o = {}) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null, is_player: true,
  player_role: null, status: 'active', is_current: true, is_dormant: false, is_inactive: false,
  squads: [], last_played: plusDays(-20), age: null, ...o,
})
const players = [
  P('a1', 'Ann Active'), P('a2', 'Bob Active'),
  P('i1', 'Ian Inactive', { status: 'inactive', is_inactive: true, is_current: false }),
  P('d1', 'Dee Dormant', { is_dormant: true, is_current: false }),
]
const MATRIX = {
  dates: [{ date: W1, fixtures: [{ id: 'f0', opponent_name: 'Opp', home_away: 'HOME', role: 'single', two_day: false }] }],
  players, all_squads: [], dormancy_months: 24, rules: { active: false, applied: [] },
  availability: {},
}
const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1',
  club_slug: 'verify-cc', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
const names = (page) => page.$$eval('[data-avail-matrix] tbody tr td:first-child span.truncate', (els) => els.map((e) => e.textContent.trim()))

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json(ME)
    if (url.includes('/availability/matrix')) return json(MATRIX)
    if (url.includes('/selection/selected-players')) return json({ player_ids: [] })
    return json({})
  })
  await page.goto(`${BASE}/admin/betterselect/availability`)
  await page.waitForSelector('[data-avail-matrix] tbody tr', { timeout: 20000 })
  await page.waitForTimeout(400)

  let n = await names(page)
  check('Current squad: only active players listed', n.length === 2 && !n.some((x) => /Inactive|Dormant/.test(x)), n.join(','))

  await page.getByRole('button', { name: /Filters/ }).click()
  const inactiveBox = page.getByText('Include inactive players')
  const dormantBox = page.getByText('Include dormant players')
  check('Filters panel offers Include inactive players', await inactiveBox.count() > 0)
  check('Filters panel offers Include dormant players', await dormantBox.count() > 0)

  await inactiveBox.first().click()
  await page.waitForTimeout(250)
  n = await names(page)
  check('Include inactive adds inactive players only', n.length === 3 && n.some((x) => x.includes('Ian')) && !n.some((x) => x.includes('Dee')), n.join(','))

  await dormantBox.first().click()
  await page.waitForTimeout(250)
  n = await names(page)
  check('Include dormant adds dormant too', n.length === 4, n.join(','))

  // The chip is the way back out.
  await page.keyboard.press('Escape')
  const chip = page.getByText('Include inactive players').first()
  check('an active chip names the toggle', await chip.count() > 0)
  await page.getByRole('button', { name: /Include inactive players/ }).first().click().catch(() => {})
  await page.waitForTimeout(250)
  n = await names(page)
  check('removing the inactive chip hides them again', !n.some((x) => x.includes('Ian')) && n.some((x) => x.includes('Dee')), n.join(','))
  check('no page errors', errors.length === 0, errors.join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
