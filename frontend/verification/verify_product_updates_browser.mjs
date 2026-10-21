// Drives the real Daily Update screen (and the bell that shows its post) in
// Chromium with the API stubbed at the network layer.
//
//   npm run build && npx vite preview --port 5204 &
//   node frontend/verification/verify_product_updates_browser.mjs [baseUrl]
//
// Nothing in the daily update is reviewed by a person before it reaches a club,
// so this screen is the control room: the Stop switch, a preview, Run now, and
// Take down. Every check that matters asserts what went ON THE WIRE. A preview
// that quietly posted, or a Stop that sent the wrong value, would look fine on
// screen. The stub MUTATES, so a working Start can be told from a no-op.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const BLASTS = () => [
  { id: 'b1', blast_date: '2026-10-21', status: 'posted', headline: 'New: share a scorecard, plus a fix',
    bullets: ['You can now share any scorecard as a picture.', 'Fixed an issue with some bowling figures.'],
    versions: ['v9.201.0'], reason: null, model: 'm', raw_output: '{"headline":"raw model text"}',
    orgs_notified: 12, created_at: '2026-10-20T22:00:05Z', retracted_at: null },
  { id: 'b2', blast_date: '2026-10-20', status: 'blocked', headline: null, bullets: [],
    versions: ['v9.200.1'], reason: 'Held back: the draft mentions "database".', model: 'm',
    raw_output: '{"headline":"Faster pages"}', orgs_notified: 0, created_at: '2026-10-19T22:00:04Z', retracted_at: null },
  { id: 'b3', blast_date: '2026-10-19', status: 'skipped', headline: null, bullets: [],
    versions: [], reason: 'No new releases since the last update.', model: 'm', raw_output: null,
    orgs_notified: 0, created_at: '2026-10-18T22:00:02Z', retracted_at: null },
  { id: 'b4', blast_date: '2026-10-18', status: 'failed', headline: null, bullets: [],
    versions: [], reason: 'Could not read the changelog: the site was down.', model: 'm', raw_output: null,
    orgs_notified: 0, created_at: '2026-10-17T22:00:02Z', retracted_at: null },
]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ width = 1280, preview = null, role = 'super_admin', lastSeen = 'v99.0.0',
                     startPath = '/admin/super/product-updates', ready = '[data-testid="control-card"]', title = 'Daily Update' } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1600 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', e => errors.push(String(e)))
  page.on('dialog', d => d.accept())
  const state = { paused: true, blasts: BLASTS() }

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace(/^\/api/, '')
    const method = req.method()
    const json = (body, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    let payload = null
    try { payload = req.postDataJSON() } catch { payload = null }
    if (method !== 'GET' && !/^\/usage\//.test(path)) calls.push({ path, method, payload })

    if (path === '/auth/me') {
      return json({ id: 'u1', username: 'staff', role, capabilities: ['*'], club_slug: 'applecross',
                    can_switch_clubs: true, entitlements: { modules: ['stats'], status: 'active' } })
    }
    if (path === '/club-admin/product-updates') {
      return json({ items: [
        { id: 'b1', date: '2026-10-21', headline: 'New: share a scorecard, plus a fix',
          bullets: ['You can now share any scorecard as a picture.', 'Fixed an issue with some bowling figures.'] },
        { id: 'b0', date: '2026-10-20', headline: 'New: copy a squad', bullets: ["You can now copy last week's squad."] },
      ] })
    }
    if (path === '/club-admin/super/product-updates' && method === 'GET') {
      return json({ paused: state.paused, blasts: state.blasts, max_age_days: 7 })
    }
    if (path === '/club-admin/super/product-updates/control') {
      state.paused = !!payload.paused
      return json({ paused: state.paused })
    }
    if (path === '/club-admin/super/product-updates/preview') {
      return json(preview || { status: 'preview', headline: 'New: copy a squad',
        bullets: ['You can now copy last week\'s squad into a new one.'],
        versions: ['v9.203.0', 'v9.203.1'], raw_output: '{}' })
    }
    if (path === '/club-admin/super/product-updates/run') {
      state.blasts = [{ ...BLASTS()[0], id: 'b9', headline: 'Run now post' }, ...state.blasts]
      return json({ status: 'posted', blast_id: 'b9', orgs_notified: 7, versions: ['v9.203.0'] })
    }
    if (/^\/club-admin\/super\/product-updates\/[^/]+$/.test(path) && method === 'DELETE') {
      const id = path.split('/').pop()
      state.blasts = state.blasts.map(b => (b.id === id ? { ...b, status: 'retracted' } : b))
      return json({ id, notifications_removed: 12 })
    }
    if (/\/notifications\/summary$/.test(path)) {
      return json({ last_seen_at: null, last_seen_version: lastSeen, unseen_count: 1, failed_sync_count: 0,
        sync_runs: [], new_milestones: [], upcoming_milestones: [], pending_sync_requests: 0,
        pending_reports_count: 0, merch_alerts: { low_stock: [], expiring: [], service_due: [], total: 0 },
        asset_alerts: { service_due: [], total: 0 },
        alerts: [{ id: 'n-1', event_key: 'product_update', severity: 'info',
          title: 'New: share a scorecard, plus a fix',
          body: '• You can now share any scorecard as a picture.\n• Fixed an issue with some bowling figures.',
          link: '/admin/changelog', payload: {}, occurred_at: null,
          created_at: new Date().toISOString(), read: false }],
        alert_count: 1 })
    }
    if (/\/notifications\/count$/.test(path)) {
      return json({ unseen_count: 1, alert_count: 1, failed_sync_count: 0, last_seen_version: lastSeen })
    }
    return json({})
  })

  await page.goto(`${BASE}${startPath}`, { waitUntil: 'domcontentloaded' })
  try {
    await page.waitForSelector(`text=${title}`, { timeout: 15000 })
    await page.waitForSelector(ready, { timeout: 15000 })
  } catch {
    await ctx.close()
    console.log(`FAIL the ${title} screen is not present in this build`)
    console.log('\n0 passed, 1 failed')
    await browser.close()
    process.exit(1)
  }
  return { page, ctx, errors, calls, state }
}

const noOverflow = page => page.evaluate(
  () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)

// ── the Stop switch ─────────────────────────────────────────────────────────
{
  const { page, ctx, errors, calls } = await open()
  const card = page.locator('[data-testid="control-card"]')
  ck('it opens stopped, which is how a deploy leaves it',
    (await card.getByText('Stopped', { exact: true }).count()) === 1)
  ck('Run now is off while stopped',
    await card.getByRole('button', { name: 'Run now' }).isDisabled())
  ck('and it says why', (await card.getByText('Run now is off while the updates are stopped.').count()) === 1)

  calls.length = 0
  await card.getByRole('button', { name: 'Start daily updates' }).click()
  await page.waitForSelector('text=Running')
  ck('Start sends exactly paused:false to the control endpoint',
    calls.length === 1 && calls[0].path === '/club-admin/super/product-updates/control'
      && calls[0].payload.paused === false, JSON.stringify(calls))
  ck('the screen reloads to Running', (await card.getByText('Running', { exact: true }).count()) === 1)
  ck('Run now is on once running',
    await card.getByRole('button', { name: 'Run now' }).isEnabled())

  calls.length = 0
  await card.getByRole('button', { name: 'Stop daily updates' }).click()
  await page.waitForSelector('text=Nothing is posted while this is stopped.')
  ck('Stop sends paused:true', calls.length === 1 && calls[0].payload.paused === true, JSON.stringify(calls))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── preview writes nothing ──────────────────────────────────────────────────
{
  const { page, ctx, calls } = await open()
  calls.length = 0
  await page.getByRole('button', { name: 'Preview the next post' }).click()
  await page.waitForSelector('[data-testid="preview-result"]')
  const box = page.locator('[data-testid="preview-result"]')
  ck('the preview shows the headline and bullet', (await box.getByText('New: copy a squad').count()) === 1
    && (await box.getByText("You can now copy last week's squad into a new one.").count()) === 1)
  ck('it says nothing has been sent', (await box.getByText(/nothing has been sent/i).count()) === 1)
  ck('the only request is the preview, no run and no control',
    calls.length === 1 && calls[0].path.endsWith('/preview'), JSON.stringify(calls))
  ck('the log did not gain a row', (await page.locator('[data-testid="blast-row"]').count()) === 4)
  await ctx.close()
}
{
  const { page, ctx } = await open({ preview: { status: 'blocked', reason: 'Held back: the draft mentions "server".',
    raw_output: '{"headline":"Server fixes"}', versions: ['v1'] } })
  await page.getByRole('button', { name: 'Preview the next post' }).click()
  await page.waitForSelector('[data-testid="preview-result"]')
  const txt = await page.locator('[data-testid="preview-result"]').innerText()
  ck('a held-back preview says so and why', /held back/i.test(txt) && txt.includes('mentions "server"'), txt)
  await ctx.close()
}

// ── Run now and Take down ───────────────────────────────────────────────────
{
  const { page, ctx, calls } = await open()
  await page.getByRole('button', { name: 'Start daily updates' }).click()
  await page.waitForSelector('text=Running')
  calls.length = 0
  await page.getByRole('button', { name: 'Run now' }).click()
  await page.waitForSelector('text=Posted. 7 clubs told.')
  ck('Run now posts to the run endpoint once', calls.length === 1 && calls[0].path.endsWith('/run')
    && calls[0].method === 'POST', JSON.stringify(calls))
  ck('and the new post appears in the log', (await page.getByText('Run now post').count()) === 1)

  calls.length = 0
  await page.locator('[data-testid="blast-row"]').nth(1).getByRole('button', { name: 'Take down' }).click()
  await page.waitForSelector('text=Taken down')
  ck('Take down sends a DELETE for that post',
    calls.length === 1 && calls[0].method === 'DELETE' && calls[0].path.endsWith('/b1'), JSON.stringify(calls))
  ck('a taken-down post cannot be taken down again',
    (await page.locator('[data-testid="blast-row"]').nth(1).getByRole('button', { name: 'Take down' }).count()) === 0)
  await ctx.close()
}

// ── the log ─────────────────────────────────────────────────────────────────
{
  const { page, ctx, calls } = await open()
  const rows = page.locator('[data-testid="blast-row"]')
  ck('every attempt is listed with its status',
    (await rows.count()) === 4
      && (await rows.nth(0).getByText('Posted', { exact: true }).count()) === 1
      && (await rows.nth(1).getByText('Held back', { exact: true }).count()) === 1
      && (await rows.nth(2).getByText('Nothing to post', { exact: true }).count()) === 1
      && (await rows.nth(3).getByText('Failed', { exact: true }).count()) === 1)
  ck('a held-back draft says why', (await rows.nth(1).getByText('the draft mentions "database"', { exact: false }).count()) === 1)
  ck('only a posted update offers Take down',
    (await page.getByRole('button', { name: 'Take down' }).count()) === 1)
  ck('the raw model text is hidden until asked',
    (await page.getByText('raw model text').count()) === 0)
  await rows.nth(0).getByRole('button', { name: 'What the model wrote' }).click()
  ck('and shown when asked', (await page.getByText('raw model text').count()) === 1)
  ck('the log reads without a single write', calls.length === 0, JSON.stringify(calls))
  await ctx.close()
}

// ── the bell shows the post as lines ────────────────────────────────────────
{
  const { page, ctx, errors } = await open()
  await page.locator('button[aria-label="Notifications"]').first().click()
  await page.waitForSelector('text=Fixed an issue with some bowling figures.')
  const body = page.locator('p', { hasText: 'You can now share any scorecard as a picture.' }).first()
  ck('the bell body keeps its line breaks',
    (await body.evaluate(el => getComputedStyle(el).whiteSpace)) === 'pre-line')
  const lines = await body.evaluate(el => Math.round(el.getBoundingClientRect().height
    / parseFloat(getComputedStyle(el).lineHeight)))
  ck('so the two bullets sit on two lines', lines >= 2, String(lines))
  ck('it links to What\'s New', (await page.locator('div.fixed.inset-0 a[href="/admin/changelog"]').count()) >= 1)
  await page.screenshot({ path: '/tmp/claude-0/shots/bell.png' })
  ck('no page errors on the bell', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── the bell no longer lists release notes ─────────────────────────────────
// A person who last looked at v9.0.0 used to see every release since then in the
// bell: a badge counting hundreds, and the full technical text under "What's New".
// The daily update replaces that, so the only count is the one stored notification.
{
  const { page, ctx, errors } = await open({ lastSeen: 'v9.0.0' })
  const badge = (await page.locator('button[aria-label="Notifications"]').first().innerText()).trim()
  ck('the badge counts the daily update and not hundreds of releases', badge === '1', JSON.stringify(badge))
  await page.locator('button[aria-label="Notifications"]').first().click()
  await page.waitForSelector('text=Fixed an issue with some bowling figures.')
  const panel = await page.locator('div.fixed.inset-0').first().innerText()
  ck('the daily update is in the panel', panel.includes('New: share a scorecard, plus a fix'))
  ck('and there is no "What\'s New" release list under it', !/what.s new/i.test(panel) && !/\bv9\.\d+\.\d+/.test(panel), panel)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── the What's New page shows the daily updates ─────────────────────────────
// It used to list every release in full, in the team's own words. A club admin now
// reads the daily notes there; the raw release history stays with staff.
for (const role of ['club_admin', 'super_admin']) {
  const { page, ctx, errors } = await open({ role, startPath: '/admin/changelog', title: "What's New",
                                              ready: '[data-testid="daily-updates"]' })
  await page.waitForSelector('[data-testid="daily-update"]')
  const daily = page.locator('[data-testid="daily-update"]')
  ck(`${role}: the page lists the posted updates, newest first`,
    (await daily.count()) === 2 && (await daily.nth(0).innerText()).includes('New: share a scorecard, plus a fix')
      && (await daily.nth(0).innerText()).includes('Fixed an issue with some bowling figures.'))
  const body = await page.locator('div.max-w-3xl').first().innerText()
  if (role === 'club_admin') {
    ck('club admin: no raw release list', !/release history/i.test(body) && !/\bv9\.\d+\.\d+/.test(body.replace(/current: v[\d.]+/i, '')), body.slice(0, 400))
  } else {
    ck('staff: the release history is still there, under its own heading',
      /release history \(staff only\)/i.test(body) && /\bv9\.128\./.test(body))
  }
  ck(`${role}: no page errors`, errors.length === 0, errors.join(' | '))
  if (role === 'club_admin') await page.screenshot({ path: '/tmp/claude-0/shots/whatsnew.png' })
  await ctx.close()
}

// ── a phone, and who may see it ─────────────────────────────────────────────
{
  const { page, ctx, errors } = await open({ width: 390 })
  await page.getByRole('button', { name: 'Preview the next post' }).click()
  await page.waitForSelector('[data-testid="preview-result"]')
  ck('390px: no horizontal overflow', await noOverflow(page))
  await page.screenshot({ path: '/tmp/claude-0/shots/phone.png', fullPage: true })
  ck('390px: no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    const body = path === '/auth/me'
      ? { id: 'u2', username: 'a', role: 'club_admin', capabilities: ['*'], club_slug: 'applecross',
          entitlements: { modules: ['stats'], status: 'active' } }
      : {}
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.goto(`${BASE}/admin/super/product-updates`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  ck('a club admin does not get the screen',
    (await page.locator('[data-testid="control-card"]').count()) === 0)
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
