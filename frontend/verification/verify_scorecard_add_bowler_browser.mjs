// Drives the real /admin/upload-scorecard review screen in Chromium, API stubbed at the network layer.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_scorecard_add_bowler_browser.mjs [baseUrl]
//
// Reported off a 1978 Sunbury U16 card: the scorer ran out of the eight analysis rows and wrote the
// 9th and 10th bowlers (Nikolic, McWilliam) in the unused part of the grid. The review screen could
// edit the bowlers the reader found but had no way to ADD one, so those two could never be imported.
// Checks:
//   * every innings offers "+ Add bowler", including one where the reader found no bowlers at all
//     (the whole bowling table used to vanish there);
//   * adding twice gives a 9th and 10th row; typing a name and picking a roster player fills it;
//   * Import sends exactly those two spells (the request on the wire) beside the original eight;
//   * a row can be removed again, and removing it takes its spell off the wire;
//   * an added row nobody matched to a player is warned about and is NOT imported;
//   * our own innings (opposition bowlers, no roster) can add a row too, without a player picker;
//   * 390px: the screen does not overflow sideways.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || '/tmp'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const NAMES = ['C Salathiel', 'C La Franki', 'R Day', 'D Watkins', 'S Bottoms', 'S James', 'R Coates', 'P Ogilvie', 'M Nikolic', 'A McWilliam']
const ID = n => 'pl-' + n.split(' ').pop().toLowerCase()
const ROSTER = NAMES.map(n => ({ id: ID(n), name: n }))
const SUGG = Object.fromEntries(NAMES.slice(0, 8).map(n => [n, ID(n)]))

// The eight bowlers the reader found on the card's second innings (Osborne batting, Sunbury bowling).
const EIGHT = [
  ['C Salathiel', 5, 1, 20, 4], ['C La Franki', 3, 0, 11, 0], ['R Day', 1, 0, 2, 1], ['D Watkins', 1, 0, 0, 0],
  ['S Bottoms', 1, 1, 0, 0], ['S James', 1, 0, 0, 0], ['R Coates', 1, 0, 1, 1], ['P Ogilvie', 1, 0, 1, 1],
].map(([name, overs, maidens, runs, wickets]) => ({ name, overs, maidens, runs, wickets, wides: null, no_balls: null }))

const card = ({ bowl2 = EIGHT, bowl1 = [] } = {}) => ({
  roster: ROSTER, suggestions: SUGG, match_info: {}, warnings: [], read_notes: null,
  match: { date: '1978-10-07', our_team: 'Sunbury', home_team: 'Sunbury', away_team: 'Osborne White', result: 'Sunbury won on 1st innings' },
  innings: [
    { innings_number: 1, batting_team: 'Sunbury', is_our_team: true, total_runs: 101, total_wickets: 4,
      batting: [{ name: 'C La Franki', position: 1, runs: 17, how_out: 'caught', bowler: 'R McDonald', fielder: 'x', dismissal_text: 'c x b R McDonald' }],
      bowling: bowl1, fall_of_wickets: [] },
    { innings_number: 2, batting_team: 'Osborne White', is_our_team: false, total_runs: 55, total_wickets: 10,
      batting: [{ name: 'R Grant', position: 1, runs: 10, how_out: 'caught', bowler: 'C Salathiel', fielder: 'x', dismissal_text: 'c x b C Salathiel' }],
      bowling: bowl2, fall_of_wickets: [] },
  ],
})

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function toReview({ payload = card(), width = 1280 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(4000)  // an absent control must be REPORTED fast, not hang the run
  const seen = { posts: [], errors: [], unknown: [] }
  page.on('pageerror', e => seen.errors.push(String(e)))
  await page.route('**/api/**', async route => {
    const req = route.request()
    const path = new URL(req.url()).pathname.replace(/^\/api/, '')
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (/^\/auth\/me/.test(path)) return json({ id: 'u1', username: 'scorer', display_name: 'Scorer', role: 'club_admin', club_slug: 'sunbury', club_id: 'org1', entitlements: { modules: ['admin'], status: 'active' } })
    if (/\/scorecard\/extract$/.test(path)) return json(payload)
    if (/\/manual-entries\/games$/.test(path) && req.method() === 'POST') {
      seen.posts.push(JSON.parse(req.postData() || '{}'))
      return json({ id: 'g-new', grand_final: null })
    }
    if (/\/manual-entries\/games$/.test(path)) return json([])
    if (/\/club-admin\/seasons$/.test(path)) return json([{ id: 's1', name: 'Summer 1978/79', year: 1978 }])
    if (/\/manual-entries\/seasons\/for-date/.test(path)) return json({ season: { id: 's1', name: 'Summer 1978/79', year: 1978 }, expected_name: 'Summer 1978/79', year: 1978 })
    if (/\/manual-entries\/grades$/.test(path)) return json([])
    if (/\/club-admin\/players$/.test(path)) return json(ROSTER.map(p => ({ id: p.id, display_name: p.name, is_player: true })))
    if (/check-duplicate/.test(path)) return json({ matches: [] })
    seen.unknown.push(`${req.method()} ${path}`)
    return json({})
  })
  await page.goto(`${BASE}/admin/upload-scorecard`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('input[type=file]', { timeout: 20000 })
  await page.setInputFiles('input[type=file]', { name: 'card.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 stub') })
  await page.getByRole('button', { name: 'Read scorecard' }).click()
  await page.waitForSelector('text=OUR BOWLING, text=OPPOSITION BOWLING, [data-testid="add-bowler-1"]', { timeout: 20000 }).catch(() => {})
  await page.waitForTimeout(400)
  return { ctx, page, seen }
}

// Bowling table of an innings: rows of [input values], read through the table's own label so the
// old screen (no Add button) is still readable. Innings 0 is ours (label OPPOSITION BOWLING),
// innings 1 the opposition's (label OUR BOWLING). Null when the table is not drawn.
const LABEL = ['OPPOSITION BOWLING', 'OUR BOWLING']
const bowlRows = (page, inn) => page.evaluate(label => {
  const lab = [...document.querySelectorAll('div')].find(d => d.children.length === 0 && d.textContent.trim() === label)
  const holder = lab?.closest('.overflow-x-auto')
  if (!holder) return null
  return [...holder.querySelectorAll('tbody tr')].map(tr => [...tr.querySelectorAll('input')].map(x => x.value))
}, LABEL[inn])
const holderLoc = (page, inn) => page.locator('.overflow-x-auto', { has: page.locator(`div:text-is("${LABEL[inn]}")`) }).last()
// Click a control only if it exists; report whether it did.
const tap = async loc => { if (await loc.count() === 0) return false; await loc.first().click(); return true }
const addBtn = (page, inn) => page.locator(`[data-testid="add-bowler-${inn}"]`)

const importNow = async page => {
  await tap(page.getByRole('button', { name: 'Import match' }))
  await tap(page.getByRole('button', { name: /^Import/ }).last())
  await page.waitForTimeout(600)
}

// ── Control reads: these must be able to FAIL on the old screen ──────────────
{
  const { ctx, page, seen } = await toReview()
  const addBtns = await page.locator('[data-testid^="add-bowler-"]').count()
  ck('every innings has a + Add bowler button', addBtns === 2, `found ${addBtns}`)

  let rows = await bowlRows(page, 1)
  ck('innings 2 starts with the eight bowlers the reader found', !!rows && rows.length === 8, JSON.stringify(rows))

  await tap(addBtn(page, 1)); await tap(addBtn(page, 1))
  rows = await bowlRows(page, 1)
  ck('two clicks give a 9th and a 10th row', !!rows && rows.length === 10, `rows=${rows?.length}`)

  // Fill row 9 and 10: name typed in the Bowler cell, then the figures.
  const fill = async (idx, name, o, m, r, w) => {
    const tr = holderLoc(page, 1).locator('tbody tr').nth(idx)
    const inputs = tr.locator('input')
    if (await inputs.count() < 6) return false   // no such row on this screen
    await inputs.nth(0).fill(name)
    // inputs: 0 bowler, 1 player picker, 2 O, 3 M, 4 R, 5 W
    await inputs.nth(1).focus()
    await tr.locator(`button:has-text("${name.split(' ').pop()}")`).first().dispatchEvent('mousedown')
    await inputs.nth(2).fill(String(o)); await inputs.nth(3).fill(String(m))
    await inputs.nth(4).fill(String(r)); await inputs.nth(5).fill(String(w))
    return true
  }
  await fill(8, 'M Nikolic', 1, 0, 1, 0)
  await fill(9, 'A McWilliam', 1, 0, 1, 1)
  rows = await bowlRows(page, 1)
  ck('row 9 holds Nikolic with his figures', !!rows && rows[8]?.[0] === 'M Nikolic' && rows[8]?.slice(2, 6).join(',') === '1,0,1,0', JSON.stringify(rows?.[8]))
  ck('row 10 holds McWilliam with his figures', !!rows && rows[9]?.[0] === 'A McWilliam' && rows[9]?.slice(2, 6).join(',') === '1,0,1,1', JSON.stringify(rows?.[9]))
  ck('both are matched to a roster player, so nothing is unmatched', (await page.getByText(/aren't matched to a player/).count()) === 0)

  await page.screenshot({ path: `${SHOTS}/add_bowler_review.png`, fullPage: false })

  await importNow(page)
  const post = seen.posts[0]
  ck('the import was sent', !!post, `unknown: ${seen.unknown.join(', ')}`)
  const spells = (post?.bowling_spells || []).filter(s => s.innings_number === 2)
  ck('ten spells go on the wire for innings 2', spells.length === 10, `got ${spells.length}`)
  const nik = spells.find(s => s.player_id === 'pl-nikolic')
  const mcw = spells.find(s => s.player_id === 'pl-mcwilliam')
  ck('Nikolic: 1 over, 0 maidens, 1 run, 0 wickets', !!nik && nik.overs === 1 && nik.runs === 1 && nik.wickets === 0, JSON.stringify(nik))
  ck('McWilliam: 1 over, 0 maidens, 1 run, 1 wicket', !!mcw && mcw.overs === 1 && mcw.runs === 1 && mcw.wickets === 1, JSON.stringify(mcw))
  const sal = spells.find(s => s.player_id === 'pl-salathiel')
  ck('the original eight are untouched (Salathiel 5-1-20-4)', !!sal && sal.overs === 5 && sal.runs === 20 && sal.wickets === 4, JSON.stringify(sal))
  ck('no page errors', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}

// ── Remove, and the unmatched row ────────────────────────────────────────────
{
  const { ctx, page, seen } = await toReview()
  await tap(addBtn(page, 1))
  let rows = await bowlRows(page, 1)
  ck('an added row nobody matched is warned about', (await page.getByText(/1 of our rows aren't matched to a player and won't be imported/).count()) === 1, `rows=${rows?.length}`)
  await tap(page.getByRole('button', { name: 'Remove bowler 9' }))
  rows = await bowlRows(page, 1)
  ck('Remove takes the blank row off again', !!rows && rows.length === 8, `rows=${rows?.length}`)
  await tap(page.getByRole('button', { name: 'Remove bowler R Coates' }))
  rows = await bowlRows(page, 1)
  ck('removing a read bowler drops exactly that one', !!rows && rows.length === 7 && !rows.some(r => r[0] === 'R Coates'), JSON.stringify(rows?.map(r => r[0])))
  await importNow(page)
  const spells = (seen.posts[0]?.bowling_spells || []).filter(s => s.innings_number === 2)
  ck('seven spells go on the wire, Coates is gone', spells.length === 7 && !spells.some(s => s.player_id === 'pl-coates'), `got ${spells.length}`)
  await ctx.close()
}

// ── A blank row is never imported ────────────────────────────────────────────
{
  const { ctx, page, seen } = await toReview()
  await tap(addBtn(page, 1))
  await importNow(page)
  const spells = (seen.posts[0]?.bowling_spells || []).filter(s => s.innings_number === 2)
  ck('a row with no player picked is not imported', spells.length === 8, `got ${spells.length}`)
  await ctx.close()
}

// ── The reader found no bowlers at all ───────────────────────────────────────
{
  const { ctx, page } = await toReview({ payload: card({ bowl2: [], bowl1: [] }) })
  ck('an innings with no bowlers read still offers + Add bowler', (await page.locator('[data-testid="add-bowler-1"]').count()) === 1)
  ck('and says no bowlers were read', (await page.getByText('No bowlers were read for this innings.').count()) === 2)
  await tap(addBtn(page, 1))
  const rows = await bowlRows(page, 1)
  ck('adding to it makes the first row', !!rows && rows.length === 1, `rows=${rows?.length}`)
  await ctx.close()
}

// ── Our own innings: opposition bowlers, no roster picker ────────────────────
{
  const { ctx, page } = await toReview()
  await tap(addBtn(page, 0))
  const rows = await bowlRows(page, 0)
  ck('our innings adds an opposition bowler row', !!rows && rows.length === 1, `rows=${rows?.length}`)
  ck('with no player picker, just name and figures (5 inputs)', !!rows && rows[0].length === 5, JSON.stringify(rows?.[0]))
  await ctx.close()
}

// ── Phone width ──────────────────────────────────────────────────────────────
{
  const { ctx, page } = await toReview({ width: 390 })
  await page.screenshot({ path: `${SHOTS}/add_bowler_390.png` })
  const w = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }))
  ck('390px: the page does not scroll sideways', w.sw <= w.cw + 1, `${w.sw} vs ${w.cw}`)
  await ctx.close()
}

console.log(`\n${pass} passed, ${fail} failed`)
await browser.close()
process.exit(fail ? 1 : 0)
