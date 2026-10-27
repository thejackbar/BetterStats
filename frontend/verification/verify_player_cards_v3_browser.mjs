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
const posted = []
const finds = []
const inReq = { id: 'w9', direction: 'in', status: 'pending', other: { player_id: 'p7', name: 'Dave, Dan' }, created_at: new Date().toISOString(), resolved_at: null,
  give: MANY.slice(0, 4).map((c, i) => ({ ...swapCard(c, 1), qty: i === 0 ? 2 : 1 })), want: [{ ...swapCard(CARDS[1], 1), qty: 1 }] }
const board = { incoming: [inReq], outgoing: [], recent: [], mine: [CARDS[1], ...CARDS.slice(2, 4), ...MANY].map((c, i) => swapCard(c, i === 4 ? 2 : 1)), people: [{ player_id: 'p7', name: 'Dave, Dan', tradeable: 30 }], expires_days: 14, max_open: 10 }

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
      if (/\/me\/cards\/swaps\/players\//.test(url)) return json({ player: { player_id: 'p7', name: 'Dave, Dan' }, cards: [swapCard(CARDS[1], 2), ...MANY.map((c, i) => swapCard(c, i === 0 ? 3 : 1))] })
      if (/\/me\/cards\/swaps\/find/.test(url)) { finds.push(decodeURIComponent(url.split('q=')[1])); return json({ cards: [{ ...swapCard(CARDS[1], 2), holders: [{ player_id: 'p7', name: 'Dave, Dan', tradeable: 2 }, { player_id: 'p9', name: 'Smith, Sue', tradeable: 1 }] }], more: 0, unheld: ['Eagle, Ed'] }) }
      if (/\/me\/cards\/swaps$/.test(url)) {
        if (route.request().method() === 'POST') { posted.push(JSON.parse(route.request().postData())); return json({ id: 'n1', status: 'pending' }) }
        return json(board)
      }
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
    const theirs = page.locator('[data-card-pick="theirs"]')
    check('their cards are shown as a card book, a page at a time', (await theirs.locator('[data-slot-card]').count()) === 4 && (await theirs.locator('[data-gallery-pages]').count()) === 1)
    check("the count says how many they could offer", /31 cards/i.test(await theirs.locator('[data-browse-count]').textContent()))
    const sorts = await theirs.locator('[data-gallery-sort] option').allTextContents()
    check('it can be sorted, without a Newest option (their cards have no date)', sorts.length > 3 && !sorts.some((x) => /newest/i.test(x)), JSON.stringify(sorts))
    check('there are no grey empty slots in someone else\'s book', (await theirs.locator('[data-empty-slot]').count()) === 0)
    await theirs.locator('[data-gallery-search]').fill('Many07')
    await page.waitForTimeout(200)
    check('searching narrows to the one name', (await theirs.locator('[data-slot-card]').count()) === 1 && /1 of 31/.test(await theirs.locator('[data-browse-count]').textContent()))
    await theirs.locator('[data-gallery-search]').fill('nobody at all')
    await page.waitForTimeout(200)
    check('a search with no match says so', (await theirs.locator('[data-gallery-empty]').count()) === 1)
    await theirs.locator('[data-gallery-search]').fill('')
    await theirs.locator('[data-gallery-next]').click()
    await page.waitForTimeout(700)
    check('Next turns the page', /Page 2 of/.test(await theirs.locator('[data-gallery-pages]').textContent()))
    await theirs.locator('[data-gallery-sort]').selectOption('name')
    await page.waitForTimeout(300)
    const names = await theirs.locator('[data-slot-card]').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')))
    check('sorting by name puts the cards in surname order', names.length === 4 && JSON.stringify(names) === JSON.stringify([...names].sort((x, y) => x.localeCompare(y))), JSON.stringify(names))
    // hold a card up and add it from there
    await theirs.locator('[data-slot-card]').first().click()
    await page.waitForSelector('[data-card-viewer]')
    check('holding a card up offers to add it', /Add to my request/i.test(await page.locator('[data-viewer-action]').textContent()))
    await page.click('[data-viewer-action]')
    await page.waitForTimeout(200)
    check('...and it is ticked in the book and in the tray', (await theirs.locator('[data-quick-pick="on"]').count()) === 1 && (await page.locator('[data-swap-tray="theirs"] [data-swap-picked]').count()) === 1)
    await theirs.locator('[data-slot-card]').first().click()
    check('holding it up again offers to take it out', /Take out of my request/i.test(await page.locator('[data-viewer-action]').textContent()))
    await page.click('[data-viewer-action]')
    await page.waitForTimeout(200)
    check('...and it goes', (await page.locator('[data-swap-tray="theirs"] [data-swap-picked]').count()) === 0)
    check('no horizontal scroll in the builder', (await overflow(page)) <= 0)
    await ctx.close()
  }

  console.log('\nmany cards each way')
  {
    const { ctx, page } = await open(390)
    await page.click('[data-cards-tab="swaps"]')
    await page.waitForSelector('[data-swap-request="w9"]')
    const req = page.locator('[data-swap-request="w9"]')
    check('a request lists every card on each side, with counts', (await req.locator('[data-swap-side="You would get"] [aria-label]').count()) === 4 && /5 cards/.test(await req.locator('[data-swap-side="You would get"]').textContent()) && (await req.locator('[data-swap-side="You give"] [aria-label]').count()) === 1, (await req.textContent()).slice(0, 200))
    check('a card offered twice shows its count', /×2/.test(await req.locator('[data-swap-side="You would get"] [data-card-count]').first().textContent()))
    check('no horizontal scroll with a long request', (await overflow(page)) <= 0)
    if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/many-request.png` })
    await page.click('[data-swap-start]')
    await page.waitForSelector('[data-swap-builder]')
    await page.locator('[data-swap-player="p7"]').click()
    await page.waitForSelector('[data-card-pick="theirs"]')
    // three of theirs: the one they hold three of, and two others
    const dotFor = async (side, term) => {
      const box = page.locator(`[data-card-pick="${side}"]`)
      await box.locator('[data-gallery-search]').fill(term)
      await page.waitForTimeout(150)
      await box.locator('[data-quick-pick]').first().click()
      await box.locator('[data-gallery-search]').fill('')
    }
    for (const t of ['Many00', 'Many01', 'Many02']) await dotFor('theirs', t)
    check('three cards can be picked, and each is in the tray', (await page.locator('[data-swap-tray="theirs"] [data-swap-picked]').count()) === 3)
    await page.locator('[data-swap-tray="theirs"] [data-swap-picked="p:q1"] [data-swap-remove]').click()
    check('a card can be taken back out', (await page.locator('[data-swap-tray="theirs"] [data-swap-picked]').count()) === 2)
    await dotFor('theirs', 'Many01')
    await dotFor('theirs', 'Many01')
    check('tapping a picked card again takes it out too', (await page.locator('[data-swap-tray="theirs"] [data-swap-picked="p:q1"]').count()) === 0)
    const row = page.locator('[data-swap-tray="theirs"] [data-swap-picked="p:q0"]')
    check('a card held three times has a count that starts at 1', /1 of 3/.test(await row.locator('[data-qty]').textContent()))
    await row.locator('[data-qty-up]').click(); await row.locator('[data-qty-up]').click()
    check('...goes up to 3 and no further', /3 of 3/.test(await row.locator('[data-qty]').textContent()) && (await row.locator('[data-qty-up]').isDisabled()))
    await row.locator('[data-qty-down]').click()
    check('...and back down, never below 1', /2 of 3/.test(await row.locator('[data-qty]').textContent()))
    check('a card held once has no count to change', (await page.locator('[data-swap-tray="theirs"] [data-swap-picked="p:q2"] [data-qty]').count()) === 0)
    // yours: Zed and the card held twice (index 4 in the list is MANY[0]'s slot in mine)
    await dotFor('yours', 'Zed')
    await dotFor('yours', 'Many00')
    await page.waitForSelector('[data-swap-confirm]')
    const text = await page.locator('[data-swap-confirm]').textContent()
    check('the confirm line counts both sides', /You give 2 for 3 from Dave, Dan/.test(text), text)
    check('no horizontal scroll with the trays full', (await overflow(page)) <= 0)
    if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/many-builder.png`, fullPage: true })
    await page.click('[data-swap-send]')
    await page.waitForSelector('[data-swap-builder]', { state: 'detached' })
    const body = posted[posted.length - 1]
    check('Send posts every card with its count', JSON.stringify(body) === JSON.stringify({ to_player_id: 'p7', give: [{ key: 'p:p2', qty: 1 }, { key: 'p:q0', qty: 1 }], want: [{ key: 'p:q0', qty: 2 }, { key: 'p:q2', qty: 1 }] }), JSON.stringify(body))
    await ctx.close()
  }

  console.log('\nfinding a card')
  {
    const { ctx, page } = await open(390)
    await page.click('[data-cards-tab="swaps"]')
    await page.waitForSelector('[data-find-input]')
    finds.length = 0
    await page.fill('[data-find-input]', 'z')
    await page.waitForTimeout(600)
    check('one letter does not search', finds.length === 0 && (await page.locator('[data-find-results]').count()) === 0)
    await page.fill('[data-find-input]', 'zed')
    await page.waitForSelector('[data-find-card="p:p2"]')
    check('a search asks the server once, for exactly what was typed', finds.length === 1 && finds[0] === 'zed', JSON.stringify(finds))
    const card = page.locator('[data-find-card="p:p2"]')
    const asks = await card.locator('[data-find-ask]').allTextContents()
    check('every holder gets an Ask button, with how many could go', asks.length === 2 && /Ask Dave, Dan \(×2\)/.test(asks[0]) && /Ask Smith, Sue$/.test(asks[1].trim()), JSON.stringify(asks))
    check('players nobody has pulled yet are named', /Nobody has pulled Eagle, Ed yet/.test(await page.locator('[data-find-unheld]').textContent()))
    check('no horizontal scroll with results', (await overflow(page)) <= 0)
    if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/find.png` })
    await card.locator('[data-find-ask="p7"]').click()
    await page.waitForSelector('[data-swap-builder]')
    await page.waitForSelector('[data-card-pick="theirs"] [data-slot-card]')
    check('Ask opens a request with that player and that card already chosen', (await page.locator('[data-swap-player]').count()) === 0 && /Dave, Dan/.test(await page.locator('[data-swap-builder]').textContent()) && (await page.locator('[data-swap-tray="theirs"] [data-swap-picked="p:p2"]').count()) === 1)
    check('...and goes on to what you give', (await page.locator('[data-card-pick="yours"]').count()) === 1)
    if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/find-builder.png` })
    await ctx.close()
  }

  console.log('\nthe builder on a wide screen, 1280')
  {
    const { ctx, page } = await open(1280)
    await page.click('[data-cards-tab="swaps"]')
    await page.click('[data-swap-start]')
    await page.locator('[data-swap-player="p7"]').click()
    await page.waitForSelector('[data-card-pick="theirs"] [data-slot-card]')
    check('their cards open as a book with several to a page', (await page.locator('[data-card-pick="theirs"] [data-slot-card]').count()) >= 6)
    check('no horizontal scroll at 1280', (await overflow(page)) <= 0)
    if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/builder-1280.png` })
    await ctx.close()
  }

  check('no errors in the console or the page', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
