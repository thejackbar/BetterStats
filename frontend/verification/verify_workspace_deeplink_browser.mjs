// The Sales Workspace's ?club= deep link, against the real screen with the
// API stubbed at the network layer. The reported failure is a linked club
// that the queue's CURRENT filters exclude; the three cases after it are the
// behaviours the auto-advance/first-load branches exist for, which the fix
// must not have traded away.
//
//   node verify_workspace_deeplink_browser.mjs   (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const OUTSIDE = '267a9c6d-3f79-4529-ba81-3850c4f7a74b'
const Q1 = 'aaaaaaaa-0000-0000-0000-000000000001'
const Q2 = 'aaaaaaaa-0000-0000-0000-000000000002'
const NAMES = { [OUTSIDE]: 'Outside Filters CC', [Q1]: 'Aardvark CC', [Q2]: 'Zebra CC' }

const pass = [], fail = []
const check = (n, c, d = '') => { (c ? pass : fail).push(n); console.log((c ? '  ok   ' : '  FAIL ') + n + (!c && d ? `  [${d}]` : '')) }

const club = (id) => ({
  id, title: NAMES[id], marketing_club_name: NAMES[id], marketing_club_suburb: null,
  marketing_club_state: 'VIC', marketing_club_associations: [], stage_name: 'Trial',
  owner_name: 'Sam Barendse', engagement_score: 10, engagement_tier: 'WARM',
  contact_count: 1, ever_called: false, callback_due: false, last_call: null,
  priority_score: 5, module_keys: ['core'], not_interested: false,
})
const drawerFor = (id) => ({
  deal: { ...club(id), product_interest_source: 'manual', stage_id: 's1',
          value_cents: 39900, owner_user_id: 'sam' },
  contacts: [], activities: [], events: [], lists: [], stages: [], boundary: null,
})

const mount = async (ctx, queueIds) => {
  const page = await ctx.newPage()
  const drawerFetches = []
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) {
      return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'super_admin',
                    entitlements: { modules: [], status: 'active' } })
    }
    if (/\/sales-workspace\/clubs(\?|$)/.test(url)) {
      return json({ clubs: queueIds.map(club), stages: [{ id: 's1', key: 'trial', name: 'Trial' }] })
    }
    const m = url.match(/\/sales-workspace\/clubs\/([0-9a-f-]{36})(\/|\?|$)/)
    if (m) {
      if (/\/signals|\/boundary/.test(url)) return json({})
      drawerFetches.push(m[1])
      return json(drawerFor(m[1]))
    }
    if (url.includes('/email-templates')) return json({ templates: [] })
    if (url.includes('/call-outcomes')) return json({ outcomes: [] })
    return json({})
  })
  return { page, drawerFetches, errors }
}

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
  await ctx.addInitScript(() => localStorage.setItem('token', 'stub'))

  // 1. The reported case.
  {
    const { page, drawerFetches, errors } = await mount(ctx, [Q1, Q2])
    await page.goto(`${BASE}/admin/super/crm/workspace?club=${OUTSIDE}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2200)
    const body = await page.innerText('body')
    check('a deep-linked club outside the current filters is the one that opens',
          body.includes('Outside Filters CC'), body.slice(0, 120))
    check('…and the queue never reassigns the selection to row one',
          !drawerFetches.includes(Q1), drawerFetches.join(','))
    check('…and the URL still names the club that was asked for',
          page.url().includes(OUTSIDE), page.url())
    check('no page errors', errors.length === 0, errors[0] || '')
    await page.close()
  }

  // 2. A deep link to a club that IS in the queue — unchanged.
  {
    const { page, drawerFetches } = await mount(ctx, [Q1, Q2])
    await page.goto(`${BASE}/admin/super/crm/workspace?club=${Q2}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2200)
    check('a deep link to a club inside the queue still opens that club',
          (await page.innerText('body')).includes('Zebra CC') && !drawerFetches.includes(Q1),
          drawerFetches.join(','))
    await page.close()
  }

  // 3. No deep link — the first-load landing this branch exists for.
  {
    const { page, drawerFetches } = await mount(ctx, [Q1, Q2])
    await page.goto(`${BASE}/admin/super/crm/workspace`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2200)
    check('with no deep link the screen still lands on the top of the queue',
          drawerFetches[0] === Q1, drawerFetches.join(','))
    await page.close()
  }

  // 4. Picking a club by hand releases the pin, so the ordinary
  //    advance-past-a-dropped-out-club behaviour comes back.
  {
    const { page, drawerFetches } = await mount(ctx, [Q1, Q2])
    await page.goto(`${BASE}/admin/super/crm/workspace?club=${OUTSIDE}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2000)
    await page.getByText('Zebra CC').first().click()
    await page.waitForTimeout(1200)
    check('picking a club from the queue by hand takes over from the deep link',
          drawerFetches[drawerFetches.length - 1] === Q2, drawerFetches.join(','))
    check('…and the URL follows it', page.url().includes(Q2), page.url())
    await page.close()
  }

  await browser.close()
  console.log(`\n${pass.length} passed, ${fail.length} failed`)
  if (fail.length) process.exit(1)
}
run().catch(e => { console.error(e); process.exit(1) })
