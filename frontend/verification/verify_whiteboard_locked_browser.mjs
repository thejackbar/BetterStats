// Drives the REAL Selection Whiteboard in Chromium with the API stubbed at the
// network layer, including the server's lock rules (a locked side refuses its
// draft and its confirm with 409 {code: "locked"}; POST /unlock opens it;
// Confirm locks it again).
//
//   * a locked side is marked Locked on the whiteboard
//   * changing a locked side (drag out, drag in, swap, captain) asks first:
//     "<team> is locked. Are you sure you want to change it?"
//   * saying no changes nothing and sends nothing
//   * saying yes puts the change on the board, unlocks THAT side (POST /unlock)
//     and only then saves its draft; the second change asks nothing
//   * a move between a locked and an unlocked team asks about the locked one only
//   * Confirm locks the side again
//   * an unlocked side never asks
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_whiteboard_locked_browser.mjs
//   CONTROL=1 expects the build before this change: the prompt checks must fail
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
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
const F1 = '00000000-0000-4000-8000-0000000000f1'
const F2 = '00000000-0000-4000-8000-0000000000f2'
const pid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const POOL = []
for (let n = 1; n <= 20; n++) {
  POOL.push({
    id: pid(n), display_name: `Player${String.fromCharCode(64 + n)} Test`, player_role: null, skill_positions: ['BAT'],
    squads: [], squad_team_id: null, availability: 'AVAILABLE', availability_reason: null, last_played: '2099-03-01', photo_url: null,
    gender: 'male', is_dormant: false, is_inactive: false, is_current: true, selected: false, clash: [], clash_detail: [], also_in: [],
    clash_blocks: false, squad_match: false, tier: 1, gender_ok: true, recent_ok: true, score: 20 - n, recent: [],
    rule_flags: [], rule_notes: [], rule_state: 'ok',
  })
}
const FX = [
  { id: F1, label: 'Rivals', opponent_name: 'Rivals', home_away: 'HOME', played_on: DAY, start_time: '1:00pm', round: 3, venue: 'Oval', team_name: 'Club 1st XI', team_sequence: 1, grade_name: 'A Grade' },
  { id: F2, label: 'Rovers', opponent_name: 'Rovers', home_away: 'AWAY', played_on: DAY, start_time: '1:00pm', round: 3, venue: 'Park', team_name: 'Club 2nd XI', team_sequence: 2, grade_name: 'B Grade' },
]

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))

  const dialogs = []
  let answer = true
  page.on('dialog', (d) => { dialogs.push(d.message()); answer ? d.accept() : d.dismiss() })

  const server = {
    confirmed: { [F1]: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map(pid), [F2]: [12, 13, 14, 15].map(pid) },
    locked: { [F1]: true, [F2]: false },
    drafts: {},
  }
  const log = []
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const lockedErr = (r) => json(r, { detail: { code: 'locked', message: 'This side is locked. Unlock it to make changes.' } }, 409)
  const payload = (fid) => {
    const f = FX.find((x) => x.id === fid)
    return {
      fixture: { ...f, end_on: null, locked: !!server.locked[fid], home_team: 'Club', away_team: f.opponent_name, team_id: `t-${fid}`, grade_id: `g-${fid}` },
      lineup: server.confirmed[fid].map((p, i) => ({ player_id: p, batting_order: i + 1, is_captain: false, is_wicket_keeper: false })),
      pool: POOL, default_team_size: 11, rules: { active: false, applied: [], team: [] }, flags: {},
    }
  }

  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route(/\/api\/selection\/overview(\?.*)?$/, (r) => json(r, {
    default_team_size: 11,
    fixtures: FX.map((f) => ({ ...f, locked: !!server.locked[f.id], lineup: server.confirmed[f.id].map((p, i) => ({ player_id: p, display_name: 'x', batting_order: i + 1, skill_positions: [], availability: 'AVAILABLE', is_captain: false, is_wicket_keeper: false })), has_draft: !!server.drafts[f.id] })),
  }))
  await page.route(/\/api\/selection\/([0-9a-f-]{36})\/unlock$/, (r) => {
    const fid = r.request().url().match(/selection\/([0-9a-f-]{36})\/unlock/)[1]
    log.push(`unlock:${fid}`)
    server.locked[fid] = false
    return json(r, { status: 'ok', locked: false })
  })
  await page.route(/\/api\/selection\/([0-9a-f-]{36})\/draft(\?.*)?$/, async (r) => {
    const fid = r.request().url().match(/selection\/([0-9a-f-]{36})\/draft/)[1]
    const m = r.request().method()
    const cur = server.drafts[fid]
    if (m === 'PUT') {
      const b = JSON.parse(r.request().postData())
      log.push(`draft:${fid}`)
      if (server.locked[fid]) return lockedErr(r)
      server.drafts[fid] = { draft: b, version: (cur?.version || 0) + 1, by: 'Jordan Admin' }
      return json(r, { status: 'ok', version: server.drafts[fid].version })
    }
    if (m === 'DELETE') { delete server.drafts[fid]; return json(r, { status: 'ok', version: 0 }) }
    return json(r, cur ? { draft: cur.draft, version: cur.version, updated_at: new Date().toISOString(), updated_by: cur.by } : { draft: null, version: 0 })
  })
  await page.route(/\/api\/selection\/([0-9a-f-]{36})$/, async (r) => {
    const fid = r.request().url().match(/selection\/([0-9a-f-]{36})$/)[1]
    if (r.request().method() === 'PUT') {
      const b = JSON.parse(r.request().postData())
      log.push(`confirm:${fid}`)
      if (server.locked[fid]) return lockedErr(r)
      const picked = new Set(b.players.map((p) => p.player_id))
      for (const other of Object.keys(server.confirmed)) if (other !== fid) server.confirmed[other] = server.confirmed[other].filter((x) => !picked.has(x))
      server.confirmed[fid] = b.players.map((p) => p.player_id)
      if (b.lock && b.players.length) server.locked[fid] = true
      delete server.drafts[fid]
      return json(r, { status: 'ok', count: b.players.length, locked: !!server.locked[fid] })
    }
    return json(r, payload(fid))
  })

  const centre = async (loc) => { if (!(await loc.count())) return null; const b = await loc.boundingBox(); return b ? { x: b.x + b.width / 2, y: b.y + b.height / 2 } : null }
  const dragTo = async (from, to) => {
    const a = await centre(from), b = await centre(to)
    if (!a || !b) return false
    await page.mouse.move(a.x, a.y); await page.mouse.down()
    await page.mouse.move(a.x + 12, a.y + 6, { steps: 3 })
    await page.mouse.move(b.x, b.y, { steps: 10 })
    await page.mouse.up()
    await page.waitForTimeout(150)
    return true
  }
  const col = (fid) => page.locator(`[data-team-col="${fid}"]`)
  const cardIn = (fid, n) => col(fid).locator(`[data-player-card="${pid(n)}"]`)
  const slotIn = (fid, i) => col(fid).locator(`[data-slot-row="${i}"]`)
  const poolCard = (n) => page.locator(`[data-pool-col] [data-player-card="${pid(n)}"]`)
  const pool = page.locator('[data-pool-col] [data-pool-list]')
  const settle = () => page.waitForTimeout(1500)   // past the 600ms autosave pause

  await page.goto(`${BASE}/admin/betterselect/whiteboard`, { waitUntil: 'domcontentloaded' })
  ok('the whiteboard opens', await page.locator('[data-draft-table]').waitFor({ timeout: 15000 }).then(() => true).catch(() => false))
  await page.waitForTimeout(400)

  console.log('\n# a locked side says so')
  ok('1st XI is marked Locked', (await page.locator(`[data-locked-col="${F1}"]`).count()) === 1)
  ok('2nd XI is not', (await page.locator(`[data-locked-col="${F2}"]`).count()) === 0)

  console.log('\n# an unlocked side never asks')
  await dragTo(poolCard(16), slotIn(F2, 5))
  await settle()
  ok('no prompt for the unlocked side', dialogs.length === 0, JSON.stringify(dialogs))
  ok('its draft saved', log.includes(`draft:${F2}`))
  ok('nothing was unlocked', !log.some((l) => l.startsWith('unlock')))

  console.log('\n# saying no to a locked side')
  answer = false
  await dragTo(cardIn(F1, 3), pool)
  await settle()
  ok('it asked', dialogs.length === 1, JSON.stringify(dialogs))
  ok('the prompt names the locked team and asks if they are sure', /1st XI is locked\. Are you sure you want to change it\?/.test(dialogs[0] || ''), dialogs[0])
  ok('the player stays in the locked side', (await cardIn(F1, 3).count()) === 1)
  ok('nothing was unlocked', !log.some((l) => l.startsWith('unlock')))
  ok('nothing was sent for the locked side', !log.includes(`draft:${F1}`))
  ok('it is still marked Locked', (await page.locator(`[data-locked-col="${F1}"]`).count()) === 1)

  console.log('\n# saying yes to a locked side')
  answer = true
  dialogs.length = 0
  await dragTo(cardIn(F1, 3), pool)
  await settle()
  ok('it asked once', dialogs.length === 1, JSON.stringify(dialogs))
  ok('the player left the side', (await cardIn(F1, 3).count()) === 0 && (await poolCard(3).count()) === 1)
  ok('the side was unlocked', log.includes(`unlock:${F1}`))
  ok('the draft was saved AFTER the unlock', log.indexOf(`unlock:${F1}`) !== -1 && log.indexOf(`draft:${F1}`) > log.indexOf(`unlock:${F1}`), JSON.stringify(log))
  ok('the saved draft has no player 3', !(server.drafts[F1]?.draft?.slots || [pid(3)]).includes(pid(3)))
  ok('the column no longer says Locked', (await page.locator(`[data-locked-col="${F1}"]`).count()) === 0)
  ok('no "Not saving" on the side', (await page.locator('[data-draft-status="error"]').count()) === 0)

  console.log('\n# the next change asks nothing')
  dialogs.length = 0
  await dragTo(poolCard(17), slotIn(F1, 2))
  await settle()
  ok('no second prompt', dialogs.length === 0, JSON.stringify(dialogs))
  ok('player 17 is in the side', (await cardIn(F1, 17).count()) === 1)

  console.log('\n# Confirm locks it again')
  await col(F1).locator(`[data-confirm-col="${F1}"]`).click()
  await settle()
  ok('confirmed', server.confirmed[F1].includes(pid(17)) && !server.confirmed[F1].includes(pid(3)))
  ok('the server locked it again', server.locked[F1] === true)
  ok('and the column says Locked again', (await page.locator(`[data-locked-col="${F1}"]`).count()) === 1)

  console.log('\n# a move from an unlocked team into a locked one')
  dialogs.length = 0
  log.length = 0
  ok('drag 2nd XI player onto an open slot of the locked 1st XI', await dragTo(cardIn(F2, 13), slotIn(F1, 10)))
  await settle()
  ok('it asked about the 1st XI only', dialogs.length === 1 && /^1st XI is locked\./.test(dialogs[0]) && !/2nd XI/.test(dialogs[0]), JSON.stringify(dialogs))
  ok('the player moved', (await cardIn(F1, 13).count()) === 1 && (await cardIn(F2, 13).count()) === 0)
  ok('only the locked side was unlocked', log.filter((l) => l.startsWith('unlock')).join() === `unlock:${F1}`, JSON.stringify(log))
  ok('both drafts saved', log.includes(`draft:${F1}`) && log.includes(`draft:${F2}`))

  console.log('\n# captain on a locked side')
  await page.getByRole('button', { name: /Confirm all/ }).click()
  await settle()
  ok('both confirmed and the 1st XI is locked again', server.locked[F1] === true && (await page.locator(`[data-locked-col="${F1}"]`).count()) === 1)
  dialogs.length = 0
  await cardIn(F1, 1).hover()
  await cardIn(F1, 1).locator('button[title="Captain"]').click()
  await settle()
  ok('naming a captain asks first', dialogs.length === 1 && /is locked/.test(dialogs[0]), JSON.stringify(dialogs))
  ok('the captain is saved in the draft', server.drafts[F1]?.draft?.captain_id === pid(1))

  ok('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed${CONTROL ? ' (control run: failures are expected)' : ''}`)
  if (FAIL) console.log('Failed:\n - ' + FAILURES.join('\n - '))
  process.exit(CONTROL ? 0 : FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(2) })
