// The Fielding tab's catch and stumping list, against the REAL PlayerProfile with the API stubbed at the network layer.
//
// Asked for by a club: "a list of his stumpings from first to most recent, showing which bowler each came off, and
// a summary of the bowlers he has taken catches or stumpings off". Asserted:
//   * the request on the wire is /players/<id>/fielding-dismissals with no filter and no season;
//   * the list opens oldest first and numbered from the oldest, the STUMPINGS filter keeps only stumpings, and
//     OLDEST FIRST flips it without renumbering;
//   * a bowler the club has hidden shows as "Not shown" with no link, the row staying on the list;
//   * the by-bowler summary carries each bowler's stumpings, catches, total, first and latest date;
//   * a note says the list holds fewer than the headline ONLY where it does (and is absent where it does not);
//   * 25 rows then "SHOW ALL n";
//   * a reply that arrives late from the player the page has left does not replace the new player's list;
//   * 390px: no horizontal overflow on the page.
//
//   APP_URL=http://localhost:5178 node verify_fielding_pairings_browser.mjs   (serve the production build; see below)
//   cd frontend && npx vite preview --port 5178 --strictPort &
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5178'
const SHOTS = process.env.SHOTS_DIR || ''
const WAIT = process.env.CONTROL ? 6000 : 20000   // the control build has no list: report it, do not hang
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const A = 'a0000000-0000-4000-8000-00000000000a'   // the keeper: list shorter than the headline
const B = 'b0000000-0000-4000-8000-00000000000b'   // list equals the headline: no note
const C = 'c0000000-0000-4000-8000-00000000000c'   // forty rows: pagination
const ORG = '11111111-1111-1111-1111-111111111111'
const BEN = 'e0000000-0000-4000-8000-0000000000e1', CAL = 'e0000000-0000-4000-8000-0000000000e2'
const DAN = 'e0000000-0000-4000-8000-0000000000e3', OLLY = 'e0000000-0000-4000-8000-0000000000e4'

const row = (n, day, kind, bowler, batter, runs) => ({
  wicket_id: n, game_id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`, played_at: day,
  home_team: 'Carmody Club', away_team: 'Rival CC', home_away_known: true, grade_name: 'A Grade',
  season_name: 'Summer 2000/01', innings_number: 2, batter_name: batter, batter_runs: runs,
  bowler_id: bowler ? bowler.id : null, bowler_name: bowler ? bowler.name : null, bowler_hidden: !bowler,
  source: 'api', kind,
})
const bowlerLines = (rows) => {
  const g = new Map()
  for (const r of rows) {
    const k = r.bowler_hidden ? 'hidden' : r.bowler_id
    if (!g.has(k)) g.set(k, { bowler_id: r.bowler_id, bowler_name: r.bowler_name, bowler_hidden: r.bowler_hidden,
      catch: 0, caught_behind: 0, stumping: 0, total: 0, first_played_at: r.played_at, last_played_at: r.played_at })
    const x = g.get(k); x[r.kind]++; x.total++
    if (r.played_at < x.first_played_at) x.first_played_at = r.played_at
    if (r.played_at > x.last_played_at) x.last_played_at = r.played_at
  }
  return [...g.values()].sort((a, b) => b.total - a.total)
}
const payload = (id, rows) => ({
  player_id: id, rows,
  counts: { catch: rows.filter(r => r.kind === 'catch').length, caught_behind: rows.filter(r => r.kind === 'caught_behind').length,
            stumping: rows.filter(r => r.kind === 'stumping').length, total: rows.length },
  by_bowler: bowlerLines(rows),
})
const ben = { id: BEN, name: 'Bowler, Ben' }, cal = { id: CAL, name: 'Quick, Cal' }, dan = { id: DAN, name: 'Spin, Dan' }, olly = { id: OLLY, name: 'Other, Olly' }

const A_ROWS = [
  row(1, '2000-02-05', 'stumping', dan, 'P Old', 4),
  row(2, '2000-10-07', 'stumping', ben, 'J Smith', 12),
  row(3, '2000-10-07', 'caught_behind', cal, 'K Jones', 30),
  row(4, '2000-10-07', 'catch', ben, 'L Brown', 7),
  row(5, '2000-10-21', 'stumping', dan, 'M Green', 15),
  row(6, '2000-10-21', 'stumping', null, 'N Hall', 8),                // a hidden bowler
  row(7, '2000-11-18', 'stumping', cal, 'S Manual', 11),
  row(8, '2000-12-02', 'stumping', ben, 'U Manual', 5),
  row(9, '2000-12-16', 'stumping', cal, 'V Late', 6),
  row(10, '2000-12-23', 'catch', ben, 'W Latest', 2),
]
const B_ROWS = [row(21, '2001-01-06', 'stumping', olly, 'X One', 3), row(22, '2001-01-13', 'stumping', olly, 'Y Two', 9)]
const C_ROWS = Array.from({ length: 40 }, (_, i) =>
  row(100 + i, `2000-${String(1 + Math.floor(i / 28)).padStart(2, '0')}-${String(1 + (i % 28)).padStart(2, '0')}`,
      i < 3 ? 'stumping' : 'catch', i % 2 ? ben : cal, `Batter ${i}`, i))

const headline = (c, s) => ({ total_catches: c, total_catches_wk: 1, total_catches_non_wk: c - 1, total_run_outs: 2, total_stumpings: s, total_dismissals: c + s + 2, games: 30 })
const statsFor = (id, name, fielding) => ({
  player: { id, name, display_name: name, organisation_id: ORG, claimed: null, playhq_id: null },
  career_batting: { games: 20, innings: 19, total_runs: 55, not_outs: 0, high_score: 10, fifties: 0, hundreds: 0, ducks: 0, total_fours: 6, total_sixes: 0 },
  career_bowling: { games: 20, total_wickets: 5 },
  career_fielding: fielding, batting_innings: [], bowling_spells: [],
  grade_scope: { active: false, categories: [], available: [] },
})
const WORLD = {
  [A]: { name: 'Carmody, Ryan', fielding: headline(5, 9), rows: A_ROWS, delay: 0 },   // list: 3 of 5 catches, 7 of 9 stumpings
  [B]: { name: 'Other, Player', fielding: headline(0, 2), rows: B_ROWS, delay: 0 },   // list equals the headline
  [C]: { name: 'Many, Catches', fielding: headline(37, 3), rows: C_ROWS, delay: 0 },  // list equals the headline
}

const newPage = async (browser, viewport, calls, errors, overrides = {}) => {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1 })
  await ctx.addInitScript(() => { localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never')) })
  const page = await ctx.newPage()
  page.on('pageerror', e => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    calls.push(url)
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    for (const id of [A, B, C]) {
      const w = { ...WORLD[id], ...(overrides[id] || {}) }
      if (url.includes(`/players/${id}/stats`)) return json(statsFor(id, w.name, w.fielding))
      if (url.includes(`/players/${id}/fielding-dismissals`)) {
        if (w.delay) await new Promise(r => setTimeout(r, w.delay))
        return json(payload(id, w.rows))
      }
    }
    if (/\/auth\/me/.test(url)) return json({}, 401)
    return json([])
  })
  return { ctx, page }
}

// A click that reports instead of waiting thirty seconds for a control with no such button.
const tap = async (loc) => { if (await loc.count()) { await loc.first().click(); return true } return false }
const openFielding = async (page, id) => {
  await page.goto(`${BASE}/players/${id}`, { waitUntil: 'domcontentloaded' })
  await page.locator('button', { hasText: /^FIELDING$/ }).first().click({ timeout: 20000 })
}
const logTable = (page) => page.locator('table', { has: page.locator('th', { hasText: 'OFF BOWLER' }) })
const logRows = async (page) => logTable(page).locator('tbody tr').evaluateAll(trs =>
  trs.map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.replace(/\s+/g, ' ').trim())))

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = []

  // ── A: the keeper, desktop ──────────────────────────────────────────────
  {
    const calls = []
    const { ctx, page } = await newPage(browser, { width: 1200, height: 1000 }, calls, errors)
    await openFielding(page, A)
    await page.waitForSelector('text=EVERY CATCH AND STUMPING', { timeout: WAIT }).catch(() => null)
    const reqs = calls.filter(u => u.includes('/fielding-dismissals'))
    check('one request for the list, to /players/<id>/fielding-dismissals', reqs.length === 1 && reqs[0].includes(`/players/${A}/fielding-dismissals`), reqs.join('\n'))
    check('no filter and no season on that request (none is picked)', reqs.length === 1 && !reqs[0].includes('?'), reqs[0])

    let rows = await logRows(page)
    check('the list opens at the oldest: #1, 5 Feb, Stumped, off Spin Dan, batter P Old',
      rows[0]?.[0] === '1' && /5 Feb/.test(rows[0]?.[1]) && /Stumped/.test(rows[0]?.[2]) && /Dan/.test(rows[0]?.[3]) && /P Old/.test(rows[0]?.[4]), JSON.stringify(rows[0]))
    check('all ten rows are listed and the last is the most recent (#10, caught, off Ben)',
      rows.length === 10 && rows[9][0] === '10' && /Caught/.test(rows[9][2]) && /Ben/.test(rows[9][3]), JSON.stringify(rows.length) + ' ' + JSON.stringify(rows[9]))
    check('a batter\'s score sits beside the batter', /J Smith · 12/.test(rows[1]?.[4] || ''), JSON.stringify(rows[1]))
    check('the match and grade are on the row', /Carmody Club vs Rival CC/.test(rows[0]?.[5] || '') && /A Grade/.test(rows[0]?.[5] || ''), JSON.stringify(rows[0]))

    const chips = await page.locator('button').evaluateAll(bs => bs.map(b => b.innerText.replace(/\s+/g, ' ').trim()).filter(t => /^(ALL|STUMPINGS|CATCHES|CT \(WK\)) \d+$/.test(t)))
    check('filter chips carry their counts: ALL 10, STUMPINGS 7, CATCHES 2, CT (WK) 1', JSON.stringify(chips) === JSON.stringify(['ALL 10', 'STUMPINGS 7', 'CATCHES 2', 'CT (WK) 1']), JSON.stringify(chips))

    await tap(page.locator('button', { hasText: /^STUMPINGS 7$/ }))
    rows = await logRows(page)
    check('STUMPINGS keeps only the 7 stumpings, numbered 1 to 7 from the oldest',
      rows.length === 7 && rows.every(r => /Stumped/.test(r[2])) && rows.map(r => r[0]).join() === '1,2,3,4,5,6,7', JSON.stringify(rows.map(r => r[0] + r[2])))
    check('the first stumping is the 5 Feb one and the seventh is the 16 Dec one',
      /5 Feb/.test(rows[0]?.[1]) && /16 Dec/.test(rows[6]?.[1]), JSON.stringify([rows[0]?.[1], rows[6]?.[1]]))
    check('a stumping row is the one with the hidden bowler: "Not shown", and it is not a link',
      rows.some(r => /Not shown/.test(r?.[3])) && (await logTable(page).locator('a', { hasText: 'Not shown' }).count()) === 0, JSON.stringify(rows.map(r => r[3])))
    check('a named bowler IS a link to their profile (so the no-link check can fail)',
      (await logTable(page).locator(`a[href="/players/${DAN}"]`).count()) >= 1)

    await tap(page.locator('button', { hasText: /^OLDEST FIRST$/ }))
    rows = await logRows(page)
    check('NEWEST FIRST: the 16 Dec stumping leads and keeps its number, 7', /16 Dec/.test(rows[0]?.[1]) && rows[0]?.[0] === '7' && rows[6]?.[0] === '1', JSON.stringify(rows.map(r => r[0])))
    await tap(page.locator('button', { hasText: /^NEWEST FIRST$/ }))

    const bowlerTable = page.locator('table', { has: page.locator('th', { hasText: /^BOWLER$/ }) })
    const brows = await bowlerTable.locator('tbody tr').evaluateAll(trs => trs.map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.replace(/\s+/g, ' ').trim())))
    const heads = await bowlerTable.locator('thead th').allInnerTexts()
    check('the by-bowler summary heads are BOWLER, STUMPINGS, CATCHES, CT (WK), TOTAL, FIRST, LATEST',
      JSON.stringify(heads.map(h => h.trim())) === JSON.stringify(['BOWLER', 'STUMPINGS', 'CATCHES', 'CT (WK)', 'TOTAL', 'FIRST', 'LATEST']), JSON.stringify(heads))
    const benRow = brows.find(r => /Ben/.test(r[0])) || []
    check('Ben: 2 stumpings, 2 catches, none behind (shown as a dash), total 4, first 7 Oct, latest 23 Dec',
      benRow[1] === '2' && benRow[2] === '2' && benRow[3] === '—' && benRow[4] === '4' && /7 Oct/.test(benRow[5]) && /23 Dec/.test(benRow[6]), JSON.stringify(benRow))
    check('most dismissals first: Ben (4) leads', /Ben/.test(brows[0]?.[0]) && brows[0][4] === '4', JSON.stringify(brows.map(r => r[0] + r[4])))
    check('the hidden bowler is one "Not shown" line, still counted',
      brows.some(r => /Not shown/.test(r[0]) && r[4] === '1'), JSON.stringify(brows.map(r => r[0] + r[4])))

    const body = await page.locator('body').innerText()
    check('the note says what the list holds against the headline: 7 of 9 stumpings and 3 of 5 catches',
      /Listed here: 7 of 9 stumpings and 3 of 5 catches\./.test(body), body.slice(body.indexOf('Listed'), body.indexOf('Listed') + 120))
    check('run outs are explained as absent', /Run outs are not listed/.test(body))
    check('the headline cards are still there above the list', /CATCHES \(WK\)/.test(body) && /STUMPINGS/.test(body))
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/fielding-desktop.png`, fullPage: true })
    await ctx.close()
  }

  // ── A at 390px ──────────────────────────────────────────────────────────
  {
    const calls = []
    const { ctx, page } = await newPage(browser, { width: 390, height: 844 }, calls, errors)
    await openFielding(page, A)
    await page.waitForSelector('text=EVERY CATCH AND STUMPING', { timeout: WAIT }).catch(() => null)
    const dims = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }))
    check('390px: no horizontal overflow on the page', dims.sw <= dims.iw, JSON.stringify(dims))
    const wrap = (await logTable(page).count()) === 0 ? { overflowX: 'no list' } : await logTable(page).first().evaluate(t => { const w = t.parentElement; return { scrolls: w.scrollWidth > w.clientWidth, overflowX: getComputedStyle(w).overflowX } })
    check('390px: the log scrolls inside its own card (overflow-x auto) rather than pushing the page', wrap.overflowX === 'auto' || wrap.overflowX === 'scroll', JSON.stringify(wrap))
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/fielding-390.png`, fullPage: true })
    await ctx.close()
  }

  // ── B: the list equals the headline: no note ────────────────────────────
  {
    const calls = []
    const { ctx, page } = await newPage(browser, { width: 1200, height: 900 }, calls, errors)
    await openFielding(page, B)
    await page.waitForSelector('text=EVERY CATCH AND STUMPING', { timeout: WAIT }).catch(() => null)
    const body = await page.locator('body').innerText()
    check('where the list holds every stumping the headline counts, there is no "Listed here" note', !/Listed here/.test(body))
    check('(and the same page does explain run outs, so the note check is not just an empty page)', /Run outs are not listed/.test(body))
    const chips = await page.locator('button').evaluateAll(bs => bs.map(b => b.innerText.replace(/\s+/g, ' ').trim()).filter(t => /^(ALL|STUMPINGS|CATCHES|CT \(WK\)) \d+$/.test(t)))
    check('with one kind only, the chips are ALL 2 and STUMPINGS 2 (no empty CATCHES chip)', JSON.stringify(chips) === JSON.stringify(['ALL 2', 'STUMPINGS 2']), JSON.stringify(chips))
    await ctx.close()
  }

  // ── C: forty rows, 25 then all ──────────────────────────────────────────
  {
    const calls = []
    const { ctx, page } = await newPage(browser, { width: 1200, height: 900 }, calls, errors)
    await openFielding(page, C)
    await page.waitForSelector('text=EVERY CATCH AND STUMPING', { timeout: WAIT }).catch(() => null)
    check('forty rows: 25 are drawn first', (await logRows(page)).length === 25, String((await logRows(page)).length))
    await tap(page.locator('button', { hasText: /^SHOW ALL 40$/ }))
    check('SHOW ALL 40 draws all forty', (await logRows(page)).length === 40, String((await logRows(page)).length))
    await tap(page.locator('button', { hasText: /^SHOW FEWER$/ }))
    check('SHOW FEWER goes back to 25', (await logRows(page)).length === 25)
    await ctx.close()
  }

  // ── a late reply from the player the page has left ──────────────────────
  {
    const calls = []
    const { ctx, page } = await newPage(browser, { width: 1200, height: 900 }, calls, errors, { [A]: { delay: 2500 } })
    await page.goto(`${BASE}/players/${A}`, { waitUntil: 'domcontentloaded' })
    await page.locator('button', { hasText: /^FIELDING$/ }).first().click({ timeout: 20000 })
    await page.waitForTimeout(600)                                         // A's list is still on its way
    await page.evaluate((id) => { window.history.pushState({}, '', `/players/${id}`); window.dispatchEvent(new PopStateEvent('popstate')) }, B)
    await page.waitForSelector('text=EVERY CATCH AND STUMPING', { timeout: WAIT }).catch(() => null)
    await page.waitForTimeout(3200)                                        // past A's late reply
    const body = await page.locator('body').innerText()
    check("B's list is showing (off Olly), A's late reply did not replace it",
      /Olly/.test(body) && !/J Smith/.test(body) && !/Ben/.test(body), body.slice(0, 160))
    check('both lists were asked for, each for its own player',
      calls.some(u => u.includes(`/players/${A}/fielding-dismissals`)) && calls.some(u => u.includes(`/players/${B}/fielding-dismissals`)))
    await ctx.close()
  }

  check('no page errors anywhere', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run()
