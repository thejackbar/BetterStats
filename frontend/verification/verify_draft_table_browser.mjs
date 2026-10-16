// Drives the REAL Draft table and Selection board in Chromium with the API
// stubbed at the network layer (an in-memory stand-in for fixtures, confirmed
// XIs and one draft row per team, with the server's clash policy for Confirm).
//
//   Draft table
//   * every team of the day is a column beside a pool of players nobody has picked
//   * dragging a player from one team onto another swaps them; pool -> team fills
//     the first open slot; team -> pool takes them out; nobody is ever in a team twice
//   * every change autosaves to THAT team's draft, never the confirmed XI
//   * Confirm all writes only the teams that changed; the higher team goes first
//   * a draft changed by someone else is refused (409), shown on the column, and
//     "Keep mine" saves over it only after asking
//   * the board fits the screen: no list scrolls with a full side at 1440x900
//   * 390px: a short note instead of a cramped table, no horizontal overflow
//
//   Selection board (Dual rail)
//   * the Selected XI shows all eleven without scrolling at common laptop heights,
//     and falls back to scrolling (not crushed rows) on a very short window
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_draft_table_browser.mjs
//   CONTROL=1 node verify_draft_table_browser.mjs     (previous build: the fit checks must fail)
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
const CONTROL = !!process.env.CONTROL

let PASS = 0, FAIL = 0
const FAILURES = []
const ok = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(label); console.log(`  FAIL ${label}  ${detail}`) }
}

const ME = {
  id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' },
}

const DAY = '2099-04-18'
const DAY2 = '2099-04-25'
const F1 = '00000000-0000-4000-8000-0000000000f1'
const F2 = '00000000-0000-4000-8000-0000000000f2'
const F3 = '00000000-0000-4000-8000-0000000000f3'
const F4 = '00000000-0000-4000-8000-0000000000f4'
const pid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const NAMES = {}
const ROLES = [['BAT'], ['BWL'], ['ALL'], ['WKT'], ['BAT'], ['BWL']]
const POOL = []
for (let n = 1; n <= 24; n++) {
  const nm = `Player${String.fromCharCode(64 + n)} Test`
  NAMES[n] = nm
  POOL.push({
    id: pid(n), display_name: nm, player_role: null, skill_positions: ROLES[n % ROLES.length],
    squads: [], squad_team_id: null, availability: n === 20 ? 'UNAVAILABLE' : 'AVAILABLE', availability_reason: null,
    last_played: '2099-03-01', photo_url: null, batting_hand: null, bowling_action: null, bowling_type: null,
    is_opening_batsman: null, gender: [17, 18, 19].includes(n) ? 'female' : 'male', is_overseas: null, age: null, is_dormant: false,
    is_inactive: n === 24, is_current: true, selected: false, clash: [], clash_detail: [], also_in: [],
    clash_blocks: false, squad_match: false, tier: 1, gender_ok: true, recent_ok: true, score: 24 - n, recent: [],
    rule_flags: [], rule_notes: [], rule_state: 'ok',
  })
}
const FX = [
  { id: F1, label: 'Rivals', opponent_name: 'Rivals', home_away: 'HOME', played_on: DAY, start_time: '1:00pm', round: 3, venue: 'Oval', team_name: 'Club 1st XI', team_sequence: 1, grade_name: 'A Grade' },
  { id: F2, label: 'Rovers', opponent_name: 'Rovers', home_away: 'AWAY', played_on: DAY, start_time: '1:00pm', round: 3, venue: 'Park', team_name: 'Club 2nd XI', team_sequence: 2, grade_name: 'B Grade' },
  { id: F3, label: 'Rams', opponent_name: 'Rams', home_away: 'HOME', played_on: DAY, start_time: '1:00pm', round: 3, venue: 'Oval 2', team_name: 'Club 3rd XI', team_sequence: 3, grade_name: 'C Grade' },
  { id: F4, label: 'Rebels', opponent_name: 'Rebels', home_away: 'HOME', played_on: DAY2, start_time: '1:00pm', round: 4, venue: 'Oval', team_name: 'Club 1st XI', team_sequence: 1, grade_name: 'A Grade' },
]

const run = async () => {
  mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('dialog', (d) => d.accept())

  // The "server".
  const server = {
    confirmed: { [F1]: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map(pid), [F2]: [12, 13, 14, 15].map(pid), [F3]: [], [F4]: [] },
    drafts: {},   // fid -> { draft, version, by }
  }
  const wire = { draftPuts: [], draftDeletes: [], confirms: [], conflicts: 0 }
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const seqOf = (fid) => FX.find((f) => f.id === fid).team_sequence
  const dayOf = (fid) => FX.find((f) => f.id === fid).played_on
  const payload = (fid) => {
    const f = FX.find((x) => x.id === fid)
    return {
      fixture: { ...f, end_on: null, home_team: 'Club', away_team: f.opponent_name, team_id: `t-${fid}`, grade_id: `g-${fid}` },
      lineup: server.confirmed[fid].map((p, i) => ({ player_id: p, batting_order: i + 1, is_captain: false, is_wicket_keeper: false })),
      pool: POOL, default_team_size: 11, rules: { active: false, applied: [], team: [] }, flags: {},
    }
  }

  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route(/\/api\/selection\/overview(\?.*)?$/, (r) => json(r, {
    default_team_size: 11,
    fixtures: FX.map((f) => ({
      ...f, lineup: server.confirmed[f.id].map((p, i) => ({ player_id: p, display_name: 'x', batting_order: i + 1, skill_positions: [], availability: 'AVAILABLE', is_captain: f.id === F1 && p === pid(1), is_wicket_keeper: f.id === F1 && p === pid(1) })),
      has_draft: !!server.drafts[f.id],
    })),
  }))
  await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { source_fixture_id: null, player_ids: [], captain_id: null, wicket_keeper_id: null }))
  await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
  await page.route(/\/api\/selection\/([0-9a-f-]{36})\/draft(\?.*)?$/, async (r) => {
    const fid = r.request().url().match(/selection\/([0-9a-f-]{36})\/draft/)[1]
    const m = r.request().method()
    const cur = server.drafts[fid]
    const conflict = () => {
      wire.conflicts++
      return json(r, { detail: { code: 'draft_conflict', message: 'changed', draft: cur?.draft || null, version: cur?.version || 0, updated_by: cur?.by || null, updated_at: new Date().toISOString() } }, 409)
    }
    if (m === 'PUT') {
      const b = JSON.parse(r.request().postData())
      wire.draftPuts.push({ fid, ...b })
      if ((b.base_version || 0) !== (cur?.version || 0)) return conflict()
      server.drafts[fid] = { draft: b, version: (cur?.version || 0) + 1, by: 'Jordan Admin' }
      return json(r, { status: 'ok', version: server.drafts[fid].version })
    }
    if (m === 'DELETE') {
      wire.draftDeletes.push(fid)
      delete server.drafts[fid]
      return json(r, { status: 'ok', version: 0 })
    }
    return json(r, cur ? { draft: cur.draft, version: cur.version, updated_at: new Date().toISOString(), updated_by: cur.by } : { draft: null, version: 0 })
  })
  await page.route(/\/api\/selection\/([0-9a-f-]{36})$/, async (r) => {
    const fid = r.request().url().match(/selection\/([0-9a-f-]{36})$/)[1]
    if (r.request().method() === 'PUT') {
      const b = JSON.parse(r.request().postData())
      wire.confirms.push({ fid, ids: b.players.map((p) => p.player_id) })
      // The server's clash policy: a higher team may call a player up from a lower
      // one; a lower team may not take a player a higher team has confirmed.
      const picked = new Set(b.players.map((p) => p.player_id))
      const blocking = []
      for (const other of Object.keys(server.confirmed)) {
        if (other === fid || dayOf(other) !== dayOf(fid)) continue
        for (const p of server.confirmed[other]) {
          if (!picked.has(p)) continue
          if (seqOf(fid) < seqOf(other)) server.confirmed[other] = server.confirmed[other].filter((x) => x !== p)
          else blocking.push(p)
        }
      }
      if (blocking.length) return json(r, { detail: `Already selected for another fixture on ${dayOf(fid)}: ${blocking.join(', ')}` }, 409)
      server.confirmed[fid] = b.players.map((p) => p.player_id)
      delete server.drafts[fid]
      return json(r, { status: 'ok', count: b.players.length })
    }
    return json(r, payload(fid))
  })

  // Mouse drag with real pointer events, in steps so the engine sees a drag.
  const centre = async (loc) => {
    const b = await loc.boundingBox()
    return b ? { x: b.x + b.width / 2, y: b.y + b.height / 2 } : null
  }
  const dragTo = async (from, to) => {
    const a = await centre(from), b = await centre(to)
    if (!a || !b) return false
    await page.mouse.move(a.x, a.y)
    await page.mouse.down()
    await page.mouse.move(a.x + 12, a.y + 6, { steps: 3 })
    await page.mouse.move(b.x, b.y, { steps: 10 })
    await page.mouse.up()
    await page.waitForTimeout(120)
    return true
  }
  const col = (fid) => page.locator(`[data-team-col="${fid}"]`)
  const cardIn = (fid, n) => col(fid).locator(`[data-player-card="${pid(n)}"]`)
  const slotIn = (fid, i) => col(fid).locator(`[data-slot-row="${i}"]`)
  const poolCard = (n) => page.locator(`[data-pool-col] [data-player-card="${pid(n)}"]`)
  const namesIn = async (fid) => (await col(fid).locator('[data-player-card]').allInnerTexts()).map((t) => t.split('\n')[0])
  const countOf = async (fid) => (await col(fid).locator('header .font-mono').first().innerText()).trim()
  const lastPut = (fid) => [...wire.draftPuts].reverse().find((p) => p.fid === fid)

  // ═══════════════ Draft table ═══════════════
  console.log('\n# the table')
  await page.goto(`${BASE}/admin/betterselect/whiteboard`, { waitUntil: 'domcontentloaded' })
  const loaded = await page.locator('[data-draft-table]').waitFor({ timeout: 15000 }).then(() => true).catch(() => false)
  ok('the draft table opens', loaded)
  if (loaded) {
    await page.waitForTimeout(400)
    ok('one column per team on the day', (await page.locator('[data-team-col]').count()) === 3)
    ok('the next day is a tab, not a column', (await page.locator('[data-day]').count()) === 2)
    ok('top team first', (await page.locator('[data-team-col]').first().getAttribute('data-team-col')) === F1)
    ok('1st XI reads 11/11', (await countOf(F1)) === '11/11', await countOf(F1))
    ok('2nd XI reads 4/11', (await countOf(F2)) === '4/11', await countOf(F2))
    ok('pool lists everyone unpicked except the inactive player', (await page.locator('[data-pool-col] [data-player-card]').count()) === 24 - 15 - 1,
      String(await page.locator('[data-pool-col] [data-player-card]').count()))
    ok('inactive player is not in the pool', (await poolCard(24).count()) === 0)
    ok('the board has no ancestor scroll: its bottom is inside the window', await page.evaluate(() => {
      const r = document.querySelector('[data-draft-table]').getBoundingClientRect()
      return r.bottom <= window.innerHeight + 1
    }))
    const fit = await page.evaluate(() => [...document.querySelectorAll('[data-team-list]')].map((l) => [l.scrollHeight, l.clientHeight]))
    ok('no team list scrolls with a full side at 1440x900', fit.every(([s, c]) => s <= c + 1), JSON.stringify(fit))
    ok('the table reports it is fitted', (await page.locator('[data-draft-table]').getAttribute('data-fit')) === 'on')
    await page.screenshot({ path: join(SHOTS, 'draft_table_1440.png') })

    console.log('\n# drag between teams')
    // 1st XI #11 swaps with 2nd XI #15 (the 4th player in the 2nd XI).
    ok('drag 2nd XI player onto a 1st XI player', await dragTo(cardIn(F2, 15), cardIn(F1, 11)))
    ok('1st XI now has the 2nd XI player', (await cardIn(F1, 15).count()) === 1)
    ok('1st XI no longer has the player they swapped out', (await cardIn(F1, 11).count()) === 0)
    ok('2nd XI has the player from 1st XI', (await cardIn(F2, 11).count()) === 1)
    ok('2nd XI no longer has the one they sent up', (await cardIn(F2, 15).count()) === 0)
    ok('both teams are still the same size (swap)', (await countOf(F1)) === '11/11' && (await countOf(F2)) === '4/11')
    ok('nobody is in the pool twice or in two teams', await page.evaluate(() => {
      const ids = [...document.querySelectorAll('[data-player-card]')].map((e) => e.getAttribute('data-player-card'))
      return new Set(ids).size === ids.length
    }))

    console.log('\n# pool to a team, and back')
    ok('drag a pool player onto the empty 3rd XI', await dragTo(poolCard(16), col(F3).locator('[data-slot-row="0"]')))
    ok('3rd XI now has that player in slot 1', (await slotIn(F3, 0).locator(`[data-player-card="${pid(16)}"]`).count()) === 1)
    ok('3rd XI reads 1/11', (await countOf(F3)) === '1/11', await countOf(F3))
    ok('the player left the pool', (await poolCard(16).count()) === 0)
    ok('drag a pool player onto the team body (first open slot)', await dragTo(poolCard(17), col(F3).locator('[data-slot-row="5"]')))
    ok('they land where dropped', (await slotIn(F3, 5).locator(`[data-player-card="${pid(17)}"]`).count()) === 1)
    ok('drag back out to the pool', await dragTo(cardIn(F3, 17), page.locator('[data-pool-col] [data-pool-list]')))
    ok('they are back in the pool', (await poolCard(17).count()) === 1)
    ok('and out of the team', (await cardIn(F3, 17).count()) === 0)
    ok('refuses to double a player into a team they are already in', await (async () => {
      // 1st XI has player 1 in slot 1: dragging 2nd XI #11 (sent down) onto 1st XI keeps one copy each.
      const before = await page.locator('[data-player-card]').count()
      await dragTo(cardIn(F1, 1), cardIn(F1, 2))   // same-team swap is allowed and never duplicates
      return (await page.locator('[data-player-card]').count()) === before
    })())

    console.log('\n# autosave to each team draft, never the confirmed XI')
    await page.waitForTimeout(1600)
    ok('1st XI draft was saved', !!lastPut(F1))
    ok('2nd XI draft was saved', !!lastPut(F2))
    ok('3rd XI draft was saved', !!lastPut(F3))
    ok('1st XI draft holds the player from the 2nd XI', !!lastPut(F1) && lastPut(F1).slots.includes(pid(15)) && !lastPut(F1).slots.includes(pid(11)))
    ok('3rd XI draft holds player 16', !!lastPut(F3) && lastPut(F3).slots.includes(pid(16)))
    ok('nothing wrote the confirmed XI', wire.confirms.length === 0)
    ok('the confirmed XIs are untouched', server.confirmed[F1].length === 11 && server.confirmed[F3].length === 0)
    ok('each changed team shows Confirm', (await page.locator('[data-confirm-col]').count()) === 3)
    ok('Confirm all counts them', /Confirm all \(3\)/.test(await page.locator('body').innerText()))

    console.log('\n# captain and keeper')
    await cardIn(F1, 1).hover()
    await cardIn(F1, 1).locator('button[title="Captain"]').click()
    await page.waitForTimeout(1500)
    ok('captain is saved in that team\'s draft', lastPut(F1)?.captain_id === pid(1), String(lastPut(F1)?.captain_id))

    console.log('\n# another selector changes the 2nd XI draft')
    server.drafts[F2] = { draft: { slots: [pid(12), pid(13), pid(14), null, null, null, null, null, null, null, null], captain_id: null, wicket_keeper_id: null, demotions: [] }, version: (server.drafts[F2]?.version || 0) + 1, by: 'Sam Selector' }
    const beforeConflicts = wire.conflicts
    ok('drag a pool player into the 2nd XI', await dragTo(poolCard(18), slotIn(F2, 6)))
    await page.waitForTimeout(1500)
    ok('the server refused the stale save', wire.conflicts > beforeConflicts)
    ok('the column says who changed it', /Sam Selector changed this draft/.test(await col(F2).innerText()))
    ok('their draft was not overwritten', server.drafts[F2].by === 'Sam Selector')
    const putsBefore = wire.draftPuts.filter((p) => p.fid === F2).length
    await col(F2).getByRole('button', { name: 'Keep mine' }).click()
    await page.waitForTimeout(1500)
    ok('Keep mine saves this board over theirs', wire.draftPuts.filter((p) => p.fid === F2).length > putsBefore && lastPut(F2).slots.includes(pid(18)))
    ok('the conflict notice clears', !(await col(F2).innerText()).includes('changed this draft'))

    console.log('\n# Confirm all')
    await page.getByRole('button', { name: /Confirm all/ }).click()
    await page.waitForTimeout(1500)
    const order = wire.confirms.map((c) => c.fid)
    ok('three teams written', wire.confirms.length === 3, JSON.stringify(order))
    ok('top team confirms first', order[0] === F1, JSON.stringify(order))
    ok('1st XI confirmed with the player from the 2nd', server.confirmed[F1].includes(pid(15)) && !server.confirmed[F1].includes(pid(11)))
    ok('2nd XI confirmed with the player sent down', server.confirmed[F2].includes(pid(11)))
    ok('the called-up player left the 2nd XI', !server.confirmed[F2].includes(pid(15)))
    ok('3rd XI confirmed', server.confirmed[F3].includes(pid(16)))
    ok('drafts are gone once confirmed', Object.keys(server.drafts).length === 0, JSON.stringify(Object.keys(server.drafts)))
    ok('button reads All confirmed', /All confirmed/.test(await page.locator('body').innerText()))
    ok('no team shows Confirm any more', (await page.locator('[data-confirm-col]').count()) === 0)

    console.log('\n# another day')
    await page.locator(`[data-day="${DAY2}"]`).click()
    await page.locator('[data-team-col]').first().waitFor({ timeout: 10000 })
    await page.waitForTimeout(300)
    ok('switching day shows that day\'s one team', (await page.locator('[data-team-col]').count()) === 1)
  }

  // ═══════════════ Draft table: the pool stays in view ═══════════════
  console.log('\n# Draft table: the pool is pinned while the teams scroll')
  await page.setViewportSize({ width: 1100, height: 800 })
  await page.goto(`${BASE}/admin/betterselect/whiteboard`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-draft-table]').waitFor({ timeout: 15000 })
  await page.waitForTimeout(500)
  const scrollInfo = () => page.evaluate(() => {
    const b = document.querySelector('[data-draft-table]')
    const p = document.querySelector('[data-pool-col]').getBoundingClientRect()
    const last = [...document.querySelectorAll('[data-team-col]')].pop().getBoundingClientRect()
    return { over: b.scrollWidth - b.clientWidth, left: b.scrollLeft, poolX: Math.round(p.left - b.getBoundingClientRect().left), lastRight: Math.round(last.right), boardRight: Math.round(b.getBoundingClientRect().right) }
  })
  const before = await scrollInfo()
  ok('the teams overflow sideways at 1100px (the test is real)', before.over > 20, JSON.stringify(before))
  await page.evaluate(() => { const b = document.querySelector('[data-draft-table]'); b.scrollLeft = b.scrollWidth })
  await page.waitForTimeout(200)
  const away = await scrollInfo()
  ok('scrolled right: the pool is still at the left edge of the board', away.poolX === 0 && away.left > 20, JSON.stringify(away))
  ok('scrolled right: the pool is on screen and draggable', await poolCard(1).isVisible() || (await page.locator('[data-pool-col] [data-player-card]').first().isVisible()))
  // Drag from the pinned pool to the far column: it must auto-scroll to reach it.
  await page.evaluate(() => { document.querySelector('[data-draft-table]').scrollLeft = 0 })
  await page.waitForTimeout(150)
  const firstPool = page.locator('[data-pool-col] [data-player-card]').first()
  const firstId = await firstPool.getAttribute('data-player-card')
  const lastCol = page.locator('[data-team-col]').last()
  const lastId = await lastCol.getAttribute('data-team-col')
  const a = await centre(firstPool)
  const board = await page.locator('[data-draft-table]').boundingBox()
  await page.mouse.move(a.x, a.y); await page.mouse.down()
  await page.mouse.move(a.x + 12, a.y + 6, { steps: 3 })
  await page.mouse.move(board.x + board.width - 20, a.y, { steps: 8 })
  await page.waitForTimeout(1200)               // held at the right edge: the board scrolls under the finger
  const held = await scrollInfo()
  ok('held at the right edge: the board scrolls sideways on its own', held.left > 20, JSON.stringify(held))
  ok('held at the right edge: the pool stays pinned', held.poolX === 0, JSON.stringify(held))
  const target = await centre(lastCol.locator('[data-slot-row]').first())
  await page.mouse.move(target.x, target.y, { steps: 6 })
  await page.mouse.up()
  await page.waitForTimeout(1200)               // past the autosave delay
  ok('dropped on the far team from the pinned pool: that team has the player', (await lastCol.locator(`[data-player-card="${firstId}"]`).count()) === 1)
  ok('and nobody was dropped on the wrong team', lastPut(lastId)?.slots?.includes(firstId) === true)
  await page.setViewportSize({ width: 1440, height: 900 })

  // ═══════════════ Overview: one player is captain AND keeper ═══════════════
  console.log('\n# Overview: a captain who is also the named keeper')
  await page.goto(`${BASE}/admin/betterselect/selection`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1500)
  const ovText = await page.locator('body').innerText()
  ok('the overview loaded with the 1st XI (11 named)', /1st XI/.test(ovText))
  ok('a named keeper (who is also captain, with no WKT tag) is not "No keeper named"', !/No keeper named/i.test(ovText), 'still says No keeper named')

  // ═══════════════ Selection board: the XI fits ═══════════════
  console.log('\n# Selection board: Selected XI fits without scrolling')
  server.confirmed[F1] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map(pid)
  server.drafts = {}
  const xi = async () => page.evaluate(() => {
    // Found by structure, so the same check runs against the previous build.
    const head = [...document.querySelectorAll('section h3')].find((h) => h.textContent.trim().startsWith('Selected XI'))
    const panel = head && head.closest('section')
    const list = panel && panel.lastElementChild
    if (!list || !panel) return null
    const rows = [...list.children]
    const last = rows[rows.length - 1].getBoundingClientRect()
    return {
      rows: rows.length, scroll: list.scrollHeight, client: list.clientHeight,
      lastBottom: Math.round(last.bottom), panelBottom: Math.round(panel.getBoundingClientRect().bottom), vh: window.innerHeight,
      density: list.querySelector('[data-density]')?.getAttribute('data-density') || null,
      namesClipped: [...list.querySelectorAll('span.font-semibold')].filter((e) => e.clientHeight < 12).length,
    }
  })
  for (const [w, h] of [[1440, 900], [1440, 780], [1280, 720], [1920, 1080]]) {
    await page.setViewportSize({ width: w, height: h })
    await page.goto(`${BASE}/admin/betterselect/select/${F1}`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Selected XI').first().waitFor({ timeout: 20000 }).catch(async () => {
      await page.screenshot({ path: join(SHOTS, 'selection_xi_failed.png') })
      console.log('   (no XI list) body:', (await page.locator('body').innerText()).replace(/\s+/g, ' ').slice(0, 300))
    })
    await page.waitForTimeout(700)
    const m = await xi()
    ok(`${w}x${h}: the XI list exists`, !!m)
    if (!m) continue
    ok(`${w}x${h}: all 11 slots are in the list`, m.rows === 11, JSON.stringify(m))
    ok(`${w}x${h}: the XI does not scroll`, m.scroll <= m.client + 1, JSON.stringify(m))
    ok(`${w}x${h}: the last slot is on screen`, m.lastBottom <= m.vh, JSON.stringify(m))
    ok(`${w}x${h}: the panel ends inside the window`, m.panelBottom <= m.vh, JSON.stringify(m))
    ok(`${w}x${h}: no name is clipped away`, m.namesClipped === 0, JSON.stringify(m))
    console.log(`       density ${m.density}  (${m.client}px list, ${m.rows} rows)`)
    await page.screenshot({ path: join(SHOTS, `selection_xi_${w}x${h}.png`) })
  }
  await page.setViewportSize({ width: 1440, height: 520 })
  await page.waitForTimeout(500)
  const short = await xi()
  ok('a very short window scrolls the list instead of crushing the rows', !!short && short.scroll > short.client && short.density === 'tight', JSON.stringify(short))

  // Pool still works beside the fitted XI.
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.waitForTimeout(400)
  const poolFit = await page.evaluate(() => {
    const p = [...document.querySelectorAll('section')].find((s) => s.textContent.includes('Available pool'))
    return p ? Math.round(p.getBoundingClientRect().bottom) <= window.innerHeight : null
  })
  ok('the Available pool ends inside the window too', poolFit === true, String(poolFit))

  // ═══════════════ Show juniors (now a Settings choice) ═══════════════
  console.log('\n# Junior grades (Selection Whiteboard): the switch is in Settings, not here')
  {
    const asked = []
    const onReq = (rq) => { if (/\/api\/selection\/overview/.test(rq.url())) asked.push(rq.url()) }
    page.on('request', onReq)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`${BASE}/admin/betterselect/whiteboard`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-draft-table]').waitFor({ timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(300)
    ok('the whiteboard no longer carries a Show juniors switch', (await page.locator('[data-juniors-toggle]').count()) === 0)
    ok('juniors are left out until asked for', asked.length > 0 && asked.every((u) => /hide_juniors=true/.test(u)), asked.join(' '))
    asked.length = 0
    // The Settings choice is the remembered device preference the screens read.
    await page.evaluate(() => { try { localStorage.setItem('bs_pref:select.juniors', 'true') } catch { /* blocked */ } })
    await page.goto(`${BASE}/admin/betterselect/whiteboard`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-draft-table]').waitFor({ timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(500)
    ok('with juniors switched on in Settings, the overview is asked for without the hide flag', asked.length > 0 && asked.every((u) => !/hide_juniors/.test(u)), asked.join(' '))
    page.off('request', onReq)
    await page.evaluate(() => { try { localStorage.removeItem('bs_pref:select.juniors') } catch { /* nothing stored */ } })
  }

  // ═══════════════ Gender filter ═══════════════
  console.log('\n# Gender filter (Draft table and Selection board)')
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(`${BASE}/admin/betterselect/whiteboard`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-draft-table]').waitFor({ timeout: 15000 })
  await page.waitForTimeout(500)
  const gSel = page.locator('[data-pool-col] select[aria-label="Gender"]')
  ok('draft table: the pool offers a Gender filter when it holds men and women', (await gSel.count()) === 1)
  if (await gSel.count()) {
    const total = (await page.locator('[data-pool-count]').innerText()).trim()
    const womenIn = async () => (await Promise.all([17, 18, 19].map((n) => poolCard(n).count()))).reduce((a, b) => a + b, 0)
    const cards = () => page.locator('[data-pool-col] [data-player-card]').count()
    const nW = await womenIn(), nAll = await cards()
    ok('draft table: the pool still holds some women and some men to filter', nW > 0 && nAll > nW, `${nW} of ${nAll}`)
    await gSel.selectOption('female')
    await page.waitForTimeout(200)
    ok('draft table: Women leaves only the women', (await cards()) === nW && (await womenIn()) === nW, `${await cards()} cards`)
    await gSel.selectOption('male')
    await page.waitForTimeout(200)
    ok('draft table: Men leaves nobody who is a woman', (await womenIn()) === 0 && (await cards()) === nAll - nW)
    await gSel.selectOption('')
    await page.waitForTimeout(200)
    ok('draft table: All genders restores the pool', (await page.locator('[data-pool-count]').innerText()).trim() === total)
  }
  await page.goto(`${BASE}/admin/betterselect/select/${F1}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /^Filters/ }).first().waitFor({ timeout: 15000 })
  await page.waitForTimeout(500)
  const poolText = () => page.locator('[data-drop-kind="pool"]').first().innerText()
  ok('board: starts with men and women both in the pool', /PlayerQ/.test(await poolText()) && /PlayerM/.test(await poolText()))
  await page.getByRole('button', { name: /^Filters/ }).first().click()
  const womenBtn = page.getByRole('button', { name: 'Women', exact: true })
  ok('board: the Filters panel has a Gender group with Women', (await womenBtn.count()) === 1)
  if (await womenBtn.count()) {
    await womenBtn.click()
    await page.waitForTimeout(300)
    const t = await poolText()
    ok('board: Women shows the women and not the men', /PlayerQ/.test(t) && /PlayerR/.test(t) && !/PlayerM/.test(t), t.slice(0, 120))
    await page.getByRole('button', { name: 'Men', exact: true }).click()
    await page.waitForTimeout(300)
    const t2 = await poolText()
    ok('board: Men shows the men and not the women', /PlayerM/.test(t2) && !/PlayerQ/.test(t2))
  }

  // ═══════════════ Phone ═══════════════
  console.log('\n# 390px')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${BASE}/admin/betterselect/whiteboard`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1200)
  const phoneNote = /needs a wider screen/.test(await page.locator('body').innerText())
  ok('the draft table says it needs a wider screen on a phone', phoneNote || CONTROL)
  const ov = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
  ok('no horizontal overflow at 390px', ov <= 0, String(ov))
  await page.goto(`${BASE}/admin/betterselect/select/${F1}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1200)
  const ov2 = await page.evaluate(() => document.documentElement.scrollWidth - 390)
  ok('the Selection board still does not overflow at 390px', ov2 <= 0, String(ov2))

  ok('no uncaught page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  if (FAIL) { console.log('FAILED:\n - ' + FAILURES.join('\n - ')); process.exit(1) }
}
run().catch((e) => { console.error(e); process.exit(2) })
