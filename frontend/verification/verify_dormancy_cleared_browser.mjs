// Drives the real BetterSelect Availability screen and Squads board in Chromium
// with the API stubbed at the network layer (the stub keeps state, so a PUT
// changes what the next read returns). The ask (Oct 2026): a dormant player
// should be markable as "no longer dormant" so they show up in availability and
// selection in the weeks before their first game back.
//
//   APP_URL=http://localhost:4173 node verify_dormancy_cleared_browser.mjs
//   (serve a production build; never rebuild dist under a running server)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}
const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const iso = (daysAgo) => plusDays(-daysAgo)
const W1 = plusDays(3)
const TODAY = plusDays(0)
const CUTOFF_DAYS = 730

// Server-side state the stub mutates.
const mk = () => ({ cleared: {} })
const P = (id, name, lastDaysAgo, cleared, extra = {}) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null, hero_photo_url: null,
  gender: null, is_player: true, player_role: null, status: 'active', skill_positions: [], is_public: true,
  squad_team_id: null, squad_team_ids: [], age: null, squads: [],
  last_played: lastDaysAgo == null ? null : iso(lastDaysAgo), dormancy_cleared_on: cleared || null, ...extra,
})
const BASE_PLAYERS = [
  ['ann', 'Current, Ann', 10],
  ['bob', 'Dormant, Bob', 900],      // two and a half years ago
  ['cal', 'Returning, Cal', 900],    // marked back already (see CLEARED below)
]
const CLEARED_AT_START = { cal: TODAY }

const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1',
  club_slug: 'verify-cc', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
async function stub(page, state, puts) {
  const players = () => BASE_PLAYERS.map(([id, name, ago]) => {
    const cleared = state.cleared[id] || null
    const last = iso(ago)
    const eff = cleared && cleared > last ? cleared : last
    const dormant = eff < iso(CUTOFF_DAYS)
    return {
      ...P(id, name, ago, cleared),
      is_dormant: dormant, is_inactive: false, is_current: !dormant, rule_flags: [], rule_notes: [], rule_state: 'ok',
    }
  })
  await page.route('**/api/**', async (route) => {
    const req = route.request(), url = req.url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json(ME)
    const put = url.match(/\/availability\/players\/([^/]+)\/dormancy/)
    if (put && req.method() === 'PUT') {
      const body = JSON.parse(req.postData() || '{}')
      puts.push({ id: put[1], body })
      state.cleared[put[1]] = body.active ? TODAY : null
      return json({ player_id: put[1], dormancy_cleared_on: body.active ? TODAY : null })
    }
    if (url.includes('/availability/matrix')) return json({
      dates: [{ date: W1, fixtures: [{ id: 'f0', opponent_name: 'Opp', home_away: 'HOME', role: 'single', two_day: false }] }],
      players: players(), all_squads: [], squad_meta: {}, dormancy_months: 24, availability: {}, squad_next: {},
      rules: { active: false, applied: [] },
    })
    if (url.includes('/club-admin/players')) return json(players())
    if (url.includes('/teams/grade-options')) return json({ seasons: [] })
    if (url.match(/\/teams(\?|$)/)) return json([{ id: '11111111-1111-1111-1111-111111111111', name: '1st XI', short_name: '1s', sequence: 1, is_active: true, grade_id: null, grade_name: null }])
    if (url.includes('/selection/selected-players')) return json({ player_ids: [] })
    return json({})
  })
}
const rows = (page) => page.evaluate(() =>
  [...document.querySelectorAll('tbody tr')].map((r) => r.querySelector('td .truncate')?.textContent.trim()).filter(Boolean))
const setRoster = async (page, label) => { await page.locator('button', { hasText: new RegExp('^' + label + '$') }).click(); await page.waitForTimeout(150) }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  // ---- Availability ----------------------------------------------------
  let ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  let page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  let state = { cleared: { ...CLEARED_AT_START } }, puts = []
  await stub(page, state, puts)
  await page.goto(`${BASE}/admin/betterselect/availability`)
  await page.waitForSelector('tbody tr', { timeout: 20000 })
  await page.waitForTimeout(300)

  let r = await rows(page)
  check('Current squad: Ann and Cal (marked back) are listed, Bob (dormant) is not', r.join() === 'Current, Ann,Returning, Cal', r.join())
  check('Cal is tagged "returning"', await page.locator('tbody tr', { hasText: 'Returning, Cal' }).locator('span', { hasText: /^returning$/i }).count() === 1)

  await setRoster(page, 'All')
  r = await rows(page)
  check('All: three players', r.length === 3, r.join())
  const bobRow = () => page.locator('tbody tr', { hasText: 'Dormant, Bob' })
  check('Bob is tagged dormant and offers "Not dormant"', await bobRow().locator('span', { hasText: /^dormant$/i }).count() === 1 && await bobRow().locator('[data-not-dormant]').count() === 1)
  check('Ann (current) and Cal (returning) offer no "Not dormant"',
    await page.locator('tbody tr', { hasText: 'Current, Ann' }).locator('[data-not-dormant]').count() === 0
    && await page.locator('tbody tr', { hasText: 'Returning, Cal' }).locator('[data-not-dormant]').count() === 0)

  await bobRow().locator('[data-not-dormant]').click()
  await page.waitForTimeout(300)
  check('the click sends exactly PUT dormancy {active:true} for Bob', puts.length === 1 && puts[0].id === 'bob' && JSON.stringify(puts[0].body) === '{"active":true}', JSON.stringify(puts))
  check('Bob now reads "returning", no "Not dormant" button',
    await bobRow().locator('span', { hasText: /^returning$/i }).count() === 1 && await bobRow().locator('[data-not-dormant]').count() === 0)
  await setRoster(page, 'Current squad')
  r = await rows(page)
  check('Current squad now lists Bob too (Ann, Bob, Cal)', r.join() === 'Current, Ann,Dormant, Bob,Returning, Cal', r.join())
  check('Bob\'s real last played year is unchanged in his tag title',
    (await page.locator('tbody tr', { hasText: 'Dormant, Bob' }).locator('span', { hasText: /^returning$/i }).getAttribute('title')).includes(iso(900)))

  await page.locator('tbody tr', { hasText: 'Dormant, Bob' }).locator('[data-dormant-again]').click()
  await page.waitForTimeout(300)
  check('undo sends PUT dormancy {active:false}', puts.length === 2 && JSON.stringify(puts[1].body) === '{"active":false}', JSON.stringify(puts))
  r = await rows(page)
  check('Bob drops off Current squad again', r.join() === 'Current, Ann,Returning, Cal', r.join())
  check('Availability: no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()

  // ---- Squads board ----------------------------------------------------
  ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  page = await ctx.newPage()
  page.on('pageerror', (e) => errors.push(String(e)))
  state = { cleared: { ...CLEARED_AT_START } }; puts = []
  await stub(page, state, puts)
  await page.goto(`${BASE}/admin/betterselect/teams`)
  await page.waitForSelector('.pb-card', { timeout: 20000 }); await page.waitForTimeout(500); await page.getByRole('button', { name: 'Expand all' }).click({ timeout: 8000 })
  await page.waitForTimeout(400)
  const cols = () => page.evaluate(() => {
    const out = {}
    for (const card of document.querySelectorAll('.pb-card')) {
      const title = card.querySelector('.font-display'); if (!title) continue
      out[title.textContent.trim()] = [...card.querySelectorAll('[draggable="true"] [data-card-name]')].map((n) => n.textContent.trim())
    }
    return out
  })
  let c = await cols()
  const inCol = (re) => Object.entries(c).filter(([h]) => re.test(h)).flatMap(([, v]) => v)
  check('Squads: Bob (dormant) is in the fill-ins column', inCol(/fill/i).includes('Dormant, Bob'), JSON.stringify(c))
  check('Squads: Cal (marked back) is Unassigned, not in fill-ins', inCol(/^unassigned/i).includes('Returning, Cal') && !inCol(/fill/i).includes('Returning, Cal'), JSON.stringify(c))
  check('Squads: only the dormant card offers "Not dormant"',
    await page.locator('[data-bring-back]').count() === 1)
  await page.locator('[draggable="true"]', { hasText: 'Dormant, Bob' }).hover()
  await page.locator('[data-bring-back]').click()
  await page.waitForTimeout(500)
  check('Squads: the click sends PUT dormancy {active:true} for Bob', puts.length === 1 && puts[0].id === 'bob' && puts[0].body.active === true, JSON.stringify(puts))
  c = await cols()
  check('Squads: Bob moves to Unassigned', inCol(/^unassigned/i).includes('Dormant, Bob') && !inCol(/fill/i).includes('Dormant, Bob'), JSON.stringify(c))
  check('Squads: no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()

  // ---- 390px -------------------------------------------------------------
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  const m = await phone.newPage()
  state = { cleared: { ...CLEARED_AT_START } }; puts = []
  await stub(m, state, puts)
  await m.goto(`${BASE}/admin/betterselect/availability`)
  await m.waitForSelector('tbody tr', { timeout: 20000 })
  await setRoster(m, 'All')
  const over = await m.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: screen.width }))
  check('390px: Availability does not overflow sideways with the new button', over.sw <= over.cw, JSON.stringify(over))
  if (process.env.SHOT_DIR) await m.screenshot({ path: process.env.SHOT_DIR + '/dormancy_390.png' })
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
