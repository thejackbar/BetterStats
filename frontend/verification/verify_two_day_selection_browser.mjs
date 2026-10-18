// Drives the REAL Selection board in Chromium with the API stubbed at the
// network layer.
//
// Reported (Applecross, Oct 2026): a two-day game on 24 and 31 Oct showed only
// "Sat 24 Oct" and registered a player's week 1 answer, ignoring that they were
// unavailable for week 2. Checks, for a two-day fixture: the header names both
// dates; a card whose weeks differ says which week is the problem; the dot
// opens an editor with "Both weeks" and one row per week; a week-2 answer writes
// the week-2 DATE only; "Both weeks" writes both; the card's status follows the
// least favourable week straight away. Control: a one-day fixture has none of
// this, and a player free in both weeks shows no split line.
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_two_day_selection_browser.mjs
import { chromium } from 'playwright'
import { readFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures/selection_same_day.json'), 'utf8'))
const FID = FIX.fixture_id
const PASS = [], FAIL = []
const ok = (name, cond, detail = '') => { (cond ? PASS : FAIL).push(name); console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  none: ' + detail : ''}`) }
const ME = { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' } }

const addDays = (iso, n) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10) }
const WK1 = FIX.payload.fixture.played_on
const WK2 = addDays(WK1, 7)

const payloadFor = (twoDay) => {
  const p = JSON.parse(JSON.stringify(FIX.payload))
  if (twoDay) p.fixture.end_on = WK2
  p.pool = p.pool.map((x) => {
    if (x.display_name === 'Cara Free') {
      return twoDay
        ? { ...x, availability: 'UNAVAILABLE', availability_days: [{ date: WK1, status: 'AVAILABLE' }, { date: WK2, status: 'UNAVAILABLE' }] }
        : { ...x, availability: 'AVAILABLE', availability_days: null }
    }
    if (x.display_name === 'Alex Backtoback') {
      return twoDay
        ? { ...x, availability: 'AVAILABLE', availability_days: [{ date: WK1, status: 'AVAILABLE' }, { date: WK2, status: 'AVAILABLE' }] }
        : { ...x, availability: 'AVAILABLE', availability_days: null }
    }
    return x
  })
  return p
}

const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

const run = async () => {
  mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  for (const twoDay of [true, false]) {
    console.log(`\n# ${twoDay ? 'two-day fixture' : 'control: one-day fixture'}`)
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const page = await ctx.newPage()
    const writes = []
    await page.route('**/api/**', (r) => json(r, {}))
    await page.route(/\/api\/club-admin\/settings$/, (r) => json(r, { player_name_format: 'first_last' }))
    await page.route('**/api/auth/me', (r) => json(r, ME))
    await page.route(/\/api\/availability\/config/, (r) => json(r, { allow_maybe: true }))
    await page.route(/\/api\/selection\/overview(\?.*)?$/, (r) => json(r, { fixtures: [], default_team_size: 11 }))
    await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { source_fixture_id: null, player_ids: [], captain_id: null, wicket_keeper_id: null }))
    await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
    await page.route(new RegExp(`/api/selection/${FID}/draft(\\?.*)?$`), (r) => json(r, { draft: null, version: 0 }))
    await page.route(new RegExp(`/api/selection/${FID}$`), (r) => json(r, { ...payloadFor(twoDay), lineup: [] }))
    await page.route(/\/api\/availability(\/set)?(\?.*)?$/, async (r) => {
      if (r.request().method() === 'POST' || r.request().method() === 'PUT') writes.push(JSON.parse(r.request().postData() || '{}'))
      return json(r, { status: 'ok' })
    })
    await page.goto(`${BASE}/admin/betterselect/select/${FID}`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Cara Free').first().waitFor({ timeout: 20000 })
    await page.waitForTimeout(300)
    const body = async () => (await page.locator('body').innerText()).replace(/\s+/g, ' ')
    const fmt = (iso) => page.evaluate((i) => new Date(i + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }), iso)

    const b0 = await body()
    if (twoDay) {
      ok('header names week 1', b0.includes(await fmt(WK1)))
      ok('header names week 2', b0.includes(await fmt(WK2)), b0.slice(0, 300))
      ok('header says it is a two-day game', /two days/i.test(b0))
      ok('the card for the player away in week 2 says which week (W1 ONLY)', /W1 ONLY/.test(b0), b0.slice(0, 400))
      ok('a player free both weeks shows no split line', (await page.locator('[data-week-split]').count()) === 1)
    } else {
      ok('control: header does not say two days', !/two days/i.test(b0))
      ok('control: no split line anywhere', (await page.locator('[data-week-split]').count()) === 0)
    }
    await page.screenshot({ path: join(SHOTS, `two_day_board_${twoDay ? 'two' : 'one'}.png`) })

    // The dot beside Cara opens the editor.
    const cara = page.locator('div.group.relative.rounded-xl', { hasText: 'Cara Free' }).first()
    await cara.locator('[data-avail-dot]').first().click({ timeout: 3000 }).catch(() => {})
    await page.waitForTimeout(250)
    const editor = await page.locator('[role="dialog"][aria-label="Update availability"]').count()
    ok('the editor opens', editor === 1)
    const twoUi = await page.locator('[data-two-day-avail]').count()
    ok(twoDay ? 'the editor offers both weeks and each week' : 'control: a one-day editor is the plain one', twoDay ? twoUi === 1 : twoUi === 0)
    if (twoDay) {
      ok('three rows: both weeks, week 1, week 2', (await page.locator('[data-avail-row]').count()) === 3)
      await page.screenshot({ path: join(SHOTS, 'two_day_editor.png') })
      // Week 2 alone.
      writes.length = 0
      await page.locator('[data-avail-row="' + WK2 + '"] [data-pick="AVAILABLE"]').click()
      await page.waitForTimeout(500)
      ok('week 2 answer writes the week-2 date only', writes.length === 1 && writes[0].date === WK2 && writes[0].status === 'AVAILABLE', JSON.stringify(writes))
      const b1 = await body()
      ok('the split line goes once both weeks agree', !/W1 ONLY/.test(b1))
      // Both weeks.
      await cara.locator('[data-avail-dot]').first().click()
      await page.waitForTimeout(250)
      writes.length = 0
      await page.locator('[data-avail-row="both"] [data-pick="UNAVAILABLE"]').click()
      await page.waitForTimeout(600)
      const dates = writes.map((w) => w.date).sort()
      ok('both weeks writes both dates, once each', JSON.stringify(dates) === JSON.stringify([WK1, WK2].sort()), JSON.stringify(writes))
      ok('...as UNAVAILABLE', writes.length === 2 && writes.every((w) => w.status === 'UNAVAILABLE'))
    } else {
      writes.length = 0
      await page.locator('[role="dialog"] button', { hasText: 'Unavailable' }).first().click({ timeout: 2000 }).catch(() => {})
      await page.waitForTimeout(400)
      ok('control: a one-day answer writes one date', writes.length === 1 && writes[0].date === WK1, JSON.stringify(writes))
    }
    await ctx.close()
  }
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run()
