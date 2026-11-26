// Match Cards (RR8): drives the REAL BetterPosts editor in Chromium with the API stubbed at the network layer.
//
// Asked for (Willetton-style results post, Nov 2026): a Results template on the club's own uploaded photo,
// one card per match that reads right for a game in play ("1ST XI NEED 188 TO WIN") as well as a finished one
// ("CROWS WIN BY 95 RUNS"), with colour for wins and losses.
//
//   npx vite build --outDir /var/tmp/rr8_dist && npx vite preview --outDir /var/tmp/rr8_dist --port 5199 &
//   PHOTO=/path/photo.jpg SHOTS=/path/dir node verification/verify_results_cards_browser.mjs [baseUrl]
//
// Reads the OFF-SCREEN EXPORT NODE (what the PNG is made from), not the scaled preview.
import { existsSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const PHOTO = process.env.PHOTO || ''
const SHOTS = process.env.SHOTS || ''
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
const SETTINGS = { id: 'org-1', name: 'Willetton Cricket Club', short_name: 'Willetton', slug: 'willetton', logo_url: null, primary_color: '#0b2a4a', accent_color: '#8fd3ff', theme_config: null }
const ME = { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'willetton', entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' } }
const SPONSOR = (i) => `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="120"><rect width="300" height="120" fill="${['#1d3557', '#e63946', '#2a9d8f'][i % 3]}"/><text x="150" y="72" font-size="40" text-anchor="middle" fill="#fff" font-family="sans-serif">SPONSOR ${i + 1}</text></svg>`

// The round as the server builds it (social_rounds._result_row): a two-day game at the end of day one
// each way round, and a finished one-dayer.
const ROUND = {
  season: '2026/27',
  dates: [{
    label: 'SAT 21 NOV', round: 'ROUND 8',
    results: [
      { grade: '1ST GRADE', teamLabel: '1ST XI', round: 'ROUND 8', opp: 'JANDAKOT PARK', oppMono: 'JP', us: '-', them: '187', themOvers: '68.5',
        battedFirst: 'them', outcome: 'LIVE', live: true, margin: 'IN PROGRESS',
        topBat: [], topBowl: [{ name: 'E BUTCHER', line: '3/20 (12.5)' }] },
      { grade: '4TH GRADE', teamLabel: '2ND XI', round: 'ROUND 8', opp: 'JANDAKOT PARK', oppMono: 'JP', us: '219', usOvers: '74.5', them: '-',
        battedFirst: 'us', outcome: 'LIVE', live: true, margin: 'IN PROGRESS',
        topBat: [{ name: 'J FLORISSON', line: '43 (61)' }], topBowl: [] },
      { grade: 'ONE DAY C', teamLabel: '3RD XI', round: 'ROUND 7', opp: 'CANNINGTON TIGERS', oppMono: 'CT', us: '8/271', usOvers: '40', them: '8/176', themOvers: '40',
        battedFirst: 'us', outcome: 'W', margin: 'BY 95 RUNS',
        topBat: [{ name: 'D DAVEY', line: '97 (55)' }], topBowl: [{ name: 'T WALKER', line: '4/41 (8)' }] },
      { grade: 'ONE DAY D', teamLabel: '4TH XI', round: 'ROUND 7', opp: 'SOUTH PERTH', oppMono: 'SP', us: '142', usOvers: '33.4', them: '3/143', themOvers: '28.1',
        battedFirst: 'us', outcome: 'L', margin: 'BY 7 WICKETS',
        topBat: [{ name: 'K LEE', line: '38 (40)' }], topBowl: [{ name: 'M ROSS', line: '2/30 (7)' }] },
    ],
  }],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
const photoBytes = PHOTO && existsSync(PHOTO) ? readFileSync(PHOTO) : null

async function openEditor({ viewport = { width: 1700, height: 2300 }, size = 'square', withPhoto = true, nSponsors = 3, mobile = false } = {}) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const errors = []
  const wire = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_|404|fonts/.test(m.text())) errors.push(m.text()) })
  const sponsors = Array.from({ length: nSponsors }, (_, i) => ({ id: `s${i + 1}`, name: `Sponsor ${i + 1}`, logo_url: '/x', tier: 'major' }))
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort())
  await page.route('**/rr8-photo.jpg', (r) => (photoBytes ? r.fulfill({ status: 200, contentType: 'image/jpeg', body: photoBytes }) : r.abort()))
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    wire.push(url)
    if (/\/images\/sponsors\/s(\d+)\/logo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: SPONSOR(Number(url.match(/s(\d+)\/logo/)[1]) - 1) })
    if (/\/auth\/me/.test(url)) return route.fulfill(json(ME))
    if (/\/admin\/social\/results/.test(url)) return route.fulfill(json(ROUND))
    if (/\/admin\/social\/templates/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json(/kind=background/.test(url) && withPhoto ? [{ id: 'bg1', name: 'huddle.jpg', url: `${BASE}/rr8-photo.jpg` }] : []))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json([]))
    if (/sponsors\/post-default/.test(url)) return route.fulfill(json({ sponsor_ids: sponsors.map((x) => x.id), source: 'club' }))
    if (/sponsors/.test(url)) return route.fulfill(json(sponsors))
    return route.fulfill(json({}))
  })
  await page.addInitScript(([s, photo, base]) => {
    localStorage.setItem('bs_social_template', 'RR8')
    localStorage.setItem('bs_social_post_size', s)
    localStorage.setItem('bs_social_short_names', '1')
    if (photo) { localStorage.setItem('bs_social_bg', 'custom-image'); localStorage.setItem('bs_social_bg_url', `${base}/rr8-photo.jpg`) }
  }, [size, withPhoto, BASE])
  await page.goto(`${BASE}/admin/social-post?type=results&template=RR8`, { waitUntil: 'domcontentloaded' })
  if (mobile) { await page.waitForTimeout(2500); return { ctx, page, errors, wire } }
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 30000 })
  return { ctx, page, errors, wire }
}
const visible = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* the check reports it */ } return false }
async function reveal(page, loc) {
  for (const t of ['Content', 'Data', 'Design', null]) {
    if (await visible(loc)) return true
    if (t) { await press(page.getByRole('button', { name: t, exact: true })); await page.waitForTimeout(300) }
  }
  return visible(loc)
}
async function pull(page) {
  await reveal(page, page.getByRole('button', { name: /Pull latest round/ }))
  await press(page.getByRole('button', { name: /Pull latest round/ }))
  await page.waitForTimeout(1500)
}
const setSize = async (page, label) => {
  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await press(page.getByRole('button', { name: new RegExp(`^${label}`) }))
  await page.waitForTimeout(700)
}

// The exported post, read off the off-screen node.
const ROOT = () => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  if (!holder) return null
  const boxes = [...holder.querySelectorAll('div')].filter((d) => d.style.overflow === 'hidden' && d.style.position === 'relative' && d.style.width)
  return boxes.sort((a, b) => b.children.length - a.children.length)[0] || null
}
async function read(page) {
  return page.evaluate((rootSrc) => {
    const root = (new Function(`return (${rootSrc})()`))()
    if (!root) return null
    const rr = root.getBoundingClientRect()
    const rel = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.left - rr.left, y: r.top - rr.top, w: r.width, h: r.height, r: r.right - rr.left, b: r.bottom - rr.top } }
    const cards = [...root.querySelectorAll('[data-card]')].map((c) => ({
      tone: c.getAttribute('data-card'),
      edge: getComputedStyle(c).borderLeftColor,
      tag: c.querySelector('[data-tag]') ? c.querySelector('[data-tag]').innerText.trim() : '',
      tagBg: c.querySelector('[data-tag]') ? getComputedStyle(c.querySelector('[data-tag]')).backgroundColor : '',
      headline: c.querySelector('[data-headline]') ? c.querySelector('[data-headline]').innerText.trim() : '',
      headFs: c.querySelector('[data-headline]') ? parseFloat(getComputedStyle(c.querySelector('[data-headline]')).fontSize) : 0,
      headFits: (() => { const h = c.querySelector('[data-headline]'); return h ? h.getBoundingClientRect().right <= h.parentElement.getBoundingClientRect().right + 1 : false })(),
      innings: [...c.querySelectorAll('[data-innings]')].map((i) => ({ side: i.getAttribute('data-innings'), text: i.innerText.replace(/\s+/g, ' ').trim() })),
      perf: c.querySelector('[data-perf]') ? c.querySelector('[data-perf]').innerText.replace(/\s+/g, ' ').trim() : '',
      box: rel(c),
      // Content is centred, so an overflow spills both ways and scrollHeight cannot see the top half:
      // measure every line against the card's own box instead.
      clipped: (() => { const b = c.getBoundingClientRect(); return [...c.children].filter((k) => { const r = k.getBoundingClientRect(); return r.top < b.top - 0.5 || r.bottom > b.bottom + 0.5 || k.scrollHeight - k.clientHeight > 1 }).map((k) => `${k.textContent.slice(0, 16)}:${Math.round(k.getBoundingClientRect().top - b.top)}/${Math.round(k.getBoundingClientRect().bottom - b.top)}/${Math.round(b.height)}:${k.scrollHeight}>${k.clientHeight}`).join('|') || false })(),
    }))
    const grid = root.querySelector('[data-sponsor-grid]')
    const q = (n) => root.querySelector(`[data-layer="${n}"]`)
    return {
      w: rr.width, h: rr.height, cards, layers: [...root.children].map((c) => c.getAttribute('data-layer') || c.tagName.toLowerCase()),
      head: rel(q('Heading')), headText: q('Heading') ? q('Heading').innerText.replace(/\s+/g, ' ').trim() : '',
      label: q('Sponsor label') ? { ...rel(q('Sponsor label')), text: q('Sponsor label').innerText.trim() } : null,
      crest: rel(q('Club crest')),
      grid: grid ? { ...rel(grid), n: grid.querySelectorAll('img').length } : null,
      bodyText: root.innerText.replace(/\s+/g, ' '),
      photo: [...root.parentElement.querySelectorAll('*'), root].some((e) => /rr8-photo/.test(getComputedStyle(e).backgroundImage) || (e.tagName === 'IMG' && /rr8-photo/.test(e.src))),
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
const overlaps = (a, b) => a && b && a.x < b.r - 1 && b.x < a.r - 1 && a.y < b.b - 1 && b.y < a.b - 1
const rgb = (hex) => `rgb(${parseInt(hex.slice(1, 3), 16)}, ${parseInt(hex.slice(3, 5), 16)}, ${parseInt(hex.slice(5, 7), 16)})`

console.log('\n# Match Cards on the club photo, after a pull with games in progress')
{
  const { ctx, page, errors, wire } = await openEditor()
  ck('Match Cards is offered on the Results tab', await reveal(page, page.getByText('Match Cards', { exact: true })))
  ck('the editor says the layout is made for your own photo', await reveal(page, page.getByTestId('rr8-hint')))
  const inPlay = page.getByTestId('results-in-play').locator('input')
  if (await inPlay.count() && !(await inPlay.first().isChecked())) { await inPlay.first().check().catch(() => {}); await page.waitForTimeout(300) }
  wire.length = 0
  await pull(page)
  ck('the pull asks for games in progress on the wire (live=true)', wire.some((u) => /\/admin\/social\/results\?live=true$/.test(u)), wire.filter((u) => /results/.test(u)).join(' '))
  const d = await read(page)
  ck('the export node is drawn with four cards', !!d && d.cards.length === 4, d ? `${d.cards.length}` : 'no node')
  const c = d ? d.cards : []
  const at = (i) => c[i] || {}
  ck('day one, we bowled them out: "1ST XI NEED 188 TO WIN"', at(0).headline === '1ST XI NEED 188 TO WIN', at(0).headline)
  ck('...with only their innings, crest, name and score with overs', at(0).innings?.length === 1 && /JANDAKOT PARK 187 \(68\.5\)/.test(at(0).innings?.[0]?.text || ''), JSON.stringify(at(0).innings))
  ck('...and our bowler underneath', at(0).perf === 'E BUTCHER 3/20 (12.5)', at(0).perf)
  ck('day one, we batted first: "JANDAKOT PARK NEED 220 TO WIN"', at(1).headline === 'JANDAKOT PARK NEED 220 TO WIN', at(1).headline)
  ck('...our innings under our club name', /WILLETTON 219 \(74\.5\)/i.test(at(1).innings?.[0]?.text || ''), JSON.stringify(at(1).innings))
  ck('the finished game leads with the winner and margin', at(2).headline === '3RD XI WIN BY 95 RUNS', at(2).headline)
  ck('...both innings in batting order, us first', at(2).innings?.map((x) => x.side).join(',') === 'us,them' && /271\/8|8\/271/.test(at(2).innings?.[0]?.text || '') && /\(40\)/.test(at(2).innings?.[1]?.text || ''), JSON.stringify(at(2).innings))
  ck('...and the batter then the bowler', at(2).perf === 'D DAVEY 97 (55) · T WALKER 4/41 (8)', at(2).perf)
  ck('a loss names the winner and no "WIN" of ours', at(3).headline === 'SOUTH PERTH WIN BY 7 WICKETS', at(3).headline)
  ck('kicker reads team · grade · round, per row', /1ST XI · 1ST GRADE · ROUND 8/.test(d?.bodyText || '') && /3RD XI · ONE DAY C · ROUND 7/.test(d?.bodyText || ''), (d?.bodyText || '').slice(0, 200))
  // Colour: the card's edge and its tag carry the state.
  ck('tones: live, live, win, loss', c.map((x) => x.tone).join(',') === 'live,live,win,loss', c.map((x) => x.tone).join(','))
  ck('a win card has a green edge and a WIN tag on green', at(2).edge === rgb('#2fd07a') && at(2).tag === 'WIN' && at(2).tagBg === rgb('#2fd07a'), `${at(2).edge} ${at(2).tag} ${at(2).tagBg}`)
  ck('a loss card has a red edge and a LOSS tag on red', at(3).edge === rgb('#ff5d6c') && at(3).tag === 'LOSS' && at(3).tagBg === rgb('#ff5d6c'), `${at(3).edge} ${at(3).tag}`)
  ck('a game in play is amber and LIVE, never a win or a loss', at(0).edge === rgb('#f5b942') && at(0).tag === 'LIVE' && !/\bWIN\b/.test(at(0).tag) && !/LOSS|LOST|DEF/.test(at(0).headline + at(0).tag), `${at(0).edge} ${at(0).tag}`)
  ck('every headline shares one size and fits its card', c.length > 0 && new Set(c.map((x) => x.headFs)).size === 1 && c.every((x) => x.headFits), JSON.stringify(c.map((x) => [x.headFs, x.headFits])))
  ck('no card clips its own content', c.length > 0 && c.every((x) => !x.clipped), JSON.stringify(c.map((x) => x.clipped)))
  ck('the club photo is under the post', !!d?.photo)
  ck('heading reads WEEKEND RESULTS, RESULTS, the date', /WEEKEND RESULTS RESULTS SAT 21 NOV/.test(d?.headText || ''), d?.headText)
  ck('sponsor heading is drawn with logos', d?.label?.text === 'PROUDLY SPONSORED BY' && d?.grid?.n === 3, JSON.stringify([d?.label?.text, d?.grid?.n]))
  ck('the sponsor grid sits under its heading, clear of the cards and the crest',
    !!d?.grid && !!d?.label && d.grid.y >= d.label.b - 1 && !c.some((x) => overlaps(x.box, d.grid)) && !overlaps(d.crest, d.grid), JSON.stringify([d?.grid, d?.label]))

  // Who batted first, set by hand, changes the story.
  await reveal(page, page.getByTestId('rr-innings'))
  const sel = page.getByTestId('rr-innings').first().locator('select')
  ck('each row has a "batted first" control on this layout', await sel.count() > 0)
  await sel.selectOption('').catch(() => {})
  await page.waitForTimeout(400)
  let d2 = await read(page)
  ck('with batting order cleared, the one side that batted is taken as first (still the chase)', d2?.cards?.[0]?.headline === '1ST XI NEED 188 TO WIN', d2?.cards?.[0]?.headline)
  const ourOvers = page.getByTestId('rr-innings').nth(2).getByLabel('Our overs')
  if (await ourOvers.count()) { await ourOvers.fill('39.4'); await page.waitForTimeout(400) }
  d2 = await read(page)
  ck('typing our overs reaches the post', /\(39\.4\)/.test(d2?.cards?.[2]?.innings?.[0]?.text || ''), JSON.stringify(d2?.cards?.[2]?.innings))
  ck('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  if (SHOTS) await shotNode(page, `${SHOTS}/rr8-square.png`)
  for (const [label, key, h] of [['Portrait', 'portrait', 1350], ['Story', 'story', 1920]]) {
    await setSize(page, label)
    const s = await read(page)
    ck(`${label}: post is 1080x${h}`, s && Math.round(s.w) === 1080 && Math.round(s.h) === h, s ? `${s.w}x${s.h}` : 'none')
    ck(`${label}: cards fit, none clipped, headlines fit`, !!s && s.cards.length === 4 && s.cards.every((x) => !x.clipped && x.headFits && x.box.b <= s.h), JSON.stringify(s?.cards?.map((x) => [x.box?.b, x.clipped, x.headFits])))
    ck(`${label}: the sponsor grid is clear of every card`, !!s?.grid && s.cards.length === 4 && !s.cards.some((x) => overlaps(x.box, s.grid)), JSON.stringify(s?.grid))
    if (SHOTS) await shotNode(page, `${SHOTS}/rr8-${key}.png`)
  }
  await ctx.close()
}

console.log('\n# Nine grades, no sponsors')
{
  const { ctx, page, errors } = await openEditor({ nSponsors: 0 })
  // Add rows by hand until nine: the "+ Add result" button.
  await pull(page)
  await reveal(page, page.getByRole('button', { name: '+ Add result' }))
  for (let i = 0; i < 5; i++) await press(page.getByRole('button', { name: '+ Add result' }))
  await page.waitForTimeout(500)
  const d = await read(page)
  ck('nine cards drawn', d?.cards?.length === 9, `${d?.cards?.length}`)
  ck('...two across, none clipped, none past the foot', !!d && d.cards.every((x) => !x.clipped && x.box.b <= d.crest.y + 1) && new Set(d.cards.map((x) => Math.round(x.box.x))).size === 2, JSON.stringify(d?.cards?.map((x) => [Math.round(x.box.x), Math.round(x.box.b), x.clipped])))
  ck('a hand-added row with no scores reads as a plain result, not a chase', d?.cards?.[8]?.headline === 'WILLETTON WIN', d?.cards?.[8]?.headline)
  ck('no sponsors: no sponsor heading', !!d && !d.label)
  ck('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  if (SHOTS) await shotNode(page, `${SHOTS}/rr8-nine.png`)
  await ctx.close()
}

console.log('\n# 390px')
{
  const { ctx, page } = await openEditor({ viewport: { width: 390, height: 900 }, mobile: true })
  await press(page.getByRole('button', { name: 'FULL EDITOR' }))
  await page.waitForTimeout(1500)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ck('no horizontal overflow at 390px', over <= 1, `${over}px`)
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
