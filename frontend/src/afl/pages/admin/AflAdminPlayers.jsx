import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { aflApi, mediaUrl } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

/** Photo, or the player's initials while there isn't one. */
function Avatar({ player, size = 'h-9 w-9', text = 'text-[11px]' }) {
  const initials = (player.display_name || '?')
    .replace(',', '').split(/\s+/).filter(Boolean).map(w => w[0]).join('').toUpperCase().slice(0, 2)
  if (!player.photo_url) {
    return (
      <span className={`${size} ${text} rounded-full bg-pb-surface2 flex items-center justify-center text-pb-faint shrink-0`}>
        {initials}
      </span>
    )
  }
  return <img src={mediaUrl(player.photo_url)} alt="" className={`${size} rounded-full object-cover shrink-0`} />
}

/**
 * Upload / replace / remove one player's photo.
 *
 * Saves immediately on choosing a file rather than joining the drawer's Save
 * button: the photo is a separate multipart endpoint, so tying it to the
 * form's own save would mean one of the two silently landing without the
 * other whenever a request failed.
 */
function PhotoField({ player, onChanged }) {
  const fileRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [photoUrl, setPhotoUrl] = useState(player.photo_url || null)

  const pick = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''            // so re-picking the same file fires again
    if (!file) return
    setBusy(true); setError(null)
    try {
      const res = await aflApi.adminUploadPlayerPhoto(player.id, file)
      setPhotoUrl(res.photo_url)
      onChanged?.(res.photo_url)
    } catch (err) {
      setError(err.message)
    } finally { setBusy(false) }
  }

  const remove = async () => {
    setBusy(true); setError(null)
    try {
      await aflApi.adminDeletePlayerPhoto(player.id)
      setPhotoUrl(null)
      onChanged?.(null)
    } catch (err) {
      setError(err.message)
    } finally { setBusy(false) }
  }

  return (
    <div>
      <span className="block text-xs text-pb-faint mb-1.5">Photo</span>
      <div className="flex items-center gap-3">
        <Avatar player={{ ...player, photo_url: photoUrl }} size="h-16 w-16" text="text-lg" />
        <div className="flex flex-col gap-1.5">
          <div className="flex gap-2">
            <button type="button" disabled={busy} onClick={() => fileRef.current?.click()}
              className="px-3 py-1.5 rounded text-xs border border-pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-50">
              {busy ? 'Uploading…' : photoUrl ? 'Replace' : 'Upload photo'}
            </button>
            {photoUrl && (
              <button type="button" disabled={busy} onClick={remove}
                className="px-3 py-1.5 rounded text-xs text-pb-dim hover:text-[var(--pb-negative)] disabled:opacity-50">
                Remove
              </button>
            )}
          </div>
          <span className="text-[11px] text-pb-faintest">JPG, PNG, WEBP or GIF, up to 2 MB.</span>
        </div>
      </div>
      <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif"
             className="hidden" onChange={pick} />
      {error && <p className="text-xs text-[var(--pb-negative)] mt-1.5">{error}</p>}
    </div>
  )
}

function EditDrawer({ player, onClose, onSaved, onPhotoChanged }) {
  const [form, setForm] = useState({
    display_name_override: player.display_name_override || '',
    playhq_id: player.playhq_id || '',
    gender: player.gender || '',
    email: player.email || '',
    phone: player.phone || '',
    status: player.status || 'active',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await aflApi.adminPatchPlayer(player.id, form)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="pb-card p-5 w-full max-w-md space-y-3 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <SectionTitle>Edit {player.display_name}</SectionTitle>
        {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
        <PhotoField player={player} onChanged={onPhotoChanged} />
        <label className="block text-xs text-pb-faint">Display name override
          <input value={form.display_name_override} onChange={e => setForm(f => ({ ...f, display_name_override: e.target.value }))}
                 className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
        </label>
        <label className="block text-xs text-pb-faint">PlayHQ ID
          <input value={form.playhq_id} onChange={e => setForm(f => ({ ...f, playhq_id: e.target.value }))}
                 className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
        </label>
        <label className="block text-xs text-pb-faint">Email
          <input value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                 className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
        </label>
        <label className="block text-xs text-pb-faint">Phone
          <input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
                 className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
        </label>
        <label className="block text-xs text-pb-faint">Gender
          <select value={form.gender} onChange={e => setForm(f => ({ ...f, gender: e.target.value }))}
                  className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
            <option value="">—</option>
            <option value="male">Male</option>
            <option value="female">Female</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="block text-xs text-pb-faint">Status
          <select value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}
                  className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-pb-dim hover:text-pb-text">Cancel</button>
          <button disabled={saving} onClick={save}
                  className="px-4 py-1.5 rounded font-semibold text-sm bg-[var(--pb-accent)] text-black disabled:opacity-50">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

function CreateDrawer({ onClose, onSaved }) {
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await aflApi.adminCreatePlayer({ first_name: firstName, last_name: lastName })
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="pb-card p-5 w-full max-w-sm space-y-3" onClick={e => e.stopPropagation()}>
        <SectionTitle>Add a player</SectionTitle>
        {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
        <label className="block text-xs text-pb-faint">First name
          <input value={firstName} onChange={e => setFirstName(e.target.value)}
                 className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
        </label>
        <label className="block text-xs text-pb-faint">Last name
          <input value={lastName} onChange={e => setLastName(e.target.value)}
                 className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-pb-dim hover:text-pb-text">Cancel</button>
          <button disabled={saving || !firstName.trim() || !lastName.trim()} onClick={save}
                  className="px-4 py-1.5 rounded font-semibold text-sm bg-[var(--pb-accent)] text-black disabled:opacity-50">
            {saving ? 'Adding…' : 'Add player'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AflAdminPlayers() {
  const [players, setPlayers] = useState(null)
  const [q, setQ] = useState('')
  const [editing, setEditing] = useState(null)
  const [creating, setCreating] = useState(false)

  const refresh = () => aflApi.adminListPlayers().then(setPlayers).catch(() => setPlayers([]))
  useEffect(() => { refresh() }, [])

  const filtered = useMemo(() => {
    if (!players) return []
    const needle = q.trim().toLowerCase()
    if (!needle) return players
    return players.filter(p => (p.display_name || '').toLowerCase().includes(needle))
  }, [players, q])

  if (players === null) return <p className="text-sm text-pb-faint">Loading…</p>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <SectionTitle right={
          <div className="flex gap-2">
            <Link to="/admin/players/import" className="px-3 py-1.5 rounded text-sm border border-pb-hairline text-pb-text hover:bg-pb-surface2">
              Import Players
            </Link>
            <button onClick={() => setCreating(true)} className="px-3 py-1.5 rounded text-sm font-semibold bg-[var(--pb-accent)] text-black">
              + Add player
            </button>
          </div>
        }>Players ({players.length})</SectionTitle>
      </div>
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search players…"
             className="w-full max-w-xs bg-pb-surface2 border border-pb-hairline rounded px-3 py-1.5 text-sm" />

      <div className="pb-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="pb-hairline-b">
            <tr>
              <th className="px-3 py-2 w-10" />
              {['Name', 'Games', 'Goals', 'Behinds', 'BOGs', 'Status', ''].map((h, i) => (
                <th key={h} className={`px-3 py-2 font-mono text-[10px] uppercase text-pb-faint ${i > 0 && i < 5 ? 'text-right' : 'text-left'}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map(p => (
              <tr key={p.id} className="pb-hairline-b last:border-0 hover:bg-pb-surface2/50">
                <td className="px-3 py-1.5"><Avatar player={p} /></td>
                <td className="px-3 py-2 font-medium">{p.display_name}</td>
                <td className="px-3 py-2 text-right pb-num">{p.games}</td>
                <td className="px-3 py-2 text-right pb-num">{p.goals}</td>
                <td className="px-3 py-2 text-right pb-num">{p.behinds}</td>
                <td className="px-3 py-2 text-right pb-num">{p.bogs}</td>
                <td className="px-3 py-2">
                  <span className={p.status === 'inactive' ? 'text-pb-faint' : 'text-[var(--pb-positive)]'}>{p.status}</span>
                </td>
                <td className="px-3 py-2 text-right">
                  <button onClick={() => setEditing(p)} className="text-xs text-pb-dim hover:text-pb-text underline">Edit</button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-4 text-pb-faint">No players found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {editing && (
        <EditDrawer
          player={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); refresh() }}
          // The photo saves on its own, so the row behind the drawer is
          // updated as it happens — closing with Cancel still leaves the
          // list showing the photo that was actually uploaded.
          onPhotoChanged={(photo_url) => setPlayers(ps =>
            (ps || []).map(p => (p.id === editing.id ? { ...p, photo_url } : p)))}
        />
      )}
      {creating && <CreateDrawer onClose={() => setCreating(false)} onSaved={() => { setCreating(false); refresh() }} />}
    </div>
  )
}
