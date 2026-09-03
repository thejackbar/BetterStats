// Drives the REAL net session screen: dragging the batting order with a
// finger, the padding-up flag, and the question ticking priority asks.
//
// THE DRAG IS THE POINT OF THIS SUITE. It is driven twice — once with real
// browser-generated pointer events (Playwright's mouse), and once with
// synthetic ones carrying `pointerType: 'touch'`, because an iPad is the
// device this screen is actually run from and the HTML5 drag API fires
// nothing there at all. Playwright cannot simulate the browser's own
// touch-action arbitration, so the thing that makes a touch drag start —
// `touch-action: none` on the handle — is measured off the computed style
// instead of inferred from the drag working with a mouse.
//
// The API is stubbed at the network layer, and the stub MUTATES on every
// write: one that answers the same thing each time can't tell a working
// toggle from a no-op.
import { chromium } from 'playwright'

const BASE = 'http://localhost:5199'
let PASS = 0, FAIL = 0
const FAILURES = []
function check(label, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (ok) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); console.log(`  FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`) }
}

const NAMES = ['Barendse, Jack', 'Mant, Brad', 'Cole, Graeme', 'Sawatzky, Cameron', 'Watt, Matthew', 'Gill, Amardeep']
// `.map` hands over (value, index) — getting these the wrong way round makes
// every attendee's name a NUMBER, and the screen dies inside Avatar a long way
// from the cause. A stub that returns the wrong SHAPE measures a broken page.
const att = (name, i) => ({
  id: `a${i + 1}`, player_id: null, guest_name: null, name, photo_url: null,
  skill_positions: [], is_guest: false, batted: false, bats: true, note: null,
  position: i, padding_up: false, priority: false, source: 'admin',
})

let state, wire

function fresh() {
  state = {
    id: 's1', version: 1, session_date: '2026-09-03', label: 'Thursday senior nets',
    notes: null, status: 'active', unchanged: false,
    settings: { duration_seconds: 600, nets: 2, auto_roll: false, sound: false, alerts: [] },
    timer: { running: false, ends_at: null, remaining_seconds: 600, duration_seconds: 600, turn_seq: 0 },
    attendees: NAMES.map(att),
    attendee_count: 6, batted_count: 0, sitting_out_count: 0, created_at: null,
  }
  wire = { reorder: [], patch: [], liveDuringDrag: 0, countLive: false }
}

const payload = () => ({ ...state, server_time: new Date().toISOString(), attendee_count: state.attendees.length })
const orderNow = () => state.attendees.filter((a) => !a.batted && a.bats).map((a) => a.name)
const idOf = (name) => state.attendees.find((a) => a.name === name).id

async function setup(page) {
  page.on('pageerror', (e) => { FAILURES.push(`page error: ${e.message}${process.env.STACK ? '\n' + e.stack : ''}`); FAIL++ })

  // REGEXES, NOT GLOBS. Playwright's `**` does not cross a `?`, so a glob
  // route for the live poll silently loses `…/live?since=3` to the catch-all —
  // which hands the screen `{}` and takes it down. Worth knowing: the symptom
  // is a page crash a long way from the route that caused it.
  //
  // Catch-all FIRST — routes are matched in reverse registration order.
  await page.route(/\/api\//, (r) => r.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  await page.route(/\/api\/auth\/me/, (r) => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ id: 'u1', username: 'coach', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1', capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' } }),
  }))
  await page.route(/\/api\/nets\/roster/, (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ players: [], squad_count: 0 }) }))
  await page.route(/\/api\/nets\/checkin-link/, (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ enabled: false }) }))
  await page.route(/\/api\/nets\/sessions\/s1(\?|$)/, (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload()) }))
  await page.route(/\/api\/nets\/sessions\/s1\/live/, (r) => {
    if (wire.countLive) wire.liveDuringDrag += 1
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload()) })
  })
  await page.route(/\/api\/nets\/sessions\/s1\/queue/, (r) => {
    const body = JSON.parse(r.request().postData() || '{}')
    wire.reorder.push(body.ids)
    // Apply it the way the server would, so the screen can't pass on a
    // response that quietly disagrees with what was asked for.
    const waiting = state.attendees.filter((a) => !a.batted && a.bats)
    const rest = state.attendees.filter((a) => a.batted || !a.bats)
    const seen = []
    body.ids.forEach((x) => { const m = waiting.find((a) => a.id === x); if (m && !seen.includes(m)) seen.push(m) })
    waiting.forEach((a) => { if (!seen.includes(a)) seen.push(a) })
    state.attendees = [...seen, ...rest]
    state.version += 1
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload()) })
  })
  await page.route(/\/api\/nets\/sessions\/s1\/attendees\//, (r) => {
    const id = r.request().url().split('/').pop()
    const body = JSON.parse(r.request().postData() || '{}')
    wire.patch.push({ id, body })
    const row = state.attendees.find((a) => a.id === id)
    if (row) Object.entries(body).forEach(([k, v]) => { row[k] = v })
    state.version += 1
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload()) })
  })
}

const rows = (page) => page.locator('[data-batting-order] [data-att]')
const namesOnScreen = async (page) => (await rows(page).evaluateAll(
  (els) => els.map((e) => (e.querySelector('.font-display') || {}).textContent || '')
))

async function centre(page) {
  await page.locator('[data-batting-order]').scrollIntoViewIfNeeded()
  // Auto-scroll fires within 96px of either edge, so keep the whole drag well
  // clear of them — this suite is measuring reordering, not the edge scroll.
  await page.evaluate(() => window.scrollBy(0, -80))
  await page.waitForTimeout(120)
}

// A finger. Synthetic PointerEvents in SEPARATE evaluate calls, because React
// has to re-render between them or every drop reads as refused — the trap this
// repo's roster notes describe.
async function dragTouch(page, fromName, toName) {
  await centre(page)
  const grip = await page.locator(`[data-att="${idOf(fromName)}"] [data-grip]`).boundingBox()
  const dst = await page.locator(`[data-att="${idOf(toName)}"]`).boundingBox()
  const down = { x: grip.x + grip.width / 2, y: grip.y + grip.height / 2 }
  const up = { x: down.x, y: dst.y + dst.height / 2 + (dst.y > grip.y ? 6 : -6) }
  const send = (type, pt) => page.evaluate(([t, x, y]) => {
    const init = { bubbles: true, cancelable: true, clientX: x, clientY: y, pointerId: 1, pointerType: 'touch', button: 0, isPrimary: true }
    const target = t === 'pointerdown' ? document.elementFromPoint(x, y) : window
    target.dispatchEvent(new PointerEvent(t, init))
  }, [type, pt.x, pt.y])
  await send('pointerdown', down)
  await page.waitForTimeout(60)
  await send('pointermove', { x: down.x, y: (down.y + up.y) / 2 })
  await page.waitForTimeout(60)
  await send('pointermove', up)
  await page.waitForTimeout(60)
  return { send, up }
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1100 } })
  const page = await ctx.newPage()
  fresh()
  await setup(page)

  await page.goto(`${BASE}/admin/betterselect/nets/s1`)
  // A CONTROL RUN HAS TO REPORT, NOT CRASH. With the change absent there is no
  // batting-order card at all, and dying on the first missing locator would
  // say nothing about which of the three features is gone. So the card is
  // waited for once, and if it never arrives the suite names every part that
  // is missing and stops there.
  const arrived = await page.waitForSelector('[data-batting-order]', { timeout: 25000 })
    .then(() => true).catch(() => false)
  check('the batting order card is on the screen', arrived, true)
  if (!arrived) {
    for (const [label, sel] of [
      ['a drag handle on each row', '[data-grip]'],
      ['a padding-up control', 'button[aria-label*="Padding up"]'],
      ['a priority control', 'button[aria-label*="Priority"]'],
      ['the in-the-nets line under the clock', '[data-hero-line="nets"]'],
      ['the padding-up line under the clock', '[data-hero-line="padding"]'],
    ]) check(label, await page.locator(sel).count() > 0, true)
    await browser.close()
    console.log(`\n${'='.repeat(60)}\n${PASS} passed, ${FAIL} failed`)
    FAILURES.forEach((f) => console.log('  -', f))
    process.exit(1)
  }
  await page.waitForTimeout(400)

  console.log('\n── One list, from the nets down ──')
  check('every waiting player is in the one order', await namesOnScreen(page), NAMES)
  check('the card is the batting order', await page.locator('text=Batting order').count() > 0, true)
  check('the two in the nets are badged', await page.locator('[data-batting-order] >> text=NET 1').count(), 1)
  check('and the second net too', await page.locator('[data-batting-order] >> text=NET 2').count(), 1)
  check('no third net is badged', await page.locator('[data-batting-order] >> text=NET 3').count(), 0)
  check('the header counts both halves', await page.locator('text=2/2 in · 4 waiting').count() > 0, true)

  console.log('\n── The one thing that makes a touch drag start ──')
  const ta = await page.locator('[data-att="a1"] [data-grip]').evaluate((el) => getComputedStyle(el).touchAction)
  check('the handle takes the gesture instead of scrolling the page', ta, 'none')
  const rowTa = await page.locator('[data-att="a1"]').evaluate((el) => getComputedStyle(el).touchAction)
  check('but the row itself still scrolls normally', rowTa !== 'none', true)

  console.log('\n── Dragging with a finger ──')
  await dragTouch(page, 'Gill, Amardeep', 'Barendse, Jack')
  check('the row lands in net 1 before the finger lifts',
    (await namesOnScreen(page))[0], 'Gill, Amardeep')
  await page.evaluate(() => window.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, pointerId: 1, pointerType: 'touch' })))
  await page.waitForTimeout(500)
  check('the whole new order goes on the wire', wire.reorder.at(-1),
    ['a6', 'a1', 'a2', 'a3', 'a4', 'a5'])
  check('THE LAST NAME IN THE QUEUE IS NOW IN A BATTING SPOT',
    (await namesOnScreen(page))[0], 'Gill, Amardeep')
  check('and it stayed there once the write landed',
    await page.locator('[data-att="a6"] >> text=NET 1').count(), 1)

  console.log('\n── Dragging with a real mouse ──')
  await centre(page)
  {
    const before = wire.reorder.length
    // Where a5 sits RIGHT NOW, not where it started — the touch drag above has
    // already moved the list, and an index hardcoded from the original order
    // measures the harness rather than the drag.
    const target = (await namesOnScreen(page)).indexOf('Watt, Matthew')
    const grip = await page.locator('[data-att="a2"] [data-grip]').boundingBox()
    const dst = await page.locator('[data-att="a5"]').boundingBox()
    await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2)
    await page.mouse.down()
    await page.mouse.move(grip.x + grip.width / 2, dst.y, { steps: 6 })
    await page.mouse.move(grip.x + grip.width / 2, dst.y + dst.height / 2 + 6, { steps: 4 })
    await page.mouse.up()
    await page.waitForTimeout(500)
    check('a mouse drag writes an order too', wire.reorder.length, before + 1)
    check('and Mant lands where he was dropped', (await namesOnScreen(page)).indexOf('Mant, Brad'), target)
  }

  console.log('\n── A poll must not pull the row out from under the finger ──')
  {
    await centre(page)
    const start = await namesOnScreen(page)
    const { send, up } = await dragTouch(page, start[5], start[0])
    wire.countLive = true
    // Longer than the 2.5s poll interval: without the guard this is where the
    // server's older order would be adopted and the drag undone.
    await page.waitForTimeout(3400)
    check('no poll ran while the finger was down', wire.liveDuringDrag, 0)
    check('and the dragged row is still where it was put',
      (await namesOnScreen(page))[0], start[5])
    await send('pointerup', up)
    await page.waitForTimeout(600)
    // Count again from zero, or "it came back" would be reading the same
    // zero the guard produced and could never fail.
    wire.liveDuringDrag = 0
    await page.waitForTimeout(3200)
    check('the poll comes straight back once it is over', wire.liveDuringDrag > 0, true)
    wire.countLive = false
  }

  console.log('\n── The order is reachable without a pointer ──')
  {
    const before = await namesOnScreen(page)
    await page.locator(`[data-att="${idOf(before[3])}"] [data-grip]`).focus()
    await page.keyboard.press('ArrowUp')
    await page.waitForTimeout(400)
    check('the arrow keys move a focused row', (await namesOnScreen(page)).indexOf(before[3]), 2)
  }

  console.log('\n── Padding up ──')
  {
    fresh()
    await page.reload()
    await page.waitForSelector('[data-batting-order]')
    await page.waitForTimeout(400)
    check('the hero says nobody is flagged yet',
      await page.locator('[data-nets-hero] >> text=/Nobody flagged/').count() > 0, true)

    await page.locator('[data-att="a4"] button[aria-label*="Padding up"]').click()
    await page.waitForTimeout(400)
    check('the exact flag goes on the wire', wire.patch.at(-1), { id: 'a4', body: { padding_up: true } })
    check('the row says so in words, not only colour',
      await page.locator('[data-att="a4"] >> text=PADDING UP').count(), 1)
    check('and the name is up beside the clock, on the padding-up line',
      await page.locator('[data-hero-line="padding"] >> text=Sawatzky, Cameron').count() > 0, true)
    check('under its own heading', await page.locator('[data-hero-line="padding"] >> text=Padding up').count() > 0, true)

    // Somebody already IN a net is not padding up — they have padded up and
    // gone in. The row says NET 1, not PADDING UP.
    await page.locator('[data-att="a1"] button[aria-label*="Padding up"]').click()
    await page.waitForTimeout(400)
    check('flagging someone already in a net writes the flag', wire.patch.at(-1).id, 'a1')
    check('but the row still reads as being in the net',
      await page.locator('[data-att="a1"] >> text=NET 1').count(), 1)
    check('and it is not also called padding up',
      await page.locator('[data-att="a1"] >> text=PADDING UP').count(), 0)
    // Scoped to the padding-up LINE, not the whole hero: they are of course
    // named up there, on the "in the nets" line right above it. A check
    // against the whole block would pass with the bug and fail without it.
    check('nor named on the padding-up line',
      await page.locator('[data-hero-line="padding"] >> text=Barendse, Jack').count(), 0)
    check('while the nets line does name them',
      await page.locator('[data-hero-line="nets"] >> text=Barendse, Jack').count(), 1)

    await page.locator('[data-att="a4"] button[aria-label*="Not padding up"]').click()
    await page.waitForTimeout(400)
    check('un-flagging sends the opposite', wire.patch.at(-1), { id: 'a4', body: { padding_up: false } })
    check('and the row drops the mark',
      await page.locator('[data-att="a4"] >> text=PADDING UP').count(), 0)
  }

  console.log('\n── Ticking priority asks a question ──')
  {
    fresh()
    await page.reload()
    await page.waitForSelector('[data-batting-order]')
    await page.waitForTimeout(400)
    const before = await namesOnScreen(page)

    await page.locator('[data-att="a5"] button[aria-label*="Priority — needs"]').click()
    await page.waitForSelector('text=Just flag them')
    check('the tick alone sends NOTHING', wire.patch.length, 0)
    check('it asks about the person by name',
      await page.locator('text=Watt, Matthew').count() > 0, true)
    check('it offers to move them up', await page.locator('button:has-text("Bat next")').count() > 0, true)
    check('and to leave the order alone', await page.locator('button:has-text("Just flag them")').count() > 0, true)

    // Dismissing must not write anything either.
    await page.keyboard.press('Escape').catch(() => {})
    await page.locator('.fixed.inset-0').first().click({ position: { x: 8, y: 8 } })
    await page.waitForTimeout(300)
    check('dismissing it writes nothing', wire.patch.length, 0)
    check('and nothing was reordered', wire.reorder.length, 0)

    await page.locator('[data-att="a5"] button[aria-label*="Priority — needs"]').click()
    await page.waitForSelector('text=Just flag them')
    await page.fill('input[placeholder*="Leaving at 7"]', 'leaving at 7')
    await page.click('button:has-text("Just flag them")')
    await page.waitForTimeout(500)
    check('JUST FLAG writes the flag and the reason', wire.patch.at(-1),
      { id: 'a5', body: { priority: true, note: 'leaving at 7' } })
    check('AND MOVES NOBODY', wire.reorder.length, 0)
    check('the order is exactly what it was', await namesOnScreen(page), before)
    check('the row carries the word', await page.locator('[data-att="a5"] >> text=PRIORITY').count(), 1)
    check('and the reason is on the row', await page.locator('[data-att="a5"] >> text=leaving at 7').count(), 1)

    // Un-ticking is just an un-tick — no question to ask.
    await page.locator('[data-att="a5"] button[aria-label="Clear priority"]').click()
    await page.waitForTimeout(400)
    check('un-ticking opens no dialog', await page.locator('text=Just flag them').count(), 0)
    check('and clears the flag on the wire', wire.patch.at(-1), { id: 'a5', body: { priority: false } })
  }

  console.log('\n── Bat next goes behind whoever is in the nets ──')
  {
    // Nets idle: the front of the list IS the front of the line.
    fresh()
    await page.reload()
    await page.waitForSelector('[data-batting-order]')
    await page.waitForTimeout(400)
    await page.locator('[data-att="a6"] button[aria-label*="Priority — needs"]').click()
    await page.waitForSelector('text=Just flag them')
    check('the dialog says the plain rule while the nets are idle',
      await page.locator('text=/moves them to the front of the line\\./').count() > 0, true)
    await page.click('button:has-text("Bat next")')
    await page.waitForTimeout(600)
    check('with nobody batting they go straight to net 1', wire.reorder.at(-1)[0], 'a6')

    // A turn under way: the top two are IN, and dropping somebody above them
    // would swap out a batter mid-knock — and have the next rotation mark the
    // new arrival as having batted when they never went in.
    fresh()
    state.timer = { running: true, ends_at: new Date(Date.now() + 300000).toISOString(), remaining_seconds: 300, duration_seconds: 600, turn_seq: 1 }
    await page.reload()
    await page.waitForSelector('[data-batting-order]')
    await page.waitForTimeout(500)
    await page.locator('[data-att="a6"] button[aria-label*="Priority — needs"]').click()
    await page.waitForSelector('text=Just flag them')
    check('the dialog says who they go behind',
      await page.locator('text=/behind whoever is in the nets right now/').count() > 0, true)
    await page.click('button:has-text("Bat next")')
    await page.waitForTimeout(600)
    check('THE TWO IN THE NETS ARE NOT DISPLACED', wire.reorder.at(-1).slice(0, 2), ['a1', 'a2'])
    check('and the priority player is first in the line behind them', wire.reorder.at(-1)[2], 'a6')
  }

  console.log('\n── The key names the new controls ──')
  {
    fresh()
    await page.reload()
    await page.waitForSelector('[data-batting-order]')
    await page.waitForTimeout(400)
    for (const label of ['Drag to move', 'Padding up', 'Priority', 'Bat next', 'Mark as batted', 'Not batting', 'Remove']) {
      check(`the key explains “${label}”`, await page.locator(`[data-batting-order] >> text=${label}`).first().count() > 0, true)
    }
  }

  console.log('\n── A tap target you can hit in the dark ──')
  {
    const box = await page.locator('[data-att="a3"] button[aria-label*="Padding up"]').boundingBox()
    check('the flag buttons are at least 34px square', Math.min(box.width, box.height) >= 34, true)
  }

  console.log('\n── No page errors, and no sideways scroll on a phone ──')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(400)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check('no horizontal overflow at 390px', over <= 0, true)

  await browser.close()
  console.log(`\n${'='.repeat(60)}\n${PASS} passed, ${FAIL} failed`)
  if (FAILURES.length) { console.log('\nFailures:'); FAILURES.forEach((f) => console.log('  -', f)) }
  process.exit(FAIL ? 1 : 0)
}

// Print what was collected even when the run dies part-way: a suite that says
// nothing about the other forty checks is no use as a control run either.
run().catch((e) => {
  console.error(e)
  if (FAILURES.length) { console.log('\nCollected before the crash:'); FAILURES.forEach((f) => console.log('  -', f)) }
  process.exit(1)
})
