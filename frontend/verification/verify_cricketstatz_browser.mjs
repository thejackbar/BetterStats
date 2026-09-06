// Drives the real /admin/cricketstatz screen in Chromium with the API stubbed
// at the network layer.
//
//   npx vite --port 5198 &
//   node frontend/verification/verify_cricketstatz_browser.mjs [baseUrl]
//
// Checks the things a build cannot: that the exact address reaches the wire on
// both Check and Import, that the preview reports what the site holds
// (including the 999-row cap), that a running import shows real progress and
// polls, that the record book draws its boards, that a dismissed undo sends
// nothing, and that the Data Sync screen carries the way in.
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const CLUB_URL = 'https://www2.cricketstatz.com/ss/w?mode=104&club=93931&team=0&season='

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  — ${extra}` : ''}`) }
}

const PREVIEW = {
  club_id: '93931', club_name: 'Keon Park Cricket Club', seasons_offered: 167,
  teams: ['Keon Park 1st-XI', 'Keon Park 2nd-XI', 'Keon Park 3rd-XI'],
  matches_found: 999, truncated: true,
  earliest: '1974-01-12', latest: '2026-03-07', record_reports: 41,
}

const RECORDS = [
  { mode: 4, section: 'batting', title: 'Top Run Aggregates', scope: '',
    headers: ['#', 'Name', 'Mts', 'Runs'], row_count: 2,
    rows: [{ values: ['1', 'Brad Quinsee', '399', '10444'], players: [] },
           { values: ['2', 'Michael B. White', '325', '8405'], players: [] }] },
  { mode: 72, section: 'team', title: 'Highest Winning Margins by Runs', scope: '',
    headers: ['#', 'Team', 'Opposition', 'Margin'], row_count: 1,
    rows: [{ values: ['1', 'Keon Park 2nd-XI', "Preston Druids 'B'", 'Inns & 193 runs'], players: [] }] },
]

const IMPORTS = [{
  id: 'imp-1', club_id: '93931', club_name: 'Keon Park Cricket Club',
  status: 'complete', phase: 'done', stats: {}, error: null,
  started_at: '2026-09-06T01:00:00Z', finished_at: '2026-09-06T01:40:00Z',
  undone_at: null, matches: 1243,
}]

// The import's own life cycle: nothing, then running, then complete — so the
// screen's polling can be observed rather than assumed.
function makeState() {
  return { phase: 'none', polls: 0 }
}

const routes = (page, calls, state) => page.route('**/api/**', async (route) => {
  const url = route.request().url()
  const method = route.request().method()
  let body = null
  try { body = route.request().postData() } catch { /* GET */ }
  calls.push({ url, method, body })
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

  if (url.includes('/auth/me')) {
    return json({
      id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin',
      club_slug: 'keon-park',
      entitlements: { modules: [], status: 'active' },
    })
  }
  if (url.includes('/cricketstatz/inspect')) return json(PREVIEW)
  if (url.includes('/cricketstatz/import') && method === 'POST') {
    state.phase = 'running'
    return json({ import_id: 'imp-2', status: 'running' })
  }
  if (/\/cricketstatz\/imports\/[^/]+\/undo/.test(url)) {
    return json({ matches_removed: 1243, records_removed: 41 })
  }
  if (url.includes('/cricketstatz/imports')) return json({ imports: IMPORTS })
  if (url.includes('/cricketstatz/records')) return json({ records: RECORDS })
  if (url.includes('/cricketstatz/status')) {
    if (state.phase === 'none') return json({ import: null, club_id: null })
    state.polls += 1
    if (state.phase === 'running' && state.polls >= 3) state.phase = 'complete'
    const running = state.phase === 'running'
    return json({
      club_id: '93931',
      import: {
        id: 'imp-2', club_id: '93931', club_name: 'Keon Park Cricket Club',
        source_url: CLUB_URL,
        status: running ? 'running' : 'complete',
        phase: running ? 'matches' : 'done',
        error: null,
        started_at: '2026-09-06T02:00:00Z',
        finished_at: running ? null : '2026-09-06T02:40:00Z',
        undone_at: null,
        progress: {
          phase: running ? 'matches' : 'done',
          seasons_done: running ? 12 : 41, seasons_total: 41,
          matches_done: running ? 380 : 1243, matches_total: 1243,
          scorecards: running ? 356 : 1190, players: running ? 210 : 604,
          records: running ? 0 : 41,
          notes: running ? [] : ['match 3082412: no scorecard published'],
        },
      },
    })
  }
  // Anything else this shell asks for.
  return json({})
})

// The Data Sync screen needs its own small surface to render at all.
const syncRoutes = (page, calls) => page.route('**/api/**', async (route) => {
  const url = route.request().url()
  calls.push({ url, method: route.request().method() })
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) {
    return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin',
                  club_slug: 'keon-park', entitlements: { modules: [], status: 'active' } })
  }
  if (url.includes('/club-admin/settings')) return json({ id: 'org-1', name: 'Keon Park' })
  // Both of these answer with a bare ARRAY — a {runs:[]} stub renders the
  // error boundary instead of the screen, and then measures that.
  if (url.includes('/sync-logs')) return json([])
  if (url.includes('/sync-runs')) return json([])
  if (url.includes('/sync-requests')) return json([])
  if (url.includes('/sync-drift')) return json({ status: 'clean' })
  return json({})
})

async function open(ctx, path, calls, state) {
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  // Google Fonts, GTM and the Meta pixel are unreachable from this sandbox;
  // their load failures say nothing about the page.
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    if (/net::ERR_/.test(m.text())) return
    errors.push(m.text())
  })
  if (state) await routes(page, calls, state)
  else await syncRoutes(page, calls)
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1400)
  return { page, errors }
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: EXECUTABLE })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  await ctx.addInitScript(() => { localStorage.setItem('token', 'stub') })

  // ── the screen itself ─────────────────────────────────────────────────
  const calls = []
  const state = makeState()
  const { page, errors } = await open(ctx, '/admin/cricketstatz', calls, state)

  ck('the screen renders', (await page.locator('text=Import from CricketStatz').count()) > 0)
  ck('it asks for the club\'s own stats page',
     (await page.locator('input[placeholder*="cricketstatz.com"]').count()) === 1)
  ck('nothing is imported before it is asked for',
     !calls.some((c) => c.url.includes('/cricketstatz/import') && c.method === 'POST'))

  const input = page.locator('input[placeholder*="cricketstatz.com"]')
  await input.fill(CLUB_URL)
  await page.getByRole('button', { name: 'Check this site' }).click()
  await page.waitForTimeout(700)

  const inspect = calls.find((c) => c.url.includes('/cricketstatz/inspect'))
  ck('Check sends the exact address on the wire',
     !!inspect && JSON.parse(inspect.body || '{}').url === CLUB_URL,
     inspect?.body)
  ck('the preview names the club',
     (await page.locator('text=Keon Park Cricket Club').count()) > 0)
  ck('the preview reports what was found',
     (await page.locator('text=999+').count()) > 0)
  ck('a capped list says there are more, rather than reading as the whole history',
     (await page.locator('text=/caps one list at 999/').count()) === 1)
  ck('the preview reports the record boards',
     (await page.locator('text=41').first().count()) > 0)
  ck('the club\'s own teams are shown',
     (await page.locator('text=/Keon Park 1st-XI/').count()) > 0)

  await page.getByRole('button', { name: 'Import everything' }).click()
  await page.waitForTimeout(900)
  const started = calls.find((c) => c.url.includes('/cricketstatz/import') && c.method === 'POST')
  ck('Import sends the same address', !!started && JSON.parse(started.body || '{}').url === CLUB_URL,
     started?.body)

  ck('a running import says which phase it is in',
     (await page.locator('text=/Bringing your matches across/i').count()) > 0)
  ck('it reports progress against the real totals',
     (await page.locator('text=/380 of 1243 matches/').count()) > 0)
  ck('it reports the seasons walked',
     (await page.locator('text=/Season 12 of 41/').count()) > 0)

  const before = calls.filter((c) => c.url.includes('/cricketstatz/status')).length
  await page.waitForTimeout(5600)
  const after = calls.filter((c) => c.url.includes('/cricketstatz/status')).length
  ck('a running import is polled rather than left stale', after > before, `${before} → ${after}`)
  ck('it says so when it finishes',
     (await page.locator('text=/Your history is in/').count()) > 0)
  ck('what it could not read is offered without shouting',
     (await page.locator('text=/could not read/').count()) > 0)

  // ── the record book ───────────────────────────────────────────────────
  await page.getByRole('button', { name: /Record book/ }).click()
  await page.waitForTimeout(500)
  ck('the record book lists its boards',
     (await page.locator('text=Top Run Aggregates').count()) > 0
     && (await page.locator('text=Highest Winning Margins by Runs').count()) > 0)
  ck('the record book says whose figures these are',
     (await page.locator('text=/as CricketStatz worked them out/').count()) === 1)
  ck('the first board opens with its rows showing',
     (await page.locator('text=Brad Quinsee').count()) > 0
     && (await page.locator('text=10444').count()) > 0)
  await page.getByRole('button', { name: /Top Run Aggregates/ }).click()
  await page.waitForTimeout(300)
  ck('a board folds away when its heading is pressed',
     (await page.locator('text=Brad Quinsee').count()) === 0)
  await page.getByRole('button', { name: /Highest Winning Margins by Runs/ }).click()
  await page.waitForTimeout(300)
  ck('another board opens on its own',
     (await page.locator('text=/Inns & 193 runs/').count()) > 0)

  // ── past imports and undo ─────────────────────────────────────────────
  await page.getByRole('button', { name: /Past imports/ }).click()
  await page.waitForTimeout(500)
  ck('past imports are listed', (await page.locator('text=1243').count()) > 0)

  page.once('dialog', (d) => d.dismiss())
  await page.getByRole('button', { name: 'Undo' }).click()
  await page.waitForTimeout(500)
  ck('a dismissed undo sends nothing',
     !calls.some((c) => /\/imports\/[^/]+\/undo/.test(c.url)))

  page.once('dialog', (d) => d.accept())
  await page.getByRole('button', { name: 'Undo' }).click()
  await page.waitForTimeout(600)
  ck('an accepted undo reaches the wire',
     calls.some((c) => /\/imports\/[^/]+\/undo/.test(c.url)))

  ck('no page errors', errors.length === 0, errors[0])

  const overflow = await page.evaluate(() => {
    document.documentElement.style.width = '390px'
    return document.documentElement.scrollWidth - 390
  })
  await page.setViewportSize({ width: 390, height: 800 })
  await page.waitForTimeout(400)
  const narrow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no sideways overflow at 390px', narrow <= 0, `${narrow}px`)
  await page.close()

  // ── the way in from Data Sync ─────────────────────────────────────────
  const syncCalls = []
  const { page: sync, errors: syncErrors } = await open(ctx, '/admin/sync', syncCalls, null)
  // The sidebar links there too, so scope this to the card on the screen
  // itself — that is the way in the ask was about.
  const card = sync.locator('div.pb-card', { hasText: 'Coming from CricketStatz' })
  const link = card.locator('a[href="/admin/cricketstatz"]')
  ck('Data Sync carries the way in', (await link.count()) === 1,
     `${await link.count()} links in the card`)
  ck('and says what it is for',
     (await sync.locator('text=/Coming from CricketStatz/').count()) === 1)
  if (await link.count()) {
    await link.first().click()
    await sync.waitForTimeout(900)
    ck('it lands on the import screen', sync.url().endsWith('/admin/cricketstatz'), sync.url())
  } else {
    ck('it lands on the import screen', false, 'no link')
  }
  ck('no page errors on Data Sync', syncErrors.length === 0, syncErrors[0])

  await browser.close()
  console.log(`\n${pass} passed, ${fail} failed`)
  process.exit(fail ? 1 : 0)
}

run().catch((e) => { console.error(e); process.exit(1) })
