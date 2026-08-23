import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const STATUSES = ['pending', 'actioned', 'dismissed']

const STATUS_STYLE = {
  pending:   'bg-amber-500/15 text-amber-300 border-amber-500/40',
  actioned:  'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  dismissed: 'bg-pb-surface2 text-pb-faint border-pb-hairline',
}

const SELECT_CLS = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-xs focus:outline-none focus:border-pb-accent'

function fmtDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

/**
 * The sales-conversion lead list behind a lapsed-trial club's password-gated
 * public page — see routers/clubs.py POST /clubs/{slug}/request-unpause. A
 * visitor hit "This trial has ended" and left their email; Super Admin
 * actions the row and opens a conversation with them directly.
 */
export default function SuperUnpauseRequests() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('pending')

  const load = () => {
    setLoading(true)
    api.superListUnpauseRequests()
      .then((data) => { setRows(data); setError('') })
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

  const setStatus = async (id, status) => {
    setRows(rs => rs.map(r => (r.id === id ? { ...r, status } : r)))  // optimistic
    try {
      await api.superActionUnpauseRequest(id, status)
    } catch {
      load()  // reload to undo the optimistic change if the save failed
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-[1000px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Unpause requests</h1>
          <p className="text-sm text-pb-dim mt-1">
            Visitors who hit a lapsed-trial club's password-protected page and asked for
            access, newest first. Reply to their email to open a sales conversation.
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
              {rows.length === 0
                ? "No unpause requests yet. They'll show up here when a visitor asks for access on a locked page."
                : 'No requests with this status.'}
            </p>
          </div>
        ) : (
          <div className="pb-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                  <th className="px-3 py-2.5">Date</th>
                  <th className="px-3 py-2.5">Club</th>
                  <th className="px-3 py-2.5">Requester</th>
                  <th className="px-3 py-2.5">Message</th>
                  <th className="px-3 py-2.5">Status</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => (
                  <tr key={r.id} className="border-b pb-hairline align-top hover:bg-pb-surface2/40">
                    <td className="px-3 py-2.5 whitespace-nowrap text-pb-dim">{fmtDate(r.created_at)}</td>
                    <td className="px-3 py-2.5 font-medium text-pb-text">
                      <Link to="/admin/super/clubs" className="hover:underline">{r.club_name}</Link>
                      <div className="font-normal text-pb-faint text-xs">{r.club_slug}</div>
                    </td>
                    <td className="px-3 py-2.5">
                      <a href={`mailto:${r.email}`} className="text-accent hover:underline block">{r.email}</a>
                    </td>
                    <td className="px-3 py-2.5 text-pb-dim max-w-[300px]">
                      {r.message ? <span title={r.message} className="line-clamp-3">{r.message}</span> : <span className="text-pb-faint">-</span>}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`inline-block mb-1.5 px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase ${STATUS_STYLE[r.status] || ''}`}>
                        {r.status}
                      </span>
                      <select
                        value={r.status}
                        onChange={(e) => setStatus(r.id, e.target.value)}
                        className={`${SELECT_CLS} block`}
                        aria-label={`Status for ${r.club_name}`}
                      >
                        {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
