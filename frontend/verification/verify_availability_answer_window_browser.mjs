// Drives the real player page (/playerdash/:token) and the BetterSelect
// Availability screen's self-service panel in Chromium, with the API stubbed at
// the network layer.
//
// Asked for (Nov 2026): a club can let players say Available only N weeks ahead
// and Unavailable M weeks ahead. Checks: a date inside both windows offers every
// answer; a date past the Available window greys Available and Maybe, keeps
// Unavailable, and says when they open; a date past both greys everything and
// says so; a greyed tap writes nothing; an allowed tap writes the date with the
// browser's tz; a two-day game's quick answers grey only the patterns that break
// a window; with no window every answer is offered (the control that the greying
// could be absent). The admin panel offers both settings, sends only its own
// key, sends null for "No limit", and 390px does not overflow.
//
//   APP_URL=http://localhost:4173 node verify_availability_answer_window_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return iso(d) }
const D7 = plusDays(7), D21 = plusDays(21), D35 = plusDays(35), D70 = plusDays(70)

let n = 0
const G = (extra = {}) => ({ id: 'f' + (++n), opponent_name: 'Opp ' + n, home_away: 'HOME', role: 'single', two_day: false,
  start_time: '13:00', venue: 'Oval', team_name: '1st XI', mine: false, ...extra })
const TD = { two_day: true, day1: D21, day2: D35 }

const payload = (win) => ({
  club: { name: 'Verify CC' }, player: { id: 'p1', display_name: 'Ann' }, has_squad: false, squads: [],
  has_availability: true, allow_maybe: true, week_names: {},
  dates: [
    { date: D7, fixtures: [G()] },
    { date: D21, fixtures: [G({ id: 'td', ...TD, role: 'day1' })] },
    { date: D35, fixtures: [G({ id: 'td', ...TD, role: 'day2' }), G()] },
    { date: D70, fixtures: [G()] },
  ],
  availability: {},
  ...(win ? { answer_window: win } : {}),
})
const WIN = { available_weeks: 4, available_until: plusDays(28), unavailable_weeks: 8, unavailable_until: plusDays(56) }

async function openPlayer(browser, me, width = 390) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500, timezoneId: 'Australia/Perth' })
  await ctx.addInitScript(() => { try { localStorage.setItem('bs.playerpage.open', JSON.stringify({ availability: true })) } catch (e) { /* none */ } })
  const page = await ctx.newPage()
  const state = { writes: [] }
  await page.route('**/api/**', async (route) => {
    const req = route.request(), url = req.url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (!url.includes('/public/availability/')) return json({})
    if (/\/me(\?|$)/.test(url) && req.method() === 'POST') { state.writes.push({ url, body: JSON.parse(req.postData() || '{}') }); return json({ status: 'ok' }) }
    if (/\/me(\?|$)/.test(url)) return json(me)
    if (url.includes('/me/')) return json({})
    return json({ club: me.club, require_pin: false, players: [{ id: 'p1', display_name: 'Ann', has_phone: true }] })
  })
  await page.goto(`${BASE}/playerdash/tok123`)
  await page.waitForSelector('[data-availability]', { timeout: 20000 })
  const more = page.locator('[data-see-more]')
  while (await more.count()) { await more.click(); await page.waitForTimeout(80) }
  return { ctx, page, state }
}

const card = (page, d) => page.locator(`[data-date-card="${d}"]`)
const heldOf = (page, d) => card(page, d).evaluate((c) => Object.fromEntries([...c.querySelectorAll('[data-answer]')].map((b) => [b.dataset.answer, b.disabled])))

async function adminPanel(browser, initial, width = 1280) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500 })
  const page = await ctx.newPage()
  const state = { cfg: initial, posts: [] }
  await page.route('**/api/**', async (route) => {
    const req = route.request(), url = req.url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json({ id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1', club_slug: 'verify-cc', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' } })
    if (url.includes('/availability/matrix')) return json({ dates: [{ date: D7, fixtures: [{ id: 'f1', opponent_name: 'Willetton', home_away: 'HOME', role: 'single', two_day: false }] }], players: [], availability: {}, all_squads: [], dormancy_months: 24, rules: { active: false, applied: [] }, squad_next: {} })
    if (/\/availability\/self-service$/.test(url) && req.method() === 'POST') {
      const body = JSON.parse(req.postData() || '{}'); state.posts.push(body); state.cfg = { ...state.cfg, ...body }; return json(state.cfg)
    }
    if (/\/availability\/self-service$/.test(url)) return json(state.cfg)
    return json({})
  })
  await page.goto(`${BASE}/admin/betterselect/availability`)
  await page.getByText('Self-service link').first().waitFor({ timeout: 20000 })
  await page.getByText('Self-service link').first().click()
  await page.waitForTimeout(300)
  return { ctx, page, state }
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })

  console.log('# Player page, windows 4 and 8 weeks')
  let { ctx, page, state } = await openPlayer(browser, payload(WIN))
  const h7 = await heldOf(page, D7)
  check('1 week out: every answer offered', !h7.AVAILABLE && !h7.MAYBE && !h7.UNAVAILABLE, JSON.stringify(h7))
  check('1 week out: no window note', (await card(page, D7).locator('[data-window-note]').count()) === 0)
  const h35 = await heldOf(page, D35)
  check('5 weeks out: Available and Maybe greyed', h35.AVAILABLE === true && h35.MAYBE === true, JSON.stringify(h35))
  check('5 weeks out: Unavailable still offered', h35.UNAVAILABLE === false, JSON.stringify(h35))
  const note35 = (await card(page, D35).locator('[data-window-note]').innerText().catch(() => '')) || ''
  check('5 weeks out: the note says when Available opens', /Available and Maybe open /.test(note35) && /4 weeks ahead/.test(note35), note35)
  const h70 = await heldOf(page, D70)
  check('10 weeks out: every answer greyed', h70.AVAILABLE && h70.MAYBE && h70.UNAVAILABLE, JSON.stringify(h70))
  const note70 = (await card(page, D70).locator('[data-window-note]').innerText().catch(() => '')) || ''
  check('10 weeks out: the note says answers open later', /Answers for this day open/.test(note70), note70)

  await card(page, D35).locator('[data-answer="AVAILABLE"]').click({ force: true, timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(300)
  check('a greyed tap writes nothing', state.writes.length === 0, JSON.stringify(state.writes))
  await card(page, D35).locator('[data-answer="UNAVAILABLE"]').click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(400)
  const w = state.writes[0]
  check('an allowed tap writes that date as Unavailable', w && w.body.date === D35 && w.body.status === 'UNAVAILABLE', JSON.stringify(state.writes))
  check('...with the browser timezone in the body', w?.body?.tz === 'Australia/Perth', JSON.stringify(w?.body))

  const both = await page.locator('[data-both-weeks] [data-week-pattern]').evaluateAll((bs) => Object.fromEntries(bs.map((b) => [b.dataset.weekPattern, b.disabled])))
  check('two-day game: Both weeks greyed (week 2 is past the Available window)', both.both === true, JSON.stringify(both))
  check('two-day game: week 1 only offered', both.w1 === false, JSON.stringify(both))
  check('two-day game: week 2 only greyed', both.w2 === true, JSON.stringify(both))
  check('two-day game: Not available offered', both.none === false, JSON.stringify(both))
  check('two-day game: Maybe for both is not offered', (await page.locator('[data-both="MAYBE"]').count()) === 0)
  const ov = await page.evaluate(() => document.documentElement.scrollWidth)
  check('390px: no sideways overflow', ov <= 390, String(ov))
  if (SHOT) await card(page, D35).screenshot({ path: `${SHOT}/answer-window-card-390.png` })
  await ctx.close()

  console.log('\n# Player page, no window (control: the greying can be absent)')
  ;({ ctx, page, state } = await openPlayer(browser, payload(null)))
  const all = await page.locator('[data-answer]').evaluateAll((bs) => bs.filter((b) => b.disabled).length)
  check('no window: nothing is greyed', all === 0, String(all))
  check('no window: no notes', (await page.locator('[data-window-note]').count()) === 0)
  check('no window: Maybe for both offered', (await page.locator('[data-both="MAYBE"]').count()) === 1)
  await ctx.close()

  console.log('\n# Admin panel')
  const base = { enabled: true, require_pin: true, show_squad: false, allow_maybe: true, token: 'tok123', path: '/playerdash/tok123', phone_coverage: { with_phone: 1, total: 1 }, weeks_available: null, weeks_unavailable: null, dashboard_modules: [] }
  ;({ ctx, page, state } = await adminPanel(browser, base))
  const av = page.locator('[data-weeks-setting="available"] select')
  const un = page.locator('[data-weeks-setting="unavailable"] select')
  check('both settings are on the panel', (await av.count()) === 1 && (await un.count()) === 1)
  check('both read No limit when unset', (await av.inputValue()) === '' && (await un.inputValue()) === '')
  check('no limit: the help line explains what a limit does', /Set a limit/.test(await page.locator('[data-answer-window-note]').innerText()))
  await av.selectOption('4'); await page.waitForTimeout(300)
  check('choosing 4 sends exactly {weeks_available: 4}', JSON.stringify(state.posts.at(-1)) === '{"weeks_available":4}', JSON.stringify(state.posts))
  await un.selectOption('8'); await page.waitForTimeout(300)
  check('choosing 8 sends exactly {weeks_unavailable: 8}', JSON.stringify(state.posts.at(-1)) === '{"weeks_unavailable":8}', JSON.stringify(state.posts))
  check('with a limit, the help line says buttons are greyed', /greyed/.test(await page.locator('[data-answer-window-note]').innerText()))
  await av.selectOption(''); await page.waitForTimeout(300)
  check('No limit sends null', JSON.stringify(state.posts.at(-1)) === '{"weeks_available":null}', JSON.stringify(state.posts.at(-1)))
  await ctx.close()

  ;({ ctx, page, state } = await adminPanel(browser, { ...base, weeks_available: 9 }, 390))
  check('a stored value off the list still shows', (await page.locator('[data-weeks-setting="available"] select').inputValue()) === '9')
  const aw = await page.evaluate(() => document.documentElement.scrollWidth)
  check('admin 390px: no sideways overflow', aw <= 390, String(aw))
  if (SHOT) await page.locator('[data-answer-window]').screenshot({ path: `${SHOT}/answer-window-admin-390.png` })
  await ctx.close()

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(2) })
