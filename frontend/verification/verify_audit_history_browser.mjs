// Drives the REAL Audit History screen in Chromium with the API stubbed at the network layer:
//   * it is a BetterSelect side-menu item and opens at /admin/betterselect/audit
//   * rows read as a diary: day heading, time, who, what, squad and game
//   * search, area, action, who, squad and date filters each put exactly that on the wire
//   * Export CSV asks for the file with the SAME filters and saves it under the server's name
//   * Show more pages by offset; Clear resets; an empty result says so; 390px has no overflow
//
//   npx vite preview --port 5199 &    node verify_audit_history_browser.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const OUT = process.env.SHOT_DIR || '/tmp'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }

const ME = { id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'o1', club_slug: 'gisborne', capabilities: ['*'], entitlements: { modules: ['select'], core_live: true, status: 'active' } }
const ev = (i, extra = {}) => ({
  id: `e${i}`, at: '2026-10-16T09:00:00Z', local_date: i < 4 ? '2026-10-16' : '2026-10-15', local_time: `0${9 - (i % 9)}:${10 + i}:00`,
  by: i % 2 ? 'Sam Selector' : 'Pat Admin', via: 'admin', area: 'selection', action: 'batting_order_changed', action_label: 'Batting order changed',
  player_id: `p${i}`, player: `Player ${i}`, team: 'MACs', game: 'MACs v Rovers, Sat 17 Oct', fixture_id: 'f1',
  summary: `Player ${i} moved up the batting order from no. 5 to no. 2 in MACs v Rovers, Sat 17 Oct`, detail: {}, ...extra,
})
const ALL = Array.from({ length: 130 }, (_, i) => ev(i + 1, i === 1 ? { area: 'squads', action: 'moved_squad', action_label: 'Moved squad', summary: 'Player 2 moved from MACs to Thirds' } : i === 2 ? { area: 'availability', action: 'availability_set', action_label: 'Availability set', by: 'Player 3', via: 'player link', summary: 'Player 3 marked Available for Sat 17 Oct' } : {}))
const FACETS = { users: ['Pat Admin', 'Sam Selector'], teams: ['MACs', 'Thirds'], areas: ['selection', 'availability', 'squads'],
  actions: [['added_to_xi', 'Added to XI'], ['batting_order_changed', 'Batting order changed'], ['made_captain', 'Made captain'], ['availability_set', 'Availability set'], ['moved_squad', 'Moved squad']].map(([value, label]) => ({ value, label })) }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const asked = []
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route('**/api/club-admin/settings', (r) => json(r, { name: 'Gisborne CC', short_name: 'Gisborne', player_name_format: 'first_last' }))
  await page.route(/\/api\/audit\/facets$/, (r) => json(r, FACETS))
  await page.route(/\/api\/audit\/events(\?.*)?$/, (r) => {
    const u = new URL(r.request().url()); asked.push(Object.fromEntries(u.searchParams))
    const p = Object.fromEntries(u.searchParams)
    let rows = ALL
    if (p.q === 'nobody') rows = []
    else if (p.area) rows = rows.filter((e) => e.area === p.area)
    const off = Number(p.offset || 0), lim = Number(p.limit || 100)
    return json(r, { total: rows.length, events: rows.slice(off, off + lim) })
  })
  await page.route(/\/api\/audit\/export\.csv(\?.*)?$/, (r) => {
    asked.push({ export: Object.fromEntries(new URL(r.request().url()).searchParams) })
    return r.fulfill({ status: 200, contentType: 'text/csv', headers: { 'content-disposition': 'attachment; filename="Gisborne-audit-history.csv"' }, body: '﻿Date,Time\r\n2026-10-16,09:10:00\r\n' })
  })

  await page.goto(`${BASE}/admin/betterselect/audit`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-audit-list]').waitFor({ timeout: 20000 })

  await safe('menu', async () => {
    console.log('\n── Where it lives ──')
    const link = page.locator('a[href="/admin/betterselect/audit"]').first()
    await link.waitFor({ state: 'attached' })
    check('Audit History is a side-menu item', /Audit History/.test(await link.innerText()))
    check('the page carries its name', /Audit History/.test(await page.locator('body').innerText()))
  })

  await safe('rows', async () => {
    console.log('\n── The list ──')
    check('the count says how many changes there are', /130 changes/.test(await page.locator('[data-audit-count]').innerText()), await page.locator('[data-audit-count]').innerText())
    check('the first page holds 100 rows', (await page.locator('[data-audit-row]').count()) === 100)
    const first = await page.locator('[data-audit-row]').first().innerText()
    check('a row has the time, what changed, who, the action, squad and game', /\d\d:\d\d/.test(first) && /moved up the batting order/.test(first) && /Sam Selector|Pat Admin/.test(first) && /Batting order changed/.test(first) && /MACs/.test(first) && /Rovers/.test(first), first)
    check('rows are grouped under a day heading', (await page.locator('[data-audit-list] h3').count()) >= 2)
    check('a player\'s own answer says it came from their link', /\(their own link\)/.test(await page.locator('[data-audit-action="availability_set"]').first().innerText()))
    asked.length = 0
    await page.locator('[data-audit-more]').click()
    await page.waitForTimeout(400)
    check('Show more asks for the next page by offset', asked.some((a) => a.offset === '100' && a.limit === '100'), JSON.stringify(asked))
    check('...and all 130 are then on the page', (await page.locator('[data-audit-row]').count()) === 130)
  })

  await safe('filters', async () => {
    console.log('\n── Filters ──')
    asked.length = 0
    await page.getByPlaceholder('Search players, people, squads, games…').fill('Player 2')
    await page.waitForTimeout(700)
    check('typing a search sends q', asked.some((a) => a.q === 'Player 2'), JSON.stringify(asked))
    await page.getByPlaceholder('Search players, people, squads, games…').fill('')
    asked.length = 0
    await page.locator('[data-audit-areas] button', { hasText: 'Squads' }).click()
    await page.waitForTimeout(500)
    check('the Squads chip sends area=squads', asked.some((a) => a.area === 'squads'), JSON.stringify(asked))
    check('...and only squad changes are listed', (await page.locator('[data-audit-row]').count()) === 1 && (await page.locator('[data-audit-row]').first().getAttribute('data-audit-action')) === 'moved_squad')
    check('the "What" chips follow the area (squad actions only)', (await page.locator('[data-audit-actions] button').allInnerTexts()).join() === 'Moved squad')
    await page.locator('[data-audit-areas] button', { hasText: 'Squads' }).click()
    asked.length = 0
    await page.locator('[data-audit-actions] button', { hasText: 'Made captain' }).click()
    await page.locator('[data-audit-actions] button', { hasText: 'Moved squad' }).click()
    await page.waitForTimeout(500)
    check('picking two actions sends them together', asked.some((a) => a.action === 'made_captain,moved_squad'), JSON.stringify(asked))
    asked.length = 0
    await page.locator('[data-audit-who]').selectOption('Pat Admin')
    await page.waitForTimeout(400)
    check('Changed by sends user', asked.some((a) => a.user === 'Pat Admin'), JSON.stringify(asked))
    await page.locator('[data-audit-team]').selectOption('Thirds')
    await page.locator('[data-audit-from]').fill('2026-10-01')
    await page.locator('[data-audit-to]').fill('2026-10-16')
    await page.waitForTimeout(500)
    const last = asked[asked.length - 1] || {}
    check('squad and both dates go on the wire with the rest', last.team === 'Thirds' && last.date_from === '2026-10-01' && last.date_to === '2026-10-16' && last.user === 'Pat Admin' && !!last.tz, JSON.stringify(last))
    check('the count says the filters matched', /match these filters/.test(await page.locator('[data-audit-count]').innerText()))
  })

  await safe('export', async () => {
    console.log('\n── Export ──')
    asked.length = 0
    const [dl] = await Promise.all([page.waitForEvent('download'), page.locator('[data-audit-export]').click()])
    const body = fs.readFileSync(await dl.path(), 'utf8')
    const exp = (asked.find((a) => a.export) || {}).export || {}
    check('the file is saved under the server\'s name', dl.suggestedFilename() === 'Gisborne-audit-history.csv', dl.suggestedFilename())
    check('the export carries the same filters as the list', exp.team === 'Thirds' && exp.user === 'Pat Admin' && exp.date_from === '2026-10-01' && exp.date_to === '2026-10-16' && exp.action === 'made_captain,moved_squad', JSON.stringify(exp))
    check('the file is the CSV that came back', body.includes('Date,Time'), body)
  })

  await safe('clear and empty', async () => {
    console.log('\n── Clear and empty ──')
    await page.locator('[data-audit-clear]').click()
    await page.waitForTimeout(500)
    check('Clear brings the whole list back', /130 changes/.test(await page.locator('[data-audit-count]').innerText()))
    await page.getByPlaceholder('Search players, people, squads, games…').fill('nobody')
    await page.waitForTimeout(700)
    check('a search with no match says so', /Nothing matches these filters/.test(await page.locator('body').innerText()))
  })

  await safe('390px', async () => {
    console.log('\n── 390px ──')
    await page.getByPlaceholder('Search players, people, squads, games…').fill('')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(600)
    check('no sideways overflow', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1))
    await page.screenshot({ path: `${OUT}/audit-history-390.png` })
    await page.setViewportSize({ width: 1280, height: 900 })
    await page.waitForTimeout(300)
    await page.screenshot({ path: `${OUT}/audit-history-1280.png` })
  })

  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run()
