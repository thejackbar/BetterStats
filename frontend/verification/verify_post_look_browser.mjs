// Drives BetterPosts in Chromium (API stubbed at the network layer) to prove how a layout
// sits on a background and what the Brand tab can now set.
//
//   npx vite build && npx vite preview --port 5198 &
//   SHOTS=/some/dir node frontend/verification/verify_post_look_browser.mjs [baseUrl]
//
// Covers: a built-in texture keeps the layout's 60% fill and its dots, stripes and grain;
// the club's own photo gets neither unless asked; the tint and pattern controls; the four
// colour roles; and the Team Sheet's own elements (two title words, band, names, photo backdrop).
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


const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }

// The post as EXPORTED: the off-screen node, not the scaled preview.
const readRoot = (page) => page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  const root = holder && [...holder.querySelectorAll('div')].filter((d) => d.style.width && d.style.overflow === 'hidden' && d.querySelector('[data-layer="Players"]')).pop()
  if (!root) return null
  // Layout-drawn texture: the dot, stripe and grain layers are the root's own children.
  const kids = [...root.children]
  const dots = kids.filter((k) => /radial-gradient/.test(k.style.backgroundImage || '')).length
  const stripes = kids.filter((k) => /repeating-linear-gradient/.test(k.style.backgroundImage || '')).length
  const grain = kids.filter((k) => k.tagName.toLowerCase() === 'svg').length
  const head = root.querySelector('[data-layer="Masthead"]')
  const spans = head ? [...head.querySelectorAll('span')] : []
  const card = root.querySelector('[data-layer="Players"] > div')
  const band = card && card.children[1]
  return {
    bg: root.style.background || root.style.backgroundColor, dots, stripes, grain, ink: getComputedStyle(root).color,
    title: spans.map((s) => ({ text: s.textContent, color: getComputedStyle(s).color })),
    ghost: kids.some((k) => /TOTW/.test(k.textContent || '') && !k.dataset.layer),
    bandBg: band && getComputedStyle(band).backgroundColor, bandInk: band && getComputedStyle(band).color,
    photoBg: card && getComputedStyle(card.children[0]).backgroundColor,
  }
})
const rgb = (hex) => { const n = parseInt(hex.slice(1), 16); return `rgb(${n >> 16}, ${(n >> 8) & 255}, ${n & 255})` }

const { ctx, page, errors } = await openEditor('?type=totw')
page.setDefaultTimeout(2500)
// A control build lacks these controls: an action on one reports, it does not throw.
const safe = async (fn) => { try { return await fn() } catch { return undefined } }
await press(page.getByRole('button', { name: 'Pull latest round' }))
await page.getByTestId('totw-count').first().waitFor({ timeout: 8000 }).catch(() => {})
await press(page.getByRole('button', { name: /Continue to editor/ }))
await page.waitForTimeout(300)
const brand = async () => { await press(page.getByRole('button', { name: /^BRAND$/i })); await page.waitForTimeout(150) }
await brand()

// ── A. A built-in texture keeps what every layout has always drawn ─────────
const base = await readRoot(page)
ck('before any background: the layout draws its own dots, stripes and grain', base && base.dots >= 1 && base.stripes >= 1 && base.grain >= 1, JSON.stringify(base))
ck('before any background: no finish controls are offered', !(await seen(page.getByTestId('bg-finish'))))

const picked = await page.evaluate(() => {
  const clean = document.querySelector('button[title="Clean"]')
  const row = clean && clean.parentElement
  const btns = row ? [...row.querySelectorAll('button')] : []
  const next = btns.find((b) => b !== clean)
  if (!next) return false
  next.click(); return true
})
await page.waitForTimeout(250)
ck('a built-in background can be picked', picked)
const tex = await readRoot(page)
ck('built-in texture: the finish controls appear', await seen(page.getByTestId('bg-finish')))
ck('built-in texture: the fill keeps the default 60% (#rrggbb99)', /99\)?$|99/.test(tex?.bg || '') || /0\.6/.test(tex?.bg || ''), tex?.bg)
ck('built-in texture: the layout still draws its dots', tex && tex.dots >= 1, JSON.stringify(tex))
ck('built-in texture: the tint reads 60%', (await safe(() => page.getByTestId('bg-tint').inputValue())) === '60')

// ── B. The club's own photo: no veil, no pattern ──────────────────────────
await press(page.getByTitle('My background'))
await page.waitForTimeout(250)
const own = await readRoot(page)
ck('own photo: the layout fill is fully transparent', /rgba\(\d+, \d+, \d+, 0\)|#[0-9a-f]{6}00/i.test(own?.bg || ''), own?.bg)
ck('own photo: no dots, stripes or grain over it', own && own.dots === 0 && own.stripes === 0 && own.grain === 0, JSON.stringify(own))
ck('own photo: the ghost TOTW word is gone too', own && own.ghost === false)
ck('own photo: the tint control reads 0%', (await safe(() => page.getByTestId('bg-tint').inputValue())) === '0')
ck('own photo: the pattern switch is off', (await safe(() => page.getByTestId('bg-texture').isChecked())) === false)

// The club can still put them back.
await safe(() => page.getByTestId('bg-texture').check())
await page.waitForTimeout(150)
const withTex = await readRoot(page)
ck('switching the pattern on draws it again', withTex && withTex.dots >= 1 && withTex.stripes >= 1 && withTex.grain >= 1, JSON.stringify(withTex))
await safe(() => page.getByTestId('bg-tint').fill('60'))
await page.waitForTimeout(150)
const withTint = await readRoot(page)
ck('a 60% tint puts the veil back (alpha 0.6)', /0\.6\)?$|99$/.test(withTint?.bg || ''), withTint?.bg)
await press(page.getByTestId('bg-finish-reset'))
await page.waitForTimeout(150)
const reset = await readRoot(page)
ck('Back to automatic returns to a bare photo', reset && reset.dots === 0 && /, 0\)|00$/.test(reset.bg || ''), JSON.stringify(reset))

// ── C. Colour roles reach the whole post ──────────────────────────────────
await safe(() => page.getByLabel('Text', { exact: true }).fill('#ff0000'))
await page.waitForTimeout(150)
ck('the Text role changes the layout ink', (await readRoot(page))?.ink === rgb('#ff0000'), (await readRoot(page))?.ink)
await press(page.getByTestId('colour-roles').getByRole('button', { name: 'Reset all' }))
await page.waitForTimeout(150)
ck('Reset all returns the palette ink', (await readRoot(page))?.ink !== rgb('#ff0000'))

// ── D. This layout's elements ─────────────────────────────────────────────
ck('Team Sheet offers its own elements', await seen(page.getByTestId('layout-elements')))
const t0 = await readRoot(page)
ck('the heading is TEAM OF / THE WEEK by default', t0?.title?.map((t) => t.text).join('|') === 'TEAM OF|THE WEEK', JSON.stringify(t0?.title))
await safe(() => page.getByTestId('part-title1').locator('input').fill('BEST OF'))
await safe(() => page.getByLabel('Second word colour').fill('#00ff00'))
await safe(() => page.getByLabel('First word colour').fill('#0000ff'))
await safe(() => page.getByLabel('Name band').fill('#ffffff'))
await safe(() => page.getByLabel('Photo backdrop').fill('#123456'))
await page.waitForTimeout(200)
const t1 = await readRoot(page)
ck('the first words are editable', t1?.title?.[0]?.text === 'BEST OF', JSON.stringify(t1?.title))
ck('the two title words take their own colours', t1?.title?.[0]?.color === rgb('#0000ff') && t1?.title?.[1]?.color === rgb('#00ff00'), JSON.stringify(t1?.title))
ck('the name band takes its own colour', t1?.bandBg === rgb('#ffffff'), t1?.bandBg)
ck('names turn dark on a white band without being asked', t1?.bandInk === 'rgb(11, 11, 11)', t1?.bandInk)
ck('the photo backdrop takes its own colour', t1?.photoBg === rgb('#123456'), t1?.photoBg)
await safe(() => page.getByLabel('Surname').fill('#ff00ff'))
await page.waitForTimeout(150)
ck('the name colour can be set on its own', (await readRoot(page))?.bandInk === rgb('#ff00ff'), (await readRoot(page))?.bandInk)

// Survives a reload, and Ranked Board has its own set.
await page.reload({ waitUntil: 'domcontentloaded' })
await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
await press(page.getByRole('button', { name: 'Pull latest round' }))
await page.getByTestId('totw-count').first().waitFor({ timeout: 8000 }).catch(() => {})
await press(page.getByRole('button', { name: /Continue to editor/ }))
await page.waitForTimeout(300)
const after = await readRoot(page)
ck('the picks survive a reload', after?.title?.[0]?.text === 'BEST OF' && after?.bandBg === rgb('#ffffff'), JSON.stringify(after?.title))
ck('the own photo survives a reload (no fall back to a built-in texture)', after && after.dots === 0 && /, 0\)|00$/.test(after.bg || ''), after?.bg)

if (SHOTS) await page.screenshot({ path: `${SHOTS}/look-brand.png` }).catch(() => {})
await press(page.getByRole('button', { name: 'Design', exact: true }))
await press(page.getByRole('button', { name: /Ranked Board/ }))
await page.waitForTimeout(200)
await brand()
ck('Ranked Board offers its own elements, not the sheet\'s', await seen(page.getByTestId('part-dividerColor')) && !(await seen(page.getByTestId('part-bandBg'))))
{
  const board = await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    const head = holder && holder.querySelector('[data-layer="Masthead"]')
    return head ? [...head.querySelectorAll('span')].map((s) => ({ t: s.textContent, c: getComputedStyle(s).color })) : null
  })
  ck('the heading picks carry over to the Ranked Board', board?.[0]?.t === 'BEST OF' && board?.[0]?.c === rgb('#0000ff') && board?.[1]?.c === rgb('#00ff00'), JSON.stringify(board))
}
if (SHOTS) await page.screenshot({ path: `${SHOTS}/look-board.png` }).catch(() => {})

ck('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
await ctx.close()
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
