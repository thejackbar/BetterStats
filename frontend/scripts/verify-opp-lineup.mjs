/**
 * Drive BetterIQ's Opposition scout for a fixture and check the opposition's
 * named XI card.
 *
 * The API is stubbed at the network layer. The lineup stub behaves like the
 * server: `not_named` first, then (after "Check again") a named XI with players
 * matched by id, by name, from another side, new to us and a redacted junior;
 * `pending` while the other-sides pool builds. Asserts the exact lineup request
 * on the wire (same team/grade as the dossier, `refresh=true` on Check again),
 * 390px overflow, and screenshots.
 *
 * Run against a dev or served build:  node scripts/verify-opp-lineup.mjs [baseUrl]
 */
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:5199'
const pass = [], fail = []
const check = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  ;(ok ? pass : fail).push(label)
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}: ${JSON.stringify(got)}${ok ? '' : ` (wanted ${JSON.stringify(want)})`}`)
}
const json = (route, body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const SMITH = { player_id: 'p-smith', name: 'Smith, Sam', matches: 6, innings: 6, runs: 211, not_outs: 1, high_score: '71', average: 42.2, strike_rate: 58.1, form: 'hot', recent_scores: ['71', '30'], confidence: 'high', alert: { level: 'danger', danger: ['hot form'], caution: [] }, plan: 'Back of a length into the body.', vs_us: null }
const DOSSIER = {
  status: 'ready',
  opponent: { opp_key: 'opp1', name: 'Swanbourne CC 3rd XI', org_id: 'org1' },
  coverage: { level: 'rich', notes: ['Scoped to 3rd Grade, the grade of this fixture.'] },
  teams: [], selected_team: null, selected_team_name: null,
  grade_filter: ['3rd Grade'], grade_filter_matched: true, grade_from_fixture: true,
  scope_labels: ["Men's", 'Two day'], scoped_empty: false, mixed_grades: false,
  scouted: { season_matches: 6, teams_scouted: 1, head_to_head_games: 0, season_name: 'Summer 2026/27', grade_id: 'g3' },
  danger_batters: [SMITH], danger_bowlers: [], batting: [SMITH], bowling: [], keepers: [],
  historical_threats: [], dismissal_breakdown: [], partnerships: [], partnership_insight: null,
  how_they_win: [], how_they_lose: [],
  game_plan: { remove_early: { name: 'Smith, Sam', why: 'In form.' }, see_off: null, target_bowler: null, key_warning: 'Smith is their danger man.', one_liner: 'Get Smith early.' },
  schema_v: 11, built_at: new Date().toISOString(),
}
const NAMED = {
  status: 'named', match_id: 'm1', match_status: 'UPCOMING', team_name: 'Swanbourne CC 3rd XI', date: '2026-10-17', pending: false,
  named_count: 5, scouted_count: 1, other_sides_count: 1, new_count: 2, redacted_count: 1,
  players: [
    { participant_id: 'a', name: 'Sam Smith', is_captain: true, is_keeper: false, redacted: false, matched: true, basis: 'id', pool: 'grade', player_id: 'p-smith',
      bat: { innings: 6, runs: 211, average: 42.2, strike_rate: 58.1 }, bowl: null, danger: 'bat', alert: { level: 'danger' }, plan: 'Back of a length into the body.' },
    { participant_id: 'b', name: 'David Lane', is_captain: false, is_keeper: true, redacted: false, matched: true, basis: 'name', pool: 'other_sides', player_id: 'p-lane',
      bat: { innings: 1, runs: 79, average: 79, strike_rate: 219.4 }, bowl: null, danger: null, alert: null, plan: null },
    { participant_id: 'c', name: 'Zed Newbie', is_captain: false, is_keeper: false, redacted: false, matched: false, basis: null, pool: null, player_id: null },
    { participant_id: 'd', name: '********', is_captain: false, is_keeper: false, redacted: true, matched: false, basis: null, pool: null, player_id: null },
    { participant_id: 'e', name: 'Ben Bowler', is_captain: false, is_keeper: false, redacted: false, matched: false, basis: null, pool: null, player_id: null },
  ],
  danger_named: [{ player_id: 'p-smith', name: 'Smith, Sam', kind: 'bat' }], danger_missing: [],
  analysis: { lines: [
    'Swanbourne CC 3rd XI have named 5. We have form on 2 of them.',
    'Threats: Sam Smith, 211 runs at 42.2.',
    'David Lane usually plays T20 Div 1 (their only game this season).',
    'Not scouted before: Zed Newbie, Ben Bowler and 1 junior with names withheld.',
  ] },
}
NAMED.players[0].last_season = { label: '2025/26', matches: 12, innings: 12, runs: 312, average: 31.2, strike_rate: 61, high_score: '87', wickets: 0 }
NAMED.players.push({ participant_id: 'f', name: 'Anthony Delaney', is_captain: false, is_keeper: false, redacted: false, matched: false, career_only: true, basis: null, pool: null, player_id: null,
  last_season: { label: '2025/26', matches: 8, innings: 8, runs: 210, average: 30, strike_rate: 70, high_score: '64*', wickets: 0 } })
NAMED.named_count = 6
NAMED.last_season_only_count = 1
NAMED.new_count = 1
NAMED.analysis.lines.push('Played for them last season but nothing yet this season: Anthony Delaney, 210 runs at 30.0.')
NAMED.players[0].grades = [{ name: '3rd Grade', matches: 6 }]
NAMED.players[0].plays_elsewhere = false
NAMED.players[1].grades = [{ name: 'T20 Div 1', matches: 1 }]
NAMED.players[1].usual_grade = 'T20 Div 1'
NAMED.players[1].plays_elsewhere = true

const lineupCalls = []
const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {})
const page = await browser.newPage({ viewport: { width: 390, height: 900 } })
const errors = []
page.on('pageerror', e => errors.push(String(e)))

await page.route('**/api/**', async route => {
  const url = new URL(route.request().url())
  const path = url.pathname.replace(/^.*\/api/, '')
  if (path === '/auth/me') return json(route, { id: 'u1', email: 'a@b.c', role: 'super_admin', club_id: 'o1', club_name: 'Home CC', capabilities: [], modules: ['iq'] })
  if (path === '/iq/opposition/opponents') return json(route, { opponents: [], upcoming: [{ fixture_id: 'fx3', opponent_name: 'Swanbourne CC 3rd XI', opp_key: 'opp1', played_on: '2026-10-17', home_away: 'HOME', grade_name: '3rd Grade', team_name: '3rd XI' }] })
  if (path === '/iq/opposition/report') return json(route, { opponent: { opp_key: 'opp1', name: 'Swanbourne CC 3rd XI' }, head_to_head: { meetings: 0 }, our_performers: {}, venues: [], matchups: [], coverage: {} })
  if (path === '/iq/opposition/dossier') return json(route, DOSSIER)
  if (path === '/iq/opposition/lineup') {
    const q = Object.fromEntries(url.searchParams)
    lineupCalls.push(q)
    if (q.refresh === 'true') return json(route, NAMED)
    return json(route, { status: 'not_named', team_name: 'Swanbourne CC 3rd XI', date: '2026-10-17', named_count: 0 })
  }
  if (path === '/iq/opposition/player-tags') return json(route, {})
  if (path.startsWith('/iq/') && /(grades|seasons|players|ladder|scope)/.test(path)) return json(route, path.endsWith('grade-scope') ? { available: [], available_formats: [], default: [] } : [])
  return json(route, {})
})

await page.goto(`${BASE}/admin/betteriq/opposition?fixture=fx3&name=Swanbourne%20CC%203rd%20XI`)
try {
  await page.waitForSelector('text=Who they have named', { timeout: 25000 })
} catch (e) {
  // Report, don't crash: a page without the card is a failed check, not a broken harness.
  console.log('FAIL the lineup card renders for a fixture scout (page text:', (await page.innerText('body')).replace(/\n/g, ' ').slice(0, 200), ')')
  await browser.close()
  console.log(`\n${pass.length} passed, ${fail.length + 1} failed`)
  process.exit(1)
}

check('the lineup was requested for the fixture', lineupCalls[0]?.fixture_id, 'fx3')
check('with the dossier\'s own grade/team (none sent: the fixture default decides)', [lineupCalls[0]?.grade, lineupCalls[0]?.team], [undefined, undefined])
check('not named yet: says so plainly', (await page.innerText('body')).includes("haven't named their side yet"), true)
check('and offers Check again', (await page.locator('button:has-text("Check again")').count()), 1)

await page.click('button:has-text("Check again")')
await page.waitForSelector('text=Zed Newbie', { timeout: 10000 })
check('Check again asks the server to bypass its cache', lineupCalls.at(-1)?.refresh, 'true')
const body = await page.innerText('body')
check('the summary line counts them', body.includes('6 named') && body.includes('1 scouted') && body.includes('1 from another side') && body.includes('1 with nothing yet this season') && body.includes('1 new to us'), true)
check('the quick read is shown, with its sentences', body.toUpperCase().includes('QUICK READ') && body.includes('Threats: Sam Smith, 211 runs at 42.2.'), true)
check('the grades a visitor usually plays are shown', body.includes('Usually plays T20 Div 1. This season: T20 Div 1 (1).'), true)
check('last season is shown per player, with the games behind it', body.includes('Last season (2025/26): 312 runs @ 31.2 · SR 61 · HS 87 (12 games)'), true)
check('a player with nothing yet this season is marked, with last season\'s figures',
  body.toUpperCase().includes('LAST SEASON ONLY') && body.includes('210 runs @ 30 · SR 70 · HS 64* (8 games)'), true)
check('a regular in this grade gets no "usually" claim', body.includes('This season: 3rd Grade (6).') && !body.includes('Usually plays 3rd Grade'), true)
// Tags are CSS-uppercased, so innerText comes back uppercase: write the check that way.
check('Lane is labelled as form from another side', body.toUpperCase().includes('FROM ANOTHER SIDE') && body.includes('79 runs'), true)
check('the redacted junior is not guessed', body.includes('Name withheld (junior)'), true)
check('a stranger is "new to us"', body.toUpperCase().includes('NEW TO US'), true)
check('captain and keeper tags show', body.includes('WK') && /\bC\b/.test(body), true)
const names = await page.$$eval('[role="link"]', els => els.map(e => e.textContent.trim()))
check('matched players link to their profile, unmatched do not', names.includes('Sam Smith') && names.includes('David Lane') && !names.includes('Zed Newbie'), true)
// The lineup card itself, not the page: the scout's header action row is wider than a
// phone on its own (it was before this card existed), so a page-wide check would blame the card.
const cardOverflow = await page.evaluate(() => {
  const card = [...document.querySelectorAll('.iq-card')].find(c => /their selection/i.test(c.textContent))
  if (!card) return 'no card'
  const limit = window.innerWidth
  return [...card.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > limit + 1).length
})
check('no horizontal overflow inside the lineup card at 390px', cardOverflow, 0)
check('no page errors', errors, [])
await page.locator('text=Who they have named').first().scrollIntoViewIfNeeded()
await page.screenshot({ path: process.env.SHOT || '/tmp/claude-0/opp-lineup-390.png', fullPage: true })

await browser.close()
console.log(`\n${pass.length} passed, ${fail.length} failed`)
process.exit(fail.length ? 1 : 0)
