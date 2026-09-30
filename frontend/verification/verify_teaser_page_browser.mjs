// A prospect club's teaser page (/preview/:token) and its hand-off to the trial wizard.
//
//   npx vite --port 5204 &
//   node frontend/verification/verify_teaser_page_browser.mjs [baseUrl]
//
// Measured: what the page leads with and what it leaves out, that EVERY tile
// opens the same claim sheet, the exact events sent, that Escape and the
// backdrop close it, the registered and not-found states, no club navbar or
// CTA bar, and 390px. Then the other half: /trial?teaser=... opens the wizard
// on the right club (or the club's own site, or a prefilled search).
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const TOKEN = 'TokenForPageClub0001'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const FLEM = {
  club: { name: 'Flemington Cricket Club', suburb: 'Ascot Vale', state: 'VIC', association: 'Mercantile Cricket Association', logo_url: null },
  season: { name: 'Summer 2025/26', year: 2025 },
  hero: { kind: 'runs', player: 'K. Parekh', value: 565, unit: 'runs', detail: 'average 56.5, highest score 100*, 1 hundred' },
  lead: { grade: 'A Reserve', rank: 8, teams: 8 }, teams: 4, matches: 61, record: null, ladders_shown: [],
  history: { seasons_listed: 20, first_year: 2005 }, version: 3,
  batting: [['K. Parekh', 565, 56.5], ['J. Little', 419, 32.23], ['S. Molligoda', 384, 29.54], ['R. Two', 300, 20], ['R. Three', 250, 18]]
    .map(([name, runs, average]) => ({ name, runs, average, high_score: 90, hs_not_out: false, fifties: 1, hundreds: 0 })),
  bowling: [['S. Parekh', 20, '6-11'], ['K. Parekh', 17, '4-33'], ['L. Wright', 16, '3-24']]
    .map(([name, wickets, best]) => ({ name, wickets, best, average: 16.7, economy: 4.4 })),
  fielding: [{ name: 'J. Crook', catches: 8, run_outs: 0, stumpings: 0 }, { name: 'J. Delaney', catches: 8, run_outs: 1, stumpings: 2 }],
  records: [{ label: 'Most Individual Runs', value: '100*', player: 'K. Parekh' }, { label: 'Best Bowling Figures', value: '6-11', player: 'S. Parekh' }],
  claim: { ca_org_id: 'CA-ORG-1', name: 'Flemington Cricket Club' }, registered: null,
}
const BRIS = {
  ...FLEM,
  club: { name: 'Brisbane Masters Cricket', suburb: 'Chermside West', state: 'QLD', association: 'Queensland Veterans Cricket', logo_url: null },
  season: { name: 'Winter 2026', year: 2026 },
  hero: { kind: 'wickets', player: 'P. Matthews', value: 26, unit: 'wickets', detail: 'average 14.77, best 4-28' },
  matches: 69, record: { played: 69, won: 33, lost: 21, win_rate: 48 },
  ladders_shown: [{ grade: 'O50 Div 1', rank: 2, teams: 10, place: '2nd' }, { grade: 'O60 Div 1', rank: 2, teams: 8, place: '2nd' }],
  claim: { ca_org_id: 'CA-ORG-2', name: 'Brisbane Masters Cricket' },
}

// A section that throws (a missing element in a control run, a timeout) is
// REPORTED as one failure and the rest still run: a control run that crashes on
// its first missing locator says nothing about the other forty checks.
async function section(name, fn) {
  try { await fn() } catch (e) { fail++; console.log(`FAIL ${name} did not complete  ${String(e.message || e).split('\n')[0].slice(0, 120)}`) }
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(path, { teaser = FLEM, missing = false, search = null, width = 1300 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(4000)
  const errors = [], events = [], calls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    calls.push(`${req.method()} ${p}`)
    const json = (b, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(p)) return json({ detail: 'no' }, 401)
    if (/public\/teaser\/[^/]+\/event/.test(p)) {
      events.push(JSON.parse(req.postData() || '{}')); return json({ ok: true })
    }
    if (/public\/teaser\//.test(p)) return missing ? json({ detail: 'Not found' }, 404) : json(teaser)
    if (/public\/self-serve\/status/.test(p)) return json({ enabled: true, default_trial_days: 14 })
    if (/public\/self-serve\/search/.test(p)) return json(search || [])
    return json([])
  })
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1200)
  return { page, ctx, errors, events, calls }
}

const textOf = async (l) => (await l.count() ? await l.first().innerText() : '')
const tile = (page, id) => page.locator(`[data-tile="${id}"]`)
const sheet = (page) => page.locator('[data-testid="teaser-sheet"]')

// ---- 1. The page a club at the foot of its ladder sees -----------------------
await section('block 1', async () => {
  const { page, ctx, errors, events } = await open(`/preview/${TOKEN}`)
  ck('the club and its place are named', /Flemington Cricket Club/.test(await textOf(page.locator('[data-testid="teaser-club"]')))
     && /Ascot Vale, VIC/.test(await textOf(page.locator('main'))))
  ck('the season is shown', /Summer 2025\/26/.test(await textOf(page.locator('main'))))
  ck('it LEADS with the top run-scorer: 565 runs, named', (await textOf(page.locator('[data-testid="teaser-hero-value"]'))) === '565'
     && /K\. Parekh/.test(await textOf(page.locator('[data-testid="teaser-hero-player"]'))))
  ck('with the average, highest score and hundred beneath', /average 56\.5, highest score 100\*, 1 hundred/.test(await textOf(tile(page, 'hero'))))
  ck('there is NO season record tile for a club that lost most of its games', await tile(page, 'record').count() === 0)
  ck('and no ladder tile when no grade is in the top half', await tile(page, 'ladder').count() === 0)
  ck('batting, bowling, fielding and records are shown',
     await tile(page, 'batting').count() === 1 && await tile(page, 'bowling').count() === 1
     && await tile(page, 'fielding').count() === 1 && await tile(page, 'records').count() === 1)
  const rows = await page.locator('[data-tile="batting"] li').evaluateAll((els) => els.map((e) => getComputedStyle(e).opacity))
  ck('batting shows five rows, the first three full and the last two dimmed', rows.length === 5
     && rows.slice(0, 3).every((o) => o === '1') && rows.slice(3).every((o) => Number(o) < 0.6), rows.join(','))
  ck('the source is stated', /Cricket Australia's public match data for Summer 2025\/26/.test(await textOf(page.locator('main'))))
  ck('the tab title names the club and season', /Flemington Cricket Club: your Summer 2025\/26/.test(await page.title()))
  ck('the page tells search engines not to index it',
     await page.locator('meta[name="robots"]').first().getAttribute('content') === 'noindex, nofollow')
  ck('a view event was sent exactly once', events.filter((e) => e.kind === 'view').length === 1, JSON.stringify(events))
  ck('there is no club navbar and no CTA bar of the site', await page.locator('nav').count() === 0
     && !/get your club on BetterCricket/i.test(await textOf(page.locator('body'))))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
})

// ---- 2. Every tile opens the SAME sheet, and reports where -------------------
for (const id of ['hero', 'batting', 'bowling', 'fielding', 'records']) await section(`tile ${id}`, async () => {
  const { page, ctx, events } = await open(`/preview/${TOKEN}`)
  await tile(page, id).click()
  await page.waitForTimeout(300)
  const s = await textOf(sheet(page))
  ck(`tapping ${id} opens the claim sheet naming the club`, /Flemington Cricket Club's season/.test(s), s.slice(0, 80))
  ck(`${id}: the tap is reported with its section, then claim_open`,
     events.some((e) => e.kind === 'tile' && e.section === id) && events.some((e) => e.kind === 'claim_open' && e.section === id),
     JSON.stringify(events))
  await ctx.close()
})
await section('block 2', async () => {
  const { page, ctx, events } = await open(`/preview/${TOKEN}`)
  await tile(page, 'batting').click()
  await page.waitForTimeout(200)
  const s = await textOf(sheet(page))
  ck('the sheet says what the club gets, including the years back', /back to 2005/.test(s) && /Free trial, no card/.test(s), s)
  ck('the primary button has the focus when it opens', await page.evaluate(() => document.activeElement?.getAttribute('data-testid')) === 'teaser-sheet-go')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(200)
  ck('Escape closes it', await sheet(page).count() === 0)
  ck('and puts the focus back on the tile that opened it', await page.evaluate(() => document.activeElement?.getAttribute('data-tile')) === 'batting')
  await page.locator('[data-testid="teaser-bar-cta"]').click()
  await page.waitForTimeout(200)
  ck('the bottom button reads "Claim <club> free" and opens the same sheet', /Claim Flemington Cricket Club free/.test(await textOf(page.locator('[data-testid="teaser-bar-cta"]'))) && await sheet(page).count() === 1)
  ck('opened from a button it reports claim_open for the header, not a tile',
     events.some((e) => e.kind === 'claim_open' && e.section === 'header'))
  await page.locator('[data-testid="teaser-sheet-backdrop"]').click({ position: { x: 5, y: 5 } })
  await page.waitForTimeout(200)
  ck('the backdrop closes it', await sheet(page).count() === 0)
  await page.locator('[data-testid="teaser-header-cta"]').click()
  await page.waitForTimeout(150)
  await page.locator('[data-testid="teaser-sheet-close"]').click()
  ck('"Not now" closes it', await sheet(page).count() === 0)
  await page.locator('[data-testid="teaser-header-cta"]').click()
  await page.locator('[data-testid="teaser-sheet-go"]').click()
  await page.waitForTimeout(400)
  ck('Claim goes to the trial wizard carrying the token', new URL(page.url()).pathname === '/trial'
     && new URL(page.url()).searchParams.get('teaser') === TOKEN, page.url())
  ck('and reports claim_go', events.some((e) => e.kind === 'claim_go'))
  ck('every event carried a visitor id', events.length > 0 && events.every((e) => typeof e.visitor_id === 'string' && e.visitor_id.length > 5), JSON.stringify(events[0]))
  await ctx.close()
})

// ---- 3. A club that did well is shown its record and ladder places ---------------
await section('block 3', async () => {
  const { page, ctx } = await open(`/preview/${TOKEN}`, { teaser: BRIS })
  ck('a wicket-taker can lead: "Leading wicket-taker", 26', /leading wicket-taker/i.test(await textOf(tile(page, 'hero')))
     && await textOf(page.locator('[data-testid="teaser-hero-value"]')) === '26')
  const rec = await textOf(page.locator('[data-testid="teaser-record"]'))
  ck('the record is shown when it flatters: 69 played, 33 won, 21 lost', /69/.test(rec) && /33/.test(rec) && /21/.test(rec), rec)
  const lad = await textOf(page.locator('[data-testid="teaser-ladders"]'))
  ck('ladder places read "2nd of 10"', /O50 Div 1/.test(lad) && /2nd/.test(lad) && /of 10/.test(lad), lad)
  await ctx.close()
})

// ---- 4. Already registered, and a bad link ------------------------------------
await section('block 4', async () => {
  const { page, ctx, events } = await open(`/preview/${TOKEN}`, { teaser: { ...BRIS, registered: { slug: 'brisbane-masters' } } })
  ck('a registered club is told so, with a link to its site', /already on BetterCricket/.test(await textOf(page.locator('[data-testid="teaser-registered"]'))))
  ck('the button offers the club site, not a trial', /Open Brisbane Masters Cricket's site/.test(await textOf(page.locator('[data-testid="teaser-bar-cta"]'))))
  await page.locator('[data-testid="teaser-bar-cta"]').click()
  await page.locator('[data-testid="teaser-sheet-go"]').click()
  await page.waitForTimeout(400)
  ck('and takes it to /brisbane-masters', new URL(page.url()).pathname === '/brisbane-masters', page.url())
  await ctx.close()
})
await section('block 5', async () => {
  const { page, ctx, errors } = await open(`/preview/${TOKEN}`, { missing: true })
  ck('an invalid link says so and offers to find the club', /not valid any more/.test(await textOf(page.locator('[data-testid="teaser-missing"]')))
     && await page.locator('a[href="/trial"]').count() >= 1)
  ck('and shows no club data', await page.locator('[data-testid="teaser-page"]').count() === 0 && errors.length === 0, errors.join('|'))
  await ctx.close()
})

// ---- 5. Phone width --------------------------------------------------------------
await section('block 6', async () => {
  const { page, ctx } = await open(`/preview/${TOKEN}`, { teaser: BRIS, width: 390 })
  const m = await page.evaluate(() => ({ over: document.documentElement.scrollWidth - document.documentElement.clientWidth }))
  ck('no horizontal overflow at 390px', m.over <= 0, JSON.stringify(m))
  await tile(page, 'bowling').click()
  await page.waitForTimeout(250)
  const box = await sheet(page).boundingBox()
  ck('the sheet sits inside the viewport at 390px', box && box.x >= 0 && box.x + box.width <= 390.5 && box.y >= 0 && box.y + box.height <= 900, JSON.stringify(box))
  await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/sheet-390.png` : '/tmp/sheet-390.png' })
  await ctx.close()
})

// ---- 6. The hand-off: /trial?teaser=... opens the wizard on that club ----------------
const RESULTS = [
  { id: 'other-id', name: 'Flemington Colts Cricket Club', already_registered: false },
  { id: 'CA-ORG-1', name: 'Flemington Cricket Club', already_registered: false },
]
await section('block 7', async () => {
  const { page, ctx, calls } = await open(`/trial?teaser=${TOKEN}`, { search: RESULTS })
  await page.waitForTimeout(800)
  const wizardOpen = await page.getByText(/Start your club's 14 Day Free Trial/i).count() > 0
  const field = await page.locator('input[value="Flemington Cricket Club"]').count()
  const colts = await page.locator('input[value="Flemington Colts Cricket Club"]').count()
  ck('the wizard opens on the club whose org id matches the teaser (not the first hit)',
     wizardOpen && field === 1 && colts === 0, `wizard=${wizardOpen} field=${field} colts=${colts}`)
  ck('it searched by the club name', calls.some((c) => /public\/self-serve\/search/.test(c)))
  await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/handoff.png` : '/tmp/handoff.png' })
  await ctx.close()
})
await section('block 8', async () => {
  const { page, ctx } = await open(`/trial?teaser=${TOKEN}`, { search: [{ ...RESULTS[1], already_registered: true, already_registered_slug: 'flemington-cc' }] })
  await page.waitForTimeout(600)
  ck('a club already registered is sent to its own site', new URL(page.url()).pathname === '/flemington-cc', page.url())
  await ctx.close()
})
await section('block 9', async () => {
  const { page, ctx } = await open(`/trial?teaser=${TOKEN}`, { search: [] })
  await page.waitForTimeout(700)
  const v = await page.locator('input').first().inputValue().catch(() => '')
  ck('a club that cannot be placed lands as a prefilled search box', /Flemington Cricket Club/.test(v), v)
  await ctx.close()
})
await section('block 10', async () => {
  const { page, ctx, errors } = await open('/trial', { search: RESULTS })
  ck('the ordinary /trial page is unchanged (no wizard, no search)', await page.locator('[role="dialog"]').count() === 0 && errors.length === 0)
  await ctx.close()
})

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
