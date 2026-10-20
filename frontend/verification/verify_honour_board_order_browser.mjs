// A club's own Honour Board order (migration 324), driven in Chromium against the
// REAL screens with the API stubbed at the network layer. The two fixtures are
// the shipped backend's own output (see backend/verification/verify_honour_board_layout.py),
// so the screens read the real payload shape.
//
//   Admin    Award types has a second tab, "Honour Board order"; it opens on the
//            standard order with Save off; the arrows move groups, roles and
//            people; oldest / newest only let people who share a season swap;
//            Manual lets anybody move; Save writes exactly the order on screen
//            and leaves boards nobody touched out of the request; Reset sends
//            an empty layout
//   Public   a club with a saved layout shows Life Members first and Allan
//            Godfrey first, and says the order is the club's own; a club with
//            none shows the standard order and no note
//   Phone    390px: neither screen is wider than the screen, and the arrow
//            buttons are at least 32px
//
//   npx vite preview --outDir dist --port 5199 &   then   node verify_honour_board_order_browser.mjs
import { readFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { launch, overflow, json, BASE, PHONE, ME } from './mobile_harness.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
mkdirSync(SHOTS, { recursive: true })
const STD = JSON.parse(readFileSync(join(HERE, 'fixtures/honour_board_standard.json'), 'utf8'))
const SAVED = JSON.parse(readFileSync(join(HERE, 'fixtures/honour_board_saved.json'), 'utf8'))

let PASS = 0, FAIL = 0
const FAILURES = []
const ok = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(label); console.log(`  FAIL ${label}  ${detail}`) }
}
const count = (loc) => loc.count().catch(() => 0)
const box = (loc) => loc.first().boundingBox({ timeout: 1500 }).catch(() => null)

const ME_CLUB = { ...ME, club_id: 'o1', club_slug: 'shoalwater', club_name: 'Shoalwater Bay CC' }
const DESKTOP = { width: 1400, height: 1000 }

async function adminPage(opts) {
  const h = await launch(opts)
  const { page } = h
  page.setDefaultTimeout(4000)
  const writes = []
  let layoutView = STD
  page.on('request', (rq) => {
    if (rq.method() === 'PUT' && /honour-board-layout/.test(rq.url())) writes.push({ url: rq.url(), body: JSON.parse(rq.postData() || 'null') })
  })
  await page.route('**/api/auth/me', (r) => json(r, ME_CLUB))
  await page.route('**/api/club-admin/settings', (r) => json(r, { id: 'o1', name: 'Shoalwater Bay CC', slug: 'shoalwater' }))
  await page.route(/\/api\/award-definitions\?/, (r) => json(r, [
    { id: 'd1', org_id: 'o1', category: 'Life Membership', subcategory: 'Club', achievement: 'Life Membership', display_name: null, sort_order: 1, active: true },
  ]))
  await page.route('**/api/club-admin/honour-board-layout', (r) => {
    if (r.request().method() === 'PUT') {
      const body = JSON.parse(r.request().postData() || '{}')
      const empty = !(body.groups || []).length && !Object.keys(body.roles || {}).length && !Object.keys(body.holders || {}).length
      layoutView = empty ? STD : SAVED.admin
      return json(r, layoutView)
    }
    return json(r, layoutView)
  })
  return { ...h, writes }
}

const groupNames = (page) => page.locator('section[aria-labelledby="hbo-groups"] > div > div:first-child span.truncate').allInnerTexts()
const personRows = (page) => page.locator('section[aria-labelledby="hbo-people"] div.rounded.border.mb-1\\.5')
const rowTexts = async (page) => (await personRows(page).allInnerTexts()).map((t) => t.replace(/\s+/g, ' ').trim())
const pick = async (page, text) => {
  const value = await page.locator('#hbo-board option', { hasText: text }).first().getAttribute('value')
  await page.locator('#hbo-board').selectOption(value)
}

// A section that cannot finish (a control run against code without the feature has
// no tab to click) is reported as a failure and the run carries on.
const section = async (name, fn) => {
  console.log(name)
  try { await fn() } catch (e) { ok(`${name}: ran to the end`, false, String(e.message).split('\n')[0]) }
}

const run = async () => {
  await section('Admin (desktop)', async () => {
    const { browser, page, errors, writes } = await adminPage({ viewport: DESKTOP, mobile: false })
    await page.goto(`${BASE}/admin/award-definitions?tab=honour-order`, { waitUntil: 'domcontentloaded' })
    await page.getByText('1 · Groups and roles').first().waitFor({ timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(300)

    const tabs = page.getByRole('tab')
    ok('the page has an Award types tab and an Honour Board order tab', (await count(tabs)) === 2
      && (await tabs.nth(1).innerText()) === 'Honour Board order')
    ok('the Honour Board order tab is the selected one', (await tabs.nth(1).getAttribute('aria-selected')) === 'true')

    const std = STD.groups.map((g) => g.group)
    const first = await groupNames(page)
    ok('it opens on the standard order the server sent', JSON.stringify(first) === JSON.stringify(std), JSON.stringify(first))
    ok('Life Members is not first in the standard order (so moving it is a real change)', first[0] !== 'Life Members')
    const save = page.getByRole('button', { name: 'Save order' })
    ok('Save is off until something changes', await save.isDisabled())
    ok('Reset is off for a club that has not customised', await page.getByRole('button', { name: 'Reset to standard order' }).isDisabled())

    // Move Life Members to the top with its own up arrow.
    for (let i = 0; i < first.length; i++) {
      const up = page.getByRole('button', { name: 'Move Life Members up' })
      if (await up.isDisabled()) break
      await up.click()
    }
    const moved = await groupNames(page)
    ok('Life Members moves to the first group', moved[0] === 'Life Members', JSON.stringify(moved))
    ok('the groups it passed keep their order', JSON.stringify(moved.slice(1)) === JSON.stringify(first.filter((g) => g !== 'Life Members')))
    ok('Save is on once something changes', await save.isEnabled())
    ok('an unsaved-changes note is shown', (await page.getByText('not saved yet').count()) > 0)

    // A role arrow moves one role inside its group.
    const execRoles = STD.groups.find((g) => g.group === 'Executive Committee').boards.map((b) => b.role)
    await page.getByRole('button', { name: `Move ${execRoles[2]} up` }).click()
    await save.click()
    await page.getByText('Saved.').first().waitFor({ timeout: 5000 }).catch(() => {})
    ok('Save sends one PUT', writes.length === 1, JSON.stringify(writes))
    const w1 = writes[0]?.body || {}
    ok('the request carries the group order on screen', w1.groups?.[0] === 'Life Members' && w1.groups.length === first.length, JSON.stringify(w1.groups))
    const wantRoles = [execRoles[0], execRoles[2], execRoles[1]]
    ok('the request carries the moved role order', JSON.stringify(w1.roles?.['Executive Committee']) === JSON.stringify(wantRoles), JSON.stringify(w1.roles?.['Executive Committee']))
    ok('boards nobody touched are left out of the request (they stay standard)', JSON.stringify(w1.holders) === '{}', JSON.stringify(w1.holders))
    ok('after Save the screen says so, and Save goes off again', (await page.getByText('Saved.').count()) > 0 && (await save.isDisabled()))
    ok('after Save, Reset is on', await page.getByRole('button', { name: 'Reset to standard order' }).isEnabled())

    // People under Life Membership.
    await pick(page, 'Life Members: Life Membership')
    await page.waitForTimeout(150)
    const standardRows = await rowTexts(page)
    ok('the people are listed with their season', standardRows.length >= 8 && standardRows.some((t) => /^1985 Allan Godfrey/.test(t)), JSON.stringify(standardRows.slice(0, 3)))
    // The stub answers the first Save with the saved layout (Manual, Godfrey first),
    // so this is the screen reading back what the server says it holds.
    ok('after a save the board shows the server\'s saved sort (Manual, Godfrey first)',
      (await page.getByRole('button', { name: 'Manual' }).getAttribute('aria-pressed')) === 'true' && /Godfrey/.test(standardRows[0]), standardRows[0])
    await page.getByRole('button', { name: 'Newest first' }).click()
    const newest = await rowTexts(page)
    ok('newest first puts the latest season on top and Godfrey (1985) well down', /^2024 /.test(newest[0]) && !/Godfrey/.test(newest[0]), newest[0])

    await page.getByRole('button', { name: 'Oldest first' }).click()
    const oldest = await rowTexts(page)
    ok('oldest first puts the earliest season on top', /^1978 /.test(oldest[0]), oldest[0])
    ok('oldest first puts Godfrey (1985) second, not first', /Allan Godfrey/.test(oldest[1]), oldest[1])
    const enabled = await page.locator('section[aria-labelledby="hbo-people"] button:not([disabled])[aria-label^="Move"]').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')))
    ok('only the two people who share a season can swap (2003): one arrow each', enabled.length === 2 && enabled.some((l) => /down$/.test(l)) && enabled.some((l) => /up$/.test(l)), JSON.stringify(enabled))
    const downLabel = enabled.find((l) => /down$/.test(l))
    const swapA = downLabel.replace(/^Move (.*) down$/, '$1')
    await page.getByRole('button', { name: downLabel }).click()
    const afterSwap = await rowTexts(page)
    const ia = afterSwap.findIndex((t) => t.includes(swapA))
    ok('a swap moves that person below the other one on their season', ia > 0 && /^2003 /.test(afterSwap[ia]) && /^2003 /.test(afterSwap[ia - 1]), JSON.stringify(afterSwap))

    // Manual: anybody can move, so Godfrey can go to the top.
    await page.getByRole('button', { name: 'Manual' }).click()
    for (let i = 0; i < 20; i++) {
      const up = page.getByRole('button', { name: 'Move Allan Godfrey up' })
      if (await up.isDisabled()) break
      await up.click()
    }
    const manual = await rowTexts(page)
    ok('Manual: Allan Godfrey is first', /Allan Godfrey/.test(manual[0]), manual[0])
    await page.screenshot({ path: join(SHOTS, 'honour_order_desktop.png') })
    await save.click()
    await page.getByText('Saved.').first().waitFor({ timeout: 5000 }).catch(() => {})
    const w2 = writes[1]?.body || {}
    const cfg = w2.holders?.['Life Members']?.['Life Membership']
    ok('the second Save sends the manual order for that one board', cfg?.sort === 'manual' && cfg.order?.[0] === SAVED.godfrey_key, JSON.stringify(cfg?.order?.slice(0, 2)))
    ok('only that board is in holders', Object.keys(w2.holders || {}).length === 1 && Object.keys(w2.holders['Life Members']).length === 1, JSON.stringify(Object.keys(w2.holders || {})))

    // Reset.
    await page.getByRole('button', { name: 'Reset to standard order' }).click()
    await page.getByText('Back to the standard order.').first().waitFor({ timeout: 5000 }).catch(() => {})
    const w3 = writes[2]?.body
    ok('Reset sends an empty layout', w3 && JSON.stringify(w3) === '{}', JSON.stringify(w3))
    ok('after Reset the groups are back in the standard order', JSON.stringify(await groupNames(page)) === JSON.stringify(std))

    // The other tab still works.
    await page.getByRole('tab', { name: 'Award types' }).click()
    await page.getByText('Award Definitions').first().waitFor({ timeout: 5000 }).catch(() => {})
    ok('the Award types tab still shows the award definitions', (await page.getByText('Award Definitions').count()) > 0 && (await page.getByText('ACHIEVEMENT (STORED VALUE)').count()) > 0)
    ok('no script error', errors.length === 0, errors.join(' | '))
    await browser.close()
  })

  await section('Admin (390px)', async () => {
    const { browser, page, errors } = await adminPage({ viewport: PHONE, mobile: true })
    await page.goto(`${BASE}/admin/award-definitions?tab=honour-order`, { waitUntil: 'domcontentloaded' })
    await page.getByText('1 · Groups and roles').first().waitFor({ timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(300)
    const o = await overflow(page)
    ok('the screen is not wider than the phone', o.over <= 0, JSON.stringify(o))
    const arrow = await box(page.getByRole('button', { name: 'Move Life Members down' }))
    ok('arrow buttons are at least 32px square', !!arrow && arrow.width >= 31.5 && arrow.height >= 31.5, JSON.stringify(arrow))
    await page.screenshot({ path: join(SHOTS, 'honour_order_phone.png'), fullPage: true })
    ok('no script error', errors.length === 0, errors.join(' | '))
    await browser.close()
  })

  console.log('Public Honour Board')
  for (const [label, view, wantFirst, wantNote] of [
    ['a club with a saved layout', SAVED.public, 'Life Members', true],
    ['a club with no layout', { groups: STD.groups }, STD.groups[0].group, false],
  ]) {
    for (const [vp, mobile] of [[DESKTOP, false], [PHONE, true]]) {
      const { browser, page, errors } = await launch({ viewport: vp, mobile })
      await page.route('**/api/clubs/shoalwater', (r) => json(r, { id: 'o1', slug: 'shoalwater', name: 'Shoalwater Bay CC', is_active: true }))
      await page.route('**/api/honours/o1/office-bearers', (r) => json(r, view))
      await page.goto(`${BASE}/shoalwater/honour-board`, { waitUntil: 'domcontentloaded' })
      await page.locator('table').first().waitFor({ timeout: 15000 }).catch(() => {})
      await page.waitForTimeout(250)
      const tag = `${label}, ${mobile ? '390px' : 'desktop'}`
      const heading = (await page.locator('thead').first().innerText().catch(() => '')) || ''
      const names = await page.locator('tbody tr td:first-child').allInnerTexts()
      const head = await page.getByText(/people|person/).first().innerText().catch(() => '')
      if (wantNote) {
        ok(`${tag}: the first board is Life Membership, Allan Godfrey first`, /Awarded/i.test(heading) && /Godfrey/.test(names[0] || ''), JSON.stringify(names.slice(0, 2)))
        ok(`${tag}: says the order is the club's own`, /club.s order/.test(head), head)
        if (!mobile) {
          const rail = await page.locator('nav.pb-card').first().innerText()
          ok(`${tag}: the rail starts with Life Members`, /^LIFE MEMBERS/i.test(rail.trim()), rail.slice(0, 40))
          await page.screenshot({ path: join(SHOTS, 'honour_public_saved.png') })
        }
      } else {
        ok(`${tag}: the first board is the standard first group, with no order note`, !/club.s order|oldest first/.test(head) && !/Godfrey/.test(names[0] || ''), head)
      }
      if (mobile) {
        const o = await overflow(page)
        ok(`${tag}: not wider than the phone`, o.over <= 0, JSON.stringify(o))
      }
      ok(`${tag}: no script error`, errors.length === 0, errors.join(' | '))
      await browser.close()
    }
  }

  console.log(`\n${PASS} passed, ${FAIL} failed`)
  if (FAIL) { console.log('FAILED:\n  - ' + FAILURES.join('\n  - ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
