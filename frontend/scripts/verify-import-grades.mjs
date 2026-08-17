/**
 * Drive the import wizard's Grades step in a real browser.
 *
 * The API is stubbed at the network layer, so the actual AdminImport screen,
 * picker and payload building run for real. Checks the thing a screenshot
 * cannot: that "Add as a new historical grade" sends the seasons the sheet
 * records that competition in, and nothing else.
 *
 * Run against a dev server:  node scripts/verify-import-grades.mjs [baseUrl]
 */
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:5173'
const pass = [], fail = []
const check = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  ;(ok ? pass : fail).push(label)
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}: ${JSON.stringify(got)}${ok ? '' : ` (wanted ${JSON.stringify(want)})`}`)
}

const SEASONS = [
  { id: 's-2018', name: 'Summer 2018/19', year: 2018 },
  { id: 's-2019', name: 'Summer 2019/20', year: 2019 },
  { id: 's-2020', name: 'Summer 2020/21', year: 2020 },
]
const HEADERS = ['player_name', 'season_label', 'grade_label', 'batting_runs']
const ROWS = [
  { player_name: 'Ken Baker', season_label: 'Summer 2018/19', grade_label: 'VCV', batting_runs: '7' },
  { player_name: 'Ken Baker', season_label: 'Summer 2019/20', grade_label: 'VCV', batting_runs: '101' },
  // Border Cup only ever in 2020/21 — its create call must not name the others.
  { player_name: 'Geoff Barker', season_label: 'Summer 2020/21', grade_label: 'Border Cup', batting_runs: '149' },
]

const json = (route, body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const resolved = (gradeOverrides = {}) => ({
  granularity: 'season',
  columns_used: { player_name: 'player_name', season_label: 'season_label', grade_label: 'grade_label', batting_runs: 'batting_runs' },
  players: [
    { raw_name: 'Ken Baker', player_id: 'p1', matched_name: 'Ken Baker', status: 'exact', candidates: [] },
    { raw_name: 'Geoff Barker', player_id: 'p2', matched_name: 'Geoff Barker', status: 'exact', candidates: [] },
  ],
  seasons: SEASONS.map(s => ({ raw_label: s.name, season_id: s.id, matched_name: s.name, status: 'exact', candidates: [] })),
  grades: [
    { raw_label: 'VCV', grade_name: gradeOverrides.VCV || null, status: gradeOverrides.VCV ? 'manual' : 'none', candidates: [] },
    { raw_label: 'Border Cup', grade_name: gradeOverrides['Border Cup'] || null, status: gradeOverrides['Border Cup'] ? 'manual' : 'none', candidates: [] },
  ],
  grade_options: [{ name: '1st Grade', games: 12, players: 14, runs: 900 }],
  preview: [], rounding_notes: [], warnings: [],
  totals: { rows: ROWS.length, players_matched: 2, players_new: 0, players_unresolved: 0, rows_skipped: 0 },
})

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
const errors = []
page.on('pageerror', e => errors.push(String(e)))

let gradePosts = []
let lastResolve = null

await page.route('**/api/**', async route => {
  const url = route.request().url()
  const method = route.request().method()
  const body = () => { try { return JSON.parse(route.request().postData() || '{}') } catch { return {} } }

  if (url.includes('/auth/me')) return json(route, {
    id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'hvcc',
    entitlements: { modules: ['select', 'socials', 'admin', 'iq'], status: 'active' },
    capabilities: ['*'], organisation: { id: 'o1', name: 'Hamilton Veterans CC', slug: 'hvcc' },
  })
  if (url.includes('/imports/preview')) return json(route, {
    filename: 'hamilton.csv', headers: HEADERS, rows: ROWS,
    field_options: HEADERS, mapping_suggestions: Object.fromEntries(HEADERS.map(h => [h, { column: h, confidence: 1 }])),
    granularity_guess: 'season', row_count: ROWS.length, sample: ROWS,
  })
  if (url.includes('/imports/resolve')) {
    lastResolve = body()
    return json(route, resolved(lastResolve.grade_overrides || {}))
  }
  if (url.includes('/imports/grades') && method === 'POST') {
    gradePosts.push(body())
    const b = body()
    return json(route, { name: b.name, created: (b.season_ids || []).length, seasons: (b.season_ids || []).length,
                         already_existed: 0, option: { name: b.name, games: 0, players: 0, runs: 0 } })
  }
  if (url.includes('/imports')) return json(route, { imports: [] })
  if (url.includes('/players')) return json(route, [{ id: 'p1', name: 'Ken Baker', display_name: 'Ken Baker' }])
  if (url.includes('/seasons')) return json(route, SEASONS)
  return json(route, {})
})

await page.addInitScript(() => {
  localStorage.setItem('bs_token', 'test-token')
  localStorage.setItem('token', 'test-token')
})

await page.goto(`${BASE}/admin/import`, { waitUntil: 'networkidle' })

// Upload → the wizard parses through the stubbed preview.
const csv = [HEADERS.join(','), ...ROWS.map(r => HEADERS.map(h => r[h]).join(','))].join('\n')
await page.setInputFiles('input[type=file]', { name: 'hamilton.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })
await page.getByRole('button', { name: 'PARSE FILE' }).click()
await page.waitForTimeout(900)

// Walk to the Grades step through the wizard's own steps.
await page.getByRole('button', { name: /NEXT: MATCH PLAYERS/i }).click()
await page.waitForTimeout(600)
for (const label of ['4. Seasons', '5. Grades']) {
  const tab = page.getByRole('button', { name: label })
  await tab.first().click()
  await page.waitForTimeout(500)
}
check('the Grades step is reachable', await page.getByText('Match grades / teams').count() > 0, true)

// Open the first row's picker.
const rowButtons = page.locator('table button', { hasText: 'Unresolved' })
check('both unmatched labels are unresolved', await rowButtons.count(), 2)
await rowButtons.first().click()
await page.waitForTimeout(200)

const addOption = page.getByRole('button', { name: /Add as a new historical grade/i })
check('the wizard offers a new historical grade', await addOption.count() > 0, true)
await addOption.first().click()
await page.waitForTimeout(200)

// The sheet's own label is offered as the name, so the common case is one click.
const nameInput = page.locator('input[placeholder="e.g. Border Cup"]')
check('the sheet label is prefilled', await nameInput.inputValue(), 'VCV')

await page.getByRole('button', { name: 'ADD GRADE' }).click()
await page.waitForTimeout(600)

check('one grade was created', gradePosts.length, 1)
check('created under the name typed', gradePosts[0]?.name, 'VCV')
check('only the seasons the sheet records it in',
  [...(gradePosts[0]?.season_ids || [])].sort(), ['s-2018', 's-2019'])
check('the label now resolves to the new grade', lastResolve?.grade_overrides?.VCV, 'VCV')

// A second label played in one season only must not inherit the first's seasons.
await page.waitForTimeout(300)
const remaining = page.locator('table button', { hasText: 'Unresolved' })
await remaining.first().click()
await page.waitForTimeout(200)
await page.getByRole('button', { name: /Add as a new historical grade/i }).first().click()
await page.waitForTimeout(200)
await page.getByRole('button', { name: 'ADD GRADE' }).click()
await page.waitForTimeout(600)
check('the second grade names only its own season',
  [...(gradePosts[1]?.season_ids || [])].sort(), ['s-2020'])
check('and carries its own label', gradePosts[1]?.name, 'Border Cup')

check('no page errors', errors, [])
await page.setViewportSize({ width: 390, height: 900 })
await page.waitForTimeout(300)
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
check('no horizontal overflow at 390px', overflow, false)

await browser.close()
console.log(`\n${pass.length} passed, ${fail.length} failed`)
process.exit(fail.length ? 1 : 0)
