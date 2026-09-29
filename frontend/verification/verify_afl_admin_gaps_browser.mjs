// The BetterStats admin tools ported to football, driven in Chromium against a
// real football backend and the football production build: merging and
// ordering seasons, the player's date of birth / number / positions, draft
// mode and its PIN gate, stats by grade and its public note, and competitions
// with the public Competition filter.
//
// Run:  node verification/verify_afl_admin_gaps_browser.mjs http://localhost:4311/afl
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:4311/afl'
let pass = 0, fail = 0
const check = (label, ok, detail = '') => {
  if (ok) { pass++; console.log(`  ok   ${label}`) } else { fail++; console.log(`  FAIL ${label} ${detail}`) }
}
const count = (loc) => loc.count().catch(() => 0)
async function press(loc) { if (!(await count(loc))) return false; await loc.first().click().catch(() => {}); return true }
const textOf = async (loc) => (await count(loc)) ? (await loc.first().innerText().catch(() => '')) : ''

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }).catch(() => chromium.launch())
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } })
const page = await ctx.newPage()
const errors = [], bad = [], writes = []
page.on('pageerror', e => errors.push(String(e)))
page.on('dialog', d => d.accept())
page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 500) bad.push(`${r.status()} ${r.url()}`) })
page.on('request', r => {
  if (['PATCH', 'POST', 'PUT', 'DELETE'].includes(r.method()) && /\/api\/(club-admin|admin)\//.test(r.url()))
    writes.push({ m: r.method(), u: r.url(), b: r.postData() })
})
const body = (w) => { try { return JSON.parse(w?.b || '{}') } catch { return {} } }

await page.goto(`${BASE}/login`)
await page.locator('form input:not([type=password])').first().fill('coach')
await page.fill('input[type="password"]', 'pass1234')
await page.keyboard.press('Enter')
await page.waitForURL(/\/admin/, { timeout: 15000 })

// ── Seasons ────────────────────────────────────────────────────────────────
console.log('\n── Seasons: order and merge ──')
await page.goto(`${BASE}/admin/seasons`); await page.waitForTimeout(1500)
const down = page.getByRole('button', { name: /^Move .* down$/ })
check('each season can be moved', (await count(down)) > 0)
await press(down); await page.waitForTimeout(1200)
const reorder = writes.find(w => w.m === 'PUT' && w.u.endsWith('/club-admin/seasons/reorder'))
check('moving one writes the whole order', Array.isArray(body(reorder)) && body(reorder).length >= 3, reorder?.b || '')
const merge = page.getByTestId('season-merge')
check('the merge panel is on the page', (await count(merge)) > 0)
if (await count(merge)) {
  await merge.getByLabel('Season to keep').selectOption({ label: 'VAFA 2026' }).catch(() => {})
  await merge.getByLabel('Season to merge in').selectOption({ label: 'Juniors League 2026' }).catch(() => {})
  await press(merge.getByRole('button', { name: 'MERGE', exact: true }))
  await page.waitForTimeout(1500)
}
const mw = writes.find(w => w.m === 'POST' && w.u.endsWith('/club-admin/seasons/merges'))
check('a merge sends the two seasons', !!body(mw).canonical_season_id && !!body(mw).alias_season_id, mw?.b || '')
check('the merged season is marked with where it went', (await textOf(page.getByTestId('merged-badge'))).toUpperCase().includes('VAFA 2026'))
check('  ... and it can be undone', await press(merge.getByRole('button', { name: 'Undo' })))
await page.waitForTimeout(1500)
check('  ... with the undo request', writes.some(w => w.m === 'POST' && /\/merges\/[^/]+\/undo$/.test(w.u)))
check('  ... and the badge goes', (await count(page.getByTestId('merged-badge'))) === 0)

// ── Players ────────────────────────────────────────────────────────────────
console.log('\n── A player: date of birth, number, positions ──')
await page.goto(`${BASE}/admin/players`); await page.waitForTimeout(1500)
await press(page.getByRole('button', { name: 'Edit' }))
await page.waitForTimeout(800)
check('the drawer carries an action-photo field', (await count(page.getByTestId('hero-field'))) > 0)
await page.locator('input[type="date"]').first().fill('2008-03-04').catch(() => {})
check('the age is worked out as the date is typed', /Age \d+/.test(await textOf(page.getByTestId('player-age'))))
await page.getByLabel('Shirt number').fill('07').catch(() => {})
const ruck = page.getByRole('button', { name: 'Ruck' })
// A toggle: press it only when it is off, so a rerun over a player saved by an
// earlier run still ends with Ruck picked.
if ((await ruck.first().getAttribute('aria-pressed').catch(() => null)) !== 'true') await press(ruck)
await press(page.getByRole('button', { name: 'Save', exact: true }))
await page.waitForTimeout(1500)
const pw = [...writes].reverse().find(w => w.m === 'PATCH' && /\/club-admin\/players\/[^/]+$/.test(w.u))
const pb = body(pw)
check('the save sends the date of birth', pb.date_of_birth === '2008-03-04', pw?.b || '')
check('  ... the number as typed, "07" kept', pb.shirt_number === '07')
check('  ... and the position picked', Array.isArray(pb.positions) && pb.positions.includes('RUCK'))

// ── Settings: stats by grade ──────────────────────────────────────────────
console.log('\n── Stats by grade ──')
await page.goto(`${BASE}/admin/settings`); await page.waitForTimeout(1500)
const scope = page.getByTestId('stats-scope')
check('a club fielding two grade types is offered the setting', (await count(scope)) > 0)
if (await count(scope)) {
  await scope.getByLabel('Colts').uncheck().catch(() => {})
  await press(scope.getByRole('button', { name: /Save/ }))
  await page.waitForTimeout(1200)
}
const sw = [...writes].reverse().find(w => w.m === 'PATCH' && w.u.endsWith('/club-admin/settings') && (w.b || '').includes('stats_grade_categories'))
const cats = body(sw).stats_grade_categories || []
check('unticking Colts stores everything else, so a new category still counts',
  cats.includes('senior') && !cats.includes('colts') && cats.includes('masters'), sw?.b || '')

// ── Competitions ──────────────────────────────────────────────────────────
console.log('\n── Competitions ──')
await page.goto(`${BASE}/admin/merge-grades`); await page.waitForTimeout(1500)
check('Merge Grades carries the competitions panel', (await count(page.locator('#competitions'))) > 0)
check('grouping is offered from the season names', await press(page.getByRole('button', { name: /Group my grades/i })))
await page.waitForTimeout(1500)
check('  ... and posts to the football seed', writes.some(w => w.m === 'POST' && w.u.endsWith('/admin/competitions/seed')))
check('two competitions are drawn', (await count(page.getByTestId('competition-card'))) === 2,
  String(await count(page.getByTestId('competition-card'))))
check('the panel asks nothing of a background job on football', (await count(page.getByTestId('grouping-quiet'))) === 0)
const cdown = page.getByRole('button', { name: /^Move .* down$/ })
await press(cdown); await page.waitForTimeout(1200)
const cr = writes.find(w => w.m === 'POST' && w.u.endsWith('/admin/competitions/reorder'))
check('the competitions can be put in order', (body(cr).competition_ids || []).length === 2, cr?.b || '')

// ── The public site ───────────────────────────────────────────────────────
console.log('\n── The public leaderboard ──')
await page.goto(`${BASE}/cuw/leaderboard`); await page.waitForTimeout(2000)
check('the stats-by-grade note says what is left out', (await textOf(page.getByTestId('stats-scope-note'))).includes('Colts'))
const filter = page.getByTestId('competition-filter')
check('a Competition filter is offered', (await count(filter)) > 0)
const lbReq = page.waitForRequest(r => r.url().includes('/afl-leaderboard/') && r.url().includes('competition_id='), { timeout: 5000 }).catch(() => null)
if (await count(filter)) {
  const opts = await filter.locator('option').allInnerTexts()
  const juniors = opts.find(o => /Juniors/.test(o))
  await filter.locator('select').selectOption({ label: juniors }).catch(() => {})
}
check('picking one sends it with the leaderboard request', !!(await lbReq))
await page.waitForTimeout(1500)
check('  ... and the note goes, since the pick overrides the default', (await count(page.getByTestId('stats-scope-note'))) === 0)
check('the junior shows under the Juniors League', (await page.locator('body').innerText()).includes('Mark'))

console.log('\n── Draft mode and the PIN gate ──')
await page.goto(`${BASE}/admin/settings`); await page.waitForTimeout(1500)
const draft = page.getByTestId('draft-panel')
await draft.getByLabel('4-digit PIN').fill('4821').catch(() => {})
await press(draft.getByRole('button', { name: 'Turn on draft mode' }))
await page.waitForTimeout(1500)
check('draft mode is on', (await textOf(page.getByTestId('draft-status'))).startsWith('On'))
const anon = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage()
await anon.goto(`${BASE}/cuw`); await anon.waitForTimeout(2500)
const pinBox = anon.locator('input[placeholder="••••"]')
check('a visitor meets the PIN screen', (await count(pinBox)) > 0)
if (await count(pinBox)) {
  await pinBox.fill('4821'); await anon.keyboard.press('Enter'); await anon.waitForTimeout(2500)
}
check('  ... and the right PIN opens the club', (await count(pinBox)) === 0 && /leaderboard/i.test(await anon.locator('body').innerText()))
check('no horizontal overflow on a phone', await anon.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth))
await press(draft.getByRole('button', { name: 'Make the site public' }))
await page.waitForTimeout(1200)
check('the site can be made public again', (await textOf(page.getByTestId('draft-status'))).startsWith('Off'))

check('no page errors', errors.length === 0, errors.join(' | '))
check('no server errors', bad.length === 0, bad.join(' | '))
await browser.close()
console.log(`\nverify_afl_admin_gaps_browser: ${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
