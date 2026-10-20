/**
 * Drive the Ask IQ page in a real browser.
 *
 * Ask IQ can put a clarifying question back as buttons. The API is stubbed at
 * the network layer the way the server behaves: a first question gets a
 * `clarify` block; the pick goes back as the next message with the thread so
 * far, the clarifying turn flagged `clarified` so the server answers rather
 * than asking again.
 *
 * Run against a dev or served build:  node scripts/verify-ask-iq-clarify.mjs [baseUrl]
 */
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:5199'
const pass = [], fail = []
const check = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  ;(ok ? pass : fail).push(label)
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}: ${JSON.stringify(got)}${ok ? '' : ` (wanted ${JSON.stringify(want)})`}`)
}
const json = (route, body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const asks = []
const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {})
const page = await browser.newPage({ viewport: { width: 390, height: 900 } })
const errors = []
page.on('pageerror', e => errors.push(String(e)))

await page.route('**/api/**', async route => {
  const url = new URL(route.request().url())
  const path = url.pathname.replace(/^.*\/api/, '')
  if (path === '/auth/me') return json(route, { id: 'u1', email: 'a@b.c', role: 'super_admin', club_id: 'o1', club_name: 'Home CC', capabilities: [], modules: ['iq'] })
  if (path === '/iq/ask') {
    const body = JSON.parse(route.request().postData() || '{}')
    asks.push(body)
    if (!(body.history || []).length) {
      return json(route, { available: true, answer: 'Which grade do you mean?', clarify: {
        question: 'Which grade do you mean?',
        options: [{ label: '1st XI', value: 'Use 1st Grade' }, { label: '2nd XI', value: 'Use 2nd Grade' }, { label: '3rd XI', value: 'Use 3rd Grade' }],
      } })
    }
    return json(route, { available: true, answer: 'In 3rd Grade, pick Smith.' })
  }
  if (path.startsWith('/iq/') && /(players|grades|seasons|opponents)/.test(path)) return json(route, [])
  return json(route, {})
})

await page.goto(`${BASE}/admin/betteriq/ask`)
await page.waitForSelector('textarea', { timeout: 20000 })
await page.fill('textarea', 'Who should we pick?')
await page.keyboard.press('Enter')
await page.waitForSelector('text=Which grade do you mean?', { timeout: 10000 })

const labels = async () => page.$$eval('[role="group"] button', bs => bs.map(b => b.textContent.trim()))
check('three buttons under the question', await labels(), ['1st XI', '2nd XI', '3rd XI'])
if (!(await labels()).length) {
  // Nothing to click (the page has no clarify buttons): report, don't crash.
  console.log('no buttons rendered under the question; the rest cannot run')
  await browser.close()
  console.log(`\n${pass.length} passed, ${fail.length + 1} failed`)
  process.exit(1)
}
check('the first request carried no history', asks[0]?.history, [])
check('the buttons are live', await page.$$eval('[role="group"] button', bs => bs.map(b => b.disabled)), [false, false, false])
check('the ask bar points at the buttons', await page.getAttribute('textarea', 'placeholder'), 'Pick one, or type a reply…')
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
check('no horizontal overflow at 390px', overflow <= 0, true)
await page.screenshot({ path: process.env.SHOT || '/tmp/claude-0/ask-clarify-390.png', fullPage: true })

await page.click('[role="group"] button:has-text("3rd XI")')
await page.waitForSelector('text=In 3rd Grade, pick Smith.', { timeout: 10000 })
check('the pick is sent as its value', asks[1]?.question, 'Use 3rd Grade')
check('with the thread so far, the question turn flagged clarified',
  asks[1]?.history, [{ question: 'Who should we pick?', answer: 'Which grade do you mean?', clarified: true }])
const bubbles = await page.$$eval('.whitespace-pre-wrap, [class*="max-w-[80%]"]', els => els.map(e => e.textContent.trim()).join('|'))
check('the thread shows the label the user clicked, not the instruction', bubbles.includes('3rd XI') && !bubbles.includes('Use 3rd Grade'), true)
check('the answered set is greyed out', await page.$$eval('[role="group"] button', bs => bs.every(b => b.disabled)), true)
check('and the placeholder is back to normal', (await page.getAttribute('textarea', 'placeholder')).startsWith('Ask about'), true)

// A typed reply works too, and a plain question afterwards is unaffected.
await page.fill('textarea', 'and the bowlers?')
await page.keyboard.press('Enter')
await page.waitForFunction(() => document.body.innerText.split('In 3rd Grade, pick Smith.').length > 2)
check('a typed follow-up carries both earlier turns', asks[2]?.history?.map(h => h.clarified), [true, false])
check('no page errors', errors, [])
await page.screenshot({ path: process.env.SHOT2 || '/tmp/claude-0/ask-clarify-after-390.png', fullPage: true })

await browser.close()
console.log(`\n${pass.length} passed, ${fail.length} failed`)
process.exit(fail.length ? 1 : 0)
