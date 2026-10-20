// Drives the real BetterPosts editor in Chromium (API stubbed at the network layer) for a
// BetterCricket template made for each post type other than the line up: it has to land on its
// own "Your template" layout on that type's tab, and its words have to fill from what the editor
// holds for the type.
//
//   npx vite build && npx vite preview --port 5198 &
//   node frontend/verification/verify_post_types_browser.mjs [baseUrl]
//
// A control run against the commit before this one fails every check that names a type.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'
import { makeEditor, press, seen, tab, ROOT } from './card_layouts_harness.mjs'

const BASE = process.argv[2] || 'http://127.0.0.1:5198'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => { if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) } }

const look = { fontSize: 40, bold: false, colorRole: 'ink', fontRole: 'body', align: 'left', uppercase: false }
const f = (token, y, extra = {}) => ({ token, x: 100, y, w: 800, ...look, ...extra })
const file = (postType, fields, extra = {}) => ({ format: 'bettercricket-template', version: 1, name: `T ${postType}`, postType, canvas: { w: 1080, h: 1080 }, fields, ...extra })

const text = (page) => page.evaluate((rootSrc) => { const r = (new Function(`return (${rootSrc})()`))(); return r ? r.innerText.replace(/\s+/g, ' ') : '' }, ROOT.toString())
const say = async (page) => (await page.locator('body').innerText()).replace(/\s+/g, ' ')
// The text at one y of the exported post, or null.
const at = (page, y) => page.evaluate(([rootSrc, y]) => {
  const root = (new Function(`return (${rootSrc})()`))()
  if (!root) return null
  const rr = root.getBoundingClientRect()
  const l = [...root.querySelectorAll('div')].filter((d) => d.children.length === 0 && d.style.width).find((d) => Math.abs(d.getBoundingClientRect().top - rr.top - y) < 8)
  return l ? l.innerText.trim() : null
}, [ROOT.toString(), y])
const imgs = (page) => page.evaluate((rootSrc) => { const r = (new Function(`return (${rootSrc})()`))(); return r ? [...r.querySelectorAll('img')].map((i) => ({ src: i.getAttribute('src') || '', w: Math.round(i.getBoundingClientRect().width) })) : [] }, ROOT.toString())

async function open(layout, opts = {}) {
  const e = await makeEditor(browser, BASE, { layout, size: 'square', viewport: { width: 1700, height: 1700 }, photos: opts.photos })
  await tab(e.page, 'Design'); await e.page.waitForTimeout(400)
  return e
}
// A page with no import box (the build before this one has it on the Lineup tab only) is reported by the checks, not a crash.
async function importFile(page, obj) {
  try {
    await page.getByTestId('template-paste').first().fill(JSON.stringify(obj), { timeout: 3000 })
    await page.getByTestId('template-paste-import').first().click({ timeout: 3000 })
  } catch { /* the checks that follow say what is missing */ }
  await page.waitForTimeout(1500)
}
const tabIsActive = async (page, label) => page.evaluate((l) => [...document.querySelectorAll('button')].filter((b) => b.innerText.trim().toLowerCase() === l.toLowerCase()).some((b) => /(^| )text-pb-accent/.test(b.className)), label)

// ── Fixtures ────────────────────────────────────────────────────────────────
{
  const { page, errors } = await open('FX1')
  await importFile(page, file('fixtures', [f('fixture 1 opponent', 200), f('fixture 1 grade', 260), f('fixture 1 time', 320), f('fixture 2 venue', 380), f('fixture 1 home away', 440), f('fixture 7 opponent', 500), f('opponent', 560)]))
  const t = await say(page)
  ck('fixtures: says it went to a Fixtures layout', /as a Fixtures layout called “Your template”/.test(t), t.slice(0, 200))
  ck('fixtures: the Fixtures tab stays the active one', await tabIsActive(page, 'Fixtures'))
  ck('fixtures: row 1 opponent comes from the Fixtures tab', (await at(page, 200)) === 'SUBIACO-FLOREAT', await at(page, 200))
  ck('fixtures: row 1 grade', (await at(page, 260)) === '1ST XI', await at(page, 260))
  ck('fixtures: row 1 time', (await at(page, 320)) === '12:30 PM', await at(page, 320))
  ck('fixtures: row 2 venue', (await at(page, 380)) === 'BURRENDAH RES', await at(page, 380))
  ck('fixtures: home or away prints a word', (await at(page, 440)) === 'HOME', await at(page, 440))
  ck('fixtures: a row the club has not got prints nothing, not the sample', ((await at(page, 500)) ?? '') === '', await at(page, 500))
  ck('fixtures: no console errors', errors.length === 0, errors.join(' | '))
  await page.close()
}

// ── Results ─────────────────────────────────────────────────────────────────
{
  const { page } = await open('RR1')
  await importFile(page, file('results', [f('result 1 opponent', 200), f('result 1 our score', 260), f('result 1 their score', 320), f('result 1 outcome', 380), f('result 2 margin', 440)]))
  ck('results: row 1 opponent', (await at(page, 200)) === 'SUBIACO-FLOREAT', await at(page, 200))
  ck('results: our score', (await at(page, 260)) === '6/188', await at(page, 260))
  ck('results: their score', (await at(page, 320)) === '184', await at(page, 320))
  ck('results: the outcome is a word', (await at(page, 380)) === 'WIN', await at(page, 380))
  ck('results: row 2 margin', /RUNS/.test((await at(page, 440)) || ''), await at(page, 440))
  await page.close()
}

// ── Toss ────────────────────────────────────────────────────────────────────
{
  const { page } = await open('C2')
  await importFile(page, file('toss', [f('toss', 200), f('toss winner', 260), f('toss decision', 320), f('competition', 380)]))
  const t = await say(page)
  ck('toss: lands on the Toss tab as Your template', /as a Toss layout called “Your template”/.test(t), t.slice(0, 200))
  ck('toss: the toss panel is still there to edit it', /Toss Won By/i.test(t))
  ck('toss: sentence', (await at(page, 200)) === 'SCARBOROUGH CRICKET CLUB WON THE TOSS', await at(page, 200))
  ck('toss: winner', (await at(page, 260)) === 'SCARBOROUGH CRICKET CLUB', await at(page, 260))
  ck('toss: decision', (await at(page, 320)) === 'BAT', await at(page, 320))
  // Change the decision in the panel and the post follows.
  await tab(page, 'Content'); await page.waitForTimeout(300)
  const sel = page.locator('select').filter({ has: page.locator('option[value="BOWL"]') }).first()
  await sel.selectOption('BOWL')
  await page.waitForTimeout(500)
  ck('toss: choosing bowl in the panel changes the post', (await at(page, 320)) === 'BOWL', await at(page, 320))
  await page.close()
}

// ── Announcement ────────────────────────────────────────────────────────────
{
  const { page } = await open('C1', { photos: ['p1'] })
  await importFile(page, file('announcement', [f('announcement headline', 200), f('announcement subheadline', 260), f('announcement kind', 320), f('announcement name', 380), f('announcement photo', 440, { h: 300, w: 300 })]))
  ck('announcement: headline', (await at(page, 200)) === 'NAMED CAPTAIN', await at(page, 200))
  ck('announcement: subheadline', /FOR THE/.test((await at(page, 260)) || ''), await at(page, 260))
  ck('announcement: kind', (await at(page, 320)) === 'APPOINTMENT', await at(page, 320))
  ck('announcement: no player yet prints no name', ((await at(page, 380)) ?? '') === '', await at(page, 380))
  ck('announcement: with no player the photo area shows its label', /ANNOUNCEMENT PHOTO/i.test(await text(page)))
  await tab(page, 'Content'); await page.waitForTimeout(300)
  await press(page.locator('button', { hasText: 'Pullinger, George' })); await page.waitForTimeout(600)
  ck('announcement: choosing a player fills the name', /george/i.test((await at(page, 380)) || '') && /pullinger/i.test((await at(page, 380)) || ''), await at(page, 380))
  const pics = await imgs(page)
  ck('announcement: and the photo area shows that player\'s photo at the size the template drew', pics.some((i) => /images\/players\/p1\/photo/.test(i.src) && i.w === 300), JSON.stringify(pics))
  await page.close()
}

// ── Events ──────────────────────────────────────────────────────────────────
{
  const { page } = await open('EV1')
  await importFile(page, file('events', [f('event title', 200), f('event kicker', 260), f('event date', 320), f('event venue', 380), f('event price', 440), f('event cta', 500)]))
  const t = await say(page)
  ck('events: lands on the Events tab', /as a Events layout called “Your template”|as an? Events? layout/.test(t) || /layout called “Your template”/.test(t), t.slice(0, 200))
  ck('events: title comes from the event form', (await at(page, 200)) === 'Curry Night', await at(page, 200))
  ck('events: kicker', (await at(page, 260)) === 'Club Social', await at(page, 260))
  ck('events: date', (await at(page, 320)) === 'Fri 18 Jul', await at(page, 320))
  ck('events: price', /25/.test((await at(page, 440)) || ''), await at(page, 440))
  await page.close()
}

// ── Final score, player of the match, team of the week, milestones ──────────
{
  const { page } = await open('RS1')
  await importFile(page, file('result', [f('our score', 200), f('opponent score', 260), f('result', 320), f('margin', 380), f('our batter 1 name', 440)]))
  const t = await say(page)
  ck('result: lands on the Final Score tab', /as a Final Score layout called “Your template”/.test(t), t.slice(0, 200))
  ck('result: nothing typed yet shows the sample label, not blanks', /OUR SCORE|Our score/i.test(await text(page)), (await text(page)).slice(0, 200))
  await tab(page, 'Content'); await page.waitForTimeout(300)
  await page.locator('input[placeholder="6/188"]').first().fill('6/188')
  await page.waitForTimeout(500)
  ck('result: typing our score in the Final Score panel fills it', (await at(page, 200)) === '6/188', await at(page, 200))
  ck('result: and the result word follows the winner', (await at(page, 320)) === 'WIN', await at(page, 320))
  await page.close()
}
{
  const { page } = await open('C3', { photos: ['p1'] })
  await importFile(page, file('motm', [f('potm name', 200), f('potm line', 260), f('stat 1 value', 320), f('stat 1 label', 380), f('potm photo', 440, { w: 300, h: 300 })]))
  const t = await say(page)
  ck('motm: lands on the Player of Match tab', /as a Player of Match layout called “Your template”/.test(t), t.slice(0, 200))
  ck('motm: shows sample labels before a player is chosen', /Player of the match/i.test(await text(page)), (await text(page)).slice(0, 200))
  await tab(page, 'Content'); await page.waitForTimeout(300)
  await press(page.locator('button', { hasText: 'Pullinger, George' })); await page.waitForTimeout(600)
  ck('motm: the chosen player fills the name', /pullinger/i.test((await at(page, 200)) || ''), await at(page, 200))
  ck('motm: and their photo', (await imgs(page)).some((i) => /images\/players\/p1\/photo/.test(i.src) && i.w === 300))
  const stat = page.getByPlaceholder('Runs').first()
  await page.locator('input[placeholder="84"], input[placeholder="Value"], input[placeholder*="64"]').first().fill('84').catch(() => {})
  await page.waitForTimeout(300)
  await page.close()
}
{
  const { page } = await open('TW1')
  await importFile(page, file('totw', [f('totw 1 name', 200), f('totw 2 name', 260), f('totw 1 line', 320)]))
  const t = await say(page)
  ck('totw: lands on the Team of the Week tab', /as a Team of the Week layout called “Your template”/.test(t), t.slice(0, 200))
  await tab(page, 'Content'); await page.waitForTimeout(300)
  for (const n of ['Pullinger, George', 'Hansberry, Chris']) { await press(page.locator('button', { hasText: n })); await page.waitForTimeout(300) }
  await page.waitForTimeout(400)
  ck('totw: row 1 is the first player on the post', /pullinger/i.test((await at(page, 200)) || ''), await at(page, 200))
  ck('totw: row 2 is the second', /hansberry/i.test((await at(page, 260)) || ''), await at(page, 260))
  await page.close()
}
{
  const { page } = await open('MS1')
  await importFile(page, file('milestones', [f('milestone 1 name', 200), f('milestone 1 value', 260), f('milestone title', 320)]))
  const t = await say(page)
  ck('milestones: lands on the Milestones tab', /as a Milestones layout called “Your template”/.test(t), t.slice(0, 200))
  await page.close()
}

// ── A template for one type does not land on another, and a general one goes to Blank ──
{
  const { page } = await open('FX1')
  await importFile(page, file('toss', [f('toss', 200)]))
  const t = await say(page)
  ck('moving between tabs: a toss template imported from Fixtures goes to the Toss layout', /as a Toss layout called “Your template”/.test(t), t.slice(0, 200))
  await page.close()
}
{
  const { page } = await open('FX1')
  await importFile(page, file('general', [f('opponent', 200)]))
  const t = await say(page)
  ck('a general template still goes to the Blank canvas', /as a Blank canvas post/.test(t), t.slice(0, 200))
  await page.close()
}
{
  const { page } = await open('FX1')
  await importFile(page, file('fixtures', [f('opponent', 200)]))
  const t = await say(page)
  ck('a fixtures template with none of its words says so', /none of its fields/.test(t), t.slice(0, 300))
  await page.close()
}
await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
