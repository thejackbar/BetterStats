// Suggested swaps, in Chromium on the production build with the API stubbed:
//  * Swaps shows the suggestion to a player (both cards, the other player, a spare note), one tap asks with the exact request
//    {to_player_id, give: [{key, qty: 1}], want: [{key, qty: 1}]}, and the screen reports it and reads the board again;
//  * Change it opens the swap builder with that player and both cards already chosen;
//  * with no suggestions nothing about them is drawn; Home shows how many there are; no sideways scroll at 390.
//
//   APP_URL=http://localhost:4173 node verification/verify_player_cards_suggested_browser.mjs
import { chromium } from 'playwright'
import { cardsUrl } from './lib/cardsPage.mjs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}
const CLUB = { name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c' }
const card = (pid, name, tier, rarity, x = {}) => ({
  kind: 'player', key: `p:${pid}`, player_id: pid, name, photo_url: null, hero_photo_url: null, matches: 100, runs: 1500, bat_avg: 24.5,
  wickets: 20, bowl_avg: 31.2, dismissals: 30, rarity, tier, copies: 1, obtained_at: '2026-10-20T01:00:00Z', mine: false, ...x,
})
const GIVE = { ...card('p2', 'Zed, Alan', 'common', 18), spare: true, tradeable: 2 }
const WANT = card('p3', 'Adams, Brian', 'epic', 81)
const SUGGESTION = { player: { player_id: 'p7', name: 'Dave, Dan' }, give: GIVE, want: WANT, options: 4 }
const state = { suggested: [SUGGESTION] }
const asked = []

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
      if (/\/me\/cards\/swaps\/players\//.test(url)) return json({ player: SUGGESTION.player, cards: [{ ...WANT, tradeable: 1 }] })
      if (/\/me\/cards\/swaps$/.test(url) && method === 'POST') { asked.push(JSON.parse(rq.postData())); state.suggested = []; return json({ id: 'sw1', status: 'pending' }) }
      if (/\/me\/cards\/swaps(\?|$)/.test(url)) return json({ incoming: [], outgoing: [], recent: [], suggested: state.suggested, mine: [{ ...GIVE, tradeable: 2 }], people: [{ player_id: 'p7', name: 'Dave, Dan', tradeable: 3 }], expires_days: 14, max_open: 10 })
      if (/\/me\/cards\/(showcase|feed|board|sets)/.test(url)) return json({ cards: [], events: [], entries: [], sets: [], max: 6 })
      if (/\/me\/cards\/wants/.test(url)) return json({ wants: [], ready: 0, limit: 100 })
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: [], pack_size: 5, season: 'Summer', cards: [card('p1', 'Barendse, Jack', 'rare', 62, { mine: true }), GIVE], totals: {} })
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

  {
    const { ctx, page } = await open(1280, '', '[data-suggested-tag]')
    check('Home says how many suggested swaps there are', /1 suggested swap/.test(await page.locator('[data-suggested-tag]').innerText()))
    await ctx.close()
  }
  {
    state.suggested = [SUGGESTION]
    const { ctx, page } = await open(1280, '/swaps', '[data-suggested]')
    check('Swaps shows the suggestion with the other player and both cards', (await page.locator('[data-suggestion="p7"]').count()) === 1 && (await page.locator('[data-suggestion="p7"] [aria-label]').count()) >= 2)
    const line = await page.locator('[data-suggestion-line]').innerText()
    check('it reads as my card for theirs, names them, and says it is a spare', /Zed, Alan for Adams, Brian, with Dave, Dan/.test(line) && /spare/.test(line), line)
    check('it says how many pairs would work', /4 pairs would work/.test(await page.locator('[data-suggestion]').innerText()))
    await page.click('[data-suggestion-ask]')
    await page.waitForSelector('[data-swap-msg]')
    check('one tap sends exactly my card for theirs, one copy each', JSON.stringify(asked[0]) === JSON.stringify({ to_player_id: 'p7', give: [{ key: 'p:p2', qty: 1 }], want: [{ key: 'p:p3', qty: 1 }] }), JSON.stringify(asked))
    check('it says the request went to them, and the suggestion is gone once the board is read again', /Swap request sent to Dave, Dan/.test(await page.locator('[data-swap-msg]').innerText()) && (await page.locator('[data-suggested]').count()) === 0)
    await ctx.close()
  }
  {
    state.suggested = [SUGGESTION]
    const { ctx, page } = await open(1280, '/swaps', '[data-suggested]')
    await page.click('[data-suggestion-change]')
    await page.waitForSelector('[data-screen="new-swap"]')
    await page.waitForTimeout(600)
    const body = await page.locator('body').innerText()
    if (process.env.DEBUG_BODY) console.log(body)
    check('Change it opens the builder with the player and both cards chosen', /dave, dan/i.test(body) && /2\. the cards you want from dave, dan\s+1 card . 1 picked/i.test(body) && /3\. the cards you give[^\n]*\s+1 card . 1 picked/i.test(body) && /adams, brian, epic/i.test(body), body.slice(0, 400))
    await ctx.close()
  }
  {
    state.suggested = []
    const { ctx, page } = await open(1280, '/swaps', '[data-screen="swaps"]')
    check('with no suggestions nothing about them is drawn', (await page.locator('[data-suggested]').count()) === 0)
    await ctx.close()
  }
  for (const route of ['', '/swaps']) {
    state.suggested = [SUGGESTION]
    const { ctx, page } = await open(390, route, route ? '[data-suggested]' : '[data-suggested-tag]')
    check(`${route || '/'} has no sideways scroll at 390`, (await overflow(page)) <= 0, String(await overflow(page)))
    await ctx.close()
  }
  check('no errors in the console', errors.length === 0, errors.slice(0, 3).join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
