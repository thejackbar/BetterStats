import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// Perth (AWST) is a fixed UTC+8 with no daylight saving, so a time set here
// means the same thing all year and needs no conversion on the way to the
// server — it is stored, checked and displayed as Perth throughout (see
// backend/app/services/backup_schedule.py).
const PERTH_TZ = 'Australia/Perth'

const INPUT_CLS =
  'bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm ' +
  'focus:outline-none focus:border-pb-accent'

function fmtBytes(n) {
  if (n === null || n === undefined) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = Number(n), i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

// Everything on this page is about a Perth-time schedule, so times are shown
// in Perth wherever they come from — a super admin reading this from
// anywhere else shouldn't have to work out the offset themselves.
function fmtPerth(iso, { withDate = true } = {}) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('en-AU', {
    timeZone: PERTH_TZ,
    ...(withDate ? { day: 'numeric', month: 'short', year: 'numeric' } : {}),
    hour: '2-digit', minute: '2-digit',
  })
}

function relativeFromNow(iso) {
  if (!iso) return ''
  const mins = Math.round((new Date(iso) - Date.now()) / 60000)
  if (mins <= 0) return 'due now'
  if (mins < 60) return `in ${mins} min`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `in ${hours} hour${hours === 1 ? '' : 's'}`
  return `in ${Math.round(hours / 24)} day${Math.round(hours / 24) === 1 ? '' : 's'}`
}

// A bundle's own directory name is backup.sh's UTC stamp
// (2026-08-21T19-00-00Z) — readable to a machine, not to a person, so it's
// parsed back into a real date and shown in Perth like everything else.
function bundleDate(bundle) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})Z$/.exec(bundle || '')
  if (!m) return null
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]))
}

function ageInDays(bundle) {
  const d = bundleDate(bundle)
  if (!d) return null
  return Math.floor((Date.now() - d.getTime()) / 86400000)
}

// Schedule + retention. Saving takes effect on the host timer's next tick —
// there's no unit file to edit and no redeploy, which is the whole point of
// the setting living here.
function ScheduleCard({ data, onSaved }) {
  const [hour, setHour] = useState(String(data.schedule.hour))
  const [minute, setMinute] = useState(String(data.schedule.minute))
  const [retention, setRetention] = useState(String(data.schedule.retention_days))
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const dirty =
    Number(hour) !== data.schedule.hour ||
    Number(minute) !== data.schedule.minute ||
    Number(retention) !== data.schedule.retention_days

  const save = async (e) => {
    e.preventDefault()
    setSaving(true); setMsg(''); setErr('')
    try {
      const saved = await api.superUpdateBackupSettings({
        hour: Math.min(23, Math.max(0, Number(hour) || 0)),
        minute: Math.min(59, Math.max(0, Number(minute) || 0)),
        retention_days: Math.max(1, Number(retention) || 1),
      })
      onSaved(saved)
      setMsg('Saved — the next scheduled run uses this.')
    } catch (e2) {
      setErr(e2.message || 'Could not save the backup settings.')
    } finally {
      setSaving(false)
    }
  }

  const shortening = Number(retention) < data.schedule.retention_days

  return (
    <form onSubmit={save} className="pb-card p-4 mb-5">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Schedule and retention</p>

      <div className="flex flex-wrap items-end gap-4">
        <label className="font-mono text-[10px] text-pb-faint">
          <span className="block mb-1">Hour (Perth)</span>
          <input type="number" min="0" max="23" value={hour}
            onChange={(e) => setHour(e.target.value)} className={`${INPUT_CLS} w-20`} />
        </label>
        <label className="font-mono text-[10px] text-pb-faint">
          <span className="block mb-1">Minute</span>
          <input type="number" min="0" max="59" value={minute}
            onChange={(e) => setMinute(e.target.value)} className={`${INPUT_CLS} w-20`} />
        </label>
        <label className="font-mono text-[10px] text-pb-faint">
          <span className="block mb-1">Keep backups for (days)</span>
          <input type="number" min={data.retention_min_days} max={data.retention_max_days} value={retention}
            onChange={(e) => setRetention(e.target.value)} className={`${INPUT_CLS} w-28`} />
        </label>
        <button type="submit" disabled={saving || !dirty}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 uppercase font-semibold transition disabled:opacity-40 text-pb-bg"
          style={{ background: 'var(--pb-accent)' }}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>

      <p className="text-xs text-pb-dim mt-3">
        The backup runs daily at{' '}
        <span className="text-pb-text font-semibold">
          {String(data.schedule.hour).padStart(2, '0')}:{String(data.schedule.minute).padStart(2, '0')}
        </span>{' '}
        Perth time and keeps{' '}
        <span className="text-pb-text font-semibold">{data.schedule.retention_days}</span>{' '}
        day{data.schedule.retention_days === 1 ? '' : 's'} of bundles. Perth has no daylight
        saving, so the time you set is the time it runs all year.
      </p>

      {shortening && (
        <p className="text-xs text-amber-300 mt-2">
          Shortening the window doesn't delete anything when you save — the next run prunes
          what's then out of range. To free the space now, delete the bundles below.
        </p>
      )}

      <div className="flex flex-wrap gap-x-8 gap-y-2 mt-4 pt-3 border-t pb-hairline">
        <div>
          <p className="font-mono text-[10px] text-pb-faint uppercase">Last completed</p>
          <p className="text-sm text-pb-text">{fmtPerth(data.last_completed_at)}</p>
        </div>
        <div>
          <p className="font-mono text-[10px] text-pb-faint uppercase">Next run</p>
          <p className="text-sm text-pb-text">
            {fmtPerth(data.next_run_at)}{' '}
            <span className="text-pb-faint">({relativeFromNow(data.next_run_at)})</span>
          </p>
        </div>
        <div>
          <p className="font-mono text-[10px] text-pb-faint uppercase">Perth time now</p>
          <p className="text-sm text-pb-dim">{fmtPerth(data.perth_now, { withDate: false })}</p>
        </div>
      </div>

      <p className="font-mono text-[10px] text-pb-faintest mt-3">
        A run that is missed (the server was down, say) is taken on the next tick rather than
        skipped for the day — the host timer checks every 15 minutes and backs up once the
        configured time has passed with no backup yet that day.
      </p>

      {msg && <p className="text-xs text-emerald-300 mt-3">{msg}</p>}
      {err && <p className="text-xs text-red-400 mt-3">{err}</p>}
    </form>
  )
}

// Confirms a deletion by naming exactly what goes and how much it frees. The
// newest bundle needs its own extra tick — it's the one a restore would
// reach for, so a select-all shouldn't quietly sweep it up.
function DeleteConfirm({ bundles, latest, totalBytes, busy, onCancel, onConfirm }) {
  const includesLatest = bundles.includes(latest)
  const [latestOk, setLatestOk] = useState(false)
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="pb-card w-full max-w-lg p-5">
        <h2 className="text-lg font-semibold text-pb-text mb-2">
          Delete {bundles.length} backup{bundles.length === 1 ? '' : 's'}?
        </h2>
        <p className="text-sm text-pb-dim mb-3">
          This deletes the backup FILES for {bundles.length === 1 ? 'this run' : 'these runs'} and
          frees about {fmtBytes(totalBytes)}. The run history, sizes and per-club record counts
          stay on the Backups page — only the files go, and they can't be restored from
          afterwards.
        </p>
        <div className="max-h-40 overflow-y-auto border pb-hairline rounded p-2 mb-3">
          {bundles.map((b) => (
            <p key={b} className="font-mono text-[11px] text-pb-dim">{b}</p>
          ))}
        </div>
        {includesLatest && (
          <label className="flex items-start gap-2 mb-3 text-xs text-amber-300">
            <input type="checkbox" checked={latestOk} onChange={(e) => setLatestOk(e.target.checked)}
              className="mt-0.5" />
            <span>
              This selection includes <span className="font-mono">{latest}</span>, the most recent
              backup — the one a restore would use. Delete it too.
            </span>
          </label>
        )}
        <div className="flex gap-2">
          <button onClick={() => onConfirm(includesLatest)} disabled={busy || (includesLatest && !latestOk)}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 uppercase font-semibold bg-red-500/90 text-white disabled:opacity-40">
            {busy ? 'Deleting…' : 'Delete'}
          </button>
          <button onClick={onCancel} disabled={busy}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 uppercase border pb-hairline text-pb-dim hover:text-pb-text">
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

export default function SuperBackupSettings() {
  const [settings, setSettings] = useState(null)
  const [settingsErr, setSettingsErr] = useState('')
  const [files, setFiles] = useState(null)
  const [filesErr, setFilesErr] = useState('')
  const [filesLoading, setFilesLoading] = useState(true)
  const [selected, setSelected] = useState(() => new Set())
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteMsg, setDeleteMsg] = useState('')

  useEffect(() => {
    api.superBackupSettings().then(setSettings)
      .catch((e) => setSettingsErr(e.message || 'Could not load the backup settings.'))
  }, [])

  const loadFiles = () => {
    setFilesLoading(true)
    api.superBackupFiles()
      .then((d) => { setFiles(d); setFilesErr('') })
      .catch((e) => setFilesErr(e.message || 'Could not list the stored backups.'))
      .finally(() => setFilesLoading(false))
  }
  useEffect(loadFiles, [])

  const bundles = files?.bundles || []
  const latest = bundles.length ? bundles[0].bundle : null
  const retention = settings?.schedule?.retention_days

  // "Older than the retention window" is the selection a super admin
  // actually wants most of the time — bundles the next run would prune
  // anyway, only sooner.
  const olderThanRetention = useMemo(
    () => (retention ? bundles.filter((b) => (ageInDays(b.bundle) ?? 0) > retention) : []),
    [bundles, retention],
  )

  const selectedList = useMemo(
    () => bundles.filter((b) => selected.has(b.bundle)).map((b) => b.bundle),
    [bundles, selected],
  )
  const selectedBytes = useMemo(
    () => bundles.filter((b) => selected.has(b.bundle))
      .reduce((sum, b) => sum + (b.size_bytes || 0), 0),
    [bundles, selected],
  )

  const toggle = (bundle) => setSelected((prev) => {
    const next = new Set(prev)
    if (next.has(bundle)) next.delete(bundle); else next.add(bundle)
    return next
  })

  const runDelete = async (includeLatest) => {
    setDeleting(true)
    try {
      const res = await api.superDeleteBackupFiles(selectedList, includeLatest)
      const failed = (res.results || []).filter((r) => r.status === 'failed')
      setDeleteMsg(
        `Deleted ${res.deleted_count} backup${res.deleted_count === 1 ? '' : 's'}, ` +
        `freeing ${fmtBytes(res.freed_bytes)}.` +
        (failed.length ? ` ${failed.length} could not be deleted: ${failed.map((f) => f.bundle).join(', ')}.` : ''),
      )
      setSelected(new Set())
      setConfirming(false)
      loadFiles()
    } catch (e) {
      setDeleteMsg(e.message || 'Could not delete those backups.')
      setConfirming(false)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-[1000px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Backup settings</h1>
          <p className="text-sm text-pb-dim mt-1">
            When the daily backup runs, how long backups are kept, and what's stored on the
            server right now.{' '}
            <Link to="/admin/super/backups" className="underline hover:text-pb-text">
              Run history and restore
            </Link>{' '}
            live on the Backups page.
          </p>
        </div>

        {settingsErr && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">
            {settingsErr}
          </p>
        )}
        {!settings && !settingsErr && <p className="text-sm text-pb-dim mb-5">Loading…</p>}
        {settings && <ScheduleCard data={settings} onSaved={setSettings} />}

        <div className="pb-card p-4">
          <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
            <div>
              <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Stored backups</p>
              <p className="text-xs text-pb-dim mt-1">
                {files ? (
                  <>
                    {bundles.length} bundle{bundles.length === 1 ? '' : 's'} on disk, {fmtBytes(files.total_size_bytes)} total
                    {files.backup_root && <> in <span className="font-mono">{files.backup_root}</span></>}.
                  </>
                ) : 'Reading the server\u2019s backup directory…'}
              </p>
            </div>
            <button onClick={loadFiles} disabled={filesLoading}
              className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint hover:text-pb-text disabled:opacity-50">
              {filesLoading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>

          {filesErr && <p className="text-sm text-red-400 mb-3">{filesErr}</p>}

          {files && bundles.length > 0 && (
            <>
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <button onClick={() => setSelected(new Set(bundles.map((b) => b.bundle)))}
                  className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase border pb-hairline text-pb-faint hover:text-pb-text">
                  Select all
                </button>
                {olderThanRetention.length > 0 && (
                  <button onClick={() => setSelected(new Set(olderThanRetention.map((b) => b.bundle)))}
                    className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase border pb-hairline text-pb-faint hover:text-pb-text">
                    Select older than {retention} days ({olderThanRetention.length})
                  </button>
                )}
                <button onClick={() => setSelected(new Set())} disabled={!selected.size}
                  className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-40">
                  Clear
                </button>
                <span className="flex-1" />
                <span className="font-mono text-[10px] text-pb-faint">
                  {selected.size} selected · {fmtBytes(selectedBytes)}
                </span>
                <button onClick={() => setConfirming(true)} disabled={!selected.size}
                  className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 uppercase font-semibold bg-red-500/90 text-white disabled:opacity-40">
                  Delete selected
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                      <th className="px-2 py-2 w-8"></th>
                      <th className="px-3 py-2">Backup</th>
                      <th className="px-3 py-2">Age</th>
                      <th className="px-3 py-2">Size</th>
                      <th className="px-3 py-2">Files</th>
                      <th className="px-3 py-2">Triggered</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bundles.map((b) => {
                      const age = ageInDays(b.bundle)
                      const beyond = retention != null && age != null && age > retention
                      return (
                        <tr key={b.bundle}
                          className={`border-b pb-hairline ${selected.has(b.bundle) ? 'bg-pb-surface2/50' : ''}`}>
                          <td className="px-2 py-2">
                            <input type="checkbox" checked={selected.has(b.bundle)}
                              onChange={() => toggle(b.bundle)} />
                          </td>
                          <td className="px-3 py-2">
                            <span className="text-pb-text">{fmtPerth(bundleDate(b.bundle)?.toISOString())}</span>
                            <span className="block font-mono text-[10px] text-pb-faintest">{b.bundle}</span>
                            {!b.complete && (
                              <span className="font-mono text-[10px] text-amber-300">
                                incomplete — no database dump in this bundle
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap text-pb-dim">
                            {age == null ? '-' : `${age} day${age === 1 ? '' : 's'}`}
                            {beyond && (
                              <span className="block font-mono text-[10px] text-pb-faint">past retention</span>
                            )}
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap text-pb-dim">{fmtBytes(b.size_bytes)}</td>
                          <td className="px-3 py-2 text-pb-faint font-mono text-[10px]">
                            {b.files.map((f) => f.name).join(', ') || '-'}
                          </td>
                          <td className="px-3 py-2 text-pb-dim whitespace-nowrap">
                            {b.triggered_by || <span className="text-pb-faintest">not logged</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {files && bundles.length === 0 && !filesErr && (
            <p className="text-sm text-pb-dim">
              No backup bundles on disk yet
              {files.root_missing && <> — the backup directory doesn't exist on the server</>}.
            </p>
          )}

          {files?.missing?.length > 0 && (
            <p className="font-mono text-[10px] text-pb-faintest mt-3">
              {files.missing.length} earlier run{files.missing.length === 1 ? '' : 's'} still
              listed on the Backups page {files.missing.length === 1 ? 'has' : 'have'} had their
              files removed (retention or a deletion here) — the history stays, the files are gone.
            </p>
          )}

          {deleteMsg && <p className="text-xs text-pb-dim mt-3">{deleteMsg}</p>}
        </div>
      </div>

      {confirming && (
        <DeleteConfirm
          bundles={selectedList}
          latest={latest}
          totalBytes={selectedBytes}
          busy={deleting}
          onCancel={() => setConfirming(false)}
          onConfirm={runDelete}
        />
      )}
    </AdminLayout>
  )
}
