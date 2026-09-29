// Drives the real StatLab screen in Chromium with the API stubbed at the
// network layer (the schema is the SHIPPED one, dumped by
// `python -c "import json; from app.services import statlab; print(json.dumps(statlab.schema(), default=str))"`).
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_statlab_player_browser.mjs [baseUrl]
//
// Two asks: a Player filter as the first thing in Build custom query, and the
// table-type tabs actually doing something — running the table and reshaping
// the filters to the ones that apply to it.
import { existsSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SCHEMA = JSON.parse(readFileSync(new URL('./fixtures/statlab_schema.json', import.meta.url)))

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
const ROW = (id, name) => ({ player_id: id, player_name: name, runs: 500, matches: 10, wickets: 3 })

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
  if (/^\/statlab\/query/.test(p)) {
    calls.push(Object.fromEntries([...url.searchParams.entries()]))
    const pid = url.searchParams.get('player_id')
    const rows = pid ? [ROW(pid, 'Smith, Jack')] : [ROW('p-1', 'Smith, Jack'), ROW('p-2', 'Jones, Tom')]
    return json({ rows, page: 1, has_more: false })
  }
  if (/^\/players$/.test(p)) return json(PLAYERS)
  if (/\/seasons$/.test(p)) return json([{ id: 's-1', name: 'Summer 2025/26', year: 2025 }])
  if (/grade-categories/.test(p)) return json({ available: ['senior'], default: ['senior'], available_formats: [] })
  if (/families/.test(p)) return json([])
  if (/grades/.test(p)) return json([])
  return json({})
})

// Every read of something this change ADDS goes through a helper that reports
// absence rather than throwing, so a control run against the old build says
// which checks fail instead of dying on the first missing locator.
const textOf = async (loc) => (await loc.count()) ? (await loc.first().innerText()) : ''
const LABELS = { player_career: 'PLAYER CAREER', spell_list: 'BOWLING SPELLS', family_career: 'FAMILY CAREER',
  match_list: 'MATCH LIST', innings_list: 'INNINGS LIST', team_innings_list: 'TEAM INNINGS' }
const tab = (key) => page.locator(`[data-target="${key}"]`).or(page.getByText(LABELS[key], { exact: true })).first()

await page.goto(`${BASE}/our-club/statlab`)
await page.getByText('PLAYER CAREER', { exact: true }).first().waitFor({ timeout: 20000 })

// ── the tabs run the table and explain it ────────────────────────────────
const guide = page.getByTestId('statlab-target-guide')
ck('the guide says what a Player career row is', /whole career/.test(await textOf(guide)))
const before = calls.length
await tab('spell_list').click()
await page.waitForTimeout(400)
const last = calls[calls.length - 1] || {}
ck('picking a tab runs the table straight away', calls.length > before && last.target === 'spell_list', JSON.stringify(last))
ck('the sort snaps to one bowling spells actually has', last.sort_by === 'wickets' || (SCHEMA.targets.spell_list.metrics || []).includes(last.sort_by), last.sort_by)
ck('the guide changes with the tab', /bowling spell/.test(await textOf(guide)))
ck('the tab reads as selected', await tab('spell_list').getAttribute('aria-selected') === 'true')
const text = async () => (await page.locator('main').innerText())
ck('bowling spells: no Dismissal filter (it is a batting filter)', !/\bDismissal\b/i.test(await text()))
ck('bowling spells: player attributes still shown', /PLAYER ATTRIBUTES/.test(await text()))
ck('bowling spells: quick starts offered for this table', (await textOf(guide)).includes('Best bowling in an innings'))

await tab('family_career').click()
await page.waitForTimeout(400)
ck('family career: no Player picker', await page.getByTestId('statlab-player-picker').count() === 0)
ck('family career: no Opposition filter (a family total has no games)', !/Opposition/.test(await text()))
ck('family career: no player attributes', !/PLAYER ATTRIBUTES/.test(await text()))

await tab('match_list').click()
await page.waitForTimeout(400)
ck('match list: the player filter explains itself for matches', /matches this player played in/i.test(await text()))
ck('match list: opposition filter back', /Opposition/.test(await text()))

// ── the Player filter, first in Build custom query ───────────────────────
await tab('player_career').click()
await page.waitForTimeout(400)
const picker = page.getByTestId('statlab-player-picker')
ck('player career: the Player picker is shown', await picker.count() === 1)
const pickerBox = (await picker.count()) ? await picker.boundingBox() : null
const sortBox = await page.getByText('Sort by', { exact: true }).first().boundingBox()
ck('the Player picker is the first thing, above Sort by', pickerBox && sortBox && pickerBox.y < sortBox.y,
  `${pickerBox?.y} vs ${sortBox?.y}`)
if (await picker.count()) {
  await picker.getByRole('textbox').fill('smi')
  const opt = page.getByRole('button', { name: 'Smith, Jack' })
  if (await opt.count()) await opt.click()
}
ck('picking a player shows them as chosen',
  (await textOf(page.getByTestId('statlab-player-chosen'))).includes('Smith, Jack'))
ck('the player lands in the URL', new URL(page.url()).searchParams.get('c_player_id') === 'p-1', page.url())
await page.getByRole('button', { name: /Run query/ }).click()
await page.waitForTimeout(400)
const q = calls[calls.length - 1] || {}
ck('the query sends player_id on the wire', q.player_id === 'p-1', JSON.stringify(q))
ck('a chip names the player', /Player: Smith, Jack/.test(await text()))

// a filter that still applies survives a tab switch; one that does not is dropped
await tab('innings_list').click()
await page.waitForTimeout(400)
ck('switching to Innings list keeps the player', (calls[calls.length - 1] || {}).player_id === 'p-1')
await tab('team_innings_list').click()
await page.waitForTimeout(400)
ck('Team innings cannot take a player, so it is dropped rather than hidden',
  !(calls[calls.length - 1] || {}).player_id && !new URL(page.url()).searchParams.get('c_player_id'))

await tab('player_career').click()
await page.waitForTimeout(300)
await page.setViewportSize({ width: 390, height: 900 })
await page.waitForTimeout(300)
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
ck('no horizontal overflow at 390px', overflow <= 0, String(overflow))
ck('no page errors', errors.length === 0, errors.join(' | '))

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
