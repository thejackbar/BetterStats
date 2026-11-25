// "Can't find your name?" on the Player Dashboard, and the Registrations list in BetterStats, against the real
// screens with the API stubbed at the network layer (the stub answers the way routers/public_player_register.py does).
//
// Asserts:
//   * the name step shows the Register button only when the landing says registration is open (a contrast);
//   * the past-player search waits for three letters, then lists a hidden past player with the year they last played;
//   * claiming a record asks for NO PIN up front; the server's need_pin brings the old-number box, and the exact
//     claim_player_id + pin + playing go on the wire;
//   * a claimed record with no mobile posts no pin and lands on the thank-you screen;
//   * a new sign-up whose name is on the books gets "Is one of these you?"; That's me re-sends it as a claim;
//     None of these sends confirmed_new;
//   * Your cricket appears only for a playing connection, and a supporter's post carries no playing details;
//   * admin: opens on Needs review; a matched sign-up sits in Signed up and says how it was matched and what was
//     added; a bare note is not shown; an inactive returning player offers Make active again (POST on the wire);
//     Mark contacted sends only {contacted:true}; the role filter narrows the list;
//   * the settings switch posts only {registration_enabled:false};
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
  { id: 'past-1', display_name: 'Oldham, Bruce', last_played_year: 2014, has_phone: true, phone: '0400333444' },
  { id: 'past-2', display_name: 'Oldfield, Colin', last_played_year: 2009, has_phone: false },
  { id: 'russ', display_name: 'Kingdon, Russell', last_played_year: 2006, has_phone: true, phone: '0433331162' },
]
const ME = { player: { id: 'me', display_name: 'Newman, Dana' }, dates: [], availability: {}, has_availability: false, club: CLUB, modules: [] }

const reg = (o) => ({
  id: 'r1', player_id: 'russ', player_name: 'Kingdon, Russell', kind: 'claim', role: 'current_player', role_label: 'Current player',
  first_name: 'Russell', last_name: 'Kingdon', email: 'russell@example.com', phone: '0433331162', date_of_birth: null,
  years_played: '', grades_played: '', notes: '', interests: ['volunteer'], contact_consent: true, status: 'approved',
  matched_by: 'mobile', playing: { player_role: 'Batter', batting_hand: 'RIGHT', bowling_action: 'RIGHT_ARM', bowling_type: 'FINGER_SPIN' },
  applied: ['role', 'bowling', 'back for selection'], player_status: 'inactive', player_dormant: true,
  admin_note: '', contacted_at: null, reviewed_at: '2026-11-25T01:00:00Z', reviewed_by: 'Matched automatically',
  created_at: '2026-11-25T10:00:00Z', last_played: '2006-01-28', is_player: true, ...o,
})
const adminState = {
  regs: [
    reg({}),
    reg({ id: 'r2', player_id: 'p2', player_name: 'Newman, Dana', kind: 'new', role: 'volunteer', role_label: 'Volunteer', first_name: 'Dana',
      last_name: 'Newman', email: 'dana@example.com', phone: '0400 555 666', interests: ['volunteer'], notes: 'Free on Saturdays for canteen',
      status: 'pending', matched_by: null, playing: {}, applied: [], last_played: null, is_player: false, contact_consent: false,
      player_status: 'active', player_dormant: false }),
    reg({ id: 'r3', player_id: 'p3', player_name: 'Oldfield, Colin', kind: 'claim', role: 'ex_player', role_label: 'Past player', first_name: 'Colin',
      last_name: 'Oldfield', status: 'pending', matched_by: null, applied: [], interests: [], playing: {}, player_status: 'inactive' }),
    reg({ id: 'r4', player_id: 'p4', player_name: 'Archie, Ann', kind: 'new', role: 'supporter', role_label: 'Supporter', first_name: 'Ann',
      last_name: 'Archie', status: 'archived', matched_by: null, interests: [], playing: {}, applied: [], is_player: false, player_status: 'inactive' }),
  ],
}
const counts = () => Object.fromEntries(['pending', 'approved', 'archived'].map((s) => [s, adminState.regs.filter((r) => r.status === s).length]))
const digits = (s) => String(s || '').replace(/\D/g, '').slice(-9)

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
        return json({ min_chars: 3, players: q.replace(/\s/g, '').length < 3 ? [] : PAST.filter((p) => p.display_name.toLowerCase().includes(q)).map(({ phone, ...p }) => p) })
      }
      if (path === `${pub}/register` && method === 'POST') {
        const claim = PAST.find((p) => p.id === body.claim_player_id)
        if (claim) {
          if (!claim.has_phone) return json({ status: 'pending', player_name: claim.display_name })
          if (digits(body.phone) === digits(claim.phone)) { signedIn = true; return json({ status: 'signed_in', matched: true, player_name: claim.display_name }) }
          if (!body.pin) return json({ status: 'need_pin', player_name: claim.display_name })
          if (body.pin !== claim.phone.slice(-4)) return json({ detail: 'Those digits don’t match the mobile the club has for them.' }, 401)
          signedIn = true
          return json({ status: 'signed_in', matched: true, player_name: claim.display_name })
        }
        if (body.last_name === 'Kingdon' && !body.confirmed_new) {
          return json({ status: 'possible_matches', players: [{ id: 'russ', display_name: 'Kingdon, Russell', last_played_year: 2006, has_phone: true }] })
        }
        signedIn = true
        return json({ status: 'signed_in', matched: false, player_name: `${body.first_name} ${body.last_name}` })
      }
      if (path.startsWith(pub)) return json({})
      if (path === '/player-dashboard/registrations') {
        return json({ registrations: adminState.regs, roles: ROLES, interests: INTERESTS, counts: counts(), registration_enabled: true })
      }
      let m = path.match(/^\/player-dashboard\/registrations\/(r\d)\/(approve|archive|restore|reactivate)$/)
      if (m) {
        const r = adminState.regs.find((x) => x.id === m[1])
        if (m[2] === 'reactivate') { r.player_status = 'active'; r.player_dormant = false } else r.status = m[2] === 'approve' ? 'approved' : m[2] === 'archive' ? 'archived' : 'pending'
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
  const posts = () => calls.filter((c) => c.method === 'POST' && c.path.endsWith('/register'))
  const lastPost = () => posts().pop()?.body || {}
  const openRegister = async (page) => {
    await page.goto(`${BASE}/playerdash/${TOKEN}`)
    await page.locator('[data-cant-find]').click()
    await page.locator('[data-register-find]').waitFor()
  }

  // ── Closed club: no button (contrast) ───────────────────────────────────────
  registrationOpen = false
  let page = await newPage({ width: 390, height: 900 })
  await page.goto(`${BASE}/playerdash/${TOKEN}`)
  await page.getByText('Who are you?').waitFor({ timeout: 20000 })
  check('closed: no Register button', (await page.locator('[data-cant-find]').count()) === 0)
  await page.context().close()
  registrationOpen = true

  // ── Claim, a new mobile: PIN asked only when the server says so ─────────────
  page = await newPage({ width: 390, height: 900 })
  await page.goto(`${BASE}/playerdash/${TOKEN}`)
  await page.getByText('Who are you?').waitFor({ timeout: 20000 })
  check('open: Register button on the name step', (await page.locator('[data-cant-find]').count()) === 1)
  await page.locator('[data-cant-find]').click()
  await page.locator('[data-register-search]').fill('ol')
  await page.waitForTimeout(500)
  check('search waits for three letters', !calls.some((c) => c.path.endsWith('/past-players') && c.q === 'ol'))
  await page.locator('[data-register-search]').fill('old')
  await page.locator('[data-register-past="past-1"]').waitFor()
  check('past players listed with last played year', (await page.locator('[data-register-past="past-1"]').innerText()).includes('Last played 2014'))
  await shot(page, '01-find')
  await page.locator('[data-register-past="past-1"]').click()
  await page.locator('[data-register-form="claim"]').waitFor()
  check('claim: welcome back by first name, record named', (await page.locator('h1').innerText()).includes('Welcome back, Bruce')
    && (await page.locator('[data-register-claim-name]').innerText()).includes('last played 2014'))
  check('claim: no PIN box up front', (await page.locator('[data-register-pin]').count()) === 0)
  check('claim: cricket section shown for a past player', (await page.locator('[data-register-cricket]').count()) === 1)
  check('claim: no years/grades (the club has the record)', (await page.locator('#reg-years').count()) === 0)
  await page.locator('#reg-phone').fill('0499 999 999')
  await page.locator('[data-crole="All Rounder"]').click()
  await page.locator('[data-hand="LEFT"]').click()
  await page.selectOption('[data-register-bowling]', 'Left-arm orthodox')
  await page.locator('[data-register-overseas]').check()
  await page.locator('#reg-country').fill('England')
  await page.locator('[data-register-submit]').click()
  await page.locator('[data-register-pin-box]').waitFor()
  check('need_pin: the old-number box appears with the reason', (await page.locator('[data-register-pin-box]').innerText()).includes('different mobile'))
  check('need_pin: not signed in yet', !signedIn)
  await shot(page, '02-need-pin')
  await page.locator('[data-register-pin]').fill('3444')
  await page.locator('[data-register-submit]').click()
  await page.waitForTimeout(800)
  const pinPost = lastPost()
  check('claim posts claim_player_id and pin', pinPost.claim_player_id === 'past-1' && pinPost.pin === '3444', JSON.stringify(pinPost))
  check('claim posts the cricket exactly', JSON.stringify(pinPost.playing) === JSON.stringify({ player_role: 'All Rounder', batting_hand: 'LEFT', bowling_action: 'LEFT_ARM', bowling_type: 'FINGER_SPIN', is_overseas: true, overseas_country: 'England' }), JSON.stringify(pinPost.playing))
  check('signed in: the page reads who they are', signedIn && calls.some((c) => c.path.endsWith('/me') && c.method === 'GET'))
  await page.context().close()

  // ── Claim, no mobile on the record → pending ───────────────────────────────
  signedIn = false
  page = await newPage({ width: 390, height: 900 })
  await openRegister(page)
  await page.locator('[data-register-search]').fill('oldfield')
  await page.locator('[data-register-past="past-2"]').click()
  await page.locator('[data-register-form="claim"]').waitFor()
  check('no mobile on record: says the club will confirm', (await page.getByText('the club will confirm').count()) > 0)
  await page.locator('#reg-phone').fill('0477 000 111')
  await page.locator('[data-register-submit]').click()
  await page.locator('[data-register-pending]').waitFor()
  check('pending claim posts no pin', !('pin' in lastPost()) && lastPost().claim_player_id === 'past-2', JSON.stringify(lastPost()))
  await page.context().close()

  // ── New sign-up whose name is on the books: Is one of these you? ────────────
  signedIn = false
  page = await newPage({ width: 390, height: 900 })
  await openRegister(page)
  await page.locator('[data-register-new]').click()
  await page.locator('[data-register-form="new"]').waitFor()
  check('new: no cricket section before a connection is picked', (await page.locator('[data-register-cricket]').count()) === 0)
  await page.locator('#reg-first').fill('Russ')
  await page.locator('#reg-last').fill('Kingdon')
  await page.locator('#reg-phone').fill('0433 331 162')
  await page.locator('[data-register-submit]').click()
  check('new: connection required before posting', (await page.getByText('Pick how you’re connected').count()) > 0 && !posts().some((p) => p.body.first_name === 'Russ'))
  await page.locator('[data-role="ex_player"]').click()
  check('new past player: years and grades offered', (await page.locator('#reg-years').count()) === 1)
  await page.locator('[data-crole="Batter"]').click()
  await page.locator('#reg-notes').fill('No')
  await page.locator('[data-register-submit]').click()
  await page.locator('[data-register-matches]').waitFor()
  check('possible match: asks "Is one of these you?" and names Russell', (await page.locator('[data-register-matches]').innerText()).includes('Kingdon, Russell'))
  check('possible match: submit hidden while asking', (await page.locator('[data-register-submit]').count()) === 0)
  check('390px: no overflow with the matches panel', (await overflow(page)) <= 0, String(await overflow(page)))
  await shot(page, '03-possible-match')
  await page.locator('[data-register-match="russ"]').click()
  await page.waitForTimeout(800)
  const pick = lastPost()
  check("That's me re-sends as a claim with the same form", pick.claim_player_id === 'russ' && pick.first_name === 'Russ'
    && pick.playing?.player_role === 'Batter' && !('confirmed_new' in pick), JSON.stringify(pick))
  check('matched on mobile: signed in with no PIN', signedIn && !('pin' in pick))
  await page.context().close()

  // ── None of these are me, and a supporter's form ───────────────────────────
  signedIn = false
  page = await newPage({ width: 1200, height: 1000 })
  await openRegister(page)
  await page.locator('[data-register-new]').click()
  await page.locator('#reg-first').fill('Nigel')
  await page.locator('#reg-last').fill('Kingdon')
  await page.locator('#reg-phone').fill('0455 000 999')
  await page.locator('[data-role="current_player"]').click()
  await page.locator('[data-crole="Bowler"]').click()
  await page.locator('[data-role="supporter"]').click()
  check('supporter: cricket section goes away', (await page.locator('[data-register-cricket]').count()) === 0)
  await page.locator('[data-interest="social"]').click()
  await shot(page, '04-new-form-desktop')
  await page.locator('[data-register-submit]').click()
  await page.locator('[data-register-matches]').waitFor()
  await page.locator('[data-register-not-me]').click()
  await page.waitForTimeout(800)
  const none = lastPost()
  check('None of these sends confirmed_new and no claim', none.confirmed_new === true && !('claim_player_id' in none), JSON.stringify(none))
  check("a supporter's post carries no playing details", JSON.stringify(none.playing) === '{}' && none.years_played === '', JSON.stringify(none))
  await page.context().close()

  // ── Admin ──────────────────────────────────────────────────────────────────
  page = await newPage({ width: 1200, height: 1000 })
  await page.goto(`${BASE}/admin/player-registrations`)
  const root = page.locator('[data-player-registrations-admin]')
  await root.waitFor({ timeout: 20000 })
  await page.locator('[data-registration-row]').first().waitFor()
  check('opens on Needs review: the new person and the unproven claim only',
    (await page.locator('[data-registration-row]').count()) === 2 && (await page.locator('[data-registration-row="r1"]').count()) === 0)
  check('unproven claim explains why it waits', (await page.locator('[data-registration-row="r3"]').innerText()).includes('has no mobile'))
  check('the note is labelled', (await page.locator('[data-registration-row="r2"] [data-registration-notes]').innerText()).includes('IN THEIR WORDS'))
  await shot(page, '05-admin-review')
  await root.getByRole('button', { name: /^Signed up/ }).click()
  const russ = page.locator('[data-registration-row="r1"]')
  await russ.waitFor()
  const rt = await russ.innerText()
  check('matched sign-up sits in Signed up, says how it matched', rt.includes('Matched to their record by mobile'), rt.slice(0, 200))
  check('says what was added to the record', rt.includes('Added to it: role, bowling'), rt)
  check('shows their cricket in words', rt.includes('Batter · Right handed · Off spin'), rt)
  check('no empty note block', (await russ.locator('[data-registration-notes]').count()) === 0)
  check('inactive returning player: Make active again offered', (await russ.locator('[data-reactivate]').count()) === 1)
  await shot(page, '06-admin-signed-up')
  await russ.locator('[data-reactivate]').click()
  await page.waitForTimeout(400)
  check('Make active again posts to the right row', calls.some((c) => c.method === 'POST' && c.path === '/player-dashboard/registrations/r1/reactivate'))
  check('the prompt goes once active', (await russ.locator('[data-reactivate]').count()) === 0)
  await russ.locator('[data-contacted]').click()
  await page.waitForTimeout(400)
  const patch = calls.filter((c) => c.method === 'PATCH').pop()
  check('Mark contacted sends only {contacted:true}', patch && JSON.stringify(patch.body) === '{"contacted":true}', JSON.stringify(patch?.body))
  await root.getByRole('button', { name: /^All/ }).click()
  await page.selectOption('select[aria-label="Role"]', 'supporter')
  check('role filter narrows to the supporter', (await page.locator('[data-registration-row]').count()) === 1)
  await page.selectOption('select[aria-label="Role"]', '')
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(200)
  check('admin 390px: no horizontal overflow', (await overflow(page)) <= 0, String(await overflow(page)))
  await shot(page, '07-admin-390')
  await page.context().close()

  page = await newPage({ width: 1200, height: 1000 })
  await page.goto(`${BASE}/admin/player-dashboard`)
  await page.locator('[data-dash-register-setting]').waitFor({ timeout: 20000 })
  await page.locator('[data-dash-register-setting]').getByRole('button', { name: 'Off', exact: true }).click()
  await page.waitForTimeout(400)
  const set = calls.filter((c) => c.method === 'POST' && c.path === '/player-dashboard/settings').pop()
  check('switch posts only {registration_enabled:false}', set && JSON.stringify(set.body) === '{"registration_enabled":false}', JSON.stringify(set?.body))
  await page.context().close()

  check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
