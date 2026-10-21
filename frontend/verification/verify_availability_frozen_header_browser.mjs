// Drives the real BetterSelect Availability matrix in Chromium with the API
// stubbed at the network layer. Ask (Oct 2026): keep the top row with the dates
// visible while scrolling the players, like the Selection Whiteboard does.
//
// The header cells were already `sticky top-0`, but the card around the table was
// `overflow-auto` with no height, so it never scrolled and the page did: nothing
// for the header to stick to. The card now has a measured height (useFitHeight,
// lg and up) and scrolls inside itself.
//
//   APP_URL=http://localhost:4173 node verify_availability_frozen_header_browser.mjs
//   (serve a production build; never rebuild dist under a running server)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}
const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const iso = (daysAgo) => plusDays(-daysAgo)
const W1 = plusDays(3), W2 = plusDays(10), W3 = plusDays(17)

const N = 60
const P = (id, name) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null, is_player: true,
  player_role: null, status: 'active', is_current: true, is_dormant: false, is_inactive: false,
  squads: [], last_played: iso(20), age: null,
})
const players = Array.from({ length: N }, (_, i) => P('p' + i, 'Player ' + String(i).padStart(2, '0')))
const MATRIX = {
  dates: [W1, W2, W3].map((date, i) => ({ date, fixtures: [{ id: 'f' + i, opponent_name: 'Opp ' + i, home_away: 'HOME', role: 'single', two_day: false }] })),
  players,
  all_squads: [], dormancy_months: 24, rules: { active: false, applied: [] },
  availability: Object.fromEntries(players.map((p, i) => [p.id, { [W1]: { status: i % 2 ? 'AVAILABLE' : 'UNAVAILABLE', source: 'admin' } }])),
}
const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1',
  club_slug: 'verify-cc', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
async function stub(page) {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json(ME)
    if (url.includes('/availability/matrix')) return json(MATRIX)
    if (url.includes('/selection/selected-players')) return json({ player_ids: [] })
    return json({})
  })
}
const geo = (page) => page.evaluate(() => {
  const card = document.querySelector('[data-avail-matrix]')
  const th = card?.querySelector('thead th:nth-child(2)')
  const corner = card?.querySelector('thead th:nth-child(1)')
  const rect = (el) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left } }
  const c = card && rect(card), t = th && rect(th)
  let topmost = null
  if (th) { const r = th.getBoundingClientRect(); const hit = document.elementFromPoint(r.left + r.width / 2, r.top + 6); topmost = !!hit && th.contains(hit) }
  return {
    has: !!card, fit: card?.getAttribute('data-fit'), card: c, th: t, corner: corner && rect(corner), topmost,
    cardScroll: card?.scrollTop ?? null, cardClient: card?.clientHeight ?? null, cardScrollH: card?.scrollHeight ?? null,
    scrollY: window.scrollY, innerH: window.innerHeight,
  }
})

const open = async (browser, width, height, ctxOpts = {}) => {
  const ctx = await browser.newContext({ viewport: { width, height }, ...ctxOpts })
  const page = await ctx.newPage()
  page.errors = []
  page.on('pageerror', (e) => page.errors.push(String(e)))
  await stub(page)
  await page.goto(`${BASE}/admin/betterselect/availability`)
  await page.waitForSelector('tbody tr', { timeout: 20000 })
  await page.waitForTimeout(500)
  return page
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  for (const [w, h] of [[1440, 900], [1280, 720], [1440, 600]]) {
    const page = await open(browser, w, h)
    let g = await geo(page)
    check(`${w}x${h}: the matrix card is found with ${N} players`, g.has && (await page.locator('tbody tr').count()) === N)
    check(`${w}x${h}: card is fitted to the window`, g.fit === 'on' && g.card.bottom <= g.innerH + 1, JSON.stringify(g.card) + ' fit=' + g.fit)
    check(`${w}x${h}: card scrolls inside itself (content taller than card)`, g.cardScrollH > g.cardClient + 100, `${g.cardScrollH} vs ${g.cardClient}`)

    // Wheel over the players, a long way, as a real scroll would.
    const cx = g.card.left + 600, cy = g.card.top + (g.cardClient / 2)
    await page.mouse.move(cx, cy)
    await page.mouse.wheel(0, 1200)
    await page.waitForTimeout(300)
    g = await geo(page)
    check(`${w}x${h}: wheel scrolled the players, not the page`, g.cardScroll > 400 && g.scrollY < 5, `card=${g.cardScroll} page=${g.scrollY}`)
    check(`${w}x${h}: date row stays at the top of the card`, Math.abs(g.th.top - g.card.top) <= 3, `th=${g.th.top} card=${g.card.top}`)
    check(`${w}x${h}: date row is still on screen`, g.th.top >= 0 && g.th.bottom <= g.innerH, JSON.stringify(g.th))
    check(`${w}x${h}: date row is what you hit there (nothing scrolls over it)`, g.topmost === true)
    check(`${w}x${h}: Player corner cell frozen too`, Math.abs(g.corner.top - g.card.top) <= 3 && Math.abs(g.corner.left - g.card.left) <= 3)

    // Scroll sideways too: the Player column and the date row both hold.
    await page.evaluate(() => { document.querySelector('[data-avail-matrix]').scrollLeft = 200 })
    await page.waitForTimeout(150)
    g = await geo(page)
    check(`${w}x${h}: corner holds when scrolled across as well`, Math.abs(g.corner.top - g.card.top) <= 3 && Math.abs(g.corner.left - g.card.left) <= 3, JSON.stringify(g.corner))
    check(`${w}x${h}: no page errors`, page.errors.length === 0, page.errors.join(' | '))
    if (process.env.SHOT_DIR && w === 1440 && h === 900) await page.screenshot({ path: process.env.SHOT_DIR + '/avail_frozen_desktop.png' })
    await page.context().close()
  }

  // Window resized after load: the card follows.
  {
    const page = await open(browser, 1440, 900)
    await page.setViewportSize({ width: 1440, height: 650 })
    await page.waitForTimeout(400)
    const g = await geo(page)
    check('resize 900 -> 650: card still ends inside the window', g.card.bottom <= g.innerH + 1, JSON.stringify(g.card))
    await page.context().close()
  }

  // Phone: unchanged. No fixed height, no sideways overflow.
  {
    const page = await open(browser, 390, 844, { hasTouch: true, isMobile: true })
    const g = await geo(page)
    const over = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: screen.width }))
    check('390px: card is left alone (no fitted height)', g.fit === 'off')
    check('390px: page does not overflow sideways', over.sw <= over.cw, JSON.stringify(over))
    check('390px: no page errors', page.errors.length === 0, page.errors.join(' | '))
    if (process.env.SHOT_DIR) await page.screenshot({ path: process.env.SHOT_DIR + '/avail_frozen_390.png' })
    await page.context().close()
  }

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
