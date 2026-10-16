// Squad list PDF: one landscape page, columns worked out from how many names there are.
// Drives the real Squads screen and Export lists in Chromium (API stubbed), then reads
// the PDF that comes down: page count, page shape, every name present, and renders it.
//   npx vite preview --port 5199 &    node verify_squad_sheet_browser.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'
import { execFileSync } from 'node:child_process'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const OUT = process.env.SHOT_DIR || '/tmp'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }

const FIRST = ['Sam', 'Evan', 'Tess', 'Olly', 'Tom', 'Holly', 'Charlie', 'Freya', 'Jack', 'Brendan', 'Skye', 'Macy', 'Ninna', 'Ava', 'Elana', 'Zac', 'Gavin', 'Leith', 'Callum', 'James']
const LAST = ['Johnson', 'Jensen', 'Arthur', 'Barker', 'Bourke', 'Brennan', 'Brown', 'Dolling', 'Doyle', 'Franklin', 'Geier', 'Hynes', 'Jacobs', 'Anderson', 'Cairns', 'Hampton', 'Whelan']
const SIZES = [13, 50, 20, 11, 15, 12]
const TEAM_IDS = SIZES.map((_, i) => `00000000-0000-0000-0000-00000000000${i + 1}`)
const NAMES = ['Jenson A', 'Jenson B / Club Grade', 'Womens', 'MacIntyre 1s & 2s', 'Juniors U14', 'Juniors U12']
let GRADE = null
const mkTeams = (n) => TEAM_IDS.slice(0, n).map((id, i) => ({ id, name: NAMES[i], short_name: null, sequence: i + 1, is_active: true, grade_id: null, grade_name: GRADE || `Grade ${i + 1}` }))
let seq = 0
const mkPlayers = (sizes) => sizes.flatMap((n, ti) => Array.from({ length: n }, () => {
  const k = seq++
  const name = `${LAST[k % LAST.length]}, ${FIRST[k % FIRST.length]}${k >= 20 ? ` ${String.fromCharCode(65 + (k % 26))}` : ''}`
  return { id: `p${k}`, name, display_name: name, display_name_override: null, photo_url: null, gender: 'male', is_player: true, player_role: null,
    skill_positions: k % 3 === 0 ? ['BAT'] : k % 5 === 0 ? ['BOWL', 'WKT'] : [], status: 'active', is_public: true, squad_team_id: TEAM_IDS[ti], squad_team_ids: [TEAM_IDS[ti]], last_played: '2026-09-01', age: null }
}))
const ME = { id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1', club_slug: 'gisborne', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' } }

async function openAndExport(browser, sizes, { grade = null } = {}) {
  seq = 0
  GRADE = grade
  const players = mkPlayers(sizes), teams = mkTeams(sizes.length)
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json(ME)
    if (url.includes('/club-admin/settings')) return json({ name: 'Gisborne CC', short_name: 'Gisborne', player_name_format: 'first_last', theme_config: { accent: '#0a7d3b', accent2: '#e0b100' } })
    if (url.includes('/club-admin/players')) return json(players)
    if (url.includes('/availability/matrix')) return json({ dates: [], players: players.map((p) => ({ id: p.id, display_name: p.display_name, name: p.name, squads: [], is_current: true, last_played: p.last_played, player_role: null })), availability: {}, all_squads: [], dormancy_months: 24, squad_next: {}, rules: { active: false, applied: [] } })
    if (url.includes('/teams/grade-options')) return json({ seasons: [] })
    if (url.match(/\/teams(\?|$)/)) return json(teams)
    if (url.includes('/selection/selected-players')) return json({ player_ids: [] })
    if (url.includes('/fixtures')) return json([])
    return json({})
  })
  await page.goto(`${BASE}/admin/betterselect/teams`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.pb-card', { timeout: 20000 })
  await page.getByRole('button', { name: 'Export lists' }).click()
  await page.waitForSelector('[data-export-modal]')
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'PDF', exact: true }).click()])
  const file = `${OUT}/squad-sheet-${sizes.length}x${sizes.reduce((a, b) => a + b, 0)}.pdf`
  fs.copyFileSync(await dl.path(), file)
  await ctx.close()
  return { file, players, errors, name: dl.suggestedFilename() }
}

const info = (file) => execFileSync('pdfinfo', [file]).toString()
const text = (file) => execFileSync('pdftotext', ['-layout', file, '-']).toString()

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  await safe('six squads', async () => {
    console.log('\n── Six squads, 121 players ──')
    const r = await openAndExport(browser, SIZES)
    const i = info(r.file), t = text(r.file)
    check('it is one page', /Pages:\s+1\b/.test(i), i)
    check('and landscape (wider than tall)', (() => { const m = /Page size:\s+([\d.]+) x ([\d.]+)/.exec(i); return m && +m[1] > +m[2] })(), i)
    const names = r.players.map((p) => { const [l, f] = p.name.split(', '); return `${f} ${l}` })
    const missing = names.filter((n) => !t.includes(n))
    check('every one of the 121 players is on it', missing.length === 0, `missing ${missing.length}: ${missing.slice(0, 5).join(' | ')}`)
    check('every squad is headed with its name', NAMES.every((n) => t.includes(n)), NAMES.filter((n) => !t.includes(n)).join(', '))
    check('the club name and printed date are at the top', /Gisborne CC/.test(t) && /Printed /.test(t))
    check('the file is named for the club', /Gisborne - squads\.pdf$/.test(r.name), r.name)
    execFileSync('pdftoppm', ['-png', '-r', '70', r.file, `${OUT}/squad-sheet-six`])
    check('no page errors', r.errors.length === 0, r.errors.join(' | '))
  })

  await safe('one big squad', async () => {
    console.log('\n── One squad of 41 with a long list of grades ──')
    const r = await openAndExport(browser, [41], { grade: '09. Jensen Shield - North B, 10. Jensen Shield - South B, 10. Club Grade - North, 11. Club Grade - South' })
    const i = info(r.file), t = text(r.file)
    check('one landscape page', /Pages:\s+1\b/.test(i) && (() => { const m = /Page size:\s+([\d.]+) x ([\d.]+)/.exec(i); return m && +m[1] > +m[2] })(), i)
    check('all 41 names are there', r.players.every((p) => { const [l, f] = p.name.split(', '); return t.includes(`${f} ${l}`) }))
    check('the grades are written out in full across the top, not squeezed into a column', t.includes('11. Club Grade - South') && /41 players/.test(t))
    // Columns, not one long list: count distinct x positions of the numbering.
    const bbox = execFileSync('pdftotext', ['-bbox-layout', r.file, '-']).toString()
    const xs = new Set([...bbox.matchAll(/<word xMin="([\d.]+)"[^>]*>(\d+)<\/word>/g)].filter((m) => +m[2] <= 41).map((m) => Math.round(+m[1] / 40)))
    check('the names run across several columns', xs.size >= 2, [...xs].join())
    execFileSync('pdftoppm', ['-png', '-r', '70', r.file, `${OUT}/squad-sheet-one`])
  })

  await safe('one small squad', async () => {
    console.log('\n── One squad of 8 ──')
    const r = await openAndExport(browser, [8])
    const i = info(r.file)
    check('one landscape page', /Pages:\s+1\b/.test(i) && (() => { const m = /Page size:\s+([\d.]+) x ([\d.]+)/.exec(i); return m && +m[1] > +m[2] })(), i)
    check('all 8 names are there', r.players.every((p) => { const [l, f] = p.name.split(', '); return text(r.file).includes(`${f} ${l}`) }))
  })

  await safe('too many for one page', async () => {
    console.log('\n── 4 squads of 200: more than a page can hold ──')
    const r = await openAndExport(browser, [200, 200, 200, 200].concat([]))
    const i = info(r.file)
    check('it runs to more pages rather than dropping names', /Pages:\s+([2-9]|\d\d)\b/.test(i), i)
    const t = text(r.file)
    const missing = r.players.filter((p) => { const [l, f] = p.name.split(', '); return !t.includes(`${f} ${l}`) })
    check('...and still has every name', missing.length === 0, `missing ${missing.length}`)
  })

  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run()
