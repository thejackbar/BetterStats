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
const SAT = plusDays(6), SUN = plusDays(7)

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
  ],
  availability: {},
})

const writes = []
async function stub(page, me) {
  await page.route('**/api/public/availability/**', async (route) => {
    const req = route.request(), url = req.url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.endsWith('/me') && req.method() === 'POST') { writes.push(JSON.parse(req.postData() || '{}')); return json({ status: 'ok' }) }
    if (url.endsWith('/me')) return json(me)
    return json({ club: me.club, require_pin: true, players: [{ id: 'p1', display_name: 'Barendse, Jack', has_phone: true }] })
  })
  await page.route('**/api/**', (route) => (route.request().url().includes('/public/availability/') ? route.fallback() : route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })))
}

// Each date card -> its game rows as the player sees them.
const readCards = (page) => page.evaluate(() => [...document.querySelectorAll('div.rounded-xl.border')]
  .filter((c) => c.querySelector('[data-fixture]') || /Available/.test(c.textContent))
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
  await stub(page, me)
  await page.goto(`${BASE}/avail/tok123`)
  await page.waitForSelector('text=Signed in as', { timeout: 20000 })
  await page.waitForTimeout(300)
  return { ctx, page }
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  // ── a player in a squad ─────────────────────────────────────────────────
  let { ctx, page } = await open(browser, payload(true))
  let cards = await readCards(page)
  const satCard = cards[0], sunCard = cards[1]
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

  const w = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, screen: window.screen.width }))
  check('390px: no sideways overflow', w.sw <= Math.max(w.screen, 390), JSON.stringify(w))
  if (SHOT) await page.screenshot({ path: `${SHOT}/public-availability-390.png`, fullPage: true })
  await ctx.close()

  // ── a player in no squad: nothing emphasised, nothing hidden ───────────
  ;({ ctx, page } = await open(browser, payload(false)))
  cards = await readCards(page)
  check('no squad: every Saturday game is shown', rowsOf(cards[0]).length === 5 && cards[0]?.toggle === null, JSON.stringify(cards[0]?.toggle))
  const text = (await page.locator('body').innerText()).toLowerCase()
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
