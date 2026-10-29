// Drives the sponsor choice for player cards in Chromium on the production build, API stubbed at the network layer.
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_card_sponsors_browser.mjs [baseUrl]
//
// 1. Sponsors admin: the "Sponsors on player cards" panel lists only sponsors with a logo, shows the saved pick, and
//    a change sends exactly PUT /club-admin/sponsors/card-sponsors with only that surface in the body; clearing sends null.
// 2. Player share page (/players/:id/share): the club's pick is drawn, with no pick the top major is drawn, the
//    picker switches the logo, "No sponsor" removes the line, the choice rides in the URL, and opening that URL
//    directly shows the same card; a club with no logos gets no picker; 390px has no sideways scroll.
// 3. Player Cards share sheet: the picker defaults to the club's pick, the sponsor on the flat copy that is rendered to
//    a picture changes with it, and the copied link carries the choice.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SHOTS = process.env.SHOTS_DIR || ''

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  - ${extra}` : ''}`) }
}

const svgFor = (id) => `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="80" viewBox="0 0 300 80"><rect width="300" height="80" fill="#1a1a1a"/><text x="150" y="52" font-size="30" font-family="Arial" text-anchor="middle" fill="#fff">${id.toUpperCase()}</text></svg>`
const logo = (id) => `/api/images/sponsors/${id}/logo`
const sp = (id, name, tier, withLogo = true) => ({ id, name, website_url: null, logo_url: withLogo ? logo(id) : null, tier, tier_label: null, placements: ['footer'] })
const SPONSORS = [sp('maj1', 'Froth Craft', 'major'), sp('gold1', 'Gold Plumbing', 'gold'), sp('nologo1', 'Logoless Ltd', 'major', false), sp('sil1', 'Silver Sparks', 'silver')]
const sponsorsPayload = (list, picks = {}) => ({ club_name: 'Test CC', current_season: null, tier_labels: {}, card_sponsors: { share_card: null, player_cards: null, ...picks }, sponsors: list })

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const noSideScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)

// ── 1. Sponsors admin ─────────────────────────────────────────────────────────
{
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 1400 } })
  const page = await ctx.newPage()
  const errors = [], puts = []
  let picks = { share_card: 'gold1', player_cards: null }
  page.on('pageerror', (e) => errors.push(String(e)))
  const admin = (s) => ({ ...s, display_order: 1, placement_overrides: {}, placements: ['footer'], website_url: null })
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace(/^\/api/, '')
    if (path.startsWith('/images/sponsors/')) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svgFor(path.split('/')[3]) })
    if (path === '/auth/me') return json(route, { id: 'u1', username: 'admin', role: 'club_admin', club_id: 'org-1', capabilities: ['manage_sponsors'], entitlements: { modules: [] } })
    if (path === '/club-admin/sponsors') return json(route, SPONSORS.map(admin))
    if (path === '/club-admin/sponsors/settings') return json(route, { tiers: ['major', 'gold', 'silver', 'supporter'].map(k => ({ key: k, default_label: k, default_placements: ['footer'] })), placements: [{ key: 'footer', label: 'Sponsor list' }], tier_labels: {} })
    if (path === '/club-admin/sponsors/section-names') return json(route, { sections: [] })
    if (path === '/club-admin/sponsors/post-defaults') return json(route, { options: { teams: [], grades: [] }, assignments: { teams: {}, grades: {} }, club_default_ids: [] })
    if (path === '/club-admin/sponsors/card-sponsors') {
      if (req.method() === 'PUT') {
        const body = JSON.parse(req.postData() || '{}')
        puts.push(body)
        picks = { ...picks, ...body }
      }
      return json(route, { surfaces: [{ key: 'share_card', label: 'Player share card' }, { key: 'player_cards', label: 'Player Cards' }], picks })
    }
    return json(route, {})
  })
  await page.goto(`${BASE}/admin/sponsors`, { waitUntil: 'domcontentloaded' })
  const panel = page.locator('[data-testid="card-sponsors"]')
  await panel.waitFor({ timeout: 20000 }).catch(() => {})
  ck('the panel is on the Sponsors screen', (await panel.count()) === 1)
  const shareSel = panel.getByLabel('Player share card')
  const cardsSel = panel.getByLabel('Player Cards')
  ck('the saved share card pick is selected', (await shareSel.inputValue().catch(() => '')) === 'gold1')
  ck('the other surface starts on automatic', (await cardsSel.inputValue().catch(() => 'x')) === '')
  const opts = await shareSel.locator('option').evaluateAll(os => os.map(o => o.value)).catch(() => [])
  ck('only sponsors with a logo can be picked', JSON.stringify(opts) === JSON.stringify(['', 'maj1', 'gold1', 'sil1']), JSON.stringify(opts))
  await cardsSel.selectOption('sil1').catch(() => {})
  await page.waitForTimeout(300)
  ck('picking a sponsor sends only that surface', JSON.stringify(puts[0]) === JSON.stringify({ player_cards: 'sil1' }), JSON.stringify(puts))
  await shareSel.selectOption('').catch(() => {})
  await page.waitForTimeout(300)
  ck('choosing automatic sends an explicit null', JSON.stringify(puts[1]) === JSON.stringify({ share_card: null }), JSON.stringify(puts))
  ck('the screen shows the saved picks', (await cardsSel.inputValue().catch(() => '')) === 'sil1' && (await shareSel.inputValue().catch(() => 'x')) === '')
  if (SHOTS) await panel.screenshot({ path: `${SHOTS}/card_sponsors_admin.png` }).catch(() => {})
  ck('no page errors (admin)', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── 2. Player share page ──────────────────────────────────────────────────────
const PLAYER = { id: 'p1', name: 'Pullinger, George', display_name: 'Pullinger, George', organisation_id: 'org1', photo_url: null }
const STATS = { player: PLAYER, career_batting: { games: 42, total_runs: 1234 }, career_bowling: { total_wickets: 20 }, career_fielding: {} }

async function openShare({ list = SPONSORS, picks = {}, width = 1000, query = '' } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    if (path.startsWith('/images/sponsors/')) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svgFor(path.split('/')[3]) })
    if (path === '/players/p1/stats') return json(route, STATS)
    if (path === '/players/p1/rankings') return json(route, {})
    if (path === '/organisations/org1') return json(route, { id: 'org1', name: 'Applecross CC', slug: 'apx', accent_color: '#f0b429', theme_config: {} })
    if (path === '/organisations/org1/seasons') return json(route, [])
    if (path === '/clubs/apx/sponsors') return json(route, sponsorsPayload(list, picks))
    return json(route, {})
  })
  await page.goto(`${BASE}/players/p1/share${query}`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('[role="button"][aria-pressed]', { timeout: 15000 })
  await page.waitForTimeout(700)
  return { page, ctx, errors }
}
const front = (page) => page.locator('[role="button"][aria-pressed] > div[aria-hidden="false"]')
const shown = async (page) => (await front(page).locator('img[src^="/api/images/sponsors/"]').evaluateAll(els => els.map(e => e.getAttribute('src').split('/')[4]))).join(',')

{
  const p = await openShare({ picks: { share_card: 'gold1' } })
  ck('the club\'s pick is the sponsor drawn', (await shown(p.page)) === 'gold1', await shown(p.page))
  ck('the picker starts on the club\'s choice', (await p.page.locator('#card-sponsor').inputValue()) === '')
  const opts = await p.page.locator('#card-sponsor option').evaluateAll(os => os.map(o => o.value))
  ck('the picker offers the sponsors with logos and No sponsor', JSON.stringify(opts) === JSON.stringify(['', 'maj1', 'gold1', 'sil1', 'none']), JSON.stringify(opts))
  await p.page.selectOption('#card-sponsor', 'sil1')
  await p.page.waitForTimeout(300)
  ck('choosing another sponsor swaps the logo', (await shown(p.page)) === 'sil1', await shown(p.page))
  ck('and the choice is in the URL', new URL(p.page.url()).searchParams.get('sponsor') === 'sil1', p.page.url())
  await p.page.selectOption('#card-sponsor', 'none')
  await p.page.waitForTimeout(300)
  ck('No sponsor removes the sponsor line', (await shown(p.page)) === '' && !/Sponsored by/.test(await front(p.page).innerText()))
  ck('and the URL says so', new URL(p.page.url()).searchParams.get('sponsor') === 'none')
  await p.page.selectOption('#card-sponsor', '')
  await p.page.waitForTimeout(300)
  ck('Club\'s choice goes back to the pick and drops the URL parameter', (await shown(p.page)) === 'gold1' && !new URL(p.page.url()).searchParams.has('sponsor'), `${await shown(p.page)} ${p.page.url()}`)
  if (SHOTS) await p.page.screenshot({ path: `${SHOTS}/share_sponsor_picker.png` })
  ck('no page errors (share)', p.errors.length === 0, p.errors.join(' | '))
  await p.ctx.close()
}
{
  const p = await openShare({ picks: {} })
  ck('with no pick the club\'s top major sponsor is drawn, as before', (await shown(p.page)) === 'maj1', await shown(p.page))
  await p.ctx.close()
}
{
  const p = await openShare({ picks: { share_card: 'gold1' }, query: '?sponsor=sil1' })
  ck('a link with a sponsor in it opens on that sponsor', (await shown(p.page)) === 'sil1' && (await p.page.locator('#card-sponsor').inputValue()) === 'sil1', await shown(p.page))
  await p.ctx.close()
}
{
  const p = await openShare({ picks: { share_card: 'gold1' }, query: '?sponsor=nonsense' })
  ck('a link naming a sponsor that is not there falls back to the club\'s pick', (await shown(p.page)) === 'gold1' && (await p.page.locator('#card-sponsor').inputValue()) === '', await shown(p.page))
  await p.ctx.close()
}
{
  const p = await openShare({ list: [sp('nologo1', 'Logoless Ltd', 'major', false)] })
  ck('a club with no sponsor logos gets no picker and no sponsor line', (await p.page.locator('#card-sponsor').count()) === 0 && (await shown(p.page)) === '')
  await p.ctx.close()
}
{
  const p = await openShare({ picks: { share_card: 'gold1' }, width: 390 })
  ck('390px: the picker fits with no sideways scroll', (await noSideScroll(p.page)) && (await p.page.locator('#card-sponsor').count()) === 1)
  if (SHOTS) await p.page.screenshot({ path: `${SHOTS}/share_sponsor_picker_390.png` })
  await p.ctx.close()
}

// ── 3. Player Cards share sheet ───────────────────────────────────────────────
{
  const CLUB = { name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c' }
  const mineCard = { kind: 'player', key: 'p:p1', player_id: 'p1', name: 'Barendse, Jack', photo_url: null, hero_photo_url: null, matches: 214, runs: 4114, bat_avg: 22.98, wickets: 211, bowl_avg: 24.1, dismissals: 98, rarity: 62, tier: 'rare', copies: 1, obtained_at: null, mine: true }
  const ctx = await browser.newContext({ viewport: { width: 390, height: 900 }, isMobile: true, hasTouch: true })
  await ctx.addInitScript(() => { try { localStorage.setItem('bs.playerpage.open', JSON.stringify({ cards: true })) } catch (e) { /* none */ } })
  await ctx.grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => {})
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const path = new URL(url).pathname.replace(/^\/api/, '')
    if (path.startsWith('/images/sponsors/')) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svgFor(path.split('/')[3]) })
    if (path === '/clubs/verify-cc/sponsors') return json(route, sponsorsPayload(SPONSORS, { player_cards: 'gold1' }))
    if (!url.includes('/public/availability/')) return json(route, {})
    if (/\/me\/cards$/.test(url)) return json(route, { club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: [], pack_size: 5, season: 'S', cards: [mineCard], totals: { regular_owned: 1, regular_total: 1, special_owned: 0, special_total: 0, copies: 1 } })
    if (/\/me\/profile/.test(url)) return json(route, { club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 0 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
    if (/\/me\/cards\/swaps/.test(url)) return json(route, { incoming: [], outgoing: [] })
    if (/\/me(\?|$)/.test(url)) return json(route, { club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
    return json(route, { club: CLUB, require_pin: true, has_availability: false, players: [{ id: 'p1', display_name: 'Barendse, Jack', has_phone: true }] })
  })
  await page.goto(`${BASE}/avail/tok123`)
  await page.waitForSelector('[data-cards-module]', { timeout: 20000 })
  await page.waitForTimeout(500)
  await page.click('[data-share-mine]')
  await page.waitForSelector('[data-share-sheet]')
  await page.waitForTimeout(400)
  const flat = () => page.locator('[data-share-sheet] div[aria-hidden="true"] img[src^="/api/images/sponsors/"]').evaluateAll(els => els.map(e => e.getAttribute('src').split('/')[4]).join(','))
  ck('the sheet\'s picture starts on the club\'s Player Cards pick', (await flat()) === 'gold1', await flat())
  ck('the picker starts on the club\'s choice', (await page.locator('[data-share-sponsor]').inputValue()) === '')
  await page.selectOption('[data-share-sponsor]', 'sil1')
  await page.waitForTimeout(300)
  ck('choosing a sponsor changes the picture that gets shared', (await flat()) === 'sil1', await flat())
  await page.selectOption('[data-share-sponsor]', 'none')
  await page.waitForTimeout(300)
  ck('No sponsor takes it off the picture', (await flat()) === '')
  await page.selectOption('[data-share-sponsor]', 'maj1')
  await page.click('[data-share-link]')
  await page.waitForFunction(() => /Link copied|did not work/.test(document.querySelector('[data-share-note]')?.textContent || ''))
  const copied = await page.evaluate(() => navigator.clipboard.readText()).catch(() => '')
  ck('the copied link carries the chosen sponsor', /\/players\/p1\/share\?sponsor=maj1$/.test(copied), copied)
  ck('390px: the sheet fits', await noSideScroll(page))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/share_sheet_sponsor_390.png` })
  ck('no page errors (share sheet)', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
