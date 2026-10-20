// Football BetterSelect wears cricket's module chrome, driven in Chromium against
// a real football backend (seeded by backend/verification/seed_afl_select_browser.py,
// with the club holding every football module) and the football production build.
//
// What it proves: BetterSelect is its own module surface on cricket's
// /admin/betterselect URLs (module-branded sidebar with the lockup, grouped nav
// with icons, module switcher, an Overview with the hero and the tool groups), the
// old /admin/select links still land, each screen's actions sit in the header, and
// nothing overflows at 390px.
//
// Run:  node verification/verify_afl_select_layout_browser.mjs http://localhost:4311/afl [shotsDir]
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:4311/afl'
const SHOTS = process.argv[3] || ''
let pass = 0, fail = 0
const check = (label, ok, detail = '') => {
  if (ok) { pass++; console.log(`  ok   ${label}`) } else { fail++; console.log(`  FAIL ${label} ${detail}`) }
}
const count = (loc) => loc.count().catch(() => 0)
// A click on something absent is reported by the checks after it, not thrown, so
// a control run against the previous build finishes and says what is missing.
async function press(loc) { if (!(await count(loc))) return false; await loc.first().click().catch(() => {}); return true }
const textOf = async (loc) => (await count(loc)) ? (await loc.first().innerText().catch(() => '')) : ''
const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` }).catch(() => {}) }

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }).catch(() => chromium.launch())
const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } })
const page = await ctx.newPage()
page.setDefaultTimeout(5000)
const errors = [], bad = []
page.on('pageerror', e => errors.push(String(e)))
page.on('dialog', d => d.accept())
page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 500) bad.push(`${r.status()} ${r.url()}`) })

await page.goto(`${BASE}/login`)
await page.locator('form input:not([type=password])').first().fill('coach')
await page.fill('input[type="password"]', 'pass1234')
await page.keyboard.press('Enter')
await page.waitForURL(/\/admin/, { timeout: 15000 })

const aside = page.locator('aside').first()
const header = page.locator('header').first()
const go = async (path) => { await page.goto(`${BASE}${path}`); await page.waitForTimeout(1800) }

console.log('\n── The football admin menu ──')
await go('/admin')
const adminNav = await textOf(page.locator('aside nav'))
check('BetterSelect is a module entry in the menu', /BetterSelect/.test(adminNav))
check('  ... and the old inline Selection section is gone', !/Selection rules/i.test(adminNav))
const entry = page.locator('aside nav a', { hasText: 'BetterSelect' }).first()
await press(entry); await page.waitForTimeout(1800)
check('  ... opening it lands on the module Overview', /\/admin\/betterselect\/?$/.test(page.url()), page.url())

console.log('\n── The module chrome ──')
const side = await textOf(aside)
check('the sidebar carries the BetterSelect lockup', /BetterSelect/.test(side))
check('  ... a way back to admin', /Back to admin/.test(side))
for (const h of ['Your Squad', 'Match Day', 'Setup']) check(`  ... the heading ${h}`, new RegExp(h, 'i').test(side))
for (const l of ['Overview', 'Squads', 'Fixtures', 'Availability', 'Selection', 'Selection rules']) {
  check(`  ... the tool ${l}`, (await count(page.locator('aside nav a', { hasText: new RegExp(`^\\s*${l}\\s*$`) }))) === 1)
}
check('  ... each with an icon', (await count(page.locator('aside nav a svg'))) === 6, String(await count(page.locator('aside nav a svg'))))
check('  ... and none of cricket-only Players, Nets, Votes or Ladders', !/Players|Nets|Votes|Ladders/.test(side))
const accent = await page.evaluate(() => getComputedStyle(document.querySelector('aside').parentElement).getPropertyValue('--pb-accent').trim())
check('the module wears its own brand colour', accent.toLowerCase() === '#3b82f6', accent)
const pills = await textOf(header)
for (const p of ['Football', 'Select', 'Socials', 'Admin']) check(`the module switcher offers ${p}`, new RegExp(p).test(pills), pills)
check('  ... and no bookmark star (the football app has none)', (await count(page.locator('header [aria-label*="ookmark"], header [title*="ookmark"]'))) === 0)

console.log('\n── The Overview ──')
check('the hero names the module', /BetterSelect/.test(await textOf(page.locator('main'))))
// CSS uppercase makes innerText uppercase, so the casing is the rendered one.
check('the next game is called out', /NEXT TO PICK|THIS WEEKEND/.test(await textOf(page.locator('main'))))
check('  ... with the round written once', !/ROUND\s+ROUND/.test(await textOf(page.locator('main'))))
check('  ... with a button to pick it', (await count(page.getByRole('button', { name: 'Pick this side' }))) > 0)
check('upcoming fixtures and needs-attention cards are drawn', /Needs attention/.test(await textOf(page.locator('main'))) && /Upcoming fixtures/.test(await textOf(page.locator('main'))))
for (const g of ['Your Squad', 'Match Day', 'Setup']) check(`a tool group card for ${g}`, (await count(page.locator('main a', { hasText: g }))) > 0)
await shot(page, 'overview-desktop')

await press(page.locator('main a', { hasText: 'Match Day' })); await page.waitForTimeout(800)
check('a group card opens that group page', /betterselect\/matchday$/.test(page.url()), page.url())
const grp = await textOf(page.locator('main'))
check('  ... listing its three tools', ['Fixtures', 'Availability', 'Selection'].every(t => grp.includes(t)))
check('  ... with a way back to the Overview', /Overview/.test(grp))
await press(page.locator('main a', { hasText: 'Availability' })); await page.waitForTimeout(1500)
check('  ... and a tool card opens the tool', /betterselect\/availability$/.test(page.url()), page.url())

console.log('\n── Each screen inside the chrome ──')
const SCREENS = [['squads', 'Squads'], ['fixtures', 'Fixtures'], ['availability', 'Availability'], ['selection', 'Selection'], ['rules', 'Selection rules']]
for (const [slug, title] of SCREENS) {
  await go(`/admin/betterselect/${slug}`)
  const h1 = await textOf(header.locator('h1'))
  check(`${slug}: the header title is ${title}`, h1.trim() === title, h1)
  const active = await page.locator('aside nav a', { hasText: new RegExp(`^\\s*${title}\\s*$`) }).first().getAttribute('class').catch(() => '')
  check(`  ... and that sidebar item is highlighted`, /border-pb-accent/.test(active || ''), active)
  check(`  ... and the screen drew (no spinner left)`, (await count(page.locator('main'))) > 0 && !/Loading/.test(await textOf(page.locator('main'))))
  await shot(page, `${slug}-desktop`)
}
await go('/admin/betterselect/fixtures')
check('Fixtures: its actions are in the header', (await count(header.getByRole('button', { name: 'Update from PlayHQ' }))) === 1 && (await count(header.getByRole('button', { name: 'Add a game' }))) === 1)
check('  ... not repeated down the page', (await count(page.locator('main').getByRole('button', { name: 'Update from PlayHQ' }))) === 0)
check('  ... and the caption stays on the page as its intro', /PlayHQ's draw/.test(await textOf(page.locator('main'))))
await go('/admin/betterselect/squads')
check('Squads: its actions are in the header', (await count(header.getByRole('button', { name: 'Add sides from PlayHQ' }))) === 1)
await go('/admin/betterselect/selection')
check('Selection: the board still opens on the next fixture', /fixture=/.test(page.url()), page.url())
check('  ... eighteen positions on the ground', (await count(page.locator('[data-slot]'))) === 18)
check('  ... the fixture picker is in the header', (await count(header.locator('select[aria-label="Fixture"]'))) === 1)
await go('/admin/betterselect/rules')
check('Rules: the rule picker is in the header', (await count(header.locator('select[aria-label="New rule"]'))) === 1)

console.log('\n── Old links still land ──')
await go('/admin/select/fixtures')
check('/admin/select/fixtures lands on the new Fixtures', /betterselect\/fixtures$/.test(page.url()), page.url())
await go('/admin/select')
check('/admin/select lands on the Overview', /betterselect\/?$/.test(page.url()), page.url())
await go('/admin/select/selection?fixture=abc')
check('  ... and keeps the query on a saved Selection link', /betterselect\/selection\?fixture=/.test(page.url()), page.url())

console.log('\n── Gating ──')
const r = await page.evaluate(async () => {
  const x = await fetch(`${location.origin}/afl/api/club-admin/super/clubs`, { credentials: 'include' })
  return x.status
})
check('the club admin is not a super admin (sanity)', r === 403 || r === 401, String(r))

console.log('\n── Phone width: nothing overflows ──')
const phone = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage()
phone.setDefaultTimeout(5000)
await phone.goto(`${BASE}/login`)
await phone.locator('form input:not([type=password])').first().fill('coach')
await phone.fill('input[type="password"]', 'pass1234')
await phone.keyboard.press('Enter')
await phone.waitForURL(/\/admin/, { timeout: 15000 })
for (const s of ['', 'squads', 'fixtures', 'availability', 'selection', 'rules', 'matchday']) {
  await phone.goto(`${BASE}/admin/betterselect${s ? '/' + s : ''}`); await phone.waitForTimeout(1800)
  const w = await phone.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }))
  check(`${s || 'overview'}: no horizontal page scroll at 390px`, w.sw <= w.cw + 1, JSON.stringify(w))
  await shot(phone, `${s || 'overview'}-phone`)
}

console.log('\n── No errors ──')
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
check('no 5xx from the API', bad.length === 0, bad.slice(0, 3).join(' | '))

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
