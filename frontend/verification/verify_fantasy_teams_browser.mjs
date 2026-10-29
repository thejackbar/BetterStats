// Drives the real Fantasy Teams screen (list and card swap) in Chromium with the API stubbed at the network layer.
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_fantasy_teams_browser.mjs [baseUrl]
//
// Checks: the ladder offers the screen once teams are visible and not before; the exact request it sends (one
// GET /teams); the list holds every team in rank order and a row opens its locked XI; the stack opens on the
// manager's own team; Next, Prev, a swipe, the jump list and My team each move it; Share card produces a real PNG
// at 2x; a refused request says why; no overflow at 390px; no page errors.
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

const N = 26
const YOU = 17   // index of the manager's own team (rank 18)
const NAMES = ['Alice Opener', 'Bob Spinner', 'Cara Keeper', 'Dan Quick', 'Eve Allround', 'Finn Seamer', 'Gus Slogger', 'Hana Leggie', 'Ivo Anchor', 'Jade Pacer', 'Kai Finisher', 'Lena Bench']
const lineup = (k) => NAMES.map((nm, i) => ({
  player_id: `p${k}-${i}`, name: `${nm}`, role: i % 2 ? 'bowler' : 'batter', points: 10 - i, eff_points: i === 0 ? 20 : 10 - i,
  counted: i < 11, captained: i === 0, photo_url: null, initials: nm.split(' ').map(w => w[0]).join(''),
}))
const teams = Array.from({ length: N }, (_, i) => i === 3
  ? { squad_id: `s-${i + 1}`, team_name: `Team ${i + 1}`, manager: `Manager ${i + 1}`, you: false, total_points: 300 - i * 5, rank: i + 1, rank_delta: 0,
      round: { number: 3, name: 'Round 3', status: 'scored' }, lineup: null, points: null, chip_used: null,
      note: 'This team joined after that round locked, so it has no locked team to show.' }
  : { squad_id: `s-${i + 1}`, team_name: `Team ${i + 1}`, manager: `Manager ${i + 1}`, you: i === YOU, total_points: 300 - i * 5, rank: i + 1,
      rank_delta: i % 3 - 1, round: { number: 3, name: 'Round 3', status: 'scored' }, lineup: lineup(i + 1), points: 80 - i, chip_used: i === 1 ? 'wildcard' : null })

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1280, visible = true, teamsStatus = 200, start = 'Ladder' } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 }, acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = [], reqs = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const rows = teams.map(t => ({ rank: t.rank, squad_id: t.squad_id, team_name: t.team_name, manager: t.manager, points: t.total_points, gw: 5, rank_delta: 0, you: t.you }))
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    if (path === '/public/fantasy/tok') return json(route, { club: { name: 'Applecross CC' }, season: { name: 'Fantasy', status: 'active', rules: {} }, me: { id: 'm1', display_name: 'Xavier' } })
    if (path === '/public/fantasy/tok/me') return json(route, { manager: { id: 'm1', display_name: 'Xavier' }, squad: { id: `s-${YOU + 1}`, team_name: `Team ${YOU + 1}`, players: [], chips: [], total_points: 215, value: 0, budget_remaining: 0, free_transfers: 1, queued_transfers: [] }, round: null })
    if (path === '/public/fantasy/tok/pool') return json(route, { players: [], rules: {} })
    if (path === '/public/fantasy/tok/notifications') return json(route, { notifications: [] })
    if (path === '/public/fantasy/tok/live') return json(route, { live: false, round: null, mine: null })
    if (path === '/public/fantasy/tok/round') return json(route, { round: null, mine: null, rounds: [] })
    if (path === '/public/fantasy/tok/ladder') return json(route, { ladder: rows, my_squad_id: `s-${YOU + 1}`, live: null, teams_visible: visible })
    if (path === '/public/fantasy/tok/teams') {
      reqs.push(path)
      if (teamsStatus !== 200) return json(route, { detail: 'Teams are shown once the first round has locked.' }, teamsStatus)
      return json(route, { round: { number: 3, name: 'Round 3', status: 'scored' }, teams })
    }
    return json(route, {})
  })
  await page.goto(`${BASE}/fantasy/tok`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: start, exact: true }).first().click({ timeout: 15000 })
  return { page, ctx, errors, reqs }
}

const counter = async (page) => (await page.locator('body').innerText()).match(/(\d+) of 26/)?.[1]
const settle = (page) => page.waitForTimeout(1300)   // a swap is about half a second; leave room for it

// ── 1. Getting there ──────────────────────────────────────────────────────────
{
  const a = await open({ visible: false })
  await a.page.waitForSelector('text=Team 5', { timeout: 15000 })
  ck('before a round has locked the ladder does not offer the teams screen', (await a.page.getByText('Browse every team').count()) === 0)
  await a.ctx.close()

  const b = await open()
  await b.page.waitForSelector('text=Team 5', { timeout: 15000 })
  ck('once teams are visible the ladder offers the screen', (await b.page.getByText('Browse every team').count()) === 1)
  await b.page.getByText('Browse every team').click()
  await b.page.waitForSelector('text=as locked', { timeout: 15000 })
  ck('it makes exactly one request, GET /teams', b.reqs.length === 1 && b.reqs[0] === '/public/fantasy/tok/teams', b.reqs.join(','))
  ck('the Teams tab is in the nav', (await b.page.getByRole('button', { name: 'Teams', exact: true }).count()) >= 1)
  await b.ctx.close()
}

// ── 2. List view ──────────────────────────────────────────────────────────────
{
  const l = await open({ start: 'Teams' })
  await l.page.waitForSelector('text=as locked', { timeout: 15000 })
  ck('it opens as a list by default', (await l.page.getByRole('button', { name: /Show Team \d+'s team/ }).count()) === N)
  const body = await l.page.locator('body').innerText()
  ck('the title says which round, as locked', /ROUND 3 · AS LOCKED/i.test(body))
  const first = await l.page.getByRole('button', { name: /Show Team \d+'s team/ }).first().getAttribute('aria-label')
  ck('rows are in rank order, leader first', first === "Show Team 1's team", first)
  ck('the manager\'s own row says YOU', /Team 18[\s\S]{0,40}YOU/.test(body))
  ck('a team with no locked lineup is still listed', /Team 4/.test(body))
  await l.page.getByRole('button', { name: "Show Team 2's team" }).click()
  await l.page.waitForSelector('text=Lena Bench')
  ck('a row opens its locked XI, with no further request', (await l.page.getByText('Alice Opener').count()) >= 1 && l.reqs.length === 1, String(l.reqs.length))
  await l.page.getByRole('button', { name: "Show Team 4's team" }).click()
  await l.page.waitForSelector('text=joined after that round locked')
  ck('a team that joined late says why it has no XI', (await l.page.getByText('joined after that round locked').count()) === 1)
  const over = await l.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('1280px: no sideways scroll in the list', over <= 1, String(over))
  if (SHOTS) await l.page.screenshot({ path: `${SHOTS}/teams_list_desktop.png` })
  ck('no page errors in the list', l.errors.length === 0, l.errors.join(' | '))
  await l.ctx.close()
}

// ── 3. Card swap ──────────────────────────────────────────────────────────────
{
  const c = await open({ start: 'Teams', width: 390 })
  await c.page.waitForSelector('text=as locked', { timeout: 15000 })
  await c.page.getByRole('button', { name: 'Cards', exact: true }).click()
  await c.page.waitForSelector('text=Next ›')
  await settle(c.page)
  ck('the stack opens on the manager\'s own team (18 of 26)', (await counter(c.page)) === String(YOU + 1), await counter(c.page))
  const pngOf = async () => c.page.locator('[aria-roledescription="carousel"] > div').evaluateAll(els =>
    els.map(e => ({ z: Number(getComputedStyle(e).zIndex), o: Number(getComputedStyle(e).opacity), t: e.innerText.slice(0, 60).replace(/\n/g, ' ') })).sort((a, b) => b.z - a.z)[0])
  let top = await pngOf()
  ck('the card on top is that team and is fully visible', /TEAM 18/i.test(top.t) && top.o === 1, JSON.stringify(top))
  ck('only a few cards are drawn behind it', (await c.page.locator('[aria-roledescription="carousel"] > div').evaluateAll(els => els.filter(e => Number(getComputedStyle(e).opacity) > 0.5).length)) === 4)
  if (SHOTS) await c.page.screenshot({ path: `${SHOTS}/teams_cards_390.png`, fullPage: true })
  const over = await c.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no sideways scroll with the stack on screen', over <= 1, String(over))

  await c.page.getByRole('button', { name: 'Next ›' }).click(); await settle(c.page)
  ck('Next moves to 19 of 26', (await counter(c.page)) === '19', await counter(c.page))
  top = await pngOf()
  ck('and Team 19 is now on top', /TEAM 19/i.test(top.t), JSON.stringify(top))
  await c.page.getByRole('button', { name: '‹ Prev' }).click(); await settle(c.page)
  ck('Prev goes back to 18 of 26', (await counter(c.page)) === '18', await counter(c.page))
  top = await pngOf()
  ck('with Team 18 on top again', /TEAM 18/i.test(top.t), JSON.stringify(top))

  const box = await c.page.locator('[aria-roledescription="carousel"]').boundingBox()
  await c.page.mouse.move(box.x + box.width - 20, box.y + 200); await c.page.mouse.down()
  await c.page.mouse.move(box.x + 40, box.y + 200, { steps: 6 }); await c.page.mouse.up(); await settle(c.page)
  ck('a swipe left is Next (19 of 26)', (await counter(c.page)) === '19', await counter(c.page))
  await c.page.mouse.move(box.x + 40, box.y + 200); await c.page.mouse.down()
  await c.page.mouse.move(box.x + box.width - 20, box.y + 200, { steps: 6 }); await c.page.mouse.up(); await settle(c.page)
  ck('and a swipe right is Prev (18 of 26)', (await counter(c.page)) === '18', await counter(c.page))

  await c.page.getByLabel('Jump to a team').selectOption('9'); await settle(c.page)
  ck('the jump list goes to that team (10 of 26)', (await counter(c.page)) === '10', await counter(c.page))
  top = await pngOf()
  ck('and shows it', /TEAM 10/i.test(top.t), JSON.stringify(top))
  await c.page.getByRole('button', { name: 'My team', exact: true }).click(); await settle(c.page)
  ck('My team comes back to 18 of 26', (await counter(c.page)) === '18', await counter(c.page))
  await c.page.locator('[aria-roledescription="carousel"]').focus()
  await c.page.keyboard.press('ArrowRight'); await settle(c.page)
  ck('the arrow keys work too (19 of 26)', (await counter(c.page)) === '19', await counter(c.page))

  const [dl] = await Promise.all([
    c.page.waitForEvent('download', { timeout: 20000 }),
    c.page.getByRole('button', { name: 'Share card' }).click(),
  ])
  const path = await dl.path()
  const { readFileSync } = await import('node:fs')
  const buf = readFileSync(path)
  const isPng = buf.slice(0, 8).toString('hex') === '89504e470d0a1a0a'
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20)
  ck('Share card saves a PNG named for the team and round', isPng && dl.suggestedFilename() === 'team-19-round-3.png', dl.suggestedFilename())
  ck('at 2x the card size (600 x 1040)', w === 600 && h === 1040, `${w}x${h}`)
  if (SHOTS) { const { writeFileSync } = await import('node:fs'); writeFileSync(`${SHOTS}/teams_card_export.png`, buf) }
  ck('the off-screen copy is gone afterwards', (await c.page.locator('[aria-hidden="true"] [data-theme="dark"]').count()) === 0)

  await c.page.reload(); await c.page.waitForSelector('text=Teams', { timeout: 15000 })
  await c.page.getByRole('button', { name: 'Teams', exact: true }).first().click()
  await c.page.waitForSelector('text=as locked', { timeout: 15000 })
  ck('the chosen view is remembered across a reload', (await c.page.getByRole('button', { name: 'Next ›' }).count()) === 1)
  ck('no page errors in the card view', c.errors.length === 0, c.errors.join(' | '))
  await c.ctx.close()
}

// ── 4. Refused ────────────────────────────────────────────────────────────────
{
  const r = await open({ start: 'Teams', teamsStatus: 403 })
  await r.page.waitForSelector('text=Teams are shown once the first round has locked.', { timeout: 15000 })
  ck('a refused request says why and offers no list', (await r.page.getByRole('button', { name: /Show Team/ }).count()) === 0)
  ck('no page errors', r.errors.length === 0, r.errors.join(' | '))
  await r.ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
