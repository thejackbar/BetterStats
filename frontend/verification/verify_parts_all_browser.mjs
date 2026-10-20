// Drives EVERY BetterPosts layout in Chromium (API stubbed): opens it with ?template=ID, sets every colour in the
// Brand tab's elements panel, checks the pick reaches the exported post, that Reset all undoes it, and that nothing throws.
//   npx vite build && npx vite preview --port 5198 &
//   [IDS=T1,FX1] [SHOTS=dir] node verification/verify_parts_all_browser.mjs [baseUrl]
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const SETTINGS = {
  id: 'org-1', name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'applecross',
  logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null,
}
// Ten of the sixteen ranked players are on the club roster (so their photo
// resolves); the last six are scorecard names with no club record.
const NAMES = ['Star, Sam', 'Ton, Eli', 'Bowler, Bo', 'Guest, Gus', 'Keeper, Fay', 'Catcher, Cy', 'Duck, Dee',
  'Alpha, Al', 'Bravo, Bea', 'Charlie, Chaz', 'Delta, Dom', 'Echo, Ed', 'Foxtrot, Flo', 'Golf, Gil', 'Hotel, Hux', 'India, Ivy']
const PLAYERS = NAMES.slice(0, 10).map((n, i) => ({
  id: `p${i + 1}`, name: n, display_name: n, status: 'active', photo_url: `/api/images/players/p${i + 1}/photo`,
}))
// The seat each performance fills (WK / BAT / AR / BOWL). The first six are the junior game's players.
const KINDS = ['AR', 'BAT', 'BOWL', 'WK', 'BAT', 'BOWL', 'AR', 'BAT', 'WK', 'BOWL', 'AR', 'BAT', 'BOWL', 'BAT', 'WK', 'BAT']
const POOL = NAMES.map((n, i) => {
  const [last, first] = n.split(', ')
  const base = 130 - i * 7
  return {
    first, last, short: `${first[0]}. ${last.toUpperCase()}`, pid: i < 10 ? `p${i + 1}` : null, guid: `g${i + 1}`, points: base,
    batting: i % 3 === 0 ? { r: base - 40, b: 50, notOut: i % 2 === 0, fours: 0, sixes: 0, sr: 100 } : null,
    bowling: i % 3 !== 2 ? { o: '8.0', m: 1, r: 30, w: 2, econ: 3.75 } : null,
    fielding: i % 4 === 0 ? { catches: 2, catches_wk: 0, stumpings: 0, run_outs: 0 } : null,
    grade: i % 2 ? '2ND GRADE' : '1ST GRADE', opp: 'RIVALS CC', oppMono: 'RIV', outcome: 'W',
    kind: KINDS[i], categories: i < 6 ? ['junior'] : ['senior'],
  }
})
const TOTW = { kind: 'round', season: '2025/26', club: {}, round: 'Round 5', date: '2026-09-26', label: 'SAT 26 SEP', matches: 3, scope: 'all', scopeMatches: { junior: 2, senior: 3 }, players: POOL }
// What the server answers for a query: the same round, narrowed to the junior game's players or to the rest by `scope`,
// and labelled with the period when one is sent.
const totwFor = (search) => {
  const q = new URLSearchParams(search)
  const scope = q.get('scope') || 'all'
  const players = scope === 'junior' ? POOL.slice(0, 6) : scope === 'senior' ? POOL.slice(6) : POOL
  const label = q.get('date_from') ? 'TUE 13 TO SUN 18 OCT' : TOTW.label
  return { ...TOTW, scope, label, players, matches: scope === 'all' ? 5 : scope === 'junior' ? 2 : 3 }
}
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC', 'base64')

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openEditor(query, viewport = { width: 1600, height: 1000 }, mobile = false) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const errors = []
  const totwCalls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_/.test(m.text())) errors.push(m.text()) })
  const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    if (/\/admin\/social\/totw/.test(url)) { totwCalls.push(new URL(url).search); return route.fulfill(json(totwFor(new URL(url).search))) }
    if (/\/images\/players\/[^/]+\/photo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross',
      entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
    }))
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json([]))
    if (/\/images\/bg1/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json(/kind=background/.test(url) ? [{ id: 'bg1', name: 'My background', url: '/api/images/bg1' }] : []))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json(PLAYERS))
    if (/sponsors/.test(url)) return route.fulfill(json([]))
    if (/selection\/overview/.test(url)) return route.fulfill(json({ fixtures: [] }))
    if (/lineups/.test(url)) return route.fulfill(json({ matches: [] }))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/social-post${query}`, { waitUntil: 'domcontentloaded' })
  // Anchor on the export button, which every build has; a control run on a build
  // without this feature then reports below rather than dying here.
  // (The phone layout is a different, quick-post editor with no such button.)
  if (mobile) await page.waitForFunction(() => document.body.innerText.length > 80, null, { timeout: 25000 })
  else await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  return { ctx, page, errors, totwCalls }
}



const IDS = (process.env.IDS || 'T1,T2,T3,T4,T5,T6,T7,T8,T9,T10,T11,T12,T13,C1,C2,C3,C4,C5,RS1,RS2,RS3,RS4,RS5,RS6,RS7,RS8,FX1,FX2,FX3,FX4,FX5,FX6,RR1,RR2,RR3,RR4,RR5,RR6,RR7,TW1,TW2,MS1,MS2,SC1,SC2,SC3,EV1,EV2,EV3,EV4,EV5,EV6,EV7,EV8,EV9,EV10,EV11,EL1,EL2,EL3').split(',')
const MARK = '#0a8f3c', MARK_RGB = '10, 143, 60'
let errorsAll = []
for (const id of IDS) {
  const { ctx, page, errors } = await openEditor(`?template=${id}`)
  page.setDefaultTimeout(5000)
  try {
    await page.getByRole('button', { name: /^BRAND$/i }).first().click()
    await page.waitForTimeout(250)
    const panel = page.getByTestId('layout-elements')
    const shown = await panel.count()
    const inputs = panel.locator('input[type=color]')
    const n = shown ? await inputs.count() : 0
    ck(`${id}: the Brand tab lists its own elements`, shown === 1 && n >= 5, `panel=${shown} colour parts=${n}`)
    const html0 = await page.evaluate(() => { const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute'); return h ? h.innerHTML : '' })
    ck(`${id}: nothing is in the post's own markup before a pick`, html0.length > 200 && !html0.includes(MARK_RGB), `len=${html0.length}`)
    for (let i = 0; i < n; i++) await inputs.nth(i).fill(MARK)
    await page.waitForTimeout(300)
    const html1 = await page.evaluate(() => { const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute'); return h ? h.innerHTML : '' })
    const hits = html1.split(MARK_RGB).length - 1
    ck(`${id}: picking every colour reaches the exported post`, hits >= Math.min(3, n), `${hits} uses of the pick from ${n} parts`)
    const reset = panel.getByRole('button', { name: 'Reset all' })
    ck(`${id}: Reset all is offered once something is picked`, (await reset.count()) > 0)
    await reset.first().click().catch(() => {})
    await page.waitForTimeout(200)
    const html2 = await page.evaluate(() => { const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute'); return h ? h.innerHTML : '' })
    ck(`${id}: Reset all returns the post to its own colours`, !html2.includes(MARK_RGB), `${html2.split(MARK_RGB).length - 1} left`)
    if (SHOTS && ['T1', 'FX1', 'RR1', 'RS2', 'EV3', 'SC1', 'MS1'].includes(id)) {
      for (let i = 0; i < n; i++) await inputs.nth(i).fill(i % 2 ? '#ff7a00' : '#00b3ff')
      await page.waitForTimeout(250)
      await page.screenshot({ path: `${SHOTS}/parts-${id}.png` }).catch(() => {})
    }
  } catch (e) { ck(`${id}: sweep ran`, false, String(e.message).split('\n')[0]) }
  ck(`${id}: no page errors`, errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
