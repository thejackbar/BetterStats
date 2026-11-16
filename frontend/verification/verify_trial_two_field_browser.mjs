// /trial wizard: the details step asks for first name and email only, the email code goes out on its
// own and checks itself, and the dashboard offers the rest as a prompt the new admin can close.
//
//   npx vite build && npx vite preview --port 5207 &
//   PW_CHROMIUM=/opt/pw-browsers/chromium node frontend/verification/verify_trial_two_field_browser.mjs [baseUrl]
//
// Measured on the real screen, API stubbed at the network layer: the club step has one "Claim <club>"
// button; the details step has exactly two inputs; the details check sends blanks for the fields it no
// longer asks (the server fills them); "Sign-up form opened" is beaconed once with the club; the code
// is sent with no click; a pasted "Code: 1234" is checked by itself and the wizard moves on to Terms;
// every funnel beacon still fires, in order; the dashboard prompt saves through PATCH
// /club-admin/account/profile and "Not now" sends dismiss_nudge; 390px has no sideways scroll.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5207'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SHOTS = process.env.SHOTS || '/tmp'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
async function section(name, fn) {
  try { await fn() } catch (e) { fail++; console.log(`FAIL ${name} did not complete  ${String(e.message || e).split('\n')[0].slice(0, 160)}`) }
}
const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

const CLUB = { id: 'CA-NEW', playHQId: 'PH-NEW', name: 'Brand New Cricket Club', already_registered: false }

async function openWizard({ width = 1300 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const seen = { validate: [], send: [], check: [], steps: [], submit: [] }
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    const json = (b, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(b) })
    const body = () => { try { return JSON.parse(req.postData() || '{}') } catch { return {} } }
    if (/\/auth\/me/.test(p)) return json({ detail: 'no' }, 401)
    if (/public\/self-serve\/status/.test(p)) return json({ enabled: true, default_trial_days: 14 })
    if (/public\/self-serve\/search/.test(p)) return json([CLUB])
    if (/public\/teaser\/by-club/.test(p)) return json({ found: false })
    if (/public\/teaser\//.test(p)) return json({ club: { name: CLUB.name }, claim: { ca_org_id: CLUB.id, name: CLUB.name }, registered: null })
    if (/self-serve\/prepare/.test(p)) return json({ org_id: CLUB.id, name: CLUB.name, short_name: 'Brand New', slug: 'brand-new-cricket-club' })
    if (/self-serve\/validate-admin/.test(p)) {
      const b = body(); seen.validate.push(b)
      const ok = !!(b.first_name || '').trim() && /@/.test(b.email || '')
      return json({ valid: ok, returning_admin: false, errors: ok ? {} : {}, normalised: { username: b.email, email: b.email } })
    }
    if (/verify-email\/send/.test(p)) { seen.send.push(body()); return json({ sent: true }) }
    if (/verify-email\/check/.test(p)) { seen.check.push(body()); return json({ verified: true }) }
    if (/self-serve\/acknowledge/.test(p)) return json({ accepted: true })
    if (/self-serve\/submit/.test(p)) { seen.submit.push(body()); return json({ status: 'completed', org_id: 'o1', user_id: 'u1', returning_admin: false, redirect: '/admin', username: 'sam@club.example' }) }
    if (/self-serve\/track-step/.test(p)) { seen.steps.push(body()); return json({}) }
    return json({})
  })
  await page.goto(`${BASE}/trial?teaser=TokenForNewClub0001`)
  return { page, ctx, seen }
}

await section('two-field sign-up', async () => {
  const { page, ctx, seen } = await openWizard()
  const claim = page.getByTestId('claim-club')
  await claim.waitFor()
  ck('club step: one Claim button naming the club', (await claim.innerText()).trim() === 'Claim Brand New', await claim.innerText())
  ck('club step: sets the time expectation', await page.getByText('About a minute · free · no card').isVisible())
  ck('club step: no second CONTINUE competing in the footer', (await page.getByRole('button', { name: 'CONTINUE' }).count()) === 0)
  ck('control: Sign-up form opened is not sent before the form is on screen', !seen.steps.some((s) => s.step === 'signup_form_opened'))
  await claim.click()

  await page.getByLabel('First name').waitFor()
  const inputs = page.locator('[role=dialog] input:visible:not([type=checkbox])')
  ck('details step: exactly two inputs', (await inputs.count()) === 2, String(await inputs.count()))
  ck('details step: no mobile, username or surname box', (await page.locator('[role=dialog] input[type=tel]').count()) === 0
    && (await page.getByLabel('Username').count()) === 0 && (await page.getByLabel('Last name').count()) === 0)
  ck('details step: first name has the focus', await page.getByLabel('First name').evaluate((el) => el === document.activeElement))
  await page.waitForTimeout(150)
  const opened = seen.steps.filter((s) => s.step === 'signup_form_opened')
  ck('Sign-up form opened is beaconed once, with the club', opened.length === 1 && opened[0].club_name === CLUB.name && opened[0].club_org_id === CLUB.id, JSON.stringify(opened))

  await page.getByLabel('First name').fill('Sam')
  await page.getByLabel('Email address').fill('sam@club.example')
  await page.getByText('All details valid').waitFor()
  const last = seen.validate.at(-1) || {}
  ck('the details check sends blanks for what it no longer asks',
    last.first_name === 'Sam' && last.email === 'sam@club.example' && last.last_name === '' && last.display_name === ''
    && last.username === '' && last.mobile_number === '', JSON.stringify(last))
  ck('control: nothing sent the code before Continue', seen.send.length === 0)
  await page.getByRole('button', { name: 'CONTINUE' }).click()

  const code = page.locator('input[inputmode=numeric]')
  await code.waitFor()
  ck('the code is sent with no click, once', seen.send.length === 1 && seen.send[0].email === 'sam@club.example', JSON.stringify(seen.send))
  ck('no SEND CODE button to press', (await page.getByRole('button', { name: 'SEND CODE', exact: true }).count()) === 0)
  ck('the code box has the focus', await code.evaluate((el) => el === document.activeElement))
  ck('the code box offers one-time-code autofill', (await code.getAttribute('autocomplete')) === 'one-time-code')
  await code.focus()
  await page.evaluate(() => {
    const dt = new DataTransfer(); dt.setData('text/plain', 'Code: 1234')
    document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }))
  })
  // Chromium does not insert text for a synthetic paste event, so also type what a paste inserts.
  if (!(await code.inputValue())) await code.fill('Code: 1234')
  await page.locator('[role=dialog] input[type=checkbox]:not([disabled])').first().waitFor()
  ck('pasted text is checked by itself as the 4 digits', seen.check.length === 1 && seen.check[0].code === '1234', JSON.stringify(seen.check))
  ck('the wizard moved on to Terms by itself', await page.getByText('Privacy Policy').isVisible())

  const boxes = page.locator('[role=dialog] input[type=checkbox]:not([disabled])')
  for (let i = 0; i < await boxes.count(); i++) await boxes.nth(i).check()
  await page.getByRole('button', { name: 'CONTINUE' }).click()
  const pw = page.locator('input[type=password]')
  await pw.nth(0).fill('Str0ng!Passw0rd#1'); await pw.nth(1).fill('Str0ng!Passw0rd#1')
  await page.evaluate(() => { window.location.assign = () => {} })
  await page.getByRole('button', { name: /START 14 DAY FREE TRIAL/ }).click()
  await page.getByText('Taking you to your dashboard').waitFor()
  await page.waitForTimeout(200)
  const sub = seen.submit[0] || {}
  ck('submit sends first name, email and password; honeypot, idempotency key and attribution intact',
    sub.first_name === 'Sam' && sub.email === 'sam@club.example' && sub.password === 'Str0ng!Passw0rd#1'
    && 'website' in sub && !!sub.idempotency_key && typeof sub.form_started_at === 'number' && 'attribution' in sub, JSON.stringify(Object.keys(sub)))
  const order = seen.steps.map((s) => s.step).filter((s) => s !== 'club_searched')
  const want = ['club_prepared', 'signup_form_opened', 'admin_details_completed', 'email_code_sent', 'email_verified',
    'acknowledgements_accepted', 'submit_attempted', 'registration_completed']
  ck('every funnel beacon fires, in order', JSON.stringify(order) === JSON.stringify(want), JSON.stringify(order))
  await ctx.close()
})

await section('390px', async () => {
  const { page, ctx } = await openWizard({ width: 390 })
  await page.getByTestId('claim-club').waitFor()
  let over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px club step: no sideways scroll', over <= 0, String(over))
  await page.screenshot({ path: `${SHOTS}/trial-claim-390.png` })
  await page.getByTestId('claim-club').click()
  await page.getByLabel('First name').waitFor()
  over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px details step: no sideways scroll', over <= 0, String(over))
  await page.screenshot({ path: `${SHOTS}/trial-details-390.png` })
  await ctx.close()
})

async function openDashboard({ nudge = true, width = 1300, patchStatus = 200 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const patches = []
  let profile = { username: 'sam@club.example', email: 'sam@club.example', first_name: 'Sam', last_name: '', display_name: 'Sam', mobile_number: '', nudge }
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    const method = req.method()
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p === '/auth/me') {
      return json({
        id: 'u1', username: 'sam@club.example', display_name: 'Sam', role: 'club_admin', club_id: 'c1',
        club_slug: 'brand-new', is_primary_admin: true, can_switch_clubs: false,
        entitlements: { modules: [], status: 'trial', billing_modules: [] }, capabilities: [],
      })
    }
    if (p === '/club-admin/account/profile' && method === 'GET') return json(profile)
    if (p === '/club-admin/account/profile' && method === 'PATCH') {
      const b = JSON.parse(req.postData() || '{}'); patches.push(b)
      if (patchStatus !== 200) return json({ detail: { errors: { mobile_number: 'Enter a valid Australian mobile number' } } }, patchStatus)
      profile = { ...profile, ...b, nudge: false }
      delete profile.dismiss_nudge
      return json(profile)
    }
    if (p === '/club-admin/broadcasts') return json({ items: [], preview: false })
    if (p === '/club-admin/settings') return json({ name: 'Brand New Cricket Club', slug: 'brand-new' })
    if (p === '/club-admin/seasons') return json([])
    if (p === '/club-admin/account/plan') return json({ modules: [] })
    if (/(module-requests|sync-logs|bookmarks)$/.test(p)) return json([])
    if (p === '/club-admin/onboarding-wizard/flow') return json({ groups: [] })
    return json({})
  })
  page.on('pageerror', (e) => console.log(`  page error: ${e.message}`))
  await page.goto(`${BASE}/admin`)
  return { page, ctx, patches }
}

await section('dashboard prompt', async () => {
  const { page, ctx, patches } = await openDashboard()
  const card = page.getByTestId('profile-nudge')
  await card.waitFor()
  ck('the prompt shows, with the sign-in name', (await card.innerText()).includes('sam@club.example'))
  ck('it says it is optional', (await card.innerText()).includes('Optional. Your trial is already running.'))
  await page.getByLabel('Last name').fill('Smith')
  await page.getByLabel(/^Mobile/).fill('0412 345 678')
  await page.getByRole('button', { name: 'SAVE' }).click()
  await page.getByTestId('profile-nudge-done').waitFor()
  ck('save sends the details on the wire', patches.length === 1 && patches[0].last_name === 'Smith'
    && patches[0].mobile_number === '0412 345 678' && patches[0].display_name === 'Sam' && !patches[0].dismiss_nudge, JSON.stringify(patches))
  await page.getByRole('button', { name: 'Close' }).last().click()
  ck('after saving, closing leaves no card', (await page.getByTestId('profile-nudge').count()) === 0 && (await page.getByTestId('profile-nudge-done').count()) === 0)
  await ctx.close()
})

await section('dashboard prompt: Not now', async () => {
  const { page, ctx, patches } = await openDashboard()
  await page.getByTestId('profile-nudge').waitFor()
  await page.getByRole('button', { name: 'Not now' }).click()
  await page.waitForTimeout(200)
  ck('Not now sends dismiss_nudge only', patches.length === 1 && patches[0].dismiss_nudge === true && Object.keys(patches[0]).length === 1, JSON.stringify(patches))
  ck('and the card goes away', (await page.getByTestId('profile-nudge').count()) === 0)
  await ctx.close()
})

await section('dashboard prompt: refused mobile', async () => {
  const { page, ctx } = await openDashboard({ patchStatus: 422 })
  await page.getByTestId('profile-nudge').waitFor()
  await page.getByLabel(/^Mobile/).fill('12')
  await page.getByRole('button', { name: 'SAVE' }).click()
  await page.getByText('Enter a valid Australian mobile number').waitFor()
  ck('a refused mobile shows under the box and the card stays', await page.getByTestId('profile-nudge').isVisible())
  await ctx.close()
})

await section('dashboard: no prompt when not pending', async () => {
  const { page, ctx } = await openDashboard({ nudge: false })
  await page.getByText('Welcome, Sam').waitFor()
  await page.waitForTimeout(300)
  ck('control: an admin with nothing pending sees no card', (await page.getByTestId('profile-nudge').count()) === 0)
  await ctx.close()
})

await section('dashboard prompt 390px', async () => {
  const { page, ctx } = await openDashboard({ width: 390 })
  await page.getByTestId('profile-nudge').waitFor()
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: the prompt causes no sideways scroll', over <= 0, String(over))
  await page.getByTestId('profile-nudge').screenshot({ path: `${SHOTS}/profile-nudge-390.png` })
  await ctx.close()
})

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
