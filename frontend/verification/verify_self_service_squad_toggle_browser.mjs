// Drives the real BetterSelect Availability screen in Chromium with the API
// stubbed at the network layer. A club may not want players to know which squad
// they are in, so the self-service panel has a "Show squad" switch.
// Checks: the switch is there once the link is on and not before; it reads the
// club's saved value; a tap sends exactly {show_squad} and nothing else; the
// help line changes with it; the other switches still send only their own key;
// 390px does not overflow.
//
//   APP_URL=http://localhost:4173 node verify_self_service_squad_toggle_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}
const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }

const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin',
  organisation_id: 'org-1', club_slug: 'verify-cc', capabilities: [],
  entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
const MATRIX = {
  dates: [{ date: plusDays(3), fixtures: [{ id: 'f1', opponent_name: 'Willetton', home_away: 'HOME', role: 'single', two_day: false }] }],
  players: [], availability: {}, all_squads: [], dormancy_months: 24, rules: { active: false, applied: [] }, squad_next: {},
}
const cfg = (over = {}) => ({
  enabled: true, require_pin: true, show_squad: false, token: 'tok123', path: '/avail/tok123',
  phone_coverage: { with_phone: 10, total: 12 }, ...over,
})

async function openPanel(browser, initial, width = 1280) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500 })
  const page = await ctx.newPage()
  const state = { cfg: initial, posts: [] }
  await page.route('**/api/**', async (route) => {
    const req = route.request(), url = req.url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json(ME)
    if (url.includes('/availability/matrix')) return json(MATRIX)
    if (/\/availability\/self-service$/.test(url) && req.method() === 'POST') {
      const body = JSON.parse(req.postData() || '{}')
      state.posts.push(body)
      state.cfg = { ...state.cfg, ...body }
      return json(state.cfg)
    }
    if (/\/availability\/self-service$/.test(url)) return json(state.cfg)
    return json({})
  })
  await page.goto(`${BASE}/admin/betterselect/availability`)
  await page.getByText('Self-service link').first().waitFor({ timeout: 20000 })
  await page.getByText('Self-service link').first().click()
  await page.waitForTimeout(300)
  return { ctx, page, state }
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  let { ctx, page, state } = await openPanel(browser, cfg({ show_squad: false }))
  const setting = page.locator('[data-show-squad-setting]')
  check('the Show squad switch is on the panel', (await setting.count()) === 1)
  check('it is labelled Show squad', /show squad/i.test((await setting.innerText().catch(() => '')) || ''))
  const panelText = (await page.locator('body').innerText()).toLowerCase()
  check('saved off: the help line says players are not told their squad', panelText.includes('players are not told which squad they are in'))

  await setting.getByRole('button', { name: 'On', exact: true }).click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(300)
  check('turning it on sends exactly {show_squad: true}', state.posts.length === 1 && JSON.stringify(state.posts[0]) === '{"show_squad":true}', JSON.stringify(state.posts))
  const onText = (await page.locator('body').innerText()).toLowerCase()
  check('on: the help line now describes the bold squad games', onText.includes('players see their own squad') && !onText.includes('players are not told'))

  await setting.getByRole('button', { name: 'Off', exact: true }).click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(300)
  check('turning it off sends exactly {show_squad: false}', state.posts.length === 2 && JSON.stringify(state.posts[1]) === '{"show_squad":false}', JSON.stringify(state.posts))

  // the neighbouring PIN switch still sends only its own key
  await page.getByRole('button', { name: 'No PIN' }).click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(300)
  check('the PIN switch sends only require_pin', state.posts.length === 3 && JSON.stringify(state.posts[2]) === '{"require_pin":false}', JSON.stringify(state.posts[2]))
  await ctx.close()

  // saved on: the switch opens showing On
  ;({ ctx, page, state } = await openPanel(browser, cfg({ show_squad: true })))
  const t2 = (await page.locator('body').innerText()).toLowerCase()
  check('saved on: the help line describes the bold squad games', t2.includes('players see their own squad'))
  await ctx.close()

  // link switched off: no squad switch to offer
  ;({ ctx, page, state } = await openPanel(browser, cfg({ enabled: false, token: null, path: null })))
  check('link off: no Show squad switch', (await page.locator('[data-show-squad-setting]').count()) === 0)
  await ctx.close()

  // phone width
  ;({ ctx, page, state } = await openPanel(browser, cfg(), 390))
  const w = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, screen: window.screen.width }))
  check('390px: no sideways overflow', w.sw <= Math.max(w.screen, 390), JSON.stringify(w))
  check('390px: the switch is on the panel', (await page.locator('[data-show-squad-setting]').count()) === 1)
  if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/self-service-squad-390.png`, fullPage: false })
  await ctx.close()

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(2) })
