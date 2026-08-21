// Drives the REAL live net session screen and proves the arrival pop-up:
// it fires for a self check-in arriving on a poll, stays quiet for the
// manager's own writes, and does not announce a screen's first paint.
import { chromium } from 'playwright'

const BASE = 'http://localhost:5199'
let PASS = 0, FAIL = 0
const FAILURES = []
function check(label, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (ok) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); console.log(`  FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`) }
}

const SETTINGS = { duration_seconds: 600, nets: 2, auto_roll: false, sound: true, alerts: [] }
let state

function att(id, name, source, is_guest = false) {
  return { id, player_id: is_guest ? null : id, guest_name: is_guest ? name : null, name, photo_url: null, skill_positions: [], is_guest, batted: false, position: 0, source }
}

function payload() {
  return {
    id: 'sess1', version: state.version, server_time: new Date().toISOString(),
    session_date: '2026-08-21', label: 'Tuesday senior nets', notes: null, status: 'active',
    settings: SETTINGS,
    timer: { running: false, ends_at: null, remaining_seconds: 600, duration_seconds: 600, turn_seq: 0 },
    attendees: state.attendees,
    attendee_count: state.attendees.length,
    batted_count: 0, created_at: new Date().toISOString(),
  }
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))

  // Two people already there when the screen opens — these must NOT announce.
  state = { version: 1, attendees: [att('a1', 'Barendse, Jack', 'self'), att('a2', 'Mant, Brad', 'admin')] }

  // Playwright matches routes in REVERSE registration order, so the catch-all
  // has to be registered FIRST or it swallows every specific handler below it.
  await page.route('**/api/**', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) }))

  // Signed in, so the admin screen renders.
  await page.route('**/api/auth/me', (r) => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross',
      organisation_id: 'o1', capabilities: ['*'],
      entitlements: { modules: ['select'], status: 'active' },
    }),
  }))
  await page.route('**/api/nets/roster', (r) => r.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ players: [] }),
  }))
  await page.route('**/api/nets/sessions/sess1/live**', (r) => {
    const url = r.request().url()
    const since = new URL(url).searchParams.get('since')
    if (since !== null && Number(since) === state.version) {
      return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ version: state.version, server_time: new Date().toISOString(), unchanged: true }) })
    }
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload()) })
  })
  await page.route('**/api/nets/sessions/sess1', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload()) }))

  await page.goto(`${BASE}/admin/betterselect/nets/sess1`)
  await page.waitForSelector('text=Tuesday senior nets', { timeout: 20000 })

  console.log('\n── Opening the screen mid-session ──')
  check('the session renders', await page.locator('text=Tuesday senior nets').count() > 0, true)
  check('people already there do NOT trigger a pop-up', await page.locator('[role="status"]:has-text("Checked in")').count(), 0)
  check('a browser that has not been touched offers to turn sound on',
    await page.locator('text=/Tap once to turn on sound/').count() > 0, true)

  console.log('\n── Somebody scans themselves in ──')
  state.attendees = [...state.attendees, att('a3', 'Cole, Graeme', 'self')]
  state.version = 2
  await page.waitForSelector('[role="status"]:has-text("Checked in")', { timeout: 15000 })
  check('the pop-up fires for a self check-in', await page.locator('[role="status"]:has-text("Checked in")').count() > 0, true)
  check('and names who arrived', await page.locator('[role="status"]:has-text("Cole, Graeme")').count() > 0, true)
  check('no page errors', errors, [])
  check('no horizontal overflow', await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false)

  // Tapping it dismisses.
  await page.locator('[role="status"]').click()
  await page.waitForSelector('[role="status"]:has-text("Checked in")', { state: 'detached', timeout: 5000 })
  check('tapping the pop-up dismisses it', await page.locator('[role="status"]:has-text("Checked in")').count(), 0)

  console.log('\n── A name the manager added does NOT pop up ──')
  state.attendees = [...state.attendees, att('a4', 'Walk-up Trialist', 'admin', true)]
  state.version = 3
  await page.waitForSelector('text=Walk-up Trialist', { timeout: 15000 })
  check('the admin-added guest reaches the list', await page.locator('text=Walk-up Trialist').count() > 0, true)
  check('but raises no pop-up', await page.locator('[role="status"]:has-text("Checked in")').count(), 0)

  console.log('\n── A newcomer scanning in says so ──')
  state.attendees = [...state.attendees, att('a5', 'Tom Newcomer', 'self', true)]
  state.version = 4
  await page.waitForSelector('[role="status"]:has-text("Checked in")', { timeout: 15000 })
  check('a self-registered newcomer pops up', await page.locator('[role="status"]:has-text("Tom Newcomer")').count() > 0, true)
  check('and is flagged as new to the club',
    await page.locator('[role="status"]:has-text("New to the club")').count() > 0, true)

  console.log('\n── It clears itself ──')
  await page.waitForSelector('[role="status"]:has-text("Checked in")', { state: 'detached', timeout: 15000 })
  check('the pop-up clears on its own', await page.locator('[role="status"]:has-text("Checked in")').count(), 0)
  check('still no page errors', errors, [])

  await browser.close()
  console.log(`\n${'='.repeat(60)}\n${PASS} passed, ${FAIL} failed`)
  if (FAILURES.length) { console.log('\nFailures:'); FAILURES.forEach((f) => console.log('  -', f)) }
  process.exit(FAIL ? 1 : 0)
}

run().catch((e) => { console.error(e); process.exit(1) })
