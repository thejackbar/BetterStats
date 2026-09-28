// Drives the real /:club/records MILESTONES tab in Chromium with the API
// stubbed at the network layer (harness lifted from verify_club_records_browser).
//
//   npx vite --port 5197 &
//   node frontend/verification/verify_milestone_split_browser.mjs [baseUrl]
//
// A player with junior and open-age records carries both figures, and the page
// has to SAY which one a milestone is measured on — without a switch, since the
// milestone emails cannot press one. A player with nothing to split must draw
// no note at all.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  — ${extra}` : ''}`) }
}

const HIND = 'p-hind', HETEL = 'p-hetel', GIRL = 'p-girl'
const UPCOMING = [
  { player_id: HIND, player_name: 'Hind, Jason', gender: 'male', type: 'runs', category: 'batting',
    current: 2982, target: 3000, needed: 18, detail: null,
    junior_split: { with_junior: 2982, without_junior: 2271 }, counts: 'with_junior' },
  { player_id: GIRL, player_name: 'Smith, Grace', gender: 'female', type: 'runs', category: 'batting',
    current: 495, target: 500, needed: 5, detail: null, variant: true,
    junior_split: { with_junior: 495, without_junior: 395 }, counts: 'with_junior' },
  { player_id: GIRL, player_name: 'Smith, Grace', gender: 'female', type: 'catches', category: 'fielding',
    current: 48, target: 50, needed: 2, detail: null,
    junior_split: { with_junior: 52, without_junior: 48 }, counts: 'without_junior' },
  { player_id: HETEL, player_name: 'Hetel, Steve', gender: 'male', type: 'runs', category: 'batting',
    current: 5924, target: 6000, needed: 76, detail: null },
]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openPage({ failPlayerRecords = false, width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  const clubCalls = []
  page.on('pageerror', (e) => errors.push(String(e)))

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')

    if (/\/records\/[^/]+\/club$/.test(path)) {
      clubCalls.push(url.search)
      return route.fulfill({ status: 200, contentType: 'application/json',
                             body: JSON.stringify(CLUB_RECORDS) })
    }
    if (/^\/clubs\/testclub/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: 'org-1', slug: 'testclub', name: 'Test Cricket Club', is_active: true,
        website_enabled: false,
      }) })
    }
    if (/\/records\/[^/]+\/milestones/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
                             body: JSON.stringify({ upcoming: UPCOMING, achieved: [], scope: 'career' }) })
    }
    if (/\/records\/[^/]+$/.test(path)) {
      // Deliberately answerable as a FAILURE: the club board must survive it.
      if (failPlayerRecords) return route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        batting: {}, bowling: {}, partnerships: {}, team: {}, allrounders: {},
        grade_scope: { categories: ['senior'], active: false },
      }) })
    }
    if (/\/seasons/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(
        [{ id: 's25', name: 'Summer 2025/26', year: 2025 }]) })
    }
    if (/grade-categories/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        available: ['senior'], default: ['senior'], available_formats: [] }) })
    }
    if (/\/grades/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    }
    if (path === '/auth/me') {
      return route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"no"}' })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
  return { page, ctx, errors, clubCalls }
}


async function openMilestones(width = 1440) {
  const o = await openPage({ width })
  await o.page.goto(`${BASE}/testclub/records`, { waitUntil: 'load' })
  await o.page.getByRole('button', { name: 'MILESTONES', exact: true }).click()
  await o.page.getByText('MILESTONES IN REACH').first().waitFor({ timeout: 15000 }).catch(() => {})
  return o
}

const rowText = async (page, name, needle) => {
  const rows = page.locator('tr', { hasText: name })
  const n = await rows.count()
  for (let i = 0; i < n; i++) {
    const t = await rows.nth(i).innerText()
    if (!needle || t.includes(needle)) return t
  }
  return ''
}

{
  const { page, ctx, errors } = await openMilestones()
  const hind = await rowText(page, 'Hind')
  ck('Hind is listed', hind.length > 0)
  ck('his row says the figure includes his junior matches',
     /Includes junior matches/i.test(hind), hind)
  ck('…and gives the other figure, 2,271 without them',
     hind.includes('2,271 runs without them'), hind)
  const girlRuns = await rowText(page, 'Smith', '495')
  ck('a milestone only the other figure reaches is still listed',
     girlRuns.includes('495'), girlRuns)
  ck('…and says it counts her junior matches',
     /Includes junior matches/i.test(girlRuns) && girlRuns.includes('395 runs without them'), girlRuns)
  const girlCatches = await rowText(page, 'Smith', '48')
  ck('a headline that leaves juniors out says so, with the other figure',
     /Excludes junior matches/i.test(girlCatches) && girlCatches.includes('52 catches with them'),
     girlCatches)
  const hetel = await rowText(page, 'Hetel')
  ck('a player with nothing to split draws no note',
     hetel.length > 0 && !/junior/i.test(hetel), hetel)
  ck('one note per split row, none elsewhere',
     (await page.locator('[data-testid="milestone-split"]').count()) === 3)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  const { page, ctx } = await openMilestones(390)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', over <= 0, `${over}px`)
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
