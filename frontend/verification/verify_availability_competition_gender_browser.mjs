// Drives the real BetterSelect Availability screen in Chromium with the API stubbed at
// the network layer. The report (Oct 2026): Availability had no gender filter and no easy
// way to leave the Veterans out.
//
// Now: a Gender facet (Men, Women, Not set), a Competition facet built from the
// competitions the club has games in, and a one-tap "Leave out" row. Leave out hides a
// player only when EVERY competition they are in is left out; someone who also plays in
// another competition, or in none the club has grouped, stays.
//
//   APP_URL=http://localhost:4173 node verify_availability_competition_gender_browser.mjs
//   (serve a production build; never rebuild dist under a running server)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOTS = process.env.SHOT_DIR || ''
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}
const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const W1 = plusDays(3)

const P = (id, name, gender, competitions) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null, is_player: true,
  player_role: null, status: 'active', is_current: true, is_dormant: false, is_inactive: false,
  squads: [], last_played: plusDays(-10), age: null, gender, competitions,
})
const COMPS = [{ id: 'c-vet', name: 'Veterans' }, { id: 'c-sat', name: 'Saturday League' }]
const MATRIX = {
  dates: [{ date: W1, fixtures: [{ id: 'f0', opponent_name: 'Opp', home_away: 'HOME', role: 'single', two_day: false }] }],
  players: [
    P('ann', 'Ann', 'Female', ['c-sat']),
    P('ben', 'Ben', 'Male', ['c-sat']),
    P('cal', 'Cal', 'M', ['c-vet']),               // Veterans only
    P('dan', 'Dan', 'male', ['c-sat', 'c-vet']),   // plays both
    P('eve', 'Eve', null, []),                     // no gender, no competition
    P('fay', 'Fay', 'F', ['c-vet']),               // Veterans only
  ],
  all_squads: [], squad_meta: {}, competitions: COMPS,
  dormancy_months: 24, rules: { active: false, applied: [] }, availability: {},
}
const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1',
  club_slug: 'verify-cc', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' },
}
async function stub(page, matrix) {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json(ME)
    if (url.includes('/availability/matrix')) return json(matrix)
    if (url.includes('/selection/selected-players')) return json({ player_ids: [] })
    return json({})
  })
}
const rows = (page) => page.evaluate(() =>
  [...document.querySelectorAll('tbody tr')].map((r) => r.querySelector('td .truncate')?.textContent.trim()).filter(Boolean))
const openPanel = async (page) => {
  const has = await page.evaluate(() => [...document.querySelectorAll('div')].some((d) => /^(squad|role|selected)$/i.test(d.textContent.trim()) && d.className.includes('border-b')))
  if (!has) await page.locator('button', { hasText: 'Filters' }).click()
}
// The labels of one facet group in the open Filters panel (checkboxes or chips), or null.
const group = async (page, title) => {
  await openPanel(page)
  return page.evaluate((t) => {
    const g = [...document.querySelectorAll('div')].find((d) => d.children.length === 2
      && d.children[0].textContent.trim().toLowerCase() === t.toLowerCase() && d.children[0].className.includes('border-b'))
    return g ? [...g.children[1].querySelectorAll('label, button')].map((l) => l.textContent.trim()) : null
  }, title)
}
const pickInGroup = async (page, title, label) => {
  await openPanel(page)
  const g = page.locator('div', { has: page.locator(`> div:first-child:text-is("${title}")`) }).last()
  await g.locator('label, button', { hasText: new RegExp('^' + label + '$') }).first().click()
  await page.waitForTimeout(150)
}
const leaveOut = (page, label) => page.locator('[data-leave-out] button', { hasText: new RegExp('^' + label + '$') })
const clearAll = async (page) => { await page.locator('button', { hasText: 'Clear all' }).click(); await page.waitForTimeout(150) }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const open = async (matrix = MATRIX, viewport = { width: 1440, height: 1000 }) => {
    const ctx = await browser.newContext({ viewport })
    const page = await ctx.newPage()
    page.errors = []
    page.on('pageerror', (e) => page.errors.push(String(e)))
    await stub(page, matrix)
    await page.goto(`${BASE}/admin/betterselect/availability`)
    await page.waitForSelector('tbody tr', { timeout: 20000 })
    await page.waitForTimeout(300)
    return page
  }

  let page = await open()
  let r = await rows(page)
  check('everyone is listed to start with', r.join() === 'Ann,Ben,Cal,Dan,Eve,Fay', r.join())
  check('Gender facet offers Men, Women, Not set', (await group(page, 'Gender') || []).join() === 'Men,Women,Not set', String(await group(page, 'Gender')))
  check('Competition facet lists the current competitions only', (await group(page, 'Competition') || []).join() === 'Veterans,Saturday League', String(await group(page, 'Competition')))
  check('a Leave out facet is in the panel too', (await group(page, 'Leave out') || []).join() === 'Veterans,Saturday League', String(await group(page, 'Leave out')))
  check('the one-tap Leave out row is on screen with a chip per competition',
    (await page.locator('[data-leave-out] button').allTextContents()).join() === 'Veterans,Saturday League')

  // One tap leaves the Veterans out.
  await leaveOut(page, 'Veterans').click(); await page.waitForTimeout(150)
  r = await rows(page)
  check('Leave out Veterans: Cal and Fay (Veterans only) go', !r.includes('Cal') && !r.includes('Fay'), r.join())
  check('Dan (plays both) stays', r.includes('Dan'), r.join())
  check('Eve (no competition known) stays', r.includes('Eve'), r.join())
  check('exactly Ann, Ben, Dan, Eve are left', r.join() === 'Ann,Ben,Dan,Eve', r.join())
  check('the count reads "4 of 6"', await page.locator('text=/^4 of 6$/').count() === 1)
  check('an active chip says what is left out', await page.locator('text=Leave out: Veterans').count() >= 1)
  await leaveOut(page, 'Veterans').click(); await page.waitForTimeout(150)
  r = await rows(page)
  check('tapping the chip again brings them back', r.length === 6, r.join())

  // Competition include.
  await pickInGroup(page, 'Competition', 'Veterans')
  r = await rows(page)
  check('Competition = Veterans: Cal, Dan, Fay', r.join() === 'Cal,Dan,Fay', r.join())
  await clearAll(page)

  // Gender.
  await pickInGroup(page, 'Gender', 'Women')
  r = await rows(page)
  check('Gender = Women: Ann and Fay (Female / F)', r.join() === 'Ann,Fay', r.join())
  await pickInGroup(page, 'Gender', 'Men')
  r = await rows(page)
  check('Gender = Men: Ben, Cal, Dan (Male / M / male)', r.join() === 'Ben,Cal,Dan', r.join())
  await pickInGroup(page, 'Gender', 'Not set')
  r = await rows(page)
  check('Gender = Not set: Eve, so nobody is silently lost', r.join() === 'Eve', r.join())
  await pickInGroup(page, 'Gender', 'Women')
  await leaveOut(page, 'Veterans').click(); await page.waitForTimeout(150)
  r = await rows(page)
  check('Women and leave out Veterans together: Ann only', r.join() === 'Ann', r.join())
  check('no page errors', page.errors.length === 0, page.errors.join(' | '))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/availability-competition-gender-desktop.png`, fullPage: false })
  await clearAll(page)
  r = await rows(page)
  check('Clear all clears gender, competition and leave out', r.length === 6, r.join())
  await page.context().close()

  // Narrow phone: the new row wraps and nothing scrolls sideways.
  page = await open(MATRIX, { width: 390, height: 900 })
  await leaveOut(page, 'Veterans').click(); await page.waitForTimeout(150)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  check('390px: no horizontal page scroll', over <= 0, `overflow ${over}px`)
  check('390px: the Leave out row is still visible', await page.locator('[data-leave-out]').isVisible())
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/availability-competition-gender-390.png`, fullPage: false })
  await page.context().close()

  // One competition: no leave-out row (nothing would be left), the Competition facet stays.
  page = await open({ ...MATRIX, competitions: [COMPS[1]] })
  check('one competition: no Leave out row', (await page.locator('[data-leave-out]').count()) === 0)
  check('one competition: the Competition facet is still offered', (await group(page, 'Competition') || []).join() === 'Saturday League')
  await page.context().close()

  // An older server (no gender, no competitions): nothing new is drawn and nobody is lost.
  const old = { ...MATRIX, competitions: undefined, players: MATRIX.players.map(({ gender, competitions, ...p }) => p) }
  page = await open(old)
  r = await rows(page)
  check('older server: everyone still listed', r.length === 6, r.join())
  check('older server: no Gender group', (await group(page, 'Gender')) === null)
  check('older server: no Competition group', (await group(page, 'Competition')) === null)
  check('older server: no Leave out row', (await page.locator('[data-leave-out]').count()) === 0)
  check('older server: no page errors', page.errors.length === 0, page.errors.join(' | '))
  await page.context().close()

  // A club with nobody's gender recorded: no Gender facet to pick from.
  const noGender = { ...MATRIX, players: MATRIX.players.map((p) => ({ ...p, gender: null })) }
  page = await open(noGender)
  check('nobody has a gender: no Gender group', (await group(page, 'Gender')) === null)
  await page.context().close()

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(2) })
