// Player Cards, third release, in Chromium on the production build with the API stubbed at the network layer:
//  * run, wicket and dismissal milestone cards: filed with the milestones in order (games, runs, wickets,
//    dismissals), one player's cards of a kind stacked, a big number on the face, nothing clipped;
//  * a swap can offer any held card (but not your own card with only its implied copy), and the builder pages
//    and searches a big collection;
//  * 390px for overflow, and no errors in the console.
//
//   APP_URL=http://localhost:4173 node verification/verify_player_cards_v3_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}

const PHOTO = 'data:image/svg+xml;utf8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><rect width="400" height="500" fill="#678"/><circle cx="200" cy="170" r="80" fill="#e9c9a8"/><rect x="90" y="260" width="220" height="240" rx="40" fill="#fff"/></svg>')
const CLUB = { name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c' }
const base = (pid, name, tier, rarity, x = {}) => ({
  kind: 'player', key: `p:${pid}`, player_id: pid, name, photo_url: null, hero_photo_url: null, matches: 100, runs: 1500, bat_avg: 24.5,
  wickets: 20, bowl_avg: 31.2, dismissals: 30, rarity, tier, copies: 1, obtained_at: '2026-10-20T01:00:00Z', mine: false, ...x,
})
let sid = 0
const sp = (pid, name, kind, title, detail, x = {}) => {
  sid += 1
  return { kind: 'special', key: `s:s${sid}`, special_id: `s${sid}`, special_kind: kind, player_id: pid, name, photo_url: null, hero_photo_url: null, title,
    occurred_on: null, detail, tier: 'special', copies: 1, obtained_at: `2026-10-${10 + (sid % 15)}T01:00:00Z`, mine: false, ...x }
}
const ME = 'p1'
const MANY = Array.from({ length: 30 }, (_, i) => base(`q${i}`, `Many${String(i).padStart(2, '0')}, Pat`, 'common', 10 + i))
const CARDS = [
  base(ME, 'Barendse, Jack', 'rare', 62, { mine: true, obtained_at: null, hero_photo_url: PHOTO, runs: 4114, matches: 214, wickets: 211 }),
  base('p2', 'Zed, Alan', 'common', 18),
  sp(ME, 'Barendse, Jack', 'dismissals_milestone', '50 dismissals', { threshold: 50, total: 98 }, { hero_photo_url: PHOTO }),
  sp(ME, 'Barendse, Jack', 'wickets_milestone', '200 wickets', { threshold: 200, total: 211 }, { hero_photo_url: PHOTO }),
  ...[1000, 2000, 3000, 4000].map((t) => sp(ME, 'Barendse, Jack', 'runs_milestone', `${t.toLocaleString('en-AU')} runs`, { threshold: t, total: 4114 }, { hero_photo_url: PHOTO })),
  sp(ME, 'Barendse, Jack', 'games', '200 games', { games: 200 }, { hero_photo_url: PHOTO }),
]
const totals = { regular_owned: CARDS.filter((c) => c.kind === 'player').length, regular_total: 40, special_owned: 7, special_total: 20, copies: CARDS.length }
const swapCard = (c, tradeable) => ({ ...c, tradeable, copies: undefined })
const board = { incoming: [], outgoing: [], recent: [], mine: [CARDS[1], ...CARDS.slice(2, 4), ...MANY].map((c) => swapCard(c, 1)), people: [{ player_id: 'p7', name: 'Dave, Dan', tradeable: 30 }], expires_days: 14, max_open: 10 }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = []
  const open = async (width) => {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500 })
    await ctx.addInitScript(() => { try { localStorage.setItem('bs.playerpage.open', JSON.stringify({ cards: true })) } catch (e) { /* none */ } })
    const page = await ctx.newPage()
    page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|font/i.test(m.text())) errors.push(m.text()) })
    page.on('pageerror', (e) => errors.push(String(e)))
    await page.route('**/api/**', async (route) => {
      const url = route.request().url()
      const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
      if (!url.includes('/public/availability/')) return json({})
      if (/\/me\/cards\/swaps\/players\//.test(url)) return json({ player: { player_id: 'p7', name: 'Dave, Dan' }, cards: MANY.map((c) => swapCard(c, 1)) })
      if (/\/me\/cards\/swaps$/.test(url)) return json(board)
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: [], pack_size: 5, season: 'Summer', cards: CARDS, totals })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 0, swaps_waiting: 0 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
      if (/\/me(\?|$)/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
      return json({ club: CLUB, require_pin: true, has_availability: false, players: [{ id: ME, display_name: 'Barendse, Jack', has_phone: true }] })
    })
    await page.goto(`${BASE}/avail/tok123`)
    await page.waitForSelector('[data-cards-module]', { timeout: 20000 })
    await page.waitForTimeout(500)
    return { ctx, page }
  }
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  const slots = (page) => page.locator('[data-slot-card], [data-slot-stack]').evaluateAll((els) => els.map((e) => e.getAttribute('data-slot-stack') || e.getAttribute('data-slot-card')))

  console.log('\nmilestone cards in the book, 390px')
  {
    const { ctx, page } = await open(390)
    const chips = await page.locator('[data-gallery-filter]').allTextContents()
    check('the Milestones chip counts games, runs, wickets and dismissals together (7)', chips.some((x) => x.replace(/\s/g, '') === 'Milestones7'), JSON.stringify(chips))
    await page.click('[data-gallery-filter="special"]')
    await page.waitForTimeout(300)
    const order = await slots(page)
    check("one player's seven milestones (games, runs, wickets, dismissals) share one slot", order.length === 1 && order[0] === `stack:milestones:${ME}`, JSON.stringify(order))
    check('the stack says what it holds', /×7 Milestones/.test(await page.locator('[data-stack-count]').first().textContent()))
    check('no horizontal scroll', (await overflow(page)) <= 0)
    await page.locator('[data-slot-stack]').first().click()
    await page.waitForSelector('[data-stack-viewer]')
    const labels = await page.locator('[data-stack-card]').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')))
    const want = ['200 games', '1,000 runs', '2,000 runs', '3,000 runs', '4,000 runs', '200 wickets', '50 dismissals']
    check('opened out: games, runs 1,000 to 4,000, wickets, then dismissals', labels.length === 7 && want.every((t, i) => labels[i].includes(t)), JSON.stringify(labels))
    check('the opened stack fits the phone', (await overflow(page)) <= 0)
    const kindCard = async (title) => {
      await page.locator(`[data-stack-card]`).filter({ has: page.locator('xpath=self::*') }).nth(want.indexOf(title)).click()
      await page.waitForSelector('[data-card-viewer]')
      const viewer = page.locator('[data-card-viewer]').first()
      const text = await viewer.textContent()
      if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/${title.replace(/\W+/g, '-')}.png` })
      const clipped = await viewer.locator('[data-fit]').evaluateAll((els) => els.filter((e) => e.scrollWidth > e.clientWidth + 1).length)
      await page.keyboard.press('Escape')
      await page.waitForTimeout(200)
      return { text, clipped }
    }
    for (const [title, big, noun] of [['1,000 runs', '1,000', 'runs'], ['200 wickets', '200', 'wickets'], ['50 dismissals', '50', 'dismissals']]) {
      const r = await kindCard(title)
      check(`the ${title} card shows ${big} with the word ${noun}, and nothing is clipped`, r.text.includes(big) && new RegExp(noun, 'i').test(r.text) && r.clipped === 0, `${r.text.slice(0, 100)} clipped ${r.clipped}`)
    }
    await ctx.close()
  }

  console.log('\noffering any held card')
  {
    const { ctx, page } = await open(390)
    await page.click('[data-gallery-filter="regular"]')
    await page.locator(`[data-slot-card="p:${ME}"]`).click()
    await page.waitForSelector('[data-card-viewer]')
    check('your own card with only its implied copy has no offer button', (await page.locator('[data-viewer-offer]').count()) === 0)
    await page.keyboard.press('Escape')
    await page.waitForTimeout(200)
    await page.locator('[data-slot-card="p:p2"]').click()
    await page.waitForSelector('[data-card-viewer]')
    check("a single copy of someone else's card can be offered", (await page.locator('[data-viewer-offer]').count()) === 1)
    await page.click('[data-viewer-offer]')
    await page.waitForSelector('[data-swap-builder]')
    await ctx.close()
  }

  console.log('\nthe swap builder with a big collection')
  {
    const { ctx, page } = await open(390)
    await page.click('[data-cards-tab="swaps"]')
    await page.click('[data-swap-start]')
    await page.waitForSelector('[data-swap-builder]')
    await page.locator('[data-swap-player="p7"]').click()
    await page.waitForSelector('[data-card-pick="theirs"]')
    const first = await page.locator('[data-card-pick="theirs"] [data-swap-card]').count()
    check('their 30 cards come a page at a time (24)', first === 24, String(first))
    check('a search box shows once there are more than eight', (await page.locator('[data-card-pick="theirs"] input').count()) === 1)
    await page.locator('[data-card-pick="theirs"] input').fill('Many07')
    await page.waitForTimeout(200)
    const found = await page.locator('[data-card-pick="theirs"] [data-swap-card]').count()
    check('searching narrows to the one name', found === 1, String(found))
    await page.locator('[data-card-pick="theirs"] input').fill('')
    await page.getByText(/Show more/).first().click()
    await page.waitForTimeout(200)
    check('Show more brings the rest', (await page.locator('[data-card-pick="theirs"] [data-swap-card]').count()) === 30)
    check('no horizontal scroll in the builder', (await overflow(page)) <= 0)
    await ctx.close()
  }

  check('no errors in the console or the page', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
