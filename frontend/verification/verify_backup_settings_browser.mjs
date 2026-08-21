// Drives the REAL Backup settings screen (and the Backups page's own
// deleted-bundle state) with the API stubbed at the network layer, so what is
// asserted is the shipped components and the exact requests they put on the
// wire.
import { chromium } from 'playwright'

const BASE = 'http://localhost:5199'
let PASS = 0, FAIL = 0
const FAILURES = []
function check(label, got, want = true) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (ok) { PASS++; console.log(`  ok   ${label}`) }
  else { FAIL++; FAILURES.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); console.log(`  FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`) }
}

// Perth is UTC+8, so these UTC stamps are the Perth times the page should show.
const stamp = (n) => new Date(Date.now() - n * 86400000).toISOString().replace(/\.\d+Z$/, 'Z').replace(/:/g, '-')
// Computed once — a stamp rebuilt later in the run would differ by a second
// and stop matching what the page was given.
const B_TODAY = stamp(0), B_3D = stamp(3), B_12D = stamp(12), B_40D = stamp(40), B_90D = stamp(90)

let settings, files, wire

const run = async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))

  settings = {
    schedule: { hour: 3, minute: 0, retention_days: 30, timezone: 'Australia/Perth' },
    retention_min_days: 1, retention_max_days: 365,
    last_completed_at: new Date(Date.UTC(2026, 7, 20, 19, 4, 0)).toISOString(),
    next_run_at: new Date(Date.now() + 3600000).toISOString(),
    perth_now: new Date().toISOString(),
    agent_configured: true,
  }
  const bundles = [
    { bundle: B_TODAY, on_disk: true, size_bytes: 5_000_000, complete: true, task_id: 't1', triggered_by: 'scheduled', files: [{ name: 'db.dump.age' }, { name: 'uploads.tar.zst.age' }] },
    { bundle: B_3D, on_disk: true, size_bytes: 4_000_000, complete: true, task_id: 't2', triggered_by: 'manual', files: [{ name: 'db.dump.age' }] },
    { bundle: B_12D, on_disk: true, size_bytes: 3_000_000, complete: true, task_id: 't3', triggered_by: 'scheduled', files: [{ name: 'db.dump.age' }] },
    { bundle: B_40D, on_disk: true, size_bytes: 2_000_000, complete: false, task_id: null, triggered_by: null, files: [{ name: 'uploads.tar.zst.age' }] },
  ]
  files = { bundles, missing: [{ bundle: B_90D, task_id: 't9' }], total_size_bytes: 14_000_000, backup_root: '/mnt/media/bettercricket/backup', root_missing: false }
  wire = { patches: [], deletes: [] }

  await page.route('**/api/**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  await page.route('**/api/auth/me', (r) => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ id: 'u1', username: 'super', role: 'super_admin', club_slug: 'applecross', organisation_id: 'o1', capabilities: ['*'], entitlements: { modules: [], status: 'active' } }),
  }))
  await page.route('**/api/club-admin/super/backups/settings', (r) => {
    if (r.request().method() === 'PATCH') {
      const body = JSON.parse(r.request().postData() || '{}')
      wire.patches.push(body)
      settings = { ...settings, schedule: { ...settings.schedule, ...body } }
    }
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(settings) })
  })
  await page.route('**/api/club-admin/super/backups/files', (r) => r.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify(files),
  }))
  await page.route('**/api/club-admin/super/backups/files/delete', (r) => {
    const body = JSON.parse(r.request().postData() || '{}')
    wire.deletes.push(body)
    files = { ...files, bundles: files.bundles.filter((b) => !body.bundles.includes(b.bundle)) }
    return r.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ results: body.bundles.map((b) => ({ bundle: b, status: 'deleted' })), deleted_count: body.bundles.length, failed_count: 0, freed_bytes: 3_000_000 }),
    })
  })

  console.log('\n── The schedule reads in Perth time ──')
  await page.goto(`${BASE}/admin/super/backup-settings`)
  await page.waitForSelector('text=Schedule and retention', { timeout: 15000 })
  check('the hour is the Perth hour, not a UTC one', await page.locator('input[type=number]').first().inputValue(), '3')
  check('the minute is shown', await page.locator('input[type=number]').nth(1).inputValue(), '0')
  check('retention shows the stored 30 days', await page.locator('input[type=number]').nth(2).inputValue(), '30')
  check('the sentence says what it does', await page.locator('text=/runs daily at/').count() > 0, true)
  check('it labels the hour as Perth', await page.locator('text=Hour (Perth)').count(), 1)
  check('Save is dead until something changes', await page.getByRole('button', { name: 'Save' }).isDisabled(), true)
  check('the last run is shown in Perth (03:04, not 19:04)', await page.locator('text=/03:04/').count() > 0, true)
  check('the next run is shown', await page.locator('text=Next run').count(), 1)
  check('it says a missed run is caught up', await page.locator('text=/taken on the next tick/').count() > 0, true)

  console.log('\n── Changing retention from 30 days to 7 ──')
  const retention = page.locator('input[type=number]').nth(2)
  await retention.fill('7')
  check('shortening warns that nothing is deleted on save', await page.locator('text=/Shortening the window/').count() > 0, true)
  check('Save is live now', await page.getByRole('button', { name: 'Save' }).isDisabled(), false)
  await page.getByRole('button', { name: 'Save' }).click()
  await page.waitForSelector('text=/next scheduled run uses this/', { timeout: 10000 })
  check('the exact payload on the wire', wire.patches, [{ hour: 3, minute: 0, retention_days: 7 }])
  check('the page now reads 7 days', await page.locator('text=/keeps\\s*7\\s*days/').count() > 0, true)

  console.log('\n── Changing the time ──')
  await page.locator('input[type=number]').first().fill('21')
  await page.locator('input[type=number]').nth(1).fill('30')
  await page.getByRole('button', { name: 'Save' }).click()
  await page.waitForTimeout(500)
  check('a Perth time goes on the wire unconverted', wire.patches[1], { hour: 21, minute: 30, retention_days: 7 })

  console.log('\n── The stored backups list ──')
  check('every bundle on disk is listed', await page.locator('table').last().locator('tbody tr').count(), 4)
  check('the total size is stated', await page.locator('text=/13 MB total/').count() > 0, true)
  check('the backup directory is named', await page.getByText('/mnt/media/bettercricket/backup').count() > 0, true)
  check('an incomplete bundle says so', await page.locator('text=/no database dump/').count(), 1)
  check('a bundle with no task row says the trigger is not logged', await page.locator('text=not logged').count(), 1)
  check('bundles past the retention window are flagged', await page.locator('text=past retention').count(), 2)
  check('Delete is dead with nothing selected', await page.getByRole('button', { name: 'Delete selected' }).isDisabled(), true)

  console.log('\n── Selecting what the next run would prune anyway ──')
  await page.getByRole('button', { name: /Select older than 7 days/ }).click()
  check('it selects exactly the out-of-window ones', await page.locator('text=/2 selected/').count() > 0, true)
  check('...and totals what that frees', await page.locator('text=/2 selected · 4.8 MB/').count() > 0, true)

  console.log('\n── The confirm names what goes ──')
  await page.getByRole('button', { name: 'Delete selected' }).click()
  await page.waitForSelector('text=/Delete 2 backups\\?/', { timeout: 5000 })
  check('it says the files go and the history stays', await page.locator('text=/The run history, sizes and per-club record counts/').count() > 0, true)
  check('it names each bundle', await page.locator(`text=${B_12D}`).count() > 0, true)
  await page.getByRole('button', { name: 'Cancel' }).click()
  await page.waitForTimeout(300)
  check('cancelling deletes nothing', wire.deletes, [])
  check('...and keeps the selection', await page.locator('text=/2 selected/').count() > 0, true)

  console.log('\n── Deleting them ──')
  await page.getByRole('button', { name: 'Delete selected' }).click()
  await page.waitForSelector('text=/Delete 2 backups\\?/', { timeout: 5000 })
  await page.locator('.fixed.inset-0').getByRole('button', { name: 'Delete', exact: true }).click()
  await page.waitForSelector('text=/Deleted 2 backups/', { timeout: 10000 })
  check('the exact payload on the wire', wire.deletes, [{ bundles: [B_12D, B_40D], include_latest: false }])
  check('the list refreshes without them', await page.locator('table').last().locator('tbody tr').count(), 2)
  check('the selection is cleared', await page.locator('text=/0 selected/').count() > 0, true)

  console.log('\n── The newest backup needs its own confirmation ──')
  await page.getByRole('button', { name: 'Select all' }).click()
  await page.getByRole('button', { name: 'Delete selected' }).click()
  await page.waitForSelector('text=/Delete 2 backups\\?/', { timeout: 5000 })
  const confirmBtn = page.locator('.fixed.inset-0').getByRole('button', { name: 'Delete', exact: true })
  check('Delete is blocked while the newest is in the selection', await confirmBtn.isDisabled(), true)
  check('it says which one and why', await page.locator('text=/the one a restore would use/').count() > 0, true)
  await page.locator('.fixed.inset-0 input[type=checkbox]').first().check()
  check('ticking it releases the button', await confirmBtn.isDisabled(), false)
  await confirmBtn.click()
  await page.waitForTimeout(600)
  check('and only then does include_latest go on the wire', wire.deletes[1].include_latest, true)

  console.log('\n── The Backups page reflects a deleted bundle ──')
  // A URL predicate, not a glob: Playwright globs treat "?" as a single-char
  // wildcard, so "backups?**" would also swallow "backups/settings".
  await page.route((u) => u.pathname.endsWith('/club-admin/super/backups'), (r) => r.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ total: 2, tasks: [
      { id: 't1', task_type: 'backup', status: 'completed', triggered_by: 'scheduled', started_at: new Date().toISOString(), bundle_path: '/b/one', db_size_bytes: 1000, uploads_size_bytes: 500, total_row_count: 10, bundle_deleted_at: null, bundle_deleted_reason: null },
      { id: 't2', task_type: 'backup', status: 'completed', triggered_by: 'scheduled', started_at: new Date().toISOString(), bundle_path: '/b/two', db_size_bytes: 1000, uploads_size_bytes: 500, total_row_count: 10, bundle_deleted_at: new Date().toISOString(), bundle_deleted_reason: 'retention' },
    ] }),
  }))
  await page.goto(`${BASE}/admin/super/backups`)
  await page.waitForSelector('text=Backup settings', { timeout: 15000 })
  check('it links across to the settings screen', await page.getByRole('link', { name: 'Backup settings' }).count(), 1)
  check('a deleted bundle says its files are gone', await page.locator('text=/Files deleted \\(retention\\)/').count(), 1)
  // Scoped to the table — the filter row above it has a button of the same name.
  check('...and is offered no restore', await page.locator('table').getByRole('button', { name: 'Restore (full)' }).count(), 1)
  check('...nor a download', await page.getByRole('button', { name: 'DB' }).count(), 1)

  console.log('\n── Housekeeping ──')
  await page.goto(`${BASE}/admin/super/backup-settings`)
  await page.waitForSelector('text=Schedule and retention', { timeout: 15000 })
  check('no page errors', errors, [])
  check('no horizontal overflow at 1280px', await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(500)
  check('no horizontal overflow at 390px', await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false)

  await browser.close()
  console.log(`\n${'='.repeat(60)}\n${PASS} passed, ${FAIL} failed`)
  if (FAILURES.length) { console.log('\nFailures:'); FAILURES.forEach((f) => console.log('  -', f)) }
  process.exit(FAIL ? 1 : 0)
}

run().catch((e) => { console.error(e); process.exit(1) })
