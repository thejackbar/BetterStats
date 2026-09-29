import { useEffect, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'
import LoadingSpinner from '../../../components/LoadingSpinner'

// Every football admin router writes to audit_logs (merges, imports, user and
// season changes); this is the screen that reads it back, the counterpart of
// cricket's Activity Log. Read-only by design: the undo for each action lives
// on the screen that did it.
const fmtWhen = iso => iso ? new Date(iso).toLocaleString('en-AU', {
  day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit',
}) : ''

const humanAction = a => (a || '').replace(/[._]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

function detailLine(details) {
  if (!details || typeof details !== 'object') return ''
  return Object.entries(details)
    .filter(([, v]) => v != null && v !== '' && typeof v !== 'object')
    .slice(0, 4)
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
    .join(' · ')
}

export default function AflAdminActivity() {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    aflApi.adminActivityLog(300).then(setRows).catch(e => { setError(e.message); setRows([]) })
  }, [])

  if (rows === null) return <LoadingSpinner />
  const needle = q.trim().toLowerCase()
  const shown = needle
    ? rows.filter(r => [r.action, r.user_name, r.user_email, detailLine(r.details)].join(' ').toLowerCase().includes(needle))
    : rows

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Activity Log</h1>
        <p className="text-sm text-pb-dim mt-1">Who changed what in this club's admin, newest first.</p>
      </div>
      {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search actions or people"
        className="w-full sm:w-80 bg-pb-surface2 border border-pb-hairline rounded px-3 py-2 text-sm" />
      <div className="pb-card p-4">
        <SectionTitle right={<span className="font-mono text-[10px] text-pb-faint">{shown.length} shown</span>}>Recent actions</SectionTitle>
        {shown.length === 0 ? (
          <p className="text-sm text-pb-faint">{rows.length ? 'Nothing matches that search.' : 'No admin actions recorded yet.'}</p>
        ) : (
          <ul className="divide-y divide-[var(--pb-hairline)]">
            {shown.map(r => (
              <li key={r.id} className="py-2.5 flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4" data-testid="activity-row">
                <span className="font-mono text-[11px] text-pb-faint sm:w-44 shrink-0">{fmtWhen(r.created_at)}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm"><span className="font-semibold">{humanAction(r.action)}</span>
                    {r.user_name && <span className="text-pb-dim"> by {r.user_name}</span>}</div>
                  {detailLine(r.details) && <div className="text-xs text-pb-faint break-words">{detailLine(r.details)}</div>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
