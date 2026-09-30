/**
 * The hand-entry form warns about a game that does not add up and never
 * refuses to save it.
 *
 * Run:
 *   npx vite --port 5199 &
 *   node verification/verify_manual_game_check_browser.mjs
 *
 * Reported off Hamilton Veterans' 23 Oct 2011 game: both sides read 142/7. The
 * opposition-total boxes are only drawn for an opposition innings, so a total
 * typed there and then flipped to "Our innings" stayed on the row, hidden, and
 * was saved. Checked here, against the real form with the API stubbed at the
 * network layer:
 *   - flipping an innings to ours clears the total it was carrying;
 *   - a total already stored on our innings is not sent back on save;
 *   - the server's warnings show on the form, and in the confirm dialog;
 *   - a game with warnings SAVES (the PATCH is sent), because the person may
 *     not have the figure and must not be blocked;
 *   - a check that fails says nothing and does not stop the save.
 *
 * The check itself is the server's (backend/verification/verify_manual_game_check.py);
 * the stub here answers with canned warnings so this suite measures the FORM.
 *
 * Every read is guarded so a control run reports rather than crashing.
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

const WARNINGS = [
  { kind: 'bowling_runs', innings: 1, text: "Our bowlers' figures for innings 1 add up to 118 runs, plus 13 in byes, leg byes and penalties, which is 131. The opposition total is 142." },
  { kind: 'result_margin', innings: null, text: 'The result says "Lost By 16 Runs", a margin of 16 runs, but the totals entered are 125 to 142, a difference of 17.' },
]

const GAME = {
  id: 'g1', season_id: 's1', grade_id: 'gr1', played_at: '2011-10-23',
  home_team: 'Portland Over 60s', away_team: 'Mt Gambier Over 60s', opposition: 'Mt Gambier Over 60s',
  result: 'Lost By 16 Runs', winning_team: 'Mt Gambier Over 60s', match_format: '40 Over',
  batting_innings: [
    { player_id: 'p1', innings_number: 2, batting_position: 1, runs: 19, not_out: false, dismissal_type: 'b X' },
    { player_id: 'p2', innings_number: 2, batting_position: 2, runs: 23, not_out: true },
  ],
  bowling_spells: [{ player_id: 'p3', innings_number: 1, overs: 5, runs: 16, wickets: 0 }],
  fielding_stats: [],
  // As the old form saved it: our innings 2 carries a copy of their total.
  innings: [
    { innings_number: 1, batting_side: 'opposition', byes: 7, leg_byes: 6, wides: 1, no_balls: 1, penalty: 0,
      total_runs: 142, total_wickets: 7, overs: 40 },
    { innings_number: 2, batting_side: 'us', byes: 4, leg_byes: 3, wides: null, no_balls: null, penalty: 0,
      total_runs: 142, total_wickets: 7, overs: 40 },
  ],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ checkFails = false, checkWarnings = WARNINGS } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1400 } })
  const page = await ctx.newPage()
  const errors = [], checks = [], patches = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route(/\/api\//, async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = route.request().method()
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path.startsWith('/auth/me')) {
      return json({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'club_admin',
                    club_id: 'c1', club_slug: 'test-cc',
                    entitlements: { modules: ['stats', 'fees'], status: 'active' } })
    }
    if (/manual-entries\/games\/check$/.test(path)) {
      checks.push(JSON.parse(route.request().postData() || '{}'))
      return checkFails ? json({ detail: 'boom' }, 500) : json({ warnings: checkWarnings })
    }
    if (/manual-entries\/games\/g1$/.test(path)) {
      if (method === 'PATCH') { patches.push(JSON.parse(route.request().postData() || '{}')); return json({ id: 'g1' }) }
      return json(GAME)
    }
    if (/manual-entries\/games$/.test(path)) {
      return json([{ id: 'g1', played_at: '2011-10-23', opposition: 'Mt Gambier Over 60s', home_team: 'Portland Over 60s', away_team: 'Mt Gambier Over 60s', result: 'Lost By 16 Runs' }])
    }
    if (path === '/club-admin/players') return json([{ id: 'p1', name: 'Costello, John' }, { id: 'p2', name: 'Hollis, T' }, { id: 'p3', name: 'Hollis, T' }])
    if (path === '/club-admin/seasons') return json([{ id: 's1', name: '2011/12', year: 2011 }])
    if (/manual-entries\/grades$/.test(path)) return json([{ id: 'gr1', season_id: 's1', name: 'One Off 40 Overs' }])
    if (/known-values/.test(path)) return json({ oppositions: [], venues: [] })
    return json([])
  })
  await page.goto(`${BASE}/admin/manual-entries#game`, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Edit', exact: true }).first().click({ timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(400)
  return { page, ctx, errors, checks, patches }
}

const inningsTab = (page) => page.getByRole('button', { name: /^Innings/ }).first()
const cards = (page) => page.locator('div.border.rounded-md.p-3')
const totalsOf = async (card) => {
  const ins = card.locator('input')
  const n = await ins.count()
  if (n < 10) return null
  return [await ins.nth(7).inputValue(), await ins.nth(8).inputValue(), await ins.nth(9).inputValue()]
}

// ── the warnings show, and a stored stray total is not sent back ────────────
{
  const { page, ctx, errors, checks, patches } = await open()
  await inningsTab(page).click().catch(() => {})
  await page.waitForTimeout(900)

  const box = page.getByTestId('game-checks')
  ck('the form asks the server what does not add up', checks.length > 0)
  ck('and shows the answer in a box on the form', (await box.count()) > 0)
  const text = (await box.count()) ? await box.innerText() : ''
  ck('the box says how many things are wrong', /2 things do not add up/.test(text), text.slice(0, 120))
  ck('it says the person can still save', /still save/i.test(text), text.slice(0, 200))
  ck('and lists each warning in full', /118 runs/.test(text) && /difference of 17/.test(text), text)
  ck('the check is sent our innings with NO total on it',
     checks.length > 0 && (() => {
       const us = (checks.at(-1).innings || []).find(i => i.batting_side === 'us')
       return !!us && us.total_runs == null && us.total_wickets == null && us.overs == null
     })(), JSON.stringify(checks.at(-1)?.innings))
  ck('and the opposition innings keeps its total',
     (() => { const t = (checks.at(-1)?.innings || []).find(i => i.batting_side === 'opposition'); return t?.total_runs === 142 && t?.total_wickets === 7 })())

  // Saving with warnings showing: the dialog lists them, and Update still goes.
  await page.getByRole('button', { name: 'Update manual game' }).click().catch(() => {})
  await page.waitForTimeout(300)
  const dialog = await page.locator('.fixed.inset-0').innerText().catch(() => '')
  ck('the confirm dialog lists what does not add up', /do not add up yet/.test(dialog) && /118 runs/.test(dialog), dialog.slice(0, 200))
  ck('and says the game can still be saved', /still save/i.test(dialog), dialog.slice(0, 200))
  await page.locator('.fixed.inset-0').getByRole('button', { name: 'Update', exact: true }).click().catch(() => {})
  await page.waitForTimeout(500)
  ck('the game SAVES even though it has warnings', patches.length === 1, String(patches.length))
  const sent = patches[0]?.innings || []
  const ours = sent.find(i => i.batting_side === 'us')
  ck('and our innings goes to the server with no total, wickets or overs',
     !!ours && ours.total_runs == null && ours.total_wickets == null && ours.overs == null, JSON.stringify(ours))
  ck('the opposition total goes as entered',
     sent.find(i => i.batting_side === 'opposition')?.total_runs === 142)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── flipping the side clears the total it was carrying ──────────────────────
{
  const { page, ctx, errors } = await open()
  await inningsTab(page).click().catch(() => {})
  await page.waitForTimeout(300)
  const c = cards(page)
  ck('both innings are on screen', (await c.count()) === 2, String(await c.count()))
  if ((await c.count()) === 2) {
    const first = c.nth(0)
    ck('the opposition innings shows its total', JSON.stringify(await totalsOf(first)) === JSON.stringify(['142', '7', '40']),
       JSON.stringify(await totalsOf(first)))
    // Flip the opposition innings to ours: the boxes go, and so must the values.
    await first.locator('select').selectOption('us')
    await page.waitForTimeout(150)
    ck('flipping to Our innings hides the total boxes', (await first.locator('input').count()) < 10,
       String(await first.locator('input').count()))
    await first.locator('select').selectOption('opposition')
    await page.waitForTimeout(150)
    ck('and flipping back finds them EMPTY, not the old values',
       JSON.stringify(await totalsOf(first)) === JSON.stringify(['', '', '']),
       JSON.stringify(await totalsOf(first)))
    await first.locator('input').nth(7).fill('142')
    ck('a total typed after that is kept', (await first.locator('input').nth(7).inputValue()) === '142')
    ck('the extras beside it survive a flip',
       (await first.locator('input').nth(1).inputValue()) === '7', await first.locator('input').nth(1).inputValue())
  }
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── a game that adds up shows no box ────────────────────────────────────────
{
  const { page, ctx } = await open({ checkWarnings: [] })
  await inningsTab(page).click().catch(() => {})
  await page.waitForTimeout(900)
  ck('a game with nothing to warn about shows no warning box', (await page.getByTestId('game-checks').count()) === 0)
  await ctx.close()
}

// ── a failing check is silent and does not stop the save ────────────────────
{
  const { page, ctx, patches, errors } = await open({ checkFails: true })
  await inningsTab(page).click().catch(() => {})
  await page.waitForTimeout(900)
  ck('a check that fails draws nothing', (await page.getByTestId('game-checks').count()) === 0)
  await page.getByRole('button', { name: 'Update manual game' }).click().catch(() => {})
  await page.waitForTimeout(300)
  await page.locator('.fixed.inset-0').getByRole('button', { name: 'Update', exact: true }).click().catch(() => {})
  await page.waitForTimeout(500)
  ck('and the game still saves', patches.length === 1, String(patches.length))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
