// Drives the real Admin > Players screen (Core) in Chromium with the API stubbed
// at the network layer. The ask (Oct 2026): an Active filter on the Players list.
// "Active" is the server's `is_current`: not marked inactive, not dormant (the
// club's window, "no longer dormant" marks honoured). Search looks at everyone.
//
//   APP_URL=http://localhost:4173 node verify_players_active_filter_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}
const P = (id, name, extra) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null, hero_photo_url: null,
  gender: null, is_player: true, player_role: null, is_overseas: false, skill_positions: [],
  status: 'active', is_public: true, squad_team_id: null, squad_team_ids: [], age: null,
  last_played: null, is_current: true, is_dormant: false, ...extra,
})
const PLAYERS = [
  P('a', 'Abbas Aamir'),                                           // active
  P('b', 'Abbott Brad', { status: 'inactive', is_current: false }),  // marked inactive
  P('c', 'Abeygunasekara Gihan', { is_current: false, is_dormant: true, last_played: '2022-01-01' }), // dormant
  P('d', 'Adams Dan', { is_overseas: true }),                      // active overseas
  P('e', 'Aitken Ed', { is_current: false, is_dormant: true, is_overseas: true, last_played: '2021-01-01' }),
]
const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1',
  club_slug: 'verify-cc', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
async function stub(page, opts = {}) {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json(ME)
    if (url.includes('/club-admin/players')) return json(opts.noFlag ? PLAYERS.map(({ is_current, is_dormant, ...r }) => r) : PLAYERS)
    if (url.includes('/club-admin/settings')) return json({ player_name_format: 'last_first' })
    if (url.match(/\/teams(\?|$)/)) return json([])
    return json({})
  })
}
const names = (page) => page.evaluate(() => [...document.querySelectorAll('.pl-row')].map((r) => r.querySelector('.pl-name, strong, [class*="name"]')?.textContent.trim()).filter(Boolean))
const count = (page) => page.locator('.pl-row').count()

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await stub(page)
  await page.goto(`${BASE}/admin/players`)
  await page.waitForSelector('.pl-row', { timeout: 20000 })
  await page.waitForTimeout(300)
  const btn = page.locator('[data-active-filter]')

  check('the Active only control is drawn', await btn.count() === 1)
  check('off by default: all five players listed', await count(page) === 5, String(await count(page)))
  await btn.click(); await page.waitForTimeout(200)
  check('Active only: inactive and dormant players drop out (Abbas, Adams left)', await count(page) === 2, String(await count(page)))
  check('...and the button reads pressed', await btn.getAttribute('aria-pressed') === 'true')
  check('the All range tab count follows (2)', await page.locator('.pl-rangetab', { hasText: /^All/ }).first().innerText().then((t) => /2/.test(t)))

  await page.getByRole('button', { name: 'Overseas' }).click(); await page.waitForTimeout(200)
  check('Active only + Overseas combine: only the active overseas player (Adams)', await count(page) === 1, String(await count(page)))
  await page.getByRole('button', { name: 'All', exact: true }).first().click(); await page.waitForTimeout(200)

  await page.fill('.pl-search input', 'brad'); await page.waitForTimeout(250)
  check('searching ignores Active only: the inactive player is found by name', await count(page) === 1, String(await count(page)))
  await page.fill('.pl-search input', ''); await page.waitForTimeout(250)
  check('clearing the search brings the filter back (2)', await count(page) === 2, String(await count(page)))

  await page.reload(); await page.waitForSelector('.pl-row', { timeout: 20000 })
  check('remembered on this device across a reload', await count(page) === 2 && await page.locator('[data-active-filter]').getAttribute('aria-pressed') === 'true', String(await count(page)))
  await page.locator('[data-active-filter]').click(); await page.waitForTimeout(200)
  check('turning it off lists everyone again', await count(page) === 5, String(await count(page)))
  const over = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: screen.width }))
  check('390px: no sideways overflow', over.sw <= over.cw, JSON.stringify(over))
  if (process.env.SHOT_DIR) { await page.locator('[data-active-filter]').click(); await page.waitForTimeout(200); await page.screenshot({ path: process.env.SHOT_DIR + '/players_active_390.png' }) }
  await ctx.close()

  // An older server (no is_current on the payload) must not empty the list.
  const c2 = await browser.newContext({ viewport: { width: 1200, height: 900 } })
  const p2 = await c2.newPage()
  await stub(p2, { noFlag: true })
  await p2.goto(`${BASE}/admin/players`)
  await p2.waitForSelector('.pl-row', { timeout: 20000 })
  await p2.locator('[data-active-filter]').click(); await p2.waitForTimeout(200)
  check('payload without is_current: Active only filters nothing rather than emptying the list', await count(p2) === 5, String(await count(p2)))
  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
