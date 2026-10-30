// The Player Cards page at /playerdash/:token/cards, in Chromium on the production build with the API stubbed:
//  * the way round: sidebar on a wide screen, a rail on a tablet, a bottom bar of five on a phone, badges, More, Back to my page;
//  * every screen opens cold from its own address, the old /avail address moves on to the new one, an unknown one lands on Home;
//  * Home, Packs, Swaps (asking, asked, history, the full screen builder), How it works, and the Not mine / Someone could swap filters;
//  * no horizontal scroll on any screen at 390, 800 and 1280, and no errors in the console.
//
//   APP_URL=http://localhost:4173 node verification/verify_player_cards_page_browser.mjs
import { chromium } from 'playwright'
import { cardsUrl, goNav } from './lib/cardsPage.mjs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}
const CLUB = { name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c' }
const ME = 'p1'
const card = (pid, name, tier, rarity, x = {}) => ({
  kind: 'player', key: `p:${pid}`, player_id: pid, name, photo_url: null, hero_photo_url: null, matches: 100, runs: 1500, bat_avg: 24.5,
  wickets: 20, bowl_avg: 31.2, dismissals: 30, rarity, tier, copies: 1, obtained_at: '2026-10-20T01:00:00Z', mine: false, ...x,
})
const CARDS = [card(ME, 'Barendse, Jack', 'rare', 62, { mine: true, obtained_at: null }), card('p2', 'Zed, Alan', 'common', 18, { copies: 2 }), card('p3', 'Adams, Brian', 'epic', 81)]
const totals = { regular_owned: 3, regular_total: 14, special_owned: 0, special_total: 0, copies: 4 }
const PACKS = [{ id: 'k1', source: 'weekly', label: 'Weekly pack' }, { id: 'k2', source: 'runs', label: 'Runs pack' }]
const tr = (c, tradeable) => ({ ...c, tradeable, copies: undefined })
const req = (id, dir, other) => ({ id, direction: dir, status: 'pending', other: { player_id: 'p7', name: other }, created_at: new Date().toISOString(), resolved_at: null,
  give: [{ ...tr(CARDS[2], 1), qty: 1 }], want: [{ ...tr(CARDS[1], 1), qty: 1 }] })
const RECENT = [
  { ...req('h1', 'out', 'Dave, Dan'), status: 'accepted', resolved_at: new Date().toISOString() },
  { ...req('h2', 'in', 'Smith, Sue'), status: 'declined', resolved_at: new Date().toISOString() },
  { ...req('h3', 'out', 'Dave, Dan'), status: 'cancelled', resolved_at: new Date().toISOString() },
]
const board = (history) => ({ incoming: [req('w1', 'in', 'Dave, Dan')], outgoing: [req('o1', 'out', 'Smith, Sue')], recent: history ? RECENT : RECENT.slice(0, 1), mine: [tr(CARDS[1], 2)], people: [{ player_id: 'p7', name: 'Dave, Dan', tradeable: 3 }], expires_days: 14, max_open: 10 })
const catCalls = [], swapCalls = []
const catalogue = (u) => {
  catCalls.push(Object.fromEntries(u.searchParams.entries()))
  const items = [{ ...CARDS[0], others: 0, mine_copies: 1 }, { ...CARDS[2], others: 2, mine_copies: 0 }]
  return { total: items.length, counts: { regular: 2, special: 0 }, items, offset: 0, limit: 12 }
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = []
  const open = async (width, route = '', { height = 900, wait = '[data-cards-page] [data-screen]', from } = {}) => {
    const ctx = await browser.newContext({ viewport: { width, height }, isMobile: width < 500, hasTouch: width < 500 })
    const page = await ctx.newPage()
    page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|font/i.test(m.text())) errors.push(m.text()) })
    page.on('pageerror', (e) => errors.push(String(e)))
    await page.route('**/api/**', async (r) => {
      const url = r.request().url()
      const json = (b, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
      if (!url.includes('/public/availability/')) return json({})
      if (/\/me\/cards\/catalogue\/holders/.test(url)) return json({ card: CARDS[2], holders: [], mine_copies: 0 })
      if (/\/me\/cards\/catalogue/.test(url)) return json(catalogue(new URL(url)))
      if (/\/me\/cards\/(showcase|feed|board|sets)/.test(url)) return json({ cards: [], events: [], entries: [], sets: [], max: 6 })
      if (/\/me\/cards\/wants/.test(url)) return json({ wants: [], ready: 0, limit: 100 })
      if (/\/me\/cards\/swaps\/players\//.test(url)) return json({ player: { player_id: 'p7', name: 'Dave, Dan' }, cards: [tr(CARDS[2], 1)] })
      if (/\/me\/cards\/swaps$/.test(url) || /\/me\/cards\/swaps\?/.test(url)) { swapCalls.push(url.split('/api')[1]); return json(board(/history=true/.test(url))) }
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: PACKS, pack_size: 5, season: 'Summer', cards: CARDS, totals })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 2, swaps_waiting: 1 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
      if (/\/me(\?|$)/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
      return json({ club: CLUB, require_pin: true, has_availability: false, players: [{ id: ME, display_name: 'Barendse, Jack', has_phone: true }] })
    })
    await page.goto(from || cardsUrl(BASE, 'tok123', route))
    await page.waitForSelector(wait, { timeout: 20000 })
    await page.waitForTimeout(400)
    return { ctx, page }
  }
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  const vis = (page, sel) => page.locator(sel).evaluateAll((els) => els.some((e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)))
  const path = (page) => new URL(page.url()).pathname

  console.log('\nthe sidebar, 1280')
  {
    const { ctx, page } = await open(1280)
    check('a sidebar, and no rail or bottom bar', await vis(page, '[data-sidebar]') && !(await vis(page, '[data-rail]')) && !(await vis(page, '[data-bottom-bar]')))
    const items = await page.locator('[data-sidebar] [data-nav]').evaluateAll((els) => els.map((e) => e.getAttribute('data-nav')))
    check('Home, My cards, Club cards, Wish list, Showcase, Open packs, Swaps, Spares, Challenges, Sets and board, How it works, Settings, in that order', JSON.stringify(items) === JSON.stringify(['home', 'book', 'club', 'wishlist', 'showcase', 'packs', 'swaps', 'spares', 'challenges', 'sets', 'how', 'settings']), JSON.stringify(items))
    check('the screen you are on is lit', (await page.locator('[data-sidebar] [data-nav="home"]').getAttribute('aria-current')) === 'page')
    check('packs and swaps carry their counts', (await page.locator('[data-sidebar] [data-nav="packs"] [data-nav-badge]').textContent()) === '2' && (await page.locator('[data-sidebar] [data-nav="swaps"] [data-nav-badge]').textContent()) === '1')
    check('Back to my page goes to the dashboard', (await page.locator('[data-sidebar] [data-back-to-page]').getAttribute('href')) === '/playerdash/tok123')
    check('the player is named, with a way to switch', /Barendse, Jack/.test(await page.locator('[data-sidebar]').textContent()) && (await page.locator('[data-sidebar] [data-not-you]').count()) === 1)
    if (SHOT) await page.screenshot({ path: `${SHOT}/page-1280-home.png` })
    check('no horizontal scroll', (await overflow(page)) <= 0)
    await ctx.close()
  }

  console.log('\nthe rail, 800')
  {
    const { ctx, page } = await open(800)
    check('a rail of icons, and no sidebar or bottom bar', await vis(page, '[data-rail]') && !(await vis(page, '[data-sidebar]')) && !(await vis(page, '[data-bottom-bar]')))
    await page.locator('[data-rail] [data-nav="swaps"]').click()
    await page.waitForSelector('[data-screen="swaps"]')
    check('the rail goes to Swaps', path(page) === '/playerdash/tok123/cards/swaps')
    check('no horizontal scroll', (await overflow(page)) <= 0)
    await ctx.close()
  }

  console.log('\nthe bottom bar, 390')
  {
    const { ctx, page } = await open(390)
    check('a bottom bar of five, and no sidebar or rail', await vis(page, '[data-bottom-bar]') && !(await vis(page, '[data-sidebar]')) && !(await vis(page, '[data-rail]')))
    const items = await page.locator('[data-bottom-bar] [data-nav]').evaluateAll((els) => els.map((e) => e.getAttribute('data-nav')))
    check('Home, Cards, Packs, Swaps, More', JSON.stringify(items) === JSON.stringify(['home', 'book', 'packs', 'swaps', 'more']), JSON.stringify(items))
    check('the counts show on the bar', (await page.locator('[data-bottom-bar] [data-nav="packs"] [data-nav-badge]').textContent()) === '2')
    await page.click('[data-bottom-bar] [data-nav="more"]')
    await page.waitForSelector('[data-more-sheet]')
    const links = await page.locator('[data-more-link]').allTextContents()
    check('More holds Club cards, Wish list, Spares, How it works, Settings and the way back', links.map((x) => x.trim()).join('|') === 'Club cards|Wish list|Showcase|Spares|Sets and board|How it works|Settings|Back to my page', links.join('|'))
    await page.click('[data-more-link]:has-text("How it works")')
    await page.waitForSelector('[data-screen="how"]')
    check('...and a link in it goes there and closes the sheet', path(page) === '/playerdash/tok123/cards/how' && (await page.locator('[data-more-sheet]').count()) === 0)
    await page.click('[data-bottom-bar] [data-nav="book"]')
    await page.waitForSelector('[data-screen="book"]')
    check('My cards and Club cards share one slot, with a switch on top', (await page.locator('[data-cards-switch]').count()) === 1)
    await page.click('[data-switch="club"]')
    await page.waitForSelector('[data-screen="club"]')
    check('the switch moves between them', path(page) === '/playerdash/tok123/cards/club' && (await page.locator('[data-bottom-bar] [data-nav="book"]').getAttribute('aria-current')) === 'page')
    if (SHOT) await page.screenshot({ path: `${SHOT}/page-390-club.png` })
    await ctx.close()
  }

  console.log('\naddresses')
  {
    for (const [route, screen] of [['', 'home'], ['/book', 'book'], ['/club', 'club'], ['/packs', 'packs'], ['/swaps', 'swaps'], ['/swaps/sent', 'swaps'], ['/swaps/history', 'swaps'], ['/swaps/new', 'new-swap'], ['/how', 'how']]) {
      const { ctx, page } = await open(1280, route, { wait: `[data-screen="${screen}"]` })
      check(`${route || '/'} opens cold`, path(page) === `/playerdash/tok123/cards${route}` && (await overflow(page)) <= 0, path(page))
      await ctx.close()
    }
    const old = await open(1280, '', { from: `${BASE}/avail/tok123/cards/club?x=1`, wait: '[data-screen="club"]' })
    check('the old /avail address, with its sub page, moves to /playerdash', path(old.page) === '/playerdash/tok123/cards/club' && new URL(old.page.url()).search === '?x=1', old.page.url())
    await old.ctx.close()
    const odd = await open(1280, '/nonsense/here', { wait: '[data-screen="home"]' })
    check('an address under cards that does not exist lands on Home', path(odd.page) === '/playerdash/tok123/cards', path(odd.page))
    await odd.ctx.close()
    const dash = await open(1280, '', { from: `${BASE}/playerdash/tok123`, wait: '[data-my-page]' })
    check('/playerdash/:token is the dashboard', (await dash.page.locator('[data-cards-module] [data-open-cards-page]').count()) === 1)
    await dash.ctx.close()
  }

  console.log('\nHome, Packs and How it works')
  {
    const { ctx, page } = await open(1280)
    check('Home shows your card, the packs and four tiles', (await page.locator('[data-my-card]').count()) === 1 && /2 packs to open/.test(await page.locator('[data-packs-ready]').textContent()) && (await page.locator('[data-tile]').count()) === 4)
    check('the swaps tile says one is asking you', /1 asking you/.test(await page.locator('[data-tile="swaps"]').textContent()))
    check('the collection tile counts the set', /3\s*\/\s*14/.test(await page.locator('[data-tile="collection"]').textContent()))
    await goNav(page, 'packs')
    check('Packs lists every way a pack arrives, in three groups', (await page.locator('[data-way]').count()) === 24 && (await page.locator('[data-pack-group]').count()) === 3 && /2 packs to open/.test(await page.locator('[data-packs-ready]').textContent()))
    await goNav(page, 'how')
    check('How it works has the odds for each tier and eight sections', (await page.locator('[data-odds]').count()) === 4 && (await page.locator('[data-how]').count()) === 8)
    check('...with the odds that the pack uses (60, 28, 10, 2)', /60 in 100/.test(await page.locator('[data-how="packs"]').textContent()) && /2 in 100/.test(await page.locator('[data-how="packs"]').textContent()))
    await ctx.close()
  }

  console.log('\npack art')
  {
    // Every kind of pack, and a scheduled event with a long name, at every size the page draws them.
    const saved = [...PACKS]
    PACKS.length = 0
    PACKS.push({ id: 'a1', source: 'century', label: 'Century pack' }, { id: 'a2', source: 'event', label: 'Australia v South Africa, First Test' }, { id: 'a3', source: 'melbourne_cup', label: 'Melbourne Cup pack' }, { id: 'a4', source: 'weekly', label: 'Weekly pack' })
    const fit = (page) => page.evaluate(() => [...document.querySelectorAll('[data-pack-art]')].map((a) => {
      const r = a.getBoundingClientRect(), n = a.querySelector('[data-pack-name]')
      return { src: a.dataset.packArt, w: Math.round(r.width), ratio: +(r.height / r.width).toFixed(2), nameFits: !n || (n.scrollWidth <= n.clientWidth + 1 && n.getBoundingClientRect().left >= r.left && n.getBoundingClientRect().right <= r.right + 0.5 && n.getBoundingClientRect().top > r.top + r.height * 0.3 && n.getBoundingClientRect().bottom < r.bottom - r.height * 0.08) }
    }))
    for (const [width, label] of [[1280, 'wide'], [390, 'phone']]) {
      const { ctx, page } = await open(width, '/packs', { wait: '[data-screen="packs"] [data-way]' })
      const all = await fit(page)
      check(`${label}: every pack is the same shape (1.5 tall for 1 wide), whatever its size`, all.length >= 22 && all.every((a) => Math.abs(a.ratio - 1.5) < 0.03), JSON.stringify(all.filter((a) => Math.abs(a.ratio - 1.5) >= 0.03)))
      check(`${label}: the pack's name sits inside it, even the longest`, all.every((a) => a.nameFits), JSON.stringify(all.filter((a) => !a.nameFits)))
      check(`${label}: the packs in the list are big enough to read (88px wide)`, all.filter((a) => a.w === 88).length >= 22)
      check(`${label}: the next pack is drawn larger than the list's`, all.some((a) => a.w >= 110))
      check(`${label}: no horizontal scroll`, (await overflow(page)) <= 0)
      if (SHOT) await page.screenshot({ path: `${SHOT}/packs-${width}.png`, fullPage: true })
      check(`${label}: a scheduled event is counted by its own name`, /Australia v South Africa, First Test/i.test(await page.locator('[data-packs-ready]').locator('..').textContent()))
      await ctx.close()
    }
    PACKS.length = 0
    PACKS.push(...saved)
  }

  console.log('\nSwaps')
  {
    const { ctx, page } = await open(390, '/swaps')
    check('Asking you shows the request', (await page.locator('[data-swap-request="w1"]').count()) === 1 && (await page.locator('[data-swap-request="o1"]').count()) === 0)
    check('the tabs carry their counts', /Asking you 1/.test(await page.locator('[data-swaps-tab="asking"]').textContent()) && /You asked 1/.test(await page.locator('[data-swaps-tab="sent"]').textContent()))
    await page.click('[data-swaps-tab="sent"]')
    await page.waitForSelector('[data-swap-request="o1"]')
    check('You asked shows the one you made, with a Cancel', path(page) === '/playerdash/tok123/cards/swaps/sent' && (await page.locator('[data-swap-request="o1"] [data-swap-cancel]').count()) === 1)
    swapCalls.length = 0
    await page.click('[data-swaps-tab="history"]')
    await page.waitForSelector('[data-history]')
    check('History asks for the longer list and shows every finished swap', swapCalls.some((c) => /history=true/.test(c)) && (await page.locator('[data-swap-recent]').count()) === 3)
    check('...each says how it ended', (await page.locator('[data-swap-recent][data-status="accepted"]').count()) === 1 && (await page.locator('[data-swap-recent][data-status="declined"]').count()) === 1)
    check('no horizontal scroll', (await overflow(page)) <= 0)
    await page.click('[data-swap-start]')
    await page.waitForSelector('[data-swap-builder]')
    check('Start a swap is a page of its own, not a pop-up', path(page) === '/playerdash/tok123/cards/swaps/new' && (await page.locator('[role="dialog"]').count()) === 0)
    await page.click('[data-swap-cancel-build]')
    await page.waitForSelector('[data-screen="swaps"]')
    check('Cancel returns to Swaps', path(page) === '/playerdash/tok123/cards/swaps')
    await page.goBack()
    await page.waitForSelector('[data-swap-builder]')
    check('the Back button works through the screens', path(page) === '/playerdash/tok123/cards/swaps/new')
    await ctx.close()
  }

  console.log('\nClub cards filters')
  {
    const { ctx, page } = await open(1280, '/club', { wait: '[data-catalogue] [data-slot-card]' })
    catCalls.length = 0
    await page.selectOption('[data-gallery-have]', 'not_mine')
    await page.waitForTimeout(500)
    check('Not mine asks the server for cards you do not hold', catCalls.some((c) => c.have === 'not_mine'), JSON.stringify(catCalls))
    catCalls.length = 0
    await page.selectOption('[data-gallery-have]', 'swappable')
    await page.waitForTimeout(500)
    check('Someone could swap it asks for that', catCalls.some((c) => c.have === 'swappable'))
    catCalls.length = 0
    await page.selectOption('[data-gallery-have]', 'all')
    await page.waitForTimeout(500)
    check('Every card sends no filter at all', catCalls.length > 0 && catCalls.every((c) => !('have' in c)))
    await ctx.close()
  }

  console.log('\nthe card beside the book, 1440')
  {
    const { ctx, page } = await open(1440, '/club', { wait: '[data-catalogue] [data-slot-card]', height: 1000 })
    check('with room, there is a place for a card held up, beside the book', (await page.locator('[data-card-panel-empty]').count()) === 1)
    await page.locator('[data-slot-card="p:p3"]').click()
    await page.waitForSelector('[data-card-panel]')
    check('a card tapped opens in the panel, not over the book', (await page.locator('[role="dialog"]').count()) === 0 && (await page.locator('[data-catalogue] [data-slot-card]').count()) >= 1)
    check('...with who could swap one under it', (await page.locator('[data-card-panel] [data-holders]').count()) === 1)
    if (SHOT) await page.screenshot({ path: `${SHOT}/page-1440-club-panel.png` })
    check('no horizontal scroll', (await overflow(page)) <= 0)
    await page.click('[data-card-panel-close]')
    check('it can be put down', (await page.locator('[data-card-panel]').count()) === 0 && (await page.locator('[data-card-panel-empty]').count()) === 1)
    await ctx.close()
    const narrow = await open(1280, '/club', { wait: '[data-catalogue] [data-slot-card]' })
    await narrow.page.locator('[data-slot-card="p:p3"]').click()
    await narrow.page.waitForSelector('[data-card-viewer]')
    check('on a narrower screen it is held up over the book instead', (await narrow.page.locator('[data-card-panel]').count()) === 0)
    await narrow.ctx.close()
  }

  check('no errors in the console or the page', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
