// The Milestones page keeps its settings (how often runs, wickets, matches and
// catches are marked, and the per grade increments) in ONE closed section at the
// foot, so the milestones come first.
//
//   npx vite build && npx vite preview --port 5197 &
//   node frontend/verification/verify_milestones_settings_browser.mjs [baseUrl]
//
// Asserts, in Chromium with the API stubbed: the milestone tables are above the
// settings, the settings are closed until opened (and say what is inside), opening
// shows the pickers and the per grade card, a change sends the exact request and the
// report is read again, and nothing overflows at 390px. The control (previous commit)
// fails the position, closed and toggle checks and reports, never crashes.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => { if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) } }

const REPORT = {
  upcoming: Array.from({ length: 6 }, (_, i) => ({ player_id: `p${i}`, player_name: `Player ${i}`, gender: 'male', type: 'runs', category: 'batting', current: 950 + i, target: 1000, needed: 50 - i, detail: null })),
  achieved: [{ player_id: 'p9', player_name: 'Veteran Vic', gender: 'male', type: 'matches', category: 'matches', milestone_value: 100, achieved_at: '2026-10-03', detail: null }],
  scheme: { runs_step: 1000, wickets_step: 100, matches_step: 50, catches_step: 50 },
  scheme_options: { runs_steps: [250, 500, 1000], wickets_steps: [25, 50, 100], matches_steps: [25, 50, 100], catches_steps: [25, 50, 100] },
  step_limits: { runs: { min: 100, max: 10000, multiple: 25 }, wickets: { min: 10, max: 1000, multiple: 5 }, matches: { min: 10, max: 500, multiple: 5 }, catches: { min: 10, max: 500, multiple: 5 } },
  grade_schemes: [{ key: 'a grade', name: 'A Grade', active: true, steps: {} }, { key: 'b grade', name: 'B Grade', active: true, steps: {} }],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
async function open(viewport) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const reads = [], writes = []
  const json = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  await page.route('**/api/**', (route) => {
    const req = route.request(), url = req.url()
    if (/\/auth\/me/.test(url)) return route.fulfill(json({ id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'kalamunda', entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' } }))
    if (/\/club-admin\/milestones\/scheme/.test(url)) { writes.push({ method: req.method(), body: JSON.parse(req.postData() || '{}') }); return route.fulfill(json({})) }
    if (/\/club-admin\/milestones$/.test(url)) { reads.push(url); return route.fulfill(json(REPORT)) }
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json({ id: 'org-1', name: 'Kalamunda CC', slug: 'kalamunda', theme_config: null }))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/milestones`, { waitUntil: 'domcontentloaded' })
  await page.getByText('Milestones In Reach').first().waitFor({ timeout: 30000 }).catch(() => {})
  return { ctx, page, reads, writes }
}
const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const top = async (loc) => { try { return (await loc.count()) ? (await loc.first().boundingBox())?.y ?? null : null } catch { return null } }

{
  const { ctx, page, reads, writes } = await open({ width: 1400, height: 1000 })
  const sec = page.locator('[data-testid="milestone-settings"]')
  const toggle = sec.getByRole('button', { name: /Milestone settings/i })
  ck('the settings section is on the page', await seen(sec))
  const yTable = await top(page.getByText('Milestones In Reach'))
  const ySettings = await top(sec)
  ck('the milestones come first: settings sit below the achieved table', yTable !== null && ySettings !== null && ySettings > (await top(page.getByText('Veteran Vic'))), `${yTable} ${ySettings}`)
  ck('closed to begin with: no "Milestones tracked" picker', !(await seen(page.getByText('Milestones tracked'))))
  ck('closed to begin with: no per grade card', !(await seen(page.getByText('Milestones by grade'))))
  ck('the closed bar says what is inside', /runs, wickets, matches and catches/i.test(await sec.innerText().catch(() => '')))
  ck('aria-expanded is false', (await toggle.getAttribute('aria-expanded').catch(() => null)) === 'false')
  await toggle.click().catch(() => {})
  await page.waitForTimeout(300)
  ck('opens: the club wide pickers show', await seen(page.getByText('Milestones tracked')))
  ck('opens: the per grade card shows', await seen(page.getByText('Milestones by grade')))
  ck('aria-expanded is true', (await toggle.getAttribute('aria-expanded').catch(() => null)) === 'true')
  const before = reads.length
  const btn = sec.getByRole('button', { name: /^250$/ }).first()
  if (await btn.count()) { await btn.click(); await page.waitForTimeout(600) }
  ck('a change sends the exact request', writes.length === 1 && writes[0].body.runs_step === 250, JSON.stringify(writes))
  ck('and the report is read again', reads.length > before, `${before} -> ${reads.length}`)
  await toggle.click().catch(() => {})
  await page.waitForTimeout(200)
  ck('closes again', !(await seen(page.getByText('Milestones tracked'))))
  await ctx.close()
}
{
  const { ctx, page } = await open({ width: 390, height: 900 })
  await page.locator('[data-testid="milestone-settings"] button').first().click().catch(() => {})
  await page.waitForTimeout(300)
  ck('390px: no horizontal overflow with the settings open', !(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)))
  await ctx.close()
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
