// The email picture: /preview/:token/dashboard, the season page in capture mode.
//
//   npx vite --port 5204 &
//   node frontend/verification/verify_teaser_dashboard_browser.mjs [baseUrl]
//
// The picture renderer screenshots the element marked data-card once it says
// data-card-ready. Measured: that it is the SAME page (nav bar, header, tiles and
// the three top cards, in the club's colours and light or dark), at 1280px, as
// tall as its content, with nothing a live page has and a picture should not (the
// claim bar, the claim card, the ladder, the footer text, events, a page title);
// that it becomes ready only when the crest has settled, and still becomes ready
// when the crest fails or hangs; the loading and not-found markers the renderer
// reports; and that the screenshot it takes is a real picture.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const TOKEN = 'TokenForDashboard01'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
async function section(name, fn) {
  try { await fn() } catch (e) { fail++; console.log(`FAIL ${name} did not complete  ${String(e.message || e).split('\n')[0].slice(0, 140)}`) }
}

const CREST = '/api/public/teaser/' + TOKEN + '/crest.png?v=abc'
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')
const DATA = {
  club: { name: 'Brisbane Masters Cricket', suburb: 'Chermside West', state: 'QLD', association: 'Queensland Veterans Cricket', logo_url: CREST },
  season: { name: 'Winter 2026', year: 2026 },
  hero: null, lead: null, teams: 4, matches: 69,
  record: { played: 69, won: 33, lost: 21, win_rate: 48 },
  ladders_shown: [{ grade: 'O50 Div 1', rank: 2, teams: 10, place: '2nd' }],
  version: 3,
  batting: [['K. Parekh', 565, 56.5], ['J. Little', 419, 32.23], ['S. Molligoda', 384, 29.54], ['R. Two', 300, 20], ['R. Three', 250, 18]]
    .map(([name, runs, average]) => ({ name, runs, average, high_score: 90, hs_not_out: false })),
  bowling: [['S. Parekh', 20, '6-11'], ['K. Parekh', 17, '4-33'], ['L. Wright', 16, '3-24']]
    .map(([name, wickets, best]) => ({ name, wickets, best, average: 16.7, economy: 4.4 })),
  fielding: [{ name: 'J. Crook', catches: 8, run_outs: 0, stumpings: 0 }],
  records: [{ label: 'Most Individual Runs', value: '100*', player: 'K. Parekh' }, { label: 'Best Bowling Figures', value: '6-11', player: 'S. Parekh' }],
  claim: { ca_org_id: 'CA-1', name: 'Brisbane Masters Cricket' }, registered: null,
  theme: { mode: 'light', accent: '#1f5fbf', accent2: '#d9a21b', on_accent: '#ffffff' },
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ teaser = DATA, missing = false, crest = 'ok', delay = 0, path = `/preview/${TOKEN}/dashboard`, wait = 1500 } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const errors = [], events = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    const json = (b, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(p)) return json({ detail: 'no' }, 401)
    if (/crest\.png/.test(p)) {
      if (crest === 'hang') return // never answered
      if (crest === 'fail') return route.fulfill({ status: 404, body: 'no' })
      return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    }
    if (/public\/teaser\/[^/]+\/event/.test(p)) { events.push(JSON.parse(req.postData() || '{}')); return json({ ok: true }) }
    if (/public\/teaser\//.test(p)) {
      if (delay) await new Promise((r) => setTimeout(r, delay))
      return missing ? json({ detail: 'Not found' }, 404) : json(teaser)
    }
    return json([])
  })
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(wait)
  return { page, ctx, errors, events }
}
const card = (page) => page.locator('[data-card]')
const textOf = async (l) => (await l.count() ? await l.first().innerText() : '')

await section('block 1', async () => {
  const { page, ctx, errors, events } = await open()
  await page.waitForSelector('[data-card][data-card-ready="1"]')
  ck('the picture page has a data-card element that says it is ready', await card(page).count() === 1)
  const box = await card(page).boundingBox()
  ck('it is 1280 pixels wide and as tall as its content', box && Math.round(box.width) === 1280 && box.height > 500 && box.height < 1100, JSON.stringify(box))
  const fits = await card(page).evaluate((e) => e.scrollHeight <= e.clientHeight + 1 && e.scrollWidth <= e.clientWidth + 1)
  ck('nothing overflows its frame (the renderer refuses a card that does)', fits)
  const t = await textOf(card(page))
  ck('it is the club dashboard: crest, name, season, tiles', /Brisbane Masters Cricket/.test(t) && /CLUB DASHBOARD/.test(t) && /WINTER 2026/.test(t) && /WIN RATE/.test(t) && /48/.test(t))
  ck('with top batters, top bowlers and season best, names and figures', /TOP BATTERS/.test(t) && /K\. Parekh/.test(t) && /565/.test(t) && /TOP BOWLERS/.test(t) && /SEASON BEST/.test(t) && /100\*/.test(t) && /6-11/.test(t))
  ck('and the paid club menu bar', ['Players', 'Stats', 'Games', 'Compare', 'Yearbook', 'Website'].every((w) => t.includes(w)) && /PLAYER DASHBOARD/.test(t))
  ck('the menu bar is not sticky (it is part of the picture)', await page.evaluate(() => getComputedStyle(document.querySelector('[data-testid="teaser-nav"]')).position) !== 'sticky')
  ck('the three cards sit side by side (the full desktop layout)', await page.evaluate(() => {
    const ys = ['batting', 'bowling', 'records'].map((k) => Math.round(document.querySelector(`[data-tile="${k}"]`).getBoundingClientRect().top))
    return new Set(ys).size === 1
  }))
  ck('there is no claim bar, no claim card, no ladder card, no footer text and no registered notice',
     await page.locator('[data-testid="teaser-bar-cta"]').count() === 0 && await page.locator('[data-testid="teaser-sheet"]').count() === 0
     && await page.locator('[data-testid="teaser-ladders"]').count() === 0 && !/Something not right|one season of Cricket Australia/.test(t)
     && await page.locator('[data-testid="teaser-registered"]').count() === 0)
  ck('it carries no page-view event and leaves the page title alone', events.length === 0 && !/your Winter 2026/.test(await page.title()), JSON.stringify(events))
  ck('the club\'s colours and light theme are applied', (await page.evaluate(() => getComputedStyle(document.querySelector('[data-card]')).getPropertyValue('--pb-accent').trim())).toLowerCase() === '#1f5fbf'
     && await card(page).getAttribute('data-mode') === 'light')
  ck('no page errors', errors.length === 0, errors.join(' | '))
  const shot = await card(page).screenshot({ type: 'png' })
  ck('the screenshot is a real picture of that size', shot.slice(0, 8).toString('hex') === '89504e470d0a1a0a' && shot.length > 20000, String(shot.length))
  await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/email-dashboard.png` : '/tmp/email-dashboard.png', clip: { x: 0, y: 0, width: box.width, height: box.height } })
  await ctx.close()
})

await section('dark', async () => {
  const { page, ctx } = await open({ teaser: { ...DATA, theme: { mode: 'dark', accent: '#e23b3b', accent2: null, on_accent: '#ffffff' } } })
  await page.waitForSelector('[data-card][data-card-ready="1"]')
  ck('a dark club is drawn on the dark theme with its own accent', await card(page).getAttribute('data-mode') === 'dark'
     && (await page.evaluate(() => getComputedStyle(document.querySelector('[data-card]')).getPropertyValue('--pb-accent').trim())).toLowerCase() === '#e23b3b')
  await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/email-dashboard-dark.png` : '/tmp/email-dashboard-dark.png', clip: { x: 0, y: 0, width: 1280, height: (await card(page).boundingBox()).height } })
  await ctx.close()
})

await section('no theme', async () => {
  const { page, ctx } = await open({ teaser: { ...DATA, club: { ...DATA.club, logo_url: null }, theme: null } })
  await page.waitForSelector('[data-card][data-card-ready="1"]')
  ck('a club with no crest and no theme is drawn in BetterCricket\'s green on dark, with no crest in the picture',
     (await page.evaluate(() => getComputedStyle(document.querySelector('[data-card]')).getPropertyValue('--pb-accent').trim())).toLowerCase() === '#16c784'
     && await card(page).getAttribute('data-mode') === 'dark' && await page.locator('[data-card] img[alt=""]').count() === 0)
  await ctx.close()
})

await section('ready waits for the crest', async () => {
  const { page, ctx } = await open({ crest: 'hang', wait: 800 })
  ck('while the crest is still loading it is NOT ready (it would be drawn without it)', await card(page).getAttribute('data-card-ready') === '0')
  await page.waitForSelector('[data-card][data-card-ready="1"]', { timeout: 9000 })
  ck('a crest host that never answers does not hold it up for ever: it gives up and is ready', true)
  await ctx.close()
})
await section('failing crest', async () => {
  const { page, ctx } = await open({ crest: 'fail' })
  await page.waitForSelector('[data-card][data-card-ready="1"]', { timeout: 4000 })
  ck('a crest that fails to load settles at once and the picture is drawn without it', true)
  ck('the broken image is hidden, not shown', await page.evaluate(() => [...document.querySelectorAll('[data-card] img[alt=""], [data-card] img[data-testid="teaser-nav-logo"]')].every((i) => getComputedStyle(i).display === 'none')))
  await ctx.close()
})

await section('loading and missing', async () => {
  const a = await open({ delay: 2500, wait: 600 })
  ck('while the data is on its way the page says so (the renderer reports it)', await a.page.locator('[data-testid="teaser-card-loading"]').count() === 1 && await card(a.page).count() === 0)
  await a.ctx.close()
  const b = await open({ missing: true })
  ck('an unknown or no-longer-good snapshot says not found, and draws no card', await b.page.locator('[data-testid="teaser-card-missing"]').count() === 1 && await card(b.page).count() === 0)
  await b.ctx.close()
})

await section('the live page is unchanged', async () => {
  const { page, ctx } = await open({ path: `/preview/${TOKEN}` })
  ck('the ordinary page still has its claim bar and is not a data-card', await page.locator('[data-testid="teaser-bar-cta"]').count() === 1
     && await page.locator('[data-card]').count() === 0 && await page.locator('[data-testid="teaser-ladders"]').count() === 1)
  await ctx.close()
})

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
