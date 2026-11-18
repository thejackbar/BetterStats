// Drives the real match page and Manual entries screens in Chromium with the API stubbed at the
// network layer: a club marks a player as named for a synced match but not having played it.
//
//   npx vite build && npx vite preview --port 5199 &
//   node verification/verify_game_exclusions_browser.mjs [baseUrl]
//
// Reported off Piara Waters: Roy Marsh is on the East Fremantle team sheet (5th Grade, 7 March 2015)
// with nothing recorded, and the club could only type a -1 season adjustment. Checks:
//   * public: the scorecard names who did not play and why; no team list, and it is never requested;
//   * admin: the team list offers DIDN'T PLAY only for a player with nothing recorded;
//   * the dialog defaults to moving an existing -1 onto the game, and Mark sends exactly the
//     reason, note and adjustment picked (the request on the wire); the list and the public note reload;
//   * a refusal from the server is shown in the dialog;
//   * Adjustments: pick a player, filter by season, mark from there; Games to check: KEEP AS PLAYED
//     posts the game and player;
//   * 390px: nothing overflows sideways. Screenshots of both screens.
// Every read is guarded, so a control run against the previous build reports each check.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || '/tmp'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const GID = 'cccccccc-0000-0000-0000-000000000001'
const ROY = 'aaaaaaaa-0000-0000-0000-00000000000r'
const BEN = 'aaaaaaaa-0000-0000-0000-00000000000b'
const REASONS = [
  { key: 'twelfth_man', label: '12th man' }, { key: 'thirteenth_man', label: '13th man' },
  { key: 'late_withdrawal', label: 'Late withdrawal' }, { key: 'other', label: 'Did not play' },
]
const base = {
  game_id: GID, played_at: '2015-03-07', home_team: 'East Fremantle', away_team: 'Piara Waters',
  grade_name: '5th Grade', season_name: 'Summer 2014/15', season_year: 2014, reason: null, reason_label: null, note: null,
}
const royNamed = { ...base, player_id: ROY, player_name: 'Marsh, Roy', status: 'named', counts: true, can_mark: true }
const royMarked = { ...royNamed, status: 'marked', counts: false, can_mark: false, reason: 'thirteenth_man', reason_label: '13th man' }
const ben = { ...base, player_id: BEN, player_name: 'Batted, Ben', status: 'played', counts: true, can_mark: false }

const scorecard = {
  id: GID, home_team: 'East Fremantle', away_team: 'Piara Waters', home_away_known: true, innings_order_known: true,
  played_at: '2015-03-07', result: 'LOSS', winning_team: 'East Fremantle', organisation_id: null, is_manual: false,
  grade: { id: 'g1', name: '5th Grade', raw_name: '5th Grade' }, season: { id: 's1', name: 'Summer 2014/15' },
  innings_totals: { 1: { runs: 250, wickets: 8, extras: 9 } },
  batting: [], bowling: [], opp_batting: [], opp_bowling: [], fielding: [], fall_of_wickets: [], partnerships: [],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(url, { admin = true, width = 1280, postStatus = 200, waitFor } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(5000)
  const seen = { posts: [], deletes: [], dismiss: [], teamList: 0, notPlayed: 0, playerGames: [], errors: [] }
  let marked = false
  page.on('pageerror', e => seen.errors.push(String(e)))
  await page.route(/\/api\//, async route => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p.startsWith('/auth/me')) {
      return admin
        ? json({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'club_admin', club_id: 'org1',
                 club_slug: 'piara', entitlements: { modules: ['stats'], status: 'active' } })
        : route.fulfill({ status: 401, body: '{}' })
    }
    if (p === `/games/${GID}/scorecard`) return json(scorecard)
    if (p === `/games/${GID}/not-played` && req.method() === 'GET') {
      seen.notPlayed++
      return json({ players: marked ? [{ player_id: ROY, player_name: 'Marsh, Roy', reason: 'thirteenth_man', reason_label: '13th man' }] : [] })
    }
    if (p === `/games/${GID}/team-list`) { seen.teamList++; return json({ game_id: GID, reasons: REASONS, players: [marked ? royMarked : royNamed, ben] }) }
    if (p === `/games/${GID}/not-played/${ROY}/adjustments`) {
      return json({ adjustments: [{ id: 7, matches: -1, season_name: 'Summer 2014/15', grade_name: '5th Grade' }] })
    }
    if (p === `/games/${GID}/not-played` && req.method() === 'POST') {
      seen.posts.push(JSON.parse(req.postData() || '{}'))
      if (postStatus !== 200) return json({ detail: 'Marsh, Roy is already marked as not having played this game.' }, postStatus)
      marked = true
      return json({ player: royMarked, summary: 'Marsh, Roy marked as 13th man: East Fremantle v Piara Waters on 7 Mar 2015' })
    }
    if (p === `/games/${GID}/not-played/${ROY}` && req.method() === 'DELETE') {
      seen.deletes.push(p); marked = false
      return json({ player: royNamed, summary: 'Marsh, Roy counted as playing again: East Fremantle v Piara Waters on 7 Mar 2015' })
    }
    if (/\/club-admin\/game-exclusions\/players\/[^/]+\/games$/.test(p)) {
      seen.playerGames.push(p)
      return json({ player_id: ROY, reasons: REASONS, games: [
        marked ? royMarked : royNamed,
        { ...royNamed, game_id: 'g-2017', played_at: '2018-03-17', home_team: 'Cannington Tigers', grade_name: 'One Day D',
          season_name: 'Summer 2017/18', season_year: 2017 },
        { ...royNamed, game_id: 'g-played', played_at: '2015-02-28', home_team: 'Piara Waters', away_team: 'Willetton',
          grade_name: 'One Day C', status: 'played', can_mark: false },
      ] })
    }
    if (p === '/club-admin/game-exclusions/suggestions') {
      return json({ truncated: false, reasons: REASONS, items: seen.dismiss.length ? [] : [
        { ...royNamed, our_season_total: 19, ca_season_total: 18 }] })
    }
    if (p === '/club-admin/game-exclusions/suggestions/dismiss') {
      seen.dismiss.push(JSON.parse(req.postData() || '{}')); return json({ dismissed: true })
    }
    if (/manual-entries\/(season|career)-adjustments$/.test(p)) return json([])
    if (/admin\/seasons|manual-entries\/seasons/.test(p)) return json([{ id: 's1', name: 'Summer 2014/15', year: 2014 }])
    if (/known-values/.test(p)) return json({ oppositions: [], venues: [] })
    if (/admin\/players/.test(p)) return json([{ id: ROY, display_name: 'Marsh, Roy', is_player: true },
                                               { id: BEN, display_name: 'Batted, Ben', is_player: true }])
    return json([])
  })
  await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' })
  if (waitFor) await page.waitForSelector(waitFor, { timeout: 20000 }).catch(() => {})
  await page.waitForTimeout(600)
  return { ctx, page, seen, setMarked: v => { marked = v } }
}

const overflow = page => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
const text = async (page, sel) => (await page.locator(sel).first().textContent().catch(() => '')) || ''

// ── Public: the note, and no team list ───────────────────────────────────────
{
  const { ctx, page, seen, setMarked } = await open(`/games/${GID}`, { admin: false, waitFor: 'text=BACK' })
  ck('public: nothing is said while nobody is marked', await page.getByTestId('not-played-note').count() === 0)
  await ctx.close()
  const o = await open(`/games/${GID}`, { admin: false, waitFor: 'text=BACK' })
  o.setMarked(true)
  await o.page.reload({ waitUntil: 'domcontentloaded' })
  await o.page.waitForTimeout(800)
  const note = await text(o.page, '[data-testid="not-played-note"]')
  ck('public: the scorecard names who did not play and why', /Named but did not play:.*Marsh, Roy.*\(13th man\)/.test(note), note)
  ck('public: no team list panel', await o.page.getByTestId('team-list-panel').count() === 0)
  ck('public: the team list is never requested', o.seen.teamList === 0, String(o.seen.teamList))
  ck('public: no script errors', seen.errors.length === 0 && o.seen.errors.length === 0, [...seen.errors, ...o.seen.errors].join(' | '))
  await o.ctx.close()
  void setMarked
}

// ── Admin on the match page ──────────────────────────────────────────────────
{
  const { ctx, page, seen } = await open(`/games/${GID}`, { waitFor: '[data-testid="team-list-panel"]' })
  const rows = page.getByTestId('game-row')
  ck('admin: the team list shows both named players', await rows.count() === 2, String(await rows.count()))
  const royRow = rows.filter({ hasText: 'Marsh, Roy' })
  const benRow = rows.filter({ hasText: 'Batted, Ben' })
  ck("admin: Roy (nothing recorded) is offered DIDN'T PLAY", await royRow.getByTestId('mark-not-played').count() === 1)
  ck('admin: Ben (bowled) is shown as played with no option', await benRow.getByTestId('mark-not-played').count() === 0
     && /Played/i.test(await benRow.textContent().catch(() => '')))

  await royRow.getByTestId('mark-not-played').click().catch(() => {})
  await page.waitForSelector('[data-testid="not-played-dialog"]').catch(() => {})
  await page.waitForSelector('[data-testid="swap-adjustment"]').catch(() => {})
  ck('dialog: the existing -1 is offered and picked by default',
     await page.locator('[data-testid="swap-adjustment"] input[type=radio]').first().isChecked().catch(() => false))
  await page.getByLabel('13th man').check().catch(() => {})
  await page.getByPlaceholder('e.g. came on as a substitute fielder only').fill('carried drinks').catch(() => {})
  await page.screenshot({ path: `${SHOTS}/game_exclusions_dialog.png` }).catch(() => {})
  await page.getByTestId('confirm-not-played').click().catch(() => {})
  await page.waitForTimeout(800)
  ck('Mark sends exactly the reason, note and adjustment picked', JSON.stringify(seen.posts) === JSON.stringify(
    [{ player_id: ROY, reason: 'thirteenth_man', note: 'carried drinks', swap_adjustment_id: 7 }]), JSON.stringify(seen.posts))
  ck('the dialog closes and the list reloads showing the mark',
     await page.getByTestId('not-played-dialog').count() === 0
     && /13th man/.test(await rows.filter({ hasText: 'Marsh, Roy' }).textContent().catch(() => '')))
  ck('the server summary is shown', /marked as 13th man/.test(await page.getByTestId('team-list-panel').textContent().catch(() => '')))
  ck('the public note reloads with the mark', /13th man/.test(await text(page, '[data-testid="not-played-note"]')))
  await page.getByTestId('unmark-not-played').click().catch(() => {})
  await page.waitForTimeout(600)
  ck('COUNT AGAIN sends a DELETE for that player and game', seen.deletes.length === 1, JSON.stringify(seen.deletes))
  ck('admin: no script errors', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}
{
  const { ctx, page } = await open(`/games/${GID}`, { postStatus: 409, waitFor: '[data-testid="team-list-panel"]' })
  await page.getByTestId('mark-not-played').first().click().catch(() => {})
  await page.getByTestId('confirm-not-played').click().catch(() => {})
  await page.waitForTimeout(500)
  ck('a refusal from the server is shown in the dialog',
     /already marked/.test(await page.getByTestId('not-played-dialog').textContent().catch(() => '')))
  await ctx.close()
}
{
  const { ctx, page } = await open(`/games/${GID}`, { width: 390, waitFor: '[data-testid="team-list-panel"]' })
  ck('390px match page: no sideways overflow', await overflow(page) <= 0, String(await overflow(page)))
  await page.getByTestId('team-list-panel').screenshot({ path: `${SHOTS}/game_exclusions_match_390.png` }).catch(() => {})
  await page.getByTestId('mark-not-played').first().click().catch(() => {})
  await page.waitForSelector('[data-testid="not-played-dialog"]').catch(() => {})
  ck('390px dialog: no sideways overflow', await overflow(page) <= 0, String(await overflow(page)))
  await ctx.close()
}

// ── Adjustments: pick the player and the game ────────────────────────────────
{
  const { ctx, page, seen } = await open('/admin/manual-entries#season', { waitFor: '[data-testid="player-game-picker"]' })
  ck('Adjustments shows the game picker', await page.getByTestId('player-game-picker').count() === 1)
  await page.getByTestId('picker-player').selectOption(ROY).catch(() => {})
  await page.waitForTimeout(600)
  ck("picking a player loads that player's games", seen.playerGames.some(p => p.includes(ROY)), JSON.stringify(seen.playerGames))
  const rows = page.getByTestId('player-game-picker').getByTestId('game-row')
  ck('every named game is listed', await rows.count() === 3, String(await rows.count()))
  await page.getByTestId('picker-season').selectOption('Summer 2017/18').catch(() => {})
  ck('the season filter narrows the list', await rows.count() === 1 && /Cannington/.test(await rows.first().textContent().catch(() => '')))
  await page.getByTestId('picker-season').selectOption('').catch(() => {})
  await rows.filter({ hasText: 'East Fremantle' }).getByTestId('mark-not-played').click().catch(() => {})
  await page.getByTestId('confirm-not-played').click().catch(() => {})
  await page.waitForTimeout(700)
  ck('marking from Adjustments sends the game and player', seen.posts.length === 1 && seen.posts[0].player_id === ROY
     && seen.posts[0].reason === 'twelfth_man', JSON.stringify(seen.posts))
  await page.setViewportSize({ width: 390, height: 1400 })
  await page.waitForTimeout(300)
  ck('390px Adjustments: no sideways overflow', await overflow(page) <= 0, String(await overflow(page)))
  await page.getByTestId('player-game-picker').screenshot({ path: `${SHOTS}/game_exclusions_picker_390.png` }).catch(() => {})
  ck('Adjustments: no script errors', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}

// ── Games to check ───────────────────────────────────────────────────────────
{
  const { ctx, page, seen } = await open('/admin/manual-entries#check', { waitFor: '[data-testid="games-to-check"]' })
  const box = page.getByTestId('games-to-check')
  ck('Games to check lists Roy at East Fremantle with both totals',
     /Marsh, Roy/.test(await box.textContent().catch(() => '')) && /we count 19, Cricket Australia counts 18/.test(await box.textContent().catch(() => '')))
  await page.screenshot({ path: `${SHOTS}/game_exclusions_check.png`, fullPage: true }).catch(() => {})
  await box.getByTestId('keep-as-played').click().catch(() => {})
  await page.waitForTimeout(600)
  ck('KEEP AS PLAYED posts that game and player', JSON.stringify(seen.dismiss) === JSON.stringify([{ game_id: GID, player_id: ROY }]),
     JSON.stringify(seen.dismiss))
  ck('and the list then says there is nothing to check', await page.getByTestId('games-to-check-empty').count() === 1)
  await page.setViewportSize({ width: 390, height: 1400 })
  await page.waitForTimeout(300)
  ck('390px Games to check: no sideways overflow', await overflow(page) <= 0, String(await overflow(page)))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
