// The People-view "Open shifts" row labels every open shift correctly, against
// the REAL Roster screen with the API stubbed at the network layer.
//
// Two bugs this pins, both reported off a live roster showing "undefined"
// descriptions on open-shift chips:
//
//   1. ARCHIVED-AREA ORPHAN → "undefined". `list_areas` returns only active
//      areas, but a week's shifts include any whose area was later archived. The
//      old chip named a shift by looking its area up in that active-only set, so
//      an archived-area shift read as the literal "undefined". The shift now
//      carries its own `area_name`, so the chip names it whatever its area's
//      state.
//   2. MULTI-ROLE MERGE. A shift is FOR one role now, but the open-shifts row
//      grouped by area NAME + time — so an Umpire slot and a Scorer slot at the
//      same time in one Match Day area merged into a single "×N" chip that hid
//      one of the roles. Grouping keys on (area, role, time) now, so each role
//      shows as its own chip.
//
// Control run (previous commit — the old Roster.jsx): the archived chip reads
// "undefined", the Scorer role is swallowed into the Match Day group, the
// archived area's real name never shows, and the merged group counts "×3"
// where the fix shows the Umpire pair as "×2".
//
//   node verify_roster_open_shift_labels_browser.mjs   (dev/preview server via APP_URL)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

// Only Match Day is active. The Grounds area has been ARCHIVED, so it is NOT in
// `areas` — but its open shift is still on the week and carries `area_name`.
const MATCH_DAY = {
  id: 'ar-md', name: 'Match Day', department: 'Officials', color: '#3b82f6',
  required_role_id: 'r-ump', required_role_name: 'Umpire',
  roles: [
    { role_id: 'r-ump', role_name: 'Umpire', required_qualification_type_id: null, required_qualification_name: null },
    { role_id: 'r-sco', role_name: 'Scorer', required_qualification_type_id: null, required_qualification_name: null },
  ],
  patterns: [],
}

const shift = (id, area_id, area_name, role_id, role_name, day, s, e) => ({
  id, area_id, area_name, role_id, role_name, day_of_week: day,
  start_time: s, end_time: e, headcount: 1, assignee_member_id: null,
  required_qualification_type_id: null, required_qualification_name: null, warnings: [],
})

const WEEK = {
  week: {
    id: 'w1', week_start: '2026-08-17', status: 'draft', version: 1,
    shifts: [
      // SAT (day 5): an Umpire pair (same role + time → one "Match Day ×2"
      // chip) and a Scorer at the same time (different role → its OWN chip, not
      // merged). The old code grouped by area name + time, so all three lumped
      // into one "Match Day ×3" that hid the Scorer.
      shift('s-ump-1', 'ar-md', 'Match Day', 'r-ump', 'Umpire', 5, 12, 18.5),
      shift('s-ump-2', 'ar-md', 'Match Day', 'r-ump', 'Umpire', 5, 12, 18.5),
      shift('s-sco-1', 'ar-md', 'Match Day', 'r-sco', 'Scorer', 5, 12, 18.5),
      // SUN (day 6): a PAIR of open shifts whose area (Turf) has been archived
      // and is absent from `areas`. The area name is "Turf", distinct from the
      // "Groundskeeper" role, so a headline match can't pass on the role. A pair
      // (count 2) is what makes the old `a.name + ' ×2'` concat render the
      // literal "undefined ×2" the live screenshot showed.
      shift('s-grd-1', 'ar-gk', 'Turf', 'r-grd', 'Groundskeeper', 6, 9, 10),
      shift('s-grd-2', 'ar-gk', 'Turf', 'r-grd', 'Groundskeeper', 6, 9, 10),
    ],
  },
  areas: [MATCH_DAY],   // NB: Grounds is archived, deliberately not here.
  candidates: [
    { member_id: 'm1', name: 'Amardeep Gill', available_days: [5, 6], max_shifts: 5,
      role_ids: ['r-ump'], role_names: ['Umpire'], qual_type_ids: [] },
  ],
  settings: {},
}

const routes = (page) => page.route('**/api/**', async (route) => {
  const url = route.request().url()
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) {
    return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } })
  }
  if (/\/roster\/week/.test(url)) return json(WEEK)
  if (/\/roster\/areas(\?|$)/.test(url)) return json({ areas: [MATCH_DAY] })
  if (/\/roster\/departments/.test(url)) return json({ departments: [{ id: 'd1', name: 'Officials' }] })
  if (/\/roster\/hours/.test(url)) return json({ rows: [], totals: {} })
  if (/\/roster\/shortages/.test(url)) return json({ roles: [], no_role_required: 0 })
  if (/\/roster\/settings/.test(url)) return json({})
  if (/\/roles-activities\/roles/.test(url)) return json({ roles: [] })
  if (/\/role-types/.test(url)) return json({ types: [] })
  if (/\/roles-activities\/activities|\/activity-types/.test(url)) return json({ activities: [], types: [] })
  if (/\/qualifications\/types/.test(url)) return json({ types: [] })
  if (/\/clubhouse|\/notifications/.test(url)) return json({})
  if (/\/seasons/.test(url)) return json([{ id: 'se1', name: 'Summer 2025/26', year: 2025 }])
  if (/\/settings/.test(url)) return json({ diary_start_month: 7 })
  return json({})
})

// The innerText of the People-view "Open shifts" grid row only — so a role name
// showing here means it drew as its own chip, not that it appears somewhere
// else on the page (a pool badge, an area sub-line).
const openRowText = (page) => page.evaluate(() => {
  const label = [...document.querySelectorAll('span')].find(n => (n.textContent || '').trim() === 'Open shifts')
  if (!label) return null
  let row = label
  while (row && getComputedStyle(row).display !== 'grid') row = row.parentElement
  return row ? row.innerText : null
})

const noOverflow = (page) => page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth)

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
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page)

  await page.goto(BASE + '/admin/clubhouse/roster', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(1200)

  const text = await openRowText(page)
  check('the Open shifts row rendered', !!text, JSON.stringify(text))
  const t = text || ''

  // ── The bug: nothing reads "undefined" (the archived pair's headline) ──────
  check('no open-shift chip reads "undefined"', !/undefined/.test(t), JSON.stringify(t))

  // ── The archived area's shift still names its area ─────────────────────────
  // "Turf" is the archived area's name and is NOT a substring of the role, so
  // this can only pass on a real headline, never on the "Groundskeeper" role.
  check('the archived-area chip shows its real area name (Turf)', t.includes('Turf'), JSON.stringify(t))
  check('the archived-area chip shows its role (Groundskeeper)', /Groundskeeper ·/.test(t), JSON.stringify(t))

  // ── Distinct roles at the same time are separate chips, not one merged ×N ──
  check('the active area is named on its chips (Match Day)', t.includes('Match Day'), JSON.stringify(t))
  check('the Umpire role shows as its own chip', /Umpire ·/.test(t), JSON.stringify(t))
  check('the Scorer role shows as its own chip (not merged into Umpire)', /Scorer ·/.test(t), JSON.stringify(t))

  // ── The same-role Umpire pair counts ×2 on its own; the merge would have
  //    lumped the Scorer in as "Match Day ×3". ─────────────────────────────────
  check('the same-role Umpire pair reads "Match Day ×2"', /Match Day ×2/.test(t), JSON.stringify(t))
  check('no chip over-counts to ×3 (Scorer merged in)', !t.includes('×3'), JSON.stringify(t))

  check('no page errors across the run', errors.length === 0, errors.join(' | '))

  await page.setViewportSize({ width: 390, height: 900 })
  await page.goto(BASE + '/admin/clubhouse/roster', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(800)
  const over = await noOverflow(page)
  check('Roster: no overflow at 390px', over <= 0, `${over}px`)

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch(e => { console.error(e); process.exit(1) })
