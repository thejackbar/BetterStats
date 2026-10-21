// Drives the REAL voting page (/vote/:token) and availability page (/avail/:token)
// in Chromium with the API stubbed at the network layer:
//   * a verified voter sees a "My page" link in the header and "Go to my page" once
//     their votes are in; it points at /avail/<token>?tab=mine&player=<id>
//   * a visitor who has not said who they are sees neither
//   * the availability page opens on My page for that link when already signed in
//   * with no session it picks the player for them and asks only for the PIN
//   * with no query nothing changes: it opens on Availability and asks who you are
//   * 390px: no sideways overflow
//
//   npx vite preview --port 5199 &    node verify_vote_my_page_link_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const iso = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
const CLUB = { name: 'Gisborne CC', logo_url: null, accent_color: null, primary_color: null }
const MY = '/avail/atok?tab=mine&player=p1'

const voteStubs = async (page, me) => {
  await page.route('**/api/**', (r) => json(r, {}))
  await page.route(/\/api\/public\/votes\/vtok(\?.*)?$/, (r) => json(r, {
    club: CLUB, medal: { id: 'm1', name: 'Best player' }, require_pin: true, voter_mode: 'players', allow_non_participants: false,
    allow_self_vote: false, ballot_values: [3, 2, 1], me, players: [{ id: 'p1', display_name: 'Sam Sledge', has_phone: true }],
    grades: [], rounds: [], fixtures: [{ id: 'f1', opponent: 'Rovers', round: 'Round 1', round_key: '1', date: iso(-2), home_away: 'HOME', state: 'open' }],
  }))
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })

  await safe('voting header', async () => {
    console.log('\n── The voting page ──')
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 }, isMobile: true, hasTouch: true })
    const page = await ctx.newPage(); page.setDefaultTimeout(8000)
    await voteStubs(page, { id: 'p1', display_name: 'Sam Sledge', my_page: MY })
    await page.goto(`${BASE}/vote/vtok`)
    const link = page.locator('[data-my-page-link]')
    await link.waitFor()
    check('a verified voter sees My page in the header', /My page/.test(await link.innerText()))
    check('it points at their own page, opened on My page', (await link.getAttribute('href')) === MY, await link.getAttribute('href'))
    check('"Not you?" is still there', (await page.getByText('Not you?').count()) === 1)
    check('390px: no sideways overflow', (await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0)
    await ctx.close()
  })

  await safe('voting no link', async () => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 } })
    const page = await ctx.newPage(); page.setDefaultTimeout(8000)
    await voteStubs(page, null)
    await page.goto(`${BASE}/vote/vtok`)
    await page.getByText('Rovers').waitFor()
    check('a visitor who has not said who they are has no My page link', (await page.locator('[data-my-page-link]').count()) === 0)
    await ctx.close()
    const ctx2 = await browser.newContext({ viewport: { width: 390, height: 900 } })
    const p2 = await ctx2.newPage(); p2.setDefaultTimeout(8000)
    await voteStubs(p2, { id: 'p1', display_name: 'Sam Sledge' })
    await p2.goto(`${BASE}/vote/vtok`)
    await p2.getByText('Rovers').waitFor()
    check('and a club with its player link off sends none', (await p2.locator('[data-my-page-link]').count()) === 0)
    await ctx2.close()
  })

  await safe('after voting', async () => {
    console.log('\n── After the votes are in ──')
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 } })
    const page = await ctx.newPage(); page.setDefaultTimeout(8000)
    const me = { id: 'p1', display_name: 'Sam Sledge', my_page: MY }
    await voteStubs(page, me)
    await page.route(/\/api\/public\/votes\/vtok\/fixtures\/f1$/, (r) => json(r, {
      club: CLUB, fixture: { id: 'f1', opponent: 'Rovers', round: 'Round 1', date: iso(-2), state: 'open' }, ballot_values: [3, 2, 1],
      allow_self_vote: false, voter_mode: 'players', me, role: 'player', reason: null, my_ballot: null,
      players: [{ id: 'a', name: 'Ann Anchor' }, { id: 'b', name: 'Bob Rival' }, { id: 'c', name: 'Cal Cover' }],
    }))
    await page.route(/\/api\/public\/votes\/vtok\/fixtures\/f1\/ballot$/, (r) => json(r, { status: 'ok' }))
    await page.goto(`${BASE}/vote/vtok?fixture=f1`)
    for (const n of ['Ann Anchor', 'Bob Rival', 'Cal Cover']) await page.getByRole('button', { name: new RegExp(n) }).first().click()
    await page.getByRole('button', { name: /submit|send|cast/i }).first().click()
    await page.locator('[data-my-page-done]').waitFor()
    check('"Go to my page" is offered on the thank-you screen', (await page.locator('[data-my-page-done]').getAttribute('href')) === MY)
    await ctx.close()
  })

  await safe('photos', async () => {
    console.log('\n── Player photos on the ballot ──')
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 }, isMobile: true, hasTouch: true })
    const page = await ctx.newPage(); page.setDefaultTimeout(8000)
    const me = { id: 'p1', display_name: 'Sam Sledge' }
    await voteStubs(page, me)
    const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')
    await page.route('https://img.test/**', (r) => (r.request().url().endsWith('good.png')
      ? r.fulfill({ status: 200, contentType: 'image/png', body: PNG })
      : r.fulfill({ status: 404, body: 'nope' })))
    await page.route(/\/api\/public\/votes\/vtok\/fixtures\/f1$/, (r) => json(r, {
      club: CLUB, fixture: { id: 'f1', opponent: 'Rovers', round: 'Round 1', date: iso(-2), state: 'open' }, ballot_values: [3, 2, 1],
      allow_self_vote: false, voter_mode: 'players', me, role: 'player', reason: null, my_ballot: null,
      players: [{ id: 'a', name: 'Ann Anchor', photo_url: 'https://img.test/good.png' }, { id: 'b', name: 'Bob Broken', photo_url: 'https://img.test/missing.png' }, { id: 'c', name: 'Cal Cover', photo_url: null }],
    }))
    await page.goto(`${BASE}/vote/vtok?fixture=f1`)
    await page.getByRole('button', { name: /Ann Anchor/ }).waitFor()
    await page.waitForTimeout(600)
    const row = (n) => page.getByRole('button', { name: new RegExp(n) }).first()
    check('a player with a photo shows it, not initials', (await row('Ann Anchor').locator('[data-face="photo"]').count()) === 1 && (await row('Ann Anchor').locator('[data-face="initials"]').count()) === 0)
    check('a photo that will not load falls back to initials', (await row('Bob Broken').locator('[data-face="initials"]').count()) === 1)
    check('a player with no photo shows initials', (await row('Cal Cover').locator('[data-face="initials"]').innerText()) === 'CC')
    check('the photo is a round 40px face', await row('Ann Anchor').locator('[data-face="photo"]').evaluate((e) => e.getBoundingClientRect().width === 40 && getComputedStyle(e).borderRadius.includes('9999') || getComputedStyle(e).borderRadius === '50%'))
    check('390px: no sideways overflow', (await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0)
    await page.screenshot({ path: `${process.env.SHOT_DIR || '/tmp'}/vote-photos-390.png` })
    await ctx.close()
  })

  await safe('vote page autopick', async () => {
    console.log('\n── The vote page from a reminder ──')
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 }, isMobile: true, hasTouch: true })
    const page = await ctx.newPage(); page.setDefaultTimeout(8000)
    await voteStubs(page, null)
    await page.route(/\/api\/public\/votes\/vtok\/fixtures\/f1$/, (r) => json(r, {
      club: CLUB, fixture: { id: 'f1', opponent: 'Rovers', round: 'Round 1', date: iso(-2), state: 'open' }, ballot_values: [3, 2, 1],
      allow_self_vote: false, voter_mode: 'players', me: null, role: 'none', reason: 'verify_required', my_ballot: null, players: [],
    }))
    await page.goto(`${BASE}/vote/vtok?fixture=f1&player=p1`)
    await page.getByText('Last 4 digits of your mobile').waitFor()
    check('from the reminder the player is already picked, only the PIN is asked', /Sam Sledge/.test(await page.locator('body').innerText()))
    await page.getByText('Not you? Pick a different name').click()
    await page.waitForTimeout(400)
    check('"Not you?" goes back to the names and stays there', (await page.getByText('Last 4 digits of your mobile').count()) === 0)
    await ctx.close()
    const ctx2 = await browser.newContext({ viewport: { width: 390, height: 900 } })
    const p2 = await ctx2.newPage(); p2.setDefaultTimeout(8000)
    await voteStubs(p2, null)
    await p2.route(/\/api\/public\/votes\/vtok\/fixtures\/f1$/, (r) => json(r, {
      club: CLUB, fixture: { id: 'f1', opponent: 'Rovers', round: 'Round 1', date: iso(-2), state: 'open' }, ballot_values: [3, 2, 1],
      allow_self_vote: false, voter_mode: 'players', me: null, role: 'none', reason: 'verify_required', my_ballot: null, players: [],
    }))
    await p2.goto(`${BASE}/vote/vtok?fixture=f1`)
    await p2.getByPlaceholder('Search your name…').waitFor().catch(() => {})
    check('without ?player the player is not guessed', (await p2.getByText('Last 4 digits of your mobile').count()) === 0)
    await ctx2.close()
  })

  const availStubs = async (page, { verified }) => {
    await page.route('**/api/**', (r) => json(r, {}))
    const me = {
      club: CLUB, player: { id: 'p1', display_name: 'Sam Sledge' }, has_squad: true, squads: [],
      dates: [{ date: iso(5), fixtures: [{ id: 'f1', opponent_name: 'Rovers', home_away: 'HOME', role: 'single', start_time: '13:00', team_name: '1st XI', mine: true }] }], availability: {},
    }
    await page.route(/\/api\/public\/availability\/atok\/me\/profile(\?.*)?$/, (r) => json(r, { club: CLUB, player: me.player, squads: [], squads_visible: false, selected: [], training: { upcoming: [], attended_8_weeks: 0, last_attended: null }, modules: ['availability', 'training'] }))
    await page.route(/\/api\/public\/availability\/atok\/me(\?.*)?$/, (r) => (verified ? json(r, me) : json(r, { detail: 'Not verified' }, 401)))
    await page.route(/\/api\/public\/availability\/atok$/, (r) => json(r, { club: CLUB, require_pin: true, players: [{ id: 'p0', display_name: 'Ann Anchor', has_phone: true }, { id: 'p1', display_name: 'Sam Sledge', has_phone: true }] }))
  }

  await safe('avail signed in', async () => {
    console.log('\n── The player\'s page from the link ──')
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 } })
    const page = await ctx.newPage(); page.setDefaultTimeout(8000)
    await availStubs(page, { verified: true })
    await page.goto(`${BASE}${MY}`)
    await page.locator('[data-my-page]').waitFor()
    check('already signed in: it opens on the player\'s page, whatever ?tab says', (await page.locator('[data-hero]').count()) === 1)
    await ctx.close()
  })

  await safe('avail not signed in', async () => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 } })
    const page = await ctx.newPage(); page.setDefaultTimeout(8000)
    await availStubs(page, { verified: false })
    await page.goto(`${BASE}${MY}`)
    await page.getByText('Last 4 digits of your mobile').waitFor()
    check('not signed in: the player is already picked, only the PIN is asked', /Sam Sledge/.test(await page.locator('body').innerText()))
    check('...and the other player is not', !/Ann Anchor/.test(await page.locator('body').innerText()))
    // Not you? goes back to the name list and does not pick them again.
    await page.getByText('Not you? Pick a different name').click()
    await page.waitForTimeout(400)
    check('"Not you?" returns to the name list and stays there', (await page.getByPlaceholder('Search your name…').count()) === 1)
    await ctx.close()
  })

  await safe('avail plain link', async () => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 } })
    const page = await ctx.newPage(); page.setDefaultTimeout(8000)
    await availStubs(page, { verified: false })
    await page.goto(`${BASE}/avail/atok`)
    await page.getByPlaceholder('Search your name…').waitFor()
    check('a plain link still asks who you are', true)
    await ctx.close()
    const ctx2 = await browser.newContext({ viewport: { width: 390, height: 900 } })
    const p2 = await ctx2.newPage(); p2.setDefaultTimeout(8000)
    await availStubs(p2, { verified: true })
    await p2.goto(`${BASE}/avail/atok`)
    await p2.locator('[data-hero]').waitFor()
    check('and a plain link opens the same page, availability editor included', (await p2.locator('[data-availability]').count()) === 1)
    await ctx2.close()
  })

  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run().catch((e) => { console.error(e); process.exit(1) })
