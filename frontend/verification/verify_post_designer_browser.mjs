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
  { id: 'p1', name: 'Jack Barendse', display_name: 'Jack Barendse', status: 'active', photo_url: null },
  { id: 'p2', name: 'Sam Alborn', display_name: 'Sam Alborn', status: 'active', photo_url: null },
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

  // A fixed 1080×1080 layout must be PLACED into the taller canvas, not
  // stretched: measured off the real element, not inferred from the code.
  const fitGeom = await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    const node = holder?.firstElementChild
    const framed = node?.querySelector('[data-post-frame]')
    if (!framed) return null
    const m = /scale\(([\d.]+)\)/.exec(framed.style.transform || '')
    return { scale: m ? parseFloat(m[1]) : null, top: parseFloat(framed.style.top), width: parseFloat(framed.style.width) }
  })
  ck('the layout is placed whole, not stretched', fitGeom && fitGeom.scale === 1 && fitGeom.width === 1080, JSON.stringify(fitGeom))
  ck('and centred, so the bands are even', fitGeom && Math.abs(fitGeom.top - 135) < 0.6, JSON.stringify(fitGeom))

  const fitExplained = await page.getByText(/sits whole on the portrait canvas/i).isVisible().catch(() => false)
  ck('the letterbox is explained rather than left to look broken', fitExplained)

  // Fill scales the layout up to cover, cropping the edges.
  await press(page.getByRole('button', { name: 'Fill & crop' }))
  await page.waitForTimeout(150)
  const fillGeom = await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    const framed = holder?.firstElementChild?.querySelector('[data-post-frame]')
    const m = /scale\(([\d.]+)\)/.exec(framed?.style.transform || '')
    return { scale: m ? parseFloat(m[1]) : null, left: parseFloat(framed?.style.left) }
  })
  ck('Fill covers the canvas', fillGeom && Math.abs(fillGeom.scale - 1.25) < 0.001, JSON.stringify(fillGeom))
  ck('Fill crops evenly on both sides', fillGeom && Math.abs(fillGeom.left + 135) < 0.6, JSON.stringify(fillGeom))

  await pickSize(page, 'Story')
  const storyCap = await captionOf(page)
  ck('Story is 1080 × 1920', /1080 × 1920/.test(storyCap), storyCap)

  ck('no page errors while resizing', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 1b. The letterbox bands, and where the picker does NOT belong ──────────
{
  const { ctx, page } = await openEditor()
  await pickSize(page, 'Portrait')

  // Left at the canvas well's near-black the bands read as an unfinished
  // export; they carry the club's own colour instead. Read off the real
  // element rather than the source.
  const fill = await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    const node = holder?.firstElementChild
    return node ? getComputedStyle(node).backgroundColor : null
  })
  const opaque = fill && fill !== 'rgba(0, 0, 0, 0)' && fill !== 'transparent'
  ck('the fitted bands carry a colour, not the well', opaque, String(fill))
  ck('and it is the club palette, not black', opaque && fill !== 'rgb(8, 8, 8)' && fill !== 'rgb(0, 0, 0)', String(fill))

  await ctx.close()

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
  ck('the Layers panel explains a built-in layout', /sit on top of it/i.test(note), note.slice(0, 90))
  ck('and offers the way out', /Blank canvas|movable blocks/i.test(note), note.slice(0, 90))

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
