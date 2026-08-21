// Drives the REAL net check-in pages in Chromium against the dev server, with
// the API stubbed at the network layer. Asserts what a screenshot can't reach:
// the params on the wire, the step transitions, and the live screen's pop-up.
import { chromium } from 'playwright'

const BASE = 'http://localhost:5199'
const TOKEN = 'tok-verify-abc'
let PASS = 0, FAIL = 0
const FAILURES = []

function check(label, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (ok) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); console.log(`  FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`) }
}

const CLUB = { name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'applecross', logo_url: null, primary_color: '#16c784', accent_color: '#243352' }
const SESSIONS = [{ id: 's1', session_date: '2026-08-21', label: 'Tuesday senior nets' }]
const PLAYERS = [
  { id: 'p1', display_name: 'Barendse, Jack', has_phone: true },
  { id: 'p2', display_name: 'Mant, Brad', has_phone: true },
  { id: 'p3', display_name: 'Cole, Graeme', has_phone: false },
]

// State the stub mutates, so the page's own flow drives it like the real API.
let landing, wire

function resetState(over = {}) {
  wire = { verify: null, checkin: 0, register: null }
  landing = {
    club: CLUB, require_pin: true, allow_registration: true,
    sessions: SESSIONS, players: PLAYERS, me: null, ...over,
  }
}

async function stub(page) {
  await page.route('**/api/public/net-checkin/**', async (route) => {
    const url = route.request().url()
    const method = route.request().method()
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (method === 'GET') return json(landing)
    if (url.includes('/verify')) {
      const b = JSON.parse(route.request().postData() || '{}')
      wire.verify = b
      if (b.pin !== '1234' && landing.require_pin) {
        return json({ detail: 'That PIN didn’t match. Try the last 4 digits of your mobile.' }, 401)
      }
      return json({ status: 'ok', player: { id: b.player_id, display_name: 'Barendse, Jack' } })
    }
    if (url.includes('/check-in')) {
      wire.checkin += 1
      return json({ status: 'ok', player: { display_name: 'Barendse, Jack' }, sessions: SESSIONS, added: 1, already_in: false })
    }
    if (url.includes('/register')) {
      wire.register = JSON.parse(route.request().postData() || '{}')
      return json({ status: 'ok', name: wire.register.full_name, sessions: SESSIONS })
    }
    if (url.includes('/switch')) { landing.me = null; return json({ status: 'ok' }) }
    return json({}, 404)
  })
}

async function overflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  // ── The existing-player path, with a PIN ────────────────────────────────
  console.log('\n── A player scans in (PIN on) ──')
  {
    resetState()
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    await stub(page)
    await page.goto(`${BASE}/nets-checkin/${TOKEN}`)
    await page.waitForSelector('text=Tuesday senior nets', { timeout: 15000 })

    check('the club is named', await page.locator('text=Applecross Cricket Club').count() > 0, true)
    check('it says what you are checking in to', await page.locator('text=/Tuesday senior nets/').count() > 0, true)
    check('the club nav is suppressed on this standalone page', await page.locator('nav').count(), 0)
    check('no horizontal overflow at 390px', await overflow(page), false)

    // A player with no mobile is marked, not silently broken.
    check('a player with no mobile is flagged', await page.locator('text=no mobile').count() > 0, true)

    await page.click('text=Barendse, Jack')
    await page.waitForSelector('text=Last 4 digits of your mobile')
    check('picking a name asks for the PIN', await page.locator('text=Last 4 digits of your mobile').count() > 0, true)

    // A wrong PIN reports the server's own words, and does not check anyone in.
    await page.fill('input[inputmode="numeric"]', '0000')
    await page.click('button:has-text("Check in")')
    await page.waitForSelector('text=/didn’t match/')
    check('a wrong PIN shows the server’s reason', await page.locator('text=/didn’t match/').count() > 0, true)
    check('and checks nobody in', wire.checkin, 0)

    await page.fill('input[inputmode="numeric"]', '1234')
    await page.click('button:has-text("Check in")')
    await page.waitForSelector('text=You’re checked in')
    check('the right PIN checks you in', await page.locator('text=You’re checked in').count() > 0, true)
    check('the player id went on the wire', wire.verify.player_id, 'p1')
    check('the typed PIN went on the wire', wire.verify.pin, '1234')
    check('check-in was called exactly once', wire.checkin, 1)
    check('the session is named on the confirmation', await page.locator('text=/Tuesday senior nets/').count() > 0, true)
    check('no page errors', errors, [])
    check('no overflow on the confirmation', await overflow(page), false)
    await ctx.close()
  }

  // ── No PIN: picking your name IS the check-in ───────────────────────────
  console.log('\n── PIN switched off ──')
  {
    resetState({ require_pin: false })
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    await stub(page)
    await page.goto(`${BASE}/nets-checkin/${TOKEN}`)
    await page.waitForSelector('text=Barendse, Jack')
    await page.click('text=Barendse, Jack')
    await page.waitForSelector('text=You’re checked in')
    check('one tap checks you in, no PIN screen', wire.checkin, 1)
    check('the PIN sent is empty', wire.verify.pin, '')
    check('no page errors', errors, [])
    await ctx.close()
  }

  // ── A returning player is not asked again ───────────────────────────────
  console.log('\n── A returning player (cookie already verified) ──')
  {
    resetState({ me: { id: 'p1', display_name: 'Barendse, Jack', checked_in: false } })
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const page = await ctx.newPage()
    await stub(page)
    await page.goto(`${BASE}/nets-checkin/${TOKEN}`)
    await page.waitForSelector('button:has-text("Check in")')
    check('lands on the button, not the roster', await page.locator('input[placeholder="Search your name…"]').count(), 0)
    check('is not asked for the PIN again', await page.locator('text=Last 4 digits').count(), 0)
    check('greets them by name', await page.locator('text=Barendse, Jack').count() > 0, true)
    await page.click('button:has-text("Check in")')
    await page.waitForSelector('text=You’re checked in')
    check('one tap and done', wire.checkin, 1)
    check('it never re-verified', wire.verify, null)
    await ctx.close()
  }

  // ── Already checked in ──────────────────────────────────────────────────
  console.log('\n── Already checked in ──')
  {
    resetState({ me: { id: 'p1', display_name: 'Barendse, Jack', checked_in: true } })
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const page = await ctx.newPage()
    await stub(page)
    await page.goto(`${BASE}/nets-checkin/${TOKEN}`)
    await page.waitForSelector('text=You’re already checked in')
    check('says so rather than checking in again', await page.locator('text=You’re already checked in').count() > 0, true)
    check('and calls nothing', wire.checkin, 0)
    await ctx.close()
  }

  // ── A newcomer registers ────────────────────────────────────────────────
  console.log('\n── A newcomer registers ──')
  {
    resetState()
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    await stub(page)
    await page.goto(`${BASE}/nets-checkin/${TOKEN}`)
    await page.waitForSelector('text=I’m not on the list')
    await page.click('text=I’m not on the list')
    await page.waitForSelector('text=New to the club?')

    // Every field the brief asked for is present.
    for (const label of ['Full name', 'Mobile', 'Email', 'Date of birth', 'Previous club']) {
      check(`the form asks for ${label.toLowerCase()}`, await page.locator(`text=${label}`).count() > 0, true)
    }
    const submit = page.locator('form button[type="submit"]')
    check('submit is dead until a name is typed', await submit.isDisabled(), true)

    const inputs = page.locator('form input')
    await inputs.nth(0).fill('Tom Newcomer')
    await inputs.nth(1).fill('0455 123 456')
    await inputs.nth(2).fill('tom@example.com')
    await inputs.nth(3).fill('2008-03-04')
    await inputs.nth(4).fill('Willetton CC')
    check('submit enables once named', await submit.isDisabled(), false)
    check('no overflow on the form at 390px', await overflow(page), false)
    await submit.click()
    await page.waitForSelector('text=You’re checked in')

    check('the name went on the wire', wire.register.full_name, 'Tom Newcomer')
    check('the phone went on the wire', wire.register.phone, '0455 123 456')
    check('the email went on the wire', wire.register.email, 'tom@example.com')
    check('the date of birth went on the wire', wire.register.date_of_birth, '2008-03-04')
    check('the previous club went on the wire', wire.register.previous_club, 'Willetton CC')
    check('they are told they are in as a guest', await page.locator('text=/in as a guest/').count() > 0, true)
    check('no page errors', errors, [])
    await ctx.close()
  }

  // ── Registration switched off ───────────────────────────────────────────
  console.log('\n── Registration switched off ──')
  {
    resetState({ allow_registration: false })
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const page = await ctx.newPage()
    await stub(page)
    await page.goto(`${BASE}/nets-checkin/${TOKEN}`)
    await page.waitForSelector('text=Barendse, Jack')
    check('the register button is not offered', await page.locator('text=I’m not on the list').count(), 0)
    check('and it says who to ask instead', await page.locator('text=/Ask whoever is running nets/').count() > 0, true)
    await ctx.close()
  }

  // ── Nothing running ─────────────────────────────────────────────────────
  console.log('\n── No session on ──')
  {
    resetState({ sessions: [] })
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const page = await ctx.newPage()
    await stub(page)
    await page.goto(`${BASE}/nets-checkin/${TOKEN}`)
    await page.waitForSelector('text=No nets on right now')
    check('says nothing is running', await page.locator('text=No nets on right now').count() > 0, true)
    check('offers no roster to tap', await page.locator('input[placeholder="Search your name…"]').count(), 0)
    check('and offers a re-check', await page.locator('text=Check again').count() > 0, true)
    await ctx.close()
  }

  // ── A dead link ─────────────────────────────────────────────────────────
  console.log('\n── A rotated / dead link ──')
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const page = await ctx.newPage()
    await page.route('**/api/public/net-checkin/**', (r) =>
      r.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'This check-in link isn’t active' }) }))
    await page.goto(`${BASE}/nets-checkin/dead-token`)
    await page.waitForSelector('text=This link isn’t active')
    check('a dead link says so and nothing else', await page.locator('text=This link isn’t active').count() > 0, true)
    check('no roster is leaked on a dead link', await page.locator('text=Barendse').count(), 0)
    await ctx.close()
  }

  await browser.close()
  console.log(`\n${'='.repeat(60)}\n${PASS} passed, ${FAIL} failed`)
  if (FAILURES.length) { console.log('\nFailures:'); FAILURES.forEach((f) => console.log('  -', f)) }
  process.exit(FAIL ? 1 : 0)
}

run().catch((e) => { console.error(e); process.exit(1) })
