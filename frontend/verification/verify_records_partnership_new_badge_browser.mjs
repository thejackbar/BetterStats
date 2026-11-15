// Drives the real /:club/records PARTNERSHIPS tab in Chromium with the API stubbed at the network layer.
//
//   npx vite --port 5197 &
//   node frontend/verification/verify_records_partnership_new_badge_browser.mjs [baseUrl]
//
// Asked for: the batting and bowling boards mark a record made in the club's latest season with NEW;
// the partnership boards did not. Checks, on the page a visitor sees: a stand from the latest season
// carries NEW in all four tables (all-time, top 25, by grade, by wicket); a stand from an earlier
// season and a hand-typed record (season is a bare year) do not; 390px does not overflow sideways.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || ''
const SHOTS = process.env.SHOTS || '/tmp'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  — ${extra}` : ''}`) }
}

const stand = (runs, w, gameId, o = {}) => ({
  player1_id: o.p1 === undefined ? 'p-a' : o.p1, player1_name: o.n1 || 'Luke Pomersbach',
  player2_id: o.p2 === undefined ? 'p-b' : o.p2, player2_name: o.n2 || 'Derek Bland',
  runs, wicket_number: w, game_id: gameId, grade_name: o.grade || 'Grade D',
  season_name: o.season === undefined ? 'Summer 2017/18' : o.season, is_manual: !gameId,
})

const LATEST = 'Summer 2026/27'
const OLD_150 = stand(150, 1, 'game-150')
const NEW_208 = stand(208, 2, 'game-208', { n1: 'Hunter Daddow', p1: 'p-c', n2: 'Asitha Doloswala', p2: 'p-d', season: LATEST, grade: 'Grade F' })
const TYPED_90 = stand(90, 1, null, { p1: null, p2: null, n1: 'Old Timer', n2: 'Other Timer', season: '2017' })

const RECORDS = {
  batting: {}, bowling: {}, team: {}, allrounders: {},
  grade_scope: { categories: ['senior'], active: false },
  partnerships: {
    top_partnerships: [NEW_208, OLD_150, TYPED_90],
    wicket_1: [OLD_150, TYPED_90],
    wicket_2: [NEW_208],
    by_grade: { 'Grade D': [OLD_150], 'Grade F': [NEW_208] },
  },
}

const browser = await chromium.launch(EXECUTABLE && existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(width = 1440) {
  const ctx = await browser.newContext({ viewport: { width, height: 1100 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (/^\/clubs\/testclub/.test(path)) return json({ id: 'org-1', slug: 'testclub', name: 'Test Cricket Club', is_active: true, website_enabled: false })
    if (/\/records\/[^/]+\/milestones/.test(path)) return json({ upcoming: [], achieved: [], scope: 'career' })
    if (/\/records\/[^/]+\/club$/.test(path)) return json({})
    if (/\/records\/[^/]+$/.test(path)) return json(RECORDS)
    if (/\/seasons/.test(path)) return json([{ id: 's26', name: LATEST, year: 2026 }, { id: 's17', name: 'Summer 2017/18', year: 2017 }])
    if (/grade-categories/.test(path)) return json({ available: ['senior'], default: ['senior'], available_formats: [] })
    if (/\/grades/.test(path)) return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    if (path === '/auth/me') return json({ detail: 'no' }, 401)
    return json({})
  })
  await page.goto(`${BASE}/testclub/records`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'PARTNERSHIPS', exact: true }).click()
  await page.waitForSelector('text=TOP 25 PARTNERSHIPS')
  return { ctx, page, errors }
}

const NEW = (loc) => loc.getByText('NEW', { exact: true })
// CSS `uppercase` is not applied to the badge text itself, which is written in capitals.

{
  const { ctx, page, errors } = await open()
  const card = (title) => page.locator('div.pb-card', { hasText: title }).first()

  const all = card('ALL TIME RECORDS')
  ck('all time: the latest-season stand (208) carries NEW',
     await NEW(all.locator('tr', { hasText: '208' })).count() === 1)
  ck('all time: the older stand (150) does not',
     await NEW(all.locator('tr', { hasText: '150' })).count() === 0)

  const top = card('TOP 25 PARTNERSHIPS')
  ck('top 25: the 208 carries NEW', await NEW(top.locator('tr', { hasText: '208' })).count() === 1)
  ck('top 25: the 150 does not', await NEW(top.locator('tr', { hasText: '150' })).count() === 0)
  ck('top 25: a hand-typed record (season "2017") does not', await NEW(top.locator('tr', { hasText: 'Timer, Old' })).count() === 0)

  const grade = card('WICKET RECORDS BY GRADE')
  ck('by grade: the 208 carries NEW', await NEW(grade.locator('tr', { hasText: '208' })).count() === 1)
  ck('by grade: the 150 does not', await NEW(grade.locator('tr', { hasText: '150' })).count() === 0)

  const w2 = card('2ND WICKET')
  ck('by wicket: the 208 carries NEW', await NEW(w2.locator('tr', { hasText: '208' })).count() === 1)
  const w1 = card('1ST WICKET')
  ck('by wicket: no NEW on the 1st wicket list (150 and the typed record)', await NEW(w1).count() === 0)

  ck('exactly four badges on the whole tab (one per table the 208 appears in)', await NEW(page.locator('main')).count() === 4,
     String(await NEW(page.locator('main')).count()))
  await page.screenshot({ path: `${SHOTS}/partnership_new_badge_desktop.png`, fullPage: true })
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  const { ctx, page } = await open(390)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ck('390px: the page does not overflow sideways', overflow <= 0, `${overflow}px`)
  ck('390px: the badge is still there', await NEW(page.locator('main')).count() === 4)
  await page.screenshot({ path: `${SHOTS}/partnership_new_badge_390.png`, fullPage: true })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
