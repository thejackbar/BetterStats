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
//   * the Static section shows two live tiles (in / not in the segment) from
//     /segments/resolve's count + out_count, and reveals a list only on click —
//     the old always-both-lists screen is gone, as are its engagement browsing
//     controls (relocated to the Active rules as a field);
//   * the sections read Active rules → Static members → Include/exclude (C1);
//   * a second condition shows an AND / OR connector, and switching it to OR
//     sends conj:"or" on the resolve wire (C4 / C5);
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

// A contact row (services/directory + routers/comms _contact_out shape). It
// carries a `club` so the Static section's directory chips render — which is
// also what the OLD build showed its (now-removed) engagement browsing controls
// beside, making their absence discriminating.
const CONTACT = {
  id: 'c1', name: 'Amardeep Gill', email: 'a@x.com', source: 'member',
  subscribed: true, suppressed: false, club: 'Rovers', state: 'WA', player_id: 'pl1', member_id: 'm1',
}
// A second contact that is NOT in the resolved audience — so the "Not in this
// segment" tile's list has a row to reveal.
const CONTACT2 = {
  id: 'c2', name: 'Bob Other', email: 'bob@x.com', source: 'member',
  subscribed: true, suppressed: false, club: 'Rovers', state: 'WA', player_id: 'pl2', member_id: 'm2',
}
// A third contact that IS in the segment (in the resolve `member_ids`) but is
// PAST the 5000-row cap — so it is absent from the capped `contacts` preview
// the resolve returns. This is the reported bug: the OLD build derived list
// membership from that capped preview, so Carol read as "not in" (she showed in
// the out list, not the in list) though the count said she was in. The fix
// partitions the club's OWN complete /comms/contacts list by `member_ids`, so
// she lands in the in list and never the out list.
const CONTACT3 = {
  id: 'c3', name: 'Carol Past', email: 'carol@x.com', source: 'member',
  subscribed: true, suppressed: false, club: 'Rovers', state: 'WA', player_id: 'pl3', member_id: 'm3',
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
  if ((m = url.match(/\/comms\/segments\/([^/]+)\/duplicate/)) && req.method() === 'POST') {
    return json({ id: 'copy1', name: 'Both seg (copy)', source: 'manual', origin: null,
      member_count: 1, definition: SEGMENTS[2].definition })
  }
  // Update echoes the sent definition back, so a saved segment's exclusions
  // round-trip through the wire the way the real router persists them.
  if ((m = url.match(/\/comms\/segments\/([^/]+)$/)) && req.method() === 'PUT') {
    let def = { match: 'all', rules: [] }
    try { def = JSON.parse(req.postData()).definition || def } catch { /* keep default */ }
    const base = SEGMENTS.find(s => s.id === m[1]) || { id: m[1], name: 'X', source: 'manual', origin: null, member_count: 0 }
    return json({ ...base, definition: def })
  }
  if (/\/comms\/segments\/resolve/.test(url) || /\/comms\/segments\/preview/.test(url)) {
    // universe / out_count drive the two In / Not-in tiles. Two contacts are IN
    // the segment (c1 hand-picked, c3 matched by a rule) but the `contacts`
    // preview is CAPPED to c1 alone — c3 is past the cap. `member_ids` is the
    // full in-segment set the screen partitions its own contact list with, so
    // the tiles (in = count = 2, not-in = out_count = 1) and the lists agree.
    return json({ count: 2, universe: 3, out_count: 1, member_ids: ['c1', 'c3'],
                  contacts: [CONTACT], reachable: 2, other_route: 0, clubs: 1 })
  }
  if (/\/comms\/segments$/.test(url) && req.method() === 'GET') return json(SEGMENTS)
  if (/\/comms\/contacts/.test(url)) return json({ contacts: [CONTACT, CONTACT2, CONTACT3] })
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

    // ── Tiles at the top, always-visible criteria, lists at the bottom ────────
    // Redesign: the two count tiles sit at the TOP (above Active rules) and
    // toggle only the contact LISTS, which appear at the BOTTOM (below
    // Include/exclude). The hand-pick selection criteria stay on display in the
    // Static section whatever the tiles do, and the two lists toggle
    // independently. 'Both seg' is selected.
    const tiles = await page.evaluate(() => {
      const out = []
      for (const b of document.querySelectorAll('button')) {
        const t = (b.textContent || '')
        // The big count is the tile's first child div (text-2xl tabular-nums).
        const num = (b.querySelector('div')?.textContent || '').trim()
        if (t.includes('In this segment') && !t.includes('Not in this segment')) out.push(['in', num])
        else if (t.includes('Not in this segment')) out.push(['out', num])
      }
      return out
    })
    const inTile = tiles.find(t => t[0] === 'in')
    const outTile = tiles.find(t => t[0] === 'out')
    check('the "In this segment" tile renders its count', !!inTile && inTile[1] === '2', JSON.stringify(tiles))
    check('the "Not in this segment" tile renders its count', !!outTile && outTile[1] === '1', JSON.stringify(tiles))

    // Geometry, before any tile is clicked: the tiles sit above the Active rules
    // section; the always-visible hand-pick search box sits inside the Static
    // section; and the three definition areas are each their own bordered card.
    const layout = await page.evaluate(() => {
      const txt = el => (el.textContent || '').trim()
      const leaf = (label) => [...document.querySelectorAll('*')].find(
        e => e.children.length === 0 && txt(e) === label)
      const topOf = (el) => el ? el.getBoundingClientRect().top : null
      let tileTop = null
      for (const b of document.querySelectorAll('button')) {
        if ((b.textContent || '').includes('In this segment')) {
          const t = b.getBoundingClientRect().top
          tileTop = tileTop == null ? t : Math.min(tileTop, t)
        }
      }
      // The hand-pick contact search (its hint names "email"), NOT the sidebar's
      // "Search segments…" box.
      const search = [...document.querySelectorAll('input')].find(
        i => /^Search .*email/.test(i.getAttribute('placeholder') || ''))
      // A definition card = the nearest ancestor of a heading with a real border.
      const cardOf = (label) => {
        let el = leaf(label)
        while (el && el !== document.body) {
          const b = getComputedStyle(el).borderTopWidth
          if (b && parseFloat(b) > 0) return el
          el = el.parentElement
        }
        return null
      }
      const cards = ['Active rules (live)', 'Static members (fixed)', 'Include or exclude other segments'].map(cardOf)
      return {
        tileTop,
        activeTop: topOf(leaf('Active rules (live)')),
        staticTop: topOf(leaf('Static members (fixed)')),
        searchTop: search ? search.getBoundingClientRect().top : null,
        cardCount: new Set(cards.filter(Boolean)).size,
        allBordered: cards.every(Boolean),
      }
    })
    check('the tiles sit above the Active rules section',
      layout.tileTop != null && layout.activeTop != null && layout.tileTop < layout.activeTop, JSON.stringify(layout))
    check('the hand-pick search box is always visible (no tile clicked yet)',
      layout.searchTop != null, JSON.stringify(layout))
    check('the search box sits inside the Static section',
      layout.searchTop != null && layout.staticTop != null && layout.searchTop > layout.staticTop, JSON.stringify(layout))
    check('the three definition areas are each their own bordered card',
      layout.allBordered && layout.cardCount === 3, JSON.stringify(layout))

    // Before a tile is clicked, no contact LIST is shown (the criteria are, but
    // no contact name).
    const bodyPreClick = await page.textContent('body')
    check('no contact list is shown until a tile is clicked',
      !bodyPreClick.includes('Amardeep Gill') && !bodyPreClick.includes('Bob Other'),
      'a name is visible before any tile click')

    const clickTile = (which) => page.evaluate((which) => {
      for (const b of document.querySelectorAll('button')) {
        const t = (b.textContent || '')
        const isIn = t.includes('In this segment') && !t.includes('Not in this segment')
        const isOut = t.includes('Not in this segment')
        if ((which === 'in' && isIn) || (which === 'out' && isOut)) { b.click(); return true }
      }
      return false
    }, which)

    // Click "In this segment" → its list reveals the audience contact.
    await clickTile('in')
    await page.waitForTimeout(500)
    let bod = await page.textContent('body')
    check('clicking the In tile reveals the in-segment contact', bod.includes('Amardeep Gill'))
    // Discriminating: a member PAST the resolve cap still lands in the in list,
    // because the screen partitions the full contact list by `member_ids` rather
    // than by the capped preview. The old build derived membership from the
    // capped preview, so Carol was missing here.
    check('the in list includes an in-segment member past the resolve cap (Carol)',
      bod.includes('Carol Past'), 'a past-cap member is missing from the in list')
    check('both tiles remain on screen with a list open',
      bod.includes('In this segment') && bod.includes('Not in this segment'))
    check('the in list keeps its per-contact Remove/matched controls', /matched|Remove/i.test(bod))

    // The revealed list sits BELOW the Include/exclude section.
    const listGeo = await page.evaluate(() => {
      const txt = el => (el.textContent || '').trim()
      const leaf = (label) => [...document.querySelectorAll('*')].find(
        e => e.children.length === 0 && txt(e) === label)
      const inc = leaf('Include or exclude other segments')
      const list = leaf('Contacts in this segment')
      return {
        incTop: inc ? inc.getBoundingClientRect().top : null,
        listTop: list ? list.getBoundingClientRect().top : null,
      }
    })
    check('the revealed list sits below the Include/exclude section',
      listGeo.listTop != null && listGeo.incTop != null && listGeo.listTop > listGeo.incTop, JSON.stringify(listGeo))

    // The engagement browsing controls (placeholder "score min") stay gone.
    const hasScoreMin = await page.$('input[placeholder="score min"]')
    check('the engagement min/max browsing controls are gone from the static section', hasScoreMin === null)

    // Independent toggles: opening "Not in" ALSO shows its list without hiding
    // the "in" one (the old single-view build would have replaced it).
    await clickTile('out')
    await page.waitForTimeout(500)
    bod = await page.textContent('body')
    check('opening the Not-in list leaves the In list open too (independent toggles)',
      bod.includes('Contacts in this segment') && bod.includes('Contacts not in this segment'),
      'one list replaced the other')
    check('the Not-in list reveals a contact outside the segment (with Add)',
      bod.includes('Bob Other') && /\bAdd\b/.test(bod))

    // Toggling the In tile again hides its list (show/hide, not a one-way open).
    await clickTile('in')
    await page.waitForTimeout(400)
    bod = await page.textContent('body')
    check('toggling the In tile again hides the In list',
      !bod.includes('Contacts in this segment') && bod.includes('Contacts not in this segment'))
    // Discriminating: with only the Not-in list showing, an in-segment member
    // past the cap (Carol) must NOT appear here — she is in the segment. The old
    // build listed her in the out list because she was absent from the capped
    // preview it derived membership from.
    check('the Not-in list excludes an in-segment member past the resolve cap (Carol)',
      !bod.includes('Carol Past'), 'a past-cap member wrongly appears in the not-in list')

    // ── Phase 2: Save/Delete in the title row, and the include/exclude picker ──
    const body2 = await page.textContent('body')
    check('the Include or exclude other segments section is labelled',
      body2.includes('Include or exclude other segments'))

    // C1: the include/exclude section sits immediately BELOW the Static members
    // section (Active rules → Static members → Include/exclude).
    const order = await page.evaluate(() => {
      const txt = el => (el.textContent || '').trim()
      const head = (label) => {
        const el = [...document.querySelectorAll('*')].find(
          e => e.children.length === 0 && txt(e) === label)
        return el ? el.getBoundingClientRect().top : null
      }
      return {
        active: head('Active rules (live)'),
        staticH: head('Static members (fixed)'),
        refs: head('Include or exclude other segments'),
      }
    })
    check('sections read Active rules → Static members → Include/exclude, top to bottom',
      order.active != null && order.staticH != null && order.refs != null
      && order.active < order.staticH && order.staticH < order.refs, JSON.stringify(order))

    // Save and Delete were moved out of a footer SaveRow and up into the title
    // row — both sit ABOVE the "Active rules (live)" heading now.
    const geo = await page.evaluate(() => {
      const txt = el => (el.textContent || '').trim()
      const btns = [...document.querySelectorAll('button')]
      const save = btns.find(b => txt(b) === 'Save changes')
      const del = btns.find(b => txt(b) === 'Delete')
      const head = [...document.querySelectorAll('*')].find(
        e => e.children.length === 0 && txt(e) === 'Active rules (live)')
      return {
        saveTop: save ? save.getBoundingClientRect().top : null,
        delTop: del ? del.getBoundingClientRect().top : null,
        activeTop: head ? head.getBoundingClientRect().top : null,
      }
    })
    check('a Save button is present', geo.saveTop != null)
    check('a Delete button is present', geo.delTop != null)
    check('Save sits above the Active rules section (moved to the title row)',
      geo.saveTop != null && geo.activeTop != null && geo.saveTop < geo.activeTop, JSON.stringify(geo))
    check('Delete sits above the Active rules section (moved to the title row)',
      geo.delTop != null && geo.activeTop != null && geo.delTop < geo.activeTop, JSON.stringify(geo))

    // A ref row is a row carrying exactly an Include and an Exclude button; its
    // first direct span is the segment's name. Read them off, and (below) drive
    // them. Everything goes through page.evaluate so a build with no picker (the
    // control) reports the miss rather than hanging on a locator.
    const refNames = await page.evaluate(() => {
      const out = []
      for (const row of document.querySelectorAll('div')) {
        const labels = [...row.querySelectorAll('button')].map(b => (b.textContent || '').trim())
        if (labels.length === 2 && labels.includes('Include') && labels.includes('Exclude')) {
          const span = row.querySelector(':scope > span')
          if (span) out.push((span.textContent || '').trim())
        }
      }
      return [...new Set(out)]
    })
    check('the ref picker lists the other segments',
      refNames.includes('Rule seg') && refNames.includes('Static seg'), JSON.stringify(refNames))
    check('the ref picker omits the segment being edited',
      !refNames.includes('Both seg'), JSON.stringify(refNames))

    const clickRef = (name, mode) => page.evaluate(({ name, mode }) => {
      for (const row of document.querySelectorAll('div')) {
        const btns = [...row.querySelectorAll('button')]
        const labels = btns.map(b => (b.textContent || '').trim())
        if (labels.length === 2 && labels.includes('Include') && labels.includes('Exclude')) {
          const span = row.querySelector(':scope > span')
          if (span && (span.textContent || '').trim() === name) {
            const b = btns.find(x => (x.textContent || '').trim() === mode)
            if (b) { b.click(); return true }
          }
        }
      }
      return false
    }, { name, mode })

    // INCLUDE the rule segment → include_segments on the resolve wire.
    await clickRef('Rule seg', 'Include')
    await page.waitForTimeout(900)
    const incResolve = calls.filter(c => /\/comms\/segments\/resolve/.test(c.url) && c.body).some(c => {
      try { return (JSON.parse(c.body).definition?.include_segments || []).includes('s_rule') } catch { return false }
    })
    check('choosing Include sends include_segments on the resolve wire', incResolve)

    // EXCLUDE the static segment → exclude_segments on the resolve wire.
    await clickRef('Static seg', 'Exclude')
    await page.waitForTimeout(900)
    const excResolve = calls.filter(c => /\/comms\/segments\/resolve/.test(c.url) && c.body).some(c => {
      try { return (JSON.parse(c.body).definition?.exclude_segments || []).includes('s_static') } catch { return false }
    })
    check('choosing Exclude sends exclude_segments on the resolve wire', excResolve)

    // Save from the title row updates the segment, carrying BOTH the include and
    // the exclude reference.
    const saveBtn = page.locator('button:has-text("Save changes")')
    if (await saveBtn.count()) await saveBtn.first().click().catch(() => {})
    await page.waitForTimeout(700)
    const putRefs = calls.filter(c => c.method === 'PUT' && /\/comms\/segments\/s_both$/.test(c.url) && c.body).some(c => {
      try {
        const d = JSON.parse(c.body).definition || {}
        return (d.include_segments || []).includes('s_rule') && (d.exclude_segments || []).includes('s_static')
      } catch { return false }
    })
    check('Save (in the title row) sends a PUT carrying the include and exclude refs', putRefs)

    // Reselect Both seg for the field-scope checks below (Save reset the draft).
    await page.click('text=Both seg')
    await page.waitForTimeout(700)

    // Club scope: the field select offers club fields, never directory ones.
    const opts = await fieldOptions(page)
    check('the club builder offers club member fields', !!opts
      && opts.includes('Membership type') && opts.includes('Squad'), JSON.stringify(opts))
    check('the club builder does NOT leak directory fields', !!opts
      && !opts.includes('Engagement score') && !opts.includes('Sales pipeline stage'),
      JSON.stringify(opts))

    // ── AND / OR connector between conditions (C4 / C5) ───────────────────────
    // Add a second condition; a two-state AND/OR toggle appears between the rows
    // (the first condition has no connector). 'Both seg' is selected with its one
    // valued rule.
    await page.click('button:has-text("Add condition")')
    await page.waitForTimeout(300)
    const conjButtons = await page.evaluate(() => {
      const bs = [...document.querySelectorAll('button')].map(b => (b.textContent || '').trim())
      return { and: bs.filter(t => t === 'AND').length, or: bs.filter(t => t === 'OR').length }
    })
    check('adding a condition shows an AND / OR connector',
      conjButtons.and >= 1 && conjButtons.or >= 1, JSON.stringify(conjButtons))

    // The new (2nd) condition defaults to the text `tag` field — give it a value
    // so it survives into the definition, then switch its connector to OR.
    await page.fill('input[placeholder="e.g. Committee"]', 'vip')
    await page.evaluate(() => {
      const or = [...document.querySelectorAll('button')].find(b => (b.textContent || '').trim() === 'OR')
      if (or) or.click()
    })
    await page.waitForTimeout(300)
    const orActive = await page.evaluate(() => {
      const or = [...document.querySelectorAll('button')].find(b => (b.textContent || '').trim() === 'OR')
      return or ? or.className.includes('bg-pb-accent') : false
    })
    check('clicking OR marks the connector active', orActive)

    // C5: the connector travels on the resolve wire — rules[1].conj === 'or', so
    // the tiles above recompute against the OR'd audience.
    await page.waitForTimeout(900)   // debounced resolve
    const conjOnWire = calls.filter(c => /\/comms\/segments\/resolve/.test(c.url) && c.body).some(c => {
      try {
        const rules = JSON.parse(c.body).definition?.rules || []
        return rules.length >= 2 && rules.some(r => r.conj === 'or')
      } catch { return false }
    })
    check('the OR connector travels on the resolve wire (conj:"or")', conjOnWire)

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
