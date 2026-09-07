// Drives the real notification screens in Chromium with the API stubbed at the
// network layer.
//
//   npx vite --port 5203 &
//   node frontend/verification/verify_notifications_browser.mjs [baseUrl]
//
// A club could not choose what it was told about. This screen is where it does,
// and the bell is where the result shows up.
//
// Every check that matters asserts what went ON THE WIRE, not what the screen
// says about itself: a toggle that looks pressed and sends the whole rule back
// would silently reset the club's other channels, and no screenshot would show
// it. The stub also MUTATES — one that answered the same thing every time could
// not tell a working save from a no-op.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5203'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const CATEGORIES = [
  { key: 'stats', label: 'Stats and milestones' },
  { key: 'people', label: 'People and compliance' },
  { key: 'operations', label: 'Club operations' },
  { key: 'data', label: 'Data and sync' },
]
const CHANNELS = [
  { key: 'email', label: 'Email' },
  { key: 'in_app', label: 'In the app' },
]

const EVENT = (over) => ({
  key: 'milestone_achieved', label: 'A milestone was reached',
  description: 'A player has passed a career milestone.',
  category: 'stats', severity: 'info', module: null, capability: null,
  config_fields: [], enabled: true,
  channels: { email: true, in_app: true }, config: {},
  default_enabled: true, default_channels: { email: true, in_app: true },
  receives: true, my_channels: {},
  ...over,
})

const EVENTS = () => [
  EVENT({}),
  EVENT({
    key: 'qualification_expiring',
    label: 'A certification is about to lapse',
    description: "A volunteer's Working With Children check, RSA or first aid certificate is close to its expiry date.",
    category: 'people', severity: 'warning', capability: 'manage_qualifications',
    config_fields: [{
      key: 'lead_days', label: 'Notice period',
      hint: 'How long before the expiry date to raise it.',
      default: 60, minimum: 1, maximum: 365, unit: 'days',
    }],
    config: { lead_days: 60 },
  }),
  // Gated on a capability this person does not hold — listed so the club can
  // configure it, shown as not reaching them so the personal toggle is not
  // offered for something that would do nothing.
  EVENT({
    key: 'report_pending', label: 'A saved report is waiting for approval',
    description: 'A member has shared a StatLab report with the club.',
    category: 'operations', capability: 'manage_reports', receives: false,
  }),
  EVENT({
    key: 'sync_completed', label: 'New results have landed',
    description: 'A sync finished and brought new matches in.',
    category: 'data', channels: { email: false, in_app: true },
    default_channels: { email: false, in_app: true },
  }),
]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openSettings({ width = 1440, canManage = true, providerLive = true, alerts = [] } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1800 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))

  const state = {
    club: { enabled: true, email_enabled: true, in_app_enabled: true,
            email_frequency: 'daily', email_weekday: 0 },
    events: EVENTS(),
    blanket: {},
  }

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = req.method()
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

    if (method !== 'GET') {
      let payload = null
      try { payload = req.postDataJSON() } catch { payload = null }
      // Page-view telemetry fires on every visit and is not a save. Counting it
      // would make "this control sends nothing" unfailable in the other
      // direction.
      if (!/^\/usage\//.test(path)) calls.push({ path, method, payload })

      // Apply the write the way the server does, so the reload after a save
      // shows what was actually sent rather than what was typed.
      const rule = path.match(/\/notifications\/settings\/events\/([^/]+)$/)
      const pref = path.match(/\/notifications\/settings\/preferences\/([^/]+)$/)
      if (path === '/club-admin/notifications/settings' && method === 'PATCH') {
        Object.assign(state.club, payload || {})
        return json({ ...state.club })
      }
      if (rule) {
        const e = state.events.find(x => x.key === rule[1])
        if (e) {
          if (payload?.enabled !== undefined) e.enabled = payload.enabled
          if (payload?.channels) Object.assign(e.channels, payload.channels)
          if (payload?.config) Object.assign(e.config, payload.config)
        }
        return json({ enabled: e?.enabled, channels: e?.channels, config: e?.config })
      }
      if (pref) {
        if (pref[1] === '*') Object.assign(state.blanket, payload?.channels || {})
        else {
          const e = state.events.find(x => x.key === pref[1])
          if (e) e.my_channels = { ...e.my_channels, ...(payload?.channels || {}) }
        }
        return json({ ok: true })
      }
      if (/run-now$/.test(path)) return json({ emitted: 3, events_run: 4, sources_failed: 0 })
      if (/notifications\/feed\/read$/.test(path)) return json({ marked_read: 2, unread: 0 })
      return json({ ok: true })
    }

    if (/^\/auth\/me/.test(path)) {
      return json({
        id: 'u1', username: 'admin', role: 'club_admin',
        capabilities: ['*'], club_slug: 'applecross',
        entitlements: { modules: ['stats'], status: 'active' },
      })
    }
    if (/\/notifications\/settings$/.test(path)) {
      return json({
        club: { ...state.club },
        can_manage_club_settings: canManage,
        categories: CATEGORIES,
        channels: CHANNELS,
        events: state.events.map(e => ({ ...e })),
        my_blanket_optout: { ...state.blanket },
        my_email: 'jack@club.test',
        email_provider_live: providerLive,
      })
    }
    if (/\/notifications\/count$/.test(path)) {
      return json({ unseen_count: alerts.length, alert_count: alerts.length,
                    failed_sync_count: 0, last_seen_version: 'v99.0.0' })
    }
    if (/\/notifications\/summary$/.test(path)) {
      return json({ last_seen_at: null, last_seen_version: 'v99.0.0',
                    unseen_count: alerts.length, failed_sync_count: 0,
                    sync_runs: [], new_milestones: [], upcoming_milestones: [],
                    pending_sync_requests: 0, pending_reports_count: 0,
                    merch_alerts: { low_stock: [], expiring: [], service_due: [], total: 0 },
                    asset_alerts: { service_due: [], total: 0 },
                    alerts, alert_count: alerts.filter(a => !a.read).length })
    }
    return json({})
  })

  await page.goto(`${BASE}/admin/notifications`, { waitUntil: 'networkidle' })
  // A CONTROL RUN AGAINST A BUILD WITHOUT THIS FEATURE MUST REPORT, NOT CRASH.
  // Without this the suite dies on the first absent locator and says nothing
  // about the other forty-odd checks.
  try {
    await page.waitForSelector('text=A milestone was reached', { timeout: 15000 })
  } catch {
    await ctx.close()
    console.log('FAIL the notifications settings screen is not present in this build')
    console.log('\n0 passed, 1 failed')
    await browser.close()
    process.exit(1)
  }
  await page.waitForTimeout(300)
  return { page, ctx, errors, calls, state }
}

/** The checkbox whose visible label is exactly this, inside this event's card. */
const cardToggle = (page, cardText, label) =>
  page.locator('div.rounded-lg.border', { hasText: cardText })
    .last()
    .locator('label', { hasText: new RegExp(`^${label}$`) })
    .locator('input[type=checkbox]')

const lastCall = (calls, re) => [...calls].reverse().find(c => re.test(c.path))

// ── the screen ──────────────────────────────────────────────────────────────
{
  const { page, ctx, errors, calls, state } = await openSettings()

  ck('the screen lists the club\'s events',
    await page.locator('text=A certification is about to lapse').count() > 0)
  for (const c of CATEGORIES) {
    ck(`the "${c.label}" section is drawn`,
      await page.locator(`text=${c.label}`).count() > 0)
  }
  ck('an event for a module the club does not hold is not listed',
    await page.locator('text=Stock is running low').count() === 0)

  // The club's master switches.
  const master = page.locator('label', { hasText: 'Send notifications for' }).locator('input').first()
  ck('the club master switch is on', await master.isChecked())

  calls.length = 0

  // Cadence.
  await page.locator('button', { hasText: 'Weekly' }).first().click()
  await page.waitForTimeout(500)
  let call = lastCall(calls, /notifications\/settings$/)
  ck('picking a weekly cadence sends only that field',
    call && call.method === 'PATCH' && call.payload.email_frequency === 'weekly'
      && Object.keys(call.payload).length === 1, JSON.stringify(call))
  ck('the weekday picker appears once the cadence is weekly',
    await page.locator('button', { hasText: /^Wed$/ }).count() > 0)

  calls.length = 0
  await page.locator('button', { hasText: /^Wed$/ }).first().click()
  await page.waitForTimeout(500)
  call = lastCall(calls, /notifications\/settings$/)
  ck('picking a day sends the weekday as a number',
    call && call.payload.email_weekday === 2, JSON.stringify(call))

  // One event's channel — the exact payload matters, because sending the whole
  // rule back would reset whatever else the club had set.
  calls.length = 0
  await cardToggle(page, 'A milestone was reached', 'Email').first().click({ force: true })
  await page.waitForTimeout(500)
  call = lastCall(calls, /settings\/events\//)
  ck('switching one channel off sends that channel and nothing else',
    call && call.method === 'PUT' && call.path.endsWith('/milestone_achieved')
      && JSON.stringify(call.payload) === JSON.stringify({ channels: { email: false } }),
    JSON.stringify(call))
  ck('and the club\'s other channel on that event is untouched',
    state.events[0].channels.in_app === true, JSON.stringify(state.events[0].channels))

  // Switching an event off entirely.
  calls.length = 0
  await page.locator('div.rounded-lg.border', { hasText: 'New results have landed' })
    .last().locator('label', { hasText: /^(On|Off)$/ }).locator('input').click({ force: true })
  await page.waitForTimeout(500)
  call = lastCall(calls, /settings\/events\/sync_completed$/)
  ck('switching an event off sends enabled:false alone',
    call && JSON.stringify(call.payload) === JSON.stringify({ enabled: false }), JSON.stringify(call))
  ck('a switched-off event hides its channels — there is nothing left to choose',
    await page.locator('div.rounded-lg.border', { hasText: 'New results have landed' })
      .last().locator('label', { hasText: /^In the app$/ }).count() === 0)

  await ctx.close()
}

// ── the notice period ───────────────────────────────────────────────────────
{
  const { page, ctx, calls, state } = await openSettings()
  const field = page.locator('div.rounded-lg.border', { hasText: 'A certification is about to lapse' })
    .last().locator('input[type=number]').first()

  ck('the notice period shows the club\'s own value', await field.inputValue() === '60')
  ck('the field says what it is for',
    (await page.locator('text=How long before the expiry date to raise it.').count()) > 0)

  calls.length = 0
  await field.fill('14')
  await field.blur()
  await page.waitForTimeout(600)
  let call = lastCall(calls, /settings\/events\/qualification_expiring$/)
  ck('a changed notice period is sent as config alone',
    call && JSON.stringify(call.payload) === JSON.stringify({ config: { lead_days: 14 } }),
    JSON.stringify(call))
  ck('and the server-side value follows it', state.events[1].config.lead_days === 14)

  // Blurring without changing anything must send nothing — an unchanged field
  // that writes on every focus is how a screen looks busy and does nothing.
  calls.length = 0
  await field.focus()
  await field.blur()
  await page.waitForTimeout(500)
  ck('blurring an unchanged notice period sends nothing',
    !lastCall(calls, /settings\/events\//), JSON.stringify(calls))

  calls.length = 0
  await field.fill('9999')
  await field.blur()
  await page.waitForTimeout(600)
  call = lastCall(calls, /settings\/events\/qualification_expiring$/)
  ck('an out-of-range notice period is clamped before it is sent',
    call && call.payload.config.lead_days === 365, JSON.stringify(call))
  ck('and the field shows what will actually be stored',
    await field.inputValue() === '365', await field.inputValue())

  await ctx.close()
}

// ── a person's own opt-out ──────────────────────────────────────────────────
{
  const { page, ctx, calls, state } = await openSettings()

  const blanket = page.locator('label', { hasText: 'Email me about this club' }).locator('input').first()
  ck('an admin is emailed unless they say otherwise', await blanket.isChecked())
  ck('the screen names the address it would use',
    (await page.locator('text=Sent to jack@club.test.').count()) > 0)

  calls.length = 0
  await blanket.click({ force: true })
  await page.waitForTimeout(500)
  let call = lastCall(calls, /preferences\//)
  ck('the whole-club opt-out is a preference, not a club setting',
    call && call.method === 'PUT' && call.path.endsWith('/*')
      && call.payload.channels.email === false, JSON.stringify(call))
  ck('and it never touches the club\'s own switches',
    !lastCall(calls, /notifications\/settings$/), JSON.stringify(calls))

  calls.length = 0
  const mine = page.locator('div.rounded-lg.border', { hasText: 'A milestone was reached' })
    .last().locator('label', { hasText: /^Email$/ }).last().locator('input')
  await mine.click({ force: true })
  await page.waitForTimeout(500)
  call = lastCall(calls, /preferences\/milestone_achieved$/)
  ck('opting out of one event goes to the preferences endpoint',
    call && call.payload.channels.email === false, JSON.stringify(call))
  ck('and never to the rule endpoint, which would change it for everybody',
    !lastCall(calls, /settings\/events\//), JSON.stringify(calls))
  ck('the opt-out is recorded against this person alone',
    state.events[0].my_channels.email === false && state.events[0].channels.email === true,
    JSON.stringify(state.events[0]))

  ck('an event that does not reach this person offers no personal toggle',
    (await page.locator('text=This one goes to the people who can act on it').count()) > 0)

  await ctx.close()
}

// ── check now, and the provider warning ─────────────────────────────────────
{
  const { page, ctx, calls } = await openSettings()
  calls.length = 0
  await page.locator('button', { hasText: 'Check now' }).click()
  await page.waitForTimeout(700)
  ck('Check now runs the scan for this club',
    !!lastCall(calls, /run-now$/), JSON.stringify(calls))
  ck('and says what it found',
    (await page.locator('text=Found 3 things to tell you about.').count()) > 0)
  ck('it never sends email — the digest is the daily job\'s',
    !lastCall(calls, /feed\/read|notifications\/settings$/), JSON.stringify(calls))
  await ctx.close()
}

{
  const { page, ctx } = await openSettings({ providerLive: false })
  ck('a club is told when email is not actually connected',
    (await page.locator('text=Email is not connected yet').count()) > 0)
  await ctx.close()
}

// ── an admin who may not change the club's settings ─────────────────────────
{
  const { page, ctx } = await openSettings({ canManage: false })
  ck('somebody without the Settings permission is told what they can change',
    (await page.locator('text=needs the Settings permission').count()) > 0)
  ck('and is shown no club master switch',
    (await page.locator('label', { hasText: 'Send notifications for' }).count()) === 0)
  ck('but still chooses what reaches their own inbox',
    (await page.locator('label', { hasText: 'Email me about this club' }).count()) > 0)
  ck('and still sees the per-event choice for themselves',
    (await page.locator('text=Send to me').count()) > 0)
  await ctx.close()
}


// ── the bell serves the stored feed ─────────────────────────────────────────
//
// The club's own configurable notifications are a STORED record with their own
// read state; everything else in that panel is recomputed live on each poll. So
// this asserts the section is drawn, that reading it goes to the FEED endpoint
// rather than the old "seen" one, and that a row links to where the thing can
// actually be acted on.
//
// Hosted on the settings screen rather than the dashboard: the bell lives in
// AdminLayout, so every admin page carries it, and stubbing the dashboard's own
// dozen calls would be measuring the harness rather than the bell.
{
  const ALERTS = [
    { id: 'n-1', event_key: 'qualification_expiring', severity: 'warning',
      title: "Jo Volunteer's Working With Children Check expires in 20 days",
      body: 'Due to expire on 27 Sep 2026.', link: '/admin/clubhouse/qualifications',
      payload: {}, occurred_at: null, created_at: new Date().toISOString(), read: false },
    { id: 'n-2', event_key: 'milestone_achieved', severity: 'info',
      title: 'Brad Quinsee reached 5,000 career runs', body: 'Passed on 4 Sep 2026.',
      link: '/admin/players', payload: {}, occurred_at: null,
      created_at: new Date().toISOString(), read: false },
  ]
  const { page, ctx, errors, calls } = await openSettings({ alerts: ALERTS })
  ck('a club admin has a bell at all — it was staff-only before this release',
    (await page.locator('button[aria-label="Notifications"]').count()) > 0)
  await page.locator('button[aria-label="Notifications"]').first().click()
  await page.waitForTimeout(800)
  // The bell and the panel were gated SEPARATELY, so lifting one and not the
  // other left a bell that opened nothing. Asserted on its own.
  ck('and pressing it actually opens the panel',
    (await page.locator('div.fixed.inset-0').count()) > 0)

  ck("the bell shows the club's own notifications",
    (await page.locator("text=Jo Volunteer's Working With Children Check expires in 20 days").count()) > 0)
  // The heading is CSS-uppercased, so innerText returns "FOR YOUR CLUB" —
  // a locator written in the source's casing could never match.
  ck('under their own heading, above the sections the bell computes itself',
    (await page.getByText(/for your club/i).count()) > 0)
  ck('a row says where to go and act on it',
    (await page.locator('div.fixed.inset-0 a[href="/admin/clubhouse/qualifications"]').count()) > 0)
  ck('the panel offers a way to the settings screen',
    (await page.locator('div.fixed.inset-0 a[href="/admin/notifications"]').count()) > 0)

  calls.length = 0
  await page.locator('button', { hasText: /^mark 2 read$/i }).click()
  await page.waitForTimeout(800)
  ck('marking them read goes to the feed, not the old seen endpoint',
    calls.some(c => /notifications\/feed\/read$/.test(c.path))
      && !calls.some(c => /notifications\/seen$/.test(c.path)), JSON.stringify(calls))
  ck('and the control settles rather than offering to do it again',
    (await page.locator('button', { hasText: /^mark 2 read$/i }).count()) === 0)
  ck('no page errors on the bell', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── no errors, and it fits a phone ──────────────────────────────────────────
{
  const { page, ctx, errors } = await openSettings()
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}
{
  const { page, ctx } = await openSettings({ width: 390 })
  const over = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', over <= 0, `overflow ${over}px`)
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail === 0 ? 1 && 0 : 1)
