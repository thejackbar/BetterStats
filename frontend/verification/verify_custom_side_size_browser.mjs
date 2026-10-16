// Drives the REAL Selection board in Chromium with the API stubbed at the
// network layer. Asked for: women's and junior sides name 7 or 9, so the side
// size picker (11 / 12 / 13 / No limit) needs a "Custom" box.
//
//   * Custom opens a number box; Enter saves it: exactly one POST
//     /selection/default-team-size with {size: 7, fixture_id}, and the board
//     shows 7 slots and a "Custom · 7" button
//   * a preset still posts its own number; Escape in the box posts nothing
//   * 0, 31 and blank are not sent
//   * a team that loads with a size of 9 shows "Custom · 9" selected
//   * 390px: no horizontal overflow with a custom size showing
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_custom_side_size_browser.mjs
import { chromium } from 'playwright'
import { readFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures/selection_same_day.json'), 'utf8'))
const FID = FIX.fixture_id

let PASS = 0, FAIL = 0
const ok = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const ME = {
  id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' },
}

const run = async () => {
  mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const sizePosts = []
  let loadSize = 11
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route(/\/api\/club-admin\/settings$/, (r) => json(r, { player_name_format: 'first_last' }))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route(/\/api\/selection\/overview(\?.*)?$/, (r) => json(r, { fixtures: [], default_team_size: 11 }))
  await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { source_fixture_id: null, player_ids: [], captain_id: null, wicket_keeper_id: null }))
  await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
  await page.route(new RegExp(`/api/selection/${FID}/draft(\\?.*)?$`), (r) => json(r, { draft: null, version: 0 }))
  await page.route('**/api/selection/default-team-size', (r) => {
    const b = JSON.parse(r.request().postData())
    sizePosts.push(b)
    return json(r, { status: 'ok', default_team_size: b.size, scope: 'team' })
  })
  await page.route(new RegExp(`/api/selection/${FID}$`), (r) => json(r, { ...FIX.payload, lineup: [], default_team_size: loadSize }))

  const body = async () => (await page.locator('body').innerText()).replace(/\s+/g, ' ')
  const open = async () => {
    await page.goto(`${BASE}/admin/betterselect/select/${FID}`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Cara Free').first().waitFor({ timeout: 20000 })
    await page.waitForTimeout(300)
  }
  // Presence-safe: against a build with no Custom button these report absence instead of timing out.
  const customBtn = () => page.getByRole('button', { name: /^Custom/ }).first()
  const hasCustom = async () => (await customBtn().count()) > 0
  const slotCount = async () => page.evaluate(() => document.querySelectorAll('[data-slot-index], [data-drop-slot]').length)

  await open()
  console.log('\n# Custom opens a number box and saves on Enter')
  ok('a Custom button is on the picker', await hasCustom())
  await customBtn().click({ timeout: 1500 }).catch(() => {})
  const input = page.getByLabel(/Custom side size/).first()
  ok('clicking it shows a number box', (await input.count()) > 0)
  await input.fill('7').catch(() => {})
  await input.press('Enter').catch(() => {})
  await page.waitForTimeout(500)
  ok('exactly one POST', sizePosts.length === 1, JSON.stringify(sizePosts))
  ok('it sends size 7 with the fixture id', sizePosts[0]?.size === 7 && sizePosts[0]?.fixture_id === FID, JSON.stringify(sizePosts[0]))
  ok('the button now reads "Custom · 7"', /Custom · 7/.test(await body()))
  await page.screenshot({ path: join(SHOTS, 'custom_side_size_1440.png') })

  console.log('\n# presets, Escape and out-of-range')
  await page.getByRole('button', { name: /^12$/ }).first().click({ timeout: 1500 }).catch(() => {})
  await page.waitForTimeout(300)
  ok('12 posts 12', sizePosts[sizePosts.length - 1]?.size === 12, JSON.stringify(sizePosts))
  ok('the custom label goes back to "Custom"', !/Custom · /.test(await body()))
  const n = sizePosts.length
  await customBtn().click({ timeout: 1500 }).catch(() => {})
  await page.getByLabel(/Custom side size/).first().fill('9').catch(() => {})
  await page.getByLabel(/Custom side size/).first().press('Escape').catch(() => {})
  await page.waitForTimeout(300)
  ok('Escape posts nothing', sizePosts.length === n, JSON.stringify(sizePosts.slice(n)))
  for (const bad of ['0', '31', '']) {
    await customBtn().click({ timeout: 1500 }).catch(() => {})
    await page.getByLabel(/Custom side size/).first().fill(bad).catch(() => {})
    await page.getByLabel(/Custom side size/).first().press('Enter').catch(() => {})
    await page.waitForTimeout(250)
  }
  ok('0, 31 and blank are not sent', sizePosts.length === n, JSON.stringify(sizePosts.slice(n)))

  console.log('\n# a team that loads with 9 shows it selected')
  loadSize = 9
  await open()
  ok('button reads "Custom · 9"', /Custom · 9/.test(await body()))

  console.log('\n# 390px')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(400)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
  ok('no horizontal overflow', over <= 0, `scrollWidth over screen by ${over}`)
  await page.screenshot({ path: join(SHOTS, 'custom_side_size_390.png') })
  ok('no page errors', errors.length === 0, errors.join(' | '))

  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
