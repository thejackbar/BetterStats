// The Club Diary season plan — dragging a task along the timeline, and the
// "+ Add task" dialog — against the REAL screen with the API stubbed at the
// network layer.
//
// What is asserted:
//   * "+ Add task" sits on the SAME LINE as the search box and starts after it.
//     Measured off the two real boxes: a check that only asked "are both on the
//     page" would pass with the button still up on the title line.
//   * the dialog holds the caret character by character. `fill()` sets the value
//     in one shot and so cannot catch a component declared inside a render.
//   * the EXACT payloads on the wire — POST /definitions, then PATCH on the
//     occurrence /board minted for it — and that Cancel sends nothing at all.
//   * a bar dragged N pixels writes the day it was DROPPED on, computed from
//     the track's own measured width, with the span preserved.
//   * a due marker (a generated occurrence has a due date and no start) moves
//     the due date ALONE — never a start date nobody set.
//   * a drag does not open the task drawer; a plain click on the same bar does.
//   * a refused write puts the bar back where it was.
//   * no page errors, and no horizontal overflow at 390px.
//
//   node verify_club_diary_browser.mjs   (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

// The club starts its diary year in July, so the season drawn is 2026/27 and
// the timeline's day 0 is 1 July 2026. Every expected date below is derived
// from that rather than typed, so the arithmetic is the thing under test.
const SEASON_START = Date.UTC(2026, 6, 1)
const SEASON_DAYS = 365
const dayOf = (iso) => Math.round((Date.parse(iso) - SEASON_START) / 86400000)
const isoOfDay = (d) => new Date(SEASON_START + d * 86400000).toISOString().slice(0, 10)

const BAR = { start: '2026-09-01', due: '2026-10-01' }   // a task with both dates
const MARK = { due: '2026-11-15' }                        // due date only

const board = () => ([
  { id: 'd1', title: 'Ground lease review', frequency: 'annual', description: null, category_id: null,
    responsibility_role_id: 'r1', default_assignee_member_id: null, third_party: null,
    budget_estimate: 0, is_active: true, reminder_enabled: false, reminder_days_before: 14, depends_on: [],
    occurrence: { id: 'o1', definition_id: 'd1', period_label: '2026', status: 'pending', percent_complete: 0,
      start_date: BAR.start, due_date: BAR.due, budget_estimate: 0, actual_expenditure: 0,
      assigned_to_member_id: null, assigned_to_role_id: 'r1', third_party: null, notes: null,
      estimated_completion_date: null, over_budget: false, is_late: false, completed_at: null } },
  { id: 'd2', title: 'Renew public liability', frequency: 'annual', description: null, category_id: null,
    responsibility_role_id: null, default_assignee_member_id: null, third_party: null,
    budget_estimate: 0, is_active: true, reminder_enabled: false, reminder_days_before: 14, depends_on: [],
    occurrence: { id: 'o2', definition_id: 'd2', period_label: '2026', status: 'pending', percent_complete: 0,
      start_date: null, due_date: MARK.due, budget_estimate: 0, actual_expenditure: 0,
      assigned_to_member_id: null, assigned_to_role_id: null, third_party: null, notes: null,
      estimated_completion_date: null, over_budget: false, is_late: false, completed_at: null } },
])

// ── The stub ────────────────────────────────────────────────────────────────
// `state` lets one test add a row (the new definition and the occurrence /board
// mints for it) so the screen re-reads exactly what a real server would answer.
const routes = (page, wire, state) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url(), method = req.method()
  const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
  if (method !== 'GET') {
    let body = null
    try { body = JSON.parse(req.postData() || 'null') } catch { /* not JSON */ }
    wire.push({ method, url, body })
  }

  if (url.includes('/auth/me')) {
    return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
                  entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } })
  }
  if (/\/club-diary\/board/.test(url)) return json({ tasks: state.board })
  if (/\/club-diary\/definitions/.test(url)) {
    if (method === 'POST') {
      if (state.refuseDefinition) return json({ detail: 'A task called "Ground lease review" already exists' }, 422)
      const body = JSON.parse(req.postData() || '{}')
      const def = { id: 'd9', depends_on: [], is_active: true, ...body }
      // What /board does for a brand-new definition: mint this period's
      // occurrence, due on the first of its default month.
      state.board = state.board.concat([{ ...def, occurrence: {
        id: 'o9', definition_id: 'd9', period_label: '2026', status: 'pending', percent_complete: 0,
        start_date: null, due_date: body.default_month ? `2026-${String(body.default_month).padStart(2, '0')}-01` : null,
        budget_estimate: body.budget_estimate, actual_expenditure: null, assigned_to_member_id: null,
        assigned_to_role_id: body.responsibility_role_id, third_party: body.third_party, notes: null,
        estimated_completion_date: null, over_budget: false, is_late: false, completed_at: null } }])
      return json(def)
    }
    return json({ definitions: state.board.map(({ occurrence, ...d }) => d) })
  }
  if (/\/club-diary\/categories/.test(url)) {
    if (method === 'POST') return json({ id: 'c9', name: JSON.parse(req.postData()).name, sort_order: 0, color: '#8b7cf6' })
    return json({ categories: [{ id: 'c1', name: 'Compliance', sort_order: 0, color: '#ef4444' }] })
  }
  if (/\/club-diary\/occurrences\//.test(url)) {
    if (state.refusePatch) return json({ detail: 'nope' }, 500)
    const id = url.split('/occurrences/')[1].split('?')[0]
    const fields = JSON.parse(req.postData() || '{}')
    let out = null
    state.board = state.board.map(r => {
      if (!r.occurrence || r.occurrence.id !== id) return r
      out = { ...r.occurrence, ...fields }
      return { ...r, occurrence: out }
    })
    return json(out || {})
  }
  if (/\/club-diary\/season-years/.test(url)) return json({ years: [2026] })
  if (/\/roles/.test(url)) return json({ roles: [{ id: 'r1', title: 'Secretary', role_type_name: 'Committee', is_committee: true }] })
  if (/\/fees\/all-members/.test(url)) return json({ members: [{ member_id: 'm1', full_name: 'Bev Naylor' }] })
  if (/\/club-admin\/settings/.test(url)) return json({ diary_start_month: 7 })
  if (/\/seasons/.test(url)) return json([{ id: 'se1', name: 'Summer 2026/27', year: 2026 }])
  return json({})
})

// ── Measurement helpers ─────────────────────────────────────────────────────
const box = (page, sel) => page.evaluate((s) => {
  const el = document.querySelector(s)
  if (!el) return null
  const r = el.getBoundingClientRect()
  return { x: r.x, y: r.y, w: r.width, h: r.height, right: r.right, bottom: r.bottom, mid: r.y + r.height / 2 }
}, sel)

const findBtn = (page, text) => page.evaluate((t) => {
  const el = [...document.querySelectorAll('button')].find(b => (b.textContent || '').trim() === t)
  if (!el) return null
  const r = el.getBoundingClientRect()
  return { x: r.x, y: r.y, w: r.width, h: r.height, right: r.right, bottom: r.bottom, mid: r.y + r.height / 2 }
}, text)

// The bar / marker for one task, found by the aria-label the row carries.
const trackEl = (title) => `[aria-label^="${title} — "]`
const noOverflow = (page) => page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth)

// A pointer drag across `dx` px. Playwright's mouse dispatches real pointer
// events, which is what this gesture listens for — an HTML5 dragstart/drop pair
// reports nothing in between and could not drive a bar at all.
async function dragBy(page, sel, dx) {
  const b = await box(page, sel)
  if (!b) return null
  const y = b.y + b.h / 2, x = b.x + b.w / 2
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x + dx, y, { steps: 12 })
  await page.mouse.up()
  await page.waitForTimeout(350)
  return b
}

// The track a bar sits in — its width is what turns pixels into days, so the
// expectation is derived from the same number the screen used.
const trackWidth = (page, sel) => page.evaluate((s) => {
  const el = document.querySelector(s)
  return el && el.parentElement ? el.parentElement.getBoundingClientRect().width : 0
}, sel)

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const errors = [], wire = []
  const state = { board: board(), refusePatch: false, refuseDefinition: false }
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page, wire, state)

  const open = async () => {
    await page.goto(BASE + '/admin/club-diary', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(1400)
  }
  const posts = (re) => wire.filter(w => re.test(w.url))

  // ── The screen, and where the button landed ───────────────────────────────
  await open()
  check('Club Diary renders', (await page.textContent('h1'))?.includes('Club Diary'))
  const bodyText = await page.textContent('body')
  check('both tasks are on the plan', bodyText.includes('Ground lease review') && bodyText.includes('Renew public liability'))

  {
    const search = await box(page, 'input[placeholder^="Search tasks"]')
    const add = await findBtn(page, '+ Add task')
    check('"+ Add task" is on the page', !!add, JSON.stringify(add))
    // ONE LINE means the two boxes overlap vertically — not merely that both
    // exist. A button still up on the title line would pass a weaker check.
    const sameLine = !!search && !!add && add.y < search.bottom && search.y < add.bottom
    check('"+ Add task" sits on the same line as the search box', sameLine,
      `search ${JSON.stringify(search)} add ${JSON.stringify(add)}`)
    check('"+ Add task" sits to the RIGHT of the search box', !!search && !!add && add.x >= search.right,
      `search right ${search?.right} add x ${add?.x}`)
  }

  // ── Dragging a bar reschedules the task ───────────────────────────────────
  {
    const sel = trackEl('Ground lease review')
    await page.locator(sel).scrollIntoViewIfNeeded()
    const before = await box(page, sel)
    const trackW = await trackWidth(page, sel)
    const dx = 200
    const shift = Math.round((dx / trackW) * SEASON_DAYS)
    wire.length = 0
    await dragBy(page, sel, dx)
    const patch = posts(/\/occurrences\/o1/)[0]
    check('dragging a bar writes the occurrence', !!patch, JSON.stringify(wire))
    check('the bar lands on the day it was dropped on', !!patch && patch.body &&
      patch.body.start_date === isoOfDay(dayOf(BAR.start) + shift) &&
      patch.body.due_date === isoOfDay(dayOf(BAR.due) + shift),
      `shift ${shift} sent ${JSON.stringify(patch?.body)} expected ${isoOfDay(dayOf(BAR.start) + shift)} → ${isoOfDay(dayOf(BAR.due) + shift)}`)
    check('the span is preserved', !!patch && patch.body &&
      dayOf(patch.body.due_date) - dayOf(patch.body.start_date) === dayOf(BAR.due) - dayOf(BAR.start),
      JSON.stringify(patch?.body))
    const after = await box(page, sel)
    check('the bar moved on screen, by about what was dragged', !!after && !!before &&
      Math.abs((after.x - before.x) - dx) < 12, `moved ${after && before ? (after.x - before.x) : null}px of ${dx}px`)
    check('the same width', !!after && !!before && Math.abs(after.w - before.w) < 4,
      `${before?.w} → ${after?.w}`)
    // A drag ends in a click on the same element. Without the guard, every
    // reschedule would also throw the drawer open.
    check('a drag does not open the task drawer', !(await page.locator('text=DEPENDS ON').count()))
  }

  // ── A plain click on the same bar still opens it ──────────────────────────
  {
    const sel = trackEl('Ground lease review')
    await page.click(sel)
    await page.waitForTimeout(300)
    check('a click without a drag opens the task drawer', !!(await page.locator('text=DEPENDS ON').count()))
    await page.keyboard.press('Escape').catch(() => {})
    await page.click('body', { position: { x: 5, y: 400 } }).catch(() => {})
    await page.waitForTimeout(250)
  }

  // ── A due date with no start moves on its own ─────────────────────────────
  await open()
  {
    const sel = trackEl('Renew public liability')
    await page.locator(sel).scrollIntoViewIfNeeded()
    const trackW = await trackWidth(page, sel)
    const dx = -120
    const shift = Math.round((dx / trackW) * SEASON_DAYS)
    wire.length = 0
    await dragBy(page, sel, dx)
    const patch = posts(/\/occurrences\/o2/)[0]
    check('dragging a due marker writes the occurrence', !!patch, JSON.stringify(wire))
    check('the due date moves to the day it was dropped on', !!patch && patch.body &&
      patch.body.due_date === isoOfDay(dayOf(MARK.due) + shift),
      `shift ${shift} sent ${JSON.stringify(patch?.body)}`)
    // A start date nobody set is not ours to invent.
    check('a start date is NOT invented for it', !!patch && patch.body && !('start_date' in patch.body),
      JSON.stringify(patch?.body))
  }

  // ── A refused write puts the bar back ─────────────────────────────────────
  await open()
  {
    const sel = trackEl('Ground lease review')
    await page.locator(sel).scrollIntoViewIfNeeded()
    state.refusePatch = true
    const before = await box(page, sel)
    await dragBy(page, sel, 180)
    await page.waitForTimeout(500)
    const after = await box(page, sel)
    state.refusePatch = false
    check('a refused move puts the bar back where it was', !!after && !!before && Math.abs(after.x - before.x) < 3,
      `${before?.x} → ${after?.x}`)
    check('and says so', (await page.textContent('body')).includes('Could not move'))
  }

  // ── The dialog ────────────────────────────────────────────────────────────
  await open()
  {
    wire.length = 0
    await page.click('button:text-is("+ Add task")')
    await page.waitForSelector('[aria-label="TASK"]', { timeout: 5000 })
    check('the dialog opens', !!(await page.locator('text=Add a task').count()))
    check('it names the season it adds to', (await page.textContent('[role="dialog"]')).includes('2026/27'))

    // Character by character, re-reading focus each time. `fill()` sets the
    // value in one shot and so cannot catch a component declared inside a
    // render, which is the bug this guards against.
    let held = true
    for (const ch of 'Insurance audit') {
      await page.type('[aria-label="TASK"]', ch, { delay: 12 })
      const still = await page.evaluate(() => document.activeElement?.getAttribute('aria-label'))
      if (still !== 'TASK') { held = false; break }
    }
    check('the caret is held, character by character', held)
    check('and every character landed', (await page.inputValue('[aria-label="TASK"]')) === 'Insurance audit',
      await page.inputValue('[aria-label="TASK"]'))

    // Cancel writes nothing at all.
    await page.click('[role="dialog"] button:text-is("Cancel")')
    await page.waitForTimeout(300)
    check('Cancel sends nothing', posts(/\/definitions/).length === 0, JSON.stringify(wire))
    check('Cancel closes the dialog', !(await page.locator('[aria-label="TASK"]').count()))
  }

  {
    wire.length = 0
    await page.click('button:text-is("+ Add task")')
    await page.waitForSelector('[aria-label="TASK"]', { timeout: 5000 })
    await page.fill('[aria-label="TASK"]', 'Insurance audit')
    await page.selectOption('[aria-label="USUAL MONTH"]', '5')
    await page.selectOption('[aria-label="OWNER ROLE"]', 'r1')
    await page.fill('[aria-label="BUDGET"]', '250')
    await page.fill('[aria-label="START"]', '2026-10-05')
    await page.fill('[aria-label="DUE"]', '2026-11-20')
    await page.click('[role="dialog"] button:text-is("Add task")')
    await page.waitForTimeout(900)

    const post = posts(/\/definitions/)[0]
    check('the definition is created', !!post && post.method === 'POST', JSON.stringify(wire))
    check('with exactly the fields the dialog collected', !!post && JSON.stringify(post.body) === JSON.stringify({
      title: 'Insurance audit', category_id: null, frequency: 'annual', default_month: 5, description: null,
      responsibility_role_id: 'r1', third_party: null, budget_estimate: 250,
      reminder_enabled: false, reminder_days_before: 14,
    }), JSON.stringify(post?.body))
    // The dates go to the occurrence /board minted for the new definition —
    // which is what puts it on THIS season's plan rather than only in the
    // template library.
    const patch = posts(/\/occurrences\/o9/)[0]
    check('the dates are written to this season\'s occurrence', !!patch && patch.method === 'PATCH', JSON.stringify(wire))
    check('and only the dates that were typed', !!patch &&
      JSON.stringify(patch.body) === JSON.stringify({ start_date: '2026-10-05', due_date: '2026-11-20' }),
      JSON.stringify(patch?.body))
    check('the dialog closes', !(await page.locator('[aria-label="TASK"]').count()))
    check('the new task is on the plan', (await page.textContent('body')).includes('Insurance audit'))
    check('and it drew a draggable bar', !!(await page.locator(trackEl('Insurance audit')).count()))
    check('the screen says it was added', (await page.textContent('body')).includes('Added "Insurance audit"'))
  }

  // ── A refused create is reported in the dialog, not swallowed ─────────────
  {
    state.refuseDefinition = true
    await page.click('button:text-is("+ Add task")')
    await page.waitForSelector('[aria-label="TASK"]', { timeout: 5000 })
    await page.fill('[aria-label="TASK"]', 'Ground lease review')
    await page.click('[role="dialog"] button:text-is("Add task")')
    await page.waitForTimeout(600)
    check('a refused create says why, and keeps the dialog open',
      (await page.textContent('[role="dialog"]')).includes('already exists'),
      await page.textContent('[role="dialog"]'))
    state.refuseDefinition = false
    await page.click('[role="dialog"] button:text-is("Cancel")')
  }

  check('no page errors', errors.length === 0, errors.join(' | '))

  // Pre-existing: the timeline is a 1000px-wide grid by design and scrolls
  // inside its own box. Re-measured with this change stashed to confirm the
  // budget is a baseline rather than something introduced here.
  await page.setViewportSize({ width: 390, height: 900 })
  await open()
  const over = await noOverflow(page)
  check('no overflow added at 390px', over <= 0, `${over}px`)

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch(e => { console.error(e); process.exit(1) })
