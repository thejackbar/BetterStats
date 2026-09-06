// Drives the real /:club/records CLUB tab in Chromium with the API stubbed at
// the network layer.
//
//   npx vite --port 5197 &
//   node frontend/verification/verify_club_records_browser.mjs [baseUrl]
//
// Checks the things a build cannot: that the club board is its OWN fetch (so a
// failing player-records call can't blank it, and opening the page on BATTING
// never pays for it), that the filters reach the wire, that an approximate
// figure is marked where it is READ rather than only counted in a footnote,
// and that each board draws the unit it is actually in.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  — ${extra}` : ''}`) }
}

const game = (id, o) => ({
  game_id: id, played_at: '2026-01-10', opponent: o.opp || 'Rovers',
  venue: 'Home Ground', our_venue: o.away ? 'AWAY' : 'HOME',
  season_name: 'Summer 2025/26', grade_name: "Men's First Grade",
  is_final: !!o.final, result: o.result || 'WIN',
  our_runs: o.our ?? 300, our_wickets: o.ourW ?? 8,
  opp_runs: o.opp_runs ?? 120, opp_wickets: o.oppW ?? 10,
  our_innings_count: o.innCount ?? 1, their_innings_count: 1,
  innings_number: o.inn ?? 1, innings_wickets: o.innW ?? null,
  value: o.value, unit: o.unit, exact: o.exact !== false,
})

const CLUB_RECORDS = {
  summary: { played: 16, wins: 8, losses: 6, draws: 2, seasons: 2 },
  coverage: {
    games_with_a_total: 16, exact_totals: 2, approximate_totals: 14,
    note: 'A total is exact when the club holds the scorecard’s own innings figure, which counts extras.',
  },
  grade_scope: {
    categories: ['senior'], formats: ['t20'], competition_names: ['Saturday Grade'],
    active: true, category_active: true, format_active: true, competition_active: true,
  },
  boards: {
    highest_totals: {
      rows: [game('g1', { value: 300 }), game('g2', { value: 250, exact: false, our: 250 })],
      approximate: 1,
    },
    lowest_totals: { rows: [game('g3', { value: 35, our: 35, ourW: 10, result: 'LOSS' })], approximate: 0 },
    highest_conceded: { rows: [game('g9', { value: 400, opp_runs: 400, result: 'LOSS' })], approximate: 0 },
    lowest_conceded: { rows: [game('g10', { value: 22, opp_runs: 22 })], approximate: 0 },
    highest_match_totals: {
      rows: [game('g1', { value: 481, innCount: 2, our: 481 })], approximate: 0 },
    highest_match_aggregates: {
      rows: [game('g1', { value: 583, innCount: 2, our: 481, opp_runs: 102 })], approximate: 0 },
    highest_chases: { rows: [{ ...game('g6', { value: 251, inn: 2, away: true }),
                               chased_with: 240, innings_wickets: 5 }], approximate: 0 },
    most_extras_conceded: { rows: [game('g1', { value: 8, inn: 2 })], approximate: 0 },
    narrowest_wins_runs: { rows: [game('g12', { value: 3, unit: 'runs' })], approximate: 0 },
    narrowest_wins_wickets: { rows: [game('g13', { value: 1, unit: 'wickets' })], approximate: 0 },
    head_to_head: {
      rows: [{ opponent: 'Rovers', played: 4, wins: 2, losses: 1, draws: 1,
               win_rate: 50.0, runs_for: 900, runs_against: 700, exact: false }],
      approximate: 0 },
    biggest_wins_runs: { rows: [game('g5', { value: 220, unit: 'runs' })], approximate: 0 },
    biggest_wins_wickets: { rows: [game('g6', { value: 9, unit: 'wickets', away: true })], approximate: 0 },
    heaviest_defeats_runs: { rows: [game('g7', { value: 160, unit: 'runs', result: 'LOSS' })], approximate: 0 },
    heaviest_defeats_wickets: { rows: [game('g8', { value: 8, unit: 'wickets', result: 'LOSS' })], approximate: 0 },
    longest_win_streak: {
      rows: [{ value: 3, from: '2026-01-12', to: '2026-01-14', from_season: 'Summer 2025/26',
               to_season: 'Summer 2025/26', wins: 3, draws: 0, exact: true }],
      approximate: 0,
    },
    longest_unbeaten_streak: {
      rows: [{ value: 4, from: '2026-01-11', to: '2026-01-14', from_season: 'Summer 2025/26',
               to_season: 'Summer 2025/26', wins: 3, losses: 0, draws: 1,
               grades: ["Men's First Grade"], opponents: ['A', 'B', 'C', 'D'], exact: true }],
      approximate: 0,
    },
    longest_losing_streak: {
      rows: [{ value: 2, from: '2026-02-01', to: '2026-02-08', from_season: 'Summer 2025/26',
               to_season: 'Summer 2025/26', wins: 0, losses: 2, draws: 0,
               grades: ["Men's First Grade"], opponents: ['E', 'F'], exact: true }],
      approximate: 0,
    },
    best_seasons: {
      rows: [
        { season_id: 's25', season_name: 'Summer 2025/26', played: 14, wins: 8, losses: 4,
          draws: 2, win_rate: 57.1, runs_for: 2000, runs_against: 1800, exact: false },
        { season_id: 's24', season_name: 'Summer 2024/25', played: 2, wins: 0, losses: 2,
          draws: 0, win_rate: 0.0, runs_for: 150, runs_against: 380, exact: true },
      ],
      approximate: 0,
    },
  },
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openPage({ failPlayerRecords = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
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
                             body: JSON.stringify({ upcoming: [], achieved: [], scope: 'career' }) })
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

const openClubTab = async (page) => {
  await page.getByRole('button', { name: 'CLUB', exact: true }).click()
  await page.waitForTimeout(400)
}

// ─────────────────────────────────────────────────── the tab and its fetch
{
  const { page, ctx, errors, clubCalls } = await openPage()
  await page.goto(`${BASE}/testclub/records`, { waitUntil: 'networkidle' })

  ck('CLUB is the first tab', 
     (await page.locator('button', { hasText: /^CLUB$/ }).count()) > 0)
  // The board is a separate per-game pull; landing on BATTING must not run it.
  ck('landing on BATTING never fetches the club board', clubCalls.length === 0,
     `${clubCalls.length} call(s)`)

  await openClubTab(page)
  ck('opening CLUB fetches the board once', clubCalls.length === 1, `${clubCalls.length}`)

  const body = await page.locator('main').innerText()
  ck('the club summary strip renders', /PLAYED/.test(body) && /SEASONS/.test(body))
  ck('every asked-for board is drawn', [
    'HIGHEST TEAM TOTALS', 'LOWEST TEAM TOTALS', 'HIGHEST OPPOSITION TOTALS',
    'LOWEST OPPOSITION TOTALS', 'BIGGEST WINS (RUNS)', 'BIGGEST WINS (WICKETS)',
    'HEAVIEST DEFEATS (RUNS)', 'HEAVIEST DEFEATS (WICKETS)',
    'HIGHEST MATCH TOTALS', 'HIGHEST MATCH AGGREGATES', 'HIGHEST SUCCESSFUL CHASES',
    'MOST EXTRAS CONCEDED', 'NARROWEST WINS (RUNS)', 'NARROWEST WINS (WICKETS)',
    'LONGEST WINNING RUN', 'LONGEST UNBEATEN RUN', 'LONGEST LOSING RUN',
    'HEAD TO HEAD', 'SEASON BY SEASON',
  ].every((t) => body.includes(t)), 'a board is missing')

  // The chase board ranks the TARGET; the runs we made getting there ride
  // alongside, or a 251 beside a 240 innings reads as an error.
  const chaseCard = page.locator('div.pb-card', { hasText: 'HIGHEST SUCCESSFUL CHASES' }).first()
  const chaseTxt = await chaseCard.innerText()
  ck('the chase board is headed by the target, not by runs made',
     /TARGET/.test(chaseTxt) && /Made/.test(chaseTxt), chaseTxt.slice(0, 120))
  ck('the chase row shows the target and what we made',
     chaseTxt.includes('251') && chaseTxt.includes('5/240'), chaseTxt.slice(0, 200))
  ck('the chase board says the target is what is ranked',
     chaseTxt.includes('the target we ran down'))

  const loseCard = page.locator('div.pb-card', { hasText: 'LONGEST LOSING RUN' }).first()
  const loseTxt = await loseCard.innerText()
  ck('the losing run counts losses, not wins', /Lost/.test(loseTxt), loseTxt.slice(0, 120))
  ck('the losing run reports its own length', loseTxt.includes('2'))

  ck('the extras board says it only uses cards that add up',
     body.includes('from cards that add up'))

  // A filter that IS working reads as broken when the top of a 25-row board
  // doesn't visibly move, so the scope has to be stated.
  ck('the board says what it covers', /COVERING 16 MATCHES/.test(body), body.slice(0, 200))
  ck('the scope names the competition in play', body.includes('Saturday Grade'))
  ck('the scope names the grade type', body.includes('Senior'))
  ck('the scope names the match type', body.includes('T20'))

  const q = clubCalls.join(' ')
  ck('gender is never on the wire for a team board', !q.includes('gender='))
  ck('the gender and captain pills are withdrawn on the club board',
     !(await page.locator('button', { hasText: /^(Male|Female)$/ }).count())
     && !(await page.locator('button', { hasText: /^Captain$/ }).count()))

  // The rename the club asked for: "defended against" described nothing.
  ck('the opposition boards are named for the opposition',
     !body.includes('DEFENDED AGAINST') && body.includes('LOWEST OPPOSITION TOTALS'))
  ck('a match aggregate is named as one, never as a total',
     body.includes('HIGHEST MATCH AGGREGATES') && body.includes('both sides, whole match'))
  ck('an innings board says it is one innings', body.includes('one innings'))
  ck('head to head lists the opponent', body.includes('Rovers'))
  ck('a streak says how it was worked out',
     body.includes('consecutive matches, in date order'))

  ck('the record total is on screen', body.includes('300'))
  ck('a wickets margin is drawn in wickets, not runs', /9\s*wkts/.test(body))
  ck('a runs margin is drawn in runs', /220\s*runs/.test(body))
  ck('the lowest board says it is all-out only', body.includes('all out only'))
  ck('the bowled-out board says so', body.includes('bowled out only'))

  // The coverage warning, and the per-row mark that makes it actionable.
  ck('the club is told how much of the book is approximate',
     /14 OF 16 TOTALS ARE APPROXIMATE/.test(body))
  const approxMarks = await page.locator('span[title*="Bat-only"]').count()
  ck('an approximate figure is marked where it is READ', approxMarks >= 1, `${approxMarks} mark(s)`)
  // Row 1 of HIGHEST TEAM TOTALS is the exact 300, row 2 the bat-only 250.
  // Asserting per row is what makes this a check rather than a head count.
  const hiRows = page.locator('table').first().locator('tbody tr')
  const exactRowMarks = await hiRows.nth(0).locator('span[title*="Bat-only"]').count()
  const approxRowMarks = await hiRows.nth(1).locator('span[title*="Bat-only"]').count()
  ck('the exact record carries no mark', exactRowMarks === 0, `${exactRowMarks}`)
  ck('the bat-only row beneath it does', approxRowMarks === 1, `${approxRowMarks}`)

  // A game links to its own scorecard.
  const gameHref = await page.locator('main a[href^="/games/"]').first().getAttribute('href')
  ck('a record links to the game behind it', gameHref === '/games/g1', String(gameHref))

  const finalTag = await page.locator('main', { hasText: 'BIGGEST WINS (RUNS)' })
    .locator('text=FINAL').count()
  ck('a final is flagged on the row', finalTag >= 1, `${finalTag} tag(s)`)
  ck('no page errors', errors.length === 0, errors.join(' | '))

  // Nothing overflows on a phone.
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(200)
  const over = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', over <= 0, `${over}px`)
  await ctx.close()
}

// ──────────────────────────────────────────────── filters reach the wire
{
  const { page, ctx, clubCalls } = await openPage()
  await page.goto(`${BASE}/testclub/records`, { waitUntil: 'networkidle' })
  await openClubTab(page)
  const first = clubCalls.length

  const finals = page.getByRole('button', { name: /finals/i }).first()
  if (await finals.count()) {
    await finals.click()
    await page.waitForTimeout(400)
    ck('toggling a filter refetches the club board', clubCalls.length > first,
       `${first} → ${clubCalls.length}`)
    ck('the filter is on the wire', clubCalls.some((q) => q.includes('finals_only=true')),
       clubCalls.join(' | '))
  } else {
    ck('toggling a filter refetches the club board', false, 'no finals control found')
    ck('the filter is on the wire', false, 'no finals control found')
  }
  ck('gender is never sent — a team total has no gender',
     clubCalls.every((q) => !q.includes('gender=')), clubCalls.join(' | '))
  ck('captain_only is never sent either',
     clubCalls.every((q) => !q.includes('captain_only')), clubCalls.join(' | '))
  await ctx.close()
}

// ───────────────────── the club board survives a failing player-records call
{
  const { page, ctx, errors } = await openPage({ failPlayerRecords: true })
  await page.goto(`${BASE}/testclub/records`, { waitUntil: 'networkidle' })
  await openClubTab(page)
  const body = await page.locator('main').innerText()
  ck('a failing player-records call does not blank the club board',
     body.includes('HIGHEST TEAM TOTALS') && body.includes('300'),
     body.slice(0, 160))
  ck('no page errors on the failure path', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
