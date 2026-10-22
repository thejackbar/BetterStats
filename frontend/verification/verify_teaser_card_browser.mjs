// The picture card the renderer screenshots (/preview/:token/card/:format).
//
//   npx vite --port 5204 &
//   node frontend/verification/verify_teaser_card_browser.mjs [baseUrl]
//
// Measured, per format: the frame is exactly the size the renderer expects, the
// ready flag only comes up once the figures are in, the content fits the frame
// (the renderer refuses a card that overflows), and what is printed. The point
// that matters most to a club: only the email card prints a player's name, the
// two ad sizes never do. Then the awkward clubs: a very long name, a club with
// nothing flattering to say, no logo (a crest of initials), a logo that fails to
// load, an unknown token and an unknown format.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const TOKEN = 'TokenForCardClub0001'
const SIZES = { card: [1200, 630], feed: [1080, 1350], story: [1080, 1920] }

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
async function section(name, fn) {
  try { await fn() } catch (e) { fail++; console.log(`FAIL ${name} did not complete  ${String(e.message || e).split('\n')[0].slice(0, 120)}`) }
}

const DATA = {
  club: { name: 'Flemington Cricket Club', suburb: 'Ascot Vale', state: 'VIC', association: 'Mercantile Cricket Association', logo_url: null },
  season: { name: 'Summer 2025/26', year: 2025 },
  hero: { kind: 'runs', player: 'K. Parekh', value: 565, unit: 'runs', detail: 'average 56.5, highest score 100*, 1 hundred' },
  teams: 3, matches: 61, record: { played: 61, won: 40, lost: 11, win_rate: 66 },
  ladders_shown: [{ grade: 'D Sunday', rank: 2, teams: 8, place: '2nd' }],
  history: { seasons_listed: 20, first_year: 2005 }, version: 3,
  batting: [{ name: 'K. Parekh', runs: 565, average: 56.5 }, { name: 'J. Little', runs: 419 }, { name: 'S. M', runs: 384 }],
  bowling: [{ name: 'S. Parekh', wickets: 20, best: '6-11' }, { name: 'K. Parekh', wickets: 17 }, { name: 'L. Wright', wickets: 16 }],
  fielding: [], records: [{ label: 'Most Individual Runs', value: '100*', player: 'K. Parekh' }],
  claim: { ca_org_id: 'CA-1', name: 'Flemington Cricket Club' }, registered: null,
}
const NAMES = ['K. Parekh', 'S. Parekh', 'J. Little', 'L. Wright']

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(fmt, { data = DATA, status = 200, delay = 0, logo = null, token = TOKEN } = {}) {
  const [w, h] = SIZES[fmt] || [1200, 630]
  const ctx = await browser.newContext({ viewport: { width: w, height: h } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(5000)
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/broken-logo.png', (r) => r.fulfill({ status: 404, body: '' }))
  await page.route('**/api/**', async (route) => {
    const p = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    const json = (b, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(p)) return json({ detail: 'no' }, 401)
    if (/public\/teaser\//.test(p)) {
      if (delay) await new Promise((r) => setTimeout(r, delay))
      return status === 200 ? json({ ...data, club: { ...data.club, logo_url: logo ?? data.club.logo_url } }) : json({ detail: 'Not found' }, status)
    }
    return json([])
  })
  await page.goto(`${BASE}/preview/${token}/card/${fmt}`, { waitUntil: 'domcontentloaded' })
  return { page, ctx, errors }
}
const card = (page) => page.locator('[data-card]')
const ready = (page) => page.waitForSelector('[data-card][data-card-ready="1"]')
const fits = (page) => card(page).evaluate((e) => ({ over: e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1, w: e.clientWidth, h: e.clientHeight }))
const text = async (page) => (await card(page).innerText()).replace(/\s+/g, ' ')

for (const [fmt, [w, h]] of Object.entries(SIZES)) {
  await section(`format ${fmt}`, async () => {
    const { page, ctx, errors } = await open(fmt)
    await ready(page)
    const f = await fits(page)
    ck(`${fmt}: the frame is exactly ${w} by ${h}`, f.w === w && f.h === h, JSON.stringify(f))
    ck(`${fmt}: the content fits the frame (a card that overflows is refused by the renderer)`, !f.over)
    const t = await text(page)
    ck(`${fmt}: it names the club, the season and the lead figure`, /Flemington Cricket Club/.test(t) && /Summer 2025\/26/i.test(t) && /565/.test(t))
    const facts = await page.locator('[data-card-fact]').count()
    ck(`${fmt}: between one and three supporting facts`, facts >= 1 && facts <= 3, String(facts))
    const named = NAMES.filter((n) => t.includes(n))
    if (fmt === 'card') ck('card: the email card names the player behind the figure', named.includes('K. Parekh'), t.slice(0, 200))
    else ck(`${fmt}: an ad never prints a player's name`, named.length === 0, named.join(', '))
    ck(`${fmt}: the call to action fits the format`, fmt === 'card' ? /See the whole season/.test(t) : /Claim it free/.test(t))
    ck(`${fmt}: no navbar, cookie bar or other fixed chrome sits over the picture`,
       await page.evaluate(() => [...document.querySelectorAll('body *')].filter((e) => {
         const s = getComputedStyle(e); return s.position === 'fixed' && e.getBoundingClientRect().width > 100
       }).length === 0))
    ck(`${fmt}: no page errors`, errors.length === 0, errors.join(' | '))
    await ctx.close()
  })
}

await section('ready flag', async () => {
  const { page, ctx } = await open('card', { delay: 900 })
  await page.waitForTimeout(250)
  ck('before the figures arrive there is no card marked ready', (await page.locator('[data-card][data-card-ready="1"]').count()) === 0)
  await ready(page)
  ck('and once they have, it is', (await page.locator('[data-card-ready="1"]').count()) === 1)
  await ctx.close()
})

await section('no logo', async () => {
  const { page, ctx } = await open('card')
  await ready(page)
  ck('a club with no logo gets a crest of its initials (not a gap, not a broken image)',
     /^F$/.test((await page.locator('[data-card] [style*="border: 2px solid"]').first().innerText()).trim())
     && (await page.locator('[data-card] img[crossorigin]').count()) === 0)
  await ctx.close()
})

await section('logo that fails', async () => {
  const { page, ctx } = await open('card', { logo: 'http://127.0.0.1:5204/broken-logo.png' })
  await ready(page)
  ck('a logo that will not load falls back to the crest and the card still becomes ready',
     (await page.locator('[data-card-ready="1"]').count()) === 1 && (await page.locator('[data-card] img[crossorigin]').count()) === 0)
  await ctx.close()
})

await section('logo that hangs', async () => {
  const { page, ctx } = await open('card', { logo: 'http://127.0.0.1:5204/hang-logo.png' })
  await page.route('**/hang-logo.png', () => { /* never answers */ })
  const t0 = Date.now()
  await page.waitForSelector('[data-card][data-card-ready="1"]', { timeout: 12000 })
  const waited = Date.now() - t0
  ck('a logo host that never answers does not hold the card: it is ready within about 5 seconds, with the crest',
     waited < 9000 && (await page.locator('[data-card] img[crossorigin]').count()) === 0, `${waited}ms`)
  await ctx.close()
})

await section('logo that loads', async () => {
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64')
  const { page, ctx } = await open('card', { logo: 'http://127.0.0.1:5204/ok-logo.png' })
  await page.route('**/ok-logo.png', (r) => r.fulfill({ status: 200, contentType: 'image/png', body: png }))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await ready(page)
  await page.waitForTimeout(6000)
  ck('a logo that loaded stays on the card after the give-up time has passed (the timer does not undo it)',
     (await page.locator('[data-card] img[crossorigin]').count()) === 1)
  await ctx.close()
})

await section('long name', async () => {
  const long = { ...DATA, club: { ...DATA.club, name: 'Brisbane Masters Cricket Incorporated Seniors and Veterans Association of Queensland' } }
  for (const fmt of Object.keys(SIZES)) {
    const { page, ctx } = await open(fmt, { data: long })
    await ready(page)
    const f = await fits(page)
    ck(`${fmt}: an 80 character club name still fits the frame`, !f.over, JSON.stringify(f))
    await ctx.close()
  }
})

await section('nothing flattering', async () => {
  const bare = { ...DATA, record: null, ladders_shown: [], records: [], bowling: [{ name: 'X', wickets: 2 }] }
  for (const fmt of Object.keys(SIZES)) {
    const { page, ctx } = await open(fmt, { data: bare })
    await ready(page)
    const f = await fits(page)
    ck(`${fmt}: a club with no record, ladder or records still draws a complete card`, !f.over && /565/.test(await text(page)))
    await ctx.close()
  }
  const noHero = { ...bare, hero: null, batting: [], bowling: [] }
  const { page, ctx } = await open('feed', { data: noHero })
  await ready(page)
  ck('and a club with no lead figure at all does not crash the page', (await page.locator('[data-card]').count()) === 1)
  await ctx.close()
})

await section('wickets lead', async () => {
  const w = { ...DATA, hero: { kind: 'wickets', player: 'S. Parekh', value: 26, unit: 'wickets', detail: 'average 14.77' } }
  const { page, ctx } = await open('story', { data: w })
  await ready(page)
  const t = await text(page)
  ck('a wicket-taker lead reads as such, with the top run-scorer as a supporting fact, unnamed in an ad',
     /Leading wicket-taker/i.test(t) && /Top run-scorer/i.test(t) && !/S\. Parekh|K\. Parekh/.test(t), t.slice(0, 160))
  await ctx.close()
})

await section('bad requests', async () => {
  let r = await open('card', { status: 404 })
  await r.page.waitForSelector('[data-testid="teaser-card-missing"]')
  ck('an unknown token shows nothing a renderer could mistake for a card', (await r.page.locator('[data-card]').count()) === 0)
  await r.ctx.close()
  r = await open('huge')
  await r.page.waitForSelector('[data-testid="teaser-card-unknown"]')
  ck('an unknown format is not drawn', (await r.page.locator('[data-card]').count()) === 0)
  await r.ctx.close()
})

await section('not indexed', async () => {
  const { page, ctx } = await open('card')
  await ready(page)
  ck('the card page tells search engines to stay away', (await page.locator('meta[name="robots"]').getAttribute('content')) === 'noindex, nofollow')
  await ctx.close()
})

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
