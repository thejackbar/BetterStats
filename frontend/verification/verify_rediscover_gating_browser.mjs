// The reported surface: "rediscover committee is disabled on club directory".
//
//   npx vite --port 5203 &
//   node frontend/verification/verify_rediscover_gating_browser.mjs [baseUrl]
//
// The button was correctly held back — a full rediscover re-pages the whole of
// PlayHQ and the service refuses outright while an operator has the crawler
// stopped — but it never said so, and the Stop that causes it is set two rows
// away. What is measured here is that the screen now names the reason, that it
// is no longer held back by a run this backend has lost track of, and that a
// run which never read a page is not reported as a finished one.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5203'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const PAGE_URL = `${BASE}/admin/super/marketing`

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const RUNNING = {
  state: 'idle', detail: 'Idle — 12 clubs await association enrichment.',
  paused: false, clubs: 40, associations_pending: 12,
  continuous_enabled: false, crawl_enabled: true, in_window: true,
  window: { start: '01:00', end: '06:00', tz: 'Australia/Perth' },
}
const STOPPED = {
  ...RUNNING, state: 'stopped', paused: true,
  detail: 'Stopped by an operator. 12 clubs still await enrichment. Click Start crawling to resume.',
}
// The OTHER "paused": the runner merely on a break. The operator flag is false,
// so this must NOT disable anything.
const ON_A_BREAK = {
  ...RUNNING, state: 'paused', paused: false,
  detail: 'In window, no fetch in 400s — likely on a break, or the runner stalled.',
}

const IDLE_RUN = { running: false, started_at: null, finished_at: null,
                   result: null, error: null, progress: {}, stale: false }

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ status = RUNNING, run = IDLE_RUN, width = 1500 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))

  let liveRun = run

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const u = new URL(req.url())
    const p = u.pathname.replace(/^\/api/, '')
    let payload = null
    try { payload = req.postData() ? JSON.parse(req.postData()) : null } catch { /* not json */ }
    calls.push({ path: p, method: req.method(), payload })
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

    if (/\/auth\/me/.test(p)) {
      return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'super_admin',
                    entitlements: { modules: [], status: 'active' } })
    }
    if (/marketing\/rediscover\/status/.test(p)) return json(liveRun)
    if (/marketing\/rediscover$/.test(p)) {
      // The stub MUTATES — one that answers the same thing every time cannot
      // tell a working press from a no-op.
      liveRun = { ...liveRun, running: true, stale: false,
                  started_at: new Date().toISOString(), progress: {} }
      return json({ status: 'started' })
    }
    if (/marketing\/status/.test(p)) return json(status)
    if (/marketing\/stats/.test(p)) return json({ clubs: 40, contacts: 90 })
    if (/marketing\/clubs/.test(p)) return json({ total: 0, limit: 100, offset: 0, clubs: [] })
    return json([])
  })

  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' })
  // Wait for the control this suite is about rather than for the network to go
  // quiet — the page polls the crawl status every 12s, so it never does.
  await btn(page).waitFor({ state: 'visible', timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(900)
  return { page, ctx, errors, calls }
}

// Addressed by its own hook, NOT by its label — the label is itself one of the
// things being checked here (it reads "Rediscovering..." mid-run), so a
// name-based locator would silently stop finding the button in exactly the
// state this suite exists to measure. Found by running it.
//
// The label is kept as a FALLBACK so a build without the hook is still found
// and fails on its BEHAVIOUR. Without it the control run reports "button not
// found" everywhere, which measures the harness rather than the code.
const btn = (page) => page.locator(
  '[data-testid="rediscover-btn"], button:has-text("Rediscover committees"), '
  + 'button:has-text("Rediscovering")').first()

// A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN — a build without the button
// reports each missing check by name rather than dying on the first locator
// timeout and saying nothing about the rest.
async function state(page, label) {
  const b = btn(page)
  if (await b.count() === 0) {
    ck(`the ${label} button is on the page`, false, 'not found')
    return null
  }
  return { disabled: await b.isDisabled(), title: await b.getAttribute('title') || '',
           text: await b.innerText() }
}

// ── the reported case: the crawler is stopped ─────────────────────────────
{
  const { page, ctx, errors } = await open({ status: STOPPED })
  const s = await state(page, 'rediscover')
  ck('THE REPORTED CASE REPRODUCES — with the crawler stopped, the button is disabled',
    !!s && s.disabled)

  const note = page.getByTestId('rediscover-blocked')
  ck('AND IT NOW SAYS WHY, ON SCREEN — a disabled control with no stated reason '
     + 'reads as broken software',
    await note.count() > 0 && /crawler is stopped/i.test(await note.first().innerText()),
    await note.count() ? await note.first().innerText() : 'no note')
  ck('naming the way out, which is set two rows away',
    await note.count() > 0 && /Start crawling/i.test(await note.first().innerText()))
  ck('and the tooltip says the same thing',
    !!s && /crawler is stopped/i.test(s.title), s && s.title)
  const crawlBtn = page.getByRole('button', { name: /Run crawl batch/ }).first()
  ck('the crawl button beside it is held back for the same reason, and says so too',
    await crawlBtn.count() > 0
      && /crawler is stopped/i.test(await crawlBtn.getAttribute('title') || ''))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── the crawler running: nothing held back, nothing said ──────────────────
{
  const { page, ctx, errors } = await open({ status: RUNNING })
  const s = await state(page, 'rediscover')
  ck('with the crawler running the button is live', !!s && !s.disabled)
  ck('AND NOTHING IS DRAWN — a note on every visit is noise that teaches people '
     + 'to stop reading notes',
    await page.getByTestId('rediscover-blocked').count() === 0)
  ck('the tooltip goes back to describing what it does',
    !!s && /Re-page the whole PlayHQ/i.test(s.title), s && s.title)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── a runner merely on a break is NOT the operator's Stop ─────────────────
{
  const { page, ctx } = await open({ status: ON_A_BREAK })
  const s = await state(page, 'rediscover')
  ck('A RUNNER ON A BREAK DOES NOT DISABLE ANYTHING — "paused" the derived state '
     + 'and "paused" the operator flag are two different things',
    !!s && !s.disabled)
  ck('and nothing claims the crawler is stopped',
    await page.getByTestId('rediscover-blocked').count() === 0)
  await ctx.close()
}

// ── a run genuinely in flight ─────────────────────────────────────────────
{
  const { page, ctx } = await open({
    run: { ...IDLE_RUN, running: true, stale: false,
           started_at: new Date().toISOString(),
           progress: { clubs_seen: 300, total_reported: 6900, pruned: 12, marked_former: 4 } },
  })
  const s = await state(page, 'rediscover')
  ck('a rediscover already running disables the button', !!s && s.disabled)
  ck('and says so on the button itself', !!s && /Rediscovering/i.test(s.text), s && s.text)
  ck('for its OWN reason, not the crawler one',
    !!s && /already running/i.test(s.title), s && s.title)
  const body = await page.locator('body').innerText()
  ck('and the progress is shown beside it', /300 club\(s\) re-read/.test(body))
  await ctx.close()
}

// ── the case the button was permanently dead in ───────────────────────────
{
  const { page, ctx } = await open({
    run: { ...IDLE_RUN, running: true, stale: true,
           started_at: new Date(Date.now() - 24 * 3600 * 1000).toISOString() },
  })
  const s = await state(page, 'rediscover')
  ck('A RUN THIS BACKEND HAS LOST TRACK OF NO LONGER HOLDS THE BUTTON — the '
     + 'server would happily start a new one, so the screen must not disagree',
    !!s && !s.disabled)
  await ctx.close()
}

// ── pressing it ───────────────────────────────────────────────────────────
{
  const { page, ctx, calls, errors } = await open({ status: RUNNING })
  page.on('dialog', d => d.accept())
  const before = calls.length
  if (await btn(page).count() === 0) ck('the rediscover button is on the page', false, 'not found')
  else {
    await btn(page).click()
    await page.waitForTimeout(900)
  }
  const sent = calls.slice(before).filter(c => c.method === 'POST')
  ck('pressing it sends exactly one write, to the rediscover endpoint',
    sent.length === 1 && /marketing\/rediscover$/.test(sent[0].path),
    JSON.stringify(sent))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── a run that never read a page is not a finished one ────────────────────
{
  const { page, ctx } = await open({
    run: { ...IDLE_RUN, finished_at: new Date().toISOString(),
           result: { skipped: 'stopped' } },
  })
  const body = await page.locator('body').innerText()
  ck('A SKIPPED RUN IS NOT REPORTED AS A FINISHED ONE — "0 club(s)" reads as '
     + '"it ran and there was nothing to do" when in fact it never started',
    !/Last rediscover: 0 club/.test(body),
    body.match(/Last rediscover[^\n]{0,70}/)?.[0] || '')
  ck('it says what actually happened instead',
    /did not run/i.test(body) && /crawler was stopped/i.test(body),
    body.match(/Last rediscover[^\n]{0,70}/)?.[0] || 'nothing said')
  await ctx.close()
}

// ── a phone ───────────────────────────────────────────────────────────────
{
  const { page, ctx, errors } = await open({ status: STOPPED, width: 390 })
  const over = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', over <= 0, `${over}px`)
  ck('and the reason is still drawn there',
    await page.getByTestId('rediscover-blocked').count() > 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
