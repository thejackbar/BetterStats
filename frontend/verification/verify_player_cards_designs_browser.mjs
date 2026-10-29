// Club pack designs, in Chromium on the production build with the API stubbed:
//  * the admin Pack designs tab: pick a pack, upload a background and a centre picture (the request on the wire is multipart), change colours,
//    darkness and layout (one debounced PUT with only what changed), reset it, no horizontal scroll at 390px;
//  * the player's screens: a designed pack draws its background, centre picture and colours on Packs, Home and the opening screen, a pack
//    with no design keeps the built-in look, a design can hide the name, and the club's name for a kind of pack is used.
//
//   APP_URL=http://localhost:4173 node verification/verify_player_cards_designs_browser.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'
import { cardsUrl, goNav } from './lib/cardsPage.mjs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
if (SHOT) fs.mkdirSync(SHOT, { recursive: true })
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}
// A real 8x12 PNG, so the browser decodes what the stub serves.
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAgAAAAMCAIAAADQ/GvKAAAAEklEQVR4nGOQizqBFTGMSqAjABWGeAGPl/lFAAAAAElFTkSuQmCC', 'base64')
const CLUB = { name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c', font_config: {} }
const design = (target, x = {}) => ({ id: `d-${target}`, target, title: null, a: null, b: null, on: null, overlay: 0.25, show_name: true, show_logo: true, art_position: 'center', art_size: 'm', background_url: null, art_url: null, ...x })
const TARGETS = [
  { key: 'default', label: 'Every pack', group: 'All' }, { key: 'weekly', label: 'Weekly pack', group: 'Everyday' }, { key: 'century', label: 'Century pack', group: 'For what you do' },
  { key: 'melbourne_cup', label: 'Melbourne Cup pack', group: 'On the day' }, { key: 'event:e1', label: 'Boxing Day Test', group: 'Scheduled' },
]
const imageHits = []

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = []

  // ── The admin designer ──────────────────────────────────────────────────────
  console.log('\nthe designer')
  const state = { designs: {} }
  const calls = []
  const adminPayload = () => ({ club: CLUB, settings: { enabled: true, include_juniors: false, weekly_packs: 1, timezone: null, effective_timezone: 'Australia/Perth', event_packs_enabled: true, starter_gifts: 'minimal' }, events: [], designs: state.designs, design_targets: TARGETS, timezones: [], max_weekly_packs: 10, link: { path: '/playerdash/tok123' }, pool: { size: 0, players: 0 }, players: [] })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  page.setDefaultTimeout(10000)
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errors.push(m.text()) })
  await page.route('**/api/**', async (route) => {
    const req = route.request(), url = req.url(), method = req.method()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/api\/images\/card-packs\//.test(url)) { imageHits.push(url); return route.fulfill({ status: 200, contentType: 'image/png', body: PNG }) }
    if (/\/auth\/me/.test(url)) return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', entitlements: { modules: [], status: 'active' } })
    if (!/\/player-cards\//.test(url)) return json({})
    const path = new URL(url).pathname.replace(/^\/api/, '')
    const ct = req.headers()['content-type'] || ''
    const body = !ct.includes('multipart') && req.postData() ? JSON.parse(req.postData()) : null
    calls.push({ method, path, body, multipart: ct.includes('multipart') })
    const m = path.match(/^\/player-cards\/designs\/([^/]+)(?:\/(bg|art))?$/)
    if (m) {
      const target = decodeURIComponent(m[1]), kind = m[2]
      const cur = state.designs[target] || design(target)
      if (method === 'PUT') state.designs[target] = { ...cur, ...Object.fromEntries(Object.entries(body).map(([k, v]) => [({ color_a: 'a', color_b: 'b', color_on: 'on' })[k] || k, v])) }
      else if (method === 'POST') state.designs[target] = { ...cur, [kind === 'bg' ? 'background_url' : 'art_url']: `/api/images/card-packs/d-${target}/${kind}?v=${calls.length}` }
      else if (method === 'DELETE' && kind) state.designs[target] = { ...cur, [kind === 'bg' ? 'background_url' : 'art_url']: null }
      else if (method === 'DELETE') delete state.designs[target]
      return json({ designs: state.designs })
    }
    if (path === '/player-cards/overview') return json({ totals: {}, players: [] })
    if (path === '/player-cards/activity') return json({ daily: [], recent_specials: [], recent_cards: [], recent_openings: [] })
    return json(adminPayload())
  })
  await page.goto(`${BASE}/admin/player-cards`)
  await page.waitForSelector('[data-player-cards-admin]')
  await page.click('[data-pc-tab="designs"]')
  await page.waitForSelector('[data-pack-designs]')
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  check('the tab lists every pack kind and the scheduled event, grouped', (await page.locator('[data-design-target]').count()) === 5 && /scheduled/i.test(await page.locator('[data-design-targets]').innerText()))
  check('with no design the preview says it is the built-in look', /built-in look/.test(await page.locator('[data-design-preview]').innerText()) && (await page.locator('[data-pack-design-bg]').count()) === 0)
  check('there is nothing to reset yet, and no darkness or position controls without pictures', (await page.locator('[data-design-reset]').count()) === 0 && (await page.locator('[data-design-overlay]').count()) === 0)

  calls.length = 0
  await page.locator('[data-design-file="bg"]').setInputFiles({ name: 'pitch.png', mimeType: 'image/png', buffer: PNG })
  await page.waitForSelector('[data-pack-design-bg]')
  const up = calls.find((c) => c.method === 'POST')
  check('choosing a background uploads it as a multipart file to that pack, then draws it', up && up.path === '/player-cards/designs/default/bg' && up.multipart, JSON.stringify(up))
  check('the picture is fetched for the preview', imageHits.some((u) => /d-default\/bg/.test(u)))
  await page.locator('[data-design-file="art"]').setInputFiles({ name: 'cup.png', mimeType: 'image/png', buffer: PNG })
  await page.waitForSelector('[data-pack-design-art]')
  check('a centre picture draws on the pack too', (await page.locator('[data-design-preview] [data-pack-design-art]').count()) === 1)
  check('the darkness, position and size controls appear once there are pictures', (await page.locator('[data-design-overlay]').count()) === 1 && (await page.getByLabel('Centre picture position').count()) === 1)

  calls.length = 0
  await page.locator('[data-design-overlay]').evaluate((el) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; for (const v of ['0.3', '0.45', '0.6']) { set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })) } })
  await page.waitForTimeout(900)
  const puts = calls.filter((c) => c.method === 'PUT')
  check('dragging the darkness slider sends one save with only that value', puts.length === 1 && JSON.stringify(puts[0].body) === '{"overlay":0.6}', JSON.stringify(puts))
  calls.length = 0
  await page.getByLabel('Centre picture size').selectOption('l')
  await page.getByLabel('Centre picture position').selectOption('bottom')
  await page.waitForTimeout(900)
  check('size and position go together in one save', calls.filter((c) => c.method === 'PUT').length === 1 && JSON.stringify(calls.find((c) => c.method === 'PUT').body) === '{"art_size":"l","art_position":"bottom"}', JSON.stringify(calls))
  calls.length = 0
  await page.locator('[data-design-colour="Foil colour"] input').evaluate((el) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(el, '#1d4ed8'); el.dispatchEvent(new Event('input', { bubbles: true })) })
  await page.waitForTimeout(900)
  check('a colour is sent under its API name, lower case hex', JSON.stringify(calls.find((c) => c.method === 'PUT')?.body) === '{"color_a":"#1d4ed8"}', JSON.stringify(calls))
  await page.locator('[data-design-colour="Foil colour"] button', { hasText: 'Use built in' }).click()
  await page.waitForTimeout(900)
  check('"Use built in" sends an explicit null', JSON.stringify(calls.filter((c) => c.method === 'PUT').pop()?.body) === '{"color_a":null}')
  calls.length = 0
  await page.getByRole('switch', { name: "Show the pack's name" }).click()
  await page.waitForTimeout(900)
  check('hiding the name sends show_name false and takes the name off the preview', JSON.stringify(calls.find((c) => c.method === 'PUT')?.body) === '{"show_name":false}' && (await page.locator('[data-design-preview] [data-pack-name]').count()) === 0)
  await page.getByRole('switch', { name: "Show the pack's name" }).click()
  await page.waitForTimeout(900)

  await page.click('[data-design-target="century"]')
  check('another pack starts from its own design (none), not the last one', (await page.locator('[data-design-preview] [data-pack-design-bg]').count()) === 0 && /built-in look/.test(await page.locator('[data-design-preview]').innerText()))
  check('a kind of pack can be given a name of its own, an event cannot (it has its own)', (await page.getByLabel('Name on the pack').count()) === 1)
  calls.length = 0
  await page.getByLabel('Name on the pack').fill('Ton Up')
  await page.waitForTimeout(900)
  check('the name saves, and the preview uses it', JSON.stringify(calls.find((c) => c.method === 'PUT')?.body) === '{"title":"Ton Up"}' && /Ton Up/i.test(await page.locator('[data-design-preview] [data-pack-name]').innerText()))
  await page.click('[data-design-target="event:e1"]')
  check('a scheduled event has no name field and shows its own title', (await page.getByLabel('Name on the pack').count()) === 0)
  await page.click('[data-design-target="default"]')
  check('a designed pack has a dot in the list', (await page.locator('[data-design-target="default"] [aria-label="Has a design"]').count()) === 1 && (await page.locator('[data-design-target="weekly"] [aria-label="Has a design"]').count()) === 0)
  if (SHOT) await page.screenshot({ path: `${SHOT}/designs-admin-1280.png`, fullPage: true })
  calls.length = 0
  await page.locator('[data-design-slot="art"] button', { hasText: 'Remove' }).click()
  await page.waitForFunction(() => !document.querySelector('[data-design-preview] [data-pack-design-art]'))
  check('removing a picture sends a DELETE for that slot', calls.some((c) => c.method === 'DELETE' && c.path === '/player-cards/designs/default/art'))
  await page.locator('[data-design-reset]').click()
  check('reset asks first', (await page.getByText('Take this pack back to the built-in look?').count()) === 1 && !calls.some((c) => c.method === 'DELETE' && c.path === '/player-cards/designs/default'))
  await page.getByRole('button', { name: 'Yes, reset it' }).click()
  await page.waitForFunction(() => !document.querySelector('[data-design-preview] [data-pack-design-bg]'))
  check('...and then sends a DELETE for the whole design', calls.some((c) => c.method === 'DELETE' && c.path === '/player-cards/designs/default'))
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(300)
  check('no horizontal scroll at 390px', (await overflow()) <= 0, `over by ${await overflow()}px`)
  if (SHOT) await page.screenshot({ path: `${SHOT}/designs-admin-390.png`, fullPage: true })
  await ctx.close()

  // ── What players see ────────────────────────────────────────────────────────
  console.log('\nwhat players see')
  const DESIGNS = {
    default: design('default', { background_url: '/api/images/card-packs/d-default/bg?v=1', art_url: '/api/images/card-packs/d-default/art?v=1', a: '#1d4ed8', b: '#0b1a4a', on: '#ffffff', overlay: 0.3 }),
    century: design('century', { title: 'Ton Up', background_url: '/api/images/card-packs/d-century/bg?v=1', show_name: false, show_logo: false }),
  }
  const PACKS = [{ id: 'k1', source: 'weekly', label: 'Weekly pack', design: DESIGNS.default }, { id: 'k2', source: 'century', label: 'Ton Up', design: DESIGNS.century }, { id: 'k3', source: 'runs', label: 'Runs pack', design: null }]
  const card = (pid, name, tier, x = {}) => ({ kind: 'player', key: `p:${pid}`, player_id: pid, name, photo_url: null, hero_photo_url: null, matches: 100, runs: 1500, bat_avg: 24.5, wickets: 20, bowl_avg: 31.2, dismissals: 30, rarity: 60, tier, copies: 1, obtained_at: '2026-10-20T01:00:00Z', mine: false, ...x })
  const CARDS = [card('p1', 'Barendse, Jack', 'rare', { mine: true }), card('p2', 'Zed, Alan', 'common')]
  const open = async (width, route) => {
    const c = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500 })
    const p = await c.newPage()
    p.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|font/i.test(m.text())) errors.push(m.text()) })
    p.on('pageerror', (e) => errors.push(String(e)))
    await p.route('**/api/**', async (r) => {
      const url = r.request().url()
      const json = (b) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
      if (/\/api\/images\/card-packs\//.test(url)) return r.fulfill({ status: 200, contentType: 'image/png', body: PNG })
      if (!url.includes('/public/availability/')) return json({})
      if (/\/me\/cards\/packs\/[^/]+\/open$/.test(url)) return json({ cards: [CARDS[1]], packs_left: 2 })
      if (/\/me\/cards\/(showcase|feed|board|sets|swaps|wants)/.test(url)) return json({ cards: [], events: [], entries: [], sets: [], max: 6, incoming: [], outgoing: [], recent: [], mine: [], people: [], wants: [], ready: 0, limit: 100 })
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: PACKS, pack_designs: DESIGNS, pack_size: 5, season: 'Summer', cards: CARDS, totals: { regular_owned: 2, regular_total: 14, special_owned: 0, special_total: 0, copies: 2 }, features: { sets: true, showcase: true, board: true, feed: true } })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 3, swaps_waiting: 0 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
      if (/\/me(\?|$)/.test(url)) return json({ club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
      return json({ club: CLUB, require_pin: true, has_availability: false, players: [{ id: 'p1', display_name: 'Barendse, Jack', has_phone: true }] })
    })
    await p.goto(cardsUrl(BASE, 'tok123', route))
    await p.waitForSelector('[data-cards-page] [data-screen]', { timeout: 20000 })
    await p.waitForTimeout(400)
    return { c, p }
  }
  {
    const { c, p } = await open(1280, '/packs')
    const way = (k) => p.locator(`[data-way="${k}"] [data-pack-art]`)
    check('a kind of pack with a design of its own draws it', (await p.locator('[data-way="century"] [data-pack-design-bg]').count()) === 1 && (await way('century').getAttribute('data-pack-designed')) === 'yes')
    check('a kind with no design of its own takes the club default (background and centre picture)', (await p.locator('[data-way="halloween"] [data-pack-design-bg]').count()) === 1 && (await p.locator('[data-way="halloween"] [data-pack-design-art]').count()) === 1)
    check('a design that hides the name and the logo hides them', (await p.locator('[data-way="century"] [data-pack-name]').count()) === 0 && (await p.locator('[data-way="century"] [data-pack-stars]').count()) === 0)
    check('the list uses the club\'s name for that kind of pack, and the default design\'s name never', /Ton Up/.test(await p.locator('[data-way="century"]').innerText()) && /Weekly pack/.test(await p.locator('[data-way="weekly"]').innerText()))
    const bgStyle = await p.locator('[data-way="century"] [data-pack-design-bg]').evaluate((el) => getComputedStyle(el).backgroundImage)
    check('the background is the club\'s picture, covering the pack', /card-packs\/d-century\/bg/.test(bgStyle))
    const shape = await p.evaluate(() => [...document.querySelectorAll('[data-pack-art]')].map((a) => +(a.getBoundingClientRect().height / a.getBoundingClientRect().width).toFixed(2)))
    check('designed or not, every pack is still the same shape', shape.length >= 22 && shape.every((r) => Math.abs(r - 1.5) < 0.03), JSON.stringify(shape.filter((r) => Math.abs(r - 1.5) >= 0.03)))
    check('the packs to open show their designs (weekly and century designed, runs plain)', (await p.locator('[data-packs-ready]').locator('..').locator('[data-pack-art]').count()) >= 1)
    if (SHOT) await p.screenshot({ path: `${SHOT}/designs-player-packs-1280.png`, fullPage: true })
    await p.locator('[data-open-next]').click()
    await p.waitForSelector('[data-pack-sealed]')
    check('the pack that tears open is the designed one', (await p.locator('[data-pack-sealed] [data-pack-design-bg]').count()) === 1 && (await p.locator('[data-pack-sealed] [data-pack-design-art]').count()) === 1)
    if (SHOT) await p.screenshot({ path: `${SHOT}/designs-player-opening-1280.png` })
    await c.close()
  }
  {
    const { c, p } = await open(390, '')
    check('Home shows the next pack with its design at 390px', (await p.locator('[data-open-pack] [data-pack-design-bg]').count()) === 1)
    check('no horizontal scroll on Home at 390px', (await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 0)
    if (SHOT) await p.screenshot({ path: `${SHOT}/designs-player-home-390.png` })
    await c.close()
  }
  {
    // A club with no designs at all keeps the built-in look everywhere.
    const c = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const p = await c.newPage()
    await p.route('**/api/**', async (r) => {
      const url = r.request().url()
      const json = (b) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
      if (!url.includes('/public/availability/')) return json({})
      if (/\/me\/cards\/(showcase|feed|board|sets|swaps|wants)/.test(url)) return json({ cards: [], events: [], entries: [], sets: [], max: 6, incoming: [], outgoing: [], recent: [], mine: [], people: [], wants: [], ready: 0, limit: 100 })
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: [{ id: 'k1', source: 'weekly', label: 'Weekly pack', design: null }], cards: CARDS, totals: { regular_owned: 2, regular_total: 14, special_owned: 0, special_total: 0, copies: 2 }, features: {} })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 1, swaps_waiting: 0 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
      if (/\/me(\?|$)/.test(url)) return json({ club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
      return json({ club: CLUB, require_pin: true, has_availability: false, players: [{ id: 'p1', display_name: 'Barendse, Jack', has_phone: true }] })
    })
    await p.goto(cardsUrl(BASE, 'tok123', '/packs'))
    await p.waitForSelector('[data-screen="packs"] [data-way]', { timeout: 20000 })
    check('a club with no designs, and an older server that sends no pack_designs, keeps the built-in look and does not crash', (await p.locator('[data-pack-designed="yes"]').count()) === 0 && (await p.locator('[data-pack-design-bg]').count()) === 0 && (await p.locator('[data-way]').count()) === 23)
    await c.close()
  }
  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
