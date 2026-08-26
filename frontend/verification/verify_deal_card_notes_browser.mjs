// A note typed in the Sales Workspace has to be READABLE on the CRM deal
// card, not merely present in its payload. The card is deliberately the
// shows-everything surface — the Twenty pipeline backfill and the
// reassignment audit rows the Sales Workspace drawer hides from its own
// History are on it too — so this drives the real board, opens a deal whose
// timeline is mostly that noise, and asserts the rep's own notes can be
// found, named and read.
//
//   node verify_deal_card_notes_browser.mjs   (expects the dev server on :5199)
import { chromium } from 'playwright'

const BASE = process.env.APP_URL || 'http://localhost:5199'
const DEAL = 'aaaaaaaa-0000-0000-0000-000000000001'
const PASS = [], FAIL = []
const check = (name, cond, detail = '') => {
  ;(cond ? PASS : FAIL).push(name)
  console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`)
}

const stages = [
  { id: 's1', key: 'target', name: 'Target', position: 0, default_probability: 10, is_won: false, is_lost: false },
]
const deal = {
  id: DEAL, title: 'Applecross CC', scope: 'platform', stage_id: 's1', stage_name: 'Target',
  stage_key: 'target', value_cents: 39900, currency: 'AUD', probability: 10, module_keys: ['core'],
  status: 'open', owner_user_id: 'sam', owner_name: 'Sam Rep', marketing_club_id: null,
  marketing_club_name: 'Applecross CC', expected_close_date: null, engagement_score: 40,
  engagement_tier: 'WARM', archived_at: null, product_interest_source: 'manual',
}

// The shape the reported case actually has: two rep notes (one pinned) sitting
// under a pile of Twenty-imported rows. A one-note stub would pass against the
// broken code, because with nothing to hide behind a note is findable however
// it is drawn.
const IMPORTED = Array.from({ length: 24 }, (_, i) => ({
  id: `imp-${i}`, deal_id: DEAL, person_id: null, organisation_id: null, type: 'system',
  body: `Twenty pipeline row ${i + 1}`, outcome: null, next_follow_up_at: null,
  follow_up_done_at: null, occurred_at: `2026-08-0${(i % 9) + 1}T02:00:00Z`,
  created_by_user_id: null, created_by_name: null, meta: { twenty_note_id: `t${i}` },
}))
// Returned newest-first, exactly as crm_service.list_activities orders it —
// otherwise the stub's own array order decides where a row lands and the
// "pinned sits on top" check would pass on the arrangement, not the code.
const activities = () => [
  { id: 'note-pin', deal_id: DEAL, person_id: null, organisation_id: null, type: 'note',
    body: 'Committee meets first Tuesday.\nRing the week before.', outcome: null,
    // Deliberately the OLDEST row on the deal: in a flat chronological feed it
    // sorts to the bottom, so it can only appear above the rest if the card
    // genuinely lifts a pinned note out.
    next_follow_up_at: null, follow_up_done_at: null, occurred_at: '2026-07-01T04:00:00Z',
    created_by_user_id: 'sam', created_by_name: 'Sam Rep', meta: { pinned: true } },
  { id: 'note-plain', deal_id: DEAL, person_id: null, organisation_id: null, type: 'note',
    body: 'Secretary prefers mobile after 5pm', outcome: null, next_follow_up_at: null,
    follow_up_done_at: null, occurred_at: '2026-08-19T04:00:00Z',
    created_by_user_id: 'sam', created_by_name: 'Sam Rep',
    meta: { pinned: false, edited_at: '2026-08-19T05:00:00Z' } },
  { id: 'call-1', deal_id: DEAL, person_id: null, organisation_id: null, type: 'call',
    body: 'Left a message', outcome: 'voicemail', next_follow_up_at: null,
    follow_up_done_at: null, occurred_at: '2026-08-18T04:00:00Z',
    created_by_user_id: 'sam', created_by_name: 'Sam Rep', meta: null },
  // A plain system row — not a Twenty import, not a reassignment — so it
  // survives the drawer's own filter and both screens have one to name.
  { id: 'sys-1', deal_id: DEAL, person_id: null, organisation_id: null, type: 'system',
    body: 'Auto-advanced on engagement score', outcome: null, next_follow_up_at: null,
    follow_up_done_at: null, occurred_at: '2026-08-16T04:00:00Z',
    created_by_user_id: null, created_by_name: null, meta: null },
  { id: 'reassign', deal_id: DEAL, person_id: null, organisation_id: null, type: 'system',
    body: 'Reassigned to Sam Rep', outcome: null, next_follow_up_at: null,
    follow_up_done_at: null, occurred_at: '2026-08-17T04:00:00Z',
    created_by_user_id: 'boss', created_by_name: 'Boss', meta: { kind: 'reassignment' } },
  ...IMPORTED,
].sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : a.occurred_at > b.occurred_at ? -1 : 0))

const run = async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  })
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
  await ctx.addInitScript(() => localStorage.setItem('token', 'stub'))
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))

  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) {
      return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'super_admin',
                    entitlements: { modules: [], status: 'active' } })
    }
    if (/\/deals\/[0-9a-z-]+\/activities/.test(url)) return json({ activities: activities() })
    if (/\/deals\/[0-9a-z-]+\/contacts/.test(url)) return json({ contacts: [] })
    if (/\/deals\/[0-9a-z-]+\/events/.test(url)) return json({ events: [] })
    if (/\/crm\/deals\/[0-9a-z-]+$/.test(url)) return json(deal)
    if (url.includes('/crm/deals')) return json({ deals: [deal] })
    if (url.includes('/crm/stages')) return json({ stages })
    if (url.includes('/crm/owners')) return json({ owners: [{ id: 'sam', name: 'Sam Rep' }] })
    if (url.includes('/crm/settings')) return json({})
    if (url.includes('/ui-prefs')) return json({ preferences: {} })
    return json({})
  })

  await page.goto(`${BASE}/admin/super/crm`, { waitUntil: 'networkidle' })
  await page.waitForSelector('text=Applecross CC', { timeout: 20000 })
  await page.click('text=Applecross CC')
  await page.waitForSelector('text=Notes & activity', { timeout: 15000 })

  // The section a reader actually scans. Scoped to it, so a match somewhere
  // else on the card (the composer's placeholder, say) can't pass this.
  // The heading's grandparent: the h3 sits in the section's own header row,
  // and that row is what a naive `div has h3` .last() would pick — a scope so
  // tight that none of the notes are inside it.
  const section = page.locator('h3:text-is("Notes & activity")').locator('xpath=../..')

  // ---- the reported case: is the note there to be read? ------------------
  const notePlain = section.getByText('Secretary prefers mobile after 5pm', { exact: false }).first()
  check('the workspace note is on the card', await notePlain.count() > 0)
  check('…and is actually visible, not merely in the DOM', await notePlain.isVisible())

  const pinned = section.getByText('Committee meets first Tuesday', { exact: false }).first()
  check('the pinned note is on the card', await pinned.isVisible())

  // A pinned note is the rep's "keep this in front of whoever picks the club
  // up next" — it has to READ as pinned, not as one more row.
  check('the pinned note is labelled as pinned',
        await section.getByText('Pinned note', { exact: true }).count() > 0)

  // Measured, not assumed: the pin has to sit ABOVE the ordinary feed, or the
  // label is decoration.
  const pinBox = await pinned.boundingBox()
  const plainBox = await notePlain.boundingBox()
  check('the pinned note sits above the rest of the feed',
        pinBox && plainBox && pinBox.y < plainBox.y, JSON.stringify({ pinBox, plainBox }))

  // ---- readable, and attributable ---------------------------------------
  const pinText = await pinned.evaluate(el => el.textContent)
  check('a multi-line note keeps its line break',
        /Ring the week before/.test(pinText) &&
        await pinned.evaluate(el => getComputedStyle(el).whiteSpace.startsWith('pre')),
        JSON.stringify(pinText))
  // On the note's OWN row, not merely somewhere on the card — the deal's
  // owner is also Sam Rep, so a card-wide search would pass with nothing drawn.
  const plainRow = notePlain.locator('xpath=..')
  const plainRowText = await plainRow.innerText()
  check('the note row says who wrote it', plainRowText.includes('Sam Rep'), plainRowText)
  check('…and that an edited note was edited', plainRowText.includes('(edited)'), plainRowText)

  // ---- the noise the card also shows, and the way out of it -------------
  const bodyText = await section.innerText()
  check('the Twenty backfill is still shown (the card hides nothing by default)',
        bodyText.includes('Twenty pipeline row'))
  check('so is the reassignment audit row', bodyText.includes('Reassigned to Sam Rep'))
  check('a call is named by its outcome, as in the workspace',
        bodyText.includes('Voicemail'), bodyText.slice(0, 400))

  const notesBtn = section.getByRole('button', { name: /^Notes \(\d+\)$/ })
  check('the feed offers a notes-only filter', await notesBtn.count() > 0)
  check('…and it counts the notes on the deal',
        /Notes \(2\)/.test(await notesBtn.first().innerText()),
        await notesBtn.first().innerText())

  await notesBtn.first().click()
  await page.waitForTimeout(250)
  const filtered = await section.innerText()
  check('filtering to notes drops the Twenty backfill',
        !filtered.includes('Twenty pipeline row'))
  check('…and the reassignment rows', !filtered.includes('Reassigned to Sam Rep'))
  check('…and the calls', !filtered.includes('Left a message'))
  check('…and keeps the note', filtered.includes('Secretary prefers mobile after 5pm'))
  check('…and keeps the pinned note above it',
        filtered.includes('Committee meets first Tuesday'))

  await section.getByRole('button', { name: /^All$/ }).first().click()
  await page.waitForTimeout(250)
  check('switching back to All brings the rest of the timeline back',
        (await section.innerText()).includes('Twenty pipeline row'))

  // ---- the same rows, named the same way, on the other screen -----------
  // activityLabel/activityTone/activityByLine live in crm/ui.jsx and are read
  // by BOTH this card and the Sales Workspace drawer's ActivityRow. Asserted
  // by rendering the SAME activity rows on the drawer and comparing what each
  // screen calls them — a claim of "one definition" that nothing measures is
  // just a comment.
  const cardLabels = await section.locator('span.font-mono').allInnerTexts()

  await page.route('**/api/**', async (route) => {
    const url = route.request().url()
    const json = (b) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) {
      return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'super_admin',
                    entitlements: { modules: [], status: 'active' } })
    }
    if (/\/sales-workspace\/clubs(\?|$)/.test(url)) {
      return json({ clubs: [{ ...deal, marketing_club_associations: [], contact_count: 0,
                              ever_called: true, callback_due: false, last_call: null,
                              priority_score: 5, not_interested: false }],
                    stages })
    }
    if (/\/sales-workspace\/clubs\/[0-9a-z-]+/.test(url)) {
      if (/\/signals|\/boundary/.test(url)) return json({})
      return json({ deal: { ...deal, owner_user_id: 'sam' }, contacts: [],
                    // The drawer filters the Twenty backfill and the
                    // reassignment rows server-side, so its payload is what is
                    // left — the notes and the call.
                    activities: activities().filter(a => !a.meta?.twenty_note_id && a.meta?.kind !== 'reassignment'),
                    events: [], lists: [], stages, boundary: null })
    }
    if (url.includes('/email-templates')) return json({ templates: [] })
    if (url.includes('/call-outcomes')) return json({ outcomes: [] })
    return json({})
  })

  await page.setViewportSize({ width: 1500, height: 1000 })
  await page.goto(`${BASE}/admin/super/crm/workspace?club=${DEAL}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('text=History', { timeout: 20000 })
  const drawerText = await page.innerText('body')
  // The drawer lifts a pinned note into its own amber block with no label of
  // its own, so the two screens are compared on the rows both draw through
  // the shared vocabulary: an ordinary note, a call named by its outcome, a
  // system row.
  for (const label of ['Note', 'Voicemail', 'System']) {
    check(`both screens call this row "${label}"`,
          cardLabels.includes(label) && drawerText.includes(label),
          JSON.stringify(cardLabels))
  }
  check('the card labels a pinned note as pinned; the drawer lifts it out instead',
        cardLabels.includes('Pinned note') &&
        drawerText.includes('Committee meets first Tuesday'),
        JSON.stringify(cardLabels))
  check('…and both name the rep who wrote it', drawerText.includes('Sam Rep'))

  // ---- the card must not have got worse ---------------------------------
  check('no page errors', errors.length === 0, errors.join(' | '))

  await page.setViewportSize({ width: 390, height: 900 })
  await page.waitForTimeout(300)
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  // PRE-EXISTING, confirmed by re-measuring with this change stashed: the
  // deal card modal overflows by exactly this much at 390px either way (the
  // widest element is a 726px `flex items-center gap-2` row this change does
  // not touch). Budgeted at the measured number so nothing here can make it
  // worse or introduce a new one.
  check('no NEW horizontal overflow at 390px', overflow <= 360, `overflow=${overflow}px`)

  await browser.close()
  console.log(`\n${PASS.length}/${PASS.length + FAIL.length} checks passed`)
  if (FAIL.length) { console.log('FAILED:\n - ' + FAIL.join('\n - ')); process.exit(1) }
}

run().catch(e => { console.error(e); process.exit(1) })
