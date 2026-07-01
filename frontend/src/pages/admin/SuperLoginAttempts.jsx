import { useState, useEffect, useMemo } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// Machine reason code → friendly label. Mirrors login_audit.REASON_* codes.
const REASON_LABEL = {
  unknown_user:   'No such account',
  bad_password:   'Wrong password',
  locked:         'Account locked',
  no_membership:  'No club membership',
  club_inactive:  'Club inactive',
}

function fmtTime(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

// A rough one-word device read from the user-agent, so the table stays scannable.
function deviceOf(ua) {
  if (!ua) return '-'
  const s = ua.toLowerCase()
  if (s.includes('iphone') || s.includes('ipad') || s.includes('ios')) return 'iOS'
  if (s.includes('android')) return 'Android'
  if (s.includes('windows')) return 'Windows'
  if (s.includes('mac os') || s.includes('macintosh')) return 'Mac'
  if (s.includes('linux')) return 'Linux'
  return 'Other'
}

const INPUT_CLS = 'bg-pb-surface2 border pb-hairline rounded px-3 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

export default function SuperLoginAttempts() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [onlyFailures, setOnlyFailures] = useState(false)
  const [search, setSearch] = useState('')

  const load = (opts) => {
    setLoading(true)
    api.superListLoginAttempts({ limit: 500, onlyFailures, q: search.trim() || undefined, ...opts })
      .then((data) => { setRows(data); setError('') })
      .catch((e) => setError(e.message || 'Could not load login attempts.'))
      .finally(() => setLoading(false))
  }
  // Reload from the server when the failures toggle flips (it's a WHERE clause).
  useEffect(() => { load() }, [onlyFailures])  // eslint-disable-line react-hooks/exhaustive-deps

  const counts = useMemo(() => ({
    total: rows.length,
    failures: rows.filter(r => !r.success).length,
    success: rows.filter(r => r.success).length,
  }), [rows])

  const submitSearch = (e) => { e.preventDefault(); load() }

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Login attempts</h1>
          <p className="text-sm text-pb-dim mt-1">
            Every sign-in attempt, newest first: the username or email tried, whether it
            worked, and where it came from.
          </p>
          <p className="text-xs text-pb-faint mt-2 max-w-2xl">
            The IP is stored as a one-way hash, never the raw address, and the password is
            never recorded. Repeated failures from one hash against different usernames is
            the pattern to watch for.
          </p>
        </div>

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <button
            onClick={() => setOnlyFailures(v => !v)}
            className={`px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase border transition ${
              onlyFailures ? 'border-pb-accent text-pb-text' : 'border-pb-hairline text-pb-faint hover:text-pb-text'
            }`}
          >
            {onlyFailures ? 'Failures only' : 'All attempts'}
          </button>
          <form onSubmit={submitSearch} className="flex items-center gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search username / email…"
              className={INPUT_CLS}
            />
            <button type="submit" className="px-3 py-1.5 rounded border border-pb-hairline text-pb-faint hover:text-pb-text text-sm">
              Search
            </button>
          </form>
          <div className="text-xs text-pb-faint ml-auto">
            {counts.total} shown · <span className="text-emerald-300">{counts.success} ok</span> · <span className="text-red-400">{counts.failures} failed</span>
          </div>
        </div>

        {error && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>
        )}

        {loading ? (
          <p className="text-sm text-pb-dim">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="pb-card p-8 text-center">
            <p className="text-sm text-pb-dim">
              {onlyFailures || search
                ? 'No login attempts match this filter.'
                : 'No login attempts recorded yet. They start showing up here from the next sign-in.'}
            </p>
          </div>
        ) : (
          <div className="pb-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                  <th className="px-3 py-2.5">Time</th>
                  <th className="px-3 py-2.5">Username / email</th>
                  <th className="px-3 py-2.5">Outcome</th>
                  <th className="px-3 py-2.5">Account</th>
                  <th className="px-3 py-2.5">Club</th>
                  <th className="px-3 py-2.5">Where</th>
                  <th className="px-3 py-2.5">IP hash</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b pb-hairline align-top hover:bg-pb-surface2/40">
                    <td className="px-3 py-2.5 whitespace-nowrap text-pb-dim">{fmtTime(r.created_at)}</td>
                    <td className="px-3 py-2.5 font-medium text-pb-text break-all">{r.username || '-'}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {r.success ? (
                        <span className="inline-block px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase bg-emerald-500/15 text-emerald-300 border-emerald-500/40">
                          success
                        </span>
                      ) : (
                        <span className="inline-block px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase bg-red-500/15 text-red-300 border-red-500/40"
                          title={r.failure_reason || ''}>
                          {REASON_LABEL[r.failure_reason] || r.failure_reason || 'failed'}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-pb-dim">
                      {r.user_id
                        ? (r.user_display_name || <span className="text-pb-faint">linked account</span>)
                        : <span className="text-pb-faint">—</span>}
                    </td>
                    <td className="px-3 py-2.5 text-pb-dim">{r.org_name || <span className="text-pb-faint">—</span>}</td>
                    <td className="px-3 py-2.5 text-pb-dim whitespace-nowrap">
                      {r.country || '??'} · {deviceOf(r.user_agent)}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-xs text-pb-faint">{r.ip_hash || '-'}</td>
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
