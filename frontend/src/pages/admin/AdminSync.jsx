import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import LoadingBar, { ProgressBar } from '../../components/ProgressBar'
import { useToast } from '../../contexts/ToastContext'
import SyncRunCard, { syncProgressLabel } from '../../components/admin/SyncRunCard'

export default function AdminSync() {
  const toast = useToast()
  const [settings, setSettings] = useState(null)
  const [logs, setLogs] = useState([])
  const [syncing, setSyncing] = useState(false)
  const [lastTriggered, setLastTriggered] = useState(null)
  const [polling, setPolling] = useState(false)
  const [syncRequests, setSyncRequests] = useState([])
  const [actionLoading, setActionLoading] = useState(null)
  const [hardRefreshing, setHardRefreshing] = useState(false)
  const [backfilling, setBackfilling] = useState(false)
  const [cleaningOpp, setCleaningOpp] = useState(false)
  const [syncWarnings, setSyncWarnings] = useState({})
  const [drift, setDrift] = useState(null)

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

  const fetchDrift = useCallback(async () => {
    try {
      setDrift(await api.adminGetSyncDrift())
    } catch { /* silent — the notice is advisory, never blocks the page */ }
  }, [])

  useEffect(() => {
    api.adminGetSettings().then(s => {
      setSettings(s)
      if (s?.id) fetchLogs(s.id)
    }).catch(() => {})
    fetchSyncRequests()
    fetchDrift()
  }, [fetchLogs, fetchSyncRequests, fetchDrift])

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

  // Keep polling while a run is live — including runs this tab didn't trigger
  // (the weekly job, another admin) — so the progress bar stays current.
  useEffect(() => {
    if (!logs.length) return
    const latest = logs[0]
    if (latest.status === 'running') {
      if (!polling) setPolling(true)
      return
    }
    if (!polling) return
    // Latest run is finished: stop, unless we just triggered one whose row
    // hasn't appeared in the log yet.
    if (!lastTriggered || new Date(latest.started_at) >= new Date(lastTriggered)) {
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
        toast.info('A sync is already running for this club. Wait for it to complete.')
        return
      }
      setPolling(true)
    } catch (e) {
      setSyncing(false)
      toast.error(`Failed to start sync: ${e.message}`)
    }
  }

  const handleBackfillAggregates = async () => {
    if (!orgId || backfilling || syncing || hardRefreshing) return
    setBackfilling(true)
    try {
      const res = await api.adminBackfillAggregates()
      toast.success(`Backfill complete — inserted ${res.inserted ?? 0} aggregate rows.`)
    } catch (e) {
      toast.error(`Backfill failed: ${e.message}`)
    } finally {
      setBackfilling(false)
    }
  }

  const handleCleanupOpposition = async () => {
    if (!orgId || cleaningOpp || syncing || hardRefreshing || backfilling) return
    const ok = window.confirm(
      'Remove batting / bowling / fielding rows that belong to players who were on the OPPOSITION team in those games. ' +
      'Inflated match counts (e.g. a current club member who played against us a few times having those games counted as theirs) get corrected. ' +
      'Cheaper than a Full Rebuild — runs in seconds. Continue?'
    )
    if (!ok) return
    setCleaningOpp(true)
    try {
      const res = await api.adminCleanupOppositionStats()
      const d = res.deleted || {}
      const total = (d.batting_innings || 0) + (d.bowling_spells || 0) + (d.fielding_stats || 0)
      toast.success(
        `Cleanup complete — removed ${total} opposition stat rows ` +
        `(${d.batting_innings || 0} batting, ${d.bowling_spells || 0} bowling, ${d.fielding_stats || 0} fielding), ` +
        `dropped ${d.player_season_stats_phantom || 0} phantom season rows, ` +
        `re-backfilled ${d.player_season_stats_backfilled || 0}.`
      )
    } catch (e) {
      toast.error(`Cleanup failed: ${e.message}`)
    } finally {
      setCleaningOpp(false)
    }
  }

  const handleHardRefresh = async () => {
    if (!orgId || hardRefreshing || syncing || backfilling) return
    const ok = window.confirm(
      'Full Rebuild wipes every stored game for this club and re-pulls all match history. ' +
      'This may take an hour or longer for clubs with a lot of history. Continue?'
    )
    if (!ok) return
    setHardRefreshing(true)
    setLastTriggered(new Date().toISOString())
    try {
      const res = await api.adminHardRefreshOrg()
      if (res.status === 'already_running') {
        setHardRefreshing(false)
        toast.info('A full rebuild is already running for this club. Wait for it to complete.')
        return
      }
      setPolling(true)
    } catch (e) {
      setHardRefreshing(false)
      toast.error(`Failed to start full rebuild: ${e.message}`)
    }
  }

  const runningLog = logs.find(l => l.status === 'running')

  const handleDismissDrift = async () => {
    try {
      await api.adminAcknowledgeSyncDrift()
      await fetchDrift()
    } catch (e) {
      toast.error(`Could not dismiss: ${e.message}`)
    }
  }

  const driftFindings = drift?.findings || []

  return (
    <BetterStatsLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-6">Data Sync</h1>

        {driftFindings.length > 0 && (
          <DriftNotice
            findings={driftFindings}
            checkedAt={drift?.last_checked_at}
            onRebuild={handleHardRefresh}
            onDismiss={handleDismissDrift}
            busy={hardRefreshing || syncing || backfilling || cleaningOpp || !orgId}
          />
        )}

        {/* Coming from CricketStatz. Its own screen rather than a fourth
            button here: the sync actions all talk to Cricket Australia and run
            on a club that is already set up, whereas this is a one-off move of
            a club's whole history off another platform. */}
        <div className="pb-card p-5 mb-8">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">
            Coming from CricketStatz?
          </p>
          <p className="text-[13px] text-pb-dim mb-3 max-w-2xl">
            If your club keeps its records on CricketStatz, paste the address of
            your own stats page and we will bring the lot across — every season,
            every match, every scorecard, and your record book.
          </p>
          <Link
            to="/admin/cricketstatz"
            className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] font-semibold"
            style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
          >
            Import from CricketStatz
          </Link>
        </div>

        {/* Trigger card */}
        <div className="pb-card p-5 mb-8">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">Sync Actions</p>

          {/* Update with latest data */}
          <div className="flex items-start gap-4 py-3">
            <button
              onClick={handleSync}
              disabled={syncing || hardRefreshing || backfilling || cleaningOpp || !orgId}
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
                Adds new games and updates existing players automatically. Safe to run anytime —
                this is the normal weekly sync.
              </p>
            </div>
          </div>

          {/* Fix missing totals */}
          <div className="flex items-start gap-4 py-3 pb-hairline-t">
            <button
              onClick={handleBackfillAggregates}
              disabled={backfilling || syncing || hardRefreshing || cleaningOpp || !orgId}
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
                headline reads 0 despite having visible innings. No new data pulled —
                runs in seconds.
              </p>
              {backfilling && <LoadingBar expectedMs={12000} className="mt-2" />}
            </div>
          </div>

          {/* Clean opposition stats */}
          <div className="flex items-start gap-4 py-3 pb-hairline-t">
            <button
              onClick={handleCleanupOpposition}
              disabled={cleaningOpp || backfilling || syncing || hardRefreshing || !orgId}
              className="w-44 shrink-0 px-4 py-2 rounded font-mono text-[11px] tracking-wide2 font-semibold border transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-pb-text"
              style={{ borderColor: 'var(--pb-hairline)', background: 'transparent' }}
            >
              {cleaningOpp ? (
                <>
                  <span className="w-3 h-3 border-2 border-pb-text/30 border-t-pb-text rounded-full animate-spin" />
                  CLEANING…
                </>
              ) : 'CLEAN OPPOSITION STATS'}
            </button>
            <div className="flex-1">
              <p className="text-pb-text text-sm font-medium mb-0.5">Remove opposition appearances counted as ours</p>
              <p className="text-pb-faint text-xs leading-relaxed">
                Drops batting / bowling / fielding rows belonging to players who were on the opposition team
                in those games. Fixes inflated match counts (e.g. a current club member who played against us
                having those games attributed to their club record). Runs in seconds.
              </p>
              {cleaningOpp && <LoadingBar expectedMs={8000} className="mt-2" />}
            </div>
          </div>

          {/* Full rebuild */}
          <div className="flex items-start gap-4 py-3 pb-hairline-t">
            <button
              onClick={handleHardRefresh}
              disabled={hardRefreshing || syncing || backfilling || cleaningOpp || !orgId}
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
                Deletes every stored game and re-pulls all match history. Use after a
                sync-logic change or if data looks broadly wrong. Slow — an hour or more for a club with
                a lot of history.
              </p>
            </div>
          </div>

          {(syncing || hardRefreshing || runningLog) && (
            <div className="mt-3 pt-3 pb-hairline-t">
              <ProgressBar
                pct={runningLog?.stats?.progress_pct ?? 0}
                label={syncProgressLabel(runningLog?.stats || {})}
                labelClassName="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint"
              />
              <p className="font-mono text-[10px] text-pb-faint mt-2">
                Running in background — this page will update automatically.
                A full rebuild can take an hour or longer.
              </p>
            </div>
          )}
          {settings && (
            <div className="mt-4 pt-4 pb-hairline-t">
              <p className="font-mono text-[10px] text-pb-faint">
                Club ID:{' '}
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
              {logs.map((entry, i) => (
                <SyncRunCard key={entry.id || i} entry={entry} isLatest={i === 0} />
              ))}
            </div>
          )}
        </div>
      </div>
    </BetterStatsLayout>
  )
}

/**
 * "Cricket Australia has changed a season you already hold."
 *
 * The scheduled sync only pulls fixtures played since the club's last run, so
 * nothing revisits an older season on its own. The monthly drift check
 * compares the season totals we stored against CA's current ones and raises
 * this when they no longer agree — a Full Rebuild is the fix, and dismissing
 * only records that someone has looked.
 */
function DriftNotice({ findings, checkedAt, onRebuild, onDismiss, busy }) {
  const seasons = findings.map(f => f.season).filter(Boolean)
  const examples = findings.flatMap(f => f.examples || []).slice(0, 3)
  const checked = checkedAt ? new Date(checkedAt).toLocaleDateString() : null

  return (
    <div
      className="pb-card p-5 mb-8 border"
      style={{ borderColor: 'var(--pb-amber)', background: 'color-mix(in srgb, var(--pb-amber) 7%, transparent)' }}
    >
      <p className="font-mono text-[10px] tracking-wide3 uppercase mb-2" style={{ color: 'var(--pb-amber)' }}>
        Historical data has changed
      </p>
      <p className="text-pb-text text-sm font-medium mb-1">
        {seasons.length === 1
          ? `${seasons[0]} no longer matches Cricket Australia`
          : `${seasons.length} past seasons no longer match Cricket Australia`}
      </p>
      <p className="text-pb-faint text-xs leading-relaxed mb-3">
        Cricket Australia has revised {seasons.length === 1 ? 'this season' : 'these seasons'} since
        BetterStats last pulled {seasons.length === 1 ? 'it' : 'them'}. The scheduled sync only fetches
        recent fixtures, so it will not pick the changes up. A Full Rebuild re-pulls the club&apos;s whole
        history and brings the figures back into line.
        {seasons.length > 1 && <> Affected: {seasons.join(', ')}.</>}
      </p>

      {examples.length > 0 && (
        <ul className="mb-3 space-y-0.5">
          {examples.map((ex, i) => (
            <li key={i} className="font-mono text-[10px] text-pb-faint">
              {ex.player} · {ex.field === 'missing'
                ? 'we hold no season record'
                : `${ex.field}: we have ${ex.ours}, they have ${ex.theirs}`}
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center gap-4">
        <button
          onClick={onRebuild}
          disabled={busy}
          className="px-4 py-2 rounded font-mono text-[11px] tracking-wide2 font-semibold border transition disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ borderColor: 'var(--pb-amber)', color: 'var(--pb-amber)', background: 'transparent' }}
        >
          RUN FULL REBUILD
        </button>
        <button
          onClick={onDismiss}
          className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors"
        >
          Dismiss
        </button>
        {checked && (
          <span className="font-mono text-[10px] text-pb-faintest ml-auto">Checked {checked}</span>
        )}
      </div>
    </div>
  )
}
