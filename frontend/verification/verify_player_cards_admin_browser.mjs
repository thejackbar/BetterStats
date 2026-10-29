// The Player Cards admin screen (/admin/player-cards) against the real page with the API stubbed at the network
// layer: the Overview numbers, the Players table (search, sort, a click through to one player's whole collection),
// Activity (special cards and cards added lately, packs opened), All cards (the exact query each filter sends, paging),
// Packs (who has and has not opened one), the Swap audit (filters and search) and Settings (the exact PATCH each
// control sends, hiding and showing a player). 390px on every tab, and no page errors.
//
//   APP_URL=http://localhost:4173 SHOT_DIR=/tmp/cards3 node verification/verify_player_cards_admin_browser.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
if (SHOT) fs.mkdirSync(SHOT, { recursive: true })
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}

// A real PNG, so the browser decodes what a test uploads.
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAgAAAAMCAIAAADQ/GvKAAAAEklEQVR4nGOQizqBFTGMSqAjABWGeAGPl/lFAAAAAElFTkSuQmCC', 'base64')
const CLUB = { name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c', font_config: {} }
const state = {
  settings: { enabled: true, include_juniors: false, weekly_packs: 1, timezone: null, effective_timezone: 'Australia/Perth', event_packs_enabled: true, starter_gifts: 'minimal', big_photos: 'all' },
  events: [],
  gifts: [],
  players: [
    { id: 'a1', display_name: 'Adams, Brian', hidden: false, in_pool: true, matches: 260, rarity: 81, tier: 'epic', excluded: null },
    { id: 'b2', display_name: 'Baker, Chris', hidden: false, in_pool: true, matches: 12, rarity: 22, tier: 'common', excluded: null },
    { id: 'c3', display_name: 'Young, Kid', hidden: false, in_pool: false, matches: 8, rarity: null, tier: null, excluded: 'junior' },
    { id: 'd4', display_name: 'Hidden, Pat', hidden: false, in_pool: false, matches: 40, rarity: null, tier: null, excluded: 'private' },
    { id: 'e5', display_name: 'New, Nick', hidden: false, in_pool: false, matches: 0, rarity: 1, tier: 'common', excluded: null },
  ],
}
const QUALITIES = [['standard', 'Standard', 1, 5], ['boosted', 'Boosted', 2, 8], ['special', 'Special', 2, 10], ['premium', 'Premium', 3, 10], ['elite', 'Elite', 4, 15], ['legendary', 'Legendary', 4, 15]]
  .map(([key, label, rare_plus, special_pct]) => ({ key, label, line: `${label} line`, rare_plus, special_pct, odds: { common: 40, rare: 35, epic: 20, legendary: 5 } }))
const settingsPayload = () => ({
  club: CLUB, settings: state.settings, events: state.events, gifts: state.gifts, max_gift_qty: 10, pack_size: { default: 5, min: 1, max: 12 }, qualities: QUALITIES,
  timezones: [{ id: 'Australia/Perth', label: 'Western Australia' }, { id: 'Australia/Sydney', label: 'New South Wales, ACT' }],
  max_weekly_packs: 10, link: { path: '/playerdash/tok123' },
  pool: { size: state.players.filter((p) => p.in_pool).length, players: state.players.length }, players: state.players,
})
const prow = (id, name, x = {}) => ({ id, name, in_pool: true, rarity: 50, tier: 'rare', cards: 5, regular: 4, specials: 1, copies: 7, collected_pct: 33, packs_opened: 0, packs_waiting: 2, opened_7d: 0, first_opened_at: null, last_opened_at: null, last_card_at: null, swaps: 0, swaps_done: 0, ...x })
const OV = {
  totals: { pool: 12, players_in_pool: 3, players_opened: 2, players_never_opened: 1, players_opened_7d: 1, copies: 40, packs_opened: 14, specials: 30, specials_7d: 4, swaps: 5, swaps_done: 2, swaps_open: 1 },
  players: [
    prow('a1', 'Adams, Brian', { packs_opened: 9, packs_waiting: 0, regular: 9, collected_pct: 75, copies: 20, first_opened_at: '2026-10-01T01:00:00Z', last_opened_at: '2026-10-25T01:00:00Z', swaps: 2, swaps_done: 2, opened_7d: 3 }),
    prow('b2', 'Baker, Chris', { packs_opened: 5, regular: 3, collected_pct: 25, copies: 9, first_opened_at: '2026-10-10T01:00:00Z', last_opened_at: '2026-10-12T01:00:00Z' }),
    prow('f6', 'Zed, Zak', { packs_opened: 0, regular: 1, collected_pct: 8, copies: 1, packs_waiting: 3 }),
    prow('c3', 'Young, Kid', { in_pool: false, cards: 0, regular: 0, specials: 0, copies: 0, collected_pct: 0, packs_waiting: 0 }),
  ],
}
const day = (i) => new Date(Date.now() - (13 - i) * 86400000).toISOString().slice(0, 10)
const ACT = {
  daily: Array.from({ length: 14 }, (_, i) => ({ day: day(i), specials_added: i === 13 ? 4 : 0, packs_opened: i % 3, swaps: i === 12 ? 1 : 0 })),
  recent_specials: [
    { id: 's1', kind: 'century', title: 'Century', player: 'Adams, Brian', player_id: 'a1', occurred_on: '2026-10-24', added_at: '2026-10-25T02:00:00Z', held: 3 },
    { id: 's2', kind: 'award', title: 'Best Bowler', player: 'Baker, Chris', player_id: 'b2', occurred_on: null, added_at: '2026-10-20T02:00:00Z', held: 1 },
  ],
  recent_cards: [
    { owner: 'Adams, Brian', owner_id: 'a1', source: 'pack', new_to_owner: true, obtained_at: '2026-10-25T01:00:00Z', kind: 'player', title: 'Card', player: 'Baker, Chris', tier: 'common' },
    { owner: 'Baker, Chris', owner_id: 'b2', source: 'swap', new_to_owner: false, obtained_at: '2026-10-24T01:00:00Z', kind: 'special', title: 'Century', player: 'Adams, Brian', tier: 'special' },
  ],
  recent_openings: [{ id: 'k1', player: 'Adams, Brian', player_id: 'a1', source: 'weekly', opened_at: '2026-10-25T01:00:00Z', best: 'epic', cards: [{ kind: 'player', title: 'Card', player: 'Zed, Zak', tier: 'epic' }, { kind: 'player', title: 'Card', player: 'Baker, Chris', tier: 'common' }] }],
}
const card = (pid, name, tier, x = {}) => ({ kind: 'player', key: `p:${pid}`, player_id: pid, name, photo_url: null, hero_photo_url: null, matches: 50, runs: 900, bat_avg: 20.1, wickets: 10, bowl_avg: 25, dismissals: 12, rarity: 60, tier, held: 3, owners: 2, copies: 1, ...x })
const CAT = [
  card('a1', 'Adams, Brian', 'epic', { rarity: 81 }), card('b2', 'Baker, Chris', 'common', { rarity: 22, held: 1, owners: 1 }),
  { kind: 'special', key: 's:s1', special_id: 's1', special_kind: 'century', player_id: 'a1', name: 'Adams, Brian', photo_url: null, hero_photo_url: null, title: 'Century', occurred_on: '2026-10-24', detail: { runs: 112, not_out: true, opposition: 'Rovers' }, tier: 'special', held: 3, owners: 3, added_at: '2026-10-25T02:00:00Z', copies: 1 },
]
const PLAYER = {
  player: { id: 'a1', name: 'Adams, Brian', in_pool: true, rarity: 81, tier: 'epic' },
  totals: { regular_owned: 9, regular_total: 12, special_owned: 2, special_total: 30, copies: 20 },
  cards: [card('a1', 'Adams, Brian', 'epic', { mine: true, copies: 2 }), card('b2', 'Baker, Chris', 'common'), CAT[2]],
  packs: { by_source: [{ source: 'weekly', opened: 6, waiting: 0 }, { source: 'duck', opened: 3, waiting: 0 }], recent: [{ id: 'k1', source: 'weekly', granted_at: '2026-10-25T00:00:00Z', opened_at: '2026-10-25T01:00:00Z' }] },
  recent_cards: [{ source: 'pack', obtained_at: '2026-10-25T01:00:00Z', kind: 'player', title: 'Card', player: 'Baker, Chris', tier: 'common' }],
  swaps: [{ id: 'w1', status: 'accepted', from: { id: 'a1', name: 'Adams, Brian' }, to: { id: 'b2', name: 'Baker, Chris' }, give: [{ kind: 'player', player: 'Zed, Zak', tier: 'rare', title: 'Card', qty: 1 }, { kind: 'player', player: 'Moss, Max', tier: 'common', title: 'Card', qty: 2 }], want: [{ kind: 'special', player: 'Adams, Brian', title: 'Century', tier: 'special', qty: 1 }], created_at: '2026-10-24T01:00:00Z', resolved_at: '2026-10-24T05:00:00Z' }],
}
const swap = (id, status, from, to) => ({ id, status, from: { id: 'x', name: from }, to: { id: 'y', name: to }, give: [{ kind: 'player', player: 'Zed, Zak', tier: 'rare', title: 'Card', qty: 1 }, { kind: 'player', player: 'Moss, Max', tier: 'common', title: 'Card', qty: 2 }], want: [{ kind: 'special', player: 'Adams, Brian', title: 'Century', tier: 'special', qty: 1 }], created_at: '2026-10-20T01:00:00Z', resolved_at: status === 'pending' ? null : '2026-10-21T01:00:00Z' })
const SWAPS = [swap('w1', 'accepted', 'Adams, Brian', 'Baker, Chris'), swap('w2', 'declined', 'Baker, Chris', 'Zed, Zak'), swap('w3', 'pending', 'Zed, Zak', 'Adams, Brian'), swap('w4', 'cancelled', 'Zed, Zak', 'Baker, Chris'), swap('w5', 'expired', 'Baker, Chris', 'Adams, Brian')]

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  page.setDefaultTimeout(10000)
  const errors = [], calls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errors.push(m.text()) })
  await page.route('**/api/**', async (route) => {
    const req = route.request(), url = req.url(), method = req.method()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(url)) return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', entitlements: { modules: [], status: 'active' } })
    if (!/\/player-cards\//.test(url)) return json({})
    const u = new URL(url)
    const path = u.pathname.replace(/^\/api/, '')
    const multipart = (req.headers()['content-type'] || '').includes('multipart')
    const raw = multipart ? (req.postDataBuffer() || Buffer.from('')).toString('latin1') : null
    const body = !multipart && req.postData() ? JSON.parse(req.postData()) : null
    calls.push({ method, path, query: u.search.replace(/^\?/, ''), body, multipart, raw })
    if (path === '/player-cards/overview') return json(OV)
    if (path === '/player-cards/activity') return json(ACT)
    if (path === '/player-cards/wanted') return json({ total_wants: 7, cards: [{ key: 'p:a1', kind: 'player', player: 'Adams, Brian', tier: 'epic', title: 'Card', wanted_by: 4, could_swap: 2 }, { key: 's:x', kind: 'special', player: 'Baker, Chris', title: 'Century', tier: 'special', wanted_by: 3, could_swap: 0 }] })
    if (path === '/player-cards/catalogue') {
      const q = u.searchParams
      let items = CAT.filter((c) => (q.get('kind') === 'player' ? c.kind === 'player' : q.get('kind') === 'special' ? c.kind === 'special' : true))
      if (q.get('special_kind')) items = items.filter((c) => c.special_kind === q.get('special_kind'))
      if (q.get('q')) items = items.filter((c) => c.name.toLowerCase().includes(q.get('q').toLowerCase()))
      const off = Number(q.get('offset') || 0)
      return json({ total: items.length + (off === 0 && items.length === 3 ? 40 : 0), counts: { player: 2, special: 1 }, items: items.slice(off), offset: off, limit: Number(q.get('limit')) })
    }
    const pl = path.match(/\/player-cards\/players\/([^/]+)$/)
    if (pl && method === 'GET') return json(PLAYER)
    if (path === '/player-cards/swaps') {
      const st = u.searchParams.get('status') || 'all'
      const rows = SWAPS.filter((s) => (st === 'all' ? true : s.status === st)).filter((s) => !u.searchParams.get('q') || (s.from.name + s.to.name).toLowerCase().includes(u.searchParams.get('q').toLowerCase()))
      return json({ total: rows.length, counts: { accepted: 1, declined: 1, cancelled: 1, pending: 1, expired: 1 }, swaps: rows, offset: 0, limit: 50 })
    }
    if (path === '/player-cards/events' && method === 'POST') { state.events.push({ id: `e${state.events.length + 1}`, title: body.title, starts_on: body.starts_on, ends_on: body.ends_on || body.starts_on, per_day: body.per_day, quality: body.quality }); return json(settingsPayload()) }
    if (path === '/player-cards/gifts/designed' && method === 'POST') {
      const field = (name) => (raw.match(new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r]*)`)) || [])[1]
      const gift = { id: `g${state.gifts.length + 1}`, title: field('title'), quality: field('quality'), qty: Number(field('qty')), size: Number(field('size')), audience: field('audience'), players: 3, packs: 3 * Number(field('qty')), opened: 0, created_at: '2026-10-28T01:00:00Z' }
      state.gifts.unshift(gift)
      return json({ gift, ...settingsPayload() })
    }
    if (path === '/player-cards/gifts' && method === 'POST') {
      const n = body.audience === 'all' ? 3 : body.player_ids.length
      const gift = { id: `g${state.gifts.length + 1}`, title: body.title, quality: body.quality, qty: body.qty, size: body.size, audience: body.audience, players: n, packs: n * body.qty, opened: 0, created_at: '2026-10-28T01:00:00Z' }
      state.gifts.unshift(gift)
      return json({ gift, ...settingsPayload() })
    }
    const evDel = path.match(/\/player-cards\/events\/([^/]+)$/)
    if (evDel && method === 'DELETE') { state.events = state.events.filter((e) => e.id !== evDel[1]); return json(settingsPayload()) }
    if (path === '/player-cards/trim-gifts') return json(body.apply ? { cards: 14, players: 6, applied: true } : { cards: 14, players: 6, applied: false })
    if (method === 'PATCH') Object.assign(state.settings, body)
    const hide = path.match(/\/players\/([^/]+)\/hidden$/)
    if (hide) { const p = state.players.find((x) => x.id === hide[1]); p.hidden = body.hidden; p.in_pool = !body.hidden && p.matches > 0 }
    if (/refresh-specials/.test(path)) return json({ made: { century: 2, fifty: 0 } })
    return json(settingsPayload())
  })
  const shot = async (name) => { if (SHOT) await page.screenshot({ path: `${SHOT}/${name}.png`, fullPage: true }) }
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  const tab = async (k) => { await page.click(`[data-pc-tab="${k}"]`); await page.waitForTimeout(250) }
  const text = () => page.locator('[data-player-cards-admin]').innerText()
  const last = () => calls[calls.length - 1]

  await page.goto(`${BASE}/admin/player-cards`)
  await page.waitForSelector('[data-pc-tab="overview"]', { timeout: 20000 })
  await page.waitForSelector('[data-stat]')

  console.log('\noverview')
  check('eight tabs', (await page.locator('[data-pc-tab]').count()) === 8)
  const stat = (n) => page.locator(`[data-stat="${n}"]`).innerText()
  check('players who have opened a pack, and who have not', /2/.test(await stat('Have opened a pack')) && /1 have not/.test(await stat('Have opened a pack')))
  check('packs opened and cards held', /14/.test(await stat('Packs opened')) && /40 cards held/.test(await stat('Packs opened')))
  check('special cards and how many are new this week', /30/.test(await stat('Special cards')) && /4 added this week/.test(await stat('Special cards')))
  check('swaps made, asked and open', /2/.test(await stat('Swaps made')) && /5 asked, 1 open/.test(await stat('Swaps made')))
  check('a two week chart of packs, special cards and swaps', (await page.locator('[data-daily] > div > div').count()) === 14)
  await shot('01-overview')

  console.log('\nplayers')
  await tab('players')
  const names = () => page.locator('[data-player-row]').evaluateAll((els) => els.map((e) => e.getAttribute('data-player-row')))
  check('the card pool is listed, a player outside it is not (until asked for)', JSON.stringify(await names()) === JSON.stringify(['a1', 'b2', 'f6']), JSON.stringify(await names()))
  await page.selectOption('select[aria-label="Show"]', 'all')
  check('"Everyone" adds the players outside the pool', (await names()).length === 4)
  await page.selectOption('select[aria-label="Show"]', 'pool')
  await page.locator('[data-players-table] th', { hasText: 'Packs opened' }).click()
  check('sorting by packs opened puts the busiest first', (await names())[0] === 'a1')
  await page.locator('[data-players-table] th', { hasText: 'Packs opened' }).click()
  check('and again, the quietest first', (await names())[0] === 'f6')
  const rowZ = await page.locator('[data-player-row="f6"]').innerText()
  check('a player who never opened one says Never', /Never/.test(rowZ))
  await page.getByLabel('Find a player').fill('bak')
  check('search narrows the table', JSON.stringify(await names()) === JSON.stringify(['b2']))
  await page.getByLabel('Find a player').fill('')
  await shot('02-players')
  calls.length = 0
  await page.click('[data-open-player="a1"]')
  await page.waitForSelector('[data-player-panel="a1"]')
  check('clicking a name asks for that one player', calls.some((c) => c.method === 'GET' && c.path === '/player-cards/players/a1'), JSON.stringify(calls))
  check('their whole collection is shown as cards, in groups', (await page.locator('[data-grid-card]').count()) === 3 && /player cards \(2\)/i.test(await page.locator("[data-card-grid]").innerText()) && /centuries \(1\)/i.test(await page.locator("[data-card-grid]").innerText()))
  check('with their packs, what they got lately and their swaps', /Weekly pack/.test(await text()) && /Baker, Chris \(Common\)/.test(await text()) && (await page.locator('[data-swap-row="accepted"]').count()) === 1)
  await shot('03-player')
  await page.getByRole('button', { name: /All players/ }).click()
  check('Back returns to the table', (await page.locator('[data-players-table]').count()) === 1)

  console.log('\nactivity')
  await tab('activity')
  check('the most wanted cards show demand and how many could swap, with no names of who wants them', (await page.locator('[data-most-wanted] tbody tr').count()) === 2 && /Adams, Brian \(Epic\)/.test(await page.locator('[data-most-wanted]').innerText()) && !/wishlist|wish list of/i.test(await page.locator('[data-most-wanted]').innerText()))
  check('special cards added lately, with who, when and how many hold them', (await page.locator('[data-recent-specials] tbody tr').count()) === 2 && /Century/.test(await page.locator('[data-recent-specials]').innerText()))
  check('cards pulled or swapped in, marked new or a double', /NEW/.test(await page.locator('[data-recent-cards]').innerText()) && /double/.test(await page.locator('[data-recent-cards]').innerText()) && /swap/.test(await page.locator('[data-recent-cards]').innerText()))
  check('packs opened lately with the best card', /opened a weekly pack/.test(await page.locator('[data-recent-openings]').innerText()))
  await shot('04-activity')
  await page.locator('[data-recent-specials]').getByRole('button', { name: 'Adams, Brian' }).click()
  await page.waitForSelector('[data-player-panel="a1"]')
  check('a name in the feed opens that player', true)

  console.log('\nall cards')
  await tab('cards')
  await page.waitForSelector('[data-catalogue-card]')
  check('the first request asks for the rarest 36 of everything', last().query === 'kind=all&sort=rarity&limit=36&offset=0', JSON.stringify(last()))
  check('each card shows copies held and owners', /3 copies · 2 owners/.test(await page.locator('[data-catalogue-card="p:a1"]').innerText()) && /1 copy · 1 owner/.test(await page.locator('[data-catalogue-card="p:b2"]').innerText()))
  check('a special card says when it was added', /added/.test(await page.locator('[data-catalogue-card="s:s1"]').innerText()))
  await shot('05-cards')
  await page.selectOption('select[aria-label="Kind"]', 'special')
  await page.waitForFunction(() => document.querySelectorAll('[data-catalogue-card]').length === 1)
  check('picking specials sends kind=special', last().query.startsWith('kind=special'), last().query)
  await page.selectOption('select[aria-label="Kind of special"]', 'century')
  await page.waitForFunction(() => document.querySelectorAll('[data-catalogue-card]').length === 1)
  check('picking a kind of special sends it', /special_kind=century/.test(last().query), last().query)
  await page.selectOption('select[aria-label="Kind"]', 'all')
  await page.getByLabel('Find a card').fill('baker')
  await page.waitForFunction(() => document.querySelectorAll('[data-catalogue-card]').length === 1)
  check('search sends q (after a short pause)', /q=baker/.test(last().query), last().query)
  await page.getByLabel('Find a card').fill('')
  await page.waitForFunction(() => document.querySelectorAll('[data-catalogue-card]').length === 3)
  await page.getByRole('button', { name: /Show more/ }).click()
  await page.waitForFunction(() => true)
  check('Show more asks for the next page by offset', calls.some((c) => c.path === '/player-cards/catalogue' && /offset=3/.test(c.query)), JSON.stringify(calls.slice(-3)))

  console.log('\npacks')
  await tab('packs')
  check('who has opened packs, most recent first, with first and last dates', JSON.stringify(await page.locator('[data-openers] button').allTextContents()) === JSON.stringify(['Adams, Brian', 'Baker, Chris']))
  check('who has not opened one', JSON.stringify(await page.locator('[data-never-opened] button').allTextContents()) === JSON.stringify(['Zed, Zak']) && /3 waiting/.test(await page.locator('[data-never-opened]').innerText()))
  await shot('06-packs')

  console.log('\nswap audit')
  await tab('swaps')
  await page.waitForSelector('[data-swap-table]')
  check('every swap, with who asked, who was asked, both cards and the result', (await page.locator('[data-swap-row]').count()) === 5 && /Adams, Brian/.test(await page.locator('[data-swap-row="accepted"]').innerText()) && /Century/.test(await page.locator('[data-swap-row="accepted"]').innerText()))
  check('each ending is told apart', ['accepted', 'declined', 'pending', 'cancelled', 'expired'].every((s) => ['x'].length && page.locator(`[data-swap-row="${s}"]`).count()))
  await page.click('[data-swap-filter="accepted"]')
  await page.waitForFunction(() => document.querySelectorAll('[data-swap-row]').length === 1)
  check('the filter sends the status', /status=accepted/.test(last().query), last().query)
  await page.click('[data-swap-filter="all"]')
  await page.getByLabel('Find a swap by player').fill('zed')
  await page.waitForFunction(() => document.querySelectorAll('[data-swap-row]').length === 3)
  check('search sends the name', /q=zed/.test(last().query), last().query)
  await page.getByLabel('Find a swap by player').fill('')
  await page.click('[data-swap-filter="countered"]')
  await page.waitForTimeout(500)
  check('Changed is a filter and sends its status', /status=countered/.test(last().query), last().query)
  await page.click('[data-swap-filter="all"]')
  await shot('07-swaps')

  console.log('\nsettings')
  await tab('settings')
  await page.waitForSelector('[data-card-player]')
  check('the pool count is in the heading', /Players in the card pool \(2 of 5\)/i.test(await text()))
  check('cards are on and juniors are off by default', (await page.getByRole('switch', { name: 'Player Cards are on' }).getAttribute('aria-checked')) === 'true' && (await page.getByRole('switch', { name: 'Include junior players' }).getAttribute('aria-checked')) === 'false')
  check('the player page link is shown', /\/playerdash\/tok123/.test(await page.locator('[data-player-page-link]').innerText()))
  const reasons = await page.locator('[data-card-player]').evaluateAll((els) => Object.fromEntries(els.map((e) => [e.getAttribute('data-card-player'), e.innerText])))
  check('a junior and a privacy-hidden player are shown as out, with the reason', /Junior player, and juniors are switched off/.test(reasons.c3) && /Hidden from the public site/.test(reasons.d4))
  check('no Hide button for those', !/Hide|Show/.test(reasons.c3) && !/Hide|Show/.test(reasons.d4) && /Hide/.test(reasons.a1))
  await page.getByRole('switch', { name: 'Include junior players' }).click()
  await page.waitForFunction(() => document.querySelector('[role="switch"][aria-label="Include junior players"]').getAttribute('aria-checked') === 'true')
  check('a switch sends only what it changed', JSON.stringify(calls.filter((c) => c.method === 'PATCH').pop().body) === '{"include_juniors":true}')
  await page.getByRole('switch', { name: 'Include junior players' }).click()
  for (const [name, key] of [['Sets are on', 'sets_enabled'], ['Showcases are on', 'showcase_enabled'], ['The collectors board is on', 'board_enabled'], ['This week at the club is on', 'feed_enabled']]) {
    await page.getByRole('switch', { name }).click()
    await page.waitForFunction((n) => document.querySelector(`[role="switch"][aria-label="${n}"]`).getAttribute('aria-checked') === 'false', name)
    check(`the ${name.toLowerCase()} switch sends ${key} false and nothing else`, JSON.stringify(calls.filter((c) => c.method === 'PATCH').pop().body) === `{"${key}":false}`)
    await page.getByRole('switch', { name }).click()
  }
  check('card emails are on by default, and the switch sends only alerts_enabled', (await page.getByRole('switch', { name: 'Card emails are on' }).getAttribute('aria-checked')) === 'true')
  await page.getByRole('switch', { name: 'Card emails are on' }).click()
  await page.waitForFunction(() => document.querySelector('[role="switch"][aria-label="Card emails are on"]').getAttribute('aria-checked') === 'false')
  check('turning card emails off sends alerts_enabled false and nothing else', JSON.stringify(calls.filter((c) => c.method === 'PATCH').pop().body) === '{"alerts_enabled":false}')
  await page.getByRole('switch', { name: 'Card emails are on' }).click()
  check('day packs are on by default, and the switch sends only event_packs_enabled', (await page.getByRole('switch', { name: 'Day packs are on' }).getAttribute('aria-checked')) === 'true')
  await page.getByRole('switch', { name: 'Day packs are on' }).click()
  await page.waitForFunction(() => document.querySelector('[role="switch"][aria-label="Day packs are on"]').getAttribute('aria-checked') === 'false')
  check('turning them off sends event_packs_enabled false only', JSON.stringify(calls.filter((c) => c.method === 'PATCH').pop().body) === '{"event_packs_enabled":false}')
  await page.getByRole('switch', { name: 'Day packs are on' }).click()
  check('photos on cards default to every card with a photo, and say what that means', (await page.getByLabel('Cards that fill with a photo').inputValue()) === 'all' && /Every card fills with the player.s hero photo/.test(await page.locator('[data-photo-note]').innerText()))
  await page.getByLabel('Cards that fill with a photo').selectOption('specials')
  await page.waitForFunction(() => document.querySelector('select[aria-label="Cards that fill with a photo"]').value === 'specials')
  check('changing it sends big_photos only', JSON.stringify(calls.filter((c) => c.method === 'PATCH').pop().body) === '{"big_photos":"specials"}')
  check('the note follows the choice', /Every regular card shows the profile photo/.test(await page.locator('[data-photo-note]').innerText()))
  await page.getByLabel('Cards that fill with a photo').selectOption('all')
  check('starting cards default to the minimal set', (await page.getByLabel('Starting cards').inputValue()) === 'minimal')
  await page.getByLabel('Starting cards').selectOption('all')
  await page.waitForFunction(() => document.querySelector('select[aria-label="Starting cards"]').value === 'all')
  check('changing them sends starter_gifts only', JSON.stringify(calls.filter((c) => c.method === 'PATCH').pop().body) === '{"starter_gifts":"all"}')
  await page.getByLabel('Starting cards').selectOption('minimal')
  await page.locator('[data-trim-check]').click()
  await page.waitForSelector('[data-trim-result]')
  check('tidying counts first and removes nothing (a dry run)', /14 starting cards held by 6 players would be removed/.test(await page.locator('[data-trim-result]').innerText()) && JSON.stringify(calls.filter((c) => /trim-gifts/.test(c.path)).pop().body) === '{"apply":false}')
  await page.locator('[data-trim-apply]').click()
  await page.waitForFunction(() => /Done\./.test(document.querySelector('[data-trim-result]').innerText))
  check('...and only a second, deliberate click applies it', JSON.stringify(calls.filter((c) => /trim-gifts/.test(c.path)).pop().body) === '{"apply":true}')
  await page.locator('[data-create-pack]').scrollIntoViewIfNeeded()
  await shot('09-make-a-pack')
  check('the create form starts on "give them out now" with nothing to press until it has a name', (await page.locator('[data-when-now]').isChecked()) && (await page.getByRole('button', { name: /^Give .* now$/ }).isDisabled()))
  check('every quality is offered with what it guarantees and how it is weighted', (await page.locator('[data-quality]').count()) === 6 && /At least 4 of 5 Rare or better/.test(await page.locator('[data-quality="legendary"]').innerText()) && /Epic 20%/.test(await page.locator('[data-quality="elite"]').innerText()))
  check('special is picked to begin with', (await page.locator('[data-quality="special"]').getAttribute('aria-checked')) === 'true')
  await page.getByLabel('Name of the pack').fill('Grand Final winners')
  await page.locator('[data-quality="legendary"]').click()
  await page.getByLabel('Packs for each player').selectOption('2')
  check('the button says how many packs go out to how many players', (await page.getByRole('button', { name: /^Give 6 packs now$/ }).count()) === 1 && /2 packs each to 3 players/.test(await page.locator('[data-create-pack]').innerText()))
  check('the preview pack takes the name and shows the quality in stars', /Grand Final winners/i.test(await page.locator('[data-create-preview] [data-pack-name]').innerText()) && (await page.locator('[data-create-preview] [data-pack-stars]').getAttribute('data-pack-stars')) === '5')
  calls.length = 0
  await page.getByRole('button', { name: /^Give 6 packs now$/ }).click()
  await page.waitForSelector('[data-create-done]')
  const gift = calls.find((c) => c.path === '/player-cards/gifts')
  check('giving sends the name, quality, quantity, audience and a request id, and nothing else', gift && JSON.stringify(Object.keys(gift.body)) === JSON.stringify(['title', 'quality', 'qty', 'size', 'audience', 'player_ids', 'request_id']) && gift.body.title === 'Grand Final winners' && gift.body.quality === 'legendary' && gift.body.qty === 2 && gift.body.audience === 'all' && gift.body.player_ids.length === 0 && /^[0-9a-f-]{36}$/.test(gift.body.request_id), JSON.stringify(gift?.body))
  check('it says what happened, and the gift is listed with its quality', /Gave 6 packs to 3 players/.test(await page.locator('[data-create-done]').innerText()) && /Grand Final winners/.test(await page.locator('[data-gift="g1"]').innerText()) && /Legendary/.test(await page.locator('[data-gift="g1"]').innerText()))
  check('the name is cleared ready for the next', (await page.getByLabel('Name of the pack').inputValue()) === '')
  await page.getByLabel('Name of the pack').fill('Thanks')
  await page.getByLabel('Who gets them').selectOption('players')
  check('choosing players shows a list, and nothing can be given until one is picked', (await page.locator('[data-player-picker]').count()) === 1 && (await page.getByRole('button', { name: /^Give .* now$/ }).isDisabled()))
  check('players who cannot have cards (a junior with juniors off, a privacy-hidden player) are not offered', (await page.locator('[data-pick-player]').count()) === 3 && (await page.locator('[data-pick-player="c3"]').count()) === 0 && (await page.locator('[data-pick-player="d4"]').count()) === 0)
  await page.locator('[data-pick-player="a1"] input').check()
  check('picking updates the count', /1 player chosen/.test(await page.locator('[data-picked-count]').innerText()))
  calls.length = 0
  const first = gift.body.request_id
  await page.getByRole('button', { name: /^Give 2 packs now$/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('[data-gift]').length === 2)
  const g2 = calls.find((c) => c.path === '/player-cards/gifts')
  check('a gift to chosen players sends their ids, with a fresh request id', g2 && g2.body.audience === 'players' && JSON.stringify(g2.body.player_ids) === '["a1"]' && g2.body.request_id !== first, JSON.stringify(g2?.body))
  await page.getByLabel('Who gets them').selectOption('all')
  // cards in the pack, the words under the name, and a design made on the spot
  check('the number of cards starts at five, and the preview says so', (await page.getByLabel('Cards in the pack').inputValue()) === '5' && /5 cards/i.test(await page.locator('[data-create-preview]').innerText()))
  await page.getByLabel('Cards in the pack').fill('0')
  check('a pack of no cards is refused with a message and nothing to press', /holds from 1 to 12 cards/.test(await page.locator('[data-create-pack]').innerText()) && (await page.getByRole('button', { name: /^Give .* now$/ }).isDisabled()))
  await page.getByLabel('Cards in the pack').fill('13')
  check('...and so is one of thirteen', /holds from 1 to 12 cards/.test(await page.locator('[data-create-pack]').innerText()))
  await page.getByLabel('Cards in the pack').fill('8')
  check('the preview follows the number of cards', /8 cards/i.test(await page.locator('[data-create-preview]').innerText()))
  await page.getByLabel('Name of the pack').fill('Ton Up Tuesday')
  await page.getByLabel('Words under the name').fill('Dig deep, champions')
  check('the words under the name show on the preview as they are typed', /dig deep, champions/i.test(await page.locator('[data-create-preview]').innerText()))
  check('the design controls are tucked away until asked for', (await page.locator('[data-create-design]').count()) === 0)
  await page.locator('[data-design-toggle]').click()
  await page.locator('[data-create-design] [data-design-file="bg"]').setInputFiles({ name: 'pitch.png', mimeType: 'image/png', buffer: PNG })
  await page.waitForSelector('[data-create-preview] [data-pack-design-bg]')
  await page.locator('[data-create-design] [data-design-file="art"]').setInputFiles({ name: 'cup.png', mimeType: 'image/png', buffer: PNG })
  await page.waitForSelector('[data-create-preview] [data-pack-design-art]')
  check('a chosen picture shows on the preview at once, before anything is sent', !calls.some((c) => /designs/.test(c.path)))
  await page.locator('[data-create-design] [data-design-colour="Foil colour"] input').evaluate((el) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(el, '#1d4ed8'); el.dispatchEvent(new Event('input', { bubbles: true })) })
  await page.getByRole('switch', { name: "Show the club logo" }).click()
  check('the button says it will go with the design', /with your design/.test(await page.locator('[data-create-pack]').innerText()))
  if (SHOT) await page.screenshot({ path: `${SHOT}/10-make-a-designed-pack.png`, fullPage: true })
  calls.length = 0
  await page.getByRole('button', { name: /^Give 6 packs now$/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('[data-gift]').length === 3)
  const dz = calls.find((c) => c.path === '/player-cards/gifts/designed')
  check('a designed pack is sent as one multipart request to the designed route, with both pictures', dz && dz.multipart && /name="bg"; filename="pitch.png"/.test(dz.raw) && /name="art"; filename="cup.png"/.test(dz.raw), dz && dz.raw.slice(0, 300))
  const styleField = ((dz?.raw || '').match(/name="style"\r\n\r\n([^\r]*)/) || [])[1]
  check('...with the name, size and quality, and only the style that was changed', /name="size"\r\n\r\n8/.test(dz.raw) && /name="title"\r\n\r\nTon Up Tuesday/.test(dz.raw) && JSON.stringify(JSON.parse(styleField || '{}')) === '{"color_a":"#1d4ed8","show_logo":false,"line":"Dig deep, champions"}', styleField)
  check('the gift is listed with its size', /8 cards/.test(await page.locator('[data-gift="g3"]').innerText()))
  check('the design is cleared, ready for the next pack', (await page.locator('[data-create-design]').count()) === 0 && (await page.getByLabel('Words under the name').inputValue()) === '')
  await page.getByLabel('Cards in the pack').fill('4')
  await page.getByLabel('Name of the pack').fill('Plain four')
  calls.length = 0
  await page.getByRole('button', { name: /^Give 6 packs now$/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('[data-gift]').length === 4)
  check('a pack with no design goes the quick way (JSON, with its size)', calls.some((c) => c.path === '/player-cards/gifts' && c.body.size === 4) && !calls.some((c) => c.path === '/player-cards/gifts/designed'))
  await page.getByLabel('Cards in the pack').fill('5')
  await page.locator('[data-when-later]').click()
  check('scheduling hides the design and the words, and says why', (await page.locator('[data-design-toggle]').count()) === 0 && (await page.getByLabel('Words under the name').count()) === 0 && /Scheduled packs hold five cards/.test(await page.locator('[data-when-dates]').innerText()))
  await page.locator('[data-when-now]').click()
  await page.locator('[data-when-later]').click()
  check('scheduling needs a name and a first day', await page.getByRole('button', { name: 'Schedule it' }).isDisabled())
  await page.getByLabel('Name of the pack').fill('Australia v South Africa, First Test')
  await page.locator('[data-quality="elite"]').click()
  await page.getByLabel('First day').fill('2026-12-03')
  await page.getByLabel('Last day').fill('2026-12-07')
  await page.getByRole('button', { name: 'Schedule it' }).click()
  await page.waitForSelector('[data-event="e1"]')
  const ev = calls.filter((c) => /\/player-cards\/events$/.test(c.path)).pop()
  check('a scheduled pack sends its name, both days, one a day and its quality', JSON.stringify(ev.body) === '{"title":"Australia v South Africa, First Test","starts_on":"2026-12-03","ends_on":"2026-12-07","per_day":true,"quality":"elite"}', JSON.stringify(ev.body))
  check('it is listed with its days and its quality', /Elite/.test(await page.locator('[data-event="e1"]').innerText()) && /First Test/.test(await page.locator('[data-event="e1"]').innerText()) && /a pack each day/.test(await page.locator('[data-event="e1"]').innerText()))
  await page.locator('[data-event="e1"] button', { hasText: 'Remove' }).click()
  await page.waitForFunction(() => !document.querySelector('[data-event="e1"]'))
  check('removing it sends a DELETE', calls.some((c) => c.method === 'DELETE' && /events\/e1$/.test(c.path)))
  await page.getByLabel('Weekly packs per player').selectOption('3')
  await page.waitForFunction(() => document.querySelector('select[aria-label="Weekly packs per player"]').value === '3')
  check('the weekly count sends weekly_packs only', JSON.stringify(calls.filter((c) => c.method === 'PATCH').pop().body) === '{"weekly_packs":3}')
  await page.getByLabel('Timezone').selectOption('Australia/Sydney')
  await page.waitForFunction(() => document.querySelector('select[aria-label="Timezone"]').value === 'Australia/Sydney')
  await page.getByLabel('Timezone').selectOption('')
  await page.waitForFunction(() => document.querySelector('select[aria-label="Timezone"]').value === '')
  check('the default timezone sends an explicit null', JSON.stringify(calls.filter((c) => c.method === 'PATCH').pop().body) === '{"timezone":null}')
  await page.locator('[data-card-player="a1"] button', { hasText: 'Hide' }).click()
  await page.waitForFunction(() => /Hidden by the club/.test(document.querySelector('[data-card-player="a1"]').innerText))
  const hid = calls.filter((c) => c.method === 'POST' && /hidden$/.test(c.path)).pop()
  check('Hide sends the player and hidden true', hid && hid.path === '/player-cards/players/a1/hidden' && JSON.stringify(hid.body) === '{"hidden":true}')
  await page.locator('[data-card-player="a1"] button', { hasText: 'Show' }).click()
  await page.waitForFunction(() => /260 matches/.test(document.querySelector('[data-card-player="a1"]').innerText))
  await page.getByRole('button', { name: 'Look for new ones' }).click()
  await page.waitForTimeout(300)
  check('the special cards button posts to refresh', calls.some((c) => c.method === 'POST' && c.path === '/player-cards/refresh-specials'))

  console.log('\nthe phone')
  await page.setViewportSize({ width: 390, height: 900 })
  for (const k of ['overview', 'players', 'activity', 'cards', 'packs', 'designs', 'swaps', 'settings']) {
    await tab(k)
    await page.waitForTimeout(200)
    check(`no horizontal scroll on ${k} at 390px`, (await overflow()) <= 0, `over by ${await overflow()}px`)
  }
  check('no page errors', errors.length === 0, errors.join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
