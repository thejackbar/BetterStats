// Drives the real player share page (/players/:id/share) in Chromium with the API stubbed at the network layer.
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_player_share_card_browser.mjs [baseUrl]
//
// Checks: the front reads as a trading card (name split first / SURNAME, sponsor, style chips, best club rank);
// what a club hides stays off it (no chips when the payload carries none, no sponsor when it lists none); the
// card turns over to the figures and back, by tap, key and button; the season picker still re-requests the
// stats and the rankings for that season; Save image makes a real 2x PNG of whichever side shows; the club
// slug is remembered for the sponsor list; 390px fits with no sideways scroll; no page errors.
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome'
const SHOTS = process.env.SHOTS_DIR || ''

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  - ${extra}` : ''}`) }
}

const svg = (body, w = 600, h = 800) => `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${body}</svg>`
const PHOTO = svg('<rect width="600" height="800" fill="#2c4a3e"/><circle cx="300" cy="250" r="95" fill="#d9a77c"/><path d="M110 800c10-190 90-300 190-300s180 110 190 300z" fill="#0f5a43"/>')
const LOGO = svg('<rect width="200" height="200" rx="40" fill="#f0b429"/><text x="100" y="125" font-size="80" text-anchor="middle" fill="#0a0d14" font-family="Arial" font-weight="700">AC</text>', 200, 200)
const SPONSOR = svg('<rect width="300" height="80" fill="#1a1a1a"/><rect x="20" y="25" width="30" height="30" fill="#e11"/><text x="62" y="52" font-size="30" fill="#fff" font-family="Arial">KITCHENHAUS</text>', 300, 80)

const PLAYER = {
  id: 'p1', name: 'Pullinger, George', display_name: 'Pullinger, George', organisation_id: 'org1', claimed: false, playhq_id: null,
  photo_url: '/api/players/p1/photo', is_overseas: false, batting_hand: 'RIGHT', bowling_action: 'RIGHT_ARM', bowling_type: 'MEDIUM',
}
const STATS = (player) => ({
  player,
  career_batting: { games: 42, innings: 40, total_runs: 1234, high_score: '101*', average: 34.5, hundreds: 1, fifties: 6 },
  career_bowling: { total_wickets: 20, average: 25.1, economy: 4.8, best_bowling_figures: '4/21', five_fors: 0 },
  career_fielding: { total_catches_non_wk: 11, total_catches_wk: 0, total_run_outs: 2, total_stumpings: 0 },
})

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1000, player = PLAYER, photo = true, hero = false, sponsors = true, ranks = { runs_rank: 1, wickets_rank: 7, catches_rank: 12 } } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 }, acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = [], reqs = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    reqs.push(path + url.search)
    if (path === '/players/p1/photo') return photo ? route.fulfill({ status: 200, contentType: 'image/svg+xml', body: PHOTO }) : route.fulfill({ status: 404, body: '' })
    if (path === '/players/p1/hero') return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: PHOTO })
    if (path === '/logo.svg') return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: LOGO })
    if (path === '/sponsor.svg') return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: SPONSOR })
    if (path === '/players/p1/stats') return json(route, STATS(hero ? { ...player, hero_photo_url: '/api/players/p1/hero' } : player))
    if (path === '/players/p1/rankings') return json(route, ranks)
    if (path === '/organisations/org1') return json(route, { id: 'org1', name: 'Applecross CC', slug: 'apx', logo_url: '/api/logo.svg', accent_color: '#f0b429', theme_config: {} })
    if (path === '/organisations/org1/seasons') return json(route, [{ id: 's24', name: '2024/25', start_year: 2024 }, { id: 's23', name: '2023/24', start_year: 2023 }])
    if (path === '/clubs/apx/sponsors') return json(route, { tier_labels: {}, sponsors: sponsors ? [{ id: 'sp1', name: 'KitchenHaus', tier: 'major', logo_url: '/api/sponsor.svg', placements: ['dashboard'] }] : [] })
    return json(route, {})
  })
  await page.goto(`${BASE}/players/p1/share`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('[role="button"][aria-pressed]', { timeout: 15000 })
  await page.waitForTimeout(600)
  return { page, ctx, errors, reqs }
}

const flipState = (page) => page.locator('[role="button"][aria-pressed]').getAttribute('aria-pressed')
const turned = (page) => page.locator('[role="button"][aria-pressed]').evaluate(e => getComputedStyle(e).transform)
const visibleText = (page) => page.locator('[role="button"][aria-pressed] > div[aria-hidden="false"]').innerText()

// ── 1. The front is a trading card ────────────────────────────────────────────
{
  const p = await open()
  const front = await visibleText(p.page)
  ck('it opens on the front, not turned', (await flipState(p.page)) === 'false' && (await turned(p.page)) === 'none', await turned(p.page))
  ck('"Last, First" is shown as the first name over the SURNAME, with no comma', /GEORGE/i.test(front) && /PULLINGER/.test(front) && !/,/.test(front.replace(/1,234/g, '')), front)
  ck('the style chips read RH Batter and RH Medium', /RH Batter/.test(front) && /RH Medium/.test(front), front)
  ck('the big number is the best club ranking, labelled', /#1/.test(front) && /CLUB RUNS/.test(front), front)
  ck('the sponsor is named and drawn', /Sponsored by/.test(front) && (await p.page.locator('[role="button"][aria-pressed] img[src="/api/sponsor.svg"]').count()) >= 1)
  ck('the player\'s photo is the card background', (await p.page.locator('[role="button"][aria-pressed] img[src="/api/players/p1/photo"]').count()) >= 1)
  ck('the front carries a band of headline figures, not the full sheet', /MATCHES/.test(front) && /RUNS/.test(front) && /1,234/.test(front) && /WICKETS/.test(front) && !/BATTING/.test(front) && !/HIGH SCORE/.test(front), front)
  const img = await p.page.locator('[role="button"][aria-pressed] > div[aria-hidden="false"] img[src="/api/players/p1/photo"]').boundingBox()
  const cardBox = await p.page.locator('[role="button"][aria-pressed]').boundingBox()
  ck('a headshot is a smaller picture, not the whole card', img && img.width < cardBox.width * 0.6 && img.height < cardBox.height * 0.45, JSON.stringify({ img, w: cardBox.width }))
  ck('and it is centred', img && Math.abs((img.x + img.width / 2) - (cardBox.x + cardBox.width / 2)) < 6, JSON.stringify({ img, cardBox }))
  ck('the club slug went to the sponsor list', p.reqs.includes('/clubs/apx/sponsors'), p.reqs.join(' '))
  if (SHOTS) await p.page.screenshot({ path: `${SHOTS}/share_front_1000.png` })
  ck('no page errors', p.errors.length === 0, p.errors.join(' | '))
  await p.ctx.close()
}

// ── 1b. A hero photo fills the card ───────────────────────────────────────────
{
  const p = await open({ hero: true })
  const cardBox = await p.page.locator('[role="button"][aria-pressed]').boundingBox()
  const img = await p.page.locator('[role="button"][aria-pressed] > div[aria-hidden="false"] img[src="/api/players/p1/hero"]').boundingBox()
  ck('a hero photo fills the width of the card', img && img.width > cardBox.width * 0.9, JSON.stringify({ img, w: cardBox.width }))
  ck('and the headshot is not drawn as well', (await p.page.locator('[role="button"][aria-pressed] > div[aria-hidden="false"] img[src="/api/players/p1/photo"]').count()) === 0)
  if (SHOTS) await p.page.screenshot({ path: `${SHOTS}/share_front_hero.png` })
  ck('no page errors', p.errors.length === 0, p.errors.join(' | '))
  await p.ctx.close()
}

// ── 2. What a club hides stays off it ─────────────────────────────────────────
{
  const hidden = { ...PLAYER }
  delete hidden.batting_hand; delete hidden.bowling_action; delete hidden.bowling_type
  const p = await open({ player: hidden, sponsors: false, photo: false, ranks: { runs_rank: 150, wickets_rank: null, catches_rank: null } })
  const front = await visibleText(p.page)
  ck('no style chips when the club does not show them', !/Batter/.test(front) && !/Medium/.test(front), front)
  ck('no sponsor line when the club lists none', !/Sponsored by/.test(front), front)
  ck('no big number for a player outside the top 99', !/#\d/.test(front) && !/CLUB RUNS/.test(front), front)
  ck('with no photo the club logo stands in and the name still shows', (await p.page.locator('[role="button"][aria-pressed] img[src="/api/logo.svg"]').count()) >= 1 && /PULLINGER/.test(front))
  if (SHOTS) await p.page.screenshot({ path: `${SHOTS}/share_front_bare.png` })
  await p.ctx.close()
}

// ── 3. Turning it over ────────────────────────────────────────────────────────
{
  const p = await open()
  await p.page.locator('[role="button"][aria-pressed]').click()
  await p.page.waitForTimeout(900)
  const back = await visibleText(p.page)
  ck('a tap turns it over', (await flipState(p.page)) === 'true' && /matrix3d\(-1|matrix\(-1/.test(await turned(p.page)), await turned(p.page))
  ck('the back is the details sheet with every figure', /PLAYER DETAILS/.test(back) && /BATTING/.test(back) && /1,?234/.test(back) && /BOWLING/.test(back) && /FIELDING/.test(back) && /101\*/.test(back) && /HIGH SCORE/.test(back), back)
  ck('its name box reads first name then SURNAME and the club is not cut off', /GEORGE\s+PULLINGER/i.test(back) && /APPLECROSS CC/.test(back) && !/…|\.\.\./.test(back), back)
  ck('and the rankings as badges', /1st runs/.test(back) && /7th wickets/.test(back), back)
  if (SHOTS) await p.page.screenshot({ path: `${SHOTS}/share_back_1000.png` })
  await p.page.getByRole('button', { name: 'SHOW CARD' }).click(); await p.page.waitForTimeout(900)
  ck('the button turns it back', (await flipState(p.page)) === 'false')
  await p.page.locator('[role="button"][aria-pressed]').focus()
  await p.page.keyboard.press('Enter'); await p.page.waitForTimeout(900)
  ck('Enter on the focused card turns it too', (await flipState(p.page)) === 'true')
  await p.page.keyboard.press('Space'); await p.page.waitForTimeout(900)
  ck('and Space turns it back', (await flipState(p.page)) === 'false')

  // The season picker still drives both requests.
  p.reqs.length = 0
  await p.page.locator('select').selectOption('s24')
  await p.page.waitForTimeout(800)
  ck('picking a season asks for that season\'s stats and rankings', p.reqs.some(r => r.startsWith('/players/p1/stats') && r.includes('season_id=s24')) && p.reqs.some(r => r.startsWith('/players/p1/rankings') && r.includes('season_id=s24')), p.reqs.join(' '))
  ck('and the card says which season', /2024\/25/.test(await p.page.locator('[role="button"][aria-pressed]').innerText()) || /2024/.test(await p.page.locator('body').innerText()))

  // Save image: whichever side is showing, as a real PNG at 2x.
  const grab = async () => {
    const [dl] = await Promise.all([p.page.waitForEvent('download', { timeout: 20000 }), p.page.getByRole('button', { name: 'SAVE IMAGE' }).click()])
    const buf = readFileSync(await dl.path())
    return { name: dl.suggestedFilename(), png: buf.slice(0, 8).toString('hex') === '89504e470d0a1a0a', w: buf.readUInt32BE(16), h: buf.readUInt32BE(20), buf }
  }
  const a = await grab()
  ck('Save image on the front gives a PNG named for the player', a.png && a.name === 'george-pullinger-card.png', a.name)
  ck('at 2x the design size (720 x 984)', a.w === 720 && a.h === 984, `${a.w}x${a.h}`)
  if (SHOTS) writeFileSync(`${SHOTS}/share_export_front.png`, a.buf)
  await p.page.getByRole('button', { name: 'SHOW STATS' }).click(); await p.page.waitForTimeout(900)
  const b = await grab()
  ck('Save image on the back is the stats side', b.png && b.name === 'george-pullinger-stats.png', b.name)
  if (SHOTS) writeFileSync(`${SHOTS}/share_export_back.png`, b.buf)
  ck('the two saved images differ', !a.buf.equals(b.buf))
  ck('no page errors turning, picking or saving', p.errors.length === 0, p.errors.join(' | '))
  await p.ctx.close()
}

// ── 4. A phone ────────────────────────────────────────────────────────────────
{
  const p = await open({ width: 390 })
  const box = await p.page.locator('[role="button"][aria-pressed]').boundingBox()
  ck('390px: the card is scaled to fit inside the gutters', box.width <= 358.5 && box.width > 300, JSON.stringify(box))
  const over = await p.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no sideways scroll', over <= 1, String(over))
  if (SHOTS) await p.page.screenshot({ path: `${SHOTS}/share_front_390.png`, fullPage: true })
  await p.page.locator('[role="button"][aria-pressed]').click(); await p.page.waitForTimeout(900)
  if (SHOTS) await p.page.screenshot({ path: `${SHOTS}/share_back_390.png`, fullPage: true })
  ck('390px: still no sideways scroll turned over', (await p.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 1)
  ck('no page errors', p.errors.length === 0, p.errors.join(' | '))
  await p.ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
