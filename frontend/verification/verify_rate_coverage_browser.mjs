// Drives the real Leaderboard and Records screens in Chromium with the API
// stubbed at the network layer.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_rate_coverage_browser.mjs [baseUrl]
//
// A season scored partly on an iPad and partly in a written book gives us every
// run and only some of the ball counts. The figure is worked out from the
// innings that carry a ball count, and these screens have to say so — a rate
// nobody can check is worse than no rate.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

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
const SEASONS = [{ id: 's-2025', name: 'Summer 2025/26', year: 2025 }]

// The reported player: 500 runs, ball counts for three of ten innings.
const PARTIAL = {
  player_id: 'p-1', name: 'Barendse, Jack', games: 10, innings: 10,
  total_runs: 500, average: 50.0, strike_rate: 100.0, high_score: 50,
  fifties: 10, hundreds: 0, total_fours: 0, total_sixes: 0, ducks: 0,
  strike_rate_coverage: { counted: 3, of: 10, complete: false, none: false, basis: 'innings' },
}
// A team-mate whose season was scored on the iPad throughout.
const COMPLETE = {
  player_id: 'p-2', name: 'Mant, Brad', games: 12, innings: 12,
  total_runs: 600, average: 50.0, strike_rate: 125.0, high_score: 80,
  fifties: 6, hundreds: 0, total_fours: 0, total_sixes: 0, ducks: 0,
  strike_rate_coverage: { counted: 12, of: 12, complete: true, none: false, basis: 'innings' },
}
const BOWLER_PARTIAL = {
  player_id: 'p-3', name: 'Cole, Graeme', games: 4, total_wickets: 6,
  average: 20.83, economy: 3.0, total_maidens: 0, total_overs: 20, five_fors: 0,
  best_bowling_figures: '2-30', best_figures_wickets: 2,
  economy_coverage: { counted: 2, of: 4, complete: false, none: false, basis: 'innings' },
}

const RECORDS = {
  scope: { categories: [], excluded_categories: [], formats: null, excluded_formats: [], active: false, available: [], available_formats: [] },
  batting: {
    top_career_runs: [], top_high_scores: [], top_batting_avg: [],
    most_fifties: [], most_hundreds: [], most_ducks: [], most_runs_season: [],
    best_strike_rate_season: [
      { player_id: 'p-1', name: 'Barendse, Jack', strike_rate: 150.0, runs: 720,
        season_name: 'Summer 2025/26', season_year: 2025,
        strike_rate_coverage: { counted: 12, of: 12, complete: true, none: false, basis: 'innings' } },
      { player_id: 'p-2', name: 'Mant, Brad', strike_rate: 118.5, runs: 430,
        season_name: 'Summer 2024/25', season_year: 2024,
        strike_rate_coverage: { counted: 10, of: 14, complete: false, none: false, basis: 'innings' } },
    ],
  },
  bowling: {
    top_career_wickets: [], best_innings_figures: [], top_bowling_avg: [],
    top_economy: [], most_five_fors: [], most_wickets_season: [],
    best_economy_season: [
      { player_id: 'p-3', name: 'Cole, Graeme', economy: 2.85, wickets: 24, overs: 96,
        season_name: 'Summer 2025/26', season_year: 2025,
        economy_coverage: { counted: 10, of: 12, complete: false, none: false, basis: 'innings' } },
    ],
  },
  partnerships: {}, team: { most_matches: [], most_seasons: [] },
  allrounders: { top_allrounders: [] },
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(path, { width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const p = url.pathname.replace(/^\/api/, '')
    calls.push({ path: p, params: Object.fromEntries(url.searchParams) })
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (/^\/auth\/me/.test(p)) return route.fulfill({ status: 401, body: '{}' })
    if (/^\/clubs\/our-club$/.test(p)) return json(CLUB)
    if (/\/seasons$/.test(p)) return json(SEASONS)
    if (/grade-categories/.test(p)) return json({ available: [], default: [], available_formats: [] })
    if (/^\/leaderboard\/batting/.test(p)) {
      const min = url.searchParams.get('min_rate_innings')
      // Behave like the real board: a bar of N drops anyone whose COVERED
      // innings fall short, which is the whole point of counting them.
      const rows = [PARTIAL, COMPLETE].filter(r =>
        min == null || r.strike_rate_coverage.counted >= Number(min))
      return json(rows)
    }
    if (/^\/leaderboard\/bowling/.test(p)) return json([BOWLER_PARTIAL])
    if (/^\/leaderboard\/fielding/.test(p)) return json([])
    if (/^\/records\/.*\/milestones/.test(p)) return json({})
    if (/^\/records\//.test(p)) return json(RECORDS)
    if (/grades/.test(p)) return json([])
    return json({})
  })

  await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' })
  return { page, ctx, errors, calls }
}

const text = (page) => page.evaluate(() => document.body.innerText.replace(/\s+/g, ' '))

// ------------------------------------------------------------- leaderboard

{
  console.log('\nThe batting board can be sorted by strike rate, and says what answered it')
  const { page, ctx, errors, calls } = await open('/our-club/leaderboard')

  const sortBtn = page.getByRole('button', { name: 'STRIKE RATE', exact: true })
  ck('a STRIKE RATE sort exists on the batting board', await sortBtn.count() > 0)
  if (await sortBtn.count()) {
    calls.length = 0
    await sortBtn.first().click()
    await page.waitForTimeout(600)
    const board = calls.find(c => c.path === '/leaderboard/batting')
    ck('it asks the server for a strike-rate board', board?.params.sort_by === 'strike_rate',
       JSON.stringify(board?.params))
    ck('and sends no minimum, so the club’s own setting applies',
       board && !('min_rate_innings' in board.params), JSON.stringify(board?.params))

    const body = await text(page)
    ck('the partially covered player is marked', /100\.00\s*†/.test(body) || body.includes('†'), body.slice(0, 300))
    ck('the fully covered player is NOT marked',
       !/125\.00\s*†/.test(body), body.slice(0, 300))
    ck('a footnote explains the mark', /Data may be incomplete for these rows/i.test(body))

    // The explainer behind the (i)
    const info = page.getByRole('button', { name: /Why this strike rate may be incomplete/i })
    ck('there is an (i) to open the explainer', await info.count() > 0)
    if (await info.count()) {
      await info.first().click()
      await page.waitForTimeout(200)
      const open = await text(page)
      ck('the explainer says both halves must come from the same innings',
         /same innings/i.test(open), open.slice(0, 400))
      ck('and says the other figures still count every innings',
         /still count every innings/i.test(open))
      await page.keyboard.press('Escape')
      await page.waitForTimeout(150)
      ck('Escape closes it again',
         !/same innings/i.test(await text(page)))
    }
  }

  console.log('\nThe minimum is offered, and it is counted on ball-counted innings')
  const pills = page.getByRole('button', { name: '10+', exact: true })
  ck('a minimum control is offered', await pills.count() > 0)
  if (await pills.count()) {
    calls.length = 0
    await pills.first().click()
    await page.waitForTimeout(600)
    const board = calls.find(c => c.path === '/leaderboard/batting')
    ck('picking 10+ sends min_rate_innings=10', board?.params.min_rate_innings === '10',
       JSON.stringify(board?.params))
    const body = await text(page)
    ck('the 3-of-10 player drops off, though he played ten innings',
       !body.includes('Barendse'), body.slice(0, 300))
    ck('the 12-of-12 player stays', body.includes('Mant'), body.slice(0, 300))
  }
  const anyPill = page.getByRole('button', { name: 'Any', exact: true })
  if (await anyPill.count()) {
    calls.length = 0
    await anyPill.first().click()
    await page.waitForTimeout(600)
    const board = calls.find(c => c.path === '/leaderboard/batting')
    ck('"Any" sends an explicit 0 rather than nothing',
       board?.params.min_rate_innings === '0', JSON.stringify(board?.params))
  }

  ck('no page errors', errors.length === 0, errors.join(' | '))
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 1440px', overflow <= 0, String(overflow))
  await ctx.close()
}

{
  console.log('\nThe bowling board marks a partially covered economy')
  const { page, ctx, errors } = await open('/our-club/leaderboard')
  const bowlTab = page.getByRole('button', { name: /^BOWLING$/i })
  if (await bowlTab.count()) {
    await bowlTab.first().click()
    await page.waitForTimeout(500)
  }
  const body = await text(page)
  ck('the economy carries the mark', body.includes('†'), body.slice(0, 300))
  ck('the footnote reads for spells', /not every innings recorded a ball count/i.test(body) || /Data may be incomplete/i.test(body))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ----------------------------------------------------------------- records

{
  console.log('\nRecords files a strike rate by season and points at StatLab for a range')
  const { page, ctx, errors } = await open('/our-club/records')
  const body = await text(page)
  ck('a season strike-rate record is drawn', /BEST STRIKE RATE IN A SEASON/i.test(body), body.slice(0, 400))
  ck('it carries the qualification it was built with',
     /MIN\. 10 INNINGS WITH BALLS FACED/i.test(body))
  ck('the record names its season', /Summer 2025\/26|2025\/26/.test(body))
  // Read off the rows themselves: a count of daggers on the page would pass
  // with BOTH marked, which is the failure this is meant to catch.
  const srRows = await page.evaluate(() => {
    const card = [...document.querySelectorAll('.pb-card')].find(
      el => /BEST STRIKE RATE IN A SEASON/i.test(el.innerText || ''))
    return [...(card?.querySelectorAll('tbody tr') || [])].map(tr => tr.innerText.replace(/\s+/g, ' '))
  })
  ck('the fully covered leader carries no mark',
     srRows[0] && /150\.00/.test(srRows[0]) && !srRows[0].includes('†'), JSON.stringify(srRows))
  ck('the partially covered one does',
     srRows[1] && /118\.50/.test(srRows[1]) && srRows[1].includes('†'), JSON.stringify(srRows))
  const bowlTab = page.getByRole('button', { name: /^BOWLING$/i })
  if (await bowlTab.count()) { await bowlTab.first().click(); await page.waitForTimeout(400) }
  const bowlBody = await text(page)
  ck('a season economy record is drawn', /BEST ECONOMY IN A SEASON/i.test(bowlBody), bowlBody.slice(0, 400))
  ck('it explains why it is not all time',
     /how much was recorded changed from one era to the next/i.test(body), body.slice(0, 600))

  const statlab = page.getByRole('link', { name: 'StatLab', exact: true })
  ck('and points at StatLab for a range of seasons', await statlab.count() > 0)
  if (await statlab.count()) {
    const href = await statlab.first().getAttribute('href')
    ck('the StatLab link goes to this club’s StatLab', /\/our-club\/statlab$/.test(href || ''), String(href))
  }
  ck('no page errors', errors.length === 0, errors.join(' | '))
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 1440px', overflow <= 0, String(overflow))
  await ctx.close()
}

{
  console.log('\nNothing is said where the figure covers everything')
  const { page, ctx } = await open('/our-club/leaderboard')
  // The default board sorts by runs and every row here is complete on that
  // metric, so no mark and no footnote should be drawn at all.
  const body = await text(page)
  ck('no footnote on a board with nothing to qualify',
     !/Data may be incomplete for these rows/i.test(body), body.slice(0, 200))
  await ctx.close()
}

{
  console.log('\nOn a phone')
  for (const path of ['/our-club/leaderboard', '/our-club/records']) {
    const { page, ctx, errors } = await open(path, { width: 390 })
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth)
    ck(`${path}: no horizontal overflow at 390px`, overflow <= 0, String(overflow))
    ck(`${path}: no page errors at 390px`, errors.length === 0, errors.join(' | '))
    await ctx.close()
  }
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
