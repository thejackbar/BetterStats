// Drives the real BetterSocials screen in Chromium with the API stubbed at the
// network layer and asserts what goes ON THE WIRE: every request the post
// builder makes carries `X-Publishing: 1` (so the server leaves out anyone who
// asked to be removed from the public site), and a screen that does not publish
// does not send it. The second half is the control: a header sent everywhere
// would make the first half meaningless.
//
//   npx vite build --outDir /tmp/dist_pub && npx vite preview --outDir /tmp/dist_pub --port 5205 &
//   node frontend/verification/verify_publishing_header_browser.mjs [baseUrl]
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5205'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function visit(path) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  await ctx.addInitScript(() => { localStorage.setItem('token', 'stub') })
  const page = await ctx.newPage()
  const calls = []
  page.on('pageerror', () => {})
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    calls.push({ path: p, publishing: req.headers()['x-publishing'] || null })
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (p.startsWith('/auth/me')) {
      return json({ id: 'u1', username: 'admin', role: 'club_admin', club_id: 'org-1', club_slug: 'applecross',
        capabilities: ['*'], entitlements: { modules: ['stats', 'socials', 'select'], status: 'active' } })
    }
    if (p === '/club-admin/players') return json([{ id: 'p1', name: 'Plain, Pat', display_name: 'Pat Plain', status: 'active' }])
    if (p === '/club-admin/settings') return json({ id: 'org-1', name: 'Applecross', slug: 'applecross' })
    return json([])
  })
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  await ctx.close()
  return calls
}

console.log('BetterSocials post builder')
const builder = await visit('/admin/social-post?type=scorecard')
// The app shell makes its own calls (sign-in, plan, trial status) before the
// builder screen has loaded. None carries player data, so they are out of scope.
const SHELL = (c) => c.path.startsWith('/auth/') || c.path.startsWith('/usage') || c.path.includes('heartbeat')
  || c.path.startsWith('/public/self-serve') || c.path.startsWith('/club-admin/account')
const data = builder.filter(c => !SHELL(c))
ck('the builder made data requests', data.length > 0, JSON.stringify(builder.map(c => c.path)))
ck('EVERY player-data request the builder made carries X-Publishing: 1',
  data.length > 0 && data.every(c => c.publishing === '1'),
  JSON.stringify(data.filter(c => c.publishing !== '1').map(c => c.path)))
ck('including the roster read', data.some(c => c.path === '/club-admin/players' && c.publishing === '1'))

console.log('A screen that does not publish (control)')
const players = await visit('/admin/players')
const pd = players.filter(c => !c.path.startsWith('/auth/') && !c.path.startsWith('/usage') && !c.path.includes('heartbeat'))
ck('the admin Players screen made data requests', pd.length > 0)
ck('NONE of them carries X-Publishing (the flag is released when the builder closes)',
  pd.every(c => c.publishing === null), JSON.stringify(pd.filter(c => c.publishing).map(c => c.path)))

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
