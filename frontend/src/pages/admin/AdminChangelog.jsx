import { useEffect, useState } from 'react'
import AdminLayout from '../../components/admin/AdminLayout'
import { CHANGELOG } from '../../data/changelog'
import { api } from '../../lib/api'
import { SITE_VERSION } from '../../version'
import { useAuth } from '../../contexts/AuthContext'

function compareVersions(a, b) {
  const parse = v => (v || '').replace('v', '').split('.').map(Number)
  const av = parse(a)
  const bv = parse(b)
  for (let i = 0; i < Math.max(av.length, bv.length); i++) {
    const diff = (av[i] || 0) - (bv[i] || 0)
    if (diff !== 0) return diff
  }
  return 0
}

export default function AdminChangelog() {
  const { user } = useAuth()
  const isStaff = user?.role === 'super_admin'
  const [lastSeen, setLastSeen] = useState(null)
  // null while loading, then the daily updates posted so far.
  const [updates, setUpdates] = useState(null)

  useEffect(() => {
    api.getProductUpdates()
      .then(d => setUpdates(d?.items || []))
      .catch(() => setUpdates([]))
  }, [])

  useEffect(() => {
    api.getNotificationsCount()
      .then(d => setLastSeen(d?.last_seen_version || null))
      .catch(() => {})
  }, [])

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <div className="flex items-baseline justify-between mb-2">
          <h1 className="font-display font-bold text-2xl text-pb-text">What's New</h1>
          <span className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase">
            Current: {SITE_VERSION}
          </span>
        </div>
        <p className="text-pb-faint text-sm mb-6 leading-relaxed">
          A short note on what has changed in BetterCricket, posted on days something is new.
          The same note arrives in your notifications.
        </p>

        <div className="space-y-4 mb-10" data-testid="daily-updates">
          {updates === null && <p className="text-sm text-pb-faint">Loading…</p>}
          {updates && updates.length === 0 && (
            <div className="pb-card p-5 text-sm text-pb-faint">
              Nothing has been posted yet. New notes appear here each morning something has changed.
            </div>
          )}
          {(updates || []).map(u => (
            <div key={u.id} className="pb-card p-5" data-testid="daily-update">
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <span className="text-sm font-medium text-pb-text">{u.headline}</span>
                <span className="font-mono text-[10px] text-pb-faintest ml-auto">{u.date}</span>
              </div>
              <ul className="space-y-1.5 pl-1">
                {u.bullets.map((b, i) => (
                  <li key={i} className="flex gap-2 text-sm text-pb-dim">
                    <span className="text-pb-faintest mt-0.5 shrink-0">·</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* The raw release notes are written for the team. Staff only. */}
        {isStaff && (
          <>
            <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase mb-3">
              Release history (staff only)
            </h2>
        <div className="space-y-5">
          {CHANGELOG.map(entry => {
            const isNew = compareVersions(entry.version, lastSeen) > 0
            return (
              <div key={entry.version} className="pb-card p-5">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span
                    className="font-mono text-[10px] px-1.5 py-0.5 rounded font-bold"
                    style={{ background: 'var(--pb-accent)', color: '#000' }}
                  >
                    {entry.version}
                  </span>
                  <span className="text-sm font-medium text-pb-text">{entry.title}</span>
                  {isNew && (
                    <span
                      className="font-mono text-[9px] tracking-wide3 uppercase px-1.5 py-0.5 rounded border"
                      style={{ color: 'var(--pb-accent)', borderColor: 'var(--pb-accent)' }}
                    >
                      New
                    </span>
                  )}
                  <span className="font-mono text-[10px] text-pb-faintest ml-auto">{entry.date}</span>
                </div>
                <ul className="space-y-1.5 pl-1">
                  {entry.items.map((item, i) => (
                    <li key={i} className="flex gap-2 text-sm text-pb-dim">
                      <span className="text-pb-faintest mt-0.5 shrink-0">·</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
          </>
        )}
      </div>
    </AdminLayout>
  )
}
