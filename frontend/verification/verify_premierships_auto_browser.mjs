// Drives the three screens automatic premierships touch, in Chromium, API stubbed at the network layer:
// the club's Premierships page, a grand-final scorecard, and the Awards admin panel.
//
//   npx vite build && npx vite preview --port 5199 &
//   node verification/verify_premierships_auto_browser.mjs [baseUrl]
//
// Checks what is drawn, the exact requests on the wire (preview is a GET, "Add them" is a POST, and
// nothing is written before it is pressed), that a hand-typed flag with no scorecard draws no link, that
// a game with no premiership draws no banner, and 390px for overflow.
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const CLUB = { id: 'c1', name: 'Leederville Cricket Club', slug: 'leederville', is_active: true }
const GF = '250a6886-5ae7-4f16-991a-fc41b42af1f0'
const SEMI = '11111111-5ae7-4f16-991a-fc41b42af1f0'

const PREMS = { premierships: [
  { season: '2025/26', year: 2025, team: 'F Grade', competition: null, game_id: GF, player_count: 2,
    game: { id: GF, played_at: '2026-03-14', opponent: 'Rivals F', round_name: 'Grand Final' },
    players: [
      { player_id: 'p1', name: 'Caden Smith', photo_url: null, roles: [], detail: 'Captain' },
      { player_id: 'p2', name: 'Bob Bell', photo_url: null, roles: [], detail: null }] },
  { season: '1998/99', year: 1998, team: 'A Grade', competition: null, game_id: null, game: null, player_count: 1,
    players: [{ player_id: null, name: 'Hal Hist', photo_url: null, roles: [], detail: null }] },
] }

const SCORECARD = {
  id: GF, organisation_id: CLUB.id, home_team: 'Leederville F', away_team: 'Rivals F', winning_team: 'Leederville F',
  result: 'WIN', played_at: '2026-03-14', venue: 'Leederville Oval', batting: [], bowling: [], opp_batting: [],
  opp_bowling: [], innings_totals: {}, home_away_known: true,
}

const ADMIN = {
  id: 'u1', username: 'pat', display_name: 'Pat', role: 'club_admin', club_id: CLUB.id, club_slug: CLUB.slug,
  is_primary_admin: true, can_switch_clubs: false,
  entitlements: { modules: [], status: 'active', billing_modules: [] }, capabilities: ['manage_awards'],
}

async function stub(page, state, { signedIn = false } = {}) {
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    const method = req.method()
    state.calls.push({ method, p, q: url.search })
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p === '/auth/me') return signedIn ? json(ADMIN) : json({ detail: 'Not authenticated' }, 401)
    if (p === `/clubs/${CLUB.slug}`) return json(CLUB)
    if (p === `/organisations/${CLUB.id}`) return json(CLUB)
    if (p === `/honours/${CLUB.id}/premierships/squad` && method === 'POST') {
      const b = JSON.parse(req.postData() || '{}')
      state.squadPosts = [...(state.squadPosts || []), b]
      if (b.role === 'Man of Steel') return json({ detail: 'Choose Player of the Match, 12th Man or 13th Man.' }, 400)
      const card = state.squad.premierships.find(c => c.game_id === b.game_id)
      const pl = card.players.find(x => x.player_id === b.player_id)
      if (b.action === 'role' && pl) pl.roles = b.on ? [...pl.roles, b.role] : pl.roles.filter(r => r !== b.role)
      if (b.action === 'add') { card.players.push({ player_id: b.player_id, name: 'Dan Day', photo_url: null, roles: b.role ? [b.role] : [], detail: null }); card.player_count += 1 }
      if (b.action === 'remove') { card.players = card.players.filter(x => x.player_id !== b.player_id); card.player_count -= 1 }
      return json({ ok: true })
    }
    if (p === `/honours/${CLUB.id}/premierships`) return json(state.squad || PREMS)
    if (p === '/players') return json([{ id: 'p1', name: 'Caden Smith' }, { id: 'p2', name: 'Bob Bell' }, { id: 'p9', name: 'Dan Day' }])
    if (p === `/honours/games/${GF}/premierships`) {
      return json({ premierships: [{ org_id: CLUB.id, slug: CLUB.slug, club_name: CLUB.name, team: 'F Grade', season: '2025/26', players: 2 }] })
    }
    if (p === `/honours/games/${SEMI}/premierships`) return json({ premierships: [] })
    if (p === `/games/${GF}/scorecard` || p === `/games/${SEMI}/scorecard`) return json({ ...SCORECARD, id: p.split('/')[2] })
    if (p === `/honours/${CLUB.id}/premierships/auto`) {
      return method === 'POST'
        ? json({ applied: true, wins: 4, create: 3, link: 1, delete: 0, unresolved: [] })
        : json({ applied: false, wins: 4, create: 3, link: 1, delete: 0, update_detail: 0, unlink: 0, covered: 0,
                 unresolved: [{ grade_name: 'A Grade', opponent: 'Rivals A', played_at: '2026-03-21' }] })
    }
    if (p === '/players/p1/stats') return json({ player: { id: 'p1', name: 'Caden Smith', display_name: 'Caden Smith', organisation_id: CLUB.id, is_public: true },
      career_batting: { innings: 36, total_runs: 177, games: 45 }, career_bowling: { total_wickets: 60 } })
    if (p === '/achievements') return json([
      { id: 1, org_id: CLUB.id, player_id: 'p1', player_name: 'Caden Smith', season: '2025/26', season_end: null,
        category: 'Premiership', subcategory: 'F Grade', achievement: 'Premiership', detail: 'Captain', game_id: GF, auto_created: true },
      { id: 2, org_id: CLUB.id, player_id: 'p1', player_name: 'Caden Smith', season: '2023/24', season_end: null,
        category: 'Premiership', subcategory: 'H Grade', achievement: 'Premiership', detail: null, game_id: null, auto_created: false },
    ])
    if (route.request().method() === 'GET') return json([])
    return json({ detail: 'not stubbed' }, 404)
  })
}

const noOverflow = page => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)
const browser = await chromium.launch({ executablePath: EXECUTABLE })

for (const width of [1280, 390]) {
  console.log(`== ${width}px`)
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  const errors = []

  // 1. Premierships page
  let page = await ctx.newPage(); page.on('pageerror', e => errors.push(e.message))
  let state = { calls: [] }; await stub(page, state)
  await page.goto(`${BASE}/${CLUB.slug}/premierships`)
  await page.waitForSelector('main >> text=Scorecard')
  const links = await page.locator('a', { hasText: 'Scorecard' }).all()
  ck('exactly one card links to a scorecard', links.length === 1, `got ${links.length}`)
  ck('the link goes to the grand final with the club on the query',
    (await links[0].getAttribute('href')) === `/games/${GF}?org=${CLUB.id}`, await links[0].getAttribute('href'))
  const body = await page.locator('main').innerText()
  ck('the card names the opponent and the day', body.includes('v Rivals F') && body.includes('14 Mar 2026'))
  // The page writes names as "Smith, Caden" and labels in capitals (CSS uppercase), so check in that casing.
  ck('the hand-typed flag still renders, with no scorecard line', body.includes('Hist, Hal') && body.includes('A GRADE'))
  ck('no horizontal overflow', await noOverflow(page))
  if (width === 1280) await page.screenshot({ path: 'verification/shots/premierships_auto_page.png' })
  await page.close()

  // 2. Scorecard banner, and no banner on a game that was no premiership
  page = await ctx.newPage(); page.on('pageerror', e => errors.push(e.message))
  state = { calls: [] }; await stub(page, state)
  await page.goto(`${BASE}/games/${GF}`)
  await page.waitForSelector('[data-testid="premiership-banner"]')
  const banner = await page.locator('[data-testid="premiership-banner"]').innerText()
  ck('the banner says who won which flag with how many players',
    banner.includes('Leederville Cricket Club won the F Grade · 2025/26 grand final with 2 players'), banner)
  ck('and links to the club\'s Premierships page',
    (await page.locator('[data-testid="premiership-banner"] a').getAttribute('href')) === `/${CLUB.slug}/premierships`)
  ck('no horizontal overflow', await noOverflow(page))
  if (width === 1280) await page.screenshot({ path: 'verification/shots/premierships_auto_scorecard.png' })
  await page.goto(`${BASE}/games/${SEMI}`)
  await page.waitForSelector('main >> text=Leederville Oval')
  await page.waitForTimeout(400)
  ck('a game that was not a premiership has no banner', (await page.locator('[data-testid="premiership-banner"]').count()) === 0)
  ck('and the banner could have drawn (the request was made)',
    state.calls.some(c => c.p === `/honours/games/${SEMI}/premierships`))
  await page.close()

  // 3. Admin panel
  page = await ctx.newPage(); page.on('pageerror', e => errors.push(e.message))
  state = { calls: [] }; await stub(page, state, { signedIn: true })
  await page.goto(`${BASE}/admin/awards`)
  await page.waitForSelector('[data-testid="premiership-auto-panel"]')
  // The usage beacons (heartbeat, events) are the app's own telemetry POSTs, not this screen's writes.
  const writes = () => state.calls.filter(c => c.method !== 'GET' && !c.p.startsWith('/usage/'))
  ck('opening the screen writes nothing', writes().length === 0, JSON.stringify(writes()))
  ck('the auto row is tagged and links to its scorecard',
    (await page.getByText('AUTO', { exact: true }).count()) === 1 && (await page.locator(`a[href="/games/${GF}?org=${CLUB.id}"]`).count()) === 1,
    `${await page.getByText('AUTO', { exact: true }).count()} tags, ${await page.locator(`a[href^="/games/"]`).count()} links`)
  await page.click('text=Check scorecards')
  await page.waitForSelector('[data-testid="premiership-auto-report"]')
  const rep = await page.locator('[data-testid="premiership-auto-report"]').innerText()
  ck('the preview reports what it would add', rep.includes('4 grand finals won') && rep.includes('3 honours to add') && rep.includes('1 typed in by hand'), rep)
  ck('and names a grand final with no winner', (await page.locator('[data-testid="premiership-auto-panel"]').innerText()).includes('A Grade v Rivals A'))
  ck('the preview was a GET and wrote nothing', writes().length === 0, JSON.stringify(writes()))
  ck('no horizontal overflow', await noOverflow(page))
  if (width === 1280) await page.screenshot({ path: 'verification/shots/premierships_auto_admin.png' })
  await page.click('text=Add them')
  await page.waitForSelector('[data-testid="premiership-auto-done"]')
  const posts = state.calls.filter(c => c.p.endsWith('/premierships/auto') && c.method === 'POST')
  ck('Add them is one POST to the club\'s own route', posts.length === 1 && posts[0].p === `/honours/${CLUB.id}/premierships/auto`)
  await page.close()

  // 4. The honour badge on the player's profile
  page = await ctx.newPage(); page.on('pageerror', e => errors.push(e.message))
  state = { calls: [] }; await stub(page, state)
  await page.goto(`${BASE}/players/p1`)
  await page.getByText('HONOURS', { exact: true }).first().click()
  await page.waitForSelector('.hb-card')
  ck('both Premiership badges draw', (await page.locator('.hb-card').count()) === 2)
  const badgeLinks = await page.locator('a.hb-scorecard').all()
  ck('only the badge with a scorecard links to it', badgeLinks.length === 1
    && (await badgeLinks[0].getAttribute('href')) === `/games/${GF}?org=${CLUB.id}`)
  ck('no horizontal overflow', await noOverflow(page))
  if (width === 1280) await page.screenshot({ path: 'verification/shots/premierships_auto_profile.png' })
  await page.close()

  // 5. The squad editor
  const fresh = () => ({ calls: [], squad: JSON.parse(JSON.stringify(PREMS)) })
  page = await ctx.newPage(); page.on('pageerror', e => errors.push(e.message))
  state = fresh(); await stub(page, state)
  await page.goto(`${BASE}/${CLUB.slug}/premierships`)
  await page.waitForSelector('main >> text=Scorecard')
  ck('a public visitor sees no Edit squad', (await page.getByText('Edit squad').count()) === 0)
  await page.close()

  page = await ctx.newPage(); page.on('pageerror', e => errors.push(e.message))
  state = fresh(); await stub(page, state, { signedIn: true })
  await page.goto(`${BASE}/${CLUB.slug}/premierships`)
  await page.waitForSelector('main >> text=Scorecard')
  ck('an admin sees Edit squad on the card that links to a scorecard only', (await page.getByText('Edit squad').count()) === 1)
  await page.getByText('Edit squad').click()
  await page.waitForSelector('[data-testid="squad-editor"]')
  ck('the editor lists the squad with a role button for each part', (await page.locator('[data-testid="squad-editor"] li').count()) === 2)
  const bob = page.locator('[data-testid="squad-editor"] li', { hasText: 'Bell, Bob' })
  await bob.getByRole('button', { name: '12th Man' }).click()
  await page.waitForFunction(() => document.querySelector('[data-testid="squad-editor"]'))
  ck('marking a 12th Man sends exactly that change',
    JSON.stringify(state.squadPosts.at(-1)) === JSON.stringify({ game_id: GF, action: 'role', player_id: 'p2', role: '12th Man', on: true }),
    JSON.stringify(state.squadPosts.at(-1)))
  await page.waitForFunction(() => [...document.querySelectorAll('[data-testid="squad-editor"] li')]
    .find(li => li.innerText.includes('Bell, Bob'))?.querySelector('button[aria-pressed="true"]'))
  ck('and the button shows it is on once the card reloads', true)
  await bob.getByRole('button', { name: '12th Man' }).click()
  await page.waitForFunction(() => ![...document.querySelectorAll('[data-testid="squad-editor"] li')]
    .find(li => li.innerText.includes('Bell, Bob'))?.querySelector('button[aria-pressed="true"]'))
  ck('pressing it again unmarks it', JSON.stringify(state.squadPosts.at(-1)) ===
    JSON.stringify({ game_id: GF, action: 'role', player_id: 'p2', role: '12th Man', on: false }))

  await page.getByLabel('Player to add').selectOption('p9')
  await page.getByLabel('Their part').selectOption('12th Man')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="squad-editor"] li').length === 3)
  ck('adding a 12th Man sends the player and the part', JSON.stringify(state.squadPosts.at(-1)) ===
    JSON.stringify({ game_id: GF, action: 'add', player_id: 'p9', role: '12th Man' }), JSON.stringify(state.squadPosts.at(-1)))
  ck('and they join the list', (await page.locator('[data-testid="squad-editor"]').innerText()).includes('Day, Dan'))
  ck('a player already on the card is not offered again',
    !(await page.getByLabel('Player to add').innerText()).includes('Bob Bell')
    && !(await page.getByLabel('Player to add').innerText()).includes('Bell, Bob'))
  if (width === 1280) await page.screenshot({ path: 'verification/shots/premierships_auto_editor.png' })
  ck('no horizontal overflow with the editor open', await noOverflow(page))

  page.once('dialog', d => d.dismiss())
  await page.locator('[data-testid="squad-editor"] li', { hasText: 'Day, Dan' }).getByRole('button', { name: /Remove/ }).click()
  await page.waitForTimeout(300)
  ck('cancelling the confirm removes nobody and sends nothing',
    state.squadPosts.at(-1).action === 'add' && (await page.locator('[data-testid="squad-editor"] li').count()) === 3)
  page.once('dialog', d => d.accept())
  await page.locator('[data-testid="squad-editor"] li', { hasText: 'Day, Dan' }).getByRole('button', { name: /Remove/ }).click()
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="squad-editor"] li').length === 2)
  ck('removing sends exactly that', JSON.stringify(state.squadPosts.at(-1)) ===
    JSON.stringify({ game_id: GF, action: 'remove', player_id: 'p9' }), JSON.stringify(state.squadPosts.at(-1)))
  await page.getByText('Done').click()
  ck('Done returns to the plain card', (await page.locator('[data-testid="squad-editor"]').count()) === 0)
  await page.close()

  ck(`no page errors at ${width}px`, errors.length === 0, errors.join(' | '))
  await ctx.close()
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
