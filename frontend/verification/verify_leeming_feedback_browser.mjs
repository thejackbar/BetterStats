// Drives the REAL BetterPosts editor in Chromium with the API stubbed at the network layer.
//
// Reported (Leeming Spartan, Nov 2026), Result · Classic (C4):
//   1. "Layout dots, stripes and grain" is one switch, and the background's diagonal lines ignore it.
//      Asked for: one control per texture, lines included, each with its own strength.
//   2. "Hide Cricket Club" changes both names. Asked for: the full name in the header and a short one
//      by the score.
//   3. The season prints 2025-26 unless typed. Asked for: the season of the match.
//   4. A picked panel colour is a solid fill. Asked for: an opacity for it.
//   5. Midway through a two-day game one side has only batted, and the other side's bowlers sit a row
//      lower than our batters.
//
//   npx vite build --outDir /var/tmp/lf_dist && npx vite preview --outDir /var/tmp/lf_dist --port 5199 &
//   node verification/verify_leeming_feedback_browser.mjs [baseUrl]
//
// Every read goes through presence-safe helpers, so an older build reports FAIL rather than crashing.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || ''
const SHOTS = process.env.SHOTS || ''
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const SETTINGS = { id: 'org-1', name: 'Leeming Spartan Cricket Club', short_name: 'LSCC', slug: 'leeming', logo_url: null, primary_color: '#1b2a6b', accent_color: '#22b8f0', theme_config: null }
const ME = { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'leeming', entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' } }

const bat = (short, r, b) => ({ first: '', last: short.split('. ')[1], short, r, b, notOut: false, didNotBat: false, pid: null })
const bowl = (short, w, r, o) => ({ first: '', last: short.split('. ')[1], short, o, m: 0, r, w, econ: r / 8, pid: null })
// Day one of a two-day game: we batted, they bowled, they have not batted yet. Our side's `bowling`
// is the bowling in the innings we batted (their bowlers); theirs is empty.
const SCORECARD = {
  meta: { competition: 'SMCA 1ST GRADE', round: 'ROUND 8', venue: 'TEMPEST PARK', date: '2026-11-21', result: '' },
  home: {
    name: 'Leeming Spartan Cricket Club', short: 'LSCC', total: '145', wickets: 10, overs: '80',
    batting: [bat('A. MORGAN', 70, 173), bat('J. JOHNSON', 21, 63), bat('T. STEPHENSON', 12, 24)],
    bowling: [bowl('J. BACK', 4, 64, '20'), bowl('A. SARWAR', 3, 39, '15'), bowl('T. WYBENGA', 1, 13, '6')],
  },
  away: { name: 'Phoenix Cricket Club', short: 'PCC', total: '', wickets: 0, overs: '', batting: [], bowling: [] },
}

// The post as it is exported: the off-screen export node's first child.
const FRAME_INIT = () => {
  window.__frame = () => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    return holder ? holder.firstElementChild : null
  }
}
async function shot(page, file) {
  await page.evaluate(() => {
    const holder = window.__frame().parentElement
    holder.dataset.shot = '1'; Object.assign(holder.style, { left: '0px', top: '0px', position: 'fixed', zIndex: '2147483647', background: '#101010' })
  })
  await page.screenshot({ path: file, clip: { x: 0, y: 0, width: 1080, height: 1080 } })
  await page.evaluate(() => {
    const h = document.querySelector('[data-shot="1"]')
    Object.assign(h.style, { left: '-9999px', top: '0', position: 'absolute', zIndex: '-1', background: '' }); delete h.dataset.shot
  })
}

const browser = await chromium.launch(EXECUTABLE && existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openEditor(init = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1700, height: 2300 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort())
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    if (/\/auth\/me/.test(url)) return route.fulfill(json(ME))
    if (/\/admin\/social\/match-lookup/.test(url)) return route.fulfill(json({ kind: 'match', match_id: 'm1' }))
    if (/\/admin\/social\/scorecard\//.test(url)) return route.fulfill(json(SCORECARD))
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json([]))
    if (/sponsors\/post-default/.test(url)) return route.fulfill(json({ sponsor_ids: [], source: 'club' }))
    if (/sponsors/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  await page.addInitScript(FRAME_INIT)
  await page.addInitScript((kv) => {
    localStorage.setItem('bs_social_template', 'C4')
    localStorage.setItem('bs_social_post_size', 'square')
    Object.entries(kv).forEach(([k, v]) => localStorage.setItem(k, v))
  }, init)
  await page.goto(`${BASE}/admin/social-post?type=result&template=C4`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 30000 })
  return { ctx, page, errors }
}
const visible = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
async function reveal(page, loc) {
  for (const t of ['Content', 'Brand', 'Design', 'Data', null]) {
    if (await visible(loc)) return true
    if (t) { await page.getByRole('button', { name: t, exact: true }).first().click().catch(() => {}); await page.waitForTimeout(300) }
  }
  return visible(loc)
}
async function importMatch(page) {
  const box = page.getByPlaceholder(/Match link from play\.cricket/).first()
  await reveal(page, box)
  await box.fill('m1')
  await page.getByRole('button', { name: /^(Import|Fetch)$/ }).first().click()
  await page.waitForTimeout(1500)
}
// Text of the exported post.
const postText = (page) => page.evaluate(() => {
  const f = window.__frame()
  return f ? f.innerText.replace(/\s+/g, ' ') : ''
})
// Top of the first leaf element in the post whose text is exactly `t` (null when absent).
const topOf = (page, t) => page.evaluate((s) => {
  const f = window.__frame()
  if (!f) return null
  const el = Array.from(f.querySelectorAll('span, div')).find((e) => e.children.length === 0 && e.textContent.trim() === s)
  return el ? el.getBoundingClientRect().top : null
}, t)
// Inline styles in the post that match a pattern, counted.
const countStyle = (page, re) => page.evaluate((src) => {
  const f = window.__frame()
  if (!f) return -1
  const r = new RegExp(src)
  return Array.from(f.querySelectorAll('[style]')).filter((e) => r.test(e.getAttribute('style'))).length
}, re)
const setRange = (page, testid, value) => page.evaluate(([id, v]) => {
  const el = document.querySelector(`input[type=range][data-testid="${id}"]`) || document.querySelector(`[data-testid="${id}"] input[type=range]`)
  if (!el || el.disabled) return false
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
  setter.call(el, String(v)); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }))
  return true
}, [testid, value])
const setColour = (page, testid, value) => page.evaluate(([id, v]) => {
  const el = document.querySelector(`[data-testid="${id}"] input[type=color]`)
  if (!el) return false
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
  setter.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }))
  return true
}, [testid, value])
// The background of the performers panel that carries `title`.
// `which` is 0 for our panel, 1 for theirs.
const panelBg = (page, which) => page.evaluate((n) => {
  const f = window.__frame()
  if (!f) return null
  const heads = Array.from(f.querySelectorAll('div')).filter((e) => e.children.length === 0 && / · TOP PERFORMERS$/.test(e.textContent.trim()))
  return heads[n] ? getComputedStyle(heads[n].parentElement).backgroundColor : null
}, which)

// ───────── 5 and 3: a two-day game on day one ─────────
console.log('\n# Day one of a two-day game')
{
  const { ctx, page, errors } = await openEditor()
  await importMatch(page)
  const morgan = await topOf(page, 'A. MORGAN')
  const back = await topOf(page, 'J. BACK')
  ck('our top batter and their top bowler are both on the post', morgan != null && back != null, JSON.stringify({ morgan, back }))
  ck('their first bowler lines up with our first batter', morgan != null && back != null && Math.abs(morgan - back) < 2, JSON.stringify({ morgan, back }))
  const text = await postText(page)
  ck('the opposition panel has no empty BATTING heading', !/PCC · TOP PERFORMERS BATTING/.test(text) && /PCC · TOP PERFORMERS BOWLING J\. BACK/.test(text), text.slice(0, 400))
  ck('our panel keeps its BATTING heading', /LSC · TOP PERFORMERS BATTING A\. MORGAN/.test(text), text.slice(0, 400))
  ck('the season is the match\'s own (2026-27), not 2025-26', /2026-27/.test(text) && !/2025.26/.test(text), text.slice(0, 300))
  if (SHOTS) await shot(page, `${SHOTS}/two_day.png`)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ───────── 2 and 4: the name by the score, and the panel opacity ─────────
console.log('\n# Name by the score and panel opacity')
{
  const { ctx, page, errors } = await openEditor()
  await importMatch(page)
  const nameBox = page.locator('[data-testid="part-c4ScoreName"] input')
  const found = await reveal(page, nameBox)
  ck('a field for the name by the score is offered', found)
  if (found) { await nameBox.fill('Leeming Spartan'); await page.waitForTimeout(400) }
  const text = await postText(page)
  ck('the header keeps the full club name', /LEEMING SPARTAN CRICKET CLUB/.test(text), text.slice(0, 300))
  ck('the score box prints the short name', /LEEMING SPARTAN 145/i.test(text) && !/CRICKET CLUB 145/i.test(text), text.slice(0, 400))

  const alpha = page.locator('[data-testid="part-c4PanelAlpha"]')
  const alphaFound = await reveal(page, alpha)
  ck('a panel opacity control is offered', alphaFound)
  const before = alphaFound ? await alpha.innerText() : ''
  ck('on Auto it says to pick a panel colour first', /Pick a panel colour/.test(before), before)
  const picked = await setColour(page, 'part-cardBg', '#ff0000')
  await page.waitForTimeout(300)
  ck('a picked panel colour fills solid at first', (await panelBg(page, 0)) === 'rgb(255, 0, 0)', String(await panelBg(page, 0)))
  const moved = picked && await setRange(page, 'part-c4PanelAlpha', 40)
  await page.waitForTimeout(300)
  const bg = await panelBg(page, 0)
  ck('the opacity slider makes it see-through (40%)', moved && /rgba\(255, 0, 0, 0\.4/.test(bg || ''), String(bg))
  ck('the opposition panel follows the same pick', /rgba\(255, 0, 0, 0\.4/.test((await panelBg(page, 1)) || ''))
  if (SHOTS) await shot(page, `${SHOTS}/name_alpha.png`)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ───────── 1: each texture on its own ─────────
console.log('\n# Dots, stripes, grain and background lines')
{
  const { ctx, page, errors } = await openEditor({ bs_social_bg: 'gradient-custom' })
  const LINES = 'background-image: repeating-linear-gradient\\(-45deg'
  const DOTS = 'radial-gradient\\((#|rgb).{0,40}1\\.2px'
  const STRIPES = 'repeating-linear-gradient\\(0deg'
  const lines0 = await countStyle(page, LINES)
  const dots0 = await countStyle(page, DOTS)
  const stripes0 = await countStyle(page, STRIPES)
  ck('the gradient background draws its lines and C4 its dots and stripes', lines0 > 0 && dots0 > 0 && stripes0 > 0, JSON.stringify({ lines0, dots0, stripes0 }))
  const linesRow = page.locator('[data-testid="bg-finish-lines"]')
  ck('a background lines control is offered', await reveal(page, linesRow))
  for (const k of ['dots', 'stripes', 'grain']) ck(`a ${k} control is offered`, await visible(page.locator(`[data-testid="bg-finish-${k}"]`)))
  const press = async (id) => { const l = page.locator(`[data-testid="${id}"]`); if (await l.count()) { await l.first().click(); await page.waitForTimeout(300); return true } return false }
  await press('bg-finish-lines-on')
  ck('lines off: the lines go', (await countStyle(page, LINES)) === 0, String(await countStyle(page, LINES)))
  ck('...and the dots and stripes stay', (await countStyle(page, DOTS)) === dots0 && (await countStyle(page, STRIPES)) === stripes0)
  await press('bg-finish-dots-on')
  ck('dots off: the dots go and the stripes stay', (await countStyle(page, DOTS)) === 0 && (await countStyle(page, STRIPES)) === stripes0)
  await press('bg-finish-lines-on')
  ck('lines back on', (await countStyle(page, LINES)) === lines0)
  await setRange(page, 'bg-finish-lines-strength', 300)
  await page.waitForTimeout(300)
  const lineOp = await page.evaluate((src) => {
    const f = window.__frame(); const r = new RegExp(src)
    const e = f && Array.from(f.querySelectorAll('[style]')).find((x) => r.test(x.getAttribute('style')))
    return e ? getComputedStyle(e).opacity : null
  }, LINES)
  ck('lines at 300% draw three times as strong (0.08 to 0.24)', lineOp != null && Math.abs(Number(lineOp) - 0.24) < 0.005, String(lineOp))
  await setRange(page, 'bg-finish-grain-strength', 200)
  await page.waitForTimeout(300)
  const grainOp = await page.evaluate(() => {
    const f = window.__frame()
    const svg = f && Array.from(f.querySelectorAll('svg')).find((s) => s.querySelector('feTurbulence') && s.style.mixBlendMode === 'overlay' && s.style.width === '100%')
    return svg ? svg.style.opacity : null
  })
  ck('grain at 200% draws twice as strong (0.3 to 0.6)', grainOp === '0.6', String(grainOp))
  // The choice is the club's: it goes up with the style.
  const stored = await page.evaluate(() => localStorage.getItem('bs_social_bg_finish'))
  ck('the picks are kept for the next post', /"lines":3/.test(stored || '') && /"dots":0/.test(stored || '') && /"grain":2/.test(stored || ''), String(stored))
  if (SHOTS) await shot(page, `${SHOTS}/finish.png`)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ───────── 390px ─────────
console.log('\n# Phone width')
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const page = await ctx.newPage()
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort())
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    if (/\/auth\/me/.test(url)) return route.fulfill(json(ME))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/players|sponsors|templates|media/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  await page.addInitScript(() => { localStorage.setItem('bs_social_template', 'C4'); localStorage.setItem('bs_social_bg', 'gradient-custom') })
  await page.goto(`${BASE}/admin/social-post?type=result&template=C4`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(3000)
  // A phone opens the quick post; the texture controls are in the full editor.
  await page.getByRole('button', { name: /full editor/i }).first().click().catch(() => {})
  await page.waitForTimeout(800)
  const row = page.locator('[data-testid="bg-finish-lines"]')
  await reveal(page, row)
  const over = await page.evaluate(() => {
    const ids = ['bg-finish', 'layout-elements']
    return ids.map((id) => { const e = document.querySelector(`[data-testid="${id}"]`); if (!e) return null; const r = e.getBoundingClientRect(); return r.width ? r.right > window.innerWidth + 1 : null })
  })
  ck('the texture controls fit at 390px', over[0] === false, JSON.stringify(over))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
