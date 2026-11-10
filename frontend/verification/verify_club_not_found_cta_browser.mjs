// A club page we cannot find (a new club, or one whose free trial ended) sends the
// visitor straight to registration with their club already searched.
//
//   npx vite --port 5204 &
//   node frontend/verification/verify_club_not_found_cta_browser.mjs [baseUrl]
//
// Measured: the "Not on BetterCricket yet" page shows for a 404 club, its button goes
// to /trial?club=<name>, /trial opens with that name in the search box and sends that
// exact search on the wire, a bare /trial starts empty (so the prefill is not always
// on), a switched-off club (403) still reads "paused" and still goes to /contact, and
// 390px has no sideways scroll.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
async function section(name, fn) {
  try { await fn() } catch (e) { fail++; console.log(`FAIL ${name} did not complete  ${String(e.message || e).split('\n')[0].slice(0, 140)}`) }
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(width = 1300) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const searches = []
  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url())
    const p = u.pathname.replace(/^\/api/, '')
    const json = (b, code = 200) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(p)) return json({ detail: 'no' }, 401)
    if (/^\/clubs\/high-wycombe/.test(p)) return json({ detail: 'Club not found' }, 404)
    if (/^\/clubs\/switched-off/.test(p)) return json({ detail: 'This club page is currently not available. Contact your club executives to get access.' }, 403)
    if (/public\/self-serve\/status/.test(p)) return json({ enabled: true, default_trial_days: 14 })
    if (/public\/self-serve\/search/.test(p)) {
      searches.push(u.searchParams.get('q'))
      return json([{ id: 'CA-HW', playHQId: 'PH-HW', name: 'High Wycombe Cricket Club', already_registered: false }])
    }
    return json({})
  })
  return { page, ctx, searches }
}

await section('404 club', async () => {
  const { page, ctx, searches } = await open()
  await page.goto(`${BASE}/high-wycombe`)
  await page.getByText('Not on BetterCricket yet').first().waitFor()
  ck('404 club shows "Not on BetterCricket yet"', true)
  const cta = page.locator('a.cta-primary')
  const href = await cta.getAttribute('href')
  ck('button goes to /trial with the club name', href === '/trial?club=High%20Wycombe', String(href))
  await cta.click()
  await page.waitForURL(/\/trial\?club=High%20Wycombe/)
  const box = page.getByLabel('Search for your club')
  await box.waitFor()
  ck('/trial opens with the club name in the search box', (await box.inputValue()) === 'High Wycombe', await box.inputValue())
  await page.waitForFunction(() => document.body.innerText.includes('High Wycombe Cricket Club'))
  for (let i = 0; i < 50 && !searches.length; i++) await page.waitForTimeout(100)
  ck('the search that went out is exactly that name, once', searches.length === 1 && searches[0] === 'High Wycombe', JSON.stringify(searches))
  await ctx.close()
})

await section('bare /trial', async () => {
  const { page, ctx, searches } = await open()
  await page.goto(`${BASE}/trial`)
  const box = page.getByLabel('Search for your club')
  await box.waitFor()
  ck('control: a bare /trial starts with an empty search and sends none', (await box.inputValue()) === '' && searches.length === 0, JSON.stringify(searches))
  await ctx.close()
})

await section('switched-off club', async () => {
  const { page, ctx } = await open()
  await page.goto(`${BASE}/switched-off`)
  await page.getByText('Club page paused', { exact: false }).first().waitFor()
  ck('403 club still reads paused', true)
  const href = await page.locator('a.cta-primary').getAttribute('href')
  ck('and still asks them to get in touch (/contact)', href === '/contact?club=Switched%20Off', String(href))
  await ctx.close()
})

await section('390px', async () => {
  const { page, ctx } = await open(390)
  await page.goto(`${BASE}/high-wycombe`)
  await page.getByText('Not on BetterCricket yet').first().waitFor()
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no sideways scroll on the not-found page', over <= 0, `overflow ${over}px`)
  await page.goto(`${BASE}/trial?club=High%20Wycombe`)
  await page.getByLabel('Search for your club').waitFor()
  const over2 = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no sideways scroll on /trial with a prefilled search', over2 <= 0, `overflow ${over2}px`)
  await ctx.close()
})

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
