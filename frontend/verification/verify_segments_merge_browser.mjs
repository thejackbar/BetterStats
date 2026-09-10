// BetterComms Lists → Segments merge, against the REAL Segments screens with
// the API stubbed at the network layer.
//
// Lists were folded into Segments: a segment now carries an ACTIVE rule AND a
// frozen STATIC hand-picked set, and the audience is the union of the two. What
// is asserted:
//   * both labelled sections — "Active rules (live)" and "Static members
//     (fixed)" — render on the club screen;
//   * the Active / Static / combined badge reads the right kind per segment;
//   * a saved segment carrying static members sends `static_member_ids` on the
//     /segments/resolve wire (the union goes to the server, not just the rules);
//   * the CLUB builder offers only club fields — the directory-only fields
//     (Engagement score, Sales pipeline stage) never leak in;
//   * the INTERNAL builder (acting as the outreach org) DOES offer them;
//   * /admin/comms/lists redirects to /admin/comms/segments;
//   * there is no "Lists" nav item;
//   * no horizontal overflow at 390px.
//
//   node verify_segments_merge_browser.mjs   (BASE via APP_URL, default :5178)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5178'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

// A contact row (services/directory + routers/comms _contact_out shape).
const CONTACT = {
  id: 'c1', name: 'Amardeep Gill', email: 'a@x.com', source: 'member',
  subscribed: true, suppressed: false, club: null, state: null, player_id: 'pl1', member_id: 'm1',
}
// Three saved segments: a rule-only (Active), a static-only (Static), and both.
const SEGMENTS = [
  { id: 's_rule', name: 'Rule seg', source: 'manual', origin: null, member_count: 0,
    definition: { match: 'all', rules: [{ field: 'mem_squad', op: 'eq', value: ['sq1'] }] } },
  { id: 's_static', name: 'Static seg', source: 'manual', origin: null, member_count: 1,
    definition: { match: 'all', rules: [] } },
  { id: 's_both', name: 'Both seg', source: 'manual', origin: null, member_count: 1,
    definition: { match: 'all', rules: [{ field: 'mem_squad', op: 'eq', value: ['sq1'] }] } },
]
const MEMBERS_BY_SEG = { s_rule: [], s_static: [CONTACT], s_both: [CONTACT] }

// Whether /auth/me presents as BetterCricket's outreach org (internal builder)
// or a club (club builder). Flipped between the two runs.
let INTERNAL = false

const routes = (page, calls) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url()
  calls.push({ url, method: req.method(), body: req.postData() })
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

  if (url.includes('/auth/me')) {
    return json({
      id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      can_switch_clubs: INTERNAL, is_marketing_org: INTERNAL,
      entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' },
    })
  }
  if (/\/comms\/segments\/options/.test(url)) {
    // Club vocab; the internal screen ignores it (its fields carry their own
    // options). Never any directory options here.
    return json({
      roles: ['Batter'], genders: [['male', 'Male'], ['female', 'Female']], teams: [],
      membership_types: [{ id: 'mt1', name: 'Senior Player' }], membership_tiers: [],
      squads: [{ id: 'sq1', name: '1st XI' }], club_roles: [['volunteer', 'Volunteer']],
      honours: [['life_member', 'Life member']],
    })
  }
  let m
  if ((m = url.match(/\/comms\/segments\/([^/]+)\/size/))) return json({ count: 3 })
  if ((m = url.match(/\/comms\/segments\/([^/]+)\/members/)) && req.method() === 'GET') {
    return json(MEMBERS_BY_SEG[m[1]] || [])
  }
  if (/\/comms\/segments\/resolve/.test(url) || /\/comms\/segments\/preview/.test(url)) {
    return json({ count: 1, contacts: [CONTACT], reachable: 1, other_route: 0, clubs: 0 })
  }
  if (/\/comms\/segments$/.test(url) && req.method() === 'GET') return json(SEGMENTS)
  if (/\/comms\/contacts/.test(url)) return json({ contacts: [CONTACT] })
  if (/\/comms\/context/.test(url)) return json({ current: { is_marketing: INTERNAL } })
  if (/\/notifications\/(count|summary)/.test(url)) return json({ unseen_count: 0, items: [] })
  // Anything else the layout pokes at.
  return json({})
})

const noOverflow = (page) => page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth)

// The option labels in the RuleBuilder's field <select> (the first select under
// the "Active rules (live)" heading).
const fieldOptions = (page) => page.evaluate(() => {
  const heads = [...document.querySelectorAll('*')].filter(
    el => (el.textContent || '').trim() === 'Active rules (live)' && el.children.length === 0)
  // The rule rows sit after the Active heading; grab every field select's
  // option text on the page (the field select is the one offering 'Has tag').
  const sels = [...document.querySelectorAll('select')]
  for (const s of sels) {
    const opts = [...s.options].map(o => o.textContent.trim())
    if (opts.includes('Has tag')) return opts
  }
  return null
})

async function openSegments(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const calls = [], errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page, calls)
  return { ctx, page, calls, errors }
}

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })

  // ── The club builder ────────────────────────────────────────────────────
  INTERNAL = false
  {
    const { page, calls, errors } = await openSegments(browser)
    await page.goto(BASE + '/admin/comms/segments', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(1500)

    const body = await page.textContent('body')
    check('the Active rules section is labelled', body.includes('Active rules (live)'))
    check('the Static members section is labelled', body.includes('Static members (fixed)'))

    // Read the ONE badge element (a leaf whose exact text is one of the three
    // kind labels), rather than scanning the whole body — "Static" also appears
    // in the section heading, so a body scan cannot tell the badges apart.
    const LABELS = ['Active — with hand-picked additions', 'Active', 'Static', 'Empty']
    const readBadge = async (name) => {
      await page.click(`text=${name}`)
      await page.waitForTimeout(700)
      return page.evaluate((labels) => {
        for (const el of document.querySelectorAll('span, div')) {
          if (el.children.length === 0 && labels.includes((el.textContent || '').trim())) {
            return el.textContent.trim()
          }
        }
        return null
      }, LABELS)
    }
    check('a rule-only segment reads "Active"', (await readBadge('Rule seg')) === 'Active')
    check('a static-only segment reads "Static"', (await readBadge('Static seg')) === 'Static')
    check('a segment with rules AND members reads the combined badge',
      (await readBadge('Both seg')) === 'Active — with hand-picked additions')

    // Selecting a segment with static members sends the union on the resolve
    // wire: the request body carries static_member_ids AND the definition rules.
    await page.click('text=Both seg')
    await page.waitForTimeout(900)
    const resolveCalls = calls.filter(c => /\/comms\/segments\/resolve/.test(c.url) && c.body)
    const withStatic = resolveCalls.some(c => {
      try {
        const b = JSON.parse(c.body)
        return Array.isArray(b.static_member_ids) && b.static_member_ids.includes('c1')
          && (b.definition?.rules || []).length > 0
      } catch { return false }
    })
    check('resolve sends the union (static_member_ids + rules) on the wire', withStatic,
      JSON.stringify(resolveCalls.map(c => c.body).slice(-2)))

    // Club scope: the field select offers club fields, never directory ones.
    const opts = await fieldOptions(page)
    check('the club builder offers club member fields', !!opts
      && opts.includes('Membership type') && opts.includes('Squad'), JSON.stringify(opts))
    check('the club builder does NOT leak directory fields', !!opts
      && !opts.includes('Engagement score') && !opts.includes('Sales pipeline stage'),
      JSON.stringify(opts))

    // No Lists nav item anywhere; Segments is present.
    const listsNav = await page.$('a[href="/admin/comms/lists"]')
    const segNav = await page.$('a[href="/admin/comms/segments"]')
    check('there is no Lists nav item', listsNav === null)
    check('the Segments nav item is present', segNav !== null)

    check('no page errors on the club Segments screen', errors.length === 0, errors.join('; '))
  }

  // ── /admin/comms/lists redirects ────────────────────────────────────────
  {
    const { page } = await openSegments(browser)
    await page.goto(BASE + '/admin/comms/lists', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1500)
    check('/admin/comms/lists redirects to /admin/comms/segments',
      page.url().endsWith('/admin/comms/segments'), page.url())
  }

  // ── The internal builder shows directory fields ─────────────────────────
  INTERNAL = true
  {
    const { page, errors } = await openSegments(browser)
    await page.goto(BASE + '/admin/comms/segments', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(1500)
    const opts = await fieldOptions(page)
    check('the internal builder offers the directory fields', !!opts
      && opts.includes('Engagement score'), JSON.stringify(opts))
    check('no page errors on the internal Segments screen', errors.length === 0, errors.join('; '))
  }

  // ── No overflow at 390px ────────────────────────────────────────────────
  INTERNAL = false
  {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 800 } })
    await ctx.addInitScript(() => {
      localStorage.setItem('token', 'stub')
      localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
      localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
    })
    const page = await ctx.newPage()
    const calls = []
    await routes(page, calls)
    await page.goto(BASE + '/admin/comms/segments', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('h1', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(1500)
    const ov = await noOverflow(page)
    check('no horizontal overflow at 390px', ov <= 1, `overflow ${ov}px`)
    await ctx.close()
  }

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}

run().catch(e => { console.error(e); process.exit(2) })
