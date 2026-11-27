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

// ── 0. Colour splash sliders respond across their whole range ──────────────
// STRUCTURAL: the pixel pass itself, on a red kit's highlight and shadow and an
// orange neighbour. Range must keep widening past 10, and Softness must matter.
{
  const { applyPixels } = await import(new URL('../src/social/designFx.js', import.meta.url))
  const kept = (rgb, range, soft) => {
    const d = new Uint8ClampedArray([...rgb, 255])
    applyPixels(d, { tone: 'mono', splash: [{ color: '#c8141e', range, soft }] })
    const ch = (x) => Math.max(x[0], x[1], x[2]) - Math.min(x[0], x[1], x[2])
    return ch(d) / Math.max(1, ch(rgb))
  }
  const hi = [240, 112, 112], shadow = [90, 10, 10], orange = [232, 112, 26], blue = [26, 79, 214]
  ck('splash: Range 10 keeps less of the kit highlight than Range 30', kept(hi, 10, 0) < 0.5 && kept(hi, 30, 0) > 0.5)
  ck('splash: Range 45 brings in the kit shadow that Range 30 left out', kept(shadow, 30, 0) < 0.5 && kept(shadow, 45, 0) > 0.5)
  ck('splash: Range keeps growing to the top (orange by 60, never blue below 90)', kept(orange, 60, 0) > 0.9 && kept(blue, 80, 0) < 0.1)
  ck('splash: Softness fades in what is just outside the range', kept(shadow, 20, 0) < 0.1 && kept(shadow, 20, 100) > 0.5)
}

const browser = await chromium.launch(existsSync(EXE) ? { executablePath: EXE } : {})

const ROSTER = Array.from({ length: 6 }, (_, i) => ({ id: `p${i + 1}`, name: `Sam Player${i + 1}`, display_name: `Sam Player${i + 1}`, status: 'active', photo_url: `/api/images/players/p${i + 1}/photo` }))
async function openEditor({ settings = CLUB, assoc = false, viewport = { width: 1600, height: 1000 }, query = '?type=blank', roster = [] } = {}) {
  const ctx = await browser.newContext({ viewport, acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = []
  const writes = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('dialog', (d) => d.accept())
  const json = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    if (route.request().method() !== 'GET') writes.push({ url, method: route.request().method(), body: route.request().postData() })
    if (/\/social\/media\/m1\/file/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PHOTO })
    if (/\/social\/media\/m2\/file/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: CUTOUT })
    if (/\/auth\/me/.test(url)) return route.fulfill(json(assoc
      ? { id: 'u1', username: 'staff', role: 'super_admin', club_slug: null, club_name: 'WASTCA', workspace_kind: 'association', acting_as_club: true, entitlements: { modules: ['socials'], status: 'active' } }
      : { id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'tcc', entitlements: { modules: ['socials', 'select', 'stats'], status: 'active' } }))
    if (/\/admin\/social\/media\?kind=background/.test(url)) return route.fulfill(json([]))
    if (/\/admin\/social\/media/.test(url)) return route.fulfill(json(MEDIA))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(settings))
    if (/\/admin\/social\/crests/.test(url)) return route.fulfill(json({ crests: [] }))
    if (/\/images\/players\/[^/]+\/photo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: CUTOUT })
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json(roster))
    if (/templates|players|sponsors/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/social-post${query}`, { waitUntil: 'domcontentloaded' })
  if (viewport.width < 768) await page.getByRole('button', { name: /full editor/i }).first().waitFor({ timeout: 25000 })
  else await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 })
  await page.waitForTimeout(500)
  return { ctx, page, errors, writes }
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
    const h = holder ? holder.innerHTML : ''
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
  ['DL1', 'Match Day V', 'Our panel'], ['DL2', 'Gameday Echo', 'Echo word'], ['DL3', 'Final Score V', 'Opposition side'],
  ['DL8', 'Game Day Card', 'Game day word'], ['DL9', 'Squad Collage', 'Players'], ['DL4', 'Fixtures Echo', 'Rows'], ['DL5', 'Results Echo', 'Rows'], ['DL6', 'Colour Pop', 'Name'], ['DL7', 'Colour Pop', 'Name'],
  ['DL10', 'Signed Stamp', 'Stamp'], ['DL11', 'Quote Card', 'Quote'], ['DL12', 'Birthday', 'Greeting'], ['DL13', 'Squad Update', 'Status'],
  ['DL14', 'Countdown', 'Number'], ['DL15', 'Stat Hero', 'Big figure'], ['DL16', 'Coin Toss', 'Coin'], ['DL17', 'Big Number', 'Number'],
  ['DL18', 'The Oval', 'Field'], ['DL19', 'Split Final', 'Ribbon'], ['DL20', 'Numbered List', 'Team list'],
  ['DL21', 'Ladder', 'Title'], ['DL22', 'Head to Head', 'Crests'], ['DL23', 'Stat Leaders', 'Title'],
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
  // Square: our panel runs from x 70 and from y ~330; the club is navy #0b1530.
  const px = await exportPixels(page, [[90, 380], [74, 700]])
  ck('PNG: Match Day V paints our panel in the club colour', near(px.px[0], [11, 21, 48], 30), JSON.stringify(px.px[0]))
  ck('PNG: and cuts its bottom corner into a V (the paper shows)', near(px.px[1], [235, 232, 225], 30), JSON.stringify(px.px[1]))
  await ctx.close()
}
{
  const { ctx, page, errors } = await openLayout('DL1', { settings: WORKSPACE, assoc: true })
  ck('workspace: Match Day V opens in an Association workspace', (await exportBlocks(page)).includes('data-layer="Our panel"'))
  ck('workspace: no page errors on the design layout', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 4c. Squad Collage: players stack by count and can be reordered ─────────
async function pickRoster(page, n) {
  await press(page.getByRole('button', { name: 'Content', exact: true }))
  await page.waitForTimeout(200)
  for (let i = 1; i <= n; i++) await press(page.getByRole('button', { name: new RegExp(`^Sam Player${i}\\b`) }))
  await page.waitForTimeout(300)
}
{
  const { ctx, page, errors } = await openEditor({ query: '?template=DL9', roster: ROSTER })
  await pickRoster(page, 5)
  const slots = async () => (await exportBlocks(page)).match(/data-collage-slot="/g)?.length || 0
  ck('collage: five picked players with photos give five places', await slots() === 5, String(await slots()))
  ck('collage: its Content panel lists them to reorder', (await page.getByTestId('collage-row').count()) === 5)
  const first0 = await textOf(page.getByTestId('collage-row').first())
  await press(page.getByTestId('collage-down').first())
  await page.waitForTimeout(150)
  const first1 = await textOf(page.getByTestId('collage-row').first())
  ck('collage: the down arrow moves the featured player down the order', first0 !== first1 && /FEATURED/.test(first1), `${first0} -> ${first1}`)
  await press(page.getByTestId('collage-on').first())
  await page.waitForTimeout(250)
  ck('collage: unticking a player rearranges the poster for four', await slots() === 4, String(await slots()))
  const rows = await page.evaluate(() => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    return h ? [...h.querySelectorAll('[data-collage-slot]')].map((e) => e.getAttribute('data-collage-slot')) : []
  })
  ck('collage: four players stand in two rows of two', JSON.stringify(rows.slice().sort()) === JSON.stringify(['0', '0', '1', '1']), JSON.stringify(rows))
  ck('collage: no page errors', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 4d. A photo look on a built-in layout's own photos (Player Spotlight) ──
{
  const { ctx, page, errors } = await openEditor({ query: '?template=C3', roster: ROSTER })
  await pickRoster(page, 1)
  const imgs = async () => page.evaluate(() => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    return h ? [...h.querySelectorAll('img')].map((i) => i.getAttribute('src')) : []
  })
  const before = await imgs()
  ck('control: the spotlight draws the player photo straight from the profile', before.some((s) => /images\/players\/p1\/photo/.test(s)) && !before.some((s) => /^blob:/.test(s)), JSON.stringify(before).slice(0, 160))
  await tool(page, 'Effects')
  ck('Effects with nothing selected offers the layout photo look', await seen(page.getByTestId('fx-layout-photos')))
  await press(page.getByTestId('look-noir'))
  await page.waitForTimeout(900)
  const after = await imgs()
  ck('a look swaps the layout photo for its processed copy', after.some((s) => /^blob:/.test(s)) && !after.some((s) => /images\/players\/p1\/photo/.test(s)), JSON.stringify(after).slice(0, 160))
  await press(page.getByText('Cut-out edge'))
  const eo = page.getByTestId('fx-edge-outline')
  if (await eo.count()) await eo.fill('12')
  await page.waitForTimeout(900)
  const dims = await page.evaluate(async () => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    const src = h && [...h.querySelectorAll('img')].map((i) => i.getAttribute('src')).find((s) => /^blob:/.test(s))
    if (!src) return null
    const im = new Image(); im.src = src; await im.decode()
    return [im.naturalWidth, im.naturalHeight]
  })
  ck('the baked outline grows the cut-out by its width on each side', !!dims && dims[0] === 400 + 24 && dims[1] === 600 + 24, JSON.stringify(dims))
  await press(page.getByTestId('fx-layout-reset'))
  await page.waitForTimeout(300)
  ck('taking the look off restores the original photo', (await imgs()).some((s) => /images\/players\/p1\/photo/.test(s)))
  ck('no page errors through the layout photo look', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 4e. Favourites: starred layouts lead their post type's list ────────────
const tilesOf = async (page) => page.evaluate(() => [...document.querySelectorAll('[data-testid^="layout-tile-"]')].map((e) => e.getAttribute('data-testid').slice(12)))
{
  const { ctx, page, errors, writes } = await openEditor({ query: '?template=T11' })
  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await page.waitForTimeout(200)
  const t0 = await tilesOf(page)
  ck('control: the Lineup list opens in its usual order (Split Poster first)', t0[0] === 'T11' && t0.includes('DL9') && t0.includes('DL2'), t0.slice(0, 4).join(','))
  ck('every layout tile carries a star', t0.length > 0 && (await page.locator('button[data-testid^="fav-"]').count()) === t0.length)
  await press(page.getByTestId('fav-DL9'))
  await press(page.getByTestId('fav-DL2'))
  await page.waitForTimeout(200)
  const t1 = await tilesOf(page)
  ck('starred layouts move to the top, in the order they were starred', t1[0] === 'DL9' && t1[1] === 'DL2' && t1[2] === 'T11', t1.slice(0, 4).join(','))
  ck('the star shows as pressed', (await page.getByTestId('fav-DL9').getAttribute('aria-pressed').catch(() => null)) === 'true')
  ck('the list says how many are starred', /2 starred/.test(await textOf(page.getByTestId('fav-hint'))))
  await page.waitForTimeout(1800)
  const saved = writes.filter((w) => /club-admin\/settings/.test(w.url) && /favourite_layouts/.test(w.body || '')).map((w) => JSON.parse(w.body).socials_style?.favourite_layouts)
  ck('favourites are saved to the club settings for every admin', saved.length > 0 && JSON.stringify(saved[saved.length - 1]) === JSON.stringify(['DL9', 'DL2']), JSON.stringify(saved.slice(-1)))
  await press(page.getByTestId('fav-DL9'))
  await press(page.getByTestId('fav-DL2'))
  await page.waitForTimeout(200)
  ck('unstarring puts the list back as it was', t0.length > 0 && JSON.stringify(await tilesOf(page)) === JSON.stringify(t0))
  ck('no page errors through favourites', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}
{
  const settings = { ...CLUB, socials_style: { palette: 'club', favourite_layouts: ['DL20', 'NOPE'] } }
  const { ctx, page, errors } = await openEditor({ query: '?template=T11', settings })
  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await page.waitForTimeout(300)
  const t = await tilesOf(page)
  ck("a club's stored favourite leads the list in another admin's browser", t[0] === 'DL20', t.slice(0, 3).join(','))
  ck('an unknown id in the stored list is ignored, not shown', t.length > 0 && !t.includes('NOPE'))
  ck('no page errors on load with stored favourites', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 4f. Ladder & Leaders: ladder, head to head, stat leaders ───────────────
{
  const cols = [['played', 'P'], ['won', 'W'], ['lost', 'L'], ['competitionPoints', 'PTS'], ['netRunRate', 'NRR']].map(([id, heading]) => ({ id, heading }))
  const ladderRows = Array.from({ length: 12 }, (_, i) => ({
    rank: i + 1, team_name: i === 10 ? 'Test Cricket Club 1st XI' : `Rival ${i + 1}`, logo_url: null, is_club: i === 10,
    stats: { played: 9, won: 9 - i * 0.5 | 0, lost: i * 0.5 | 0, competitionPoints: 60 - i * 4, netRunRate: (1.2 - i * 0.2).toFixed(3) },
  }))
  const LADDERS = { teams: [{ team_id: 't1', team_name: '1st XI', grade_id: 'g1', grade_name: 'A Grade', available: true, views: [{ name: 'Overall', columns: cols, rows: ladderRows }] }], unlinked: [] }
  const BAT = [1, 2, 3, 4, 5].map((i) => ({ player_id: `p${i}`, name: `Sam Player${i}`, total_runs: 600 - i * 50, innings: 9, average: '45.2', high_score: '102*' }))
  const BOWL = [1, 2, 3].map((i) => ({ player_id: `p${i}`, name: `Sam Player${i}`, total_wickets: 30 - i, economy: '3.4', best_figures_wickets: 6, best_figures_runs: 22 }))
  const SEASONS = [{ id: 's1', name: '2024-25', year: 2024 }, { id: 's2', name: '2025-26', year: 2025 }]
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  const gets = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    gets.push(url)
    if (/\/auth\/me/.test(url)) return route.fulfill(json({ id: 'u1', role: 'club_admin', club_slug: 'tcc', entitlements: { modules: ['socials', 'select', 'stats'], status: 'active' } }))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(CLUB))
    if (/\/admin\/social\/head-to-head/.test(url)) return route.fulfill(json({ found: true, opponent: 'Rival 1', meetings: 3, wins: 1, losses: 2, draws: 0, ties: 0, no_result: 0, form: ['L', 'W', 'L'], recent: [{ played_at: '2026-11-01', grade_name: 'A Grade', home_away: 'AWAY', outcome: 'L' }, { played_at: '2026-01-10', grade_name: 'A Grade', home_away: 'HOME', outcome: 'W' }, { played_at: '2025-12-01', grade_name: 'A Grade', home_away: 'AWAY', outcome: 'L' }] }))
    if (/\/ladders\/teams/.test(url)) return route.fulfill(json(LADDERS))
    if (/\/club-admin\/seasons/.test(url)) return route.fulfill(json(SEASONS))
    if (/\/leaderboard\/batting/.test(url)) return route.fulfill(json(BAT))
    if (/\/leaderboard\/bowling/.test(url)) return route.fulfill(json(BOWL))
    if (/\/leaderboard\/fielding/.test(url)) return route.fulfill(json([]))
    if (/\/images\/players\//.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: CUTOUT })
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json(ROSTER))
    if (/social\/media|templates|sponsors/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/social-post?template=DL21`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 }).catch(() => {})
  await page.waitForTimeout(800)
  const html = async () => (await exportBlocks(page))
  ck('Ladder & Leaders is a post type in the editor', await seen(page.getByRole('button', { name: /Ladder & Leaders/ })))
  ck('it reads the club\'s team ladders', gets.some((u) => /\/ladders\/teams/.test(u)))
  const h1 = await html()
  ck('DL21 draws ten ladder rows on a square post', (h1.match(/data-ladder-row="/g) || []).length === 10, String((h1.match(/data-ladder-row="/g) || []).length))
  ck('our row is kept although we sit 11th, below the cut', /data-ladder-row="club"/.test(h1) && h1.includes('TEST CRICKET CLUB 1ST XI'))
  ck('the row above the cut gives way to ours', !h1.includes('RIVAL 10') && h1.includes('RIVAL 9'))
  await press(page.locator('nav button[title="Data"]'))
  await page.waitForTimeout(200)
  ck('the Data step offers the team, opponent and leaderboard picks', await seen(page.getByTestId('standings-controls')) && await seen(page.getByTestId('standings-team')))
  // Head to Head
  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await press(page.getByRole('button', { name: /^DL22\s*Head to Head/ }))
  await page.waitForTimeout(300)
  ck('control: Head to Head asks for an opponent before one is picked', /PICK THE OPPONENT/.test(await html()) && !/data-h2h-row/.test(await html()))
  await press(page.locator('nav button[title="Data"]'))
  await page.getByTestId('standings-opp').selectOption('Rival 1').catch(() => {})
  await page.waitForTimeout(300)
  const h2 = await html()
  ck('Head to Head compares the two ladder rows stat by stat', ['rank', 'played', 'won', 'lost', 'competitionPoints', 'netRunRate'].every((id) => h2.includes(`data-h2h-row="${id}"`)))
  ck('it names both sides from the ladder', h2.includes('TEST CRICKET CLUB 1ST XI') && h2.includes('RIVAL 1'))
  await page.waitForTimeout(900)
  const askH2H = gets.filter((u) => /\/admin\/social\/head-to-head/.test(u))
  ck('Head to Head asks for past results against the ladder opponent', askH2H.length > 0 && /opponent=Rival%201/.test(askH2H[askH2H.length - 1]), askH2H.slice(-1)[0] || 'none')
  const h2b = await html()
  ck('Head to Head draws the past meetings under the ladder comparison', /data-past-block/.test(h2b) && (h2b.match(/data-past-row=""/g) || []).length === 3 && /1-2 IN 3 MEETINGS/.test(h2b))
  // Stat Leaders
  await press(page.getByRole('button', { name: 'Design', exact: true }))
  await press(page.getByRole('button', { name: /^DL23\s*Stat Leaders/ }))
  await page.waitForTimeout(800)
  const bat = gets.filter((u) => /\/leaderboard\/batting/.test(u))
  ck('Stat Leaders reads the batting leaderboard for the newest season by default', bat.length > 0 && /season_id=s2/.test(bat[bat.length - 1]) && !/grade_id=/.test(bat[bat.length - 1]), bat.slice(-1)[0] || 'none')
  const h3 = await html()
  ck('the leader is drawn large and four more as rows', (h3.match(/data-leader-row=""/g) || []).length === 4 && h3.includes('550'))
  ck('the post names the scope it is measured under', h3.includes('2025-26 · ALL GRADES') || /2025-26 · ALL GRADES/i.test(h3))
  await press(page.locator('nav button[title="Data"]'))
  await press(page.getByTestId('leaders-bowling'))
  await page.getByTestId('leaders-grade').selectOption('g1').catch(() => {})
  await page.waitForTimeout(800)
  const bowl = gets.filter((u) => /\/leaderboard\/bowling/.test(u))
  ck('choosing Wickets and the grade reads the bowling leaderboard for that grade', bowl.length > 0 && /grade_id=g1/.test(bowl[bowl.length - 1]) && /season_id=s2/.test(bowl[bowl.length - 1]), bowl.slice(-1)[0] || 'none')
  ck('and the post shows wicket takers', /WICKET TAKERS/.test(await html()))
  await page.getByTestId('leaders-season').selectOption('').catch(() => {})
  await page.waitForTimeout(800)
  const allTime = gets.filter((u) => /\/leaderboard\/bowling/.test(u)).slice(-1)[0] || ''
  ck('All time drops the season from the request', allTime && !/season_id=/.test(allTime), allTime)
  ck('no page errors through Ladder & Leaders', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}
{
  const { ctx, page } = await openEditor({ settings: WORKSPACE, assoc: true, query: '?type=lineup' })
  ck('workspace: Ladder & Leaders is not offered (no club teams; Round Review has the ladder)', !(await seen(page.getByRole('button', { name: /Ladder & Leaders/ }))))
  await ctx.close()
}

// ── 4g. Past results against the opponent ──────────────────────────────────
{
  const PAST = {
    found: true, opponent: 'Subiaco-Floreat', meetings: 5, wins: 3, losses: 1, draws: 0, ties: 1, no_result: 0,
    form: ['W', 'W', 'L', 'T', 'W'],
    recent: [
      { played_at: '2026-11-15', grade_name: 'A Grade', home_away: 'HOME', outcome: 'W' },
      { played_at: '2026-11-08', grade_name: 'B Grade', home_away: 'HOME', outcome: 'W' },
      { played_at: '2026-10-18', grade_name: 'A Grade', home_away: 'AWAY', outcome: 'L' },
      { played_at: '2026-09-18', grade_name: 'A Grade', home_away: 'HOME', outcome: 'T' },
      { played_at: '2026-08-19', grade_name: 'A Grade', home_away: 'HOME', outcome: 'W' },
    ],
  }
  const NONE = { found: false, opponent: 'Nobody CC', meetings: 0, wins: 0, losses: 0, draws: 0, ties: 0, no_result: 0, form: [], recent: [], reason: 'no past games against that club' }
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  const asks = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    if (/\/admin\/social\/head-to-head/.test(url)) { asks.push(url); return route.fulfill(json(/Nobody/i.test(decodeURIComponent(url)) ? NONE : PAST)) }
    if (/\/auth\/me/.test(url)) return route.fulfill(json({ id: 'u1', role: 'club_admin', club_slug: 'tcc', entitlements: { modules: ['socials', 'select', 'stats'], status: 'active' } }))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(CLUB))
    if (/\/club-admin\/players/.test(url)) return route.fulfill(json(ROSTER))
    if (/\/images\/players\//.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: CUTOUT })
    if (/social\/media|templates|sponsors|ladders/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  await page.goto(`${BASE}/admin/social-post?template=DL1`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 }).catch(() => {})
  await page.waitForTimeout(500)
  const html = async () => exportBlocks(page)
  ck('control: with no opponent typed nothing is asked and no strip is drawn', asks.length === 0 && !/data-past-strip/.test(await html()))
  await press(page.getByRole('button', { name: 'Content', exact: true }))
  await page.waitForTimeout(200)
  ck('Content offers the past results switch on a layout that draws them', await seen(page.getByTestId('past-meetings')))
  await page.getByPlaceholder('Subiaco CC').first().fill('Subiaco-Floreat').catch(() => {})
  await page.waitForTimeout(1300)
  ck('typing the opponent asks once it settles, for that club and every grade', asks.length === 1 && /opponent=Subiaco-Floreat/.test(asks[0]) && !/grade=/.test(asks[0]), asks.join(' | '))
  const h1 = await html()
  ck('Match Day V draws the last-meetings strip with five results', /data-past-strip/.test(h1) && (h1.match(/>W<|>L<|>T</g) || []).length >= 5)
  ck('and the record line', /3-1 1 T IN 5 MEETINGS/.test(h1))
  ck('the panel says what was found and where it came from', /3-1, 1 tied in 5 games against Subiaco-Floreat/.test(await textOf(page.getByTestId('past-status'))), await textOf(page.getByTestId('past-status')))
  await press(page.getByTestId('past-on'))
  await page.waitForTimeout(300)
  ck('switching it off takes the strip off the post', !/data-past-strip/.test(await html()))
  await press(page.getByTestId('past-on'))
  await page.getByPlaceholder('Subiaco CC').first().fill('Nobody CC').catch(() => {})
  await page.waitForTimeout(1300)
  ck('an opponent never played draws nothing and says so', !/data-past-strip/.test(await html()) && /No past games against Nobody CC/.test(await textOf(page.getByTestId('past-status'))))
  // Other layouts take the same strip.
  for (const id of ['DL2', 'DL8', 'DL20', 'DL3', 'DL19', 'DL16']) {
    await page.getByPlaceholder('Subiaco CC').first().fill('Subiaco-Floreat').catch(() => {})
    await page.goto(`${BASE}/admin/social-post?template=${id}`, { waitUntil: 'domcontentloaded' }).catch(() => {})
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 }).catch(() => {})
    await press(page.getByRole('button', { name: 'Content', exact: true }))
    await page.getByPlaceholder('Subiaco CC').first().fill('Subiaco-Floreat').catch(() => {})
    await page.waitForTimeout(1300)
    ck(`${id} draws the last-meetings strip`, /data-past-strip/.test(await html()))
  }
  ck('no page errors through past results', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 4h. Roundups: each row's last results against that row's opponent ──────
{
  const FOUND = { found: true, opponent: 'Subiaco-Floreat', meetings: 4, wins: 2, losses: 2, draws: 0, ties: 0, no_result: 0, form: ['W', 'L', 'W', 'L'], recent: [] }
  const MISS = { found: false, opponent: null, meetings: 0, wins: 0, losses: 0, draws: 0, ties: 0, no_result: 0, form: [], recent: [], reason: 'no past games against that club' }
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  const asks = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    if (/\/admin\/social\/head-to-head\/batch/.test(url)) {
      asks.push({ url, method: route.request().method() })
      const os = new URL(url).searchParams.getAll('o')
      return route.fulfill(json({ results: os.map((o) => (/subiaco/i.test(o) ? { ...FOUND, opponent: o } : MISS)) }))
    }
    if (/\/auth\/me/.test(url)) return route.fulfill(json({ id: 'u1', role: 'club_admin', club_slug: 'tcc', entitlements: { modules: ['socials', 'select', 'stats'], status: 'active' } }))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(CLUB))
    if (/social\/media|templates|sponsors|players|ladders/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  const rowForms = async () => page.evaluate(() => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    return h ? h.querySelectorAll('[data-row-form]').length : -1
  })
  await page.goto(`${BASE}/admin/social-post?template=FX1`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 }).catch(() => {})
  await page.waitForTimeout(1200)
  const first = asks[0]
  const os = first ? new URL(first.url).searchParams.getAll('o') : []
  ck('a roundup asks once for every row\'s opponent, as a GET', asks.length === 1 && first.method === 'GET' && os.length >= 4 && os.some((o) => /subiaco/i.test(o)), first ? `${first.method} ${os.join(', ')}` : 'none')
  ck('each opponent is asked once, for every grade', new Set(os.map((o) => o.toLowerCase())).size === os.length && new URL(first?.url || 'http://x').searchParams.getAll('g').every((g) => g === ''))
  ck('FX1: only the row against a club we have played carries chips', await rowForms() === 1, String(await rowForms()))
  await press(page.getByRole('button', { name: 'Content', exact: true }))
  await page.waitForTimeout(200)
  ck('Content says how many opponents have past games', /Past games found against 1 of \d+ opponents/.test(await textOf(page.getByTestId('past-status'))), await textOf(page.getByTestId('past-status')))
  await press(page.getByTestId('past-grade'))
  await page.waitForTimeout(900)
  const g2 = asks.length > 1 ? new URL(asks[asks.length - 1].url).searchParams.getAll('g') : []
  ck("each row's own grade goes with its opponent when asked", g2.length >= 4 && g2.every((g) => g.length > 0), g2.join(', '))
  await press(page.getByTestId('past-grade'))
  await press(page.getByTestId('past-on'))
  await page.waitForTimeout(300)
  ck('switched off, no row carries chips', await rowForms() === 0)
  await press(page.getByTestId('past-on'))
  for (const id of ['FX2', 'FX3', 'FX4', 'FX5', 'FX6', 'DL4', 'RR1', 'RR2', 'RR3', 'RR4', 'RR5', 'RR6', 'RR7', 'RR8', 'DL5']) {
    await page.goto(`${BASE}/admin/social-post?template=${id}`, { waitUntil: 'domcontentloaded' }).catch(() => {})
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 }).catch(() => {})
    await page.waitForTimeout(1100)
    const n = await rowForms()
    ck(`${id} puts the chips on the Subiaco-Floreat row and nowhere else`, n === 1, String(n))
  }
  ck('no page errors through the roundups', errors.length === 0, errors.slice(0, 2).join(' | '))
  await ctx.close()
}

// ── 4i. Older built-in layouts: past results as a block placed on the post ─
{
  const PAST = { found: true, opponent: 'Subiaco-Floreat', meetings: 5, wins: 3, losses: 1, draws: 0, ties: 1, no_result: 0, form: ['W', 'W', 'L', 'T', 'W'], recent: [] }
  const NONE = { found: false, opponent: null, meetings: 0, wins: 0, losses: 0, draws: 0, ties: 0, no_result: 0, form: [], recent: [], reason: 'no past games against that club' }
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  const asks = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const json = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    if (/\/admin\/social\/head-to-head\?/.test(url)) { asks.push(url); return route.fulfill(json(/Nobody/i.test(decodeURIComponent(url)) ? NONE : PAST)) }
    if (/\/auth\/me/.test(url)) return route.fulfill(json({ id: 'u1', role: 'club_admin', club_slug: 'tcc', entitlements: { modules: ['socials', 'select', 'stats'], status: 'active' } }))
    if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(CLUB))
    if (/social\/media|templates|sponsors|players|ladders/.test(url)) return route.fulfill(json([]))
    return route.fulfill(json({}))
  })
  const counts = async () => page.evaluate(() => {
    const h = [...document.querySelectorAll('div')].find((d) => d.style.left === '-9999px')
    const shown = document.body.innerText
    return { exp: h ? h.querySelectorAll('[data-past-line]').length : -1, placeholder: /NO PAST RESULTS AGAINST|PAST RESULTS · TYPE THE OPPONENT/.test(shown), expText: h ? h.innerText : '' }
  })
  for (const id of ['T11', 'T1', 'C4', 'RS1', 'C2', 'C3']) {
    await page.goto(`${BASE}/admin/social-post?template=${id}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 }).catch(() => {})
    await page.waitForTimeout(400)
    await press(page.getByRole('button', { name: 'Content', exact: true }))
    await page.waitForTimeout(200)
    const box = page.getByTestId('past-block-on')
    ck(`${id}: Content offers past results for this older layout`, await seen(box))
    const c0 = await counts()
    ck(`${id}: control, nothing on the post before it is switched on`, c0.exp === 0)
    await press(box)
    await page.getByPlaceholder('Subiaco CC').first().fill('Subiaco-Floreat').catch(() => {})
    await page.waitForTimeout(1300)
    const c1 = await counts()
    ck(`${id}: switched on, the record strip is on the exported post`, c1.exp === 1 && /3-1 1 T IN 5 MEETINGS/.test(c1.expText), JSON.stringify({ exp: c1.exp }))
    if (id === 'T11') {
      ck('it asks for that opponent', asks.some((u) => /opponent=Subiaco-Floreat/.test(u)))
      await page.getByPlaceholder('Subiaco CC').first().fill('Nobody CC').catch(() => {})
      await page.waitForTimeout(1300)
      const c2 = await counts()
      ck('a club never played: the editor marks where the strip is, the export holds no record', c2.placeholder && !/IN \d+ MEETINGS/.test(c2.expText))
      await page.getByPlaceholder('Subiaco CC').first().fill('Subiaco-Floreat').catch(() => {})
      await page.waitForTimeout(1300)
    }
    await press(box)
    await page.waitForTimeout(300)
    ck(`${id}: switched off, the strip comes off the post`, (await counts()).exp === 0)
  }
  // The block is in Club data for any layout, including the Blank canvas.
  await page.goto(`${BASE}/admin/social-post?type=blank`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 25000 }).catch(() => {})
  await press(page.locator('nav button[title="Club data"]'))
  ck('Club data offers the Past results block', await seen(page.getByRole('button', { name: /Past results v opponent/ })))
  ck('no page errors through the older layouts', errors.length === 0, errors.slice(0, 2).join(' | '))
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
