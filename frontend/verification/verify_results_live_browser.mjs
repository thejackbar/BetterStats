// Drives the real BetterPosts "Results" post in Chromium with the API stubbed at the network layer.
//
//   npx vite build && npx vite preview --port 5198 &
//   node frontend/verification/verify_results_live_browser.mjs [baseUrl]      (SHOTS=dir writes a PNG per layout)
//
// What a build cannot tell you: that the Results pull asks for games in progress by default and sends
// nothing extra once the box is cleared, that the choice is remembered, that a game in play reaches the
// post as an IN PROGRESS row (not a loss) on every results layout, and that the Split layout gives it its
// own column rather than dropping it.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome'
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
const row = (grade, opp, mono, us, them, outcome, margin, extra = {}) => ({
  grade, gradeOrder: 1, opp, oppMono: mono, us, them, outcome, margin, categories: ['senior'],
  topBat: [], topBowl: [], oppTopBat: [], oppTopBowl: [], ...extra,
})
const DONE = [
  row('1ST GRADE', 'RIVALS', 'RIV', '6/188', '184', 'W', 'BY 4 WICKETS'),
  row('2ND GRADE', 'WILLETTON', 'WIL', '176', '9/201', 'L', 'BY 25 RUNS'),
]
const LIVE_ROWS = [
  row('3RD GRADE', 'GOSNELLS', 'GOS', '3/210', '-', 'LIVE', 'IN PROGRESS', { live: true }),
  row('4TH GRADE', 'MELVILLE', 'MEL', '154', '2/60', 'LIVE', 'IN PROGRESS', { live: true }),
]
const resultsFor = (search) => {
  const live = new URLSearchParams(search).get('live') === 'true'
  return { season: '2025/26', club: {}, dates: [{ date: '2026-10-24', label: 'SAT 24 OCT', round: 'Round 5', results: live ? [...DONE, ...LIVE_ROWS] : DONE }] }
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openEditor(query, viewport = { width: 1600, height: 1000 }, init) {
  const ctx = await browser.newContext({ viewport })
  if (init) await ctx.addInitScript(init)
  const page = await ctx.newPage()
  const errors = [], calls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_/.test(m.text())) errors.push(m.text()) })
  const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    if (/\/admin\/social\/results/.test(url)) { calls.push(new URL(url).search); return route.fulfill(json(resultsFor(new URL(url).search))) }
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross',
      entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
    }))
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json([]))
    if (/sponsors/.test(url)) return route.fulfill(json([]))
    if (/selection\/overview/.test(url)) return route.fulfill(json({ fixtures: [] }))
    if (/lineups/.test(url)) return route.fulfill(json({ matches: [] }))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/social-post${query}`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  return { ctx, page, errors, calls }
}
const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }

// The export node: the post as it is downloaded, not the scaled preview.
const postText = (page) => page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  return holder ? holder.innerText.replace(/\s+/g, ' ').toUpperCase() : ''
})
const pickLayout = async (page, name) => {
  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await press(page.getByRole('button', { name: new RegExp(name) }))
  await page.waitForTimeout(150)
  await press(page.getByRole('button', { name: 'Content', exact: true }))
  await page.waitForTimeout(100)
}

// ── 1. The pull and the box ────────────────────────────────────────────────
{
  const { ctx, page, errors, calls } = await openEditor('?type=results')
  const box = page.getByTestId('results-in-play')
  ck('the Results pull offers to include games in progress', await seen(box))
  ck('  ... ticked by default', await page.locator('[data-testid="results-in-play"] input').first().isChecked().catch(() => false))
  await press(page.getByRole('button', { name: 'Pull latest round' }))
  await page.waitForTimeout(500)
  ck('the default pull asks for games in progress', calls.length === 1 && calls[0] === '?live=true', JSON.stringify(calls))

  await press(page.getByRole('button', { name: /Continue to editor/ }))
  await page.waitForTimeout(250)
  const txt = await postText(page)
  ck('the post carries the games in play', /3RD GRADE/.test(txt) && /4TH GRADE/.test(txt), txt.slice(0, 200))
  ck('  ... as IN PROGRESS, with the score so far', /IN PROGRESS/.test(txt) && /3\/210/.test(txt), txt.slice(0, 200))
  ck('  ... and the finished games as they were', /BY 4 WICKETS/.test(txt) && /BY 25 RUNS/.test(txt))

  await press(page.getByRole('button', { name: 'Data', exact: true }))
  await page.waitForTimeout(150)
  await page.locator('[data-testid="results-in-play"] input').first().uncheck()
  await page.waitForTimeout(500)
  ck('clearing the box pulls again without live', calls.length === 2 && calls[1] === '', JSON.stringify(calls))
  await press(page.getByRole('button', { name: /Continue to editor/ }))
  await page.waitForTimeout(250)
  ck('  ... and the games in play are gone from the post', !/IN PROGRESS/.test(await postText(page)))
  ck('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  await ctx.close()
}

// ── 2. The choice is remembered ────────────────────────────────────────────
{
  const { ctx, page } = await openEditor('?type=results', undefined, () => { try { localStorage.setItem('bs_social_results_live', '0') } catch { /* none */ } })
  ck('a club that turned it off finds it off', !(await page.locator('[data-testid="results-in-play"] input').first().isChecked().catch(() => true)))
  const calls = []
  page.on('request', (r) => { if (/admin\/social\/results/.test(r.url())) calls.push(new URL(r.url()).search) })
  await press(page.getByRole('button', { name: 'Pull latest round' }))
  await page.waitForTimeout(400)
  ck('  ... and its pull sends nothing extra', calls.length === 1 && calls[0] === '', JSON.stringify(calls))
  await ctx.close()
}

// ── 3. Every results layout shows a game in play as in play ────────────────
{
  // Wide enough that the editor shows the whole post, so a shot is of the post and not a crop of it.
  const { ctx, page, errors } = await openEditor('?type=results', { width: 2300, height: 1300 })
  await press(page.getByRole('button', { name: 'Pull latest round' }))
  await page.waitForTimeout(500)
  await press(page.getByRole('button', { name: /Continue to editor/ }))
  await page.waitForTimeout(250)
  const LAYOUTS = ['Weekend Wrap', 'Wrap \\+ Leaders', 'W/L Scoreboard', 'Record Strip', 'Headline', 'Board', 'Win/Loss Split']
  for (const name of LAYOUTS) {
    await pickLayout(page, name)
    const txt = await postText(page)
    // The finished 2nd grade loss prints a loss word; the games in play must never print one.
    ck(`${name}: no loss wording against a game in play`, !/(LOST TO|DEF BY|LOST)\s+(GOSNELLS|MELVILLE)/.test(txt.replace(/\s+/g, ' ')), txt.slice(0, 300))
    ck(`${name}: games in play are labelled, not scored as losses`, /IN PROGRESS|LIVE|IN PLAY|LV/.test(txt) && /3RD GRADE/.test(txt) && /4TH GRADE/.test(txt), txt.slice(0, 160))
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name.replace(/[^A-Za-z]+/g, '-')}.png` }).catch(() => {})
  }
  await pickLayout(page, 'Win/Loss Split')
  const cols = await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    return holder ? holder.innerText.toUpperCase() : ''
  })
  ck('Win/Loss Split gives games in play their own column', /IN PLAY/.test(cols) && /WON/.test(cols) && /LOST/.test(cols), cols.slice(0, 200))
  ck('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
