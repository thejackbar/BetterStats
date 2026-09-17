// The Static members search/filter feeds back through the count tiles, against
// the REAL Segments screen with the API stubbed at the network layer.
//
// Reported: searching or filtering in the "Static members (fixed)" section gave
// no feedback — the "In this segment" tile stayed at the whole-segment count and
// the matching contacts were hidden until a tile was toggled, so a search read
// as "nothing found". What is asserted:
//   * with no filter, the tiles show the whole exact audience (in / not-in) and
//     the reachable/clubs line;
//   * typing a search drops the "In this segment" tile to the count MATCHING the
//     search, drops "Not in this segment" too, and shows the "out of N in the
//     segment" context line;
//   * clicking the tile then lists exactly those matching contacts;
//   * a search that matches only NON-members shows In=0 and Not-in=N — so the
//     tiles point at which list the matches are in;
//   * searching by a directory field (club) works, not just name/email;
//   * the club-admin context (no directory fields) filters by name the same way;
//   * no horizontal overflow at 390px.
//
//   node verify_static_filter_counts_browser.mjs   (BASE via APP_URL, default :5178)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5178'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const CLUBS = ['Alpha CC', 'Beta CC', 'Gamma CC']
// 40 members and 10 sendable non-members (prospects) at a club no member has.
const CONTACTS = []
for (let i = 0; i < 40; i++) CONTACTS.push({
  id: 'm' + i, name: `Member ${i}`, email: `m${i}@x.com`, source: 'directory',
  subscribed: true, suppressed: false, club: CLUBS[i % 3], state: ['WA', 'VIC', 'NSW'][i % 3],
  association: 'Assoc ' + (i % 2), country: 'Australia', utm_code: 'u' + (i % 3), marketing_club_id: 'mc' + (i % 3),
})
for (let i = 0; i < 10; i++) CONTACTS.push({
  id: 'p' + i, name: `Prospect ${i}`, email: `pr${i}@x.com`, source: 'directory',
  subscribed: true, suppressed: false, club: 'Zeta CC', state: 'SA',
  association: 'Assoc Z', country: 'Australia', utm_code: 'uz', marketing_club_id: 'mcz',
})
const MEMBER_IDS = CONTACTS.slice(0, 40).map(c => c.id)
const SEGMENTS = [{ id: 's1', name: 'Cold seg', source: 'manual', origin: null, member_count: 0,
  definition: { match: 'all', rules: [{ field: 'exported', op: 'eq', value: ['yes'] }] } }]

let INTERNAL = true
// A club with NO saved segments never auto-selects one, so the screen sits in
// the genuinely-empty state — pressing "New segment" then leaves the definition
// byte-identical, which is where Issue B (the resolve effect never firing for a
// new segment) actually bites. The saved-segment blocks keep their one segment.
let NO_SEGMENTS = false

const routes = (page) => page.route('**/api/**', async (route) => {
  const url = route.request().url()
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) return json({ id: 'boss', username: 'boss', role: 'club_admin', club_slug: 'test-cc',
    can_switch_clubs: INTERNAL, is_marketing_org: INTERNAL, entitlements: { modules: ['comms', 'admin'], status: 'active' } })
  if (/\/comms\/segments\/options/.test(url)) return json({ roles: [], genders: [], teams: [] })
  if (/\/comms\/segments\/([^/]+)\/members/.test(url)) return json([])
  if (/\/comms\/segments\/(resolve|preview)/.test(url)) return json({
    count: 40, universe: 50, out_count: 10, member_ids: MEMBER_IDS,
    contacts: CONTACTS.slice(0, 40), reachable: 40, other_route: 0, clubs: 3 })
  if (/\/comms\/segments$/.test(url)) return json(NO_SEGMENTS ? [] : SEGMENTS)
  if (/\/comms\/contacts/.test(url)) return json({
    contacts: INTERNAL ? CONTACTS : CONTACTS.map(c => ({
      ...c, club: undefined, association: undefined, country: undefined,
      utm_code: undefined, state: undefined, marketing_club_id: null })),
    cap: 50000 })
  if (/\/comms\/context/.test(url)) return json({ current: { is_marketing: INTERNAL } })
  if (/\/notifications\/(count|summary)/.test(url)) return json({ unseen_count: 0, items: [] })
  return json({})
})

// The tile counts, keyed 'in' / 'out', read off the tile's big number div.
const tileCounts = (page) => page.evaluate(() => {
  const out = {}
  for (const b of document.querySelectorAll('button')) {
    const t = b.textContent || ''
    const num = (b.querySelector('div')?.textContent || '').trim()
    if (/In this segment/.test(t) && !/Not in/.test(t)) out.in = num
    else if (/Not in this segment/.test(t)) out.out = num
  }
  return out
})
const listShown = (page) => page.evaluate(() =>
  [...document.querySelectorAll('span')].filter(s => /\d+ shown/.test(s.textContent || '')).map(s => s.textContent.trim()))
const noOverflow = (page) => page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth)

async function open(browser, width = 1500, mode = 'saved') {
  const ctx = await browser.newContext({ viewport: { width, height: 1100 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page)
  await page.goto(BASE + '/admin/comms/segments', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1400)
  // 'saved' opens an existing segment; 'new' presses "New segment" from the
  // fresh/empty state — the path whose blank starter rule leaves the definition
  // byte-identical to the empty state, so the resolve effect must be nudged to
  // fire or the tiles read 0.
  if (mode === 'new') await page.click('button:has-text("New segment")').catch(() => {})
  else await page.click('text=Cold seg').catch(() => {})
  await page.waitForTimeout(1200)
  return { ctx, page, errors }
}
// The Static picker's own search box — its hint always names "email" in both
// contexts ("Search name, email, …" / "Search on name or email address"),
// unlike the sidebar's "Search segments…", so this never grabs the wrong one.
const search = (page, v) => page.$('input[placeholder*="email" i]').then(el => el && el.fill(v))
// Open the Club facet dropdown and tick one club — the reported "select a club"
// path. The facet button's accessible name starts with "Club"; the nav's
// "BetterClubhouse" starts with "BetterC", so the anchored regex is unambiguous.
const pickClub = async (page, name) => {
  await page.getByRole('button', { name: /^Club/ }).first().click().catch(() => {})
  await page.waitForTimeout(200)
  await page.locator(`label:has-text("${name}") input[type=checkbox]`).first().check().catch(() => {})
  await page.keyboard.press('Escape').catch(() => {})
}

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  // ── Outreach: clubs present ──────────────────────────────────────────────
  INTERNAL = true
  {
    const { ctx, page, errors } = await open(browser)

    let t = await tileCounts(page)
    check('with no filter the "In" tile shows the whole segment count', t.in === '40', JSON.stringify(t))
    check('with no filter the "Not in" tile shows the whole out count', t.out === '10', JSON.stringify(t))
    let body = await page.textContent('body')
    check('with no filter the reachable/clubs line shows', /reachable by email/.test(body))

    // Type a search matching a subset of MEMBERS.
    await search(page, 'Member 1'); await page.waitForTimeout(600)
    t = await tileCounts(page)
    // Member 1, 10..19 = 11 members; no prospect matches "Member 1".
    check('searching drops the "In" tile to the matching count', t.in === '11', JSON.stringify(t))
    check('...and the "Not in" tile to its matching count (0 here)', t.out === '0', JSON.stringify(t))
    body = await page.textContent('body')
    check('a context line names the whole-segment total while filtered',
      /out of\s*40\s*in the segment/i.test(body.replace(/\s+/g, ' ')), 'context line')
    check('the sub-text says it is matching the filter', /Matching your filter/.test(body))

    // Toggle the In tile → the drill-down lists exactly the matches.
    await page.click('button:has-text("In this segment")').catch(() => {})
    await page.waitForTimeout(600)
    check('clicking the tile lists exactly the matching contacts', (await listShown(page)).includes('11 shown'),
      JSON.stringify(await listShown(page)))

    // A search that matches only NON-members: In=0, Not-in=10.
    await search(page, 'Zeta'); await page.waitForTimeout(600)
    t = await tileCounts(page)
    check('a search matching only non-members shows In = 0', t.in === '0', JSON.stringify(t))
    check('...and Not-in = the matching prospects, pointing at the right list', t.out === '10', JSON.stringify(t))

    // Clearing the filter restores the whole counts.
    await search(page, ''); await page.waitForTimeout(500)
    t = await tileCounts(page)
    check('clearing the search restores the whole-segment counts', t.in === '40' && t.out === '10', JSON.stringify(t))

    check('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  // ── Outreach: a NEW unsaved segment resolves so its tiles show the universe ─
  // Reported: on a new segment, typing a contact's name that exists (e.g.
  // "Peter Moore") left "In this segment" at the whole-audience figure and the
  // matches hidden — In never dropped to 1; picking a club never showed its 3.
  // The cause was the resolve effect never firing for a new segment (its blank
  // rule filters out, so defKey is unchanged from the fresh state), leaving
  // member_ids null. With the fix the new segment resolves (In = the universe),
  // then a search or club facet narrows it — exactly the reported expectation.
  INTERNAL = true
  NO_SEGMENTS = true
  {
    const { ctx, page, errors } = await open(browser, 1500, 'new')

    let t = await tileCounts(page)
    check('a new segment resolves — the "In" tile shows the universe, not 0', t.in === '40', JSON.stringify(t))

    // A name search narrows it (the reported "Peter Moore" case).
    await search(page, 'Member 1'); await page.waitForTimeout(600)
    t = await tileCounts(page)
    check('typing a name on a new segment drops the "In" tile to the match count', t.in === '11', JSON.stringify(t))
    await page.click('button:has-text("In this segment")').catch(() => {})
    await page.waitForTimeout(600)
    check('clicking the tile lists exactly the matching contacts (new segment)',
      (await listShown(page)).includes('11 shown'), JSON.stringify(await listShown(page)))

    // A club facet narrows it too (the reported "Hoxton Park Tigers" case).
    await search(page, ''); await page.waitForTimeout(400)
    await pickClub(page, 'Alpha CC'); await page.waitForTimeout(600)
    t = await tileCounts(page)
    // Members whose club is Alpha CC: i in {0,3,…,39} = 14.
    check('picking a club on a new segment drops the "In" tile to the club count', t.in === '14', JSON.stringify(t))

    check('no page errors (new segment)', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }
  NO_SEGMENTS = false

  // ── Outreach at 390px ────────────────────────────────────────────────────
  INTERNAL = true
  {
    const { ctx, page } = await open(browser, 390)
    await search(page, 'Member 2'); await page.waitForTimeout(500)
    check('no horizontal overflow at 390px', (await noOverflow(page)) <= 1)
    await ctx.close()
  }

  // ── Club admin: no directory fields, filter by name still feeds the tiles ─
  INTERNAL = false
  {
    const { ctx, page, errors } = await open(browser)
    let t = await tileCounts(page)
    check('club-admin: whole counts with no filter', t.in === '40' && t.out === '10', JSON.stringify(t))
    await search(page, 'Member 3'); await page.waitForTimeout(600)
    t = await tileCounts(page)
    // Member 3, 30..39 = 11.
    check('club-admin: a name search drops the "In" tile to the match count', t.in === '11', JSON.stringify(t))
    check('no page errors (club-admin)', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { FAIL.forEach(f => console.log('  FAILED: ' + f)); process.exit(1) }
}

run().catch(e => { console.error(e); process.exit(1) })
