// A club's own Player Dashboard modules, the card order and how players pay fees, driven in the real
// screens with the API stubbed at the network layer.
//
// Settings (/admin/player-dashboard): add a link button and assert the exact body on the wire, move a
// card in Card order and assert the posted layout, save fee payment details and assert the body.
// Player page (/playerdash/tok): the club's own cards are drawn in the club's order among the built-in
// sections, a link opens in a new tab and posts one tap, an event shows its countdown, an image banner
// draws its picture, and Fees shows How to pay with the copyable details, the pay-online button and the
// other ways. Both at 390px with no horizontal scroll.
//
//   APP_URL=http://localhost:4173 SHOT_DIR=/tmp/custom node verification/verify_player_dashboard_custom_modules_browser.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
if (SHOT) fs.mkdirSync(SHOT, { recursive: true })
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }
const plus = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const PNG = Buffer.from('89504e470d0a1a0a0000000d4948445200000001000000010806000000' + '1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082', 'hex')

const CATALOGUE = [
  { key: 'cards', label: 'Player Cards', blurb: 'Cards.', enabled: true, blocked: null },
  { key: 'season', label: 'Season dashboard', blurb: 'Season.', enabled: true, blocked: null },
  { key: 'fees', label: 'Fees owing', blurb: 'Fees.', enabled: true, blocked: null },
]

async function settingsScreen(browser) {
  console.log('\nsettings screen')
  const st = {
    custom: [],
    layout: ['availability', 'selection', 'cards', 'fantasy', 'stats', 'voting', 'admin'],
    fees_payment: {},
  }
  const lay = () => st.layout.map((id) => {
    const m = st.custom.find((c) => `custom:${c.id}` === id)
    return m ? { id, type: 'custom', label: m.title, kind_label: 'Link button', emoji: m.emoji, shown: true, note: null }
      : { id, type: 'builtin', label: id[0].toUpperCase() + id.slice(1), shown: id !== 'availability', note: id === 'availability' ? 'Needs BetterSelect.' : null }
  })
  const payload = () => ({
    enabled: true, has_select: false, availability_enabled: false, require_pin: true, show_on_site: true, token: 'tok',
    path: '/playerdash/tok', phone_coverage: { with_phone: 1, total: 1 }, registration_enabled: true, registrations_pending: 0,
    dashboard_modules: CATALOGUE, custom_modules: st.custom,
    custom_kinds: [{ key: 'link', label: 'Link button' }, { key: 'text', label: 'Announcement' }, { key: 'event', label: 'Event' }, { key: 'image', label: 'Image banner' }],
    layout: lay(), fees_payment: st.fees_payment,
  })
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 1000 } })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
    localStorage.setItem('bs_clubhouse_intro_mode_anon', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  page.setDefaultTimeout(10000)
  const errors = [], calls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const req = route.request(), url = new URL(req.url()), method = req.method()
    if (/\/auth\/me/.test(url.pathname)) return json(route, { id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc', entitlements: { modules: [], status: 'active' } })
    const path = url.pathname.replace(/^\/api/, '')
    if (!/^\/player-dashboard\//.test(path)) return json(route, {})
    const body = req.postData() ? JSON.parse(req.postData()) : null
    calls.push({ method, path, body, search: url.search })
    if (method === 'POST' && path === '/player-dashboard/custom-modules') {
      const id = `m${st.custom.length + 1}`
      st.custom.push({ ...body, id, kind_label: 'Link button', click_count: 0, live: true, hidden_reason: null, enabled: body.enabled !== false })
      st.layout.push(`custom:${id}`)
      return json(route, { ...payload(), created_id: id })
    }
    if (method === 'POST' && path === '/player-dashboard/settings') {
      if (body.layout) st.layout = body.layout
      if (body.fees_payment) st.fees_payment = Object.fromEntries(Object.entries(body.fees_payment).filter(([, v]) => v))
    }
    return json(route, payload())
  })
  const lastPost = (p) => calls.filter((c) => c.method !== 'GET' && c.path === p).pop()

  await page.goto(`${BASE}/admin/player-dashboard`)
  await page.locator('[data-custom-modules]').waitFor({ timeout: 20000 })

  await safe('add a link button', async () => {
    check('the empty state says there are none yet', (await page.locator('[data-custom-empty]').count()) === 1)
    await page.locator('[data-add-custom]').click()
    await page.locator('[data-custom-form] [data-field="title"]').fill('Presentation night tickets')
    await page.locator('[data-custom-form] [data-field="emoji"]').fill('🎟️')
    await page.locator('[data-custom-form] [data-field="url"]').fill('tix.example.com/pn')
    await page.locator('[data-custom-form] [data-field="button_label"]').fill('Buy tickets')
    await page.locator('[data-custom-form] [data-field="show_until"]').fill(plus(20))
    await page.getByRole('button', { name: 'Add module' }).click()
    await page.locator('[data-custom-row="m1"]').waitFor()
    const b = lastPost('/player-dashboard/custom-modules')?.body || {}
    check('the create posts what was typed, blanks as null',
      b.kind === 'link' && b.title === 'Presentation night tickets' && b.url === 'tix.example.com/pn' && b.emoji === '🎟️' &&
      b.button_label === 'Buy tickets' && b.show_until === plus(20) && b.show_from === null && b.event_date === null && b.enabled === true, JSON.stringify(b))
    check('the create carries the browser timezone', /tz=/.test(calls.filter((c) => c.path === '/player-dashboard/custom-modules').pop()?.search || ''))
    check('the row shows its tap count', /0 taps/.test(await page.locator('[data-custom-row="m1"]').innerText()))
  })

  await safe('the image kind asks to save before uploading', async () => {
    await page.locator('[data-add-custom]').click()
    await page.locator('[data-kind-option="image"]').click()
    check('an image banner offers no upload until it is saved', /Save first, then upload the image/.test(await page.locator('[data-custom-form]').innerText()))
    await page.getByRole('button', { name: 'Cancel' }).click()
  })

  await safe('card order', async () => {
    const rows = await page.locator('[data-layout-row]').evaluateAll((els) => els.map((e) => e.getAttribute('data-layout-row')))
    check('the new module is last in Card order', rows[rows.length - 1] === 'custom:m1', rows.join(','))
    check('a card that is not showing says why', /Not showing\. Needs BetterSelect/.test(await page.locator('[data-layout-row="availability"]').innerText()))
    await page.getByRole('button', { name: 'Move Presentation night tickets up' }).click()
    await page.waitForTimeout(200)
    const b = lastPost('/player-dashboard/settings')?.body || {}
    check('moving it up posts only the whole order, swapped',
      JSON.stringify(Object.keys(b)) === '["layout"]' && b.layout[b.layout.length - 2] === 'custom:m1' && b.layout[b.layout.length - 1] === 'admin', JSON.stringify(b))
  })

  await safe('fee payment details', async () => {
    const save = page.locator('[data-save-fees-payment]')
    check('Save is off until something changes', await save.isDisabled())
    await page.locator('[data-pay-field="bsb"]').fill('062-000')
    await page.locator('[data-pay-field="account_number"]').fill('1234 5678')
    await page.locator('[data-pay-field="account_name"]').fill('Gisborne CC')
    await page.locator('[data-pay-field="pay_online_url"]').fill('https://club.teamapp.com/pay')
    await page.locator('[data-pay-field="other_instructions"]').fill('Cash at the bar on Saturdays.')
    await save.click()
    await page.waitForTimeout(200)
    const b = lastPost('/player-dashboard/settings')?.body || {}
    check('saving posts the payment details and nothing else',
      JSON.stringify(Object.keys(b)) === '["fees_payment"]' && b.fees_payment.bsb === '062-000' && b.fees_payment.account_number === '1234 5678' &&
      b.fees_payment.pay_online_url === 'https://club.teamapp.com/pay' && b.fees_payment.other_instructions === 'Cash at the bar on Saturdays.', JSON.stringify(b))
    check('Save is off again once saved', await save.isDisabled())
  })

  if (SHOT) await page.screenshot({ path: `${SHOT}/settings-desktop.png`, fullPage: true })
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(300)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  check('the settings screen has no horizontal scroll at 390px', over <= 0, `overflow ${over}px`)
  if (SHOT) await page.screenshot({ path: `${SHOT}/settings-390.png`, fullPage: true })
  check('no page errors on the settings screen', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

async function playerPage(browser) {
  console.log('\nplayer page')
  const club = { name: 'Gisborne CC', logo_url: null, accent_color: null, primary_color: null, slug: 'gisborne' }
  const me = { club, player: { id: 'p1', display_name: 'Jack Barendse' }, has_availability: false, dates: [], availability: {}, squads: [] }
  const profile = {
    club: {}, player: { id: 'p1', display_name: 'Jack Barendse' }, modules: ['season', 'fees'], squads: [], squads_visible: false,
    selected: [], training: { upcoming: [], attended_8_weeks: 0, last_attended: null },
    season: { season: '2026/27', matches: 3, runs: 120, wickets: 4, catches: 1, batting: {}, bowling: {}, fielding: {}, form: { batting: [], bowling: [] } },
    fees: { on_record: true, season: '2026/27', total_outstanding: 150, membership_outstanding: 150, match_fee_outstanding: 0, total_paid: 50, credit: 0, payments: [],
      how_to_pay: { account_name: 'Gisborne CC', bsb: '062-000', account_number: '1234 5678', reference_hint: 'Your surname', pay_online_url: 'https://club.teamapp.com/pay', pay_online_label: 'Pay on TeamApp', other_instructions: 'Cash at the bar on Saturdays.' } },
    has_availability: false,
    custom_modules: [
      { id: 'c1', kind: 'link', title: 'Club merch', body: 'Hoodies are in.', url: 'https://shop.example.com', button_label: 'Shop now', emoji: '👕', image_url: null },
      { id: 'c2', kind: 'event', title: 'Presentation night', body: null, url: 'https://tix.example.com', button_label: null, emoji: '🏆', location: 'Clubrooms', event_date: plus(12), event_time: '19:00', image_url: null },
      { id: 'c3', kind: 'image', title: 'Merch poster', body: null, url: null, image_url: '/api/images/player-dashboard-modules/c3?v=1' },
    ],
    layout: ['custom:c1', 'stats', 'custom:c2', 'admin', 'custom:c3'],
  }
  const ctx = await browser.newContext({ viewport: { width: 1000, height: 900 } })
  await ctx.addInitScript(() => { try { localStorage.setItem('bs.playerpage.open', JSON.stringify({ admin: true })) } catch (e) { /* none */ } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(8000)
  const errors = [], clicks = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route(/\/api\/images\/player-dashboard-modules\/c3/, (r) => r.fulfill({ status: 200, contentType: 'image/png', body: PNG }))
  await page.route(/\/api\/public\/availability\/tok\/me\/profile(\?.*)?$/, (r) => json(r, profile))
  await page.route(/\/api\/public\/availability\/tok\/me\/custom\/[^/]+\/click$/, (r) => { clicks.push(r.request().url()); return json(r, { counted: true }) })
  await page.route(/\/api\/public\/availability\/tok\/me(\?.*)?$/, (r) => json(r, me))
  await page.route(/\/api\/public\/availability\/tok$/, (r) => json(r, { club, require_pin: true, has_availability: false, players: [{ id: 'p1', display_name: 'Jack Barendse', has_phone: true }] }))
  // A tapped link opens a new tab; answer it locally so nothing leaves the sandbox.
  await ctx.route(/shop\.example\.com|tix\.example\.com|teamapp\.com/, (r) => r.fulfill({ status: 200, contentType: 'text/html', body: 'ok' }))

  await page.goto(`${BASE}/playerdash/tok`)
  await page.locator('[data-custom-card]').first().waitFor({ timeout: 20000 })

  await safe('order and content', async () => {
    const order = await page.locator('[data-groups] > section').evaluateAll((els) => els.map((e) => e.getAttribute('data-group')))
    check('the grid follows the club\'s order, its own cards among the sections', JSON.stringify(order) === JSON.stringify(['custom:c1', 'stats', 'custom:c2', 'admin', 'custom:c3']), order.join(','))
    const merch = page.locator('[data-group="custom:c1"]')
    check('a link card shows its icon, title, text and button', /Club merch/.test(await merch.innerText()) && /Hoodies are in/.test(await merch.innerText()) && /Shop now/.test(await merch.innerText()))
    const a = merch.locator('a[data-custom-link]')
    check('the link opens in a new tab, safely', (await a.getAttribute('target')) === '_blank' && /noopener/.test(await a.getAttribute('rel') || '') && (await a.getAttribute('href')) === 'https://shop.example.com')
    const ev = page.locator('[data-group="custom:c2"]')
    check('an event shows its countdown', (await ev.locator('[data-custom-countdown]').innerText()) === 'In 12 days')
    check('an event shows its time and place', /7pm/.test(await ev.locator('[data-custom-when]').innerText()) && /Clubrooms/.test(await ev.locator('[data-custom-when]').innerText()))
    check('an event with no button text says Get tickets', /Get tickets/.test(await ev.innerText()))
    const img = page.locator('[data-group="custom:c3"] img')
    await page.waitForFunction(() => { const i = document.querySelector('[data-group="custom:c3"] img'); return i && i.complete && i.naturalWidth > 0 })
    check('an image banner draws its picture with the title as alt text', (await img.getAttribute('alt')) === 'Merch poster')
    check('the custom cards are not collapsible sections', (await page.locator('[data-group="custom:c1"] [data-group-toggle]').count()) === 0)
  })

  await safe('a tap is counted', async () => {
    const [popup] = await Promise.all([page.waitForEvent('popup'), page.locator('[data-group="custom:c1"] a[data-custom-link]').click()])
    await page.waitForTimeout(300)
    check('tapping the link opens it', /shop\.example\.com/.test(popup.url()), popup.url())
    check('and posts exactly one tap for that card', clicks.length === 1 && /\/me\/custom\/c1\/click$/.test(clicks[0]), clicks.join(','))
    await popup.close()
  })

  await safe('fees: how to pay', async () => {
    const box = page.locator('[data-fees-how-to-pay]')
    const t = await box.innerText()
    check('Fees shows the bank details to copy', /062-000/.test(t) && /1234 5678/.test(t) && /Gisborne CC/.test(t) && /Your surname/.test(t), t)
    check('and a pay-online button with the club\'s label', (await box.locator('[data-fees-pay-online]').innerText()).includes('Pay on TeamApp') && (await box.locator('[data-fees-pay-online]').getAttribute('target')) === '_blank')
    check('and the other ways to pay', /Cash at the bar on Saturdays/.test(await box.locator('[data-fees-other]').innerText()))
  })

  if (SHOT) await page.screenshot({ path: `${SHOT}/player-desktop.png`, fullPage: true })
  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(300)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  check('the player page has no horizontal scroll at 390px', over <= 0, `overflow ${over}px`)
  if (SHOT) await page.screenshot({ path: `${SHOT}/player-390.png`, fullPage: true })
  check('no page errors on the player page', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
try {
  await settingsScreen(browser)
  await playerPage(browser)
} finally {
  await browser.close()
}
console.log(`\n${PASS} passed, ${FAIL} failed`)
process.exit(FAIL ? 1 : 0)
