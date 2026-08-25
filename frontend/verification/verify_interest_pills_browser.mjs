// The "Interested in" pills on the Sales Workspace, against the real screen
// with the API stubbed at the network layer. A deal has to be for at least
// one module, so the last one standing must not be unpickable — and the
// screen has to refuse it without sending a request the server would reject.
//
// It also asserts that picking a pill does not MOVE the page. These pills sit
// down the detail pane, and the queue reload the toggle fires used to
// re-anchor the open club's rail row, scrolling the document and taking the
// pane the rep is reading with it. Measured off window.scrollY either side of
// the click, with the pane made tall enough (a real timeline) for there to be
// somewhere to scroll from.
//
//   node verify_interest_pills_browser.mjs   (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const CLUB = 'aaaaaaaa-0000-0000-0000-000000000001'
// The open club sits well down a real queue, which is what puts its rail row
// out of view once the rep scrolls to the pills — the state the scroll bug
// needs. Row one is always on screen, so a one-club stub proves nothing.
const SEL = 20
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

let modules = ['core', 'iq']
const PRICE = { core: 39900, iq: 24900, select: 14900 }
const value = (keys) => keys.reduce((t, k) => t + (PRICE[k] || 0), 0)

const row = (i = SEL) => ({
  id: i === SEL ? CLUB : `bbbbbbbb-0000-0000-0000-${String(i).padStart(12, '0')}`,
  title: i === SEL ? 'Test CC' : `Club ${i}`,
  marketing_club_name: i === SEL ? 'Test CC' : `Club ${i}`, marketing_club_suburb: null,
  marketing_club_state: 'VIC', marketing_club_associations: [], stage_name: 'Trial',
  owner_name: 'Sam', engagement_score: 10, engagement_tier: 'WARM', contact_count: 0,
  ever_called: false, callback_due: false, last_call: null, priority_score: 5,
  module_keys: i === SEL ? modules : ['core'], not_interested: false,
})
const rows = () => Array.from({ length: 25 }, (_, i) => row(i))
// A real club's pane is long — a contact list and a call history each run to
// dozens of rows — and the scroll bug only bites once the pills sit BELOW the
// queue rail, which is where those cards push them. An empty pane keeps the
// pills level with the rail, where the row is on screen anyway and nothing
// moves: the stub has to be the shape of a real club or it proves nothing.
const contacts = Array.from({ length: 14 }, (_, i) => ({
  directory_contact_id: `c-${i}`, crm_person_id: null, name: `Contact ${i}`,
  role: 'Secretary', email: `c${i}@example.com`, mobile: '0400000000', phone: null,
  do_not_contact: false, source: 'directory',
}))
const activities = Array.from({ length: 30 }, (_, i) => ({
  id: `act-${i}`, type: 'call', outcome: 'spoke', created_at: '2026-08-01T00:00:00Z',
  body: `Called the secretary, round ${i + 1}`, actor_name: 'Sam', meta: {},
}))
const drawer = () => ({
  deal: { ...row(), product_interest_source: 'manual', stage_id: 's1',
          value_cents: value(modules), owner_user_id: 'sam' },
  contacts, activities, events: [], lists: [], stages: [], boundary: null,
})

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
  await ctx.addInitScript(() => localStorage.setItem('token', 'stub'))
  const page = await ctx.newPage()
  const errors = []
  const interestCalls = []
  const clubListCalls = []
  page.on('pageerror', e => errors.push(String(e)))

  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) {
      return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'super_admin',
                    entitlements: { modules: [], status: 'active' } })
    }
    if (/\/interest$/.test(url)) {
      const body = JSON.parse(route.request().postData() || '{}')
      interestCalls.push(body.module_keys)
      // The server's own rule, mirrored so the stub can't be more permissive
      // than the thing it stands in for.
      if (!body.module_keys?.length) {
        return route.fulfill({ status: 422, contentType: 'application/json',
          body: JSON.stringify({ detail: 'Pick at least one module — a deal has to be for something.' }) })
      }
      modules = body.module_keys
      return json(drawer())
    }
    if (/\/sales-workspace\/clubs(\?|$)/.test(url)) {
      clubListCalls.push(url)
      return json({ clubs: rows(), stages: [{ id: 's1', key: 'trial', name: 'Trial' }] })
    }
    if (/\/sales-workspace\/clubs\/[0-9a-f-]{36}/.test(url)) {
      if (/\/signals|\/boundary/.test(url)) return json({})
      return json(drawer())
    }
    if (url.includes('/email-templates')) return json({ templates: [] })
    if (url.includes('/call-outcomes')) return json({ outcomes: [] })
    return json({})
  })

  await page.goto(`${BASE}/admin/super/crm/workspace?club=${CLUB}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('text=Interested in', { timeout: 15000 })

  // The pane's own pills, not the filter bar's — scope to the drawer.
  const pill = (label) => page.locator('button', { hasText: new RegExp(`^${label}$`) }).last()

  await pill('IQ').click()
  await page.waitForTimeout(600)
  check('unpicking one of two modules is allowed',
        JSON.stringify(interestCalls[interestCalls.length - 1]) === JSON.stringify(['core']),
        JSON.stringify(interestCalls))

  const before = interestCalls.length
  await pill('Stats').click()
  await page.waitForTimeout(600)
  check('unpicking the LAST module sends nothing at all',
        interestCalls.length === before, JSON.stringify(interestCalls.slice(before)))
  check('…and the screen says why', (await page.innerText('body')).includes('at least one module'))

  // It does NOT have to be Stats: swap to a single non-Stats module.
  await pill('Select').click()
  await page.waitForTimeout(600)
  await pill('Stats').click()
  await page.waitForTimeout(600)
  check('a single non-Stats module is allowed',
        JSON.stringify(interestCalls[interestCalls.length - 1]) === JSON.stringify(['select']),
        JSON.stringify(interestCalls))

  const after = interestCalls.length
  await pill('Select').click()
  await page.waitForTimeout(600)
  check('…and that one is now the last one standing, so it holds too',
        interestCalls.length === after)

  // ---- the pane must not move under the rep ----------------------------
  // Put the pills where a rep actually uses them: scrolled down the pane,
  // with the open club's rail row off the top of the screen. Anything that
  // re-anchors that row from here drags the whole document back up.
  const pills = pill('Stats')
  await pills.scrollIntoViewIfNeeded()
  await page.evaluate(() => window.scrollBy(0, 400))
  await page.waitForTimeout(200)

  // Where the selected rail row actually sits, measured rather than assumed.
  const railRowTop = () => page.evaluate(() => {
    const rail = [...document.querySelectorAll('div')].find(
      d => typeof d.className === 'string'
        && d.className.includes('overflow-y-auto') && d.className.includes('max-h-[75vh]'))
    const sel = rail && [...rail.querySelectorAll('button')]
      .find(b => typeof b.className === 'string' && b.className.includes('border-pb-accent'))
    return sel ? sel.getBoundingClientRect().top : null
  })

  const scrollBefore = await page.evaluate(() => window.scrollY)
  const pillBoxBefore = await pills.boundingBox()
  const rowTopBefore = await railRowTop()
  check('the page is genuinely scrolled down before the click (else this proves nothing)',
        scrollBefore > 50, `scrollY=${scrollBefore}`)
  check('…and the open club\'s rail row is off screen, which is what used to drag it back',
        rowTopBefore !== null && rowTopBefore < 0, `rowTop=${rowTopBefore}`)

  const reloadsBefore = clubListCalls.length
  await pill('IQ').click()
  await page.waitForTimeout(800)

  const scrollAfter = await page.evaluate(() => window.scrollY)
  const pillBoxAfter = await pills.boundingBox()
  check('picking a module does not scroll the page',
        Math.abs(scrollAfter - scrollBefore) <= 2, `${scrollBefore} -> ${scrollAfter}`)
  check('…so the pill stays put under the cursor',
        pillBoxBefore && pillBoxAfter && Math.abs(pillBoxAfter.y - pillBoxBefore.y) <= 2,
        `${pillBoxBefore?.y} -> ${pillBoxAfter?.y}`)
  check('…and the queue is still refreshed behind it',
        clubListCalls.length > reloadsBefore,
        `${reloadsBefore} -> ${clubListCalls.length}`)

  check('no page errors', errors.length === 0, errors[0] || '')

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) process.exit(1)
}
run().catch(e => { console.error(e); process.exit(1) })
