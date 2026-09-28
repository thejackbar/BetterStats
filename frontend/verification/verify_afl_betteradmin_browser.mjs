// BetterAdmin in the football app, driven in Chromium against a real football
// backend (uvicorn app.afl_main) and the football production build
// (VITE_SPORT=afl VITE_BASE=/afl/, served by vite preview).
//
// For every BetterAdmin screen: it renders, the shared module sidebar is there
// with football's module switcher (no cricket tiles), no page error, no API
// call answers 5xx, and nothing overflows a 390px phone.
//
// Run:  node verification/verify_afl_betteradmin_browser.mjs http://localhost:4311/afl
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:4311/afl'
let pass = 0, fail = 0
const check = (label, ok, detail = '') => {
  if (ok) { pass++; console.log(`  ok   ${label}`) } else { fail++; console.log(`  FAIL ${label} ${detail}`) }
}

const SCREENS = [
  ['/admin/clubhouse', 'Today'],
  ['/admin/clubhouse/directory', 'Directory'],
  ['/admin/clubhouse/roster', 'Roster'],
  ['/admin/committee', 'Committee'],
  ['/admin/clubhouse/role-programs', 'Role programs'],
  ['/admin/fees', 'Accounts'],
  ['/admin/fees/payments', 'Payments'],
  ['/admin/fees/schedule', 'Membership tiers'],
  ['/admin/merch/stock', 'Inventory'],
  ['/admin/comms', 'Emails'],
  ['/admin/comms/segments', 'Segments'],
  ['/admin/comms/templates', 'Templates'],
  ['/admin/comms/settings', 'Email settings'],
  ['/admin/club-diary', 'Diary'],
  ['/admin/events', 'Events'],
  ['/admin/assets', 'Facilities'],
  ['/admin/clubhouse/areas-roles', 'Areas'],
  ['/admin/clubhouse/integrations', 'Integrations'],
  ['/admin/clubhouse/reports', 'Reports'],
  ['/admin/clubhouse/settings', 'Settings'],
  ['/admin/families', 'Families'],
]

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }).catch(() => chromium.launch())
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } })
const page = await ctx.newPage()
const errors = [], bad = []
page.on('pageerror', e => errors.push(String(e)))
page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 500) bad.push(`${r.status()} ${r.url()}`) })

await page.goto(`${BASE}/login`)
await page.locator('form input:not([type=password])').first().fill('coach')
await page.fill('input[type="password"]', 'pass1234')
await page.keyboard.press('Enter')
await page.waitForURL(/\/admin/, { timeout: 15000 })

console.log('\n── The football admin sidebar offers the modules ──')
await page.goto(`${BASE}/admin`)
await page.waitForTimeout(1500)
const sideText = await page.locator('aside').first().innerText().catch(() => '')
check('BetterAdmin is in the football sidebar', /BetterAdmin/.test(sideText))
check('BetterSocials is in the football sidebar', /BetterSocials/.test(sideText))
check('Matches, Milestones and Activity Log are in the sidebar',
  /Matches/.test(sideText) && /Milestones/.test(sideText) && /Activity Log/i.test(sideText))

for (const [path, name] of SCREENS) {
  console.log(`\n── ${name} (${path}) ──`)
  const before = errors.length, beforeBad = bad.length
  await page.goto(`${BASE}${path}`)
  await page.waitForTimeout(2200)
  const url = page.url()
  check(`${name}: stays on its own URL (not bounced)`, url.includes(path), url)
  const body = await page.locator('body').innerText().catch(() => '')
  check(`${name}: renders content`, body.trim().length > 50)
  check(`${name}: no "Something went wrong"`, !/Something went wrong/i.test(body))
  const aside = await page.locator('aside').first().innerText().catch(() => '')
  check(`${name}: football module switcher, not cricket's`, /Football/.test(aside) && !/Select|Fantasy|IQ\b/.test(aside), aside.slice(-200).replace(/\n/g, ' | '))
  check(`${name}: no page errors`, errors.length === before, errors.slice(before).join(' / ').slice(0, 300))
  check(`${name}: no 5xx API calls`, bad.length === beforeBad, bad.slice(beforeBad).join(' / '))
}

console.log('\n── Mobile width ──')
await page.setViewportSize({ width: 390, height: 844 })
for (const path of ['/admin/clubhouse', '/admin/clubhouse/directory', '/admin/fees']) {
  await page.goto(`${BASE}${path}`)
  await page.waitForTimeout(1500)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check(`${path}: no horizontal overflow at 390px`, over <= 0, `${over}px`)
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
