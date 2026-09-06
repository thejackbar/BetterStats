// Drives the real BetterAdmin → Accounts member page in Chromium with the API
// stubbed at the network layer.
//
//   npx vite --port 5199 &
//   node frontend/verification/verify_member_fees_save_browser.mjs [baseUrl]
//
// Reported off Sam Alborn's page (Applecross, 2025/26): changing the Membership
// Type and saving reset the Membership Tier, and with two panels edited only
// one panel's changes survived whichever button was pressed.
//
// The checks read what actually went ON THE WIRE, not what the screen says —
// the reported tier reset is a field the page WASN'T sending, and no amount of
// reading the rendered form can catch that.
import { existsSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) }
  else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const MEMBER_ID = '5a34c14b-92b4-4f88-a4ea-27327d6d2df2'
const SEASON_ID = 'bb617a6f-9912-5e36-9dae-79578454a1a4'
const TIER_SENIOR = 'tier-senior'
const TIER_JUNIOR = 'tier-junior'
const TYPE_SENIOR = 'type-senior'
const TYPE_SOCIAL = 'type-social'

const SCHEDULE = [
  { id: TIER_SENIOR, name: 'Senior', payment_type: 'standard', membership_amount: 200, match_day_rate: 20 },
  { id: TIER_JUNIOR, name: 'Junior', payment_type: 'standard', membership_amount: 100, match_day_rate: 10 },
]
const TYPES = [
  { id: TYPE_SENIOR, name: 'Senior Player' },
  { id: TYPE_SOCIAL, name: 'Social Member' },
]

const FINANCIALS = {
  status: 'financial', credit: 0, membership_credit: 0, match_fee_credit: 0,
  membership_payable: 200, membership_paid: 200, membership_outstanding: 0,
  match_fee_payable: 0, match_fee_paid: 0, match_fee_outstanding: 0, match_fee_waived: 0,
  total_payable: 200, total_paid: 200, total_outstanding: 0,
  match_days: 0, match_day_rate: 20, waived_days: 0, needs_tier: false,
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

/**
 * The member page with the API stubbed. The stub MUTATES on a write and the
 * page re-reads after every save, so a check can tell a working save from one
 * that reported success and changed nothing.
 */
async function openMember({ width = 1440 } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1600 } })
  const page = await ctx.newPage()
  const errors = []
  const calls = []
  page.on('pageerror', (e) => errors.push(String(e)))

  const state = {
    member: {
      id: MEMBER_ID, full_name: 'Alborn, Sam', email: 'sam@example.com', mobile: '', notes: '',
      membership_type_id: TYPE_SENIOR, is_life_member: false, is_honorary: false,
      honorary_expires_at: null, is_linked: false, player_id: null,
      email_from_player: false, mobile_from_player: false,
    },
    member_season: {
      id: 'ms-1', fee_schedule_id: TIER_SENIOR, is_new_registration: false,
      membership_payment_method: 'EFT', notes: null, status: 'active',
      playhq_registered: false, playhq_registered_at: null,
    },
  }

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = req.method()
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

    if (method !== 'GET') {
      let payload = null
      try { payload = req.postDataJSON() } catch { payload = null }
      // Page-view telemetry fires on every visit and is not a save; counting it
      // would make "pressing save with nothing edited sends nothing" unfailable
      // in the other direction.
      if (!/^\/usage\//.test(path)) calls.push({ path, method, payload })
      // Apply the write the way the server does, so the reload after a save
      // shows what was actually sent.
      if (/\/fees\/members\/[^/]+\/season$/.test(path)) {
        const b = payload || {}
        if ('fee_schedule_id' in b) state.member_season.fee_schedule_id = b.fee_schedule_id || null
        if (b.status !== undefined) state.member_season.status = b.status
        if (b.is_new_registration !== undefined) state.member_season.is_new_registration = b.is_new_registration
        if (b.membership_payment_method !== undefined) state.member_season.membership_payment_method = b.membership_payment_method
        if (b.playhq_registered !== undefined) state.member_season.playhq_registered = b.playhq_registered
      } else if (/\/fees\/members\/[^/]+$/.test(path)) {
        const b = payload || {}
        for (const k of ['full_name', 'email', 'mobile', 'notes']) if (b[k] !== undefined) state.member[k] = b[k]
        if (b.membership_type_id !== undefined) state.member.membership_type_id = b.membership_type_id || null
        if (b.is_life_member !== undefined) state.member.is_life_member = b.is_life_member
        if (b.is_honorary !== undefined) state.member.is_honorary = b.is_honorary
      }
      return json({ ok: true })
    }

    if (/^\/auth\/me/.test(path)) {
      return json({
        id: 'u1', username: 'admin', role: 'club_admin', capabilities: ['*'], club_slug: 'applecross',
        entitlements: { modules: ['stats', 'admin', 'fees'], status: 'active' },
      })
    }
    if (/^\/club-admin\/seasons$/.test(path)) return json([{ id: SEASON_ID, name: 'Summer 2025/26', year: 2025 }])
    if (/\/fees\/schedule/.test(path)) return json(SCHEDULE)
    if (/\/fees\/membership-types/.test(path)) return json({ types: TYPES })
    if (/\/fees\/members\/[^/]+$/.test(path)) {
      return json({
        member: { ...state.member }, member_season: { ...state.member_season },
        season: { id: SEASON_ID, name: 'Summer 2025/26', year: 2025 },
        financials: FINANCIALS, match_days: [], payments: [],
      })
    }
    return json({})
  })

  await page.goto(`${BASE}/admin/fees/member/${MEMBER_ID}?season=${SEASON_ID}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('text=SAVE MEMBERSHIP', { timeout: 20000 })
  await page.waitForTimeout(400)
  return { page, ctx, errors, calls, state }
}

// A panel's own <select>, addressed through the label above it. Reading "the
// first select on the page" would drift the moment a panel gains a field.
const selectUnder = (page, label) =>
  page.locator(`xpath=//label[normalize-space()='${label}']/following-sibling::select[1]`).first()

const typeSelect = (page) => selectUnder(page, 'TYPE')
const tierSelect = (page) => selectUnder(page, 'TIER')
const statusSelect = (page) => selectUnder(page, 'STATUS THIS SEASON')
const notesBox = (page) => page.locator('textarea').first()

// Press one panel's save button. Falls back to the panel's OWN label when the
// combined-save labelling isn't there, so a CONTROL RUN against a build without
// this feature reports the behaviour that is missing rather than dying on an
// absent locator and saying nothing about the other checks.
const SAVE = {
  membership: { idx: 0, re: /SAVE MEMBERSHIP/i },
  tier: { idx: 1, re: /SAVE TIER/i },
  contact: { idx: 2, re: /SAVE CONTACT/i },
}
async function pressSave(page, panel) {
  const all = page.getByRole('button', { name: /SAVE ALL CHANGES/i })
  if (await all.count() > SAVE[panel].idx) { await all.nth(SAVE[panel].idx).click(); return }
  await page.getByRole('button', { name: SAVE[panel].re }).first().click()
}

const seasonCalls = (calls) => calls.filter(c => /\/season$/.test(c.path) && c.method === 'PATCH')
const memberCalls = (calls) => calls.filter(c => /\/fees\/members\/[^/]+$/.test(c.path) && c.method === 'PATCH')

// --------------------------------------------- the reported tier reset

{
  console.log('\nChanging the Membership Type and saving')
  const { page, ctx, errors, calls, state } = await openMember()

  ck('the member opens on the Senior tier', await tierSelect(page).inputValue() === TIER_SENIOR)

  await typeSelect(page).selectOption(TYPE_SOCIAL)
  ck('the tier is untouched by picking a type — the picker does not reach across panels',
    await tierSelect(page).inputValue() === TIER_SENIOR, await tierSelect(page).inputValue())

  await page.getByRole('button', { name: /SAVE MEMBERSHIP/i }).click()
  await page.waitForTimeout(700)

  const seasonWrite = seasonCalls(calls).at(-1)
  ck('a membership save says NOTHING about the tier on the wire — the key being '
    + 'absent is what stops the server clearing it',
    !!seasonWrite && !('fee_schedule_id' in (seasonWrite.payload || {})),
    JSON.stringify(seasonWrite?.payload))
  ck('and it did send the status it was for', seasonWrite?.payload?.status === 'active',
    JSON.stringify(seasonWrite?.payload))
  ck('the membership type went to the person endpoint',
    memberCalls(calls).at(-1)?.payload?.membership_type_id === TYPE_SOCIAL,
    JSON.stringify(memberCalls(calls).at(-1)?.payload))

  ck('THE TIER SURVIVES THE SAVE — the reported bug',
    await tierSelect(page).inputValue() === TIER_SENIOR, await tierSelect(page).inputValue())
  ck('and the stored row still holds it', state.member_season.fee_schedule_id === TIER_SENIOR,
    String(state.member_season.fee_schedule_id))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------- two panels edited, one button pressed

{
  console.log('\nEditing Membership and Tier, then pressing SAVE TIER')
  const { page, ctx, errors, calls, state } = await openMember()

  await typeSelect(page).selectOption(TYPE_SOCIAL)
  await tierSelect(page).selectOption(TIER_JUNIOR)
  await page.waitForTimeout(200)

  const unsaved = await page.locator('[data-testid="unsaved-mark"]').count()
  ck('both touched panels are marked unsaved', unsaved === 2, `${unsaved} marked`)

  const also = page.locator('[data-testid="also-saving"]')
  ck('the button says what else it will write before it is pressed',
    await also.count() > 0, `${await also.count()} notes`)

  const label = await page.locator('button', { hasText: /SAVE ALL CHANGES/ }).count()
  ck('and the buttons themselves invite the whole save', label === 3, `${label} buttons`)

  await pressSave(page, 'tier')
  await page.waitForTimeout(800)

  ck('THE TIER LANDED', state.member_season.fee_schedule_id === TIER_JUNIOR,
    String(state.member_season.fee_schedule_id))
  ck('AND SO DID THE MEMBERSHIP TYPE — pressing one panel\'s button no longer '
    + 'throws the other panel\'s edit away',
    state.member.membership_type_id === TYPE_SOCIAL, String(state.member.membership_type_id))

  ck('each endpoint was written exactly once, so the two panels cannot race',
    seasonCalls(calls).length === 1 && memberCalls(calls).length === 1,
    `${memberCalls(calls).length} member, ${seasonCalls(calls).length} season`)

  await page.waitForTimeout(300)
  ck('nothing is left marked unsaved afterwards', await page.locator('[data-testid="unsaved-mark"]').count() === 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------------- all three panels, from Contact

{
  console.log('\nEditing all three panels, then pressing SAVE CONTACT')
  const { page, ctx, errors, calls, state } = await openMember()

  await typeSelect(page).selectOption(TYPE_SOCIAL)
  await statusSelect(page).selectOption('suspended')
  await tierSelect(page).selectOption(TIER_JUNIOR)
  await notesBox(page).fill('Pays by EFT')
  await page.waitForTimeout(200)

  ck('all three panels are marked unsaved', await page.locator('[data-testid="unsaved-mark"]').count() === 3)

  await pressSave(page, 'contact')
  await page.waitForTimeout(800)

  ck('the contact note landed', state.member.notes === 'Pays by EFT', String(state.member.notes))
  ck('the membership type landed', state.member.membership_type_id === TYPE_SOCIAL)
  ck('the season status landed', state.member_season.status === 'suspended', state.member_season.status)
  ck('the tier landed', state.member_season.fee_schedule_id === TIER_JUNIOR,
    String(state.member_season.fee_schedule_id))

  const mp = memberCalls(calls).at(-1)?.payload || {}
  ck('the person endpoint carried the contact AND the membership fields in one write',
    mp.notes === 'Pays by EFT' && mp.membership_type_id === TYPE_SOCIAL, JSON.stringify(mp))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------------ only the panel that was touched

{
  console.log('\nEditing only the Contact panel')
  const { page, ctx, errors, calls } = await openMember()

  await notesBox(page).fill('Just a note')
  await page.waitForTimeout(200)
  ck('only that panel is marked unsaved', await page.locator('[data-testid="unsaved-mark"]').count() === 1)
  // The two CLEAN panels say they would write the contact change, and the
  // edited panel does not claim anything beyond itself. Asserting "no note
  // anywhere" would be asserting the opposite of what was asked for.
  const notes = page.locator('[data-testid="also-saving"]')
  ck('the two untouched panels say they would save it too',
    await notes.count() === 2 && (await notes.allTextContents()).every(t => /Contact & Notes/.test(t)),
    (await notes.allTextContents()).join(' | '))
  const contactCard = page.locator('.pb-card').filter({ hasText: 'Contact & Notes' }).last()
  ck('and the panel that was edited claims nothing beyond itself',
    await contactCard.locator('[data-testid="also-saving"]').count() === 0)
  ck('the button keeps its own name when it is the only one dirty',
    await page.getByRole('button', { name: /^SAVE CONTACT$/ }).count() === 1)

  await page.getByRole('button', { name: /SAVE CONTACT/i }).click()
  await page.waitForTimeout(800)

  ck('an untouched panel writes NOTHING — a save must not re-send fields nobody edited',
    seasonCalls(calls).length === 0, JSON.stringify(seasonCalls(calls).map(c => c.payload)))
  ck('and the person endpoint carries no membership fields either',
    !('membership_type_id' in (memberCalls(calls).at(-1)?.payload || {})),
    JSON.stringify(memberCalls(calls).at(-1)?.payload))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// -------------------------------------------- pressing save with nothing to do

{
  console.log('\nPressing a save button with nothing edited')
  const { page, ctx, errors, calls } = await openMember()
  await page.getByRole('button', { name: /SAVE TIER/i }).click()
  await page.waitForTimeout(600)
  ck('nothing is sent at all', calls.length === 0, JSON.stringify(calls.map(c => c.path)))
  ck('and the screen says why rather than reporting a save that never happened',
    await page.locator('text=/No changes to save/i').count() > 0)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ------------------------------------------- clearing the tier deliberately

{
  console.log('\nClearing the tier deliberately')
  const { page, ctx, errors, calls, state } = await openMember()
  await tierSelect(page).selectOption('')
  await page.getByRole('button', { name: /SAVE TIER/i }).click()
  await page.waitForTimeout(800)
  const body = seasonCalls(calls).at(-1)?.payload || {}
  ck('the key IS present, carrying null — which is what makes an intended clear '
    + 'different from a panel that never mentioned the tier',
    'fee_schedule_id' in body && body.fee_schedule_id === null, JSON.stringify(body))
  ck('and the tier is cleared', state.member_season.fee_schedule_id === null,
    String(state.member_season.fee_schedule_id))
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// -------------------------------------------------------------------- phone

{
  console.log('\nOn a phone')
  const { page, ctx, errors } = await openMember({ width: 390 })
  await typeSelect(page).selectOption(TYPE_SOCIAL)
  await tierSelect(page).selectOption(TIER_JUNIOR)
  await page.waitForTimeout(200)
  ck('the unsaved marks still show at 390px', await page.locator('[data-testid="unsaved-mark"]').count() === 2)
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('no horizontal overflow at 390px', overflow <= 0, `${overflow}px`)
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
