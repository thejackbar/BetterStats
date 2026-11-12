/**
 * Drive the Ask IQ page in a real browser while an answer is slow.
 *
 * Three behaviours, with the API stubbed at the network layer and the page clock
 * faked so a four minute wait runs in a moment:
 *   1. A question that never answers: the wording moves on as the seconds pass
 *      (it must not sit on "Reading your data" for minutes), the seconds show,
 *      and after the client timeout the page says so and unlocks the ask bar.
 *   2. A 504 from the proxy reads as an Ask IQ message, not "System refreshing".
 *   3. A normal answer is unchanged.
 *
 * Every check reads through counts and presence-safe accessors, so run against the
 * previous page it reports what is missing rather than crashing.
 *
 * Run against a dev or served build:  node scripts/verify-ask-iq-wait.mjs [baseUrl]
 */
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:5199'
const pass = [], fail = []
const check = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  ;(ok ? pass : fail).push(label)
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}: ${JSON.stringify(got)}${ok ? '' : ` (wanted ${JSON.stringify(want)})`}`)
}
const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {})
const errors = []

async function open(mode) {
  const page = await browser.newPage({ viewport: { width: 390, height: 900 } })
  page.on('pageerror', e => errors.push(String(e)))
  const seen = { asks: 0, signals: 0 }
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^.*\/api/, '')
    if (path === '/auth/me') return json(route, { id: 'u1', email: 'a@b.c', role: 'super_admin', club_id: 'o1', club_name: 'Home CC', capabilities: [], modules: ['iq'] })
    if (path === '/iq/ask') {
      seen.asks++
      if (mode === 'hang') return // never answered: the client has to give up on its own
      // A proxy's own 504 page is HTML, not the API's JSON; that is what turns
      // into "System refreshing" in api.js, so the stub has to look like it.
      if (mode === '504') return route.fulfill({ status: 504, contentType: 'text/html', body: '<html><h1>504 Gateway Time-out</h1></html>' })
      return json(route, { available: true, answer: 'Smith is in the best form.' })
    }
    if (path.startsWith('/iq/') && /(players|grades|seasons|opponents)/.test(path)) return json(route, [])
    return json(route, {})
  })
  await page.clock.install()
  await page.goto(`${BASE}/admin/betteriq/ask`)
  await page.waitForSelector('textarea', { timeout: 20000 })
  return { page, seen }
}
const text = async page => (await page.evaluate(() => document.body.innerText)).replace(/\s+/g, ' ')
const has = async (page, s) => (await text(page)).includes(s)
const ask = async (page, q) => { await page.fill('textarea', q); await page.keyboard.press('Enter') }

// 1. a question that never answers
{
  const { page, seen } = await open('hang')
  await ask(page, 'How do we go against Kardinya Lakes?')
  await page.waitForSelector('text=Reading your data', { timeout: 10000 })
  check('starts on the first wording', await has(page, 'Reading your data'), true)
  check('the ask button is locked while waiting', await page.locator('button:has-text("Asking")').count(), 1)

  await page.clock.runFor(20000)
  check('20s in: it says it is still working', await has(page, 'Still working'), true)
  check('20s in: the first wording is gone', await has(page, 'Reading your data'), false)

  await page.clock.runFor(30000)
  check('50s in: it says it is taking a while', await has(page, 'taking a while'), true)
  check('50s in: the seconds are on screen', /\b5\ds\b/.test(await text(page)), true)

  check('390px: nothing overflows sideways while waiting',
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
  if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT, deviceScaleFactor: 2 }).catch(() => page.screenshot({ path: process.env.SHOT }))

  const pct = await page.locator('[role="progressbar"]').first().getAttribute('aria-valuenow')
  check('the bar has not been pinned at the old 94% since the first seconds', Number(pct) < 94, true)

  await page.clock.runFor(210000)
  await page.waitForSelector('text=took too long', { timeout: 10000 }).catch(() => {})
  check('after the client timeout the page says it took too long', await has(page, 'took too long to work out'), true)
  check('the progress bar is gone', await page.locator('[role="progressbar"]').count(), 0)
  await page.fill('textarea', 'Another question')
  check('the ask bar is unlocked again', await page.locator('button:has-text("Ask"):not([disabled])').count() > 0, true)
  check('one request was sent', seen.asks, 1)
  await page.close()
}

// 2. a proxy 504
{
  const { page } = await open('504')
  await ask(page, 'How do we go against Kardinya Lakes?')
  await page.waitForSelector('text=connection dropped', { timeout: 10000 }).catch(() => {})
  check('a 504 says the connection dropped', await has(page, 'connection dropped'), true)
  check('a 504 does not say System refreshing', await has(page, 'System refreshing'), false)
  await page.close()
}

// 3. a normal answer
{
  const { page } = await open('ok')
  await ask(page, 'Who is in form?')
  await page.waitForSelector('text=Smith is in the best form', { timeout: 10000 }).catch(() => {})
  check('a normal answer shows', await has(page, 'Smith is in the best form'), true)
  check('no waiting text is left behind', await has(page, 'Reading your data'), false)
  await page.close()
}

check('no page errors', errors, [])
await browser.close()
console.log(`\n${pass.length} passed, ${fail.length} failed`)
process.exit(fail.length ? 1 : 0)
