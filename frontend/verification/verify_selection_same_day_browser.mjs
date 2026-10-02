// Drives the REAL Selection board in Chromium with the API stubbed at the
// network layer. The payload is a real `assemble_selection` dump
// (fixtures/selection_same_day.json) for a Colts game at 9:00am on a day when:
//   Alex  is also in T20 Div 1 at 6:00pm  -> playable, flagged "Also in", pickable
//   Bob   is also in the 1st Grade (no time) -> real clash, refused
//   Cara  is in nothing                   -> plain
//
//   npx vite preview --port 5199 &   then   node verify_selection_same_day_browser.mjs
import { chromium } from 'playwright'
import { readFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures/selection_same_day.json'), 'utf8'))

let PASS = 0, FAIL = 0
const FAILURES = []
function check(label, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (ok) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(label); console.log(`  FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`) }
}

// Boolean check with a detail string shown on failure.
const ok = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(label); console.log(`  FAIL ${label}  ${detail}`) }
}

// Daniel last played four years ago: outside the board's default "Played <= 3 yrs".
const fourYearsAgo = new Date(); fourYearsAgo.setFullYear(fourYearsAgo.getFullYear() - 4)
const cara = FIX.payload.pool.find((p) => p.display_name === 'Cara Free')
FIX.payload.pool.push({ ...cara, id: 'd4e5f6a7-0000-4000-8000-000000000001', display_name: 'Daniel Newman', last_played: fourYearsAgo.toISOString().slice(0, 10) })

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
  page.on('dialog', (d) => d.accept())

  const wire = { put: null }
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  // Catch-all FIRST: Playwright matches routes in reverse registration order.
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route('**/api/selection/overview', (r) => json(r, { fixtures: [] }))
  await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { source_fixture_id: null, player_ids: [], captain_id: null, wicket_keeper_id: null }))
  await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
  await page.route(new RegExp(`/api/selection/${FIX.fixture_id}$`), async (r) => {
    if (r.request().method() === 'PUT') {
      wire.put = JSON.parse(r.request().postData())
      return json(r, { status: 'ok', count: wire.put.players.length })
    }
    return json(r, FIX.payload)
  })

  await page.goto(`${BASE}/admin/betterselect/select/${FIX.fixture_id}`, { waitUntil: 'domcontentloaded' })
  await page.getByText('Alex Backtoback').first().waitFor({ timeout: 20000 })
  await page.waitForTimeout(400)

  const card = (name) => page.locator('div.group.relative.rounded-xl', { hasText: name }).first()
  const cardText = async (name) => (await card(name).innerText()).replace(/\s+/g, ' ')

  console.log('\n# the flag')
  const alex = await cardText('Alex Backtoback')
  ok('Alex shows "Also in T20 Div 1 6:00pm"', /Also in T20 Div 1 6:00pm/.test(alex), alex)
  ok('Alex is not shown as picked elsewhere', !/Picked for/.test(alex), alex)
  const bob = await cardText('Bob Blocked')
  ok('Bob (real clash) is shown as picked for the 1st Grade', /Picked for 1st Grade/.test(bob), bob)
  const cara = await cardText('Cara Free')
  ok('Cara has no flag', !/Also in|Picked for/.test(cara), cara)
  check('Alex card is not greyed out', !(await card('Alex Backtoback').getAttribute('class')).includes('opacity-50'))
  check('Bob card IS greyed out', (await card('Bob Blocked').getAttribute('class')).includes('opacity-50'))
  await page.screenshot({ path: join(SHOTS, 'selection_same_day_1440.png') })

  console.log('\n# search reaches past the recency window')
  const bodyText = async () => (await page.locator('body').innerText())
  ok('Daniel (last played 4 years ago) is not in the default browse list', !(await bodyText()).includes('Daniel Newman'))
  const search = page.getByPlaceholder(/search players/i)
  await search.fill('Newman')
  await page.waitForTimeout(300)
  ok('searching "Newman" finds Daniel', (await bodyText()).includes('Daniel Newman'))
  await search.fill('')
  await page.waitForTimeout(300)
  ok('clearing the search hides him again', !(await bodyText()).includes('Daniel Newman'))

  console.log('\n# picking')
  await card('Bob Blocked').click()
  await page.waitForTimeout(300)
  await card('Alex Backtoback').click()
  await page.waitForTimeout(300)
  const toastText = (await page.locator('body').innerText()).replace(/\s+/g, ' ')
  check('tapping Alex says he is also in T20 Div 1 and is added to both', /Alex Backtoback is also in T20 Div 1 6:00pm.*Adding to both/.test(toastText))
  await page.screenshot({ path: join(SHOTS, 'selection_same_day_after_alex.png') })
  await card('Cara Free').click()
  await page.waitForTimeout(300)

  await page.screenshot({ path: join(SHOTS, 'selection_same_day_before_save.png') })
  console.log('\n# save (the exact request)')
  await page.getByRole("button", { name: /^confirm/i }).first().click()
  await page.waitForTimeout(800)
  const ids = (wire.put?.players || []).map((p) => p.player_id)
  await page.screenshot({ path: join(SHOTS, 'selection_same_day_after_save.png') })
  console.log('   PUT players:', JSON.stringify(ids), 'ids:', JSON.stringify(FIX.ids))
  ok('PUT carries Alex', ids.includes(FIX.ids['Alex Backtoback']), JSON.stringify(ids))
  ok('PUT carries Cara', ids.includes(FIX.ids['Cara Free']), JSON.stringify(ids))
  ok('PUT does NOT carry Bob', !ids.includes(FIX.ids['Bob Blocked']), JSON.stringify(ids))
  check('no demotions are sent for a back to back pick', (wire.put?.demotions || []).length, 0)

  console.log('\n# 390px')
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(400)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ok('no horizontal page overflow at 390px', overflow <= 0, `overflow ${overflow}px`)
  await page.screenshot({ path: join(SHOTS, 'selection_same_day_390.png') })

  check('no page errors', errors, [])
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  if (FAIL) { FAILURES.forEach((f) => console.log('  -', f)); process.exit(1) }
}
run().catch((e) => { console.error(e); process.exit(1) })
