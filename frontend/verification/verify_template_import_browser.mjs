// Drives the real BetterPosts editor in Chromium with the API stubbed at the
// network layer, for importing a BetterCricket template file (from the Canva
// app) onto the Blank canvas and filling its bound fields.
//
//   npx vite build && npx vite preview --port 5198 &
//   BG_PNG=/path/1080x1350.png node frontend/verification/verify_template_import_browser.mjs [baseUrl]
//
// What a build cannot tell you: that importing a file gives the exported post its
// shape, a locked design and a text block per field in the file's position, size
// and colour; that the Players panel (hidden on a plain Blank canvas) appears
// with the number of slots the template has; that adding players fills the slots
// in order and leaves the rest blank rather than printing "PLAYER 9"; that a word
// that is not a field stays plain text and is reported; that a bad file changes
// nothing; that importing again does not stack a second set of fields; and that
// Save as template keeps the bindings.
import { existsSync, readFileSync } from 'node:fs'
import { chromium } from 'playwright'
import { makeEditor, press, seen, tab, ROOT, shotNode } from './card_layouts_harness.mjs'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const BG = readFileSync(process.env.BG_PNG)
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => { if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) } }

const TEMPLATE = {
  format: 'bettercricket-template', version: 1, name: 'LineUp',
  canvas: { w: 1080, h: 1350 },
  background: `data:image/png;base64,${BG.toString('base64')}`,
  fields: [
    ...Array.from({ length: 11 }, (_, i) => ({ token: `player ${i + 1}`, x: 90, y: 300 + i * 62, w: 600, fontFamily: 'Anton', fontSize: 44, bold: true, color: '#ffe14d', align: 'left', uppercase: true, lineHeight: 1, letterSpacing: 1 })),
    { token: 'opponent', x: 90, y: 120, w: 800, fontFamily: 'Comic Sans MS', fontSize: 70, color: '#FFFFFF', align: 'center', uppercase: true },
    { token: 'date', x: 90, y: 1200, w: 400, fontFamily: 'Inter', fontSize: 30, color: '#ffffff' },
    { token: 'banana 7', x: 700, y: 1200, w: 300, fontFamily: 'Inter', fontSize: 30, color: '#ffffff' },
  ],
}

const read = (page) => page.evaluate((rootSrc) => {
  const root = (new Function(`return (${rootSrc})()`))()
  if (!root) return null
  const rr = root.getBoundingClientRect()
  const leaves = [...root.querySelectorAll('div')].filter((d) => d.children.length === 0 && d.innerText.trim() && d.style.width)
  const at = (y) => { const l = leaves.find((d) => Math.abs(d.getBoundingClientRect().top - rr.top - y) < 6); return l ? { text: l.innerText.trim(), color: getComputedStyle(l).color, size: parseFloat(getComputedStyle(l).fontSize), family: getComputedStyle(l).fontFamily, x: l.parentElement.getBoundingClientRect().left - rr.left, w: l.getBoundingClientRect().width } : null }
  const img = [...root.querySelectorAll('img')].find((i) => /social-media\/design/.test(i.getAttribute('src') || ''))
  const ir = img ? img.getBoundingClientRect() : null
  return { w: rr.width, h: rr.height, at, texts: leaves.map((d) => d.innerText.trim()),
    design: ir ? { x: ir.left - rr.left, y: ir.top - rr.top, w: ir.width, h: ir.height, pe: getComputedStyle(img.parentElement).pointerEvents } : null,
    count: leaves.length }
}, ROOT.toString())
// `at` is a function and cannot cross the wire: read rows by y here instead.
const rows = (page, ys) => page.evaluate(([rootSrc, ys]) => {
  const root = (new Function(`return (${rootSrc})()`))()
  if (!root) return null
  const rr = root.getBoundingClientRect()
  const leaves = [...root.querySelectorAll('div')].filter((d) => d.children.length === 0 && d.style.width)
  return ys.map((y) => {
    const l = leaves.find((d) => Math.abs(d.getBoundingClientRect().top - rr.top - y) < 8)
    if (!l) return null
    const cs = getComputedStyle(l)
    return { text: l.innerText.trim(), color: cs.color, size: parseFloat(cs.fontSize), family: cs.fontFamily, align: cs.textAlign, x: Math.round(l.getBoundingClientRect().left - rr.left) }
  })
}, [ROOT.toString(), ys])
const rootText = (page) => page.evaluate((rootSrc) => { const r = (new Function(`return (${rootSrc})()`))(); return r ? r.innerText.replace(/\s+/g, ' ') : '' }, ROOT.toString())
const flat = async (page) => { const r = await read(page); return r ? { ...r, at: undefined } : null }

async function open() {
  const e = await makeEditor(browser, BASE, { layout: 'BL1', size: 'square', viewport: { width: 1700, height: 1700 } })
  const { page } = e
  const uploads = [], puts = []
  await page.route('**/api/admin/social/media**', (route) => {
    if (route.request().method() !== 'POST') return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    uploads.push(1)
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'a1', name: 'LineUp.png', url: `/api/social-media/design-${uploads.length}`, kind: null }) })
  })
  await page.route('**/social-media/design-*', (route) => route.fulfill({ status: 200, contentType: 'image/png', body: BG }))
  await page.route('**/api/admin/social/templates/**', async (route) => {
    if (route.request().method() === 'PUT') { puts.push(route.request().postDataJSON()); return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) }) }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
  await tab(page, 'Content'); await page.waitForTimeout(300)
  return { ...e, uploads, puts }
}
const importFile = async (page, obj, name = 'lineup.json') => {
  const body = typeof obj === 'string' ? obj : JSON.stringify(obj)
  await page.getByTestId('template-file-input').setInputFiles({ name, mimeType: 'application/json', buffer: Buffer.from(body) }).catch(() => {})
  await page.waitForTimeout(1800)
}
const say = async (page) => (await page.locator('body').innerText()).replace(/\s+/g, ' ')
const ys = [300, 362, 424, 486, 548, 610, 672, 734, 796, 858, 920, 120, 1200]

// 1. Import, before any player is added.
{
  const { page, uploads, puts } = await open()
  ck('Players panel is hidden on a plain Blank canvas', !(await seen(page.getByPlaceholder('Search players...'))))
  await importFile(page, TEMPLATE)
  const r = await flat(page)
  ck('the post took the template\'s 1080x1350 shape', r && r.w === 1080 && r.h === 1350, JSON.stringify(r && [r.w, r.h]))
  ck('the design picture was uploaded once', uploads.length === 1, String(uploads.length))
  ck('design fills the post and is locked', r && r.design && r.design.w === 1080 && r.design.h === 1350 && r.design.pe === 'none', JSON.stringify(r && r.design))
  const g = await rows(page, ys)
  ck('player 1 slot sits at y 300 and shows its sample', g && g[0] && g[0].text === 'PLAYER 1', JSON.stringify(g && g[0]))
  ck('player 11 slot shows its sample', g && g[10] && g[10].text === 'PLAYER 11', JSON.stringify(g && g[10]))
  ck('slot colour comes from the file', g && g[0] && g[0].color === 'rgb(255, 225, 77)', JSON.stringify(g && g[0] && g[0].color))
  ck('slot size and left edge come from the file', g && g[0] && g[0].size === 44 && g[0].x === 90, JSON.stringify(g && g[0]))
  ck('a known font is used (Anton)', g && g[0] && /Anton/.test(g[0].family), JSON.stringify(g && g[0] && g[0].family))
  ck('opponent slot is centred and white', g && g[11] && g[11].align === 'center' && g[11].color === 'rgb(255, 255, 255)', JSON.stringify(g && g[11]))
  ck('an unknown font falls back to Inter', g && g[11] && /Inter/.test(g[11].family) && !/Comic/.test(g[11].family), JSON.stringify(g && g[11] && g[11].family))
  const t = await say(page)
  ck('the note says how many slots were imported', /Imported “LineUp”/.test(t) && /11 player slots/.test(t), t.slice(0, 0))
  ck('the note names the unknown font', /Comic Sans MS/.test(t))
  ck('the note names the word that is not a field', /banana 7/.test(t))
  ck('the untouched starter blocks are gone, so nothing sits over the design', r && !r.texts.some((x) => /PLAYERS WANTED|Join the club/.test(x)), JSON.stringify(r && r.texts.slice(0, 3)))
  ck('an unknown word stays as its own text', r && r.texts.some((x) => /banana 7/i.test(x)), JSON.stringify(r && r.texts.slice(-3)))
  ck('Players panel appears with 11 places', await seen(page.getByPlaceholder('Search players...')) && /0\/11/.test(await say(page)), '')

  // 2. Add three players: slots 1 to 3 fill, the rest go blank.
  for (const n of ['Pullinger, George', 'Hansberry, Chris', 'Timmins, Sam']) {
    await press(page.locator('button', { hasText: n })); await page.waitForTimeout(250)
  }
  await page.waitForTimeout(500)
  const f = await rows(page, ys)
  ck('slot 1 prints the first player', f && f[0] && /george/i.test(f[0].text) && /pullinger/i.test(f[0].text), JSON.stringify(f && f[0]))
  ck('slot 2 prints the second player', f && f[1] && /chris/i.test(f[1].text) && /hansberry/i.test(f[1].text), JSON.stringify(f && f[1]))
  ck('slot 3 prints the third player', f && f[2] && /timmins/i.test(f[2].text), JSON.stringify(f && f[2]))
  const after = await flat(page)
  ck('slots 4 to 11 print nothing, not "PLAYER 4"', after && !after.texts.some((x) => /^PLAYER \d+$/i.test(x)), JSON.stringify(after && after.texts.filter((x) => /^PLAYER/i.test(x))))
  ck('the count reads 3/11', /3\/11/.test(await say(page)))
  if (process.env.SHOTS) await shotNode(page, `${process.env.SHOTS}/lineup-3-players.png`)

  // 3. Opponent and date.
  const o = await rows(page, [120, 1200])
  ck('opponent still shows its sample until one is chosen', o && o[0] && /OPPONENT/.test(o[0].text), JSON.stringify(o && o[0]))
  ck('date prints the editor\'s match date', o && o[1] && o[1].text.length > 0 && !/^DATE$/i.test(o[1].text), JSON.stringify(o && o[1]))

  // 4. Fill all 11: the panel stops offering more.
  for (const n of ['Couch, Brody', 'Allen, Matt', 'Offer, Aaron', 'Spear, Regan', 'Turner, Angus', 'Egan, Noah', 'Cantrill, Josh', 'Cohen, Max']) {
    await press(page.locator('button', { hasText: n })); await page.waitForTimeout(150)
  }
  await page.waitForTimeout(400)
  ck('after 11 players the search box is gone (cap is the slot count)', !(await seen(page.getByPlaceholder('Search players...'))) && /11\/11/.test(await say(page)))
  const full = await rows(page, [920])
  ck('slot 11 now prints the eleventh player', full && full[0] && /cohen/i.test(full[0].text), JSON.stringify(full && full[0]))

  // 5. Import again: the fields are replaced, not doubled.
  const beforeFlat = await flat(page); const before = beforeFlat.count
  await importFile(page, TEMPLATE)
  const re = await flat(page)
  ck('importing again does not stack a second set of fields', re && re.count === before, `${before} -> ${re && re.count}`)
  ck('only one design picture after a re-import', re && re.design !== null)

  // 6. Save as template keeps the bindings.
  await tab(page, 'Design'); await page.waitForTimeout(400)
  await page.getByPlaceholder('Template name...').fill('LineUp').catch(() => {})
  await press(page.getByRole('button', { name: /^Save current$/ })); await page.waitForTimeout(1200)
  const saved = puts.length ? JSON.stringify(puts[puts.length - 1]) : ''
  ck('template save reached the server', puts.length >= 1, String(puts.length))
  ck('saved template keeps the player bindings', /"bind":"lineup\.1\.name"/.test(saved) && /"bind":"lineup\.11\.name"/.test(saved) && /"bind":"opponent"/.test(saved) && /"bind":"match\.date"/.test(saved), saved.slice(0, 200))
  ck('saved template keeps the design as a library address, not a blob', /social-media\/design/.test(saved) && !/blob:/.test(saved))
  await page.close()
}

// 6b. A block the club added itself survives an import (and so do the starter blocks then).
{
  const { page } = await open()
  await tab(page, 'Club data'); await page.waitForTimeout(300)
  await press(page.locator('button', { has: page.locator('div', { hasText: /^Fixtures$/ }) })); await page.waitForTimeout(600)
  await tab(page, 'Content'); await page.waitForTimeout(300)
  ck('the club\'s Fixtures block is on the post before the import', /No fixtures loaded|THIS WEEK/i.test(await rootText(page)))
  await importFile(page, TEMPLATE)
  const post = await flat(page)
  ck('the club\'s own block survives the import', /No fixtures loaded|THIS WEEK/i.test(await rootText(page)))
  ck('the template fields are there too', post && post.texts.includes('PLAYER 1'))
  await page.close()
}

// 7. Bad files change nothing and say why.
for (const [label, file, expect] of [
  ['not JSON', 'this is not json', /not JSON/],
  ['some other JSON', JSON.stringify({ hello: 'world' }), /not a BetterCricket template/],
  ['a newer version', JSON.stringify({ ...TEMPLATE, version: 2 }), /version 2/],
  ['no fields', JSON.stringify({ ...TEMPLATE, fields: [] }), /no fields/],
  ['a picture that is not an image', JSON.stringify({ ...TEMPLATE, background: 'data:text/html;base64,PGI+eDwvYj4=' }), /not a PNG, JPG or WebP/],
]) {
  const { page, uploads } = await open()
  const before = await flat(page)
  await importFile(page, file)
  const after = await flat(page)
  ck(`${label}: says why`, expect.test(await say(page)))
  ck(`${label}: nothing uploaded`, uploads.length === 0, String(uploads.length))
  ck(`${label}: the post is unchanged`, before && after && before.count === after.count && before.h === after.h, JSON.stringify([before && before.count, after && after.count]))
  ck(`${label}: no Players panel appeared`, !(await seen(page.getByPlaceholder('Search players...'))))
  await page.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
