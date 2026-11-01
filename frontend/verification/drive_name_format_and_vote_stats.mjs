// The player's own page and the vote pages print names the way the club chose in Settings,
// the vote page thanks a player by first name, and the ballot (and the player's cast votes)
// show a small line of that player's stats from the game under each name.
//
// Drives the REAL screens in Chromium (390px phone) with the API stubbed at the network layer.
//
//   npx vite build --outDir /tmp/dist && npx vite preview --outDir /tmp/dist --port 5199 &
//   APP_URL=http://localhost:5199 node verification/drive_name_format_and_vote_stats.mjs
import { launch, json, overflow, PHONE } from './mobile_harness.mjs'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOT = process.env.SHOT_DIR || '/tmp'
let failed = 0
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : `  ${extra}`}`); if (!ok) failed++ }

const JACK = { id: 'jack', display_name: 'Barendse, Jack' }
const TEAM = [
  { id: 'jack', name: 'Barendse, Jack', stats: '45* (32) · 2/18 (4 ov) · 2 ct' },
  { id: 'sam', name: 'Smith, Sam', stats: 'Did not bat or bowl' },
  { id: 'kim', name: 'Jones, Kim', stats: '12 (10), 30 (28) · 0/25 (3.4 ov) · 1 st, 1 ro' },
  { id: 'hal', name: 'Hidden, Hal', stats: null },
]
const brand = (fmt) => ({ name: 'Applecross Cricket Club', primary_color: '#c8102e', ...(fmt ? { player_name_format: fmt } : {}) })

async function votePage(format, who) {
  const { browser, page, errors } = await launch()
  await page.route(/\/api\/public\/votes\/TOK/, async (r) => {
    const path = new URL(r.request().url()).pathname.replace(/^.*\/public\/votes\/TOK/, '')
    const me = { ...who }
    if (path.endsWith('/ballot')) return json(r, { status: 'ok' })
    if (path.startsWith('/fixtures/')) {
      return json(r, {
        club: brand(format), fixture: { id: 'fx1', opponent: 'Swanbourne', round: 'Round 5', date: '2026-11-01', state: 'open' },
        ballot_values: [3, 2, 1], allow_self_vote: false, voter_mode: 'players', me, role: 'player', reason: null,
        is_chosen: false, players: TEAM.map((p) => ({ id: p.id, name: p.name, photo_url: null, stats: p.stats })), my_ballot: null,
      })
    }
    return json(r, {
      club: brand(format), medal: { id: 'm', name: 'Club Champion' }, require_pin: true, voter_mode: 'players',
      allow_non_participants: false, allow_self_vote: false, ballot_values: [3, 2, 1], me,
      players: [], grades: [], rounds: [], team: null, round_key: null, q: null,
      fixtures: [{ id: 'fx1', opponent: 'Swanbourne', round: 'Round 5', round_key: 'round 5', date: '2026-11-01', state: 'open', voted: false }],
    })
  })
  await page.goto(`${BASE}/vote/TOK?fixture=fx1`)
  await page.waitForSelector('[data-player-stats]', { timeout: 10000 })
  return { browser, page, errors }
}

// ── 1. Club prints "First Last": ballot, signed-in strip and the thanks ───────────────
{
  const { browser, page, errors } = await votePage('first_last', JACK)
  const body = await page.locator('body').innerText()
  check('strip names the voter in the club format', (await page.locator('[data-signed-in-name]').first().textContent()) === 'Jack Barendse')
  check('ballot lists teammates First Last', body.includes('Sam Smith') && body.includes('Kim Jones') && !body.includes('Smith, Sam'))
  const stats = await page.locator('[data-player-stats]').allTextContents()
  check('lines show for the voter\'s teammates who have one (self-vote is off, hidden player has none)', stats.length === 2, JSON.stringify(stats))
  check('batting, bowling and fielding read in one small line', stats.includes('12 (10), 30 (28) · 0/25 (3.4 ov) · 1 st, 1 ro'), JSON.stringify(stats))
  check('a player who did not bat or bowl says so', stats.includes('Did not bat or bowl'))
  const row = page.locator('button', { hasText: 'Kim Jones' }).first()
  const size = await row.locator('[data-player-stats]').evaluate((e) => parseFloat(getComputedStyle(e).fontSize))
  check('the line is small (under the 15.5px name)', size < 13, String(size))
  check('no sideways overflow at 390px', (await overflow(page, PHONE.width)).over <= 0)
  await page.screenshot({ path: `${SHOT}/ballot-stats-first-last.png` })
  for (const n of ['Sam Smith', 'Kim Jones', 'Hal Hidden']) await page.getByText(n, { exact: false }).first().click()
  await page.getByRole('button', { name: /submit my votes/i }).click()
  await page.waitForSelector('text=Votes in!', { timeout: 8000 })
  const done = await page.locator('body').innerText()
  check('thanked by first name, not surname', /Thanks, Jack\./.test(done) && !/Thanks, Barendse/.test(done), done.slice(0, 120))
  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
}

// ── 2. Control: a club on the default "Last, First" is still thanked by first name ─────
{
  const { browser, page } = await votePage(null, JACK)
  const done0 = await page.locator('body').innerText()
  check('default format: names stay Last, First', done0.includes('Smith, Sam') && (await page.locator('[data-signed-in-name]').first().textContent()) === 'Barendse, Jack')
  for (const n of ['Smith, Sam', 'Jones, Kim', 'Hidden, Hal']) await page.getByText(n, { exact: false }).first().click()
  await page.getByRole('button', { name: /submit my votes/i }).click()
  await page.waitForSelector('text=Votes in!', { timeout: 8000 })
  check('default format: still thanked by first name', /Thanks, Jack\./.test(await page.locator('body').innerText()))
  await browser.close()
}

// ── 3. The player's own page ──────────────────────────────────────────────────────────
for (const [fmt, shown, initials, pick] of [['first_last', 'Jack Barendse', 'JB', 'Kim Jones'], [null, 'Barendse, Jack', 'BJ', 'Jones, Kim']]) {
  const { browser, page, errors } = await launch()
  const club = { ...brand(fmt), short_name: 'Applecross Cricket Club' }
  const player = { id: 'jack', display_name: 'Barendse, Jack', photo_url: null, shirt_number: null, profile_path: '/players/jack' }
  await page.route(/\/api\/public\/availability\/AV/, async (r) => {
    const path = new URL(r.request().url()).pathname.replace(/^.*\/public\/availability\/AV/, '')
    if (path === '/me/profile') {
      return json(r, {
        player, squads: [], selected: [], modules: ['votes'], can_update_details: true,
        votes: [], votes_cast: [{
          medal: 'Club Champion', fixture_id: 'fx1', opponent: 'Swanbourne', round: 'Round 5', date: '2026-11-01',
          open: false, closes_on: null, link: null,
          picks: [{ points: 3, name: 'Barendse, Jack', stats: '45* (32) · 2/18 (4 ov) · 2 ct' }, { points: 2, name: 'Jones, Kim', stats: '12 (10), 30 (28) · 0/25 (3.4 ov) · 1 st, 1 ro' }, { points: 1, name: 'Hidden, Hal', stats: null }],
        }],
      })
    }
    if (path.startsWith('/me')) return json(r, { club, player, dates: [], squads: [], has_availability: false, has_squad: false })
    return json(r, { club, require_pin: false, has_availability: false, allow_maybe: false, week_names: [], players: [{ id: 'jack', display_name: 'Barendse, Jack', has_phone: true }] })
  })
  await page.goto(`${BASE}/playerdash/AV`)
  await page.waitForSelector('[data-hero-name]', { timeout: 10000 })
  const label = fmt || 'default'
  check(`${label}: hero name`, (await page.locator('[data-hero-name]').textContent()) === shown, await page.locator('[data-hero-name]').textContent())
  check(`${label}: "Signed in as" line`, (await page.locator('[data-hero]').innerText()).includes(`Signed in as ${shown}. Not you?`))
  check(`${label}: initials follow the shown name`, (await page.locator('[data-hero-initials]').count()) === 0 || (await page.locator('[data-hero-initials]').textContent()) === initials)
  await page.locator('[data-group-toggle="voting"]').click()
  await page.waitForSelector('[data-pick]', { state: 'visible', timeout: 10000 })
  const picks = await page.locator('[data-pick]').allInnerTexts()
  check(`${label}: cast picks use the club format`, picks.some((t) => t.includes(pick)), JSON.stringify(picks))
  const pstats = await page.locator('[data-pick-stats]').allTextContents()
  check(`${label}: stats sit under each name that has them (2 of 3)`, pstats.length === 2 && pstats[0].startsWith('45*'), JSON.stringify(pstats))
  check(`${label}: no sideways overflow at 390px`, (await overflow(page, PHONE.width)).over <= 0)
  await page.screenshot({ path: `${SHOT}/dashboard-votes-${label}.png` })
  check(`${label}: no page errors`, errors.length === 0, errors.join(' | '))
  await browser.close()
}

console.log(failed ? `\n${failed} FAILED` : '\nall passed')
process.exit(failed ? 1 : 0)
