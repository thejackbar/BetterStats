/**
 * Drive the printed cheat sheet in a real browser.
 *
 * Reported (Applecross, a One Day Grade 4 fixture vs North Perth): the top right said
 * "Twenty20 Div 1" (the LAST MEETING's grade) and "Our edge" named players who were not
 * in the picked XI. The API is stubbed at the network layer the way the server answers.
 *
 * Checks: the sheet asks for `selected_only` with the fixture id; the header shows the
 * fixture's grade and the last meeting's grade sits under "Last meeting"; "Our edge" is
 * labelled with the XI and shows what the server sent; a fixture with nobody picked says
 * so instead of listing the squad; the opponent-only sheet (no fixture) is unchanged.
 *
 * Run against a dev or served build:  node scripts/verify-cheatsheet-xi.mjs [baseUrl]
 */
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:5199'
const FID = 'fef8eb7c-e1a1-4ec6-98ff-e928cef46c0f'
const pass = [], fail = []
const check = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  ;(ok ? pass : fail).push(label)
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}: ${JSON.stringify(got)}${ok ? '' : ` (wanted ${JSON.stringify(want)})`}`)
}
const json = (route, body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

let xiStatus = 'confirmed'
const reportCalls = []
const report = () => ({
  fixture: { fixture_id: FID, grade_name: 'One Day Grade 4', team_name: 'OD4s', played_on: '2026-10-24' },
  selected_xi: xiStatus ? { status: xiStatus, count: xiStatus === 'none' ? 0 : 2 } : null,
  opponent: { opp_key: 'k', name: 'North Perth 4th XI' },
  coverage: { level: 'limited', note: '' },
  head_to_head: { wins: 112, losses: 84, draws: 2, ties: 0, win_pct: 57, recent_form: ['L', 'L', 'W', 'W', 'L'] },
  last_meeting: { grade: 'Twenty20 Div 1', result: 'loss', our_runs: 121, opp_runs: 175 },
  our_performers: xiStatus === 'none' || xiStatus === 'empty'
    ? { batting: [], bowling: [] }
    : { batting: [{ player_id: 'p1', name: 'Pat Picked', runs: 33, average: 16.5 }], bowling: [{ player_id: 'p2', name: 'Wes Wicket', wickets: 3, average: 23.67 }] },
  their_danger_batters: [], matchups: { bowler_dominance: [] }, venues: [],
})

const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {})
const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } })
const errors = []
page.on('pageerror', e => errors.push(String(e)))

await page.route('**/api/**', async route => {
  const url = new URL(route.request().url())
  const path = url.pathname.replace(/^.*\/api/, '')
  if (path === '/auth/me') return json(route, { id: 'u1', email: 'a@b.c', role: 'super_admin', club_id: 'o1', club_name: 'Applecross CC', capabilities: [], modules: ['iq'] })
  if (path === '/club-admin/settings') return json(route, { name: 'Applecross Cricket Club', short_name: 'Applecross Cricket Club' })
  if (path === '/iq/opposition/report') { reportCalls.push(url.search); return json(route, report()) }
  if (path === '/iq/opposition/dossier') return json(route, { status: 'ready', game_plan: null, danger_batters: [], danger_bowlers: [], opponent: { name: 'North Perth 4th XI' } })
  return json(route, {})
})

const headerRight = () => page.$eval('.iq-cs-header .shrink-0', e => e.innerText)
const columnText = title => page.evaluate(t => {
  const col = [...document.querySelectorAll('.iq-print-area .min-w-0')].find(e => e.firstElementChild?.textContent.startsWith(t))
  return col ? col.innerText : null
}, title)

// 1. confirmed XI
await page.goto(`${BASE}/admin/betteriq/opposition/cheatsheet?fixture=${FID}`)
await page.waitForSelector('.iq-cs-header', { timeout: 20000 })
await page.waitForSelector('text=Pat Picked', { timeout: 10000 })
check('the sheet asks for the picked XI only, for this fixture',
  reportCalls.some(q => q.includes('selected_only=true') && q.includes(`fixture_id=${FID}`)), true)
const hr = await headerRight()
check('header shows the fixture\'s own grade', hr.includes('One Day Grade 4'), true)
check('header does not show the last meeting\'s grade', hr.includes('Twenty20'), false)
const lm = await page.evaluate(() => [...document.querySelectorAll('.iq-print-area div')].find(d => d.textContent.trim().startsWith('Last meeting') && d.querySelector('.iq-mono'))?.innerText || '')
check('the last meeting\'s grade is captioned under Last meeting', lm.includes('Twenty20 Div 1'), true)
check('head to head says it spans all grades', (await page.innerText('.iq-print-area')).toLowerCase().includes('head to head, all grades'), true)
const edge = await columnText('Our edge')
check('our edge is labelled with the picked XI', edge?.startsWith('Our edge (picked XI)'), true)
check('our edge shows the picked players', ['Picked', 'Wicket'].every(n => edge?.includes(n)), true)
await page.screenshot({ path: process.env.SHOT || '/tmp/claude-0/cheatsheet-xi-confirmed.png', fullPage: true })

// 2. draft
xiStatus = 'draft'
reportCalls.length = 0
await page.goto(`${BASE}/admin/betteriq/opposition/cheatsheet?fixture=${FID}`)
await page.waitForSelector('text=Pat Picked', { timeout: 10000 })
check('a draft XI is labelled as a draft', (await columnText('Our edge'))?.startsWith('Our edge (draft XI)'), true)

// 3. nothing picked
xiStatus = 'none'
await page.goto(`${BASE}/admin/betteriq/opposition/cheatsheet?fixture=${FID}`)
await page.waitForSelector('text=No XI picked for this fixture yet', { timeout: 10000 })
const none = await columnText('Our edge')
check('nothing picked: says so, no players listed', none?.includes('No XI picked') && !none.includes('Pat Picked'), true)

// 4. picked XI with no record against them
xiStatus = 'empty'
await page.goto(`${BASE}/admin/betteriq/opposition/cheatsheet?fixture=${FID}`)
await page.waitForSelector('text=Nobody in the picked XI has a record', { timeout: 10000 })
const emptyEdge = await columnText('Our edge')
check('picked XI with no record: says that, not "no XI picked"',
  emptyEdge?.includes('Nobody in the picked XI has a record') && !emptyEdge.includes('No XI picked'), true)

// 5. opponent-only sheet (no fixture): old wording and request
xiStatus = null
reportCalls.length = 0
await page.goto(`${BASE}/admin/betteriq/opposition/cheatsheet?opponent=k`)
await page.waitForSelector('text=Pat Picked', { timeout: 10000 })
check('no fixture: selected_only is not sent', reportCalls.some(q => q.includes('selected_only')), false)
check('no fixture: the column keeps its plain title', (await columnText('Our edge'))?.startsWith('Our edge\n'), true)

// 6. phone width
await page.setViewportSize({ width: 390, height: 900 })
xiStatus = 'confirmed'
await page.goto(`${BASE}/admin/betteriq/opposition/cheatsheet?fixture=${FID}`)
await page.waitForSelector('text=Pat Picked', { timeout: 10000 })
check('no horizontal overflow at 390px', (await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0, true)
check('no page errors', errors, [])

await browser.close()
console.log(`\n${pass.length} passed, ${fail.length} failed`)
process.exit(fail.length ? 1 : 0)
