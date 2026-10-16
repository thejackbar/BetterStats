// Drives the REAL screens in Chromium with the API stubbed at the network layer:
//   * BetterSelect > Selection rules > "Selection emails": pick a template for the
//     captain's email, Save sends exactly the two link keys, Preview posts the
//     template id and shows the made-up match, a club without BetterComms is told so.
//   * Admin > Comms > Templates: a club (not a Super Admin) gets the Subject field and
//     the selection variables.
//   * 390px: no horizontal overflow.
//
//   npx vite build --outDir /var/tmp/np-dist && npx vite preview --outDir /var/tmp/np-dist --port 5199 &
//   node verification/verify_selection_email_templates_browser.mjs
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')

let PASS = 0, FAIL = 0
const FAILURES = []
const ok = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(label); console.log(`  FAIL ${label}  ${detail}`) }
}
const same = (label, got, want) => ok(label, JSON.stringify(got) === JSON.stringify(want), `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`)

const ME = (modules) => ({
  id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'northperth', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules, status: 'active' },
})
const VARS = [
  { name: 'first_name', desc: 'The recipient\'s first name', to: ['captain', 'players'] },
  { name: 'team_sheet', desc: 'The side with mobiles', to: ['captain'] },
  { name: 'note', desc: 'The selector\'s note', to: ['players'] },
]
const TEMPLATES = [{ id: 't1', name: 'Captain sheet', subject: null }, { id: 't2', name: 'Player welcome', subject: null }]

const run = async () => {
  mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const errors = []
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  async function open(modules, commsAvailable, settings = {}) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } })
    const page = await ctx.newPage()
    page.on('pageerror', (e) => errors.push(e.message))
    const wire = { patch: null, preview: null }
    // What the server has stored: the screen reloads after a save, so a stub that
    // forgot the PATCH would show the old value again.
    const stored = { captain_email_template_id: null, player_email_template_id: null, ...settings }
    // Catch-all FIRST: Playwright matches routes in reverse registration order.
    await page.route('**/api/**', (r) => json(r, {}))
    await page.route('**/api/auth/me', (r) => json(r, ME(modules)))
    await page.route(/\/api\/club-admin\/settings$/, (r) => json(r, { player_name_format: 'first_last' }))
    await page.route(/\/api\/selection-rules$/, (r) => json(r, {
      settings: { age_basis: { basis: 'season_year' }, age_basis_label: 'x', season_start_month: 1, select_show_age: false,
        dormancy_months: 24, default_team_size: 11, show_fees: true, show_training: true, notify_captain_on_confirm: false,
        ...stored },
      rules: [], kinds: [], options: { grades: [], categories: [], formats: [], teams: [] },
    }))
    await page.route(/\/api\/selection-rules\/email-templates$/, (r) => json(r, {
      comms_available: commsAvailable, templates: commsAvailable ? TEMPLATES : [], variables: VARS }))
    await page.route(/\/api\/selection-rules\/email-templates\/preview$/, (r) => {
      wire.preview = JSON.parse(r.request().postData())
      return json(r, { subject: 'Skip: 1st XI v Sample Opponents CC', html: '<html><body><h2>Hello Sam</h2><p>Sample Opponents CC at Main Oval</p></body></html>' })
    })
    await page.route(/\/api\/selection-rules\/settings$/, (r) => {
      wire.patch = JSON.parse(r.request().postData())
      Object.assign(stored, wire.patch)
      return json(r, { age_basis: { basis: 'season_year' }, age_basis_label: 'x', season_start_month: 1, select_show_age: false,
        dormancy_months: 24, default_team_size: 11, show_fees: true, show_training: true, notify_captain_on_confirm: false,
        captain_email_template_id: wire.patch.captain_email_template_id ?? null, player_email_template_id: wire.patch.player_email_template_id ?? null })
    })
    await page.route(/\/api\/club-admin\/comms\/templates$/, (r) => json(r, TEMPLATES))
    await page.route(/\/api\/club-admin\/comms\/merge-variables$/, (r) => json(r, { is_marketing: false, variables: [] }))
    return { page, wire, ctx }
  }

  console.log('\n# Selection rules: link a template')
  {
    const { page, wire, ctx } = await open(['select', 'comms'], true)
    await page.goto(`${BASE}/admin/betterselect/rules`, { waitUntil: 'domcontentloaded' })
    await page.locator('#tpl-captain').waitFor({ timeout: 20000 })
    same('captain picker offers Standard plus the club\'s templates',
      await page.locator('#tpl-captain option').allInnerTexts(), ['Standard wording', 'Captain sheet', 'Player welcome'])
    ok('Save is disabled until something changes', await page.getByRole('button', { name: /^save$/i }).last().isDisabled())
    await page.locator('#tpl-captain').selectOption('t1')
    await page.getByRole('button', { name: 'Preview' }).first().click()
    await page.getByTestId('tpl-preview-captain').waitFor({ timeout: 5000 })
    same('Preview posts the template id and which email', wire.preview, { template_id: 't1', to: 'captain' })
    const frame = page.frameLocator('iframe[title^="Preview of"]')
    ok('...and shows the filled-in email', (await frame.locator('body').innerText()).includes('Sample Opponents CC'))
    ok('...with its subject', (await page.getByTestId('tpl-preview-captain').innerText()).includes('Skip: 1st XI v Sample Opponents CC'))
    ok('...in a sandboxed frame (no scripts)', (await page.locator('iframe[title^="Preview of"]').getAttribute('sandbox')) === '')
    await page.screenshot({ path: join(SHOTS, 'selection_email_templates_1280.png'), fullPage: true })
    await page.getByRole('button', { name: /^save$/i }).last().click()
    await page.waitForTimeout(500)
    same('Save sends exactly the two links (the players\' stays cleared as null)', wire.patch,
      { captain_email_template_id: 't1', player_email_template_id: null })

    await page.locator('#tpl-captain').selectOption({ index: 0 })
    await page.getByRole('button', { name: /^save$/i }).last().click()
    await page.waitForTimeout(500)
    same('Choosing Standard again clears the link (null on the wire, not absent)', wire.patch,
      { captain_email_template_id: null, player_email_template_id: null })

    await page.setViewportSize({ width: 390, height: 900 })
    await page.waitForTimeout(400)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    ok('no horizontal overflow at 390px', overflow <= 0, `overflow ${overflow}px`)
    await page.screenshot({ path: join(SHOTS, 'selection_email_templates_390.png'), fullPage: true })
    await ctx.close()
  }

  console.log('\n# A link to a template that has since been deleted')
  {
    const { page, ctx } = await open(['select', 'comms'], true, { captain_email_template_id: 'gone-id' })
    await page.goto(`${BASE}/admin/betterselect/rules`, { waitUntil: 'domcontentloaded' })
    await page.locator('#tpl-captain').waitFor({ timeout: 20000 })
    ok('says the template is deleted instead of showing a blank',
      (await page.locator('#tpl-captain option:checked').innerText()).includes('deleted'))
    ok('...and offers no Preview for it', (await page.getByRole('button', { name: 'Preview' }).count()) === 0)
    await ctx.close()
  }

  console.log('\n# A club without BetterComms')
  {
    const { page, ctx } = await open(['select'], false)
    await page.goto(`${BASE}/admin/betterselect/rules`, { waitUntil: 'domcontentloaded' })
    await page.getByTestId('templates-no-comms').waitFor({ timeout: 20000 })
    ok('is told templates need BetterComms', (await page.getByTestId('templates-no-comms').innerText()).includes('BetterComms'))
    same('...and gets no pickers', await page.locator('#tpl-captain').count(), 0)
    await ctx.close()
  }

  console.log('\n# Admin > Comms > Templates')
  {
    const { page, ctx } = await open(['select', 'comms'], true)
    await page.route(/\/api\/club-admin\/comms\/templates\/t1$/, (r) => json(r, { id: 't1', name: 'Captain sheet', subject: '', html: '<p>Hi {{first_name}}</p>' }))
    await page.goto(`${BASE}/admin/comms/templates`, { waitUntil: 'domcontentloaded' })
    // The first visit to a Comms screen shows its introduction; skip it as a user would.
    const skip = page.getByRole('button', { name: 'Skip' })
    await skip.waitFor({ timeout: 20000 }).then(() => skip.click()).catch(() => {})
    await page.getByTestId('selection-vars').waitFor({ timeout: 20000 })
    ok('a club (not a Super Admin) can set the subject', (await page.getByPlaceholder('(no subject)').count()) === 1)
    await page.getByTestId('selection-vars').locator('summary').click()
    const chips = await page.getByTestId('selection-vars').locator('button').allInnerTexts()
    same('the selection variables are listed, with who gets each', chips,
      ['{{first_name}}', '{{team_sheet}} (captain)', '{{note}} (players)'])
    await ctx.close()
  }

  same('no page errors', errors, [])
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  if (FAIL) { FAILURES.forEach((f) => console.log('  -', f)); process.exit(1) }
}
run().catch((e) => { console.error(e); process.exit(1) })
