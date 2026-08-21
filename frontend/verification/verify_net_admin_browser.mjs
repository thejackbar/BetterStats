// Drives the REAL admin Check-in tab: the QR/NFC panel and the review queue.
import { chromium } from 'playwright'

const BASE = 'http://localhost:5199'
let PASS = 0, FAIL = 0
const FAILURES = []
function check(label, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (ok) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); console.log(`  FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`) }
}

let link, regs, wire

const run = async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))

  link = { enabled: true, require_pin: true, allow_registration: true, token: 'tok-abc-123', path: '/nets-checkin/tok-abc-123', phone_coverage: { with_phone: 34, total: 41 }, pending_registrations: 1 }
  regs = [{ id: 'r1', full_name: 'Tom Newcomer', phone: '0455 123 456', email: 'tom@example.com', date_of_birth: '2008-03-04', previous_club: 'Willetton CC', status: 'pending', player_id: null, player_name: null, session_id: 's1', created_at: new Date().toISOString(), reviewed_at: null }]
  wire = { approve: null, dismiss: null, setLink: null }

  // Catch-all FIRST — Playwright matches routes in reverse registration order.
  await page.route('**/api/**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) }))
  await page.route('**/api/auth/me', (r) => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1', capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' } }),
  }))
  await page.route('**/api/nets/sessions**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ sessions: [] }) }))
  await page.route('**/api/nets/roster', (r) => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ players: [{ id: 'p3', name: 'Cole, Graeme' }, { id: 'p1', name: 'Barendse, Jack' }] }),
  }))
  await page.route('**/api/nets/checkin-link**', (r) => {
    if (r.request().method() === 'POST') { wire.setLink = JSON.parse(r.request().postData() || '{}') }
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(link) })
  })
  await page.route('**/api/nets/registrations?**', (r) => r.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ registrations: regs, pending_count: regs.filter((x) => x.status === 'pending').length }),
  }))
  await page.route('**/api/nets/registrations/r1/approve', (r) => {
    wire.approve = JSON.parse(r.request().postData() || '{}')
    regs = []
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', player_id: 'newp', player_name: 'Newcomer, Tom' }) })
  })
  await page.route('**/api/nets/registrations/r1/dismiss', (r) => {
    wire.dismiss = true
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) })
  })

  await page.goto(`${BASE}/admin/betterselect/nets`)
  await page.waitForSelector('text=Net Manager', { timeout: 20000 })

  console.log('\n── The tab carries what is waiting ──')
  check('the Check-in tab shows a pending count', await page.locator('text=Check-in (1)').count() > 0, true)

  await page.click('text=Check-in (1)')
  await page.waitForSelector('text=Self check-in (QR / NFC)')

  console.log('\n── The link panel ──')
  check('the panel is there', await page.locator('text=Self check-in (QR / NFC)').count() > 0, true)
  check('and reads as ON', await page.locator('text=Self check-in (QR / NFC)').locator('..').locator('text=ON').count() > 0, true)

  await page.click('text=Self check-in (QR / NFC)')
  await page.waitForSelector('input[readonly]')
  const url = await page.locator('input[readonly]').inputValue()
  check('the full URL is composed from the path', url.endsWith('/nets-checkin/tok-abc-123'), true)
  await page.waitForSelector('img[alt="Net check-in QR code"]', { timeout: 10000 })
  const src = await page.locator('img[alt="Net check-in QR code"]').getAttribute('src')
  check('a QR code is rendered for it', src.startsWith('data:image/png;base64,'), true)
  check('the QR can be downloaded to print', await page.locator('text=Download QR').count() > 0, true)
  check('NFC is explained beside it', await page.locator('text=/Writing an NFC tag/').count() > 0, true)
  check('it says the tag holds the same address', await page.locator('text=/same address as the QR code/').count() > 0, true)
  check('phone coverage is reported', await page.locator('text=/34/').count() > 0, true)
  check('and it warns who cannot check in', await page.locator('text=/7 players can’t check in/').count() > 0, true)

  console.log('\n── Turning the PIN off says what that means ──')
  await page.click('button:has-text("No PIN")')
  await page.waitForTimeout(400)
  check('the change goes on the wire', wire.setLink, { require_pin: false })

  console.log('\n── The review queue ──')
  check('the newcomer is listed', await page.locator('text=Tom Newcomer').count() > 0, true)
  for (const bit of ['0455 123 456', 'tom@example.com', 'Willetton CC']) {
    check(`their ${bit.includes('@') ? 'email' : bit.includes('0455') ? 'phone' : 'previous club'} is shown`, await page.locator(`text=${bit}`).count() > 0, true)
  }
  // Exact text: has-text is substring matching, and the status filter above
  // carries a "Dismissed" pill that would otherwise be counted as a decision.
  check('three decisions are offered', await page.locator('button:has-text("Add as a player")').count()
    + await page.locator('button:has-text("Already on the list")').count()
    + await page.getByRole('button', { name: 'Dismiss', exact: true }).count(), 3)

  console.log('\n── Matching to somebody already on the roster ──')
  await page.click('button:has-text("Already on the list")')
  await page.waitForSelector('input[placeholder="Search the roster…"]')
  await page.fill('input[placeholder="Search the roster…"]', 'Cole')
  await page.waitForSelector('button:has-text("Cole, Graeme")')
  check('the roster search narrows', await page.locator('button:has-text("Barendse, Jack")').count(), 0)
  await page.click('button:has-text("Cole, Graeme")')
  await page.waitForTimeout(500)
  check('the picked player goes on the wire', wire.approve, { player_id: 'p3' })

  console.log('\n── No page errors, no overflow ──')
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
