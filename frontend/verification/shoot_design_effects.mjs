// Exports each design starter as a real PNG with the test cut-out dropped into
// every empty photo slot. Writes to argv[3] (a folder). Same stubs as
// verify_design_effects_browser.mjs.
//   node verification/shoot_design_effects.mjs http://127.0.0.1:5199 /tmp/out
import { readFileSync, existsSync, copyFileSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'
const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const OUT = process.argv[3] || './shots'
mkdirSync(OUT, { recursive: true })
const PHOTO = readFileSync(new URL('./fixtures/design_fx/photo_red_blue.png', import.meta.url))
const CUTOUT = readFileSync(new URL('./fixtures/design_fx/cutout_player.png', import.meta.url))
const EXE = '/opt/pw-browsers/chromium'
const browser = await chromium.launch(existsSync(EXE) ? { executablePath: EXE } : {})
const json = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
for (const key of ['matchday', 'gameday', 'colourpop']) {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, acceptDownloads: true })
  const page = await ctx.newPage()
  page.on('dialog', (d) => d.accept())
  await page.route('**/api/**', (r) => {
    const u = r.request().url()
    if (/media\/m1\/file/.test(u)) return r.fulfill({ status: 200, contentType: 'image/png', body: PHOTO })
    if (/media\/m2\/file/.test(u)) return r.fulfill({ status: 200, contentType: 'image/png', body: CUTOUT })
    if (/auth\/me/.test(u)) return r.fulfill(json({ id: 'u1', role: 'club_admin', club_slug: 'tcc', entitlements: { modules: ['socials'], status: 'active' } }))
    if (/club-admin\/settings/.test(u)) return r.fulfill(json({ id: 'org-1', name: 'Test Cricket Club', short_name: 'TCC', slug: 'tcc', primary_color: '#0b1530', accent_color: '#ffc233' }))
    if (/social\/media\?kind/.test(u)) return r.fulfill(json([]))
    if (/social\/media/.test(u)) return r.fulfill(json([{ id: 'm1', name: 'photo.png', url: '/api/admin/social/media/m1/file' }, { id: 'm2', name: 'cutout.png', url: '/api/admin/social/media/m2/file' }]))
    if (/templates|players|sponsors/.test(u)) return r.fulfill(json([]))
    return r.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/social-post?type=blank`)
  await page.getByRole('button', { name: /DOWNLOAD PNG/ }).first().waitFor({ timeout: 25000 })
  await page.locator('nav button[title="Layers"]').click()
  for (let i = 0; i < 12; i++) { const d = page.locator('[data-testid="layer-row-block"] button[title="Delete"]'); if (!(await d.count())) break; await d.first().click() }
  await page.locator('nav button[title="Effects"]').click()
  await page.getByTestId(`starter-${key}`).click()
  await page.waitForTimeout(300)
  await page.locator('nav button[title="Layers"]').click()
  const rows = page.locator('[data-testid="layer-row-block"]', { hasText: 'Image (empty)' })
  const n = await rows.count()
  for (let i = 0; i < n; i++) {
    await page.locator('nav button[title="Layers"]').click()
    await page.locator('[data-testid="layer-row-block"]', { hasText: 'Image (empty)' }).first().click()
    await page.locator('nav button[title="Photos"]').click()
    await page.locator(`button[title^="${key === 'colourpop' ? 'photo.png' : 'cutout.png'}"]`).click()
    await page.waitForTimeout(200)
  }
  await page.waitForTimeout(600)
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /DOWNLOAD PNG/ }).first().click()])
  copyFileSync(await dl.path(), `${OUT}/${key}.png`)
  console.log('wrote', `${OUT}/${key}.png`)
  await ctx.close()
}
await browser.close()
