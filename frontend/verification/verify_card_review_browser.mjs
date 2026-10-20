// Card review, against the REAL screens with the API stubbed at the network layer.
//
// What is asserted:
//   * the overview shows the five groups, the progress by season, the download link, and the
//     bulk switch is a preview first: the Apply button stays disabled until the box is ticked,
//     and the wire then carries ONE POST to /bulk/apply;
//   * the queue asks for the right slice (group, undecided, 50 a page), draws one uniform line per
//     match, a caret appears only where there is more than one difference and opens the full list
//     in place, a click on Cricket Australia / Club card sends the choice, the combined choice does
//     NOT send anything from the list (it needs a preview), and "Last 3 seasons" asks again;
//   * the compare page marks the differing cell, shows where the club card came from, loads the
//     combined choice's preview only on request, and sends exactly one choice, then Undo;
//   * the match page shows the admin bar to a club admin only, and only for a paired match;
//   * no horizontal overflow at 390px on any screen.
//
//   node verify_card_review_browser.mjs   (BASE via APP_URL, default :5179)
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const BASE = process.env.APP_URL || 'http://localhost:5179'
const SHOTS = new URL('./shots/', import.meta.url).pathname
mkdirSync(SHOTS, { recursive: true })
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const M1 = 'aaaaaaaa-0000-4000-8000-000000000001'   // six differences
const M2 = 'aaaaaaaa-0000-4000-8000-000000000002'   // one difference, has a suggestion
const M3 = 'aaaaaaaa-0000-4000-8000-000000000003'   // pairing problem
const G1 = 'bbbbbbbb-0000-4000-8000-000000000001'
const G2 = 'bbbbbbbb-0000-4000-8000-000000000002'

const items6 = [
  { kind: 'team_total', category: 'total', label: 'Team total', ca: 171, club: 168 },
  { kind: 'batter_runs', category: 'batting', label: 'Pike, Jordan, runs', ca: 44, club: 41 },
  { kind: 'batter_runs', category: 'batting', label: 'Ortega, Sam, runs', ca: 12, club: 11 },
  { kind: 'how_out', category: 'batting', label: 'Raman, Dev, how out', ca: 'b K Moss', club: 'not out' },
  { kind: 'extras', category: 'extras', label: 'Extras', ca: 9, club: 8 },
  { kind: 'bowler_wickets', category: 'bowling', label: 'Tran, Lee, wickets', ca: 2, club: 3 },
]
const line = (id, gid, o = {}) => ({
  match_id: id, game_id: gid, season: 'Summer 2025/26', grade: '1st XI', date: '2026-03-14', opposition: 'Northfield',
  group: 'differ', headline: 'Team total 171 v 168', item_count: 6, items: items6, size: 55, suggested: null,
  current: 'club', decided_by_hand: false, decided_at: null, note: null,
  source: { kind: 'file', label: 'Imported from file Stage2.csv', filename: 'Stage2.csv', at: '2026-10-19T00:00:00Z', by: 'jack' },
  ca_holds: { balls: 9, credits: 8, fow: 7, partnerships: 6 }, club_holds: { balls: 0 }, club_richer: {},
  shared: 8, club_batters: 11, ca_batters: 11, ...o,
})
const ROWS = [
  line(M1, G1),
  line(M2, G2, { opposition: 'Westgate', grade: '4th XI', date: '2026-03-21', headline: 'Extras 11 v 12', item_count: 1,
    items: [{ kind: 'extras', category: 'extras', label: 'Extras', ca: 11, club: 12 }], size: 8, suggested: 'ca' }),
]
const OVERVIEW = {
  total: 3328, groups: { agree: 2112, small: 533, differ: 222, pairing: 233, nocard: 228 },
  current: { ca: 0, club: 3328, hybrid: 0 }, decided_by_hand: 0, agree_club_richer: 87,
  seasons: [
    { season: 'Summer 2025/26', matches: 253, ca: 0, club: 253, hybrid: 0, needs_decision: 31 },
    { season: 'Summer 2024/25', matches: 232, ca: 0, club: 232, hybrid: 0, needs_decision: 27 },
  ],
}
const detail = (current = 'club', extra = {}) => ({
  ...line(M1, G1, { current }), ca_date: '2026-03-14', club_date: '2026-03-14', ca_result: 'WIN', club_result: 'WIN',
  ca_opposition: 'Northfield', club_opposition: 'Northfield',
  innings: [{ number: 1, batting: [
    { player_id: 'p1', name: 'Ortega, Sam', ca: { runs: 28, balls: 77, how_out: 'c', position: 1, not_out: false }, club: { runs: 28, balls: null, how_out: 'c', position: 1, not_out: false }, differs: false },
    { player_id: 'p5', name: 'Pike, Jordan', ca: { runs: 36, balls: 81, how_out: 'c', position: 5, not_out: false }, club: { runs: 35, balls: null, how_out: 'c', position: 5, not_out: false }, differs: true },
    { player_id: 'p9', name: 'Reid, Rex', ca: { runs: 4, balls: 9, how_out: 'b', position: 9, not_out: false }, club: null, differs: true },
  ] }],
  bowling: [{ player_id: 'p6', name: 'Tran, Lee', ca: { wickets: 2, runs: 40 }, club: { wickets: 3, runs: 40 }, differs: true }],
  totals: { ca: [{ innings: 1, runs: 171, wickets: 8, extras: 9 }], club: [{ innings: 1, runs: 168, wickets: null, extras: 8 }] },
  effective_game_id: current === 'ca' ? G1 : M1,
  history: [{ id: 1, action: 'choice', from_choice: 'club', to_choice: 'ca', source: 'hand', note: null, batch_id: null, created_at: '2026-10-19T04:14:00Z', undone_at: null, username: 'neil', reverted: false }],
  ...extra,
})

const state = { current: 'club' }
const routes = (page, calls, o = {}) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url()
  const body = req.postData()
  calls.push({ url, method: req.method(), body })
  const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) {
    return json(o.member
      ? { id: 'mem', username: 'mem', display_name: 'Member', role: 'club_member', capabilities: [], club_slug: 'test-cc', club_id: 'org1', entitlements: { modules: ['admin'], status: 'active' } }
      : { id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', club_id: 'org1', entitlements: { modules: ['admin'], status: 'active' } })
  }
  if (/card-review\/overview/.test(url)) return json(OVERVIEW)
  if (/card-review\/bulk\/batches/.test(url)) return json({ batches: [{ batch_id: 'bt1', created_at: '2026-10-19T05:00:00Z', matches: 12, still_switched: 12 }] })
  if (/card-review\/bulk\/preview/.test(url)) return json({ matches: 2112, held_back: 87, by_season: [{ season: 'Summer 2025/26', matches: 162 }], sample: [{ match_id: M1, game_id: G1, date: '2026-03-14', grade: '1st XI', opposition: 'Northfield' }] })
  if (/card-review\/bulk\/apply/.test(url)) return json({ batch_id: 'bt2', switched: 2112, skipped: [] })
  if (/card-review\/accept/.test(url)) return json({ switched: 1, skipped: [] })
  if (/card-review\/matches\?/.test(url)) {
    const g = new URL(url).searchParams.get('group')
    if (new URL(url).searchParams.get('richer') === 'yes') {
      return json({ total: 1, offset: 0, limit: 50, sources: ['Stage2.csv'],
        rows: [line(M1, G1, { group: 'agree', headline: null, item_count: 0, items: [], size: 0, suggested: 'hybrid', club_richer: { balls: 6 } })] })
    }
    return json({ total: g === 'pairing' ? 1 : 2, offset: 0, limit: 50, sources: ['Stage2.csv'],
      rows: g === 'pairing' ? [line(M3, G1, { group: 'pairing', headline: null, item_count: 0, items: [], shared: 0, ca_batters: 11, club_batters: 11 })] : ROWS })
  }
  if (/card-review\/matches\/[^/]+\/preview/.test(url)) return json({ ok: true, reason: null, brought: ['Balls faced for 9 batters', 'Fall of wickets (10 wickets)'], left_out: ['Balls faced for Pike, Jordan: Cricket Australia has 36 runs and the club card 35'], counts: {} })
  if (/card-review\/matches\/[^/]+\/candidates/.test(url)) return json({ candidates: [{ game_id: G2, date: '2026-03-14', opposition: 'Northfield', grade: '1st XI', shared: 11, ca_batters: 11, club_batters: 11, taken_by: null }] })
  if (/card-review\/matches\/[^/]+\/choice/.test(url) && req.method() === 'POST') {
    const b = JSON.parse(body); state.current = b.choice
    return json({ match_id: M1, from: 'club', to: b.choice, left_out: b.choice === 'hybrid' ? ['x'] : [], brought: [], match: detail(b.choice) })
  }
  if (/card-review\/matches\/[^/]+\/undo/.test(url) && req.method() === 'POST') { state.current = 'club'; return json({ to: 'club', match: detail('club') }) }
  if (/card-review\/matches\/[^/]+\/(pair-ok|relink|unlink)/.test(url) && req.method() === 'POST') return json({ ok: true })
  if (/card-review\/matches\/[^/]+$/.test(url)) return json(detail(state.current))
  if (/card-review\/game\//.test(url)) {
    return json(o.unpaired ? { paired: false } : { paired: true, match_id: M1, game_id: G1, current: state.current, group: 'differ', suggested: null, decided_by_hand: false, headline: 'x', item_count: 6, effective_game_id: state.current === 'ca' ? G1 : M1 })
  }
  if (/\/games\/[^/]+\/scorecard/.test(url) || /\/games\/[0-9a-f-]{36}(\?|$)/.test(url)) {
    return json({ id: M1, home_team: 'Test CC', away_team: 'Northfield', home_away_known: true, innings_order_known: true, played_at: '2026-03-14',
      result: 'WIN', winning_team: 'Test CC', organisation_id: 'org1', grade: { id: 'g', name: '1st XI', raw_name: '1st XI' }, season: { id: 's', name: 'Summer 2025/26' },
      innings_totals: {}, batting: [], bowling: [], opp_batting: [], opp_bowling: [], fielding: [], fall_of_wickets: [], partnerships: [] })
  }
  if (/\/organisations\/|\/orgs?\//.test(url)) return json({ id: 'org1', slug: 'test-cc', name: 'Test CC' })
  if (/\/notifications\/(count|summary)/.test(url)) return json({ unseen_count: 0, items: [] })
  return json({})
})

async function open(browser, width, path, o = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_mem', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const calls = [], errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page, calls, o)
  await page.goto(BASE + path, { waitUntil: 'domcontentloaded' })
  return { ctx, page, calls, errors }
}
const overflow = page => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
const posts = (calls, re) => calls.filter(c => c.method === 'POST' && re.test(c.url))

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] })

// ── overview ───────────────────────────────────────────────────────────────────────────────────
{
  console.log('\n-- the overview --')
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review')
  await page.waitForSelector('[data-testid="groups"]', { timeout: 15000 })
  const text = await page.locator('[data-testid="groups"]').innerText()
  check('the five groups show their counts', ['2,112', '533', '222', '233', '228'].every(n => text.includes(n)), text.slice(0, 200))
  check('and their names', ['Scores agree', 'Small differences', 'Scores differ', 'Pairing looks wrong', 'No Cricket Australia card'].every(n => text.toLowerCase().includes(n.toLowerCase())))
  check('progress by season lists each season', (await page.locator('[data-testid="seasons"] tbody tr').count()) === 2)
  check('the spreadsheet link points at the export', (await page.getAttribute('[data-testid="export-link"]', 'href')).endsWith('/club-admin/card-review/export.csv'))
  check('the agree card says how many are held back from the switch, with a way to look at them',
    (await page.locator('[data-testid="richer-note"]').innerText()).includes('87') && (await page.getAttribute('[data-testid="richer-link"]', 'href')) === '/admin/card-review/agree?richer=yes')
  check('a previous bulk switch is offered an undo', (await page.locator('[data-testid="batches"]').innerText()).includes('Undo this batch'))
  await page.screenshot({ path: SHOTS + 'card_review_overview_1440.png', fullPage: true })
  await page.click('[data-testid="preview-switch"]')
  await page.waitForSelector('[data-testid="bulk-modal"]')
  check('the bulk switch opens a preview, not an action', posts(calls, /bulk\/apply/).length === 0)
  check('and says how many agreeing matches it leaves out, and why',
    (await page.locator('[data-testid="bulk-held-back"]').innerText()).includes('87') && (await page.locator('[data-testid="bulk-held-back"]').innerText()).includes('club card holds something'))
  const dis = await page.isDisabled('[data-testid="bulk-apply"]')
  check('Apply stays disabled until the sample has been looked at', dis === true)
  await page.check('[data-testid="bulk-ack"]')
  check('and unlocks when ticked', (await page.isDisabled('[data-testid="bulk-apply"]')) === false)
  await page.click('[data-testid="bulk-apply"]')
  await page.waitForTimeout(400)
  check('one POST goes to /bulk/apply', posts(calls, /bulk\/apply/).length === 1)
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── queue ──────────────────────────────────────────────────────────────────────────────────────
{
  console.log('\n-- the queue --')
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review/differ')
  await page.waitForSelector('[data-testid="queue-row"]', { timeout: 15000 })
  const first = calls.find(c => /card-review\/matches\?/.test(c.url))
  const q = new URL(first.url).searchParams
  check('it asks for one group, undecided, 50 a page', q.get('group') === 'differ' && q.get('decided') === 'no' && q.get('limit') === '50', first.url)
  check('every match is one uniform line', (await page.locator('[data-testid="queue-row"]').count()) === 2)
  check('a caret shows only where there is more than one difference', (await page.locator('[data-testid="caret"]').count()) === 1)
  check('the caret says how many more', (await page.locator('[data-testid="caret"]').innerText()).includes('+5 more'))
  check('the full list is closed to begin with', (await page.locator('[data-testid="difference-table"]').count()) === 0)
  await page.click('[data-testid="caret"]')
  check('the caret opens every difference in place', (await page.locator('[data-testid="difference-table"] tbody tr').count()) === 6)
  check('without leaving the page', page.url().endsWith('/admin/card-review/differ'))
  await page.screenshot({ path: SHOTS + 'card_review_queue_1440.png', fullPage: true })
  const before = calls.length
  await page.locator('[data-testid="queue-row"]').first().locator('[data-choice="hybrid"]').click()
  await page.waitForURL(/card-review\/match\/.+#hybrid/, { timeout: 8000 })
  check('the combined choice sends nothing from the list: it opens the match to preview first',
    posts(calls.slice(before), /choice/).length === 0)
  await page.goBack()
  await page.waitForSelector('[data-testid="queue-row"]')
  const row = page.locator('[data-testid="queue-row"]').nth(1)
  await row.locator('[data-choice="ca"]').click()
  await page.waitForTimeout(400)
  const choice = posts(calls, /choice/)
  check('Cricket Australia is one POST with that choice', choice.length === 1 && JSON.parse(choice[0].body).choice === 'ca')
  check('to that match', choice[0].url.includes(M2))
  await row.locator('input[type=checkbox]').check()
  await page.click('[data-testid="accept"]')
  await page.waitForTimeout(400)
  const acc = posts(calls, /accept/)
  check('accepting a selected suggestion sends that match id', acc.length === 1 && JSON.parse(acc[0].body).match_ids.includes(M2))
  const n = calls.length
  await page.getByText('Last 3 seasons').click()
  await page.waitForTimeout(400)
  check('"Last 3 seasons" asks again for the newest three', calls.slice(n).some(c => new URL(c.url).searchParams.get('recent_seasons') === '3'))
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── the matches held back from the bulk switch ────────────────────────────────────────────────
{
  console.log('\n-- matches whose club card holds more --')
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review/agree?richer=yes')
  await page.waitForSelector('[data-testid="queue-row"]', { timeout: 15000 })
  const first = calls.find(c => /card-review\/matches\?/.test(c.url))
  check('the link asks for just those matches', new URL(first.url).searchParams.get('richer') === 'yes', first.url)
  check('each is marked as holding more on the club card', (await page.locator('[data-testid="richer-badge"]').count()) === 1)
  check('and its suggestion is the combined choice, not Cricket Australia', (await page.locator('[data-testid="queue-row"]').first().innerText()).toLowerCase().includes('club + ca detail'))
  await page.click('[data-testid="richer-filter"]')
  await page.click('text=Any')
  await page.waitForTimeout(300)
  const last = calls.filter(c => /card-review\/matches\?/.test(c.url)).pop()
  check('turning the filter off stops asking for them', !new URL(last.url).searchParams.has('richer'), last.url)
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── pairing ────────────────────────────────────────────────────────────────────────────────────
{
  console.log('\n-- the pairing screen --')
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review/pairing')
  await page.waitForSelector('[data-testid="pairing-card"]', { timeout: 15000 })
  await page.click('text=Find a better match')
  await page.waitForSelector('[data-testid="candidates"]')
  check('a better match is offered with its evidence', (await page.locator('[data-testid="candidates"]').innerText()).toLowerCase().includes('11 of 11 batters in common'))
  await page.click('text=Re-link to this match')
  await page.waitForTimeout(300)
  const rl = posts(calls, /relink/)
  check('re-linking is one POST naming the Cricket Australia game', rl.length === 1 && JSON.parse(rl[0].body).game_id === G2)
  await page.screenshot({ path: SHOTS + 'card_review_pairing_1440.png', fullPage: true })
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── compare ─────────────────────────────────────────────────────────────────────────────────────
{
  console.log('\n-- the compare page --')
  state.current = 'club'
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review/differ')
  await page.waitForSelector('[data-testid="queue-row"]', { timeout: 15000 })
  await page.locator('[data-testid="headline"]').first().click()
  await page.waitForSelector('[data-testid="card-ca"]', { timeout: 15000 })
  check('both cards are drawn', (await page.locator('[data-testid="card-club"]').count()) === 1)
  const caCard = await page.locator('[data-testid="card-ca"]').innerText()
  const clubCard = await page.locator('[data-testid="card-club"]').innerText()
  check('each says where it came from', caCard.includes('Cricket Australia, synced') && clubCard.includes('Imported from file Stage2.csv'))
  check('a batter on one card only is shown as a gap, not dropped', clubCard.includes('not on this card'))
  check('Cricket Australia shows balls faced where the club card has none', caCard.includes('81') && /—/.test(clubCard))
  check('the position reads 1 of N from the list it came from', (await page.locator('[data-testid="position"]').innerText()).startsWith('1 of 2'))
  check('the combined choice has not read Cricket Australia yet: no preview request', !calls.some(c => /\/preview/.test(c.url)))
  await page.click('[data-testid="preview"]')
  await page.waitForSelector('[data-testid="preview-body"]')
  check('the preview lists what comes over', (await page.locator('[data-testid="brought"]').innerText()).includes('Balls faced for 9 batters'))
  check('and what is left out, with the reason', (await page.locator('[data-testid="left-out"]').innerText()).includes('Pike, Jordan'))
  await page.screenshot({ path: SHOTS + 'card_review_compare_1440.png', fullPage: true })
  await page.click('[data-testid="choose-hybrid"]')
  await page.waitForTimeout(400)
  const ch = posts(calls, /choice/)
  check('choosing it is one POST with the combined choice', ch.length === 1 && JSON.parse(ch[0].body).choice === 'hybrid')
  await page.click('[data-testid="undo"]')
  await page.waitForTimeout(400)
  check('Undo is one POST to /undo', posts(calls, /undo/).length === 1)
  await page.click('[data-testid="diff-toggle"]')
  check('the full difference list opens under the cards', (await page.locator('[data-testid="difference-table"] tbody tr').count()) === 6)
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── the bar on the match page ────────────────────────────────────────────────────────────────────
{
  console.log('\n-- the match page --')
  state.current = 'club'
  const a = await open(browser, 1440, `/games/${M1}`)
  await a.page.waitForSelector('[data-testid="card-review-bar"]', { timeout: 15000 })
  check('a club admin sees the bar on a paired match', true)
  check('it names what the site shows', (await a.page.locator('[data-testid="card-review-bar"]').innerText()).includes('Club scorecard'))
  await a.page.screenshot({ path: SHOTS + 'card_review_bar_1440.png' })
  await a.page.locator('[data-testid="bar-choice"] [data-choice="ca"]').click()
  await a.page.waitForTimeout(500)
  check('one click sends one choice', posts(a.calls, /choice/).length === 1)
  check('and the page follows to the card the site now shows', a.page.url().includes(G1), a.page.url())
  await a.ctx.close()
  const b = await open(browser, 1440, `/games/${M1}`, { unpaired: true })
  await b.page.waitForTimeout(1500)
  check('no bar for a match stored once', (await b.page.locator('[data-testid="card-review-bar"]').count()) === 0)
  await b.ctx.close()
  const c = await open(browser, 1440, `/games/${M1}`, { member: true })
  await c.page.waitForTimeout(1500)
  check('no bar, and no request for one, for a member without the capability',
    (await c.page.locator('[data-testid="card-review-bar"]').count()) === 0 && !c.calls.some(x => /card-review/.test(x.url)))
  await c.ctx.close()
}

// ── a phone ──────────────────────────────────────────────────────────────────────────────────────
{
  console.log('\n-- 390px --')
  for (const [label, path, sel] of [
    ['overview', '/admin/card-review', '[data-testid="groups"]'],
    ['queue', '/admin/card-review/differ', '[data-testid="queue-row"]'],
    ['pairing', '/admin/card-review/pairing', '[data-testid="pairing-card"]'],
    ['compare', `/admin/card-review/match/${M1}`, '[data-testid="card-ca"]'],
  ]) {
    state.current = 'club'
    const { ctx, page } = await open(browser, 390, path)
    await page.waitForSelector(sel, { timeout: 15000 })
    check(`${label} has no page-level horizontal overflow`, (await overflow(page)) <= 1, `overflow ${await overflow(page)}px`)
    if (label === 'compare') await page.screenshot({ path: SHOTS + 'card_review_compare_390.png', fullPage: true })
    if (label === 'queue') await page.screenshot({ path: SHOTS + 'card_review_queue_390.png', fullPage: true })
    await ctx.close()
  }
}

await browser.close()
console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
process.exit(FAIL.length ? 1 : 0)
