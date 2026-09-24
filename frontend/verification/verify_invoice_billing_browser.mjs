// Pay by invoice (migration 308), driven in Chromium against the real Account
// page and the Super Admin's per-club Invoice modal, with the API stubbed at
// the network layer.
//
//   npx vite --port 5199 &
//   node verification/verify_invoice_billing_browser.mjs [baseUrl]
//
// The checks read what went ON THE WIRE — which endpoint, which modules, which
// code — not only what the screen says, because "the invoice was requested for
// the right modules" is not something a rendered page can prove.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const ORG = '11111111-1111-4111-8111-111111111111'
const TRIAL_END = '2026-10-03T02:00:00+00:00'
const MODULES = ['core', 'select', 'socials', 'admin', 'iq', 'fantasy'].map((m) => ({
  module: m, name: { core: 'BetterStats', select: 'BetterSelect', socials: 'BetterSocials', admin: 'BetterAdmin', iq: 'BetterIQ', fantasy: 'BetterFantasyCricket' }[m],
  status: 'trial', renewal_date: null, trial_ends_at: TRIAL_END, trial_eligible: false, can_subscribe: true, pending_requests: [],
}))
const PRICES = { core: 399, select: 149, socials: 149, admin: 149, iq: 249, fantasy: 49 }
const NAMES = Object.fromEntries(MODULES.map((m) => [m.module, m.name]))

const OPEN_INVOICE = {
  id: 'inv-row-1', invoice_number: 'BC-1042', invoice_kind: 'initial', status: 'open',
  billing_keys: ['core', 'select'], line_items: [{ name: 'BetterCricket — BetterStats', price: 399 }, { name: 'BetterCricket — BetterSelect', price: 149 }],
  bundle_discount_cents: 0, coupon_code: null, coupon_discount_cents: 0, amount_total_cents: 60280,
  service_start_date: '2026-10-03', service_end_date: '2027-10-03', due_at: TRIAL_END,
  pay_url: 'https://betterat.cricket/api/public/billing/pay/tok123', invoice_pdf: 'https://invoice.stripe.test/in_1.pdf',
  sent_to_email: 'pat@club.test', emailed_at: '2026-09-23T03:00:00+00:00', email_error: null, created_at: '2026-09-23T03:00:00+00:00',
}

// A price plan in plan_out's shape, worked out the way the server does for a
// first invoice (Core forced in, the default bundle schedule, a code last).
function planFor(keys, code) {
  const priced = [...new Set([...keys, 'core'])]
  const bundleCount = priced.filter((k) => ['select', 'socials', 'admin', 'iq'].includes(k)).length
  const discount = { 0: 0, 1: 0, 2: 48, 3: 97, 4: 146 }[bundleCount]
  const subtotal = priced.reduce((a, k) => a + PRICES[k], 0)
  const coupon = code ? { code: code.toUpperCase(), display_name: 'Ten percent', amount_off: Math.round((subtotal - discount) * 10) / 100 } : null
  return {
    mode: 'invoice', kind: 'initial', billing_keys: priced,
    line_items: priced.map((k) => ({ key: k, name: NAMES[k], full_price: PRICES[k], amount: PRICES[k] })),
    subtotal, discount, coupon, total: subtotal - discount - (coupon?.amount_off || 0),
    service_start_date: '2026-10-03', service_end_date: '2027-10-03', prorated: null, due_at: TRIAL_END,
  }
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openAccount({ width = 1440, method = 'card', primary = false, query = '', offered = true } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const state = { method, open: [] }
  const overview = () => ({
    billing_method: state.method, can_use_invoice: true, invoice_billing_enabled: offered,
    primary_admin: { name: 'Pat Primary', email: 'pat@club.test' }, email_live: true,
    period: null, open_invoices: state.open, renewal_notice_days: 14,
  })

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace(/^\/api/, '')
    const verb = req.method()
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    let payload = null
    try { payload = req.postDataJSON() } catch { payload = null }
    if (!/^\/usage\//.test(path)) calls.push({ path, method: verb, payload })

    if (/^\/auth\/me/.test(path)) {
      return json({ id: 'u2', username: 'sam', role: 'club_admin', capabilities: ['*'], club_slug: 'invoice-cc',
        club_id: ORG, entitlements: { modules: ['stats'], status: 'active' } })
    }
    if (path === '/club-admin/account/plan') {
      return json({ modules: MODULES, is_primary_admin: primary, is_club_admin: true, billing_checkout_enabled: true,
        stripe_subscription_active: false, stripe_customer_id: false, billing_method: state.method,
        invoice_billing_enabled: offered })
    }
    if (path === '/club-admin/billing/invoice-billing') return json(overview())
    if (path === '/club-admin/billing/billing-method' && verb === 'PUT') { state.method = payload.method; return json(overview()) }
    if (path === '/club-admin/billing/quote') {
      if (state.method !== 'invoice') return json({ mode: 'new_subscription', ...planFor(payload.module_keys, null), mode: 'new_subscription' })
      if (payload.coupon_code && payload.coupon_code.toUpperCase() !== 'TENOFF') return json({ detail: "That code isn't valid" }, 422)
      return json(planFor(payload.module_keys, payload.coupon_code))
    }
    if (path === '/club-admin/billing/invoices/request') {
      state.open = [OPEN_INVOICE]
      return json({ invoice: OPEN_INVOICE, emailed: true, email_error: null })
    }
    if (/\/club-admin\/billing\/invoices\/[^/]+\/resend$/.test(path)) return json({ ok: true, error: null, to: 'pat@club.test', invoice: OPEN_INVOICE })
    if (path === '/club-admin/billing/invoices') return json(state.open)
    if (path === '/club-admin/billing/payment-methods') return json({ default_payment_method_id: null, payment_methods: [] })
    if (/primary-admin/.test(path)) return json({ admins: [{ display_name: 'Pat Primary', is_primary_admin: true }] })
    if (/notifications\/count/.test(path)) return json({ unseen_count: 0 })
    return json({})
  })

  await page.goto(`${BASE}/admin/account${query}`, { waitUntil: 'domcontentloaded' })
  // The page's own heading — 'BetterSelect' also appears in the sidebar, which
  // is a closed drawer at phone width and never becomes visible.
  await page.waitForSelector('h1:has-text("Account")', { timeout: 30000 })
  await page.waitForSelector('main >> text=BetterSelect', { timeout: 30000 }).catch(() => {})
  await page.waitForTimeout(600)
  return { page, ctx, errors, calls, state }
}

// Every interaction with something this change ADDS goes through press/fill,
// which report absence instead of throwing — a control run against a build
// without the feature must report each missing part, not die on the first one.
const press = async (loc) => { if (await loc.count()) { await loc.first().click({ timeout: 5000 }).catch(() => {}); return true } return false }
const fillIn = async (loc, v) => { if (await loc.count()) { await loc.first().fill(v, { timeout: 5000 }).catch(() => {}); return true } return false }
const text = async (loc) => ((await loc.count()) ? (await loc.first().innerText()).trim() : '')
const byTestId = (page, id) => page.locator(`[data-testid="${id}"]`)
const moduleBox = (page, name) => page.locator('.pb-card', { hasText: name }).locator('input[type="checkbox"]').first()

{
  console.log('\nA club nobody has offered invoicing to (the default)')
  const { page, ctx, errors, calls } = await openAccount({ offered: false })
  ck('sees no invoicing option at all', (await byTestId(page, 'billing-method').count()) === 0)
  ck('and nothing about invoices anywhere on the page', (await page.locator('text=Pay by invoice').count()) === 0)
  await moduleBox(page, 'BetterSelect').check().catch(() => {})
  await page.waitForTimeout(400)
  ck('a non-primary admin still cannot subscribe', (await page.locator('text=Only your club\'s Primary Admin User can subscribe').count()) === 1)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  console.log('\nA club a Super Admin has offered invoicing to, still paying by card')
  const { page, ctx, errors, calls } = await openAccount({ primary: true, offered: true, method: 'card' })
  ck('sees no invoicing option — only a Super Admin can put a club on it',
    (await byTestId(page, 'billing-method').count()) === 0 && (await page.locator('text=Pay by invoice').count()) === 0)
  await moduleBox(page, 'BetterSelect').check().catch(() => {})
  await page.waitForTimeout(700)
  ck('the Primary Admin still gets the ordinary card checkout',
    (await page.getByRole('button', { name: /PROCEED TO SECURE CHECKOUT/ }).count()) === 1)
  ck('and nothing asks to switch how the club pays', !calls.some((c) => c.path === '/club-admin/billing/billing-method'))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  console.log('\nA club BetterCricket has put on invoice billing')
  const { page, ctx, errors, calls, state } = await openAccount({ primary: true, method: 'invoice' })
  state.open = [OPEN_INVOICE]
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('[data-testid="open-invoices"]', { timeout: 20000 }).catch(() => {})
  await page.waitForTimeout(600)
  const card = byTestId(page, 'billing-method')
  ck('the page says the club pays by invoice', (await card.count()) === 1 && (await text(card)).includes('Pay by invoice'), await text(card))
  ck('it is a statement, not a choice (no radio buttons)', (await card.locator('input[type="radio"]').count()) === 0)
  ck('it says BetterCricket manages it and how to ask for a change',
    (await text(card)).includes('BetterCricket manages') && (await text(card)).includes('support@bettersports.com.au'), await text(card))
  ck('it says who invoices go to', (await text(card)).includes('Pat Primary'), await text(card))
  ck('even the Primary Admin gets no module checkboxes to pick from',
    (await page.locator('main .pb-card input[type="checkbox"]').count()) === 0)
  ck('and no CANCEL on a module', (await page.getByRole('button', { name: 'CANCEL' }).count()) === 0)
  ck('there is no button to raise an invoice', (await page.getByRole('button', { name: /EMAIL INVOICE/ }).count()) === 0)

  const open = byTestId(page, 'open-invoices')
  ck('an invoice to pay is listed', (await open.count()) === 1 && (await text(open)).includes('BC-1042'), await text(open))
  const pay = open.getByRole('link', { name: 'PAY NOW' })
  const payHref = (await pay.count()) ? await pay.getAttribute('href').catch(() => '') : ''
  ck('with a PAY NOW link to the invoice\'s pay page', payHref === OPEN_INVOICE.pay_url, payHref)
  const pdf = open.getByRole('link', { name: 'DOWNLOAD PDF' })
  ck('and its PDF', ((await pdf.count()) ? await pdf.getAttribute('href').catch(() => '') : '') === OPEN_INVOICE.invoice_pdf)
  ck('it shows the GST-inclusive total and the due date', /\$602\.80 incl\. GST/.test(await text(open)) && /Due by 3 Oct 2026/.test(await text(open)))
  await press(open.getByRole('button', { name: 'EMAIL IT AGAIN' }))
  await page.waitForTimeout(600)
  ck('the club can still have it emailed again', calls.some((c) => c.path === '/club-admin/billing/invoices/inv-row-1/resend' && c.method === 'POST'))
  ck('nothing on the page raised an invoice or changed how the club pays',
    !calls.some((c) => c.path === '/club-admin/billing/invoices/request' || c.path === '/club-admin/billing/billing-method'))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  console.log('\nArriving from a paid invoice\'s email link')
  const { page, ctx, errors } = await openAccount({ method: 'invoice', query: '?invoice=paid' })
  ck('the page says the invoice is paid', (await page.locator('text=That invoice is paid').count()) === 1)
  ck('and tidies the address', !page.url().includes('invoice='), page.url())
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  console.log('\nOn a phone')
  const { page, ctx, state } = await openAccount({ method: 'invoice', width: 390 })
  state.open = [OPEN_INVOICE]
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('[data-testid="open-invoices"]', { timeout: 20000 }).catch(() => {})
  await moduleBox(page, 'BetterSelect').check().catch(() => {})
  await page.waitForTimeout(700)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('nothing overflows at 390px', overflow <= 0, `${overflow}px`)
  await ctx.close()
}

// ─── The Super Admin modal ───────────────────────────────────────────────────
{
  console.log('\nA Super Admin raises an invoice on a club\'s behalf')
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1400 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const club = { id: ORG, name: 'Helped CC', slug: 'helped-cc', is_active: true, module_overrides: [], modules: [] }
  const st = { method: 'card', open: [], offered: false }
  const ov = () => ({
    billing_method: st.method, can_use_invoice: true, invoice_billing_enabled: st.offered, primary_admin: { name: 'Pat Primary', email: 'pat@club.test' },
    email_live: true, renewal_notice_days: 14, open_invoices: st.open, modules: MODULES,
    period: { billing_keys: ['core'], renewal_date: '2027-03-01', ends_at: '2027-02-28T15:59:59+00:00', renewal_invoice_on: '2027-02-15', renewal_invoice: null },
  })
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace(/^\/api/, '')
    const verb = req.method()
    let payload = null
    try { payload = req.postDataJSON() } catch { payload = null }
    if (!/^\/usage\//.test(path)) calls.push({ path, method: verb, payload })
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/^\/auth\/me/.test(path)) return json({ id: 'sa', username: 'super', role: 'super_admin', capabilities: ['*'], entitlements: { modules: [], status: 'active' } })
    if (/^\/club-admin\/super\/clubs$/.test(path)) return json([club])
    if (path === `/club-admin/super/clubs/${ORG}` && verb === 'PATCH') { st.offered = !!payload.invoice_billing_enabled; return json({ ...club, invoice_billing_enabled: st.offered }) }
    const base = `/club-admin/billing/super/clubs/${ORG}`
    if (path === `${base}/invoice-billing`) return json(ov())
    if (path === `${base}/invoice-quote`) {
      if (payload.coupon_code && payload.coupon_code.toUpperCase() !== 'TENOFF') return route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: "That code isn't valid" }) })
      return json(planFor(payload.module_keys, payload.coupon_code))
    }
    if (path === `${base}/invoices`) { st.method = 'invoice'; st.open = [OPEN_INVOICE]; return json({ invoice: OPEN_INVOICE, emailed: true, email_error: null }) }
    if (path === `${base}/renewal-invoice`) return json({ invoice: { ...OPEN_INVOICE, invoice_kind: 'renewal' }, emailed: true, email_error: null })
    if (path === `${base}/invoices/inv-row-1/resend`) return json({ ok: true, error: null, to: 'pat@club.test', invoice: OPEN_INVOICE })
    if (path === `${base}/invoices/inv-row-1/void`) { st.open = []; return json({ invoice: { ...OPEN_INVOICE, status: 'void' } }) }
    if (/^\/club-admin\/super\/(general-settings|trials)/.test(path)) return json({})
    return json(/list|clubs|admins/.test(path) ? [] : {})
  })
  page.on('dialog', (d) => d.accept())
  await page.goto(`${BASE}/admin/super/clubs`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('text=Helped CC', { timeout: 30000 }).catch(() => {})
  const invBtn = page.getByRole('button', { name: 'Invoice', exact: true })
  ck('each club has an Invoice action', (await invBtn.count()) > 0)
  if (await invBtn.count()) await invBtn.first().click()
  await page.waitForSelector('text=Raise an invoice', { timeout: 15000 }).catch(() => {})
  await page.waitForSelector('[data-testid="invoice-offer"]', { timeout: 15000 }).catch(() => {})
  ck('the modal opens on the club', (await page.locator('text=Helped CC — invoicing').count()) === 1)
  ck('invoicing starts switched off', (await page.locator('[data-testid="invoice-offer"] input').isChecked().catch(() => true)) === false)
  ck('and nothing can be raised until it is on', (await page.getByText('Raise an invoice', { exact: true }).count()) === 0)
  await page.locator('[data-testid="invoice-offer"] input').click().catch(() => {})
  await page.waitForTimeout(700)
  const offer = calls.find((c) => c.path === `/club-admin/super/clubs/${ORG}` && c.method === 'PATCH')
  ck('switching it on is a PATCH to the club, from All Clubs', offer?.payload?.invoice_billing_enabled === true, JSON.stringify(offer?.payload))
  await page.waitForSelector('text=Raise an invoice', { timeout: 10000 }).catch(() => {})
  ck('then the invoicing tools appear', (await page.getByText('Raise an invoice', { exact: true }).count()) > 0)
  const modal = page.locator('div.pb-card', { hasText: 'Raise an invoice' }).last()
  const lines = () => page.locator('[data-testid="invoice-line"]').count()
  ck('the draft invoice is on screen before anything is picked', (await byTestId(page, 'invoice-preview').count()) === 1
    && (await byTestId(page, 'invoice-preview-empty').count()) === 1)
  ck('it is addressed to the Primary Club Admin', /Pat Primary.*pat@club\.test/.test(await text(byTestId(page, 'invoice-preview'))))
  ck('the discount code box is there before a module is picked', (await byTestId(page, 'invoice-coupon').count()) === 1)
  await modal.locator('label', { hasText: 'BetterSelect' }).locator('input').check().catch(() => {})
  await page.waitForTimeout(700)
  const oneLine = await lines()
  ck('ticking one module draws Core and that module', oneLine === 2, `${oneLine} lines`)
  ck('with no bundle discount yet', !/Bundle discount/.test(await text(byTestId(page, 'invoice-quote'))))
  await modal.locator('label', { hasText: 'BetterSocials' }).locator('input').check().catch(() => {})
  await page.waitForTimeout(700)
  ck('ticking a second updates the invoice live', (await lines()) === 3, `${await lines()} lines`)
  ck('it prices the invoice', /Bundle discount\s*-\$48\.00/.test(await text(byTestId(page, 'invoice-quote'))), await text(byTestId(page, 'invoice-quote')))
  ck('and shows GST and the total', /GST 10%/.test(await text(byTestId(page, 'invoice-quote'))) && /Total/.test(await text(byTestId(page, 'invoice-quote'))))
  const quotesSoFar = calls.filter((c) => c.path === `/club-admin/billing/super/clubs/${ORG}/invoice-quote`).length
  ck('each pick asked the server to price it', quotesSoFar >= 2, `${quotesSoFar} quote calls`)

  await byTestId(page, 'invoice-coupon').fill('WRONG').catch(() => {})
  await page.getByRole('button', { name: 'APPLY' }).click().catch(() => {})
  await page.waitForTimeout(900)
  ck('a code the server refuses says why', /isn't valid/.test(await text(byTestId(page, 'invoice-coupon-error'))))
  ck('and the invoice is still drawn without it', (await lines()) === 3 && (await byTestId(page, 'invoice-coupon-line').count()) === 0)
  await page.getByRole('button', { name: 'REMOVE' }).click().catch(() => {})
  await byTestId(page, 'invoice-coupon').fill('tenoff').catch(() => {})
  await byTestId(page, 'invoice-coupon').press('Enter').catch(() => {})
  await page.waitForTimeout(900)
  const couponCall = calls.filter((c) => c.path === `/club-admin/billing/super/clubs/${ORG}/invoice-quote`).pop()
  ck('a code is sent with the selection to be priced', couponCall?.payload?.coupon_code === 'tenoff', JSON.stringify(couponCall?.payload))
  ck('and appears on the invoice as a discount', /TENOFF/.test(await text(byTestId(page, 'invoice-coupon-line'))), await text(byTestId(page, 'invoice-quote')))
  ck('the total drops by it', /\$64\.90/.test(await text(byTestId(page, 'invoice-coupon-line'))), await text(byTestId(page, 'invoice-coupon-line')))
  ck('and says raising it moves the club to invoice billing', (await page.locator('text=Raising an invoice moves this club to invoice billing').count()) === 1)
  await page.getByRole('button', { name: /EMAIL INVOICE TO PAT PRIMARY/ }).click().catch(() => {})
  await page.waitForTimeout(800)
  const req = calls.find((c) => c.path === `/club-admin/billing/super/clubs/${ORG}/invoices`)
  ck('the Super Admin raises it for that club by id', req?.method === 'POST'
    && ['select', 'socials'].every((k) => req.payload.module_keys.includes(k)), JSON.stringify(req?.payload))
  ck('the code goes with it', req?.payload?.coupon_code === 'tenoff', JSON.stringify(req?.payload))
  ck('the open invoice is listed with its pay link', (await page.getByRole('link', { name: 'PAY NOW' }).count()) === 1)
  await page.getByRole('button', { name: 'SEND RENEWAL INVOICE NOW' }).click().catch(() => {})
  await page.waitForTimeout(700)
  ck('the renewal can be sent early, after a confirm', calls.some((c) => c.path === `/club-admin/billing/super/clubs/${ORG}/renewal-invoice`))
  await page.getByRole('button', { name: 'EMAIL IT AGAIN' }).click().catch(() => {})
  await page.waitForTimeout(700)
  ck('an open invoice can be re-emailed from the modal', calls.some((c) => c.path === `/club-admin/billing/super/clubs/${ORG}/invoices/inv-row-1/resend` && c.method === 'POST'))
  await page.getByRole('button', { name: 'VOID' }).click().catch(() => {})
  await page.waitForTimeout(700)
  ck('an invoice can be voided', calls.some((c) => c.path === `/club-admin/billing/super/clubs/${ORG}/invoices/inv-row-1/void`))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
