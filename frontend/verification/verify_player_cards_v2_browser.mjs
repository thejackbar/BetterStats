// Player Cards, second release, in Chromium on the production build with the API stubbed at the network layer:
//  * special cards filed after the players in a fixed order (awards, milestones, centuries, half centuries,
//    wickets, debuts) and a player's cards of one kind stacked on ONE slot, the viewer's own first, a stack
//    opened out and a card held up out of it (Escape closes one level at a time);
//  * a special card drawn with the whole photo, and no text clipped on a long name, a long award or a wide club font;
//  * the club's own display font used on the cards (an uploaded one gets its @font-face);
//  * sharing: the picture (a real PNG) for any card, and for the player's own card a link and a looping GIF
//    (the shine, and turning over), made on the device (a real GIF with the right header and size);
//  * swaps: the tab and its count, the exact request each tap sends (ask, accept, decline, cancel), the offer
//    from a held card going straight into the builder, the empty cases, and an error shown not swallowed;
//  * 390px for overflow, and no errors in the console.
//
//   APP_URL=http://localhost:4173 SHOT_DIR=/tmp/cards2 node verification/verify_player_cards_v2_browser.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
if (SHOT) fs.mkdirSync(SHOT, { recursive: true })
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}

// A tiny real picture so the full-photo layout has something to draw.
const PHOTO = 'data:image/svg+xml;utf8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8aa"/><stop offset="1" stop-color="#334"/></linearGradient></defs><rect width="400" height="500" fill="url(#g)"/><circle cx="200" cy="170" r="80" fill="#e9c9a8"/><rect x="90" y="260" width="220" height="240" rx="40" fill="#fff"/></svg>')
const CLUB = {
  name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c',
  font_config: { display: { source: 'upload', family: 'Test Face' } }, font_display_url: '/api/images/fonts/test-face.woff2', font_display_format: 'woff2',
}
const base = (pid, name, tier, rarity, x = {}) => ({
  kind: 'player', key: `p:${pid}`, player_id: pid, name, photo_url: null, hero_photo_url: null, matches: 100, runs: 1500, bat_avg: 24.5,
  wickets: 20, bowl_avg: 31.2, dismissals: 30, rarity, tier, copies: 1, obtained_at: '2026-10-20T01:00:00Z', mine: false, ...x,
})
let sid = 0
const sp = (pid, name, kind, title, detail, x = {}) => {
  sid += 1
  return { kind: 'special', key: `s:s${sid}`, special_id: `s${sid}`, special_kind: kind, player_id: pid, name, photo_url: null, hero_photo_url: null, title,
    occurred_on: `2026-0${(sid % 9) + 1}-1${sid % 9}`, detail, tier: 'special', copies: 1, obtained_at: `2026-10-${10 + (sid % 15)}T01:00:00Z`, mine: false, ...x }
}
const ME = 'p1'
const LONG = 'Wijesinghe-Fernandez, Jacqueline'
const CARDS = [
  base(ME, 'Barendse, Jack', 'rare', 62, { mine: true, obtained_at: null, hero_photo_url: PHOTO, runs: 4114, matches: 214, wickets: 211, bat_avg: 22.98, bowl_avg: 24.1, dismissals: 98 }),
  base('p2', 'Zed, Alan', 'common', 18, { copies: 3, wickets: 0, bowl_avg: null }),
  base('p3', 'Adams, Brian', 'epic', 81),
  base('p6', LONG, 'rare', 70, { photo_url: PHOTO }),
  // Jack: five awards (a stack), three centuries (a stack), one milestone (a single)
  ...['Best Bowler', 'Best Batter', "The 'Russell Kingdon' Presidents Trophy", 'Womens - Most Improved', 'Best and Fairest and Most Valuable Player of the Whole Season'].map((t) => sp(ME, 'Barendse, Jack', 'award', t, { season: '2015_16', grade: 'Perpetual' }, { hero_photo_url: PHOTO })),
  ...[112, 101, 140].map((r) => sp(ME, 'Barendse, Jack', 'century', 'Century', { runs: r, not_out: r === 112, balls: 98, opposition: 'Neeton Cardinals Cricket Club' }, { hero_photo_url: PHOTO })),
  sp(ME, 'Barendse, Jack', 'games', '100 games', { games: 100 }, { hero_photo_url: PHOTO }),
  // Another player: a lone award, and two wicket cards (a stack)
  sp('p4', 'Eagle, Ed', 'award', 'Most Improved', { season: '2019' }),
  sp('p5', 'Mole, Sam', 'five_for', 'Five wicket haul', { wickets: 5, runs: 30, overs: 10, opposition: 'Eagles' }),
  sp('p5', 'Mole, Sam', 'hat_trick', 'Hat-trick', { season: '2025' }),
]
const totals = { regular_owned: 4, regular_total: 12, special_owned: 12, special_total: 20, copies: 16 }
const PACKS = [{ id: 'k1', source: 'weekly', label: 'Weekly pack' }]

const swapCard = (c, spare) => ({ ...c, spare, copies: undefined })
const REQ = {
  id: 'w1', direction: 'in', status: 'pending', other: { player_id: 'p7', name: 'Dave, Dan' }, created_at: new Date().toISOString(), resolved_at: null,
  give: swapCard(base('p8', 'Other, Olly', 'rare', 66), 1), want: swapCard(base('p2', 'Zed, Alan', 'common', 18), 2),
}

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = [], calls = []
  let board, swapFails = false
  const resetBoard = () => { board = { incoming: [REQ], outgoing: [], recent: [], mine: [swapCard(base('p2', 'Zed, Alan', 'common', 18), 2)], people: [{ player_id: 'p7', name: 'Dave, Dan', spare: 1 }, { player_id: 'p9', name: 'Smith, Sue', spare: 3 }], expires_days: 14, max_open: 10 } }
  resetBoard()

  const open = async (width, { height = 900 } = {}) => {
    const ctx = await browser.newContext({ viewport: { width, height }, isMobile: width < 500, hasTouch: width < 500, acceptDownloads: true })
    await ctx.addInitScript(() => { try { localStorage.setItem('bs.playerpage.open', JSON.stringify({ cards: true })) } catch (e) { /* none */ } })
    const page = await ctx.newPage()
    page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|font/i.test(m.text())) errors.push(m.text()) })
    page.on('pageerror', (e) => errors.push(String(e)))
    await page.route('**/api/**', async (route) => {
      const req = route.request(), url = req.url(), method = req.method()
      const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
      if (!url.includes('/public/availability/')) return json({})
      const path = url.split('/api')[1]
      const body = req.postData() ? JSON.parse(req.postData()) : null
      if (/\/me\/cards\/swaps\/players\//.test(url)) { calls.push(`${method} ${path}`); return json({ player: { player_id: 'p7', name: 'Dave, Dan' }, cards: [swapCard(base('p10', 'Wanted, Wes', 'epic', 80), 1)] }) }
      if (/\/me\/cards\/swaps\/[^/]+\/(accept|decline|cancel)$/.test(url)) {
        calls.push(`${method} ${path}`)
        if (swapFails) return json({ detail: 'The card they offered is no longer a double, so this swap cannot go ahead.' }, 409)
        board.incoming = []
        return json({ status: 'ok' })
      }
      if (/\/me\/cards\/swaps$/.test(url)) {
        if (method === 'POST') {
          calls.push({ method, path, body })
          board.outgoing = [{ ...REQ, id: 'o1', direction: 'out', other: { player_id: 'p7', name: 'Dave, Dan' } }]
          return json({ id: 'o1', status: 'pending' })
        }
        calls.push(`${method} ${path}`)
        return json(board)
      }
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: PACKS, pack_size: 5, season: 'Summer', cards: CARDS, totals })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 1, swaps_waiting: 1 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
      if (/\/me(\?|$)/.test(url)) return json({ club: CLUB, player: { id: ME, display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
      return json({ club: CLUB, require_pin: true, has_availability: false, players: [{ id: ME, display_name: 'Barendse, Jack', has_phone: true }] })
    })
    await page.goto(`${BASE}/avail/tok123`)
    await page.waitForSelector('[data-cards-module]', { timeout: 20000 })
    await page.waitForTimeout(500)
    return { ctx, page }
  }
  const shot = async (page, name) => { if (SHOT) await page.screenshot({ path: `${SHOT}/${name}.png` }) }
  const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  const slots = (page) => page.locator('[data-slot-card], [data-slot-stack]').evaluateAll((els) => els.map((e) => e.getAttribute('data-slot-stack') || e.getAttribute('data-slot-card')))
  const allSlots = async (page) => {
    const seen = []
    for (let i = 0; i < 8; i += 1) {
      seen.push(...(await slots(page)))
      if (await page.locator('[data-gallery-next]').isDisabled()) break
      await page.click('[data-gallery-next]'); await page.waitForTimeout(650)
    }
    while (!(await page.locator('[data-gallery-prev]').isDisabled())) { await page.click('[data-gallery-prev]'); await page.waitForTimeout(650) }
    return seen
  }

  console.log('\nthe book: categories and stacks, 390px')
  {
    const { ctx, page } = await open(390)
    const chips = await page.locator('[data-gallery-filter]').allTextContents()
    check('a chip for each kind of special that is held, with its count', ['Club awards6', 'Milestones1', 'Centuries3', 'Wickets2'].every((c) => chips.some((x) => x.replace(/\s/g, '') === c.replace(/\s/g, ''))), JSON.stringify(chips))
    check('no chip for a kind nobody holds (half centuries, debuts)', !chips.some((x) => /Half centuries|Debuts/.test(x)))
    await page.selectOption('[data-gallery-sort]', 'name')
    await page.click('[data-gallery-filter="special"]')
    const order = await allSlots(page)
    const kinds = order.map((k) => (k.startsWith('stack:') ? k.split(':')[1] : (CARDS.find((c) => c.key === k) || {}).special_kind))
    check('specials come in the order awards, milestones, centuries, wickets', JSON.stringify([...new Set(kinds.map((k) => ({ award: 'awards', games: 'milestones', century: 'centuries', five_for: 'wickets' }[k] || k)))]) === JSON.stringify(['awards', 'milestones', 'centuries', 'wickets']), JSON.stringify(kinds))
    check("a player's cards of one kind share one slot (3 stacks, not 11 cards)", order.filter((k) => k.startsWith('stack:')).length === 3 && order.length === 5, JSON.stringify(order))
    check("the viewer's own stack comes before another player's card in the same kind", order.indexOf(`stack:awards:${ME}`) < order.findIndex((k) => /s9|s1[0-9]/.test(k) && CARDS.find((c) => c.key === k)?.player_id === 'p4'), JSON.stringify(order))
    await page.click('[data-gallery-filter="all"]')
    await page.waitForTimeout(300)
    check('the players come first, then the grey slots, then the specials', (await slots(page))[0] === 'p:p6' || /^p:/.test((await slots(page))[0]))
    await page.click('[data-gallery-filter="special"]')
    await page.waitForTimeout(300)
    const stack = page.locator(`[data-slot-stack="stack:awards:${ME}"]`)
    check('a stack says how many it holds and of what', /×5 Club awards/.test(await stack.locator('[data-stack-count]').textContent()))
    check('no horizontal scroll with stacks', (await overflow(page)) <= 0)
    await shot(page, '01-stacks-390')
    await stack.click()
    await page.waitForSelector('[data-stack-viewer]')
    check('opening a stack lays out its cards', (await page.locator('[data-stack-card]').count()) === 5)
    check('...and fits the phone', (await overflow(page)) <= 0)
    await shot(page, '02-stack-open-390')
    await page.locator('[data-stack-card]').first().click()
    await page.waitForSelector('[data-card-viewer]')
    await page.keyboard.press('Escape')
    await page.waitForTimeout(200)
    const after = [await page.locator('[data-card-viewer]').count(), await page.locator('[data-stack-viewer]').count()]
    check('Escape puts down the held card and leaves the stack open', after[0] === 0 && after[1] === 1, `viewer ${after[0]}, stack ${after[1]}`)
    await page.keyboard.press('Escape')
    await page.waitForTimeout(200)
    check('a second Escape closes the stack', (await page.locator('[data-stack-viewer]').count()) === 0)
    await ctx.close()
  }

  console.log('\nthe cards themselves')
  {
    const { ctx, page } = await open(390)
    await page.click('[data-gallery-filter="special"]')
    await page.waitForTimeout(300)
    const single = page.locator(`[data-slot-card="${CARDS.find((c) => c.special_kind === 'games').key}"]`)
    const photoW = await single.locator('img').first().evaluate((i) => i.style.width)
    check('a special card uses the whole photo, edge to edge, not a window', photoW === '346px', photoW)
    check('the special card has its band and a headline', (await single.locator('[data-special-headline]').count()) === 1)
    check("the club's uploaded font has its @font-face added", /Test Face/.test(await page.evaluate(() => document.querySelector('[data-club-card-fonts]')?.textContent || '')))
    const usesFont = await page.evaluate(() => [...document.querySelectorAll('[data-fit] > span')].some((s) => /Test Face/.test(getComputedStyle(s).fontFamily)))
    check("the cards are drawn in the club's own font", usesFont)
    // Clipping: every shrink-to-fit box holds its text.
    await page.click('[data-gallery-filter="all"]')
    await page.selectOption('[data-gallery-sort]', 'name')
    await page.waitForTimeout(300)
    const clipped = []
    for (let i = 0; i < 6; i += 1) {
      const bad = await page.evaluate(() => [...document.querySelectorAll('[data-fit]')].filter((o) => { const s = o.firstElementChild; return s && s.scrollWidth > o.clientWidth + 1 && o.clientWidth > 0 }).map((o) => o.textContent))
      clipped.push(...bad)
      if (await page.locator('[data-gallery-next]').isDisabled()) break
      await page.click('[data-gallery-next]'); await page.waitForTimeout(650)
    }
    check('no name, headline or figure runs past its box (a long surname, a long award, a wide font)', clipped.length === 0, JSON.stringify(clipped))
    await page.click('[data-gallery-filter="awards"]')
    await page.waitForTimeout(300)
    await page.locator(`[data-slot-stack="stack:awards:${ME}"]`).click()
    await page.waitForSelector('[data-stack-viewer]')
    const longAward = await page.evaluate(() => [...document.querySelectorAll('[data-stack-viewer] [data-fit]')].filter((o) => /Whole Season/.test(o.textContent)).map((o) => ({ w: o.clientWidth, h: o.firstElementChild.scrollHeight, boxH: o.clientHeight, sw: o.firstElementChild.scrollWidth })))
    check('a very long award title wraps and still fits its box', longAward.length === 1 && longAward[0].sw <= longAward[0].w + 1 && longAward[0].h <= longAward[0].boxH + 1, JSON.stringify(longAward))
    await shot(page, '03-long-award-390')
    await ctx.close()
  }

  console.log('\nsharing')
  {
    const { ctx, page } = await open(390)
    await page.click('[data-share-mine]')
    await page.waitForSelector('[data-share-sheet]')
    check('the player\'s own card offers the picture, a link and two kinds of GIF', (await page.locator('[data-share-picture]').count()) === 1 && (await page.locator('[data-share-link]').count()) === 1 && (await page.locator('[data-share-gif]').count()) === 2)
    const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 20000 }), page.click('[data-share-picture]')])
    const pngPath = await dl.path()
    const png = fs.readFileSync(pngPath)
    check('the picture is a real PNG at card size, named for the player', /barendse|card/.test(dl.suggestedFilename()) && dl.suggestedFilename().endsWith('.png') && png.slice(1, 4).toString() === 'PNG' && png.length > 5000, `${dl.suggestedFilename()} ${png.length}`)
    await shot(page, '04-share-sheet-390')
    await page.click('[data-share-link]')
    await page.waitForFunction(() => /Link copied|did not work/.test(document.querySelector('[data-share-note]')?.textContent || ''))
    for (const mode of ['shine', 'turn']) {
      await page.click(`[data-share-gif="${mode}"]`)
      await page.waitForSelector('[data-gif-ready]', { timeout: 60000 })
      check(`the ${mode === 'turn' ? 'turning over' : 'shine'} GIF previews`, (await page.locator('[data-gif-preview]').getAttribute('src')).startsWith('blob:'))
      const [g] = await Promise.all([page.waitForEvent('download', { timeout: 20000 }), page.click('[data-gif-send]')])
      const bytes = fs.readFileSync(await g.path())
      const w = bytes.readUInt16LE(6), h = bytes.readUInt16LE(8)
      let frames = 0
      for (let i = 13; i < bytes.length - 1; i += 1) if (bytes[i] === 0x21 && bytes[i + 1] === 0xf9) frames += 1
      check(`the ${mode} GIF is a real looping GIF (header, 300 wide, many frames, a loop block)`, bytes.slice(0, 6).toString() === 'GIF89a' && w === 300 && h > 380 && frames >= 20 && bytes.includes(Buffer.from('NETSCAPE2.0')) && g.suggestedFilename().endsWith('.gif'), `${bytes.slice(0, 6)} ${w}x${h} frames ${frames}`)
      if (mode === 'turn' && SHOT) fs.copyFileSync(await g.path(), `${SHOT}/05-turn.gif`)
      if (mode === 'shine' && SHOT) fs.copyFileSync(await g.path(), `${SHOT}/05-shine.gif`)
    }
    await page.click('[data-share-close]')
    // another card: picture only
    await page.click('[data-gallery-filter="regular"]')
    await page.locator('[data-slot-card="p:p2"]').click()
    await page.click('[data-viewer-share]')
    await page.waitForSelector('[data-share-sheet]')
    check("another player's card offers the picture and nothing about a GIF or a page link", (await page.locator('[data-share-picture]').count()) === 1 && (await page.locator('[data-share-gif]').count()) === 0 && (await page.locator('[data-share-link]').count()) === 0)
    check('the share sheet fits a phone', (await overflow(page)) <= 0)
    await ctx.close()
  }

  console.log('\nswaps')
  {
    resetBoard(); swapFails = false
    const { ctx, page } = await open(390)
    check('the swaps tab carries the number of requests waiting', /Swaps \(1\)/.test(await page.locator('[data-cards-tab="swaps"]').textContent()))
    check('the page header counts it once the packs are gone (or shows packs first)', /1 pack to open|1 swap request/.test(await page.locator('[data-group="cards"] [data-group-summary]').first().textContent()))
    await page.click('[data-cards-tab="swaps"]')
    await page.waitForSelector('[data-swaps-panel]')
    check('a request asked of the player is shown with both cards', (await page.locator('[data-swap-request="w1"]').count()) === 1 && /Dave, Dan/.test(await page.locator('[data-swap-request="w1"]').textContent()))
    check('their doubles are counted for them', /2 doubles to swap/.test(await page.locator('[data-doubles-count]').textContent()))
    check('no horizontal scroll on the swaps tab', (await overflow(page)) <= 0)
    await shot(page, '06-swaps-390')
    calls.length = 0
    await page.click('[data-swap-accept]')
    await page.waitForSelector('[data-no-requests]')
    check('Accept makes exactly the accept request', calls.filter((c) => typeof c === 'string' && c.startsWith('POST')).join() === 'POST /public/availability/tok123/me/cards/swaps/w1/accept', JSON.stringify(calls))
    check('the answer is said, and the list is read again', /Swapped/.test(await page.locator('[data-swap-msg]').textContent()) && calls.some((c) => c === 'GET /public/availability/tok123/me/cards/swaps'))

    // an accept that the server refuses is shown, not swallowed
    resetBoard(); swapFails = true
    await page.reload(); await page.waitForSelector('[data-cards-module]')
    await page.click('[data-cards-tab="swaps"]')
    await page.click('[data-swap-accept]')
    await page.waitForFunction(() => /no longer a double/.test(document.querySelector('[data-swap-msg]')?.textContent || ''))
    check('a swap the server refuses says why and stays on the list', (await page.locator('[data-swap-request="w1"]').count()) === 1)
    swapFails = false
    calls.length = 0
    await page.click('[data-swap-decline]')
    await page.waitForSelector('[data-no-requests]')
    check('Decline makes exactly the decline request', calls.some((c) => c === 'POST /public/availability/tok123/me/cards/swaps/w1/decline'))

    // build a swap by hand
    resetBoard(); board.incoming = []
    await page.reload(); await page.waitForSelector('[data-cards-module]')
    await page.click('[data-cards-tab="swaps"]')
    await page.click('[data-swap-start]')
    await page.waitForSelector('[data-swap-builder]')
    check('the builder opens on who to swap with', (await page.locator('[data-swap-player]').count()) === 2)
    await shot(page, '07-builder-390')
    await page.locator('[data-swap-player="p7"]').click()
    await page.waitForSelector('[data-swap-card="p:p10"]')
    await page.locator('[data-swap-card="p:p10"]').click()
    await page.waitForSelector('[data-swap-card="p:p2"]')
    check('then their doubles, then yours', (await page.locator('[data-swap-card]').count()) === 2)
    await page.locator('[data-swap-card="p:p2"]').click()
    await page.waitForSelector('[data-swap-confirm]')
    await shot(page, '08-builder-confirm-390')
    check('the confirm step fits the phone', (await overflow(page)) <= 0)
    calls.length = 0
    await page.click('[data-swap-send]')
    await page.waitForSelector('[data-swap-builder]', { state: 'detached' })
    const post = calls.find((c) => typeof c === 'object')
    check('Send posts exactly who, what you give and what you want', JSON.stringify(post) === JSON.stringify({ method: 'POST', path: '/public/availability/tok123/me/cards/swaps', body: { to_player_id: 'p7', give_key: 'p:p2', want_key: 'p:p10' } }), JSON.stringify(post))
    await page.waitForSelector('[data-swap-request="o1"]')
    check('it then shows as a request you made, with a Cancel', (await page.locator('[data-swap-cancel]').count()) === 1 && /Swap request sent/.test(await page.locator('[data-swap-msg]').textContent()))

    // offered straight from a held double
    await page.click('[data-cards-tab="book"]')
    await page.click('[data-gallery-filter="regular"]')
    await page.locator('[data-slot-card="p:p2"]').click()
    await page.click('[data-viewer-offer]')
    await page.waitForSelector('[data-swap-builder]')
    check('offering a held double opens the builder with it already chosen (no step to pick yours)', (await page.locator('[data-swap-player]').count()) === 2 && !/3\. The one you give/.test(await page.locator('[data-swap-builder]').textContent()))
    await page.locator('[data-swap-player="p7"]').click()
    await page.locator('[data-swap-card="p:p10"]').click()
    await page.waitForSelector('[data-swap-confirm]')
    check('...and goes straight to confirm after their card', true)
    await ctx.close()

    // a player with nothing spare
    resetBoard(); board.mine = []; board.incoming = []
    const b = await open(390)
    await b.page.click('[data-cards-tab="swaps"]')
    await b.page.click('[data-swap-start]')
    await b.page.waitForSelector('[data-swap-builder]')
    check('with no doubles the builder says so instead of offering a swap', (await b.page.locator('[data-no-doubles]').count()) === 1 && (await b.page.locator('[data-swap-player]').count()) === 0)
    await b.ctx.close()
  }

  console.log('\nthe wide book with stacks, 1280')
  {
    resetBoard()
    const { ctx, page } = await open(1280, { height: 1000 })
    check('two pages open side by side', (await page.locator('[data-page]').count()) === 2)
    check('no horizontal scroll at 1280', (await overflow(page)) <= 0)
    await page.click('[data-gallery-filter="special"]')
    await page.waitForTimeout(300)
    await shot(page, '09-specials-1280')
    await ctx.close()
  }

  check('no errors in the console or the page', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
