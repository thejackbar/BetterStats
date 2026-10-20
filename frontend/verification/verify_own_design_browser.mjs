// Drives the real BetterPosts editor in Chromium with the API stubbed at the
// network layer, for "Your own design (Canva)" on the Blank canvas.
//
//   npx vite build && npx vite preview --port 5198 &
//   DESIGN_SQ=/path/1080x1080.png DESIGN_WIDE=/path/1920x1080.png NOTE=/path/notes.txt \
//     node frontend/verification/verify_own_design_browser.mjs [baseUrl]
//
// What a build cannot tell you: that an uploaded design reaches the server and
// comes back as the bottom layer of the EXPORTED post, edge to edge; that it
// takes no clicks (a drag meant for a block on top must not move it); that a
// block added afterwards sits above it; that a design of the wrong shape says it
// is cropped; that a refused upload or a non-image changes nothing and says why;
// that the design follows the Square / Portrait / Story picker; and that Save as
// template stores a library address, never a blob: URL.
import { existsSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'
import { makeEditor, press, seen, tab, ROOT } from './card_layouts_harness.mjs'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const SQ = process.env.DESIGN_SQ, WIDE = process.env.DESIGN_WIDE, NOTE = process.env.NOTE
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => { if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) } }

// Presence-safe: a build with no such feature reports, it does not crash.
const readPost = (page) => page.evaluate((rootSrc) => {
  const root = (new Function(`return (${rootSrc})()`))()
  if (!root) return null
  const rr = root.getBoundingClientRect()
  const imgs = [...root.querySelectorAll('img')].filter((i) => /social-media\/design/.test(i.getAttribute('src') || ''))
  const img = imgs[0]
  const r = img ? img.getBoundingClientRect() : null
  const all = [...root.querySelectorAll('img, [data-testid]')]
  return {
    w: rr.width, h: rr.height, n: imgs.length,
    design: r ? { x: r.left - rr.left, y: r.top - rr.top, w: r.width, h: r.height } : null,
    pe: img ? getComputedStyle(img.parentElement).pointerEvents : null,
    designIndex: img ? all.indexOf(img) : -1,
    texts: root.innerText.replace(/\s+/g, ' '),
  }
}, ROOT.toString())

async function open(opts = {}) {
  const e = await makeEditor(browser, BASE, { layout: 'BL1', size: opts.size || 'square', viewport: { width: 1700, height: 1500 } })
  const { page } = e
  const uploads = [], puts = []
  let failUpload = !!opts.failUpload
  await page.route('**/api/admin/social/media**', (route) => {
    if (route.request().method() !== 'POST') return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    uploads.push(route.request().postDataBuffer()?.length || 0)
    if (failUpload) return route.fulfill({ status: 413, contentType: 'application/json', body: JSON.stringify({ detail: 'Image is too big (limit 5 MB).' }) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'a1', name: 'design.png', url: `/api/social-media/design-${uploads.length}`, kind: null }) })
  })
  await page.route('**/social-media/design-*', (route) => route.fulfill({ status: 200, contentType: 'image/png', body: readFileSync(opts.img || SQ) }))
  await page.route('**/api/admin/social/templates/**', async (route) => {
    if (route.request().method() === 'PUT') { puts.push(route.request().postDataJSON()); return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) }) }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
  return { ...e, uploads, puts }
}
const say = async (page) => (await page.locator('body').innerText()).replace(/\s+/g, ' ')

// 1. Panel is offered on the blank canvas with the size to export at.
{
  const { page, uploads, puts } = await open()
  await tab(page, 'Content'); await page.waitForTimeout(300)
  ck('panel shown on the blank canvas', await seen(page.getByTestId('own-design')))
  ck('panel names the size to export at', /1080\s*×\s*1080/.test(await page.getByTestId('own-design').innerText().catch(() => '')))
  const before = await readPost(page)
  ck('no design before an upload', before && before.n === 0, JSON.stringify(before && before.n))

  // 2. Upload a 1080x1080 design.
  await page.getByTestId('own-design-input').setInputFiles(SQ).catch(() => {})
  await page.waitForTimeout(1500)
  const after = await readPost(page)
  ck('upload sent to the server once', uploads.length === 1, String(uploads.length))
  ck('design is in the exported post', after && after.n === 1, JSON.stringify(after && after.n))
  ck('design fills the post edge to edge', after && after.design && Math.abs(after.design.x) < 1 && Math.abs(after.design.y) < 1 && Math.abs(after.design.w - 1080) < 1 && Math.abs(after.design.h - 1080) < 1, JSON.stringify(after && after.design))
  ck('design takes no pointer events (locked)', after && after.pe === 'none', String(after && after.pe))
  ck('right-size upload is not called cropped', !/edges are cropped/.test(await say(page)))
  ck('button now offers Replace', /Replace your design/.test(await page.getByTestId('own-design').innerText().catch(() => '')))

  // 3. Nothing is selected after an upload (the design is locked).
  const sel = await page.evaluate(() => document.querySelectorAll('[style*="outline"][style*="solid"]').length)
  ck('nothing is selected after upload', sel === 0, String(sel))

  // 4. A block added afterwards sits above the design, in the exported post.
  await tab(page, 'Club data'); await page.waitForTimeout(300)
  await press(page.locator('button', { has: page.locator('div', { hasText: /^Fixtures$/ }) })); await page.waitForTimeout(600)
  const order = await page.evaluate((rootSrc) => {
    const root = (new Function(`return (${rootSrc})()`))()
    if (!root) return null
    const img = [...root.querySelectorAll('img')].find((i) => /social-media\/design/.test(i.getAttribute('src') || ''))
    const block = [...root.querySelectorAll('div')].find((d) => /No fixtures loaded|THIS WEEK/.test(d.innerText || '') && d.children.length <= 3 && !d.contains(img))
    if (!img || !block) return { img: !!img, block: !!block }
    return { img: true, block: true, after: !!(img.compareDocumentPosition(block) & Node.DOCUMENT_POSITION_FOLLOWING) }
  }, ROOT.toString())
  ck('a Fixtures block was added', order && order.block === true, JSON.stringify(order))
  ck('the added block is drawn after (above) the design', order && order.after === true, JSON.stringify(order))

  // 5. Save as template keeps the library address and the design flags.
  await tab(page, 'Design'); await page.waitForTimeout(400)
  await page.getByPlaceholder('Template name...').fill('Canva fixtures').catch(() => {})
  await press(page.getByRole('button', { name: /^Save current$/ }))
  await page.waitForTimeout(1200)
  const saved = puts.length ? JSON.stringify(puts[puts.length - 1]) : ''
  ck('template save reached the server', puts.length >= 1, String(puts.length))
  ck('saved template holds the design as the first block, flagged', /"blank":\[\{[^}]*"design":true[^}]*"locked":true/.test(saved) || (/"design":true/.test(saved) && /"locked":true/.test(saved)), saved.slice(0, 300))
  ck('saved design is a library address, not a blob:', /social-media\/design-1/.test(saved) && !/blob:/.test(saved), saved.slice(0, 300))
  await page.close()
}

// 6. Design follows the size picker.
{
  const { page } = await open()
  await tab(page, 'Content'); await page.waitForTimeout(300)
  await page.getByTestId('own-design-input').setInputFiles(SQ).catch(() => {})
  await page.waitForTimeout(1200)
  await tab(page, 'Design'); await page.waitForTimeout(300)
  await press(page.getByRole('button', { name: /Portrait/ })); await page.waitForTimeout(800)
  const p = await readPost(page)
  ck('portrait: post is 1080x1350', p && p.w === 1080 && p.h === 1350, JSON.stringify(p && [p.w, p.h]))
  ck('portrait: design fills the taller post', p && p.design && Math.abs(p.design.h - 1350) < 1 && Math.abs(p.design.w - 1080) < 1, JSON.stringify(p && p.design))
  await press(page.getByRole('button', { name: /Story/ })); await page.waitForTimeout(800)
  const s = await readPost(page)
  ck('story: design fills 1080x1920', s && s.design && Math.abs(s.design.h - 1920) < 1, JSON.stringify(s && s.design))
  await page.close()
}

// 7. Wrong shape says it is cropped.
{
  const { page } = await open({ img: WIDE })
  await tab(page, 'Content'); await page.waitForTimeout(300)
  await page.getByTestId('own-design-input').setInputFiles(WIDE).catch(() => {})
  await page.waitForTimeout(1500)
  const t = await say(page)
  ck('1920x1080 design on a square post says it is cropped', /1920×1080/.test(t) && /cropped/.test(t), t.slice(0, 0))
  const p = await readPost(page)
  ck('cropped design still fills the post', p && p.design && Math.abs(p.design.w - 1080) < 1 && Math.abs(p.design.h - 1080) < 1, JSON.stringify(p && p.design))
  await page.close()
}

// 8. A non-image is refused before any upload.
{
  const { page, uploads } = await open()
  await tab(page, 'Content'); await page.waitForTimeout(300)
  await page.getByTestId('own-design-input').setInputFiles(NOTE).catch(() => {})
  await page.waitForTimeout(800)
  const p = await readPost(page)
  ck('non-image: nothing uploaded', uploads.length === 0, String(uploads.length))
  ck('non-image: no design added', p && p.n === 0)
  ck('non-image: says why', /not a PNG, JPG or WebP/.test(await say(page)))
  await page.close()
}

// 9. A refused upload changes nothing and says so.
{
  const { page, uploads } = await open({ failUpload: true })
  await tab(page, 'Content'); await page.waitForTimeout(300)
  await page.getByTestId('own-design-input').setInputFiles(SQ).catch(() => {})
  await page.waitForTimeout(1200)
  const p = await readPost(page)
  ck('server refusal: the upload was attempted', uploads.length === 1, String(uploads.length))
  ck('server refusal: no design added', p && p.n === 0, JSON.stringify(p && p.n))
  const t = await say(page)
  ck('server refusal: says so and names the 5 MB limit', /did not upload/.test(t) && /5 MB/.test(t))
  ck('server refusal: button still offers Upload', /Upload your design/.test(await page.getByTestId('own-design').innerText().catch(() => '')))
  await page.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
