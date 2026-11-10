// /trial wizard: an earlier admin of a lapsed club registers again with their OWN email.
//
//   npx vite --port 5204 &
//   PW_CHROMIUM=/opt/pw-browsers/chromium node frontend/verification/verify_returning_admin_browser.mjs [baseUrl]
//
// Measured on the real screen, API stubbed at the network layer: the admin-details check carries the
// club (org_id and club_name) on the wire; a returning admin sees the welcome-back note, is never asked
// for a password, the submit button is live without one, the submit sends no password, and they land on
// a "sign in" card and stay on /trial (nothing redirects into /admin); a new person still sees no note,
// both password boxes, a button that waits for a valid password, and is sent on into /admin; 390px.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
async function section(name, fn) {
  try { await fn() } catch (e) { fail++; console.log(`FAIL ${name} did not complete  ${String(e.message || e).split('\n')[0].slice(0, 160)}`) }
}
const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

const CLUB = { id: 'CA-LAPSED', playHQId: 'PH-LAPSED', name: 'Lapsed Cricket Club', already_registered: false }

async function open(email, { width = 1300, returning }) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const seen = { validate: [], submit: [] }
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const u = new URL(req.url())
    const p = u.pathname.replace(/^\/api/, '')
    const json = (b, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(b) })
    const body = () => { try { return JSON.parse(req.postData() || '{}') } catch { return {} } }
    if (/\/auth\/me/.test(p)) return json({ detail: 'no' }, 401)
    if (/public\/self-serve\/status/.test(p)) return json({ enabled: true, default_trial_days: 14 })
    if (/public\/self-serve\/search/.test(p)) return json([CLUB])
    if (/public\/teaser\/by-club/.test(p)) return json({ found: false })
    if (/public\/teaser\//.test(p)) return json({ club: { name: CLUB.name }, claim: { ca_org_id: CLUB.id, name: CLUB.name }, registered: null })
    if (/self-serve\/prepare/.test(p)) return json({ org_id: CLUB.id, name: CLUB.name, short_name: '', slug: 'lapsed-cricket-club' })
    if (/self-serve\/validate-admin/.test(p)) {
      const b = body(); seen.validate.push(b)
      const isReturning = returning && b.email === email
      return json({ valid: true, returning_admin: isReturning, errors: {}, normalised: { username: b.username, email: b.email } })
    }
    if (/verify-email\/send/.test(p)) return json({ sent: true })
    if (/verify-email\/check/.test(p)) return json({ verified: true })
    if (/self-serve\/acknowledge/.test(p)) return json({ accepted: true })
    if (/self-serve\/submit/.test(p)) {
      const b = body(); seen.submit.push(b)
      return json(returning
        ? { status: 'completed', org_id: 'o1', user_id: null, returning_admin: true, redirect: '/login' }
        : { status: 'completed', org_id: 'o1', user_id: 'u1', returning_admin: false, redirect: '/admin' })
    }
    if (/self-serve\/track-step|usage|heartbeat/.test(p)) return json({})
    return json({})
  })
  return { page, ctx, seen }
}

async function walk(page, email) {
  await page.goto(`${BASE}/trial?teaser=TokenForLapsed00001`)
  await page.getByRole('button', { name: 'CONTINUE' }).first().waitFor()        // club prepared
  await page.getByRole('button', { name: 'CONTINUE' }).first().click()
  await page.locator('input[type=email]').waitFor()                              // admin details
  const text = page.locator('input[type=text]')
  await text.nth(0).fill('Ann'); await text.nth(1).fill('Admin')
  await text.nth(2).fill('Ann Admin'); await text.nth(3).fill('ann-admin')
  await page.locator('input[type=email]').fill(email)
  await page.locator('input[type=tel]').fill('0412345678')
  await page.getByText('All details valid').waitFor()
}
async function toSubmitStep(page, email) {
  await page.getByRole('button', { name: 'CONTINUE' }).first().click()
  await page.getByRole('button', { name: 'SEND CODE' }).click()
  await page.locator('input[inputmode=numeric]').fill('1234')
  await page.getByRole('button', { name: 'VERIFY' }).click()
  await page.getByRole('button', { name: 'CONTINUE' }).first().click()
  await page.locator('input[type=checkbox]:not([disabled])').nth(0).check()
  await page.locator('input[type=checkbox]:not([disabled])').nth(1).check()
  await page.getByRole('button', { name: 'CONTINUE' }).first().click()
  await page.getByRole('button', { name: /START 14 DAY FREE TRIAL/ }).waitFor()
}

await section('returning admin', async () => {
  const { page, ctx, seen } = await open('ann@returning.example', { returning: true })
  await walk(page, 'ann@returning.example')
  const last = seen.validate.at(-1) || {}
  ck('the details check carries the club on the wire', last.org_id === 'CA-LAPSED' && last.club_name === 'Lapsed Cricket Club', JSON.stringify(last))
  ck('welcome-back note is shown', await page.getByTestId('returning-admin-note').isVisible())
  ck('the "password is set later" note is replaced, not shown beside it', !(await page.getByText("Password isn't set here").count()))
  await toSubmitStep(page, 'ann@returning.example')
  ck('no password boxes at the submit step', (await page.locator('input[type=password]').count()) === 0
    && (await page.getByTestId('returning-admin-no-password').isVisible()))
  const btn = page.getByRole('button', { name: /START 14 DAY FREE TRIAL/ })
  ck('the submit button is live with no password', await btn.isEnabled())
  await btn.click()
  await page.getByTestId('returning-admin-done').waitFor()
  ck('submit sent no password', seen.submit.length === 1 && !seen.submit[0].password && !seen.submit[0].confirm_password, JSON.stringify(seen.submit[0] && Object.keys(seen.submit[0])))
  ck('shows the sign-in card with a link to /login', (await page.getByText('Your trial has restarted').isVisible())
    && (await page.getByRole('link', { name: 'Go to sign in' }).getAttribute('href')) === '/login')
  await page.waitForTimeout(2200)
  ck('stays on /trial: nothing redirects a signed-out person into /admin', new URL(page.url()).pathname === '/trial', page.url())
  await ctx.close()
})

await section('new person', async () => {
  const { page, ctx, seen } = await open('nina@new.example', { returning: false })
  await walk(page, 'nina@new.example')
  ck('control: no welcome-back note for a new person', (await page.getByTestId('returning-admin-note').count()) === 0
    && (await page.getByText("Password isn't set here").isVisible()))
  await toSubmitStep(page, 'nina@new.example')
  ck('control: both password boxes are there', (await page.locator('input[type=password]').count()) === 2)
  const btn = page.getByRole('button', { name: /START 14 DAY FREE TRIAL/ })
  ck('control: the button waits for a valid password', await btn.isDisabled())
  const pw = page.locator('input[type=password]')
  await pw.nth(0).fill('Str0ng!Passw0rd#1'); await pw.nth(1).fill('Str0ng!Passw0rd#1')
  ck('control: it goes live once the password is valid', await btn.isEnabled())
  await btn.click()
  await page.getByText('Taking you to your dashboard').waitFor()
  ck('control: the password is sent', seen.submit[0]?.password === 'Str0ng!Passw0rd#1')
  await page.waitForFunction(() => location.pathname !== '/trial', null, { timeout: 5000 })
  ck('control: a new person is sent on into the dashboard', /^\/(admin|login)/.test(new URL(page.url()).pathname), page.url())
  await ctx.close()
})

await section('390px', async () => {
  const { page, ctx } = await open('ann@returning.example', { returning: true, width: 390 })
  await walk(page, 'ann@returning.example')
  await toSubmitStep(page, 'ann@returning.example')
  await page.getByRole('button', { name: /START 14 DAY FREE TRIAL/ }).click()
  await page.getByTestId('returning-admin-done').waitFor()
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  const card = await page.getByTestId('returning-admin-done').boundingBox()
  ck('390px: no sideways scroll and the card fits the screen', over <= 0 && card && card.x >= 0 && card.x + card.width <= 390, `overflow ${over} card ${JSON.stringify(card)}`)
  await page.screenshot({ path: process.env.SHOT || '/tmp/returning-admin-390.png' })
  await ctx.close()
})

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
