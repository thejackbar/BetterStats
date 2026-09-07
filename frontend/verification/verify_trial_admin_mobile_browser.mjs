// Drives the real public self-serve trial signup in Chromium, with the API
// stubbed at the network layer, to check the one thing a build cannot: that the
// club admin's MOBILE NUMBER reads and behaves as a mandatory field.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_trial_admin_mobile_browser.mjs [baseUrl]
//
// THE STUB'S validate-admin MIRRORS THE SHIPPED SERVER RULE
// (services/admin_identity.validate_admin_fields called with
// require_mobile=True), including its exact refusal wording — measured by
// running that real function directly, not invented here. What the browser is
// asked is whether the FORM honours it: the marker on the label, the note above
// the fields, the refusal shown under the box, and CONTINUE staying dead until
// a real mobile is typed.
//
// A control run against a build without the change reports the missing parts by
// name rather than dying on the first absent locator, and the split it produces
// is the point: the four PRESENTATION checks fail, while the enforcement ones
// still pass — because the mobile was ALREADY mandatory server-side and only
// nothing on the form said so. The refusal WORDING is the stub's, so the two
// message checks here prove the form renders what the server sends, not what
// the server sends; that half is measured against the real
// admin_identity.validate_admin_fields directly.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

// The server's own rules, copied only so the stub refuses exactly what the real
// one refuses. Keep in step with services/admin_identity.py.
const AU_MOBILE = /^(\+?61|0)4\d{8}$/
const INTL_MOBILE = /^\+\d{8,15}$/
const BLANK_MSG = 'Mobile number is required — an Australian mobile, or an international number starting with +'
const FORMAT_MSG = 'Enter a valid Australian mobile number, or an international number starting with +'

function serverValidate(body) {
  const errors = {}
  const t = (v) => (v || '').trim()
  if (!t(body.first_name)) errors.first_name = 'First name is required'
  if (!t(body.last_name)) errors.last_name = 'Last name is required'
  if (!t(body.display_name)) errors.display_name = 'Preferred display name is required'
  const u = t(body.username).toLowerCase()
  if (!u || u.length < 3 || u.length > 32) errors.username = 'Username must be 3-32 characters'
  const mail = t(body.email).toLowerCase()
  if (!mail || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(mail)) errors.email = 'Enter a valid email address'
  const mobile = t(body.mobile_number)
  const compact = mobile.replace(/[\s-]/g, '')
  if (!mobile) errors.mobile_number = BLANK_MSG
  else if (!AU_MOBILE.test(compact) && !INTL_MOBILE.test(compact)) errors.mobile_number = FORMAT_MSG
  return errors
}

const CLUB = {
  id: '00000000-0000-0000-0000-0000000000aa',
  name: 'Applecross Cricket Club',
  shortName: 'Applecross',
  already_registered: false,
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await ctx.newPage()
const errors = []
const validateCalls = []
page.on('pageerror', (e) => errors.push(String(e)))

await page.route('**/api/**', async (route) => {
  const req = route.request()
  const path = new URL(req.url()).pathname.replace(/^\/api/, '')
  const json = (body, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  if (path === '/public/self-serve/status') return json({ enabled: true, trial_days: 30 })
  if (path === '/public/self-serve/search') return json([CLUB])
  if (path === '/public/self-serve/prepare')
    return json({ org_id: CLUB.id, name: CLUB.name, slug: 'applecross' })
  if (path === '/public/self-serve/validate-admin') {
    const body = JSON.parse(req.postData() || '{}')
    validateCalls.push(body)
    const errs = serverValidate(body)
    return json({
      valid: Object.keys(errs).length === 0,
      errors: errs,
      normalised: { username: (body.username || '').toLowerCase(), email: (body.email || '').toLowerCase() },
    })
  }
  if (path.startsWith('/public/self-serve/track-step')) return json({ ok: true })
  if (path === '/auth/me') return json({ detail: 'no' }, 401)
  return json({})
})

await page.goto(`${BASE}/trial`, { waitUntil: 'networkidle' })

// ── Open the wizard and get to the admin-details step ────────────────────────
// /trial's own path in: search → click the club → "Set up my club" → the wizard
// opens on its club step with that club already selected → CONTINUE.
await page.locator('input[aria-label="Search for your club"]').fill('applecross')
await page.waitForTimeout(800)
const hit = page.locator('button', { hasText: /Applecross Cricket Club/ }).first()
if (await hit.count()) await hit.click()
await page.waitForTimeout(400)

const setUp = page.locator('button', { hasText: /Set up my club/ }).first()
if (await setUp.count()) await setUp.click()
await page.waitForTimeout(1200)

const toAdmin = page.locator('button', { hasText: /^CONTINUE$/ }).first()
if (await toAdmin.count()) await toAdmin.click().catch(() => {})
await page.waitForTimeout(600)

const mobileInput = page.locator('input[type="tel"]').first()
const onAdminStep = await mobileInput.count() > 0
ck('reached the admin-details step', onAdminStep,
   onAdminStep ? '' : 'no tel input found — the wizard did not advance')

if (!onAdminStep) {
  console.log(`\n${pass} passed, ${fail} failed`)
  await browser.close()
  process.exit(fail ? 1 : 0)
}

// ── The field READS as mandatory ─────────────────────────────────────────────
const mobileLabel = page.locator('label', { hasText: /Mobile number/ }).first()
const labelText = (await mobileLabel.count()) ? (await mobileLabel.innerText()).trim() : ''
ck('the mobile label carries a required marker', /\*/.test(labelText), `label read "${labelText}"`)

const stepText = await page.locator('input[type="tel"]').first()
  .evaluate((el) => el.closest('div.space-y-3')?.innerText || '')
ck('the step says every field is required', /every field is required/i.test(stepText),
   `step text: ${JSON.stringify(stepText.slice(0, 120))}`)
ck('and names the mobile among them', /mobile number included/i.test(stepText))

const ariaMobile = await mobileInput.getAttribute('aria-required')
ck('the mobile input is announced as required', ariaMobile === 'true', `aria-required=${ariaMobile}`)

// ── Everything filled EXCEPT the mobile ──────────────────────────────────────
// Address each field through its own label, so a search box elsewhere on the
// page can never be typed into by accident.
const setField = async (label, value) => {
  const handle = page.locator('label', { hasText: label }).first()
  if (!(await handle.count())) return false
  const input = await handle.evaluateHandle((el) => el.parentElement.querySelector('input'))
  const el = input.asElement()
  if (!el) return false
  await el.fill(value)
  return true
}
await setField(/First name/, 'Sam')
await setField(/Last name/, 'Nolan')
await setField(/Email address/, 'sam.nolan@example.com')
await page.waitForTimeout(900)

const contAdmin = page.locator('button', { hasText: /^CONTINUE$/ }).first()
const disabledNoMobile = await contAdmin.isDisabled().catch(() => null)
ck('CONTINUE is dead while the mobile is blank', disabledNoMobile === true,
   `disabled=${disabledNoMobile}`)

const blankErr = await page.locator('p', { hasText: /Mobile number is required/ }).count()
ck('a blank mobile says it is REQUIRED, not that it is mistyped', blankErr > 0)

// ── A mobile that is not a mobile ────────────────────────────────────────────
await mobileInput.fill('(08) 9364 1234')   // a clubroom landline
await page.waitForTimeout(900)
const stillDisabled = await contAdmin.isDisabled().catch(() => null)
ck('a landline does not satisfy it', stillDisabled === true, `disabled=${stillDisabled}`)
const fmtErr = await page.locator('p', { hasText: /Enter a valid Australian mobile/ }).count()
ck('and the refusal changes to the format message', fmtErr > 0)

// ── A real mobile ────────────────────────────────────────────────────────────
await mobileInput.fill('0412 345 678')
await page.waitForTimeout(900)
const nowEnabled = await contAdmin.isDisabled().catch(() => null)
ck('a real mobile unlocks CONTINUE', nowEnabled === false, `disabled=${nowEnabled}`)
ck('the mobile is on the wire exactly as typed',
   validateCalls.some((c) => c.mobile_number === '0412 345 678'),
   JSON.stringify(validateCalls.slice(-1)))

// ── Chrome ───────────────────────────────────────────────────────────────────
ck('no page errors', errors.length === 0, errors.join(' | '))

await page.setViewportSize({ width: 390, height: 900 })
await page.waitForTimeout(300)
const overflow = await page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth)
ck('no horizontal overflow at 390px', overflow <= 0, `overflow ${overflow}px`)

console.log(`\n${pass} passed, ${fail} failed`)
await browser.close()
process.exit(fail ? 1 : 0)
