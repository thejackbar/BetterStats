// Drives the real BetterSelect team sheet and the BetterPosts lineup list in
// Chromium (API stubbed at the network layer) for the A to Z by first name option.
//
//   npx vite build && npx vite preview --port 5198 &
//   node frontend/verification/verify_alpha_order_browser.mjs [baseUrl]
//
// Reported: teams could only be shown in batting order, or dragged into position by
// hand. What a build cannot tell you:
//   * the team sheet lists the XI by FIRST name when asked (surname order would put
//     them somewhere else), with no batting numbers, and the saved batting order is
//     untouched (nothing is written, switching back gives the numbered order again)
//   * Copy lineup as text follows the same order
//   * Open in social post hands the post the players in the order the sheet shows
//   * in the post's player list, A-Z sorts by first name, and putting the order back
//     restores what it was, including after a player is added in between
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { chromium } from 'playwright'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures/selection_same_day.json'), 'utf8'))

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

// Batting order: Zed, Mick, Bob, Alan, Cara. By FIRST name: Alan, Bob, Cara, Mick,
// Zed. By SURNAME it would be Mick (Alpha), Cara (Bravo), Bob (Charlie), Alan
// (Delta), Zed (Zulu), so a sort on the wrong half of the name cannot pass.
const BAT = [['Zed Zulu', 'z'], ['Mick Alpha', 'm'], ['Bob Charlie', 'b'], ['Alan Delta', 'a'], ['Cara Bravo', 'c']]
const FIRST = ['Alan', 'Bob', 'Cara', 'Mick', 'Zed']
const base = FIX.payload.pool[0]
const POOL = BAT.map(([name, k]) => ({ ...base, id: `id-${k}`, display_name: name, also_in: [], clash: [], clash_detail: [], clash_blocks: false }))
const PAYLOAD = {
  ...FIX.payload, pool: POOL,
  lineup: POOL.map((p, i) => ({ player_id: p.id, batting_order: i + 1, is_captain: false, is_wicket_keeper: false })),
}
const ME = {
  id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select', 'socials', 'stats'], status: 'active' },
}
const SETTINGS = { id: 'org-1', name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'applecross', logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null, player_name_format: 'first_last' }
const ROSTER = [...BAT.map(([name, k]) => ({ id: `id-${k}`, name, display_name: name, status: 'active', photo_url: null })),
  { id: 'id-e', name: 'Bea Echo', display_name: 'Bea Echo', status: 'active', photo_url: null }]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
await ctx.grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => {})
const page = await ctx.newPage()
page.setDefaultTimeout(4000)
const errors = []
const writes = []
page.on('pageerror', (e) => errors.push(String(e)))
page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_/.test(m.text())) errors.push(m.text()) })
const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
await page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url()
  if (req.method() !== 'GET' && /\/selection\//.test(url)) writes.push(`${req.method()} ${url}`)
  if (/\/auth\/me/.test(url)) return route.fulfill(json(ME))
  if (new RegExp(`/selection/${FIX.fixture_id}/draft`).test(url)) return route.fulfill(json({ draft: null, version: 0 }))
  if (new RegExp(`/selection/${FIX.fixture_id}$`).test(url)) return route.fulfill(json(PAYLOAD))
  if (/\/selection\/[^/]+\/previous-xi/.test(url)) return route.fulfill(json({ source_fixture_id: null, player_ids: [], captain_id: null, wicket_keeper_id: null }))
  if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
  if (/\/club-admin\/players/.test(url)) return route.fulfill(json(ROSTER))
  if (/\/admin\/social\/(templates|media)/.test(url)) return route.fulfill(json([]))
  if (/sponsors/.test(url)) return route.fulfill(json([]))
  if (/selection\/overview/.test(url)) return route.fulfill(json({ fixtures: [] }))
  if (/lineups/.test(url)) return route.fulfill(json({ matches: [] }))
  return route.fulfill(json({}))
})

const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }

// The names on the open team sheet, in order, with whatever number leads each row.
const sheetRows = async () => page.evaluate(() => {
  const head = [...document.querySelectorAll('div')].find((d) => /^Team sheet$/i.test(d.textContent.trim()) && d.className.includes('uppercase'))
  const modal = head && head.closest('.rounded-2xl')
  if (!modal) return null
  return [...modal.querySelectorAll('.overflow-auto > div')].map((r) => r.innerText.replace(/\s+/g, ' ').trim()).filter((t) => /\b(Zed|Mick|Bob|Alan|Cara)\b/.test(t))
})
const namesOnly = (rows) => (rows || []).map((t) => (t.match(/\b(Zed|Mick|Bob|Alan|Cara)\b/) || [])[1])

// Open in social post lands on the start screen with the players already carried
// across; choosing Lineup opens the editor on them.
const enterEditor = async () => {
  await page.getByRole('button', { name: /^Lineup/ }).first().waitFor({ timeout: 25000 }).catch(() => {})
  await press(page.getByRole('button', { name: /^Lineup/ }))
  await press(page.getByRole('button', { name: /Continue to editor/ }))
  await page.getByTestId('selected-player-row').first().waitFor({ timeout: 25000 }).catch(() => {})
}

// ── 1. The team sheet ──────────────────────────────────────────────────────
await page.goto(`${BASE}/admin/betterselect/select/${FIX.fixture_id}`, { waitUntil: 'domcontentloaded' })
await page.getByText('Zed Zulu').first().waitFor({ timeout: 25000 }).catch(() => {})
await page.evaluate(() => { try { localStorage.removeItem('bs_sheet_order') } catch { /* fine */ } })
await press(page.getByRole('button', { name: /Share/ }))
await page.waitForTimeout(300)
let rows = await sheetRows()
ck('the sheet opens in batting order', namesOnly(rows).join() === 'Zed,Mick,Bob,Alan,Cara', JSON.stringify(rows))
ck('batting order rows are numbered', (rows || []).every((t, i) => t.startsWith(`${i + 1} `)), JSON.stringify(rows))
ck('the sheet offers an A to Z choice', await seen(page.getByTestId('sheet-order')))

await press(page.getByRole('button', { name: 'A to Z by first name' }))
await page.waitForTimeout(150)
rows = await sheetRows()
ck('A to Z lists the XI by first name', namesOnly(rows).join() === FIRST.join(), JSON.stringify(rows))
ck('A to Z carries no batting numbers', (rows || []).every((t) => !/^\d+ /.test(t)), JSON.stringify(rows))
ck('the choice is shown as pressed', (await page.getByRole('button', { name: 'A to Z by first name' }).first().getAttribute('aria-pressed').catch(() => null)) === 'true')

await press(page.getByRole('button', { name: /Copy lineup as text/ }))
await page.waitForTimeout(250)
const copied = await page.evaluate(() => navigator.clipboard.readText().catch(() => '')).catch(() => '')
const copiedNames = copied.split('\n').filter((l) => /Zed|Mick|Bob|Alan|Cara/.test(l))
ck('the copied text follows the same order', copiedNames.map((l) => (l.match(/\b(Zed|Mick|Bob|Alan|Cara)\b/) || [])[1]).join() === FIRST.join(), JSON.stringify(copied))
ck('the copied text has no numbers in A to Z', copiedNames.every((l) => !/^\d+\./.test(l)), JSON.stringify(copiedNames))

await press(page.getByRole('button', { name: 'Batting order', exact: true }))
await page.waitForTimeout(150)
rows = await sheetRows()
ck('switching back restores the numbered batting order', namesOnly(rows).join() === 'Zed,Mick,Bob,Alan,Cara' && rows.every((t, i) => t.startsWith(`${i + 1} `)), JSON.stringify(rows))
ck('nothing was written to the selection', writes.length === 0, JSON.stringify(writes))

// ── 2. Into the post, in the order the sheet shows ─────────────────────────
await press(page.getByRole('button', { name: 'A to Z by first name' }))
await page.waitForTimeout(100)
await press(page.getByRole('button', { name: /Open in social post/ }))
await enterEditor()
const postNames = async () => (await page.getByTestId('selected-player-row').allInnerTexts()).map((t) => (t.match(/\b(Zed|Mick|Bob|Alan|Cara|Bea)\b/) || [])[1])
ck('the post gets the players in A to Z', (await postNames()).join() === FIRST.join(), (await postNames()).join())

// ── 3. The post's own list ─────────────────────────────────────────────────
await page.evaluate(() => { try { localStorage.setItem('bs_sheet_order', 'batting') } catch { /* fine */ } })
await page.goto(`${BASE}/admin/betterselect/select/${FIX.fixture_id}`, { waitUntil: 'domcontentloaded' })
await page.getByText('Zed Zulu').first().waitFor({ timeout: 25000 }).catch(() => {})
await press(page.getByRole('button', { name: /Share/ }))
await page.waitForTimeout(300)
ck('the sheet remembers batting order was chosen last', namesOnly(await sheetRows()).join() === 'Zed,Mick,Bob,Alan,Cara')
await press(page.getByRole('button', { name: /Open in social post/ }))
await enterEditor()
ck('the post starts in batting order', (await postNames()).join() === 'Zed,Mick,Bob,Alan,Cara', (await postNames()).join())
ck('the post offers A-Z', await seen(page.getByTestId('order-alpha')))

await press(page.getByTestId('order-alpha'))
await page.waitForTimeout(150)
ck('A-Z sorts the post list by first name', (await postNames()).join() === FIRST.join(), (await postNames()).join())
ck('the button becomes a way back', await seen(page.getByTestId('order-restore')) && !(await seen(page.getByTestId('order-alpha'))))

await press(page.getByTestId('order-restore'))
await page.waitForTimeout(150)
ck('putting the order back restores batting order', (await postNames()).join() === 'Zed,Mick,Bob,Alan,Cara', (await postNames()).join())
ck('and offers A-Z again', await seen(page.getByTestId('order-alpha')))

// A player added between the sort and the restore goes last; nobody is lost.
await press(page.getByTestId('order-alpha'))
await page.waitForTimeout(100)
await press(page.getByRole('button', { name: 'Remove player' }).nth(0))   // Alan, first in A to Z, goes
await page.waitForTimeout(100)
await press(page.getByTestId('order-restore'))
await page.waitForTimeout(150)
ck('restoring after a removal keeps the others in batting order', (await postNames()).join() === 'Zed,Mick,Bob,Cara', (await postNames()).join())

ck('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
