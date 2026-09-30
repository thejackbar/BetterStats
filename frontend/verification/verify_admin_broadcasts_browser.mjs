// Drives the real club admin dashboard and the Better HQ composer in Chromium,
// with the API stubbed at the network layer.
//
//   npx vite --port 5199 &
//   node verification/verify_admin_broadcasts_browser.mjs [baseUrl]
//
// Asked for: a super admin sends a one-line message to club admins, shown near
// the top of the club admin dashboard, and it has to work on every device. So
// the checks measure the message's position against the page heading, its
// order, what each rule lets a recipient do, what goes over the wire, and the
// layout at phone, tablet and desktop widths.
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const CLUB = { id: 'c1', name: 'Alpha CC', slug: 'alpha' }
const LONG = 'Season 2026/27 fees are now open in BetterAdmin and every club needs to review its fee schedule before the first round, including https://betterat.cricket/help/articles/a-very-long-url-that-must-wrap-on-a-phone-screen-without-pushing-the-page-sideways'
const MESSAGES = [
  { id: 'b-info', message: LONG, tone: 'info', link_url: null, link_label: null, persistence: 'dismissible', dismissible: true },
  { id: 'b-crit', message: 'Scheduled maintenance tonight 9-10pm AWST.', tone: 'critical', link_url: '/admin/account', link_label: 'Your plan', persistence: 'until_cleared', dismissible: false },
  { id: 'b-once', message: 'Welcome to the new dashboard.', tone: 'success', link_url: 'https://betterat.cricket/videos', link_label: 'Watch', persistence: 'view_once_user', dismissible: true },
]
// The server orders them; the stub hands them over the way it would.
const ORDERED = [MESSAGES[1], MESSAGES[0], MESSAGES[2]]

const AUDIENCE = {
  clubs: [
    { id: 'c1', name: 'Alpha CC', slug: 'alpha', users: [
      { id: 'u1', name: 'Pat Primary', role: 'club_admin', is_primary: true, email: 'pat@a.test' },
      { id: 'u2', name: 'Alex Admin', role: 'club_admin', is_primary: false, email: 'alex@a.test' },
      { id: 'u3', name: 'Mel Member', role: 'club_member', is_primary: false, email: 'mel@a.test' },
    ] },
    { id: 'c2', name: 'Bravo CC', slug: 'bravo', users: [
      { id: 'u4', name: 'Bo Bravo', role: 'club_admin', is_primary: true, email: 'bo@b.test' },
    ] },
  ],
}

function makeState({ role = 'club_admin', items = ORDERED, preview = false } = {}) {
  return { role, items, preview, calls: [], list: [] }
}

async function stub(page, state) {
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    const method = req.method()
    const body = req.postData() ? JSON.parse(req.postData()) : null
    state.calls.push({ method, p, body })
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p === '/auth/me') {
      return json({
        id: 'u1', username: 'pat', display_name: 'Pat', role: state.role, club_id: CLUB.id,
        club_slug: CLUB.slug, is_primary_admin: true, can_switch_clubs: state.role === 'super_admin',
        entitlements: { modules: ['select'], status: 'active', billing_modules: [] }, capabilities: [],
      })
    }
    if (p === '/club-admin/broadcasts' && method === 'GET') return json({ items: state.items, preview: state.preview })
    if (p === '/club-admin/broadcasts/seen') return json({ recorded: body.ids.length })
    if (/\/club-admin\/broadcasts\/[^/]+\/dismiss/.test(p)) return json({ dismissed: true })
    if (p === '/club-admin/settings') return json({ name: CLUB.name, slug: CLUB.slug })
    if (p === '/club-admin/seasons') return json([])
    if (p === '/club-admin/account/plan') return json({ modules: [] })
    if (p === '/club-admin/super/broadcasts/audience') return json(AUDIENCE)
    if (p === '/club-admin/super/broadcasts' && method === 'GET') return json({ items: state.list })
    if (p === '/club-admin/super/broadcasts' && method === 'POST') {
      const row = {
        id: 'new1', ...body, dismissible: body.persistence !== 'until_cleared', status: 'live',
        club_names: (body.org_ids || []).map(id => AUDIENCE.clubs.find(c => c.id === id)?.name),
        user_names: [], recipients: 1, clubs: 1, seen: 0, dismissed: 0, clubs_seen: 0,
        created_by: 'Staff', created_at: new Date().toISOString(), cleared_at: null,
      }
      state.list = [row, ...state.list]
      return json(row, 201)
    }
    if (/\/club-admin\/super\/broadcasts\/[^/]+\/clear/.test(p)) {
      const id = p.split('/')[4]
      state.list = state.list.map(r => (r.id === id ? { ...r, status: 'cleared', cleared_at: new Date().toISOString() } : r))
      return json(state.list.find(r => r.id === id))
    }
    return json({ detail: 'not stubbed' }, 404)
  })
}

const noOverflow = page => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)
// The dashboard's own module tiles already run 7px over at 768px, with or
// without a message (measured with the messages stubbed empty), so the
// dashboard check is scoped to the messages themselves.
const messagesInside = page => page.evaluate(() => {
  const cw = document.documentElement.clientWidth
  const sec = document.querySelector('section[aria-label="Messages from BetterCricket"]')
  return !!sec && [sec, ...sec.querySelectorAll('*')].every(e => e.getBoundingClientRect().right <= cw + 1)
})

const browser = await chromium.launch({ executablePath: EXECUTABLE })

// ── Dashboard ──────────────────────────────────────────────────────────────
for (const width of [1440, 768, 390]) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  const state = makeState()
  await stub(page, state)
  await page.goto(`${BASE}/admin`)
  const lines = page.getByTestId('admin-broadcast')
  await lines.first().waitFor({ timeout: 15000 }).catch(() => {})
  const n = await lines.count()
  ck(`${width}: all three messages drawn`, n === 3, `got ${n}`)
  if (n === 3) {
    const first = await lines.nth(0).innerText()
    ck(`${width}: the most urgent comes first`, /maintenance/i.test(first) && /important/i.test(first), first.slice(0, 80))
    const h1 = await page.locator('h1').filter({ hasText: /Welcome/ }).boundingBox()
    const top = await lines.nth(0).boundingBox()
    ck(`${width}: the messages sit above the page heading`, h1 && top && top.y < h1.y, `${top?.y} vs ${h1?.y}`)
    ck(`${width}: and in the first screenful`, top && top.y < 400, `${top?.y}`)
    const crit = lines.nth(0)
    ck(`${width}: an until-cleared message has no close button`, (await crit.getByRole('button').count()) === 0)
    ck(`${width}: an in-app link is a real link`, (await crit.locator('a[href="/admin/account"]').count()) === 1)
    const once = lines.nth(2)
    ck(`${width}: an outside link opens in a new tab`,
      (await once.locator('a[href="https://betterat.cricket/videos"][target="_blank"]').count()) === 1)
    const close = lines.nth(1).getByRole('button', { name: 'Dismiss this message' })
    const cb = await close.boundingBox()
    ck(`${width}: the close button is a finger-sized target`, cb && cb.width >= 36 && cb.height >= 36, JSON.stringify(cb))
    for (let i = 0; i < 3; i++) {
      const b = await lines.nth(i).boundingBox()
      ck(`${width}: message ${i + 1} fits inside the viewport`, b && b.x >= 0 && b.x + b.width <= width + 1, JSON.stringify(b))
    }
    ck(`${width}: nothing in the messages runs past the screen edge`, await messagesInside(page))
    if (width !== 768) ck(`${width}: nothing pushes the page sideways`, await noOverflow(page))
    await page.waitForTimeout(300)
    const seen = state.calls.filter(c => c.p === '/club-admin/broadcasts/seen')
    ck(`${width}: the dashboard reports what it showed, once`, seen.length === 1 &&
      JSON.stringify([...seen[0].body.ids].sort()) === JSON.stringify(['b-crit', 'b-info', 'b-once']),
      JSON.stringify(seen.map(s => s.body)))
    await close.click()
    await page.waitForTimeout(200)
    ck(`${width}: closing hides it`, (await lines.count()) === 2)
    ck(`${width}: and tells the server`, state.calls.some(c => c.method === 'POST' && c.p === '/club-admin/broadcasts/b-info/dismiss'))
    if (width === 390) await page.screenshot({ path: '/tmp/claude-0/broadcast-390.png', fullPage: false }).catch(() => {})
  }
  ck(`${width}: no page errors`, errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// No messages: nothing drawn at all.
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 800 } })
  const page = await ctx.newPage()
  const state = makeState({ items: [] })
  await stub(page, state)
  await page.goto(`${BASE}/admin`)
  await page.locator('h1').filter({ hasText: /Welcome/ }).waitFor({ timeout: 15000 })
  await page.waitForTimeout(400)
  ck('no messages draws nothing', (await page.getByTestId('admin-broadcast').count()) === 0)
  ck('and reports nothing', !state.calls.some(c => c.p === '/club-admin/broadcasts/seen'))
  await ctx.close()
}

// A super admin acting as the club sees a preview and records nothing.
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  const state = makeState({ role: 'super_admin', preview: true,
    items: [{ ...MESSAGES[1], preview: true, audience: 'all', audience_roles: 'all_admins' }] })
  await stub(page, state)
  await page.goto(`${BASE}/admin`)
  const line = page.getByTestId('admin-broadcast')
  await line.first().waitFor({ timeout: 15000 }).catch(() => {})
  ck('a preview says it is a preview', /preview/i.test(await line.first().innerText().catch(() => '')))
  ck('and can be hidden from the screen', (await line.first().getByRole('button').count()) === 1)
  await page.waitForTimeout(300)
  ck('a preview reports nothing seen', !state.calls.some(c => c.p === '/club-admin/broadcasts/seen'))
  await line.first().getByRole('button').click().catch(() => {})
  await page.waitForTimeout(200)
  ck('and hiding a preview sends nothing', !state.calls.some(c => /dismiss/.test(c.p)))
  await ctx.close()
}

// ── Composer ───────────────────────────────────────────────────────────────
for (const width of [1280, 390]) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('dialog', d => d.accept())
  const state = makeState({ role: 'super_admin' })
  await stub(page, state)
  await page.goto(`${BASE}/admin/super/broadcasts`)
  await page.getByRole('button', { name: 'New message' }).click({ timeout: 15000 })
  const comp = page.getByTestId('broadcast-composer')
  await comp.locator('textarea').fill('Ground closures this weekend.')
  await comp.getByRole('button', { name: 'Heads up' }).click()
  ck(`${width}: the preview follows the message`, /ground closures/i.test(await comp.getByTestId('admin-broadcast').innerText()))
  ck(`${width}: every club reaches all four admins`, /Reaches 4 people at 2 clubs/.test(await comp.getByTestId('broadcast-reach').innerText()))
  await comp.getByRole('button', { name: 'Chosen clubs' }).click()
  await comp.getByPlaceholder('Search clubs…').fill('bra')
  await comp.locator('label', { hasText: 'Bravo CC' }).locator('input').check()
  ck(`${width}: the reach follows the pick`, /Reaches 1 person at 1 club/.test(await comp.getByTestId('broadcast-reach').innerText()))
  await comp.getByRole('button', { name: 'Chosen users' }).click()
  await comp.getByPlaceholder(/Search a club/).fill('mel')
  await comp.locator('label', { hasText: 'Mel Member' }).locator('input').check()
  ck(`${width}: a named person counts once`, /Reaches 1 person at 1 club/.test(await comp.getByTestId('broadcast-reach').innerText()))
  await comp.getByRole('button', { name: 'Chosen clubs' }).click()
  const selects = comp.locator('select')
  await comp.getByLabel('Which admins at each club').selectOption('primary')
  await comp.getByLabel('Stays until').selectOption('view_once_club')
  await comp.getByLabel('Stops').selectOption('72')
  ck(`${width}: the composer does not push the page sideways`, await noOverflow(page))
  await comp.getByRole('button', { name: 'Send message' }).click()
  await page.waitForTimeout(400)
  const post = state.calls.find(c => c.method === 'POST' && c.p === '/club-admin/super/broadcasts')
  ck(`${width}: the message goes over the wire`, !!post)
  if (post) {
    const b = post.body
    ck(`${width}: with exactly what was chosen`, b.message === 'Ground closures this weekend.' && b.tone === 'warning'
      && b.audience === 'clubs' && JSON.stringify(b.org_ids) === '["c2"]' && b.user_ids.length === 0
      && b.audience_roles === 'primary' && b.persistence === 'view_once_club', JSON.stringify(b))
    const hours = (new Date(b.expires_at) - new Date(b.starts_at)) / 3600e3
    ck(`${width}: and a stop time three days after the start`, Math.abs(hours - 72) < 0.01, String(hours))
  }
  const row = page.getByTestId('broadcast-row').first()
  await row.waitFor({ timeout: 5000 }).catch(() => {})
  ck(`${width}: the new message is listed`, /ground closures/i.test(await row.innerText().catch(() => '')))
  await row.getByRole('button', { name: 'Clear now' }).click().catch(() => {})
  await page.waitForTimeout(300)
  ck(`${width}: clear now reaches the server`, state.calls.some(c => c.p === '/club-admin/super/broadcasts/new1/clear'))
  ck(`${width}: the list stops showing it as current`, (await page.getByTestId('broadcast-row').count()) === 0)
  ck(`${width}: no page errors`, errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
