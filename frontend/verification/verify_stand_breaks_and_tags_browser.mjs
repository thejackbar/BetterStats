// Drives the real screens in Chromium with the API stubbed at the network layer (v9.145.0):
//   * the match page: an unbroken stand reads 12*, and a club admin's Premiers tick sends the tag;
//   * the fall-of-wickets editor: a retirement and the unbroken tick go on the wire as typed;
//   * the admin Premierships screen: a pasted match link is tagged, and a listed tag can be changed;
//   * Partnership Records: a record links to its match, and an edit leaves an untouched link alone;
//   * 390px: none of them overflows sideways.
//
//   npx vite build && npx vite preview --port 5198 &
//   node frontend/verification/verify_stand_breaks_and_tags_browser.mjs [baseUrl]
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SHOTS = process.env.SHOTS || '/tmp'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const ORG = 'org1'
const GID = 'bbbbbbbb-0000-0000-0000-000000000001'
const LINK = 'https://play.cricket.com.au/match/cccccccc-0000-0000-0000-000000000009/piara-v-rivals'
const NAMES = ['Payne', 'Hall', 'Bivens', 'Sweet', 'Cox', 'Menezes', 'Ito', 'Lee']
const pid = n => `g-${n.toLowerCase()}`
const OUT = ['Payne', 'Hall', 'Bivens', 'Sweet', 'Menezes', 'Cox']
const FOW6 = [[1, 73, 'Payne'], [2, 150, 'Hall'], [3, 331, 'Bivens'], [4, 356, 'Sweet'], [5, 381, 'Menezes'], [6, 400, 'Cox']]

const ADMIN = {
  id: 'u1', username: 'pat', display_name: 'Pat', role: 'club_admin', club_id: ORG, club_slug: 'piara',
  is_primary_admin: true, entitlements: { modules: ['admin'], status: 'active', billing_modules: [] },
}

const scorecard = {
  id: GID, home_team: 'Piara Waters', away_team: 'Rivals', home_away_known: true, innings_order_known: true,
  played_at: '2026-03-14', result: 'WIN', winning_team: 'Piara Waters', organisation_id: null, is_manual: false,
  grade: { id: 'g1', name: "Women's A Grade", raw_name: "Women's A Grade" }, season: { id: 's1', name: '2025/26' },
  innings_totals: { 1: { runs: 412, wickets: 6, extras: 9 } },
  batting: [], bowling: [], opp_batting: [], opp_bowling: [], fielding: [],
  fall_of_wickets: FOW6.map(([w, s, n]) => ({ innings_number: 1, wicket_number: w, score_at_fall: s, player_name: `${n[0]} ${n}` })),
  partnerships: [
    { innings_number: 1, wicket_number: 6, runs: 19, batter1_name: 'C Cox', batter2_name: 'I Ito', is_unbroken: false },
    { innings_number: 1, wicket_number: 7, runs: 12, batter1_name: 'I Ito', batter2_name: 'L Lee', is_unbroken: true },
  ],
}

const EDITOR = {
  game_id: GID,
  innings: [{
    innings_number: 1, edited: false, wickets: 6, innings_total: 412,
    batters: OUT.map((n, i) => ({ participant_id: pid(n), name: `${n[0]} ${n}`, bat_order: i + 1, runs: 20 })),
    all_batters: NAMES.map((n, i) => ({ participant_id: pid(n), name: `${n[0]} ${n}`, bat_order: i + 1, runs: 20 })),
    fow: FOW6.map(([w, s, n]) => ({ wicket_number: w, score_at_fall: s, participant_id: pid(n), batter_name: n })),
    retirements: [], unbroken: false, unbroken_score: null,
    stands: [], missing: {},
  }],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(url, { admin = true, width = 1280, tags = [] } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1100 } })
  const page = await ctx.newPage()
  const seen = { puts: [], patches: [], posts: [], errors: [], bannerReads: 0, tagList: tags }
  page.on('pageerror', e => seen.errors.push(String(e)))
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    const m = req.method()
    const body = () => JSON.parse(req.postData() || '{}')
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p === '/auth/me') return admin ? json(ADMIN) : json({ detail: 'Not authenticated' }, 401)
    if (p === `/games/${GID}/scorecard` || /^\/games\/[^/]+\/scorecard/.test(p)) return json(scorecard)
    if (p === `/honours/games/${GID}/premierships`) {
      seen.bannerReads++
      return json({ premierships: seen.tagged ? [{ org_id: ORG, club_name: 'Piara Waters CC', team: "Women's A Grade", season: '2025/26', players: 3 }] : [] })
    }
    if (p === `/honours/${ORG}/premierships/tags/${GID}`) return json({ game_id: GID, kind: null, won: false, players: 0, reason: null })
    if (p === `/honours/${ORG}/premierships/tags` && m === 'GET') return json({ tags: seen.tagList })
    if (p === `/honours/${ORG}/premierships/tags` && m === 'PUT') {
      const b = body(); seen.puts.push(b)
      if (/playhq/.test(b.match)) return json({ detail: "That's a playhq.com link, which uses a different match ID." }, 422)
      seen.tagged = b.kind === 'grand_final'
      const gid = b.match.match(/[0-9a-f-]{36}/)?.[0] || b.match
      const st = { game_id: gid, kind: b.kind, won: b.won, players: b.kind === 'grand_final' ? 3 : 0, reason: null }
      seen.tagList = b.kind ? [{ ...st, grade_name: "Women's A Grade", opponent: 'Rivals', played_at: '2026-03-14', round_name: 'Round 16' }] : []
      return json(st)
    }
    if (/\/fall-of-wickets\/editor$/.test(p)) return json(EDITOR)
    if (/\/fall-of-wickets\/1$/.test(p) && m === 'PUT') {
      const b = body(); seen.puts.push(b)
      return json({
        summary: 'Fall of wickets for innings 1: 6 of 6 wickets entered, 1 retirement, the unbroken stand, 8 partnerships worked out.',
        warnings: [],
        innings: { ...EDITOR.innings[0], edited: true, retirements: b.retirements, unbroken: b.unbroken, unbroken_score: 412,
          stands: [{ wicket_number: 7, runs: 12, batter1_name: 'I Ito', batter2_name: 'L Lee', is_unbroken: true }] },
      })
    }
    if (p === '/club-admin/partnership-records' && m === 'GET') {
      return json([{ id: 7, batter1_name: 'Ann Able', batter2_name: 'Ben Bold', grade_name: "Women's A Grade", season_year: 2025,
        wicket_number: 8, runs: 41, is_not_out: true, notes: null, linked_game_id: GID, batter1_id: null, batter2_id: null }])
    }
    if (/^\/club-admin\/partnership-records\/7$/.test(p) && m === 'PATCH') { seen.patches.push(body()); return json({ status: 'updated' }) }
    if (/^\/club-admin\/partnership-records$/.test(p) && m === 'POST') { seen.posts.push(body()); return json({ id: 8 }) }
    return json(m === 'GET' && /players|grades|seasons|partnership-records/.test(p) ? [] : {})
  })
  await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' })
  return { ctx, page, seen }
}

const overflow = page => page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)

// ── Match page ──────────────────────────────────────────────────────────────
{
  const { ctx, page, seen } = await open(`/games/${GID}`, { admin: false })
  await page.waitForSelector('text=PARTNERSHIPS', { timeout: 20000 })
  ck('match page: the unbroken stand reads 12*', await page.getByText('12*', { exact: true }).count() === 1)
  ck('match page: a stand a wicket ended has no star', await page.getByText('19*', { exact: true }).count() === 0
    && await page.getByText('19', { exact: true }).count() >= 1)
  ck('match page: the public sees no Premiers tick', await page.getByTestId('premiers-tick').count() === 0)
  ck('match page: no script errors (public)', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}
{
  const { ctx, page, seen } = await open(`/games/${GID}`)
  await page.waitForSelector('[data-testid="premiers-tick"]', { timeout: 20000 })
  const before = seen.bannerReads
  await page.locator('#premiers-tick').click()
  await page.waitForSelector('text=Premiership recorded for 3 players from this match.')
  ck('match page: the tick sends Grand final, won, for this match',
    JSON.stringify(seen.puts.at(-1)) === JSON.stringify({ match: GID, kind: 'grand_final', won: true }), JSON.stringify(seen.puts))
  await page.waitForSelector('[data-testid="premiership-banner"]')
  ck('match page: the banner reloads and shows the flag', seen.bannerReads > before)
  ck('match page: no script errors (admin)', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}

// ── Fall-of-wickets editor ──────────────────────────────────────────────────
for (const width of [1280, 390]) {
  const { ctx, page, seen } = await open(`/games/${GID}`, { width })
  await page.waitForSelector('text=FALL OF WICKETS', { timeout: 20000 })
  await page.getByRole('button', { name: 'EDIT' }).click()
  await page.waitForSelector('text=RETIREMENTS')
  await page.getByRole('button', { name: '+ ADD A RETIREMENT' }).click()
  await page.locator('input[aria-label="Score at retirement 1"]').fill('200')
  await page.locator('select[aria-label="Batter who retired, retirement 1"]').selectOption(pid('Sweet'))
  await page.locator('input[aria-label="Wickets down at retirement 1"]').fill('2')
  ck(`editor ${width}: a batter who is not out can retire (Ito is offered)`,
    await page.locator(`select[aria-label="Batter who retired, retirement 1"] option[value="${pid('Ito')}"]`).count() === 1)
  await page.getByLabel('Last partnership unbroken at the end of the innings').check()
  ck(`editor ${width}: the end score defaults to the card total`,
    await page.locator('input[aria-label="Score at the end of the innings"]').getAttribute('placeholder') === '412')
  if (width === 390) {
    ck('editor 390: no sideways overflow', !(await overflow(page)))
    await page.screenshot({ path: `${SHOTS}/fow_retire_390.png`, fullPage: true })
  }
  await page.getByRole('button', { name: 'SAVE WICKETS' }).click()
  await page.waitForSelector('text=Unbroken 7th wicket partnership: 12*', { timeout: 10000 })
  const put = seen.puts.at(-1) || {}
  ck(`editor ${width}: the retirement goes on the wire as typed`,
    JSON.stringify(put.retirements) === JSON.stringify([{ participant_id: pid('Sweet'), score: 200, after_wicket: 2 }]), JSON.stringify(put))
  ck(`editor ${width}: with the unbroken tick and a blank end score`, put.unbroken === true && put.unbroken_score === null)
  ck(`editor ${width}: and all six wickets`, (put.rows || []).length === 6)
  if (width === 1280) await page.screenshot({ path: `${SHOTS}/fow_retire_desktop.png` })
  ck(`editor ${width}: no script errors`, seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}

// ── Admin Premierships ──────────────────────────────────────────────────────
for (const width of [1280, 390]) {
  const { ctx, page, seen } = await open('/admin/premierships', { width })
  await page.waitForSelector('text=MATCH LINK OR ID', { timeout: 20000 })
  ck(`premierships ${width}: an empty list says so`, await page.getByText('No matches tagged yet.', { exact: false }).count() === 1)
  await page.locator('[data-testid="tag-form"] input[placeholder^="https://play.cricket"]').fill('https://www.playhq.com/x/y/z/game-centre/abc123')
  await page.getByRole('button', { name: 'TAG MATCH' }).click()
  await page.waitForSelector("text=That's a playhq.com link", { timeout: 10000 })
  ck(`premierships ${width}: a playhq link is refused with the reason`, true)
  await page.locator('[data-testid="tag-form"] input[placeholder^="https://play.cricket"]').fill(LINK)
  await page.getByLabel('We won the premiership').check()
  await page.getByRole('button', { name: 'TAG MATCH' }).click()
  await page.waitForSelector('text=Premiership recorded for 3 players.', { timeout: 10000 })
  ck(`premierships ${width}: the pasted link is sent with Grand final and won`,
    JSON.stringify(seen.puts.at(-1)) === JSON.stringify({ match: LINK, kind: 'grand_final', won: true }), JSON.stringify(seen.puts.at(-1)))
  ck(`premierships ${width}: the list shows the tagged match`, await page.getByText('GRAND FINAL · WON').count() === 1)
  if (width === 390) {
    ck('premierships 390: no sideways overflow', !(await overflow(page)))
    await page.screenshot({ path: `${SHOTS}/admin_premierships_390.png`, fullPage: true })
  } else {
    await page.screenshot({ path: `${SHOTS}/admin_premierships_desktop.png`, fullPage: true })
  }
  await page.locator('select[aria-label="Change what this match was"]').selectOption('final')
  await page.waitForTimeout(300)
  ck(`premierships ${width}: changing a listed tag sends its game id`,
    JSON.stringify(seen.puts.at(-1)) === JSON.stringify({ match: 'cccccccc-0000-0000-0000-000000000009', kind: 'final', won: false }),
    JSON.stringify(seen.puts.at(-1)))
  ck(`premierships ${width}: no script errors`, seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}

// ── Partnership Records ─────────────────────────────────────────────────────
{
  const { ctx, page, seen } = await open('/admin/partnerships')
  await page.waitForSelector('text=Ann Able', { timeout: 20000 })
  ck('records: a linked record offers its match', await page.getByRole('link', { name: 'Open the match' }).getAttribute('href') === `/games/${GID}`)
  await page.getByRole('button', { name: 'Edit' }).first().click()
  await page.waitForSelector('text=Match link (optional)')
  await page.getByRole('button', { name: /^save changes$/i }).first().click().catch(() => {})
  await page.waitForTimeout(400)
  ck('records: an edit that leaves the link alone does not send it',
    seen.patches.length === 1 && !('match' in seen.patches[0]), JSON.stringify(seen.patches))
  await page.getByRole('button', { name: 'Edit' }).first().click().catch(() => {})
  const field = page.locator('input[placeholder^="https://play.cricket"]').first()
  if (await field.count()) {
    await field.fill(LINK)
    await page.getByRole('button', { name: /^save changes$/i }).first().click()
    await page.waitForTimeout(400)
  }
  ck('records: an edited link is sent', seen.patches.at(-1)?.match === LINK, JSON.stringify(seen.patches))
  ck('records: no script errors', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
