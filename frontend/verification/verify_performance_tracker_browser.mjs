// Drives the Performance Tracker and the Round Review posts inside an
// ASSOCIATION SOCIALS WORKSPACE in Chromium, with the API stubbed at the network
// layer (backend: routers/performance.py, services/performance_round.py,
// services/performance_season.py).
//
//   npx vite build && npx vite preview --port 5199 &
//   A_JSON=a.json B_JSON=b.json SEASON_JSON=season.json [OLD_JSON=old.json] \
//     node frontend/verification/verify_performance_tracker_browser.mjs [baseUrl]
//
// A_JSON and B_JSON are two grades' pulls as the backend returned them for one
// real round (PSWL South A and South B, Round 7, were used), SEASON_JSON the
// season reading of those two grades in that order. OLD_JSON is A_JSON stripped
// to a pull from before crests were stored (no team ids, crests or clubs).
// SHOTS=dir saves screenshots.
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SHOTS = process.env.SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
for (const k of ['A_JSON', 'B_JSON', 'SEASON_JSON']) {
  if (!process.env[k]) { console.log(`Set ${k} (see the header).`); process.exit(2) }
}

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const A = JSON.parse(readFileSync(process.env.A_JSON, 'utf8'))
const B = JSON.parse(readFileSync(process.env.B_JSON, 'utf8'))
const SEASON_RAW = JSON.parse(readFileSync(process.env.SEASON_JSON, 'utf8'))
// One career milestone added by hand: the real round had none, and the page and
// the post must show one when there is.
const CAREER = { pid: 'x1', name: 'Career Keeper', club: SEASON_RAW.competitions[0].players[0].club, club_id: SEASON_RAW.competitions[0].players[0].club_id,
  kind: 'career_matches', stat: 'matches', scope: 'career', mark: 100, value: 100, text: 'Career Keeper played game 100' }
SEASON_RAW.competitions[0].career_milestones = [CAREER]
const LINK_A = 'https://play.cricket.com.au/match/aaaaaaaa-0000-0000-0000-000000000001/a'
const LINK_B = 'https://play.cricket.com.au/match/bbbbbbbb-0000-0000-0000-000000000002/b'
const SETTINGS = { id: 'ws-1', name: 'PSWL South', short_name: 'PSWL', slug: null, workspace_kind: 'association', logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null }
let LIBRARY = []
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC', 'base64')

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

// The season stub answers for whatever grade keys the round holds, in order.
function seasonFor(round) {
  const comps = (round?.data?.competitions || []).filter(c => c.pull && c.pull.kind === 'round')
  return { ...SEASON_RAW, competitions: SEASON_RAW.competitions.slice(0, comps.length).map((b, i) => ({ ...b, key: comps[i].key, name: comps[i].name })) }
}

async function open(path, viewport, store) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const calls = [], errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (body, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/*', async (route) => {
    const req = route.request()
    const url = req.url()
    if (!/\/api\//.test(url)) return route.continue()
    const u = new URL(url)
    calls.push({ method: req.method(), path: u.pathname, search: u.search, body: req.postData() })
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'staff', role: 'super_admin', club_slug: null, club_name: 'PSWL South', workspace_kind: 'association',
      acting_as_club: true, home_club_name: 'BetterCricket', can_switch_clubs: true, entitlements: { modules: ['socials'], status: 'active' },
    }))
    if (u.pathname.endsWith('/admin/performance/pull')) return route.fulfill(json(u.searchParams.get('q') === LINK_B ? B : A))
    if (u.pathname.endsWith('/admin/performance/rounds') && req.method() === 'GET') return route.fulfill(json({ rounds: store.map(({ data, ...r }) => r) }))
    if (u.pathname.endsWith('/admin/performance/rounds') && req.method() === 'POST') {
      const r = { id: `r${store.length + 1}`, round_label: '', round_date: null, data: {} }
      store.unshift(r)
      return route.fulfill(json(r))
    }
    const sm = u.pathname.match(/\/admin\/performance\/rounds\/([^/]+)\/season$/)
    if (sm) return route.fulfill(json(seasonFor(store.find(x => x.id === sm[1]))))
    const m = u.pathname.match(/\/admin\/performance\/rounds\/([^/]+)$/)
    if (m) {
      const r = store.find(x => x.id === m[1])
      if (req.method() === 'PATCH') Object.assign(r, JSON.parse(req.postData() || '{}'))
      return route.fulfill(json(r))
    }
    if (/\/images\/association-crests\//.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    if (/\/admin\/social\/crests/.test(url)) return route.fulfill(json({ crests: LIBRARY }))
    if (/\/admin\/social\/templates|\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json([]))
    if (/sponsors/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
  return { ctx, page, calls, errors }
}

const firstText = async (loc) => ((await loc.count()) ? (await loc.first().innerText()) : '')
const store = []
const topBy = (rows, f) => [...rows].sort(f)[0]
const ALL_BAT = [...A.batting, ...B.batting].sort((a, b) => b.runs - a.runs || (a.balls || 999) - (b.balls || 999))
const ALL_BOWL = [...A.bowling, ...B.bowling].sort((a, b) => b.wickets - a.wickets || a.runs - b.runs)

// ── The tracker ───────────────────────────────────────────────────────────────
let keyA = '', keyB = ''
{
  const { ctx, page, calls, errors } = await open('/admin/performance', { width: 1400, height: 1000 }, store)
  const start = page.getByRole('button', { name: 'Track a round' })
  await start.waitFor({ timeout: 25000 })
  await start.click()
  await page.getByTestId('add-grade').waitFor()
  ck('a new round starts with no grades (no North, South, East)', (await page.locator('[data-testid^="grade-state-"]').count()) === 0 && !(await page.locator('body').innerText()).includes('North'))
  // Add a grade from a link: it reads the round and takes its own name.
  await page.getByLabel('Match link for a new grade').fill(LINK_A)
  await page.getByRole('button', { name: 'Add grade' }).click()
  await page.getByTestId('section-glance').waitFor({ timeout: 8000 })
  const pullA = calls.find(c => c.path.endsWith('/admin/performance/pull'))
  ck('adding a grade pulls its link', pullA && new URLSearchParams(pullA.search).get('q') === LINK_A, pullA?.search)
  await page.waitForTimeout(300)
  ck('the grade takes Cricket Australia\'s name', (await firstText(page.locator('[data-testid^="grade-state-"]'))).startsWith(A.grade), await firstText(page.locator('[data-testid^="grade-state-"]')))
  ck('the round takes its label from the pull', (await page.getByLabel('Round', { exact: true }).inputValue()) === A.round)
  ck('one grade: no grade filter yet', (await page.getByTestId('grade-filter').count()) === 0)
  await page.getByLabel('Match link for a new grade').fill(LINK_B)
  await page.getByRole('button', { name: 'Add grade' }).click()
  await page.getByTestId('grade-filter').waitFor({ timeout: 8000 })
  await page.waitForTimeout(1600)
  const states = await page.locator('[data-testid^="grade-state-"]').allInnerTexts()
  ck('the second grade names itself too', states.length === 2 && states[1].startsWith(B.grade), states.join(' | '))
  keyA = (await page.locator('[data-testid^="grade-state-"]').nth(0).getAttribute('data-testid')).replace('grade-state-', '')
  keyB = (await page.locator('[data-testid^="grade-state-"]').nth(1).getAttribute('data-testid')).replace('grade-state-', '')
  ck('the grade filter offers all grades and each grade', (await page.getByTestId('grade-filter').getByRole('button').allInnerTexts()).join('|') === `All grades|${A.grade}|${B.grade}`)
  // Both grades show, then the filter narrows every section.
  ck('results show both grades', (await page.getByTestId(`results-${keyA}`).count()) === 1 && (await page.getByTestId(`results-${keyB}`).count()) === 1)
  ck('top batting over both grades', (await firstText(page.getByTestId('performers-batting').locator('li'))).includes(ALL_BAT[0].name))
  await page.getByTestId('grade-filter').getByRole('button', { name: B.grade }).click()
  await page.waitForTimeout(300)
  ck('the filter narrows results to one grade', (await page.getByTestId(`results-${keyA}`).count()) === 0 && (await page.getByTestId(`results-${keyB}`).locator('li').count()) === B.results.length)
  ck('and the performers', (await firstText(page.getByTestId('performers-batting').locator('li'))).includes(topBy(B.batting, (a, b) => b.runs - a.runs || (a.balls || 999) - (b.balls || 999)).name))
  await page.getByRole('tab', { name: 'Bowling', exact: true }).click()
  ck('performer tabs switch to bowling', (await firstText(page.getByTestId('performers-bowling').locator('li'))).includes(topBy(B.bowling, (a, b) => b.wickets - a.wickets || a.runs - b.runs).name))
  await page.getByTestId('grade-filter').getByRole('button', { name: 'All grades' }).click()
  await page.waitForTimeout(300)
  ck('back to all grades', (await firstText(page.getByTestId('performers-bowling').locator('li'))).includes(ALL_BOWL[0].name))

  // Season leaderboards: the grades shown, added together.
  await page.getByTestId('leaders-runs').waitFor({ timeout: 8000 })
  const merged = {}
  for (const b of SEASON_RAW.competitions) for (const p of b.players) merged[p.pid] = { name: p.name, runs: (merged[p.pid]?.runs || 0) + p.runs, wk: (merged[p.pid]?.wk || 0) + p.wickets }
  const topRuns = Object.values(merged).sort((a, b) => b.runs - a.runs)[0]
  ck('season runs leader over both grades', (await firstText(page.getByTestId('leaders-runs').locator('li'))).includes(topRuns.name), topRuns.name)
  await page.getByRole('tab', { name: 'Most wickets' }).click()
  const topWk = Object.values(merged).sort((a, b) => b.wk - a.wk)[0]
  ck('leaderboard tabs switch to wickets', (await firstText(page.getByTestId('leaders-wickets').locator('li'))).includes(topWk.name))
  await page.getByTestId('grade-filter').getByRole('button', { name: A.grade }).click()
  await page.waitForTimeout(300)
  const aTopWk = [...SEASON_RAW.competitions[0].players].sort((a, b) => b.wickets - a.wickets || a.bowl_runs - b.bowl_runs)[0]
  ck('leaderboard follows the grade filter', (await firstText(page.getByTestId('leaders-wickets').locator('li'))).includes(aTopWk.name))
  await page.getByTestId('grade-filter').getByRole('button', { name: 'All grades' }).click()

  // Milestones: one tidy row each, with kind and stat toggles.
  const rows = () => page.getByTestId('milestone-rows').locator('li').count()
  const nMatch = A.milestones.length + B.milestones.length
  const nSeason = SEASON_RAW.competitions.reduce((s, b) => s + b.season_milestones.length, 0)
  await page.waitForTimeout(300)
  ck('every milestone listed (match, season, career)', (await rows()) === nMatch + nSeason + 1, `${await rows()} vs ${nMatch + nSeason + 1}`)
  ck('the career milestone shows as a row', (await page.getByTestId('milestone-rows').innerText()).includes('Career Keeper') && (await page.getByTestId('milestone-rows').innerText()).includes('100 games'))
  await page.getByRole('group', { name: 'Milestone kind' }).getByRole('button', { name: /^Season/ }).click()
  ck('turning season off drops exactly the season rows', (await rows()) === nMatch + 1, `${await rows()}`)
  await page.getByRole('group', { name: 'Milestone kind' }).getByRole('button', { name: /^Season/ }).click()
  await page.getByRole('group', { name: 'Milestone stat' }).getByRole('button', { name: /^Games/ }).click()
  ck('turning games off drops the career games row', (await rows()) === nMatch + nSeason)
  await page.getByRole('group', { name: 'Milestone stat' }).getByRole('button', { name: /^Games/ }).click()

  // Sections fold away and stay folded.
  await page.getByTestId('section-results').getByRole('button', { name: /Results/ }).first().click()
  ck('a section folds', (await page.getByTestId(`results-${keyA}`).count()) === 0)
  await page.getByLabel('Notes').fill('Clubrooms reopening Saturday')
  await page.waitForTimeout(1500)
  const patch = calls.filter(c => c.method === 'PATCH').pop()
  const body = patch ? JSON.parse(patch.body) : {}
  ck('autosave keeps both grades with names, links and pulls', (body.data?.competitions || []).map(c => [c.name, c.link, c.pull?.results?.length].join('/')).join('|')
    === `${A.grade}/${LINK_A}/${A.results.length}|${B.grade}/${LINK_B}/${B.results.length}`)
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download' }).click()])
  const txt = readFileSync(await dl.path(), 'utf8')
  ck('download holds both grades, the season leaders, the milestones and the notes', txt.includes(A.grade.toUpperCase()) && txt.includes(B.grade.toUpperCase())
    && txt.includes('SEASON LEADERS') && txt.includes('Career Keeper') && txt.includes('Clubrooms reopening Saturday'))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/tracker.png`, fullPage: true })
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByTestId('section-results').waitFor({ timeout: 15000 })
  await page.waitForTimeout(500)
  ck('a folded section stays folded after a reload', (await page.getByTestId(`results-${keyA}`).count()) === 0 && (await page.getByTestId('section-glance').getByTestId('glance').count()) === 1)
  // Make post from a section: its layout, this round, these grades.
  await page.getByTestId('grade-filter').getByRole('button', { name: B.grade }).click()
  await Promise.all([page.waitForURL(/social-post/), page.getByTestId('post-RV5').click()])
  const u = new URL(page.url())
  ck('a section opens its own post on this round and these grades', u.searchParams.get('template') === 'RV5' && u.searchParams.get('round') === store[0].id && u.searchParams.get('grades') === keyB, page.url())
  ck('tracker: no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── The posts: every section's layout draws from the round ────────────────────
const postText = (page) => page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  return holder ? holder.innerText : ''
})
const MOR_A = A.next_round.fixtures[A.next_round.match_of_round]
const bLadderTop = B.ladder[0].team.toUpperCase()
for (const [id, extra, ok, label] of [
  ['RV1', '', (t) => t.includes('WRAP') && t.includes(ALL_BAT[0].name.toUpperCase()), 'the round wrap leads with the top score'],
  ['RV2', '', (t) => t.includes('TOP SCORES') && t.includes(ALL_BOWL[0].name.toUpperCase()), 'top performers'],
  ['RV3', '', (t) => t.includes('PLAYER OF'), 'player of the round'],
  ['RV4', '', (t) => t.includes('MATCH OF') && t.includes(MOR_A.home.toUpperCase()), 'match of the round'],
  ['RV5', `&grades=${keyB}`, (t) => t.includes('RESULTS') && B.results.every(r => t.includes(r.home.toUpperCase())) && !A.results.some(r => t.includes(r.home.toUpperCase()) && !B.results.some(x => x.home === r.home || x.away === r.home)), 'results, one grade only'],
  ['RV6', '&board=wickets', (t) => t.includes('MOST WICKETS') && t.includes(Object.values((() => { const m = {}; for (const b of SEASON_RAW.competitions) for (const p of b.players) m[p.pid] = { name: p.name, wk: (m[p.pid]?.wk || 0) + p.wickets }; return m })()).sort((a, b) => b.wk - a.wk)[0].name.toUpperCase()), 'season leaders, the board picked'],
  ['RV7', '&scopes=career', (t) => t.includes('MILE') && t.includes('CAREER KEEPER') && t.includes('100 GAMES') && !t.includes('SEASON RUNS'), 'milestones, career only'],
  ['RV8', `&ladder=${keyB}`, (t) => t.includes('LADDER') && t.includes(bLadderTop), "the picked grade's ladder"],
  ['RV9', '', (t) => t.includes('NEXT') && t.includes('MATCH OF THE ROUND') && t.includes(MOR_A.away.toUpperCase()), 'next round fixtures'],
  ['RV9', '', (t) => { const byes = [...A.next_round.fixtures, ...B.next_round.fixtures].filter(f => !f.home || !f.away).length; return !byes || t.includes('BYE') }, 'a bye is named, never a blank side'],
]) {
  const { ctx, page, errors } = await open(`/admin/social-post?template=${id}&round=${store[0].id}${extra}`, { width: 1600, height: 1000 }, store)
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  await page.waitForTimeout(1800)
  const t = await postText(page)
  ck(`${id}: ${label}`, ok(t), t.slice(0, 260).replace(/\n/g, ' '))
  ck(`${id}: no page errors`, errors.length === 0, errors.join(' | '))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${id.toLowerCase()}.png` })
  await ctx.close()
}
{
  // The post's own grade chips narrow it.
  const { ctx, page } = await open(`/admin/social-post?template=RV5&round=${store[0].id}`, { width: 1600, height: 1000 }, store)
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  await page.getByRole('group', { name: 'Grades on the post' }).waitFor({ timeout: 10000 })
  const aOnly = A.results.map(r => r.home.toUpperCase()).find(h => !B.results.some(x => x.home.toUpperCase() === h || x.away.toUpperCase() === h))
  ck('a results post starts with every grade', (await postText(page)).includes(aOnly))
  await page.getByRole('group', { name: 'Grades on the post' }).getByRole('button', { name: A.grade }).click()
  await page.waitForTimeout(500)
  ck('untick a grade and it leaves the post', !(await postText(page)).includes(aOnly))
  await page.getByPlaceholder("Leave blank for the layout's own").first().fill('Round Seven Wrap')
  await page.waitForTimeout(400)
  ck('a typed heading reaches the post', (await postText(page)).includes('ROUND SEVEN WRAP'))
  await ctx.close()
}

// ── Crests come from the crest library as it is now ──────────────────────────
if (process.env.OLD_JSON) {
  const old = JSON.parse(readFileSync(process.env.OLD_JSON, 'utf8'))
  const club = A.clubs[A.batting[0].team_id]
  const kept = `/api/images/association-crests/ws-1/${club.id}?v=7`
  LIBRARY = [
    { caOrgId: club.id, name: club.name, logo: kept },
    { caOrgId: 'someone-else', name: 'Applecross Districts Juniors', logo: '/api/images/association-crests/ws-1/someone-else?v=1' },
  ]
  for (const [label, pull] of [['by club id', A], ['by club name, on a round pulled before crests were stored', old]]) {
    const rs = [{ id: 'p1', round_label: pull.round, round_date: pull.date, data: { competitions: [{ key: 'sa', name: 'South A', link: LINK_A, pull }] } }]
    const { ctx, page, errors } = await open('/admin/social-post?template=RV2&round=p1', { width: 1600, height: 1000 }, rs)
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
    await page.waitForTimeout(1500)
    const srcs = await page.evaluate(() => {
      const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
      return holder ? [...holder.querySelectorAll('img')].map((i) => i.getAttribute('src') || '') : []
    })
    ck(`RV2 top score shows the library crest ${label}`, srcs.some(x => x.endsWith(`${club.id}?v=7`)), srcs.slice(0, 4).join(' | '))
    ck(`RV2 ${label}: no page errors`, errors.length === 0, errors.join(' | '))
    await ctx.close()
    const t = await open('/admin/performance', { width: 1400, height: 1000 }, rs)
    await t.page.getByTestId('glance').waitFor({ timeout: 25000 })
    await t.page.waitForTimeout(500)
    const gsrc = await t.page.getByTestId('glance-top').locator('img').first().getAttribute('src', { timeout: 3000 }).catch(() => '')
    ck(`tracker highest score shows the library crest ${label}`, (gsrc || '').endsWith(`${club.id}?v=7`), gsrc)
    await t.ctx.close()
  }
  LIBRARY = []
}

// ── A club has no Round Review ────────────────────────────────────────────────
{
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
  const page = await ctx.newPage()
  await page.route('**/*', async (route) => {
    const url = route.request().url()
    if (!/\/api\//.test(url)) return route.continue()
    const json = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(url)) return route.fulfill(json({ id: 'u2', username: 'club', role: 'club_admin', club_slug: 'alpha', club_name: 'Alpha CC', entitlements: { modules: ['socials'], status: 'active' } }))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json({ ...SETTINGS, id: 'c1', name: 'Alpha CC', workspace_kind: null, slug: 'alpha' }))
    if (/\/admin\/social\/templates|\/admin\/social\/media|\/club-admin\/players|sponsors/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/social-post?type=fixtures`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  ck('a club sees post types', (await page.getByRole('button', { name: /^Fixtures/ }).count()) > 0)
  ck('a club is not offered Round Review', (await page.getByRole('button', { name: /^Round Review/ }).count()) === 0)
  await ctx.close()
}

// ── 390px ─────────────────────────────────────────────────────────────────────
{
  const { ctx, page, errors } = await open('/admin/performance', { width: 390, height: 844 }, store)
  await page.getByTestId('section-glance').waitFor({ timeout: 25000 })
  await page.waitForTimeout(1500)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no sideways scroll', over <= 0, `overflow ${over}px`)
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/tracker-phone.png`, fullPage: true })
  ck('390px: no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
