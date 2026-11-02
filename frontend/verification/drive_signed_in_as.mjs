// Public player pages say who is signed in, and an error offers "sign out and sign in again".
//
// The case that started this: a player opened the Womens Medal link on a phone that was
// still signed in as somebody else. The page read "Only players who played in this game
// can vote at this club" with nothing to say whose name it was judging.
//
// Drives the REAL vote page in Chromium (390px phone) with the API stubbed at the network
// layer, and asserts what goes over the wire. Football's twin is driven at the end.
//
//   npx vite build --outDir /tmp/dist && npx vite preview --outDir /tmp/dist --port 5199 &
//   APP_URL=http://localhost:5199 node verification/drive_signed_in_as.mjs
import { launch, json, overflow, PHONE } from './mobile_harness.mjs'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOT = process.env.SHOT_DIR || '/tmp'
let failed = 0
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : `  ${extra}`}`); if (!ok) failed++ }

const TOKEN = 'TOKEN123'
const FX = 'b74c06c7-5b46-417e-a070-e3c1429010c4'
const KATE = { id: 'kate', display_name: 'Leary, Kate' }
const JESS = { id: 'jess', display_name: 'Smith, Jess' }
const TEAM = [KATE, { id: 'lil', display_name: 'Brown, Lilly-Kate' }, { id: 'cai', display_name: 'Sweeney, Caitlin' }, { id: 'can', display_name: 'Woodhams, Candice' }]
const club = { name: 'Applecross Cricket Club', primary_color: '#c8102e' }

async function run() {
  const { browser, page, errors } = await launch()
  // Who the cookie says is signed in. The server, not the page, owns this.
  const server = { who: JESS, submitFails: false }
  const sent = []

  const fixtureRow = { id: FX, opponent: "Thornlie Lioness's Senior Women", round: 'Round 4', round_key: 'round 4', date: '2026-11-01', home_away: 'HOME', state: 'open', voted: false }
  await page.route(new RegExp(`/api/public/votes/${TOKEN}`), async (r) => {
    const req = r.request(); const url = new URL(req.url()); const path = url.pathname.replace(/^.*\/public\/votes\/TOKEN123/, '')
    if (req.method() === 'POST') sent.push({ path, body: req.postData() ? JSON.parse(req.postData()) : null })
    const me = server.who ? { ...server.who, my_page: null } : null
    if (path === '/switch') { server.who = null; return json(r, { status: 'ok' }) }
    if (path === '/verify') { server.who = JSON.parse(req.postData()).player_id === 'kate' ? KATE : JESS; return json(r, { status: 'ok', player: server.who }) }
    if (path.endsWith('/ballot')) return server.submitFails ? json(r, { detail: 'That ballot could not be saved.' }, 400) : json(r, { status: 'ok' })
    if (path.startsWith('/fixtures/')) {
      // The wrong person is not on the list, so the page says they did not play.
      const onList = server.who && TEAM.some((p) => p.id === server.who.id)
      return json(r, {
        club, fixture: { id: FX, opponent: fixtureRow.opponent, round: 'Round 4', date: '2026-11-01', state: 'open' },
        ballot_values: [3, 2, 1], allow_self_vote: true, voter_mode: 'players', me,
        role: onList ? 'player' : (server.who ? 'none' : 'none'),
        reason: onList ? null : (server.who ? 'did_not_play' : 'verify_required'),
        is_chosen: false, players: onList ? TEAM.map((p) => ({ id: p.id, name: p.display_name })) : [], my_ballot: null,
      })
    }
    return json(r, {
      club, medal: { id: 'm1', name: 'Womens Medal' }, require_pin: true, voter_mode: 'players',
      allow_non_participants: false, allow_self_vote: true, ballot_values: [3, 2, 1], me,
      players: [{ id: 'kate', display_name: KATE.display_name, has_phone: true }, { id: 'jess', display_name: JESS.display_name, has_phone: true }],
      grades: [], rounds: [], team: null, round_key: null, q: null,
      fixtures: server.who && (server.who.id === 'kate') ? [fixtureRow] : [],
    })
  })

  // ── 1. Signed in as somebody who did not play ─────────────────────────────
  await page.goto(`${BASE}/vote/${TOKEN}?fixture=${FX}`)
  await page.waitForSelector('[data-signed-in-as]', { timeout: 8000 }).catch(() => {})
  const strip = await page.locator('[data-signed-in-as]').count()
  check('top of the page says who is signed in', strip === 1)
  check('...and it is the signed-in person', (await page.locator('[data-signed-in-name]').first().textContent().catch(() => '')) === 'Smith, Jess')
  const body1 = await page.locator('body').innerText()
  check('the "did not play" message is shown', /Only players who played in this game can vote/.test(body1))
  check('...with a hint to sign out and in again, naming the person', /You are signed in as Smith, Jess/.test(body1) && /sign out and sign in again/.test(body1))
  const first = await page.locator('[data-signed-in-as]').first().boundingBox().catch(() => null)
  const logo = await page.locator('img[alt=""], span.font-display').first().boundingBox().catch(() => null)
  check('the strip sits above the club header', !!(first && logo && first.y < logo.y), JSON.stringify({ first, logo }))
  const o1 = await overflow(page, PHONE.width)
  check('no sideways overflow at 390px (signed in, error)', o1.over <= 0, JSON.stringify(o1))
  await page.screenshot({ path: `${SHOT}/signed-in-as-1-wrong-person.png` })

  // ── 2. The hint signs out, then she picks her own name ────────────────────
  await page.locator('[data-sign-in-hint] button').click()
  await page.waitForSelector('text=Find your name to vote', { timeout: 8000 })
  check('the hint sent exactly one sign-out', sent.filter((s) => s.path === '/switch').length === 1, JSON.stringify(sent))
  check('the strip is gone once signed out', (await page.locator('[data-signed-in-as]').count()) === 0)

  await page.getByText(KATE.display_name, { exact: false }).first().click()
  await page.locator('input[inputmode="numeric"], input[type="tel"], input[type="password"]').first().fill('1234')
  await page.getByRole('button', { name: /continue|verify|next|sign|vote|check/i }).first().click().catch(async () => { await page.keyboard.press('Enter') })
  await page.waitForSelector('[data-signed-in-name]', { timeout: 8000 })
  const verify = sent.find((s) => s.path === '/verify')
  check('verify sent her id and PIN', verify && verify.body.player_id === 'kate' && verify.body.pin === '1234', JSON.stringify(verify))
  check('ballot page now names Kate', (await page.locator('[data-signed-in-name]').first().textContent()) === 'Leary, Kate')
  check('...and offers the team to vote for', (await page.locator('body').innerText()).includes('Brown, Lilly-Kate'))
  await page.screenshot({ path: `${SHOT}/signed-in-as-2-kate-ballot.png` })
  const o2 = await overflow(page, PHONE.width)
  check('no sideways overflow at 390px (ballot)', o2.over <= 0, JSON.stringify(o2))

  // ── 3. An error while signed in carries the hint ──────────────────────────
  server.submitFails = true
  for (const n of ['Brown, Lilly-Kate', 'Sweeney, Caitlin', 'Woodhams, Candice']) await page.getByText(n, { exact: false }).first().click()
  await page.getByRole('button', { name: /submit my votes/i }).click()
  await page.waitForSelector('text=That ballot could not be saved.', { timeout: 8000 })
  const body3 = await page.locator('body').innerText()
  check('a failed submit shows the sign-out hint', /You are signed in as Leary, Kate/.test(body3) && /sign out and sign in again/.test(body3))
  await page.screenshot({ path: `${SHOT}/signed-in-as-3-error-hint.png` })

  // ── 4. Control for the above: nobody signed in shows neither ──────────────
  server.who = null
  await page.context().clearCookies()
  await page.goto(`${BASE}/vote/${TOKEN}`)
  await page.waitForSelector('text=Find your name to vote', { timeout: 8000 })
  check('signed out: no strip', (await page.locator('[data-signed-in-as]').count()) === 0)
  check('signed out: no hint', (await page.locator('[data-sign-in-hint]').count()) === 0)

  // ── 5. Net check-in: a returning player's refused check-in carries the hint ──
  const nets = { who: JESS, switched: 0 }
  await page.route(/\/api\/public\/net-checkin\/NETTOKEN/, async (r) => {
    const path = new URL(r.request().url()).pathname.replace(/^.*\/net-checkin\/NETTOKEN/, '')
    if (path === '/switch') { nets.who = null; nets.switched++; return json(r, { status: 'ok' }) }
    if (path === '/check-in') return json(r, { detail: 'You are not on the list for these nets.' }, 403)
    return json(r, {
      club, require_pin: true, allow_registration: false, squads: [],
      sessions: [{ id: 's1', label: 'Tuesday nets', session_date: '2026-11-03' }],
      players: [{ id: 'kate', display_name: KATE.display_name, has_phone: true }],
      me: nets.who ? { ...nets.who, checked_in: false } : null,
    })
  })
  await page.goto(`${BASE}/nets-checkin/NETTOKEN`)
  await page.getByRole('button', { name: /^check in$/i }).click({ timeout: 8000 })
  await page.waitForSelector('text=You are not on the list for these nets.', { timeout: 8000 })
  const bodyN = await page.locator('body').innerText()
  check('nets: a refused check-in shows the sign-out hint naming the person', /You are signed in as Smith, Jess/.test(bodyN) && /sign out and sign in again/.test(bodyN))
  await page.locator('[data-sign-in-hint] button').click()
  await page.waitForSelector('text=Search your name', { timeout: 8000 }).catch(() => {})
  check('nets: the hint signs them out', nets.switched === 1)
  check('nets: no sideways overflow at 390px', (await overflow(page, PHONE.width)).over <= 0)

  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
}

await run()
console.log(failed ? `\n${failed} FAILED` : '\nall passed')
process.exit(failed ? 1 : 0)
