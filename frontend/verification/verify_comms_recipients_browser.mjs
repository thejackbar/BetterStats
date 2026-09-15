// A sent campaign's recipient drill-down, against the REAL Emails detail pane
// with the API stubbed at the network layer.
//
// Reported on BetterComms → Emails: the recipient list (Unsubscribed/spam,
// Bounced, All recipients) named a person and their event but not their club
// or how recently they were emailed; the Super Admin outreach screen also
// wanted a searchable "Clubs" view. What is asserted:
//   * every recipient row shows the contact's club (when it has one) and when
//     they were LAST emailed;
//   * a fourth "Clubs" tab, with a searchable club <select>, that groups the
//     send by club and reads out each recipient's last-email status
//     (Received / Bounced / Unsubscribed / Spam);
//   * filtering by a club shows only that club's recipients;
//   * a club-admin send (recipients with no club) still shows last-emailed on
//     every row, shows no club sub-line, and the Clubs view says there is no
//     club information rather than offering a lone "No club" bucket;
//   * no horizontal overflow at 390px.
//
//   node verify_comms_recipients_browser.mjs   (BASE via APP_URL, default :5178)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5178'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const CID = 'camp1'

// Outreach recipients: four with a real club (Alpha/Beta), plus one club-less
// directory contact and one events-only ghost — so the "No club" bucket is
// offered alongside real clubs. `last_emailed_at` is CROSS-campaign: alice was
// re-emailed later than this campaign's own send.
const OUTREACH = [
  { id: 'r1', email: 'alice@x.com', name: 'Alice', club: 'Alpha CC',
    last_emailed_at: '2026-03-20T09:00:00+00:00', unsubscribed: false, complained: false, bounced: false, events: [] },
  { id: 'r2', email: 'bob@x.com', name: 'Bob', club: 'Beta CC',
    last_emailed_at: '2026-01-10T09:00:00+00:00', unsubscribed: false, complained: false, bounced: true,
    events: [{ type: 'bounce', subtype: 'Permanent', at: '2026-01-10T09:00:00+00:00' }] },
  { id: 'r3', email: 'carol@x.com', name: 'Carol', club: 'Alpha CC',
    last_emailed_at: '2026-01-10T09:00:00+00:00', unsubscribed: true, complained: false, bounced: false,
    events: [{ type: 'unsubscribe', at: '2026-01-11T09:00:00+00:00' }] },
  { id: 'r4', email: 'dave@x.com', name: 'Dave', club: null,
    last_emailed_at: '2026-01-10T09:00:00+00:00', unsubscribed: false, complained: false, bounced: false, events: [] },
  { id: null, email: 'ghost@x.com', name: null, club: null,
    last_emailed_at: null, unsubscribed: false, complained: false, bounced: true,
    events: [{ type: 'bounce', subtype: 'Permanent', at: '2026-01-10T09:00:00+00:00' }] },
]

// Club-admin recipients: a club's own members, so no club on any row.
const CLUB_MEMBERS = [
  { id: 'm1', email: 'ed@club.com', name: 'Ed', club: null,
    last_emailed_at: '2026-04-01T09:00:00+00:00', unsubscribed: false, complained: false, bounced: false, events: [] },
  { id: 'm2', email: 'fay@club.com', name: 'Fay', club: null,
    last_emailed_at: '2026-04-01T09:00:00+00:00', unsubscribed: false, complained: false, bounced: true,
    events: [{ type: 'bounce', at: '2026-04-01T09:00:00+00:00' }] },
]

let RECIPIENTS = OUTREACH
let INTERNAL = true
// Distinct clubs behind the recipients / delivered, for the summary tiles.
let CLUB_STATS = { recipients: 3, delivered: 2 }

const filterOnly = (rows, only) => {
  if (only === 'unsub_supp') return rows.filter(r => r.unsubscribed || r.complained)
  if (only === 'bounced') return rows.filter(r => r.bounced)
  return rows
}

const routes = (page, calls) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url()
  calls.push({ url, method: req.method() })
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

  if (url.includes('/auth/me')) {
    return json({
      id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      can_switch_clubs: INTERNAL, is_marketing_org: INTERNAL,
      entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' },
    })
  }
  // The recipient drill-down — the endpoint under test. Honour `only`.
  let m
  if ((m = url.match(/\/comms\/campaigns\/[^/]+\/recipients/))) {
    const only = new URL(url).searchParams.get('only')
    return json({ campaign: { id: CID, name: 'March outreach' },
                  recipients: filterOnly(RECIPIENTS, only) })
  }
  if (/\/comms\/campaigns\/[^/]+\/preview/.test(url)) return json({ html: '<p>preview</p>' })
  if ((m = url.match(/\/comms\/campaigns\/([^/]+)$/)) && req.method() === 'GET') {
    return json({
      id: CID, subject: 'Ready for another look at BetterCricket?', name: 'March outreach',
      description: '', body_html: '<p>hi</p>', audience: { type: 'segment', segment_id: 's1' },
      utm: {}, template_id: null, status: 'sent',
      engagement: { sent: 418, unsub_supp: 1, bounced: 1 },
      stats: { recipients: 419, sent: 418, failed: 1 },
      club_stats: CLUB_STATS,
    })
  }
  if (/\/comms\/campaigns$/.test(url)) {
    return json([{ id: CID, subject: 'Ready for another look at BetterCricket?', name: 'March outreach',
                   status: 'sent', created_at: '2026-03-20T09:00:00+00:00',
                   engagement: { sent: 418, unsub_supp: 1, bounced: 1 } }])
  }
  if (/\/comms\/segments/.test(url)) return json([])
  if (/\/comms\/templates/.test(url)) return json([])
  if (/\/comms\/merge-variables/.test(url)) return json({ variables: [] })
  if (/\/comms\/context/.test(url)) return json({ current: { is_marketing: INTERNAL } })
  if (/\/comms\/settings/.test(url)) return json({ provider: { live: true } })
  if (/\/notifications\/(count|summary)/.test(url)) return json({ unseen_count: 0, items: [] })
  return json({})
})

const noOverflow = (page) => page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth)

async function openDetail(browser, width = 1500) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const calls = [], errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page, calls)
  await page.goto(BASE + '/admin/comms/' + CID, { waitUntil: 'domcontentloaded' })
  // Wait for the recipient panel's own tabs to render.
  await page.waitForSelector('button:has-text("All recipients")', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(800)
  return { ctx, page, calls, errors }
}

// Tolerant of a control run where the tab / control does not exist at all — a
// missing button reports (the dependent check fails on absence) rather than
// crashing the whole run.
const clickPill = async (page, label) => {
  await page.click(`button:has-text("${label}")`, { timeout: 2500 }).catch(() => {})
  await page.waitForTimeout(500)
}
const clickIf = async (page, sel) => {
  await page.click(sel, { timeout: 2500 }).catch(() => {})
  await page.waitForTimeout(300)
}
const fillIf = async (page, sel, val) => {
  await page.fill(sel, val, { timeout: 2500 }).catch(() => {})
  await page.waitForTimeout(300)
}

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })

  // ── Super Admin / outreach: clubs present ────────────────────────────────
  RECIPIENTS = OUTREACH; INTERNAL = true; CLUB_STATS = { recipients: 3, delivered: 2 }
  {
    const { ctx, page, errors } = await openDetail(browser)

    // The summary tiles: Recipients + Delivered carry a distinct-club line;
    // Failed does not.
    const tiles = await page.evaluate(() => {
      const map = {}
      for (const label of ['recipients', 'delivered', 'failed']) {
        const lab = [...document.querySelectorAll('div')].find(
          d => d.children.length === 0 && (d.textContent || '').trim() === label)
        map[label] = lab && lab.parentElement ? lab.parentElement.textContent : null
      }
      return map
    })
    check('the Recipients tile shows the distinct-club count', /3 clubs/.test(tiles.recipients || ''), tiles.recipients)
    check('the Delivered tile shows the distinct-club count', /2 clubs/.test(tiles.delivered || ''), tiles.delivered)
    check('the Failed tile shows no club line', !/club/.test(tiles.failed || ''), tiles.failed)

    // All recipients — the club column + last-emailed on ordinary rows.
    await clickPill(page, 'All recipients')
    let body = await page.textContent('body')
    check('a recipient row shows its club name', body.includes('Alpha CC') && body.includes('Beta CC'))
    check('a recipient row shows when it was last emailed', body.includes('Last emailed'))

    // Read alice's own row: her club and her (later, cross-campaign) send date.
    const aliceRow = await page.evaluate(() => {
      const el = [...document.querySelectorAll('div')].find(d =>
        (d.textContent || '').includes('alice@x.com') && (d.textContent || '').includes('Last emailed'))
      return el ? el.textContent : null
    })
    check('alice\'s row carries her club and last-emailed together',
      !!aliceRow && aliceRow.includes('Alpha CC') && /Last emailed.*Mar/.test(aliceRow), aliceRow)

    // The fourth tab.
    check('a "Clubs" tab is offered', body.includes('Clubs'))
    await clickPill(page, 'Clubs')
    await page.waitForTimeout(600)

    // The searchable club <select> button.
    const hasChooser = await page.locator('button:has-text("Choose a club")').count()
    check('the Clubs view offers a club chooser', hasChooser > 0)

    // Before a club is chosen, no recipient rows are drawn.
    body = await page.textContent('body')
    check('nothing is listed until a club is picked',
      body.includes('Choose a club above') && !body.includes('alice@x.com'))

    // Open the chooser, search, and confirm the "No club" bucket is offered
    // alongside the real clubs (dave + ghost have none).
    await clickIf(page, 'button:has-text("Choose a club")')
    const optNames = await page.evaluate(() =>
      [...document.querySelectorAll('button')].map(b => (b.textContent || '').trim()))
    check('the chooser lists the real clubs', optNames.includes('Alpha CC') && optNames.includes('Beta CC'))
    check('...and a "No club" bucket beside them', optNames.includes('No club'))

    // Search narrows the options.
    await fillIf(page, 'input[placeholder="Search clubs…"]', 'beta')
    const shown = await page.evaluate(() => {
      const pop = [...document.querySelectorAll('div')].find(d => d.querySelector('input[placeholder="Search clubs…"]'))
      return pop ? [...pop.querySelectorAll('button')].map(b => (b.textContent || '').trim()) : []
    })
    check('the search box filters the club list', shown.includes('Beta CC') && !shown.includes('Alpha CC'))

    // Pick Alpha CC → only its two recipients (alice, carol), not Beta's bob.
    await fillIf(page, 'input[placeholder="Search clubs…"]', '')
    await clickIf(page, 'button:has-text("Alpha CC")')
    await page.waitForTimeout(300)
    body = await page.textContent('body')
    check('picking a club shows only that club\'s recipients',
      body.includes('alice@x.com') && body.includes('carol@x.com') && !body.includes('bob@x.com'), '')

    // The status badge is read out in the Clubs view: alice Received, carol
    // Unsubscribed. (The problem states win over "Received".)
    const badges = await page.evaluate(() => {
      const rows = [...document.querySelectorAll('div')].filter(d => {
        const t = d.textContent || ''
        return (t.includes('alice@x.com') || t.includes('carol@x.com'))
      })
      return rows.map(r => r.textContent)
    })
    const joined = badges.join(' || ')
    check('the Clubs view reads out each recipient\'s last-email status',
      /alice@x\.com[\s\S]*Received/.test(joined) && /carol@x\.com[\s\S]*Unsubscribed/.test(joined),
      joined.slice(0, 200))

    check('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  // ── Super Admin at 390px: no overflow ────────────────────────────────────
  RECIPIENTS = OUTREACH; INTERNAL = true
  {
    const { ctx, page } = await openDetail(browser, 390)
    await clickPill(page, 'All recipients')
    await clickPill(page, 'Clubs')
    const ov = await noOverflow(page)
    check('no horizontal overflow at 390px', ov <= 1, `overflow ${ov}px`)
    await ctx.close()
  }

  // ── Club Admin: no clubs, but last-emailed still shows ────────────────────
  RECIPIENTS = CLUB_MEMBERS; INTERNAL = false; CLUB_STATS = { recipients: 0, delivered: 0 }
  {
    const { ctx, page, errors } = await openDetail(browser)

    // A club's own send has no directory clubs, so no tile draws a club line.
    const memberTiles = await page.evaluate(() => {
      const t = [...document.querySelectorAll('div')].find(
        d => d.children.length === 0 && (d.textContent || '').trim() === 'recipients')
      return t && t.parentElement && t.parentElement.parentElement
        ? t.parentElement.parentElement.textContent : ''
    })
    check('a club\'s own send draws no club line on any tile', !/club/.test(memberTiles || ''), memberTiles)

    await clickPill(page, 'All recipients')
    let body = await page.textContent('body')
    check('a club member\'s row still shows when they were last emailed', body.includes('Last emailed'))
    // No club sub-line: none of the member rows name a club.
    check('a club member\'s row shows no club', !body.includes('Alpha CC') && !body.includes('Beta CC'))

    await clickPill(page, 'Clubs')
    await page.waitForTimeout(500)
    body = await page.textContent('body')
    check('with no clubs, the Clubs view says there is no club information, not a lone "No club"',
      body.includes('No club information for these recipients'))
    const chooser = await page.locator('button:has-text("Choose a club")').count()
    check('...and offers no club chooser at all', chooser === 0)
    check('no page errors (club-admin)', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { FAIL.forEach(f => console.log('  FAILED: ' + f)); process.exit(1) }
}

run().catch(e => { console.error(e); process.exit(1) })
