// Drives the real /admin/import wizard in Chromium with the API stubbed at the
// network layer, for a club history book that stops at a season.
//
//   npx vite build --outDir /tmp/dist && npx vite preview --outDir /tmp/dist --port 5199 &
//   node frontend/verification/verify_import_through_season_browser.mjs [baseUrl]
//
// Reported by Kalamunda Cricket Club: their "A Century of Cricket 1904/05 -
// 2004/05" book was reconciled against the player's whole online record, so a
// player with online data from 2012 lost the book entirely. The server side is
// proved in backend/verification/verify_import_through_season.py; this proves
// the screen asks for the cut-off, refuses to import without a usable one, and
// sends exactly what the server expects.
//
// The sheet is the three players typed from the photographed pages
// (backend/verification/fixtures/kalamunda_century_of_cricket.csv). The numbers
// the stub returns are the ones that suite reads back from a real Postgres.
//
// Every read is guarded, so a control run against a build without the feature
// reports each check rather than dying on the first absent locator.
import { existsSync, readFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOT_DIR || ''

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const CSV = readFileSync(join(HERE, '../../backend/verification/fixtures/kalamunda_century_of_cricket.csv'), 'utf8')
const [headLine, ...bodyLines] = CSV.trim().split('\n')
const HEADERS = headLine.split(',')
const ROWS = bodyLines.map(l => Object.fromEntries(l.split(',').map((v, i) => [HEADERS[i], v])))

const MAPPING = {
  player_name: 'Name', games_played: 'Games Played', batting_innings: 'No Innings', batting_runs: 'Total Runs',
  batting_not_outs: 'NO', batting_fifties: "No 50's", batting_hundreds: "No 100's",
  batting_high_score: 'Highest Score', bowling_overs: 'Overs Bowled', bowling_maidens: 'Maidens',
  bowling_runs: 'Bowling Runs', bowling_wickets: 'Total Wickets', bowling_five_wicket_innings: 'No 5wkt Inns',
  bowling_best_figures: 'Best Bowling Inn', fielding_catches: 'Catches',
}

// What the server returned for this sheet in the real-Postgres suite: book 64 games,
// 19 online to 2004/05, 26 after, 1839 runs in the end. T Overton: online all after.
const PREVIEW_CUT = [
  { player_id: 'p-m', player_name: 'TRAVCICH M', new: false, club_games: 64, club_runs: 1158, gr_games: 19, gr_runs: 400,
    residual_games: 45, residual_runs: 758, online_after_games: 26, online_after_runs: 681, final_games: 90, final_runs: 1839,
    season_deltas: 0, gr_exceeds: false },
  { player_id: 'p-t', player_name: 'OVERTON T', new: false, club_games: 42, club_runs: 777, gr_games: 0, gr_runs: 0,
    residual_games: 42, residual_runs: 777, online_after_games: 20, online_after_runs: 410, final_games: 62, final_runs: 1187,
    season_deltas: 0, gr_exceeds: false },
]
// The control: no cut-off, the book is compared with the whole online record.
const PREVIEW_WHOLE = [
  { player_id: 'p-m', player_name: 'TRAVCICH M', new: false, club_games: 64, club_runs: 1158, gr_games: 45, gr_runs: 1081,
    residual_games: 19, residual_runs: 77, online_after_games: 0, online_after_runs: 0, final_games: 64, final_runs: 1158,
    season_deltas: 0, gr_exceeds: true },
]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1500 } })
  const page = await ctx.newPage()
  const errors = []
  const wire = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route(/\/api\//, async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (/club-admin\/imports\/preview$/.test(path)) {
      return json({
        filename: 'kalamunda.csv', headers: HEADERS, field_options: Object.keys(MAPPING), row_count: ROWS.length,
        mapping_suggestions: Object.fromEntries(Object.entries(MAPPING).map(([f, c]) => [f, { column: c, confidence: 1 }])),
        granularity_guess: 'career', sample_rows: ROWS, rows: ROWS,
      })
    }
    if (/club-admin\/imports\/resolve$/.test(path)) {
      const body = JSON.parse(route.request().postData() || '{}')
      wire.push({ path, body })
      const cut = body.through_season ? { year: 2004, label: body.through_season } : null
      return json({
        through: cut, granularity: 'career', columns_used: MAPPING, grades: [], seasons: [], grade_options: [],
        players: ROWS.map((r, i) => ({ raw_name: r.Name, player_id: `p-${i}`, matched_name: r.Name, status: 'exact',
                                         auto_status: 'exact', confidence: 1, candidates: [] })),
        preview: cut ? PREVIEW_CUT : PREVIEW_WHOLE, rounding_notes: [],
        warnings: cut ? [] : ['Online (GR) data already shows more than your sheet for: TRAVCICH M, OVERTON T — we\'ll show the higher online figure.'],
        totals: { rows: 3, players_matched: 3, players_new: 0, players_unresolved: 0, rows_skipped: 0 },
      })
    }
    if (/club-admin\/imports\/commit$/.test(path)) {
      const body = JSON.parse(route.request().postData() || '{}')
      wire.push({ path, body })
      return json({ batch_id: 'b1', players_imported: 3, rows_written: 3, players_created: 0, deltas_written: 3,
                    rows_skipped: 0, through: body.through_season ? { year: 2004, label: body.through_season } : null,
                    preview: [] })
    }
    if (/club-admin\/imports$/.test(path)) {
      return json({ imports: [{ id: 'b0', filename: 'kalamunda.csv', status: 'committed', granularity: 'career',
                                row_count: 3, stats_rows: 3, through_label: '2004/05', created_at: '2026-10-13T00:00:00Z' }] })
    }
    if (path.startsWith('/auth/me')) {
      return json({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'club_admin', club_id: 'c1',
                    club_slug: 'test-cc', entitlements: { modules: ['stats', 'fees'], status: 'active' } })
    }
    return json([])
  })
  await page.goto(`${BASE}/admin/import`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('text=Import historical stats', { timeout: 20000 }).catch(() => {})
  return { page, ctx, errors, wire }
}

async function parseSheet(page) {
  const input = page.locator('input[type=file]').first()
  await input.setInputFiles({ name: 'kalamunda.csv', mimeType: 'text/csv', buffer: Buffer.from(CSV) })
  await page.getByRole('button', { name: 'PARSE FILE' }).click()
  await page.waitForSelector('text=THIS SHEET HOLDS', { timeout: 10000 }).catch(() => {})
  await page.waitForTimeout(400)
}
const lastResolve = (wire) => [...wire].reverse().find(w => /resolve$/.test(w.path))?.body
const nextBtn = (page) => page.getByRole('button', { name: /NEXT: MATCH PLAYERS/ })
const shot = async (page, name) => { if (SHOTS) { mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: join(SHOTS, name), fullPage: true }) } }
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)

{
  console.log('\nThe Columns step asks how far the figures go')
  const { page, ctx, errors, wire } = await open()
  const hist = await page.locator('text=TO 2004/05').count()
  ck('the past-imports list names the cut-off of an earlier history book', hist > 0)
  ck('there is a link to the history book template',
    (await page.locator('a[href$="/club-admin/imports/summary-template.csv"]').count()) > 0)
  await parseSheet(page)
  const block = page.getByTestId('through-block')
  ck('the step has a "the figures run" choice', await block.isVisible().catch(() => false))
  const body0 = lastResolve(wire)
  ck('by default it is an ordinary import: no cut-off on the wire', body0 && body0.through_season === null,
    JSON.stringify(body0 && body0.through_season))

  await page.getByTestId('through-to_season').click().catch(() => {})
  ck('choosing "only up to a season" shows a season box', await page.getByTestId('through-input').isVisible().catch(() => false))
  ck('and blocks Next until there is one', await nextBtn(page).isDisabled().catch(() => false))
  ck('and says what is missing', /Enter the last season the sheet covers/.test(await page.locator('body').innerText()))
  for (const bad of ['2004', '2004/06', '2004/']) {
    await page.getByTestId('through-input').fill(bad).catch(() => {})
    ck(`"${bad}" is not accepted: Next stays blocked`, await nextBtn(page).isDisabled().catch(() => false))
    ck(`"${bad}" sends no cut-off to the server`, (lastResolve(wire) || {}).through_season === null)
  }
  const sentBefore = wire.length
  await page.getByTestId('through-input').fill('2004/05').catch(() => {})
  await page.waitForTimeout(500)
  const note = await page.getByTestId('through-note').innerText().catch(() => '')
  ck('"2004/05" is read back: up to and including 2004/05', /up to and including 2004\/05/.test(note), note)
  ck('and says online from 2005/06 is left alone', /from 2005\/06 onwards is left alone/.test(note), note)
  ck('Next is open', await nextBtn(page).isEnabled().catch(() => false))
  ck('the server is asked again with exactly "2004/05"', wire.length > sentBefore && lastResolve(wire)?.through_season === '2004/05',
    JSON.stringify(lastResolve(wire)?.through_season))
  await shot(page, 'columns-step.png')

  console.log('\nThe review shows the book beside the online record on both sides of the cut-off')
  await nextBtn(page).click().catch(() => {})
  await page.getByRole('button', { name: /NEXT: REVIEW/ }).click().catch(() => {})
  await page.waitForSelector('text=Reconciliation preview', { timeout: 8000 }).catch(() => {})
  const text = await page.locator('body').innerText()
  ck('the review has an "online after 2004/05" column', await page.getByTestId('after-col').isVisible().catch(() => false))
  ck('its heading says the sheet is to 2004/05', /YOUR SHEET \(TO 2004\/05\)/i.test(text))
  ck('TRAVCICH M reads 64 + 26 = 90 games', /TRAVCICH M[\s\S]{0,80}\b64\b[\s\S]{0,40}\b19\b[\s\S]{0,40}\+45[\s\S]{0,40}\+26[\s\S]{0,40}\b90\b/.test(text))
  ck('the explanation names 2004/05', /online to 2004\/05 \+ what your sheet adds \+ online after 2004\/05/i.test(text))
  ck('no "GR higher" flag on a book that stops early', !/GR HIGHER/.test(text))
  ck('no warning that online is higher', !/already shows more than your sheet/.test(text))
  ck('no horizontal overflow at 1440px', (await overflow(page)) <= 0)
  await shot(page, 'review-to-2004-05.png')
  await page.getByRole('button', { name: /^IMPORT 2 PLAYERS/ }).click().catch(() => {})
  await page.waitForSelector('text=IMPORT COMPLETE', { timeout: 8000 }).catch(() => {})
  const commit = [...wire].reverse().find(w => /commit$/.test(w.path))?.body
  ck('the commit carries through_season "2004/05"', commit?.through_season === '2004/05', JSON.stringify(commit?.through_season))
  ck('and the same mapping and rows', commit?.rows?.length === 3 && commit?.mapping?.batting_runs === 'Total Runs')
  ck('the finished card says the figures run up to 2004/05',
    /run up to 2004\/05/.test(await page.locator('body').innerText()))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  console.log('\nControl: an ordinary whole-career sheet reads as it always did')
  const { page, ctx, errors, wire } = await open()
  await parseSheet(page)
  await nextBtn(page).click().catch(() => {})
  await page.getByRole('button', { name: /NEXT: REVIEW/ }).click().catch(() => {})
  await page.waitForSelector('text=Reconciliation preview', { timeout: 8000 }).catch(() => {})
  const text = await page.locator('body').innerText()
  ck('no "online after" column', !(await page.getByTestId('after-col').isVisible().catch(() => false)))
  ck('the old heading is unchanged', /ONLINE \(GR\)/.test(text) && /\+ RESIDUAL/.test(text))
  ck('the old flag is still there', /GR HIGHER/.test(text))
  await page.getByRole('button', { name: /^IMPORT 1 PLAYER/ }).click().catch(() => {})
  await page.waitForSelector('text=IMPORT COMPLETE', { timeout: 8000 }).catch(() => {})
  const commit = [...wire].reverse().find(w => /commit$/.test(w.path))?.body
  ck('the commit carries no cut-off', commit && commit.through_season === null, JSON.stringify(commit?.through_season))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  console.log('\nOn a phone')
  const { page, ctx } = await open({ width: 390 })
  await parseSheet(page)
  await page.getByTestId('through-to_season').click().catch(() => {})
  await page.getByTestId('through-input').fill('2004/05').catch(() => {})
  await page.waitForTimeout(400)
  ck('no horizontal overflow at 390px on the Columns step', (await overflow(page)) <= 0, `${await overflow(page)}px`)
  await shot(page, 'columns-step-390.png')
  await nextBtn(page).click().catch(() => {})
  await page.getByRole('button', { name: /NEXT: REVIEW/ }).click().catch(() => {})
  await page.waitForSelector('text=Reconciliation preview', { timeout: 8000 }).catch(() => {})
  ck('no horizontal overflow at 390px on the review', (await overflow(page)) <= 0, `${await overflow(page)}px`)
  await shot(page, 'review-390.png')
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
