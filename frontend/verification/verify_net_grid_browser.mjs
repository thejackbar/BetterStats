// Drives the REAL live nets screen in time-slot mode in Chromium with the API
// stubbed at the network layer (North Perth round):
//   * a session with no times shows "Set up the nets"; saving sends the plan
//     with the browser's own timezone offset
//   * the grid draws a column per net, a row per slot (club's own "4:45" style),
//     the running slot says NOW, people sit under their squad's net
//   * tap a name then tap a cell, and drag the grip onto a cell, both POST
//     exactly {attendee_id, net_id, slot_index} to /slots
//   * people who do not fit and people with no net are named in words
//   * "Nets run as" on the sessions page sends mode on create
//   * 390px: no sideways overflow of the page, grid scrolls inside its card
//
//   npx vite build --outDir /tmp/dist && npx vite preview --outDir /tmp/dist --port 5199 &
//   node verify_net_grid_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }

const SETTINGS = { duration_seconds: 600, nets: 2, auto_roll: false, sound: false, alerts: [] }
const ROSTER = {
  players: [], squads: [{ id: 's1', label: '1st', name: 'Seniors' }, { id: 's3', label: '3rd', name: 'Thirds' }], squad_count: 0,
}
const att = (id, name, net, slot, extra = {}) => ({
  id, player_id: id, name, guest_name: null, is_guest: false, batted: false, bats: true, note: null, position: 0,
  padding_up: false, priority: false, source: 'admin', net_key: net, slot_index: slot, slot_manual: false, skill_positions: [], photo_url: null, ...extra,
})

let state, wire
const mkGrid = () => {
  if (!state.configured) return { configured: false, nets: [], times: [], no_net: [], overflow_count: 0, slots: 0 }
  // Slot 0 started ten minutes ago, 7-minute slots: the running slot is 1.
  const start = new Date(Date.now() - 10 * 60000).toISOString()
  const times = ['16:45', '16:52', '16:59', '17:06', '17:13']
  const cell = (net, i) => {
    const a = state.attendees.find((x) => x.net_key === net && x.slot_index === i)
    return { slot: i, attendee_id: a ? a.id : null, repeat: false }
  }
  const nets = [
    { id: 'n1', name: '1st & 2nd XI', squad_team_ids: ['s1'], catch_all: false },
    { id: 'n2', name: '3rd & 4th XI', squad_team_ids: ['s3'], catch_all: false },
    { id: 'n3', name: 'Juniors / etc', squad_team_ids: [], catch_all: true },
  ].map((n) => ({
    ...n, cells: times.map((_, i) => cell(n.id, i)),
    overflow: state.attendees.filter((a) => a.net_key === n.id && a.slot_index == null && a.bats).map((a) => a.id),
    count: state.attendees.filter((a) => a.net_key === n.id && a.bats).length,
  }))
  return {
    configured: true, slot_minutes: 7, first_time: '16:45', finish_time: '17:20', second_go: false, slots: 5, times,
    start_at: start, now_slot: 1, nets,
    no_net: state.attendees.filter((a) => !a.net_key && a.bats).map((a) => a.id),
    overflow_count: nets.reduce((n, x) => n + x.overflow.length, 0),
  }
}
const payload = () => ({
  id: 'sess1', version: state.version, server_time: new Date().toISOString(), mode: 'auto',
  slot_plan: { first_time: state.configured ? '16:45' : null, slot_minutes: 7, finish_time: '17:20', second_go: false, tz_offset_minutes: 480, nets: [] },
  grid: mkGrid(), session_date: '2026-11-10', label: 'Tuesday nets', notes: null, status: 'active', settings: SETTINGS,
  timer: { running: false, ends_at: null, remaining_seconds: 600, duration_seconds: 600, turn_seq: 0 },
  attendees: state.attendees, attendee_count: state.attendees.length, batted_count: 0, sitting_out_count: 0,
  squad_team_ids: [], checkin_path: '/nets-checkin/tok', created_at: new Date().toISOString(),
})

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ['--no-sandbox'] })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, timezoneId: 'Australia/Perth' })
  const page = await ctx.newPage()
  page.setDefaultTimeout(5000)
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  state = {
    version: 1, configured: false,
    attendees: [
      att('a1', 'Adams, Zed', 'n1', 0), att('a2', 'Brown, Anna', 'n1', 1), att('a3', 'Cole, Cara', 'n2', 0),
      att('a4', 'Doe, Dan', 'n2', null),                       // does not fit
      att('a5', 'Eve, Ed', null, null),                         // not in a net
      att('a6', 'Fox, Finn', null, null, { bats: false, note: 'sore shoulder' }),
    ],
  }
  wire = { plan: [], slots: [], create: [] }
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'np', organisation_id: 'o1', capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' } }))
  await page.route('**/api/nets/roster', (r) => json(r, ROSTER))
  await page.route('**/api/nets/checkin-link**', (r) => json(r, { enabled: false }))
  await page.route('**/api/nets/sessions?**', (r) => json(r, { sessions: [{ id: 'sess1', session_date: '2026-11-10', label: 'Tuesday nets', status: 'active', mode: 'auto', attendee_count: 6, batted_count: 0 }] }))
  await page.route('**/api/nets/sessions/sess1/live**', (r) => {
    const since = new URL(r.request().url()).searchParams.get('since')
    if (since !== null && Number(since) === state.version) return json(r, { version: state.version, server_time: new Date().toISOString(), unchanged: true })
    return json(r, payload())
  })
  await page.route('**/api/nets/sessions/sess1/plan', (r) => {
    const b = JSON.parse(r.request().postData() || '{}')
    wire.plan.push({ method: r.request().method(), body: b })
    state.configured = true; state.version += 1
    return json(r, payload())
  })
  await page.route('**/api/nets/sessions/sess1/slots', (r) => {
    const b = JSON.parse(r.request().postData() || '{}')
    wire.slots.push(b)
    const a = state.attendees.find((x) => x.id === b.attendee_id)
    const occ = state.attendees.find((x) => x.net_key === b.net_id && x.slot_index === b.slot_index && x.id !== a.id)
    if (occ) { occ.net_key = a.net_key; occ.slot_index = a.slot_index }
    a.net_key = b.net_id; a.slot_index = b.slot_index; a.slot_manual = true; a.bats = true
    state.version += 1
    return json(r, payload())
  })
  await page.route('**/api/nets/sessions/sess1', (r) => json(r, payload()))

  await page.goto(`${BASE}/admin/betterselect/nets/sess1`)
  await page.waitForSelector('text=Tuesday nets', { timeout: 20000 })

  await safe('Unconfigured', async () => {
    console.log('\n── A session with no times yet ──')
    await page.locator('[data-grid-unconfigured]').waitFor()
    check('it asks for the nets to be set up', (await page.locator('[data-grid-unconfigured]').innerText()).includes('Set up the nets'))
    check('the batting queue and timer are not drawn', (await page.locator('[data-batting-order]').count()) === 0)
    await page.getByRole('button', { name: 'Set up the nets' }).click()
    await page.locator('[data-plan-modal]').waitFor()
    check('the editor opens with a first net time field', (await page.locator('input[aria-label="First net time"]').count()) === 1)
    check('the club\'s squads are offered on each net', (await page.locator('[data-plan-net]').first().locator('button', { hasText: '1st' }).count()) === 1)
    check('saving with no first time is held back and says why',
      (await page.getByRole('button', { name: 'Save' }).isDisabled()) && (await page.locator('[data-plan-modal]').innerText()).includes('Set the time the first net starts'))
    await page.locator('input[aria-label="First net time"]').fill('16:45')
    await page.locator('[data-plan-net]').first().locator('button', { hasText: '1st' }).click()
    await page.getByRole('button', { name: 'Save' }).click()
    await page.locator('[data-net-grid]').waitFor()
    const put = wire.plan[0]
    check('the plan goes up as a PUT', put && put.method === 'PUT', JSON.stringify(wire.plan))
    check('with the first time and slot length', put && put.body.first_time === '16:45' && put.body.slot_minutes === 7, JSON.stringify(put && put.body))
    check('the browser\'s own offset (Perth, +480)', put && put.body.tz_offset_minutes === 480, String(put && put.body.tz_offset_minutes))
    check('and the first net takes the 1st squad', put && put.body.nets[0].squad_team_ids.join() === 's1', JSON.stringify(put && put.body.nets))
  })

  await safe('The grid', async () => {
    console.log('\n── The grid ──')
    const t = await page.locator('[data-net-grid]').innerText()
    check('times are written the way the club sheet does (4:45, 4:52)', t.includes('4:45') && t.includes('4:52') && t.includes('5:13'))
    check('each net is a column with its name', t.includes('1st & 2nd XI') && t.includes('3rd & 4th XI') && t.includes('Juniors / etc'))
    const col = async (net) => (await page.locator(`[data-cell][data-net="${net}"]`).allInnerTexts()).map((x) => x.trim())
    const n1 = await col('n1')
    check('Zed is first in net 1 and Anna second', n1[0].includes('Adams, Zed') && n1[1].includes('Brown, Anna'), JSON.stringify(n1))
    check('Cara is first in net 2', (await col('n2'))[0].includes('Cole, Cara'))
    check('the running slot says NOW in words', (await page.locator('[data-slot-time="1"]').innerText()).toLowerCase().includes('now'))
    check('another slot does not', !(await page.locator('[data-slot-time="3"]').innerText()).toLowerCase().includes('now'))
    check('someone who does not fit is named, with the words "Does not fit"',
      (await page.locator('[data-net-overflow="n2"]').innerText()).includes('Does not fit') && (await page.locator('[data-net-overflow="n2"]').innerText()).includes('Doe, Dan'))
    check('a banner says how many do not fit', (await page.locator('[data-overflow-banner]').innerText()).includes('1 person'))
    check('someone with no net is listed as such', (await page.locator('[data-no-net]').innerText()).includes('Eve, Ed'))
    check('someone not batting is listed with their note', (await page.locator('[data-not-batting]').innerText()).includes('Fox, Finn') && (await page.locator('[data-not-batting]').innerText()).includes('sore shoulder'))
  })

  await safe('Tap to move', async () => {
    console.log('\n── Tap a name, tap a cell ──')
    wire.slots.length = 0
    await page.locator('[data-no-net] button', { hasText: 'Eve, Ed' }).click()
    check('picking someone up says who is being moved', (await page.locator('[data-picked-bar]').innerText()).includes('Eve, Ed'))
    await page.locator('[data-cell][data-net="n3"][data-slot="2"]').click()
    await page.waitForTimeout(400)
    check('the drop POSTs exactly attendee, net and slot', JSON.stringify(wire.slots) === JSON.stringify([{ attendee_id: 'a5', net_id: 'n3', slot_index: 2 }]), JSON.stringify(wire.slots))
    check('Ed is now drawn in net 3 and off the not-in-a-net list', (await page.locator('[data-cell][data-net="n3"][data-slot="2"]').innerText()).includes('Eve, Ed') && (await page.locator('[data-no-net]').count()) === 0)
    check('the bar is gone after the drop', (await page.locator('[data-picked-bar]').count()) === 0)
  })

  await safe('Swap by tap', async () => {
    console.log('\n── Dropping on an occupied cell swaps ──')
    wire.slots.length = 0
    await page.locator('[data-cell][data-net="n1"][data-slot="1"] button', { hasText: 'Brown, Anna' }).click()
    await page.locator('[data-cell][data-net="n1"][data-slot="0"] button', { hasText: 'Adams, Zed' }).click()
    await page.waitForTimeout(400)
    check('one POST, Anna into slot 0', JSON.stringify(wire.slots) === JSON.stringify([{ attendee_id: 'a2', net_id: 'n1', slot_index: 0 }]), JSON.stringify(wire.slots))
    check('and Zed is in slot 1 after the server answers', (await page.locator('[data-cell][data-net="n1"][data-slot="1"]').innerText()).includes('Adams, Zed'))
  })

  await safe('Drag', async () => {
    console.log('\n── Dragging the grip ──')
    wire.slots.length = 0
    const grip = page.locator('[data-cell][data-net="n2"][data-slot="0"] [data-name-chip] span').first()
    const gb = await grip.boundingBox()
    check('the grip stops the page scrolling under the finger (touch-action: none)', (await grip.evaluate((el) => getComputedStyle(el).touchAction)) === 'none')
    const target = await page.locator('[data-cell][data-net="n2"][data-slot="3"]').boundingBox()
    await page.mouse.move(gb.x + gb.width / 2, gb.y + gb.height / 2)
    await page.mouse.down()
    await page.mouse.move(gb.x + 30, gb.y + 30, { steps: 4 })
    await page.mouse.move(target.x + target.width / 2, target.y + target.height / 2, { steps: 8 })
    check('a name follows the pointer while dragging', (await page.locator('.fixed.pointer-events-none', { hasText: 'Cole, Cara' }).count()) === 1)
    await page.mouse.up()
    await page.waitForTimeout(400)
    check('the drop POSTs Cara into net 2, slot 3', JSON.stringify(wire.slots) === JSON.stringify([{ attendee_id: 'a3', net_id: 'n2', slot_index: 3 }]), JSON.stringify(wire.slots))
  })

  await safe('Phone', async () => {
    console.log('\n── 390px ──')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(300)
    const w = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, win: window.innerWidth }))
    check('the page does not scroll sideways with the grid showing', w.doc <= w.win, JSON.stringify(w))
    const inner = await page.locator('[data-net-grid] .overflow-x-auto').evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth }))
    check('the grid scrolls inside its own card instead', inner.sw > inner.cw, JSON.stringify(inner))
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/grid-390.png` : '/tmp/grid-390.png', fullPage: true })
    await page.getByRole('button', { name: 'Edit nets' }).click()
    await page.locator('[data-plan-modal]').waitFor()
    const w2 = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, win: window.innerWidth }))
    check('nor does the plan editor', w2.doc <= w2.win, JSON.stringify(w2))
    const mb = await page.locator('[data-plan-modal]').boundingBox()
    check('and it fits the screen', mb.x >= 0 && mb.x + mb.width <= 391, JSON.stringify(mb))
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/plan-390.png` : '/tmp/plan-390.png' })
    await page.keyboard.press('Escape')
    await page.locator('[data-plan-modal] button[aria-label="Close"]').click()
    await page.setViewportSize({ width: 1280, height: 900 })
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/grid-1280.png` : '/tmp/grid-1280.png', fullPage: true })
  })

  await safe('Create', async () => {
    console.log('\n── Starting a session in time-slot mode ──')
    await page.route('**/api/nets/sessions', (r) => {
      if (r.request().method() === 'POST') { wire.create.push(JSON.parse(r.request().postData() || '{}')); return json(r, { ...payload(), id: 'sess1' }) }
      return json(r, { sessions: [] })
    })
    await page.goto(`${BASE}/admin/betterselect/nets`)
    await page.getByRole('button', { name: 'Time slots' }).first().click()
    await page.getByRole('button', { name: 'Start a session' }).click()
    await page.waitForTimeout(500)
    const b = wire.create[0] || {}
    check('create sends mode auto', b.mode === 'auto', JSON.stringify(b))
    check('and the browser offset for the plan', b.slot_plan && b.slot_plan.tz_offset_minutes === 480, JSON.stringify(b.slot_plan))
  })

  check('no uncaught page errors', errors.length === 0, errors.join(' | '))
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  await browser.close()
  process.exit(FAIL ? 1 : 0)
}
run()
