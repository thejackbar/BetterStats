// Drives the REAL Selection board and Availability screen in Chromium with the API
// stubbed at the network layer.
//
// Asked for (Applecross, Oct 2026):
//   * the Filters box was broken: opened inside the pool card it pushed the player
//     list out of the card and spilled over the card's border. It is now a floating
//     panel that scrolls inside itself and closes on Escape or a click outside.
//   * "Played within" and "Show juniors" come off the screens (Settings holds them).
//   * a team can start on its own filters: a women's team on Gender = Women, a 1st
//     XI that only sees the top squads. They are shown as a banner, the selector's
//     own pick wins, and one click turns them off for the match.
//
//   npx vite preview --outDir <dist> --port 5199 &   then   node verify_select_filters_browser.mjs
import { chromium } from 'playwright'
import { readFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures/selection_same_day.json'), 'utf8'))
const FID = FIX.fixture_id
const TEAM = FIX.payload.fixture.team_id
const PASS = [], FAIL = []
const ok = (name, cond, detail = '') => { (cond ? PASS : FAIL).push(name); console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  none: ' + String(detail).slice(0, 220) : ''}`) }
const ME = { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' } }
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

// Twelve players: men and women across the squads, one long since retired.
const SQUADS = ['Club 1st XI', 'Club 2nd XI', 'Club 3rd XI', 'Club 4th XI']
const PLAYERS = [
  ['Mia Firsts', 'female', ['Club 1st XI']], ['Ned Firsts', 'male', ['Club 1st XI']],
  ['Amy Seconds', 'female', ['Club 2nd XI']], ['Ben Seconds', 'male', ['Club 2nd XI']],
  ['Cat Thirds', 'female', ['Club 3rd XI']], ['Dan Thirds', 'male', ['Club 3rd XI']],
  ['Eve Fourths', 'female', ['Club 4th XI']], ['Fin Fourths', 'male', ['Club 4th XI']],
  ['Gus Retired', 'male', ['Club 2nd XI']],
]
const base = FIX.payload.pool[0]
const pool = PLAYERS.map(([name, gender, squads], i) => ({
  ...base, id: `00000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`, display_name: name, gender, squads,
  squad_team_id: null, availability: 'AVAILABLE', clash: [], clash_detail: [], also_in: [], clash_blocks: false,
  last_played: name === 'Gus Retired' ? '2010-01-01' : '2099-01-01', score: 50 - i, tier: 1, squad_match: false,
}))
const payload = () => ({ ...FIX.payload, lineup: [], pool })
const CONFIG = (extra = {}) => ({
  allow_maybe: true, half_colours: { w1: '#a855f7', w2: '#06b6d4' }, played_years: { selection: 3, availability: 0 },
  team_defaults: [], squads: SQUADS.map((name, i) => ({ id: `s${i}`, name, sequence: i + 1 })), ...extra,
})

async function stub(page, cfg) {
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route(/\/api\/club-admin\/settings$/, (r) => json(r, { player_name_format: 'first_last' }))
  await page.route(/\/api\/availability\/config/, (r) => json(r, cfg))
  await page.route(/\/api\/selection\/overview(\?.*)?$/, (r) => json(r, { fixtures: [], default_team_size: 11 }))
  await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { source_fixture_id: null, player_ids: [], captain_id: null, wicket_keeper_id: null }))
  await page.route(/\/api\/selection\/selected-players/, (r) => json(r, { player_ids: [] }))
  await page.route(new RegExp(`/api/selection/${FID}/draft(\\?.*)?$`), (r) => json(r, { draft: null, version: 0 }))
  await page.route(new RegExp(`/api/selection/${FID}$`), (r) => json(r, payload()))
}

const run = async () => {
  mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const open = async (cfg, vp = { width: 1440, height: 900 }) => {
    const ctx = await browser.newContext({ viewport: vp })
    const page = await ctx.newPage()
    await stub(page, cfg)
    await page.goto(`${BASE}/admin/betterselect/select/${FID}`, { waitUntil: 'domcontentloaded' })
    await page.getByText('Mia Firsts').first().waitFor({ timeout: 20000 }).catch(() => {})
    await page.waitForTimeout(400)
    return { ctx, page }
  }
  // A card's text starts with the avatar initials: take the line that is a player's name.
  const ALL_NAMES = new Set(PLAYERS.map((p) => p[0]))
  const names = async (page) => (await page.locator('div.group.relative.rounded-xl').allInnerTexts())
    .map((t) => t.split('\n').map((l) => l.trim()).find((l) => ALL_NAMES.has(l))).filter(Boolean)
  const body = async (page) => (await page.locator('body').innerText()).replace(/\s+/g, ' ')

  // ───────── the Filters panel ─────────
  console.log('\n# the Filters panel')
  {
    const { ctx, page } = await open(CONFIG())
    const card = page.locator('section.pb-card', { hasText: 'Available pool' }).first()
    const before = await card.boundingBox()
    const listBefore = await page.locator('[data-drop-kind="pool"]').first().boundingBox()
    await page.getByRole('button', { name: /Filters/ }).first().click()
    await page.waitForTimeout(250)
    const panel = page.locator('[data-filters-panel]')
    ok('the panel opens', (await panel.count()) === 1)
    const after = await card.boundingBox()
    const listAfter = await page.locator('[data-drop-kind="pool"]').first().boundingBox()
    ok('it floats: the pool card does not change size', before && after && Math.abs(before.height - after.height) < 1, JSON.stringify([before?.height, after?.height]))
    ok('...and the player list is not pushed or squashed', listBefore && listAfter && Math.abs(listBefore.y - listAfter.y) < 1 && Math.abs(listBefore.height - listAfter.height) < 1, JSON.stringify([listBefore, listAfter]))
    const pb = await panel.boundingBox()
    ok('the panel stays inside the window', pb && pb.y >= 0 && pb.y + pb.height <= 900 + 1, JSON.stringify(pb))
    ok('it has a height limit and scrolls inside itself', await panel.evaluate((el) => getComputedStyle(el).overflowY === 'auto' && el.getBoundingClientRect().height <= window.innerHeight * 0.7))
    ok('it sits above the list (a click in it reaches it, not a player card)', await page.evaluate(() => {
      const el = document.querySelector('[data-filters-panel]'); const r = el.getBoundingClientRect()
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + 24)
      return !!hit && el.contains(hit)
    }))
    ok('the Squad group is reachable in it', (await panel.getByText('Squad', { exact: true }).count()) >= 1)
    await page.screenshot({ path: join(SHOTS, 'filters_panel_open.png') })
    await page.keyboard.press('Escape')
    await page.waitForTimeout(150)
    ok('Escape closes it', (await page.locator('[data-filters-panel]').count()) === 0)
    await page.getByRole('button', { name: /Filters/ }).first().click()
    await page.waitForTimeout(150)
    await page.getByText('Available pool').first().click()
    await page.waitForTimeout(150)
    ok('a click outside closes it', (await page.locator('[data-filters-panel]').count()) === 0)
    // A short window: it must still fit and scroll.
    await page.setViewportSize({ width: 1280, height: 640 })
    await page.getByRole('button', { name: /Filters/ }).first().click()
    await page.waitForTimeout(250)
    const pb2 = await page.locator('[data-filters-panel]').boundingBox()
    ok('at 640px high it still fits the window and scrolls', pb2 && pb2.y + pb2.height <= 640 + 1, JSON.stringify(pb2))
    await ctx.close()
  }

  // ───────── the controls that moved to Settings ─────────
  console.log('\n# Played within and Show juniors are not on the screens')
  {
    const { ctx, page } = await open(CONFIG())
    const b = await body(page)
    ok('Selection board: no "Played" window control', !(await page.locator('select', { hasText: /Played/ }).count()) && !/Played (≤|any time)/i.test(b), b.slice(0, 200))
    ok('Selection board: no Show juniors switch', (await page.locator('[data-juniors-toggle]').count()) === 0)
    await ctx.close()
  }
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    await page.route('**/api/**', (r) => json(r, {}))
    await page.route('**/api/auth/me', (r) => json(r, ME))
    await page.route(/\/api\/availability\/config/, (r) => json(r, CONFIG()))
    await page.route(/\/api\/availability\/matrix/, (r) => json(r, {
      dates: [{ date: '2099-06-06', fixtures: [{ id: 'f1', opponent_name: 'Opp', home_away: 'HOME', role: 'single', two_day: false }] }],
      players: pool.slice(0, 3).map((p) => ({ id: p.id, name: p.display_name, display_name: p.display_name, display_name_override: null, photo_url: null, is_player: true, player_role: null, status: 'active', is_current: true, is_dormant: false, is_inactive: false, squads: [], last_played: p.last_played, age: null })),
      all_squads: [], dormancy_months: 24, rules: { active: false, applied: [] }, availability: {},
    }))
    await page.goto(`${BASE}/admin/betterselect/availability`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('tbody tr', { timeout: 20000 }).catch(() => {})
    await page.waitForTimeout(300)
    const b = await body(page)
    ok('Availability: the screen drew its table', (await page.locator('tbody tr').count()) >= 1)
    ok('Availability: no "Played" window control', !(await page.locator('select', { hasText: /Played/ }).count()) && !/Played (≤|any time)/i.test(b))
    ok('Availability: no Show juniors switch', (await page.locator('[data-juniors-toggle]').count()) === 0 && !/Show juniors/i.test(b))
    ok('control: the Current squad / All switch is still there', /Current squad/.test(b))
    await page.screenshot({ path: join(SHOTS, 'availability_streamlined.png') })
    await ctx.close()
  }

  // ───────── the club's window ─────────
  console.log('\n# the club setting decides who is listed')
  {
    const { ctx, page } = await open(CONFIG({ played_years: { selection: 3, availability: 0 } }))
    ok('3 years: the long-retired player is not listed', !(await names(page)).includes('Gus Retired') && (await names(page)).includes('Mia Firsts'), (await names(page)).join())
    await ctx.close()
  }
  {
    const { ctx, page } = await open(CONFIG({ played_years: { selection: 0, availability: 0 } }))
    ok('any time: they are', (await names(page)).includes('Gus Retired'), (await names(page)).join())
    await ctx.close()
  }
  {
    const { ctx, page } = await open(CONFIG({ played_years: { selection: 3, availability: 0 } }))
    await page.getByPlaceholder('Search players…').first().fill('Gus')
    await page.waitForTimeout(300)
    ok('control: typing a name still finds them whatever the window', (await names(page)).includes('Gus Retired'), (await names(page)).join())
    await ctx.close()
  }

  // ───────── team defaults ─────────
  console.log('\n# team defaults')
  const rule = (extra) => ({ id: 'r1', team_ids: [TEAM], gender: '', squads: [], top_squads: null, played_years: null, ...extra })
  {
    const { ctx, page } = await open(CONFIG({ team_defaults: [rule({ gender: 'female' })] }))
    const n = await names(page)
    ok('a Gender = Women default starts on the women only', n.length > 0 && n.every((x) => /^(Mia|Amy|Cat|Eve)/.test(x)), n.join())
    ok('the banner says what it applied', /team default/i.test(await body(page)) && (await page.locator('[data-team-default]').innerText()).includes('Women'))
    await page.screenshot({ path: join(SHOTS, 'team_default_women.png') })
    await page.locator('[data-team-default-toggle]').click()
    await page.waitForTimeout(250)
    const n2 = await names(page)
    ok('"Show everyone" turns it off for the match', n2.includes('Ned Firsts') && n2.includes('Mia Firsts'), n2.join())
    ok('...and the banner offers to turn it back on', /Turn on/.test(await page.locator('[data-team-default]').innerText()))
    await page.locator('[data-team-default-toggle]').click()
    await page.waitForTimeout(250)
    ok('turning it on again filters again', !(await names(page)).includes('Ned Firsts'))
    // The selector's own pick wins over the default.
    await page.getByRole('button', { name: /Filters/ }).first().click()
    await page.waitForTimeout(200)
    const menBtn = page.locator('[data-filters-panel]').getByRole('button', { name: 'Men', exact: true })
    ok('the Gender group is offered in the panel', (await menBtn.count()) === 1, JSON.stringify([await page.locator('[data-filters-panel]').count(), await page.locator('[data-filters-panel]').boundingBox(), (await page.locator('[data-filters-panel]').innerText()).replace(/\n/g, '|').slice(0, 300)]))
    await menBtn.click({ timeout: 3000 }).catch((e) => console.log('   click failed:', String(e).slice(0, 120)))
    await page.waitForTimeout(250)
    ok('the selector\'s own Gender pick beats the default', (await names(page)).includes('Ned Firsts') && !(await names(page)).includes('Mia Firsts'), (await names(page)).join())
    await ctx.close()
  }
  {
    const { ctx, page } = await open(CONFIG({ team_defaults: [rule({ top_squads: 2 })] }))
    const n = await names(page)
    ok('top 2 squads: only the 1st and 2nd XI players', n.length > 0 && n.every((x) => /(Firsts|Seconds)$/.test(x)), n.join())
    ok('...not the 3rd or 4th', !n.some((x) => /Thirds|Fourths/.test(x)))
    ok('the banner names the squads', /1st XI/.test(await page.locator('[data-team-default]').innerText()) && /2nd XI/.test(await page.locator('[data-team-default]').innerText()), await page.locator('[data-team-default]').innerText())
    await ctx.close()
  }
  {
    const { ctx, page } = await open(CONFIG({ team_defaults: [rule({ squads: ['Club 3rd XI', 'Club 4th XI'], gender: 'male' })] }))
    const n = await names(page)
    ok('chosen squads and a gender combine', JSON.stringify(n.sort()) === JSON.stringify(['Dan Thirds', 'Fin Fourths']), n.join())
    await ctx.close()
  }
  {
    const { ctx, page } = await open(CONFIG({ team_defaults: [rule({ played_years: 0 })] }))
    ok('a team\'s own window beats the club\'s (any time lists the retired player)', (await names(page)).includes('Gus Retired'), (await names(page)).join())
    await ctx.close()
  }
  {
    const { ctx, page } = await open(CONFIG({ team_defaults: [{ ...rule({ gender: 'female' }), team_ids: ['some-other-team'] }] }))
    const n = await names(page)
    ok('control: a rule for another team does nothing here', n.includes('Ned Firsts') && n.includes('Mia Firsts'), n.join())
    ok('control: no banner for a team with no rule', (await page.locator('[data-team-default]').count()) === 0)
    await ctx.close()
  }

  // ───────── a phone ─────────
  console.log('\n# 390px')
  {
    const { ctx, page } = await open(CONFIG({ team_defaults: [rule({ gender: 'female' })] }), { width: 390, height: 844 })
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.screen.width)
    ok('no horizontal overflow with a team default showing', over <= 0, String(over))
    await ctx.close()
  }

  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run()
