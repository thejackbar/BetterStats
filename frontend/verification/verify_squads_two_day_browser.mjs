// Drives the real BetterSelect Squads board in Chromium with the API stubbed at
// the network layer.
//
// Reported (Oct 2026): tapping a player's dot on a squad whose next game is a
// two-day one asked about ONE date ("Sat 24 Oct @ Bedford Morley 2nd XI") with
// the four one-day buttons. A two-day game has two weeks and must ask which of
// them the player can do: both, week 1 only, week 2 only, or neither.
//
// The stub has a two-day squad (1st XI, 24 and 31 Oct style dates) and a one-day
// squad (3rd XI). Checks: the column names both weeks; the card is judged on
// both (least favourable) and a player free one week and away the other is DRAWN
// in the half colour; the dot opens the four quick answers; each answer writes
// exactly one request per week with the right statuses; the one-day squad keeps
// the plain four-button window and one write; 390px does not overflow.
//
//   APP_URL=http://localhost:4173 node verify_squads_two_day_browser.mjs
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
const WK1 = plusDays(6)
const WK2 = plusDays(13)
const iso = (daysAgo) => { const d = new Date(); d.setDate(d.getDate() - daysAgo); return d.toISOString().slice(0, 10) }

const FIRSTS = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'   // the two-day squad
const THIRDS = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'   // a one-day squad

const P = (id, name, squads, extra) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null,
  hero_photo_url: null, gender: null, is_player: true, player_role: null,
  is_overseas: false, overseas_country: null, batting_hand: null, bowling_action: null,
  bowling_type: null, is_opening_batsman: false, skill_positions: [], status: 'active',
  is_public: true, is_financial_override: null, trained_override: null,
  squad_team_id: squads[0] || null, squad_team_ids: squads, last_played: iso(20), age: null, ...extra,
})
const PLAYERS = [
  P('p-alice', 'Alice, Anna', [FIRSTS]),   // week 1 yes, week 2 no: half available
  P('p-bob', 'Bob, Barry', [FIRSTS]),      // no answer at all
  P('p-cat', 'Cat, Cara', [THIRDS]),       // one-day squad
  P('p-dan', 'Dan, Dave', [FIRSTS]),       // away week 1, no answer week 2
  P('p-eve', 'Eve, Ella', [FIRSTS]),       // free week 1, maybe week 2
  P('p-fay', 'Fay, Fran', [FIRSTS]),       // away week 1, free week 2 (the reported pair with Dan)
]
const TEAMS = [
  { id: FIRSTS, name: '1st XI', short_name: '1s', sequence: 1, is_active: true, grade_id: 'g1', grade_name: 'Two Day' },
  { id: THIRDS, name: '3rd XI', short_name: '3s', sequence: 3, is_active: true, grade_id: 'g3', grade_name: 'Saturday 3s' },
]
const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin',
  organisation_id: 'org-1', club_slug: 'verify-cc', capabilities: [],
  entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
const MATRIX = {
  dates: [
    { date: WK1, fixtures: [
      { id: 'f-2d', opponent_name: 'Bedford Morley', home_away: 'AWAY', role: 'day1', two_day: true, day1: WK1, day2: WK2 },
      { id: 'f-3', opponent_name: 'Willetton 3s', home_away: 'HOME', role: 'single', two_day: false },
    ] },
    { date: WK2, fixtures: [{ id: 'f-2d', opponent_name: 'Bedford Morley', home_away: 'AWAY', role: 'day2', two_day: true, day1: WK1, day2: WK2 }] },
  ],
  players: [], all_squads: [], dormancy_months: 24, rules: { active: false, applied: [] },
  availability: {
    'p-alice': { [WK1]: { status: 'AVAILABLE', source: 'admin' }, [WK2]: { status: 'UNAVAILABLE', source: 'admin' } },
    'p-cat': { [WK1]: { status: 'AVAILABLE', source: 'admin' } },
    'p-dan': { [WK1]: { status: 'UNAVAILABLE', source: 'admin' } },
    'p-eve': { [WK1]: { status: 'AVAILABLE', source: 'admin' }, [WK2]: { status: 'MAYBE', source: 'admin' } },
    'p-fay': { [WK1]: { status: 'UNAVAILABLE', source: 'admin' }, [WK2]: { status: 'AVAILABLE', source: 'admin' } },
  },
  squad_next: {
    [FIRSTS]: { date: WK1, end_on: WK2, fixture_id: 'f-2d', opponent_name: 'Bedford Morley', label: null, home_away: 'AWAY', scope: 'squad' },
    [THIRDS]: { date: WK1, end_on: null, fixture_id: 'f-3', opponent_name: 'Willetton 3s', label: null, home_away: 'HOME', scope: 'squad' },
  },
}

const writes = []
async function stub(page, matrix = MATRIX, weekNames = null) {
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = req.url()
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.includes('/auth/me')) return json(ME)
    if (/\/availability\/config/.test(url)) return json(weekNames ? { allow_maybe: true, week_names: weekNames, squads: [] } : {})
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

const readColumns = (page) => page.evaluate(() => {
  const out = {}
  for (const card of document.querySelectorAll('.pb-card')) {
    const title = card.querySelector('.font-display')
    if (!title) continue
    const head = title.textContent.trim()
    const line = card.querySelector('[data-next-game]')
    const rows = {}
    for (const row of card.querySelectorAll('[draggable="true"]')) {
      const name = (row.querySelector('[data-card-name]') || row.querySelector('.flex-1'))?.textContent.trim()
      const dot = row.querySelector('[data-avail-dot] span, span.inline-flex span')
      const flag = row.querySelector('[data-week-flag]')
      rows[name] = { dot: dot?.getAttribute('style') || '', flag: flag?.textContent.trim() || '', flagStyle: flag?.getAttribute('style') || '' }
    }
    out[head] = { line: line?.textContent.trim() || null, rows }
  }
  return out
})
const colour = (s) => (/pb-half-w1/.test(s) ? 'HALF_W1' : /pb-half-w2/.test(s) ? 'HALF_W2' : /pb-positive/.test(s) ? 'AVAILABLE'
  : /pb-red/.test(s) ? 'UNAVAILABLE' : /pb-amber/.test(s) ? 'MAYBE' : /pb-faintest/.test(s) ? 'NO_RESPONSE' : '?')
const dayWord = (d) => new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

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
  const firsts = cols['1s'] || cols['1st XI'], thirds = cols['3s'] || cols['3rd XI']
  check('both squad columns render', !!(firsts && thirds), Object.keys(cols).join(' | '))

  // The column says it is a two-day game and names both weeks.
  check('two-day column names both weeks',
    (firsts?.line || '').includes(dayWord(WK1)) && (firsts?.line || '').includes(dayWord(WK2)) && /2 days/.test(firsts?.line || ''), firsts?.line)
  check('control: the one-day column names one date only',
    (thirds?.line || '').includes(dayWord(WK1)) && !(thirds?.line || '').includes(dayWord(WK2)) && !/2 days/.test(thirds?.line || ''), thirds?.line)

  // Judged on both weeks. Alice is in for week 1 and out for week 2: drawn half.
  check('Alice (week 1 yes, week 2 no) is drawn in the half colour, not plain available',
    colour(firsts?.rows['Alice, Anna']?.dot || '') === 'HALF_W1', firsts?.rows['Alice, Anna']?.dot)
  check('Bob (no answer for either week) shows no response',
    colour(firsts?.rows['Bob, Barry']?.dot || '') === 'NO_RESPONSE', firsts?.rows['Bob, Barry']?.dot)
  check('control: Cat in the one-day squad reads her one date (available)',
    colour(thirds?.rows['Cat, Cara']?.dot || '') === 'AVAILABLE', thirds?.rows['Cat, Cara']?.dot)

  // One vocabulary: the same words are always the same colour as the dot. Dan
  // and Fay are both "away week 1" but only Fay is free week 2, so they read
  // differently ("W1 OUT" red, "W2 ONLY" in the half colour), never the same
  // words in two colours.
  const rowsF = firsts?.rows || {}
  check('Alice (free W1, away W2) reads "W1 ONLY"', rowsF['Alice, Anna']?.flag === 'W1 ONLY', rowsF['Alice, Anna']?.flag)
  check('Fay (away W1, free W2) reads "W2 ONLY"', rowsF['Fay, Fran']?.flag === 'W2 ONLY', rowsF['Fay, Fran']?.flag)
  check('Dan (away W1, no answer W2) reads "W1 OUT"', rowsF['Dan, Dave']?.flag === 'W1 OUT', rowsF['Dan, Dave']?.flag)
  check('Eve (free W1, maybe W2) reads "W2 ?"', rowsF['Eve, Ella']?.flag === 'W2 ?', rowsF['Eve, Ella']?.flag)
  check('Bob (no answers) has no flag', !rowsF['Bob, Barry']?.flag)
  const same = (r) => colour(r.dot) === colour(r.flagStyle)
  check('every flag is the colour of its own dot', ['Alice, Anna', 'Fay, Fran', 'Dan, Dave', 'Eve, Ella'].every((n) => same(rowsF[n])),
    JSON.stringify(['Alice, Anna', 'Fay, Fran', 'Dan, Dave', 'Eve, Ella'].map((n) => [n, colour(rowsF[n].dot), colour(rowsF[n].flagStyle)])))
  check('Dan is red and Fay is the half colour (not the same)', colour(rowsF['Dan, Dave'].dot) === 'UNAVAILABLE' && colour(rowsF['Fay, Fran'].dot) === 'HALF_W2')
  // "Order: by availability" (the default) leads with the players free ONE week of
  // the two-day game: they are nearly a yes and need a decision. The rest keep the
  // combined answer, so Dan (away week 1, no answer week 2) is not lifted.
  const order = Object.keys(firsts.rows)
  check('by availability: the two half-available players lead (Alice, Fay)',
    order.slice(0, 2).sort().join('|') === 'Alice, Anna|Fay, Fran', order.join(' | '))
  check('by availability: the rest keep the combined order (Eve maybe, Bob none, Dan out)',
    order.slice(2).join('|') === 'Eve, Ella|Bob, Barry|Dan, Dave', order.join(' | '))
  check('control: the one-day squad has no week flags', Object.values(thirds?.rows || {}).every((r) => !r.flag))

  // The window: four quick answers for the two-day squad.
  const card = (re) => page.locator('.pb-card', { has: page.locator('.font-display', { hasText: re }) }).first()
  // Cards sort by availability, so open one by NAME.
  const dot = (squad, name) => card(squad).locator('[draggable="true"]', { hasText: name }).locator('[data-avail-dot]').first()
  const dlg = page.locator('[role="dialog"]')
  await dot(/^1s$/, 'Alice').click()
  const head = (await dlg.innerText()).toLowerCase()
  check('modal says it is a two-day game and names the opponent', head.includes('two-day game') && head.includes('bedford morley'), head.slice(0, 160))
  check('modal has the four quick answers', (await dlg.locator('[data-week-pattern]').count()) === 4)
  const labels = await dlg.locator('[data-week-pattern]').allInnerTexts()
  check('quick answers read Both weeks, W1 Only, W2 Only, Not available',
    JSON.stringify(labels.map((l) => l.trim())) === JSON.stringify(['Both weeks', 'W1 Only', 'W2 Only', 'Not available']), JSON.stringify(labels))
  check('the week rows are still there for a Maybe or one week at a time', (await dlg.locator('[data-avail-row]').count()) === 3)
  if (SHOT) await page.screenshot({ path: `${SHOT}/squads-two-day-modal.png` })

  const lastWrites = async (n, pick) => {
    const before = writes.length
    await pick()
    await page.waitForTimeout(400)
    return writes.slice(before, before + n + 1)
  }
  const sameWrites = (got, want) => got.length === want.length
    && want.every((w) => got.some((g) => g.date === w.date && g.status === w.status && g.player_id === 'p-bob'))

  await dlg.locator('[aria-label="Close"]').click()

  // Bob, Both weeks: exactly two writes, both available.
  await dot(/^1s$/, 'Bob').click()
  let w = await lastWrites(2, () => dlg.locator('[data-week-pattern="both"]').click())
  check('Both weeks: two writes, week 1 and week 2 AVAILABLE', sameWrites(w, [{ date: WK1, status: 'AVAILABLE' }, { date: WK2, status: 'AVAILABLE' }]), JSON.stringify(w))
  cols = await readColumns(page)
  check('Bob now draws available (both weeks, straight away)', colour(cols['1s']?.rows['Bob, Barry']?.dot || '') === 'AVAILABLE', cols['1s']?.rows['Bob, Barry']?.dot)

  // Week 1 only.
  await dot(/^1s$/, 'Bob').click()
  w = await lastWrites(2, () => dlg.locator('[data-week-pattern="w1"]').click())
  check('Week 1 only: week 1 AVAILABLE and week 2 UNAVAILABLE', sameWrites(w, [{ date: WK1, status: 'AVAILABLE' }, { date: WK2, status: 'UNAVAILABLE' }]), JSON.stringify(w))
  cols = await readColumns(page)
  check('Bob now draws the week 1 half colour', colour(cols['1s']?.rows['Bob, Barry']?.dot || '') === 'HALF_W1')

  // Week 2 only.
  await dot(/^1s$/, 'Bob').click()
  w = await lastWrites(2, () => dlg.locator('[data-week-pattern="w2"]').click())
  check('Week 2 only: week 1 UNAVAILABLE and week 2 AVAILABLE', sameWrites(w, [{ date: WK1, status: 'UNAVAILABLE' }, { date: WK2, status: 'AVAILABLE' }]), JSON.stringify(w))
  cols = await readColumns(page)
  check('Bob now draws the week 2 half colour', colour(cols['1s']?.rows['Bob, Barry']?.dot || '') === 'HALF_W2')

  // Not available.
  await dot(/^1s$/, 'Bob').click()
  w = await lastWrites(2, () => dlg.locator('[data-week-pattern="none"]').click())
  check('Not available: both weeks UNAVAILABLE', sameWrites(w, [{ date: WK1, status: 'UNAVAILABLE' }, { date: WK2, status: 'UNAVAILABLE' }]), JSON.stringify(w))
  cols = await readColumns(page)
  check('Bob now draws unavailable', colour(cols['1s']?.rows['Bob, Barry']?.dot || '') === 'UNAVAILABLE')

  // A Maybe for one week through the week rows: one write, that date only.
  await dot(/^1s$/, 'Bob').click()
  w = await lastWrites(1, () => dlg.locator(`[data-avail-row="${WK2}"] [data-pick="MAYBE"]`).click())
  check('Week 2 row Maybe: one write, week 2 only', sameWrites(w, [{ date: WK2, status: 'MAYBE' }]), JSON.stringify(w))
  cols = await readColumns(page)
  check('Bob (week 1 unavailable, week 2 maybe) is judged on the worse week: unavailable',
    colour(cols['1s']?.rows['Bob, Barry']?.dot || '') === 'UNAVAILABLE')

  // Control: the one-day squad keeps the plain window and one write.
  await dot(/^3s$/, 'Cat').click()
  check('control: one-day squad has no quick answers', (await dlg.locator('[data-week-pattern]').count()) === 0)
  check('control: one-day squad modal names its one date', (await dlg.innerText()).toLowerCase().includes(dayWord(WK1).toLowerCase()))
  const before = writes.length
  await dlg.locator('button', { hasText: 'Maybe' }).click()
  await page.waitForTimeout(300)
  const one = writes.slice(before)
  check('control: one-day squad writes one request on its date', one.length === 1 && one[0].date === WK1 && one[0].status === 'MAYBE', JSON.stringify(one))

  // The club's own week names (A and B) reach every word on the board.
  const named = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  await stub(named, MATRIX, { w1: 'A', w2: 'B' })
  await named.goto(`${BASE}/admin/betterselect/teams`)
  await named.waitForSelector('[draggable="true"]', { timeout: 20000 })
  await named.getByRole('button', { name: 'Expand all' }).click()
  await named.waitForTimeout(500)
  const nc = await readColumns(named)
  const nrows = (nc['1s'] || nc['1st XI'])?.rows || {}
  check('named A/B: Alice reads "A ONLY", Fay "B ONLY", Dan "A OUT", Eve "B ?"',
    nrows['Alice, Anna']?.flag === 'A ONLY' && nrows['Fay, Fran']?.flag === 'B ONLY' && nrows['Dan, Dave']?.flag === 'A OUT' && nrows['Eve, Ella']?.flag === 'B ?',
    JSON.stringify(Object.fromEntries(Object.entries(nrows).map(([k, v]) => [k, v.flag]))))
  await named.locator('.pb-card', { has: named.locator('.font-display', { hasText: /^1s$/ }) }).first()
    .locator('[draggable="true"]', { hasText: 'Bob' }).locator('[data-avail-dot]').first().click()
  const nl = (await named.locator('[role="dialog"] [data-week-pattern]').allInnerTexts()).map((t) => t.trim())
  check('named A/B: quick answers read Both weeks, A Only, B Only, Not available',
    JSON.stringify(nl) === JSON.stringify(['Both weeks', 'A Only', 'B Only', 'Not available']), JSON.stringify(nl))
  const rowTitles = (await named.locator('[role="dialog"] [data-avail-row]').allInnerTexts()).map((t) => t.split('\n')[0].trim())
  check('named A/B: the week rows are Both weeks, A, B', JSON.stringify(rowTitles) === JSON.stringify(['Both weeks', 'A', 'B']), JSON.stringify(rowTitles))
  await named.close()

  // A matrix from before this change (no end_on) still draws one date.
  const old = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const legacy = JSON.parse(JSON.stringify(MATRIX))
  delete legacy.squad_next[FIRSTS].end_on
  await stub(old, legacy)
  await old.goto(`${BASE}/admin/betterselect/teams`)
  await old.waitForSelector('[draggable="true"]', { timeout: 20000 })
  await old.getByRole('button', { name: 'Expand all' }).click()
  await old.waitForTimeout(300)
  const oldCols = await readColumns(old)
  check('legacy payload (no end_on) still renders as a one-date game', !/2 days/.test((oldCols['1s'] || oldCols['1st XI'])?.line || ''), (oldCols['1s'] || {}).line)
  await old.close()

  // 390px: no horizontal overflow, with the two-day window open.
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  const m = await phone.newPage()
  await stub(m)
  await m.goto(`${BASE}/admin/betterselect/teams`)
  await m.waitForSelector('[draggable="true"]', { timeout: 20000 })
  await m.getByRole('button', { name: 'Expand all' }).click()
  await m.waitForTimeout(300)
  await m.locator('.pb-card', { has: m.locator('.font-display', { hasText: /^1s$/ }) }).first().locator('[data-avail-dot]').first().click()
  await m.waitForSelector('[data-week-pattern]')
  const over = await m.evaluate(() => ({ sw: document.documentElement.scrollWidth, screen: window.screen.width }))
  check('390px: page is not wider than the screen with the two-day window open', over.sw <= Math.max(over.screen, 390), JSON.stringify(over))
  const box = await m.locator('[role="dialog"] > div').boundingBox()
  check('390px: the window fits the screen', !!box && box.x >= 0 && box.x + box.width <= 391, JSON.stringify(box))
  if (SHOT) await m.screenshot({ path: `${SHOT}/squads-two-day-modal-390.png` })
  await phone.close()

  check('no page errors', errors.length === 0, errors.slice(0, 3).join(' || '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(2) })
