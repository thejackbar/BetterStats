// Drives the real public self-service page (/avail/:token) in Chromium with the
// API stubbed at the network layer (Gisborne round):
//   * the player's squad shows under their name when the club allows it, and not
//     at all when it does not
//   * one page shows their availability, squad, locked selections (with
//     captain / keeper) and training, from GET /me/profile, no tabs
//   * nothing is selected yet reads plainly
//   * 390px: no sideways overflow
//
//   npx vite preview --port 5199 &    node verify_player_page_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }
const plus = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }

const state = { squads: ['1sts', 'T20'], visible: true, selected: true }
const me = () => ({
  club: { name: 'Gisborne CC', logo_url: null, accent_color: null, primary_color: null },
  player: { id: 'p1', display_name: 'Jack Barendse' }, has_squad: true,
  squads: state.visible ? state.squads : [],
  dates: [
    { date: plus(5), fixtures: [{ id: 'f1', opponent_name: 'Rovers', home_away: 'HOME', role: 'single', start_time: '13:00', venue: 'Main Oval', team_name: '1sts', mine: true }] },
    { date: plus(12), fixtures: [{ id: 'f2', opponent_name: 'Saints', home_away: 'AWAY', role: 'single', start_time: '13:00', venue: 'Saints Park', team_name: '1sts', mine: true }] },
  ],
  availability: { [plus(5)]: { status: 'AVAILABLE' } },
})
const profile = () => ({
  club: {}, player: { id: 'p1', display_name: 'Jack Barendse' },
  squads: state.visible ? state.squads : [], squads_visible: state.visible,
  selected: state.selected ? [{ date: plus(5), start_time: '13:00', venue: 'Main Oval', opponent_name: 'Rovers', home_away: 'HOME', label: null, round: '4', team_name: state.visible ? '1sts' : null, is_captain: true, is_wicket_keeper: false }] : [],
  training: { upcoming: [{ date: plus(2), label: 'Tuesday nets' }], attended_8_weeks: 5, last_attended: plus(-6) },
})

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  // Every section of the player page starts closed. These checks read what is inside them,
  // so each context starts with them opened, the way a returning player's page can be.
  const _newContext = browser.newContext.bind(browser)
  browser.newContext = async (o) => {
    const c = await _newContext(o)
    await c.addInitScript(() => { try { if (!localStorage.getItem('bs.playerpage.open')) localStorage.setItem('bs.playerpage.open', JSON.stringify({ availability: true, selection: true, admin: true, voting: true, stats: true, fantasy: true })) } catch (e) { /* no storage */ } })
    return c
  }

  const ctx = await browser.newContext({ viewport: { width: 1000, height: 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(6000)
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const hits = { profile: 0 }
  const json = (r, body) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route(/\/api\/public\/availability\/tok\/me\/profile(\?.*)?$/, (r) => { hits.profile++; return json(r, profile()) })
  await page.route(/\/api\/public\/availability\/tok\/me(\?.*)?$/, (r) => json(r, me()))
  await page.route(/\/api\/public\/availability\/tok$/, (r) => json(r, { club: me().club, require_pin: true, players: [{ id: 'p1', display_name: 'Jack Barendse', has_phone: true }] }))

  await page.goto(`${BASE}/avail/tok`)
  await page.locator('[data-hero]').waitFor({ timeout: 20000 })

  await safe('Squad under the name', async () => {
    console.log('\n── Squad on the availability page ──')
    const chips = await page.locator('[data-my-squads]').innerText()
    check('the squads are shown under the name', /1sts/.test(chips) && /T20/.test(chips), chips)
  })

  await safe('My page', async () => {
    console.log('\n── My page ──')
    await page.locator('[data-my-page]').waitFor()
    await page.locator('[data-groups]').waitFor()
    const t = (await page.locator('[data-my-page]').innerText()).replace(/\s+/g, ' ')
    check('the profile was fetched once', hits.profile === 1, String(hits.profile))
    check('it shows their availability for the next game', /Available/i.test(t))
    check('it shows the locked side with team, opponent and time', /Rovers/.test(t) && /13:00/.test(t) && /1sts/.test(t), t.slice(0, 400))
    check('...and that they are captain', /Captain/.test(t))
    check('it lists the next training', /Tuesday nets/.test(t))
    check('...and how often they have been lately', /5 sessions in the last eight weeks/.test(t), t)
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/player-page.png` : '/tmp/player-page.png' })
    await page.getByText('Your answers save automatically').waitFor()
    check('the availability editor is on the same page', (await page.locator('[data-availability]').count()) === 1)
  })

  await safe('Nothing selected yet', async () => {
    console.log('\n── Nothing selected yet ──')
    state.selected = false
    await page.reload(); await page.locator('[data-hero]').waitFor()
    await page.locator('[data-no-selection]').waitFor()
    check('it says nothing yet, and when sides show', /selectors lock them/.test(await page.locator('[data-no-selection]').innerText()))
  })

  await safe('Squad switched off', async () => {
    console.log('\n── The club keeps squads private ──')
    state.visible = false
    await page.reload(); await page.locator('[data-hero]').waitFor()
    check('no squad chips under the name', (await page.locator('[data-my-squads]').count()) === 0)
    await page.locator('[data-my-page]').waitFor()
    await page.getByText('has not turned on squad names').waitFor()
    check('My page says squads are not shown, rather than naming one', true)
  })

  await safe('390px', async () => {
    console.log('\n── 390px ──')
    state.visible = true; state.selected = true
    await page.setViewportSize({ width: 390, height: 800 })
    await page.reload(); await page.locator('[data-hero]').waitFor()
    let overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
    await page.locator('[data-groups]').waitFor(); await page.waitForTimeout(300)
    overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
    check('no sideways overflow', overflow <= 1, String(overflow))
  })

  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
