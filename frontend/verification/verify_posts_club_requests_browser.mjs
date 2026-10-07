// Drives the real BetterPosts editor in Chromium with the API stubbed at the
// network layer, for the club's requests of v9.106.37:
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_posts_club_requests_browser.mjs [baseUrl]
//   SHOTS=/tmp/club node ...        also writes a PNG per layout and size
//
//  1. Player rows: C, VC, WK and DEBUT stay inside the Players panel (and at
//     390px), where before they ran out over the design.
//  2. A roster role of "All Rounder" arrives as AR (the select and the card's
//     icon), where before every real role fell through to BAT.
//  3. Headline: the Match Day Card prints it; a layout with no title says so.
//  4. A player added by hand: the club's players are checked first (the match is
//     offered), the choice is honoured on the wire (no POST when "that's them",
//     one POST with the role when "add as new"), and the photo is uploaded.
//  5. The event poster is kept as it is typed (reload finds it), and saved event
//     templates are listed under Start from an example.
//  6. The three event list layouts draw every event at all three sizes, inside
//     the frame, with the calendar lighting the right days.
//  7. Icon search: results come back, picking one stores its SVG on the post (an
//     event, and a block on the blank canvas), and a failed search says so.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const person = (id, name, role, skills = []) => ({ id, name, display_name: name, status: 'active', player_role: role, skill_positions: skills, photo_url: null })
const PLAYERS = [
  person('p1', 'Abbey, Jayden', 'Batter', ['BAT']),
  person('p2', 'Abbey, Nate', 'Bowler', ['BWL']),
  person('p3', 'Abbey, Robert', 'Batter', ['BAT']),
  person('p4', 'North, Ash', 'All Rounder', ['ALL']),
  person('p5', 'Smith, Steven', 'All Rounder', ['ALL']),
]
const SVG = (c) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="${c}"/></svg>`
const PIC = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100"><rect width="100" height="100" fill="#556b8d"/></svg>`

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

// `similar` is what the similar-players route answers; `iconFail` makes the icon
// search return a 502 so the error path is on screen.
async function openEditor({ type = 'lineup', template = 'T12', viewport = { width: 1600, height: 1980 }, size = 'square', local = {}, similar = [], iconFail = false, templates = [], keepStorage = null } = {}) {
  const ctx = keepStorage ? await browser.newContext({ viewport, storageState: keepStorage }) : await browser.newContext({ viewport })
  const page = await ctx.newPage()
  page.setDefaultTimeout(6000)
  const log = { errors: [], created: [], similarAsked: [], photos: [], puts: [], uploads: [], iconSearches: [] }
  page.on('pageerror', (e) => log.errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_|404|502|Failed to load resource/.test(m.text())) log.errors.push(m.text()) })
  const json = (body, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const settings = { id: 'org-1', name: 'Secret Harbour Dockers CC', short_name: 'SHDCC', slug: 'shdcc', logo_url: '/x', primary_color: '#4b2a8a', accent_color: '#6b3fc4', theme_config: null, socials_style: null }
  const roster = [...PLAYERS]
  const stored = [...templates]
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (route) => route.abort())
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = req.url()
    const m = req.method()
    const img = (body) => route.fulfill({ status: 200, contentType: 'image/svg+xml', body })
    if (/\/images\//.test(url)) return img(PIC)
    if (/\/auth\/me/.test(url)) return route.fulfill(json({ id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'shdcc', entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' } }))
    if (/\/admin\/social\/icons\/search/.test(url)) {
      const q = new URL(url).searchParams.get('q')
      log.iconSearches.push(q)
      if (iconFail) return route.fulfill(json({ detail: 'The icon library did not answer. Try again in a moment.' }, 502))
      if (/nothing/.test(q)) return route.fulfill(json({ icons: [], total: 0 }))
      return route.fulfill(json({ icons: [{ id: 'noto:jack-o-lantern', name: 'jack o lantern', set: 'Noto Emoji', coloured: true }, { id: 'lucide:ghost', name: 'ghost', set: 'Lucide', coloured: false }], total: 2 }))
    }
    if (/\/admin\/social\/icons\/svg/.test(url)) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: SVG(/lucide/.test(url) ? '#222' : '#e8731a') })
    if (/\/admin\/social\/templates\/import/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/templates\/([^/?]+)/.test(url)) {
      const key = url.match(/templates\/([^/?]+)/)[1]
      if (m === 'PUT') { const body = JSON.parse(req.postData() || '{}'); log.puts.push(body); stored.unshift({ ...body, key, updated_at: new Date().toISOString() }); return route.fulfill(json({ ...body, key })) }
      return route.fulfill(json({}))
    }
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json(stored))
    if (/\/admin\/social\/media/.test(url)) {
      if (m === 'POST') { log.uploads.push(true); const n = log.uploads.length; return route.fulfill(json({ id: `up${n}`, name: `up${n}.png`, url: `/api/images/social-media/up${n}?v=1`, kind: null })) }
      return route.fulfill(json([]))
    }
    if (/\/admin\/social\/debuts/.test(url)) return route.fulfill(json({ debuts: [], known: [], before: '2026-10-10' }))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(settings))
    if (/\/club-admin\/players\/similar/.test(url)) { log.similarAsked.push(JSON.parse(req.postData() || '{}').name); return route.fulfill(json({ candidates: similar })) }
    if (/\/club-admin\/players\/([^/]+)\/photo/.test(url)) { log.photos.push(url.match(/players\/([^/]+)\/photo/)[1]); return route.fulfill(json({ photo_url: `/api/images/players/${url.match(/players\/([^/]+)\/photo/)[1]}/photo?v=1` })) }
    if (/\/club-admin\/players/.test(url)) {
      if (m === 'POST') {
        const body = JSON.parse(req.postData() || '{}'); log.created.push(body)
        const made = { id: 'new1', name: `${body.last_name}, ${body.first_name}`, display_name: `${body.last_name}, ${body.first_name}`, player_role: body.player_role || null, skill_positions: body.player_role === 'All Rounder' ? ['ALL'] : [], photo_url: null, hero_photo_url: null, is_player: true }
        roster.push(made)
        return route.fulfill(json(made))
      }
      return route.fulfill(json(roster))
    }
    if (/sponsors\/post-default/.test(url)) return route.fulfill(json({ sponsor_ids: [], source: 'club' }))
    if (/sponsors/.test(url)) return route.fulfill(json([]))
    if (/selection\/overview/.test(url)) return route.fulfill(json({ fixtures: [] }))
    if (/lineups/.test(url)) return route.fulfill(json({ matches: [] }))
    return route.fulfill(json({}))
  })
  await page.addInitScript(([t, s, loc]) => {
    if (!sessionStorage.getItem('bs_seeded')) {
      sessionStorage.setItem('bs_seeded', '1')
      localStorage.setItem('bs_social_template', t)
      localStorage.setItem('bs_social_post_size', s)
      for (const [k, v] of Object.entries(loc)) localStorage.setItem(k, v)
    }
  }, [template, size, local])
  await page.goto(`${BASE}/admin/social-post?type=${type}${template ? `&template=${template}` : ''}`.replace(/&template=$/, ''), { waitUntil: 'domcontentloaded' })
  // A phone opens Quick Post first; the full editor is one tap further.
  if (viewport.width < 700) {
    await page.waitForTimeout(2000)
    await press(page.getByRole('button', { name: /FULL EDITOR/i }))
    await page.waitForTimeout(1500)
    return { ctx, page, log }
  }
  try {
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 30000 })
  } catch (e) {
    console.log('EDITOR DID NOT OPEN', log.errors.slice(0, 3).join(' | '), (await page.innerText('body').catch(() => '')).slice(0, 300))
    throw e
  }
  return { ctx, page, log }
}


// A control build lacks the new screens, so a step that cannot find its control
// is a FAIL on screen, not a crash that hides every check after it.
async function section(name, fn) {
  try { await fn() } catch (e) {
    fail++; console.log(`FAIL ${name}: could not run  ${String(e.message || e).split('\n')[0].slice(0, 140)}`)
  }
}

const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }
const tab = (page, name) => press(page.getByRole('button', { name, exact: true }))

const ROOT = () => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  if (!holder) return null
  const boxes = [...holder.querySelectorAll('div')].filter((d) => d.style.overflow === 'hidden' && d.style.position === 'relative' && d.style.width)
  return boxes.sort((a, b) => b.children.length - a.children.length)[0] || null
}
// What the exported post says and draws.
async function readPost(page) {
  return (await page.evaluate((rootSrc) => {
    const root = (new Function(`return (${rootSrc})()`))()
    if (!root) return null
    const rr = root.getBoundingClientRect()
    const clipped = (e) => { for (let a = e.parentElement; a && a !== root; a = a.parentElement) if (getComputedStyle(a).overflow === 'hidden') return true; return false }
    return {
      w: rr.width, h: rr.height, text: root.innerText.replace(/\s+/g, ' ').trim(), html: root.innerHTML,
      imgs: [...root.querySelectorAll('img')].map((i) => i.getAttribute('src') || ''),
      iconKinds: [...root.querySelectorAll('svg')].map((s) => s.innerHTML.replace(/\s+/g, '').length),
      overflow: [...root.querySelectorAll('*')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > rr.right + 1 || r.left < rr.left - 1 || r.bottom > rr.bottom + 1 || r.top < rr.top - 1) && !e.closest('svg') && e.tagName !== 'IMG' && e.style.pointerEvents !== 'none' && !clipped(e) }).map((e) => `${e.tagName}${e.getAttribute('data-layer') ? '[' + e.getAttribute('data-layer') + ']' : ''}`),
    }
  }, ROOT.toString())) || { w: 0, h: 0, text: '', html: '', imgs: [], iconKinds: [], overflow: ['no post'] }
}
async function shotNode(page, file) {
  await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
    holder.dataset.shot = '1'; Object.assign(holder.style, { left: '0px', top: '0px', position: 'fixed', zIndex: '2147483647', background: '#101010' })
  })
  const box = await page.evaluate(() => { const r = document.querySelector('[data-shot="1"]').firstElementChild.getBoundingClientRect(); return { w: r.width, h: r.height } })
  await page.screenshot({ path: file, clip: { x: 0, y: 0, width: Math.min(box.w, 1920), height: Math.min(box.h, 1920) } })
  await page.evaluate(() => {
    const h = document.querySelector('[data-shot="1"]')
    Object.assign(h.style, { left: '-9999px', top: '0', position: 'absolute', zIndex: '-1', background: '' }); delete h.dataset.shot
  })
}
const addByName = async (page, q) => {
  await tab(page, 'Content')
  const box = page.getByPlaceholder('Search players...')
  await box.fill(q)
  await page.waitForTimeout(150)
  await press(page.locator('button', { hasText: new RegExp(q, 'i') }).filter({ hasText: '+' }))
  await box.fill('')
  await page.waitForTimeout(250)
}
// The Players panel's chips against the panel's own edge. Written without the
// new test id so the control build reports instead of crashing.
const chipOverflow = (page) => page.evaluate(() => {
  const card = [...document.querySelectorAll('section')].find((s) => /^\s*Players/i.test(s.querySelector('h2')?.innerText || ''))
  if (!card) return { card: false, chips: 0, out: ['no panel'] }
  const cr = card.getBoundingClientRect()
  const chips = [...card.querySelectorAll('button')].filter((b) => /^(C|VC|WK|DEBUT)$/.test(b.innerText.trim()))
  return { card: true, chips: chips.length, out: chips.filter((b) => b.getBoundingClientRect().right > cr.right + 0.5).map((b) => b.innerText.trim()) }
})

// ── 1 and 2. Rows stay in the panel; an All Rounder arrives as AR ───────────
await section('step 1', async () => {
{
  const { ctx, page, log } = await openEditor({})
  for (const n of ['Abbey, Jayden', 'Abbey, Nate', 'North, Ash']) await addByName(page, n.split(',')[0] === 'Abbey' ? n.replace(', ', ', ') : n)
  const rows = page.locator('select').filter({ has: page.locator('option[value="AR"]') })
  const vals = await rows.evaluateAll((els) => els.map((e) => e.value))
  ck('three players are in the lineup', vals.length === 3, JSON.stringify(vals))
  ck('a Batter arrives as BAT', vals[0] === 'BAT', JSON.stringify(vals))
  ck('a Bowler arrives as BOWL', vals[1] === 'BOWL', JSON.stringify(vals))
  ck('an All Rounder (Ash North) arrives as AR', vals[2] === 'AR', JSON.stringify(vals))
  const post = await readPost(page)
  ck('the card draws a different icon for the all-rounder', post.iconKinds.length >= 3 && new Set(post.iconKinds).size >= 3, JSON.stringify(post.iconKinds))
  const o = await chipOverflow(page)
  ck('the panel has its chips to measure', o.card && o.chips >= 12, JSON.stringify(o))
  ck('C, VC, WK and DEBUT all sit inside the panel', o.out.length === 0, o.out.join(','))
  ck('no page errors', log.errors.length === 0, log.errors.slice(0, 3).join(' | '))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/rows-desktop.png`, clip: { x: 0, y: 0, width: 700, height: 1100 } })
  await ctx.close()
}
})
await section('step 2', async () => {
{
  const { ctx, page } = await openEditor({ viewport: { width: 390, height: 1900 } })
  for (const n of ['Abbey, Jayden', 'North, Ash']) await addByName(page, n)
  const o = await chipOverflow(page)
  ck('390px: chips inside the panel', o.card && o.chips >= 8 && o.out.length === 0, JSON.stringify(o))
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ck('390px: no sideways page scroll', wide <= 1, `${wide}px`)
  await ctx.close()
}
})

// ── 3. Headline ──────────────────────────────────────────────────────────────
await section('step 3', async () => {
{
  const { ctx, page } = await openEditor({})
  await addByName(page, 'Abbey, Jayden')
  await page.getByPlaceholder(/Applecross 6th XI/).fill('1ST XI ZZ')
  await page.waitForTimeout(500)
  const post = await readPost(page)
  ck('the Match Day Card prints the headline', /1ST XI ZZ/.test(post.text), post.text.slice(0, 120))
  ck('...and says nothing about it not being drawn', !(await seen(page.getByTestId('headline-unsupported'))))
  await ctx.close()
}
})
await section('step 4', async () => {
{
  const { ctx, page } = await openEditor({ template: 'T4' })
  await tab(page, 'Content')
  await page.getByPlaceholder(/Applecross 6th XI/).fill('1ST XI ZZ')
  await page.waitForTimeout(400)
  const post = await readPost(page)
  ck('a layout with no title does not print it', !/1ST XI ZZ/.test(post.text))
  ck('...and the panel says so, naming the layouts that do', await seen(page.getByTestId('headline-unsupported')) && /Match Day Card/.test(await page.getByTestId('headline-unsupported').innerText()))
  await ctx.close()
}
})

// ── 4. A player added by hand ────────────────────────────────────────────────
const MATCH = [{ id: 'p5', name: 'Smith, Steven', photo_url: null, player_role: 'All Rounder', confidence: 0.9, reason: 'Short form of the same first name' }]
async function fillManual(page, first, last, role, withPhoto) {
  await tab(page, 'Content')
  await press(page.getByTestId('add-manual-player'))
  await page.getByTestId('manual-first').fill(first)
  await page.getByTestId('manual-last').fill(last)
  if (role) await page.getByTestId('manual-role').selectOption(role)
  if (withPhoto) await page.getByTestId('manual-photo').setInputFiles({ name: 'face.png', mimeType: 'image/png', buffer: Buffer.from('\x89PNG\r\n\x1a\nfake') })
}
await section('step 5', async () => {
{
  const { ctx, page, log } = await openEditor({ similar: MATCH })
  ck('the add-by-hand button is offered', await seen(page.getByTestId('add-manual-player')) || (await tab(page, 'Content'), await seen(page.getByTestId('add-manual-player'))))
  await fillManual(page, 'Steve', 'Smith', 'All Rounder', true)
  await press(page.getByTestId('manual-add'))
  await page.waitForTimeout(500)
  ck('the club is asked about the typed name', log.similarAsked.join('|') === 'Steve Smith', JSON.stringify(log.similarAsked))
  ck('the likely match is shown before anything is created', await seen(page.getByTestId('manual-player-similar')) && /Smith, Steven/.test(await page.getByTestId('manual-player-similar').innerText()))
  ck('...and nothing has been created yet', log.created.length === 0)
  await press(page.getByTestId('add-as-new'))
  await page.waitForTimeout(700)
  ck('"add as new" makes exactly one player', log.created.length === 1, JSON.stringify(log.created))
  ck('...with the name split and the role', log.created[0]?.first_name === 'Steve' && log.created[0]?.last_name === 'Smith' && log.created[0]?.player_role === 'All Rounder', JSON.stringify(log.created[0]))
  ck('...and the photo goes to the new player', log.photos.join(',') === 'new1', JSON.stringify(log.photos))
  const vals = await page.locator('select').filter({ has: page.locator('option[value="AR"]') }).evaluateAll((els) => els.map((e) => e.value))
  ck('the new player is in the lineup as an all-rounder', vals.length === 1 && vals[0] === 'AR', JSON.stringify(vals))
  ck('the form closes', !(await seen(page.getByTestId('manual-player'))))
  const post = await readPost(page)
  ck('the card names them', /Smith/i.test(post.text), post.text.slice(0, 160))
  await ctx.close()
}
})
await section('step 6', async () => {
{
  const { ctx, page, log } = await openEditor({ similar: MATCH })
  await fillManual(page, 'Steve', 'Smith', '', true)
  await press(page.getByTestId('manual-add'))
  await page.waitForTimeout(400)
  await press(page.getByTestId('similar-player'))
  await page.waitForTimeout(500)
  ck('"that\'s them" creates no second record', log.created.length === 0, JSON.stringify(log.created))
  ck('...and puts the existing player in the lineup', (await page.getByText('Smith, Steven').count()) >= 1)
  ck('...and gives them the photo they had none of', log.photos.join(',') === 'p5', JSON.stringify(log.photos))
  await ctx.close()
}
})
await section('step 7', async () => {
{
  const { ctx, page, log } = await openEditor({ similar: [] })
  await fillManual(page, 'Zed', 'Nobody', 'Batter', false)
  await press(page.getByTestId('manual-add'))
  await page.waitForTimeout(700)
  ck('no likely match: the player is created straight away', log.created.length === 1 && log.created[0].last_name === 'Nobody', JSON.stringify(log.created))
  ck('...with no photo upload when none was chosen', log.photos.length === 0)
  await ctx.close()
}
})

// ── 5. The event poster is kept; saved events are listed ─────────────────────
let storage = null
await section('step 8', async () => {
{
  const { ctx, page, log } = await openEditor({ type: 'events', template: 'EV7' })
  await press(page.getByRole('button', { name: 'Season Launch', exact: true }))
  await page.getByPlaceholder(/Wine & Cheese/).fill('Halloween Night')
  await page.waitForTimeout(900)
  storage = await ctx.storageState()
  await ctx.close()
  const second = await openEditor({ type: 'events', template: 'EV7', keepStorage: storage })
  const val = await second.page.getByPlaceholder(/Wine & Cheese/).inputValue()
  ck('coming back finds the Halloween poster, not Curry Night', val === 'Halloween Night', val)
  const post = await readPost(second.page)
  ck('...and the poster draws it', /HALLOWEEN NIGHT/i.test(post.text), post.text.slice(0, 120))
  await press(second.page.getByTestId('save-as-template'))
  await second.page.waitForTimeout(300)
  const defaultName = await second.page.getByTestId('save-template-dialog').locator('input').first().inputValue()
  ck('the save name starts as the event title', defaultName === 'Halloween Night', defaultName)
  await press(second.page.getByTestId('save-template-dialog').getByRole('button', { name: /SAVE TEMPLATE|SAVE AS NEW/ }))
  await second.page.waitForTimeout(900)
  ck('saving an event template sends its wording', second.log.puts.length >= 1 && second.log.puts[0].event?.facts?.title === 'Halloween Night', JSON.stringify(second.log.puts[0]?.event?.facts || null).slice(0, 160))
  ck('...and its layout', second.log.puts[0]?.templateId === 'EV7', JSON.stringify(second.log.puts[0]?.templateId))
  await second.ctx.close()
}
})
await section('step 9', async () => {
{
  const tpl = { key: 'tpl_gold', name: 'Golf Day', templateId: 'EV7', event: { facts: { kicker: 'Annual', title: 'Golf Day', subtitle: 'Nine holes', date: 'Sun 2 Nov', time: '8:00 AM', venue: 'Links', price: '$40', cta: 'Book', sponsor: '' }, preset: 'launch', motif: 'target', bg: null, bgOpacity: 0.85 }, style: {}, updated_at: new Date().toISOString() }
  const { ctx, page } = await openEditor({ type: 'events', template: 'EV7', templates: [tpl] })
  await page.waitForTimeout(800)
  ck('saved events are listed under Start from an example', await seen(page.getByTestId('saved-events')) && /Golf Day/.test(await page.getByTestId('saved-events').innerText()))
  await press(page.getByTestId('saved-event'))
  await page.waitForTimeout(700)
  ck('picking one brings its wording back', (await page.getByPlaceholder(/Wine & Cheese/).inputValue()) === 'Golf Day')
  await ctx.close()
}
})

// ── 6. The event list layouts ────────────────────────────────────────────────
await section('step 10', async () => {
for (const [id, label, lit] of [['EL1', 'Agenda', false], ['EL2', 'Calendar', true], ['EL3', 'Icon Cards', false]]) {
  for (const size of ['square', 'portrait', 'story']) {
    const { ctx, page, log } = await openEditor({ type: 'events', template: id, size })
    await page.waitForTimeout(500)
    const post = await readPost(page)
    const H = size === 'square' ? 1080 : size === 'portrait' ? 1350 : 1920
    ck(`${label} ${size}: draws a ${H}px post`, post.w === 1080 && post.h === H, `${post.w}x${post.h}`)
    ck(`${label} ${size}: all four events are on it`, ['Working Bee', 'Quiz Night', 'Season Launch', 'Presentation Night'].every((t) => new RegExp(t, 'i').test(post.text)), post.text.slice(0, 200))
    ck(`${label} ${size}: nothing outside the frame`, post.overflow.length === 0, post.overflow.slice(0, 4).join(' | '))
    ck(`${label} ${size}: each event has its icon`, post.imgs.length >= 4, `${post.imgs.length} images`)
    if (lit) {
      const litCells = await page.evaluate((rootSrc) => {
        const root = (new Function(`return (${rootSrc})()`))()
        const accent = getComputedStyle(root).getPropertyValue('--x')
        return [...root.querySelectorAll('div')].filter((d) => d.style.borderRadius === '10px' && d.style.border === 'none' && /\d/.test(d.innerText)).length
      }, ROOT.toString())
      ck(`${label} ${size}: the event days are lit on the grid`, litCells >= 3, `${litCells} lit`)
      ck(`${label} ${size}: it names the month`, /(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER) 20\d\d/.test(post.text), post.text.slice(0, 160))
    }
    if (size === 'square') {
      ck(`${label}: the layout is in the picker under Events`, await seen(page.getByRole('button', { name: label, exact: true })))
      ck(`${label}: the editor shows the event list, not one event's facts`, await seen(page.getByTestId('event-list-editor')) && !(await seen(page.getByPlaceholder('Fri 18 Jul'))))
    }
    ck(`${label} ${size}: no page errors`, log.errors.length === 0, log.errors.slice(0, 3).join(' | '))
    if (SHOTS) await shotNode(page, `${SHOTS}/list-${id}-${size}.png`)
    await ctx.close()
  }
}
})
await section('step 11', async () => {
{
  // Editing the list: add, retitle, set a date; the post follows.
  const { ctx, page } = await openEditor({ type: 'events', template: 'EL1' })
  await press(page.getByTestId('event-add'))
  const rows = page.getByTestId('event-item')
  const n0 = await rows.count()
  ck('adding an event adds a row', n0 === 5, `${n0}`)
  await page.getByPlaceholder('Quiz Night').last().fill('Halloween Party')
  await page.getByTestId('event-date').last().fill('2026-10-31')
  await page.waitForTimeout(500)
  const post = await readPost(page)
  ck('the new event is on the post, dated', /HALLOWEEN PARTY/i.test(post.text) && /\b31\b/.test(post.text) && /OCT/i.test(post.text), post.text.slice(0, 260))
  await ctx.close()
}
})

// ── 7. Icon search ───────────────────────────────────────────────────────────
await section('step 12', async () => {
{
  const { ctx, page, log } = await openEditor({ type: 'events', template: 'EV3' })
  await press(page.getByTestId('motif-icon-search-toggle'))
  await page.getByTestId('icon-query').fill('pumpkin')
  await page.waitForTimeout(900)
  ck('searching asks the server once, with the word', log.iconSearches.join('|') === 'pumpkin', JSON.stringify(log.iconSearches))
  ck('results appear', (await page.getByTestId('icon-result').count()) === 2)
  await press(page.getByTestId('icon-result'))
  await page.waitForTimeout(700)
  ck('the picked icon becomes the motif', await seen(page.getByTestId('custom-motif')))
  const post = await readPost(page)
  ck('...and the poster draws that SVG from a data URI', post.imgs.some((s) => s.startsWith('data:image/svg+xml')), JSON.stringify(post.imgs.map((s) => s.slice(0, 30))))
  await ctx.close()
}
})
await section('step 13', async () => {
{
  const { ctx, page } = await openEditor({ type: 'events', template: 'EV1', iconFail: true })
  await press(page.getByTestId('motif-icon-search-toggle'))
  await page.getByTestId('icon-query').fill('golf')
  await page.waitForTimeout(900)
  ck('a failed search says why', /did not answer/.test(await page.getByTestId('icon-search').innerText()))
  await ctx.close()
}
})
await section('step 14', async () => {
{
  const { ctx, page } = await openEditor({ type: 'events', template: 'EV1' })
  await press(page.getByTestId('motif-icon-search-toggle'))
  await page.getByTestId('icon-query').fill('nothing here')
  await page.waitForTimeout(900)
  ck('no results says so', await seen(page.getByTestId('icon-empty')))
  await ctx.close()
}
})
await section('step 15', async () => {
{
  const { ctx, page } = await openEditor({ type: 'events', template: 'EL1' })
  await press(page.getByTestId('event-icon-search-toggle'))
  await page.getByTestId('icon-query').fill('pumpkin')
  await page.waitForTimeout(900)
  await press(page.getByTestId('icon-result'))
  await page.waitForTimeout(600)
  const post = await readPost(page)
  ck('an event in a list takes a searched icon', post.imgs.some((s) => s.startsWith('data:image/svg+xml')), JSON.stringify(post.imgs.map((s) => s.slice(0, 24))))
  await ctx.close()
}
})
await section('step 16', async () => {
{
  const { ctx, page } = await openEditor({ type: 'blank', template: 'BL1' })
  await press(page.getByRole('button', { name: 'Photos', exact: true }))
  await page.waitForTimeout(300)
  await press(page.getByRole('button', { name: 'Icons', exact: true }))
  await page.getByTestId('icon-query').fill('ghost')
  await page.waitForTimeout(900)
  await press(page.getByTestId('icon-result').nth(1))
  await page.waitForTimeout(700)
  const post = await readPost(page)
  ck('on the blank canvas an icon becomes an image block', post.imgs.some((s) => s.startsWith('data:image/svg+xml')), JSON.stringify(post.imgs.map((s) => s.slice(0, 24))))
  await ctx.close()
}
})

// ── 390px: the events editor and a list layout do not overflow ───────────────
await section('step 17', async () => {
{
  const { ctx, page } = await openEditor({ type: 'events', template: 'EL1', viewport: { width: 390, height: 1900 } })
  await page.waitForTimeout(500)
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ck('390px: events editor has no sideways scroll', wide <= 1, `${wide}px`)
  await ctx.close()
}
})

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
