// Drives the real BetterPosts "Milestones" post in Chromium with the API stubbed
// at the network layer.
//
//   npx vite build && npx vite preview --port 5198 &
//   node frontend/verification/verify_milestones_browser.mjs [baseUrl]
//
// What a build cannot tell you: that the club's milestone report is asked for once,
// that the newest dated milestones are ticked to begin with (and an old or undated
// one is not), that unticking a milestone takes THAT player off the post and
// ticking another puts them on, that the window changes what the picker lists
// without losing a tick, that the post stops at twelve, and that every count from
// one to twelve fits both layouts at all three post sizes with no card overlapping.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const SETTINGS = {
  id: 'org-1', name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'applecross',
  logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null,
}
const NAMES = ['Star, Sam', 'Ton, Eli', 'Bowler, Bo', 'Guest, Gus', 'Keeper, Fay', 'Catcher, Cy', 'Duck, Dee',
  'Alpha, Al', 'Bravo, Bea', 'Charlie, Chaz', 'Delta, Dom', 'Echo, Ed', 'Foxtrot, Flo', 'Golf, Gil']
const PLAYERS = NAMES.map((n, i) => ({
  id: `p${i + 1}`, name: n, display_name: n, status: 'active', photo_url: i < 8 ? `/api/images/players/p${i + 1}/photo` : null,
}))
const dayAgo = (n) => {
  const d = new Date(); d.setDate(d.getDate() - n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
// Six in the last 30 days, three 31 to 80 days ago, one over a year ago, two with
// no date (three). Types cover every unit the post words.
const TYPES = ['runs', 'wickets', 'matches', 'catches', 'runs', 'wickets']
const ACHIEVED = [
  ...[2, 5, 9, 14, 21, 27].map((n, i) => ({ player_id: `p${i + 1}`, player_name: NAMES[i], type: TYPES[i], milestone_value: [1000, 50, 100, 25, 3000, 100][i], achieved_at: dayAgo(n), detail: null })),
  ...[40, 55, 80].map((n, i) => ({ player_id: `p${i + 7}`, player_name: NAMES[i + 6], type: 'runs', milestone_value: 500, achieved_at: dayAgo(n), detail: null })),
  { player_id: 'p10', player_name: NAMES[9], type: 'wickets', milestone_value: 200, achieved_at: dayAgo(400), detail: null },
  { player_id: 'p11', player_name: NAMES[10], type: 'grade_matches', milestone_value: 100, achieved_at: null, detail: '1ST GRADE' },
  { player_id: 'p12', player_name: NAMES[11], type: 'grade_matches', milestone_value: 50, achieved_at: null, detail: '2ND GRADE' },
  { player_id: 'p13', player_name: NAMES[12], type: 'catches', milestone_value: 25, achieved_at: null, detail: null },
]
const REPORT = { upcoming: [], achieved: ACHIEVED, scheme: { runs_step: 1000, wickets_step: 100 }, scheme_options: { runs_steps: [250, 500, 1000], wickets_steps: [25, 50, 100] } }
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC', 'base64')

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openEditor(query, viewport = { width: 1600, height: 1000 }, mobile = false) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  page.setDefaultTimeout(4000)
  const errors = []
  const reportCalls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_/.test(m.text())) errors.push(m.text()) })
  const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    if (/\/club-admin\/milestones/.test(url)) { reportCalls.push(url); return route.fulfill(json(REPORT)) }
    if (/\/images\/players\/[^/]+\/photo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross',
      entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
    }))
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json(PLAYERS))
    if (/sponsors/.test(url)) return route.fulfill(json([]))
    if (/selection\/overview/.test(url)) return route.fulfill(json({ fixtures: [] }))
    if (/lineups/.test(url)) return route.fulfill(json({ matches: [] }))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/social-post${query}`, { waitUntil: 'domcontentloaded' })
  if (mobile) await page.waitForFunction(() => document.body.innerText.length > 80, null, { timeout: 25000 })
  else await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  return { ctx, page, errors, reportCalls }
}

// Reads that report absence instead of throwing.
const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const fillIn = async (loc, v) => { try { await loc.first().fill(v, { timeout: 2500 }) } catch { /* reported by the check */ } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }
const textOf = async (loc) => { try { return (await loc.count()) ? await loc.first().innerText() : '' } catch { return '' } }

// The post as it is EXPORTED: the off-screen node, not the scaled preview.
async function readPost(page) {
  return page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    const root = holder && [...holder.querySelectorAll('div')].find((d) => d.style.width && d.style.overflow === 'hidden' && d.querySelector('[data-layer="Milestones"]'))
    if (!root) return null
    const rr = root.getBoundingClientRect()
    const box = root.querySelector('[data-layer="Milestones"]')
    const br = box.getBoundingClientRect()
    const foot = root.querySelector('[data-layer="Sponsors"]')
    const footTop = foot ? foot.getBoundingClientRect().top - rr.top : rr.height
    const cards = [...box.children].map((c) => { const r = c.getBoundingClientRect(); return { x: r.left - rr.left, y: r.top - rr.top, w: r.width, h: r.height, text: c.innerText } })
    const head = root.querySelector('[data-layer="Masthead"]')
    return { w: rr.width, h: rr.height, footTop, body: { x: br.left - rr.left, y: br.top - rr.top, w: br.width, h: br.height }, cards, head: head ? head.innerText : '' }
  })
}
const overlaps = (cards) => {
  for (let i = 0; i < cards.length; i++) for (let j = i + 1; j < cards.length; j++) {
    const a = cards[i], b = cards[j]
    if (a.x < b.x + b.w - 1 && b.x < a.x + a.w - 1 && a.y < b.y + b.h - 1 && b.y < a.y + a.h - 1) return true
  }
  return false
}
const inside = (cards, post) => cards.every((c) => c.x >= -0.5 && c.y >= -0.5 && c.x + c.w <= post.w + 0.5 && c.y + c.h <= Math.min(post.h, post.footTop) + 0.5)

const rows = (page) => page.getByTestId('milestone-row')
const tickedCount = async (page) => Number(((await textOf(page.getByTestId('milestone-count'))).match(/^(\d+)/) || [])[1])
const rowFor = (page, name) => rows(page).filter({ hasText: name })
const isTicked = async (page, name) => { try { return await rowFor(page, name).first().locator('input').isChecked() } catch { return null } }
const pickWindow = async (page, label) => { await press(page.getByRole('button', { name: label, exact: true })); await page.waitForTimeout(100) }
const pickLayout = async (page, name) => {
  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await press(page.getByRole('button', { name: new RegExp(name) }))
  await page.waitForTimeout(120)
  await press(page.getByRole('button', { name: 'Content', exact: true }))
  await page.waitForTimeout(80)
}
const pickSize = async (page, label) => { await press(page.getByRole('button', { name: 'Design', exact: true })); await press(page.getByRole('button', { name: new RegExp(`^${label}`) })); await page.waitForTimeout(150); await press(page.getByRole('button', { name: 'Content', exact: true })); await page.waitForTimeout(100) }
// Set the ticks to exactly `n` rows of the "All time" list.
const tickExactly = async (page, n) => {
  await pickWindow(page, 'All time')
  await press(page.getByRole('button', { name: 'Untick all' }))
  for (let i = 0; i < n; i++) await rows(page).nth(i).locator('input').check().catch(() => {})
  await page.waitForTimeout(100)
}

// ── 1. The tab, the report and what is ticked to begin with ────────────────
{
  const { ctx, page, errors, reportCalls } = await openEditor('?type=milestones')
  const tabs = await page.locator('button').allInnerTexts()
  ck('a Milestones post type is offered', tabs.some((t) => /^milestones$/i.test(t.trim())))
  await page.getByTestId('milestone-picker').first().waitFor({ timeout: 8000 }).catch(() => {})
  ck('the data step shows the milestone picker', await seen(page.getByTestId('milestone-picker')))
  ck('the club milestone report is asked for once', reportCalls.length === 1, String(reportCalls.length))
  ck('the picker lists only the last 30 days to begin with', (await rows(page).count()) === 6, String(await rows(page).count()))
  ck('all six are ticked to begin with', (await tickedCount(page)) === 6, String(await tickedCount(page)))

  await press(page.getByRole('button', { name: /Continue to editor/ }))
  await page.waitForTimeout(250)
  const post = await readPost(page)
  ck('the exported post holds the six', post?.cards.length === 6, String(post?.cards.length))
  ck('the newest is first', /STAR/i.test(post?.cards[0]?.text || ''), post?.cards[0]?.text)
  ck('a runs milestone reads with a thousands separator and its unit', /1,000/.test(post?.cards[0]?.text || '') && /CAREER RUNS/i.test(post?.cards[0]?.text || ''), post?.cards[0]?.text)
  ck('a wickets milestone is worded as wickets', /CAREER WICKETS/i.test(post?.cards[1]?.text || ''), post?.cards[1]?.text)
  ck('the masthead says MILESTONES', /MILESTONES/i.test(post?.head || ''), post?.head)

  // Unticking takes that player off and nobody else.
  const target = await textOf(rows(page).nth(1))
  await rows(page).nth(1).locator('input').uncheck().catch(() => {})
  await page.waitForTimeout(150)
  const after = await readPost(page)
  ck('unticking one removes one card', after?.cards.length === 5, String(after?.cards.length))
  ck('the player unticked is the one gone', !/TON/i.test((after?.cards || []).map((c) => c.text).join(' ')) && /STAR/i.test(after?.cards[0]?.text || ''), (after?.cards || []).map((c) => c.text.split('\n')[0]).join(','))
  ck('the count in the picker follows', (await tickedCount(page)) === 5, String(await tickedCount(page)))
  void target

  // An older one is not on the post until it is ticked.
  await pickWindow(page, 'Last 90 days')
  ck('a longer window lists more', (await rows(page).count()) === 9, String(await rows(page).count()))
  ck('an older milestone is not ticked by being listed', (await isTicked(page, 'Alpha, Al')) === false)
  await rowFor(page, 'Alpha, Al').first().locator('input').check().catch(() => {})
  await page.waitForTimeout(150)
  const more = await readPost(page)
  ck('ticking an older one adds it to the post, last', more?.cards.length === 6 && /ALPHA/i.test(more.cards[5]?.text || ''), (more?.cards || []).map((c) => c.text.split('\n')[0]).join(','))

  // The window only narrows the list: a tick survives a change of window.
  await pickWindow(page, 'Last 14 days')
  ck('a shorter window lists fewer', (await rows(page).count()) === 4, String(await rows(page).count()))
  ck('the post keeps its ticks through a change of window', (await readPost(page))?.cards.length === 6)
  ck('the count still says six', (await tickedCount(page)) === 6, String(await tickedCount(page)))

  // All time includes the undated ones; narrower windows never show them.
  ck('undated milestones are not in a dated window', (await rowFor(page, 'Delta, Dom').count()) === 0)
  await pickWindow(page, 'All time')
  ck('all time lists all thirteen, undated included', (await rows(page).count()) === 13, String(await rows(page).count()))
  ck('an undated row says so', /no date/i.test(await textOf(rowFor(page, 'Delta, Dom'))), await textOf(rowFor(page, 'Delta, Dom')))
  ck('an undated grade milestone reads in its grade', /Games in 1ST GRADE/.test(await textOf(rowFor(page, 'Delta, Dom'))), await textOf(rowFor(page, 'Delta, Dom')))

  // Search narrows by name.
  await fillIn(page.getByPlaceholder('Search a player'), 'keeper')
  await page.waitForTimeout(100)
  ck('search finds a player by name', (await rows(page).count()) === 1 && /Keeper/.test(await textOf(rows(page))), String(await rows(page).count()))
  await fillIn(page.getByPlaceholder('Search a player'), 'nobody here')
  await page.waitForTimeout(100)
  ck('a search with no match says so', await seen(page.getByTestId('milestone-empty')))
  await fillIn(page.getByPlaceholder('Search a player'), '')
  await page.waitForTimeout(100)

  // The heading and the date line are the club's to change.
  await fillIn(page.getByPlaceholder('MILESTONES'), 'Big night')
  await page.waitForTimeout(150)
  ck('a typed heading reaches the post', /BIG NIGHT/i.test((await readPost(page))?.head || ''), (await readPost(page))?.head)
  ck('dates are on the post by default', /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/i.test((await readPost(page))?.cards[0]?.text || ''), (await readPost(page))?.cards[0]?.text)
  await press(page.getByLabel('Show the date each was reached'))
  await page.waitForTimeout(150)
  ck('dates come off when switched off', !/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/i.test((await readPost(page))?.cards[0]?.text || ''), (await readPost(page))?.cards[0]?.text)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── 2. The post stops at twelve ────────────────────────────────────────────
{
  const { ctx, page } = await openEditor('?type=milestones')
  await page.getByTestId('milestone-picker').first().waitFor({ timeout: 8000 }).catch(() => {})
  await pickWindow(page, 'All time')
  await press(page.getByRole('button', { name: 'Untick all' }))
  await press(page.getByRole('button', { name: 'Tick shown' }))
  await page.waitForTimeout(100)
  ck('ticking everything stops at twelve', (await tickedCount(page)) === 12, String(await tickedCount(page)))
  ck('the thirteenth cannot be ticked, the twelve can still be unticked', (await rows(page).locator('input:disabled').count()) === 1, String(await rows(page).locator('input:disabled').count()))
  ck('the full post says so', /holds 12 milestones/i.test(await textOf(page.getByTestId('milestone-picker'))))
  await rows(page).nth(0).locator('input').uncheck().catch(() => {})
  await page.waitForTimeout(100)
  ck('unticking one makes room again', (await rows(page).locator('input:disabled').count()) === 0 && (await tickedCount(page)) === 11, String(await tickedCount(page)))
  await ctx.close()
}

// ── 3. Every count, both layouts, all three post sizes ─────────────────────
{
  const { ctx, page, errors } = await openEditor('?type=milestones')
  await page.getByTestId('milestone-picker').first().waitFor({ timeout: 8000 }).catch(() => {})
  await press(page.getByRole('button', { name: /Continue to editor/ }))
  await page.waitForTimeout(200)
  for (const size of ['Square', 'Portrait', 'Story']) {
    await pickSize(page, size)
    for (const layout of ['Milestone Cards', 'Milestone Board']) {
      await pickLayout(page, layout)
      const bad = []
      for (let n = 1; n <= 12; n++) {
        await tickExactly(page, n)
        const post = await readPost(page)
        const problems = []
        if (!post) problems.push('no post')
        else {
          if (post.cards.length !== n) problems.push(`${post.cards.length} cards`)
          if (!inside(post.cards, post)) problems.push('a card outside the post')
          if (overlaps(post.cards)) problems.push('cards overlap')
          if (post.cards.some((c) => c.h < 40 || c.w < 100)) problems.push('a card is squashed')
        }
        if (problems.length) bad.push(`${n}: ${problems.join(', ')}`)
        if (SHOTS && [1, 2, 5, 12].includes(n)) await page.screenshot({ path: `${SHOTS}/${layout.replace(/ /g, '')}-${size}-${n}.png` }).catch(() => {})
      }
      ck(`${layout} at ${size}: 1 to 12 all fit, none overlap`, bad.length === 0, bad.join(' ; '))
    }
  }
  ck('no page errors across the sweep', errors.length === 0, errors.slice(0, 3).join(' | '))
  await ctx.close()
}

// ── 4. Nothing ticked says what to do ──────────────────────────────────────
{
  const { ctx, page } = await openEditor('?type=milestones')
  await page.getByTestId('milestone-picker').first().waitFor({ timeout: 8000 }).catch(() => {})
  await press(page.getByRole('button', { name: 'Untick all' }))
  await press(page.getByRole('button', { name: /Continue to editor/ }))
  await page.waitForTimeout(200)
  const post = await readPost(page)
  ck('an empty post says to tick milestones', /TICK THE MILESTONES/i.test(post?.cards[0]?.text || ''), post?.cards[0]?.text)
  await ctx.close()
}

// ── 5. The phone quick-post: pick, untick, choose the layout ──────────────
{
  const { ctx, page, errors, reportCalls } = await openEditor('?type=milestones', { width: 390, height: 800 }, true)
  await page.getByTestId('milestone-picker').first().waitFor({ timeout: 8000 }).catch(() => {})
  ck('the phone quick-post offers the milestone picker', await seen(page.getByTestId('quick-extra')) && await seen(page.getByTestId('milestone-picker')))
  ck('it asks the club report once', reportCalls.length === 1, String(reportCalls.length))
  // The preview is drawn in the page: read the layer that holds the cards.
  const cards = () => page.evaluate(() => {
    const box = document.querySelector('[data-layer="Milestones"]')
    return box ? [...box.children].map((c) => c.innerText) : null
  })
  ck('the preview holds the six ticked to begin with', (await cards())?.length === 6, String((await cards())?.length))
  ck('the count says six', (await tickedCount(page)) === 6, String(await tickedCount(page)))
  const heights = await rows(page).evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height))
  ck('every row is a finger-sized target (44px or more)', heights.length > 0 && heights.every((h) => h >= 44), JSON.stringify(heights))
  const boxes = await rows(page).locator('input').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().width))
  ck('the tick box is big enough to hit', boxes.length > 0 && boxes.every((w) => w >= 20), JSON.stringify(boxes))
  await rows(page).nth(1).locator('input').uncheck().catch(() => {})
  await page.waitForTimeout(200)
  ck('unticking on the phone takes that player off the preview', (await cards())?.length === 5 && !/TON/i.test((await cards() || []).join(' ')), JSON.stringify(await cards()))
  await press(page.getByRole('button', { name: 'Milestone Board', exact: true }))
  await page.waitForTimeout(200)
  ck('the layout can be switched on the phone', await page.getByRole('button', { name: 'Milestone Board', exact: true }).first().getAttribute('aria-pressed').catch(() => null) === 'true' && (await cards())?.length === 5)
  ck('the board is the layout showing', await page.evaluate(() => !!document.querySelector('[data-layer="Milestones"]') && getComputedStyle(document.querySelector('[data-layer="Milestones"]')).flexDirection === 'column'))
  await fillIn(page.getByPlaceholder('MILESTONES'), 'Big night')
  await page.waitForTimeout(200)
  ck('a heading typed on the phone reaches the preview', await page.evaluate(() => /BIG NIGHT/i.test(document.querySelector('[data-layer="Masthead"]')?.innerText || '')))
  await press(page.getByRole('button', { name: 'All time', exact: true }))
  await page.waitForTimeout(150)
  ck('the window works on the phone', (await rows(page).count()) === 13, String(await rows(page).count()))
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px with the picker open', overflow <= 1, String(overflow))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/phone-milestones.png`, fullPage: false }).catch(() => {})
  ck('no page errors on the phone', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── 6. Mobile: nothing pushes the page sideways at 390px ───────────────────
{
  const { ctx, page } = await openEditor('?type=milestones', { width: 390, height: 800 }, true)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', overflow <= 1, String(overflow))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
