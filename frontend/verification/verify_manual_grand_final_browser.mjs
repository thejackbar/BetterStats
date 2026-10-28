/**
 * Marking a hand-entered match as the grand final, driven in a real browser.
 *
 * Run:
 *   npx vite --port 5199 &
 *   node verification/verify_manual_grand_final_browser.mjs [baseUrl]
 *
 * Reported by Shoalwater Bay: their 1999/00 and 2004/05 premiership scorecards are hand-entered games, which
 * the automatic premierships could not see. A match can now be marked as the grand final (a) in the CSV import,
 * (b) with a tick on the Manual Games form, and (c) later, from the quick "Details" editor on a game already
 * stored, which sends only what changed and never the scorecard.
 *
 * The API is stubbed at the network layer and every request body is read off the wire. Every read is guarded,
 * so a CONTROL RUN against a build without the feature reports each check instead of dying on the first absent
 * locator. 390px width is checked for overflow, and the screens are screenshotted to $SHOTS.
 */
import { chromium } from 'playwright'
import { existsSync, mkdirSync } from 'node:fs'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const SHOTS = process.env.SHOTS || '/tmp/gf-shots'
mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const SEASON = { id: 's-2000', name: '1999/00', year: 1999 }
const SEASON2 = { id: 's-2005', name: 'Summer 2004/05', year: 2004 }
const GRADE = { id: 'g-c', name: 'C grade', season_id: SEASON.id }

// What the server holds. G_PLAIN is an imported scorebook match; G_FINAL is already marked.
const GAMES = {
  'g-plain': { id: 'g-plain', season_id: SEASON.id, season_name: SEASON.name, grade_id: GRADE.id, played_at: '2000-03-25',
    opposition: 'Rival', home_team: null, away_team: null, venue: null, result: 'WIN', winning_team: 'Shoalwater Bay',
    is_final: false, is_grand_final: false, match_format: null, notes: null, batting_count: 4, is_photo_upload: false },
  'g-final': { id: 'g-final', season_id: SEASON2.id, season_name: SEASON2.name, grade_id: null, played_at: '2005-03-19',
    opposition: 'Other', venue: 'Oval', result: 'Lost by 5 runs', winning_team: 'Other',
    is_final: true, is_grand_final: true, match_format: null, notes: null, batting_count: 3, is_photo_upload: false },
  'g-semi': { id: 'g-semi', season_id: SEASON2.id, season_name: SEASON2.name, grade_id: null, played_at: '2005-03-12',
    opposition: 'Third', result: 'WIN', winning_team: 'Shoalwater Bay',
    is_final: true, is_grand_final: false, match_format: null, notes: null, batting_count: 3, is_photo_upload: false },
  'g-photo': { id: 'g-photo', season_id: SEASON.id, season_name: SEASON.name, grade_id: GRADE.id, played_at: '2000-03-18',
    opposition: 'Snap', result: 'WIN', winning_team: 'Shoalwater Bay',
    is_final: false, is_grand_final: false, match_format: null, notes: null, batting_count: 1, is_photo_upload: true },
}
const FULL = id => ({
  ...GAMES[id],
  batting_innings: [{ id: 1, player_id: 'p1', player_name: 'Alpha, Anne', innings_number: 1, runs: 12, fours: 1, sixes: 0 }],
  bowling_spells: [], fielding_stats: [], innings: [],
  extracted_payload: id === 'g-photo' ? { match: { home_team: 'SBCC', away_team: 'Snap' }, innings: [] } : null,
})

const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1440, hash = 'game', path = '/admin/manual-entries', grandFinalStatus } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1600 } })
  const page = await ctx.newPage()
  // Short, so a CONTROL run against a build without the feature reports each absent control in seconds
  // instead of waiting out Playwright's 30 s per missing locator.
  page.setDefaultTimeout(4000)
  page.setDefaultNavigationTimeout(30000)
  const errors = []
  const wire = []
  page.on('pageerror', e => errors.push(String(e)))
  await page.route(/\/api\//, async route => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    const method = req.method()
    // The preview is a multipart upload, not JSON: only a JSON body is read.
    let body = null
    try { body = req.postData() ? JSON.parse(req.postData()) : null } catch { body = null }
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p.startsWith('/auth/me')) {
      return json({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'club_admin', club_id: 'c1',
                    club_slug: 'shoalwater', entitlements: { modules: ['stats', 'fees'], status: 'active' } })
    }
    if (/\/manual-entries\/games\/import\/preview$/.test(p)) {
      wire.push({ method, p, body })
      return json({ filename: 'history.csv', columns: [], unknown_columns: [], row_count: 1, token: 't1',
                    sample_rows: [{ game_key: 'C1', is_grand_final: 'yes' }], rows: [{ game_key: 'C1', is_grand_final: 'yes' }] })
    }
    if (/\/manual-entries\/games\/import\/resolve$/.test(p)) {
      wire.push({ method, p, body })
      return json({
        games: 1, rows: 1, seasons: [], grades: [], players: [], grade_options: [], row_errors: [], bad_cells: [],
        warnings: ['1 match(es) marked as a grand final do not say who won (C1 (2000-03-25)). No premiership is written for them until the winning team or the result line names your side. They import either way.'],
        grand_finals: 1, grand_finals_undecided: [{ game_key: 'C1', reason: 'no winner recorded', played_at: '2000-03-25' }],
        will_create: { seasons: 0, grades: 0, players: 0 },
        totals: { players_matched: 0, players_new: 0, players_skipped: 0, players_unresolved: 0 },
        duplicates: { total: 0, manual: 0, synced: 0, matched_on_scores: 0 },
      })
    }
    if (/\/manual-entries\/games\/import\/commit$/.test(p)) {
      wire.push({ method, p, body })
      return json({ games_created: 1, seasons_created: 0, grades_created: 0, players_created: 0, errors: 0,
                    errors_detail: [], warnings: [], grand_finals: 1 })
    }
    let m = p.match(/\/manual-entries\/games\/([\w-]+)\/details$/)
    if (m && method === 'PATCH') {
      wire.push({ method, p, body, id: m[1] })
      return json({ ...GAMES[m[1]], ...body, changed: Object.keys(body),
                    grand_final: grandFinalStatus || { state: 'won', players: 11, reason: '' } })
    }
    m = p.match(/\/manual-entries\/games\/([\w-]+)$/)
    if (m && method === 'GET' && GAMES[m[1]]) return json(FULL(m[1]))
    if (m && method === 'PATCH') {
      wire.push({ method, p, body, id: m[1] })
      return json({ ...GAMES[m[1]], ...body, grand_final: grandFinalStatus || { state: 'won', players: 11, reason: '' } })
    }
    if (/\/manual-entries\/games$/.test(p) && method === 'GET') return json(Object.values(GAMES))
    if (/\/manual-entries\/games\/check$/.test(p)) return json({ warnings: [] })
    if (/admin\/seasons|manual-entries\/seasons/.test(p) && method === 'GET') return json([SEASON, SEASON2])
    if (/manual-entries\/grades$/.test(p)) return json([GRADE])
    if (/known-values/.test(p)) return json({ oppositions: ['Rival'], venues: ['Oval'] })
    if (/admin\/players/.test(p)) return json([{ id: 'p1', display_name: 'Alpha, Anne', is_player: true }])
    return json([])
  })
  await page.goto(`${BASE}${path}#${hash}`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('text=Manual stat entries', { timeout: 20000 }).catch(() => {})
  await page.waitForTimeout(500)
  return { page, ctx, errors, wire }
}

const rowOf = (page, text) => page.locator('tr', { hasText: text }).first()
const confirmModal = async page => {
  const btn = page.getByRole('button', { name: /^(Save|Update)$/ })
  if (await btn.count()) { await btn.first().click(); await page.waitForTimeout(500); return true }
  return false
}

// ── the list says which matches are finals ──────────────────────────────────
{
  const { page, ctx, errors } = await open()
  const kinds = await page.locator('[data-testid=match-kind]').allInnerTexts().catch(() => [])
  ck('the list has a Match column that says Grand Final', kinds.includes('Grand Final'), JSON.stringify(kinds))
  ck('and says Final for a semi, and nothing for an ordinary match',
     kinds.includes('Final') && kinds.includes(''), JSON.stringify(kinds))
  ck('every row has a Details button', (await page.locator('[data-testid=details-btn]').count()) === Object.keys(GAMES).length)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await page.screenshot({ path: `${SHOTS}/list.png`, fullPage: false })
  await ctx.close()
}

// ── (c) set it later, from the quick Details editor: only what changed goes on the wire ──
{
  const { page, ctx, errors, wire } = await open()
  await rowOf(page, '2000-03-25').getByTestId('details-btn').click().catch(() => {})
  await page.waitForSelector('[data-testid=match-details]', { timeout: 5000 }).catch(() => {})
  const panel = page.getByTestId('match-details')
  ck('Details opens the match\'s own fields', (await panel.count()) > 0)
  const text = await panel.innerText().catch(() => '')
  ck('and says the scorecard is not touched', /scorecard is not touched/i.test(text), text.slice(0, 200))
  ck('Grand Final starts unticked', !(await page.getByTestId('d-is_grand_final').isChecked().catch(() => true)))

  await page.getByTestId('d-is_grand_final').check().catch(() => {})
  ck('ticking Grand Final ticks Final too', await page.getByTestId('d-is_final').isChecked().catch(() => false))
  ck('and says what it does for the premiership', (await page.getByTestId('gf-help').count()) > 0
     && /premiership automatically/i.test(await page.getByTestId('gf-help').innerText().catch(() => '')))
  await page.getByTestId('d-is_final').uncheck().catch(() => {})
  ck('unticking Final unticks Grand Final', !(await page.getByTestId('d-is_grand_final').isChecked().catch(() => true)))
  await page.getByTestId('d-is_grand_final').check().catch(() => {})

  await page.screenshot({ path: `${SHOTS}/details.png`, fullPage: false })
  await page.getByTestId('details-save').click().catch(() => {})
  ck('saving asks first', await confirmModal(page))
  await page.waitForTimeout(400)
  const sent = wire.filter(w => /details$/.test(w.p))
  ck('exactly one request, to the details route', sent.length === 1, JSON.stringify(sent.map(s => s.p)))
  ck('it carries only the two fields that changed, nothing else',
     JSON.stringify(sent[0]?.body) === JSON.stringify({ is_final: true, is_grand_final: true }), JSON.stringify(sent[0]?.body))
  const notice = await page.getByTestId('manual-notice').innerText().catch(() => '')
  ck('the person is told it worked, and for how many', /11 players on the card have the premiership/.test(notice), notice)
  ck('and the editor closes', (await page.getByTestId('match-details').count()) === 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── only a changed field is sent; nothing changed sends nothing ─────────────
{
  const { page, ctx, wire } = await open()
  await rowOf(page, '2000-03-25').getByTestId('details-btn').click().catch(() => {})
  await page.waitForSelector('[data-testid=match-details]', { timeout: 5000 }).catch(() => {})
  await page.getByTestId('details-save').click().catch(() => {})
  await page.waitForTimeout(300)
  const text = await page.getByTestId('match-details').innerText().catch(() => '')
  ck('saving with nothing changed says so', /Nothing has changed/.test(text), text.slice(0, 120))
  ck('and sends nothing', wire.filter(w => /details$/.test(w.p)).length === 0)
  await page.getByTestId('d-match_format').fill('40-over').catch(() => {})
  await page.getByTestId('details-save').click().catch(() => {})
  await confirmModal(page)
  await page.waitForTimeout(300)
  const sent = wire.filter(w => /details$/.test(w.p))
  ck('changing only the format sends only the format',
     JSON.stringify(sent[0]?.body) === JSON.stringify({ match_format: '40-over' }), JSON.stringify(sent[0]?.body))
  await ctx.close()
}

// ── an unclear result: the person is told why nothing was written ───────────
{
  const { page, ctx } = await open({ grandFinalStatus: { state: 'undecided', players: 0, reason: 'no winner recorded' } })
  await rowOf(page, '2000-03-25').getByTestId('details-btn').click().catch(() => {})
  await page.waitForSelector('[data-testid=match-details]', { timeout: 5000 }).catch(() => {})
  await page.getByTestId('d-is_grand_final').check().catch(() => {})
  await page.getByTestId('details-save').click().catch(() => {})
  await confirmModal(page)
  await page.waitForTimeout(400)
  const notice = await page.getByTestId('manual-notice').innerText().catch(() => '')
  ck('a marked match with no clear winner is told so, with the reason and what to do',
     /no premiership is written yet: no winner recorded/.test(notice) && /winning team or the result line/.test(notice), notice)
  await ctx.close()
}

// ── (b) the tick on the full form, through Edit ─────────────────────────────
{
  const { page, ctx, wire } = await open()
  await rowOf(page, '2000-03-25').getByRole('button', { name: 'Edit', exact: true }).click().catch(() => {})
  await page.waitForSelector('text=Edit manual game', { timeout: 5000 }).catch(() => {})
  const tick = page.getByTestId('gf-tick')
  ck('the full form has a Grand Final tick beside Final', (await tick.count()) > 0)
  await tick.check().catch(() => {})
  ck('ticking it ticks Final', await page.getByLabel('Final', { exact: true }).isChecked().catch(() => false))
  await page.screenshot({ path: `${SHOTS}/form.png`, fullPage: false })
  await page.getByRole('button', { name: 'Update manual game' }).click().catch(() => {})
  await confirmModal(page)
  await page.waitForTimeout(500)
  const sent = wire.filter(w => /\/games\/g-plain$/.test(w.p))
  ck('the full edit sends the flag, true, with the final', sent[0]?.body?.is_grand_final === true && sent[0]?.body?.is_final === true,
     JSON.stringify(sent[0]?.body && { gf: sent[0].body.is_grand_final, fin: sent[0].body.is_final }))
  await ctx.close()
}
{
  // Editing a game that is already marked loads the tick ticked, and re-saving does not clear it.
  const { page, ctx, wire } = await open()
  await rowOf(page, '2005-03-19').getByRole('button', { name: 'Edit', exact: true }).click().catch(() => {})
  await page.waitForSelector('text=Edit manual game', { timeout: 5000 }).catch(() => {})
  ck('a game already marked loads with Grand Final ticked', await page.getByTestId('gf-tick').isChecked().catch(() => false))
  await page.getByRole('button', { name: 'Update manual game' }).click().catch(() => {})
  await confirmModal(page)
  await page.waitForTimeout(500)
  const sent = wire.filter(w => /\/games\/g-final$/.test(w.p))
  ck('and an untouched re-save keeps it', sent[0]?.body?.is_grand_final === true, JSON.stringify(sent[0]?.body?.is_grand_final))
  await ctx.close()
}

// ── (a) the CSV import: the column is explained, counted, and warned about ──
{
  const { page, ctx, errors, wire } = await open({ hash: 'import' })
  const help = await page.getByTestId('gf-column-help').innerText().catch(() => '')
  ck('the import page explains the is_grand_final column', /is_grand_final/.test(help) && /premiership automatically/i.test(help), help)
  await page.locator('input[type=file]').first().setInputFiles({
    name: 'history.csv', mimeType: 'text/csv', buffer: Buffer.from('game_key,is_grand_final\nC1,yes\n') }).catch(() => {})
  await page.waitForTimeout(900)
  const review = await page.getByTestId('gf-review').innerText().catch(() => '')
  ck('the review counts the matches marked as the grand final', /1 match in this sheet is marked as the grand final/.test(review), review)
  const body = await page.locator('body').innerText()
  ck('and warns about the one that does not say who won, while still importing',
     /do not say who won/.test(body) && /They import either way/.test(body))
  await page.screenshot({ path: `${SHOTS}/import-review.png`, fullPage: false })
  const importBtn = page.getByRole('button', { name: /^Import 1 match/ })
  ck('the import button is still enabled (a warning never blocks)', (await importBtn.count()) > 0 && !(await importBtn.first().isDisabled()))
  await importBtn.first().click().catch(() => {})
  await page.waitForTimeout(700)
  const done = await page.getByTestId('gf-result').innerText().catch(() => '')
  ck('after importing it says how many grand finals went in', /1 match is marked as the grand final/.test(done), done)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── Upload Historical Scorecard: jump back into a photo upload and tick it ──
{
  const { page, ctx, wire } = await open({ path: '/admin/upload-scorecard', hash: '' })
  await page.waitForSelector('text=Upload Historical Scorecard', { timeout: 15000 }).catch(() => {})
  const edit = page.getByRole('button', { name: /Edit/ }).first()
  if (await edit.count()) await edit.click().catch(() => {})
  await page.waitForTimeout(800)
  const tick = page.getByTestId('gf-tick')
  ck('the upload screen has a Grand Final tick when a card is open for review', (await tick.count()) > 0,
     (await page.locator('body').innerText().catch(() => '')).slice(0, 160))
  if (await tick.count()) {
    await tick.check()
    ck('ticking it ticks Final here too', await page.getByLabel('Final', { exact: true }).isChecked().catch(() => false))
    await page.screenshot({ path: `${SHOTS}/upload.png`, fullPage: false })
  }
  await ctx.close()
}

// ── 390px: no horizontal overflow on the screens that changed ───────────────
{
  const { page, ctx } = await open({ width: 390 })
  await rowOf(page, '2000-03-25').getByTestId('details-btn').click().catch(() => {})
  await page.waitForSelector('[data-testid=match-details]', { timeout: 5000 }).catch(() => {})
  await page.getByTestId('d-is_grand_final').check().catch(() => {})
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ck('Manual Games with the details editor open does not overflow at 390px', overflow <= 1, `overflow ${overflow}px`)
  await page.screenshot({ path: `${SHOTS}/details-390.png`, fullPage: false })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
