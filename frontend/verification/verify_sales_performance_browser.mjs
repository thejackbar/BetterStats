// Sales Performance's Contact activity, against the real screen with the API
// stubbed at the network layer. The reported failure is the one it opens on:
// nothing logged today or this week, so the whole table said nothing — even
// though the team had been calling clubs for months.
//
//   node verify_sales_performance_browser.mjs   (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const PERF = `${BASE}/admin/super/crm/performance`

const pass = [], fail = []
const check = (n, c, d = '') => { (c ? pass : fail).push(n); console.log((c ? '  ok   ' : '  FAIL ') + n + (!c && d ? `  [${d}]` : '')) }

const bucket = (o = {}) => ({
  contacts: 0, calls: 0, emails: 0, clubs_contacted: 0,
  positive_conversations: 0, callbacks_created: 0, trials_started: 0, ...o,
})

// The reported shape: today and this week empty, real work behind them.
const SAM = {
  user_id: 'sam', name: 'Sam Barendse',
  today: bucket(), week: bucket(),
  all: bucket({ contacts: 148, calls: 96, emails: 41, clubs_contacted: 62,
                positive_conversations: 30, callbacks_created: 19, trials_started: 7 }),
}
const KATE = {
  user_id: 'kate', name: 'Kate Leary',
  today: bucket(), week: bucket(),
  all: bucket({ contacts: 54, calls: 50, emails: 4, clubs_contacted: 31 }),
}
const SUMMARY = {
  today: bucket(), week: bucket(),
  all: bucket({ contacts: 202, calls: 146, emails: 45, clubs_contacted: 88,
                positive_conversations: 41, callbacks_created: 24, trials_started: 9 }),
}
const DRILL = {
  clubs: [
    { deal_id: 'd1', club_name: 'Applecross CC', state: 'WA', engagement_score: 44, count: 9 },
    { deal_id: 'd2', club_name: 'Bassendean CC', state: 'WA', engagement_score: 31, count: 4 },
  ],
  total: 148, club_count: 2,
}

const mount = async (ctx) => {
  const page = await ctx.newPage()
  const drillCalls = []
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) {
      return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'super_admin',
                    entitlements: { modules: [], status: 'active' } })
    }
    if (url.includes('/performance/drilldown')) {
      drillCalls.push(url)
      return json(DRILL)
    }
    if (url.includes('/sales-workspace/performance')) {
      return json({
        summary: SUMMARY, activity: [SAM, KATE],
        by_rep: [], totals: null, stage_columns: [],
      })
    }
    return json({})
  })
  return { page, drillCalls, errors }
}

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1100 } })

  const { page, drillCalls, errors } = await mount(ctx)
  await page.goto(PERF, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  const body = await page.innerText('body')

  // 1. The reported case: the table says something on a quiet Monday.
  check('the reps are listed even with a blank week', body.includes('Sam Barendse') && body.includes('Kate Leary'))
  check('the "nobody has made contact" note is gone', !body.includes('Nobody has made contact'))

  // 2. Three windows, in order, as KPI rows and as column groups.
  const kpiTitles = await page.locator('h3').allInnerTexts()
  check('a KPI row per window, in order',
        JSON.stringify(kpiTitles.slice(0, 3)), JSON.stringify(['Today', 'This week', 'All time']))
  const groups = await page.evaluate(() => {
    const table = [...document.querySelectorAll('table')]
      .find(t => t.innerText.includes('Salesperson') && t.innerText.includes('Clubs'))
    return [...table.querySelectorAll('thead tr')[0].querySelectorAll('th')]
      .map(th => ({ label: th.innerText.trim(), span: th.colSpan }))
  })
  check('three column groups over four columns each',
        JSON.stringify(groups.filter(g => g.label)),
        JSON.stringify([{ label: 'Today', span: 4 }, { label: 'This week', span: 4 },
                        { label: 'All time', span: 4 }]))

  // 3. Sam's all-time figures are the ones rendered, and a zero is not a button.
  const samCells = await page.evaluate(() => {
    const tr = [...document.querySelectorAll('tbody tr')].find(r => r.innerText.includes('Sam Barendse'))
    return [...tr.querySelectorAll('td')].slice(1).map(td => ({
      text: td.innerText.trim(), button: !!td.querySelector('button'),
    }))
  })
  check('twelve figure cells on a rep row', samCells.length, 12)
  check('all-time contacts/calls/emails/clubs render',
        JSON.stringify(samCells.slice(8).map(c => c.text)),
        JSON.stringify(['148', '96', '41', '62']))
  check('every all-time figure opens its clubs', samCells.slice(8).every(c => c.button))
  check('a zero stays plain text, not a button', samCells.slice(0, 8).every(c => !c.button && c.text === '0'))

  // 4. A group's first column carries the edge that separates it from the last.
  const edges = await page.evaluate(() => {
    const tr = [...document.querySelectorAll('tbody tr')].find(r => r.innerText.includes('Sam Barendse'))
    return [...tr.querySelectorAll('td')].slice(1).map(td => {
      const s = getComputedStyle(td)
      return parseFloat(s.borderLeftWidth) > 0 && s.borderLeftStyle !== 'none'
    })
  })
  check('the two later groups are ruled off from the one before',
        JSON.stringify(edges.map((e, i) => (e ? i : null)).filter(i => i !== null)),
        JSON.stringify([4, 8]))

  // 5. Clicking an all-time figure asks for that exact window on the wire.
  await page.evaluate(() => {
    const tr = [...document.querySelectorAll('tbody tr')].find(r => r.innerText.includes('Sam Barendse'))
    ;[...tr.querySelectorAll('td')][9].querySelector('button').click()
  })
  await page.waitForTimeout(600)
  const url = drillCalls[drillCalls.length - 1] || ''
  const q = new URL(url).searchParams
  check('the drill-down asks for panel=activity', q.get('panel'), 'activity')
  check('…window=all', q.get('window'), 'all')
  check('…metric=contacts', q.get('metric'), 'contacts')
  check('…for that rep', q.get('user_id'), 'sam')
  const afterClick = await page.innerText('body')
  check('the panel names the figure it opened', afterClick.includes('Sam Barendse — contacts all time'))
  check('…and lists the clubs behind it', afterClick.includes('Applecross CC') && afterClick.includes('Bassendean CC'))

  // 6. The totals row is the KPI strip's own all-time figure.
  const footer = await page.evaluate(() => {
    const table = [...document.querySelectorAll('table')].find(t => t.innerText.includes('Salesperson'))
    const tr = table.querySelector('tfoot tr')
    return [...tr.querySelectorAll('td')].slice(1).map(td => td.innerText.trim())
  })
  check('the Everyone row carries the all-time totals',
        JSON.stringify(footer.slice(8)), JSON.stringify(['202', '146', '45', '88']))
  check('…matching the All time KPI card',
        (await page.innerText('body')).includes('202'))

  // 7. Housekeeping.
  check('no page errors', errors.length === 0, errors[0] || '')
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(400)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check('no horizontal overflow at 390px', over <= 0, `${over}px`)
  const scrolls = await page.evaluate(() => {
    const table = [...document.querySelectorAll('table')].find(t => t.innerText.includes('Salesperson'))
    const box = table.closest('div')
    return box.scrollWidth > box.clientWidth && getComputedStyle(box).overflowX === 'auto'
  })
  check('the wide table scrolls inside its own box', scrolls)

  await page.close()
  await browser.close()
  console.log(`\n${pass.length} passed, ${fail.length} failed`)
  if (fail.length) process.exit(1)
}
run().catch(e => { console.error(e); process.exit(1) })
