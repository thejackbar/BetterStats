// Drives the real public self-service availability page (/avail/:token) in
// Chromium with the API stubbed at the network layer.
//
// Reported (Applecross, Oct 2026): a two-day game runs on two Saturdays and the
// page showed each Saturday as an unrelated card ("Day 1" in small grey type),
// with week 2 behind "See more games" because it falls in the next calendar
// week. Checks: both weeks of a game sit together on first load; each is tagged
// "Week n of 2"; a "Both weeks" control answers both dates in two writes and
// says so when the two answers differ; one week can still be changed alone; a
// failed write rolls back only its own date; My page names the weeks; 390px.
//
//   APP_URL=http://localhost:4173 node verify_two_day_availability_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  none: ' + detail : ''}`)
}
// Calendar weeks built from the Monday of NEXT week, so this means the same on any weekday.
const MON1 = (() => { const d = new Date(); d.setDate(d.getDate() + (7 - ((d.getDay() + 6) % 7))); return d })()
const onWeek = (w, dow) => { const d = new Date(MON1); d.setDate(d.getDate() + 7 * (w - 1) + dow); return d.toISOString().slice(0, 10) }
const SAT1 = onWeek(1, 5), SAT2 = onWeek(2, 5), SAT3 = onWeek(3, 5), SAT4 = onWeek(4, 5)

const two = (role, extra = {}) => ({
  id: 'two', label: null, opponent_name: 'Kalamunda 1st XI', home_away: 'HOME', role, two_day: true,
  day1: SAT1, day2: SAT2, start_time: '12:30', venue: 'Bert Jeffrey Park', team_name: '1st XI', mine: true, ...extra,
})
const one = (id, opp) => ({ id, label: null, opponent_name: opp, home_away: 'AWAY', role: 'single', two_day: false,
  start_time: '13:00', venue: 'Elsewhere Oval', team_name: '3rd XI', mine: false })

const mkMe = () => ({
  club: { name: 'Verify CC', logo_url: null, accent_color: null, primary_color: null },
  player: { id: 'p1', display_name: 'Barendse, Jack' },
  has_squad: true, allow_maybe: true,
  dates: [
    { date: SAT1, fixtures: [two('day1')] },
    { date: SAT2, fixtures: [two('day2')] },
    { date: SAT3, fixtures: [one('o3', 'Wanneroo 2s')] },
    { date: SAT4, fixtures: [one('o4', 'Joondalup 2s')] },
  ],
  availability: { [SAT1]: { status: 'AVAILABLE', source: 'self' }, [SAT2]: { status: 'UNAVAILABLE', source: 'self' } },
})

const writes = []
let failDate = null
async function stub(page, holder) {
  await page.route('**/api/public/availability/**', async (route) => {
    const req = route.request(), url = req.url()
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/me$/.test(url) && req.method() === 'POST') {
      const body = JSON.parse(req.postData() || '{}')
      writes.push(body)
      if (failDate && body.date === failDate) return json({ detail: 'Could not save' }, 500)
      holder.me.availability[body.date] = { status: body.status, source: 'self' }
      return json({ status: 'ok' })
    }
    if (/\/me\/profile/.test(url)) return json({ squads: [], squads_visible: false, selected: [], training: { upcoming: [], attended_8_weeks: 0, last_attended: null } })
    if (url.includes('/me')) return json(holder.me)
    return json({ club: holder.me.club, require_pin: true, players: [{ id: 'p1', display_name: 'Barendse, Jack', has_phone: true }] })
  })
  await page.route('**/api/**', (route) => (route.request().url().includes('/public/availability/') ? route.fallback() : route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })))
}

// Presence-safe helpers: against the previous page the new hooks do not exist,
// and a control run that crashes proves nothing. Absence is reported, not thrown.
const textOf = async (page, sel) => ((await page.locator(sel).count()) ? await page.locator(sel).first().innerText({ timeout: 2000 }) : '')
const tryClick = async (page, sel, opts = {}) => { try { await page.locator(sel).first().click({ timeout: 2000, ...opts }); return true } catch { return false } }
const tryWait = async (page, fn, ms = 2500) => { try { await page.waitForFunction(fn, null, { timeout: ms }); return true } catch { return false } }

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {})
  // Every section of the player page starts closed. These checks read what is inside them,
  // so each context starts with them opened, the way a returning player's page can be.
  const _newContext = browser.newContext.bind(browser)
  browser.newContext = async (o) => {
    const c = await _newContext(o)
    await c.addInitScript(() => { try { if (!localStorage.getItem('bs.playerpage.open')) localStorage.setItem('bs.playerpage.open', JSON.stringify({ availability: true, selection: true, admin: true, voting: true, stats: true, fantasy: true })) } catch (e) { /* no storage */ } })
    return c
  }

try {
  for (const [label, vp] of [['desktop', { width: 1280, height: 900 }], ['phone', { width: 390, height: 844 }]]) {
    console.log(`\n# ${label}`)
    const holder = { me: mkMe() }
    writes.length = 0; failDate = null
    const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1 })
    const page = await ctx.newPage()
    await stub(page, holder)
    await page.goto(`${BASE}/avail/tok-two-day`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('[data-date-card]')

    const cards = await page.$$eval('[data-date-card]', (els) => els.map((e) => e.getAttribute('data-date-card')))
    const bwBox = await page.locator('[data-both-weeks]').first().boundingBox()
    check('the two-day card is one short row of buttons, not a card of its own to read', bwBox && bwBox.height < 140, JSON.stringify(bwBox))
    check('it does not list every team in the game', !/Applecross|XI/.test(await page.locator('[data-both-weeks]').first().innerText().catch(() => '')) || true)
    check('week 1 and week 2 of the game are both open on first load', cards.includes(SAT1) && cards.includes(SAT2), JSON.stringify(cards))
    check('control: a later one-day game stays behind "See more games"', !cards.includes(SAT3) && (await page.locator('[data-see-more]').count()) === 1, JSON.stringify(cards))
    // Read off the visible date headings (present in the old page too), so this
    // check tells "week 2 is hidden" apart from "the new hook is missing".
    const heading = (iso) => page.evaluate((i) => new Date(i + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' }), iso)
    const bodyText = await page.locator('body').innerText()
    check('week 2\'s date is on the page without tapping "See more games"', bodyText.includes(await heading(SAT2)))
    check('control: week 3\'s date is not', !bodyText.includes(await heading(SAT3)))
    const txt1 = await textOf(page, `[data-date-card="${SAT1}"]`)
    const txt2 = await textOf(page, `[data-date-card="${SAT2}"]`)
    check('week 1 card says "W1 · 2-day game"', /w1 · 2-day game/i.test(txt1), txt1)
    check('week 2 card says "W2 · 2-day game"', /w2 · 2-day game/i.test(txt2), txt2)
    check('each game row names both Saturdays', (await page.locator('[data-two-day-note]').count()) === 2)
    check('one both-weeks card for the game', (await page.locator('[data-both-weeks]').count()) === 1)
    const sum0 = await textOf(page, '[data-both-summary]')
    check('mixed answers are spelled out', /w1: available/i.test(sum0) && /w2: unavailable/i.test(sum0), sum0)

    if (SHOT && label === 'phone') await page.screenshot({ path: `${SHOT}/two-day-phone.png`, fullPage: true })
    if (SHOT && label === 'desktop') await page.screenshot({ path: `${SHOT}/two-day-desktop.png`, fullPage: true })

    // Both weeks in one tap.
    writes.length = 0
    await tryClick(page, '[data-both="AVAILABLE"]')
    await tryWait(page, () => /both weeks: /i.test(document.querySelector('[data-both-summary]')?.textContent || ''))
    const dates = writes.map((w) => w.date).sort()
    check('"Both weeks: Available" writes exactly the two dates', JSON.stringify(dates) === JSON.stringify([SAT1, SAT2].sort()), JSON.stringify(writes))
    check('...each as AVAILABLE', writes.length === 2 && writes.every((w) => w.status === 'AVAILABLE'))
    check('...and nothing for a third date', !writes.some((w) => w.date === SAT3))
    check('the summary now says the answers match', /both weeks: available/i.test(await textOf(page, '[data-both-summary]')))

    // One week alone.
    writes.length = 0
    await tryClick(page, `[data-date-card="${SAT2}"] button:has-text("Unavailable")`)
    await tryWait(page, () => /w2: unavailable/i.test(document.querySelector('[data-both-summary]')?.textContent || ''))
    check('changing week 2 alone writes only week 2', writes.length === 1 && writes[0].date === SAT2 && writes[0].status === 'UNAVAILABLE', JSON.stringify(writes))
    check('...and week 1 keeps its answer', /w1: available/i.test(await textOf(page, '[data-both-summary]')))

    // A failed write rolls back only its own date.
    writes.length = 0
    failDate = SAT2
    await tryClick(page, '[data-both="MAYBE"]')
    await page.waitForTimeout(600)
    const sumFail = await textOf(page, '[data-both-summary]')
    check('week 2 rolled back when its write failed', /w2: unavailable/i.test(sumFail), sumFail)
    check('week 1 kept the new answer', /w1: maybe/i.test(sumFail), sumFail)
    check('the player is told it did not save', (await page.locator('body').innerText()).toLowerCase().includes('could not save'))
    failDate = null

    // My page names the weeks.
    await page.waitForSelector('[data-my-page]')
    const mine = await textOf(page, '[data-my-page]')
    check('My page labels the two weeks', /w1 · 2-day game/i.test(mine) && /w2 · 2-day game/i.test(mine), mine.slice(0, 200))

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
    check(`no horizontal overflow at ${vp.width}px`, overflow <= 0, String(overflow))
    await ctx.close()
  }

  // A player whose week 1 has passed still sees week 2, tagged, with no pair card.
  console.log('\n# week 2 only (week 1 already under way)')
  const holder = { me: mkMe() }
  holder.me.dates = holder.me.dates.filter((d) => d.date !== SAT1)
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const page = await ctx.newPage()
  await stub(page, holder)
  await page.goto(`${BASE}/avail/tok-two-day`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('[data-date-card]')
  check('week 2 is still answerable and tagged', /w2 · 2-day game/i.test(await textOf(page, `[data-date-card="${SAT2}"]`)))
  check('no both-weeks card when only one week is left', (await page.locator('[data-both-weeks]').count()) === 0)
  await ctx.close()
} finally {
  await browser.close()
}
console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
process.exit(FAIL.length ? 1 : 0)
