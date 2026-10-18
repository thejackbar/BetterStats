// A capped send says so, before and after: the REAL Emails detail pane with the
// API stubbed at the network layer.
//
// Reported: a Sandbox club (50 a day) sent an email to 669 players. 50 went at
// once and the rest trickled out over ten days, and nothing on screen said so.
// (A Note's title is CSS-uppercase, so title checks are case-insensitive.)
// What is asserted:
//   * a draft whose audience is bigger than today's allowance shows "Only 50 of
//     669 will go out today", the number held back and when the next batch goes;
//   * the confirm dialog repeats it, and Send still posts exactly the save
//     (PATCH) then the send (POST) with no body on the send;
//   * a club whose allowance covers the audience sees NO such note and a plain
//     confirm (so the note is not simply always drawn);
//   * a sent email with recipients still waiting shows a "waiting" tile and a
//     note; one with none shows neither;
//   * no horizontal overflow at 390px.
//
//   node verify_comms_send_limits_browser.mjs   (BASE via APP_URL, default :5178;
//   CHROMIUM_PATH points at a browser binary when the pinned one is not installed)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5178'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const CID = 'camp1'

const SANDBOX_LIMITS = {
  tier: 'sandbox', daily_cap: 50, sent_today: 0, daily_remaining: 50, allowance: 50,
  account_remaining: 45000, metrics: {}, blocked: null, can_request: false, open_request: null,
  next_batch_at: '2026-10-09T00:15:00+00:00',
}
const PRODUCTION_LIMITS = { ...SANDBOX_LIMITS, tier: 'production', daily_cap: 2000, daily_remaining: 2000, allowance: 2000 }

let LIMITS = SANDBOX_LIMITS
let CAMPAIGN = null
const draft = () => ({
  id: CID, subject: 'Important Reminder', name: 'Important Reminder', description: '',
  body_html: '<p>Hello</p>', audience: { type: 'all' }, utm: {}, template_id: null,
  status: 'draft', stats: {}, club_stats: {},
})
const sent = (deferred) => ({
  ...draft(), status: 'sending', sent_at: null,
  engagement: { sent: 300, unsub_supp: 0, bounced: 0 },
  stats: { recipients: 669, sent: 300, failed: 0, deferred },
})

const routes = (page, calls) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url()
  calls.push({ url, method: req.method(), body: req.postData() })
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

  if (url.includes('/auth/me')) {
    return json({
      id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      can_switch_clubs: false, is_marketing_org: false,
      entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' },
    })
  }
  if (/\/comms\/limits$/.test(url)) return json(LIMITS)
  if (/\/comms\/audience\/preview/.test(url)) return json({ count: 669 })
  if (/\/comms\/campaigns\/[^/]+\/send$/.test(url)) {
    return json({ status: 'sending', recipients: 669, sending_now: 50, deferred: 619,
                  next_batch_at: LIMITS.next_batch_at })
  }
  if (/\/comms\/campaigns\/[^/]+\/recipients/.test(url)) return json({ campaign: { id: CID }, recipients: [] })
  if (/\/comms\/campaigns\/[^/]+\/preview/.test(url)) return json({ html: '<p>preview</p>' })
  if (/\/comms\/campaigns\/[^/]+\/status$/.test(url)) return json({ status: CAMPAIGN.status, stats: CAMPAIGN.stats, error: null })
  if (/\/comms\/campaigns\/[^/]+$/.test(url)) return json(CAMPAIGN)
  if (/\/comms\/campaigns$/.test(url)) return json([{ id: CID, subject: CAMPAIGN.subject, name: CAMPAIGN.name,
    status: CAMPAIGN.status, created_at: '2026-10-08T01:44:00+00:00' }])
  if (/\/comms\/segments/.test(url)) return json([])
  if (/\/comms\/templates/.test(url)) return json([])
  if (/\/comms\/merge-variables/.test(url)) return json({ variables: [] })
  if (/\/comms\/context/.test(url)) return json({ current: { is_marketing: false } })
  if (/\/comms\/settings/.test(url)) return json({ provider: { live: true } })
  if (/\/notifications\/(count|summary)/.test(url)) return json({ unseen_count: 0, items: [] })
  return json({})
})

const overflow = (page) => page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth)

async function open(browser, width, { limits, campaign }) {
  LIMITS = limits
  CAMPAIGN = campaign
  const ctx = await browser.newContext({ viewport: { width, height: 1000 }, timezoneId: 'Australia/Perth', locale: 'en-AU' })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const calls = [], errors = [], dialogs = []
  page.on('pageerror', e => errors.push(String(e)))
  page.on('dialog', d => { dialogs.push(d.message()); d.accept() })
  await routes(page, calls)
  await page.goto(BASE + '/admin/comms/' + CID, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  return { ctx, page, calls, errors, dialogs }
}

const bodyText = (page) => page.evaluate(() => document.body.innerText)

async function main() {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {})

  // ── A Sandbox club, audience of 669 ────────────────────────────────────
  console.log('\n── Draft: Sandbox club, 669 people, 50 allowed today ──────────')
  {
    const { ctx, page, calls, errors, dialogs } = await open(browser, 1500, { limits: SANDBOX_LIMITS, campaign: draft() })
    const t = await bodyText(page)
    check('the note says only 50 of 669 go out today', /Only 50 of 669 will go out today/i.test(t), t.slice(0, 200))
    check('it says how many are held back (619)', /other 619/.test(t))
    check('it says when the next batch goes (Friday 8:15 Perth time)', /Friday[^.]*8:15/.test(t))
    check('it says how the limit is lifted (BetterAdmin subscribers)', /BetterAdmin subscribers/.test(t))

    // Send. The button label is "Send to 669".
    await page.getByRole('button', { name: /Send to 669/ }).click()
    await page.waitForTimeout(1500)
    check('the confirm dialog repeats the limit', dialogs.length === 1 && /50 go out today/.test(dialogs[0]) && /other 619/.test(dialogs[0]),
      JSON.stringify(dialogs))
    const writes = calls.filter(c => c.method !== 'GET' && !/audience\/preview/.test(c.url))
    const patch = writes.find(c => c.method === 'PATCH')
    const send = writes.find(c => c.method === 'POST' && /\/send$/.test(c.url))
    check('Send saves the draft (PATCH) then sends (POST)', !!patch && !!send && writes.indexOf(patch) < writes.indexOf(send),
      writes.map(w => `${w.method} ${new URL(w.url).pathname}`).join(' | '))
    check('the send POST carries no body', send && !send.body, send && send.body)
    check('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  // ── The same screen at 390px ───────────────────────────────────────────
  console.log('\n── 390px ──────────────────────────────────────────────────────')
  {
    const { ctx, page } = await open(browser, 390, { limits: SANDBOX_LIMITS, campaign: draft() })
    check('the note is on screen at 390px', /Only 50 of 669/i.test(await bodyText(page)))
    const o = await overflow(page)
    check('no horizontal overflow at 390px (draft)', o <= 0, `scrollWidth - clientWidth = ${o}`)
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/draft-390.png` : '/dev/null', fullPage: true }).catch(() => {})
    await ctx.close()
  }

  // ── A Production club: the note must be absent ─────────────────────────
  console.log('\n── Draft: Production club, 2000 allowed today ─────────────────')
  {
    const { ctx, page, dialogs } = await open(browser, 1500, { limits: PRODUCTION_LIMITS, campaign: draft() })
    const t = await bodyText(page)
    check('the audience is counted (669 contacts) so the note COULD show', /669/.test(t))
    check('no "will go out today" note when everyone goes today', !/will go out today/i.test(t))
    await page.getByRole('button', { name: /Send to 669/ }).click()
    await page.waitForTimeout(1200)
    check('the confirm is the plain one', dialogs.length === 1 && !/go out today/.test(dialogs[0]), JSON.stringify(dialogs))
    await ctx.close()
  }

  // ── A sent email with people still waiting ─────────────────────────────
  console.log('\n── Sent email: 369 still waiting ──────────────────────────────')
  {
    const { ctx, page, errors } = await open(browser, 1500, { limits: SANDBOX_LIMITS, campaign: sent(369) })
    const t = await bodyText(page)
    check('a "waiting" tile shows 369', /369\s*\n?\s*waiting/i.test(t), t.slice(0, 300))
    check('the note says 369 are still waiting and when they go', /369 still waiting to go out/i.test(t) && /next daily batch/i.test(t))
    check('the header no longer claims it is all going out now', /Part of this email has gone out/.test(t) && !/going out now/i.test(t), t.slice(0, 400))
    check('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
    const c390 = await open(browser, 390, { limits: SANDBOX_LIMITS, campaign: sent(369) })
    const o = await overflow(c390.page)
    check('no horizontal overflow at 390px (sent)', o <= 0, `scrollWidth - clientWidth = ${o}`)
    await c390.page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/sent-390.png` : '/dev/null', fullPage: true }).catch(() => {})
    await c390.ctx.close()
  }
  console.log('\n── Sent email: nobody waiting ─────────────────────────────────')
  {
    const { ctx, page } = await open(browser, 1500, { limits: SANDBOX_LIMITS, campaign: { ...sent(0), status: 'sent' } })
    const t = await bodyText(page)
    check('the sent email itself is on screen (recipients tile)', /recipients/i.test(t))
    check('no waiting tile or note when nobody is waiting', !/waiting/i.test(t.replace(/Sending in progress/i, '')))
    await ctx.close()
  }

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  FAIL.forEach(f => console.log('  FAILED:', f))
  process.exit(FAIL.length ? 1 : 0)
}

main().catch(e => { console.error(e); process.exit(2) })
