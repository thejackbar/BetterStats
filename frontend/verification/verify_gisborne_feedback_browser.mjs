// Drives the real BetterSelect screens in Chromium with the API stubbed at the
// network layer, for the Gisborne feedback round:
//   * Availability: the filters survive a trip to another screen; juniors are left
//     out until asked for (the request says so); the juniors switch is remembered
//   * Squads: a card's x removes the player from THAT squad only (request on the
//     wire); Alt-drop copies (action 'add', not 'move'); the order control sorts
//     A to Z by first name and by surname; Export lists writes a CSV with a club
//     header and a real PDF
//   * 390px: no sideways overflow
//
//   (serve the production build)  npx vite preview --port 5199 &
//   node verify_gisborne_feedback_browser.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const iso = (daysAhead) => { const d = new Date(); d.setDate(d.getDate() + daysAhead); return d.toISOString().slice(0, 10) }
const FIRSTS = '11111111-1111-1111-1111-111111111111'
const SECONDS = '22222222-2222-2222-2222-222222222222'

const P = (id, name, extra) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null, hero_photo_url: null,
  gender: 'male', is_player: true, player_role: null, is_overseas: false, skill_positions: [],
  status: 'active', is_public: true, squad_team_id: null, last_played: iso(-20), age: null,
  squad_team_ids: [], ...extra,
})
// Stored "Last, First": Zed Adams sorts last by first name, first by surname.
const PLAYERS = [
  P('p-anna', 'Brown, Anna', { squad_team_ids: [FIRSTS] }),
  P('p-bob', 'Adams, Zed', { squad_team_ids: [FIRSTS, SECONDS] }),
  P('p-cara', 'Cole, Cara', { squad_team_ids: [FIRSTS] }),
  P('p-dan', 'Dunn, Dan', {}),
]
const TEAMS = [
  { id: FIRSTS, name: '1st XI', short_name: '1s', sequence: 1, is_active: true, grade_id: null, grade_name: 'Mens A' },
  { id: SECONDS, name: '2nd XI', short_name: '2s', sequence: 2, is_active: true, grade_id: null, grade_name: 'Mens B' },
]
const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1',
  club_slug: 'gisborne', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
const MATRIX = (juniors) => ({
  dates: [{ date: iso(7), fixtures: [{ id: 'f1', label: null, opponent_name: 'Rovers', home_away: 'HOME', role: 'single', two_day: false, team_id: FIRSTS, grade_id: null }] },
    ...(juniors ? [{ date: iso(8), fixtures: [{ id: 'f2', label: 'U14', opponent_name: 'Kids', home_away: 'HOME', role: 'single', two_day: false, team_id: null, grade_id: null }] }] : [])],
  players: PLAYERS.map((p) => ({ id: p.id, display_name: p.display_name, name: p.name, squads: [], is_current: true, last_played: p.last_played, player_role: null })),
  availability: {}, all_squads: ['1st XI', '2nd XI'], dormancy_months: 24, squad_next: {}, rules: { active: false, applied: [] },
})

const wire = []
async function stub(page) {
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = req.url()
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (req.method() !== 'GET') wire.push({ method: req.method(), url, body: req.postData() })
    else if (url.includes('/availability/matrix')) wire.push({ method: 'GET', url })
    if (url.includes('/auth/me')) return json(ME)
    if (url.includes('/club-admin/settings')) return json({ name: 'Gisborne CC', short_name: 'Gisborne', player_name_format: 'first_last', theme_config: { accent: '#0a7d3b', accent2: '#e0b100' } })
    if (url.includes('/club-admin/players')) return json(PLAYERS)
    if (url.includes('/availability/matrix')) return json(MATRIX(url.includes('juniors=true')))
    if (url.includes('/teams/squad-assign')) return json({ ok: true })
    if (url.includes('/teams/grade-options')) return json({ seasons: [] })
    if (url.match(/\/teams(\?|$)/)) return json(TEAMS)
    if (url.includes('/selection/selected-players')) return json({ player_ids: [] })
    if (url.includes('/fixtures')) return json([])
    return json({})
  })
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error' && !/Failed to load resource|ERR_CONNECTION|ERR_NAME_NOT_RESOLVED/.test(m.text())) errors.push(m.text())
  })
  await stub(page)

  /* ───────── Availability ───────── */
  await page.goto(`${BASE}/admin/betterselect/availability`, { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('Search players…').waitFor({ timeout: 20000 })
  const firstMatrix = wire.find((w) => w.url.includes('/availability/matrix'))
  check('juniors are NOT requested by default', !!firstMatrix && !firstMatrix.url.includes('juniors=true'), firstMatrix?.url)

  const search = page.getByPlaceholder('Search players…')
  await search.fill('zed')
  await page.waitForTimeout(300)
  check('typing a search puts it in the URL', page.url().includes('q=zed'), page.url())

  // Leave for another screen through the sidebar (its links carry no query string) and come back.
  await page.locator('a[href="/admin/betterselect/fixtures"]').first().click()
  await page.waitForTimeout(600)
  check('on the Fixtures screen the availability filter is gone from the URL', !page.url().includes('q=zed'), page.url())
  await page.locator('a[href="/admin/betterselect/availability"]').first().click()
  await page.getByPlaceholder('Search players…').waitFor({ timeout: 20000 })
  await page.waitForTimeout(500)
  check('coming back restores the search in the URL', page.url().includes('q=zed'), page.url())
  check('...and in the search box', (await page.getByPlaceholder('Search players…').inputValue()) === 'zed')

  // Clearing is remembered too: it must not spring back.
  await page.getByPlaceholder('Search players…').fill('')
  await page.waitForTimeout(300)
  await page.locator('a[href="/admin/betterselect/fixtures"]').first().click()
  await page.waitForTimeout(500)
  await page.locator('a[href="/admin/betterselect/availability"]').first().click()
  await page.getByPlaceholder('Search players…').waitFor({ timeout: 20000 })
  await page.waitForTimeout(500)
  check('a cleared search stays cleared after leaving and returning', !page.url().includes('q='), page.url())

  // A link that carries its own filter beats the remembered one.
  await page.goto(`${BASE}/admin/betterselect/availability?q=dan`, { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('Search players…').waitFor({ timeout: 20000 })
  check('a link with its own filter is not overwritten', (await page.getByPlaceholder('Search players…').inputValue()) === 'dan')

  wire.length = 0
  if (await page.getByText('Show juniors').count()) await page.getByText('Show juniors').click()
  await page.waitForTimeout(500)
  check('"Show juniors" asks the server for juniors', wire.some((w) => w.url.includes('/availability/matrix') && w.url.includes('juniors=true')),
    JSON.stringify(wire.map((w) => w.url)))
  await page.goto(`${BASE}/admin/betterselect/availability`, { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('Search players…').waitFor({ timeout: 20000 })
  await page.waitForTimeout(400)
  check('the juniors switch is remembered on this device', (await page.getByText('Juniors shown').count()) === 1)
  if (await page.getByText('Juniors shown').count()) await page.getByText('Juniors shown').click()
  await page.waitForTimeout(300)

  /* ───────── Squads ───────── */
  await page.goto(`${BASE}/admin/betterselect/teams`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.pb-card', { timeout: 20000 })
  await page.waitForTimeout(500)
  const hint = (await page.locator('[data-squad-hint]').count()) ? await page.locator('[data-squad-hint]').innerText() : ''
  check('the board explains move, copy (Alt), × and ＋', /Alt/.test(hint) && /×/.test(hint) && /＋/.test(hint), hint)

  const colOf = (title) => page.locator('.pb-card', { has: page.locator('.font-display', { hasText: new RegExp(`^${title}$`) }) }).first()
  const namesIn = async (title) => colOf(title).locator('[draggable="true"] .flex-1').allInnerTexts()

  // The club's real squads come first; the working pools sit at the end unless asked for.
  const order = async () => page.locator('.pb-card .font-display').allInnerTexts()
  let titles = await order()
  const iUn = titles.findIndex((t) => /^Unassigned/.test(t)), iSq = titles.findIndex((t) => t === '1s')
  check('squads come before the Unassigned pools', iSq >= 0 && iUn > iSq, JSON.stringify(titles))
  check('...and the first card on the board is a squad', titles[0] === '1s', JSON.stringify(titles))
  await page.locator('[data-pools-at]').selectOption('start')
  await page.waitForTimeout(250)
  titles = await order()
  check('"Pools first" puts them back at the front', /^Unassigned/.test(titles[0] || ''), JSON.stringify(titles))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.pb-card', { timeout: 20000 })
  check('...and the choice is remembered', /^Unassigned/.test((await order())[0] || ''))
  await page.locator('[data-pools-at]').selectOption('end')
  await page.waitForTimeout(250)

  // × on Zed Adams in the 1st XI
  wire.length = 0
  const zed1 = colOf('1s').locator('[draggable="true"]', { hasText: 'Zed' }).first()
  if (await zed1.locator('[data-remove-from-squad]').count()) await zed1.locator('[data-remove-from-squad]').click()
  await page.waitForTimeout(400)
  const rm = wire.find((w) => w.url.includes('/teams/squad-assign'))
  const rmBody = rm ? JSON.parse(rm.body) : {}
  check('× sends a REMOVE for that one squad', rmBody.action === 'remove' && rmBody.from_squad_team_id === FIRSTS && (rmBody.player_ids || []).join() === 'p-bob', rm?.body)
  check('...and Zed leaves the 1st XI column', !(await namesIn('1s')).some((n) => /Zed/.test(n)), JSON.stringify(await namesIn('1s')))
  check('...but is still in the 2nd XI column', (await namesIn('2s')).some((n) => /Zed/.test(n)), JSON.stringify(await namesIn('2s')))
  check('cards in Unassigned have no ×', (await page.locator('.pb-card', { has: page.locator('.font-display', { hasText: /^Unassigned$/ }) }).first().locator('[data-remove-from-squad]').count()) === 0)

  // Names are the point of the board: in a three-column squad screen the name
  // takes most of the card, and the add / remove buttons only show on hover.
  await page.setViewportSize({ width: 860, height: 900 })
  await page.waitForTimeout(300)
  const share = await page.evaluate(() => {
    const out = []
    document.querySelectorAll('[draggable="true"]').forEach((card) => {
      const n = card.querySelector('span.truncate')
      if (n) out.push(n.getBoundingClientRect().width / card.getBoundingClientRect().width)
    })
    return out
  })
  check('names take most of each squad card at 860px', share.length > 0 && Math.min(...share) > 0.55, JSON.stringify(share.map((x) => +x.toFixed(2))))
  const acts = page.locator('[draggable="true"]').first().locator('[data-card-actions]')
  check('add and remove buttons stay out of the way until hover', (await acts.count()) === 1 && (await acts.evaluate((e) => getComputedStyle(e).opacity)) === '0')
  await page.locator('[draggable="true"]').first().hover()
  await page.waitForTimeout(250)
  check('...and appear when the card is hovered', (await acts.evaluate((e) => getComputedStyle(e).opacity)) === '1')
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.waitForTimeout(200)

  // Alt-drop copy: Anna from 1s onto 2s
  wire.length = 0
  await page.evaluate(() => {
    const cols = [...document.querySelectorAll('.pb-card')]
    const card = (t) => cols.find((c) => c.querySelector('.font-display')?.textContent.trim() === t)
    const anna = [...card('1s').querySelectorAll('[draggable="true"]')].find((n) => /Anna/.test(n.textContent))
    const dt = new DataTransfer()
    anna.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }))
    const target = card('2s')
    target.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }))
    target.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt, altKey: true }))
  })
  await page.waitForTimeout(400)
  const cp = wire.find((w) => w.url.includes('/teams/squad-assign'))
  const cpBody = cp ? JSON.parse(cp.body) : {}
  check('Alt-drop is an ADD, not a MOVE', cpBody.action === 'add' && cpBody.squad_team_id === SECONDS, cp?.body)
  check('...Anna is in both squads afterwards', (await namesIn('1s')).some((n) => /Anna/.test(n)) && (await namesIn('2s')).some((n) => /Anna/.test(n)))

  // Plain drop still moves
  wire.length = 0
  await page.evaluate(() => {
    const cols = [...document.querySelectorAll('.pb-card')]
    const card = (t) => cols.find((c) => c.querySelector('.font-display')?.textContent.trim() === t)
    const cara = [...card('1s').querySelectorAll('[draggable="true"]')].find((n) => /Cara/.test(n.textContent))
    const dt = new DataTransfer()
    cara.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }))
    card('2s').dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
  })
  await page.waitForTimeout(400)
  const mv = wire.find((w) => w.url.includes('/teams/squad-assign'))
  const mvBody = mv ? JSON.parse(mv.body) : {}
  check('a plain drop is still a MOVE', mvBody.action === 'move' && mvBody.from_squad_team_id === FIRSTS, mv?.body)

  // Order: first name vs surname. 2nd XI now holds Zed Adams, Anna Brown, Cara Cole.
  if (await page.locator('[data-squad-sort]').count()) await page.locator('[data-squad-sort]').selectOption('first')
  await page.waitForTimeout(300)
  const byFirst = (await namesIn('2s')).map((n) => n.replace(/\s+/g, ' '))
  check('first-name order puts Anna before Cara before Zed', byFirst.findIndex((n) => /Anna/.test(n)) < byFirst.findIndex((n) => /Cara/.test(n)) && byFirst.findIndex((n) => /Cara/.test(n)) < byFirst.findIndex((n) => /Zed/.test(n)), JSON.stringify(byFirst))
  if (await page.locator('[data-squad-sort]').count()) await page.locator('[data-squad-sort]').selectOption('last')
  await page.waitForTimeout(300)
  const byLast = (await namesIn('2s')).map((n) => n.replace(/\s+/g, ' '))
  check('surname order puts Adams (Zed) first', /Zed/.test(byLast[0] || ''), JSON.stringify(byLast))

  // Export
  if (!(await page.getByRole('button', { name: 'Export lists' }).count())) {
    check('Export lists is on the Squads board', false, 'no button')
  } else {
    await page.getByRole('button', { name: 'Export lists' }).click()
    await page.waitForSelector('[data-export-modal]')
    const [csvDl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'CSV', exact: true }).click()])
    const csvPath = await csvDl.path()
    const csv = fs.readFileSync(csvPath, 'utf8')
    check('CSV file is named for the club', /Gisborne - squads\.csv$/.test(csvDl.suggestedFilename()), csvDl.suggestedFilename())
    check('CSV opens with the club name and a printed date', /^﻿Gisborne CC squad lists\r\nPrinted /.test(csv), csv.slice(0, 80))
    check('CSV has a header row and the players with their squad', csv.includes('Squad,Grade,#,Shirt,Player,Role') && /1st XI,Mens A,\d,,(.*Anna)/.test(csv), csv)
    check('CSV leaves out nobody who is in the squad', csv.includes('Cara') && csv.includes('Zed'))

    await page.getByRole('button', { name: 'Export lists' }).click()
    await page.waitForSelector('[data-export-modal]')
    const [pdfDl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'PDF', exact: true }).click()])
    const pdf = fs.readFileSync(await pdfDl.path())
    check('PDF is a real PDF', pdf.slice(0, 5).toString() === '%PDF-', pdf.slice(0, 8).toString())
    check('PDF names the club in its title', pdf.toString('latin1').includes('Gisborne CC'))

    // Single squad from its column
    await colOf('1s').locator('[data-export-squad]').click()
    await page.waitForSelector('[data-export-modal]')
    const checked = await page.locator('[data-export-modal] input[type=checkbox]:checked').count()
    check('the per-squad export opens with just that squad ticked', checked === 1, String(checked))
    await page.keyboard.press('Escape')
    await page.locator('[data-export-modal] button[aria-label="Close"]').click()


  }

  /* ───────── 390px ───────── */
  await page.setViewportSize({ width: 390, height: 800 })
  await page.waitForTimeout(400)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
  check('Squads has no sideways overflow at 390px', overflow <= 1, String(overflow))
  await page.goto(`${BASE}/admin/betterselect/availability`, { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('Search players…').waitFor({ timeout: 20000 })
  const overflow2 = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check('Availability has no sideways overflow at 390px', overflow2 <= 1, String(overflow2))
  await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/availability-390.png` : '/tmp/availability-390.png' })

  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
