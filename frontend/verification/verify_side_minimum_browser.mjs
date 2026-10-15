// Drives the REAL Selection board and matchday overview in Chromium with the
// API stubbed at the network layer. Asked for: a women's or junior side that
// needs 8 players but may name 12 ("minimum 8, size 12"), instead of using "No
// limit" (no cap, no empty slots, reads as set at zero).
//
//   * the board has a Min box for a fixture that belongs to a team, and none
//     for one that does not
//   * typing a minimum and pressing Enter sends one POST /selection/default-team-size
//     {size, fixture_id, min_size}; clearing it sends min_size null; a size
//     change alone sends NO min_size key
//   * a minimum not below the size is refused on screen and nothing is sent
//   * the pill reads "n / size picked · min m" and stays amber only below the minimum
//   * lowering the size to the minimum or under clears the box
//   * a team that loads with a minimum shows it
//   * the matchday overview: 8 named of "8 to 12" reads set, 7 reads "short of the
//     minimum", and the same 8 with no minimum on a 12 side reads "short of XI"
//   * 390px: no horizontal overflow with the Min box showing
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_side_minimum_browser.mjs
import { chromium } from 'playwright'
import { readFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures/selection_same_day.json'), 'utf8'))
const FID = FIX.fixture_id
const ID = FIX.ids

let PASS = 0, FAIL = 0
const ok = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const ME = {
  id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' },
}
const mkLineup = (n) => Array.from({ length: n }, (_, i) => ({
  player_id: `p${i}`, display_name: `Player ${i}`, batting_order: i + 1, is_captain: i === 0, is_wicket_keeper: i === 1,
  skill_positions: i === 1 ? ['WKT'] : i < 6 ? ['BWL'] : ['BAT'], availability: 'AVAILABLE',
}))

const run = async () => {
  mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const posts = []
  const load = { size: 11, min: null, team: true }
  const overview = { fixtures: [], default_team_size: 11 }
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route(/\/api\/club-admin\/settings$/, (r) => json(r, { player_name_format: 'first_last' }))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route('**/api/selection/overview', (r) => json(r, overview))
  await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { source_fixture_id: null, player_ids: [], captain_id: null, wicket_keeper_id: null }))
  await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
  await page.route(new RegExp(`/api/selection/${FID}/draft(\\?.*)?$`), (r) => json(r, { draft: null, version: 0 }))
  await page.route('**/api/selection/default-team-size', (r) => {
    const b = JSON.parse(r.request().postData())
    posts.push(b)
    return json(r, { status: 'ok', default_team_size: b.size, scope: 'team', min_size: b.min_size ?? null })
  })
  await page.route(new RegExp(`/api/selection/${FID}$`), (r) => json(r, {
    ...FIX.payload, lineup: [], default_team_size: load.size, team_min: load.min,
    fixture: { ...FIX.payload.fixture, team_id: load.team ? FIX.payload.fixture.team_id : null },
  }))

  const body = async () => (await page.locator('body').innerText()).replace(/\s+/g, ' ')
  const open = async () => {
    await page.goto(`${BASE}/admin/betterselect/select/${FID}`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Us vs Opp').first().waitFor({ timeout: 20000 })
    await page.waitForTimeout(300)
  }
  const minBox = () => page.getByLabel('Minimum players for this team').first()
  const pill = () => page.getByText(/picked/).first()
  const pillAmber = async () => (await pill().evaluate((el) => getComputedStyle(el).backgroundColor).catch(() => '')).replace(/\s/g, '')
  const last = () => posts[posts.length - 1]

  await open()
  console.log('\n# the Min box')
  ok('a Min box is on the board for a fixture with a team', (await minBox().count()) > 0)
  await minBox().fill('2').catch(() => {})
  await minBox().press('Enter').catch(() => {})
  await page.waitForTimeout(400)
  ok('Enter sends one POST', posts.length === 1, JSON.stringify(posts))
  ok('it carries size 11, the fixture and min_size 2', last()?.size === 11 && last()?.fixture_id === FID && last()?.min_size === 2, JSON.stringify(last()))
  ok('the pill says "min 2"', /picked · min 2/.test(await body()), (await body()).slice(0, 300))

  console.log('\n# amber only below the minimum')
  const amberNone = await pillAmber()
  await page.getByText('Cara Free').first().click()
  await page.waitForTimeout(250)
  await page.getByText('Alex Backtoback').first().click()
  await page.waitForTimeout(500)
  const amberTwo = await pillAmber()
  ok('0 picked of min 2 is amber', amberNone !== '' && amberNone !== amberTwo, `${amberNone} vs ${amberTwo}`)
  ok('2 picked (the minimum) of 11 is not amber', /2 \/ 11 picked/.test(await body()) && amberTwo !== amberNone, (await body()).slice(0, 200))
  await page.screenshot({ path: join(SHOTS, 'side_minimum_1440.png') })

  console.log('\n# refusals and clearing')
  const n = posts.length
  await minBox().fill('11').catch(() => {})
  await minBox().press('Enter').catch(() => {})
  await page.waitForTimeout(400)
  ok('a minimum equal to the size is refused on screen and not sent', posts.length === n && /lower than the side size/.test(await body()), JSON.stringify(posts.slice(n)))
  await minBox().fill('').catch(() => {})
  await minBox().press('Enter').catch(() => {})
  await page.waitForTimeout(400)
  ok('clearing sends min_size null', posts.length === n + 1 && last()?.min_size === null && 'min_size' in (last() || {}), JSON.stringify(posts.slice(n)))
  ok('the pill drops "min"', !/picked · min/.test(await body()))

  console.log('\n# a size change alone does not touch the minimum')
  await minBox().fill('5').catch(() => {})
  await minBox().press('Enter').catch(() => {})
  await page.waitForTimeout(400)
  const m = posts.length
  await page.getByRole('button', { name: /^12$/ }).first().click({ timeout: 1500 }).catch(() => {})
  await page.waitForTimeout(400)
  ok('picking 12 sends size 12 and NO min_size key', posts.length === m + 1 && last()?.size === 12 && !('min_size' in last()), JSON.stringify(posts.slice(m)))
  ok('the box still reads 5', (await minBox().inputValue().catch(() => '')) === '5')
  await page.getByRole('button', { name: /^Custom/ }).first().click({ timeout: 1500 }).catch(() => {})
  await page.getByLabel(/Custom side size/).first().fill('5').catch(() => {})
  await page.getByLabel(/Custom side size/).first().press('Enter').catch(() => {})
  await page.waitForTimeout(400)
  ok('lowering the size to the minimum clears the box (the server drops it too)', (await minBox().inputValue().catch(() => 'x')) === '', await minBox().inputValue().catch(() => 'x'))

  console.log('\n# a team that loads with a minimum, and a fixture with no team')
  load.size = 12; load.min = 8
  await open()
  ok('the box shows 8 and the pill "min 8"', (await minBox().inputValue().catch(() => '')) === '8' && /\/ 12 picked · min 8/.test(await body()))
  load.team = false; load.min = null
  await open()
  ok('no Min box without a team', (await minBox().count()) === 0)
  load.team = true

  console.log('\n# the matchday overview')
  const fxr = (id, team, size, min, n) => ({
    id, label: 'x', opponent_name: `Opp ${id}`, home_away: 'HOME', played_on: '2099-01-01', start_time: '09:00', round: 1,
    team_name: team, team_sequence: 1, grade_name: 'G', lineup: mkLineup(n), team_size: size, team_min: min, has_draft: false,
  })
  overview.fixtures = [fxr('a', 'Women A', 12, 8, 8), fxr('b', 'Women B', 12, 8, 7), fxr('c', 'Colts', 12, null, 8)]
  await page.goto(`${BASE}/admin/betterselect/selection`, { waitUntil: 'domcontentloaded' })
  await page.getByText('Women A').first().waitFor({ timeout: 20000 })
  await page.waitForTimeout(400)
  const row = (name) => page.locator('div', { hasText: name }).filter({ hasText: /Squad set|Ready to review|In progress|Needs attention/ }).last()
  const textOf = async (name) => (await row(name).innerText().catch(() => '')).replace(/\s+/g, ' ')
  const a = await textOf('Women A'), b = await textOf('Women B'), c = await textOf('Colts')
  ok('8 named of "8 to 12" is not short', !/short of/.test(a) && /8\/8 to 12/.test(a), a.slice(0, 200))
  ok('7 named reads short of the minimum', /1 short of the minimum/.test(b), b.slice(0, 200))
  ok('8 named of a plain 12 still reads short of XI', /4 short of XI/.test(c), c.slice(0, 200))
  await page.screenshot({ path: join(SHOTS, 'side_minimum_overview.png') })

  console.log('\n# 390px')
  await page.setViewportSize({ width: 390, height: 844 })
  await open()
  load.size = 12; load.min = 8
  await open()
  await page.waitForTimeout(300)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
  ok('no horizontal overflow', over <= 0, `over by ${over}`)
  await page.screenshot({ path: join(SHOTS, 'side_minimum_390.png') })
  ok('no page errors', errors.length === 0, errors.join(' | '))

  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
