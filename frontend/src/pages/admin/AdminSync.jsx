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

  useEffect(() => {
    api.adminGetSettings().then(s => {
      setSettings(s)
      if (s?.id) fetchLogs(s.id)
    }).catch(() => {})
  }, [fetchLogs])

  useEffect(() => {
    if (!polling || !orgId) return
    const interval = setInterval(() => fetchLogs(orgId), 4000)
    const timeout = setTimeout(() => {
      setPolling(false)
      setSyncing(false)
    }, 120_000)
    return () => { clearInterval(interval); clearTimeout(timeout) }
  }, [polling, orgId, fetchLogs])

  useEffect(() => {
    if (!polling || !lastTriggered || !logs.length) return
    if (new Date(logs[0].started_at) >= new Date(lastTriggered)) {
      setPolling(false)
      setSyncing(false)
    }
  }, [logs, polling, lastTriggered])

  const handleSync = async () => {
    if (!orgId || syncing) return
    setSyncing(true)
    setLastTriggered(new Date().toISOString())
    try {
      await api.triggerSync(orgId)
      setPolling(true)
    } catch (e) {
      setSyncing(false)
      alert(`Failed to start sync: ${e.message}`)
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <h1 className="text-2xl font-display font-bold text-white mb-6">Data Sync</h1>

        {/* Trigger card */}
        <div className="bg-navy-900 border border-navy-700 rounded-lg p-5 mb-8">
          <h2 className="text-white font-semibold mb-4">Full Sync</h2>
          <button
            onClick={handleSync}
            disabled={syncing || !orgId}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {syncing ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Syncing…
              </>
            ) : 'Sync Now'}
          </button>
          {syncing && (
            <p className="text-slate-500 text-xs mt-3">
              Running in background — this page will update automatically when complete.
            </p>
          )}
        </div>

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
                Sync history resets when the server restarts. Trigger a sync above to see results here.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {logs.map((entry, i) => {
                const s = entry.stats || {}
                const dur = fmtDuration(entry.started_at, entry.completed_at)
                const isError = !!entry.error
                const isNew = i === 0 && !isError
                return (
                  <div
                    key={i}
                    className={`bg-navy-900 border rounded-lg p-4 ${
                      isError ? 'border-red-500/40' : isNew ? 'border-accent/30' : 'border-navy-700'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div>
                        <p className="text-white text-sm font-medium">{fmtTime(entry.started_at)}</p>
                        {dur && <p className="text-slate-600 text-xs mt-0.5">Completed in {dur}</p>}
                      </div>
                      <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${
                        isError
                          ? 'bg-red-500/10 border-red-500/30 text-red-400'
                          : 'bg-accent/10 border-accent/30 text-accent'
                      }`}>
                        {isError ? 'Error' : 'OK'}
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
                        {s.games_new != null && (
                          <StatPill label="new games" value={s.games_new} highlight={s.games_new > 0} />
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
