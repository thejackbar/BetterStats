// Drives the REAL Past Lineups screen in Chromium with the API stubbed at the network layer:
//   * it is a BetterSelect side-menu item and opens at /admin/betterselect/past-lineups
//   * the first team's first page is asked for with the exact query (team + limit, no offset)
//   * cards run newest first under year headings; the XI is in batting order with C and WK
//   * every card says who came in and who dropped out, in words; the first game on record says so
//   * scrolling to the bottom pulls the next page in by offset with no click; the last page ends cleanly
//   * picking another team asks for that team and puts it in the address; a reload remembers it
//   * `?fixture=` resolves a team (fixture_id on the wire) and opens it
//   * tapping a player follows them: a count, the cards they are not in say so, and it clears
//   * a club with nothing to show says so; 390px has no sideways overflow
//
//   npx vite preview --port 5199 &    node verify_past_lineups_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const OUT = process.env.SHOT_DIR || '/tmp'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }

const ME = { id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'o1', club_slug: 'gisborne', capabilities: ['*'], entitlements: { modules: ['select'], core_live: true, status: 'active' } }
const TEAMS = [
  { key: 'sq-1', name: '1st XI', squad_name: '1st XI', rank: 1, games: 20, last_played: '2026-10-17' },
  { key: 'sq-2:alpha', name: '2nd XI', squad_name: 'MACs', rank: 2, games: 2, last_played: '2026-10-10' },
]
// Twenty 1st XI games, one every three weeks back from 17 Oct 2026, so the list crosses into 2025.
const NAMES = ['Smith, Alex', 'Jones, Ben', 'Brown, Cal', 'Lee, Dan', 'Wong, Eli', 'Ng, Fin', 'Ray, Gus', 'Cho, Hal', 'Dow, Ian', 'Fox, Jay', 'Kay, Kit', 'Lam, Leo', 'Moe, Max', 'Nix, Ned']
const pl = (i, order, extra = {}) => ({ player_id: `pl${i}`, display_name: NAMES[i], batting_order: order, is_captain: false, is_wicket_keeper: false, ...extra })
const dayStr = (back) => { const d = new Date(Date.UTC(2026, 9, 17)); d.setUTCDate(d.getUTCDate() - 21 * back); return d.toISOString().slice(0, 10) }
const xiFor = (g) => {                      // game g (0 = newest): a rolling 11 of the 14, so each week changes two names
  const ids = []
  for (let k = 0; k < 11; k++) ids.push((g + k) % 14)
  return ids
}
const GAMES = Array.from({ length: 20 }, (_, g) => {
  const ids = xiFor(g)
  return {
    fixture_id: `fx${g}`, played_on: dayStr(g), end_on: null, start_time: '13:00', round: `Round ${20 - g}`, label: `R${20 - g}`,
    opponent_name: `Rovers ${g}`, home_away: g % 2 ? 'AWAY' : 'HOME', venue: g === 0 ? 'Home Oval' : null, locked: g < 2,
    players: ids.map((id, i) => pl(id, i + 1, { is_captain: i === 0, is_wicket_keeper: i === 1 })),
    _ids: ids,
  }
})
const withBaseline = (g) => {
  const older = GAMES[g + 1]
  const e = { ...GAMES[g] }
  delete e._ids
  if (!older) return { ...e, vs_previous: null }
  const now = new Set(GAMES[g]._ids), before = new Set(older._ids)
  return {
    ...e,
    vs_previous: {
      fixture_id: older.fixture_id, played_on: older.played_on,
      added: [...now].filter((i) => !before.has(i)).map((i) => pl(i, null)),
      removed: [...before].filter((i) => !now.has(i)).map((i) => pl(i, null)),
    },
  }
}

const run = async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {})
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const asked = []
  let emptyClub = false
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route('**/api/club-admin/settings', (r) => json(r, { name: 'Gisborne CC', short_name: 'Gisborne', player_name_format: 'first_last' }))
  await page.route(/\/api\/selection\/past-lineups\/teams(\?.*)?$/, (r) => { asked.push({ teams: true }); return json(r, { teams: emptyClub ? [] : TEAMS }) })
  await page.route(/\/api\/selection\/past-lineups(\?.*)?$/, (r) => {
    const p = Object.fromEntries(new URL(r.request().url()).searchParams)
    asked.push(p)
    const key = p.team || (p.fixture_id === 'fx-from-builder' ? 'sq-2:alpha' : null)
    if (key === 'sq-2:alpha') {
      const two = [0, 1].map((g) => ({ ...withBaseline(g), fixture_id: `a${g}`, players: GAMES[g].players.slice(0, 3) }))
      return json(r, { team: TEAMS[1], entries: p.fixture_id ? two.slice(0, 1) : two, total: 2, has_more: false, next_offset: 2 })
    }
    if (key !== 'sq-1') return json(r, { team: null, entries: [], total: 0, has_more: false, next_offset: 0 })
    const off = Number(p.offset || 0), lim = Number(p.limit || 8)
    const slice = GAMES.slice(off, off + lim).map((_, i) => withBaseline(off + i))
    return json(r, { team: TEAMS[0], entries: slice, total: 20, has_more: off + lim < 20, next_offset: off + slice.length })
  })

  const cards = () => page.locator('[data-past-card]')
  const open = async (url) => { await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' }); }

  await safe('first page', async () => {
    console.log('\n── Opening it ──')
    await open('/admin/betterselect/past-lineups')
    await cards().first().waitFor({ timeout: 20000 })
    const link = page.locator('a[href="/admin/betterselect/past-lineups"]').first()
    await link.waitFor({ state: 'attached' })
    check('Past Lineups is a side-menu item', /Past Lineups/.test(await link.innerText()))
    check('the team list was asked for', asked.some((a) => a.teams))
    const first = asked.find((a) => a.team)
    check('the top team opens first, asked for with team and limit only', first && first.team === 'sq-1' && first.limit === '8' && !('offset' in first), JSON.stringify(asked))
    check('the first page holds 8 cards', (await cards().count()) === 8, String(await cards().count()))
    const ids = await cards().evaluateAll((els) => els.map((e) => e.getAttribute('data-past-card')))
    check('newest game first, then back in time', ids.join() === 'fx0,fx1,fx2,fx3,fx4,fx5,fx6,fx7', ids.join())
    check('the active team chip says which team and how many games', /1st XI · 20/.test(await page.locator('[data-past-teams] button').first().innerText()))
    check('the summary says how many are on record', /20 games on record/.test(await page.locator('[data-past-summary]').innerText()), await page.locator('[data-past-summary]').innerText())
  })

  await safe('card', async () => {
    console.log('\n── A card ──')
    const c = cards().first()
    const txt = await c.innerText()
    check('the card has its date, round, opponent and ground', /Oct/.test(txt) && /\b17\b/.test(txt) && /Round 20/.test(txt) && /Rovers 0/.test(txt) && /Home Oval/.test(txt), txt.slice(0, 200))
    check('an away game reads "at"', /at Rovers 1/.test(await cards().nth(1).innerText()))
    check('a locked side says so', /Locked/.test(txt) && !/Locked/.test(await cards().nth(5).innerText()))
    const names = await c.locator('[data-past-xi] li').allInnerTexts()
    check('the XI has 11 players in batting order (Alex Smith first, Ben Jones second)', names.length === 11 && /Alex Smith/.test(names[0]) && /Ben Jones/.test(names[1]), names.slice(0, 2).join(' | '))
    check('captain and keeper are marked in words', /\bC\b/.test(names[0]) && /\bWK\b/.test(names[1]), `${names[0]} | ${names[1]}`)
    check('names go through the club\'s name format (first last)', /Alex Smith/.test(txt) && !/Smith, Alex/.test(txt))
    const inTxt = await c.locator('[data-past-in]').innerText()
    const outTxt = await c.locator('[data-past-out]').innerText()
    check('who came in is labelled "In"', /^In\b/.test(inTxt), inTxt)
    // game 0 = ids 0..10, game 1 = ids 1..11 -> 0 came in, 11 went out
    check('game 0 vs game 1: Alex Smith in', /Alex Smith/.test(inTxt), inTxt)
    check('game 0 vs game 1: Leo Lam out', /^Out\b/.test(outTxt) && /Leo Lam/.test(outTxt), outTxt)
    check('...and it names the game it compares with (CSS uppercases the label)', /Changes since/i.test(await c.locator('[data-past-changes]').innerText()))
    await page.screenshot({ path: `${OUT}/past-lineups-1280.png` })
  })

  await safe('years', async () => {
    console.log('\n── Years ──')
    check('a year heading sits above the first card', (await page.locator('[data-past-year]').first().innerText()) === '2026')
  })

  await safe('scroll back', async () => {
    console.log('\n── Scrolling back ──')
    asked.length = 0
    await page.locator('[data-past-end], [data-past-more]').first().scrollIntoViewIfNeeded()
    await page.mouse.wheel(0, 20000)
    await page.waitForFunction(() => document.querySelectorAll('[data-past-card]').length >= 16, null, { timeout: 8000 })
    const more = asked.filter((a) => a.team === 'sq-1')
    check('scrolling asked for the next page by offset, with no click', more.some((a) => a.offset === '8' && a.limit === '8'), JSON.stringify(asked))
    check('...and now 16 cards are on the page', (await cards().count()) >= 16)
    for (let i = 0; i < 6 && (await page.locator('[data-past-end]').count()) === 0; i++) {
      await page.mouse.wheel(0, 30000); await page.waitForTimeout(400)
    }
    check('the last page ends with a clear message', (await page.locator('[data-past-end]').count()) === 1)
    check('...all 20 cards are there and the button is gone', (await cards().count()) === 20 && (await page.locator('[data-past-more]').count()) === 0, String(await cards().count()))
    check('no card repeats', new Set(await cards().evaluateAll((els) => els.map((e) => e.getAttribute('data-past-card')))).size === 20)
    check('the list crosses into 2025 under its own heading', (await page.locator('[data-past-year]').allInnerTexts()).join() === '2026,2025', (await page.locator('[data-past-year]').allInnerTexts()).join())
    const last = cards().last()
    check('the first game on record says it has nothing before it', /First side on record/.test(await last.innerText()))
    check('(control) a card with a baseline does not say that', !/First side on record/.test(await cards().first().innerText()))
  })

  await safe('follow', async () => {
    console.log('\n── Following a player ──')
    await page.evaluate(() => window.scrollTo(0, 0))
    // Alex Smith (pl0) is in games 0..0 and 3? ids: game g holds (g..g+10)%14 -> pl0 is in g where 0 in range.
    const inGames = GAMES.filter((g) => g._ids.includes(0)).length
    await cards().first().locator('[data-past-player="pl0"]').first().click()
    await page.locator('[data-past-following]').waitFor()
    const banner = await page.locator('[data-past-following]').innerText()
    check('a banner names the player and counts their games', /Alex Smith/.test(banner) && new RegExp(`in ${inGames} of the 20 games shown`).test(banner), banner)
    const absent = await page.locator('[data-past-absent="1"]').count()
    check('cards without them are dimmed and say so', absent === 20 - inGames && (await page.locator('[data-past-not-in]').count()) === absent, `${absent} vs ${20 - inGames}`)
    check('(control) cards with them are not', (await cards().count()) - absent === inGames)
    check('the name is highlighted wherever it appears', (await page.locator('[data-past-player="pl0"][aria-pressed="true"]').count()) > 1)
    await page.locator('[data-past-unfollow]').click()
    check('Stop following clears it', (await page.locator('[data-past-following]').count()) === 0 && (await page.locator('[data-past-absent="1"]').count()) === 0)
  })

  await safe('switch team', async () => {
    console.log('\n── Another team ──')
    asked.length = 0
    await page.locator('[data-past-teams] button', { hasText: '2nd XI' }).click()
    await page.waitForFunction(() => document.querySelectorAll('[data-past-card]').length === 2, null, { timeout: 8000 })
    check('picking a team asks for that team', asked.some((a) => a.team === 'sq-2:alpha'), JSON.stringify(asked))
    check('...the old team\'s games are gone', (await page.locator('[data-past-card="fx0"]').count()) === 0)
    check('the team is in the address', /[?&]team=sq-2%3Aalpha|[?&]team=sq-2:alpha/.test(page.url()), page.url())
    await open('/admin/betterselect/past-lineups')
    await cards().first().waitFor()
    check('opening the screen again remembers the last team', (await page.locator('[data-past-card="a0"]').count()) === 1)
  })

  await safe('from the builder', async () => {
    console.log('\n── From the Selection board ──')
    await ctx.addInitScript(() => { try { localStorage.removeItem('bs_pref:select.pastLineups.team') } catch {} })
    await page.evaluate(() => { try { localStorage.removeItem('bs_pref:select.pastLineups.team') } catch {} })
    asked.length = 0
    await open('/admin/betterselect/past-lineups?fixture=fx-from-builder')
    await page.locator('[data-past-card="a0"]').waitFor({ timeout: 10000 })
    check('a fixture is resolved with fixture_id on the wire', asked.some((a) => a.fixture_id === 'fx-from-builder'), JSON.stringify(asked))
    check('...then that team\'s feed is asked for by key', asked.some((a) => a.team === 'sq-2:alpha' && a.limit === '8'), JSON.stringify(asked))
    check('...and the right chip is lit', /2nd XI/.test(await page.locator('[data-past-teams] button[class*="text-pb-accent"]').first().innerText()))
  })

  await safe('phone', async () => {
    console.log('\n── Phone ──')
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 })
    const p2 = await phone.newPage()
    const j = (r, body) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    await p2.route('**/api/**', (r) => j(r, {}))
    await p2.route('**/api/auth/me', (r) => j(r, ME))
    await p2.route('**/api/club-admin/settings', (r) => j(r, { name: 'Gisborne CC', player_name_format: 'first_last' }))
    await p2.route(/\/api\/selection\/past-lineups\/teams/, (r) => j(r, { teams: TEAMS }))
    await p2.route(/\/api\/selection\/past-lineups(\?.*)?$/, (r) => {
      const q = Object.fromEntries(new URL(r.request().url()).searchParams)
      const off = Number(q.offset || 0)
      return j(r, { team: TEAMS[0], entries: GAMES.slice(off, off + 8).map((_, i) => withBaseline(off + i)), total: 20, has_more: off + 8 < 20, next_offset: off + 8 })
    })
    await p2.goto(`${BASE}/admin/betterselect/past-lineups?team=sq-1`, { waitUntil: 'domcontentloaded' })
    await p2.locator('[data-past-card]').first().waitFor({ timeout: 20000 })
    const w = await p2.evaluate(() => ({ doc: document.documentElement.scrollWidth, screen: window.screen.width, inner: window.innerWidth }))
    check('no sideways overflow at 390px', w.doc <= Math.max(w.screen, w.inner) + 1, JSON.stringify(w))
    check('the XI is one column on a phone', await p2.locator('[data-past-xi]').first().evaluate((el) => getComputedStyle(el).columnCount === 'auto' || getComputedStyle(el).columnCount === '1'))
    const tap = await p2.locator('[data-past-player]').first().boundingBox()
    check('a player name is a usable tap target (height 20px or more)', tap && tap.height >= 20, JSON.stringify(tap))
    await p2.screenshot({ path: `${OUT}/past-lineups-390.png` })
    await phone.close()
  })

  await safe('empty', async () => {
    console.log('\n── Nothing to show ──')
    emptyClub = true
    await page.evaluate(() => { try { localStorage.clear() } catch {} })
    await open('/admin/betterselect/past-lineups')
    await page.locator('[data-past-none]').waitFor({ timeout: 10000 })
    check('a club with no past sides is told why', /No past sides yet/.test(await page.locator('[data-past-none]').innerText()))
    check('...and no team chips or cards are drawn', (await page.locator('[data-past-teams]').count()) === 0 && (await cards().count()) === 0)
  })

  check('no uncaught page errors', errors.length === 0, errors.join(' | ').slice(0, 300))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
