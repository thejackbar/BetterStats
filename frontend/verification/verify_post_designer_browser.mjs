// Drives the real BetterPosts designer (/admin/social-post) in Chromium with
// the API stubbed at the network layer.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_post_designer_browser.mjs [baseUrl]
//
// Checks the things a build cannot: that picking a post size actually changes
// the canvas AND the off-screen node the PNG is captured from (in step, or the
// download comes out a different shape from the preview); that a fixed 1080×1080
// layout is really placed into a 4:5 canvas rather than stretched; that the
// blank canvas is genuinely the new size; that Preview shows every page of a
// carousel; and that the four "where did that go" explanations are on screen
// where somebody would look for them.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const SETTINGS = {
  id: 'org-1', name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'applecross',
  logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null,
}
const PLAYERS = [
  // With no photo every hero layout renders its CREST FALLBACK instead of the
  // cut-out, so a roster of photo-less players silently tests the wrong branch.
  { id: 'p1', name: 'Jack Barendse', display_name: 'Jack Barendse', status: 'active', photo_url: '/api/images/players/p1/photo' },
  { id: 'p2', name: 'Sam Alborn', display_name: 'Sam Alborn', status: 'active', photo_url: '/api/images/players/p2/photo' },
]
const MEDIA = [
  { id: 'm1', name: 'sponsor-white-bg.png', url: '/api/admin/social/media/m1/file' },
  { id: 'm2', name: 'team-photo.jpg', url: '/api/admin/social/media/m2/file' },
]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

// A 2×2 PNG, so an <img> in the club library actually resolves rather than
// leaving a broken tile the checks then can't tell from a missing feature.
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC',
  'base64',
)

async function openEditor(query = '?type=lineup') {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  const writes = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_/.test(m.text())) errors.push(m.text()) })

  const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const method = route.request().method()
    if (method !== 'GET') writes.push({ url, method })
    if (/\/social\/media\/[^/]+\/file/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    if (/\/images\/players\/[^/]+\/photo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    if (/\/auth\/me/.test(url)) return route.fulfill(json({
      id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross',
      entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
    }))
    if (/\/admin\/social\/media\?kind=background/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json(MEDIA))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json(PLAYERS))
    if (/sponsors/.test(url)) return route.fulfill(json([]))
    if (/selection\/overview/.test(url)) return route.fulfill(json({ fixtures: [] }))
    if (/lineups/.test(url)) return route.fulfill(json({ matches: [] }))
    if (/usage/.test(url)) return route.fulfill(json({ ok: true }))
    return route.fulfill(json({}))
  })

  await page.goto(`${BASE}/admin/social-post${query}`, { waitUntil: 'domcontentloaded' })
  // Anchor on the export button, which every build of this editor has —
  // waiting on anything this change ADDS would make a control run die here and
  // say nothing about the forty checks below. networkidle never settles on this
  // app (HeartbeatBeacon), so it is never used.
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  return { ctx, page, errors, writes }
}

// Reads that report absence instead of throwing.
const textOf = async (loc) => { try { return (await loc.count()) ? await loc.first().innerText() : '' } catch { return '' } }
const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }

// Reads the canvas caption ("1080 × 1350 · 48% · PORTRAIT · 4:5").
const captionOf = (page) => page.locator('text=/^\\d+ × \\d+ ·/').first().innerText().catch(() => '')

// The off-screen node the PNG is actually captured from.
async function exportNodeBox(page) {
  return page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find(
      (d) => d.style.left === '-9999px' && d.style.position === 'absolute',
    )
    const first = holder?.firstElementChild
    if (!first) return null
    return { w: parseFloat(first.style.width), h: parseFloat(first.style.height), count: holder.children.length }
  })
}

// The LAYOUT itself, inside the export node — the thing that has to be the new
// size now that a taller canvas means more room rather than a band.
async function templateBox(page) {
  return page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find(
      (d) => d.style.left === '-9999px' && d.style.position === 'absolute',
    )
    const node = holder?.firstElementChild
    // The page div holds the background, the layout and any overlay layers; the
    // layout is the child that is not the SocialBackground.
    const kid = node && [...node.children].find((c) => c.tagName === 'DIV' && c.style.width)
    if (!kid) return null
    const r = kid.getBoundingClientRect()
    return { w: Math.round(r.width), h: Math.round(r.height) }
  })
}

async function pickSize(page, label) {
  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await press(page.getByRole('button', { name: new RegExp(`^${label}`) }))
  await page.waitForTimeout(150)
}

// ── 1. Post size ───────────────────────────────────────────────────────────
{
  const { ctx, page, errors } = await openEditor()

  await press(page.getByRole('button', { name: 'Design', exact: true }))
  const sizesVisible = await page.getByRole('button', { name: /^Portrait/ }).first().isVisible().catch(() => false)
  ck('a post size picker is offered', sizesVisible)

  const squareCap = await captionOf(page)
  ck('square is the default canvas', /1080 × 1080/.test(squareCap), squareCap)
  const squareNode = await exportNodeBox(page)
  ck('the export node matches the square canvas', squareNode?.w === 1080 && squareNode?.h === 1080, JSON.stringify(squareNode))

  await pickSize(page, 'Portrait')
  const portraitCap = await captionOf(page)
  ck('picking Portrait makes the canvas 1080 × 1350', /1080 × 1350/.test(portraitCap), portraitCap)
  ck('the caption names the shape', /PORTRAIT · 4:5/.test(portraitCap), portraitCap)

  // The download must be the same shape as the preview — the whole reason the
  // size is worked out in one place.
  const portraitNode = await exportNodeBox(page)
  ck('the export node follows the canvas', portraitNode?.w === 1080 && portraitNode?.h === 1350, JSON.stringify(portraitNode))

  // The LAYOUT is now drawn at the canvas size rather than placed into it —
  // measured off the real element, not inferred from the code.
  const drawn = await templateBox(page)
  ck('the layout is drawn at the full canvas height', drawn?.h === 1350, JSON.stringify(drawn))
  ck('and at the full width', drawn?.w === 1080, JSON.stringify(drawn))

  // Nothing is scaled into a band any more, so there must be no frame at all.
  const framed = await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    return !!holder?.firstElementChild?.querySelector('[data-post-frame]')
  })
  ck('and is not letterboxed into the canvas', drawn?.h === 1350 && framed === false, `framed=${framed}`)

  const nativeNote = await textOf(page.getByTestId('size-native-note'))
  ck('the panel says the layout uses the whole canvas', /1080×1350/.test(nativeNote), nativeNote)

  // The Fit/Fill control existed only to describe a band, so it must be gone.
  ck('no Fit/Fill choice is offered any more', !(await seen(page.getByRole('button', { name: 'Fill & crop' }))))

  await pickSize(page, 'Story')
  const storyCap = await captionOf(page)
  ck('Story is 1080 × 1920', /1080 × 1920/.test(storyCap), storyCap)
  const storyDrawn = await templateBox(page)
  ck('and the layout fills the story too', storyDrawn?.h === 1920 && storyDrawn?.w === 1080, JSON.stringify(storyDrawn))

  ck('no page errors while resizing', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 1b. Every family reflows, and where the picker does NOT belong ─────────
{
  // One layout from each family — they are drawn by three different shells
  // (cricket's own roots, the roundup Post, the event FRAME), so one passing
  // says nothing about the other two.
  for (const [id, name] of [['T4', 'a lineup layout'], ['FX1', 'a roundup layout'], ['EV1', 'an event poster']]) {
    const { ctx, page } = await openEditor(`?template=${id}`)
    await pickSize(page, 'Portrait')
    const box = await templateBox(page)
    ck(`${name} fills the 4:5 canvas`, box?.w === 1080 && box?.h === 1350, `${id} ${JSON.stringify(box)}`)
    await ctx.close()
  }

  // A scorecard is 1920×1080 and already has its own reframing control, so
  // offering a second one would be two answers to one question.
  const sc = await openEditor('?type=scorecard')
  await press(sc.page.getByRole('button', { name: 'Design', exact: true }))
  await sc.page.waitForTimeout(250)
  const scHasPicker = await seen(sc.page.getByRole('button', { name: /^Portrait/ }))
  ck('a scorecard is not offered the post-size picker', !scHasPicker)
  const scCap = await captionOf(sc.page)
  ck('and keeps its own 1920 × 1080', /1920 × 1080/.test(scCap), scCap)
  await sc.ctx.close()
}

// ── 1c. A cut-out headshot grows with the canvas ───────────────────────────
// T7/C3/C1 stand the player's cut-out ON the panel floor and let it overflow
// the top — so its height is a FIXED number, and a taller canvas would grow the
// box while the photo stayed put, leaving dead air above it. The height is now
// derived from the canvas; at 1080 it is exactly the number it always was.
{
  const { ctx, page, errors } = await openEditor('?template=T7')

  await press(page.getByRole('button', { name: 'Content', exact: true }))
  await page.waitForTimeout(200)
  for (const p of PLAYERS) await press(page.getByRole('button', { name: new RegExp(`^${p.name}\\b`) }))
  await page.waitForTimeout(300)

  // Only the cut-out is sized this way (a fixed height with an auto width); the
  // crest fallback beside it is a square, so this cannot pick up the wrong img.
  const cutout = () => page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find(
      (d) => d.style.left === '-9999px' && d.style.position === 'absolute',
    )
    const node = holder?.firstElementChild
    if (!node) return null
    const img = [...node.querySelectorAll('img')].find((x) => x.style.width === 'auto' && x.style.height)
    return img ? parseFloat(img.style.height) : null
  })

  const sq = await cutout()
  ck('the hero cut-out renders at all', sq !== null, String(sq))
  ck('and is unchanged at 1080', sq === 720, String(sq))

  await pickSize(page, 'Story')
  await page.waitForTimeout(250)
  const st = await cutout()
  ck('the cut-out grows with a taller canvas', st !== null && st > sq, `${sq} -> ${st}`)

  ck('no page errors measuring the cut-out', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 1d. The taller canvas is DESIGNED for, not just filled ─────────────────
// Reflow made every layout draw at the full canvas; it did not make any of them
// a portrait design. These measure the difference: a masthead that keeps a
// share of the extra height rather than becoming a tenth of the post, a sponsor
// strip that is still a strip, row type that steps up with the slot it sits in,
// and a body that runs to the footer instead of stopping where the square did.
// Every one is read off the real element at both sizes, and every one is
// asserted UNCHANGED at 1080 — the square output is the same post it was.
{
  // One element inside the export node, by a predicate run in the page.
  const box = (page, findSrc) => page.evaluate((src) => {
    const holder = [...document.querySelectorAll('div')].find(
      (d) => d.style.left === '-9999px' && d.style.position === 'absolute',
    )
    const root = holder?.firstElementChild
    if (!root) return null
    // eslint-disable-next-line no-new-func
    const find = new Function('root', src)
    const el = find(root)
    if (!el) return null
    const rr = root.getBoundingClientRect()
    const r = el.getBoundingClientRect()
    const cs = getComputedStyle(el)
    return {
      // Relative to the layout, and unscaled — the live canvas is drawn at a
      // preview scale, so raw client pixels would move with the zoom.
      // EVERY field is a percentage of the post's own height, font included —
      // one unit, so every check converts to real post pixels the same way
      // (× 10.8 at square, × 13.5 at portrait). The first cut returned the font
      // already multiplied by 1080 while the positions were plain percentages,
      // so the step-up check converted twice and read a genuine 31 → 35 as
      // 31 → 28, i.e. a design that had worked reported as a failure.
      top: Math.round(((r.top - rr.top) / rr.height) * 10000) / 100,
      bottom: Math.round(((r.bottom - rr.top) / rr.height) * 10000) / 100,
      h: Math.round((r.height / rr.height) * 10000) / 100,
      font: Math.round((parseFloat(cs.fontSize) / rr.height) * 10000) / 100,
    }
  }, findSrc)

  // ── A fixture roundup: masthead, rows and sponsor strip ─────────────────
  {
    const { ctx, page, errors } = await openEditor('?template=FX1')
    // The body box is the one absolutely-positioned block inset 56px a side.
    const BODY = "return [...root.querySelectorAll('div')].find((d) => d.style.left === '56px' && d.style.right === '56px' && d.style.top) || null"
    // The sponsor slots are the only dashed boxes on the post.
    const SLOT = "return [...root.querySelectorAll('div')].find((d) => getComputedStyle(d).borderStyle === 'dashed') || null"
    // A row's opponent name — the biggest thing in a row, and what a reader is
    // scanning for.
    const OPP = "return [...root.querySelectorAll('div')].find((d) => d.children.length === 0 && /SUBIACO/i.test(d.textContent || '')) || null"

    const sqBody = await box(page, BODY)
    const sqSlot = await box(page, SLOT)
    const sqOpp = await box(page, OPP)
    ck('the roundup body, sponsor strip and rows are all measurable', sqBody && sqSlot && sqOpp,
      JSON.stringify({ sqBody, sqSlot, sqOpp }))
    // Pinned so a later change cannot quietly move the square's own design.
    ck('the square masthead is unchanged', sqBody && Math.abs(sqBody.top - (196 / 1080) * 100) < 0.6, String(sqBody?.top))
    ck('the square sponsor slot is unchanged', sqSlot && Math.abs(sqSlot.h - (50 / 1080) * 100) < 0.6, String(sqSlot?.h))
    ck('the square row type is unchanged', sqOpp && Math.abs(sqOpp.font * 10.8 - 31) < 1.2, String(sqOpp && sqOpp.font * 10.8))

    await pickSize(page, 'Portrait')
    await page.waitForTimeout(250)
    const poBody = await box(page, BODY)
    const poSlot = await box(page, SLOT)
    const poOpp = await box(page, OPP)
    // In post pixels: 196 → 239, 50 → 62, 31 → 35.
    ck('the masthead keeps a share of the extra height',
      poBody && poBody.top * 13.5 > sqBody.top * 10.8 + 20, `${sqBody?.top}% -> ${poBody?.top}%`)
    ck('the sponsor strip grows with the post',
      poSlot && poSlot.h * 13.5 > sqSlot.h * 10.8 + 5, `${sqSlot?.h}% -> ${poSlot?.h}%`)
    ck('the row type steps up with the slot it sits in',
      poOpp && poOpp.font * 13.5 > sqOpp.font * 10.8 + 1.5,
      `${sqOpp && Math.round(sqOpp.font * 10.8)}px -> ${poOpp && Math.round(poOpp.font * 13.5)}px`)
    // The body still runs to the sponsor strip rather than stopping short.
    ck('and the body still reaches the sponsor strip',
      poBody && poSlot && poSlot.top - poBody.bottom < 6, `${poBody?.bottom}% .. ${poSlot?.top}%`)

    ck('no page errors measuring the roundup', errors.length === 0, errors.slice(0, 2).join(' | '))
    await ctx.close()
  }

  // ── An event poster: the colour band and the panel under it ─────────────
  // EV2 draws a band whose height follows the canvas and a panel that used to
  // start at a hardcoded 606 — so on a portrait post the two overlapped by
  // 150px and on a story by 340. They have to MEET.
  {
    const { ctx, page } = await openEditor('?template=EV2')
    const BAND = "return [...root.querySelectorAll('div')].find((d) => d.style.top === '0px' && d.style.left === '0px' && d.style.height) || null"
    const PANEL = "return [...root.querySelectorAll('div')].find((d) => d.style.left === '0px' && d.style.bottom === '0px' && d.style.top && d.style.top !== '0px') || null"
    const sqBand = await box(page, BAND)
    const sqPanel = await box(page, PANEL)
    ck('the event band and its panel are measurable', sqBand && sqPanel, JSON.stringify({ sqBand, sqPanel }))
    ck('they meet exactly on the square', sqBand && sqPanel && Math.abs(sqBand.bottom - sqPanel.top) < 0.3,
      `${sqBand?.bottom}% vs ${sqPanel?.top}%`)

    await pickSize(page, 'Portrait')
    await page.waitForTimeout(250)
    const poBand = await box(page, BAND)
    const poPanel = await box(page, PANEL)
    ck('and still meet on a portrait post', poBand && poPanel && Math.abs(poBand.bottom - poPanel.top) < 0.3,
      `${poBand?.bottom}% vs ${poPanel?.top}%`)
    await ctx.close()
  }

  // ── A batting order: the rows fill down to the footer ───────────────────
  // T4 was document flow, so its rows kept the height they had on the square
  // and left a dead strip above the footer on anything taller.
  {
    const { ctx, page } = await openEditor('?template=T4')
    await press(page.getByRole('button', { name: 'Content', exact: true }))
    await page.waitForTimeout(200)
    for (const p of PLAYERS) await press(page.getByRole('button', { name: new RegExp(`^${p.name}\\b`) }))
    await page.waitForTimeout(300)

    // The last row of the order — the row grid is the only block of striped
    // rows, and its last child is what has to reach the bottom.
    // The one flex-1 column in T4 is the rows container. Keyed on that rather
    // than on a child count: the suite seeds TWO players, so a "more than two
    // rows" predicate found nothing and reported the design as unmeasurable.
    const LAST = "const g = [...root.querySelectorAll('div')].find((d) => d.style.flex === '1 1 0%' && d.style.flexDirection === 'column' && d.children.length > 0); return g ? g.lastElementChild : null"
    const sqLast = await box(page, LAST)
    ck('the batting order rows are measurable', sqLast !== null, JSON.stringify(sqLast))

    await pickSize(page, 'Portrait')
    await page.waitForTimeout(250)
    const poLast = await box(page, LAST)
    // Within the footer's own band of the post, not stopping at the square's
    // own last row (which would land around 78%).
    ck('the order runs down to the footer on a portrait post',
      poLast && poLast.bottom > 88, `${poLast?.bottom}%`)
    await ctx.close()
  }
}

// ── 2. The blank canvas is genuinely the new size ──────────────────────────
{
  const { ctx, page, errors } = await openEditor('?type=blank')
  await pickSize(page, 'Portrait')

  const node = await exportNodeBox(page)
  ck('the blank canvas exports at 1080 × 1350', node?.w === 1080 && node?.h === 1350, JSON.stringify(node))

  // A freely-positioned canvas has nothing to place, so it must NOT be framed.
  const framed = await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    return !!holder?.firstElementChild?.querySelector('[data-post-frame]')
  })
  const isPortrait = node?.w === 1080 && node?.h === 1350
  ck('and is not letterboxed — its blocks carry their own coordinates', isPortrait && !framed)

  const saidSo = await page.getByText(/blank canvas is genuinely 1080×1350/i).isVisible().catch(() => false)
  ck('the panel says the canvas is really that size', saidSo)

  ck('no page errors on the blank canvas', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 3. Preview ─────────────────────────────────────────────────────────────
{
  const { ctx, page, errors } = await openEditor()

  ck('a Preview control is offered', await seen(page.getByTestId('open-preview')))
  await press(page.getByTestId('open-preview'))
  await page.waitForTimeout(400)
  const opened = await seen(page.getByTestId('post-preview'))
  ck('Preview opens', opened)
  ck('a single post previews one page', opened && (await page.getByTestId('preview-page').count()) === 1)
  const meta = await textOf(page.getByTestId('preview-meta'))
  ck('the preview names the real size', /1080 × 1080/.test(meta) && /1 page\b/i.test(meta), meta)

  // No editing chrome over the artwork — that is the point of a preview.
  const chrome = await page.evaluate(() => {
    const box = document.querySelector('[data-testid="post-preview"]')
    return box ? box.innerText.includes('DRAG TO MOVE') : true
  })
  ck('the preview carries no editing hints', opened && !chrome)

  await page.keyboard.press('Escape')
  await page.waitForTimeout(200)
  ck('Escape closes it', opened && (await page.getByTestId('post-preview').count()) === 0)

  ck('no page errors in preview', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 4. Preview covers every page of a carousel ─────────────────────────────
{
  const { ctx, page, errors } = await openEditor('?type=blank')
  // Two pages on the blank canvas.
  if (!await press(page.getByTitle('Add a page'))) await press(page.getByRole('button', { name: '+', exact: true }))
  await page.waitForTimeout(200)

  const label = await textOf(page.getByTestId('open-preview'))
  ck('the Preview button counts the pages', /\(2\)/.test(label), label || 'no Preview button')

  await press(page.getByTestId('open-preview'))
  await page.waitForTimeout(400)
  ck('both pages preview at once', (await page.getByTestId('preview-page').count()) === 2)
  const meta = await textOf(page.getByTestId('preview-meta'))
  ck('and the header says how many', /2 pages/i.test(meta), meta)

  ck('no page errors on a carousel preview', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 5. Background removal reachable from any image ─────────────────────────
{
  const { ctx, page, errors } = await openEditor('?type=blank')

  await press(page.getByRole('button', { name: 'Photos', exact: true }))
  await page.waitForTimeout(200)

  ck('the club library is named in the Photos panel',
    await page.getByText('Club library', { exact: true }).isVisible().catch(() => false))
  const panelMeta = await textOf(page.locator('aside'))
  ck('the panel header points at it too', /CLUB LIBRARY/i.test(panelMeta), panelMeta.slice(0, 80))

  // Each library image can be cleaned up without leaving the editor.
  const tileEdit = page.getByRole('button', { name: 'Edit', exact: true })
  ck('a library image offers Edit', (await tileEdit.count()) > 0)
  try { await tileEdit.first().click({ force: true }) } catch { /* reported below */ }
  await page.waitForTimeout(500)
  const bgTool = await page.getByText(/Remove background \(logo\)/i).isVisible().catch(() => false)
  ck('Edit opens the background remover', bgTool)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(200)

  // And the image already sitting on the post, which is where somebody who has
  // just uploaded a white-backgrounded PNG actually is.
  await press(page.getByRole('button', { name: /team-photo/ }))
  await page.waitForTimeout(300)
  const inspectorEdit = page.getByRole('button', { name: 'Edit', exact: true })
  try { if (await inspectorEdit.count()) await inspectorEdit.last().click() } catch { /* reported below */ }
  await page.waitForTimeout(500)
  const bgTool2 = await page.getByText(/Remove background \(logo\)/i).isVisible().catch(() => false)
  ck('an image on the canvas can be edited in place', bgTool2)

  ck('no page errors around the image editor', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 6. The four explanations ───────────────────────────────────────────────
{
  const { ctx, page, errors } = await openEditor()

  // Layers: what Forward/Backward can and cannot reach on a fixed layout.
  await press(page.getByRole('button', { name: 'Layers', exact: true }))
  await page.waitForTimeout(200)
  const note = await textOf(page.getByTestId('layers-template-note'))
  ck('the Layers panel says a block can sit among the layout\'s own elements',
    /between two of them/i.test(note), note.slice(0, 140))
  ck('and that the background stays at the floor', /background stays/i.test(note), note.slice(0, 140))

  // Hero: which layouts have the slot, rather than the section just vanishing.
  await press(page.getByRole('button', { name: 'Content', exact: true }))
  await page.waitForTimeout(200)
  const heroPanel = await page.getByText('Hero Image', { exact: false }).first().isVisible().catch(() => false)
  ck('a hero layout offers the Hero Image slot', heroPanel)

  await ctx.close()

  // A layout with no hero slot names the ones that have it.
  const b = await openEditor('?type=fixtures')
  await press(b.page.getByRole('button', { name: 'Content', exact: true }))
  await b.page.waitForTimeout(200)
  const unavailable = await textOf(b.page.getByTestId('hero-unavailable'))
  ck('a layout without one says which layouts have it', /has no hero slot/i.test(unavailable), unavailable.slice(0, 90))
  ck('and names at least one by name', /Hero List/.test(unavailable), unavailable.slice(0, 120))
  await b.ctx.close()

  ck('no page errors reading the explanations', errors.length === 0, errors.slice(0, 2).join(' | '))
}

// ── 7. Saving says where it went ───────────────────────────────────────────
{
  const { ctx, page, errors } = await openEditor()

  await press(page.getByRole('button', { name: 'SAVE AS TEMPLATE' }))
  await page.waitForTimeout(300)
  const tplNote = await textOf(page.getByTestId('saved-note'))
  ck('saving a template says where it went', /Your templates/i.test(tplNote), tplNote.slice(0, 90))
  ck('and that it is on this browser only', /this browser/i.test(tplNote), tplNote.slice(0, 90))

  ck('no page errors while saving', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 7b. Every element of a layout is a layer ───────────────────────────────
// The layout's own elements are in the stack alongside the blocks somebody
// adds, so a block can sit BETWEEN two of them. Measured off the off-screen
// export node, because that is what the downloaded PNG is captured from — the
// canvas agreeing with itself proves nothing about the file.
{
  const { ctx, page, errors } = await openEditor()

  // The layout root inside the export node, and its layers in paint order.
  // A run of blocks carries `data-testid="post-blocks"`; the layout's own DOM
  // children carry the id the panel lists them under.
  const stackOf = () => page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find(
      (d) => d.style.left === '-9999px' && d.style.position === 'absolute',
    )
    const page_ = holder?.firstElementChild
    if (!page_) return null
    const root = [...page_.children].find((c) => c.tagName === 'DIV' && c.style.width && c.children.length > 1)
    if (!root) return null
    return [...root.children]
      .map((c) => ({
        z: Number(c.style.zIndex) || 0,
        kind: c.getAttribute('data-testid') === 'post-blocks' ? 'blocks' : 'layout',
        id: c.getAttribute('data-layer-id') || '',
      }))
      .sort((a, b) => a.z - b.z)
  })
  // The layout root's own background, which is the floor rather than a layer.
  // Most of these layouts paint a GRADIENT (background-image), so reading the
  // colour alone would report every one of them transparent.
  const rootBg = () => page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find(
      (d) => d.style.left === '-9999px' && d.style.position === 'absolute',
    )
    const page_ = holder?.firstElementChild
    const root = page_ && [...page_.children].find((c) => c.tagName === 'DIV' && c.style.width && c.children.length > 1)
    if (!root) return null
    const s = getComputedStyle(root)
    return { color: s.backgroundColor, image: s.backgroundImage }
  })
  const paints = (v) => !!v && ((v.color && v.color !== 'rgba(0, 0, 0, 0)' && v.color !== 'transparent') || (v.image && v.image !== 'none'))

  const rowIds = () => page.evaluate(() => [...document.querySelectorAll('[data-layer-id]')]
    .filter((r) => r.getAttribute('data-testid')?.startsWith('layer-row-'))
    .map((r) => ({ id: r.getAttribute('data-layer-id'), kind: r.getAttribute('data-testid'), label: (r.innerText || '').trim() })))

  await press(page.getByRole('button', { name: 'Layers', exact: true }))
  await page.waitForTimeout(300)
  const beforeAdd = await rowIds()
  ck('a layout lists its own elements as layers',
    beforeAdd.filter((r) => r.kind === 'layer-row-template').length >= 3,
    JSON.stringify(beforeAdd.map((r) => r.label)).slice(0, 160))
  ck('and they are named rather than numbered',
    beforeAdd.some((r) => r.kind === 'layer-row-template' && r.label && !/^Element \d+$/.test(r.label)),
    JSON.stringify(beforeAdd.map((r) => r.label)).slice(0, 160))
  ck('the background is shown as the floor, not a layer', await seen(page.getByTestId('layers-background-row')))

  // Adding a block on a real layout turns Custom Edit on by itself — the exact
  // path somebody takes when they drop an image onto a lineup post.
  await press(page.getByRole('button', { name: 'Photos', exact: true }))
  await page.waitForTimeout(250)
  await press(page.getByRole('button', { name: /Empty image frame/i }))
  await page.waitForTimeout(400)

  const before = await stackOf()
  const blockAt = (st) => (st || []).findIndex((l) => l.kind === 'blocks')
  ck('a new block starts in front of the whole layout',
    Array.isArray(before) && blockAt(before) === before.length - 1, JSON.stringify(before))
  const bgBefore = await rootBg()
  ck('the layout paints its own background', paints(bgBefore), JSON.stringify(bgBefore))

  // Send to back: under every one of the layout's own elements.
  await press(page.getByRole('button', { name: 'Send to back' }))
  await page.waitForTimeout(400)
  const back = await stackOf()
  ck('Send to back puts it under every element of the layout',
    Array.isArray(back) && blockAt(back) === 0, JSON.stringify(back))

  // THE BACKGROUND STAYS. It is the floor, so a block at the bottom of the
  // stack sits ON it rather than the layout being made see-through.
  const bgBack = await rootBg()
  ck('the background still paints under a block sent to the back', paints(bgBack), JSON.stringify(bgBack))

  // The point of the whole change: one step forward and the block is BETWEEN
  // two of the layout's own elements, with a layout element on either side.
  await press(page.getByRole('button', { name: 'Layers', exact: true }))
  await page.waitForTimeout(250)
  const rows = await rowIds()
  const blockRow = rows.find((r) => r.kind === 'layer-row-block')
  ck('the block is listed in the same stack as the layout', !!blockRow, JSON.stringify(rows.map((r) => r.kind)))
  // Rows read front-first, so Forward on the block is the ⇧ button in its row.
  await press(page.locator(`[data-layer-id="${blockRow?.id}"] button[title="Forward"]`))
  await page.waitForTimeout(400)
  const mid = await stackOf()
  const i = blockAt(mid)
  ck('one step forward puts the block between two of the layout\'s own elements',
    i > 0 && i < (mid?.length ?? 0) - 1 && mid[i - 1].kind === 'layout' && mid[i + 1].kind === 'layout',
    JSON.stringify(mid))

  ck('no page errors moving a block through the stack', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 7c. Hiding one of the layout's own elements ────────────────────────────
{
  const { ctx, page, errors } = await openEditor()
  await press(page.getByRole('button', { name: 'Layers', exact: true }))
  await page.waitForTimeout(300)

  const countLayers = () => page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find(
      (d) => d.style.left === '-9999px' && d.style.position === 'absolute',
    )
    const page_ = holder?.firstElementChild
    const root = page_ && [...page_.children].find((c) => c.tagName === 'DIV' && c.style.width && c.children.length > 1)
    return root ? root.children.length : -1
  })
  const before = await countLayers()
  ck('the export node draws the layout\'s elements', before > 2, String(before))

  await press(page.locator('[data-testid="layer-hide"]').first())
  await page.waitForTimeout(400)
  const after = await countLayers()
  ck('hiding an element takes it off the exported post', after === before - 1, `${before} -> ${after}`)

  // And it says so in the list rather than the row simply disappearing.
  const hiddenRow = await page.locator('[data-testid="layer-row-template"] .line-through').count().catch(() => 0)
  ck('the hidden element is still listed, struck through', hiddenRow >= 1, String(hiddenRow))

  // Putting it back is the same control.
  await press(page.locator('[data-testid="layer-hide"]').first())
  await page.waitForTimeout(400)
  ck('showing it again puts it back', (await countLayers()) === before, String(await countLayers()))

  ck('no page errors hiding an element', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 7d. The blank canvas has no layout ─────────────────────────────────────
{
  const b = await openEditor('?type=blank')
  await press(b.page.getByRole('button', { name: 'Layers', exact: true }))
  await b.page.waitForTimeout(300)
  ck('the blank canvas shows no layout background row', !(await seen(b.page.getByTestId('layers-background-row'))))
  ck('and no layout elements in its stack',
    (await b.page.locator('[data-testid="layer-row-template"]').count()) === 0)
  await b.ctx.close()
}

// ── 7e. A saved template keeps its stacking ────────────────────────────────
// The whole point of saving a design is getting it back. Driven through a real
// RELOAD in one context, because that is the round trip somebody makes: save,
// come back later, apply it. A second context would have its own localStorage
// and the check would be measuring the harness.
{
  const { ctx, page, errors } = await openEditor()
  const countLayers = () => page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find(
      (d) => d.style.left === '-9999px' && d.style.position === 'absolute',
    )
    const page_ = holder?.firstElementChild
    const root = page_ && [...page_.children].find((c) => c.tagName === 'DIV' && c.style.width && c.children.length > 1)
    return root ? root.children.length : -1
  })

  await press(page.getByRole('button', { name: 'Layers', exact: true }))
  await page.waitForTimeout(300)
  const drawn = await countLayers()
  await press(page.locator('[data-testid="layer-hide"]').first())
  await page.waitForTimeout(400)
  const hiddenCount = await countLayers()
  ck('a hidden element is off the post before saving', hiddenCount === drawn - 1, `${drawn} -> ${hiddenCount}`)

  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await page.waitForTimeout(250)
  await page.getByPlaceholder('Template name...').fill('Stacked')
  await press(page.getByRole('button', { name: 'Save current' }))
  await page.waitForTimeout(400)

  // Come back to it. A reload clears every bit of in-memory state, so what the
  // stack reads afterwards can only have come from the saved template.
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  await page.waitForTimeout(600)
  ck('a fresh load draws the layout whole again', (await countLayers()) === drawn, String(await countLayers()))

  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await page.waitForTimeout(250)
  await press(page.getByRole('button', { name: 'Stacked' }))
  await page.waitForTimeout(600)
  ck('applying the saved template brings its stacking back',
    (await countLayers()) === drawn - 1, `${drawn} -> ${await countLayers()}`)

  ck('no page errors saving and re-applying a template', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 8. Narrow viewport ─────────────────────────────────────────────────────
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(url)) return json({ id: 'u1', role: 'club_admin', entitlements: { modules: ['socials'], status: 'active' } })
    if (/\/club-admin\/settings/.test(url)) return json(SETTINGS)
    if (/\/club-admin\/players/.test(url)) return json(PLAYERS)
    if (/social\/media/.test(url)) return json([])
    return json({})
  })
  await page.goto(`${BASE}/admin/social-post?type=lineup`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', overflow <= 0, `overflow ${overflow}px`)
  ck('no page errors on a phone', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
