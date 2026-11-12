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
// Same for a <select> this change adds: absent on the control build, so skip rather than time out.
const selectIf = async (locator, value) => { if (await locator.count()) await locator.first().selectOption(value) }

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
    { key: 'club_selected', label: 'Club selected', value: 20, pct_of_top: 0, pct_of_prev: 0, meta_leads: 275,
      note: 'Meta counted 275 Lead events for the same step (its own count, so it can differ from ours).' },
    { key: 'results', label: 'Free trial signups', value: SIGNUPS, pct_of_top: 0, pct_of_prev: 30 },
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

const summaryFor = ({ webinar = webinarEmpty, countingSince = null, countsFrom = null, excluded = { before_restart: 0, undated: 0 }, unattributed = 0 } = {}) => ({
  campaign: {
    spend: TRIAL_SPEND + webinar.spend, impressions: 90000, link_clicks: 800, link_ctr: 0.9,
    landing_page_views: 700, cost_per_lpv: 2.43, leads: 9, registrations: SIGNUPS,
    leads_adjustment: 0, leads_effective: SIGNUPS,
  },
  ads: ADS, streams: [trialStream, webinar], creatives: CREATIVES, unattributed_spend: unattributed,
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
    { name: 'Applegrove CC', key: 'applegrove cc', slug: null, via_meta: true, furthest_step: 'Registration completed', email: 'sec@applegrove.example', last_at: '2026-11-10T09:00:00Z', visitors: 1,
      origin: { channel: 'email', label: 'Email (our outreach)', detail: 'utm_source=bettercricket, utm_medium=email, utm_id=APPLE1' } },
    { name: 'Bayview CC', key: 'bayview cc', slug: null, via_meta: true, furthest_step: 'Reached Terms & privacy', email: 'bayview@club.example', last_at: '2026-11-10T08:00:00Z', visitors: 2,
      origin: { channel: 'meta', label: 'Meta ad', detail: 'utm_source=meta, utm_campaign=BC_AU_Trial_CBO_Sep2026, click=facebook' } },
    { name: 'Cresthill CC', key: 'cresthill cc', slug: null, via_meta: true, furthest_step: 'Club selected', email: null, last_at: '2026-11-09T08:00:00Z', visitors: 3,
      origin: { channel: 'direct', label: 'Direct', detail: 'no UTM tags and no referrer' } },
  ],
  hidden_clubs: [], identified: 3, hidden_count: 0, anonymous: 2, outside_campaign: 2, scope: 'campaign',
}
// What 'All traffic' adds: a club from other traffic, and no "left out" count.
const SELECTED_ALL = {
  ...SELECTED,
  clubs: [...SELECTED.clubs,
    { name: 'Organic CC', key: 'organic cc', slug: null, via_meta: false, furthest_step: 'Reached Terms & privacy', email: 'org@club.example', last_at: '2026-11-08T08:00:00Z', visitors: 3,
      origin: { channel: 'social', label: 'Shared on Facebook', detail: 'referrer=l.facebook.com' } }],
  identified: 4, outside_campaign: 0, scope: 'all',
}
const SEARCHED = {
  clubs: [
    { name: 'Dunmore CC', key: 'dunmore cc', via_meta: true, selected: false, visitors: 4, searches: 6, queries: ['dunmore', 'dunmore cricket'], last_at: '2026-11-10T07:00:00Z',
      origin: { channel: 'google', label: 'Google', detail: 'referrer=www.google.com.au' } },
    { name: 'Applegrove CC', key: 'applegrove cc', via_meta: true, selected: true, visitors: 2, searches: 2, queries: ['applegrove'], last_at: '2026-11-10T06:00:00Z' },
  ],
  hidden_clubs: [], identified: 2, hidden_count: 0, searched_only_count: 1, converted_count: 1, scope: 'campaign',
}
const ONSITE = {
  days: 7, scope: 'campaign',
  meta: { visitors: 31, views: 60, facebook: 29, instagram: 2, paid: 31 },
  conversion: { visitors: 31, reached_intent: 3, pct: 10 },
  creatives: [{ content: 'check_out_your_club_v2', campaign: 'BC_AU_Trial_CBO_Sep2026', visitors: 31 }],
  landing: [{ page: '/trial', label: 'Trial page', visitors: 31 }],
}

async function open({ summary, signups = { rows: ROWS, campaigns: [] }, signupsFail = false, listsFail = false,
                      selected = SELECTED_ALL, searched = SEARCHED,
                      tokens = null, width = 1500 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 3200 } })
  const page = await ctx.newPage()
  const errors = []
  const wire = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url())
    const p = u.pathname.replace(/^\/api/, '')
    wire.push(p + u.search)
    const scopeQ = u.searchParams.get('scope')
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
    if (/meta-ads\/selected-clubs/.test(p)) return listsFail ? json({ detail: 'boom' }, 500) : json(scopeQ === 'campaign' && selected === SELECTED_ALL ? SELECTED : selected)
    if (/meta-ads\/searched-clubs/.test(p)) return listsFail ? json({ detail: 'boom' }, 500) : json(searched)
    if (/meta-ads\/onsite/.test(p)) return json({ ...ONSITE, scope: scopeQ || 'campaign', days: Number(u.searchParams.get('days') || 30) })
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
  return { page, ctx, errors, wire }
}
const val = (page, id) => textOf(page.locator(`[data-testid="kpi-${id}-value"]`))
const money = (n) => `A$${n.toFixed(2)}`

// ── A. The normal read ───────────────────────────────────────────────────────
{
  const { page, ctx, errors, wire } = await open({ summary: summaryFor() })
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

  // ── The clubs panel: one list, stacked in view, with the stage each club reached ──
  const bodyNow = await page.locator('body').innerText()
  const stageOf = async (name) => {
    const row = page.locator('[data-testid="club-row"]', { hasText: name })
    return (await row.count()) ? (await textOf(row.first().locator('[data-testid="club-stage"]'))).toLowerCase() : ''
  }
  ck('the section has no tabs', (await page.locator('[role="tab"], [data-testid^="demand-tab-"]').count()) === 0)
  ck('the clubs panel is on screen with nothing clicked', await has(page.locator('[data-testid="clubs-panel"]')))
  ck('each club that typed in is named, once (the two lists are folded)',
     (await page.locator('[data-testid="club-row"]').count()) === 5
     && ['Applegrove CC', 'Bayview CC', 'Cresthill CC', 'Dunmore CC', 'Organic CC'].every((n) => bodyNow.includes(n)),
     String(await page.locator('[data-testid="club-row"]').count()))
  ck('a completed club says Completed', (await stageOf('Applegrove')).includes('completed'), await stageOf('Applegrove'))
  ck('a club that reached the Terms step says so', (await stageOf('Bayview')).includes('reached terms'), await stageOf('Bayview'))
  ck('a club that only picked one says Selected a club', (await stageOf('Cresthill')).includes('selected a club'), await stageOf('Cresthill'))
  ck('a club only searched is told apart', (await stageOf('Dunmore')).includes('searched only'), await stageOf('Dunmore'))
  ck('there is no Typed column any more', !/\btyped\b/i.test(await textOf(page.locator('[data-testid="clubs-panel"] thead'))) && !bodyNow.includes('“dunmore”'))
  const count = async (k) => (await textOf(page.locator(`[data-testid="club-chip-count-${k}"]`))).trim()
  const chips = async () => [await count('all'), await count('completed'), await count('terms'), await count('selected'), await count('searched')].join(',')
  ck('the stage chips carry counts', (await chips()) === '5,1,2,1,1', await chips())
  await clickIf(page.locator('[data-testid="club-chip-terms"]'))
  ck('"Reached terms, not finished" shows the clubs that stopped at Terms',
     (await page.locator('[data-testid="club-row"]').count()) === 2 && (await textOf(page.locator('[data-testid="clubs-panel"] tbody'))).includes('Bayview') && (await textOf(page.locator('[data-testid="clubs-panel"] tbody'))).includes('Organic'))
  await clickIf(page.locator('[data-testid="club-chip-searched"]'))
  ck('"Searched only" shows only Dunmore', (await page.locator('[data-testid="club-row"]').count()) === 1 && (await page.locator('[data-testid="club-row"]').first().innerText()).includes('Dunmore'))
  await clickIf(page.locator('[data-testid="club-chip-all"]'))
  await page.locator('input[type="search"]').first().fill('crest')
  ck('the name search narrows it', (await page.locator('[data-testid="club-row"]').count()) === 1 && (await page.locator('[data-testid="club-row"]').first().innerText()).includes('Cresthill'))
  await page.locator('input[type="search"]').first().fill('')
  ck('it opens on all traffic, so nothing is hidden and no "left out" note shows', !(await has(page.locator('[data-testid="clubs-outside"]'))))
  const recon = await textOf(page.locator('[data-testid="clubs-reconcile"]'))
  ck('the list says it counts named clubs while the funnel counts visitors, so the two can differ', /counts named clubs; the funnel above counts visitors/i.test(recon), recon.slice(0, 160))
  ck('and gives the reconciliation: clubs picked, visitor picks on them, picks that could not be named',
     /4 clubs picked here, 9 visitor picks on them/i.test(recon) && /2 more picks could not be named/i.test(recon), recon)
  ck('the pixel category is not printed on the stream card', !/self_serve_trial/i.test(await page.locator('body').innerText()))

  ck('no empty or failed message when there is data', !(await has(page.locator('[data-testid="clubs-empty"], [data-testid="lists-failed"]'))))
  ck('the wizard funnel and the traffic card are on screen too',
     /wizard: where visitors drop off \(7 days\)/i.test(bodyNow) && await has(page.locator('[data-testid="traffic-card"]')))
  ck('the club list leads, before the wizard funnel', bodyNow.search(/clubs that typed in their club/i) > -1 && bodyNow.search(/clubs that typed in their club/i) < bodyNow.search(/wizard: where visitors drop off/i))

  // ── The trial funnel: Club selected and Meta's Lead are one step, not two ────────
  const funnelText = await textOf(page.locator('[data-testid="stream-card-trial"]').locator('xpath=ancestor::div[contains(@class,"grid")][1]'))
  ck('the trial funnel has no "Started registering" stage after Club selected', !/started registering/i.test(funnelText) && /club selected/i.test(funnelText), funnelText.slice(0, 200))
  ck("Meta's Lead count is a note on the Club selected stage", /Meta counted 275 Lead events for the same step/.test(await textOf(page.locator('[data-testid="funnel-note"]'))))
  ck('no step reads over 100% "continued" (it read 23,200%)', !/\b\d{3,}(\.\d)?% continued/.test(bodyNow))
  ck('the webinar card is not shown for a campaign with no webinar ad or result', !(await has(page.locator('[data-testid="stream-card-webinar"]'))))

  // ── The wire: one period and one scope, sent to every on-site panel ─────────────
  const reads = (re) => wire.filter((w) => re.test(w))
  ck('the first load asks for 7 days of ALL TRAFFIC for the funnel, both lists and the traffic card',
     reads(/registration-funnel\?days=7&scope=all/).length >= 1 && reads(/selected-clubs\?days=7&scope=all/).length >= 1
     && reads(/searched-clubs\?days=7&scope=all/).length >= 1 && reads(/onsite\?days=7&scope=all/).length >= 1, wire.filter((w) => /meta-ads\/(reg|sel|sea|ons)/.test(w)).join(' | '))
  ck('and nothing is asked for at campaign scope until it is chosen', reads(/scope=campaign/).length === 0, reads(/scope=campaign/).join(' | '))
  ck('the scope note says every source', /every source/i.test(await textOf(page.locator('[data-testid="scope-note"]'))))
  ck('"All traffic" is the pressed option', (await page.locator('[data-testid="scope-all"]').getAttribute('aria-pressed')) === 'true')
  const before = wire.length
  await clickIf(page.locator('[data-testid="period-30"]'))
  await page.waitForTimeout(600)
  const afterPeriod = wire.slice(before)
  ck('picking 30 days re-reads every panel for 30 days, still all traffic',
     afterPeriod.some((w) => /selected-clubs\?days=30&scope=all/.test(w)) && afterPeriod.some((w) => /registration-funnel\?days=30&scope=all/.test(w))
     && afterPeriod.some((w) => /onsite\?days=30&scope=all/.test(w)), afterPeriod.join(' | '))
  const before2 = wire.length
  await clickIf(page.locator('[data-testid="period-730"]'))
  await page.waitForTimeout(600)
  const afterWhole = wire.slice(before2)
  ck('"Whole campaign" asks each endpoint for its own maximum (the funnel caps at 90, the card at 365)',
     afterWhole.some((w) => /selected-clubs\?days=730&scope=all/.test(w)) && afterWhole.some((w) => /registration-funnel\?days=90&scope=all/.test(w))
     && afterWhole.some((w) => /onsite\?days=365&scope=all/.test(w)), afterWhole.join(' | '))
  await clickIf(page.locator('[data-testid="period-7"]'))
  const before3 = wire.length
  await clickIf(page.locator('[data-testid="scope-campaign"]'))
  await page.waitForTimeout(600)
  const afterScope = wire.slice(before3)
  ck('"This campaign" re-reads everything with scope=campaign',
     afterScope.some((w) => /selected-clubs\?days=7&scope=campaign/.test(w)) && afterScope.some((w) => /onsite\?days=7&scope=campaign/.test(w)) && afterScope.some((w) => /registration-funnel\?days=7&scope=campaign/.test(w)), afterScope.join(' | '))
  ck('the scope note says this campaign only', /this campaign.s visitors only/i.test(await textOf(page.locator('[data-testid="scope-note"]'))))
  ck('the other traffic\'s club drops out', (await page.locator('[data-testid="club-row"]', { hasText: 'Organic CC' }).count()) === 0)
  ck('and what the campaign view left out is counted, with a way back to all traffic', /2 more clubs started in this period from other traffic/i.test(await textOf(page.locator('[data-testid="clubs-outside"]'))))
  await clickIf(page.locator('[data-testid="clubs-outside"] button'))
  await page.waitForTimeout(500)
  ck('that link returns to all traffic', (await page.locator('[data-testid="club-row"]', { hasText: 'Organic CC' }).count()) === 1)
  // ── Where each club came from: the column, the badge, the evidence, the filter ─────
  const originOfRow = async (name) => {
    const row = page.locator('[data-testid="club-row"]', { hasText: name })
    return (await row.count()) ? (await textOf(row.first().locator('[data-testid="club-origin"]'))).trim() : ''
  }
  ck('the column is "Where from" (it read Meta / Other)', /where from/i.test(await textOf(page.locator('[data-testid="clubs-panel"] thead'))) && !/\bsource\b/i.test(await textOf(page.locator('[data-testid="clubs-panel"] thead'))))
  ck('a club our own outreach email brought says so', /email \(our outreach\)/i.test(await originOfRow('Applegrove')), await originOfRow('Applegrove'))
  ck('a Meta ad says so', /meta ad/i.test(await originOfRow('Bayview')), await originOfRow('Bayview'))
  ck('a shared link names where it was shared', /shared on facebook/i.test(await originOfRow('Organic')), await originOfRow('Organic'))
  ck('a club with nothing to go on says Direct, not Other', /direct/i.test(await originOfRow('Cresthill')), await originOfRow('Cresthill'))
  const tip = await page.locator('[data-testid="club-row"]', { hasText: 'Applegrove' }).first().locator('td').nth(2).getAttribute('title')
  ck('hovering shows the raw evidence (UTMs, outreach code, referrer)', /utm_id=APPLE1/.test(tip || ''), tip || '')
  const opts = await page.locator('[data-testid="club-origin-filter"] option').allTextContents()
  ck('the filter lists only channels that occur, with counts', opts[0] === 'All sources (5)' && opts.includes('Email (1)') && opts.includes('Shared link (1)') && opts.includes('Google (1)') && !opts.some((o) => /^AI assistant/.test(o)), opts.join(' | '))
  await selectIf(page.locator('[data-testid="club-origin-filter"]'), 'social')
  ck('picking Shared link shows only that club', (await page.locator('[data-testid="club-row"]').count()) === 1 && (await page.locator('[data-testid="club-row"]').first().innerText()).includes('Organic'))
  await selectIf(page.locator('[data-testid="club-origin-filter"]'), 'email')
  ck('picking Email shows only the emailed club', (await page.locator('[data-testid="club-row"]').count()) === 1 && (await page.locator('[data-testid="club-row"]').first().innerText()).includes('Applegrove'))
  await clickIf(page.locator('[data-testid="club-chip-completed"]'))
  ck('the filters combine (Email and Completed)', (await page.locator('[data-testid="club-row"]').count()) === 1)
  await clickIf(page.locator('[data-testid="club-chip-terms"]'))
  ck('and an Email club that did not reach Terms is not shown under Reached terms', (await page.locator('[data-testid="club-row"]').count()) === 0)
  await selectIf(page.locator('[data-testid="club-origin-filter"]'), 'all')
  await clickIf(page.locator('[data-testid="club-chip-all"]'))
  ck('clearing them brings all five back', (await page.locator('[data-testid="club-row"]').count()) === 5)
  await page.screenshot({ path: '/tmp/meta_ads_kpi_desktop.png', fullPage: true })
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── A2. The list is empty, or fails to load: say so, never go quiet ─────────────
{
  const empty = { clubs: [], hidden_clubs: [], identified: 0, hidden_count: 0, anonymous: 0, searched_only_count: 0, converted_count: 0, outside_campaign: 0 }
  const { page, ctx } = await open({ summary: summaryFor(), selected: empty, searched: empty })
  ck('an empty list says no club typed in during the period instead of vanishing', /no club typed into the trial page in the last 7 days/i.test(await textOf(page.locator('[data-testid="clubs-empty"]'))))
  ck('and that is not reported as a load failure', !(await has(page.locator('[data-testid="lists-failed"]'))))
  await ctx.close()
}
{
  const { page, ctx } = await open({ summary: summaryFor(), listsFail: true })
  ck('a failed load of the list is shown, not swallowed', await has(page.locator('[data-testid="lists-failed"]')))
  ck('and no misleading "no club typed in" appears beside it', !(await has(page.locator('[data-testid="clubs-empty"]'))))
  await ctx.close()
}

// ── A2b. Stale ad rows: the ads add up to MORE than the campaign spent ───────────
{
  const { page, ctx } = await open({ summary: summaryFor({ unattributed: -1419.84 }) })
  ck('Cost per trial is withheld when the ad rows disagree with the campaign spend', (await val(page, 'cost')).trim() === '–', await val(page, 'cost'))
  ck('and so is ROAS', (await val(page, 'roas')).trim() === '–', await val(page, 'roas'))
  ck('and the page says why, and what to press', /add up to A\$1419\.84 more than the campaign/i.test(await textOf(page.locator('[data-testid="stale-spend"]'))) && /refresh now/i.test(await textOf(page.locator('[data-testid="stale-spend"]'))))
  await ctx.close()
}

// ── A3. A restarted campaign says where counting starts and what it left out ──
{
  const { page, ctx } = await open({ summary: summaryFor({ countsFrom: '2026-11-09T16:00:00Z', excluded: { before_restart: 1, undated: 2, other_traffic: 5 } }) })
  const note = await textOf(page.locator('[data-testid="counts-from-note"]'))
  ck('the restart date is stated on the page', /restarted/i.test(note) && /counting registrations and spend from/i.test(note), note.slice(0, 160))
  ck('the earlier registration left out is reported, singular', /1 earlier registration from this campaign is from before the restart and not counted/i.test(note), note)
  const other = await textOf(page.locator('[data-testid="other-traffic-note"]'))
  ck('five registrations that finished from outside the campaign are explained', /5 other registrations finished since then from outside this campaign/i.test(other), other.slice(0, 200))
  ck('and the page says why they are not in Free trial signups or cost per trial', /not in free trial signups or cost per trial/i.test(other) && /where each came from/i.test(other), other.slice(0, 260))
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
