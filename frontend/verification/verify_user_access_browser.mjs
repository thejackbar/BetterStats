// Module-locked club users (migration 344): drives the real Users screen and the
// sidebar in Chromium with the API stubbed at the network layer.
//
//   npx vite build && npx vite preview --port 5199 &
//   node verification/verify_user_access_browser.mjs [baseUrl]
//
// Asked for: everyone starts with access to everything; only the Primary Admin
// (or a Super Admin) can limit someone to one module; a limited person does not
// see Plan & Billing, Setup Wizard or any module that is not theirs. So the checks
// cover what is drawn for a Primary Admin, an ordinary admin and a limited person,
// the exact request each save sends (and that a name edit sends no `access` key),
// the Primary Admin's own row, and the layout at phone width.
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const SHOTS = process.env.SHOTS || '/tmp/claude-0'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const MODULES = [
  { key: 'stats', name: 'BetterStats', blurb: 'Matches, players, imports, awards.' },
  { key: 'select', name: 'BetterSelect', blurb: 'Squads, fixtures, availability, selection, nets, votes.' },
  { key: 'admin', name: 'BetterAdmin', blurb: 'Directory, roster, committee, fees.' },
]
const CATALOGUE = [
  { key: 'stats', name: 'BetterStats', blurb: 'Matches, players.', items: [
    { id: 'stats.players', name: 'Players', menu: 'Players, Import Players', needs: [] },
  ] },
  { key: 'select', name: 'BetterSelect', blurb: 'Squads, availability, selection.', items: [
    { id: 'select.availability', name: 'Availability', menu: 'Availability', needs: [] },
    { id: 'select.selection', name: 'Selection', menu: 'Selection, Selection Whiteboard', needs: [{ item: 'select.availability', level: 'view', name: 'Availability' }] },
    { id: 'select.fines', name: 'Fines', menu: 'Fines', needs: [] },
    { id: 'select.votes', name: 'Votes', menu: 'Votes', needs: [] },
  ] },
  { key: 'admin', name: 'BetterAdmin', blurb: 'Directory, fees.', items: [
    { id: 'admin.fees', name: 'Fees', menu: 'Accounts, Payments, Membership tiers', needs: [] },
  ] },
]
const ALL_CAPS = ['manage_settings', 'manage_users', 'manage_fees', 'manage_selections', 'manage_fixtures', 'manage_players']
const SELECT_CAPS = ['manage_players', 'manage_fixtures', 'manage_selections']

function usersList() {
  return [
    { id: 'u-primary', username: 'pat', display_name: 'Pat Primary', email: 'pat@x.test', mobile_number: null, last_login_at: null,
      role: 'club_admin', capabilities: [], is_primary_admin: true, access: { mode: 'full', module_key: null, module_name: null } },
    { id: 'u-full', username: 'fran', display_name: 'Fran Full', email: 'fran@x.test', mobile_number: null, last_login_at: null,
      role: 'club_admin', capabilities: [], is_primary_admin: false, access: { mode: 'full', module_key: null, module_name: null } },
    { id: 'u-items', username: 'ivy', display_name: 'Ivy Items', email: 'ivy@x.test', mobile_number: null, last_login_at: null,
      role: 'club_member', capabilities: ['select_fines', 'manage_fees'], is_primary_admin: false,
      access: { mode: 'items', module_key: null, module_name: null, grants: { 'select.fines': 'manage', 'admin.fees': 'view' }, modules: ['select', 'admin'], item_count: 2 } },
    { id: 'u-locked', username: 'leo', display_name: 'Leo Locked', email: 'leo@x.test', mobile_number: null, last_login_at: null,
      role: 'club_member', capabilities: SELECT_CAPS, is_primary_admin: false, access: { mode: 'module', module_key: 'select', module_name: 'BetterSelect' } },
  ]
}

// The /auth/me payload for each kind of signed-in person.
function meFor(kind) {
  const base = {
    id: kind === 'locked' ? 'u-locked' : kind === 'full' ? 'u-full' : 'u-primary',
    username: kind, display_name: kind, club_id: 'c1', club_slug: 'alpha', club_name: 'Alpha CC',
    can_switch_clubs: false, home_club_id: 'c1', home_club_name: 'Alpha CC', acting_as_club: false,
    linked_clubs: [], can_switch_linked_clubs: false, acting_as_linked_club: false,
    entitlements: { modules: ['select', 'fees'], status: 'active', billing_modules: [] },
  }
  const itemsMe = {
    items: { caps: ['select_availability', 'select_fines', 'manage_fees', 'view_vote_results'], view: ['select_availability', 'manage_fees'],
      grants: { 'select.availability': 'view', 'select.fines': 'manage', 'admin.fees': 'view', 'select.votes': 'view' }, modules: ['select', 'admin'] },
    'rules-manage': { caps: ['select_rules'], view: [], grants: { 'select.rules': 'manage' }, modules: ['select'] },
    'rules-view': { caps: ['select_rules'], view: ['select_rules'], grants: { 'select.rules': 'view' }, modules: ['select'] },
  }[kind]
  if (itemsMe) {
    return { ...base, role: 'club_member', is_primary_admin: false, capabilities: itemsMe.caps, view_only_capabilities: itemsMe.view,
      access: { mode: 'items', module_key: null, module_name: null, grants: itemsMe.grants, modules: itemsMe.modules, item_count: Object.keys(itemsMe.grants).length } }
  }
  if (kind === 'locked') {
    return { ...base, role: 'club_member', is_primary_admin: false, capabilities: SELECT_CAPS,
      access: { mode: 'module', module_key: 'select', module_name: 'BetterSelect' } }
  }
  return { ...base, role: 'club_admin', is_primary_admin: kind === 'primary', capabilities: ALL_CAPS,
    access: { mode: 'full', module_key: null, module_name: null } }
}

async function stub(page, state) {
  await page.route(/\/api\//, async (route) => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace(/^\/api/, '')
    const method = req.method()
    const body = req.postData() ? JSON.parse(req.postData()) : null
    state.calls.push({ method, p, body })
    const json = (b, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (p === '/auth/me') return json(meFor(state.kind))
    if (p === '/club-admin/users' && method === 'GET') return json(usersList())
    if (p === '/club-admin/users/capabilities') return json({ capabilities: ALL_CAPS, modules: MODULES, catalogue: CATALOGUE })
    if (p === '/availability/config') return json({ allow_maybe: true, played_years: { selection: 3, availability: 0 }, team_defaults: [], squads: [] })
    if (p === '/selection-rules') return json({ settings: {}, options: { teams: [] }, rules: [] })
    if (p === '/club-admin/users' && method === 'POST') return json({ id: 'u-new', invited: true, access: { mode: 'full' } })
    if (/^\/club-admin\/users\/[^/]+$/.test(p) && method === 'PATCH') {
      const g = body?.access?.grants || {}
      const added = body?.access?.mode === 'items' && g['select.selection']
        ? [{ item: 'select.availability', name: 'Availability', level: 'view', because: 'Selection' }] : []
      return json({ status: 'ok', added })
    }
    if (p === '/club-admin/settings') return json({ name: 'Alpha CC', slug: 'alpha' })
    if (p === '/club-admin/broadcasts') return json({ items: [], preview: false })
    if (p === '/club-admin/seasons') return json([])
    if (p === '/club-admin/account/plan') return json({ modules: [] })
    return json({ detail: 'not stubbed' }, 404)
  })
}

// A section that cannot finish (an element the control build does not have) is reported as a
// failure, not thrown: a control run that crashes is not a control run.
async function section(name, fn) {
  try { await fn() } catch (e) { fail++; console.log(`FAIL ${name} did not complete  ${String(e.message).split('\n')[0].slice(0, 120)}`) }
}

const browser = await chromium.launch({ executablePath: EXECUTABLE })

async function open(kind, path, viewport = { width: 1280, height: 900 }) {
  const ctx = await browser.newContext({ viewport })
  const page = await ctx.newPage()
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) console.log(`CONSOLE ${kind} ${path}: ${m.text().slice(0, 200)}`) })
  page.on('pageerror', e => console.log(`PAGEERROR ${kind} ${path}: ${String(e.message).slice(0, 160)}`))
  const state = { kind, calls: [] }
  await stub(page, state)
  await page.goto(`${BASE}${path}`)
  return { ctx, page, state }
}
const patches = (state) => state.calls.filter(c => c.method === 'PATCH' && /\/club-admin\/users\//.test(c.p))
const posts = (state) => state.calls.filter(c => c.method === 'POST' && c.p === '/club-admin/users')

// ── Primary Admin: the list ─────────────────────────────────────────────
await section('Primary Admin screen', async () => {
  const { ctx, page, state } = await open('primary', '/admin/users')
  await page.getByText('Leo Locked').first().waitFor({ timeout: 15000 })
  const text = await page.locator('main, body').first().innerText()
  ck('the list shows everyone', ['Pat Primary', 'Fran Full', 'Leo Locked'].every(n => text.includes(n)))
  ck('the Primary Admin is labelled', text.includes('Primary Admin'))
  ck('a limited person is labelled Limited access', text.includes('Limited access'))
  ck('and carries a BetterSelect only badge', (await page.getByTestId('access-badge').allInnerTexts()).join('|').includes('BetterSelect only'))
  ck('only the two limited people have an access badge', (await page.getByTestId('access-badge').count()) === 2)
  ck('the intro says new users start with everything', /start with access to everything/i.test(text))

  // ── open an ordinary admin: picker present, Everything pressed ──
  await page.getByText('Fran Full').first().click()
  await page.getByTestId('access-picker').waitFor()
  ck('the picker is shown to the Primary Admin', true)
  ck('Everything is pressed for a full admin', (await page.getByTestId('access-full').getAttribute('aria-pressed')) === 'true')
  ck('the module list is hidden until One module is chosen', (await page.getByTestId('access-module-select').count()) === 0)

  // a name edit alone sends no access key (an absent key is not a clear)
  await page.locator('input').first().fill('Fran Renamed')
  await page.getByRole('button', { name: /^Save$/ }).click()
  await page.waitForTimeout(300)
  const p1 = patches(state)
  ck('saving only a name sends one PATCH', p1.length === 1, JSON.stringify(p1.map(c => c.p)))
  ck('and that PATCH has no access key', p1.length === 1 && !('access' in p1[0].body), JSON.stringify(p1[0]?.body))

  // lock to BetterAdmin
  await page.getByText('Fran Full').first().click()
  await page.getByTestId('access-picker').waitFor()
  await page.getByTestId('access-module').click()
  await page.getByTestId('access-module-select').waitFor()
  const opts = await page.getByTestId('access-module-select').locator('option').allInnerTexts()
  ck('the module list names every module', opts.join('|') === 'BetterStats|BetterSelect|BetterAdmin', opts.join('|'))
  ck('the module blurb is shown', (await page.getByTestId('access-picker').innerText()).includes('Matches, players'))
  ck('and says what they will not see', (await page.getByTestId('access-picker').innerText()).includes('will not see Settings, Users, Plan & Billing'))
  await page.getByTestId('access-module-select').selectOption('admin')
  await page.getByRole('button', { name: /^Save$/ }).click()
  await page.waitForTimeout(300)
  const p2 = patches(state)
  const last = p2[p2.length - 1]
  ck('saving a lock sends the exact access body', last && JSON.stringify(last.body.access) === JSON.stringify({ mode: 'module', module_key: 'admin' }), JSON.stringify(last?.body))
  ck('to the right user', last && last.p === '/club-admin/users/u-full', last?.p)
  await page.screenshot({ path: `${SHOTS}/user-access-picker.png` })

  // the limited person: module pre-selected, Everything clears it
  await page.getByText('Leo Locked').first().click()
  await page.getByTestId('access-picker').waitFor()
  ck('a limited person opens with One module pressed', (await page.getByTestId('access-module').getAttribute('aria-pressed')) === 'true')
  ck('on their own module', (await page.getByTestId('access-module-select').inputValue()) === 'select')
  await page.getByTestId('access-full').click()
  await page.getByRole('button', { name: /^Save$/ }).click()
  await page.waitForTimeout(300)
  const p3 = patches(state)
  const last3 = p3[p3.length - 1]
  ck('choosing Everything sends full to clear the lock', last3 && JSON.stringify(last3.body.access) === JSON.stringify({ mode: 'full' }) && last3.p === '/club-admin/users/u-locked', JSON.stringify(last3))

  // the Primary Admin's own row: nothing to edit
  await page.getByText('Pat Primary').first().click()
  await page.getByTestId('access-readonly').waitFor()
  ck('the Primary Admin has no picker', (await page.getByTestId('access-picker').count()) === 0)
  ck('and reads Everything (always)', (await page.getByTestId('access-readonly').innerText()).includes('Everything (always)'))

  // invite: no access key by default, a lock when chosen
  await page.getByRole('button', { name: /Add user/ }).click()
  await page.getByTestId('access-picker').waitFor()
  await page.locator('input').nth(0).fill('newperson')
  await page.locator('input[type=email]').fill('new@x.test')
  await page.getByRole('button', { name: /Send invite/ }).click()
  await page.waitForTimeout(300)
  const c1 = posts(state)
  ck('an invite with the default sends no access key', c1.length === 1 && !('access' in c1[0].body), JSON.stringify(c1[0]?.body))
  await page.getByRole('button', { name: /Add user/ }).click()
  await page.getByTestId('access-picker').waitFor()
  await page.locator('input').nth(0).fill('limited')
  await page.locator('input[type=email]').fill('limited@x.test')
  await page.getByTestId('access-module').click()
  await page.getByTestId('access-module-select').selectOption('select')
  await page.getByRole('button', { name: /Send invite/ }).click()
  await page.waitForTimeout(300)
  const c2 = posts(state)
  ck('an invite with a lock sends the module', c2.length === 2 && JSON.stringify(c2[1].body.access) === JSON.stringify({ mode: 'module', module_key: 'select' }), JSON.stringify(c2[1]?.body))
  await ctx.close()
})

// ── an ordinary admin: sees the state, cannot change it ──────────────────
await section('ordinary admin screen', async () => {
  const { ctx, page, state } = await open('full', '/admin/users')
  await page.getByText('Leo Locked').first().waitFor({ timeout: 15000 })
  await page.getByText('Leo Locked').first().click()
  await page.getByTestId('access-readonly').waitFor()
  ck('an ordinary admin gets no picker', (await page.getByTestId('access-picker').count()) === 0)
  const t = await page.getByTestId('access-readonly').innerText()
  ck('they can still read what the person can open', t.includes('BetterSelect only'), t)
  ck('and are told who can change it', t.includes('Only the Primary Admin can change this'), t)
  await page.getByRole('button', { name: /Add user/ }).click()
  await page.getByTestId('access-note').waitFor()
  ck('the invite form explains instead of offering a picker', (await page.getByTestId('access-picker').count()) === 0)
  await ctx.close()
})

// ── the sidebar and dashboard: a limited person loses what is not theirs ──
async function dashboard(kind) {
  const { ctx, page, state } = await open(kind, '/admin')
  await page.waitForTimeout(1800)
  const nav = await page.locator('nav a[href^="/admin"]').evaluateAll(as => as.map(a => a.getAttribute('href')))
  const main = await page.locator('main a[href^="/admin"]').evaluateAll(as => as.map(a => a.getAttribute('href')))
  const text = await page.locator('body').innerText()
  const paths = state.calls.map(c => c.p)
  await ctx.close()
  return { nav, main, text, paths }
}
await section('dashboard and sidebar', async () => {
  const full = await dashboard('primary')
  ck('a full admin sees Plan & Billing', full.nav.includes('/admin/account'), full.nav.join(','))
  ck('and the Setup Wizard', full.nav.includes('/admin/setup'))
  ck('and the BetterStats and BetterSelect tiles', full.main.includes('/admin/betterstats') && full.main.includes('/admin/betterselect'))
  ck('and Club Settings and Data Sync quick links', full.main.includes('/admin/settings') && full.main.includes('/admin/sync'))
  ck('and the plan line', /Plan:/.test(full.text))
  ck('and the page loads the plan', full.paths.includes('/club-admin/account/plan'))

  const locked = await dashboard('locked')
  ck('a limited person does not see Plan & Billing', !locked.nav.includes('/admin/account'), locked.nav.join(','))
  ck('nor the Setup Wizard', !locked.nav.includes('/admin/setup'))
  ck('nor Users or Settings in the sidebar', !locked.nav.includes('/admin/users') && !locked.nav.includes('/admin/settings'))
  ck('they see their own module tile', locked.main.includes('/admin/betterselect'), locked.main.join(','))
  ck('and no other module tile', !locked.main.includes('/admin/betterstats') && !locked.main.includes('/admin/bettersocials'), locked.main.join(','))
  ck('no Club Settings, Data Sync or Merge quick links', !['/admin/settings', '/admin/sync', '/admin/merge', '/admin/yearbook', '/admin/awards'].some(h => locked.main.includes(h)), locked.main.join(','))
  ck('they keep the quick links their permissions allow', locked.main.includes('/admin/players') && locked.main.includes('/admin/games'), locked.main.join(','))
  ck('there is no plan line for them', !/Plan:/.test(locked.text))
  ck('the page does not fetch the plan, the setup flow or sync logs for them',
    !locked.paths.includes('/club-admin/account/plan') && !locked.paths.some(p => /sync/i.test(p) || /onboarding-wizard/.test(p)),
    locked.paths.filter(p => /plan|sync|wizard/i.test(p)).join(','))
})

// ── choose items ────────────────────────────────────────────────────────
await section('choose items editor', async () => {
  const { ctx, page, state } = await open('primary', '/admin/users')
  await page.getByText('Fran Full').first().waitFor({ timeout: 15000 })
  ck('the list shows an items person with a count', (await page.getByTestId('access-badge').allInnerTexts()).join('|').includes('2 menu items'))
  await page.getByText('Fran Full').first().click()
  await page.getByTestId('access-picker').waitFor()
  ck('Choose items is offered', (await page.getByTestId('access-items').count()) === 1)
  await page.getByTestId('access-items').click()
  await page.getByTestId('item-switches').waitFor()
  const mods = await page.locator('[data-testid^="module-"][data-testid$="stats"], [data-testid="module-select"], [data-testid="module-admin"]').count()
  ck('every module is listed with its items', (await page.getByTestId('item-select.fines').count()) === 1 && (await page.getByTestId('item-admin.fees').count()) === 1 && (await page.getByTestId('item-stats.players').count()) === 1 && mods >= 3)
  ck('each item names the menu screens it opens', (await page.getByTestId('item-select.selection').innerText()).includes('Selection Whiteboard'))
  ck('Save is blocked until something is chosen', await page.getByRole('button', { name: /^Save$/ }).isDisabled())
  ck('and says nothing is chosen', (await page.getByTestId('item-count').innerText()).includes('Nothing chosen yet'))

  await page.getByTestId('item-select.selection-manage').click()
  ck('Selection at Manage', (await page.getByTestId('item-select.selection-manage').getAttribute('aria-pressed')) === 'true')
  ck('switches Availability on at View', (await page.getByTestId('item-select.availability-view').getAttribute('aria-pressed')) === 'true')
  ck('and tells the Primary Admin why', (await page.getByTestId('item-notice').innerText()).includes('Selection needs Availability'), await page.getByTestId('item-notice').innerText().catch(() => 'no notice'))
  await page.getByTestId('item-select.availability-off').click()
  ck('an item that something chosen needs cannot be switched off', (await page.getByTestId('item-select.availability-view').getAttribute('aria-pressed')) === 'true')
  await page.getByTestId('item-select.fines-manage').click()
  await page.getByTestId('item-admin.fees-view').click()
  ck('the count follows', (await page.getByTestId('item-count').innerText()).includes('4 menu items chosen'), await page.getByTestId('item-count').innerText())
  ck('and says what View means', (await page.getByTestId('item-count').innerText()).includes('View lets them look but not change anything'))
  ck('Save is available once items are chosen', !(await page.getByRole('button', { name: /^Save$/ }).isDisabled()))
  await page.screenshot({ path: `${SHOTS}/user-access-items.png`, fullPage: true })
  await page.getByRole('button', { name: /^Save$/ }).click()
  await page.waitForTimeout(400)
  const ps = patches(state)
  const last = ps[ps.length - 1]
  const want = { 'select.selection': 'manage', 'select.availability': 'view', 'select.fines': 'manage', 'admin.fees': 'view' }
  const got = last?.body?.access
  ck('Save sends the exact items and levels', got?.mode === 'items' && JSON.stringify(Object.fromEntries(Object.entries(got.grants || {}).sort())) === JSON.stringify(Object.fromEntries(Object.entries(want).sort())), JSON.stringify(last?.body))
  ck('to the right user', last?.p === '/club-admin/users/u-full', last?.p)
  ck('the confirmation names what was added', (await page.locator('body').innerText()).includes('Selection needs Availability, so it is on at View'))

  // a module's own buttons set every item in it
  await page.getByText('Fran Full').first().click()
  await page.getByTestId('access-picker').waitFor()
  await page.getByTestId('access-items').click()
  await page.getByTestId('module-select-view').click()
  const pressed = async (id) => (await page.getByTestId(`item-${id}-view`).getAttribute('aria-pressed')) === 'true'
  ck('All view on a module sets each of its items to View', await pressed('select.fines') && await pressed('select.votes') && await pressed('select.availability'))
  await page.getByTestId('module-select-off').click()
  ck('All off on a module switches its items off', (await page.getByTestId('item-select.fines-off').getAttribute('aria-pressed')) === 'true')
  await ctx.close()
})

await section('editing an items person and moving between modes', async () => {
  const { ctx, page, state } = await open('primary', '/admin/users')
  await page.getByText('Ivy Items').first().waitFor({ timeout: 15000 })
  await page.getByText('Ivy Items').first().click()
  await page.getByTestId('item-switches').waitFor()
  ck('an items person opens on Choose items', (await page.getByTestId('access-items').getAttribute('aria-pressed')) === 'true')
  ck('with their levels shown', (await page.getByTestId('item-select.fines-manage').getAttribute('aria-pressed')) === 'true' && (await page.getByTestId('item-admin.fees-view').getAttribute('aria-pressed')) === 'true')
  ck('and the other items off', (await page.getByTestId('item-select.votes-off').getAttribute('aria-pressed')) === 'true')
  await page.getByTestId('access-full').click()
  await page.getByRole('button', { name: /^Save$/ }).click()
  await page.waitForTimeout(300)
  const p1 = patches(state)
  ck('choosing Everything clears the items', JSON.stringify(p1[p1.length - 1]?.body?.access) === JSON.stringify({ mode: 'full' }) && p1[p1.length - 1]?.p === '/club-admin/users/u-items', JSON.stringify(p1[p1.length - 1]))

  await page.getByText('Leo Locked').first().click()
  await page.getByTestId('access-picker').waitFor()
  await page.getByTestId('access-items').click()
  await page.getByTestId('item-switches').waitFor()
  ck('moving a whole-module person to chosen items starts with that module on Manage',
    (await page.getByTestId('item-select.fines-manage').getAttribute('aria-pressed')) === 'true' &&
    (await page.getByTestId('item-select.votes-manage').getAttribute('aria-pressed')) === 'true' &&
    (await page.getByTestId('item-admin.fees-off').getAttribute('aria-pressed')) === 'true')
  await ctx.close()
})

await section('an items person: sidebar, dashboard and read-only screens', async () => {
  const d = await dashboard('items')
  ck('they see a tile for each module they can open something in', d.main.includes('/admin/betterselect') && d.main.includes('/admin/clubhouse'), d.main.join(','))
  ck('and none for a module they cannot', !d.main.includes('/admin/betterstats') && !d.main.includes('/admin/bettersocials'), d.main.join(','))
  ck('no Plan & Billing, Setup Wizard, Users or Settings', !['/admin/account', '/admin/setup', '/admin/users', '/admin/settings'].some(h => d.nav.includes(h)), d.nav.join(','))
  ck('no plan line and no plan, setup or sync fetches', !/Plan:/.test(d.text) && !d.paths.some(p => /account\/plan|onboarding-wizard|sync/i.test(p)), d.paths.filter(p => /plan|sync|wizard/i.test(p)).join(','))

  const { ctx, page } = await open('items', '/admin/betterselect')
  await page.waitForTimeout(1800)
  const links = await page.locator('nav a[href^="/admin/betterselect"]').evaluateAll(as => as.map(a => a.getAttribute('href')))
  await ctx.close()
  ck('the BetterSelect menu shows the items they hold', links.includes('/admin/betterselect/availability') && links.includes('/admin/betterselect/fines') && links.includes('/admin/betterselect/votes'), links.join(','))
  ck('and none they do not', !['/admin/betterselect/teams', '/admin/betterselect/nets', '/admin/betterselect/selection', '/admin/betterselect/rules', '/admin/betterselect/audit', '/admin/betterselect/settings'].some(h => links.includes(h)), links.join(','))

  for (const [kind, expectDisabled] of [['rules-manage', false], ['rules-view', true]]) {
    const { ctx: c2, page: p2 } = await open(kind, '/admin/betterselect/settings')
    await p2.locator('select[data-window="selection"]').waitFor({ timeout: 15000 })
    const disabled = await p2.locator('select[data-window="selection"]').isDisabled()
    ck(`Settings at ${kind === 'rules-view' ? 'View' : 'Manage'} draws ${expectDisabled ? 'read only' : 'editable'}`, disabled === expectDisabled, `disabled=${disabled}`)
    await c2.close()
  }
})

// ── phone width ────────────────────────────────────────────────────────
await section('phone width', async () => {
  const { ctx, page } = await open('primary', '/admin/users', { width: 390, height: 844 })
  await page.getByText('Fran Full').first().waitFor({ timeout: 15000 })
  await page.getByText('Fran Full').first().click()
  await page.getByTestId('access-picker').waitFor()
  await page.getByTestId('access-module').click()
  await page.getByTestId('access-module-select').waitFor()
  const w = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }))
  ck('no horizontal overflow at 390px with the picker open', w.sw <= w.iw + 1, JSON.stringify(w))
  await page.screenshot({ path: `${SHOTS}/user-access-390.png`, fullPage: true })
  await ctx.close()
})

await section('phone width, choose items', async () => {
  const { ctx, page } = await open('primary', '/admin/users', { width: 390, height: 844 })
  await page.getByText('Fran Full').first().waitFor({ timeout: 15000 })
  await page.getByText('Fran Full').first().click()
  await page.getByTestId('access-picker').waitFor()
  await page.getByTestId('access-items').click()
  await page.getByTestId('item-switches').waitFor()
  await page.getByTestId('item-select.selection-manage').click()
  const w = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }))
  ck('no horizontal overflow at 390px with the item switches open', w.sw <= w.iw + 1, JSON.stringify(w))
  const row = await page.getByTestId('item-select.selection').boundingBox()
  ck('an item row fits inside the screen width', row && row.x >= 0 && row.x + row.width <= w.iw + 1, JSON.stringify(row))
  await page.screenshot({ path: `${SHOTS}/user-access-items-390.png`, fullPage: true })
  await ctx.close()
})

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
