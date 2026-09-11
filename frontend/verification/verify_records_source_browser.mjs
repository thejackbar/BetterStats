// Drives the real stats screens in Chromium with the API stubbed at the
// network layer, for the RECORDS SOURCE axis.
//
//   npx vite --port 5202 &
//   node frontend/verification/verify_records_source_browser.mjs [baseUrl]
//
// Reported (Shoalwater Bay, Peter Ritchie, one competition only): the profile
// header read 408 matches with "Competition = All" while the Peel filter — his
// only competition — read 425, so "All" did not equal the sum of the
// competitions. It never could: "All" was Cricket Australia's own season total,
// and Cricket Australia is not a competition and holds no grade at all, so it
// can say nothing about which competition a match was in.
//
// The fix is a separate RECORDS axis:
//
//   * Cricket Australia (default) — the official season totals, unsliced. The
//     opening view is exactly what a club has always seen, and the competition
//     / grade-type / match-type pills are not even drawn.
//   * BetterCricket — everything we hold a scorecard for, which IS sliceable,
//     and whose "all competitions" state genuinely equals the sum. Only this
//     source sends source=scorecard and reveals the competition filter.
//
// So the check that matters is what goes ON THE WIRE: Cricket Australia sends
// no source and no slicing at all; BetterCricket sends source=scorecard, and a
// picked competition rides alongside it.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5202'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const CLUB = { id: 'org-1', name: 'Shoalwater Bay Cricket Club', slug: 'shoalwater-bay' }
const SEASONS = [{ id: 's-2025', name: 'Summer 2025/26', year: 2025 }]
// Two competitions, so the Competition row is genuinely offered (a
// single-competition club is shown none — a control that can only ever answer
// "everything").
const COMPETITIONS = [
  { id: 'c-peel', name: 'Peel Cricket Association Inc.',
    association_name: 'Peel Cricket Association Inc.',
    grade_count: 8, season_count: 20, is_seeded: true, display_order: 0 },
  { id: 'c-metro', name: 'Metro South Cricket League',
    association_name: 'Metro South Cricket League',
    grade_count: 3, season_count: 6, is_seeded: true, display_order: 1 },
]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

/** The pill row addressed by its own label, so a check reads the right group. */
function labelRow(page, label) {
  return page.locator('div').filter({
    has: page.locator('label', { hasText: new RegExp(`^${label}$`) }),
  }).last()
}
/** The two Records-source pills, addressed by the toggle's own label. */
function sourceRow(page) { return labelRow(page, 'Records') }

// A CONTROL RUN against the previous commit has no source toggle and no
// competition filter, so every read and click below must report absence rather
// than throw — a run that dies on the first missing locator says nothing about
// the checks under it. These are the textOf/press/attrOf pattern the repo keeps.
async function attrOf(locator, name) {
  try { return await locator.getAttribute(name, { timeout: 500 }) }
  catch { return null }
}
async function clickBtn(row, text) {
  const b = row.locator('button').filter({ hasText: text }).first()
  if (await b.count()) { await b.click(); return true }
  return false
}

// A leaderboard call carries the slicing params we care about; the summary /
// seasons / grade-categories calls do not, so filter to the ones under test.
const isDataCall = (c) => /leaderboard\/(batting|bowling|fielding|sirs)/.test(c.path)
const hasSource = (c) => 'source' in c.params
const hasComp = (c) => 'competitions' in c.params

async function open(path, { width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1600 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    calls.push({ path: p, params: Object.fromEntries(url.searchParams), method: req.method() })
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

    if (/^\/clubs\//.test(p)) return json({ ...CLUB, theme_config: {}, is_active: true })
    if (/grade-categories$/.test(p)) {
      return json({
        available: ['senior', 'womens'], default: ['senior', 'womens', 'masters', 'mixed'],
        available_formats: ['one_day', 't20'],
        available_competitions: COMPETITIONS,
      })
    }
    if (/seasons$/.test(p)) return json(SEASONS)
    if (/grades$/.test(p)) return json([{ id: 'g-1', name: '1st Grade' }])
    if (/leaderboard\/(batting|bowling|fielding|sirs)/.test(p)) return json([])
    if (/^\/games/.test(p)) return json([])
    if (/summary$/.test(p)) return json({ total_games: 0, wins: 0, losses: 0, draws: 0 })
    if (/results$/.test(p)) return json([])
    if (/^\/auth\/me/.test(p)) return route.fulfill({ status: 401, body: '{}' })
    return json([])
  })

  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1500)
  return { page, ctx, errors, calls }
}

// -------------------------------------------------- the two list surfaces
for (const [name, path] of [
  ['Players', '/shoalwater-bay/players'],
  ['Leaderboard', '/shoalwater-bay/leaderboard'],
]) {
  console.log(`\n${name}`)
  const { page, ctx, errors, calls } = await open(path)

  const src = sourceRow(page)
  ck(`${name}: the Records source toggle is drawn`,
    await page.locator('label', { hasText: /^Records$/ }).count() > 0)
  const srcButtons = src.locator('button')
  const srcTexts = (await srcButtons.count()) ? await srcButtons.allTextContents() : []
  ck(`${name}: it offers Cricket Australia and BetterCricket`,
    srcTexts.length === 2 && srcTexts.some(t => /Cricket Australia/.test(t))
    && srcTexts.some(t => /BetterCricket/.test(t)), JSON.stringify(srcTexts))
  ck(`${name}: Cricket Australia is the default`,
    (await attrOf(srcButtons.filter({ hasText: /Cricket Australia/ }).first(),
      'aria-pressed')) === 'true')

  // In Cricket Australia mode the sliceable pills are NOT drawn — Cricket
  // Australia is not a competition, so there is nothing to slice. This is the
  // discriminator: the previous build showed the Competition pill ALWAYS (it
  // had no source axis), so a bare "is it revealed after the switch" passes
  // for the wrong reason. Capture the count now and assert it moves 0 -> >0.
  const compBefore = await page.locator('label', { hasText: /^Competition$/ }).count()
  ck(`${name}: no Competition pill row in Cricket Australia mode`, compBefore === 0)
  ck(`${name}: no Grade Type pill row in Cricket Australia mode`,
    await page.locator('label', { hasText: /^Grade Type$/ }).count() === 0)
  ck(`${name}: no Match Type pill row in Cricket Australia mode`,
    await page.locator('label', { hasText: /^Match Type$/ }).count() === 0)

  // The opening fetch is the official record: no source, no slicing on the wire.
  const initial = calls.filter(isDataCall)
  ck(`${name}: the opening data fetch carries NO source param`,
    initial.length > 0 && initial.every(c => !hasSource(c)),
    JSON.stringify(initial.map(c => c.params.source).slice(0, 3)))
  ck(`${name}: and NO competition/grade slicing`,
    initial.every(c => !hasComp(c) && !('categories' in c.params) && !('formats' in c.params)))

  // Switch to BetterCricket.
  calls.length = 0
  await clickBtn(src, /BetterCricket/)
  await page.waitForTimeout(900)
  const compAfter = await page.locator('label', { hasText: /^Competition$/ }).count()
  ck(`${name}: switching to BetterCricket REVEALS the Competition filter (0 -> shown)`,
    compBefore === 0 && compAfter > 0, `${compBefore} -> ${compAfter}`)
  const scCalls = calls.filter(isDataCall)
  ck(`${name}: and the data fetch now carries source=scorecard`,
    scCalls.length > 0 && scCalls.every(c => c.params.source === 'scorecard'),
    JSON.stringify(scCalls.map(c => c.params.source).slice(0, 3)))
  ck(`${name}: with no competition picked, it sends no competitions= — the genuine sum`,
    scCalls.every(c => !hasComp(c)),
    JSON.stringify(scCalls.map(c => c.params.competitions).slice(0, 3)))

  // Pick one competition.
  calls.length = 0
  await clickBtn(labelRow(page, 'Competition'), /Peel/)
  await page.waitForTimeout(900)
  const picked = calls.filter(isDataCall)
  ck(`${name}: picking a competition sends source=scorecard AND competitions=`,
    picked.length > 0
    && picked.every(c => c.params.source === 'scorecard' && c.params.competitions === 'c-peel'),
    JSON.stringify(picked.map(c => [c.params.source, c.params.competitions]).slice(0, 3)))

  // Back to Cricket Australia: the competition row disappears and the pick is
  // dropped, so the official record can never come back sliced by a stale
  // competition.
  calls.length = 0
  await clickBtn(sourceRow(page), /Cricket Australia/)
  await page.waitForTimeout(900)
  ck(`${name}: switching back hides the Competition filter again`,
    await page.locator('label', { hasText: /^Competition$/ }).count() === 0)
  const backCalls = calls.filter(isDataCall)
  ck(`${name}: and drops both the source and the competition from the wire`,
    backCalls.length > 0 && backCalls.every(c => !hasSource(c) && !hasComp(c)),
    JSON.stringify(backCalls.map(c => [c.params.source, c.params.competitions]).slice(0, 3)))

  ck(`${name}: no page errors`, errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------------------------ the player profile itself
{
  console.log('\nThe player profile')
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1600 } })
  const page = await ctx.newPage()
  const errors = []
  const statsCalls = []
  page.on('pageerror', (e) => errors.push(String(e)))

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const p = url.pathname.replace(/^\/api/, '')
    const params = Object.fromEntries(url.searchParams)
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

    if (/^\/players\/[^/]+\/stats/.test(p)) {
      statsCalls.push(params)
      return json({
        player: { id: 'p1', name: 'Ritchie, Peter', display_name: 'Ritchie, Peter',
                  organisation_id: CLUB.id, claimed: false },
        career_batting: { matches: 408 }, career_bowling: {}, career_fielding: {},
        batting_innings: [], bowling_spells: [],
        match_coverage: { career_matches: 408, extra_scorecards: 17,
                          without_scorecard: 0, breakdown_matches: 425 },
        grade_scope: { categories: [], excluded_categories: [], active: false,
                       source: 'ca', available: ['senior'],
                       available_competitions: COMPETITIONS },
      })
    }
    if (/^\/players\/[^/]+$/.test(p)) {
      return json({ id: 'p1', name: 'Ritchie, Peter', display_name: 'Ritchie, Peter',
                    organisation_id: CLUB.id })
    }
    if (/^\/clubs\//.test(p)) return json({ ...CLUB, theme_config: {}, is_active: true })
    if (/seasons$/.test(p)) return json(SEASONS)
    if (/grade-categories$/.test(p)) {
      return json({ available: ['senior'], default: ['senior'], available_formats: [],
                    available_competitions: COMPETITIONS })
    }
    if (/players\/[^/]+\/competitions/.test(p)) return json({ rows: [], total_matches: 0, unattributed: 0 })
    if (/^\/auth\/me/.test(p)) return route.fulfill({ status: 401, body: '{}' })
    return json([])
  })

  await page.goto(`${BASE}/players/p1`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1800)

  ck('the profile draws the Records source toggle',
    await page.locator('label', { hasText: /^Records$/ }).count() > 0)
  ck('with Cricket Australia the default',
    (await attrOf(sourceRow(page).locator('button').filter({ hasText: /Cricket Australia/ })
      .first(), 'aria-pressed')) === 'true')
  // In Cricket Australia mode the whole GradeFilterPills block (competition and
  // the two grade axes) is not mounted at all.
  const profCompBefore = await page.locator('label', { hasText: /^Competition$/ }).count()
  ck('the profile offers NO competition filter in Cricket Australia mode',
    profCompBefore === 0)
  const initial = statsCalls.filter(c => 'source' in c)
  ck('the opening stats fetch carries no source', initial.length === 0,
    JSON.stringify(statsCalls.map(c => c.source).slice(0, 3)))

  // Switch to BetterCricket — the reported page's own gap: the profile had NO
  // competition filter at all, unlike the players list.
  statsCalls.length = 0
  await clickBtn(sourceRow(page), /BetterCricket/)
  await page.waitForTimeout(1000)
  const profCompAfter = await page.locator('label', { hasText: /^Competition$/ }).count()
  ck('switching to BetterCricket gives the profile a competition filter (0 -> shown)',
    profCompBefore === 0 && profCompAfter > 0, `${profCompBefore} -> ${profCompAfter}`)
  ck('and the stats fetch now carries source=scorecard',
    statsCalls.length > 0 && statsCalls.every(c => c.source === 'scorecard'),
    JSON.stringify(statsCalls.map(c => c.source).slice(0, 3)))

  // Pick Peter's one competition.
  statsCalls.length = 0
  await clickBtn(labelRow(page, 'Competition'), /Peel/)
  await page.waitForTimeout(1000)
  ck('picking a competition sends source=scorecard and competitions= together',
    statsCalls.length > 0
    && statsCalls.every(c => c.source === 'scorecard' && c.competitions === 'c-peel'),
    JSON.stringify(statsCalls.map(c => [c.source, c.competitions]).slice(0, 3)))

  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
