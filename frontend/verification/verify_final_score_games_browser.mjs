// Drives the real BetterPosts "Final Score" post in Chromium with the API
// stubbed at the network layer.
//
//   npx vite build && npx vite preview --port 5198 &
//   node frontend/verification/verify_final_score_games_browser.mjs [baseUrl]
//
// What a build cannot tell you: that the picker asks for the same list the
// public Games page reads (`/organisations/{id}/results` for a season), that it
// leaves called-off games out, that a pick loads THAT game's scorecard (the
// request on the wire names the game id) and fills the result fields, and that
// the season and grade selectors narrow the list. The phone layout is a separate
// quick-post editor with no Final Score data step, so there is no 390px case.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const SETTINGS = {
  id: 'org-1', name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'applecross',
  logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null,
}
const SEASONS = [
  { id: 's-new', name: 'Summer 2026/27', year: 2026 },
  { id: 's-old', name: 'Summer 2025/26', year: 2025 },
]
const GAME = (id, played_at, home, away, result, grade_name, status = 'COMPLETED') =>
  ({ id, played_at, home_team: home, away_team: away, result, winning_team: null, grade_name, status, match_format: 'One Day' })
const RESULTS = {
  's-new': [GAME('g-new-1', '2026-10-03', 'CVPCC T20 Division 1', 'Applecross T20 Div 1', 'WIN', 'Twenty20 Div 1')],
  's-old': [
    GAME('g-old-1', '2026-03-21', 'Applecross 6th XI', 'Swan Athletic OD4', 'LOSS', 'One Day Grade 4'),
    GAME('g-old-2', '2026-03-29', 'Bassendean 2nd XI', 'Applecross 2nd XI', 'WIN', '3rd Grade'),
    GAME('g-old-3', '2026-03-14', 'Applecross 2nd XI', 'Rivals 2nd XI', null, '3rd Grade', 'ABANDONED'),
  ],
}
const CARD = {
  meta: { competition: '3RD GRADE', round: 'ROUND 9', format: 'ONE DAY', overs: 40, venue: 'Hale Oval', date: '2026-03-29', toss: '', result: 'APPLECROSS 2ND XI WON BY 4 WICKETS', series: '', motm: {} },
  home: { name: 'BASSENDEAN 2ND XI', short: 'B2X', monogram: 'B2X', total: '188', wickets: 9, overs: '40.0', runRate: '4.7', batting: [], bowling: [], extras: {} },
  away: { name: 'APPLECROSS 2ND XI', short: 'A2X', monogram: 'A2X', total: '189', wickets: 6, overs: '38.2', runRate: '4.9', batting: [], bowling: [], extras: {} },
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openEditor(viewport = { width: 1600, height: 1000 }) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const errors = []
  const calls = { results: [], scorecard: [], lookup: [] }
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_/.test(m.text())) errors.push(m.text()) })
  const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const u = new URL(url)
    let m
    if (/\/organisations\/[^/]+\/seasons$/.test(u.pathname)) return route.fulfill(json(SEASONS))
    if (/\/organisations\/[^/]+\/results$/.test(u.pathname)) {
      calls.results.push(u.search)
      return route.fulfill(json(RESULTS[u.searchParams.get('season_id')] || []))
    }
    if ((m = u.pathname.match(/\/admin\/social\/scorecard\/(.+)$/))) { calls.scorecard.push(m[1]); return route.fulfill(json(CARD)) }
    if (/\/admin\/social\/match-lookup/.test(u.pathname)) { calls.lookup.push(u.search); return route.fulfill(json({ kind: 'unknown', message: 'x' })) }
    if (/\/auth\/me/.test(u.pathname)) return route.fulfill(json({
      id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross',
      entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
    }))
    if (/\/admin\/social\/templates/.test(u.pathname)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(u.pathname)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(u.pathname)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(u.pathname)) return route.fulfill(json([]))
    if (/sponsors/.test(u.pathname)) return route.fulfill(json([]))
    if (/selection\/overview/.test(u.pathname)) return route.fulfill(json({ fixtures: [] }))
    if (/lineups/.test(u.pathname)) return route.fulfill(json({ matches: [] }))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/social-post?type=result`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  return { ctx, page, errors, calls }
}

const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }
const choose = async (loc, value) => { try { if (await loc.count()) await loc.first().selectOption(value, { timeout: 2000 }) } catch { /* reported by the check */ } }
const textOf = async (loc) => { try { return (await loc.count()) ? await loc.first().innerText() : '' } catch { return '' } }

// ── Desktop: the picker in the "Get your data" step ─────────────────────────
{
  const { ctx, page, errors, calls } = await openEditor()
  const picker = page.getByTestId('club-games-picker').first()
  page.setDefaultTimeout(3000)
  ck('picker is on the Final Score data step', await seen(picker))
  ck('nothing is fetched until it is opened', calls.results.length === 0)

  await press(picker.getByRole('button', { name: /pick from your games/i }))
  await page.waitForTimeout(400)
  ck('opening it reads the newest season from the Games endpoint',
    calls.results.length === 1 && /season_id=s-new/.test(calls.results[0]), JSON.stringify(calls.results))
  ck('the newest season is the default', (await textOf(picker)).includes('CVPCC T20 Division 1 v Applecross T20 Div 1'))

  await choose(picker.getByLabel('Season'), 's-old')
  await page.waitForTimeout(400)
  const body = await textOf(picker)
  ck('switching season reads that season', calls.results.some((q) => /season_id=s-old/.test(q)), JSON.stringify(calls.results))
  ck('both played games are listed', body.includes('Bassendean 2nd XI v Applecross 2nd XI') && body.includes('Applecross 6th XI v Swan Athletic OD4'))
  ck('a called-off game is left out', !body.includes('Rivals 2nd XI'))
  ck('newest first', body.indexOf('Bassendean 2nd XI') < body.indexOf('Applecross 6th XI'))

  await choose(picker.getByLabel('Grade'), '3rd Grade')
  await page.waitForTimeout(150)
  const narrowed = await textOf(picker)
  ck('the grade filter narrows the list', narrowed.includes('Bassendean 2nd XI') && !narrowed.includes('Swan Athletic'))
  ck('the picker does not overflow its panel', await picker.evaluate((el) => el.scrollWidth <= el.clientWidth + 1).catch(() => false))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/picker-desktop.png` })

  await press(picker.getByRole('button', { name: /Bassendean 2nd XI v Applecross 2nd XI/ }))
  await page.waitForTimeout(500)
  ck('a pick loads that game\'s scorecard by id', calls.scorecard.length === 1 && calls.scorecard[0] === 'g-old-2', JSON.stringify(calls.scorecard))
  ck('a pick does not go through the paste-a-link lookup', calls.lookup.length === 0)
  ck('the result is reported as loaded', /Result, scores & top performers loaded/.test(await page.locator('body').innerText()))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── Control for the check above: a paste still goes through the lookup ──────
{
  const { ctx, page, calls } = await openEditor()
  const input = page.getByPlaceholder(/Match link from play.cricket.com.au/).first()
  await input.fill('ef9b6401-787f-4f93-b9b8-8de0316f3686')
  await press(page.getByRole('button', { name: 'Fetch' }))
  await page.waitForTimeout(400)
  ck('control: a pasted link still uses the lookup', calls.lookup.length === 1, JSON.stringify(calls.lookup))
  await ctx.close()
}

console.log(`\n${pass} passed, ${fail} failed`)
await browser.close()
process.exit(fail ? 1 : 0)
