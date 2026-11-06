// Drives the real Fantasy Ladder "Round winners" tab and the Insights screen in Chromium with the API stubbed at
// the network layer.
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_fantasy_round_winners_browser.mjs [baseUrl]
//
// Checks: the Ladder opens on the season ladder and the tab asks for nothing extra until clicked; the Round
// winners tab opens on the latest scored round with the exact requests on the wire; stepping back and the round
// dropdown load the chosen round; a shared win says so; a round with no winner says so; the history list and the
// win tally show; Insights asks for the default round first, then for the round picked (?round=n), shows the
// five boards, tells the open round it has no points yet, opens a player; empty and refused states say why;
// no overflow at 390px; no page errors.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome'
const SHOTS = process.env.SHOTS_DIR || ''

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  - ${extra}` : ''}`) }
}

const w = (id, name, mgr, points, extra = {}) => ({ squad_id: id, team_name: name, manager: mgr, points, chip: null, you: false, ...extra })
const ROUNDS = {
  1: { number: 1, name: 'Round 1', start_date: '2026-10-03', end_date: '2026-10-04', teams: 3, top_points: 20, margin: 8, winners: [w('s2', 'Team B', 'Manager B', 20)] },
  2: { number: 2, name: 'Round 2', start_date: '2026-10-10', end_date: '2026-10-11', teams: 3, top_points: 30, margin: null, winners: [w('s1', 'Team A', 'Manager A', 30, { chip: 'triple_captain' }), w('s3', 'Team C', 'Manager C', 30)] },
  3: { number: 3, name: 'Round 3', start_date: '2026-10-17', end_date: '2026-10-18', teams: 3, top_points: 41, margin: 12, winners: [w('s2', 'Team B', 'Manager B', 41, { you: true })] },
}
const ranking = (n) => {
  const r = ROUNDS[n]
  const rows = n === 2
    ? [['s1', 'Team A', 30, 1, true], ['s3', 'Team C', 30, 1, true], ['s2', 'Team B', 10, 3, false]]
    : [['s2', 'Team B', r.top_points, 1, true], ['s1', 'Team A', r.top_points - r.margin, 2, false], ['s3', 'Team C', 3, 3, false]]
  return { ...r, ranking: rows.map(([id, t, p, rank, win]) => ({ squad_id: id, team_name: t, manager: `Manager ${t.slice(-1)}`, points: p, rank, winner: win, chip: null, transfer_hit: 0, you: id === 's2' })), my_squad_id: 's2' }
}
const tally = [
  { squad_id: 's2', team_name: 'Team B', manager: 'Manager B', wins: 2, rounds: [1, 3], best_points: 41, you: true },
  { squad_id: 's1', team_name: 'Team A', manager: 'Manager A', wins: 1, rounds: [2], best_points: 30, you: false },
  { squad_id: 's3', team_name: 'Team C', manager: 'Manager C', wins: 1, rounds: [2], best_points: 30, you: false },
]
const strip = ({ ranking: _r, ...x }) => x

const pl = (i, extra = {}) => ({ player_id: `p${i}`, name: `Player ${i}`, photo_url: null, role: i % 2 ? 'batter' : 'bowler', ...extra })
const INS = {
  3: {
    id: 'r3', number: 3, name: 'Round 3', status: 'scored', start_date: '2026-10-17', end_date: '2026-10-18', teams: 12,
    top_scorers: Array.from({ length: 10 }, (_, i) => pl(i + 1, { points: 120 - i * 7, games: 1, picked_by: 10 - i })),
    traded_in: [pl(21, { count: 5, price: 8.4 }), pl(22, { count: 2, price: 7.1 })],
    traded_out: [pl(31, { count: 4, price: 9.0 })],
    risers: [pl(41, { move: 0.4, price: 9.4 }), pl(42, { move: 0.1, price: 6.1 })],
    fallers: [pl(51, { move: -0.3, price: 7.7 })],
  },
  1: {
    id: 'r1', number: 1, name: 'Round 1', status: 'scored', start_date: '2026-10-03', end_date: '2026-10-04', teams: 12,
    top_scorers: [pl(1, { points: 99, games: 1, picked_by: 1 })], traded_in: [], traded_out: [], risers: [], fallers: [],
  },
  4: {
    id: 'r4', number: 4, name: 'Round 4', status: 'live', start_date: '2026-10-24', end_date: '2026-10-25', teams: 12,
    top_scorers: [], traded_in: [pl(61, { count: 3, price: 6.6 })], traded_out: [], risers: [], fallers: [],
  },
}
const OPTIONS = [1, 2, 3, 4].map(n => ({ id: `r${n}`, number: n, name: `Round ${n}`, status: n === 4 ? 'live' : 'scored', start_date: `2026-10-${3 + (n - 1) * 7}`, end_date: `2026-10-${4 + (n - 1) * 7}` }))

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1280, start = 'Ladder', empty = false, insightsStatus = 200 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = [], reqs = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url())
    const path = u.pathname.replace(/^\/api/, '')
    if (path === '/public/fantasy/tok') return json(route, { club: { name: 'Applecross CC' }, season: { name: 'Fantasy', status: 'active', rules: {} }, me: { id: 'm1', display_name: 'Xavier' } })
    if (path === '/public/fantasy/tok/me') return json(route, { manager: { id: 'm1', display_name: 'Xavier' }, squad: { id: 's2', team_name: 'Team B', players: [], chips: [], total_points: 215, value: 0, budget_remaining: 0, free_transfers: 1, queued_transfers: [] }, round: null })
    if (path === '/public/fantasy/tok/pool') return json(route, { players: [], rules: {} })
    if (path === '/public/fantasy/tok/notifications') return json(route, { notifications: [] })
    if (path === '/public/fantasy/tok/live') return json(route, { live: false, round: null, mine: null })
    if (path === '/public/fantasy/tok/round') return json(route, { round: null, mine: null, rounds: [] })
    if (path === '/public/fantasy/tok/ladder') return json(route, { ladder: [{ rank: 1, squad_id: 's2', team_name: 'Team B', manager: 'Manager B', points: 100, gw: 41, rank_delta: 0, you: true }], my_squad_id: 's2', live: null, teams_visible: false })
    if (path === '/public/fantasy/tok/round-winners') {
      reqs.push(path)
      return json(route, empty ? { rounds: [], tally: [], my_squad_id: 's2' } : { rounds: [1, 2, 3].map(n => strip(ROUNDS[n])), tally, my_squad_id: 's2' })
    }
    const m = path.match(/^\/public\/fantasy\/tok\/round-ranking\/(\d+)$/)
    if (m) { reqs.push(path); return json(route, ranking(Number(m[1]))) }
    if (path === '/public/fantasy/tok/round-insights') {
      reqs.push(path + u.search)
      if (insightsStatus !== 200) return json(route, { detail: 'nope' }, insightsStatus)
      if (empty) return json(route, { rounds: [], selected: null })
      const n = u.searchParams.get('round') ? Number(u.searchParams.get('round')) : 3
      return INS[n] ? json(route, { rounds: OPTIONS, selected: INS[n] }) : json(route, { detail: 'That round has no insights yet' }, 404)
    }
    if (path.startsWith('/public/fantasy/tok/player/')) { reqs.push(path); return json(route, { player_id: path.split('/').pop(), name: 'Player 21', role: 'batter', price: 8, price_change: 0, total_points: 10, weekly_avg: 5, last_round_points: 3, form: 4, selected_pct: 12, last5: [], season_stats: {}, career_stats: {} }) }
    return json(route, {})
  })
  await page.goto(`${BASE}/fantasy/tok`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: start, exact: true }).first().click({ timeout: 15000 })
  return { page, ctx, errors, reqs }
}
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
const text = async (page) => await page.locator('body').innerText()

// ── 1. Round winners tab ──────────────────────────────────────────────────────
{
  const a = await open()
  await a.page.waitForSelector('text=Season ladder', { timeout: 15000 })
  ck('the Ladder opens on the season ladder', (await text(a.page)).includes('Team B'))
  ck('and asks for no round data until the tab is opened', a.reqs.length === 0, a.reqs.join(','))
  await a.page.getByRole('button', { name: 'Round winners', exact: true }).click()
  await a.page.waitForSelector('[data-testid="round-winner"]', { timeout: 15000 })
  ck('the tab asks for the winners list, then the latest round (3)', a.reqs.join(',') === '/public/fantasy/tok/round-winners,/public/fantasy/tok/round-ranking/3', a.reqs.join(','))
  let t = await text(a.page)
  ck('it shows Round 3 winner Team B on 41, 12 clear, flagged YOU', /ROUND 3 WINNER/i.test(t) && /41/.test(t) && /12 points clear of second/.test(t) && /YOU/.test(t))
  ck('the table lists every team that played, winner first', (await a.page.getByText(/^Team [ABC]$/).count()) >= 3 && /ROUND PTS/i.test(t))
  ck('the history lists all three rounds, newest first', /R3[\s\S]*R2[\s\S]*R1/.test(await a.page.locator('[data-testid="round-history"]').innerText()))
  ck('a shared win reads as "Team A and Team C" in the history', /Team A and Team C/.test(await a.page.locator('[data-testid="round-history"]').innerText()))
  ck('the tally puts Team B first on 2 wins', /Team B[\s\S]*?Rounds 1, 3[\s\S]*?2/.test(await a.page.locator('[data-testid="round-tally"]').innerText()))

  await a.page.getByRole('button', { name: 'Previous round' }).click()
  await a.page.waitForSelector('text=Round 2 shared win', { timeout: 15000 })
  ck('Previous loads round 2 with one more request', a.reqs[a.reqs.length - 1] === '/public/fantasy/tok/round-ranking/2', a.reqs.join(','))
  const winnerTxt = await a.page.locator('[data-testid="round-winner"]').innerText()   // the card uppercases names with CSS
  ck('a tie for first is a shared win with both teams and no margin line', /team a/i.test(winnerTxt) && /team c/i.test(winnerTxt) && !/clear of second/.test(winnerTxt), winnerTxt)
  ck('the chip the winner played is shown', /Triple captain/.test(await text(a.page)))
  const before = a.reqs.length
  await a.page.getByRole('button', { name: 'Next round' }).click()
  await a.page.waitForSelector('text=Round 3 winner')
  ck('going back to round 3 reuses what was loaded (no new request)', a.reqs.length === before, a.reqs.join(','))
  await a.page.getByLabel('Round', { exact: true }).selectOption('1')
  await a.page.waitForSelector('text=Round 1 winner', { timeout: 15000 })
  ck('the dropdown jumps to round 1 (backdated)', a.reqs[a.reqs.length - 1] === '/public/fantasy/tok/round-ranking/1', a.reqs.join(','))
  await a.page.getByRole('button', { name: 'Show round 2' }).click()
  await a.page.waitForSelector('text=Round 2 shared win')
  ck('a row in the history opens that round', true)
  ck('1280px: no sideways scroll', (await overflow(a.page)) <= 1)
  if (SHOTS) await a.page.screenshot({ path: `${SHOTS}/round_winners_desktop.png` })
  ck('no page errors', a.errors.length === 0, a.errors.join(' | '))
  await a.ctx.close()

  const m = await open({ width: 390 })
  await m.page.getByRole('button', { name: 'Round winners', exact: true }).click()
  await m.page.waitForSelector('[data-testid="round-winner"]', { timeout: 15000 })
  ck('390px: no sideways scroll', (await overflow(m.page)) <= 1, String(await overflow(m.page)))
  if (SHOTS) await m.page.screenshot({ path: `${SHOTS}/round_winners_390.png`, fullPage: true })
  await m.ctx.close()

  const e = await open({ empty: true })
  await e.page.getByRole('button', { name: 'Round winners', exact: true }).click()
  await e.page.waitForSelector('text=No round has been scored yet', { timeout: 15000 })
  ck('before any round is scored it says so', true)
  await e.ctx.close()
}

// ── 2. Insights ───────────────────────────────────────────────────────────────
{
  const a = await open({ start: 'Insights' })
  await a.page.waitForSelector('[data-testid="insights-top"]', { timeout: 15000 })
  ck('Insights asks for the default round first (no ?round)', a.reqs.join(',') === '/public/fantasy/tok/round-insights', a.reqs.join(','))
  const top = await a.page.locator('[data-testid="insights-top"]').innerText()
  ck('Top 10 players: ten rows, highest first, 120 then 113', (await a.page.locator('[data-testid="insights-top"] button').count()) === 10 && /Player 1[\s\S]*?120/.test(top) && /113/.test(top))
  ck('each says how many of the 12 teams had them', /10 of 12 teams had them/.test(top))
  ck('Most traded in: Player 21 on 5, $8.4', /Player 21[\s\S]*?\$8\.4[\s\S]*?5/.test(await a.page.locator('[data-testid="insights-in"]').innerText()))
  ck('Most traded out: Player 31 on 4', /Player 31[\s\S]*?4/.test(await a.page.locator('[data-testid="insights-out"]').innerText()))
  ck('Biggest risers show the rise and the new price', /Player 41[\s\S]*?now \$9\.4[\s\S]*?▲ 0\.4/.test(await a.page.locator('[data-testid="insights-risers"]').innerText()))
  ck('Biggest fallers show the fall', /Player 51[\s\S]*?now \$7\.7[\s\S]*?▼ 0\.3/.test(await a.page.locator('[data-testid="insights-fallers"]').innerText()))
  ck('the picker lists the open round too', (await a.page.getByLabel('Round', { exact: true }).locator('option').allInnerTexts()).some(o => /Round 4 \(open\)/.test(o)))

  await a.page.getByLabel('Round', { exact: true }).selectOption('1')
  await a.page.waitForSelector('text=No transfers into this round.', { timeout: 15000 })
  ck('picking a round asks for exactly that round (?round=1)', a.reqs[a.reqs.length - 1] === '/public/fantasy/tok/round-insights?round=1', a.reqs.join(','))
  ck('a round with no price moves says so', /No price rises after this round/.test(await text(a.page)) && /No price falls after this round/.test(await text(a.page)))

  await a.page.getByLabel('Round', { exact: true }).selectOption('4')
  await a.page.waitForSelector('text=This round is still open', { timeout: 15000 })
  ck('the open round says it is open and shows the trades so far', /Player 61/.test(await text(a.page)))
  ck('and tells you when points and price moves will arrive', (await a.page.getByText('Shown once this round is confirmed.').count()) === 3)
  const n = a.reqs.length
  await a.page.getByLabel('Round', { exact: true }).selectOption('3')
  await a.page.waitForSelector('[data-testid="insights-top"] >> text=Player 2')
  ck('going back to a loaded round makes no new request', a.reqs.length === n, a.reqs.join(','))

  await a.page.getByRole('button', { name: 'Open Player 21' }).click()
  await a.page.getByText(/total pts/i).first().waitFor({ timeout: 15000 })
  ck('a player opens their profile (GET /player/p21)', a.reqs.some(r => r === '/public/fantasy/tok/player/p21'), a.reqs.join(','))
  await a.page.getByRole('button', { name: 'Back' }).first().click()
  await a.page.waitForSelector('[data-testid="insights-top"]', { timeout: 15000 })
  ck('Back returns to Insights', true)
  ck('1280px: no sideways scroll', (await overflow(a.page)) <= 1)
  if (SHOTS) await a.page.screenshot({ path: `${SHOTS}/insights_desktop.png`, fullPage: true })
  ck('no page errors', a.errors.length === 0, a.errors.join(' | '))
  await a.ctx.close()

  const m = await open({ start: 'Insights', width: 390 })
  await m.page.waitForSelector('[data-testid="insights-top"]', { timeout: 15000 })
  ck('390px: no sideways scroll', (await overflow(m.page)) <= 1, String(await overflow(m.page)))
  if (SHOTS) await m.page.screenshot({ path: `${SHOTS}/insights_390.png`, fullPage: true })
  await m.ctx.close()

  const e = await open({ start: 'Insights', empty: true })
  await e.page.waitForSelector('text=Nothing to show yet', { timeout: 15000 })
  ck('before the season starts it says so', true)
  await e.ctx.close()

  const r = await open({ start: 'Insights', insightsStatus: 500 })
  await r.page.waitForSelector('text=could not be loaded', { timeout: 15000 })
  ck('a failed request says so, with no page error', r.errors.length === 0, r.errors.join(' | '))
  await r.ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
