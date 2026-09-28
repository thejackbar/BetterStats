// Drives the real /games/:id scorecard in Chromium for a match imported from a
// club's own scorebook, with the API stubbed at the network layer.
//
//   npx vite preview --port 5199 &
//   node frontend/verification/verify_scorebook_import_browser.mjs [baseUrl]
//
// Reported off Shoalwater Bay's CSFW archive: an imported fixture showed no
// opposition team, no opposition score and no partnerships. The fixture here
// is the payload the SHIPPED scorecard route returned for such a match in
// backend/verification/verify_scorebook_innings.py (SCORECARD_FIXTURE), so the
// page is checked against real output rather than an invented one.
//
// The scorebook never recorded who batted first, so the page must not number
// the innings, draw a winning margin, or call either side home. An ordinary
// synced match beside it is the control: it has to read exactly as before.
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

const IMPORTED = JSON.parse(readFileSync(join(HERE, 'fixtures/scorecard_scorebook_import.json'), 'utf8'))

const SYNCED = {
  id: 'aaaaaaaa-0000-0000-0000-000000000002',
  home_team: 'Newry', away_team: 'Collegians 2nd XI',
  played_at: '2026-01-10', result: 'WIN', winning_team: 'Collegians 2nd XI',
  organisation_id: null,
  grade: { id: 'g1', name: '2nd Grade', raw_name: '2nd Grade' },
  season: { id: 's1', name: 'Summer 2025/26' },
  innings_totals: {
    1: { runs: 118, wickets: 10, extras: 9, batting_team: 'Newry' },
    2: { runs: 140, wickets: 6, extras: 7, batting_team: 'Collegians 2nd XI' },
  },
  batting: [{ innings_number: 2, player_id: 'p1', player_name: 'Smith, John', runs: 64,
    balls: 98, fours: 7, sixes: 0, dismissal_type: 'bowled', not_out: false,
    batting_position: 1, did_not_bat: false }],
  bowling: [{ innings_number: 1, player_id: 'p1', player_name: 'Smith, John', overs: 14,
    maidens: 3, runs: 38, wickets: 5, wides: 0, no_balls: 0, economy: 2.71 }],
  opp_batting: [{ innings_number: 1, player_id: null, player_name: 'R Kelly', runs: 41,
    balls: 60, dismissal_type: 'bowled', not_out: false, batting_position: 1, did_not_bat: false }],
  opp_bowling: [{ innings_number: 2, player_id: null, player_name: 'G Nolan', overs: 16,
    maidens: 2, runs: 52, wickets: 3 }],
  fielding: [], fall_of_wickets: [], partnerships: [],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(card, width = 1440) {
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
  await page.goto(`${BASE}/games/${card.id}`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('main .pb-card', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(400)
  return { page, ctx, errors }
}

// Each innings card's label, team and score, read off the rendered page.
const readCards = (page) => page.evaluate(() => {
  const out = []
  for (const el of document.querySelectorAll('.pb-card')) {
    const label = el.querySelector('div[class*="tracking-wide3"]')?.textContent || ''
    if (!/^INNINGS/.test(label.trim())) continue
    out.push({
      label: label.trim().split('·')[0].trim(),
      team: el.querySelector('div[class*="font-display"][class*="truncate"]')?.textContent?.trim() || '',
      score: el.querySelector('div[class*="pb-num"]')?.textContent?.trim() || '',
      bowlers: [...el.querySelectorAll('tbody tr')].map((r) => r.innerText.replace(/\s+/g, ' ')),
    })
  }
  return out
})
const headerText = (page) => page.evaluate(() => {
  const h = document.querySelector('main > .pb-card')
  return h ? h.innerText.replace(/\s+/g, ' ') : ''
})

{
  console.log('\nA match imported from the scorebook (the reported case)')
  const { page, ctx, errors } = await open(IMPORTED)
  const cards = await readCards(page)
  ck('both innings are drawn', cards.length === 2, JSON.stringify(cards.map((c) => c.team)))
  ck('the opposition has its own card, under its own name',
    cards.some((c) => c.team === 'Rockingham'), JSON.stringify(cards.map((c) => c.team)))
  ck("the opposition's score is the scorebook's 120/8",
    cards.some((c) => c.team === 'Rockingham' && /^120\/8$/.test(c.score)),
    JSON.stringify(cards.map((c) => c.score)))
  ck('our score is the scorebook total of 55',
    cards.some((c) => c.team === 'Shoalwater Bay' && /^55\/2$/.test(c.score)),
    JSON.stringify(cards.map((c) => c.score)))
  ck('our bowler bowls at the opposition, not at our own batters',
    cards.find((c) => c.team === 'Rockingham')?.bowlers.some((r) => /Bowler, Eve/.test(r))
    && !cards.find((c) => c.team === 'Shoalwater Bay')?.bowlers.some((r) => /Bowler, Eve.*10/.test(r)))
  ck('no innings is numbered, since nobody recorded who batted first',
    cards.length > 0 && cards.every((c) => c.label === 'INNINGS'), JSON.stringify(cards.map((c) => c.label)))
  ck('the page says why', await page.getByTestId('innings-order-note').isVisible().catch(() => false))
  const head = await headerText(page)
  ck('the header names both sides', /Shoalwater Bay/.test(head) && /Rockingham/.test(head), head)
  ck('without calling either one home', !/\bHOME\b/.test(head) && !/\bAWAY\b/.test(head), head)
  ck('and draws no margin it cannot know', !/won by/i.test(head), head)
  const body = await page.evaluate(() => document.body.innerText)
  ck('the partnerships are on the page', /partnership/i.test(body) && /\b25\b/.test(body))
  ck('so is the fall of wickets', /fall of wickets/i.test(body))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  console.log('\nThe same match on a phone')
  const { page, ctx } = await open(IMPORTED, 390)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', over <= 0, `${over}px`)
  await ctx.close()
}

{
  console.log('\nAn ordinary synced match reads exactly as before (control)')
  const { page, ctx, errors } = await open(SYNCED)
  const cards = await readCards(page)
  ck('its innings are still numbered', cards.map((c) => c.label).join(',') === 'INNINGS 1,INNINGS 2',
    JSON.stringify(cards.map((c) => c.label)))
  const head = await headerText(page)
  ck('its header still says home and away', /HOME/.test(head) && /AWAY/.test(head), head)
  ck('and still draws the margin', /won by 4 wickets/i.test(head), head)
  ck('with no note about batting order',
    !(await page.getByTestId('innings-order-note').isVisible().catch(() => false)))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
