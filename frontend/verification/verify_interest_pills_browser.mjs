// The "Interested in" pills on the Sales Workspace, against the real screen
// with the API stubbed at the network layer. A deal has to be for at least
// one module, so the last one standing must not be unpickable — and the
// screen has to refuse it without sending a request the server would reject.
//
//   node verify_interest_pills_browser.mjs   (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const CLUB = 'aaaaaaaa-0000-0000-0000-000000000001'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

let modules = ['core', 'iq']
const PRICE = { core: 39900, iq: 24900, select: 14900 }
const value = (keys) => keys.reduce((t, k) => t + (PRICE[k] || 0), 0)

const row = () => ({
  id: CLUB, title: 'Test CC', marketing_club_name: 'Test CC', marketing_club_suburb: null,
  marketing_club_state: 'VIC', marketing_club_associations: [], stage_name: 'Trial',
  owner_name: 'Sam', engagement_score: 10, engagement_tier: 'WARM', contact_count: 0,
  ever_called: false, callback_due: false, last_call: null, priority_score: 5,
  module_keys: modules, not_interested: false,
})
const drawer = () => ({
  deal: { ...row(), product_interest_source: 'manual', stage_id: 's1',
          value_cents: value(modules), owner_user_id: 'sam' },
  contacts: [], activities: [], events: [], lists: [], stages: [], boundary: null,
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
      return json({ clubs: [row()], stages: [{ id: 's1', key: 'trial', name: 'Trial' }] })
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

  check('no page errors', errors.length === 0, errors[0] || '')

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) process.exit(1)
}
run().catch(e => { console.error(e); process.exit(1) })
