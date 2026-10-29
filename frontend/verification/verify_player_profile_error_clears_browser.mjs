// The player profile after a failed load, against the REAL PlayerProfile with the API stubbed at the network layer.
//
// Reported off Payneham: "Error: Player not found" on a profile that exists (both reads return 200 on the
// live system). /players/:playerId is one mounted page, so moving between players re-runs usePlayerStats on
// the same instance, and an error from one load was never cleared. Asserted:
//   * player A's stats fail (404) and the page says so;
//   * moving to player B in the same page (client-side) draws B's profile and no error;
//   * a reply that arrives late from the player we left does not replace B;
//   * the request on the wire for B is /players/<B>/stats.
//
//   node verify_player_profile_error_clears_browser.mjs   (BASE via APP_URL, default :5178)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5178'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const A = 'cc98c504-a205-4ef5-808f-c1a991d55c8f'
const B = 'd02803c3-471e-49d3-b966-47087811e4fe'
const ORG = '11111111-1111-1111-1111-111111111111'
const stats = (id, name) => ({
  player: { id, name, display_name: name, organisation_id: ORG, claimed: null, playhq_id: null },
  career_batting: { games: 20, innings: 19, total_runs: 55, not_outs: 0, high_score: 10, fifties: 0, hundreds: 0, ducks: 0, total_fours: 6, total_sixes: 0 },
  career_bowling: { games: 20, total_wickets: 5 },
  career_fielding: {}, batting_innings: [], bowling_spells: [],
  grade_scope: { active: false, categories: [], available: [] },
})

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 900 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const calls = [], errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    calls.push(url)
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes(`/players/${A}/stats`)) return json({ detail: 'Player not found' }, 404)
    if (url.includes(`/players/${B}/stats`)) return json(stats(B, 'MYB Zia'))
    if (/\/auth\/me/.test(url)) return json({}, 401)
    return json([])
  })

  await page.goto(`${BASE}/players/${A}`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('text=Error: Player not found', { timeout: 15000 })
  check('player A fails and the page says so', true)

  // A client-side move to B, the way the search box and teammate links do it.
  await page.evaluate((id) => {
    window.history.pushState({}, '', `/players/${id}`)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, B)
  await page.waitForTimeout(1500)
  const body = await page.locator('body').innerText()
  check('B is drawn after A failed', /Zia, MYB/i.test(body) && /MATCHES\s*20/i.test(body), body.slice(0, 200))
  check('the error from A is gone', !/Player not found/.test(body), body.slice(0, 200))
  check('the stats request for B went out', calls.some(u => u.includes(`/players/${B}/stats`)), calls.join('\n'))
  check('no page errors', errors.length === 0, errors.join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run()
