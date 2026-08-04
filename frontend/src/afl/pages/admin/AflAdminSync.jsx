import { useCallback, useEffect, useRef, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

/** Data Sync — pull the latest games and stats from PlayHQ + run history.
 * Club branding/registration moved to the Better HQ "All Clubs" page. */
export default function AflAdminSync() {
  const [runs, setRuns] = useState(null)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  const refresh = useCallback(() => {
    aflApi.getSyncRuns().then(d => setRuns(d.runs)).catch(() => {})
  }, [])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    const hasRunning = (runs || []).some(r => r.status === 'running')
    clearInterval(pollRef.current)
    if (hasRunning) pollRef.current = setInterval(refresh, 4000)
    return () => clearInterval(pollRef.current)
  }, [runs, refresh])

  const act = async (name, fn, confirmText) => {
    if (confirmText && !window.confirm(confirmText)) return
    setBusy(name)
    setError(null)
    try {
      await fn()
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  if (runs === null) return <p className="text-sm text-pb-faint">Loading…</p>

  const running = runs.find(r => r.status === 'running')

  return (
    <div className="space-y-6">
      {error && <p className="pb-card p-3 text-sm text-[var(--pb-negative)]">{error}</p>}

      <div className="pb-card p-4 space-y-3">
        <SectionTitle>Data sync</SectionTitle>
        <p className="text-sm text-pb-dim">
          <strong className="text-pb-text">Sync Now</strong> pulls the latest games and stats from PlayHQ — safe to run anytime.{' '}
          <strong className="text-pb-text">Full Rebuild</strong> wipes the synced game data and re-pulls everything (slow).
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            disabled={!!busy || !!running}
            onClick={() => act('sync', aflApi.syncNow)}
            className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50"
          >
            {busy === 'sync' ? 'Starting…' : 'Sync Now'}
          </button>
          <button
            disabled={!!busy || !!running}
            onClick={() => act('rebuild', aflApi.fullRebuild,
              'Full Rebuild wipes all synced games and stats for this club and re-pulls everything from PlayHQ. Continue?')}
            className="px-4 py-2 rounded font-semibold bg-pb-surface2 text-pb-text border border-pb-hairline disabled:opacity-50"
          >
            {busy === 'rebuild' ? 'Starting…' : 'Full Rebuild'}
          </button>
        </div>
        {running && (
          <div className="text-sm text-pb-dim">
            <span className="pb-pulse inline-block h-2 w-2 rounded-full bg-[var(--pb-accent)] mr-2" />
            {running.stats?.progress_phase || 'Running'}…
            {running.stats?.progress_pct != null && ` ${running.stats.progress_pct}%`}
            {running.stats?.progress_total != null && ` (${running.stats.progress_done ?? 0}/${running.stats.progress_total})`}
          </div>
        )}
      </div>

      <div className="pb-card p-4">
        <SectionTitle>Sync history</SectionTitle>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="pb-hairline-b">
              <tr>
                {['Started', 'Kind', 'Status', 'Games', 'Players', 'Events'].map((h, i) => (
                  <th key={h} className={`px-2 py-1.5 font-mono text-[10px] uppercase text-pb-faint ${i > 2 ? 'text-right' : 'text-left'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr key={r.id} className="pb-hairline-b last:border-0">
                  <td className="px-2 py-1.5 pb-num text-pb-faint">{(r.started_at || '').replace('T', ' ').slice(0, 16)}</td>
                  <td className="px-2 py-1.5">{r.kind}</td>
                  <td className="px-2 py-1.5">
                    <span className={
                      r.status === 'success' ? 'text-[var(--pb-positive)]'
                        : r.status === 'error' ? 'text-[var(--pb-negative)]'
                          : 'text-[var(--pb-amber)]'
                    }>
                      {r.status}
                    </span>
                    {r.error && <span className="block text-[11px] text-pb-faint truncate max-w-[220px]" title={r.error}>{r.error}</span>}
                  </td>
                  <td className="px-2 py-1.5 text-right pb-num">{r.stats?.games_stats_synced ?? '—'}</td>
                  <td className="px-2 py-1.5 text-right pb-num">{r.stats?.players ?? '—'}</td>
                  <td className="px-2 py-1.5 text-right pb-num">{r.stats?.events_stored ?? '—'}</td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr><td colSpan={6} className="px-2 py-3 text-pb-faint">No syncs yet — run one above.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
