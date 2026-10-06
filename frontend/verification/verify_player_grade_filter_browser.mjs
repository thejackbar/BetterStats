// Drives the real public player profile in Chromium with the API stubbed at the
// network layer: the Grade filter.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_player_grade_filter_browser.mjs [baseUrl]
//
// A person on a player's profile can narrow it to one of the club's grades, and the
// list is the one Manage Grades produces (the club's rename, in the club's own
// reading order, one entry per grade). What is asserted here is what is on the
// WIRE: the exact query each profile endpoint receives, and what the control
// looks like on a phone.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS_DIR || ''

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const PID = 'aaaaaaaa-0000-0000-0000-0000000000aa'
const ORG = 'bbbbbbbb-0000-0000-0000-0000000000bb'
const SEASON = 'dddddddd-0000-0000-0000-0000000000dd'

const STATS = {
  player: { id: PID, name: 'Wilton, Rob', display_name: 'Wilton, Rob',
            organisation_id: ORG, claimed: false, photo_url: null,
            is_overseas: false, overseas_country: null },
  career_batting: { player_id: PID, name: 'Wilton, Rob', organisation_id: ORG,
                    innings: 20, total_runs: 600, high_score: 96, average: 31.2,
                    strike_rate: 71.4, fifties: 8, hundreds: 0, ducks: 4,
                    total_fours: 120, total_sixes: 9, games: 20 },
  career_bowling: null, career_fielding: null,
  batting_innings: [], bowling_spells: [],
  grade_scope: { categories: [], excluded_categories: [], formats: null,
                 competitions: null, competition_names: [], grades: null,
                 active: false, category_active: false, format_active: false,
                 competition_active: false, grade_active: false,
                 available: ['senior'], available_competitions: [], auto_shown: false },
}

// In the SERVER's order, which is not the club's: Premier is the one the club
// put first, and two grades it has not placed carry no order.
const GRADES = [
  { name: 'B grade', display_order: 1 },
  { name: 'C grade', display_order: null },
  { name: 'Division 1, North', display_order: null },
  { name: 'Premier', display_order: 0 },
]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ grades = GRADES, width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = []
  const wire = []   // every profile request: { path, search }
  const gradeLists = []
  page.on('pageerror', (e) => errors.push(String(e)))
  // A regex, not a glob: `**` does not cross a `?`, so a glob loses
  // `/stats?grades=…` to the catch-all.
  await page.route(/\/api\//, async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json',
                                           body: JSON.stringify(body) })
    if (/\/players\/[^/]+\//.test(path + '/') && path.includes(PID)) {
      wire.push({ path: path.replace(`/players/${PID}`, '') || '/stats', search: url.search })
    }
    if (/\/players\/[^/]+\/stats$/.test(path)) return json(STATS)
    if (/^\/auth\/me/.test(path)) return route.fulfill({ status: 401, body: '{}' })
    if (/\/organisations\/[^/]+\/seasons$/.test(path)) {
      return json([{ id: SEASON, name: 'Summer 2025/26', year: 2025 }])
    }
    if (/\/organisations\/[^/]+\/grades$/.test(path)) {
      gradeLists.push(url.search)
      return json(grades)
    }
    if (/\/grade-categories$/.test(path)) {
      return json({ available: ['senior'], default: ['senior'],
                    available_formats: [], available_competitions: [] })
    }
    // The profile fans out to ~20 endpoints and most of them return a LIST; a
    // stub answering `{}` everywhere takes the page down on the first
    // "x is not iterable", and a broken page measures nothing.
    const obj = /team-breakdown|captain-stats|self-serve|usage/.test(path)
    return route.fulfill({ status: 200, contentType: 'application/json',
                           body: obj ? '{}' : '[]' })
  })
  await page.goto(`${BASE}/players/${PID}`, { waitUntil: 'domcontentloaded' })
  // waitUntil networkidle never settles on this app (heartbeat beacon): wait for
  // the element instead.
  await page.waitForSelector('text=SEASON', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(400)
  return { page, ctx, errors, wire, gradeLists }
}

const gradeSelect = (page) => page.locator('select[aria-label="Grade"]')
// Short timeout and a swallowed failure: a CONTROL RUN has no Grade select, and
// must REPORT every check below rather than hang and die saying nothing.
const pick = (page, value) => gradeSelect(page).selectOption(value, { timeout: 1500 }).catch(() => {})
const pickedValue = (page) => gradeSelect(page).inputValue({ timeout: 1500 }).catch(() => null)
const optionTexts = (page) => gradeSelect(page).locator('option').allTextContents()
const lastOf = (wire, path) => [...wire].reverse().find(w => w.path === path)
const gradesOn = (w) => w ? new URLSearchParams(w.search).getAll('grades') : null

try {
  console.log('\n-- the control is drawn from the club\'s own grade list --')
  {
    const { page, ctx, errors, wire } = await open()
    ck('a Grade select is on the filter bar', await gradeSelect(page).count() === 1)
    const opts = await optionTexts(page)
    ck('it opens on All Grades', opts[0] === 'All Grades', JSON.stringify(opts))
    ck("grades the club has placed come first, in ITS order, then the rest in the server's",
       JSON.stringify(opts.slice(1)) === JSON.stringify(
         ['Premier', 'B grade', 'C grade', 'Division 1, North']), JSON.stringify(opts))
    ck('no grade is on the wire until one is picked',
       wire.length > 0 && wire.every(w => !new URLSearchParams(w.search).has('grades')),
       JSON.stringify(wire.map(w => w.search)))
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- picking a grade reaches every request the profile makes --')
  {
    const { page, ctx, errors, wire } = await open()
    const before = wire.length
    await pick(page, 'Premier')
    await page.waitForTimeout(900)
    const after = wire.slice(before)
    ck('the career stats request carries grades=Premier exactly',
       JSON.stringify(gradesOn(lastOf(after, '/stats'))) === '["Premier"]',
       JSON.stringify(after.map(w => `${w.path}${w.search}`)))
    for (const p of ['/by-grade', '/by-position', '/dismissals', '/seasons', '/team-breakdown',
                     '/captain-stats', '/by-venue', '/by-opposition']) {
      ck(`${p} carries it too`,
         JSON.stringify(gradesOn(lastOf(after, p))) === '["Premier"]',
         JSON.stringify(lastOf(after, p)))
    }
    ck('and the select shows the pick', await pickedValue(page) === 'Premier')

    await pick(page, 'Division 1, North')
    await page.waitForTimeout(900)
    const comma = lastOf(wire, '/stats')
    ck('a grade with a comma in its name is ONE value, not two',
       JSON.stringify(gradesOn(comma)) === '["Division 1, North"]', comma?.search)

    const n = wire.length
    await pick(page, '')
    await page.waitForTimeout(900)
    const cleared = wire.slice(n)
    ck('All Grades puts the request back as it was, with no grade on it',
       cleared.length > 0 && cleared.every(w => !new URLSearchParams(w.search).has('grades')),
       JSON.stringify(cleared.map(w => w.search)))
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- the list follows the season --')
  {
    const { page, ctx, gradeLists } = await open()
    ck('first load asks for every grade (no season)', gradeLists[0] === '', JSON.stringify(gradeLists))
    await page.locator('select').first().selectOption(SEASON, { timeout: 1500 }).catch(() => {})
    await page.waitForTimeout(800)
    ck('picking a season asks for that season\'s grades',
       gradeLists.some(s => s === `?season_id=${SEASON}`), JSON.stringify(gradeLists))
    await ctx.close()
  }

  console.log('\n-- a club with one grade has nothing to choose, so no control --')
  {
    const { page, ctx } = await open({ grades: [{ name: 'A grade', display_order: null }] })
    ck('no Grade select', await gradeSelect(page).count() === 0)
    await ctx.close()
  }

  console.log('\n-- the reach notes name the Grade filter --')
  {
    const { page, ctx } = await open()
    await pick(page, 'Premier')
    await page.waitForTimeout(700)
    await page.getByRole('button', { name: /^MILESTONES/ }).first().click().catch(() => {})
    await page.waitForTimeout(400)
    const text = await page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' '))
    ck('Milestones says the Grade filter does not change a career figure',
       /The Grade filter above does not change this/.test(text), text.slice(0, 300))
    await ctx.close()
  }

  console.log('\n-- a phone --')
  {
    const { page, ctx, errors } = await open({ width: 390 })
    await pick(page, 'Division 1, North')
    await page.waitForTimeout(700)
    const m = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth,
      box: (() => { const r = document.querySelector('select[aria-label="Grade"]')?.getBoundingClientRect()
                    return r ? { left: r.left, right: r.right } : null })(),
    }))
    ck('no horizontal scroll at 390px', m.scroll <= m.client, JSON.stringify(m))
    ck('the select sits inside the screen', !!m.box && m.box.left >= 0 && m.box.right <= 390,
       JSON.stringify(m.box))
    if (SHOTS) {
      mkdirSync(SHOTS, { recursive: true })
      await page.screenshot({ path: `${SHOTS}/grade-filter-390.png`, clip: { x: 0, y: 0, width: 390, height: 700 } })
    }
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }
  {
    const { page, ctx } = await open()
    if (SHOTS) {
      await pick(page, 'Premier')
      await page.waitForTimeout(700)
      await page.screenshot({ path: `${SHOTS}/grade-filter-1440.png`, clip: { x: 0, y: 0, width: 1440, height: 520 } })
    }
    await ctx.close()
  }
} finally {
  await browser.close()
}
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
