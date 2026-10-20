// Shoots the three card layouts (Round Cover T13, Giant Type C5, Round Highlights
// RS8) through the real editor with the API stubbed, one PNG per layout and size.
//
//   npx vite build && npx vite preview --port 5197 &
//   CUTOUT=/path/cutout.png PHOTO=/path/photo.jpg SHOTS=/tmp/cards \
//     node frontend/verification/shoot_card_layouts.mjs [baseUrl]
//
// Read the PNGs: a contact sheet cannot show whether the type clears the player.
import { existsSync, mkdirSync } from 'node:fs'
import { chromium } from 'playwright'
import { makeEditor, shotNode, press, tab, seen } from './card_layouts_harness.mjs'

const BASE = process.argv[2] || 'http://127.0.0.1:5197'
const SHOTS = process.env.SHOTS || '/tmp/cards'
const CUTOUT = process.env.CUTOUT || ''
const PHOTO = process.env.PHOTO || ''
mkdirSync(SHOTS, { recursive: true })
const SIZES = [['square', 'Square'], ['portrait', 'Portrait'], ['story', 'Story']]
const ONLY = (process.env.ONLY || '').split(',').filter(Boolean)

const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
const sponsors = Number(process.env.SPONSORS || 2)

for (const [key, label] of SIZES) {
  if (ONLY.length && !ONLY.includes(key)) continue
  for (const layout of ['T13', 'C5', 'RS8']) {
    const { ctx, page, errors, run } = await makeEditor(browser, BASE, { layout, size: key, nSponsors: sponsors })
    await run.prepare({ cutout: CUTOUT, photo: PHOTO })
    await page.waitForTimeout(700)
    await shotNode(page, `${SHOTS}/${layout}-${key}.png`)
    console.log(layout, key, errors.length ? `ERR ${errors.slice(0, 2).join(' | ')}` : 'ok')
    await ctx.close()
  }
}
await browser.close()
