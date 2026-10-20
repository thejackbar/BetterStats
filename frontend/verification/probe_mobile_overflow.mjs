// Prints how far each phone-size screen is wider than the screen. A probe, not a
// pass/fail check: run it against any build to see the baseline.
import { launch, overflow, stubAccounts, stubSquads, BASE, json } from './mobile_harness.mjs'
import { readFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const SHOTS = process.env.SHOTS_DIR || join(HERE, 'shots')
mkdirSync(SHOTS, { recursive: true })
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures/selection_same_day.json'), 'utf8'))

const { browser, page, errors } = await launch()
const show = async (label, url, ready) => {
  await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' })
  await ready().catch(() => {})
  await page.waitForTimeout(500)
  console.log(label, JSON.stringify(await overflow(page)))
  await page.screenshot({ path: join(SHOTS, `${process.env.TAG || 'probe'}_${label}.png`) })
}

await stubAccounts(page)
await show('accounts', '/admin/fees', () => page.getByText('Abbas, Aamir').first().waitFor({ timeout: 8000 }))

await stubSquads(page)
await show('squads', '/admin/betterselect/teams', () => page.getByText('Abbas, Aamir').first().waitFor({ timeout: 8000 }))

await page.route(/\/api\/selection\/overview/, (r) => json(r, { fixtures: [], default_team_size: 11 }))
await page.route(/\/api\/selection\/[^/]+\/previous-xi/, (r) => json(r, { player_ids: [] }))
await page.route(new RegExp(`/api/selection/${FIX.fixture_id}/draft`), (r) => json(r, { draft: null, version: 0 }))
await page.route(new RegExp(`/api/selection/${FIX.fixture_id}$`), (r) => json(r, FIX.payload))
await show('selection', `/admin/betterselect/select/${FIX.fixture_id}`, () => page.getByText('Cara Free').first().waitFor({ timeout: 8000 }))

if (errors.length) console.log('page errors:', errors.slice(0, 3))
await browser.close()
