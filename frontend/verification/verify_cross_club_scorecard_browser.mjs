// Drives the REAL match page in Chromium with the API stubbed at the network layer:
// a game between two BetterCricket clubs (Alpha v Bravo).
//   * the request on the wire is the scorecard call
//   * Bravo's batters and bowler link to their own profiles; a Bravo player with no
//     id (one Bravo does not hold) stays plain text
//   * both side names in the header and on each innings card link to that club's page
//   * a side with no club_slug (an older payload, or a club not on BetterCricket)
//     reads as plain text, as before
//   * 390px: no sideways overflow
//
//   npx vite build --outDir /tmp/xclub-dist && npx vite preview --outDir /tmp/xclub-dist --port 5199 &
//   APP_URL=http://localhost:5199 node verification/verify_cross_club_scorecard_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOT = process.env.SHOT_DIR || null
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}

const GAME = '97e4fbfe-0000-4000-8000-000000000001'
const A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const bat = (id, name, runs, extra = {}) => ({
  innings_number: extra.inn || 1, player_id: id, player_name: name, runs, balls: runs + 4, fours: 1, sixes: 0,
  strike_rate: null, dismissal_type: 'b Someone', caught_behind: false, not_out: false,
  batting_position: extra.pos || 1, did_not_bat: false,
})
const bowl = (id, name, inn) => ({ innings_number: inn, player_id: id, player_name: name, overs: 4, maidens: 0, runs: 18, wickets: 2, wides: 0, no_balls: 0, economy: 4.5 })

const card = (withSlugs) => ({
  id: GAME, home_team: 'Alpha 1sts', away_team: 'Bravo 1sts', home_away_known: true, is_manual: false,
  innings_order_known: true, played_at: '2026-11-21', result: 'WIN', winning_team: 'Alpha 1sts',
  organisation_id: A, grade: { id: 'g', name: '1st Grade', raw_name: '1st Grade' }, season: { id: 's', name: '2026/27' },
  innings_totals: {
    1: { runs: 60, wickets: 2, extras: 4, overs: 20, batting_team: 'Alpha 1sts', logo_url: null, ...(withSlugs ? { club_slug: 'alpha' } : {}) },
    2: { runs: 40, wickets: 2, extras: 2, overs: 20, batting_team: 'Bravo 1sts', logo_url: null, ...(withSlugs ? { club_slug: 'bravo' } : {}) },
  },
  batting: [bat('pa-1', 'Adam Archer', 40, { pos: 1 }), bat('pa-2', 'Alan Apple', 20, { pos: 2 })],
  bowling: [bowl('pa-1', 'Adam Archer', 2)],
  opp_batting: [bat('pb-1', 'Ben Baker', 30, { inn: 2, pos: 1 }), bat(null, 'Z Stranger', 10, { inn: 2, pos: 2 })],
  opp_bowling: [bowl('pb-9', 'Bert Bowles', 1)],
  fielding: [], fall_of_wickets: [], partnerships: [],
})

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: SHOT ? 2 : 1 })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const wire = []
  let payload = card(true)

  await page.route('**/api/**', (r) => json(r, {}))
  await page.route(/\/api\/games\/[^/]+\/scorecard(\?.*)?$/, (r) => { wire.push(r.request().url()); return json(r, payload) })
  await page.route(/\/api\/organisations\/[^/?]+$/, (r) => json(r, { id: A, slug: 'alpha', name: 'Alpha Cricket Club', is_active: true }))

  const open = async (p) => {
    payload = p
    await page.goto(`${BASE}/games/${GAME}`)
    await page.locator('a[href="/players/pa-1"]').first().waitFor()
  }

  console.log('\n[1] Alpha v Bravo, both on BetterCricket')
  await open(card(true))
  check('the scorecard request went out', wire.some(u => u.includes(`/api/games/${GAME}/scorecard`)), wire.join(' '))
  check('Bravo batter links to their profile', await page.locator('a[href="/players/pb-1"]').count() > 0)
  check('Bravo bowler links to their profile', await page.locator('a[href="/players/pb-9"]').count() > 0)
  check("Alpha's own batter still links", await page.locator('a[href="/players/pa-1"]').count() > 0)
  check('a Bravo player with no id is plain text',
    await page.locator('a', { hasText: 'Stranger' }).count() === 0 && await page.getByText(/Stranger/).count() > 0)
  check("Bravo's name links to Bravo's club page (header and card)", await page.locator('a[href="/bravo"]').count() === 2)
  check("Alpha's name links to Alpha's club page (header and card)", await page.locator('a[href="/alpha"]').count() === 2)
  if (SHOT) await page.screenshot({ path: `${SHOT}/cross-club-desktop.png`, fullPage: false })

  await page.locator('a[href="/players/pb-1"]').first().click()
  await page.waitForURL(/\/players\/pb-1$/)
  check('clicking a Bravo player lands on their profile route', page.url().endsWith('/players/pb-1'))

  console.log('\n[2] Older payload with no club_slug')
  await open(card(false))
  check('no club-page links without a club_slug', await page.locator('[data-testid="club-link"]').count() === 0)
  check('...the side names still show', await page.getByText('Bravo 1sts').count() > 0)

  console.log('\n[3] 390px')
  await page.setViewportSize({ width: 390, height: 844 })
  await open(card(true))
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check('no sideways overflow at 390px', overflow <= 0, `overflow ${overflow}px`)
  if (SHOT) await page.screenshot({ path: `${SHOT}/cross-club-390.png`, fullPage: false })

  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run()
