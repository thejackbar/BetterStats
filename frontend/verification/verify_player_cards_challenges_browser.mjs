// Player Cards challenges, in Chromium on the production build with the API stubbed:
//  * the player's Challenges screen: exchange and collection challenges with their rewards, a collection's cards, the earned banner, a player's
//    own private sets (made and deleted, with the exact request on the wire), no horizontal scroll at 390;
//  * the squad builder: tap cards to pick them (each once, tap again to put it back), the checklist comes from the server, Finish sends exactly
//    the cards picked and says what was earned and that every card is kept;
//  * the admin Challenges tab: make an exchange (the body on the wire carries exactly the rules set), make a collection from a premiership,
//    change one, remove one (asks first), and a refusal from the server is shown.
//
//   APP_URL=http://localhost:4173 node verification/verify_player_cards_challenges_browser.mjs
import { chromium } from 'playwright'
import { cardsUrl } from './lib/cardsPage.mjs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}
const CLUB = { name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c', font_config: {} }
const ME = 'p1'
const card = (pid, name, tier, rarity, x = {}) => ({
  kind: 'player', key: `p:${pid}`, player_id: pid, name, photo_url: null, hero_photo_url: null, matches: 100, runs: 1500, bat_avg: 24.5,
  wickets: 20, bowl_avg: 31.2, dismissals: 30, rarity, tier, copies: 1, obtained_at: '2026-10-20T01:00:00Z', mine: false, ...x,
})
const SPEND = [{ ...card('p2', 'Zed, Alan', 'common', 18), copies: 2 }, { ...card('p3', 'Adams, Brian', 'epic', 81), copies: 1 }, { ...card('p4', 'Hill, Tom', 'rare', 55), copies: 1 }]
// A batters' challenge with roles, ratings across the range and special cards, for the filters.
const special = (id, pid, name, kind, title, x = {}) => ({ kind: 'special', key: `s:${id}`, special_id: id, special_kind: kind, player_id: pid, name, photo_url: null, hero_photo_url: null, title, occurred_on: '2024-01-01', detail: { season: '2023/24', grade: 'A Grade' }, tier: 'special', copies: 1, ...x })
const FILTER_CARDS = [
  card('b1', 'Brown, Sam', 'legendary', 95, { role: 'BAT' }), card('b2', 'Cole, Ned', 'rare', 52, { role: 'BAT' }), card('b3', 'Dunn, Kai', 'common', 12, { role: 'BAT' }),
  card('w1', 'Ford, Lee', 'epic', 78, { role: 'BOWL' }), card('k1', 'Gray, Max', 'rare', 60, { role: 'WK' }), card('n1', 'Hart, Joe', 'common', 30),
  special('x1', 'b1', 'Brown, Sam', 'century', '112 v Rovers', { role: 'BAT' }), special('x2', 'w1', 'Ford, Lee', 'award', 'Bowler of the Year', { role: 'BOWL' }),
]
const reward = { quality: 'special', quality_label: 'Special', qty: 2, size: 5, title: 'Squad reward' }
const EXCHANGE = { id: 'c1', kind: 'exchange', title: 'Rare squad', blurb: 'Two rares and a common.', reward, starts_on: null, ends_on: null, status: 'open', completions: 0, max_completions: 2, finished: false, requirements: ['3 cards', 'At least 1 Rare', 'At least 1 Common'], count: 3 }
const COLLECTION = {
  id: 'c2', kind: 'collection', title: '2019 A Grade premiers', blurb: null, reward: { ...reward, qty: 1, title: '2019 A Grade premiers' }, starts_on: null, ends_on: null, status: 'open', completions: 0, max_completions: 1, finished: false,
  total: 3, need: 3, owned: 1, percent: 33, complete: false,
  members: [{ key: 'p:p2', name: 'Zed, Alan', tier: 'common', held: true }, { key: 'p:p3', name: 'Adams, Brian', tier: 'epic', held: false }, { key: 'p:p4', name: 'Hill, Tom', tier: 'rare', held: false }],
}
const MY_SET = { id: 's1', title: 'My favourites', owned: 1, total: 2, percent: 50, complete: false, members: [{ key: 'p:p2', name: 'Zed, Alan', tier: 'common', held: true }, { key: 'p:p3', name: 'Adams, Brian', tier: 'epic', held: false }] }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = []

  // ── The player's screens ───────────────────────────────────────────────────
  console.log('\nthe player')
  const calls = []
  const state = { mySets: [MY_SET], earned: [{ title: 'Ton Up', qty: 1, quality: 'boosted', quality_label: 'Boosted' }], verdictOk: false, submitted: false, failSubmit: false }
  const player = async (width, route, wait) => {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500 })
    const page = await ctx.newPage()
    page.setDefaultTimeout(15000)
    page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|font/i.test(m.text())) errors.push(m.text()) })
    page.on('pageerror', (e) => errors.push(String(e)))
    await page.route('**/api/**', async (r) => {
      const rq = r.request(), url = rq.url(), method = rq.method()
      const json = (b, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
      if (!url.includes('/public/availability/')) return json({})
      const path = new URL(url).pathname.replace(/^.*\/me\/cards/, '')
      const body = rq.postData() ? JSON.parse(rq.postData()) : null
      if (/\/me\/cards\/challenge/.test(url) || /\/me\/cards\/my-sets/.test(url)) calls.push({ method, path, body })
      if (path === '/challenges' && method === 'GET') {
        const earned = state.earned; state.earned = []
        return json({ challenges: [EXCHANGE, COLLECTION], my_sets: state.mySets, max_my_sets: 20, earned })
      }
      if (path === '/challenge-options') return json({ players: [{ id: 'p2', name: 'Zed, Alan' }, { id: 'p3', name: 'Adams, Brian' }], premierships: [{ season: '2019', grade: 'A Grade', players: 3, label: '2019 A Grade premiers' }], tiers: [{ key: 'rare', label: 'Rare' }], special_kinds: [{ key: 'century', label: 'Century card' }] })
      if (path === '/my-sets' && method === 'POST') { state.mySets = [...state.mySets, { ...MY_SET, id: 's2', title: body.title || 'Zed fans' }]; return json({ ok: true }) }
      if (/^\/my-sets\//.test(path) && method === 'DELETE') { state.mySets = state.mySets.filter((s) => `/my-sets/${s.id}` !== path); return json({ ok: true }) }
      if (/^\/challenges\/c1\/check$/.test(path)) {
        const n = body.cards.length
        return json({ ok: n === 3, checks: [{ id: 'count', label: '3 cards', ok: n === 3, have: n, need: 3 }, { id: 'rare', label: 'At least 1 Rare', ok: body.cards.some((c) => c.key === 'p:p4'), have: 0, need: 1 }], rating: 61 })
      }
      if (/^\/challenges\/c1\/submit$/.test(path)) {
        if (state.failSubmit) return json({ detail: 'You can only use cards you hold.' }, 409)
        state.submitted = true
        return json({ ok: true, used: 3, packs: 2, reward })
      }
      if (/^\/challenges\/c3\/check$/.test(path)) return json({ ok: false, checks: [{ id: 'count', label: '3 cards', ok: false, have: body.cards.length, need: 3 }], rating: null })
      if (/^\/challenges\/c3$/.test(path)) return json({ id: 'c3', title: 'Top order', blurb: null, rules: { count: 3, kinds: 'any', roles: ['BAT'] }, requirements: ['3 cards', 'Only batters'], reward, status: 'open', completions: 0, max_completions: 1, cards: FILTER_CARDS })
      if (/^\/challenges\/c1$/.test(path)) return json({ id: 'c1', title: EXCHANGE.title, blurb: EXCHANGE.blurb, rules: {}, requirements: EXCHANGE.requirements, reward, status: 'open', completions: state.submitted ? 1 : 0, max_completions: 2, cards: SPEND })
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: [], pack_size: 5, season: 'Summer', cards: [], totals: {} })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 0, swaps_waiting: 0 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
      if (/\/me(\?|$)/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
      return json({ club: CLUB, require_pin: true, has_availability: false, players: [{ id: ME, display_name: 'Barendse, Jack', has_phone: true }] })
    })
    await page.goto(cardsUrl(BASE, 'tok123', route))
    await page.waitForSelector(wait, { timeout: 20000 })
    await page.waitForTimeout(300)
    return { ctx, page }
  }
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)

  {
    const { ctx, page } = await player(1280, '/challenges', '[data-screen="challenges"]')
    check('the earned banner says what was paid, once', /Ton Up is finished/.test(await page.locator('[data-earned]').innerText()) && /Boosted reward pack/.test(await page.locator('[data-earned]').innerText()))
    check('an exchange shows its rules and reward, with a way in', (await page.locator('[data-challenge="c1"] [data-requirements] li').count()) === 3 && /2 packs/.test(await page.locator('[data-challenge="c1"] [data-reward]').innerText()) && (await page.locator('[data-challenge="c1"] [data-challenge-go]').count()) === 1)
    check('a collection shows progress and no way to hand in', /1 of 3/i.test(await page.locator('[data-challenge="c2"] [data-challenge-progress]').innerText()) && (await page.locator('[data-challenge="c2"] [data-challenge-go]').count()) === 0)
    await page.locator('[data-challenge="c2"] [data-members-toggle]').click()
    check('the collection lists its cards with the held one marked', (await page.locator('[data-challenge="c2"] [data-member]').count()) === 3 && (await page.locator('[data-member="p:p2"]').getAttribute('data-held')) === 'yes' && (await page.locator('[data-member="p:p3"]').getAttribute('data-held')) === 'no')
    {
      // The held card is shaded behind its own name (no tick in another column); the one still needed is a faint dashed outline.
      const bg = (key) => page.locator(`[data-member="${key}"]`).evaluate((el) => getComputedStyle(el).backgroundColor)
      const held = await bg('p:p2'), need = await bg('p:p3')
      check('a held card is shaded and a needed one is not', held !== need && /0\)$|transparent/.test(need) && !/0\)$/.test(held), `held=${held} need=${need}`)
      check('no tick sits in a separate column', !/✓/.test(await page.locator('[data-challenge="c2"] [data-members]').innerText()))
      check('the list says what shading means', /Shaded cards are the ones you hold/.test(await page.locator('[data-challenge="c2"] [data-members-legend]').innerText()))
    }
    check('the private set is there and says it pays nothing', (await page.locator('[data-my-set="s1"]').count()) === 1 && /pay nothing/.test(await page.locator('[data-section="my-sets"]').innerText()))

    // Make a set.
    await page.click('[data-new-set]')
    check('Make the set stays off until something is picked', await page.locator('[data-set-make]').isDisabled())
    await page.selectOption('[aria-label="What to collect"]', 'premiership')
    await page.selectOption('[aria-label="Premiership"]', '2019|A Grade')
    await page.fill('[aria-label="Name of the set"]', 'The 2019 side')
    await page.click('[data-set-make]')
    await page.waitForSelector('[data-my-set="s2"]')
    const made = calls.find((c) => c.method === 'POST' && c.path === '/my-sets')
    check('the set request carries the name and the picked premiership', made && made.body.title === 'The 2019 side' && JSON.stringify(made.body.selector) === JSON.stringify({ type: 'premiership', season: '2019', grade: 'A Grade' }), JSON.stringify(made))
    check('the new set appears and the banner does not come back', (await page.locator('[data-my-set]').count()) === 2 && (await page.locator('[data-earned]').count()) === 0)
    await page.click('[data-new-set]')
    await page.selectOption('[aria-label="What to collect"]', 'players')
    await page.locator('[data-set-players] input[type=checkbox]').first().check()
    check('players can be picked for a set', /1 player picked/.test(await page.locator('[data-set-builder]').innerText()))
    await page.click('text=Cancel')
    await page.locator('[data-my-set="s2"] [data-my-set-delete]').click()
    await page.waitForFunction(() => document.querySelectorAll('[data-my-set]').length === 1)
    check('deleting a set sends a DELETE for that set', calls.some((c) => c.method === 'DELETE' && c.path === '/my-sets/s2'))
    await ctx.close()
  }

  {
    const { ctx, page } = await player(1280, '/challenges/c1', '[data-screen="challenge"]')
    check('the builder lists the cards the player can pick, with the rules unticked', (await page.locator('[data-challenge-card]').count()) === 3 && (await page.locator('[data-check-ok="no"]').count()) === 3)
    check('Finish is off with nothing picked', await page.locator('[data-handin]').isDisabled())
    const tap = (k) => page.locator(`[data-challenge-card="${k}"] button, [data-challenge-card="${k}"] [role=button]`).first().click()
    const before = calls.filter((c) => /check$/.test(c.path)).length
    await tap('p:p2'); await tap('p:p3'); await tap('p:p4')
    await page.waitForFunction(() => document.querySelector('[data-check="rare"]')?.getAttribute('data-check-ok') === 'yes')
    check('the checklist comes from the server', (await page.locator('[data-check="count"]').getAttribute('data-check-ok')) === 'yes' && (await page.locator('[data-check="count"]').innerText()).includes('3/3'))
    check('three quick taps are checked once or twice, not once each', calls.filter((c) => /check$/.test(c.path)).length - before <= 2)
    await tap('p:p2')
    check('tapping a picked card puts it back, and a card can only be picked once', (await page.locator('[data-picked-row]').count()) === 2 && (await page.locator('[data-picked-row="p:p2"]').count()) === 0)
    await page.waitForFunction(() => document.querySelector('[data-check="count"]')?.getAttribute('data-check-ok') === 'no')
    check('with a card missing the count line shows it and Finish is off', await page.locator('[data-handin]').isDisabled())
    await tap('p:p2')
    await page.waitForFunction(() => document.querySelector('[data-check="count"]')?.getAttribute('data-check-ok') === 'yes')
    check('with the rules met the checklist ticks and Finish turns on', (await page.locator('[data-check-ok="yes"]').count()) === 2 && !(await page.locator('[data-handin]').isDisabled()) && /Squad rating 61/i.test(await page.locator('[data-rating]').innerText()))
    check('the screen says every card is kept, and there is no confirmation about spending', /keep every card/i.test(await page.locator('[data-challenge-side]').innerText()) && (await page.locator('[data-handin-confirm]').count()) === 0)
    await page.click('[data-handin]')
    await page.waitForSelector('[data-challenge-done]')
    const sub = calls.find((c) => /submit$/.test(c.path))
    check('Finish sends exactly the cards picked, once each', JSON.stringify((sub?.body?.cards || []).map((c) => c.key).sort()) === JSON.stringify(['p:p2', 'p:p3', 'p:p4']) && (sub?.body?.cards || []).every((c) => c.qty === undefined), JSON.stringify(sub?.body))
    check('it then says what was earned, with a link to the packs', /used 3 cards and earned 2 Special reward packs/.test(await page.locator('[data-challenge-done]').innerText()) && /still yours/.test(await page.locator('[data-challenge-done]').innerText()) && (await page.locator('[data-challenge-done] a[href$="/cards/packs"]').count()) === 1)
    await ctx.close()
  }

  {
    state.failSubmit = true; state.submitted = false
    const { ctx, page } = await player(1280, '/challenges/c1', '[data-screen="challenge"]')
    const tap = (k) => page.locator(`[data-challenge-card="${k}"] button, [data-challenge-card="${k}"] [role=button]`).first().click()
    await tap('p:p2'); await tap('p:p3'); await tap('p:p4')
    await page.waitForFunction(() => document.querySelector('[data-check="count"]')?.getAttribute('data-check-ok') === 'yes')
    await page.click('[data-handin]')
    await page.waitForSelector('[role=alert]')
    check('a refusal from the server is shown and the cards stay picked', /only use cards you hold/.test(await page.locator('[role=alert]').innerText()) && (await page.locator('[data-picked-row]').count()) === 3 && (await page.locator('[data-challenge-done]').count()) === 0)
    state.failSubmit = false
    await ctx.close()
  }

  {
    const { ctx, page } = await player(1280, '/challenges/c3', '[data-screen="challenge"]')
    // Every step is presence-safe, so the screen before these filters reports each check as failed instead of stopping.
    page.setDefaultTimeout(3000)
    const act = (fn) => fn().catch(() => null)
    const shown = () => page.locator('[data-challenge-card]').evaluateAll((els) => els.map((e) => e.getAttribute('data-challenge-card')))
    const same = async (want) => JSON.stringify((await shown()).slice().sort()) === JSON.stringify(want.slice().sort())
    check('a challenge with a role rule starts on the cards that fit it', (await act(() => page.locator('[data-filter-fits]').isChecked())) && await same(['p:b1', 'p:b2', 'p:b3', 's:x1']), JSON.stringify(await shown()))
    check('the count says how many of the cards are shown', /Showing 4 of 8/.test(await act(() => page.locator('[data-filter-count]').innerText())))
    await act(() => page.locator('[data-filter-fits]').uncheck())
    check('unticking it shows every card', (await page.locator('[data-challenge-card]').count()) === 8)
    check('role chips are drawn only for roles some card has, plus no role recorded', (await page.locator('[data-filter-row="role"] [role=tab]').count()) === 5 && (await page.locator('[data-filter="role:AR"]').count()) === 0 && (await page.locator('[data-filter="role:none"]').count()) === 1)
    await act(() => page.click('[data-filter="role:BOWL"]'))
    check('the role filter keeps bowlers, player and special cards', await same(['p:w1', 's:x2']), JSON.stringify(await shown()))
    await act(() => page.click('[data-filter="role:none"]'))
    check('no role recorded keeps the players without one', await same(['p:n1']), JSON.stringify(await shown()))
    await act(() => page.click('[data-filter="role:any"]'))
    await act(() => page.fill('[data-rating-lo]', '50')); await act(() => page.fill('[data-rating-hi]', '80'))
    check('a rating range of 50 to 80 keeps only player cards in it', await same(['p:b2', 'p:w1', 'p:k1']), JSON.stringify(await shown()))
    check('the screen says why special cards are hidden', (await page.locator('[data-rating-note]').count()) === 1)
    await act(() => page.fill('[data-rating-lo]', '1')); await act(() => page.fill('[data-rating-hi]', '99'))
    check('the full range of 1 to 99 brings the specials back', (await page.locator('[data-challenge-card]').count()) === 8 && (await page.locator('[data-rating-note]').count()) === 0)
    await act(() => page.fill('[data-rating-lo]', '150')); await act(() => page.locator('[data-rating-lo]').blur())
    check('a rating above 99 is held at 99', (await act(() => page.locator('[data-rating-lo]').inputValue())) === '99' && await same([]))
    await act(() => page.fill('[data-rating-lo]', '0')); await act(() => page.locator('[data-rating-lo]').blur())
    await act(() => page.fill('[data-rating-hi]', '20')); await act(() => page.locator('[data-rating-hi]').blur())
    check('a rating below 1 is held at 1', (await act(() => page.locator('[data-rating-lo]').inputValue())) === '1' && await same(['p:b3']), JSON.stringify(await shown()))
    await act(() => page.fill('[data-rating-lo]', '90')); await act(() => page.locator('[data-rating-lo]').blur())
    check('a low end above the high end swaps them', (await act(() => page.locator('[data-rating-lo]').inputValue())) === '20' && (await act(() => page.locator('[data-rating-hi]').inputValue())) === '90')
    await act(() => page.click('[data-filter-clear]'))
    check('Clear filters puts everything back, with the rules filter on again', (await act(() => page.locator('[data-filter-fits]').isChecked())) && (await page.locator('[data-challenge-card]').count()) === 4 && (await act(() => page.locator('[data-rating-hi]').inputValue())) === '99')
    await act(() => page.locator('[data-filter-fits]').uncheck())
    await act(() => page.click('[data-filter="type:centuries"]'))
    check('the type chips go down to a kind of special card', await same(['s:x1']))
    await act(() => page.click('[data-filter="type:player"]'))
    await act(() => page.selectOption('[data-filter-sort]', 'rating_asc'))
    check('sorting by lowest rating orders the players by rating', JSON.stringify(await shown()) === JSON.stringify(['p:b3', 'p:n1', 'p:b2', 'p:k1', 'p:w1', 'p:b1']), JSON.stringify(await shown()))
    await act(() => page.fill('[data-filter-search]', 'ford'))
    check('search narrows within the other filters', await same(['p:w1']))
    await act(() => page.locator('[data-challenge-card="p:w1"] button, [data-challenge-card="p:w1"] [role=button]').first().click())
    await act(() => page.fill('[data-filter-search]', 'brown'))
    check('a picked card stays picked when a filter hides it', (await page.locator('[data-picked-row="p:w1"]').count()) === 1 && (await page.locator('[data-challenge-card="p:w1"]').count()) === 0)
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/challenge-filters-1280.png` : '/dev/null' }).catch(() => {})
    await ctx.close()
  }

  for (const route of ['/challenges', '/challenges/c1', '/challenges/c3']) {
    const { ctx, page } = await player(390, route, route === '/challenges' ? '[data-screen="challenges"]' : '[data-screen="challenge"]')
    if (route === '/challenges') await page.locator('[data-challenge="c2"] [data-members-toggle]').click()
    check(`${route} has no sideways scroll at 390`, (await overflow(page)) <= 0, String(await overflow(page)))
    await ctx.close()
  }

  // ── The admin tab ──────────────────────────────────────────────────────────
  console.log('\nthe admin tab')
  const admin = {
    list: [{ id: 'a1', kind: 'exchange', title: 'Old exchange', blurb: null, rules: { count: 5, kinds: 'any', players: ['p2'], players_label: '2019 A Grade premiers' }, reward: { quality: 'boosted', qty: 1, size: 5 }, max_completions: 1, starts_on: null, ends_on: null, active: true, sort_order: 0, completions: 3, players_done: 2, requirements: ['5 cards', 'Only 2019 A Grade premiers'] }],
    refuse: null,
  }
  const payload = () => ({
    challenges: admin.list,
    premierships: [{ season: '2019', grade: 'A Grade', players: 3, label: '2019 A Grade premiers' }],
    players: [{ id: 'p2', name: 'Zed, Alan' }, { id: 'p3', name: 'Adams, Brian' }],
    tiers: ['common', 'rare', 'epic', 'legendary', 'special'].map((k) => ({ key: k, label: k[0].toUpperCase() + k.slice(1) })),
    special_kinds: [{ key: 'century', label: 'Century card' }],
    roles: [{ key: 'BAT', label: 'Batter' }, { key: 'BOWL', label: 'Bowler' }, { key: 'AR', label: 'All Rounder' }, { key: 'WK', label: 'Wicketkeeper' }],
    qualities: [{ key: 'standard', label: 'Standard', line: 'A plain pack', rare_plus: 0, odds: { epic: 5, legendary: 1 }, special_pct: 0 }, { key: 'special', label: 'Special', line: 'Better odds', rare_plus: 2, odds: { epic: 12, legendary: 3 }, special_pct: 5 }],
    limits: { count: 30, completions: 10, reward_qty: 5, pack_size: { min: 1, max: 12, default: 5 } },
  })
  const adminCalls = []
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  page.setDefaultTimeout(10000)
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errors.push(m.text()) })
  await page.route('**/api/**', async (route) => {
    const rq = route.request(), url = rq.url(), method = rq.method()
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(url)) return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', entitlements: { modules: [], status: 'active' } })
    if (!/\/player-cards\//.test(url)) return json({})
    const path = new URL(url).pathname.replace(/^\/api/, '')
    const body = rq.postData() ? JSON.parse(rq.postData()) : null
    if (/^\/player-cards\/challenges/.test(path)) {
      if (method !== 'GET') adminCalls.push({ method, path, body })
      if (method === 'POST' || method === 'PUT') {
        if (admin.refuse) return json({ detail: admin.refuse }, 400)
        const row = { id: method === 'PUT' ? path.split('/').pop() : `a${admin.list.length + 1}`, kind: body.kind, title: body.title, blurb: body.blurb, rules: body.rules || { selector: body.selector, card_keys: ['p:p2'], need: body.need || 1 }, reward: body.reward,
          max_completions: body.max_completions || 1, starts_on: body.starts_on, ends_on: body.ends_on, active: body.active, sort_order: body.sort_order, completions: 0, players_done: 0, requirements: ['stub'] }
        admin.list = method === 'PUT' ? admin.list.map((c) => (c.id === row.id ? row : c)) : [...admin.list, row]
      }
      if (method === 'DELETE') admin.list = admin.list.filter((c) => c.id !== path.split('/').pop())
      return json(payload())
    }
    if (path === '/player-cards/overview') return json({ totals: {}, players: [] })
    if (path === '/player-cards/activity') return json({ daily: [], recent_specials: [], recent_cards: [], recent_openings: [] })
    return json({ club: CLUB, settings: { enabled: true, include_juniors: false, weekly_packs: 1, timezone: null, effective_timezone: 'Australia/Perth', event_packs_enabled: true, starter_gifts: 'minimal' }, events: [], designs: {}, design_targets: [], timezones: [], max_weekly_packs: 10, link: { path: '/playerdash/tok123' }, pool: { size: 0, players: 0 }, players: [] })
  })
  await page.goto(`${BASE}/admin/player-cards`)
  await page.waitForSelector('[data-player-cards-admin]')
  await page.click('[data-pc-tab="challenges"]')
  await page.waitForSelector('[data-admin-challenges]')
  check('the tab lists the challenge with how often it was done and what it pays', /Old exchange/.test(await page.locator('[data-challenge-row="a1"]').innerText()) && /done 3 times by 2 players/.test(await page.locator('[data-challenge-row="a1"]').innerText()) && /1 pack of 5/.test(await page.locator('[data-challenge-row="a1"]').innerText()))

  await page.click('[data-challenge-new] button')
  await page.waitForSelector('[data-challenge-form]')
  check('Publish stays off until it has a name', await page.locator('[data-challenge-save] button').isDisabled())
  await page.fill('[aria-label="Challenge name"]', 'Rare squad')
  await page.fill('[aria-label="Cards in the squad"]', '11')
  await page.selectOption('[aria-label="Kind of card"]', 'players')
  await page.fill('[data-min-tier="rare"]', '3')
  await page.click('[data-checks="roles"] [data-check="BOWL"]')
  await page.click('[data-checks="roles"] [data-check="AR"]')
  await page.fill('[data-min-role="BOWL"]', '2')
  await page.fill('[aria-label="Squad rating"]', '70')
  await page.fill('[aria-label="Cards of one player"]', '1')
  await page.locator('[data-checks="tiers"] [data-check="common"]').click()
  await page.locator('[data-checks="tiers"] [data-check="rare"]').click()
  await page.selectOption('[aria-label="Premiership side"]', '2019|A Grade')
  await page.selectOption('[aria-label="Reward pack quality"]', 'special')
  await page.fill('[aria-label="Reward packs"]', '2')
  await page.fill('[aria-label="Cards in each reward pack"]', '7')
  await page.fill('[aria-label="Reward pack name"]', 'Squad reward')
  await page.fill('[aria-label="Times it can be completed"]', '3')
  await page.fill('[aria-label="Closes on"]', '2026-12-31')
  await page.locator('[data-challenge-save] button').click()
  await page.waitForSelector('[data-challenge-row="a2"]')
  const made = adminCalls.find((c) => c.method === 'POST')
  check('the exchange is sent with exactly the rules set', JSON.stringify(made?.body?.rules) === JSON.stringify({ count: 11, kinds: 'players', tiers_only: ['common', 'rare'], min_tier: { rare: 3 }, min_rating: 70, max_per_player: 1, roles: ['BOWL', 'AR'], min_role: { BOWL: 2 }, premiership: { season: '2019', grade: 'A Grade' } }), JSON.stringify(made?.body?.rules))
  check('...with the reward, the completions and the closing day', JSON.stringify(made?.body?.reward) === JSON.stringify({ quality: 'special', qty: 2, size: 7, title: 'Squad reward' }) && made.body.max_completions === 3 && made.body.ends_on === '2026-12-31' && made.body.starts_on === null, JSON.stringify(made?.body))
  check('the form closes and the list has the new challenge', (await page.locator('[data-challenge-form]').count()) === 0 && (await page.locator('[data-challenge-row]').count()) === 2)

  // A collection.
  await page.click('[data-challenge-new] button')
  await page.click('[data-challenge-kind="collection"]')
  await page.fill('[aria-label="Challenge name"]', '2019 side')
  check('a collection asks what to collect, not for rules', (await page.locator('[data-collection-rules]').count()) === 1 && (await page.locator('[data-exchange-rules]').count()) === 0)
  await page.selectOption('[aria-label="Premiership side"]', '2019|A Grade')
  await page.fill('[aria-label="Cards needed"]', '2')
  await page.locator('[data-challenge-save] button').click()
  await page.waitForSelector('[data-challenge-row="a3"]')
  const col = adminCalls.filter((c) => c.method === 'POST')[1]
  check('the collection is sent with its selector and how many are needed', JSON.stringify(col?.body?.selector) === JSON.stringify({ type: 'premiership', season: '2019', grade: 'A Grade' }) && col.body.need === 2 && col.body.kind === 'collection', JSON.stringify(col?.body))

  // Change an exchange that was limited to a list of players: the list is kept unless another side is picked.
  await page.click('[data-challenge-edit="a1"] button')
  await page.waitForSelector('[data-challenge-form]')
  check('the form opens filled in, with the kept list of players shown', (await page.inputValue('[aria-label="Challenge name"]')) === 'Old exchange' && /2019 A Grade premiers/.test(await page.locator('[aria-label="Premiership side"] option').first().innerText()))
  await page.fill('[aria-label="Challenge name"]', 'Old exchange v2')
  await page.locator('[data-challenge-save] button').click()
  await page.waitForSelector('text=Old exchange v2')
  const put = adminCalls.find((c) => c.method === 'PUT')
  check('saving sends a PUT for that challenge and keeps the list of players', put?.path === '/player-cards/challenges/a1' && JSON.stringify(put.body.rules.players) === '["p2"]' && put.body.rules.players_label === '2019 A Grade premiers' && !put.body.rules.premiership, JSON.stringify(put?.body?.rules))

  // A refusal.
  admin.refuse = 'Nobody from that premiership has a card yet.'
  await page.click('[data-challenge-new] button')
  await page.fill('[aria-label="Challenge name"]', 'Bad one')
  await page.locator('[data-challenge-save] button').click()
  await page.waitForSelector('[data-challenge-error]')
  check('a refusal from the server is shown in the form, which stays open', /Nobody from that premiership/.test(await page.locator('[data-challenge-error]').innerText()) && (await page.locator('[data-challenge-form]').count()) === 1)
  admin.refuse = null
  await page.click('text=Cancel')

  // Remove.
  await page.click('[data-challenge-delete="a3"] button')
  check('Remove asks first and sends nothing', (await page.locator('[data-challenge-confirm-delete="a3"]').count()) === 1 && !adminCalls.some((c) => c.method === 'DELETE'))
  await page.click('[data-challenge-confirm-delete="a3"] button')
  await page.waitForFunction(() => !document.querySelector('[data-challenge-row="a3"]'))
  check('Yes, remove sends a DELETE for it', adminCalls.some((c) => c.method === 'DELETE' && c.path === '/player-cards/challenges/a3'))

  await page.setViewportSize({ width: 390, height: 900 })
  await page.click('[data-challenge-new] button')
  await page.waitForTimeout(200)
  check('the admin tab has no sideways scroll at 390', (await overflow(page)) <= 0, String(await overflow(page)))
  await ctx.close()

  check('no errors in the console', errors.length === 0, errors.slice(0, 3).join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
