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
// 16:45 plus the (possibly stretched) slot lengths: where each slot starts, in minutes.
const startsOf = () => { let t = 16 * 60 + 45; return state.lens.map((l) => { const out = t; t += l; return out }) }
const hhmm = (m) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
const mkGrid = () => {
  if (!state.configured) return { configured: false, nets: [], times: [], no_net: [], overflow_count: 0, slots: 0 }
  // The first slot began `elapsedMin` minutes ago.
  const start = new Date(Date.now() - state.elapsedMin * 60000).toISOString()
  const starts = startsOf()
  const times = starts.map(hhmm)
  const offsets = [0]; state.lens.forEach((l) => offsets.push(offsets[offsets.length - 1] + l))
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
    configured: true, slot_minutes: 7, first_time: '16:45', finish_time: '17:20', second_go: false, pad_up_seconds: 120, slots: times.length, times,
    offsets, custom_slots: state.lens.map((l, i) => (l !== 7 ? i : null)).filter((x) => x != null),
    start_at: start, now_slot: 1, nets,
    no_net: state.attendees.filter((a) => !a.net_key && a.bats).map((a) => a.id),
    overflow_count: nets.reduce((n, x) => n + x.overflow.length, 0),
  }
}
const payload = () => ({
  id: 'sess1', version: state.version, server_time: new Date().toISOString(), mode: state.mode || 'auto',
  slot_plan: { first_time: state.configured ? '16:45' : null, slot_minutes: 7, finish_time: '17:20', second_go: false, pad_up_seconds: 120, tz_offset_minutes: 480, nets: [] },
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
    version: 1, configured: false, elapsedMin: 10, lens: [7, 7, 7, 7, 7],
    attendees: [
      att('a1', 'Adams, Zed', 'n1', 0), att('a2', 'Brown, Anna', 'n1', 1), att('a3', 'Cole, Cara', 'n2', 0),
      att('a7', 'Gray, Gus', 'n1', 2),
      att('a4', 'Doe, Dan', 'n2', null),                       // does not fit
      att('a5', 'Eve, Ed', null, null),                         // not in a net
      att('a6', 'Fox, Finn', null, null, { bats: false, note: 'sore shoulder' }),
    ],
  }
  wire = { plan: [], slots: [], create: [], times: [], patch: [] }
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
  await page.route('**/api/nets/sessions/sess1/slot-time', (r) => {
    const b = JSON.parse(r.request().postData() || '{}')
    wire.times.push(b)
    const [h, m] = b.time.split(':').map(Number)
    const want = h * 60 + m
    if (b.slot_index > 0) state.lens[b.slot_index - 1] = want - startsOf()[b.slot_index - 1]
    state.version += 1
    return json(r, payload())
  })
  await page.route('**/api/nets/sessions/sess1', (r) => {
    if (r.request().method() === 'PATCH') {
      const b = JSON.parse(r.request().postData() || '{}')
      wire.patch.push(b)
      if (b.mode) state.mode = b.mode
    }
    return json(r, payload())
  })

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

  const reloadAt = async (elapsedMin) => {
    state.elapsedMin = elapsedMin
    await page.goto(`${BASE}/admin/betterselect/nets/sess1`)
    await page.locator('[data-net-grid]').waitFor({ timeout: 20000 })
  }
  const bgOf = (sel) => page.locator(sel).first().evaluate((el) => getComputedStyle(el).backgroundColor)

  await safe('Now and next', async () => {
    console.log('\n── The strip at the top and the shading ──')
    await reloadAt(10)                                   // slot 1 (4:52) has 4 minutes left
    const now = await page.locator('[data-hero-line="now"]').innerText()
    check('who is in now: the people in the running slot', now.includes('Brown, Anna') && /in now/i.test(now), now)
    check('a net with nobody in the slot says nobody', /nobody/.test(now))
    const next = await page.locator('[data-hero-line="next"]').innerText()
    check('who is next, with the time, outside the pad up window', next.includes('Gray, Gus') && /4:59/.test(next) && /next/i.test(next), next)
    check('no pad up line yet', (await page.locator('[data-hero-line="pad"]').count()) === 0)
    const timer = await page.locator('[data-slot-timer]').innerText()
    check('the timer counts down the running slot', /this slot ends in/i.test(timer) && /\b[34]:\d\d\b/.test(timer), timer)
    check('the rows carry their state as a word and an attribute', JSON.stringify(await page.locator('[data-row-state]').evaluateAll((els) => els.map((e) => e.dataset.rowState))) === JSON.stringify(['past', 'now', 'next', '', '']))
    check('the running row is shaded', (await bgOf('[data-cell][data-slot="1"]')) !== 'rgba(0, 0, 0, 0)')
    check('the next row is shaded too, and differently', (await bgOf('[data-cell][data-slot="2"]')) !== 'rgba(0, 0, 0, 0)' && (await bgOf('[data-cell][data-slot="2"]')) !== (await bgOf('[data-cell][data-slot="1"]')))
    check('a row after that is not shaded', (await bgOf('[data-cell][data-slot="4"]')) === 'rgba(0, 0, 0, 0)')
    check('a slot that has gone is dimmed', (await page.locator('[data-cell][data-slot="0"]').first().evaluate((el) => getComputedStyle(el).opacity)) === '0.55')
    const key = await page.locator('[data-grid-key]').innerText()
    check('a key names every shade in words', /in now/i.test(key) && /pad up/i.test(key) && /next/i.test(key), key)
    check('no alarm is showing', (await page.locator('[data-alarm-banner]').count()) === 0)
  })

  await safe('Pad up', async () => {
    console.log('\n── Padding up ──')
    await reloadAt(12.5)                                 // 90 seconds left, inside the 2 minute window
    const pad = await page.locator('[data-hero-line="pad"]').innerText()
    check('inside the window the next line becomes PAD UP, with the names', /pad up/i.test(pad) && pad.includes('Gray, Gus'), pad)
    check('and the next row is shaded as pad up', (await page.locator('[data-slot-time="2"]').getAttribute('data-row-state')) === 'pad')
    check('opening the page inside the window does not sound the alarm for it', (await page.locator('[data-alarm-banner]').count()) === 0)
    await reloadAt(14 - 122 / 60)                        // 122 seconds left: the window opens in two seconds
    await page.locator('[data-alarm-banner="Pad up"]').waitFor({ timeout: 8000 })
    const banner = await page.locator('[data-alarm-banner="Pad up"]').innerText()
    check('the pad up alarm names who is next', /Next:/.test(banner) && banner.includes('Gray, Gus (1st & 2nd XI)'), banner)
    check('and says so once, not every second', (await page.locator('[data-alarm-banner="Pad up"]').count()) === 1)
  })

  await safe('Change over', async () => {
    console.log('\n── The change over ──')
    await reloadAt(14 - 3 / 60)                          // three seconds to the change
    await page.locator('[data-alarm-banner="Change over"]').waitFor({ timeout: 9000 })
    const banner = await page.locator('[data-alarm-banner="Change over"]').innerText()
    check('the change over alarm says who is in now', /In now:/.test(banner) && banner.includes('Gray, Gus'), banner)
    check('and the strip has moved on to that slot', (await page.locator('[data-hero-line="now"]').innerText()).includes('Gray, Gus'))
    check('the row state follows', (await page.locator('[data-slot-time="2"]').getAttribute('data-row-state')) === 'now')
    wire.patch.length = 0
    await page.locator('[data-alarm-toggle]').click()
    await page.waitForTimeout(300)
    check('the alarm switch sends the session\'s sound setting', wire.patch.length === 1 && wire.patch[0].settings && typeof wire.patch[0].settings.sound === 'boolean', JSON.stringify(wire.patch))
    await reloadAt(10)
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

  await safe('Edit a time', async () => {
    console.log('\n── Click a time ──')
    check('the screen says times can be clicked', /click a time to change it/i.test(await page.locator('[data-time-hint]').innerText()))
    wire.times.length = 0
    await page.locator('[data-time-edit="2"]').click()
    await page.locator('[data-time-input="2"]').fill('17:01')
    await page.locator('[data-time-input="2"]').press('Enter')
    await page.waitForTimeout(500)
    check('one POST with the slot and the new time, nothing else', JSON.stringify(wire.times) === JSON.stringify([{ slot_index: 2, time: '17:01' }]), JSON.stringify(wire.times))
    const t = await page.locator('[data-slot-time]').allInnerTexts()
    check('that row now starts at 5:01 and the rows below moved with it', /5:01/.test(t[2]) && /5:08/.test(t[3]) && /5:15/.test(t[4]), JSON.stringify(t))
    check('the row after a stretched slot is marked as changed', /underline/.test(await page.locator('[data-time-edit="2"]').getAttribute('class')))
    check('and the header says a slot was changed', /1 changed/.test(await page.locator('[data-net-grid]').innerText()))
    wire.times.length = 0
    await page.locator('[data-time-edit="3"]').click()
    await page.locator('[data-time-input="3"]').fill('17:40')
    await page.locator('[data-time-input="3"]').press('Escape')
    await page.waitForTimeout(300)
    check('Escape cancels without sending anything', wire.times.length === 0 && (await page.locator('[data-time-input]').count()) === 0)
  })

  await safe('Print', async () => {
    console.log('\n── Printing ──')
    const btn = page.locator('[data-print-btn]')
    check('the session has a Print button that opens a new tab', (await btn.getAttribute('href')) === '/admin/betterselect/nets/sess1/print' && (await btn.getAttribute('target')) === '_blank')
    await page.goto(`${BASE}/admin/betterselect/nets/sess1/print`)
    await page.locator('[data-print-grid]').waitFor({ timeout: 20000 })
    const g = await page.locator('[data-print-grid]').innerText()
    check('the sheet has the times and a column per net', /4:45/.test(g) && /1st & 2nd XI/.test(g) && /3rd & 4th XI/.test(g) && /Juniors \/ etc/.test(g), g)
    check('and the names where they sit', g.includes('Adams, Zed') && g.includes('Cole, Cara'))
    check('who does not fit is written under it', /Does not fit/.test(await page.locator('[data-print-overflow]').innerText()))
    check('there is no admin chrome on the sheet', !/Check in players/.test(await page.locator('body').innerText()))
    check('the sheet is set to print landscape', /size: landscape/.test(await page.locator('style').allInnerTexts().then((x) => x.join(' '))))
    check('the Print button is there on screen', (await page.locator('[data-print-now]').isVisible()))
    await page.emulateMedia({ media: 'print' })
    check('and left off the paper', !(await page.locator('[data-print-now]').isVisible()))
    await page.emulateMedia({ media: 'screen' })
    await page.goto(`${BASE}/admin/betterselect/nets/sess1`)
    await page.locator('[data-net-grid]').waitFor()
  })

  await safe('Switch', async () => {
    console.log('\n── Switching how the night is run ──')
    check('the switcher offers both ways', (await page.locator('[data-mode-switch] button').allInnerTexts()).join('|') === 'Queue|Time slots')
    wire.patch.length = 0
    page.once('dialog', (d) => d.accept())
    await page.locator('[data-mode-switch] button', { hasText: 'Queue' }).click()
    await page.waitForTimeout(500)
    check('going back to the queue PATCHes just the mode', JSON.stringify(wire.patch) === JSON.stringify([{ mode: 'manual' }]), JSON.stringify(wire.patch))
    state.mode = 'auto'
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
