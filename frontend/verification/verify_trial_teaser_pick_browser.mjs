// /trial: a visitor searches for their club, picks it, and (when we hold a season
// page for it) goes straight to that page.
//
//   npx vite --port 5204 &
//   node frontend/verification/verify_trial_teaser_pick_browser.mjs [baseUrl]
//
// Measured: the exact lookup request on the wire (every id the picker gave, once
// each), that a club with a page lands on /preview/<token>, that a club without
// one, a lookup that fails, and a registered club all behave as they did before
// (the ordinary choice, the ordinary choice, the club's own site with NO lookup),
// that the row says it is opening and the others cannot be pressed meanwhile, that
// a double press makes one request, and 390px.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const TOKEN = 'TokenForRenmark0001'
const PAUSED_TOKEN = 'TokenForPaused00001'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
async function section(name, fn) {
  try { await fn() } catch (e) { fail++; console.log(`FAIL ${name} did not complete  ${String(e.message || e).split('\n')[0].slice(0, 120)}`) }
}

const RESULTS = [
  { id: 'CA-RENMARK', playHQId: 'PH-RENMARK', organisationGuid: 'CA-RENMARK', name: 'Renmark North Cricket Club', already_registered: false },
  { id: 'CA-PLAIN', playHQId: 'PH-PLAIN', name: 'Plainville Cricket Club', already_registered: false },
  { id: 'CA-REG', playHQId: 'PH-REG', name: 'Registered Cricket Club', already_registered: true, already_registered_slug: 'registered-cc' },
  { id: 'CA-PAUSED', playHQId: 'PH-PAUSED', name: 'Lapsed Cricket Club', already_registered: true, already_registered_paused: true, already_registered_slug: 'lapsed-cc' },
  { id: 'CA-PAUSED2', playHQId: 'PH-PAUSED2', name: 'Lapsed No Page Cricket Club', already_registered: true, already_registered_paused: true, already_registered_slug: 'lapsed-two-cc' },
]
const TEASER = {
  club: { name: 'Renmark North Cricket Club', suburb: 'Renmark', state: 'SA', association: 'Riverland Cricket Association', logo_url: null },
  season: { name: 'Summer 2025/26', year: 2025 },
  hero: { kind: 'runs', player: 'K. Parekh', value: 565, unit: 'runs', detail: 'average 56.5' },
  lead: null, teams: 1, matches: 20, record: null, ladders_shown: [], history: {}, version: 1,
  batting: [{ name: 'K. Parekh', runs: 565, average: 56.5 }], bowling: [], fielding: [], records: [],
  claim: { ca_org_id: 'CA-RENMARK', name: 'Renmark North Cricket Club' }, registered: null,
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ byClub, delay = 0, width = 1300, path = null } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(6000)
  const errors = [], lookups = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const u = new URL(req.url())
    const p = u.pathname.replace(/^\/api/, '')
    const json = (b, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(p)) return json({ detail: 'no' }, 401)
    if (/public\/self-serve\/status/.test(p)) return json({ enabled: true, default_trial_days: 14 })
    if (/public\/self-serve\/search/.test(p)) return json(RESULTS)
    if (/public\/teaser\/by-club/.test(p)) {
      lookups.push(u.searchParams.getAll('id'))
      if (delay) await new Promise((r) => setTimeout(r, delay))
      if (byClub === 'error') return json({ detail: 'boom' }, 500)
      const ids = u.searchParams.getAll('id')
      if (ids.includes('CA-RENMARK')) return json({ found: true, token: TOKEN })
      if (ids.includes('CA-PAUSED')) return json({ found: true, token: PAUSED_TOKEN })
      return json({ found: false })
    }
    if (/public\/teaser\/[^/]+\/event/.test(p)) return json({ ok: true })
    if (/public\/teaser\//.test(p)) {
      if (p.includes(PAUSED_TOKEN)) return json({ ...TEASER, club: { ...TEASER.club, name: 'Lapsed Cricket Club' }, claim: { ca_org_id: 'CA-PAUSED', name: 'Lapsed Cricket Club' }, registered: null })
      return json(TEASER)
    }
    return json([])
  })
  await page.goto(`${BASE}${path || '/trial'}`, { waitUntil: 'domcontentloaded' })
  if (!path) {
    await page.getByLabel('Search for your club').fill('club')
    await page.waitForSelector('button:has-text("Renmark North Cricket Club")')
  }
  return { page, ctx, errors, lookups }
}
const row = (page, name) => page.locator('button', { hasText: name }).first()

await section('a club with a season page', async () => {
  const { page, ctx, errors, lookups } = await open()
  await row(page, 'Renmark North Cricket Club').click()
  await page.waitForURL(`**/preview/${TOKEN}`)
  ck('picking it opens its season page, /preview/<token>', new URL(page.url()).pathname === `/preview/${TOKEN}`)
  ck('exactly one lookup was made, with every id the picker gave once each (CA id, PlayHQ id)',
     lookups.length === 1 && JSON.stringify(lookups[0]) === JSON.stringify(['CA-RENMARK', 'PH-RENMARK']), JSON.stringify(lookups))
  await page.waitForSelector('[data-testid="teaser-page"]')
  ck('and the page is that club\'s', /Renmark North Cricket Club/.test(await page.locator('[data-testid="teaser-club"]').innerText()))
  ck('with the claim button the page always has', await page.locator('[data-testid="teaser-bar-cta"]').count() === 1)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
})

await section('a club with no season page', async () => {
  const { page, ctx, lookups } = await open()
  await row(page, 'Plainville Cricket Club').click()
  await page.waitForSelector('[data-testid="trial-not-yet-heading"]')
  ck('the ordinary set-up choice opens, as before', await page.locator('[data-testid="trial-not-yet-heading"]').count() === 1)
  ck('and we stayed on /trial', new URL(page.url()).pathname === '/trial')
  ck("the lookup used that club's own ids", lookups.length === 1 && lookups[0].includes('CA-PLAIN') && !lookups[0].includes('CA-RENMARK'), JSON.stringify(lookups))
  await ctx.close()
})

await section('a lookup that fails', async () => {
  const { page, ctx } = await open({ byClub: 'error' })
  await row(page, 'Renmark North Cricket Club').click()
  await page.waitForSelector('[data-testid="trial-not-yet-heading"]')
  ck('a server error falls back to the ordinary choice (the visitor is never stuck)', new URL(page.url()).pathname === '/trial')
  await ctx.close()
})

await section('a club already on BetterCricket', async () => {
  const { page, ctx, lookups } = await open()
  await row(page, 'Registered Cricket Club').click()
  await page.waitForURL('**/registered-cc')
  ck('goes to its own site, as before', new URL(page.url()).pathname === '/registered-cc')
  ck('and makes NO teaser lookup', lookups.length === 0, JSON.stringify(lookups))
  await ctx.close()
})

await section('while the lookup runs', async () => {
  const { page, ctx, lookups } = await open({ delay: 900 })
  const r = row(page, 'Renmark North Cricket Club')
  await r.click()
  await page.waitForTimeout(250)
  ck('the picked row says it is opening', /Opening/.test(await r.innerText()))
  ck('every result is disabled meanwhile, so a second club cannot be picked', await row(page, 'Plainville Cricket Club').isDisabled())
  await r.click({ force: true, noWaitAfter: true, timeout: 500 }).catch(() => {})
  await page.waitForURL(`**/preview/${TOKEN}`)
  ck('a second press made no second lookup', lookups.length === 1, String(lookups.length))
  await ctx.close()
})

await section('a club whose trial has ended', async () => {
  const { page, ctx, lookups } = await open()
  await row(page, 'Lapsed Cricket Club').click()
  await page.waitForURL(`**/preview/${PAUSED_TOKEN}`)
  ck('with a season page, it opens that page (what someone coming back should see), not the paused club site',
     new URL(page.url()).pathname === `/preview/${PAUSED_TOKEN}`)
  ck('after one lookup with that club\'s ids', lookups.length === 1 && lookups[0].includes('CA-PAUSED'), JSON.stringify(lookups))
  await page.waitForSelector('[data-testid="teaser-page"]')
  ck('and that page is not a redirect to the club site (no registered notice)', await page.locator('[data-testid="teaser-registered"]').count() === 0)
  await ctx.close()
})

await section('a club whose trial has ended and has no season page', async () => {
  const { page, ctx, lookups } = await open()
  await row(page, 'Lapsed No Page Cricket Club').click()
  await page.waitForSelector('[data-testid="trial-extension-form"]')
  ck('it gets the extension request, as before (not the set-up choice, not the paused site)',
     await page.locator('[data-testid="trial-not-yet-heading"]').count() === 0 && new URL(page.url()).pathname === '/trial')
  ck('after a lookup that found nothing', lookups.length === 1 && lookups[0].includes('CA-PAUSED2'), JSON.stringify(lookups))
  await ctx.close()
})

await section('a club whose trial has ended and the lookup fails', async () => {
  const { page, ctx } = await open({ byClub: 'error' })
  await row(page, 'Lapsed Cricket Club').click()
  await page.waitForSelector('[data-testid="trial-extension-form"]')
  ck('the visitor still gets the extension request', new URL(page.url()).pathname === '/trial')
  await ctx.close()
})

await section('claiming from a lapsed club\'s page', async () => {
  const { page, ctx } = await open({ path: `/trial?teaser=${PAUSED_TOKEN}` })
  await page.waitForSelector('[data-testid="trial-extension-form"]')
  ck('asks for more trial time (the club has had its trial), rather than opening the paused club site or a new wizard',
     new URL(page.url()).pathname === '/trial' && await page.locator('[data-testid="trial-extension-form"]').count() === 1)
  await ctx.close()
})

await section('phone width', async () => {
  const { page, ctx } = await open({ delay: 900, width: 390 })
  await row(page, 'Renmark North Cricket Club').click()
  await page.waitForTimeout(250)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('the results do not overflow at 390px while opening', over <= 0, String(over))
  await ctx.close()
})

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
