// Super Admin "Privacy requests": drives the real screen in Chromium with the API
// stubbed at the network layer.
//
//   npx vite build --outDir /tmp/dist_pr && npx vite preview --outDir /tmp/dist_pr --port 5211 &
//   node frontend/verification/verify_privacy_requests_browser.mjs [baseUrl]
//
// Asserts the exact request on the wire for the search and for the download, that
// a short search is refused client-side (no request), that every status reads in
// words, that the PDF is saved under the filename the server gave, that a refusal
// from the server is shown, and that nothing overflows at 390px.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5211'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || '/tmp/claude-0'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const PLAYERS = [
  { id: 'p1', name: 'Alex Sample', club: 'Kalamunda CC', has_participant_id: true, status: 'removed_at_request' },
  { id: 'p2', name: 'Alex Sample', club: 'Rival Club with a rather long name that must truncate on a phone', has_participant_id: true, status: 'removed_at_request' },
  { id: 'p3', name: 'Alex Sample', club: 'Kalamunda CC', has_participant_id: false, status: 'name_match_hold' },
  { id: 'p4', name: 'Alexa Sampson', club: 'Kalamunda CC', has_participant_id: true, status: 'public' },
  { id: 'p5', name: 'Alec Samples', club: 'Kalamunda CC', has_participant_id: true, status: 'hidden_by_club' },
]
const PDF = Buffer.from('%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n')

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(width) {
  const ctx = await browser.newContext({ viewport: { width, height: 1100 }, acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = [], calls = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_|status of 4\d\d/.test(m.text())) errors.push(m.text()) })
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace(/^\/api/, '')
    calls.push({ method: req.method(), p, q: url.searchParams.get('q'), cookie: req.headers()['cookie'] })
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p === '/auth/me') return json({ id: 'u1', username: 'jack', role: 'super_admin', club_id: 'c1', club_slug: 'alpha',
      club_name: 'Alpha', is_primary_admin: true, can_switch_clubs: true, entitlements: { modules: [], status: 'active', billing_modules: [] }, capabilities: [] })
    if (p === '/club-admin/super/privacy/players') {
      const q = (url.searchParams.get('q') || '').toLowerCase()
      return json(q.length < 3 ? { players: [], note: 'Type at least three characters of a name, or paste a player id.' } : { players: PLAYERS })
    }
    if (p === '/club-admin/super/privacy/players/p5/data-report.pdf') return json({ detail: 'Player not found' }, 404)
    if (/^\/club-admin\/super\/privacy\/players\/[^/]+\/data-report\.pdf$/.test(p)) {
      return route.fulfill({ status: 200, contentType: 'application/pdf', body: PDF,
        headers: { 'content-disposition': 'attachment; filename="data-held-alex-sample-2026-10-08.pdf"', 'cache-control': 'no-store' } })
    }
    if (p === '/club-admin/broadcasts') return json({ items: [], preview: false })
    return json([])
  })
  await page.goto(`${BASE}/admin/super/privacy-requests`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('#privacy-q', { timeout: 20000 })
  return { page, ctx, errors, calls }
}

for (const width of [1280, 390]) {
  console.log(`\nPrivacy requests at ${width}px`)
  const { page, ctx, errors, calls } = await open(width)
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)

  ck('the page explains what the PDF holds and warns to check who is asking',
    /personal information BetterCricket holds/.test(await page.locator('body').innerText())
    && /Confirm who is asking/.test(await page.locator('body').innerText()))
  ck('it says hiding is a server script, not a button', /hide_player_at_request/.test(await page.locator('body').innerText()))
  ck('Search is disabled for a short query', await page.getByRole('button', { name: 'SEARCH' }).isDisabled())
  await page.fill('#privacy-q', 'al')
  ck('...still disabled at two characters, and no request was sent',
    await page.getByRole('button', { name: 'SEARCH' }).isDisabled() && !calls.some((c) => c.p.includes('/privacy/players')))

  await page.fill('#privacy-q', 'Alex Sample')
  await page.getByRole('button', { name: 'SEARCH' }).click()
  await page.waitForSelector('[data-testid="privacy-player"]')
  const search = calls.find((c) => c.p === '/club-admin/super/privacy/players')
  ck('the search sends the typed name as q', search && search.q === 'Alex Sample', JSON.stringify(search))
  ck('five results are drawn', (await page.locator('[data-testid="privacy-player"]').count()) === 5)
  const body = await page.locator('body').innerText()
  ck('each status reads in words',
    /Removed at their request/.test(body) && /Held: same name as a removed person/.test(body)
    && /On the public site/.test(body) && /Hidden by the club/.test(body))
  ck('a row with no Cricket Australia id says so', /no Cricket Australia id/.test(body))
  ck(`no horizontal overflow at ${width}px`, (await overflow()) <= 1, String(await overflow()))
  await page.screenshot({ path: `${SHOTS}/pr_results_${width}.png`, fullPage: true })

  // Download: exact request, file saved under the server's filename.
  const [dl] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('[data-testid="privacy-player"]').first().getByRole('button', { name: 'DOWNLOAD PDF' }).click(),
  ])
  ck('the download saves under the filename the server gave', dl.suggestedFilename() === 'data-held-alex-sample-2026-10-08.pdf', dl.suggestedFilename())
  const dcall = calls.find((c) => c.p.endsWith('/p1/data-report.pdf'))
  ck('the download is a GET for that player\'s PDF', dcall && dcall.method === 'GET', JSON.stringify(dcall))
  await page.waitForTimeout(300)
  ck('it tells the admin to check who is asking before sending', /Check who is asking before you send it/.test(await page.locator('body').innerText()))

  // A refusal from the server is shown, not swallowed.
  await page.locator('[data-testid="privacy-player"]').nth(4).getByRole('button', { name: 'DOWNLOAD PDF' }).click()
  await page.waitForTimeout(500)
  ck('a 404 from the server is shown as an error', /Player not found/.test(await page.locator('[role="alert"]').innerText()))

  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
