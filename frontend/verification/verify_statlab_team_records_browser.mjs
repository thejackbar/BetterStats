// Drives the real StatLab screen in Chromium with the API stubbed at the network
// layer (the schema is the SHIPPED one, in fixtures/statlab_schema.json).
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_statlab_team_records_browser.mjs [baseUrl]
//
// The ask: team records such as Biggest Team Chases. Checks the presets are offered
// on the Team innings and Match list tabs, that picking one sends the exact request
// (target, sort, and the is_chase / is_defended filters), and that the Team innings
// table names the team, the opposition and the target instead of a blank NAME column.
import { existsSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SCHEMA = JSON.parse(readFileSync(new URL('./fixtures/statlab_schema.json', import.meta.url)))

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const CLUB = {
  id: 'org-1', name: 'Our Club', slug: 'our-club', short_name: 'OCC',
  is_active: true, primary_color: '#1b8f4d', accent_color: '#1b8f4d',
  theme_config: {}, font_config: {}, logo_url: null, modules: [],
}
const CHASE_ROW = {
  game_id: 'g-1', batting_team: 'Our Club 1st XI', against: 'Bayswater', grade_name: '1st Grade',
  played_at: '2025-11-08', result: 'won', innings_number: 2, runs: 251, wickets: 4, extras: 6, target: 251,
  is_chase: 1, is_defended: 0, won: 1, is_ours: 1,
}
const MATCH_ROW = {
  game_id: 'g-2', opposition: 'Bayswater', grade_name: '1st Grade', played_at: '2025-11-08', result: 'won',
  team_runs: 251, team_wickets: 4, opp_runs: 250, opp_wickets: 8, margin_runs: 1, match_runs: 501,
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const errors = []
page.on('pageerror', e => errors.push(String(e)))
const calls = []
await page.route('**/api/**', async (route) => {
  const url = new URL(route.request().url())
  const p = url.pathname.replace(/^\/api/, '')
  const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  if (/^\/auth\/me/.test(p)) return route.fulfill({ status: 401, body: '{}' })
  if (/^\/clubs\/our-club$/.test(p)) return json(CLUB)
  if (/^\/statlab\/schema/.test(p)) return json(SCHEMA)
  if (/^\/statlab\/reports/.test(p)) return json([])
  if (/^\/statlab\/query/.test(p)) {
    calls.push(Object.fromEntries([...url.searchParams.entries()]))
    const t = url.searchParams.get('target')
    return json({ rows: t === 'match_list' ? [MATCH_ROW] : t === 'team_innings_list' ? [CHASE_ROW] : [], page: 1, has_more: false })
  }
  if (/\/seasons$/.test(p)) return json([{ id: 's-1', name: 'Summer 2025/26', year: 2025 }])
  if (/grade-categories/.test(p)) return json({ available: ['senior'], default: ['senior'], available_formats: [] })
  if (/families|grades|^\/players$/.test(p)) return json([])
  return json({})
})

// Reads of what this change ADDS report absence instead of throwing, so a control run
// against the old build says which checks fail.
const textOf = async (loc) => (await loc.count()) ? (await loc.first().innerText()) : ''
const lastCall = () => calls[calls.length - 1] || {}
const treeOf = (c) => { try { return JSON.stringify(JSON.parse(c.filter_tree || '{}')) } catch { return c.filter_tree || '' } }

await page.goto(`${BASE}/our-club/statlab`)
await page.getByText('PLAYER CAREER', { exact: true }).first().waitFor({ timeout: 20000 })

await page.getByText('TEAM INNINGS', { exact: true }).first().click()
await page.waitForTimeout(500)
const guide = page.getByTestId('statlab-target-guide')
const guideText = await textOf(guide)
for (const label of ['Biggest successful chases', 'Biggest chases against us', 'Lowest totals we defended']) {
  ck(`Team innings leads with "${label}"`, guideText.includes(label))
}

const chase = guide.getByText('Biggest successful chases', { exact: true }).first()
if (await chase.count()) await chase.click()
await page.waitForTimeout(500)
let c = lastCall()
ck('chases: runs the Team innings table', c.target === 'team_innings_list', JSON.stringify(c))
ck('chases: sorted by target, biggest first', c.sort_by === 'target' && c.sort_dir === 'desc', `${c.sort_by} ${c.sort_dir}`)
ck('chases: asks for our innings that were chases',
  /is_ours/.test(treeOf(c)) && /is_chase/.test(treeOf(c)), treeOf(c))
const main = await textOf(page.locator('main'))
ck('the table has a TEAM column with the batting side', /TEAM/.test(main) && main.includes('Our Club 1st XI'), main.slice(0, 200))
ck('the table has a VS column with the opposition', /\bVS\b/.test(main) && main.includes('Bayswater'))
ck('the target is shown', /TARGET/i.test(main) && main.includes('251'))
ck('the old blank NAME column is gone', !/\bNAME\b/.test(main))

const against = guide.getByText('Biggest chases against us', { exact: true }).first()
if (await against.count()) await against.click()
await page.waitForTimeout(500)
c = lastCall()
ck('against us: is_ours is 0 and is_chase is 1 on the wire',
  /"value":"0"/.test(treeOf(c)) && /is_chase/.test(treeOf(c)), treeOf(c))

const defended = guide.getByText('Lowest totals we defended', { exact: true }).first()
if (await defended.count()) await defended.click()
await page.waitForTimeout(500)
c = lastCall()
ck('defended: smallest first and filtered to defended totals',
  c.sort_by === 'runs' && c.sort_dir === 'asc' && /is_defended/.test(treeOf(c)), `${c.sort_by} ${c.sort_dir} ${treeOf(c)}`)

// The rest are in the REPORTS list on the left, under Match.
const matchGroup = page.locator('button', { hasText: /^\s*MATCH\s*\d+/ }).first()
ck('the Match group is in the REPORTS list', await matchGroup.count() === 1)
if (await matchGroup.count()) await matchGroup.click()
for (const [label, expect] of [
  ['Lowest totals defended against us', { sort_by: 'runs', sort_dir: 'asc', field: 'is_defended', result: null }],
  ['Highest totals in a loss', { sort_by: 'runs', sort_dir: 'desc', field: 'is_ours', result: 'lost' }],
  ['Lowest totals in a win', { sort_by: 'runs', sort_dir: 'asc', field: 'is_ours', result: 'won' }],
  ['Biggest wins (Runs)', { sort_by: 'won_by_runs', sort_dir: 'desc', field: 'won_by_runs', result: null, ours: '1' }],
  ['Biggest wins (Wickets)', { sort_by: 'won_by_wickets', sort_dir: 'desc', field: 'won_by_wickets', result: null, ours: '1' }],
  ['Biggest defeats (Runs)', { sort_by: 'won_by_runs', sort_dir: 'desc', field: 'won_by_runs', result: null, ours: '0' }],
  ['Biggest defeats (Wickets)', { sort_by: 'won_by_wickets', sort_dir: 'desc', field: 'won_by_wickets', result: null, ours: '0' }],
  ['Closest wins (Runs)', { sort_by: 'won_by_runs', sort_dir: 'asc', field: 'won_by_runs', result: null }],
  ['Closest wins (Wickets)', { sort_by: 'won_by_wickets', sort_dir: 'asc', field: 'won_by_wickets', result: null }],
]) {
  const link = page.locator('button', { hasText: label }).first()
  ck(`REPORTS lists "${label}"`, await link.count() > 0)
  if (await link.count()) await link.click()
  await page.waitForTimeout(400)
  const k = lastCall()
  ck(`${label}: sorted ${expect.sort_by} ${expect.sort_dir} and filtered on ${expect.field}`,
    k.target === 'team_innings_list' && k.sort_by === expect.sort_by && k.sort_dir === expect.sort_dir
    && treeOf(k).includes(expect.field), `${k.sort_by} ${k.sort_dir} ${treeOf(k)}`)
  if (expect.ours) {
    ck(`${label}: is_ours is ${expect.ours} on the wire`,
      treeOf(k).includes(`"field":"is_ours","op":"eq","value":"${expect.ours}"`), treeOf(k))
  }
  if (expect.result) {
    ck(`${label}: our result (${expect.result}) goes on the wire`,
      k.result === expect.result || (k.results || '').includes(expect.result), JSON.stringify(k))
  }
}

// The old single "Closest wins" (whole-match run difference, which counts a chase as a run margin) is gone.
{
  const labels = await page.locator('button').allInnerTexts()
  ck('no preset is still called just "Closest wins"', !labels.some(t => /^\s*·?\s*Closest wins\s*$/.test(t)))
  ck('nor "Biggest winning margins" or plain "Biggest defeats"',
    !labels.some(t => /^\s*·?\s*(Biggest winning margins|Biggest defeats)\s*$/.test(t)))
}

await page.getByText('MATCH LIST', { exact: true }).first().click()
await page.waitForTimeout(500)
const mguide = await textOf(page.getByTestId('statlab-target-guide'))
ck('Match list offers the highest-scoring matches (both sides)', (await page.locator('button', { hasText: 'Highest-scoring matches (both sides)' }).count()) > 0)
const hs = page.locator('button', { hasText: 'Highest-scoring matches (both sides)' }).first()
if (await hs.count()) await hs.click()
await page.waitForTimeout(500)
c = lastCall()
ck('match runs: sorted by match_runs', c.target === 'match_list' && c.sort_by === 'match_runs', JSON.stringify(c))
ck('match runs: the column is shown', /MATCH/i.test(await textOf(page.locator('main'))) && (await textOf(page.locator('main'))).includes('501'))

// ── a row opens the scorecard of its match ────────────────────────────────
const mrow = page.locator('tr[data-game-id="g-2"]')
ck('a Match list row is a click-through to its match', await mrow.count() === 1)
if (await mrow.count()) await mrow.first().click()
await page.waitForTimeout(400)
ck('clicking a Match list row opens /games/<its game id>', new URL(page.url()).pathname === '/games/g-2', page.url())

await page.goto(`${BASE}/our-club/statlab`)
await page.getByText('TEAM INNINGS', { exact: true }).first().click()
await page.waitForTimeout(400)
await page.getByTestId('statlab-target-guide').getByText('Biggest successful chases', { exact: true }).first().click()
await page.waitForTimeout(500)
const trow = page.locator('tr[data-game-id="g-1"]')
ck('a Team innings row is a click-through to its match', await trow.count() === 1)
ck('the row says so on hover', (await trow.first().getAttribute('title')) === 'Open the scorecard')
if (await trow.count()) { await trow.first().focus(); await page.keyboard.press('Enter') }
await page.waitForTimeout(400)
ck('Enter on a Team innings row opens /games/<its game id>', new URL(page.url()).pathname === '/games/g-1', page.url())

await page.goto(`${BASE}/our-club/statlab`)
await page.getByText('PLAYER CAREER', { exact: true }).first().waitFor()
ck('a player table row is not made a click-through', await page.locator('tr[data-game-id]').count() === 0)

await page.setViewportSize({ width: 390, height: 900 })
await page.waitForTimeout(300)
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
ck('no horizontal overflow at 390px', overflow <= 0, String(overflow))
await page.screenshot({ path: process.env.SHOT || '/tmp/statlab_team_records_390.png', fullPage: false })
ck('no page errors', errors.length === 0, errors.join(' | '))

console.log(`\n${pass} passed, ${fail} failed`)
await browser.close()
process.exit(fail ? 1 : 0)
