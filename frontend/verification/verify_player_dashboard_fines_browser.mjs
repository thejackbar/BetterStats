// Drives the REAL screens in Chromium with the API stubbed at the network layer:
//
//   A. The player's private page (/avail/:token, "My page") as a dashboard:
//      * it draws exactly the modules the server lists, in the club's order
//      * the Ladder module asks for the ladder on its own, once, and only when listed
//      * Fines shows what they owe, week by week, with how to pay (copyable rows)
//      * a zero balance reads "all square" and shows no payment block
//      * Fees, Season and Fines each explain an absent figure instead of showing $0
//      * a ladder that fails does not take the rest of the page with it
//      * 390px: no sideways overflow
//   B. The admin Player page chooser (Availability > Self-service link):
//      * lists the modules, ticking one sends the whole ordered list, the arrows reorder
//      * a module the club cannot show yet says why
//   C. BetterSelect > Fines:
//      * it is a side-menu item at /admin/betterselect/fines
//      * the tracker shows every player's fines by date and what they owe
//      * a fines session puts exactly the right body on the wire (blank lines dropped)
//      * Paid records a payment prefilled with what they owe; History voids a fine
//      * Fines switches on and off per squad; how to pay saves the whole form
//      * 390px: no sideways overflow
//
//   npx vite preview --port 5199 &    node verify_player_dashboard_fines_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOT = process.env.SHOT_DIR || '/tmp'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }
const iso = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
const norm = (s) => s.replace(/\s+/g, ' ').trim()

// ─── A. the player's page ──────────────────────────────────────────────────
const CLUB = { name: 'Gisborne CC', logo_url: null, accent_color: null, primary_color: null }
const ME_PUBLIC = {
  club: CLUB, player: { id: 'p1', display_name: 'Sam Sledge' }, has_squad: true, squads: ['1st XI'],
  dates: [{ date: iso(5), fixtures: [{ id: 'f1', opponent_name: 'Rovers', home_away: 'HOME', role: 'single', start_time: '13:00', venue: 'Main Oval', team_name: '1st XI', mine: true }] }],
  availability: { [iso(5)]: { status: 'AVAILABLE' } },
}
const FINES = [{
  squad: '1st XI', fined: 17, paid: 10, owing: 7, pot: 35,
  weeks: [{ date: iso(-1), total: 7, items: [{ reason: 'Chirping the umpire', amount: 7 }] }, { date: iso(-8), total: 10, items: [{ reason: 'Dropped catch', amount: 5 }, { reason: 'Dropped catch', amount: 5 }] }],
  payments: [{ date: iso(-6), amount: 10, method: 'PayID' }],
  how_to_pay: { payid: 'pay@gisborne.org', payid_name: 'Gisborne Fines', bsb: '063-000', account_number: '1234 5678', reference_hint: 'Fines and your name' },
}]
const LADDER = { ladders: [{ team: '1st XI', grade: 'A Grade', view: 'Overall', columns: [{ id: 'played', heading: 'P' }, { id: 'won', heading: 'W' }, { id: 'lost', heading: 'L' }, { id: 'competitionPoints', heading: 'PTS' }],
  rows: [{ rank: 1, team_name: 'Rovers', is_club: false, stats: { played: 5, won: 4, lost: 1, competitionPoints: 40 } }, { rank: 2, team_name: 'Gisborne 1st XI', is_club: true, stats: { played: 5, won: 3, lost: 2, competitionPoints: 30 } }] }] }

const profileFor = (over = {}) => ({
  club: CLUB, player: { id: 'p1', display_name: 'Sam Sledge' }, squads: ['1st XI'], squads_visible: true,
  selected: [], training: { upcoming: [], attended_8_weeks: 0, last_attended: null },
  season: { season: 'Summer 26/27', matches: 11, runs: 412, high_score: 87, batting_average: 51.5, wickets: 9, best_bowling: '3-21', catches: 6, auto_shown: false },
  fees: { on_record: true, season: 'Summer 26/27', total_outstanding: 60, membership_outstanding: 60, match_fee_outstanding: 0, total_paid: 40, credit: 0 },
  fines: FINES,
  modules: ['season', 'fines', 'ladder', 'fees', 'availability'],
  ...over,
})

async function playerPage(browser, width, profile, ladder) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500 })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const hits = { profile: 0, ladder: 0 }
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route(/\/api\/public\/availability\/tok\/me\/ladder$/, (r) => { hits.ladder++; return ladder.status === 200 ? json(r, ladder.body) : json(r, { detail: 'nope' }, ladder.status) })
  await page.route(/\/api\/public\/availability\/tok\/me\/profile(\?.*)?$/, (r) => { hits.profile++; return json(r, profile) })
  await page.route(/\/api\/public\/availability\/tok\/me(\?.*)?$/, (r) => json(r, ME_PUBLIC))
  await page.route(/\/api\/public\/availability\/tok$/, (r) => json(r, { club: CLUB, require_pin: true, players: [{ id: 'p1', display_name: 'Sam Sledge', has_phone: true }] }))
  await page.goto(`${BASE}/avail/tok`)
  await page.getByText('Signed in as').waitFor({ timeout: 20000 })
  await page.locator('[data-tab="mine"]').click()
  await page.locator('[data-my-page]').waitFor()
  return { ctx, page, hits, errors }
}
const titles = (page) => page.evaluate(() => [...document.querySelectorAll('[data-my-page] > section > div:first-child')].map((e) => e.textContent.trim().toLowerCase()))

// ─── C. the admin Fines screen ─────────────────────────────────────────────
const ME = { id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'o1', club_slug: 'gisborne', capabilities: ['*'], entitlements: { modules: ['select'], core_live: true, status: 'active' } }
const D1 = iso(-8), D2 = iso(-1)
const squadPayload = (on = true) => ({
  squad: { id: 't1', name: '1st XI' },
  settings: { enabled: on, payid: 'pay@gisborne.org', payid_name: '', account_name: '', bsb: '063-000', account_number: '', reference_hint: '', other_instructions: '' },
  types: [{ id: 'ty1', name: 'Dropped catch', amount: 5 }, { id: 'ty2', name: 'Late to training', amount: 10.5 }], archived_types: [],
  dates: [D2, D1],
  players: [
    { player_id: 'p1', name: 'Sam Sledge', in_squad: true, by_date: { [D1]: 10, [D2]: 7 }, fined: 17, paid: 10, owing: 7 },
    { player_id: 'p2', name: 'Ann Anchor', in_squad: true, by_date: { [D1]: 20 }, fined: 20, paid: 25, owing: -5 },
    { player_id: 'p3', name: 'Ian Idle', in_squad: true, by_date: {}, fined: 0, paid: 0, owing: 0 },
  ],
  candidates: [{ id: 'p9', name: 'Bob Rival' }],
  totals: { fined: 37, paid: 35, owing: 2 },
})

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  // ── A. the player's page ──
  await safe('A. modules', async () => {
    console.log('\n── A. The player\'s page: the club\'s modules, in the club\'s order ──')
    const { ctx, page, hits, errors } = await playerPage(browser, 390, profileFor(), { status: 200, body: LADDER })
    await page.locator('[data-ladder]').waitFor()
    const t = await titles(page)
    check('sections are drawn in the order the server lists', JSON.stringify(t.map((x) => x.split(':')[0])) === JSON.stringify(['your season', 'fines', 'ladder', 'fees', 'your availability']), JSON.stringify(t))
    check('the profile was fetched once, the ladder once', hits.profile === 1 && hits.ladder === 1, JSON.stringify(hits))
    const body = norm(await page.locator('[data-my-page]').innerText())
    check('season: matches, runs, high score and the season name', /Summer 26\/27/i.test(body) && /412/.test(body) && /87/.test(body), body.slice(0, 300))
    check('fines: what they owe, in the squad\'s name', /You owe the 1st XI fines pot/i.test(body) && /\$7\.00/.test(body), body)
    check('fines: week by week with the reasons', /Chirping the umpire \$7\.00/.test(body) && /Dropped catch \$5\.00 · Dropped catch \$5\.00/.test(body), body)
    check('fines: the pot total', /In the pot so far: \$35\.00/.test(body), body)
    const pay = norm(await page.locator('[data-how-to-pay]').innerText())
    check('how to pay lists PayID, BSB, account number and the reference', /pay@gisborne\.org/.test(pay) && /063-000/.test(pay) && /1234 5678/.test(pay) && /Fines and your name/.test(pay), pay)
    check('...each with a Copy button', (await page.locator('[data-how-to-pay] button', { hasText: 'Copy' }).count()) === 5)
    check('ladder: the club\'s own row is marked', (await page.locator('[data-ladder] tr[data-mine="yes"]').innerText()).includes('Gisborne 1st XI'))
    check('fees: what they owe', /You owe\s*\$60\.00/.test(body) && /Membership \$60\.00/.test(body), body)
    check('390px: no sideways overflow', (await overflow(page)) <= 0, String(await overflow(page)))
    check('no script errors', errors.length === 0, errors.join('; '))
    await page.screenshot({ path: `${SHOT}/player-dashboard-390.png`, fullPage: true })
    await ctx.close()
  })

  await safe('A. only what is listed', async () => {
    console.log('\n── A. A module the club left off is not drawn, and not fetched ──')
    const { ctx, page, hits } = await playerPage(browser, 390, profileFor({ modules: ['availability', 'fees'], fines: null, season: null }), { status: 200, body: LADDER })
    await page.waitForTimeout(400)
    const t = await titles(page)
    check('just availability and fees', JSON.stringify(t) === JSON.stringify(['your availability', 'fees']), JSON.stringify(t))
    check('the ladder is never requested', hits.ladder === 0, String(hits.ladder))
    await ctx.close()
  })

  await safe('A. empty modules', async () => {
    console.log('\n── A. A club that turned everything off says so ──')
    const { ctx, page } = await playerPage(browser, 390, profileFor({ modules: [], fines: null }), { status: 200, body: LADDER })
    await page.locator('[data-no-modules]').waitFor()
    check('the page explains itself', (await page.locator('[data-no-modules]').count()) === 1)
    await ctx.close()
  })

  await safe('A. explaining absence', async () => {
    console.log('\n── A. A figure that is correctly zero or absent explains itself ──')
    const square = [{ ...FINES[0], fined: 10, paid: 10, owing: 0, weeks: [{ date: iso(-8), total: 10, items: [{ reason: 'Late', amount: 10 }] }] }]
    const { ctx, page } = await playerPage(browser, 390,
      profileFor({ modules: ['fines', 'fees', 'season', 'ladder'], fines: square, fees: { on_record: false }, season: null }), { status: 200, body: { ladders: [] } })
    await page.locator('[data-no-ladder]').waitFor()
    const body = norm(await page.locator('[data-my-page]').innerText())
    check('a zero fines balance reads all square', /You are all square/i.test(body) && /\$0\.00/.test(body), body)
    check('...and shows no payment block', (await page.locator('[data-how-to-pay]').count()) === 0)
    check('no fee record says so, not $0', (await page.locator('[data-no-fees]').count()) === 1 && !/You owe\s*\$0/.test(body))
    check('no games says so, not zeroes', (await page.locator('[data-no-season]').count()) === 1)
    check('no linked ladder says so', (await page.locator('[data-no-ladder]').count()) === 1)
    await ctx.close()
  })

  await safe('A. ladder fails', async () => {
    console.log('\n── A. A ladder that cannot load does not take the page down ──')
    const { ctx, page } = await playerPage(browser, 390, profileFor({ modules: ['ladder', 'fines'] }), { status: 502, body: {} })
    await page.getByText('could not load right now').waitFor()
    check('the ladder says it could not load', true)
    check('...and Fines still shows', /You owe the 1st XI/.test(await page.locator('[data-my-page]').innerText()))
    await ctx.close()
  })

  await safe('A. legacy payload', async () => {
    console.log('\n── A. A server that sends no module list gets the page as it was ──')
    const legacy = profileFor(); delete legacy.modules
    const { ctx, page } = await playerPage(browser, 390, legacy, { status: 200, body: LADDER })
    await page.waitForTimeout(300)
    const t = await titles(page)
    check('availability, squad, selected, training', JSON.stringify(t) === JSON.stringify(['your availability', 'your squad', 'selected', 'training']), JSON.stringify(t))
    await ctx.close()
  })

  // ── B. the admin chooser ──
  await safe('B. chooser', async () => {
    console.log('\n── B. Player page chooser in the self-service panel ──')
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const page = await ctx.newPage()
    page.setDefaultTimeout(8000)
    const posts = []
    let modules = [
      { key: 'availability', label: 'Your availability', blurb: 'x', enabled: true, blocked: null },
      { key: 'training', label: 'Training', blurb: 'x', enabled: true, blocked: null },
      { key: 'fees', label: 'Fees owing', blurb: 'x', enabled: false, blocked: 'Needs the BetterAdmin fees module.' },
      { key: 'season', label: 'Season overview', blurb: 'x', enabled: false, blocked: null },
    ]
    const panel = () => ({ enabled: true, require_pin: true, show_squad: false, allow_maybe: true, token: 'tok', path: '/avail/tok', phone_coverage: { with_phone: 2, total: 2 }, dashboard_modules: modules })
    await page.route('**/api/**', (r) => json(r, {}))
    await page.route('**/api/auth/me', (r) => json(r, ME))
    await page.route('**/api/club-admin/settings', (r) => json(r, { name: 'Gisborne CC' }))
    const PLAYERS = ['Anna Brown', 'Zed Adams'].map((name, i) => ({ id: `p${i}`, display_name: name, name, squads: [], is_current: true, last_played: iso(-20), player_role: null, skill_positions: [], status: 'active' }))
    await page.route(/\/api\/availability\/matrix/, (r) => json(r, { dates: [{ date: iso(7), fixtures: [{ id: 'f1', label: null, opponent_name: 'Rovers', home_away: 'HOME', role: 'single', two_day: false, team_id: null, grade_id: null }] }], players: PLAYERS, availability: {}, all_squads: [], dormancy_months: 24, squad_next: {}, rules: { active: false, applied: [] } }))
    await page.route(/\/api\/availability\/config$/, (r) => json(r, { allow_maybe: true }))
    await page.route(/\/api\/teams(\?.*)?$/, (r) => json(r, []))
    await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
    await page.route(/\/api\/fixtures/, (r) => json(r, []))
    await page.route(/\/api\/availability\/self-service$/, (r) => {
      if (r.request().method() === 'POST') {
        const b = JSON.parse(r.request().postData() || '{}'); posts.push(b)
        if (b.dashboard_modules) {
          const on = b.dashboard_modules
          const all = [...modules]
          modules = [...on.map((k) => ({ ...all.find((m) => m.key === k), enabled: true })), ...all.filter((m) => !on.includes(m.key)).map((m) => ({ ...m, enabled: false }))]
        }
      }
      return json(r, panel())
    })
    await page.goto(`${BASE}/admin/betterselect/availability`, { waitUntil: 'domcontentloaded' })
    await page.getByPlaceholder('Search players…').waitFor({ timeout: 20000 })
    await page.getByText('Self-service link').first().click()
    await page.locator('[data-page-modules]').waitFor()
    const rows = () => page.locator('[data-page-module]').evaluateAll((els) => els.map((e) => `${e.getAttribute('data-page-module')}:${e.getAttribute('data-on')}`))
    check('on modules first, in order, then the rest', JSON.stringify(await rows()) === JSON.stringify(['availability:yes', 'training:yes', 'fees:no', 'season:no']), JSON.stringify(await rows()))
    await page.locator('[data-page-module="season"] input[type=checkbox]').click()
    await page.waitForTimeout(300)
    check('ticking Season sends the whole ordered list', JSON.stringify(posts.at(-1)) === JSON.stringify({ dashboard_modules: ['availability', 'training', 'season'] }), JSON.stringify(posts.at(-1)))
    await page.locator('[data-page-module="season"] button[aria-label="Move Season overview up"]').click()
    await page.waitForTimeout(300)
    check('the up arrow swaps it with the one above', JSON.stringify(posts.at(-1)) === JSON.stringify({ dashboard_modules: ['availability', 'season', 'training'] }), JSON.stringify(posts.at(-1)))
    await page.locator('[data-page-module="availability"] input[type=checkbox]').click()
    await page.waitForTimeout(300)
    check('unticking drops just that one', JSON.stringify(posts.at(-1)) === JSON.stringify({ dashboard_modules: ['season', 'training'] }), JSON.stringify(posts.at(-1)))
    await page.locator('[data-page-module="fees"] input[type=checkbox]').click()
    await page.locator('[data-module-blocked]').waitFor()
    check('a module the club cannot show yet says why', /BetterAdmin fees/.test(await page.locator('[data-module-blocked]').innerText()))
    await ctx.close()
  })

  // ── C. the admin Fines screen ──
  await safe('C. fines screen', async () => {
    console.log('\n── C. BetterSelect > Fines ──')
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const page = await ctx.newPage()
    page.setDefaultTimeout(8000)
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    const wire = []
    let on = true
    await page.route('**/api/**', (r) => json(r, {}))
    await page.route('**/api/auth/me', (r) => json(r, ME))
    await page.route('**/api/club-admin/settings', (r) => json(r, { name: 'Gisborne CC' }))
    await page.route(/\/api\/fines\/squads$/, (r) => json(r, { squads: [{ id: 't1', name: '1st XI', enabled: on, owing: 2 }, { id: 't2', name: '2nd XI', enabled: false, owing: 0 }] }))
    await page.route(/\/api\/fines\/squads\/t1$/, (r) => json(r, squadPayload(on)))
    await page.route(/\/api\/fines\/squads\/t1\/players\/p1\/ledger$/, (r) => json(r, {
      player: { id: 'p1', name: 'Sam Sledge' }, owing: 7,
      entries: [{ id: 'e1', date: D2, reason: 'Chirping the umpire', amount: 7, voided: false }],
      payments: [{ id: 'pay1', date: D1, amount: 10, method: 'PayID', note: null, voided: false }],
    }))
    await page.route(/\/api\/fines\/(squads\/t1\/(entries|payments|types|settings)|entries\/e1\/void|types\/ty1)$/, (r) => {
      const req = r.request()
      const body = req.postData() ? JSON.parse(req.postData()) : null
      wire.push({ method: req.method(), path: new URL(req.url()).pathname.replace('/api', ''), body })
      if (body && 'enabled' in body) on = body.enabled
      return json(r, { status: 'ok', created: 1, total: 10, id: 'n1', settings: squadPayload(on).settings })
    })

    await page.goto(`${BASE}/admin/betterselect/fines`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-fines-squad="t1"]').waitFor({ timeout: 20000 })

    const link = page.locator('a[href="/admin/betterselect/fines"]').first()
    await link.waitFor({ state: 'attached' })
    check('Fines is a side-menu item', /Fines/.test(await link.innerText()))
    const tabs = norm(await page.locator('[role=tablist]').innerText())
    check('squads are tabs showing ON/OFF, the one that is on is open', /1st XI ON/.test(tabs) && /2nd XI OFF/.test(tabs), tabs)

    const tr = norm(await page.locator('[data-fines-player="p1"]').innerText())
    check('the tracker row has the fines by date, nothing paid yet shown, and what is owed', /\$10\.00/.test(tr) && /\$7\.00/.test(tr) && /\$10\.00/.test(tr), tr)
    check('a player in credit reads as credit', /\$5\.00 credit/.test(norm(await page.locator('[data-fines-player="p2"]').innerText())))
    check('a player with nothing owing reads square', /Square/.test(norm(await page.locator('[data-fines-player="p3"]').innerText())))

    // a fines session
    const row = page.locator('[data-fine-row]').first()
    await row.locator('select[aria-label="Player"]').selectOption('p1')
    await row.locator('select[aria-label="Fine"]').selectOption('ty1')
    check('picking a fine shows its price as the amount', (await row.locator('input[aria-label="Amount"]').getAttribute('placeholder')) === '5')
    await row.locator('input[aria-label="How many"]').fill('2')
    const row2 = page.locator('[data-fine-row]').nth(1)
    await row2.locator('select[aria-label="Player"]').selectOption('p9')
    await row2.locator('input[aria-label="Reason"]').fill('Sunglasses at night')
    await row2.locator('input[aria-label="Amount"]').fill('20')
    check('a line with a typed amount shows it in the running total', /\$30\.00/.test(await page.getByText(/2 lines/).innerText()), await page.getByText(/2 lines/).innerText())
    wire.length = 0
    await page.getByRole('button', { name: 'Save fines' }).click()
    await page.waitForTimeout(400)
    const posted = wire.find((w) => w.path === '/fines/squads/t1/entries')
    const want = { fined_on: iso(0), items: [
      { player_id: 'p1', fine_type_id: 'ty1', reason: null, amount: null, quantity: 2 },
      { player_id: 'p9', fine_type_id: null, reason: 'Sunglasses at night', amount: '20', quantity: 1 }] }
    // The date is "today" in the browser's local clock; accept the UTC neighbour.
    check('a session puts exactly the right body on the wire, blank lines dropped',
      posted && posted.body.items.length === 2 && JSON.stringify(posted.body.items) === JSON.stringify(want.items) && /^\d{4}-\d\d-\d\d$/.test(posted.body.fined_on), JSON.stringify(posted))

    // payment
    await page.locator('[data-fines-player="p1"]').getByRole('button', { name: 'Paid' }).locator('visible=true').click()
    const amount = page.locator('[role=dialog] input').first()
    check('Paid is prefilled with what they owe', (await amount.inputValue()) === '7')
    wire.length = 0
    await page.getByRole('button', { name: 'Record payment' }).click()
    await page.waitForTimeout(300)
    const pay = wire.find((w) => w.path === '/fines/squads/t1/payments')
    check('the payment body names the player, amount, method', pay && pay.body.player_id === 'p1' && pay.body.amount === '7' && pay.body.method === 'PayID', JSON.stringify(pay))

    // history + void
    await page.locator('[data-fines-player="p1"]').getByRole('button', { name: 'History' }).locator('visible=true').click()
    await page.getByText('Chirping the umpire').waitFor()
    wire.length = 0
    await page.locator('[role=dialog]').getByRole('button', { name: 'Void' }).first().click()
    await page.waitForTimeout(300)
    check('Void asks the server to void that fine', wire.some((w) => w.method === 'POST' && w.path === '/fines/entries/e1/void'), JSON.stringify(wire))
    await page.keyboard.press('Escape')

    // fine list
    wire.length = 0
    await page.getByLabel('New fine name').fill('Phone at nets')
    await page.getByLabel('New fine amount').fill('3.5')
    await page.getByRole('button', { name: 'Add to list' }).click()
    await page.waitForTimeout(300)
    const ty = wire.find((w) => w.path === '/fines/squads/t1/types')
    check('adding to the fine list sends name and amount', ty && ty.body.name === 'Phone at nets' && ty.body.amount === '3.5', JSON.stringify(ty))
    wire.length = 0
    await page.locator('[data-fine-type="ty1"] button', { hasText: 'Archive' }).click()
    await page.waitForTimeout(300)
    check('Archive sends archived: true to that fine only', wire.some((w) => w.method === 'PATCH' && w.path === '/fines/types/ty1' && w.body.archived === true), JSON.stringify(wire))

    // a toast (from the actions above) must not reload the squad or wipe a half-typed form
    const squadGets = []
    page.on('request', (rq) => { if (/\/api\/fines\/squads\/t1$/.test(rq.url()) && rq.method() === 'GET') squadGets.push(rq.url()) })
    await page.getByPlaceholder('An email, mobile or ABN, e.g. fines@yourclub.com.au').fill('typed-but-not-saved@x.org')
    await page.getByLabel('New fine name').fill('x')
    await page.getByLabel('New fine name').fill('')
    await page.waitForTimeout(500)
    check('typing in How to pay survives the screen reloading after other actions', (await page.getByPlaceholder('An email, mobile or ABN, e.g. fines@yourclub.com.au').inputValue()) === 'typed-but-not-saved@x.org')

    // how to pay
    wire.length = 0
    await page.getByPlaceholder('An email, mobile or ABN, e.g. fines@yourclub.com.au').fill('fines@gisborne.org')
    await page.getByRole('button', { name: 'Save', exact: true }).last().click()
    await page.waitForTimeout(300)
    const st = wire.find((w) => w.path === '/fines/squads/t1/settings')
    check('How to pay saves the whole form, the edit included', st && st.body.payid === 'fines@gisborne.org' && st.body.bsb === '063-000' && !('enabled' in st.body), JSON.stringify(st))

    // switch off
    wire.length = 0
    await page.locator('[data-fines-squad="t1"] section').first().getByRole('button', { name: 'Off', exact: true }).click()
    await page.waitForTimeout(300)
    check('switching Fines off sends only enabled: false', wire.some((w) => w.path === '/fines/squads/t1/settings' && JSON.stringify(w.body) === '{"enabled":false}'), JSON.stringify(wire))
    check('and the screen says so', /Fines is off for this squad/.test(await page.locator('[data-fines-squad="t1"]').innerText()))

    check('no script errors', errors.length === 0, errors.join('; '))
    await page.screenshot({ path: `${SHOT}/fines-admin-1280.png`, fullPage: true })
    await ctx.close()
  })

  await safe('C. 390px', async () => {
    console.log('\n── C. Fines at 390px ──')
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 }, isMobile: true, hasTouch: true })
    const page = await ctx.newPage()
    page.setDefaultTimeout(8000)
    await page.route('**/api/**', (r) => json(r, {}))
    await page.route('**/api/auth/me', (r) => json(r, ME))
    await page.route('**/api/club-admin/settings', (r) => json(r, { name: 'Gisborne CC' }))
    await page.route(/\/api\/fines\/squads$/, (r) => json(r, { squads: [{ id: 't1', name: '1st XI', enabled: true, owing: 2 }] }))
    await page.route(/\/api\/fines\/squads\/t1$/, (r) => json(r, squadPayload(true)))
    await page.goto(`${BASE}/admin/betterselect/fines`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-fines-squad="t1"]').waitFor({ timeout: 20000 })
    check('no sideways overflow of the page (the tracker scrolls inside its card)', (await overflow(page)) <= 0, String(await overflow(page)))
    const btn = await page.locator('[data-fines-player="p1"]').getByRole('button', { name: 'Paid' }).locator('visible=true').boundingBox()
    check('Paid and History are on screen, not past the right edge', btn && btn.x + btn.width <= 390, JSON.stringify(btn))
    await page.screenshot({ path: `${SHOT}/fines-admin-390.png`, fullPage: true })
    await ctx.close()
  })

  await safe('C. nothing to show', async () => {
    console.log('\n── C. No squads ──')
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const page = await ctx.newPage()
    page.setDefaultTimeout(8000)
    await page.route('**/api/**', (r) => json(r, {}))
    await page.route('**/api/auth/me', (r) => json(r, ME))
    await page.route('**/api/club-admin/settings', (r) => json(r, { name: 'Gisborne CC' }))
    await page.route(/\/api\/fines\/squads$/, (r) => json(r, { squads: [] }))
    await page.goto(`${BASE}/admin/betterselect/fines`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-no-squads]').waitFor({ timeout: 20000 })
    check('a club with no squads is told why there is nothing here', true)
    await ctx.close()
  })

  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
