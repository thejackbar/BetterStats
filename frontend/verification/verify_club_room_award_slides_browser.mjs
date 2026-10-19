// Drives the real Club Room Mode editor and TV in Chromium, API stubbed at the network layer.
//
//   npx vite --port 5199 &
//   node verification/verify_club_room_award_slides_browser.mjs [baseUrl]
//
// Asked for by Shoalwater Bay CC: show A Grade cap numbers on the TV from Club Room Mode,
// without going to the website admin. The Honour Boards slide gets "Awards from your
// records". Checks the editor's pickers, the warning for a name that matches nothing, the
// exact PATCH body, the playlist row's wording, the TV slide, and 390px for overflow.
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const CLUB = { id: 'c1', name: 'Alpha CC', slug: 'alpha' }
const SLIDES = [{ id: 's1', slide_type: 'honours', title: null, enabled: true, position: 0, duration_seconds: null,
  config: { kind: 'boards', board_id: '', group: '' } }]
const ENTRIES = [
  { label: '2013', name: 'Sample Player A', detail: 'Cap 186' }, { label: '2013', name: 'Sample Player B', detail: 'Cap 187' },
  { label: '2014', name: 'Sample Player C', detail: 'Cap 188' }, { label: '2014', name: 'Sample Player D', detail: 'Cap 189' },
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
      entitlements: { modules: [], status: 'active', billing_modules: [] }, capabilities: ['manage_club_room'],
    })
    if (p === '/club-admin/club-room/settings') return json({ enabled: true, rotation_seconds: 15, theme: 'dark', shuffle: false, slides: SLIDES })
    if (p === '/club-admin/club-room/honour-sources') return json({
      boards: [], groups: [],
      award_categories: [{ category: 'Club Award', subcategory: null, count: 270 }, { category: 'Hall of Fame', subcategory: null, count: 4 }] })
    if (p === '/club-admin/club-room/award-names') return json([
      { achievement: 'A Grade Cap Number', count: 230 }, { achievement: "Women's A Grade Cap Number", count: 40 }])
    if (p === '/club-admin/club-room/grade-types') return json({ available: [], default: [] })
    if (/\/club-admin\/club-room\/slides\/s1$/.test(p) && method === 'PATCH') return json({ ...SLIDES[0], ...body })
    if (p === '/club-admin/club-room/public-link') return json({ enabled: false, has_pin: false })
    if (p === '/club-admin/club-room/play') return json({
      enabled: true, club_name: 'Alpha CC', theme: 'dark', rotation_seconds: 15, shuffle: false, skipped: [],
      slides: [{ type: 'honours', id: 'honours-s1-0', eyebrow: 'Honour board', title: "Men's A Grade Caps", subtitle: null, columns: 2, entries: ENTRIES }] })
    if (/\/club-admin\/(sponsors|seasons|settings|players)$/.test(p)) return json([])
    if (/club-room\/(reports|media)/.test(p)) return json([])
    return json({ detail: 'not stubbed' }, 404)
  })
}

const noOverflow = page => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)
const browser = await chromium.launch({ executablePath: EXECUTABLE })

for (const width of [1280, 390]) {
  console.log(`== ${width}px editor`)
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  const state = { calls: [] }
  await stub(page, state)
  try {
    await page.goto(`${BASE}/admin/club-room`)
    await page.getByRole('button', { name: 'EDIT' }).first().click({ timeout: 15000 })
    const what = page.locator('label', { hasText: 'What to show' }).locator('xpath=following-sibling::select').first()
    const kinds = await what.locator('option').allInnerTexts()
    ck(`${width}: Awards from your records is offered`, kinds.some(k => /^Awards from your records/.test(k)), JSON.stringify(kinds))
    ck(`${width}: the category picker is hidden until it is chosen (the field is not always there)`, (await page.getByText('Award category').count()) === 0)
    await what.selectOption({ label: 'Awards from your records (e.g. cap numbers)' })
    const cat = page.locator('label', { hasText: 'Award category' }).locator('xpath=following-sibling::select').first()
    const cats = await cat.locator('option').allInnerTexts()
    ck(`${width}: the club's award categories are listed with counts`, JSON.stringify(cats) === JSON.stringify(['Choose a category', 'Club Award (270)', 'Hall of Fame (4)']), JSON.stringify(cats))
    ck(`${width}: no award-name box until a category is picked`, (await page.getByPlaceholder('e.g. A Grade Cap Number').count()) === 0)
    await cat.selectOption({ label: 'Club Award (270)' })
    const name = page.getByPlaceholder('e.g. A Grade Cap Number')
    await name.waitFor({ timeout: 5000 })
    const asked = state.calls.find(c => c.p === '/club-admin/club-room/award-names')
    ck(`${width}: the name picker asked for that category`, asked && /category=Club(\+|%20)Award/.test(asked.q), asked?.q)
    const opts = await page.locator('datalist option').evaluateAll(els => els.map(e => e.getAttribute('value')))
    ck(`${width}: and offers the award names in it`, opts.includes('A Grade Cap Number') && opts.includes("Women's A Grade Cap Number"), JSON.stringify(opts))
    await name.fill('A Grade Cap Numbr')
    ck(`${width}: a name that matches nothing is flagged`, (await page.getByText(/would be skipped/).count()) === 1)
    await name.fill('a grade cap number')
    ck(`${width}: a name that matches (any case) is not`, (await page.getByText(/would be skipped/).count()) === 0)
    await name.fill('A Grade Cap Number')
    await page.getByPlaceholder('Honour Boards').fill("Men's A Grade Caps")
    await page.screenshot({ path: `/tmp/room_awards_${width}.png` })
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.waitForTimeout(300)
    const patch = state.calls.filter(c => c.method === 'PATCH').pop()
    ck(`${width}: saving sends the slide title and the award settings`,
      patch?.body?.title === "Men's A Grade Caps" && patch?.body?.config?.kind === 'awards'
        && patch?.body?.config?.category === 'Club Award' && patch?.body?.config?.achievement === 'A Grade Cap Number', JSON.stringify(patch?.body))
    const rows = await page.locator('text=/^Honour Boards ·/').allInnerTexts()
    ck(`${width}: the playlist row says which award`, rows.some(r => /^Honour Boards · A Grade Cap Number/.test(r)), JSON.stringify(rows))
  } catch (e) {
    ck(`${width}: the editor could be driven to the end`, false, String(e.message).split('\n')[0])
  }
  ck(`${width}: no page errors`, errors.length === 0, errors.join(' | '))
  ck(`${width}: nothing pushes the page sideways`, await noOverflow(page))
  await ctx.close()
}

console.log('== the TV')
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } })
  const page = await ctx.newPage()
  await stub(page, { calls: [] })
  try {
    await page.goto(`${BASE}/admin/club-room/play`)
    await page.getByText("Men's A Grade Caps").first().waitFor({ timeout: 15000 })
    await page.waitForTimeout(1500)
    const text = (await page.locator('body').innerText()).replace(/\s+/g, ' ')
    ck('the TV lists the caps as "Cap N" under the slide title', /Cap 186/.test(text) && /Cap 189/.test(text) && /MEN'S A GRADE CAPS/i.test(text), text.slice(0, 200))
    await page.screenshot({ path: '/tmp/room_awards_tv.png' })
  } catch (e) {
    ck('the TV slide could be drawn', false, String(e.message).split('\n')[0])
  }
  await ctx.close()
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
