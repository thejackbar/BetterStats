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

// Clickable, sortable column header — shows an arrow when it's the active sort.
function SortTh({ label, sortKey, activeKey, dir, onClick, className = '' }) {
  const active = activeKey === sortKey
  return (
    <th
      className={`px-3 py-2 cursor-pointer select-none hover:text-pb-text ${className}`}
      onClick={() => onClick(sortKey)}
    >
      {label} {active && (dir === 'asc' ? '▲' : '▼')}
    </th>
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
      window.alert('Could not download this file. The backup-agent may be unreachable.')
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

const RESTORE_CONFIRM_WORD = 'RESTORE'

// Restore (full or per-club), triggered from the web instead of SSH. Two
// independent gates, in order: (1) type the confirmation word back exactly,
// checked entirely client-side/server-side before step 2 ever appears; (2)
// paste the age PRIVATE key, sent fresh with this one request and never
// stored anywhere — the backup-agent cryptographically verifies it's the
// real matching key before the restore is allowed to proceed. Plain SSH
// restore (ops/backup/restore.sh) remains fully available alongside this.
function RestoreModal({ task, mode, onClose, onStarted }) {
  const [step, setStep] = useState(1)
  const [confirmInput, setConfirmInput] = useState('')
  const [orgId, setOrgId] = useState('')
  const [clubs, setClubs] = useState([])
  const [clubsLoading, setClubsLoading] = useState(false)
  const [privateKey, setPrivateKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    if (mode !== 'club') return
    setClubsLoading(true)
    api.superListClubs().then((cs) => setClubs(cs || [])).catch(() => {}).finally(() => setClubsLoading(false))
  }, [mode])

  const bundle = (task.bundle_path || '').split('/').filter(Boolean).pop() || task.bundle_path

  const goToStep2 = () => {
    if (confirmInput !== RESTORE_CONFIRM_WORD) return
    setStep(2)
  }

  const submit = async () => {
    if (mode === 'club' && !orgId) {
      setMsg('Pick a club first.')
      return
    }
    setBusy(true)
    setMsg('')
    try {
      const res = mode === 'full'
        ? await api.superBackupRestoreFull(task.id, confirmInput, privateKey)
        : await api.superBackupRestoreClub(task.id, orgId, confirmInput, privateKey)
      if (res?.status === 'already_running') {
        setMsg(`Another operation is already running (${res.operation || 'unknown'}). Try again once it finishes.`)
      } else {
        onStarted()
        return // onStarted closes the modal
      }
    } catch (err) {
      setMsg(err.message || 'Could not start the restore.')
    } finally {
      // The private key never outlives this one request, success or failure.
      setPrivateKey('')
      setBusy(false)
    }
  }

  const close = () => {
    setPrivateKey('')
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 overflow-y-auto" onClick={close}>
      <div className="pb-card w-full max-w-lg bg-pb-surface mt-16" onClick={(e) => e.stopPropagation()}>
        <div className="p-5 pb-0">
          <h2 className="font-display font-bold text-lg text-pb-text">
            {mode === 'full' ? 'Restore, whole platform' : 'Restore, one club'}
          </h2>
          <p className="font-mono text-[10px] text-pb-faintest mt-1">Bundle: {bundle}</p>
        </div>

        <div className="p-5 space-y-4">
          {mode === 'full' ? (
            <p className="text-sm text-pb-dim">
              This REPLACES every club's live data with this bundle and briefly stops the app
              for every club. Only do this for genuine disaster recovery.
            </p>
          ) : (
            <p className="text-sm text-pb-dim">
              This restores ONE club's data from this bundle. No downtime, no effect on any
              other club. The club's current data is snapshotted first, so it can be undone
              (see docs/backup-system.md's rollback-club command).
            </p>
          )}

          {step === 1 ? (
            <div className="space-y-2">
              <label className="font-mono text-[10px] text-pb-faint block">
                Type <span className="text-pb-text font-bold">{RESTORE_CONFIRM_WORD}</span> to continue
              </label>
              <input
                type="text" value={confirmInput} autoFocus
                onChange={(e) => setConfirmInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && goToStep2()}
                className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
              />
            </div>
          ) : (
            <>
              {mode === 'club' && (
                <div>
                  <label className="font-mono text-[10px] text-pb-faint block mb-1">Club</label>
                  {clubsLoading ? (
                    <p className="text-sm text-pb-dim">Loading clubs…</p>
                  ) : (
                    <select value={orgId} onChange={(e) => setOrgId(e.target.value)}
                      className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
                      <option value="">Select a club…</option>
                      {clubs.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  )}
                </div>
              )}
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">
                  Private key (age identity: never stored, used once for this restore only)
                </label>
                <textarea
                  value={privateKey} onChange={(e) => setPrivateKey(e.target.value)}
                  rows={4} spellCheck={false} autoComplete="off"
                  placeholder="AGE-SECRET-KEY-1..."
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-xs font-mono focus:outline-none focus:border-pb-accent"
                />
                <p className="font-mono text-[10px] text-pb-faintest mt-1">
                  Rejected outright unless it's the real matching private key for this
                  server's configured public key, verified cryptographically before anything
                  is restored.
                </p>
              </div>
            </>
          )}

          {msg && <p className="text-sm text-red-400">{msg}</p>}
        </div>

        <div className="flex gap-2 p-5 pt-3 border-t pb-hairline">
          {step === 1 ? (
            <button onClick={goToStep2} disabled={confirmInput !== RESTORE_CONFIRM_WORD}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 uppercase font-semibold transition disabled:opacity-40 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}>
              Continue
            </button>
          ) : (
            <button onClick={submit} disabled={busy || !privateKey.trim() || (mode === 'club' && !orgId)}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 uppercase font-semibold transition disabled:opacity-40 bg-red-500 text-white">
              {busy ? 'Starting…' : 'Restore now'}
            </button>
          )}
          <button onClick={close} className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors">
            Cancel
          </button>
        </div>
      </div>
    </div>
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
  const [clubQuery, setClubQuery] = useState('')
  const [clubSortKey, setClubSortKey] = useState('size_bytes') // 'name' | 'rows' | 'size_bytes'
  const [clubSortDir, setClubSortDir] = useState('desc')
  const [restoreModal, setRestoreModal] = useState(null) // { task, mode: 'full'|'club' } | null

  const toggleClubSort = (key) => {
    if (clubSortKey === key) {
      setClubSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setClubSortKey(key)
      setClubSortDir(key === 'name' ? 'asc' : 'desc')
    }
  }

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
    return Object.entries(stats.club_stats).map(([id, v]) => ({ id, ...v }))
  }, [stats])

  const visibleClubs = useMemo(() => {
    let rows = topClubs
    const q = clubQuery.trim().toLowerCase()
    if (q) rows = rows.filter((c) => (c.name || '').toLowerCase().includes(q))
    const dir = clubSortDir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      if (clubSortKey === 'name') return dir * String(a.name || '').localeCompare(b.name || '')
      return dir * ((a[clubSortKey] || 0) - (b[clubSortKey] || 0))
    })
  }, [topClubs, clubQuery, clubSortKey, clubSortDir])

  const runNow = async () => {
    setRunning(true)
    setRunMsg('')
    try {
      const res = await api.superRunBackupNow()
      if (res?.status === 'already_running') {
        setRunMsg('A backup is already running.')
      } else {
        setRunMsg('Backup started. Progress shows below as it runs.')
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
              Backup and restore both run as host-level scripts (see docs/backup-system.md), 
              this page proxies to them and shows what they logged. Restore is available both
              here and over SSH: from here it needs the private key pasted in fresh each time
              (never stored) plus a typed confirmation, verified cryptographically before
              anything is touched. Backups are never sent anywhere automatically, every
              DB/Uploads download below is a manual, on-demand copy of the still-encrypted
              file, nothing more.
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
                size split proportionally by row share). See docs/backup-system.md.
              </p>
              <input
                type="text"
                value={clubQuery}
                onChange={(e) => setClubQuery(e.target.value)}
                placeholder="Search clubs…"
                className="w-full max-w-xs mb-3 bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
              />
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                      <SortTh label="Club" sortKey="name" activeKey={clubSortKey} dir={clubSortDir} onClick={toggleClubSort} />
                      <SortTh label="Records" sortKey="rows" activeKey={clubSortKey} dir={clubSortDir} onClick={toggleClubSort} />
                      <SortTh label="Size (est.)" sortKey="size_bytes" activeKey={clubSortKey} dir={clubSortDir} onClick={toggleClubSort} />
                    </tr>
                  </thead>
                  <tbody>
                    {visibleClubs.map((c) => (
                      <tr key={c.id} className="border-b pb-hairline">
                        <td className="px-3 py-1.5 text-pb-text">{c.name}</td>
                        <td className="px-3 py-1.5 text-pb-dim">{(c.rows || 0).toLocaleString()}</td>
                        <td className="px-3 py-1.5 text-pb-dim">{fmtBytes(c.size_bytes)}</td>
                      </tr>
                    ))}
                    {visibleClubs.length === 0 && (
                      <tr>
                        <td colSpan={3} className="px-3 py-3 text-pb-faint text-center">No clubs match "{clubQuery}"</td>
                      </tr>
                    )}
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
                          <>
                            <div className="flex gap-2">
                              <DownloadLink taskId={t.id} file="db" label="DB" />
                              <DownloadLink taskId={t.id} file="uploads" label="Uploads" />
                            </div>
                            <div className="flex gap-2">
                              <button
                                onClick={() => setRestoreModal({ task: t, mode: 'full' })}
                                className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-red-400"
                              >
                                Restore (full)
                              </button>
                              <button
                                onClick={() => setRestoreModal({ task: t, mode: 'club' })}
                                className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-red-400"
                              >
                                Restore (club)
                              </button>
                            </div>
                          </>
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

      {restoreModal && (
        <RestoreModal
          task={restoreModal.task}
          mode={restoreModal.mode}
          onClose={() => setRestoreModal(null)}
          onStarted={() => {
            setRestoreModal(null)
            setRunMsg(`Restore started. Progress shows in the task list below.`)
            setTimeout(loadTasks, 1500)
          }}
        />
      )}
    </AdminLayout>
  )
}
