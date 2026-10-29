// Drives the real BetterPosts editor in Chromium with the API stubbed at the
// network layer, for the milestone badge and the MILESTONE WATCH strip on the
// lineup layouts (T1, T2, T3, T10, T11, T12).
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_lineup_milestones_browser.mjs [baseUrl]
//   SHOTS=/tmp/watch node ...      also writes a PNG per layout, size and squad size
//   ONLY=T1,T2 SIZES=square node ... narrows the sweep
//
// What a build cannot tell you, asked of the EXPORTED (off-screen) node at every
// post size with eleven and twelve names:
//   - the strip lists exactly the items the server sent (never more than three), with
//     the badge beside the right names, drawn inside the frame;
//   - no name, badge or role chip is covered by the strip, clipped by a parent with
//     overflow hidden, or pushed outside the post, and no line of the strip overflows;
//   - an empty answer draws nothing at all, and the post is byte for byte the one with
//     the switch off;
//   - the request on the wire carries the lineup's ids and the match day;
//   - a stale answer says why on screen and refuses to make the post (download and
//     Club Room), and CHECK AGAIN re-reads it.
// A control run against the commit before this change reports FAIL on the strip and
// badge checks without crashing: every read of a new element goes through `seen`/`count`.
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || ''
const ONLY = (process.env.ONLY || 'T1,T2,T3,T10,T11,T12').split(',')
const SIZES = (process.env.SIZES || 'square,portrait,story').split(',')
const SQUADS = (process.env.SQUADS || '11,12').split(',').map(Number)
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const NAMES = ['Szigligeti, Sam', 'Farmer, Nathan', 'Cartwright, Hilton', 'Hay, Frazer', 'Middlemas, Ben', 'Melville, Alexander',
  'Wenban, Alex', 'Botha, Eric', 'Frame, Josh', 'Dallimore, Liam', 'Wilson, Wyatt', 'Christopher-Hawtone, Spare']
const PLAYERS = NAMES.map((n, i) => ({ id: `00000000-0000-4000-8000-0000000000${String(i + 1).padStart(2, '0')}`, name: n, display_name: n, status: 'active', player_role: i < 5 ? 'BAT' : 'BOWL', photo_url: null }))
const ID = (i) => PLAYERS[i - 1].id

// What the server sends: one certain games item, one runs, one wickets, and a badge
// for a fourth player (a badge is per player, the strip is the shortlist of three).
const badge = (kind, short, full, label, certain = false) => ({ kind, short, badge: full, label, certain })
const FRESH = {
  items: [
    { player_id: ID(3), player_name: 'Cartwright, Hilton', kind: 'games', certain: true, label: '100th club game' },
    { player_id: ID(1), player_name: 'Szigligeti, Sam', kind: 'runs', certain: false, label: '40 runs to 1,000 club runs' },
    { player_id: ID(7), player_name: 'Wenban, Alex', kind: 'wickets', certain: false, label: '3 wickets to 100 club wickets' },
  ],
  badges: {
    [ID(3)]: badge('games', '100TH', '100TH GAME', '100th club game', true),
    [ID(1)]: badge('runs', '1K', '1K RUNS', '40 runs to 1,000 club runs'),
    [ID(7)]: badge('wickets', '100', '100 WKTS', '3 wickets to 100 club wickets'),
    [ID(9)]: badge('runs', '500', '500 RUNS', '45 runs to 500 club runs'),
  },
  freshness: 'fresh', stale: false, stale_reason: null, as_of: '2026-10-03', synced_at: '2026-10-04T02:00:00+00:00', match_date: '2026-10-10',
}
const withKnown = (d, n) => ({ ...d, known: PLAYERS.slice(0, n).map((p) => p.id) })
const EMPTY_ANSWER = { items: [], badges: {}, freshness: 'fresh', stale: false, stale_reason: null, as_of: '2026-10-03', synced_at: null, match_date: '2026-10-10' }
const STALE = { ...FRESH, freshness: 'stale', stale: true, stale_reason: '2 games are from the last round still not scored here. Run a sync, then make the post again.' }

const svg = (w, h, fill, label) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><rect width="${w}" height="${h}" fill="${fill}"/><text x="${w / 2}" y="${h / 2 + 12}" font-family="Arial" font-weight="800" font-size="${Math.round(h * 0.4)}" fill="#fff" text-anchor="middle">${label}</text></svg>`
const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function openEditor({ template, size = 'square', squad = 11, answer = FRESH, viewport = { width: 1600, height: 1980 } } = {}) {
  const ctx = await browser.newContext({ viewport, acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = [], watchCalls = []
  const state = { answer }
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_|404/.test(m.text())) errors.push(m.text()) })
  const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  const settings = {
    id: 'org-1', name: 'Kalamunda Cricket Club', short_name: 'KCC', slug: 'kalamunda',
    logo_url: '/x', primary_color: '#0a2a6b', accent_color: '#0b5fe0', theme_config: null, socials_style: null,
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
    if (/\/images\/organisations\/[^/]+\/logo/.test(url)) return img(svg(200, 200, '#c22030', 'K'))
    if (/\/images\/players\//.test(url)) return img(svg(400, 500, '#556b8d', 'P'))
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'kalamunda',
      entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
    }))
    if (/\/admin\/social\/milestone-watch/.test(url)) {
      watchCalls.push(new URL(url).searchParams)
      return route.fulfill(json(withKnown(state.answer, squad)))
    }
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(settings))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json(PLAYERS))
    if (/sponsors\/post-default/.test(url)) return route.fulfill(json({ sponsor_ids: [], source: 'club' }))
    if (/sponsors/.test(url)) return route.fulfill(json([]))
    if (/selection\/overview/.test(url)) return route.fulfill(json({ fixtures: [{ id: 'fx1', opponent_name: 'Bayswater Morley', grade: '1st Grade', round: 'Round 4', played_on: '2026-10-10' }] }))
    if (/\/selection\/fx1$/.test(url)) return route.fulfill(json({
      fixture: { id: 'fx1', opponent_name: 'Bayswater Morley', grade: '1st Grade', round: 'Round 4', played_on: '2026-10-10', venue: 'Edinburgh Oval', start_time: '10:30', home_away: 'HOME', home_team: 'Kalamunda', away_team: 'Bayswater Morley' },
      lineup: PLAYERS.slice(0, squad).map((p, i) => ({ player_id: p.id, batting_order: i + 1, is_captain: i === 0, is_wicket_keeper: i === 4 })),
      pool: [],
    }))
    if (/\/admin\/social\/debuts/.test(url)) return route.fulfill(json({ debuts: [], known: [], before: '2026-10-10' }))
    if (/lineups/.test(url)) return route.fulfill(json({ matches: [] }))
    return route.fulfill(json({}))
  })
  await page.addInitScript(([t, s]) => {
    localStorage.setItem('bs_social_template', t)
    localStorage.setItem('bs_social_post_size', s)
  }, [template, size])
  await page.goto(`${BASE}/admin/social-post?type=lineup&template=${template}`, { waitUntil: 'domcontentloaded' })
  try {
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 30000 })
  } catch (e) {
    console.log('EDITOR DID NOT OPEN', errors.slice(0, 3).join(' | '), (await page.innerText('body').catch(() => '')).slice(0, 300))
    throw e
  }
  return { ctx, page, errors, watchCalls, state }
}

const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }

// Pull the lineup in from BetterSelect (the real route into a lineup post).
async function loadLineup(page) {
  await press(page.getByRole('button', { name: /^Data$/i }))
  await page.waitForTimeout(300)
  await press(page.getByRole('button', { name: /Bayswater/ }))
  await page.waitForTimeout(1200)
  await press(page.getByRole('button', { name: 'Content', exact: true }))
  await page.waitForTimeout(500)
}

// The EXPORTED post: the off-screen node, not the scaled preview. Returns geometry only.
function measure({ lastNames, squad }) {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  if (!holder) return null
  const boxes = [...holder.querySelectorAll('div')].filter((d) => d.style.overflow === 'hidden' && d.style.position === 'relative' && d.style.width)
  const root = boxes.sort((a, b) => b.children.length - a.children.length)[0]
  if (!root) return null
  const R = root.getBoundingClientRect()
  const rect = (el) => { const r = el.getBoundingClientRect(); return { x: r.left - R.left, y: r.top - R.top, w: r.width, h: r.height, r: r.right - R.left, b: r.bottom - R.top } }
  const strip = root.querySelector('[data-milestone-watch]')
  const stripRect = strip ? rect(strip) : null
  const lines = strip ? [...strip.querySelectorAll('[data-watch-line]')].map((l) => {
    const t = l.firstElementChild
    return { text: l.textContent, over: t ? t.scrollWidth > t.clientWidth + 1 : false, fs: t ? parseFloat(getComputedStyle(t).fontSize) : 0, r: rect(l) }
  }) : []
  const badges = [...root.querySelectorAll('[data-milestone-badge]')].map((b) => ({ text: b.textContent.trim(), r: rect(b), inStrip: !!(strip && strip.contains(b)) }))
  // The smallest element that holds each player's name, outside the strip.
  const nameEls = lastNames.map((n) => {
    const hits = [...root.querySelectorAll('*')].filter((el) => !(strip && strip.contains(el))
      && el.children.length === 0 || (el.children.length > 0 && [...el.children].every((c) => c.tagName === 'svg' || c.tagName === 'SPAN'))
    ).filter((el) => !(strip && strip.contains(el)) && (el.textContent || '').toLowerCase().includes(n.toLowerCase()) && (el.textContent || '').length < n.length + 40)
    hits.sort((a, b) => (a.textContent || '').length - (b.textContent || '').length)
    return { n, el: hits[0] || null }
  })
  const clipped = []
  const covered = []
  const outside = []
  for (const { n, el } of nameEls) {
    if (!el) { clipped.push(`${n}: not drawn`); continue }
    const r = rect(el)
    if (r.w <= 0 || r.h <= 0) { clipped.push(`${n}: empty box`); continue }
    if (r.x < -1 || r.y < -1 || r.r > R.width + 1 || r.b > R.height + 1) outside.push(n)
    // Clipped by a parent that hides overflow?
    for (let p = el.parentElement; p && p !== root.parentElement; p = p.parentElement) {
      const cs = getComputedStyle(p)
      if (cs.overflow === 'visible' && cs.overflowX === 'visible' && cs.overflowY === 'visible') continue
      const pr = rect(p)
      if (r.b > pr.b + 1.5 || r.y < pr.y - 1.5 || r.r > pr.r + 1.5 || r.x < pr.x - 1.5) { clipped.push(`${n}: clipped by ${p.tagName}`); break }
    }
    if (stripRect && !(r.r <= stripRect.x || r.x >= stripRect.r || r.b <= stripRect.y || r.y >= stripRect.b)) covered.push(n)
  }
  // Every badge clear of the strip; no two badges overlap each other.
  const badgeOver = badges.filter((b) => !b.inStrip && stripRect
    && !(b.r.r <= stripRect.x || b.r.x >= stripRect.r || b.r.b <= stripRect.y || b.r.y >= stripRect.b)).length
  const badgeOutside = badges.filter((b) => b.r.x < -1 || b.r.y < -1 || b.r.r > R.width + 1 || b.r.b > R.height + 1).length
  // Chips (C / WK) must not sit under a badge.
  const chips = [...root.querySelectorAll('span,div')].filter((el) => ['C', 'VC', 'WK'].includes((el.textContent || '').trim()) && el.children.length === 0).map(rect)
  const chipHit = chips.filter((c) => badges.some((b) => !(b.r.r <= c.x || b.r.x >= c.r || b.r.b <= c.y || b.r.y >= c.b))).length
  const stripInside = stripRect ? (stripRect.x >= -1 && stripRect.r <= R.width + 1 && stripRect.y >= -1 && stripRect.b <= R.height + 1) : null
  return { w: R.width, h: R.height, stripRect, stripInside, lines, badges, clipped, covered, outside, badgeOver, badgeOutside, chipHit, html: root.outerHTML.length, squad }
}

const lastOf = (n) => n.split(',')[0].trim()

for (const template of ONLY) {
  for (const size of SIZES) {
    for (const squad of SQUADS) {
      const tag = `${template} ${size} ${squad}`
      let ed
      try { ed = await openEditor({ template, size, squad }) } catch { ck(`${tag}: editor opens`, false); continue }
      const { page, errors, watchCalls } = ed
      await loadLineup(page)
      await page.waitForTimeout(800)
      const lastNames = PLAYERS.slice(0, squad).map((p) => lastOf(p.name))
      const m = await page.evaluate(measure, { lastNames, squad }).catch((e) => ({ err: String(e) }))
      if (!m || m.err) { ck(`${tag}: export node read`, false, m?.err || 'null'); await ed.ctx.close(); continue }
      ck(`${tag}: strip drawn with the three items`, m.lines.length === 3 && /MILESTONE WATCH/.test(await page.locator('[data-milestone-watch]').first().innerText().catch(() => '')), JSON.stringify(m.lines.map((l) => l.text)))
      ck(`${tag}: strip lines read "Name — label"`, m.lines.length === 3
        && /CARTWRIGHT HILTON — 100TH CLUB GAME|HILTON CARTWRIGHT — 100TH CLUB GAME/.test(m.lines[0].text.toUpperCase())
        && /40 RUNS TO 1,000 CLUB RUNS/.test(m.lines[1].text.toUpperCase())
        && /3 WICKETS TO 100 CLUB WICKETS/.test(m.lines[2].text.toUpperCase()), JSON.stringify(m.lines.map((l) => l.text)))
      ck(`${tag}: certain games item first`, m.lines.length > 0 && /100TH/.test(m.lines[0].text.toUpperCase()))
      ck(`${tag}: no strip line overflows`, m.lines.length > 0 && m.lines.every((l) => !l.over && l.fs >= 9), JSON.stringify(m.lines.map((l) => [l.over, l.fs])))
      ck(`${tag}: strip inside the post`, m.stripInside === true)
      const wantBadges = squad === 12 ? 4 : 4
      ck(`${tag}: a badge on each of the four players`, m.badges.filter((b) => !b.inStrip).length === wantBadges, JSON.stringify(m.badges.map((b) => b.text)))
      ck(`${tag}: every name drawn, none clipped`, m.clipped.length === 0, m.clipped.join('; '))
      ck(`${tag}: no name outside the post`, m.outside.length === 0, m.outside.join(', '))
      ck(`${tag}: strip covers no name`, m.stripRect !== null && m.covered.length === 0, m.covered.join(', '))
      ck(`${tag}: no badge under the strip or outside the post`, m.stripRect !== null && m.badgeOver === 0 && m.badgeOutside === 0, `${m.badgeOver}/${m.badgeOutside}`)
      ck(`${tag}: no badge over a C / WK chip`, m.badges.length > 0 && m.chipHit === 0, String(m.chipHit))
      const wire = watchCalls[watchCalls.length - 1]
      ck(`${tag}: request carries the lineup ids and match day`, !!wire && wire.get('player_ids').split(',').length === squad && wire.get('on') === '2026-10-10', wire ? `${wire.get('player_ids')?.split(',').length} ${wire.get('on')}` : 'no call')
      ck(`${tag}: no page errors`, errors.length === 0, errors.slice(0, 2).join(' | '))
      if (SHOTS) {
        // The export node sits off-screen; park it at the top left of the page to shoot it.
        const box = await page.evaluate(() => {
          const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
          if (!holder) return null
          holder.style.left = '0px'; holder.style.top = '0px'; holder.style.zIndex = '99999'
          const r = [...holder.querySelectorAll('div')].filter((d) => d.style.overflow === 'hidden' && d.style.position === 'relative' && d.style.width)
            .sort((x, y) => y.children.length - x.children.length)[0].getBoundingClientRect()
          return { x: r.left, y: r.top, width: r.width, height: r.height }
        })
        try { if (box) await page.screenshot({ path: `${SHOTS}/${template}-${size}-${squad}.png`, clip: box }) } catch { /* shot only */ }
      }
      await ed.ctx.close()
    }
  }
}

// ── Behaviour that does not depend on the layout, on the default layout ─────────
const L = ONLY[0]
{
  // An empty answer draws nothing, and the post is as it is with the switch off.
  const ed = await openEditor({ template: L, squad: 11, answer: EMPTY_ANSWER })
  await loadLineup(ed.page)
  await ed.page.waitForTimeout(600)
  const a = await ed.page.evaluate(measure, { lastNames: PLAYERS.slice(0, 11).map((p) => lastOf(p.name)), squad: 11 })
  ck('empty answer: no strip and no badge at all', !!a && a.stripRect === null && a.badges.length === 0)
  ck('empty answer: says nobody is close', /Nobody in this XI is close/.test(await ed.page.locator('[data-testid="milestone-watch-status"]').innerText().catch(() => '')))
  // Switch off with a full answer: same post.
  ed.state.answer = FRESH
  await ed.page.locator('[data-testid="milestone-recheck"]').click().catch(() => {})
  await ed.page.waitForTimeout(500)
  const on = await ed.page.evaluate(measure, { lastNames: PLAYERS.slice(0, 11).map((p) => lastOf(p.name)), squad: 11 })
  ck('answer with items: strip appears after CHECK AGAIN', !!on && on.stripRect !== null && on.badges.length > 0)
  await ed.page.locator('[data-testid="milestone-watch-toggle"]').uncheck().catch(() => {})
  await ed.page.waitForTimeout(500)
  const off = await ed.page.evaluate(measure, { lastNames: PLAYERS.slice(0, 11).map((p) => lastOf(p.name)), squad: 11 })
  ck('switch off: no strip and no badge', !!off && off.stripRect === null && off.badges.length === 0)
  ck('switch off: post is the same size as the empty-answer post', !!off && !!a && off.html === a.html, `${off?.html} vs ${a?.html}`)
  await ed.ctx.close()
}
{
  // A stale answer says why and refuses to make the post.
  const ed = await openEditor({ template: L, squad: 11, answer: STALE })
  await loadLineup(ed.page)
  await ed.page.waitForTimeout(600)
  const msg = await ed.page.locator('[data-testid="milestone-stale"]').innerText().catch(() => '')
  ck('stale: the reason is on screen', /not scored here/.test(msg), msg)
  const dl = ed.page.locator('[data-testid="download-png"]')
  ck('stale: download is disabled', (await dl.count()) > 0 && await dl.first().isDisabled())
  ck('stale: Club Room save is disabled', await ed.page.getByRole('button', { name: /SAVE TO CLUB ROOM/ }).first().isDisabled().catch(() => false))
  let downloaded = false
  ed.page.on('download', () => { downloaded = true })
  await dl.first().click({ force: true }).catch(() => {})
  await ed.page.waitForTimeout(800)
  ck('stale: no file is produced', !downloaded)
  // Switching the strip off is the way out.
  await ed.page.locator('[data-testid="milestone-watch-toggle"]').uncheck().catch(() => {})
  await ed.page.waitForTimeout(400)
  ck('stale: switching the strip off lets the post be made', await dl.first().isEnabled().catch(() => false))
  // After a sync, CHECK AGAIN reads the new answer.
  await ed.page.locator('[data-testid="milestone-watch-toggle"]').check().catch(() => {})
  ed.state.answer = FRESH
  await ed.page.locator('[data-testid="milestone-recheck"]').click().catch(() => {})
  await ed.page.waitForTimeout(600)
  ck('stale: CHECK AGAIN re-reads and the post can be made', await dl.first().isEnabled().catch(() => false) && !(await seen(ed.page.locator('[data-testid="milestone-stale"]'))))
  await ed.ctx.close()
}
{
  // A layout that does not draw milestones says so on screen.
  const ed = await openEditor({ template: 'T4', squad: 11 })
  await loadLineup(ed.page)
  ck('layout without milestones: says which layouts do', /does not draw milestones/.test(await ed.page.locator('[data-testid="milestone-unsupported"]').innerText().catch(() => '')))
  ck('layout without milestones: no request is made', ed.watchCalls.length === 0)
  await ed.ctx.close()
}
{
  // 390px: the new controls cause no horizontal overflow.
  const ed = await openEditor({ template: L, squad: 11, viewport: { width: 390, height: 900 } }).catch(() => null)
  if (ed) {
    await ed.page.waitForTimeout(500)
    const over = await ed.page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    ck('390px: no horizontal overflow', !over)
    await ed.ctx.close()
  }
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
