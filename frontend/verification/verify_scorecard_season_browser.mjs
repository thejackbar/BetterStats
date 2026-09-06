// Drives the real Upload Scorecard screen in Chromium with the API stubbed
// at the network layer.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_scorecard_season_browser.mjs [baseUrl]
//
// Reported off a live club: a card uploaded from a 1974 PDF was filed under
// Summer 1999/00, because the season dropdown only offers seasons the club
// already has and this club's list starts at 1996/97. The season field was
// simply left blank and whatever got picked was what the game went in under.
//
// The club here has the reported club's shape: nothing before 1996/97.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const SEASONS = [
  { id: 's-2025', name: 'Summer 2025/26', year: 2025 },
  { id: 's-1999', name: 'Summer 1999/00', year: 1999 },
  { id: 's-1996', name: 'Summer 1996/97', year: 1996 },
]
const GRADES = [{ id: 'g-1999', name: '2nd Grade', season_id: 's-1999', season_name: 'Summer 1999/00' }]

// What the reader hands back for the reported card.
const extractFor = (date) => ({
  match: { date, home_team: 'Newry', away_team: 'Collegians 2nd XI', our_team: 'Collegians 2nd XI', venue: '', result: '', winning_team: 'Collegians 2nd XI' },
  innings: [
    { innings_number: 1, batting_team: 'Newry', is_our_team: false, total_runs: 118, total_wickets: 10,
      batting: [{ name: 'R Kelly', runs: 41 }], bowling: [{ name: 'J Smith', overs: 14, runs: 38, wickets: 5 }] },
    { innings_number: 2, batting_team: 'Collegians 2nd XI', is_our_team: true, total_runs: 140, total_wickets: 6,
      batting: [{ name: 'J Smith', runs: 64 }], bowling: [{ name: 'G Nolan', overs: 16, runs: 52, wickets: 3 }] },
  ],
  roster: [{ id: 'p1', name: 'Smith, John' }],
  warnings: [], match_info: {},
})

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

/**
 * The upload screen with the API stubbed. `date` is what the reader reports
 * for the card. Returns the page plus every call it made, so a check can
 * assert what actually went on the wire rather than what the screen says.
 */
async function openUpload(date, { width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))

  // Seasons the club holds, mutated by a create so the stub behaves like a
  // real backend — one that answers the same thing forever cannot tell a
  // working create from a no-op.
  const seasons = SEASONS.map(s => ({ ...s }))

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = req.method()
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

    if (method !== 'GET') {
      let payload = null
      try { payload = req.postDataJSON() } catch { payload = null }
      calls.push({ path, method, payload })
    } else if (/seasons\/for-date/.test(path)) {
      calls.push({ path: `${path}?${url.searchParams}`, method })
    }

    if (/^\/auth\/me/.test(path)) {
      return json({ id: 'u1', username: 'admin', role: 'club_admin', capabilities: ['*'],
        entitlements: { modules: ['stats'], status: 'active' } })
    }
    if (/^\/club-admin\/seasons$/.test(path)) return json(seasons)
    if (/manual-entries\/grades$/.test(path) && method === 'GET') return json(GRADES)
    if (/^\/club-admin\/players/.test(path) && method === 'GET') return json([{ id: 'p1', name: 'Smith, John' }])

    // The server owns the Jul-Jun boundary; this mirrors it for the stub.
    if (/manual-entries\/seasons\/for-date/.test(path)) {
      const iso = url.searchParams.get('played_at') || ''
      const [y, m] = iso.split('-').map(Number)
      const year = m >= 7 ? y : y - 1
      const expected = `Summer ${year}/${String((year + 1) % 100).padStart(2, '0')}`
      const hit = seasons.find(s => s.year === year) || null
      return json({ year, expected_name: expected, season: hit, season_created: false, grade: null, grade_created: false })
    }
    if (/manual-entries\/seasons$/.test(path) && method === 'POST') {
      const body = req.postDataJSON()
      const made = { id: `s-new-${body.year}`, name: body.name, year: body.year }
      seasons.push(made)
      return json(made)
    }
    if (/manual-entries\/grades$/.test(path) && method === 'POST') {
      const body = req.postDataJSON()
      return json({ id: 'g-new', name: body.name, season_id: body.season_id })
    }
    if (/scorecard\/extract/.test(path)) return json(extractFor(date))
    if (/check-duplicate/.test(path)) return json({ duplicate: false })
    return json({})
  })

  await page.goto(`${BASE}/admin/upload-scorecard`, { waitUntil: 'networkidle' })
  await page.setInputFiles('input[type="file"]', {
    name: 'card.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('x'),
  })
  await page.getByRole('button', { name: /read/i }).first().click()
  // The review form's own date field — `text=Season` also matches the
  // sidebar's "2026/27 SEASON", which at 390px is inside a closed drawer and
  // never becomes visible.
  await page.waitForSelector('input[type="date"]', { timeout: 15000 })
  await page.waitForTimeout(600)
  return { page, ctx, errors, calls }
}

// The label showing on the Season picker, read off the rendered control.
const seasonLabel = (page) => page.evaluate(() => {
  const lab = [...document.querySelectorAll('label')].find(l => /^Season/.test(l.textContent.trim()))
  if (!lab) return ''
  const box = lab.parentElement
  const sel = box.querySelector('select')
  if (sel) return sel.options[sel.selectedIndex]?.textContent?.trim() || ''
  return (box.querySelector('button')?.textContent || '').trim()
})

// ------------------------------- a card older than every season the club has

{
  console.log('\nA 1974 card at a club whose seasons start in 1996')
  const { page, ctx, errors, calls } = await openUpload('1974-11-30')

  const asked = calls.find(c => /for-date/.test(c.path))
  ck('the screen asks the server which season the date belongs to',
    !!asked && /1974-11-30/.test(asked.path), asked?.path || 'never asked')

  const created = calls.find(c => /manual-entries\/seasons$/.test(c.path) && c.method === 'POST')
  ck('the missing season is created rather than left blank', !!created, 'no create call')
  ck('it is named the way the club names a season',
    created?.payload?.name === 'Summer 1974/75', JSON.stringify(created?.payload))
  ck('and carries its year', created?.payload?.year === 1974, JSON.stringify(created?.payload))

  const label = await seasonLabel(page)
  ck('the new season is what the form is set to', /1974\/75/.test(label), label)

  const note = await page.locator('[data-testid="season-created-note"]').first()
  ck('the screen says it added a season', await note.count() > 0 && /had no season/i.test(await note.textContent()),
    (await note.count()) ? await note.textContent() : 'no note')
  ck('no mismatch is claimed when the season is the right one',
    await page.locator('[data-testid="season-mismatch-note"]').count() === 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// -------------------------------------- a card inside a season the club has

{
  console.log('\nA card the club already has a season for')
  const { page, ctx, errors, calls } = await openUpload('1999-11-06')
  const created = calls.find(c => /manual-entries\/seasons$/.test(c.path) && c.method === 'POST')
  ck('no season is created', !created, JSON.stringify(created?.payload))
  const label = await seasonLabel(page)
  ck('the club\'s own 1999/00 is selected', /1999\/00/.test(label), label)
  ck('nothing is claimed to have been added',
    await page.locator('[data-testid="season-created-note"]').count() === 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------------------- picking the wrong one by hand

{
  console.log('\nFiling a card against a season its date does not fall in')
  const { page, ctx, errors } = await openUpload('1999-11-06')
  await page.evaluate(() => {
    const lab = [...document.querySelectorAll('label')].find(l => /^Season/.test(l.textContent.trim()))
    const sel = lab.parentElement.querySelector('select')
    const opt = [...sel.options].find(o => /2025\/26/.test(o.textContent))
    sel.value = opt.value
    sel.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await page.waitForTimeout(400)
  const note = page.locator('[data-testid="season-mismatch-note"]').first()
  ck('the screen says so instead of letting it through silently', await note.count() > 0)
  const text = (await note.count()) ? await note.textContent() : ''
  ck('and names both the season picked and the one the date falls in',
    /1999\/00/.test(text) && /2025\/26/.test(text), text)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------------------------ correcting a misread date

{
  console.log('\nCorrecting a date the reader got wrong')
  const { page, ctx, errors } = await openUpload('1999-11-06')
  await page.evaluate(() => {
    const el = document.querySelector('input[type="date"]')
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
    setter.call(el, '1974-11-30')
    el.dispatchEvent(new Event('input', { bubbles: true }))
    el.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await page.waitForTimeout(700)
  const note = page.locator('[data-testid="season-mismatch-note"]').first()
  ck('the season no longer matches the corrected date, and it says so',
    await note.count() > 0 && /1974\/75/.test(await note.textContent()),
    (await note.count()) ? await note.textContent() : 'no note')
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// -------------------------------------------------------------------- phone

{
  console.log('\nOn a phone')
  const { page, ctx, errors } = await openUpload('1974-11-30', { width: 390 })
  ck('the season note still shows at 390px',
    await page.locator('[data-testid="season-created-note"]').count() > 0)
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', overflow <= 0, `${overflow}px`)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
