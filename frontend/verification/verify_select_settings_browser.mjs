// Drives the REAL BetterSelect Settings screen in Chromium with the API stubbed at
// the network layer.
//
// Asked for (Applecross, Oct 2026): a colour for "half available" (free one weekend
// of a two-day game, away the other), one for week 1 and one for week 2, kept in a
// BetterSelect Settings screen with the other small switches, to clear the UI.
// Checks: Settings is in the Setup menu; both colours show with their current
// value; changing one sends exactly that key and repaints the page's colour
// variable at once; a bad hex sends nothing; Reset sends null for that colour only;
// a failed save puts the colour back; Maybe sends allow_maybe; the junior switch is
// the same device preference the screens read; nothing overflows at 390px.
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_select_settings_browser.mjs
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
const PASS = [], FAIL = []
const ok = (name, cond, detail = '') => { (cond ? PASS : FAIL).push(name); console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  none: ' + String(detail).slice(0, 200) : ''}`) }
const ME = { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' } }
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

const run = async () => {
  mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  for (const [label, vp] of [['desktop', { width: 1280, height: 900 }], ['phone', { width: 390, height: 844 }]]) {
    console.log(`\n# ${label}`)
    const ctx = await browser.newContext({ viewport: vp })
    const page = await ctx.newPage()
    const patches = [], selfService = []
    let failSave = false
    const saved = { w1: '#a855f7', w2: '#06b6d4' }
    await page.route('**/api/**', (r) => json(r, {}))
    await page.route('**/api/auth/me', (r) => json(r, ME))
    await page.route(/\/api\/club-admin\/settings$/, (r) => json(r, { player_name_format: 'first_last' }))
    await page.route(/\/api\/availability\/config/, (r) => json(r, { allow_maybe: true, half_colours: { ...saved } }))
    await page.route(/\/api\/selection-rules$/, (r) => json(r, { rules: [], kinds: [], options: {}, settings: { half_colours: { ...saved } } }))
    await page.route(/\/api\/selection-rules\/settings$/, async (r) => {
      const b = JSON.parse(r.request().postData() || '{}')
      patches.push(b)
      if (failSave) return json(r, { detail: 'Could not save' }, 500)
      for (const k of ['w1', 'w2']) if (`half_colour_${k}` in b) saved[k] = b[`half_colour_${k}`] || (k === 'w1' ? '#a855f7' : '#06b6d4')
      return json(r, { half_colours: { ...saved } })
    })
    await page.route(/\/api\/availability\/self-service$/, async (r) => {
      if (r.request().method() === 'POST') selfService.push(JSON.parse(r.request().postData() || '{}'))
      return json(r, { allow_maybe: false })
    })
    await page.goto(`${BASE}/admin/betterselect/settings`, { waitUntil: 'domcontentloaded' })
    const open = await page.locator('[data-select-settings]').waitFor({ timeout: 15000 }).then(() => true).catch(() => false)
    ok('the Settings screen opens', open)
    if (!open) { await ctx.close(); continue }
    const body = async () => (await page.locator('body').innerText()).replace(/\s+/g, ' ')
    const cssVar = (n) => page.evaluate((v) => document.documentElement.style.getPropertyValue(v).trim(), n)
    const hexOf = (k) => page.locator(`[data-half-colour="${k}"] input[type="text"]`)

    if (vp.width > 800) ok('Settings is in the Setup menu', /Settings/.test(await page.locator('nav, aside').first().innerText().catch(() => '')) || (await page.getByRole('link', { name: /^Settings/ }).count()) > 0)
    ok('both colours are shown with their current value', (await hexOf('w1').inputValue()) === '#a855f7' && (await hexOf('w2').inputValue()) === '#06b6d4')
    ok('a sample dot sits beside each', (await page.locator('[data-half-sample]').count()) === 2)
    ok('the screen explains what half available means', /half available/i.test(await body()))

    // Change week 1.
    patches.length = 0
    await hexOf('w1').fill('#FF0000')
    await page.waitForTimeout(400)
    ok('changing week 1 sends only that key', patches.length === 1 && Object.keys(patches[0]).join() === 'half_colour_w1' && patches[0].half_colour_w1.toLowerCase() === '#ff0000', JSON.stringify(patches))
    ok("the page's colour variable follows at once", (await cssVar('--pb-half-w1')) === '#ff0000', await cssVar('--pb-half-w1'))
    ok('week 2 is untouched', (await cssVar('--pb-half-w2')) !== '#ff0000')

    // A bad value sends nothing.
    patches.length = 0
    await hexOf('w2').fill('#12')
    await hexOf('w2').fill('purple')
    await page.waitForTimeout(300)
    ok('a half-typed or invalid colour sends nothing', patches.length === 0, JSON.stringify(patches))
    ok('...and says so (the box goes red)', await hexOf('w2').evaluate((el) => el.className.includes('border-pb-red')))

    // Reset.
    await hexOf('w2').fill('#06b6d4')
    patches.length = 0
    await hexOf('w1').fill('#ff0000')
    await page.waitForTimeout(200)
    patches.length = 0
    await page.locator('[data-half-colour="w1"]').getByRole('button', { name: 'Reset' }).click()
    await page.waitForTimeout(400)
    ok('Reset sends null for that colour only', patches.length === 1 && patches[0].half_colour_w1 === null && !('half_colour_w2' in patches[0]), JSON.stringify(patches))
    ok('...and the box is back to the default', (await hexOf('w1').inputValue()) === '#a855f7')

    // A failed save puts it back.
    failSave = true
    await hexOf('w1').fill('#00ff00')
    await page.waitForTimeout(500)
    ok('a failed save puts the colour back', (await hexOf('w1').inputValue()) === '#a855f7' && (await cssVar('--pb-half-w1')) !== '#00ff00', `${await hexOf('w1').inputValue()} ${await cssVar('--pb-half-w1')}`)
    failSave = false

    // Maybe.
    await page.locator('[data-select-settings] >> text=Maybe answer').locator('xpath=ancestor::div[contains(@class,"flex-wrap")][1]').getByRole('button', { name: 'Off' }).click()
    await page.waitForTimeout(300)
    ok('turning Maybe off sends allow_maybe false', selfService.length === 1 && selfService[0].allow_maybe === false, JSON.stringify(selfService))

    // Juniors: the same device preference the screens read.
    await page.locator('[data-select-settings] >> text=Junior grades').locator('xpath=ancestor::div[contains(@class,"flex-wrap")][1]').getByRole('button', { name: 'Show' }).click()
    await page.waitForTimeout(200)
    const stored = await page.evaluate(() => Object.keys(localStorage).filter((k) => localStorage.getItem(k) === 'true' && /juniors/.test(k)))
    ok('the junior switch writes the device preference the screens read', stored.length === 1, JSON.stringify(stored))

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
    ok(`no horizontal overflow at ${vp.width}px`, overflow <= 0, String(overflow))
    await page.screenshot({ path: join(SHOTS, `select_settings_${label}.png`), fullPage: true })
    await ctx.close()
  }
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run()
