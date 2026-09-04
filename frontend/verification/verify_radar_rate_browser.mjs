// Drives the player profile's Analysis → Profile radar in Chromium with the
// API stubbed at the network layer.
//
//   npx vite --port 5198 &
//   node frontend/verification/verify_radar_rate_browser.mjs [baseUrl]
//
// Reported off Darren Hind's profile: the radar read a strike rate of 320.19
// beside an innings history where most rows record no balls faced at all. The
// card was the one figure on the page still worked out in the browser as
// SUM(runs) / SUM(balls) over every innings drawn beneath it — all the runs
// over some of the balls, the exact shape services/rate_coverage.py exists to
// stop us publishing. The career header two inches above it had already
// worked the figure out correctly.
//
// So the checks are: the radar reads the SERVER's figure, it is marked when
// short, it says so underneath, and a fully-covered player gets neither mark
// nor note — a note on every rate in the app is noise that trains people to
// stop reading it.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const PID = 'aaaaaaaa-0000-0000-0000-0000000000aa'
const ORG = 'bbbbbbbb-0000-0000-0000-0000000000bb'

// 125 innings of 20. Only 25 carry a ball count, at 20 off 20 — a real strike
// rate of 100. Summing both halves separately gives 2500 / 500 = 500.00, so
// the two answers are impossible to confuse in a check.
const INNINGS = Array.from({ length: 125 }, (_, i) => ({
  runs: 20, balls: i < 25 ? 20 : null, fours: 2, sixes: 0,
  not_out: false, strike_rate: null, dismissal_type: 'bowled',
  batting_position: 3, innings_number: 1,
  game_id: `gggggggg-0000-0000-0000-${String(i).padStart(12, '0')}`,
  home_team: 'Our Club', away_team: 'Them', played_at: '2025-11-01',
  result: 'WIN', grade_name: '1st Grade', season_name: 'Summer 2025/26',
  season_year: 2025,
}))

const base = (over) => ({
  player: { id: PID, name: 'Hind, Darren', display_name: 'Hind, Darren',
            organisation_id: ORG, claimed: false, photo_url: null,
            is_overseas: false, overseas_country: null },
  career_batting: {
    player_id: PID, name: 'Hind, Darren', organisation_id: ORG,
    innings: 125, total_runs: 2500, high_score: 104, average: 20.0,
    // What the server works out from the innings that can answer it.
    strike_rate: 100.0,
    strike_rate_coverage: { counted: 25, of: 125, complete: false, none: false,
                            basis: 'innings' },
    fifties: 9, hundreds: 1, ducks: 4, total_fours: 250, total_sixes: 0,
    games: 150,
  },
  career_bowling: {
    player_id: PID, total_wickets: 17, average: 23.71, economy: 4.98,
    economy_coverage: { counted: 12, of: 12, complete: true, none: false,
                        basis: 'innings' },
    best_figures_wickets: 3, best_bowling_figures: '3/28', total_maidens: 4,
    total_overs: 80.0, total_runs: 403, five_fors: 0,
    bowling_strike_rate: 28.5, games: 150,
  },
  career_fielding: { total_catches: 60, total_stumpings: 3, total_run_outs: 10,
                     total_dismissals: 73 },
  batting_innings: INNINGS, bowling_spells: [],
  grade_scope: { categories: [], excluded_categories: [], formats: null,
                 competitions: null, competition_names: [], active: false,
                 category_active: false, format_active: false,
                 competition_active: false, available: ['senior'],
                 available_competitions: [], auto_shown: false },
  ...over,
})

// The reported player.
const PARTIAL = base({})

// Every innings ball-counted: the same card with nothing to say.
const COMPLETE = base({})
COMPLETE.batting_innings = INNINGS.map(r => ({ ...r, balls: 20 }))
COMPLETE.career_batting = { ...PARTIAL.career_batting, strike_rate: 100.0,
  strike_rate_coverage: { counted: 125, of: 125, complete: true, none: false,
                          basis: 'innings' } }

// A club whose history predates the ball-count era entirely: nothing to
// re-derive from, so the aggregate stands and names itself.
const AGGREGATE = base({})
AGGREGATE.batting_innings = INNINGS.map(r => ({ ...r, balls: null }))
AGGREGATE.career_batting = { ...PARTIAL.career_batting, strike_rate: 62.5,
  strike_rate_coverage: { counted: 0, of: 125, complete: false, none: true,
                          basis: 'aggregate' } }

// The bowling half short instead, so the economy row carries the mark.
const BOWL_SHORT = base({})
BOWL_SHORT.career_batting = COMPLETE.career_batting
BOWL_SHORT.batting_innings = COMPLETE.batting_innings
BOWL_SHORT.career_bowling = { ...PARTIAL.career_bowling,
  economy_coverage: { counted: 5, of: 12, complete: false, none: false,
                      basis: 'innings' } }

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(stats, { width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1600 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  // Routed by REGEX: Playwright's `**` glob does not cross a `?`, so a glob
  // silently loses `/stats?categories=…` to the catch-all and hands the page
  // an empty object, which takes it down a long way from the route at fault.
  await page.route(/\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    if (/\/players\/[^/]+\/stats$/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
                             body: JSON.stringify(stats) })
    }
    if (/^\/auth\/me/.test(path)) return route.fulfill({ status: 401, body: '{}' })
    if (/\/organisations\/[^/]+\/seasons$/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify([{ id: 'dddddddd-0000-0000-0000-0000000000dd',
                                name: 'Summer 2025/26', year: 2025 }]) })
    }
    // The profile fans out to ~20 endpoints and most of them return a LIST. A
    // stub answering `{}` everywhere takes the page down on the first
    // `x is not iterable`, and a broken page measures nothing.
    const obj = /team-breakdown|grade-categories|captain-stats|self-serve|usage/.test(path)
    return route.fulfill({ status: 200, contentType: 'application/json',
                           body: obj ? '{}' : '[]' })
  })
  await page.goto(`${BASE}/players/${PID}`, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'ANALYSIS', exact: true }).click()
  await page.waitForSelector('text=PLAYER PROFILE', { timeout: 15000 })
  return { page, ctx, errors }
}

// One radar row, read off the row itself. A check scoped to the whole card
// would match the career strip above it, which also prints a strike rate.
const readAxis = (page, axis) => page.evaluate((wanted) => {
  for (const row of document.querySelectorAll('div.flex.items-center.gap-3')) {
    const label = row.querySelector('span.uppercase')
    if (!label || label.textContent.trim().toUpperCase() !== wanted) continue
    const fig = row.querySelector('.pb-num')
    return {
      figure: (fig?.textContent || '').replace(/[\s ]/g, '').replace('†', ''),
      marked: (fig?.textContent || '').includes('†'),
    }
  }
  return null
}, axis.toUpperCase())

const cardText = (page) => page.evaluate(() => {
  for (const el of document.querySelectorAll('.pb-card')) {
    if (/PLAYER PROFILE/.test(el.innerText || '')) {
      return (el.innerText || '').replace(/\s+/g, ' ').trim()
    }
  }
  return ''
})

try {
  console.log('\n-- the reported case: most innings recorded no balls faced --')
  {
    const { page, ctx, errors } = await open(PARTIAL)
    const sr = await readAxis(page, 'Strike Rt')
    ck('the Strike Rt row is found at all', !!sr, JSON.stringify(sr))
    ck('it reads the server\'s 100.00', sr?.figure === '100.00', JSON.stringify(sr))
    ck('NOT the 500.00 the innings below it would give',
       sr?.figure !== '500.00', JSON.stringify(sr))
    ck('the figure is marked as short', sr?.marked === true, JSON.stringify(sr))
    const text = await cardText(page)
    ck('the card says which innings answered it',
       /from 25 of 125 innings/.test(text), text.slice(0, 400))
    ck('and says the data may be incomplete',
       /Data may be incomplete/.test(text), text.slice(0, 400))
    const bat = await readAxis(page, 'Bat Avg')
    ck('the average beside it still counts every innings (20.00)',
       bat?.figure === '20.00', JSON.stringify(bat))
    ck('and carries no mark of its own — it is not a rate',
       bat?.marked === false, JSON.stringify(bat))
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- every innings ball-counted: the card says nothing extra --')
  {
    const { page, ctx, errors } = await open(COMPLETE)
    const sr = await readAxis(page, 'Strike Rt')
    ck('the same 100.00 is drawn', sr?.figure === '100.00', JSON.stringify(sr))
    ck('with no mark', sr?.marked === false, JSON.stringify(sr))
    const text = await cardText(page)
    ck('and no note at all', !/Data may be incomplete/.test(text), text.slice(0, 300))
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- a club with no scorecards behind the figure --')
  {
    const { page, ctx } = await open(AGGREGATE)
    const sr = await readAxis(page, 'Strike Rt')
    ck('the aggregate figure still draws rather than reading blank',
       sr?.figure === '62.50', JSON.stringify(sr))
    ck('marked, because it could not be checked against any innings',
       sr?.marked === true, JSON.stringify(sr))
    const text = await cardText(page)
    ck('and it names where the figure came from',
       /worked out from season totals/.test(text), text.slice(0, 400))
    await ctx.close()
  }

  console.log('\n-- the economy row carries the same treatment --')
  {
    const { page, ctx } = await open(BOWL_SHORT)
    const econ = await readAxis(page, 'Economy')
    ck('the economy reads 4.98', econ?.figure === '4.98', JSON.stringify(econ))
    ck('and is marked when its spells are short', econ?.marked === true,
       JSON.stringify(econ))
    const text = await cardText(page)
    ck('the note counts spells, not innings',
       /from 5 of 12 spells/.test(text), text.slice(0, 400))
    await ctx.close()
  }

  console.log('\n-- and it fits a phone --')
  {
    const { page, ctx } = await open(PARTIAL, { width: 390 })
    const over = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth)
    ck('no horizontal overflow at 390px', over <= 0, `overflow ${over}px`)
    const sr = await readAxis(page, 'Strike Rt')
    ck('the figure and its mark still read', sr?.figure === '100.00' && sr?.marked,
       JSON.stringify(sr))
    await ctx.close()
  }
} finally {
  await browser.close()
}

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
