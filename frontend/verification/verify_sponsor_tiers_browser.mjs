// Drives the real club dashboard, a club leaderboard page and a player profile in
// Chromium with the API stubbed at the network layer, for sponsor tiers (v9.103).
//
//   npm run build && npx vite preview --port 5197 &
//   node frontend/verification/verify_sponsor_tiers_browser.mjs [baseUrl]
//
// Checks the exact request on the wire (one sponsors fetch shared by the
// dashboard slot, the sponsor list and the bar), what each spot draws, that a
// club with no major sponsor keeps the plain header, that a signed-in admin sees
// the prompt in its place, that a player profile (no club slug in its URL) gets
// its club's sponsor list, and that 390px has no sideways overflow.
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

// A visible 300x100 logo per sponsor id, so layout and sizing can be judged on screenshots.
const svgFor = (id) => `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100" viewBox="0 0 300 100"><rect width="300" height="100" rx="10" fill="#e11d48"/><text x="150" y="58" font-size="28" font-family="sans-serif" font-weight="700" text-anchor="middle" fill="#fff">${id.toUpperCase()}</text></svg>`

const logo = (n) => `/api/images/sponsors/${n}/logo`
const sp = (id, name, tier, placements, withLogo = true) => ({
  id, name, website_url: `https://${id}.example`, logo_url: withLogo ? logo(id) : null,
  tier, tier_label: null, placements,
})
const MAJOR = ['dashboard', 'bar', 'footer']
const BAR = ['bar', 'footer']
const LIST = ['footer']

const SPONSORS_ONE_MAJOR = {
  club_name: 'Test CC', current_season: 'Summer 2026/27',
  tier_labels: { major: 'Naming Partner', gold: 'Gold Partners', silver: 'Silver Partners', supporter: 'Supporters' },
  sponsors: [
    sp('maj1', 'Froth Craft', 'major', MAJOR),
    sp('gold1', 'Gold Plumbing', 'gold', BAR),
    sp('sil1', 'Silver Sparks', 'silver', BAR),
    sp('sup1', 'Corner Bakery', 'supporter', LIST, false),
  ],
}
const SPONSORS_THREE_MAJORS = {
  ...SPONSORS_ONE_MAJOR,
  sponsors: [sp('maj1', 'Froth Craft', 'major', MAJOR), sp('maj2', 'Big Bank', 'major', MAJOR),
             sp('maj3', 'Tyre World', 'major', MAJOR), sp('gold1', 'Gold Plumbing', 'gold', BAR)],
}
const SPONSORS_NO_MAJOR = {
  ...SPONSORS_ONE_MAJOR,
  sponsors: [sp('gold1', 'Gold Plumbing', 'gold', BAR), sp('sup1', 'Corner Bakery', 'supporter', LIST, false)],
}
const SPONSORS_NONE = { ...SPONSORS_ONE_MAJOR, sponsors: [] }

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openPage({ sponsors, width = 1440, admin = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  const sponsorCalls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  // The app's ErrorBoundary swallows a render error into the console, so catch it there too.
  page.on('console', (m) => { if (m.type() === 'error' && /render error/i.test(m.text())) errors.push(m.text().slice(0, 200)) })
  const json = (route, body, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    if (path.startsWith('/images/sponsors/')) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svgFor(path.split('/')[3]) })
    if (path === '/clubs/testclub/sponsors') { sponsorCalls.push(url.search); return json(route, sponsors) }
    if (path === '/clubs/testclub') {
      return json(route, { id: 'org-1', slug: 'testclub', name: 'Test Cricket Club', short_name: 'Test CC', is_active: true, website_enabled: false })
    }
    if (path === '/auth/me') {
      if (!admin) return json(route, { detail: 'no' }, 401)
      return json(route, { id: 'u1', username: 'admin', role: 'club_admin', club_id: 'org-1', capabilities: ['manage_sponsors', 'run_sync'],
                           entitlements: { modules: [] } })
    }
    if (path === '/players/p1' || path === '/players/p1/stats') {
      return json(route, { player: { id: 'p1', organisation_id: 'org-1', name: 'Pat Player', display_name: 'Pat Player' },
                           career_batting: {}, career_bowling: {}, career_fielding: {}, batting_innings: [], bowling_spells: [] })
    }
    if (path.startsWith('/players/p1/') || /achievements|award-definitions/.test(path)) return json(route, [])
    if (path === '/organisations/org-1') return json(route, { id: 'org-1', slug: 'testclub', name: 'Test Cricket Club' })
    if (/\/organisations\/org-1\/seasons$/.test(path)) return json(route, [{ id: 's26', name: 'Summer 2026/27', year: 2026 }])
    if (/grade-categories/.test(path)) return json(route, { available: ['senior'], default: ['senior'], available_formats: [] })
    if (/\/summary/.test(path)) return json(route, { total_games: 10, total_runs: 1000, total_wickets: 100, total_players: 20 })
    if (/upcoming-milestones/.test(path)) return json(route, [])
    if (/leaderboard/.test(path)) return json(route, [])
    if (/\/(games|players|fixtures)$/.test(path)) return json(route, [])
    if (/\/grades/.test(path)) return json(route, [])
    return json(route, {})
  })
  return { page, ctx, errors, sponsorCalls }
}

const noSideScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)
const count = (page, sel) => page.locator(sel).count()
// Presence-safe reads: an absent element reads as '' / null so a control run reports FAIL instead of crashing.
const textOf = (loc) => loc.first().innerText({ timeout: 1500 }).catch(() => '')
const attrOf = (loc, name) => loc.first().getAttribute(name, { timeout: 1500 }).catch(() => null)

// 1. One major sponsor on the dashboard.
{
  const { page, ctx, errors, sponsorCalls } = await openPage({ sponsors: SPONSORS_ONE_MAJOR })
  await page.goto(`${BASE}/testclub`, { waitUntil: 'load' })
  await page.locator('[data-testid=major-sponsor-slot]').waitFor({ timeout: 15000 }).catch(() => {})
  if (process.env.DEBUG_BODY) { console.log('ERRORS', errors); console.log((await page.locator('body').innerText()).slice(0, 600)) }
  ck('1 major: the slot is on the dashboard', await count(page, '[data-testid=major-sponsor-slot]') === 1)
  const slotImgs = await page.locator('[data-testid=major-sponsor-slot] img').evaluateAll((l) => l.map((i) => i.getAttribute('alt')))
  ck('1 major: only the major sponsor is in the slot', JSON.stringify(slotImgs) === '["Froth Craft"]', JSON.stringify(slotImgs))
  const slotText = await textOf(page.locator('[data-testid=major-sponsor-slot]'))
  ck("1 major: the slot is headed with the club's own tier name", /naming partner/i.test(slotText), slotText)
  const wall = page.locator('section[aria-label="Club sponsors"]')
  ck('1 major: the all-sponsors list is at the bottom', await wall.count() === 1)
  const wallText = await textOf(wall)
  ck('list: names the logo-less supporter in text', /corner bakery/i.test(wallText), wallText)
  ck('list: groups by tier with the club tier names', /naming partner/i.test(wallText) && /gold partners/i.test(wallText) && /silver partners/i.test(wallText) && /supporters/i.test(wallText), wallText)
  const barImgs = await page.locator('footer img').evaluateAll((l) => l.map((i) => i.getAttribute('alt')))
  ck('bar: logos only, biggest tier first', JSON.stringify(barImgs) === '["Froth Craft","Gold Plumbing","Silver Sparks"]', JSON.stringify(barImgs))
  ck('one sponsors request serves the slot, the list and the bar', sponsorCalls.length === 1, String(sponsorCalls.length))
  ck('the slot link goes to the sponsor site', await attrOf(page.locator('[data-testid=major-sponsor-slot] a'), 'href') === 'https://maj1.example')
  ck('the header still has its Leaderboard button beside the slot', await page.getByRole('link', { name: /Leaderboard/ }).count() >= 1)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/dashboard-one-major.png`, fullPage: true })
  await ctx.close()
}

// 2. Several majors share the slot.
{
  const { page, ctx } = await openPage({ sponsors: SPONSORS_THREE_MAJORS })
  await page.goto(`${BASE}/testclub`, { waitUntil: 'load' })
  await page.locator('[data-testid=major-sponsor-slot]').waitFor({ timeout: 15000 }).catch(() => {})
  ck('3 majors: all three share the slot', await count(page, '[data-testid=major-sponsor-slot] img') === 3)
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/dashboard-three-majors.png`, fullPage: true })
  await ctx.close()
}

// 3. No major sponsor: the plain header, no slot, no prompt for the public.
{
  const { page, ctx } = await openPage({ sponsors: SPONSORS_NO_MAJOR })
  await page.goto(`${BASE}/testclub`, { waitUntil: 'load' })
  await page.getByText('CLUB DASHBOARD').first().waitFor({ timeout: 15000 }).catch(() => {})
  await page.locator('section[aria-label="Club sponsors"]').waitFor({ timeout: 15000 }).catch(() => {})
  ck('no major: no slot is drawn', await count(page, '[data-testid=major-sponsor-slot]') === 0)
  ck('no major: the public sees no add prompt', await page.getByText('Add a major sponsor').count() === 0)
  ck('no major: the other sponsors still show in the list (the check can pass the other way)',
     await count(page, 'section[aria-label="Club sponsors"]') === 1)
  await ctx.close()
}

// 4. Admin with no major sponsor sees the prompt.
{
  const { page, ctx } = await openPage({ sponsors: SPONSORS_NO_MAJOR, admin: true })
  await page.goto(`${BASE}/testclub`, { waitUntil: 'load' })
  await page.getByText('Add a major sponsor').waitFor({ timeout: 15000 }).catch(() => {})
  ck('no major: a club admin sees the add prompt', await page.getByText('Add a major sponsor').count() === 1)
  ck('the prompt links to the sponsors screen', await attrOf(page.getByRole('link', { name: 'Add a major sponsor' }), 'href') === '/admin/sponsors')
  await ctx.close()
}

// 5. A club with no sponsors at all draws nothing extra.
{
  const { page, ctx } = await openPage({ sponsors: SPONSORS_NONE })
  await page.goto(`${BASE}/testclub`, { waitUntil: 'load' })
  await page.getByText('CLUB DASHBOARD').first().waitFor({ timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(300)
  ck('no sponsors: no slot, no list, no bar',
     await count(page, '[data-testid=major-sponsor-slot]') === 0
     && await count(page, 'section[aria-label="Club sponsors"]') === 0
     && await count(page, 'footer') === 0)
  await ctx.close()
}

// 6. Another club page: the list is there too.
{
  const { page, ctx } = await openPage({ sponsors: SPONSORS_ONE_MAJOR })
  await page.goto(`${BASE}/testclub/leaderboard`, { waitUntil: 'load' })
  await page.locator('section[aria-label="Club sponsors"]').waitFor({ timeout: 15000 }).catch(() => {})
  ck('leaderboard page: the all-sponsors list is at the bottom', await count(page, 'section[aria-label="Club sponsors"]') === 1)
  await ctx.close()
}

// 7. Player profile: no club slug in the URL, the page tells the footer.
{
  const { page, ctx, sponsorCalls, errors } = await openPage({ sponsors: SPONSORS_ONE_MAJOR })
  await page.goto(`${BASE}/players/p1`, { waitUntil: 'load' })
  await page.locator('section[aria-label="Club sponsors"]').waitFor({ timeout: 15000 }).catch(() => {})
  if (process.env.DEBUG_BODY) { console.log('ERRORS', errors); console.log((await page.locator('body').innerText()).slice(0, 400)) }
  ck('player profile: the all-sponsors list is at the bottom', await count(page, 'section[aria-label="Club sponsors"]') === 1)
  ck('player profile: asked for its own club', sponsorCalls.length >= 1)
  await ctx.close()
}

// 8. 390px: no sideways scroll, slot fits.
{
  const { page, ctx } = await openPage({ sponsors: SPONSORS_THREE_MAJORS, width: 390 })
  await page.goto(`${BASE}/testclub`, { waitUntil: 'load' })
  await page.locator('[data-testid=major-sponsor-slot]').waitFor({ timeout: 15000 }).catch(() => {})
  ck('390px: no sideways overflow on the dashboard', await noSideScroll(page))
  const box = await page.locator('[data-testid=major-sponsor-slot]').first().boundingBox({ timeout: 1500 }).catch(() => null)
  ck('390px: the slot fits inside the viewport', box && box.x >= 0 && box.x + box.width <= 390, JSON.stringify(box))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/dashboard-390.png`, fullPage: true })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
