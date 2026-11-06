// Drives the REAL Selection Whiteboard in Chromium (API stubbed at the network
// layer) to prove the sideways scroll helpers:
//   * a window too narrow for every team shows a big scrollbar and Previous/Next team arrows
//   * Next team lines the next team up beside the pinned pool; Previous goes back; each
//     arrow is disabled at its end of the board
//   * a window wide enough for every team shows no arrows
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_whiteboard_scroll_arrows_browser.mjs
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
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
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


  const open = async (w, h) => {
    await page.setViewportSize({ width: w, height: h })
    await page.goto(`${BASE}/admin/betterselect/whiteboard`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-draft-table]').waitFor({ timeout: 15000 })
    await page.waitForTimeout(500)
  }
  const board = () => page.evaluate(() => {
    const el = document.querySelector('[data-draft-table]')
    const pool = document.querySelector('[data-pool-col]').getBoundingClientRect()
    return {
      left: el.scrollLeft, over: el.scrollWidth - el.clientWidth, barH: el.offsetHeight - el.clientHeight,
      poolRight: pool.right,
      teamLefts: [...document.querySelectorAll('[data-team-col]')].map((c) => Math.round(c.getBoundingClientRect().left)),
    }
  })
  const state = async () => ({
    back: await page.locator('[data-board-back]').isDisabled().then((d) => !d).catch(() => null),
    forward: await page.locator('[data-board-forward]').isDisabled().then((d) => !d).catch(() => null),
  })
  const click = async (sel) => { await page.locator(sel).click(); await page.waitForTimeout(700) }

  console.log('\n# 1024x768 (iPad held sideways): not every team fits')
  await open(1024, 768)
  let b = await board()
  ok('the board is wider than the window', b.over > 0, JSON.stringify(b))
  ok('the sideways scrollbar is big enough to grab (14px or more)', b.barH >= 14, `bar ${b.barH}px`)
  ok('the arrows are showing', (await page.locator('[data-board-nav]').count()) === 1)
  let s = await state()
  ok('at the start Previous is off and Next is on', s.back === false && s.forward === true, JSON.stringify(s))
  await page.screenshot({ path: join(SHOTS, 'whiteboard_arrows_1024_start.png') })

  await click('[data-board-forward]')
  b = await board()
  ok('Next team lines the 2nd team up beside the pool', Math.abs(b.teamLefts[1] - (b.poolRight + 10)) <= 3, JSON.stringify(b))
  ok('the pool stays pinned while the teams move', b.left > 0)
  s = await state()
  ok('after Next, Previous is on', s.back === true, JSON.stringify(s))
  await page.screenshot({ path: join(SHOTS, 'whiteboard_arrows_1024_next.png') })

  for (let i = 0; i < 4 && (await state()).forward; i++) await click('[data-board-forward]')
  b = await board()
  s = await state()
  ok('at the far end Next is off', s.forward === false, JSON.stringify(s))
  ok('the last team is fully on screen', b.over - b.left <= 2, JSON.stringify(b))

  await click('[data-board-back]')
  const back1 = await board()
  ok('Previous moves the board back', back1.left < b.left, `${b.left} -> ${back1.left}`)
  for (let i = 0; i < 4 && (await state()).back; i++) await click('[data-board-back]')
  b = await board()
  ok('Previous all the way returns to the start', b.left <= 2 && (await state()).back === false, JSON.stringify(b))

  console.log('\n# 1920x1080: every team fits')
  await open(1920, 1080)
  b = await board()
  ok('nothing to scroll', b.over <= 1, JSON.stringify(b))
  ok('no arrows when everything fits', (await page.locator('[data-board-nav]').count()) === 0)
  const fit = await page.evaluate(() => [...document.querySelectorAll('[data-team-list]')].map((l) => [l.scrollHeight, l.clientHeight]))
  ok('no team list scrolls at 1920x1080', fit.every(([sh, ch]) => sh <= ch + 1), JSON.stringify(fit))

  ok('no uncaught page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  if (FAIL) { console.log('FAILED:\n - ' + FAILURES.join('\n - ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
