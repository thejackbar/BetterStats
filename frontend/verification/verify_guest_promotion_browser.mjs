// Drives the REAL "Not on the roster" panel on BOTH Players screens.
import { chromium } from 'playwright'

const BASE = 'http://localhost:5199'
let PASS = 0, FAIL = 0
const FAILURES = []
function check(label, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (ok) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); console.log(`  FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`) }
}

const GUESTS = {
  guests: [
    { key: 'dave trialist', name: 'Dave Trialist', attended: 3, last_attended: '2026-08-21', sessions: [] },
    { key: 'one off', name: 'One Off', attended: 1, last_attended: '2026-08-14', sessions: [] },
  ],
  days: 90,
  pending_registrations: 1,
}

let wire

async function mount(page, { modules = ['select'], guests = GUESTS } = {}) {
  wire = { promote: null, listed: 0 }
  // Catch-all FIRST — Playwright matches routes in reverse registration order.
  // Several of these screens map straight over their response, so a bare {}
  // crashes them before the panel under test ever renders. Anything that looks
  // like a list gets a list.
  await page.route('**/api/**', (r) => {
    const u = r.request().url()
    const isList = /\/(teams|players|grades|fixtures|ladders)(\?|$)/.test(u)
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(isList ? [] : {}) })
  })
  await page.route('**/api/auth/me', (r) => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1', capabilities: ['*'], entitlements: { modules, status: 'active' } }),
  }))
  await page.route('**/api/club-admin/players', (r) => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify([{ id: 'p1', name: 'Barendse, Jack', display_name: 'Barendse, Jack', status: 'active' }]),
  }))
  await page.route('**/api/nets/roster', (r) => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ players: [{ id: 'p1', name: 'Barendse, Jack' }, { id: 'p2', name: 'Mant, Brad' }] }),
  }))
  await page.route('**/api/nets/guests?**', (r) => { wire.listed += 1; return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(guests) }) })
  await page.route('**/api/nets/guests/promote', (r) => {
    wire.promote = JSON.parse(r.request().postData() || '{}')
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', player_id: 'newp', player_name: 'Trialist, Dave', sessions_moved: 3, duplicates_dropped: 0 }) })
  })
}

async function exercise(page, label) {
  console.log(`\n── ${label} ──`)
  await page.waitForSelector('text=Not on the roster', { timeout: 20000 })
  check('the panel renders', await page.locator('text=Not on the roster').count() > 0, true)
  check('it summarises how many', await page.locator('text=/2 people have been to nets/').count() > 0, true)

  await page.click('text=Not on the roster')
  await page.waitForSelector('text=Dave Trialist')
  check('the guest is named', await page.locator('text=Dave Trialist').count() > 0, true)
  check('with how often they turned up', await page.locator('text=/3 sessions/').count() > 0, true)
  check('someone waiting in Check-in is pointed at, not duplicated',
    await page.locator('text=/Review them in Nets/').count() > 0, true)

  // Match to an existing player.
  await page.locator('button:has-text("Already on the list")').first().click()
  await page.waitForSelector('input[placeholder="Search the roster…"]')
  await page.fill('input[placeholder="Search the roster…"]', 'Mant')
  await page.waitForSelector('button:has-text("Mant, Brad")')
  check('the roster search narrows', await page.locator('button:has-text("Barendse, Jack")').count(), 0)
  await page.click('button:has-text("Mant, Brad")')
  await page.waitForTimeout(500)
  check('the guest key and player go on the wire', wire.promote, { key: 'dave trialist', player_id: 'p2', name: null })

  // And straight creation.
  wire.promote = null
  await page.locator('button:has-text("Add as a player")').first().click()
  await page.waitForTimeout(500)
  check('creating sends the key with no player', wire.promote, { key: 'dave trialist', player_id: null, name: null })

  check('no horizontal overflow at 1280px', await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(400)
  check('no horizontal overflow at 390px', await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false)
  await page.setViewportSize({ width: 1280, height: 900 })
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  for (const [label, url] of [
    ['BetterStats → Players', '/admin/players'],
    ['BetterSelect → Players', '/admin/betterselect/players'],
  ]) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    await mount(page)
    await page.goto(BASE + url)
    await exercise(page, label)
    check('no page errors', errors, [])
    await ctx.close()
  }

  console.log('\n── A club without BetterSelect ──')
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const page = await ctx.newPage()
    await mount(page, { modules: [] })
    await page.goto(`${BASE}/admin/players`)
    await page.waitForSelector('text=Add player', { timeout: 20000 })
    check('the panel does not render', await page.locator('text=Not on the roster').count(), 0)
    check('and the endpoint is never called', wire.listed, 0)
    await ctx.close()
  }

  console.log('\n── Nobody to sort out ──')
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const page = await ctx.newPage()
    await mount(page, { guests: { guests: [], days: 90, pending_registrations: 0 } })
    await page.goto(`${BASE}/admin/players`)
    await page.waitForSelector('text=Add player', { timeout: 20000 })
    await page.waitForTimeout(700)
    check('the endpoint is asked', wire.listed > 0, true)
    check('but nothing is drawn when everyone is on the list',
      await page.locator('text=Not on the roster').count(), 0)
    await ctx.close()
  }

  await browser.close()
  console.log(`\n${'='.repeat(60)}\n${PASS} passed, ${FAIL} failed`)
  if (FAILURES.length) { console.log('\nFailures:'); FAILURES.forEach((f) => console.log('  -', f)) }
  process.exit(FAIL ? 1 : 0)
}

run().catch((e) => { console.error(e); process.exit(1) })
