import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../../contexts/AuthContext'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

function RegisterPanel({ onRegistered }) {
  const [playhqOrgId, setPlayhqOrgId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const register = async () => {
    if (!playhqOrgId.trim()) return
    setBusy(true)
    setError(null)
    try {
      const res = await aflApi.superCreateClub(playhqOrgId.trim())
      setPlayhqOrgId('')
      onRegistered(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pb-card p-4 space-y-3">
      <SectionTitle>Register a club</SectionTitle>
      <p className="text-sm text-pb-dim">
        Paste the PlayHQ org code, the hex code in a{' '}
        <code className="text-pb-text">playhq.com/afl/org/…/CODE</code> URL. Every
        side at the club is pulled in on the first sync.
      </p>
      {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
      <div className="flex gap-2">
        <input value={playhqOrgId} onChange={e => setPlayhqOrgId(e.target.value)} placeholder="e.g. d14445c4"
               className="bg-pb-surface2 border border-pb-hairline rounded px-3 py-2 text-sm flex-1" />
        <button disabled={busy || !playhqOrgId.trim()} onClick={register}
                className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
          {busy ? 'Registering…' : 'Register & sync'}
        </button>
      </div>
    </div>
  )
}

function ClubEditor({ club, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: club.name, short_name: club.short_name || '', slug: club.slug || '',
    primary_color: club.primary_color || '', accent_color: club.accent_color || '', is_active: club.is_active,
  })
  const [admins, setAdmins] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => { aflApi.superListClubAdmins(club.id).then(setAdmins).catch(() => setAdmins([])) }, [club.id])

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await aflApi.superPatchClub(club.id, form)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const archive = async () => {
    if (!window.confirm(`Archive ${club.name}? This hides it from the club list and its public site (reversible).`)) return
    setBusy(true)
    try {
      await aflApi.superArchiveClub(club.id)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const restore = async () => {
    setBusy(true)
    try {
      await aflApi.superRestoreClub(club.id)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const sync = async () => {
    setBusy(true)
    setError(null)
    try {
      await aflApi.superSyncClub(club.id)
      window.alert('Sync started.')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const makePrimary = async (userId) => {
    setBusy(true)
    setError(null)
    try {
      await aflApi.superSetPrimaryAdmin(club.id, userId)
      aflApi.superListClubAdmins(club.id).then(setAdmins).catch(() => {})
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="pb-card p-5 w-full max-w-lg space-y-4 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <SectionTitle>{club.name}</SectionTitle>
        {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}

        <div className="grid grid-cols-2 gap-2">
          <label className="block text-xs text-pb-faint col-span-2">Name
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                   className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          </label>
          <label className="block text-xs text-pb-faint">Short name
            <input value={form.short_name} onChange={e => setForm(f => ({ ...f, short_name: e.target.value }))}
                   className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          </label>
          <label className="block text-xs text-pb-faint">Slug
            <input value={form.slug} onChange={e => setForm(f => ({ ...f, slug: e.target.value }))}
                   className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          </label>
          <label className="block text-xs text-pb-faint">Primary colour
            <input type="color" value={form.primary_color || '#16c784'} onChange={e => setForm(f => ({ ...f, primary_color: e.target.value }))}
                   className="mt-1 w-full h-9 bg-pb-surface2 border border-pb-hairline rounded" />
          </label>
          <label className="block text-xs text-pb-faint">Accent colour
            <input type="color" value={form.accent_color || '#243352'} onChange={e => setForm(f => ({ ...f, accent_color: e.target.value }))}
                   className="mt-1 w-full h-9 bg-pb-surface2 border border-pb-hairline rounded" />
          </label>
          <label className="flex items-center gap-2 text-sm text-pb-text col-span-2 mt-1">
            <input type="checkbox" checked={!!form.is_active} onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))} />
            Public site active
          </label>
        </div>

        <div>
          <SectionTitle>Primary admin</SectionTitle>
          {admins === null ? <p className="text-xs text-pb-faint">Loading…</p> : (
            <div className="space-y-1">
              {admins.map(a => (
                <div key={a.user_id} className="flex items-center justify-between text-sm">
                  <span>{a.display_name} {a.is_primary_admin && <span className="text-[var(--pb-accent)] text-xs ml-1">(primary)</span>}</span>
                  {!a.is_primary_admin && (
                    <button disabled={busy} onClick={() => makePrimary(a.user_id)} className="text-xs text-pb-dim hover:text-pb-text underline">
                      Make primary
                    </button>
                  )}
                </div>
              ))}
              {admins.length === 0 && <p className="text-xs text-pb-faint">No admins yet.</p>}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 pb-hairline-t">
          <div className="flex gap-2">
            <button disabled={busy} onClick={sync} className="px-3 py-1.5 rounded text-sm border border-pb-hairline text-pb-text hover:bg-pb-surface2">
              Sync now
            </button>
            {club.archived
              ? <button disabled={busy} onClick={restore} className="px-3 py-1.5 rounded text-sm border border-pb-hairline text-pb-text hover:bg-pb-surface2">Restore</button>
              : <button disabled={busy} onClick={archive} className="px-3 py-1.5 rounded text-sm text-[var(--pb-negative)] border border-pb-hairline hover:bg-pb-surface2">Archive</button>}
          </div>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1.5 text-sm text-pb-dim hover:text-pb-text">Close</button>
            <button disabled={busy} onClick={save} className="px-4 py-1.5 rounded font-semibold text-sm bg-[var(--pb-accent)] text-black disabled:opacity-50">
              {busy ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function AflAdminSuperClubs() {
  const { user: me } = useAuth()
  const [data, setData] = useState(null)
  const [q, setQ] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [editing, setEditing] = useState(null)

  const refresh = () => aflApi.superListClubs({ q, include_archived: showArchived }).then(setData).catch(() => setData({ clubs: [] }))
  useEffect(() => { refresh() }, [q, showArchived]) // eslint-disable-line react-hooks/exhaustive-deps

  if (me && me.role !== 'super_admin') return <Navigate to="/admin" replace />

  return (
    <div className="space-y-6">
      <SectionTitle>All Clubs {data ? `(${data.total ?? data.clubs.length})` : ''}</SectionTitle>

      <RegisterPanel onRegistered={() => refresh()} />

      <div className="flex items-center gap-3 flex-wrap">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search clubs…"
               className="bg-pb-surface2 border border-pb-hairline rounded px-3 py-1.5 text-sm flex-1 min-w-[200px]" />
        <label className="flex items-center gap-2 text-sm text-pb-dim">
          <input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)} />
          Show archived
        </label>
      </div>

      {data === null ? <p className="text-sm text-pb-faint">Loading…</p> : (
        <div className="pb-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="pb-hairline-b">
              <tr>
                {['Club', 'Admin', 'Status', 'Last sync', ''].map(h => (
                  <th key={h} className="px-2 py-1.5 text-left font-mono text-[10px] uppercase text-pb-faint">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.clubs.map(c => (
                <tr key={c.id} className="pb-hairline-b last:border-0">
                  <td className="px-2 py-1.5 font-medium">{c.name}{c.archived && <span className="ml-2 text-xs text-pb-faint">(archived)</span>}</td>
                  <td className="px-2 py-1.5 text-pb-faint">{c.admin_name || '—'}</td>
                  <td className="px-2 py-1.5">
                    <span className={c.is_active ? 'text-[var(--pb-positive)]' : 'text-pb-faint'}>{c.is_active ? 'Active' : 'Inactive'}</span>
                  </td>
                  <td className="px-2 py-1.5 text-pb-faint">
                    {c.last_sync_at ? `${c.last_sync_at.replace('T', ' ').slice(0, 16)} · ${c.last_sync_status}` : 'Never'}
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <button onClick={() => setEditing(c)} className="text-xs text-pb-dim hover:text-pb-text underline">Manage</button>
                  </td>
                </tr>
              ))}
              {data.clubs.length === 0 && (
                <tr><td colSpan={5} className="px-2 py-3 text-pb-faint">No clubs found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {editing && <ClubEditor club={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh() }} />}
    </div>
  )
}
