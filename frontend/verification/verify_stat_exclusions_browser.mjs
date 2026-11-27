// Drives the real Manual entries tab and match page in Chromium with the API stubbed at the network
// layer: a club leaves a whole match out of its players' career stats, and counts it again.
//
//   npx vite build && npx vite preview --port 5199 &
//   node verification/verify_stat_exclusions_browser.mjs [baseUrl]
//
// Reported by Kalamunda: the Tuesday T20 against Hills is a social fixture Cricket Australia lists like
// any other. Checks:
//   * Manual entries, Excluded Matches: pasting the play.cricket.com.au link asks the server about
//     exactly that link (the request on the wire), and shows the match and what comes off;
//   * a refusal (a PlayHQ link) is shown under the box;
//   * Exclude asks "Are you sure you want to exclude this match?"; Cancel sends nothing; Yes sends the
//     match id and the reason typed; the list then holds it and an Undo toast appears; Undo sends the
//     DELETE for that exclusion and the list empties;
//   * Count it again asks first, then sends the DELETE, and its toast's Undo excludes it again;
//   * the match page: the public sees the "Not counted in career stats" banner and never asks the admin
//     lookup; an admin sees the Exclude bar and gets the same confirm;
//   * 390px: nothing overflows sideways. Screenshots.
// Every read is guarded, so a control run against the previous build reports each check.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome'
const SHOTS = process.env.SHOTS || '/tmp'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const GID = '97e4fbfe-6bf7-4571-ba86-b2f8c20e6012'
const PC_LINK = `https://play.cricket.com.au/match/${GID}/hwcc-tuesday-t20-kcc-tuesday-t20-mountford-tillemans-shield-2026?tab=scorecard`
const MATCH = {
  game_id: GID, source: 'api', home_team: 'HWCC Tuesday T20', away_team: 'KCC Tuesday T20', played_at: '2026-11-24',
  result: 'KCC Tuesday T20 won by 4 wickets', status: 'COMPLETED', club_team: 'KCC Tuesday T20', other_team: 'HWCC Tuesday T20', grade_name: 'Tuesday T20', season_name: 'Summer 2026/27',
  players: [
    { player_id: 'p1', name: 'Able, Alex', runs: 55, innings: 1, wickets: 3, dismissals: 1 },
    { player_id: 'p2', name: 'Cole, Chris', runs: 31, innings: 1, wickets: 0, dismissals: 0 },
    { player_id: 'p3', name: 'Bench, Ben', runs: 0, innings: 0, wickets: 0, dismissals: 0 },
  ],
  totals: { players: 3, runs: 86, wickets: 3, dismissals: 1 },
}
const scorecard = {
  id: GID, home_team: MATCH.home_team, away_team: MATCH.away_team, home_away_known: true, innings_order_known: true,
  played_at: '2026-11-24', result: 'WIN', winning_team: 'KCC Tuesday T20', organisation_id: 'org1', is_manual: false,
  grade: { id: 'g1', name: 'Tuesday T20', raw_name: 'Tuesday T20' }, season: { id: 's1', name: 'Summer 2026/27' },
  innings_totals: { 1: { runs: 140, wickets: 6, extras: 9 } },
  batting: [], bowling: [], opp_batting: [], opp_bowling: [], fielding: [], fall_of_wickets: [], partnerships: [],
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(url, { admin = true, width = 1280, waitFor, excludedPublic = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1300 } })
  const page = await ctx.newPage()
  page.setDefaultTimeout(5000)
  const seen = { lookups: [], posts: [], deletes: [], errors: [] }
  let live = null   // the exclusion in force: { id, note, ... }
  let nextId = 41
  page.on('pageerror', e => seen.errors.push(String(e)))
  await page.route(/\/api\//, async route => {
    const req = route.request()
    const u = new URL(req.url())
    const p = u.pathname.replace(/^\/api/, '')
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p.startsWith('/auth/me')) {
      return admin
        ? json({ id: 'u1', username: 'kcc-admin', display_name: 'Admin', role: 'club_admin', club_id: 'org1',
                 club_slug: 'kalamunda', club_name: 'Kalamunda CC', entitlements: { modules: ['stats'], status: 'active' } })
        : route.fulfill({ status: 401, body: '{}' })
    }
    if (p === `/games/${GID}/scorecard`) return json({ ...scorecard, stats_excluded: excludedPublic || !!live })
    if (p === '/organisations/org1' || p === '/orgs/org1') return json({ id: 'org1', name: 'Kalamunda CC', slug: 'kalamunda' })
    if (p === '/club-admin/stat-exclusions/lookup') {
      const link = u.searchParams.get('link')
      seen.lookups.push(link)
      if (/playhq/.test(link)) {
        return json({ detail: "That's a PlayHQ link. Open the same match on play.cricket.com.au, or on your BetterCricket site, and paste that link instead." }, 422)
      }
      return json({ ...MATCH, exclusion: live })
    }
    if (p === '/club-admin/stat-exclusions' && req.method() === 'GET') {
      return json({ exclusions: live ? [{ ...MATCH, ...live, entered_by_name: 'kcc-admin', entered_at: '2026-11-27T09:00:00+08:00' }] : [] })
    }
    if (p === '/club-admin/stat-exclusions' && req.method() === 'POST') {
      const body = JSON.parse(req.postData() || '{}')
      seen.posts.push(body)
      live = { id: nextId++, game_id: GID, source: 'api', note: body.note || null }
      return json({ exclusion: live, match: { ...MATCH, exclusion: live }, summary: 'left out' })
    }
    const del = p.match(/^\/club-admin\/stat-exclusions\/(\d+)$/)
    if (del && req.method() === 'DELETE') {
      seen.deletes.push(Number(del[1]))
      const was = live
      live = null
      return json({ restored: was, summary: 'counted again' })
    }
    return json([])
  })
  await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' })
  if (waitFor) await page.waitForSelector(waitFor, { timeout: 20000 }).catch(() => {})
  await page.waitForTimeout(500)
  return { ctx, page, seen }
}

const overflow = page => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
const text = async (page, sel) => (await page.locator(sel).first().textContent().catch(() => '')) || ''
const has = async (page, sel) => (await page.locator(sel).count().catch(() => 0)) > 0

// ── Manual entries: find, confirm, exclude, undo ────────────────────────────
{
  const { ctx, page, seen } = await open('/admin/manual-entries#excluded', { waitFor: '[data-testid="excluded-matches"]' })
  ck('the Excluded Matches tab renders', await has(page, '[data-testid="excluded-matches"]'))
  ck('with an empty list that explains itself', (await text(page, '[data-testid="excluded-matches"]')).includes('No matches excluded'))

  await page.fill('[data-testid="exclude-link"]', 'https://www.playhq.com/cricket-australia/org/x/y/game-centre/abecedd5').catch(() => {})
  await page.click('[data-testid="find-match"]').catch(() => {})
  await page.waitForSelector('[data-testid="exclude-error"]', { timeout: 3000 }).catch(() => {})
  ck('a PlayHQ link is refused under the box', (await text(page, '[data-testid="exclude-error"]')).includes('PlayHQ'))

  await page.fill('[data-testid="exclude-link"]', PC_LINK).catch(() => {})
  await page.click('[data-testid="find-match"]').catch(() => {})
  await page.waitForSelector('[data-testid="match-preview"]', { timeout: 3000 }).catch(() => {})
  ck('the lookup asks about exactly the pasted link', seen.lookups.at(-1) === PC_LINK, seen.lookups.at(-1))
  const pv = await text(page, '[data-testid="match-preview"]')
  ck('the preview names the match and the grade', pv.includes('HWCC Tuesday T20 v KCC Tuesday T20') && pv.includes('Tuesday T20'), pv.slice(0, 120))
  ck('and what comes off: 3 players, 86 runs, 3 wickets', /3\s*Players/i.test(pv) && /86\s*Runs/i.test(pv) && /3\s*Wickets/i.test(pv), pv)
  ck('with each player and their figures', pv.includes('Able, Alex') && pv.includes('55 · 3w · 1ct'), pv)
  await page.screenshot({ path: `${SHOTS}/stat-exclusions-preview.png`, fullPage: true }).catch(() => {})

  await page.click('[data-testid="exclude-match"]').catch(() => {})
  await page.waitForSelector('[data-testid="exclude-confirm"]', { timeout: 3000 }).catch(() => {})
  const dlg = await text(page, '[role="dialog"]')
  ck('Exclude asks "Are you sure you want to exclude this match?"', dlg.includes('Are you sure you want to exclude this match?'), dlg.slice(0, 80))
  ck('and says the other side keeps its figures, and it can be undone',
     dlg.includes('HWCC Tuesday T20 players keep their figures') && dlg.includes('count it again at any time'), dlg)
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${SHOTS}/stat-exclusions-confirm.png` }).catch(() => {})
  await page.getByRole('button', { name: 'Cancel' }).last().click().catch(() => {})
  await page.waitForTimeout(200)
  ck('Cancel closes it and sends nothing', !(await has(page, '[data-testid="exclude-confirm"]')) && seen.posts.length === 0, seen.posts)

  await page.click('[data-testid="exclude-match"]').catch(() => {})
  await page.fill('[data-testid="exclude-note"]', 'Pre-season social T20').catch(() => {})
  await page.click('[data-testid="confirm-exclude"]').catch(() => {})
  await page.waitForSelector('[data-testid="undo-toast"]', { timeout: 3000 }).catch(() => {})
  ck('Yes sends the match id and the reason', JSON.stringify(seen.posts.at(-1)) === JSON.stringify({ link: GID, note: 'Pre-season social T20' }),
     JSON.stringify(seen.posts.at(-1)))
  await page.waitForSelector('[data-testid="excluded-row"]', { timeout: 3000 }).catch(() => {})
  const row = await text(page, '[data-testid="excluded-row"]')
  ck('the list now holds the match with its reason', row.includes('HWCC Tuesday T20 v KCC Tuesday T20') && row.includes('Pre-season social T20'), row)
  ck('an Undo toast appears', (await text(page, '[data-testid="undo-toast"]')).includes('Match excluded from career stats'))
  await page.waitForTimeout(300)
  await page.screenshot({ path: `${SHOTS}/stat-exclusions-list.png`, fullPage: true }).catch(() => {})
  await page.click('[data-testid="toast-undo"]').catch(() => {})
  await page.waitForTimeout(500)
  ck('Undo sends the DELETE for that exclusion', seen.deletes.at(-1) === 41, seen.deletes)
  ck('and the list empties', !(await has(page, '[data-testid="excluded-row"]')))

  // Exclude again, then Count it again from the list, then Undo that.
  await page.fill('[data-testid="exclude-link"]', PC_LINK).catch(() => {})
  await page.click('[data-testid="find-match"]').catch(() => {})
  await page.click('[data-testid="exclude-match"]').catch(() => {})
  await page.click('[data-testid="confirm-exclude"]').catch(() => {})
  await page.waitForSelector('[data-testid="restore-row"]', { timeout: 3000 }).catch(() => {})
  await page.click('[data-testid="toast-undo"] ~ button[aria-label="Dismiss"]').catch(() => {})
  await page.click('[data-testid="restore-row"]').catch(() => {})
  await page.waitForSelector('[data-testid="restore-confirm"]', { timeout: 3000 }).catch(() => {})
  ck('Count it again asks first', (await text(page, '[role="dialog"]')).includes('Count this match in career stats again?'))
  const before = seen.deletes.length
  await page.click('[data-testid="confirm-restore"]').catch(() => {})
  await page.waitForTimeout(400)
  ck('then sends the DELETE for the exclusion in force', seen.deletes.length === before + 1 && seen.deletes.at(-1) === 42, seen.deletes)
  ck('its toast says so', (await text(page, '[data-testid="undo-toast"]')).includes('counted in career stats again'))
  const posts = seen.posts.length
  await page.click('[data-testid="toast-undo"]').catch(() => {})
  await page.waitForTimeout(500)
  ck('and its Undo excludes the match again', seen.posts.length === posts + 1 && seen.posts.at(-1)?.link === GID, seen.posts)
  ck('no page errors', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}

// ── 390px ─────────────────────────────────────────────────────────────────────
{
  const { ctx, page } = await open('/admin/manual-entries#excluded', { width: 390, waitFor: '[data-testid="excluded-matches"]' })
  await page.fill('[data-testid="exclude-link"]', PC_LINK).catch(() => {})
  await page.click('[data-testid="find-match"]').catch(() => {})
  await page.waitForSelector('[data-testid="match-preview"]', { timeout: 3000 }).catch(() => {})
  ck('390px: the preview fits with no sideways scroll', (await overflow(page)) <= 0, `${await overflow(page)}px`)
  await page.screenshot({ path: `${SHOTS}/stat-exclusions-390.png`, fullPage: true }).catch(() => {})
  await page.click('[data-testid="exclude-match"]').catch(() => {})
  await page.waitForSelector('[data-testid="exclude-confirm"]', { timeout: 3000 }).catch(() => {})
  ck('390px: the confirm fits', (await overflow(page)) <= 0, `${await overflow(page)}px`)
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${SHOTS}/stat-exclusions-390-confirm.png` }).catch(() => {})
  await page.click('[data-testid="confirm-exclude"]').catch(() => {})
  await page.waitForSelector('[data-testid="excluded-row"]', { timeout: 3000 }).catch(() => {})
  ck('390px: the list row fits', (await overflow(page)) <= 0, `${await overflow(page)}px`)
  await ctx.close()
}

// ── Match page ────────────────────────────────────────────────────────────────
{
  const { ctx, page, seen } = await open(`/games/${GID}`, { admin: false, excludedPublic: true, waitFor: 'text=BACK' })
  await page.waitForSelector('[data-testid="stats-excluded-banner"]', { timeout: 4000 }).catch(() => {})
  const b = await text(page, '[data-testid="stats-excluded-banner"]')
  ck('public: the banner says the match is not counted in career stats', /not counted in career stats/i.test(b), b)
  ck('public: no Count it again button', !(await has(page, '[data-testid="match-restore"]')))
  ck('public: the admin lookup is never requested', seen.lookups.length === 0, seen.lookups)
  await page.screenshot({ path: `${SHOTS}/stat-exclusions-match-public.png` }).catch(() => {})
  await ctx.close()
}
{
  const { ctx, page, seen } = await open(`/games/${GID}`, { waitFor: '[data-testid="stats-exclude-bar"]' })
  ck('admin: the Exclude bar shows on a match the club played', await has(page, '[data-testid="stats-exclude-bar"]'))
  ck('admin: it asked about this match by id', seen.lookups.includes(GID), seen.lookups)
  await page.click('[data-testid="match-exclude"]').catch(() => {})
  await page.waitForSelector('[data-testid="exclude-confirm"]', { timeout: 3000 }).catch(() => {})
  ck('admin: the same "are you sure" confirm', (await text(page, '[role="dialog"]')).includes('Are you sure you want to exclude this match?'))
  await page.click('[data-testid="confirm-exclude"]').catch(() => {})
  await page.waitForSelector('[data-testid="stats-excluded-banner"]', { timeout: 3000 }).catch(() => {})
  ck('admin: the bar turns into the banner, with Count it again', await has(page, '[data-testid="match-restore"]'))
  ck('admin: and an Undo toast', await has(page, '[data-testid="toast-undo"]'))
  await page.screenshot({ path: `${SHOTS}/stat-exclusions-match-admin.png` }).catch(() => {})
  await page.click('[data-testid="toast-undo"]').catch(() => {})
  await page.waitForSelector('[data-testid="stats-exclude-bar"]', { timeout: 3000 }).catch(() => {})
  ck('admin: Undo sends the DELETE and puts the Exclude bar back', seen.deletes.length === 1 && await has(page, '[data-testid="stats-exclude-bar"]'), seen.deletes)
  ck('admin: no page errors', seen.errors.length === 0, seen.errors.join(' | '))
  await ctx.close()
}
{
  const { ctx, page } = await open(`/games/${GID}`, { width: 390, admin: false, excludedPublic: true, waitFor: '[data-testid="stats-excluded-banner"]' })
  ck('390px: the match page banner fits', (await overflow(page)) <= 0, `${await overflow(page)}px`)
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
