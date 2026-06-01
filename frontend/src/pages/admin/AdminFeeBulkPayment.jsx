import { useState, useEffect, useMemo, useCallback } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterFeesLayout from '../../components/admin/BetterFeesLayout'
import { PbSpinner } from '../../lib/presskit'

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

  const cell = 'bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

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
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">MEMBER</label>
          {row.member_season_id ? (
            <div className="flex items-center gap-2">
              <span className="text-pb-text text-sm flex-1">{row.full_name}</span>
              <button onClick={() => onChange(idx, { member_season_id: '', member_id: '', full_name: '', match_day_ids: [], unpaid_days: [] })}
                className="font-mono text-[9px] text-pb-faint hover:text-pb-text">CHANGE</button>
            </div>
          ) : (
            <div>
              <input className={`${cell} w-full`} placeholder="Search members…"
                value={memberSearch} onChange={e => setMemberSearch(e.target.value)} />
              {memberSearch.trim() && (
                <div className="mt-1 max-h-48 overflow-y-auto border pb-hairline rounded bg-pb-surface">
                  {filtered.length === 0 && <div className="px-3 py-2 font-mono text-[10px] text-pb-faintest">No match</div>}
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
                      className="block w-full text-left px-3 py-1.5 text-sm text-pb-text hover:bg-pb-surface2 transition-colors">
                      {m.full_name}
                      {m.needs_tier && <span className="ml-2 font-mono text-[9px] text-pb-amber">⚠ needs tier</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">KIND</label>
          <select className={`${cell} w-32`} value={row.kind}
            onChange={e => onChange(idx, { kind: e.target.value, match_day_ids: [] })}>
            <option value="match_day">Match Day</option>
            <option value="membership">Membership</option>
          </select>
        </div>
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">AMOUNT</label>
          <input type="number" min="0" step="0.01" className={`${cell} w-24 text-right tabular-nums`}
            value={row.amount} onChange={e => onChange(idx, { amount: e.target.value })} />
        </div>
        <button onClick={() => onRemove(idx)}
          className="font-mono text-[9px] text-pb-red/60 hover:text-pb-red transition-colors px-2 py-2">REMOVE</button>
      </div>

      {isMatchDay && row.member_season_id && (
        <div className="mt-3 pt-3 border-t pb-hairline-t">
          <div className="flex items-center gap-2 mb-2">
            <span className="font-mono text-[10px] tracking-wide3 text-pb-faint">UNPAID MATCH DAYS</span>
            <span className="font-mono text-[9px] text-pb-faintest">
              {(row.unpaid_days || []).length === 0 ? 'none' : `${row.match_day_ids.length} / ${row.unpaid_days.length} selected · auto-calc ${money(computedFromDays)}`}
            </span>
            {(row.unpaid_days || []).length > 0 && (
              <button onClick={() => {
                const all = row.unpaid_days.map(d => d.id)
                const total = row.unpaid_days.reduce((s, d) => s + Number(row.match_day_rate) * Number(d.days_played), 0)
                onChange(idx, { match_day_ids: all, amount: total.toFixed(2) })
              }} className="ml-auto font-mono text-[9px] text-pb-faint hover:text-pb-text">SELECT ALL</button>
            )}
          </div>
          {(row.unpaid_days || []).length === 0 ? (
            <p className="font-mono text-[10px] text-pb-faintest">No unpaid match days for this member. Amount won't be linked to a specific day.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {row.unpaid_days.map(d => {
                const on = row.match_day_ids.includes(d.id)
                return (
                  <button key={d.id} onClick={() => toggleDay(d.id, d.days_played)}
                    className={`font-mono text-[10px] rounded px-2 py-1 border transition-colors ${on
                      ? 'border-pb-accent text-pb-bg'
                      : 'pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent/50'}`}
                    style={on ? { background: 'var(--pb-accent)' } : {}}>
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
      const unpaid = (detail.match_days || []).filter(d => !d.is_paid)
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

  const inp = 'bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

  return (
    <BetterFeesLayout>
      <div className="max-w-4xl">
        <Link to="/admin/fees/payments" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">← PAYMENTS</Link>
        <h1 className="font-display font-bold text-2xl text-pb-text mt-2 mb-1">Bulk payment</h1>
        <p className="text-pb-faint text-sm mb-5 leading-relaxed">
          One deposit covering multiple players — for when a captain collects cash from the team and transfers it as one lump sum.
          Each row becomes its own payment (so each player's balance updates), and any match days you tick get marked Paid.
        </p>

        {members.length === 0 ? <PbSpinner message="Loading members…" /> : (
          <>
            {/* Shared payment metadata */}
            <div className="pb-card p-5 mb-5">
              <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Deposit Details</p>
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <div>
                  <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">SEASON</label>
                  <select className={`${inp} w-full`} value={seasonId} onChange={e => setSeasonId(e.target.value)}>
                    {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">DATE</label>
                  <input type="date" className={`${inp} w-full`} value={header.paid_at}
                    onChange={e => setHeader(h => ({ ...h, paid_at: e.target.value }))} />
                </div>
                <div>
                  <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">METHOD</label>
                  <select className={`${inp} w-full`} value={header.method}
                    onChange={e => setHeader(h => ({ ...h, method: e.target.value }))}>
                    {PAY_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div>
                  <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">EXPECTED TOTAL</label>
                  <input type="number" min="0" step="0.01" placeholder="optional"
                    className={`${inp} w-full text-right tabular-nums`}
                    value={header.expected_total} onChange={e => setHeader(h => ({ ...h, expected_total: e.target.value }))} />
                </div>
              </div>
              <div className="mt-3">
                <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">BANK REF (optional)</label>
                <input className={`${inp} w-full`} placeholder="e.g. TRF FROM J BARENDSE 19/10"
                  value={header.bank_ref} onChange={e => setHeader(h => ({ ...h, bank_ref: e.target.value }))} />
              </div>
            </div>

            {/* Rows */}
            <div className="space-y-3 mb-5">
              {rows.map((r, idx) => (
                <BulkRow key={idx} row={r} idx={idx} members={members}
                  onChange={patchRow} onRemove={removeRow} onLoadDays={loadDays} />
              ))}
              <button onClick={addRow}
                className="w-full py-2.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline border-dashed text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors">
                + ADD PLAYER
              </button>
            </div>

            {/* Footer: totals + commit */}
            {rows.length > 0 && (
              <div className="pb-card p-5 sticky bottom-4">
                <div className="grid grid-cols-3 gap-4 mb-3">
                  <div>
                    <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">ROW TOTAL</div>
                    <div className="font-display font-bold text-xl text-pb-text tabular-nums">{money(total)}</div>
                  </div>
                  {expected > 0 && (
                    <>
                      <div>
                        <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">EXPECTED</div>
                        <div className="font-display font-bold text-xl text-pb-dim tabular-nums">{money(expected)}</div>
                      </div>
                      <div>
                        <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">DELTA</div>
                        <div className={`font-display font-bold text-xl tabular-nums ${matchesExpected ? 'text-green-300' : 'text-pb-amber'}`}>
                          {matchesExpected ? '✓ match' : (delta > 0 ? `+${money(delta)}` : `−${money(Math.abs(delta))}`)}
                        </div>
                      </div>
                    </>
                  )}
                </div>
                <button onClick={commit} disabled={!canCommit || busy}
                  className="w-full py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-40" style={{ background: 'var(--pb-accent)' }}>
                  {busy ? 'COMMITTING…' : `COMMIT ${readyRows.length} PAYMENT${readyRows.length === 1 ? '' : 'S'}`}
                </button>
                {!canCommit && rows.length > 0 && (
                  <p className="font-mono text-[10px] text-pb-faintest mt-2">
                    {readyRows.length < rows.length
                      ? 'Each row needs a member and a positive amount.'
                      : 'Row total must match the expected deposit.'}
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
