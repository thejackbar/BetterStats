// The reported surface: "rediscover committee is disabled on club directory",
// then — once the button explained itself — if they are two different jobs, why
// must the crawler be restarted to run one of them?
//
//   npx vite --port 5203 &
//   node frontend/verification/verify_rediscover_gating_browser.mjs [baseUrl]
//
// The gate turned out to be protecting nothing: the prune is per club, so a
// half-finished run leaves the clubs it never reached untouched, and the
// single-club Rediscover has always run while stopped. So Stop now governs the
// UNATTENDED crawler and a rediscover carries its own cancel.
//
// What is measured here: the button is live while the crawler is stopped, the
// crawl button beside it is still held back (the half that must not regress),
// the Stop rediscover control appears and writes to its own endpoint, and a run
// halted part way is not reported as a finished one.
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
    if (/marketing\/rediscover\/stop/.test(p)) {
      liveRun = { ...liveRun, cancel: true }
      return json({ status: 'stopping' })
    }
    if (/marketing\/rediscover$/.test(p)) {
      // The stub MUTATES — one that answers the same thing every time cannot
      // tell a working press from a no-op.
      liveRun = { ...liveRun, running: true, stale: false, cancel: false,
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
// EVERY read of an element this change ADDS goes through here. A bare
// `.first().innerText()` on a locator that found nothing throws, and in a
// control run — where the element is absent by definition — that kills the run
// after a couple of checks and says nothing about the rest. Found by running it.
async function textOf(locator) {
  return await locator.count() ? await locator.first().innerText() : ''
}

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
  ck('THE REPORTED CASE IS FIXED — with the crawler stopped, Rediscover is LIVE. '
     + 'Stop governs the unattended crawler, and pressing this is the opposite '
     + 'of unattended',
    !!s && !s.disabled, s && `disabled=${s.disabled}`)

  const noteText = await textOf(page.getByTestId('rediscover-runs-stopped'))
  ck('AND IT SAYS SO — a stopped crawler two rows up otherwise reads as though '
     + 'this button must be blocked too, which is what it used to be',
    /still runs/i.test(noteText), noteText || 'no note')
  ck('the tooltip says the same thing rather than a reason it is held back',
    !!s && /whether or not the crawler is stopped/i.test(s.title), s && s.title)
  ck('and nothing on the row tells you to press Start crawling first',
    !/Press Start crawling above to run this/i.test(noteText)
      && !/Press Start crawling above to run this/i.test((s && s.title) || ''),
    noteText || (s && s.title) || '')

  // THE HALF THAT MUST NOT REGRESS. Letting a rediscover through is only
  // defensible while the switch still stops the unattended crawler.
  const crawlBtn = page.getByRole('button', { name: /Run crawl batch/ }).first()
  ck('THE CRAWL BUTTON BESIDE IT IS STILL HELD BACK — the switch still stops '
     + 'every unattended path',
    await crawlBtn.count() > 0 && await crawlBtn.isDisabled())
  ck('and still says why', await crawlBtn.count() > 0
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
    await page.getByTestId('rediscover-runs-stopped').count() === 0)
  ck('the tooltip describes what it does',
    !!s && /Re-page the whole PlayHQ/i.test(s.title), s && s.title)
  ck('and no Stop rediscover control is drawn when nothing is running',
    await page.getByTestId('rediscover-stop-btn').count() === 0)
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
  const crawlBtn = page.getByRole('button', { name: /Run crawl batch/ }).first()
  ck('and the crawl button is live too — gating on the WORD would kill it every '
     + 'time the crawler took a breather',
    await crawlBtn.count() > 0 && !(await crawlBtn.isDisabled()))
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
  ck('AND A STOP CONTROL APPEARS — without one, letting it ignore the crawler\'s '
     + 'Stop would take away the ability to halt all PlayHQ traffic',
    await page.getByTestId('rediscover-stop-btn').count() > 0)
  await ctx.close()
}

// ── stopping a running rediscover ─────────────────────────────────────────
{
  const { page, ctx, calls, errors } = await open({
    run: { ...IDLE_RUN, running: true, stale: false, cancel: false,
           started_at: new Date().toISOString(),
           progress: { clubs_seen: 120, total_reported: 6900 } },
  })
  page.on('dialog', d => d.accept())
  const stop = page.getByTestId('rediscover-stop-btn')
  if (await stop.count() === 0) {
    ck('the Stop rediscover control is on the page', false, 'not found')
    ck('pressing it writes to its own endpoint', false, 'no button')
    ck('and never to the crawler\'s own Stop', false, 'no button')
  } else {
    const before = calls.length
    await stop.click()
    await page.waitForTimeout(900)
    const sent = calls.slice(before).filter(c => c.method === 'POST')
    ck('PRESSING STOP WRITES TO THE REDISCOVER\'S OWN ENDPOINT',
      sent.length === 1 && /marketing\/rediscover\/stop$/.test(sent[0].path),
      JSON.stringify(sent))
    // Stopping this run must NOT stop the crawler — they are separate switches
    // now, and conflating them is the whole bug this change undoes.
    ck('AND NEVER TO THE CRAWLER\'S OWN STOP — they are separate switches',
      !sent.some(c => /crawl\/control/.test(c.path)), JSON.stringify(sent))
  }
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── a dismissed confirm writes nothing ────────────────────────────────────
{
  const { page, ctx, calls } = await open({
    run: { ...IDLE_RUN, running: true, stale: false, cancel: false,
           started_at: new Date().toISOString(), progress: { clubs_seen: 5 } },
  })
  page.on('dialog', d => d.dismiss())
  const stop = page.getByTestId('rediscover-stop-btn')
  const before = calls.length
  if (await stop.count() === 0) ck('a dismissed confirm sends nothing', false, 'no button')
  else {
    await stop.click()
    await page.waitForTimeout(700)
    ck('a dismissed confirm sends nothing at all',
      calls.slice(before).filter(c => c.method === 'POST').length === 0,
      JSON.stringify(calls.slice(before).filter(c => c.method === 'POST')))
  }
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

// ── a run halted part way is not a finished one ───────────────────────────
{
  const { page, ctx } = await open({
    run: { ...IDLE_RUN, finished_at: new Date().toISOString(),
           result: { au_seen: 412, pruned: 9, marked_former: 2, new: 0, stopped: true } },
  })
  const body = await page.locator('body').innerText()
  ck('A HALTED RUN IS NOT REPORTED AS A FINISHED ONE — the same line over a '
     + 'partial pass claims a whole-directory reconcile that never happened',
    /stopped part way/i.test(body),
    body.match(/Last rediscover[^\n]{0,80}/)?.[0] || 'nothing said')
  ck('while still reporting what it did get through',
    /412 club/.test(body), body.match(/Last rediscover[^\n]{0,80}/)?.[0] || '')
  await ctx.close()
}

// ── a run that finished ───────────────────────────────────────────────────
{
  const { page, ctx } = await open({
    run: { ...IDLE_RUN, finished_at: new Date().toISOString(),
           result: { au_seen: 6900, pruned: 140, marked_former: 31, new: 4, stopped: false } },
  })
  const body = await page.locator('body').innerText()
  ck('a run that finished says so plainly, with no halted wording',
    /Last rediscover: 6900 club/.test(body) && !/stopped part way/i.test(body),
    body.match(/Last rediscover[^\n]{0,80}/)?.[0] || 'nothing said')
  await ctx.close()
}

// ── a phone ───────────────────────────────────────────────────────────────
{
  const { page, ctx, errors } = await open({ status: STOPPED, width: 390 })
  const over = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', over <= 0, `${over}px`)
  ck('and the note is still drawn there',
    await page.getByTestId('rediscover-runs-stopped').count() > 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
