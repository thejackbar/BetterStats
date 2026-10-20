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
const COUNTS = { total: 3, dismissed: 1, by_strength: { strong: 2, likely: 0, possible: 1 }, by_kind: { ca: 2, club: 1 }, formats_differ: 2 }
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

const routes = (page, calls, o = {}) => page.route('**/api/**', async (route) => {
  const req = route.request(), url = req.url(), body = req.postData()
  calls.push({ url, method: req.method(), body })
  const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) {
    return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', club_id: 'org1', entitlements: { modules: ['admin'], status: 'active' } })
  }
  if (/card-review\/overview/.test(url)) return json(o.scanFailed ? { ...OVERVIEW, groups: { ...OVERVIEW.groups, doubles: 0 }, todo: { ...OVERVIEW.todo, doubles: 0 }, doubles: { error: 'The scan for possible doubles failed. Reload to try again.' } } : OVERVIEW)
  if (/card-review\/bulk\/batches/.test(url)) return json({ batches: [] })
  if (/card-review\/find\/options/.test(url)) return json({ seasons: ['Summer 2005/06'], competitions: ['Reserves League'] })
  if (/card-review\/find\?/.test(url)) return json({ total: FIND_ROWS.length, offset: 0, limit: 25, capped: false, rows: FIND_ROWS })
  if (/card-review\/doubles\/(link|dismiss|restore)/.test(url) && req.method() === 'POST') return json({ ok: true, shows: 'ca' })
  if (/card-review\/doubles\?/.test(url)) {
    const sp = new URL(url).searchParams
    const dis = sp.get('shown') === 'dismissed'
    const rows = dis ? DISMISSED : ROWS.filter(r => !sp.get('kind') || r.kind === sp.get('kind'))
    return json({ total: rows.length, offset: 0, limit: 25, seasons: ['Summer 2005/06'], counts: COUNTS, rows })
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
  check('one card per pair', (await page.locator('[data-testid="double-card"]').count()) === 3)
  check('every card draws both copies', (await page.locator('[data-testid="double-card"]').first().locator('[data-testid="side"]').count()) === 2)
  const ev = (await page.locator('[data-testid="evidence"]').first().innerText()).toLowerCase()
  check('the evidence says strength, batters in common, the gap and the opposition', /strong match/i.test(ev) && ev.includes('9 batters in common') && /same day/i.test(ev) && /same opposition/i.test(ev), ev)
  check('two copies under different match types are flagged', /different match types/i.test(ev))
  check('a pair where one card has no batters says so', (await page.locator('[data-testid="evidence"]').nth(1).innerText()).toLowerCase().includes('no batters to compare'))
  check('the formats note counts them', (await page.locator('[data-testid="formats-note"]').innerText()).includes('2'))
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
  check('Put back is ONE POST', res.length === 1 && JSON.parse(res[0].body).match_id === MA)
  check('the screen raised no errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
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

await browser.close()
console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
process.exit(FAIL.length ? 1 : 0)
