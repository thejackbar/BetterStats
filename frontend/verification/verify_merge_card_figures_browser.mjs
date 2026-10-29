// Merge Duplicates cards, against the REAL MergeTools component with the API stubbed at the network layer.
//
// Reported off Payneham: a scorebook-only pair "Zia, MYB" / "Zia, M" showed 0 on every figure although
// one of them holds 20 matches. The server now sends games_held, first_game and last_game. Asserted:
//   * the Games tile shows the number the server sent, on both cards;
//   * the span line reads "2019 to 2020" for a player who played across two years and the single year
//     for one who did not, and is absent for a record with no games (the zero is a true one);
//   * a pair with no span data (an older response) still renders;
//   * no horizontal overflow at 390px, and a screenshot of the card.
//
//   node verify_merge_card_figures_browser.mjs   (BASE via APP_URL, default :5178)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5178'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const card = (id, name, extra = {}) => ({
  id, name, playhq_id: null, claimed: false, seasons_count: 0, total_runs: 0, total_wickets: 0, total_matches: 0,
  game_level_innings: 0, games_held: 0, first_game: null, last_game: null, ...extra,
})
const CANDIDATES = [
  { kind: 'name_variant', confidence: 0.8, reason: 'one record has only an initial', normalised_name: null, redacted: false,
    player_a: card('p1', 'Zia, MYB', { seasons_count: 2, games_held: 20, total_runs: 55, total_wickets: 5, game_level_innings: 19,
      first_game: '2019-11-03', last_game: '2020-11-07' }),
    player_b: card('p2', 'Zia, M') },
  { kind: 'name_variant', confidence: 0.8, reason: 'one record has only an initial', normalised_name: null, redacted: false,
    player_a: card('p3', 'Ward, J', { seasons_count: 1, games_held: 6, total_runs: 90, first_game: '2022-10-09', last_game: '2023-02-12' }),
    player_b: card('p4', 'Ward, Jamie', { playhq_id: 'ph4' }) },
]

const routes = (page) => page.route('**/api/**', async (route) => {
  const url = route.request().url()
  const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  if (url.includes('/auth/me')) {
    return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      club_id: 'org1', entitlements: { modules: ['admin'], status: 'active' } })
  }
  if (/\/admin\/merge-candidates/.test(url)) return json(CANDIDATES)
  if (/\/admin\/merge-history/.test(url)) return json([])
  if (/\/admin\/players/.test(url)) return json([])
  if (/\/notifications\/(count|summary)/.test(url)) return json({ unseen_count: 0, items: [] })
  return json({})
})

async function open(browser, width) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await routes(page)
  await page.goto(BASE + '/admin/merge', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('text=Merge Duplicates', { timeout: 15000 })
  await page.waitForSelector('text=Zia, MYB', { timeout: 15000 })
  return { page, errors }
}

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  for (const width of [1200, 390]) {
    const { page, errors } = await open(browser, width)
    const text = await page.locator('body').innerText()
    // CSS uppercase makes innerText uppercase, so the tile labels are read in that casing.
    check(`[${width}] the Games tile label is on the card`, /GAMES/.test(text), text.slice(0, 200))
    const mybCard = page.locator('button', { hasText: 'Zia, MYB' }).first()
    const mybText = await mybCard.innerText()
    check(`[${width}] MYB's card shows 20 games and 55 runs`, /20\s*\n?\s*GAMES/.test(mybText) && /55\s*\n?\s*RUNS/.test(mybText), JSON.stringify(mybText))
    check(`[${width}] MYB's span reads "2019 to 2020"`, /2019 to 2020/.test(mybText), JSON.stringify(mybText))
    const emptyText = await page.locator('button', { hasText: 'Zia, M' }).filter({ hasNotText: 'MYB' }).first().innerText()
    check(`[${width}] the empty record reads 0 games and shows no span`, /0\s*\n?\s*GAMES/.test(emptyText) && !/\d{4}( to \d{4})?\s*$/.test(emptyText.trim()), JSON.stringify(emptyText))
    const wardText = await page.locator('button', { hasText: 'Ward, J' }).filter({ hasNotText: 'Jamie' }).first().innerText()
    check(`[${width}] a span over two calendar years reads "2022 to 2023"`, /2022 to 2023/.test(wardText), JSON.stringify(wardText))
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    check(`[${width}] no horizontal overflow`, overflow <= 0, `overflow=${overflow}`)
    check(`[${width}] no page errors`, errors.length === 0, errors.join(' | '))
    if (width === 390) await page.screenshot({ path: process.env.SHOT || '/tmp/merge_card_390.png', fullPage: false })
  }
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run()
