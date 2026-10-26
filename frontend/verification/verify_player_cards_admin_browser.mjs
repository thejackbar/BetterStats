// The Player Cards settings screen (/admin/player-cards) against the real page with the API stubbed at the
// network layer. Asserts the exact request each control sends (a PATCH sends only what changed), that the
// screen then shows what the server answered, who is in and out of the pool and why, hiding and showing a
// player, the link players use, the special cards button, 390px, and no page errors.
//
//   APP_URL=http://localhost:4173 node verification/verify_player_cards_admin_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}

const state = {
  settings: { enabled: true, include_juniors: false, weekly_packs: 1, timezone: null, effective_timezone: 'Australia/Perth' },
  players: [
    { id: 'a1', display_name: 'Adams, Brian', hidden: false, in_pool: true, matches: 260, rarity: 81, tier: 'epic', excluded: null },
    { id: 'b2', display_name: 'Baker, Chris', hidden: false, in_pool: true, matches: 12, rarity: 22, tier: 'common', excluded: null },
    { id: 'c3', display_name: 'Young, Kid', hidden: false, in_pool: false, matches: 8, rarity: null, tier: null, excluded: 'junior' },
    { id: 'd4', display_name: 'Hidden, Pat', hidden: false, in_pool: false, matches: 40, rarity: null, tier: null, excluded: 'private' },
    { id: 'e5', display_name: 'New, Nick', hidden: false, in_pool: false, matches: 0, rarity: 1, tier: 'common', excluded: null },
  ],
}
const payload = () => ({
  settings: state.settings,
  timezones: [{ id: 'Australia/Perth', label: 'Western Australia' }, { id: 'Australia/Sydney', label: 'New South Wales, ACT' }],
  max_weekly_packs: 10,
  link: { path: '/avail/tok123' },
  pool: { size: state.players.filter((p) => p.in_pool).length, players: state.players.length },
  players: state.players,
})

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const errors = [], calls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const req = route.request(), url = req.url(), method = req.method()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(url)) return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', entitlements: { modules: [], status: 'active' } })
    if (/\/player-cards\//.test(url)) {
      const body = req.postData() ? JSON.parse(req.postData()) : null
      calls.push({ method, path: url.split('/api')[1], body })
      if (method === 'PATCH') Object.assign(state.settings, body)
      const hide = url.match(/\/players\/([^/]+)\/hidden$/)
      if (hide) { const p = state.players.find((x) => x.id === hide[1]); p.hidden = body.hidden; p.in_pool = !body.hidden && p.matches > 0 }
      if (/refresh-specials/.test(url)) return json({ made: { century: 2, fifty: 0 } })
      return json(payload())
    }
    return json({})
  })
  await page.goto(`${BASE}/admin/player-cards`)
  await page.waitForSelector('[data-player-cards-admin] [data-card-player]', { timeout: 20000 })

  const last = () => calls[calls.length - 1]
  check('the screen opens with the pool count', /Players in the card pool \(2 of 5\)/i.test(await page.locator('[data-player-cards-admin]').innerText()))
  check('cards are on by default', (await page.getByRole('switch', { name: 'Player Cards are on' }).getAttribute('aria-checked')) === 'true')
  check('juniors are off by default', (await page.getByRole('switch', { name: 'Include junior players' }).getAttribute('aria-checked')) === 'false')
  check('the player page link is shown', /\/avail\/tok123/.test(await page.locator('[data-player-page-link]').innerText()))
  const reasons = await page.locator('[data-card-player]').evaluateAll((els) => Object.fromEntries(els.map((e) => [e.getAttribute('data-card-player'), e.innerText])))
  check('a junior is shown as out because juniors are off, and a hidden-from-public player as out for privacy',
    /Junior player, and juniors are switched off/.test(reasons.c3) && /Hidden from the public site/.test(reasons.d4), JSON.stringify(reasons))
  check('a player with no matches says they cannot be pulled', /No matches yet/.test(reasons.e5))
  check('a player the club cannot hide for those reasons has no Hide button', !/Hide|Show/.test(reasons.c3) && !/Hide|Show/.test(reasons.d4) && /Hide/.test(reasons.a1))

  // each control sends only what it changed
  await page.getByRole('switch', { name: 'Include junior players' }).click()
  await page.waitForFunction(() => document.querySelector('[role="switch"][aria-label="Include junior players"]').getAttribute('aria-checked') === 'true')
  check('Include juniors sends only include_juniors', JSON.stringify(last()) === JSON.stringify({ method: 'PATCH', path: '/player-cards/settings', body: { include_juniors: true } }), JSON.stringify(last()))
  await page.getByRole('switch', { name: 'Include junior players' }).click()
  await page.getByLabel('Weekly packs per player').selectOption('3')
  await page.waitForFunction(() => document.querySelector('select[aria-label="Weekly packs per player"]').value === '3')
  check('the weekly count sends only weekly_packs', JSON.stringify(last().body) === '{"weekly_packs":3}', JSON.stringify(last()))
  await page.getByLabel('Timezone').selectOption('Australia/Sydney')
  await page.waitForFunction(() => document.querySelector('select[aria-label="Timezone"]').value === 'Australia/Sydney')
  check('the timezone sends only timezone', JSON.stringify(last().body) === '{"timezone":"Australia/Sydney"}', JSON.stringify(last()))
  await page.getByLabel('Timezone').selectOption('')
  await page.waitForFunction(() => document.querySelector('select[aria-label="Timezone"]').value === '')
  check('choosing the default clears the timezone (an explicit null, not an absent key)', JSON.stringify(last().body) === '{"timezone":null}', JSON.stringify(last()))
  await page.getByRole('switch', { name: 'Player Cards are on' }).click()
  await page.waitForFunction(() => document.querySelector('[role="switch"][aria-label="Player Cards are on"]').getAttribute('aria-checked') === 'false')
  check('switching cards off sends enabled false', JSON.stringify(last().body) === '{"enabled":false}', JSON.stringify(last()))

  // hide and show a player
  await page.locator('[data-card-player="a1"] button', { hasText: 'Hide' }).click()
  await page.waitForFunction(() => /Hidden by the club/.test(document.querySelector('[data-card-player="a1"]').innerText))
  check('Hide sends the player and hidden true', JSON.stringify(last()) === JSON.stringify({ method: 'POST', path: '/player-cards/players/a1/hidden', body: { hidden: true } }), JSON.stringify(last()))
  check('the pool count follows (1 of 5)', /\(1 of 5\)/i.test(await page.locator('[data-player-cards-admin]').innerText()))
  await page.locator('[data-card-player="a1"] button', { hasText: 'Show' }).click()
  await page.waitForFunction(() => /260 matches/.test(document.querySelector('[data-card-player="a1"]').innerText))
  check('Show brings them back', last().body.hidden === false)
  await page.getByPlaceholder('Find a player').fill('baker')
  check('the search narrows the list', (await page.locator('[data-card-player]').count()) === 1)
  await page.getByPlaceholder('Find a player').fill('')

  await page.getByRole('button', { name: 'Look for new ones' }).click()
  await page.waitForFunction(() => /Look for new ones/.test(document.body.innerText))
  check('the special cards button posts to refresh', calls.some((c) => c.method === 'POST' && c.path === '/player-cards/refresh-specials'))

  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(300)
  check('no horizontal scroll at 390px', (await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 0)
  check('no page errors', errors.length === 0, errors.join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
