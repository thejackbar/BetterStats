// Drives the Podcast Run Sheet inside an ASSOCIATION SOCIALS WORKSPACE in Chromium,
// with the API stubbed at the network layer (backend: routers/podcast.py).
//
//   npx vite build && npx vite preview --port 5199 &
//   PULL_JSON=/path/to/a/real/pull.json node frontend/verification/verify_podcast_run_sheet_browser.mjs [baseUrl]
//
// PULL_JSON is optional: one competition's pull as the backend returned it for a
// real round. Without it a small inline round is used.
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const SHOTS = process.env.SHOTS || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const INLINE = {
  kind: 'round', grade: '1st Grade', grade_id: 'g1', round: 'Round 4', round_id: 'r4', season: '2026/27', date: '2026-11-07', label: 'SAT 7 NOV',
  results: [{ match_id: 'm1', url: 'https://play.cricket.com.au/match/m1', home: 'Subiaco Marist', away: 'Swan Valley', home_score: '134', away_score: '153',
    winner: 'away', result: 'Swan Valley 1st XI won by 19 runs', margin: { runs: 19, wickets: null, tie: false, closeness: 19 }, venue: 'Oval', date: '2026-11-07',
    home_rank: 3, away_rank: 1, top_bat: [], top_bowl: [] }],
  not_played: [], skipped: [],
  batting: [{ name: 'Heshan Perera', team: 'Swan Valley', opp: 'Subiaco Marist', runs: 80, balls: 151, not_out: false, match_id: 'm1', line: '80 (151)' }],
  bowling: [{ name: 'Jeffrey Willey', team: 'Swan Valley', opp: 'Subiaco Marist', overs: '12', runs: 30, wickets: 4, hat_tricks: 0, match_id: 'm1', line: '4/30 (12)' }],
  performers: [{ name: 'Heshan Perera', team: 'Swan Valley', opp: 'Subiaco Marist', points: 96, line: '80 (151), 1 ct', match_id: 'm1' }],
  milestones: [{ kind: 'fifty', name: 'Heshan Perera', team: 'Swan Valley', text: 'Heshan Perera (Swan Valley) made 80 (151) against Subiaco Marist', match_id: 'm1' }],
  fielders: [], catches: [], catches_total: 0, run_outs: [],
  ladder: [{ rank: 1, team_id: 't1', team: 'Swan Valley', played: 4, won: 4, lost: 0, points: 36 }, { rank: 3, team_id: 't3', team: 'Subiaco Marist', played: 4, won: 2, lost: 2, points: 26 }],
  upsets: [], upset_gap: 3,
  next_round: { round: 'Round 5', match_of_round: 0, fixtures: [{ match_id: 'f1', url: '', home: 'Swan Valley', away: 'Bedford Morley', home_rank: 1, away_rank: 6, date: '2026-11-21', label: 'SAT 21 NOV', time: '12:30 PM', venue: 'Swan Valley Sporting Club' }] },
}
const PULL = process.env.PULL_JSON ? JSON.parse(readFileSync(process.env.PULL_JSON, 'utf8')) : INLINE
const LINK = 'https://play.cricket.com.au/match/bf35fc33-02b9-4c55-84aa-fed719f64422/smcc-v-swan-valley'

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(viewport) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  const calls = [], errors = []
  const episodes = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (body, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/*', async (route) => {
    const req = route.request()
    const url = req.url()
    if (!/\/api\//.test(url)) return route.continue()
    const u = new URL(url)
    calls.push({ method: req.method(), path: u.pathname, search: u.search, body: req.postData() })
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'staff', role: 'super_admin', club_slug: null, club_name: 'Hills Association', workspace_kind: 'association',
      acting_as_club: true, home_club_name: 'BetterCricket', can_switch_clubs: true, capabilities: ['manage_social'],
      entitlements: { modules: ['socials'], status: 'active' },
    }))
    if (u.pathname.endsWith('/admin/podcast/pull')) return route.fulfill(json(PULL))
    if (u.pathname.endsWith('/admin/podcast/episodes') && req.method() === 'GET') return route.fulfill(json({ episodes }))
    if (u.pathname.endsWith('/admin/podcast/episodes') && req.method() === 'POST') {
      const ep = { id: `e${episodes.length + 1}`, episode_no: episodes.length + 1, recording_date: null, round_label: '', data: {} }
      episodes.unshift(ep)
      return route.fulfill(json(ep))
    }
    const m = u.pathname.match(/\/admin\/podcast\/episodes\/([^/]+)$/)
    if (m) {
      const ep = episodes.find(e => e.id === m[1])
      if (req.method() === 'PATCH') Object.assign(ep, JSON.parse(req.postData() || '{}'))
      return route.fulfill(json(ep))
    }
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json({ id: 'ws-1', name: 'Hills Association', workspace_kind: 'association' }))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/podcast`, { waitUntil: 'domcontentloaded' })
  return { ctx, page, calls, errors }
}

{
  const { ctx, page, calls, errors } = await open({ width: 1400, height: 1000 })
  const start = page.getByRole('button', { name: 'Start episode 1' })
  await start.waitFor({ timeout: 25000 })
  ck('empty state offers episode 1', await start.isVisible())
  ck('sidebar carries the run sheet in a workspace', (await page.getByRole('link', { name: /Podcast Run Sheet/ }).count()) > 0)
  await start.click()
  await page.getByText('Episode Details').waitFor()
  ck('POST creates the episode', calls.some(c => c.method === 'POST' && c.path.endsWith('/admin/podcast/episodes')))
  for (const name of ['1. Opening', '2. Around the Grounds', '3. Stats Corner', '4. Awards', '5. Club Spotlight', '6. Guest Segment', '7. Looking Ahead', 'Sunday Night Preparation', 'Episode Close']) {
    ck(`segment shown: ${name}`, await page.getByRole('heading', { name }).isVisible())
  }
  ck('three competitions by default', (await page.getByLabel('Competition name').count()) === 3)
  ck('running time adds the segments', /29 MINS OF 30/.test(await page.getByTestId('running-time').innerText()))

  await page.getByLabel('North match link').fill(LINK)
  await page.getByTestId('comp-0').getByRole('button', { name: 'Pull' }).click()
  await page.getByTestId('grounds-north').locator('li').first().waitFor({ timeout: 5000 })
  const pullCall = calls.find(c => c.path.endsWith('/admin/podcast/pull'))
  ck('pull sends the pasted link as q', pullCall && new URLSearchParams(pullCall.search).get('q') === LINK, pullCall?.search)
  ck('every result is listed for North', (await page.getByTestId('grounds-north').locator('li').count()) === PULL.results.length)
  ck('round label filled from the pull', (await page.getByLabel(/^ROUND$/).inputValue().catch(() => '')) === PULL.round
    || (await page.locator('input[placeholder="Round 5"]').inputValue()) === PULL.round)

  const hs = page.getByTestId('item-high-scores')
  const top = PULL.batting[0]
  ck('highest score suggestion names the top innings', (await hs.getByText(`${top.name} (${top.team}) ${top.line}`, { exact: false }).count()) > 0)
  await hs.getByRole('button').first().click()
  ck('a suggestion click adds it to the notes', (await hs.locator('textarea').inputValue()).includes(top.name))
  await page.waitForTimeout(1500)
  const patch = calls.filter(c => c.method === 'PATCH').pop()
  const body = patch ? JSON.parse(patch.body) : {}
  ck('autosave PATCH carries the note', (body.data?.notes?.high_scores || '').includes(top.name))
  ck('autosave PATCH carries the round label', body.round_label === PULL.round)
  ck('autosave PATCH carries the pull, so the episode reopens as recorded', body.data?.competitions?.[0]?.pull?.results?.length === PULL.results.length)
  ck('save state reads saved', /SAVED/.test(await page.getByTestId('save-state').innerText()))

  const mor = PULL.next_round.fixtures[PULL.next_round.match_of_round]
  ck('match of the round suggested from the ladder', (await page.getByTestId('item-mor').getByText(`${mor.home} (`, { exact: false }).count()) > 0)
  const upsetEmpty = PULL.upsets.length === 0
  ck('upset item explains itself either way', upsetEmpty
    ? (await page.getByTestId('item-upset').getByText(/3 or more places below/).count()) > 0
    : (await page.getByTestId('item-upset').getByTestId('suggestions').count()) > 0)
  ck('player of the round suggestion present', (await page.getByTestId('item-potr').getByText(PULL.performers[0].name, { exact: false }).count()) > 0)
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/desktop.png`, fullPage: true })
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

{
  const { ctx, page, errors } = await open({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Start episode 1' }).click({ timeout: 25000 })
  await page.getByLabel('North match link').fill(LINK)
  await page.getByTestId('comp-0').getByRole('button', { name: 'Pull' }).click()
  await page.getByTestId('grounds-north').locator('li').first().waitFor({ timeout: 5000 })
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no sideways scroll', over <= 0, `overflow ${over}px`)
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/phone.png`, fullPage: true })
  ck('390px: no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
