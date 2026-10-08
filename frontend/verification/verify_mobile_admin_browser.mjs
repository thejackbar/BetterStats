// Phone-size checks for the three screens a club reported as hard to use on a
// phone, driven in Chromium with touch and a real mobile viewport (a page wider
// than the screen widens the layout viewport, as it does on the reporter's phone).
//
//   Accounts   no page wider than the screen; every figure of a person is on
//              screen as a card; the header scrolls away instead of sitting on
//              the list; the PlayHQ tick writes the right request
//   Squads     the page is not wider than the screen; the availability dot is a
//              40px target and a tap beside it opens the sheet, not the profile;
//              the sheet is wholly on screen and saves the chosen status
//   Selection  Confirm and Pool / XI are pinned to the bottom; "Add players"
//              searches by any word order and adds without leaving the XI; the
//              up / down buttons and the options sheet change the batting order,
//              captain and keeper; Confirm writes the order that is on screen;
//              the desk layout (1440px) is unchanged
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_mobile_admin_browser.mjs
import { readFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { launch, overflow, stubAccounts, stubSquads, stubPlayers, json, BASE, PHONE } from './mobile_harness.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
mkdirSync(SHOTS, { recursive: true })
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures/selection_same_day.json'), 'utf8'))
const FID = FIX.fixture_id

let PASS = 0, FAIL = 0
const FAILURES = []
const ok = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(label); console.log(`  FAIL ${label}  ${detail}`) }
}
// Presence-safe: a build without the feature reports absence instead of throwing.
const box = (loc) => loc.first().boundingBox({ timeout: 1500 }).catch(() => null)
const count = (loc) => loc.count().catch(() => 0)
const text = (loc) => loc.first().innerText({ timeout: 1500 }).then((t) => t || '').catch(() => '')
const tap = (loc) => loc.first().tap({ timeout: 2500 }).catch(() => {})
const inScreen = (b, w = PHONE.width) => !!b && b.x >= -0.5 && b.x + b.width <= w + 0.5

const run = async () => {
  // ═══ Accounts ═══════════════════════════════════════════════════════════
  console.log('Accounts (390px)')
  {
    const { browser, page, errors } = await launch()
    const writes = []
    page.on('request', (rq) => { if (rq.method() !== 'GET' && /\/fees\//.test(rq.url())) writes.push({ m: rq.method(), url: rq.url(), body: rq.postData() }) })
    await stubAccounts(page, 24)
    await page.route(/\/api\/club-admin\/fees\/members\/[^/]+\/season/, (r) => json(r, { status: 'ok' }))
    await page.goto(`${BASE}/admin/fees`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Owes money').first().waitFor({ timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(400)

    const o = await overflow(page)
    ok('page is not wider than the screen', o.over <= 0, JSON.stringify(o))
    const add = page.getByRole('button', { name: 'Add member' })
    ok('Add member is on screen', inScreen(await box(add)), JSON.stringify(await box(add)))
    const cards = page.locator('[data-testid="accounts-cards"] > div.pb-card:not(label)')
    ok('one card per person (24)', (await count(cards)) === 24, `got ${await count(cards)}`)
    const first = cards.first()
    const txt = ((await text(first)) || '').replace(/\s+/g, ' ')
    ok('a card shows payable, paid and owed', /PAYABLE/i.test(txt) && /PAID/i.test(txt) && /OWED/i.test(txt) && /\$250/.test(txt), txt)
    ok('a card shows the status and the tier', /(FINANCIAL|OWES)/i.test(txt) && /Mens - Established/.test(txt), txt)
    ok('the 11-column table is not drawn on a phone', !(await page.locator('table').first().isVisible().catch(() => false)))
    await page.screenshot({ path: join(SHOTS, 'accounts_top.png') })

    // The header scrolls away; only the slim bar stays.
    await page.evaluate(() => window.scrollTo(0, 900))
    await page.waitForTimeout(250)
    const bar = await box(page.getByRole('button', { name: 'Open menu' }))
    ok('the menu button stays pinned at the top', !!bar && bar.y >= 0 && bar.y < 80, JSON.stringify(bar))
    const membership = await box(page.getByText('Membership', { exact: true }))
    ok('the filter box scrolled away with the page', !membership || membership.y + membership.height < 0, JSON.stringify(membership))
    await page.screenshot({ path: join(SHOTS, 'accounts_scrolled.png') })

    // PlayHQ tick from a card (row 2 is not registered: i % 2)
    const tick = cards.nth(1).getByLabel ? cards.nth(1).locator('label:has-text("PlayHQ") input') : null
    await tick.check({ timeout: 2000 }).catch(() => {})
    await page.waitForTimeout(250)
    const w = writes.find((x) => /season/.test(x.url) && x.m === 'PATCH')
    ok('ticking PlayHQ on a card patches that member', !!w && /"playhq_registered":true/.test(w.body || ''), JSON.stringify(writes))
    ok('no script error', errors.length === 0, errors.join(' | '))
    await browser.close()
  }

  // ═══ Squads ═════════════════════════════════════════════════════════════
  console.log('Squads (390px)')
  {
    const { browser, page, errors } = await launch()
    const writes = []
    page.on('request', (rq) => { if (rq.method() === 'POST' && /\/api\/availability$/.test(rq.url())) writes.push(JSON.parse(rq.postData() || '{}')) })
    await stubSquads(page)
    await page.goto(`${BASE}/admin/betterselect/teams`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Abbas, Aamir').first().waitFor({ timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(400)
    const o = await overflow(page)
    ok('page is not wider than the screen', o.over <= 0, JSON.stringify(o))

    const dot = page.locator('[data-avail-dot]').first()
    const d = await box(dot)
    ok('the availability dot is a 40px touch target', !!d && d.width >= 39.5 && d.height >= 39.5, JSON.stringify(d))
    // A thumb that lands 14px to the right of the dot's centre: on the old 17px
    // target that was the avatar link, so it opened the player's profile.
    if (d) await page.touchscreen.tap(d.x + d.width / 2 + 14, d.y + d.height / 2)
    await page.waitForTimeout(300)
    const dlg = page.getByRole('dialog', { name: /Update availability/i })
    ok('a tap beside the dot opens the availability sheet', (await count(dlg)) === 1)
    ok('and does not leave the Squads page', /\/teams/.test(page.url()), page.url())
    const panel = await box(dlg.locator('> div'))
    ok('the sheet is wholly on screen', inScreen(panel), JSON.stringify(panel))
    ok('the sheet sits at the bottom, under the thumb', !!panel && panel.y + panel.height >= PHONE.height - 2, JSON.stringify(panel))
    await page.screenshot({ path: join(SHOTS, 'squads_sheet.png') })
    await tap(dlg.getByRole('button', { name: 'Unavailable' }))
    await page.waitForTimeout(300)
    ok('choosing a status saves it for the fixture date', writes.length === 1 && writes[0].status === 'UNAVAILABLE' && writes[0].date === '2027-04-20', JSON.stringify(writes))
    ok('the sheet closes after the pick', (await count(dlg)) === 0)
    ok('no script error', errors.length === 0, errors.join(' | '))
    await browser.close()
  }

  // ═══ Selection ══════════════════════════════════════════════════════════
  const NAMES = ['Abbas, Aamir', 'Barendse, Jack', 'Barker, David', 'Ashworth, Shayne', 'Kumar, Raj', 'Singh, Amit', 'Perera, Nuwan',
    'Smith, Tom', 'Jones, Ben', 'Wilson, Sam', 'Taylor, Max', 'Brown, Lee', 'Davis, Cal', 'Evans, Zac']
  const tpl = FIX.payload.pool.find((p) => !p.clash?.length && !p.also_in?.length) || FIX.payload.pool[0]
  const pool = NAMES.map((n, i) => ({ ...tpl, id: `pl-${i}`, display_name: n, name: n, clash: [], clash_detail: [], clash_blocks: false, also_in: [], availability: i % 5 === 4 ? 'UNAVAILABLE' : 'AVAILABLE', skill_positions: i % 4 === 0 ? ['WKT'] : ['BAT'], squads: [], is_inactive: false, last_played: '2026-03-01', rule_flags: [], rule_notes: [], rule_state: 'ok', tier: 1, drop_in_from: null }))
  // Davis is in the 3rd XI squad and not picked there: one grade up (tier 3), so he
  // would sort LAST by tier alone; the server says he is a drop-in and he goes first.
  Object.assign(pool.find((p) => p.display_name === 'Davis, Cal'), { tier: 3, drop_in_from: '3rd XI' })
  const payload = { ...FIX.payload, pool, lineup: [] }

  const stubSelection = async (page, state) => {
    await page.route(/\/api\/selection\/overview/, (r) => json(r, { fixtures: [], default_team_size: 11 }))
    await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { player_ids: [] }))
    await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
    await page.route(new RegExp(`/api/selection/${FID}/draft(\\?.*)?$`), (r) => {
      const m = r.request().method()
      if (m === 'PUT') { state.draft = JSON.parse(r.request().postData()); state.v += 1; return json(r, { status: 'ok', version: state.v }) }
      if (m === 'DELETE') { state.draft = null; return json(r, { status: 'ok', version: 0 }) }
      return json(r, state.draft ? { draft: state.draft, version: state.v, updated_at: new Date().toISOString(), updated_by: 'Me' } : { draft: null, version: 0 })
    })
    await page.route(new RegExp(`/api/selection/${FID}$`), (r) => {
      if (r.request().method() === 'PUT') { state.confirm = JSON.parse(r.request().postData()); state.draft = null; return json(r, { status: 'ok', count: state.confirm.players.length }) }
      return json(r, payload)
    })
    await page.route('**/api/availability', (r) => json(r, { status: 'ok' }))
  }
  const names = async (page) => page.locator('[data-drop-kind="slot"] span.truncate.font-semibold').evaluateAll((els) => els.map((e) => e.textContent.trim()))

  console.log('Selection (390px)')
  {
    const { browser, page, errors } = await launch()
    const state = { draft: null, v: 0, confirm: null }
    await stubSelection(page, state)
    await page.goto(`${BASE}/admin/betterselect/select/${FID}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: /Add players/i }).first().waitFor({ timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(500)

    const o = await overflow(page)
    ok('page is not wider than the screen', o.over <= 0, JSON.stringify(o))
    const bar = page.locator('[data-mobile-bar]')
    const bb = await box(bar)
    ok('the bottom bar is pinned to the bottom of the screen', !!bb && Math.abs(bb.y + bb.height - PHONE.height) < 2, JSON.stringify(bb))
    ok('Confirm is in the bar', (await count(bar.getByRole('button', { name: /^confirm/i }))) === 1)
    ok('the header does not carry a second Confirm on a phone', (await page.getByRole('button', { name: /^confirm/i }).filter({ visible: true } ).count().catch(() => 0)) === 1)
    ok('Pool and XI switches are in the bar', (await count(bar.getByRole('tab', { name: /Pool/ }))) === 1 && (await count(bar.getByRole('tab', { name: /XI/ }))) === 1)
    const hb = await box(page.locator('header').first())
    ok('the header is one row, not a tall sticky block', !!hb && hb.height < 80, JSON.stringify(hb))
    await page.screenshot({ path: join(SHOTS, 'selection_xi.png') })

    // Add players: search by words in any order
    await tap(page.locator('[data-open-add]'))
    const sheet = page.locator('[data-testid="add-players-sheet"]')
    ok('Add players opens a sheet', (await count(sheet)) === 1)
    const input = sheet.getByRole('searchbox')
    const fill = (v) => input.fill(v, { timeout: 2000 }).catch(() => {})
    ok('the search box has the keyboard (focused)', await input.evaluate((e) => document.activeElement === e).catch(() => false))
    const sb = await box(sheet.locator('> div'))
    ok('the sheet is wholly on screen', inScreen(sb), JSON.stringify(sb))
    ok('with nothing typed it lists the pool', (await count(sheet.locator('[data-add-row]'))) === 14, `got ${await count(sheet.locator('[data-add-row]'))}`)
    const firstRow = await text(sheet.locator('[data-add-row]'))
    ok('a player the squad above has not picked is listed first, and says so', /Davis, Cal/.test(firstRow) && /Not picked in 3rd XI/.test(firstRow), firstRow.replace(/\s+/g, ' '))
    await fill('jack bar')
    await page.waitForTimeout(150)
    const rows = sheet.locator('[data-add-row]')
    ok('"jack bar" finds "Barendse, Jack"', (await count(rows)) === 1 && /Barendse, Jack/.test(await text(rows)), await rows.allInnerTexts().catch(() => ''))
    await page.screenshot({ path: join(SHOTS, 'selection_add_search.png') })
    await tap(rows.first())
    await page.waitForTimeout(200)
    ok('tapping adds them and the sheet stays open', (await count(sheet)) === 1 && /Barendse, Jack added at 1/.test(await text(sheet.locator('[data-add-note]'))))
    ok('they are gone from the results (already picked)', (await count(rows)) === 0)
    await fill('')
    await tap(sheet.locator('[data-add-row]', { hasText: 'Abbas, Aamir' }))
    await tap(sheet.locator('[data-add-row]', { hasText: 'Barker, David' }))
    await page.waitForTimeout(200)
    ok('the sheet counts what is picked', /3 \/ 11 picked/.test(await text(sheet)), (await text(sheet)).slice(0, 120))
    await tap(sheet.locator('[data-add-done]'))
    await page.waitForTimeout(250)
    ok('Done closes the sheet', (await count(sheet)) === 0)
    ok('the XI is in the order they were added', JSON.stringify((await names(page)).slice(0, 3)) === JSON.stringify(['Barendse, Jack', 'Abbas, Aamir', 'Barker, David']), JSON.stringify(await names(page)))

    // Reorder with the arrows
    const row = (n) => page.locator('[data-drop-kind="slot"]', { hasText: n })
    const cb = await box(row('Barker, David').locator('[data-move-up]'))
    ok('the move buttons are 40px targets', !!cb && cb.width >= 39.5 && cb.height >= 39.5, JSON.stringify(cb))
    await tap(row('Barker, David').locator('[data-move-up]'))
    await page.waitForTimeout(150)
    ok('up moves Barker above Abbas', JSON.stringify((await names(page)).slice(0, 3)) === JSON.stringify(['Barendse, Jack', 'Barker, David', 'Abbas, Aamir']), JSON.stringify(await names(page)))
    await tap(row('Barendse, Jack').locator('[data-move-down]'))
    await page.waitForTimeout(150)
    ok('down moves Barendse below Barker', JSON.stringify((await names(page)).slice(0, 3)) === JSON.stringify(['Barker, David', 'Barendse, Jack', 'Abbas, Aamir']), JSON.stringify(await names(page)))

    // Options sheet: captain
    await tap(row('Barker, David').locator('[data-slot-more]'))
    const ss = page.locator('[data-testid="slot-sheet"]')
    ok('the ••• button opens the options sheet', (await count(ss)) === 1)
    ok('the options sheet is wholly on screen', inScreen(await box(ss.locator('> div'))), JSON.stringify(await box(ss.locator('> div'))))
    await page.screenshot({ path: join(SHOTS, 'selection_slot_sheet.png') })
    await tap(ss.getByRole('button', { name: /Make captain/ }))
    await page.waitForTimeout(200)
    ok('Make captain closes the sheet and tags them C', (await count(ss)) === 0 && (await count(row('Barker, David').getByText('C', { exact: true }))) >= 1)
    await tap(row('Abbas, Aamir').locator('[data-slot-more]'))
    await tap(ss.getByRole('button', { name: /Take out of the XI/ }))
    await page.waitForTimeout(200)
    ok('Take out of the XI removes them', !(await names(page)).includes('Abbas, Aamir'), JSON.stringify(await names(page)))

    // Open slot opens the search too
    const open = page.locator('[data-drop-kind="slot"]', { hasText: 'Tap to add a player' }).first()
    await tap(open)
    ok('tapping an open slot opens the search', (await count(sheet)) === 1)
    await tap(sheet.locator('[data-add-row]', { hasText: 'Ashworth, Shayne' }))
    await tap(sheet.locator('[data-add-done]'))
    await page.waitForTimeout(250)
    ok('and the player lands in that slot', (await names(page)).includes('Ashworth, Shayne'))

    // Pool tab on the bar
    await tap(bar.getByRole('tab', { name: /Pool/ }))
    await page.waitForTimeout(200)
    ok('the Pool tab shows the pool', await page.getByText('Available pool').first().isVisible().catch(() => false))
    await page.screenshot({ path: join(SHOTS, 'selection_pool.png') })
    const firstPool = await text(page.locator('section', { hasText: 'Available pool' }).locator('div.group.relative').first())
    ok('the pool lists him first too, with the label', /Davis, Cal/.test(firstPool) && /Not picked in 3rd XI/.test(firstPool), firstPool.replace(/\s+/g, ' '))
    // The dot sits on the picture. A tap on it (even off to the side, where iOS
    // would have handed it to the avatar link) opens the availability sheet.
    const poolCard = (n) => page.locator('section', { hasText: 'Available pool' }).locator('div.group.relative', { hasText: n }).first()
    await poolCard('Wilson, Sam').scrollIntoViewIfNeeded({ timeout: 2000 }).catch(() => {})
    await page.waitForTimeout(400)
    const dotBox = await box(poolCard('Wilson, Sam').locator('[data-avail-dot]'))
    ok('the dot on the picture is a button of 32px or more', !!dotBox && dotBox.width >= 31.5 && dotBox.height >= 31.5, JSON.stringify(dotBox))
    const urlBefore = page.url()
    if (dotBox) await page.touchscreen.tap(dotBox.x + dotBox.width / 2 - 10, dotBox.y + dotBox.height / 2 - 10)
    await page.waitForTimeout(300)
    const adlg = page.getByRole('dialog', { name: /Update availability/i })
    ok('tapping the dot opens the availability sheet', (await count(adlg)) === 1)
    ok('and does not open the profile or add the player', page.url() === urlBefore && /XI\s*3\/11/.test(await text(bar)), `${page.url()} ${await text(bar)}`)
    await tap(adlg.getByRole('button', { name: 'Maybe' }))
    await page.waitForTimeout(300)
    ok('the pick is saved from the board', (await count(adlg)) === 0)
    await poolCard('Taylor, Max').scrollIntoViewIfNeeded({ timeout: 2000 }).catch(() => {})
    await page.waitForTimeout(400)
    const avBox = await box(poolCard('Taylor, Max').locator('span.relative.shrink-0 > span').first())
    if (avBox) await page.touchscreen.tap(avBox.x + avBox.width / 2, avBox.y + avBox.height / 2 - 4)
    await page.waitForTimeout(300)
    ok('on a phone the picture is not a link to the profile', /\/select\//.test(page.url()), page.url())
    const before = (await text(bar)).replace(/\s+/g, ' ')
    await tap(page.locator('section', { hasText: 'Available pool' }).locator('div.group.relative', { hasText: 'Evans, Zac' }).first())
    await page.waitForTimeout(200)
    const after = (await text(bar)).replace(/\s+/g, ' ')
    ok('tapping a pool card moves the XI count in the bar', before !== after && /XI\s*5\/11/.test(after), `${before} -> ${after}`)

    // Confirm from the bar writes the order on screen
    await tap(bar.getByRole('tab', { name: /XI/ }))
    await page.waitForTimeout(150)
    const shown = await names(page)
    await tap(bar.getByRole('button', { name: /^confirm/i }))
    await page.waitForTimeout(400)
    const sent = (state.confirm?.players || []).map((p) => p.player_id)
    const idByName = Object.fromEntries(pool.map((p) => [p.display_name, p.id]))
    ok('Confirm sends the batting order that is on screen', JSON.stringify(sent) === JSON.stringify(shown.filter((n) => n && idByName[n]).map((n) => idByName[n])), `${JSON.stringify(sent)} vs ${JSON.stringify(shown)}`)
    ok('and the captain', state.confirm?.players?.find((p) => p.is_captain)?.player_id === idByName['Barker, David'])
    ok('no script error', errors.length === 0, errors.join(' | '))
    await browser.close()
  }

  console.log('Players (390px)')
  {
    const { browser, page, errors } = await launch()
    await stubPlayers(page)
    await page.goto(`${BASE}/admin/betterselect/players`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Ashworth, Shayne').first().waitFor({ timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(400)
    const list = page.locator('[data-players-list]'), prof = page.locator('[data-players-profile]')
    ok('page is not wider than the screen', (await overflow(page)).over <= 0)
    ok('a phone opens on the list, not on the first player', (await list.first().isVisible().catch(() => false)) && !(await prof.first().isVisible().catch(() => false)))
    await tap(page.getByText('Ashworth, Shayne').first())
    await page.waitForTimeout(500)
    ok('choosing a player shows their profile in place of the list', (await prof.first().isVisible().catch(() => false)) && !(await list.first().isVisible().catch(() => false)))
    const pb = await box(prof)
    ok('the profile starts at the top of the screen', !!pb && pb.y >= 0 && pb.y < 240, JSON.stringify(pb))
    ok('there is a Back to the list', (await count(page.locator('[data-players-back]'))) === 1)
    await page.screenshot({ path: join(SHOTS, 'players_profile.png') })
    await tap(page.locator('[data-players-back]'))
    await page.waitForTimeout(300)
    ok('Back returns to the list', (await list.first().isVisible().catch(() => false)) && !(await prof.first().isVisible().catch(() => false)))
    await page.goto(`${BASE}/admin/betterselect/players?player=p2`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(800)
    ok('a ?player= link opens straight onto that profile', await prof.first().isVisible().catch(() => false))
    ok('no script error', errors.length === 0, errors.join(' | '))
    await browser.close()
  }

  console.log('Selection (1440px desk layout)')
  {
    const { browser, page, errors } = await launch({ viewport: { width: 1440, height: 1000 }, mobile: false })
    const state = { draft: null, v: 0, confirm: null }
    await stubSelection(page, state)
    await page.goto(`${BASE}/admin/betterselect/select/${FID}`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Abbas, Aamir').first().waitFor({ timeout: 15000 })
    await page.waitForTimeout(400)
    ok('no bottom bar on the desk layout', !(await page.locator('[data-mobile-bar]').first().isVisible().catch(() => false)))
    ok('Confirm is in the header', (await page.getByRole('button', { name: /^confirm/i }).filter({ visible: true }).count()) === 1)
    ok('both columns are showing', (await page.getByRole('heading', { name: 'Available pool' }).isVisible().catch(() => false)) && (await page.getByRole('heading', { name: /Selected XI/ }).isVisible().catch(() => false)))
    ok('the three small slot buttons, not the phone cluster', (await page.locator('[data-slot-phone-controls]').filter({ visible: true }).count()) === 0)
    await page.getByText('Abbas, Aamir').first().click({ timeout: 3000 }).catch(() => {})
    await page.waitForTimeout(250)
    ok('click-to-add still works on the desk', (await names(page)).includes('Abbas, Aamir'))
    ok('the C / WK / remove cluster shows for a picked player', (await page.locator('[data-drop-kind="slot"]', { hasText: 'Abbas, Aamir' }).getByTitle('Captain').filter({ visible: true }).count()) === 1)
    await page.screenshot({ path: join(SHOTS, 'selection_desk.png') })
    ok('no script error', errors.length === 0, errors.join(' | '))
    await browser.close()
  }

  console.log(`\n${PASS} passed, ${FAIL} failed`)
  if (FAIL) { console.log('Failed:\n  ' + FAILURES.join('\n  ')); process.exit(1) }
}
run().catch((e) => { console.error(e); process.exit(2) })
