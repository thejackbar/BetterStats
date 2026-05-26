import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { CHANGELOG } from '../data/changelog'

const KIND_LABELS = {
  org_full: 'Sync Now',
  org_hard_refresh: 'Full Rebuild',
  backfill_aggregates: 'Fix Missing Totals',
  player_deep: 'Player Deep Sync',
}

const MILESTONE_STAT_LABELS = {
  runs: 'career runs',
  wickets: 'career wickets',
  matches: 'career matches',
  catches: 'career catches',
}

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

function getNewEntries(lastSeenVersion) {
  return CHANGELOG.filter(e => compareVersions(e.version, lastSeenVersion) > 0)
}

function relativeTime(isoString) {
  if (!isoString) return ''
  const diffMs = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diffMs / 60_000)
  const hours = Math.floor(mins / 60)
  const days = Math.floor(hours / 24)
  if (mins < 2) return 'just now'
  if (mins < 60) return `${mins}m ago`
  if (hours < 24) return `${hours}h ago`
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days} days ago`
  return new Date(isoString).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
}

function SectionHead({ title, color }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
      <span className="font-mono text-[10px] tracking-wide3 text-pb-faintest uppercase">{title}</span>
    </div>
  )
}

function SyncRunRow({ run }) {
  const ok = run.status === 'success'
  const label = KIND_LABELS[run.kind] || run.kind
  const newGames = run.stats?.gr_games_new ?? null
  const color = ok ? 'var(--pb-positive)' : 'var(--pb-negative)'

  return (
    <div className="flex items-start gap-3 px-3 py-2.5 rounded-lg border pb-hairline">
      <span className="mt-1 w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-pb-text">{label}</span>
          <span className="font-mono text-[9px] px-1 py-0.5 rounded border" style={{ color, borderColor: color }}>
            {ok ? 'OK' : 'ERROR'}
          </span>
        </div>
        <p className="text-xs text-pb-faint mt-0.5">
          {ok && newGames != null && <span>{newGames} new game{newGames !== 1 ? 's' : ''} · </span>}
          {!ok && run.error && <span style={{ color: 'var(--pb-negative)' }}>{run.error.slice(0, 80)}{run.error.length > 80 ? '…' : ''} · </span>}
          {relativeTime(run.completed_at)}
        </p>
      </div>
    </div>
  )
}

function MilestoneAchievedRow({ milestone }) {
  const label = MILESTONE_STAT_LABELS[milestone.milestone_type] || milestone.milestone_type
  return (
    <div className="flex items-start gap-3 px-3 py-2.5 rounded-lg border pb-hairline">
      <svg className="mt-0.5 shrink-0" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--pb-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="8" r="6" /><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11" />
      </svg>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-pb-text">
          {milestone.player_name} — {(milestone.milestone_value || 0).toLocaleString()} {label}
        </p>
        {milestone.achieved_at && (
          <p className="text-xs text-pb-faint mt-0.5">
            {new Date(milestone.achieved_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
          </p>
        )}
      </div>
    </div>
  )
}

function UpcomingMilestoneRow({ milestone }) {
  const label = MILESTONE_STAT_LABELS[milestone.type] || milestone.type
  const pct = Math.round(((milestone.target - milestone.needed) / milestone.target) * 100)
  return (
    <div className="flex items-start gap-3 px-3 py-2.5 rounded-lg border pb-hairline">
      <svg className="mt-0.5 shrink-0" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--pb-dim)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
      </svg>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-pb-text">
          {milestone.name} — {milestone.needed} {label} from {(milestone.target || 0).toLocaleString()}
        </p>
        <div className="mt-1.5 h-1 w-full rounded-full overflow-hidden" style={{ background: 'var(--pb-surface2)' }}>
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--pb-accent)' }} />
        </div>
      </div>
    </div>
  )
}

export default function NotificationModal({ isOpen, summary, error, onClose }) {
  useEffect(() => {
    if (!isOpen) return
    const handler = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const loading = !summary && !error
  const newEntries = getNewEntries(summary?.last_seen_version)
  const syncRuns = summary?.sync_runs || []
  const newMilestones = summary?.new_milestones || []
  const upcoming = (summary?.upcoming_milestones || []).slice(0, 5)
  const pendingCount = summary?.pending_sync_requests || 0
  const failedSyncs = syncRuns.filter(r => r.status === 'error')

  const hasSinceLastVisit = syncRuns.length > 0 || newMilestones.length > 0
  const hasAnything = newEntries.length > 0 || hasSinceLastVisit || upcoming.length > 0 || pendingCount > 0

  return (
    <div className="fixed inset-0 z-[60] flex" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />

      {/* Panel anchored top-right, below the header */}
      <div
        className="absolute top-14 right-4 w-[420px] max-h-[calc(100vh-5rem)] flex flex-col rounded-xl shadow-2xl border pb-hairline overflow-hidden"
        style={{ background: 'var(--pb-surface)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b pb-hairline-b shrink-0">
          <span className="font-mono text-[11px] tracking-wide3 text-pb-faintest uppercase">Notifications</span>
          <button
            onClick={onClose}
            className="p-1 rounded text-pb-faint hover:text-pb-text hover:bg-pb-surface2 transition"
            aria-label="Close notifications"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

          {loading && (
            <p className="text-sm text-pb-faint text-center py-6">Loading…</p>
          )}

          {error && (
            <div
              className="px-3 py-2.5 rounded-lg border text-sm"
              style={{ borderColor: 'var(--pb-negative)', color: 'var(--pb-negative)', background: 'color-mix(in srgb, var(--pb-negative) 8%, transparent)' }}
            >
              Couldn't load notifications: {error}
            </div>
          )}

          {/* Sync Failures — top callout when scheduled syncs have errored */}
          {failedSyncs.length > 0 && (
            <section>
              <SectionHead title="Sync Failures" color="var(--pb-negative)" />
              <Link
                to="/admin/sync"
                onClick={onClose}
                className="block px-3 py-2.5 rounded-lg border hover:bg-pb-surface2 transition"
                style={{ borderColor: 'var(--pb-negative)', background: 'color-mix(in srgb, var(--pb-negative) 8%, transparent)' }}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: 'var(--pb-negative)' }} />
                  <span className="text-sm font-medium text-pb-text">
                    {failedSyncs.length} sync {failedSyncs.length === 1 ? 'run' : 'runs'} failed since your last visit
                  </span>
                </div>
                {failedSyncs[0].error && (
                  <p className="text-xs text-pb-dim pl-4 truncate">
                    Latest: {failedSyncs[0].error.slice(0, 100)}{failedSyncs[0].error.length > 100 ? '…' : ''}
                  </p>
                )}
                <p className="text-[10px] text-pb-faintest pl-4 mt-1 font-mono uppercase tracking-wide3">
                  Open admin → sync to retry
                </p>
              </Link>
            </section>
          )}

          {/* Needs Attention */}
          {pendingCount > 0 && (
            <section>
              <SectionHead title="Needs Attention" color="#f59e0b" />
              <Link
                to="/admin/sync"
                onClick={onClose}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg border pb-hairline hover:bg-pb-surface2 transition"
              >
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: '#f59e0b' }} />
                <span className="text-sm text-pb-text flex-1">
                  {pendingCount} player sync {pendingCount === 1 ? 'request' : 'requests'} awaiting approval
                </span>
                <svg className="text-pb-faintest" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </Link>
            </section>
          )}

          {/* What's New */}
          {newEntries.length > 0 && (
            <section>
              <SectionHead title="What's New" color="var(--pb-accent)" />
              <div className="space-y-4">
                {newEntries.map(entry => (
                  <div key={entry.version}>
                    <div className="flex items-center gap-2 mb-1.5">
                      <span
                        className="font-mono text-[10px] px-1.5 py-0.5 rounded font-bold"
                        style={{ background: 'var(--pb-accent)', color: '#000' }}
                      >
                        {entry.version}
                      </span>
                      <span className="text-sm font-medium text-pb-text">{entry.title}</span>
                      <span className="text-xs text-pb-faintest ml-auto">{entry.date}</span>
                    </div>
                    <ul className="space-y-1 pl-1">
                      {entry.items.map((item, i) => (
                        <li key={i} className="flex gap-2 text-xs text-pb-dim">
                          <span className="text-pb-faintest mt-0.5 shrink-0">·</span>
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Since Your Last Visit */}
          {hasSinceLastVisit && (
            <section>
              <SectionHead title="Since Your Last Visit" color="var(--pb-positive)" />
              <div className="space-y-1.5">
                {syncRuns.map(run => <SyncRunRow key={run.id} run={run} />)}
                {newMilestones.map((m, i) => <MilestoneAchievedRow key={i} milestone={m} />)}
              </div>
            </section>
          )}

          {/* Coming Up */}
          {upcoming.length > 0 && (
            <section>
              <SectionHead title="Coming Up" color="var(--pb-dim)" />
              <div className="space-y-1.5">
                {upcoming.map((m, i) => <UpcomingMilestoneRow key={i} milestone={m} />)}
              </div>
            </section>
          )}

          {!loading && !error && !hasAnything && (
            <p className="text-sm text-pb-faint text-center py-6">
              Nothing new since your last visit.
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 px-5 py-3 border-t pb-hairline-t flex items-center gap-2">
          <Link
            to="/admin/changelog"
            onClick={onClose}
            className="flex-1 text-center font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-2 hover:bg-pb-surface2 transition"
          >
            ALL UPDATES
          </Link>
          <button
            onClick={onClose}
            className="flex-1 font-mono text-[11px] tracking-wide2 text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-2 hover:bg-pb-surface2 transition"
          >
            DISMISS
          </button>
        </div>
      </div>
    </div>
  )
}
