// Football BetterSelect, driven in Chromium against a real football backend
// (seeded by backend/verification/seed_afl_select_browser.py) and the football
// production build: the field board, bench and emergencies, the rules refusing
// a side, fixtures, availability and the player's own link, squads and rules.
//
// Run:  node verification/verify_afl_select_browser.mjs http://localhost:4311/afl
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:4311/afl'
let pass = 0, fail = 0
const check = (label, ok, detail = '') => {
  if (ok) { pass++; console.log(`  ok   ${label}`) } else { fail++; console.log(`  FAIL ${label} ${detail}`) }
}
const count = (loc) => loc.count().catch(() => 0)
async function press(loc) { if (!(await count(loc))) return false; await loc.first().click().catch(() => {}); return true }
const textOf = async (loc) => (await count(loc)) ? (await loc.first().innerText().catch(() => '')) : ''

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }).catch(() => chromium.launch())
const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } })
await ctx.grantPermissions(['clipboard-read', 'clipboard-write'])
const page = await ctx.newPage()
// A short wait: an absent element is reported, and a control run against a
// build without these screens finishes rather than waiting 30s per locator.
page.setDefaultTimeout(5000)
const errors = [], bad = [], writes = []
page.on('pageerror', e => errors.push(String(e)))
page.on('dialog', d => d.accept())
page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 500) bad.push(`${r.status()} ${r.url()}`) })
page.on('request', r => {
  if (['PATCH', 'POST', 'PUT', 'DELETE'].includes(r.method()) && r.url().includes('/afl-select/'))
    writes.push({ m: r.method(), u: r.url(), b: r.postData() })
})
const body = (w) => { try { return JSON.parse(w?.b || '{}') } catch { return {} } }
const last = (m, re) => [...writes].reverse().find(w => w.m === m && re.test(w.u))

await page.goto(`${BASE}/login`)
await page.locator('form input:not([type=password])').first().fill('coach')
await page.fill('input[type="password"]', 'pass1234')
await page.keyboard.press('Enter')
await page.waitForURL(/\/admin/, { timeout: 15000 })
const api = (path, opts = {}) => page.evaluate(async ([p, o]) => {
  const r = await fetch(`${location.origin}/afl/api${p}`, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...o })
  return { status: r.status, json: await r.json().catch(() => null) }
}, [path, opts])

console.log('\n── The menu ──')
check('BetterSelect is in the football admin menu', (await count(page.getByRole('link', { name: 'BetterSelect', exact: true }))) > 0)

console.log('\n── The ground ──')
await page.goto(`${BASE}/admin/betterselect/selection`); await page.waitForTimeout(2500)
check('the board opens on the next fixture', /fixture=/.test(page.url()))
check('eighteen positions on the ground', (await count(page.locator('[data-slot]'))) === 18, String(await count(page.locator('[data-slot]'))))
for (const s of ['FB', 'CHB', 'C', 'CHF', 'FF', 'RUCK', 'RR', 'ROV']) {
  check(`  ... including ${s}`, (await count(page.getByTestId(`slot-${s}`))) === 1)
}
check('a player is listed with their football position', (await textOf(page.getByTestId('pool-player'))).includes('FB'))
check('  ... and no batting or bowling anywhere', !/batting|bowling|wicket|innings/i.test(await page.locator('main').innerText().catch(() => '')))

// Tap a player, then a spot.
const pool = page.getByTestId('pool-player')
await press(pool.nth(0))
check('tapping a player puts them in hand', (await count(page.getByTestId('in-hand'))) > 0)
await press(page.getByTestId('slot-FB'))
check('  ... and tapping a spot puts them there', (await textOf(page.getByTestId('slot-FB'))).includes('Player01'))
// Fill the ground: 18 more taps.
const order = ['LBP', 'RBP', 'LHB', 'CHB', 'RHB', 'LW', 'C', 'RW', 'LHF', 'CHF', 'RHF', 'LFP', 'FF', 'RFP', 'RUCK', 'RR', 'ROV']
for (let i = 0; i < order.length; i++) {
  await press(page.getByTestId('pool-player').filter({ hasText: `Player${String(i + 2).padStart(2, '0')}` }))
  await press(page.getByTestId(`slot-${order[i]}`))
}
check('eighteen on the ground', (await textOf(page.getByTestId('counts'))).startsWith('18/18'), await textOf(page.getByTestId('counts')))
// The ruck as captain.
await press(page.getByTestId('slot-RUCK'))
await press(page.getByRole('button', { name: 'Captain', exact: true }))
await press(page.getByRole('button', { name: 'Cancel' }))
check('the captain is marked on the ground', (await textOf(page.getByTestId('slot-RUCK'))).includes('(c)'))
for (const n of ['19', '20']) {
  await press(page.getByTestId('pool-player').filter({ hasText: `Player${n}` }))
  await press(page.getByRole('button', { name: 'Put on the bench' }))
}
await press(page.getByTestId('pool-player').filter({ hasText: 'Player21' }))
await press(page.getByRole('button', { name: 'Make emergency' }))
check('two on the bench', (await count(page.getByTestId('bench-row'))) === 2)
check('one emergency', (await count(page.getByTestId('emg-row'))) === 1)

// Moving a player swaps them with whoever is there.
await press(page.getByTestId('slot-FB'))
await press(page.getByTestId('slot-FF'))
check('moving the full back to full forward swaps the two', (await textOf(page.getByTestId('slot-FF'))).includes('Player01')
  && (await textOf(page.getByTestId('slot-FB'))).includes('Player14'))

await press(page.getByRole('button', { name: 'Save side' }))
await page.waitForTimeout(1500)
const put = last('PUT', /\/lineup$/)
const items = body(put).items || []
check('the save sends the whole side', items.length === 21, String(items.length))
check('  ... each at their football position', items.some(x => x.slot === 'FF') && items.some(x => x.slot === 'RUCK'))
check('  ... the captain', items.filter(x => x.is_captain).map(x => x.slot).join() === 'RUCK')
check('  ... the bench as INT and the emergency as EMG', items.filter(x => x.slot === 'INT').length === 2 && items.filter(x => x.slot === 'EMG').length === 1)
check('the button reads saved', (await textOf(page.getByRole('button', { name: /Saved/ }))).length > 0)

// The team sheet the way a football club writes it.
await press(page.getByRole('button', { name: 'Copy team sheet' }))
await page.waitForTimeout(800)
const sheet = await page.evaluate(() => navigator.clipboard.readText()).catch(() => '')
check('the team sheet is in football lines', ['\nB: ', '\nHB: ', '\nC: ', '\nHF: ', '\nF: ', '\nFoll: ', '\nI/C: ', '\nEmg: '].every(k => sheet.includes(k)), JSON.stringify(sheet.slice(0, 80)))

console.log('\n── A rule the club enforces ──')
const rules = await api('/afl-select/rules/starter', { method: 'POST' })
check('the usual two rules go in', rules.status === 200)
const rl = await api('/afl-select/rules')
const con = (rl.json?.rules || []).find(r => r.kind === 'concussion')
const sel = await api(`/afl-select/fixtures/${new URL(page.url()).searchParams.get('fixture')}/selection`)
const ruck = (sel.json?.players || []).find(p => p.name.includes('Player16'))
if (con && ruck) {
  const d = new Date(); d.setDate(d.getDate() - 3)
  await api(`/afl-select/rules/${con.id}/players`, { method: 'POST', body: JSON.stringify({ player_id: ruck.id, mode: 'incident', incident_date: d.toISOString().slice(0, 10) }) })
}
await page.reload(); await page.waitForTimeout(2500)
check('the concussed player is flagged on the ground', (await page.getByTestId('slot-RUCK').getAttribute('style').catch(() => '') || '').includes('red'))
check('  ... and the rule is spelled out', (await textOf(page.getByTestId('rules-strip'))).includes('Concussed'))
// Any change makes the side savable again; the server refuses it.
await press(page.getByTestId('bench-row').first().getByRole('button', { name: /Take/ }))
await press(page.getByRole('button', { name: 'Save side' }))
await page.waitForTimeout(1500)
check('the save is refused with the reason', (await textOf(page.getByTestId('save-errors'))).includes('Player16'))

console.log('\n── Fixtures ──')
await page.goto(`${BASE}/admin/betterselect/fixtures`); await page.waitForTimeout(2000)
check('the PlayHQ draw is listed', (await count(page.getByTestId('fixture-row'))) >= 3, String(await count(page.getByTestId('fixture-row'))))
check('a named side shows its count', (await textOf(page.getByTestId('fixture-row').first())).includes('named'))
check('each fixture has a way to pick its side', (await count(page.getByRole('link', { name: /Pick side|Edit side/ }))) >= 3)
await press(page.getByRole('button', { name: 'Add a game' }))
const ff = page.getByTestId('fixture-form')
await ff.getByPlaceholder('Opponent').fill('Trial match').catch(() => {})
await ff.getByLabel('Date').fill('2026-12-05').catch(() => {})
await press(ff.getByRole('button', { name: 'Add game' }))
await page.waitForTimeout(1200)
const fw = last('POST', /\/afl-select\/fixtures$/)
check('adding a game sends its opponent and date', body(fw).opponent_name === 'Trial match' && body(fw).played_on === '2026-12-05', fw?.b || '')

console.log('\n── Availability ──')
await page.goto(`${BASE}/admin/betterselect/availability`); await page.waitForTimeout(2000)
check('the matrix shows the match dates', (await count(page.locator('[data-testid=avail-matrix] thead th'))) >= 3)
await press(page.getByTestId('avail-cell'))
await page.waitForTimeout(800)
const aw = last('POST', /\/afl-select\/availability$/)
check('a tap records Available for that date', body(aw).status === 'AVAILABLE' && /\d{4}-\d\d-\d\d/.test(body(aw).date || ''), aw?.b || '')
await press(page.getByRole('button', { name: 'Turn the link on' }))
await page.waitForTimeout(1500)
const link = await textOf(page.getByTestId('self-link'))
check('turning the link on shows it', link.includes('/afl/avail/'), link)
check('  ... with a QR code', (await count(page.getByAltText(/QR code/))) > 0)
if (link) {
  const anon = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage()
  const aerr = []; anon.on('pageerror', e => aerr.push(String(e)))
  await anon.goto(link); await anon.waitForTimeout(2500)
  check("the player's link opens under the football site", (await textOf(anon.locator('body'))).includes('Player01'))
  check('  ... with no page errors', aerr.length === 0, aerr.join('|'))
}

console.log('\n── Squads ──')
await page.goto(`${BASE}/admin/betterselect/squads`); await page.waitForTimeout(2000)
check('two sides, seniors first', (await textOf(page.getByTestId('side-row').first())).includes('Seniors'))
const sel2 = page.getByLabel(/Squad for Senior, Player26/)
await sel2.selectOption({ label: 'Curtin Uni Wesley Reserves' }).catch(() => {})
await page.waitForTimeout(800)
const sw = last('PUT', /\/afl-select\/squads\//)
check('moving a player sends the side', !!body(sw).team_id, sw?.b || '')
await press(page.getByRole('button', { name: /Move Curtin Uni Wesley Seniors down/ }))
await page.waitForTimeout(800)
const ro = last('POST', /\/teams\/reorder$/)
check('reordering sends every side in the new order', (body(ro).ids || []).length === 2)
await press(page.getByRole('button', { name: /Move Curtin Uni Wesley Reserves down/ }))
await page.waitForTimeout(500)

console.log('\n── Rules ──')
await page.goto(`${BASE}/admin/betterselect/rules`); await page.waitForTimeout(2000)
check('the starter rules are listed', (await count(page.getByTestId('rule-card'))) >= 2)
check("the stand-down reads as AFL's 21 days", (await textOf(page.locator('main'))).includes("21 days' stand-down"))
await page.getByLabel('New rule').selectOption('age').catch(() => {})
await press(page.getByRole('button', { name: 'Add', exact: true }))
await page.waitForTimeout(1200)
check('an age rule can be added', body(last('POST', /\/afl-select\/rules$/)).kind === 'age')
check('no cricket rule kinds are offered', !/bowl|overseas|nets/i.test((await page.getByLabel('New rule').innerText().catch(() => ''))))

console.log('\n── On a phone ──')
const phone = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage()
await phone.goto(`${BASE}/login`)
await phone.locator('form input:not([type=password])').first().fill('coach')
await phone.fill('input[type="password"]', 'pass1234'); await phone.keyboard.press('Enter')
await phone.waitForURL(/\/admin/, { timeout: 15000 })
for (const s of ['selection', 'fixtures', 'availability', 'squads', 'rules']) {
  await phone.goto(`${BASE}/admin/betterselect/${s}`); await phone.waitForTimeout(1800)
  check(`${s}: no sideways scroll at 390px`, await phone.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth))
}

check('no page errors', errors.length === 0, errors.join(' | '))
check('no server errors', bad.length === 0, bad.join(' | '))
await browser.close()
console.log(`\nverify_afl_select_browser: ${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
