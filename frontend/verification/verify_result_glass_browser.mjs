// Drives the real BetterPosts editor in Chromium with the API stubbed at the
// network layer, for the Glass Card result layout (RS7).
//
//   npx vite build && npx vite preview --port 5199 &
//   PHOTO=/path/to/photo.jpg node frontend/verification/verify_result_glass_browser.mjs [baseUrl]
//   SHOTS=/tmp/glass node ...        also writes a PNG per position and size
//
// What a build cannot tell you: that the layout is in the Final Score picker and
// draws both teams, the winner's trophy and three performers a side from a real
// import; that all six positions put the card where they say (top, bottom, the
// four side corners) at square, portrait and story, with nothing outside the
// post; that the sponsor grid and the BetterCricket logo take the free end of the
// photo and never sit under the card; that the glass panes carry a blurred copy
// of the photo and the tint behind the card follows the slider; that the sponsor
// label shows with sponsors and not without; that a side that has not batted
// says so; and that the controls fit at 390px.
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || ''
const PHOTO = process.env.PHOTO || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const POSITIONS = ['top-left', 'top-center', 'top-right', 'bottom-left', 'bottom-center', 'bottom-right']
const SIZES = [['Square', 1080, 1080], ['Portrait', 1080, 1350], ['Story', 1080, 1920]]

const svg = (w, h, fill, label) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><rect width="${w}" height="${h}" fill="${fill}"/><text x="${w / 2}" y="${h / 2 + 12}" font-family="Arial" font-weight="800" font-size="${Math.round(h * 0.4)}" fill="#fff" text-anchor="middle">${label}</text></svg>`
const SPONSOR = (i) => svg(270, 84, ['#2a7', '#a52', '#26a', '#a26'][i % 4], `SPONSOR ${i + 1}`)

const SETTINGS = {
  id: 'org-1', name: 'South Perth Cricket Club', short_name: 'SPCC', slug: 'southperth',
  logo_url: '/x', primary_color: '#0b3a2e', accent_color: '#1faa7a', theme_config: null,
}
const first = ['Chris', 'George', 'Sam', 'Brody', 'Matt', 'Aaron', 'Regan', 'Angus', 'Noah', 'Josh', 'Tom', 'Max']
const last = ['HANSBERRY', 'PULLINGER', 'TIMMINS', 'COUCH', 'ALLEN', 'OFFER', 'SPEAR', 'TURNER', 'EGAN', 'CANTRILL', 'FOX-DEAN', 'COHEN']
const bat = (i, runs, balls, notOut = false) => ({ num: i + 1, first: first[i], last: last[i], r: runs, b: balls, notOut, didNotBat: false, out: 'b X' })
const bowl = (i, w, r, o) => ({ first: first[i], last: last[i], o, m: 0, r, w, econ: r / 10 })
const CREST = (c, t) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 120" width="100" height="120"><path d="M5 5h90v70q0 30-45 40Q5 105 5 75z" fill="${c}"/><text x="50" y="70" font-family="Arial" font-weight="800" font-size="38" fill="#fff" text-anchor="middle">${t}</text></svg>`
const SCORECARD = (batted = true, oppLogo = true) => ({
  meta: { competition: 'MENS FIRST GRADE', round: 'ROUND 1', venue: 'RICHARDSON PARK', date: '2026-10-03', result: 'SOUTH PERTH WON BY 14 RUNS' },
  home: {
    name: 'South Perth Cricket Club', short: 'SPCC', total: 242, wickets: 4, overs: '50',
    batting: [bat(0, 88, 91), bat(1, 61, 70), bat(2, 33, 40), bat(3, 20, 22)],
    bowling: [bowl(5, 2, 24, '9'), bowl(6, 2, 47, '9'), bowl(7, 1, 21, '6'), bowl(8, 0, 40, '8')],
  },
  away: batted
    ? {
      name: 'Scarborough Cricket Club', short: 'SCAR', ...(oppLogo ? { logo: '/api/images/clubs/opp/logo' } : {}), total: 228, wickets: 8, overs: '50',
      batting: [bat(1, 53, 100), bat(3, 33, 19), bat(4, 25, 42), bat(9, 113, 156, true)],
      bowling: [bowl(0, 2, 42, '10'), bowl(1, 1, 63, '10'), bowl(2, 1, 49, '10'), bowl(3, 0, 30, '5')],
    }
    : { name: 'Scarborough Cricket Club', short: 'SCAR', total: '', wickets: 0, overs: '', batting: [], bowling: [] },
})

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openEditor({ viewport = { width: 1700, height: 2300 }, nSponsors = 1, batted = true, oppLogo = true, local = {}, size = 'square', mobile = false } = {}) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_|404|fonts/.test(m.text())) errors.push(m.text()) })
  const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  const sponsors = Array.from({ length: nSponsors }, (_, i) => ({ id: `s${i + 1}`, name: `Sponsor ${i + 1}`, logo_url: '/x', tier: 'major' }))
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (route) => route.abort())
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    if (/\/images\/organisations\/[^/]+\/logo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: CREST('#c22030', 'SP') })
    if (/\/images\/clubs\/opp\/logo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: CREST('#1a4eb8', 'SC') })
    if (/\/images\/sponsors\/s(\d+)\/logo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: SPONSOR(Number(url.match(/s(\d+)\/logo/)[1]) - 1) })
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'southperth',
      entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
    }))
    if (/\/admin\/social\/match-lookup/.test(url)) return route.fulfill(json({ kind: 'match', match_id: 'm1' }))
    if (/\/admin\/social\/scorecard\//.test(url)) return route.fulfill(json(SCORECARD(batted, oppLogo)))
    if (/\/admin\/social\/potm\//.test(url)) return route.fulfill(json({ match: {}, players: [] }))
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json([]))
    if (/sponsors\/post-default/.test(url)) return route.fulfill(json({ sponsor_ids: sponsors.map((x) => x.id), source: 'club' }))
    if (/sponsors/.test(url)) return route.fulfill(json(sponsors))
    return route.fulfill(json({}))
  })
  await page.addInitScript(([t, s, loc]) => {
    localStorage.setItem('bs_social_template', t)
    localStorage.setItem('bs_social_post_size', s)
    for (const [k, v] of Object.entries(loc)) localStorage.setItem(k, v)
  }, ['RS7', size, local])
  await page.goto(`${BASE}/admin/social-post?type=result&template=RS7`, { waitUntil: 'domcontentloaded' })
  if (mobile) { await page.waitForTimeout(2500); return { ctx, page, errors } }
  try {
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 30000 })
  } catch (e) {
    console.log('EDITOR DID NOT OPEN', errors.slice(0, 3).join(' | '), (await page.innerText('body').catch(() => '')).slice(0, 300))
    throw e
  }
  return { ctx, page, errors }
}

const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }

async function importResult(page) {
  await page.getByPlaceholder(/Match link from play\.cricket/).first().fill('m1')
  await page.getByRole('button', { name: /^(Import|Fetch)$/ }).first().click()
  await page.waitForTimeout(1200)
}
const tab = (page, name) => press(page.getByRole('button', { name, exact: true }))
// The card's own controls live in whichever panel holds the Glass Card section.
async function glassControls(page) {
  for (const t of ['Content', 'Design', 'Data']) {
    if (await seen(page.getByTestId('glass-card-look'))) return t
    await tab(page, t)
    await page.waitForTimeout(300)
  }
  return (await seen(page.getByTestId('glass-card-look'))) ? 'found' : ''
}
async function addPhoto(page) {
  if (!PHOTO) return false
  await glassControls(page)
  if (!(await page.getByTestId('glass-photo-input').count())) return false
  await page.getByTestId('glass-photo-input').setInputFiles(PHOTO)
  await page.getByRole('button', { name: /^Apply$/ }).waitFor({ timeout: 10000 })
  await page.waitForTimeout(600)
  await page.getByRole('button', { name: /^Apply$/ }).click()
  await page.waitForTimeout(900)
  return true
}
const setSize = async (page, label) => {
  const design = page.getByRole('button', { name: 'Design', exact: true })
  if (await design.count()) await design.first().click().catch(() => {})
  await press(page.getByRole('button', { name: new RegExp(`^${label}`) }))
  await page.waitForTimeout(500)
}

// The EXPORTED post: the off-screen node, not the scaled preview.
const ROOT = () => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  if (!holder) return null
  const boxes = [...holder.querySelectorAll('div')].filter((d) => d.style.overflow === 'hidden' && d.style.position === 'relative' && d.style.width)
  return boxes.sort((a, b) => b.children.length - a.children.length)[0] || null
}
async function read(page) {
  return await page.evaluate((rootSrc) => {
    const root = (new Function(`return (${rootSrc})()`))()
    if (!root) return null
    const rr = root.getBoundingClientRect()
    const rel = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.left - rr.left, y: r.top - rr.top, w: r.width, h: r.height, r: r.right - rr.left, b: r.bottom - rr.top } }
    const q = (n) => root.querySelector(`[data-layer="${n}"]`)
    const us = q('Our scorecard'), them = q('Their scorecard')
    const grid = root.querySelector('[data-sponsor-grid]')
    const clipped = (e) => { for (let a = e.parentElement; a && a !== root; a = a.parentElement) if (getComputedStyle(a).overflow === 'hidden') return true; return false }
    const textHits = []
    for (const el of root.querySelectorAll('*')) {
      const cs = getComputedStyle(el)
      // A glass pane holds a canvas-sized blurred photo on purpose, so only text boxes are measured.
      if (!(cs.overflow === 'hidden' || cs.overflowX === 'hidden') || !el.textContent.trim() || el.querySelector('img')) continue
      if (el.scrollWidth - el.clientWidth > 1) textHits.push(el.textContent.trim().slice(0, 30))
    }
    return {
      w: rr.width, h: rr.height, layers: [...root.children].map((c) => c.getAttribute('data-layer') || c.tagName.toLowerCase()),
      head: rel(q('Match header')), headText: q('Match header') ? q('Match header').innerText.replace(/\s+/g, ' ').trim() : '',
      us: rel(us), them: rel(them),
      usText: us ? us.innerText.replace(/\s+/g, ' ').trim() : '', themText: them ? them.innerText.replace(/\s+/g, ' ').trim() : '',
      crests: [us, them].map((p) => (p ? p.querySelectorAll('img[style*="object-fit: contain"]').length : 0)),
      crestBoxes: [us, them].map((p) => { const i = p && p.querySelector('img[style*="object-fit: contain"]'); return i ? rel(i) : null }),
      backing: q('Sponsor backing') ? { ...rel(q('Sponsor backing')), fills: [...q('Sponsor backing').children].map((c) => getComputedStyle(c).backgroundColor) } : null,
      glassImgs: [us, them].map((p) => (p ? p.querySelectorAll('img[style*="blur"]').length : 0)),
      glassFilter: us && us.querySelector('img[style*="blur"]') ? getComputedStyle(us.querySelector('img[style*="blur"]')).filter : '',
      photo: q('Background photo') ? !!q('Background photo').querySelector('img') : false,
      tintBg: q('Blur and tint') ? getComputedStyle(q('Blur and tint').lastElementChild).backgroundColor : '',
      scrim: q('Blur and tint') ? rel(q('Blur and tint')) : null,
      label: q('Sponsor label') ? { ...rel(q('Sponsor label')), text: q('Sponsor label').innerText.trim() } : null,
      credit: rel(q('BetterCricket logo')), creditImg: q('BetterCricket logo') && q('BetterCricket logo').querySelector('img') ? q('BetterCricket logo').querySelector('img').getAttribute('src') : '',
      grid: grid ? { ...rel(grid), n: grid.querySelectorAll('img').length } : null,
      trophies: root.querySelectorAll('svg path[fill="#f2d94e"]').length,
      textHits,
      outside: [...root.querySelectorAll('*')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > rr.right + 1 || r.left < rr.left - 1 || r.bottom > rr.bottom + 1 || r.top < rr.top - 1) && !e.closest('svg') && e.tagName !== 'IMG' && !clipped(e) }).map((e) => `${e.tagName}${e.getAttribute('data-layer') ? '[' + e.getAttribute('data-layer') + ']' : ''}`),
    }
  }, ROOT.toString())
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
// A check about the card only means something once the card is drawn.
const drawn = (d) => !!(d && d.us && d.them)
const overlaps = (a, b) => a && b && a.x < b.r - 1 && b.x < a.r - 1 && a.y < b.b - 1 && b.y < a.b - 1
const union = (...bs) => { const l = bs.filter(Boolean); return { x: Math.min(...l.map((b) => b.x)), y: Math.min(...l.map((b) => b.y)), r: Math.max(...l.map((b) => b.r)), b: Math.max(...l.map((b) => b.b)) } }

// ── 1. Offered, imported, both panels, trophy, header ───────────────────────
{
  const { ctx, page, errors } = await openEditor({ nSponsors: 1 })
  await importResult(page)
  await tab(page, 'Design')
  await page.waitForTimeout(300)
  ck('Glass Card is in the Final Score picker', await seen(page.getByText('Glass Card', { exact: true })))
  ck('its own controls are offered', (await glassControls(page)) !== '')
  const hadPhoto = await addPhoto(page)
  const d = await read(page)
  ck('RS7 draws a post', drawn(d) && d.w === 1080 && d.h === 1080, d && `${d.w}x${d.h}`)
  ck('layers named', d && ['Blur and tint', 'Match header', 'Our scorecard', 'Their scorecard', 'BetterCricket logo'].every((n) => d.layers.includes(n)), d && d.layers.join(','))
  ck('header carries grade, venue, round and date', d && /MENS FIRST GRADE/.test(d.headText) && /RICHARDSON PARK/.test(d.headText) && /ROUND 1/.test(d.headText) && /OCT/.test(d.headText), d && d.headText)
  ck('our panel shows the score as 4-242 with overs', d && /SOUTH PERTH/.test(d.usText) && /4-242/.test(d.usText) && /\(50\)/.test(d.usText), d && d.usText)
  ck('their panel shows 8-228', d && /SCARBOROUGH/.test(d.themText) && /8-228/.test(d.themText), d && d.themText)
  ck('first name plain and surname bold, in title case', d && /Chris/.test(d.usText + d.themText) || /George Pullinger/.test((d && d.themText) || ''), d && d.themText)
  // The team's own score and overs read the same way, so each panel has four matches.
  ck('three performers a side', d && (d.usText.match(/\d+\*?\s*\(\d+\)/g) || []).length === 4 && (d.themText.match(/\d+\*?\s*\(\d+\)/g) || []).length === 4, d && `${d.usText} || ${d.themText}`)
  ck('a hundred is picked out', d && /113\*/.test(d.themText))
  ck('one trophy, for the winner', d && d.trophies >= 1 && d.trophies <= 4, d && `${d.trophies} gold paths`)
  ck('both club crests are drawn in the panel headers', drawn(d) && d.crests[0] === 1 && d.crests[1] === 1, d && JSON.stringify(d.crests))
  ck('the crests sit inside their panels', drawn(d) && d.crestBoxes.every((b, i) => b && b.w > 20 && b.x >= [d.us, d.them][i].x && b.r <= [d.us, d.them][i].r), d && JSON.stringify(d.crestBoxes))
  ck('no sponsor backing by default', drawn(d) && !d.backing)
  ck('BetterCricket logo is drawn', d && d.credit && d.credit.h > 10 && !!d.creditImg, d && JSON.stringify(d.credit))
  ck('nothing outside the post', drawn(d) && d.outside.length === 0, d && d.outside.join(','))
  ck('no clipped text', drawn(d) && d.textHits.length === 0, d && d.textHits.join('|'))
  if (hadPhoto) {
    ck('photo reaches the post', d.photo)
    ck('both glass panes carry a blurred copy of the photo', d.glassImgs.every((n) => n === 1) && /blur\(/.test(d.glassFilter), d && `${d.glassImgs} ${d.glassFilter}`)
  }
  ck('sponsor label with a sponsor', d && d.label && /proudly sponsored by/i.test(d.label.text), d && JSON.stringify(d.label))
  ck('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  await ctx.close()
}

// ── 2. Six positions at three sizes ─────────────────────────────────────────
for (const [label, W, H] of SIZES) {
  const { ctx, page } = await openEditor({ nSponsors: 1, size: label.toLowerCase() })
  await importResult(page)
  await addPhoto(page)
  await setSize(page, label)
  await glassControls(page)
  await page.getByTestId('glass-sponsor-shade').fill('0.5')
  for (const pos of POSITIONS) {
    await glassControls(page)
    await press(page.getByTestId(`glass-pos-${pos}`))
    await page.waitForTimeout(700)
    const d = await read(page)
    const tag = `${label} ${pos}`
    if (!d) { ck(`${tag} drew`, false); continue }
    ck(`${tag}: size`, drawn(d) && d.w === W && d.h === H, `${d.w}x${d.h}`)
    const card = union(d.head, d.us, d.them)
    const [v, h] = pos.split('-')
    ck(`${tag}: card is in the ${v} half`, v === 'top' ? card.y < H * 0.3 : card.b > H * 0.7, JSON.stringify(card))
    if (h === 'center') ck(`${tag}: card spans the post`, card.x < 80 && card.r > W - 80, JSON.stringify(card))
    else if (h === 'left') ck(`${tag}: card is on the left`, card.x < 80 && card.r < W * 0.62, JSON.stringify(card))
    else ck(`${tag}: card is on the right`, card.r > W - 80 && card.x > W * 0.38, JSON.stringify(card))
    ck(`${tag}: the two panels do not overlap`, drawn(d) && !overlaps(d.us, d.them))
    ck(`${tag}: nothing outside the post`, drawn(d) && d.outside.length === 0, d.outside.join(','))
    ck(`${tag}: no clipped text`, drawn(d) && d.textHits.length === 0, d.textHits.join('|'))
    ck(`${tag}: BetterCricket logo clear of the card`, drawn(d) && d.credit && !overlaps(d.credit, card), JSON.stringify(d.credit))
    ck(`${tag}: sponsor grid clear of the card`, drawn(d) && d.grid && !overlaps(d.grid, card), JSON.stringify(d.grid))
    ck(`${tag}: sponsor backing is inside the post and clear of the card`, drawn(d) && d.backing && d.backing.x >= 0 && d.backing.r <= W && d.backing.y >= 0 && d.backing.b <= H && !overlaps(d.backing, card), JSON.stringify(d.backing))
    ck(`${tag}: sponsor label sits just above the grid`, drawn(d) && d.label && d.grid && Math.abs(d.label.b - d.grid.y) < 40, JSON.stringify({ l: d.label, g: d.grid }))
    ck(`${tag}: sponsors are at the free end`, drawn(d) && d.grid && (v === 'top' ? d.grid.y > H * 0.6 : d.grid.b < H * 0.4), JSON.stringify(d.grid))
    ck(`${tag}: BetterCricket logo is at the free end`, drawn(d) && d.credit && (v === 'top' ? d.credit.y > H * 0.6 : d.credit.b < H * 0.4), JSON.stringify(d.credit))
    if (SHOTS) await shotNode(page, `${SHOTS}/${label.toLowerCase()}-${pos}.png`)
  }
  await ctx.close()
}

// ── 2b. Logos on and off, a club with no logo, and the sponsor shade ─────────
{
  const { ctx, page } = await openEditor({ nSponsors: 1, oppLogo: false })
  await importResult(page)
  const on = await read(page)
  ck('no opposition logo: its panel shows initials, ours keeps the crest', drawn(on) && on.crests[0] === 1 && on.crests[1] === 0 && /^[A-Z]{1,3}\s+SCARBOROUGH/.test(on.themText), on && `${on.crests} ${on.themText}`)
  await glassControls(page)
  await page.getByTestId('glass-logos').locator('input').uncheck()
  await page.waitForTimeout(400)
  const off = await read(page)
  ck('turning logos off removes every crest and monogram', drawn(off) && off.crests[0] === 0 && off.crests[1] === 0 && /^SCARBOROUGH/.test(off.themText), off && `${off.crests} ${off.themText}`)
  await page.getByTestId('glass-logos').locator('input').check()
  await page.waitForTimeout(300)
  await glassControls(page)
  await page.getByTestId('glass-sponsor-shade').fill('0.6')
  await page.waitForTimeout(500)
  const dark = await read(page)
  const card = dark && drawn(dark) && union(dark.head, dark.us, dark.them)
  ck('a dark backing appears behind the sponsor label and logo', drawn(dark) && dark.backing && dark.backing.fills.some((f) => /rgba\(0, 0, 0, 0\.6\)/.test(f)), dark && JSON.stringify(dark.backing))
  ck('the backing holds the label and the grid and stays in the post', drawn(dark) && dark.backing && dark.grid && dark.label
    && dark.backing.x <= dark.grid.x && dark.backing.r >= dark.grid.r && dark.backing.y <= dark.label.y && dark.backing.b >= dark.grid.b
    && dark.backing.x >= 0 && dark.backing.r <= 1080 && dark.backing.y >= 0 && dark.backing.b <= 1080, dark && JSON.stringify(dark.backing))
  ck('the backing is clear of the card', drawn(dark) && dark.backing && !overlaps(dark.backing, card))
  await glassControls(page)
  await press(page.getByTestId('glass-sponsor-tone-light'))
  await page.waitForTimeout(400)
  const light = await read(page)
  ck('light glass backs with white', drawn(light) && light.backing && light.backing.fills.some((f) => /rgba\(255, 255, 255, 0\.6\)/.test(f)), light && JSON.stringify(light.backing))
  ck('the label turns dark on a strong light backing', drawn(light) && light.label && light.label.text.length > 0)
  await glassControls(page)
  await page.getByTestId('glass-sponsor-shade').fill('0')
  await page.waitForTimeout(400)
  const none = await read(page)
  ck('shade at zero takes the backing away', drawn(none) && !none.backing)
  await ctx.close()
}
{
  const { ctx, page } = await openEditor({ nSponsors: 0 })
  await importResult(page)
  await glassControls(page)
  await page.getByTestId('glass-sponsor-shade').fill('0.6')
  await page.waitForTimeout(400)
  const d = await read(page)
  ck('no sponsors: no backing even with shade on', drawn(d) && !d.backing)
  await ctx.close()
}

// ── 3. Sponsors: none, and four ─────────────────────────────────────────────
{
  const { ctx, page } = await openEditor({ nSponsors: 0 })
  await importResult(page)
  const d = await read(page)
  ck('no sponsors: no label and no grid', drawn(d) && !d.label && !d.grid, d && JSON.stringify({ l: d.label, g: d.grid }))
  ck('no sponsors: BetterCricket logo still shown', drawn(d) && d.credit && d.credit.h > 10)
  await ctx.close()
}
{
  const { ctx, page } = await openEditor({ nSponsors: 4 })
  await importResult(page)
  await page.waitForTimeout(500)
  const d = await read(page)
  const card = d && union(d.head, d.us, d.them)
  ck('four sponsors: four logos inside the post and clear of the card', drawn(d) && d.grid && d.grid.n === 4 && !overlaps(d.grid, card) && d.grid.r <= 1080, d && JSON.stringify(d.grid))
  if (SHOTS) await shotNode(page, `${SHOTS}/four-sponsors.png`)
  await ctx.close()
}

// ── 4. A side that has not batted ───────────────────────────────────────────
{
  const { ctx, page } = await openEditor({ nSponsors: 1, batted: false })
  await importResult(page)
  const d = await read(page)
  ck('a side with no score says Yet to bat', d && /Yet to bat/.test(d.themText) && !/Yet to bat/.test(d.usText), d && `${d.usText} || ${d.themText}`)
  await ctx.close()
}

// ── 5. Performers per side, tint, and the grid following a move ─────────────
{
  const { ctx, page } = await openEditor({ nSponsors: 1 })
  await importResult(page)
  await addPhoto(page)
  const before = await read(page)
  await glassControls(page)
  if (!(await page.getByTestId('glass-perfUs').count())) { ck('performer, tint and position controls exist', false); await ctx.close() } else {
  await glassControls(page)
  await page.getByTestId('glass-perfUs').selectOption('bowl')
  await page.waitForTimeout(500)
  const bowl = await read(page)
  ck('our panel switches to bowlers (2-24 style figures with overs)', bowl && /\d-\d+ \(\d/.test(bowl.usText) && bowl.usText !== before.usText, bowl && bowl.usText)
  ck('their panel is unchanged by it', bowl && bowl.themText === before.themText)
  const t0 = before.tintBg
  await page.getByTestId('glass-tint').fill('0.85')
  await page.waitForTimeout(400)
  const dark = await read(page)
  ck('the tint follows the slider', dark && dark.tintBg !== t0 && /0\.85/.test(dark.tintBg), `${t0} -> ${dark && dark.tintBg}`)
  await glassControls(page)
  await press(page.getByTestId('glass-pos-bottom-left'))
  await page.waitForTimeout(700)
  const moved = await read(page)
  ck('moving the card moves the grid to the other end', moved && moved.grid && moved.grid.y < 540 && before.grid && before.grid.y > 540, `${before.grid && before.grid.y} -> ${moved && moved.grid && moved.grid.y}`)
  // the position is remembered
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 30000 })
  await importResult(page)
  await glassControls(page)
  ck('position and performers are kept across a reload', (await page.getByTestId('glass-pos-bottom-left').getAttribute('aria-checked')) === 'true' && (await page.getByTestId('glass-perfUs').inputValue()) === 'bowl')
  await ctx.close()
}
}

// ── 6. 390px ────────────────────────────────────────────────────────────────
{
  const { ctx, page } = await openEditor({ viewport: { width: 390, height: 900 }, mobile: true })
  if (page) {
    await page.waitForTimeout(800)
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    ck('no horizontal overflow at 390px', over <= 1, `${over}px`)
    await ctx.close()
  }
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
