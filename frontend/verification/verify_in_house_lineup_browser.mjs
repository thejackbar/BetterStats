// Drives the REAL public Lineups screen in Chromium with the API stubbed at the network layer
// (Applecross, One Day Grade 6 Black): the 10th XI plays the 8th XI, both the club's own.
//   * both sides read "OUR SIDE" and both XIs link each player to their profile
//   * the request on the wire is the plain upcoming-lineups call
//   * a game against another club still marks only the club's own side, and links only its players
//   * an older payload with no `is_club` still marks the one `is_ours` side (no regression)
//   * 390px: no sideways overflow
//
//   npx vite build --outDir /tmp/lineups-dist && npx vite preview --outDir /tmp/lineups-dist --port 5198 &
//   node verification/verify_in_house_lineup_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5198'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }

const ORG = '11111111-1111-4111-8111-111111111111'
const CLUB = { id: ORG, slug: 'applecross', name: 'Applecross Cricket Club', short_name: 'Applecross', is_active: true }

const player = (pid, name, own) => ({
  participant_id: pid, name, short_name: name, redacted: false, roles: [], is_captain: false, is_wicket_keeper: false,
  ...(own ? { player_id: `pl-${pid}`, photo_url: null } : {}),
})
const team = (id, name, players, flags) => ({
  id, name, club: 'Applecross', club_id: ORG, logo_url: null, staff: [], published: players.length > 0,
  score_text: null, is_winner: false, players, ...flags,
})

// In-house: BOTH sides are the club's. `is_ours` is one of them, `is_club` is both.
const IN_HOUSE = {
  match_id: 'm-inhouse', status: 'UPCOMING', date: '2026-10-31', time: '12:00', round: '5',
  grade: 'One Day Grade 6 Black', venue: 'Applecross Reserve', any_published: true, officials: [],
  category: 'senior', category_label: 'Senior', is_final: false,
  teams: [
    team('t-10', 'Applecross 10th XI', [player('h1', 'Hugh Home', true), player('h2', 'Holly Home', true)],
      { is_home: true, is_ours: true, is_club: true }),
    team('t-8', 'Applecross 8th XI', [player('a1', 'Alex Away', true), player('a2', 'Abby Away', true)],
      { is_home: false, is_ours: false, is_club: true }),
  ],
}
// Against another club: only the club's own side is ours.
const VS_OTHER = {
  ...IN_HOUSE, match_id: 'm-other', teams: [
    team('t-8', 'Applecross 8th XI', [player('a1', 'Alex Away', true)], { is_home: true, is_ours: true, is_club: true }),
    { ...team('t-r', 'Rivals 8th XI', [player('r1', 'Rex Rival', false)], { is_home: false, is_ours: false, is_club: false }), club: 'Rivals', club_id: 'rivals' },
  ],
}
// An older payload (before `is_club` existed): one side `is_ours`, nothing else.
const OLD_SHAPE = {
  ...VS_OTHER, match_id: 'm-old', teams: VS_OTHER.teams.map(({ is_club, ...t }) => t),
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const wire = { lineups: [] }
  let payload = IN_HOUSE

  await page.route('**/api/**', (r) => json(r, {}))
  await page.route(/\/api\/clubs\/applecross$/, (r) => json(r, CLUB))
  await page.route(/\/api\/organisations\/[^/]+\/lineups(\?.*)?$/, (r) => {
    wire.lineups.push(r.request().url())
    return json(r, { source: 'fixtures', offset: 0, has_more: false, categories: [], matches: [payload] })
  })

  const open = async (p) => {
    payload = p
    await page.goto(`${BASE}/applecross/lineups`)
    await page.getByText('Alex Away').first().waitFor()
  }
  const ourSideTags = () => page.getByText('OUR SIDE', { exact: true }).count()
  const profileLinks = () => page.locator('a[href^="/players/"]').count()

  await safe('in-house game', async () => {
    await open(IN_HOUSE)
    check('both Applecross sides read OUR SIDE', (await ourSideTags()) === 2, `got ${await ourSideTags()}`)
    check('all four players link to their profile', (await profileLinks()) === 4, `got ${await profileLinks()}`)
    check('the away side is on the page at all', (await page.getByText('Applecross 8th XI').count()) > 0)
    check('the request asked for the plain upcoming list',
      wire.lineups.length > 0 && /mode=upcoming/.test(wire.lineups[0]), wire.lineups[0])
  })
  await safe('against another club', async () => {
    await open(VS_OTHER)
    check('only the club side reads OUR SIDE', (await ourSideTags()) === 1, `got ${await ourSideTags()}`)
    check('only the club side links to profiles', (await profileLinks()) === 1, `got ${await profileLinks()}`)
  })
  await safe('older payload', async () => {
    await open(OLD_SHAPE)
    check('the one is_ours side still reads OUR SIDE', (await ourSideTags()) === 1, `got ${await ourSideTags()}`)
    check('...and still links', (await profileLinks()) === 1, `got ${await profileLinks()}`)
  })
  await safe('390px', async () => {
    await page.setViewportSize({ width: 390, height: 800 })
    await open(IN_HOUSE)
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    check('no sideways overflow at 390px', over <= 0, `overflow ${over}px`)
    await page.screenshot({ path: process.env.SHOT || '/tmp/in-house-lineup-390.png', fullPage: true })
  })
  check('no uncaught page errors', errors.length === 0, errors.join(' | '))

  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run()
