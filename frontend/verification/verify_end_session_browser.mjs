// Drives the REAL live nets screen through ending and reopening a session.
import { chromium } from 'playwright'

const BASE = 'http://localhost:5199'
let PASS = 0, FAIL = 0
const FAILURES = []
function check(label, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (ok) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); console.log(`  FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`) }
}

const SETTINGS = { duration_seconds: 600, nets: 2, auto_roll: false, sound: false, alerts: [] }
let state, wire

function payload() {
  return {
    id: 'sess1', version: state.version, server_time: new Date().toISOString(),
    session_date: '2026-08-20', label: 'Net session', notes: null, status: state.status,
    settings: SETTINGS,
    timer: state.timer,
    attendees: state.attendees,
    attendee_count: state.attendees.length,
    batted_count: state.attendees.filter((a) => a.batted).length,
    created_at: new Date().toISOString(),
  }
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))

  state = {
    version: 1, status: 'active',
    timer: { running: true, ends_at: new Date(Date.now() + 300000).toISOString(), remaining_seconds: 300, duration_seconds: 600, turn_seq: 1 },
    attendees: [
      { id: 'a1', player_id: 'p1', guest_name: null, name: 'Dagg, Will', photo_url: null, skill_positions: [], is_guest: false, batted: false, bats: true, position: 0, source: 'admin' },
      { id: 'a2', player_id: 'p2', guest_name: null, name: 'Meredith, Justin', photo_url: null, skill_positions: [], is_guest: false, batted: true, bats: true, position: 1, source: 'admin' },
    ],
  }
  wire = { patches: [] }

  await page.route('**/api/**', (r) => {
    const u = r.request().url()
    const isList = /\/(teams|players|grades|fixtures|ladders)(\?|$)/.test(u)
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(isList ? [] : {}) })
  })
  await page.route('**/api/auth/me', (r) => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1', capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' } }),
  }))
  await page.route('**/api/nets/roster', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ players: [] }) }))
  await page.route('**/api/nets/checkin-link**', (r) => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ enabled: true, require_pin: true, allow_registration: true, token: 'tok', path: '/nets-checkin/tok', phone_coverage: { with_phone: 1, total: 1 }, pending_registrations: 0 }),
  }))
  await page.route('**/api/nets/sessions/sess1/live**', (r) => {
    const since = new URL(r.request().url()).searchParams.get('since')
    if (since !== null && Number(since) === state.version) {
      return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ version: state.version, server_time: new Date().toISOString(), unchanged: true }) })
    }
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload()) })
  })
  // The PATCH mirrors the shipped handler: ending stops the clock too.
  await page.route('**/api/nets/sessions/sess1', (r) => {
    if (r.request().method() === 'PATCH') {
      const b = JSON.parse(r.request().postData() || '{}')
      wire.patches.push(b)
      if (b.status) {
        state.status = b.status
        if (b.status === 'done') state.timer = { ...state.timer, running: false, ends_at: null }
        state.version += 1
      }
    }
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload()) })
  })

  await page.goto(`${BASE}/admin/betterselect/nets/sess1`)
  await page.waitForSelector('text=Net session', { timeout: 20000 })

  console.log('\n── While the session is live ──')
  check('it reads Live', await page.locator('text=Live').first().count() > 0, true)
  check('End session is offered', await page.getByRole('button', { name: 'End session' }).count(), 1)
  check('the timer controls are there', await page.getByRole('button', { name: 'Pause' }).count(), 1)
  check('the check-in screen shortcut is there', await page.locator('text=Check-in screen').count() > 0, true)
  check('Reopen is not offered', await page.getByRole('button', { name: 'Reopen' }).count(), 0)

  console.log('\n── The confirm names what it costs ──')
  let dialogMsg = null
  page.once('dialog', async (d) => { dialogMsg = d.message(); await d.dismiss() })
  await page.getByRole('button', { name: 'End session' }).click()
  await page.waitForTimeout(400)
  check('it warns about the queue', /1 person is still in the queue/.test(dialogMsg || ''), true)
  check('and says the QR code stops working', /QR code/.test(dialogMsg || ''), true)
  check('dismissing changes nothing', wire.patches.length, 0)
  check('the session is still live', await page.getByRole('button', { name: 'End session' }).count(), 1)

  console.log('\n── Ending it ──')
  page.once('dialog', async (d) => { await d.accept() })
  await page.getByRole('button', { name: 'End session' }).click()
  await page.waitForSelector('text=Session ended', { timeout: 10000 })
  check('the status goes on the wire', wire.patches, [{ status: 'done' }])
  check('the header reads Ended', await page.locator('text=Ended').first().count() > 0, true)
  check('the timer controls are gone', await page.getByRole('button', { name: 'Pause' }).count(), 0)
  check('Start is not offered', await page.getByRole('button', { name: 'Start' }).count(), 0)
  check('checking more people in is not offered', await page.getByRole('button', { name: 'Check in players' }).count(), 0)
  check('the check-in screen shortcut is withdrawn', await page.locator('text=Check-in screen').count(), 0)
  check('it says what the night came to', await page.locator('text=/1 batted of 2 here/').count() > 0, true)
  check('the attendance list is still there', await page.locator('text=Dagg, Will').count() > 0, true)
  check('downloading the list still works', await page.getByRole('link', { name: 'List' }).count(), 1)
  check('Reopen is offered', await page.getByRole('button', { name: 'Reopen' }).count(), 1)

  console.log('\n── Reopening ──')
  await page.getByRole('button', { name: 'Reopen' }).click()
  await page.waitForSelector('text=Session reopened', { timeout: 10000 })
  check('the status goes back on the wire', wire.patches[1], { status: 'active' })
  check('End session is back', await page.getByRole('button', { name: 'End session' }).count(), 1)
  check('so are the timer controls', await page.getByRole('button', { name: 'Start' }).count(), 1)
  check('and check-in', await page.getByRole('button', { name: 'Check in players' }).count(), 1)

  console.log('\n── Housekeeping ──')
  check('no page errors', errors, [])
  check('no horizontal overflow at 1280px', await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(400)
  check('no horizontal overflow at 390px', await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false)

  await browser.close()
  console.log(`\n${'='.repeat(60)}\n${PASS} passed, ${FAIL} failed`)
  if (FAILURES.length) { console.log('\nFailures:'); FAILURES.forEach((f) => console.log('  -', f)) }
  process.exit(FAIL ? 1 : 0)
}

run().catch((e) => { console.error(e); process.exit(1) })
