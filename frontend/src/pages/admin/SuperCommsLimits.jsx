import { useState, useEffect, useMemo } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const STATUSES = ['pending', 'approved', 'denied']
const STATUS_STYLE = {
  pending:  'bg-amber-500/15 text-amber-300 border-amber-500/40',
  approved: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  denied:   'bg-pb-surface2 text-pb-faint border-pb-hairline',
}
const TIER_STYLE = {
  sandbox:    'text-amber-300 border-amber-500/40',
  production: 'text-emerald-300 border-emerald-500/40',
  suspended:  'text-red-300 border-red-500/40',
}

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}
const pct = (v) => `${((v || 0) * 100).toFixed(v >= 0.01 ? 1 : 2)}%`

export default function SuperCommsLimits() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('pending')
  const [busy, setBusy] = useState('')
  const [edits, setEdits] = useState({})   // per-request { daily_limit, note }
  // Account send rate (AWS ceiling + our pacing rate).
  const [rates, setRates] = useState(null)
  const [rateForm, setRateForm] = useState({ aws_max_send_rate: '', send_rate: '' })
  const [rateMsg, setRateMsg] = useState(null)
  const [rateBusy, setRateBusy] = useState(false)

  const load = () => {
    setLoading(true)
    api.superListCommsRequests('all')
      .then((data) => { setRows(Array.isArray(data) ? data : []); setError('') })
      .catch((e) => setError(e.message || 'Could not load requests.'))
      .finally(() => setLoading(false))
  }
  const loadRates = () => {
    api.superGetCommsRates()
      .then((d) => { setRates(d); setRateForm({ aws_max_send_rate: d.aws_max_send_rate, send_rate: d.send_rate }) })
      .catch(() => setRates(null))
  }
  useEffect(() => { load(); loadRates() }, [])

  const saveRates = async () => {
    setRateBusy(true); setRateMsg(null)
    try {
      const d = await api.superUpdateCommsRates({
        aws_max_send_rate: Number(rateForm.aws_max_send_rate),
        send_rate: Number(rateForm.send_rate),
      })
      setRates(d)
      setRateMsg({ kind: 'ok', text: 'Send rate updated.' })
    } catch (e) { setRateMsg({ kind: 'error', text: e.message }) }
    finally { setRateBusy(false) }
  }

  const counts = useMemo(() => {
    const c = { all: rows.length }
    for (const s of STATUSES) c[s] = rows.filter(r => r.status === s).length
    return c
  }, [rows])

  const visible = filter === 'all' ? rows : rows.filter(r => r.status === filter)
  const setEdit = (id, patch) => setEdits(e => ({ ...e, [id]: { ...(e[id] || {}), ...patch } }))

  const approve = async (r) => {
    setBusy(r.id); setError('')
    try {
      const e = edits[r.id] || {}
      const body = {}
      if (e.daily_limit) body.daily_limit = Number(e.daily_limit)
      if (e.note) body.note = e.note
      await api.superApproveCommsRequest(r.id, body)
      load()
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }
  const deny = async (r) => {
    setBusy(r.id); setError('')
    try {
      const e = edits[r.id] || {}
      await api.superDenyCommsRequest(r.id, e.note ? { note: e.note } : {})
      load()
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  return (
    <AdminLayout>
      <div className="max-w-[1100px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">BetterComms sending limits</h1>
          <p className="text-sm text-pb-dim mt-1">
            Clubs asking to move from the sandbox to production sending, newest first. Each row shows
            the club's live bounce and spam rates so you can judge the ask. Approving moves the club to
            production. A club whose rates cross the danger line is auto-suspended by the circuit breaker;
            reinstate it from All Clubs once resolved.
          </p>
        </div>

        {/* Account send rate — AWS ceiling + our pacing rate */}
        {rates && (() => {
          const aws = Number(rateForm.aws_max_send_rate)
          const send = Number(rateForm.send_rate)
          const invalid = !(send > 0) || !(aws > 0) || send >= aws
          return (
            <div className="pb-card p-4 mb-5">
              <div className="text-sm text-pb-text font-medium mb-1">Account send rate</div>
              <p className="text-xs text-pb-dim mb-3 leading-relaxed">
                AWS grants this account a maximum send rate per second, shared across every club. We pace all
                sending just below it. Update the AWS limit here when AWS changes your account's rate. Our
                send rate must always stay below the AWS limit.
              </p>
              <div className="flex flex-wrap items-end gap-3">
                <label className="text-[10px] text-pb-faint">
                  <span className="block mb-1">AWS limit (msgs/sec)</span>
                  <input type="number" min="1" value={rateForm.aws_max_send_rate}
                    onChange={e => setRateForm(f => ({ ...f, aws_max_send_rate: e.target.value }))}
                    className="w-32 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-sm focus:outline-none focus:border-pb-accent" />
                </label>
                <label className="text-[10px] text-pb-faint">
                  <span className="block mb-1">Our send rate (msgs/sec)</span>
                  <input type="number" min="1" value={rateForm.send_rate}
                    onChange={e => setRateForm(f => ({ ...f, send_rate: e.target.value }))}
                    className="w-32 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-sm focus:outline-none focus:border-pb-accent" />
                </label>
                <button onClick={saveRates} disabled={rateBusy || invalid}
                  className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-40 text-pb-bg"
                  style={{ background: 'var(--pb-accent)' }}>
                  {rateBusy ? '…' : 'SAVE RATE'}
                </button>
              </div>
              {invalid && (
                <p className="text-[11px] text-amber-400 mt-2">Our send rate must be a positive number below the AWS limit.</p>
              )}
              {rateMsg && (
                <p className={`text-[11px] mt-2 ${rateMsg.kind === 'error' ? 'text-red-400' : 'text-emerald-400'}`}>{rateMsg.text}</p>
              )}
            </div>
          )
        })()}

        <div className="flex flex-wrap gap-2 mb-4">
          {['all', ...STATUSES].map((s) => (
            <button key={s} onClick={() => setFilter(s)}
              className={`px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase border transition ${
                filter === s ? 'border-pb-accent text-pb-text' : 'border-pb-hairline text-pb-faint hover:text-pb-text'
              }`}>
              {s} ({counts[s] ?? 0})
            </button>
          ))}
        </div>

        {error && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>
        )}

        {loading ? (
          <p className="text-sm text-pb-dim">Loading…</p>
        ) : visible.length === 0 ? (
          <div className="pb-card p-8 text-center">
            <p className="text-sm text-pb-dim">{rows.length === 0 ? 'No tier requests yet.' : 'No requests with this status.'}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {visible.map((r) => {
              const e = edits[r.id] || {}
              const m = r.metrics || {}
              const isPending = r.status === 'pending'
              return (
                <div key={r.id} className="pb-card p-4">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="font-medium text-pb-text">{r.club_name || '—'}</span>
                    <span className={`font-mono text-[10px] uppercase tracking-wide2 px-1.5 py-0.5 rounded border ${TIER_STYLE[r.current_tier] || 'pb-hairline text-pb-faint'}`}>
                      {r.current_tier}
                    </span>
                    <span className="text-pb-faint text-xs">→ {r.requested_tier}{r.requested_cap ? ` (${r.requested_cap}/day)` : ''}</span>
                    <span className={`font-mono text-[10px] uppercase px-2 py-0.5 rounded-full border ${STATUS_STYLE[r.status] || ''}`}>
                      {r.status}
                    </span>
                    <span className="ml-auto font-mono text-[10px] text-pb-faint">{fmtDate(r.requested_at)}</span>
                  </div>

                  {/* Live deliverability for the decision */}
                  <div className="flex flex-wrap gap-x-5 gap-y-1 mt-2 text-xs">
                    <span className="text-pb-faint">Sent ({m.window_days || 30}d): <span className="text-pb-text">{m.sent ?? 0}</span></span>
                    <span className="text-pb-faint">Bounce: <span className={m.bounce_rate >= 0.05 ? 'text-red-300' : 'text-pb-text'}>{m.sufficient_sample ? pct(m.bounce_rate) : '—'}</span></span>
                    <span className="text-pb-faint">Spam: <span className={m.complaint_rate >= 0.001 ? 'text-red-300' : 'text-pb-text'}>{m.sufficient_sample ? pct(m.complaint_rate) : '—'}</span></span>
                    {!m.sufficient_sample && <span className="text-pb-faintest">(under {m.min_sample} sends — rates not yet meaningful)</span>}
                  </div>
                  {r.breaker_reason && <p className="text-xs text-red-300 mt-1">⚠ {r.breaker_reason}</p>}
                  {r.reason && <p className="text-xs text-pb-faint mt-1.5">“{r.reason}”</p>}

                  {isPending && (
                    <div className="flex flex-wrap items-end gap-2 mt-3">
                      <label className="text-[10px] text-pb-faint">
                        <span className="block mb-1">Daily cap (optional override)</span>
                        <input type="number" min="0" value={e.daily_limit || ''} placeholder="tier default"
                          onChange={ev => setEdit(r.id, { daily_limit: ev.target.value })}
                          className="w-32 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-xs focus:outline-none focus:border-pb-accent" />
                      </label>
                      <label className="text-[10px] text-pb-faint flex-1 min-w-[180px]">
                        <span className="block mb-1">Note (optional)</span>
                        <input type="text" value={e.note || ''}
                          onChange={ev => setEdit(r.id, { note: ev.target.value })}
                          className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-xs focus:outline-none focus:border-pb-accent" />
                      </label>
                      <button onClick={() => approve(r)} disabled={busy === r.id}
                        className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
                        style={{ background: 'var(--pb-accent)' }}>
                        {busy === r.id ? '…' : 'APPROVE'}
                      </button>
                      <button onClick={() => deny(r)} disabled={busy === r.id}
                        className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition disabled:opacity-50">
                        Deny
                      </button>
                    </div>
                  )}
                  {!isPending && r.decided_at && (
                    <p className="text-[10px] text-pb-faintest mt-1.5">
                      {r.status} {fmtDate(r.decided_at)}{r.decision_note ? ` · ${r.decision_note}` : ''}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
