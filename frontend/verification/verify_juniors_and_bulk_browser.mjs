// Drives the real screens in Chromium with the API stubbed at the network layer (v9.146.0):
//   Whiteboard and Selection board
//   * players whose squads are all junior sides (is_junior) are left out of the pool by default;
//   * "Show juniors (N)" puts them back, and a name typed in finds a junior either way;
//   Admin, Players
//   * "Not played in N years" narrows to the past players; "Select all shown" ticks them;
//   * Mark inactive sends ONE request with exactly the ticked ids (the request on the wire);
//   * ticking a row does not open the profile;
//   * 390px: no sideways overflow.
//
//   npx vite build && npx vite preview --port 5198 &
//   node frontend/verification/verify_juniors_and_bulk_browser.mjs [baseUrl]
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SHOTS = process.env.SHOTS || '/tmp'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const ME = {
  id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'piara', club_id: 'o1', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select', 'admin'], status: 'active' },
}
const F1 = '00000000-0000-4000-8000-0000000000f1'
const pid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const DAY = '2099-04-18'
const row = (n, name, junior) => ({
  id: pid(n), display_name: name, player_role: null, skill_positions: ['BAT'],
  squads: junior ? ['Year 4'] : ['1st XI'], squad_team_id: null, availability: 'AVAILABLE', availability_reason: null,
  last_played: '2099-03-01', photo_url: null, gender: 'female', is_inactive: false, is_current: true, is_junior: junior,
  selected: false, clash: [], clash_detail: [], also_in: [], clash_blocks: false, squad_match: true, tier: 1,
  gender_ok: true, recent_ok: true, score: 10 - n, recent: [], rule_flags: [], rule_notes: [], rule_state: 'ok',
})
const POOL = [
  row(1, 'Senior Ava', false), row(2, 'Senior Bea', false), row(3, 'Senior Cat', false), row(4, 'Senior Dee', false),
  row(5, 'Senior Eve', false), row(6, 'Junior Fay', true), row(7, 'Junior Gia', true), row(8, 'Junior Hal', true),
]
const FX = { id: F1, label: 'Rivals', opponent_name: 'Rivals', home_away: 'HOME', played_on: DAY, start_time: '1:00pm',
  round: 3, venue: 'Oval', team_name: "Women's A Grade", team_sequence: 1, grade_name: "Women's A Grade" }

const PLAYERS = [
  { id: 'p1', name: 'Old Timer One', last_played: '2016-02-01', status: 'active', is_current: true },
  { id: 'p2', name: 'Old Timer Two', last_played: '2018-12-01', status: 'active', is_current: true },
  { id: 'p3', name: 'Old Timer Three', last_played: '2019-01-20', status: 'active', is_current: true },
  { id: 'p4', name: 'Old Timer Four', last_played: '2020-03-07', status: 'active', is_current: true },
  { id: 'p5', name: 'Current Player', last_played: new Date().toISOString().slice(0, 10), status: 'active', is_current: true },
  { id: 'p6', name: 'Never Played', last_played: null, status: 'active', is_current: true },
].map((p) => ({ ...p, display_name_override: null, skill_positions: [], is_public: true, squad_team_id: null }))

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(url, width = 1440) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  const seen = { errors: [], bulk: [], profileOpens: 0 }
  page.on('pageerror', (e) => seen.errors.push(e.message))
  page.on('dialog', (d) => d.accept())
  const json = (r, b, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
  await page.route('**/api/**', (r) => {
    const req = r.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    const m = req.method()
    if (p === '/auth/me') return json(r, ME)
    if (/^\/selection\/overview/.test(p)) return json(r, { default_team_size: 11, fixtures: [{ ...FX, lineup: [], has_draft: false }] })
    if (/^\/selection\/[^/]+\/previous-xi/.test(p)) return json(r, { source_fixture_id: null, player_ids: [] })
    if (/^\/selection\/selected-players/.test(p)) return json(r, { player_ids: [] })
    if (/^\/selection\/[0-9a-f-]{36}\/draft/.test(p)) return json(r, { draft: null, version: 0 })
    if (new RegExp(`^/selection/${F1}$`).test(p)) {
      return json(r, { fixture: { ...FX, end_on: null, home_team: 'Club', away_team: 'Rivals', team_id: 't1', grade_id: 'g1' },
        lineup: [], pool: POOL, default_team_size: 11, rules: { active: false, applied: [], team: [] }, flags: {} })
    }
    if (p === '/club-admin/players') return json(r, PLAYERS)
    if (p === '/players/bulk-status' && m === 'POST') { seen.bulk.push(JSON.parse(req.postData() || '{}')); return json(r, { updated: 4, unchanged: 0, not_found: 0 }) }
    if (/^\/players\/[^/]+\/profile$/.test(p)) { seen.profileOpens++; return json(r, {}) }
    if (/teams|grades|seasons|players|squads/.test(p) && m === 'GET') return json(r, [])
    return json(r, {})
  })
  await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' })
  return { ctx, page, seen }
}

// ── Whiteboard ───────────────────────────────────────────────────────────────
{
  const { ctx, page, seen } = await open('/admin/betterselect/whiteboard')
  await page.locator('[data-pool-col]').waitFor({ timeout: 20000 })
  await page.waitForTimeout(500)
  const cards = () => page.locator('[data-pool-col] [data-player-card]').count()
  const names = () => page.locator('[data-pool-col]').innerText()
  ck('whiteboard: juniors are out of the pool by default', await cards() === 5 && !(await names()).includes('Fay, Junior') && (await names()).includes('Ava, Senior'), String(await cards()))
  ck('whiteboard: the toggle says how many juniors there are', await page.getByLabel('Show juniors (3)').count() === 1)
  await page.getByLabel('Find a player').fill('Junior Gia')
  await page.waitForTimeout(200)
  ck('whiteboard: a name typed in finds a junior', (await names()).includes('Gia, Junior'))
  await page.getByLabel('Find a player').fill('')
  await page.getByLabel('Show juniors (3)').check()
  await page.waitForTimeout(200)
  ck('whiteboard: Show juniors puts them back', await cards() === 8, String(await cards()))
  await page.screenshot({ path: `${SHOTS}/whiteboard_juniors.png` })
  ck('whiteboard: no script errors', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}

// ── Selection board ──────────────────────────────────────────────────────────
{
  const { ctx, page, seen } = await open(`/admin/betterselect/select/${F1}`)
  await page.getByText('Selected XI').first().waitFor({ timeout: 20000 })
  await page.waitForTimeout(500)
  const body = () => page.locator('body').innerText()
  ck('board: the count says 5 of 8 shown', (await body()).includes('5 of 8 shown'))
  ck('board: no junior in the pool', !(await body()).includes('Fay, Junior') && (await body()).includes('Ava, Senior'))
  const toggle = page.getByLabel('Show juniors (3)').first()
  ck('board: the toggle is offered', await toggle.count() === 1)
  if (await toggle.count()) {
    await toggle.check()
    await page.waitForTimeout(500)
    ck('board: Show juniors puts them back (8 of 8)', (await body()).includes('8 of 8 shown') && (await body()).includes('Fay, Junior'))
  }
  ck('board: no script errors', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}

// ── Admin, Players ───────────────────────────────────────────────────────────
for (const width of [1440, 390]) {
  const { ctx, page, seen } = await open('/admin/players', width)
  await page.getByText('Old Timer One').waitFor({ timeout: 20000 })
  await page.getByLabel('Not played in').selectOption('5')
  await page.waitForTimeout(200)
  const text = await page.locator('body').innerText()
  ck(`players ${width}: "Not played in 5 years" keeps the four past players`,
    text.includes('Old Timer Four') && !text.includes('Current Player') && !text.includes('Never Played'))
  await page.getByLabel('Select Old Timer Two').check()
  ck(`players ${width}: ticking a row does not open the profile`, seen.profileOpens === 0 && await page.getByText('1 selected').count() === 1)
  await page.getByLabel('Select all shown (4)').check()
  ck(`players ${width}: Select all shown ticks the four`, await page.getByText('4 selected').count() === 1)
  if (width === 390) {
    ck('players 390: no sideways overflow', !(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)))
    await page.screenshot({ path: `${SHOTS}/players_bulk_390.png` })
  } else {
    await page.screenshot({ path: `${SHOTS}/players_bulk_desktop.png` })
  }
  await page.getByRole('button', { name: 'Mark inactive' }).click()
  await page.waitForTimeout(400)
  const b = seen.bulk.at(-1) || {}
  ck(`players ${width}: ONE request, with exactly the four ticked ids`,
    seen.bulk.length === 1 && b.status === 'inactive' && JSON.stringify([...(b.player_ids || [])].sort()) === JSON.stringify(['p1', 'p2', 'p3', 'p4']),
    JSON.stringify(seen.bulk))
  ck(`players ${width}: no script errors`, seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
