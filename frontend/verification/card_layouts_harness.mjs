// Shared by shoot_card_layouts.mjs and verify_card_layouts_browser.mjs: opens the
// real BetterPosts editor in Chromium with the API stubbed at the network layer.
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'

const svg = (w, h, fill, label) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><rect width="${w}" height="${h}" fill="${fill}"/><text x="${w / 2}" y="${h / 2 + 12}" font-family="Arial" font-weight="800" font-size="${Math.round(h * 0.4)}" fill="#fff" text-anchor="middle">${label}</text></svg>`
const CREST = (c, l) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200"><circle cx="100" cy="100" r="92" fill="${c}"/><text x="100" y="128" font-family="Arial" font-weight="900" font-size="90" fill="#fff" text-anchor="middle">${l}</text></svg>`
const SPONSOR = (i) => svg(270, 84, ['#2a7', '#a52', '#26a', '#a26', '#6a2', '#2aa'][i % 6], `SPONSOR ${i + 1}`)

const NAMES = ['Pullinger, George', 'Hansberry, Chris', 'Timmins, Sam', 'Couch, Brody', 'Allen, Matt', 'Offer, Aaron', 'Spear, Regan', 'Turner, Angus', 'Egan, Noah', 'Cantrill, Josh', 'Cohen, Max', 'Spare, Sid']
const PLAYERS = NAMES.map((n, i) => ({ id: `p${i + 1}`, name: n, display_name: n, status: 'active', player_role: i < 5 ? 'BAT' : 'BOWL', photo_url: null }))

const first = ['Chris', 'George', 'Sam', 'Brody', 'Matt', 'Aaron', 'Regan', 'Angus', 'Noah', 'Josh', 'Tom', 'Max']
const last = ['HANSBERRY', 'PULLINGER', 'TIMMINS', 'COUCH', 'ALLEN', 'OFFER', 'SPEAR', 'TURNER', 'EGAN', 'CANTRILL', 'FOX-DEAN', 'COHEN']
const bat = (i, runs, balls, notOut = false) => ({ num: i + 1, first: first[i], last: last[i], r: runs, b: balls, notOut, didNotBat: false, out: 'b X' })
const bowl = (i, w, r, o) => ({ first: first[i], last: last[i], o, m: 0, r, w, econ: r / 10 })
export const SCORECARD = () => ({
  meta: { competition: 'WA PREMIER CRICKET', round: 'ROUND 1', venue: 'RICHARDSON PARK', date: '2026-10-03', result: 'SOUTH PERTH WON BY 14 RUNS' },
  home: {
    name: 'South Perth Cricket Club', short: 'SPCC', total: 242, wickets: 4, overs: '50',
    batting: [bat(0, 88, 91), bat(1, 61, 70), bat(2, 33, 40), bat(3, 20, 22)],
    bowling: [bowl(5, 2, 24, '9'), bowl(6, 2, 47, '9'), bowl(7, 1, 21, '6'), bowl(8, 0, 40, '8')],
  },
  away: {
    name: 'Scarborough Cricket Club', short: 'SCAR', total: 228, wickets: 8, overs: '50',
    batting: [bat(1, 53, 100), bat(3, 33, 19), bat(4, 25, 42), bat(9, 113, 156, true)],
    bowling: [bowl(0, 2, 42, '10'), bowl(1, 1, 63, '10'), bowl(2, 1, 49, '10'), bowl(3, 0, 30, '5')],
  },
})

export const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
export const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }
export const tab = (page, name) => press(page.getByRole('button', { name, exact: true }))

const TYPE = { T13: 'lineup', C5: 'announcement', RS8: 'result' }

// The EXPORTED post: the off-screen node, not the scaled preview.
export const ROOT = () => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  if (!holder) return null
  const boxes = [...holder.querySelectorAll('div')].filter((d) => d.style.overflow === 'hidden' && d.style.position === 'relative' && d.style.width)
  return boxes.sort((a, b) => b.children.length - a.children.length)[0] || null
}

export async function shotNode(page, file) {
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

export async function makeEditor(browser, BASE, { layout, size = 'portrait', nSponsors = 1, viewport = { width: 1700, height: 2300 }, mobile = false } = {}) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_|404|fonts/.test(m.text())) errors.push(m.text()) })
  const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  const sponsors = Array.from({ length: nSponsors }, (_, i) => ({ id: `s${i + 1}`, name: `Sponsor ${i + 1}`, logo_url: '/x', tier: 'major' }))
  const settings = { id: 'org-1', name: 'Scarborough Cricket Club', short_name: 'SCC', slug: 'scarborough', logo_url: '/x', primary_color: '#0e6e51', accent_color: '#ffdd1a', theme_config: { accent: '#ffdd1a' }, socials_style: null }
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
    const url = route.request().url()
    const img = (body) => route.fulfill({ status: 200, contentType: 'image/svg+xml', body })
    if (/\/images\/organisations\/[^/]+\/logo/.test(url)) return img(CREST('#0e6e51', 'S'))
    if (/\/images\/sponsors\/s(\d+)\/logo/.test(url)) return img(SPONSOR(Number(url.match(/s(\d+)\/logo/)[1]) - 1))
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'scarborough',
      entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
    }))
    if (/\/admin\/social\/match-lookup/.test(url)) return route.fulfill(json({ kind: 'match', match_id: 'm1' }))
    if (/\/admin\/social\/scorecard\//.test(url)) return route.fulfill(json(SCORECARD()))
    if (/\/admin\/social\/potm\//.test(url)) return route.fulfill(json({ match: {}, players: [] }))
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/debuts/.test(url)) return route.fulfill(json({ debuts: [], known: [], before: '2026-10-03' }))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(settings))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json(PLAYERS))
    if (/sponsors\/post-default/.test(url)) return route.fulfill(json({ sponsor_ids: sponsors.map((x) => x.id), source: 'club' }))
    if (/sponsors/.test(url)) return route.fulfill(json(sponsors))
    if (/selection\/overview/.test(url)) return route.fulfill(json({ fixtures: [{ id: 'fx1', opponent_name: 'South Perth', grade: '1st Grade', round: 'Round 1', played_on: '2026-10-03' }] }))
    if (/\/selection\/fx1$/.test(url)) return route.fulfill(json({
      fixture: { id: 'fx1', opponent_name: 'South Perth', grade: '1st Grade', round: 'Round 1', played_on: '2026-10-03', venue: 'Richardson Park', start_time: '10:30', home_away: 'HOME', home_team: 'Scarborough', away_team: 'South Perth' },
      lineup: PLAYERS.slice(0, 11).map((p, i) => ({ player_id: p.id, batting_order: i + 1, is_captain: p.id === 'p1', is_wicket_keeper: p.id === 'p5' })),
      pool: [],
    }))
    if (/lineups/.test(url)) return route.fulfill(json({ matches: [] }))
    return route.fulfill(json({}))
  })
  await page.addInitScript(([t, s]) => { localStorage.setItem('bs_social_template', t); localStorage.setItem('bs_social_post_size', s) }, [layout, size])
  await page.goto(`${BASE}/admin/social-post?type=${TYPE[layout]}&template=${layout}`, { waitUntil: 'domcontentloaded' })
  if (mobile) { await page.waitForTimeout(2500); return { ctx, page, errors, run: {} } }
  try {
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 30000 })
  } catch (e) {
    console.log('EDITOR DID NOT OPEN', errors.slice(0, 3).join(' | '), (await page.innerText('body').catch(() => '')).slice(0, 300))
    throw e
  }

  const loadXI = async () => {
    await press(page.getByRole('button', { name: /^Data$/i }))
    await page.waitForTimeout(400)
    await press(page.getByRole('button', { name: /South Perth/ }))
    await page.waitForTimeout(900)
    await tab(page, 'Content')
    await page.waitForTimeout(200)
  }
  const importResult = async () => {
    await page.getByPlaceholder(/Match link from play\.cricket/).first().fill('m1')
    await page.getByRole('button', { name: /^(Import|Fetch)$/ }).first().click()
    await page.waitForTimeout(1200)
  }
  // Finds the photo input wherever its panel is, sends the file and takes the crop.
  const addPhoto = async (file, testid) => {
    if (!file) return false
    for (const t of ['Content', 'Design', 'Data', 'Content']) {
      const input = page.getByTestId(testid || 'hero-photo-input')
      if (await input.count()) {
        await input.first().setInputFiles(file)
        try { await page.getByRole('button', { name: /^Apply$/ }).waitFor({ timeout: 8000 }); await page.waitForTimeout(500); await page.getByRole('button', { name: /^Apply$/ }).click() } catch { /* no crop step */ }
        await page.waitForTimeout(1200)
        return true
      }
      await tab(page, t)
      await page.waitForTimeout(300)
    }
    return false
  }
  const prepare = async ({ cutout, photo, ...opts }) => {
    if (layout === 'T13') { await loadXI(); await addPhoto(cutout) }
    if (layout === 'C5') {
      await tab(page, 'Content')
      await page.waitForTimeout(300)
      await press(page.getByRole('button', { name: /Pullinger, George/ }))
      await page.waitForTimeout(400)
      await tab(page, 'Design')
      await page.waitForTimeout(300)
      await press(page.getByRole('button', { name: /Giant Type/ }))
      await page.waitForTimeout(500)
      await tab(page, 'Content')
      await page.waitForTimeout(300)
      const fill = async (ph, v) => { const el = page.getByPlaceholder(ph).first(); if (await el.count()) await el.fill(v) }
      await fill('APPOINTMENT', opts.kind || 'CAPTAIN')
      await fill('NAMED CAPTAIN', opts.headline || 'FIRST XI')
      await fill('FOR THE 2025-26 SEASON', opts.sub || '1ST GRADE · 2026-27')
      await press(page.getByRole('button', { name: /^Hero Image$/ }))
      await addPhoto(cutout)
    }
    if (layout === 'RS8') { await importResult(); await addPhoto(photo, 'highlights-photo-input') }
  }
  return { ctx, page, errors, run: { prepare, loadXI, importResult, addPhoto } }
}
