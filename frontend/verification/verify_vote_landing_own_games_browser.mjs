// Drives the REAL voting page (/vote/:token) in Chromium with the API stubbed at the network layer:
//   * a visitor who opens a ballot link, picks their name and enters their PIN, then taps
//     "Back to games": the games list is READ AGAIN after they verify, and shows only their games
//   * a game they have already voted on reads "VOTED · CHANGE"
//   * "Not you?" reads the list again for whoever comes next
//   * 390px: no sideways overflow
//
//   npx vite preview --port 5199 &    node verify_vote_landing_own_games_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const iso = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const CLUB = { name: 'Gisborne CC', logo_url: null, accent_color: null, primary_color: null }
const fx = (id, opp, voted) => ({ id, opponent: opp, round: 'Round 1', round_key: '1', date: iso(-2), home_away: 'HOME', state: 'open', ...(voted === undefined ? {} : { voted }) })
const ME = { id: 'p1', display_name: 'Sam Sledge' }

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
const ctx = await browser.newContext({ viewport: { width: 390, height: 900 }, isMobile: true, hasTouch: true })
const page = await ctx.newPage(); page.setDefaultTimeout(8000)

let verified = false
const landingCalls = []
await page.route('**/api/**', (r) => json(r, {}))
await page.route(/\/api\/public\/votes\/vtok(\?.*)?$/, (r) => {
  landingCalls.push({ verified })
  json(r, {
    club: CLUB, medal: { id: 'm1', name: 'Best player' }, require_pin: true, voter_mode: 'players', allow_non_participants: false,
    allow_self_vote: false, ballot_values: [3, 2, 1], me: verified ? ME : null,
    players: [{ id: 'p1', display_name: 'Sam Sledge', has_phone: true }], grades: [], rounds: [],
    fixtures: verified ? [fx('f1', 'Rovers', true)] : [fx('f1', 'Rovers'), fx('f2', 'Saints'), fx('f3', 'Wanderers')],
  })
})
await page.route(/\/api\/public\/votes\/vtok\/fixtures\/f1$/, (r) => json(r, {
  club: CLUB, fixture: { id: 'f1', opponent: 'Rovers', round: 'Round 1', date: iso(-2), state: 'open' }, ballot_values: [3, 2, 1],
  allow_self_vote: false, voter_mode: 'players', me: verified ? ME : null, role: verified ? 'player' : 'none',
  reason: verified ? null : 'verify_required', my_ballot: verified ? ['a', 'b', 'c'] : null,
  players: verified ? [{ id: 'a', name: 'Ann Anchor' }, { id: 'b', name: 'Bob Rival' }, { id: 'c', name: 'Cal Cover' }] : [],
}))
await page.route(/\/api\/public\/votes\/vtok\/verify$/, (r) => { verified = true; json(r, { status: 'ok', player: ME }) })
await page.route(/\/api\/public\/votes\/vtok\/switch$/, (r) => { verified = false; json(r, { status: 'ok' }) })

console.log('\n── Open a ballot link, verify, back to games ──')
await page.goto(`${BASE}/vote/vtok?fixture=f1`)
await page.getByText('Find your name to vote').waitFor()
await page.getByText('Sam Sledge').first().click()
await page.locator('input[inputmode="numeric"]').fill('0111')
await page.getByRole('button', { name: 'Continue' }).click()
await page.getByText('Update my votes').waitFor()
check('the games list was read again once they verified', landingCalls.length >= 2 && landingCalls.at(-1).verified === true, JSON.stringify(landingCalls))
await page.getByText('← Back to games').first().click()
await page.getByText('Rovers').first().waitFor()
const body = await page.innerText('body')
check('Back to games lists the game they played', /Rovers/.test(body))
check('and none of the games they were not in', !/Saints|Wanderers/.test(body), body.slice(0, 300))
check('a game already voted on reads VOTED · CHANGE', /VOTED · CHANGE/.test(body))
check('390px: no sideways overflow', (await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0)
await page.screenshot({ path: process.env.SHOT || '/var/tmp/vote-landing.png' })

console.log('\n── Not you? ──')
await page.getByText('Not you?').click()
await page.getByText('Saints').first().waitFor()
check('the next person sees the club list again', /Saints/.test(await page.innerText('body')) && /Wanderers/.test(await page.innerText('body')))

await browser.close()
console.log(`\n${PASS} passed, ${FAIL} failed`)
process.exit(FAIL ? 1 : 0)
