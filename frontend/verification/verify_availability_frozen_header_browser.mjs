// Drives the real BetterSelect Availability matrix in Chromium with the API
// stubbed at the network layer.
//
// Oct 2026: the date row must stay visible while the players scroll past.
// Nov 2026: the fitted-height card (useFitHeight) left only ~3 rows visible when
// the filters above were tall. The list now flows down the page (no inner
// vertical scroll). The date row is a separate strip, sticky under the layout's
// own header, kept in step with the body's sideways scroll through one shared
// colgroup. Run with a TALL stack above the matrix (the 600px window) as well.
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
const DAYS = Array.from({ length: 14 }, (_, i) => plusDays(3 + 7 * i))
const W1 = DAYS[0]

const N = 60
const P = (id, name) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null, is_player: true,
  player_role: null, status: 'active', is_current: true, is_dormant: false, is_inactive: false,
  squads: [], last_played: iso(20), age: null,
})
const players = Array.from({ length: N }, (_, i) => P('p' + i, 'Player ' + String(i).padStart(2, '0')))
const MATRIX = {
  dates: DAYS.map((date, i) => ({ date, fixtures: [{ id: 'f' + i, opponent_name: 'Opp ' + i, home_away: 'HOME', role: 'single', two_day: false }] })),
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
  const headEl = card?.querySelector('[data-avail-head]')
  const bodyEl = card?.querySelector('[data-avail-body]')
  const layoutHeader = document.querySelector('header.sticky')
  const rect = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, width: r.width } }
  const th = headEl?.querySelector('th:nth-child(3)'), td = bodyEl?.querySelector('tbody tr td:nth-child(3)')
  const corner = headEl?.querySelector('th:nth-child(1)')
  let topmost = null
  if (th) { const r = th.getBoundingClientRect(); const hit = document.elementFromPoint(r.left + r.width / 2, r.top + 6); topmost = !!hit && th.contains(hit) }
  return {
    has: !!card, card: rect(card), head: rect(headEl), th: rect(th), td: rect(td), corner: rect(corner), layoutBottom: layoutHeader ? layoutHeader.getBoundingClientRect().bottom : 0,
    topmost, rows: bodyEl ? bodyEl.querySelectorAll('tbody tr').length : 0,
    bodyClient: bodyEl?.clientHeight ?? null, bodyScrollH: bodyEl?.scrollHeight ?? null,
    headLeft: headEl?.scrollLeft ?? null, bodyLeft: bodyEl?.scrollLeft ?? null,
    scrollY: window.scrollY, innerH: window.innerHeight, docH: document.documentElement.scrollHeight,
    lastRow: bodyEl ? rect(bodyEl.querySelector('tbody tr:last-child')) : null,
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
    check(`${w}x${h}: the matrix is found with ${N} players`, g.has && g.rows === N, `rows=${g.rows}`)
    check(`${w}x${h}: card is NOT cut to the window (it runs off the page)`, g.card.bottom > g.innerH + 200, JSON.stringify(g.card))
    check(`${w}x${h}: no inner vertical scroll (body is as tall as its rows)`, g.bodyScrollH <= g.bodyClient + 1, `${g.bodyScrollH} vs ${g.bodyClient}`)
    check(`${w}x${h}: the page is long enough to scroll the whole list`, g.docH > g.innerH + 800, `${g.docH}`)

    // Wheel over the players: the PAGE scrolls.
    await page.mouse.move(g.card.left + 600, Math.min(g.innerH - 80, g.card.top + 400))
    await page.mouse.wheel(0, 1200)
    await page.waitForTimeout(300)
    g = await geo(page)
    check(`${w}x${h}: wheel scrolled the page`, g.scrollY > 800, `page=${g.scrollY}`)
    check(`${w}x${h}: date row pinned just under the page header`, Math.abs(g.head.top - g.layoutBottom) <= 2, `head=${g.head.top} header=${g.layoutBottom}`)
    check(`${w}x${h}: date row is on screen and is what you hit there`, g.th.top >= 0 && g.th.bottom <= g.innerH && g.topmost === true, JSON.stringify(g.th))
    check(`${w}x${h}: Player corner cell pinned with it`, Math.abs(g.corner.top - g.head.top) <= 2)

    // To the very end: the last player is reachable and fully visible.
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
    await page.waitForTimeout(200)
    g = await geo(page)
    check(`${w}x${h}: last player reachable by scrolling the page`, g.lastRow.bottom <= g.innerH + 1 && g.lastRow.top >= 0, JSON.stringify(g.lastRow))

    // Sideways: the strip follows the body and the columns still line up.
    await page.evaluate(() => { document.querySelector('[data-avail-body]').scrollLeft = 200 })
    await page.waitForTimeout(150)
    g = await geo(page)
    check(`${w}x${h}: date strip follows the sideways scroll`, g.bodyLeft > 100 && g.headLeft === g.bodyLeft, `head=${g.headLeft} body=${g.bodyLeft}`)
    check(`${w}x${h}: a date column lines up with its cells`, Math.abs(g.th.left - g.td.left) <= 1 && Math.abs(g.th.width - g.td.width) <= 1, `${JSON.stringify(g.th)} ${JSON.stringify(g.td)}`)
    await page.evaluate(() => { document.querySelector('[data-avail-head]').scrollLeft = 80 })
    await page.waitForTimeout(150)
    g = await geo(page)
    check(`${w}x${h}: scrolling the strip drags the body`, g.bodyLeft === 80 && g.headLeft === 80, `head=${g.headLeft} body=${g.bodyLeft}`)
    check(`${w}x${h}: no page errors`, page.errors.length === 0, page.errors.join(' | '))
    if (process.env.SHOT_DIR && w === 1440 && h === 900) {
      await page.evaluate(() => window.scrollTo(0, 500))
      await page.screenshot({ path: process.env.SHOT_DIR + '/avail_flow_desktop.png' })
    }
    await page.context().close()
  }

  // Phone: no sideways overflow of the page, list still flows.
  {
    const page = await open(browser, 390, 844, { hasTouch: true, isMobile: true })
    const g = await geo(page)
    const over = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: screen.width }))
    check('390px: no inner vertical scroll', g.bodyScrollH <= g.bodyClient + 1)
    check('390px: page does not overflow sideways', over.sw <= over.cw, JSON.stringify(over))
    check('390px: no page errors', page.errors.length === 0, page.errors.join(' | '))
    if (process.env.SHOT_DIR) await page.screenshot({ path: process.env.SHOT_DIR + '/avail_flow_390.png' })
    await page.context().close()
  }

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
