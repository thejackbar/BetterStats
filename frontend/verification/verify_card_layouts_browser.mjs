// Drives the real BetterPosts editor in Chromium with the API stubbed at the
// network layer, for the three card layouts: Round Cover (T13), Giant Type (C5)
// and Round Highlights (RS8).
//
//   npx vite build && npx vite preview --port 5197 &
//   CUTOUT=/path/cutout.png PHOTO=/path/photo.jpg node frontend/verification/verify_card_layouts_browser.mjs [baseUrl]
//   SHOTS=/tmp/cards node ...        also writes a PNG per layout and size
//
// What a build cannot tell you: that each layout is in its post type's picker and
// draws the right words from the data it was given (the round, both clubs, the
// date; the giant word and the player's name; the kicker, both scores and the
// winner's trophy); that a photo reaches the post when one is chosen and is
// absent when not; that the giant type sits BEHIND the player and comes back in
// front of them as an outline; that the winner is the top row of the score card;
// that the sponsor grid sits clear of the text at every size; that nothing falls
// outside the post at square, portrait and story; and that the controls fit at
// 390px.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'
import { makeEditor, shotNode, press, tab, seen, ROOT } from './card_layouts_harness.mjs'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const SHOTS = process.env.SHOTS || ''
const CUTOUT = process.env.CUTOUT || ''
const PHOTO = process.env.PHOTO || ''
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
const SIZES = [['square', 1080, 1080], ['portrait', 1080, 1350], ['story', 1080, 1920]]

// Reads the exported post. Every key is read through a presence-safe accessor so a
// layout that is missing reports as missing instead of crashing the run.
async function read(page) {
  return (await page.evaluate((rootSrc) => {
    const root = (new Function(`return (${rootSrc})()`))()
    if (!root) return null
    const rr = root.getBoundingClientRect()
    const rel = (el) => { const r = el.getBoundingClientRect(); return { x: r.left - rr.left, y: r.top - rr.top, w: r.width, h: r.height } }
    const q = (n) => root.querySelector(`[data-layer="${n}"]`)
    const layers = [...root.children].map((c) => c.getAttribute('data-layer') || c.tagName.toLowerCase())
    const text = (n) => { const e = q(n); return e ? e.innerText.replace(/\s+/g, ' ').trim() : '' }
    const grid = root.querySelector('[data-sponsor-grid]')
    const clipped = (e) => { for (let a = e.parentElement; a && a !== root; a = a.parentElement) if (getComputedStyle(a).overflow === 'hidden') return true; return false }
    const outline = q('Giant type outline')
    const filled = q('Giant type')
    const rows = q('Score card') ? [...q('Score card').children] : []
    return {
      w: rr.width, h: rr.height, layers,
      photo: !!q('Hero photo') || !!q('Photo') || !!q('Player'),
      heroImg: (q('Hero photo') || q('Photo') || q('Player') || { querySelector: () => null }).querySelector('img') ? true : false,
      roundText: text('Round and fixture'), nameText: text('Name and line'), titleText: text('Kicker and title'), sideLabel: text('Side label'),
      sideWordTransform: q('Side word') ? getComputedStyle(q('Side word')).transform : '',
      sideWordText: text('Side word'),
      stackRect: q('Round and fixture') ? rel(q('Round and fixture')) : null,
      nameRect: q('Name and line') ? rel(q('Name and line')) : null,
      cardRect: q('Score card') ? rel(q('Score card')) : null,
      stripRect: q('Hatched strip') ? rel(q('Hatched strip')) : null,
      grid: grid ? { ...rel(grid), n: grid.querySelectorAll('img').length } : null,
      badges: q('Round and fixture') ? q('Round and fixture').querySelectorAll('img, svg').length : 0,
      outlineStyle: outline ? { color: getComputedStyle(outline).color, stroke: getComputedStyle(outline).webkitTextStrokeWidth } : null,
      filledColor: filled ? getComputedStyle(filled).color : null,
      statDividers: q('Name and line') ? q('Name and line').querySelectorAll('span[style*="width: 2px"]').length : 0,
      scoreRows: rows.map((r) => ({ text: r.innerText.replace(/\s+/g, ' ').trim(), opacity: getComputedStyle(r).opacity, svg: r.querySelectorAll('svg').length })),
      hatched: !!q('Hatched strip'),
      overflowList: [...root.querySelectorAll('*')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > rr.right + 1 || r.left < rr.left - 1 || r.bottom > rr.bottom + 1 || r.top < rr.top - 1) && !e.closest('svg') && e.tagName !== 'IMG' && !clipped(e) && !e.closest('[data-layer="Glow"]') && e.getAttribute('data-layer') !== 'Glow' && !e.closest('[data-layer="Side word"]') && !e.closest('[data-layer="Side label"]') && !e.closest('[data-layer="Giant type"]') && !e.closest('[data-layer="Giant type outline"]') }).map((e) => `${e.tagName}${e.getAttribute('data-layer') ? '[' + e.getAttribute('data-layer') + ']' : ''}`),
    }
  }, ROOT.toString()))
}
const EMPTY = { w: 0, h: 0, layers: [], overflowList: ['no post'], scoreRows: [], photo: false }
const get = async (page) => (await read(page)) || EMPTY

// ── Round Cover (T13) ───────────────────────────────────────────────────────
for (const [size, W, H] of SIZES) {
  const { ctx, page, errors, run } = await makeEditor(browser, BASE, { layout: 'T13', size, nSponsors: 3 })
  await run.loadXI()
  await page.waitForTimeout(500)
  const before = await get(page)
  ck(`T13 ${size}: draws a post`, before.w === W && before.h === H, `${before.w}x${before.h}`)
  ck(`T13 ${size}: layers named`, ['Glow', 'Side word', 'Shade', 'Round and fixture', 'Platform credit', 'Corner top left', 'Corner bottom right'].every((n) => before.layers.includes(n)), before.layers.join(','))
  ck(`T13 ${size}: no hero layer before a photo is chosen`, !before.layers.includes('Hero photo'))
  ck(`T13 ${size}: side word reads SELECTION, turned a quarter turn`, /SELECTION/.test(before.sideWordText) && /matrix\(\s*0,\s*1,\s*-1,\s*0/.test(before.sideWordTransform), `${before.sideWordText} ${before.sideWordTransform}`)
  ck(`T13 ${size}: round number from the fixture`, /ROUND 1/.test(before.roundText), before.roundText)
  ck(`T13 ${size}: both clubs named`, /SCARBOROUGH/.test(before.roundText) && /SOUTH PERTH/.test(before.roundText), before.roundText)
  ck(`T13 ${size}: date and time`, /2026-10-03|SAT/.test(before.roundText) && /10:30/.test(before.roundText), before.roundText)
  ck(`T13 ${size}: two club marks`, before.badges >= 2, `${before.badges}`)
  ck(`T13 ${size}: sponsor grid below the text`, before.grid && before.stackRect && before.grid.n === 3 && before.grid.y >= before.stackRect.y + before.stackRect.h - 1, JSON.stringify([before.grid, before.stackRect]))
  ck(`T13 ${size}: grid inside the post`, before.grid && before.grid.y + before.grid.h <= H && before.grid.x >= 0 && before.grid.x + before.grid.w <= W, JSON.stringify(before.grid))
  ck(`T13 ${size}: nothing outside the post`, before.overflowList.length === 0, before.overflowList.join(' | '))
  if (CUTOUT) {
    await run.addPhoto(CUTOUT)
    await page.waitForTimeout(500)
    const after = await get(page)
    ck(`T13 ${size}: hero photo layer after a photo is chosen`, after.layers.includes('Hero photo') && after.heroImg, after.layers.join(','))
    ck(`T13 ${size}: hero sits between the glow and the type`, after.layers.indexOf('Glow') < after.layers.indexOf('Hero photo') && after.layers.indexOf('Hero photo') < after.layers.indexOf('Round and fixture'), after.layers.join(','))
    ck(`T13 ${size}: still nothing outside the post with a photo`, after.overflowList.length === 0, after.overflowList.join(' | '))
    if (SHOTS) await shotNode(page, `${SHOTS}/T13-${size}.png`)
  }
  ck(`T13 ${size}: no page errors`, errors.length === 0, errors.slice(0, 3).join(' | '))
  await ctx.close()
}

// ── Giant Type (C5) ─────────────────────────────────────────────────────────
for (const [size, W, H] of SIZES) {
  const { ctx, page, errors, run } = await makeEditor(browser, BASE, { layout: 'C5', size, nSponsors: 2 })
  await run.prepare({ cutout: CUTOUT, kind: 'CAPTAIN', headline: 'FIRST XI', sub: '1ST GRADE · 2026-27' })
  await page.waitForTimeout(600)
  const d = await get(page)
  ck(`C5 ${size}: draws a post`, d.w === W && d.h === H, `${d.w}x${d.h}`)
  ck(`C5 ${size}: layers named`, ['Giant type', 'Giant type outline', 'Name shade', 'Name and line', 'Kind chip', 'Club logo', 'Platform credit'].every((n) => d.layers.includes(n)), d.layers.join(','))
  ck(`C5 ${size}: the word the club typed`, d.layers.length > 0 && d.nameText.length > 0, d.nameText)
  ck(`C5 ${size}: first name and surname`, /GEORGE/.test(d.nameText) && /PULLINGER/.test(d.nameText), d.nameText)
  ck(`C5 ${size}: stats split into a row`, /1ST GRADE/.test(d.nameText) && /2026-27/.test(d.nameText) && d.statDividers === 1, `${d.nameText} dividers=${d.statDividers}`)
  ck(`C5 ${size}: outline copy is hollow`, d.outlineStyle && /0, 0, 0, 0|transparent/.test(d.outlineStyle.color) && parseFloat(d.outlineStyle.stroke) >= 2, JSON.stringify(d.outlineStyle))
  ck(`C5 ${size}: filled copy carries the accent`, d.filledColor && !/0, 0, 0, 0/.test(d.filledColor), d.filledColor)
  if (CUTOUT) {
    ck(`C5 ${size}: player layer present`, d.layers.includes('Player') && d.heroImg, d.layers.join(','))
    ck(`C5 ${size}: type behind the player, outline in front`, d.layers.indexOf('Giant type') < d.layers.indexOf('Player') && d.layers.indexOf('Player') < d.layers.indexOf('Giant type outline'), d.layers.join(','))
  }
  ck(`C5 ${size}: sponsor grid below the name`, d.grid && d.nameRect && d.grid.n === 2 && d.grid.y >= d.nameRect.y + d.nameRect.h - 1, JSON.stringify([d.grid, d.nameRect]))
  ck(`C5 ${size}: nothing outside the post`, d.overflowList.length === 0, d.overflowList.join(' | '))
  if (SHOTS) await shotNode(page, `${SHOTS}/C5-${size}.png`)
  // A plain sentence is one line, never cut into stats.
  const sub = page.getByPlaceholder('FOR THE 2025-26 SEASON').first()
  if (await sub.count()) {
    await sub.fill('FOR THE 2026-27 SEASON')
    await page.waitForTimeout(400)
    const e = await get(page)
    ck(`C5 ${size}: a sentence is not split into stats`, /FOR THE 2026-27 SEASON/.test(e.nameText) && e.statDividers === 0, `${e.nameText} dividers=${e.statDividers}`)
  } else ck(`C5 ${size}: subheadline field is offered`, false)
  ck(`C5 ${size}: no page errors`, errors.length === 0, errors.slice(0, 3).join(' | '))
  await ctx.close()
}

// ── Round Highlights cover (RS8) ────────────────────────────────────────────
for (const [size, W, H] of SIZES) {
  const { ctx, page, errors, run } = await makeEditor(browser, BASE, { layout: 'RS8', size, nSponsors: 2 })
  await run.importResult()
  await page.waitForTimeout(500)
  const none = await get(page)
  ck(`RS8 ${size}: draws a post`, none.w === W && none.h === H, `${none.w}x${none.h}`)
  ck(`RS8 ${size}: no photo layer before a photo is chosen`, !none.layers.includes('Photo'), none.layers.join(','))
  ck(`RS8 ${size}: the card is still drawn without a photo`, none.layers.includes('Score card') && none.scoreRows.length === 2, none.layers.join(','))
  if (PHOTO) { await run.addPhoto(PHOTO, 'highlights-photo-input'); await page.waitForTimeout(600) }
  let d = await get(page)
  for (let i = 0; PHOTO && !d.layers.includes('Photo') && i < 4; i++) { await page.waitForTimeout(700); d = await get(page) }
  ck(`RS8 ${size}: layers named`, ['Foot shade', 'Kicker and title', 'Club logo', 'Hatched strip', 'Score card'].every((n) => d.layers.includes(n)), d.layers.join(','))
  if (PHOTO) ck(`RS8 ${size}: photo layer after a photo is chosen`, d.layers.includes('Photo') && d.heroImg && d.layers.indexOf('Photo') === 0, d.layers.join(','))
  ck(`RS8 ${size}: kicker names the round and the opponent`, /RND 1 V SOUTH PERTH/.test(d.titleText), d.titleText)
  ck(`RS8 ${size}: title`, /ROUND HIGHLIGHTS/.test(d.titleText), d.titleText)
  ck(`RS8 ${size}: competition on the side label`, /WA PREMIER CRICKET/.test(d.sideLabel), d.sideLabel)
  ck(`RS8 ${size}: two score rows`, d.scoreRows.length === 2, JSON.stringify(d.scoreRows))
  ck(`RS8 ${size}: winner on top with the trophy and both scores`, d.scoreRows.length === 2 && /SOUTH PERTH/.test(d.scoreRows[0].text) && /4-242/.test(d.scoreRows[0].text) && d.scoreRows[0].svg === 1 && /8-228/.test(d.scoreRows[1].text), JSON.stringify(d.scoreRows))
  ck(`RS8 ${size}: loser row dimmed and without a trophy`, d.scoreRows.length === 2 && Math.abs(parseFloat(d.scoreRows[1].opacity) - 0.8) < 0.01 && d.scoreRows[1].svg === 0, JSON.stringify(d.scoreRows))
  ck(`RS8 ${size}: overs shown`, d.scoreRows.length === 2 && /\(50\)/.test(d.scoreRows[0].text), JSON.stringify(d.scoreRows))
  ck(`RS8 ${size}: hatched strip along the foot`, d.stripRect && Math.abs(d.stripRect.y + d.stripRect.h - (H - (size === 'story' ? 230 : 0))) < 2 && d.stripRect.w === W, JSON.stringify(d.stripRect))
  ck(`RS8 ${size}: card sits above the strip`, d.cardRect && d.stripRect && d.cardRect.y + d.cardRect.h <= d.stripRect.y, JSON.stringify([d.cardRect, d.stripRect]))
  ck(`RS8 ${size}: sponsor grid inside the strip`, d.grid && d.stripRect && d.grid.n === 2 && d.grid.y >= d.stripRect.y - 1 && d.grid.y + d.grid.h <= d.stripRect.y + d.stripRect.h + 1, JSON.stringify([d.grid, d.stripRect]))
  ck(`RS8 ${size}: nothing outside the post`, d.overflowList.length === 0, d.overflowList.join(' | '))
  if (SHOTS && PHOTO) await shotNode(page, `${SHOTS}/RS8-${size}.png`)
  ck(`RS8 ${size}: no page errors`, errors.length === 0, errors.slice(0, 3).join(' | '))
  await ctx.close()
}

// ── The downloaded PNG (rule: read a real export, not the preview) ──────────
// The export goes through modern-screenshot, which paints less than the browser
// does. Masks, text strokes, repeating gradients and quarter-turn text have to
// survive it, so each layout is downloaded and its pixels are read back.
for (const layout of ['T13', 'C5', 'RS8']) {
  const { ctx, page, run } = await makeEditor(browser, BASE, { layout, size: 'portrait', nSponsors: 2 })
  await run.prepare({ cutout: CUTOUT, photo: PHOTO, kind: 'CAPTAIN', headline: 'FIRST XI', sub: '1ST GRADE · 2026-27' })
  await page.waitForTimeout(800)
  let png = null
  try {
    const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 40000 }), page.getByRole('button', { name: /DOWNLOAD PNG/ }).first().click()])
    const file = SHOTS ? `${SHOTS}/${layout}-download.png` : `/tmp/${layout}-download.png`
    await dl.saveAs(file)
    const buf = (await import('node:fs')).readFileSync(file)
    png = { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20), magic: buf.subarray(1, 4).toString(), bytes: buf.length }
  } catch (e) { png = { err: String(e).slice(0, 120) } }
  // The app exports at twice the post's size.
  ck(`${layout}: the download is a 4:5 PNG at 2x`, png && png.magic === 'PNG' && png.w === 2160 && png.h === 2700, JSON.stringify(png))
  ck(`${layout}: the PNG is not blank`, png && png.bytes > 40000, JSON.stringify(png))
  await ctx.close()
}

// ── Picker and 390px ────────────────────────────────────────────────────────
for (const [layout, name] of [['T13', 'Round Cover'], ['C5', 'Giant Type'], ['RS8', 'Highlights Cover']]) {
  const { ctx, page } = await makeEditor(browser, BASE, { layout, size: 'portrait' })
  await tab(page, 'Design')
  await page.waitForTimeout(300)
  ck(`${layout}: offered in the picker as ${name}`, await seen(page.getByRole('button', { name: new RegExp(name) })))
  await ctx.close()
  const m = await makeEditor(browser, BASE, { layout, size: 'portrait', mobile: true, viewport: { width: 390, height: 844 } })
  const overflow = await m.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck(`${layout}: no horizontal scroll at 390px`, overflow <= 1, `${overflow}px`)
  await m.ctx.close()
}

console.log(`\n${pass} passed, ${fail} failed`)
await browser.close()
process.exit(fail ? 1 : 0)
