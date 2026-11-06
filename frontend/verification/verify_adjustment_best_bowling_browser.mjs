/**
 * The adjustment form asks for best bowling ONCE, as wickets/runs.
 *
 * Run:
 *   npx vite --port 5199 &
 *   node verification/verify_adjustment_best_bowling_browser.mjs
 *
 * Reported by Hamilton Veterans (Oct 2026): best bowling read "1 wicket", "4wickets". The form had two
 * boxes, "Best, wickets" and "Best figures", and a person who filled only the first left the profile
 * with nothing to print but a wicket count. Checked against the real form with the API stubbed at the
 * network layer, asserting the exact request on the wire:
 *   - there is one best-bowling box and no separate wickets box;
 *   - typing 4/13 sends figures 4/13 and wickets 4 together, so they cannot disagree;
 *   - a row saved earlier as a bare wicket count says so, offers to be re-entered, and is NOT wiped by
 *     saving the form untouched (an absent entry is not a clear);
 *   - "or remove it" clears the wickets and sends null;
 *   - 390px wide has no sideways scroll.
 *
 * Every read is guarded so a control run reports rather than crashing.
 */
import { chromium } from 'playwright'
import { existsSync } from 'node:fs'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const ROW = {
  id: 7, kind: 'season', player_id: 'p1', season_id: 's1', grade_id: null,
  player_name: 'Baker, Ken', season_name: '2012/13',
  games_played: 8, batting_innings: 8, batting_runs: 51, batting_not_outs: 0, batting_balls: 0, batting_fours: 0, batting_sixes: 0,
  batting_fifties: 0, batting_hundreds: 0, batting_ducks: 0, batting_high_score: 15, batting_high_score_not_out: false,
  bowling_innings: 6, bowling_overs: 39, bowling_balls: 0, bowling_maidens: 0, bowling_runs: 113, bowling_wickets: 11,
  bowling_wides: 0, bowling_no_balls: 0, bowling_five_wicket_innings: 0,
  bowling_best_wickets: 4, bowling_best_figures: null,
  fielding_catches: 0, fielding_catches_wk: 0, fielding_run_outs: 0, fielding_stumpings: 0, notes: '',
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(width = 1440) {
  const ctx = await browser.newContext({ viewport: { width, height: 1600 } })
  const page = await ctx.newPage()
  const errors = [], patches = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route(/\/api\//, async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = route.request().method()
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path.startsWith('/auth/me')) {
      return json({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'club_admin', club_id: 'c1', club_slug: 'test-cc',
                    entitlements: { modules: ['stats', 'fees'], status: 'active' } })
    }
    if (/season-adjustments\/7$/.test(path)) {
      if (method === 'PATCH') { patches.push(JSON.parse(route.request().postData() || '{}')); return json({ ...ROW }) }
      return json(ROW)
    }
    if (/manual-entries\/season-adjustments$/.test(path)) return json([ROW])
    if (/manual-entries\/career-adjustments$/.test(path)) return json([])
    if (path === '/club-admin/players') return json([{ id: 'p1', name: 'Baker, Ken' }])
    if (path === '/club-admin/seasons') return json([{ id: 's1', name: '2012/13', year: 2012 }])
    if (/manual-entries\/grades$/.test(path)) return json([])
    if (/known-values/.test(path)) return json({ oppositions: [], venues: [] })
    return json([])
  })
  await page.goto(`${BASE}/admin/manual-entries#season`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Edit', exact: true }).first().click({ timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(600)
  return { page, ctx, errors, patches }
}

const save = async (page) => {
  await page.getByRole('button', { name: 'Update adjustment', exact: true }).click().catch(() => {})
  await page.waitForTimeout(300)
  await page.locator('.fixed.inset-0').getByRole('button', { name: 'Update', exact: true }).click().catch(() => {})
  await page.waitForTimeout(500)
}

// ── one box ─────────────────────────────────────────────────────────────────
{
  const { page, ctx, errors, patches } = await open()
  const box = page.getByTestId('best-bowling')
  ck('there is one best-bowling box', (await box.count()) === 1, String(await box.count()))
  ck('and no separate "wickets" box beside it', (await page.getByText('Best — wickets', { exact: true }).count()) === 0)
  const label = (await page.locator('label[for="best-bowling"]').innerText().catch(() => ''))
  ck('it says wickets/runs and shows an example', /wickets\/runs/.test(label) && /4\/13/.test(label), label)

  const legacy = page.getByTestId('best-bowling-legacy')
  ck('a row saved as a bare wicket count says so', (await legacy.count()) === 1)
  const text = (await legacy.count()) ? await legacy.innerText() : ''
  ck('it names the count and says the profile can only say that', /saved as 4 wickets with no runs/.test(text), text)

  // Saved untouched: the old wickets are kept, not wiped.
  await save(page)
  ck('saving untouched sends one update', patches.length === 1, String(patches.length))
  ck('and keeps the wickets it had', patches[0]?.bowling_best_wickets === 4 && patches[0]?.bowling_best_figures == null,
     JSON.stringify([patches[0]?.bowling_best_wickets, patches[0]?.bowling_best_figures]))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── typing the figures ──────────────────────────────────────────────────────
{
  const { page, ctx, patches } = await open()
  await page.getByTestId('best-bowling').fill('5/18')
  await page.waitForTimeout(150)
  ck('the legacy note goes once figures are entered', (await page.getByTestId('best-bowling-legacy').count()) === 0)
  await save(page)
  ck('the update carries the figures as typed', patches.length === 1 && patches[0]?.bowling_best_figures === '5/18',
     JSON.stringify(patches[0]?.bowling_best_figures))
  ck('and the wickets read off them (5, not the old 4)', patches[0]?.bowling_best_wickets === 5, JSON.stringify(patches[0]?.bowling_best_wickets))
  await ctx.close()
}

// ── a different separator, and a typo ───────────────────────────────────────
{
  const { page, ctx, patches } = await open()
  await page.getByTestId('best-bowling').fill('3-21')
  await save(page)
  ck('3-21 works as 3/21 does', patches[0]?.bowling_best_wickets === 3 && patches[0]?.bowling_best_figures === '3-21',
     JSON.stringify([patches[0]?.bowling_best_wickets, patches[0]?.bowling_best_figures]))
  await ctx.close()
}

// ── removing it ─────────────────────────────────────────────────────────────
{
  const { page, ctx, patches } = await open()
  await page.getByTestId('best-bowling-clear').click().catch(() => {})
  await page.waitForTimeout(150)
  ck('"or remove it" hides the note', (await page.getByTestId('best-bowling-legacy').count()) === 0)
  await save(page)
  ck('and sends no best at all', patches.length === 1 && patches[0]?.bowling_best_wickets == null && patches[0]?.bowling_best_figures == null,
     JSON.stringify([patches[0]?.bowling_best_wickets, patches[0]?.bowling_best_figures]))
  await ctx.close()
}

// ── a phone ─────────────────────────────────────────────────────────────────
{
  const { page, ctx } = await open(390)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('at 390px the page does not scroll sideways', over <= 0, `overflow ${over}px`)
  await page.getByTestId('best-bowling').scrollIntoViewIfNeeded().catch(() => {})
  await page.screenshot({ path: process.env.SHOT || '/tmp/best-bowling-390.png' })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
