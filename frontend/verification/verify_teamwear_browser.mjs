// Teamwear ordering, driven on the REAL screens with the API stubbed at the network layer. The
// stub is the real payload the backend produced from a seeded Postgres
// (backend/verification/verify_teamwear.py with DUMP_TEAMWEAR=<file>), so a shape mismatch
// between service and screen shows.
//
// Coordinator (BetterAdmin > Stock > Teamwear):
//   * the nav item opens Teamwear, which asks GET /club-admin/teamwear/campaigns and lists the round
//   * Shop range shows each item at the club-rule price
//   * Triage draws the live table: the 1-unit product is flagged Suggested cut, the approval is shown;
//     choosing Cut on another product sends PUT .../triage/{id} {decision: "cut"} and the
//     "approval was cleared" note appears when the server says so
//   * Orders: the number clash shows under "Numbers to check"
//   * Payments: a bank CSV upload POSTs multipart to /payments/bank/preview, the reference match is
//     preselected, and Record sends the row with that order id
//   * no horizontal overflow at 390px on the campaign screen
// Member (Player Dashboard > Teamwear):
//   * the dashboard card links to /playerdash/tok/kit
//   * the Kit page lists the open round; adding a personalised shirt and typing #23 asks the
//     number check and shows the clash note; placing the order POSTs the line with the wearer,
//     the number and the name in capitals
//   * a cut line reads Not available this round; a requested order shows the bank reference and
//     Pay by card POSTs /kit/orders/{id}/pay/stripe
//   * no overflow at 390px
//
//   DUMP_TEAMWEAR=/tmp/tw.json (backend) then:
//   TEAMWEAR_JSON=/tmp/tw.json node verification/verify_teamwear_browser.mjs http://localhost:4173
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.argv[2] || process.env.APP_URL || 'http://localhost:4173'
const D = JSON.parse(fs.readFileSync(process.env.TEAMWEAR_JSON, 'utf8'))
const SHOT = process.env.SHOT_DIR || null
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)

const CID = D.triage_payload.campaign.id
const ME = {
  id: 'boss', username: 'boss', email: 'boss@example.com', display_name: 'Boss', role: 'club_admin', club_slug: 'npcc',
  capabilities: ['*'], entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], core_live: true, status: 'active' },
}

async function adminPage(browser, width, calls) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  let triage = D.triage
  await page.route('**/api/**', async (r) => {
    const req = r.request()
    const url = req.url()
    const path = new URL(url).pathname.replace(/^\/api/, '')
    calls.push({ method: req.method(), path, body: req.postData() })
    if (path === '/auth/me') return json(r, ME)
    if (path === '/club-admin/teamwear/campaigns') return json(r, { campaigns: D.campaigns })
    if (path === '/club-admin/teamwear/range') return json(r, D.range)
    if (path === `/club-admin/teamwear/campaigns/${CID}`) return json(r, page.__payload || D.triage_payload)
    if (path === `/club-admin/teamwear/campaigns/${CID}/triage`) return json(r, triage)
    if (req.method() === 'PUT' && path.startsWith(`/club-admin/teamwear/campaigns/${CID}/triage/`)) {
      triage = { ...D.triage, approval_current: false, approval_cleared: true,
        items: D.triage.items.map((i) => (path.endsWith(i.product_id) ? { ...i, decision: JSON.parse(req.postData()).decision } : i)) }
      return json(r, triage)
    }
    if (path === `/club-admin/teamwear/campaigns/${CID}/payments`) return json(r, { payments: D.payments })
    if (path === `/club-admin/teamwear/campaigns/${CID}/export`) return json(r, D.export)
    if (path === '/club-admin/teamwear/payments/bank/preview') return json(r, D.bank_preview)
    if (path === '/club-admin/teamwear/payments/bank/commit') return json(r, { recorded: 1, skipped: 0 })
    return json(r, {})
  })
  return { ctx, page, errors }
}

async function memberPage(browser, width, calls, path = '/playerdash/tok/kit') {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500 })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const CLUB = { name: 'North Perth CC', slug: 'npcc', logo_url: null, accent_color: null, primary_color: null }
  const kit = { ...D.kit, card: { stripe: true, square: false } }
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route(/\/api\/public\/availability\/tok$/, (r) => json(r, { club: CLUB, require_pin: true, has_availability: false, players: [{ id: 'p1', display_name: 'Smith, Jo', has_phone: true }] }))
  await page.route(/\/api\/public\/availability\/tok\/me(\?.*)?$/, (r) => json(r, { club: CLUB, player: { id: 'p1', display_name: 'Smith, Jo' }, dates: [], availability: {}, has_availability: false, squads: [] }))
  await page.route(/\/api\/public\/availability\/tok\/me\/profile(\?.*)?$/, (r) => json(r, {
    club: CLUB, player: { id: 'p1', display_name: 'Smith, Jo' }, modules: ['teamwear'], squads: [], selected: [],
    training: { upcoming: [], attended_8_weeks: 0, last_attended: null },
    teamwear: { open: [{ name: 'Winter training', closes_at: D.kit.campaigns[0].closes_at }], orders: 2, owing: 40, stock: true,
      active: [{ reference: 'SMITH TEAMWEAR', phase: 'payment', balance: 40, campaign_name: null }] },
  }))
  await page.route(/\/api\/public\/availability\/tok\/kit(\?.*)?$/, (r) => { calls.push({ method: 'GET', path: 'kit' }); return json(r, kit) })
  await page.route(/\/api\/public\/availability\/tok\/kit\/number-check/, (r) => {
    const u = new URL(r.request().url())
    calls.push({ method: 'GET', path: 'number-check', number: u.searchParams.get('number') })
    return json(r, u.searchParams.get('number') === '23'
      ? { status: 'clash', note: '#23 is held by Ali Holder on the club register.' } : { status: 'new', note: null })
  })
  await page.route(/\/api\/public\/availability\/tok\/kit\/orders$/, (r) => {
    calls.push({ method: r.request().method(), path: 'orders', body: r.request().postData() })
    return json(r, { order: { id: 'new' } })
  })
  await page.route(/\/api\/public\/availability\/tok\/kit\/orders\/[^/]+\/pay\/stripe$/, (r) => {
    calls.push({ method: 'POST', path: r.request().url() })
    return json(r, { url: `${BASE}/paid-stub` })
  })
  await page.route(/\/paid-stub$/, (r) => r.fulfill({ status: 200, contentType: 'text/html', body: '<p id="stub">stripe</p>' }))
  await page.goto(`${BASE}${path}`)
  return { ctx, page, errors }
}

const run = async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {})

  console.log('coordinator')
  const calls = []
  const { ctx, page, errors } = await adminPage(browser, 1400, calls)
  await safe('home', async () => {
    await page.goto(`${BASE}/admin/clubhouse`)
    await page.getByRole('link', { name: 'Teamwear', exact: true }).first().click()
    await page.locator('[data-teamwear-tab="campaigns"]').waitFor()
    await page.getByText(D.campaigns[0].name).first().waitFor()
    check('nav opens Teamwear and lists the round', calls.some((c) => c.path === '/club-admin/teamwear/campaigns'))
    await page.getByRole('button', { name: 'Shop range' }).click()
    await page.locator('[data-range-item]').first().waitFor()
    const items = await page.locator('[data-range-item]').allInnerTexts()
    const shirt = items.find((t) => t.includes('Playing shirt')) || ''
    check('shop range shows the club-rule price', shirt.includes('$60.00'), shirt.slice(0, 120))
    check('range lists every item', items.length === D.range.products.length, String(items.length))
  })
  await safe('triage', async () => {
    await page.goto(`${BASE}/admin/teamwear/campaigns/${CID}?tab=triage`)
    await page.locator('[data-triage-row]').first().waitFor()
    const training = await page.locator('[data-triage-row="MS202"]').innerText()
    check('1 unit product is flagged Suggested cut', /suggested cut/i.test(training), training.slice(0, 160))
    const approval = await page.locator('[data-approval]').innerText()
    check('approval recorded is shown', /approved/i.test(approval) && approval.includes('Re-approved by email'), approval.slice(0, 160))
    const before = calls.length
    await page.locator('[data-triage-row="MS303"]').getByRole('button', { name: 'Cut', exact: true }).click()
    await page.getByText('the committee approval was cleared').waitFor()
    const put = calls.slice(before).find((c) => c.method === 'PUT')
    check('Cut sends the decision on the wire', put && JSON.parse(put.body).decision === 'cut' && put.path.endsWith(D.triage.items.find((i) => i.supplier_code === 'MS303').product_id), JSON.stringify(put))
    check('stepper sits on Confirm while approved', (await page.locator('[data-step="confirm"]').getAttribute('data-state')) === 'now')
  })
  await safe('orders', async () => {
    // At triage the kid's #23 still clashes with the register (it is approved later in the round).
    page.__payload = D.triage_payload
    await page.goto(`${BASE}/admin/teamwear/campaigns/${CID}?tab=orders`)
    await page.locator('[data-order]').first().waitFor()
    await page.getByRole('button', { name: /Numbers to check/ }).click()
    const shown = await page.locator('[data-order]').count()
    check('Numbers to check shows the order with the clash', shown >= 1, String(shown))
    await page.locator('[data-order="SMITH TEAMWEAR"] button[aria-expanded]').click()
    const card = await page.locator('[data-order="SMITH TEAMWEAR"]').innerText()
    check('a cut line reads Not available this round', /not available this round/i.test(card), card.slice(0, 200))
  })
  await safe('bank csv', async () => {
    page.__payload = D.payment_payload
    await page.goto(`${BASE}/admin/teamwear/campaigns/${CID}?tab=payments`)
    await page.locator('[data-bank-import]').waitFor()
    const before = calls.length
    await page.locator('[data-bank-import] input[type=file]').setInputFiles({ name: 'cba.csv', mimeType: 'text/csv', buffer: Buffer.from(D.bank_csv) })
    await page.locator('[data-bank-row]').first().waitFor()
    const prev = calls.slice(before).find((c) => c.path === '/club-admin/teamwear/payments/bank/preview')
    check('CSV goes up as multipart with the campaign', prev && /name="campaign_id"/.test(prev.body || '') && (prev.body || '').includes(CID))
    const sel = await page.locator('[data-bank-row] select').inputValue()
    const want = D.bank_preview.rows[0].suggestions[0].order_id
    check('reference match is preselected', sel === want, sel)
    await page.getByRole('button', { name: /^Record 1 payments?$/ }).click()
    await page.getByText(/Recorded 1 payment/).waitFor()
    const commit = calls.find((c) => c.path === '/club-admin/teamwear/payments/bank/commit')
    const row = commit && JSON.parse(commit.body).rows[0]
    check('Record sends the row with the matched order', row && row.order_id === want && row.key === D.bank_preview.rows[0].key, JSON.stringify(row))
  })
  check('no page errors (coordinator)', errors.length === 0, errors.join(' | '))
  await ctx.close()

  await safe('390px coordinator', async () => {
    const c2 = []
    const m = await adminPage(browser, 390, c2)
    m.page.__payload = D.payment_payload
    for (const tab of ['orders', 'triage', 'payments', 'export', 'setup']) {
      await m.page.goto(`${BASE}/admin/teamwear/campaigns/${CID}?tab=${tab}`)
      await m.page.locator(`[data-campaign-tab="${tab}"]`).waitFor()
      await m.page.waitForTimeout(300)
      const o = await overflow(m.page)
      check(`no overflow at 390px: ${tab}`, o <= 1, `${o}px`)
    }
    if (SHOT) await m.page.screenshot({ path: `${SHOT}/teamwear-admin-390.png`, fullPage: true })
    await m.ctx.close()
  })

  console.log('member')
  const mc = []
  await safe('dashboard card', async () => {
    const { ctx: c, page: p } = await memberPage(browser, 1200, mc, '/playerdash/tok')
    await p.locator('[data-my-page]').waitFor({ timeout: 20000 })
    const summary = (await p.locator('[data-group="kit"] [data-group-summary]').innerText()).trim()
    check('Teamwear section summary says what is owing', summary === '$40.00 to pay', summary)
    await p.locator('[data-group-toggle="kit"]').click()
    const link = p.locator('[data-teamwear-link]')
    await link.waitFor()
    check('dashboard card links to the Kit page', (await link.getAttribute('href')) === '/playerdash/tok/kit')
    await c.close()
  })
  const { ctx: mctx, page: mp, errors: merr } = await memberPage(browser, 1200, mc)
  await safe('kit page', async () => {
    await mp.locator('[data-kit-page]').waitFor({ timeout: 20000 })
    await mp.locator('[data-campaign="Winter training"]').waitFor()
    const camp = mp.locator('[data-campaign="Winter training"]')
    await camp.locator('[data-shop-product="Playing shirt"] button', { hasText: 'Add' }).click()
    const line = camp.locator('[data-basket-line]').first()
    await line.getByLabel('Number').fill('23')
    await line.getByLabel('Name on the back').fill('smith j')
    await mp.locator('[data-number-note="clash"]').waitFor()
    check('number check asked with the number', mc.some((c) => c.path === 'number-check' && c.number === '23'))
    check('name shows in capitals as typed', (await line.getByLabel('Name on the back').inputValue()) === 'SMITH J')
    await camp.locator('[data-place-order]').click()
    await mp.getByText('Your order is in').waitFor()
    const post = mc.find((c) => c.path === 'orders' && c.method === 'POST')
    const body = post && JSON.parse(post.body)
    const l0 = body?.lines?.[0]
    check('order POST carries campaign, wearer, number and capitals',
      body && body.campaign_id === D.kit.campaigns[0].id && l0.number === '23' && l0.text === 'SMITH J' && l0.wearer_player_id === D.kit.family.find((f) => f.me).player_id,
      JSON.stringify(body))
  })
  await safe('orders and paying', async () => {
    const cut = mp.locator('[data-line-state="cut"]')
    check('cut line reads Not available this round', /not available this round/i.test(await cut.first().innerText()))
    const pay = mp.locator('[data-pay-box]').first()
    await pay.waitFor()
    const ref = await pay.locator('[data-pay-reference]').innerText()
    check('pay box shows the bank reference', /TEAMWEAR/.test(ref), ref)
    await pay.getByRole('button', { name: 'Pay by card' }).click()
    await mp.waitForURL(/paid-stub/)
    check('Pay by card POSTs the Stripe checkout for that order', mc.some((c) => /\/kit\/orders\/[^/]+\/pay\/stripe$/.test(c.path)))
  })
  check('no page errors (member)', merr.length === 0, merr.join(' | '))
  await mctx.close()
  await safe('390px member', async () => {
    const { ctx: c, page: p } = await memberPage(browser, 390, [])
    await p.locator('[data-kit-page]').waitFor({ timeout: 20000 })
    await p.locator('[data-campaign="Winter training"] [data-shop-product="Playing shirt"] button', { hasText: 'Add' }).click()
    await p.waitForTimeout(300)
    const o = await overflow(p)
    check('no overflow at 390px: kit page', o <= 1, `${o}px`)
    if (SHOT) await p.screenshot({ path: `${SHOT}/teamwear-kit-390.png`, fullPage: true })
    await c.close()
  })
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run()
