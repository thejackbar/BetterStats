// Drives the paid funnel end to end in Chromium, with the API stubbed at the
// network layer and `fbq` replaced by a recorder:
//
//   ad click -> /trial?utm..&fbclid -> search -> a club's dashboard (client-side
//   navigation, so the query string has left the address bar) -> "Check out your club"
//   -> the registration wizard -> a completed registration.
//
//   npx vite preview --port 5207 &
//   node frontend/verification/verify_club_cta_browser.mjs [baseUrl]
//
// What only a browser can show: the prompt on the dashboard with no scrolling,
// the club's own name in it, nobody but a prospect seeing it, the campaign
// params surviving the hops onto the submit payload, and CompleteRegistration
// firing once, on success, never on a click or a failed submit.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5207'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const AD_QUERY = '?utm_source=facebook&utm_medium=paid_social&utm_campaign=BC_AU_Trials_CBO_Aug2026'
  + '&utm_content=trial_4x5_v2&fbclid=IwAR0clubcta123'

const CLUB = { id: '11111111-1111-1111-1111-111111111111', slug: 'applecross', name: 'Applecross Cricket Club', short_name: 'Applecross', is_active: true }
const NEW_CLUB = { id: '22222222-2222-2222-2222-222222222222', name: 'Brand New Cricket Club' }

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1440, signedIn = false, submitStatus = 200 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 500 ? 800 : 900 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(6000)
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.addInitScript(() => {
    window.__fbq = []
    window.fbq = (...args) => { window.__fbq.push(args) }
  })
  const posts = {}
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (req.method() === 'POST') {
      let body = null
      try { body = req.postDataJSON() } catch { /* not json */ }
      posts[p] = body
    }
    if (p === '/auth/me') return signedIn ? json({ id: 'u1', username: 'admin', role: 'club_admin', club_id: CLUB.id }) : json({ detail: 'Not authenticated' }, 401)
    if (p === '/public/self-serve/status') return json({ enabled: true, default_trial_days: 14 })
    if (p === '/public/self-serve/search') {
      const q = (url.searchParams.get('q') || '').toLowerCase()
      if (q.startsWith('apple')) return json([{ ...CLUB, id: CLUB.id, already_registered: true, already_registered_slug: 'applecross' }])
      return json([{ id: NEW_CLUB.id, name: NEW_CLUB.name, already_registered: false }])
    }
    if (p === '/public/self-serve/prepare') return json({ org_id: NEW_CLUB.id, name: NEW_CLUB.name, short_name: '', slug: 'brand-new' })
    if (p === '/public/self-serve/validate-admin') return json({ valid: true, errors: {} })
    if (p === '/public/self-serve/verify-email/send') return json({ ok: true })
    if (p === '/public/self-serve/verify-email/check') return json({ ok: true })
    if (p === '/public/self-serve/acknowledge') return json({ ok: true })
    if (p === '/public/self-serve/submit') {
      if (submitStatus !== 200) return json({ detail: 'Something went wrong' }, submitStatus)
      return json({ status: 'completed', org_id: NEW_CLUB.id, redirect: '/admin' })
    }
    if (p === `/clubs/${CLUB.slug}`) return json(CLUB)
    if (req.method() === 'POST') return json({ ok: true })
    return json([])
  })
  return { ctx, page, errors, posts }
}

const fbqEvents = (page) => page.evaluate(() => window.__fbq.filter((a) => a[0] === 'track').map((a) => ({ name: a[1], params: a[2], opts: a[3] })))

// ── 1. The paid funnel: /trial -> search -> dashboard ───────────────────────
{
  try {
    const { ctx, page, errors, posts } = await open()
    await page.goto(`${BASE}/trial${AD_QUERY}`)
    await page.getByLabel('Search for your club').waitFor()
    ck('no club bar on /trial itself (it has its own call to action)', await page.getByTestId('club-cta').count() === 0)
    ck('no generic bar on /trial either', await page.getByRole('region', { name: 'Get your club on BetterCricket' }).count() === 0)

    const fallback = page.getByTestId('trial-setup-yourself')
    ck('/trial: "set it up yourself" is a real button', await fallback.count() === 1)
    const fb = await fallback.boundingBox().catch(() => null)
    ck('/trial: the fallback button is a proper tap target', fb && fb.height >= 44 && fb.width >= 200, JSON.stringify(fb))
    const fbStyle = await fallback.evaluate((el) => ({ size: parseFloat(getComputedStyle(el).fontSize) })).catch(() => ({}))
    ck('/trial: the fallback reads at body size, not small print', fbStyle.size >= 15, JSON.stringify(fbStyle))

    const landing = await page.evaluate(() => JSON.parse(sessionStorage.getItem('bc:landingParams') || 'null'))
    ck('landing params kept for the session (utm + fbclid)', landing?.utm_campaign === 'BC_AU_Trials_CBO_Aug2026' && landing?.fbclid === 'IwAR0clubcta123', JSON.stringify(landing))

    // The animated placeholder must never suggest a real club: sample it
    // across a full cycle of its phrases.
    const seen = new Set()
    for (let i = 0; i < 24; i++) {
      const t = await page.evaluate(() => document.querySelector('input[aria-label="Search for your club"]')?.parentElement?.textContent || '')
      if (t) seen.add(t.trim())
      await page.waitForTimeout(500)
    }
    const all = [...seen].join(' | ')
    ck('/trial: the placeholder names no real club', seen.size > 3 && !/Applecross|Gosnells|Cricket Club/.test(all), all.slice(0, 200))

    // A club not yet on BetterCricket: the modal says there is nothing to
    // show yet and what setting it up brings in, in the ad's terms.
    await page.getByLabel('Search for your club').fill('brand new')
    const newRow = page.getByRole('button', { name: /Brand New Cricket Club/ }).first()
    await newRow.waitFor().catch(() => {})
    await newRow.click().catch(() => {})
    const heading = await page.getByTestId('trial-not-yet-heading').textContent({ timeout: 4000 }).catch(() => '')
    ck('/trial: a new club is told there is no page to show yet', /isn.t on BetterCricket yet, so there.s no club page/.test(heading || ''), heading)
    const body = await page.getByTestId('trial-not-yet-body').textContent({ timeout: 2000 }).catch(() => '')
    ck('/trial: and what setting it up brings in', /every season Cricket Australia holds/.test(body || ''), body)
    const modalText = await page.locator('.fixed.inset-0').first().textContent().catch(() => '')
    ck('/trial: the modal carries the ad\'s terms', /Free · about 3 minutes · no card/.test(modalText || ''), (modalText || '').slice(0, 200))
    await page.getByRole('button', { name: 'Close' }).click().catch(() => {})
    await page.getByLabel('Search for your club').fill('')

    await page.getByLabel('Search for your club').fill('applecross')
    await page.getByRole('button', { name: /Applecross Cricket Club/ }).first().click()
    await page.waitForURL(/\/applecross$/)
    ck('search result navigated client-side (query string gone)', !page.url().includes('utm_'))

    const bar = page.getByTestId('club-cta')
    await bar.waitFor({ timeout: 8000 }).catch(() => {})
    ck('dashboard: the prospect bar is shown', await bar.count() === 1)
    await page.getByTestId('club-cta-headline').filter({ hasText: 'Applecross' }).waitFor({ timeout: 5000 }).catch(() => {})
    const headline = await page.getByTestId('club-cta-headline').textContent().catch(() => '')
    ck('dashboard: the bar names the club being viewed', /Applecross Cricket Club.s real history on BetterCricket/.test(headline || ''), headline)
    const text = await bar.textContent().catch(() => '')
    ck('dashboard: the ad\'s terms stated', /Free · about 3 minutes · no card/.test(text || ''), text)
    ck('dashboard: no trial-length framing the ad does not make', !/day trial/i.test(text || ''), text)
    const startLabel = await page.getByTestId('club-cta-start').textContent().catch(() => '')
    ck('dashboard: the button says what the ad said', /Check out your club/.test(startLabel || ''), startLabel)
    const box = await bar.boundingBox()
    const vh = page.viewportSize().height
    ck('dashboard: visible without scrolling', box && box.y >= 0 && box.y + box.height <= vh + 1, JSON.stringify(box))
    const startStyle = await page.getByTestId('club-cta-start').evaluate((el) => getComputedStyle(el).backgroundColor)
    ck('dashboard: the start button is a filled primary button', startStyle === 'rgb(52, 211, 153)', startStyle)

    const before = (await fbqEvents(page)).map((e) => e.name)
    await page.getByTestId('club-cta-start').click()
    await page.getByPlaceholder("Start typing your club's name…").waitFor()
    ck('the start button opens the registration wizard', true)
    const afterClick = (await fbqEvents(page)).map((e) => e.name)
    ck('no CompleteRegistration on the click', !afterClick.includes('CompleteRegistration'), JSON.stringify(afterClick))
    ck('no other pixel event fired by the click itself', afterClick.length === before.length, JSON.stringify({ before, afterClick }))

    // Walk the wizard for a club that is NOT yet registered.
    await page.getByPlaceholder("Start typing your club's name…").fill('brand new')
    await page.getByRole('button', { name: /Brand New Cricket Club/ }).first().click()
    await page.getByRole('button', { name: 'CONTINUE' }).click()
    const field = (label) => page.locator(`label:has-text("${label}") + input, label:has-text("${label}") ~ input`).first()
    await field('First name').fill('Sam')
    await field('Last name').fill('Tester')
    await field('Email address').fill('sam@example.com')
    await field('Mobile number').fill('0400 111 222')
    await page.waitForTimeout(700)
    await page.getByRole('button', { name: 'CONTINUE' }).click()
    await page.getByRole('button', { name: 'SEND CODE' }).click()
    await page.locator('input[inputmode="numeric"]').fill('1234')
    await page.getByRole('button', { name: 'VERIFY' }).click()
    await page.getByText('✓ Email verified').waitFor()
    await page.getByRole('button', { name: 'CONTINUE' }).click()
    const boxes = page.locator('input[type="checkbox"]:not([disabled])')
    for (let i = 0; i < await boxes.count(); i++) await boxes.nth(i).check()
    await page.getByRole('button', { name: 'CONTINUE' }).click()
    await page.locator('input[type="password"]').nth(0).fill('Sup3rSecret!pw')
    await page.locator('input[type="password"]').nth(1).fill('Sup3rSecret!pw')
    // Stop the success redirect so the recorder can still be read afterwards.
    await page.evaluate(() => { window.location.assign = () => {} })
    const preSubmit = (await fbqEvents(page)).map((e) => e.name)
    ck('no CompleteRegistration before submit', !preSubmit.includes('CompleteRegistration'), JSON.stringify(preSubmit))
    await page.getByRole('button', { name: /DAY FREE TRIAL/ }).click()
    await page.waitForTimeout(600)
    const events = await fbqEvents(page)
    const cr = events.filter((e) => e.name === 'CompleteRegistration')
    ck('CompleteRegistration fires once on success', cr.length === 1, JSON.stringify(events.map((e) => e.name)))
    ck('content_category intact (self_serve_trial)', cr[0]?.params?.content_category === 'self_serve_trial', JSON.stringify(cr[0]?.params))
    const sub = posts['/public/self-serve/submit']
    ck('browser and server share the event id', !!cr[0]?.opts?.eventID && cr[0].opts.eventID === sub?.meta?.eventId, JSON.stringify({ b: cr[0]?.opts, s: sub?.meta?.eventId }))
    ck('submit carries the ad UTMs after the hops', sub?.attribution?.utm_campaign === 'BC_AU_Trials_CBO_Aug2026' && sub?.attribution?.utm_content === 'trial_4x5_v2', JSON.stringify(sub?.attribution))
    ck('submit carries the fbclid after the hops', sub?.attribution?.click_id === 'IwAR0clubcta123', JSON.stringify(sub?.attribution))
    ck('submit carries an fbc built from the landing fbclid', /IwAR0clubcta123$/.test(sub?.meta?.fbc || ''), sub?.meta?.fbc)
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  } catch (e) { ck('section ran to the end', false, String(e).split('\n')[0]) }
}

// ── 2. A failed submit claims nothing ───────────────────────────────────────
{
  try {
    const { ctx, page } = await open({ submitStatus: 500 })
    await page.goto(`${BASE}/trial${AD_QUERY}`)
    await page.getByLabel('Search for your club').fill('brand new')
    await page.getByRole('button', { name: /Brand New Cricket Club/ }).first().click()
    await page.getByRole('button', { name: 'Set up my club' }).click()
    await page.getByRole('button', { name: 'CONTINUE' }).click()
    const field = (label) => page.locator(`label:has-text("${label}") + input, label:has-text("${label}") ~ input`).first()
    await field('First name').fill('Sam')
    await field('Last name').fill('Tester')
    await field('Email address').fill('sam@example.com')
    await field('Mobile number').fill('0400 111 222')
    await page.waitForTimeout(700)
    await page.getByRole('button', { name: 'CONTINUE' }).click()
    await page.getByRole('button', { name: 'SEND CODE' }).click()
    await page.locator('input[inputmode="numeric"]').fill('1234')
    await page.getByRole('button', { name: 'VERIFY' }).click()
    await page.getByRole('button', { name: 'CONTINUE' }).click()
    const boxes = page.locator('input[type="checkbox"]:not([disabled])')
    for (let i = 0; i < await boxes.count(); i++) await boxes.nth(i).check()
    await page.getByRole('button', { name: 'CONTINUE' }).click()
    await page.locator('input[type="password"]').nth(0).fill('Sup3rSecret!pw')
    await page.locator('input[type="password"]').nth(1).fill('Sup3rSecret!pw')
    await page.getByRole('button', { name: /DAY FREE TRIAL/ }).click()
    await page.waitForTimeout(600)
    const names = (await fbqEvents(page)).map((e) => e.name)
    ck('failed submit fires no CompleteRegistration', !names.includes('CompleteRegistration'), JSON.stringify(names))
    await ctx.close()
  } catch (e) { ck('section ran to the end', false, String(e).split('\n')[0]) }
}

// ── 3. Who does NOT see it ──────────────────────────────────────────────────
{
  try {
    const { ctx, page } = await open()
    await page.goto(`${BASE}/applecross`)
    await page.waitForTimeout(2000)
    ck('a club member arriving directly sees no bar', await page.getByTestId('club-cta').count() === 0)
    ck('...and no pill', await page.getByTestId('club-cta-pill').count() === 0)
    await ctx.close()
  } catch (e) { ck('section ran to the end', false, String(e).split('\n')[0]) }
}
{
  try {
    const { ctx, page } = await open({ signedIn: true })
    await page.goto(`${BASE}/applecross${AD_QUERY}`)
    await page.waitForTimeout(2000)
    ck('a signed-in user sees no bar, even from an ad', await page.getByTestId('club-cta').count() === 0)
    await ctx.close()
  } catch (e) { ck('section ran to the end', false, String(e).split('\n')[0]) }
}

// ── 4. Direct ad landing on a club page, minimise, mobile ───────────────────
{
  try {
    const { ctx, page, errors } = await open({ width: 390 })
    await page.goto(`${BASE}/applecross${AD_QUERY}`)
    const bar = page.getByTestId('club-cta')
    await bar.waitFor({ timeout: 8000 }).catch(() => {})
    ck('ad landing straight on a club page shows the bar', await bar.count() === 1)
    const box = await bar.boundingBox()
    ck('390px: bar inside the viewport', box && box.y + box.height <= 801 && box.width <= 391, JSON.stringify(box))
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    ck('390px: no horizontal overflow from the bar', overflow <= 0, String(overflow))
    await page.getByRole('button', { name: 'Minimise' }).click()
    ck('minimising leaves a pill', await page.getByTestId('club-cta-pill').count() === 1)
    const pillText = await page.getByTestId('club-cta-pill').textContent().catch(() => '')
    ck('the pill carries the ad\'s wording', /Check out your club/.test(pillText || ''), pillText)
    await page.goto(`${BASE}/applecross/players`)
    await page.waitForTimeout(1500)
    ck('the pill persists across the club\'s pages', await page.getByTestId('club-cta-pill').count() === 1)
    await page.getByTestId('club-cta-pill').click()
    await page.getByPlaceholder("Start typing your club's name…").waitFor({ timeout: 5000 }).catch(() => {})
    ck('the pill opens the wizard', await page.getByPlaceholder("Start typing your club's name…").count() === 1)
    ck('no page errors (390px)', errors.length === 0, errors.join(' | '))
    await ctx.close()
  } catch (e) { ck('section ran to the end', false, String(e).split('\n')[0]) }
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
