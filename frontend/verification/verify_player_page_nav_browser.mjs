// Drives a club's public site in Chromium with the API stubbed at the network layer:
// the Player Dashboard button next to Admin, and both reachable on a portrait phone.
//   * wide: PLAYER DASHBOARD sits beside ADMIN LOGIN and goes to the club's /avail link
//   * portrait phone: the bar has a person icon (no sideways overflow at 360 and
//     390px) and the menu has two big buttons, Player Dashboard and Admin Login
//   * Admin used to be unreachable on a phone; it is in the menu whether or not the
//     club shows the Player Dashboard button
//   * a club that hides the button, or has no link, shows no Player Dashboard anywhere
//   * signed in, the Admin entry reads ADMIN
//
//   npx vite preview --port 5199 &    node verify_player_page_nav_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOT = process.env.SHOT_DIR || '/tmp'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

const CLUB = (path) => ({
  id: 'o1', slug: 'dash', name: 'Dash Cricket Club', short_name: 'DCC', is_active: true, primary_color: null, accent_color: null,
  logo_url: null, theme_config: {}, player_name_format: 'last_first', website_enabled: false, player_page_path: path,
})

async function open(browser, width, { path = '/avail/tok123', signedIn = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 800 }, isMobile: width < 500, hasTouch: width < 500 })
  const page = await ctx.newPage()
  page.setDefaultTimeout(6000)
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.route('**/api/**', (r) => json(r, []))
  await page.route('**/api/clubs/dash', (r) => json(r, CLUB(path)))
  await page.route('**/api/auth/me', (r) => signedIn
    ? json(r, { id: 'u1', username: 'a', email: 'a@b.c', role: 'club_admin', organisation_id: 'o1', club_slug: 'dash', capabilities: ['*'], entitlements: { modules: ['select'], core_live: true, status: 'active' } })
    : json(r, { detail: 'Not authenticated' }, 401))
  await page.route(/\/api\/public\/availability\/tok123(\/.*)?$/, (r) => json(r, { club: { name: 'Dash Cricket Club' }, require_pin: true, players: [] }))
  await page.goto(`${BASE}/dash`)
  await page.locator('header').waitFor()
  await page.waitForTimeout(500)
  return { ctx, page, errors }
}
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  await safe('wide', async () => {
    console.log('\n── Wide screen ──')
    const { ctx, page, errors } = await open(browser, 1280)
    const pp = page.locator('[data-player-page-link]')
    check('PLAYER DASHBOARD is shown', (await pp.count()) === 1 && /PLAYER DASHBOARD/.test(await pp.innerText()))
    check('it goes to the club\'s own link', (await pp.getAttribute('href')) === '/avail/tok123')
    const adm = page.locator('header a', { hasText: 'ADMIN LOGIN' })
    const [a, b] = [await pp.boundingBox(), await adm.boundingBox()]
    check('it sits right beside the Admin button, on the same row', b.x - (a.x + a.width) < 24 && b.x > a.x && Math.abs(a.y - b.y) < 6, JSON.stringify([a, b]))
    check('the phone icon is not drawn', !(await page.locator('[data-player-page-icon]').isVisible()))
    await pp.click()
    await page.waitForURL('**/avail/tok123')
    check('clicking opens the player page', /\/avail\/tok123$/.test(page.url()))
    check('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  })

  await safe('tablet', async () => {
    console.log('\n── In between (640 to 767px): both words in the bar ──')
    for (const w of [640, 700, 767, 800]) {
      const { ctx, page } = await open(browser, w)
      const pp = await page.locator('[data-player-page-link]').boundingBox()
      const adm = await page.locator('header a', { hasText: 'ADMIN LOGIN' }).boundingBox()
      check(`${w}px: no sideways overflow and both buttons are on screen`, (await overflow(page)) <= 0 && pp && adm && adm.x + adm.width <= w, JSON.stringify([await overflow(page), pp, adm]))
      await ctx.close()
    }
  })

  await safe('portrait', async () => {
    console.log('\n── Portrait phone ──')
    for (const w of [360, 390]) {
      const { ctx, page } = await open(browser, w)
      check(`${w}px: no sideways overflow with the button on`, (await overflow(page)) <= 0, String(await overflow(page)))
      check(`${w}px: the wide-screen words are not squeezed into the bar`, !(await page.locator('[data-player-page-link]').isVisible()))
      check(`${w}px: the person icon is visible and labelled`, (await page.locator('[data-player-page-icon]').isVisible()) && (await page.locator('[data-player-page-icon]').getAttribute('aria-label')) === 'Player dashboard')
      const icon = await page.locator('[data-player-page-icon]').boundingBox()
      check(`${w}px: the icon is a real touch target`, icon.width >= 32 && icon.height >= 32, JSON.stringify(icon))
      await ctx.close()
    }
    const { ctx, page } = await open(browser, 390)
    await page.getByRole('button', { name: 'Open menu' }).click()
    await page.locator('[data-mobile-entries]').waitFor()
    check('the menu leads with Player Dashboard and Admin Login', (await page.locator('[data-mobile-player-page]').isVisible()) && (await page.locator('[data-mobile-admin]').isVisible()))
    const [pb, ab] = [await page.locator('[data-mobile-player-page]').boundingBox(), await page.locator('[data-mobile-admin]').boundingBox()]
    check('both are tall enough to tap and side by side', pb.height >= 40 && ab.height >= 40 && Math.abs(pb.y - ab.y) < 4, JSON.stringify([pb, ab]))
    check('Admin Login goes to the login page', (await page.locator('[data-mobile-admin]').getAttribute('href')) === '/login')
    await page.screenshot({ path: `${SHOT}/nav-390-menu.png` })
    await page.locator('[data-mobile-player-page]').click()
    await page.waitForURL('**/avail/tok123')
    check('Player Dashboard opens the player page and the menu closes behind it', /\/avail\/tok123$/.test(page.url()))
    await ctx.close()
  })

  await safe('hidden', async () => {
    console.log('\n── The club does not show it ──')
    const { ctx, page } = await open(browser, 390, { path: null })
    check('no icon in the bar', (await page.locator('[data-player-page-icon]').count()) === 0)
    await page.getByRole('button', { name: 'Open menu' }).click()
    await page.locator('[data-mobile-entries]').waitFor()
    check('no Player Dashboard in the menu', (await page.locator('[data-mobile-player-page]').count()) === 0)
    check('but Admin Login is still reachable on a phone', (await page.locator('[data-mobile-admin]').isVisible()))
    await ctx.close()
    const wide = await open(browser, 1280, { path: null })
    check('wide: no PLAYER DASHBOARD button either', (await wide.page.locator('[data-player-page-link]').count()) === 0)
    await wide.ctx.close()
  })

  await safe('signed in', async () => {
    console.log('\n── Signed in ──')
    const { ctx, page } = await open(browser, 390, { signedIn: true })
    await page.getByRole('button', { name: 'Open menu' }).click()
    await page.locator('[data-mobile-entries]').waitFor()
    check('the menu says ADMIN and goes to /admin', (await page.locator('[data-mobile-admin]').innerText()).trim() === 'ADMIN' && (await page.locator('[data-mobile-admin]').getAttribute('href')) === '/admin')
    await ctx.close()
  })

  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
