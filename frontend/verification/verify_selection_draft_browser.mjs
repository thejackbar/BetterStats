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
  const server = { draft: null, confirmed: [] }
  const wire = { draftPuts: [], draftDeletes: 0, confirms: [] }
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route('**/api/selection/overview', (r) => json(r, { fixtures: [] }))
  await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { source_fixture_id: null, player_ids: [], captain_id: null, wicket_keeper_id: null }))
  await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
  await page.route(new RegExp(`/api/selection/${FID}/draft$`), async (r) => {
    const m = r.request().method()
    if (m === 'PUT') {
      const b = JSON.parse(r.request().postData())
      wire.draftPuts.push(b)
      server.draft = b
      return json(r, { status: 'ok' })
    }
    if (m === 'DELETE') { wire.draftDeletes++; server.draft = null; return json(r, { status: 'ok' }) }
    return json(r, server.draft ? { draft: server.draft, updated_at: new Date().toISOString(), updated_by: 'Sam Selector' } : { draft: null })
  })
  await page.route(new RegExp(`/api/selection/${FID}$`), async (r) => {
    if (r.request().method() === 'PUT') {
      const b = JSON.parse(r.request().postData())
      wire.confirms.push(b)
      server.confirmed = b.players.map((p) => p.player_id)
      server.draft = null    // the real route clears it in the same transaction
      return json(r, { status: 'ok', count: b.players.length })
    }
    const lineup = server.confirmed.map((pid, i) => ({ player_id: pid, batting_order: i + 1, is_captain: false, is_wicket_keeper: false }))
    return json(r, { ...FIX.payload, lineup })
  })

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
  ok('the board credits who saved it', /Last saved by Sam Selector/.test(await body()))
  ok('restoring did not write anything', wire.confirms.length === 0)
  await page.screenshot({ path: join(SHOTS, 'selection_draft_restored.png') })

  console.log('\n# getting back to the confirmed XI removes the draft')
  const dels = wire.draftDeletes
  await page.locator('[title="Remove"]').first().click({ timeout: 1500 }).catch(() => {})
  await page.waitForTimeout(1500)
  ok('a DELETE went out', wire.draftDeletes === dels + 1, `${dels} -> ${wire.draftDeletes}`)
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
