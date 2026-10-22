// Drives the real /games/:id scorecard and its fall-of-wickets editor in Chromium with the API
// stubbed at the network layer.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_fow_editor_browser.mjs [baseUrl]
//
// Reported off a club card: six wickets fell and Cricket Australia held four fall-of-wicket rows
// (1, 3, 4, 5). The club has the rest in its scorebook and needs to type it in. Checks:
//   * the card says "4 of 6 wickets recorded" to everyone, and only a club editor sees EDIT;
//   * the editor opens on six wicket slots with what Cricket Australia holds filled in;
//   * a batter already used at one wicket cannot be picked at another;
//   * Save sends exactly the wickets typed (the request on the wire), and shows the server's
//     summary; a refusal from the server is shown and the form keeps what was typed;
//   * closing after a save reloads the scorecard;
//   * an uploaded card (is_manual) offers no EDIT;
//   * 390px: the editor does not overflow sideways.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || '/tmp'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const GID = 'bbbbbbbb-0000-0000-0000-000000000001'
const P = { Payne: 'g-payne', Hall: 'g-hall', Bivens: 'g-bivens', Sweet: 'g-sweet', Menezes: 'g-menezes', Cox: 'g-cox' }
const RUNS = { Payne: 40, Hall: 33, Bivens: 160, Sweet: 12, Menezes: 14, Cox: 60 }

const FOW4 = [[1, 73, 'Payne'], [3, 331, 'Bivens'], [4, 356, 'Sweet'], [5, 381, 'Menezes']]
const fowRow = ([w, s, n]) => ({ innings_number: 1, wicket_number: w, score_at_fall: s, player_name: `${n[0]} ${n}`, player_id: null })

const scorecard = (over = {}) => ({
  id: GID, home_team: 'Our Club', away_team: 'Opp', home_away_known: true, innings_order_known: true,
  played_at: '2026-01-10', result: 'WIN', winning_team: 'Our Club', organisation_id: null, is_manual: false,
  grade: { id: 'g1', name: 'A Grade', raw_name: 'A Grade' }, season: { id: 's1', name: 'Summer 2025/26' },
  innings_totals: { 1: { runs: 395, wickets: 6, extras: 9 }, 2: { runs: 140, wickets: 10, extras: 7 } },
  batting: [], bowling: [], opp_batting: [], opp_bowling: [], fielding: [],
  fall_of_wickets: FOW4.map(fowRow),
  partnerships: [
    { innings_number: 1, wicket_number: 1, runs: 73, batter1_name: 'P Payne', batter2_name: 'H Hall' },
    { innings_number: 1, wicket_number: 4, runs: 25, batter1_name: 'S Sweet', batter2_name: 'C Cox' },
  ],
  ...over,
})

const EDITOR = {
  game_id: GID,
  innings: [{
    innings_number: 1, edited: false, wickets: 6,
    batters: Object.keys(RUNS).map((n, i) => ({ participant_id: P[n], name: `${n[0]} ${n}`, bat_order: i + 1, runs: RUNS[n], dismissal: 'Bowled' })),
    fow: FOW4.map(([w, s, n]) => ({ wicket_number: w, score_at_fall: s, participant_id: P[n], batter_name: `${n[0]} ${n}` })),
    stands: [
      { wicket_number: 1, runs: 73, batter1_name: 'P Payne', batter2_name: 'H Hall' },
      { wicket_number: 4, runs: 25, batter1_name: 'S Sweet', batter2_name: 'C Cox' },
    ],
    missing: { 2: 'no score recorded for this wicket', 3: 'no score recorded for wicket 2', 6: 'no score recorded for this wicket' },
  }],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ admin = true, card = scorecard(), putStatus = 200, width = 1280 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1200 } })
  const page = await ctx.newPage()
  const seen = { scorecards: 0, puts: [], deletes: 0, errors: [] }
  page.on('pageerror', (e) => seen.errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace(/^\/api/, '')
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (/^\/auth\/me/.test(path)) {
      return admin
        ? json({ id: 'u1', username: 'scorer', display_name: 'Scorer', role: 'club_admin', club_slug: 'our-club', club_id: 'org1', entitlements: { modules: ['admin'], status: 'active' } })
        : route.fulfill({ status: 401, body: '{}' })
    }
    if (/\/fall-of-wickets\/editor$/.test(path)) return json(EDITOR)
    if (/\/fall-of-wickets\/1$/.test(path) && req.method() === 'PUT') {
      const body = JSON.parse(req.postData() || '{}')
      seen.puts.push({ path, body })
      if (putStatus !== 200) return json({ detail: 'Wicket 3: 60 is lower than the score at an earlier wicket (150).' }, putStatus)
      return json({
        summary: 'Fall of wickets for innings 1: 6 of 6 wickets entered, 6 partnerships worked out.', warnings: [],
        innings: { ...EDITOR.innings[0], edited: true, missing: {},
          fow: body.rows.map(r => ({ ...r, batter_name: null })),
          stands: [73, 77, 181, 25, 25, 19].map((runs, i) => ({ wicket_number: i + 1, runs, batter1_name: 'A', batter2_name: 'B' })) },
      })
    }
    if (/\/fall-of-wickets\/1$/.test(path) && req.method() === 'DELETE') { seen.deletes++; return json({ summary: 'reset', warnings: [], innings: EDITOR.innings[0] }) }
    if (/\/games\/[^/]+\/scorecard/.test(path)) { seen.scorecards++; return json(card) }
    return json({})
  })
  await page.goto(`${BASE}/games/${GID}`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('text=FALL OF WICKETS', { timeout: 20000 })
  return { ctx, page, seen }
}

// ── Everyone sees the gap; only an editor sees EDIT ──────────────────────────
{
  const { ctx, page, seen } = await open({ admin: false })
  ck('public: the card says how many wickets are recorded',
    await page.getByText('4 of 6 wickets recorded').count() === 1)
  ck('public: no EDIT button', await page.getByRole('button', { name: 'EDIT' }).count() === 0)
  ck('public: no script errors', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}
{
  const { ctx, page } = await open({ card: scorecard({ is_manual: true }) })
  ck('an uploaded card offers no EDIT', await page.getByRole('button', { name: 'EDIT' }).count() === 0)
  await ctx.close()
}

// ── The editor ───────────────────────────────────────────────────────────────
{
  const { ctx, page, seen } = await open()
  ck('an editor sees EDIT', await page.getByRole('button', { name: 'EDIT' }).count() === 1)
  await page.getByRole('button', { name: 'EDIT' }).click()
  await page.waitForSelector('text=EDIT FALL OF WICKETS')
  await page.waitForSelector('input[aria-label="Score at wicket 1"]')

  ck('six wicket slots', await page.locator('input[aria-label^="Score at wicket"]').count() === 6)
  ck('what Cricket Australia holds is filled in',
    await page.locator('input[aria-label="Score at wicket 3"]').inputValue() === '331'
    && await page.locator('select[aria-label="Batter out at wicket 3"]').inputValue() === P.Bivens)
  ck('the missing wickets are empty',
    await page.locator('input[aria-label="Score at wicket 2"]').inputValue() === ''
    && await page.locator('select[aria-label="Batter out at wicket 2"]').inputValue() === '')
  ck('says why a wicket has no partnership', await page.getByText('No partnership for this wicket: no score recorded for wicket 2.').count() === 1)
  ck('shows the stand a wicket already has', await page.getByText('Partnership: 73 (P Payne and H Hall)').count() === 1)
  ck('Save is off until something changes', await page.getByRole('button', { name: 'SAVE WICKETS' }).isDisabled())

  const optionDisabled = (w, pid) => page.locator(`select[aria-label="Batter out at wicket ${w}"] option[value="${pid}"]`).isDisabled()
  ck('a batter used at wicket 1 cannot be picked at wicket 2', await optionDisabled(2, P.Payne))
  ck('a batter nobody has used can be', !(await optionDisabled(2, P.Hall)))

  await page.locator('input[aria-label="Score at wicket 2"]').fill('150')
  await page.locator('select[aria-label="Batter out at wicket 2"]').selectOption(P.Hall)
  await page.locator('input[aria-label="Score at wicket 6"]').fill('400')
  await page.locator('select[aria-label="Batter out at wicket 6"]').selectOption(P.Cox)
  await page.screenshot({ path: `${SHOTS}/fow_editor_desktop.png` })

  await page.getByRole('button', { name: 'SAVE WICKETS' }).click()
  await page.waitForSelector('text=6 of 6 wickets entered')
  ck('exactly one PUT, to the right innings', seen.puts.length === 1 && seen.puts[0].path === `/games/${GID}/fall-of-wickets/1`, JSON.stringify(seen.puts.map(p => p.path)))
  const want = [[1, 73, 'Payne'], [2, 150, 'Hall'], [3, 331, 'Bivens'], [4, 356, 'Sweet'], [5, 381, 'Menezes'], [6, 400, 'Cox']]
    .map(([w, s, n]) => ({ wicket_number: w, score_at_fall: s, participant_id: P[n] }))
  ck('the request carries exactly the six wickets typed', JSON.stringify(seen.puts[0]?.body?.rows) === JSON.stringify(want), JSON.stringify(seen.puts[0]?.body))
  ck('the server summary is shown', await page.getByText('6 partnerships worked out').count() >= 1)
  ck('Reset is offered once the club has typed wickets', await page.getByRole('button', { name: 'RESET TO CRICKET AUSTRALIA' }).count() === 1)

  const before = seen.scorecards
  await page.getByRole('button', { name: 'DONE' }).click()
  await page.waitForFunction(() => !document.body.innerText.includes('EDIT FALL OF WICKETS'))
  await page.waitForTimeout(300)
  ck('closing after a save reloads the scorecard', seen.scorecards > before, `${before} -> ${seen.scorecards}`)
  ck('no script errors', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}

// ── A refusal from the server ────────────────────────────────────────────────
{
  const { ctx, page, seen } = await open({ putStatus: 422 })
  await page.getByRole('button', { name: 'EDIT' }).click()
  await page.waitForSelector('input[aria-label="Score at wicket 2"]')
  await page.locator('input[aria-label="Score at wicket 2"]').fill('150')
  await page.locator('input[aria-label="Score at wicket 3"]').fill('60')
  await page.getByRole('button', { name: 'SAVE WICKETS' }).click()
  await page.waitForSelector('text=is lower than the score at an earlier wicket')
  ck('the server refusal is shown', true)
  ck('what was typed is kept', await page.locator('input[aria-label="Score at wicket 3"]').inputValue() === '60')
  ck('and nothing is marked saved', await page.getByRole('button', { name: 'CLOSE' }).count() === 1)
  await ctx.close()
}

// ── 390px ────────────────────────────────────────────────────────────────────
{
  const { ctx, page } = await open({ width: 390 })
  await page.getByRole('button', { name: 'EDIT' }).click()
  await page.waitForSelector('input[aria-label="Score at wicket 6"]')
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no sideways overflow with the editor open', over <= 0, `overflow ${over}px`)
  const modal = await page.locator('div.pb-card', { hasText: 'EDIT FALL OF WICKETS' }).last().boundingBox()
  ck('390px: the editor fits the screen', modal && modal.x >= 0 && modal.x + modal.width <= 390, JSON.stringify(modal))
  await page.screenshot({ path: `${SHOTS}/fow_editor_390.png`, fullPage: false })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
