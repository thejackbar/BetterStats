// Drives the real admin Milestones screen in Chromium with the API stubbed at the
// network layer, for a club choosing its own increments: presets or a step it
// types, club-wide and for one grade at a time.
//
//   npx vite build --outDir /tmp/ms-dist && npx vite preview --outDir /tmp/ms-dist --port 5198 &
//   node frontend/verification/verify_milestone_scheme_browser.mjs [baseUrl]
//
// Checks the pickers show the saved steps, the exact PUT on the wire for a runs
// change and for a wickets change (one key each, the other left out), a typed
// step (turned back on screen when it breaks the rule, sent when it does not),
// the per-grade card (one grade, one stat, the exact body, null for "follow the
// club", older grades behind a toggle), that the report is read again after a
// save, that a user without the milestones permission sees everything disabled,
// an error from the server is shown, and 390px has no sideways scroll.
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

// A block that throws (an element the screen does not have, which is what the
// previous screen does for the new controls) is a failure, not a crash, so a run
// against the previous build reports what is missing instead of dying.
async function block(fn) {
  try { await fn() } catch (e) { fail++; console.log(`FAIL block threw: ${String(e.message).split('\n')[0]}`) }
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openPage({ caps = ['manage_milestones'], width = 1440, putStatus = 200 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(6000)
  const errors = [], puts = []
  let reads = 0
  const gradePuts = []
  const scheme = { runs_step: 1000, wickets_step: 100, matches_step: 50, catches_step: 50 }
  const none = () => ({ runs: null, wickets: null, matches: null, catches: null })
  const grades = [
    { key: 'a grade', name: 'A Grade', last_year: 2026, active: true, steps: none() },
    { key: 'b grade', name: 'B Grade', last_year: 2026, active: true, steps: none() },
    { key: 'old grade', name: 'Old Grade', last_year: 2019, active: false, steps: none() },
  ]
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
        scheme_options: { runs_steps: [250, 500, 1000], wickets_steps: [25, 50, 100], matches_steps: [25, 50, 100], catches_steps: [25, 50, 100] },
        step_limits: {
          runs: { min: 100, max: 10000, multiple: 25 }, wickets: { min: 10, max: 1000, multiple: 5 },
          matches: { min: 10, max: 500, multiple: 5 }, catches: { min: 10, max: 500, multiple: 5 },
        },
        grade_schemes: grades.map(g => ({ ...g, steps: { ...g.steps } })),
      })
    }
    if (path === '/club-admin/milestones/scheme' && method === 'PUT') {
      const body = JSON.parse(route.request().postData() || '{}')
      puts.push(body)
      if (putStatus !== 200) return json(route, { detail: 'Runs step must be between 100 and 10,000' }, putStatus)
      Object.assign(scheme, body)
      return json(route, { ...scheme })
    }
    if (path === '/club-admin/milestones/grade-schemes' && method === 'PUT') {
      const body = JSON.parse(route.request().postData() || '{}')
      gradePuts.push(body)
      if (putStatus !== 200) return json(route, { detail: 'Matches step must be a multiple of 5' }, putStatus)
      const g = grades.find(x => x.name === body.grade)
      for (const stat of ['runs', 'wickets', 'matches', 'catches']) {
        if (`${stat}_step` in body) g.steps[stat] = body[`${stat}_step`]
      }
      return json(route, { key: g.key, name: g.name, steps: { ...g.steps } })
    }
    return json(route, {})
  })
  return { page, ctx, errors, puts, gradePuts, reads: () => reads }
}

const pressed = (page, label) =>
  page.getByRole('button', { name: label, exact: true }).first().getAttribute('aria-pressed')

// 1. Default: pickers show 1,000 and 100, a runs change sends one key.
await block(async () => {
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
})

// 2. Without the milestones permission the pickers are disabled and say why.
await block(async () => {
  const { page, ctx, puts } = await openPage({ caps: [] })
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'load' })
  await page.getByText('Milestones tracked').waitFor({ timeout: 20000 }).catch(() => {})
  const btn = page.getByRole('button', { name: '250', exact: true }).first()
  ck('no permission: the picker is disabled', await btn.isDisabled())
  ck('no permission: the screen says why', (await page.locator('body').innerText()).includes('You need the Milestones permission'))
  await btn.click({ force: true, timeout: 1500 }).catch(() => {})
  ck('no permission: nothing is sent', puts.length === 0)
  ck('no permission: the grade boxes are disabled too', await page.getByLabel('A Grade matches increment').isDisabled())
  ck('no permission: the CUSTOM button is disabled', await page.getByRole('button', { name: 'CUSTOM', exact: true }).first().isDisabled())
  await ctx.close()
})

// 3. A refusal from the server is shown and the picker stays on the saved step.
await block(async () => {
  const { page, ctx } = await openPage({ putStatus: 422 })
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'load' })
  await page.getByText('Milestones tracked').waitFor({ timeout: 20000 }).catch(() => {})
  await page.getByRole('button', { name: '500', exact: true }).first().click()
  await page.getByText(/must be between/).waitFor({ timeout: 5000 }).catch(() => {})
  ck('a refusal is shown on screen', (await page.locator('body').innerText()).includes('must be between'))
  ck('…and the saved step stays selected', (await page.getByRole('button', { name: '1,000', exact: true }).first().getAttribute('aria-pressed')) === 'true')
  await ctx.close()
})

// 4. 390px: no sideways scroll.
await block(async () => {
  const { page, ctx } = await openPage({ width: 390 })
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'load' })
  await page.getByText('Milestones tracked').waitFor({ timeout: 20000 }).catch(() => {})
  ck('390px: the panel shows', await page.getByText('Milestones tracked').count() === 1)
  ck('390px: no sideways scroll', await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/milestones-390.png` })
  await ctx.close()
})

// 5. A typed club-wide step: turned back on screen when it breaks the rule,
//    sent as one key when it does not, and shown as the Custom choice.
await block(async () => {
  const { page, ctx, errors, puts } = await openPage()
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'load' })
  await page.getByText('Milestones tracked').waitFor({ timeout: 20000 }).catch(() => {})
  const runsGroup = page.locator('div:has(> p:text-is("Runs, every"))').first()
  ck('custom: no input until CUSTOM is pressed', await runsGroup.getByLabel('custom runs step').count() === 0)
  await runsGroup.getByRole('button', { name: 'CUSTOM', exact: true }).click()
  const input = runsGroup.getByLabel('custom runs step')
  ck('custom: pressing CUSTOM opens the input and sends nothing', await input.count() === 1 && puts.length === 0)
  ck('custom: the limits are shown', (await runsGroup.innerText()).includes('100 to 10,000, in multiples of 25'), await runsGroup.innerText())
  await input.fill('130')
  await runsGroup.getByRole('button', { name: 'SET', exact: true }).click()
  ck('custom: 130 is turned back on screen and nothing is sent',
     (await runsGroup.innerText()).includes('multiple of 25') && puts.length === 0, await runsGroup.innerText())
  await input.fill('50')
  await input.press('Enter')
  ck('custom: 50 is below the smallest and nothing is sent',
     (await runsGroup.innerText()).includes('between 100 and 10,000') && puts.length === 0)
  await input.fill('300')
  await input.press('Enter')
  await page.waitForFunction(() => document.body.innerText.includes('300, 600, 900, 1,200'), null, { timeout: 8000 }).catch(() => {})
  ck('custom: 300 sends exactly {runs_step: 300}', puts.length === 1 && JSON.stringify(puts[0]) === '{"runs_step":300}', JSON.stringify(puts))
  ck('custom: the ladder reads 300, 600, 900, 1,200', (await runsGroup.innerText()).includes('300, 600, 900, 1,200'), await runsGroup.innerText())
  ck('custom: CUSTOM is the pressed choice and no preset is',
     (await runsGroup.getByRole('button', { name: 'CUSTOM', exact: true }).getAttribute('aria-pressed')) === 'true'
     && (await runsGroup.getByRole('button', { name: '1,000', exact: true }).getAttribute('aria-pressed')) === 'false')
  ck('custom: the input holds the saved 300', (await runsGroup.getByLabel('custom runs step').inputValue()) === '300')
  await runsGroup.getByRole('button', { name: '500', exact: true }).click()
  await page.waitForFunction(() => document.body.innerText.includes('500, 1,000, 1,500, 2,000'), null, { timeout: 8000 }).catch(() => {})
  ck('custom: going back to a preset sends exactly {runs_step: 500}', puts.length === 2 && JSON.stringify(puts[1]) === '{"runs_step":500}', JSON.stringify(puts))
  ck('custom: the input is gone and 500 is pressed',
     await runsGroup.getByLabel('custom runs step').count() === 0
     && (await runsGroup.getByRole('button', { name: '500', exact: true }).getAttribute('aria-pressed')) === 'true')
  const matchesGroup = page.locator('div:has(> p:text-is("Matches, every"))').first()
  ck('the club card now offers matches and catches too',
     await matchesGroup.count() === 1 && await page.locator('div:has(> p:text-is("Catches, every"))').count() > 0)
  ck('matches: the ladder reads 50, 100, 150, 200 on the default', (await matchesGroup.innerText()).includes('50, 100, 150, 200'), await matchesGroup.innerText())
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
})

// 6. One grade's own increments.
await block(async () => {
  const { page, ctx, errors, puts, gradePuts, reads } = await openPage()
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'load' })
  await page.getByText('Milestones by grade').waitFor({ timeout: 20000 }).catch(() => {})
  ck('the grade card shows', await page.getByText('Milestones by grade').count() === 1)
  const card = page.locator('div.pb-card', { has: page.locator('p:text-is("Milestones by grade")') })
  const body = await card.innerText()
  ck('A Grade and B Grade are listed', body.includes('A Grade') && body.includes('B Grade'))
  ck('a grade out of play is hidden behind a toggle', !body.includes('Old Grade') && body.includes('SHOW 1 OLDER GRADE'), body)
  const aMatches = page.getByLabel('A Grade matches increment')
  ck('every box starts on the club setting, with the club figure in the text',
     (await aMatches.inputValue()) === '' && (await aMatches.locator('option').first().innerText()).includes('Club (50)'),
     await aMatches.locator('option').first().innerText())
  ck('presets are Every 25, 50 and 100 and there is a Custom choice',
     (await aMatches.locator('option').allInnerTexts()).join('|') === 'Club (50)|Every 25|Every 50|Every 100|Custom…',
     (await aMatches.locator('option').allInnerTexts()).join('|'))
  ck('nothing sent yet', gradePuts.length === 0 && puts.length === 0)

  const readsBefore = reads()
  await aMatches.selectOption('25')
  await page.waitForFunction(() => document.querySelector('select[aria-label="A Grade matches increment"]')?.value === '25', null, { timeout: 8000 }).catch(() => {})
  ck('A Grade matches every 25 sends exactly {grade, matches_step}',
     gradePuts.length === 1 && JSON.stringify(gradePuts[0]) === '{"grade":"A Grade","matches_step":25}', JSON.stringify(gradePuts))
  ck('…and it is not a club-wide save', puts.length === 0)
  ck('the report is read again', reads() > readsBefore, `reads=${reads()}`)
  ck('the box shows the saved 25', (await aMatches.inputValue()) === '25')
  ck('B Grade is untouched', (await page.getByLabel('B Grade matches increment').inputValue()) === '')

  const bRuns = page.getByLabel('B Grade runs increment')
  await bRuns.selectOption('custom')
  ck('Custom opens an input for that grade and sends nothing',
     await page.getByLabel('B Grade custom runs step').count() === 1 && gradePuts.length === 1)
  await page.getByLabel('B Grade custom runs step').fill('130')
  await page.getByLabel('B Grade custom runs step').press('Enter')
  ck('a step that breaks the rule is turned back and nothing is sent',
     (await card.innerText()).includes('multiple of 25') && gradePuts.length === 1)
  await page.getByLabel('B Grade custom runs step').fill('150')
  await page.getByLabel('B Grade custom runs step').press('Enter')
  await page.waitForFunction(() => document.querySelector('input[aria-label="B Grade custom runs step"]')?.value === '150', null, { timeout: 8000 }).catch(() => {})
  ck('B Grade runs 150 sends exactly {grade, runs_step: 150}',
     gradePuts.length === 2 && JSON.stringify(gradePuts[1]) === '{"grade":"B Grade","runs_step":150}', JSON.stringify(gradePuts))
  ck('…and the box reads Custom with 150', (await bRuns.inputValue()) === 'custom'
     && (await page.getByLabel('B Grade custom runs step').inputValue()) === '150')

  await aMatches.selectOption('')
  await page.waitForFunction(() => document.querySelector('select[aria-label="A Grade matches increment"]')?.value === '', null, { timeout: 8000 }).catch(() => {})
  ck('choosing Club sends null, so it follows the club again',
     gradePuts.length === 3 && JSON.stringify(gradePuts[2]) === '{"grade":"A Grade","matches_step":null}', JSON.stringify(gradePuts))

  await page.getByRole('button', { name: /SHOW 1 OLDER GRADE/ }).click()
  ck('the toggle brings the older grade in', (await card.innerText()).includes('Old Grade'))
  ck('…and offers to hide it again', await page.getByRole('button', { name: 'HIDE OLDER GRADES' }).count() === 1)
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/milestones-grades.png`, fullPage: true })
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
})

// 7. The server's refusal for a grade is shown.
await block(async () => {
  const { page, ctx } = await openPage({ putStatus: 422 })
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'load' })
  await page.getByText('Milestones by grade').waitFor({ timeout: 20000 }).catch(() => {})
  await page.getByLabel('A Grade matches increment').selectOption('25')
  await page.getByText(/multiple of 5/).waitFor({ timeout: 5000 }).catch(() => {})
  ck('a grade refusal is shown on screen', (await page.locator('body').innerText()).includes('Matches step must be a multiple of 5'))
  ck('…and the box goes back to what was saved', (await page.getByLabel('A Grade matches increment').inputValue()) === '')
  await ctx.close()
})

// 8. 390px with the grade card and a custom input open.
await block(async () => {
  const { page, ctx } = await openPage({ width: 390 })
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'load' })
  await page.getByText('Milestones by grade').waitFor({ timeout: 20000 }).catch(() => {})
  await page.getByLabel('A Grade runs increment').selectOption('custom')
  await page.getByRole('button', { name: 'CUSTOM', exact: true }).first().click()
  ck('390px: the grade card shows', await page.getByText('Milestones by grade').count() === 1)
  ck('390px: no sideways scroll with custom inputs open',
     await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1),
     await page.evaluate(() => `${document.documentElement.scrollWidth} vs ${document.documentElement.clientWidth}`))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/milestones-grades-390.png`, fullPage: true })
  await ctx.close()
})

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
