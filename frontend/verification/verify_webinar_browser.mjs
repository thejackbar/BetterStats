// Drives the real /demo and /trial pages in Chromium, with the API stubbed at
// the network layer and `fbq`/`gtag` replaced by recorders.
//
//   npx vite --port 5203 &
//   node frontend/verification/verify_webinar_browser.mjs [baseUrl]
//
// THE CHECKS THAT MATTER MOST ARE ABOUT WHEN THE PIXEL FIRES. The Meta ad set
// optimises for `CompleteRegistration`, so a copy of it that fires on page
// load, on the click, or on a validation failure poisons the ad set's
// optimisation immediately — and none of that is observable from the backend.
// So every one of those is asserted here by recording what `fbq` was actually
// called with, in order, rather than by reading the source.
//
// Also here because only a browser can see them: the exact payload on the
// wire (UTMs and fbclid captured end to end from the landing URL), the
// date-driven before/after states, the graceful-failure path, and no
// horizontal overflow at 390px.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5203'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const WATCH = 'https://streamyard.com/watch/ibBKm5Ek4sQu'
const RECORDING = 'https://youtu.be/rec123'

// The real ad landing URL shape: campaign tags plus Meta's own click id.
const AD_QUERY = '?utm_source=fb&utm_medium=paid_social&utm_campaign=BC_AU_Trials_CBO_Aug2026'
  + '&utm_content=demo_4x5_v1&utm_term=committee&fbclid=IwAR0abcdef123'

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

/**
 * Open a page with the API stubbed and the pixel recorded.
 *
 * `registerStatus` / `registerBody` drive what POST /register answers, so the
 * new-registration, already-registered and server-error paths are all real
 * round trips rather than mocked-out component state.
 */
async function open(path, {
  isPast = false, recordingUrl = null, width = 1440,
  registerStatus = 200, registerBody = null, selfServeEnabled = true,
  registerDelayMs = 0,
} = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1800 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  // Every fbq/gtag call, in the order they happened — the order IS the check
  // for "fires only on success".
  const pixel = []

  page.on('pageerror', (e) => errors.push(String(e)))
  // fbq is safe to stub in an init script — index.html's own loader bails out
  // early when window.fbq already exists. gtag is NOT: index.html unconditionally
  // redefines it (`function gtag(){dataLayer.push(arguments)}`), so a recorder
  // installed here is replaced before the app runs. GA4's own function pushes
  // into window.dataLayer, so gtag calls are read back from there instead.
  await page.addInitScript(() => {
    window.__pixel = []
    window.fbq = (...args) => { window.__pixel.push({ lib: 'fbq', args }) }
    window.fbq.callMethod = null
  })

  const details = {
    key: 'webinar-2026-09-21',
    title: 'BetterCricket live demo + Q&A',
    starts_at: '2026-09-21T09:30:00Z',
    ends_at: '2026-09-21T10:30:00Z',
    date_label: 'Monday 21 September',
    time_label: '5:30pm AWST / 7:30pm AEST',
    is_past: isPast,
    watch_url: isPast ? recordingUrl : WATCH,
    recording_available: !!(isPast && recordingUrl),
    google_calendar_url: 'https://calendar.google.com/calendar/render?action=TEMPLATE',
    roles: ['President', 'Secretary', 'Committee', 'Coach', 'Captain', 'Player', 'Other'],
  }

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    let body = null
    try { body = req.postData() ? JSON.parse(req.postData()) : null } catch { /* not json */ }
    calls.push({ path: p, method: req.method(), body })
    const json = (payload, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(payload),
    })

    if (p === '/public/webinar' && req.method() === 'GET') return json(details)
    if (p === '/public/webinar/register') {
      if (registerDelayMs) await new Promise((r) => setTimeout(r, registerDelayMs))
      if (registerStatus !== 200) return json({ detail: 'Something went wrong on our end.' }, registerStatus)
      return json(registerBody || { ok: true, created: true, ...details })
    }
    if (p === '/public/self-serve/status') {
      return selfServeEnabled ? json({ enabled: true, default_trial_days: 14 }) : json({ detail: 'off' }, 404)
    }
    if (p === '/public/self-serve/search') return json([])
    if (/^\/clubs\//.test(p)) return json({ detail: 'Not found' }, 404)
    // Telemetry and anything else — answered so nothing hangs, and never
    // counted as a registration call.
    return json({ ok: true })
  })

  // NOT 'networkidle': the app mounts a usage heartbeat that pings every ~25s,
  // so the network never goes idle and the load hangs. Wait for the thing the
  // checks are about instead.
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('#main-content', { timeout: 15000 })
  if (path.startsWith('/demo')) await page.waitForSelector('[data-testid="demo-form"]', { timeout: 15000 })
  const readPixel = async () => page.evaluate(() => [
    ...(window.__pixel || []),
    ...Array.from(window.dataLayer || []).map((a) => ({ lib: 'gtag', args: Array.from(a) })),
  ])
  return { page, ctx, errors, calls, pixel, readPixel }
}

const registrations = (calls) => calls.filter((c) => c.path === '/public/webinar/register')
const completeReg = (px) => px.filter((e) => e.lib === 'fbq' && e.args[1] === 'CompleteRegistration')

async function fill(page, {
  name = 'Sam Committee', email = 'sam@example.com', club = 'Applecross CC',
  phone = '0412 345 678',
} = {}) {
  if (name !== null) await page.fill('#demo-name', name)
  if (email !== null) await page.fill('#demo-email', email)
  if (club !== null) await page.fill('#demo-club', club)
  // Presence-checked, not filled blind: against a build without the field a
  // bare fill() hangs on the locator and takes the whole run down with it —
  // a control run that crashes is not a control run.
  if (phone !== null && await page.locator('#demo-phone').count() === 1) {
    await page.fill('#demo-phone', phone)
  }
}

// Read an attribute without waiting for an element that may not exist.
async function attrOf(page, selector, name) {
  if (await page.locator(selector).count() !== 1) return null
  return page.locator(selector).getAttribute(name)
}

// ---------------------------------------------------------------- before ----
{
  console.log('\n-- /demo before the event --')
  const { page, ctx, errors, calls, readPixel } = await open(`/demo${AD_QUERY}`)

  const h1 = (await page.locator('h1').first().innerText()).trim()
  // Message match: the ad creative reads "See BetterCricket in action". A
  // scent mismatch between the ad and the page is the biggest single cause of
  // bounce on paid traffic.
  ck('the H1 echoes the ad creative', /see bettercricket in action/i.test(h1), h1)
  const sub = await page.locator('#main-content').innerText()
  ck('the sub-headline is there', /The entire platform\. Your questions answered\./.test(sub))
  const when = (await page.getByTestId('demo-when').innerText()).trim()
  ck('the date and both timezones are shown',
    /Monday 21 September/.test(when) && /5:30pm AWST/.test(when) && /7:30pm AEST/.test(when), when)

  // THE FORM MUST BE VISIBLE WITHOUT SCROLLING PAST THE HERO, not behind a
  // button that scrolls or opens a modal.
  ck('the form is inline on the page, not behind a button',
    await page.getByTestId('demo-form').isVisible())
  ck('the submit button reads "Register now"',
    (await page.getByTestId('demo-submit').innerText()).trim() === 'Register now')
  ck('and the "register anyway" recording line is under it',
    /Can’t make it live\? Register anyway/.test(sub))

  // Four fields now, and the role picker still collapsed. The phone was
  // asked for directly after the page shipped; the brief's own three-field
  // rule is what keeps the role optional and out of the way.
  ck('name, email, club and phone are all present',
    await page.locator('#demo-name').count() === 1
    && await page.locator('#demo-email').count() === 1
    && await page.locator('#demo-club').count() === 1
    && await page.locator('#demo-phone').count() === 1)
  ck('the optional role field is collapsed by default',
    await page.locator('#demo-role').count() === 0)
  await page.getByTestId('demo-role-toggle').click()
  ck('and opens when asked', await page.locator('#demo-role').count() === 1)
  ck('offering the seven roles',
    await page.locator('#demo-role option').count() === 8)   // 7 + "prefer not to say"

  // Autocomplete: a phone keyboard filling these in is most of this traffic.
  ck('the name field autocompletes',
    await page.locator('#demo-name').getAttribute('autocomplete') === 'name')
  ck('the email field autocompletes',
    await page.locator('#demo-email').getAttribute('autocomplete') === 'email')
  ck('the club field autocompletes as an organisation',
    await page.locator('#demo-club').getAttribute('autocomplete') === 'organization')
  ck('the phone field autocompletes as a phone number',
    await attrOf(page, '#demo-phone', 'autocomplete') === 'tel')
  // What puts a keypad rather than a full keyboard in front of the ~all of
  // this traffic that is on a phone.
  ck('and asks for a phone keypad',
    await attrOf(page, '#demo-phone', 'inputmode') === 'tel'
    && await attrOf(page, '#demo-phone', 'type') === 'tel')
  ck('every field has a real label',
    await page.locator('label[for="demo-name"]').count() === 1
    && await page.locator('label[for="demo-email"]').count() === 1
    && await page.locator('label[for="demo-club"]').count() === 1
    && await page.locator('label[for="demo-phone"]').count() === 1)

  // THE PIXEL MUST NOT HAVE FIRED YET.
  let px = await readPixel()
  ck('no CompleteRegistration on page load', completeReg(px).length === 0,
    JSON.stringify(px.map((e) => e.args[1])))
  ck('but the softer ViewContent intent signal did fire',
    px.some((e) => e.lib === 'fbq' && e.args[1] === 'ViewContent'))

  // A validation failure must not fire it either, and must not post.
  await page.getByTestId('demo-submit').click()
  await page.waitForTimeout(250)
  px = await readPixel()
  ck('an empty form fires no CompleteRegistration', completeReg(px).length === 0)
  ck('and posts nothing at all', registrations(calls).length === 0)
  ck('it reports which fields are missing',
    /Add your name\./.test(await page.getByTestId('demo-form').innerText()))
  ck('and marks them invalid for a screen reader',
    await page.locator('#demo-name[aria-invalid="true"]').count() === 1)

  await fill(page, { email: 'not-an-email' })
  await page.getByTestId('demo-submit').click()
  await page.waitForTimeout(250)
  ck('a malformed email is caught before posting', registrations(calls).length === 0)
  ck('and fires no CompleteRegistration', completeReg(await readPixel()).length === 0)

  // The phone is required, so the same has to hold for it — caught in the
  // browser, nothing posted, and no conversion claimed.
  //
  // The WHOLE block is gated on the field existing. Against a build without
  // it these submissions SUCCEED, the form is replaced by the success state,
  // and every later check in this section hangs on a form that is gone — a
  // control run that crashes is not a control run. Absent, the three checks
  // report and the page is left exactly as it was.
  if (await page.locator('#demo-phone').count() === 1) {
    await fill(page, { phone: '' })
    await page.getByTestId('demo-submit').click()
    await page.waitForTimeout(300)
    ck('a missing phone is caught before posting', registrations(calls).length === 0)
    ck('and it says which field is missing',
      /Add your phone number\./.test(await page.getByTestId('demo-form').innerText()))
    // A landline is a perfectly good number to ring a club secretary on, so
    // the rule is 'could be a phone number', never 'is an Australian mobile'.
    await fill(page, { phone: '1234' })
    await page.getByTestId('demo-submit').click()
    await page.waitForTimeout(300)
    ck('and so is one with too few digits to be a phone number',
      registrations(calls).length === 0 && completeReg(await readPixel()).length === 0)
    await fill(page, { phone: '(08) 9364 1234' })
  } else {
    ck('a missing phone is caught before posting', false, 'no phone field')
    ck('and it says which field is missing', false, 'no phone field')
    ck('and so is one with too few digits to be a phone number', false, 'no phone field')
  }

  // Now a real submission.
  await page.fill('#demo-email', 'sam@example.com')
  await page.selectOption('#demo-role', 'Secretary')
  await page.getByTestId('demo-submit').click()
  await page.getByTestId('demo-success').waitFor({ timeout: 5000 })

  const posts = registrations(calls)
  ck('exactly one registration is posted', posts.length === 1, String(posts.length))
  const sent = posts[0]?.body || {}
  ck('carrying the name', sent.name === 'Sam Committee', JSON.stringify(sent.name))
  ck('the email', sent.email === 'sam@example.com')
  ck('the club', sent.club === 'Applecross CC')
  // Exactly as typed, spaces and brackets and all — the server stores what a
  // person wrote rather than a form of it nobody would recognise.
  ck('the phone as it was typed', sent.phone === '(08) 9364 1234', JSON.stringify(sent.phone))
  ck('and the role that was picked', sent.role === 'Secretary')

  // UTMs AND fbclid, end to end from the landing URL — captured by the same
  // lib/visitor.js the rest of the site uses, not a second mechanism.
  const attr = sent.attribution || {}
  ck('utm_source survives to the submission', attr.utm_source === 'fb', JSON.stringify(attr))
  ck('utm_medium too', attr.utm_medium === 'paid_social')
  ck('utm_campaign too', attr.utm_campaign === 'BC_AU_Trials_CBO_Aug2026')
  ck('utm_content too', attr.utm_content === 'demo_4x5_v1')
  ck('utm_term too', attr.utm_term === 'committee')
  ck('and the fbclid, as the click id', attr.click_id === 'IwAR0abcdef123', JSON.stringify(attr.click_id))
  ck('tagged as a facebook click', attr.click_source === 'facebook')
  ck('the visitor id rides along', typeof sent.visitorId === 'string' && sent.visitorId.length > 10)
  ck('the honeypot goes across empty', !sent.website)
  ck('and the form-start time, for the fill-speed check', typeof sent.formStartedAt === 'number')
  // Meta counts the browser and server copies as one event only if both carry
  // the same id.
  ck('an event_id is sent for the server copy to share',
    typeof sent.meta?.eventId === 'string' && sent.meta.eventId.length > 8)

  // AND NOW THE PIXEL.
  px = await readPixel()
  const cr = completeReg(px)
  ck('CompleteRegistration fires exactly once, on success', cr.length === 1, String(cr.length))
  ck('with content_category "webinar"', cr[0]?.args[2]?.content_category === 'webinar',
    JSON.stringify(cr[0]?.args[2]))
  ck('and a content_name naming the event',
    /Webinar Registration/.test(cr[0]?.args[2]?.content_name || ''),
    JSON.stringify(cr[0]?.args[2]?.content_name))
  ck('sharing the same event_id the server got',
    cr[0]?.args[3]?.eventID === sent.meta.eventId,
    `${cr[0]?.args[3]?.eventID} vs ${sent.meta.eventId}`)
  ck('and the analytics-side event fires too, for reconciliation',
    px.some((e) => e.lib === 'gtag' && e.args[1] === 'sign_up'))

  // The success state. NOT a redirect — the beacon has to get out, and there
  // is a calendar and an inbox note to hand over.
  ck('the page is still on /demo, not redirected to StreamYard',
    new URL(page.url()).pathname === '/demo', page.url())
  ck('the success state confirms the registration',
    /YOU’RE REGISTERED/i.test(await page.getByTestId('demo-success').innerText()))
  ck('the StreamYard link is handed over',
    await page.getByTestId('demo-watch-link').getAttribute('href') === WATCH)
  ck('opening in a new tab so the page is not lost',
    await page.getByTestId('demo-watch-link').getAttribute('target') === '_blank')
  ck('a Google Calendar link is offered',
    /calendar\.google\.com/.test(await page.getByTestId('demo-gcal').getAttribute('href')))
  ck('and a downloadable .ics for Outlook and Apple',
    (await page.getByTestId('demo-ics').getAttribute('href')) === '/api/public/webinar/calendar.ics')
  ck('and it says the link is in their inbox too',
    /in your inbox/i.test(await page.getByTestId('demo-success').innerText()))

  // The secondary path, present but subordinate.
  const trialCta = page.locator('a[href="/trial"]')
  ck('the trial CTA is in the success state too', await trialCta.count() >= 1)
  ck('reading as a secondary offer, not a second primary',
    /Not ready for a live demo/.test(await page.getByTestId('demo-success').locator('..').innerText()))

  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// -------------------------------------------------- the trial CTA position ----
{
  console.log('\n-- the trial CTA must not compete above the fold --')
  const { page, ctx } = await open('/demo', { width: 390 })
  const form = await page.getByTestId('demo-submit').boundingBox()
  const cta = await page.locator('a[href="/trial"]').first().boundingBox()
  // Measured, not read off the source order: the registration button is what
  // this page is paid for, so the trial offer has to sit below it.
  ck('the trial CTA sits BELOW the register button on a phone',
    cta && form && cta.y > form.y, `cta ${cta?.y} vs submit ${form?.y}`)
  await ctx.close()
}

// ---------------------------------------------------- already registered ----
{
  console.log('\n-- registering twice is one lead, not two conversions --')
  const { page, ctx, readPixel } = await open('/demo', {
    registerBody: {
      ok: true, created: false, is_past: false, watch_url: WATCH,
      date_label: 'Monday 21 September', time_label: '5:30pm AWST / 7:30pm AEST',
      recording_available: false, roles: [],
    },
  })
  await fill(page)
  await page.getByTestId('demo-submit').click()
  await page.getByTestId('demo-success').waitFor({ timeout: 5000 })
  ck('they are still shown the link', await page.getByTestId('demo-watch-link').count() === 1)
  // This is what stops the ad set optimising toward people who submit twice.
  ck('but NO CompleteRegistration fires', completeReg(await readPixel()).length === 0)
  ck('and no analytics sign_up either',
    !(await readPixel()).some((e) => e.lib === 'gtag' && e.args[1] === 'sign_up'))
  await ctx.close()
}

// ------------------------------------------------------- graceful failure ----
{
  console.log('\n-- a broken backend must not trap a registered user --')
  const { page, ctx, errors, readPixel } = await open('/demo', { registerStatus: 500 })
  await fill(page)
  await page.getByTestId('demo-submit').click()
  await page.getByTestId('demo-fallback-link').waitFor({ timeout: 5000 })
  ck('the StreamYard link is shown anyway',
    await page.getByTestId('demo-fallback-link').getAttribute('href') === WATCH)
  // Nothing was registered, so nothing may be claimed — a conversion we
  // invented is worse for the ad set than one we missed.
  ck('but no CompleteRegistration is claimed', completeReg(await readPixel()).length === 0)
  ck('and the page did not crash', errors.length === 0, errors.join(' | '))
  ck('with a way back to try again',
    await page.getByText('Try registering again').count() === 1)
  await ctx.close()
}

// ------------------------------------------------- the double-fire guard ----
{
  console.log('\n-- the button cannot be double-fired --')
  // The response is held for a moment so the in-flight state is genuinely
  // observable rather than a race with the round trip.
  const { page, ctx, calls, readPixel } = await open('/demo', { registerDelayMs: 900 })
  await fill(page)
  const submit = page.getByTestId('demo-submit')
  await submit.click()
  // While the request is in flight the button must refuse further presses —
  // otherwise an impatient double-tap posts twice and claims the conversion
  // twice for one registration.
  ck('the button disables itself while the request is in flight',
    await submit.isDisabled())
  ck('and says so', /Registering/.test((await submit.innerText()).trim()),
    (await submit.innerText()).trim())
  // Dispatched rather than clicked: a real click on a disabled button is a
  // no-op the browser swallows, so this is the harder case - the event
  // arriving anyway.
  await submit.dispatchEvent('click')
  await page.getByTestId('demo-success').waitFor({ timeout: 8000 })
  ck('only one registration is posted', registrations(calls).length === 1,
    String(registrations(calls).length))
  ck('and CompleteRegistration fires only once', completeReg(await readPixel()).length === 1)
  await ctx.close()
}

// ------------------------------------------------------------ after ----
{
  console.log('\n-- /demo after the event, recording published --')
  const { page, ctx, errors, readPixel } = await open('/demo', {
    isPast: true, recordingUrl: RECORDING,
    registerBody: {
      ok: true, created: true, is_past: true, watch_url: RECORDING,
      recording_available: true, date_label: 'Monday 21 September',
      time_label: '5:30pm AWST / 7:30pm AEST', roles: [],
    },
  })
  const h1 = (await page.locator('h1').first().innerText()).trim()
  ck('the H1 becomes "Watch the BetterCricket demo"', /watch the bettercricket demo/i.test(h1), h1)
  const when = (await page.getByTestId('demo-when').innerText()).trim()
  ck('the date block reads "Recorded 21 September 2026"',
    /Recorded 21 September 2026/.test(when), when)
  ck('and no longer advertises a live time', !/5:30pm AWST/.test(when), when)
  ck('the button becomes "Get the recording"',
    (await page.getByTestId('demo-submit').innerText()).trim() === 'Get the recording')

  await fill(page)
  await page.getByTestId('demo-submit').click()
  await page.getByTestId('demo-success').waitFor({ timeout: 5000 })
  ck('the recording link is served, not the dead live link',
    await page.getByTestId('demo-watch-link').getAttribute('href') === RECORDING)
  // The pixel event is deliberately unchanged after the event, so the
  // conversion history stays continuous.
  ck('CompleteRegistration still fires, under the same category',
    completeReg(await readPixel())[0]?.args[2]?.content_category === 'webinar')
  ck('and no calendar controls, for an event that has been and gone',
    await page.getByTestId('demo-gcal').count() === 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  console.log('\n-- /demo after the event, no recording yet --')
  const { page, ctx } = await open('/demo', { isPast: true, recordingUrl: null })
  await fill(page)
  await page.getByTestId('demo-submit').click()
  await page.getByTestId('demo-success').waitFor({ timeout: 5000 })
  const text = await page.getByTestId('demo-success').innerText()
  ck('it says the recording is on its way', /recording is on its way/i.test(text), text)
  // Never a link that goes nowhere.
  ck('and offers no link at all', await page.getByTestId('demo-watch-link').count() === 0)
  await ctx.close()
}

// -------------------------------------------------------- /trial promo ----
{
  console.log('\n-- the /trial promo block --')
  const { page, ctx, errors, calls, readPixel } = await open('/trial')
  const promo = page.getByTestId('trial-webinar-promo')
  await promo.waitFor({ timeout: 5000 })
  const text = await promo.innerText()
  ck('it offers the guided tour', /Want a guided tour first\?/.test(text), text)
  ck('naming the date and both timezones',
    /Monday 21 September/.test(text) && /5:30pm AWST/.test(text) && /7:30pm AEST/.test(text))
  ck('the CTA reads "Save your spot"', /Save your spot/.test(text))
  ck('and links to /demo',
    await promo.locator('a').first().getAttribute('href') === '/demo')

  // Placement: the trial page's job is trial signups, so this must not sit
  // above the search box it would compete with.
  const search = await page.locator('input[aria-label="Search for your club"]').boundingBox()
  const box = await promo.boundingBox()
  ck('it sits BELOW the club search, not competing with it',
    box && search && box.y > search.y, `promo ${box?.y} vs search ${search?.y}`)

  // No pixel event from here — clicking through and registering is what fires it.
  const px = await readPixel()
  ck('the promo fires no CompleteRegistration', completeReg(px).length === 0)
  ck('and posts no registration', registrations(calls).length === 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// --------------------------------------------------------------- 390px ----
for (const [label, path] of [['/demo', '/demo'], ['/trial', '/trial']]) {
  const { page, ctx, errors } = await open(path, { width: 390 })
  const over = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck(`${label} does not overflow sideways at 390px`, over <= 0, `${over}px`)
  ck(`${label} has no page errors at 390px`, errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
