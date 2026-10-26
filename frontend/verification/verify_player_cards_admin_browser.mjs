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

const CLUB = { name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c', font_config: {} }
const state = {
  settings: { enabled: true, include_juniors: false, weekly_packs: 1, timezone: null, effective_timezone: 'Australia/Perth' },
  players: [
    { id: 'a1', display_name: 'Adams, Brian', hidden: false, in_pool: true, matches: 260, rarity: 81, tier: 'epic', excluded: null },
    { id: 'b2', display_name: 'Baker, Chris', hidden: false, in_pool: true, matches: 12, rarity: 22, tier: 'common', excluded: null },
    { id: 'c3', display_name: 'Young, Kid', hidden: false, in_pool: false, matches: 8, rarity: null, tier: null, excluded: 'junior' },
    { id: 'd4', display_name: 'Hidden, Pat', hidden: false, in_pool: false, matches: 40, rarity: null, tier: null, excluded: 'private' },
    { id: 'e5', display_name: 'New, Nick', hidden: false, in_pool: false, matches: 0, rarity: 1, tier: 'common', excluded: null },
  ],
}
const settingsPayload = () => ({
  club: CLUB, settings: state.settings,
  timezones: [{ id: 'Australia/Perth', label: 'Western Australia' }, { id: 'Australia/Sydney', label: 'New South Wales, ACT' }],
  max_weekly_packs: 10, link: { path: '/avail/tok123' },
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
  swaps: [{ id: 'w1', status: 'accepted', from: { id: 'a1', name: 'Adams, Brian' }, to: { id: 'b2', name: 'Baker, Chris' }, give: { kind: 'player', player: 'Zed, Zak', tier: 'rare', title: 'Card' }, want: { kind: 'special', player: 'Adams, Brian', title: 'Century', tier: 'special' }, created_at: '2026-10-24T01:00:00Z', resolved_at: '2026-10-24T05:00:00Z' }],
}
const swap = (id, status, from, to) => ({ id, status, from: { id: 'x', name: from }, to: { id: 'y', name: to }, give: { kind: 'player', player: 'Zed, Zak', tier: 'rare', title: 'Card' }, want: { kind: 'special', player: 'Adams, Brian', title: 'Century', tier: 'special' }, created_at: '2026-10-20T01:00:00Z', resolved_at: status === 'pending' ? null : '2026-10-21T01:00:00Z' })
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
    const body = req.postData() ? JSON.parse(req.postData()) : null
    calls.push({ method, path, query: u.search.replace(/^\?/, ''), body })
    if (path === '/player-cards/overview') return json(OV)
    if (path === '/player-cards/activity') return json(ACT)
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
  check('seven tabs', (await page.locator('[data-pc-tab]').count()) === 7)
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
  await shot('07-swaps')

  console.log('\nsettings')
  await tab('settings')
  await page.waitForSelector('[data-card-player]')
  check('the pool count is in the heading', /Players in the card pool \(2 of 5\)/i.test(await text()))
  check('cards are on and juniors are off by default', (await page.getByRole('switch', { name: 'Player Cards are on' }).getAttribute('aria-checked')) === 'true' && (await page.getByRole('switch', { name: 'Include junior players' }).getAttribute('aria-checked')) === 'false')
  check('the player page link is shown', /\/avail\/tok123/.test(await page.locator('[data-player-page-link]').innerText()))
  const reasons = await page.locator('[data-card-player]').evaluateAll((els) => Object.fromEntries(els.map((e) => [e.getAttribute('data-card-player'), e.innerText])))
  check('a junior and a privacy-hidden player are shown as out, with the reason', /Junior player, and juniors are switched off/.test(reasons.c3) && /Hidden from the public site/.test(reasons.d4))
  check('no Hide button for those', !/Hide|Show/.test(reasons.c3) && !/Hide|Show/.test(reasons.d4) && /Hide/.test(reasons.a1))
  await page.getByRole('switch', { name: 'Include junior players' }).click()
  await page.waitForFunction(() => document.querySelector('[role="switch"][aria-label="Include junior players"]').getAttribute('aria-checked') === 'true')
  check('a switch sends only what it changed', JSON.stringify(calls.filter((c) => c.method === 'PATCH').pop().body) === '{"include_juniors":true}')
  await page.getByRole('switch', { name: 'Include junior players' }).click()
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
  for (const k of ['overview', 'players', 'activity', 'cards', 'packs', 'swaps', 'settings']) {
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
