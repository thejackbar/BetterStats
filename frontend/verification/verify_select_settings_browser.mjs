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
    const savedNames = { w1: 'W1', w2: 'W2' }
    const T1 = '11111111-1111-4111-8111-111111111111', T2 = '22222222-2222-4222-8222-222222222222'
    const cfgNow = () => ({ allow_maybe: true, half_colours: { ...saved }, week_names: { ...savedNames }, played_years: { selection: 3, availability: 0 }, team_defaults: [],
      squads: [{ id: 'a', name: 'Club 1st XI', sequence: 1 }, { id: 'b', name: 'Club 2nd XI', sequence: 2 }] })
    await page.route('**/api/**', (r) => json(r, {}))
    await page.route('**/api/auth/me', (r) => json(r, ME))
    await page.route(/\/api\/club-admin\/settings$/, (r) => json(r, { player_name_format: 'first_last' }))
    await page.route(/\/api\/availability\/config/, (r) => json(r, cfgNow()))
    await page.route(/\/api\/selection-rules$/, (r) => json(r, { rules: [], kinds: [], options: { teams: [{ value: T1, label: '1st XI' }, { value: T2, label: "Women's XI" }] }, settings: { half_colours: { ...saved } } }))
    await page.route(/\/api\/selection-rules\/settings$/, async (r) => {
      const b = JSON.parse(r.request().postData() || '{}')
      patches.push(b)
      if (failSave) return json(r, { detail: 'Could not save' }, 500)
      for (const k of ['w1', 'w2']) if (`week_name_${k}` in b) savedNames[k] = b[`week_name_${k}`] || (k === 'w1' ? 'W1' : 'W2')
      for (const k of ['w1', 'w2']) if (`half_colour_${k}` in b) saved[k] = b[`half_colour_${k}`] || (k === 'w1' ? '#a855f7' : '#06b6d4')
      return json(r, { half_colours: { ...saved }, week_names: { ...savedNames }, played_years: { selection: b.played_years_selection ?? 3, availability: b.played_years_availability ?? 0 }, team_defaults: b.team_defaults || [] })
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

    // What the club calls the weeks.
    const nameBox = (k) => page.locator(`[data-week-name="${k}"] input`)
    ok('both week names are shown, W1 and W2 to start', (await nameBox('w1').inputValue()) === 'W1' && (await nameBox('w2').inputValue()) === 'W2')
    patches.length = 0
    await nameBox('w1').fill('A')
    await nameBox('w1').press('Enter')
    await page.waitForTimeout(400)
    ok('naming the first week "A" sends only that key', patches.length === 1 && Object.keys(patches[0]).join() === 'week_name_w1' && patches[0].week_name_w1 === 'A', JSON.stringify(patches))
    ok('the colour rows and the legend follow at once', /Available for A only/.test(await body()) && /A Only/.test(await body()), (await body()).slice(0, 300))
    ok('the second week still reads W2', /Available for W2 only/.test(await body()))
    patches.length = 0
    await nameBox('w2').fill('  B  ')
    await nameBox('w2').blur()
    await page.waitForTimeout(400)
    ok('the second week is trimmed and saved as "B"', patches.length === 1 && patches[0].week_name_w2 === 'B' && !('week_name_w1' in patches[0]), JSON.stringify(patches))
    patches.length = 0
    await nameBox('w1').fill('')
    await nameBox('w1').blur()
    await page.waitForTimeout(400)
    ok('a blank name sends null (back to W1)', patches.length === 1 && patches[0].week_name_w1 === null, JSON.stringify(patches))
    ok('...and the box reads W1 again', (await nameBox('w1').inputValue()) === 'W1')
    patches.length = 0
    await page.locator('[data-week-name="w2"]').getByRole('button', { name: 'Reset' }).click()
    await page.waitForTimeout(400)
    ok('Reset sends null for that name only', patches.length === 1 && patches[0].week_name_w2 === null && !('week_name_w1' in patches[0]), JSON.stringify(patches))
    ok('a name is capped at ten characters', (await nameBox('w1').getAttribute('maxlength')) === '10')

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

    // Players listed.
    patches.length = 0
    await page.locator('[data-window="selection"]').selectOption('0')
    await page.waitForTimeout(300)
    ok('Selection board window: "Played any time" sends played_years_selection 0', patches.length === 1 && patches[0].played_years_selection === 0 && Object.keys(patches[0]).length === 1, JSON.stringify(patches))
    patches.length = 0
    await page.locator('[data-window="selection"]').selectOption('-1')
    await page.waitForTimeout(300)
    ok('...and "Played this season" sends -1', patches.length === 1 && patches[0].played_years_selection === -1, JSON.stringify(patches))
    patches.length = 0
    await page.locator('[data-window="availability"]').selectOption('5')
    await page.waitForTimeout(300)
    ok('Availability window sends played_years_availability 5', patches.length === 1 && patches[0].played_years_availability === 5, JSON.stringify(patches))
    ok('Availability has no "this season" (the matrix has no season to measure from)', (await page.locator('[data-window="availability"] option[value="-1"]').count()) === 0)
    ok('Selection board does', (await page.locator('[data-window="selection"] option[value="-1"]').count()) === 1)

    // Team defaults.
    const lastRules = () => [...patches].reverse().find((b) => 'team_defaults' in b)?.team_defaults
    ok('no team rules yet', (await page.locator('[data-team-rule]').count()) === 0)
    patches.length = 0
    await page.locator('[data-add-team-rule]').click()
    await page.waitForTimeout(500)
    ok('a new rule shows as not yet saved', (await page.locator('[data-team-rule]').count()) === 1 && (await page.locator('[data-rule-state="incomplete"]').count()) === 1)
    ok('...and a half-made rule is not sent as a rule', lastRules() === undefined || lastRules().length === 0, JSON.stringify(patches))
    const rule = page.locator('[data-team-rule]').first()
    patches.length = 0
    await rule.getByLabel("Women's XI").check()
    await page.waitForTimeout(500)
    ok('a team alone is still half made (nothing to start on)', (lastRules() || []).length === 0, JSON.stringify(patches))
    await rule.getByRole('button', { name: 'Women', exact: true }).click()
    await page.waitForTimeout(600)
    const r1 = (lastRules() || [])[0]
    ok('team + Gender = Women is saved as a rule', !!r1 && r1.team_ids.join() === T2 && r1.gender === 'female', JSON.stringify(patches))
    ok('...and shows as saved', (await page.locator('[data-rule-state="saved"]').count()) === 1)
    patches.length = 0
    await rule.getByRole('button', { name: 'Top', exact: true }).click()
    await page.waitForTimeout(600)
    await rule.getByLabel('Number of squads').fill('2')
    await page.waitForTimeout(600)
    const r2 = (lastRules() || [])[0]
    ok('Squads shown = Top 2 is saved', !!r2 && r2.top_squads === 2 && (r2.squads || []).length === 0, JSON.stringify(r2))
    patches.length = 0
    await rule.getByRole('button', { name: 'Chosen', exact: true }).click()
    await page.waitForTimeout(300)
    await rule.getByLabel('Club 1st XI').check()
    await page.waitForTimeout(600)
    const r3 = (lastRules() || [])[0]
    ok('Chosen squads are saved by name and replace the top-N', !!r3 && r3.squads.join() === 'Club 1st XI' && !r3.top_squads, JSON.stringify(r3))
    patches.length = 0
    await rule.getByLabel('Played within').selectOption('0')
    await page.waitForTimeout(600)
    ok("a team's own window is saved on the rule", (lastRules() || [])[0]?.played_years === 0, JSON.stringify(lastRules()))
    // A second rule, then delete both.
    await page.locator('[data-add-team-rule]').click()
    await page.waitForTimeout(300)
    ok('rules can be added without limit of one', (await page.locator('[data-team-rule]').count()) === 2, `${await page.locator('[data-team-rule]').count()} rules; add buttons: ${await page.locator('[data-add-team-rule]').count()}; ids: ${(await page.locator('[data-team-rule]').evaluateAll((e) => e.map((x) => x.getAttribute('data-team-rule')))).join()}`)
    patches.length = 0
    await page.locator('[data-team-rule]').nth(1).getByRole('button', { name: 'Delete rule' }).click()
    await page.waitForTimeout(600)
    ok('deleting a rule removes just that one', (await page.locator('[data-team-rule]').count()) === 1 && (lastRules() || []).length === 1, JSON.stringify(lastRules()))
    patches.length = 0
    await page.locator('[data-team-rule]').first().getByRole('button', { name: 'Delete rule' }).click()
    await page.waitForTimeout(600)
    ok('deleting the last sends an empty list', Array.isArray(lastRules()) && lastRules().length === 0, JSON.stringify(patches))

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
