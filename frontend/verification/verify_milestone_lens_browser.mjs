// The Milestones screen's two "who" filters: age group (Seniors, Juniors...) and
// "Last played", which takes players who have gone quiet off the list.
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_milestone_lens_browser.mjs [baseUrl]
//
// Asserted in Chromium with the API stubbed at the network layer: the age-group
// buttons exist only for groups the club has, picking one filters both tables and
// sends NO new request (the server already sent what the filter needs), "Last
// played" counts seasons back from the club's current one, a player the server
// could not place stays under every setting, the filters combine with search, the
// empty state names the filters, and 390px does not overflow. The control
// (previous commit) fails the filter checks and reports, never crashes.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SHOTS = process.env.SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => { if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) } }

const up = (id, name, groups, season, extra = {}) => ({
  player_id: id, player_name: name, gender: 'male', type: 'runs', category: 'batting',
  current: 950, target: 1000, needed: 50, detail: null,
  ...(groups === undefined ? {} : { age_groups: groups }),
  ...(season === undefined ? {} : { last_played_season: season }),
  ...extra,
})
const base = () => ({
  upcoming: [
    up('p1', 'Senior Sam', ['senior'], 2026),
    up('p2', 'Junior Jo', ['junior'], 2026),
    up('p3', 'Both Bea', ['senior', 'junior'], 2025),
    up('p4', 'Quiet Quentin', ['senior'], 2023),
    up('p5', 'Unplaced Una'),            // the server could not place her: no groups, no season
  ],
  achieved: [
    { player_id: 'p6', player_name: 'Veteran Vic', gender: 'male', type: 'matches', category: 'matches', milestone_value: 100, achieved_at: '2019-03-03', detail: null, age_groups: ['senior'], last_played_season: 2019 },
    { player_id: 'p2', player_name: 'Junior Jo', gender: 'male', type: 'runs', category: 'batting', milestone_value: 500, achieved_at: '2026-10-03', detail: null, age_groups: ['junior'], last_played_season: 2026 },
  ],
  lens: { current_season: 2026, age_groups: ['senior', 'junior'] },
  scheme: { runs_step: 1000, wickets_step: 100, matches_step: 50, catches_step: 50 },
  scheme_options: { runs_steps: [250, 500, 1000], wickets_steps: [25, 50, 100], matches_steps: [25, 50, 100], catches_steps: [25, 50, 100] },
  step_limits: { runs: { min: 100, max: 10000, multiple: 25 }, wickets: { min: 10, max: 1000, multiple: 5 }, matches: { min: 10, max: 500, multiple: 5 }, catches: { min: 10, max: 500, multiple: 5 } },
  grade_schemes: [],
})

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
async function open(viewport, report = base()) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const reads = []
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    if (/\/auth\/me/.test(url)) return route.fulfill(json({ id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'kalamunda', entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' } }))
    if (/\/club-admin\/milestones$/.test(url)) { reads.push(url); return route.fulfill(json(report)) }
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json({ id: 'org-1', name: 'Kalamunda CC', slug: 'kalamunda', theme_config: null }))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'domcontentloaded' })
  await page.getByText('Milestones In Reach').first().waitFor({ timeout: 30000 }).catch(() => {})
  return { ctx, page, reads, errors }
}
// Reads that report absence instead of throwing.
const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }
const names = async (page) => page.locator('table tbody tr td:first-child').allInnerTexts().catch(() => [])
const has = (list, n) => list.some((t) => t.includes(n))
const group = (page, label) => page.getByRole('group', { name: 'Age group' }).getByRole('button', { name: label, exact: true })
const since = (page) => page.getByLabel('Since last played')
const pick = async (loc, v) => { try { await loc.selectOption(v, { timeout: 2500 }); return true } catch { return false } }

{
  const { ctx, page, reads, errors } = await open({ width: 1400, height: 1000 })
  const all = await names(page)
  ck('to begin with every upcoming player is listed', ['Senior Sam', 'Junior Jo', 'Both Bea', 'Quiet Quentin', 'Unplaced Una'].every((n) => has(all, n)), JSON.stringify(all))
  ck('an age group control is offered (the club has two groups)', await seen(page.getByRole('group', { name: 'Age group' })))
  ck('…with All, Seniors and Juniors', (await seen(group(page, 'ALL'))) && (await seen(group(page, 'SENIORS'))) && (await seen(group(page, 'JUNIORS'))))
  ck('…and no Masters button, since the club has none', !(await seen(group(page, 'MASTERS'))))
  ck('a "Last played" control is offered', await seen(since(page)))
  const readsBefore = reads.length

  await press(group(page, 'JUNIORS'))
  await page.waitForTimeout(150)
  let now = await names(page)
  ck('Juniors: Junior Jo and Both Bea (a player in both) stay', has(now, 'Junior Jo') && has(now, 'Both Bea'), JSON.stringify(now))
  ck('Juniors: Senior Sam and Quiet Quentin go', !has(now, 'Senior Sam') && !has(now, 'Quiet Quentin'), JSON.stringify(now))
  ck('Juniors: a player the server could not place stays', has(now, 'Unplaced Una'), JSON.stringify(now))
  ck('Juniors: the achieved table filters too (Veteran Vic goes, Junior Jo stays)', !(await seen(page.getByText('Veteran Vic'))) && has(now, 'Junior Jo'))
  ck('picking an age group sends no new request', reads.length === readsBefore, `${readsBefore} -> ${reads.length}`)

  await press(group(page, 'SENIORS'))
  await page.waitForTimeout(150)
  now = await names(page)
  ck('Seniors: Junior Jo goes, Senior Sam and Both Bea stay', !has(now, 'Junior Jo') && has(now, 'Senior Sam') && has(now, 'Both Bea'), JSON.stringify(now))
  await press(group(page, 'ALL'))

  // The club is in season 2026. "Last 2 seasons" keeps 2025 and 2026.
  ck('"Last 2 seasons" is a choice', await pick(since(page), '2'))
  await page.waitForTimeout(150)
  now = await names(page)
  ck('Last 2 seasons: Quiet Quentin (last played 2023) goes', !has(now, 'Quiet Quentin'), JSON.stringify(now))
  ck('…Both Bea (2025) and Senior Sam (2026) stay', has(now, 'Both Bea') && has(now, 'Senior Sam'))
  ck('…and the unplaced player stays: no season means no basis to hide her', has(now, 'Unplaced Una'))
  ck('…Veteran Vic (achieved, last played 2019) goes from the achieved table', !(await seen(page.getByText('Veteran Vic'))))

  await pick(since(page), '1')
  await page.waitForTimeout(150)
  now = await names(page)
  ck('This season: Both Bea (2025) goes too', !has(now, 'Both Bea') && has(now, 'Senior Sam') && has(now, 'Junior Jo'), JSON.stringify(now))

  // Combined with Juniors and the search box.
  await press(group(page, 'JUNIORS'))
  await page.getByPlaceholder('Search player...').fill('Una').catch(() => {})
  await page.waitForTimeout(150)
  now = await names(page)
  ck('filters combine with search: Juniors + this season + "Una" leaves Una', has(now, 'Unplaced Una') && !has(now, 'Junior Jo'), JSON.stringify(now))
  await page.getByPlaceholder('Search player...').fill('Nobody').catch(() => {})
  await page.waitForTimeout(150)
  ck('an empty result says so', await seen(page.getByText('No upcoming milestones match the current filters.')))

  await page.getByPlaceholder('Search player...').fill('').catch(() => {})
  await pick(since(page), 'any')
  await press(group(page, 'ALL'))
  await page.waitForTimeout(150)
  ck('clearing the filters brings everyone back', (await names(page)).length >= 5)
  ck('no request was sent for any of it', reads.length === readsBefore, `${readsBefore} -> ${reads.length}`)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/lens-desktop.png`, fullPage: true })
  await ctx.close()
}

{
  // A club with only one kind of cricket has nothing to filter between.
  const r = base()
  r.lens = { current_season: 2026, age_groups: ['senior'] }
  const { ctx, page } = await open({ width: 1400, height: 1000 }, r)
  ck('a club with one age group gets no age group control', !(await seen(page.getByRole('group', { name: 'Age group' }))))
  ck('…but still gets "Last played"', await seen(since(page)))
  await ctx.close()
}

{
  // An older server (or a cached payload) with no lens at all must not crash the page.
  const r = base()
  delete r.lens
  r.upcoming.forEach((i) => { delete i.age_groups; delete i.last_played_season })
  r.achieved.forEach((i) => { delete i.age_groups; delete i.last_played_season })
  const { ctx, page, errors } = await open({ width: 1400, height: 1000 }, r)
  ck('a report with no lens still renders every player', (await names(page)).length >= 5)
  await pick(since(page), '1')
  await page.waitForTimeout(150)
  ck('…and "Last played" keeps everyone, there is nothing to judge on', (await names(page)).length >= 5)
  ck('…with no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  const { ctx, page } = await open({ width: 390, height: 900 })
  ck('390px: no horizontal overflow with the filter bar', !(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/lens-390.png`, fullPage: true })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
