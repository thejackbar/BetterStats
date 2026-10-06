// Drives the real admin Milestones screen in Chromium with the API stubbed at the
// network layer, for a club choosing its own run and wicket increments.
//
//   npm run build && npx vite preview --port 5198 &
//   node frontend/verification/verify_milestone_scheme_browser.mjs [baseUrl]
//
// Checks the pickers show the saved steps, the exact PUT on the wire for a runs
// change and for a wickets change (one key each, the other left out), that the
// report is read again after a save, that a user without the milestones
// permission sees the pickers disabled, an error from the server is shown, and
// 390px has no sideways scroll.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS_DIR || ''

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  - ${extra}` : ''}`) }
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openPage({ caps = ['manage_milestones'], width = 1440, putStatus = 200 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = [], puts = []
  let reads = 0
  const scheme = { runs_step: 1000, wickets_step: 100 }
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (route, body, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = route.request().method()
    if (path === '/auth/me') {
      return json(route, { id: 'u1', username: 'admin', role: 'club_member', club_id: 'org-1', club_slug: 'testclub',
        capabilities: caps, entitlements: { modules: ['core'] } })
    }
    if (path === '/clubs/testclub') {
      return json(route, { id: 'org-1', slug: 'testclub', name: 'Test Cricket Club', short_name: 'Test CC', is_active: true })
    }
    if (path === '/club-admin/milestones' && method === 'GET') {
      reads++
      return json(route, {
        upcoming: [{ player_id: 'p1', player_name: 'Pat Player', type: 'runs', category: 'batting', current: 740, target: scheme.runs_step === 250 ? 750 : 1000, needed: 10, detail: null }],
        achieved: [],
        scheme: { ...scheme },
        scheme_options: { runs_steps: [250, 500, 1000], wickets_steps: [25, 50, 100] },
      })
    }
    if (path === '/club-admin/milestones/scheme' && method === 'PUT') {
      const body = JSON.parse(route.request().postData() || '{}')
      puts.push(body)
      if (putStatus !== 200) return json(route, { detail: 'Runs step must be one of 250, 500, 1000' }, putStatus)
      Object.assign(scheme, body)
      return json(route, { ...scheme })
    }
    return json(route, {})
  })
  return { page, ctx, errors, puts, reads: () => reads }
}

const pressed = (page, label) =>
  page.getByRole('button', { name: label, exact: true }).first().getAttribute('aria-pressed')

// 1. Default: pickers show 1,000 and 100, a runs change sends one key.
{
  const { page, ctx, errors, puts, reads } = await openPage()
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'load' })
  await page.getByText('Milestones tracked').waitFor({ timeout: 20000 }).catch(() => {})
  ck('the Milestones tracked panel shows', await page.getByText('Milestones tracked').count() === 1)
  const runsGroup = page.locator('div:has(> p:text-is("Runs, every"))').first()
  ck('runs: 1,000 is the selected step', (await runsGroup.getByRole('button', { name: '1,000', exact: true }).getAttribute('aria-pressed')) === 'true')
  ck('runs: 250 and 500 are offered', await runsGroup.getByRole('button', { name: '250', exact: true }).count() === 1 && await runsGroup.getByRole('button', { name: '500', exact: true }).count() === 1)
  ck('runs: the ladder reads 500, 1,000, 2,000, 3,000 for the default',
     (await runsGroup.innerText()).includes('500, 1,000, 2,000, 3,000'), await runsGroup.innerText())
  const wicketsGroup = page.locator('div:has(> p:text-is("Wickets, every"))').first()
  ck('wickets: 100 is selected', (await wicketsGroup.getByRole('button', { name: '100', exact: true }).getAttribute('aria-pressed')) === 'true')
  ck('wickets: the ladder reads 50, 100, 200, 300', (await wicketsGroup.innerText()).includes('50, 100, 200, 300'), await wicketsGroup.innerText())
  ck('before any click: nothing sent and one read', puts.length === 0 && reads() === 1, `puts=${puts.length} reads=${reads()}`)

  if (SHOTS) await page.screenshot({ path: `${SHOTS}/milestones-default.png` })
  await runsGroup.getByRole('button', { name: '250', exact: true }).click()
  await page.waitForFunction(() => document.body.innerText.includes('250, 500, 750, 1,000'), null, { timeout: 8000 }).catch(() => {})
  ck('picking runs 250 sends exactly {runs_step: 250}', puts.length === 1 && JSON.stringify(puts[0]) === '{"runs_step":250}', JSON.stringify(puts))
  ck('the report is read again after the save', reads() >= 2, `reads=${reads()}`)
  ck('runs: 250 is now selected', (await runsGroup.getByRole('button', { name: '250', exact: true }).getAttribute('aria-pressed')) === 'true')
  ck('runs: the ladder reads 250, 500, 750, 1,000', (await runsGroup.innerText()).includes('250, 500, 750, 1,000'), await runsGroup.innerText())
  ck('the list now shows the 750 target from the re-read', (await page.locator('body').innerText()).includes('750 runs'))

  await wicketsGroup.getByRole('button', { name: '25', exact: true }).click()
  await page.waitForFunction(() => document.body.innerText.includes('25, 50, 75, 100'), null, { timeout: 8000 }).catch(() => {})
  ck('picking wickets 25 sends exactly {wickets_step: 25}', puts.length === 2 && JSON.stringify(puts[1]) === '{"wickets_step":25}', JSON.stringify(puts))
  ck('wickets: the ladder reads 25, 50, 75, 100', (await wicketsGroup.innerText()).includes('25, 50, 75, 100'), await wicketsGroup.innerText())
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/milestones-picked.png` })
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// 2. Without the milestones permission the pickers are disabled and say why.
{
  const { page, ctx, puts } = await openPage({ caps: [] })
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'load' })
  await page.getByText('Milestones tracked').waitFor({ timeout: 20000 }).catch(() => {})
  const btn = page.getByRole('button', { name: '250', exact: true }).first()
  ck('no permission: the picker is disabled', await btn.isDisabled())
  ck('no permission: the screen says why', (await page.locator('body').innerText()).includes('You need the Milestones permission'))
  await btn.click({ force: true, timeout: 1500 }).catch(() => {})
  ck('no permission: nothing is sent', puts.length === 0)
  await ctx.close()
}

// 3. A refusal from the server is shown and the picker stays on the saved step.
{
  const { page, ctx } = await openPage({ putStatus: 422 })
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'load' })
  await page.getByText('Milestones tracked').waitFor({ timeout: 20000 }).catch(() => {})
  await page.getByRole('button', { name: '500', exact: true }).first().click()
  await page.getByText(/must be one of/).waitFor({ timeout: 5000 }).catch(() => {})
  ck('a refusal is shown on screen', (await page.locator('body').innerText()).includes('must be one of'))
  ck('…and the saved step stays selected', (await page.getByRole('button', { name: '1,000', exact: true }).first().getAttribute('aria-pressed')) === 'true')
  await ctx.close()
}

// 4. 390px: no sideways scroll.
{
  const { page, ctx } = await openPage({ width: 390 })
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'load' })
  await page.getByText('Milestones tracked').waitFor({ timeout: 20000 }).catch(() => {})
  ck('390px: the panel shows', await page.getByText('Milestones tracked').count() === 1)
  ck('390px: no sideways scroll', await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/milestones-390.png` })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
