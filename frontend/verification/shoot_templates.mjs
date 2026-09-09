// Screenshots every BetterPosts template at every post size, by driving the
// REAL editor — so each layout gets the exact props the app builds for it
// rather than a harness's invented stand-ins.
//
//   npx vite --port 5199 &
//   node frontend/verification/shoot_templates.mjs [outDir] [templateIds...]
//
// Writes one PNG per (template, size) plus a contact sheet per batch, because
// "does this layout hold up at 4:5" is a question only a picture answers — the
// geometry checks in verify_post_designer_browser.mjs all passed on a version
// whose letterbox bands were the wrong colour.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const OUT = process.argv[2] || '/tmp/shots'
const ONLY = process.argv.slice(3)
const BASE = process.env.BASE || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

const ALL = [
  'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10',
  'C1', 'C2', 'C3', 'C4',
  'RS1', 'RS2', 'RS3', 'RS4', 'RS5', 'RS6',
  'FX1', 'FX2', 'FX3', 'FX4', 'FX5', 'FX6',
  'RR1', 'RR2', 'RR3', 'RR4', 'RR5', 'RR6', 'RR7',
  'SC1', 'SC2', 'SC3',
  'EV1', 'EV2', 'EV3', 'EV4', 'EV5', 'EV6', 'EV7', 'EV8', 'EV9', 'EV10', 'EV11',
  'BL1',
]
const IDS = ONLY.length ? ONLY : ALL
const SIZES = ['square', 'portrait', 'story']

mkdirSync(OUT, { recursive: true })

const SETTINGS = {
  id: 'org-1', name: 'Applecross Cricket Club', short_name: 'ACC', slug: 'applecross',
  logo_url: null, primary_color: '#0b1530', accent_color: '#ffc233', theme_config: null,
}
const PLAYERS = Array.from({ length: 13 }, (_, i) => ({
  id: `p${i + 1}`, name: `Player ${i + 1} Surname${i + 1}`, display_name: `Player ${i + 1} Surname${i + 1}`,
  // A photo is what makes a hero template render its CUT-OUT, which is the
  // branch these layouts are really about; with no photo every one of them
  // falls back to the club crest and the shots show the wrong thing.
  status: 'active', photo_url: `/api/images/players/p${i + 1}/photo`,
}))

const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC',
  'base64',
)

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
// Tall enough that a 1080×1920 story fits the clip — a clip past the bottom of
// the viewport comes back short, which reads as a broken layout rather than a
// framing mistake. Wide enough to stay out of the editor's mobile shell.
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1980 } })

const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
await ctx.route('**/api/**', async (route) => {
  const url = route.request().url()
  if (/\/social\/media\/[^/]+\/file/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
    if (/\/images\/players\/[^/]+\/photo/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
  if (/\/auth\/me/.test(url)) return route.fulfill(json({
    id: 'u1', username: 'admin', role: 'club_admin', club_slug: 'applecross',
    entitlements: { modules: ['socials', 'select', 'stats', 'admin', 'iq'], status: 'active' },
  }))
  if (/\/admin\/social\/media\?kind=background/.test(url)) return route.fulfill(json([]))
  if (/\/admin\/social\/media/.test(url)) return route.fulfill(json([]))
  if (/\/club-admin\/settings/.test(url)) return route.fulfill(json(SETTINGS))
  if (/\/club-admin\/players/.test(url)) return route.fulfill(json(PLAYERS))
  if (/sponsors/.test(url)) return route.fulfill(json([]))
  if (/selection\/overview/.test(url)) return route.fulfill(json({ fixtures: [] }))
  if (/lineups/.test(url)) return route.fulfill(json({ matches: [] }))
  if (/usage/.test(url)) return route.fulfill(json({ ok: true }))
  return route.fulfill(json({}))
})

const page = await ctx.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))

// Seeded through the page's own localStorage rather than by clicking, because
// the editor reads both of these in its state initialisers — so one reload puts
// it on any template at any size with no UI to drive.
await page.addInitScript(() => {
  window.__seed = () => {
    const p = new URLSearchParams(location.search)
    localStorage.setItem('bs_social_template', p.get('tpl') || 'T1')
    localStorage.setItem('bs_social_post_size', p.get('sz') || 'square')
  }
  window.__seed()
})

// Switching size in the open editor rather than reloading — a reload is by far
// the most expensive thing here, so one load per template instead of one per
// (template, size) is the difference between minutes and an hour.
async function pickSize(label) {
  const design = page.getByRole('button', { name: 'Design', exact: true })
  if (await design.count()) await design.first().click().catch(() => {})
  const btn = page.getByRole('button', { name: new RegExp(`^${label}`) })
  if (await btn.count()) await btn.first().click().catch(() => {})
  await page.waitForTimeout(350)
}
const SIZE_LABEL = { square: 'Square', portrait: 'Portrait', story: 'Story' }

// A lineup layout with nobody picked renders its player column empty, and an
// empty column looks the same whether it distributes well at 4:5 or not. So the
// squad is filled from the roster before shooting — a no-op on every layout that
// has no player picker.
async function fillLineup() {
  const content = page.getByRole('button', { name: 'Content', exact: true })
  if (await content.count()) await content.first().click().catch(() => {})
  await page.waitForTimeout(200)
  for (let i = 1; i <= 13; i++) {
    const b = page.getByRole('button', { name: new RegExp(`^Player ${i} Surname${i}\\b`) })
    if (await b.count()) await b.first().click().catch(() => {})
  }
  await page.waitForTimeout(200)
}

const shots = []
for (const id of IDS) {
  // ?template= names the layout AND skips the "What are you posting?" start
  // screen — without it the editor never renders and there is no export node
  // to shoot, which reads as every template being broken.
  await page.goto(`${BASE}/admin/social-post?template=${id}&sz=square`, { waitUntil: 'domcontentloaded' })
  // The export node existing IS the success signal — waiting on a button by
  // name would make a renamed label read as every template being broken.
  try {
    await page.getByRole('button', { name: /DOWNLOAD PNG|SLIDES/ }).first().waitFor({ timeout: 15000 })
  } catch { /* the node check below decides */ }
  await fillLineup()

  for (const size of SIZES) {
    const before = errors.length
    await pickSize(SIZE_LABEL[size])
    await page.waitForTimeout(250)

    // The off-screen export node is what the PNG is really captured from, so it
    // is what gets shot — moved on screen first, because an element screenshot
    // of something at left:-9999px silently captures the page instead.
    const moved = await page.evaluate(() => {
      const holder = [...document.querySelectorAll('div')].find(
        (d) => d.style.left === '-9999px' && d.style.position === 'absolute',
      )
      if (!holder) return null
      holder.dataset.shot = '1'
      holder.style.left = '0px'
      holder.style.top = '0px'
      holder.style.position = 'fixed'
      holder.style.zIndex = '2147483647'
      holder.style.background = '#101010'
      const first = holder.firstElementChild
      if (!first) return null
      const r = first.getBoundingClientRect()
      return { w: Math.round(r.width), h: Math.round(r.height) }
    })

    const file = `${OUT}/${id}-${size}.png`
    // Page.screenshot takes a clip; Locator.screenshot does not, and passing one
    // there is how the first cut of this stalled with no output at all.
    if (moved) {
      await page.screenshot({
        path: file,
        clip: { x: 0, y: 0, width: Math.min(moved.w, 1920), height: Math.min(moved.h, 1920) },
      })
      // Put it back off screen, or it covers the editor and the next size can
      // never be clicked — the whole reason this loop reloads once per template
      // rather than once per shot.
      await page.evaluate(() => {
        const h = document.querySelector('[data-shot="1"]')
        if (!h) return
        h.style.left = '-9999px'
        h.style.top = '0'
        h.style.position = 'absolute'
        h.style.zIndex = '-1'
        h.style.background = ''
        delete h.dataset.shot
      })
    }
    const errs = errors.slice(before)
    shots.push({ id, size, ok: !!moved, box: moved, errors: errs.length, err: errs[0] || null })
    console.log(`${id.padEnd(5)} ${size.padEnd(9)} ${moved ? `${moved.w}x${moved.h}` : 'NO NODE'}${errs.length ? `  ERR ${errs[0].slice(0, 90)}` : ''}`)
  }
}

// Contact sheets — six templates a sheet, three sizes across, so a whole family
// can be judged in one look.
const sheet = await ctx.newPage()
const BATCH = 6
for (let b = 0; b * BATCH < IDS.length; b++) {
  const rows = IDS.slice(b * BATCH, (b + 1) * BATCH)
  const html = `<body style="margin:0;background:#181818;font:11px monospace;color:#ddd">
  ${rows.map((id) => `<div style="display:flex;gap:8px;align-items:flex-start;padding:8px">
    <div style="width:60px">${id}</div>
    ${SIZES.map((s) => `<div><div>${s}</div><img src="file://${OUT}/${id}-${s}.png" style="height:300px;display:block"></div>`).join('')}
  </div>`).join('')}
  </body>`
  await sheet.setContent(html)
  await sheet.waitForTimeout(400)
  await sheet.screenshot({ path: `${OUT}/sheet-${b + 1}.png`, fullPage: true })
  console.log(`sheet-${b + 1}.png  ${rows.join(' ')}`)
}

const bad = shots.filter((s) => !s.ok || s.errors)
console.log(`\n${shots.length} shots, ${bad.length} problem${bad.length === 1 ? '' : 's'}`)
bad.forEach((s) => console.log(`  ${s.id} ${s.size}${s.err ? `  ${s.err.slice(0, 140)}` : ''}`))
await browser.close()
