// Drives the real admin Players screen in Chromium with the API stubbed at the
// network layer, for "a player who asked to be removed" (migration 316).
//
//   npx vite build --outDir /tmp/dist_pp && npx vite preview --outDir /tmp/dist_pp --port 5203 &
//   node frontend/verification/verify_player_privacy_browser.mjs [baseUrl]
//
// Two players are listed. Toby asked to be removed (privacy_hidden_at set,
// is_public false). Pat is hidden by the club's own switch (is_public false, no
// marker). The point of the pair: Toby's profile shows a note and NO switch, Pat's
// still shows the switch, so the screen cannot pass by drawing nothing.
//
// What is asserted on the wire: saving Toby's profile sends is_public: false
// (never true) and never sends the read-only marker back.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5203'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const TOBY = 'aaaaaaaa-0000-4000-8000-000000000001'
const PAT = 'aaaaaaaa-0000-4000-8000-000000000002'

const row = (id, name, extra = {}) => ({
  id, name, display_name: name, status: 'active', is_player: true, is_public: true,
  skill_positions: [], squad_team_ids: [], player_role: null, ...extra,
})
const ROSTER = [
  row(TOBY, 'Marlowe, Toby', { is_public: false }),
  row(PAT, 'Plain, Pat', { is_public: false }),
]
const PROFILES = {
  [TOBY]: row(TOBY, 'Marlowe, Toby', { is_public: false, privacy_hidden_at: '2026-10-01T02:00:00+00:00' }),
  [PAT]: row(PAT, 'Plain, Pat', { is_public: false, privacy_hidden_at: null }),
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(width) {
  const ctx = await browser.newContext({ viewport: { width, height: 1500 } })
  await ctx.addInitScript(() => { localStorage.setItem('token', 'stub') })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    if (/net::ERR_/.test(m.text())) return
    errors.push(m.text())
  })
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    let body = null
    try { body = req.postData() } catch { /* GET */ }
    calls.push({ path: p, method: req.method(), body })
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (p.startsWith('/auth/me')) {
      return json({ id: 'u1', username: 'admin', role: 'club_admin', club_id: 'org-1', club_slug: 'applecross',
        capabilities: ['*'], entitlements: { modules: ['stats'], status: 'active' } })
    }
    if (p === '/club-admin/players') return json(ROSTER)
    if (p === '/club-admin/settings') return json({ id: 'org-1', name: 'Applecross', slug: 'applecross', player_name_format: 'last_first' })
    const m = p.match(/^\/players\/([^/]+)\/profile$/)
    if (m && req.method() === 'GET') return json(PROFILES[m[1]] || {})
    if (m && req.method() === 'PATCH') return json({ ...(PROFILES[m[1]] || {}), ...(JSON.parse(body || '{}')) })
    return json([])
  })
  await page.goto(`${BASE}/admin/players`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1500)
  return { page, ctx, errors, calls }
}

const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)

async function openProfile(page, name) {
  const rowEl = page.locator('.pl-row', { hasText: name }).first()
  if (await rowEl.count()) await rowEl.click()
  await page.waitForTimeout(900)
}

for (const width of [1280, 390]) {
  console.log(`\nAdmin Players at ${width}px`)
  const { page, ctx, errors, calls } = await open(width)

  // Toby: asked to be removed.
  await openProfile(page, 'Marlowe')
  let body = await page.locator('body').innerText()
  ck('Toby: the note says it was at the player\'s request', /Removed at the player's request/.test(body))
  ck('Toby: there is NO Hidden switch to flip',
    (await page.getByText('Hidden — keep off the public website').count()) === 0)
  ck('Toby: the note says what stays (club totals, admin screens)', /club's totals/.test(body))
  ck(`Toby: no horizontal overflow at ${width}px`, (await overflow(page)) <= 1, String(await overflow(page)))
  await page.screenshot({ path: `/tmp/claude-0/pp_trent_${width}.png` })

  // Save his profile: the PATCH must keep him hidden and never carry the marker.
  // Dirty the form with the shirt number so "Save changes" enables, then save.
  const shirtBox = page.locator('div', { has: page.locator('span', { hasText: /^Shirt number$/ }) }).locator('input').first()
  if (await shirtBox.count()) await shirtBox.fill('7')
  const save = page.locator('button', { hasText: 'Save changes' }).first()
  if (await save.count()) {
    await save.click().catch(() => {})
    await page.waitForTimeout(700)
  }
  const patch = calls.find(c => c.method === 'PATCH' && c.path === `/players/${TOBY}/profile`)
  if (patch) {
    const sent = JSON.parse(patch.body)
    ck('Toby: saving sends is_public: false on the wire', sent.is_public === false, patch.body)
    ck('Toby: the read-only marker is never sent back', !('privacy_hidden_at' in sent), patch.body)
  } else {
    ck('Toby: saving his profile sent a PATCH at all', false, 'no PATCH captured')
  }

  // Pat: hidden by the club's own switch only. The control: the switch IS drawn.
  await page.goto(`${BASE}/admin/players`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1200)
  await openProfile(page, 'Plain')
  body = await page.locator('body').innerText()
  ck('Pat: the Hidden switch is still drawn for the club to flip',
    (await page.getByText('Hidden — keep off the public website').count()) === 1)
  ck('Pat: no "at the player\'s request" note', !/Removed at the player's request/.test(body))
  await page.screenshot({ path: `/tmp/claude-0/pp_pat_${width}.png` })

  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
