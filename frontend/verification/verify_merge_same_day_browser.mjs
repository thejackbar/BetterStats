// Merge Duplicates screen, against the REAL MergeTools component with the API
// stubbed at the network layer.
//
// Two records that share a name but each have a game on the SAME DATE in
// different games are usually two people (a junior and an adult), so the server
// flags that pair `same_day_clash` and refuses the merge until the admin confirms.
// What is asserted:
//   * a flagged exact pair shows the "Probably two people" chip, a clean one does not;
//   * Bulk Approve counts only the clean pair, and the wire carries ONE merge call,
//     for the clean pair, with no confirm flag;
//   * Confirm Merge on the flagged pair gets a 409 same_day_clash, asks the admin,
//     and on OK retries with confirm_same_day_clash:true on the wire;
//   * on Cancel there is no second request and no error banner;
//   * a clean pair merges in a single request (confirm_same_day_clash:false);
//   * no horizontal overflow at 390px.
//
//   node verify_merge_same_day_browser.mjs   (BASE via APP_URL, default :5178)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5178'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const player = (id, name, extra = {}) => ({
  id, name, games: 20, seasons_count: 3, runs: 300, wickets: 10, playhq_id: null, source: 'synced', ...extra,
})
const CANDIDATES = [
  { kind: 'exact', normalised_name: 'luke bennett', redacted: false,
    same_day_clash: 2, same_day_clash_message: 'Both records have a game on the same date in different games (2 dates).',
    player_a: player('p1', 'Luke Bennett', { playhq_id: 'ph1' }), player_b: player('p2', 'Luke Bennett') },
  { kind: 'exact', normalised_name: 'sam clean', redacted: false, same_day_clash: 0, same_day_clash_message: '',
    player_a: player('p3', 'Sam Clean', { playhq_id: 'ph3' }), player_b: player('p4', 'Sam Clean') },
]

const routes = (page, calls, mode) => page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = req.url()
  const body = req.postData()
  calls.push({ url, method: req.method(), body })
  const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) {
    return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      club_id: 'org1', entitlements: { modules: ['admin'], status: 'active' } })
  }
  if (/\/admin\/merge-candidates/.test(url)) return json(CANDIDATES)
  if (/\/admin\/merge-history/.test(url)) return json([])
  if (/\/admin\/merge-players/.test(url) && req.method() === 'POST') {
    const b = JSON.parse(body)
    const flagged = [b.keep_player_id, b.remove_player_id].some(x => x === 'p1' || x === 'p2')
    if (flagged && !b.confirm_same_day_clash) {
      return json({ detail: { code: 'same_day_clash', dates: 2, message: CANDIDATES[0].same_day_clash_message } }, 409)
    }
    return json({ ok: true })
  }
  if (/\/admin\/players/.test(url)) return json([])
  if (/\/notifications\/(count|summary)/.test(url)) return json({ unseen_count: 0, items: [] })
  return json({})
})

const merges = (calls) => calls.filter(c => c.method === 'POST' && /merge-players/.test(c.url)).map(c => JSON.parse(c.body))

async function open(browser, width) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const calls = [], errors = [], dialogs = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page, calls)
  await page.goto(BASE + '/admin/merge', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('text=Merge Duplicates', { timeout: 15000 })
  await page.waitForSelector('text=Bulk Approve', { timeout: 15000 })
  return { ctx, page, calls, errors, dialogs }
}

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })

  // ── Bulk Approve and the chip ───────────────────────────────────────────
  {
    const { page, calls, errors, dialogs } = await open(browser, 1200)
    page.on('dialog', async d => { dialogs.push(d.message()); await d.accept() })
    const chips = await page.locator('text=Probably two people').count()
    check('exactly one pair carries the "Probably two people" chip', chips === 1, `chips=${chips}`)
    const bulk = (await page.locator('button', { hasText: 'Bulk Approve' }).first().textContent()).trim()
    check('Bulk Approve counts only the clean pair', bulk === 'Bulk Approve (1)', bulk)
    await page.locator('button', { hasText: 'Bulk Approve' }).first().click()
    await page.waitForTimeout(800)
    const m = merges(calls)
    check('Bulk Approve sends one merge', m.length === 1, JSON.stringify(m))
    check('that merge is the clean pair', m.length === 1 && [m[0].keep_player_id, m[0].remove_player_id].sort().join() === 'p3,p4', JSON.stringify(m))
    check('the bulk merge does not carry a confirm flag', m.length === 1 && m[0].confirm_same_day_clash === false, JSON.stringify(m))
    check('the confirm text says pairs are left for review', dialogs.some(t => /same date/.test(t)), dialogs.join(' | '))
    check('no page errors', errors.length === 0, errors.join(' | '))
  }

  // ── Confirm the flagged pair: OK retries with the flag ──────────────────
  {
    const { page, calls, dialogs } = await open(browser, 1200)
    page.on('dialog', async d => { dialogs.push(d.message()); await d.accept() })
    await page.locator('button', { hasText: 'Confirm Merge' }).first().click()
    await page.waitForTimeout(800)
    const m = merges(calls)
    check('flagged pair: two requests (refused, then confirmed)', m.length === 2, JSON.stringify(m))
    check('first request has no confirm flag', m[0]?.confirm_same_day_clash === false, JSON.stringify(m[0]))
    check('retry carries confirm_same_day_clash:true', m[1]?.confirm_same_day_clash === true, JSON.stringify(m[1]))
    check('the admin was asked, with the server message',
      dialogs.length === 1 && /same date/.test(dialogs[0]) && /Merge them anyway/.test(dialogs[0]), dialogs.join(' | '))
  }

  // ── Cancel: no retry, no error banner ───────────────────────────────────
  {
    const { page, calls, dialogs } = await open(browser, 1200)
    page.on('dialog', async d => { dialogs.push(d.message()); await d.dismiss() })
    await page.locator('button', { hasText: 'Confirm Merge' }).first().click()
    await page.waitForTimeout(800)
    const m = merges(calls)
    check('cancelled: only the first request was sent', m.length === 1, JSON.stringify(m))
    const body = await page.textContent('body')
    check('cancelled: no error banner', !/Merge cancelled/.test(body) && !/same_day_clash/.test(body))
    check('cancelled: the Confirm Merge button is usable again',
      await page.locator('button', { hasText: 'Confirm Merge' }).first().isEnabled())
  }

  // ── A clean pair merges in one request ──────────────────────────────────
  {
    const { page, calls, dialogs } = await open(browser, 1200)
    page.on('dialog', async d => { dialogs.push(d.message()); await d.accept() })
    await page.locator('button', { hasText: 'Confirm Merge' }).nth(1).click()
    await page.waitForTimeout(800)
    const m = merges(calls)
    check('clean pair: one request, no prompt', m.length === 1 && dialogs.length === 0, `${JSON.stringify(m)} dialogs=${dialogs.length}`)
  }

  // ── 390px ───────────────────────────────────────────────────────────────
  {
    const { page } = await open(browser, 390)
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    check('no horizontal overflow at 390px', over <= 0, `over=${over}`)
    await page.screenshot({ path: 'verification/shots/merge_same_day_390.png', fullPage: true })
  }

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run()
