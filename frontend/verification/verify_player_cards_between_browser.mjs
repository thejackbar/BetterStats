// Player Cards swap builder, "Between you and them", in Chromium on the production build with the API stubbed at the network layer:
//  * once a player is picked, the builder shows the cards of you they hold (with how many) and the cards of them you hold;
//  * a tap on either puts the card in the request, and Send posts exactly those keys;
//  * a player with none either way gets both sentences, not an empty box;
//  * a board without `me` (an older backend) shows no panel and the builder still works;
//  * 390px for overflow, and no errors in the console.
//
//   APP_URL=http://localhost:4173 SHOT_DIR=/tmp/between node verification/verify_player_cards_between_browser.mjs
import { chromium } from 'playwright'
import { cardsUrl, goNav } from './lib/cardsPage.mjs'
import fs from 'node:fs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
if (SHOT) fs.mkdirSync(SHOT, { recursive: true })
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}

const CLUB = { name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c' }
const ME = 'p1'
const base = (pid, name, tier, rarity, x = {}) => ({
  kind: 'player', key: `p:${pid}`, player_id: pid, name, photo_url: null, hero_photo_url: null, matches: 100, runs: 1500, bat_avg: 24.5,
  wickets: 20, bowl_avg: 31.2, dismissals: 30, rarity, tier, ...x,
})
const swapCard = (c, tradeable) => ({ ...c, tradeable, spare: Math.max(tradeable - 1, 0) })
const special = (pid, name, id) => ({ kind: 'special', key: `s:${id}`, special_id: id, special_kind: 'century', player_id: pid, name, photo_url: null, hero_photo_url: null,
  title: 'Century', occurred_on: '2026-01-10', detail: { runs: 104 }, tier: 'special', tradeable: 1, spare: 0 })

const THEIRS = {
  p7: [swapCard(base(ME, 'Barendse, Jack', 'rare', 62), 2), special(ME, 'Barendse, Jack', 'sx1'), swapCard(base('p10', 'Wanted, Wes', 'epic', 80), 1)],
  p9: [swapCard(base('p10', 'Wanted, Wes', 'epic', 80), 1)],
}
const NAMES = { p7: 'Dave, Dan', p9: 'Smith, Sue' }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = [], posts = []
  let withMe = true
  const board = () => ({
    incoming: [], outgoing: [], recent: [], suggested: [], expires_days: 14, max_open: 10,
    mine: [swapCard(base('p2', 'Zed, Alan', 'common', 18), 2), swapCard(base('p7', 'Dave, Dan', 'rare', 66), 1)],
    people: [{ player_id: 'p7', name: 'Dave, Dan', tradeable: 4 }, { player_id: 'p9', name: 'Smith, Sue', tradeable: 1 }],
    ...(withMe ? { me: ME } : {}),
  })

  const open = async (width) => {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500 })
    const page = await ctx.newPage()
    page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|font/i.test(m.text())) errors.push(m.text()) })
    page.on('pageerror', (e) => errors.push(String(e)))
    await page.route('**/api/**', async (route) => {
      const req = route.request(), url = req.url(), method = req.method()
      const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
      if (!url.includes('/public/availability/')) return json({})
      const m = url.match(/\/me\/cards\/swaps\/players\/([^/?]+)/)
      if (m) return json({ player: { player_id: m[1], name: NAMES[m[1]] }, cards: THEIRS[m[1]] || [] })
      if (/\/me\/cards\/swaps$/.test(url)) {
        if (method === 'POST') { posts.push(JSON.parse(req.postData())); return json({ id: 'o1', status: 'pending' }) }
        return json(board())
      }
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: [], pack_size: 5, season: 'Summer', cards: [base(ME, 'Barendse, Jack', 'rare', 62, { mine: true, copies: 1 })], totals: { regular_owned: 1, regular_total: 3, special_owned: 0, special_total: 0, copies: 1 } })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 0, swaps_waiting: 0 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
      if (/\/me(\?|$)/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
      return json({ club: CLUB, require_pin: true, has_availability: false, players: [{ id: ME, display_name: 'Barendse, Jack', has_phone: true }] })
    })
    await page.goto(cardsUrl(BASE, 'tok123', '/swaps'))
    await page.waitForSelector('[data-cards-page] [data-screen]', { timeout: 20000 })
    return { ctx, page }
  }
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  const keysIn = (page, side) => page.locator(`[data-between="${side}"] [data-swap-card]`).evaluateAll((els) => els.map((e) => e.getAttribute('data-swap-card')))
  const startWith = async (page, pid) => {
    await goNav(page, 'swaps')
    await page.click('[data-swap-start]')
    await page.waitForSelector('[data-swap-builder]')
    await page.locator(`[data-swap-player="${pid}"]`).click()
    await page.waitForSelector('[data-card-pick="theirs"]')
    await page.waitForTimeout(300)
  }

  console.log('\nbetween you and them, 390px')
  {
    const { ctx, page } = await open(390)
    await startWith(page, 'p7')
    const panel = await page.locator('[data-swap-between]').count()
    check('picking a player shows what is between you', panel === 1, `panels: ${panel}`)
    const ofMe = await keysIn(page, 'of-me'), ofThem = await keysIn(page, 'of-them')
    check('their copies of your cards: your regular card and your special', JSON.stringify(ofMe) === JSON.stringify(['p:p1', 's:sx1']), JSON.stringify(ofMe))
    check('a card they hold twice says so', (await page.locator('[data-between="of-me"] [data-swap-card="p:p1"] [data-card-count]').textContent().catch(() => '')) === '×2')
    check('your copies of their card', JSON.stringify(ofThem) === JSON.stringify(['p:p7']), JSON.stringify(ofThem))
    const between = panel ? await page.locator('[data-swap-between]').innerText() : ''
    check('the counts are in the headings', /your cards they hold \(3\)/i.test(between) && /their cards you hold \(1\)/i.test(between))
    check('a card of someone else is in neither row', !ofMe.includes('p:p10') && !ofThem.includes('p:p2'))
    if (SHOT) await page.screenshot({ path: `${SHOT}/between-390.png`, fullPage: true })
    check('no horizontal scroll at 390px', (await overflow(page)) <= 0)

    if (!panel) check('tapping the cards between you', false, 'no panel to tap')
    else {
      await page.locator('[data-between="of-me"] [data-swap-card="p:p1"]').click()
      check('a tap marks it chosen', (await page.locator('[data-between="of-me"] [data-swap-card="p:p1"]').getAttribute('aria-pressed')) === 'true')
      await page.locator('[data-between="of-them"] [data-swap-card="p:p7"]').click()
      await page.waitForSelector('[data-swap-confirm]')
      posts.length = 0
      await page.click('[data-swap-send]')
      await page.waitForTimeout(600)
      check('Send posts exactly the two cards tapped', JSON.stringify(posts[0]) === JSON.stringify({ give: [{ key: 'p:p7', qty: 1 }], want: [{ key: 'p:p1', qty: 1 }], to_player_id: 'p7' })
        || JSON.stringify(posts[0]) === JSON.stringify({ to_player_id: 'p7', give: [{ key: 'p:p7', qty: 1 }], want: [{ key: 'p:p1', qty: 1 }] }), JSON.stringify(posts[0]))
    }
    await ctx.close()
  }

  console.log('\nnothing either way')
  {
    const { ctx, page } = await open(390)
    await startWith(page, 'p9')
    const empties = await page.locator('[data-between-empty]').allTextContents().catch(() => [])
    check('both rows say there is nothing', empties.length === 2 && /Smith, Sue has none of your cards/.test(empties[0]) && /You hold none of their cards/.test(empties[1]), JSON.stringify(empties))
    await ctx.close()
  }

  console.log('\nan older backend without `me`')
  {
    withMe = false
    const { ctx, page } = await open(1280)
    await startWith(page, 'p7')
    check('no panel, and their cards still load', (await page.locator('[data-swap-between]').count()) === 0 && (await page.locator('[data-card-pick="theirs"] [data-slot-card]').count()) > 0)
    await ctx.close()
  }

  check('no errors in the console', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
