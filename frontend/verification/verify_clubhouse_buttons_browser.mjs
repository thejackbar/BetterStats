// The BetterAdmin button rows, against the REAL screens with the API stubbed
// at the network layer.
//
// What is asserted, per screen:
//   * the button row wears Committee's own segmented control — one box with a
//     border and a surface2 fill, measured off the computed style rather than
//     off a class name, so a lookalike built by hand fails;
//   * the row is CENTRED on the title line, measured as "its midpoint sits
//     within a few px of the header's" — the thing that was actually asked
//     for, and the thing a class name cannot prove;
//   * a search box sits on its OWN line, below the caption;
//   * typing into that box keeps the caret, character by character. `fill()`
//     cannot catch the render-declared-component bug (it sets the value in one
//     shot), so every character is typed and focus re-checked after each.
//   * no page errors, and no horizontal overflow at 390px.
//
//   node verify_clubhouse_buttons_browser.mjs   (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const SEASON = { id: 'se1', name: 'Summer 2025/26', year: 2025 }

// ── The stub ────────────────────────────────────────────────────────────────
// Every endpoint the changed screens touch. Shapes copied from the routers, in
// particular `GET /assets/items` → { assets: [...] }, which is the exact key
// the Facilities screen was reading wrongly.
// `name`, not `full_name` — the key services/directory.py actually emits.
const PEOPLE = [
  { key: 'p1', member_id: 'm1', player_id: 'pl1', name: 'Amardeep Gill', email: 'a@x.com', phone: '', photo: null,
    segs: ['Player', 'Volunteer'], membership_types: [{ id: 't1', name: 'Senior Player' }], roles: [],
    player_status: 'active', archived: false, category: null, squad: null, tier: null },
  { key: 'p2', member_id: 'm2', player_id: null, name: 'Bev Naylor', email: '', phone: '', photo: null,
    segs: ['Committee'], membership_types: [], roles: [], player_status: null,
    archived: false, category: 'committee', squad: null, tier: null },
]
const FACILITIES = [
  { id: 'f1', name: 'Main Ground', facility_type: 'ground', is_active: true, description: null, key_location: 'Clubroom hook' },
  { id: 'f2', name: 'Nets', facility_type: 'nets', is_active: true, description: null, key_location: null },
]
const ASSETS = [
  { id: 'a1', name: 'Bowling machine', category: 'equipment', condition: 'good', status: 'in_service', is_active: true },
]
const BOOKINGS = [
  { id: 'b1', facility_id: 'f1', title: 'Doyle engagement', starts_at: null, ends_at: null },
]
const DIARY_BOARD = [
  { id: 'd1', title: 'Renew public liability', frequency: 'annual', status: 'open',
    start_date: null, due_date: null, responsibility_role_id: null, budget_estimate: 0, actual_expenditure: 0, depends_on: [] },
  { id: 'd2', title: 'Quarterly BAS', frequency: 'quarterly', status: 'open',
    start_date: null, due_date: null, responsibility_role_id: null, budget_estimate: 0, actual_expenditure: 0, depends_on: [] },
]

const routes = (page, calls) => page.route('**/api/**', async (route) => {
  const url = route.request().url()
  calls.push(url)
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

  if (url.includes('/auth/me')) {
    return json({
      id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' },
    })
  }
  // Directory + the shared People filters
  if (url.includes('/directory/people')) {
    return json({ people: PEOPLE, membership_types: [{ id: 't1', name: 'Senior Player', scope: 'internal' }],
                  genders: ['male'], squads: [], tiers: [], tier_season: null })
  }
  // Facilities — note `assets`, not `items`.
  if (/\/assets\/items/.test(url)) return json({ assets: ASSETS })
  if (/\/assets\/facilities/.test(url)) return json({ facilities: FACILITIES })
  if (/\/assets\/bookings/.test(url)) return json({ bookings: BOOKINGS })
  if (/\/assets\/maintenance-logs/.test(url)) return json({ logs: [] })
  if (url.includes('/facility-requests')) return json({ requests: [] })
  // Roster
  if (/\/roster\/week/.test(url)) {
    return json({ week: { id: 'w1', week_start: '2026-08-17', status: 'draft', version: 1 },
                  areas: [{ id: 'ar1', name: 'Canteen', department: 'Food', color: null, patterns: [] }],
                  shifts: [], candidates: [], members: [], settings: {} })
  }
  if (/\/roster\/areas/.test(url)) return json({ areas: [] })
  if (/\/roster\/departments/.test(url)) return json({ departments: [] })
  if (/\/roster\/hours/.test(url)) return json({ rows: [], totals: {} })
  // Areas & roles catalogues
  if (/\/role-types/.test(url)) return json({ types: [{ id: 'rt1', name: 'Volunteer', category: 'volunteer' }] })
  if (/\/activity-types/.test(url)) return json({ types: [] })
  if (/\/activities/.test(url)) return json({ activities: [] })
  if (/\/roles/.test(url)) return json({ roles: [{ id: 'r1', title: 'Scorer', role_type_name: 'Volunteer', is_committee: false }] })
  if (/\/qualifications\/types|\/qual-types/.test(url)) return json({ types: [] })
  // Club diary
  if (/\/club-diary\/board/.test(url)) return json({ tasks: DIARY_BOARD })
  if (/\/club-diary\/definitions/.test(url)) return json({ definitions: [] })
  if (/\/club-diary\/season-years|\/club-diary\/seasons/.test(url)) return json({ years: [2025] })
  // Events
  if (/\/events\/types/.test(url)) return json({ types: [] })
  if (/\/events\/[^/]+\/registrations/.test(url)) return json({ registrations: [], registered_count: 0, capacity: 0 })
  if (/\/committee\/events|\/events(\?|$)/.test(url)) {
    return json([{ id: 'e1', title: 'Presentation night', starts_at: '2026-09-01T18:00:00Z',
                   location: 'Clubrooms', capacity: 100, is_ticketed: true, ticket_price_cents: 2500, registration_open: true }])
  }
  // Fees
  if (/\/fees\/seasons/.test(url)) return json({ seasons: [SEASON] })
  if (/\/fees\/members\b|\/fees\/members\?/.test(url)) {
    return json({ members: [{ id: 'm1', member_id: 'm1', full_name: 'Amardeep Gill', tier_name: 'Senior',
                              total_payable: 200, total_paid: 100, outstanding: 100, status: 'non_financial',
                              playhq_registered: false, is_new_registration: false }],
                  summary: { total_outstanding: 100, total_members: 1, non_financial: 1, needs_tier: 0, playhq_missing: 1 } })
  }
  if (/\/fees\/payments/.test(url)) {
    return json({ payments: [{ id: 'pay1', member_id: 'm1', full_name: 'Amardeep Gill', amount: 100,
                               kind: 'membership', paid_on: '2026-08-01', method: 'bank', reference: 'REF1' }] })
  }
  if (/\/fees\/all-members/.test(url)) return json({ members: [] })
  // Merch
  // A real category, or the "All categories" control is correctly not drawn.
  if (/\/merch\/categories/.test(url)) {
    return json({ categories: [{ id: 'c1', name: 'Balls', parent_id: null, top_category: 'equipment' }] })
  }
  if (/\/merch\/products/.test(url)) return json({ products: [] })
  if (/\/merch\/alerts/.test(url)) return json({ alerts: [] })
  if (/\/merch\/reports|\/merch\/summary/.test(url)) return json({})
  // Clubhouse roll-up (Today / Reports / sidebar counts)
  if (/\/clubhouse|\/notifications/.test(url)) return json({})
  if (/\/seasons/.test(url)) return json({ seasons: [SEASON] })
  if (/\/settings/.test(url)) return json({ diary_start_month: 7 })
  return json({})
})

// ── Measurement helpers, all computed-style based ───────────────────────────
// Anchors are included because a Manage LINK now sits among its section's
// buttons. The header is searched first and the document only as a fallback,
// or a sidebar nav link with the same word ("Events") would be found instead of
// the control being measured.
const FIND = `(text) => {
  const hit = (root) => [...root.querySelectorAll('button, select, a')].find(b => {
    const raw = (b.textContent || '').replace(/\u25be/g, '').trim()
    const bare = raw.split(':')[0].trim()
    return raw === text || bare === text || (b.getAttribute('aria-label') || '') === text
  })
  for (const h of document.querySelectorAll('header')) { const f = hit(h); if (f) return f }
  return hit(document)
}`

const SEG_PROBE = `(el) => {
  const cs = getComputedStyle(el)
  const r = el.getBoundingClientRect()
  return { bg: cs.backgroundColor, border: cs.borderTopWidth, borderColor: cs.borderTopColor,
           radius: cs.borderTopLeftRadius,
           padding: cs.paddingTop, x: r.x, width: r.width, mid: r.x + r.width / 2 }
}`

// Committee's box: a real 1px border, a rounded corner, a 3px inner pad and a
// fill that is NOT transparent. A loose row of pills has no such container.
// `--pb-hairline` on the dark theme. Asserted as a VALUE, because the reported
// "white border" was `border pb-hairline` — not a class at all, so the width
// applied and the colour fell through to Tailwind's preflight #e5e7eb
// (rgb(229,231,235)). A box that merely "has a border" would pass that.
const HAIRLINE = 'rgb(29, 35, 49)'
const looksSeg = (m) => !!m && m.border === '1px' && parseFloat(m.radius) >= 6
  && parseFloat(m.padding) >= 2 && m.bg !== 'rgba(0, 0, 0, 0)'
  && m.borderColor === HAIRLINE

async function segBox(page, label) {
  return page.evaluate(([text, probe, find]) => {
    const fn = eval(probe)
    const btn = eval(find)(text)
    if (!btn) return null
    // The container is the nearest ancestor that actually draws the box.
    let el = btn.parentElement
    for (let i = 0; i < 4 && el; i++, el = el.parentElement) {
      const cs = getComputedStyle(el)
      if (cs.borderTopWidth === '1px' && parseFloat(cs.borderTopLeftRadius) >= 6) return fn(el)
    }
    return null
  }, [label, SEG_PROBE, FIND])
}

// Centred = the group's midpoint is within 24px of the header's own midpoint.
// A generous tolerance on purpose: the point is "in the middle", not a pixel.
async function centredInHeader(page, label) {
  return page.evaluate(([text, find]) => {
    const btn = eval(find)(text)
    if (!btn) return null
    let group = null
    for (let el = btn.parentElement, i = 0; el && i < 4; el = el.parentElement, i++) {
      const cs = getComputedStyle(el)
      if (cs.borderTopWidth === '1px' && parseFloat(cs.borderTopLeftRadius) >= 6) { group = el; break }
    }
    // No box found is a failure, not something to measure a stand-in for.
    if (!group) return null
    const header = btn.closest('header') || group.closest('header')
    if (!header) return null
    const g = group.getBoundingClientRect(), h = header.getBoundingClientRect()
    const title = header.querySelector('h1')
    return {
      drift: Math.abs((g.x + g.width / 2) - (h.x + h.width / 2)),
      // On the title line, not below it: the two boxes overlap vertically.
      sameLine: !!title && g.top < title.getBoundingClientRect().bottom + 6
                        && g.bottom > title.getBoundingClientRect().top - 6,
    }
  }, [label, FIND])
}

// A search box on its own line under the caption: below the caption's baseline,
// and starting at the header's own left edge rather than beside the title.
async function searchBelowCaption(page, placeholder) {
  return page.evaluate((ph) => {
    const input = document.querySelector(`input[placeholder*="${ph}"]`)
    if (!input) return null
    const header = input.closest('header')
    const h1 = header?.querySelector('h1')
    if (!header || !h1) return null
    const i = input.getBoundingClientRect(), t = h1.getBoundingClientRect()
    return { below: i.top >= t.bottom, ownLine: i.x < t.x + 40 }
  }, placeholder)
}

// Is the first control drawn ABOVE the second? Measured off the real boxes, so
// "below the buttons" is a fact rather than a reading of the source order.
async function isAbove(page, topLabel, bottomSel) {
  return page.evaluate(([text, sel, find]) => {
    const a = eval(find)(text)
    const b = document.querySelector(sel)
    if (!a || !b) return null
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect()
    return { above: ra.bottom <= rb.top + 2, aTop: Math.round(ra.top), bTop: Math.round(rb.top) }
  }, [topLabel, bottomSel, FIND])
}

// The labels inside a seg box, in the order they are actually drawn.
async function segOrder(page, anyLabel) {
  return page.evaluate(([text, find]) => {
    const btn = eval(find)(text)
    if (!btn) return null
    let box = null
    for (let el = btn.parentElement, i = 0; el && i < 4; el = el.parentElement, i++) {
      const cs = getComputedStyle(el)
      if (cs.borderTopWidth === '1px' && parseFloat(cs.borderTopLeftRadius) >= 6) { box = el; break }
    }
    if (!box) return null
    return [...box.children].map(c => (c.textContent || '').replace(/\u25be/g, '').trim())
  }, [anyLabel, FIND])
}

// Type character by character, re-reading document.activeElement each time.
// This is the check `fill()` cannot make.
async function typesWithoutLosingFocus(page, placeholder, text) {
  const sel = `input[placeholder*="${placeholder}"]`
  if (!(await page.$(sel))) return { held: false, value: null, missing: true }
  await page.click(sel)
  for (const ch of text) {
    await page.keyboard.type(ch)
    const ok = await page.evaluate((s) => document.activeElement === document.querySelector(s), sel)
    if (!ok) return { held: false, value: await page.inputValue(sel) }
  }
  return { held: true, value: await page.inputValue(sel) }
}

const noOverflow = (page) => page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth)

// ── The run ─────────────────────────────────────────────────────────────────
const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    // The screen introductions are a first-visit takeover; they would render
    // instead of Reports and its button row.
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const errors = [], calls = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page, calls)

  const open = async (path, waitFor) => {
    await page.goto(BASE + path, { waitUntil: 'domcontentloaded' })
    if (waitFor) await page.waitForSelector(waitFor, { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(1200)
  }

  // ── Directory ─────────────────────────────────────────────────────────────
  await open('/admin/clubhouse/directory', 'h1')
  check('Directory renders', (await page.textContent('h1'))?.includes('Directory'),
    JSON.stringify(await page.$$eval('h1', ns => ns.map(n => n.textContent))))
  for (const label of ['Membership', 'Role', 'More', 'Manage']) {
    const box = await segBox(page, label)
    check(`Directory: ${label} wears the Committee button box`, looksSeg(box),
      JSON.stringify(box))
  }
  {
    const c = await centredInHeader(page, 'Membership')
    check('Directory: the four buttons sit on the title line', !!c?.sameLine, JSON.stringify(c))
    check('Directory: that group is centred', c && c.drift <= 24, `drift ${c?.drift}px`)
    const s = await searchBelowCaption(page, 'Search name or role')
    check('Directory: search on its own line below the heading', !!s?.below && !!s?.ownLine, JSON.stringify(s))
    const t = await typesWithoutLosingFocus(page, 'Search name or role', 'Gill')
    check('Directory: search keeps focus per character', t.held && t.value === 'Gill', JSON.stringify(t))
  }

  // ── Roster ────────────────────────────────────────────────────────────────
  await open('/admin/clubhouse/roster', 'h1')
  {
    const box = await segBox(page, 'People')
    check('Roster: People/Areas/Confirm/Hours wear the Committee box', looksSeg(box), JSON.stringify(box))
    const c = await centredInHeader(page, 'People')
    check('Roster: that group is centred', c && c.drift <= 24, `drift ${c?.drift}px`)
    for (const label of ['Auto-fill open shifts', 'Email rostered', 'Reset']) {
      const wk = await segBox(page, label)
      check(`Roster: "${label}" wears the Committee button box`, looksSeg(wk), JSON.stringify(wk))
    }
    // Volunteer pool is a view toggle and Publish week is the primary action,
    // so neither should have been swept into that box.
    const pool = await segBox(page, 'Volunteer pool')
    check('Roster: Volunteer pool is NOT in that box', !looksSeg(pool))
  }

  // ── Committee ─────────────────────────────────────────────────────────────
  await open('/admin/committee', 'h1')
  {
    const ord = await isAbove(page, 'All Meetings', 'input[placeholder*="Search meetings"]')
    check('Committee: the search sits below the second row of buttons', !!ord?.above, JSON.stringify(ord))
  }

  // ── Areas & roles ─────────────────────────────────────────────────────────
  await open('/admin/clubhouse/areas-roles', 'h1')
  {
    const s = await searchBelowCaption(page, 'Search roles')
    check('Areas & roles: search on its own line below the caption', !!s?.below && !!s?.ownLine, JSON.stringify(s))
    const t = await typesWithoutLosingFocus(page, 'Search roles', 'Score')
    check('Areas & roles: search keeps focus per character', t.held && t.value === 'Score', JSON.stringify(t))
    const c = await centredInHeader(page, 'Roles')
    check('Areas & roles: the section buttons are centred', c && c.drift <= 24, `drift ${c?.drift}px`)
  }

  // ── Club Diary ────────────────────────────────────────────────────────────
  await open('/admin/club-diary', 'h1')
  {
    const ord = await isAbove(page, 'Overdue & blocked only', 'input[placeholder*="Search tasks"]')
    check('Club Diary: the search sits below the cadence buttons', !!ord?.above, JSON.stringify(ord))
    const t = await typesWithoutLosingFocus(page, 'Search tasks', 'BAS')
    check('Club Diary: search keeps focus per character', t.held && t.value === 'BAS', JSON.stringify(t))
    // Clear it again so the cadence row is measured unfiltered.
    await page.fill('input[placeholder*="Search tasks"]', '').catch(() => {})
    await page.waitForTimeout(200)
    for (const label of ['All', 'Annual', 'Quarterly', 'Overdue & blocked only']) {
      const box = await segBox(page, label)
      check(`Club Diary: "${label}" wears the Committee button box`, looksSeg(box), JSON.stringify(box))
    }
  }

  // ── Events ────────────────────────────────────────────────────────────────
  await open('/admin/events', 'h1')
  {
    const box = await segBox(page, 'Events')
    check('Events: Events/Event types wear the Committee box', looksSeg(box), JSON.stringify(box))
    const mbox = await segBox(page, 'Manage events & tickets')
    check('Events: the Manage link is inside that same box', looksSeg(mbox), JSON.stringify(mbox))
    const order = await segOrder(page, 'Events')
    check('Events: Manage sits between Events and Event types',
      JSON.stringify(order) === JSON.stringify(['Events', 'Manage events & tickets', 'Event types']),
      JSON.stringify(order))
    const c = await centredInHeader(page, 'Events')
    check('Events: that group is centred', c && c.drift <= 24, `drift ${c?.drift}px`)
    const s = await searchBelowCaption(page, 'Search events')
    check('Events: search on its own line below the caption', !!s?.below && !!s?.ownLine, JSON.stringify(s))
    const t = await typesWithoutLosingFocus(page, 'Search events', 'Present')
    check('Events: search keeps focus per character', t.held && t.value === 'Present', JSON.stringify(t))
  }

  // ── Facilities (the reported failure) ─────────────────────────────────────
  await open('/admin/assets', 'h1')
  {
    const body = await page.textContent('body')
    check('Facilities: no longer says "Could not load facilities."', !body.includes('Could not load facilities'))
    check('Facilities: the page is titled "Facilities & Assets"',
      (await page.textContent('h1')) === 'Facilities & Assets', await page.textContent('h1'))
    check('Facilities: the sidebar item reads "Facilities & Assets"',
      body.includes('Facilities & Assets'))
    check('Facilities: the club\'s facilities are drawn', body.includes('Main Ground') && body.includes('Nets'))
    const box = await segBox(page, 'Availability')
    check('Facilities: Availability/Requests/Assets wear the Committee box', looksSeg(box), JSON.stringify(box))
    const mbox = await segBox(page, 'Manage assets & bookings')
    check('Facilities: the Manage link is inside that same box', looksSeg(mbox), JSON.stringify(mbox))
    const order = await segOrder(page, 'Availability')
    check('Facilities: Manage sits in the middle of the row',
      JSON.stringify(order) === JSON.stringify(['Availability', 'Requests', 'Manage assets & bookings', 'Assets']),
      JSON.stringify(order))
    const c = await centredInHeader(page, 'Availability')
    check('Facilities: that group is centred', c && c.drift <= 24, `drift ${c?.drift}px`)
    const s = await searchBelowCaption(page, 'Search facilities')
    check('Facilities: search on its own line below the caption', !!s?.below && !!s?.ownLine, JSON.stringify(s))
    const t = await typesWithoutLosingFocus(page, 'Search facilities', 'Nets')
    check('Facilities: search keeps focus per character', t.held && t.value === 'Nets', JSON.stringify(t))
    await page.waitForTimeout(300)
    const filtered = await page.textContent('body')
    check('Facilities: the search actually narrows the grid',
      filtered.includes('Nets') && !filtered.includes('Main Ground'))
    // The Assets tab reads the same endpoint the bug was in.
    await page.fill('input[placeholder*="Search facilities"]', '').catch(() => {})
    await page.click('button:text-is("Assets")').catch(() => {})
    await page.waitForTimeout(600)
    check('Facilities: the Assets tab lists the club\'s gear',
      (await page.textContent('body')).includes('Bowling machine'))
  }

  // ── Facilities → manage ───────────────────────────────────────────────────
  await open('/admin/clubhouse/facilities/manage', 'h1')
  {
    const box = await segBox(page, 'Bookings')
    check('Facilities manage: Facilities/Bookings/Assets wear the Committee box', looksSeg(box), JSON.stringify(box))
    const c = await centredInHeader(page, 'Bookings')
    check('Facilities manage: that group is on the title line', !!c?.sameLine, JSON.stringify(c))
    check('Facilities manage: that group is centred', c && c.drift <= 24, `drift ${c?.drift}px`)
  }

  // ── Accounts ──────────────────────────────────────────────────────────────
  await open('/admin/fees', 'h1')
  for (const label of ['Everyone', 'Owes money', 'Needs tier', 'Not on PlayHQ']) {
    const box = await segBox(page, label)
    check(`Accounts: "${label}" wears the Committee button box`, looksSeg(box), JSON.stringify(box))
  }
  for (const label of ['Membership', 'Role', 'More']) {
    const box = await segBox(page, label)
    check(`Accounts: "${label}" wears the Committee button box`, looksSeg(box), JSON.stringify(box))
  }
  {
    const ord = await isAbove(page, 'Membership', 'input[placeholder*="Search name or tier"]')
    check('Accounts: the menus sit above the search', !!ord?.above, JSON.stringify(ord))
    const below = await isAbove(page, 'Everyone', 'input[placeholder*="Search name or tier"]')
    check('Accounts: the four filters sit above both', !!below?.above, JSON.stringify(below))
  }

  // ── Payments ──────────────────────────────────────────────────────────────
  await open('/admin/fees/payments', 'h1')
  {
    for (const label of ['Membership', 'Role', 'More']) {
      const box = await segBox(page, label)
      check(`Payments: "${label}" wears the Committee button box`, looksSeg(box), JSON.stringify(box))
    }
    const c = await centredInHeader(page, 'Membership')
    check('Payments: the group sits on the title line', !!c?.sameLine, JSON.stringify(c))
    check('Payments: the group is centred', c && c.drift <= 24, `drift ${c?.drift}px`)
    // The kind filter directly under the caption, the search on the line after.
    const ord = await page.evaluate(() => {
      const sel = [...document.querySelectorAll('select')].find(s => s.textContent.includes('All kinds'))
      const inp = document.querySelector('input[placeholder*="Search name, bank ref"]')
      const h1 = document.querySelector('h1')
      if (!sel || !inp || !h1) return null
      const rs = sel.getBoundingClientRect(), ri = inp.getBoundingClientRect(), rh = h1.getBoundingClientRect()
      return { kindAboveSearch: rs.bottom <= ri.top + 2, kindBelowTitle: rs.top >= rh.bottom,
               kindOnLeft: rs.x < rh.x + 40, searchOnLeft: ri.x < rh.x + 40 }
    })
    check('Payments: All kinds sits under the caption, on the left', !!ord?.kindBelowTitle && !!ord?.kindOnLeft, JSON.stringify(ord))
    check('Payments: the search is on the line below it', !!ord?.kindAboveSearch, JSON.stringify(ord))
  }

  // ── Stock ─────────────────────────────────────────────────────────────────
  await open('/admin/merch/stock', 'h1')
  for (const label of ['All', 'Apparel', 'Equipment', 'Food & Drink']) {
    const box = await segBox(page, label)
    check(`Stock: "${label}" wears the Committee button box`, looksSeg(box), JSON.stringify(box))
  }
  {
    // The category narrowing is still a real <select> — a club's tree is as
    // long as the club makes it — but it wears the same box as the buttons
    // above it. Found by its aria-label, since a <select>'s text content is
    // every option it holds.
    const box = await segBox(page, 'Category')
    check('Stock: the "All categories" control wears the Committee button box', looksSeg(box), JSON.stringify(box))
    const ord = await page.evaluate(() => {
      const sel = document.querySelector('select[aria-label="Category"]')
      const inp = document.querySelector('input[placeholder*="Search products"]')
      const h1 = document.querySelector('h1')
      if (!sel || !inp || !h1) return null
      const rs = sel.getBoundingClientRect(), ri = inp.getBoundingClientRect(), rh = h1.getBoundingClientRect()
      return { catAboveSearch: rs.bottom <= ri.top + 2, catOnLeft: rs.x < rh.x + 60 }
    })
    check('Stock: All categories is on the far left', !!ord?.catOnLeft, JSON.stringify(ord))
    check('Stock: the search is on the line below it', !!ord?.catAboveSearch, JSON.stringify(ord))
  }

  // ── Membership tiers ──────────────────────────────────────────────────────
  await open('/admin/fees/schedule', 'h1')
  {
    const box = await segBox(page, 'Membership types')
    check('Membership tiers: its title-line button wears the Committee box', looksSeg(box), JSON.stringify(box))
  }

  // ── Reports ───────────────────────────────────────────────────────────────
  await open('/admin/clubhouse/reports', 'h1')
  {
    const box = await segBox(page, 'Money')
    check('Reports: Money/Stock wear the Committee button box', looksSeg(box), JSON.stringify(box))
    const c = await centredInHeader(page, 'Money')
    check('Reports: the group is centred', c && c.drift <= 24, `drift ${c?.drift}px`)
  }

  // ── No page errors ────────────────────────────────────────────────────────
  check('No page errors on any screen', errors.length === 0, errors.slice(0, 3).join(' | '))

  // ── 390px: nothing pushes the page sideways ───────────────────────────────
  //
  // Three screens overflow at 390px BEFORE any of this, measured by re-running
  // this same probe with the change stashed: Accounts 33px (its twoRow action
  // cluster — BOOKMARKS / Import / Add member — which carries `shrink-0`),
  // Payments 111px (the "Import bank CSV" button) and Stock 12px ("New
  // product"). None of them is a button row this change touches, and each is
  // the trap the Selection-header note already documents, so they are recorded
  // rather than quietly widened into. The budget is the measured baseline:
  // this must never make an existing overflow worse, and must introduce none.
  const OVERFLOW_BASELINE = { Accounts: 33, Payments: 111, Stock: 12 }
  await page.setViewportSize({ width: 390, height: 900 })
  for (const [path, name] of [
    ['/admin/clubhouse/directory', 'Directory'],
    ['/admin/clubhouse/roster', 'Roster'],
    ['/admin/clubhouse/areas-roles', 'Areas & roles'],
    ['/admin/club-diary', 'Club Diary'],
    ['/admin/events', 'Events'],
    ['/admin/assets', 'Facilities'],
    ['/admin/clubhouse/facilities/manage', 'Facilities manage'],
    ['/admin/fees', 'Accounts'],
    ['/admin/fees/payments', 'Payments'],
    ['/admin/merch/stock', 'Stock'],
    ['/admin/clubhouse/reports', 'Reports'],
  ]) {
    await open(path, 'h1')
    const over = await noOverflow(page)
    const budget = OVERFLOW_BASELINE[name] || 0
    check(`${name}: no overflow added at 390px (budget ${budget}px)`, over <= budget, `${over}px`)
  }

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch(e => { console.error(e); process.exit(1) })
