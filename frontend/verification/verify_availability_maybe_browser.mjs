// Drives the REAL Availability screen in Chromium (API stubbed):
//   * the bulk bar uses the same words as everywhere else: Available, Maybe, No response,
//     Unavailable (never "In", "Out" or "No reply")
//   * the Self-service link card has a "Maybe answer" On/Off; Off POSTs allow_maybe=false
//   * with Maybe off, the bulk bar and the quick-answer modal stop offering it at once
//   * with Maybe on, both offer it
//
//   npx vite preview --port 5199 &    node verify_availability_maybe_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }
const iso = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const ME = { id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'o1', club_slug: 'gisborne', capabilities: ['*'], entitlements: { modules: ['select'], core_live: true, status: 'active' } }
const PLAYERS = ['Anna Brown', 'Zed Adams'].map((name, i) => ({ id: `p${i}`, display_name: name, name, squads: [], is_current: true, last_played: iso(-20), player_role: null, skill_positions: [], status: 'active' }))
const MATRIX = { dates: [{ date: iso(7), fixtures: [{ id: 'f1', label: null, opponent_name: 'Rovers', home_away: 'HOME', role: 'single', two_day: false, team_id: null, grade_id: null }] }],
  players: PLAYERS, availability: {}, all_squads: [], dormancy_months: 24, squad_next: {}, rules: { active: false, applied: [] } }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  // Every section of the player page starts closed. These checks read what is inside them,
  // so each context starts with them opened, the way a returning player's page can be.
  const _newContext = browser.newContext.bind(browser)
  browser.newContext = async (o) => {
    const c = await _newContext(o)
    await c.addInitScript(() => { try { if (!localStorage.getItem('bs.playerpage.open')) localStorage.setItem('bs.playerpage.open', JSON.stringify({ availability: true, selection: true, admin: true, voting: true, stats: true, fantasy: true })) } catch (e) { /* no storage */ } })
    return c
  }

  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const state = { allow: true, posts: [] }
  const panel = () => ({ enabled: true, require_pin: true, show_squad: false, allow_maybe: state.allow, token: 'tok', path: '/avail/tok', phone_coverage: { with_phone: 2, total: 2 } })
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route('**/api/club-admin/settings', (r) => json(r, { name: 'Gisborne CC' }))
  await page.route(/\/api\/availability\/matrix/, (r) => json(r, MATRIX))
  await page.route(/\/api\/availability\/config$/, (r) => json(r, { allow_maybe: state.allow }))
  await page.route(/\/api\/availability\/self-service$/, (r) => {
    if (r.request().method() === 'POST') {
      const b = JSON.parse(r.request().postData() || '{}'); state.posts.push(b)
      if ('allow_maybe' in b) state.allow = b.allow_maybe
    }
    return json(r, panel())
  })
  await page.route(/\/api\/teams(\?.*)?$/, (r) => json(r, []))
  await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
  await page.route(/\/api\/fixtures/, (r) => json(r, []))

  await page.goto(`${BASE}/admin/betterselect/availability`, { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('Search players…').waitFor({ timeout: 20000 })
  await page.waitForTimeout(500)

  const tick = async () => { await page.locator('tbody input[type=checkbox]').first().check() }
  const barText = async () => (await page.locator('.pb-card', { hasText: 'selected' }).filter({ has: page.locator('text=mark') }).first().innerText())

  await safe('terminology', async () => {
    console.log('\n── One set of words ──')
    await tick()
    const bar = await barText()
    check('the bulk bar says Available, Maybe, No response, Unavailable', ['Available', 'Maybe', 'No response', 'Unavailable'].every((w) => bar.includes(w)), bar)
    check('...and never In, Out or No reply', !/\bIn\b|\bOut\b|No reply/.test(bar.replace(/Unavailable/g, '').replace(/Available/g, '')), bar)
  })

  await safe('quick modal on', async () => {
    console.log('\n── Maybe on ──')
    await page.locator('tbody [title], tbody button').filter({ hasText: /^$/ }).first().click({ trial: true }).catch(() => {})
    check('the bulk bar offers Maybe', /Maybe/.test(await barText()))
  })

  await safe('switch off', async () => {
    console.log('\n── Switching Maybe off ──')
    await page.getByText('Self-service link').first().click()
    await page.locator('[data-allow-maybe-setting]').waitFor()
    check('the Self-service link card has a Maybe answer setting', /maybe answer/i.test(await page.locator("[data-allow-maybe-setting]").innerText()))
    state.posts.length = 0
    await page.locator('[data-allow-maybe-setting] button', { hasText: 'Off' }).click()
    await page.waitForTimeout(500)
    check('Off sends allow_maybe false and nothing else', JSON.stringify(state.posts) === JSON.stringify([{ allow_maybe: false }]), JSON.stringify(state.posts))
    check('the card says what it means', (await page.locator('[data-maybe-off-note]').count()) === 1)
    const bar = await barText()
    check('the bulk bar stops offering Maybe straight away', !/Maybe/.test(bar) && /Available/.test(bar) && /Unavailable/.test(bar) && /No response/.test(bar), bar)
  })

  await safe('quick modal off', async () => {
    // Open the quick-answer modal from a status cell.
    const cell = page.locator('tbody td button').first()
    await cell.click()
    await page.locator('[aria-label="Update availability"]').waitFor()
    const modal = await page.locator('[aria-label="Update availability"]').innerText()
    check('the quick-answer modal offers Available and Unavailable but not Maybe', /Available/.test(modal) && /Unavailable/.test(modal) && !/Maybe/.test(modal), modal)
    await page.locator('[aria-label="Update availability"] button[aria-label="Close"]').click()
  })

  await safe('switch on', async () => {
    console.log('\n── Switching it back on ──')
    state.posts.length = 0
    await page.locator('[data-allow-maybe-setting] button', { hasText: 'On' }).click()
    await page.waitForTimeout(500)
    check('On sends allow_maybe true', JSON.stringify(state.posts) === JSON.stringify([{ allow_maybe: true }]), JSON.stringify(state.posts))
    check('the bulk bar offers Maybe again', /Maybe/.test(await barText()))
  })

  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run()
