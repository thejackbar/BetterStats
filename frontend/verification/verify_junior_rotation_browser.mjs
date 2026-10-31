// Drives the REAL Junior Rotation screens in Chromium with the API stubbed at the
// network layer: the group list and create form, a draft (hand edits, re-roll,
// lock, unlock, a 409 conflict), the kids, the season table, settings and the
// parent link, the print sheet and the public parent page. Asserts the exact
// request each control puts on the wire, and checks 390px for overflow.
//
//   npx vite build && npx vite preview --port 5199 --strictPort &
//   node verification/verify_junior_rotation_browser.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.env.BASE || 'http://localhost:5199'
const SHOTS = process.env.SHOTS || ''
let PASS = 0, FAIL = 0
const FAILURES = []
function check(label, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (ok) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); console.log(`  FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`) }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
async function until(fn, ms = 4000) {
  const t = Date.now()
  while (Date.now() - t < ms) { if (await fn()) return true; await sleep(60) }
  return false
}

// ── The fake backend ─────────────────────────────────────────────────────────
const KIDS = [['k1', 'Sam Taylor'], ['k2', 'Ava Brown'], ['k3', 'Noah Smith'], ['k4', 'Mia Jones']]
const mkPlayers = () => KIDS.map(([id, name]) => ({ id, name, avoid_positions: [], note: null, former_at: null }))
const POS = [{ id: 'pa', name: 'Pitcher', key: true }, { id: 'pb', name: '1st base', key: true }, { id: 'pc', name: 'Left field', key: false }]
const today = new Date().toISOString().slice(0, 10)
const mkRound = (over = {}) => ({
  id: 'r1', group_id: 'g1', round_date: today, label: 'vs Bayswater', fixture_id: null, status: 'draft',
  present: ['k1', 'k2', 'k3', 'k4'], batting_order: ['k1', 'k2', 'k3', 'k4'],
  fielding: [{ k1: 'pa', k2: 'pb', k3: 'pc', k4: null }], warnings: [], version: 1, locked_at: null, ...over,
})

let S, wire
function reset() {
  S = {
    group: { id: 'g1', name: 'U8 Tee Ball', kind: 'tee_ball', positions: POS.map((p) => ({ ...p })), innings: 1, fairness: 60, bats: true,
      public_enabled: false, public_show_surnames: false, public_path: null, archived: false },
    players: mkPlayers(),
    round: mkRound(),
    conflictNext: false,
    publicDead: false,
  }
  wire = []
}
const last = (m, re) => [...wire].reverse().find((w) => w.m === m && re.test(w.path))

async function install(page) {
  const json = (route, o, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(o) })
  // Catch-all FIRST: Playwright matches the most recently registered route first.
  await page.route(/\/api\//, (r) => json(r, {}))
  await page.route(/\/api\/auth\/me/, (r) => json(r, {
    id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1',
    capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' },
  }))
  await page.route(/\/api\/(public\/)?rotation\b/, async (route) => {
    const req = route.request()
    const u = new URL(req.url())
    const path = u.pathname.replace(/^\/api/, '')
    const m = req.method()
    const body = req.postData() ? JSON.parse(req.postData()) : null
    wire.push({ m, path, body, search: u.search })
    const full = () => ({ group: S.group, players: S.players })
    let x
    if (m === 'GET' && path === '/rotation/presets') return json(route, { presets: [
      { key: 'tee_ball', label: 'Tee ball', innings: 1, positions: POS.map(({ name, key }) => ({ name, key })) },
      { key: 'junior_cricket', label: 'Junior cricket', innings: 1, positions: [{ name: 'Wicketkeeper', key: true }] },
      { key: 'custom', label: 'Start blank', innings: 1, positions: [] }] })
    if (m === 'GET' && path === '/rotation/groups') return json(route, { groups: [{ ...S.group, player_count: 4, locked_rounds: 2, last_round: today }] })
    if (m === 'POST' && path === '/rotation/groups') return json(route, full())
    if (m === 'GET' && path === '/rotation/groups/g1') return json(route, full())
    if (m === 'PATCH' && path === '/rotation/groups/g1') {
      Object.assign(S.group, body)
      if (body.public_enabled) S.group.public_path = '/rotation/tok123'
      if (body.positions) S.group.positions = body.positions.map((p, i) => ({ id: p.id || `new${i}`, name: p.name, key: !!p.key }))
      return json(route, full())
    }
    if (m === 'POST' && path === '/rotation/groups/g1/regenerate-link') { S.group.public_path = '/rotation/tok456'; return json(route, full()) }
    if (m === 'POST' && path === '/rotation/groups/g1/players') {
      const added = body.names.split(/[\n,]/).map((n) => n.trim()).filter(Boolean)
      added.forEach((n, i) => S.players.push({ id: `n${i}`, name: n, avoid_positions: [], note: null, former_at: null }))
      return json(route, { added: added.length, returned: 0, skipped: 0, players: S.players })
    }
    if (m === 'PATCH' && (x = path.match(/^\/rotation\/players\/(\w+)$/))) {
      const p = S.players.find((q) => q.id === x[1])
      if ('active' in body) p.former_at = body.active ? null : new Date().toISOString()
      if ('avoid_positions' in body) p.avoid_positions = body.avoid_positions
      if ('name' in body) p.name = body.name
      return json(route, { player: p })
    }
    if (m === 'GET' && path === '/rotation/fixtures') return json(route, { fixtures: [{ id: 'f1', date: '2031-04-12', team: 'U8 Gold', opponent: 'Wanneroo', round: '3', label: null, home_away: 'HOME', start_time: '09:00' }] })
    if (m === 'GET' && path === '/rotation/groups/g1/rounds') return json(route, { rounds: S.round ? [S.round] : [] })
    if (m === 'POST' && path === '/rotation/groups/g1/rounds') {
      S.round = mkRound({ id: 'r2', label: body.label, round_date: body.round_date, fixture_id: body.fixture_id, present: body.present, batting_order: body.present, fielding: [{}] })
      return json(route, { round: S.round })
    }
    if (m === 'GET' && (x = path.match(/^\/rotation\/rounds\/(\w+)$/))) return json(route, { round: S.round, group: S.group, players: S.players })
    if (m === 'PUT' && path.startsWith('/rotation/rounds/')) {
      if (S.conflictNext) {
        S.conflictNext = false
        S.round = mkRound({ label: 'Server version', version: 9, batting_order: ['k4', 'k3', 'k2', 'k1'] })
        return json(route, { detail: { code: 'conflict', message: 'Someone else changed this round. Reload to see their version.', round: S.round } }, 409)
      }
      const { version, ...rest } = body
      S.round = { ...S.round, ...rest, version: S.round.version + 1 }
      return json(route, { round: S.round })
    }
    if (m === 'POST' && path.endsWith('/generate')) { S.round = { ...S.round, batting_order: [...S.round.batting_order].reverse(), version: S.round.version + 1 }; return json(route, { round: S.round }) }
    if (m === 'POST' && path.endsWith('/lock')) { S.round = { ...S.round, status: 'locked', locked_at: new Date().toISOString(), version: S.round.version + 1 }; return json(route, { round: S.round }) }
    if (m === 'POST' && path.endsWith('/unlock')) { S.round = { ...S.round, status: 'draft', locked_at: null, version: S.round.version + 1 }; return json(route, { round: S.round }) }
    if (m === 'DELETE' && path.startsWith('/rotation/rounds/')) { S.round = null; return json(route, { ok: true }) }
    if (m === 'GET' && path === '/rotation/groups/g1/tally') return json(route, {
      rounds: 3, spread: { key_turns: 1, rests: 1 },
      players: [
        { id: 'k1', name: 'Sam Taylor', former: false, games: 3, bat_first: 1, bat_last: 0, bat_avg: 0.33, rests: 1, field: { pa: 1, pb: 1, pc: 0 }, key_turns: 2 },
        { id: 'k2', name: 'Ava Brown', former: false, games: 3, bat_first: 0, bat_last: 2, bat_avg: 0.83, rests: 0, field: { pa: 1, pb: 1, pc: 1 }, key_turns: 2 },
      ] })
    if (m === 'GET' && path === '/public/rotation/tok123') {
      if (S.publicDead) return json(route, { detail: 'This link isn\'t active' }, 404)
      return json(route, { club: 'Applecross CC', group: { name: 'U8 Tee Ball', bats: true }, rounds: [
        { date: today, label: 'vs Bayswater', batting: ['Sam T.', 'Ava B.'], changes: [{ slots: [{ position: 'Pitcher', key: true, name: 'Sam T.' }, { position: 'Left field', key: false, name: null }], resting: ['Mia J.'] }] },
        { date: '2031-01-05', label: null, batting: ['Ava B.'], changes: [] }] })
    }
    return json(route, {})
  })
}

const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
const opts = process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {}

const run = async () => {
  reset()
  const browser = await chromium.launch(opts)
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('dialog', (d) => d.accept())
  await install(page)
  const shot = async (name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }) } }

  console.log('\n── The list and the create form ──')
  await page.goto(`${BASE}/admin/betterselect/rotation`)
  await page.waitForSelector('[data-groups]', { timeout: 20000 })
  check('the group is listed with its counts', (await page.locator('[data-group="U8 Tee Ball"]').innerText()).includes('4 kids'), true)
  check('and says how many games are locked', (await page.locator('[data-group="U8 Tee Ball"]').innerText()).includes('2 games locked'), true)
  await page.click('button:has-text("New group")')
  await page.waitForSelector('[data-create-group]')
  check('the preset note names the positions', (await page.locator('[data-preset-note]').innerText()).includes('Pitcher'), true)
  await page.fill('#rot-name', 'Kanga Group')
  await page.click('button:has-text("Junior cricket")')
  await page.fill('#rot-names', 'Ollie Nguyen\nIsla Roberts')
  await page.click('button:has-text("Create group")')
  check('create sends the name, preset and the pasted names', last('POST', /^\/rotation\/groups$/)?.body, { name: 'Kanga Group', preset: 'junior_cricket', names: 'Ollie Nguyen\nIsla Roberts' })
  check('and opens the new group', await until(async () => page.url().includes('/admin/betterselect/rotation/g1')), true)

  console.log('\n── Game day: a draft ──')
  await page.waitForSelector('[data-round="r1"]', { timeout: 15000 })
  check('the draft is open and says DRAFT', (await page.locator('[data-round]').innerText()).includes('DRAFT'), true)
  check('four kids in the batting order', await page.locator('[data-bat-row]').count(), 4)
  check('three positions in the field', await page.locator('[data-slot]').count(), 3)
  check('the resting kid is named in words', (await page.locator('[data-resting]').innerText()).includes('Mia Jones'), true)
  check('key positions say KEY in text', await page.locator('[data-slot]:has-text("KEY")').count(), 2)
  await shot('rotation-draft-desktop')

  await page.selectOption('select[aria-label="Pitcher"]', 'k3')
  check('picking Noah for Pitcher swaps with the holder, on the wire',
    await until(() => !!last('PUT', /rounds\/r1$/)), true)
  check('the PUT carries the version and the swapped field', last('PUT', /rounds\/r1$/)?.body, { version: 1, fielding: [{ k1: 'pc', k2: 'pb', k3: 'pa', k4: null }] })
  check('the screen shows the swap', await page.locator('select[aria-label="Pitcher"]').inputValue(), 'k3')
  await page.selectOption('select[aria-label="1st base"]', '')
  await until(() => wire.filter((w) => w.m === 'PUT').length === 2)
  check('choosing Nobody rests the holder, version moves on', last('PUT', /rounds\/r1$/)?.body, { version: 2, fielding: [{ k1: 'pc', k2: null, k3: 'pa', k4: null }] })
  check('and Ava is now listed as resting', (await page.locator('[data-resting]').innerText()).includes('Ava Brown'), true)

  await page.click('button[aria-label="Move Sam Taylor down"]')
  await until(() => wire.filter((w) => w.m === 'PUT').length === 3)
  check('moving a kid down sends the new order', last('PUT', /rounds\/r1$/)?.body, { version: 3, batting_order: ['k2', 'k1', 'k3', 'k4'] })
  check('the first row is Ava, the top Up arrow is disabled', await page.locator('[data-bat-row]').first().innerText().then((t) => t.includes('Ava Brown')), true)
  check('the first row cannot move up', await page.locator('button[aria-label="Move Ava Brown up"]').isDisabled(), true)

  await page.click('[data-present] >> text=Mia Jones')
  await until(() => wire.filter((w) => w.m === 'PUT').length === 4)
  check('unticking a kid sends the present list without them', last('PUT', /rounds\/r1$/)?.body, { version: 4, present: ['k1', 'k2', 'k3'] })

  await page.click('[data-reroll="batting"]')
  await until(() => !!last('POST', /generate$/))
  check('re-rolling the batting order names the part and the version', last('POST', /generate$/)?.body, { part: 'batting', version: 5 })

  console.log('\n── A conflict shows the other version ──')
  S.conflictNext = true
  await page.click('button[aria-label="Move Noah Smith up"]')
  await page.waitForSelector('text=Someone else changed this round', { timeout: 5000 })
  check('the screen adopts the server version', await page.locator('[data-round]').innerText().then((t) => t.includes('Server version')), true)

  console.log('\n── Lock, and a locked game is read only ──')
  await page.click('[data-lock]')
  await page.waitForSelector('[data-round-status="locked"]')
  check('the lock request is sent', !!last('POST', /lock$/), true)
  check('it says LOCKED and explains it counts towards the season', (await page.locator('[data-locked-note]').innerText()).includes('counts towards the season'), true)
  check('and that the parent link is off', (await page.locator('[data-locked-note]').innerText()).includes('Turn on the parent link'), true)
  check('no position pickers on a locked game', await page.locator('select[aria-label="Pitcher"]').count(), 0)
  check('no re-roll buttons on a locked game', await page.locator('[data-reroll]').count(), 0)
  check('the lineup is still shown', await page.locator('[data-bat-row]').count() > 0, true)
  check('Unlock is offered', await page.locator('[data-unlock]').count(), 1)
  await shot('rotation-locked-desktop')
  await page.click('[data-unlock]')
  await page.waitForSelector('[data-round-status="draft"]')
  check('unlock goes to the server', !!last('POST', /unlock$/), true)

  console.log('\n── A new game from a fixture ──')
  await page.click('[data-round-list] >> text=+ New game')
  await page.waitForSelector('[data-new-game]')
  await page.selectOption('#rot-fixture', 'f1')
  check('picking a fixture fills the date and label', [await page.inputValue('#rot-date'), await page.inputValue('#rot-label')], ['2031-04-12', 'vs Wanneroo'])
  await page.click('[data-present] >> text=Mia Jones')
  await page.click('button:has-text("Generate lineup")')
  await until(() => !!last('POST', /groups\/g1\/rounds$/))
  check('generate sends date, label, fixture and who is here', last('POST', /groups\/g1\/rounds$/)?.body,
    { round_date: '2031-04-12', label: 'vs Wanneroo', fixture_id: 'f1', present: ['k1', 'k2', 'k3'] })
  await page.waitForSelector('[data-round="r2"]')

  console.log('\n── Kids ──')
  await page.click('button:has-text("Kids")')
  await page.waitForSelector('[data-kids]')
  check('the four kids are listed', await page.locator('[data-kid]').count(), 4)
  await page.fill('textarea[aria-label="Names to add"]', 'Leo Wilson, Ella Davis')
  await page.click('button:has-text("Add kids")')
  await until(() => !!last('POST', /players$/))
  check('adding sends the pasted text as is', last('POST', /players$/)?.body, { names: 'Leo Wilson, Ella Davis' })
  check('the new kids appear', await until(async () => (await page.locator('[data-kid="Leo Wilson"]').count()) === 1), true)
  await page.click('[data-kid="Sam Taylor"] summary')
  await page.click('[data-kid="Sam Taylor"] >> button:has-text("Pitcher")')
  await until(() => !!last('PATCH', /players\/k1$/))
  check('keeping a kid out of Pitcher sends the avoid list', last('PATCH', /players\/k1$/)?.body, { avoid_positions: ['pa'] })
  await page.click('[data-kid="Ava Brown"] >> [data-leave]')
  await until(() => wire.some((w) => w.m === 'PATCH' && /players\/k2$/.test(w.path)))
  check('a kid who leaves is patched inactive, not deleted', last('PATCH', /players\/k2$/)?.body, { active: false })
  check('they move to the left-the-group list', await page.locator('[data-former]').innerText().then((t) => t.includes('Kids who have left (1)')), true)

  console.log('\n── Season ──')
  await page.click('button:has-text("Season")')
  await page.waitForSelector('[data-tally]')
  check('the sentence says how even it is', (await page.locator('[data-season-summary]').innerText()).includes('3 locked games'), true)
  check('and the spread', (await page.locator('[data-season-summary]').innerText()).includes('1 rest and 1 key-position turn apart'), true)
  check('the table has a row per kid', await page.locator('[data-tally-row]').count(), 2)
  check('Ava led off 0 times, batted last twice', await page.locator('[data-tally-row="Ava Brown"]').innerText().then((t) => /0\s+2/.test(t.replace(/\s+/g, ' '))), true)
  // The header row is CSS uppercase, so innerText comes back uppercase.
  check('key positions are starred in the header', /pitcher ★/i.test(await page.locator('[data-tally] thead').innerText()), true)

  console.log('\n── Settings and the parent link ──')
  await page.click('button:has-text("Settings")')
  await page.waitForSelector('[data-positions]')
  check('the link starts off with no URL shown', await page.locator('[data-link-url]').count(), 0)
  await page.fill('#rot-gname', 'U8 Tee Ball Gold')
  await page.selectOption('#rot-innings', '3')
  await page.click('[data-save-settings]')
  await until(() => wire.some((w) => w.m === 'PATCH' && w.path === '/rotation/groups/g1' && 'innings' in w.body))
  check('settings go as one PATCH', last('PATCH', /groups\/g1$/)?.body, { name: 'U8 Tee Ball Gold', innings: 3, fairness: 60, bats: true })
  await page.click('[data-add-position]')
  await page.fill('input[aria-label="Position 4 name"]', 'Right field')
  await page.click('[data-save-positions]')
  await until(() => wire.some((w) => w.m === 'PATCH' && w.body && w.body.positions))
  const posBody = wire.filter((w) => w.m === 'PATCH' && w.body && w.body.positions).pop().body.positions
  check('a new position is sent with no id, the old ones keep theirs', [posBody.length, posBody[0].id, posBody[3].id, posBody[3].name], [4, 'pa', undefined, 'Right field'])
  await page.click('[data-link-enabled]')
  await page.waitForSelector('[data-link-url]')
  check('turning the link on sends public_enabled', last('PATCH', /groups\/g1$/)?.body, { public_enabled: true })
  check('and shows the full address', (await page.locator('[data-link-url]').inputValue()).endsWith('/rotation/tok123'), true)
  await page.click('[data-link-surnames]')
  await until(() => wire.some((w) => w.m === 'PATCH' && w.body && 'public_show_surnames' in w.body))
  check('surnames are their own switch', last('PATCH', /groups\/g1$/)?.body, { public_show_surnames: true })
  await shot('rotation-settings-desktop')

  console.log('\n── The print sheet ──')
  S.round = mkRound({ status: 'locked' })
  await page.goto(`${BASE}/admin/betterselect/rotation/g1/print/r1`)
  await page.waitForSelector('[data-batting-order]', { timeout: 15000 })
  check('the sheet has the batting order and the field (four positions after the settings test)', [await page.locator('[data-bat-row]').count(), await page.locator('[data-slot]').count()], [4, 4])
  check('it names the group, label and date', await page.locator('h1').innerText(), 'U8 Tee Ball Gold')
  check('there is a Print button that stays off the paper', await page.locator('.rot-no-print [data-print-now]').count(), 1)
  check('no admin sidebar on the sheet', await page.locator('nav').count(), 0)
  check('the sheet is on the light theme', await page.locator('[data-theme="light"]').count() > 0, true)

  console.log('\n── The parent page (no login) ──')
  await page.goto(`${BASE}/rotation/tok123`)
  await page.waitForSelector('[data-group-name]', { timeout: 15000 })
  check('shows the club and the group', [await page.locator('[data-group-name]').innerText()], ['U8 Tee Ball'])
  check('lists names as sent (first name and initial)', (await page.locator('[data-batting-order]').innerText()).includes('Sam T.'), true)
  check('a position nobody holds reads Nobody', (await page.locator('[data-slot]:has-text("Left field")').innerText()).includes('Nobody'), true)
  check('the resting kid is named', (await page.locator('[data-resting]').innerText()).includes('Mia J.'), true)
  check('earlier games are one tap away', await page.locator('[data-round-picker] button').count(), 2)
  await page.click('[data-round-picker] button:nth-child(2)')
  check('picking an earlier game shows its batting order', (await page.locator('[data-batting-order]').innerText()).includes('Ava B.'), true)
  check('the public page carries no admin chrome', await page.locator('text=Re-roll').count(), 0)
  check('the public page shows no ids in its text', /k\d|\bg1\b|\br1\b/.test(await page.locator('body').innerText()), false)
  await shot('rotation-public-desktop')
  S.publicDead = true
  await page.reload()
  await page.waitForSelector('[data-dead]', { timeout: 15000 })
  check('a dead link says so plainly', (await page.locator('[data-dead]').innerText()).includes('isn’t active'), true)

  console.log('\n── 390px: nothing overflows ──')
  S.publicDead = false
  S.round = mkRound()
  await page.setViewportSize({ width: 390, height: 844 })
  for (const [name, path, sel] of [
    ['list', '/admin/betterselect/rotation', '[data-groups]'],
    ['game day', '/admin/betterselect/rotation/g1', '[data-round]'],
    ['print', '/admin/betterselect/rotation/g1/print/r1', '[data-batting-order]'],
    ['parent page', '/rotation/tok123', '[data-batting-order]'],
  ]) {
    await page.goto(`${BASE}${path}`)
    await page.waitForSelector(sel, { timeout: 15000 })
    await sleep(250)
    check(`${name} has no horizontal overflow at 390px`, await overflow(page), false)
    await shot(`rotation-${name.replace(' ', '-')}-390`)
  }
  for (const tab of ['Kids', 'Season', 'Settings']) {
    await page.goto(`${BASE}/admin/betterselect/rotation/g1`)
    await page.waitForSelector('[data-round]', { timeout: 15000 })
    await page.click(`button:has-text("${tab}")`)
    await sleep(400)
    check(`${tab} tab has no horizontal overflow at 390px`, await overflow(page), false)
    await shot(`rotation-${tab.toLowerCase()}-390`)
  }

  console.log('\n── No page errors ──')
  check('no page errors', errors, [])

  await browser.close()
  console.log(`\n${'='.repeat(60)}\n${PASS} passed, ${FAIL} failed`)
  if (FAILURES.length) { console.log('\nFailures:'); FAILURES.forEach((f) => console.log('  -', f)) }
  process.exit(FAIL ? 1 : 0)
}

run().catch((e) => { console.error(e); process.exit(1) })
