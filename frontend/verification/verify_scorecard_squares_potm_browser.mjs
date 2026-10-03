// Scorecard "2 Instagram squares" and the scorecard player of the match.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_scorecard_squares_potm_browser.mjs http://127.0.0.1:5199 [outDir]
//
// 1. Each square is drawn at its real 1080x1080 and fills the post: no ancestor
//    scales it (it used to be wrapped in the 1920x1080 scorecard frame and shrunk
//    to 56% in the middle of the canvas).
// 2. Importing a scorecard fills the player of the match from the ranking the
//    Player of Match tab uses, a select offers the others, and typing over the
//    fields still works.
// Run it against the previous commit as the control: every `exists`-style check
// reads through a presence-safe accessor, so a missing control reports FAIL
// rather than crashing the run.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const OUT = process.argv[3] || '/tmp/sc-squares'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
mkdirSync(OUT, { recursive: true })

let failed = 0
const check = (name, ok, detail = '') => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
  if (!ok) failed++
}

const SETTINGS = {
  id: 'org-1', name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'applecross',
  logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null,
}
const bat = (n, last, r, b) => ({ num: n, first: 'A', last, r, b, fours: 1, sixes: 0, out: 'caught', notOut: false, didNotBat: false })
const bowl = (last, w, r) => ({ first: 'B', last, o: 4, m: 0, r, w, econ: r / 4 })
const SCORECARD = {
  meta: {
    competition: 'T20 DIV 1', round: 'ROUND 1', format: 'T20', overs: 20, venue: 'Harold Rossiter Park',
    date: 'SAT 3 OCT', toss: '', result: 'APPLECROSS WON BY 10 WICKETS', series: '',
    motm: { first: '', last: '', team: '', line: '' },
  },
  home: { name: 'Applecross Cricket Club', short: 'ACC', total: 121, wickets: 0, overs: '14.2', extras: { b: 0, lb: 1, nb: 0, wd: 2 }, batting: [bat(1, 'EDWARDS', 64, 34), bat(2, 'DAGG', 47, 26)], bowling: [bowl('SINGH', 0, 20)] },
  away: { name: 'CVPCC T20 Division 1', short: 'CTD', total: 120, wickets: 7, overs: '20', extras: { b: 0, lb: 0, nb: 0, wd: 4 }, batting: [bat(1, 'SINGH', 37, 49), bat(2, 'ASIF', 18, 13)], bowling: [bowl('HOLLIWAY', 0, 7)] },
}
const POTM = {
  match: {},
  players: [
    { pid: 'x1', first: 'Matthew', last: 'Edwards', short: 'M. EDWARDS', batting: { r: 64, b: 34, notOut: true, sr: 188.2 }, bowling: null, fielding: null },
    { pid: 'x2', first: 'William', last: 'Dagg', short: 'W. DAGG', batting: { r: 47, b: 26, notOut: true, sr: 180.7 }, bowling: { w: 1, r: 18, o: 3 }, fielding: null },
  ],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
const ctx = await browser.newContext({ viewport: { width: 1600, height: 2300 } })
const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
const calls = []
await ctx.route('**/api/**', async (route) => {
  const url = route.request().url()
  calls.push(url)
  if (/\/auth\/me/.test(url)) return route.fulfill(json({
    id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross',
    entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
  }))
  if (/\/admin\/social\/match-lookup/.test(url)) return route.fulfill(json({ kind: 'match', match_id: 'm1' }))
  if (/\/admin\/social\/scorecard\//.test(url)) return route.fulfill(json(SCORECARD))
  if (/\/admin\/social\/potm\//.test(url)) return route.fulfill(json(POTM))
  if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
  if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
  if (/\/club-admin\/players/.test(url)) return route.fulfill(json([]))
  if (/sponsors/.test(url)) return route.fulfill(json([]))
  return route.fulfill(json({}))
})

const page = await ctx.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))
await page.addInitScript(() => {
  localStorage.setItem('bs_social_template', 'SC1')
  localStorage.setItem('bs_social_post_size', 'square')
})
await page.goto(`${BASE}/admin/social-post?template=SC1`, { waitUntil: 'domcontentloaded' })
await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 20000 })

// ── 1. The squares ──────────────────────────────────────────────────────────
await page.getByRole('button', { name: '2 Instagram squares' }).click()
await page.waitForTimeout(500)

const measure = () => page.evaluate(() => {
  // One off-screen holder at left -9999px; each page of the post is a child.
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  if (!holder) return []
  return [...holder.children].map((pg) => {
    const r = pg.getBoundingClientRect()
    // Any element inside carrying a scale transform means something shrank the post.
    const scaledEls = [...pg.querySelectorAll('*')].filter((e) => /scale\(/.test(e.style.transform || ''))
    // A shrunk post is a BIG element scaled below 1; a small decorative one is not.
    const scaled = scaledEls.filter((e) => { const m = (e.style.transform || '').match(/scale\(([\d.]+)/); return m && +m[1] < 0.99 && e.getBoundingClientRect().width > 400 }).length
    // How far down the post the last real content reaches.
    let lowest = 0
    for (const e of pg.querySelectorAll('*')) {
      const b = e.getBoundingClientRect()
      if (b.height > 0 && b.height < r.height * 0.9) lowest = Math.max(lowest, b.bottom - r.top)
    }
    return { w: Math.round(r.width), h: Math.round(r.height), scaled, lowest: Math.round(lowest) }
  })
})
const pages = await measure()
check('two export pages for the split', pages.length === 2, JSON.stringify(pages.map((p) => `${p.w}x${p.h}`)))
check('each square is 1080x1080', pages.length === 2 && pages.every((p) => p.w === 1080 && p.h === 1080))
check('nothing scales the square down inside the post', pages.length === 2 && pages.every((p) => p.scaled === 0), `scale transforms: ${pages.map((p) => p.scaled)}`)
check('content reaches the foot of the square', pages.length === 2 && pages.every((p) => p.lowest > 1000), `lowest content y: ${pages.map((p) => p.lowest)}`)

// Shoot both squares from the export node (moved on screen first).
await page.evaluate(() => {
  const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  if (!h) return
  h.dataset.shot = '1'
  Object.assign(h.style, { left: '0px', top: '0px', position: 'fixed', zIndex: '2147483647' })
})
for (let i = 0; i < pages.length; i++) {
  await page.screenshot({ path: `${OUT}/square-${i + 1}.png`, clip: { x: 0, y: i * 1080, width: 1080, height: 1080 } })
}
await page.evaluate(() => {
  const h = document.querySelector('[data-shot="1"]')
  if (!h) return
  Object.assign(h.style, { left: '-9999px', top: '0', position: 'absolute', zIndex: '-1' })
  delete h.dataset.shot
})

// ── 2. Player of the match ──────────────────────────────────────────────────
const lastField = page.getByPlaceholder('NAME', { exact: true })
const val = async (loc) => ((await loc.count()) ? loc.first().inputValue() : null)
const before = await val(lastField)

await page.getByPlaceholder(/Match link from play\.cricket/).fill('m1')
await page.getByRole('button', { name: 'Import' }).click()
await page.waitForTimeout(900)

const potmCall = calls.some((u) => /\/admin\/social\/potm\/m1/.test(u))
check('import asks for the player-of-the-match ranking', potmCall)
check('MOTM surname is filled from the top ranked player', (await val(lastField)) === 'Edwards', `was ${JSON.stringify(before)}, now ${JSON.stringify(await val(lastField))}`)
const lineField = page.getByPlaceholder('87 (54) · 2/22', { exact: true })
check('MOTM line carries the figures', (await val(lineField)) === '64* (34)', JSON.stringify(await val(lineField)))

const sel = page.locator('select').filter({ has: page.locator('option', { hasText: 'M. EDWARDS' }) })
check('a select offers the ranked players', (await sel.count()) === 1 && (await sel.locator('option').count()) === 2)
if (await sel.count()) {
  await sel.selectOption('1')
  await page.waitForTimeout(250)
  check('choosing another player rewrites the MOTM fields', (await val(lastField)) === 'Dagg' && (await val(lineField)) === '47* (26) · 1/18', `${await val(lastField)} / ${await val(lineField)}`)
}
await lastField.fill('Someone Else')
await page.waitForTimeout(150)
check('typing over the surname still works', (await val(lastField)) === 'Someone Else')
if (await sel.count()) check('the select says it was typed by hand', (await sel.inputValue()) === '-1')

// The POTM shows on the post itself.
await page.getByRole('button', { name: '2 Instagram squares' }).click()
await page.waitForTimeout(300)
const onPost = await page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  return holder ? holder.innerText : ''
})
check('the player of the match is printed on the square', /PLAYER OF THE MATCH/i.test(onPost) && /Someone Else/i.test(onPost))

check('no page errors', errors.length === 0, errors[0] || '')
await browser.close()
console.log(failed ? `\n${failed} check(s) failed` : '\nall checks passed')
process.exit(failed ? 1 : 0)
