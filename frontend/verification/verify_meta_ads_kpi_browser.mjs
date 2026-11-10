// Meta Ads HQ cleanup: the headline strip, the per-creative Converted and ROAS
// columns, the Paid? badge, the grouped demand section, and the daily charts
// behind a toggle.
//
//   npx vite --port 5204 &
//   node frontend/verification/verify_meta_ads_kpi_browser.mjs [baseUrl]
//
// What a reader can be misled by, and so what is measured:
//  * ROAS must be PAID CLUBS x 399 over the trial ads' spend. The service's own
//    `roas` is signups x 399, so the stub carries a deliberately different
//    value there: a page that read it would show 4.69x instead of 0.47x.
//  * Cost per trial divides the TRIAL ads' spend, never the campaign's.
//  * Webinar registrations are never valued: adding 12 of them must not move
//    revenue or ROAS.
//  * Counting-since never narrows the trial count, and when signups pre-date it
//    the cost and ROAS are withheld rather than printed too good.
//  * An unloaded signups report is "unknown", not zero.
//
// Control runs must REPORT, not crash: every read of something this change adds
// goes through textOf()/has(), which tolerate absence.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium/chrome-linux/chrome'
const PAGE_URL = `${BASE}/admin/super/meta-ads`

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
async function textOf(locator) {
  return await locator.count() ? await locator.first().innerText() : ''
}
const has = async (locator) => (await locator.count()) > 0
// A click on something this change adds would time out on the control build.
const clickIf = async (locator) => { if (await locator.count()) await locator.first().click() }

const CAMPAIGN_ID = '120251284365570121'
const TRIAL_SPEND = 1700.49
const SIGNUPS = 6
const PAID = 2
const WEBINAR_REGS = 12

const trialStream = {
  stream: 'trial', label: 'Free trial signups', content_category: 'self_serve_trial',
  spend: TRIAL_SPEND, impressions: 90000, link_clicks: 800, landing_page_views: 700,
  leads: 9, ad_count: 7, active_ad_count: 1, cost_per_lpv: 2.43,
  results: SIGNUPS, result_label: 'Free trial signups',
  cost_per_result: Number((TRIAL_SPEND / SIGNUPS).toFixed(2)),
  unit_value_aud: 399, carries_value: true,
  attributed_value_aud: SIGNUPS * 399,
  // The service's own figure is SIGNUPS x 399 over spend. The strip must not
  // read it: it would claim 1.41x when only 2 of the 6 clubs have paid.
  roas: Number(((SIGNUPS * 399) / TRIAL_SPEND).toFixed(2)),
  ends_on: null, ended: false, since_change: null,
  funnel: [
    { key: 'impressions', label: 'Impressions', value: 90000, pct_of_top: 100, pct_of_prev: 100 },
    { key: 'results', label: 'Free trial signups', value: SIGNUPS, pct_of_top: 0, pct_of_prev: 0.9 },
  ],
}
const webinarEmpty = {
  stream: 'webinar', label: 'Webinar registrations', content_category: 'webinar',
  spend: 0, impressions: 0, link_clicks: 0, landing_page_views: 0, leads: 0,
  ad_count: 0, active_ad_count: 0, cost_per_lpv: null, results: 0,
  result_label: 'Webinar registrations', cost_per_result: null, unit_value_aud: 0,
  attributed_value_aud: 0, carries_value: false, roas: null, ends_on: null, ended: false,
  since_change: null, funnel: [],
}
const webinarBusy = { ...webinarEmpty, spend: 120, results: WEBINAR_REGS, ad_count: 1, active_ad_count: 1 }

const mkAd = (id, name, spend, extra = {}) => ({
  ad_id: id, ad_name: name, name, stream: 'trial', destination: null, utm_content: null,
  ends_on: null, spend, impressions: 10000, link_clicks: 100, link_ctr: 1, landing_page_views: 80,
  cost_per_lpv: 2, leads: 1, cost_per_lead: null, delivery_status: 'ACTIVE', status: 'on_track',
  note: 'Steady.', ...extra,
})
// The real new campaign: seven ads, none mapped to a utm_content yet.
const ADS = [
  mkAd('120251342626760121', 'Ad_CheckOutYourClub_v2_Relaunch', 280.65),
  mkAd('120251460370820121', 'Ad_Video_V5_MatchSocials_1x1_Sep2026', 164.93),
  mkAd('120251550833470121', 'Ad_ClubSearch_Static_Sep2026', 1042.94, { delivery_status: 'PAUSED', status: 'paused' }),
  mkAd('120251301631290121', 'Ad_Trial_Spreadsheet_Sep2026_v3', 137.68, { delivery_status: 'PAUSED', status: 'paused' }),
]

const CREATIVES = [
  { utm_content: 'club_search', stream: 'trial', ad_name: null, spend: 0, trial_signups: 2,
    webinar_registrations: 0, landing_page_views: 0, results: 2, cost_per_result: null },
  { utm_content: 'spreadsheet_hero', stream: 'trial', ad_name: null, spend: 500, trial_signups: 3,
    webinar_registrations: 0, landing_page_views: 300, results: 3, cost_per_result: 166.67 },
  { utm_content: '(untagged)', stream: 'trial', ad_name: 'Ad_ClubSearch_Static_Sep2026', spend: 1200.49,
    trial_signups: 1, webinar_registrations: 0, landing_page_views: 400, results: 1, cost_per_result: 1200.49 },
]

const row = (n, extra = {}) => ({
  org_id: `o${n}`, name: `Club ${n}`, slug: `club-${n}`, signed_up_at: `2026-10-0${n}T02:00:00Z`,
  signup_source: 'self_serve_ad', utm_campaign: null, utm_content: null, utm_source: 'fb',
  click_source: 'facebook', landing_path: '/trial', trial_modules: ['select'], paid_modules: [],
  converted_to_paid: false, engagement_score: null, engagement_scored_at: null, ...extra,
})
const ROWS = [
  row(1, { utm_content: 'club_search', converted_to_paid: true, paid_modules: ['core', 'select'], trial_modules: [] }),
  row(2, { utm_content: 'club_search' }),
  row(3, { utm_content: 'spreadsheet_hero', converted_to_paid: true, paid_modules: ['core'], trial_modules: [] }),
  row(4, { utm_content: 'spreadsheet_hero' }),
  row(5, { utm_content: 'spreadsheet_hero' }),
  row(6),
]

const summaryFor = ({ webinar = webinarEmpty, countingSince = null, countsFrom = null, excluded = { before_restart: 0, undated: 0 } } = {}) => ({
  campaign: {
    spend: TRIAL_SPEND + webinar.spend, impressions: 90000, link_clicks: 800, link_ctr: 0.9,
    landing_page_views: 700, cost_per_lpv: 2.43, leads: 9, registrations: SIGNUPS,
    leads_adjustment: 0, leads_effective: SIGNUPS,
  },
  ads: ADS, streams: [trialStream, webinar], creatives: CREATIVES, unattributed_spend: 0,
  annotations: [], attribution_window_days: 7, undated_trial_results: 0,
  recommendation: null, recommendation_status: null, last_updated: new Date().toISOString(),
  leads_adjustment: 0, campaign_budget: 750, campaign_length_days: 30, insights: [],
  counting_since: countingSince, token_configured: true,
  counts_from: countsFrom, registrations_excluded: excluded,
})

const HISTORY = Array.from({ length: 14 }, (_, i) => ({
  date: new Date(Date.now() - (13 - i) * 86400000).toISOString().slice(0, 10),
  spend: 15, impressions: 1000, link_clicks: 10, link_ctr: 1, landing_page_views: 8,
  cost_per_lpv: 1.9, leads: 1, provisional: i > 7,
}))

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

const SELECTED = {
  clubs: [
    { name: 'Applegrove CC', key: 'applegrove cc', slug: null, via_meta: true, furthest_step: 'Registration completed', email: 'sec@applegrove.example', last_at: '2026-11-10T09:00:00Z' },
    { name: 'Bayview CC', key: 'bayview cc', slug: null, via_meta: true, furthest_step: 'Reached Terms & privacy', email: null, last_at: '2026-11-10T08:00:00Z' },
    { name: 'Cresthill CC', key: 'cresthill cc', slug: null, via_meta: false, furthest_step: 'Selected a club', email: null, last_at: '2026-11-09T08:00:00Z' },
  ],
  hidden_clubs: [], identified: 3, hidden_count: 0, anonymous: 0,
}
const SEARCHED = {
  clubs: [
    { name: 'Dunmore CC', key: 'dunmore cc', via_meta: true, selected: false, visitors: 4, searches: 6, queries: ['dunmore', 'dunmore cricket'], last_at: '2026-11-10T07:00:00Z' },
    { name: 'Applegrove CC', key: 'applegrove cc', via_meta: true, selected: true, visitors: 2, searches: 2, queries: ['applegrove'], last_at: '2026-11-10T06:00:00Z' },
  ],
  hidden_clubs: [], identified: 2, hidden_count: 0, searched_only_count: 1, converted_count: 1,
}

async function open({ summary, signups = { rows: ROWS, campaigns: [] }, signupsFail = false, listsFail = false,
                      selected = SELECTED, searched = SEARCHED,
                      tokens = null, width = 1500 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 3200 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url())
    const p = u.pathname.replace(/^\/api/, '')
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(p)) {
      return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'super_admin',
                    entitlements: { modules: [], status: 'active' } })
    }
    if (/meta-ads\/token-health/.test(p)) {
      return json(tokens || {
        ads: { configured: true, checked: true, valid: true, days_left: 50, never: false },
        capi: { configured: true, checked: true, valid: true, days_left: 50, never: false },
        attention: false, warn_within_days: 14,
      })
    }
    if (/meta-ads\/ad-history|meta-ads\/history/.test(p)) return json({ days: HISTORY, token_configured: true })
    if (/meta-ads\/summary/.test(p)) return json(summary)
    if (/meta-ads\/campaigns/.test(p)) {
      return json({ campaigns: [{ id: CAMPAIGN_ID, name: 'BC_AU_Trial_CBO_Sep2026', effective_status: 'ACTIVE' }],
                    active_campaign_id: CAMPAIGN_ID, token_configured: true })
    }
    if (/meta-ads\/leads\/adjustments/.test(p)) return json({ adjustments: [
      { delta: 5, note: 'older run', created_by_email: 'a@x.example', created_at: '2026-09-22T03:00:00Z', counted: false },
      { delta: 1, note: 'after restart', created_by_email: 'a@x.example', created_at: '2026-11-10T10:00:00Z', counted: true },
    ] })
    if (/meta-ads\/registration-funnel/.test(p)) {
      return json({ funnel: [
        { key: 'a', label: 'Club selected', value: 20, pct_of_top: 100, pct_of_prev: 100 },
        { key: 'b', label: 'Completed', value: 6, pct_of_top: 30, pct_of_prev: 30 },
      ] })
    }
    if (/meta-ads\/selected-clubs/.test(p)) return listsFail ? json({ detail: 'boom' }, 500) : json(selected)
    if (/meta-ads\/searched-clubs/.test(p)) return listsFail ? json({ detail: 'boom' }, 500) : json(searched)
    if (/meta-ads\/ad-signups/.test(p)) return signupsFail ? json({ detail: 'boom' }, 500) : json(signups)
    if (/usage\/campaigns/.test(p)) {
      return json({ days: 30, meta: { visitors: 10, facebook: 8, instagram: 2, paid: 9 },
                    conversion: { reached_intent: 3, pct: 30 }, creatives: [],
                    landing: [{ page: '/trial', label: 'Trial page', visitors: 9 }] })
    }
    return json([])
  })
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-testid="stream-card-trial"], [data-testid="kpi-strip"]')
    .first().waitFor({ state: 'visible', timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(1200)
  return { page, ctx, errors }
}
const val = (page, id) => textOf(page.locator(`[data-testid="kpi-${id}-value"]`))
const money = (n) => `A$${n.toFixed(2)}`

// ── A. The normal read ───────────────────────────────────────────────────────
{
  const { page, ctx, errors } = await open({ summary: summaryFor() })
  ck('the KPI strip exists', await has(page.locator('[data-testid="kpi-strip"]')))

  ck('Spend is the campaign spend', (await val(page, 'spend')).trim() === money(TRIAL_SPEND), await val(page, 'spend'))
  ck('Trial signups is our count', (await val(page, 'trials')).trim() === String(SIGNUPS), await val(page, 'trials'))
  ck(`Cost per trial is trial-ad spend over signups (${money(TRIAL_SPEND / SIGNUPS)})`,
     (await val(page, 'cost')).trim() === money(TRIAL_SPEND / SIGNUPS), await val(page, 'cost'))
  ck('Converted to paid counts the paid clubs in the signups report',
     (await val(page, 'converted')).trim() === String(PAID), await val(page, 'converted'))
  ck(`Revenue is paid clubs x 399 (${money(PAID * 399)})`,
     (await val(page, 'revenue')).trim() === money(PAID * 399), await val(page, 'revenue'))
  const roas = ((PAID * 399) / TRIAL_SPEND).toFixed(2)
  ck(`ROAS is revenue over trial-ad spend (${roas}x), not the service's signup-valued figure`,
     (await val(page, 'roas')).trim() === `${roas}x`, await val(page, 'roas'))
  ck('ROAS is not the signups x 399 figure the service computes',
     !(await val(page, 'roas')).includes(trialStream.roas.toFixed(2)))
  ck(`Trial to paid is converted over tracked signups (${((PAID / SIGNUPS) * 100).toFixed(1)}%)`,
     (await val(page, 'rate')).trim() === `${((PAID / SIGNUPS) * 100).toFixed(1)}%`, await val(page, 'rate'))
  ck('no webinar tile when the campaign has no webinar ads or registrations',
     !(await has(page.locator('[data-testid="kpi-webinar"]'))))

  // Source labels: innerText is CSS-uppercase already.
  const src = async (id) => (await textOf(page.locator(`[data-testid="kpi-${id}-source"]`))).toLowerCase()
  ck('Spend is labelled Meta-reported', (await src('spend')).includes('meta-reported'), await src('spend'))
  ck('Trial signups is labelled our tracking', (await src('trials')).includes('our tracking'), await src('trials'))
  ck('Converted is labelled our tracking', (await src('converted')).includes('our tracking'), await src('converted'))

  // Order and placement.
  const order = await page.evaluate(() => {
    const q = (s) => document.querySelector(s)
    const strip = q('[data-testid="kpi-strip"]'), since = q('[data-testid="counting-since"]')
    const tabs = q('[data-testid="demand-section"]'), header = q('h1')
    if (!strip || !since || !tabs || !header) return null
    const before = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)
    return {
      sinceBeforeStrip: before(since, strip), stripBeforeDemand: before(strip, tabs),
      headerBeforeSince: before(header, since),
      sinceInsideHeader: !!header.parentElement.parentElement.contains(since),
    }
  })
  ck('counting-since sits directly above the strip, not up in the header',
     !!order && order.sinceBeforeStrip && !order.sinceInsideHeader, JSON.stringify(order))
  ck('the strip comes before the demand section', !!order && order.stripBeforeDemand)

  // Token health is one pill.
  const pill = page.locator('[data-testid="token-pill"]')
  ck('token health is a single small pill', (await pill.count()) === 1 && /tokens ok/i.test(await textOf(pill)),
     await textOf(pill))

  // Creative table: Converted and ROAS.
  const rows = page.locator('[data-testid="creative-row"]')
  const find = async (tag) => {
    for (let i = 0; i < await rows.count(); i++) {
      const t = await rows.nth(i).innerText()
      if (t.includes(tag)) return rows.nth(i)
    }
    return null
  }
  const cs = await find('club_search'), sh = await find('spreadsheet_hero'), un = await find('(untagged)')
  ck('creative table has a Converted and a ROAS column',
     (await has(page.locator('[data-testid="creative-converted"]'))) && (await has(page.locator('[data-testid="creative-roas"]'))))
  const cell = async (r, id) => r ? (await textOf(r.locator(`[data-testid="${id}"]`))).trim() : ''
  ck('spreadsheet_hero: 1 paid club', (await cell(sh, 'creative-converted')) === '1', await cell(sh, 'creative-converted'))
  ck(`spreadsheet_hero ROAS is 1 x 399 over its A$500 spend (0.80x)`, (await cell(sh, 'creative-roas')) === '0.80x', await cell(sh, 'creative-roas'))
  ck('club_search: 1 paid club', (await cell(cs, 'creative-converted')) === '1', await cell(cs, 'creative-converted'))
  ck('a creative with no spend has no ROAS to divide', (await cell(cs, 'creative-roas')) === '–', await cell(cs, 'creative-roas'))
  ck('the untagged row has 0 paid clubs and a 0.00x ROAS, not a dash',
     (await cell(un, 'creative-converted')) === '0' && (await cell(un, 'creative-roas')) === '0.00x',
     `${await cell(un, 'creative-converted')} / ${await cell(un, 'creative-roas')}`)

  const unmapped = await textOf(page.locator('[data-testid="unmapped-ads"]'))
  ck('ads carrying spend with no tag on record are named',
     unmapped.includes('Ad_ClubSearch_Static_Sep2026') && unmapped.includes('AD_DESTINATIONS'), unmapped.slice(0, 120))

  // Signups table: Paid? badge and the modules.
  const paidCells = page.locator('[data-testid="signup-paid"]')
  const texts = []
  for (let i = 0; i < await paidCells.count(); i++) texts.push((await paidCells.nth(i).innerText()).toLowerCase())
  ck('every signup row has a Paid? cell', texts.length === ROWS.length, String(texts.length))
  const t0 = texts[0] || '', t1 = texts[1] || ''
  ck('a paid club shows Paid and its paid modules', t0.includes('paid') && t0.includes('core, select'), t0)
  ck('an unpaid club shows Trial', t1.includes('trial') && !t1.includes('paid'), t1)
  ck('two rows read Paid', texts.filter((t) => t.includes('paid')).length === PAID)

  // Daily charts hidden by default, behind one toggle.
  ck('daily charts are collapsed by default', (await page.locator('.recharts-wrapper').count()) === 0)
  await clickIf(page.locator('[data-testid="toggle-charts"]'))
  await page.waitForTimeout(700)
  ck('the toggle shows them', (await page.locator('.recharts-wrapper').count()) > 0)

  // Demand section: one stacked block. NOTHING is behind a click: the lists of who
  // typed a club in and the furthest step each reached are the follow-up list, and
  // they were lost once already to a tab that opened on the funnel.
  const bodyNow = await page.locator('body').innerText()
  ck('the section has no tabs', (await page.locator('[role="tab"], [data-testid^="demand-tab-"]').count()) === 0)
  ck('Clubs selected is on screen with nothing clicked', /clubs selected in the wizard/i.test(bodyNow))
  ck('Clubs searched is on screen with nothing clicked', /clubs searched in the wizard/i.test(bodyNow))
  ck('the wizard funnel is on screen too', /wizard: where visitors drop off/i.test(bodyNow))
  ck('where Meta clicks land is on screen too', /where meta clicks land/i.test(bodyNow))
  ck('each selected club is named', ['Applegrove CC', 'Bayview CC', 'Cresthill CC'].every((n) => bodyNow.includes(n)))
  ck('and the furthest step each reached is shown (CSS-uppercase, so compared lowercase)',
     /registration completed/i.test(bodyNow) && /reached terms & privacy/i.test(bodyNow) && /selected a club/i.test(bodyNow))
  ck('each searched club is named with what was typed', bodyNow.includes('Dunmore CC') && bodyNow.includes('“dunmore”'))
  ck('searched-only is told apart from selected', /searched only/i.test(bodyNow) && /\bselected\b/i.test(bodyNow))
  const posOf = (re) => bodyNow.search(re)
  ck('the two stage lists come before the funnel',
     posOf(/clubs selected in the wizard/i) > -1 && posOf(/clubs selected in the wizard/i) < posOf(/wizard: where visitors drop off/i)
     && posOf(/clubs searched in the wizard/i) < posOf(/wizard: where visitors drop off/i))
  ck('no empty-state message when there is data', !(await has(page.locator('[data-testid="selected-empty"], [data-testid="searched-empty"], [data-testid="lists-failed"]'))))
  await page.screenshot({ path: '/tmp/meta_ads_kpi_desktop.png', fullPage: true })
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── A2. The lists are empty, or fail to load: say so, never go quiet ──────────
{
  const empty = { clubs: [], hidden_clubs: [], identified: 0, hidden_count: 0, anonymous: 0, searched_only_count: 0, converted_count: 0 }
  const { page, ctx } = await open({ summary: summaryFor(), selected: empty, searched: empty })
  ck('empty lists say none recorded yet instead of vanishing',
     (await has(page.locator('[data-testid="selected-empty"]'))) && (await has(page.locator('[data-testid="searched-empty"]'))))
  ck('and that is not reported as a load failure', !(await has(page.locator('[data-testid="lists-failed"]'))))
  await ctx.close()
}
{
  const { page, ctx } = await open({ summary: summaryFor(), listsFail: true })
  ck('a failed load of the lists is shown, not swallowed', await has(page.locator('[data-testid="lists-failed"]')))
  ck('and no misleading "none recorded" appears beside it', !(await has(page.locator('[data-testid="selected-empty"], [data-testid="searched-empty"]'))))
  await ctx.close()
}

// ── A3. A restarted campaign says where counting starts and what it left out ──
{
  const { page, ctx } = await open({ summary: summaryFor({ countsFrom: '2026-11-09T16:00:00Z', excluded: { before_restart: 1, undated: 2 } }) })
  const note = await textOf(page.locator('[data-testid="counts-from-note"]'))
  ck('the restart date is stated on the page', /restarted/i.test(note) && /counting registrations and spend from/i.test(note), note.slice(0, 160))
  ck('the earlier registration left out is reported, singular', /1 earlier registration from this campaign is from before the restart and not counted/i.test(note), note)
  ck('registrations with no date are reported too', /2 more carry no signup date/i.test(note), note)
  await clickIf(page.getByRole('button', { name: /^log \(/ }))
  await page.waitForTimeout(400)
  const marks = await page.locator('[data-testid="adjustment-not-counted"]').count()
  ck('only the adjustment from before the restart is marked not counted', marks === 1, String(marks))
  await ctx.close()
}
{
  const { page, ctx } = await open({ summary: summaryFor() })
  ck('a campaign that never restarted shows no restart note', !(await has(page.locator('[data-testid="counts-from-note"]'))))
  await ctx.close()
}

// ── B. Webinar registrations never reach revenue or ROAS ─────────────────────
{
  const { page, ctx } = await open({ summary: summaryFor({ webinar: webinarBusy }) })
  ck('the webinar tile appears once there are webinar registrations', await has(page.locator('[data-testid="kpi-webinar"]')))
  ck('it reports the webinar count on its own', (await val(page, 'webinar')).trim() === String(WEBINAR_REGS))
  ck('revenue is unchanged by 12 webinar registrations', (await val(page, 'revenue')).trim() === money(PAID * 399), await val(page, 'revenue'))
  ck('and so is ROAS (webinar spend is not in the trial ads\' spend)',
     (await val(page, 'roas')).trim() === `${((PAID * 399) / TRIAL_SPEND).toFixed(2)}x`, await val(page, 'roas'))
  ck('the trial count is not inflated by webinar registrations', (await val(page, 'trials')).trim() === String(SIGNUPS))
  ck('Spend shows both products, the split is in its hint',
     (await val(page, 'spend')).trim() === money(TRIAL_SPEND + 120) && /webinar ads/i.test(await textOf(page.locator('[data-testid="kpi-spend-hint"]'))),
     await textOf(page.locator('[data-testid="kpi-spend-hint"]')))
  await ctx.close()
}

// ── C. Counting-since after some signups: withhold, never print too good ─────
{
  const since = '2026-10-04T00:00:00Z'  // rows 1-3 pre-date it
  const { page, ctx } = await open({ summary: summaryFor({ countingSince: since }) })
  ck('trial signups still counts every real registration', (await val(page, 'trials')).trim() === String(SIGNUPS), await val(page, 'trials'))
  ck('cost per trial is withheld when signups pre-date the cutoff', (await val(page, 'cost')).trim() === '–', await val(page, 'cost'))
  ck('ROAS is withheld too', (await val(page, 'roas')).trim() === '–', await val(page, 'roas'))
  const note = await textOf(page.locator('[data-testid="kpi-window-note"]'))
  ck('and the page says why', /pre-date/i.test(note) && /counting since/i.test(note), note.slice(0, 140))
  ck('the active window is shown', (await textOf(page.locator('[data-testid="counting-since-value"]'))).length > 0)
  await ctx.close()
}
{
  const since = '2026-09-01T00:00:00Z'  // before every signup: nothing to mismatch
  const { page, ctx } = await open({ summary: summaryFor({ countingSince: since }) })
  ck('a cutoff earlier than every signup withholds nothing',
     (await val(page, 'cost')).trim() === money(TRIAL_SPEND / SIGNUPS) && (await val(page, 'roas')).trim().endsWith('x'),
     `${await val(page, 'cost')} / ${await val(page, 'roas')}`)
  await ctx.close()
}

// ── D. The signups report is down: unknown, not zero ─────────────────────────
{
  const { page, ctx } = await open({ summary: summaryFor(), signupsFail: true })
  const conv = (await val(page, 'converted')).trim()
  const rev = (await val(page, 'revenue')).trim()
  ck('Converted is not shown as 0 when the report did not load', conv !== '0' && conv !== '', `"${conv}"`)
  ck('Revenue is not shown as A$0.00 either', rev !== money(0) && rev !== '', `"${rev}"`)
  ck('Trial signups still reads from the summary', (await val(page, 'trials')).trim() === String(SIGNUPS))
  await ctx.close()
}

// ── E. Token pill goes red, and the page fits a phone ────────────────────────
{
  const { page, ctx } = await open({
    summary: summaryFor(),
    tokens: {
      ads: { configured: true, checked: true, valid: true, days_left: 50, never: false },
      capi: { configured: true, checked: true, valid: false, error: 'expired' },
      attention: true, warn_within_days: 14,
    },
  })
  ck('either token failing turns the pill to a problem', /token problem/i.test(await textOf(page.locator('[data-testid="token-pill"]'))))
  await ctx.close()
}
{
  const { page, ctx, errors } = await open({ summary: summaryFor({ webinar: webinarBusy }), width: 390 })
  const over = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }))
  ck('390px: no horizontal page overflow', over.sw <= over.iw + 1, JSON.stringify(over))
  ck('390px: the strip is still there', await has(page.locator('[data-testid="kpi-strip"]')))
  await page.screenshot({ path: '/tmp/meta_ads_kpi_mobile.png', fullPage: false })
  ck('390px: no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
