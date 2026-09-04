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

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(stats, { width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = []
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
  return { page, ctx, errors }
}

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
