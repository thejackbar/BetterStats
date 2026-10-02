// Drives the real public club pages, the fantasy sign-in and the Sponsors admin
// screen in Chromium with the API stubbed at the network layer, for a club's own
// section names (v9.104).
//
//   npm run build && npx vite preview --port 5197 &
//   node frontend/verification/verify_section_names_browser.mjs [baseUrl]
//
// Checks the exact request on the wire for the admin save, the menu, heading and
// page title of renamed sections, the "Presented by" strip (and its absence on a
// section with no sponsor), the Fantasy header and sign-in wording, and 390px.
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
const card = (id, name) => ({ id, name, logo_url: `/api/images/sponsors/${id}/logo`, website_url: `https://${id}.example` })

const SECTION_NAMES = {
  leaderboard: { name: 'Big Bank Leaderboard', sponsor: null },
  records: { name: null, sponsor: card('bank', 'Big Bank') },
  fantasy: { name: 'Froth Fantasy Cricket', sponsor: card('froth', 'Froth Craft') },
  player_profile: { name: null, sponsor: card('bank', 'Big Bank') },
}
const SPONSORS = (section_names) => ({
  club_name: 'Test CC', current_season: 'Summer 2026/27',
  tier_labels: { major: 'Major Partners', gold: 'Gold Partners', silver: 'Silver Partners', supporter: 'Supporters' },
  section_names, sponsors: [],
})

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openPage({ names = SECTION_NAMES, width = 1440, admin = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  const puts = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && /render error/i.test(m.text())) errors.push(m.text().slice(0, 200)) })
  const json = (route, body, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const adminView = () => ({
    sections: [
      { key: 'fantasy', default_label: 'Fantasy', where: 'The fantasy game', name: 'Froth Fantasy Cricket', sponsor_id: 'froth' },
      { key: 'leaderboard', default_label: 'Leaderboard', where: 'Stats menu', name: null, sponsor_id: null },
      { key: 'records', default_label: 'Records', where: 'Stats menu', name: null, sponsor_id: null },
    ],
  })

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = route.request().method()
    if (path.startsWith('/images/sponsors/')) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svgFor(path.split('/')[3]) })
    if (path === '/clubs/testclub/sponsors') return json(route, SPONSORS(names))
    if (path === '/clubs/testclub') {
      return json(route, { id: 'org-1', slug: 'testclub', name: 'Test Cricket Club', short_name: 'Test CC', is_active: true, website_enabled: false })
    }
    if (path === '/auth/me') {
      if (!admin) return json(route, { detail: 'no' }, 401)
      return json(route, { id: 'u1', username: 'admin', role: 'club_admin', club_id: 'org-1', club_slug: 'testclub', capabilities: ['manage_sponsors'], entitlements: { modules: [] } })
    }
    if (path === '/club-admin/sponsors/section-names') {
      if (method === 'PUT') { puts.push(JSON.parse(route.request().postData() || '{}')); return json(route, adminView()) }
      return json(route, adminView())
    }
    if (path === '/club-admin/sponsors/settings') {
      return json(route, { tiers: [{ key: 'major', default_label: 'Major Partners', default_placements: ['dashboard'] }], placements: [{ key: 'dashboard', label: 'Dashboard slot' }], tier_labels: { major: 'Major Partners' } })
    }
    if (path === '/club-admin/sponsors') {
      return json(route, [{ id: 'froth', name: 'Froth Craft', logo_url: '/api/images/sponsors/froth/logo', tier: 'major', placements: [], placement_overrides: {} },
                          { id: 'bank', name: 'Big Bank', logo_url: '/api/images/sponsors/bank/logo', tier: 'gold', placements: [], placement_overrides: {} }])
    }
    if (path === '/public/fantasy/tok') {
      return json(route, {
        club: { name: 'Scarborough CC', short_name: 'SCC', slug: 'scarborough', logo_url: null,
                fantasy_name: names.fantasy?.name || null, fantasy_sponsor: names.fantasy?.sponsor || null },
        season: { id: 'fs1', name: 'Summer 2026/27', status: 'open', registration_open: true, rules: {}, scoring: {}, pool_size: 0 },
        me: null,
      })
    }
    if (path === '/players/p1' || path === '/players/p1/stats') {
      return json(route, { player: { id: 'p1', organisation_id: 'org-1', name: 'Pat Player', display_name: 'Pat Player' },
                           career_batting: {}, career_bowling: {}, career_fielding: {}, batting_innings: [], bowling_spells: [] })
    }
    if (path.startsWith('/players/p1/') || /achievements|award-definitions/.test(path)) return json(route, [])
    if (path === '/organisations/org-1') return json(route, { id: 'org-1', slug: 'testclub', name: 'Test Cricket Club' })
    if (/\/organisations\/org-1\/seasons$/.test(path)) return json(route, [{ id: 's26', name: 'Summer 2026/27', year: 2026 }])
    if (/grade-categories/.test(path)) return json(route, { available: ['senior'], default: ['senior'], available_formats: [] })
    if (/leaderboard/.test(path)) return json(route, [])
    if (/\/(games|players|fixtures)$/.test(path)) return json(route, [])
    return json(route, {})
  })
  return { page, ctx, errors, puts }
}

const textOf = (loc) => loc.first().innerText({ timeout: 1500 }).catch(() => '')
const noSideScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)

// 1. Renamed Leaderboard: menu, heading, tab title.
{
  const { page, ctx, errors } = await openPage()
  await page.goto(`${BASE}/testclub/leaderboard`, { waitUntil: 'load' })
  await page.locator('h1').first().waitFor({ timeout: 15000 }).catch(() => {})
  ck('leaderboard: the page heading is the club\'s own name', (await textOf(page.locator('h1'))).trim() === 'Big Bank Leaderboard', await textOf(page.locator('h1')))
  ck('leaderboard: the browser tab title uses it', /Big Bank Leaderboard/.test(await page.title()), await page.title())
  await page.getByRole('button', { name: /^Stats/ }).click().catch(() => {})
  const menu = await page.locator('body').innerText()
  ck('leaderboard: the Stats menu lists the new name', /Big Bank Leaderboard/.test(menu) && !/^\s*Leaderboard\s*$/m.test(menu), '')
  ck('leaderboard: no "Presented by" strip when no sponsor is linked', await page.locator('[data-testid=section-banner]').count() === 0)
  ck('leaderboard: no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// 2. Sponsor-only Records: standard name, plus the strip with the logo.
{
  const { page, ctx } = await openPage()
  await page.goto(`${BASE}/testclub/records`, { waitUntil: 'load' })
  await page.locator('[data-testid=section-banner]').waitFor({ timeout: 15000 }).catch(() => {})
  const banner = page.locator('[data-testid=section-banner]')
  ck('records: the "Presented by" strip shows', await banner.count() === 1)
  ck('records: it carries the sponsor logo and link',
     (await banner.locator('img').first().getAttribute('alt', { timeout: 1500 }).catch(() => null)) === 'Big Bank'
     && (await banner.locator('a').first().getAttribute('href', { timeout: 1500 }).catch(() => null)) === 'https://bank.example')
  ck('records: the heading keeps the standard wording', /record books/i.test(await textOf(page.locator('h1'))), await textOf(page.locator('h1')))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/records-presented-by.png` })
  await ctx.close()
}

// 3. Compare was not renamed: nothing changes (paired control).
{
  const { page, ctx } = await openPage()
  await page.goto(`${BASE}/testclub/compare`, { waitUntil: 'load' })
  await page.locator('h1').first().waitFor({ timeout: 15000 }).catch(() => {})
  ck('compare: not renamed, so the standard heading stays', /compare players/i.test(await textOf(page.locator('h1'))), await textOf(page.locator('h1')))
  ck('compare: no strip', await page.locator('[data-testid=section-banner]').count() === 0)
  await ctx.close()
}

// 4. A club with no names at all looks as before.
{
  const { page, ctx } = await openPage({ names: {} })
  await page.goto(`${BASE}/testclub/leaderboard`, { waitUntil: 'load' })
  await page.locator('h1').first().waitFor({ timeout: 15000 }).catch(() => {})
  ck('no names: the standard Leaderboard heading', /the ladder/i.test(await textOf(page.locator('h1'))), await textOf(page.locator('h1')))
  ck('no names: the standard tab title', /Leaderboard/.test(await page.title()) && !/Big Bank/.test(await page.title()), await page.title())
  await ctx.close()
}

// 5. Player profile gets the strip for the player_profile section.
{
  const { page, ctx } = await openPage()
  await page.goto(`${BASE}/players/p1`, { waitUntil: 'load' })
  await page.locator('[data-testid=section-banner]').waitFor({ timeout: 15000 }).catch(() => {})
  ck('player profile: the "Presented by" strip shows', await page.locator('[data-testid=section-banner]').count() === 1)
  await ctx.close()
}

// 6. Fantasy sign-in wording and header sponsor.
{
  const { page, ctx, errors } = await openPage()
  await page.goto(`${BASE}/fantasy/tok`, { waitUntil: 'load' })
  await page.getByText('Froth Fantasy Cricket').first().waitFor({ timeout: 15000 }).catch(() => {})
  const body = await page.locator('body').innerText()
  ck('fantasy: the sign-in shows the club\'s own name for the game', /Froth Fantasy Cricket/i.test(body), body.slice(0, 200))
  ck('fantasy: the club name is the sub line, not the title', /Scarborough CC\s*·\s*Summer 2026\/27/i.test(body), body.slice(0, 300))
  ck('fantasy: the sign-in shows the sponsor as presenting it', /Presented by/i.test(body) && await page.locator('img[alt="Froth Craft"]').count() >= 1, body.slice(0, 300))
  ck('fantasy: no page errors', errors.length === 0, errors.join(' | '))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/fantasy-auth.png` })
  await ctx.close()
}
{
  const { page, ctx } = await openPage({ names: {} })
  await page.goto(`${BASE}/fantasy/tok`, { waitUntil: 'load' })
  await page.getByText('Fantasy Cricket').first().waitFor({ timeout: 15000 }).catch(() => {})
  const body = await page.locator('body').innerText()
  ck('fantasy: with no name set the standard wording stays (the check can fail the other way)',
     /Scarborough CC/i.test(body) && /Fantasy Cricket/i.test(body) && !/Froth/i.test(body), body.slice(0, 200))
  await ctx.close()
}

// 7. Admin panel: exact request on the wire.
{
  const { page, ctx, puts, errors } = await openPage({ admin: true })
  await page.goto(`${BASE}/admin/sponsors`, { waitUntil: 'load' })
  await page.locator('[data-testid=section-names]').waitFor({ timeout: 15000 }).catch(() => {})
  ck('admin: the Section names panel lists every section', await page.locator('[data-testid=section-names] input').count() === 3)
  ck('admin: it shows what is saved', (await page.getByLabel('Name for Fantasy').inputValue({ timeout: 1500 }).catch(() => '')) === 'Froth Fantasy Cricket')
  await page.getByLabel('Name for Leaderboard').fill('Big Bank Leaderboard', { timeout: 1500 }).catch(() => {})
  await page.getByLabel('Sponsor for Leaderboard').selectOption('bank', { timeout: 1500 }).catch(() => {})
  await page.getByRole('button', { name: 'Save section names' }).click({ timeout: 1500 }).catch(() => {})
  await page.waitForTimeout(500)
  const sent = puts[0]?.sections
  ck('admin: one PUT with the edited section', puts.length === 1 && sent?.leaderboard?.name === 'Big Bank Leaderboard' && sent?.leaderboard?.sponsor_id === 'bank', JSON.stringify(puts))
  ck('admin: the unchanged Fantasy section is sent as it was', sent?.fantasy?.name === 'Froth Fantasy Cricket' && sent?.fantasy?.sponsor_id === 'froth', JSON.stringify(sent))
  ck('admin: a blank section is sent as nulls so the server drops it', sent?.records?.name === null && sent?.records?.sponsor_id === null, JSON.stringify(sent))
  ck('admin: no page errors', errors.length === 0, errors.join(' | '))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/admin-section-names.png`, fullPage: true })
  await ctx.close()
}

// 8. 390px.
{
  const { page, ctx } = await openPage({ width: 390 })
  await page.goto(`${BASE}/testclub/records`, { waitUntil: 'load' })
  await page.locator('[data-testid=section-banner]').waitFor({ timeout: 15000 }).catch(() => {})
  ck('390px: no sideways overflow with the strip', await noSideScroll(page))
  await page.goto(`${BASE}/fantasy/tok`, { waitUntil: 'load' })
  await page.getByText('Froth Fantasy Cricket').first().waitFor({ timeout: 15000 }).catch(() => {})
  ck('390px: no sideways overflow on the fantasy sign-in', await noSideScroll(page))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
