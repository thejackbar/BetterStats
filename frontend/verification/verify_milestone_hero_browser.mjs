// BetterPosts lineup: with the Milestone watch on, the hero photo defaults to the player the
// watch has badged (and "Mark the player in the photo" comes on by itself). Real editor in
// Chromium, API stubbed at the network layer, read off the EXPORTED node.
//   npx vite preview --port 5197 &   node verification/verify_milestone_hero_browser.mjs [baseUrl]
// Every "X is the hero" check is paired with one where another player is, and a control run
// on the previous commit reports FAIL (reads go through seen/press, nothing crashes).
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

async function openEditor({ template, size = 'square', squad = 11, answer = FRESH, photos = [0,1,2,3,4,5,6,7,8], viewport = { width: 1600, height: 1980 } } = {}) {
  const ctx = await browser.newContext({ viewport, acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = [], watchCalls = []
  const state = { answer, photos: new Set(photos) }
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
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json(PLAYERS.map((p, i) => ({ ...p, photo_url: state.photos.has(i) ? 'x' : null }))))
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

const ids = (n) => PLAYERS.slice(0, n)
const heroIds = (page) => page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  if (!holder) return null
  return [...holder.querySelectorAll('img')].map((i) => (i.getAttribute('src') || '').match(/players\/([^/]+)\//)?.[1]).filter(Boolean)
})
const exportHtml = (page) => page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  return holder ? holder.innerHTML : null
})
const markBox = (page) => page.locator('[data-testid="mark-hero"] input')
const checked = async (page) => { try { return (await markBox(page).count()) ? await markBox(page).first().isChecked() : null } catch { return null } }
const heroSelect = (page) => page.locator('select').filter({ has: page.locator('option', { hasText: /^Auto(:| —)/ }) }).first()
const autoText = async (page) => { try { return await heroSelect(page).locator('option[value=""]').first().textContent() } catch { return null } }
const ONE = { ...FRESH, items: [FRESH.items[0]], badges: { [ID(3)]: FRESH.badges[ID(3)] } }

for (const template of (process.env.ONLY || 'T1,T3').split(',')) {
  console.log(`--- ${template}`)
  // A. captain is player 1; the certain 100th game belongs to player 3 and everyone has a photo
  {
    const { ctx, page, errors } = await openEditor({ template })
    await loadLineup(page)
    const h = await heroIds(page)
    ck(`${template} A hero photo is the milestone player (player 3), not the captain`, !!h && h.includes(ID(3)) && !h.includes(ID(1)), JSON.stringify(h))
    ck(`${template} A the photo of the captain is NOT in the hero slot`, !!h && !h.includes(ID(1)), JSON.stringify(h))
    ck(`${template} A Mark the player in the photo is on by itself`, (await checked(page)) === true, String(await checked(page)))
    ck(`${template} A Auto option names the milestone player`, /Cartwright/.test(await autoText(page) || '') && /milestone/i.test(await autoText(page) || ''), String(await autoText(page)))
    const on = await exportHtml(page)
    // D. the club turns the mark off: it stays off, the hero stays put, the post changes
    if (await seen(markBox(page))) await markBox(page).first().uncheck()
    await page.waitForTimeout(400)
    const off = await exportHtml(page)
    const h2 = await heroIds(page)
    ck(`${template} D unticking the mark sticks`, (await checked(page)) === false)
    ck(`${template} D hero stays the milestone player after unticking`, !!h2 && h2.includes(ID(3)), JSON.stringify(h2))
    ck(`${template} D the export node changes when the mark goes off`, !!on && !!off && on !== off)
    // C. a Hero Player picked by hand wins, and the mark goes back to its own default (off)
    const sel = heroSelect(page)
    const handPick = async (id) => { try { await sel.selectOption(id); return true } catch { return false } }
    ck(`${template} C hero player picker found`, await handPick(ID(5)))
    await page.waitForTimeout(400)
    const h3 = await heroIds(page)
    ck(`${template} C a hand-picked hero (player 5) is used, not the milestone player`, !!h3 && h3.includes(ID(5)) && !h3.includes(ID(3)), JSON.stringify(h3))
    // back to Auto: the milestone player returns
    await handPick('')
    await page.waitForTimeout(400)
    const h4 = await heroIds(page)
    ck(`${template} C Auto again returns the milestone player`, !!h4 && h4.includes(ID(3)), JSON.stringify(h4))
    // F. switch the watch off: captain again, mark off
    await press(page.getByTestId('milestone-watch-toggle'))
    await page.waitForTimeout(500)
    const h5 = await heroIds(page)
    ck(`${template} F watch off: hero is the captain again`, !!h5 && h5.includes(ID(1)) && !h5.includes(ID(3)), JSON.stringify(h5))
    ck(`${template} F watch off: no auto mark`, (await checked(page)) === false, String(await checked(page)))
    ck(`${template} no page errors (A)`, errors.length === 0, errors.slice(0, 2).join(' | '))
    await ctx.close()
  }
  // B. nobody has a milestone: captain, mark off (the pair for A)
  {
    const { ctx, page } = await openEditor({ template, answer: EMPTY_ANSWER })
    await loadLineup(page)
    const h = await heroIds(page)
    ck(`${template} B no milestones: hero is the captain`, !!h && h.includes(ID(1)) && !h.includes(ID(3)), JSON.stringify(h))
    ck(`${template} B no milestones: mark off`, (await checked(page)) === false, String(await checked(page)))
    ck(`${template} B Auto option keeps its old wording`, /captain/i.test(await autoText(page) || ''), String(await autoText(page)))
    await ctx.close()
  }
  // E. the only badged player has no photo: captain leads, and the page says why
  {
    const { ctx, page } = await openEditor({ template, answer: ONE, photos: [0, 1, 3, 4] })
    await loadLineup(page)
    const h = await heroIds(page)
    ck(`${template} E badged player has no photo: hero is the captain`, !!h && h.includes(ID(1)) && !h.includes(ID(3)), JSON.stringify(h))
    ck(`${template} E the page explains the choice`, await seen(page.getByTestId('milestone-hero-nophoto')))
    ck(`${template} E mark stays off`, (await checked(page)) === false, String(await checked(page)))
    await ctx.close()
  }
  // G. two badged players: the certain one beats the runs one even with a photo each
  {
    const { ctx, page } = await openEditor({ template, answer: { ...FRESH, items: [FRESH.items[1], FRESH.items[2]], badges: { [ID(1)]: FRESH.badges[ID(1)], [ID(7)]: FRESH.badges[ID(7)], [ID(3)]: FRESH.badges[ID(3)] } } })
    await loadLineup(page)
    const h = await heroIds(page)
    ck(`${template} G certain milestone outranks the others`, !!h && h.includes(ID(3)) && !h.includes(ID(7)), JSON.stringify(h))
    await ctx.close()
  }
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
