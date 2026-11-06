/**
 * Captain and wicketkeeper on a hand-entered or imported match, driven in a real browser.
 *
 * Run:
 *   npx vite --port 5199 &
 *   node verification/verify_manual_game_roles_browser.mjs [baseUrl]
 *
 * Reported by Shoalwater Bay: the captain and wicketkeeper they entered in CSFW are missing. An admin can now set
 * or change both (a) from the quick Details editor, which sends only what changed and never the scorecard, and
 * (b) in Match Info on the full form, which sends them only when they were changed. The CSV wizard says how many
 * matches named each.
 *
 * The API is stubbed at the network layer and every request body is read off the wire. Every read is guarded, so a
 * CONTROL RUN against a build without the feature reports each check instead of dying on the first absent
 * locator. 390px width is checked for overflow, and the screens are screenshotted to $SHOTS.
 */
import { chromium } from 'playwright'
import { existsSync, mkdirSync } from 'node:fs'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const SHOTS = process.env.SHOTS || '/tmp/roles-shots'
mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const SEASON = { id: 's-2000', name: '1999/00', year: 1999 }
const GRADE = { id: 'g-c', name: 'C grade', season_id: SEASON.id }
const PLAYERS = [
  { id: 'p1', display_name: 'Alpha, Anne', is_player: true },
  { id: 'p2', display_name: 'Bravo, Beth', is_player: true },
  { id: 'p3', display_name: 'Delta, Dana', is_player: true },   // not on any card
  { id: 'p4', display_name: 'Echo, Eve', is_player: true },
]

// G_PLAIN has no roles; G_ROLES has Bravo as captain and Alpha keeping. The card holds p1, p2 and p4.
const GAMES = {
  'g-plain': { id: 'g-plain', season_id: SEASON.id, season_name: SEASON.name, grade_id: GRADE.id, played_at: '2000-03-25',
    opposition: 'Rival', result: 'WIN', winning_team: 'Shoalwater Bay', is_final: false, is_grand_final: false,
    batting_count: 2, is_photo_upload: false },
  'g-roles': { id: 'g-roles', season_id: SEASON.id, season_name: SEASON.name, grade_id: GRADE.id, played_at: '2000-03-18',
    opposition: 'Other', result: 'WIN', winning_team: 'Shoalwater Bay', is_final: false, is_grand_final: false,
    batting_count: 2, is_photo_upload: false },
}
const ROLES = {
  'g-plain': { captain_player_ids: [], wicket_keeper_player_ids: [] },
  'g-roles': { captain_player_ids: ['p2'], wicket_keeper_player_ids: ['p1'] },
}
const FULL = id => ({
  ...GAMES[id],
  batting_innings: [
    { id: 1, player_id: 'p1', player_name: 'Alpha, Anne', innings_number: 1, runs: 12, fours: 1, sixes: 0 },
    { id: 2, player_id: 'p2', player_name: 'Bravo, Beth', innings_number: 1, runs: 3, fours: 0, sixes: 0 },
  ],
  bowling_spells: [{ id: 3, player_id: 'p4', player_name: 'Echo, Eve', innings_number: 1, overs: 4, runs: 20, wickets: 1 }],
  fielding_stats: [], innings: [], extracted_payload: null,
  roles: ROLES[id],
})

const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1440, hash = 'game' } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1600 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(4000)
  page.setDefaultNavigationTimeout(30000)
  const errors = []
  const wire = []
  page.on('pageerror', e => errors.push(String(e)))
  await page.route(/\/api\//, async route => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    const method = req.method()
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
                    sample_rows: [{ game_key: 'C1' }], rows: [{ game_key: 'C1' }] })
    }
    if (/\/manual-entries\/games\/import\/resolve$/.test(p)) {
      return json({
        games: 1, rows: 1, seasons: [], grades: [], players: [], grade_options: [], row_errors: [], bad_cells: [],
        warnings: [], grand_finals: 0, will_create: { seasons: 0, grades: 0, players: 0 },
        totals: { players_matched: 0, players_new: 0, players_skipped: 0, players_unresolved: 0 },
        duplicates: { total: 0, manual: 0, synced: 0, matched_on_scores: 0 },
      })
    }
    if (/\/manual-entries\/games\/import\/commit$/.test(p)) {
      return json({ games_created: 3, seasons_created: 0, grades_created: 0, players_created: 0, errors: 0,
                    errors_detail: [], warnings: [], grand_finals: 0, captains_named: 3, keepers_named: 2 })
    }
    let m = p.match(/\/manual-entries\/games\/([\w-]+)\/details$/)
    if (m && method === 'PATCH') {
      wire.push({ method, p, body, id: m[1] })
      return json({ ...GAMES[m[1]], changed: Object.keys(body), roles: ROLES[m[1]] })
    }
    m = p.match(/\/manual-entries\/games\/([\w-]+)$/)
    if (m && method === 'GET' && GAMES[m[1]]) return json(FULL(m[1]))
    if (m && method === 'PATCH') {
      wire.push({ method, p, body, id: m[1] })
      return json({ ...GAMES[m[1]], ...ROLES[m[1]] })
    }
    if (/\/manual-entries\/games$/.test(p) && method === 'GET') return json(Object.values(GAMES))
    if (/\/manual-entries\/games\/check$/.test(p)) return json({ warnings: [] })
    if (/admin\/seasons|manual-entries\/seasons/.test(p) && method === 'GET') return json([SEASON])
    if (/manual-entries\/grades$/.test(p)) return json([GRADE])
    if (/known-values/.test(p)) return json({ oppositions: ['Rival'], venues: ['Oval'] })
    if (/admin\/players/.test(p)) return json(PLAYERS)
    return json([])
  })
  await page.goto(`${BASE}/admin/manual-entries#${hash}`, { waitUntil: 'domcontentloaded' })
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
const chips = (page, id) => page.getByTestId(`${id}-chip`).allInnerTexts().then(a => a.map(t => t.replace('×', '').trim())).catch(() => [])
const quick = (page, id) => page.getByTestId(`${id}-quick`).allInnerTexts().catch(() => [])
const openDetails = async (page, date) => {
  await rowOf(page, date).getByTestId('details-btn').click().catch(() => {})
  await page.waitForSelector('[data-testid=match-details]', { timeout: 5000 }).catch(() => {})
}
const sentTo = (wire, re) => wire.filter(w => re.test(w.p))

// ── Details editor: shows what the match holds, offers the card's players ───
{
  const { page, ctx, errors } = await open()
  await openDetails(page, '2000-03-18')
  ck('the Details editor has a Captain and a Wicketkeeper field', (await page.getByTestId('match-roles').count()) > 0)
  ck('the captain the match holds is shown', JSON.stringify(await chips(page, 'captain')) === JSON.stringify(['Bravo, Beth']), JSON.stringify(await chips(page, 'captain')))
  ck('and the wicketkeeper', JSON.stringify(await chips(page, 'keeper')) === JSON.stringify(['Alpha, Anne']), JSON.stringify(await chips(page, 'keeper')))
  const qc = await quick(page, 'captain')
  ck('quick picks are the players on the card, not the whole club',
     qc.includes('Alpha, Anne') && qc.includes('Echo, Eve') && !qc.includes('Delta, Dana') && !qc.includes('Bravo, Beth'), JSON.stringify(qc))
  await page.screenshot({ path: `${SHOTS}/details.png`, fullPage: false })
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── Details: set a keeper, only that key goes on the wire ───────────────────
{
  const { page, ctx, wire } = await open()
  await openDetails(page, '2000-03-25')
  ck('a match with no roles says so', (await page.getByTestId('captain-none').count()) > 0 && (await page.getByTestId('keeper-none').count()) > 0)
  await page.getByTestId('keeper-quick').filter({ hasText: 'Alpha, Anne' }).click().catch(() => {})
  await page.getByTestId('details-save').click().catch(() => {})
  ck('saving asks first', await confirmModal(page))
  const sent = sentTo(wire, /details$/)
  ck('one request, to the details route', sent.length === 1, JSON.stringify(sent.map(s => s.p)))
  ck('it carries only the wicketkeeper, as a list of ids',
     JSON.stringify(sent[0]?.body) === JSON.stringify({ wicket_keeper_player_ids: ['p1'] }), JSON.stringify(sent[0]?.body))
  await ctx.close()
}

// ── Details: a player not on the card can be found by name ──────────────────
{
  const { page, ctx, wire } = await open()
  await openDetails(page, '2000-03-25')
  const search = page.getByTestId('match-details').getByPlaceholder('Search for the captain…')
  await search.click().catch(() => {})
  await search.fill('Del').catch(() => {})
  await page.getByRole('button', { name: 'Delta, Dana' }).click().catch(() => {})
  ck('a player off the card can be picked by searching', JSON.stringify(await chips(page, 'captain')) === JSON.stringify(['Delta, Dana']), JSON.stringify(await chips(page, 'captain')))
  await page.getByTestId('details-save').click().catch(() => {})
  await confirmModal(page)
  const sent = sentTo(wire, /details$/)
  ck('and goes as the captain alone', JSON.stringify(sent[0]?.body) === JSON.stringify({ captain_player_ids: ['p3'] }), JSON.stringify(sent[0]?.body))
  await ctx.close()
}

// ── Details: picking a new captain replaces, removing clears, two keepers allowed ─
{
  const { page, ctx, wire } = await open()
  await openDetails(page, '2000-03-18')
  await page.getByTestId('captain-quick').filter({ hasText: 'Echo, Eve' }).click().catch(() => {})
  ck('picking another captain replaces the first (one captain)', JSON.stringify(await chips(page, 'captain')) === JSON.stringify(['Echo, Eve']), JSON.stringify(await chips(page, 'captain')))
  await page.getByRole('button', { name: 'Remove wicketkeeper Alpha, Anne' }).click().catch(() => {})
  await page.getByTestId('keeper-quick').filter({ hasText: 'Bravo, Beth' }).click().catch(() => {})
  await page.getByTestId('keeper-quick').filter({ hasText: 'Echo, Eve' }).click().catch(() => {})
  ck('two keepers can be named (a change mid-match)', JSON.stringify(await chips(page, 'keeper')) === JSON.stringify(['Bravo, Beth', 'Echo, Eve']), JSON.stringify(await chips(page, 'keeper')))
  await page.getByTestId('details-save').click().catch(() => {})
  await confirmModal(page)
  const sent = sentTo(wire, /details$/)
  ck('both lists go, in order', JSON.stringify(sent[0]?.body) === JSON.stringify({ captain_player_ids: ['p4'], wicket_keeper_player_ids: ['p2', 'p4'] }), JSON.stringify(sent[0]?.body))
  await ctx.close()
}
{
  const { page, ctx, wire } = await open()
  await openDetails(page, '2000-03-18')
  await page.getByRole('button', { name: 'Remove captain Bravo, Beth' }).click().catch(() => {})
  ck('removing the captain leaves "Not recorded"', (await page.getByTestId('captain-none').count()) > 0)
  await page.getByTestId('details-save').click().catch(() => {})
  await confirmModal(page)
  const sent = sentTo(wire, /details$/)
  ck('an empty list is sent, which clears only the captain', JSON.stringify(sent[0]?.body) === JSON.stringify({ captain_player_ids: [] }), JSON.stringify(sent[0]?.body))
  await ctx.close()
}
{
  const { page, ctx, wire } = await open()
  await openDetails(page, '2000-03-18')
  await page.getByTestId('details-save').click().catch(() => {})
  await page.waitForTimeout(300)
  ck('saving with nothing changed says so', /Nothing has changed/.test(await page.getByTestId('match-details').innerText().catch(() => '')))
  ck('and sends nothing', sentTo(wire, /details$/).length === 0)
  await ctx.close()
}

// ── Full form: roles ride along only when changed ───────────────────────────
{
  const { page, ctx, wire } = await open()
  await rowOf(page, '2000-03-18').getByRole('button', { name: 'Edit', exact: true }).click().catch(() => {})
  await page.waitForSelector('text=Edit manual game', { timeout: 5000 }).catch(() => {})
  ck('Match Info shows the stored captain and keeper',
     JSON.stringify(await chips(page, 'captain')) === JSON.stringify(['Bravo, Beth']) && JSON.stringify(await chips(page, 'keeper')) === JSON.stringify(['Alpha, Anne']))
  await page.screenshot({ path: `${SHOTS}/form.png`, fullPage: false })
  await page.getByRole('button', { name: 'Update manual game' }).click().catch(() => {})
  await confirmModal(page)
  const sent = sentTo(wire, /\/games\/g-roles$/)
  ck('an untouched re-save sends neither role (an absent key is not a clear)',
     sent.length === 1 && !('captain_player_ids' in (sent[0].body || {})) && !('wicket_keeper_player_ids' in (sent[0].body || {})), JSON.stringify(Object.keys(sent[0]?.body || {})))
  await ctx.close()
}
{
  const { page, ctx, wire } = await open()
  await rowOf(page, '2000-03-18').getByRole('button', { name: 'Edit', exact: true }).click().catch(() => {})
  await page.waitForSelector('text=Edit manual game', { timeout: 5000 }).catch(() => {})
  await page.getByTestId('captain-quick').filter({ hasText: 'Alpha, Anne' }).click().catch(() => {})
  await page.getByRole('button', { name: 'Update manual game' }).click().catch(() => {})
  await confirmModal(page)
  const sent = sentTo(wire, /\/games\/g-roles$/)
  const b = sent[0]?.body || {}
  ck('changing only the captain sends only the captain', JSON.stringify(b.captain_player_ids) === JSON.stringify(['p1']) && !('wicket_keeper_player_ids' in b), JSON.stringify([b.captain_player_ids, b.wicket_keeper_player_ids]))
  await ctx.close()
}

// ── CSV wizard: says how many matches named a captain and a keeper ──────────
{
  const { page, ctx, errors } = await open({ hash: 'import' })
  await page.locator('input[type=file]').first().setInputFiles({
    name: 'history.csv', mimeType: 'text/csv', buffer: Buffer.from('game_key,is_captain\nC1,true\n') }).catch(() => {})
  await page.waitForTimeout(900)
  const importBtn = page.getByRole('button', { name: /^Import 1 match/ })
  await importBtn.first().click().catch(() => {})
  await page.waitForTimeout(700)
  const done = await page.getByTestId('roles-result').innerText().catch(() => '')
  ck('after importing it says how many matches named each role', /named on 3 matches and a wicketkeeper on 2/.test(done.replace(/\s+/g, ' ')), done)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── 390px ───────────────────────────────────────────────────────────────────
{
  const { page, ctx } = await open({ width: 390 })
  await openDetails(page, '2000-03-18')
  await page.getByTestId('keeper-quick').first().click().catch(() => {})
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ck('the Details editor with roles does not overflow at 390px', overflow <= 1, `overflow ${overflow}px`)
  await page.screenshot({ path: `${SHOTS}/details-390.png`, fullPage: false })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
