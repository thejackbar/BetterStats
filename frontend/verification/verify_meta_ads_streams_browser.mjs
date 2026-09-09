// The reported change: the Meta ad account was restructured on 8-9 Sep 2026 and
// ONE campaign now sells TWO things. Both landing pages fire the SAME pixel
// event (CompleteRegistration) on the same dataset, told apart only by
// `content_category` — /trial sends 'self_serve_trial', /demo sends 'webinar'.
//
//   npx vite --port 5204 &
//   node frontend/verification/verify_meta_ads_streams_browser.mjs [baseUrl]
//
// What is measured here, and it is all about what a reader can be misled by:
// there is NO unlabelled combined registrations total anywhere on the page; the
// two streams report their own result count and their own cost per result, from
// their own spend; only the trial carries value; the 8 Sep change is drawn on
// every time-series chart; the trailing seven days are visibly marked as still
// settling; and an ad that has ended neither divides by zero nor empties the
// layout.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const PAGE_URL = `${BASE}/admin/super/meta-ads`

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

// A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN. Every read of an element
// this change ADDS goes through here — a bare .innerText() on a locator that
// found nothing throws, and in a control run (where the element is absent by
// definition) that kills the run after two checks and says nothing about the
// rest. The house rule this file's neighbours already record.
async function textOf(locator) {
  return await locator.count() ? await locator.first().innerText() : ''
}
const has = async (locator) => (await locator.count()) > 0

const iso = (daysAgo) => {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() - daysAgo)
  return d.toISOString().slice(0, 10)
}
// The change lands 10 days back so there are settled days on BOTH sides of it
// in the 14-day window — a marker with nothing after it proves nothing.
const CHANGE_DATE = iso(10)

// Real-shaped: the brief's own lifetime figures to 8 Sep (A$1,920.29 / 41 trial
// registrations), plus the webinar ad's own spend since the restructure.
const TRIAL_SPEND = 1800.0
const WEBINAR_SPEND = 120.0
const TRIAL_RESULTS = 41
const WEBINAR_RESULTS = 12

const STREAMS = [
  {
    stream: 'trial', label: 'Free trial signups', content_category: 'self_serve_trial',
    spend: TRIAL_SPEND, impressions: 220000, link_clicks: 1760, landing_page_views: 1600,
    leads: 20, ad_count: 4, active_ad_count: 0, cost_per_lpv: 1.13,
    results: TRIAL_RESULTS, result_label: 'Free trial signups',
    cost_per_result: Number((TRIAL_SPEND / TRIAL_RESULTS).toFixed(2)),
    unit_value_aud: 399, attributed_value_aud: TRIAL_RESULTS * 399, carries_value: true,
    roas: Number(((TRIAL_RESULTS * 399) / TRIAL_SPEND).toFixed(2)),
    ends_on: null, ended: false,
    funnel: [
      { key: 'impressions', label: 'Impressions', value: 220000, pct_of_top: 100, pct_of_prev: 100 },
      { key: 'link_clicks', label: 'Link clicks', value: 1760, pct_of_top: 0.8, pct_of_prev: 0.8 },
      { key: 'landing_page_views', label: 'Landing page views', value: 1600, pct_of_top: 0.7, pct_of_prev: 90.9 },
      { key: 'club_selected', label: 'Club selected', value: 25, pct_of_top: 0, pct_of_prev: 1.6 },
      { key: 'leads', label: 'Started registering (Meta-reported)', value: 20, pct_of_top: 0, pct_of_prev: 80 },
      { key: 'results', label: 'Free trial signups', value: TRIAL_RESULTS, pct_of_top: 0, pct_of_prev: 205 },
    ],
  },
  {
    stream: 'webinar', label: 'Webinar registrations', content_category: 'webinar',
    spend: WEBINAR_SPEND, impressions: 9000, link_clicks: 200, landing_page_views: 150,
    leads: 0, ad_count: 2, active_ad_count: 1, cost_per_lpv: 0.8,
    results: WEBINAR_RESULTS, result_label: 'Webinar registrations',
    cost_per_result: Number((WEBINAR_SPEND / WEBINAR_RESULTS).toFixed(2)),
    unit_value_aud: 0, attributed_value_aud: 0, carries_value: false, roas: null,
    ends_on: '2026-09-21', ended: false,
    unattributed_results: 3, total_registrations: 15,
    funnel: [
      { key: 'impressions', label: 'Impressions', value: 9000, pct_of_top: 100, pct_of_prev: 100 },
      { key: 'link_clicks', label: 'Link clicks', value: 200, pct_of_top: 2.2, pct_of_prev: 2.2 },
      { key: 'landing_page_views', label: 'Landing page views', value: 150, pct_of_top: 1.7, pct_of_prev: 75 },
      { key: 'results', label: 'Webinar registrations', value: WEBINAR_RESULTS, pct_of_top: 0.1, pct_of_prev: 8 },
    ],
  },
]

const ADS = [
  { ad_id: '120251267760560121', ad_name: 'Ad_Webinar_LiveDemo_21Sep2026_v2',
    name: 'Ad_Webinar_LiveDemo_21Sep2026_v2', stream: 'webinar', destination: 'betterat.cricket/demo',
    utm_content: 'live_demo_hero', ends_on: '2026-09-21', spend: WEBINAR_SPEND, impressions: 9000,
    link_clicks: 200, link_ctr: 2.22, landing_page_views: 150, cost_per_lpv: 0.8, leads: 0,
    cost_per_lead: null, delivery_status: 'ACTIVE', status: 'winner', note: 'Keep it running.' },
  { ad_id: '120250150859240121', ad_name: 'Ad_ClubHistory_Trial_Hero_v3',
    name: 'Ad_ClubHistory_Trial_Hero_v3', stream: 'trial', destination: 'betterat.cricket/trial',
    utm_content: 'club_history_hero', ends_on: null, spend: TRIAL_SPEND, impressions: 220000,
    link_clicks: 1760, link_ctr: 0.8, landing_page_views: 1600, cost_per_lpv: 1.13, leads: 20,
    cost_per_lead: 90, delivery_status: 'PAUSED', status: 'paused', note: 'Paused — not spending any more.' },
  // An ad that is paused with NOTHING recorded — goes live 22 Sep. It must not
  // divide by zero or break the layout.
  { ad_id: '120251268385660121', ad_name: 'Ad_Trial_Spreadsheet_Sep2026',
    name: 'Ad_Trial_Spreadsheet_Sep2026', stream: 'trial', destination: 'betterat.cricket/trial',
    utm_content: 'spreadsheet_hero', ends_on: null, spend: 0, impressions: 0,
    link_clicks: 0, link_ctr: 0, landing_page_views: 0, cost_per_lpv: null, leads: 0,
    cost_per_lead: null, delivery_status: 'PAUSED', status: 'paused', note: 'Paused — live from 22 Sep.' },
]

const SUMMARY = {
  token_configured: true,
  campaign: {
    ad_id: null, ad_name: null, spend: 1920.29, impressions: 231168, link_clicks: 1962,
    link_ctr: 2.0, landing_page_views: 1753, cost_per_lpv: 1.1, leads: 20,
    delivery_status: null, leads_adjustment: 0,
    registrations: TRIAL_RESULTS, leads_effective: TRIAL_RESULTS,
    webinar_registrations: { attributed: WEBINAR_RESULTS, unattributed: 3, total: 15 },
    cost_per_lead: Number((TRIAL_SPEND / TRIAL_RESULTS).toFixed(2)),
    cost_per_trial_signup: Number((TRIAL_SPEND / TRIAL_RESULTS).toFixed(2)),
    cost_per_webinar_registration: Number((WEBINAR_SPEND / WEBINAR_RESULTS).toFixed(2)),
  },
  ads: ADS,
  streams: STREAMS,
  creatives: [
    { utm_content: 'club_history_hero', stream: 'trial', ad_name: 'Ad_ClubHistory_Trial_Hero_v3',
      spend: TRIAL_SPEND, impressions: 220000, link_clicks: 1760, landing_page_views: 1600,
      trial_signups: TRIAL_RESULTS, webinar_registrations: 0, results: TRIAL_RESULTS,
      cost_per_result: Number((TRIAL_SPEND / TRIAL_RESULTS).toFixed(2)), cost_per_lpv: 1.13 },
    { utm_content: 'live_demo_hero', stream: 'webinar', ad_name: 'Ad_Webinar_LiveDemo_21Sep2026_v2',
      spend: WEBINAR_SPEND, impressions: 9000, link_clicks: 200, landing_page_views: 150,
      trial_signups: 0, webinar_registrations: WEBINAR_RESULTS, results: WEBINAR_RESULTS,
      cost_per_result: Number((WEBINAR_SPEND / WEBINAR_RESULTS).toFixed(2)), cost_per_lpv: 0.8 },
  ],
  unattributed_spend: 0.29,
  annotations: [{ date: CHANGE_DATE, label: 'Campaign restructured',
                  detail: 'Budget A$50 → A$30/day; Facebook Feed only; /demo added alongside /trial.' }],
  attribution_window_days: 7,
  recommendation: 'Keep going.', recommendation_status: 'keep_going',
  last_updated: new Date().toISOString(), leads_adjustment: 0,
  campaign_budget: 900, campaign_length_days: 30,
  insights: [{ severity: 'info', title: 'Two results at two prices',
               detail: 'Webinar registrations cost $10.00 each, Free trial signups $43.90.' }],
  counting_since: null,
}

// 14 days of daily rows; the last 7 flagged provisional exactly as the backend
// flags them, so the shaded band is measured against real rows.
const HISTORY = Array.from({ length: 14 }, (_, i) => {
  const day = 13 - i
  return {
    date: iso(day),
    spend: day > 10 ? 50 : 30,
    impressions: 8000, link_clicks: 70, link_ctr: 0.9,
    landing_page_views: 60, cost_per_lpv: 0.9, leads: 1,
    provisional: day < 7,
  }
})

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ summary = SUMMARY, history = HISTORY, width = 1500 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 2600 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))

  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url())
    const p = u.pathname.replace(/^\/api/, '')
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

    if (/\/auth\/me/.test(p)) {
      return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'super_admin',
                    entitlements: { modules: [], status: 'active' } })
    }
    if (/meta-ads\/ad-history/.test(p)) return json({ days: history, token_configured: true })
    if (/meta-ads\/history/.test(p)) return json({ days: history, token_configured: true })
    if (/meta-ads\/summary/.test(p)) return json(summary)
    if (/meta-ads\/campaigns/.test(p)) {
      return json({ campaigns: [{ id: '120250149119070121', name: 'BC_AU_Trials_CBO_Aug2026',
                                  status: 'ACTIVE', effective_status: 'ACTIVE' }],
                    active_campaign_id: '120250149119070121', token_configured: true })
    }
    if (/meta-ads\/leads\/adjustments/.test(p)) return json({ adjustments: [] })
    if (/meta-ads\/registration-funnel/.test(p)) return json({ funnel: [] })
    if (/meta-ads\/selected-clubs/.test(p)) return json({ clubs: [], hidden_clubs: [], identified: 0, hidden_count: 0, anonymous: 0 })
    if (/meta-ads\/searched-clubs/.test(p)) return json({ clubs: [], hidden_clubs: [], identified: 0, hidden_count: 0, searched_only_count: 0, converted_count: 0 })
    if (/meta-ads\/ad-signups/.test(p)) return json({ rows: [], campaigns: [] })
    if (/meta-ads\/counting-since/.test(p)) return json({ since: null })
    if (/usage\/campaigns/.test(p)) return json(null)
    return json([])
  })

  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' })
  // Wait for the thing this suite is about rather than for the network to go
  // quiet — HeartbeatBeacon pings for as long as the tab is open, so
  // networkidle never settles on this app and would hang the run.
  await page.locator('[data-testid="stream-card-trial"]')
    .waitFor({ state: 'visible', timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(1200)
  return { page, ctx, errors }
}

// ─────────────────────────────────────────────────────────────────────────────
const { page, ctx, errors } = await open()

// 1. THE SPLIT ITSELF.
const trialCard = page.locator('[data-testid="stream-card-trial"]')
const webinarCard = page.locator('[data-testid="stream-card-webinar"]')
ck('the trial stream has its own card', await has(trialCard))
ck('the webinar stream has its own card', await has(webinarCard))

const trialResults = await textOf(trialCard.locator('[data-testid="stream-results"]'))
const webinarResults = await textOf(webinarCard.locator('[data-testid="stream-results"]'))
ck('the trial card reports the trial\'s own result count', trialResults.trim() === String(TRIAL_RESULTS),
   `got "${trialResults}"`)
ck('the webinar card reports the webinar\'s own result count', webinarResults.trim() === String(WEBINAR_RESULTS),
   `got "${webinarResults}"`)

const trialCpr = await textOf(trialCard.locator('[data-testid="stream-cpr"]'))
const webinarCpr = await textOf(webinarCard.locator('[data-testid="stream-cpr"]'))
ck('the trial cost per result is its own spend over its own signups (A$43.90)',
   trialCpr.includes('43.90'), `got "${trialCpr}"`)
ck('the webinar cost per result is its own spend over its own registrations (A$10.00)',
   webinarCpr.includes('10.00'), `got "${webinarCpr}"`)
ck('the two costs per result are different figures, never averaged into one',
   trialCpr.trim() !== webinarCpr.trim())

// The number the page used to show: whole-campaign spend over trial signups.
// A$1920.29 / 41 = A$46.84 — the brief's own lifetime figure, and now wrong.
// innerText returns CSS-`uppercase` text ALREADY TRANSFORMED, so anything
// compared against a label the page renders uppercase is compared lowercase
// here. A check written in the source's casing passes whatever the code does.
const bodyRaw = await page.locator('body').innerText()
const body = bodyRaw
const lower = bodyRaw.toLowerCase()

// 2. NO UNLABELLED COMBINED TOTAL. 41 + 12 = 53 must appear nowhere as a
//    conversion count. (A guard against a future combined total rather than a
//    discriminator — the old page had no combined figure either; it simply
//    reported the trial's and called it "registrations".)
ck('no combined 53 registrations total anywhere', !/\b53\b/.test(body))
// The heading the old page used. Case-insensitive because innerText returns
// CSS-`uppercase` text transformed — written in the source's casing this
// passed against the old page for the wrong reason.
ck('the old unqualified "Free trial registrations" heading is gone',
   !/free trial registrations/i.test(bodyRaw))
ck('each stream names the pixel content_category that separates the two',
   lower.includes('self_serve_trial') && lower.includes('webinar'))

// 3. VALUE EXCLUDES THE WEBINAR.
const webinarText = await textOf(webinarCard)
ck('the webinar card says it carries no value and is out of revenue/ROAS',
   /carries no value/i.test(webinarText), `got "${webinarText.slice(0, 160)}"`)
ck('the trial card does NOT claim to carry no value',
   (await has(trialCard)) && !/carries no value/i.test(await textOf(trialCard)))

// 4. THE UNTAGGED-LINK SHORTFALL IS REPORTED, NOT ABSORBED.
ck('the webinar card names the registrations that arrived with no campaign tag',
   /no campaign tag/i.test(webinarText), `got "${webinarText.slice(0, 200)}"`)

// 5. UNATTRIBUTED SPEND. A few cents of rounding is noise and stays quiet; a
//    real gap (a deleted ad) is called out rather than charged to a stream.
ck('a few cents of rounding does not raise a note',
   !(await has(page.locator('[data-testid="unattributed-spend"]'))))

// 6. ONE FUNNEL PER STREAM, each ending in its own result.
const funnelTitles = await page.locator('text=/impressions to a registration/i').count()
ck('there are two funnels, one per stream', funnelTitles === 2, `found ${funnelTitles}`)
// Read off the funnel cards themselves. `body.includes(...)` also matched the
// insight prose above them, so it passed with no funnel on the page at all.
const funnelCards = page.locator('div.pb-card', { hasText: /impressions to a registration/i })
const funnelText = (await funnelCards.count())
  ? (await funnelCards.allInnerTexts()).join('\n') : ''
ck('the trial funnel keeps the Club selected step', /club selected/i.test(funnelText))
ck('the webinar funnel ends in its own result, not the trial\'s',
   /webinar registrations/i.test(funnelText))

// 7. THE 8 SEP CHANGE IS DRAWN AND EXPLAINED.
ck('the campaign change is named under the charts', body.includes('Campaign restructured'))
ck('the change explains what actually changed', /A\$50/.test(body) && /A\$30/.test(body))
const markers = await page.locator('svg line[stroke="#f59e0b"]').count()
ck('a change marker is drawn on every trend chart', markers >= 4, `found ${markers} marker lines`)

// 8. THE TRAILING SEVEN DAYS READ AS PROVISIONAL.
ck('the trailing days are described as still settling', /still settling/i.test(body))
ck('the reason is given — Meta attributes to the date of the click',
   /date of the click/i.test(bodyRaw))
// Recharts draws a ReferenceArea as a <path class="recharts-reference-area-rect">,
// NOT a <rect> — the first cut of this check selected `svg rect` and reported
// zero against code that was drawing the band correctly. Measured on the real
// element, and on its WIDTH: a band present but collapsed to nothing would
// pass a bare presence check while covering none of the days it is about.
const bands = await page.evaluate(() =>
  Array.from(document.querySelectorAll('path.recharts-reference-area-rect'))
    .map((p) => ({
      opacity: Number(p.getAttribute('fill-opacity')),
      width: p.getBBox().width,
      plotWidth: p.ownerSVGElement?.getBoundingClientRect().width || 0,
    })))
ck('a shaded band is drawn on every trend chart', bands.length >= 4, `found ${bands.length}`)
// `.every()` on an empty array is vacuously true, so both of these assert
// there ARE bands first — otherwise they pass on a page drawing none.
ck('the band is visible but does not obscure the series',
   bands.length > 0 && bands.every((b) => b.opacity > 0 && b.opacity < 0.3),
   JSON.stringify(bands[0] || {}))
ck('it covers roughly the trailing half of a 14-day window (7 of 14 days)',
   bands.length > 0
   && bands.every((b) => b.width > 0 && b.width / b.plotWidth > 0.3 && b.width / b.plotWidth < 0.7),
   JSON.stringify(bands.map((b) => Math.round(100 * b.width / b.plotWidth))))

// 9. CREATIVE-LEVEL VIEW KEYED ON utm_content.
ck('there is a creative table', await has(page.locator('[data-testid="creative-table"]')))
ck('it is keyed on utm_content', lower.includes('utm_content'))
const creativeRows = await page.locator('[data-testid="creative-row"]').count()
ck('every creative gets a row', creativeRows === 2, `found ${creativeRows}`)
const creativeText = await textOf(page.locator('[data-testid="creative-table"]'))
ck('each creative names the tag it is identified by',
   creativeText.includes('club_history_hero') && creativeText.includes('live_demo_hero'))
ck('a creative keeps its two result counts apart',
   /trial signups/i.test(creativeText) && /webinar regs/i.test(creativeText))

// 10. PAUSED AND ENDED ADS DON'T BREAK ANYTHING.
ck('the ad that has not gone live yet is still listed', body.includes('Ad_Trial_Spreadsheet_Sep2026'))
ck('the dated ad says when it stops being relevant', /Runs to/i.test(body))
ck('no NaN or Infinity anywhere from a zero-spend or zero-result division',
   !/NaN|Infinity/.test(body), body.match(/.{0,40}(NaN|Infinity).{0,40}/)?.[0] || '')
ck('each ad card says which of the two products it sells',
   (await page.locator('span:text-is("webinar")').count()) > 0
   && (await page.locator('span:text-is("trial")').count()) > 0)

// 11. Housekeeping.
ck('no page errors', errors.length === 0, errors[0] || '')

// A stream with nothing recorded at all — the state the webinar was in before
// 8 Sep, and the trial will be in on a brand-new campaign.
await ctx.close()
const empty = await open({
  summary: {
    ...SUMMARY,
    streams: STREAMS.map((s) => ({
      ...s, spend: 0, impressions: 0, link_clicks: 0, landing_page_views: 0,
      results: 0, cost_per_result: null, roas: null, attributed_value_aud: 0,
      ad_count: 0, active_ad_count: 0,
      funnel: s.funnel.map((f) => ({ ...f, value: 0, pct_of_top: 0, pct_of_prev: 0 })),
    })),
    creatives: [], unattributed_spend: 0,
  },
  history: [],
})
const emptyBody = await empty.page.locator('body').innerText()
ck('a stream with no spend says so rather than showing a cost per result',
   /no cost per result yet/i.test(emptyBody))
ck('nothing divides by zero on an empty campaign', !/NaN|Infinity/.test(emptyBody))
ck('no creative table is drawn when there is nothing to compare',
   !(await has(empty.page.locator('[data-testid="creative-table"]'))))
ck('no page errors on an empty campaign', empty.errors.length === 0, empty.errors[0] || '')
await empty.ctx.close()

// Mobile.
const narrow = await open({ width: 390 })
const overflow = await narrow.page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth)
ck('no horizontal overflow at 390px', overflow <= 0, `${overflow}px over`)
ck('both stream cards still render at 390px',
   await has(narrow.page.locator('[data-testid="stream-card-trial"]'))
   && await has(narrow.page.locator('[data-testid="stream-card-webinar"]')))
await narrow.ctx.close()

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
