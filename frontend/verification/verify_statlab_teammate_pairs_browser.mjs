// Drives the real StatLab screen in Chromium with the API stubbed at the network layer (the schema
// is the SHIPPED one, fixtures/statlab_schema.json) for the teammate pair reports.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_statlab_teammate_pairs_browser.mjs [baseUrl]
//
// Asks: a "Teammates & Pairs" group with games together, win rate together, bowler and fielder
// dismissals (filterable to the wicketkeeper), opening pairs; a player picker on them; the
// Fielder and Minimum games controls on the one report each belongs to; and no leftover control
// when another report is picked.
import { existsSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SCHEMA = JSON.parse(readFileSync(new URL('./fixtures/statlab_schema.json', import.meta.url)))
const SHOT = process.env.SHOT_DIR

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const CLUB = {
  id: 'org-1', name: 'Our Club', slug: 'our-club', short_name: 'OCC',
  is_active: true, primary_color: '#1b8f4d', accent_color: '#1b8f4d',
  theme_config: {}, font_config: {}, logo_url: null, modules: [],
}
const PLAYERS = [
  { id: 'p-1', name: 'Smith, Jack', display_name: 'Smith, Jack' },
  { id: 'p-2', name: 'Jones, Tom', display_name: 'Jones, Tom' },
]
const PAIR = { player_a_id: 'p-1', player_a_name: 'Smith, Jack', player_b_id: 'p-2', player_b_name: 'Jones, Tom' }
const ROWS = {
  games_together: [{ ...PAIR, games: 41, wins: 25, losses: 14, draws: 2, win_pct: '61.0', first_game: '2019-10-12', last_game: '2025-03-01' }],
  win_rate_together: [{ ...PAIR, win_pct: '72.5', sided_games: 40, wins: 29, losses: 10, draws: 1 }],
  bowler_fielder_dismissals: [{ ...PAIR, dismissals: 17, catches: 15, catches_wk: 12, stumpings: 2 }],
  opening_bowling_pairs: [{ ...PAIR, innings: 22, matches: 20, wickets: 61 }],
  opening_batting_pairs: [{ ...PAIR, stands: 30, total_runs: 1180, average: '39.3', best: 142, fifty_stands: 7 }],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const errors = []
page.on('pageerror', e => errors.push(String(e)))
const calls = []
await page.route('**/api/**', async (route) => {
  const url = new URL(route.request().url())
  const p = url.pathname.replace(/^\/api/, '')
  const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  if (/^\/auth\/me/.test(p)) return route.fulfill({ status: 401, body: '{}' })
  if (/^\/clubs\/our-club$/.test(p)) return json(CLUB)
  if (/^\/statlab\/schema/.test(p)) return json(SCHEMA)
  if (/^\/statlab\/reports/.test(p)) return json([])
  if (/^\/statlab\/derived\//.test(p)) {
    const name = p.split('/').pop()
    calls.push({ name, ...Object.fromEntries([...url.searchParams.entries()]) })
    return json({ rows: ROWS[name] || [], page: 1, has_more: false })
  }
  if (/^\/players$/.test(p)) return json(PLAYERS)
  if (/\/seasons$/.test(p)) return json([{ id: 's-1', name: 'Summer 2025/26', year: 2025 }])
  if (/grade-categories/.test(p)) return json({ available: ['senior'], default: ['senior'], available_formats: [] })
  if (/families/.test(p)) return json([])
  if (/grades/.test(p)) return json([])
  return json({})
})

const textOf = async (loc) => (await loc.count()) ? (await loc.first().innerText()) : ''
const main = () => page.locator('main').innerText()
const last = () => calls[calls.length - 1] || {}

await page.goto(`${BASE}/our-club/statlab`)
const group = page.getByText('TEAMMATES & PAIRS', { exact: true }).first()
await group.waitFor({ timeout: 20000 })
await group.click()
const item = (label) => page.getByText(label, { exact: true }).first()

for (const label of ['Most games played together', 'Best win rate together', 'Bowler and fielder dismissals',
                     'Opening bowling pairs', 'Opening batting pairs']) {
  ck(`the group lists "${label}"`, await page.getByText(label, { exact: true }).count() >= 1)
}
ck('the old catches-only entry is gone from the Bowling menu (the new report covers it)',
  await page.getByText('Top bowler/fielder combinations', { exact: true }).count() === 0)

// ── games together ──────────────────────────────────────────────────────
await item('Most games played together').click()
await page.waitForTimeout(500)
ck('runs the report straight away', last().name === 'games_together', JSON.stringify(last()))
let t = await main()
ck('the pair is one cell, A & B', /Smith, Jack\s*&\s*Jones, Tom/.test(t))
ck('games, wins and win percent are shown', /41/.test(t) && /25/.test(t) && /61\.00/.test(t))
ck('the count says pairs, not players', /1 PAIRS/.test(t), t.slice(0, 120))
ck('the dates read as dates', /2019-10-12/.test(t) && /2025-03-01/.test(t))
await page.getByText('+ BUILD CUSTOM QUERY', { exact: true }).click()
await page.waitForTimeout(300)
ck('a player picker is offered for a pair report', await page.getByTestId('statlab-player-picker').count() === 1)
ck('...and says what it does', /Only pairs this player is in/.test(await main()))
ck('no player attribute filters (one flag cannot describe a pair)', !/PLAYER ATTRIBUTES/.test(await main()))
ck('no Dismissal filter either', !/\bDismissal\b/i.test(await main()))
ck('the Fielder control is not here', await page.getByText('Fielder', { exact: true }).count() === 0)
ck('the Minimum games control is not here', !/Minimum games together/.test(await main()))

const picker = page.getByTestId('statlab-player-picker')
await picker.getByRole('textbox').fill('smi')
const opt = page.getByRole('button', { name: 'Smith, Jack' })
if (await opt.count()) await opt.click()
await page.getByRole('button', { name: /Run query/ }).click()
await page.waitForTimeout(500)
ck('the player goes on the wire', last().name === 'games_together' && last().player_id === 'p-1', JSON.stringify(last()))
ck('a chip names the player', /Player: Smith, Jack/.test(await main()))
if (SHOT) await page.screenshot({ path: `${SHOT}/games_together.png`, fullPage: false })

// ── bowler and fielder dismissals: the keeper filter ────────────────────
await item('Bowler and fielder dismissals').click()
await page.waitForTimeout(500)
ck('runs the dismissals report', last().name === 'bowler_fielder_dismissals', JSON.stringify(last()))
ck('the picked player stays picked on a report that can use one', last().player_id === 'p-1', JSON.stringify(last()))
ck('no fielder filter sent until one is chosen', !('fielder_role' in last()), JSON.stringify(last()))
t = await main()
ck('BOWLER and FIELDER are separate columns', /BOWLER/.test(t) && /FIELDER/.test(t))
ck('the figures: dismissals, catches, keeper catches, stumpings', /17/.test(t) && /15/.test(t) && /12/.test(t))
const sel = page.locator('select').filter({ has: page.locator('option', { hasText: 'Wicketkeeper' }) })
ck('a Fielder control with a wicketkeeper option', await sel.count() === 1)
if (await sel.count()) {
  await sel.selectOption('keeper')
  await page.getByRole('button', { name: /Run query/ }).click()
  await page.waitForTimeout(500)
}
ck('choosing the wicketkeeper sends fielder_role=keeper', last().fielder_role === 'keeper', JSON.stringify(last()))
ck('a chip names the keeper filter', /Fielder: wicketkeeper/.test(await main()))
if (SHOT) await page.screenshot({ path: `${SHOT}/dismissals_keeper.png`, fullPage: false })

// ── win rate: the games floor ───────────────────────────────────────────
await item('Best win rate together').click()
await page.waitForTimeout(500)
ck('runs win rate', last().name === 'win_rate_together', JSON.stringify(last()))
ck('the keeper filter is dropped, not left scoping a report that cannot read it', !('fielder_role' in last()) && !/Fielder: wicketkeeper/.test(await main()), JSON.stringify(last()))
const floor = page.locator('select').filter({ has: page.locator('option', { hasText: 'games with a known side' }) })
ck('a Minimum games control, defaulting to 10', await floor.count() === 1 && (await floor.inputValue()) === '10')
if (await floor.count()) {
  await floor.selectOption('20')
  await page.getByRole('button', { name: /Run query/ }).click()
  await page.waitForTimeout(500)
}
ck('the floor goes on the wire', last().min_games === '20', JSON.stringify(last()))

// ── the control: a one-player report keeps the attribute filters and has no picker ──
await page.getByText('FIELDING & KEEPING', { exact: true }).first().click()
await page.getByText('Top catches & stumpings combined', { exact: true }).first().click()
await page.waitForTimeout(500)
ck('control: a per-player report still shows the player attribute filters', /PLAYER ATTRIBUTES/.test(await main()))
ck('control: ...and has no pair picker', await page.getByTestId('statlab-player-picker').count() === 0)
ck('control: the picked player was dropped, not left scoping it', !('player_id' in last()), JSON.stringify(last()))

// ── the other two ───────────────────────────────────────────────────────
for (const [label, key, probe] of [['Opening bowling pairs', 'opening_bowling_pairs', /61/], ['Opening batting pairs', 'opening_batting_pairs', /1,?180/]]) {
  await item(label).first().click()
  await page.waitForTimeout(500)
  ck(`${label}: runs and shows its figures`, last().name === key && probe.test(await main()), JSON.stringify(last()))
}

// ── layout ──────────────────────────────────────────────────────────────
await page.setViewportSize({ width: 390, height: 900 })
await page.waitForTimeout(400)
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
ck('no horizontal overflow at 390px', overflow <= 0, String(overflow))
if (SHOT) await page.screenshot({ path: `${SHOT}/mobile.png`, fullPage: false })
ck('no page errors', errors.length === 0, errors.join(' | '))

console.log(`\n${pass} passed, ${fail} failed`)
await browser.close()
process.exit(fail ? 1 : 0)
