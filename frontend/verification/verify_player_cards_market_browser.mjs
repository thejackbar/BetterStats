// The Market, in Chromium on the production build with the API stubbed:
//  * your cards in demand name who wants them (a link to that player), and say how many keep their list private;
//  * every visible wish list is listed, the players whose list lines up with yours first, with what they want of yours and what you want of theirs;
//  * a player's page marks the cards you hold (and lets you pick them to give) beside their cards that are on your list (pick them to ask for),
//    and Start a swap opens the builder with the player, the cards asked for and the cards given;
//  * My cards filters by Wanted, Doubles and the club's role for the player, and says nothing about roles where none are recorded;
//  * Settings can keep the wish list out of the Market, sending exactly {wants_hidden: true}; no sideways scroll at 390.
//
//   APP_URL=http://localhost:4173 node verification/verify_player_cards_market_browser.mjs
import { chromium } from 'playwright'
import { cardsUrl } from './lib/cardsPage.mjs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}
const CLUB = { name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c' }
const card = (pid, name, tier, rarity, x = {}) => ({
  kind: 'player', key: `p:${pid}`, player_id: pid, name, photo_url: null, hero_photo_url: null, matches: 100, runs: 1500, bat_avg: 24.5,
  wickets: 20, bowl_avg: 31.2, dismissals: 30, rarity, tier, copies: 1, obtained_at: '2026-10-20T01:00:00Z', mine: false, role: null, ...x,
})
const ME = card('p1', 'Barendse, Jack', 'rare', 62, { mine: true, role: 'BAT', wanted_by: 0 })
const ZED = card('p2', 'Zed, Alan', 'common', 18, { role: 'BOWL', copies: 2, wanted_by: 3 })
const ADAMS = card('p3', 'Adams, Brian', 'epic', 81, { role: 'WK', wanted_by: 0 })
const COLE = card('p4', 'Cole, Chris', 'rare', 55, { role: null, wanted_by: 1 })
let BOOK = [ME, ZED, ADAMS, COLE]
const OVERVIEW = {
  my_wants: 2,
  demand: [{ ...ZED, tradeable: 2, wanted_by: [{ player_id: 'p7', name: 'Dave, Dan' }, { player_id: 'p8', name: 'Eve, Ed' }], hidden: 1 }],
  players: [
    { player_id: 'p7', name: 'Dave, Dan', wants: 4, they_want_mine: 1, i_want_theirs: 1, swap_possible: true },
    { player_id: 'p9', name: 'Fox, Fred', wants: 2, they_want_mine: 0, i_want_theirs: 1, swap_possible: false },
    { player_id: 'p8', name: 'Eve, Ed', wants: 1, they_want_mine: 1, i_want_theirs: 0, swap_possible: false },
  ],
}
const DETAIL = {
  player: { player_id: 'p7', name: 'Dave, Dan' },
  wants: [{ ...ZED, tradeable: 2, mine: true }, { ...card('p5', 'Hill, Harry', 'legendary', 95), tradeable: 0, mine: false }],
  theirs: [{ ...ADAMS, tradeable: 1, on_my_list: true }, { ...card('p6', 'Iles, Ian', 'common', 20), tradeable: 1, on_my_list: false }],
}
const calls = []
let prefs = { alert_swaps: false, alert_wants: false, board_hidden: false, feed_hidden: false, wants_hidden: false, club_alerts: true, email_on_file: true, features: { sets: true, showcase: true, board: true, feed: true } }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = []
  const open = async (width, route, wait) => {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500 })
    const page = await ctx.newPage()
    page.setDefaultTimeout(15000)
    page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|font/i.test(m.text())) errors.push(m.text()) })
    page.on('pageerror', (e) => errors.push(String(e)))
    await page.route('**/api/**', async (r) => {
      const rq = r.request(), url = rq.url(), method = rq.method()
      const json = (b, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
      if (!url.includes('/public/availability/')) return json({})
      if (/\/me\/cards\/market\/p7$/.test(url)) return json(DETAIL)
      if (/\/me\/cards\/market$/.test(url)) return json(OVERVIEW)
      if (/\/me\/cards\/prefs$/.test(url)) { if (method === 'PUT') { const body = JSON.parse(rq.postData()); calls.push({ method, body }); prefs = { ...prefs, ...body } } return json(prefs) }
      if (/\/me\/cards\/swaps\/players\//.test(url)) return json({ player: DETAIL.player, cards: DETAIL.theirs })
      if (/\/me\/cards\/swaps(\?|$)/.test(url)) return json({ incoming: [], outgoing: [], recent: [], suggested: [], mine: [{ ...ZED, tradeable: 2 }], people: [{ player_id: 'p7', name: 'Dave, Dan', tradeable: 2 }], expires_days: 14, max_open: 10 })
      if (/\/me\/cards\/(showcase|feed|board|sets)/.test(url)) return json({ cards: [], events: [], entries: [], sets: [], max: 6 })
      if (/\/me\/cards\/wants/.test(url)) return json({ wants: [], ready: 0, limit: 100 })
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: [], pack_size: 5, season: 'Summer', features: { sets: true, showcase: true, board: true, feed: true }, cards: BOOK, totals: {} })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 0, swaps_waiting: 0 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
      if (/\/me(\?|$)/.test(url)) return json({ club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
      return json({ club: CLUB, require_pin: true, has_availability: false, players: [{ id: 'p1', display_name: 'Barendse, Jack', has_phone: true }] })
    })
    await page.goto(cardsUrl(BASE, 'tok123', route))
    await page.waitForSelector(wait, { timeout: 20000 })
    await page.waitForTimeout(300)
    return { ctx, page }
  }
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)

  // ── the Market ──
  {
    const { ctx, page } = await open(1280, '/market', '[data-screen="market"]')
    check('the Market has an entry in the navigation', (await page.locator('[data-nav="market"]:visible').count()) >= 1)
    const dem = page.locator('[data-demand="p:p2"]')
    check('your cards in demand: the card, how many you hold, and who wants it (a link to each)', (await dem.count()) === 1 && /You hold 2 copies/.test(await dem.innerText()) && (await dem.locator('[data-wanter]').count()) === 2 && /Dave, Dan/.test(await dem.innerText()), await dem.innerText())
    check('...and says how many keep their list private, without naming them', /1 player who keeps their list private/.test(await dem.innerText()))
    const order = await page.locator('[data-market-player]').evaluateAll((els) => els.map((e) => e.getAttribute('data-market-player')))
    check('players are listed as the server ranks them, swap possible first', JSON.stringify(order) === JSON.stringify(['p7', 'p9', 'p8']), JSON.stringify(order))
    const dave = await page.locator('[data-market-player="p7"]').innerText()
    check('a player shows what they want, how many of yours, how many you want, and that a swap is possible', /wants 4 cards/.test(dave) && /1 of yours/.test(dave) && /1 you want/.test(dave) && /swap possible/i.test(dave), dave)
    check('a player who wants none of yours has no "of yours" chip (and one who does, has)', (await page.locator('[data-market-player="p9"] [data-chip="they-want"]').count()) === 0 && (await page.locator('[data-market-player="p8"] [data-chip="they-want"]').count()) === 1)
    await page.fill('[data-market-search]', 'fox')
    check('the search narrows the list', (await page.locator('[data-market-player]').count()) === 1 && (await page.locator('[data-market-player="p9"]').count()) === 1)
    await page.fill('[data-market-search]', 'nobody')
    check('...and says so when nobody matches', (await page.locator('[data-no-market-match]').count()) === 1)
    await ctx.close()
  }
  {
    const { ctx, page } = await open(1280, '/market?card=p%3Ap2', '[data-demand="p:p2"]')
    check('opening it from a card focuses that card', (await page.locator('[data-demand="p:p2"][data-focused="yes"]').count()) === 1)
    await ctx.close()
  }
  // ── a player's page ──
  {
    const { ctx, page } = await open(1280, '/market', '[data-market-player="p7"]')
    await page.click('[data-market-player="p7"]')
    await page.waitForSelector('[data-screen="market-player"]')
    check('their page marks the cards you hold, and only those', (await page.locator('[data-grid="wants"] [data-market-card="p:p2"][data-marked="yes"]').count()) === 1 && (await page.locator('[data-grid="wants"] [data-market-card="p:p5"][data-marked="no"]').count()) === 1)
    check('...says how many you have', /You have ×2/i.test(await page.locator('[data-market-card="p:p2"]').innerText()))
    check('...and marks their cards that are on your wish list, and only those', (await page.locator('[data-grid="theirs"] [data-market-card="p:p3"][data-marked="yes"]').count()) === 1 && (await page.locator('[data-grid="theirs"] [data-market-card="p:p6"][data-marked="no"]').count()) === 1)
    check('a card you do not hold cannot be picked to give', (await page.locator('[data-market-card="p:p5"] button').count()) === 0)
    await page.click('[data-grid="wants"] [data-market-card="p:p2"] button')
    await page.click('[data-grid="theirs"] [data-market-card="p:p3"] button')
    const sum = await page.locator('[data-market-summary]').innerText()
    check('the bar says what you give and what you get', /You give 1 card/.test(sum) && /You get 1 card/.test(sum) && /Zed, Alan/.test(sum) && /Adams, Brian/.test(sum), sum)
    if (SHOT) await page.screenshot({ path: `${SHOT}/market-player-1280.png`, fullPage: true })
    await page.click('[data-market-start]')
    await page.waitForSelector('[data-screen="new-swap"]')
    await page.waitForTimeout(600)
    const body = await page.locator('body').innerText()
    check('Start a swap opens the builder with Dave, the card asked for and the card given', /dave, dan/i.test(body) && /adams, brian, epic/i.test(body) && /zed, alan/i.test(body), body.slice(0, 300))
    await ctx.close()
  }
  // ── My cards: Wanted, Doubles, roles ──
  {
    BOOK = [ME, ZED, ADAMS, COLE]
    const { ctx, page } = await open(1280, '/book', '[data-screen="book"]')
    const slots = async () => (await page.locator('[data-slot-card]').evaluateAll((els) => els.map((e) => e.getAttribute('data-slot-card')))).sort()
    check('with roles recorded there is a role row: any, batters, bowlers, keepers, no role recorded', (await page.locator('[data-gallery-roles] [data-gallery-role]').count()) === 5)
    await page.click('[data-gallery-filter="wanted"]')
    check('Wanted shows the cards other players want, and no others', JSON.stringify(await slots()) === JSON.stringify(['p:p2', 'p:p4']), JSON.stringify(await slots()))
    await page.click('[data-gallery-filter="doubles"]')
    check('Doubles shows the cards held twice', JSON.stringify(await slots()) === JSON.stringify(['p:p2']), JSON.stringify(await slots()))
    await page.click('[data-gallery-filter="all"]')
    await page.click('[data-gallery-role="BOWL"]')
    check('Bowlers shows only bowlers', JSON.stringify(await slots()) === JSON.stringify(['p:p2']), JSON.stringify(await slots()))
    await page.click('[data-gallery-role="none"]')
    check('"No role recorded" shows the players the club has no role for', JSON.stringify(await slots()) === JSON.stringify(['p:p4']), JSON.stringify(await slots()))
    await page.click('[data-gallery-role="WK"]')
    await page.click('[data-gallery-filter="wanted"]')
    check('a role and Wanted together narrow each other (the keeper is not wanted, so nothing is left)', (await slots()).length === 0 && (await page.locator('[data-gallery-empty]').count()) === 1)
    await page.click('[data-gallery-role="any"]')
    await page.click('[data-gallery-filter="all"]')
    await page.click('[data-slot-card="p:p2"]')
    await page.waitForSelector('[data-see-wanters]')
    check('a held card that is wanted links to the Market for it', /market\?card=p%3Ap2/.test((await page.locator('[data-see-wanters]').getAttribute('href')) || ''))
    await ctx.close()
  }
  {
    BOOK = [{ ...ME, role: null }, { ...ZED, role: null }]
    const { ctx, page } = await open(1280, '/book', '[data-screen="book"]')
    check('with no roles recorded at all there is no role row (nothing to filter on, nothing guessed)', (await page.locator('[data-gallery-roles]').count()) === 0)
    await ctx.close()
    BOOK = [ME, ZED, ADAMS, COLE]
  }
  // ── Settings ──
  {
    const { ctx, page } = await open(1280, '/settings', '[data-screen="settings"]')
    const box = page.locator('[data-pref="wants_hidden"] input')
    check('the wish list is shown in the Market until the player switches it off (box ticked)', (await box.count()) === 1 && (await box.isChecked()))
    calls.length = 0
    await box.click()
    await page.waitForTimeout(400)
    check('unticking sends exactly {wants_hidden: true}, and nothing else', calls.length === 1 && JSON.stringify(calls[0].body) === JSON.stringify({ wants_hidden: true }), JSON.stringify(calls))
    check('...and the box stays unticked once saved', !(await box.isChecked()))
    await ctx.close()
  }
  // ── 390 ──
  for (const [route, wait] of [['/market', '[data-market-player="p7"]'], ['/market/p7', '[data-screen="market-player"]'], ['/book', '[data-gallery-roles]']]) {
    const { ctx, page } = await open(390, route, wait)
    check(`${route} has no sideways scroll at 390`, (await overflow(page)) <= 0, String(await overflow(page)))
    if (SHOT) await page.screenshot({ path: `${SHOT}/market${route.replace(/\//g, '-')}-390.png`, fullPage: route !== '/book' })
    await ctx.close()
  }
  check('no errors in the console', errors.length === 0, errors.slice(0, 3).join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
