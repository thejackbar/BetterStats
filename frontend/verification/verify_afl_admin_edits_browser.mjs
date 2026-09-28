// Football admin: the club logo upload on Settings, editing a club user, and
// editing a sponsor. Driven in Chromium against a real football backend and
// the football production build.
//
// Run:  node verification/verify_afl_admin_edits_browser.mjs http://localhost:4311/afl
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:4311/afl'
let pass = 0, fail = 0
const check = (label, ok, detail = '') => {
  if (ok) { pass++; console.log(`  ok   ${label}`) } else { fail++; console.log(`  FAIL ${label} ${detail}`) }
}
const count = (loc) => loc.count().catch(() => 0)
async function press(loc) { if (!(await count(loc))) return false; await loc.first().click().catch(() => {}); return true }
import zlib from 'node:zlib'
// A real 200x200 PNG: the crop editor needs something to crop.
function makePng(n = 200) {
  const crc = (buf) => { let c = ~0; for (const b of buf) { c ^= b; for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xEDB88320 & -(c & 1)) } return ~c >>> 0 }
  const chunk = (type, data) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length)
    const td = Buffer.concat([Buffer.from(type), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td))
    return Buffer.concat([len, td, c])
  }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(n, 0); ihdr.writeUInt32BE(n, 4); ihdr[8] = 8; ihdr[9] = 2
  const raw = Buffer.alloc((n * 3 + 1) * n)
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) { const o = y * (n * 3 + 1) + 1 + x * 3; raw[o] = 200; raw[o + 1] = 30 + (x % 200); raw[o + 2] = 60 }
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))])
}
const PNG = makePng()

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }).catch(() => chromium.launch())
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage()
const errors = [], bad = [], writes = []
page.on('pageerror', e => errors.push(String(e)))
page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 500) bad.push(`${r.status()} ${r.url()}`) })
page.on('request', r => { if (['PATCH', 'POST', 'DELETE'].includes(r.method()) && r.url().includes('/api/club-admin/')) writes.push({ m: r.method(), u: r.url(), b: r.postData() }) })

await page.goto(`${BASE}/login`)
await page.locator('form input:not([type=password])').first().fill('coach')
await page.fill('input[type="password"]', 'pass1234')
await page.keyboard.press('Enter')
await page.waitForURL(/\/admin/, { timeout: 15000 })

console.log('\n── Club logo ──')
await page.goto(`${BASE}/admin/settings`); await page.waitForTimeout(1500)
const field = page.getByTestId('logo-field')
check('Settings has a club logo section', (await count(field)) > 0)
if (await count(page.getByTestId('logo-input'))) {
  await page.getByTestId('logo-input').setInputFiles({ name: 'crest.png', mimeType: 'image/png', buffer: PNG })
  await page.waitForTimeout(1500)
  await page.waitForTimeout(1000)
  await press(page.getByRole('button', { name: 'Apply', exact: true }))
  await page.waitForTimeout(2500)
}
const up = writes.find(w => w.m === 'POST' && w.u.endsWith('/club-admin/logo'))
check('the logo goes to the football logo endpoint', !!up)
const src = await field.locator('img').first().getAttribute('src').catch(() => null)
check('the crest shows, under the football API base', !!src && src.includes('/afl/api/images/organisations/'), src || '')
const loaded = src ? await field.locator('img').first().evaluate(i => i.complete && i.naturalWidth > 0).catch(() => false) : false
check('  ... and actually loads', loaded)
check('it can be removed', await press(field.getByRole('button', { name: 'Remove' })))
await page.waitForTimeout(1200)
check('  ... with a DELETE to the logo endpoint', writes.some(w => w.m === 'DELETE' && w.u.endsWith('/club-admin/logo')))

console.log('\n── Editing a club user ──')
await page.goto(`${BASE}/admin/users`); await page.waitForTimeout(1500)
check('each user has an Edit action', await press(page.getByRole('button', { name: 'Edit' })))
const row = page.getByTestId('user-edit-row')
check('the edit row opens', (await count(row)) > 0)
if (await count(row)) {
  await row.getByLabel('Mobile').fill(`0412 ${String(Date.now()).slice(-6, -3)} ${String(Date.now()).slice(-3)}`)
  await press(row.getByRole('button', { name: 'Save' }))
  await page.waitForTimeout(1500)
}
const up2 = writes.find(w => w.m === 'PATCH' && /\/club-admin\/users\//.test(w.u))
let body2 = {}; try { body2 = JSON.parse(up2?.b || '{}') } catch {}
check('only the changed field is sent', JSON.stringify(Object.keys(body2)) === '["mobile_number"]', up2?.b || '')
check('the row closes after saving', (await count(row)) === 0)

// Unique per run, so a sponsor a previous (or control) run left behind cannot
// answer for this one.
const RUN = String(Date.now()).slice(-6)
const OLD = `Old Name ${RUN}`, NEW = `New Name ${RUN}`
console.log('\n── Editing a sponsor ──')
await page.goto(`${BASE}/admin/sponsors`); await page.waitForTimeout(1500)
await page.getByPlaceholder('Sponsor name').fill(OLD)
await press(page.getByRole('button', { name: 'Add sponsor' }))
await page.waitForTimeout(1500)
const card = page.locator('.pb-card', { hasText: OLD })
await press(card.getByRole('button', { name: 'Edit' }))
const ed = page.getByTestId('sponsor-edit')
check('a sponsor can be edited', (await count(ed)) > 0)
if (await count(ed)) {
  await ed.getByLabel('Sponsor name').fill(NEW)
  await ed.getByLabel('Website URL').fill('https://example.com')
  await press(ed.getByRole('button', { name: 'Save' }))
  await page.waitForTimeout(1500)
}
const txt = await page.locator('body').innerText()
check('the new name is saved', txt.includes(NEW) && !txt.includes(OLD))
check('  ... with its website', /example\.com/.test(txt))
const card2 = page.locator('.pb-card', { hasText: NEW })
if (await count(card2.locator('input[type=file]'))) {
  await card2.locator('input[type=file]').setInputFiles({ name: 'l.png', mimeType: 'image/png', buffer: PNG })
  await page.waitForTimeout(1500)
}
const sImg = card2.locator('img').first()
const sOk = (await count(sImg)) ? await sImg.evaluate(i => i.complete && i.naturalWidth > 0).catch(() => false) : false
check('the sponsor logo loads under /afl', sOk, (await sImg.getAttribute('src').catch(() => '')) || 'no img')
check('its logo can be removed', await press(card2.getByRole('button', { name: 'Remove logo' })))
await page.waitForTimeout(1000)
page.once('dialog', d => d.accept())
await press(page.locator('.pb-card', { hasText: NEW }).getByRole('button', { name: 'Remove', exact: true }))
await page.waitForTimeout(1000)

console.log('\n── Health ──')
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
check('no API call answered 5xx', bad.length === 0, bad.slice(0, 3).join(' | '))
for (const path of ['/admin/settings', '/admin/users', '/admin/sponsors']) {
  await page.setViewportSize({ width: 390, height: 800 })
  await page.goto(`${BASE}${path}`); await page.waitForTimeout(1200)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check(`no horizontal overflow at 390px on ${path}`, over <= 1, `${over}px`)
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
