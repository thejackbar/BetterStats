/**
 * Drive BetterIQ's Opposition player profile and check the "Against us" view.
 *
 * The API is stubbed at the network layer. The vs-us stub behaves like the
 * server: `building` on the first call, then the record. Asserts the exact
 * request on the wire (opponent key, player GUID, name, club), the Overview
 * headline, the tab's lists and game log, links to our player pages, 390px
 * overflow, and screenshots at 390 and 1280.
 *
 * Run against a served build:  node scripts/verify-opp-player-vs-us.mjs [baseUrl]
 */
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:5199'
const SHOTS = process.env.SHOTS || '/tmp'
const pass = [], fail = []
const check = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  ;(ok ? pass : fail).push(label)
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}: ${JSON.stringify(got)}${ok ? '' : ` (wanted ${JSON.stringify(want)})`}`)
}
const json = (route, body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const OPP = '5db6ee9f-87d8-eb11-a7ad-2818780da0cc'
const PID = '3f655144-5f0c-4d8a-81c0-0a3a9c7391d4'
const CLUB = 'Western Suburbs Cricket Club'
const BAR = { player_id: PID, name: 'Adam Barwood', matches: 2, innings: 2, runs: 25, not_outs: 1, high_score: '23*', average: 25, strike_rate: 60, recent_scores: ['2', '23*'], vs_us: null }
const DOSSIER = {
  status: 'ready', opponent: { opp_key: OPP, name: CLUB, org_id: OPP },
  coverage: { notes: [] }, batting: [BAR, { ...BAR, player_id: 'x', name: 'Max Mate', runs: 80 }], bowling: [], danger_batters: [], danger_bowlers: [],
  schema_v: 12, built_at: new Date().toISOString(),
}
const VS = {
  status: 'ready', player: { player_id: PID, name: 'Adam Barwood' }, opponent: { opp_key: OPP, name: CLUB },
  us: { name: 'Applecross CC' }, scope: [], games_total: 5, games_checked: 4, games_played: 3,
  batting: { innings: 3, runs: 61, not_outs: 0, average: 20.33, strike_rate: 75.31, high_score: '40', fifties: 0, hundreds: 0, ducks: 0, outs: 3,
    dismissals: [{ type: 'caught', count: 1, pct: 33 }, { type: 'caught behind', count: 1, pct: 33 }, { type: 'bowled', count: 1, pct: 33 }] },
  bowling: { spells: 2, wickets: 2, runs: 39, overs: 13, maidens: 0, average: 19.5, economy: 3, strike_rate: 39, best: '1/14' },
  got_them_out: [
    { player_id: 'our-smith', name: 'Tom Smith', count: 2, wickets: 2, methods: [{ type: 'caught behind', count: 1 }, { type: 'bowled', count: 1 }], last_date: '2026-03-07' },
    { player_id: 'our-white', name: 'Pat White', count: 1, wickets: 1, methods: [{ type: 'caught', count: 1 }], last_date: '2026-10-31' },
  ],
  fielded_them: [{ player_id: 'our-jones', name: 'Ryan Jones', count: 2, catches: 2, methods: [{ type: 'caught behind', count: 1 }, { type: 'caught', count: 1 }], last_date: '2026-10-31' }],
  victims: [{ player_id: 'our-brown', name: 'Ben Brown', count: 2, wickets: 2, runs: [4, 0], methods: [{ type: 'bowled', count: 1 }, { type: 'lbw', count: 1 }], last_date: '2026-03-07' }],
  their_fielding: [{ player_id: 'our-lee', name: 'Sam Lee', count: 2, catches: 1, run_outs: 1, methods: [{ type: 'caught', count: 1 }, { type: 'run out', count: 1 }], last_date: '2026-10-31' }],
  games: [
    { game_id: 'g3', date: '2026-10-31', grade: 'One Day Grade 4', bat: { runs: 40, balls: 52, not_out: false, dismissal: 'caught', bowler: { player_id: 'our-white', name: 'Pat White' }, fielders: [{ player_id: 'our-jones', name: 'Ryan Jones' }] }, bowl: null, field: { catches: 0, stumpings: 0, run_outs: 1, victims: ['Sam Lee'] } },
    { game_id: 'g2', date: '2026-03-07', grade: 'One Day Grade 4', bat: { runs: 2, balls: 6, not_out: false, dismissal: 'bowled', bowler: { player_id: 'our-smith', name: 'Tom Smith' }, fielders: [] }, bowl: { wickets: 1, runs: 14, balls: 36, victims: ['Ben Brown'] }, field: null },
    { game_id: 'g1', date: '2026-01-17', grade: 'One Day Grade 4', bat: { runs: 19, balls: 23, not_out: false, dismissal: 'caught behind', bowler: { player_id: 'our-smith', name: 'Tom Smith' }, fielders: [{ player_id: 'our-jones', name: 'Ryan Jones' }] }, bowl: { wickets: 1, runs: 25, balls: 42, victims: ['Ben Brown'] }, field: { catches: 1, stumpings: 0, run_outs: 0, victims: ['Sam Lee'] } },
  ],
  lines: [
    '61 runs against Applecross CC from 3 innings (average 20.33, best 40).',
    'Tom Smith has dismissed them 2 times out of 3.',
    'Ryan Jones has caught them 2 times.',
    '2 wickets against Applecross CC at 19.50, best 1/14.',
    'Ben Brown has fallen to them 2 times.',
  ],
  notes: ['Checked 5 games Applecross CC has played against Western Suburbs Cricket Club; this player appeared in 3.'],
}

const vsCalls = []
const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {})
const errors = []

async function open(width) {
  const page = await browser.newPage({ viewport: { width, height: 1000 } })
  page.on('pageerror', e => errors.push(String(e)))
  let served = 0
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^.*\/api/, '')
    if (path === '/auth/me') return json(route, { id: 'u1', email: 'a@b.c', role: 'super_admin', club_id: 'o1', club_name: 'Applecross CC', capabilities: [], modules: ['iq'] })
    if (path === '/iq/opposition/opponents') return json(route, { opponents: [{ opp_key: OPP, name: CLUB, meetings: 5 }], upcoming: [] })
    if (path === '/iq/opposition/dossier') return json(route, DOSSIER)
    if (path === '/iq/opposition/player-vs-us') {
      vsCalls.push(Object.fromEntries(url.searchParams))
      return json(route, served++ === 0 ? { status: 'building' } : VS)
    }
    if (path === '/iq/opposition/player-tags') return json(route, {})
    if (path === '/iq/opposition/player-career' || path === '/iq/opposition/player-deep') return json(route, { status: 'ready', player: null })
    if (path === '/iq/opposition/club-players') return json(route, { status: 'ready', players: [] })
    if (path.endsWith('grade-scope')) return json(route, { available: [], available_formats: [], default: [] })
    if (path.startsWith('/iq/')) return json(route, [])
    return json(route, {})
  })
  await page.goto(`${BASE}/admin/betteriq/opposition-player?opponent=${OPP}&player=${PID}&name=${encodeURIComponent(CLUB)}`)
  return page
}

const page = await open(390)
try {
  await page.waitForSelector('text=Against Applecross CC', { timeout: 25000 })
} catch {
  console.log('FAIL the Against us headline renders (page text:', (await page.innerText('body')).replace(/\n/g, ' ').slice(0, 300), ')')
  await browser.close()
  process.exit(1)
}
check('the record was requested for this opponent and player', [vsCalls[0]?.opponent, vsCalls[0]?.player], [OPP, PID])
check('with the player and club names', [vsCalls[0]?.player_name, vsCalls[0]?.club_name], ['Adam Barwood', CLUB])
check('it polled past "building"', vsCalls.length >= 2, true)
let body = await page.innerText('body')
check('Overview leads with the record against us', body.indexOf('Against Applecross CC') < body.indexOf('Career snapshot') || !body.includes('Career snapshot'), true)
check('the headline names the bowler who has their number', body.includes('Tom Smith has dismissed them 2 times out of 3.'), true)

await page.click('button:has-text("Full record")')
await page.waitForSelector('text=Who has got them out')
body = await page.innerText('body')
check('the tab is called Against us', (await page.locator('button:has-text("Against us")').count()) >= 1, true)
check('who has got them out lists Tom Smith then Pat White', body.indexOf('Tom Smith') < body.indexOf('Pat White'), true)
check('who has caught them lists Ryan Jones', body.includes('Who has caught or run them out') && body.includes('Ryan Jones') && body.includes('2 ct'), true)
check('who they have got out lists Ben Brown with scores when out', body.includes('Who they have got out') && body.includes('scores when out: 4, 0'), true)
check('caught or run out by them lists Sam Lee', body.includes('Caught or run out by them') && body.includes('1 ct · 1 run out'), true)
check('game log spells out how they were out', body.includes('caught behind c Ryan Jones b Tom Smith') && body.includes('bowled b Tom Smith'), true)
check('game log lists who they removed', body.includes('Sam Lee (field)') && body.includes('Ben Brown'), true)
const links = await page.$$eval('[role="link"]', els => els.map(e => e.textContent.trim()))
check('our players link to their pages', ['Tom Smith', 'Ryan Jones', 'Ben Brown', 'Sam Lee'].every(n => links.includes(n)), true)
await page.locator('[role="link"]:has-text("Tom Smith")').first().click()
await page.waitForURL(/\/admin\/betteriq\/trends\?player=our-smith/, { timeout: 5000 }).catch(() => {})
check('clicking Tom Smith opens our player page', new URL(page.url()).pathname + new URL(page.url()).search, '/admin/betteriq/trends?player=our-smith')
await page.goBack()
await page.waitForSelector('text=Against Applecross CC', { timeout: 15000 })
await page.click('button:has-text("Against us")')
await page.waitForSelector('text=Who has got them out')
const overflow = await page.evaluate(() => {
  const limit = window.innerWidth
  const cards = [...document.querySelectorAll('.iq-card')].filter(c => /Who has|With the bat|With the ball|The read|Who they/.test(c.textContent))
  // Tables scroll inside their own wrapper; anything else poking past the edge is overflow.
  return cards.flatMap(c => [...c.querySelectorAll('*')].filter(e => !e.closest('.overflow-x-auto') && e.getBoundingClientRect().right > limit + 1)).length
})
check('no horizontal overflow in the Against us cards at 390px', overflow, 0)
check('the page itself does not scroll sideways', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
await page.waitForTimeout(2000)
await page.screenshot({ path: `${SHOTS}/opp-vs-us-390.png`, fullPage: true })

const wide = await open(1280)
await wide.waitForSelector('text=Against Applecross CC', { timeout: 25000 })
await wide.waitForTimeout(2000)
await wide.screenshot({ path: `${SHOTS}/opp-vs-us-overview-1280.png`, fullPage: true })
await wide.click('button:has-text("Against us")')
await wide.waitForSelector('text=Who has got them out')
await wide.waitForTimeout(2000)
await wide.screenshot({ path: `${SHOTS}/opp-vs-us-tab-1280.png`, fullPage: true })

check('no page errors', errors, [])
await browser.close()
console.log(`\n${pass.length} passed, ${fail.length} failed`)
process.exit(fail.length ? 1 : 0)
