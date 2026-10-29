// Drives the player page's login in Chromium with the API stubbed at the network layer.
// A player who typed their own mobile and was refused had usually tapped someone
// else's name, so the screen has to say who they are logging in as.
//   * the PIN step names the player in a card, in the label and on the button
//   * "This isn't me" is a real button that goes back to the names
//   * a wrong PIN repeats whose mobile was wanted, and sends the exact request
//   * the plain club link picks nobody; a link carrying ?player= picks that player once, then
//     the address bar is the plain link again, so copying it never hands the next person a name
//   * 390px: no sideways overflow
//
//   npx vite preview --port 5199 &    node verify_player_login_identity_browser.mjs
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const SHOT = process.env.SHOT_DIR || '/tmp'
let PASS = 0, FAIL = 0
const check = (label, cond, detail = '') => {
  if (cond) { PASS++; console.log(`  ok   ${label}`) } else { FAIL++; console.log(`  FAIL ${label}  ${detail}`) }
}
const safe = async (label, fn) => { try { await fn() } catch (e) { check(`${label}: step could not run`, false, String(e.message).split('\n')[0]) } }
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const CLUB = { id: 'o1', slug: 'dash', name: 'Dash Cricket Club', short_name: 'DCC' }

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined })
  await safe('login', async () => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 800 }, isMobile: true, hasTouch: true })
    const page = await ctx.newPage(); page.setDefaultTimeout(8000)
    const verifies = []
    await page.route('**/api/**', (r) => json(r, {}))
    await page.route(/\/api\/public\/availability\/tok$/, (r) => json(r, { club: CLUB, require_pin: true, players: [
      { id: 'p0', display_name: 'Ann Anchor', has_phone: true }, { id: 'p1', display_name: 'Sam Sledge', has_phone: true }, { id: 'p2', display_name: 'No Phone', has_phone: false }] }))
    await page.route(/\/api\/public\/availability\/tok\/me(\?.*)?$/, (r) => json(r, { detail: 'Not verified' }, 401))
    await page.route(/\/api\/public\/availability\/tok\/verify$/, (r) => { verifies.push(r.request().postDataJSON()); return json(r, { detail: 'That PIN didn\'t match. Try the last 4 digits of your mobile.' }, 401) })
    await page.goto(`${BASE}/avail/tok`)
    await page.getByPlaceholder('Search your name…').waitFor()
    check('names step tells them to tap their own name', (await page.getByText('Who are you?').count()) === 1)

    await page.getByText('Sam Sledge').click()
    const card = page.locator('[data-signing-in-as]')
    await card.waitFor()
    check('the card says they are logging in as someone', /logging in as/i.test(await card.innerText()))
    check('the card names the player', (await page.locator('[data-signing-in-name]').innerText()) === 'Sam Sledge')
    check('the label names whose mobile', /last 4 digits of Sam Sledge’s mobile/i.test(await page.locator('label').innerText()))
    check('the button names the player', (await page.getByRole('button', { name: 'Log in as Sam Sledge' }).count()) === 1)
    const nameBox = await page.locator('[data-signing-in-name]').evaluate((e) => parseFloat(getComputedStyle(e).fontSize))
    check('the name is the largest text on the step (30px+)', nameBox >= 30, String(nameBox))
    check('390px: no sideways overflow', (await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0)
    await page.screenshot({ path: `${SHOT}/player-login-pin.png` })

    await page.getByPlaceholder('••••').fill('1234')
    await page.getByRole('button', { name: 'Log in as Sam Sledge' }).click()
    await page.getByText(/If that is not you/).waitFor()
    check('the request carries the picked player and the PIN', verifies.length === 1 && verifies[0].player_id === 'p1' && verifies[0].pin === '1234', JSON.stringify(verifies))
    check('a wrong PIN repeats who they are logging in as', /You are logging in as Sam Sledge\. If that is not you, pick your own name/.test(await page.locator('body').innerText()))
    check('the server\'s own words are still shown', /That PIN didn't match/.test(await page.locator('body').innerText()))
    check('390px after the error: no sideways overflow', (await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0)
    await page.screenshot({ path: `${SHOT}/player-login-error.png` })

    await page.locator('[data-not-you]').click()
    await page.getByPlaceholder('Search your name…').waitFor()
    check('"This isn\'t me" goes back to the names', (await page.locator('[data-signing-in-as]').count()) === 0)

    await page.getByText('No Phone').click()
    await card.waitFor()
    check('no mobile on file: still says who, and names them in the explanation', /logging in as/i.test(await card.innerText()) && /no mobile number on file for No Phone/i.test(await page.locator('body').innerText()))
    check('...and offers no PIN box', (await page.getByPlaceholder('••••').count()) === 0)
    await ctx.close()
  })
  await safe('shared link', async () => {
    console.log('\n── The link people share ──')
    const stubs = async (page) => {
      await page.route('**/api/**', (r) => json(r, {}))
      await page.route(/\/api\/public\/availability\/tok$/, (r) => json(r, { club: CLUB, require_pin: true, players: [
        { id: 'p0', display_name: 'Ann Anchor', has_phone: true }, { id: 'p1', display_name: 'Sam Sledge', has_phone: true }] }))
      await page.route(/\/api\/public\/availability\/tok\/me(\?.*)?$/, (r) => json(r, { detail: 'Not verified' }, 401))
    }
    const ctx = await browser.newContext({ viewport: { width: 390, height: 800 } })
    const page = await ctx.newPage(); page.setDefaultTimeout(8000)
    await stubs(page)
    await page.goto(`${BASE}/avail/tok`)
    await page.getByPlaceholder('Search your name…').waitFor()
    check('the plain link asks who you are and picks nobody', (await page.locator('[data-signing-in-as]').count()) === 0)
    check('...and lists every player', (await page.getByText('Ann Anchor').count()) === 1 && (await page.getByText('Sam Sledge').count()) === 1)
    await ctx.close()

    const ctx2 = await browser.newContext({ viewport: { width: 390, height: 800 } })
    const p2 = await ctx2.newPage(); p2.setDefaultTimeout(8000)
    await stubs(p2)
    await p2.goto(`${BASE}/avail/tok?tab=mine&player=p1&utm=x`)
    await p2.locator('[data-signing-in-name]').waitFor()
    check('a link with ?player= picks that player', (await p2.locator('[data-signing-in-name]').innerText()) === 'Sam Sledge')
    await p2.waitForTimeout(300)
    const u = new URL(p2.url())
    check('...then the address bar is the plain link (player and tab gone)', u.pathname === '/avail/tok' && !u.searchParams.has('player') && !u.searchParams.has('tab'), p2.url())
    check('...and other query parameters are left alone', u.searchParams.get('utm') === 'x', p2.url())
    // Somebody else opens what was copied from that address bar.
    const ctx3 = await browser.newContext({ viewport: { width: 390, height: 800 } })
    const p3 = await ctx3.newPage(); p3.setDefaultTimeout(8000)
    await stubs(p3)
    await p3.goto(p2.url())
    await p3.getByPlaceholder('Search your name…').waitFor()
    check('what a person copies from the address bar picks nobody for the next person', (await p3.locator('[data-signing-in-as]').count()) === 0)
    await p2.locator('[data-not-you]').click()
    await p2.getByPlaceholder('Search your name…').waitFor()
    check('"This isn\'t me" still returns to the names after the clean-up', true)
    await ctx2.close(); await ctx3.close()
  })
  await browser.close()
  console.log(`\n${PASS} passed, ${FAIL} failed`)
  process.exit(FAIL ? 1 : 0)
}
run()
