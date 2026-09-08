// Drives the real Manage Grades screen in Chromium with the API stubbed at the
// network layer.
//
//   npx vite --port 5203 &
//   node frontend/verification/verify_grade_duplicates_browser.mjs [baseUrl]
//
// Asked for on Manage Grades: suggest the grades that look like duplicates.
// The backend rules are verified separately (verify_grade_duplicates.py); what
// is measured here is the SCREEN — that the exact merge lands on the wire, that
// dismissing one sends nothing else, that a club with nothing to sort out is
// shown no panel at all, and that the weaker tiers say so.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5203'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const CLUB = { id: 'org-1', name: 'Applecross Cricket Club', slug: 'applecross' }

const card = (name, games, runs, seasons, assoc, cats) => ({
  grade_name: name, display_name: name, games, runs,
  seasons, association_names: assoc, categories: cats,
})

// Two tiers plus a dismissable one, shaped like the backend's own payload.
const PAIRS = [
  {
    kind: 'same_name', confidence: 0.99,
    reason: 'the same name written two ways',
    canonical: 'A Grade', alias: 'A Grade (Gatorade)', bulk_safe: true,
    cautions: ['Both run by WASTCA.'],
    grade_a: card('A Grade', 12, 900, ['Summer 2024/25'], ['WASTCA'], ['senior']),
    grade_b: card('A Grade (Gatorade)', 10, 780, ['Summer 2025/26'], ['WASTCA'], ['senior']),
  },
  {
    kind: 'extra_words', confidence: 0.7,
    reason: 'one name carries extra words (colts, cup)',
    canonical: 'F Grade', alias: 'F Grade Colts Cup', bulk_safe: false,
    cautions: ['Classified differently (senior vs junior).',
               'They were never played in the same season, which reads as a rename.'],
    grade_a: card('F Grade', 9, 400, ['Summer 2024/25'], ['WASTCA'], ['senior']),
    grade_b: card('F Grade Colts Cup', 4, 120, ['Summer 2023/24'], ['WASTCA'], ['junior']),
  },
]

// A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN. Every interaction goes
// through this, so a build without the panel REPORTS each missing control by
// name rather than dying on the first absent locator and saying nothing at all
// about the other checks. Found by running the control, not by reading it.
async function press(page, locator, label) {
  if (await locator.count() === 0) {
    ck(`the ${label} control is on the card`, false, 'not found')
    return false
  }
  await locator.first().click()
  await page.waitForTimeout(1200)
  return true
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ pairs = PAIRS, width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1800 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))

  let live = pairs

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    const method = req.method()
    let payload = null
    try { payload = req.postData() ? JSON.parse(req.postData()) : null } catch { /* not json */ }
    calls.push({ path: p, method, payload, params: Object.fromEntries(url.searchParams) })
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

    if (/grade-merge-candidates/.test(p)) return json(live)
    // The stub MUTATES: one that answers the same thing every time cannot tell
    // a working action from a no-op.
    if (/^\/admin\/merge-grades$/.test(p)) {
      live = live.filter(x => x.alias !== payload.alias_name && x.canonical !== payload.alias_name)
      return json({ status: 'merged' })
    }
    if (/^\/admin\/ignore-grade-pair$/.test(p)) {
      live = live.filter(x => ![payload.name_a, payload.name_b].includes(x.alias))
      return json({ status: 'ignored' })
    }
    if (/grades-with-stats/.test(p)) return json([])
    if (/grade-merge-history/.test(p)) return json([])
    if (/^\/admin\/competitions/.test(p)) return json([])
    if (/^\/club-admin\/grades$/.test(p)) return json([])
    if (/settings/.test(p)) return json({ id: CLUB.id, name: CLUB.name })
    if (/^\/clubs\//.test(p)) return json({ ...CLUB, theme_config: {}, is_active: true })
    return json([])
  })

  await page.goto(`${BASE}/admin/grades`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1800)
  return { page, ctx, errors, calls, since: () => calls.length }
}

// ── the panel itself ──────────────────────────────────────────────────────
{
  const { page, ctx, errors, calls } = await open()
  const body = await page.locator('body').innerText()

  ck('the suggestions panel is drawn', /POSSIBLE DUPLICATE GRADES/i.test(body), body.slice(0, 300))
  ck('and counts what it found', /\(2\)/.test(body))
  ck('the near-certain tier names itself',
    /THE SAME NAME, WRITTEN TWO WAYS/i.test(body))
  ck('the weaker tier names itself', /ONE NAME HAS EXTRA WORDS/i.test(body))
  ck('and the weaker tier carries the check-it warning, while the certain one does not',
    (body.match(/CHECK IT'S THE SAME GRADE/gi) || []).length === 1,
    String((body.match(/CHECK IT'S THE SAME GRADE/gi) || []).length))
  ck('each pair says which way round it will merge',
    /A Grade \(Gatorade\)[\s\S]{0,40}merges into[\s\S]{0,40}A Grade/i.test(body))
  ck('the reason is shown', /one name carries extra words/i.test(body))
  ck('every caution is listed',
    /Classified differently/i.test(body) && /never played in the same season/i.test(body))
  ck('the CA association is shown on the card', /WASTCA/.test(body))
  ck('and each side reports its games and its seasons',
    /12 games/.test(body) && /Summer 2024\/25/.test(body))
  ck('the candidates were fetched with the club id',
    calls.some(c => /grade-merge-candidates/.test(c.path) && c.params.org_id === CLUB.id),
    JSON.stringify(calls.filter(c => /candidates/.test(c.path))))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── merging from a card ───────────────────────────────────────────────────
{
  const { page, ctx, calls, errors } = await open()
  const before = calls.length
  await press(page, page.getByRole('button', { name: 'Merge', exact: true }), 'Merge')
  const sent = calls.slice(before).filter(c => c.method === 'POST')

  ck('pressing Merge sends exactly one write', sent.length === 1, JSON.stringify(sent))
  ck('THE EXACT MERGE IS ON THE WIRE — the alias merges into the fuller record',
    sent[0] && sent[0].path === '/admin/merge-grades'
      && sent[0].payload.alias_name === 'A Grade (Gatorade)'
      && sent[0].payload.canonical_name === 'A Grade',
    JSON.stringify(sent[0]))
  const body = await page.locator('body').innerText()
  ck('and the merged pair leaves the panel', !/A Grade \(Gatorade\)/.test(body))
  ck('while the other pair stays', /F Grade Colts Cup/.test(body))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── flipping the direction ────────────────────────────────────────────────
{
  const { page, ctx, calls } = await open()
  await press(page, page.getByRole('button', { name: /Keep A Grade \(Gatorade\) instead/ }), 'flip-direction')
  const before = calls.length
  await press(page, page.getByRole('button', { name: 'Merge', exact: true }), 'Merge')
  const sent = calls.slice(before).filter(c => c.method === 'POST')

  ck('FLIPPING THE DIRECTION SENDS THE OTHER WAY ROUND — which spelling a club '
     + 'keeps on its own leaderboard is the club\'s call',
    sent[0] && sent[0].payload.alias_name === 'A Grade'
      && sent[0].payload.canonical_name === 'A Grade (Gatorade)',
    JSON.stringify(sent[0]))
  await ctx.close()
}

// ── dismissing a pair ─────────────────────────────────────────────────────
{
  const { page, ctx, calls, errors } = await open()
  const before = calls.length
  await press(page, page.getByRole('button', { name: 'Not a duplicate' }), 'Not a duplicate')
  const sent = calls.slice(before).filter(c => c.method === 'POST')

  ck('dismissing sends exactly one write', sent.length === 1, JSON.stringify(sent))
  ck('to the ignore endpoint, and NEVER a merge',
    sent[0] && sent[0].path === '/admin/ignore-grade-pair',
    JSON.stringify(sent[0]))
  ck('naming both grades', sent[0]
    && [sent[0].payload.name_a, sent[0].payload.name_b].sort().join('|')
       === ['A Grade', 'A Grade (Gatorade)'].sort().join('|'),
    JSON.stringify(sent[0] && sent[0].payload))
  const body = await page.locator('body').innerText()
  ck('and the dismissed pair leaves the panel', !/A Grade \(Gatorade\)/.test(body))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── nothing to sort out ───────────────────────────────────────────────────
{
  const { page, ctx, errors } = await open({ pairs: [] })
  const body = await page.locator('body').innerText()
  ck('A CLUB WITH NOTHING TO SORT OUT IS SHOWN NO PANEL AT ALL — one that can '
     + 'only ever say "everything is fine" is worse than none',
    !/POSSIBLE DUPLICATE GRADES/i.test(body))
  ck('while the manual merge builder is still there',
    /Merge Grades/i.test(body))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── a phone ───────────────────────────────────────────────────────────────
{
  const { page, ctx, errors } = await open({ width: 390 })
  const over = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', over <= 0, `${over}px`)
  ck('the panel still renders there',
    /POSSIBLE DUPLICATE GRADES/i.test(await page.locator('body').innerText()))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
