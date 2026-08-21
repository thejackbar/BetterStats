// Drives the real BetterSelect Squads board in Chromium with the API stubbed
// at the network layer, to check the unassigned side really splits into the
// three pools and that inactive players are off the board.
//
//   node verify_squads_ui.mjs            (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const iso = (daysAgo) => {
  const d = new Date(); d.setDate(d.getDate() - daysAgo)
  return d.toISOString().slice(0, 10)
}

const FIRSTS = '11111111-1111-1111-1111-111111111111'
const SECONDS = '22222222-2222-2222-2222-222222222222'

const P = (id, name, extra) => ({
  id, name, display_name: name, display_name_override: null, photo_url: null,
  hero_photo_url: null, gender: null, is_player: true, player_role: null,
  is_overseas: false, overseas_country: null, batting_hand: null, bowling_action: null,
  bowling_type: null, is_opening_batsman: false, skill_positions: [], status: 'active',
  is_public: true, is_financial_override: null, trained_override: null,
  squad_team_id: null, last_played: null, age: null, ...extra,
})

// last_played chosen against a 24-month dormancy window:
//   Recent   30d   → Unassigned
//   Lapsed   2.5y  → fill-ins, inside the default "≤ 3 yrs" reach
//   Ancient  4y    → fill-ins, only once the reach opens to "≤ 5 yrs"
//   Newbie   never → Not yet played
//   Gone     30d but inactive → off the board unless asked for
//   Filed    30d, in the 1st XI → stays in its squad column
//   NotAPlayer → never anywhere
const PLAYERS = [
  P('p-recent', 'Recent, Rita', { last_played: iso(30) }),
  P('p-lapsed', 'Lapsed, Larry', { last_played: iso(Math.round(365 * 2.5)) }),
  P('p-ancient', 'Ancient, Amy', { last_played: iso(365 * 4) }),
  P('p-newbie', 'Newbie, Ned', { last_played: null }),
  P('p-gone', 'Gone, Gary', { last_played: iso(30), status: 'inactive' }),
  P('p-filed', 'Filed, Fiona', { last_played: iso(30), squad_team_id: FIRSTS }),
  P('p-nonplayer', 'Treasurer, Terry', { is_player: false }),
]

const TEAMS = [
  { id: FIRSTS, name: '1st XI', short_name: '1s', sequence: 1, is_active: true, grade_id: null, grade_name: null },
  { id: SECONDS, name: '2nd XI', short_name: '2s', sequence: 2, is_active: true, grade_id: null, grade_name: null },
]

const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin',
  organisation_id: 'org-1', club_slug: 'verify-cc', capabilities: [],
  entitlements: { modules: ['select'], core_live: true, status: 'active' },
}

const MATRIX = {
  dates: [], players: [], availability: {}, all_squads: [],
  dormancy_months: 24, rules: { active: false, applied: [] },
}

async function stub(page) {
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.includes('/auth/me')) return json(ME)
    if (url.includes('/club-admin/players')) return json(PLAYERS)
    if (url.includes('/availability/matrix')) return json(MATRIX)
    if (url.includes('/teams/grade-options')) return json({ seasons: [] })
    if (url.match(/\/teams(\?|$)/)) return json(TEAMS)
    if (url.includes('/selection/selected-players')) return json({ player_ids: [] })
    return json({})
  })
}

// Column header -> the names rendered inside that column card.
async function columns(page) {
  return page.evaluate(() => {
    const out = {}
    for (const card of document.querySelectorAll('.pb-card')) {
      const title = card.querySelector('.font-display')
      if (!title) continue
      const head = title.textContent.trim()
      const names = [...card.querySelectorAll('[draggable="true"] .flex-1')].map((n) => n.textContent.trim())
      const collapsed = !card.querySelector('.pb-scroll')
      out[head] = { names, collapsed, count: card.querySelector('.pb-num')?.textContent.trim() }
    }
    return out
  })
}

const openAll = async (page) => {
  await page.getByRole('button', { name: 'Expand all' }).click()
  await page.waitForTimeout(250)
}

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  // Google Fonts / GTM / the Meta pixel are blocked in this sandbox and fail as
  // resource loads. That's the environment, not the page.
  page.on('console', (m) => {
    if (m.type() === 'error' && !/Failed to load resource|ERR_CONNECTION|ERR_NAME_NOT_RESOLVED/.test(m.text())) {
      errors.push(m.text())
    }
  })
  await stub(page)

  const go = async (qs = '') => {
    await page.goto(`${BASE}/admin/betterselect/teams${qs}`, { waitUntil: 'networkidle' })
    await page.waitForSelector('.pb-card', { timeout: 20000 })
    await page.waitForTimeout(400)
  }

  await go()

  // ── the three unassigned pools exist, and the two extras start collapsed ──
  let cols = await columns(page)
  const heads = Object.keys(cols)
  check('the Unassigned column renders', heads.includes('Unassigned'), heads.join(' | '))
  check('a "Potential fill-ins" column renders', heads.includes('Potential fill-ins'), heads.join(' | '))
  check('a "Not yet played" column renders', heads.includes('Not yet played'), heads.join(' | '))
  check('Potential fill-ins opens collapsed', cols['Potential fill-ins']?.collapsed === true)
  check('Not yet played opens collapsed', cols['Not yet played']?.collapsed === true)
  check('Unassigned opens expanded', cols['Unassigned']?.collapsed === false)

  // ── who is in which pool ────────────────────────────────────────────────
  await openAll(page)
  cols = await columns(page)
  check('Unassigned holds only the active, recently-played, unsquadded player',
    JSON.stringify(cols['Unassigned']?.names) === JSON.stringify(['Recent, Rita']),
    JSON.stringify(cols['Unassigned']?.names))
  check('a player who has dropped off is in Potential fill-ins, not Unassigned',
    cols['Potential fill-ins']?.names.includes('Lapsed, Larry'),
    JSON.stringify(cols['Potential fill-ins']?.names))
  check('a never-played player is in Not yet played, not Unassigned',
    JSON.stringify(cols['Not yet played']?.names) === JSON.stringify(['Newbie, Ned']),
    JSON.stringify(cols['Not yet played']?.names))
  check('an inactive player is on no pool at all',
    !JSON.stringify(cols).includes('Gone, Gary'))
  check('a non-player is nowhere on the board',
    !JSON.stringify(cols).includes('Treasurer, Terry'))
  check('an assigned player still shows in their squad column',
    cols['1s']?.names.includes('Filed, Fiona'), JSON.stringify(cols['1s']?.names))

  // ── the fill-in reach control ───────────────────────────────────────────
  const reachOptions = await page.evaluate(() => {
    const sel = [...document.querySelectorAll('select')].find((s) =>
      [...s.options].some((o) => o.textContent.startsWith('Fill-ins')))
    return sel ? [...sel.options].map((o) => o.textContent.trim()) : null
  })
  check('the fill-in reach control is on the toolbar', !!reachOptions, String(reachOptions))
  check('it never offers a window inside the dormancy boundary',
    reachOptions && !reachOptions.some((o) => /≤ 1 yr|≤ 2 yrs/.test(o)), String(reachOptions))
  check('it offers ≤ 3 yrs and ≤ 5 yrs',
    reachOptions && reachOptions.some((o) => o.includes('≤ 3 yrs')) && reachOptions.some((o) => o.includes('≤ 5 yrs')),
    String(reachOptions))
  check('a 4-year-dormant player is out of reach at the default ≤ 3 yrs',
    !cols['Potential fill-ins']?.names.includes('Ancient, Amy'),
    JSON.stringify(cols['Potential fill-ins']?.names))

  await page.evaluate(() => {
    const sel = [...document.querySelectorAll('select')].find((s) =>
      [...s.options].some((o) => o.textContent.startsWith('Fill-ins')))
    sel.value = '5'
    sel.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await page.waitForTimeout(300)
  cols = await columns(page)
  check('opening the reach to ≤ 5 yrs brings the 4-year-dormant player in',
    cols['Potential fill-ins']?.names.includes('Ancient, Amy'),
    JSON.stringify(cols['Potential fill-ins']?.names))
  check('...and the recently-played player never leaks into the fill-in pool',
    !cols['Potential fill-ins']?.names.includes('Recent, Rita'))

  // ── the inactive escape hatch ───────────────────────────────────────────
  const hint = await page.evaluate(() => document.body.innerText)
  check('the board says how many inactive players it is holding back',
    /1 inactive not shown/.test(hint), hint.split('\n').find((l) => /inactive/.test(l)) || '')

  const facetLabels = await page.evaluate(async () => {
    const btn = [...document.querySelectorAll('button')].find((b) => /Filters/.test(b.textContent))
    btn?.click()
    await new Promise((r) => setTimeout(r, 250))
    return document.body.innerText
  })
  check('"Show inactive players" is offered as a filter', /Show inactive players/.test(facetLabels))

  await go('?showinactive=1')
  await openAll(page)
  cols = await columns(page)
  check('ticking Show inactive brings the inactive player back onto the board',
    JSON.stringify(cols).includes('Gone, Gary'), JSON.stringify(cols['Unassigned']?.names))
  check('...into the pool their history puts them in',
    cols['Unassigned']?.names.includes('Gone, Gary'), JSON.stringify(cols['Unassigned']?.names))
  const inactiveBadged = await page.evaluate(() =>
    [...document.querySelectorAll('[draggable="true"]')]
      .some((c) => /Gone, Gary/.test(c.textContent) && /inactive/i.test(c.textContent)))
  check('...badged as inactive so it is obvious why they were hidden', inactiveBadged)

  // ── card badges ─────────────────────────────────────────────────────────
  await go()
  await openAll(page)
  const badges = await page.evaluate(() => {
    const out = {}
    for (const c of document.querySelectorAll('[draggable="true"]')) {
      const name = c.querySelector('.flex-1')?.textContent.trim()
      out[name] = [...c.querySelectorAll('span.font-mono')].map((s) => s.textContent.trim()).filter(Boolean)
    }
    return out
  })
  check('a never-played card is badged "new"', (badges['Newbie, Ned'] || []).includes('new'),
    JSON.stringify(badges['Newbie, Ned']))
  check('a dormant card is badged with the year they last played',
    (badges['Lapsed, Larry'] || []).some((b) => /^\d{4}$/.test(b)), JSON.stringify(badges['Lapsed, Larry']))
  check('a current player carries no recency badge',
    !(badges['Recent, Rita'] || []).some((b) => /^\d{4}$|new/.test(b)), JSON.stringify(badges['Recent, Rita']))

  // ── a card in a secondary pool still drags into a squad ─────────────────
  // The point of filing rather than hiding: a fill-in has to be pickable.
  // dragstart and drop go in SEPARATE evaluate calls or React hasn't
  // re-rendered with the drag in flight and the drop reads as refused.
  let assigned = null
  await page.route('**/api/teams/squad-assign', async (route) => {
    assigned = JSON.parse(route.request().postData() || '{}')
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', updated: 1 }) })
  })
  await page.evaluate(() => {
    const card = [...document.querySelectorAll('[draggable="true"]')]
      .find((c) => /Lapsed, Larry/.test(c.textContent))
    const dt = new DataTransfer()
    card.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }))
    window.__dt = dt
  })
  await page.waitForTimeout(150)
  await page.evaluate(() => {
    const col = [...document.querySelectorAll('.pb-card')]
      .find((c) => c.querySelector('.font-display')?.textContent.trim() === '2s')
    col.dispatchEvent(new DragEvent('dragover', { bubbles: true, dataTransfer: window.__dt, cancelable: true }))
    col.dispatchEvent(new DragEvent('drop', { bubbles: true, dataTransfer: window.__dt }))
  })
  await page.waitForTimeout(400)
  check('a Potential fill-ins card drags into a squad', !!assigned, JSON.stringify(assigned))
  check('...and sends that player to that squad',
    assigned?.player_ids?.[0] === 'p-lapsed' && assigned?.squad_team_id === SECONDS,
    JSON.stringify(assigned))

  // ── bulk add never offers an inactive player ────────────────────────────
  await page.getByRole('button', { name: 'Bulk add' }).click()
  await page.waitForTimeout(400)
  const bulkText = await page.evaluate(() => {
    const dlg = [...document.querySelectorAll('div')].find((d) => /Bulk add to squad/.test(d.textContent))
    return dlg ? dlg.innerText : ''
  })
  check('Bulk add lists active players', /Recent, Rita/.test(bulkText))
  check('Bulk add never offers an inactive player', !/Gone, Gary/.test(bulkText), bulkText.slice(0, 200))
  await page.keyboard.press('Escape')

  // ── hygiene ─────────────────────────────────────────────────────────────
  await go()
  await page.setViewportSize({ width: 390, height: 860 })
  await page.waitForTimeout(500)
  // The page as a whole DOES overflow at 390px, and it isn't the board: the
  // module header's action cluster (Auto-seed / Auto-assign / Fix order /
  // Manage squads / New squad) measures 693px inside a shrink-0 wrapper.
  // Confirmed pre-existing by re-measuring with this change stashed — 709px
  // either way — so this asserts the board's own columns, and that the page
  // total hasn't moved.
  const widths = await page.evaluate(() => {
    const docW = document.documentElement.clientWidth
    const grid = document.querySelector('[style*="auto-fill"]')
    const worst = Math.max(0, ...[...(grid?.querySelectorAll('*') || [])]
      .map((el) => el.getBoundingClientRect().right - docW))
    return { page: document.documentElement.scrollWidth - docW, board: Math.round(worst) }
  })
  check('the squad board itself does not overflow at 390px', widths.board <= 0, `${widths.board}px`)
  check('the page total is unchanged from the pre-existing header overflow',
    widths.page === 319, `${widths.page}px (was 319px before this change)`)
  check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { FAIL.forEach((f) => console.log('  FAILED:', f)); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
