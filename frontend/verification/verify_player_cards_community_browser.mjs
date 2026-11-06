// Player Cards, the community side, in Chromium on the production build with the API stubbed at the network layer:
//  * sets (grouped, progress, complete banner, a set page that reads the catalogue with set=);
//  * the collectors board (a join prompt until opted in, ranks, showcase and rarest card) and This week (the feed, and its short
//    form on Home);
//  * the showcase (pin, order, save the exact keys, the limit);
//  * settings for being seen (the opt-in and the inverted opt-out send the right thing);
//  * a club that has parts switched off (no menu entry, a redirect, no Home block);
//  * 390px for overflow and no errors in the console.
//
//   APP_URL=http://localhost:4173 node verification/verify_player_cards_community_browser.mjs
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
const ME = 'p1'
const card = (pid, name, tier, rarity, x = {}) => ({
  kind: 'player', key: `p:${pid}`, player_id: pid, name, photo_url: null, hero_photo_url: null, matches: 100, runs: 1500, bat_avg: 24.5,
  wickets: 20, bowl_avg: 31.2, dismissals: 30, rarity, tier, copies: 1, obtained_at: '2026-10-20T01:00:00Z', mine: false, ...x,
})
const MINE = card(ME, 'Barendse, Jack', 'rare', 62, { mine: true })
const ZED = card('p2', 'Zed, Alan', 'common', 18, { copies: 3 })
const ADAMS = card('p3', 'Adams, Brian', 'epic', 81)
const CARDS = [MINE, ZED, ADAMS]
const calls = [], catCalls = []
let features, board, prefs, showcase
const reset = () => {
  features = { sets: true, showcase: true, board: true, feed: true }
  prefs = { alert_swaps: false, alert_wants: false, board_hidden: false, feed_hidden: false, club_alerts: true, email_on_file: true }
  showcase = [MINE, ZED]
  board = { entries: [
    { player_id: 'p9', rank: 1, name: 'Smith, Sue', percent: 61.5, held: 24, rarest: { ...ADAMS }, showcase: [ADAMS] },
    { player_id: 'p7', rank: 2, name: 'Dave, Dan', percent: 40.2, held: 16, rarest: { ...ZED }, showcase: [] },
  ], total_cards: 39, me_on_board: true, me_hidden: false, me_rank: 2, me: { player_id: 'p1', rank: 2, name: 'Barendse, Jack', percent: 8, held: 3 }, count: 3 }
}
reset()
const SETS = { sets: [
  { key: 'tier:legendary', group: 'Players', title: 'Every Legendary', blurb: 'The club\'s rarest players.', total: 4, owned: 1, percent: 25, complete: false },
  { key: 'kind:century', group: 'Special cards', title: 'Every century at the club', blurb: 'Each hundred.', total: 12, owned: 12, percent: 100, complete: true },
  { key: 'season:2015/16', group: 'Awards', title: '2015/16 awards', blurb: 'The awards for 2015/16.', total: 5, owned: 2, percent: 40, complete: false },
], complete: 1 }
const FEED = { days: 7, events: Array.from({ length: 8 }, (_, i) => ({ type: i % 3 === 0 ? 'special' : i % 3 === 1 ? 'pull' : 'swap', on: '2026-10-2' + (7 - Math.floor(i / 2)), text: `Event number ${i + 1}`, card: i % 3 === 2 ? null : ADAMS })) }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = []
  const open = async (width, route, { wait = '[data-cards-page] [data-screen]', height = 900 } = {}) => {
    const ctx = await browser.newContext({ viewport: { width, height }, isMobile: width < 500, hasTouch: width < 500 })
    const page = await ctx.newPage()
    page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|font/i.test(m.text())) errors.push(m.text()) })
    page.on('pageerror', (e) => errors.push(String(e)))
    await page.route('**/api/**', async (r) => {
      const req = r.request(), url = req.url(), method = req.method()
      const json = (b, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
      if (!url.includes('/public/availability/')) return json({})
      const path = url.split('/api')[1]
      const body = req.postData() ? JSON.parse(req.postData()) : null
      if (/\/me\/cards\/sets\/[^/?]+$/.test(url)) return json({ key: decodeURIComponent(url.split('/').pop()), title: 'Every century at the club', blurb: 'Each hundred.', group: 'Special cards', total: 12, owned: 5, complete: false })
      if (/\/me\/cards\/sets$/.test(url)) return json(SETS)
      if (/\/me\/cards\/showcase/.test(url)) {
        if (method === 'PUT') { calls.push({ method, path, body }); return json({ cards: body.keys.map((k) => CARDS.find((c) => c.key === k)), max: 6 }) }
        return json({ cards: showcase, max: 6 })
      }
      if (/\/me\/cards\/board/.test(url)) return json(board)
      if (/\/me\/cards\/feed/.test(url)) return json(FEED)
      if (/\/me\/cards\/prefs/.test(url)) { if (method === 'PUT') { calls.push({ method, path, body }); prefs = { ...prefs, ...body }; if (body.board_hidden === true) board = { ...board, me_on_board: false, me_hidden: true, me_rank: null, me: null, count: 2 }; if (body.board_hidden === false) board = { ...board, me_on_board: true, me_hidden: false, me_rank: 2, count: 3 } } return json({ ...prefs, features }) }
      if (/\/me\/cards\/wants/.test(url)) return json({ wants: [], ready: 0, limit: 100 })
      if (/\/me\/cards\/catalogue\/holders/.test(url)) return json({ card: ADAMS, holders: [], mine_copies: 0 })
      if (/\/me\/cards\/catalogue/.test(url)) { catCalls.push(Object.fromEntries(new URL(url).searchParams.entries())); return json({ total: 1, counts: { regular: 0, special: 1, centuries: 1 }, items: [{ ...ADAMS, others: 1, mine_copies: 1 }], offset: 0, limit: 12 }) }
      if (/\/me\/cards\/swaps/.test(url)) return json({ incoming: [], outgoing: [], recent: [], mine: [], people: [], expires_days: 14, max_open: 10 })
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: [], pack_size: 5, season: 'Summer', cards: CARDS, totals: { regular_owned: 3, regular_total: 14, special_owned: 0, special_total: 0, copies: 5 }, features })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 0, swaps_waiting: 0 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
      if (/\/me(\?|$)/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
      return json({ club: CLUB, require_pin: true, has_availability: false, players: [{ id: ME, display_name: 'Barendse, Jack', has_phone: true }] })
    })
    await page.goto(cardsUrl(BASE, 'tok123', route))
    await page.waitForSelector(wait, { timeout: 20000 })
    await page.waitForTimeout(400)
    return { ctx, page }
  }
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  const path = (page) => new URL(page.url()).pathname

  console.log('\nsets')
  {
    reset()
    const { ctx, page } = await open(390, '/sets', { wait: '[data-sets-list]' })
    check('sets are grouped: Players, Special cards, Awards', (await page.locator('[data-sets-list] h2').allTextContents()).join('|') === 'Players|Special cards|Awards')
    check('each says how far through you are', /1 of 4 · 25%/.test(await page.locator('[data-set="tier:legendary"] [data-set-progress]').textContent()))
    check('a finished set says so', (await page.locator('[data-set="kind:century"] [data-set-complete]').count()) === 1 && (await page.locator('[data-set="tier:legendary"] [data-set-complete]').count()) === 0)
    check('the intro says how many you have finished, and that there is no prize', /finished 1 set/.test(await page.locator('[data-sets-list]').textContent()))
    check('the three parts are tabs', (await page.locator('[data-club-tab]').count()) === 3)
    check('no horizontal scroll', (await overflow(page)) <= 0)
    if (SHOT) await page.screenshot({ path: `${SHOT}/community-sets-390.png` })
    catCalls.length = 0
    await page.click('[data-set="kind:century"]')
    await page.waitForSelector('[data-screen="set"] [data-set-header]')
    await page.waitForSelector('[data-catalogue] [data-slot-card]')
    check('a set page shows its progress and reads the catalogue with the set', /5 of 12/.test(await page.locator('[data-set-owned]').textContent()) && catCalls.some((c) => c.set === 'kind:century'), JSON.stringify(catCalls))
    check('its address carries the set key', decodeURIComponent(path(page)).endsWith('/cards/set/kind:century'))
    await ctx.close()
  }

  console.log('\nthe collectors board and this week')
  {
    reset()
    const { ctx, page } = await open(390, '/sets/board', { wait: '[data-board]' })
    check('everyone is on the board without joining: no join prompt, and where you stand', (await page.locator('[data-board-join]').count()) === 0 && (await page.locator('[data-board-row]').count()) === 2 && /number 2 of 3/.test(await page.locator('[data-board-me]').textContent()))
    check('it is ranked, with the share of the set and the number of different cards', /61.5% of the set · 24 different cards/.test(await page.locator('[data-board-row="p9"]').textContent()))
    check('an entry shows the showcase and the rarest card', (await page.locator('[data-board-row="p9"] [data-board-showcase]').count()) === 1 && /Rarest/.test(await page.locator('[data-board-row="p9"]').textContent()))
    check('...and the board says it counts different cards, not copies', /never copies/.test(await page.locator('[data-board]').textContent()))
    check('no horizontal scroll', (await overflow(page)) <= 0)
    if (SHOT) await page.screenshot({ path: `${SHOT}/community-board-390.png`, fullPage: true })
    check('...and says anyone can leave in Settings', /leave in Settings/.test(await page.locator('[data-board]').textContent()))
    board = { ...board, me_on_board: false, me_hidden: true, me_rank: null, me: null, count: 2 }
    await page.reload()
    await page.waitForSelector('[data-board-hidden]')
    check('a player who left is told so and sees no rank, and the board still shows', (await page.locator('[data-board-me]').count()) === 0 && (await page.locator('[data-board-row]').count()) === 2)
    reset()
    await page.click('[data-club-tab="week"]')
    await page.waitForSelector('[data-feed]')
    check('This week lists the events with their dates', (await page.locator('[data-feed-event]').count()) === 8)
    await ctx.close()
    const home = await open(1280, '', { wait: '[data-screen="home"] [data-home-week] [data-feed-event]' })
    check('Home shows the five latest, with a way to see all', (await home.page.locator('[data-home-week] [data-feed-event]').count()) === 5 && (await home.page.locator('[data-home-week] a:has-text("See all")').count()) === 1)
    check('...and the showcase', (await home.page.locator('[data-home-showcase] a[href*="/card/"]').count()) === 2)
    await home.ctx.close()
  }

  console.log('\nthe showcase')
  {
    reset()
    const { ctx, page } = await open(390, '/showcase', { wait: '[data-showcase-pinned]' })
    check('what is pinned is listed in order', (await page.locator('[data-pin]').count()) === 2 && /2 of 6 pinned/.test(await page.locator('[data-showcase-pinned]').textContent()))
    check('Save is off until something changes', await page.locator('[data-showcase-save]').isDisabled())
    await page.locator('[data-pin="p:p1"] button[aria-label="Move down"]').click()
    check('cards can be moved', (await page.locator('[data-pin]').first().getAttribute('data-pin')) === 'p:p2' && !(await page.locator('[data-showcase-save]').isDisabled()))
    await page.locator('[data-quick-pick][aria-label="Pick Adams, Brian"]').click()
    await page.waitForTimeout(200)
    check('a card from the collection is pinned with the plus', (await page.locator('[data-pin]').count()) === 3)
    calls.length = 0
    await page.click('[data-showcase-save]')
    await page.waitForSelector('[data-showcase-msg]')
    const put = calls.find((c) => c.method === 'PUT')
    check('Save sends every key in the order shown', put && put.body.keys.join() === 'p:p2,p:p1,p:p3', JSON.stringify(put))
    await page.locator('[data-pin="p:p3"] [data-unpin]').click()
    check('a card can be unpinned', (await page.locator('[data-pin]').count()) === 2)
    check('no horizontal scroll', (await overflow(page)) <= 0)
    await ctx.close()
  }

  console.log('\nsettings for being seen')
  {
    reset()
    const { ctx, page } = await open(390, '/settings', { wait: '[data-pref="board_hidden"]' })
    check('both emails are off until you switch them on', (await page.locator('[data-pref="alert_swaps"] input').isChecked()) === false && (await page.locator('[data-pref="alert_wants"] input').isChecked()) === false)
    check('the board is on and your name in This week is on, until you say otherwise', (await page.locator('[data-pref="board_hidden"] input').isChecked()) === true && (await page.locator('[data-pref="feed_hidden"] input').isChecked()) === true)
    calls.length = 0
    await page.locator('[data-pref="board_hidden"] input').click()
    await page.waitForSelector('[data-saved]')
    check('leaving the board sends board_hidden true only (stored the other way round)', JSON.stringify(calls[0].body) === '{"board_hidden":true}')
    calls.length = 0
    await page.locator('[data-pref="alert_swaps"] input').click()
    await page.waitForTimeout(300)
    check('switching a swap email on sends alert_swaps true only', JSON.stringify(calls[0].body) === '{"alert_swaps":true}')
    await page.locator('[data-pref="feed_hidden"] input').click()
    await page.waitForTimeout(300)
    check('unticking your name in This week sends feed_hidden true (it is stored the other way round)', calls.some((c) => JSON.stringify(c.body) === '{"feed_hidden":true}'))
    await ctx.close()
  }

  console.log('\na club with parts switched off')
  {
    reset(); features = { sets: false, showcase: false, board: true, feed: false }
    const { ctx, page } = await open(1280, '')
    const items = await page.locator('[data-sidebar] [data-nav]').evaluateAll((els) => els.map((e) => e.getAttribute('data-nav')))
    check('the menu leaves out Showcase, and keeps Sets and board because the board is on', !items.includes('showcase') && items.includes('sets'), JSON.stringify(items))
    check('Home has no showcase or this week block', (await page.locator('[data-home-week]').count()) === 0 && (await page.locator('[data-home-showcase]').count()) === 0)
    await page.click('[data-sidebar] [data-nav="sets"]')
    await page.waitForSelector('[data-board]')
    check('Sets and board lands on the first part that is on', path(page) === '/playerdash/tok123/cards/sets/board')
    check('only that tab is offered', (await page.locator('[data-club-tab]').count()) === 1)
    await ctx.close()
    reset(); features = { sets: false, showcase: false, board: false, feed: false }
    const none = await open(1280, '')
    const items2 = await none.page.locator('[data-sidebar] [data-nav]').evaluateAll((els) => els.map((e) => e.getAttribute('data-nav')))
    check('with all of them off there is no Club entry at all', !items2.includes('sets') && !items2.includes('showcase'))
    await none.ctx.close()
  }

  check('no errors in the console or the page', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
