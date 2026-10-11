// Drives the real BetterSelect Squads board in Chromium with the API stubbed at
// the network layer. The report (Oct 2026): availability typed on the Squads
// board for the Saturday 3s landed on the club's next game, a midweek T20.
//
// The stub carries two squads with different next games (T20 on Tuesday, 3rd
// XI on Saturday) and ONE player in both squads whose answer differs per date.
// Checks: each column shows its own date's answer, says which game it is, a tap
// writes to THAT column's date (exact request on the wire), a squad whose grade
// has nothing upcoming says so and offers no edit, and 390px does not overflow.
//
//   APP_URL=http://localhost:4173 node verify_squads_next_game_browser.mjs
//   (serve a production build; never rebuild dist under a running server)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const TUE = plusDays(2)    // the T20
const SAT = plusDays(6)    // the 3rd XI
const iso = (daysAgo) => { const d = new Date(); d.setDate(d.getDate() - daysAgo); return d.toISOString().slice(0, 10) }

const T20 = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
const THIRDS = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
const FOURTHS = 'cccccccc-cccc-cccc-cccc-cccccccccccc'   // grade with nothing upcoming

const P = (id, name, squads, extra) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null,
  hero_photo_url: null, gender: null, is_player: true, player_role: null,
  is_overseas: false, overseas_country: null, batting_hand: null, bowling_action: null,
  bowling_type: null, is_opening_batsman: false, skill_positions: [], status: 'active',
  is_public: true, is_financial_override: null, trained_override: null,
  squad_team_id: squads[0] || null, squad_team_ids: squads, last_played: iso(20), age: null, ...extra,
})
const PLAYERS = [
  P('p-alice', 'Alice, Anna', [THIRDS, T20]),   // in both squads
  P('p-bob', 'Bob, Barry', [THIRDS]),
  P('p-cat', 'Cat, Cara', [FOURTHS]),
]
const TEAMS = [
  { id: THIRDS, name: '3rd XI', short_name: '3s', sequence: 3, is_active: true, grade_id: 'g3', grade_name: 'Saturday 3s' },
  { id: T20, name: 'T20', short_name: 'T20', sequence: 0, is_active: true, grade_id: 'gt20', grade_name: 'T20' },
  { id: FOURTHS, name: '4th XI', short_name: '4s', sequence: 4, is_active: true, grade_id: 'g4', grade_name: 'Saturday 4s' },
]
const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin',
  organisation_id: 'org-1', club_slug: 'verify-cc', capabilities: [],
  entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
const next = (date, opp) => ({ date, fixture_id: 'f-' + date, opponent_name: opp, label: null, home_away: 'HOME', scope: 'squad' })
const MATRIX = {
  dates: [
    { date: TUE, fixtures: [{ id: 'f-t20', opponent_name: 'Jarrah T20', home_away: 'HOME', role: 'single', two_day: false }] },
    { date: SAT, fixtures: [{ id: 'f-3', opponent_name: 'Willetton 3s', home_away: 'HOME', role: 'single', two_day: false }] },
  ],
  players: [], all_squads: [], dormancy_months: 24, rules: { active: false, applied: [] },
  // Alice is OUT for the T20 on Tuesday but IN for the 3s on Saturday. Bob is IN
  // on Tuesday (he is not in the T20 squad) and OUT on Saturday.
  availability: {
    'p-alice': { [TUE]: { status: 'UNAVAILABLE', source: 'admin' }, [SAT]: { status: 'AVAILABLE', source: 'admin' } },
    'p-bob': { [TUE]: { status: 'AVAILABLE', source: 'admin' }, [SAT]: { status: 'UNAVAILABLE', source: 'admin' } },
  },
  squad_next: {
    [THIRDS]: next(SAT, 'Willetton 3s'),
    [T20]: next(TUE, 'Jarrah T20'),
    [FOURTHS]: { date: null, fixture_id: null, opponent_name: null, label: null, home_away: null, scope: 'none' },
  },
}

const writes = []
async function stub(page, matrix = MATRIX) {
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = req.url()
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.includes('/auth/me')) return json(ME)
    if (url.includes('/club-admin/players')) return json(PLAYERS)
    if (url.includes('/availability/matrix')) return json(matrix)
    if (/\/availability(\?|$)/.test(url) && req.method() === 'POST') {
      writes.push(JSON.parse(req.postData() || '{}'))
      return json({ status: 'ok' })
    }
    if (url.includes('/teams/grade-options')) return json({ seasons: [] })
    if (url.match(/\/teams(\?|$)/)) return json(TEAMS)
    if (url.includes('/selection/selected-players')) return json({ player_ids: [] })
    return json({})
  })
}

// Per column: header, the game line, and each player's dot colour.
const readColumns = (page) => page.evaluate(() => {
  const out = {}
  for (const card of document.querySelectorAll('.pb-card')) {
    const title = card.querySelector('.font-display')
    if (!title) continue
    const head = title.textContent.trim()
    const line = card.querySelector('[data-next-game]')
    const rows = {}
    for (const row of card.querySelectorAll('[draggable="true"]')) {
      const name = row.querySelector('.flex-1')?.textContent.trim()
      const dot = row.querySelector('[data-avail-dot] span, span.inline-flex span')
      rows[name] = { dot: dot?.getAttribute('style') || '', editable: !!row.querySelector('[data-avail-dot]') }
    }
    out[head] = { line: line?.textContent.trim() || null, scope: line?.getAttribute('data-next-game') || null, rows }
  }
  return out
})
const colour = (s) => (/pb-positive/.test(s) ? 'AVAILABLE' : /pb-red/.test(s) ? 'UNAVAILABLE' : /pb-amber/.test(s) ? 'MAYBE' : /pb-faintest/.test(s) ? 'NO_RESPONSE' : '?')
const dayWord = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error' && !/Failed to load resource|ERR_CONNECTION|ERR_NAME_NOT_RESOLVED/.test(m.text())) errors.push(m.text())
  })
  await stub(page)
  await page.goto(`${BASE}/admin/betterselect/teams`)
  await page.waitForSelector('[draggable="true"]', { timeout: 20000 })
  await page.getByRole('button', { name: 'Expand all' }).click()
  await page.waitForTimeout(300)

  let cols = await readColumns(page)
  const third = cols['3s'] || cols['3rd XI'], t20 = cols['T20'], fourth = cols['4s'] || cols['4th XI']
  check('all three squad columns render', !!(third && t20 && fourth), Object.keys(cols).join(' | '))

  // The same player, two columns, two dates: Alice is IN in the 3s, OUT in the T20.
  check('3s column reads the 3s game: Alice is available (Saturday)',
    colour(third?.rows['Alice, Anna']?.dot || '') === 'AVAILABLE', third?.rows['Alice, Anna']?.dot)
  check('3s column: Bob is unavailable (Saturday), not the T20 day\'s answer',
    colour(third?.rows['Bob, Barry']?.dot || '') === 'UNAVAILABLE', third?.rows['Bob, Barry']?.dot)
  check('T20 column reads the T20: Alice is unavailable (Tuesday)',
    colour(t20?.rows['Alice, Anna']?.dot || '') === 'UNAVAILABLE', t20?.rows['Alice, Anna']?.dot)

  // Each column says which game it is.
  check('3s header names its game', (third?.line || '').includes(dayWord(SAT)) && (third?.line || '').includes('Willetton 3s'), third?.line)
  check('T20 header names its game', (t20?.line || '').includes(dayWord(TUE)) && (t20?.line || '').includes('Jarrah T20'), t20?.line)

  // A squad whose grade has nothing upcoming says so, shows no answer, offers no edit.
  check('4s: says no upcoming game for the grade', /No upcoming game for this grade/.test(fourth?.line || ''), fourth?.line)
  check('4s: marked as the none scope', fourth?.scope === 'none', fourth?.scope)
  check('4s: Cat shows no response and is not editable',
    colour(fourth?.rows['Cat, Cara']?.dot || '') === 'NO_RESPONSE' && fourth?.rows['Cat, Cara']?.editable === false,
    JSON.stringify(fourth?.rows['Cat, Cara']))

  // The write goes to the date of the column that was tapped, not the club's first date.
  const thirdCard = page.locator('.pb-card', { has: page.locator('.font-display', { hasText: /^3s$/ }) }).first()
  await thirdCard.locator('[data-avail-dot]').first().click()
  // CSS `uppercase` makes innerText come back upper-cased: compare in that casing.
  const modalHead = (await page.locator('[role="dialog"]').innerText()).toLowerCase()
  check('modal names the 3s date, not the T20 day',
    modalHead.includes(dayWord(SAT).toLowerCase()) && !modalHead.includes(dayWord(TUE).toLowerCase()), modalHead.slice(0, 120))
  await page.locator('[role="dialog"] button', { hasText: 'Maybe' }).click()
  await page.waitForTimeout(300)
  const w3 = writes[writes.length - 1]
  check('exact request: POST /availability with the 3s date', !!w3 && w3.date === SAT && w3.status === 'MAYBE' && w3.player_id.startsWith('p-'), JSON.stringify(w3))
  cols = await readColumns(page)
  const row3 = (cols['3s'] || cols['3rd XI'])?.rows
  check('after the write one 3s card is Maybe (optimistic, that date only)',
    Object.values(row3 || {}).some((r) => colour(r.dot) === 'MAYBE'), JSON.stringify(row3))
  check('the T20 column is untouched by that write', colour(cols['T20']?.rows['Alice, Anna']?.dot || '') === 'UNAVAILABLE')

  // And the T20 column writes to Tuesday.
  const t20Card = page.locator('.pb-card', { has: page.locator('.font-display', { hasText: /^T20$/ }) }).first()
  await t20Card.locator('[data-avail-dot]').first().click()
  await page.locator('[role="dialog"] button', { hasText: 'Available' }).first().click()
  await page.waitForTimeout(300)
  const wt = writes[writes.length - 1]
  check('exact request: POST /availability with the T20 date', !!wt && wt.date === TUE && wt.status === 'AVAILABLE', JSON.stringify(wt))

  // A matrix from before this change (no squad_next) still draws, on the club's first date.
  const old = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const { squad_next, ...legacy } = MATRIX
  await stub(old, legacy)
  await old.goto(`${BASE}/admin/betterselect/teams`)
  await old.waitForSelector('[draggable="true"]', { timeout: 20000 })
  await old.getByRole('button', { name: 'Expand all' }).click()
  await old.waitForTimeout(300)
  const oldCols = await readColumns(old)
  check('legacy payload (no squad_next) still renders, every column on the club\'s first date',
    colour((oldCols['3s'] || oldCols['3rd XI'])?.rows['Bob, Barry']?.dot || '') === 'AVAILABLE', JSON.stringify(oldCols['3s']?.rows))
  await old.close()

  // 390px: no horizontal overflow.
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  const m = await phone.newPage()
  await stub(m)
  await m.goto(`${BASE}/admin/betterselect/teams`)
  await m.waitForSelector('[draggable="true"]', { timeout: 20000 })
  await m.getByRole('button', { name: 'Expand all' }).click()
  await m.waitForTimeout(300)
  const over = await m.evaluate(() => ({ sw: document.documentElement.scrollWidth, screen: window.screen.width, iw: window.innerWidth }))
  check('390px: page is not wider than the screen', over.sw <= Math.max(over.screen, 390), JSON.stringify(over))
  if (SHOT) { await m.screenshot({ path: `${SHOT}/squads-next-game-390.png`, fullPage: false }); await page.screenshot({ path: `${SHOT}/squads-next-game-desktop.png` }) }
  await phone.close()

  check('no page errors', errors.length === 0, errors.slice(0, 3).join(' || '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(2) })
