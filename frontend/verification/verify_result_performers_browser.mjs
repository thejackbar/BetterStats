// Drives the REAL BetterPosts editor in Chromium with the API stubbed at the network layer.
//
// Reported (North Perth, Oct 2026): "the results posts show our batters' stats alongside the
// opposition's bowlers, instead of our own bowling figures". Asked for: an option to show your
// club's players or the opposition's on a results post.
//
//   npx vite build --outDir /var/tmp/np_dist && npx vite preview --outDir /var/tmp/np_dist --port 5199 &
//   node verify_result_performers_browser.mjs [baseUrl]
//
// Two screens:
//   Final Score (Classic, C4), after importing a match: the server sends each side's `bowling` as the
//     bowling in the innings that side BATTED, i.e. the other side's bowlers. "Our Bowlers" must hold
//     OUR bowlers (the figures in the away list) and "Their Bowlers" the opposition's.
//   Results roundup, Wrap + Leaders (RR7): a "Players shown" switch (Our club / Opposition). The post
//     heading, the names on the post and the editor's labels and inputs all follow it, and a row from
//     an older pull with no opposition lists shows an empty column rather than breaking.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

const SETTINGS = { id: 'org-1', name: 'North Perth Cricket Club', short_name: 'NPCC', slug: 'northperth', logo_url: null, primary_color: '#7a1229', accent_color: '#e0a526', theme_config: null }
const ME = { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'northperth', entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' } }

// A match as the server builds it: home batted first, and each side's `bowling` is the bowling in the
// innings that side batted, so it lists the OTHER side's bowlers.
const bat = (short, r, b) => ({ first: '', last: short.split('. ')[1], short, r, b, notOut: false, didNotBat: false, pid: null })
const bowl = (short, w, r, o) => ({ first: '', last: short.split('. ')[1], short, o, m: 0, r, w, econ: r / 8, pid: null })
const SCORECARD = {
  meta: { competition: '1ST GRADE', round: 'ROUND 2', venue: 'CHARLES VERYARD RESERVE', date: '2026-10-17', result: 'NORTH PERTH WON BY 1 RUN' },
  home: {
    name: 'North Perth Cricket Club', short: 'NPCC', total: '134', wickets: 3, overs: '50',
    batting: [bat('M. NPBATONE', 50, 89), bat('B. NPBATTWO', 32, 44), bat('U. NPBATTHREE', 20, 30)],
    bowling: [bowl('N. OPPBOWLONE', 1, 23, '5.1'), bowl('M. OPPBOWLTWO', 1, 24, '7'), bowl('Z. OPPBOWLTHREE', 0, 30, '8')],   // bowled by THEM
  },
  away: {
    name: 'Bassendean CC', short: 'BCC', total: '133', wickets: 10, overs: '49',
    batting: [bat('A. OPPBATONE', 61, 80), bat('C. OPPBATTWO', 28, 40), bat('D. OPPBATTHREE', 14, 22)],
    bowling: [bowl('C. NPBOWLONE', 3, 22, '7'), bowl('E. NPBOWLTWO', 3, 31, '8'), bowl('B. NPBOWLTHREE', 2, 21, '6')],   // bowled by US
  },
}

// A roundup as the importer sends it: ours plus (from now on) the opposition's.
const ROUND = {
  season: '2026/27',
  dates: [{
    label: 'SAT 17 OCT', round: 'ROUND 2',
    results: [
      { grade: '1ST GRADE', opp: 'BASSENDEAN', oppMono: 'BAS', us: '3/134', them: '133', outcome: 'W', margin: 'BY 7 WICKETS',
        topBat: [{ name: 'M. NPBATONE', line: '50 (89)' }, { name: 'B. NPBATTWO', line: '32* (44)' }],
        topBowl: [{ name: 'C. NPBOWLONE', line: '3/22 (7.0)' }, { name: 'E. NPBOWLTWO', line: '3/31 (8.0)' }],
        oppTopBat: [{ name: 'A. OPPBATONE', line: '61 (80)' }, { name: 'C. OPPBATTWO', line: '28 (40)' }],
        oppTopBowl: [{ name: 'N. OPPBOWLONE', line: '1/23 (5.1)' }, { name: 'M. OPPBOWLTWO', line: '1/24 (7.0)' }] },
      // an older pull, from before the opposition's lists existed
      { grade: '3RD GRADE', opp: 'SWANBOURNE', oppMono: 'SWA', us: '148', them: '206', outcome: 'L', margin: 'BY 58 RUNS',
        topBat: [{ name: 'Q. OLDBAT', line: '35 (40)' }], topBowl: [{ name: 'Q. OLDBOWL', line: '2/13 (2.0)' }] },
    ],
  }],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openEditor(query, template, viewport = { width: 1700, height: 2300 }, mobile = false) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const errors = []
  const seen = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_|404|fonts/.test(m.text())) errors.push(m.text()) })
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort())
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    seen.push(url)
    if (/\/auth\/me/.test(url)) return route.fulfill(json(ME))
    if (/\/admin\/social\/match-lookup/.test(url)) return route.fulfill(json({ kind: 'match', match_id: 'm1' }))
    if (/\/admin\/social\/scorecard\//.test(url)) return route.fulfill(json(SCORECARD))
    if (/\/admin\/social\/results/.test(url)) return route.fulfill(json(ROUND))
    if (/\/admin\/social\/potm\//.test(url)) return route.fulfill(json({ match: {}, players: [] }))
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json([]))
    if (/sponsors\/post-default/.test(url)) return route.fulfill(json({ sponsor_ids: [], source: 'club' }))
    if (/sponsors/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  await page.addInitScript((t) => { localStorage.setItem('bs_social_template', t); localStorage.setItem('bs_social_post_size', 'square') }, template)
  await page.goto(`${BASE}/admin/social-post?${query}`, { waitUntil: 'domcontentloaded' })
  // A phone has no DOWNLOAD PNG button in view: give the editor a moment instead.
  if (mobile) await page.waitForTimeout(2500)
  else await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 30000 })
  return { ctx, page, errors, seen }
}
const body = async (page) => (await page.locator('body').innerText()).replace(/\s+/g, ' ')
// The editor's controls sit under Content, Design or Data. Open whichever tab holds `test`.
const visible = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
async function reveal(page, loc) {
  for (const t of ['Content', 'Data', 'Design', null]) {
    if (await visible(loc)) return true
    if (t) { await page.getByRole('button', { name: t, exact: true }).first().click().catch(() => {}); await page.waitForTimeout(300) }
  }
  return visible(loc)
}
// An attribute of a test id, or null when there is no such element (so an older build reports, not crashes).
const attr = (page, id, name) => page.evaluate(([i, n]) => { const e = document.querySelector(`[data-testid="${i}"]`); return e ? e.getAttribute(n) : null }, [id, name])
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* the check reports it */ } return false }
// The text inputs inside the editor block headed by `label`.
const inputsUnder = (page, label) => page.evaluate((l) => {
  const lab = Array.from(document.querySelectorAll('label, span')).find((e) => e.textContent.trim().toLowerCase() === l.toLowerCase())
  const box = lab && lab.closest('div.mb-3, div.flex.flex-col')
  return box ? Array.from(box.querySelectorAll('input')).map((i) => i.value).filter(Boolean) : null
}, label)

// ───────── Final Score: whose bowlers ─────────
console.log('\n# Final Score, after importing a match')
{
  const { ctx, page, errors } = await openEditor('type=result&template=C4', 'C4')
  await page.getByPlaceholder(/Match link from play\.cricket/).first().fill('m1')
  await page.getByRole('button', { name: /^(Import|Fetch)$/ }).first().click()
  await page.waitForTimeout(1500)
  await reveal(page, page.getByText('Our Bowlers', { exact: true }))
  const ourBat = await inputsUnder(page, 'Our Batters')
  const ourBowl = await inputsUnder(page, 'Our Bowlers')
  const theirBat = await inputsUnder(page, 'Their Batters')
  const theirBowl = await inputsUnder(page, 'Their Bowlers')
  const has = (list, s) => !!list && list.some((v) => v.includes(s))
  ck('Our Batters are our batters', has(ourBat, 'NPBATONE') && !has(ourBat, 'OPPBAT'), JSON.stringify(ourBat))
  ck('Our Bowlers are OUR bowlers', has(ourBowl, 'NPBOWLONE') && has(ourBowl, 'NPBOWLTWO'), JSON.stringify(ourBowl))
  ck('...and none of the opposition\'s', !has(ourBowl, 'OPPBOWL'), JSON.stringify(ourBowl))
  ck('Their Batters are theirs', has(theirBat, 'OPPBATONE') && !has(theirBat, 'NPBAT'), JSON.stringify(theirBat))
  ck('Their Bowlers are THEIR bowlers, none of ours', has(theirBowl, 'OPPBOWLONE') && !has(theirBowl, 'NPBOWL'), JSON.stringify(theirBowl))
  ck('our best bowling is the first figure on our side (3/22)', ourBowl && /3\/22/.test(ourBowl.join(' ')), JSON.stringify(ourBowl))
  const text = await body(page)
  ck('the post carries the bowlers under the right club (ours with ours)',
    /NPBOWLONE/.test(text) && /OPPBOWLONE/.test(text) && text.indexOf('NPBATONE') < text.indexOf('OPPBATONE'), text.slice(0, 120))
  ck('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  await ctx.close()
}

// ───────── Wrap + Leaders: Players shown ─────────
console.log('\n# Wrap + Leaders, Players shown')
{
  const { ctx, page, errors } = await openEditor('type=results&template=RR7', 'RR7')
  const sw = page.getByTestId('rr-perf-side')
  ck('the "Players shown" switch is in the editor', await reveal(page, sw))
  await press(page.getByRole('button', { name: /Pull latest round/ }))
  await page.waitForTimeout(1200)
  let text = await body(page)
  ck('default is our club: the post lists our scorers and wicket takers', /NPBATONE/.test(text) && /NPBOWLONE/.test(text) && !/OPPBATONE|OPPBOWLONE/.test(text), text.slice(0, 160))
  ck('...under the plain headings', /TOP RUN SCORERS/.test(text) && !/OPPOSITION TOP RUN SCORERS/.test(text))
  ck('...and the editor says Our top scorers', /OUR TOP SCORERS/i.test(text) && !/THEIR TOP SCORERS/i.test(text))
  ck('Our club is the pressed one', (await attr(page, 'rr-perf-us', 'aria-checked')) === 'true')

  await press(page.getByTestId('rr-perf-them'))
  await page.waitForTimeout(500)
  text = await body(page)
  ck('Opposition: the post lists the opposition\'s scorers and wicket takers', /OPPBATONE/.test(text) && /OPPBOWLONE/.test(text) && !/NPBATONE|NPBOWLONE/.test(text), text.slice(0, 160))
  ck('...under OPPOSITION headings', /OPPOSITION TOP RUN SCORERS/.test(text) && /OPPOSITION TOP WICKET TAKERS/.test(text))
  ck('...and the editor says Their top scorers, not Our', /THEIR TOP SCORERS/i.test(text) && !/OUR TOP SCORERS/i.test(text))
  ck('...with the opposition\'s names in the row inputs',
    await page.evaluate(() => Array.from(document.querySelectorAll('input')).some((i) => /OPPBATONE/.test(i.value))))
  ck('a row from an older pull (no opposition lists) draws nothing rather than breaking', !/OLDBAT|OLDBOWL/.test(text) && /3RD GRADE/.test(text), text.slice(0, 160))
  ck('the aria state follows', (await attr(page, 'rr-perf-them', 'aria-checked')) === 'true' && (await attr(page, 'rr-perf-us', 'aria-checked')) === 'false')

  // Editing while on the opposition writes to THEIR list, and ours is left alone.
  const input = page.locator('input[value="A. OPPBATONE"]').first()
  if (await input.count()) { await input.fill('A. EDITED'); await page.waitForTimeout(300) }
  await press(page.getByTestId('rr-perf-us'))
  await page.waitForTimeout(400)
  text = await body(page)
  ck('an edit made on the opposition side does not touch ours', /NPBATONE/.test(text) && !/EDITED/.test(text), text.slice(0, 160))
  await press(page.getByTestId('rr-perf-them'))
  await page.waitForTimeout(400)
  ck('...and is still there when you come back to it', /EDITED/.test(await body(page)))

  ck('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  await ctx.close()
}

{
  console.log('\n# 390px')
  const { ctx, page } = await openEditor('type=results&template=RR7', 'RR7', { width: 390, height: 900 }, true).catch(() => ({}))
  if (page) {
    // A phone opens a simplified composer; the roundup's rows and this switch are in the full editor.
    await press(page.getByRole('button', { name: 'FULL EDITOR' }))
    await page.waitForTimeout(1500)
    await reveal(page, page.getByTestId('rr-perf-side'))
    ck('the switch is reachable on a phone', await visible(page.getByTestId('rr-perf-side')))
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    ck('no horizontal overflow at 390px', over <= 1, `${over}px`)
    await ctx.close()
  } else ck('the editor opens at 390px', false)
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
