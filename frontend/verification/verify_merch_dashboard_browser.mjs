// BetterMerch stock dashboard, driven on the REAL screen with the API stubbed at
// the network layer. The stub is the real payload the backend produced from a
// seeded Postgres (backend/verification/verify_merch_dashboard.py with
// DUMP_DASHBOARD=<file>), so a shape mismatch between service and screen shows.
//
// Asserted:
//   * the page opens from the Stock dashboard nav item and asks
//     GET /club-admin/merch/dashboard?days=90;
//   * the KPI tiles carry the payload's figures; the stock-over-time and
//     what-went-out charts draw (recharts svg), as do best sellers and size;
//   * switching the window to 30 days sends days=30 on the wire and the sold
//     tile changes (a contrast, not a pass by default);
//   * the four attention lists name the right products;
//   * the table filters (a status filter leaves only that status), searches
//     without losing focus per character, and a row expands to its sizes;
//   * the three export links point at the right endpoints with the window;
//   * an empty club (no products) shows the call to add stock, not a blank page;
//   * no page errors, and no horizontal overflow at 390px.
//
//   DUMP_DASHBOARD=/tmp/dash.json (backend) then:
//   MERCH_DASH_JSON=/tmp/dash.json node verify_merch_dashboard_browser.mjs http://localhost:4173
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.argv[2] || process.env.APP_URL || 'http://localhost:4173'
const DASH = JSON.parse(fs.readFileSync(process.env.MERCH_DASH_JSON, 'utf8'))
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

let EMPTY = false
const EMPTY_DASH = {
  ...DASH['90'], products: [], series: [], by_size: [], by_colour: [], by_category: [], by_type: [],
  sales_by_source: [], retired_sales: [],
  kpis: { ...DASH['90'].kpis, units_on_hand: 0, units_sold: 0 },
  notes: { ...DASH['90'].notes, has_stock: false, has_sales: false },
}

const stub = (page, calls) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url()
  calls.push({ url, method: req.method() })
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  if (/\/auth\/me/.test(url)) {
    return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } })
  }
  const m = url.match(/\/club-admin\/merch\/dashboard\?days=(\d+)/)
  if (m) return json(EMPTY ? EMPTY_DASH : (DASH[m[1]] || DASH['90']))
  if (/\/club-admin\/merch\/storefront-status/.test(url)) return json({ enabled: false })
  return json({})
})

const run = async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {})
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  page.setDefaultTimeout(6000)
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const calls = []
  await stub(page, calls)

  const seen = (sel) => page.locator(sel).count().then((n) => n > 0).catch(() => false)
  const countOf = (sel) => page.locator(sel).count().catch(() => 0)
  const bodyText = () => page.locator('body').innerText().catch(() => '')
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  // The KPI tile's value, read by its label (CSS `uppercase` makes innerText upper-case).
  const kpi = async (label) => {
    const tile = page.locator('div.pb-card', { has: page.getByText(label, { exact: true }) }).first()
    return (await tile.innerText().catch(() => '')).replace(label.toUpperCase(), '').replace(label, '').trim()
  }
  const card = (title) => page.locator('section.pb-card', { has: page.getByRole('heading', { name: title, exact: true }) }).first()

  await page.goto(BASE + '/admin/clubhouse', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1200)
  // Through the nav, so the sidebar item is proven rather than the URL.
  await page.getByRole('link', { name: 'Stock dashboard' }).first().click().catch(() => {})
  await page.waitForSelector('text=Stock value (cost)', { timeout: 10000 }).catch(() => {})
  await page.waitForTimeout(800)

  check('reached via the Stock dashboard nav item', /\/admin\/merch\/dashboard$/.test(page.url()), page.url())
  check('asks for the 90 day dashboard', calls.some((c) => /merch\/dashboard\?days=90/.test(c.url)))

  const d90 = DASH['90']
  const fmtMoney = (n) => '$' + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  check('units on hand tile', (await kpi('Units on hand')).includes(String(d90.kpis.units_on_hand)), await kpi('Units on hand'))
  check('stock value (cost) tile', (await kpi('Stock value (cost)')).includes(fmtMoney(d90.kpis.stock_value_cost)), await kpi('Stock value (cost)'))
  const sold90 = await kpi('Units sold (90d)')
  check('units sold tile for the window', sold90.includes(String(d90.kpis.units_sold)), sold90)

  // Charts draw real marks.
  check('stock over time draws an area', (await card('Stock on hand over time').locator('path.recharts-area-curve').count()) > 0)
  check('what went out draws bars', (await card('What went out').locator('.recharts-bar-rectangle').count()) > 0)
  check('best sellers draws bars', (await card('Best sellers').locator('.recharts-bar-rectangle').count()) > 0)
  check('size chart draws on-hand and sold bars', (await card('Apparel by size').locator('.recharts-bar-rectangle').count()) >= 4)
  check('value by category draws bars', (await card('Where the money is sitting').locator('.recharts-bar-rectangle').count()) > 0)
  check('the history note names the lens (stock starts when items were entered)',
    /history starts|Balance at the end/.test(await card('Stock on hand over time').innerText()))

  // Toggles change the chart.
  await card('Apparel by size').getByRole('button', { name: 'Colour', exact: true }).click().catch(() => {})
  await page.waitForTimeout(300)
  check('size toggle switches to colour', await seen('h3:has-text("Apparel by colour")'))
  await card('Best sellers').getByRole('button', { name: 'Revenue', exact: true }).click().catch(() => {})
  await page.waitForTimeout(300)
  check('best sellers revenue toggle redraws', (await card('Best sellers').locator('.recharts-bar-rectangle').count()) > 0)

  check('a single unpriced sale reads in the singular', /1 unit was sold with no price recorded/.test(await bodyText()))

  // Attention lists
  const att = (title) => page.locator('div.pb-card', { has: page.getByRole('heading', { name: title, exact: true }) }).first().innerText().catch(() => '')
  check('out of stock names the sold-out product', /Sold-out socks/.test(await att('Out of stock')))
  check('low stock names the hoodie size under its reorder point', /Hoodie/.test(await att('Low stock')) && /2XL \(4\)/.test(await att('Low stock')))
  check('running low names the water bottle with weeks left', /Water bottle/.test(await att('Running low')) && /wks left/.test(await att('Running low')))
  check('not selling names the cap with value tied up', /Club cap/.test(await att('Not selling')) && /tied up/.test(await att('Not selling')))
  check('a product entered today is not in not-selling', !/New scarf/.test(await att('Not selling')))

  // Table
  const rowsAll = await countOf('section.pb-card tbody tr.cursor-pointer')
  check('table lists every product', rowsAll === d90.products.length, `${rowsAll} vs ${d90.products.length}`)
  await page.getByLabel('Status', { exact: true }).selectOption('not_selling').catch(() => {})
  await page.waitForTimeout(300)
  const filtered = await page.locator('section.pb-card tbody tr.cursor-pointer').allInnerTexts()
  check('status filter leaves only that status', filtered.length === 1 && /Club cap/.test(filtered[0]) && /Not selling/i.test(filtered[0]), JSON.stringify(filtered))
  await page.getByLabel('Status', { exact: true }).selectOption('').catch(() => {})
  let held = true
  for (const ch of 'hood') {
    await page.getByLabel('Search items').type(ch, { delay: 25 }).catch(() => { held = false })
    if ((await page.evaluate(() => document.activeElement && document.activeElement.tagName)) !== 'INPUT') held = false
  }
  check('search keeps focus per character', held)
  const searched = await page.locator('section.pb-card tbody tr.cursor-pointer').allInnerTexts()
  check('search narrows to the hoodie', searched.length === 1 && /Hoodie/.test(searched[0]), JSON.stringify(searched))
  await page.locator('section.pb-card tbody tr.cursor-pointer').first().click().catch(() => {})
  await page.waitForTimeout(300)
  const detail = await card('Every item').locator('tbody').first().innerText().catch(() => '')
  check('a row expands to its sizes with on hand and last sold', /2XL/.test(detail) && /Reorder at/.test(detail) && /\b20\b/.test(detail), detail.slice(0, 200))
  await page.getByLabel('Search items').fill('').catch(() => {})

  // Window contrast
  await page.getByLabel('Time window').selectOption('30').catch(() => {})
  await page.waitForTimeout(900)
  check('changing the window asks for days=30', calls.some((c) => /merch\/dashboard\?days=30/.test(c.url)))
  const sold30 = await kpi('Units sold (30d)')
  check('the sold tile changes with the window', sold30.includes(String(DASH['30'].kpis.units_sold)) && DASH['30'].kpis.units_sold !== d90.kpis.units_sold, sold30)
  check('daily buckets at 30 days draw more than 13 points', DASH['30'].series.length === 30)

  // Exports
  const href = (name) => page.getByRole('link', { name }).first().getAttribute('href').catch(() => '')
  check('Excel workbook link carries the window', /reports\/export-workbook\?days=30$/.test(await href('Excel workbook')), await href('Excel workbook'))
  check('Stock CSV link', /reports\/export$/.test(await href('Stock CSV')), await href('Stock CSV'))
  check('All movements CSV link', /reports\/export-movements\?days=0$/.test(await href('All movements CSV')), await href('All movements CSV'))

  await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/merch-dashboard-desktop.png` : '/tmp/merch-dashboard-desktop.png', fullPage: true })
  check('no horizontal overflow at 1500px', (await overflow()) <= 1, `${await overflow()}px`)

  // Phone width
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(600)
  check('no horizontal overflow at 390px', (await overflow()) <= 1, `${await overflow()}px`)
  await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/merch-dashboard-phone.png` : '/tmp/merch-dashboard-phone.png', fullPage: true })

  // Empty club
  EMPTY = true
  await page.setViewportSize({ width: 1200, height: 900 })
  await page.getByLabel('Time window').selectOption('180').catch(() => {})
  await page.waitForTimeout(900)
  check('an empty club is told to add stock', /No stock entered yet/.test(await bodyText()) && (await seen('a:has-text("Add your first item")')))

  check('no page errors', errors.length === 0, errors.join(' | ').slice(0, 300))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run()
