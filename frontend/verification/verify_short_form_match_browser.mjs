/**
 * A short-form name match on the scorecard import's review, driven in a real
 * browser: "Salter, Steve" arrives pre-selected as the club's "Salter, Steven",
 * says why, and "Create all as new players" leaves it alone.
 *
 * Run:
 *   npx vite preview --port 5199 &
 *   node verification/verify_short_form_match_browser.mjs
 *
 * Every read is guarded, so a control run against a build without the feature
 * reports each check rather than dying on the first absent locator.
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
  { game_key: 'G1', played_at: '2004-11-06', season_name: '2004/05', grade_name: 'A grade',
    player_name: 'Salter, Steve', batting_runs: '40', did_not_bat: 'false' },
  { game_key: 'G1', played_at: '2004-11-06', season_name: '2004/05', grade_name: 'A grade',
    player_name: 'Guest, Rob', batting_runs: '19', did_not_bat: 'false' },
]
const NOTE = 'Suggested: Salter, Steven. The first names are a short and a full form of one name ' +
  "(played 2004 here, 2004-2006 on the club's record). Change it if these are two different people."

// What the server hands back: Salter suggested, Rob with nothing chosen.
const reviewFor = (body) => {
  const ov = body.player_overrides || {}
  const st = (v, fallbackId, fallback) => v === '__new__' ? ['new', null] : v === '__skip__' ? ['skip', null]
    : v ? ['manual', v] : [fallback, fallbackId]
  const [salSt, salId] = st(ov['Salter, Steve'], 'p-salter', 'suggested')
  const [robSt, robId] = st(ov['Guest, Rob'], null, 'none')
  const unresolved = [salId || ['new', 'skip'].includes(salSt), robId || ['new', 'skip'].includes(robSt)]
    .filter(x => !x).length
  return {
    games: 1, rows: 2,
    seasons: [{ raw_label: '2004/05', season_id: 's1', status: 'exact', candidates: [] }],
    grades: [{ raw_label: 'A grade', grade_name: 'A grade', status: 'exact', used_in_seasons: ['2004/05'], candidates: [] }],
    players: [
      { raw_name: 'Salter, Steve', player_id: salId, matched_name: 'Salter, Steven', status: salSt,
        note: NOTE, candidates: [{ player_id: 'p-salter', name: 'Salter, Steven', confidence: 0.96 }],
        sheet: { games: 1, runs: 40, wickets: 0, first_year: 2004, last_year: 2004 } },
      { raw_name: 'Guest, Rob', player_id: robId, status: robSt, candidates: [],
        sheet: { games: 1, runs: 19, wickets: 0, first_year: 2004, last_year: 2004 } },
    ],
    grade_options: ['A grade'], warnings: [], row_errors: [],
    will_create: { seasons: 0, grades: 0, players: [salSt, robSt].filter(s => s === 'new').length },
    totals: { players_matched: salId ? 1 : 0, players_new: 0, players_skipped: 0, players_unresolved: unresolved },
  }
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(width = 1440) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = [], wire = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route(/\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/games\/import\/preview$/.test(path)) {
      return json({ filename: 's.csv', columns: [], unknown_columns: [], row_count: 2, sample_rows: ROWS, rows: ROWS })
    }
    if (/games\/import\/resolve$/.test(path)) {
      const body = JSON.parse(route.request().postData() || '{}')
      wire.push(body)
      return json(reviewFor(body))
    }
    if (path.startsWith('/auth/me')) {
      return json({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'club_admin',
                    club_id: 'c1', club_slug: 'test-cc', entitlements: { modules: ['stats'], status: 'active' } })
    }
    return json([])
  })
  await page.goto(`${BASE}/admin/manual-entries#import`, { waitUntil: 'domcontentloaded' })
  const tab = page.getByRole('button', { name: 'Import Scorecards', exact: true })
  await tab.waitFor({ timeout: 20000 }).catch(() => {})
  if (await tab.count()) await tab.click()
  const input = page.locator('input[type=file]').first()
  if (await input.count()) {
    await input.setInputFiles({ name: 's.csv', mimeType: 'text/csv', buffer: Buffer.from('game_key\nG1\n') })
  }
  await page.waitForTimeout(900)
  return { page, ctx, errors, wire }
}

const rowOf = (page, name) => page.locator('div.flex-wrap', { has: page.locator(`span:text-is("${name}")`) }).first()
const safe = async (fn, fallback) => { try { return await fn() } catch { return fallback } }

{
  const { page, ctx, errors, wire } = await open()
  const sal = rowOf(page, 'Salter, Steve')
  const salText = await safe(() => sal.innerText(), '')
  ck('the suggested row says what it is, as a word', /SUGGESTED, CHECK THIS/.test(salText), salText.slice(0, 120))
  ck('and why, with both careers', /short and a full form/.test(salText) && /2004-2006/.test(salText))
  const salSelect = sal.locator('select')
  ck('the club player is pre-selected',
     (await safe(() => salSelect.inputValue(), '')) === 'p-salter')

  const bulk = page.getByRole('button', { name: /Create all \d+ as new players/ })
  const bulkLabel = await safe(() => bulk.innerText(), '')
  ck('Create all counts only the name with nothing chosen', /Create all 1 as new/.test(bulkLabel), bulkLabel)
  if (await bulk.count()) await bulk.click()
  await page.waitForTimeout(500)
  const last = wire[wire.length - 1] || {}
  const ov = last.player_overrides || {}
  ck('pressing it creates the unanswered name', ov['Guest, Rob'] === '__new__', JSON.stringify(ov))
  ck('and leaves the suggested match alone', !('Salter, Steve' in ov), JSON.stringify(ov))
  ck('which still reads as the club player afterwards',
     (await safe(() => rowOf(page, 'Salter, Steve').locator('select').inputValue(), '')) === 'p-salter')

  // The person can still say no.
  await safe(() => rowOf(page, 'Salter, Steve').locator('select').selectOption('__new__'), null)
  await page.waitForTimeout(500)
  const after = (wire[wire.length - 1] || {}).player_overrides || {}
  ck('changing it to create sends that answer', after['Salter, Steve'] === '__new__', JSON.stringify(after))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  const { page, ctx } = await open(390)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  const noteVisible = await safe(() => rowOf(page, 'Salter, Steve').getByText(/short and a full form/).isVisible(), false)
  ck('the note is readable at 390px', noteVisible)
  ck('and nothing pushes the page sideways', over <= 0, `${over}px`)
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
