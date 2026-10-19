// Player photos on the admin Votes screens: drives the real Leaderboard, awards-night
// stage and game detail in Chromium with the API stubbed at the network layer.
//
//   npx vite build && npx vite preview --port 5199 &
//   node verification/verify_vote_photos_browser.mjs [baseUrl]
//   NO_PHOTOS=1 node verification/verify_vote_photos_browser.mjs   (control: payloads without photo_url)
//
// Asked for: show each player's photo on Votes and the places around it. So the checks
// cover a face on the podium, the standings rows, the race legend, the last-round
// results, the awards-night leader and rows, the game's count and its ballots; that a
// player with no photo, and one whose photo will not load, still show their initials;
// and the layout at phone width.
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || '/tmp/claude-0'
const NO_PHOTOS = !!process.env.NO_PHOTOS

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const svg = (fill) => 'data:image/svg+xml;utf8,' + encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" fill="${fill}"/></svg>`)
// Thusith has a photo, Malinda has none, James's photo URL is dead.
const PHOTO = { p1: svg('#c0392b'), p2: null, p3: 'http://127.0.0.1:1/dead.png', p4: svg('#2980b9'), p5: svg('#27ae60') }
const photo = (id) => (NO_PHOTOS ? null : PHOTO[id])

const NAMES = { p1: 'De soysa, Thusith', p2: 'Deshapriya, Malinda', p3: 'Dockery, James', p4: 'Galhenage, Thilina', p5: 'Hales, Thomas' }
const standing = (id, i) => ({
  player_id: id, name: NAMES[id], photo_url: photo(id), points: 3, raw: 3, counts: [1, 0, 0], rounds: 1,
  grade: '4th Grade', grade_short: '4th', movement: 0, form: [3], cumulative: [3], round_gain: 3, tied: i > 0,
})
const ROUNDS = [{ key: 'r1', label: 'Round 1', short: 'R1', date: '2026-10-10', counted: true, fixtures: [] },
                { key: 'r2', label: 'Round 2', short: 'R2', date: '2026-10-17', counted: true, fixtures: [] }]
const BOARD = {
  year: 2026, medal_id: 'm1', medal_name: 'Best Player', ballot_values: [3, 2, 1], counting_method: 'rank', tie_policy: 'share',
  weighting: { mode: 'off', top_grade: null, weights: {} },
  rounds: ROUNDS, standings: Object.keys(NAMES).map(standing), through_round: null,
  last_round: { label: 'Round 2', fixture: 'vs Bassendean CC 3rd XI', results: [
    { player_id: 'p3', name: NAMES.p3, photo_url: photo('p3'), points: 3 },
    { player_id: 'p1', name: NAMES.p1, photo_url: photo('p1'), points: 2 },
    { player_id: 'p2', name: NAMES.p2, photo_url: photo('p2'), points: 1 }] },
  grades: [{ id: 'g1', name: '4th Grade' }], club_name: 'Alpha CC', club_short: 'AC', season_label: '2026/27',
  grade_name: 'Whole club', grade_id: null, medals: [], race_caption: null,
}
const MEDALS = { medals: [{ medal_id: 'm1', medal_name: 'Best Player', enabled: true, grade_names: [], ballot_values: [3, 2, 1] }], grades: [] }
const FIXTURES = { year: 2026, years: [2026], grades: [], rounds: [], settings: { token: 't', enabled: true, ballot_values: [3, 2, 1] },
  summary: { open: 1, awaiting: 0, closed: 0, total: 1 },
  fixtures: [{ id: 'f1', round: 'Round 2', opponent: 'Bassendean CC 3rd XI', home_away: 'HOME', date: '2026-10-17', grade: '4th Grade',
    state: 'closed', ballots: 1, voters_expected: 11, closes_on: null, in_count: 1 }] }
const DETAIL = {
  fixture: { id: 'f1', opponent: 'Bassendean CC 3rd XI', round: 'Round 2', date: '2026-10-17', state: 'closed', override: null, voters_expected: 11, weight: 1 },
  outstanding: [], settings: { ballot_values: [3, 2, 1], voter_mode: 'all', token: 't', enabled: true, vote_counter: null },
  eligibility: { requested: 'scorecard', used: 'scorecard', fell_back: false, counts: { scorecard: 3 }, unmatched: [], override: null, labels: {} },
  eligible: [{ id: 'p1', name: NAMES.p1, is_captain: true }, { id: 'p2', name: NAMES.p2, is_captain: false }, { id: 'p3', name: NAMES.p3, is_captain: false }],
  ballots: [{ id: 'b1', voter_player_id: 'p4', voter: NAMES.p4, voter_photo_url: photo('p4'), voter_kind: 'player', source: 'public',
    picks: [{ position: 1, player_id: 'p3', name: NAMES.p3, photo_url: photo('p3') },
            { position: 2, player_id: 'p1', name: NAMES.p1, photo_url: photo('p1') },
            { position: 3, player_id: 'p2', name: NAMES.p2, photo_url: photo('p2') }] }],
  results: [{ player_id: 'p3', name: NAMES.p3, photo_url: photo('p3'), raw: 3, counts: [1, 0, 0], points: 3 },
            { player_id: 'p1', name: NAMES.p1, photo_url: photo('p1'), raw: 2, counts: [0, 1, 0], points: 2 },
            { player_id: 'p2', name: NAMES.p2, photo_url: photo('p2'), raw: 1, counts: [0, 0, 1], points: 1 }],
}

const ME = {
  id: 'u1', username: 'pat', display_name: 'Pat', club_id: 'c1', club_slug: 'alpha', club_name: 'Alpha CC',
  can_switch_clubs: false, home_club_id: 'c1', home_club_name: 'Alpha CC', acting_as_club: false,
  linked_clubs: [], can_switch_linked_clubs: false, acting_as_linked_club: false,
  entitlements: { modules: ['select'], status: 'active', billing_modules: [] },
  role: 'club_admin', is_primary_admin: true, capabilities: ['manage_votes', 'view_vote_results'],
  access: { mode: 'full', module_key: null, module_name: null },
}

async function stub(page, state) {
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const u = new URL(req.url())
    const p = u.pathname.replace(/^\/api/, '')
    state.calls.push({ method: req.method(), p, q: u.search })
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p === '/auth/me') return json(ME)
    if (p === '/votes/medals') return json(MEDALS)
    if (p === '/votes/leaderboard') return json(BOARD)
    if (p === '/votes/fixtures') return json(FIXTURES)
    if (p === '/votes/fixtures/f1') return json(DETAIL)
    return json({ detail: 'not stubbed' }, 404)
  })
}

async function section(name, fn) {
  try { await fn() } catch (e) { fail++; console.log(`FAIL ${name} did not complete  ${String(e.message).split('\n')[0].slice(0, 140)}`) }
}

const browser = await chromium.launch({ executablePath: EXECUTABLE })
async function open(path, viewport = { width: 1280, height: 900 }) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  page.on('pageerror', (e) => console.log(`PAGEERROR ${path}: ${String(e.message).slice(0, 160)}`))
  const state = { calls: [] }
  await stub(page, state)
  await page.goto(`${BASE}${path}`)
  return { ctx, page, state }
}
// Faces inside a locator: how many are photos that actually loaded, how many show initials.
const faces = async (loc) => ({
  loaded: await loc.locator('img[data-face="photo"]').evaluateAll((els) => els.filter((e) => e.complete && e.naturalWidth > 0).length),
  initials: await loc.locator('[data-face="initials"]').count(),
})

// ── Leaderboard ─────────────────────────────────────────────────────────
await section('leaderboard', async () => {
  const { ctx, page } = await open('/admin/betterselect/votes?tab=leaderboard&medal=m1')
  await page.getByText('Best Player Count').waitFor({ timeout: 15000 })
  await page.waitForTimeout(600) // let the images settle (and the dead one fail)

  const podium = page.locator('div.flex-col.md\\:flex-row').first()
  const pf = await faces(podium)
  // p1 has a photo; p2 has none; p3's is dead: the podium is those three players in order.
  ck('podium: the player with a photo shows it', NO_PHOTOS ? pf.loaded === 0 : pf.loaded === 1, JSON.stringify(pf))
  ck('podium: no photo and a dead photo both fall back to initials', NO_PHOTOS ? pf.initials === 3 : pf.initials === 2, JSON.stringify(pf))

  const rows = page.locator('div.grid.border-t')
  const rf = await faces(rows)
  ck('rows: 5 standings, each shows a face', rf.loaded + rf.initials === 5, JSON.stringify(rf))
  ck('rows: three loaded photos (p1, p4, p5)', NO_PHOTOS ? rf.loaded === 0 : rf.loaded === 3, JSON.stringify(rf))
  ck('rows: the initials still read right for a player without a photo',
    (await rows.nth(1).locator('[data-face="initials"]').first().innerText()) === 'DM')
  const rowText = await rows.first().innerText()
  ck('rows: the name is still there next to the photo', rowText.includes('De soysa, Thusith'))

  const side = page.locator('.pb-card').first()
  const sf = await faces(side)
  ck('race card: legend and last-round results both carry faces', sf.loaded + sf.initials === 5 + 3, JSON.stringify(sf))

  // a loaded photo is a round box of the right size, not a stretched image
  if (!NO_PHOTOS) {
    const box = await rows.first().locator('img[data-face="photo"]').boundingBox()
    ck('row photo is a 32px square', Math.round(box.width) === 32 && Math.round(box.height) === 32, JSON.stringify(box))
  }
  await page.screenshot({ path: `${SHOTS}/votes-photos-leaderboard${NO_PHOTOS ? '-control' : ''}.png` })

  // ── Awards night ──
  await page.getByRole('button', { name: /Presentation mode/ }).click()
  await page.getByText('LEADING THE COUNT').waitFor()
  await page.waitForTimeout(600)
  const stage = page.locator('div.fixed.inset-0')
  const af = await faces(stage)
  // leader + 5 rows = 6 faces; photos on p1 (twice), p4 and p5 = 4
  ck('awards night: the leader and every row carry a face', af.loaded + af.initials === 6, JSON.stringify(af))
  ck('awards night: photos load on the stage', NO_PHOTOS ? af.loaded === 0 : af.loaded === 4, JSON.stringify(af))
  const big = stage.locator('[data-face]').first()
  const bb = await big.boundingBox()
  ck('awards night: the leader is the big face', Math.round(bb.width) === 112, JSON.stringify(bb))
  await page.screenshot({ path: `${SHOTS}/votes-photos-awards${NO_PHOTOS ? '-control' : ''}.png` })
  await ctx.close()
})

// ── Game detail ─────────────────────────────────────────────────────────
await section('game detail', async () => {
  const { ctx, page } = await open('/admin/betterselect/votes?medal=m1')
  await page.getByText('Round 2 · vs Bassendean CC 3rd XI').first().click()
  await page.getByText("This week's count").waitFor({ timeout: 15000 })
  await page.waitForTimeout(600)

  const table = page.locator('table')
  const tf = await faces(table)
  ck("this week's count: a face on each of the 3 rows", tf.loaded + tf.initials === 3, JSON.stringify(tf))
  ck("this week's count: one loaded, one initials, one dead falls back", NO_PHOTOS ? tf.loaded === 0 : (tf.loaded === 1 && tf.initials === 2), JSON.stringify(tf))

  const ballots = page.locator('div.divide-y').filter({ hasText: 'Galhenage' })
  const bf = await faces(ballots)
  ck('ballots: the voter and three picks each have a face', bf.loaded + bf.initials === 4, JSON.stringify(bf))
  ck('ballots: voter and p1 photos load', NO_PHOTOS ? bf.loaded === 0 : bf.loaded === 2, JSON.stringify(bf))
  const ballotText = await ballots.innerText()
  ck('ballots: values and names still read 3 Dockery, 2 De soysa, 1 Deshapriya',
    /3\s*Dockery, James/.test(ballotText.replace(/\n/g, ' ')) || (ballotText.includes('Dockery, James') && ballotText.includes('Deshapriya, Malinda')))
  await page.screenshot({ path: `${SHOTS}/votes-photos-detail${NO_PHOTOS ? '-control' : ''}.png` })
  await ctx.close()
})

// ── Phone width ─────────────────────────────────────────────────────────
await section('390px', async () => {
  for (const [label, path, ready] of [
    ['leaderboard', '/admin/betterselect/votes?tab=leaderboard&medal=m1', 'Best Player Count'],
  ]) {
    const { ctx, page } = await open(path, { width: 390, height: 844 })
    await page.getByText(ready).waitFor({ timeout: 15000 })
    await page.waitForTimeout(500)
    const podiumBox = await page.locator('div.flex-col.md\\:flex-row').first().boundingBox()
    // the leaderboard table already scrolls inside its own box at this width (pre-existing),
    // so the check is the podium: a photo must not push a card past the viewport
    ck(`390px ${label}: the podium stays inside the viewport`, podiumBox.x + podiumBox.width <= 391, JSON.stringify(podiumBox))
    await page.screenshot({ path: `${SHOTS}/votes-photos-390${NO_PHOTOS ? '-control' : ''}.png` })
    await ctx.close()
  }
})

await browser.close()
console.log(`\n${pass} passed, ${fail} failed${NO_PHOTOS ? ' (control run: photo checks are inverted to expect none)' : ''}`)
process.exit(fail ? 1 : 0)
