// Drives BetterPosts inside an ASSOCIATION SOCIALS WORKSPACE in Chromium, with the
// API stubbed at the network layer (backend: services/social_competition.py).
//
//   npx vite build && npx vite preview --port 5198 &
//   node frontend/verification/verify_association_socials_browser.mjs [baseUrl]
//
// What a build cannot tell you: that a workspace's pulls are link only (no "Pull
// latest round"), that the pasted link goes on the wire as `q`, that the post names
// the home team first with no HOME / AWAY word and no club round record, that the
// team of the week sends the per-club cap and draws each player's own club crest,
// that a lineup is picked by side, that Milestones is not offered, and that the
// Super Admin page creates a workspace with the body it shows.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SHOTS = process.env.SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const SETTINGS = {
  id: 'ws-1', name: 'WASTCA', short_name: 'WASTCA', slug: null, workspace_kind: 'association',
  logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null,
}
const LINK = 'https://play.cricket.com.au/grade/f584d7c6-e416-4075-979a-f2a25f059932?tab=matches&roundId=05a04e96-2e57-4b32-ab8d-c7fc1a781ccd'
const CREST = (k) => `https://res.cloudinary.com/playhq/${k}.png`
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC', 'base64')

const side = (home, homeLogo, opp, oppLogo) => ({
  grade: home, home, homeClub: `${home} CRICKET CLUB`, homeMono: home.slice(0, 3), homeLogo,
  opp, oppClub: `${opp} CRICKET CLUB`, oppMono: opp.slice(0, 3), oppLogo, neutral: true, categories: [],
})
const FIXTURES = {
  kind: 'round', neutral: true, season: '2026/27', grade: '2nd Grade', club: {},
  dates: [{ date: '2026-10-10', label: 'SAT 10 OCT', round: 'ROUND 1', comp: '2ND GRADE', fixtures: [
    { ...side('APPLECROSS', CREST('app'), 'WESTERN SUBURBS', CREST('wsc')), ha: 'H', time: '12:00 PM', venue: 'BERT JEFFREY PARK' },
    { ...side('OCEAN RIDGE', CREST('ocr'), 'KALAMUNDA', CREST('kal')), ha: 'H', time: '12:00 PM', venue: 'FLINDERS PARK' },
    { ...side('BENTLEY', CREST('ben'), 'SWAN VALLEY', CREST('swv')), ha: 'H', time: '12:00 PM', venue: 'WYONG PARK' },
  ] }],
}
const RESULTS = {
  kind: 'round', neutral: true, season: '2026/27', grade: '2nd Grade', club: {}, skipped: ['OCEAN RIDGE V KALAMUNDA'],
  dates: [{ date: '2026-10-10', label: 'SAT 10 OCT', round: 'ROUND 1', comp: '2ND GRADE', results: [
    { ...side('APPLECROSS', CREST('app'), 'WESTERN SUBURBS', CREST('wsc')), us: '1/78', them: '76', outcome: 'W', margin: 'BY 9 WICKETS',
      topBat: [{ name: 'W. DAGG', line: '40 (30)' }], topBowl: [{ name: 'P. ACHARIGE', line: '3/10 (5)' }], oppTopBat: [], oppTopBowl: [],
      winnerSide: 'home',
      leadBat: [{ name: 'W. DAGG', line: '40 (30)', team: 'home' }, { name: 'K. AWAYMAN', line: '30 (41)', team: 'away' }],
      leadBowl: [{ name: 'P. ACHARIGE', line: '3/10 (5)', team: 'home' }, { name: 'T. AWAYBOWL', line: '2/20 (6)', team: 'away' }] },
    { ...side('BENTLEY', CREST('ben'), 'SWAN VALLEY', CREST('swv')), us: '9/180', them: '188', outcome: 'L', margin: 'BY 8 RUNS',
      topBat: [{ name: 'O. FANAYAN', line: '37 (50)' }], topBowl: [], oppTopBat: [{ name: 'D. KIRKNESS', line: '46 (54)' }], oppTopBowl: [{ name: 'M. TURNER', line: '3/38 (8)' }],
      winnerSide: 'away',
      leadBat: [{ name: 'D. KIRKNESS', line: '46 (54)', team: 'away' }, { name: 'O. FANAYAN', line: '37 (50)', team: 'home' }],
      leadBowl: [{ name: 'M. TURNER', line: '3/38 (8)', team: 'away' }, { name: 'S. GOYAL', line: '3/33 (7.5)', team: 'home' }] },
  ] }],
}
const CLUBS = ['SUBIACO MARIST', 'SUBIACO MARIST', 'SUBIACO MARIST', 'APPLECROSS', 'BENTLEY', 'SWAN VALLEY', 'WESTERN SUBURBS',
  'BEDFORD MORLEY', 'FREMANTLE', 'SOUTH PERTH', 'APPLECROSS', 'BENTLEY', 'SWAN VALLEY', 'KALAMUNDA']
const POOL = CLUBS.map((club, i) => ({
  first: `First${i}`, last: `Last${i}`, short: `F. LAST${i}`, pid: null, guid: `g${i}`, points: 150 - i * 7,
  batting: { r: 90 - i * 5, b: 60, notOut: false, fours: 0, sixes: 0, sr: 100 }, bowling: null, fielding: null,
  grade: club, opp: 'RIVALS', oppMono: 'RIV', outcome: 'W', kind: 'BAT', categories: [],
  club, clubFull: `${club} CRICKET CLUB`, clubId: club, clubMono: club.slice(0, 3), clubLogo: CREST(club.toLowerCase().replace(/ /g, '-')),
}))
// How many clubs the stubbed round says it holds (the server counts the pool).
let CLUB_COUNT = new Set(CLUBS).size
const CRESTS = [
  { caOrgId: 'c-app', name: 'Applecross Cricket Club', logo: '/api/images/association-crests/ws-1/c-app?v=1',
    original: '/api/images/association-crests/ws-1/c-app?variant=original&v=1', cleaned: '/api/images/association-crests/ws-1/c-app?variant=cleaned&v=1',
    uploaded: null, useCleaned: true, cutStyle: 'auto', colour: '#143ca0', colour2: null, colourByHand: false, uploadedAt: null },
]
const totwFor = (search) => {
  const cap = Number(new URLSearchParams(search).get('cap') || 0)
  let players = POOL
  if (cap) {
    const n = {}, keep = [], later = []
    for (const p of POOL) { n[p.club] = (n[p.club] || 0) + 1; (n[p.club] <= cap ? keep : later).push(n[p.club] <= cap ? p : { ...p, overCap: true }) }
    players = [...keep, ...later]
  }
  return { kind: 'round', neutral: true, season: '2026/27', club: {}, grade: '2nd Grade', comp: '2ND GRADE', round: 'ROUND 1',
    date: '2026-10-10', label: 'SAT 10 OCT', matches: 4, scope: 'all', mode: 'week', cap, clubs: CLUB_COUNT, liveMatches: 0, skipped: [], scopeMatches: { junior: 0, senior: 4 }, players }
}
const LINEUPS = {
  kind: 'round', neutral: true, grade: '2nd Grade', round: 'ROUND 1', matches: [{
    match_id: 'm1', date: '2026-10-10', time: '12:00', round: 'Round 1', grade: '2nd Grade', venue: 'Ernest Johnson Oval',
    teams: [
      { id: 't1', label: 'SOUTH PERTH', name: 'South Perth 2nd XI', club: 'South Perth Cricket Club', logo_url: CREST('sp'), is_home: true, published: true,
        players: Array.from({ length: 11 }, (_, i) => ({ participant_id: `sp${i}`, name: `Pat Perthson${i}`, is_captain: i === 0, is_wicket_keeper: i === 1 })) },
      { id: 't2', label: 'SUBIACO MARIST', name: 'Subiaco Marist 2nd XI', club: 'Subiaco Marist Cricket Club', logo_url: CREST('sm'), is_home: false, published: true,
        players: Array.from({ length: 11 }, (_, i) => ({ participant_id: `sm${i}`, name: `Max Maristone${i}`, is_captain: i === 0, is_wicket_keeper: i === 1 })) },
    ],
  }],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(path, viewport = { width: 1600, height: 1000 }, waitExport = true, opts = {}) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  if (opts.storage) await page.addInitScript((kv) => { for (const [k, v] of Object.entries(kv)) localStorage.setItem(k, v) }, opts.storage)
  const settings = { ...SETTINGS, ...(opts.settings || {}) }
  const calls = []
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (body, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/*', async (route) => {
    const url = route.request().url()
    if (/res\.cloudinary\.com/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG, headers: { 'access-control-allow-origin': '*' } })
    if (!/\/api\//.test(url)) return route.continue()
    const u = new URL(url)
    calls.push({ method: route.request().method(), path: u.pathname, search: u.search, body: route.request().postData() })
    if (/\/admin\/social\/fixtures/.test(url)) return route.fulfill(json(FIXTURES))
    if (/\/admin\/social\/results/.test(url)) return route.fulfill(json(RESULTS))
    if (/\/admin\/social\/totw/.test(url)) return route.fulfill(json(totwFor(u.search)))
    if (/\/admin\/social\/competition\/lineups/.test(url)) return route.fulfill(json(LINEUPS))
    if (/\/admin\/social\/crests/.test(url)) {
      if (route.request().method() === 'PATCH') {
        const body = JSON.parse(route.request().postData() || '{}')
        return route.fulfill(json({ crests: CRESTS.map((c) => ({ ...c, useCleaned: body.cut_style ? true : (body.use_cleaned ?? c.useCleaned), cutStyle: body.cut_style || c.cutStyle })) }))
      }
      return route.fulfill(json({ crests: CRESTS }))
    }
    if (/\/images\/association-crests\//.test(url) || /\/images\/organisations\/ws-1\/logo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'staff', role: 'super_admin', club_slug: null, club_name: 'WASTCA', workspace_kind: 'association',
      acting_as_club: true, home_club_name: 'BetterCricket', can_switch_clubs: true,
      entitlements: { modules: ['socials'], status: 'active' },
    }))
    if (/super\/association-workspaces/.test(url)) {
      if (route.request().method() === 'POST') return route.fulfill(json({ id: 'ws-2', name: 'Perth Juniors', short_name: null }, 201))
      return route.fulfill(json({ workspaces: [{ id: 'ws-1', name: 'WASTCA', short_name: 'WASTCA', logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', archived_at: null }] }))
    }
    if (/\/admin\/social\/templates|\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(route.request().method() === 'PATCH' ? {} : settings))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json([]))
    if (/sponsors/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
  if (waitExport) await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  return { ctx, page, calls, errors }
}

const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported */ } return false }
// The post as EXPORTED: the off-screen node.
const postText = (page) => page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  return holder ? holder.innerText : ''
})
const postImgs = (page) => page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  return holder ? [...holder.querySelectorAll('img')].map((i) => i.getAttribute('src') || '') : []
})
const linkBox = (page) => page.getByLabel(/Paste a match or grade link/).first()
async function fetchLink(page) {
  // Absent on a build without workspaces: reported by the checks, not thrown.
  if (!(await seen(linkBox(page)))) return
  await linkBox(page).fill(LINK)
  await press(page.getByRole('button', { name: /^Fetch$/ }))
  await page.waitForTimeout(700)
}
async function toData(page) {
  if (await seen(linkBox(page))) return
  await press(page.getByRole('button', { name: /^Data$/ }))
  await page.waitForTimeout(300)
}

// ── Fixtures ──────────────────────────────────────────────────────────────────
{
  const { ctx, page, calls, errors } = await open('/admin/social-post?type=fixtures')
  await toData(page)
  ck('fixtures: workspace offers a link box', await seen(linkBox(page)))
  ck('fixtures: no "Pull latest round" (a workspace has no club round)', !(await seen(page.getByRole('button', { name: /Pull latest round/ }))))
  await fetchLink(page)
  const fx = calls.filter((c) => c.path.endsWith('/admin/social/fixtures'))
  ck('fixtures: the pasted link goes on the wire as q', fx.length === 1 && new URLSearchParams(fx[0].search).get('q') === LINK, JSON.stringify(fx))
  const t = await postText(page)
  ck('fixtures: every match in the grade is on the post', ['APPLECROSS', 'OCEAN RIDGE', 'BENTLEY', 'WESTERN SUBURBS', 'SWAN VALLEY'].every((n) => t.includes(n)), t.slice(0, 300))
  ck('fixtures: home team named first', t.indexOf('APPLECROSS') > -1 && t.indexOf('APPLECROSS') < t.indexOf('WESTERN SUBURBS'))
  ck('fixtures: no HOME or AWAY word on a neutral post', !/\bHOME\b|\bAWAY\b/.test(t), t.match(/.{0,30}(HOME|AWAY).{0,30}/)?.[0])
  ck('fixtures: grade is the competition line', t.includes('2ND GRADE'))
  ck('fixtures: both crests drawn', (await postImgs(page)).filter((s) => /cloudinary/.test(s)).length >= 6)
  const crestBoxes = await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    return holder ? [...holder.querySelectorAll('img')].filter((i) => /cloudinary/.test(i.src)).map((i) => ({ w: parseFloat(i.style.width), r: i.style.borderRadius })) : []
  })
  ck('fixtures: a workspace row\'s crests are sized from the row (well over the old 50px)', crestBoxes.length >= 6 && crestBoxes.every((b) => b.w >= 90), JSON.stringify(crestBoxes))
  ck('fixtures: and drawn bare, not clipped into a disc', crestBoxes.length > 0 && crestBoxes.every((b) => !/50%/.test(b.r)), JSON.stringify(crestBoxes.slice(0, 2)))
  ck('fixtures: the crest library is offered in the Data step', await seen(page.getByTestId('crest-library')))
  await press(page.getByTestId('crest-library').getByRole('button', { name: /Club crests/ }))
  await page.waitForTimeout(300)
  ck('fixtures: the library lists the kept crests', (await page.getByTestId('crest-row').count()) === 1)
  ck('fixtures: the crest style starts on Auto', (await page.getByTestId('crest-style-auto').getAttribute('aria-pressed').catch(() => null)) === 'true')
  await press(page.getByTestId('crest-style-original'))
  await page.waitForTimeout(400)
  const patchC = calls.find((c) => c.method === 'PATCH' && c.path.endsWith('/admin/social/crests/c-app'))
  ck('fixtures: "Original" sends only that choice', patchC && patchC.body === JSON.stringify({ use_cleaned: false }), patchC?.body)
  ck('fixtures: the row then shows Original as chosen', (await page.getByTestId('crest-style-original').getAttribute('aria-pressed').catch(() => null)) === 'true')
  await press(page.getByTestId('crest-style-edge'))
  await page.waitForTimeout(400)
  const patchE = calls.filter((c) => c.method === 'PATCH' && c.path.endsWith('/admin/social/crests/c-app')).at(-1)
  ck('fixtures: "White edge" sends cut_style edge', patchE && patchE.body === JSON.stringify({ cut_style: 'edge' }), patchE?.body)
  ck('fixtures: Milestones is not offered in a workspace', !(await seen(page.getByRole('button', { name: /^Milestones$/ }))))
  ck('fixtures: no page errors', errors.length === 0, errors.join(' | '))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/fixtures.png` })
  await ctx.close()
}

// ── Results ───────────────────────────────────────────────────────────────────
{
  const { ctx, page, calls } = await open('/admin/social-post?type=results')
  await toData(page)
  await fetchLink(page)
  const rr = calls.filter((c) => c.path.endsWith('/admin/social/results'))
  ck('results: the pasted link goes on the wire as q', rr.length >= 1 && new URLSearchParams(rr.at(-1).search).get('q') === LINK)
  const t = await postText(page)
  ck('results: rows on the post, home first', t.includes('APPLECROSS') && t.indexOf('APPLECROSS') < t.indexOf('WESTERN SUBURBS'), t.slice(0, 300))
  ck('results: no club round record', !/ROUND RECORD/.test(t) && !/\b\d+W · \d+L\b/.test(t), t.match(/.{0,30}(ROUND RECORD|\dW · \dL).{0,30}/)?.[0])
  ck('results: margin from the feed printed', t.includes('BY 9 WICKETS'))
  ck('results: a match with no scorecard is named in the panel', await seen(page.getByTestId('competition-skipped')))
  ck('results (Weekend Wrap): no WON or LOST on a neutral post', !/\bWON\b|\bLOST\b|DEF BY/.test(t), t.match(/.{0,30}(WON|LOST|DEF BY).{0,30}/)?.[0])
  ck('results (Weekend Wrap): each decided match tags its winner', (t.match(/\bWIN\b/g) || []).length === 2, t.slice(0, 400))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/results.png` })
  await ctx.close()
}
for (const [id, label] of [['RR7', 'Wrap + Leaders'], ['RR2', 'Scoreboard'], ['RR4', 'Headline'], ['RR5', 'Board']]) {
  const { ctx, page } = await open(`/admin/social-post?template=${id}`)
  await toData(page)
  await fetchLink(page)
  const t = await postText(page)
  ck(`results (${label}): rows drawn`, t.includes('APPLECROSS') && t.includes('SWAN VALLEY'), t.slice(0, 200))
  ck(`results (${label}): no WON, LOST or LOST TO on a neutral post`, !/\bWON\b|\bLOST\b|LOST TO|DEF BY/.test(t), t.match(/.{0,30}(WON|LOST|DEF BY).{0,30}/)?.[0])
  if (id === 'RR7') {
    ck('results (Wrap + Leaders): leaders from BOTH sides', ['W. DAGG', 'K. AWAYMAN', 'P. ACHARIGE', 'T. AWAYBOWL', 'D. KIRKNESS', 'S. GOYAL'].every((n) => t.includes(n)), t.slice(0, 600))
    ck('results (Wrap + Leaders): no OPPOSITION heading (no side is ours)', !/OPPOSITION/.test(t))
    ck('results (Wrap + Leaders): the winner is tagged, away side too', (t.match(/\bWIN\b/g) || []).length === 2)
    const crestsNextToLeaders = await page.evaluate(() => {
      const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
      return holder ? [...holder.querySelectorAll('img')].filter((i) => /cloudinary/.test(i.src)).length : 0
    })
    // 2 rows x 2 side crests + 2 rows x 4 leader crests.
    ck('results (Wrap + Leaders): each leader carries their side\'s crest', crestsNextToLeaders >= 12, String(crestsNextToLeaders))
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/results-rr7.png` })
  }
  await ctx.close()
}

// ── Team of the week ─────────────────────────────────────────────────────────
{
  const { ctx, page, calls } = await open('/admin/social-post?type=totw')
  await toData(page)
  ck('totw: per-club cap offered', await seen(page.getByTestId('totw-club-cap')))
  ck('totw: club Juniors / Seniors switch not offered', !(await seen(page.getByTestId('totw-scope'))))
  ck('totw: no period pick (a workspace names the round by link)', !(await seen(page.getByTestId('totw-range'))))
  await fetchLink(page)
  const first = calls.filter((c) => c.path.endsWith('/admin/social/totw'))
  ck('totw: link on the wire, no cap by default', first.length === 1 && new URLSearchParams(first[0].search).get('q') === LINK && !new URLSearchParams(first[0].search).get('cap'), JSON.stringify(first))
  let imgs = await postImgs(page)
  ck('totw: players show their own club crest', imgs.some((s) => s.includes('subiaco-marist')) && imgs.some((s) => s.includes('applecross')), imgs.slice(0, 5).join(' '))
  const before = (await postText(page)).match(/Last2\b/i)
  await press(page.getByTestId('totw-cap-2'))
  await page.waitForTimeout(700)
  const all = calls.filter((c) => c.path.endsWith('/admin/social/totw'))
  ck('totw: choosing a cap re-pulls with cap=2', all.length === 2 && new URLSearchParams(all[1].search).get('cap') === '2', JSON.stringify(all.map((c) => c.search)))
  const after = await postText(page)
  ck('totw: the third Subiaco Marist player leaves the 11 under a cap of 2', !!before && !/\bLast2\b/i.test(after), after.slice(0, 200))
  // 9 clubs cannot fill 11 places at 1 each.
  const one = page.getByTestId('totw-cap-1')
  ck('totw: a cap of 1 is greyed out when 9 clubs cannot fill a team of 11', (await one.count()) > 0 && await one.isDisabled())
  ck('totw: and the panel says why', await seen(page.getByTestId('totw-cap-floor')))
  ck('totw: a cap of 2 is still offered', (await page.getByTestId('totw-cap-2').count()) > 0 && !(await page.getByTestId('totw-cap-2').isDisabled()))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/totw.png` })
  await ctx.close()
}

// A round with only 5 clubs: a cap of 2 cannot fill 11, so the pull is made again at 3.
{
  CLUB_COUNT = 5
  const { ctx, page, calls } = await open('/admin/social-post?type=totw')
  await toData(page)
  await press(page.getByTestId('totw-cap-2'))
  await fetchLink(page)
  await page.waitForTimeout(500)
  const caps = calls.filter((c) => c.path.endsWith('/admin/social/totw')).map((c) => new URLSearchParams(c.search).get('cap'))
  ck('totw: a cap the round cannot meet is raised and pulled again (2 then 3)', caps.join(',') === '2,3', caps.join(','))
  ck('totw: the raise is explained', await seen(page.getByTestId('totw-cap-raised')))
  ck('totw: the cap button follows the raise', (await page.getByTestId('totw-cap-3').getAttribute('aria-pressed')) === 'true')
  CLUB_COUNT = new Set(CLUBS).size
  await ctx.close()
}

// ── Background travels with the club; the watermark stays the association's ─
{
  const { ctx, page, calls } = await open('/admin/social-post?type=lineup', { width: 1600, height: 1000 }, true, {
    settings: { logo_url: '/api/images/organisations/ws-1/logo.png', socials_style: { bg: 'halftone-ramp', bg_url: null, bg_logo: true, bg_logo_op: 0.3, bg_text: '', bg_text_op: 0.16 } },
  })
  await toData(page)
  await fetchLink(page)
  await press(page.getByRole('button', { name: /SUBIACO MARIST/ }))
  await page.waitForTimeout(500)
  const imgs = await postImgs(page)
  const bgImgs = await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    if (!holder) return []
    const out = []
    holder.querySelectorAll('*').forEach((el) => {
      const b = getComputedStyle(el).backgroundImage
      if (b && b.includes('organisations/ws-1/logo')) out.push(b)
      if (el.tagName === 'IMG' && /organisations\/ws-1\/logo/.test(el.getAttribute('src') || '')) out.push(el.getAttribute('src'))
      if (el.tagName === 'image' && /organisations\/ws-1\/logo/.test(el.getAttribute('href') || '')) out.push(el.getAttribute('href'))
    })
    return out
  })
  ck('lineup: the watermark is the association crest, not the featured club', bgImgs.length > 0, JSON.stringify(imgs.slice(0, 6)))
  ck('lineup: the featured club\'s crest is still on the post (where the hero goes)', imgs.some((s) => s.includes('/sm.png')))
  await page.waitForTimeout(1600)
  const saves = calls.filter((c) => c.method === 'PATCH' && c.path.endsWith('/club-admin/settings'))
  ck('style from the server applied without saving it back', saves.length === 0, saves.map((c) => c.body).join(' | ').slice(0, 300))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/lineup-watermark.png` })
  await ctx.close()
}
{
  const { ctx, page, calls } = await open('/admin/social-post?type=fixtures', { width: 1600, height: 1000 }, true, {
    settings: { logo_url: '/api/images/organisations/ws-1/logo.png', socials_style: { bg: 'halftone-ramp' } },
  })
  await press(page.getByRole('button', { name: /^brand$/i }))
  await page.waitForTimeout(300)
  const wm = page.getByText(/crest watermark/).first()
  if (await seen(wm)) await press(wm)
  await page.waitForTimeout(1800)
  const save = calls.filter((c) => c.method === 'PATCH' && c.path.endsWith('/club-admin/settings')).at(-1)
  let st = {}
  try { st = JSON.parse(save?.body || '{}').socials_style || {} } catch { /* reported */ }
  ck('background settings are saved for the club (watermark and its strength travel)', st.bg === 'halftone-ramp' && 'bg_logo' in st && 'bg_logo_op' in st && 'bg_url' in st && 'bg_tint' in st, save?.body?.slice(0, 300))
  await ctx.close()
}

// ── Lineup ────────────────────────────────────────────────────────────────────
{
  const { ctx, page, calls } = await open('/admin/social-post?type=lineup')
  await toData(page)
  ck('lineup: no BetterSelect source in a workspace', !(await seen(page.getByRole('button', { name: /^BetterSelect$/ }))))
  await fetchLink(page)
  ck('lineup: round lineups asked for with the link', calls.some((c) => c.path.endsWith('/admin/social/competition/lineups') && new URLSearchParams(c.search).get('q') === LINK))
  await press(page.getByRole('button', { name: /SUBIACO MARIST/ }))
  await page.waitForTimeout(400)
  const t = (await postText(page)).toUpperCase()
  ck('lineup: the picked side\'s players are on the post', t.includes('MARISTONE0'), t.slice(0, 300))
  ck('lineup: the picked side, not the other, is the lineup', t.includes('MARISTONE') && !t.includes('PERTHSON'))
  ck('lineup: the side\'s crest replaces the workspace crest', (await postImgs(page)).some((s) => s.includes('/sm.png')))
  await ctx.close()
}

// ── Super Admin page ─────────────────────────────────────────────────────────
{
  const { ctx, page, calls } = await open('/admin/super/association-socials', { width: 1280, height: 900 }, false)
  await page.getByTestId('assoc-workspace').first().waitFor({ timeout: 20000 }).catch(() => {})
  ck('super: lists workspaces', await seen(page.getByTestId('assoc-workspace')))
  ck('super: the admin shell says it is a workspace (me says workspace_kind)', await seen(page.getByTestId('association-workspace-banner')))
  if (await seen(page.getByPlaceholder('WASTCA'))) await page.getByPlaceholder('WASTCA').first().fill('Perth Juniors')
  await press(page.getByRole('button', { name: /Create workspace/ }))
  await page.waitForTimeout(500)
  const post = calls.find((c) => c.method === 'POST' && c.path.endsWith('/club-admin/super/association-workspaces'))
  let body = {}
  try { body = JSON.parse(post?.body || '{}') } catch { /* reported */ }
  ck('super: create sends the name and colours', body.name === 'Perth Juniors' && /^#[0-9a-f]{6}$/i.test(body.primary_color || ''), post?.body)
  await ctx.close()
}

// ── 390px ─────────────────────────────────────────────────────────────────────
for (const path of ['/admin/super/association-socials']) {
  const { ctx, page } = await open(path, { width: 390, height: 844 }, false)
  await page.waitForTimeout(1500)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  const shown = await seen(page.getByTestId('assoc-workspace'))
  ck(`390px: ${path} renders its list with no horizontal overflow`, shown && over <= 0, `shown ${shown}, over by ${over}px`)
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/super-390.png` })
  await ctx.close()
}

console.log(`\n${pass} passed, ${fail} failed`)
await browser.close()
process.exit(fail ? 1 : 0)
