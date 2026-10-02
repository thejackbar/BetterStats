// Drives the real BetterPosts designer (/admin/social-post) and the Sponsors admin
// screen in Chromium with the API stubbed at the network layer, for the sponsors a
// post starts with (v9.105).
//
//   npm run build && npx vite preview --port 5197 &
//   node frontend/verification/verify_post_sponsors_browser.mjs [baseUrl]
//
// Checks that a new post carries the club's default sponsors without anyone
// asking, that the request on the wire names the post's grade, that a grade pin
// changes what the post starts with, that picking sponsors in the panel resizes
// the grid and takes it over from the defaults, that taking the last sponsor off
// asks first (and a "no" leaves it), that the grid is in the exported node, that
// a layout with sponsor slots of its own gets no second grid, and the exact PUT
// the admin screen sends when a sponsor is pinned to a grade.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS_DIR || ''

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  - ${extra}` : ''}`) }
}

const svgFor = (id) => `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100" viewBox="0 0 300 100"><rect width="300" height="100" rx="10" fill="#e11d48"/><text x="150" y="58" font-size="28" font-family="sans-serif" font-weight="700" text-anchor="middle" fill="#fff">${id.toUpperCase()}</text></svg>`
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC', 'base64')

const SETTINGS = {
  id: 'org-1', name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'applecross',
  logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null,
}
const PLAYERS = [
  { id: 'p1', name: 'Jack Barendse', display_name: 'Jack Barendse', status: 'active', photo_url: '/api/images/players/p1/photo' },
  { id: 'p2', name: 'Sam Alborn', display_name: 'Sam Alborn', status: 'active', photo_url: '/api/images/players/p2/photo' },
]
const sp = (id, name, tier, withLogo = true) => ({
  id, name, tier, website_url: null, logo_url: withLogo ? `/images/sponsors/${id}/logo` : null,
  display_order: 1, placement_overrides: {}, placements: [],
})
const SPONSORS = [
  sp('major', 'Big Major', 'major'), sp('gold', 'Gold Co', 'gold'), sp('silver', 'Silver Co', 'silver'),
  sp('nologo', 'Logoless Co', 'major', false),
]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

// `answer(team, grade)` is the stand-in for the server's post-default route.
async function openEditor(query, { answer, sponsors = SPONSORS, width = 1600 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  const defaultCalls = []
  const writes = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_|Failed to load resource/.test(m.text())) errors.push(m.text().slice(0, 200)) })
  const json = (body, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = route.request().method()
    if (method !== 'GET') writes.push({ path, method, body: route.request().postData() })
    if (path.startsWith('/images/sponsors/')) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svgFor(path.split('/')[3]) })
    if (/\/images\/players\/[^/]+\/photo/.test(path)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    if (path === '/club-admin/sponsors/post-default') {
      defaultCalls.push(url.search)
      const r = answer(url.searchParams.get('team') || '', url.searchParams.get('grade') || '')
      return r ? route.fulfill(json(r)) : route.fulfill(json({ detail: 'nope' }, 404))
    }
    if (path === '/club-admin/sponsors/post-defaults') {
      if (method === 'PUT') return route.fulfill(json({ options: { teams: ['1st XI'], grades: ['A Grade', 'B Grade'] }, assignments: { teams: {}, grades: JSON.parse(route.request().postData()).grades }, club_default_ids: ['major', 'gold'] }))
      return route.fulfill(json({ options: { teams: ['1st XI'], grades: ['A Grade', 'B Grade'] }, assignments: { teams: {}, grades: {} }, club_default_ids: ['major', 'gold'] }))
    }
    if (path === '/club-admin/sponsors/settings') {
      return route.fulfill(json({ tiers: [{ key: 'major', default_label: 'Major Partners', default_placements: ['posts'] }], placements: [{ key: 'posts', label: 'Social posts' }], tier_labels: { major: 'Major Partners' } }))
    }
    if (path === '/club-admin/sponsors/section-names') return route.fulfill(json({ sections: [] }))
    if (path === '/club-admin/sponsors') return route.fulfill(json(sponsors))
    if (path === '/auth/me') {
      return route.fulfill(json({ id: 'u1', username: 'admin', role: 'club_admin', club_id: 'org-1', club_slug: 'applecross', capabilities: ['manage_sponsors'],
        entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' } }))
    }
    if (/\/admin\/social\/templates/.test(path)) return route.fulfill(json([]))
    if (/\/admin\/social\/media\?kind=background/.test(route.request().url())) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(path)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(path)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(path)) return route.fulfill(json(PLAYERS))
    if (/selection\/overview/.test(path)) return route.fulfill(json({ fixtures: [] }))
    if (/lineups/.test(path)) return route.fulfill(json({ matches: [] }))
    return route.fulfill(json({}))
  })

  await page.goto(`${BASE}${query}`, { waitUntil: 'domcontentloaded' })
  return { ctx, page, errors, defaultCalls, writes }
}

const rail = (page, label) => page.locator(`nav button[title="${label}"]`).first().click({ timeout: 3000 }).catch(() => {})
const waitEditor = (page) => page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
// The live canvas and the off-screen export copy both carry post-blocks; read the canvas's.
const gridAlts = (page) =>
  page.locator('[data-testid=post-blocks]').first().locator('[data-sponsor-grid] img').evaluateAll((l) => l.map((i) => i.getAttribute('alt')))
const readAlts = (page) => page.locator('[data-testid=post-blocks] [data-sponsor-grid] img').first().waitFor({ timeout: 8000 }).catch(() => {})
  .then(() => gridAlts(page))

const DEFAULT = (team, grade) => ({ sponsor_ids: ['major', 'gold'], source: 'club' })
const WITH_PIN = (team, grade) => (grade === 'A Grade' ? { sponsor_ids: ['silver'], source: 'grade' } : { sponsor_ids: ['major', 'gold'], source: 'club' })

// 1. A new lineup post carries the club's default sponsors with nobody asking.
{
  const { page, ctx, errors, defaultCalls } = await openEditor('/admin/social-post?type=lineup', { answer: DEFAULT })
  await waitEditor(page)
  const alts = await readAlts(page)
  ck('a new lineup post has a sponsor grid on it', alts.length > 0, JSON.stringify(alts))
  ck('it holds the club default sponsors, major first', JSON.stringify(alts) === '["Big Major","Gold Co"]', JSON.stringify(alts))
  ck('a sponsor with no logo is not drawn', !alts.includes('Logoless Co'))
  ck('the editor asked the server what this post starts with', defaultCalls.length >= 1, String(defaultCalls.length))
  const exported = await page.locator('[data-sponsor-grid]').count()
  ck('the grid is in the exported copy of the post as well as the canvas', exported >= 2, String(exported))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/post-default-sponsors.png` })
  await ctx.close()
}

// 2. A grade pin changes what the post starts with, until somebody takes over.
{
  const { page, ctx, defaultCalls } = await openEditor('/admin/social-post?type=lineup', { answer: WITH_PIN })
  await waitEditor(page)
  await readAlts(page)
  await rail(page, 'Content')
  const comp = page.getByPlaceholder('PREMIER T20').first()
  await comp.waitFor({ timeout: 8000 }).catch(() => {})
  await comp.fill('A Grade', { timeout: 3000 }).catch(() => {})
  await page.waitForFunction(() => {
    const alts = [...document.querySelector('[data-testid=post-blocks]').querySelectorAll('[data-sponsor-grid] img')].map((i) => i.getAttribute('alt'))
    return alts.length === 1 && alts[0] === 'Silver Co'
  }, null, { timeout: 8000 }).catch(() => {})
  let alts = await gridAlts(page)
  ck('typing the grade asks for that grade, on the wire', defaultCalls.some((q) => /grade=A\+Grade|grade=A%20Grade/.test(q)), JSON.stringify(defaultCalls))
  ck("an untouched grid follows the grade's pinned sponsor", JSON.stringify(alts) === '["Silver Co"]', JSON.stringify(alts))
  // Take over: open the panel and add Gold.
  await rail(page, 'Sponsors')
  await page.getByLabel('Put Gold Co on this post').check({ timeout: 3000 }).catch(() => {})
  await page.waitForTimeout(300)
  alts = await gridAlts(page)
  ck('ticking a sponsor in the panel adds it to the grid', alts.includes('Gold Co') && alts.includes('Silver Co'), JSON.stringify(alts))
  await comp.fill('B Grade', { timeout: 3000 }).catch(() => {})
  await page.waitForTimeout(900)
  alts = await gridAlts(page)
  ck("once taken over, the grid no longer follows the grade", alts.includes('Gold Co') && alts.includes('Silver Co') && !alts.includes('Big Major'), JSON.stringify(alts))
  ck('the panel offers no tick for a sponsor with no logo', await page.getByLabel('Put Logoless Co on this post').count() === 0)
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/post-sponsors-panel.png` })
  await ctx.close()
}

// 3. Taking the sponsors off asks first; "no" leaves them, "yes" removes them for good on this post.
{
  const { page, ctx } = await openEditor('/admin/social-post?type=lineup', { answer: DEFAULT })
  await waitEditor(page)
  await readAlts(page)
  const dialogs = []
  let accept = false
  page.on('dialog', async (d) => { dialogs.push(d.message()); if (accept) await d.accept(); else await d.dismiss() })
  await rail(page, 'Sponsors')
  await page.getByRole('button', { name: 'Take the sponsors off this post' }).click({ timeout: 3000 }).catch(() => {})
  await page.waitForTimeout(300)
  ck('taking the sponsors off asks first', dialogs.length === 1 && /every post carries a sponsor/i.test(dialogs[0]), JSON.stringify(dialogs))
  ck('answering no leaves the sponsors on the post', (await gridAlts(page)).length > 0)
  accept = true
  await page.getByRole('button', { name: 'Take the sponsors off this post' }).click({ timeout: 3000 }).catch(() => {})
  await page.waitForTimeout(600)
  ck('answering yes takes them off', (await gridAlts(page)).length === 0, JSON.stringify(await gridAlts(page)))
  await page.waitForTimeout(900)
  ck('and the editor does not put them back on this post', (await gridAlts(page)).length === 0)
  await ctx.close()
}

// 4. A layout with sponsor slots of its own gets no second grid.
{
  const { page, ctx } = await openEditor('/admin/social-post?type=results', { answer: DEFAULT })
  await waitEditor(page)
  await page.waitForTimeout(1200)
  ck('a results post uses its own sponsor slots, so no extra grid', await page.locator('[data-sponsor-grid]').count() === 0)
  await ctx.close()
}

// 5. The server route is missing (football, or an older server): the top sponsor still goes on.
{
  const { page, ctx } = await openEditor('/admin/social-post?type=lineup', { answer: () => null })
  await waitEditor(page)
  const alts = await readAlts(page)
  ck('with no default route the first sponsor with a logo is still on the post', JSON.stringify(alts) === '["Big Major"]', JSON.stringify(alts))
  await ctx.close()
}

// 6. A club with no sponsors: the post has none, and says so in the panel.
{
  const { page, ctx } = await openEditor('/admin/social-post?type=lineup', { answer: DEFAULT, sponsors: [] })
  await waitEditor(page)
  await page.waitForTimeout(1200)
  ck('a club with no sponsors gets no grid', await page.locator('[data-sponsor-grid]').count() === 0)
  await rail(page, 'Sponsors')
  const panel = await page.getByTestId('sponsors-panel').innerText({ timeout: 3000 }).catch(() => '')
  ck('and the panel says why', /no sponsors yet/i.test(panel), panel)
  await ctx.close()
}

// 7. The grid follows the canvas size while untouched.
{
  const { page, ctx } = await openEditor('/admin/social-post?type=lineup', { answer: DEFAULT })
  await waitEditor(page)
  await readAlts(page)
  const topOf = () => page.evaluate(() => {
    const g = document.querySelector('[data-testid=post-blocks]')?.querySelector('[data-sponsor-grid]')
    if (!g) return null
    // The block's wrapper carries the absolute top, in 1080-space.
    return parseFloat(g.parentElement.style.top)
  })
  const square = await topOf()
  await rail(page, 'Design')
  await page.getByRole('button', { name: /Story/ }).first().click({ timeout: 3000 }).catch(() => {})
  await page.waitForTimeout(700)
  const story = await topOf()
  ck('on a story the untouched grid moves down to the new bottom edge', square !== null && story !== null && story > square + 500, `${square} -> ${story}`)
  await ctx.close()
}

// 8. Admin screen: pin a sponsor to a grade, exact request on the wire.
{
  const { page, ctx, writes } = await openEditor('/admin/sponsors', { answer: DEFAULT })
  await page.getByTestId('post-sponsors').waitFor({ timeout: 15000 }).catch(() => {})
  ck('admin: the Sponsors on posts panel is there', await page.getByTestId('post-sponsors').count() === 1)
  await page.getByLabel('Team or grade to pin sponsors to').selectOption('grades:A Grade', { timeout: 3000 }).catch(() => {})
  await page.getByTestId('post-sponsors').getByRole('button', { name: 'Silver Co' }).click({ timeout: 3000 }).catch(() => {})
  ck('admin: a sponsor with no logo cannot be picked', await page.getByTestId('post-sponsors').getByRole('button', { name: 'Logoless Co' }).count() === 0)
  await page.getByRole('button', { name: 'Pin sponsors' }).click({ timeout: 3000 }).catch(() => {})
  await page.waitForTimeout(500)
  const put = writes.find((w) => w.path === '/club-admin/sponsors/post-defaults' && w.method === 'PUT')
  const body = put ? JSON.parse(put.body) : null
  ck('admin: one PUT pins the sponsor to the grade', JSON.stringify(body) === JSON.stringify({ teams: {}, grades: { 'A Grade': ['silver'] } }), JSON.stringify(body))
  ck('admin: the pin shows in the list afterwards', (await page.getByTestId('post-sponsors').innerText({ timeout: 1500 }).catch(() => '')).includes('A Grade'))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/admin-post-sponsors.png`, fullPage: true })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
