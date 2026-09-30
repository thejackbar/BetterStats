// Drives the REAL Add player form, the Fantasy new-player form and the player
// profile: matching a hand-made player to their PlayCricket profile.
//
// A player created by hand has no Cricket Australia identity, so their first
// synced game would mint a SECOND player and leave the one in the squad empty.
// The admin now has to choose before a player can be created: match the person
// and confirm they are joining THIS club, or say they are not on PlayCricket
// yet. This suite asserts that gate, what goes on the wire, and the Fantasy
// price suggestion that arrives once a previous club's figures have been read.
//
// The API is stubbed at the network layer and every stub MUTATES or records, so
// a screen cannot pass on an answer that disagrees with what it asked for.
//
//   node verify_player_identity_browser.mjs [http://localhost:5199]
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:5199'
let PASS = 0, FAIL = 0
const FAILURES = []
function check(label, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (ok) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); console.log(`  FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`) }
}


// Every read and press goes through these, so a build WITHOUT the feature is
// REPORTED check by check rather than dying on the first absent element and
// saying nothing about the rest.
const has = async (loc) => (await loc.count()) > 0
const press = async (loc) => { if (await has(loc)) { await loc.first().click(); return true } return false }
const put = async (loc, t) => { if (await has(loc)) { await loc.first().fill(t); return true } return false }
const textOf = async (loc) => ((await has(loc)) ? await loc.first().innerText() : '')
const valueOf = async (loc) => ((await has(loc)) ? await loc.first().inputValue() : '')
const disabled = async (loc) => ((await has(loc)) ? await loc.first().isDisabled() : false)

const SPENCER = '9292cde6-36c5-40a4-b843-0c530951ede8'
const TODD = 'aaaaaaaa-0000-4000-8000-000000000001'
const OUR_ORG = 'o-scarb'
const CLUB_A = '4578f08d-87d8-eb11-a7ad-2818780da0cc'
const CLUB_B = '65ce4bf0-87d8-eb11-a7ad-2818780da0cc'

const person = (id, name, clubs, extra = {}) => ({
  participant_id: id, name, clubs: clubs.map(([i, n]) => ({ id: i, name: n })),
  at_this_club: false, existing_player: null, ...extra,
})

let wire
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

function fresh() {
  wire = { searches: [], created: [], linked: [], prior: [], fantasyNew: [], profile: 0 }
}

const SEARCHES = {
  'spencer green': { candidates: [
    person(SPENCER, 'Spencer Green', [[CLUB_A, 'Toombul District Cricket Club'], [CLUB_B, 'QLD']], { at_this_club: true }),
    person(TODD, 'Todd Gill', [[CLUB_A, 'Leeming Spartan Cricket Club']], { existing_player: { id: 'p-todd', name: 'Gill, Todd' } }),
    person('eeeeeeee-0000-4000-8000-000000000009', 'Spencer Greene', [['x1', 'Somewhere CC']]),
  ], capped: false },
  'ben harris': { candidates: [
    person('b0000000-0000-4000-8000-000000000001', 'Ben Harris', [['c1', 'Alpha Cricket Club']]),
    person('b0000000-0000-4000-8000-000000000002', 'Ben Harris', [['c2', 'Beta Cricket Club']]),
  ], capped: true },
}

const PROFILE = (linked) => ({
  id: 'p-fred', name: 'Fat, Fred', display_name: 'Fat, Fred', display_name_override: null, player_role: null,
  skill_positions: [], batting_hand: null, bowling_action: null, bowling_type: null, is_opening_batsman: false,
  gender: null, is_player: true, status: 'active', email: null, phone: null, photo_url: null, hero_photo_url: null,
  playhq_id: null, identity_linked: linked, squad_team_id: null, is_overseas: false, overseas_country: null,
  is_public: true, is_financial_override: null, trained_override: null, shirt_number: null, date_of_birth: null, age: null,
  squad: null, snapshot: { form: [], availability: [], last_picked: null },
})

async function setup(page, { searchFail = false, priorScript = [] } = {}) {
  page.on('pageerror', (e) => { FAILURES.push(`page error: ${e.message}`); FAIL++ })
  await page.route(/\/api\//, (r) => json(r, {}))
  await page.route(/\/api\/auth\/me/, (r) => json(r, {
    id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'scarb', club_name: 'Scarborough CC', organisation_id: OUR_ORG,
    capabilities: ['*'], entitlements: { modules: ['fantasy'], status: 'active' },
  }))
  await page.route(/\/api\/teams(\?|$)/, (r) => json(r, []))
  await page.route(/\/api\/club-admin\/settings/, (r) => json(r, { player_name_format: 'last_first' }))
  await page.route(/\/api\/club-admin\/players$/, (r) => {
    if (r.request().method() === 'POST') {
      const body = JSON.parse(r.request().postData() || '{}')
      wire.created.push(body)
      return json(r, { id: 'p-new', name: `${body.last_name}, ${body.first_name}`, display_name: `${body.last_name}, ${body.first_name}`, identity_linked: !!body.participant_id })
    }
    return json(r, [{ id: 'p-fred', name: 'Fat, Fred', display_name: 'Fat, Fred', status: 'active', is_player: true }])
  })
  await page.route(/\/api\/club-admin\/player-identity\/search/, (r) => {
    const q = decodeURIComponent(new URL(r.request().url()).searchParams.get('q') || '')
    wire.searches.push(q)
    if (searchFail) return json(r, { detail: 'Too many searches, wait a moment and try again.' }, 429)
    return json(r, SEARCHES[q.toLowerCase()] || { candidates: [], capped: false })
  })
  await page.route(/\/api\/club-admin\/player-identity\/link/, (r) => {
    const body = JSON.parse(r.request().postData() || '{}')
    wire.linked.push(body)
    return json(r, { ok: true, linked: true, changed: true })
  })
  await page.route(/\/api\/players\/p-fred\/profile/, (r) => { wire.profile++; return json(r, PROFILE(wire.linked.length > 0)) })
  await page.route(/\/api\/players\/p-fred\/aliases/, (r) => json(r, []))
  await page.route(/\/api\/players\/p-todd\/profile/, (r) => { wire.profile++; return json(r, { ...PROFILE(true), id: 'p-todd', name: 'Gill, Todd', display_name: 'Gill, Todd' }) })
  await page.route(/\/api\/players\/p-todd\/aliases/, (r) => json(r, []))

  // Fantasy
  await page.route(/\/api\/club-admin\/fantasy\/season$/, (r) => json(r, {
    season: { id: 'fs1', season_year: 2026, name: 'Fantasy 2026', status: 'setup', rules: { price_window_years: 3 }, scoring: {} },
    link_token: null, link_active: false,
  }))
  await page.route(/\/api\/club-admin\/fantasy\/season\/fs1\/pool$/, (r) => json(r, { players: [] }))
  await page.route(/\/api\/club-admin\/fantasy\/season\/fs1\/pool\/new-player/, (r) => {
    const body = JSON.parse(r.request().postData() || '{}')
    wire.fantasyNew.push(body)
    return json(r, { ok: true, player_id: 'np1', identity_linked: !!body.participant_id })
  })
  let n = 0
  await page.route(/\/api\/club-admin\/fantasy\/season\/fs1\/prior-record/, (r) => {
    const u = new URL(r.request().url())
    wire.prior.push({ pid: u.searchParams.get('participant_id'), club: u.searchParams.get('club_id') })
    const step = priorScript[Math.min(n++, priorScript.length - 1)] || { status: 'unavailable' }
    return json(r, typeof step === 'function' ? step(u) : step)
  })
}

const SUGGESTION = {
  status: 'ready', found: true,
  suggestion: { role: 'bowler', price: 9.4, basis: { matches: 29, runs: 70, wickets: 50, catches: 3, years: [2026, 2025], from_year: 2024 } },
}

async function typeAndWait(page, selector, text) {
  await page.fill(selector, text)
  await page.waitForTimeout(900) // the search is debounced
}

async function run() {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  // ── Add player ────────────────────────────────────────────────────────────────
  console.log('-- Add player')
  fresh()
  let ctx = await browser.newContext({ viewport: { width: 1280, height: 1300 } })
  let page = await ctx.newPage()
  await setup(page)
  await page.goto(`${BASE}/admin/players`)
  await page.getByRole('button', { name: /add player/i }).click()
  await page.getByTestId('pc-match').waitFor({ timeout: 15000 }).catch(() => {})
  const seen = async (id) => (await page.getByTestId(id).count()) > 0
  const submit = page.getByRole('button', { name: /create player/i })

  check('the picker is on the form', await seen('pc-match'))
  check('Create is held back until they have chosen', await submit.isDisabled())
  check('and the form says why', (await page.locator('text=Match to PlayCricket first').count()) > 0)

  await page.fill('input[placeholder="e.g. John"]', 'Spencer')
  await page.fill('input[placeholder="e.g. Smith"]', 'Green')
  await page.waitForTimeout(1100)
  check('the name typed into the form is searched, First Last', wire.searches.includes('Spencer Green'))
  check('three people are listed', await page.getByTestId('pc-match-candidate').count(), 3)
  check('a person already registered at this club is marked', (await page.locator('text=Already registered at Scarborough CC').count()) > 0)
  const todd = page.getByTestId('pc-match-candidate').filter({ hasText: 'Todd Gill' })
  check('a person already in the roster is marked with who', (await textOf(todd)).includes('Already in your club as Gill, Todd'))
  check('and cannot be picked again', await todd.getByRole('button', { name: /this is them/i }).count(), 0)
  check('their clubs are shown so the right person can be picked', (await textOf(page.getByTestId('pc-match-candidate').first())).includes('Toombul District Cricket Club'))

  await press(page.getByTestId('pc-match-candidate').first().getByRole('button', { name: /this is them/i }))
  check('picking asks for confirmation, naming the club they are joining',
    (await textOf(page.getByTestId('pc-match-confirm'))).includes('joining Scarborough CC'))
  check('Create is still held back before they confirm', await submit.isDisabled())
  await press(page.getByTestId('pc-match-confirm-box'))
  check('confirming shows them as matched', await seen('pc-match-linked'))
  check('and releases Create', !(await submit.isDisabled()))
  await submit.click()
  await page.waitForTimeout(500)
  check('one player was created', wire.created.length, 1)
  check('the PlayCricket id went on the wire', wire.created[0]?.participant_id, SPENCER)
  check('with the name as typed', [wire.created[0]?.first_name, wire.created[0]?.last_name], ['Spencer', 'Green'])

  // Not on PlayCricket yet.
  await page.getByRole('button', { name: /add player/i }).click()
  await page.fill('input[placeholder="e.g. John"]', 'Newbie')
  await page.fill('input[placeholder="e.g. Smith"]', 'Nine')
  await page.waitForTimeout(1100)
  check('a name nobody has finds nobody, and says what to do', (await page.getByTestId('pc-match-empty').count()) > 0)
  check('Create is held back for them too', await submit.isDisabled())
  await press(page.getByTestId('pc-match-none'))
  check('saying they are not on PlayCricket releases Create', !(await submit.isDisabled()))
  await submit.click()
  await page.waitForTimeout(500)
  check('a second player was created', wire.created.length, 2)
  check('with NO identity on the wire', wire.created[1]?.participant_id, null)

  // Common name: narrow by club.
  await page.getByRole('button', { name: /add player/i }).click()
  await page.fill('input[placeholder="e.g. John"]', 'Ben')
  await page.fill('input[placeholder="e.g. Smith"]', 'Harris')
  await page.waitForTimeout(1100)
  check('a capped search offers a club filter', await seen('pc-match-club-filter'))
  check('both people are listed before filtering', await page.getByTestId('pc-match-candidate').count(), 2)
  await put(page.getByTestId('pc-match-club-filter'), 'beta')
  check('the club filter narrows the list', await page.getByTestId('pc-match-candidate').count(), 1)

  // Open the existing player instead of duplicating them.
  await page.fill('input[placeholder="e.g. John"]', 'Spencer')
  await page.fill('input[placeholder="e.g. Smith"]', 'Green')
  await page.waitForTimeout(1100)
  await press(page.getByTestId('pc-match-candidate').filter({ hasText: 'Todd Gill' }).getByRole('button', { name: /open that player/i }))
  await page.waitForTimeout(600)
  check('"Open that player" opens the existing record and closes the form', wire.profile > 0 && !(await seen('pc-match')))
  await ctx.close()

  // ── search unavailable ────────────────────────────────────────────────────────
  console.log('-- the search fails')
  fresh()
  ctx = await browser.newContext({ viewport: { width: 1280, height: 1300 } })
  page = await ctx.newPage()
  await setup(page, { searchFail: true })
  await page.goto(`${BASE}/admin/players`)
  await page.getByRole('button', { name: /add player/i }).click()
  await page.fill('input[placeholder="e.g. John"]', 'Spencer')
  await page.fill('input[placeholder="e.g. Smith"]', 'Green')
  await page.waitForTimeout(1100)
  check('a failed search says so', (await page.locator('text=Too many searches').count()) > 0)
  check('and does not trap the admin: they can still say not on PlayCricket', await page.getByTestId('pc-match-none').count(), 1)
  await ctx.close()

  // ── existing player: profile ──────────────────────────────────────────────────
  console.log('-- linking an existing player from their profile')
  fresh()
  ctx = await browser.newContext({ viewport: { width: 1280, height: 1500 } })
  page = await ctx.newPage()
  await setup(page)
  await page.goto(`${BASE}/admin/players`)
  await page.getByText('Fat, Fred').first().click()
  await page.getByTestId('pc-identity').waitFor({ timeout: 15000 }).catch(() => {})
  check('an unmatched player says so and offers to find them', (await textOf(page.getByTestId('pc-identity'))).includes('Not matched yet'))
  await press(page.getByTestId('pc-identity').getByRole('button', { name: /find on playcricket/i }))
  check('the profile picker has no "not on PlayCricket" escape (that is a create-time choice)', await page.getByTestId('pc-match-none').count(), 0)
  await put(page.getByTestId('pc-match-search'), 'Spencer Green')
  await page.waitForTimeout(1100)
  await press(page.getByTestId('pc-match-candidate').first().getByRole('button', { name: /this is them/i }))
  await press(page.getByTestId('pc-match-confirm-box'))
  check('nothing is written until they press Link', wire.linked.length, 0)
  await press(page.getByRole('button', { name: /link to this player/i }))
  await page.waitForTimeout(500)
  check('the link went to the right player with the right id', wire.linked[0], { player_id: 'p-fred', participant_id: SPENCER })
  check('the profile then reads as matched', (await page.getByTestId('pc-identity-linked').count()) > 0)
  await ctx.close()

  // ── Fantasy: price from a previous club ───────────────────────────────────────
  console.log('-- Fantasy new player and the price from a previous club')
  fresh()
  ctx = await browser.newContext({ viewport: { width: 1280, height: 1900 } })
  page = await ctx.newPage()
  await setup(page, { priorScript: [{ status: 'building' }, SUGGESTION, { status: 'unavailable' }] })
  await page.goto(`${BASE}/admin/fantasy/pool`)
  await page.getByTestId('fp-new-name').waitFor({ timeout: 15000 }).catch(() => {})
  const create = page.getByTestId('fp-new-create')
  await put(page.getByTestId('fp-new-name'), 'Spencer Green')
  await page.waitForTimeout(1100)
  check('Create & add is held back until they choose', await disabled(create))
  check('the name is searched in the shared picker', wire.searches.includes('Spencer Green'))
  await press(page.getByTestId('pc-match-candidate').first().getByRole('button', { name: /this is them/i }))
  await press(page.getByTestId('pc-match-confirm-box'))
  await page.getByTestId('fp-prior').waitFor({ timeout: 8000 }).catch(() => {})
  await page.getByTestId('fp-prior-building').waitFor({ timeout: 8000 }).catch(() => {})
  check('their previous clubs are offered, the first selected', wire.prior[0]?.club, CLUB_A)
  check('the first read says the club is being read for the first time', (await page.getByTestId('fp-prior-building').count()) > 0)
  await page.getByTestId('fp-prior-suggestion').waitFor({ timeout: 12000 }).catch(() => {})
  check('the poll keeps asking until it is ready', wire.prior.length >= 2)
  check('the suggestion names its basis', (await textOf(page.getByTestId('fp-prior-suggestion'))).includes('29 matches, 70 runs and 50 wickets'))
  check('and the caveat about boundaries', (await textOf(page.getByTestId('fp-prior-suggestion'))).includes("Boundaries aren't counted"))
  check('the role was filled in from it', await valueOf(page.getByTestId('fp-new-role')), 'bowler')
  check('and the price', await valueOf(page.getByTestId('fp-new-price')), '9.4')

  await put(page.getByTestId('fp-new-price'), '12')
  await press(page.locator('input[name="fp-prev-club"]').nth(1))
  await page.waitForTimeout(600)
  check('choosing another club asks about THAT club', wire.prior.at(-1)?.club, CLUB_B)
  check('a club with no record says so', (await page.locator('text=No Cricket Australia record for that club').count()) > 0)
  check("the admin's own price is not overwritten by a later answer", await valueOf(page.getByTestId('fp-new-price')), '12')

  await press(create)
  await page.waitForTimeout(500)
  check('the player was created with the identity, role and the admin price',
    [wire.fantasyNew[0]?.participant_id, wire.fantasyNew[0]?.role, wire.fantasyNew[0]?.price], [SPENCER, 'bowler', 12])
  await ctx.close()

  // ── layout ────────────────────────────────────────────────────────────────────
  console.log('-- layout')
  fresh()
  ctx = await browser.newContext({ viewport: { width: 390, height: 1400 } })
  page = await ctx.newPage()
  await setup(page)
  await page.goto(`${BASE}/admin/players`)
  await page.getByRole('button', { name: /add player/i }).click()
  await page.fill('input[placeholder="e.g. John"]', 'Spencer')
  await page.fill('input[placeholder="e.g. Smith"]', 'Green')
  await page.waitForTimeout(1100)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check('no horizontal overflow at 390px with the picker open', overflow <= 0)
  await ctx.close()

  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  for (const f of FAILURES) console.log('  - ' + f)
  process.exit(FAIL ? 1 : 0)
}

run().catch((e) => { console.error(e); process.exit(2) })
