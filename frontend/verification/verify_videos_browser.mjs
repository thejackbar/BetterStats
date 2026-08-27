// Drives the real /videos section in Chromium with the API stubbed at the
// network layer.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_videos_browser.mjs [baseUrl]
//
// Checks the things a build cannot: that a visitor never sees a management
// control, that a super admin does, that each write puts the right thing on
// the wire, that a dismissed delete sends nothing, and that a new top-level
// route is not mistaken for a club slug.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const VIDEOS = [
  {
    id: '11111111-1111-1111-1111-111111111111', slug: 'merge-players',
    title: 'BetterCricket - Merge Players', description: 'One person, two records.',
    module_label: 'BetterStats', sort_order: 0, date: '2026-08-27',
    src: '/api/public/videos/merge-players/file', poster: '/api/public/videos/merge-players/poster',
    video_size: 1024, updated_at: '2026-08-27T00:00:00',
  },
  {
    id: '22222222-2222-2222-2222-222222222222', slug: 'merge-grades',
    title: 'BetterCricket - Merge Grades', description: 'Two names, one grade.',
    module_label: 'BetterStats', sort_order: 1, date: '2026-08-27',
    src: '/api/public/videos/merge-grades/file', poster: null,
    video_size: 900, updated_at: '2026-08-27T00:00:00',
  },
  {
    id: '33333333-3333-3333-3333-333333333333', slug: 'selection',
    title: 'BetterCricket - Selection', description: 'Picking a side for the weekend.',
    module_label: 'BetterSelect', sort_order: 2, date: '2026-08-27',
    src: '/api/public/videos/selection/file', poster: null,
    video_size: 700, updated_at: '2026-08-27T00:00:00',
  },
]

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

/**
 * One page with the API stubbed. `role` decides what /auth/me answers, which
 * is the only thing separating a visitor from a super admin here.
 * Returns the page plus the recorded write calls.
 */
async function openPage(role) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  const writes = []
  const clubCalls = []

  page.on('pageerror', (e) => errors.push(String(e)))

  // Everything the app asks the backend for, answered locally.
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = req.method()

    if (/^\/clubs\/videos/.test(path)) clubCalls.push(path)
    if (method !== 'GET') {
      let body = null
      try { body = req.postData() } catch { /* multipart, read below */ }
      writes.push({ method, path, body, postDataBuffer: req.postDataBuffer()?.toString('utf8') ?? null })
    }

    if (path === '/auth/me') {
      if (!role) return route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"no"}' })
      return route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ id: 'u1', username: 'tester', role, entitlements: { modules: [] } }),
      })
    }
    if (path === '/public/videos' && method === 'GET') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ videos: VIDEOS }) })
    }
    if (path === '/club-admin/super/videos/reorder') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ videos: VIDEOS }) })
    }
    if (/^\/club-admin\/super\/videos\//.test(path) && method === 'DELETE') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"deleted":true}' })
    }
    if (/^\/club-admin\/super\/videos/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(VIDEOS[0]) })
    }
    // The video/poster bytes themselves, and everything else.
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  return { page, ctx, errors, writes, clubCalls }
}

// ------------------------------------------------------------- the visitor
{
  const { page, ctx, errors, clubCalls } = await openPage(null)
  await page.goto(`${BASE}/videos`, { waitUntil: 'networkidle' })

  ck('visitor: heading renders', (await page.locator('h1').first().innerText()).trim() === 'Videos.')
  ck('visitor: intro text explains the section',
     (await page.locator('#main-content').innerText()).includes('Short walkthroughs of the jobs a club admin does'))

  const links = await page.locator('#main-content a[href^="/videos/"]').evaluateAll(
    (els) => [...new Set(els.map((e) => e.getAttribute('href')))])
  ck('visitor: one card per video from the API', links.length === VIDEOS.length, links.join(', '))

  const thumb = await page.locator('a[href="/videos/merge-players"] div').first().boundingBox()
  ck('visitor: thumbnail is a real 16:9 tile',
     !!thumb && Math.abs(thumb.width / thumb.height - 16 / 9) < 0.05 && thumb.width > 200,
     `${thumb?.width}x${thumb?.height}`)

  const dl = page.locator('a[download][href*="merge-players/file"]').first()
  ck('visitor: download link points at the streaming endpoint', await dl.count() > 0)
  ck('visitor: download link asks for the attachment form',
     (await dl.getAttribute('href') || '').includes('download=1'))
  ck('visitor: download link is not nested inside the card link', await page.evaluate(() => {
    const a = document.querySelector('a[download]')
    return !!a && !a.closest('a[href^="/videos/"]')
  }))

  // The whole point of the gate: none of the management surface may render.
  // Compared against the RENDERED text, which the uppercase class has already
  // transformed — matching the source casing here is a check that cannot fail.
  const text = (await page.locator('#main-content').innerText()).toUpperCase()
  ck('visitor: NO add control', !text.includes('ADD VIDEO'))
  ck('visitor: NO edit control',
     await page.getByRole('button', { name: 'EDIT', exact: true }).count() === 0)
  ck('visitor: NO delete control',
     await page.getByRole('button', { name: 'DELETE', exact: true }).count() === 0)
  ck('visitor: NO reorder control', !text.includes('REORDER'))
  ck('visitor: NO super admin bar', !text.includes('SUPER ADMIN'))
  ck('visitor: cards are not draggable', await page.evaluate(
    () => ![...document.querySelectorAll('[data-video-slug]')].some((e) => e.draggable)))

  ck('visitor: "videos" is never looked up as a club slug', clubCalls.length === 0, clubCalls.join(', '))
  ck('visitor: exactly one nav on the page', await page.locator('nav').count() === 1)
  ck('visitor: the marketing site stays dark',
     await page.evaluate(() => document.documentElement.dataset.theme) === 'dark')
  ck('visitor: no page errors', errors.length === 0, errors.join(' | '))

  // The detail page.
  await page.goto(`${BASE}/videos/merge-players`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(400)
  ck('visitor: detail title renders',
     (await page.locator('h1').first().innerText()).trim() === 'BetterCricket - Merge Players')
  ck('visitor: detail description renders',
     (await page.locator('#main-content').innerText()).includes('One person, two records.'))
  ck('visitor: detail has a player or a plain note',
     await page.locator('video').count() > 0
     || (await page.locator('#main-content').innerText()).includes('could not be played'))
  ck('visitor: detail download button present',
     await page.locator('a[download][href*="download=1"]').count() > 0)
  ck('visitor: detail shows NO edit control',
     !(await page.locator('#main-content').innerText()).includes('EDIT THIS VIDEO'))
  const rail = await page.locator('#main-content a[href^="/videos/"]').evaluateAll(
    (els) => [...new Set(els.map((e) => e.getAttribute('href')))])
  ck('visitor: rail offers the others and not this one',
     !rail.includes('/videos/merge-players') && rail.length === VIDEOS.length - 1, rail.join(', '))
  ck('visitor: no page errors on the detail page', errors.length === 0, errors.join(' | '))

  await page.goto(`${BASE}/videos/not-a-real-video`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(500)
  ck('visitor: unknown slug redirects to the index', new URL(page.url()).pathname === '/videos')
  await ctx.close()
}

// ------------------------------- a signed-in NON super admin sees nothing
{
  const { page, ctx } = await openPage('club_admin')
  await page.goto(`${BASE}/videos`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(300)
  const text = (await page.locator('#main-content').innerText()).toUpperCase()
  ck('club admin: NO add control', !text.includes('ADD VIDEO'))
  ck('club admin: NO super admin bar', !text.includes('SUPER ADMIN'))
  ck('club admin: NO reorder control', !text.includes('REORDER'))
  ck('club admin: NO edit or delete on any card',
     await page.getByRole('button', { name: 'EDIT', exact: true }).count() === 0
     && await page.getByRole('button', { name: 'DELETE', exact: true }).count() === 0)
  await ctx.close()
}

// -------------------------------------------------------- the super admin
{
  const { page, ctx, errors, writes } = await openPage('super_admin')
  await page.goto(`${BASE}/videos`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(400)

  const text = (await page.locator('#main-content').innerText()).toUpperCase()
  ck('super admin: the management bar renders', text.includes('SUPER ADMIN'))
  ck('super admin: add control renders', text.includes('ADD VIDEO'))
  ck('super admin: reorder control renders', text.includes('REORDER'))
  ck('super admin: each card offers edit and delete',
     await page.getByRole('button', { name: 'EDIT', exact: true }).count() === VIDEOS.length
     && await page.getByRole('button', { name: 'DELETE', exact: true }).count() === VIDEOS.length)

  // --- the editor form
  await page.getByRole('button', { name: '+ ADD VIDEO' }).click()
  await page.waitForTimeout(250)
  ck('super admin: the add form opens', await page.locator('[role="dialog"]').isVisible())
  const formRaw = await page.locator('[role="dialog"]').innerText()
  const form = formRaw.toUpperCase()
  ck('super admin: the form asks for a title', form.includes('TITLE'))
  ck('super admin: the form asks for a description', form.includes('DESCRIPTION'))
  ck('super admin: the form takes a video file', form.includes('VIDEO FILE'))
  ck('super admin: the form offers an optional thumbnail', form.includes('THUMBNAIL'))
  ck('super admin: the form says a frame is taken automatically',
     formRaw.includes('a frame is taken from the video itself'))
  ck('super admin: the form accepts only playable formats',
     (await page.locator('input[type=file]').first().getAttribute('accept')) === 'video/mp4,video/webm')

  // Saving with no file must be refused client-side, before any request.
  writes.length = 0
  await page.locator('[role="dialog"] input[type=text]').first().fill('A new walkthrough')
  await page.getByRole('button', { name: 'UPLOAD VIDEO' }).click()
  await page.waitForTimeout(400)
  ck('super admin: uploading with no file is refused and sends nothing',
     writes.length === 0 && (await page.locator('[role="dialog"]').innerText()).includes('Choose a video file'),
     `${writes.length} writes`)

  await page.getByRole('button', { name: 'CANCEL' }).click()
  await page.waitForTimeout(200)
  ck('super admin: cancel closes the form', await page.locator('[role="dialog"]').count() === 0)

  // --- editing text only
  writes.length = 0
  await page.getByRole('button', { name: 'EDIT', exact: true }).first().click()
  await page.waitForTimeout(250)
  const editForm = page.locator('[role="dialog"]')
  ck('super admin: the edit form is seeded with the current title',
     (await editForm.locator('input[type=text]').first().inputValue()) === 'BetterCricket - Merge Players')
  ck('super admin: the edit form is seeded with the current description',
     (await editForm.locator('textarea').first().inputValue()) === 'One person, two records.')
  ck('super admin: editing says the file is kept unless replaced',
     (await editForm.innerText()).includes('Leave empty to keep the current file'))

  await editForm.locator('input[type=text]').first().fill('Merging duplicate players')
  await page.getByRole('button', { name: 'SAVE CHANGES' }).click()
  await page.waitForTimeout(600)
  const patch = writes.find((w) => w.method === 'PATCH')
  ck('super admin: a text edit sends a PATCH to that video', !!patch
     && patch.path === '/club-admin/super/videos/11111111-1111-1111-1111-111111111111', patch?.path)
  const patchBody = patch?.postDataBuffer || ''
  ck('super admin: the PATCH carries the new title', patchBody.includes('Merging duplicate players'))
  ck('super admin: the PATCH carries NO video file when none was picked',
     !/name="video"/.test(patchBody))

  // --- delete, dismissed then accepted
  writes.length = 0
  page.once('dialog', (d) => d.dismiss())
  await page.getByRole('button', { name: 'DELETE', exact: true }).first().click()
  await page.waitForTimeout(400)
  ck('super admin: a DISMISSED delete sends nothing', writes.length === 0, `${writes.length} writes`)

  let confirmText = ''
  page.once('dialog', (d) => { confirmText = d.message(); d.accept() })
  await page.getByRole('button', { name: 'DELETE', exact: true }).first().click()
  await page.waitForTimeout(600)
  ck('super admin: the confirm names the video and says the file goes',
     confirmText.includes('BetterCricket - Merge Players') && confirmText.includes('video file'),
     confirmText)
  const del = writes.find((w) => w.method === 'DELETE')
  ck('super admin: an accepted delete sends the DELETE', !!del
     && del.path === '/club-admin/super/videos/11111111-1111-1111-1111-111111111111', del?.path)

  // --- reorder by drag
  await page.reload({ waitUntil: 'networkidle' })
  await page.waitForTimeout(400)
  writes.length = 0
  await page.getByRole('button', { name: 'REORDER' }).click()
  await page.waitForTimeout(250)
  ck('super admin: reorder mode makes the cards draggable', await page.evaluate(
    () => [...document.querySelectorAll('[data-video-slug]')].every((e) => e.draggable)))
  ck('super admin: reorder mode withdraws the card links so a drag cannot navigate',
     await page.locator('#main-content a[href^="/videos/"]').count() === 0)

  // dragstart and drop must be dispatched in SEPARATE evaluate calls, or React
  // has not re-rendered with the drag in flight and the drop reads as refused.
  await page.evaluate(() => {
    const from = document.querySelector('[data-video-slug="selection"]')
    const dt = new DataTransfer()
    window.__dt = dt
    from.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }))
  })
  await page.waitForTimeout(150)
  await page.evaluate(() => {
    const to = document.querySelector('[data-video-slug="merge-players"]')
    to.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: window.__dt }))
    to.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: window.__dt }))
  })
  await page.waitForTimeout(600)

  const reorder = writes.find((w) => w.path === '/club-admin/super/videos/reorder')
  ck('super admin: the drop sends a reorder', !!reorder, writes.map((w) => w.path).join(', '))
  if (reorder) {
    const ids = JSON.parse(reorder.body || reorder.postDataBuffer || '{}').ids || []
    ck('super admin: the reorder sends every video, not just the moved one',
       ids.length === VIDEOS.length, `${ids.length} ids`)
    ck('super admin: the dragged video is sent in its new position',
       ids[0] === '33333333-3333-3333-3333-333333333333', ids.join(', '))
  }

  ck('super admin: no page errors', errors.length === 0, errors.join(' | '))

  // The detail page's own edit affordance.
  await page.goto(`${BASE}/videos/merge-players`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(400)
  ck('super admin: the detail page offers an edit control',
     await page.getByRole('button', { name: 'EDIT THIS VIDEO' }).isVisible())
  await ctx.close()
}

// ---------------------------------------------------------- reachability
{
  const { page, ctx } = await openPage(null)
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
  ck('home: footer links to Videos', await page.locator('footer a[href="/videos"]').count() > 0)

  // The nav row is measured, not eyeballed: a sixth link overflowed its own
  // box below lg, so Videos is held out of the row there and the mobile menu
  // and footer carry it instead.
  for (const width of [1440, 1024, 900, 820, 768]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(200)
    const m = await page.evaluate(() => {
      const bar = document.querySelector('nav > div')
      const doc = document.documentElement
      return { bar: bar.scrollWidth - bar.clientWidth, doc: doc.scrollWidth - doc.clientWidth }
    })
    // 16px at 768 is the pre-existing baseline with five links; the point is
    // that adding Videos does not make it worse.
    const budget = width === 768 ? 16 : 0
    ck(`nav: bar overflow at ${width}px is within the pre-existing budget`, m.bar <= budget, `${m.bar}px`)
    ck(`nav: page does not scroll sideways at ${width}px`, m.doc <= 0, `${m.doc}px`)
    if (width >= 1024) {
      ck(`nav: Videos is in the row at ${width}px`,
         await page.locator('nav a[href="/videos"]').first().isVisible())
    }
  }

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${BASE}/videos`, { waitUntil: 'networkidle' })
  await page.locator('nav button[aria-controls="mobile-nav"]').click()
  await page.waitForTimeout(250)
  ck('mobile: the menu offers Videos', await page.locator('#mobile-nav a[href="/videos"]').isVisible())
  await page.locator('nav button[aria-controls="mobile-nav"]').click()
  await page.waitForTimeout(200)

  for (const path of ['/videos', '/videos/merge-players']) {
    await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(400)
    const o = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth)
    ck(`mobile: no horizontal overflow at 390px on ${path}`, o <= 0, `${o}px`)
  }
  await ctx.close()
}

await browser.close()
console.log(`\n${pass}/${pass + fail} checks passed`)
process.exit(fail ? 1 : 0)
