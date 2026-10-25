// Drives the real Fantasy admin Overview in Chromium with the API stubbed at the network layer, for
// running scores (v9.129.18).
//
//   npm run build && npx vite preview --port 5197 &
//   node frontend/verification/verify_fantasy_live_sync_browser.mjs [baseUrl]
//
// Checks: a round being played reads "live" with when its scores were last checked and offers Sync
// scores; the exact request that button sends; the message for a pass that moved scores and for one
// that did not run; the Live scoring switch and the exact PATCH it sends; a finished round offers
// only Confirm final scores; confirming a round still being played asks first; and 390px width has
// no horizontal overflow.
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

const iso = (d) => d.toISOString().slice(0, 10)
const today = new Date()
const day = (n) => { const d = new Date(today); d.setDate(d.getDate() + n); return iso(d) }
const checkedAt = new Date(today.getTime() - 4 * 60 * 1000).toISOString()

const ROUNDS = (live_sync) => ({
  live_sync,
  rounds: [
    { id: 'r1', round_number: 1, name: 'Round 1', status: 'scored', playing: false, live_checked_at: null, drift: null,
      start_date: day(-20), end_date: day(-14), lock_at: new Date(today.getTime() - 20 * 864e5).toISOString(), lock_manual: false },
    { id: 'r2', round_number: 2, name: 'Round 2', status: 'upcoming', playing: true, live_checked_at: checkedAt, drift: null,
      start_date: day(-1), end_date: day(6), lock_at: new Date(today.getTime() - 864e5).toISOString(), lock_manual: false },
    { id: 'r3', round_number: 3, name: 'Round 3', status: 'upcoming', playing: false, live_checked_at: null, drift: null,
      start_date: day(8), end_date: day(9), lock_at: new Date(today.getTime() + 8 * 864e5).toISOString(), lock_manual: false },
  ],
})

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openPage({ width = 1440, syncReply, liveSync = true } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1100 } })
  const page = await ctx.newPage()
  const errors = [], calls = []
  let liveOn = liveSync
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('dialog', async (d) => { calls.push(`dialog:${d.message().slice(0, 60)}`); await d.accept() })
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = route.request().method()
    const body = route.request().postData()
    if (path === '/auth/me') {
      return json(route, { id: 'u1', username: 'admin', role: 'club_admin', club_id: 'org-1', club_slug: 'apx',
        capabilities: ['manage_fantasy'], entitlements: { modules: ['stats', 'fantasy'] } })
    }
    if (path === '/club-admin/fantasy/season' && method === 'GET') {
      return json(route, {
        season: { id: 's1', year: today.getFullYear(), season_year: today.getFullYear(), name: 'Applecross Fantasy', status: 'active',
                  registration_open: true, rules: liveOn ? {} : { live_sync: false } },
        link_token: 'tok', link_active: true, counts: { pool: 30, rounds: 3, rounds_scored: 1 },
      })
    }
    if (path === '/club-admin/fantasy/season/s1/rounds') return json(route, ROUNDS(liveOn))
    if (path === '/club-admin/fantasy/season/s1/sync-scores' && method === 'POST') {
      calls.push('POST sync-scores')
      return json(route, syncReply)
    }
    if (path === '/club-admin/fantasy/season/s1/rules' && method === 'PATCH') {
      calls.push(`PATCH rules ${body}`)
      liveOn = JSON.parse(body).live_sync
      return json(route, { rules: { live_sync: liveOn } })
    }
    if (path === '/club-admin/fantasy/rounds/r1/settle' || path === '/club-admin/fantasy/rounds/r2/settle') {
      calls.push(`POST ${path}`)
      return json(route, { players_scored: 12 })
    }
    return json(route, {})
  })
  await page.goto(`${BASE}/admin/fantasy`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('text=Applecross Fantasy', { timeout: 15000 })
  return { page, ctx, errors, calls }
}

const rowOf = (page, name) => page.locator('tr', { hasText: name })
const flashText = async (page) => (await page.locator('div.rounded.bg-pb-accent\\/10').first().innerText().catch(() => ''))

// ── 1. The running round ──────────────────────────────────────────────────────
{
  const { page, ctx, errors, calls } = await openPage({
    syncReply: { ran: true, games_checked: 3, players_moved: 5, message: null, rounds: [{ number: 2, action: 'refreshed' }] },
  })
  const r2 = rowOf(page, 'Round 2')
  const r1 = rowOf(page, 'Round 1')
  const r3 = rowOf(page, 'Round 3')
  ck('the round being played reads "live", not "upcoming"', /live/.test(await r2.innerText()) && !/upcoming/.test(await r2.innerText()))
  ck('and says when its scores were last checked', /Scores last checked/.test(await r2.innerText()), await r2.innerText())
  ck('and that these are running scores', /Running scores until you confirm/.test(await r2.innerText()))
  ck('a round not yet being played is still "upcoming" with no live text', /upcoming/.test(await r3.innerText()) && !/Being played/.test(await r3.innerText()))
  ck('only the running round offers Sync scores in its row', (await r2.getByText('Sync scores').count()) === 1 && (await r3.getByText('Sync scores').count()) === 0
     && (await r1.getByText('Sync scores').count()) === 0)
  ck('every round offers Confirm final scores, and nothing in the table still says Settle',
     (await page.getByText('Confirm final scores').count()) === 3 && !/\bSettle\b/.test(await page.locator('table').innerText()))
  ck('the header offers Sync scores and Confirm finished rounds', (await page.getByRole('button', { name: 'Sync scores' }).count()) >= 1
     && (await page.getByRole('button', { name: 'Confirm finished rounds' }).count()) === 1)
  ck('Live scoring shows as on', await page.getByText('Live scoring on').count() === 1)
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/fantasy_live_admin_1440.png`, fullPage: true })

  await page.getByRole('button', { name: 'Sync scores' }).first().click()
  await page.waitForSelector('text=Checked 3 games in play')
  ck('Sync scores sends exactly one POST to the season sync-scores route', calls.filter(c => c === 'POST sync-scores').length === 1, calls.join(' | '))
  const msg = await flashText(page)
  ck('the message says what moved and that points are running', /Checked 3 games in play\. 5 players moved\./.test(msg) && /running scores/.test(msg), msg)

  // the row's own link does the same call
  await rowOf(page, 'Round 2').getByRole('button', { name: 'Sync scores' }).click()
  await page.waitForFunction(() => true)
  await page.waitForTimeout(300)
  ck('the row link sends the same request', calls.filter(c => c === 'POST sync-scores').length === 2, calls.join(' | '))

  // confirming a round still being played asks first; a finished one does not
  calls.length = 0
  await rowOf(page, 'Round 2').getByRole('button', { name: 'Confirm final scores' }).click()
  await page.waitForTimeout(300)
  ck('confirming a round still being played asks first, then sends the settle request',
     calls[0]?.startsWith('dialog:Games are still being played') && calls.includes('POST /club-admin/fantasy/rounds/r2/settle'), calls.join(' | '))
  calls.length = 0
  await rowOf(page, 'Round 1').getByRole('button', { name: 'Confirm final scores' }).click()
  await page.waitForTimeout(300)
  ck('confirming a finished round does not ask', !calls.some(c => c.startsWith('dialog:')) && calls.includes('POST /club-admin/fantasy/rounds/r1/settle'), calls.join(' | '))

  // the switch
  calls.length = 0
  await page.getByRole('button', { name: 'Turn off' }).click()
  await page.waitForSelector('text=Live scoring off')
  ck('Turn off sends exactly {live_sync:false} to the rules route', calls.length === 1 && calls[0] === 'PATCH rules {"live_sync":false}', calls.join(' | '))
  calls.length = 0
  await page.getByRole('button', { name: 'Turn on' }).click()
  await page.waitForSelector('text=Live scoring on')
  ck('Turn on sends {live_sync:true}', calls[0] === 'PATCH rules {"live_sync":true}', calls.join(' | '))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── 2. A pass that did not run, and one with nothing to report ────────────────
{
  const { page, ctx } = await openPage({ syncReply: { ran: false, reason: 'no_running_round', message: 'No round is being played today. A finished round is confirmed with Confirm final scores.' } })
  await page.getByRole('button', { name: 'Sync scores' }).first().click()
  await page.waitForSelector('text=No round is being played today')
  ck('a pass that did not run says why in words', /No round is being played today/.test(await flashText(page)))
  await ctx.close()
}
{
  const { page, ctx } = await openPage({ syncReply: { ran: true, games_checked: 1, players_moved: 0, message: null, rounds: [] } })
  await page.getByRole('button', { name: 'Sync scores' }).first().click()
  await page.waitForSelector('text=Checked 1 game in play')
  ck('a pass with no change says so, and does not claim a move', /No scores have changed since the last look/.test(await flashText(page)) && !/moved/.test(await flashText(page)), await flashText(page))
  await ctx.close()
}

// ── 3. Phone width ────────────────────────────────────────────────────────────
{
  const { page, ctx } = await openPage({ width: 390, syncReply: { ran: true, games_checked: 0, players_moved: 0, rounds: [] } })
  const over = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, c: document.documentElement.clientWidth,
                                            bodyW: document.body.scrollWidth }))
  ck('390px: the page does not scroll sideways', over.w <= over.c + 1 && over.bodyW <= over.c + 1, JSON.stringify(over))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/fantasy_live_admin_390.png`, fullPage: true })
  await ctx.close()
}

// ── 4. The manager's Live screen ──────────────────────────────────────────────
async function openLive(livePayload, width = 390) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (route, body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  const lineup = [{ player_id: 'p1', name: 'Sushruth Menon', role: 'batter', points: 30, eff_points: 30, counted: true, captained: false }]
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    if (path === '/public/fantasy/tok') return json(route, { club: { name: 'Applecross CC' }, season: { name: 'Fantasy', rules: {} }, me: { id: 'm1', display_name: 'Xavier' } })
    if (path === '/public/fantasy/tok/me') return json(route, { manager: { id: 'm1', display_name: 'Xavier' }, squad: { id: 'sq1', team_name: 'X Team', players: [], chips: [], total_points: 0, last_round: 0, value: 0, budget_remaining: 0, free_transfers: 1, queued_transfers: [] }, round: null })
    if (path === '/public/fantasy/tok/pool') return json(route, { players: [], rules: {} })
    if (path === '/public/fantasy/tok/notifications') return json(route, { notifications: [] })
    if (path === '/public/fantasy/tok/live') return json(route, livePayload(lineup))
    return json(route, {})
  })
  await page.goto(`${BASE}/fantasy/tok`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Live', exact: true }).first().click({ timeout: 15000 })
  return { page, ctx, errors }
}
{
  const payload = (lineup, checked_at) => ({ live: true, round: { number: 2, name: 'Round 2', status: 'live' }, mine: { points: 30, raw_points: 30, lineup },
                                              playing_now: 3, provisional_rank: 2, overall_rank: 2, checked_at })
  const a = await openLive((l) => payload(l, checkedAt))
  await a.page.waitForSelector('text=Live points', { timeout: 15000 })
  const body = await a.page.locator('body').innerText()
  ck('Live shows the points as live and says when the games were last read',
     /Scores checked \d{1,2}:\d{2}/.test(body) && /Running points until the round is confirmed/.test(body), body.slice(0, 400))
  const over = await a.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: the Live screen does not scroll sideways', over <= 1, String(over))
  if (SHOTS) await a.page.screenshot({ path: `${SHOTS}/fantasy_live_member_390.png` })
  ck('no page errors on the Live screen', a.errors.length === 0, a.errors.join(' | '))
  await a.ctx.close()
  const b = await openLive((l) => payload(l, null))
  await b.page.waitForSelector('text=Live points', { timeout: 15000 })
  const body2 = await b.page.locator('body').innerText()
  ck('before the first check it says the points are running and does not invent a time',
     /Running points until the round is confirmed/.test(body2) && !/Scores checked/.test(body2))
  await b.ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
