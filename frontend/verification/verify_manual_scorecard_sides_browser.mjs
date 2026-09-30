// Drives the real /games/:id scorecard in Chromium over Hamilton Veterans'
// own hand-entered and CSV-imported games, pulled off the live API.
//
//   VITE_PROXY_TARGET=https://betterat.cricket/api npx vite --port 5199 &
//   node frontend/verification/verify_manual_scorecard_sides_browser.mjs [baseUrl]
//
// Reported: whenever the opposition batted first, the header drew each side's
// score under the other side's name. The club plays as "Portland Over 60s",
// the match records that name, and the innings were labelled with the club's
// own name (Hamilton Veterans Cricket Club) — a name the header could not
// place, so it fell back to "innings 1 is the home side". "Over 60s" made it
// worse: "60s" read as a word the two sides shared.
//
// Each game is run twice: as the live payload has it today (the club's name
// on our innings, which the frontend fix alone must handle) and as the
// backend fix returns it (the match's own team name). The last section drives
// the Games page's season picker against the live API.
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const CLUB = 'Hamilton Veterans Cricket Club'
const TEAM = 'Portland Over 60s'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const GAMES = {
  '588030cf-43f2-4d4d-81eb-e5ce955b7390': '20 Feb 2011, Mt Gambier batted first',
  '92989d14-825b-4cfd-a597-597608e171a5': '20 Mar 2011, Portland batted first',
  '336e4161-5215-46cf-a9d6-5d72faec8b3b': '23 Oct 2011, Mt Gambier batted first',
  'cc4ce224-5490-4997-a176-7b9d99525e19': '5 Feb 2012 (CSV), SAVCA batted first',
  'f84afa5e-67c4-4fea-9dd1-a9aa6e847299': '6 Feb 2012 (CSV), Portland batted first',
  '061dd7ae-20dd-448b-ab01-12811e8b4b5b': '7 Feb 2012 (CSV), Portland batted first',
}
const load = id => JSON.parse(readFileSync(join(HERE, 'fixtures', 'hamilton_sides', `${id}.json`), 'utf8'))

// What the backend now sends: our innings named for the side the match calls ours.
const renamed = g => {
  const out = structuredClone(g)
  for (const t of Object.values(out.innings_totals)) {
    if (t.batting_team === CLUB) t.batting_team = TEAM
  }
  return out
}

// All out reads as the runs alone, the page's own fmtScore rule.
const scoreOf = t => (t.wickets >= 10 ? `${t.runs + (t.extras || 0)}` : `${t.runs + (t.extras || 0)}/${t.wickets}`)

const browser = await chromium.launch({ executablePath: EXECUTABLE })
const page = await browser.newPage({ viewport: { width: 1400, height: 1100 } })
const errors = []
page.on('pageerror', e => errors.push(String(e)))

let current = null
await page.route(/\/api\/games\/[^/]+\/scorecard/, r => r.fulfill({ json: current }))
await page.route(/\/api\/organisations\/[^/?]+(\?.*)?$/, r => r.fulfill({ json: { id: 'x', name: CLUB } }))

const readPage = () => page.evaluate(() => {
  const card = document.querySelector('.pb-card')
  const grid = card?.querySelector('.grid')
  const [home, , away] = grid ? [...grid.children] : []
  const side = el => el ? {
    // The crest's initials are .font-display too and come first; the name is the last.
    name: [...el.querySelectorAll('.font-display.tracking-tight')].pop()?.innerText.trim(),
    score: [...el.querySelectorAll('.font-mono')].map(n => n.innerText.trim()).find(s => /^\d+(\/\d+)?$/.test(s)) || null,
    won: /WON/.test(el.innerText),
  } : null
  return { home: side(home), away: side(away), body: document.body.innerText }
})

for (const [id, label] of Object.entries(GAMES)) {
  const raw = load(id)
  const ourT = Object.values(raw.innings_totals).find(t => t.batting_team === CLUB)
  const theirT = Object.values(raw.innings_totals).find(t => t.batting_team !== CLUB)
  for (const [variant, payload] of [['club name on our innings', raw], ['team name on our innings', renamed(raw)]]) {
    current = payload
    await page.goto(`${BASE}/games/${id}`)
    await page.waitForSelector('text=INNINGS', { timeout: 20000 }).catch(() => {})
    await page.waitForTimeout(400)
    const r = await readPage()
    const tag = `${label} [${variant}]:`
    ck(`${tag} header home is Portland`, r.home?.name === TEAM, JSON.stringify(r.home))
    ck(`${tag} Portland's own score under Portland`, r.home?.score === scoreOf(ourT),
       `got ${r.home?.score} want ${scoreOf(ourT)}`)
    ck(`${tag} the opposition's score under the opposition`, r.away?.score === scoreOf(theirT),
       `got ${r.away?.score} want ${scoreOf(theirT)}`)
    if (variant.startsWith('team')) {
      ck(`${tag} the club's name appears nowhere on the card`, !r.body.includes(CLUB))
      ck(`${tag} our bowlers are headed Portland's bowling`,
         r.body.toUpperCase().includes(`${TEAM.toUpperCase()} BOWLING`))
    }
  }
}

// The winner badge follows the recorded winning team, on the side that is it.
{
  current = renamed(load('588030cf-43f2-4d4d-81eb-e5ce955b7390'))
  await page.goto(`${BASE}/games/588030cf-43f2-4d4d-81eb-e5ce955b7390`)
  await page.waitForSelector('text=INNINGS', { timeout: 20000 }).catch(() => {})
  const r = await readPage()
  ck('20 Feb: WON sits on Mt Gambier, not Portland', r.away?.won && !r.home?.won, JSON.stringify([r.home, r.away]))
}

// Two sides whose names share only an age band are two sides: every innings
// of a Portland v Mt Gambier match must not land on one of them.
{
  const g = renamed(load('92989d14-825b-4cfd-a597-597608e171a5'))
  current = g
  await page.goto(`${BASE}/games/92989d14-825b-4cfd-a597-597608e171a5`)
  await page.waitForSelector('text=INNINGS', { timeout: 20000 }).catch(() => {})
  const r = await readPage()
  ck('20 Mar: both sides carry a score in the header', !!r.home?.score && !!r.away?.score,
     JSON.stringify([r.home, r.away]))
}

ck('no page errors on the scorecard', errors.length === 0, errors.join(' | '))

// ── Games page: "All seasons" stays chosen ───────────────────────────────────
await page.unrouteAll({ behavior: 'ignoreErrors' })
const results = []
page.on('response', async res => {
  if (/\/organisations\/[^/]+\/results/.test(res.url())) results.push(res.url())
})
await page.goto(`${BASE}/hamilton-veterans-cricket-club/games`)
const seasonSel = page.locator('select').filter({ has: page.locator('option', { hasText: 'All seasons' }) }).first()
await seasonSel.waitFor({ timeout: 30000 }).catch(() => {})
await page.waitForTimeout(1500)
const before = await seasonSel.inputValue().catch(() => null)
ck('the page opens on a season', !!before, `value=${before}`)
results.length = 0
await seasonSel.selectOption('').catch(() => {})
await page.waitForTimeout(2500)
const after = await seasonSel.inputValue().catch(() => null)
ck('"All seasons" is still selected after choosing it', after === '', `value=${after}`)
ck('the results request carried no season', results.some(u => !/season_id=/.test(u)), results.join(' | '))
const text = await page.locator('body').innerText()
ck('the page says ALL SEASONS', /ALL SEASONS/i.test(text))
ck('games from 2011 and 2012 are both listed', /2011/.test(text) && /2012/.test(text))

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
