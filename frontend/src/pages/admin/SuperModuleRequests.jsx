import { useState, useEffect, useMemo } from 'react'
import { api } from '../../lib/api'
import { MODULE_INFO } from '../../lib/modules'
import AdminLayout from '../../components/admin/AdminLayout'

const STATUSES = ['outstanding', 'completed', 'dismissed']
const MODULE_NAME = Object.fromEntries(MODULE_INFO.map(m => [m.key, m.name]))

const STATUS_STYLE = {
  outstanding: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  completed:   'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  dismissed:   'bg-pb-surface2 text-pb-faint border-pb-hairline',
}
const KIND_LABEL = { trial: 'Trial', subscribe: 'Subscribe', cancel: 'Cancel' }
const SOURCE_LABEL = { app: 'In-app', super_admin: 'Super admin', twenty: 'CRM (Twenty)' }

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

export default function SuperModuleRequests() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('outstanding')
  const [busy, setBusy] = useState('')
  // Per-request approval overrides (trial dates / renewal), keyed by request id.
  const [edits, setEdits] = useState({})

  const load = () => {
    setLoading(true)
    api.superListModuleRequests()
      .then((data) => { setRows(Array.isArray(data) ? data : []); setError('') })
      .catch((e) => setError(e.message || 'Could not load requests.'))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const counts = useMemo(() => {
    const c = { all: rows.length }
    for (const s of STATUSES) c[s] = rows.filter(r => r.status === s).length
    return c
  }, [rows])

  const visible = filter === 'all' ? rows : rows.filter(r => r.status === filter)

  const approve = async (r) => {
    setBusy(r.id)
    setError('')
    try {
      const e = edits[r.id] || {}
      const body = {}
      if (r.kind === 'trial') {
        if (e.days) body.days = Number(e.days)
        if (e.start) body.start = new Date(e.start).toISOString()
        if (e.end) body.end = new Date(e.end).toISOString()
      }
      if (r.kind === 'subscribe' && e.renewal_date) body.renewal_date = e.renewal_date
      await api.superApproveModuleRequest(r.id, body)
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const dismiss = async (r) => {
    setBusy(r.id)
    setError('')
    try {
      await api.superDismissModuleRequest(r.id)
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const setEdit = (id, patch) => setEdits(e => ({ ...e, [id]: { ...(e[id] || {}), ...patch } }))

  return (
    <AdminLayout>
      <div className="max-w-[1100px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Module requests</h1>
          <p className="text-sm text-pb-dim mt-1">
            Trial and subscription requests from clubs (and the CRM), newest first. Approving a
            trial starts it now for the club's default length; adjust the dates first if you need to.
          </p>
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          {['all', ...STATUSES].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase border transition ${
                filter === s ? 'border-pb-accent text-pb-text' : 'border-pb-hairline text-pb-faint hover:text-pb-text'
              }`}
            >
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
            <p className="text-sm text-pb-dim">
              {rows.length === 0 ? 'No module requests yet.' : 'No requests with this status.'}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {visible.map((r) => {
              const e = edits[r.id] || {}
              const isOutstanding = r.status === 'outstanding'
              return (
                <div key={r.id} className="pb-card p-4">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="font-medium text-pb-text">{r.club_name || '—'}</span>
                    <span className="text-pb-text text-sm">{MODULE_NAME[r.module_key] || r.module_key}</span>
                    <span className="font-mono text-[10px] uppercase tracking-wide2 px-1.5 py-0.5 rounded border pb-hairline text-pb-faint">
                      {KIND_LABEL[r.kind] || r.kind}
                    </span>
                    <span className={`font-mono text-[10px] uppercase px-2 py-0.5 rounded-full border ${STATUS_STYLE[r.status] || ''}`}>
                      {r.status}
                    </span>
                    <span className="ml-auto font-mono text-[10px] text-pb-faint">
                      {SOURCE_LABEL[r.source] || r.source} · {fmtDate(r.requested_at)}
                      {r.requested_by ? ` · ${r.requested_by}` : ''}
                    </span>
                  </div>
                  {r.note && <p className="text-xs text-pb-faint mt-1.5">{r.note}</p>}

                  {isOutstanding && (
                    <div className="flex flex-wrap items-end gap-2 mt-3">
                      {r.kind === 'trial' && (
                        <>
                          <label className="text-[10px] text-pb-faint">
                            <span className="block mb-1">Days (optional)</span>
                            <input type="number" min="1" value={e.days || ''} placeholder="default"
                              onChange={ev => setEdit(r.id, { days: ev.target.value })}
                              className="w-24 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-xs focus:outline-none focus:border-pb-accent" />
                          </label>
                          <label className="text-[10px] text-pb-faint">
                            <span className="block mb-1">Start</span>
                            <input type="date" value={e.start || ''}
                              onChange={ev => setEdit(r.id, { start: ev.target.value })}
                              className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-xs focus:outline-none focus:border-pb-accent" />
                          </label>
                          <label className="text-[10px] text-pb-faint">
                            <span className="block mb-1">End</span>
                            <input type="date" value={e.end || ''}
                              onChange={ev => setEdit(r.id, { end: ev.target.value })}
                              className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-xs focus:outline-none focus:border-pb-accent" />
                          </label>
                        </>
                      )}
                      {r.kind === 'subscribe' && (
                        <label className="text-[10px] text-pb-faint">
                          <span className="block mb-1">Renewal date</span>
                          <input type="date" value={e.renewal_date || ''}
                            onChange={ev => setEdit(r.id, { renewal_date: ev.target.value })}
                            className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-xs focus:outline-none focus:border-pb-accent" />
                        </label>
                      )}
                      <button onClick={() => approve(r)} disabled={busy === r.id}
                        className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
                        style={{ background: 'var(--pb-accent)' }}>
                        {busy === r.id ? '…' : 'APPROVE'}
                      </button>
                      <button onClick={() => dismiss(r)} disabled={busy === r.id}
                        className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition disabled:opacity-50">
                        Dismiss
                      </button>
                    </div>
                  )}
                  {!isOutstanding && (r.completed_at || r.completed_by) && (
                    <p className="text-[10px] text-pb-faintest mt-1.5">
                      {r.status} {fmtDate(r.completed_at)}{r.completed_by ? ` by ${r.completed_by}` : ''}
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
