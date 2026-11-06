/**
 * Club grades in the Awards form's Subcategory / Grade list, driven in a real browser.
 *
 * Run:
 *   npx vite preview --port 5199 &     (after npm run build)
 *   node verification/verify_award_club_grades_browser.mjs [baseUrl]
 *
 * Reported by Shoalwater Bay: the grade list when adding a premiership offers the starter set (1st XI, 2nd XI,
 * 3rd XI) and not the club's own grades, so the 1995/96 C grade premiership went in under "3rd XI". The form now
 * adds the grades the club plays in (from /organisations/{id}/grades) for Premiership and Club Award, never twice,
 * and gives a club grade the usual team awards when the award setup says nothing about it. Every read is guarded so
 * a CONTROL RUN against the old build reports each check instead of dying on the first absent locator.
 */
import { chromium } from 'playwright'
import { existsSync, mkdirSync } from 'node:fs'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const SHOTS = process.env.SHOTS || '/tmp/award-grade-shots'
mkdirSync(SHOTS, { recursive: true })
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => { if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) } }

const DEFS = [
  ...['1st XI', '2nd XI', '3rd XI'].flatMap((sub, i) =>
    ['Premiership', 'Captain'].map((ach, j) => ({ id: `d${i}${j}`, category: 'Premiership', subcategory: sub, achievement: ach, active: true }))),
  { id: 'c1', category: 'Club Award', subcategory: 'Perpetual', achievement: 'Most Improved', active: true },
]
const GRADES = [{ name: 'A grade', display_order: 1 }, { name: 'B grade', display_order: 2 }, { name: 'C grade', display_order: 3 },
                { name: 'C2 grade', display_order: 4 }, { name: '3rd XI', display_order: null }]

const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome'
const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(width = 1440) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(4000)
  page.setDefaultNavigationTimeout(60000)
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await page.route(/\/api\//, async route => {
    const p = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    const json = b => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (p.startsWith('/auth/me')) return json({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'club_admin', club_id: 'c1', club_slug: 'shoalwater',
      entitlements: { modules: ['stats'], status: 'active' } })
    if (/\/organisations\/c1\/grades$/.test(p)) return json(GRADES)
    if (/\/organisations\/c1\/seasons$/.test(p)) return json([{ id: 's1', name: '1995/96', year: 1995 }])
    if (/award-definitions/.test(p)) return json(DEFS)
    if (/\/players/.test(p)) return json([{ id: 'p1', name: 'Alpha, Anne', display_name: 'Alpha, Anne' }])
    if (/\/achievements/.test(p)) return json([])
    return json([])
  })
  await page.goto(`${BASE}/admin/awards`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1200)
  return { page, ctx, errors }
}
const optionsOf = (sel) => sel.locator('option').allInnerTexts().catch(() => [])
const subcatSelect = page => page.locator('select').filter({ has: page.locator('option', { hasText: 'Other…' }) })

{
  const { page, ctx, errors } = await open()
  await page.getByRole('button', { name: /^\+?\s*Add/ }).first().click().catch(() => {})
  await page.waitForTimeout(400)
  const catSel = page.locator('select').filter({ has: page.locator('option', { hasText: 'Premiership' }) }).first()
  await catSel.selectOption('Premiership').catch(() => {})
  const subcat = page.locator('select').filter({ has: page.locator('option', { hasText: '1st XI' }) }).first()
  const opts = await optionsOf(subcat)
  ck('Premiership offers the club\'s own C grade', opts.includes('C grade'), JSON.stringify(opts))
  ck('and the other grades the club plays in', opts.includes('A grade') && opts.includes('B grade') && opts.includes('C2 grade'), JSON.stringify(opts))
  ck('the award setup\'s own choices are still there', opts.includes('1st XI') && opts.includes('3rd XI'), JSON.stringify(opts))
  ck('a grade the setup already lists is not offered twice', opts.filter(o => o === '3rd XI').length === 1, JSON.stringify(opts))
  ck('Other… is still the last choice', opts[opts.length - 1] === 'Other…', JSON.stringify(opts))
  await subcat.selectOption('C grade').catch(() => {})
  const ach = page.locator('select').filter({ has: page.locator('option', { hasText: '12th Man' }) }).first()
  const aopts = await optionsOf(ach)
  ck('a club grade with no setup gets the usual team awards', ['Premiership', 'Player of the Grand Final', 'Captain', '12th Man', '13th Man'].every(a => aopts.includes(a)), JSON.stringify(aopts))
  await page.screenshot({ path: `${SHOTS}/premiership.png` })
  await subcat.selectOption('3rd XI').catch(() => {})
  const aopts2 = await optionsOf(page.locator('select').filter({ has: page.locator('option', { hasText: 'Captain' }) }).first())
  ck('a grade the setup does define keeps the setup\'s own awards, not the defaults', aopts2.includes('Premiership') && aopts2.includes('Captain') && !aopts2.includes('12th Man'), JSON.stringify(aopts2))
  // Club Award: the grades are offered too, Perpetual stays
  await catSel.selectOption('Club Award').catch(() => {})
  const sub2 = await optionsOf(page.locator('select').filter({ has: page.locator('option', { hasText: 'Perpetual' }) }).first())
  ck('Club Award offers the club grades beside the setup\'s own', sub2.includes('Perpetual') && sub2.includes('C grade'), JSON.stringify(sub2))
  // Milestone: not a team category, so no grades
  await catSel.selectOption('Milestone').catch(() => {})
  const sub3 = await optionsOf(page.locator('select').filter({ has: page.locator('option', { hasText: 'Other…' }) }).first())
  ck('a category that is not a team award gets no grades', !sub3.includes('C grade'), JSON.stringify(sub3))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}
{
  const { page, ctx } = await open(390)
  await page.getByRole('button', { name: /^\+?\s*Add/ }).first().click().catch(() => {})
  await page.waitForTimeout(400)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ck('the Add honour form does not overflow at 390px', overflow <= 1, `overflow ${overflow}px`)
  await page.screenshot({ path: `${SHOTS}/390.png` })
  await ctx.close()
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
