// Drives the real Fantasy sign-in screen in Chromium with the API stubbed at the network layer.
//
//   npx vite build && npx vite preview --port 5198 &
//   node frontend/verification/verify_fantasy_forgot_pin_browser.mjs [baseUrl]
//
// Checks: "Forgot your PIN?" is offered on Sign in and not on New player; it swaps the PIN box for an email-only
// form; the exact request on the wire (one POST /forgot-pin with just the email); the sent notice names the address
// and does not claim the address is registered; a refused request (no email set up, 502, 429) is shown with its
// reason and the form stays; Back to sign in returns to the normal form and a normal sign in still sends email + PIN;
// no overflow at 390px; no page errors.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SHOTS = process.env.SHOTS_DIR || ''

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  - ${extra}` : ''}`) }
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1280, forgotStatus = 200, forgotDetail = '' } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  const errors = [], posts = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace(/^\/api/, '')
    if (path === '/public/fantasy/tok') return json(route, { club: { name: 'Applecross CC' }, season: { name: 'Fantasy', status: 'open', registration_open: true, rules: {} }, me: null })
    if (req.method() === 'POST' && path.startsWith('/public/fantasy/tok/')) {
      posts.push({ path, body: req.postDataJSON() })
      if (path.endsWith('/forgot-pin')) return forgotStatus === 200 ? json(route, { status: 'sent' }) : json(route, { detail: forgotDetail }, forgotStatus)
      if (path.endsWith('/login')) return json(route, { detail: 'That email and PIN didn\'t match.' }, 401)
    }
    return json(route, {})
  })
  await page.goto(`${BASE}/fantasy/tok`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Sign in', exact: true }).first().click({ timeout: 15000 })
  return { page, ctx, errors, posts }
}

const body = (page) => page.locator('body').innerText()
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)

// ── 1. Where it is offered ────────────────────────────────────────────────────
{
  const { page, ctx, errors } = await open()
  ck('Sign in offers Forgot your PIN?', await page.getByRole('button', { name: 'Forgot your PIN?' }).count() === 1)
  ck('Sign in still has the PIN box', await page.getByPlaceholder('PIN (4+ digits)').count() === 1)
  await page.getByRole('button', { name: 'New player', exact: true }).click()
  ck('New player does not offer it', await page.getByRole('button', { name: 'Forgot your PIN?' }).count() === 0)
  await page.getByRole('button', { name: 'Sign in', exact: true }).first().click()

  // ── 2. The forgot form ──────────────────────────────────────────────────────
  await page.getByRole('button', { name: 'Forgot your PIN?' }).click()
  ck('the PIN box is gone', await page.getByPlaceholder('PIN (4+ digits)').count() === 0)
  ck('it asks for the email only', await page.getByPlaceholder('Email').count() === 1)
  ck('it says the old PIN will stop working', /old one will stop working/i.test(await body(page)))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/forgot-form.png` })
  ck('no page errors so far', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── 3. Sending ────────────────────────────────────────────────────────────────
{
  const { page, ctx, posts } = await open()
  await page.getByRole('button', { name: 'Forgot your PIN?' }).click()
  await page.getByPlaceholder('Email').fill('xavier@example.com')
  await page.getByRole('button', { name: 'Email me a new PIN' }).click()
  await page.getByText('is on its way').waitFor({ timeout: 8000 })
  ck('exactly one POST went to /forgot-pin', posts.length === 1 && posts[0].path === '/public/fantasy/tok/forgot-pin', JSON.stringify(posts))
  ck('the body is only the email', JSON.stringify(posts[0]?.body) === JSON.stringify({ email: 'xavier@example.com' }), JSON.stringify(posts[0]?.body))
  const t = await body(page)
  ck('the notice names the address and hedges on it having a team', /If xavier@example\.com has a team here/.test(t))
  ck('it tells them to change the PIN under Settings', /under Settings/.test(t))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/forgot-sent.png` })
  await page.getByRole('button', { name: 'Back to sign in' }).click()
  ck('Back to sign in restores the PIN box', await page.getByPlaceholder('PIN (4+ digits)').count() === 1)
  await page.getByPlaceholder('Email').fill('xavier@example.com')
  await page.getByPlaceholder('PIN (4+ digits)').fill('123456')
  await page.getByRole('button', { name: 'Sign in', exact: true }).last().click()
  await page.waitForTimeout(600)
  const login = posts.find(p => p.path.endsWith('/login'))
  ck('a normal sign in still sends email and PIN to /login', JSON.stringify(login?.body) === JSON.stringify({ email: 'xavier@example.com', pin: '123456' }), JSON.stringify(login))
  ck('a wrong PIN is shown', /didn't match/.test(await body(page)))
  await ctx.close()
}

// ── 4. Refusals are readable and keep the form ───────────────────────────────
for (const [status, detail] of [
  [503, "Email isn't set up for this club yet, so a new PIN can't be sent. Ask your club admin to reset it."],
  [502, "We couldn't send the email just now. Your PIN hasn't changed. Please try again shortly."],
  [429, 'Too many PIN emails for this address. Please try again later.'],
]) {
  const { page, ctx } = await open({ forgotStatus: status, forgotDetail: detail })
  await page.getByRole('button', { name: 'Forgot your PIN?' }).click()
  await page.getByPlaceholder('Email').fill('xavier@example.com')
  await page.getByRole('button', { name: 'Email me a new PIN' }).click()
  await page.getByText(detail).waitFor({ timeout: 8000 }).catch(() => {})
  const t = await body(page)
  ck(`${status}: the reason is on screen`, t.includes(detail))
  ck(`${status}: no "on its way" notice`, !/is on its way/.test(t))
  ck(`${status}: the form is still there to try again`, await page.getByRole('button', { name: 'Email me a new PIN' }).count() === 1)
  await ctx.close()
}

// ── 5. Phone width ────────────────────────────────────────────────────────────
{
  const { page, ctx, errors } = await open({ width: 390 })
  await page.getByRole('button', { name: 'Forgot your PIN?' }).click()
  ck('390px: forgot form does not overflow', !(await overflow(page)))
  await page.getByPlaceholder('Email').fill('a-rather-long-address-for-a-phone@example.com')
  await page.getByRole('button', { name: 'Email me a new PIN' }).click()
  await page.getByText('is on its way').waitFor({ timeout: 8000 })
  ck('390px: sent notice with a long address does not overflow', !(await overflow(page)))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/forgot-sent-390.png` })
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
