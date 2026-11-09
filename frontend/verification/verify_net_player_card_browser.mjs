// Drives the REAL player page (/avail/:token) in Chromium with the API stubbed at
// the network layer: checking yourself in to nets, and seeing where you bat.
//   * a session that is on shows a check-in button, and the Selection header says
//     "Nets on, check in"
//   * tapping it POSTs exactly /me/nets/<session>/checkin and then shows the net,
//     the time you bat (in the club's own 5:06pm form) and second-go times
//   * the Selection header then says where you bat
//   * a queue session says where you are in the batting order, and "in the nets now"
//   * checked in but not placed, not batting, and no slot before the finish are each
//     said in words
//   * once the nets have started there is no button, and the page says why
//   * a refused check-in shows the server's sentence on the card
//   * the card re-reads when the page comes back (a move by the coach shows up)
//   * a session with nothing on draws nothing
//   * 390px: no sideways overflow
//
//   npx vite preview --outDir /tmp/dist --port 5199 &    node verify_net_player_card_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }
const iso = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }

const state = { sessions: [], checkins: [], refuse: null }
const player = () => ({ id: 'p1', display_name: 'Sam Sledge', photo_url: null, shirt_number: '7', profile_path: '/players/p1' })
const me = () => ({ club: { name: 'Dash CC' }, player: player(), has_squad: true, squads: ['1sts'], allow_maybe: true, week_names: {}, dates: [], availability: {} })
const profile = () => ({
  club: {}, player: player(), can_update_details: false, squads: ['1sts'], squads_visible: true,
  modules: ['squad', 'selected', 'training'], selected: [],
  training: { upcoming: [], attended_8_weeks: 0, last_attended: null }, nets: state.sessions,
  season: null, fees: null, votes: [], votes_cast: [], fines: [], fantasy: null, cards: null,
})
const slotPlace = (over = {}) => ({
  mode: 'auto', bats: true, batted: false, configured: true, net: { id: 'n2', name: '3rd & 4th XI' }, time: '17:06',
  start_at: new Date(Date.now() + 25 * 60000).toISOString(), slot_minutes: 7, also: ['17:34'], fits: true, ...over,
})
const sess = (over = {}) => ({ id: 's1', label: 'Tuesday nets', date: iso(0), mode: 'auto', checked_in: false, can_check_in: true, started: false, place: null, ...over })

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ['--no-sandbox'] })
  const errors = []
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const ctx = await browser.newContext({ viewport: { width: 1000, height: 900 } })
  await ctx.addInitScript(() => { try { localStorage.setItem('bs.playerpage.open', JSON.stringify({ availability: true, selection: true })) } catch (e) { /* no storage */ } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(6000)
  page.on('pageerror', (e) => errors.push(e.message))
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route(/\/api\/public\/availability\/tok\/me\/profile(\?.*)?$/, (r) => json(r, profile()))
  await page.route(/\/api\/public\/availability\/tok\/me\/nets$/, (r) => json(r, { sessions: state.sessions }))
  await page.route(/\/api\/public\/availability\/tok\/me\/nets\/([^/]+)\/checkin$/, (r) => {
    state.checkins.push(new URL(r.request().url()).pathname)
    if (state.refuse) return json(r, { detail: state.refuse }, 409)
    state.sessions = [sess({ checked_in: true, can_check_in: false, place: slotPlace() })]
    return json(r, { status: 'ok', added: 1, sessions: state.sessions })
  })
  await page.route(/\/api\/public\/availability\/tok\/me(\?.*)?$/, (r) => json(r, me()))
  await page.route(/\/api\/public\/availability\/tok$/, (r) => json(r, { club: me().club, require_pin: true, players: [{ id: 'p1', display_name: 'Sam Sledge', has_phone: true }] }))

  const load = async () => {
    await page.goto(`${BASE}/avail/tok`)
    await page.locator('[data-hero]').waitFor({ timeout: 20000 })
    await page.locator('[data-groups]').waitFor()
  }
  const summary = async () => (await page.locator('[data-group="selection"]').first().innerText().catch(() => '')) || ''
  const body = () => page.locator('body').innerText()

  await safe('Nothing on', async () => {
    console.log('\n── No session on ──')
    state.sessions = []
    await load()
    check('the card draws nothing', (await page.locator('[data-nets-today]').count()) === 0)
  })

  await safe('Check in', async () => {
    console.log('\n── Checking yourself in ──')
    state.sessions = [sess()]
    await load()
    await page.locator('[data-nets-checkin]').waitFor()
    check('there is a check-in button in words', /I am here, check me in/.test(await page.locator('[data-nets-checkin]').innerText()))
    check('the Selection header says nets are on', /Nets on, check in/.test(await body()))
    await page.locator('[data-nets-checkin]').click()
    await page.locator('[data-place="slot"]').waitFor()
    check('one POST to this session\'s own check-in path', JSON.stringify(state.checkins) === JSON.stringify(['/api/public/availability/tok/me/nets/s1/checkin']), JSON.stringify(state.checkins))
    check('the net is named', (await page.locator('[data-place-net]').innerText()).includes('3rd & 4th XI'))
    check('the time is in the club\'s own form', /5:06pm/.test(await page.locator('[data-place-time]').innerText()))
    check('and how long until it, by this phone\'s clock', /in (2[3-5]) min/.test(await page.locator('[data-place-rel]').innerText()), await page.locator('[data-place-rel]').innerText())
    check('second go times are listed', /5:34pm/.test(await page.locator('[data-place-also]').innerText()))
    check('the button is gone', (await page.locator('[data-nets-checkin]').count()) === 0)
    check('the Selection header now says where you bat', /3rd & 4th XI at 5:06pm/.test(await body()))
  })

  await safe('States', async () => {
    console.log('\n── Every state is said in words ──')
    const show = async (placeOver, sessOver = {}) => {
      state.sessions = [sess({ checked_in: true, can_check_in: false, place: slotPlace(placeOver), ...sessOver })]
      await load()
      await page.locator('[data-nets-today]').waitFor()
      return page.locator('[data-nets-today]').innerText()
    }
    check('no net yet', /Your coach will put you in a net/.test(await show({ net: null, time: null })))
    check('no slot before the finish', /no slot for you before the finish/.test(await show({ time: null, fits: false, start_at: null })))
    check('not batting', /here and not batting/.test(await show({ bats: false, net: null, time: null })))
    check('times not set yet', /times are not set yet/.test(await show({ configured: false, net: null, time: null })))
    state.sessions = [sess({ mode: 'manual', checked_in: true, can_check_in: false, place: { mode: 'manual', bats: true, batted: false, position: 3, ahead: 2, waiting: 5, nets: 2, in_nets_now: false } })]
    await load()
    check('a queue says your place', /3rd/.test(await page.locator('[data-place-position]').innerText()))
    check('and how many are ahead', /2 people are ahead of you/.test(await page.locator('[data-nets-today]').innerText()))
    check('the header says your place in the order', /3rd in the batting order/.test(await body()))
    state.sessions = [sess({ mode: 'manual', checked_in: true, can_check_in: false, place: { mode: 'manual', bats: true, batted: false, position: 1, ahead: 0, waiting: 5, nets: 2, in_nets_now: true } })]
    await load()
    check('first in the queue is in the nets now', /in the nets now/i.test(await page.locator('[data-nets-today]').innerText()))
    state.sessions = [sess({ mode: 'manual', checked_in: true, can_check_in: false, place: { mode: 'manual', bats: true, batted: true, position: null, ahead: null, waiting: 4, nets: 2, in_nets_now: false } })]
    await load()
    check('after your turn it says so', /had your turn/.test(await page.locator('[data-nets-today]').innerText()))
  })

  await safe('Started', async () => {
    console.log('\n── Once the nets have started ──')
    state.sessions = [sess({ can_check_in: false, started: true })]
    await load()
    await page.locator('[data-nets-closed]').waitFor()
    check('there is no check-in button', (await page.locator('[data-nets-checkin]').count()) === 0)
    check('and the page says the nets have started', /nets have started/.test(await page.locator('[data-nets-closed]').innerText()))
  })

  await safe('Refused', async () => {
    console.log('\n── A refused check-in ──')
    state.sessions = [sess()]
    state.refuse = 'That session is not on right now.'
    await load()
    await page.locator('[data-nets-checkin]').click()
    await page.locator('[data-nets-error]').waitFor()
    check('the server\'s sentence is on the card', /not on right now/.test(await page.locator('[data-nets-error]').innerText()))
    check('and the button is still there to try again', (await page.locator('[data-nets-checkin]').count()) === 1)
    state.refuse = null
  })

  await safe('Re-read', async () => {
    console.log('\n── A move by the coach shows up ──')
    state.sessions = [sess({ checked_in: true, can_check_in: false, place: slotPlace() })]
    await load()
    check('first the 5:06pm slot', /5:06pm/.test(await page.locator('[data-place-time]').innerText()))
    state.sessions = [sess({ checked_in: true, can_check_in: false, place: slotPlace({ time: '17:20', also: [] }) })]
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
    await page.waitForFunction(() => /5:20pm/.test(document.querySelector('[data-place-time]')?.innerText || ''))
    check('coming back to the page re-reads it: now 5:20pm', true)
  })

  await safe('Phone', async () => {
    console.log('\n── 390px ──')
    await page.setViewportSize({ width: 390, height: 844 })
    state.sessions = [sess({ checked_in: true, can_check_in: false, place: slotPlace({ net: { id: 'n2', name: 'Third and Fourth XI with a very long net name' } }) })]
    await load()
    const ov = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    check('no sideways overflow with the card showing', ov <= 0, String(ov))
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/player-card-390.png` : '/tmp/player-card-390.png', fullPage: true })
  })

  check('no uncaught page errors', errors.length === 0, errors.join(' | '))
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  await browser.close()
  process.exit(FAIL ? 1 : 0)
}
run()
