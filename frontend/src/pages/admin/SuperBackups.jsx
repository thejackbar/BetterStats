import { Fragment, useState, useEffect, useMemo } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const TYPE_LABEL = { backup: 'Backup', restore_full: 'Restore (full)', restore_club: 'Restore (club)' }

const STATUS_STYLE = {
  requested: 'bg-pb-surface2 text-pb-faint border-pb-hairline',
  running:   'bg-accent/15 text-accent border-accent/40',
  completed: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  failed:    'bg-red-500/15 text-red-300 border-red-500/40',
}

function fmtBytes(n) {
  if (n === null || n === undefined) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = Number(n), i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

function fmtDateTime(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

// Live progress for a running task — percentage bar, current stage's
// "Processing X N of M" message, plus a running tally of finished stages
// ("Players: 876", "Games: 3957", ...). Table-level for a whole-DB
// backup/restore (pg_dump/pg_restore don't expose row-level progress within
// a table); true row-level for a per-club restore.
function ProgressBar({ progress }) {
  if (!progress) {
    return <p className="font-mono text-[10px] text-pb-faint">Starting…</p>
  }
  const { stage, current, total, message, stage_results: stageResults } = progress
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0
  return (
    <div className="space-y-2 max-w-xl">
      <div className="flex items-center justify-between font-mono text-[10px] text-pb-faint">
        <span>{message || (stage ? `Processing ${stage}` : 'Working…')}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-pb-surface2 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: 'var(--pb-accent)' }}
        />
      </div>
      {stageResults && Object.keys(stageResults).length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-pb-dim">
          {Object.entries(stageResults).map(([name, count]) => (
            <span key={name}>
              {name.charAt(0).toUpperCase() + name.slice(1).replace(/_/g, ' ')}: {Number(count).toLocaleString()}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// Downloads a bundle file (still age-encrypted, exactly as it sits on
// disk — this app never sends backups anywhere on its own; a manual
// download is the only way a copy leaves the server).
function DownloadLink({ taskId, file, label }) {
  const [busy, setBusy] = useState(false)
  const download = async () => {
    setBusy(true)
    try {
      const res = await api.superDownloadBackupFile(taskId, file)
      if (!res.ok) throw new Error(`Download failed (${res.status})`)
      const disposition = res.headers.get('Content-Disposition') || ''
      const match = disposition.match(/filename="([^"]+)"/)
      const filename = match ? match[1] : `${taskId}-${file}`
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      window.alert('Could not download this file — the backup-agent may be unreachable.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <button onClick={download} disabled={busy}
      className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text disabled:opacity-50">
      {busy ? '…' : label}
    </button>
  )
}

export default function SuperBackups() {
  const [tasks, setTasks] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [stats, setStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [running, setRunning] = useState(false)
  const [runMsg, setRunMsg] = useState('')

  const loadTasks = () => {
    setLoading(true)
    const params = {}
    if (typeFilter) params.task_type = typeFilter
    if (statusFilter) params.status = statusFilter
    api.superListBackupTasks(params)
      .then((d) => { setTasks(d?.tasks || []); setTotal(d?.total || 0); setError('') })
      .catch((e) => setError(e.message || 'Could not load backup tasks.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadTasks() }, [typeFilter, statusFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  const hasRunning = tasks.some((t) => t.status === 'running' || t.status === 'requested')
  useEffect(() => {
    if (!hasRunning) return
    const id = setInterval(loadTasks, 3000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasRunning])

  useEffect(() => {
    setStatsLoading(true)
    api.superBackupStats().then(setStats).catch(() => {}).finally(() => setStatsLoading(false))
  }, [])

  const topClubs = useMemo(() => {
    if (!stats?.club_stats) return []
    return Object.entries(stats.club_stats)
      .map(([id, v]) => ({ id, ...v }))
      .sort((a, b) => (b.size_bytes || 0) - (a.size_bytes || 0))
  }, [stats])

  const runNow = async () => {
    setRunning(true)
    setRunMsg('')
    try {
      const res = await api.superRunBackupNow()
      if (res?.status === 'already_running') {
        setRunMsg('A backup is already running.')
      } else {
        setRunMsg('Backup started — progress shows below as it runs.')
      }
      // give the new "running" row a moment to land, then refresh the list
      // (the polling effect takes over from there while it's running)
      setTimeout(loadTasks, 1500)
    } catch (err) {
      setRunMsg(err.message || 'Could not start a backup.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-pb-text">Backups</h1>
            <p className="text-sm text-pb-dim mt-1">
              Daily automated backup history, plus current database size. Schedule and retention
              are set from General Settings → Backups.
            </p>
            <p className="text-xs text-pb-faint mt-2 max-w-2xl">
              Backup runs as a host-level script (see docs/backup-system.md) — this page proxies
              "Run backup now" to it, then shows what it logged. Restore (full or per-club) is
              deliberately NOT triggerable from here — it needs the backup encryption key, which
              is kept offline for safety, so it's always run by an operator directly on the
              server. Backups are never sent anywhere automatically — every DB/Uploads download
              below is a manual, on-demand copy of the still-encrypted file, nothing more.
            </p>
          </div>
          <div className="text-right shrink-0">
            <button onClick={runNow} disabled={running}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 uppercase font-semibold transition disabled:opacity-50 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}>
              {running ? 'Starting…' : 'Run backup now'}
            </button>
            {runMsg && <p className="font-mono text-[10px] text-pb-faint mt-2 max-w-[220px]">{runMsg}</p>}
          </div>
        </div>

        {/* Live DB size / per-club stats */}
        <div className="pb-card p-4 mb-5">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">
            Current database size
          </p>
          {statsLoading ? (
            <p className="text-sm text-pb-dim">Loading…</p>
          ) : !stats ? (
            <p className="text-sm text-pb-dim">Could not load stats.</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-6 mb-4">
                <div>
                  <p className="font-mono text-[10px] text-pb-faint uppercase">Total DB size</p>
                  <p className="text-lg font-semibold text-pb-text">{fmtBytes(stats.db_size_bytes)}</p>
                </div>
                <div>
                  <p className="font-mono text-[10px] text-pb-faint uppercase">Total records (org-scoped)</p>
                  <p className="text-lg font-semibold text-pb-text">{(stats.total_row_count || 0).toLocaleString()}</p>
                </div>
                <div>
                  <p className="font-mono text-[10px] text-pb-faint uppercase">Clubs</p>
                  <p className="text-lg font-semibold text-pb-text">{topClubs.length}</p>
                </div>
              </div>
              <p className="font-mono text-[10px] text-pb-faintest mb-2">
                Per-club size is an estimate (rows are exact; bytes are each table's on-disk
                size split proportionally by row share) — see docs/backup-system.md.
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                      <th className="px-3 py-2">Club</th>
                      <th className="px-3 py-2">Records</th>
                      <th className="px-3 py-2">Size (est.)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topClubs.map((c) => (
                      <tr key={c.id} className="border-b pb-hairline">
                        <td className="px-3 py-1.5 text-pb-text">{c.name}</td>
                        <td className="px-3 py-1.5 text-pb-dim">{(c.rows || 0).toLocaleString()}</td>
                        <td className="px-3 py-1.5 text-pb-dim">{fmtBytes(c.size_bytes)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        {/* Task history */}
        <div className="flex flex-wrap gap-2 mb-4">
          {['', 'backup', 'restore_full', 'restore_club'].map((t) => (
            <button key={t || 'all'} onClick={() => setTypeFilter(t)}
              className={`px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase border transition ${
                typeFilter === t ? 'border-pb-accent text-pb-text' : 'border-pb-hairline text-pb-faint hover:text-pb-text'
              }`}>
              {t ? TYPE_LABEL[t] : 'All types'}
            </button>
          ))}
          <span className="w-px bg-pb-hairline mx-1" />
          {['', 'requested', 'running', 'completed', 'failed'].map((s) => (
            <button key={s || 'anystatus'} onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase border transition ${
                statusFilter === s ? 'border-pb-accent text-pb-text' : 'border-pb-hairline text-pb-faint hover:text-pb-text'
              }`}>
              {s || 'Any status'}
            </button>
          ))}
        </div>

        {error && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>
        )}

        {loading ? (
          <p className="text-sm text-pb-dim">Loading…</p>
        ) : tasks.length === 0 ? (
          <div className="pb-card p-8 text-center">
            <p className="text-sm text-pb-dim">
              No backup/restore tasks recorded yet. They'll appear here once the daily timer
              runs, or a manual backup/restore is run on the server.
            </p>
          </div>
        ) : (
          <div className="pb-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                  <th className="px-3 py-2.5">Started</th>
                  <th className="px-3 py-2.5">Type</th>
                  <th className="px-3 py-2.5">Scope</th>
                  <th className="px-3 py-2.5">Triggered</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-3 py-2.5">DB size</th>
                  <th className="px-3 py-2.5">Uploads size</th>
                  <th className="px-3 py-2.5">Records</th>
                  <th className="px-3 py-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t) => (
                  <Fragment key={t.id}>
                    <tr className="border-b pb-hairline align-top hover:bg-pb-surface2/40">
                      <td className="px-3 py-2.5 whitespace-nowrap text-pb-dim">{fmtDateTime(t.started_at)}</td>
                      <td className="px-3 py-2.5 text-pb-text">{TYPE_LABEL[t.task_type] || t.task_type}</td>
                      <td className="px-3 py-2.5 text-pb-dim">{t.scope_org_name || 'Whole platform'}</td>
                      <td className="px-3 py-2.5 text-pb-dim whitespace-nowrap">{t.triggered_by}</td>
                      <td className="px-3 py-2.5">
                        <span className={`inline-block px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase ${STATUS_STYLE[t.status] || ''}`}>
                          {t.status}
                        </span>
                        {t.error_message && (
                          <p className="text-red-400 text-xs mt-1 max-w-[220px] truncate" title={t.error_message}>
                            {t.error_message}
                          </p>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-pb-dim whitespace-nowrap">{fmtBytes(t.db_size_bytes)}</td>
                      <td className="px-3 py-2.5 text-pb-dim whitespace-nowrap">{fmtBytes(t.uploads_size_bytes)}</td>
                      <td className="px-3 py-2.5 text-pb-dim whitespace-nowrap">
                        {t.total_row_count != null ? t.total_row_count.toLocaleString() : '-'}
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap space-y-1">
                        {t.club_stats && (
                          <button
                            onClick={() => setExpanded(expanded === t.id ? null : t.id)}
                            className="block font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text"
                          >
                            {expanded === t.id ? 'Hide' : 'Per-club'}
                          </button>
                        )}
                        {t.task_type === 'backup' && t.status === 'completed' && (
                          <div className="flex gap-2">
                            <DownloadLink taskId={t.id} file="db" label="DB" />
                            <DownloadLink taskId={t.id} file="uploads" label="Uploads" />
                          </div>
                        )}
                      </td>
                    </tr>
                    {(t.status === 'running' || t.status === 'requested') && (
                      <tr className="border-b pb-hairline bg-pb-surface2/20">
                        <td colSpan={9} className="px-3 py-3">
                          <ProgressBar progress={t.progress} />
                        </td>
                      </tr>
                    )}
                    {expanded === t.id && t.club_stats && (
                      <tr className="border-b pb-hairline bg-pb-surface2/20">
                        <td colSpan={9} className="px-3 py-3">
                          <div className="overflow-x-auto max-h-64 overflow-y-auto">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint">
                                  <th className="px-2 py-1">Club</th>
                                  <th className="px-2 py-1">Records</th>
                                  <th className="px-2 py-1">Size (est.)</th>
                                </tr>
                              </thead>
                              <tbody>
                                {Object.entries(t.club_stats)
                                  .map(([id, v]) => ({ id, ...v }))
                                  .sort((a, b) => (b.size_bytes || 0) - (a.size_bytes || 0))
                                  .map((c) => (
                                    <tr key={c.id}>
                                      <td className="px-2 py-1 text-pb-text">{c.name}</td>
                                      <td className="px-2 py-1 text-pb-dim">{(c.rows || 0).toLocaleString()}</td>
                                      <td className="px-2 py-1 text-pb-dim">{fmtBytes(c.size_bytes)}</td>
                                    </tr>
                                  ))}
                              </tbody>
                            </table>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
            <p className="font-mono text-[10px] text-pb-faintest px-3 py-2">{total} task{total === 1 ? '' : 's'} total</p>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
