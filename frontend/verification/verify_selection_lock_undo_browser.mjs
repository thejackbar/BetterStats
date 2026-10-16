// Drives the REAL Selection board and overview in Chromium with the API stubbed
// at the network layer, for the Gisborne round:
//   * Undo steps back through board changes (button and Ctrl+Z), never past the start
//   * Confirm sends lock:true; a locked side shows a banner and an Unlock button,
//     takes no picks, and a named, unlocked side offers "Lock team" (POST /lock)
//   * Unlock sends POST /unlock and the board is editable again
//   * History lists who did what; "Load this side onto the board" puts that XI on
//     the board as unconfirmed changes (nothing is written)
//   * Registered filter (only when the club records it), "Played this season",
//     and first-name / surname ordering of the pool
//   * the overview asks for juniors to be hidden, "Show juniors" drops that, and a
//     locked side reads Locked
//   * 390px: no sideways overflow on the locked board
//
//   npx vite preview --port 5199 &    node verify_selection_lock_undo_browser.mjs
import { chromium } from 'playwright'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.APP_URL || 'http://localhost:5199'
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures/selection_same_day.json'), 'utf8'))
const FID = FIX.fixture_id

let PASS = 0, FAIL = 0
const ok = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}

const ME = {
  id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'gisborne', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' },
}

// Four players with distinct names, seasons and registration answers.
const base = FIX.payload.pool[0]
const mk = (id, name, extra) => ({
  ...base, id, display_name: name, also_in: [], clash: [], clash_detail: [], clash_blocks: false,
  gender_ok: true, tier: 1, recent_ok: true, autofill_eligible: true, availability: 'AVAILABLE',
  is_dormant: false, is_inactive: false, is_current: true, rule_state: 'ok', squads: [], ...extra,
})
const POOL = [
  mk('p-zed', 'Zed Adams', { last_played: '2027-02-01', registered: true }),
  mk('p-anna', 'Anna Brown', { last_played: '2025-01-10', registered: false }),
  mk('p-cara', 'Cara Cole', { last_played: '2027-03-01', registered: null }),
  mk('p-dan', 'Dan Dunn', { last_played: '2027-03-05', registered: true }),
]

// A step that cannot run (a control or broken build lacks the control it needs)
// is reported as a failed check and the next step still runs.
const safe = async (label, fn) => {
  try { await fn() } catch (e) { ok(`${label}: step could not run`, false, String(e.message).split('\n')[0]) }
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(5000)   // a missing control fails its check quickly rather than stalling the run
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('dialog', (d) => d.accept())

  const server = { locked: false, lineup: [], events: [], overviewUrls: [], overviewLocked: false }
  const wire = { puts: [], locks: 0, unlocks: 0 }
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route(/\/api\/club-admin\/settings$/, (r) => json(r, { player_name_format: 'first_last' }))
  // The club's "played within" window is a Settings choice now (read from the config the screens share).
  await page.route(/\/api\/availability\/config/, (r) => json(r, { allow_maybe: true, half_colours: null, played_years: { selection: server.playedYears ?? 3, availability: 0 }, team_defaults: [], squads: [] }))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route(/\/api\/selection\/overview(\?.*)?$/, (r) => {
    server.overviewUrls.push(r.request().url())
    const lineup = Array.from({ length: 11 }, (_, i) => ({ player_id: `x${i}`, display_name: `Player ${i}`, batting_order: i + 1, is_captain: i === 0, is_wicket_keeper: i === 1, skill_positions: ['BAT', 'BWL', 'WKT'], availability: 'AVAILABLE' }))
    return json(r, { default_team_size: 11, fixtures: [{
      id: FID, label: 'Colts', opponent_name: 'Opp', played_on: '2027-04-20', team_name: 'Colts', team_sequence: 4, team_size: 11,
      lineup, locked: server.overviewLocked, has_draft: false,
    }] })
  })
  await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { source_fixture_id: null, player_ids: [], captain_id: null, wicket_keeper_id: null }))
  await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
  await page.route(new RegExp(`/api/selection/${FID}/draft(\\?.*)?$`), (r) => json(r, { draft: null, version: 0 }))
  await page.route(new RegExp(`/api/selection/${FID}/lock$`), (r) => { wire.locks++; server.locked = true; return json(r, { status: 'ok', locked: true }) })
  await page.route(new RegExp(`/api/selection/${FID}/unlock$`), (r) => { wire.unlocks++; server.locked = false; return json(r, { status: 'ok', locked: false }) })
  await page.route(new RegExp(`/api/selection/${FID}/history$`), (r) => json(r, { events: server.events }))
  await page.route(new RegExp(`/api/selection/${FID}$`), async (r) => {
    if (r.request().method() === 'PUT') {
      const b = JSON.parse(r.request().postData())
      wire.puts.push(b)
      server.lineup = b.players
      if (b.lock) server.locked = true
      const names = b.players.map((p) => POOL.find((x) => x.id === p.player_id)?.display_name)
      server.events.unshift({ id: `e${server.events.length}`, by: 'Sam Selector', action: 'confirmed', at: new Date().toISOString(),
        detail: { added: names, removed: [], locked: !!b.lock, after: b.players.map((p) => ({ ...p, name: POOL.find((x) => x.id === p.player_id)?.display_name })) } })
      return json(r, { status: 'ok', count: b.players.length, locked: server.locked })
    }
    return json(r, {
      ...FIX.payload,
      fixture: { ...FIX.payload.fixture, locked: server.locked, locked_at: server.locked ? new Date().toISOString() : null, locked_by: server.locked ? 'Sam Selector' : null },
      pool: POOL,
      lineup: server.lineup,
      flags: { ...FIX.payload.flags, registered: 'fees', season_start: '2026-07-01' },
    })
  })

  const card = (name) => page.locator('div.group.relative.rounded-xl', { hasText: name }).first()
  const body = async () => (await page.locator('body').innerText()).replace(/\s+/g, ' ')
  const open = async () => {
    await page.goto(`${BASE}/admin/betterselect/select/${FID}`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Zed Adams').first().waitFor({ timeout: 20000 })
    await page.waitForTimeout(400)
  }
  const confirmBtn = () => page.locator('button[data-confirm]').first()
  const undoBtn = () => page.locator('button[data-undo]').first()
  const count = async () => {
    const t = await confirmBtn().innerText({ timeout: 1500 }).catch(() => '')
    const m = /\((\d+)\)/.exec(t); return m ? Number(m[1]) : 0
  }

  /* ───────── Undo ───────── */
  await safe('Undo', async () => {
    await open()
    ok('Undo is disabled before anything changes', await undoBtn().isDisabled().catch(() => 'absent') === true)
    await card('Zed Adams').click(); await page.waitForTimeout(200)
    await card('Cara Cole').click(); await page.waitForTimeout(200)
    ok('two picks on the board: Confirm (2)', (await count()) === 2, await confirmBtn().innerText().catch(() => '<absent>'))
    ok('Undo is now enabled', (await undoBtn().isDisabled().catch(() => 'absent')) === false)
    await undoBtn().click(); await page.waitForTimeout(250)
    ok('Undo takes the last pick back (Confirm (1))', (await count()) === 1, String(await count()))
    await page.keyboard.press('Control+z'); await page.waitForTimeout(250)
    ok('Ctrl+Z takes the one before it back', /Confirmed|Lock team/.test(await confirmBtn().innerText().catch(() => '')), await confirmBtn().innerText().catch(() => '<absent>'))
    ok('and Undo is disabled again at the start', (await undoBtn().isDisabled().catch(() => 'absent')) === true)
  })

  /* ───────── Confirm locks ───────── */
  await safe('Confirm locks', async () => {
    await card('Zed Adams').click(); await page.waitForTimeout(150)
    await card('Dan Dunn').click(); await page.waitForTimeout(150)
    await confirmBtn().click(); await page.waitForTimeout(1200)
    ok('Confirm sends the side with lock:true', wire.puts.length === 1 && wire.puts[0].lock === true, JSON.stringify(wire.puts[0]))
    ok('the board now says Locked with an Unlock button', (await page.locator('[data-locked-banner]').count()) === 1 && (await page.locator('button[data-unlock]').count()) === 1)
    ok('...and names who locked it', /Sam Selector locked this side/.test(await body()), (await body()).slice(0, 200))
    ok('there is no Confirm button on a locked side', (await confirmBtn().count()) === 0)
    const before = (await page.locator('[data-slot]').count().catch(() => 0))
    await card('Cara Cole').click({ timeout: 1500 }).catch(() => {})
    await page.waitForTimeout(250)
    ok('a locked side takes no picks', wire.puts.length === 1 && (await page.locator('[data-locked-banner]').count()) === 1 && !(await body()).includes('Draft.'))
    await page.screenshot({ path: process.env.SHOT_DIR ? `${process.env.SHOT_DIR}/selection-locked-1440.png` : '/tmp/selection-locked-1440.png' })
  })

  /* ───────── 390px ───────── */
  await safe('390px', async () => {
    await page.setViewportSize({ width: 390, height: 800 })
    await page.waitForTimeout(500)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
    ok('the locked board has no sideways overflow at 390px', overflow <= 1, String(overflow))
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.waitForTimeout(300)
  })

  /* ───────── History ───────── */
  await safe('History', async () => {
    await page.getByRole('button', { name: /History/ }).click()
    await page.locator('[data-selection-history]').waitFor({ timeout: 5000 })
    ok('History lists the confirm with who did it', (await page.locator('[data-history-row="confirmed"]').count()) === 1 && /Sam Selector/.test(await page.locator('[data-selection-history]').innerText()))
    ok('a locked side offers no "load onto the board"', (await page.getByText('Load this side onto the board').count()) === 0)
    await page.locator('[data-selection-history] button[aria-label="Close"]').click()
  })

  /* ───────── Unlock ───────── */
  await safe('Unlock', async () => {
    await page.locator('button[data-unlock]').first().click(); await page.waitForTimeout(900)
    ok('Unlock sends POST /unlock', wire.unlocks === 1)
    ok('the banner is gone and the board is open again', (await page.locator('[data-locked-banner]').count()) === 0)
    ok('a named, unlocked side offers "Lock team"', /Lock team/.test(await confirmBtn().innerText().catch(() => '<absent>')), await confirmBtn().innerText().catch(() => '<absent>'))
    await confirmBtn().click(); await page.waitForTimeout(900)
    ok('Lock team sends POST /lock (no XI write)', wire.locks === 1 && wire.puts.length === 1)
    ok('...and it reads Locked again', (await page.locator('[data-locked-banner]').count()) === 1)
    await page.locator('button[data-unlock]').first().click(); await page.waitForTimeout(900)
  })

  /* ───────── Restore from history ───────── */
  await safe('Restore from history', async () => {
    await page.getByRole('button', { name: /History/ }).click()
    await page.locator('[data-selection-history]').waitFor({ timeout: 5000 })
    const writes = wire.puts.length
    await page.getByText('Load this side onto the board').first().click(); await page.waitForTimeout(500)
    ok('loading a version writes nothing', wire.puts.length === writes)
    ok('...the board shows it as unconfirmed (nothing changed here, so Lock team)', /Lock team|Confirm/.test(await confirmBtn().innerText().catch(() => '')))
  })

  /* ───────── Filters and order ───────── */
  await safe('Filters and order', async () => {
    // Pool cards in the order they are drawn, as the first name found in each.
    const poolNames = async () => {
      const t = await page.locator('div.group.relative.rounded-xl').allInnerTexts()
      return t.map((x) => (POOL.find((p) => x.includes(p.display_name)) || {}).display_name).filter(Boolean)
    }
    await page.getByRole('button', { name: /^Filters/ }).first().click().catch(() => {})
    await page.waitForTimeout(300)
    ok('the Registered filter is offered (the club records it)', (await page.getByText('Registered', { exact: true }).count()) > 0)
    await page.getByRole('button', { name: 'Not registered' }).click().catch(() => {}); await page.waitForTimeout(300)
    let t = await body()
    ok('"Not registered" leaves only the unregistered player', t.includes('Anna Brown') && !t.includes('Cara Cole'), '')
    await page.getByRole('button', { name: 'Not known', exact: true }).first().click().catch(() => {}); await page.waitForTimeout(300)
    t = await body()
    ok('"Not known" is the players the club has not told us about', t.includes('Cara Cole') && !t.includes('Anna Brown'))
    await page.getByRole('button', { name: 'All', exact: true }).first().click().catch(() => {})
    await page.getByRole('button', { name: 'Registered', exact: true }).last().click().catch(() => {}); await page.waitForTimeout(300)
    t = await body()
    ok('"Registered" shows the registered players still in the pool', t.includes('Dan Dunn') || t.includes('Zed Adams'))

    // Clear filters via URL, then season recency. An empty confirmed XI, so all four are in the pool.
    server.lineup = []
    await page.goto(`${BASE}/admin/betterselect/select/${FID}?q=`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Anna Brown').first().waitFor({ timeout: 20000 })
    ok('there is no "Played within" control on the board any more', (await page.locator('select', { has: page.locator('option', { hasText: 'Played this season' }) }).count()) === 0)
    // The window is the club's setting: "this season" drops the player who last played before the season started.
    server.playedYears = -1
    await page.goto(`${BASE}/admin/betterselect/select/${FID}?q=`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Cara Cole').first().waitFor({ timeout: 20000 })
    await page.waitForTimeout(300)
    t = await body()
    ok('the club setting "Played this season" hides the player who last played before the season started', !t.includes('Anna Brown') && t.includes('Cara Cole'))
    server.playedYears = 0
    await page.goto(`${BASE}/admin/betterselect/select/${FID}?q=`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Anna Brown').first().waitFor({ timeout: 20000 })
    ok('...and "any time" brings them back', (await body()).includes('Anna Brown'))

    await page.locator('button[title="Sort pool"]').click()
    const firstOpt = page.getByRole('button', { name: 'First name (A–Z)' })
    const hasSort = (await firstOpt.count()) > 0
    ok('a "First name (A–Z)" order is offered', hasSort)
    if (hasSort) {
      await firstOpt.click(); await page.waitForTimeout(300)
      const order = await poolNames()
      ok('first-name order: Anna, Cara, Dan, Zed', order.findIndex((n) => /Anna/.test(n)) < order.findIndex((n) => /Cara/.test(n)) && order.findIndex((n) => /Cara/.test(n)) < order.findIndex((n) => /Dan/.test(n)) && order.findIndex((n) => /Dan/.test(n)) < order.findIndex((n) => /Zed/.test(n)), order.join(' | '))
    }
  })

  /* ───────── Overview ───────── */
  await safe('Overview', async () => {
    server.overviewLocked = true
    await page.goto(`${BASE}/admin/betterselect/selection`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: /Expand all/ }).waitFor({ timeout: 20000 })
    await page.waitForTimeout(500)
    ok('the overview no longer carries a Show juniors switch', (await page.locator('[data-juniors-toggle]').count()) === 0)
    ok('the overview asks for juniors to be left out', server.overviewUrls.some((u) => u.includes('hide_juniors=true')), JSON.stringify(server.overviewUrls))
    ok('a locked side reads Locked on the overview', /Locked/.test(await body()))
    await page.getByRole('button', { name: /Expand all/ }).click(); await page.waitForTimeout(300)
    ok('and offers View XI', /View XI/.test(await body()))
    server.overviewUrls.length = 0
    await page.evaluate(() => { try { localStorage.setItem('bs_pref:select.juniors', 'true') } catch { /* blocked */ } })
    await page.goto(`${BASE}/admin/betterselect/selection`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: /Expand all/ }).waitFor({ timeout: 20000 })
    await page.waitForTimeout(600)
    ok('with juniors on in Settings, the request drops the hide filter', server.overviewUrls.length > 0 && server.overviewUrls.every((u) => !u.includes('hide_juniors')), JSON.stringify(server.overviewUrls))
    await page.evaluate(() => { try { localStorage.removeItem('bs_pref:select.juniors') } catch { /* nothing stored */ } })
    server.overviewLocked = false
    await page.goto(`${BASE}/admin/betterselect/selection`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: /Expand all/ }).waitFor({ timeout: 20000 })
    if (!/Review and lock|Collapse all/.test(await body())) await page.getByRole('button', { name: /Expand all/ }).click().catch(() => {})
    await page.waitForTimeout(300)
    ok('an unlocked, full side offers "Review and lock"', /Review and lock/.test(await body()), (await body()).slice(0, 300))
  })

  ok('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
