// Drives the Performance Tracker and the Round Review posts inside an
// ASSOCIATION SOCIALS WORKSPACE in Chromium, with the API stubbed at the network
// layer (backend: routers/performance.py, services/performance_round.py).
//
//   npx vite build && npx vite preview --port 5199 &
//   PULL_JSON=/path/to/a/real/pull.json node frontend/verification/verify_performance_tracker_browser.mjs [baseUrl]
//
// PULL_JSON is optional: one competition's pull as the backend returned it for a
// real round. Without it a small inline round is used. SHOTS=dir saves screenshots.
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SHOTS = process.env.SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const INLINE = {
  kind: 'round', grade: '1st Grade', grade_id: 'g1', round: 'Round 4', round_id: 'r4', season: '2026/27', date: '2026-11-07', label: 'SAT 7 NOV',
  results: [{ match_id: 'm1', url: 'https://play.cricket.com.au/match/m1', home: 'Subiaco Marist', away: 'Swan Valley', home_id: 't3', away_id: 't1', home_score: '134', away_score: '153',
    winner: 'away', result: 'Swan Valley 1st XI won by 19 runs', margin: { runs: 19, wickets: null, tie: false, closeness: 19 }, venue: 'Oval', date: '2026-11-07',
    home_rank: 3, away_rank: 1, top_bat: [], top_bowl: [] }],
  not_played: [], skipped: [],
  batting: [{ name: 'Heshan Perera', team: 'Swan Valley', team_id: 't1', opp: 'Subiaco Marist', runs: 80, balls: 151, not_out: false, match_id: 'm1', line: '80 (151)' }],
  bowling: [{ name: 'Jeffrey Willey', team: 'Swan Valley', team_id: 't1', opp: 'Subiaco Marist', overs: '12', runs: 30, wickets: 4, hat_tricks: 0, match_id: 'm1', line: '4/30 (12)' }],
  performers: [{ name: 'Heshan Perera', team: 'Swan Valley', team_id: 't1', opp: 'Subiaco Marist', points: 96, line: '80 (151), 1 ct', match_id: 'm1' }],
  milestones: [{ kind: 'fifty', name: 'Heshan Perera', team: 'Swan Valley', text: 'Heshan Perera (Swan Valley) made 80 (151) against Subiaco Marist', match_id: 'm1' }],
  fielders: [], catches: [], catches_total: 0, run_outs: [],
  ladder: [{ rank: 1, team_id: 't1', team: 'Swan Valley', played: 4, won: 4, lost: 0, points: 36 }, { rank: 3, team_id: 't3', team: 'Subiaco Marist', played: 4, won: 2, lost: 2, points: 26 }],
  upsets: [], upset_gap: 3, crests: {},
  next_round: { round: 'Round 5', match_of_round: 0, fixtures: [{ match_id: 'f1', url: '', home: 'Swan Valley', away: 'Bedford Morley', home_id: 't1', away_id: 't6', home_rank: 1, away_rank: 6, date: '2026-11-21', label: 'SAT 21 NOV', time: '12:30 PM', venue: 'Swan Valley Sporting Club' }] },
}
// A season reading (GET .../season). SEASON_JSON takes a real one; inline otherwise.
const SEASON = process.env.SEASON_JSON ? JSON.parse(readFileSync(process.env.SEASON_JSON, 'utf8')) : {
  competitions: [{ key: 'north', name: 'North', grade: '1st Grade', latest: true, players: 2,
    leaders: { runs: [{ pid: 'p1', name: 'Heshan Perera', club: 'Swan Valley', value: 280, sub: '4 inns' }], wickets: [], catches: [], high_score: [], best_bowling: [] },
    season_milestones: [{ pid: 'p1', name: 'Heshan Perera', club: 'Swan Valley', kind: 'season_runs', mark: 200, text: 'Heshan Perera (Swan Valley) passed 200 runs for the season (280)' }],
    career_milestones: [] }],
  all: null, career: { ready: [], pending: ['Swan Valley'], failed: [] }, as_at: '2026-11-23T00:00:00Z' }
const PULL = process.env.PULL_JSON ? JSON.parse(readFileSync(process.env.PULL_JSON, 'utf8')) : INLINE
const LINK = 'https://play.cricket.com.au/match/bf35fc33-02b9-4c55-84aa-fed719f64422/smcc-v-swan-valley'
const SETTINGS = { id: 'ws-1', name: 'Hills Association', short_name: 'HILLS', slug: null, workspace_kind: 'association', logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null }

// The workspace crest library the stub serves (GET /admin/social/crests).
let LIBRARY = []
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC', 'base64')

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

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
      id: 'u1', username: 'staff', role: 'super_admin', club_slug: null, club_name: 'Hills Association', workspace_kind: 'association',
      acting_as_club: true, home_club_name: 'BetterCricket', can_switch_clubs: true, entitlements: { modules: ['socials'], status: 'active' },
    }))
    if (u.pathname.endsWith('/admin/performance/pull')) return route.fulfill(json(PULL))
    if (u.pathname.endsWith('/admin/performance/rounds') && req.method() === 'GET') return route.fulfill(json({ rounds: store.map(({ data, ...r }) => r) }))
    if (u.pathname.endsWith('/admin/performance/rounds') && req.method() === 'POST') {
      const r = { id: `r${store.length + 1}`, round_label: '', round_date: null, data: {} }
      store.unshift(r)
      return route.fulfill(json(r))
    }
    if (/\/admin\/performance\/rounds\/[^/]+\/season$/.test(u.pathname)) return route.fulfill(json(SEASON))
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

const store = []
const MOR = PULL.next_round.fixtures[PULL.next_round.match_of_round]
const POTR = [...PULL.performers].sort((a, b) => b.points - a.points)[0]

// ── The tracker ───────────────────────────────────────────────────────────────
{
  const { ctx, page, calls, errors } = await open('/admin/performance', { width: 1400, height: 1000 }, store)
  const start = page.getByRole('button', { name: 'Track a round' })
  await start.waitFor({ timeout: 25000 })
  ck('empty state offers to track a round', await start.isVisible())
  ck('sidebar names the Performance Tracker', (await page.getByRole('link', { name: /Performance Tracker/ }).count()) > 0)
  ck('no podcast wording left on the page', !/podcast run sheet|episode/i.test(await page.locator('main, body').first().innerText()))
  await start.click()
  await page.getByLabel('North match link').waitFor()
  ck('three competitions by default', (await page.getByLabel('Competition name').count()) === 3)
  await page.getByLabel('North match link').fill(LINK)
  await page.getByTestId('comp-0').getByRole('button', { name: 'Pull' }).click()
  await page.getByTestId('glance').waitFor({ timeout: 5000 })
  const pullCall = calls.find(c => c.path.endsWith('/admin/performance/pull'))
  ck('pull sends the pasted link as q', pullCall && new URLSearchParams(pullCall.search).get('q') === LINK, pullCall?.search)
  ck('round label filled from the pull', (await page.getByLabel('Round', { exact: true }).inputValue()) === PULL.round)
  const top = POTR
  ck('at a glance names the player of the round', (await page.getByTestId('glance-potr').innerText()).includes(top.name))
  ck('every result listed', (await page.getByTestId('results-north').locator('li').count()) === PULL.results.length)
  ck('batting table led by the top score', (await page.getByTestId('table-batting').locator('tbody tr').first().innerText()).includes(PULL.batting[0].name))
  ck('bowling table led by the best figures', (await page.getByTestId('table-bowling').locator('tbody tr').first().innerText()).includes(PULL.bowling[0].name))
  ck('upsets explain themselves when there are none', PULL.upsets.length ? true : (await page.getByTestId('glance-upset').innerText()).includes('3 or more places'))
  ck('ladder shown', (await page.getByTestId('ladders').locator('tbody tr').count()) === PULL.ladder.length)
  const mor = MOR
  ck('next round marks the match of the round', (await page.getByTestId('next').getByText(`${mor.home} (`, { exact: false }).first().innerText()).includes('MATCH OF THE ROUND'))
  // Season leaderboards and milestones, from GET .../season.
  await page.getByTestId('leaders-runs').waitFor({ timeout: 8000 })
  const sb = SEASON.competitions[0]
  ck('season call made for this round', calls.some(c => /\/rounds\/[^/]+\/season$/.test(c.path)))
  ck('most runs leaderboard led by the season leader', (await page.getByTestId('leaders-runs').locator('li').first().innerText()).includes(sb.leaders.runs[0].name))
  ck('season milestones listed', sb.season_milestones.length
    ? (await page.getByTestId('season-milestones').innerText()).includes(sb.season_milestones[0].text)
    : (await page.getByTestId('season-milestones').innerText()).includes('Nobody passed'))
  ck('career milestones explain themselves', (await page.getByTestId('career-milestones').innerText()).length > 20)
  ck('pending career clubs are named', SEASON.career.pending.length
    ? (await page.getByTestId('career-pending').innerText()).includes(SEASON.career.pending[0])
    : (await page.getByTestId('career-pending').count()) === 0)
  await page.getByLabel('Notes').fill('Bentley clubrooms reopening Saturday')
  await page.waitForTimeout(1500)
  const patch = calls.filter(c => c.method === 'PATCH').pop()
  const body = patch ? JSON.parse(patch.body) : {}
  ck('autosave carries the pull, the label and the notes', body.data?.competitions?.[0]?.pull?.results?.length === PULL.results.length
    && body.round_label === PULL.round && body.data?.notes === 'Bentley clubrooms reopening Saturday')
  // Download hands over the same text as Copy.
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download' }).click()])
  const txt = readFileSync(await dl.path(), 'utf8')
  ck('download names the file after the round', /round-\d+-performance\.txt|performance\.txt$/.test(dl.suggestedFilename()), dl.suggestedFilename())
  ck('download holds results, top batting, ladder and notes', txt.includes('Results') && txt.includes(PULL.batting[0].name) && txt.includes('Ladder') && txt.includes('Bentley clubrooms reopening Saturday'))
  ck('download holds the season leaders and milestones', txt.includes('SEASON LEADERS') && txt.includes(SEASON.competitions[0].leaders.runs[0].name)
    && (!SEASON.competitions[0].season_milestones.length || txt.includes(SEASON.competitions[0].season_milestones[0].text)))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/tracker.png`, fullPage: true })
  await Promise.all([page.waitForURL(/social-post/), page.getByRole('button', { name: 'Make posts' }).click()])
  ck('Make posts opens Round Review on this round', /type=review/.test(page.url()) && page.url().includes(`round=${store[0].id}`), page.url())
  ck('tracker: no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── The posts ─────────────────────────────────────────────────────────────────
const postText = (page) => page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  return holder ? holder.innerText : ''
})
{
  const { ctx, page, errors } = await open(`/admin/social-post?type=review&round=${store[0].id}`, { width: 1600, height: 1000 }, store)
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  await page.getByTestId('round-review-controls').waitFor({ timeout: 10000 })
  await page.waitForTimeout(800)
  const wrap = await postText(page)
  ck('RV1 round wrap names the round', wrap.includes(PULL.round.toUpperCase()), wrap.slice(0, 200))
  ck('RV1 headline leads with the top score', wrap.includes(PULL.batting[0].name.toUpperCase()))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/rv1.png` })
  // Typing a heading changes the post.
  await page.getByPlaceholder("Leave blank for the layout's own").first().fill('Round Four Gold')
  await page.waitForTimeout(400)
  ck('a typed heading reaches the post', (await postText(page)).includes('ROUND FOUR GOLD'))
  ck('posts: no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// Each layout opened by its id: what it draws, and that it is not another layout's text.
for (const [id, ok, not] of [
  ['RV2', (t) => t.includes('TOP SCORES') && t.includes('BEST BOWLING') && t.includes(PULL.bowling[0].name.toUpperCase()), 'WRAP'],
  ['RV3', (t) => t.includes('PLAYER OF') && t.includes(POTR.name.split(' ').pop().toUpperCase()), 'TOP SCORES'],
  ['RV4', (t) => t.includes('MATCH OF') && t.includes(MOR.home.toUpperCase()) && t.includes(MOR.away.toUpperCase()), 'TOP SCORES'],
]) {
  const { ctx, page, errors } = await open(`/admin/social-post?template=${id}&round=${store[0].id}`, { width: 1600, height: 1000 }, store)
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  await page.waitForTimeout(1500)
  const t = await postText(page)
  ck(`${id} draws from the round`, ok(t), t.slice(0, 240))
  ck(`${id} is its own layout`, !t.includes(not))
  ck(`${id}: no page errors`, errors.length === 0, errors.join(' | '))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${id.toLowerCase()}.png` })
  await ctx.close()
}

// ── Crests come from the crest library as it is now ──────────────────────────
// PSWL_JSON is a real pull with club ids; PSWL_OLD_JSON the same round as a pull
// read before crests were stored (no team ids, crests or clubs). Both must show
// the library's crest for the top score's club, found by club id on the first
// and by club name on the second.
if (process.env.PSWL_JSON && process.env.PSWL_OLD_JSON) {
  const fresh = JSON.parse(readFileSync(process.env.PSWL_JSON, 'utf8'))
  const old = JSON.parse(readFileSync(process.env.PSWL_OLD_JSON, 'utf8'))
  const topTeamId = fresh.batting[0].team_id
  const club = fresh.clubs[topTeamId]
  const kept = `/api/images/association-crests/ws-1/${club.id}?v=7`
  LIBRARY = [
    { caOrgId: club.id, name: club.name, logo: kept },
    { caOrgId: 'someone-else', name: 'Applecross Districts Juniors', logo: '/api/images/association-crests/ws-1/someone-else?v=1' },
  ]
  for (const [label, pull] of [['by club id', fresh], ['by club name, on a round pulled before crests were stored', old]]) {
    const rs = [{ id: 'p1', round_label: pull.round, round_date: pull.date, data: { competitions: [{ key: 'south', name: 'South A', link: LINK, pull }] } }]
    const { ctx, page, errors } = await open(`/admin/social-post?template=RV2&round=p1`, { width: 1600, height: 1000 }, rs)
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
    await page.waitForTimeout(1500)
    const srcs = await page.evaluate(() => {
      const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
      return holder ? [...holder.querySelectorAll('img')].map((i) => i.getAttribute('src') || '') : []
    })
    ck(`RV2 top score shows the library crest ${label}`, srcs.includes(kept.replace('/api', '/api')) || srcs.some(x => x.endsWith(`${club.id}?v=7`)), srcs.slice(0, 4).join(' | '))
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/rv2-${pull === fresh ? 'id' : 'name'}.png` })
    ck(`RV2 ${label}: no page errors`, errors.length === 0, errors.join(' | '))
    await ctx.close()
    const t = await open('/admin/performance', { width: 1400, height: 1000 }, rs)
    // The highest score card: its own test id, else (an older build) the card that says so.
    await t.page.getByTestId('glance').waitFor({ timeout: 25000 })
    await t.page.waitForTimeout(500)
    const card = (await t.page.getByTestId('glance-top').count()) ? t.page.getByTestId('glance-top') : t.page.getByTestId('glance').locator('div', { hasText: /^HIGHEST SCORE/ }).first()
    const gsrc = await card.locator('img').first().getAttribute('src', { timeout: 3000 }).catch(() => '')
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
  await page.getByTestId('glance').waitFor({ timeout: 25000 })
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no sideways scroll', over <= 0, `overflow ${over}px`)
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/tracker-phone.png`, fullPage: true })
  ck('390px: no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
