// Multiple roles per Operational Area, against the REAL screens with the API
// stubbed at the network layer.
//
// What is asserted:
//   * the Operational-area form is a ROLE PALETTE editor — "+ Add role" grows a
//     row of (role, gating-qualification), and two roles can be added at once;
//   * the EXACT `roles: [...]` payload on the wire when the area is saved:
//     Umpire carries its accreditation, Scorer carries a null qualification;
//   * an existing area's sub-line lists its palette (role + qual in parens);
//   * the per-pattern ROLE picker is scoped to that area's palette and the
//     pattern POST carries the chosen `role_id`;
//   * on the weekly grid, an open shift's chip shows its role;
//   * the AddShift picker on the Roster is scoped to the chosen area's palette;
//   * no page errors, and no horizontal overflow at 390px.
//
//   node verify_roster_area_roles_browser.mjs   (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

// ── The catalogue the screens pull from ─────────────────────────────────────
const ROLES = [
  { id: 'r-ump', title: 'Umpire', role_type_name: 'Officials', is_committee: false },
  { id: 'r-sco', title: 'Scorer', role_type_name: 'Officials', is_committee: false },
  { id: 'r-tm', title: 'Team Manager', role_type_name: 'Officials', is_committee: false },
]
const QUALS = [{ id: 'q-acc', name: 'Umpire Accreditation' }]

// An existing Match Day area with a two-role palette: Umpire (gated by
// accreditation) beside Scorer (gated by nothing). One weekly pattern for the
// Umpire role, so its chip shows the role name.
const MATCH_DAY = {
  id: 'ar1', name: 'Match Day', department: 'Officials', color: '#3b82f6',
  required_role_id: 'r-ump', required_role_name: 'Umpire',
  roles: [
    { role_id: 'r-ump', role_name: 'Umpire', required_qualification_type_id: 'q-acc', required_qualification_name: 'Umpire Accreditation' },
    { role_id: 'r-sco', role_name: 'Scorer', required_qualification_type_id: null, required_qualification_name: null },
  ],
  patterns: [
    { id: 'pp1', day_of_week: 5, start_time: 12, end_time: 18, headcount: 1, role_id: 'r-ump', role_name: 'Umpire' },
  ],
}

// The week the Roster grid draws: one OPEN (unassigned) Umpire shift, so the
// open-shifts row renders a chip carrying its role.
const WEEK = {
  week: {
    id: 'w1', week_start: '2026-08-17', status: 'draft', version: 1,
    shifts: [
      { id: 'sh1', area_id: 'ar1', area_name: 'Match Day', role_id: 'r-ump', role_name: 'Umpire',
        day_of_week: 5, start_time: 12, end_time: 18, headcount: 1, assignee_member_id: null,
        required_qualification_type_id: 'q-acc', required_qualification_name: 'Umpire Accreditation' },
    ],
  },
  areas: [MATCH_DAY],
  candidates: [
    { member_id: 'm1', name: 'Amardeep Gill', available_days: [5, 6], max_shifts: 5,
      role_ids: ['r-ump'], role_names: ['Umpire'], qual_type_ids: ['q-acc'] },
  ],
  settings: {},
}

const routes = (page, calls) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url()
  const method = req.method()
  if (method !== 'GET') calls.push({ url, method, body: req.postData() })
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

  if (url.includes('/auth/me')) {
    return json({
      id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' },
    })
  }
  // Roster
  if (/\/roster\/week/.test(url)) return json(WEEK)
  if (/\/roster\/areas\/reorder/.test(url)) return json({ ok: true })
  if (/\/roster\/areas\/[^/]+\/patterns/.test(url)) return json({ ok: true })
  if (/\/roster\/areas\/seed-starter/.test(url)) return json({ ok: true })
  if (/\/roster\/areas(\?|$)/.test(url)) {
    if (method === 'POST') return json({ ok: true, id: 'ar-new' })
    return json({ areas: [MATCH_DAY] })
  }
  if (/\/roster\/departments/.test(url)) return json({ departments: [{ id: 'd1', name: 'Officials' }] })
  if (/\/roster\/hours/.test(url)) return json({ rows: [], totals: {} })
  if (/\/roster\/shortages/.test(url)) return json({ roles: [], no_role_required: 0 })
  if (/\/roster\/settings/.test(url)) return json({})
  // Areas & roles catalogues
  if (/\/roles-activities\/roles/.test(url)) return json({ roles: ROLES })
  if (/\/role-types/.test(url)) return json({ types: [{ id: 'rt1', name: 'Officials', category: 'volunteer' }] })
  if (/\/roles-activities\/activities|\/activity-types/.test(url)) return json({ activities: [], types: [] })
  if (/\/qualifications\/types/.test(url)) return json({ types: QUALS })
  // Clubhouse chrome
  if (/\/clubhouse|\/notifications/.test(url)) return json({})
  if (/\/seasons/.test(url)) return json([{ id: 'se1', name: 'Summer 2025/26', year: 2025 }])
  if (/\/settings/.test(url)) return json({ diary_start_month: 7 })
  return json({})
})

// The POST body that created an area, parsed. Exactly one create is expected.
const createBody = (calls) => {
  const c = calls.find(x => x.method === 'POST' && /\/roster\/areas(\?|$)/.test(x.url) && !/\/patterns|\/reorder|seed-starter/.test(x.url))
  if (!c) return null
  try { return JSON.parse(c.body) } catch { return null }
}
const patternBody = (calls) => {
  const c = calls.find(x => x.method === 'POST' && /\/roster\/areas\/[^/]+\/patterns/.test(x.url))
  if (!c) return null
  try { return JSON.parse(c.body) } catch { return null }
}
const shiftBody = (calls) => {
  const c = calls.find(x => x.method === 'POST' && /\/roster\/shifts(\?|$)/.test(x.url))
  if (!c) return null
  try { return JSON.parse(c.body) } catch { return null }
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
  // Absence-reporting helpers: an element the change ADDS is read/clicked/picked
  // through these, so the control run (previous commit, no such element) fails
  // each new check rather than dying on the first missing locator.
  const seen = (sel) => page.locator(sel).count().then(n => n > 0).catch(() => false)
  const press = async (sel) => { if (await seen(sel)) { await page.locator(sel).first().click().catch(() => {}); return true } return false }
  const pick = async (sel, i, value) => { const loc = page.locator(sel).nth(i); if (await loc.count().catch(() => 0)) { await loc.selectOption(value).catch(() => {}) } }
  const opts = async (sel, i = 0) => { const loc = page.locator(sel).nth(i); if (!(await loc.count().catch(() => 0))) return null; return loc.evaluate(s => [...s.options].map(o => o.textContent.trim())).catch(() => null) }

  // ── Operational areas: the palette editor ──────────────────────────────────
  await open('/admin/clubhouse/areas-roles?tab=areas', 'h1')

  // The existing area lists its whole palette on its sub-line (role + the qual
  // that gates it, in parens), separated by a middle dot — not a single role.
  const subline = await page.evaluate(() => {
    const el = [...document.querySelectorAll('div')].find(n =>
      /Umpire \(Umpire Accreditation\)/.test(n.textContent || '') &&
      /Scorer/.test(n.textContent || '') && n.children.length === 0)
    return el ? el.textContent.trim() : null
  })
  check('the area sub-line lists both palette roles with their qualifications',
    !!subline && subline.includes('Umpire (Umpire Accreditation)') && subline.includes('Scorer'),
    JSON.stringify(subline))

  // Open the add-area form and build a two-role palette.
  await press('text=+ Add area')
  await page.waitForTimeout(300)
  // The NAME field is the input inside the form's "NAME *" label.
  await page.locator('label', { hasText: 'NAME' }).locator('input').fill('Match Day New').catch(() => {})
  await page.waitForTimeout(150)

  const hasPalette = await seen('[data-testid="area-add-role"]')
  check('the operational-area form has a role-palette editor', hasPalette)

  const beforeRoles = await page.locator('[data-testid="area-role"]').count()
  check('the palette starts with no role rows', beforeRoles === 0, `${beforeRoles}`)

  await press('[data-testid="area-add-role"]'); await page.waitForTimeout(120)
  await press('[data-testid="area-add-role"]'); await page.waitForTimeout(120)
  const twoRows = await page.locator('[data-testid="area-role"]').count()
  check('"+ Add role" grows the palette to two role rows', twoRows === 2, `${twoRows}`)

  // Row 1: Umpire + its accreditation. Row 2: Scorer + no qualification.
  await pick('[data-testid="area-role"]', 0, 'r-ump'); await page.waitForTimeout(80)
  await pick('[data-testid="area-role-qual"]', 0, 'q-acc'); await page.waitForTimeout(80)
  await pick('[data-testid="area-role"]', 1, 'r-sco'); await page.waitForTimeout(80)

  // Row 2's role options must exclude the role already chosen in row 1 — a role
  // can't be in one area's palette twice.
  const row2opts = await opts('[data-testid="area-role"]', 1)
  check('row 2 does not offer the role already chosen in row 1',
    !!row2opts && !row2opts.includes('Umpire') && row2opts.includes('Scorer'), JSON.stringify(row2opts))

  await press('text=Add area')
  await page.waitForTimeout(600)
  const body = createBody(calls)
  check('the create payload carries the exact two-role palette',
    !!body && body.name === 'Match Day New' && Array.isArray(body.roles) && body.roles.length === 2,
    JSON.stringify(body))
  check('Umpire in the payload carries its accreditation',
    !!body && body.roles?.[0]?.role_id === 'r-ump' && body.roles?.[0]?.required_qualification_type_id === 'q-acc',
    JSON.stringify(body?.roles))
  check('Scorer in the payload carries a null qualification',
    !!body && body.roles?.[1]?.role_id === 'r-sco' && body.roles?.[1]?.required_qualification_type_id === null,
    JSON.stringify(body?.roles))

  // ── The per-pattern role picker, scoped to the area's palette ───────────────
  await page.getByRole('button', { name: 'Shifts', exact: true }).first().click().catch(() => {})
  await page.waitForTimeout(300)
  const patOpts = await opts('[data-testid="pattern-role"]')
  check('the pattern ROLE picker offers Any role plus the two palette roles',
    !!patOpts && patOpts.includes('Any role') && patOpts.includes('Umpire') && patOpts.includes('Scorer') && patOpts.length === 3,
    JSON.stringify(patOpts))

  await pick('[data-testid="pattern-role"]', 0, 'r-sco')
  await page.waitForTimeout(100)
  await page.click('text=Add shift').catch(() => {})
  await page.waitForTimeout(500)
  const pat = patternBody(calls)
  check('the added pattern carries the chosen role_id', !!pat && pat.role_id === 'r-sco', JSON.stringify(pat))

  // ── The weekly grid shows a shift's role ────────────────────────────────────
  calls.length = 0
  await open('/admin/clubhouse/roster', 'h1')
  const chipRole = await page.evaluate(() => {
    // The open-shifts row draws a chip for the unassigned Umpire shift; its
    // second line reads "Umpire · 12pm–6pm".
    return [...document.querySelectorAll('div')].some(n =>
      n.children.length === 0 && /^Umpire · /.test((n.textContent || '').trim()))
  })
  check('an open shift chip on the grid shows its role', chipRole)

  // ── The AddShift picker is scoped to the area's palette ─────────────────────
  await page.click('text=+ Add a shift').catch(() => {})
  await page.waitForTimeout(300)
  const addOpts = await opts('[data-testid="add-shift-role"]')
  check('the AddShift role picker is scoped to the chosen area palette',
    !!addOpts && addOpts.includes('Any role') && addOpts.includes('Umpire') && addOpts.includes('Scorer'),
    JSON.stringify(addOpts))
  await pick('[data-testid="add-shift-role"]', 0, 'r-ump')
  await page.waitForTimeout(100)
  await page.click('text=Add shift').catch(() => {})
  await page.waitForTimeout(500)
  const sh = shiftBody(calls)
  check('the one-off shift carries the chosen role_id', !!sh && sh.role_id === 'r-ump', JSON.stringify(sh))

  // ── No page errors ──────────────────────────────────────────────────────────
  check('no page errors across the run', errors.length === 0, errors.join(' | '))

  // ── No overflow at 390px ────────────────────────────────────────────────────
  await page.setViewportSize({ width: 390, height: 900 })
  for (const [path, name] of [
    ['/admin/clubhouse/areas-roles?tab=areas', 'Operational areas'],
    ['/admin/clubhouse/roster', 'Roster'],
  ]) {
    await open(path, 'h1')
    const over = await noOverflow(page)
    check(`${name}: no overflow at 390px`, over <= 0, `${over}px`)
  }

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch(e => { console.error(e); process.exit(1) })
