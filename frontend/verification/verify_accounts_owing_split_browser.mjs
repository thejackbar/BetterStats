// Drives the real BetterFees Accounts screen in Chromium with the API stubbed at
// the network layer: the owing filter split into Owes money / Owes membership /
// Owes match fees, the per-row breakdown, and the CSV export of what is listed.
//
//   npx vite preview --outDir <build> --port 5199 &
//   node frontend/verification/verify_accounts_owing_split_browser.mjs [baseUrl]
//
// Control run: against the previous commit there is no split, so the new checks
// fail (each reads its element through an absence-safe helper, not a throw).
import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:5199'
const EXECUTABLE = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => {
  if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) }
}

const SEASON = { id: 'se1', name: '2026/27', year: 2026 }
const base = {
  email: '', mobile: '', is_linked: true, membership_type_id: null, is_life_member: false, is_honorary: false,
  playhq_registered: true, match_days: 0, in_credit: false, credit: 0, needs_tier: false, tier: 'Senior',
  membership_payable: 0, membership_paid: 0, match_fee_payable: 0, match_fee_paid: 0,
}
const mk = (n, o) => ({ ...base, member_id: `m-${n}`, member_season_id: `ms-${n}`, ...o })
const MEMBERS = [
  mk('a', { full_name: 'Alan Membership', email: 'alan@x.com', status: 'non_financial', membership_payable: 200, membership_paid: 100,
    membership_outstanding: 100, match_fee_outstanding: 0, total_payable: 200, total_paid: 100, total_outstanding: 100 }),
  mk('b', { full_name: 'Bec Matchfees', status: 'non_financial', match_days: 4, membership_payable: 200, membership_paid: 200,
    match_fee_payable: 80, match_fee_paid: 40, membership_outstanding: 0, match_fee_outstanding: 40,
    total_payable: 280, total_paid: 240, total_outstanding: 40 }),
  mk('c', { full_name: 'Cal, Both', status: 'non_financial', match_days: 3, membership_payable: 200,
    match_fee_payable: 60, membership_outstanding: 200, match_fee_outstanding: 60,
    total_payable: 260, total_paid: 0, total_outstanding: 260 }),
  mk('d', { full_name: 'Dee Paid', status: 'financial', membership_payable: 200, membership_paid: 200,
    membership_outstanding: 0, match_fee_outstanding: 0, total_payable: 200, total_paid: 200, total_outstanding: 0 }),
  mk('e', { full_name: 'Eli NoTier', status: 'needs_tier', needs_tier: true, tier: null,
    membership_outstanding: 0, match_fee_outstanding: 0, total_payable: 0, total_paid: 0, total_outstanding: 0 }),
]
const SUMMARY = {
  total_members: 5, needs_tier: 1, non_financial: 3, playhq_missing: 0,
  membership_outstanding: 300, match_fee_outstanding: 100, total_outstanding: 400,
  total_payable: 940, total_paid: 540,
}

const browser = await chromium.launch(existsSync(EXECUTABLE) ? { executablePath: EXECUTABLE } : {})

async function open(width) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 }, acceptDownloads: true })
  await ctx.addInitScript(() => {
    localStorage.setItem('token', 'stub')
    localStorage.setItem('bs_clubhouse_intro_mode_boss', JSON.stringify('never'))
  })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await page.route('**/api/**', route => {
    const url = route.request().url()
    const json = b => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })
    if (url.includes('/auth/me')) return json({ id: 'boss', username: 'boss', display_name: 'Boss', role: 'club_admin', club_slug: 'test-cc',
      entitlements: { modules: ['fees', 'comms', 'merch', 'crm', 'admin'], status: 'active' } })
    if (/\/club-admin\/fees\/members\?/.test(url)) return json({ members: MEMBERS, summary: SUMMARY })
    if (/\/club-admin\/fees\/schedule/.test(url)) return json([])
    if (/membership-types/.test(url)) return json({ types: [] })
    if (/\/seasons/.test(url)) return json([SEASON])
    return json({})
  })
  await page.goto(`${BASE}/admin/fees?season=se1`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('text=Alan Membership', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(500)
  return { page, errors, ctx }
}

const names = async page => (await page.locator('table tbody tr td:nth-child(2) a').allInnerTexts()).map(t => t.replace(/Manual/, '').trim())
const segBtn = (page, label) => page.locator('button[aria-pressed]').filter({ hasText: label }).first()
const present = async (loc) => (await loc.count().catch(() => 0)) > 0

// ── Desktop ────────────────────────────────────────────────────────────────
{
  const { page, errors, ctx } = await open(1500)
  ck('everyone lists all five', (await names(page)).length === 5, JSON.stringify(await names(page)))

  const hasMem = await present(segBtn(page, 'Owes membership'))
  const hasMatch = await present(segBtn(page, 'Owes match fees'))
  const hasAny = await present(segBtn(page, 'Owes money'))
  ck('three owing filters exist (combined, membership, match fees)', hasMem && hasMatch && hasAny, `mem=${hasMem} match=${hasMatch} any=${hasAny}`)
  if (hasMem) ck('membership filter count is 2 (Alan, Cal)', /2/.test(await segBtn(page, 'Owes membership').innerText()))
  if (hasMatch) ck('match fees filter count is 2 (Bec, Cal)', /2/.test(await segBtn(page, 'Owes match fees').innerText()))
  ck('combined filter count is 3', /3/.test(await segBtn(page, 'Owes money').innerText().catch(() => '')))

  if (hasAny) {
    await segBtn(page, 'Owes money').click(); await page.waitForTimeout(200)
    ck('combined lists Alan, Bec, Cal', JSON.stringify(await names(page)) === JSON.stringify(['Alan Membership', 'Bec Matchfees', 'Cal, Both']), JSON.stringify(await names(page)))
  }
  if (hasMem) {
    await segBtn(page, 'Owes membership').click(); await page.waitForTimeout(200)
    ck('membership lens lists Alan and Cal only', JSON.stringify(await names(page)) === JSON.stringify(['Alan Membership', 'Cal, Both']), JSON.stringify(await names(page)))
    const body = await page.locator('table tbody').innerText()
    ck('membership lens Owed column shows Cal membership part $200 and breakdown', body.includes('$200') && /Memb \$200 · Match \$60/.test(body), body.slice(0, 300))
    ck('owed column header names the lens', /MEMBERSHIP OWED/i.test(await page.locator('table thead').innerText()))

    // Export: exactly what is listed.
    const exportBtn = page.getByRole('button', { name: /Export 2 as CSV/ })
    ck('export button counts the listed people', await present(exportBtn))
    if (await present(exportBtn)) {
      const [dl] = await Promise.all([page.waitForEvent('download'), exportBtn.click()])
      const text = (await readFile(await dl.path(), 'utf8')).replace(/^﻿/, '')
      const lines = text.trim().split('\r\n')
      ck('export file is named for the lens and season', dl.suggestedFilename() === 'owing-membership-2026-27.csv', dl.suggestedFilename())
      ck('export header has the split columns', lines[0].includes('Membership owing') && lines[0].includes('Match fees owing') && lines[0].includes('Total owing'), lines[0])
      ck('export has Alan and Cal only', lines.length === 3 && lines[1].startsWith('Alan Membership') && lines[2].startsWith('"Cal, Both"'), JSON.stringify(lines))
      ck('export carries both figures for Cal', lines[2].includes(',200.00,') && lines[2].includes(',60.00,') && lines[2].includes(',260.00,'), lines[2])
    }
  }
  if (hasMatch) {
    await segBtn(page, 'Owes match fees').click(); await page.waitForTimeout(200)
    ck('match lens lists Bec and Cal only', JSON.stringify(await names(page)) === JSON.stringify(['Bec Matchfees', 'Cal, Both']), JSON.stringify(await names(page)))
    ck('match lens column header', /MATCH FEES OWED/i.test(await page.locator('table thead').innerText()))
    // Toggling it off returns everyone.
    await segBtn(page, 'Owes match fees').click(); await page.waitForTimeout(200)
    ck('toggling the lens off lists everyone again', (await names(page)).length === 5)
  }
  ck('no page errors', errors.length === 0, errors.join(' | '))
  await ctx.close()
}

// ── 390px ──────────────────────────────────────────────────────────────────
{
  const { page, errors, ctx } = await open(390)
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  ck('390px: no horizontal overflow', over <= 0, `over=${over}`)
  const cards = await page.locator('[data-testid="accounts-cards"]').innerText().catch(() => '')
  ck('390px: card shows the membership / match split for Cal', /Membership \$200 · Match fees \$60/.test(cards), cards.slice(0, 200))
  ck('390px: no page errors', errors.length === 0, errors.join(' | '))
  await page.screenshot({ path: process.env.SHOT || '/tmp/accounts-390.png', fullPage: false })
  await ctx.close()
}

await browser.close()
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
