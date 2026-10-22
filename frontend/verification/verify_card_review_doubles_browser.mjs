// Card review: the Possible doubles step, Find a match, and the filters every step shares, against
// the REAL screens with the API stubbed at the network layer.
//
// What is asserted:
//   * the overview has five steps in order (doubles first), counts the doubles, says when the scan
//     failed, offers Find a match, and "Start here" opens the doubles first;
//   * the doubles list asks for the right slice, draws both copies of each pair with the evidence,
//     and each action is exactly ONE request with the right ids: link, different matches, remove a
//     copy (the existing Manual Entries delete, after a confirm), put back; after a change the list is
//     asked for again with fresh=true;
//   * the filters (opposition, player, grade, competition, dates) are the same panel on every step:
//     they ride in the address bar, go to the server as query parameters, and Find a match keeps them;
//   * Find a match asks for nothing until it has something to look for, shows linked pairs with both
//     copies, and links a ticked club-only and Cricket Australia-only fixture, but only that pairing;
//   * no horizontal overflow at 390px on any screen.
//
//   node verify_card_review_doubles_browser.mjs   (BASE via APP_URL, default :5179)
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

const MA = 'aaaaaaaa-0000-4000-8000-00000000000a', GA = 'bbbbbbbb-0000-4000-8000-00000000000a'
const MB = 'aaaaaaaa-0000-4000-8000-00000000000b', GB = 'bbbbbbbb-0000-4000-8000-00000000000b'
const MC = 'aaaaaaaa-0000-4000-8000-00000000000c', MD = 'aaaaaaaa-0000-4000-8000-00000000000d'
const ML = 'aaaaaaaa-0000-4000-8000-00000000000e', GL = 'bbbbbbbb-0000-4000-8000-00000000000e'
const MR = 'aaaaaaaa-0000-4000-8000-000000000010', GR = 'bbbbbbbb-0000-4000-8000-000000000010', GW = 'bbbbbbbb-0000-4000-8000-000000000011'

const side = (kind, id, o = {}) => ({
  kind, id, linked: false, date: '2006-02-04', season: 'Summer 2005/06', grade: 'A Grade', opposition: 'Warnbro',
  format: kind === 'ca' ? 'Two Day' : 'One Day', result: 'WIN', batters: 9, bowlers: 5,
  source: kind === 'ca' ? { kind: 'cricket_australia', label: 'Synced from Cricket Australia', at: null }
    : { kind: 'file', label: 'Imported from file Archive.csv', at: '2026-10-01T00:00:00Z' }, ...o,
})
const ROWS = [
  { key: `ca:${MA}:${GA}`, kind: 'ca', strength: 'strong', a: side('club', MA), b: side('ca', GA), shared: 9, gap_days: 0,
    same_day: true, opposition_agrees: true, both_cards: true, formats_differ: true, date: '2006-02-04' },
  { key: `ca:${MB}:${GB}`, kind: 'ca', strength: 'possible', a: side('club', MB, { date: '2004-12-11', opposition: 'Hillman' }),
    b: side('ca', GB, { date: '2004-12-11', opposition: 'Hillman', batters: 0, bowlers: 0 }), shared: 0, gap_days: 0, same_day: true,
    opposition_agrees: true, both_cards: false, formats_differ: false, date: '2004-12-11' },
  { key: `club:${MC}:${MD}`, kind: 'club', strength: 'strong', a: side('club', MC, { date: '2007-02-24', format: 'Two Day' }),
    b: side('club', MD, { date: '2007-02-24' }), shared: 9, gap_days: 0, same_day: true, opposition_agrees: true,
    both_cards: true, formats_differ: true, date: '2007-02-24' },
]
// A card linked to the wrong game: the B grade card sits on the A grade game, the real B game is free.
ROWS.push({ key: `relink:${MR}:${GR}`, kind: 'relink', strength: 'strong', a: side('club', MR, { linked: true, date: '2006-02-04', grade: 'B grade', opposition: 'Safety Bay' }),
  b: side('ca', GR, { date: '2006-02-04', grade: 'B Grade: McIntosh Cup', opposition: 'Safety Bay Cricket Club' }), shared: 9, gap_days: 0, same_day: true,
  opposition_agrees: true, both_cards: true, confirmed: true, formats_differ: true, date: '2006-02-04',
  current: side('ca', GW, { date: '2006-02-04', grade: 'A Grade', opposition: 'Safety Bay Cricket Club', batters: 0, shared_with_club: 0 }) })
const COUNTS = { total: 4, dismissed: 1, by_strength: { strong: 3, likely: 0, possible: 1 }, by_kind: { ca: 2, club: 1, relink: 1 }, formats_differ: 3 }
// Two cards that each sit on the other's game: the C grade card is on the D grade game.
const MS = 'aaaaaaaa-0000-4000-8000-000000000020', MT = 'aaaaaaaa-0000-4000-8000-000000000021'
const GS = 'bbbbbbbb-0000-4000-8000-000000000020', GT = 'bbbbbbbb-0000-4000-8000-000000000021'
const SWAP_ROW = { key: `swap:${MS}:${GS}`, kind: 'swap', strength: 'strong', a: side('club', MS, { linked: true, date: '2005-01-22', grade: 'C grade', opposition: 'Safety Bay', batters: 11 }),
  b: side('ca', GS, { date: '2005-01-22', grade: 'C Grade: Jeffrey Cup', opposition: 'Safety Bay Cricket Club', batters: 10 }), shared: 10, gap_days: 0, same_day: true,
  opposition_agrees: true, both_cards: true, confirmed: true, formats_differ: false, date: '2005-01-22',
  current: side('ca', GT, { date: '2005-01-22', grade: 'D Grade', opposition: 'Safety Bay Cricket Club', batters: 0, shared_with_club: 0 }),
  partner: { match: side('club', MT, { linked: true, date: '2005-01-22', grade: 'D grade', opposition: 'Safety Bay', batters: 0 }),
    moves_to: side('ca', GT, { date: '2005-01-22', grade: 'D Grade', opposition: 'Safety Bay Cricket Club', batters: 0 }),
    from_game: side('ca', GS, { date: '2005-01-22', grade: 'C Grade: Jeffrey Cup', batters: 10 }) } }
const DISMISSED = [{ key: `ca:${MA}:${GB}`, kind: 'ca', a: side('club', MA), b: side('ca', GB), date: '2006-02-04', dismissed_by: 'jack' }]
const OVERVIEW = {
  total: 3328, groups: { agree: 2112, small: 533, differ: 222, pairing: 233, nocard: 228, doubles: 3 },
  current: { ca: 0, club: 3328, hybrid: 0 }, decided_by_hand: 0, agree_club_richer: 87, bulk_left: 2025,
  todo: { doubles: 3, pairing: 233, agree: 2112, small: 533, differ: 222 }, doubles: { ...COUNTS, error: null },
  seasons: [{ season: 'Summer 2025/26', matches: 253, ca: 0, club: 253, hybrid: 0, needs_decision: 31 }],
}
const FIND_ROWS = [
  { key: `linked:${ML}:${GL}`, state: 'linked', date: '2006-03-04', match_id: ML, game_id: GL,
    copies: [side('club', ML, { linked: true, date: '2006-03-04' }), side('ca', GL, { date: '2006-03-04' })],
    review: { group: 'agree', current: 'ca', headline: null, differences: 0, decided_by_hand: false }, candidate: null },
  { key: `club_only:${MA}:`, state: 'club_only', date: '2006-02-04', match_id: MA, game_id: null, copies: [side('club', MA)], review: null, candidate: ROWS[0] },
  { key: `ca_only::${GA}`, state: 'ca_only', date: '2006-02-04', match_id: null, game_id: GA, copies: [side('ca', GA)], review: null, candidate: ROWS[0] },
  { key: `club_only:${MC}:`, state: 'club_only', date: '2007-02-24', match_id: MC, game_id: null, copies: [side('club', MC, { date: '2007-02-24' })], review: null, candidate: null },
]

// A real server takes time. The stub waits too: with instant answers a page that refetches in a loop
// still looks fine (each answer lands before the next request), which is how that bug got through.
const LATENCY = 150
// The compare page for a club card linked to the wrong game (the page in the Shoalwater report).
const detailMismatch = {
  match_id: MR, game_id: GW, season: 'Summer 2003/04', grade: 'C1 Grade', date: '2003-11-22', opposition: 'Rockingham Beach', group: 'pairing',
  headline: null, items: [], size: 0, suggested: null, current: 'ca', decided_by_hand: true, decided_at: null, note: null, club_richer: {},
  source: { kind: 'file', label: 'Imported from file manual_games_scorecards.csv', filename: 'manual_games_scorecards.csv', at: '2026-09-29T00:00:00Z', by: 'elton' },
  ca_holds: { balls: 0, credits: 0, fow: 6, partnerships: 0, opp_batters: 11 }, club_holds: { balls: 0, fow: 10, partnerships: 10 },
  shared: 0, club_batters: 11, ca_batters: 11, ca_date: '2003-11-22', club_date: '2003-11-22', ca_result: 'WIN', club_result: 'WIN',
  ca_opposition: 'Rockingham Hornets Cricket Club', club_opposition: 'Rockingham Beach',
  innings: [{ number: 1, batting: [{ player_id: 'p1', name: 'Ritchie, Peter', ca: { runs: 16, balls: 0, how_out: 'c', position: 1, not_out: false }, club: null, differs: true },
                                     { player_id: 'p2', name: 'Spinks, Ray', ca: null, club: { runs: 8, balls: null, how_out: 'c', position: 2, not_out: false }, differs: true }] }],
  bowling: [], totals: { ca: [], club: [] }, effective_game_id: GW,
  history: [{ id: 1, action: 'choice', from_choice: 'club', to_choice: 'ca', source: 'hand', note: null, batch_id: null, created_at: '2026-10-21T07:29:00Z', undone_at: null, username: 'darrenhind', reverted: false }],
}
const routes = (page, calls, o = {}) => page.route('**/api/**', async (route) => {
  const req = route.request(), url = req.url(), body = req.postData()
  calls.push({ url, method: req.method(), body })
  if (/card-review\/(doubles\?|find\?|matches\?)/.test(url)) await new Promise(r => setTimeout(r, LATENCY))
  const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) {
    return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', club_id: 'org1', entitlements: { modules: ['admin'], status: 'active' } })
  }
  if (/card-review\/overview/.test(url)) return json(o.scanFailed ? { ...OVERVIEW, groups: { ...OVERVIEW.groups, doubles: 0 }, todo: { ...OVERVIEW.todo, doubles: 0 }, doubles: { error: 'The scan for possible doubles failed. Reload to try again.' } } : OVERVIEW)
  if (/card-review\/bulk\/batches/.test(url)) return json({ batches: [] })
  if (/card-review\/matches\/[^/]+\/candidates/.test(url)) return json({ candidates: [{ game_id: GR, date: '2003-11-22', opposition: 'Rockingham Beach', grade: 'C1 Grade', shared: 10, ca_batters: 11, club_batters: 11, taken_by: null }] })
  if (/card-review\/matches\/[^/]+\/(pair-ok|unlink)/.test(url) && req.method() === 'POST') return json({ ok: true })
  if (/card-review\/matches\/[^/]+$/.test(url) && url.includes(MR)) return json(detailMismatch)
  if (/\/games\/[0-9a-f-]{36}/.test(url) && !/card-review/.test(url)) return json({ id: MR, home_team: 'Shoalwater', away_team: 'Rockingham Beach', home_away_known: true, innings_order_known: true, played_at: '2003-11-22', result: 'WIN', winning_team: 'Shoalwater', organisation_id: 'org1', grade: { id: 'g', name: 'C1 Grade', raw_name: 'C1 Grade' }, season: { id: 's', name: 'Summer 2003/04' }, innings_totals: {}, batting: [], bowling: [], opp_batting: [], opp_bowling: [], fielding: [], fall_of_wickets: [], partnerships: [] })
  if (/card-review\/history/.test(url)) {
    const only = new URL(url).searchParams.get('only') === 'undoable'
    const all = [
      { id: 9, action: 'not_double', what: 'Said the suggested game is not the right one', match_id: MR, date: '2004-12-11', grade: 'B grade', opposition: 'Safety Bay', season: 'Summer 2004/05', by: 'elton', bulk: false, at: '2026-10-20T01:00:00Z', undone_at: null, can: 'restore', linked_now: true, other_id: GR, other_kind: 'relink' },
      { id: 8, action: 'unlink', what: 'Unlinked: said these are two different matches', match_id: MA, date: '2006-02-04', grade: 'A Grade', opposition: 'Warnbro', season: 'Summer 2005/06', by: 'elton', bulk: false, at: '2026-10-20T00:50:00Z', undone_at: null, can: 'undo', linked_now: false, other_id: null, other_kind: null },
      { id: 7, action: 'choice', what: 'Switched to Cricket Australia (was the club scorecard)', match_id: MB, date: '2004-12-11', grade: 'A Grade', opposition: 'Hillman', season: 'Summer 2004/05', by: 'jack', bulk: true, at: '2026-10-19T23:00:00Z', undone_at: null, can: null, linked_now: true, other_id: null, other_kind: null },
      { id: 6, action: 'link', what: 'Linked the club scorecard to a Cricket Australia match', match_id: MC, date: '2007-02-24', grade: 'B grade', opposition: 'Halls Head', season: 'Summer 2006/07', by: 'elton', bulk: false, at: '2026-10-19T22:00:00Z', undone_at: '2026-10-19T22:05:00Z', can: null, linked_now: false, other_id: null, other_kind: null },
    ]
    const rows = only ? all.filter(r => r.can) : all
    return json({ rows, more: false, offset: 0, limit: 50 })
  }
  if (/card-review\/matches\/[^/]+\/undo/.test(url) && req.method() === 'POST') return json({ ok: true, match: null })
  if (/card-review\/find\/options/.test(url)) return json({ seasons: ['Summer 2005/06', 'Summer 2004/05'], competitions: ['Reserves League'], players: ['Ritchie, Peter', 'Ritchie, Rod', 'Hind, Darren', 'Smith, John'], oppositions: ['Warnbro Knights', 'Old Irwinians', 'Hillman'], grades: ['A Grade', 'B Grade', 'C1 Grade'] })
  if (/card-review\/find\?/.test(url)) return json({ total: FIND_ROWS.length, offset: 0, limit: 25, capped: false, rows: FIND_ROWS })
  if (/card-review\/doubles\/bulk\/preview/.test(url)) return json({ relink: 1, ca: 2, swap: o.swap ? 2 : 0, sample: o.swap ? [SWAP_ROW, ROWS[3]] : [ROWS[3], ROWS[0]] })
  if (/card-review\/doubles\/bulk/.test(url) && req.method() === 'POST') return json({ batch_id: 'bt9', relinked: 1, linked: 2, skipped: [] })
  if (/card-review\/matches\/[^/]+\/relink/.test(url) && req.method() === 'POST') return json({ ok: true })
  if (/card-review\/doubles\/swap/.test(url) && req.method() === 'POST') return json({ match_id: MS, partner_id: MT, batch_id: 'bt1' })
  if (/card-review\/doubles\/(link|dismiss|restore)/.test(url) && req.method() === 'POST') return json({ ok: true, shows: 'ca' })
  if (/card-review\/doubles\?/.test(url)) {
    const sp = new URL(url).searchParams
    const dis = sp.get('shown') === 'dismissed'
    if (dis && sp.get('player') === 'Unlinked') return json({ total: 1, offset: 0, limit: 25, seasons: [], counts: COUNTS, rows: [{ ...DISMISSED[0], via: 'unlink' }] })
    if (sp.get('player') === 'Nobody') return json({ total: 0, offset: 0, limit: 25, seasons: [], counts: COUNTS, rows: [], player_note: { query: 'Nobody', matched: [], fuzzy: false } })
    if (sp.get('player') === 'peter richie') return json({ total: 1, offset: 0, limit: 25, seasons: [], counts: COUNTS, rows: [ROWS[0]], player_note: { query: 'peter richie', matched: ['Ritchie, Peter'], fuzzy: true } })
    const all = o.swap ? [SWAP_ROW, ...ROWS] : ROWS
    const rows = dis ? DISMISSED : all.filter(r => !sp.get('kind') || r.kind === sp.get('kind'))
    const counts = o.swap ? { ...COUNTS, total: 5, by_kind: { ...COUNTS.by_kind, swap: 1 }, by_strength: { ...COUNTS.by_strength, strong: 4 } } : COUNTS
    return json({ total: rows.length, offset: 0, limit: 25, seasons: ['Summer 2005/06'], counts, rows })
  }
  if (/card-review\/matches\?/.test(url)) return json({ total: 0, offset: 0, limit: 50, sources: [], rows: [] })
  if (/manual-entries\/games\/[0-9a-f-]{36}$/.test(url) && req.method() === 'DELETE') return json({ deleted: true })
  if (/\/notifications\/(count|summary)/.test(url)) return json({ unseen_count: 0, items: [] })
  return json({})
})

async function open(browser, width, path, o = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    for (const k of ['boss', 'anon', 'mem']) localStorage.setItem(`bs_clubhouse_intro_mode_${k}`, JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const calls = [], errors = []
  page.on('pageerror', e => errors.push(String(e)))
  page.on('dialog', d => d.accept())
  await routes(page, calls, o)
  await page.goto(BASE + path, { waitUntil: 'domcontentloaded' })
  return { ctx, page, calls, errors }
}
const overflow = page => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
const posts = (calls, re) => calls.filter(c => c.method === 'POST' && re.test(c.url))
const gets = (calls, re) => calls.filter(c => c.method === 'GET' && re.test(c.url))

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] })

// ── overview ───────────────────────────────────────────────────────────────────────────────────
{
  console.log('\n-- the overview --')
  const { ctx, page, errors } = await open(browser, 1440, '/admin/card-review')
  await page.waitForSelector('[data-testid="groups"]', { timeout: 15000 }).catch(async e => { console.log('PAGEERRORS', errors, (await page.locator('body').innerText()).slice(0, 400)); throw e })
  const order = await page.locator('[data-testid^="step-"]').evaluateAll(els => els.map(e => e.dataset.testid))
  check('five steps, the doubles first', order.join(',') === 'step-doubles,step-pairing,step-agree,step-small,step-differ', order.join(','))
  check('the doubles step is the one marked to start with', (await page.getAttribute('[data-testid="step-doubles"]', 'data-state')) === 'next')
  check('each step says its place in the order', (await page.locator('[data-testid="step-doubles"]').innerText()).toLowerCase().includes('step 1 of 5'))
  check('the doubles step shows its count', (await page.locator('[data-testid="step-doubles"]').innerText()).includes('3'))
  check('Find a match is offered on the overview', (await page.locator('[data-testid="find-link"]').count()) === 1)
  check('start here names the doubles', (await page.locator('[data-testid="start-here"]').innerText()).toLowerCase().includes('find the doubles'))
  await page.click('[data-testid="start-here"]')
  await page.waitForURL(/card-review\/doubles$/, { timeout: 8000 })
  check('and opens that list', page.url().endsWith('/admin/card-review/doubles'))
  await ctx.close()
  const bad = await open(browser, 1440, '/admin/card-review', { scanFailed: true })
  await bad.page.waitForSelector('[data-testid="groups"]', { timeout: 15000 })
  check('a failed scan is said on the page and the other steps still draw', (await bad.page.locator('body').innerText()).includes('scan for possible doubles failed') && (await bad.page.locator('[data-testid="step-differ"]').count()) === 1)
  await bad.ctx.close()
  const narrow = await open(browser, 390, '/admin/card-review')
  await narrow.page.waitForSelector('[data-testid="groups"]', { timeout: 15000 })
  check('no horizontal overflow at 390px', (await overflow(narrow.page)) <= 0)
  await narrow.ctx.close()
}

// ── the doubles list ───────────────────────────────────────────────────────────────────────────
{
  console.log('\n-- the doubles list --')
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review/doubles')
  await page.waitForSelector('[data-testid="double-card"]', { timeout: 15000 }).catch(async e => { console.log('PAGEERRORS', errors, (await page.locator('body').innerText()).slice(0, 400)); throw e })
  const first = gets(calls, /card-review\/doubles\?/)[0]
  const q = new URL(first.url).searchParams
  check('it asks for the open pairs, strongest first, 25 a page', q.get('shown') === 'open' && q.get('sort') === 'strongest' && q.get('limit') === '25', first.url)
  check('one card per pair', (await page.locator('[data-testid="double-card"]').count()) === 4)
  check('every card draws both copies', (await page.locator('[data-testid="double-card"]').first().locator('[data-testid="side"]').count()) === 2)
  const ev = (await page.locator('[data-testid="evidence"]').first().innerText()).toLowerCase()
  check('the evidence says strength, batters in common, the gap and the opposition', /strong match/i.test(ev) && ev.includes('9 of 9 batters in common') && /same day/i.test(ev) && /same opposition/i.test(ev), ev)
  check('two copies under different match types are flagged', /different match types/i.test(ev))
  check('a pair where one card has no batters says so', (await page.locator('[data-testid="evidence"]').nth(1).innerText()).toLowerCase().includes('no batters to compare'))
  check('the formats note counts them', (await page.locator('[data-testid="formats-note"]').innerText()).includes('3'))
  check('each side links to its real scorecard page', (await page.locator('[data-testid="side"] a').first().getAttribute('href')) === `/games/${MA}`)
  await page.screenshot({ path: SHOTS + 'card_review_doubles_1440.png', fullPage: true })
  const n = calls.length
  await page.locator('[data-testid="double-card"]').first().locator('[data-testid="link"]').click()
  await page.waitForTimeout(400)
  const link = posts(calls, /doubles\/link/)
  check('Same match is ONE POST with the club card and the Cricket Australia match', link.length === 1 && JSON.parse(link[0].body).match_id === MA && JSON.parse(link[0].body).game_id === GA, JSON.stringify(link.map(l => l.body)))
  check('and the list is asked for again with a fresh scan', gets(calls.slice(n), /card-review\/doubles\?/).some(c => new URL(c.url).searchParams.get('fresh') === 'true'))
  await page.locator('[data-testid="double-card"]').nth(1).locator('[data-testid="dismiss"]').click()
  await page.waitForTimeout(300)
  const dis = posts(calls, /doubles\/dismiss/)
  check('Different matches is ONE POST naming both ids and the kind', dis.length === 1 && JSON.parse(dis[0].body).kind === 'ca' && JSON.parse(dis[0].body).other_id === GB, JSON.stringify(dis.map(d => d.body)))
  const wrong = page.locator('[data-testid="double-card"][data-kind="relink"]')
  check('a card linked to the wrong game says where it is linked now and that none of its batters are there', (await wrong.locator('[data-testid="current-link"]').innerText()).includes('A Grade v Safety Bay Cricket Club') && (await wrong.locator('[data-testid="current-link"]').innerText()).includes("0 of this card's 9 batters"))
  check('it offers moving the link, not a plain link', (await wrong.locator('[data-testid="relink"]').count()) === 1 && (await wrong.locator('[data-testid="link"]').count()) === 0)
  await wrong.locator('[data-testid="relink"]').click()
  await page.waitForTimeout(400)
  const rl = posts(calls, /matches\/[^/]+\/relink/)
  check('moving the link is ONE POST to that card with the right game', rl.length === 1 && rl[0].url.includes(MR) && JSON.parse(rl[0].body).game_id === GR, JSON.stringify(rl.map(r => [r.url, r.body])))
  check('and it did not send a plain link', posts(calls, /doubles\/link/).length === 1)
  const clubCard = page.locator('[data-testid="double-card"][data-kind="club"]')
  check('two club scorecards offer removing a copy, not a link', (await clubCard.locator('[data-testid="link"]').count()) === 0 && (await clubCard.locator('[data-testid="remove-b"]').count()) === 1)
  await clubCard.locator('[data-testid="remove-b"]').click()
  await page.waitForTimeout(400)
  const del = calls.filter(c => c.method === 'DELETE')
  check('removing a copy is ONE DELETE of that copy through Manual Entries', del.length === 1 && del[0].url.endsWith(`/club-admin/manual-entries/games/${MD}`), del.map(d => d.url).join(','))
  check('and a link request was never sent for it', posts(calls, /doubles\/link/).length === 1)
  await page.click('[data-testid="k-club"]')
  await page.waitForTimeout(300)
  check('"Two club scorecards" asks for that kind', gets(calls, /card-review\/doubles\?/).some(c => new URL(c.url).searchParams.get('kind') === 'club'))
  await page.click('[data-testid="shown-dismissed"]')
  await page.waitForSelector('[data-testid="restore"]', { timeout: 8000 })
  await page.click('[data-testid="restore"]')
  await page.waitForTimeout(300)
  const res = posts(calls, /doubles\/restore/)
  check('Put back is ONE POST', res.length === 1 && JSON.parse(res[0].body).match_id === MA, JSON.stringify(res.map(r => r.body)))
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
  // the list settles: loaded once, and no further requests while it sits there
  const quiet = await open(browser, 1440, '/admin/card-review/doubles?player=Ritchie')
  await quiet.page.waitForSelector('[data-testid="double-card"]', { timeout: 15000 })
  const n1 = gets(quiet.calls, /card-review\/doubles\?/).length
  await quiet.page.waitForTimeout(1500)
  const n2 = gets(quiet.calls, /card-review\/doubles\?/).length
  check('the list loads once and then stays quiet (no refetch loop)', n1 <= 2 && n2 === n1, `after load ${n1}, 1.5s later ${n2}`)
  await quiet.ctx.close()
  // a search with no answer says so instead of spinning
  const none = await open(browser, 1440, '/admin/card-review/doubles?player=Nobody')
  await none.page.waitForSelector('[data-testid="player-note"]', { timeout: 8000 })
  const m1 = gets(none.calls, /card-review\/doubles\?/).length
  await none.page.waitForTimeout(1200)
  check('no result shows the empty message, not the spinner', (await none.page.locator('body').innerText()).includes('No possible doubles here.') && !(await none.page.locator('body').innerText()).includes('Looking for matches held twice'))
  check('and says that no player at the club matches', (await none.page.locator('[data-testid="player-note"]').innerText()).includes('No player at this club matches "Nobody"'))
  check('and it did not keep asking', gets(none.calls, /card-review\/doubles\?/).length === m1)
  await none.ctx.close()
  // a misspelt name is matched and the page says what it showed
  const typo = await open(browser, 1440, '/admin/card-review/doubles?player=peter%20richie')
  await typo.page.waitForSelector('[data-testid="player-note"]', { timeout: 8000 })
  check('a close name shows its pairs and says which player it used', (await typo.page.locator('[data-testid="player-note"]').innerText()).includes('Ritchie, Peter') && (await typo.page.locator('[data-testid="double-card"]').count()) === 1)
  await typo.ctx.close()
  const narrow = await open(browser, 390, '/admin/card-review/doubles')
  await narrow.page.waitForSelector('[data-testid="double-card"]', { timeout: 15000 })
  check('no horizontal overflow at 390px', (await overflow(narrow.page)) <= 0, String(await overflow(narrow.page)))
  await narrow.page.screenshot({ path: SHOTS + 'card_review_doubles_390.png', fullPage: true })
  await narrow.ctx.close()
}

// ── the filters on a step ──────────────────────────────────────────────────────────────────────
{
  console.log('\n-- the same filters on every step --')
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review/differ?player=Ritchie&competition=Reserves%20League')
  await page.waitForSelector('[data-testid="match-filters"]', { timeout: 15000 })
  await page.waitForTimeout(400)
  const q = new URL(gets(calls, /card-review\/matches\?/)[0].url).searchParams
  check('a step reads the filters from the address and sends them', q.get('player') === 'Ritchie' && q.get('competition') === 'Reserves League' && q.get('group') === 'differ')
  check('the panel shows them', (await page.inputValue('[data-testid="f-player"]')) === 'Ritchie')
  check('Find a match from a step keeps the words', (await page.getAttribute('[data-testid="find-link"]', 'href')).includes('player=Ritchie'))
  await page.fill('[data-testid="f-grade"]', 'B Grade')
  await page.fill('[data-testid="f-from"]', '2005-12-01')
  const n = calls.length
  await page.click('[data-testid="f-apply"]')
  await page.waitForTimeout(500)
  const q2 = new URL(gets(calls.slice(n), /card-review\/matches\?/).pop().url).searchParams
  check('searching sends the new words too', q2.get('grade') === 'B Grade' && q2.get('date_from') === '2005-12-01' && q2.get('player') === 'Ritchie')
  check('and they ride in the address bar', page.url().includes('grade=B+Grade') || page.url().includes('grade=B%20Grade'))
  await page.click('[data-testid="f-clear"]')
  await page.waitForTimeout(400)
  const q3 = new URL(gets(calls, /card-review\/matches\?/).pop().url).searchParams
  check('Clear removes them all', !q3.get('player') && !q3.get('grade') && !q3.get('competition'))
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
  const d = await open(browser, 1440, '/admin/card-review/doubles?player=Ritchie')
  await d.page.waitForSelector('[data-testid="double-card"]', { timeout: 15000 })
  check('the doubles list takes them as well', gets(d.calls, /card-review\/doubles\?/).some(c => new URL(c.url).searchParams.get('player') === 'Ritchie'))
  await d.ctx.close()
}

// ── find a match ───────────────────────────────────────────────────────────────────────────────
{
  console.log('\n-- find a match --')
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review/find')
  await page.waitForSelector('[data-testid="match-filters"]', { timeout: 15000 })
  await page.waitForTimeout(400)
  check('with nothing to look for it asks for nothing', gets(calls, /card-review\/find\?/).length === 0)
  await page.fill('[data-testid="f-player"]', 'Ritchie')
  await page.click('[data-testid="f-apply"]')
  await page.waitForSelector('[data-testid="fixture"]', { timeout: 8000 })
  const q = new URL(gets(calls, /card-review\/find\?/)[0].url).searchParams
  check('a search sends the player', q.get('player') === 'Ritchie')
  check('every fixture is listed with its state', (await page.locator('[data-testid="fixture"]').evaluateAll(e => e.map(x => x.dataset.state))).join(',') === 'linked,club_only,ca_only,club_only')
  const linked = page.locator('[data-testid="fixture"][data-state="linked"]')
  check('a linked fixture shows BOTH copies and how the review sees it', (await linked.locator('[data-testid="side"]').count()) === 2 && (await linked.innerText()).toLowerCase().includes('scores agree'))
  check('and opens the side-by-side compare', (await linked.locator('[data-testid="open-compare"]').getAttribute('href')) === `/admin/card-review/match/${ML}`)
  check('a fixture the scan suggested a pair for says so, with a way to review it', (await page.locator('[data-testid="candidate"]').count()) === 2 && (await page.locator('[data-testid="to-doubles"]').count()) === 2)
  check('the link button is off until a club card and a Cricket Australia match are ticked', await page.isDisabled('[data-testid="link-picked"]'))
  const picks = page.locator('[data-testid="pick"]')
  await picks.nth(0).check()   // club_only MA
  await picks.nth(2).check()   // club_only MC  (two club cards)
  check('two club scorecards cannot be linked to each other', await page.isDisabled('[data-testid="link-picked"]'))
  await picks.nth(2).uncheck()
  await picks.nth(1).check()   // ca_only GA
  check('one club scorecard and one Cricket Australia match can', !(await page.isDisabled('[data-testid="link-picked"]')))
  await page.screenshot({ path: SHOTS + 'card_review_find_1440.png', fullPage: true })
  await page.click('[data-testid="link-picked"]')
  await page.waitForTimeout(400)
  const link = posts(calls, /doubles\/link/)
  check('linking is ONE POST with exactly the two ticked', link.length === 1 && JSON.parse(link[0].body).match_id === MA && JSON.parse(link[0].body).game_id === GA, JSON.stringify(link.map(l => l.body)))
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
  const narrow = await open(browser, 390, '/admin/card-review/find?player=Ritchie')
  await narrow.page.waitForSelector('[data-testid="fixture"]', { timeout: 15000 })
  check('no horizontal overflow at 390px', (await overflow(narrow.page)) <= 0, String(await overflow(narrow.page)))
  await narrow.page.screenshot({ path: SHOTS + 'card_review_find_390.png', fullPage: true })
  await narrow.ctx.close()
}

// ── the bulk fix ───────────────────────────────────────────────────────────────────────────────
{
  console.log('\n-- fix the strong ones --')
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review/doubles')
  await page.waitForSelector('[data-testid="bulk-fix"]', { timeout: 15000 })
  await page.click('[data-testid="bulk-fix"]')
  await page.waitForSelector('[data-testid="doubles-bulk-modal"]')
  await page.waitForSelector('[data-testid="bulk-relink"]')
  check('it opens a preview, not an action', posts(calls, /doubles\/bulk$/).length === 0)
  check('the preview says how many wrong links and how many unlinked pairs', (await page.locator('[data-testid="bulk-relink"]').innerText()).startsWith('1') && (await page.locator('[data-testid="bulk-link"]').innerText()).startsWith('2'))
  check('and that nothing is deleted', (await page.locator('[data-testid="doubles-bulk-modal"]').innerText()).includes('Nothing is deleted'))
  check('Fix stays disabled until the sample has been looked at', await page.isDisabled('[data-testid="doubles-bulk-apply"]'))
  await page.check('[data-testid="doubles-bulk-ack"]')
  check('and unlocks when ticked', !(await page.isDisabled('[data-testid="doubles-bulk-apply"]')))
  await page.screenshot({ path: SHOTS + 'card_review_doubles_bulk_1440.png', fullPage: true })
  await page.click('[data-testid="doubles-bulk-apply"]')
  await page.waitForTimeout(500)
  check('one POST goes to /doubles/bulk', posts(calls, /doubles\/bulk$/).length === 1)
  check('and the list is asked for again with a fresh scan', gets(calls, /card-review\/doubles\?/).some(c => new URL(c.url).searchParams.get('fresh') === 'true'))
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── a mismatched pair on the compare page ──────────────────────────────────────────────────────
{
  console.log('\n-- the compare page for a card linked to the wrong game --')
  const { ctx, page, calls, errors } = await open(browser, 1440, `/admin/card-review/match/${MR}`)
  await page.waitForSelector('[data-testid="pairing-warning"]', { timeout: 15000 }).catch(async e => { console.log('PAGEERRORS', errors, (await page.locator('body').innerText()).slice(0, 400)); throw e })
  const warn = (await page.locator('[data-testid="pairing-warning"]').innerText()).toLowerCase()
  check('it says the two cards are probably not the same match, with the evidence', warn.includes('not the same match') && warn.includes('only 0 of 11 batters'))
  check('and no longer claims the cards agree on every figure', (await page.locator('body').innerText()).toLowerCase().includes('agree on every figure') === false && (await page.locator('[data-testid="diff-note"]').count()) === 0)
  await page.waitForSelector('[data-testid="candidates"]', { timeout: 8000 })
  check('the better match is looked for at once, without a click', gets(calls, /matches\/[^/]+\/candidates/).length === 1)
  check('and offered with its evidence', (await page.locator('[data-testid="candidates"]').innerText()).toLowerCase().includes('10 of 11 batters in common'))
  check('choosing which card the site shows is switched off, and says why', (await page.isDisabled('[data-testid="choose-ca"]')) && (await page.isDisabled('[data-testid="choose-club"]')) && (await page.locator('[data-testid="choices-off"]').count()) === 1)
  await page.screenshot({ path: SHOTS + 'card_review_compare_mismatch_1440.png', fullPage: true })
  await page.locator('[data-testid="candidates"] [data-testid="relink"]').click()
  await page.waitForTimeout(400)
  const rl = posts(calls, /matches\/[^/]+\/relink/).filter(c => c.url.includes(MR))
  check('Re-link is ONE POST to this card with the right game', rl.length === 1 && JSON.parse(rl[0].body).game_id === GR, JSON.stringify(rl.map(r => r.body)))
  check('and the page loads the card again', gets(calls, /card-review\/matches\/[^/?]+$/).filter(c => c.url.includes(MR)).length >= 2)
  await page.click('[data-testid="pair-ok"]')
  await page.waitForTimeout(300)
  check('Looks right is ONE POST', posts(calls, /matches\/[^/]+\/pair-ok/).length === 1)
  await page.click('[data-testid="unlink"]')
  await page.waitForURL(/card-review\/pairing$/, { timeout: 8000 })
  check('Unlink is ONE POST and leaves for the pairing list, since the card is no longer paired', posts(calls, /matches\/[^/]+\/unlink/).length === 1 && page.url().endsWith('/admin/card-review/pairing'))
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
  const narrow = await open(browser, 390, `/admin/card-review/match/${MR}`)
  await narrow.page.waitForSelector('[data-testid="pairing-warning"]', { timeout: 15000 })
  check('no horizontal overflow at 390px', (await overflow(narrow.page)) <= 0, String(await overflow(narrow.page)))
  await narrow.ctx.close()
}

// ── recent changes ─────────────────────────────────────────────────────────────────────────────
{
  console.log('\n-- recent changes: every change, each with its undo --')
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review/history')
  await page.waitForSelector('[data-testid="change"]', { timeout: 15000 })
  check('every change is a row', (await page.locator('[data-testid="change"]').count()) === 4)
  const text = (await page.locator('[data-testid="history-table"]').innerText()).toLowerCase()
  check('each says what happened, in plain words', text.includes('said the suggested game is not the right one') && text.includes('unlinked: said these are two different matches') && text.includes('linked the club scorecard'))
  check('a batch change is marked as one', (await page.locator('[data-testid="change"][data-id="7"]').innerText()).toLowerCase().includes('batch'))
  check('a change that was undone says so and has no button', (await page.locator('[data-testid="change"][data-id="6"]').innerText()).toLowerCase().includes('undone') && (await page.locator('[data-testid="change"][data-id="6"] [data-testid="undo-change"]').count()) === 0)
  check('an older change to a card that has a newer one says why it cannot be undone', (await page.locator('[data-testid="change"][data-id="7"]').innerText()).toLowerCase().includes('replaced by a newer change') && (await page.locator('[data-testid="change"][data-id="7"] [data-testid="undo-change"]').count()) === 0)
  check('the "different matches" answer offers Put back, the others Undo',
    (await page.locator('[data-testid="change"][data-id="9"] [data-testid="undo-change"]').innerText()) === 'Put back' && (await page.locator('[data-testid="change"][data-id="8"] [data-testid="undo-change"]').innerText()) === 'Undo')
  await page.screenshot({ path: SHOTS + 'card_review_history_1440.png', fullPage: true })
  await page.click('[data-testid="change"][data-id="9"] [data-testid="undo-change"]')
  await page.waitForTimeout(400)
  const rs = posts(calls, /doubles\/restore/)
  check('Put back is ONE POST naming the card, the other game and the kind', rs.length === 1 && JSON.parse(rs[0].body).match_id === MR && JSON.parse(rs[0].body).other_id === GR && JSON.parse(rs[0].body).kind === 'relink', JSON.stringify(rs.map(r => r.body)))
  await page.click('[data-testid="change"][data-id="8"] [data-testid="undo-change"]')
  await page.waitForTimeout(400)
  const un = posts(calls, /matches\/[^/]+\/undo/)
  check('Undo is ONE POST to that card, even though the card is no longer paired', un.length === 1 && un[0].url.includes(MA))
  check('the list is asked for again after each', gets(calls, /card-review\/history/).length >= 3)
  const n = calls.length
  await page.click('[data-testid="h-undoable"]')
  await page.waitForTimeout(400)
  check('"Can be undone" asks for just those', gets(calls.slice(n), /card-review\/history/).some(c => new URL(c.url).searchParams.get('only') === 'undoable'))
  check('and shows only them', (await page.locator('[data-testid="change"]').count()) === 2)
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
  for (const path of ['/admin/card-review', '/admin/card-review/doubles', '/admin/card-review/find', '/admin/card-review/differ']) {
    const p = await open(browser, 1440, path)
    await p.page.waitForSelector('[data-testid="history-link"]', { timeout: 15000 })
    check(`${path} links to Recent changes`, (await p.page.getAttribute('[data-testid="history-link"]', 'href')) === '/admin/card-review/history')
    await p.ctx.close()
  }
  const unl = await open(browser, 1440, '/admin/card-review/doubles?player=Unlinked')
  await unl.page.click('[data-testid="shown-dismissed"]')
  await unl.page.waitForSelector('[data-testid="restore"]', { timeout: 8000 })
  check('a pair dismissed by unlinking says so and offers to link it again', (await unl.page.locator('[data-testid="restore"]').innerText()).includes('Undo the unlink'))
  await unl.ctx.close()
  const narrow = await open(browser, 390, '/admin/card-review/history')
  await narrow.page.waitForSelector('[data-testid="change"]', { timeout: 15000 })
  check('no horizontal overflow at 390px', (await overflow(narrow.page)) <= 0, String(await overflow(narrow.page)))
  await narrow.page.screenshot({ path: SHOTS + 'card_review_history_390.png', fullPage: true })
  await narrow.ctx.close()
}

// ── typeahead and the season dropdown ──────────────────────────────────────────────────────────
{
  console.log('\n-- suggestions and the season dropdown --')
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review/doubles')
  await page.waitForSelector('[data-testid="match-filters"]', { timeout: 15000 })
  await page.waitForTimeout(500)
  await page.fill('[data-testid="f-player"]', 'richie')
  await page.waitForSelector('[data-testid="suggestion"]', { timeout: 5000 })
  const sug = await page.locator('[data-testid="suggestion"]').allInnerTexts()
  check('a misspelt surname still offers the player', sug.includes('Ritchie, Peter') && sug.includes('Ritchie, Rod') && !sug.includes('Hind, Darren'), sug.join(' | '))
  check('and says these are the closest matches', (await page.locator('[data-testid="f-player-list"]').innerText()).toLowerCase().includes('closest matches'))
  const firstOffered = sug[0]
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Enter')
  check('the keyboard picks the first one offered', (await page.inputValue('[data-testid="f-player"]')) === firstOffered, `${await page.inputValue('[data-testid="f-player"]')} v ${firstOffered}`)
  check('and the list closes', (await page.locator('[data-testid="suggestion"]').count()) === 0)
  await page.fill('[data-testid="f-q"]', 'warnbo')
  await page.waitForSelector('[data-testid="suggestion"]')
  await page.locator('[data-testid="suggestion"]').first().click()
  check('a click picks too (the list is not inside a label)', (await page.inputValue('[data-testid="f-q"]')) === 'Warnbro Knights')
  await page.click('[data-testid="f-grade"]')
  await page.waitForSelector('[data-testid="f-grade-list"]')
  check('the grade box lists every grade on focus', (await page.locator('[data-testid="f-grade-list"] [data-testid="suggestion"]').count()) === 3)
  await page.locator('[data-testid="f-grade-list"] [data-testid="suggestion"]').nth(1).click()
  check('a grade can be picked', (await page.inputValue('[data-testid="f-grade"]')) === 'B Grade')
  const seasons = await page.locator('[data-testid="f-season"] option').allInnerTexts()
  check('there is a season dropdown, with the club\'s seasons', seasons.join('|') === 'Any season|Summer 2005/06|Summer 2004/05', seasons.join('|'))
  await page.selectOption('[data-testid="f-season"]', 'Summer 2005/06')
  const n = calls.length
  await page.click('[data-testid="f-apply"]')
  await page.waitForTimeout(600)
  const q = new URL(gets(calls.slice(n), /card-review\/doubles\?/).pop().url).searchParams
  check('searching sends all of it', q.get('player') === firstOffered && q.get('q') === 'Warnbro Knights' && q.get('grade') === 'B Grade' && q.get('season') === 'Summer 2005/06', [...q.entries()].join('&'))
  check('and the season rides in the address bar', page.url().includes('season=Summer'))
  check('Find a match carries the season too', (await page.getAttribute('[data-testid="find-link"]', 'href')).includes('season='))
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
  const lst = await open(browser, 1440, '/admin/card-review/differ')
  await lst.page.waitForSelector('[data-testid="match-filters"]', { timeout: 15000 })
  check('every step has the season dropdown too', (await lst.page.locator('[data-testid="f-season"]').count()) === 1)
  await lst.page.waitForTimeout(500)
  const l1 = gets(lst.calls, /card-review\/matches\?/).length
  await lst.page.waitForTimeout(1500)
  check('a step list loads once and stays quiet', gets(lst.calls, /card-review\/matches\?/).length === l1 && l1 <= 2, String(l1))
  await lst.ctx.close()
  const fnd = await open(browser, 1440, '/admin/card-review/find?player=Ritchie')
  await fnd.page.waitForSelector('[data-testid="fixture"]', { timeout: 15000 })
  const f1 = gets(fnd.calls, /card-review\/find\?/).length
  await fnd.page.waitForTimeout(1500)
  check('Find a match loads once and stays quiet', gets(fnd.calls, /card-review\/find\?/).length === f1 && f1 <= 2, String(f1))
  await fnd.ctx.close()
}

// ── two cards on each other's games ────────────────────────────────────────────────────────────
{
  console.log('\n-- a swap: two cards each on the other\'s game --')
  const { ctx, page, calls, errors } = await open(browser, 1440, '/admin/card-review/doubles', { swap: true })
  await page.waitForSelector('[data-testid="double-card"][data-kind="swap"]', { timeout: 15000 })
  const card = page.locator('[data-testid="double-card"][data-kind="swap"]')
  check('the filter offers swapped links with their count', (await page.locator('[data-testid="k-swap"]').innerText()).includes('1'))
  check('the card says where it is now and that none of its batters are there', (await card.locator('[data-testid="current-link"]').innerText()).includes("0 of this card's 11 batters"))
  const part = await card.locator('[data-testid="swap-partner"]').innerText()
  check('it names the other card and the game that card would move to', part.includes('D grade v Safety Bay') && part.includes('D Grade v Safety Bay Cricket Club'), part)
  check('it offers a swap, not a link or a move', (await card.locator('[data-testid="swap"]').count()) === 1 && (await card.locator('[data-testid="link"]').count()) === 0 && (await card.locator('[data-testid="relink"]').count()) === 0)
  await page.screenshot({ path: SHOTS + 'card_review_doubles_swap_1440.png', fullPage: true })
  await card.locator('[data-testid="swap"]').click()
  await page.waitForTimeout(400)
  const sw = posts(calls, /doubles\/swap/)
  check('Swap is ONE POST naming the card, the other card and the game', sw.length === 1 && JSON.parse(sw[0].body).match_id === MS && JSON.parse(sw[0].body).partner_id === MT && JSON.parse(sw[0].body).game_id === GS, JSON.stringify(sw.map(c => c.body)))
  check('and nothing else was written', posts(calls, /doubles\/(link|dismiss)|relink/).length === 0)
  check('the list is asked for again with a fresh scan', gets(calls, /card-review\/doubles\?/).some(c => new URL(c.url).searchParams.get('fresh') === 'true'))
  await card.locator('[data-testid="dismiss"]').click()
  await page.waitForTimeout(300)
  const dis = posts(calls, /doubles\/dismiss/)
  check('Different matches on a swap is recorded against the game it would move to', dis.length === 1 && JSON.parse(dis[0].body).kind === 'relink' && JSON.parse(dis[0].body).other_id === GS, JSON.stringify(dis.map(c => c.body)))
  await page.click('[data-testid="bulk-fix"]')
  await page.waitForSelector('[data-testid="bulk-swap"]')
  check('the bulk preview counts the swaps', (await page.locator('[data-testid="bulk-swap"]').innerText()).startsWith('2'))
  check('and the sample says what it would do to a swap', (await page.locator('[data-testid="doubles-bulk-modal"]').innerText()).includes('Swap two links'))
  check('the button counts all three', (await page.locator('[data-testid="doubles-bulk-apply"]').innerText()).includes('5'))
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
  const n = await open(browser, 390, '/admin/card-review/doubles', { swap: true })
  await n.page.waitForSelector('[data-testid="double-card"][data-kind="swap"]', { timeout: 15000 })
  check('no horizontal overflow at 390px', (await overflow(n.page)) <= 1, String(await overflow(n.page)))
  await n.page.screenshot({ path: SHOTS + 'card_review_doubles_swap_390.png', fullPage: true })
  await n.ctx.close()
}

await browser.close()
console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
process.exit(FAIL.length ? 1 : 0)
