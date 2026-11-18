// Better HQ > Reporting > Trial Summary, driven in Chromium with the API stubbed at the network.
//
//   npx vite build && npx vite preview --port 5204 &
//   node frontend/verification/verify_trial_summary_browser.mjs [baseUrl]
//
// What a reader could be misled by, and so what is measured: a trial ending in two days must
// stand out and say how long is left; a club with no activity must say so, not show a blank;
// "Current" leaves archived clubs out while "All" brings them back; the Reporting hub links here.
// Control runs must REPORT, not crash: reads go through textOf()/has().
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SHOTS = process.env.SHOT_DIR || null

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
const textOf = async (l) => (await l.count() ? await l.first().innerText() : '')
const has = async (l) => (await l.count()) > 0
const clickIf = async (l) => { if (await l.count()) await l.first().click() }
const classOf = async (l) => (await l.count() ? (await l.first().getAttribute('class')) || '' : '')

const NOW = '2026-11-18T10:00:00Z'
const day = (n) => new Date(Date.parse(NOW) + n * 86400000).toISOString()
const base = (o) => ({
  slug: o.name.toLowerCase().replace(/ /g, '-'), trial_open_ended: false, trial_ended_at: null, ending_soon: false,
  signed_up_from: 'registration', signup_channel: 'Self-serve', origin: { channel: 'direct', label: 'Direct' },
  admin_name: null, admin_email: null, contact_source: null, members: 1, last_login_at: null,
  activity: { views: 0, views_recent: 0, active_days: 0, active_days_recent: 0, active_people: 0, last_active_at: null, top_areas: [] },
  data: { players: 0, games: 0, last_sync_at: null, last_sync_status: null }, modules: [], ...o,
})
const CLUBS = [
  base({ org_id: 'a', name: 'Soon CC', status: 'on_trial', trial_ends_at: day(2), days_left: 2, ending_soon: true, signed_up_at: day(-12),
    signup_channel: 'Self-serve, from a tracked link', origin: { channel: 'email', label: 'Email (our outreach)' },
    modules: [{ module: 'core', name: 'BetterStats', status: 'trial' }, { module: 'select', name: 'BetterSelect', status: 'trial' }],
    admin_name: 'Sam Admin', admin_email: 'sam@soon.example', contact_source: 'club_admin', members: 2, last_login_at: day(-1),
    activity: { views: 5, views_recent: 4, active_days: 3, active_days_recent: 2, active_people: 2, last_active_at: day(-1),
      top_areas: [{ area: 'selection', views: 3 }, { area: 'players', views: 1 }] },
    data: { players: 41, games: 12, last_sync_at: day(-11), last_sync_status: 'success' } }),
  base({ org_id: 'b', name: 'Later CC', status: 'on_trial', trial_ends_at: day(10), days_left: 10, signed_up_at: day(-4),
    signup_channel: 'Set up by us', signed_up_from: 'trial_start', origin: null,
    modules: [{ module: 'core', name: 'BetterStats', status: 'trial' }] }),
  base({ org_id: 'c', name: 'Lapsed CC', status: 'trial_ended', trial_ends_at: null, days_left: null, trial_ended_at: day(-16), signed_up_at: day(-30),
    modules: [{ module: 'core', name: 'BetterStats', status: 'trial_expired' }], last_login_at: day(-20) }),
  base({ org_id: 'd', name: 'Paying CC', status: 'paying', trial_ends_at: day(11), days_left: 11, signed_up_at: day(-60),
    modules: [{ module: 'core', name: 'BetterStats', status: 'subscribed' }, { module: 'iq', name: 'BetterIQ', status: 'trial' }] }),
  base({ org_id: 'e', name: 'Archived CC', status: 'archived', trial_ends_at: day(4), days_left: 4, signed_up_at: day(-10) }),
  base({ org_id: 'f', name: 'Quiet CC', status: 'on_trial', trial_ends_at: day(12), days_left: 12, signed_up_at: day(-2),
    admin_name: 'Quiet Secretary', admin_email: 'sec@quiet.example', contact_source: 'club_directory' }),
]

const browser = await chromium.launch({ executablePath: EXECUTABLE })

async function open(path, { width = 1500, fail: failLoad = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = [], wire = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url())
    const p = u.pathname.replace(/^\/api/, '')
    wire.push(route.request().method() + ' ' + p + u.search)
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(p)) return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'super_admin', entitlements: { modules: [], status: 'active' } })
    if (/super\/trial-summary/.test(p)) {
      return failLoad ? json({ detail: 'boom' }, 500)
        : json({ clubs: CLUBS, generated_at: NOW, recent_days: 7, ending_soon_days: 3 })
    }
    return json([])
  })
  await page.goto(BASE + path, { waitUntil: 'domcontentloaded' })
  await page.locator('h1').first().waitFor({ state: 'visible', timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(1200)
  return { page, ctx, errors, wire }
}

{
  const { page, ctx, errors, wire } = await open('/admin/super/trial-summary')
  ck('the page asks for the trial summary once, as a GET', wire.filter((w) => /^GET \/club-admin\/super\/trial-summary$/.test(w)).length === 1,
     wire.filter((w) => /trial/.test(w)).join(' | '))
  ck('the heading is Trial Summary', /trial summary/i.test(await textOf(page.locator('h1'))))
  const rows = page.locator('[data-testid="trial-row"]')
  ck('Current lists every club but the archived one', (await rows.count()) === 5, String(await rows.count()))
  ck('the Current chip counts 5', (await textOf(page.locator('[data-testid="trial-chip-count-active"]'))).trim() === '5')
  const soon = await textOf(rows.filter({ hasText: 'Soon CC' }))
  ck('the newest sign-up is first', (await textOf(rows.first())).includes('Quiet CC'), await textOf(rows.first()))
  ck('a trial ending in two days says how long is left', /2 days left/i.test(soon), soon)
  ck('and stands out', /amber/.test(await classOf(rows.filter({ hasText: 'Soon CC' }))))
  ck('it names what is on trial', /BetterStats/.test(soon) && /BetterSelect/.test(soon))
  ck('the activity line reads plainly', /active 3 days/i.test(soon) && /2 in the last 7/i.test(soon) && /5 page views/i.test(soon) && /2 people/i.test(soon), soon)
  ck('and says what they used most', /mostly selection, players/i.test(soon), soon)
  ck('how they signed up and where from', /from a tracked link/i.test(soon) && /email \(our outreach\)/i.test(soon), soon)
  ck('the contact is shown with an email link', await has(rows.filter({ hasText: 'Soon CC' }).locator('a[href="mailto:sam@soon.example"]')))
  ck('players, games and the last sync are shown', /41 players · 12 games · synced/i.test(soon), soon)
  const later = await textOf(rows.filter({ hasText: 'Later CC' }))
  ck('a club with no activity says so rather than going blank', /has not used the admin yet/i.test(later), later)
  ck('a club we set up says so', /set up by us/i.test(later))
  ck('a later trial is not highlighted', (await rows.count()) > 0 && !/amber/.test(await classOf(rows.filter({ hasText: 'Later CC' }))))
  const lapsed = await textOf(rows.filter({ hasText: 'Lapsed CC' }))
  ck('a lapsed trial says when it ended', /trial ended/i.test(lapsed) && /ended 16 days ago/i.test(lapsed), lapsed)
  ck('a signed-in-only club says when it last signed in', /signed in 20 days ago/i.test(lapsed), lapsed)
  ck('a paying club shows the add-on trial still running', /paying/i.test(await textOf(rows.filter({ hasText: 'Paying CC' }))) && /on an add-on trial/i.test(await textOf(rows.filter({ hasText: 'Paying CC' }))))
  ck('a Club Directory contact says where it came from', /from the club directory/i.test(await textOf(rows.filter({ hasText: 'Quiet CC' }))))

  await clickIf(page.locator('[data-testid="trial-chip-ending_soon"]'))
  ck('Ending soon shows only the club ending in two days', (await rows.count()) === 1 && (await textOf(rows.first())).includes('Soon CC'), String(await rows.count()))
  await clickIf(page.locator('[data-testid="trial-chip-all"]'))
  ck('All brings the archived club back', (await rows.count()) === 6 && await has(rows.filter({ hasText: 'Archived CC' })))
  await clickIf(page.locator('[data-testid="trial-chip-active"]'))
  if (await page.locator('[data-testid="trial-sort"]').count()) await page.locator('[data-testid="trial-sort"]').selectOption('trial_end')
  ck('sorting by trial end puts the soonest first', (await textOf(rows.first())).includes('Soon CC'), await textOf(rows.first()))
  if (await page.locator('[data-testid="trial-search"]').count()) await page.locator('[data-testid="trial-search"]').fill('quiet')
  ck('the search narrows by club name', (await rows.count()) === 1)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await clickIf(page.locator('[data-testid="trial-chip-active"]'))
  if (await page.locator('[data-testid="trial-search"]').count()) await page.locator('[data-testid="trial-search"]').fill('')
  const table = page.locator('[data-testid="trial-table"]')
  const clipped = await table.count() ? await table.evaluate((el) => el.scrollWidth - el.clientWidth) : -1
  ck('at 1500px every column fits without scrolling the table', clipped >= 0 && clipped <= 1, String(clipped))
  if (SHOTS) {
    await page.locator('[data-testid="trial-search"]').fill('')
    await page.screenshot({ path: `${SHOTS}/trial-summary-1500.png`, fullPage: false })
  }
  await ctx.close()
}
{
  const { page, ctx } = await open('/admin/super/trial-summary', { width: 390 })
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal page scroll at 390px (the table scrolls inside its card)', over <= 1 && await has(page.locator('[data-testid="trial-table"]')), String(over))
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/trial-summary-390.png`, fullPage: false })
  await ctx.close()
}
{
  const { page, ctx } = await open('/admin/super/trial-summary', { fail: true })
  ck('a failed load is shown, not swallowed', /could not load|boom/i.test(await textOf(page.locator('main, body'))))
  await ctx.close()
}
{
  const { page, ctx } = await open('/admin/super/hub/reporting')
  const link = page.locator('a[href="/admin/super/trial-summary"]')
  ck('the Reporting hub links to Trial Summary', await has(link) && /trial summary/i.test(await textOf(link)), await textOf(page.locator('main, body')))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
