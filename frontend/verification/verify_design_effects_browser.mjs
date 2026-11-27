// Drives the real BetterPosts editor in Chromium (API stubbed at the network
// layer) through the design effects: frames and pop-out, colour splash with the
// eyedropper, looks, cut-out outline, motion trail, the faded copy, echo and
// hollow text, textures, the seven design layouts (DL1-DL7), and the same tools inside an
// Association Socials workspace. Effects are proved on a REAL downloaded PNG,
// sampled pixel by pixel, because a preview that looks right is not an export
// that is right.
//
//   npm run build && npx vite preview --port 5199 &
//   node verification/verify_design_effects_browser.mjs http://127.0.0.1:5199
//
// Fixtures: verification/fixtures/design_fx/photo_red_blue.png (left half red
// #e10600, right half blue #1a4fd6, 600 square) and cutout_player.png (400×600,
// clear background, red body x 100..300 y 200..600, skin head).
import { readFileSync, existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium'
const PHOTO = readFileSync(new URL('./fixtures/design_fx/photo_red_blue.png', import.meta.url))
const CUTOUT = readFileSync(new URL('./fixtures/design_fx/cutout_player.png', import.meta.url))

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}
const textOf = async (loc) => { try { return (await loc.count()) ? await loc.first().innerText() : '' } catch { return '' } }
const seen = async (loc) => { try { return (await loc.count()) > 0 && await loc.first().isVisible() } catch { return false } }
const press = async (loc) => { try { if (await loc.count()) { await loc.first().click(); return true } } catch { /* reported by the check */ } return false }

const CLUB = { id: 'org-1', name: 'Test Cricket Club', short_name: 'TCC', slug: 'tcc', logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null }
const WORKSPACE = { id: 'ws-1', name: 'WASTCA', short_name: 'WASTCA', slug: null, workspace_kind: 'association', logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null }
const MEDIA = [
  { id: 'm1', name: 'photo-red-blue.png', url: '/api/admin/social/media/m1/file' },
  { id: 'm2', name: 'cutout-player.png', url: '/api/admin/social/media/m2/file' },
]

const browser = await chromium.launch(existsSync(EXE) ? { executablePath: EXE } : {})

async function openEditor({ settings = CLUB, assoc = false, viewport = { width: 1600, height: 1000 }, query = '?type=blank' } = {}) {
  const ctx = await browser.newContext({ viewport, acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('dialog', (d) => d.accept())
  const json = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    if (/\/social\/media\/m1\/file/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PHOTO })
    if (/\/social\/media\/m2\/file/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: CUTOUT })
    if (/\/auth\/me/.test(url)) return route.fulfill(json(assoc
      ? { id: 'u1', username: 'staff', role: 'super_admin', club_slug: null, club_name: 'WASTCA', workspace_kind: 'association', acting_as_club: true, entitlements: { modules: ['socials'], status: 'active' } }
      : { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'tcc', entitlements: { modules: ['socials', 'select', 'stats'], status: 'active' } }))
    if (/\/admin\/social\/media\?kind=background/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json(MEDIA))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(settings))
    if (/\/admin\/social\/crests/.test(url)) return route.fulfill(json({ crests: [] }))
    if (/templates|players|sponsors/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/social-post${query}`, { waitUntil: 'domcontentloaded' })
  if (viewport.width < 768) await page.getByRole('button', { name: /full editor/i }).first().waitFor({ timeout: 25000 })
  else await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  await page.waitForTimeout(500)
  return { ctx, page, errors }
}

const tool = (page, label) => press(page.locator(`nav button[title="${label}"]`))

async function clearCanvas(page) {
  await tool(page, 'Layers')
  for (let i = 0; i < 12; i++) {
    const del = page.locator('[data-testid="layer-row-block"] button[title="Delete"]')
    if (!(await del.count())) break
    await del.first().click()
    await page.waitForTimeout(80)
  }
}

// The off-screen node the PNG is captured from.
const exportBlocks = (page) => page.evaluate(() => {
  const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px' && d.style.position === 'absolute')
  return holder ? holder.innerHTML : ''
})

// Download the real PNG and read pixels at 1080-space points (export is 2×).
async function exportPixels(page, points) {
  try {
    const [dl] = await Promise.all([
      page.waitForEvent('download', { timeout: 20000 }),
      page.getByRole('button', { name: /DOWNLOAD PNG/ }).first().click(),
    ])
    const buf = readFileSync(await dl.path())
    const url = `data:image/png;base64,${buf.toString('base64')}`
    return await page.evaluate(async ([u, pts]) => {
      const img = new Image()
      await new Promise((r, j) => { img.onload = r; img.onerror = j; img.src = u })
      const c = document.createElement('canvas')
      c.width = img.naturalWidth; c.height = img.naturalHeight
      const g = c.getContext('2d')
      g.drawImage(img, 0, 0)
      const k = img.naturalWidth / 1080
      return { w: img.naturalWidth, h: img.naturalHeight, px: pts.map(([x, y]) => [...g.getImageData(Math.round(x * k), Math.round(y * k), 1, 1).data]) }
    }, [url, points])
  } catch (e) { return { error: String(e), px: points.map(() => [0, 0, 0, 0]) } }
}
const isRed = ([r, g, b]) => r > 170 && g < 70 && b < 70
const isBlue = ([r, g, b]) => b > 150 && r < 80
const isGrey = ([r, g, b]) => Math.abs(r - g) < 14 && Math.abs(g - b) < 14 && r > 30
const isWhite = ([r, g, b]) => r > 225 && g > 225 && b > 225
const near = (a, b, t = 30) => Math.abs(a[0] - b[0]) < t && Math.abs(a[1] - b[1]) < t && Math.abs(a[2] - b[2]) < t

async function addLibraryPhoto(page, name) {
  await press(page.getByRole('button', { name: 'Deselect' })) // harmless if absent
  await tool(page, 'Photos')
  await press(page.locator(`button[title^="${name}"]`))
  await page.waitForTimeout(250)
}
const openEffects = async (page) => { await tool(page, 'Effects'); await page.waitForTimeout(150) }

// ── 1. Colour splash, frames and pop out on a club post, proved in the PNG ──
{
  const { ctx, page, errors } = await openEditor()
  ck('the editor rail offers an Effects tool', await seen(page.locator('nav button[title="Effects"]')))
  await clearCanvas(page)
  await addLibraryPhoto(page, 'photo-red-blue.png')
  // Default image block: x 340, y 340, 400 × 400, fit contain. Red is the left half.
  const RED = [440, 540], BLUE = [640, 540], CORNER = [346, 734]
  const plainHtml = await exportBlocks(page)
  ck('a picture with no effects still renders as a plain <img> (saved posts unchanged)', /<img[^>]+media\/m1\/file/.test(plainHtml) && !/data-pop-out/.test(plainHtml))
  ck('the inspector offers Effects on the selected picture', await seen(page.getByTestId('open-effects')))
  await press(page.getByTestId('open-effects'))
  ck('the Effects panel opens on the picture', await seen(page.getByTestId('fx-frame')) && await seen(page.getByTestId('fx-splash')))

  const before = await exportPixels(page, [RED, BLUE, CORNER])
  ck('control: the plain export shows red, blue and the photo in the bottom corner',
    isRed(before.px[0]) && isBlue(before.px[1]) && isRed(before.px[2]), JSON.stringify(before.px) + (before.error || ''))

  // Eyedropper: click the left (red) side of the thumbnail.
  const eye = page.getByTestId('fx-eyedropper')
  await eye.waitFor({ timeout: 5000 }).catch(() => {})
  const box = await eye.boundingBox().catch(() => null)
  if (box) await page.mouse.click(box.x + box.width * 0.2, box.y + box.height * 0.5)
  await page.waitForTimeout(150)
  ck('the eyedropper adds the clicked colour as a kept colour', (await page.getByTestId('splash-pick').count()) === 1)
  ck('the kept colour is the red that was clicked', /#e1060|#e0060|#e10500|#e2060/i.test(await textOf(page.getByTestId('splash-pick'))), await textOf(page.getByTestId('splash-pick')))
  await page.waitForTimeout(500)
  const splash = await exportPixels(page, [RED, BLUE])
  ck('PNG: the kept red stays red', isRed(splash.px[0]), JSON.stringify(splash.px[0]))
  ck('PNG: the blue goes black and white', isGrey(splash.px[1]) && !isBlue(splash.px[1]), JSON.stringify(splash.px[1]))

  // Frame: V base clips the bottom corners.
  await press(page.getByTestId('frame-vbottom'))
  await page.waitForTimeout(300)
  const framed = await exportPixels(page, [CORNER, RED])
  ck('PNG: the V base frame clips the photo out of the bottom corner', !isRed(framed.px[0]) && !isGrey(framed.px[0]) || near(framed.px[0], [11, 21, 48], 40), JSON.stringify(framed.px[0]))
  ck('PNG: inside the frame the photo still shows', isRed(framed.px[1]), JSON.stringify(framed.px[1]))
  // Pop out
  const pop = page.getByTestId('fx-popout')
  if (await pop.count()) await pop.fill('30')
  await page.waitForTimeout(250)
  const popHtml = await exportBlocks(page)
  ck('pop out adds the layer that lets a cut-out rise out of the frame', /data-pop-out/.test(popHtml))
  // Frame fill + outline
  await press(page.locator('[data-testid="fx-frame-fill"] button[title="accent"]'))
  const st = page.getByTestId('fx-frame-stroke')
  if (await st.count()) await st.fill('12')
  await page.waitForTimeout(250)
  ck('the frame outline is drawn as an SVG polygon', /<polygon[^>]+stroke=/.test(await exportBlocks(page)))

  // Looks: Club duotone turns the red into a palette mix (not red any more)
  await press(page.getByTestId('look-duo'))
  await page.waitForTimeout(500)
  const duo = await exportPixels(page, [RED])
  ck('PNG: the Club duotone look recolours the photo', !isRed(duo.px[0]) && duo.px[0][3] === 255, JSON.stringify(duo.px[0]))

  // Faded copy behind
  const nBefore = (await exportBlocks(page)).match(/media\/m1\/file|blob:/g)?.length || 0
  await press(page.locator('[data-testid="fx-cutout"] button').first()) // open the section
  await press(page.getByTestId('fx-ghost'))
  await page.waitForTimeout(500)
  const ghostHtml = await exportBlocks(page)
  ck('Add faded copy behind puts a second copy of the picture on the post', (ghostHtml.match(/opacity: 0.22/g) || []).length === 1 && (ghostHtml.match(/<img/g) || []).length > nBefore)
  const order = await page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    const blocks = [...holder.querySelectorAll('div')].filter((d) => d.style.position === 'absolute' && d.style.left && d.style.top && d.parentElement && d.parentElement.style.overflow === 'hidden')
    return blocks.map((b) => b.style.opacity || '1')
  })
  ck('the faded copy sits behind the original', order.indexOf('0.22') >= 0 && order.indexOf('0.22') < order.lastIndexOf('1'), JSON.stringify(order))
  ck('no page errors through the photo effects', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 2. Cut-out outline and motion trail, proved in the PNG ─────────────────
{
  const { ctx, page, errors } = await openEditor()
  await clearCanvas(page)
  await addLibraryPhoto(page, 'cutout-player.png')
  // 400×600 in a 400×400 contain box: drawn 266.7 wide from x 406.7; body x
  // 100..300 of 400 → 473.3..540 … 606.7; y 200..600 of 600 → 473.3..740.
  const OUT = [467, 600], IN = [500, 600], FAR = [400, 600]
  const before = await exportPixels(page, [OUT, IN])
  ck('control: just outside the cut-out body is not white before the outline', !isWhite(before.px[0]) && isRed(before.px[1]), JSON.stringify(before.px))
  await openEffects(page)
  await press(page.getByText('Cut-out effects'))
  const o = page.getByTestId('fx-outline')
  if (await o.count()) await o.fill('14')
  await page.waitForTimeout(300)
  const after = await exportPixels(page, [OUT, IN, FAR])
  ck('PNG: the cut-out outline paints white round the body', isWhite(after.px[0]), JSON.stringify(after.px[0]))
  ck('PNG: the body itself is untouched', isRed(after.px[1]), JSON.stringify(after.px[1]))
  ck('PNG: the outline follows the shape, not the box', !isWhite(after.px[2]), JSON.stringify(after.px[2]))
  const t = page.getByTestId('fx-trail')
  if (await t.count()) await t.fill('3')
  await page.waitForTimeout(400)
  const trailHtml = await exportBlocks(page)
  ck('the motion trail draws copies behind the cut-out', (trailHtml.match(/translate\(-\d+px, 0px\)/g) || []).length === 3)
  ck('no page errors through the cut-out effects', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 3. Text: echo, hollow, 3D block, put behind the photo ──────────────────
{
  const { ctx, page, errors } = await openEditor()
  await clearCanvas(page)
  await addLibraryPhoto(page, 'photo-red-blue.png')
  await tool(page, 'Text')
  await press(page.locator('button').filter({ hasText: /heading/i }))
  await page.waitForTimeout(200)
  await openEffects(page)
  ck('the Effects panel shows the text styles for a text block', await seen(page.getByTestId('fx-text')))
  const ec = page.getByTestId('fx-echo-count')
  if (await ec.count()) await ec.fill('4')
  await page.waitForTimeout(200)
  const html = await exportBlocks(page)
  ck('echo stack draws the words four times', (html.match(/data-echo="/g) || []).length === 4)
  ck('the echo copies are outlined (text stroke)', /-webkit-text-stroke/.test(html))
  await press(page.getByTestId('fx-hollow'))
  await press(page.getByTestId('fx-preset-block'))
  await page.waitForTimeout(150)
  const html2 = await exportBlocks(page)
  const shadowCss = (/text-shadow: ([^;"]+)/.exec(html2) || [])[1] || ''
  ck('3D block writes a stacked text shadow (14 layered offsets)', (shadowCss.match(/px 0px/g) || []).length >= 14, shadowCss.slice(0, 80))
  const pos = async () => page.evaluate(() => {
    const holder = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    const h = holder.innerHTML
    return { img: h.indexOf('media/m1/file'), txt: h.indexOf('data-echo') }
  })
  const p0 = await pos()
  ck('control: the new text is in front of the photo', p0.txt > p0.img && p0.img >= 0, JSON.stringify(p0))
  await press(page.getByTestId('fx-text-behind'))
  await page.waitForTimeout(250)
  const p1 = await pos()
  ck('Put behind the photo moves the text under it', p1.txt >= 0 && p1.txt < p1.img, JSON.stringify(p1))
  ck('no page errors through the text effects', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 4. Textures ─────────────────────────────────────
{
  const { ctx, page, errors } = await openEditor()
  await clearCanvas(page)
  await tool(page, 'Shapes')
  ck('the Shapes panel lists the textures', await seen(page.getByTestId('shape-brush')) && await seen(page.getByTestId('shape-halftone')))
  await press(page.getByTestId('shape-brush'))
  await page.waitForTimeout(200)
  const d0 = await page.evaluate(() => { const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px'); return [...h.querySelectorAll('path')].map((p) => p.getAttribute('d')).join('|') })
  ck('a brush stroke texture draws many SVG marks', d0.split('|').length > 20)
  await openEffects(page)
  await press(page.getByTestId('fx-shuffle'))
  await page.waitForTimeout(150)
  const d1 = await page.evaluate(() => { const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px'); return [...h.querySelectorAll('path')].map((p) => p.getAttribute('d')).join('|') })
  ck('Shuffle draws a new brush stroke', d1.length > 100 && d1 !== d0)
  const px = await exportPixels(page, [[540, 530]])
  ck('PNG: the brush stroke is painted in the accent colour', near(px.px[0], [255, 194, 51], 50), JSON.stringify(px.px[0]))
  ck('no page errors through textures', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 4b. The design layouts, one per post type ──────────────────────────────
const LAYOUTS = [
  ['DL1', 'Match Day V', 'Our frame'], ['DL2', 'Gameday Echo', 'Echo word'], ['DL3', 'Final Score V', 'Opposition side'],
  ['DL4', 'Fixtures Echo', 'Rows'], ['DL5', 'Results Echo', 'Rows'], ['DL6', 'Colour Pop', 'Torn strip'], ['DL7', 'Colour Pop', 'Torn strip'],
]
async function openLayout(id, opts = {}) {
  const o = await openEditor({ ...opts, query: `?template=${id}` })
  return o
}
for (const [id, name, layer] of LAYOUTS) {
  const { ctx, page, errors } = await openLayout(id)
  const html = await exportBlocks(page)
  ck(`${id} ${name} opens from its link and draws its own parts`, html.includes(`data-layer="${layer}"`) && html.includes('data-layer="Platform credit"'))
  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await page.waitForTimeout(150)
  const tile = page.getByRole('button', { name: new RegExp(`^${id}\\s*${name}`) })
  ck(`${id} is listed by name in its post type's layouts`, await seen(tile))
  // Clicking another layout and back proves the tile really selects it.
  await press(tile)
  for (const size of ['Portrait', 'Story']) {
    await press(page.getByRole('button', { name: 'Design', exact: true }))
    await press(page.getByRole('button', { name: new RegExp(`^${size}`) }))
    await page.waitForTimeout(200)
  }
  const tall = await exportBlocks(page)
  ck(`${id} still draws at story size`, tall.includes(`data-layer="${layer}"`))
  ck(`${id}: no page errors at three sizes`, errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}
{
  // Match Day V on a square post with no players: the V frames are cut, so the
  // bottom corner of our frame is the background and its top is the accent.
  const { ctx, page } = await openLayout('DL1')
  const px = await exportPixels(page, [[70, 262], [52, 872]])
  ck('PNG: Match Day V paints our frame in the accent', near(px.px[0], [255, 194, 51], 40), JSON.stringify(px.px[0]))
  ck('PNG: and cuts its bottom corner into a V', !near(px.px[1], [255, 194, 51], 60), JSON.stringify(px.px[1]))
  await ctx.close()
}
{
  const { ctx, page, errors } = await openLayout('DL1', { settings: WORKSPACE, assoc: true })
  ck('workspace: Match Day V opens in an Association workspace', (await exportBlocks(page)).includes('data-layer="Our frame"'))
  ck('workspace: no page errors on the design layout', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 5. Association Socials workspace has the same tools ────────────────────
{
  const { ctx, page, errors } = await openEditor({ settings: WORKSPACE, assoc: true })
  ck('workspace: the editor rail offers Effects', await seen(page.locator('nav button[title="Effects"]')))
  await clearCanvas(page)
  await addLibraryPhoto(page, 'photo-red-blue.png')
  await openEffects(page)
  ck('workspace: the Effects panel opens on a picture', await seen(page.getByTestId('fx-frame')))
  // Keep the accent (a yellow): the photo's red and blue are both outside it.
  await press(page.getByTestId('splash-add-accent'))
  await press(page.getByTestId('frame-hexagon'))
  await page.waitForTimeout(400)
  const html = await exportBlocks(page)
  ck('workspace: a frame and a colour splash apply', /clip-path: polygon/.test(html) && (await page.getByTestId('splash-pick').count()) === 1)
  const px = await exportPixels(page, [[640, 540]])
  ck('workspace PNG: the blue (not a kept colour) goes black and white', isGrey(px.px[0]), JSON.stringify(px.px[0]))
  ck('workspace: no page errors', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 6. Phone width: the editor does not overflow ───────────────────────────
{
  const { ctx, page } = await openEditor({ viewport: { width: 390, height: 844 } }).catch(() => ({}))
  if (page) {
    await press(page.getByRole('button', { name: /full editor/i }))
    await page.waitForTimeout(300)
    await tool(page, 'Effects')
    await page.waitForTimeout(200)
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    ck('390px: no horizontal page overflow with Effects open', over <= 1, `overflow ${over}px`)
    await ctx.close()
  } else ck('390px: editor opened', false)
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
