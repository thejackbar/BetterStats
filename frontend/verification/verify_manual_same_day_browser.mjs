/**
 * The hand-entry form says so when the club already holds a game on the date being typed.
 *
 * Run:
 *   npx vite --port 5199 &
 *   node verification/verify_manual_same_day_browser.mjs
 *
 * Reported by Hamilton Veterans (Oct 2026): totals read double and players carried games
 * with no detail. A hand-entered game counts on top of whatever the club already holds, and
 * the only place that asked "is there already a game on this date?" was the photo upload
 * page. The Manual Games form, where the games were typed, never asked, so a match PlayHQ
 * also held (typed in to correct it) was counted twice without a word.
 *
 * Checked against the real form with the API stubbed at the network layer:
 *   - choosing a date asks the server, with that date and the opposition on the wire;
 *   - a game already on that date shows a box naming it, and whether PlayHQ or a person made it;
 *   - the save dialog repeats it, and the save still goes (two real games a day is ordinary);
 *   - an empty answer shows no box, a failed check says nothing, and no date asks nothing;
 *   - 390px wide has no sideways scroll.
 *
 * Every read is guarded so a control run reports rather than crashing.
 */
import { chromium } from 'playwright'
import { existsSync } from 'node:fs'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const GAME = {
  id: 'g1', season_id: 's1', grade_id: 'gr1', played_at: '2025-02-20',
  home_team: 'Hamilton', away_team: 'Portland Over 60s', opposition: 'Portland Over 60s', result: 'Won',
  batting_innings: [{ player_id: 'p1', innings_number: 1, batting_position: 1, runs: 31, not_out: false, dismissal_type: 'b X' }],
  bowling_spells: [], fielding_stats: [], innings: [],
}

const MATCHES = [
  { id: 'syn1', played_at: '2025-02-20', opponent: 'Portland Over 60s', grade: 'Over 60s', source: 'api', likely: true },
  { id: 'man1', played_at: '2025-02-20', opponent: 'Colac', grade: null, source: 'manual', likely: false },
]

// The New game form's own date box (the Details editor has a different one).
const dateBox = (page) => page.getByTestId('game-form-card').locator('input[type=date]').first()

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ matches = MATCHES, fails = false, width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = [], asked = [], posts = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route(/\/api\//, async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = route.request().method()
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path.startsWith('/auth/me')) {
      return json({ id: 'u1', username: 'admin', display_name: 'Admin', role: 'club_admin',
                    club_id: 'c1', club_slug: 'test-cc',
                    entitlements: { modules: ['stats', 'fees'], status: 'active' } })
    }
    if (/scorecard\/check-duplicate$/.test(path)) {
      asked.push(Object.fromEntries(url.searchParams))
      return fails ? json({ detail: 'boom' }, 500) : json({ matches })
    }
    if (/manual-entries\/games\/check$/.test(path)) return json({ warnings: [] })
    if (/manual-entries\/games\/g1$/.test(path)) {
      if (method === 'PATCH') { posts.push(JSON.parse(route.request().postData() || '{}')); return json({ id: 'g1' }) }
      return json(GAME)
    }
    if (/manual-entries\/games$/.test(path)) {
      return json([{ id: 'g1', played_at: '2025-02-20', opposition: 'Portland Over 60s', home_team: 'Hamilton', away_team: 'Portland Over 60s', result: 'Won' }])
    }
    if (path === '/club-admin/players') return json([{ id: 'p1', name: 'Costello, John' }])
    if (path === '/club-admin/seasons') return json([{ id: 's1', name: '2024/25', year: 2024 }])
    if (/manual-entries\/grades$/.test(path)) return json([{ id: 'gr1', season_id: 's1', name: 'Over 60s' }])
    if (/known-values/.test(path)) return json({ oppositions: [], venues: [] })
    return json([])
  })
  await page.goto(`${BASE}/admin/manual-entries#game`, { waitUntil: 'domcontentloaded' })
  await dateBox(page).waitFor({ timeout: 15000 }).catch(() => {})
  return { page, ctx, errors, asked, posts }
}

// ── a date with games on it shows them ──────────────────────────────────────
{
  const { page, ctx, errors, asked, posts } = await open()
  ck('no date typed, nothing asked', asked.length === 0, JSON.stringify(asked))
  await dateBox(page).fill('2025-02-20')
  await page.waitForTimeout(900)
  ck('choosing a date asks the server', asked.length >= 1, String(asked.length))
  ck('with that date on the wire', asked.at(-1)?.played_at === '2025-02-20', JSON.stringify(asked.at(-1)))
  ck('and no game of its own to leave out', !asked.at(-1)?.exclude_id, JSON.stringify(asked.at(-1)))
  const box = page.getByTestId('game-same-day')
  ck('a box appears on the form', (await box.count()) === 1, String(await box.count()))
  const text = (await box.count()) ? await box.innerText() : ''
  ck('it says how many games the club already has that day', /2 games on 2025-02-20\./.test(text), text.slice(0, 160))
  ck('it names the PlayHQ one as PlayHQ', /from PlayHQ/.test(text), text)
  ck('and the other as hand entered', /hand entered/.test(text), text)
  ck('it flags the same opposition', /same opposition/.test(text), text)
  ck('and links to each game', (await box.locator('a').count()) === 2, String(await box.locator('a').count()))
  ck('it says the same match twice is counted twice', /counted twice in every total/.test(text), text)

  // Editing a saved game: it must not flag itself, and saving still goes.
  await page.getByRole('button', { name: 'Edit', exact: true }).first().click({ timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(900)
  ck('editing a saved game leaves that game out of the ask', asked.at(-1)?.exclude_id === 'g1', JSON.stringify(asked.at(-1)))
  ck('and sends the opposition it carries', asked.at(-1)?.opponent === 'Portland Over 60s', JSON.stringify(asked.at(-1)))
  await page.getByRole('button', { name: 'Update manual game' }).click().catch(() => {})
  await page.waitForTimeout(300)
  const dialog = await page.locator('.fixed.inset-0').innerText().catch(() => '')
  ck('the save dialog repeats the warning', /already has 2 games on 2025-02-20/.test(dialog), dialog.slice(0, 300))
  ck('and says to save only if it is a different game', /different game/.test(dialog), dialog.slice(0, 300))
  await page.locator('.fixed.inset-0').getByRole('button', { name: 'Update', exact: true }).click().catch(() => {})
  await page.waitForTimeout(500)
  ck('and the game still saves, because two real games in a day is ordinary', posts.length === 1, String(posts.length))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── one game, singular ──────────────────────────────────────────────────────
{
  const { page, ctx } = await open({ matches: [MATCHES[0]] })
  await dateBox(page).fill('2025-02-20')
  await page.waitForTimeout(900)
  const text = await page.getByTestId('game-same-day').innerText().catch(() => '')
  ck('one game reads "a game", not "1 games"', /already has a game on 2025-02-20/.test(text), text.slice(0, 120))
  await ctx.close()
}

// ── a clear day shows nothing ───────────────────────────────────────────────
{
  const { page, ctx, asked } = await open({ matches: [] })
  await dateBox(page).fill('2025-03-01')
  await page.waitForTimeout(900)
  ck('the server was asked', asked.length >= 1, String(asked.length))
  ck('a day with no other game shows no box', (await page.getByTestId('game-same-day').count()) === 0)
  await ctx.close()
}

// ── a failing check is silent ───────────────────────────────────────────────
{
  const { page, ctx, errors } = await open({ fails: true })
  await dateBox(page).fill('2025-02-20')
  await page.waitForTimeout(900)
  ck('a check that fails draws nothing', (await page.getByTestId('game-same-day').count()) === 0)
  ck('and breaks nothing', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── a phone ─────────────────────────────────────────────────────────────────
{
  const { page, ctx } = await open({ width: 390 })
  await dateBox(page).fill('2025-02-20')
  await page.waitForTimeout(900)
  ck('the box is there at 390px', (await page.getByTestId('game-same-day').count()) === 1)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('and the page does not scroll sideways', over <= 0, `overflow ${over}px`)
  await page.screenshot({ path: process.env.SHOT || '/tmp/same-day-390.png', fullPage: false })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
