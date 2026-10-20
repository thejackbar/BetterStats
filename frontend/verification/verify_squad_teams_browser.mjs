// Drives the real Squads screen and menu in Chromium with the API stubbed at the
// network layer:
//   * a squad covers several teams: the editor lists them with their XI numbers,
//     takes more from a picker, reorders and removes them, and sends them in order
//   * the XI numbers follow the squad's Order box
//   * a team that belongs to another squad is flagged as being moved
//   * a rename alone sends no teams (it must not move fixtures about)
//   * the column header names a squad's teams
//   * the menu has "Selection Whiteboard" as its own item, the old address still
//     lands there with its date, and the screen carries the new name
//   * 390px: no sideways overflow with the editor open
//
//   npx vite preview --port 5199 &    node verify_squad_teams_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }

const MACS = 'm1', THIRDS = 'm3'
const TEAMS = () => [
  { id: MACS, name: 'MACs', short_name: null, sequence: 1, is_active: true, grade_id: 'g1', grade_name: '1st Grade, 2nd Grade',
    sides: [{ key: '1st grade', grade_name: '1st Grade', label: null, default_label: '1st XI', rank: 1, stored: true }, { key: '2nd grade', grade_name: '2nd Grade', label: null, default_label: '2nd XI', rank: 2, stored: true }] },
  { id: THIRDS, name: 'Thirds', short_name: null, sequence: 3, is_active: true, grade_id: 'g3', grade_name: '3rd Grade',
    sides: [{ key: '3rd grade', grade_name: '3rd Grade', label: null, default_label: '3rd XI', rank: 3, stored: true }] },
]
const OPTIONS = { seasons: [{ season_id: 's1', season_name: 'Summer', year: 2026, grades: [
  { id: 'g1', name: '1st Grade', key: '1st grade' }, { id: 'g2', name: '2nd Grade', key: '2nd grade' }, { id: 'g3', name: '3rd Grade', key: '3rd grade' },
  { id: 'g4', name: '4th Grade', key: '4th grade' }, { id: 'g5', name: '5th Grade', key: '5th grade' },
] }] }
const ME = { id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1', club_slug: 'gisborne', capabilities: [],
  entitlements: { modules: ['select'], core_live: true, status: 'active' } }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(6000)
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const wire = []
  const json = (r, body) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route('**/api/club-admin/players', (r) => json(r, []))
  await page.route(/\/api\/availability\/matrix(\?.*)?$/, (r) => json(r, { dates: [], players: [], availability: {}, all_squads: [], dormancy_months: 24, squad_next: {}, rules: { active: false, applied: [] } }))
  await page.route('**/api/teams/grade-options', (r) => json(r, OPTIONS))
  await page.route(/\/api\/teams\/(?!grade-options)[^/?]+$/, (r) => {
    if (r.request().method() === 'PATCH') { wire.push(JSON.parse(r.request().postData() || '{}')); return json(r, { ...TEAMS()[0], fixtures_assigned: 3, moved_from: [] }) }
    return json(r, {})
  })
  await page.route(/\/api\/teams(\?.*)?$/, (r) => json(r, TEAMS()))
  await page.route('**/api/selection/selected-players**', (r) => json(r, { player_ids: [] }))
  await page.route(/\/api\/selection\/overview(\?.*)?$/, (r) => json(r, { fixtures: [], default_team_size: 11 }))

  await page.goto(`${BASE}/admin/betterselect/teams`)
  await page.waitForSelector('.pb-card', { timeout: 20000 })
  await page.waitForTimeout(500)

  await safe('Column header', async () => {
    console.log('\n── The squad shows its teams ──')
    check('MACs names its two teams on the board', /1st XI · 2nd XI/.test(await page.locator('[data-squad-sides]').first().innerText()))
  })

  const openMacs = async () => {
    const col = page.locator('.pb-card', { has: page.locator('.font-display', { hasText: /^MACs$/ }) }).first()
    await col.locator('button[title="Edit squad"]').click()
    await page.locator('[data-squad-modal]').waitFor()
    await page.locator('[data-squad-team]').first().waitFor()
  }

  await safe('Editor', async () => {
    console.log('\n── Editing a squad\'s teams ──')
    await openMacs()
    const rows = await page.locator('[data-squad-team]').allInnerTexts()
    check('the editor lists both teams with their XI numbers', rows.length === 2 && /^1\s/.test(rows[0].trim()) && /^2\s/.test(rows[1].trim()), JSON.stringify(rows))
    const ph = await page.locator('[data-squad-team] input').evaluateAll((els) => els.map((e) => e.placeholder))
    check('...and the names they get until renamed', JSON.stringify(ph) === JSON.stringify(['1st XI', '2nd XI']), JSON.stringify(ph))
    // Add the 4th Grade (not in any squad), then the 3rd (in Thirds).
    await page.locator('[data-add-team]').selectOption('4th grade')
    check('a third team joins the list as the 3rd XI', (await page.locator('[data-squad-team]').count()) === 3 && /^3\s/.test((await page.locator('[data-squad-team]').nth(2).innerText()).trim()))
    await page.locator('[data-add-team]').selectOption('3rd grade')
    check('a team that belongs to another squad says it is moving', /3rd Grade moves from Thirds/.test(await page.locator('[data-squad-teams]').innerText()))
    await page.locator('[data-squad-team="3rd grade"] [data-remove-team]').click()
    check('removing a team takes it out', (await page.locator('[data-squad-team="3rd grade"]').count()) === 0)
    // Order box renumbers
    await page.locator('[data-squad-order]').fill('4')
    const nums = (await page.locator('[data-squad-team]').allInnerTexts()).map((t) => t.trim().split(/\s/)[0])
    check('changing the squad\'s order renumbers the teams (4, 5, 6)', JSON.stringify(nums) === JSON.stringify(['4', '5', '6']), JSON.stringify(nums))
    await page.locator('[data-squad-order]').fill('1')
    // Reorder: move 4th Grade up above 2nd Grade
    await page.locator('[data-squad-team="4th grade"] button[aria-label="Move up"]').click()
    // Rename the 2nd Grade team
    await page.locator('[data-squad-team="2nd grade"] input').fill('Reserves')
    wire.length = 0
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.waitForTimeout(600)
    const body = wire[0] || {}
    check('Save sends the teams in the order shown, with the new name',
      JSON.stringify(body.sides) === JSON.stringify([{ grade_id: 'g1', label: null }, { grade_id: 'g4', label: null }, { grade_id: 'g2', label: 'Reserves' }]), JSON.stringify(body.sides))
    check('...and says how many upcoming games moved onto the squad', /3 upcoming games now belong to this squad/.test(await page.locator('body').innerText()))
  })

  await safe('Rename only', async () => {
    console.log('\n── A rename alone moves nothing ──')
    await openMacs()
    await page.locator('input[placeholder="e.g. Macs"]').fill('Macs')
    wire.length = 0
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.waitForTimeout(600)
    check('no teams are sent, so no fixtures are reassigned', wire.length === 1 && !('sides' in wire[0]), JSON.stringify(wire[0]))
  })

  await safe('Menu', async () => {
    console.log('\n── Selection Whiteboard ──')
    await page.goto(`${BASE}/admin/betterselect/teams`)
    const link = page.locator('a[href="/admin/betterselect/whiteboard"]').first()
    await link.waitFor({ state: 'attached', timeout: 15000 }).catch(() => {})
    check('the menu has Selection Whiteboard as its own item', (await link.count()) === 1 && /Selection Whiteboard/.test(await link.innerText()))
    await page.goto(`${BASE}/admin/betterselect/selection/draft-table?date=2027-04-20`)
    await page.waitForTimeout(800)
    check('the old Draft table address lands on the whiteboard, date kept', /\/admin\/betterselect\/whiteboard\?date=2027-04-20$/.test(page.url()), page.url())
    check('the screen carries the new name', /Selection Whiteboard/.test(await page.locator('body').innerText()))
    check('and no longer calls itself the Draft table', !/Draft table/.test(await page.locator('body').innerText()))
  })

  await safe('390px', async () => {
    console.log('\n── 390px ──')
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto(`${BASE}/admin/betterselect/teams`)
    await page.waitForSelector('.pb-card')
    await page.waitForTimeout(400)
    const col = page.locator('.pb-card', { has: page.locator('.font-display', { hasText: /^MACs$/ }) }).first()
    await col.locator('button[title="Edit squad"]').click()
    await page.locator('[data-squad-team]').first().waitFor()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
    const modalW = await page.locator('[data-squad-modal]').evaluate((e) => e.getBoundingClientRect().right)
    check('no sideways overflow with the editor open', overflow <= 1 && modalW <= 391, `${overflow} ${modalW}`)
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/squad-editor-390.png` : '/tmp/squad-editor-390.png' })
  })

  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
