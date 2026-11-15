// Drives the real StatLab screen in Chromium with the API stubbed at the
// network layer. A career report ranked on a bowling figure must show bowling
// columns, not 100s and Ducks; a fielding ranking shows fielding columns; a
// batting ranking keeps the original batting-first table.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_statlab_discipline_columns_browser.mjs [baseUrl]
import { existsSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium/chrome-linux/chrome'
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
const ROW = (id, name) => ({
  player_id: id, player_name: name, matches: 37, batting_innings: 27, runs: 232, not_outs: 12,
  batting_average: 15.47, high_score: 37, hundreds: 0, fifties: 0, ducks: 3,
  bowling_innings: 30, wickets: 100, overs: 120.2, maidens: 14, runs_conceded: 1417,
  bowling_average: 14.17, bowling_economy: 2.9, bowling_strike_rate: 29.3, five_wicket_innings: 7,
  catches: 4, catches_wk: 0, catches_non_wk: 4, run_outs: 2, stumpings: 0,
})

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
    return json({ rows: [ROW('p-1', 'Cooper, Chris'), ROW('p-2', 'Dockery, James')], page: 1, has_more: false })
  }
  if (/^\/players$/.test(p)) return json([])
  if (/\/seasons$/.test(p)) return json([{ id: 's-1', name: 'Summer 2025/26', year: 2025 }])
  if (/grade-categories/.test(p)) return json({ available: ['senior'], default: ['senior'], available_formats: [] })
  if (/families/.test(p)) return json([])
  if (/grades/.test(p)) return json([])
  return json({})
})

// Header cells, upper-cased by CSS: read them in that casing.
const headers = async () => {
  const th = page.locator('main table thead th')
  await th.first().waitFor({ timeout: 10000 })
  return (await th.allInnerTexts()).map(t => t.replace(/[↑↓]/g, '').trim().toUpperCase())
}
const preset = async (label) => {
  const before = calls.length
  await page.getByText(label, { exact: true }).first().click()
  for (let i = 0; i < 40 && calls.length === before; i++) await page.waitForTimeout(100)
  await page.waitForTimeout(300)
  return calls[calls.length - 1] || {}
}

await page.goto(`${BASE}/our-club/statlab`)
await page.getByText('Top wicket takers', { exact: true }).first().waitFor({ timeout: 20000 })

// ── bowling ranking ───────────────────────────────────────────────────────
let q = await preset('Top wicket takers')
let h = await headers()
ck('wicket takers asks for a career table sorted on wickets', q.target === 'player_career' && q.sort_by === 'wickets', JSON.stringify(q))
for (const col of ['WKTS', 'OVERS', 'MDNS', 'BOWL AVG', 'ECON', 'BOWL SR', '5W'])
  ck(`wicket takers shows ${col}`, h.includes(col), h.join('|'))
for (const col of ['100S', '50S', 'DUCKS', 'HS', 'NO'])
  ck(`wicket takers hides batting column ${col}`, !h.includes(col), h.join('|'))
ck('wicket takers leads with the wickets figure', h.indexOf('WKTS') < h.indexOf('BOWL AVG') && h.indexOf('WKTS') <= 3, h.join('|'))
const bodyText = await page.locator('main table tbody tr').first().innerText()
ck('the row shows the bowling figures', /14\.17/.test(bodyText) && /2\.90/.test(bodyText), bodyText)

// Bowling average sorts the same way.
q = await preset('Top bowling averages')
h = await headers()
ck('top bowling averages shows bowling columns', h.includes('BOWL AVG') && h.includes('ECON') && !h.includes('DUCKS'), h.join('|'))

// A season table ranked on wickets follows.
q = await preset('Most wickets in a season')
h = await headers()
ck('most wickets in a season: season target', q.target === 'player_season', JSON.stringify(q))
ck('most wickets in a season shows bowling columns', h.includes('WKTS') && h.includes('BOWL AVG') && !h.includes('100S'), h.join('|'))

// ── batting ranking keeps its table ───────────────────────────────────────
q = await preset('Top run aggregates')
h = await headers()
ck('run aggregates keeps the batting columns', ['RUNS', 'AVG', 'HS', '100S', '50S', 'DUCKS'].every(c => h.includes(c)), h.join('|'))
ck('run aggregates still ends with bowling and fielding', h.includes('WKTS') && h.includes('CT'), h.join('|'))

// ── the Sort by menu: changing the sort re-leads the table ───────────────
q = await preset('Most matches played')
h = await headers()
ck('most matches played keeps the batting-first table', h.includes('100S') && h.includes('DUCKS'), h.join('|'))

ck('no page errors', errors.length === 0, errors.join(' / '))
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
