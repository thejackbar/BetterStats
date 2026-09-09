// Every BetterSocials template at 1:1, 4:5 and 9:16.
//
//   npx vite --port 5211 &
//   node frontend/verification/verify_post_formats_browser.mjs [baseUrl]
//
// A template composes its artwork at a fixed 1080×1080 and is NOT re-laid-out
// per size — three separately-tuned copies of one layout is how they start
// disagreeing with each other — so what is measured here is the canvas and what
// reaches its edges, not the wording of anything:
//
//   · the canvas really is 1080×1350 / 1080×1920, read off the node the export
//     captures, and the preview and the export node agree on it (they are one
//     definition; two would mean the downloaded PNG is a different size from
//     the thing on screen);
//   · the artwork sits CENTRED — the band above and below measured equal;
//   · the square is untouched, artwork box === canvas, no band at all;
//   · the shared texture layers and full-height chrome reach the REAL canvas
//     edges rather than stopping at the artwork's, which is the seam that makes
//     a taller post read as a letterboxed square;
//   · the wide scorecard is offered no size control at all, because it composes
//     1920×1080 and a 1080-wide canvas could only crop it; and
//   · every template in every tab renders at all three sizes with no page error
//     and nothing painted outside the canvas.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5211'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

// A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN. Against a build without the
// size control every locator here finds nothing, and a bare .boundingBox() or
// .click() on one of those throws and kills the run after two checks — saying
// nothing about the other forty. Every read of something this change ADDS goes
// through one of these.
const has = async (loc) => (await loc.count()) > 0
const boxOf = async (loc) => (await loc.count()) ? await loc.first().boundingBox() : null
const press = async (loc) => { if (await loc.count()) { await loc.first().click(); return true } return false }

const FORMATS = [
  { key: 'square', label: 'Square', w: 1080, h: 1080 },
  { key: 'portrait', label: 'Portrait', w: 1080, h: 1350 },
  { key: 'story', label: 'Story', w: 1080, h: 1920 },
]

// The size picker lives in the Design panel and is keyed by its own label, not
// by a testid this change invented — so a control run against the build BEFORE
// the templates learned to fill the canvas still finds the buttons and fails on
// what they DO, rather than reporting "button not found", which says nothing.
const sizeBtn = (page, f) => page.locator('button', { hasText: new RegExp(`^${f.label}${f.key === 'square' ? '1:1' : f.key === 'portrait' ? '4:5' : '9:16'}$`) })
const openDesign = async (page) => {
  const tool = page.locator('button', { hasText: /^DESIGN$/i })
  if (await tool.count()) await tool.first().click()
  await page.waitForTimeout(400)
}

// One per template file, so a break in any of the four is caught rather than
// cricket-templates standing in for all of them: a lineup poster (its own
// hardcoded canvas), a fixtures roundup (the shared Post shell, 19 templates
// behind one edit), an event poster (the FRAME set) and the freeform canvas.
const SAMPLES = [
  { id: 'T1', type: 'lineup', label: 'lineup hero' },
  { id: 'T3', type: 'lineup', label: 'lineup side panel' },
  { id: 'FX2', type: 'fixtures', label: 'fixtures roundup' },
  { id: 'RR1', type: 'results', label: 'results roundup' },
  { id: 'EV1', type: 'events', label: 'event poster' },
  { id: 'C4', type: 'result', label: 'final score' },
]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open({ id = 'T1', type = 'lineup', width = 1600 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))

  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url())
    const p = u.pathname.replace(/^\/api/, '')
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(p)) {
      return json({ id: 'a1', username: 'admin', display_name: 'Admin', role: 'club_admin',
                    club_slug: 'demo', organisation_id: 'org1',
                    entitlements: { modules: ['stats', 'select', 'socials', 'admin', 'crm', 'iq'], status: 'active' } })
    }
    if (/club-admin\/settings/.test(p)) {
      return json({ id: 'org1', name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'demo', theme_config: {} })
    }
    return json([])
  })

  await page.goto(`${BASE}/admin/social-post?template=${id}&type=${type}`, { waitUntil: 'domcontentloaded' })
  // Wait for the thing this suite is about, never for the network to go quiet —
  // HeartbeatBeacon pings for as long as the tab is open, so networkidle never
  // settles on this app and would hang the run rather than fail it.
  await page.locator('[data-testid="post-export-node"]')
    .waitFor({ state: 'attached', timeout: 20000 }).catch(() => {})
  await page.waitForTimeout(1200)
  await openDesign(page)
  return { page, ctx, errors }
}

// Geometry is read off the REAL nodes rather than from the style strings: a
// style attribute says what was asked for, a bounding box says what the browser
// did with it.
async function canvasGeometry(page) {
  return await page.evaluate(() => {
    const node = document.querySelector('[data-testid="post-export-node"]')
    if (!node) return null
    const canvas = node.querySelector('[data-post-canvas]')
    const art = node.querySelector('[data-post-art]')
    const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return { top: b.top, bottom: b.bottom, left: b.left, right: b.right, w: b.width, h: b.height } }
    const nb = r(node), cb = r(canvas), ab = r(art)
    return {
      node: nb, canvas: cb, art: ab,
      // A texture layer is deliberately drawn wider than the canvas (Halftone
      // scales 1.4 about its centre) and CLIPPED by it, so measuring raw
      // bounding boxes would report a seam that is never painted. What has to
      // hold is that the canvas clips and the post does not scroll.
      clips: canvas ? getComputedStyle(canvas).overflow : null,
      scrollOverflow: canvas ? Math.max(canvas.scrollWidth - canvas.clientWidth, canvas.scrollHeight - canvas.clientHeight) : null,
    }
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. THE CONTROL ITSELF.
const { page, ctx, errors } = await open()

for (const f of FORMATS) {
  ck(`the ${f.key} size is offered`, await has(sizeBtn(page, f)))
}

// The square is the default: a club that has never touched this gets exactly
// the post it got before.
let geo = await canvasGeometry(page)
ck('it opens on the square', !!geo && Math.round(geo.node.h) === 1080, `got ${geo && Math.round(geo.node.h)}`)
ck('on the square the artwork box IS the canvas — no band at all',
  !!geo?.art && !!geo?.canvas && Math.abs(geo.art.top - geo.canvas.top) < 1 && Math.abs(geo.art.h - geo.canvas.h) < 1,
  geo?.art ? `art ${Math.round(geo.art.h)} canvas ${Math.round(geo.canvas.h)}` : 'no artwork box')

// ─────────────────────────────────────────────────────────────────────────────
// 2. THE CANVAS IS THE SIZE IT SAYS, AND THE ARTWORK IS CENTRED IN IT.
for (const f of FORMATS) {
  await press(sizeBtn(page, f))
  await page.waitForTimeout(600)
  geo = await canvasGeometry(page)
  ck(`${f.key}: the export canvas is ${f.w}×${f.h}`,
    !!geo && Math.round(geo.node.w) === f.w && Math.round(geo.node.h) === f.h,
    geo ? `got ${Math.round(geo.node.w)}×${Math.round(geo.node.h)}` : 'no export node')
  ck(`${f.key}: the template's own canvas fills the export node`,
    !!geo?.canvas && Math.round(geo.canvas.h) === f.h && Math.round(geo.canvas.w) === f.w,
    geo?.canvas ? `got ${Math.round(geo.canvas.w)}×${Math.round(geo.canvas.h)}` : 'no canvas')

  const top = geo?.art && geo?.canvas ? geo.art.top - geo.canvas.top : null
  const bottom = geo?.art && geo?.canvas ? geo.canvas.bottom - geo.art.bottom : null
  ck(`${f.key}: the artwork is centred — the band above and below measure equal`,
    top != null && Math.abs(top - bottom) <= 1, `top ${top} bottom ${bottom}`)
  ck(`${f.key}: the artwork is still composed at 1080×1080`,
    !!geo?.art && Math.round(geo.art.h) === 1080 && Math.round(geo.art.w) === 1080,
    geo?.art ? `got ${Math.round(geo.art.w)}×${Math.round(geo.art.h)}` : 'no artwork box')
  ck(`${f.key}: nothing is painted past the canvas — it clips its own edges`,
    geo?.clips === 'hidden' && geo?.scrollOverflow <= 0,
    `overflow ${geo?.clips} scroll ${geo?.scrollOverflow}`)

  // ONE definition of the canvas: the preview and the node the export captures
  // read the same W×H, so a downloaded PNG cannot be a different size from the
  // thing on screen.
  const pv = await boxOf(page.locator('[data-testid="post-preview-node"]'))
  const declared = await page.locator('[data-testid="post-preview-node"]').first()
    .evaluate((el) => ({ w: parseFloat(el.style.width), h: parseFloat(el.style.height) })).catch(() => null)
  ck(`${f.key}: the preview and the export node are the same canvas`,
    !!declared && declared.w === f.w && declared.h === f.h,
    declared ? `preview ${declared.w}×${declared.h}` : 'no preview node')
  ck(`${f.key}: the preview is scaled down to fit rather than cropped`,
    !!pv && pv.width > 0 && Math.abs((pv.width / pv.height) - (f.w / f.h)) < 0.02,
    pv ? `${Math.round(pv.width)}×${Math.round(pv.height)}` : 'no preview box')
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. THE SEAM. Texture and full-height chrome have to reach the REAL edges.
await press(sizeBtn(page, FORMATS[2]))
await page.waitForTimeout(600)
const edges = await page.evaluate(() => {
  const node = document.querySelector('[data-testid="post-export-node"]')
  if (!node) return null
  const canvas = node.querySelector('[data-post-canvas]')
  const art = node.querySelector('[data-post-art]')
  if (!canvas || !art) return null
  const cb = canvas.getBoundingClientRect()
  const ab = art.getBoundingClientRect()
  // Direct children of the artwork box that declare themselves full height
  // (top AND bottom anchored, or a repeating background image — the shared
  // texture layers) are the ones that must not stop at the artwork's edge.
  const out = []
  for (const el of art.children) {
    const cs = getComputedStyle(el)
    const fullHeight = cs.top !== 'auto' && cs.bottom !== 'auto'
    const textured = /gradient/.test(cs.backgroundImage || '')
    if (!fullHeight && !textured) continue
    const b = el.getBoundingClientRect()
    out.push({
      cls: el.tagName + (el.style.width ? `[w=${el.style.width}]` : ''),
      // A background layer: it paints across the post rather than holding
      // content, so it is one of the ones that must reach the real edges.
      backdrop: textured || (!el.textContent.trim() && b.width >= cb.width - 1),
      reachesTop: b.top <= cb.top + 1,
      reachesBottom: b.bottom >= cb.bottom - 1,
      stopsAtArt: Math.abs(b.top - ab.top) < 1 && Math.abs(b.bottom - ab.bottom) < 1,
    })
  }
  return { count: out.length, out, artTop: ab.top - cb.top }
})
ck('the story canvas has full-bleed layers to judge', (edges?.count || 0) > 0, `found ${edges?.count}`)
ck('no full-bleed layer stops at the artwork edge and leaves a line down the post',
  !!edges && edges.out.every((o) => !o.stopsAtArt),
  edges ? JSON.stringify(edges.out.filter((o) => o.stopsAtArt)) : 'nothing measured')
const backdrops = (edges?.out || []).filter((o) => o.backdrop)
ck('the story canvas has background layers to judge', backdrops.length > 0, `found ${backdrops.length}`)
ck('every background layer reaches the real top and bottom of the post',
  backdrops.length > 0 && backdrops.every((o) => o.reachesTop && o.reachesBottom),
  JSON.stringify(backdrops.filter((o) => !(o.reachesTop && o.reachesBottom))))

ck('a template that fills the canvas is offered no fit-or-crop control',
  !(await has(page.locator('text=Fitting this layout'))))
ck('and is told it fills the canvas instead',
  await has(page.locator('[data-testid="post-size-fills-note"]')))
ck('no page errors while switching size', errors.length === 0, errors.slice(0, 2).join(' | '))
await ctx.close()

// ─────────────────────────────────────────────────────────────────────────────
// 4. EVERY TEMPLATE FILE, EVERY SIZE. This is the check that earns its keep
// across sixty-odd templates: one shared canvas either works for all of them or
// the ones it does not are named here.
for (const s of SAMPLES) {
  const { page: p2, ctx: c2, errors: e2 } = await open({ id: s.id, type: s.type })
  for (const f of FORMATS) {
    await press(sizeBtn(p2, f))
    await p2.waitForTimeout(450)
    const g = await canvasGeometry(p2)
    ck(`${s.label} (${s.id}) renders at ${f.w}×${f.h}`,
      !!g && Math.round(g.node.h) === f.h && Math.round(g.node.w) === f.w,
      g ? `got ${Math.round(g.node.w)}×${Math.round(g.node.h)}` : 'no export node')
    ck(`${s.label} (${s.id}) at ${f.key} keeps its artwork centred`,
      !!g?.art && !!g?.canvas && Math.abs((g.art.top - g.canvas.top) - (g.canvas.bottom - g.art.bottom)) <= 1)
  }
  ck(`${s.label} (${s.id}) renders every size with no page error`, e2.length === 0, e2.slice(0, 1).join(' | '))
  await c2.close()
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. THE ONE LAYOUT A FORMAT CANNOT RE-CANVAS. The wide scorecard composes at
// 1920×1080; a control that could only crop it is worse than none.
{
  const { page: p3, ctx: c3 } = await open({ id: 'SC1', type: 'scorecard' })
  ck('the wide scorecard is offered no size control',
    !(await has(sizeBtn(p3, FORMATS[1]))))
  const g = await canvasGeometry(p3)
  ck('the wide scorecard still composes at 1920×1080',
    !!g && Math.round(g.node.w) === 1920 && Math.round(g.node.h) === 1080,
    g ? `got ${Math.round(g.node.w)}×${Math.round(g.node.h)}` : 'no export node')
  await c3.close()
}

// ─────────────────────────────────────────────────────────────────────────────
// 6. THE SIZE IS IN THE FILENAME, so a club exporting the same post at all
// three sizes ends up with three files rather than one overwritten twice.
{
  const { page: p4, ctx: c4 } = await open()
  const names = []
  p4.on('download', (d) => names.push(d.suggestedFilename()))
  for (const f of FORMATS) {
    await press(sizeBtn(p4, f))
    await p4.waitForTimeout(500)
    await press(p4.locator('button', { hasText: /DOWNLOAD PNG/ }))
    await p4.waitForTimeout(6000)
  }
  ck('every size downloads a file', names.length === 3, `got ${names.length}: ${names.join(', ')}`)
  ck('each download names its own size',
    FORMATS.every((f) => names.some((n) => n.includes(`${f.w}x${f.h}`))), names.join(', '))
  ck('the three downloads are three different files', new Set(names).size === names.length, names.join(', '))
  await c4.close()
}

// ─────────────────────────────────────────────────────────────────────────────
// 7. The editor itself still fits a phone.
{
  const { page: p5, ctx: c5 } = await open({ width: 390 })
  const overflow = await p5.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', overflow <= 0, `overflow ${overflow}px`)
  await c5.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
