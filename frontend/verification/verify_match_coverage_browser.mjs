// Drives the real player profile in Chromium with the API stubbed at the
// network layer.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_match_coverage_browser.mjs [baseUrl]
//
// Reported off Rob Wilton's profile: 333 matches with Competition set to All,
// 337 with one competition picked. A filter that INCREASES a total is
// incoherent however it is explained, and the reader's next move is to add the
// competitions up and conclude the site is broken.
//
// The fix is not a renumbering — both figures are real, and adopting the
// higher one would rewrite 19,439 careers platform-wide. It is to SAY SO
// BEFORE ANYONE HAS TO NOTICE. So the checks here are about the note being
// there on the UNFILTERED view, reading correctly in BOTH directions (we hold
// more than CA counts about as often as fewer), and never being drawn on a
// player it has nothing to tell.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const PID = 'aaaaaaaa-0000-0000-0000-0000000000aa'
const ORG = 'bbbbbbbb-0000-0000-0000-0000000000bb'

const career = (games) => ({
  player_id: PID, name: 'Wilton, Rob', organisation_id: ORG,
  innings: games, total_runs: games * 30, high_score: 96, average: 31.2,
  strike_rate: 71.4, fifties: 8, hundreds: 0, ducks: 4,
  total_fours: 120, total_sixes: 9, games,
})

// The reported shape: a filter reads HIGHER than All.
const SURPLUS = {
  player: { id: PID, name: 'Wilton, Rob', display_name: 'Wilton, Rob',
            organisation_id: ORG, claimed: false, photo_url: null,
            is_overseas: false, overseas_country: null },
  career_batting: career(333),
  career_bowling: null, career_fielding: null,
  batting_innings: [], bowling_spells: [],
  match_coverage: { career_matches: 333, breakdown_matches: 337,
                    without_scorecard: 0, extra_scorecards: 4 },
  grade_scope: { categories: [], excluded_categories: [], formats: null,
                 competitions: null, competition_names: [], active: false,
                 category_active: false, format_active: false,
                 competition_active: false, available: ['senior'],
                 available_competitions: [], auto_shown: false },
}

// The more common direction platform-wide: CA counts more than we hold.
const SHORT = JSON.parse(JSON.stringify(SURPLUS))
SHORT.career_batting = career(150)
SHORT.match_coverage = { career_matches: 150, breakdown_matches: 106,
                         without_scorecard: 44, extra_scorecards: 0 }

// The two sources agree — the backend sends no block, so nothing is drawn.
const AGREES = JSON.parse(JSON.stringify(SURPLUS))
AGREES.career_batting = career(212)
delete AGREES.match_coverage

// The reported player's shape, reduced. The grid reconciles per season and
// grade and takes whichever source is higher, so its total is a THIRD number:
// 8 grade rows we hold a scorecard for, plus 5 Cricket Australia counts in a
// grade we hold none for = 13, against a header of 12 held / 9 CA.
const TEAM_BREAKDOWN = {
  rows: [
    { grade_name: '6th Grade', matches: 5, scorecard_matches: 5,
      attributed_unknown: 0, seasons: 3, won: 3, lost: 2, drawn: 0, win_pct: 60 },
    { grade_name: '8th Grade', matches: 3, scorecard_matches: 3,
      attributed_unknown: 0, seasons: 2, won: 1, lost: 2, drawn: 0, win_pct: 33 },
    { grade_name: 'One Day Grade 1', matches: 5, scorecard_matches: 0,
      attributed_unknown: 5, seasons: 2, won: 0, lost: 0, drawn: 0, win_pct: null },
  ],
  season_rows: [], unattributed: 0,
}
// Held 12 against CA's 9, so the header reads a surplus AND the grid sits
// above both — the exact three-number case that was reported.
const GRID = JSON.parse(JSON.stringify(SURPLUS))
GRID.career_batting = career(9)
GRID.match_coverage = { career_matches: 9, breakdown_matches: 12,
                        without_scorecard: 0, extra_scorecards: 3 }

// The club default already active: junior grades excluded with nobody having
// touched a control. On a club with a junior programme this is the ORDINARY
// state, and it is what makes "the headline is the career total" false.
const DEFAULTED = JSON.parse(JSON.stringify(SURPLUS))
DEFAULTED.career_batting = career(11)
DEFAULTED.match_coverage = { career_matches: 9, breakdown_matches: 14,
                             without_scorecard: 0, extra_scorecards: 5 }
DEFAULTED.grade_scope = { ...SURPLUS.grade_scope, active: true,
                          category_active: true,
                          excluded_categories: ['junior'],
                          available: ['senior', 'junior'] }

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(stats, { width = 1440, team = null } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = []
  const wire = []   // every /teammates query string, to prove the pick reaches it
  page.on('pageerror', (e) => errors.push(String(e)))
  // Routed by REGEX, not a glob: Playwright's `**` does not cross a `?`, so a
  // glob silently loses `/stats?categories=…` to the catch-all.
  await page.route(/\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, '')
    if (/\/players\/[^/]+\/stats$/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
                             body: JSON.stringify(stats) })
    }
    if (/^\/auth\/me/.test(path)) return route.fulfill({ status: 401, body: '{}' })
    // The profile fans out to ~20 endpoints and most of them return a LIST.
    // A stub answering `{}` everywhere takes the page down on the first
    // `achievements is not iterable` — a broken page measures nothing.
    if (team && /\/team-breakdown$/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
                             body: JSON.stringify(team) })
    }
    // The whole filter row is gated on the club having a season, so the stub
    // has to hand one back or there is no pill to press.
    if (/\/organisations\/[^/]+\/seasons$/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify([{ id: 'dddddddd-0000-0000-0000-0000000000dd',
                                name: 'Summer 2025/26', year: 2025 }]) })
    }
    if (/\/grade-categories$/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ available: ['senior', 'junior'], default: ['senior'],
                               available_formats: ['one_day', 'two_day'],
                               available_competitions: [] }) })
    }
    if (/\/teammates$/.test(path)) {
      wire.push(new URL(route.request().url()).search)
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ player: { player_id: PID, name: 'Wilton, Rob' },
                               teammates: [{ player_id: 'cccccccc-0000-0000-0000-0000000000cc',
                                             name: 'Mate, Mick', games: 5, wins: 3,
                                             losses: 2, draws: 0, win_pct: 60 }] }) })
    }
    const obj = /team-breakdown|grade-categories|captain-stats|self-serve|usage/.test(path)
    return route.fulfill({ status: 200, contentType: 'application/json',
                           body: obj ? '{}' : '[]' })
  })
  await page.goto(`${BASE}/players/${PID}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('text=MATCHES', { timeout: 15000 }).catch(() => {})
  // The headline counts UP (AnimatedNum), so reading it straight away catches
  // it mid-animation — "MATCHES187" for a career of 212. Wait for the figure
  // to stop moving rather than sleeping a guessed number of milliseconds.
  await page.waitForFunction(() => {
    const tile = [...document.querySelectorAll('.pb-card')]
      .find(e => /^\s*MATCHES/.test(e.innerText || ''))
    if (!tile) return false
    const now = tile.innerText
    const settled = window.__mcPrev === now
    window.__mcPrev = now
    return settled
  }, null, { polling: 200, timeout: 10000 }).catch(() => {})
  return { page, ctx, errors, wire }
}

const bodyText = (page) => page.evaluate(() =>
  (document.body.innerText || '').replace(/\s+/g, ' ').trim())
const dotCount = (page) => page.evaluate(() =>
  document.querySelectorAll('button [aria-label*="filter does not"]').length)

// The note as the page actually renders it, read out of the tile that holds
// the MATCHES figure — not from anywhere on the document. A check scoped to
// the whole page passes on a note rendered in the wrong place.
async function readTile(page) {
  return page.evaluate(() => {
    for (const el of document.querySelectorAll('.pb-card')) {
      if (!/^\s*MATCHES/.test(el.innerText || '')) continue
      return {
        text: (el.innerText || '').replace(/\s+/g, ' ').trim(),
        // The headline read out of its OWN element, not matched inside the
        // tile's whole text: "MATCHES212" has no word boundary between the
        // label and the figure, and the note beside it quotes numbers too, so
        // a blob match either fails on a correct page or passes on a wrong one.
        figure: (el.querySelector('.pb-num')?.textContent || '').trim(),
        hasButton: !!el.querySelector('button[aria-label="Why these figures differ"]'),
      }
    }
    return null
  })
}

try {
  console.log('\n-- the reported case: a filter reads HIGHER than All --')
  {
    const { page, ctx, errors } = await open(SURPLUS)
    const tile = await readTile(page)
    ck('the MATCHES tile is found at all', !!tile, JSON.stringify(tile))
    ck('the headline figure is still Cricket Australia\'s own 333',
       tile?.figure === '333', tile?.figure)
    ck('THE NOTE IS DRAWN ON THE UNFILTERED VIEW — the whole point, so nobody '
       + 'adds the competitions up first and reads the gap as a mistake',
       !!tile && /337/.test(tile.text), tile?.text)
    ck('and it reads as a surplus, never as "337 of 333"',
       !!tile && /more than/.test(tile.text) && !/337 of 333/.test(tile.text),
       tile?.text)
    ck('an explainer is offered beside it', !!tile && tile.hasButton)

    // `?? ''` so a CONTROL RUN with the note absent reports each check
    // rather than dying here and saying nothing about the rest.
    const before = (await readTile(page))?.text ?? ''
    // Short timeout + a swallowed failure: a CONTROL RUN has no button to
    // click, and must REPORT the checks below rather than hanging for the
    // default 30s and then dying with nothing said about them.
    await page.click('button[aria-label="Why these figures differ"]',
                     { timeout: 2000 }).catch(() => {})
    await page.waitForTimeout(150)
    const after = (await readTile(page))?.text ?? ''
    ck('opening the explainer says where each figure comes from',
       after.length > before.length && /Cricket Australia/.test(after)
       && /season figures/.test(after), after.slice(0, 200))
    ck('it names the surplus direction rather than the missing one',
       /runs the other way/.test(after) && !/no scorecard for/.test(after),
       after.slice(0, 400))
    ck('and says neither figure is adjusted to match the other',
       /Neither is adjusted/.test(after))
    await page.click('button[aria-label="Why these figures differ"]',
                     { timeout: 2000 }).catch(() => {})
    await page.waitForTimeout(150)
    ck('and it closes again',
       ((await readTile(page))?.text ?? '').length === before.length && before.length > 0)
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- the other direction: CA counts more than we hold --')
  {
    const { page, ctx, errors } = await open(SHORT)
    const tile = await readTile(page)
    ck('the headline is CA\'s 150', tile?.figure === '150', tile?.figure)
    ck('the note says how much of it can be broken down',
       !!tile && /106 of these 150/.test(tile.text), tile?.text)
    // Short timeout + a swallowed failure: a CONTROL RUN has no button to
    // click, and must REPORT the checks below rather than hanging for the
    // default 30s and then dying with nothing said about them.
    await page.click('button[aria-label="Why these figures differ"]',
                     { timeout: 2000 }).catch(() => {})
    await page.waitForTimeout(150)
    const after = (await readTile(page))?.text ?? ''
    ck('the explainer accounts for the other 44',
       /other 44 matches/.test(after), after.slice(0, 400))
    ck('and says plainly there is nothing waiting to be filed, so nobody goes '
       + 'looking for a grade to assign', /nothing waiting to be filed/.test(after))
    ck('it does NOT claim a surplus in this direction',
       !/runs the other way/.test(after))
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- silence where there is nothing to say --')
  {
    const { page, ctx, errors } = await open(AGREES)
    const tile = await readTile(page)
    ck('the headline still draws', tile?.figure === '212', tile?.figure)
    ck('NO note is drawn on a player the two sources agree on — a note on '
       + 'everybody is noise that teaches people to stop reading notes',
       !!tile && !tile.hasButton && !/scorecard/.test(tile.text), tile?.text)
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- and the grid is a THIRD number again --')
  {
    const { page, ctx, errors } = await open(GRID, { team: TEAM_BREAKDOWN })
    await page.click('text=Analysis').catch(() => {})
    await page.waitForTimeout(400)
    await page.click('text=Team').catch(() => {})
    await page.waitForSelector('text=MATCHES BY GRADE', { timeout: 10000 })
      .catch(() => {})
    const grid = await page.evaluate(() => {
      const card = [...document.querySelectorAll('.pb-card')]
        .find(e => /MATCHES BY GRADE/.test(e.innerText || ''))
      if (!card) return null
      const rows = [...card.querySelectorAll('tr')].map(
        tr => (tr.innerText || '').replace(/\s+/g, ' ').trim())
      return { total: rows.find(r => /^TOTAL/.test(r)) || '',
               text: (card.innerText || '').replace(/\s+/g, ' ').trim() }
    })
    ck('the grid draws with its own total', !!grid && /^TOTAL 13\b/.test(grid.total),
       grid?.total)
    ck('THE GRID SAYS WHY ITS TOTAL IS NEITHER HEADER FIGURE, rather than '
       + 'leaving a third number to be found by adding the rows up',
       !!grid && /whichever is higher/.test(grid.text), grid?.text?.slice(0, 300))
    ck('and shows the arithmetic off its own rows: 8 held + 5 added = 13',
       !!grid && /8 we hold a scorecard for/.test(grid.text)
       && /\+ 5 Cricket Australia counts/.test(grid.text)
       && /= 13\./.test(grid.text), grid?.text?.slice(0, 500))
    ck('the scorecards with no grade at all are accounted for too — 12 held on '
       + 'the header against 8 on a row here', !!grid
       && /A further 4 matches have a scorecard but no grade recorded/.test(grid.text),
       grid?.text?.slice(0, 600))
    ck('the asterisk is explained without claiming a rule it does not follow',
       !!grid && /Cricket Australia counts in this grade that we hold no scorecard for/
         .test(grid.text))
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- a grid with nothing to reconcile says nothing --')
  {
    const clean = { rows: TEAM_BREAKDOWN.rows.slice(0, 2), season_rows: [],
                    unattributed: 0 }
    const stats = JSON.parse(JSON.stringify(GRID))
    // Header and grid agree: 8 held, 8 on rows, so no note anywhere.
    stats.career_batting = career(8)
    delete stats.match_coverage
    const { page, ctx, errors } = await open(stats, { team: clean })
    await page.click('text=Analysis').catch(() => {})
    await page.waitForTimeout(400)
    await page.click('text=Team').catch(() => {})
    await page.waitForSelector('text=MATCHES BY GRADE', { timeout: 10000 })
      .catch(() => {})
    const text = await page.evaluate(() => {
      const card = [...document.querySelectorAll('.pb-card')]
        .find(e => /MATCHES BY GRADE/.test(e.innerText || ''))
      return card ? (card.innerText || '').replace(/\s+/g, ' ').trim() : null
    })
    ck('the grid still draws', !!text && /TOTAL 8\b/.test(text), text?.slice(0, 200))
    ck('NO reconciliation note where the rows already add up — the same rule '
       + 'the header note keeps', !!text && !/whichever is higher/.test(text),
       text?.slice(0, 300))
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- the club default is already a filter --')
  {
    const { page, ctx, errors } = await open(DEFAULTED)
    const tile = await readTile(page)
    ck('the headline is the filtered figure, neither of the career numbers',
       tile?.figure === '11', tile?.figure)
    ck('THE NOTE NEVER CLAIMS ITS FIGURES ARE THE HEADLINE — it names both '
       + 'career sources instead, so nothing on screen contradicts anything else',
       !!tile && /counted from the 14 matches we hold a scorecard for, not the 9/
         .test(tile.text), tile?.text)
    ck('and it does not print "11" as if it were one of them',
       !!tile && !/\b11\b/.test(tile.text.replace(/^MATCHES\s*11/, '')),
       tile?.text)
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- THE CLUB DEFAULT IS NOT A PICK: nothing extra is said --')
  {
    const { page, ctx, errors } = await open(DEFAULTED, { team: TEAM_BREAKDOWN })
    // The header already says the default once. Six more lines about a
    // filter nobody turned on would be noise on every visit to a club with a
    // junior programme.
    ck('no tab is marked while nothing has been picked',
       (await dotCount(page)) === 0, String(await dotCount(page)))
    await page.click('text=Analysis').catch(() => {})
    await page.waitForTimeout(300)
    await page.click('text=COMPETITIONS').catch(() => {})
    await page.waitForTimeout(400)
    const text = await bodyText(page)
    ck('and the Competitions panel carries no reach note under the default',
       !/whatever is picked above/.test(text) && !/does not narrow/.test(text),
       text.slice(0, 200))
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- PICK A PILL, and the page says where it reached --')
  {
    const { page, ctx, errors, wire } = await open(DEFAULTED, { team: TEAM_BREAKDOWN })
    await page.getByRole('button', { name: 'Juniors', exact: true }).click({ timeout: 3000 })
      .catch(() => {})
    await page.waitForTimeout(800)
    ck('the two whole-career tabs are marked on the main bar, before opening them',
       (await dotCount(page)) >= 2, String(await dotCount(page)))
    await page.click('text=Analysis').catch(() => {})
    await page.waitForTimeout(400)
    ck('and the two enumerations are marked on the Analysis bar',
       (await dotCount(page)) >= 4, String(await dotCount(page)))
    await page.click('text=COMPETITIONS').catch(() => {})
    await page.waitForTimeout(400)
    let text = await bodyText(page)
    ck('COMPETITIONS names the pick that did not reach it — Grade type, and only '
       + 'Grade type, since nothing else was touched',
       /Shows every competition, whatever is picked above/.test(text)
       && /the Grade type filter does not narrow it/.test(text)
       && !/Match type/.test(text.slice(text.indexOf('Shows every competition'))),
       text.slice(0, 300))
    await page.click('text=FORMATS').catch(() => {})
    await page.waitForTimeout(400)
    text = await bodyText(page)
    ck('FORMATS likewise', /Shows every format, whatever is picked above/.test(text))
    await page.click('text=TEAMMATES').catch(() => {})
    await page.waitForTimeout(600)
    text = await bodyText(page)
    ck('TEAMMATES carries NO note — it takes the filter now',
       !/does not narrow/.test(text) && !/whatever is picked/.test(text),
       text.slice(0, 200))
    ck('and the pick is on the wire to it',
       wire.some(q => /categories=junior/.test(q)), JSON.stringify(wire))
    await page.click('text=MILESTONES').catch(() => {})
    await page.waitForTimeout(500)
    text = await bodyText(page)
    ck('MILESTONES says it is whole-career and names the pick it ignores',
       /Counted across the whole career\. The Grade type filter above does not change this\./
         .test(text), text.slice(0, 300))
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- the grid says which seasons were left to the scorecards --')
  {
    const team = JSON.parse(JSON.stringify(TEAM_BREAKDOWN))
    team.scope = { active: true, aggregate_excluded: false, seasons_left_to_scorecards: 2 }
    const { page, ctx, errors } = await open(DEFAULTED, { team })
    await page.click('text=Analysis').catch(() => {})
    await page.waitForTimeout(400)
    await page.click('text=Team').catch(() => {})
    await page.waitForSelector('text=MATCHES BY GRADE', { timeout: 10000 }).catch(() => {})
    const text = await bodyText(page)
    ck('the per-season gate is stated with its count',
       /only used for a season in which every match was inside this filter\. 2 seasons were left to the scorecards alone\./
         .test(text), text.slice(text.indexOf('MATCHES BY GRADE'), text.indexOf('MATCHES BY GRADE') + 900))
    ck('and the subtitle no longer claims "every grade"',
       /Every grade in the current filter/.test(text))
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }

  console.log('\n-- narrow --')
  {
    const { page, ctx, errors } = await open(SURPLUS, { width: 390 })
    const over = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth)
    ck('no horizontal overflow at 390px', over <= 0, `over by ${over}px`)
    const tile = await readTile(page)
    ck('and the note is still there', !!tile && /337/.test(tile.text))
    ck('no page errors', errors.length === 0, errors.join(' | '))
    await ctx.close()
  }
} finally {
  await browser.close()
}

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
