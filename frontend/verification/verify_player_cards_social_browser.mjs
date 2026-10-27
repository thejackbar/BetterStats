// Player Cards, the social side, in Chromium on the production build with the API stubbed at the network layer:
//  * the wish list (who could swap each card, Ask into a prefilled request, take a card off, the badge on the menu);
//  * adding to the wish list from Club cards, and the card page (opened cold from its address, holders, wish list toggle);
//  * spares (tick several, offer them in one go with the right counts, open to offers and the demand number);
//  * counter offers (Change it, the builder pre-filled with their cards and yours, a note, the exact request sent);
//  * settings (only the setting changed is sent, and the notices for a club switch and a missing address);
//  * 390px for overflow and no errors in the console.
//
//   APP_URL=http://localhost:4173 node verification/verify_player_cards_social_browser.mjs
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
const MINE = card(ME, 'Barendse, Jack', 'rare', 62, { mine: true })
const BRAVO = card('p3', 'Bravo, Bob', 'epic', 80)
const COLE = card('p4', 'Cole, Cam', 'rare', 66)
const DUNN = card('p5', 'Dunn, Dee', 'common', 30)
const CARDS = [MINE, card('p2', 'Zed, Alan', 'common', 18, { copies: 3 })]
const tr = (c, tradeable, x = {}) => ({ ...c, tradeable, copies: undefined, ...x })
const calls = []
let wants, spares, board, prefs
const reset = () => {
  wants = [
    { ...BRAVO, holders: [{ player_id: 'p7', name: 'Dave, Dan', tradeable: 2 }, { player_id: 'p9', name: 'Smith, Sue', tradeable: 1 }], others: 2, mine_copies: 0, added_at: '2026-10-25T00:00:00Z' },
    { ...DUNN, holders: [], others: 0, mine_copies: 0, added_at: '2026-10-24T00:00:00Z' },
  ]
  spares = { cards: [tr(CARDS[1], 2, { key: 'p:p2', spare: 2, open: false }), tr(COLE, 1, { spare: 1, open: true, wanted_by: 3 })], total: 3 }
  const incoming = { id: 'w1', direction: 'in', status: 'pending', other: { player_id: 'p7', name: 'Dave, Dan' }, created_at: new Date().toISOString(), resolved_at: null, note: 'Fancy a swap, mate?', parent_id: null,
    give: [{ ...tr(BRAVO, 1), qty: 1 }, { ...tr(COLE, 1), qty: 1 }], want: [{ ...tr(CARDS[1], 2), qty: 2 }] }
  board = { incoming: [incoming], outgoing: [], recent: [{ ...incoming, id: 'h1', status: 'countered', direction: 'out', resolved_at: new Date().toISOString() }], mine: [tr(CARDS[1], 2), tr(COLE, 1)], people: [{ player_id: 'p7', name: 'Dave, Dan', tradeable: 3 }], expires_days: 14, max_open: 10 }
  prefs = { alert_swaps: true, alert_wants: true, club_alerts: true, email_on_file: true }
}
reset()

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = []
  const open = async (width, route = '/wishlist', { wait = '[data-cards-page] [data-screen]', height = 900 } = {}) => {
    const ctx = await browser.newContext({ viewport: { width, height }, isMobile: width < 500, hasTouch: width < 500 })
    await ctx.grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => {})
    const page = await ctx.newPage()
    page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|font/i.test(m.text())) errors.push(m.text()) })
    page.on('pageerror', (e) => errors.push(String(e)))
    await page.route('**/api/**', async (r) => {
      const req = r.request(), url = req.url(), method = req.method()
      const json = (b, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
      if (!url.includes('/public/availability/')) return json({})
      const path = url.split('/api')[1]
      const body = req.postData() ? JSON.parse(req.postData()) : null
      if (/\/me\/cards\/wants/.test(url)) {
        if (method === 'GET') return json({ wants, ready: wants.filter((w) => w.holders.length).length, limit: 100 })
        calls.push({ method, path, body })
        if (method === 'POST') { wants = [...wants, { ...COLE, holders: [], others: 0, mine_copies: 0, added_at: 'x' }]; return json({ ok: true }) }
        const key = new URL(url).searchParams.get('key'); wants = wants.filter((w) => w.key !== key); return json({ ok: true })
      }
      if (/\/me\/cards\/spares\/open/.test(url)) { calls.push({ method, path, body }); spares.cards = spares.cards.map((c) => (c.key === body.key ? { ...c, open: body.open, ...(body.open ? { wanted_by: 1 } : {}) } : c)); return json({ ok: true }) }
      if (/\/me\/cards\/spares/.test(url)) return json(spares)
      if (/\/me\/cards\/card\?/.test(url) && /not-a-card/.test(url)) return json({ detail: 'That card could not be found.' }, 422)
      if (/\/me\/cards\/card\?/.test(url)) return json({ card: { ...BRAVO, key: new URL(url).searchParams.get('key') }, holders: [{ player_id: 'p7', name: 'Dave, Dan', tradeable: 2 }], mine_copies: 0, wanted: wants.some((w) => w.key === 'p:p3') })
      if (/\/me\/cards\/prefs/.test(url)) { if (method === 'PUT') { calls.push({ method, path, body }); prefs = { ...prefs, ...body } } return json(prefs) }
      if (/\/me\/cards\/catalogue\/holders/.test(url)) return json({ card: BRAVO, holders: [{ player_id: 'p7', name: 'Dave, Dan', tradeable: 2 }], mine_copies: 0 })
      if (/\/me\/cards\/catalogue/.test(url)) return json({ total: 2, counts: { regular: 2, special: 0 }, items: [{ ...BRAVO, others: 1, mine_copies: 0 }, { ...MINE, others: 0, mine_copies: 1 }], offset: 0, limit: 12 })
      if (/\/me\/cards\/swaps\/players\//.test(url)) return json({ player: { player_id: 'p7', name: 'Dave, Dan' }, cards: [tr(BRAVO, 2), tr(COLE, 1), tr(DUNN, 1)] })
      if (/\/me\/cards\/swaps\/[^/]+\/counter$/.test(url)) { calls.push({ method, path, body }); return json({ id: 'n9', status: 'pending' }) }
      if (/\/me\/cards\/swaps$/.test(url) || /\/me\/cards\/swaps\?/.test(url)) { if (method === 'POST') { calls.push({ method, path, body }); return json({ id: 'n1', status: 'pending' }) } return json(board) }
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: [], pack_size: 5, season: 'Summer', cards: CARDS, totals: { regular_owned: 2, regular_total: 14, special_owned: 0, special_total: 0, copies: 4 } })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 0, swaps_waiting: 1 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
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

  console.log('\nthe wish list')
  {
    reset()
    const { ctx, page } = await open(390)
    check('the menu shows how many wish list cards someone could swap', (await page.locator('[data-bottom-bar] [data-nav="more"]').count()) === 1)
    check('cards someone could swap are listed first, with an Ask for each holder', (await page.locator('[data-want-ready]').count()) === 1 && (await page.locator('[data-want="p:p3"] [data-want-ask]').count()) === 2)
    check('...and the ones nobody has are under Still looking, with a way to wait', (await page.locator('[data-want-waiting]').count()) === 1 && /email when someone does/.test(await page.locator('[data-want="p:p5"]').textContent()))
    check('how many places are used', /2 of 100 places used/.test(await page.locator('[data-screen="wishlist"]').textContent()))
    check('no horizontal scroll', (await overflow(page)) <= 0)
    if (SHOT) await page.screenshot({ path: `${SHOT}/social-wishlist-390.png` })
    await page.click('[data-want="p:p3"] [data-want-ask="p7"]')
    await page.waitForSelector('[data-swap-builder]')
    await page.waitForSelector('[data-swap-tray="theirs"] [data-swap-picked]')
    check('Ask opens a request with that player and card chosen', path(page) === '/playerdash/tok123/cards/swaps/new' && (await page.locator('[data-swap-tray="theirs"] [data-swap-picked="p:p3"]').count()) === 1 && /Dave, Dan/.test(await page.locator('[data-swap-builder]').textContent()))
    await page.goBack()
    await page.waitForSelector('[data-screen="wishlist"]')
    calls.length = 0
    await page.click('[data-want="p:p5"] [data-want-remove]')
    await page.waitForFunction(() => !document.querySelector('[data-want="p:p5"]'))
    check('Take off my list sends the delete for that card, and it goes', calls.some((c) => c.method === 'DELETE' && /key=p%3Ap5/.test(c.path)))
    wants = []
    await page.reload(); await page.waitForSelector('[data-screen="wishlist"]')
    check('an empty list says where to add cards from', (await page.locator('[data-no-wants]').count()) === 1)
    await ctx.close()
  }

  console.log('\nadding from Club cards, and the card page')
  {
    reset(); wants = wants.filter((w) => w.key !== 'p:p3')
    const { ctx, page } = await open(1280, '/club', { wait: '[data-catalogue] [data-slot-card]' })
    calls.length = 0
    await page.locator('[data-slot-card="p:p3"]').click()
    await page.waitForSelector('[data-holders]')
    check('a card held up offers Add to wish list and a link to its page', (await page.locator('[data-want-toggle]').count()) === 1 && (await page.locator('[data-card-page-link]').count()) === 1)
    await page.locator('[data-want-toggle]').click()
    await page.waitForTimeout(400)
    check('Add to wish list sends the card by its key', calls.some((c) => c.method === 'POST' && c.body && c.body.key === 'p:p3'), JSON.stringify(calls))
    await ctx.close()
    const cold = await open(1280, `/card/${encodeURIComponent('p:p3')}`, { wait: '[data-screen="card"]' })
    check('a card page opens cold from its address', path(cold.page) === '/playerdash/tok123/cards/card/p%3Ap3' && /Bravo/.test(await cold.page.locator('[data-page-title]').textContent()))
    check('...with who could swap one, and the rarity', (await cold.page.locator('[data-holder="p7"]').count()) === 1 && /80 out of 99/.test(await cold.page.locator('div[data-card-rarity]').filter({ hasText: 'out of 99' }).first().textContent()))
    cold.page.on('dialog', () => {})
    await cold.page.click('[data-copy-link]')
    await cold.page.waitForSelector('[data-copy-note]')
    check('Copy link says what the link does', /Link copied|Copy the address/.test(await cold.page.locator('[data-copy-note]').textContent()))
    calls.length = 0
    wants = wants.filter((w) => w.key !== 'p:p3')
    await cold.page.click('[data-want-toggle]')
    await cold.page.waitForTimeout(400)
    check('the wish list button on the card page sends the card', calls.some((c) => c.method === 'POST' && c.body.key === 'p:p3'))
    await cold.page.click('[data-holder-ask="p7"]')
    await cold.page.waitForSelector('[data-swap-builder]')
    check('Ask on the card page opens a request with that card chosen', (await cold.page.locator('[data-swap-tray="theirs"] [data-swap-picked="p:p3"]').count()) === 1)
    await cold.ctx.close()
    const bad = await open(1280, '/card/not-a-card', { wait: '[data-screen="card"], [data-card-page-error]' })
    check('a card page that cannot be found says so, with a way back', /could not be found/.test(await bad.page.locator('[data-card-page-error]').textContent()) && /Back to Club cards/.test(await bad.page.locator('[data-card-page-error]').textContent()))
    await bad.ctx.close()
  }

  console.log('\nspares')
  {
    reset()
    const { ctx, page } = await open(390, '/spares', { wait: '[data-screen="spares"] [data-spares-total]' })
    check('the total and the cards', /3 spares across 2 cards/.test(await page.locator('[data-spares-total]').textContent()))
    check('open to offers shows the demand as a number for cards that are open, and nothing for the rest', /3 players want this card/.test(await page.locator('[data-open-row="p:p4"] [data-open-note]').textContent()) && !/want/.test(await page.locator('[data-open-row="p:p2"] [data-open-note]').textContent()))
    check('no horizontal scroll', (await overflow(page)) <= 0)
    if (SHOT) await page.screenshot({ path: `${SHOT}/social-spares-390.png`, fullPage: true })
    calls.length = 0
    await page.locator('[data-open-toggle="p:p2"]').click()
    await page.waitForTimeout(400)
    check('switching a card to open sends that card and open true', calls.some((c) => c.path.endsWith('/spares/open') && c.body.key === 'p:p2' && c.body.open === true), JSON.stringify(calls))
    check('...and then shows the demand', /1 player wants this card/.test(await page.locator('[data-open-row="p:p2"] [data-open-note]').textContent()))
    await page.locator('[data-quick-pick]').first().click()
    await page.locator('[data-quick-pick]').nth(1).click()
    await page.waitForSelector('[data-spares-offer]')
    check('ticked cards gather into one offer', (await page.locator('[data-spare-picked]').count()) === 2)
    await page.locator('[data-spare-picked="p:p2"] button[aria-label^="More"]').click()
    await page.click('[data-spares-offer-go]')
    await page.waitForSelector('[data-swap-builder]')
    check('Offer these to someone opens the builder with those cards and counts ready to give', path(page) === '/playerdash/tok123/cards/swaps/new' && (await page.locator('[data-swap-builder]').count()) === 1)
    await page.locator('[data-swap-player="p7"]').click()
    await page.waitForSelector('[data-card-pick="theirs"] [data-slot-card]')
    await page.locator('[data-card-pick="theirs"] [data-quick-pick]').first().click()
    await page.waitForSelector('[data-swap-confirm]')
    check('...both its cards are in the tray of cards you give, with the count', (await page.locator('[data-swap-tray="yours"] [data-swap-picked]').count()) === 2 && /2 of 2/.test(await page.locator('[data-swap-tray="yours"] [data-swap-picked="p:p2"] [data-qty]').textContent()))
    await ctx.close()
  }

  console.log('\nchanging a swap and a note')
  {
    reset()
    const { ctx, page } = await open(390, '/swaps', { wait: '[data-swap-request="w1"]' })
    check('a request shows the note that came with it', /Fancy a swap, mate\?/.test(await page.locator('[data-swap-request="w1"] [data-swap-note]').textContent()))
    check('...and a Change it button beside Accept and Decline', (await page.locator('[data-swap-request="w1"] [data-swap-counter]').count()) === 1)
    await page.click('[data-swap-request="w1"] [data-swap-counter]')
    await page.waitForSelector('[data-swap-builder]')
    await page.waitForSelector('[data-swap-tray="theirs"] [data-swap-picked]')
    check('the builder opens on the same player, who cannot be changed', path(page) === '/playerdash/tok123/cards/swaps/new' && (await page.locator('[data-swap-builder] button:has-text("Change")').count()) === 0 && /Dave, Dan/.test(await page.locator('[data-swap-builder]').textContent()))
    check('what they offered is chosen from their side, and what they asked of you from yours', (await page.locator('[data-swap-tray="theirs"] [data-swap-picked]').count()) === 2 && (await page.locator('[data-swap-tray="yours"] [data-swap-picked="p:p2"]').count()) === 1)
    check('your two copies are carried over as two', /2 of 2/.test(await page.locator('[data-swap-tray="yours"] [data-swap-picked="p:p2"] [data-qty]').textContent()))
    await page.locator('[data-swap-tray="yours"] [data-swap-picked="p:p2"] [data-qty-down]').click()
    await page.waitForSelector('[data-swap-confirm]')
    await page.fill('[data-swap-note-input]', 'Two is plenty for those two')
    calls.length = 0
    await page.click('[data-swap-send]')
    await page.waitForSelector('[data-screen="swaps"]')
    const sent = calls.find((c) => c.path.endsWith('/swaps/w1/counter'))
    check('Send sends the changed cards and the note to the counter route', sent && JSON.stringify(sent.body) === JSON.stringify({ give: [{ key: 'p:p2', qty: 1 }], want: [{ key: 'p:p3', qty: 1 }, { key: 'p:p4', qty: 1 }], note: 'Two is plenty for those two' }), JSON.stringify(sent))
    check('it lands on Swaps with the request sent', path(page) === '/playerdash/tok123/cards/swaps/sent' && /Swap request sent/.test(await page.locator('[data-swap-msg]').textContent()))
    await page.click('[data-swaps-tab="history"]')
    await page.waitForSelector('[data-history]')
    check('History says a swap was changed', /Changed by Dave, Dan|You changed it for/.test(await page.locator('[data-swap-recent][data-status="countered"]').textContent()))
    await ctx.close()
    reset()
    const fresh = await open(390, '/swaps/new', { wait: '[data-swap-builder]' })
    await fresh.page.locator('[data-swap-player="p7"]').click()
    await fresh.page.waitForSelector('[data-card-pick="theirs"] [data-slot-card]')
    await fresh.page.locator('[data-card-pick="theirs"] [data-quick-pick]').first().click()
    await fresh.page.waitForSelector('[data-card-pick="yours"] [data-slot-card]')
    await fresh.page.locator('[data-card-pick="yours"] [data-quick-pick]').first().click()
    await fresh.page.waitForSelector('[data-swap-confirm]')
    check('a new request has a note box that counts down from 200', /200 left/.test(await fresh.page.locator('[data-swap-confirm]').textContent()))
    await fresh.page.fill('[data-swap-note-input]', 'x'.repeat(260))
    check('...and stops at 200', (await fresh.page.inputValue('[data-swap-note-input]')).length === 200)
    await fresh.ctx.close()
  }

  console.log('\nsettings')
  {
    reset()
    const { ctx, page } = await open(390, '/settings', { wait: '[data-screen="settings"] [data-pref]' })
    check('two emails can be switched, both on to begin with', (await page.locator('[data-pref] input:checked').count()) === 2)
    calls.length = 0
    await page.locator('[data-pref="alert_wants"] input').click()
    await page.waitForSelector('[data-saved]')
    const put = calls.find((c) => c.method === 'PUT')
    check('only the setting changed is sent', put && JSON.stringify(put.body) === JSON.stringify({ alert_wants: false }), JSON.stringify(put))
    check('...and it reads back as off, the other still on', (await page.locator('[data-pref="alert_wants"] input').isChecked()) === false && (await page.locator('[data-pref="alert_swaps"] input').isChecked()) === true)
    await ctx.close()
    reset(); prefs = { ...prefs, club_alerts: false, email_on_file: false }
    const off = await open(390, '/settings', { wait: '[data-screen="settings"] [data-pref]' })
    check('a club that has switched emails off is said, and so is a missing address', (await off.page.locator('[data-club-alerts-off]').count()) === 1 && (await off.page.locator('[data-no-email]').count()) === 1)
    await off.ctx.close()
  }

  check('no errors in the console or the page', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
