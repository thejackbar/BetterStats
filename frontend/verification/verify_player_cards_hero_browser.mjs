// Which photo a card shows follows the card's `shot` (the server decides it by card type): 'profile' is the circle, 'hero' and 'action'
// fill the card with that photo, and a payload without `shot` keeps the old answer. A card with a full-length photo keeps the top of the head clear of the name: the picture starts 64px down the card (of 478), fades in
// at its top, ends where it always did (under the band), and the name and the head do not share a row. Chromium, the API stubbed.
//
//   APP_URL=http://localhost:4173 node verification/verify_player_cards_hero_browser.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'
import { cardsUrl } from './lib/cardsPage.mjs'

const BASE = process.env.APP_URL || 'http://localhost:4173'
const SHOT = process.env.SHOT_DIR || ''
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`)
}
// A head-and-shoulders picture whose head touches the top edge, like the club photos that were being cut off. 40x50 JPEG, made here.
const HERO = Buffer.from('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAAyACgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD7/ooooA//2Q==', 'base64')
const CLUB = { name: 'Verify CC', short_name: 'Verify', slug: 'verify-cc', logo_url: null, accent_color: '#b91c1c', primary_color: '#b91c1c' }
const card = (pid, name, x = {}) => ({ kind: 'player', key: `p:${pid}`, player_id: pid, name, photo_url: null, hero_photo_url: '/api/images/hero.jpg', matches: 100, runs: 1500, bat_avg: 24.5, wickets: 20, bowl_avg: 31.2, dismissals: 30, rarity: 62, tier: 'rare', copies: 1, obtained_at: '2026-10-20T01:00:00Z', mine: false, ...x })
const CARDS = [card('p1', 'Barendse, Jack', { mine: true }), card('p2', 'Kumar, Sanjay Suresh'), card('p3', 'Ryan, Andrew', { tier: 'epic' })]

const run = async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' })
  const errors = []
  for (const [width, label] of [[1280, 'wide'], [390, 'phone']]) {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, isMobile: width < 500, hasTouch: width < 500 })
    const p = await ctx.newPage()
    p.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|font/i.test(m.text())) errors.push(m.text()) })
    p.on('pageerror', (e) => errors.push(String(e)))
    await p.route('**/api/**', async (r) => {
      const url = r.request().url()
      const json = (o) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(o) })
      if (url.endsWith('hero.jpg')) return r.fulfill({ status: 200, contentType: 'image/jpeg', body: HERO })
      if (!url.includes('/public/availability/')) return json({})
      if (/\/me\/cards\/(showcase|feed|board|sets|swaps|wants)/.test(url)) return json({ cards: [], events: [], entries: [], sets: [], max: 6, incoming: [], outgoing: [], recent: [], mine: [], people: [], wants: [], ready: 0, limit: 100 })
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: [], pack_designs: {}, cards: CARDS, totals: { regular_owned: 3, regular_total: 14, special_owned: 0, special_total: 0, copies: 3 }, features: {} })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 0, swaps_waiting: 0 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
      if (/\/me(\?|$)/.test(url)) return json({ club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
      return json({ club: CLUB, require_pin: true, has_availability: false, players: [{ id: 'p1', display_name: 'Barendse, Jack', has_phone: true }] })
    })
    await p.goto(cardsUrl(BASE, 'tok123', '/book'))
    await p.waitForSelector('[data-card-hero]', { timeout: 20000 })
    await p.waitForTimeout(500)
    const m = await p.evaluate(() => [...document.querySelectorAll('[data-card-hero]')].map((img) => {
      const r = img.getBoundingClientRect(), panel = img.parentElement.getBoundingClientRect(), scale = panel.width / 346
      const cs = getComputedStyle(img)
      return { top: (r.top - panel.top) / scale, bottom: (panel.bottom - r.bottom) / scale, mask: cs.maskImage || cs.webkitMaskImage || '', pos: cs.objectPosition }
    }))
    check(`${label}: every full-photo card starts its picture 64px down (of the 478px card), not at the top`, m.length === 3 && m.every((x) => Math.abs(x.top - 64) < 1.5), JSON.stringify(m))
    check(`${label}: the picture still ends 40px above the card's bottom edge, where it always did`, m.every((x) => Math.abs(x.bottom - 40) < 1.5), JSON.stringify(m))
    check(`${label}: it fades in at the top, and shows the top of the photo (not a middle crop)`, m.every((x) => /linear-gradient/.test(x.mask) && /^50% 0%|^50% 0px/.test(x.pos)), JSON.stringify(m))
    if (SHOT) { fs.mkdirSync(SHOT, { recursive: true }); await p.screenshot({ path: `${SHOT}/hero-${width}.png` }) }
    await ctx.close()
  }

  // ── Which photo each kind of card shows ────────────────────────────────────
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const p = await ctx.newPage()
    p.on('pageerror', (e) => errors.push(String(e)))
    const mk = (pid, name, shot, tier, x = {}) => ({ ...card(pid, name, { tier }), photo_url: '/api/images/head.jpg', hero_photo_url: '/api/images/hero.jpg', action_photo_url: '/api/images/action.jpg', shot, ...x })
    const MIXED = [mk('p1', 'Barendse, Jack', 'hero', 'common', { mine: true }), mk('p2', 'Kumar, Sanjay', 'hero', 'rare'), mk('p3', 'Ryan, Andrew', 'hero', 'epic'), mk('p4', 'Lyall, Josh', 'action', 'special', { kind: 'special', special_kind: 'century', key: 's:x1', title: 'Century' }), mk('p5', 'Old, Server', undefined, 'rare'), mk('p6', 'Circle, Only', 'profile', 'common')]
    await p.route('**/api/**', async (r) => {
      const url = r.request().url()
      const json = (o) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(o) })
      if (/\/api\/images\/.*\.jpg$/.test(url)) return r.fulfill({ status: 200, contentType: 'image/jpeg', body: HERO })
      if (!url.includes('/public/availability/')) return json({})
      if (/\/me\/cards\/(showcase|feed|board|sets|swaps|wants)/.test(url)) return json({ cards: [], events: [], entries: [], sets: [], max: 6, incoming: [], outgoing: [], recent: [], mine: [], people: [], wants: [], ready: 0, limit: 100 })
      if (/\/me\/cards$/.test(url)) return json({ club: CLUB, week_resets_at: '2026-10-26T16:00:00+00:00', packs: [], pack_designs: {}, cards: MIXED, totals: { regular_owned: 5, regular_total: 14, special_owned: 0, special_total: 0, copies: 5 }, features: {} })
      if (/\/me\/profile/.test(url)) return json({ club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, modules: ['cards'], cards: { ready: 0, swaps_waiting: 0 }, has_availability: false, squads: [], selected: [], training: { upcoming: [] }, can_update_details: false })
      if (/\/me(\?|$)/.test(url)) return json({ club: CLUB, player: { id: 'p1', display_name: 'Barendse, Jack' }, dates: [], availability: {}, has_squad: false, squads: [], has_availability: false })
      return json({ club: CLUB, require_pin: true, has_availability: false, players: [{ id: 'p1', display_name: 'Barendse, Jack', has_phone: true }] })
    })
    await p.goto(cardsUrl(BASE, 'tok123', '/book'))
    await p.waitForSelector('[data-card-hero], [data-card-head]', { timeout: 20000 })
    await p.waitForTimeout(600)
    const seen = await p.evaluate(() => ({
      hero: [...document.querySelectorAll('[data-card-hero]')].map((i) => [i.getAttribute('data-card-hero'), i.getAttribute('src')]),
      head: [...document.querySelectorAll('[data-card-head]')].map((i) => i.getAttribute('src')),
    }))
    check('Common and Rare cards fill with the hero photo too, when the player has one', seen.hero.filter(([k, u]) => k === 'hero' && /hero\.jpg/.test(u)).length === 3, JSON.stringify(seen))
    check('a special card fills with the action shot', seen.hero.some(([k, u]) => k === 'action' && /action\.jpg/.test(u)), JSON.stringify(seen))
    check('a card the server says is a circle (a player with no hero photo) shows the profile photo, and nothing fills the card', seen.head.length === 1 && /head\.jpg/.test(seen.head[0]), JSON.stringify(seen))
    check('a card from a server that does not say (no shot) keeps the old behaviour: the hero position', seen.hero.some(([k]) => k === 'legacy'), JSON.stringify(seen))
    if (SHOT) await p.screenshot({ path: `${SHOT}/hero-by-type.png` })
    await ctx.close()
  }
  check('no page errors', errors.length === 0, errors.join(' | '))
  await browser.close()
  console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
  if (FAIL.length) { console.log('FAILED:\n  ' + FAIL.join('\n  ')); process.exit(1) }
}

run().catch((e) => { console.error(e); process.exit(1) })
