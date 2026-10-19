// Drives the REAL live nets screen and the public check-in page in Chromium with
// the API stubbed at the network layer (Gisborne round):
//   * the session has its own "Link" with its own address, QR and squads
//   * ticking a squad PATCHes squad_team_ids for that session and nothing else
//   * "Check in players" opens on the session's squads and narrows the list;
//     "Everyone" widens it; a search always reaches the whole club
//   * the public page names the squads its list is limited to
//   * 390px: no sideways overflow with the modal open
//
//   npx vite preview --port 5199 &    node verify_net_session_link_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }

const SENIORS = 's-seniors', COLTS = 's-colts'
const SETTINGS = { duration_seconds: 600, nets: 2, auto_roll: false, sound: false, alerts: [] }
const ROSTER = {
  players: [
    { id: 'p1', name: 'Adams, Zed', skill_positions: [], dormant: false, inactive: false, squad_team_ids: [SENIORS] },
    { id: 'p2', name: 'Brown, Anna', skill_positions: [], dormant: false, inactive: false, squad_team_ids: [SENIORS, COLTS] },
    { id: 'p3', name: 'Cole, Cara', skill_positions: [], dormant: false, inactive: false, squad_team_ids: [COLTS] },
  ],
  squads: [{ id: SENIORS, label: 'Seniors', name: 'Seniors' }, { id: COLTS, label: 'Colts', name: 'Colts' }],
  squad_count: 3,
}
let state, wire
const payload = () => ({
  id: 'sess1', version: state.version, server_time: new Date().toISOString(), session_date: '2026-08-20',
  label: 'Tuesday nets', notes: null, status: 'active', settings: SETTINGS,
  timer: { running: false, ends_at: null, remaining_seconds: 600, duration_seconds: 600, turn_seq: 1 },
  attendees: [], attendee_count: 0, batted_count: 0, sitting_out_count: 0,
  squad_team_ids: state.squads, checkin_path: '/nets-checkin/sess-tok-123', created_at: new Date().toISOString(),
})

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(5000)
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  state = { version: 1, squads: [] }
  wire = { patches: [] }
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'gisborne', organisation_id: 'o1', capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' } }))
  await page.route('**/api/nets/roster', (r) => json(r, ROSTER))
  await page.route('**/api/nets/checkin-link**', (r) => json(r, { enabled: true, require_pin: true, allow_registration: true, token: 'club-tok', path: '/nets-checkin/club-tok', phone_coverage: { with_phone: 3, total: 3 }, pending_registrations: 0 }))
  await page.route('**/api/nets/sessions/sess1/checkin-link', (r) => json(r, { session_id: 'sess1', enabled: true, token: 'sess-tok-123', path: '/nets-checkin/sess-tok-123', squad_team_ids: state.squads }))
  await page.route('**/api/nets/sessions/sess1/live**', (r) => {
    const since = new URL(r.request().url()).searchParams.get('since')
    if (since !== null && Number(since) === state.version) return json(r, { version: state.version, server_time: new Date().toISOString(), unchanged: true })
    return json(r, payload())
  })
  await page.route('**/api/nets/sessions/sess1', (r) => {
    if (r.request().method() === 'PATCH') {
      const b = JSON.parse(r.request().postData() || '{}')
      wire.patches.push(b)
      if ('squad_team_ids' in b) { state.squads = b.squad_team_ids || []; state.version += 1 }
    }
    return json(r, payload())
  })
  await page.route(/\/api\/public\/net-checkin\/sess-tok-123$/, (r) => json(r, {
    club: { name: 'Gisborne CC', short_name: 'GCC', slug: 'gisborne' }, require_pin: true, allow_registration: true,
    sessions: [{ id: 'sess1', session_date: '2026-08-20', label: 'Tuesday nets' }], scoped: true, squads: ['Seniors'],
    players: [{ id: 'p1', display_name: 'Adams, Zed', has_phone: true }], me: null,
  }))

  await page.goto(`${BASE}/admin/betterselect/nets/sess1`)
  await page.waitForSelector('text=Tuesday nets', { timeout: 20000 })

  await safe('Session link', async () => {
    console.log('\n── The session\'s own link ──')
    check('the session has a Link button', (await page.locator('[data-session-link-btn]').count()) === 1)
    await page.locator('[data-session-link-btn]').click()
    await page.locator('[data-session-link]').waitFor()
    const url = await page.locator('[data-session-link-url]').inputValue()
    check('its address is this session\'s own, not the club-wide one', url.endsWith('/nets-checkin/sess-tok-123'), url)
    check('a QR code is drawn for it', (await page.locator('img[alt="Check-in QR code for this session"]').count()) === 1)
    check('the club\'s squads are offered', (await page.locator('[data-session-link] button', { hasText: 'Seniors' }).count()) === 1 && (await page.locator('[data-session-link] button', { hasText: 'Colts' }).count()) === 1)
  })

  await safe('Squads', async () => {
    console.log('\n── Limiting the session to a squad ──')
    wire.patches.length = 0
    await page.locator('[data-session-link] button', { hasText: 'Seniors' }).click()
    await page.waitForTimeout(500)
    check('ticking Seniors PATCHes just squad_team_ids', JSON.stringify(wire.patches) === JSON.stringify([{ squad_team_ids: [SENIORS] }]), JSON.stringify(wire.patches))
    await page.locator('[data-session-link] button[aria-label="Close"]').click()
    check('the Link button now shows the squad count', /1 squad/.test(await page.locator('[data-session-link-btn]').innerText()))
  })

  await safe('Check in by squad', async () => {
    console.log('\n── Checking in squad by squad ──')
    await page.getByRole('button', { name: 'Check in players' }).click()
    await page.locator('[data-checkin-squads]').waitFor()
    let text = await page.locator('body').innerText()
    check('the list opens on the session\'s squad (Zed and Anna, not Cara)', text.includes('Adams, Zed') && text.includes('Brown, Anna') && !text.includes('Cole, Cara'))
    await page.locator('[data-checkin-squads] button', { hasText: 'Colts' }).click(); await page.waitForTimeout(250)
    text = await page.locator('body').innerText()
    check('adding Colts brings Cara in', text.includes('Cole, Cara'))
    await page.locator('[data-checkin-squads] button', { hasText: 'Everyone' }).click(); await page.waitForTimeout(250)
    text = await page.locator('body').innerText()
    check('Everyone shows all three', text.includes('Adams, Zed') && text.includes('Brown, Anna') && text.includes('Cole, Cara'))
    await page.locator('[data-checkin-squads] button', { hasText: 'Seniors' }).click(); await page.waitForTimeout(250)
    await page.getByPlaceholder('Search every player at the club…').fill('cole'); await page.waitForTimeout(250)
    text = await page.locator('body').innerText()
    check('a search still reaches a player outside the squad', text.includes('Cole, Cara'))
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/nets-checkin-squads.png` : '/tmp/nets-checkin-squads.png' })
  })

  await safe('Public page', async () => {
    console.log('\n── The player\'s page ──')
    await page.goto(`${BASE}/nets-checkin/sess-tok-123`)
    await page.locator('[data-squad-note]').waitFor()
    check('it names the squad its list is limited to', /Seniors squad/.test(await page.locator('[data-squad-note]').innerText()))
  })

  await safe('390px', async () => {
    console.log('\n── 390px ──')
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto(`${BASE}/admin/betterselect/nets/sess1`)
    await page.waitForSelector('text=Tuesday nets')
    await page.locator('[data-session-link-btn]').click()
    await page.locator('[data-session-link]').waitFor()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
    check('no sideways overflow with the link modal open', overflow <= 1, String(overflow))
  })

  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
