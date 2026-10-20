// Drives the real Club Room Mode editor (and the TV slides) in Chromium, API stubbed at the network layer.
//
//   npx vite --port 5199 &
//   node verification/verify_club_room_grade_type_browser.mjs [baseUrl]
//
// Asked for by Shoalwater Bay CC: a Grade type pick on the Leaderboard and Records slides.
// Checks what the editor draws (only the grade types the club has), the exact PATCH body
// when a type is picked and when it is cleared, the playlist row's wording, that the TV
// slides show the type under the eyebrow, and 390px for overflow.
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const CLUB = { id: 'c1', name: 'Alpha CC', slug: 'alpha' }
const SLIDES = [
  { id: 's1', slide_type: 'leaderboard', title: null, enabled: true, position: 0, duration_seconds: null,
    config: { stat_group: 'batting', sort_by: 'total_runs', season_id: '', limit: 10 } },
  { id: 's2', slide_type: 'records', title: null, enabled: true, position: 1, duration_seconds: null,
    config: { category: 'batting.top_career_runs', categories: 'womens', season_id: '', limit: 8 } },
]
const ROWS = [
  { player_id: 'p1', name: 'Sample Player A', total_runs: 1842, runs: 1842 },
  { player_id: 'p2', name: 'Sample Player B', total_runs: 1610, runs: 1610 },
  { player_id: 'p3', name: 'Sample Player C', total_runs: 1377, runs: 1377 },
]

async function stub(page, state) {
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    const method = req.method()
    const body = req.postData() ? JSON.parse(req.postData()) : null
    state.calls.push({ method, p, body })
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p === '/auth/me') return json({
      id: 'u1', username: 'pat', display_name: 'Pat', role: 'club_admin', club_id: CLUB.id, club_slug: CLUB.slug,
      is_primary_admin: true, can_switch_clubs: false,
      entitlements: { modules: [], status: 'active', billing_modules: [] }, capabilities: ['manage_club_room'],
    })
    if (p === '/club-admin/club-room/settings') return json({ enabled: true, rotation_seconds: 15, theme: 'dark', shuffle: false, slides: SLIDES })
    if (p === '/club-admin/club-room/grade-types') return json({
      available: [{ key: 'senior', label: "Men's" }, { key: 'junior', label: 'Juniors' }, { key: 'womens', label: "Women's" }], default: ['senior', 'womens'] })
    if (/\/club-admin\/club-room\/slides\/s\d$/.test(p) && method === 'PATCH') {
      const id = p.split('/').pop()
      const base = SLIDES.find(s => s.id === id)
      return json({ ...base, ...body })
    }
    if (p === '/club-admin/club-room/public-link') return json({ enabled: false, has_pin: false })
    if (p === '/club-admin/club-room/play') return json({
      enabled: true, club_name: 'Alpha CC', theme: 'dark', rotation_seconds: 15, shuffle: false, skipped: [],
      slides: [
        { type: 'leaderboard', id: 'lb-s1', title: 'Batting Leaderboard', stat_group: 'batting', sort_by: 'total_runs', season_label: 'All-time', grade_type_label: "Women's", rows: ROWS },
      ] })
    if (/\/club-admin\/(sponsors|seasons|settings|players)$/.test(p)) return json([])
    if (/club-room\/(reports|media)/.test(p)) return json([])
    if (p === '/club-admin/club-room/honour-sources') return json({ boards: [], groups: [] })
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
    await page.getByText('Leaderboard · batting').first().waitFor({ timeout: 15000 })
    const rows = await page.locator('text=/^(Leaderboard|Club Records) ·/').allInnerTexts()
    ck(`${width}: a slide with no pick reads as it always did`, rows.some(r => /^Leaderboard · batting( · 15s per slide)?$/.test(r)), JSON.stringify(rows))
    ck(`${width}: a slide with a pick says it in the playlist row`, rows.some(r => /^Club Records · .* · Women's( · 15s per slide)?$/.test(r)), JSON.stringify(rows))

    await page.getByRole('button', { name: 'EDIT' }).first().click()
    const select = page.locator('label', { hasText: 'Grade type' }).locator('xpath=following-sibling::select').first()
    await select.waitFor({ timeout: 5000 })
    const options = await select.locator('option').allInnerTexts()
    ck(`${width}: the drop-down offers Club default, the club's grade types and All grades`,
      JSON.stringify(options) === JSON.stringify(['Club default', "Men's", 'Juniors', "Women's", 'All grades']), JSON.stringify(options))
    ck(`${width}: no Masters (the club has none)`, !options.includes('Masters'))
    ck(`${width}: it starts on Club default for a slide with no pick`, (await select.inputValue()) === '')
    await page.screenshot({ path: `/tmp/room_editor_${width}.png` })
    await select.selectOption({ label: "Women's" })
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.waitForTimeout(300)
    const patch = state.calls.filter(c => c.method === 'PATCH').pop()
    ck(`${width}: saving sends the pick in the slide's config`, patch?.body?.config?.categories === 'womens' && patch?.body?.config?.stat_group === 'batting', JSON.stringify(patch?.body))

    // Records slide already has a pick; clear it
    await page.getByRole('button', { name: 'EDIT' }).nth(1).click()
    const sel2 = page.locator('label', { hasText: 'Grade type' }).locator('xpath=following-sibling::select').first()
    ck(`${width}: a saved pick is shown selected`, (await sel2.inputValue()) === 'womens', await sel2.inputValue())
    await sel2.selectOption({ label: 'Club default' })
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.waitForTimeout(300)
    const patch2 = state.calls.filter(c => c.method === 'PATCH').pop()
    ck(`${width}: choosing Club default removes the pick (nothing is sent for it)`, patch2?.body?.config && !('categories' in patch2.body.config) && patch2.body.config.category === 'batting.top_career_runs', JSON.stringify(patch2?.body))
  } catch (e) {
    ck(`${width}: the editor could be driven to the end`, false, String(e.message).split('\n')[0])
  }
  ck(`${width}: no page errors`, errors.length === 0, errors.join(' | '))
  ck(`${width}: nothing pushes the page sideways`, await noOverflow(page))
  await ctx.close()
}

console.log('== the TV slide')
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } })
  const page = await ctx.newPage()
  const state = { calls: [] }
  await stub(page, state)
  try {
    await page.goto(`${BASE}/admin/club-room/play`)
    await page.getByText('Batting Leaderboard').first().waitFor({ timeout: 15000 })
    const eyebrow = await page.getByText(/All-time/).first().innerText()
    ck('the leaderboard slide names its grade type under the title', /ALL-TIME.*WOMEN'S/i.test(eyebrow.replace(/\s+/g, ' ')), eyebrow)
    await page.waitForTimeout(1500)
    await page.screenshot({ path: '/tmp/room_tv.png' })
  } catch (e) {
    ck('the TV slide could be drawn', false, String(e.message).split('\n')[0])
    await page.screenshot({ path: '/tmp/room_tv_fail.png' })
    console.log('  page text:', (await page.locator('body').innerText()).replace(/\s+/g, ' ').slice(0, 300))
  }
  await ctx.close()
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
