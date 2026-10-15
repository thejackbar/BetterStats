// Drives the REAL screens in Chromium with the API stubbed at the network layer,
// answering with payloads the SHIPPED backend produced (see
// backend/verification/verify_season_split_and_topup.py, DUMP_FIXTURES).
//
//   1. Public player profile: the Season filter reads "Summer 2026/27" and "Winter 2026"
//      (it used to read "2026/27" twice), picking one sends that season's id, the season
//      table keeps the two rows apart, and the header says what was added from a scorecard
//      CA's totals had not counted.
//   2. Admin player profile, Recent form: last five batting innings with the not out, the
//      bowling row, and fielding for the named season.
//   3. Admin Seasons: the "winter and summer as one season" switch saves through PATCH.
//
//   DUMP_FIXTURES=/path/fixtures.json python backend/verification/verify_season_split_and_topup.py
//   npx vite preview --outDir dist --port 5199 &
//   FIXTURES=/path/fixtures.json node frontend/verification/verify_season_split_browser.mjs
//   (CONTROL: run against the previous commit's build; the label checks must fail)
import { existsSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const FX = JSON.parse(readFileSync(process.env.FIXTURES, 'utf8'))
const { reported, form, org, summer, winter } = FX.ids

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`  ok   ${name}`) }
  else { fail++; console.log(`  FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const ME = {
  id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'split', organisation_id: org,
  capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' },
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(path, { width = 1440, routes } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1500 } })
  const page = await ctx.newPage()
  const errors = [], wire = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    wire.push({ path: p, search: url.search, method: req.method(), body: req.postData() })
    let handled = false
    const json = (body, status = 200) => {
      handled = true
      return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    }
    if (routes) await routes(p, req, json)
    if (handled) return
    if (/^\/auth\/me/.test(p)) return json(ME)
    const obj = /team-breakdown|captain-stats|self-serve|usage|settings|profile$/.test(p)
    return json(obj ? {} : [])
  })
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
  return { page, ctx, errors, wire }
}

try {
  console.log('\n-- PUBLIC PROFILE: THE SEASON FILTER AND THE TABLE --')
  {
    const stats = { ...FX.stats, batting_innings: [], bowling_spells: [] }
    const { page, ctx, errors, wire } = await open(`/players/${reported}`, {
      routes: async (p, req, json) => {
        if (new RegExp(`/players/${reported}/stats$`).test(p)) return json(stats)
        if (new RegExp(`/players/${reported}/seasons$`).test(p)) return json(FX.season_stats)
        if (/\/organisations\/[^/]+\/seasons$/.test(p)) return json(FX.seasons)
        if (/\/grade-categories$/.test(p)) {
          return json({ available: ['senior'], default: ['senior'], available_formats: [], available_competitions: [] })
        }
        return undefined
      },
    })
    await page.waitForSelector('text=SEASON', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(500)
    const sel = page.locator('select').first()
    const opts = await sel.locator('option').allTextContents()
    ck('the Season filter lists Summer 2026/27 and Winter 2026 by name',
       opts.includes('Summer 2026/27') && opts.includes('Winter 2026'), JSON.stringify(opts))
    ck('and no label appears twice', new Set(opts).size === opts.length, JSON.stringify(opts))
    ck('a year with no winter season keeps its plain label (2025/26, 2027/28)',
       opts.includes('2025/26') && opts.includes('2027/28'), JSON.stringify(opts))
    await sel.selectOption(winter).catch(() => {})
    await page.waitForTimeout(500)
    const picked = [...wire].reverse().find(w => /\/stats$/.test(w.path))
    ck('picking Winter 2026 asks for that season id', !!picked && picked.search.includes(`season_id=${winter}`),
       JSON.stringify(picked))
    await sel.selectOption('').catch(() => {})
    await page.waitForTimeout(500)
    const note = await page.getByText(/scorecards we hold that Cricket Australia/).first()
      .textContent({ timeout: 3000 }).catch(() => null)
    ck('the header says what was added: 1 batting innings (10 runs)',
       !!note && /1 batting innings \(10 runs\)/.test(note), String(note))
    await page.getByText('SEASON BY SEASON').first().click({ timeout: 1500 }).catch(() => {})
    ck('no page error', errors.length === 0, errors.join(' | '))
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    ck('no horizontal overflow at 1440', !overflow)
    await ctx.close()
  }
  {
    const stats = { ...FX.stats, batting_innings: [], bowling_spells: [] }
    const { page, ctx } = await open(`/players/${reported}`, {
      width: 390,
      routes: async (p, req, json) => {
        if (new RegExp(`/players/${reported}/stats$`).test(p)) return json(stats)
        if (new RegExp(`/players/${reported}/seasons$`).test(p)) return json(FX.season_stats)
        if (/\/organisations\/[^/]+\/seasons$/.test(p)) return json(FX.seasons)
        return undefined
      },
    })
    await page.waitForSelector('text=SEASON', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(500)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    ck('no horizontal overflow at 390px', !overflow)
    await ctx.close()
  }

  console.log('\n-- ADMIN PLAYER PROFILE: RECENT FORM --')
  {
    const profile = {
      id: form, name: 'Form, Fay', display_name: 'Form, Fay', display_name_override: null,
      player_role: null, skill_positions: [], batting_hand: null, bowling_action: 'Right-arm',
      bowling_type: 'Medium', is_opening_batsman: null, gender: 'female', is_player: true,
      status: 'active', email: null, phone: null, photo_url: null, hero_photo_url: null,
      playhq_id: null, squad_team_id: null, is_overseas: false, overseas_country: null,
      is_public: true, shirt_number: null, date_of_birth: null, age: null, squad: null,
      squad_team_ids: [], age_visible: null, snapshot: FX.snapshot,
    }
    const list = [{ id: form, name: 'Form, Fay', display_name: 'Form, Fay', status: 'active',
                    is_player: true, is_public: true, is_overseas: false, gender: 'female' }]
    const { page, ctx, errors } = await open(`/admin/players?player=${form}`, {
      width: 1440,
      routes: async (p, req, json) => {
        if (/\/club-admin\/players$/.test(p)) return json(list)
        if (new RegExp(`/players/${form}/profile$`).test(p)) return json(profile)
        if (/\/nets\/.*attendance|attendance/.test(p)) return json({ attended: 0, batted: 0, sessions: [] })
        return undefined
      },
    })
    await page.getByRole('button', { name: 'Edit' }).first().click({ timeout: 8000 }).catch(() => {})
    await page.waitForSelector('text=Recent form', { timeout: 15000 }).catch(() => {})
    await page.waitForTimeout(400)
    const text = await page.locator('body').innerText()
    const scores = ['7*', '12', '0', '33', '4']
    const batRow = await page.locator('text=BATTING').first().locator('xpath=..').innerText().catch(() => '')
    ck('batting shows the last five with the not out: 7* 12 0 33 4',
       scores.every(sc => batRow.includes(sc)) && !batRow.includes('61'), batRow.replace(/\n/g, ' '))
    const bowlRow = await page.locator('text=BOWLING').first().locator('xpath=..').innerText().catch(() => '')
    ck('a bowling row shows 3/21', /3\/21/.test(bowlRow), bowlRow.replace(/\n/g, ' '))
    ck('fielding names the season, not "this season"', /Summer 2026\/27/.test(text), '')
    ck('fielding reads 3 catches and 1 run out', /3\s*\n?\s*catches/.test(text) && /1 run out/.test(text), '')
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    ck('no horizontal overflow', !overflow)
    ck('no page error', errors.length === 0, errors.join(' | '))
    await page.screenshot({ path: process.env.SHOT_FORM || '/tmp/recent_form.png' })
    await ctx.close()
  }

  console.log('\n-- ADMIN SEASONS: THE AMALGAMATE SWITCH --')
  {
    let amalgamate = false
    const { page, ctx, wire } = await open('/admin/seasons', {
      routes: async (p, req, json) => {
        if (/\/club-admin\/seasons$/.test(p)) return json(FX.seasons.map(s => ({ ...s, synced: true })))
        if (/\/club-admin\/settings$/.test(p) && req.method() === 'GET') return json({ amalgamate_seasons: amalgamate })
        if (/\/club-admin\/settings$/.test(p) && req.method() === 'PATCH') {
          amalgamate = JSON.parse(req.postData()).amalgamate_seasons
          return json({ ok: true })
        }
        return undefined
      },
    })
    await page.waitForSelector('text=Winter and summer', { timeout: 15000 }).catch(() => {})
    const box = page.getByLabel(/Count winter and summer as one season per year/)
    ck('the switch is drawn, off', (await box.count()) === 1 && !(await box.isChecked().catch(() => true)))
    await box.check({ timeout: 2000 }).catch(() => {})
    await page.waitForTimeout(300)
    const patch = wire.find(w => w.method === 'PATCH' && /settings$/.test(w.path))
    ck('ticking it sends exactly { amalgamate_seasons: true }',
       !!patch && patch.body === JSON.stringify({ amalgamate_seasons: true }), JSON.stringify(patch))
    await ctx.close()
  }
} finally {
  await browser.close()
}
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
