// The Club Directory's "Club teaser crawl" panel: set the rate and hours the
// paced crawl runs on, and read how far through the directory it is.
//
//   npx vite --port 5204 &
//   node frontend/verification/verify_teaser_panel_browser.mjs [baseUrl]
//
// Measured: what each state says, that a save sends exactly the three settings
// (and Turn off sends the rate alone, as null), that switching ON asks first and
// changing a rate already running does not, that a bad value is stopped on the
// page and a server refusal is shown, that the 15s refresh does not overwrite
// what is being typed, and that nothing overflows at 390px.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const PAGE_URL = `${BASE}/admin/super/marketing`

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const PROGRESS = { targets: 3671, with_snapshot: 20, never_pulled: 3651, due: 3651, ok: 19, empty: 0,
                   junior_only: 1, error: 0, avg_calls: 27.8, last_pulled_at: '2026-09-30T05:00:00Z',
                   clubs_last_hour: 20, calls_last_hour: 534 }
const status = (over = {}) => ({
  state: 'off', rate: 0, window_start: 5, window_end: 22, stopped: false, in_hours: true,
  min_rate: 0.05, max_rate: 10, progress: PROGRESS, estimate: null, ...over,
})
const RUNNING = status({ state: 'running', rate: 2, estimate: { calls: 101500, hours: 14.1, window_hours: 17,
                          days: 0.8, rate_to_finish_in_one_window: 1.66 } })

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ initial = status(), width = 1400, refuse = null } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = [], patches = []
  let live = initial
  const dialogs = []
  let acceptDialog = true
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('dialog', async (d) => { dialogs.push(d.message()); acceptDialog ? await d.accept() : await d.dismiss() })

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    const json = (b, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(p)) {
      return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'super_admin',
                    entitlements: { modules: [], status: 'active' } })
    }
    if (/super\/general-settings/.test(p) && req.method() === 'PATCH') {
      const body = JSON.parse(req.postData() || '{}')
      patches.push(body)
      if (refuse) return json({ detail: refuse }, 422)
      // The stub MUTATES, so a working save is told apart from a no-op.
      const rate = 'club_teaser_calls_per_second' in body ? (body.club_teaser_calls_per_second || 0) : live.rate
      live = { ...live, rate, state: rate ? (live.state === 'off' ? 'running' : live.state) : 'off',
               window_start: body.club_teaser_window_start ?? live.window_start,
               window_end: body.club_teaser_window_end ?? live.window_end,
               estimate: rate ? RUNNING.estimate : null }
      return json({})
    }
    if (/marketing\/teaser\/status/.test(p)) return json(live)
    if (/marketing\/status/.test(p)) {
      return json({ state: 'idle', detail: 'Idle', paused: false, clubs: 40, associations_pending: 0,
                    continuous_enabled: false, crawl_enabled: true, in_window: true,
                    window: { start: '01:00', end: '06:00', tz: 'Australia/Perth' } })
    }
    if (/marketing\/rediscover\/status/.test(p)) {
      return json({ running: false, started_at: null, finished_at: null, result: null, error: null, progress: {}, stale: false })
    }
    if (/marketing\/stats/.test(p)) return json({ clubs: 40, contacts: 90 })
    if (/marketing\/clubs/.test(p)) return json({ total: 0, limit: 100, offset: 0, clubs: [] })
    return json([])
  })

  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' })
  await panel(page).waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
  await page.waitForTimeout(500)
  return { page, ctx, errors, patches, dialogs, setLive: (s) => { live = s },
           setAccept: (v) => { acceptDialog = v } }
}

const panel = (page) => page.locator('[data-testid="teaser-panel"]')
// EVERY read of an element this change adds goes through here, so a build
// without the panel reports each check as failing instead of dying on the first
// missing locator.
const textOf = async (l) => (await l.count() ? await l.first().innerText() : '')
const val = async (l) => (await l.count() ? await l.first().inputValue() : null)
const t = (page, id) => page.locator(`[data-testid="${id}"]`)
const dis = async (l) => (await l.count() ? await l.first().isDisabled() : false)
const ena = async (l) => (await l.count() ? await l.first().isEnabled() : false)
const press = async (l) => { if (await l.count()) await l.first().click() }
const put = async (l, v) => { if (await l.count()) await l.first().fill(v) }
const attr = async (l, a) => (await l.count() ? await l.first().getAttribute(a) : null)

// ---- 1. Off ---------------------------------------------------------------
{
  const { page, ctx, errors } = await open()
  const state = await textOf(t(page, 'teaser-state'))
  ck('the panel is on the Club Directory page', await panel(page).count() === 1)
  ck('unset rate reads OFF', /off/i.test(state), state)
  ck('the rate box is empty with an "off" placeholder', await val(t(page, 'teaser-rate')) === ''
     && await attr(t(page, 'teaser-rate'), 'placeholder') === 'off')
  ck('the hours show the saved 5 and 22', await val(t(page, 'teaser-start')) === '5' && await val(t(page, 'teaser-end')) === '22')
  ck('Save is disabled until something changes', await dis(t(page, 'teaser-save')))
  ck('there is no Turn off button while it is off', await t(page, 'teaser-off').count() === 0)
  const prog = await textOf(t(page, 'teaser-progress'))
  ck('progress says how many clubs are pulled and due', /20 of 3,671 clubs pulled/.test(prog) && /3,651 due/.test(prog), prog)
  ck('and the status split and last hour', /19 ok, 0 empty, 1 junior only, 0 errors/.test(prog)
     && /534 calls/.test(prog) && /0\.15 a second/.test(prog) && /27\.8 calls a club/.test(prog), prog)
  ck('no estimate is drawn while it is off', await t(page, 'teaser-estimate').count() === 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ---- 2. Switching on: asks first, sends exactly three settings ---------------
{
  const { page, ctx, patches, dialogs, setAccept } = await open()
  setAccept(false)
  await put(t(page, 'teaser-rate'), '2')
  ck('typing a rate enables Save', await ena(t(page, 'teaser-save')))
  await press(t(page, 'teaser-save'))
  await page.waitForTimeout(300)
  ck('switching ON asks first, naming the rate and the hours',
     dialogs.length === 1 && /2 calls a second/.test(dialogs[0]) && /05:00/.test(dialogs[0]) && /22:00/.test(dialogs[0]),
     dialogs.join('|'))
  ck('a dismissed confirm sends NOTHING', patches.length === 0)
  setAccept(true)
  await press(t(page, 'teaser-save'))
  await page.waitForTimeout(600)
  ck('the save sends exactly the rate and both hours',
     patches.length === 1 && JSON.stringify(patches[0]) === JSON.stringify({
       club_teaser_calls_per_second: 2, club_teaser_window_start: 5, club_teaser_window_end: 22 }),
     JSON.stringify(patches))
  ck('the panel then reads RUNNING', /running/i.test(await textOf(t(page, 'teaser-state'))))
  ck('with a confirmation message', /Saved/.test(await textOf(t(page, 'teaser-msg'))))
  ck('Save goes dead again and Turn off appears', await dis(t(page, 'teaser-save')) && await t(page, 'teaser-off').count() === 1)
  const est = await textOf(t(page, 'teaser-estimate'))
  ck('the estimate says the calls, the hours at this rate and the rate that would finish in one window',
     /101,500 calls/.test(est) && /14\.1 hours at 2 a second/.test(est) && /1\.66 a second would finish/.test(est), est)
  await ctx.close()
}

// ---- 3. Already running: changing the rate does NOT ask again; Turn off ------
{
  const { page, ctx, patches, dialogs } = await open({ initial: RUNNING })
  ck('a saved rate is shown in the box', await val(t(page, 'teaser-rate')) === '2')
  await put(t(page, 'teaser-rate'), '1.5')
  await put(t(page, 'teaser-end'), '20')
  await press(t(page, 'teaser-save'))
  await page.waitForTimeout(500)
  ck('changing a running crawl does not ask again', dialogs.length === 0, dialogs.join('|'))
  ck('a changed rate and hour are sent together',
     patches.length === 1 && patches[0].club_teaser_calls_per_second === 1.5 && patches[0].club_teaser_window_end === 20
     && patches[0].club_teaser_window_start === 5, JSON.stringify(patches))
  await press(t(page, 'teaser-off'))
  await page.waitForTimeout(500)
  ck('Turn off sends the rate alone, as null (the hours are left alone)',
     patches.length === 2 && JSON.stringify(patches[1]) === JSON.stringify({ club_teaser_calls_per_second: null }),
     JSON.stringify(patches[1]))
  ck('and the panel reads OFF with a message', /off/i.test(await textOf(t(page, 'teaser-state')))
     && /Switched off/.test(await textOf(t(page, 'teaser-msg'))))
  await ctx.close()
}

// ---- 4. A bad value is stopped on the page -----------------------------------
{
  const { page, ctx, patches } = await open({ initial: RUNNING })
  for (const [label, fills, want] of [
    ['a rate above the ceiling', { rate: '11' }, /between 0\.05 and 10/],
    ['a rate below the floor', { rate: '0.01' }, /between 0\.05 and 10/],
    ['hours that close before they open', { start: '20', end: '6' }, /open before they close/],
    ['a blank rate', { rate: '' }, /Enter a rate/],
  ]) {
    await put(t(page, 'teaser-rate'), '2'); await put(t(page, 'teaser-start'), '5'); await put(t(page, 'teaser-end'), '22')
    if ('rate' in fills) await put(t(page, 'teaser-rate'), fills.rate)
    if ('start' in fills) await put(t(page, 'teaser-start'), fills.start)
    if ('end' in fills) await put(t(page, 'teaser-end'), fills.end)
    const problem = await textOf(t(page, 'teaser-problem'))
    ck(`${label} is explained and Save is disabled`, want.test(problem) && await dis(t(page, 'teaser-save')), problem)
  }
  ck('nothing was sent for any of them', patches.length === 0)
  await ctx.close()
}

// ---- 5. A server refusal is shown --------------------------------------------
{
  const { page, ctx, patches } = await open({ initial: RUNNING, refuse: 'club_teaser_window_start must be before club_teaser_window_end' })
  await put(t(page, 'teaser-rate'), '3')
  await press(t(page, 'teaser-save'))
  await page.waitForTimeout(500)
  ck('the server error text is shown in the panel', /window_start must be before/.test(await textOf(t(page, 'teaser-error'))))
  ck('what was typed is kept so it can be fixed', await val(t(page, 'teaser-rate')) === '3' && patches.length === 1)
  await ctx.close()
}

// ---- 6. The other states say why ---------------------------------------------
for (const [label, st, want] of [
  ['stopped', status({ state: 'stopped', rate: 2, stopped: true }), /Stopped.*Start crawling above/s],
  ['outside hours', status({ state: 'outside_hours', rate: 2, in_hours: false }), /Outside hours/],
  ['caught up', status({ state: 'idle', rate: 2, progress: { ...PROGRESS, due: 0 } }), /Caught up/],
]) {
  const { page, ctx } = await open({ initial: st })
  const head = await textOf(panel(page).locator('div').first())
  ck(`${label} is named on the panel`, want.test(head), head)
  await ctx.close()
}

// ---- 7. Empty-club warning ---------------------------------------------------
{
  const { page, ctx } = await open({ initial: status({ state: 'running', rate: 2,
    progress: { ...PROGRESS, with_snapshot: 100, empty: 40 } }) })
  ck('a high share of empty clubs is called out (an outage can read as empty)',
     /read as empty/.test(await textOf(t(page, 'teaser-empty-warn'))))
  await ctx.close()
}
{
  const { page, ctx } = await open({ initial: RUNNING })
  ck('and not shown when there are none', await t(page, 'teaser-empty-warn').count() === 0)
  await ctx.close()
}

// ---- 8. The refresh does not overwrite what is being typed --------------------
{
  const { page, ctx, setLive } = await open({ initial: RUNNING })
  await put(t(page, 'teaser-rate'), '3.25')
  setLive({ ...RUNNING, progress: { ...PROGRESS, with_snapshot: 400, due: 3271 } })
  await page.waitForFunction(() => /400 of 3,671/.test(document.querySelector('[data-testid="teaser-progress"]')?.innerText || ''),
                             null, { timeout: 20000 }).catch(() => {})
  ck('the progress refreshed on its own', /400 of 3,671/.test(await textOf(t(page, 'teaser-progress'))))
  ck('and the rate being typed was left alone', await val(t(page, 'teaser-rate')) === '3.25')
  await ctx.close()
}

// ---- 9. Phone width ----------------------------------------------------------
{
  const { page, ctx, errors } = await open({ initial: RUNNING, width: 390 })
  const m = await page.evaluate(() => {
    const el = document.querySelector('[data-testid="teaser-panel"]')
    return el ? { panel: el.scrollWidth - el.clientWidth, page: document.documentElement.scrollWidth - document.documentElement.clientWidth } : null
  })
  ck('the panel does not overflow itself at 390px', m && m.panel <= 0, JSON.stringify(m))
  ck('no page errors at 390px', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
