// Shoots SC1 to SC3 as the wide post and as the two Instagram squares, with a
// full scorecard (12 batters incl. did-not-bat, 6 bowlers, long names), and lists
// every element whose text is clipped (an overflow:hidden box with more content
// than it can show).
//
//   npx vite --port 5199 &
//   BASE=http://127.0.0.1:5199 node frontend/verification/shoot_scorecards.mjs /tmp/sc [SC1 SC2 SC3]
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const OUT = process.argv[2] || '/tmp/sc'
const IDS = process.argv.slice(3).length ? process.argv.slice(3) : ['SC1', 'SC2', 'SC3']
const BASE = process.env.BASE || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
mkdirSync(OUT, { recursive: true })

const SETTINGS = {
  id: 'org-1', name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'applecross',
  logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null,
}
const NAMES = [
  ['Dinesh', 'DIKKUMBURA'], ['Hettiarachchige', 'KUMARASIRI'], ['Matthew', 'EDWARDS'], ['Will', 'DAGG'],
  ['Pasindu', 'ACHARIGE'], ['Parker', 'COWELL'], ['Joel', 'DAVIES'], ['James', 'BIRBECK'],
  ['Tom', 'FOX-DEAN'], ['David', 'STOPFORTH'], ['Sean', 'DUNCANSON'], ['Sheamus', 'BYRNE'],
]
const bat = (i, did = false) => ({
  num: i + 1, first: NAMES[i][0], last: NAMES[i][1], r: did ? 0 : 10 + i * 7, b: did ? 0 : 12 + i * 5,
  fours: i % 4, sixes: i % 3, out: i % 2 ? 'c Hettiarachchige KUMARASIRI b Stopforth' : 'lbw b Duncanson',
  notOut: i === 0, didNotBat: did, role: i === 2 ? 'C' : i === 5 ? 'WK' : '',
})
const bowl = (i) => ({ first: NAMES[i + 4][0], last: NAMES[i + 4][1], o: 4, m: i % 2, r: 20 + i * 4, w: i % 4, econ: (20 + i * 4) / 4 })
const side = (name, short, color, dnb) => ({
  name, short, color, total: 167, wickets: 6, overs: '19.4', extras: { b: 1, lb: 3, nb: 0, wd: 5, total: 9 },
  batting: Array.from({ length: 12 }, (_, i) => bat(i, i >= 12 - dnb)), bowling: Array.from({ length: 6 }, (_, i) => bowl(i)),
})
const SCORECARD = {
  meta: {
    competition: 'T20 DIV 1', round: 'ROUND 1', format: 'T20', overs: 20, venue: 'Harold Rossiter Park',
    date: 'SAT 3 OCT', toss: 'Applecross won the toss and elected to bat', result: 'APPLECROSS CRICKET CLUB WON BY 10 WICKETS', series: 'SEASON 2026/27',
    motm: { first: 'Matthew', last: 'EDWARDS', team: 'ACC', line: '64* (34) · 1/18' },
  },
  home: side('Applecross Cricket Club', 'ACC', '#e4002b', 1),
  away: side('CVPCC T20 Division 1', 'CTD', '#1a4eb8', 3),
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
const ctx = await browser.newContext({ viewport: { width: 2000, height: 2300 } })
const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
await ctx.route('**/api/**', async (route) => {
  const url = route.request().url()
  if (/\/auth\/me/.test(url)) return route.fulfill(json({
    id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross',
    entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
  }))
  if (/\/admin\/social\/match-lookup/.test(url)) return route.fulfill(json({ kind: 'match', match_id: 'm1' }))
  if (/\/admin\/social\/scorecard\//.test(url)) return route.fulfill(json(SCORECARD))
  if (/\/admin\/social\/potm\//.test(url)) return route.fulfill(json({ match: {}, players: [] }))
  if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
  if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
  if (/\/club-admin\/players/.test(url)) return route.fulfill(json([]))
  if (/sponsors/.test(url)) return route.fulfill(json([]))
  return route.fulfill(json({}))
})
const page = await ctx.newPage()

const clipped = () => page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  if (!holder) return { pages: 0, hits: [] }
  const hits = []
  for (const pg of holder.children) {
    for (const el of pg.querySelectorAll('*')) {
      const cs = getComputedStyle(el)
      const hides = cs.overflow === 'hidden' || cs.overflowX === 'hidden' || cs.overflowY === 'hidden'
      if (!hides || !el.textContent.trim()) continue
      const x = el.scrollWidth - el.clientWidth
      const y = el.scrollHeight - el.clientHeight
      if (x > 1 || y > 1) hits.push({ text: el.textContent.trim().slice(0, 40), x, y, w: el.clientWidth, h: el.clientHeight })
    }
  }
  return { pages: holder.children.length, hits }
})

for (const id of IDS) {
  await page.addInitScript((tpl) => { localStorage.setItem('bs_social_template', tpl); localStorage.setItem('bs_social_post_size', 'square') }, id)
  await page.goto(`${BASE}/admin/social-post?template=${id}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 20000 })
  await page.getByPlaceholder(/Match link from play\.cricket/).fill('m1')
  await page.getByRole('button', { name: 'Import' }).click()
  await page.waitForTimeout(900)
  for (const layout of ['wide', 'squares']) {
    await page.getByRole('button', { name: layout === 'wide' ? 'One wide post' : '2 Instagram squares' }).click()
    await page.waitForTimeout(500)
    const r = await clipped()
    console.log(`${id} ${layout}: ${r.pages} page(s), ${r.hits.length} clipped`)
    for (const h of r.hits) console.log(`   CLIP "${h.text}" over by ${h.x}px wide, ${h.y}px tall (box ${h.w}x${h.h})`)
    await page.evaluate(() => {
      const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
      h.dataset.shot = '1'; Object.assign(h.style, { left: '0px', top: '0px', position: 'fixed', zIndex: '2147483647' })
    })
    const w = layout === 'wide' ? 1920 : 1080
    for (let i = 0; i < r.pages; i++) {
      await page.screenshot({ path: `${OUT}/${id}-${layout}-${i + 1}.png`, clip: { x: 0, y: i * 1080, width: w, height: 1080 } })
    }
    await page.evaluate(() => {
      const h = document.querySelector('[data-shot="1"]')
      Object.assign(h.style, { left: '-9999px', top: '0', position: 'absolute', zIndex: '-1' }); delete h.dataset.shot
    })
  }
}
await browser.close()
