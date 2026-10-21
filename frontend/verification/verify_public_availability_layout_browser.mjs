// Drives the real public self-service availability page (/avail/:token) in
// Chromium with the API stubbed at the network layer.
//
// Feedback (Oct 2026): "finding it really difficult to know which game is on
// which day ... lay it out so it is easy to know which team is playing where,
// home or away, times etc, and maybe your squad in bold". The page used to
// print one grey line of opponents per date. Checks: each game is its own row
// with time, our team, home or away, opponent and venue; the player's own game
// is first, bold and tagged; other grades' games wait behind a tap when the
// player has a game that day and stay open when they do not; a player in no
// squad gets no emphasis at all; the tap still writes the date; 390px.
//
//   APP_URL=http://localhost:4173 node verify_public_availability_layout_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}
const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
// Calendar weeks, not "today plus n": the page groups Monday to Sunday, so the
// dates are built from the Monday of NEXT week and the test means the same on
// any weekday. Week 1 is Sat + Sun, week 2 Tue + Sat, week 3 Sat.
const MON1 = (() => { const d = new Date(); d.setDate(d.getDate() + (7 - ((d.getDay() + 6) % 7))); return d })()
const onWeek = (w, dow) => { const d = new Date(MON1); d.setDate(d.getDate() + 7 * (w - 1) + dow); return d.toISOString().slice(0, 10) }
const SAT = onWeek(1, 5), SUN = onWeek(1, 6)
const TUE2 = onWeek(2, 1), SAT2 = onWeek(2, 5), SAT3 = onWeek(3, 5)

let n = 0
const G = (opp, ha, time, team, mine, venue, extra) => ({
  id: 'f' + (++n), label: null, opponent_name: opp, home_away: ha, role: 'single', two_day: false,
  start_time: time, venue, team_name: team, mine, ...extra,
})
const sat = [
  G('Swan Valley 1st XI', 'AWAY', '11:00', '1st XI', false, 'Swan Valley Oval'),
  G('SMCC 3rd XI', 'AWAY', '13:00', '4th XI', false, 'SMCC Reserve'),
  G('Willetton 3s', 'HOME', '13:00', '3rd XI', true, 'Hillcrest Oval'),
  G('NBCCC OD3', 'HOME', '09:30', '2nd XI', false, 'Hillcrest Oval'),
  G('Bassendean 7th XI', 'AWAY', null, '7th XI', false, null),
]
const sun = [G('Cockburn Blue', 'HOME', '14:15', 'Women 2nd XI', false, 'Hillcrest Oval'), G('Swanbourne T20', 'AWAY', '13:00', 'T20 Div 3', false, 'Swanbourne')]

const payload = (hasSquad, mineOn = true) => ({
  club: { name: 'Verify CC', logo_url: null, accent_color: null, primary_color: null },
  player: { id: 'p1', display_name: 'Barendse, Jack' },
  has_squad: hasSquad,
  dates: [
    { date: SAT, fixtures: sat.map((f) => ({ ...f, mine: hasSquad && mineOn ? f.mine : false })) },
    { date: SUN, fixtures: sun },
    { date: TUE2, fixtures: [G('Jarrah T20', 'HOME', '18:30', 'T20 Div 3', false, 'Hillcrest Oval')] },
    { date: SAT2, fixtures: [G('Kenwick 3s', 'AWAY', '12:30', '3rd XI', hasSquad && mineOn, 'Kenwick Park')] },
    { date: SAT3, fixtures: [G('Bayswater 3s', 'HOME', '13:00', '3rd XI', hasSquad && mineOn, 'Hillcrest Oval')] },
  ],
  availability: {},
})

const writes = []
async function stub(page, holder) {
  const me = holder.me
  await page.route('**/api/public/availability/**', async (route) => {
    const req = route.request(), url = req.url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/me$/.test(url) && req.method() === 'POST') { writes.push(JSON.parse(req.postData() || '{}')); return json({ status: 'ok' }) }
    if (url.includes('/me')) { holder.urls.push(url); return json(holder.me) }
    return json({ club: holder.me.club, require_pin: true, players: [{ id: 'p1', display_name: 'Barendse, Jack', has_phone: true }] })
  })
  await page.route('**/api/**', (route) => (route.request().url().includes('/public/availability/') ? route.fallback() : route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })))
}

// Each date card -> its game rows as the player sees them.
const readCards = (page) => page.evaluate(() => [...document.querySelectorAll('div.rounded-xl.border')]
  .filter((c) => !c.hasAttribute('data-tile') && (c.querySelector('[data-fixture]') || /Available/.test(c.textContent)))
  .map((c) => ({
    heading: c.querySelector('.font-display')?.textContent.trim(),
    rows: [...c.querySelectorAll('[data-fixture]')].map((r) => {
      const team = r.querySelector('.font-display, .font-medium')
      return {
        mine: r.getAttribute('data-mine'),
        text: r.textContent.replace(/\s+/g, ' ').trim(),
        teamWeight: team ? Number(getComputedStyle(team).fontWeight) : 0,
      }
    }),
    toggle: [...c.querySelectorAll('button')].map((b) => b.textContent.trim()).find((t) => /other club game/.test(t)) || null,
  })))

const rowsOf = (c) => c?.rows ?? []

const open = async (browser, me, width = 390) => {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500 })
  const page = await ctx.newPage()
  const holder = { me, urls: [] }
  await stub(page, holder)
  await page.goto(`${BASE}/avail/tok123`)
  await page.waitForSelector('[data-hero]', { timeout: 20000 })
  await page.waitForTimeout(300)
  return { ctx, page, holder }
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  // ── a player in a squad ─────────────────────────────────────────────────
  let { ctx, page, holder } = await open(browser, payload(true))
  let cards = await readCards(page)
  const satCard = cards[0], sunCard = cards[1]
  check('opens on the next games only: two date cards, not five', cards.length === 2, `${cards.length}: ${cards.map((c) => c.heading).join(' | ')}`)
  const more = page.locator('[data-see-more]')
  check('a See more button is offered', (await more.count()) === 1)
  check('it says how many more days have games', /3 more days with games/.test((await more.innerText().catch(() => '')) || ''), await more.innerText().catch(() => ''))
  check('the second week is not on the page yet', !(await page.locator('body').innerText()).includes('Kenwick 3s'))
  check('Saturday opens with only the player\'s own game', satCard?.rows.length === 1, JSON.stringify(satCard?.rows.map((r) => r.text)))
  const mine = satCard?.rows[0]
  check('own game shows the time as 1:00pm', /1:00pm/.test(mine?.text || ''), mine?.text)
  check('own game names our team, 3rd XI', /3rd XI/.test(mine?.text || ''), mine?.text)
  check('own game says Home and who against', /Home/i.test(mine?.text || '') && /vs Willetton 3s/.test(mine?.text || ''), mine?.text)
  check('own game shows the venue', /Hillcrest Oval/.test(mine?.text || ''), mine?.text)
  check('own game is tagged Your squad', /your squad/i.test(mine?.text || ''), mine?.text)
  check('own game\'s team name is bold', (mine?.teamWeight || 0) >= 700, String(mine?.teamWeight))
  check('the toggle offers the other four club games', satCard?.toggle === 'Show 4 other club games', String(satCard?.toggle))

  // Presence-safe: against the previous page there is no toggle, and that must report, not hang.
  await page.getByRole('button', { name: 'Show 4 other club games' }).click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(150)
  cards = await readCards(page)
  const all = rowsOf(cards[0])
  check('after the tap all five games show', all.length === 5, String(all.length))
  check('own game is still first', all[0]?.mine === 'yes')
  const others = all.slice(1)
  check('other games are not bold', others.length === 4 && others.every((r) => r.teamWeight < 700 && r.mine === 'no'), JSON.stringify(others.map((r) => r.teamWeight)))
  const order = others.map((r) => (/(\d{1,2}:\d{2}(am|pm))/.exec(r.text) || [])[1] || 'TBC')
  check('the rest run in time order, untimed last', JSON.stringify(order) === JSON.stringify(['9:30am', '11:00am', '1:00pm', 'TBC']), JSON.stringify(order))
  check('an away game says Away and at', others.some((r) => /Away/i.test(r.text) && /at Swan Valley 1st XI/.test(r.text)))
  check('an untimed game says TBC, not blank', others.some((r) => /TBC/.test(r.text) && /Bassendean 7th XI/.test(r.text)))
  check('toggle now offers to hide them', (await readCards(page))[0]?.toggle === 'Hide other club games')

  check('a date with none of the player\'s games keeps every game open, no toggle',
    rowsOf(sunCard).length === 2 && sunCard?.toggle === null && rowsOf(sunCard).every((r) => r.mine === 'no'), JSON.stringify(sunCard))

  // the answer still goes to the date, one tap
  await page.locator('div.rounded-xl.border', { hasText: 'Willetton 3s' }).getByRole('button', { name: /Available/ }).first().click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(300)
  check('exact request: POST /me with the Saturday date', writes.length === 1 && writes[0].date === SAT && writes[0].status === 'AVAILABLE', JSON.stringify(writes))

  // See more: one more week per tap; then it goes away; Show fewer returns to the first week.
  await more.click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(150)
  cards = await readCards(page)
  check('first tap adds the second week (two more dates)', cards.length === 4, String(cards.length))
  check('the second week\'s games are on the page', (await page.locator('body').innerText()).includes('Kenwick 3s'))
  check('the third week is still held back', !(await page.locator('body').innerText()).includes('Bayswater 3s'))
  check('the button now counts one more day', /1 more day with games/.test((await more.innerText().catch(() => '')) || ''), await more.innerText().catch(() => ''))
  await more.click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(150)
  cards = await readCards(page)
  check('second tap shows every date', cards.length === 5, String(cards.length))
  check('See more is gone when nothing is left', (await page.locator('[data-see-more]').count()) === 0)
  // answering a later week writes that week's date
  await page.locator('div.rounded-xl.border', { hasText: 'Bayswater 3s' }).getByRole('button', { name: /Maybe/ }).first().click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(250)
  check('answering a later week writes that date', writes.length === 2 && writes[1].date === SAT3 && writes[1].status === 'MAYBE', JSON.stringify(writes))
  await page.getByRole('button', { name: 'Show only the next games' }).click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(150)
  check('Show only the next games returns to the first week', (await readCards(page)).length === 2 && (await page.locator('[data-see-more]').count()) === 1)

  // The browser's timezone rides on the read, so the server can tell which games have started.
  const tzSent = holder.urls.some((u) => /[?&]tz=[A-Za-z_%0-9+-]+/.test(u))
  check('the /me read carries the browser timezone', tzSent, holder.urls.join(' '))

  // A page left open: once week one's games have started the server stops listing
  // them; coming back to the tab re-reads, and the page moves to the next week.
  const before = holder.urls.length
  holder.me = { ...holder.me, dates: holder.me.dates.filter((d) => d.date !== SAT && d.date !== SUN) }
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
  await page.waitForTimeout(400)
  cards = await readCards(page)
  check('returning to the tab re-reads the games', holder.urls.length === before + 1, String(holder.urls.length - before))
  check('games that have started are gone and the next week is first', cards.length === 2 && /Tuesday/.test(cards[0]?.heading || ''), cards.map((c) => c.heading).join(' | '))
  check('the started games are no longer on the page', !(await page.locator('body').innerText()).includes('Willetton 3s'))
  check('See more now counts what is left', /1 more day with games/.test((await page.locator('[data-see-more]').innerText().catch(() => '')) || ''))

  const w = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, screen: window.screen.width }))
  check('390px: no sideways overflow', w.sw <= Math.max(w.screen, 390), JSON.stringify(w))
  if (SHOT) await page.screenshot({ path: `${SHOT}/public-availability-390.png`, fullPage: true })
  await ctx.close()

  // ── a player in no squad: nothing emphasised, nothing hidden ───────────
  ;({ ctx, page } = await open(browser, payload(false)))
  cards = await readCards(page)
  check('no squad: every Saturday game is shown', rowsOf(cards[0]).length === 5 && cards[0]?.toggle === null, JSON.stringify(cards[0]?.toggle))
  // The games to answer, not the whole dashboard (its Your squad card explains itself).
  const text = (await page.locator('[data-availability]').innerText()).toLowerCase()
  check('no squad: no "your squad" tag anywhere', !text.includes('your squad'))
  check('no squad: no bold team names', rowsOf(cards[0]).length === 5 && rowsOf(cards[0]).every((r) => r.teamWeight < 700))
  await ctx.close()

  // ── a squad player with no game that day: all open ─────────────────────
  ;({ ctx, page } = await open(browser, payload(true, false)))
  cards = await readCards(page)
  check('squad player with no game on the date sees the whole day open', rowsOf(cards[0]).length === 5 && cards[0]?.toggle === null)
  await ctx.close()

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(2) })
