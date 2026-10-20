/**
 * Drive the public Players page in a real browser.
 *
 * Reported at Applecross: three players who have played 1, 4 and 12 games sat in
 * the list with every figure a dash. The page reads two leaderboards, and a
 * leaderboard drops anyone under the club's "fewest innings before a rate is
 * shown" bar, so a roster that borrows it loses those players. The stub below
 * behaves the way the server does: leave `min_rate_innings` off and the club's
 * own bar (3) applies; send it and that value is used, 0 meaning off.
 *
 * Also checks M: a bowler who never batted has no batting row, so the games
 * figure has to come from the bowling one.
 *
 * Run against a served build:  node scripts/verify-players-page.mjs [baseUrl]
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

const CLUB_BAR = 3 // the club's own "fewest innings with a ball count" setting
const PLAYERS = [
  { id: 'p-elson', name: 'Elson, J', display_name: 'J Elson' },
  { id: 'p-brad', name: 'Ethell, Brad', display_name: 'Brad Ethell' },
  { id: 'p-sam', name: 'Ethell, Samual', display_name: 'Samual Ethell' },
  { id: 'p-reg', name: 'Regular, Rob', display_name: 'Rob Regular' },
]
// Batting board rows, each with how many innings had a ball count behind them.
const BATTING = [
  { player_id: 'p-brad', games: 4, innings: 3, total_runs: 41, average: 13.7, high_score: 22, fifties: 0, sr_counted: 2 },
  { player_id: 'p-sam', games: 12, innings: 10, total_runs: 160, average: 17.8, high_score: 48, fifties: 0, sr_counted: 2 },
  { player_id: 'p-reg', games: 30, innings: 28, total_runs: 900, average: 36, high_score: 101, fifties: 5, sr_counted: 28 },
]
// J Elson bowled one spell and never batted: a bowling row, no batting row.
const BOWLING = [
  { player_id: 'p-elson', games: 1, total_wickets: 0, best_bowling_figures: '0-5', spells_counted: 1 },
  { player_id: 'p-reg', games: 30, total_wickets: 20, best_bowling_figures: '4-20', spells_counted: 30 },
]

const requests = { batting: [], bowling: [] }

const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {})
const page = await browser.newPage({ viewport: { width: 390, height: 900 } })
const errors = []
page.on('pageerror', e => errors.push(String(e)))

await page.route('**/api/**', async route => {
  const url = new URL(route.request().url())
  const path = url.pathname.replace(/^.*\/api/, '')
  const q = url.searchParams
  if (path.startsWith('/leaderboard/batting')) {
    requests.batting.push(Object.fromEntries(q))
    const asked = q.get('min_rate_innings')
    const bar = asked == null ? CLUB_BAR : Number(asked)
    return json(route, BATTING.filter(r => r.sr_counted >= bar))
  }
  if (path.startsWith('/leaderboard/bowling')) {
    requests.bowling.push(Object.fromEntries(q))
    return json(route, BOWLING)
  }
  if (path.startsWith('/players')) return json(route, PLAYERS)
  if (path.endsWith('/sponsors')) return json(route, [])
  if (path.endsWith('/grade-categories')) return json(route, { available: [], default: [], available_formats: [], available_competitions: [] })
  if (path.endsWith('/seasons')) return json(route, [])
  if (path.startsWith('/organisations/')) return json(route, { id: 'o1', name: 'Applecross CC', slug: 'applecross' })
  if (path.startsWith('/clubs/')) return json(route, { id: 'o1', name: 'Applecross CC', slug: 'applecross', is_active: true })
  return json(route, {})
})

await page.goto(`${BASE}/applecross/players`)
try {
  await page.waitForSelector('text=Elson, J', { timeout: 15000 })
} catch (e) {
  console.log('page text:', (await page.innerText('body')).replace(/\n/g,' ').slice(0, 700), '\nerrors:', errors)
  throw e
}

// Wait for both boards to have answered and painted.
await page.waitForFunction(() => document.body.innerText.includes('900'))

check('the batting board is asked for every player, bar switched off', requests.batting.at(-1)?.min_rate_innings, '0')
check('and the bowling board', requests.bowling.at(-1)?.min_rate_spells, '0')

// Read each mobile card's five-up stat grid as label -> value.
const cards = await page.evaluate(() => {
  const out = {}
  document.querySelectorAll('.md\\:hidden a').forEach(a => {
    const name = a.querySelector('span')?.textContent?.trim()
    const stats = {}
    a.querySelectorAll('.grid > div').forEach(d => {
      const [v, l] = [...d.querySelectorAll('span')].map(s => s.textContent.trim())
      stats[l] = v
    })
    out[name] = stats
  })
  return out
})
check('Brad Ethell: 4 matches', cards['Ethell, Brad']?.M, '4')
check('Samual Ethell: 12 matches', cards['Ethell, Samual']?.M, '12')
check('J Elson, who only bowled: 1 match', cards['Elson, J']?.M, '1')
check('and his bowling figures stand', cards['Elson, J']?.BEST, '0/5')
check('a regular is unchanged', [cards['Regular, Rob']?.M, cards['Regular, Rob']?.RUNS], ['30', '900'])

const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
check('no horizontal overflow at 390px', overflow <= 0, true)
check('no page errors', errors, [])

await page.screenshot({ path: process.env.SHOT || '/tmp/claude-0/players-390.png', fullPage: true })
await browser.close()
console.log(`\n${pass.length} passed, ${fail.length} failed`)
process.exit(fail.length ? 1 : 0)
