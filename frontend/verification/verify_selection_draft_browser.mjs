// Drives the REAL Selection board in Chromium with the API stubbed at the
// network layer (a tiny in-memory stand-in for the draft row). Reported:
// leaving the screen after moving people in and out lost all progress.
//
//   * every pick is autosaved to PUT /selection/:id/draft, never to the real XI
//   * leaving the screen straight after a pick still saves it (no waiting out
//     the debounce), and coming back restores the side without pressing anything
//   * putting everyone back removes the draft and the button reads "Confirmed"
//   * the button is "Confirm (n)"; only it writes PUT /selection/:id, which is
//     what clears the draft
//   * "Discard changes" deletes the draft and returns to the confirmed XI
//   * two selectors: another selector's draft is picked up by a board with nothing
//     unsent; a board with unsent changes is refused (409), stops saving, and asks
//     "Use their version" or "Keep mine", and nothing of theirs is overwritten
//   * the matchday overview marks a fixture that has a draft
//   * 390px: no horizontal overflow with the draft banner showing
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_selection_draft_browser.mjs
import { chromium } from 'playwright'
import { readFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures/selection_same_day.json'), 'utf8'))
const ID = FIX.ids
const FID = FIX.fixture_id

let PASS = 0, FAIL = 0
const FAILURES = []
const ok = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(label); console.log(`  FAIL ${label}  ${detail}`) }
}

const ME = {
  id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' },
}

const run = async () => {
  mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('dialog', (d) => d.accept())

  // The "server": one draft slot, and a log of every write the page makes.
  const server = { draft: null, version: 0, by: null, confirmed: [], overview: [] }
  const wire = { draftPuts: [], draftDeletes: 0, confirms: [], conflicts: 0 }
  // Another selector (Sam) changes the draft behind this page's back.
  const otherSaves = (slots) => {
    server.draft = { slots, captain_id: null, wicket_keeper_id: null, demotions: [] }
    server.version += 1
    server.by = 'Sam Selector'
  }
  const conflict = (r) => {
    wire.conflicts++
    return r.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: {
      code: 'draft_conflict', message: 'Someone else changed this draft since you loaded it.',
      draft: server.draft, version: server.version, updated_by: server.by, updated_at: new Date().toISOString(),
    } }) })
  }
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route('**/api/selection/overview', (r) => json(r, { fixtures: server.overview, default_team_size: 11 }))
  await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { source_fixture_id: null, player_ids: [], captain_id: null, wicket_keeper_id: null }))
  await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
  await page.route(new RegExp(`/api/selection/${FID}/draft(\\?.*)?$`), async (r) => {
    const m = r.request().method()
    if (m === 'PUT') {
      const b = JSON.parse(r.request().postData())
      wire.draftPuts.push(b)
      if ((b.base_version || 0) !== server.version) return conflict(r)
      server.draft = b
      server.version += 1
      server.by = 'Jordan Admin'
      return json(r, { status: 'ok', version: server.version })
    }
    if (m === 'DELETE') {
      const base = Number(new URL(r.request().url()).searchParams.get('base_version') || 0)
      if (base && base !== server.version && server.draft) return conflict(r)
      wire.draftDeletes++; server.draft = null; server.version = 0
      return json(r, { status: 'ok', version: 0 })
    }
    return json(r, server.draft
      ? { draft: server.draft, version: server.version, updated_at: new Date().toISOString(), updated_by: server.by }
      : { draft: null, version: 0 })
  })
  await page.route(new RegExp(`/api/selection/${FID}$`), async (r) => {
    if (r.request().method() === 'PUT') {
      const b = JSON.parse(r.request().postData())
      wire.confirms.push(b)
      server.confirmed = b.players.map((p) => p.player_id)
      server.draft = null; server.version = 0    // the real route clears it in the same transaction
      return json(r, { status: 'ok', count: b.players.length })
    }
    const lineup = server.confirmed.map((pid, i) => ({ player_id: pid, batting_order: i + 1, is_captain: false, is_wicket_keeper: false }))
    return json(r, { ...FIX.payload, lineup })
  })

  if (process.env.TRACE) page.on('request', (rq) => { if (/selection/.test(rq.url()) && rq.method() !== 'GET') console.log('   >>', rq.method(), rq.url().replace(/^.*\/api/, ''), (rq.postData() || '').slice(0, 120)) })
  const card = (name) => page.locator('div.group.relative.rounded-xl', { hasText: name }).first()
  const body = async () => (await page.locator('body').innerText()).replace(/\s+/g, ' ')
  const open = async () => {
    await page.goto(`${BASE}/admin/betterselect/select/${FID}`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Cara Free').first().waitFor({ timeout: 20000 })
    await page.waitForTimeout(300)
  }
  const confirmBtn = () => {
    const loc = page.getByRole('button', { name: /^confirm/i }).first()
    // Presence-safe: against a build without the Confirm button this reports
    // "<absent>" instead of timing out, so a control run fails checks, not the script.
    return { innerText: () => loc.innerText({ timeout: 1500 }).catch(() => '<absent>'), click: () => loc.click({ timeout: 1500 }).catch(() => {}) }
  }

  await open()
  console.log('\n# nothing to confirm yet')
  ok('button reads "Confirmed"', /Confirmed/.test(await confirmBtn().innerText()))
  ok('no draft banner', !/Draft\./.test(await body()))

  console.log('\n# autosave as you pick')
  await card('Cara Free').click()
  await page.waitForTimeout(250)
  await card('Alex Backtoback').click()
  await page.waitForTimeout(1500)
  ok('button now reads "Confirm (2)"', /Confirm \(2\)/.test(await confirmBtn().innerText()), await confirmBtn().innerText())
  ok('draft banner shown', /Draft\./.test(await body()))
  const last = wire.draftPuts[wire.draftPuts.length - 1]
  ok('a draft PUT went out without pressing anything', !!last)
  ok('it names Cara and Alex', !!last && last.slots.includes(ID['Cara Free']) && last.slots.includes(ID['Alex Backtoback']), JSON.stringify(last))
  ok('picking did NOT write the real XI', wire.confirms.length === 0)
  ok('banner settles on "saved as you go"', /saved as you go/.test(await body()))
  await page.screenshot({ path: join(SHOTS, 'selection_draft_1440.png') })

  console.log('\n# leaving straight after a pick still saves it, and coming back restores it')
  const putsBefore = wire.draftPuts.length
  await card('Bob Blocked').click()          // refused (real clash): no change
  await page.waitForTimeout(100)
  // Remove Cara, then leave inside the debounce window.
  await page.locator('[title="Remove"]').first().click({ timeout: 1500 }).catch(() => {})
  await page.getByRole('link', { name: /All teams/ }).click()
  await page.waitForTimeout(800)
  ok('the last change was flushed on leaving', wire.draftPuts.length > putsBefore, `${putsBefore} -> ${wire.draftPuts.length}`)
  const flushed = wire.draftPuts[wire.draftPuts.length - 1] || { slots: [] }
  ok('flushed draft has one player left', flushed.slots.filter(Boolean).length === 1, JSON.stringify(flushed.slots))
  await page.goBack()
  await page.getByText('Cara Free').first().waitFor({ timeout: 20000 })
  await page.waitForTimeout(600)
  ok('back on the board: button reads "Confirm (1)" with no Confirm pressed', /Confirm \(1\)/.test(await confirmBtn().innerText()), await confirmBtn().innerText())
  ok('draft banner is back', /Draft\./.test(await body()))
  ok('the board credits who saved it', /Last saved by Jordan Admin/.test(await body()))
  ok('restoring did not write anything', wire.confirms.length === 0)
  await page.screenshot({ path: join(SHOTS, 'selection_draft_restored.png') })

  console.log('\n# getting back to the confirmed XI removes the draft')
  const dels = wire.draftDeletes
  await page.locator('[title="Remove"]').first().click({ timeout: 1500 }).catch(() => {})
  await page.waitForTimeout(1500)
  ok('a DELETE went out', wire.draftDeletes === dels + 1, `${dels} -> ${wire.draftDeletes}, conflicts ${wire.conflicts}, server v${server.version}, body: ${(await body()).slice(0, 160)}`)
  ok('button reads "Confirmed" again', /Confirmed/.test(await confirmBtn().innerText()))
  ok('banner gone', !/Draft\./.test(await body()))

  console.log('\n# Confirm is the only thing that writes the XI')
  await card('Cara Free').click()
  await page.waitForTimeout(250)
  await card('Alex Backtoback').click()
  await page.waitForTimeout(1500)
  await confirmBtn().click()
  await page.waitForTimeout(1200)
  ok('exactly one PUT to the real XI', wire.confirms.length === 1)
  const ids = (wire.confirms[0]?.players || []).map((p) => p.player_id)
  ok('it carries Cara and Alex, numbered 1 and 2', ids.length === 2 && ids.includes(ID['Cara Free']) && ids.includes(ID['Alex Backtoback']) && wire.confirms[0].players.map((p) => p.batting_order).join() === '1,2', JSON.stringify(wire.confirms[0]))
  ok('the stand-in server cleared its draft', server.draft === null)
  ok('after confirming the button reads "Confirmed"', /Confirmed/.test(await confirmBtn().innerText()), await confirmBtn().innerText())
  ok('no draft write landed after the confirm', server.draft === null)
  ok('toast says Confirmed', /Confirmed 2 players/.test(await body()))

  console.log('\n# Discard changes goes back to the confirmed XI')
  await card('Bob Blocked').click().catch(() => {})
  await page.locator('[title="Remove"]').first().click({ timeout: 1500 }).catch(() => {})
  await page.waitForTimeout(1500)
  ok('one change from confirmed shows the banner', /Draft\./.test(await body()))
  ok('server holds the draft', server.draft !== null)
  const d2 = wire.draftDeletes
  await page.getByRole('button', { name: /Discard changes/ }).click({ timeout: 1500 }).catch(() => {})
  await page.waitForTimeout(1200)
  ok('DELETE sent', wire.draftDeletes === d2 + 1)
  ok('banner gone and button "Confirmed"', !/Draft\./.test(await body()) && /Confirmed/.test(await confirmBtn().innerText()))
  ok('both confirmed players are back on the board', !(await body()).includes('Confirm (') && wire.confirms.length === 1)

  console.log('\n# a second selector: their draft reaches a board with nothing unsent')
  const poll = async () => { await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange'))); await page.waitForTimeout(700) }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await open()
  ok('board starts on the confirmed XI', /Confirmed/.test(await confirmBtn().innerText()), await confirmBtn().innerText())
  const putsBeforeSam = wire.draftPuts.length
  otherSaves([ID['Cara Free'], null, ID['Alex Backtoback']])
  await poll()
  ok('the board picked up their draft without being touched', /Confirm \(2\)/.test(await confirmBtn().innerText()), await confirmBtn().innerText())
  ok('it says so', /Sam Selector changed the draft/.test(await body()))
  ok('and credits them in the strip', /Last saved by Sam Selector/.test(await body()))
  ok('adopting their draft wrote nothing', wire.draftPuts.length === putsBeforeSam)
  await page.screenshot({ path: join(SHOTS, 'selection_draft_adopted.png') })

  console.log('\n# a second selector: unsent changes meet theirs')
  otherSaves([ID['Cara Free']])                     // Sam trims it to one player; this board has not polled yet
  const conflictsBefore = wire.conflicts
  await page.locator('[title="Remove"]').first().click()   // we change our copy
  await page.waitForTimeout(1500)
  ok('our save was refused (409)', wire.conflicts === conflictsBefore + 1, `${conflictsBefore} -> ${wire.conflicts}`)
  ok('the conflict strip names them', /Sam Selector changed this draft/.test(await body()), (await body()).slice(0, 300))
  ok('with both choices', /Use their version/.test(await body()) && /Keep mine/.test(await body()))
  ok('their draft was not overwritten', (server.draft?.slots || []).filter(Boolean).length === 1 && server.by === 'Sam Selector', JSON.stringify(server.draft))
  const putsInConflict = wire.draftPuts.length
  await card('Bob Blocked').click()
  await page.waitForTimeout(1500)
  await poll()
  ok('autosave stays stopped while it is unsettled', wire.draftPuts.length === putsInConflict, `${putsInConflict} -> ${wire.draftPuts.length}`)
  await page.screenshot({ path: join(SHOTS, 'selection_draft_conflict.png') })

  console.log('\n# Keep mine saves this board over theirs, on their version')
  const verBefore = server.version
  await page.getByRole('button', { name: 'Keep mine' }).click({ timeout: 1500 }).catch(() => {})
  await page.waitForTimeout(1500)
  ok('strip gone', !/changed this draft/.test(await body()))
  const lastMine = wire.draftPuts[wire.draftPuts.length - 1] || {}
  ok('it saved with their version as the base', lastMine.base_version === verBefore, `${lastMine.base_version} vs ${verBefore}`)
  ok('server now holds this board', server.by === 'Jordan Admin' && server.version === verBefore + 1)

  console.log('\n# Use their version replaces this board and writes nothing')
  otherSaves([ID['Alex Backtoback']])
  await page.locator('[title="Remove"]').first().click().catch(() => {})
  await page.waitForTimeout(1500)
  ok('conflict strip again', /Sam Selector changed this draft/.test(await body()))
  const putsBeforeTheirs = wire.draftPuts.length
  await page.getByRole('button', { name: 'Use their version' }).click({ timeout: 1500 }).catch(() => {})
  await page.waitForTimeout(1500)
  ok('strip gone', !/changed this draft/.test(await body()))
  ok('board shows exactly their one player', /Confirm \(1\)/.test(await confirmBtn().innerText()), await confirmBtn().innerText())
  ok('nothing was written', wire.draftPuts.length === putsBeforeTheirs)
  ok('their draft is untouched', server.by === 'Sam Selector')

  console.log('\n# the draft vanishing (confirmed or discarded elsewhere)')
  server.draft = null; server.version = 0
  await poll()
  ok('a board with nothing unsent drops back to the confirmed XI', /Confirmed/.test(await confirmBtn().innerText()) && !/Draft\./.test(await body()), await confirmBtn().innerText())
  ok('and says why', /confirmed or discarded by someone else/.test(await body()))

  console.log('\n# the matchday overview marks a fixture with a draft')
  const soon = new Date(Date.now() + 5 * 86400000).toISOString().slice(0, 10)
  const ovFx = (id, extra = {}) => ({ id, label: 'x', opponent_name: 'Rivals', home_away: 'HOME', played_on: soon, start_time: '9:00am',
    round: '1', venue: 'Oval', team_name: 'Colts', team_sequence: 4, grade_name: 'Colts', lineup: [], ...extra })
  server.overview = [ovFx(FID, { has_draft: true, draft_updated_at: new Date().toISOString() }), ovFx('00000000-0000-4000-8000-0000000000aa', { team_name: '2nd Grade' })]
  await page.goto(`${BASE}/admin/betterselect/selection`, { waitUntil: 'domcontentloaded' })
  await page.getByText('Colts').first().waitFor({ timeout: 20000 }).catch(() => {})
  await page.waitForTimeout(400)
  const ovText = await body()
  ok('the fixture with a draft says "Draft, not confirmed"', /Draft, not confirmed/.test(ovText))
  ok('only once (the other fixture has none)', (ovText.match(/Draft, not confirmed/g) || []).length === 1, String((ovText.match(/Draft, not confirmed/g) || []).length))
  await page.screenshot({ path: join(SHOTS, 'selection_draft_overview.png') })
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(300)
  ok('overview: no horizontal overflow at 390px', (await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 0)
  await page.setViewportSize({ width: 1440, height: 1000 })
  server.overview = []
  await open()

  console.log('\n# 390px')
  await card('Alex Backtoback').click().catch(() => {})
  await page.locator('[title="Remove"]').first().click({ timeout: 1500 }).catch(() => {})
  await page.waitForTimeout(1000)
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(400)
  ok('banner visible at 390px', /Draft\./.test(await body()))
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ok('no horizontal page overflow at 390px', overflow <= 0, `overflow ${overflow}px`)
  await page.screenshot({ path: join(SHOTS, 'selection_draft_390.png') })

  ok('no page errors', errors.length === 0, JSON.stringify(errors))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  if (FAIL) { FAILURES.forEach((f) => console.log('  -', f)); process.exit(1) }
}
run().catch((e) => { console.error(e); process.exit(1) })
