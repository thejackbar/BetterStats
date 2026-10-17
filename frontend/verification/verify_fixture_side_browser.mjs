// Drives the REAL Fixtures screen in Chromium with the API stubbed at the network layer
// (Gisborne round): "Our team" in the edit-fixture form is a squad's TEAM, not the squad.
//   * a squad covering two teams is offered as one choice per team ("MACs › 2nd XI")
//   * a squad with one team is one plain choice
//   * the form opens on the fixture's own team (the 2nd XI of MACs)
//   * picking the 1st XI PATCHes team_id AND side_key; a one-team squad sends side_key null
//   * "No team assigned" sends team_id null
//   * 390px: no sideways overflow with the form open
//
//   npx vite preview --port 5199 &    node verify_fixture_side_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }

const MAC = 'sq-macs', WOM = 'sq-women', OLD = 'sq-thirds'
const TEAMS = [
  { id: MAC, name: 'MacIntyre 1s & 2s Squad', is_active: true, sides: [
    { key: '1st grade', grade_name: '1st Grade', label: null, default_label: '1st XI', rank: 1, stored: true },
    { key: '2nd grade', grade_name: '2nd Grade', label: null, default_label: '2nd XI', rank: 2, stored: true }] },
  { id: OLD, name: 'Jenson A Squad', is_active: true, sides: [{ key: '3rd grade', grade_name: '3rd Grade', label: null, default_label: '3rd XI', rank: 3, stored: false }] },
  { id: WOM, name: 'Womens Squad', is_active: true, sides: [
    { key: 'womens a', grade_name: 'Womens A', label: 'Womens A', default_label: 'Womens A', rank: 50, stored: true },
    { key: 'womens b', grade_name: 'Womens B', label: 'Womens B', default_label: 'Womens B', rank: 51, stored: true }] },
]
const FIXTURE = {
  id: 'f1', source: 'grassroots', grade_id: 'g1', team_id: MAC, side_key: '2nd grade', team_name: '2nd XI', squad_name: 'MacIntyre 1s & 2s Squad',
  label: null, round: 'R3', played_on: '2026-10-24', start_time: '13:00', home_team: 'Wallan Women 1st XI', away_team: 'Gisborne',
  home_away: 'AWAY', opponent_name: 'Wallan Women 1st XI', venue: 'Greenhill Reserve', status: 'UPCOMING', notes: null, format_size: 11,
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(5000)
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const wire = { patches: [] }
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'gisborne', organisation_id: 'o1', capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' } }))
  await page.route(/\/api\/teams(\?.*)?$/, (r) => json(r, TEAMS))
  await page.route(/\/api\/fixtures(\?.*)?$/, (r) => json(r, [FIXTURE]))
  await page.route(/\/api\/fixtures\/f1$/, (r) => {
    if (r.request().method() === 'PATCH') wire.patches.push(JSON.parse(r.request().postData() || '{}'))
    return json(r, FIXTURE)
  })

  await page.goto(`${BASE}/admin/betterselect/fixtures`)
  await page.waitForSelector('button[title="Edit"]', { timeout: 20000 })
  await page.locator('button[title="Edit"]').first().click()
  const sel = page.locator('[data-fixture-team]')
  await sel.waitFor()

  await safe('options', async () => {
    console.log('\n── Our team offers teams, not just squads ──')
    const opts = await sel.locator('option').allInnerTexts()
    check('the two-team squad is one choice per team', opts.includes('MacIntyre 1s & 2s Squad › 1st XI') && opts.includes('MacIntyre 1s & 2s Squad › 2nd XI'), JSON.stringify(opts))
    check('the women\'s squad is one choice per team, by its own labels', opts.includes('Womens Squad › Womens A') && opts.includes('Womens Squad › Womens B'), JSON.stringify(opts))
    check('a one-team squad stays one plain choice', opts.includes('Jenson A Squad') && !opts.some((o) => o.startsWith('Jenson A Squad ›')), JSON.stringify(opts))
    check('the bare two-team squad is not offered on its own', !opts.includes('MacIntyre 1s & 2s Squad'), JSON.stringify(opts))
    check('the form opens on the fixture\'s own team', (await sel.locator('option:checked').innerText()) === 'MacIntyre 1s & 2s Squad › 2nd XI')
  })

  await safe('pick a team', async () => {
    console.log('\n── Picking a team sends the squad and the team ──')
    await sel.selectOption({ label: 'MacIntyre 1s & 2s Squad › 1st XI' })
    wire.patches.length = 0
    await page.getByRole('button', { name: 'Save' }).click(); await page.waitForTimeout(400)
    check('PATCH carries team_id and side_key', wire.patches.length === 1 && wire.patches[0].team_id === MAC && wire.patches[0].side_key === '1st grade', JSON.stringify(wire.patches))
  })

  await safe('one-team squad', async () => {
    console.log('\n── A one-team squad sends no team ──')
    await page.locator('button[title="Edit"]').first().click()
    await sel.waitFor()
    await sel.selectOption({ label: 'Jenson A Squad' })
    wire.patches.length = 0
    await page.getByRole('button', { name: 'Save' }).click(); await page.waitForTimeout(400)
    check('team_id is the squad, side_key is null', wire.patches[0]?.team_id === OLD && wire.patches[0]?.side_key === null, JSON.stringify(wire.patches))
  })

  await safe('no team', async () => {
    console.log('\n── No team assigned ──')
    await page.locator('button[title="Edit"]').first().click()
    await sel.waitFor()
    await sel.selectOption({ label: '— No team assigned —' })
    wire.patches.length = 0
    await page.getByRole('button', { name: 'Save' }).click(); await page.waitForTimeout(400)
    check('team_id null, side_key null', wire.patches[0]?.team_id === null && wire.patches[0]?.side_key === null, JSON.stringify(wire.patches))
  })

  await safe('390px', async () => {
    console.log('\n── 390px ──')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.locator('button[title="Edit"]').first().click()
    await sel.waitFor()
    check('no sideways overflow with the form open', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1))
  })

  check('no uncaught page errors', errors.length === 0, errors.join(' | '))
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  await browser.close()
  process.exit(FAIL ? 1 : 0)
}
run()
