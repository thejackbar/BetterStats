// Captures the real BetterPosts editor (API stubbed) for the BetterPosts brag video.
//
//   cd frontend && npx vite --port 5199 --host 127.0.0.1 &
//   node docs/marketing-videos/betterposts/capture/capture.mjs <outDir>
//
// Writes full-editor screenshots (2x), the exported posts (the off-screen export
// node, 1080 wide, the same pixels as DOWNLOAD PNG) and shots.json with the
// on-screen boxes the cursor animation needs. Same method as
// frontend/verification/shoot_templates.mjs.
//
// Sample data: the scoreline matches the September V5 video; every player is invented.
import { createRequire } from 'node:module'
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'

const require = createRequire(new URL('../../../../frontend/', import.meta.url))
const { chromium } = require('playwright')

const OUT = process.argv[2]
if (!OUT) throw new Error('usage: capture.mjs <outDir>')
mkdirSync(OUT, { recursive: true })
const BASE = process.env.BASE || 'http://127.0.0.1:5199'
const EXE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

const SETTINGS = { id: 'org-1', name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'applecross', logo_url: null, primary_color: '#5a0f1f', accent_color: '#f5c242', theme_config: null }
const json = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
const bat = (pid, first, last, r, b, notOut = false) => ({ pid, first, last, short: `${first[0]}. ${last}`.toUpperCase(), r, b, notOut })
const bowl = (pid, first, last, o, r, w) => ({ pid, first, last, short: `${first[0]}. ${last}`.toUpperCase(), o, r, w, econ: (r / parseFloat(o)).toFixed(2) })
const SC = {
  meta: { result: 'APPLECROSS WON BY 63 RUNS', competition: 'A Grade', round: 'Round 9', venue: 'Tompkins Park', date: '2026-02-14' },
  home: { name: 'Applecross Cricket Club', total: '204', wickets: 8, overs: '50.0',
    batting: [bat('a1', 'Daniel', 'Reid', 78, 91), bat('a2', 'Tom', 'Hughes', 46, 52), bat('a3', 'Sam', 'Okafor', 31, 40, true), bat('a4', 'Liam', 'Foster', 22, 30)],
    bowling: [bowl('b1', 'Jake', 'Morris', '10.0', 31, 2), bowl('b2', 'Ravi', 'Shah', '9.0', 44, 1)] },
  away: { name: 'Balcatta Cricket Club', total: '141', wickets: 7, overs: '50.0',
    batting: [bat('b1', 'Jake', 'Morris', 44, 60), bat('b2', 'Ravi', 'Shah', 28, 35), bat('b3', 'Ben', 'Carter', 19, 33)],
    bowling: [bowl('a5', 'Noah', 'Briggs', '10.0', 22, 4), bowl('a6', 'Callum', 'Rowe', '10.0', 35, 2), bowl('a1', 'Daniel', 'Reid', '8.0', 31, 1)] },
}
const GAMES = [
  { id: 'g1', home_team: 'Applecross Cricket Club', away_team: 'Balcatta Cricket Club', result: 'WIN', played_at: '2026-02-14', grade_name: 'A Grade', status: 'COMPLETED' },
  { id: 'g2', home_team: 'Swan Athletic', away_team: 'Applecross Cricket Club', result: 'LOSS', played_at: '2026-02-07', grade_name: 'A Grade', status: 'COMPLETED' },
  { id: 'g3', home_team: 'Applecross Cricket Club', away_team: 'Wanneroo', result: 'WIN', played_at: '2026-01-31', grade_name: 'B Grade', status: 'COMPLETED' },
]
const NAMES = ['Daniel Reid', 'Tom Hughes', 'Sam Okafor', 'Liam Foster', 'Noah Briggs', 'Callum Rowe', 'Jake Morris', 'Ben Carter', 'Ravi Shah', 'Chris Lowe', 'Aidan Wright']
const PLAYERS = NAMES.map((n, i) => ({ id: `p${i + 1}`, name: n, display_name: n, status: 'active', photo_url: null }))

const browser = await chromium.launch(existsSync(EXE) ? { executablePath: EXE } : {})
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: Number(process.env.DPR || 3) })
await ctx.route('**/api/**', async (route) => {
  const url = route.request().url()
  if (/\/auth\/me/.test(url)) return route.fulfill(json({ id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' } }))
  if (/\/admin\/social\/scorecard\//.test(url)) return route.fulfill(json(SC))
  if (/\/organisations\/org-1\/seasons/.test(url)) return route.fulfill(json([{ id: 's1', name: '2025/26' }]))
  if (/\/organisations\/org-1\/results/.test(url)) return route.fulfill(json(GAMES))
  if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
  if (/\/club-admin\/players/.test(url)) return route.fulfill(json(PLAYERS))
  if (/social\/media/.test(url) || /sponsors/.test(url)) return route.fulfill(json([]))
  return route.fulfill(json({}))
})
const page = await ctx.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))
const boxes = {}

async function open(id) {
  await page.goto(`${BASE}/admin/social-post?template=${id}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG/ }).first().waitFor({ timeout: 20000 })
  await page.waitForTimeout(900)
}
async function box(loc) {
  const b = await loc.first().boundingBox()
  return b ? { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) } : null
}
async function pickGame(record = false) {
  const toggle = page.getByText('Or pick from your Games').first()
  await toggle.scrollIntoViewIfNeeded()
  if (record) { boxes.pickToggle = await box(toggle); await page.screenshot({ path: `${OUT}/editor-scrolled.png` }) }
  await toggle.click()
  await page.waitForTimeout(700)
  const row = page.getByText(/Applecross Cricket Club v Balcatta/).first()
  if (record) {
    boxes.gameRow = await box(row)
    boxes.gameRows = [await box(page.locator('[data-testid="club-games-picker"] button').nth(1)), await box(page.locator('[data-testid="club-games-picker"] button').nth(2)), await box(page.locator('[data-testid="club-games-picker"] button').nth(3))]
    boxes.picker = await box(page.locator('[data-testid="club-games-picker"]'))
    await page.screenshot({ path: `${OUT}/editor-picker.png` })
  }
  await row.click()
  await page.waitForTimeout(1300)
}
async function pickSize(label) {
  const design = page.getByRole('button', { name: 'Design', exact: true })
  if (await design.count()) await design.first().click().catch(() => {})
  const btn = page.getByRole('button', { name: new RegExp(`^${label}`) })
  if (await btn.count()) await btn.first().click().catch(() => {})
  await page.waitForTimeout(450)
}
async function shootExport(file) {
  // The export node is up to 1920 tall; a shorter viewport silently crops the shot.
  await page.setViewportSize({ width: 1440, height: 2000 })
  await page.waitForTimeout(250)
  const moved = await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    if (!holder || !holder.firstElementChild) return null
    holder.dataset.shot = '1'
    Object.assign(holder.style, { left: '0px', top: '0px', position: 'fixed', zIndex: '2147483647', background: '#101010' })
    const r = holder.firstElementChild.getBoundingClientRect()
    return { w: Math.round(r.width), h: Math.round(r.height) }
  })
  if (!moved) { console.log('NO NODE', file); return }
  await page.screenshot({ path: `${OUT}/${file}`, scale: 'css', clip: { x: 0, y: 0, width: Math.min(moved.w, 1920), height: Math.min(moved.h, 1920) } })
  await page.evaluate(() => {
    const h = document.querySelector('[data-shot="1"]')
    if (!h) return
    Object.assign(h.style, { left: '-9999px', top: '0', position: 'absolute', zIndex: '-1', background: '' })
    delete h.dataset.shot
  })
  await page.setViewportSize({ width: 1440, height: 900 })
  console.log(file, `${moved.w}x${moved.h}`)
}
async function fillLineup() {
  const content = page.getByRole('button', { name: 'Content', exact: true })
  if (await content.count()) await content.first().click().catch(() => {})
  await page.waitForTimeout(200)
  for (const n of NAMES) {
    const b = page.getByRole('button', { name: new RegExp(`^${n}\\b`) })
    if (await b.count()) await b.first().click().catch(() => {})
  }
  await page.waitForTimeout(300)
}

// 1. The result flow on Margin Hero
await open('RS1')
await page.screenshot({ path: `${OUT}/editor-empty.png` })
boxes.download = await box(page.getByRole('button', { name: /DOWNLOAD PNG/ }))
await pickSize('Square'); await shootExport('rs1-empty-square.png')
await page.getByRole('button', { name: 'Content', exact: true }).first().click().catch(() => {})
await page.waitForTimeout(300)
await pickGame(true)
await page.screenshot({ path: `${OUT}/editor-filled.png` })
for (const [label, key] of [['Square', 'square'], ['Portrait', 'portrait'], ['Story', 'story']]) {
  await pickSize(label)
  await shootExport(`rs1-${key}.png`)
}

// 2. Other layouts from the same game
for (const id of ['RS3', 'RS5', 'RS6']) {
  await open(id)
  await pickGame(false)
  await pickSize('Square')
  await shootExport(`${id.toLowerCase()}-square.png`)
}
// 3. A lineup layout filled from the roster
await open('T1')
await fillLineup()
await pickSize('Square')
await shootExport('t1-lineup-square.png')

writeFileSync(`${OUT}/shots.json`, JSON.stringify({ viewport: { w: 1440, h: 900, scale: Number(process.env.DPR || 3) }, boxes, pageErrors: errors.length }, null, 2))
console.log('boxes', JSON.stringify(boxes), 'pageErrors', errors.length, errors[0] || '')
await browser.close()
