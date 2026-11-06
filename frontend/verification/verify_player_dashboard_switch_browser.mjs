// The Player Dashboard settings screen (/admin/player-dashboard) against the real page with the API stubbed at the
// network layer. A club with only BetterStats switches its player page on and off, sets the PIN and the club site
// button, chooses and orders the modules, and copies the link, without BetterSelect anywhere.
//
// Asserts the exact body each control posts (an absent key is not a clear), what the screen says in each state
// (off, PIN off, hidden button, a club that also has BetterSelect), that the nav lists it for a BetterStats-only
// club, and 390px without horizontal scroll.
//
//   APP_URL=http://localhost:4173 SHOT_DIR=/tmp/dash node verification/verify_player_dashboard_switch_browser.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
if (SHOT) fs.mkdirSync(SHOT, { recursive: true })
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}

const CATALOGUE = [
  { key: 'cards', label: 'Player Cards', blurb: 'Their card collection.', enabled: true, blocked: null },
  { key: 'votes', label: 'Votes', blurb: 'Reminds them to vote.', enabled: true, blocked: null },
  { key: 'season', label: 'Season dashboard', blurb: 'Their season.', enabled: true, blocked: null },
  { key: 'squad', label: 'Your squad', blurb: 'The squads they are in.', enabled: false, blocked: 'Needs the BetterSelect module.' },
  { key: 'fees', label: 'Fees owing', blurb: 'What they owe the club.', enabled: false, blocked: 'Needs the BetterAdmin fees module.' },
]
const state = { enabled: true, has_select: false, availability_enabled: false, require_pin: true, show_on_site: true, token: 'tok123', mods: CATALOGUE.map((m) => ({ ...m })) }
const payload = () => ({
  enabled: state.enabled, has_select: state.has_select, availability_enabled: state.availability_enabled, require_pin: state.require_pin, show_on_site: state.show_on_site,
  dashboard_modules: state.mods, token: state.token, path: state.token ? `/playerdash/${state.token}` : null,
  phone_coverage: { with_phone: 18, total: 22 },
})

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  page.setDefaultTimeout(10000)
  const errors = [], calls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errors.push(m.text()) })
  await page.route('**/api/**', async (route) => {
    const req = route.request(), url = req.url(), method = req.method()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(url)) return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', entitlements: { modules: [], status: 'active' } })
    const path = new URL(url).pathname.replace(/^\/api/, '')
    if (!/^\/player-dashboard\//.test(path)) return json({})
    const body = req.postData() ? JSON.parse(req.postData()) : null
    calls.push({ method, path, body })
    if (path === '/player-dashboard/regenerate') { state.token = 'tok456'; return json(payload()) }
    if (method === 'POST' && path === '/player-dashboard/settings') {
      if ('enabled' in body) state.enabled = body.enabled
      if ('require_pin' in body) state.require_pin = body.require_pin
      if ('show_on_site' in body) state.show_on_site = body.show_on_site
      if ('dashboard_modules' in body) {
        const on = body.dashboard_modules
        state.mods = [...on.map((k) => CATALOGUE.find((m) => m.key === k)), ...CATALOGUE.filter((m) => !on.includes(m.key))].map((m) => ({ ...m, enabled: on.includes(m.key) }))
      }
    }
    return json(payload())
  })
  const shot = async (name) => { if (SHOT) await page.screenshot({ path: `${SHOT}/${name}.png`, fullPage: true }) }
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  const root = page.locator('[data-player-dashboard-admin]')
  const text = () => root.innerText()
  const lastPost = () => calls.filter((c) => c.method === 'POST').pop()
  const posts = () => calls.filter((c) => c.method === 'POST').length
  const segment = (attr, label) => page.locator(`[${attr}]`).getByRole('button', { name: label, exact: true })

  await page.goto(`${BASE}/admin/player-dashboard`)
  await root.waitFor({ timeout: 20000 })
  await page.waitForSelector('[data-dash-enabled-setting]')

  console.log('\na club with only BetterStats')
  check('the heading says Player Dashboard', /Player Dashboard/.test(await text()))
  check('the sidebar lists Player Dashboard', (await page.getByRole('link', { name: 'Player Dashboard' }).count()) > 0)
  check('it asks for nothing but BetterStats', /needs BetterStats and nothing else/i.test(await text()))
  check('no BetterSelect note when the club does not have it', (await page.locator('[data-dash-select-note]').count()) === 0)
  check('the link is the club origin plus the token', (await page.locator('input[readonly]').inputValue()) === `${new URL(BASE).origin}/playerdash/tok123`)
  check('a QR code is drawn', (await page.getByAltText('Player Dashboard link QR code').count()) === 1)
  check('phone coverage reads 18 of 22 and names the 4 who cannot sign in', /18\s+of\s+22/.test(await page.locator('[data-dash-coverage]').innerText()) && /4 players can't sign in/.test(await page.locator('[data-dash-coverage]').innerText()))
  check('the site button note says it is shown', /shows a Player Dashboard button/.test(await page.locator('[data-dash-state-note]').innerText()))
  const checked = await page.locator('[data-page-module]').evaluateAll((els) => els.map((e) => `${e.getAttribute('data-page-module')}:${e.getAttribute('data-on')}`))
  check('the module list shows what is on, then what is off', checked.join(',') === 'cards:yes,votes:yes,season:yes,squad:no,fees:no', checked.join(','))
  await shot('on-desktop')

  console.log('\nswitching it off and on')
  const before = posts()
  await segment('data-dash-enabled-setting', 'Off').click()
  await page.waitForFunction(() => /dashboard is off/.test(document.querySelector('[data-dash-state-note]').innerText))
  check('Off posts only enabled false', posts() === before + 1 && JSON.stringify(lastPost().body) === '{"enabled":false}', JSON.stringify(lastPost()))
  check('Off posts to the BetterStats route, not the BetterSelect one', lastPost().path === '/player-dashboard/settings' && !calls.some((c) => /availability/.test(c.path)))
  check('with it off the link and QR are not shown', (await page.locator('input[readonly]').count()) === 0 && (await page.getByAltText('Player Dashboard link QR code').count()) === 0)
  check('and the screen says why: nobody can open it', /Nobody can open it/.test(await text()))
  await shot('off')
  await segment('data-dash-enabled-setting', 'On').click()
  await page.waitForSelector('input[readonly]')
  check('On posts only enabled true', JSON.stringify(lastPost().body) === '{"enabled":true}', JSON.stringify(lastPost()))

  console.log('\nPIN and the site button')
  check('no PIN warning while the PIN is on', (await page.locator('[data-dash-nopin-note]').count()) === 0)
  await segment('data-dash-pin-setting', 'No PIN').click()
  await page.waitForSelector('[data-dash-nopin-note]')
  check('No PIN posts only require_pin false', JSON.stringify(lastPost().body) === '{"require_pin":false}', JSON.stringify(lastPost()))
  check('with no PIN the screen warns anyone with the link can open any page', /anyone who has the link can open any player's page/.test(await page.locator('[data-dash-nopin-note]').innerText()))
  check('and coverage stops saying they need a mobile to sign in', !/can't sign in without a mobile/.test(await page.locator('[data-dash-coverage]').innerText()))
  await segment('data-dash-pin-setting', 'Last-4 PIN').click()
  await page.waitForFunction(() => !document.querySelector('[data-dash-nopin-note]'))
  await segment('data-dash-site-setting', 'Hidden').click()
  await page.waitForFunction(() => /button is hidden on your public site/.test(document.querySelector('[data-dash-state-note]').innerText))
  check('Hidden posts only show_on_site false', JSON.stringify(lastPost().body) === '{"show_on_site":false}', JSON.stringify(lastPost()))
  check('hiding the button leaves the link on the screen', (await page.locator('input[readonly]').count()) === 1)
  await segment('data-dash-site-setting', 'Shown').click()
  await page.waitForFunction(() => /shows a Player Dashboard button/.test(document.querySelector('[data-dash-state-note]').innerText))

  console.log('\nmodules')
  await page.getByLabel('Show Votes').click()
  await page.waitForFunction(() => document.querySelector('[data-page-module="votes"]').getAttribute('data-on') === 'no')
  check('unticking Votes posts the remaining modules in order and nothing else', JSON.stringify(lastPost().body) === '{"dashboard_modules":["cards","season"]}', JSON.stringify(lastPost()))
  await page.getByRole('button', { name: 'Move Season dashboard up' }).click()
  await page.waitForFunction(() => document.querySelector('[data-page-module]').getAttribute('data-page-module') === 'season')
  check('moving Season up posts the new order', JSON.stringify(lastPost().body) === '{"dashboard_modules":["season","cards"]}', JSON.stringify(lastPost()))
  await page.getByLabel('Show Your squad').click()
  await page.waitForSelector('[data-module-blocked]')
  check('ticking a BetterSelect-only module says why it is not showing yet', /Not showing yet\. Needs the BetterSelect module\./.test(await page.locator('[data-module-blocked]').first().innerText()))
  check('and it posts the tick like any other', JSON.stringify(lastPost().body) === '{"dashboard_modules":["season","cards","squad"]}', JSON.stringify(lastPost()))

  console.log('\nthe link')
  page.once('dialog', (d) => d.accept())
  await page.getByRole('button', { name: 'Regenerate' }).click()
  await page.waitForFunction(() => document.querySelector('input[readonly]').value.endsWith('/playerdash/tok456'))
  check('Regenerate posts to /regenerate and the screen shows the new link', lastPost().path === '/player-dashboard/regenerate')

  console.log('\na club that also has BetterSelect')
  state.has_select = true
  state.availability_enabled = true
  await page.reload()
  await root.waitFor()
  await page.waitForSelector('[data-dash-select-note]')
  const note = await page.locator('[data-dash-select-note]').innerText()
  check('it says availability and votes have their own switch, and which way it is set', /availability and votes/.test(note) && /own switch in BetterSelect > Availability, which is on now/.test(note), note)
  check('and that this switch does not change it', /does not change it/.test(note))
  await segment('data-dash-enabled-setting', 'Off').click()
  await page.waitForFunction(() => /dashboard is off/.test(document.querySelector('[data-dash-state-note]').innerText))
  check('with the dashboard off but availability on, it says the link still opens for availability and votes', /still opens for availability and votes/.test(await page.locator('[data-dash-state-note]').innerText()))
  check('the post for that carries only the dashboard switch', JSON.stringify(lastPost().body) === '{"enabled":false}', JSON.stringify(lastPost()))
  await segment('data-dash-enabled-setting', 'On').click()
  await page.waitForSelector('input[readonly]')
  await shot('with-select')
  state.availability_enabled = false
  await page.reload()
  await root.waitFor()
  await page.waitForSelector('[data-dash-select-note]')
  check('with availability off the note says so', /which is off now/.test(await page.locator('[data-dash-select-note]').innerText()))

  console.log('\nthe phone')
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(250)
  check('no horizontal scroll at 390px', (await overflow()) <= 0, `over by ${await overflow()}px`)
  await segment('data-dash-enabled-setting', 'Off').click()
  await page.waitForFunction(() => /Nobody can open it/.test(document.querySelector('[data-dash-state-note]').innerText))
  check('no horizontal scroll at 390px with it off', (await overflow()) <= 0, `over by ${await overflow()}px`)
  await shot('phone-off')
  check('no page errors', errors.length === 0, errors.join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
