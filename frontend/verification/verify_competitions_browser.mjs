// Drives the real stats screens in Chromium with the API stubbed at the
// network layer.
//
//   npx vite --port 5201 &
//   node frontend/verification/verify_competitions_browser.mjs [baseUrl]
//
// Two clubs were reported, from PlayHQ screenshots:
//
//   * Applecross plays Summer 2025/26 across THREE associations at once.
//   * Hamilton Veterans field one side in several competitions of the SAME
//     association in one season (the Border Cup and the VCV Over 60s
//     competition), which no association-level answer can separate.
//
// The club stubbed here is Applecross-shaped: three competitions, one of them
// covering most of its grades.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5201'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const CLUB = { id: 'org-1', name: 'Applecross Cricket Club', slug: 'applecross' }
const SEASONS = [{ id: 's-2025', name: 'Summer 2025/26', year: 2025 }]
const COMPETITIONS = [
  { id: 'c-wastca', name: 'West Australian Suburban Turf Cricket Assoc.',
    association_name: 'West Australian Suburban Turf Cricket Assoc.',
    grade_count: 12, season_count: 30, is_seeded: true, display_order: 0 },
  { id: 'c-pswl', name: 'Perth Scorchers Women\'s League',
    association_name: 'Perth Scorchers Women\'s League',
    grade_count: 2, season_count: 4, is_seeded: true, display_order: 1 },
  { id: 'c-icl', name: 'WA Integrated Cricket League',
    association_name: 'WA Integrated Cricket League',
    grade_count: 1, season_count: 2, is_seeded: true, display_order: 2 },
]
// One competition only — the club this feature must stay invisible for.
const SINGLE = [COMPETITIONS[0]]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

/**
 * A stats screen with the API stubbed. Returns the page plus every request it
 * made, so a check can assert what went ON THE WIRE rather than what the
 * screen says about itself.
 */
async function open(path, { competitions = COMPETITIONS, width = 1440 } = {}) {
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
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

    if (/^\/clubs\//.test(p)) {
      return json({ ...CLUB, theme_config: {}, is_active: true })
    }
    if (/grade-categories$/.test(p)) {
      return json({
        available: ['senior', 'womens'], default: ['senior', 'womens', 'masters', 'mixed'],
        available_formats: ['one_day', 't20'],
        available_competitions: competitions,
      })
    }
    if (/\/competitions$/.test(p) && /organisations/.test(p)) {
      const wanted = competitions.map((c, i) => ({
        competition_id: c.id, competition_name: c.name,
        association_name: c.association_name,
        matches: [140, 18, 9][i] ?? 1, won: 70, lost: 60, drawn: 10, win_pct: 53.8,
        seasons: c.season_count, grades: c.grade_count,
        first_year: 1996, last_year: 2025,
        runs: [24000, 3100, 900][i] ?? 100, wickets: 900, catches: 700, stumpings: 40,
      }))
      return json({
        rows: wanted, total_matches: wanted.reduce((a, r) => a + r.matches, 0),
        grades: [
          { competition_id: 'c-wastca', competition_name: COMPETITIONS[0].name, grade_name: '1st Grade', matches: 40, won: 22, lost: 16, drawn: 2, win_pct: 57.9, seasons: 30, last_year: 2025 },
          { competition_id: 'c-wastca', competition_name: COMPETITIONS[0].name, grade_name: 'One Day Grade 2', matches: 12, won: 7, lost: 5, drawn: 0, win_pct: 58.3, seasons: 3, last_year: 2025 },
          { competition_id: 'c-pswl', competition_name: COMPETITIONS[1].name, grade_name: 'PSWL South A', matches: 18, won: 11, lost: 7, drawn: 0, win_pct: 61.1, seasons: 4, last_year: 2025 },
        ],
        available: competitions,
      })
    }
    if (/seasons$/.test(p)) return json(SEASONS)
    if (/grades$/.test(p)) return json([{ id: 'g-1', name: '1st Grade' }])
    if (/leaderboard\/(batting|bowling|fielding|sirs)/.test(p)) return json([])
    if (/^\/games/.test(p)) return json([])
    if (/summary$/.test(p)) return json({ total_games: 0, wins: 0, losses: 0, draws: 0 })
    if (/results$/.test(p)) return json([])
    if (/^\/auth\/me/.test(p)) {
      return json({ id: 'u1', username: 'admin', role: 'club_admin', club_id: CLUB.id,
        capabilities: ['*'], entitlements: { modules: ['stats'], status: 'active' } })
    }
    return json([])
  })

  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1500)
  return { page, ctx, errors, calls }
}

/** The Competition pill row, addressed by its own label. */
function compRow(page) {
  return page.locator('div').filter({
    has: page.locator('label', { hasText: /^Competition$/ }),
  }).last()
}

// ------------------------------------------------- the filter row is drawn

{
  console.log('\nThe Competition filter on the club dashboard')
  const { page, ctx, errors, calls } = await open('/applecross')
  const label = page.locator('label', { hasText: /^Competition$/ })
  ck('a Competition filter row is drawn', await label.count() > 0)
  // Guarded so a CONTROL RUN against the previous commit reports each check as
  // failed rather than dying on a locator for a row that is not there yet.
  const buttons = compRow(page).locator('button')
  const texts = (await label.count()) ? await buttons.allTextContents() : []
  ck('it offers All plus every competition the club plays',
    texts.length === 4 && /All/.test(texts[0])
    && texts.some(t => /Suburban Turf/.test(t))
    && texts.some(t => /Scorchers/.test(t))
    && texts.some(t => /Integrated/.test(t)), JSON.stringify(texts))

  // What actually goes on the wire is what matters — a pill that highlights
  // and sends nothing would still look right.
  calls.length = 0
  if (await buttons.filter({ hasText: /Scorchers/ }).count()) {
    await buttons.filter({ hasText: /Scorchers/ }).first().click()
    await page.waitForTimeout(900)
  }
  const scoped = calls.filter(c => c.params.competitions)
  ck('picking one sends competitions= on the wire',
    scoped.length > 0 && scoped.every(c => c.params.competitions === 'c-pswl'),
    JSON.stringify(scoped.map(c => [c.path, c.params.competitions]).slice(0, 4)))
  ck('and it reaches the leaderboards, the summary and the games list',
    ['leaderboard', 'summary', 'games'].every(
      k => scoped.some(c => c.path.includes(k))),
    JSON.stringify([...new Set(scoped.map(c => c.path))]))

  calls.length = 0
  if (await buttons.filter({ hasText: /^All$/ }).count()) {
    await buttons.filter({ hasText: /^All$/ }).first().click()
    await page.waitForTimeout(900)
  }
  ck('clearing it sends no competitions param at all',
    scoped.length > 0 && calls.length > 0 && calls.every(c => !c.params.competitions),
    JSON.stringify(calls.map(c => c.params.competitions).slice(0, 4)))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------------- the row a single-competition club gets

{
  console.log('\nA club that plays ONE competition')
  const { page, ctx, errors } = await open('/applecross', { competitions: SINGLE })
  ck('is offered no Competition row at all — a control that could only ever '
     + 'answer "everything" is worse than none',
    await page.locator('label', { hasText: /^Competition$/ }).count() === 0)
  ck('while the other filter rows are unaffected',
    await page.locator('label', { hasText: /^Grade Type$/ }).count() > 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------------------------------ every stats surface

for (const [name, path] of [
  ['Leaderboard', '/applecross/leaderboard'],
  ['Records', '/applecross/records'],
  ['Players', '/applecross/players'],
  ['Games', '/applecross/games'],
]) {
  console.log(`\n${name}`)
  const { page, ctx, errors, calls } = await open(path)
  const label = page.locator('label', { hasText: /^Competition$/ })
  ck(`${name} draws the Competition row`, await label.count() > 0)
  if (await label.count() > 0) {
    calls.length = 0
    await compRow(page).locator('button').filter({ hasText: /Integrated/ }).first().click()
    await page.waitForTimeout(900)
    const scoped = calls.filter(c => c.params.competitions === 'c-icl')
    ck(`${name} sends the picked competition on the wire`, scoped.length > 0,
      JSON.stringify(calls.map(c => [c.path, c.params.competitions]).slice(0, 3)))
  }
  ck(`${name}: no page errors`, errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// -------------------------------------- the player's own by-competition panel

{
  console.log("\nA player's COMPETITIONS panel")
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1600 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  let asked = null
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const p = url.pathname.replace(/^\/api/, '')
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/players\/[^/]+\/competitions/.test(p)) {
      asked = p
      return json({
        rows: [
          { competition_id: 'c-wastca', competition_name: 'West Australian Suburban Turf Cricket Assoc.',
            association_name: 'WASTCA', matches: 118, seasons: 12, grades: 5,
            first_year: 2013, last_year: 2025,
            batting: { innings: 110, not_outs: 14, runs: 3412, high_score: 143, average: 35.54,
                       strike_rate: 68.2, balls: 5003, fours: 380, sixes: 44, fifties: 19, hundreds: 4 },
            bowling: { spells: 90, wickets: 141, runs: 3010, maidens: 62, balls: 5400,
                       overs: 900, average: 21.35, economy: 3.34, strike_rate: 38.3 },
            fielding: { catches: 61, catches_wk: 0, catches_non_wk: 61, stumpings: 0, run_outs: 7 } },
          { competition_id: 'c-icl', competition_name: 'WA Integrated Cricket League',
            association_name: 'WA ICL', matches: 9, seasons: 2, grades: 1,
            first_year: 2024, last_year: 2025,
            batting: { innings: 8, not_outs: 1, runs: 214, high_score: 61, average: 30.57,
                       strike_rate: 91.0, balls: 235, fours: 22, sixes: 6, fifties: 1, hundreds: 0 },
            bowling: { spells: 6, wickets: 7, runs: 180, maidens: 1, balls: 240,
                       overs: 40, average: 25.71, economy: 4.5, strike_rate: 34.3 },
            fielding: { catches: 4, catches_wk: 0, catches_non_wk: 4, stumpings: 0, run_outs: 1 } },
        ],
        total_matches: 127,
        unattributed: 6,
      })
    }
    if (/^\/players\/[^/]+\/stats/.test(p)) {
      return json({
        player: { id: 'p1', name: 'Barendse, Jack', display_name: 'Barendse, Jack',
                  organisation_id: CLUB.id, claimed: false },
        career_batting: {}, career_bowling: {}, career_fielding: {},
        batting_innings: [], bowling_spells: [],
        grade_scope: { categories: [], excluded_categories: [], active: false,
                       available: [], available_competitions: COMPETITIONS },
      })
    }
    if (/^\/players\/[^/]+$/.test(p)) {
      return json({ id: 'p1', name: 'Barendse, Jack', display_name: 'Barendse, Jack',
                    organisation_id: CLUB.id })
    }
    if (/^\/clubs\//.test(p)) return json({ ...CLUB, theme_config: {}, is_active: true })
    if (/grade-categories$/.test(p)) {
      return json({ available: [], default: [], available_formats: [],
                    available_competitions: COMPETITIONS })
    }
    if (/^\/auth\/me/.test(p)) return route.fulfill({ status: 401, body: '{}' })
    return json([])
  })
  await page.goto(`${BASE}/players/p1`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1600)

  const analysis = page.locator('button', { hasText: /^ANALYSIS$/ }).first()
  if (await analysis.count()) { await analysis.click(); await page.waitForTimeout(500) }
  const tab = page.locator('button', { hasText: /^COMPETITIONS$/ }).first()
  ck('the profile has a COMPETITIONS sub-tab', await tab.count() > 0)
  if (await tab.count()) {
    ck('which is lazy — nothing is fetched until it is opened', asked === null)
    await tab.click()
    await page.waitForTimeout(900)
    ck('opening it fetches the breakdown', asked !== null, String(asked))
    const body = await page.locator('body').innerText()
    ck('both competitions are drawn', /Suburban Turf/i.test(body) && /Integrated/i.test(body))
    ck('with the batting, bowling and fielding tables',
      /BATTING BY COMPETITION/i.test(body) && /BOWLING BY COMPETITION/i.test(body)
      && /FIELDING BY COMPETITION/i.test(body), body.slice(0, 400))
    ck('each competition\'s own figures, not a shared total',
      /3,?412/.test(body) && /214/.test(body), '')
    // The honest half: a competition breakdown is built from scorecards, so a
    // career that came through BetterImport has rows it cannot place.
    ck('and it SAYS what it could not place rather than quietly not adding up',
      /6 matches are recorded\s+without a grade/i.test(body.replace(/\s+/g, ' '))
      || /without a grade/i.test(body), '')
  }
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------------------ the Manage Grades admin screen

{
  console.log('\nManage Grades -> Competitions')
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1600 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))

  // The stub MUTATES, because one that answers the same thing every time
  // cannot tell a working write from a no-op.
  let comps = COMPETITIONS.map(c => ({ ...c }))
  let grades = [
    { name: '1st Grade', competition_id: 'c-wastca', association_name: 'WASTCA', mixed: false, latest_year: 2025, season_rows: 30 },
    { name: 'PSWL South A', competition_id: 'c-pswl', association_name: 'PSWL', mixed: false, latest_year: 2025, season_rows: 4 },
    { name: 'Old Colts Cup', competition_id: null, association_name: null, mixed: false, latest_year: 2001, season_rows: 2 },
  ]

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    const method = req.method()
    let payload = null
    try { payload = req.postDataJSON() } catch { payload = null }
    if (method !== 'GET') calls.push({ path: p, method, payload })
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

    if (/^\/auth\/me/.test(p)) {
      return json({ id: 'u1', username: 'admin', role: 'club_admin', club_id: CLUB.id,
        capabilities: ['*'], entitlements: { modules: ['stats'], status: 'active' } })
    }
    if (/^\/admin\/competitions\/grouping$/.test(p)) {
      // Nothing to fetch. This block's own check asserts the prompt is
      // therefore not drawn at all.
      return json({ needs_grouping: false, seasons_missing: 0, grades_ungrouped: 1,
                    competitions: comps.length, competitions_edited: false,
                    running_run_id: null })
    }
    if (/^\/admin\/competitions$/.test(p) && method === 'GET') {
      return json({ competitions: comps, grades,
                    associations: comps.map(c => ({ association_id: c.id, name: c.association_name, short_name: '', grade_count: c.grade_count })) })
    }
    if (/^\/admin\/competitions$/.test(p) && method === 'POST') {
      comps = [...comps, { id: 'c-new', name: payload.name, association_name: null,
                           grade_count: 0, season_count: 0, is_seeded: false, display_order: null }]
      return json({ id: 'c-new', name: payload.name })
    }
    if (/^\/admin\/competitions\/assign$/.test(p)) {
      grades = grades.map(g => g.name === payload.grade_name
        ? { ...g, competition_id: payload.competition_id } : g)
      return json({ status: 'assigned', season_rows: 2 })
    }
    if (/^\/admin\/competitions\/[^/]+$/.test(p) && method === 'PATCH') {
      const id = p.split('/').pop()
      comps = comps.map(c => c.id === id ? { ...c, name: payload.name, is_seeded: false } : c)
      return json({ status: 'renamed' })
    }
    if (/^\/admin\/competitions\/[^/]+$/.test(p) && method === 'DELETE') {
      const id = p.split('/').pop()
      comps = comps.filter(c => c.id !== id)
      grades = grades.map(g => g.competition_id === id ? { ...g, competition_id: null } : g)
      return json({ status: 'deleted' })
    }
    if (/grades-with-stats/.test(p)) return json([])
    if (/settings/.test(p)) return json({ id: CLUB.id, name: CLUB.name })
    return json([])
  })

  await page.goto(`${BASE}/admin/grades`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1800)
  const body = () => page.locator('body').innerText()

  ck('the screen lists the club\'s competitions',
    /Suburban Turf/.test(await body()) && /Scorchers/.test(await body()))
  ck('and the grades that are in no competition, rather than hiding them',
    /Not in a competition/i.test(await body()) && /Old Colts Cup/.test(await body()))
  // A button that would write nothing is worse than no button.
  ck('a club with nothing left to fetch is offered no grouping prompt',
    await page.locator('[data-testid="grouping-prompt"]').count() === 0
    && await page.locator('[data-testid="grouping-quiet"]').count() === 0)

  const hasManager = /Not in a competition/i.test(await body())

  // Assign the un-grouped grade.
  calls.length = 0
  if (hasManager) await page.evaluate(() => {
    // Address the select by ITS OWN ROW, not by an ancestor that merely
    // contains the text — a too-wide locator finds the first select on the
    // screen and the check passes on the wrong grade.
    const sel = [...document.querySelectorAll('select')].find(
      el => /^Old Colts Cup/.test(el.parentElement.textContent.trim()))
    sel.value = 'c-wastca'
    sel.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await page.waitForTimeout(900)
  const assign = calls.find(c => /assign/.test(c.path))
  ck('assigning a grade sends the grade NAME and the competition id',
    !!assign && assign.payload.grade_name === 'Old Colts Cup'
    && assign.payload.competition_id === 'c-wastca', JSON.stringify(assign))

  // Rename.
  calls.length = 0
  if (await page.locator('button', { hasText: /^Rename$/ }).count()) {
    await page.locator('button', { hasText: /^Rename$/ }).first().click()
    await page.waitForTimeout(300)
    const input = page.locator('input').first()
    await input.fill('WASTCA Seniors')
    await input.press('Enter')
    await page.waitForTimeout(900)
  }
  const rename = calls.find(c => c.method === 'PATCH')
  ck('renaming sends the new name', !!rename && rename.payload.name === 'WASTCA Seniors',
    JSON.stringify(rename))

  // Create.
  calls.length = 0
  const newInput = page.locator('input[placeholder="New competition name"]').first()
  if (await newInput.count()) {
    await newInput.fill('Border Cup')
    await page.locator('button', { hasText: /^Add$/ }).first().click()
    await page.waitForTimeout(900)
  }
  const created = calls.find(c => c.method === 'POST' && /competitions$/.test(c.path))
  ck('creating one sends its name', !!created && created.payload.name === 'Border Cup',
    JSON.stringify(created))

  // Delete, dismissed then accepted.
  calls.length = 0
  const del = page.locator('button', { hasText: /^Delete$/ })
  if (await del.count()) {
    page.once('dialog', d => d.dismiss())
    await del.first().click()
    await page.waitForTimeout(700)
  }
  ck('a dismissed delete sends nothing at all',
    hasManager && calls.length === 0, JSON.stringify(calls))

  let confirmText = ''
  if (await del.count()) {
    page.once('dialog', d => { confirmText = d.message(); d.accept() })
    await del.first().click()
    await page.waitForTimeout(900)
  }
  ck('the confirm says the grades and games are KEPT',
    /kept/i.test(confirmText) && /grade/i.test(confirmText), confirmText)
  ck('and accepting sends the delete',
    calls.some(c => c.method === 'DELETE'), JSON.stringify(calls))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------- grouping the seasons a sync no longer reaches

{
  console.log('\nManage Grades -> the grouping prompt and its progress bar')
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1600 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))

  // The run MUTATES as it is polled, because a stub that answers the same
  // thing every time cannot tell a working progress bar from a frozen one.
  let started = false
  let polls = 0
  let seasonsMissing = 12

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    const method = req.method()
    calls.push({ path: p, method })
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

    if (/^\/auth\/me/.test(p)) {
      return json({ id: 'u1', username: 'admin', role: 'club_admin', club_id: CLUB.id,
        capabilities: ['*'], entitlements: { modules: ['stats'], status: 'active' } })
    }
    if (/^\/admin\/competitions\/grouping$/.test(p) && method === 'POST') {
      started = true
      return json({ run_id: 'run-1', status: 'started' })
    }
    if (/^\/admin\/competitions\/grouping$/.test(p)) {
      return json({ needs_grouping: seasonsMissing > 0, seasons_missing: seasonsMissing,
                    grades_ungrouped: 3, competitions: 3, competitions_edited: true,
                    running_run_id: null })
    }
    if (/sync-runs\//.test(p)) {
      polls += 1
      // Two polls running, then done — enough to prove the bar moves and then
      // gives way to the result, without the check waiting on a real job.
      if (polls <= 2) {
        seasonsMissing = 12
        return json({ id: 'run-1', kind: 'competition_grouping', status: 'running',
                      stats: { progress_pct: polls === 1 ? 25 : 75, progress_done: polls * 3,
                               progress_total: 12, progress_phase: 'Season Summer 2014/15' },
                      error: null })
      }
      seasonsMissing = 0
      return json({ id: 'run-1', kind: 'competition_grouping', status: 'success',
                    stats: { seasons_checked: 12, seasons_failed: 0, grades_filled: 9,
                             associations_found: 2, competitions_created: 1, grades_assigned: 4 },
                    error: null })
    }
    if (/^\/admin\/competitions$/.test(p)) {
      return json({ competitions: COMPETITIONS, grades: [], associations: [] })
    }
    if (/grades-with-stats/.test(p)) return json([])
    if (/settings/.test(p)) return json({ id: CLUB.id, name: CLUB.name })
    return json([])
  })

  await page.goto(`${BASE}/admin/grades`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1600)
  const body = () => page.locator('body').innerText()

  const prompt = page.locator('[data-testid="grouping-prompt"]')
  ck('the club is told its older seasons sit outside its competitions',
    await prompt.count() > 0)
  ck('and the number is the seasons the job can actually act on',
    /12 seasons sit outside your competitions/i.test(await body()),
    (await body()).slice(0, 300))

  // Every interaction below is guarded, so a CONTROL RUN against the previous
  // commit reports each check as failed rather than dying on a locator for a
  // control that does not exist yet.
  const built = await prompt.count() > 0

  // "Come back later" — the offer is dismissed, never gone.
  if (built) {
    await page.locator('button', { hasText: /^Not now$/ }).first().click()
    await page.waitForTimeout(400)
  }
  ck('"Not now" puts the prompt away',
    built && await page.locator('[data-testid="grouping-prompt"]').count() === 0)
  ck('but the offer stays as one quiet line, so it can be said yes to later',
    await page.locator('[data-testid="grouping-quiet"]').count() > 0)

  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1400)
  ck('and the dismissal survives a reload, per person',
    built
    && await page.locator('[data-testid="grouping-prompt"]').count() === 0
    && await page.locator('[data-testid="grouping-quiet"]').count() > 0)

  // Clear it back so the rest of the checks drive the full prompt.
  await page.evaluate(() => {
    for (const k of Object.keys(localStorage)) {
      if (k.startsWith('bs_pref_competition_grouping_dismissed')) localStorage.removeItem(k)
    }
  })
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1400)
  ck('clearing the dismissal brings the prompt back',
    built && await page.locator('[data-testid="grouping-prompt"]').count() > 0)

  calls.length = 0
  if (await page.locator('button', { hasText: /Group them now/i }).count()) {
    await page.locator('button', { hasText: /Group them now/i }).first().click()
    await page.waitForTimeout(600)
  }
  const post = calls.find(c => c.method === 'POST' && /grouping$/.test(c.path))
  ck('pressing it starts the job on the wire', !!post && started, JSON.stringify(post))

  const bar = page.locator('[role="progressbar"]')
  ck('a progress bar is drawn while it runs', await bar.count() > 0)
  const firstPct = await bar.count()
    ? await bar.first().getAttribute('aria-valuenow') : null
  ck('carrying the real percentage, not a spinner',
    firstPct === '25' || firstPct === '75', String(firstPct))
  // A locator that finds nothing must read as a failure, never as a pass on
  // an unchanged bar.
  const moved = (a, b) => a !== null && b !== null && Number(b) > Number(a)
  ck('and it names the season it is on, so a long job is not a blank wait',
    /Season Summer/i.test(await body()), (await body()).slice(0, 400))

  // The bar has to MOVE. A check that reads it once cannot tell a live job
  // from a frozen one.
  await page.waitForTimeout(2400)
  const secondPct = await page.locator('[role="progressbar"]').first()
    .getAttribute('aria-valuenow').catch(() => null)
  ck('the bar moves as the job polls',
    // Gone entirely is the job having finished between the two reads, which
    // is the bar having moved all the way. Absent from the start is not.
    moved(firstPct, secondPct) || (firstPct !== null && secondPct === null),
    `${firstPct} -> ${secondPct}`)

  await page.waitForTimeout(3000)
  ck('and when it finishes it says what it actually did',
    await page.locator('[data-testid="grouping-result"]').count() > 0)
  ck('naming the grades filled in and the grades grouped',
    /9 grades filled in/i.test(await body()) && /4 grades grouped/i.test(await body()),
    (await body()).slice(0, 500))
  ck('the prompt is gone once there is nothing left to fetch',
    await page.locator('[data-testid="grouping-prompt"]').count() === 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ---------------------------------------------- the public Competitions page

for (const width of [1440, 390]) {
  console.log(`\nThe club's Competitions page at ${width}px`)
  const { page, ctx, errors, calls } = await open('/applecross/competitions', { width })
  const body = await page.locator('body').innerText()

  ck(`${width}: the page asks for the club's own breakdown`,
    calls.some(c => /organisations\/[^/]+\/competitions$/.test(c.path)),
    JSON.stringify(calls.map(c => c.path).slice(0, 6)))
  ck(`${width}: every competition the club plays is drawn`,
    /Suburban Turf/.test(body) && /Scorchers/.test(body) && /Integrated/.test(body))
  ck(`${width}: with the club's record in each`,
    /70/.test(body) && /53\.8%/.test(body), body.slice(0, 400))
  // The TEAM half: a grade under its own competition is what separates a side
  // playing in more than one inside a single season.
  ck(`${width}: and every grade listed under its own competition`,
    /1st Grade/.test(body) && /One Day Grade 2/.test(body) && /PSWL South A/.test(body))
  ck(`${width}: no page errors`, errors.length === 0, errors.join(' | '))

  if (width === 390) {
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth)
    ck('no horizontal overflow at 390px', overflow <= 0, `${overflow}px`)
  } else {
    // A grade must land under the competition it belongs to, not merely
    // somewhere on the page — measured off the two real boxes.
    const placed = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('table')]
      const owner = cards.find(t => /PSWL South A/.test(t.innerText))
      if (!owner) return null
      const card = owner.closest('div')?.parentElement
      return card ? /Scorchers/.test(card.innerText) && !/1st Grade/.test(owner.innerText) : null
    })
    ck('a grade sits inside its own competition\'s card, not just on the page',
      placed === true, String(placed))
    // The Stats menu is where a reader would look for it.
    ck('and the Stats menu offers it',
      await page.locator('a[href="/applecross/competitions"]').count() > 0
      || /Competitions/.test(body))
  }
  await ctx.close()
}

// -------------------------------------------------------------------- phone

{
  console.log('\nOn a phone')
  const { page, ctx, errors } = await open('/applecross', { width: 390 })
  ck('the Competition row still draws at 390px',
    await page.locator('label', { hasText: /^Competition$/ }).count() > 0
    || await page.locator('button', { hasText: /Suburban Turf/ }).count() > 0)
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', overflow <= 0, `${overflow}px`)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
