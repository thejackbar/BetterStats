// The Accounts screen's "who owes what" lens. Pure functions over the rows
// GET /club-admin/fees/members already returns (membership_outstanding and
// match_fee_outstanding are computed server-side by _financials), so nothing
// here re-derives a balance.
//
// Only a non_financial row can owe: a complimentary tier reads Financial even
// if a stray amount sits on it, and the lens must agree with the status pill.

export const OWING_LENSES = {
  any: { label: 'Owes money', owed: 'OWED', file: 'owing', pick: m => m.total_outstanding },
  membership: { label: 'Owes membership', owed: 'MEMBERSHIP OWED', file: 'owing-membership', pick: m => m.membership_outstanding },
  match: { label: 'Owes match fees', owed: 'MATCH FEES OWED', file: 'owing-match-fees', pick: m => m.match_fee_outstanding },
}

const num = v => Number(v) || 0

export function owesLens(m, lens) {
  if (m.status !== 'non_financial') return false
  if (lens === 'membership') return num(m.membership_outstanding) > 0
  if (lens === 'match') return num(m.match_fee_outstanding) > 0
  return true
}

// The figure a row shows in the Owed column under a lens ('' is the plain total).
export function owedUnder(m, lens) {
  return num((OWING_LENSES[lens] || OWING_LENSES.any).pick(m))
}

export function lensCounts(members) {
  const c = { any: 0, membership: 0, match: 0 }
  for (const m of members || []) {
    for (const k of Object.keys(c)) if (owesLens(m, k)) c[k] += 1
  }
  return c
}

function cell(v) {
  const s = v == null ? '' : String(v)
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

const COLS = [
  ['Name', m => m.full_name],
  ['Email', m => m.email || ''],
  ['Mobile', m => m.mobile || ''],
  ['Tier', m => m.tier || ''],
  ['Match days', m => num(m.match_days)],
  ['Membership payable', m => num(m.membership_payable).toFixed(2)],
  ['Membership paid', m => num(m.membership_paid).toFixed(2)],
  ['Membership owing', m => num(m.membership_outstanding).toFixed(2)],
  ['Match fees payable', m => num(m.match_fee_payable).toFixed(2)],
  ['Match fees paid', m => num(m.match_fee_paid).toFixed(2)],
  ['Match fees owing', m => num(m.match_fee_outstanding).toFixed(2)],
  ['Total owing', m => num(m.total_outstanding).toFixed(2)],
  ['Status', m => (m.status === 'non_financial' ? 'Owes' : m.status === 'needs_tier' ? 'Needs tier' : 'Financial')],
]

// Excel-friendly (BOM, CRLF). Every row in `rows` is written, so the export is
// exactly the list on screen: lens, search and People filters included.
export function accountsToCsv(rows) {
  const lines = [COLS.map(([h]) => cell(h)).join(',')]
  for (const m of rows) lines.push(COLS.map(([, f]) => cell(f(m))).join(','))
  return '﻿' + lines.join('\r\n')
}

export function accountsCsvName(seasonName, lens) {
  const slug = String(seasonName || 'season').trim().replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'season'
  const part = lens && OWING_LENSES[lens] ? OWING_LENSES[lens].file : 'accounts'
  return `${part}-${slug}.csv`.toLowerCase()
}
