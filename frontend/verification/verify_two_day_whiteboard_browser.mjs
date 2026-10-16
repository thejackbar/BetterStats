// Drives the REAL Selection Whiteboard in Chromium with the API stubbed at the
// network layer.
//
// Reported (Applecross, Oct 2026): on a day with a two-day 1st XI game, a player
// picked for a ONE-day team on the 24th looked available for the two-day game
// too, because nothing on the card showed that he is away the following weekend.
// Checks: a card whose weekends differ says which one in plain coloured text
// ("W2 OUT", "W2 ?"), never a pill and never for "no answer yet"; a player free
// for both weekends carries nothing; the one-day team's card has no separate
// OUT tag (he IS free that day); the shared pool judges
// "today" (W1) so a two-day team's worse combined status does not mark him OUT
// there; dropping him into the two-day team warns "unavailable for week 2"; the
// two-day column says so; a day with no two-day game has none of it.
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_two_day_whiteboard_browser.mjs
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
const PASS = [], FAIL = []
const ok = (name, cond, detail = '') => { (cond ? PASS : FAIL).push(name); console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  none: ' + String(detail).slice(0, 200) : ''}`) }
const ME = { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' } }

const DAY = '2099-04-18', DAY_W2 = '2099-04-25', OTHER_DAY = '2099-05-02'
const F1 = '00000000-0000-4000-8000-0000000000f1'   // two-day 1st XI
const F2 = '00000000-0000-4000-8000-0000000000f2'   // one-day 2nd XI
const F3 = '00000000-0000-4000-8000-0000000000f3'   // one-day, another day (control)
const pid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const JACK = 5, FREE = 6, W1OUT = 7, W2NONE = 8, W2MAYBE = 11
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

// Per-player answers: [W1, W2].
const WEEKS = { [JACK]: ['AVAILABLE', 'UNAVAILABLE'], [FREE]: ['AVAILABLE', 'AVAILABLE'], [W1OUT]: ['UNAVAILABLE', 'AVAILABLE'], [W2NONE]: ['AVAILABLE', 'NO_RESPONSE'], [W2MAYBE]: ['AVAILABLE', 'MAYBE'] }
const RANK = { UNAVAILABLE: 0, NO_RESPONSE: 1, MAYBE: 2, AVAILABLE: 3 }
const worst = (a) => a.reduce((x, s) => (RANK[s] < RANK[x] ? s : x), 'AVAILABLE')

const basePlayer = (n) => ({
  id: pid(n), display_name: `Player${String.fromCharCode(64 + n)} Test`, player_role: null, skill_positions: ['BAT'],
  squads: [], squad_team_id: null, availability: 'AVAILABLE', availability_reason: null, last_played: '2099-03-01',
  photo_url: null, batting_hand: null, bowling_action: null, bowling_type: null, is_opening_batsman: null, gender: 'male',
  is_overseas: null, age: null, is_dormant: false, is_inactive: false, is_current: true, selected: false, clash: [],
  clash_detail: [], also_in: [], clash_blocks: false, squad_match: false, tier: 1, gender_ok: true, recent_ok: true,
  score: 30 - n, recent: [], rule_flags: [], rule_notes: [], rule_state: 'ok',
})
// What each fixture's own pool says: the two-day team reads both weeks (worst of them),
// a one-day team reads its own day only.
const poolFor = (fid) => Array.from({ length: 12 }, (_, i) => i + 1).map((n) => {
  const p = basePlayer(n)
  const w = WEEKS[n]
  if (!w) return p
  if (fid === F1) return { ...p, availability: worst(w), availability_days: [{ date: DAY, status: w[0] }, { date: DAY_W2, status: w[1] }] }
  return { ...p, availability: w[0], availability_days: null }
})
const FX = [
  { id: F1, label: 'Kalamunda', opponent_name: 'Kalamunda', home_away: 'HOME', played_on: DAY, end_on: DAY_W2, start_time: '12:30', round: 3, venue: 'Park', team_name: 'Club 1st XI', team_sequence: 1, grade_name: 'A Grade' },
  { id: F2, label: 'Rovers', opponent_name: 'Rovers', home_away: 'AWAY', played_on: DAY, end_on: null, start_time: '12:30', round: 3, venue: 'Oval', team_name: 'Club 2nd XI', team_sequence: 2, grade_name: 'B Grade' },
  { id: F3, label: 'Rams', opponent_name: 'Rams', home_away: 'HOME', played_on: OTHER_DAY, end_on: null, start_time: '12:30', round: 5, venue: 'Oval', team_name: 'Club 1st XI', team_sequence: 1, grade_name: 'A Grade' },
]
const confirmed = { [F1]: [1, 2, 3].map(pid), [F2]: [JACK, 9, 10].map(pid), [F3]: [] }

const run = async () => {
  mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  page.on('dialog', (d) => d.accept())
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route(/\/api\/club-admin\/settings$/, (r) => json(r, { player_name_format: 'first_last' }))
  await page.route(/\/api\/selection\/overview(\?.*)?$/, (r) => json(r, { default_team_size: 11, fixtures: FX.map((f) => ({
    ...f, has_draft: false,
    lineup: confirmed[f.id].map((p, i) => ({ player_id: p, display_name: 'x', batting_order: i + 1, skill_positions: [], availability: 'AVAILABLE', is_captain: false, is_wicket_keeper: false })),
  })) }))
  await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { source_fixture_id: null, player_ids: [], captain_id: null, wicket_keeper_id: null }))
  await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
  await page.route(/\/api\/selection\/([0-9a-f-]{36})\/draft(\?.*)?$/, (r) => json(r, r.request().method() === 'PUT' ? { status: 'ok', version: 1 } : { draft: null, version: 0 }))
  await page.route(/\/api\/selection\/([0-9a-f-]{36})$/, async (r) => {
    const fid = r.request().url().match(/selection\/([0-9a-f-]{36})$/)[1]
    const f = FX.find((x) => x.id === fid)
    return json(r, {
      fixture: { ...f, home_team: 'Club', away_team: f.opponent_name, team_id: `t-${fid}`, grade_id: `g-${fid}` },
      lineup: confirmed[fid].map((p, i) => ({ player_id: p, batting_order: i + 1, is_captain: false, is_wicket_keeper: false })),
      pool: poolFor(fid), default_team_size: 11, rules: { active: false, applied: [], team: [] }, flags: {},
    })
  })

  const col = (fid) => page.locator(`[data-team-col="${fid}"]`)
  const cardIn = (fid, n) => col(fid).locator(`[data-player-card="${pid(n)}"]`)
  const poolCard = (n) => page.locator(`[data-pool-col] [data-player-card="${pid(n)}"]`)
  const flags = (loc) => loc.locator('[data-week-flag]')
  const flagText = async (loc) => ((await flags(loc).count()) ? (await flags(loc).first().innerText({ timeout: 1500 })).trim() : '')
  // The plain OUT tag, once any "W2 OUT" flag is set aside.
  const hasPlainOut = (t) => /\bOUT\b/.test(String(t).replace(/W\d OUT/g, ''))
  const text = async (loc) => (await loc.count() ? (await loc.first().innerText({ timeout: 2000 })).replace(/\s+/g, ' ') : '<absent>')

  console.log('\n# a day with a two-day game')
  await page.goto(`${BASE}/admin/betterselect/whiteboard`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-draft-table]').waitFor({ timeout: 15000 })
  await page.waitForTimeout(400)

  ok('the two-day column says it is played over two weekends', /two-day/i.test(await text(col(F1).locator('[data-two-day-header]'))), await text(col(F1).locator('[data-two-day-header]')))
  ok('...and names both dates', /\b18\b/.test(await text(col(F1).locator('[data-two-day-header]'))) && /\b25\b/.test(await text(col(F1).locator('[data-two-day-header]'))), await text(col(F1).locator('[data-two-day-header]')))
  ok('control: the one-day column has no such line', (await col(F2).locator('[data-two-day-header]').count()) === 0)
  ok('a legend explains W1 and W2', (await page.locator('[data-week-legend]').count()) === 1)

  const jackInOneDay = cardIn(F2, JACK)
  ok('Jack is in the one-day team', (await jackInOneDay.count()) === 1)
  ok('his one-day card says "W2 OUT"', (await flagText(jackInOneDay)) === 'W2 OUT', await flagText(jackInOneDay))
  ok('...in red, as plain text (no pill, no button, not clickable-looking)', await jackInOneDay.locator('[data-week-flag]').evaluate((el) => {
    const cs = getComputedStyle(el)
    return el.tagName === 'SPAN' && !el.closest('button') && cs.cursor !== 'pointer' && cs.backgroundColor === 'rgba(0, 0, 0, 0)' && cs.borderTopWidth === '0px'
  }, null, { timeout: 1500 }).catch(() => false))
  ok('...and no separate OUT tag on top of it (he is free that day)', !hasPlainOut(await text(jackInOneDay)), await text(jackInOneDay))
  const tip = (await jackInOneDay.locator('[data-week-flag]').getAttribute('title', { timeout: 1500 }).catch(() => '')) || ''
  ok('the tooltip names both weeks and dates', /Week 2 .*Unavailable/.test(tip) && /Week 1 .*Available/.test(tip), tip)
  ok('a player free both weeks has no flag', (await flags(poolCard(FREE)).count()) === 0)
  ok('a player away this week but free next says "W1 OUT"', (await flagText(poolCard(W1OUT))) === 'W1 OUT', await flagText(poolCard(W1OUT)))
  ok('a maybe for week 2 says "W2 ?"', (await flagText(poolCard(W2MAYBE))) === 'W2 ?', await flagText(poolCard(W2MAYBE)))
  ok('no answer for week 2 yet is NOT flagged (that is everyone before it is collected)', (await flags(poolCard(W2NONE)).count()) === 0)
  ok('only the three players with something to say are flagged', (await page.locator('[data-week-flag]').count()) === 3, String(await page.locator('[data-week-flag]').count()))
  ok('no pill-shaped W1/W2 chips remain', (await page.locator('[data-week-chip]').count()) === 0)
  await page.screenshot({ path: join(SHOTS, 'whiteboard_two_day.png') })

  console.log('\n# the shared pool judges today')
  // Take Jack out of the one-day team: he lands in the pool. The first team's own
  // pool (the two-day game) says UNAVAILABLE for him; the pool must not.
  await jackInOneDay.hover()
  await col(F2).locator(`[data-player-card="${pid(JACK)}"] button[aria-label^="Remove"]`).click({ force: true, timeout: 3000 }).catch(() => {})
  await page.waitForTimeout(300)
  ok('Jack is in the pool', (await poolCard(JACK).count()) === 1)
  ok('...not marked plain OUT (free today)', !hasPlainOut(await text(poolCard(JACK))), await text(poolCard(JACK)))
  ok('...and still says "W2 OUT"', (await flagText(poolCard(JACK))) === 'W2 OUT', await flagText(poolCard(JACK)))

  console.log('\n# dropping him into the two-day team')
  const centre = async (loc) => { const b = await loc.boundingBox(); return b ? { x: b.x + b.width / 2, y: b.y + b.height / 2 } : null }
  const a = await centre(poolCard(JACK)), b = await centre(col(F1).locator('[data-slot-row="5"]'))
  if (a && b) {
    await page.mouse.move(a.x, a.y); await page.mouse.down()
    await page.mouse.move(a.x + 12, a.y + 6, { steps: 3 }); await page.mouse.move(b.x, b.y, { steps: 10 }); await page.mouse.up()
  }
  await page.waitForTimeout(500)
  ok('he lands in the two-day team', (await cardIn(F1, JACK).count()) === 1)
  ok('the warning names the week he is away', /unavailable for week 2/i.test(await page.locator('body').innerText()), (await page.locator('body').innerText()).slice(0, 200))
  ok('in the two-day team the card says "W2 OUT"', (await flagText(cardIn(F1, JACK))) === 'W2 OUT', await text(cardIn(F1, JACK)))

  console.log('\n# the second weekend shows the same game, linked')
  const tabs = await page.locator('[data-day]').evaluateAll((els) => els.map((e) => e.getAttribute('data-day')))
  ok('week 2 has its own tab, in date order', JSON.stringify(tabs) === JSON.stringify([DAY, DAY_W2, OTHER_DAY]), JSON.stringify(tabs))
  await page.locator(`[data-day="${DAY_W2}"]`).click().catch(() => {})
  await page.waitForTimeout(600)
  ok('the two-day 1st XI is a column on the week 2 tab', (await col(F1).count()) === 1)
  ok('control: the one-day 2nd XI from week 1 is not', (await col(F2).count()) === 0)
  ok('it says it is week 2 and when it started', /week 2 of 2, from/i.test(await text(col(F1).locator('[data-two-day-header]'))), await text(col(F1).locator('[data-two-day-header]')))
  ok('players already in it are in the column, not the pool (they are busy in week 2)', (await poolCard(1).count()) === 0 && (await cardIn(F1, 1).count()) === 1)
  ok('a player away in week 2 reads OUT in the week 2 pool', (await poolCard(JACK).count()) === 1 && /\bOUT\b/.test(await text(poolCard(JACK))), await text(poolCard(JACK)))
  ok('a player away in week 1 only is NOT out in the week 2 pool', !hasPlainOut(await text(poolCard(W1OUT))), await text(poolCard(W1OUT)))
  await page.screenshot({ path: join(SHOTS, 'whiteboard_week2.png') })

  console.log('\n# control: a day with no two-day game')
  await page.locator('[data-day]').last().click()
  await page.waitForTimeout(500)
  ok('no legend', (await page.locator('[data-week-legend]').count()) === 0)
  ok('no flags anywhere', (await page.locator('[data-week-flag]').count()) === 0)

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run()
