// Club feedback round (v9.141.0): Result Classic (grade chip, swap, panel labels, names font,
// club names, no "(0)" balls, abandoned wording, date case), Match Summary (RS9), the
// Fixtures options (vs on every row, club not grade team), RR6 clipping, and the scorecards
// (matchup heading, full how-out, panel clear of the sponsor bar). Drives the real editor in
// Chromium with the API stubbed at the network layer and reads the OFF-SCREEN EXPORT NODE.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_feedback_round_browser.mjs http://127.0.0.1:5199 [/out/dir]
//
// Every check is paired so it can fail: an "absent" check is next to a "present" one. Run it
// against the previous commit (control) and the new behaviour must fail, not crash.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const OUT = process.argv[3] || '/tmp/feedback-round'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
mkdirSync(OUT, { recursive: true })

let pass = 0
let fail = 0
const check = (name, ok, detail = '') => { if (ok) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${detail ? ` :: ${detail}` : ''}`) } }

const SETTINGS = {
  id: 'org-1', name: 'Leeming Spartan Cricket Club', short_name: 'LSCC', slug: 'leeming',
  logo_url: null, primary_color: '#0b1530', accent_color: '#38bdf8', theme_config: null,
}
const NAMES = [['Cooper', 'BOYES'], ['Ethan', 'LEGGE'], ['Liam', 'CHAPMAN'], ['Ben', 'PETKOVICH'], ['Aman', 'BUBALO'], ['Sam', 'MOSUGANTI'], ['Bala', 'KUMAR'], ['Deepak', 'CANAKAPALLI NAGA'], ['Mo', 'MOHAMMED'], ['Gary', 'BASSRAN'], ['Tim', 'FOX'], ['Joe', 'DOE']]
const bat = (i, balls = true) => ({ num: i + 1, first: NAMES[i][0], last: NAMES[i][1], short: `${NAMES[i][0][0]}. ${NAMES[i][1]}`, r: 80 - i * 9, b: balls ? 90 - i * 8 : 0, fours: 2, sixes: 1, out: 'caught', howOut: i === 1 ? 'c C Cecchi b A Ricci' : '', notOut: i === 0, didNotBat: false, role: null })
const bowl = (i) => ({ first: NAMES[i + 3][0], last: NAMES[i + 3][1], short: `${NAMES[i + 3][0][0]}. ${NAMES[i + 3][1]}`, o: '8.0', m: 1, r: 14 + i * 9, w: 4 - i, econ: 2.5 })
const side = (name, short, color, balls, total, wk, startBat, startBowl) => ({
  name, short, color, total, wickets: wk, overs: '40.0', extras: { b: 1, lb: 2, nb: 0, wd: 3, total: 6 }, logo: null,
  batting: Array.from({ length: 11 }, (_, i) => bat((i + startBat) % 12, balls)), bowling: Array.from({ length: 9 }, (_, i) => bowl((i + startBowl) % 9)),
})
const scorecard = (resultText, balls = true) => ({
  meta: { competition: 'SENIOR MEN 7TH GRADE', round: 'ROUND 6', format: 'ONE DAY', overs: 40, venue: 'Trevor Gribble Park', date: '2026-11-07', toss: '', result: resultText, series: '', motm: { first: '', last: '', team: '', line: '' } },
  home: side('LEEMING SPARTAN SEVENTH GRADE', 'LSC', '#e4002b', balls, '180', 2, 0, 0),
  away: side('KARDINYA LAKES SEVENTH GRADE', 'KLC', '#1a4eb8', balls, '178', 10, 5, 3),
})

const FIXTURE_ROWS = [
  { grade: '1ST GRADE', opp: 'JANDAKOT PARK FIRST GRADE', oppClub: 'JANDAKOT PARK CRICKET CLUB', oppMono: 'JPC', ha: 'H', time: '1:00 PM', venue: 'JOHN CONNELL RESERVE', categories: ['senior'] },
  { grade: '5TH GRADE', opp: 'RIVERTON ROSTRATA FIFTH GRADE', oppClub: 'RIVERTON ROSTRATA CRICKET CLUB', oppMono: 'RRC', ha: 'A', time: '1:00 PM', venue: 'RIVERTON RESERVE', categories: ['senior'] },
  { grade: '7TH GRADE', opp: 'MADDINGTON SEVENTH GRADE', oppClub: 'MADDINGTON CRICKET CLUB', oppMono: 'MAD', ha: 'A', time: '1:00 PM', venue: 'HARMONY FIELDS', categories: ['senior'] },
]
const RESULT_ROWS = [
  { grade: 'ONE DAY GRADE 4', opp: 'BALCATTA STIRLING CATS', oppMono: 'BSC', us: '5/164', them: '6/163', outcome: 'W', margin: 'BY 1 WICKET', categories: ['senior'] },
  { grade: 'ONE DAY GRADE 5', opp: 'BASSENDEAN CRICKET CLUB 5TH XI - ALTITUDE PERFORMANCE', oppMono: 'BCC', us: '4/340', them: '66', outcome: 'W', margin: 'BY 274 RUNS', categories: ['senior'] },
  { grade: 'ONE DAY GRADE 3', opp: 'KALAMUNDA 4TH XI - ODONNELL WEEKEND PREMIER SENIOR DIVISION', oppMono: 'KAL', us: '90', them: '4/91', outcome: 'L', margin: 'BY 6 WICKETS', categories: ['senior'] },
  { grade: 'ONE DAY GRADE 6 BLACK', opp: 'GRANEX TRADE WHITFORDS HERITAGE AND DISTRICT CLUB', oppMono: 'GTW', us: '120', them: '3/121', outcome: 'L', margin: 'BY 7 WICKETS', categories: ['senior'] },
  { grade: 'PSWL SOUTH B', opp: 'PIARA WATERS CC WOMEN EXTRA LONG NAME', oppMono: 'PWC', us: '88', them: '2/90', outcome: 'L', margin: 'BY 8 WICKETS', categories: ['senior'] },
]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

async function open(template, { scorecardText = 'LEEMING SPARTAN SEVENTH GRADE WON BY 8 WICKETS', balls = true, init = {} } = {}) {
  if (process.env.ONLY && !process.env.ONLY.split(',').includes(template)) throw new Error('SKIP')
  const ctx = await browser.newContext({ viewport: { width: 2000, height: 2300 }, deviceScaleFactor: Number(process.env.DPR || 1) })
  await ctx.route('**/api/**', async (route) => {
    const url = route.request().url()
    if (/\/auth\/me/.test(url)) return route.fulfill(json({ id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'leeming', entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' } }))
    if (/\/admin\/social\/match-lookup/.test(url)) return route.fulfill(json({ kind: 'match', match_id: 'm1' }))
    if (/\/admin\/social\/scorecard\//.test(url)) return route.fulfill(json(scorecard(scorecardText, balls)))
    if (/\/admin\/social\/fixtures/.test(url)) return route.fulfill(json({ season: '2026/27', club: { name: 'LEEMING SPARTAN CRICKET CLUB', mono: 'LSC', logo: null }, dates: [{ date: '2026-11-07', label: 'SAT 7 NOV', round: 'Round 6', fixtures: FIXTURE_ROWS }] }))
    if (/\/admin\/social\/results/.test(url)) return route.fulfill(json({ season: '2026/27', club: { name: 'APPLECROSS CRICKET CLUB', mono: 'ACC', logo: null }, dates: [{ date: '2026-11-07', label: 'SAT 7 NOV', round: 'Round 4', results: RESULT_ROWS }] }))
    if (/\/admin\/social\/potm\//.test(url)) return route.fulfill(json({ match: {}, players: [] }))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json([]))
    if (/\/organisations(\?|$)/.test(url)) return route.fulfill(json([]))
    if (/images\/sponsors/.test(url)) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="200"><rect width="600" height="200" fill="#fff"/><text x="300" y="120" font-size="64" font-weight="800" text-anchor="middle" fill="#1d6b3a">SPONSOR</text></svg>' })
    if (/post-default/.test(url)) return route.fulfill(json({ sponsor_ids: ['sp1'], source: 'club' }))
    if (/sponsors/.test(url)) return route.fulfill(json([{ id: 'sp1', name: 'Sponsor', tier: 'major', logo_url: 'x' }]))
    return route.fulfill(json({}))
  })
  const page = await ctx.newPage()
  await page.addInitScript(({ template, init, size }) => {
    localStorage.setItem('bs_social_template', template)
    localStorage.setItem('bs_social_post_size', size)
    Object.entries(init).forEach(([k, v]) => localStorage.setItem(k, v))
  }, { template, init, size: process.env.SIZE || 'square' })
  await page.goto(`${BASE}/admin/social-post?template=${template}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  return { ctx, page }
}

// The export node: the post exactly as it is downloaded. Reads text with textContent (CSS
// `uppercase` changes innerText, not textContent).
const exportText = (page) => page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  return holder ? holder.textContent : null
})
const shoot = async (page, file) => {
  await page.evaluate(() => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    h.dataset.shot = '1'; Object.assign(h.style, { left: '0px', top: '0px', position: 'fixed', zIndex: '2147483647' })
  })
  const dims = await page.evaluate(() => { const r = document.querySelector('[data-shot="1"]').firstElementChild.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) } })
  await page.screenshot({ path: `${OUT}/${file}`, clip: { x: 0, y: 0, width: dims.w, height: dims.h } })
  await page.evaluate(() => { const h = document.querySelector('[data-shot="1"]'); Object.assign(h.style, { left: '-9999px', top: '0', position: 'absolute', zIndex: '-1' }); delete h.dataset.shot })
}
const importResult = async (page) => {
  await page.getByPlaceholder(/Match link from play\.cricket/).first().fill('m1')
  await page.getByRole('button', { name: /^(Import|Fetch)$/ }).first().click()
  await page.waitForTimeout(1500)
}
const q = (page, fn, arg) => page.evaluate(fn, arg)
// A control that is absent is a FAIL to report, never a crash (a control run on the old build has none of them).
const tick = async (page, testId, nth = 0) => {
  const box = page.getByTestId(testId).locator('input').nth(nth)
  if (!(await box.count())) return false
  await box.check({ timeout: 5000 }).catch(() => {})
  await page.waitForTimeout(400)
  return true
}
// Each section runs on its own so one that throws is reported and the rest still run.
const section = async (name, fn) => { try { await fn() } catch (e) { if (String(e.message) === 'SKIP') return; fail++; console.log(`FAIL ${name} threw :: ${String(e.message || e).split('\n')[0]}`) } }

// ── C4: Result · Classic ──────────────────────────────────────────────────────
await section('block 1', async () => {
  const { ctx, page } = await open('C4', { balls: false })
  await importResult(page)
  const t = (await exportText(page)) || ''
  check('C4 grade is its own tag beside RESULT', await q(page, () => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    return [...h.querySelectorAll('div')].some((d) => d.children.length === 0 && d.textContent.trim() === 'SENIOR MEN 7TH GRADE')
  }))
  check('C4 small line keeps the round and date', /ROUND 6 · Sat 7 Nov/i.test(t), t.slice(0, 160))
  check('C4 date is "Sat 7 Nov", not capitals', t.includes('Sat 7 Nov') && !t.includes('SAT 7 NOV'))
  check('C4 no "(0)" on batters when there are no balls', !/\(0\)/.test(t))
  check('C4 batters still print a number', /(80|71|62)\*?/.test(t))
  await shoot(page, 'C4-classic.png')
  await ctx.close()
})
await section('block 2', async () => {
  const { ctx, page } = await open('C4', { balls: true })
  await importResult(page)
  const t = (await exportText(page)) || ''
  check('C4 balls print as (n) when there are balls (control for the "(0)" check)', /\(\d+\)/.test(t))
  await ctx.close()
})
await section('block 3', async () => {
  const parts = JSON.stringify({ RESULT: { c4TeamLabel: 'Spartans', c4OppLabel: 'Kardinya' } })
  const { ctx, page } = await open('C4', { init: { bs_social_parts: parts, bs_social_names_font: 'inter', bs_social_short_names: '1' } })
  await importResult(page)
  const t = (await exportText(page)) || ''
  check('C4 your panel label can be Spartans', t.includes('Spartans · TOP PERFORMERS'), t.slice(0, 400))
  check('C4 opposition panel label can be changed', t.includes('Kardinya · TOP PERFORMERS'))
  check('C4 club name drops "Cricket Club" when asked', t.includes('LEEMING SPARTAN') && !t.includes('LEEMING SPARTAN CRICKET CLUB'))
  const font = await q(page, () => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    const root = h.firstElementChild
    return getComputedStyle(root).getPropertyValue('--social-names-font')
  })
  check('C4 names and scores font follows the picker', /Inter/.test(font), font)
  await shoot(page, 'C4-options.png')
  await ctx.close()
})
await section('block 4', async () => {
  const { ctx, page } = await open('C4')
  await importResult(page)
  const tagLeft = () => q(page, () => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    const tag = [...h.querySelectorAll('div')].find((d) => d.children.length === 0 && d.textContent.trim() === 'RESULT')
    return Math.round(tag.getBoundingClientRect().left - h.firstElementChild.getBoundingClientRect().left)
  })
  const before = await tagLeft()
  const ticked = await tick(page, 'result-swap')
  check('C4 has a swap-sides control', ticked)
  const after = await tagLeft()
  check('C4 swap moves RESULT from the left to the right', before < 300 && after > 500, `${before} -> ${after}`)
  await shoot(page, 'C4-swapped.png')
  await ctx.close()
})
for (const [label, text, want] of [
  ['abandoned', 'MATCH ABANDONED', 'MATCH ABANDONED'],
  ['abandoned (rain)', 'MATCH ABANDONED DUE TO RAIN', 'ABANDONED DUE TO WET WEATHER'],
  ['no result', 'NO RESULT', 'NO RESULT'],
  ['tie', 'MATCH TIED', 'MATCH TIED'],
]) {
  await section(`abandoned ${label}`, async () => {
  const s = await open('C4', { scorecardText: text })
  await importResult(s.page)
  const tt = (await exportText(s.page)) || ''
  check(`C4 ${label} reads "${want}"`, tt.includes(want), tt.slice(-200))
  if (label === 'abandoned (rain)') check('C4 abandoned is not printed as a tie', !tt.includes('MATCH TIED'))
  await s.ctx.close()
  })
}

// ── RS9: Match Summary ────────────────────────────────────────────────────────
await section('block 5', async () => {
  const { ctx, page } = await open('RS9')
  await importResult(page)
  const t = (await exportText(page)) || ''
  check('RS9 prints the heading and both sides', t.includes('MATCH SUMMARY') && /LEEMING SPARTAN/.test(t) && /KARDINYA LAKES/.test(t))
  check('RS9 bowlers sit under the batters they bowled to (column names the other side)', /KL BOWLING/.test(t) && /LS BOWLING/.test(t), t.slice(0, 500))
  check('RS9 prints the result line', /WIN BY 8 WICKETS|WIN\s*BY|WIN/.test(t))
  await shoot(page, 'RS9-summary.png')
  await ctx.close()
})

// ── Fixtures ──────────────────────────────────────────────────────────────────
await section('block 6', async () => {
  const { ctx, page } = await open('FX1')
  await page.getByRole('button', { name: /Pull latest round|Pull/i }).first().click().catch(() => {})
  await page.waitForTimeout(1500)
  let t = (await exportText(page)) || ''
  check('FX1 control: away games show "@" by default', t.includes('@'), t.slice(0, 200))
  check('FX1 has the round options', await tick(page, 'round-opts', 0))
  t = (await exportText(page)) || ''
  check('FX1 "vs on every row" removes the "@"', !t.includes('@') && (t.match(/VS/g) || []).length >= 3, `VS x${(t.match(/VS/g) || []).length}`)
  check('FX1 control: the team name still carries its grade before the tick', /MADDINGTON SEVENTH GRADE/.test(t))
  await tick(page, 'round-opts', 1)
  t = (await exportText(page)) || ''
  check('FX1 club only shows the club, not the grade team', /MADDINGTON CRICKET CLUB/.test(t) && !/SEVENTH GRADE/.test(t), t.slice(0, 300))
  await shoot(page, 'FX1-options.png')
  await ctx.close()
})

// ── RR6: Win/Loss Split ───────────────────────────────────────────────────────
await section('block 7', async () => {
  const { ctx, page } = await open('RR6')
  await page.getByRole('button', { name: /Pull latest round|Pull/i }).first().click().catch(() => {})
  await page.waitForTimeout(1500)
  const geo = await q(page, () => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    const root = h.firstElementChild
    const rr = root.getBoundingClientRect()
    // The WON and LOST column panels themselves (the header word's grandparent), against the
    // post's own edge: a column pushed past the canvas shows here even though the post clips it.
    let worst = -Infinity
    for (const el of root.querySelectorAll('span')) {
      if (!['WON', 'LOST'].includes(el.textContent.trim()) || el.children.length) continue
      const panel = el.parentElement && el.parentElement.parentElement
      if (panel && panel.getBoundingClientRect().right - rr.right > worst) worst = panel.getBoundingClientRect().right - rr.right
    }
    const text = root.textContent
    return { overRight: Math.round(worst), hasLost: /LOST/.test(text), width: Math.round(rr.width) }
  })
  check('RR6 the LOST column stays inside the canvas', geo.hasLost && Number.isFinite(geo.overRight) && geo.overRight <= 0, JSON.stringify(geo))
  await shoot(page, 'RR6-split.png')
  await ctx.close()
})

// ── Scorecards ────────────────────────────────────────────────────────────────
for (const id of ['SC1', 'SC2', 'SC3']) {
  await section('loop 8', async () => {
  const { ctx, page } = await open(id)
  await page.getByPlaceholder(/Match link from play\.cricket/).first().fill('m1')
  await page.getByRole('button', { name: /^(Import|Fetch)$/ }).first().click()
  await page.waitForTimeout(1500)
  await page.getByRole('button', { name: /2 Instagram squares/i }).first().click()
  await page.waitForTimeout(900)
  const t = (await exportText(page)) || ''
  check(`${id} full how-out reads "c C Cecchi b A Ricci"`, t.includes('c C Cecchi b A Ricci'))
  check(`${id} the matchup heading names both clubs`, await q(page, () => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    return [...h.querySelectorAll('[data-testid="sc-matchup"]')].every((m) => /LEEMING SPARTAN/.test(m.textContent) && /KARDINYA LAKES/.test(m.textContent)) && h.querySelectorAll('[data-testid="sc-matchup"]').length === 2
  }))
  const gap = await q(page, () => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    const out = []
    for (const pg of h.children) {
      const foot = [...pg.querySelectorAll('div')].find((d) => d.style.position === 'absolute' && d.style.bottom === '16px' && d.style.height === '56px')
      const leaves = [...pg.querySelectorAll('*')].filter((e) => !e.children.length && e.textContent.trim() && !foot.contains(e))
      const lowest = Math.max(...leaves.map((r) => r.getBoundingClientRect().bottom))
      out.push(Math.round(foot.getBoundingClientRect().top - lowest))
    }
    return out
  })
  check(`${id} no row runs under the sponsor bar`, gap.length === 2 && gap.every((g) => g >= 0), JSON.stringify(gap))
  await shoot(page, `${id}-square.png`)
  await ctx.close()
  })
}

// ── Export under browser zoom (EXPORT=1 DPR=1.25): the downloaded PNG must keep every name ──
if (process.env.EXPORT) {
  await section('export', async () => {
    const { ctx, page } = await open('C4')
    await importResult(page)
    const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), page.getByRole('button', { name: /DOWNLOAD PNG/ }).first().click()])
    await dl.saveAs(`${OUT}/C4-export-dpr${process.env.DPR || 1}.png`)
    console.log(`saved ${OUT}/C4-export-dpr${process.env.DPR || 1}.png`)
    await ctx.close()
  })
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
