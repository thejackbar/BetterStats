// Linked clubs (migration 322): drives the real screens in Chromium with the API
// stubbed at the network layer.
//
//   npx vite build && npx vite preview --port 5199 &
//   node verification/verify_club_links_browser.mjs [baseUrl]
//
// Asked for: a Super Admin links two clubs; their Club Admins can then pick which
// club they work in from the dashboard; a club that is not linked sees none of
// it. So the checks cover what is drawn for a linked and an unlinked club, the
// exact request each click sends, the state after the reload a switch does, the
// refusal path, the Super Admin page, and the layout at phone, tablet and desktop.
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || '/tmp/claude-0'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const ALPHA = { id: 'c1', name: 'Alpha CC', slug: 'alpha' }
const BRAVO = { id: 'c2', name: 'Bravo CC with a rather long name that has to truncate on a phone', slug: 'bravo' }

// The /auth/me payload a Club Admin gets, in the club they are currently in.
function meFor(state) {
  const cur = state.current === 'c2' ? BRAVO : ALPHA
  const linked = state.linked
    ? [
        { id: 'c1', name: ALPHA.name, slug: ALPHA.slug, is_home: true, is_current: state.current === 'c1' },
        { id: 'c2', name: BRAVO.name, slug: BRAVO.slug, is_home: false, is_current: state.current === 'c2' },
      ]
    : []
  return {
    id: 'u1', username: 'pat', display_name: 'Pat', role: state.role,
    club_id: cur.id, club_slug: cur.slug, club_name: cur.name,
    is_primary_admin: true, can_switch_clubs: state.role === 'super_admin',
    home_club_id: 'c1', home_club_name: ALPHA.name,
    acting_as_club: false,
    linked_clubs: state.role === 'club_admin' ? linked : [],
    can_switch_linked_clubs: state.role === 'club_admin' && linked.length > 1,
    acting_as_linked_club: state.role === 'club_admin' && state.linked && state.current !== 'c1',
    entitlements: { modules: ['select'], status: 'active', billing_modules: [] }, capabilities: [],
  }
}

function makeState(over = {}) {
  return {
    role: 'club_admin', linked: true, current: 'c1', refuseSwitch: false, calls: [],
    groups: [], clubs: [ALPHA, BRAVO, { id: 'c3', name: 'Charlie CC', slug: 'charlie' }],
    ...over,
  }
}

async function stub(page, state) {
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    const method = req.method()
    const body = req.postData() ? JSON.parse(req.postData()) : null
    state.calls.push({ method, p, body })
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p === '/auth/me') return json(meFor(state))
    if (p === '/auth/switch-club') {
      if (state.refuseSwitch) return json({ detail: 'That club is not linked to yours' }, 403)
      state.current = body.club_id || 'c1'
      return json(meFor(state))
    }
    if (p === '/club-admin/settings') return json({ name: (state.current === 'c2' ? BRAVO : ALPHA).name, slug: state.current === 'c2' ? 'bravo' : 'alpha' })
    if (p === '/club-admin/broadcasts') return json({ items: [], preview: false })
    if (p === '/club-admin/seasons') return json([])
    if (p === '/club-admin/account/plan') return json({ modules: [] })
    if (p === '/club-admin/super/clubs') return json(state.clubs.map(c => ({ ...c, is_active: true })))
    if (p === '/club-admin/super/club-links' && method === 'GET') return json({ groups: state.groups })
    if (p === '/club-admin/super/club-links' && method === 'POST') {
      const names = [body.club_a_id, body.club_b_id].map(id => state.clubs.find(c => c.id === id))
      state.groups = [{ group_id: 'g1', linked_at: new Date().toISOString(),
        clubs: names.map(c => ({ id: c.id, name: c.name, slug: c.slug, is_active: true, archived: false })) }]
      return json({ group_id: 'g1', group: state.groups[0] }, 201)
    }
    if (/^\/club-admin\/super\/club-links\/[^/]+$/.test(p) && method === 'DELETE') {
      state.groups = []
      return json({ status: 'unlinked', removed: [p.split('/').pop()] })
    }
    return json({ detail: 'not stubbed' }, 404)
  })
}

const noOverflow = page => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)
const inside = (page, sel) => page.evaluate((s) => {
  const cw = document.documentElement.clientWidth
  const root = document.querySelector(s)
  return !!root && [root, ...root.querySelectorAll('*')].every(e => e.getBoundingClientRect().right <= cw + 1)
}, sel)

const browser = await chromium.launch({ executablePath: EXECUTABLE })
const wait = (page) => page.locator('h1').filter({ hasText: /Welcome/ }).waitFor({ timeout: 15000 })

// ── A linked Club Admin, at three widths ───────────────────────────────────
for (const width of [1440, 768, 390]) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  const state = makeState()
  await stub(page, state)
  await page.goto(`${BASE}/admin`)
  await wait(page)

  const card = page.getByTestId('linked-clubs-card')
  ck(`${width}: the dashboard shows the Your clubs panel`, (await card.count()) === 1)
  const buttons = card.getByRole('button')
  ck(`${width}: one button per club`, (await buttons.count()) === 2, `${await buttons.count()}`)
  ck(`${width}: the club being worked in is marked`, (await buttons.nth(0).getAttribute('aria-pressed')) === 'true'
    && (await buttons.nth(1).getAttribute('aria-pressed')) === 'false')
  ck(`${width}: the home club says so`, /HOME/.test(await buttons.nth(0).innerText()))
  ck(`${width}: no banner while in the home club`, (await page.getByTestId('linked-club-banner').count()) === 0)
  ck(`${width}: the panel stays inside the screen`, await inside(page, '[data-testid="linked-clubs-card"]'))
  if (width !== 768) ck(`${width}: nothing pushes the page sideways`, await noOverflow(page))
  if (width === 1440) {
    ck('1440: the header carries the switcher too', await page.getByTestId('linked-club-switcher').first().isVisible())
  }
  if (width === 390) {
    await page.screenshot({ path: `${SHOTS}/club-links-dashboard-390.png` }).catch(() => {})
  }

  // Switch to Bravo with the panel.
  await buttons.nth(1).click()
  await page.waitForURL(/\/admin\/?$/, { timeout: 15000 }).catch(() => {})
  await wait(page)
  const sw = state.calls.filter(c => c.p === '/auth/switch-club')
  ck(`${width}: the click sends exactly one switch request for that club`,
    sw.length === 1 && sw[0].method === 'POST' && JSON.stringify(sw[0].body) === '{"club_id":"c2"}', JSON.stringify(sw))
  const banner = page.getByTestId('linked-club-banner')
  await banner.waitFor({ timeout: 10000 }).catch(() => {})
  ck(`${width}: after the reload a banner says which club they are in`,
    (await banner.count()) === 1 && /WORKING IN/.test(await banner.innerText()) && /BRAVO CC/.test(await banner.innerText()),
    (await banner.count()) ? await banner.innerText() : 'no banner')
  ck(`${width}: the panel now marks the other club`,
    (await page.getByTestId('linked-clubs-card').getByRole('button').nth(1).getAttribute('aria-pressed')) === 'true')
  ck(`${width}: the long club name does not overflow`, await inside(page, '[data-testid="linked-clubs-card"]'))
  if (width !== 768) ck(`${width}: still no sideways scroll`, await noOverflow(page))
  if (width === 390) await page.screenshot({ path: `${SHOTS}/club-links-switched-390.png` }).catch(() => {})

  // And back, with the banner's link: the home club is sent as null.
  await banner.getByRole('button').click()
  await page.waitForFunction(() => !document.querySelector('[data-testid="linked-club-banner"]'), null, { timeout: 15000 }).catch(() => {})
  await wait(page)
  const back = state.calls.filter(c => c.p === '/auth/switch-club').pop()
  ck(`${width}: going back sends null for the home club`, JSON.stringify(back?.body) === '{"club_id":null}', JSON.stringify(back))
  ck(`${width}: the banner is gone again`, (await page.getByTestId('linked-club-banner').count()) === 0)
  ck(`${width}: no page errors`, errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── The header dropdown (desktop) and the drawer (phone) ───────────────────
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  const state = makeState()
  await stub(page, state)
  await page.goto(`${BASE}/admin`)
  await wait(page)
  await page.getByTestId('linked-club-switcher').first().click()
  const opts = page.getByRole('option')
  await opts.first().waitFor({ timeout: 5000 }).catch(() => {})
  ck('header dropdown lists both clubs', (await opts.count()) === 2, `${await opts.count()}`)
  ck('the current club is selected and cannot be re-picked',
    (await opts.nth(0).getAttribute('aria-selected')) === 'true' && await opts.nth(0).isDisabled())
  await opts.nth(1).click()
  await page.waitForTimeout(600)
  const sw = state.calls.filter(c => c.p === '/auth/switch-club')
  ck('picking from the dropdown sends the same request', sw.length === 1 && JSON.stringify(sw[0].body) === '{"club_id":"c2"}', JSON.stringify(sw))
  await ctx.close()
}
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 800 } })
  const page = await ctx.newPage()
  const state = makeState()
  await stub(page, state)
  await page.goto(`${BASE}/admin`)
  await wait(page)
  await page.locator('button.md\\:hidden').first().click()
  const sw = page.getByTestId('linked-club-switcher')
  await sw.first().waitFor({ timeout: 5000 }).catch(() => {})
  const vis = []
  for (let i = 0; i < await sw.count(); i++) vis.push(await sw.nth(i).isVisible())
  ck('phone: the drawer has the switcher', vis.includes(true), JSON.stringify(vis))
  await ctx.close()
}

// ── Not linked: nothing at all ─────────────────────────────────────────────
for (const [label, over] of [
  ['an unlinked Club Admin', { linked: false }],
  ['a club member', { role: 'club_member', linked: true }],
]) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  const state = makeState(over)
  await stub(page, state)
  await page.goto(`${BASE}/admin`)
  await wait(page)
  await page.waitForTimeout(400)
  ck(`${label}: no Your clubs panel`, (await page.getByTestId('linked-clubs-card').count()) === 0)
  ck(`${label}: no header switcher`, (await page.getByTestId('linked-club-switcher').count()) === 0)
  ck(`${label}: no banner`, (await page.getByTestId('linked-club-banner').count()) === 0)
  ck(`${label}: nothing asked the server to switch`, !state.calls.some(c => c.p === '/auth/switch-club'))
  await ctx.close()
}

// ── The server refuses: the admin is told, and stays where they are ────────
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 800 } })
  const page = await ctx.newPage()
  const state = makeState({ refuseSwitch: true })
  await stub(page, state)
  await page.goto(`${BASE}/admin`)
  await wait(page)
  await page.getByTestId('linked-clubs-card').getByRole('button').nth(1).click()
  const alert = page.getByTestId('linked-clubs-card').getByRole('alert')
  await alert.waitFor({ timeout: 5000 }).catch(() => {})
  ck('a refused switch shows the reason', (await alert.count()) === 1 && /not linked/.test(await alert.innerText()))
  ck('and the buttons work again', !(await page.getByTestId('linked-clubs-card').getByRole('button').nth(1).isDisabled()))
  ck('and the admin is still in their club', (await page.getByTestId('linked-club-banner').count()) === 0)
  await ctx.close()
}

// ── Super Admin page ───────────────────────────────────────────────────────
for (const width of [1440, 390]) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  const state = makeState({ role: 'super_admin' })
  await stub(page, state)
  await page.goto(`${BASE}/admin/super/club-links`)
  await page.getByRole('heading', { name: 'Linked clubs' }).waitFor({ timeout: 15000 })
  ck(`${width}: super page says nothing is linked yet`, await page.getByText('No clubs are linked yet.').count() === 1)
  const link = page.getByRole('button', { name: 'LINK CLUBS' })
  ck(`${width}: Link is off until two clubs are chosen`, await link.isDisabled())
  await page.selectOption('#club-link-a', 'c1')
  ck(`${width}: still off with one`, await link.isDisabled())
  const bOpts = await page.locator('#club-link-b option').allInnerTexts()
  ck(`${width}: the first club is not offered as its own partner`, !bOpts.some(t => t.startsWith('Alpha')), JSON.stringify(bOpts))
  await page.selectOption('#club-link-b', 'c2')
  ck(`${width}: on with two different clubs`, !(await link.isDisabled()))
  await link.click()
  await page.getByTestId('club-link-group').first().waitFor({ timeout: 5000 }).catch(() => {})
  const post = state.calls.filter(c => c.method === 'POST' && c.p === '/club-admin/super/club-links')
  ck(`${width}: Link sends exactly the two club ids`, post.length === 1 && JSON.stringify(post[0].body) === '{"club_a_id":"c1","club_b_id":"c2"}', JSON.stringify(post))
  ck(`${width}: the new group is listed with both clubs`, (await page.getByTestId('club-link-group').count()) === 1
    && /Alpha CC/.test(await page.getByTestId('club-link-group').innerText()) && /Bravo CC/.test(await page.getByTestId('club-link-group').innerText()))
  ck(`${width}: and says what happened`, /are linked/.test(await page.getByRole('status').innerText()))
  const afterLink = await page.locator('#club-link-a option').allInnerTexts()
  ck(`${width}: linked clubs are marked in the pickers`, afterLink.some(t => /already linked/.test(t)), JSON.stringify(afterLink))

  // Unlink needs a second click.
  await page.getByRole('button', { name: 'UNLINK' }).first().click()
  ck(`${width}: Unlink asks first and sends nothing yet`, !state.calls.some(c => c.method === 'DELETE')
    && (await page.getByRole('button', { name: 'CONFIRM UNLINK' }).count()) === 1)
  await page.getByRole('button', { name: 'CANCEL' }).click()
  ck(`${width}: Cancel backs out without a request`, !state.calls.some(c => c.method === 'DELETE'))
  await page.getByRole('button', { name: 'UNLINK' }).first().click()
  await page.getByRole('button', { name: 'CONFIRM UNLINK' }).click()
  await page.getByText('No clubs are linked yet.').waitFor({ timeout: 5000 }).catch(() => {})
  const del = state.calls.filter(c => c.method === 'DELETE')
  ck(`${width}: Confirm sends one DELETE for that club`, del.length === 1 && del[0].p === '/club-admin/super/club-links/c1', JSON.stringify(del))
  ck(`${width}: the group is gone from the list`, (await page.getByTestId('club-link-group').count()) === 0)
  if (width !== 768) ck(`${width}: no sideways scroll on the super page`, await noOverflow(page))
  if (width === 390) await page.screenshot({ path: `${SHOTS}/club-links-super-390.png` }).catch(() => {})
  ck(`${width}: no page errors`, errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
