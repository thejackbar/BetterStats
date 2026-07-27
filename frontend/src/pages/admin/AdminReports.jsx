import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'

function fmtDate(iso) {
  if (!iso) return null
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function QueryPreview({ q }) {
  if (!q || typeof q !== 'object') return null
  const parts = []
  if (q.derived) parts.push(`Derived: ${q.derived}`)
  if (q.target) parts.push(`Target: ${q.target}`)
  if (q.sortBy) parts.push(`Sort: ${q.sortBy} ${q.sortDir || ''}`.trim())
  if (q.limit) parts.push(`Top ${q.limit}`)
  if (q.filterTree && (q.filterTree.clauses || []).length) {
    parts.push(`${q.filterTree.clauses.length} filter${q.filterTree.clauses.length === 1 ? '' : 's'}`)
  }
  const ctxCount = Object.keys(q.context || {}).filter(k => q.context[k] !== '' && q.context[k] != null && q.context[k] !== false).length
  if (ctxCount) parts.push(`${ctxCount} context filter${ctxCount === 1 ? '' : 's'}`)
  return (
    <div className="font-mono text-[10.5px] text-pb-faint tracking-wide2">
      {parts.join(' · ') || '—'}
    </div>
  )
}

export default function AdminReports() {
  const { user, hasCapability } = useAuth()
  const [clubSlug, setClubSlug] = useState(null)
  const [pending, setPending] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [acting, setActing] = useState({}) // { [id]: 'approve' | 'reject' }
  const [notes, setNotes] = useState({}) // { [id]: 'note text' }

  const canManage = hasCapability(CAP.MANAGE_REPORTS)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const data = await api.statlabListPendingReports()
      setPending(data)
    } catch (e) {
      setError(e.message)
      setPending([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { if (canManage) load() }, [canManage, load])

  useEffect(() => {
    if (!canManage) return
    api.adminGetSettings().then(s => setClubSlug(s.slug)).catch(() => {})
  }, [canManage])

  const act = async (report, action) => {
    setActing(s => ({ ...s, [report.id]: action }))
    try {
      await api.statlabReviewReport(report.id, { action, note: notes[report.id]?.trim() || null })
      setPending(p => p.filter(r => r.id !== report.id))
    } catch (e) {
      setError(e.message)
    } finally {
      setActing(s => { const { [report.id]: _, ...rest } = s; return rest })
    }
  }

  if (!canManage) {
    return (
      <BetterStatsLayout>
        <h1 className="text-2xl font-bold mb-2">Saved Reports</h1>
        <p className="text-pb-faint">You don't have permission to manage saved reports.</p>
      </BetterStatsLayout>
    )
  }

  return (
    <BetterStatsLayout>
      <div className="max-w-4xl">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Saved Reports</h1>
            <p className="text-pb-faint text-sm mt-1">
              Approve or reject club-visibility reports saved from StatLab. Approved reports appear in
              the Saved Reports panel on the club's StatLab page.
            </p>
          </div>
          <button
            onClick={load}
            className="font-mono text-[10.5px] tracking-wide2 text-pb-faint hover:text-pb-text px-3 py-1.5 rounded border pb-hairline hover:border-pb-hairline2 transition"
          >
            Refresh
          </button>
        </div>

        {error && (
          <div className="bg-pb-red/10 border border-pb-red/30 text-pb-red text-sm rounded p-3 mb-4">
            {error}
          </div>
        )}

        <div className="pb-card">
          <div className="flex items-center justify-between px-4 py-3 pb-hairline-b">
            <div className="font-mono text-[10.5px] tracking-wide3 text-pb-dim">
              PENDING APPROVAL · {pending.length}
            </div>
          </div>

          {loading ? (
            <p className="text-pb-faintest font-mono text-[10.5px] px-4 py-6">Loading…</p>
          ) : pending.length === 0 ? (
            <p className="text-pb-faintest font-mono text-[10.5px] px-4 py-6">
              No reports awaiting approval.
            </p>
          ) : (
            <ul>
              {pending.map(r => (
                <li key={r.id} className="px-4 py-4 pb-hairline-b last:border-0">
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="min-w-0 flex-1">
                      <div className="text-pb-text font-semibold text-[15px]">{r.title}</div>
                      {r.description && (
                        <p className="text-pb-dim text-sm mt-1">{r.description}</p>
                      )}
                      <div className="font-mono text-[10.5px] text-pb-faintest tracking-wide2 mt-1.5">
                        By {r.owner_name || 'unknown'} · {fmtDate(r.created_at)}
                      </div>
                    </div>
                    {clubSlug && (
                      <Link
                        to={`/${clubSlug}/statlab?${new URLSearchParams({ preview_report: r.id }).toString()}`}
                        className="font-mono text-[10.5px] tracking-wide2 text-pb-faint hover:text-pb-text px-2 py-1 rounded border pb-hairline hover:border-pb-hairline2 transition shrink-0"
                      >
                        Open in StatLab
                      </Link>
                    )}
                  </div>

                  <div className="bg-pb-surface2/50 rounded p-2 mb-3">
                    <QueryPreview q={r.query_json} />
                  </div>

                  <div className="flex items-end gap-2">
                    <input
                      type="text"
                      placeholder="Optional note for the author"
                      value={notes[r.id] || ''}
                      onChange={e => setNotes(n => ({ ...n, [r.id]: e.target.value }))}
                      maxLength={500}
                      className="flex-1 bg-pb-surface border pb-hairline2 text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
                    />
                    <button
                      onClick={() => act(r, 'reject')}
                      disabled={!!acting[r.id]}
                      className="font-mono text-[10.5px] tracking-wide2 text-pb-faint hover:text-pb-red px-3 py-1.5 rounded border pb-hairline hover:border-pb-red/40 transition disabled:opacity-50"
                    >
                      {acting[r.id] === 'reject' ? 'Rejecting…' : 'Reject'}
                    </button>
                    <button
                      onClick={() => act(r, 'approve')}
                      disabled={!!acting[r.id]}
                      className="font-mono text-[10.5px] tracking-wide2 text-pb-text bg-pb-accent/20 hover:bg-pb-accent/30 px-3 py-1.5 rounded border border-pb-accent/40 transition disabled:opacity-50"
                    >
                      {acting[r.id] === 'approve' ? 'Approving…' : 'Approve'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </BetterStatsLayout>
  )
}
