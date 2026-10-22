// Drives the real /:club/records PARTNERSHIPS tab in Chromium with the API stubbed at the network layer.
//
//   npx vite --port 5197 &
//   node frontend/verification/verify_records_partnership_click_browser.mjs [baseUrl]
//
// Asked for: on the partnerships records a row should take you to the scorecard. Checks, on the page a
// visitor sees: all four tables (all-time, top 25, by grade, by wicket) open the match; a click on a
// player's NAME still goes to the player, not the match; a hand-typed record (it names no match) is
// not clickable and does not look it; Enter opens the match from the keyboard; 390px does not
// overflow sideways.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || '/tmp'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  — ${extra}` : ''}`) }
}

const stand = (runs, w, gameId, o = {}) => ({
  player1_id: o.p1 === undefined ? 'p-a' : o.p1, player1_name: o.n1 || 'Luke Pomersbach',
  player2_id: o.p2 === undefined ? 'p-b' : o.p2, player2_name: o.n2 || 'Derek Bland',
  runs, wicket_number: w, game_id: gameId, grade_name: 'Grade D', season_name: 'Summer 2017/18',
  is_manual: !gameId,
})

const REAL_150 = stand(150, 1, 'game-150')
const REAL_100 = stand(100, 2, 'game-100', { n1: 'Bryden Emrich', p1: 'p-c', n2: 'Daniel Smedley', p2: 'p-d' })
const TYPED_300 = stand(300, 1, null, { p1: null, p2: null, n1: 'Old Timer', n2: 'Other Timer' })

const RECORDS = {
  batting: {}, bowling: {}, team: {}, allrounders: {},
  grade_scope: { categories: ['senior'], active: false },
  partnerships: {
    top_partnerships: [TYPED_300, REAL_150, REAL_100],
    wicket_1: [TYPED_300, REAL_150],
    wicket_2: [REAL_100],
    by_grade: { 'Grade D': [REAL_150, REAL_100] },
  },
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

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
    if (/\/seasons/.test(path)) return json([{ id: 's17', name: 'Summer 2017/18', year: 2017 }])
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

const path = (page) => new URL(page.url()).pathname

// ── The four tables ──────────────────────────────────────────────────────────
{
  const { ctx, page, errors } = await open()
  const rows = page.locator('tr[title="Open the scorecard"]')
  // all-time lists wicket 1's best (the typed 300, no match) and wicket 2's best (100) = 1 link row; top 25 = 2 real + 1 typed; by grade = 2;
  // by wicket: wicket 1 has 1 real + 1 typed, wicket 2 has 1 real = 2 real
  ck('every real stand is a link row, in all four tables (1 + 2 + 2 + 2)', await rows.count() === 7, String(await rows.count()))
  if (await rows.count() === 0) {
    // The state before the change: no row opens anything. Report it and stop, rather than wait out a click.
    ck('a partnership row opens its match', false, 'no row on the page is a link to a scorecard')
    await browser.close()
    console.log(`\n${pass} passed, ${fail} failed`)
    process.exit(1)
  }
  const typedRows = page.locator('tr', { hasText: 'Timer, Old' })
  ck('the hand-typed record is on the page', await typedRows.count() >= 1)
  ck('a hand-typed record is not a link row', await typedRows.first().getAttribute('title') === null)
  ck('and does not show a pointer', await typedRows.first().evaluate(el => getComputedStyle(el).cursor) !== 'pointer')
  ck('a real stand shows a pointer', await rows.first().evaluate(el => getComputedStyle(el).cursor) === 'pointer')

  const top = page.locator('div.pb-card', { hasText: 'TOP 25 PARTNERSHIPS' }).first()
  await top.locator('tr[title="Open the scorecard"]', { hasText: '150' }).first().locator('td').nth(2).click()
  await page.waitForURL(/\/games\/game-150$/)
  ck('top 25: clicking the runs opens that match', path(page) === '/games/game-150', path(page))

  await page.goBack()
  await page.getByRole('button', { name: 'PARTNERSHIPS', exact: true }).click()
  await page.waitForSelector('text=TOP 25 PARTNERSHIPS')
  const top2 = page.locator('div.pb-card', { hasText: 'TOP 25 PARTNERSHIPS' }).first()
  await top2.locator('tr[title="Open the scorecard"]', { hasText: '150' }).first().getByRole('link', { name: 'Pomersbach, Luke' }).click()
  await page.waitForURL(/\/players\/p-a$/)
  ck("clicking a player's name goes to the player, not the match", path(page) === '/players/p-a', path(page))

  await page.goBack()
  await page.getByRole('button', { name: 'PARTNERSHIPS', exact: true }).click()
  await page.waitForSelector('text=TOP 25 PARTNERSHIPS')
  const w2 = page.locator('div.pb-card', { hasText: '2ND WICKET' }).first()
  await w2.locator('tr[title="Open the scorecard"]').first().click({ position: { x: 4, y: 4 } })
  await page.waitForURL(/\/games\/game-100$/)
  ck('by wicket: a row opens its match', path(page) === '/games/game-100', path(page))

  await page.goBack()
  await page.getByRole('button', { name: 'PARTNERSHIPS', exact: true }).click()
  await page.waitForSelector('text=WICKET RECORDS BY GRADE')
  const grade = page.locator('div.pb-card', { hasText: 'WICKET RECORDS BY GRADE' }).first()
  await grade.locator('tr[title="Open the scorecard"]', { hasText: '150' }).first().locator('td').nth(2).click()
  await page.waitForURL(/\/games\/game-150$/)
  ck('by grade: a row opens its match', path(page) === '/games/game-150', path(page))

  await page.goBack()
  await page.getByRole('button', { name: 'PARTNERSHIPS', exact: true }).click()
  await page.waitForSelector('text=ALL TIME RECORDS')
  const all = page.locator('div.pb-card', { hasText: 'ALL TIME RECORDS' }).first()
  await all.locator('tr[title="Open the scorecard"]', { hasText: '100' }).first().locator('td').first().click()
  await page.waitForURL(/\/games\/game-100$/)
  ck('all time: a row opens its match', path(page) === '/games/game-100', path(page))

  await page.goBack()
  await page.getByRole('button', { name: 'PARTNERSHIPS', exact: true }).click()
  await page.waitForSelector('text=TOP 25 PARTNERSHIPS')
  const first = page.locator('div.pb-card', { hasText: 'TOP 25 PARTNERSHIPS' }).first()
    .locator('tr[title="Open the scorecard"]').first()
  await first.focus()
  await page.keyboard.press('Enter')
  await page.waitForURL(/\/games\/game-/)
  ck('Enter on a focused row opens its match', /^\/games\/game-/.test(path(page)), path(page))

  await page.goBack()
  await page.getByRole('button', { name: 'PARTNERSHIPS', exact: true }).click()
  await page.waitForSelector('text=TOP 25 PARTNERSHIPS')
  const url0 = page.url()
  await page.locator('tr', { hasText: 'Timer, Old' }).first().locator('td').nth(2).click()
  await page.waitForTimeout(300)
  ck('clicking a hand-typed record goes nowhere', page.url() === url0, page.url())
  await page.screenshot({ path: `${SHOTS}/records_partnership_click.png` })
  ck('no script errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── 390px ────────────────────────────────────────────────────────────────────
{
  const { ctx, page } = await open(390)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no sideways overflow on the partnerships tab', over <= 0, `overflow ${over}px`)
  await page.screenshot({ path: `${SHOTS}/records_partnership_click_390.png` })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
