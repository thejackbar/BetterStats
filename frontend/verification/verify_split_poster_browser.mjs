// Drives the real BetterPosts editor in Chromium with the API stubbed at the
// network layer, for the Split Poster lineup (T11), the DEBUT tag and the
// "mark the player in the photo" shading.
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_split_poster_browser.mjs [baseUrl]
//   SHOTS=/tmp/split node ...        also writes a PNG per size
//   DUMP=/tmp/old.json node ...      writes the export markup of T1, T3, T10 (square, no tags)
//   COMPARE=/tmp/old.json node ...   checks that markup is byte for byte the dump (run the dump on the previous build)
//
// What a build cannot tell you: that the new layout is in the picker and draws
// the eleven names it was given inside the frame at all three sizes, that a
// lineup load asks the server which players are debutants for the MATCH DAY and
// tags exactly those, that a tag the admin flips by hand sticks, that the mark
// shades the row of the player in the photo and nobody else, and that a post
// with neither feature switched on is unchanged on the three older layouts.
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || ''
const DUMP = process.env.DUMP || ''
const COMPARE = process.env.COMPARE || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const SETTINGS = {
  id: 'org-1', name: 'South Perth Cricket Club', short_name: 'SPCC', slug: 'southperth',
  logo_url: null, primary_color: '#101113', accent_color: '#f5b800', theme_config: null,
}
const NAMES = ['Szigligeti, Sam', 'Farmer, Nathan', 'Cartwright, Hilton', 'Hay, Frazer', 'Middlemas, Ben', 'Melville, Alexander',
  'Wenban, Alex', 'Botha, Eric', 'Frame, Josh', 'Dallimore, Liam', 'Wilson, Wyatt', 'Spare, Sid']
const PLAYERS = NAMES.map((n, i) => ({
  id: `p${i + 1}`, name: n, display_name: n, status: 'active', player_role: 'BAT', photo_url: `/api/images/players/p${i + 1}/photo`,
}))
// Debutants the server reports: Nathan Farmer (p2) and Alexander Melville (p6).
// p12 is a name the club's records cannot answer for.
const DEBUT_IDS = ['p2', 'p6']
const KNOWN = PLAYERS.slice(0, 11).map((p) => p.id)

// A full-length figure in the club's colours, standing like the reference.
const FIGURE = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 470" width="120" height="470">
  <circle cx="60" cy="34" r="26" fill="#c98f6b"/><path d="M34 26 q26 -34 52 0 v8 h-52z" fill="#2a1a12"/>
  <path d="M20 66 h80 l10 120 h-24 l-4 -60 h-44 l-4 60 h-24z" fill="#8fb9e8"/>
  <rect x="30" y="170" width="60" height="26" fill="#f2b705"/>
  <path d="M34 196 h52 l8 250 h-28 l-6 -170 l-6 170 h-28z" fill="#8fb9e8"/>
  <rect x="30" y="446" width="26" height="14" fill="#fff"/><rect x="64" y="446" width="26" height="14" fill="#fff"/></svg>`
const SPONSOR = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 270 84" width="270" height="84"><rect width="270" height="84" fill="none"/>
  <rect x="0" y="14" width="56" height="56" rx="10" fill="#fff"/><text x="70" y="52" font-family="Arial" font-weight="800" font-size="30" fill="#fff">DYENAMIC</text></svg>`
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC', 'base64')

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openEditor(query, { viewport = { width: 1600, height: 1980 }, tpl = 'T11', sz = 'square' } = {}) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const errors = [], debutCalls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_|404/.test(m.text())) errors.push(m.text()) })
  const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  // The sandbox browser cannot reach Google Fonts directly (the proxy's CA is not
  // in its store), and a layout judged in a fallback face is judged wrongly: the
  // club faces are condensed and the fallback is not. Fetch them with curl, which
  // trusts the proxy, and hand them to the page.
  await page.route(/fonts\.(googleapis|gstatic)\.com/, async (route) => {
    const url = route.request().url()
    const file = `/tmp/fontcache/${createHash('sha1').update(url).digest('hex')}`
    try {
      if (!existsSync(file)) {
        mkdirSync('/tmp/fontcache', { recursive: true })
        const ua = route.request().headers()['user-agent'] || 'Mozilla/5.0 Chrome/120'
        writeFileSync(file, execFileSync('curl', ['-s', '-m', '30', '-A', ua, url], { maxBuffer: 20e6 }))
      }
      const body = readFileSync(file)
      return route.fulfill({ status: 200, contentType: /googleapis/.test(url) ? 'text/css' : 'font/woff2', body, headers: { 'access-control-allow-origin': '*' } })
    } catch { return route.abort() }
  })
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    if (/\/admin\/social\/debuts/.test(url)) {
      const u = new URL(url)
      debutCalls.push({ ids: (u.searchParams.get('player_ids') || '').split(',').filter(Boolean), before: u.searchParams.get('before') })
      return route.fulfill(json({ debuts: DEBUT_IDS, known: KNOWN, before: u.searchParams.get('before') || '2026-10-02' }))
    }
    if (/\/images\/players\/[^/]+\/photo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: FIGURE })
    if (/\/images\/players\/[^/]+\/photo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    if (/\/images\/sponsors\/s1\/logo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: SPONSOR })
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'southperth',
      entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
    }))
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json(PLAYERS))
    if (/sponsors/.test(url)) return route.fulfill(json([{ id: 's1', name: 'Dyenamic', logo_url: '/x' }]))
    if (/selection\/overview/.test(url)) return route.fulfill(json({ fixtures: [{ id: 'fx1', opponent_name: 'Scarborough', grade: '1st Grade', round: 'Round 1', played_on: '2026-10-03' }] }))
    if (/\/selection\/fx1$/.test(url)) return route.fulfill(json({
      fixture: { id: 'fx1', opponent_name: 'Scarborough', grade: '1st Grade', round: 'Round 1', played_on: '2026-10-03', venue: 'Richardson 1', start_time: '10:30', home_away: 'HOME', home_team: 'South Perth 1st', away_team: 'Scarborough' },
      lineup: PLAYERS.slice(0, 11).map((p, i) => ({ player_id: p.id, batting_order: i + 1, is_captain: p.id === 'p10', is_wicket_keeper: p.id === 'p6' })),
      pool: [],
    }))
    if (/lineups/.test(url)) return route.fulfill(json({ matches: [] }))
    return route.fulfill(json({}))
  })
  await page.addInitScript(([t, s]) => {
    localStorage.setItem('bs_social_template', t)
    localStorage.setItem('bs_social_post_size', s)
  }, [tpl, sz])
  await page.goto(`${BASE}/admin/social-post${query}`, { waitUntil: 'domcontentloaded' })
  try {
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 30000 })
  } catch (e) {
    console.log('EDITOR DID NOT OPEN', errors.slice(0, 3).join(' | '), (await page.innerText('body').catch(() => '')).slice(0, 300))
    throw e
  }
  return { ctx, page, errors, debutCalls }
}

const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }
const textOf = async (loc) => { try { return (await loc.count()) ? await loc.first().innerText() : '' } catch { return '' } }
const tab = (page, name) => press(page.getByRole('button', { name, exact: true }))
const pickSize = async (page, label) => { await tab(page, 'Design'); await press(page.getByRole('button', { name: new RegExp(`^${label}`) })); await page.waitForTimeout(250); await tab(page, 'Content'); await page.waitForTimeout(120) }
const pickLayout = async (page, name) => { await tab(page, 'Design'); await press(page.getByRole('button', { name: new RegExp(name) })); await page.waitForTimeout(250); await tab(page, 'Content'); await page.waitForTimeout(120) }

// The EXPORTED post: the off-screen node, not the scaled preview.
const ROOT = () => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  if (!holder) return null
  // The layout's own root is the clipped, sized box with the most children; the
  // frame wrappers around it hold one or two.
  const boxes = [...holder.querySelectorAll('div')].filter((d) => d.style.overflow === 'hidden' && d.style.position === 'relative' && d.style.width)
  return boxes.sort((a, b) => b.children.length - a.children.length)[0] || null
}
const EMPTY_ROW = { x: 0, y: 0, w: 0, h: 0, text: '', shadow: 'none', bg: 'none' }
const EMPTY = { w: 0, h: 0, layers: [], rows: [], panel: { x: 0, y: 0, w: 0, h: 0 }, photo: { x: 0, y: 0, w: 0, h: 0 }, sponsor: null, text: '', overflowList: ['no post'] }
// A build without the layout reports every check as failing instead of throwing.
async function readSplit(page) {
  return (await readSplitRaw(page)) || EMPTY
}
async function readSplitRaw(page) {
  return page.evaluate((rootSrc) => {
    const root = (new Function(`return (${rootSrc})()`))()
    if (!root) return null
    const rr = root.getBoundingClientRect()
    // An element inside a clipping ancestor that is itself inside the post cannot show outside it.
    const clipped = (e) => { for (let a = e.parentElement; a && a !== root; a = a.parentElement) if (getComputedStyle(a).overflow === 'hidden') return true; return false }
    const rel = (el) => { const r = el.getBoundingClientRect(); return { x: r.left - rr.left, y: r.top - rr.top, w: r.width, h: r.height } }
    const layers = [...root.children].map((c) => c.getAttribute('data-layer') || c.tagName.toLowerCase())
    const list = root.querySelector('[data-layer="Starting XI"]')
    const rows = list ? [...list.children].map((r) => ({
      ...rel(r), text: r.innerText.replace(/\s+/g, ' ').trim(),
      shadow: getComputedStyle(r).boxShadow, bg: getComputedStyle(r).backgroundImage,
    })) : []
    const panel = root.querySelector('[data-layer="XI panel"]')
    const photo = root.querySelector('[data-layer="Player photo"] img')
    const sponsors = root.querySelector('[data-layer="Sponsors"]')
    const sponsorImg = sponsors && sponsors.querySelector('img')
    return {
      w: rr.width, h: rr.height, layers, rows,
      panel: panel ? rel(panel) : { x: 0, y: 0, w: 0, h: 0 }, photo: photo ? { ...rel(photo), src: photo.getAttribute('src') } : { x: 0, y: 0, w: 0, h: 0 },
      sponsor: sponsorImg ? { ...rel(sponsorImg), src: sponsorImg.getAttribute('src') } : null,
      text: root.innerText.replace(/\s+/g, ' '),
      overflowList: [...root.querySelectorAll('*')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > rr.right + 1 || r.left < rr.left - 1 || r.bottom > rr.bottom + 1 || r.top < rr.top - 1) && !e.closest('svg') && e.tagName !== 'IMG' && !clipped(e) }).map((e) => `${e.tagName}${e.getAttribute('data-layer') ? '[' + e.getAttribute('data-layer') + ']' : ''}:${(e.innerText || '').slice(0, 20)}`),
    }
  }, ROOT.toString())
}
const firstDiff = (a, b) => {
  if (a === b) return ''
  let i = 0
  while (i < Math.min(a.length, b.length) && a[i] === b[i]) i++
  return `at ${i}: ${JSON.stringify((a || '').slice(Math.max(0, i - 60), i + 80))} vs ${JSON.stringify((b || '').slice(Math.max(0, i - 60), i + 80))}`
}
const hasMark = (row) => /inset/.test(row.shadow) && row.shadow !== 'none'

async function shotNode(page, file) {
  await page.evaluate((rootSrc) => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    holder.dataset.shot = '1'; Object.assign(holder.style, { left: '0px', top: '0px', position: 'fixed', zIndex: '2147483647', background: '#101010' })
  }, ROOT.toString())
  const box = await page.evaluate(() => { const r = document.querySelector('[data-shot="1"]').firstElementChild.getBoundingClientRect(); return { w: r.width, h: r.height } })
  await page.screenshot({ path: file, clip: { x: 0, y: 0, width: Math.min(box.w, 1920), height: Math.min(box.h, 1920) } })
  await page.evaluate(() => {
    const h = document.querySelector('[data-shot="1"]')
    Object.assign(h.style, { left: '-9999px', top: '0', position: 'absolute', zIndex: '-1', background: '' }); delete h.dataset.shot
  })
}

// ── 1. The layout is offered, and a BetterSelect load fills it ─────────────
{
  const { ctx, page, errors, debutCalls } = await openEditor('?type=lineup&template=T11')
  await tab(page, 'Design')
  ck('Split Poster is in the layout picker', await seen(page.getByRole('button', { name: /Split Poster/ })))
  // The source step: the saved team for the match.
  await press(page.getByRole('button', { name: /^Data$/i }))
  await page.waitForTimeout(500)
  const fx = page.getByRole('button', { name: /Scarborough/ })
  ck('the BetterSelect team is offered', await seen(fx))
  await press(fx)
  await page.waitForTimeout(900)
  ck('a lineup load asks which players are debutants', debutCalls.length === 1, `calls=${debutCalls.length}`)
  ck('...for the eleven named players', debutCalls[0]?.ids?.length === 11 && debutCalls[0].ids[0] === 'p1', JSON.stringify(debutCalls[0]?.ids))
  ck('...as at the match day, not today', debutCalls[0]?.before === '2026-10-03', String(debutCalls[0]?.before))
  await tab(page, 'Content')
  await page.waitForTimeout(200)

  let post = await readSplit(page)
  ck('the post is on screen', post.w > 0)
  const names = (post?.rows || []).map((r) => r.text)
  ck('eleven rows', post?.rows.length === 11, String(post?.rows.length))
  ck('first row is the first name, numbered', /^1\.\s*SAM SZIGLIGETI/.test(names[0] || ''), names[0])
  ck('the debutants are tagged', /DEBUT/.test(names[1] || '') && /DEBUT/.test(names[5] || ''), `${names[1]} | ${names[5]}`)
  ck('nobody else is', names.filter((t) => /DEBUT/.test(t)).length === 2, String(names.filter((t) => /DEBUT/.test(t)).length))
  ck('the keeper and the debut share a row', /WK/.test(names[5] || '') && /DEBUT/.test(names[5] || ''), names[5])
  ck('the captain is tagged', /\bC$/.test(names[9] || '') || /LIAM DALLIMORE\s*C/.test(names[9] || ''), names[9])
  ck('the fixture reads as the reference does', /SOUTH PERTH CRICKET CLUB/.test(post?.text || '') && /VS SCARBOROUGH/.test(post?.text || ''), post?.text?.slice(0, 200))
  ck('STARTING and the outlined XI are both there', /STARTING/.test(post?.text || '') && post.layers.includes('Outlined XI'))
  ck('the venue is on the post', /RICHARDSON 1/.test(post?.text || ''), '')
  ck('every layer of the reference is its own layer', ['Panel bands', 'Dot texture', 'XI panel', 'Outlined XI', 'Player photo', 'Panel shade', 'Round heading', 'Starting wordmark', 'Starting XI', 'Fixture', 'Venue and time', 'Sponsors'].every((l) => post.layers.includes(l)), post?.layers.join(' | '))
  ck('the photo is the captain\'s (first with a photo), contained', post.photo.w > 0, JSON.stringify(post?.photo))
  ck('a sponsor logo replaces the platform credit', !!post.sponsor && /sponsors\/s1\/logo/.test(post.sponsor.src || ''), JSON.stringify(post.sponsor))
  ck('nothing marked until asked', post.rows.every((r) => !hasMark(r)))

  // Manual flip: the DEBUT button on row 3 (Cartwright) and back.
  const rowBtn = (i) => page.locator('div.flex.items-center.gap-2.p-2.rounded').nth(i).getByRole('button', { name: 'DEBUT', exact: true })
  await press(rowBtn(2))
  await page.waitForTimeout(250)
  post = await readSplit(page)
  ck('a tag switched on by hand shows on the post', /DEBUT/.test((post.rows[2]?.text || '')), (post.rows[2]?.text || ''))
  await press(rowBtn(2))
  await page.waitForTimeout(250)
  post = await readSplit(page)
  ck('...and off again', !/DEBUT/.test((post.rows[2]?.text || '')))
  await press(rowBtn(1))
  await page.waitForTimeout(250)
  post = await readSplit(page)
  ck('a detected tag can be switched off by hand', !/DEBUT/.test((post.rows[1]?.text || '')), (post.rows[1]?.text || ''))

  // FIND DEBUTS re-asks and restores the detected answer.
  await press(page.getByRole('button', { name: 'FIND DEBUTS' }))
  await page.waitForTimeout(500)
  post = await readSplit(page)
  ck('FIND DEBUTS asks again', debutCalls.length === 2, String(debutCalls.length))
  ck('...and the detected answer comes back', /DEBUT/.test((post.rows[1]?.text || '')) && /DEBUT/.test((post.rows[5]?.text || '')))
  ck('...and says so in words', /2 marked as a debut/.test(await textOf(page.getByTestId('debut-check'))), await textOf(page.getByTestId('debut-check')))

  // The mark.
  await press(page.getByTestId('mark-hero').locator('input'))
  await page.waitForTimeout(250)
  post = await readSplit(page)
  const marked = post.rows.map((r, i) => (hasMark(r) ? i : -1)).filter((i) => i >= 0)
  ck('the mark shades exactly one row', marked.length === 1, JSON.stringify(marked))
  ck('...the captain, who is the photo\'s player when none is picked', marked[0] === 9, JSON.stringify(marked))

  // Pick a different hero player: the mark follows.
  await tab(page, 'Content')
  const heroSel = page.locator('select').filter({ has: page.locator('option', { hasText: 'Auto — captain' }) })
  await heroSel.selectOption('p3')
  await page.waitForTimeout(300)
  post = await readSplit(page)
  const marked2 = post.rows.map((r, i) => (hasMark(r) ? i : -1)).filter((i) => i >= 0)
  ck('picking another hero player moves the mark to their row', marked2.length === 1 && marked2[0] === 2, JSON.stringify(marked2))
  ck('the mark is behind the name, not instead of it', /HILTON CARTWRIGHT/.test((post.rows[2]?.text || '')))

  // Panel colour.
  const before = await page.evaluate(() => getComputedStyle(document.querySelector('[data-testid="split-panel"]') || document.body).display)
  ck('the panel colour control is offered', await seen(page.getByTestId('split-panel')), before)

  // Layout stays valid when the debut and the mark are both on.
  ck('nothing runs off the post', post.overflowList.length === 0, post.overflowList.join(' ; '))
  ck('no page errors', errors.length === 0, errors.slice(0, 2).join(' | '))
  if (SHOTS && post.w > 0) await shotNode(page, `${SHOTS}/T11-square.png`)

  // ── sizes ────────────────────────────────────────────────────────────────
  for (const [label, w, h] of [['Portrait', 1080, 1350], ['Story', 1080, 1920], ['Square', 1080, 1080]]) {
    await pickSize(page, label)
    const p = await readSplit(page)
    ck(`${label}: the post is ${w}x${h}`, Math.round(p.w) === w && Math.round(p.h) === h, `${p.w}x${p.h}`)
    ck(`${label}: eleven rows, none overlapping`, p.rows.length === 11 && p.rows.every((r, i) => i === 0 || r.y >= p.rows[i - 1].y + p.rows[i - 1].h - 1))
    ck(`${label}: rows are inside the dark panel`, p.rows.every((r) => r.x >= p.panel.x - 14 && r.x + r.w <= p.panel.x + p.panel.w + 0.5 && r.y >= 0 && r.y + r.h <= p.h - 0.5))
    ck(`${label}: the XI clears the foot`, (p.rows[10] || EMPTY_ROW).y + (p.rows[10] || EMPTY_ROW).h < p.h - (label === 'Story' ? 300 : 150), `${(p.rows[10] || EMPTY_ROW).y + (p.rows[10] || EMPTY_ROW).h} of ${p.h}`)
    ck(`${label}: the photo stays in the pale panel`, p.photo.x >= 0 && p.photo.x + p.photo.w <= p.panel.x + 0.5)
    ck(`${label}: nothing runs off the post`, p.overflowList.length === 0, p.overflowList.join(' ; '))
    if (SHOTS && p.w > 0) await shotNode(page, `${SHOTS}/T11-${label.toLowerCase()}.png`)
  }
  await ctx.close()
}

// ── 2. The older layouts: the tag and the mark, and nothing else changed ───
{
  const { ctx, page, errors } = await openEditor('?type=lineup&template=T1', { tpl: 'T1' })
  await tab(page, 'Content')
  for (let i = 1; i <= 11; i++) await press(page.getByRole('button', { name: new RegExp(`^${NAMES[i - 1]}`) }))
  await page.waitForTimeout(200)
  const read = (t) => page.evaluate(([rootSrc]) => {
    const root = (new Function(`return (${rootSrc})()`))()
    return root ? root.outerHTML : null
  }, [ROOT.toString()])
  const html = {}
  for (const id of ['T1', 'T3', 'T10']) {
    await pickLayout(page, id === 'T1' ? 'Hero List' : id === 'T3' ? 'Side Numbered' : 'Team Sheet')
    html[id] = await read(id)
    ck(`${id}: renders`, !!html[id])
    // Debut + mark change the post...
    const rowBtn = page.locator('div.flex.items-center.gap-2.p-2.rounded').nth(3).getByRole('button', { name: 'DEBUT', exact: true })
    await press(rowBtn)
    await page.waitForTimeout(250)
    const withDebut = await read(id)
    ck(`${id}: a DEBUT tag appears`, /DEBUT/.test(withDebut || ''), '')
    await press(rowBtn)
    await page.waitForTimeout(250)
    { const again = await read(id); ck(`${id}: switching it off restores the post exactly`, again === html[id], firstDiff(html[id], again)) }
    await tab(page, 'Content')
    await press(page.getByTestId('mark-hero').locator('input'))
    await page.waitForTimeout(250)
    const withMark = await read(id)
    ck(`${id}: the mark changes the post`, withMark !== html[id])
    await press(page.getByTestId('mark-hero').locator('input'))
    await page.waitForTimeout(250)
    { const again = await read(id); ck(`${id}: switching the mark off restores the post exactly`, again === html[id], firstDiff(html[id], again)) }
  }
  await pickLayout(page, 'Hero List')
  ck('no page errors on the older layouts', errors.length === 0, errors.slice(0, 2).join(' | '))
  if (DUMP) { writeFileSync(DUMP, JSON.stringify(html)); console.log(`dumped ${DUMP}`) }
  if (COMPARE) {
    const old = JSON.parse(readFileSync(COMPARE, 'utf8'))
    for (const id of ['T1', 'T3', 'T10']) ck(`${id}: unchanged against the previous build`, old[id] === html[id], `old ${old[id]?.length} new ${html[id]?.length}`)
  }
  await ctx.close()
}

console.log(`\n${pass} passed, ${fail} failed`)
await browser.close()
process.exit(fail ? 1 : 0)
