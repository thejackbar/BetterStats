// What the browser captures from a Meta ad click, and the attribution record the
// registration wizard would then send. Written for the 10 Nov 2026 restart of
// BC_AU_Trial_CBO_Sep2026, where the live ad's website URL was changed from one
// with baked-in tags to a bare /trial and the tags moved to Ads Manager's "URL
// parameters" field.
//
//   npx vite --port 5204 &
//   PW_CHROMIUM=... ATTR_OUT=/tmp/attr node frontend/verification/verify_ad_attribution_capture_browser.mjs
//
// It also writes the captured records to ATTR_OUT/*.json, so the backend leg
// (backend/verification/verify_meta_ads_new_tags_e2e.py) registers a club with
// EXACTLY what the real browser produced rather than with a hand-typed copy.
//
// Three cases, because each answers a different question:
//   new       the live ad now: bare URL + Meta's appended parameters.
//   dupes     the shape BEFORE the fix: tags baked into the URL AND appended.
//             URLSearchParams.get() returns the FIRST value, so the old tags win.
//   returning a visitor who already holds a first-touch record from an earlier
//             click. getAttribution() never overwrites a stored signal.
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || process.env.APP_URL || 'http://127.0.0.1:5204'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium/chrome-linux/chrome'
const OUT = process.env.ATTR_OUT || '/tmp/attr'
mkdirSync(OUT, { recursive: true })

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const NEW_TAGS = 'utm_source=meta&utm_medium=paid_social&utm_campaign=BC_AU_Trial_CBO_Sep2026&utm_content=check_out_your_club_v2'
const OLD_TAGS = 'utm_source=facebook&utm_medium=paid_social&utm_campaign=bc_au_trials_cbo_aug2026&utm_content=checkout_your_club_v2'
// Meta puts its own click id after whatever else the URL carries.
const URLS = {
  new: `${BASE}/trial?${NEW_TAGS}&fbclid=IwAR_new_click`,
  dupes: `${BASE}/trial?${OLD_TAGS}&${NEW_TAGS}&fbclid=IwAR_dupe_click`,
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function visit(url, { seedAttr = null } = {}) {
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  const beacons = []
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  if (seedAttr) {
    await page.addInitScript((v) => { try { localStorage.setItem('bs_attr', v) } catch (_) {} }, JSON.stringify(seedAttr))
  }
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    if (/\/usage\/event$/.test(p) && req.method() === 'POST') {
      try { beacons.push(JSON.parse(req.postData() || '{}')) } catch (_) { /* ignore */ }
    }
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (/\/auth\/me/.test(p)) return route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"no"}' })
    return json([])
  })
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  // networkidle never settles here (heartbeat beacon): wait for the thing itself.
  await page.waitForFunction(() => !!localStorage.getItem('bs_attr'), null, { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(1200)
  const attr = await page.evaluate(() => JSON.parse(localStorage.getItem('bs_attr') || 'null'))
  const landing = await page.evaluate(() => JSON.parse(sessionStorage.getItem('bc:landingParams') || 'null'))
  // What the wizard sends: the same function SelfServeTrialModal calls on submit.
  const sent = await page.evaluate(async () => (await import('/src/lib/visitor.js')).getAttribution())
  await ctx.close()
  return { attr, landing, sent, beacons, errors }
}
const has = (o, k) => !!o && Object.prototype.hasOwnProperty.call(o, k)

// ── new: the live ad as it is now ────────────────────────────────────────────
{
  const r = await visit(URLS.new)
  ck('new: a first-touch record is stored', !!r.attr)
  ck('new: utm_source is meta', r.attr?.utm_source === 'meta', String(r.attr?.utm_source))
  ck('new: utm_medium is paid_social', r.attr?.utm_medium === 'paid_social')
  ck('new: utm_campaign is the campaign name, exactly as typed', r.attr?.utm_campaign === 'BC_AU_Trial_CBO_Sep2026', String(r.attr?.utm_campaign))
  ck('new: utm_content is the creative tag', r.attr?.utm_content === 'check_out_your_club_v2', String(r.attr?.utm_content))
  ck('new: the fbclid is captured and says facebook', r.attr?.click_id === 'IwAR_new_click' && r.attr?.click_source === 'facebook', JSON.stringify([r.attr?.click_id, r.attr?.click_source]))
  ck('new: it counts as a signal, so the signup is filed as an ad signup', r.attr?.has_signal === true)
  ck('new: the landing path keeps the query string (what the signups table shows)', /utm_content=check_out_your_club_v2/.test(r.attr?.landing_path || ''), String(r.attr?.landing_path))
  ck('new: the session copy agrees (it is what the pixel and the CTA bar read)', r.landing?.utm_campaign === 'BC_AU_Trial_CBO_Sep2026' && r.landing?.utm_content === 'check_out_your_club_v2', JSON.stringify(r.landing))
  ck('new: what the wizard would submit is the stored record', r.sent?.utm_campaign === r.attr?.utm_campaign && r.sent?.utm_content === r.attr?.utm_content)
  const beacon = r.beacons.find((b) => b && (b.utm_campaign || b.utm_content))
  ck('new: the page-view beacon on the wire carries the same tags', beacon?.utm_campaign === 'BC_AU_Trial_CBO_Sep2026' && beacon?.utm_content === 'check_out_your_club_v2' && beacon?.utm_source === 'meta', JSON.stringify(beacon || r.beacons.slice(0, 1)))
  ck('new: no page errors', r.errors.length === 0, r.errors.join(' | '))
  writeFileSync(`${OUT}/new.json`, JSON.stringify(r.sent))
}

// ── dupes: the shape before the fix ──────────────────────────────────────────
{
  const r = await visit(URLS.dupes)
  ck('dupes: the FIRST value of a repeated tag wins, so the OLD campaign is what is stored',
     r.attr?.utm_campaign === 'bc_au_trials_cbo_aug2026' && r.attr?.utm_content === 'checkout_your_club_v2' && r.attr?.utm_source === 'facebook',
     JSON.stringify([r.attr?.utm_source, r.attr?.utm_campaign, r.attr?.utm_content]))
  // The tag FIELDS, not the whole record: landing_path keeps the raw query string,
  // so both tag sets are visible there even though only the first set is parsed.
  const fields = JSON.stringify([r.attr?.utm_source, r.attr?.utm_medium, r.attr?.utm_campaign, r.attr?.utm_content])
  ck('dupes: and the new tags are in none of the tag fields', !fields.includes('BC_AU_Trial_CBO_Sep2026') && !fields.includes('check_out_your_club_v2') && !fields.includes('meta'), fields)
  ck('dupes: they are only visible in landing_path, which is the raw query string', /BC_AU_Trial_CBO_Sep2026/.test(r.attr?.landing_path || ''))
  ck('dupes: the session copy has the same problem', r.landing?.utm_campaign === 'bc_au_trials_cbo_aug2026', JSON.stringify(r.landing))
  writeFileSync(`${OUT}/dupes.json`, JSON.stringify(r.sent))
}

// ── returning: first touch is never overwritten by a later signal ────────────
{
  const earlier = JSON.parse(await (async () => {
    const r = await visit(URLS.dupes)
    return JSON.stringify(r.sent)
  })())
  const r = await visit(URLS.new, { seedAttr: earlier })
  ck('returning: a visitor who already held an earlier ad signal keeps it (first touch)',
     r.sent?.utm_campaign === 'bc_au_trials_cbo_aug2026' && r.sent?.utm_content === 'checkout_your_club_v2',
     JSON.stringify([r.sent?.utm_campaign, r.sent?.utm_content]))
  ck('returning: even though today\'s click carried the new tags', !!r.landing && r.landing.utm_campaign === 'BC_AU_Trial_CBO_Sep2026', JSON.stringify(r.landing))
  const beacon = r.beacons.find((b) => b && (b.utm_campaign || b.utm_content))
  ck('returning: the page-view beacon (today\'s click) carries the NEW tags while the signup would carry the OLD ones',
     beacon?.utm_campaign === 'BC_AU_Trial_CBO_Sep2026' && r.sent?.utm_campaign === 'bc_au_trials_cbo_aug2026',
     JSON.stringify([beacon?.utm_campaign, r.sent?.utm_campaign]))
  writeFileSync(`${OUT}/returning.json`, JSON.stringify(r.sent))
}

// ── no signal at all, then a signal (the one upgrade the code allows) ────────
{
  const r = await visit(`${BASE}/trial`, {})
  ck('direct visit: stored with no signal', has(r.attr, 'has_signal') && r.attr.has_signal === false)
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
