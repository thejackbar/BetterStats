// "Can't find your name?" on the Player Dashboard, and the Registrations list in BetterStats, against the real
// screens with the API stubbed at the network layer.
//
// Asserts:
//   * the name step shows the Register button only when the landing says registration is open (a contrast);
//   * the past-player search waits for three letters, then lists a hidden past player with the year they last played;
//   * claiming a record with a mobile asks for its last 4 digits and posts exactly claim_player_id + pin + the form;
//   * a claimed record with no mobile says the club will confirm, posts with no pin, and lands on the thank-you screen;
//   * a brand new person picks a role and interests, and the exact body goes on the wire; signed in, the page opens;
//   * admin: the list opens on To review, names a claimed record, Approve posts to the right row and the row updates,
//     Mark contacted sends only {contacted:true}, the role filter narrows the list;
//   * the Player Dashboard settings screen posts {registration_enabled:false} and only that;
//   * no page errors, and no horizontal overflow at 390px on either screen.
//
//   APP_URL=http://localhost:4173 SHOT_DIR=/tmp/reg node verification/verify_player_registration_browser.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
if (SHOT) fs.mkdirSync(SHOT, { recursive: true })
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}

const TOKEN = 'tokreg'
const ROLES = [
  { key: 'current_player', label: 'Current player' }, { key: 'ex_player', label: 'Past player' },
  { key: 'parent', label: 'Parent or family' }, { key: 'volunteer', label: 'Volunteer' },
  { key: 'coach', label: 'Coach or official' }, { key: 'supporter', label: 'Supporter' }, { key: 'other', label: 'Something else' },
]
const INTERESTS = [
  { key: 'play', label: 'Playing (again)' }, { key: 'volunteer', label: 'Volunteering' }, { key: 'coach', label: 'Coaching' },
  { key: 'social', label: 'Social events' }, { key: 'sponsor', label: 'Sponsoring or helping with fundraising' },
]
const CLUB = { name: 'Verify Cricket Club', short_name: 'VCC', slug: 'verify-cc', primary_color: '#1d4ed8', accent_color: '#16c784', player_name_format: 'last_first' }
const PAST = [
  { id: 'past-1', display_name: 'Oldham, Bruce', last_played_year: 2014, has_phone: true },
  { id: 'past-2', display_name: 'Oldfield, Colin', last_played_year: 2009, has_phone: false },
]
const ME = { player: { id: 'me', display_name: 'Newman, Dana' }, dates: [], availability: {}, has_availability: false, club: CLUB, modules: [] }

const reg = (o) => ({
  id: 'r1', player_id: 'p1', player_name: 'Oldham, Bruce', kind: 'claim', role: 'ex_player', role_label: 'Past player',
  first_name: 'Bruce', last_name: 'Oldham', email: 'bruce@example.com', phone: '0400 333 444', date_of_birth: '1980-03-04',
  years_played: '2005 to 2014', grades_played: '2nd XI', notes: 'Keen for a social game', interests: ['play', 'social'],
  contact_consent: true, status: 'pending', admin_note: '', contacted_at: null, reviewed_at: null, reviewed_by: null,
  created_at: '2026-11-20T10:00:00Z', last_played: '2014-03-01', is_player: true, ...o,
})
const adminState = {
  regs: [
    reg({}),
    reg({ id: 'r2', player_id: 'p2', player_name: 'Newman, Dana', kind: 'new', role: 'volunteer', role_label: 'Volunteer', first_name: 'Dana',
      last_name: 'Newman', email: 'dana@example.com', phone: '0400 555 666', years_played: '', grades_played: '', interests: ['volunteer'],
      notes: '', last_played: null, is_player: false, contact_consent: false }),
    reg({ id: 'r3', player_id: 'p3', player_name: 'Archie, Ann', kind: 'new', role: 'supporter', role_label: 'Supporter', first_name: 'Ann',
      last_name: 'Archie', status: 'archived', interests: [] }),
  ],
}
const counts = () => Object.fromEntries(['pending', 'approved', 'archived'].map((s) => [s, adminState.regs.filter((r) => r.status === s).length]))

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = [], calls = []
  let registrationOpen = true
  let signedIn = false
  const dashSettings = { enabled: true, has_select: false, availability_enabled: false, require_pin: true, show_on_site: true,
    dashboard_modules: [], token: TOKEN, path: `/playerdash/${TOKEN}`, phone_coverage: { with_phone: 10, total: 12 },
    registration_enabled: true, registrations_pending: 2 }

  const newPage = async (viewport) => {
    const ctx = await browser.newContext({ viewport })
    await ctx.addInitScript(() => {
      localStorage.setItem('token', 'stub')
      localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
      localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
    })
    const page = await ctx.newPage()
    page.setDefaultTimeout(10000)
    page.on('pageerror', (e) => errors.push(String(e)))
    page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|401|404/.test(m.text())) errors.push(m.text()) })
    await page.route('**/api/**', async (route) => {
      const req = route.request(), url = req.url(), method = req.method()
      const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
      const path = new URL(url).pathname.replace(/^\/api/, '')
      const search = new URL(url).searchParams
      const body = req.postData() ? JSON.parse(req.postData()) : null
      calls.push({ method, path, body, q: search.get('q') })
      if (/\/auth\/me/.test(path)) return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'verify-cc', entitlements: { modules: [], status: 'active' } })
      const pub = `/public/availability/${TOKEN}`
      if (path === pub) return json({ club: CLUB, require_pin: true, has_availability: false, allow_maybe: true, week_names: {}, registration_open: registrationOpen,
        players: [{ id: 'a1', display_name: 'Current, Alex', has_phone: true }] })
      if (path === `${pub}/me` || path === `${pub}/me/profile`) return signedIn ? json(path.endsWith('profile') ? { modules: [] } : ME) : json({ detail: 'Not verified' }, 401)
      if (path === `${pub}/register` && method === 'GET') return json({ open: true, require_pin: true, roles: ROLES, interests: INTERESTS })
      if (path === `${pub}/past-players`) {
        const q = (search.get('q') || '').toLowerCase()
        return json({ min_chars: 3, players: q.replace(/\s/g, '').length < 3 ? [] : PAST.filter((p) => p.display_name.toLowerCase().includes(q)) })
      }
      if (path === `${pub}/register` && method === 'POST') {
        if (body.claim_player_id === 'past-2') return json({ status: 'pending', player_name: 'Oldfield, Colin' })
        signedIn = true
        return json({ status: 'signed_in', player_name: `${body.first_name} ${body.last_name}` })
      }
      if (path.startsWith(pub)) return json({})
      if (path === '/player-dashboard/registrations') {
        return json({ registrations: adminState.regs, roles: ROLES, interests: INTERESTS, counts: counts(), registration_enabled: true })
      }
      let m = path.match(/^\/player-dashboard\/registrations\/(r\d)\/(approve|archive|restore)$/)
      if (m) {
        const r = adminState.regs.find((x) => x.id === m[1])
        r.status = m[2] === 'approve' ? 'approved' : m[2] === 'archive' ? 'archived' : 'pending'
        return json(r)
      }
      m = path.match(/^\/player-dashboard\/registrations\/(r\d)$/)
      if (m && method === 'PATCH') {
        const r = adminState.regs.find((x) => x.id === m[1])
        if ('contacted' in body) r.contacted_at = body.contacted ? '2026-11-25T01:00:00Z' : null
        if ('admin_note' in body) r.admin_note = body.admin_note
        return json(r)
      }
      if (path === '/player-dashboard/settings') {
        if (method === 'POST') Object.assign(dashSettings, body)
        return json(dashSettings)
      }
      return json({})
    })
    return page
  }
  const shot = async (page, name) => { if (SHOT) await page.screenshot({ path: `${SHOT}/${name}.png`, fullPage: true }) }
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  const posts = (p) => calls.filter((c) => c.method !== 'GET' && c.path.endsWith(p))

  // ── Public: closed club shows no button (contrast) ─────────────────────────
  registrationOpen = false
  let page = await newPage({ width: 390, height: 900 })
  await page.goto(`${BASE}/playerdash/${TOKEN}`)
  await page.getByText('Who are you?').waitFor({ timeout: 20000 })
  check('closed: no Register button', (await page.locator('[data-cant-find]').count()) === 0)
  check('closed: still says ask your club admin', (await page.getByText('Ask your club admin').count()) > 0)
  await page.context().close()

  // ── Public: claim with a mobile on file ────────────────────────────────────
  registrationOpen = true
  page = await newPage({ width: 390, height: 900 })
  await page.goto(`${BASE}/playerdash/${TOKEN}`)
  await page.getByText('Who are you?').waitFor({ timeout: 20000 })
  const btn = page.locator('[data-cant-find]')
  check('open: Register button on the name step', (await btn.count()) === 1)
  await shot(page, '01-name-step')
  await btn.click()
  await page.locator('[data-register-find]').waitFor()
  await page.locator('[data-register-search]').fill('ol')
  await page.waitForTimeout(500)
  check('search waits for three letters', (await page.locator('[data-register-past]').count()) === 0 && !calls.some((c) => c.path.endsWith('/past-players') && c.q === 'ol'))
  await page.locator('[data-register-search]').fill('old')
  await page.locator('[data-register-past="past-1"]').waitFor()
  check('past players listed with last played year', (await page.locator('[data-register-past="past-1"]').innerText()).includes('Last played 2014'))
  check('390px: no horizontal overflow on search', (await overflow(page)) <= 0, String(await overflow(page)))
  await shot(page, '02-past-search')
  await page.locator('[data-register-past="past-1"]').click()
  await page.locator('[data-register-form="claim"]').waitFor()
  check('claim form prefills the name', (await page.locator('#reg-first').inputValue()) === 'Bruce' && (await page.locator('#reg-last').inputValue()) === 'Oldham')
  check('claim with a mobile asks for the PIN', (await page.locator('[data-register-pin]').count()) === 1)
  check('claim defaults the role to Past player', (await page.locator('[data-role="ex_player"]').getAttribute('aria-pressed')) === 'true')
  await page.locator('[data-register-pin]').fill('3444')
  await page.locator('#reg-phone').fill('0499 999 999')
  await page.locator('#reg-email').fill('bruce@example.com')
  await page.locator('[data-interest="social"]').click()
  await page.locator('[data-register-consent]').check()
  check('390px: no horizontal overflow on the form', (await overflow(page)) <= 0, String(await overflow(page)))
  await shot(page, '03-claim-form')
  await page.locator('[data-register-submit]').click()
  await page.waitForTimeout(800)
  const claimPost = posts('/register').pop()?.body || {}
  check('claim posts claim_player_id and pin', claimPost.claim_player_id === 'past-1' && claimPost.pin === '3444', JSON.stringify(claimPost))
  check('claim posts the form fields', claimPost.role === 'ex_player' && claimPost.phone === '0499 999 999' && claimPost.contact_consent === true
    && JSON.stringify(claimPost.interests) === '["social"]' && claimPost.date_of_birth === null, JSON.stringify(claimPost))
  check('signed in: the page reads who they are', calls.some((c) => c.path.endsWith('/me') && c.method === 'GET'))
  await page.context().close()

  // ── Public: claim with no mobile → pending ─────────────────────────────────
  signedIn = false
  page = await newPage({ width: 390, height: 900 })
  await page.goto(`${BASE}/playerdash/${TOKEN}`)
  await page.locator('[data-cant-find]').click()
  await page.locator('[data-register-search]').fill('oldfield')
  await page.locator('[data-register-past="past-2"]').click()
  await page.locator('[data-register-form="claim"]').waitFor()
  check('no mobile on file: no PIN box', (await page.locator('[data-register-pin]').count()) === 0)
  check('no mobile on file: says the club will confirm', (await page.getByText('the club will confirm').count()) > 0)
  await page.locator('#reg-phone').fill('0477 000 111')
  await page.locator('[data-register-submit]').click()
  await page.locator('[data-register-pending]').waitFor()
  const pendPost = posts('/register').pop()?.body || {}
  check('pending claim posts no pin', !('pin' in pendPost) && pendPost.claim_player_id === 'past-2', JSON.stringify(pendPost))
  check('thank-you screen shown', (await page.locator('[data-register-pending]').innerText()).includes('told the club'))
  await shot(page, '04-pending')
  await page.context().close()

  // ── Public: brand new person ───────────────────────────────────────────────
  signedIn = false
  page = await newPage({ width: 390, height: 900 })
  await page.goto(`${BASE}/playerdash/${TOKEN}`)
  await page.locator('[data-cant-find]').click()
  await page.locator('[data-register-new]').click()
  await page.locator('[data-register-form="new"]').waitFor()
  check('new: no years/grades until a playing role is picked', (await page.locator('#reg-years').count()) === 0)
  await page.locator('#reg-first').fill('Dana')
  await page.locator('#reg-last').fill('Newman')
  await page.locator('#reg-phone').fill('0400 555 666')
  await page.locator('[data-register-submit]').click()
  check('new: role required before posting', (await page.getByText('Pick what best describes you.').count()) > 0 && posts('/register').length === 2)
  await page.locator('[data-role="ex_player"]').click()
  check('new: years/grades appear for a past player', (await page.locator('#reg-years').count()) === 1)
  await page.locator('[data-role="volunteer"]').click()
  await page.locator('#reg-phone').fill('0400 555 666')
  await page.locator('#reg-dob').fill('1980-03-04')
  await page.locator('[data-interest="volunteer"]').click()
  await page.locator('[data-interest="coach"]').click()
  await page.locator('[data-interest="coach"]').click()
  await page.locator('#reg-notes').fill('Happy to help on canteen')
  await shot(page, '05-new-form')
  await page.locator('[data-register-submit]').click()
  await page.waitForTimeout(800)
  const newPost = posts('/register').pop()?.body || {}
  check('new posts no claim and no pin', !('claim_player_id' in newPost) && !('pin' in newPost), JSON.stringify(newPost))
  check('new posts the exact form', newPost.first_name === 'Dana' && newPost.last_name === 'Newman' && newPost.role === 'volunteer'
    && newPost.date_of_birth === '1980-03-04' && JSON.stringify(newPost.interests) === '["volunteer"]' && newPost.contact_consent === false
    && newPost.notes === 'Happy to help on canteen', JSON.stringify(newPost))
  await page.context().close()

  // ── Admin: registrations list ──────────────────────────────────────────────
  page = await newPage({ width: 1200, height: 1000 })
  await page.goto(`${BASE}/admin/player-registrations`)
  const root = page.locator('[data-player-registrations-admin]')
  await root.waitFor({ timeout: 20000 })
  await page.locator('[data-registration-row]').first().waitFor()
  check('opens on To review: two rows, not the archived one', (await page.locator('[data-registration-row]').count()) === 2)
  check('names the claimed record', (await page.locator('[data-registration-row="r1"]').innerText()).includes('Claimed record: Oldham, Bruce'))
  check('says when someone did not consent', (await page.locator('[data-registration-row="r2"] [data-registration-consent]').innerText()).includes('Did not tick'))
  await shot(page, '06-admin-list')
  await page.locator('[data-registration-row="r1"] [data-approve]').click()
  await page.waitForTimeout(400)
  check('approve posts to the right row', calls.some((c) => c.method === 'POST' && c.path === '/player-dashboard/registrations/r1/approve'))
  check('approved row leaves To review', (await page.locator('[data-registration-row="r1"]').count()) === 0)
  await page.locator('[data-registration-row="r2"] [data-contacted]').click()
  await page.waitForTimeout(400)
  const patch = calls.filter((c) => c.method === 'PATCH').pop()
  check('mark contacted sends only {contacted:true}', patch && JSON.stringify(patch.body) === '{"contacted":true}', JSON.stringify(patch?.body))
  check('row shows Contacted', (await page.locator('[data-registration-row="r2"]').innerText()).includes('Contacted '))
  await root.getByRole('button', { name: /^All/ }).click()
  check('All shows three', (await page.locator('[data-registration-row]').count()) === 3)
  await page.selectOption('select[aria-label="Role"]', 'supporter')
  check('role filter narrows to the supporter', (await page.locator('[data-registration-row]').count()) === 1
    && (await page.locator('[data-registration-row="r3"]').count()) === 1)
  await page.setViewportSize({ width: 390, height: 900 })
  await page.selectOption('select[aria-label="Role"]', '')
  await page.waitForTimeout(200)
  check('admin 390px: no horizontal overflow', (await overflow(page)) <= 0, String(await overflow(page)))
  await shot(page, '07-admin-390')
  await page.context().close()

  // ── Admin: settings switch ─────────────────────────────────────────────────
  page = await newPage({ width: 1200, height: 1000 })
  await page.goto(`${BASE}/admin/player-dashboard`)
  await page.locator('[data-dash-register-setting]').waitFor({ timeout: 20000 })
  check('settings links to the 2 to review', (await page.locator('[data-dash-register-link]').innerText()).includes('2 to review'))
  await page.locator('[data-dash-register-setting]').getByRole('button', { name: 'Off', exact: true }).click()
  await page.waitForTimeout(400)
  const set = calls.filter((c) => c.method === 'POST' && c.path === '/player-dashboard/settings').pop()
  check('switch posts only {registration_enabled:false}', set && JSON.stringify(set.body) === '{"registration_enabled":false}', JSON.stringify(set?.body))
  check('off: note says nobody can add themselves', (await page.locator('[data-dash-register-note]').innerText()).includes('Nobody can add themselves'))
  await page.context().close()

  check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
