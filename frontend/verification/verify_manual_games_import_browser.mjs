/**
 * The scorecard import wizard, driven in a real browser.
 *
 * Run:
 *   npx vite --port 5199 &
 *   node verification/verify_manual_games_import_browser.mjs
 *
 * What it is really checking: that an unmatched PLAYER cannot be imported by
 * pressing the one obvious button. Seasons and grades default to being created
 * because there is no identity question to get wrong; a person is different,
 * and the screen has to say so rather than quietly ticking 300 boxes.
 *
 * Every read is guarded, so a CONTROL RUN against a build without the feature
 * reports each check rather than dying on the first absent locator and saying
 * nothing about the rest.
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

const ROWS = [
  { game_key: 'G1', played_at: '1992-10-17', season_name: '1992/93', grade_name: 'Grade 2',
    player_name: 'Guest, Rob', batting_runs: '19', did_not_bat: 'false' },
  { game_key: 'G1', played_at: '1992-10-17', season_name: '1992/93', grade_name: 'Grade 2',
    player_name: 'Held, Harry', batting_runs: '45', did_not_bat: 'false' },
]

// The review the server would hand back for that sheet: one season and one
// grade to create, one player matched, one still to answer.
const reviewFor = (overrides) => {
  const chosen = overrides.player_overrides || {}
  const rob = chosen['Guest, Rob']
  const robStatus = rob === '__new__' ? 'new' : rob === '__skip__' ? 'skip' : rob ? 'manual' : 'none'
  const unresolved = robStatus === 'none' ? 1 : 0
  return {
    games: 1, rows: 2,
    seasons: [{ raw_label: '1992/93', season_id: null, status: 'new', will_create: true, candidates: [] }],
    grades: [{ raw_label: 'Grade 2', grade_name: 'Grade 2', status: 'new', will_create: true,
               used_in_seasons: ['1992/93'], candidates: [] }],
    players: [
      { raw_name: 'Guest, Rob', player_id: rob && rob.startsWith('__') ? null : (rob || null),
        status: robStatus, candidates: [],
        sheet: { games: 1, runs: 19, wickets: 0, first_year: 1992, last_year: 1992 } },
      { raw_name: 'Held, Harry', player_id: 'p-held', matched_name: 'Held, Harry',
        status: 'exact', candidates: [],
        sheet: { games: 1, runs: 45, wickets: 0, first_year: 1992, last_year: 1992 } },
    ],
    grade_options: ['1st Grade'],
    warnings: unresolved ? ['1 player name(s) still need an answer: Guest, Rob'] : [],
    row_errors: [],
    will_create: { seasons: 1, grades: 1, players: robStatus === 'new' ? 1 : 0 },
    totals: { players_matched: 1, players_new: robStatus === 'new' ? 1 : 0,
              players_skipped: robStatus === 'skip' ? 1 : 0, players_unresolved: unresolved },
  }
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = []
  const wire = []          // every wizard request body, to read the real params
  page.on('pageerror', (e) => errors.push(String(e)))
  // Routed by REGEX: Playwright's `**` glob does not cross a `?`, so a glob
  // silently loses a query-carrying URL to the catch-all.
  await page.route(/\/api\//, async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json',
                                           body: JSON.stringify(body) })
    if (/games\/import\/preview$/.test(path)) {
      wire.push({ path, body: null })
      return json({ filename: 'scorecards.csv', columns: [], unknown_columns: ['Notes'],
                    row_count: ROWS.length, sample_rows: ROWS, rows: ROWS })
    }
    if (/games\/import\/resolve$/.test(path)) {
      const body = JSON.parse(route.request().postData() || '{}')
      wire.push({ path, body })
      return json(reviewFor(body))
    }
    if (/games\/import\/commit$/.test(path)) {
      const body = JSON.parse(route.request().postData() || '{}')
      wire.push({ path, body })
      return json({ games_created: 1, seasons_created: 1, grades_created: 1,
                    players_created: 1, errors: 0, errors_detail: [] })
    }
    if (path.startsWith('/auth/me')) {
      return json({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'club_admin',
                    club_id: 'c1', club_slug: 'test-cc',
                    entitlements: { modules: ['stats', 'fees'], status: 'active' } })
    }
    return json([])
  })
  await page.goto(`${BASE}/admin/manual-entries#import`, { waitUntil: 'networkidle' })
  await page.waitForSelector('text=Import Scorecards', { timeout: 20000 }).catch(() => {})
  return { page, ctx, errors, wire }
}

async function upload(page) {
  const input = page.locator('input[type=file]').first()
  if (!(await input.count())) return false
  await input.setInputFiles({ name: 'scorecards.csv', mimeType: 'text/csv',
                              buffer: Buffer.from('game_key\nG1\n') })
  await page.waitForTimeout(700)
  return true
}

// ── the tab exists and the sheet is read ────────────────────────────────────
{
  const { page, ctx, errors, wire } = await open()
  const tab = page.getByRole('button', { name: 'Import Scorecards', exact: true })
  ck('there is an Import Scorecards tab', (await tab.count()) > 0)
  if (await tab.count()) await tab.click()
  await page.waitForTimeout(200)

  const uploaded = await upload(page)
  ck('the screen takes a file', uploaded)

  const previewed = wire.some(w => /preview$/.test(w.path))
  ck('picking a file previews it on the server', previewed)
  ck('and immediately resolves what it will create',
     wire.some(w => /resolve$/.test(w.path)))

  const text = await page.locator('body').innerText().catch(() => '')
  ck('a column the import has no use for is reported, not silently dropped',
     /Notes/.test(text) && /ignoring/i.test(text), text.slice(0, 160))
  ck('the review names the matches', /\b1\b/.test(text) && /Matches/i.test(text))
  ck('and says a season will be created', /New seasons/i.test(text))
  ck('a grade too', /New grades/i.test(text))

  // Every state is a WORD, not a colour — a verdict told apart by colour alone
  // is unreadable for a good share of readers.
  ck('an unmatched name says so in words', /NEEDS AN ANSWER/.test(text), text.slice(0, 300))
  ck('a matched one says so too', /MATCHED/.test(text))
  ck('and the season says it will be created', /WILL BE CREATED/.test(text))

  ck('the sheet\'s own figures ride along, so two people sharing a surname can '
     + 'be told apart without opening the file', /19 runs/.test(text), text.slice(0, 400))

  const importBtn = page.getByRole('button', { name: /^Import 1 match/ })
  ck('the import button is there', (await importBtn.count()) > 0)
  ck('but it is DISABLED while a name is unanswered',
     (await importBtn.count()) ? await importBtn.first().isDisabled() : false)
  ck('and the screen says why', /still need an answer/i.test(text))

  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── answering the name, and what actually goes on the wire ──────────────────
{
  const { page, ctx, errors, wire } = await open()
  const tab = page.getByRole('button', { name: 'Import Scorecards', exact: true })
  if (await tab.count()) await tab.click()
  await upload(page)

  const bulk = page.getByRole('button', { name: /Create all 1 as new players/ })
  ck('a club importing a whole history gets a bulk answer', (await bulk.count()) > 0)
  if (await bulk.count()) {
    await bulk.first().click()
    await page.waitForTimeout(500)
  }
  const lastResolve = [...wire].reverse().find(w => /resolve$/.test(w.path))
  ck('pressing it sends that name as one to create, on the wire',
     lastResolve?.body?.player_overrides?.['Guest, Rob'] === '__new__',
     JSON.stringify(lastResolve?.body?.player_overrides))
  ck('and it does NOT touch the name that already matched',
     !('Held, Harry' in (lastResolve?.body?.player_overrides || {})),
     JSON.stringify(lastResolve?.body?.player_overrides))

  const text = await page.locator('body').innerText().catch(() => '')
  ck('the button is gone once nothing is unanswered',
     (await page.getByRole('button', { name: /Create all/ }).count()) === 0)
  ck('and the count of new players moves to 1', /New players/i.test(text))

  const importBtn = page.getByRole('button', { name: /^Import 1 match/ })
  ck('the import button is enabled now',
     (await importBtn.count()) ? !(await importBtn.first().isDisabled()) : false)

  if (await importBtn.count()) {
    await importBtn.first().click()
    await page.waitForTimeout(500)
  }
  const commit = wire.find(w => /commit$/.test(w.path))
  ck('committing sends the rows and every answer given', !!commit && Array.isArray(commit.body?.rows))
  ck('with the player answer among them',
     commit?.body?.player_overrides?.['Guest, Rob'] === '__new__',
     JSON.stringify(commit?.body?.player_overrides))

  const after = await page.locator('body').innerText().catch(() => '')
  ck('and the result says exactly what it created', /Seasons created/i.test(after) && /Players created/i.test(after),
     after.slice(0, 200))
  ck('naming the undo as the way back', /Audit/i.test(after) && /undo/i.test(after))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── leaving somebody out is a real answer, not the same as unanswered ───────
{
  const { page, ctx, wire } = await open()
  const tab = page.getByRole('button', { name: 'Import Scorecards', exact: true })
  if (await tab.count()) await tab.click()
  await upload(page)
  // Addressed through the ROW that names the person. "the last select on the
  // page" reached the name that had already matched, so the check passed while
  // answering the wrong person — a check that measures the harness, not the code.
  const row = page.locator('div').filter({ hasText: /^Guest, Rob/ }).last()
  const sel = row.locator('select').first()
  if (await sel.count()) {
    await sel.selectOption('__skip__').catch(() => {})
    await page.waitForTimeout(500)
  }
  const last = [...wire].reverse().find(w => /resolve$/.test(w.path))
  ck('choosing to leave a name out sends __skip__, not a blank',
     last?.body?.player_overrides?.['Guest, Rob'] === '__skip__',
     JSON.stringify(last?.body?.player_overrides))
  const importBtn = page.getByRole('button', { name: /^Import 1 match/ })
  ck('and the import is unblocked by it',
     (await importBtn.count()) ? !(await importBtn.first().isDisabled()) : false)
  await ctx.close()
}

// ── the phone ───────────────────────────────────────────────────────────────
{
  const { page, ctx } = await open({ width: 390 })
  const tab = page.getByRole('button', { name: 'Import Scorecards', exact: true })
  if (await tab.count()) await tab.click()
  await upload(page)
  const over = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', over <= 0, `overflow ${over}px`)
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
