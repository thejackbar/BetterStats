// Drives the real Fantasy My Team screen in Chromium with the API stubbed at the network layer, for the
// Sheet / Cards toggle (v9.129.32).
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_fantasy_my_team_cards_browser.mjs [baseUrl]
//
// Checks: it opens as the sheet it always was; Cards shows one card per player, grouped by role, with the
// captain and vice marked and each card's points; the choice is remembered; tapping a card opens the same
// actions the sheet has and Make captain sends exactly the request the sheet's button sends; a locked round
// offers no captain buttons; no sideways scroll at 390px or on a wide screen; no page errors.
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

const PHOTO = `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#d9a77c"/><circle cx="100" cy="80" r="40" fill="#8a5a3a"/><rect x="40" y="130" width="120" height="70" rx="30" fill="#b22"/></svg>`
const P = (i, name, role, extra = {}) => ({ player_id: `p${i}`, name, role, price: 6 + i * 0.7, purchase_price: 6 + i * 0.7, price_change: i % 3 === 0 ? 0.2 : i % 3 === 1 ? -0.1 : 0, is_captain: false, is_vice_captain: false, photo_url: i % 4 === 0 ? null : '/api/photo.svg', ...extra })
const PLAYERS = [
  P(1, 'Monument, Darren', 'batter'), P(2, 'Prakashkar, Manan', 'batter'), P(3, 'Deshapriya, Malinda', 'batter'), P(4, 'Dissanayake, Dushmantha', 'batter'),
  P(5, 'Barendse, Jack', 'allrounder', { is_captain: true }), P(6, 'Wijesinghe, Isuri', 'allrounder', { is_vice_captain: true }), P(7, 'Kershaw, Samantha', 'allrounder'),
  P(8, 'Carmody, Ryan', 'keeper'),
  P(9, 'Newman, Daniel', 'bowler'), P(10, 'Cowcher, Baxter', 'bowler'), P(11, 'De soysa, Thusith', 'bowler'), P(12, 'Dockery, James', 'bowler'),
]
const GW = Object.fromEntries(PLAYERS.map((p, i) => [p.player_id, i * 7 % 40 + (i % 2 ? 0.5 : 0)]))

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1000, locked = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = [], posts = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace(/^\/api/, '')
    if (path === '/photo.svg') return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: PHOTO })
    if (path === '/public/fantasy/tok') return json(route, { club: { name: 'Applecross CC', accent_color: '#d40000' }, season: { name: 'Fantasy', status: 'active', rules: { role_quota: { batter: 4, allrounder: 3, keeper: 1, bowler: 4 } } }, me: { id: 'm1', display_name: 'Boom Boom' } })
    if (path === '/public/fantasy/tok/me') return json(route, {
      manager: { id: 'm1', display_name: 'Boom Boom' },
      squad: { id: 's1', team_name: 'Boom XI', players: PLAYERS, chips: [], total_points: 646.5, value: 119.9, budget_remaining: 1.1, free_transfers: 0, overall_rank: 11, can_rebuild: false, queued_transfers: [] },
      round: { number: 3, status: 'upcoming', locked, lock_at: null },
    })
    if (path === '/public/fantasy/tok/pool') return json(route, { players: [], rules: {} })
    if (path === '/public/fantasy/tok/notifications') return json(route, { notifications: [] })
    if (path === '/public/fantasy/tok/round') return json(route, { round: { number: 2 }, mine: { points: 100, lineup: PLAYERS.map(p => ({ player_id: p.player_id, points: GW[p.player_id] })) }, rounds: [] })
    if (path === '/public/fantasy/tok/live') return json(route, { live: false, round: null, mine: null })
    if (path === '/public/fantasy/tok/ladder') return json(route, { ladder: [], teams_visible: false })
    if (path === '/public/fantasy/tok/captain') { posts.push({ method: req.method(), body: req.postData() }); return json(route, { ok: true }) }
    return json(route, {})
  })
  await page.goto(`${BASE}/fantasy/tok`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('text=Total points', { timeout: 8000 }).catch(async (e) => { console.log((await page.locator('body').innerText()).slice(0, 400), errors); throw e })
  return { page, ctx, errors, posts }
}

const cardCount = (page) => page.locator('button[aria-pressed][aria-label]').count()

// ── 1. The sheet is still what you get ───────────────────────────────────────
{
  const t = await open()
  const body = await t.page.locator('body').innerText()
  ck('it opens as the team sheet it always was', /Monument, Darren/.test(body) && (await cardCount(t.page)) === 0)
  ck('with a Sheet / Cards switch', (await t.page.getByRole('button', { name: 'Cards', exact: true }).count()) === 1 && (await t.page.getByRole('button', { name: 'Sheet', exact: true }).count()) === 1)
  await t.ctx.close()
}

// ── 2. Cards ─────────────────────────────────────────────────────────────────
{
  const t = await open({ width: 390 })
  await t.page.getByRole('button', { name: 'Cards', exact: true }).click()
  await t.page.waitForSelector('button[aria-pressed][aria-label]')
  ck('one card for each of the 12 players', (await cardCount(t.page)) === 12, String(await cardCount(t.page)))
  const body = await t.page.locator('body').innerText()
  ck('grouped by role with the quota counts', /BATTERS[\s\S]*4 \/ 4/.test(body) && /ALL-ROUNDERS[\s\S]*3 \/ 3/.test(body) && /WICKETKEEPER[\s\S]*1 \/ 1/.test(body) && /BOWLERS[\s\S]*4 \/ 4/.test(body), body.slice(0, 500))
  ck('a "Last, First" name is the first name over the SURNAME, no comma', /JACK\s+BARENDSE/i.test(body) && !/Barendse, Jack/.test(body), body.slice(0, 400))
  ck('the captain card is marked C and the vice V', (await t.page.getByRole('button', { name: /Barendse, Jack, captain/ }).count()) === 1 && (await t.page.getByRole('button', { name: /Wijesinghe, Isuri, vice captain/ }).count()) === 1)
  const mon = await t.page.getByRole('button', { name: /Monument, Darren/ }).innerText()
  ck('a card shows the price and the round\'s points', /\$6\.7/.test(mon) && /0\.5|0/.test(mon) && /PTS/i.test(mon), mon)
  const dockery = await t.page.getByRole('button', { name: /Dockery, James/ }).innerText()
  ck('and each player\'s own points', new RegExp(String(GW.p12).replace('.', '\\.')).test(dockery), `${dockery} vs ${GW.p12}`)
  const over = await t.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no sideways scroll', over <= 1, String(over))
  const w = await t.page.getByRole('button', { name: /Monument, Darren/ }).boundingBox()
  const w2 = await t.page.getByRole('button', { name: /Prakashkar, Manan/ }).boundingBox()
  ck('390px: two cards sit side by side', Math.abs(w.y - w2.y) < 2 && w2.x > w.x, JSON.stringify([w, w2]))
  if (SHOTS) await t.page.screenshot({ path: `${SHOTS}/myteam_cards_390.png`, fullPage: true })

  // remembered
  await t.page.reload(); await t.page.waitForSelector('text=Total points')
  ck('the choice is remembered across a reload', (await cardCount(t.page)) === 12)

  // actions
  await t.page.getByRole('button', { name: /Monument, Darren/ }).click()
  ck('tapping a card selects it and opens the captain actions', (await t.page.getByRole('button', { name: 'Make captain' }).count()) === 1 && (await t.page.getByRole('button', { name: 'Make vice' }).count()) === 1 && (await t.page.getByRole('button', { name: 'View profile' }).count()) === 1)
  ck('the selected card says so', (await t.page.getByRole('button', { name: /Monument, Darren/ }).getAttribute('aria-pressed')) === 'true')
  await t.page.getByRole('button', { name: 'Make captain' }).click()
  await t.page.waitForTimeout(500)
  ck('Make captain sends exactly one request with that player and the current vice', t.posts.length === 1 && t.posts[0].method === 'POST' && JSON.parse(t.posts[0].body).captain_player_id === 'p1' && JSON.parse(t.posts[0].body).vice_player_id === 'p6', JSON.stringify(t.posts))
  await t.page.getByRole('button', { name: 'Sheet', exact: true }).click()
  ck('switching back gives the sheet again', (await cardCount(t.page)) === 0 && /Monument, Darren/.test(await t.page.locator('body').innerText()))
  ck('no page errors', t.errors.length === 0, t.errors.join(' | '))
  await t.ctx.close()
}

// ── 3. Locked round, and a wide screen ───────────────────────────────────────
{
  const t = await open({ locked: true, width: 390 })
  await t.page.getByRole('button', { name: 'Cards', exact: true }).click()
  await t.page.getByRole('button', { name: /Monument, Darren/ }).click()
  ck('a locked round offers no captain buttons, only the profile', (await t.page.getByRole('button', { name: 'Make captain' }).count()) === 0 && (await t.page.getByRole('button', { name: 'View profile' }).count()) === 1)
  await t.ctx.close()

  const d = await open({ width: 1600 })
  await d.page.getByRole('button', { name: 'Cards', exact: true }).click()
  await d.page.waitForSelector('button[aria-pressed][aria-label]')
  ck('1600px: all 12 cards and the right rail are there', (await cardCount(d.page)) === 12 && /THIS ROUND/i.test(await d.page.locator('body').innerText()))
  const over = await d.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('1600px: no sideways scroll', over <= 1, String(over))
  if (SHOTS) await d.page.screenshot({ path: `${SHOTS}/myteam_cards_1600.png` })
  ck('no page errors', d.errors.length === 0, d.errors.join(' | '))
  await d.ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
