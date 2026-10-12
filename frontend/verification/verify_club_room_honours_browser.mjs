// Club Room Mode "Honour Boards" slide, driven in Chromium against the REAL screens
// with the API stubbed at the network layer. The fixture is the shipped backend's
// own output (backend/verification/verify_club_room_honours.py writes it when
// CLUB_ROOM_FIXTURE is set), so the screens read the real payload shape.
//
//   Admin  "Honour Boards" is in the Add to playlist list; adding it sends
//          slide_type 'honours' with the default config; the editor offers the
//          three sources; the board picker lists the club's boards, the group
//          picker lists the office-bearer groups; Save writes exactly the choice
//   Stage  the public /room/:token show renders a board, a premiership squad and
//          an office-bearer role from that payload; a long board scrolls itself
//   Phone  390px: neither the editor nor the stage is wider than the screen
//
//   npx vite preview --outDir dist --port 5199 &   then   node verify_club_room_honours_browser.mjs
import { readFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { launch, overflow, json, BASE, PHONE, ME } from './mobile_harness.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
mkdirSync(SHOTS, { recursive: true })
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures/club_room_honours.json'), 'utf8'))

let PASS = 0, FAIL = 0
const ok = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const section = async (name, fn) => {
  console.log(name)
  try { await fn() } catch (e) { ok(`${name}: ran to the end`, false, String(e.message).split('\n')[0]) }
}
const DESKTOP = { width: 1920, height: 1080 }
const ME_CLUB = { ...ME, club_id: 'o1', club_slug: 'shoalwater', club_name: 'Shoalwater Bay CC' }

async function adminPage(opts) {
  const h = await launch(opts)
  const { page } = h
  page.setDefaultTimeout(5000)
  const writes = []
  page.on('request', (rq) => {
    if (['POST', 'PATCH'].includes(rq.method()) && /club-room\/slides/.test(rq.url())) {
      writes.push({ method: rq.method(), url: rq.url(), body: JSON.parse(rq.postData() || 'null') })
    }
  })
  await page.route('**/api/auth/me', (r) => json(r, ME_CLUB))
  await page.route('**/api/club-admin/club-room/settings', (r) =>
    json(r, { enabled: true, rotation_seconds: 15, theme: 'dark', shuffle: false, slides: [] }))
  await page.route('**/api/club-admin/club-room/honour-sources', (r) => json(r, FIX.sources))
  await page.route('**/api/club-admin/club-room/public-link', (r) => json(r, { enabled: false, require_pin: true, has_pin: false, link_token: null }))
  await page.route(/\/api\/club-admin\/club-room\/media/, (r) => json(r, []))
  await page.route('**/api/club-admin/club-room/reports', (r) => json(r, []))
  await page.route(/\/api\/club-admin\/(sponsors|seasons)$/, (r) => json(r, []))
  await page.route('**/api/club-admin/club-room/slides', (r) => {
    const body = JSON.parse(r.request().postData() || '{}')
    return json(r, { id: 'sl1', slide_type: body.slide_type, title: null, config: body.config, duration_seconds: null, position: 0, enabled: true }, 201)
  })
  await page.route('**/api/club-admin/club-room/slides/sl1', (r) => {
    const body = JSON.parse(r.request().postData() || '{}')
    return json(r, { id: 'sl1', slide_type: 'honours', title: body.title, config: body.config, duration_seconds: null, position: 0, enabled: true })
  })
  return { ...h, writes }
}

async function stagePage(opts, play) {
  play.enabled = true // the fixture club has not switched Club Room Mode on
  const h = await launch(opts)
  h.page.setDefaultTimeout(5000)
  await h.page.route('**/api/public/club-room/tok', (r) => json(r, { unlocked: true, club_name: 'Shoalwater Bay CC' }))
  await h.page.route('**/api/public/club-room/tok/play', (r) => json(r, play))
  return h
}

const run = async () => {
  await section('Admin (desktop)', async () => {
    const { browser, page, writes, errors } = await adminPage({ viewport: { width: 1280, height: 1000 }, mobile: false })
    await page.goto(`${BASE}/admin/club-room`, { waitUntil: 'domcontentloaded' })
    const add = page.getByRole('button', { name: /\+ Honour Boards/ })
    await add.waitFor({ timeout: 15000 })
    ok('"Honour Boards" is offered under Add to playlist', await add.count() === 1)
    ok('its blurb names the three sources', /premiership squads/i.test(await add.innerText()) && /office bearers/i.test(await add.innerText()))

    await add.click()
    await page.getByText('What to show').first().waitFor()
    ok('adding it sends slide_type honours with the default config',
      writes.length === 1 && writes[0].method === 'POST' && writes[0].body.slide_type === 'honours'
      && writes[0].body.config.kind === 'boards', JSON.stringify(writes))

    const kind = page.locator('select').filter({ has: page.locator('option', { hasText: 'Premiership squads' }) }).first()
    const kindOpts = await kind.locator('option').allInnerTexts()
    ok('the editor offers our boards, premiership squads, and office bearers',
      JSON.stringify(kindOpts) === JSON.stringify(['Our honour boards', 'Premiership squads', 'Office bearers and life members']), JSON.stringify(kindOpts))

    const boardSel = page.locator('select').filter({ has: page.locator('option', { hasText: 'All boards, one after another' }) })
    const boardOpts = await boardSel.locator('option').allInnerTexts()
    ok('the board picker lists the club\'s own boards after "all"',
      JSON.stringify(boardOpts) === JSON.stringify(['All boards, one after another', ...FIX.sources.boards.map((b) => b.title)]), JSON.stringify(boardOpts))

    await kind.selectOption('premierships')
    ok('premierships has no board or group picker', await boardSel.count() === 0
      && await page.locator('option', { hasText: 'Every group' }).count() === 0)

    await kind.selectOption('office_bearers')
    const groupSel = page.locator('select').filter({ has: page.locator('option', { hasText: 'Every group' }) })
    const groupOpts = await groupSel.locator('option').allInnerTexts()
    ok('office bearers offers every group the club has',
      JSON.stringify(groupOpts) === JSON.stringify(['Every group', ...FIX.sources.groups]), JSON.stringify(groupOpts))
    await groupSel.selectOption('Life Members')

    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByText(/office bearers/i).first().waitFor().catch(() => {})
    const patch = writes.find((w) => w.method === 'PATCH')
    ok('Save writes exactly the choice made', patch && patch.body.config.kind === 'office_bearers'
      && patch.body.config.group === 'Life Members', JSON.stringify(patch))
    ok('the playlist row says what it will show', (await page.getByText('Honour Boards · Life Members').count()) > 0)
    ok('no page errors', errors.length === 0, errors.join(' | '))
    await page.screenshot({ path: join(SHOTS, 'club-room-honours-admin.png'), fullPage: true })
    await browser.close()
  })

  await section('Admin (phone)', async () => {
    const { browser, page } = await adminPage({})
    await page.goto(`${BASE}/admin/club-room`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: /\+ Honour Boards/ }).click()
    await page.getByText('What to show').first().waitFor()
    const o = await overflow(page)
    ok('the editor is no wider than a 390px screen', o.over <= 1, JSON.stringify(o))
    await page.screenshot({ path: join(SHOTS, 'club-room-honours-admin-390.png'), fullPage: true })
    await browser.close()
  })

  await section('Stage (TV)', async () => {
    const play = structuredClone(FIX.play)
    play.slides.forEach((s) => { s.duration_seconds = 600 })
    const { browser, page, errors } = await stagePage({ viewport: DESKTOP, mobile: false }, play)
    await page.goto(`${BASE}/room/tok`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Batting Honour Roll').first().waitFor({ timeout: 15000 })

    const text = async () => (await page.locator('body').innerText()).replace(/\s+/g, ' ')
    let t = await text()
    ok('the first board shows its title, description, names, years and details',
      /Batting Honour Roll/.test(t) && /Centuries for the club/.test(t) && /Sam Shaw/.test(t)
      && /2019/.test(t) && /142 v Rivals/.test(t) && /Old Timer/.test(t), t.slice(0, 300))
    ok('the eyebrow names it an honour board (CSS uppercases it)', /HONOUR BOARD/.test(t))
    const cols = await page.evaluate(() => [...document.querySelectorAll('div')].find((d) => d.style.columnCount)?.style.columnCount)
    ok('the board lays out in its own two columns', cols === '2', String(cols))
    await page.screenshot({ path: join(SHOTS, 'club-room-honours-board.png') })

    await page.keyboard.press('ArrowRight')
    await page.getByText('Hall of Fame').first().waitFor()
    ok('the next slide is the award-category board with its detail', /Hana Hill/.test(await text()) && /services to the club/.test(await text()))

    await page.keyboard.press('ArrowRight')
    await page.getByText('2019/20 · 1st XI').first().waitFor()
    t = await text()
    ok('a premiership slide shows the flag, competition and squad with parts played',
      /PREMIERS/.test(t) && /A Grade Premiership/.test(t) && /Wes West · Captain/.test(t) && /Xavi Xu · Player of the Match/.test(t) && /Yan Yu/.test(t), t.slice(0, 400))
    await page.screenshot({ path: join(SHOTS, 'club-room-honours-premiers.png') })

    await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight')
    await page.getByText('President', { exact: true }).first().waitFor()
    t = await text()
    ok('an office-bearer slide shows the role, its group and who held it when',
      /EXECUTIVE COMMITTEE/.test(t) && /Rob Reed/.test(t) && /2018/.test(t) && /Pat Price/.test(t) && /2010/.test(t), t.slice(0, 400))
    await page.screenshot({ path: join(SHOTS, 'club-room-honours-office.png') })
    ok('no page errors', errors.length === 0, errors.join(' | '))
    await browser.close()
  })

  await section('Stage: a long board scrolls itself', async () => {
    const play = structuredClone(FIX.play)
    const long = play.slides.find((s) => s.title === 'Batting Honour Roll')
    long.entries = Array.from({ length: 60 }, (_, i) => ({ label: String(2025 - i), name: `Player Number ${i + 1}`, detail: null }))
    long.columns = 1
    play.slides = [{ ...long, duration_seconds: 600 }]
    const { browser, page } = await stagePage({ viewport: DESKTOP, mobile: false }, play)
    await page.goto(`${BASE}/room/tok`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Player Number 1', { exact: true }).waitFor({ timeout: 15000 })
    const scroller = page.locator('.club-room-scroll').first()
    const before = await scroller.evaluate((el) => el.scrollTop)
    await page.waitForTimeout(5000)
    const after = await scroller.evaluate((el) => el.scrollTop)
    const room = await scroller.evaluate((el) => el.scrollHeight - el.clientHeight)
    ok('the list is taller than its box (so scrolling is needed)', room > 100, String(room))
    ok('it starts at the top and has moved down after a few seconds', before === 0 && after > 0, `${before} -> ${after}`)
    await browser.close()
  })

  await section('Stage (phone)', async () => {
    const play = structuredClone(FIX.play)
    play.slides.forEach((s) => { s.duration_seconds = 600 })
    const { browser, page } = await stagePage({}, play)
    await page.goto(`${BASE}/room/tok`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Batting Honour Roll').first().waitFor({ timeout: 15000 })
    const o = await overflow(page)
    ok('the stage is no wider than a 390px screen', o.over <= 1, JSON.stringify(o))
    await page.screenshot({ path: join(SHOTS, 'club-room-honours-board-390.png') })
    await browser.close()
  })

  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}

run()
