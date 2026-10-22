// Drives the real player page (/avail/:token) in Chromium with the API stubbed at the
// network layer: one dashboard with the photo, the season panels, the availability
// editor and the Fantasy card.
//   * photo and shirt number show; a missing or broken photo falls back to initials
//   * a tap on Available sends exactly one POST /me with the date and status, from
//     the dashboard itself (no tab to switch to)
//   * the season dashboard draws batting, bowling, fielding and the last innings;
//     a partial rate carries a dagger
//   * the Fantasy card shows the next lock, the team's rank and points, and links to
//     the club's fantasy page; with no team it still shows the deadline and link
//   * no picks / captain text anywhere on the card
//   * sections (Selection, Club admin, Voting, Stats, Fantasy) with a one-line summary each
//   * a section minimises and maximises, the choice is remembered, and a blocked
//     localStorage does not break the page
//   * fees paid are listed, five at a time
//   * 390px and 1280px: no sideways overflow
//
//   npx vite preview --port 5199 &    node verify_player_page_dashboard_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOT = process.env.SHOT_DIR || '/tmp'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }
const iso = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const inHours = (h) => new Date(Date.now() + h * 3600e3).toISOString()

const state = { photo: '/photo-ok.svg', team: true, fantasy: true }
const PAYMENTS = Array.from({ length: 7 }, (_, i) => ({ date: iso(-10 - i * 20), amount: 40 + i, kind: i % 2 ? 'Match fees' : 'Membership', method: 'Cash', season: 'Summer 26/27' }))
const player = () => ({ id: 'p1', display_name: 'Sam Sledge', photo_url: state.photo, shirt_number: '7', profile_path: '/players/p1' })
const me = () => ({
  club: { name: 'Dash CC', logo_url: null, accent_color: null, primary_color: null },
  player: player(), has_squad: true, squads: ['1sts'], allow_maybe: true, week_names: {},
  dates: [
    { date: iso(5), fixtures: [{ id: 'f1', opponent_name: 'Rovers', home_away: 'HOME', role: 'single', start_time: '13:00', venue: 'Main Oval', team_name: '1sts', mine: true }] },
    { date: iso(12), fixtures: [{ id: 'f2', opponent_name: 'Saints', home_away: 'AWAY', role: 'single', start_time: '13:00', venue: 'Saints Park', team_name: '1sts', mine: true }] },
  ],
  availability: {},
})
const profile = () => ({
  club: {}, player: player(), squads: ['1sts'], squads_visible: true,
  modules: state.fantasy ? ['fantasy', 'season', 'squad', 'fees', 'votes'] : ['season', 'squad', 'fees', 'votes'],
  fees: { on_record: true, season: 'Summer 26/27', total_outstanding: 60, membership_outstanding: 60, match_fee_outstanding: 0, total_paid: 40, credit: 0, payments: PAYMENTS },
  votes: [{ medal: 'Dunslow Medal', fixture_id: 'f1', opponent: 'Rovers', round: 'Round 1', date: iso(-2), closes_on: iso(5), link: '/vote/vtok?fixture=f1&player=p1' }],
  selected: [], training: { upcoming: [], attended_8_weeks: 0, last_attended: null }, votes_cast: [], fines: [],
  season: {
    season: 'Summer 26/27', matches: 11, runs: 412, high_score: 87, batting_average: 51.5, wickets: 9, best_bowling: '4-22', catches: 6, auto_shown: false,
    batting: { innings: 10, not_outs: 2, strike_rate: 84.2, strike_rate_partial: true, fifties: 3, hundreds: 1, ducks: 1, fours: 40, sixes: 6 },
    bowling: { overs: 48, maidens: 4, runs_conceded: 240, average: 26.67, economy: 5.0, economy_partial: false, five_fors: 0 },
    fielding: { catches: 6, run_outs: 2, stumpings: 0 },
    form: { batting: [{ runs: 8, not_out: false, balls: 12, date: iso(-5) }, { runs: 71, not_out: true, balls: 60, date: iso(-10) }, { runs: 0, not_out: false, balls: 3, date: iso(-15) }],
      bowling: [{ wickets: 3, runs: 21, overs: 8, date: iso(-5) }, { wickets: 0, runs: 30, overs: 6, date: iso(-10) }] },
  },
  fantasy: state.fantasy ? {
    link: '/fantasy/ftok', name: 'Dash Fantasy', season: { name: '2026 Fantasy', status: 'active', registration_open: true },
    deadlines: [{ number: 3, name: 'Round 3', lock_at: inHours(50), locked: false }, { number: 4, name: 'Round 4', lock_at: inHours(220), locked: false }],
    team: state.team ? { built: true, team_name: 'Sledgehammers', points: 123, rank: 2, of: 14, last_round: { number: 2, points: 61 }, this_round_points: null, free_transfers: 2 } : null,
    as_player: { points: 84, last_round_points: 31, price: 9.5, price_change: 0.5, owned_count: 4 },
  } : null,
})

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const errors = []
  const posts = []
  const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const open = async (width, blockStorage = false) => {
    const ctx = await browser.newContext({ viewport: { width, height: 900 } })
    const page = await ctx.newPage()
    page.setDefaultTimeout(6000)
    // Reads and writes of this page's own key fail (a full or locked-down store); the rest of the app is left alone.
    if (blockStorage) await page.addInitScript(() => {
      for (const m of ['getItem', 'setItem']) {
        const orig = Storage.prototype[m]
        Storage.prototype[m] = function (k, ...a) { if (String(k).startsWith('bs.playerpage')) throw new DOMException('blocked', 'SecurityError'); return orig.call(this, k, ...a) }
      }
    })
    page.on('pageerror', (e) => errors.push(e.message))
    await page.route('**/photo-ok.svg', (r) => r.fulfill({ status: 200, contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="red"/></svg>' }))
    await page.route('**/photo-bad.png', (r) => r.fulfill({ status: 404, body: '' }))
    await page.route('**/api/**', (r) => json(r, {}))
    await page.route(/\/api\/public\/availability\/tok\/me\/profile(\?.*)?$/, (r) => json(r, profile()))
    await page.route(/\/api\/public\/availability\/tok\/me(\?.*)?$/, (r) => {
      if (r.request().method() === 'POST') { posts.push(JSON.parse(r.request().postData())); return json(r, { status: 'ok' }) }
      return json(r, me())
    })
    await page.route(/\/api\/public\/availability\/tok$/, (r) => json(r, { club: me().club, require_pin: true, players: [{ id: 'p1', display_name: 'Sam Sledge', has_phone: true }] }))
    await page.goto(`${BASE}/avail/tok`)
    await page.locator('[data-hero]').waitFor({ timeout: 20000 })
    await page.locator('[data-groups]').waitFor()
    await page.locator('[data-vote-due]').waitFor()
    return { ctx, page }
  }
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)

  await safe('hero', async () => {
    console.log('\n── The player, not just a form ──')
    const { ctx, page } = await open(390)
    check('the photo is drawn', (await page.locator('[data-hero-photo]').count()) === 1)
    check('the shirt number is on it', /#7/.test(await page.locator('[data-shirt]').innerText()))
    check('the name and squad are shown', /Sam Sledge/.test(await page.locator('[data-hero-name]').innerText()) && /1sts/.test(await page.locator('[data-my-squads]').innerText()))
    check('it links to the public profile', (await page.locator('[data-profile-link]').getAttribute('href')) === '/players/p1')
    check('there is no tab switch', (await page.locator('[role=tablist]').count()) === 0)
    await ctx.close()
    state.photo = '/photo-bad.png'
    const bad = await open(390)
    await bad.page.locator('[data-hero-initials]').waitFor()
    check('a photo that will not load falls back to initials', /SS/.test(await bad.page.locator('[data-hero-initials]').innerText()))
    await bad.ctx.close()
    state.photo = null
    const none = await open(390)
    check('no photo at all gives initials', (await none.page.locator('[data-hero-initials]').count()) === 1 && (await none.page.locator('[data-hero-photo]').count()) === 0)
    await none.ctx.close()
    state.photo = '/photo-ok.svg'
  })

  await safe('availability', async () => {
    console.log('\n── Answer without leaving ──')
    const { ctx, page } = await open(390)
    check('the editor is on the page, before the cards', (await page.locator('[data-availability]').count()) === 1)
    check('the Selection header says what is waiting', /1 to answer/.test(await page.locator('[data-group="selection"] [data-group-summary]').innerText()))
    posts.length = 0
    await page.locator(`[data-date-card="${iso(5)}"] button`, { hasText: /^\S+\s+Available$/ }).click()
    await page.waitForTimeout(400)
    check('one tap sends one write with the date and status', posts.length === 1 && posts[0].date === iso(5) && posts[0].status === 'AVAILABLE', JSON.stringify(posts))
    check('after the tap the Selection header', /All answered/.test(await page.locator('[data-group="selection"] [data-group-summary]').innerText()))
    await ctx.close()
  })

  await safe('season', async () => {
    console.log('\n── Season dashboard ──')
    const { ctx, page } = await open(390)
    for (const id of ['batting', 'bowling', 'fielding', 'form-batting', 'form-bowling']) {
      check(`${id} panel is there`, (await page.locator(`[data-season-panel="${id}"]`).count()) === 1)
    }
    const bat = await page.locator('[data-season-panel="batting"]').innerText()
    check('batting shows runs, average and high score', /412/.test(bat) && /51\.5/.test(bat) && /87/.test(bat), bat)
    check('the partial strike rate carries a dagger', /84\.2†/.test(bat), bat)
    const bowl = await page.locator('[data-season-panel="bowling"]').innerText()
    check('the full economy does not', /5/.test(bowl) && !/†/.test(bowl), bowl)
    const form = await page.locator('[data-form-batting]').innerText()
    check('the last innings read oldest to newest, with a star for not out', form.replace(/\s+/g, ' ').trim() === '0 71* 8', form)
    check('the full stats link goes to the profile', (await page.locator('a', { hasText: 'Full stats' }).getAttribute('href')) === '/players/p1')
    await ctx.close()
  })

  await safe('fantasy', async () => {
    console.log('\n── Fantasy ──')
    const { ctx, page } = await open(390)
    const card = await page.locator('[data-fantasy]').innerText()
    check('the next lock is named, with a countdown', /Round 3 locks/.test(card) && /in 2 days/.test(card), card)
    check('a later deadline is listed', /Round 4/.test(card), card)
    check('team name, rank and points', /Sledgehammers/.test(card) && /2nd/.test(card) && /rank of 14/i.test(card) && /123/.test(card), card)
    check('last round points', /round 2/i.test(card) && /61/.test(card), card)
    check('how the player is doing as a pick', /84 points/.test(card) && /\$9\.5/.test(card), card)
    check('it links to the club fantasy page', (await page.locator('[data-fantasy-link]').getAttribute('href')) === '/fantasy/ftok')
    check('it names no picks or captain', !/captain|vice|transfer in|lineup/i.test(card), card)
    const fsum = await page.locator('[data-group="fantasy"] [data-group-summary]').innerText()
    check('the Fantasy header says when it locks and where you sit', /Locks/.test(fsum) && /2nd/.test(fsum), fsum)
    check('the Fantasy section is titled with the club\'s own name for it', /Dash Fantasy/.test(await page.locator('[data-group-toggle="fantasy"]').innerText()))
    await ctx.close()
    state.team = false
    const nt = await open(390)
    const c2 = await nt.page.locator('[data-fantasy]').innerText()
    check('with no team found it still has the deadline and the link', /Round 3 locks/.test(c2) && (await nt.page.locator('[data-fantasy-link]').count()) === 1, c2)
    check('and says where to see the team', (await nt.page.locator('[data-fantasy-no-team]').count()) === 1)
    await nt.ctx.close()
    state.team = true
    state.fantasy = false
    const off = await open(390)
    check('a club without Fantasy has no card and no section', (await off.page.locator('[data-fantasy]').count()) === 0 && (await off.page.locator('[data-group="fantasy"]').count()) === 0)
    await off.ctx.close()
    state.fantasy = true
  })

  await safe('sections', async () => {
    console.log('\n── Sections ──')
    const { ctx, page } = await open(390)
    const ids = await page.evaluate(() => [...document.querySelectorAll('[data-groups] > [data-group]')].map((e) => e.getAttribute('data-group')))
    check('Selection, Club admin, Voting, Stats, Fantasy, in that order', JSON.stringify(ids) === JSON.stringify(['selection', 'admin', 'voting', 'stats', 'fantasy']), JSON.stringify(ids))
    check('each module is in its own section', (await page.locator('[data-group="selection"] [data-availability]').count()) === 1
      && (await page.locator('[data-group="admin"] [data-fee-payments]').count()) === 1
      && (await page.locator('[data-group="voting"] [data-vote-due]').count()) === 1
      && (await page.locator('[data-group="stats"] [data-season-panel="batting"]').count()) === 1
      && (await page.locator('[data-group="fantasy"] [data-fantasy]').count()) === 1)
    check('Club admin says what is owing', /\$60\.00 owing/.test(await page.locator('[data-group="admin"] [data-group-summary]').innerText()))
    check('Voting says a vote is due', /1 vote to cast/.test(await page.locator('[data-group="voting"] [data-group-summary]').innerText()))
    check('Stats says the season in a line', /11 matches · 412 runs · 9 wkts/.test(await page.locator('[data-group="stats"] [data-group-summary]').innerText()))
    // minimise and maximise
    const toggle = page.locator('[data-group-toggle="stats"]')
    check('open to begin with', (await toggle.getAttribute('aria-expanded')) === 'true' && await page.locator('[data-season-panel="batting"]').isVisible())
    await toggle.click()
    check('a tap minimises it', (await toggle.getAttribute('aria-expanded')) === 'false' && !(await page.locator('[data-season-panel="batting"]').isVisible()))
    check('its one-line summary stays on the closed header', await page.locator('[data-group="stats"] [data-group-summary]').isVisible())
    await page.reload(); await page.locator('[data-groups]').waitFor()
    check('the choice is remembered after a reload', (await page.locator('[data-group-toggle="stats"]').getAttribute('aria-expanded')) === 'false')
    check('other sections are untouched', (await page.locator('[data-group-toggle="selection"]').getAttribute('aria-expanded')) === 'true')
    await page.locator('[data-group-toggle="stats"]').click()
    check('and it opens again', await page.locator('[data-season-panel="batting"]').isVisible())
    await page.locator('[data-toggle-all]').click()
    const states = await page.evaluate(() => [...document.querySelectorAll('[data-group]')].map((e) => e.getAttribute('data-open')))
    check('Collapse all closes every section', states.every((x) => x === 'no') && /Expand all/.test(await page.locator('[data-toggle-all]').innerText()), JSON.stringify(states))
    check('a closed Selection still shows its summary', (await page.locator('[data-group="selection"] [data-group-summary]').innerText()).length > 0)
    await page.locator('[data-toggle-all]').click()
    check('Expand all opens them again', (await page.locator('[data-group][data-open="yes"]').count()) === 5)
    // closing keeps the answer editor mounted: the open list of weeks survives
    await page.locator('[data-see-more]').click()
    const cardsBefore = await page.locator('[data-date-card]').count()
    await page.locator('[data-group-toggle="selection"]').click()
    await page.locator('[data-group-toggle="selection"]').click()
    check('closing and reopening Selection keeps the weeks you had opened', (await page.locator('[data-date-card]').count()) === cardsBefore && cardsBefore === 2, String(cardsBefore))
    await ctx.close()
    const blocked = await open(390, true)
    check('with the page storage blocked it still draws, all open', (await blocked.page.locator('[data-group][data-open="yes"]').count()) === 5)
    await blocked.page.locator('[data-group-toggle="stats"]').click()
    check('and sections still minimise for the visit', (await blocked.page.locator('[data-group-toggle="stats"]').getAttribute('aria-expanded')) === 'false')
    await blocked.ctx.close()
  })

  await safe('fees paid', async () => {
    console.log('\n── Fees paid ──')
    const { ctx, page } = await open(390)
    const rows = await page.locator('[data-fee-payment]').evaluateAll((els) => els.map((e) => e.textContent.replace(/\s+/g, ' ').trim()))
    check('five payments show first, with kind, method and amount (one season, so it is not repeated)', rows.length === 5 && /Membership · Cash/.test(rows[0]) && !/Summer/.test(rows[0]) && /\$40\.00/.test(rows[0]), JSON.stringify(rows.slice(0, 2)))
    check('the rest open on a tap', /Show all 7 payments/.test(await page.locator('[data-fee-payments-more]').innerText()))
    await page.locator('[data-fee-payments-more]').click()
    check('all seven are listed', (await page.locator('[data-fee-payment]').count()) === 7)
    check('and can be folded away again', /Show fewer/.test(await page.locator('[data-fee-payments-more]').innerText()))
    check('what is owing is still stated first', /You owe\s*\$60\.00/.test((await page.locator('[data-group="admin"]').innerText()).replace(/\s+/g, ' ')))
    await ctx.close()
  })

  await safe('layout', async () => {
    console.log('\n── Layout ──')
    const wide = await open(1280)
    const sel = await wide.page.locator('[data-group="selection"]').boundingBox()
    const stats = await wide.page.locator('[data-group="stats"]').boundingBox()
    check('wide: Selection is the left column, the rest sit to its right', sel.x + sel.width <= stats.x + 1, JSON.stringify([sel, stats]))
    check('1280px: no sideways overflow', (await overflow(wide.page)) <= 0, String(await overflow(wide.page)))
    await wide.page.screenshot({ path: `${SHOT}/player-page-1280.png`, fullPage: true })
    await wide.ctx.close()
    const phone = await open(390)
    check('390px: no sideways overflow', (await overflow(phone.page)) <= 0, String(await overflow(phone.page)))
    const order = await phone.page.evaluate(() => ['[data-hero]', '[data-group="selection"]', '[data-group="stats"]'].map((s) => document.querySelector(s).getBoundingClientRect().top))
    check('on a phone: who you are, then Selection, then the rest', order[0] < order[1] && order[1] < order[2], JSON.stringify(order))
    await phone.page.screenshot({ path: `${SHOT}/player-page-390.png`, fullPage: true })
    await phone.ctx.close()
  })

  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
