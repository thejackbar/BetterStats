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
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${
      highlight ? 'bg-accent/10 border-accent/30 text-accent' : 'bg-navy-800 border-navy-700 text-slate-400'
    }`}>
      <span className="font-mono font-bold">{value}</span>
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

  const orgId = settings?.id

  const fetchLogs = useCallback(async (id) => {
    if (!id) return
    try {
      const data = await api.getSyncLogs(id)
      setLogs(data || [])
    } catch {
      // silent
    }
  }, [])

  const fetchSyncRequests = useCallback(async () => {
    try {
      const data = await api.adminListSyncRequests()
      setSyncRequests(data || [])
    } catch {
      // silent
    }
  }, [])

  useEffect(() => {
    api.adminGetSettings().then(s => {
      setSettings(s)
      if (s?.id) fetchLogs(s.id)
    }).catch(() => {})
    fetchSyncRequests()
  }, [fetchLogs, fetchSyncRequests])

  const [syncWarnings, setSyncWarnings] = useState({}) // id → warning message

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
    // 2 hours max — hard refresh on a club with hundreds of historical games can take a while
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

  const handleHardRefresh = async () => {
    if (!orgId || hardRefreshing || syncing) return
    const ok = window.confirm(
      'Hard refresh re-pulls every historical game for this club and tops up any missing player data. ' +
      'This may take an hour or longer for clubs with a lot of history. Continue?'
    )
    if (!ok) return
    setHardRefreshing(true)
    setLastTriggered(new Date().toISOString())
    try {
      const res = await api.adminHardRefreshOrg()
      if (res.status === 'already_running') {
        setHardRefreshing(false)
        alert('A hard refresh is already running for this club. Wait for it to complete.')
        return
      }
      setPolling(true)
    } catch (e) {
      setHardRefreshing(false)
      alert(`Failed to start hard refresh: ${e.message}`)
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <h1 className="text-2xl font-display font-bold text-white mb-6">Data Sync</h1>

        {/* Trigger card */}
        <div className="bg-navy-900 border border-navy-700 rounded-lg p-5 mb-8">
          <h2 className="text-white font-semibold mb-4">Full Sync</h2>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={handleSync}
              disabled={syncing || hardRefreshing || !orgId}
              className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {syncing ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Syncing…
                </>
              ) : 'Sync Now'}
            </button>
            <button
              onClick={handleHardRefresh}
              disabled={hardRefreshing || syncing || !orgId}
              className="btn-ghost border border-amber-500/40 text-amber-300 hover:bg-amber-500/10 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              title="Re-pulls every historical game and tops up any missing player data. Takes longer than a normal sync."
            >
              {hardRefreshing ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-amber-300/40 border-t-amber-300 rounded-full animate-spin" />
                  Hard refreshing…
                </>
              ) : 'Hard Refresh'}
            </button>
          </div>
          {(syncing || hardRefreshing) && (
            <p className="text-slate-500 text-xs mt-3">
              Running in background — this page will update automatically as progress comes in.
              A hard refresh on a club with hundreds of historical games can take an hour or longer.
            </p>
          )}
          {settings && (
            <div className="mt-4 pt-4 border-t border-navy-700">
              <p className="text-slate-500 text-xs">
                PlayHQ ID:{' '}
                {settings.playhq_id
                  ? <span className="font-mono text-accent">{settings.playhq_id}</span>
                  : <span className="text-amber-500">not set — game-level data (scorecards, partnerships) requires this</span>
                }
              </p>
            </div>
          )}
        </div>

        {/* Player Sync Requests */}
        {syncRequests.length > 0 && (
          <div className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold">Player Sync Requests</h2>
              <button
                onClick={fetchSyncRequests}
                className="text-slate-500 hover:text-white text-xs transition-colors"
              >
                Refresh
              </button>
            </div>
            <div className="space-y-2">
              {syncRequests.map(req => (
                <div
                  key={req.id}
                  className={`bg-navy-900 border rounded-lg p-4 flex flex-wrap items-center justify-between gap-3 ${
                    req.status === 'pending' ? 'border-amber-500/30' : 'border-navy-700'
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-white text-sm font-medium">{req.player_name}</p>
                      {!req.playhq_id && req.status === 'pending' && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400">
                          no PHQ ID
                        </span>
                      )}
                    </div>
                    <p className="text-slate-500 text-xs mt-0.5">
                      {req.created_at ? new Date(req.created_at).toLocaleString('en-AU', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
                      {req.requester_note && ` — "${req.requester_note}"`}
                    </p>
                    {req.playhq_id && (
                      <p className="text-slate-600 text-xs font-mono mt-0.5">{req.playhq_id}</p>
                    )}
                    {syncWarnings[req.id] && (
                      <div className="mt-2 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded p-2">
                        <p className="mb-2">{syncWarnings[req.id]}</p>
                        {syncWarnings[req.id].includes('no PlayHQ ID') && (
                          <button
                            onClick={() => handleSyncRequestAction(req.id, 'approve', 'admin override — no PHQ ID')}
                            disabled={actionLoading === req.id}
                            className="text-amber-400 underline text-xs disabled:opacity-50"
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
                        className="btn-primary text-xs disabled:opacity-50"
                      >
                        {actionLoading === req.id ? 'Processing…' : 'Approve & Deep Sync'}
                      </button>
                      <button
                        onClick={() => handleSyncRequestAction(req.id, 'dismiss')}
                        disabled={actionLoading === req.id}
                        className="btn-ghost text-xs text-slate-400 disabled:opacity-50"
                      >
                        Dismiss
                      </button>
                    </div>
                  ) : (
                    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium shrink-0 ${
                      req.status === 'approved'
                        ? 'bg-accent/10 border-accent/30 text-accent'
                        : 'bg-navy-800 border-navy-700 text-slate-500'
                    }`}>
                      {req.status}
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
            <h2 className="text-white font-semibold">Sync History</h2>
            <button
              onClick={() => orgId && fetchLogs(orgId)}
              className="text-slate-500 hover:text-white text-xs transition-colors"
            >
              Refresh
            </button>
          </div>

          {logs.length === 0 ? (
            <div className="bg-navy-900 border border-navy-700 rounded-lg p-6 text-center">
              <p className="text-slate-500 text-sm">No sync history yet.</p>
              <p className="text-slate-600 text-xs mt-1">
                Trigger a sync above to see results here.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {logs.map((entry, i) => {
                const s = entry.stats || {}
                const dur = fmtDuration(entry.started_at, entry.completed_at)
                const isRunning = entry.status === 'running'
                const isError = entry.status === 'error' || !!entry.error
                const isOK = entry.status === 'success' && !isError
                const isLatest = i === 0
                return (
                  <div
                    key={entry.id || i}
                    className={`bg-navy-900 border rounded-lg p-4 ${
                      isError ? 'border-red-500/40'
                        : isRunning ? 'border-amber-500/40'
                        : isLatest ? 'border-accent/30'
                        : 'border-navy-700'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-white text-sm font-medium">{fmtTime(entry.started_at)}</p>
                          {entry.kind && (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-navy-800 border border-navy-700 text-slate-400 font-mono">
                              {entry.kind}
                            </span>
                          )}
                        </div>
                        {dur && !isRunning && <p className="text-slate-600 text-xs mt-0.5">Completed in {dur}</p>}
                        {isRunning && <p className="text-amber-400 text-xs mt-0.5">Running…</p>}
                      </div>
                      <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${
                        isError
                          ? 'bg-red-500/10 border-red-500/30 text-red-400'
                          : isRunning
                          ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                          : 'bg-accent/10 border-accent/30 text-accent'
                      }`}>
                        {isError ? 'Error' : isRunning ? 'Running' : 'OK'}
                      </span>
                    </div>

                    {isError ? (
                      <p className="text-red-400 text-xs">{entry.error}</p>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {s.seasons != null && (
                          <StatPill label="seasons" value={s.seasons} />
                        )}
                        {s.players != null && (
                          <StatPill label="players" value={s.players} />
                        )}
                        {s.season_stats != null && (
                          <StatPill label="stat rows" value={s.season_stats} />
                        )}
                        {s.playhq_games_found != null && (
                          <StatPill label="phq games" value={s.playhq_games_found} highlight={s.playhq_games_found > 0} />
                        )}
                        {s.playhq_games_final != null && (
                          <StatPill label="phq final" value={s.playhq_games_final} highlight={s.playhq_games_final > 0} />
                        )}
                        {s.games_new != null && (
                          <StatPill label="new games" value={s.games_new} highlight={s.games_new > 0} />
                        )}
                        {s.games_topped_up != null && (
                          <StatPill label="topped up" value={s.games_topped_up} highlight={s.games_topped_up > 0} />
                        )}
                        {s.batting != null && (
                          <StatPill label="batting rows" value={s.batting} highlight={s.batting > 0} />
                        )}
                        {s.bowling != null && (
                          <StatPill label="bowling rows" value={s.bowling} highlight={s.bowling > 0} />
                        )}
                        {s.partnerships != null && (
                          <StatPill label="partnerships" value={s.partnerships} highlight={s.partnerships > 0} />
                        )}
                        {s.games_skipped_done != null && (
                          <StatPill label="already done" value={s.games_skipped_done} highlight={false} />
                        )}
                        {s.games_skipped_season != null && (
                          <StatPill label="no season match" value={s.games_skipped_season} highlight={s.games_skipped_season > 0} />
                        )}
                        {s.games_skipped_no_stats != null && (
                          <StatPill label="no stats" value={s.games_skipped_no_stats} highlight={s.games_skipped_no_stats > 0} />
                        )}
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
