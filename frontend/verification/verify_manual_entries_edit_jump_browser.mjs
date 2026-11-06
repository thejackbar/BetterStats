/**
 * Edit on the Adjustments tab puts its form in view at once, however far down the list the click was.
 *
 * Run:
 *   npx vite --port 5199 &
 *   node verification/verify_manual_entries_edit_jump_browser.mjs [baseUrl]
 *
 * Edit used to run window.scrollTo({ top: 0, behavior: 'smooth' }), a visible glide up the page from the
 * bottom of a long list (reported on Manual Games, which was fixed first; the Adjustments tab had the same
 * code). It now sets the position outright, from a shared hook (useJumpToForm). The API is stubbed at the
 * network layer. The position is read 120 ms after the click: a smooth scroll over this distance is nowhere
 * near done by then, so only an instant jump passes. Every read is guarded, so a CONTROL RUN against the
 * previous build reports each check instead of dying on the first one.
 */
import { chromium } from 'playwright'
import { existsSync } from 'node:fs'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

// 30 season adjustments (newest first) and 3 older career-only ones, so the last rows are far below the form.
const SEASON_ROWS = Array.from({ length: 30 }, (_, i) => ({
  id: `sa${i + 1}`, player_id: 'p1', player_name: `Season Player ${i + 1}`, season_id: 's1', season_name: 'Summer 2010/11',
  grade_id: null, games_played: 10, batting_runs: 100 + i, bowling_wickets: 3, fielding_catches: 2, fielding_catches_wk: 0,
  created_at: `2026-10-${String(30 - i).padStart(2, '0')}T10:00:00Z`,
}))
const CAREER_ROWS = Array.from({ length: 3 }, (_, i) => ({
  id: `ca${i + 1}`, player_id: 'p1', player_name: `Career Player ${i + 1}`, games_played: 5, batting_runs: 50,
  bowling_wickets: 1, fielding_catches: 1, fielding_catches_wk: 0, created_at: `2026-01-0${i + 1}T10:00:00Z`,
}))

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1600 } })
const page = await ctx.newPage()
page.setDefaultTimeout(4000)
page.setDefaultNavigationTimeout(30000)
const errors = []
page.on('pageerror', e => errors.push(String(e)))
await page.route(/\/api\//, async route => {
  const p = new URL(route.request().url()).pathname.replace(/^\/api/, '')
  const json = b => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  if (p.startsWith('/auth/me')) {
    return json({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'club_admin', club_id: 'c1',
                  club_slug: 'shoalwater', entitlements: { modules: ['stats', 'fees'], status: 'active' } })
  }
  if (/manual-entries\/season-adjustments$/.test(p)) return json(SEASON_ROWS)
  if (/manual-entries\/career-adjustments$/.test(p)) return json(CAREER_ROWS)
  if (/admin\/seasons|manual-entries\/seasons/.test(p)) return json([{ id: 's1', name: 'Summer 2010/11', year: 2010 }])
  if (/known-values/.test(p)) return json({ oppositions: [], venues: [] })
  if (/admin\/players/.test(p)) return json([{ id: 'p1', display_name: 'Alpha, Anne', is_player: true }])
  return json([])
})
await page.goto(`${BASE}/admin/manual-entries#season`, { waitUntil: 'domcontentloaded' })
await page.waitForSelector('text=Existing season adjustments', { timeout: 20000 }).catch(() => {})
await page.waitForTimeout(500)

const headingTop = text => page.evaluate(t => {
  const h = [...document.querySelectorAll('h3')].find(e => e.textContent.trim() === t)
  return h ? Math.round(h.getBoundingClientRect().top) : null
}, text)
const toBottom = () => page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
const editOn = name => page.locator('tr', { hasText: name }).first().getByRole('button', { name: 'Edit', exact: true })

// The form is far above the viewport while the last rows are in view.
await page.locator('tr', { hasText: 'Career Player 3' }).first().scrollIntoViewIfNeeded().catch(() => {})
const before = await headingTop('New season adjustment')
ck('the form is well above the viewport when the last row is in view', before !== null && before < -300, `top ${before}`)

// A season adjustment, from the bottom of the list.
await editOn('Season Player 30').click().catch(() => {})
await page.waitForTimeout(120)
let top = await headingTop('Edit season adjustment')
ck('Edit on a season adjustment puts the form at the top of the view at once', top !== null && top >= 0 && top < 200, `top ${top}`)

// A career-only adjustment (the same tab lists them), from the bottom again.
await toBottom()
await editOn('Career Player 3').click().catch(() => {})
await page.waitForTimeout(120)
top = await headingTop('Edit season adjustment')
ck('Edit on a career-only adjustment does the same', top !== null && top >= 0 && top < 200, `top ${top}`)

// The match really is loaded into the form (the jump is not at the cost of the data).
const playerShown = await page.locator('body').innerText().catch(() => '')
ck('and the row is loaded into the form', /Cancel edit/.test(playerShown) && /Update adjustment/.test(playerShown))

// A second Edit while the form is already showing jumps again.
await toBottom()
await editOn('Season Player 29').click().catch(() => {})
await page.waitForTimeout(120)
top = await headingTop('Edit season adjustment')
ck('a second Edit from the bottom jumps again', top !== null && top >= 0 && top < 200, `top ${top}`)
ck('no page errors', errors.length === 0, errors.join(' | '))

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
