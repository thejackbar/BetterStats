// Shared harness for the phone-size admin checks. Drives the REAL screens in
// Chromium with the API stubbed at the network layer. The context is a real
// mobile one (isMobile + hasTouch): on a phone, a page wider than the screen
// does not scroll sideways politely, it widens the LAYOUT viewport, which is why
// a `position: fixed` box centred itself off screen and needed zooming out.
//
//   npx vite preview --outDir <dist> --port 5199 &
import { chromium } from 'playwright'

export const BASE = process.env.APP_URL || 'http://localhost:5199'
export const PHONE = { width: 390, height: 844 }

export const ME = {
  id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1',
  display_name: 'Jordan Admin',
  capabilities: ['*'], entitlements: { modules: ['select', 'admin', 'fees', 'comms', 'merch'], status: 'active' },
}

export const json = (r, body, status = 200) =>
  r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

export async function launch({ viewport = PHONE, mobile = true } = {}) {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({
    viewport, deviceScaleFactor: 2, isMobile: mobile, hasTouch: mobile,
    userAgent: mobile ? 'Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36' : undefined,
  })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('dialog', (d) => d.accept())
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route('**/api/club-admin/settings', (r) => json(r, { name: 'Applecross Cricket Club', slug: 'applecross' }))
  return { browser, ctx, page, errors }
}

// How far the document is wider than the screen, and which elements stick out.
export async function overflow(page, screenW = PHONE.width) {
  return page.evaluate((vw) => {
    // On a phone an over-wide page does not scroll sideways: the browser widens
    // the layout viewport to fit it (innerWidth jumps past the screen). So the
    // screen width is passed in, never read back from the page.
    const doc = document.documentElement
    const wide = []
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect()
      if (r.width === 0 || r.height === 0) continue
      if (r.right > vw + 1 && getComputedStyle(el).position !== 'fixed') {
        // Skip anything that scrolls inside its own box.
        let p = el.parentElement, clipped = false
        while (p && p !== document.body) {
          const o = getComputedStyle(p)
          if (/(auto|scroll|hidden)/.test(o.overflowX) && p.getBoundingClientRect().right <= vw + 1) { clipped = true; break }
          p = p.parentElement
        }
        if (!clipped) wide.push(`${el.tagName.toLowerCase()}.${String(el.className).split(/\s+/).slice(0, 3).join('.')} right=${Math.round(r.right)}`)
      }
    }
    return { vw, innerWidth: window.innerWidth, scrollWidth: doc.scrollWidth, over: Math.max(doc.scrollWidth, window.innerWidth) - vw, wide: wide.slice(0, 6) }
  }, screenW)
}

// ── Stubs for the three screens ───────────────────────────────────────────
export function stubAccounts(page, n = 24) {
  const tiers = ['Mens - Established Membership', 'Mens - New Membership', 'Complimentary Season', 'Closed Account - Anushka Abeyrathna']
  const members = Array.from({ length: n }, (_, i) => ({
    member_id: `m${i}`, member_season_id: `ms${i}`, full_name: ['Abbas, Aamir', 'Abeygunasekara, Gihan', 'Acharige, Pasindu', 'Ashworth, Shayne'][i % 4] + (i > 3 ? ` ${i}` : ''),
    is_linked: true, membership_type_id: null, tier: tiers[i % 4], needs_tier: false, playhq_registered: i % 2 === 0,
    match_days: i % 3, total_payable: 250, total_paid: i % 3 ? 0 : 250, total_outstanding: i % 3 ? 250 : 0,
    status: i % 3 ? 'non_financial' : 'financial', in_credit: false, credit: 0,
  }))
  const summary = { total_members: n, non_financial: Math.round(n * 2 / 3), needs_tier: 0, playhq_missing: 12, total_payable: 35595, total_paid: 19290, total_outstanding: 16305 }
  return Promise.all([
    page.route('**/api/club-admin/seasons', (r) => json(r, [{ id: 's1', name: 'Summer 2026/27', year: 2026 }, { id: 's0', name: 'Summer 2025/26', year: 2025 }])),
    page.route(/\/api\/club-admin\/fees\/members\?/, (r) => json(r, { members, summary })),
    page.route(/\/api\/club-admin\/fees\/schedule/, (r) => json(r, [])),
    page.route(/\/api\/club-admin\/fees\/membership-types/, (r) => json(r, { types: [] })),
    page.route(/\/api\/club-admin\/directory\/people/, (r) => json(r, { people: [], membership_types: [], genders: [], squads: [], tiers: [] })),
  ])
}

export function stubSquads(page) {
  const mk = (i, name, squad) => ({
    id: `p${i}`, name, display_name: name, status: 'active', is_player: true, gender: 'male', skill_positions: i % 3 === 0 ? ['BAT'] : ['BWL'],
    squad_team_ids: squad ? [squad] : [], last_played: '2026-03-01',
  })
  const players = [
    mk(1, 'Abbas, Aamir', 't1'), mk(2, 'Ashworth, Shayne', 't1'), mk(3, 'Barker, David', 't1'), mk(4, 'Barendse, Jack', 't1'),
    mk(5, 'Kumar, Raj', 't2'), mk(6, 'Singh, Amit', null),
  ]
  const matrix = { dates: [{ date: '2027-04-20' }], availability: { p1: { '2027-04-20': { status: 'AVAILABLE' } }, p2: { '2027-04-20': { status: 'UNAVAILABLE' } } }, dormancy_months: 24 }
  return Promise.all([
    page.route(/\/api\/teams(\?.*)?$/, (r) => json(r, [{ id: 't1', name: 'Applecross 1st XI', short_name: '1st XI', sequence: 1 }, { id: 't2', name: 'Applecross 2nd XI', short_name: '2nd XI', sequence: 2 }])),
    page.route('**/api/club-admin/players', (r) => json(r, players)),
    page.route('**/api/availability/matrix', (r) => json(r, matrix)),
    page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] })),
    page.route('**/api/availability', (r) => json(r, { status: 'ok' })),
  ])
}

// The Players page: the roster and matrix from the Squads stub, plus a profile.
export async function stubPlayers(page) {
  await stubSquads(page)
  await page.route(/\/api\/players\/[^/]+\/aliases/, (r) => json(r, []))
  await page.route(/\/api\/players\/[^/]+\/profile/, (r) => {
    const id = r.request().url().match(/players\/([^/]+)\/profile/)[1]
    json(r, { id, name: `Player ${id}`, display_name: `Player ${id}`, status: 'active', is_player: true, gender: 'male', skill_positions: ['BAT'], squad_team_ids: [], availability_snapshot: [], dates: [] })
  })
}
