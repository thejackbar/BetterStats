// Drives the REAL BetterSelect Players page in Chromium with the API stubbed at the network layer.
//
// Asked for (North Perth, Oct 2026): "a filter for how long since players last played a game,
// for example more than 1, 3 or 5 years, vs the less than filter that exists at the moment".
// The page's recency dropdown only had "Played <= N yrs". It now also has "Last played > N yrs
// ago", for finding the lapsed.
//
//   npx vite build --outDir /var/tmp/np_dist && npx vite preview --outDir /var/tmp/np_dist --port 5199 &
//   node verify_recency_lapsed_browser.mjs [baseUrl]
//
// What a build cannot tell you: that the new options are drawn under their own heading, that each one
// lists exactly the players whose last game is older than the cutoff (and not a player who has never
// played, who is not "lapsed", nor one still inside it), that the cutoff day itself is "within" and
// not "over" (the two are exact complements), that the old "Played <= N" choices still behave as they
// did, and that the page does not overflow at 390px.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

// Dates relative to NOW, so the check does not rot. Local YYYY-MM-DD, the way the API sends it.
const pad = (n) => String(n).padStart(2, '0')
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const yearsAgo = (y, extraDays = 0) => { const d = new Date(); d.setFullYear(d.getFullYear() - y); d.setDate(d.getDate() + extraDays); return iso(d) }
const daysAgo = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return iso(d) }

// Surnames A to E so every one sits under the page's first range tab.
const PLAYERS = [
  { id: 'p1', name: 'Adams, Recent',    last_played: daysAgo(20) },          // this month
  { id: 'p2', name: 'Allen, Twoish',    last_played: yearsAgo(2, -150) },    // about 2.4 years
  { id: 'p3', name: 'Archer, Fourish',  last_played: yearsAgo(4, -200) },    // about 4.5 years
  { id: 'p4', name: 'Baker, Nineish',   last_played: yearsAgo(9) },          // 9 years
  { id: 'p5', name: 'Brown, Never',     last_played: null },                 // has never played
  { id: 'p6', name: 'Clark, Retired',   last_played: yearsAgo(12), status: 'inactive' },
  { id: 'p7', name: 'Dixon, Onedayin',  last_played: yearsAgo(3, 1) },       // the day AFTER the 3 year cutoff: still within
  { id: 'p8', name: 'Evans, Onedayout', last_played: yearsAgo(3, -1) },      // the day BEFORE it: over
]
const ROWS = PLAYERS.map((p) => ({ status: 'active', player_role: 'Batter', email: 'x@x', ...p, display_name: p.name }))

const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const ME = { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'northperth', organisation_id: 'o1',
  capabilities: ['*'], entitlements: { modules: ['select'], status: 'active' } }

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(viewport = { width: 1440, height: 900 }) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort())
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route('**/api/auth/me', (r) => json(r, ME))
  await page.route(/\/api\/club-admin\/settings$/, (r) => json(r, { player_name_format: 'last_first' }))
  await page.route(/\/api\/club-admin\/players$/, (r) => json(r, ROWS))
  await page.route(/\/api\/teams(\?.*)?$/, (r) => json(r, []))
  await page.route(/\/api\/availability\/matrix/, (r) => json(r, { availability: {}, dates: [], players: [] }))
  await page.route(/\/api\/availability\/config/, (r) => json(r, { allow_maybe: true, played_years: { selection: 3, availability: 0 }, team_defaults: [], squads: [] }))
  await page.goto(`${BASE}/admin/betterselect/players`, { waitUntil: 'domcontentloaded' })
  await page.getByText('Adams').first().waitFor({ timeout: 30000 }).catch(() => {})
  await page.waitForTimeout(500)
  return { ctx, page, errors }
}

// The surnames drawn in the list, in order.
const SURNAMES = PLAYERS.map((p) => p.name.split(',')[0])
const listed = async (page) => {
  const body = await page.locator('.pl-root').innerText()
  return SURNAMES.filter((s) => body.includes(s))
}
const recency = (page) => page.locator('select[title="Filter by when players last played"], select[title="Hide players who haven’t played recently"]').first()

{
  const { ctx, page, errors } = await open()
  const sel = recency(page)
  ck('the recency dropdown is on the page', (await sel.count()) === 1)

  console.log('\n# the options')
  const groups = await sel.evaluate((el) => Array.from(el.children).map((c) => c.tagName === 'OPTGROUP'
    ? { group: c.label, opts: Array.from(c.children).map((o) => o.textContent) }
    : { loose: c.textContent }))
  ck('"any time" stays first and loose', groups[0] && groups[0].loose === 'Played: any time', JSON.stringify(groups[0]))
  const within = groups.find((g) => g.group === 'Played within')
  const lapsed = groups.find((g) => g.group === 'Not played for a while')
  ck('the old choices sit under "Played within", unchanged', within && within.opts.join('|') === 'Played ≤ 1 yr|Played ≤ 2 yrs|Played ≤ 3 yrs|Played ≤ 5 yrs|Played ≤ 10 yrs', JSON.stringify(within))
  ck('the new ones sit under their own heading', lapsed && lapsed.opts.join('|') === 'Last played > 1 yr ago|Last played > 2 yrs ago|Last played > 3 yrs ago|Last played > 5 yrs ago|Last played > 10 yrs ago', JSON.stringify(lapsed))

  console.log('\n# any time')
  ck('inactive players stay out by default, everyone else is listed',
    JSON.stringify(await listed(page)) === JSON.stringify(['Adams', 'Allen', 'Archer', 'Baker', 'Brown', 'Dixon', 'Evans']), JSON.stringify(await listed(page)))

  // Presence-safe: an option the build does not have reads as "listed nothing" and fails its check,
  // rather than throwing, so a run against an older build reports what is missing.
  const hasOption = (label) => sel.evaluate((el, l) => Array.from(el.querySelectorAll('option')).some((o) => o.textContent === l), label)
  const pick = async (label) => {
    if (!(await hasOption(label))) { console.log(`     (no option "${label}")`); return ['<no such option>'] }
    await sel.selectOption({ label }); await page.waitForTimeout(250); return listed(page)
  }

  console.log('\n# last played more than N years ago')
  let got = await pick('Last played > 1 yr ago')
  ck('> 1 yr: everyone whose last game is over a year old', JSON.stringify(got) === JSON.stringify(['Allen', 'Archer', 'Baker', 'Dixon', 'Evans']), JSON.stringify(got))
  ck('...not Adams, who played this month', !got.includes('Adams'))
  ck('...and not Brown, who has never played (not lapsed)', !got.includes('Brown'))
  got = await pick('Last played > 3 yrs ago')
  ck('> 3 yrs: the cutoff day itself is NOT over, the day before it is', JSON.stringify(got) === JSON.stringify(['Archer', 'Baker', 'Evans']), JSON.stringify(got))
  got = await pick('Last played > 5 yrs ago')
  ck('> 5 yrs: only Baker (Clark is inactive)', JSON.stringify(got) === JSON.stringify(['Baker']), JSON.stringify(got))
  got = await pick('Last played > 10 yrs ago')
  ck('> 10 yrs: nobody active, and the list says so rather than showing someone',
    got.length === 0 && /No players/.test(await page.locator('.pl-root').innerText()), JSON.stringify(got))
  ck('the dropdown is lit while a filter is on', await sel.evaluate((el) => /text-pb-accent/.test(el.className)))

  console.log('\n# the two directions are exact complements on the cutoff')
  const within3 = await pick('Played ≤ 3 yrs')
  const over3 = await pick('Last played > 3 yrs ago')
  ck('Dixon (the day inside) is within 3 yrs and not over; Evans (the day outside) is over and not within',
    within3.includes('Dixon') && !over3.includes('Dixon') && over3.includes('Evans') && !within3.includes('Evans'), JSON.stringify({ within3, over3 }))

  console.log('\n# the old choices are unchanged')
  got = await pick('Played ≤ 1 yr')
  ck('<= 1 yr keeps the recent and the never-played, drops the rest', JSON.stringify(got) === JSON.stringify(['Adams', 'Brown']), JSON.stringify(got))
  got = await pick('Played ≤ 5 yrs')
  ck('<= 5 yrs', JSON.stringify(got) === JSON.stringify(['Adams', 'Allen', 'Archer', 'Brown', 'Dixon', 'Evans']), JSON.stringify(got))
  got = await pick('Played: any time')
  ck('back to any time lists everyone again', got.length === 7, JSON.stringify(got))

  console.log('\n# alongside "Include inactive"')
  await pick('Last played > 10 yrs ago')
  await page.getByRole('button', { name: /Filters/ }).first().click()
  await page.waitForTimeout(250)
  await page.getByText('Include inactive', { exact: false }).first().click()
  await page.waitForTimeout(300)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(200)
  got = await listed(page)
  ck('with inactive switched on, the lapsed filter finds Clark', JSON.stringify(got) === JSON.stringify(['Clark']), JSON.stringify(got))

  ck('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))
  await page.screenshot({ path: process.env.SHOTS ? `${process.env.SHOTS}/recency_desktop.png` : '/dev/null' }).catch(() => {})
  await ctx.close()
}

{
  console.log('\n# 390px')
  const { ctx, page } = await open({ width: 390, height: 800 })
  if (await recency(page).evaluate((el) => Array.from(el.querySelectorAll('option')).some((o) => o.textContent === 'Last played > 5 yrs ago'))) await recency(page).selectOption({ label: 'Last played > 5 yrs ago' })
  await page.waitForTimeout(300)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ck('no horizontal overflow at 390px with a lapsed filter on', over <= 1, `${over}px`)
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
