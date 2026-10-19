// Drives the real Admin > Website > Honours screen in Chromium, API stubbed at the network layer.
//
//   npx vite --port 5199 &
//   node verification/verify_honour_cap_filter_browser.mjs [baseUrl]
//
// Asked for by Shoalwater Bay CC: their A Grade cap numbers are Club Award rows named
// "A Grade Cap Number", so an auto honour board needs to pick ONE award by name inside
// its category. Checks what the screen draws, the exact request on the wire for create,
// edit and clear, that a manual board shows no such field, and 390px for overflow.
// Also checks the profile badge rule (lib/capAward.js) for a cap, a non-cap and a cap
// with no number.
import { chromium } from 'playwright'
import { capBadgeText, isCapAward } from '../src/lib/capAward.js'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

console.log('== the profile badge rule')
const cap = { category: 'Club Award', subcategory: null, achievement: 'A Grade Cap Number', detail: '186' }
ck('a cap reads "A Grade Cap 186"', capBadgeText(cap, 'A Grade Cap Number') === 'A Grade Cap 186', capBadgeText(cap, 'A Grade Cap Number'))
ck('a club that renamed the award to "Cap Number" reads "Cap 186"', capBadgeText(cap, 'Cap Number') === 'Cap 186', capBadgeText(cap, 'Cap Number'))
ck('a cap with no number falls back to the usual badge', capBadgeText({ ...cap, detail: 'no number yet' }, 'A Grade Cap Number') === null)
ck('"Captain" is not a cap', !isCapAward({ category: 'Office Bearer', achievement: 'Captain', detail: '12' }) && capBadgeText({ category: 'Office Bearer', achievement: 'Captain', detail: '12' }, 'Captain') === null)
ck('a Best Batter with a number-looking detail is not a cap', capBadgeText({ category: 'Club Award', achievement: 'Best Batter', detail: '436' }, 'Best Batter') === null)

const CLUB = { id: 'c1', name: 'Alpha CC', slug: 'alpha' }
const BOARDS = [
  { id: 'b1', title: "Men's A Grade Caps", description: null, display_order: 1, columns: 2, entries: [],
    source_category: 'Club Award', source_subcategory: null, source_achievement: 'A Grade Cap Number', auto_count: 3 },
  { id: 'b2', title: 'Life Members', description: null, display_order: 2, columns: 1, entries: [],
    source_category: null, source_subcategory: null, source_achievement: null, auto_count: 0 },
]

async function stub(page, state) {
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    const method = req.method()
    const body = req.postData() ? JSON.parse(req.postData()) : null
    state.calls.push({ method, p, q: url.search, body })
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p === '/auth/me') return json({
      id: 'u1', username: 'pat', display_name: 'Pat', role: 'club_admin', club_id: CLUB.id, club_slug: CLUB.slug,
      is_primary_admin: true, can_switch_clubs: false,
      entitlements: { modules: [], status: 'active', billing_modules: [] }, capabilities: ['manage_website'],
    })
    if (p === '/club-admin/website/honours') return json(BOARDS)
    if (p === '/club-admin/website/honour-categories') return json([
      { category: 'Club Award', subcategory: null, count: 270 }, { category: 'Hall of Fame', subcategory: null, count: 4 }])
    if (p === '/club-admin/website/honour-achievements') return json([
      { achievement: 'A Grade Cap Number', count: 270 }, { achievement: "Women's A Grade Cap Number", count: 40 }])
    if (p === '/club-admin/website/settings') return json({ honours_columns: 1 })
    if (/\/club-admin\/website\/honours\/boards\/b1$/.test(p) && method === 'PUT') {
      return json({ ...BOARDS[0], ...body, auto_count: 3 })
    }
    if (p === '/club-admin/website/honours/boards' && method === 'POST') {
      return json({ id: 'b3', display_order: 3, columns: body.columns, entries: [], auto_count: 40, description: null, ...body }, 201)
    }
    if (p === '/club-admin/players' || p === '/club-admin/settings' || p === '/club-admin/seasons') return json([])
    return json({ detail: 'not stubbed' }, 404)
  })
}

const noOverflow = page => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)
const browser = await chromium.launch({ executablePath: EXECUTABLE })

for (const width of [1280, 390]) {
  console.log(`== ${width}px`)
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  const state = { calls: [] }
  await stub(page, state)
  try {
    await page.goto(`${BASE}/admin/website`)
    await page.getByRole('button', { name: /^Honours$/i }).click({ timeout: 15000 })
    await page.getByText("Men's A Grade Caps").first().waitFor({ timeout: 15000 })

    const summary = await page.getByText(/Auto-listing/).first().innerText()
    ck(`${width}: the board says which award it lists`, /Club Award/.test(summary) && /A Grade Cap Number/.test(summary), summary)

    // Edit the caps board
    await page.getByRole('button', { name: 'EDIT' }).first().click()
    const field = page.getByPlaceholder('e.g. A Grade Cap Number').first()
    await field.waitFor({ timeout: 3000 }).catch(() => {})
    ck(`${width}: the edit form shows the award name already saved`, (await field.inputValue()) === 'A Grade Cap Number', await field.inputValue())
    const opts = await page.locator('datalist option').evaluateAll(els => els.map(e => e.getAttribute('value')))
    ck(`${width}: the picker offers the award names in the category`, opts.includes('A Grade Cap Number') && opts.includes("Women's A Grade Cap Number"), JSON.stringify(opts))
    const asked = state.calls.find(c => c.p === '/club-admin/website/honour-achievements')
    ck(`${width}: the picker asked for the board's category`, asked && /category=Club(\+|%20)Award/.test(asked.q), asked?.q)
    await field.fill("Women's A Grade Cap Number")
    await page.getByRole('button', { name: 'Save board' }).click()
    await page.waitForTimeout(300)
    const put = state.calls.filter(c => c.method === 'PUT').pop()
    ck(`${width}: saving sends the new award name with the category`, put?.body?.source_achievement === "Women's A Grade Cap Number" && put?.body?.source_category === 'Club Award', JSON.stringify(put?.body))

    // Clear it
    await page.getByRole('button', { name: 'EDIT' }).first().click()
    await page.getByPlaceholder('e.g. A Grade Cap Number').first().fill('   ')
    await page.getByRole('button', { name: 'Save board' }).click()
    await page.waitForTimeout(300)
    const put2 = state.calls.filter(c => c.method === 'PUT').pop()
    ck(`${width}: clearing it sends null, so the board lists the whole category again`, put2?.body && put2.body.source_achievement === null, JSON.stringify(put2?.body))

    // Manual board: no field
    await page.getByRole('button', { name: 'EDIT' }).nth(1).click()
    ck(`${width}: a manual board's editor has no "only awards named" field`, (await page.getByText('Only awards named').count()) === 0)
    await page.getByRole('button', { name: '×' }).first().click().catch(() => {})

    // New board
    const newSel = page.locator('select').filter({ hasText: 'Manual entries' }).last()
    ck(`${width}: the new-board form hides the field until a category is picked`, (await page.getByPlaceholder('e.g. A Grade Cap Number').count()) === 0)
    await newSel.selectOption({ label: 'Auto: Club Award (270)' })
    ck(`${width}: and shows it once one is`, (await page.getByPlaceholder('e.g. A Grade Cap Number').count()) === 1)
    await page.getByPlaceholder('e.g. A Grade Cap Number').last().fill("Women's A Grade Cap Number")
    await page.getByPlaceholder('e.g. Life Members').fill("Ladies' A Grade Caps")
    await page.getByRole('button', { name: 'Add board' }).click()
    await page.waitForTimeout(300)
    const post = state.calls.filter(c => c.method === 'POST').pop()
    ck(`${width}: a new board is created with the award name`, post?.body?.source_achievement === "Women's A Grade Cap Number" && post?.body?.title === "Ladies' A Grade Caps" && post?.body?.source_category === 'Club Award', JSON.stringify(post?.body))
  } catch (e) {
    // The previous screen has no such field, so a step that needs it throws: report it as a failed check.
    ck(`${width}: the screen could be driven to the end`, false, String(e.message).split('\n')[0])
  }
  ck(`${width}: no page errors`, errors.length === 0, errors.join(' | '))
  ck(`${width}: nothing pushes the page sideways`, await noOverflow(page))
  await page.screenshot({ path: `/tmp/honours_${width}.png`, fullPage: false })
  await ctx.close()
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
