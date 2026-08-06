import { useState, useEffect, useMemo, useCallback } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterFeesLayout from '../../components/admin/BetterFeesLayout'
import { Button, Field, Select, StatReadout, Caption, INPUT_CLS } from '../../components/admin/ui'
import { PbSpinner } from '../../lib/presskit'

import { formatSeason } from '../../lib/cricketFormat'

const money = n => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
const PAY_METHODS = ['EFT', 'Cash', 'PlayHQ', 'Other']

function sortSeasons(seasons) {
  return seasons.filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0) || (b.name > a.name ? 1 : -1))
}

// ── One row in the split list ───────────────────────────────────────────────
function BulkRow({ row, idx, members, onChange, onRemove, onLoadDays }) {
  const [memberSearch, setMemberSearch] = useState('')
  // Filtered member list for the picker dropdown (cap at 80 for perf).
  const filtered = useMemo(() => {
    const q = memberSearch.trim().toLowerCase()
    return (members || []).filter(m =>
      !q || m.full_name.toLowerCase().includes(q) || (m.tier || '').toLowerCase().includes(q)
    ).slice(0, 80)
  }, [members, memberSearch])

  const isMatchDay = row.kind === 'match_day'
  const unpaid = (row.unpaid_days || []).filter(d => !row.match_day_ids.includes(d.id) ? true : true)
  const selectedDays = (row.unpaid_days || []).filter(d => row.match_day_ids.includes(d.id))
  const computedFromDays = selectedDays.reduce((sum, d) => sum + (Number(row.match_day_rate) * Number(d.days_played)), 0)

  function toggleDay(dayId, daysPlayed) {
    const has = row.match_day_ids.includes(dayId)
    const next = has
      ? row.match_day_ids.filter(x => x !== dayId)
      : [...row.match_day_ids, dayId]
    // Auto-update amount to sum of selected days × rate (admin can still override).
    const newAmount = next.reduce((sum, id) => {
      const d = (row.unpaid_days || []).find(x => x.id === id)
      return sum + (d ? Number(row.match_day_rate) * Number(d.days_played) : 0)
    }, 0)
    onChange(idx, { match_day_ids: next, amount: newAmount.toFixed(2) })
  }

  return (
    <div className={`pb-card p-4 ${row.member_season_id ? '' : 'border-pb-amber/30'}`}>
      <div className="grid grid-cols-1 sm:grid-cols-[1.4fr_auto_auto_auto] gap-3 items-end">
        <Field label="Member">
          {row.member_season_id ? (
            <div className="flex items-center gap-2">
              <span className="text-pb-text text-[13.5px] flex-1">{row.full_name}</span>
              <Button size="sm" variant="quiet"
                onClick={() => onChange(idx, { member_season_id: '', member_id: '', full_name: '', match_day_ids: [], unpaid_days: [] })}>
                Change
              </Button>
            </div>
          ) : (
            <div>
              <input className={INPUT_CLS} placeholder="Search members…"
                value={memberSearch} onChange={e => setMemberSearch(e.target.value)} />
              {memberSearch.trim() && (
                <div className="mt-1 max-h-48 overflow-y-auto pb-scroll border border-pb-hairline2 rounded-lg bg-pb-surface">
                  {filtered.length === 0 && <div className="px-3 py-2 text-[12.5px] text-pb-faintest">No match</div>}
                  {filtered.map(m => (
                    <button key={m.member_season_id} onClick={() => {
                      onChange(idx, {
                        member_season_id: m.member_season_id, member_id: m.member_id, full_name: m.full_name,
                        match_day_rate: m.match_day_rate || 0,
                        match_day_ids: [], unpaid_days: [],
                      })
                      setMemberSearch('')
                      onLoadDays(idx, m.member_id)
                    }}
                      className="block w-full text-left px-3 py-1.5 text-[13px] text-pb-text hover:bg-pb-surface2 transition-colors">
                      {m.full_name}
                      {m.needs_tier && <span className="ml-2 font-mono text-[9px] text-pb-amber">⚠ needs tier</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </Field>
        <Field label="Kind">
          <select className={`${INPUT_CLS} cursor-pointer !w-32`} value={row.kind}
            onChange={e => onChange(idx, { kind: e.target.value, match_day_ids: [] })}>
            <option value="match_day">Match day</option>
            <option value="membership">Membership</option>
          </select>
        </Field>
        <Field label="Amount">
          <input type="number" min="0" step="0.01" className={`${INPUT_CLS} !w-24 text-right pb-num`}
            value={row.amount} onChange={e => onChange(idx, { amount: e.target.value })} />
        </Field>
        <Button variant="danger" size="sm" onClick={() => onRemove(idx)} className="mb-0.5">Remove</Button>
      </div>

      {isMatchDay && row.member_season_id && (
        <div className="mt-3 pt-3 border-t pb-hairline-t">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <Caption>Unpaid match days</Caption>
            <span className="font-mono text-[9px] text-pb-faintest">
              {(row.unpaid_days || []).length === 0 ? 'none' : `${row.match_day_ids.length} / ${row.unpaid_days.length} selected · auto-calc ${money(computedFromDays)}`}
            </span>
            {(row.unpaid_days || []).length > 0 && (
              <Button size="sm" variant="quiet" className="ml-auto" onClick={() => {
                const all = row.unpaid_days.map(d => d.id)
                const total = row.unpaid_days.reduce((s, d) => s + Number(row.match_day_rate) * Number(d.days_played), 0)
                onChange(idx, { match_day_ids: all, amount: total.toFixed(2) })
              }}>Select all</Button>
            )}
          </div>
          {(row.unpaid_days || []).length === 0 ? (
            <p className="text-[12.5px] text-pb-faintest">No unpaid match days for this member. The amount won't be linked to a specific day.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {row.unpaid_days.map(d => {
                const on = row.match_day_ids.includes(d.id)
                return (
                  <button key={d.id} onClick={() => toggleDay(d.id, d.days_played)}
                    className={`font-mono text-[10px] rounded-full px-2.5 py-1 border transition-colors ${on
                      ? ''
                      : 'border-pb-hairline2 text-pb-dim hover:text-pb-text'}`}
                    style={on
                      ? { borderColor: 'color-mix(in srgb, var(--pb-accent) 50%, transparent)', background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)', color: 'var(--pb-accent-ink)' }
                      : undefined}>
                    {d.played_at || '—'} · {d.days_played}d {d.match ? `· ${d.match}` : ''}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function AdminFeeBulkPayment() {
  const toast = useToast()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState(params.get('season') || '')
  const [members, setMembers] = useState([])
  const [tiers, setTiers] = useState([])
  const [busy, setBusy] = useState(false)

  // Header form: shared metadata for every payment in this batch.
  const [header, setHeader] = useState({
    paid_at: new Date().toISOString().slice(0, 10),
    method: 'EFT',
    bank_ref: '',
    expected_total: '',
  })
  const [rows, setRows] = useState([])

  useEffect(() => {
    api.adminListSeasons().then(s => {
      const sorted = sortSeasons(s)
      setSeasons(sorted)
      if (!seasonId && sorted[0]) setSeasonId(sorted[0].id)
    }).catch(e => toast.error(e.message))
  }, [])

  // Pull members + their tier (used for match_day_rate on each row).
  useEffect(() => {
    if (!seasonId) return
    Promise.all([
      api.feeListMembers(seasonId),
      api.feeListSchedule(seasonId),
    ]).then(([d, sched]) => {
      const tierById = Object.fromEntries(sched.map(s => [s.id, s]))
      setTiers(sched)
      setMembers((d.members || []).map(m => ({
        member_id: m.member_id, member_season_id: m.member_season_id, full_name: m.full_name,
        tier: m.tier, needs_tier: m.needs_tier,
        match_day_rate: tierById[m.fee_schedule_id]?.match_day_rate || 0,
      })))
    }).catch(e => { toast.error(e.message); setMembers([]) })
  }, [seasonId])

  // When a member is picked, fetch their unpaid match days lazily.
  const loadDays = useCallback(async (idx, memberId) => {
    try {
      const detail = await api.feeGetMember(memberId, seasonId)
      // Waived games are already settled (no money owed) — keep them off the
      // "needs paying" list alongside fully-paid games.
      const unpaid = (detail.match_days || []).filter(d => !d.is_paid && d.status !== 'waived')
      setRows(rs => rs.map((r, i) => i === idx ? { ...r, unpaid_days: unpaid } : r))
    } catch (e) { toast.error(e.message) }
  }, [seasonId])

  function patchRow(idx, patch) {
    setRows(rs => rs.map((r, i) => i === idx ? { ...r, ...patch } : r))
  }
  function addRow() {
    setRows(rs => [...rs, {
      member_season_id: '', member_id: '', full_name: '',
      kind: 'match_day', amount: '', match_day_ids: [], unpaid_days: [],
      match_day_rate: 0,
    }])
  }
  function removeRow(idx) {
    setRows(rs => rs.filter((_, i) => i !== idx))
  }

  const total = useMemo(() =>
    rows.reduce((sum, r) => sum + (Number(r.amount) || 0), 0)
  , [rows])
  const expected = Number(header.expected_total) || 0
  const delta = expected ? +(total - expected).toFixed(2) : 0
  const matchesExpected = !expected || Math.abs(delta) < 0.01
  const readyRows = rows.filter(r => r.member_season_id && Number(r.amount) > 0)
  const canCommit = readyRows.length > 0 && readyRows.length === rows.length && matchesExpected

  async function commit() {
    setBusy(true)
    try {
      const res = await api.feeBulkPayment({
        paid_at: header.paid_at || null,
        method: header.method || 'EFT',
        bank_ref: header.bank_ref.trim() || null,
        expected_total: expected || null,
        items: rows.map(r => ({
          member_season_id: r.member_season_id,
          amount: Number(r.amount),
          kind: r.kind,
          match_day_ids: r.kind === 'match_day' ? r.match_day_ids : [],
        })),
      })
      toast.success(`${res.created} payments logged, ${res.match_days_marked_paid} match days marked paid`)
      navigate('/admin/fees/payments')
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <BetterFeesLayout
      title="Bulk payment"
      caption="One deposit covering several players"
      actions={<Button as={Link} to="/admin/fees/payments">← Payments</Button>}
    >
      <div className="max-w-4xl">
        <p className="text-pb-dim text-[13px] mb-5 leading-relaxed">
          For when a captain collects cash from the team and transfers it as one lump sum. Each row becomes its own
          payment, so every player's balance updates, and any match days you tick get marked paid.
        </p>

        {members.length === 0 ? <PbSpinner message="Loading members…" /> : (
          <>
            {/* Shared payment metadata */}
            <div className="pb-card p-5 mb-5">
              <Caption screen className="mb-3">Deposit details</Caption>
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <Field label="Season">
                  <Select value={seasonId} onChange={e => setSeasonId(e.target.value)}>
                    {seasons.map(s => <option key={s.id} value={s.id}>{formatSeason(s)}</option>)}
                  </Select>
                </Field>
                <Field label="Date">
                  <input type="date" className={INPUT_CLS} value={header.paid_at}
                    onChange={e => setHeader(h => ({ ...h, paid_at: e.target.value }))} />
                </Field>
                <Field label="Method">
                  <Select value={header.method} onChange={e => setHeader(h => ({ ...h, method: e.target.value }))}>
                    {PAY_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
                  </Select>
                </Field>
                <Field label="Expected total">
                  <input type="number" min="0" step="0.01" placeholder="optional"
                    className={`${INPUT_CLS} text-right pb-num`}
                    value={header.expected_total} onChange={e => setHeader(h => ({ ...h, expected_total: e.target.value }))} />
                </Field>
              </div>
              <Field label="Bank ref (optional)" className="mt-3">
                <input className={INPUT_CLS} placeholder="e.g. TRF FROM J BARENDSE 19/10"
                  value={header.bank_ref} onChange={e => setHeader(h => ({ ...h, bank_ref: e.target.value }))} />
              </Field>
            </div>

            {/* Rows */}
            <div className="space-y-3 mb-5">
              {rows.map((r, idx) => (
                <BulkRow key={idx} row={r} idx={idx} members={members}
                  onChange={patchRow} onRemove={removeRow} onLoadDays={loadDays} />
              ))}
              <button onClick={addRow}
                className="w-full py-2.5 rounded-lg text-[13px] border border-dashed border-pb-hairline2 text-pb-dim hover:text-pb-text hover:border-pb-faint transition-colors">
                + Add player
              </button>
            </div>

            {/* Footer: totals + commit */}
            {rows.length > 0 && (
              <div className="pb-card p-5 sticky bottom-4">
                <div className="flex items-start gap-8 flex-wrap mb-3.5">
                  <StatReadout value={money(total)} label="ROW TOTAL" />
                  {expected > 0 && (
                    <>
                      <StatReadout value={money(expected)} label="EXPECTED" ink="var(--pb-dim)" />
                      <StatReadout
                        label="DELTA"
                        ink={matchesExpected ? 'var(--pb-positive-ink)' : '#f5b542'}
                        value={matchesExpected ? '✓ match' : (delta > 0 ? `+${money(delta)}` : `−${money(Math.abs(delta))}`)}
                      />
                    </>
                  )}
                </div>
                <Button variant="primary" size="lg" onClick={commit} disabled={!canCommit || busy} className="w-full">
                  {busy ? 'Committing…' : `Commit ${readyRows.length} payment${readyRows.length === 1 ? '' : 's'}`}
                </Button>
                {!canCommit && rows.length > 0 && (
                  <p className="text-[12px] text-pb-faintest mt-2">
                    {readyRows.length < rows.length
                      ? 'Each row needs a member and a positive amount.'
                      : 'The row total must match the expected deposit.'}
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </BetterFeesLayout>
  )
}
