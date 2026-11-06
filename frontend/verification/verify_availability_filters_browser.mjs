// BetterSelect Availability filters, driven in Chromium with the API stubbed:
//  - Show: Active / Dormant / Inactive toggles (Active only to begin with). An
//    inactive player can be taken out as well as put in.
//  - Last game played, by season (this season, 1 season ago, ...), not "Hasn't played".
//  - Squad list in the Filters panel: natural order (1st before 10th), shown as
//    chips with the club name stripped. Competition and Leave out are not two
//    identical lists: Leave out has no list in the panel.
//  - A player's name is never cut off in the grid.
//
//   APP_URL=http://localhost:4173 node verify_availability_filters_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}
const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const iso = (d) => d.toISOString().slice(0, 10)
// Season = 1 Sep to 31 Aug. Build a "last game" date inside season N seasons ago.
const now = new Date()
const curSeason = now.getMonth() + 1 >= 9 ? now.getFullYear() : now.getFullYear() - 1
const inSeason = (ago) => `${curSeason - ago}-12-10`
const W1 = plusDays(3)
const LONG = 'Maximilian Wolfeschlegelsteinhausen-Bergerdorff'
const P = (id, name, o = {}) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null, is_player: true,
  player_role: null, status: 'active', is_current: true, is_dormant: false, is_inactive: false,
  squads: [], last_played: inSeason(0), age: null, ...o,
})
const players = [
  P('a1', 'Ann Active', { squads: ['Applecross 1st XI'] }),
  P('a2', LONG, { last_played: inSeason(1), squads: ['Applecross 10th XI'] }),
  P('a3', 'Cal Old', { last_played: inSeason(2) }),
  P('a4', 'Nev Never', { last_played: null }),
  P('a5', 'Far Gone', { last_played: inSeason(6) }),
  P('i1', 'Ian Inactive', { status: 'inactive', is_inactive: true, is_current: false }),
  P('d1', 'Dee Dormant', { is_dormant: true, is_current: false, last_played: inSeason(3) }),
]
const SQUADS = ['Applecross', 'Applecross 1st XI', 'Applecross 2nd XI', 'Applecross 10th XI', 'Applecross A']
players[0].squads = ['Applecross 1st XI']; players[1].squads = ['Applecross 10th XI']; players[2].squads = ['Applecross 2nd XI']; players[3].squads = ['Applecross A']; players[4].squads = ['Applecross']
const MATRIX = {
  dates: [{ date: W1, fixtures: [{ id: 'f0', opponent_name: 'Opp', home_away: 'HOME', role: 'single', two_day: false }] }],
  players, all_squads: SQUADS, dormancy_months: 24, rules: { active: false, applied: [] },
  competitions: [{ id: 'c1', name: 'West Australian Suburban Turf Cricket Assoc.' }, { id: 'c2', name: "Perth Scorchers Women's League" }],
  availability: {},
}
const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1',
  club_slug: 'verify-cc', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
const names = (page) => page.$$eval('[data-avail-matrix] tbody tr td:first-child span.text-sm', (els) => els.map((e) => e.textContent.trim()))

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
  await page.waitForTimeout(500)
  const showBtn = (label) => page.locator('[data-avail-show] button').filter({ hasText: new RegExp('^' + label + '$') })

  // ── Show ───────────────────────────────────────────────────────────────────
  let n = await names(page)
  check('opens on Active only', n.length === 5 && !n.some((x) => /Inactive|Dormant/.test(x)), n.join(','))
  await showBtn('Inactive').click(); await page.waitForTimeout(200)
  n = await names(page)
  check('Inactive adds inactive players only', n.length === 6 && n.some((x) => x.includes('Ian')) && !n.some((x) => x.includes('Dee')), n.join(','))
  await showBtn('Dormant').click(); await page.waitForTimeout(200)
  n = await names(page)
  check('Dormant adds dormant too', n.length === 7, n.join(','))
  await showBtn('Inactive').click(); await page.waitForTimeout(200)
  n = await names(page)
  check('Inactive can be taken out again', !n.some((x) => x.includes('Ian')) && n.some((x) => x.includes('Dee')), n.join(','))
  await showBtn('Dormant').click(); await page.waitForTimeout(200)
  await showBtn('Active').click(); await page.waitForTimeout(200)
  n = await names(page)
  check('the last one on cannot be switched off', n.length === 5, n.join(','))

  // ── Last game played ───────────────────────────────────────────────────────
  const sel = page.locator('select').filter({ hasText: 'Last game' }).first()
  const opts = await sel.locator('option').allTextContents()
  check('select is "Last game played" by season, not "Hasn\'t played"', opts.includes('Last game: this season') && opts.includes('Last game: 1 season ago') && opts.includes('Last game: 2 seasons ago') && !opts.some((o) => /Hasn't played/.test(o)), opts.join(' | '))
  const pick = async (label) => { await sel.selectOption({ label }); await page.waitForTimeout(200); return names(page) }
  n = await pick('Last game: this season')
  check('this season: only this season\'s players', n.length === 1 && n[0].includes('Ann'), n.join(','))
  n = await pick('Last game: 1 season ago')
  check('1 season ago: only last season\'s', n.length === 1 && n[0].includes('Maximilian'), n.join(','))
  n = await pick('Last game: 2 seasons ago')
  check('2 seasons ago', n.length === 1 && n[0].includes('Cal'), n.join(','))
  n = await pick('Last game: 4 or more seasons ago')
  check('4 or more seasons ago', n.length === 1 && n[0].includes('Far'), n.join(','))
  n = await pick('Last game: never played')
  check('never played', n.length === 1 && n[0].includes('Nev'), n.join(','))
  n = await pick('Last game: any time')
  check('any time lists everyone again', n.length === 5)

  // ── Filters panel ──────────────────────────────────────────────────────────
  await page.getByRole('button', { name: /Filters/ }).click()
  await page.waitForTimeout(200)
  const panel = page.locator('div.rounded-lg.border.bg-pb-surface2\\/40').first()
  const heads = await panel.locator('div.font-mono').allTextContents()
  check('Competition is in the panel', heads.some((h) => /^competition$/i.test(h.trim())), heads.join(','))
  check('Leave out is NOT a second copy of the same list', !heads.some((h) => /^leave out$/i.test(h.trim())), heads.join(','))
  const squadChips = await panel.locator('xpath=.//div[contains(@class,"font-mono") and translate(normalize-space(.),"SQUAD","squad")="squad"]/following-sibling::div//button').allTextContents()
  check('squads are chips with the club name stripped, 1st before 2nd before 10th', JSON.stringify(squadChips.slice(0, 5)) === JSON.stringify(['Applecross', '1st XI', '2nd XI', '10th XI', 'A']), JSON.stringify(squadChips))
  check('squad list is not a column of checkboxes', (await panel.locator('xpath=.//div[contains(@class,"font-mono") and translate(normalize-space(.),"SQUAD","squad")="squad"]/following-sibling::div//input[@type="checkbox"]').count()) === 0)
  await page.getByRole('button', { name: '10th XI' }).click()
  await page.waitForTimeout(250)
  n = await names(page)
  check('picking a squad chip filters to it', n.length === 1 && n[0].includes('Maximilian'), n.join(','))
  await page.keyboard.press('Escape')

  // ── Names are never cut ────────────────────────────────────────────────────
  await page.getByRole('button', { name: 'Clear all' }).click().catch(() => {})
  await page.waitForTimeout(250)
  const cut = await page.$$eval('[data-avail-matrix] tbody tr td:first-child', (tds) => tds.map((td) => {
    const span = td.querySelector('span.text-sm'); const r = span.getBoundingClientRect(); const c = td.getBoundingClientRect()
    return { name: span.textContent.trim(), clipped: span.scrollWidth > span.clientWidth + 1 || r.right > c.right + 1 }
  }))
  check('no player name is clipped (even a very long one)', cut.length > 0 && cut.every((x) => !x.clipped), JSON.stringify(cut.filter((x) => x.clipped)))
  const lineup = await page.evaluate(() => {
    const th = document.querySelector('[data-avail-head] th:nth-child(2)'), td = document.querySelector('[data-avail-matrix] tbody tr td:nth-child(2)')
    const a = th.getBoundingClientRect(), b = td.getBoundingClientRect()
    return { dl: Math.abs(a.left - b.left), dw: Math.abs(a.width - b.width) }
  })
  check('date columns still line up with the strip', lineup.dl <= 1 && lineup.dw <= 1, JSON.stringify(lineup))
  check('no page errors', errors.length === 0, errors.join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
