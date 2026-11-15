/**
 * Drive the public Compare page's bowling tab in a real browser, API stubbed.
 *
 * Reported at Applecross (Nov 2026): the bowling tab had no overs, showed best
 * figures as a bare wicket count ("5"), and had no wides, no-balls or extras.
 *
 * What the stub below makes the page prove:
 *   - OVERS are worked out from balls bowled (1310 balls = 218.2), not from the
 *     decimal-summed `total_overs` (220), and carry no green or red.
 *   - BEST FIGURES read as the spell ("5/28"), accept the hyphen the season-total
 *     path sends ("3-21"), and fall back to "4 wkts" when only a count is known.
 *     Wickets rank first and fewest runs breaks a tie.
 *   - WIDES, NO BALLS and EXTRAS (wides + no-balls) show a dash, not a flattering
 *     zero, for a player whose extras were never counted, and that player is
 *     left out of the green and red.
 *   - The page asks for each player's stats, and for the last 3 games when picked.
 *
 * Run against a served build:  node verification/verify_compare_bowling_browser.mjs [baseUrl]
 * (build with `npx vite build`, serve with `npx vite preview --port 4173`)
 * Control: run it against a build of the previous commit; it must fail the rows
 * it asserts, not crash.
 */
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:4173'
const pass = [], fail = []
const check = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  ;(ok ? pass : fail).push(label)
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}: ${JSON.stringify(got)}${ok ? '' : ` (wanted ${JSON.stringify(want)})`}`)
}
const json = (route, body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const PLAYERS = [
  { id: 'p-sakun', name: 'Dissanayake, Sakun', display_name: 'Sakun Dissanayake', player_role: 'Bowler' },
  { id: 'p-jack', name: 'Barendse, Jack', display_name: 'Jack Barendse', player_role: 'All Rounder' },
  { id: 'p-simon', name: 'Shub, Simon', display_name: 'Simon Shub', player_role: 'All Rounder' },
]
const BOWLING = {
  'p-sakun': {
    total_wickets: 41, total_runs: 1015, average: 24.76, economy: 4.8, bowling_strike_rate: 30.98,
    best_bowling_figures: '5/28', best_figures_wickets: 5, five_fors: 1, total_maidens: 15,
    total_overs: 220.0, total_balls: 1310, total_wides: 20, total_no_balls: 5,
  },
  'p-jack': {
    total_wickets: 34, total_runs: 522, average: 15.35, economy: 3.1, bowling_strike_rate: 23.03,
    best_bowling_figures: '3-21', best_figures_wickets: 3, five_fors: 0, total_maidens: 12,
    total_overs: 170.0, total_balls: 1004, total_wides: 30, total_no_balls: 2,
  },
  'p-simon': {
    total_wickets: 52, total_runs: 888, average: 17.08, economy: 4.19, bowling_strike_rate: 24.46,
    best_bowling_figures: null, best_figures_wickets: 4, five_fors: 0, total_maidens: 18,
    total_overs: 200.0, total_balls: 1200, total_wides: null, total_no_balls: null,
  },
}

const statsRequests = []
const errors = []
const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {})
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
page.on('pageerror', e => errors.push(String(e)))

await page.route('**/api/**', async route => {
  const url = new URL(route.request().url())
  const path = url.pathname.replace(/^.*\/api/, '')
  const m = path.match(/^\/players\/([^/]+)\/stats$/)
  if (m) {
    statsRequests.push({ id: m[1], ...Object.fromEntries(url.searchParams) })
    return json(route, {
      player: PLAYERS.find(p => p.id === m[1]),
      career_batting: {}, career_bowling: BOWLING[m[1]], career_fielding: {},
    })
  }
  if (path === '/players') return json(route, PLAYERS)
  if (path.endsWith('/seasons')) return json(route, [])
  if (path.endsWith('/sponsors')) return json(route, [])
  if (path.endsWith('/grade-categories')) return json(route, { available: [], default: [], available_formats: [], available_competitions: [] })
  if (path.startsWith('/clubs/')) return json(route, { id: 'o1', name: 'Applecross CC', slug: 'applecross', is_active: true })
  if (path.startsWith('/organisations/')) return json(route, { id: 'o1', name: 'Applecross CC', slug: 'applecross' })
  return json(route, {})
})

await page.goto(`${BASE}/applecross/compare`)
const search = page.getByPlaceholder('Add player…')
for (const p of PLAYERS) {
  await search.click()
  await search.fill(p.name.split(',')[0])
  await page.getByRole('button', { name: p.name }).click()
}
await page.getByRole('button', { name: 'BOWLING', exact: true }).click()
await page.waitForSelector('tbody tr')

const rows = async () => page.evaluate(() => {
  const out = {}
  document.querySelectorAll('tbody tr').forEach(tr => {
    const tds = [...tr.querySelectorAll('td')]
    const colour = td => {
      const bg = td.style.background || ''
      return bg.includes('34, 197, 94') ? 'best' : bg.includes('239, 68, 68') ? 'worst' : ''
    }
    out[tds[0].textContent.trim()] = tds.slice(1).map(td => `${td.textContent.trim()}${colour(td) ? ' ' + colour(td) : ''}`)
  })
  return out
})
const r = await rows()

check('every player is asked for their stats', statsRequests.map(s => s.id).sort(), ['p-jack', 'p-sakun', 'p-simon'])
check('the all-time request carries no window', statsRequests.every(s => Object.keys(s).length === 1), true)
check('the table lists the new rows',
  ['OVERS', 'RUNS CONCEDED', 'BEST FIGURES', 'WIDES', 'NO BALLS', 'EXTRAS'].every(k => k in r), true)
check('OVERS come from balls bowled (218.2, 167.2, 200), not the decimal sum, and are not coloured',
  r['OVERS'], ['218.2', '167.2', '200'])
check('RUNS CONCEDED shows and is not coloured', r['RUNS CONCEDED'], ['1,015', '522', '888'])
check('BEST FIGURES read as the spell; a bare count says wkts; 5/28 is best, 3/21 worst',
  r['BEST FIGURES'], ['5/28 best', '3/21 worst', '4 wkts'])
check('WIDES: a dash for the uncounted player, who is left out of the colours',
  r['WIDES'], ['20 best', '30 worst', '—'])
check('NO BALLS the same', r['NO BALLS'], ['5 worst', '2 best', '—'])
check('EXTRAS add the two (25, 32) and dash the uncounted player',
  r['EXTRAS'], ['25 best', '32 worst', '—'])
check('the rows already there are unchanged (wickets, average)',
  [r['WICKETS'], r['BOWLING AVG']], [['41', '34 worst', '52 best'], ['24.76 worst', '15.35 best', '17.08']])
check('the note about uncounted extras is on the tab',
  await page.getByText('Wides and no balls only count where the scorer recorded them').count(), 1)

await page.getByRole('button', { name: 'Last 3 Games' }).click()
await page.waitForFunction(() => document.querySelectorAll('tbody tr').length > 0)
await page.waitForTimeout(300)
check('picking Last 3 Games asks for last_n_games=3 for each player',
  statsRequests.filter(s => s.last_n_games === '3').map(s => s.id).sort(), ['p-jack', 'p-sakun', 'p-simon'])

await page.screenshot({ path: process.env.SHOT || '/tmp/claude-0/compare-bowling-1280.png', fullPage: true, })
await page.setViewportSize({ width: 390, height: 900 })
await page.waitForTimeout(200)
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
check('no horizontal PAGE overflow at 390px (the table scrolls inside its card)', overflow <= 0, true)
check('no page errors', errors, [])
await page.screenshot({ path: (process.env.SHOT || '/tmp/claude-0/compare-bowling').replace(/\.png$/, '') + '-390.png', fullPage: true })

await browser.close()
console.log(`\n${pass.length} passed, ${fail.length} failed`)
process.exit(fail.length ? 1 : 0)
