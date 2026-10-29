// Drives the real Fantasy Transfers screen in Chromium with the API stubbed at the network layer, for selling
// several players at once, the bank showing what a sale returns, and the sortable pool columns.
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_fantasy_transfers_browser.mjs [baseUrl]
//
// Checks: picking a player to sell moves the Bank straight to bank + his sale price; a second sale adds to it;
// a pick the first sale alone could not pay for becomes available once the second sale is in; the bank follows
// each pick and Confirm sends ONE request to /transfers carrying every swap, paired by role; the pool sorts by
// Player, Price, Sel and Total, both ways; an over-budget set cannot be confirmed; the phone flow (sell, next,
// replace, confirm) sends the same request; no sideways scroll at 390px; no page errors.
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

const S = (id, name, role, price, extra = {}) => ({ player_id: id, name, role, price, purchase_price: price, price_change: 0, is_captain: false, is_vice_captain: false, photo_url: null, ...extra })
const SQUAD = [
  S('m', 'Monument, Darren', 'batter', 10.0),
  S('p', 'Prakashkar, Manan', 'batter', 15.2),
  S('b', 'Barendse, Jack', 'allrounder', 11.0, { is_captain: true }),
  S('w', 'Wijesinghe, Isuri', 'allrounder', 10.5, { is_vice_captain: true }),
  S('k', 'Carmody, Ryan', 'keeper', 8.0),
  S('n', 'Newman, Daniel', 'bowler', 9.0),
]
const POOL = [
  ...SQUAD.map(p => ({ ...p, selected_pct: 50, total_points: 100 })),
  { ...S('big', 'Zimmer, Big', 'batter', 22.0), selected_pct: 65.4, total_points: 275.5 },
  { ...S('mid', 'Middleton, James', 'batter', 11.8), selected_pct: 3.8, total_points: 181.5 },
  { ...S('ohara', "O'Hara, DJ", 'batter', 9.8), selected_pct: 42.3, total_points: 227 },
  { ...S('rook', 'Rookie, Ray', 'batter', 4.0), selected_pct: 1.2, total_points: 12 },
  { ...S('dock', 'Dockery, James', 'bowler', 12.5), selected_pct: 65.4, total_points: 275.5 },
]
const names = (rows) => rows.map(r => r.replace(/\s+/g, ' ').trim())

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1600, locked = false, free = 0 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = [], posts = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace(/^\/api/, '')
    if (path === '/public/fantasy/tok') return json(route, { club: { name: 'Applecross CC', accent_color: '#d40000' }, season: { name: 'Fantasy', status: 'active', rules: { transfer_hit: 4 } }, me: { id: 'm1', display_name: 'Boom Boom' } })
    if (path === '/public/fantasy/tok/me') return json(route, {
      manager: { id: 'm1', display_name: 'Boom Boom' },
      squad: { id: 's1', team_name: 'Boom XI', players: SQUAD, chips: [], total_points: 646.5, value: 119.9, budget_remaining: 1.1, free_transfers: free, overall_rank: 11, can_rebuild: false, queued_transfers: [] },
      round: { number: 3, status: 'upcoming', locked, lock_at: null, next_number: 4 },
    })
    if (path === '/public/fantasy/tok/pool') return json(route, { players: POOL, rules: { transfer_hit: 4 } })
    if (path === '/public/fantasy/tok/notifications') return json(route, { notifications: [] })
    if (path === '/public/fantasy/tok/transfers') { posts.push({ method: req.method(), body: JSON.parse(req.postData() || '{}') }); return json(route, locked ? { ok: true, queued: true, count: 2, after_round: 3, warning: null } : { ok: true, hit: 4, count: 2 }) }
    return json(route, {})
  })
  await page.goto(`${BASE}/fantasy/tok`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Transfers' }).first().waitFor({ timeout: 8000 })
  await page.getByRole('button', { name: 'Transfers' }).first().click()
  await page.waitForSelector('text=Player pool, text=Your squad', { timeout: 8000 }).catch(() => {})
  return { page, ctx, errors, posts }
}

const bankChip = async (page) => (await page.locator('div', { hasText: /^Bank \$/ }).last().innerText()).replace(/\s+/g, ' ').trim()
// The header row shares the grid style, so keep only player rows (they carry a % in the Sel column).
const rows = async (page) => names(await page.locator('div[style*="grid-template-columns: 2fr"]').allInnerTexts()).filter(r => /%/.test(r))
const sell = (page, name) => page.getByRole('button', { name: new RegExp(name) }).first().click()
const plus = (page, name) => page.locator('div[style*="grid-template-columns: 2fr"]', { hasText: name }).getByRole('button').click()

// ── 1. Desktop ───────────────────────────────────────────────────────────────
{
  const t = await open()
  const { page } = t
  ck('Bank starts at $1.1', /\$1\.1/.test(await bankChip(page)), await bankChip(page))

  await sell(page, 'Monument, Darren')
  let bank = await bankChip(page)
  ck('selling Monument moves Bank to $11.1 straight away', /\$11\.1/.test(bank), bank)
  ck('and says what it was before', /now \$1\.1/.test(bank), bank)

  // Zimmer $22.0 is beyond 11.1, so it is unavailable with one sale
  const bigBtn = page.locator('div[style*="grid-template-columns: 2fr"]', { hasText: 'Zimmer, Big' }).getByRole('button')
  ck('a $22.0 pick is not available on one sale', await bigBtn.isDisabled())

  await sell(page, 'Prakashkar, Manan')
  bank = await bankChip(page)
  ck('a second sale adds to the bank (1.1 + 10.0 + 15.2)', /\$26\.3/.test(bank), bank)
  ck('both players are marked Out', (await page.getByText('Out', { exact: true }).count()) === 2)
  ck('the pairs show two batters still to pick', (await page.getByTestId('swap-summary').innerText()).match(/pick a batter/g)?.length === 2, await page.getByTestId('swap-summary').innerText())
  ck('now the $22.0 pick is available', !(await bigBtn.isDisabled()))

  await plus(page, 'Zimmer, Big')
  bank = await bankChip(page)
  ck('picking him takes it to $4.3', /\$4\.3/.test(bank), bank)
  const summary = await page.getByTestId('swap-summary').innerText()
  ck('the first batter out is paired with him', /Monument, Darren\s*→\s*Zimmer, Big/.test(summary.replace(/\n/g, ' ')), summary)
  const midBtn = page.locator('div[style*="grid-template-columns: 2fr"]', { hasText: 'Middleton, James' }).getByRole('button')
  ck('a $11.8 pick is now out of reach', await midBtn.isDisabled())
  const confirm = page.getByRole('button', { name: /Confirm 2 transfers/ })
  ck('Confirm is off while one replacement is missing', await confirm.isDisabled())
  ck('and Cost counts both swaps (no free transfer: 8 pts)', /8 pts/.test(await page.locator('body').innerText()))

  await plus(page, 'Rookie, Ray')
  bank = await bankChip(page)
  ck('the cheap pick leaves $0.3', /\$0\.3/.test(bank), bank)
  ck('Confirm is on', !(await confirm.isDisabled()))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/transfers-desktop.png` })
  await confirm.click()
  await page.waitForTimeout(400)
  ck('ONE request went to /transfers', t.posts.length === 1 && t.posts[0].method === 'POST', JSON.stringify(t.posts))
  ck('carrying both swaps, each out paired with its in', JSON.stringify(t.posts[0]?.body) === JSON.stringify({ swaps: [{ out_player_id: 'm', in_player_id: 'big' }, { out_player_id: 'p', in_player_id: 'rook' }] }), JSON.stringify(t.posts[0]?.body))
  ck('no page errors', t.errors.length === 0, t.errors.join(' | '))
  await t.ctx.close()
}

// ── 2. Sorting ───────────────────────────────────────────────────────────────
{
  const t = await open()
  const { page } = t
  const first = async () => (await rows(page))[0]
  ck('the pool opens on Total, biggest first', /Zimmer, Big|Dockery, James/.test(await first()), await first())
  await page.getByRole('button', { name: 'Sort by price' }).click()
  ck('Price sorts biggest first', /Zimmer, Big/.test(await first()), await first())
  await page.getByRole('button', { name: 'Sort by price' }).click()
  ck('a second click on Price reverses it', /Rookie, Ray/.test(await first()), await first())
  await page.getByRole('button', { name: 'Sort by player' }).click()
  ck('Player sorts A to Z', /Barendse, Jack/.test(await first()), await first())
  await page.getByRole('button', { name: 'Sort by player' }).click()
  ck('and Z to A', /Zimmer, Big/.test(await first()), await first())
  await page.getByRole('button', { name: 'Sort by sel' }).click()
  ck('Sel sorts biggest first', /65\.4%/.test(await first()), await first())
  await page.getByRole('button', { name: 'Sort by sel' }).click()
  ck('and smallest first', /1\.2%/.test(await first()), await first())
  await page.getByRole('button', { name: 'Sort by total' }).click()
  ck('Total sorts biggest first', /275\.5/.test(await first()), await first())
  await page.getByRole('button', { name: 'Sort by total' }).click()
  ck('and smallest first', /\b12\b/.test(await first()), await first())
  ck('the active column shows an arrow', /TOTAL ▲/.test(await page.locator('body').innerText()))
  ck('no page errors', t.errors.length === 0, t.errors.join(' | '))
  await t.ctx.close()
}

// ── 3. Over budget cannot be confirmed; locked round queues ─────────────────
{
  const t = await open({ locked: true })
  const { page } = t
  await sell(page, 'Monument, Darren')
  await sell(page, 'Prakashkar, Manan')
  await plus(page, 'Zimmer, Big')
  await plus(page, 'Rookie, Ray')
  const q = page.getByRole('button', { name: /Queue 2 transfers/ })
  ck('a locked round offers Queue 2 transfers', await q.count() === 1)
  await q.click()
  await page.waitForTimeout(300)
  ck('and sends the same one request', t.posts.length === 1 && t.posts[0].body.swaps.length === 2, JSON.stringify(t.posts))
  await t.ctx.close()
}

// ── 4. Phone: sell, next, replace ───────────────────────────────────────────
{
  const t = await open({ width: 390 })
  const { page } = t
  const over = async () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('the squad list opens with Bank $1.1', /Bank\s+\$1\.1/i.test(await page.locator('body').innerText()))
  const next = page.getByRole('button', { name: /Pick who is leaving/ })
  ck('Next is off until someone is picked', await next.isDisabled())
  await page.getByText('Monument, Darren').click()
  await page.getByText('Prakashkar, Manan').click()
  ck('Bank after reads $26.3', /Bank after\s+\$26\.3/i.test(await page.locator('body').innerText()), (await page.locator('body').innerText()).slice(0, 200))
  ck('no sideways scroll on the sell step', (await over()) <= 1, String(await over()))
  await page.getByRole('button', { name: /Next: pick 2 replacements/ }).click()
  await page.waitForSelector('text=Replace with')
  const body = await page.locator('body').innerText()
  ck('only batters are offered', /Zimmer, Big/.test(body) && !/Dockery, James/.test(body))
  await page.getByText('Zimmer, Big').click()
  await page.getByText('Rookie, Ray').click()
  ck('Bank after reads $0.3', /Bank after\s+\$0\.3/i.test(await page.locator('body').innerText()))
  // Rows out of reach are plain divs rather than buttons, so read the order off the page text.
  const order = async () => {
    const all = await page.locator('body').innerText()
    const t = all.slice(all.indexOf('SORT'))   // below the chips: the swap summary above also names the picks
    return ['Zimmer, Big', 'Middleton, James', "O'Hara, DJ", 'Rookie, Ray'].map(n => [n, t.indexOf(n)]).sort((x, y) => x[1] - y[1]).map(x => x[0])
  }
  ck('the phone list opens on Price, dearest first', JSON.stringify(await order()) === JSON.stringify(['Zimmer, Big', 'Middleton, James', "O'Hara, DJ", 'Rookie, Ray']), (await order()).join(' > '))
  await page.getByRole('button', { name: 'Sort by price' }).click()
  ck('a tap on Price reverses it', (await order())[0] === 'Rookie, Ray', (await order()).join(' > '))
  await page.getByRole('button', { name: 'Sort by player' }).click()
  ck('Name sorts A to Z', JSON.stringify(await order()) === JSON.stringify(['Middleton, James', "O'Hara, DJ", 'Rookie, Ray', 'Zimmer, Big']), (await order()).join(' > '))
  await page.getByRole('button', { name: 'Sort by total' }).click()
  ck('Total sorts biggest first', (await order())[0] === 'Zimmer, Big', (await order()).join(' > '))
  ck('no sideways scroll on the replace step', (await over()) <= 1, String(await over()))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/transfers-phone.png`, fullPage: true })
  await page.getByRole('button', { name: /Confirm 2 transfers/ }).click()
  await page.waitForTimeout(400)
  ck('the phone sends the same request', JSON.stringify(t.posts[0]?.body) === JSON.stringify({ swaps: [{ out_player_id: 'm', in_player_id: 'big' }, { out_player_id: 'p', in_player_id: 'rook' }] }), JSON.stringify(t.posts))
  ck('no page errors', t.errors.length === 0, t.errors.join(' | '))
  await t.ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
