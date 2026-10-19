// Drives the real BetterSelect Fixtures page in Chromium with the API stubbed at
// the network layer. The report (Oct 2026): Sunday games appeared to be missing
// from Fixtures but showed in Availability. They were inside the Saturday card:
// cards are per weekend, the header names the first game's date only, rows carry
// no date and were sorted by team, not by day.
//
// Checks: a weekend with Sat + Sun games is ONE card with a day separator per
// day, Sunday's game sits under the Sunday separator (even when it is the
// senior team), a Saturday-only weekend has no separator, and 390px does not
// overflow.
//
//   APP_URL=http://localhost:4173 node verify_fixtures_day_split_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}
const ymd = (d) => d.toISOString().slice(0, 10)
const nextSat = new Date(); nextSat.setDate(nextSat.getDate() + ((6 - nextSat.getDay() + 7) % 7 || 7))
const sat1 = ymd(nextSat)
const sun1 = ymd(new Date(nextSat.getTime() + 864e5))
const sat2 = ymd(new Date(nextSat.getTime() + 7 * 864e5))
const label = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

const fx = (id, date, seq, team, opp, time) => ({
  id, organisation_id: 'org-1', grade_id: null, team_id: 't' + seq, team_name: team, team_short: team,
  team_sequence: seq, source: 'grassroots', playhq_id: id, label: null, round: '2', played_on: date,
  end_on: null, start_time: time, home_team: null, away_team: null, home_away: 'HOME',
  opponent_name: opp, venue: 'Ground', status: 'UPCOMING', notes: null, lineup_count: 0, format_size: 11,
})
const FIXTURES = [
  fx('f1', sat1, 1, '1st XI', 'SatOne', '12:00'),
  fx('f2', sat1, 2, '2nd XI', 'SatTwo', '12:00'),
  fx('f3', sun1, 1, 'T20 Div 1', 'SunSenior', '10:30'),   // senior team, Sunday
  fx('f4', sun1, 5, '5th XI', 'SunFive', '10:30'),
  fx('f5', sat2, 1, '1st XI', 'NextWeek', '12:00'),
]
const ME = {
  id: 'u-1', username: 'admin', email: 'a@b.c', role: 'club_admin', organisation_id: 'org-1',
  club_slug: 'verify-cc', capabilities: [], entitlements: { modules: ['select'], core_live: true, status: 'active' },
}

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium',
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json(ME)
    if (/\/fixtures(\?|$)/.test(url)) return json(FIXTURES)
    if (/\/teams(\?|$)/.test(url)) return json([])
    return json({})
  })
  await page.goto(`${BASE}/admin/betterselect/fixtures`)
  await page.waitForSelector('text=SatOne', { timeout: 20000 })

  // Cards, each with its separators and the opponents in on-screen order.
  const cards = await page.evaluate(() => [...document.querySelectorAll('.pb-card')]
    .filter((c) => /vs |@ /.test(c.innerText))
    .map((c) => {
      const seps = [...c.querySelectorAll('div')].filter((d) => d.children.length === 0 && /^[A-Za-z]{3},? /.test(d.textContent.trim()) && d.className.includes('tracking-wide2'))
        .map((d) => d.textContent.trim())
      const order = [...c.querySelectorAll('.text-\\[14\\.5px\\]')].map((e) => e.textContent.replace(/^(vs |@ )/, '').trim())
      return { seps, order }
    }))
  check('two weekend cards', cards.length === 2, JSON.stringify(cards))
  const [wk1, wk2] = cards
  check('Sat+Sun weekend: a separator for each day', JSON.stringify(wk1?.seps) === JSON.stringify([label(sat1), label(sun1)]), JSON.stringify(wk1?.seps))
  check('Sunday senior game sits after both Saturday games',
    JSON.stringify(wk1?.order) === JSON.stringify(['SatOne', 'SatTwo', 'SunSenior', 'SunFive']), JSON.stringify(wk1?.order))
  check('Saturday-only weekend has no separator', (wk2?.seps || []).length === 0, JSON.stringify(wk2?.seps))
  if (SHOT) await page.screenshot({ path: `${SHOT}/fixtures-day-split.png`, fullPage: true })

  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(200)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check('390px: no horizontal overflow', overflow <= 0, String(overflow))
  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  process.exit(FAIL.length ? 1 : 0)
}
run()
