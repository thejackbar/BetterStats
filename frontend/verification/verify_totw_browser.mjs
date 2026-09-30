// Drives the real BetterPosts "Team of the Week" post in Chromium with the API
// stubbed at the network layer.
//
//   npx vite build && npx vite preview --port 5198 &
//   node frontend/verification/verify_totw_browser.mjs [baseUrl]
//
// What a build cannot tell you: that the pull asks for the right thing (no `q`
// for the latest round, the pasted link as `q` otherwise), that the team is 11
// by default and moves between 6 and 14 with the stepper, that every one of the
// nine sizes on both layouts puts exactly that many players on the post inside
// the frame with none overlapping, that a player swapped in by hand survives a
// resize, and that a stat line typed in the panel is the one on the post.
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
// Ten of the sixteen ranked players are on the club roster (so their photo
// resolves); the last six are scorecard names with no club record.
const NAMES = ['Star, Sam', 'Ton, Eli', 'Bowler, Bo', 'Guest, Gus', 'Keeper, Fay', 'Catcher, Cy', 'Duck, Dee',
  'Alpha, Al', 'Bravo, Bea', 'Charlie, Chaz', 'Delta, Dom', 'Echo, Ed', 'Foxtrot, Flo', 'Golf, Gil', 'Hotel, Hux', 'India, Ivy']
const PLAYERS = NAMES.slice(0, 10).map((n, i) => ({
  id: `p${i + 1}`, name: n, display_name: n, status: 'active', photo_url: `/api/images/players/p${i + 1}/photo`,
}))
const POOL = NAMES.map((n, i) => {
  const [last, first] = n.split(', ')
  const base = 130 - i * 7
  return {
    first, last, short: `${first[0]}. ${last.toUpperCase()}`, pid: i < 10 ? `p${i + 1}` : null, guid: `g${i + 1}`, points: base,
    batting: i % 3 === 0 ? { r: base - 40, b: 50, notOut: i % 2 === 0, fours: 0, sixes: 0, sr: 100 } : null,
    bowling: i % 3 !== 2 ? { o: '8.0', m: 1, r: 30, w: 2, econ: 3.75 } : null,
    fielding: i % 4 === 0 ? { catches: 2, catches_wk: 0, stumpings: 0, run_outs: 0 } : null,
    grade: i % 2 ? '2ND GRADE' : '1ST GRADE', opp: 'RIVALS CC', oppMono: 'RIV', outcome: 'W',
  }
})
const TOTW = { kind: 'round', season: '2025/26', club: {}, round: 'Round 5', date: '2026-09-26', label: 'SAT 26 SEP', matches: 3, players: POOL }
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC', 'base64')

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openEditor(query, viewport = { width: 1600, height: 1000 }, mobile = false) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const errors = []
  const totwCalls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_/.test(m.text())) errors.push(m.text()) })
  const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    if (/\/admin\/social\/totw/.test(url)) { totwCalls.push(new URL(url).search); return route.fulfill(json(TOTW)) }
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
  // Anchor on the export button, which every build has; a control run on a build
  // without this feature then reports below rather than dying here.
  // (The phone layout is a different, quick-post editor with no such button.)
  if (mobile) await page.waitForFunction(() => document.body.innerText.length > 80, null, { timeout: 25000 })
  else await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  return { ctx, page, errors, totwCalls }
}

// Reads that report absence instead of throwing.
const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }
const textOf = async (loc) => { try { return (await loc.count()) ? await loc.first().innerText() : '' } catch { return '' } }

// The post as it is EXPORTED: the off-screen node, not the scaled preview.
// Returns the layout root and the player cards inside `[data-layer="Players"]`.
async function readPost(page) {
  return page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    const root = holder && [...holder.querySelectorAll('div')].find((d) => d.style.width && d.style.overflow === 'hidden' && d.querySelector('[data-layer="Players"]'))
    if (!root) return null
    const rr = root.getBoundingClientRect()
    const box = root.querySelector('[data-layer="Players"]')
    const br = box.getBoundingClientRect()
    const foot = root.querySelector('[data-layer="Sponsors"]')
    const footTop = foot ? foot.getBoundingClientRect().top - rr.top : rr.height
    const cards = [...box.children].map((c) => { const r = c.getBoundingClientRect(); return { x: r.left - rr.left, y: r.top - rr.top, w: r.width, h: r.height, text: c.innerText } })
    return { w: rr.width, h: rr.height, footTop, body: { x: br.left - rr.left, y: br.top - rr.top, w: br.width, h: br.height }, cards }
  })
}
const overlaps = (cards) => {
  for (let i = 0; i < cards.length; i++) for (let j = i + 1; j < cards.length; j++) {
    const a = cards[i], b = cards[j]
    if (a.x < b.x + b.w - 1 && b.x < a.x + a.w - 1 && a.y < b.y + b.h - 1 && b.y < a.y + a.h - 1) return true
  }
  return false
}
// Inside the post AND clear of the sponsor strip, which a card running into is
// the one thing the post bounds alone cannot see.
const inside = (cards, post) => cards.every((c) => c.x >= -0.5 && c.y >= -0.5 && c.x + c.w <= post.w + 0.5 && c.y + c.h <= Math.min(post.h, post.footTop) + 0.5)

const count = async (page) => Number(await textOf(page.getByTestId('totw-count')))
const stepTo = async (page, n) => {
  for (let guard = 0; guard < 20 && (await count(page)) !== n; guard++) {
    const dir = (await count(page)) < n ? 'More players' : 'Fewer players'
    if (!(await press(page.getByRole('button', { name: dir }).first()))) break
    await page.waitForTimeout(40)
  }
}
// The layout buttons live in the Design panel and read "TW2 Ranked Board ...".
const pickLayout = async (page, name) => {
  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await press(page.getByRole('button', { name: new RegExp(name) }))
  await page.waitForTimeout(120)
  await press(page.getByRole('button', { name: 'Content', exact: true }))
  await page.waitForTimeout(80)
}
const pickSize = async (page, label) => { await press(page.getByRole('button', { name: 'Design', exact: true })); await press(page.getByRole('button', { name: new RegExp(`^${label}`) })); await page.waitForTimeout(150); await press(page.getByRole('button', { name: 'Content', exact: true })); await page.waitForTimeout(100) }

// ── 1. The tab, the pull and the default team ──────────────────────────────
{
  const { ctx, page, errors, totwCalls } = await openEditor('?type=totw')
  const tabs = await page.locator('button').allInnerTexts()
  ck('a Team of the Week post type is offered', tabs.some((t) => /team of the week/i.test(t)))

  // The data step opens first for a data-driven type.
  ck('the data step offers a pull of the latest round', await seen(page.getByRole('button', { name: 'Pull latest round' })))
  await press(page.getByRole('button', { name: 'Pull latest round' }))
  await page.getByTestId('totw-count').first().waitFor({ timeout: 8000 }).catch(() => {})
  ck('the latest round is asked for with no link', totwCalls.length === 1 && totwCalls[0] === '', JSON.stringify(totwCalls))
  ck('the team starts at 11', (await count(page)) === 11, String(await count(page)))

  await press(page.getByRole('button', { name: /Continue to editor/ }))
  await page.waitForTimeout(200)
  const post = await readPost(page)
  ck('the exported post holds 11 players', post?.cards.length === 11, String(post?.cards.length))
  ck('the top performer is first', /STAR/i.test(post?.cards[0]?.text || ''), post?.cards[0]?.text)
  ck('the stat line comes from the scorecard (runs and wickets)', /\(50\)|2\/30/.test(post?.cards[0]?.text || ''), post?.cards[0]?.text)

  // A pasted link names the round: it goes across as `q`, exactly.
  const link = 'https://play.cricket.com.au/match/1df207e1-9a2c-4f10-8d3e-000000000001'
  await page.getByPlaceholder('Match link from play.cricket.com.au').first().fill(link)
  await press(page.getByRole('button', { name: 'Fetch' }).first())
  await page.waitForTimeout(300)
  ck('a pasted link is sent as q', totwCalls.length === 2 && totwCalls[1] === `?q=${encodeURIComponent(link)}`, JSON.stringify(totwCalls))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── 2. Every team size, both layouts, all three post sizes ─────────────────
{
  const { ctx, page, errors } = await openEditor('?type=totw')
  await press(page.getByRole('button', { name: 'Pull latest round' }))
  await page.getByTestId('totw-count').first().waitFor({ timeout: 8000 }).catch(() => {})
  await press(page.getByRole('button', { name: /Continue to editor/ }))
  await page.waitForTimeout(200)

  for (const size of ['Square', 'Portrait', 'Story']) {
    await pickSize(page, size)
    for (const layout of ['Team Sheet', 'Ranked Board']) {
      await pickLayout(page, layout)
      const bad = []
      const first = (await readPost(page))?.cards[0]?.text || ''
      // Prove the layout switched: the sheet numbers its cards '#01', the board '01'.
      if (layout === 'Team Sheet' ? !/^#01/.test(first) : !/^01/.test(first)) bad.push(`layout did not switch (${JSON.stringify(first.slice(0, 12))})`)
      for (let n = 6; n <= 14; n++) {
        await stepTo(page, n)
        await page.waitForTimeout(60)
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
        if (SHOTS && [6, 11, 14].includes(n)) await page.screenshot({ path: `${SHOTS}/${layout.replace(/ /g, '')}-${size}-${n}.png` }).catch(() => {})
      }
      ck(`${layout} at ${size}: 6 to 14 all fit, none overlap`, bad.length === 0, bad.join(' ; '))
    }
  }
  ck('the size steps stop at 6 and 14', await (async () => {
    await stepTo(page, 14)
    const upDisabled = await page.getByRole('button', { name: 'More players' }).first().isDisabled()
    await stepTo(page, 6)
    const downDisabled = await page.getByRole('button', { name: 'Fewer players' }).first().isDisabled()
    return upDisabled && downDisabled
  })())
  ck('no page errors across the sweep', errors.length === 0, errors.slice(0, 3).join(' | '))
  await ctx.close()
}

// ── 3. Editing what is on the post ─────────────────────────────────────────
{
  const { ctx, page } = await openEditor('?type=totw')
  await press(page.getByRole('button', { name: 'Pull latest round' }))
  await page.getByTestId('totw-count').first().waitFor({ timeout: 8000 }).catch(() => {})
  await press(page.getByRole('button', { name: /Continue to editor/ }))
  await page.waitForTimeout(200)

  // A stat line typed in the panel is the one on the post.
  const line = page.getByPlaceholder('87 (54) · 2/22').first()
  await line.fill('101* (60) · 3 ct')
  await page.waitForTimeout(100)
  ck('a typed stat line reaches the post', /101\* \(60\) · 3 ct/.test((await readPost(page))?.cards[0]?.text || ''))

  // Points are hidden until asked for.
  ck('points are not shown by default', !/PTS/.test((await readPost(page))?.cards[0]?.text || ''))
  await press(page.getByLabel('Show points on the post'))
  await page.waitForTimeout(100)
  ck('points show when switched on', /130 PTS/.test((await readPost(page))?.cards[0]?.text || ''), (await readPost(page))?.cards[0]?.text)

  // A player taken off by hand stays off when the team grows, and the next
  // best performer takes the seat instead.
  const before = (await readPost(page)).cards.map((c) => c.text.split('\n').find((t) => /[A-Z]{3}/.test(t)))
  await press(page.locator('[data-testid="totw-section"]').locator('xpath=ancestor::*[1]').getByRole('button', { name: /remove|✕/i }).nth(1))
  await page.waitForTimeout(100)
  const afterRemove = await count(page)
  ck('removing a player by hand moves the team size', afterRemove === 10, String(afterRemove))
  await stepTo(page, 11)
  const names = (await readPost(page)).cards.map((c) => c.text)
  ck('growing back adds the next ranked player, not the one removed',
    names.length === 11 && !names.some((t) => /\bTON\b/i.test(t)) && names.some((t) => /GUEST|KEEPER|CATCHER|DUCK|ALPHA/i.test(t)), names.join(' / ').slice(0, 200))
  ck('the first player is still the top performer', /STAR/i.test(names[0]), names[0])

  // Shrinking and growing again walks the same ranking back down.
  await stepTo(page, 8)
  await stepTo(page, 11)
  const again = (await readPost(page)).cards.map((c) => c.text)
  ck('shrinking then growing restores the same eleven', again.join('|') === names.join('|'), again.map((t) => t.split('\n')[2]).join(','))
  await ctx.close()
}

// ── 4. Mobile: nothing pushes the page sideways at 390px ───────────────────
{
  const { ctx, page } = await openEditor('?type=totw', { width: 390, height: 800 }, true)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', overflow <= 1, String(overflow))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
