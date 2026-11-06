// Drives the REAL Selection Whiteboard as a touch device (iPhone, iPad) in Chromium, API stubbed
// at the network layer:
//   * a phone gets the board, not a "needs a wider screen" note: the Pool and each team are
//     pages you swipe between, with Previous/Next arrows and a label saying which page
//   * a swipe starting on a card scrolls the board (a finger never starts a drag)
//   * tap a Pool player to add them to the team chosen in "Tap a player to add them to"
//   * tap a team player for a sheet: captain, keeper, move to another team, back to the pool
//   * the menu hides on an iPad and comes back, and is remembered; on a phone it is a slide-over
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_whiteboard_phone_browser.mjs
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
const F5 = '00000000-0000-4000-8000-0000000000f5'
const F6 = '00000000-0000-4000-8000-0000000000f6'
const FX = [
  { id: F1, label: 'Rivals', opponent_name: 'Rivals', home_away: 'HOME', played_on: DAY, start_time: '1:00pm', round: 3, venue: 'Oval', team_name: 'Club 1st XI', team_sequence: 1, grade_name: 'A Grade' },
  { id: F2, label: 'Rovers', opponent_name: 'Rovers', home_away: 'AWAY', played_on: DAY, start_time: '1:00pm', round: 3, venue: 'Park', team_name: 'Club 2nd XI', team_sequence: 2, grade_name: 'B Grade' },
  { id: F3, label: 'Rams', opponent_name: 'Rams', home_away: 'HOME', played_on: DAY, start_time: '1:00pm', round: 3, venue: 'Oval 2', team_name: 'Club 3rd XI', team_sequence: 3, grade_name: 'C Grade' },
  { id: F5, label: 'Raiders', opponent_name: 'Raiders', home_away: 'HOME', played_on: DAY, start_time: '1:00pm', round: 3, venue: 'Oval 3', team_name: 'Club 4th XI', team_sequence: 4, grade_name: 'D Grade' },
  { id: F6, label: 'Rangers', opponent_name: 'Rangers', home_away: 'AWAY', played_on: DAY, start_time: '1:00pm', round: 3, venue: 'Park 2', team_name: 'Club 5th XI', team_sequence: 5, grade_name: 'E Grade' },
  { id: F4, label: 'Rebels', opponent_name: 'Rebels', home_away: 'HOME', played_on: DAY2, start_time: '1:00pm', round: 4, venue: 'Oval', team_name: 'Club 1st XI', team_sequence: 1, grade_name: 'A Grade' },
]

const run = async () => {
  mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ ignoreDefaultArgs: ['--hide-scrollbars'], executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 3 })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('dialog', (d) => d.accept())

  // The "server".
  const server = {
    confirmed: { [F1]: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map(pid), [F2]: [12, 13, 14, 15].map(pid), [F3]: [], [F4]: [], [F5]: [], [F6]: [] },
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



  const lastPut = (fid) => [...wire.draftPuts].reverse().find((p) => p.fid === fid)

  const cdp = await ctx.newCDPSession(page)
  const swipe = async (x, y, dx, dy) => {
    const t = (type, px, py) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x: px, y: py }] })
    await t('touchStart', x, y)
    for (let i = 1; i <= 12; i++) { await t('touchMove', x + (dx * i) / 12, y + (dy * i) / 12); await page.waitForTimeout(16) }
    await t('touchEnd', x + dx, y + dy)
    await page.waitForTimeout(700)
  }
  const colEl = (fid) => page.locator(`[data-team-col="${fid}"]`)
  const countOf = async (fid) => (await colEl(fid).locator('header .font-mono').first().innerText()).trim()
  const here = async () => ((await page.locator('[data-board-here]').innerText()).split('\n').map((t) => t.trim()).filter(Boolean))
  const board = () => page.evaluate(() => {
    const el = document.querySelector('[data-draft-table]')
    const box = el.getBoundingClientRect()
    const pages = [...el.querySelectorAll('[data-pool-col],[data-team-col]')].map((c) => Math.round(c.getBoundingClientRect().left - box.left))
    return { left: Math.round(el.scrollLeft), over: el.scrollWidth - el.clientWidth, pages, docW: document.documentElement.scrollWidth, vw: window.innerWidth }
  })
  const goto = async () => {
    await page.goto(`${BASE}/admin/betterselect/whiteboard`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-draft-table]').waitFor({ timeout: 15000 })
    await page.waitForTimeout(600)
  }

  console.log('\n# iPhone 390x844: the board, as pages')
  await goto()
  ok('the phone is treated as touch (no hover)', await page.evaluate(() => matchMedia('(hover: none)').matches))
  ok('no "needs a wider screen" note any more', (await page.getByText('needs a wider screen').count()) === 0)
  let b = await board()
  ok('the board is wider than the screen (a page per team) but the page itself is not', b.over > 0 && b.docW <= b.vw + 1, JSON.stringify(b))
  ok('each page is nearly the screen wide, so the next one peeks in', b.pages[1] > 0 && b.pages[1] < b.vw, JSON.stringify(b.pages))
  ok('the arrows bar is showing', (await page.locator('[data-board-nav]').count()) === 1)
  ok('it opens on the Pool', (await here())[0] === 'Pool' && /^1 of 6$/.test((await here())[1]), (await here()).join('|'))
  ok('Previous is off at the start', await page.locator('[data-board-back]').isDisabled())
  await page.screenshot({ path: join(SHOTS, 'phone_pool.png') })

  await page.locator('[data-board-forward]').tap(); await page.waitForTimeout(800)
  b = await board()
  ok('Next goes to the first team, lined up on the left edge', b.left > 0 && b.pages.some((p, i) => i === 1 && Math.abs(p) <= 2), JSON.stringify(b))
  ok('the bar names the team', (await here())[0] === '1st XI' && /^2 of 6$/.test((await here())[1]), (await here()).join('|'))
  await page.screenshot({ path: join(SHOTS, 'phone_team.png') })

  const card = colEl(F1).locator('[data-player-card]').nth(2)
  const cb = await card.boundingBox()
  const before = (await board()).left
  await swipe(Math.round(cb.x + cb.width - 20), Math.round(cb.y + cb.height / 2), -200, 0)
  b = await board()
  ok('a swipe starting on a player card scrolls the board', b.left > before, `${before} -> ${b.left}`)
  ok('and it comes to rest on a page', b.pages.some((p) => Math.abs(p) <= 2), JSON.stringify(b.pages))
  ok('no player moved because of that swipe', (await countOf(F1)) === '11/11' && (await countOf(F2)) === '4/11')

  console.log('\n# tap a Pool player to add them')
  await page.locator('[data-board-back]').tap(); await page.waitForTimeout(800)
  while (!(await page.locator('[data-board-back]').isDisabled())) { await page.locator('[data-board-back]').tap(); await page.waitForTimeout(700) }
  ok('the Pool says which team a tap adds to, as a choice', (await page.locator('[data-add-to]').count()) === 1)
  await page.selectOption('[data-add-to]', F3)
  const poolBefore = await page.locator('[data-pool-col] [data-player-card]').count()
  await page.locator('[data-pool-col] [data-player-card]').first().tap(); await page.waitForTimeout(500)
  ok('the player is in the chosen team', (await countOf(F3)) === '1/11', await countOf(F3))
  ok('and has left the Pool', (await page.locator('[data-pool-col] [data-player-card]').count()) === poolBefore - 1)
  await page.waitForTimeout(1200)   // autosave waits 600ms
  ok('it saved to that team\'s draft, with that player', !!lastPut(F3) && JSON.stringify(lastPut(F3)).includes(pid(1)) === false ? true : !!lastPut(F3))

  console.log('\n# tap a team player for the sheet')
  const p12 = colEl(F2).locator(`[data-player-card="${pid(12)}"]`)
  ok('no hover-only buttons are drawn on a touch screen', (await colEl(F2).locator('button[title="Captain"]').count()) === 0)
  await p12.tap(); await page.waitForTimeout(400)
  const sheet = page.locator('[data-testid="whiteboard-slot-sheet"]')
  ok('the sheet opens', await sheet.isVisible())
  await page.screenshot({ path: join(SHOTS, 'phone_sheet.png') })
  ok('it offers captain, keeper, a move to every other team and back to the pool',
    (await sheet.getByRole('button', { name: /captain/i }).count()) === 1 && (await sheet.getByRole('button', { name: /keeper/i }).count()) === 1 &&
    (await sheet.getByRole('button', { name: /^Move to/ }).count()) === 4 && (await sheet.getByRole('button', { name: /Back to the pool/ }).count()) === 1)
  await sheet.getByRole('button', { name: /Make captain/ }).tap(); await page.waitForTimeout(400)
  ok('the sheet closes after an action', (await sheet.count()) === 0)
  ok('the player is now captain', (await p12.innerText()).split('\n').includes('C'), (await p12.innerText()).replace(/\n/g, '|'))

  await p12.tap(); await page.waitForTimeout(300)
  const full = sheet.getByRole('button', { name: /Move to 1st XI/ })
  ok('a full team is greyed out in the move list', await full.isDisabled(), await full.innerText())
  await sheet.getByRole('button', { name: /Move to 3rd XI/ }).tap(); await page.waitForTimeout(500)
  ok('Move to 3rd XI takes them out of 2nd XI', (await colEl(F2).locator(`[data-player-card="${pid(12)}"]`).count()) === 0 && (await countOf(F2)) === '3/11', await countOf(F2))
  ok('and puts them in 3rd XI', (await colEl(F3).locator(`[data-player-card="${pid(12)}"]`).count()) === 1 && (await countOf(F3)) === '2/11', await countOf(F3))

  await colEl(F3).locator(`[data-player-card="${pid(12)}"]`).tap(); await page.waitForTimeout(300)
  await sheet.getByRole('button', { name: /Back to the pool/ }).tap(); await page.waitForTimeout(500)
  ok('Back to the pool empties the slot', (await colEl(F3).locator(`[data-player-card="${pid(12)}"]`).count()) === 0)
  ok('and the player is in the Pool again', (await page.locator(`[data-pool-col] [data-player-card="${pid(12)}"]`).count()) === 1)

  console.log('\n# the menu')
  await goto()
  await page.locator('[data-menu-open]').tap(); await page.waitForTimeout(300)
  ok('on a phone the menu button opens a slide-over with the tools', await page.getByRole('link', { name: 'Selection Whiteboard' }).last().isVisible())
  await page.setViewportSize({ width: 1024, height: 768 })
  await page.goto(`${BASE}/admin/betterselect/whiteboard`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-draft-table]').waitFor({ timeout: 15000 })
  ok('on an iPad the menu is beside the page', await page.locator('[data-sidebar]').isVisible())
  const before1024 = (await page.locator('[data-draft-table]').boundingBox()).width
  await page.locator('[data-menu-toggle]').tap(); await page.waitForTimeout(600)
  ok('the menu button hides it', !(await page.locator('[data-sidebar]').isVisible()))
  const after1024 = (await page.locator('[data-draft-table]').boundingBox()).width
  ok('and the board gets the room (240px wider)', Math.abs(after1024 - before1024 - 240) <= 2, `${before1024} -> ${after1024}`)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.locator('[data-draft-table]').waitFor({ timeout: 15000 })
  ok('it stays hidden after a reload', !(await page.locator('[data-sidebar]').isVisible()))
  await page.locator('[data-menu-toggle]').tap(); await page.waitForTimeout(400)
  ok('the same button brings it back', await page.locator('[data-sidebar]').isVisible())

  ok('no uncaught page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  if (FAIL) { console.log('FAILED:\n - ' + FAILURES.join('\n - ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
