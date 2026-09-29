// BetterSocials (the post designer) in the football app, driven in Chromium
// against a real football backend (uvicorn app.afl_main, seeded with a
// Seniors side, two finished games, best-on-ground rankings and a named team)
// and the football production build (VITE_SPORT=afl VITE_BASE=/afl/).
//
// Run:  node verification/verify_afl_socials_browser.mjs http://localhost:4311/afl
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:4311/afl'
let pass = 0, fail = 0
const check = (label, ok, detail = '') => {
  if (ok) { pass++; console.log(`  ok   ${label}`) } else { fail++; console.log(`  FAIL ${label} ${detail}`) }
}
const text = async (loc) => (await loc.count()) ? loc.first().innerText().catch(() => '') : ''
async function press(page, loc) {
  if (!(await loc.count())) return false
  await loc.first().click().catch(() => {}); return true
}

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }).catch(() => chromium.launch())
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } })
const page = await ctx.newPage()
const errors = [], bad = [], reqs = []
page.on('pageerror', e => errors.push(String(e)))
page.on('response', r => {
  if (!r.url().includes('/api/')) return
  if (r.status() >= 500) bad.push(`${r.status()} ${r.url()}`)
  if (r.status() === 404) bad.push(`404 ${r.url()}`)
})
page.on('request', r => { if (r.url().includes('/api/')) reqs.push(r.url()) })

await page.goto(`${BASE}/login`)
await page.locator('form input:not([type=password])').first().fill('coach')
await page.fill('input[type="password"]', 'pass1234')
await page.keyboard.press('Enter')
await page.waitForURL(/\/admin/, { timeout: 15000 })
const start = () => page.goto(`${BASE}/admin/social-post`).then(() => page.waitForTimeout(2000))

console.log('\n── The start screen offers football posts only ──')
await start()
const body = await text(page.locator('body'))
check('Lineup, Fixtures and Results are offered', /Lineup/.test(body) && /Fixtures/.test(body) && /Results/.test(body))
check('Best on Ground replaces Man of the Match', /Best on Ground/.test(body) && !/Man of the Match/i.test(body))
check('no Toss post', !/\bToss\b/.test(body))
check('no Scorecard post', !/Scorecard/.test(body))
check('no Final Score post', !/Final Score/.test(body))
check('the credit reads BetterFootball, not BetterCricket', !/BetterCricket/.test(body))
check('the account-plan endpoint (cricket only) is never asked for', !reqs.some(u => u.includes('/account/plan')))

console.log('\n── Results pulls this round from the football database ──')
await press(page, page.getByText('Results', { exact: true }))
await page.waitForTimeout(1200)
const pulled = await press(page, page.getByRole('button', { name: 'Pull latest round' }))
await page.waitForTimeout(2500)
const res = await text(page.locator('body'))
check('the pull button is there', pulled)
check('our score written the football way', /12\.8 \(80\)/.test(res))
check('the opposition named without "Football Club"', /RIVALS 6\.4 \(40\)/.test(res) && !/RIVALS FOOTBALL CLUB/.test(res))
check('the margin in points', /BY 40 POINTS/.test(res))
check('no cricket margin left on the post', !/RUNS|WICKETS/.test(res.split('SELECT SOMETHING')[0].split('Round 5')[1] || ''))

console.log('\n── Best on Ground ranks by the votes ──')
await start()
await press(page, page.getByText('Best on Ground', { exact: true }))
await page.waitForTimeout(1200)
const bog0 = await text(page.locator('body'))
check('the post heading says Best on Ground', /BEST ON GROUND/.test(bog0) && !/MAN OF THE MATCH/.test(bog0))
await press(page, page.getByRole('button', { name: 'Fetch' }))
await page.waitForTimeout(2000)
const picked = await press(page, page.getByRole('button', { name: /v Rivals/ }))
await page.waitForTimeout(2500)
check('a recent game can be picked', picked)
const bog = await text(page.locator('body'))
check('the top-voted player is offered first, not the top goal kicker',
  bog.indexOf('Star') > -1 && (bog.indexOf('Two') === -1 || bog.indexOf('Star') < bog.indexOf('Two')), bog.slice(0, 400))
check('the opposition\'s player is never offered', !/Oscar/.test(bog))

console.log('\n── Lineup imports the side named on PlayHQ ──')
await start()
await press(page, page.getByText('Lineup', { exact: true }))
await page.waitForTimeout(2000)
const lu0 = await text(page.locator('body'))
check('the named side is listed', /v Rivals/.test(lu0))
check('no BetterSelect source toggle in football', !/BetterSelect/.test(lu0))
check('the link goes to the football team lists', (await page.getByText(/Team Lists page/).count()) > 0)
await press(page, page.getByRole('button', { name: /v Rivals/ }))
await page.waitForTimeout(2500)
const lu = await text(page.locator('body'))
check('the players land on the post', /STAR/i.test(lu) && /TWO/i.test(lu))

console.log('\n── Health ──')
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
check('no API call answered 404 or 5xx', bad.length === 0, bad.slice(0, 5).join(' | '))

await page.setViewportSize({ width: 390, height: 800 })
await start()
const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
check('no horizontal overflow at 390px', over <= 1, `overflow ${over}px`)

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
