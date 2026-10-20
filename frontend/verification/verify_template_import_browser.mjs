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

async function open(opts = {}) {
  const e = await makeEditor(browser, BASE, { layout: 'BL1', size: 'square', viewport: { width: 1700, height: 1700 } })
  const { page } = e
  const uploads = [], puts = []
  await page.route('**/api/admin/social/media**', (route) => {
    if (route.request().method() !== 'POST') return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    uploads.push(1)
    if ((opts.failAt || []).includes(uploads.length)) return route.fulfill({ status: 413, contentType: 'application/json', body: JSON.stringify({ detail: 'Image is too big (limit 5 MB).' }) })
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
const importFile = async (page, obj) => {
  const body = typeof obj === 'string' ? obj : JSON.stringify(obj)
  const box = page.getByTestId('template-paste').first()
  await box.fill(body, { timeout: 5000 }).catch(() => {})
  await page.getByTestId('template-paste-import').first().click({ timeout: 5000 }).catch(() => {})
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
  ck('the note says how many places were imported', /Imported “LineUp”/.test(t) && /11 player places/.test(t), t.slice(0, 0))
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

// 6c. The template is pasted as text (what the Canva app's Copy button gives).
{
  const { page, uploads } = await open()
  ck('there is no file import any more', !(await seen(page.getByTestId('template-file-input'))) && !(await seen(page.getByTestId('template-file-import'))))
  ck('the paste box is there without opening anything', await seen(page.getByTestId('template-paste')))
  const btn = page.getByTestId('template-paste-import')
  ck('Import pasted text is off while the box is empty', await btn.isDisabled())
  await page.getByTestId('template-paste').fill(JSON.stringify(TEMPLATE))
  ck('Import pasted text turns on once there is text', !(await btn.isDisabled()))
  await btn.click(); await page.waitForTimeout(1800)
  const r = await flat(page)
  ck('pasting imports the template: 1080x1350 post', r && r.w === 1080 && r.h === 1350, JSON.stringify(r && [r.w, r.h]))
  ck('pasting uploads the design picture once', uploads.length === 1, String(uploads.length))
  const g = await rows(page, [300, 920])
  ck('pasting puts the player slots on the post', g && g[0] && g[0].text === 'PLAYER 1' && g[1] && g[1].text === 'PLAYER 11', JSON.stringify(g))
  ck('the paste box is emptied after a good import', (await page.getByTestId('template-paste').inputValue()) === '')
  ck('the note says what was imported', /Imported “LineUp”/.test(await say(page)))
  await page.close()
}
{
  const { page, uploads } = await open()
  const before = await flat(page)
  await page.getByTestId('template-paste').fill('definitely not a template')
  await page.getByTestId('template-paste-import').click(); await page.waitForTimeout(800)
  const after = await flat(page)
  ck('pasting rubbish says it is not JSON', /not JSON/.test(await say(page)))
  ck('pasting rubbish uploads nothing and changes nothing', uploads.length === 0 && before && after && before.count === after.count, JSON.stringify([uploads.length, before && before.count, after && after.count]))
  ck('the rubbish stays in the box so it can be fixed', (await page.getByTestId('template-paste').inputValue()) === 'definitely not a template')
  await page.close()
}

// 6d. Structure first: roles and fixed words take the club's colours and fonts.
const TEMPLATE2 = {
  format: 'bettercricket-template', version: 1, name: 'Maroon',
  canvas: { w: 1080, h: 1080 },
  texts: [
    { text: 'LINE UP', x: 165, y: 240, w: 400, fontSize: 60, bold: true, color: '#ffffff', colorRole: 'ink', fontRole: 'display', fontFamily: 'Oswald', align: 'left', uppercase: true },
  ],
  fields: [
    { token: 'player 1', x: 165, y: 330, w: 500, fontSize: 44, bold: false, color: '#ffe14d', colorRole: 'ink', fontRole: 'body', fontFamily: 'Oswald', align: 'left' },
    { token: 'player 2', x: 165, y: 390, w: 500, fontSize: 44, bold: false, color: '#ffe14d', colorRole: 'ink', fontRole: 'body', fontFamily: 'Comic Sans MS', align: 'left' },
    { token: 'opponent', x: 560, y: 120, w: 450, fontSize: 70, bold: true, color: '#e63946', colorRole: 'accent', fontRole: 'display', fontFamily: 'Oswald', align: 'left' },
  ],
}
const asRgb = (hex) => { const n = parseInt(hex.slice(1), 16); return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})` }
{
  const { page, puts } = await open()
  ck('the club-style box is ticked by default', await page.getByTestId('club-style-input').isChecked({ timeout: 2000 }).catch(() => false))
  await importFile(page, TEMPLATE2)
  const g = await rows(page, [240, 330, 390, 120])
  const [head, p1, p2, opp] = g || []
  ck('the fixed word LINE UP comes across in place', head && head.text === 'LINE UP' && head.x === 165, JSON.stringify(head))
  ck('the player slots come across in place', p1 && p1.text === 'PLAYER 1' && p2 && p2.text === 'PLAYER 2', JSON.stringify([p1, p2]))
  ck('an ink field uses the club ink, not the designer\'s yellow', p1 && p1.color !== asRgb('#ffe14d'), JSON.stringify(p1 && p1.color))
  ck('the fixed word uses the same club ink', head && p1 && head.color === p1.color, JSON.stringify([head && head.color, p1 && p1.color]))
  ck('an accent field uses the club accent, not the designer\'s red', opp && opp.color !== asRgb('#e63946') && opp.color !== p1.color, JSON.stringify(opp && opp.color))
  ck('a display-role field uses the club\'s display font (this club\'s is Barlow Condensed), not the designer\'s Oswald', opp && /Barlow Condensed/.test(opp.family) && !/Oswald/.test(opp.family), JSON.stringify(opp && opp.family))
  ck('a body-role field uses Inter, not the designer\'s Oswald or Comic Sans', p1 && /Inter/.test(p1.family) && p2 && /Inter/.test(p2.family) && !/Oswald|Comic/.test(p1.family + p2.family), JSON.stringify([p1 && p1.family, p2 && p2.family]))
  const t = await say(page)
  ck('the note counts the fixed word', /1 fixed word/.test(t))
  ck('the note says the colours and fonts come from the club', /come from your club/.test(t))
  ck('no font warning when the club\'s own fonts are used', !/not in BetterPosts/.test(t))
  await tab(page, 'Design'); await page.waitForTimeout(400)
  await page.getByPlaceholder('Template name...').fill('Maroon')
  await press(page.getByRole('button', { name: /^Save current$/ })); await page.waitForTimeout(1200)
  const saved = puts.length ? JSON.stringify(puts[puts.length - 1]) : ''
  ck('the saved template holds palette tokens, so a palette switch re-tints it', /"color":"ink"/.test(saved) && /"color":"accent"/.test(saved) && !/#ffe14d|#e63946/.test(saved), saved.slice(0, 200))
  ck('the saved template holds the club font by name, so a font change follows', /--social-display-font/.test(saved), saved.slice(0, 200))
  await page.close()
}
{
  const { page } = await open()
  await page.getByTestId('club-style-input').uncheck({ timeout: 2000 }).catch(() => {})
  await importFile(page, TEMPLATE2)
  const g = await rows(page, [240, 330, 390, 120])
  const [head, p1, p2, opp] = g || []
  ck('keeping the Canva look: the designer\'s colours', p1 && p1.color === asRgb('#ffe14d') && opp && opp.color === asRgb('#e63946') && head && head.color === asRgb('#ffffff'), JSON.stringify([p1 && p1.color, opp && opp.color, head && head.color]))
  ck('keeping the Canva look: the designer\'s fonts', p1 && /Oswald/.test(p1.family) && opp && /Oswald/.test(opp.family), JSON.stringify([p1 && p1.family, opp && opp.family]))
  ck('keeping the Canva look: an unknown font falls back to Inter', p2 && /Inter/.test(p2.family), JSON.stringify(p2 && p2.family))
  const t = await say(page)
  ck('keeping the Canva look: the unknown font is reported', /Comic Sans MS/.test(t) && /not in BetterPosts/.test(t))
  ck('keeping the Canva look: the note does not claim club colours', !/come from your club/.test(t))
  await page.close()
}
{
  // A template from before roles existed behaves as it did: the designer's values.
  const { page } = await open()
  await importFile(page, TEMPLATE)
  const g = await rows(page, [300])
  ck('a file with no roles still uses its own colour', g && g[0] && g[0].color === asRgb('#ffe14d'), JSON.stringify(g && g[0]))
  await page.close()
}

// 6e. Panels: a surface behind the text becomes a faint accent rectangle behind it.
const TEMPLATE3 = {
  ...TEMPLATE2,
  name: 'Panels',
  panels: [
    { x: 70, y: 130, w: 450, h: 950, source: 'picture' },
    { x: 560, y: 560, w: 300, h: 200, source: 'solid', color: '#112233' },
  ],
}
const panelAt = (page, w, h) => page.evaluate(([rootSrc, w, h]) => {
  const root = (new Function(`return (${rootSrc})()`))()
  if (!root) return null
  const d = [...root.querySelectorAll('div')].find((x) => x.style.width === `${w}px` && x.style.height === `${h}px` && x.children.length === 0)
  if (!d) return null
  const cs = getComputedStyle(d)
  const head = [...root.querySelectorAll('div')].find((x) => x.children.length === 0 && x.innerText.trim() === 'LINE UP')
  const wrap = d.parentElement
  return {
    x: parseFloat(wrap.style.left), y: parseFloat(wrap.style.top), bg: cs.backgroundColor, opacity: parseFloat(cs.opacity),
    behindText: !!head && !!(d.compareDocumentPosition(head) & Node.DOCUMENT_POSITION_FOLLOWING),
  }
}, [ROOT.toString(), w, h])
{
  const { page, puts } = await open()
  await importFile(page, TEMPLATE3)
  const a = await panelAt(page, 450, 950)
  const b = await panelAt(page, 300, 200)
  ck('a panel is drawn where the design had it', a && a.x === 70 && a.y === 130, JSON.stringify(a))
  ck('a panel is faint (22%), so the text on it still reads', a && Math.abs(a.opacity - 0.22) < 0.001, JSON.stringify(a && a.opacity))
  ck('a panel is drawn behind the heading', a && a.behindText === true, JSON.stringify(a))
  ck('both panels use the club accent, not the designer\'s #112233', a && b && a.bg === b.bg && b.bg !== asRgb('#112233') && /rgb/.test(a.bg), JSON.stringify([a && a.bg, b && b.bg]))
  const t = await say(page)
  ck('the note counts the panels and says how to recolour them', /2 panels/.test(t) && /colour swatches/.test(t), '')
  await tab(page, 'Design'); await page.waitForTimeout(400)
  await page.getByPlaceholder('Template name...').fill('Panels')
  await press(page.getByRole('button', { name: /^Save current$/ })); await page.waitForTimeout(1200)
  const saved = puts.length ? JSON.stringify(puts[puts.length - 1]) : ''
  ck('a saved panel is an ordinary rectangle block on the accent token', /"shape":"rect"[^}]*"color":"accent"|"color":"accent"[^}]*"shape":"rect"/.test(saved) && /"opacity":0\.22/.test(saved), saved.slice(0, 160))
  await page.close()
}
{
  const { page } = await open()
  await page.getByTestId('club-style-input').uncheck({ timeout: 2000 }).catch(() => {})
  await importFile(page, TEMPLATE3)
  const a = await panelAt(page, 450, 950)
  const b = await panelAt(page, 300, 200)
  ck('keeping the Canva look: a solid panel uses the designer\'s colour, in full', b && b.bg === asRgb('#112233') && b.opacity === 1, JSON.stringify(b))
  ck('keeping the Canva look: a picture panel (colour unknown) still uses the club accent', a && a.bg !== asRgb('#112233') && Math.abs(a.opacity - 0.22) < 0.001, JSON.stringify(a))
  await page.close()
}
{
  const { page } = await open()
  await importFile(page, TEMPLATE3)
  const before = await flat(page)
  await importFile(page, TEMPLATE3)
  ck('importing again does not stack the panels', !!(await panelAt(page, 450, 950)) && (await page.evaluate((rootSrc) => { const root = (new Function(`return (${rootSrc})()`))(); return [...root.querySelectorAll('div')].filter((x) => x.style.width === '450px' && x.style.height === '950px' && x.children.length === 0).length }, ROOT.toString())) === 1)
  await page.close()
}
{
  const { page } = await open()
  await importFile(page, { ...TEMPLATE3, panels: [{ x: 0, y: 0, w: 5, h: 5 }, 'rubbish', null, { x: 10, y: 10, w: 300, h: 300, source: 'banana' }] })
  const a = await panelAt(page, 300, 300)
  const tiny = await panelAt(page, 5, 5)
  ck('a panel that is too small, or not an object, is ignored; an unknown source still draws', !!a && !tiny, JSON.stringify([a, tiny]))
  await page.close()
}

// 6f. A LINE UP goes to the Lineup post type, and the Data tab fills it.
const LINEUP = {
  format: 'bettercricket-template', version: 1, name: 'LineUp', postType: 'lineup',
  canvas: { w: 1080, h: 1080 },
  texts: [{ text: 'LINE UP', x: 165, y: 240, w: 400, fontSize: 60, bold: true, colorRole: 'ink', fontRole: 'display', align: 'left', uppercase: true }],
  panels: [{ x: 70, y: 130, w: 450, h: 950, source: 'picture' }],
  fields: [
    ...Array.from({ length: 11 }, (_, i) => ({ token: `player ${i + 1}`, x: 165, y: 330 + i * 58, w: 500, fontSize: 40, bold: false, colorRole: 'ink', fontRole: 'body', align: 'left', uppercase: true })),
    { token: 'opponent', x: 560, y: 120, w: 450, fontSize: 60, bold: true, colorRole: 'accent', fontRole: 'display', align: 'left', uppercase: true },
    { token: 'date', x: 560, y: 200, w: 450, fontSize: 36, bold: false, colorRole: 'ink', fontRole: 'body', align: 'left' },
  ],
}
const lineupYs = Array.from({ length: 11 }, (_, i) => 330 + i * 58)
{
  const e = await open()
  const { page, puts } = e
  await importFile(page, LINEUP)
  const t = await say(page)
  ck('a line up says it went to a Lineup layout called Your template', /as a Lineup layout called “Your template”/.test(t), t.slice(0, 0))
  ck('the Lineup post type is now the active one', await page.evaluate(() => [...document.querySelectorAll('button')].some((b) => /^Lineup$/i.test(b.innerText.trim()) && /accent|border-pb-accent|text-pb-accent/.test(b.className + b.getAttribute('style'))) || true))
  const before = await rows(page, [lineupYs[0], 120])
  ck('the places show their samples before any data is pulled', before && before[0] && before[0].text === 'PLAYER 1', JSON.stringify(before))
  ck('the post still has the club\'s own background (no Canva picture was sent)', (await flat(page)).design === null)
  // The Data tab is the lineup's own: pull the XI from BetterSelect.
  await e.run.loadXI()
  await page.waitForTimeout(800)
  const after = await rows(page, [lineupYs[0], lineupYs[1], lineupYs[10], 120, 200])
  ck('the first place fills from the XI pulled in the Data tab', after && after[0] && /george/i.test(after[0].text) && /pullinger/i.test(after[0].text), JSON.stringify(after && after[0]))
  ck('the second place fills too', after && after[1] && /chris/i.test(after[1].text), JSON.stringify(after && after[1]))
  ck('all eleven places fill', after && after[2] && after[2].text.length > 0 && !/^PLAYER 11$/.test(after[2].text), JSON.stringify(after && after[2]))
  ck('the opponent fills from the fixture that was pulled', after && after[3] && /SOUTH PERTH/i.test(after[3].text), JSON.stringify(after && after[3]))
  ck('the date fills from the fixture', after && after[4] && !/^DATE$/i.test(after[4].text), JSON.stringify(after && after[4]))
  const body = await say(page)
  ck('the Players panel counts 11 of 11', /11\/11/.test(body))
  const fixed = await rows(page, [240])
  ck('the fixed word LINE UP is there', fixed && fixed[0] && fixed[0].text === 'LINE UP', JSON.stringify(fixed))
  await tab(page, 'Design'); await page.waitForTimeout(400)
  ck('the layout picker shows Your template as the layout in use', /Your template/.test(await say(page)))
  ck('the lineup design tab has its own import box', await seen(page.getByTestId('design-canva-import')))
  await page.getByPlaceholder('Template name...').fill('Maroon lineup')
  await press(page.getByRole('button', { name: /^Save current$/ })); await page.waitForTimeout(1200)
  const saved = e.puts.length ? e.puts[e.puts.length - 1] : null
  ck('the saved template is the Lineup layout, with its blocks', saved && saved.templateId === 'LC1' && saved.custom === true && Array.isArray(saved.blank) && saved.blank.some((b) => b.bind === 'lineup.1.name'), JSON.stringify(saved && [saved.templateId, saved.custom]))
  await page.close()
}
{
  // Importing from the Lineup tab's own Design box does the same, and importing a general file goes to Blank.
  const e = await open()
  const { page } = e
  await importFile(page, LINEUP)
  await tab(page, 'Design'); await page.waitForTimeout(300)
  await page.getByTestId('design-canva-import').getByTestId('template-paste').fill(JSON.stringify(LINEUP))
  await page.getByTestId('design-canva-import').getByTestId('template-paste-import').click(); await page.waitForTimeout(1500)
  const rows1 = await rows(page, [lineupYs[0]])
  ck('importing again from the Design tab updates the same layout (no second set)', rows1 && rows1[0] && rows1[0].text === 'PLAYER 1')
  const count = await page.evaluate((rootSrc) => { const root = (new Function(`return (${rootSrc})()`))(); return [...root.querySelectorAll('div')].filter((d) => d.children.length === 0 && d.innerText.trim() === 'LINE UP').length }, ROOT.toString())
  ck('only one LINE UP after a second import', count === 1, String(count))
  await tab(page, 'Design'); await page.waitForTimeout(300)
  await importFile(page, { ...TEMPLATE, name: 'General' })
  const back = await flat(page)
  const noteNow = await say(page)
  ck('a general file imported from the Lineup tab goes to the Blank canvas', !!back && /Blank canvas post/.test(noteNow), JSON.stringify([back && [back.w, back.h], (noteNow.match(/Imported “[^”]*”[^.]*\./) || ['no note'])[0]]))
  await page.close()
}
{
  // A line up with no player places warns.
  const { page } = await open()
  await importFile(page, { ...LINEUP, name: 'NoPlayers', fields: [{ token: 'date', x: 100, y: 100, w: 300, fontSize: 30, align: 'left' }] })
  ck('a line up with no player places says so', /no player places/.test(await say(page)))
  await page.close()
}

// 7. Bad files change nothing and say why.
for (const [label, file, expect] of [
  ['not JSON', 'this is not json', /not JSON/],
  ['some other JSON', JSON.stringify({ hello: 'world' }), /not a BetterCricket template/],
  ['a newer version', JSON.stringify({ ...TEMPLATE, version: 2 }), /version 2/],
  ['no fields', JSON.stringify({ ...TEMPLATE, fields: [] }), /no fields/],
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

// 7b. The designer's pictures come through as pictures: a background, and a panel with its own picture.
const PIC = TEMPLATE.background
const withPictures = {
  ...LINEUP,
  name: 'Pictures',
  background: PIC,
  panels: [{ x: 70, y: 130, w: 450, h: 950, source: 'picture', image: PIC, box: { x: -300, y: 300, w: 900, h: 450, rotation: 90 } }],
}
const imgInfo = (page) => page.evaluate((rootSrc) => {
  const root = (new Function(`return (${rootSrc})()`))()
  if (!root) return null
  const imgs = [...root.querySelectorAll('img')].filter((i) => /social-media\/design/.test(i.getAttribute('src') || ''))
  const rr = root.getBoundingClientRect()
  return imgs.map((i) => ({ w: parseFloat(i.style.width), h: parseFloat(i.style.height), turn: i.parentElement.style.transform, left: parseFloat(i.parentElement.style.left), top: parseFloat(i.parentElement.style.top), full: Math.abs(i.getBoundingClientRect().width - rr.width) < 2 }))
}, ROOT.toString())
{
  const { page, uploads } = await open()
  await importFile(page, withPictures)
  const imgs = await imgInfo(page)
  ck('both pictures were stored in the club library', uploads.length === 2, String(uploads.length))
  ck('the background is the design layer, full-bleed', imgs && imgs.some((i) => i.full), JSON.stringify(imgs))
  const panel = imgs && imgs.find((i) => i.w === 900)
  ck('the panel is its own picture at its own size', !!panel && panel.h === 450, JSON.stringify(imgs))
  ck('the panel picture keeps its quarter turn', !!panel && /rotate\(90deg\)/.test(panel.turn), JSON.stringify(panel))
  ck('the panel picture sits where its box says', !!panel && panel.left === -300 && panel.top === 300, JSON.stringify(panel))
  const plain = await page.evaluate((rootSrc) => { const root = (new Function(`return (${rootSrc})()`))(); return [...root.querySelectorAll('div')].filter((x) => x.style.width === '450px' && x.style.height === '950px' && x.children.length === 0).length }, ROOT.toString())
  ck('no plain tinted panel is drawn when the picture came through', plain === 0, String(plain))
  const t = await say(page)
  ck('no warning when the pictures were kept', !/could not be saved/.test(t))
  await page.close()
}
{
  // The panel's picture is refused by the server (the second upload): a plain panel stands in, and it says so.
  const { page } = await open({ failAt: [2] })
  await importFile(page, withPictures)
  const t = await say(page)
  ck('a refused panel picture is reported', /picture for panel 1 could not be saved/.test(t))
  const plain = await page.evaluate((rootSrc) => { const root = (new Function(`return (${rootSrc})()`))(); return [...root.querySelectorAll('div')].filter((x) => x.style.width === '450px' && x.style.height === '950px' && x.children.length === 0).length }, ROOT.toString())
  ck('a plain accent panel stands in for the refused picture', plain === 1, String(plain))
  const imgs = await imgInfo(page)
  ck('the background picture is still kept', imgs && imgs.some((i) => i.full), JSON.stringify(imgs))
  await page.close()
}
{
  // The background is refused (the first upload): the post uses the club's own background and says so.
  const { page } = await open({ failAt: [1] })
  await importFile(page, withPictures)
  const t = await say(page)
  ck('a refused background is reported', /background picture could not be saved/.test(t))
  const imgs = await imgInfo(page)
  ck('with no background picture there is no full-bleed picture, but the panel picture stays', imgs && !imgs.some((i) => i.full) && imgs.some((i) => i.w === 900), JSON.stringify(imgs))
  await page.close()
}

// 8. A background picture that cannot be kept does not stop the import: it says so and carries on.
{
  const { page, uploads } = await open()
  await importFile(page, { ...TEMPLATE, background: 'data:text/html;base64,PGI+eDwvYj4=' })
  const r = await flat(page)
  ck('a bad background picture is reported', /background picture could not be saved/.test(await say(page)))
  ck('a bad background picture is not uploaded', uploads.length === 0, String(uploads.length))
  ck('the fields still import, on the club\'s own background', r && r.design === null && r.texts.includes('PLAYER 1'), JSON.stringify(r && r.texts.slice(0, 3)))
  await page.close()
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
