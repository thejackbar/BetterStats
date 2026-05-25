import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

function fmtDuration(startedAt, completedAt) {
  if (!startedAt || !completedAt) return null
  const ms = new Date(completedAt) - new Date(startedAt)
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function fmtTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function StatPill({ label, value, highlight }) {
  return (
    <span className={`inline-flex items-center gap-1 font-mono text-[10px] px-2 py-0.5 rounded border ${
      highlight
        ? 'border-pb-accent/30 text-pb-accent bg-pb-accent/10'
        : 'border-pb-hairline text-pb-faint bg-pb-surface2'
    }`}>
      <span className="font-bold">{value}</span>
      <span>{label}</span>
    </span>
  )
}

export default function AdminSync() {
  const [settings, setSettings] = useState(null)
  const [logs, setLogs] = useState([])
  const [syncing, setSyncing] = useState(false)
  const [lastTriggered, setLastTriggered] = useState(null)
  const [polling, setPolling] = useState(false)
  const [syncRequests, setSyncRequests] = useState([])
  const [actionLoading, setActionLoading] = useState(null)
  const [hardRefreshing, setHardRefreshing] = useState(false)
  const [backfilling, setBackfilling] = useState(false)
  const [syncWarnings, setSyncWarnings] = useState({})

  const orgId = settings?.id

  const fetchLogs = useCallback(async (id) => {
    if (!id) return
    try {
      const data = await api.getSyncLogs(id)
      setLogs(data || [])
    } catch { /* silent */ }
  }, [])

  const fetchSyncRequests = useCallback(async () => {
    try {
      const data = await api.adminListSyncRequests()
      setSyncRequests(data || [])
    } catch { /* silent */ }
  }, [])

  useEffect(() => {
    api.adminGetSettings().then(s => {
      setSettings(s)
      if (s?.id) fetchLogs(s.id)
    }).catch(() => {})
    fetchSyncRequests()
  }, [fetchLogs, fetchSyncRequests])

  const handleSyncRequestAction = async (id, action, forceNote) => {
    setActionLoading(id)
    setSyncWarnings(w => ({ ...w, [id]: null }))
    try {
      const res = await api.adminActionSyncRequest(id, action, forceNote || null)
      if (res.status === 'needs_confirmation') {
        setSyncWarnings(w => ({ ...w, [id]: res.message }))
      } else if (res.status === 'already_running') {
        setSyncWarnings(w => ({ ...w, [id]: 'A sync is already running for this player.' }))
      } else {
        await fetchSyncRequests()
      }
    } catch (e) {
      setSyncWarnings(w => ({ ...w, [id]: e.message }))
    } finally {
      setActionLoading(null)
    }
  }

  useEffect(() => {
    if (!polling || !orgId) return
    const interval = setInterval(() => fetchLogs(orgId), 4000)
    const timeout = setTimeout(() => {
      setPolling(false)
      setSyncing(false)
      setHardRefreshing(false)
    }, 2 * 60 * 60 * 1000)
    return () => { clearInterval(interval); clearTimeout(timeout) }
  }, [polling, orgId, fetchLogs])

  useEffect(() => {
    if (!polling || !lastTriggered || !logs.length) return
    const latest = logs[0]
    if (latest.status !== 'running' && new Date(latest.started_at) >= new Date(lastTriggered)) {
      setPolling(false)
      setSyncing(false)
      setHardRefreshing(false)
    }
  }, [logs, polling, lastTriggered])

  const handleSync = async () => {
    if (!orgId || syncing) return
    setSyncing(true)
    setLastTriggered(new Date().toISOString())
    try {
      const res = await api.triggerSync(orgId)
      if (res.status === 'already_running') {
        setSyncing(false)
        alert('A sync is already running for this club. Wait for it to complete.')
        return
      }
      setPolling(true)
    } catch (e) {
      setSyncing(false)
      alert(`Failed to start sync: ${e.message}`)
    }
  }

  const handleBackfillAggregates = async () => {
    if (!orgId || backfilling || syncing || hardRefreshing) return
    setBackfilling(true)
    try {
      const res = await api.adminBackfillAggregates()
      alert(`Backfill complete — inserted ${res.inserted ?? 0} aggregate rows.`)
    } catch (e) {
      alert(`Backfill failed: ${e.message}`)
    } finally {
      setBackfilling(false)
    }
  }

  const handleHardRefresh = async () => {
    if (!orgId || hardRefreshing || syncing || backfilling) return
    const ok = window.confirm(
      'Full Rebuild wipes every stored game for this club and re-pulls all history from Cricket Australia. ' +
      'This may take an hour or longer for clubs with a lot of history. Continue?'
    )
    if (!ok) return
    setHardRefreshing(true)
    setLastTriggered(new Date().toISOString())
    try {
      const res = await api.adminHardRefreshOrg()
      if (res.status === 'already_running') {
        setHardRefreshing(false)
        alert('A full rebuild is already running for this club. Wait for it to complete.')
        return
      }
      setPolling(true)
    } catch (e) {
      setHardRefreshing(false)
      alert(`Failed to start full rebuild: ${e.message}`)
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-6">Data Sync</h1>

        {/* Trigger card */}
        <div className="pb-card p-5 mb-8">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">Sync Actions</p>

          {/* Update with latest data */}
          <div className="flex items-start gap-4 py-3">
            <button
              onClick={handleSync}
              disabled={syncing || hardRefreshing || backfilling || !orgId}
              className="w-44 shrink-0 px-4 py-2 rounded font-mono text-[11px] tracking-wide2 font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {syncing ? (
                <>
                  <span className="w-3 h-3 border-2 border-pb-bg/30 border-t-pb-bg rounded-full animate-spin" />
                  SYNCING…
                </>
              ) : 'SYNC NOW'}
            </button>
            <div className="flex-1">
              <p className="text-pb-text text-sm font-medium mb-0.5">Pull latest games &amp; stats</p>
              <p className="text-pb-faint text-xs leading-relaxed">
                Adds new games and updates existing players from Cricket Australia. Safe to run anytime —
                this is the normal weekly sync.
              </p>
            </div>
          </div>

          {/* Fix missing totals */}
          <div className="flex items-start gap-4 py-3 pb-hairline-t">
            <button
              onClick={handleBackfillAggregates}
              disabled={backfilling || syncing || hardRefreshing || !orgId}
              className="w-44 shrink-0 px-4 py-2 rounded font-mono text-[11px] tracking-wide2 font-semibold border transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-pb-text"
              style={{ borderColor: 'var(--pb-hairline)', background: 'transparent' }}
            >
              {backfilling ? (
                <>
                  <span className="w-3 h-3 border-2 border-pb-text/30 border-t-pb-text rounded-full animate-spin" />
                  FIXING…
                </>
              ) : 'FIX MISSING TOTALS'}
            </button>
            <div className="flex-1">
              <p className="text-pb-text text-sm font-medium mb-0.5">Repair players showing 0 matches</p>
              <p className="text-pb-faint text-xs leading-relaxed">
                Recomputes career totals from scorecards already in BetterStats. Use when a player&apos;s
                headline reads 0 despite having visible innings. No data pulled from Cricket Australia —
                runs in seconds.
              </p>
            </div>
          </div>

          {/* Full rebuild */}
          <div className="flex items-start gap-4 py-3 pb-hairline-t">
            <button
              onClick={handleHardRefresh}
              disabled={hardRefreshing || syncing || backfilling || !orgId}
              className="w-44 shrink-0 px-4 py-2 rounded font-mono text-[11px] tracking-wide2 font-semibold border transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-pb-amber"
              style={{ borderColor: 'var(--pb-amber)', background: 'transparent' }}
            >
              {hardRefreshing ? (
                <>
                  <span className="w-3 h-3 border-2 border-pb-amber/30 border-t-pb-amber rounded-full animate-spin" />
                  REBUILDING…
                </>
              ) : 'FULL REBUILD'}
            </button>
            <div className="flex-1">
              <p className="text-pb-text text-sm font-medium mb-0.5">Wipe and re-pull everything</p>
              <p className="text-pb-faint text-xs leading-relaxed">
                Deletes every stored game and re-pulls all history from Cricket Australia. Use after a
                sync-logic change or if data looks broadly wrong. Slow — an hour or more for a club with
                a lot of history.
              </p>
            </div>
          </div>

          {(syncing || hardRefreshing) && (
            <p className="font-mono text-[10px] text-pb-faint mt-3 pt-3 pb-hairline-t">
              Running in background — this page will update automatically.
              A full rebuild can take an hour or longer.
            </p>
          )}
          {settings && (
            <div className="mt-4 pt-4 pb-hairline-t">
              <p className="font-mono text-[10px] text-pb-faint">
                PlayHQ ID:{' '}
                {settings.playhq_id
                  ? <span style={{ color: 'var(--pb-accent)' }}>{settings.playhq_id}</span>
                  : <span style={{ color: 'var(--pb-amber)' }}>not set — game-level data requires this</span>
                }
              </p>
            </div>
          )}
        </div>

        {/* Player Sync Requests */}
        {syncRequests.length > 0 && (
          <div className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Player Sync Requests</p>
              <div className="flex items-center gap-4">
                {syncRequests.some(r => r.status !== 'pending') && (
                  <button
                    onClick={async () => {
                      if (!window.confirm('Clear all resolved (approved/dismissed) player sync requests? Pending ones are preserved.')) return
                      try {
                        await api.adminClearResolvedSyncRequests()
                        await fetchSyncRequests()
                      } catch (e) {
                        alert(`Failed to clear: ${e.message}`)
                      }
                    }}
                    className="font-mono text-[10px] text-pb-faint hover:text-pb-red transition-colors"
                  >
                    Clear resolved
                  </button>
                )}
                <button onClick={fetchSyncRequests} className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors">
                  Refresh
                </button>
              </div>
            </div>
            <div className="space-y-2">
              {syncRequests.map(req => (
                <div
                  key={req.id}
                  className={`pb-card p-4 flex flex-wrap items-center justify-between gap-3 ${
                    req.status === 'pending' ? 'border-pb-amber/30' : ''
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-pb-text text-sm font-medium">{req.player_name}</p>
                      {!req.playhq_id && req.status === 'pending' && (
                        <span className="font-mono text-[10px] px-1.5 py-0.5 rounded border border-pb-amber/30 text-pb-amber">
                          no PHQ ID
                        </span>
                      )}
                    </div>
                    <p className="font-mono text-[10px] text-pb-faint mt-0.5">
                      {req.created_at ? new Date(req.created_at).toLocaleString('en-AU', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
                      {req.requester_note && ` — "${req.requester_note}"`}
                    </p>
                    {req.playhq_id && (
                      <p className="font-mono text-[10px] text-pb-faintest mt-0.5">{req.playhq_id}</p>
                    )}
                    {syncWarnings[req.id] && (
                      <div className="mt-2 font-mono text-[10px] text-pb-amber bg-pb-amber/10 border border-pb-amber/20 rounded p-2">
                        <p className="mb-2">{syncWarnings[req.id]}</p>
                        {syncWarnings[req.id].includes('no PlayHQ ID') && (
                          <button
                            onClick={() => handleSyncRequestAction(req.id, 'approve', 'admin override — no PHQ ID')}
                            disabled={actionLoading === req.id}
                            className="underline text-pb-amber disabled:opacity-50"
                          >
                            Proceed anyway (name matching only)
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  {req.status === 'pending' ? (
                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => handleSyncRequestAction(req.id, 'approve')}
                        disabled={actionLoading === req.id}
                        className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
                        style={{ background: 'var(--pb-accent)' }}
                      >
                        {actionLoading === req.id ? 'Processing…' : 'Approve & Deep Sync'}
                      </button>
                      <button
                        onClick={() => handleSyncRequestAction(req.id, 'dismiss')}
                        disabled={actionLoading === req.id}
                        className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text transition disabled:opacity-50"
                      >
                        Dismiss
                      </button>
                    </div>
                  ) : (
                    <span className={`font-mono text-[10px] px-2 py-0.5 rounded border shrink-0 ${
                      req.status === 'approved'
                        ? 'border-pb-accent/30 text-pb-accent'
                        : 'border-pb-hairline text-pb-faint'
                    }`}>
                      {req.status.toUpperCase()}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Log */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Sync History</p>
            <div className="flex items-center gap-4">
              {logs.some(l => l.status !== 'running') && (
                <button
                  onClick={async () => {
                    if (!window.confirm('Clear sync history? Any currently-running sync is preserved.')) return
                    try {
                      await api.adminClearSyncRuns()
                      if (orgId) await fetchLogs(orgId)
                    } catch (e) {
                      alert(`Failed to clear: ${e.message}`)
                    }
                  }}
                  className="font-mono text-[10px] text-pb-faint hover:text-pb-red transition-colors"
                >
                  Clear history
                </button>
              )}
              <button onClick={() => orgId && fetchLogs(orgId)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors">
                Refresh
              </button>
            </div>
          </div>

          {logs.length === 0 ? (
            <div className="pb-card p-8 text-center">
              <p className="text-pb-faint text-sm">No sync history yet.</p>
              <p className="font-mono text-[10px] text-pb-faintest mt-1">Trigger a sync above to see results here.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {logs.map((entry, i) => {
                const s = entry.stats || {}
                const dur = fmtDuration(entry.started_at, entry.completed_at)
                const isRunning = entry.status === 'running'
                const isError = entry.status === 'error' || !!entry.error
                const isLatest = i === 0
                return (
                  <div
                    key={entry.id || i}
                    className={`pb-card p-4 ${
                      isError ? 'border-pb-red/40'
                        : isRunning ? 'border-pb-amber/40'
                        : isLatest ? 'border-pb-accent/30'
                        : ''
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-pb-text text-sm font-medium">{fmtTime(entry.started_at)}</p>
                          {entry.kind && (
                            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded border pb-hairline text-pb-faint">
                              {entry.kind}
                            </span>
                          )}
                        </div>
                        {dur && !isRunning && <p className="font-mono text-[10px] text-pb-faintest mt-0.5">Completed in {dur}</p>}
                        {isRunning && <p className="font-mono text-[10px] text-pb-amber mt-0.5">Running…</p>}
                      </div>
                      <span className={`font-mono text-[10px] px-2 py-0.5 rounded border shrink-0 ${
                        isError
                          ? 'border-pb-red/30 text-pb-red'
                          : isRunning
                          ? 'border-pb-amber/30 text-pb-amber'
                          : 'border-pb-accent/30 text-pb-accent'
                      }`}>
                        {isError ? 'ERROR' : isRunning ? 'RUNNING' : 'OK'}
                      </span>
                    </div>

                    {isError ? (
                      <p className="font-mono text-[10px] text-pb-red">{entry.error}</p>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {s.seasons != null && <StatPill label="seasons" value={s.seasons} />}
                        {s.player_seasons != null && <StatPill label="player seasons" value={s.player_seasons} />}
                        {s.season_stats != null && <StatPill label="stat rows" value={s.season_stats} />}
                        {s.playhq_games_found != null && <StatPill label="phq games" value={s.playhq_games_found} highlight={s.playhq_games_found > 0} />}
                        {s.playhq_games_final != null && <StatPill label="phq final" value={s.playhq_games_final} highlight={s.playhq_games_final > 0} />}
                        {s.games_new != null && <StatPill label="new games" value={s.games_new} highlight={s.games_new > 0} />}
                        {s.games_topped_up != null && <StatPill label="topped up" value={s.games_topped_up} highlight={s.games_topped_up > 0} />}
                        {s.batting != null && <StatPill label="batting rows" value={s.batting} highlight={s.batting > 0} />}
                        {s.bowling != null && <StatPill label="bowling rows" value={s.bowling} highlight={s.bowling > 0} />}
                        {s.partnerships != null && <StatPill label="partnerships" value={s.partnerships} highlight={s.partnerships > 0} />}
                        {s.games_skipped_done != null && <StatPill label="already done" value={s.games_skipped_done} />}
                        {s.games_skipped_season != null && <StatPill label="no season match" value={s.games_skipped_season} highlight={s.games_skipped_season > 0} />}
                        {s.games_skipped_no_stats != null && <StatPill label="no stats" value={s.games_skipped_no_stats} highlight={s.games_skipped_no_stats > 0} />}
                        {s.gr_matches_seen != null && <StatPill label="GR matches" value={s.gr_matches_seen} highlight={s.gr_matches_seen > 0} />}
                        {s.gr_games_new != null && <StatPill label="GR new games" value={s.gr_games_new} highlight={s.gr_games_new > 0} />}
                        {s.gr_batting != null && <StatPill label="GR batting" value={s.gr_batting} highlight={s.gr_batting > 0} />}
                        {s.gr_bowling != null && <StatPill label="GR bowling" value={s.gr_bowling} highlight={s.gr_bowling > 0} />}
                        {s.gr_fielding != null && <StatPill label="GR fielding" value={s.gr_fielding} highlight={s.gr_fielding > 0} />}
                        {s.gr_partnerships != null && <StatPill label="GR partnerships" value={s.gr_partnerships} highlight={s.gr_partnerships > 0} />}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </AdminLayout>
  )
}
