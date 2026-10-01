// Drives the real admin screens for "Hide juniors" in Chromium with the API
// stubbed at the network layer.
//
//   npx vite build --outDir /tmp/dist_hj && npx vite preview --outDir /tmp/dist_hj --port 5202 &
//   node frontend/verification/verify_hide_juniors_browser.mjs [baseUrl]
//
// Two screens carry the feature:
//   * Club Settings has the switch, and a preview of what it would do right now
//     (which competitions read as junior, and who would disappear), so a club
//     can check before saving.
//   * Grades & Competitions has a Cricket type control on each competition:
//     Auto (the name decides), Junior or Senior.
//
// What is asserted is what goes ON THE WIRE, not what the screen says about
// itself: the PATCH body of the switch, and the tag PATCH per competition.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5202'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const COMPETITIONS = [
  { id: 'c-sen', name: 'Northern Districts Cricket Association', association_name: 'Northern Districts',
    grade_count: 6, season_count: 20, is_seeded: true, display_order: 0,
    is_junior_tag: null, is_junior: false, suggested_junior: false },
  { id: 'c-jun', name: 'Kalamunda Junior Cricket Association', association_name: 'Kalamunda Junior',
    grade_count: 9, season_count: 12, is_seeded: true, display_order: 1,
    is_junior_tag: null, is_junior: true, suggested_junior: true },
  { id: 'c-soc', name: 'Junior Social League', association_name: 'Social',
    grade_count: 1, season_count: 2, is_seeded: false, display_order: 2,
    is_junior_tag: false, is_junior: false, suggested_junior: true },
]
const PREVIEW = {
  enabled: false,
  junior_competitions: [COMPETITIONS[1]],
  junior_grade_count: 9,
  hidden_player_count: 3,
  hidden_players: [
    { id: 'p1', name: 'Jess Junior' }, { id: 'p2', name: 'Jo Sharedjunior' }, { id: 'p3', name: 'Kai Kid' },
  ],
}
const SETTINGS = {
  id: 'org-1', name: 'Kalamunda Cricket Club', slug: 'kalamunda', subscription_status: 'active',
  hide_juniors: false, show_competition_filters: false, stats_grade_categories: [],
  effective_stats_grade_categories: ['senior'], stats_auto_show_played_grades: true,
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(path, { width = 1280, preview = PREVIEW } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  await ctx.addInitScript(() => { localStorage.setItem('token', 'stub') })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    if (/net::ERR_/.test(m.text())) return   // fonts / analytics are unreachable here
    errors.push(m.text())
  })
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    let body = null
    try { body = req.postData() } catch { /* GET */ }
    calls.push({ path: p, method: req.method(), body })
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

    if (p.startsWith('/auth/me')) {
      return json({ id: 'u1', username: 'admin', role: 'club_admin', club_id: 'org-1', club_slug: 'kalamunda',
        capabilities: ['*'], entitlements: { modules: ['stats'], status: 'active' } })
    }
    if (p === '/club-admin/settings') return json(SETTINGS)
    if (p === '/admin/juniors/preview') return json(preview)
    if (p === '/admin/competitions' && req.method() === 'GET') {
      return json({ competitions: COMPETITIONS, grades: [], associations: [] })
    }
    if (/^\/admin\/competitions\/[^/]+\/junior$/.test(p)) return json({ status: 'tagged' })
    if (p === '/admin/competitions/grouping') return json({ needs_grouping: false, running: false })
    return json([])
  })
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1500)
  return { page, ctx, errors, calls }
}

const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)

// ------------------------------------------------------------ Club Settings
{
  console.log('\nClub Settings: the switch and its preview')
  const { page, ctx, errors, calls } = await open('/admin/settings')
  const toggle = page.locator('[data-testid="hide-juniors-toggle"]')
  ck('the switch is drawn', await toggle.count() === 1)
  // Every action below is guarded, so a CONTROL RUN against the commit before
  // this change reports each missing piece as a failed check instead of
  // hanging on a locator that is not there.
  ck('it starts OFF for a club that has never set it', (await toggle.count()) > 0 && !(await toggle.isChecked()))
  const box = page.locator('[data-testid="hide-juniors-preview"]')
  const text = (await box.count()) ? await box.innerText() : ''
  ck('the preview names the junior competition', /Kalamunda Junior Cricket Association/.test(text), text)
  ck('it says how many grades that takes with it', /9 grades/.test(text), text)
  ck('it says how many players would be hidden (not "are": the switch is off)', /3 players would be hidden/.test(text), text)
  ck('it does not name the senior competition as junior', !/Northern Districts/.test(text), text)
  ck('the tag control is not drawn here', (await page.locator('[data-testid="competition-junior-tag"]').count()) === 0)

  ck('nobody is listed until asked', (await page.locator('text=Jess Junior').count()) === 0)
  if (await page.locator('button', { hasText: 'Show who' }).count()) {
    await page.locator('button', { hasText: 'Show who' }).click()
  }
  ck('"Show who" lists the hidden players', (await page.locator('text=Jess Junior').count()) === 1
    && (await page.locator('text=Kai Kid').count()) === 1)

  if (await toggle.count()) await toggle.check()
  await page.locator('button[type="submit"]', { hasText: /save/i }).first().click()
  await page.waitForTimeout(600)
  const patch = calls.find(c => c.path === '/club-admin/settings' && c.method === 'PATCH')
  const sent = patch ? JSON.parse(patch.body) : {}
  ck('saving sends hide_juniors: true on the wire', sent.hide_juniors === true, patch ? patch.body : 'no PATCH')

  await page.screenshot({ path: '/tmp/hj_settings_desktop.png', fullPage: false })
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  console.log('\nClub Settings: a club whose competitions are all senior')
  const none = { enabled: false, junior_competitions: [], junior_grade_count: 0, hidden_player_count: 0, hidden_players: [] }
  const { page, ctx } = await open('/admin/settings', { preview: none })
  const noneBox = page.locator('[data-testid="hide-juniors-preview"]')
  const text = (await noneBox.count()) ? await noneBox.innerText() : ''
  ck('it says turning the switch on would hide nothing (a control that is correctly inert explains itself)',
    /would hide nothing/.test(text) && /No players would be hidden/.test(text), text)
  ck('no "Show who" button when there is nobody to list', (await page.locator('button', { hasText: 'Show who' }).count()) === 0)
  await ctx.close()
}

{
  console.log('\nClub Settings at 390px')
  const { page, ctx } = await open('/admin/settings', { width: 390 })
  ck('no horizontal overflow', (await overflow(page)) <= 0, String(await overflow(page)))
  await page.screenshot({ path: '/tmp/hj_settings_mobile.png' })
  await ctx.close()
}

// -------------------------------------------------- Grades & Competitions
{
  console.log('\nGrades & Competitions: Cricket type on each competition')
  const { page, ctx, calls, errors } = await open('/admin/grades')
  const tags = page.locator('[data-testid="competition-junior-tag"]')
  ck('one Cricket type control per competition', await tags.count() === 3, String(await tags.count()))
  const vals = await tags.evaluateAll(els => els.map(e => e.value))
  ck('untagged reads as Auto, an admin tag shows as set', JSON.stringify(vals) === JSON.stringify(['', '', 'senior']), JSON.stringify(vals))
  const labels = (await tags.count()) > 1 ? await tags.nth(1).locator('option').allTextContents() : []
  ck('Auto says what the name reads as', labels[0] === 'Auto (reads as junior)', JSON.stringify(labels))
  const labels0 = (await tags.count()) > 0 ? await tags.nth(0).locator('option').allTextContents() : []
  ck('...and "reads as senior" for a senior name', labels0[0] === 'Auto (reads as senior)', JSON.stringify(labels0))

  const haveTags = (await tags.count()) >= 3
  if (haveTags) await tags.nth(1).selectOption('senior')
  await page.waitForTimeout(400)
  let hit = calls.filter(c => /\/junior$/.test(c.path))
  ck('choosing Senior PATCHes is_junior: false to that competition',
    hit.length === 1 && hit[0].path === '/admin/competitions/c-jun/junior' && hit[0].method === 'PATCH'
    && JSON.parse(hit[0].body).is_junior === false, JSON.stringify(hit))
  if (haveTags) await tags.nth(1).selectOption('junior')
  await page.waitForTimeout(400)
  hit = calls.filter(c => /\/junior$/.test(c.path))
  ck('choosing Junior sends true', hit.length === 2 && JSON.parse(hit[1].body).is_junior === true, JSON.stringify(hit))
  if (haveTags) await tags.nth(2).selectOption('')
  await page.waitForTimeout(400)
  hit = calls.filter(c => /\/junior$/.test(c.path))
  ck('choosing Auto sends null, which the server reads as "back to the name"',
    hit.length === 3 && hit[2].path === '/admin/competitions/c-soc/junior' && JSON.parse(hit[2].body).is_junior === null,
    JSON.stringify(hit[2]))
  ck('the screen reloads the competitions after each change',
    calls.filter(c => c.path === '/admin/competitions' && c.method === 'GET').length >= 4)
  await page.screenshot({ path: '/tmp/hj_grades_desktop.png' })
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  console.log('\nGrades & Competitions at 390px')
  const { page, ctx } = await open('/admin/grades', { width: 390 })
  ck('no horizontal overflow', (await overflow(page)) <= 0, String(await overflow(page)))
  await page.screenshot({ path: '/tmp/hj_grades_mobile.png' })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
