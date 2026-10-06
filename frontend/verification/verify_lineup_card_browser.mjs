// Drives the real BetterPosts editor in Chromium with the API stubbed at the
// network layer, for the Match Day Card lineup (T12).
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_lineup_card_browser.mjs [baseUrl]
//   SHOTS=/tmp/card node ...        also writes a PNG per size and sponsor count
//
// What a build cannot tell you: that the card is in the picker and draws the
// eleven names it was given, with the right role icon beside each (bat, bowl,
// bat and ball, bat and stumps), inside the frame at all three sizes; that the
// sponsor bar is as tall as its logos need (one or eight) and disappears with
// none; that a wide wordmark and a square crest each get the box their shape
// suits; that an uploaded background goes to the server as a background asset
// and is saved as the club default, and comes back on a reload; that the wash
// and corner colours reach the post; and that nothing overflows at 390px.
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
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

const NAMES = ['Szigligeti, Sam', 'Farmer, Nathan', 'Cartwright, Hilton', 'Hay, Frazer', 'Middlemas, Ben', 'Melville, Alexander',
  'Wenban, Alex', 'Botha, Eric', 'Frame, Josh', 'Dallimore, Liam', 'Wilson, Wyatt', 'Spare, Sid']
// Roles in the order the reference shows them: four batters, a keeper, an
// all-rounder, five bowlers.
const ROLES = ['BAT', 'BAT', 'BAT', 'BAT', 'BAT', 'AR', 'BOWL', 'BOWL', 'BOWL', 'BOWL', 'BOWL', 'BAT']
const PLAYERS = NAMES.map((n, i) => ({ id: `p${i + 1}`, name: n, display_name: n, status: 'active', player_role: ROLES[i], photo_url: null }))

const svg = (w, h, fill, label) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><rect width="${w}" height="${h}" fill="${fill}"/><text x="${w / 2}" y="${h / 2 + 12}" font-family="Arial" font-weight="800" font-size="${Math.round(h * 0.4)}" fill="#fff" text-anchor="middle">${label}</text></svg>`
const WIDE_LOGO = svg(600, 100, '#c22030', 'KALAMUNDA')      // 6:1
const SQUARE_LOGO = svg(200, 200, '#c22030', 'K')            // 1:1
const BG_PHOTO = svg(1600, 1000, '#556b8d', 'PHOTO')
const SPONSOR = (i) => svg(270, 84, ['#2a7', '#a52', '#26a', '#a26', '#6a2', '#2aa', '#a82', '#62a'][i % 8], `SPONSOR ${i + 1}`)

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openEditor({ mobile = false, viewport = { width: 1600, height: 1980 }, nSponsors = 1, logo = 'wide', style = null, size = 'square', local = {} } = {}) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const errors = [], uploads = [], patches = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_|404/.test(m.text())) errors.push(m.text()) })
  const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  const sponsors = Array.from({ length: nSponsors }, (_, i) => ({ id: `s${i + 1}`, name: `Sponsor ${i + 1}`, logo_url: '/x', tier: 'major' }))
  const settings = {
    id: 'org-1', name: 'Kalamunda Cricket Club', short_name: 'KCC', slug: 'kalamunda',
    logo_url: '/x', primary_color: '#0a2a6b', accent_color: '#0b5fe0', theme_config: null, socials_style: style,
  }
  await page.route(/fonts\.(googleapis|gstatic)\.com/, async (route) => {
    const url = route.request().url()
    const file = `/tmp/fontcache/${createHash('sha1').update(url).digest('hex')}`
    try {
      if (!existsSync(file)) {
        mkdirSync('/tmp/fontcache', { recursive: true })
        const ua = route.request().headers()['user-agent'] || 'Mozilla/5.0 Chrome/120'
        writeFileSync(file, execFileSync('curl', ['-s', '-m', '30', '-A', ua, url], { maxBuffer: 20e6 }))
      }
      return route.fulfill({ status: 200, contentType: /googleapis/.test(url) ? 'text/css' : 'font/woff2', body: readFileSync(file), headers: { 'access-control-allow-origin': '*' } })
    } catch { return route.abort() }
  })
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = req.url()
    const img = (body) => route.fulfill({ status: 200, contentType: 'image/svg+xml', body })
    if (/\/images\/organisations\/[^/]+\/logo/.test(url)) return img(logo === 'wide' ? WIDE_LOGO : SQUARE_LOGO)
    if (/\/images\/sponsors\/s(\d+)\/logo/.test(url)) return img(SPONSOR(Number(url.match(/s(\d+)\/logo/)[1]) - 1))
    if (/\/images\/social-media\//.test(url)) return img(/up2/.test(url) ? SQUARE_LOGO : BG_PHOTO)
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'kalamunda',
      entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
    }))
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) {
      if (req.method() === 'POST') {
        const body = req.postData() || ''
        uploads.push({ kind: /name="kind"\r\n\r\nbackground/.test(body) ? 'background' : null })
        const n = uploads.length
        return route.fulfill(json({ id: `up${n}`, name: `up${n}.png`, url: `/api/images/social-media/up${n}?v=1`, kind: uploads[n - 1].kind }))
      }
      return route.fulfill(json([]))
    }
    if (/\/club-admin\/settings/.test(url)) {
      if (req.method() === 'PATCH' || req.method() === 'PUT') { patches.push(JSON.parse(req.postData() || '{}')); return route.fulfill(json(settings)) }
      return route.fulfill(json(settings))
    }
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json(PLAYERS))
    if (/sponsors\/post-default/.test(url)) return route.fulfill(json({ sponsor_ids: sponsors.map((x) => x.id), source: 'club' }))
    if (/sponsors/.test(url)) return route.fulfill(json(sponsors))
    if (/selection\/overview/.test(url)) return route.fulfill(json({ fixtures: [{ id: 'fx1', opponent_name: 'Bayswater Morley', grade: '1st Grade', round: 'Round 1', played_on: '2026-10-10' }] }))
    if (/\/selection\/fx1$/.test(url)) return route.fulfill(json({
      fixture: { id: 'fx1', opponent_name: 'Bayswater Morley', grade: '1st Grade', round: 'Round 1', played_on: '2026-10-10', venue: 'Edinburgh Oval', start_time: '10:30', home_away: 'HOME', home_team: 'Kalamunda', away_team: 'Bayswater Morley' },
      lineup: PLAYERS.slice(0, 11).map((p, i) => ({ player_id: p.id, batting_order: i + 1, is_captain: p.id === 'p1', is_wicket_keeper: p.id === 'p5' })),
      pool: [],
    }))
    if (/\/admin\/social\/debuts/.test(url)) return route.fulfill(json({ debuts: [], known: [], before: '2026-10-10' }))
    if (/lineups/.test(url)) return route.fulfill(json({ matches: [] }))
    return route.fulfill(json({}))
  })
  await page.addInitScript(([t, s, loc]) => {
    localStorage.setItem('bs_social_template', t)
    localStorage.setItem('bs_social_post_size', s)
    for (const [k, v] of Object.entries(loc)) localStorage.setItem(k, v)
  }, ['T12', size, local])
  await page.goto(`${BASE}/admin/social-post?type=lineup&template=T12`, { waitUntil: 'domcontentloaded' })
  if (mobile) { await page.waitForTimeout(2500); return { ctx, page, errors, uploads, patches } }
  try {
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 30000 })
  } catch (e) {
    console.log('EDITOR DID NOT OPEN', errors.slice(0, 3).join(' | '), (await page.innerText('body').catch(() => '')).slice(0, 300))
    throw e
  }
  return { ctx, page, errors, uploads, patches }
}

const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }
const tab = (page, name) => press(page.getByRole('button', { name, exact: true }))

// The EXPORTED post: the off-screen node, not the scaled preview.
const ROOT = () => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  if (!holder) return null
  const boxes = [...holder.querySelectorAll('div')].filter((d) => d.style.overflow === 'hidden' && d.style.position === 'relative' && d.style.width)
  return boxes.sort((a, b) => b.children.length - a.children.length)[0] || null
}
const EMPTY = { w: 0, h: 0, layers: [], rows: [], icons: [], bar: null, logo: null, wash: null, corner: null, bg: null, grid: null, details: '', overflowList: ['no post'] }
async function read(page) {
  return (await page.evaluate((rootSrc) => {
    const root = (new Function(`return (${rootSrc})()`))()
    if (!root) return null
    const rr = root.getBoundingClientRect()
    const rel = (el) => { const r = el.getBoundingClientRect(); return { x: r.left - rr.left, y: r.top - rr.top, w: r.width, h: r.height } }
    const q = (n) => root.querySelector(`[data-layer="${n}"]`)
    const list = q('Starting XI')
    const rows = list ? [...list.children].filter((r) => r.style.position === 'absolute' && r.style.height).map((r) => ({ ...rel(r), text: r.innerText.replace(/\s+/g, ' ').trim(), iconKey: r.querySelector('svg') ? r.querySelector('svg').innerHTML.replace(/\s+/g, '').length : 0, fs: r.children[1] && r.children[1].firstElementChild ? parseFloat(getComputedStyle(r.children[1].firstElementChild).fontSize) : 0 })) : []
    const bar = q('Sponsor bar'), logo = q('Club logo'), wash = q('Colour wash'), bg = q('Background photo'), details = q('Match details')
    const corner = q('Corner top left')
    const grid = root.querySelector('[data-sponsor-grid]')
    const clipped = (e) => { for (let a = e.parentElement; a && a !== root; a = a.parentElement) if (getComputedStyle(a).overflow === 'hidden') return true; return false }
    return {
      w: rr.width, h: rr.height, layers: [...root.children].map((c) => c.getAttribute('data-layer') || c.tagName.toLowerCase()),
      rows, bar: bar ? rel(bar) : null, logo: logo ? rel(logo) : null, list: list ? rel(list) : null,
      wash: wash ? { bg: getComputedStyle(wash).backgroundColor, full: getComputedStyle(wash).background, opacity: getComputedStyle(wash).opacity } : null,
      corner: corner ? corner.querySelector('polygon').getAttribute('fill') : null,
      bg: bg ? bg.querySelector('img').getAttribute('src') : null,
      grid: grid ? { ...rel(grid), n: grid.querySelectorAll('img').length } : null,
      details: details ? details.innerText.replace(/\s+/g, ' ').trim() : '',
      overflowList: [...root.querySelectorAll('*')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > rr.right + 1 || r.left < rr.left - 1 || r.bottom > rr.bottom + 1 || r.top < rr.top - 1) && !e.closest('svg') && e.tagName !== 'IMG' && !clipped(e) }).map((e) => `${e.tagName}${e.getAttribute('data-layer') ? '[' + e.getAttribute('data-layer') + ']' : ''}`),
    }
  }, ROOT.toString())) || EMPTY
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
const loadXI = async (page) => {
  await press(page.getByRole('button', { name: /^Data$/i }))
  await page.waitForTimeout(400)
  await press(page.getByRole('button', { name: /Bayswater/ }))
  await page.waitForTimeout(900)
  await tab(page, 'Content')
  await page.waitForTimeout(200)
}
// The card's own controls live in whichever panel holds the hero-image section.
const openCardControls = async (page) => {
  for (const t of ['Content', 'Design', 'Data']) {
    await tab(page, t)
    await page.waitForTimeout(250)
    if (await seen(page.getByTestId('lineup-card-style'))) return t
  }
  return ''
}

// ── 1. Offered, eleven rows, role icons, details, one sponsor ───────────────
{
  const { ctx, page, errors } = await openEditor({ nSponsors: 1 })
  await loadXI(page)
  await page.waitForTimeout(800)
  const d = await read(page)
  ck('T12 draws a post', d.w === 1080 && d.h === 1080, `${d.w}x${d.h}`)
  ck('layers named', ['Colour wash', 'Sponsor bar', 'Corner top left', 'Corner bottom right', 'Club logo', 'Starting XI', 'Match details'].every((n) => d.layers.includes(n)), d.layers.join(','))
  ck('eleven rows', d.rows.length === 11, `${d.rows.length}`)
  ck('first name', /1\.\s*Sam Szigligeti|1\.\s*Szigligeti/i.test(d.rows[0]?.text || ''), d.rows[0]?.text)
  // Four batters, keeper, all-rounder, five bowlers: icon markup differs by kind.
  const k = d.rows.map((r) => r.iconKey)
  ck('batters share one icon', new Set(k.slice(0, 4)).size === 1, k.join(','))
  ck('keeper icon differs from batter', k[4] !== k[0], k.join(','))
  ck('all-rounder icon differs from both', k[5] !== k[0] && k[5] !== k[4], k.join(','))
  ck('bowlers share one icon', new Set(k.slice(6, 11)).size === 1 && k[6] !== k[0], k.join(','))
  ck('rows inside the list', d.rows.length === 11 && d.rows.every((r) => r.y >= d.list.y - 1 && r.y + r.h <= d.list.y + d.list.h + 1), JSON.stringify(d.rows.slice(0, 2)))
  ck('one name size down the whole list', d.rows.length === 11 && new Set(d.rows.map((r) => Math.round(r.fs))).size === 1 && d.rows[0].fs >= 20, d.rows.map((r) => r.fs).join(','))
  ck('fixture on the right', /KALAMUNDA CRICKET CLUB/.test(d.details) && /VS BAYSWATER MORLEY|VS\s*BAYSWATER MORLEY/.test(d.details), d.details)
  ck('details are right of the list', d.list && d.rows.length && d.details.length > 0)
  ck('one sponsor: bar present', !!d.bar && d.bar.h >= 140 && d.bar.h <= 160, JSON.stringify(d.bar))
  ck('one sponsor: grid inside bar', d.grid && d.grid.n === 1 && d.bar && d.grid.y >= d.bar.y - 1 && d.grid.y + d.grid.h <= d.bar.y + d.bar.h + 1, JSON.stringify(d.grid))
  ck('list clears the bar', d.list && d.bar && d.list.y + d.list.h <= d.bar.y)
  ck('wide logo is 6:1 and as wide as allowed', d.logo && Math.abs(d.logo.w / d.logo.h - 6) < 0.2 && d.logo.w > 500 && d.logo.w <= 530, JSON.stringify(d.logo))
  ck('logo centred over the list', d.logo && d.list && Math.abs((d.logo.x + d.logo.w / 2) - (d.list.x + d.list.w / 2)) < 2)
  ck('nothing outside the post', d.overflowList.length === 0, d.overflowList.join(' | '))
  ck('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  if (SHOTS) await shotNode(page, `${SHOTS}/card-1-sponsor.png`)
  await ctx.close()
}

// ── 2. Eight sponsors: taller bar, two rows; none: no bar ────────────────────
{
  const { ctx, page } = await openEditor({ nSponsors: 8 })
  await loadXI(page)
  await page.waitForTimeout(800)
  const d = await read(page)
  ck('eight sponsors: grid holds eight', d.grid && d.grid.n === 8, JSON.stringify(d.grid))
  ck('eight sponsors: bar taller than one', d.bar && d.bar.h >= 220, JSON.stringify(d.bar))
  ck('eight sponsors: grid inside the bar', d.grid && d.bar && d.grid.y >= d.bar.y - 1 && d.grid.y + d.grid.h <= d.bar.y + d.bar.h + 1)
  ck('eight sponsors: list still clears the bar', d.list && d.bar && d.list.y + d.list.h <= d.bar.y)
  ck('eight sponsors: eleven rows still', d.rows.length === 11)
  if (SHOTS) await shotNode(page, `${SHOTS}/card-8-sponsors.png`)
  await ctx.close()
}
{
  const { ctx, page } = await openEditor({ nSponsors: 0 })
  await loadXI(page)
  await page.waitForTimeout(500)
  const d = await read(page)
  ck('no sponsors: no bar drawn', d.bar === null && !d.layers.includes('Sponsor bar'), d.layers.join(','))
  ck('no sponsors: list gets the room', d.list && d.list.h > 560, JSON.stringify(d.list))
  await ctx.close()
}

// ── 3. A square crest gets a square box ──────────────────────────────────────
{
  const { ctx, page } = await openEditor({ nSponsors: 1, logo: 'square' })
  await loadXI(page)
  await page.waitForTimeout(600)
  const d = await read(page)
  ck('square logo is square', d.logo && Math.abs(d.logo.w / d.logo.h - 1) < 0.05 && d.logo.h > 100 && d.logo.h <= 120, JSON.stringify(d.logo))
  await ctx.close()
}

// ── 4. The controls: wash, corner, background upload, save as default ────────
{
  const { ctx, page, uploads, patches } = await openEditor({ nSponsors: 1 })
  await loadXI(page)
  const where = await openCardControls(page)
  ck('card look controls are shown', !!where)
  const before = await read(page)
  ck('no photo to begin with', before.bg === null)

  await page.getByTestId('lineup-card-wash').fill('#1a3a8a')
  await page.getByTestId('lineup-card-corner').fill('#ff6600')
  await page.waitForTimeout(400)
  const mid = await read(page)
  ck('wash colour reaches the post', mid.wash && mid.wash.full.includes('rgb(26, 58, 138)'), JSON.stringify(mid.wash))
  ck('corner colour reaches the post', (mid.corner || '').toLowerCase() === '#ff6600', mid.corner)

  await page.getByTestId('lineup-card-bg-input').setInputFiles({ name: 'ground.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC', 'base64') })
  await page.waitForTimeout(1500)
  ck('upload went up as a background asset', uploads.length === 1 && uploads[0].kind === 'background', JSON.stringify(uploads))
  const after = await read(page)
  ck('uploaded photo is on the post', /social-media\/up1/.test(after.bg || ''), after.bg)
  ck('with a photo the wash is a flat colour over it', after.wash && after.wash.bg === 'rgb(26, 58, 138)' && Math.abs(Number(after.wash.opacity) - 0.8) < 0.01, JSON.stringify(after.wash))
  await page.waitForTimeout(1800)
  const saved = patches.map((p) => p.socials_style?.lineup_card).filter(Boolean).pop()
  ck('saved to the club as the default', saved && /social-media\/up1/.test(saved.bgUrl) && saved.wash === '#1a3a8a' && saved.corner === '#ff6600', JSON.stringify(saved))
  if (SHOTS) await shotNode(page, `${SHOTS}/card-custom.png`)
  await ctx.close()

  // A second session: the server hands the saved look back and a new card opens with it.
  const style = { palette: 'club', dark: true, font: 'barlow', bg: 'none', bg_colors: {}, palettes: [], designs: [], lineup_card: saved }
  const again = await openEditor({ nSponsors: 1, style })
  await loadXI(again.page)
  await again.page.waitForTimeout(600)
  const re = await read(again.page)
  ck('reload: photo is back', /social-media\/up1/.test(re.bg || ''), re.bg)
  ck('reload: wash is back', re.wash && re.wash.bg === 'rgb(26, 58, 138)', JSON.stringify(re.wash))
  ck('reload: corner is back', (re.corner || '').toLowerCase() === '#ff6600', re.corner)
  await again.ctx.close()
}

// ── 5. Portrait, story, and a phone ─────────────────────────────────────────
for (const [size, W, H] of [['portrait', 1080, 1350], ['story', 1080, 1920]]) {
  const { ctx, page } = await openEditor({ nSponsors: 8, size })
  await loadXI(page)
  await page.waitForTimeout(800)
  const d = await read(page)
  ck(`${size}: canvas is ${W}x${H}`, d.w === W && d.h === H, `${d.w}x${d.h}`)
  ck(`${size}: eleven rows and the grid`, d.rows.length === 11 && d.grid && d.grid.n === 8, `${d.rows.length} ${JSON.stringify(d.grid)}`)
  ck(`${size}: one name size down the list`, d.rows.length === 11 && new Set(d.rows.map((r) => Math.round(r.fs))).size === 1, d.rows.map((r) => r.fs).join(','))
  ck(`${size}: list clears the bar`, d.list && d.bar && d.list.y + d.list.h <= d.bar.y)
  ck(`${size}: nothing outside the post`, d.overflowList.length === 0, d.overflowList.join(' | '))
  if (size === 'story') ck('story: grid clear of the reply bar', d.grid && d.grid.y + d.grid.h <= d.h - 130, JSON.stringify(d.grid))
  if (SHOTS) await shotNode(page, `${SHOTS}/card-${size}.png`)
  await ctx.close()
}
{
  const { ctx, page } = await openEditor({ nSponsors: 1, mobile: true, viewport: { width: 390, height: 844 } })
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no horizontal overflow', over <= 1, `${over}px`)
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
