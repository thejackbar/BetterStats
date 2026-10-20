// Drives the real /games/:id scorecard in Chromium and checks the FIELDING block.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_scorecard_fielding_browser.mjs [baseUrl]
//
// Reported by Shoalwater Bay: a 1992-93 B Grade scorecard showed nothing about
// catches. The scorebook archive records catches as a per-player tally for the
// match, never which batter each one dismissed, so the dismissal text reads a
// bare "c". The tally was imported, and the API has always returned it as
// `fielding`, but the page never read it.
//
// The payload is a real scorecard (Hamilton Veterans, off the live API) with a
// fielding list added, shaped the way get_scorecard now sends it.
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const ID = '588030cf-43f2-4d4d-81eb-e5ce955b7390'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const base = JSON.parse(readFileSync(join(HERE, 'fixtures', 'hamilton_sides', `${ID}.json`), 'utf8'))
const withFielding = fielding => ({ ...structuredClone(base), fielding })

const browser = await chromium.launch({ executablePath: EXECUTABLE })
const page = await browser.newPage({ viewport: { width: 1400, height: 1100 } })
const errors = []
page.on('pageerror', e => errors.push(String(e)))

let current = null
await page.route(/\/api\/games\/[^/]+\/scorecard/, r => r.fulfill({ json: current }))
await page.route(/\/api\/organisations\/[^/?]+(\?.*)?$/, r => r.fulfill({ json: { id: 'x', name: 'Test CC' } }))

const open = async payload => {
  current = payload
  await page.goto(`${BASE}/games/${ID}`)
  await page.waitForSelector('.pb-card')
  await page.waitForTimeout(300)
}
// Reads the block through its own testid, and reports absence rather than throwing.
const block = () => page.evaluate(() => {
  const el = document.querySelector('[data-testid="fielding-section"]')
  if (!el) return null
  const heads = [...el.querySelectorAll('thead th')].map(t => t.innerText.trim())
  const rows = [...el.querySelectorAll('tbody tr')].map(tr =>
    [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))
  const links = [...el.querySelectorAll('tbody a')].map(a => a.getAttribute('href'))
  const box = el.getBoundingClientRect()
  return { heads, rows, links, title: el.innerText.split('\n')[0], w: box.width, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }
})

console.log('-- a match with catches recorded --')
await open(withFielding([
  { player_id: 'p1', player_name: 'Spinks, Ray', catches: 2, catches_wk: 0, run_outs: 0, stumpings: 0 },
  { player_id: 'p2', player_name: 'Gloves, Gary', catches: 0, catches_wk: 3, run_outs: 0, stumpings: 1 },
  { player_id: 'p3', player_name: 'Baker, Ken', catches: 1, catches_wk: 0, run_outs: 0, stumpings: 0 },
  { player_id: 'p4', player_name: 'Nothing, Nick', catches: 0, catches_wk: 0, run_outs: 0, stumpings: 0 },
]))
let b = await block()
ck('a FIELDING block is drawn', !!b)
if (b) {
  ck('it is titled FIELDING', /FIELDING/.test(b.title), b.title)
  ck('it has a column for catches', b.heads.includes('CATCHES'), b.heads.join('|'))
  ck('and one for keeper catches, because somebody has one', b.heads.includes('CT (WK)'))
  ck('and one for stumpings, because somebody has one', b.heads.includes('STUMPINGS'))
  ck('but none for run outs, which nobody has', !b.heads.includes('RUN OUTS'))
  ck('a player with nothing recorded is not listed', !b.rows.some(r => /Nothing/.test(r[0])), JSON.stringify(b.rows))
  ck('three fielders are listed', b.rows.length === 3, JSON.stringify(b.rows))
  const spinks = b.rows.find(r => /Spinks/.test(r[0]))
  ck('Spinks has 2 catches', spinks && spinks[b.heads.indexOf('CATCHES') ] === '2', JSON.stringify(spinks))
  // The keeper's catches are in catches_wk alone, the way the scorebook import
  // stores them, so the total taken is the larger of the two.
  const keeper = b.rows.find(r => /Gloves/.test(r[0]))
  ck("a keeper whose catches are stored as keeper catches still shows the 3 he took",
    keeper && keeper[b.heads.indexOf('CATCHES')] === '3', JSON.stringify(keeper))
  ck('with the keeper split beside it', keeper && keeper[b.heads.indexOf('CT (WK)')] === '3')
  ck('and his stumping', keeper && keeper[b.heads.indexOf('STUMPINGS')] === '1')
  ck('most dismissals first', /Gloves/.test(b.rows[0][0]) && /Spinks/.test(b.rows[1][0]), JSON.stringify(b.rows.map(r => r[0])))
  ck('each name links to the player', b.links.length === 3 && b.links.every(h => /^\/players\/p\d$/.test(h)), JSON.stringify(b.links))
  ck('a zero reads as a dash, not 0', b.rows.find(r => /Baker/.test(r[0]))?.slice(1).includes('—'))
}

console.log('-- a match with nothing recorded --')
await open(withFielding([]))
ck('no block is drawn at all', (await block()) === null)
await open(withFielding([{ player_id: 'p9', player_name: 'Zero, Zed', catches: 0, catches_wk: 0, run_outs: 0, stumpings: 0 }]))
ck('nor when every row is empty', (await block()) === null)

console.log('-- an older payload with no fielding key --')
const legacy = structuredClone(base); delete legacy.fielding
await open(legacy)
ck('the page still draws', (await page.locator('.pb-card').count()) > 0)
ck('and draws no block', (await block()) === null)

console.log('-- a fill-in with no player record --')
await open(withFielding([
  { player_id: null, player_name: 'Guest Player', catches: 1, catches_wk: 0, run_outs: 0, stumpings: 0, is_fill_in: true },
]))
b = await block()
ck('is listed by name', !!b && b.rows.length === 1 && /Guest/.test(b.rows[0][0]), JSON.stringify(b))
ck('and is not a link', !!b && b.links.length === 0)

console.log('-- narrow screens --')
await page.setViewportSize({ width: 390, height: 900 })
await open(withFielding([
  { player_id: 'p1', player_name: 'Spinks, Ray', catches: 2, catches_wk: 1, run_outs: 1, stumpings: 1 },
]))
b = await block()
ck('the block fits a phone without the page scrolling sideways', !!b && b.sw <= b.cw + 1, `${b?.sw} vs ${b?.cw}`)

ck('no page errors', errors.length === 0, errors.join(' | '))
console.log(`\n${pass} passed, ${fail} failed`)
await browser.close()
process.exit(fail ? 1 : 0)
