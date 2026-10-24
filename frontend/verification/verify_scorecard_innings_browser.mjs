// Drives the real /games/:id scorecard in Chromium with the API stubbed at
// the network layer.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_scorecard_innings_browser.mjs [baseUrl]
//
// Reported off a live club: a two-day grand final showed only the first two
// innings, so half the match was missing from the page. The backend had been
// returning all four the whole time — the page took innings[0] and innings[1]
// and dropped the rest. The four-innings fixture here is the REPORTED MATCH's
// own payload, pulled straight off the live API, so the checks are about that
// game rather than an invented one.
//
// The one-day fixture beside it is the control that matters in the other
// direction: an ordinary two-innings game has to read exactly as it did.
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

// The reported match: Collegians 30 & 124, Stratford Redbacks 99 & 54/3.
const TWO_INNINGS = JSON.parse(readFileSync(join(HERE, 'fixtures/scorecard_two_innings.json'), 'utf8'))

// An ordinary one-day game, built so nothing about the two-innings work can
// quietly change how the common case reads.
const ONE_DAY = {
  id: 'aaaaaaaa-0000-0000-0000-000000000001',
  home_team: 'Newry', away_team: 'Collegians 2nd XI',
  played_at: '2026-01-10', result: 'WIN', winning_team: 'Collegians 2nd XI',
  organisation_id: null,
  grade: { id: 'g1', name: '2nd Grade', raw_name: '2nd Grade' },
  season: { id: 's1', name: 'Summer 2025/26' },
  innings_totals: {
    1: { runs: 118, wickets: 10, extras: 9, batting_team: 'Newry' },
    2: { runs: 140, wickets: 6, extras: 7, batting_team: 'Collegians 2nd XI' },
  },
  batting: [
    { innings_number: 2, player_id: 'p1', player_name: 'Smith, John', runs: 64, balls: 98,
      fours: 7, sixes: 0, dismissal_type: 'c: R Kelly b: G Nolan', not_out: false,
      batting_position: 1, did_not_bat: false },
  ],
  bowling: [
    { innings_number: 1, player_id: 'p1', player_name: 'Smith, John', overs: 14, maidens: 3,
      runs: 38, wickets: 5, wides: 0, no_balls: 0, economy: 2.71 },
  ],
  opp_batting: [
    { innings_number: 1, player_id: null, player_name: 'R Kelly', runs: 41, balls: 60,
      dismissal_type: 'b: J Smith', not_out: false, batting_position: 1, did_not_bat: false },
  ],
  opp_bowling: [
    { innings_number: 2, player_id: null, player_name: 'G Nolan', overs: 16, maidens: 2,
      runs: 52, wickets: 3 },
  ],
  fielding: [], fall_of_wickets: [], partnerships: [],
}

// A match where only ONE side batted. Reported off Payneham (2 Feb 2014): "Payneham 3 v Eastern Suburbs 2",
// a drawn two-day game in which only Eastern Suburbs 2 batted (320), came up with that 320 and Eastern
// Suburbs' crest under Payneham 3. The header's home/away check ran only when both sides had an innings.
const ONE_SIDE_BATTED = {
  id: 'aaaaaaaa-0000-0000-0000-000000000002',
  home_team: 'Payneham 3', away_team: 'Eastern Suburbs 2',
  played_at: '2014-02-09', result: 'DRAW', winning_team: null,
  organisation_id: null,
  grade: { id: 'g2', name: 'Under 15 North Division 2', raw_name: 'Under 15 North Division 2' },
  season: { id: 's2', name: 'Summer 2013/14' },
  innings_totals: { 1: { runs: 320, wickets: 10, extras: 0, batting_team: 'Eastern Suburbs 2', overs: '64.3' } },
  batting: [],
  bowling: [{ innings_number: 1, player_id: 'p9', player_name: 'Harry Edmonds', overs: 8.3, maidens: 0, runs: 32, wickets: 3, wides: 0, no_balls: 0 }],
  opp_batting: [
    { innings_number: 1, player_id: null, player_name: 'A McFarlane', runs: 160, balls: 0, dismissal_type: 'b:', not_out: false, batting_position: 1, did_not_bat: false },
    { innings_number: 1, player_id: null, player_name: 'S Elliott', runs: 160, balls: 0, dismissal_type: 'c: b:', not_out: false, batting_position: 2, did_not_bat: false },
  ],
  opp_bowling: [],
  fielding: [], fall_of_wickets: [], partnerships: [],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openCard(card, { width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1200 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))

  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    if (/\/scorecard$/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(card) })
    }
    if (/^\/auth\/me/.test(path)) return route.fulfill({ status: 401, body: '{}' })
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto(`${BASE}/games/${card.id}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('text=INNINGS 1', { timeout: 10000 }).catch(() => {})
  return { page, ctx, errors }
}

// Every innings card's label + the team name and score printed on it, read
// off the rendered page rather than inferred from the fixture.
async function readCards(page) {
  return page.evaluate(() => {
    const out = []
    for (const el of document.querySelectorAll('.pb-card')) {
      const label = el.querySelector('div[class*="tracking-wide3"]')?.textContent || ''
      if (!/^INNINGS \d/.test(label.trim())) continue
      // `.truncate` is what separates the team NAME from the crest beside it —
      // TeamBadge's initials fall back to font-display too, so a bare
      // font-display lookup reads "CS" where the card says "Collegians…".
      out.push({
        label: label.trim().split('·')[0].trim(),
        team: el.querySelector('div[class*="font-display"][class*="truncate"]')?.textContent?.trim() || '',
        score: el.querySelector('div[class*="pb-num"]')?.textContent?.trim() || '',
        won: /WON/.test(el.textContent || ''),
        rows: el.querySelectorAll('tbody tr').length,
      })
    }
    return out
  })
}

const headerText = (page) => page.evaluate(() => {
  const h = document.querySelector('main > .pb-card')
  return h ? h.innerText.replace(/\s+/g, ' ') : ''
})

// ---------------------------------------------------------------- two innings

{
  console.log('\nA two-day match shows every innings (the reported game)')
  const { page, ctx, errors } = await openCard(TWO_INNINGS)
  const cards = await readCards(page)

  ck('all four innings are drawn', cards.length === 4, `got ${cards.length}`)
  ck('they are labelled in batting order',
    cards.map(c => c.label).join('|') === 'INNINGS 1|INNINGS 2|INNINGS 3|INNINGS 4',
    cards.map(c => c.label).join('|'))

  const byLabel = Object.fromEntries(cards.map(c => [c.label, c]))
  ck('innings 3 is the second innings that was missing',
    /Collegians/.test(byLabel['INNINGS 3']?.team || ''), byLabel['INNINGS 3']?.team)
  ck('innings 4 is the winning chase',
    /Stratford/.test(byLabel['INNINGS 4']?.team || ''), byLabel['INNINGS 4']?.team)
  ck('innings 3 carries its own score (124 + 4 extras, all out)',
    byLabel['INNINGS 3']?.score === '128', byLabel['INNINGS 3']?.score)
  ck('innings 4 carries its own score (54 + 4 extras for 3)',
    byLabel['INNINGS 4']?.score === '58/3', byLabel['INNINGS 4']?.score)
  ck('each side bats twice, so a team names two cards',
    cards.filter(c => /Collegians/.test(c.team)).length === 2
    && cards.filter(c => /Stratford/.test(c.team)).length === 2,
    cards.map(c => c.team).join(' | '))
  ck('every innings card has batting rows under it',
    cards.every(c => c.rows > 0), cards.map(c => `${c.label}:${c.rows}`).join(' '))

  console.log('\nThe winner is marked once, on the right side')
  ck('both of the winning side\'s cards are marked won',
    cards.filter(c => c.won).length === 2, `${cards.filter(c => c.won).length} marked`)
  ck('the losing side is never marked won',
    cards.filter(c => c.won).every(c => /Stratford/.test(c.team)),
    cards.filter(c => c.won).map(c => c.team).join(', '))

  console.log('\nThe header reads as a two-innings scorecard')
  const head = await headerText(page)
  ck('the winning side shows both its scores', /102 & 58\/3/.test(head), head.slice(0, 220))
  ck('the losing side shows both its scores', /31 & 128/.test(head), head.slice(0, 220))
  ck('the margin is worked out across both innings, not the first two',
    /won by 7 wickets/.test(head), head.slice(0, 220))

  console.log('\nThe sections below still cover every innings')
  const sections = await page.evaluate(() => {
    const grab = (heading) => {
      const el = [...document.querySelectorAll('p')].find(p => p.textContent.trim() === heading)
      return el ? el.closest('.pb-card').innerText : ''
    }
    return { fow: grab('FALL OF WICKETS'), pt: grab('PARTNERSHIPS') }
  })
  ck('fall of wickets covers all four innings',
    [1, 2, 3, 4].every(n => new RegExp(`Innings ${n}\\b`, 'i').test(sections.fow)),
    sections.fow.slice(0, 120))
  ck('partnerships cover both of our innings',
    /Innings 1/i.test(sections.pt) && /Innings 3/i.test(sections.pt), sections.pt.slice(0, 120))

  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------------------------------------ only one side batted

{
  console.log('\nA match where only one side batted files that innings under the side that batted')
  const { page, ctx, errors } = await openCard(ONE_SIDE_BATTED)
  const sides = await page.evaluate(() => {
    const grid = document.querySelector('main > .pb-card .grid')
    const kids = grid ? [...grid.children] : []
    return { home: kids[0]?.innerText.replace(/\s+/g, ' ') || '', away: kids[2]?.innerText.replace(/\s+/g, ' ') || '' }
  })
  ck('the 320 is under Eastern Suburbs 2, the side that batted', /Eastern Suburbs 2/.test(sides.away) && /320/.test(sides.away), sides.away)
  ck('and not under Payneham 3', /Payneham 3/.test(sides.home) && !/320/.test(sides.home), sides.home)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------------------------------------------- one day

{
  console.log('\nAn ordinary one-day game is unchanged')
  const { page, ctx, errors } = await openCard(ONE_DAY)
  const cards = await readCards(page)

  ck('exactly two innings are drawn', cards.length === 2, `got ${cards.length}`)
  ck('the side batting first is on the first card',
    cards[0]?.team === 'Newry', cards[0]?.team)
  ck('its score reads runs plus extras, all out',
    cards[0]?.score === '127', cards[0]?.score)
  ck('the chasing side reads runs for wickets',
    cards[1]?.score === '147/6', cards[1]?.score)
  ck('only the winner is marked',
    cards.filter(c => c.won).length === 1 && cards[1]?.won,
    cards.map(c => `${c.team}:${c.won}`).join(' '))

  const head = await headerText(page)
  ck('a single-innings side shows one score, not a run-on',
    /147\/6/.test(head) && !/&/.test(head), head.slice(0, 200))
  ck('the chase margin is still worked out', /won by 4 wickets/.test(head), head.slice(0, 200))
  ck('overs and run rate still show for a one-innings side',
    /overs/.test(head) && /RR /.test(head), head.slice(0, 200))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// -------------------------------------------------------------------- mobile

{
  console.log('\nOn a phone')
  const { page, ctx, errors } = await openCard(TWO_INNINGS, { width: 390 })
  const cards = await readCards(page)
  ck('all four innings are still drawn at 390px', cards.length === 4, `got ${cards.length}`)
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', overflow <= 0, `${overflow}px`)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
