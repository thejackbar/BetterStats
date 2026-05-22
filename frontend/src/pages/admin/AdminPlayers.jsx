import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import ImageEditorModal from '../../components/ImageEditorModal'
import { nameMatchesSearch, formatPlayerName } from '../../lib/nameFormat'

// ---------------------------------------------------------------------------
// EditPlayerModal
// ---------------------------------------------------------------------------

function EditPlayerModal({ player, onClose, onSaved, nameFormat }) {
  const [form, setForm] = useState({
    display_name_override: player.display_name_override || '',
    gender: player.gender || '',
    is_player: player.is_player !== false, // default true
    player_role: player.player_role || '',
    playhq_id: player.playhq_id || '',
  })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [msgError, setMsgError] = useState(false)
  const [uploadingPhoto, setUploadingPhoto] = useState(false)
  const [photoUrl, setPhotoUrl] = useState(player.photo_url || null)
  const [editorSource, setEditorSource] = useState(null)

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const setSuccess = (text) => {
    setMsgError(false)
    setMsg(text)
    setTimeout(() => setMsg(''), 2500)
  }

  const setError = (text) => {
    setMsgError(true)
    setMsg(text)
  }

  const handleSave = async () => {
    setSaving(true)
    setMsg('')
    try {
      const payload = {
        display_name_override: form.display_name_override,
        gender: form.gender,
        is_player: form.is_player,
        player_role: form.player_role,
        playhq_id: form.playhq_id,
      }
      const updated = await api.adminPatchPlayer(player.id, payload)
      onSaved({ ...player, ...updated, photo_url: photoUrl })
      setSuccess('Saved')
    } catch (err) {
      setError(err.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handlePhotoUpload = async (file) => {
    if (!file) return
    setUploadingPhoto(true)
    setMsg('')
    try {
      const result = await api.adminUploadPlayerPhoto(player.id, file)
      setPhotoUrl(result.photo_url)
      onSaved({ ...player, photo_url: result.photo_url })
      setSuccess('Photo saved')
    } catch (err) {
      setError(err.message || 'Upload failed')
    } finally {
      setUploadingPhoto(false)
    }
  }

  const handlePhotoDelete = async () => {
    setUploadingPhoto(true)
    setMsg('')
    try {
      await api.adminDeletePlayerPhoto(player.id)
      setPhotoUrl(null)
      onSaved({ ...player, photo_url: null })
      setSuccess('Photo removed')
    } catch (err) {
      setError(err.message || 'Delete failed')
    } finally {
      setUploadingPhoto(false)
    }
  }

  const displayedName = player.display_name_override || formatPlayerName(player.name, nameFormat)

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60"
      style={{ backdropFilter: 'blur(2px)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-pb-surface pb-card max-w-md w-full mx-4 mt-16 mb-8 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b pb-hairline-b">
          <div>
            <p className="text-pb-text text-sm font-semibold">{displayedName}</p>
            <p className="font-mono text-[10px] text-pb-faintest mt-0.5">{player.id}</p>
          </div>
          <button
            onClick={onClose}
            className="text-pb-faint hover:text-pb-text transition-colors font-mono text-[11px] px-2 py-1"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">

          {/* Display Name */}
          <div>
            <label className="font-mono text-[10px] text-pb-faintest block mb-1">Display Name</label>
            <input
              type="text"
              value={form.display_name_override}
              onChange={e => setForm(f => ({ ...f, display_name_override: e.target.value }))}
              placeholder="Blank to use synced name"
              className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
            />
          </div>

          {/* Gender + Is Player row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="font-mono text-[10px] text-pb-faintest block mb-1">Gender</label>
              <select
                value={form.gender}
                onChange={e => setForm(f => ({ ...f, gender: e.target.value }))}
                className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
              >
                <option value="">—</option>
                <option value="Male">Male</option>
                <option value="Female">Female</option>
              </select>
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faintest block mb-1">Type</label>
              <label className="flex items-center gap-2 cursor-pointer mt-1.5">
                <input
                  type="checkbox"
                  checked={form.is_player}
                  onChange={e => setForm(f => ({ ...f, is_player: e.target.checked }))}
                  className="accent-pb-accent"
                />
                <span className="font-mono text-[10px] text-pb-text">
                  {form.is_player ? 'Player' : 'Non-Player (coach/scorer/official)'}
                </span>
              </label>
            </div>
          </div>

          {/* Role */}
          <div>
            <label className="font-mono text-[10px] text-pb-faintest block mb-1">Role</label>
            <select
              value={form.player_role}
              onChange={e => setForm(f => ({ ...f, player_role: e.target.value }))}
              className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
            >
              <option value="">—</option>
              <option value="Batter">Batter</option>
              <option value="Bowler">Bowler</option>
              <option value="Wicketkeeper">Wicketkeeper</option>
              <option value="All Rounder">All Rounder</option>
            </select>
          </div>

          {/* PlayHQ ID */}
          <div>
            <label className="font-mono text-[10px] text-pb-faintest block mb-1">PlayHQ ID</label>
            <input
              type="text"
              value={form.playhq_id}
              onChange={e => setForm(f => ({ ...f, playhq_id: e.target.value }))}
              placeholder="e.g. a1b2c3d4-e5f6-..."
              className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm font-mono focus:outline-none"
              style={{ '--tw-border-opacity': 1 }}
            />
          </div>

          {/* Photo */}
          <div>
            <label className="font-mono text-[10px] text-pb-faintest block mb-2">Photo</label>
            <div className="flex items-center gap-3">
              {photoUrl && (
                <img
                  src={photoUrl}
                  alt="Player"
                  className="w-12 h-12 rounded object-cover border pb-hairline"
                />
              )}
              <div className="flex items-center gap-2 flex-wrap">
                <label
                  className={`font-mono text-[10px] px-3 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text cursor-pointer transition-colors ${uploadingPhoto ? 'opacity-50 pointer-events-none' : ''}`}
                >
                  {uploadingPhoto ? '…' : (photoUrl ? 'Replace' : 'Upload photo')}
                  <input
                    type="file"
                    accept=".jpg,.jpeg,.png,.webp,.gif"
                    className="hidden"
                    onChange={e => {
                      const f = e.target.files?.[0]
                      e.target.value = ''
                      if (f) setEditorSource(f)
                    }}
                  />
                </label>
                {photoUrl && (
                  <>
                    <button
                      onClick={() => setEditorSource(photoUrl)}
                      disabled={uploadingPhoto}
                      className="font-mono text-[10px] px-3 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text transition-colors disabled:opacity-50"
                    >
                      Edit
                    </button>
                    <button
                      onClick={handlePhotoDelete}
                      disabled={uploadingPhoto}
                      className="font-mono text-[10px] px-3 py-1.5 rounded border pb-hairline text-pb-faintest hover:text-pb-red transition-colors disabled:opacity-50"
                    >
                      Remove
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>

          <ImageEditorModal
            open={!!editorSource}
            source={editorSource}
            title="Edit Player Photo"
            aspect={1}
            outputType="image/png"
            outputName={`player-${player.id}.png`}
            onCancel={() => setEditorSource(null)}
            onApply={async (file) => {
              setEditorSource(null)
              await handlePhotoUpload(file)
            }}
          />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t pb-hairline-t">
          <div>
            {msg && (
              <span
                className="font-mono text-[10px] tracking-wide"
                style={{ color: msgError ? 'var(--pb-red)' : 'var(--pb-accent)' }}
              >
                {msg.toUpperCase()}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
            >
              CLOSE
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50"
              style={{ background: 'var(--pb-accent)' }}
            >
              {saving ? 'SAVING…' : 'SAVE'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// AdminPlayers
// ---------------------------------------------------------------------------

export default function AdminPlayers() {
  const [players, setPlayers] = useState([])
  const [filter, setFilter] = useState('')
  const [msg, setMsg] = useState('')
  const [nameFormat, setNameFormat] = useState('last_first')
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({ first_name: '', last_name: '', playhq_id: '', display_name_override: '' })
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState('')
  const [editingPlayer, setEditingPlayer] = useState(null) // player object or null

  useEffect(() => {
    api.adminListPlayers().then(setPlayers).catch(() => {})
    api.adminGetSettings().then(s => setNameFormat(s.player_name_format || 'last_first')).catch(() => {})
  }, [])

  const fmt = (name) => formatPlayerName(name, nameFormat)

  const filtered = players.filter(p => {
    const q = filter.trim()
    if (!q) return true
    return (
      nameMatchesSearch(p.name, q) ||
      nameMatchesSearch(p.display_name_override, q) ||
      (p.playhq_id || '').toLowerCase().includes(q.toLowerCase())
    )
  })

  const handleModalSaved = useCallback((updated) => {
    setPlayers(ps => ps.map(p => p.id === updated.id ? { ...p, ...updated } : p))
    // If modal is still open, keep it open — user closed it themselves
  }, [])

  const handleModalClose = useCallback(() => {
    setEditingPlayer(null)
  }, [])

  const submitCreate = async (e) => {
    e.preventDefault()
    setCreating(true)
    setCreateMsg('')
    try {
      const payload = {
        first_name: createForm.first_name.trim(),
        last_name: createForm.last_name.trim(),
        playhq_id: createForm.playhq_id.trim() || null,
        display_name_override: createForm.display_name_override.trim() || null,
      }
      const created = await api.adminCreatePlayer(payload)
      setPlayers(ps => [...ps, created].sort((a, b) => a.name.localeCompare(b.name)))
      setCreateForm({ first_name: '', last_name: '', playhq_id: '', display_name_override: '' })
      setShowCreate(false)
      setMsg('Player created')
      setTimeout(() => setMsg(''), 2500)
    } catch (err) {
      setCreateMsg(err.message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <AdminLayout>
      {editingPlayer && (
        <EditPlayerModal
          player={editingPlayer}
          onClose={handleModalClose}
          onSaved={handleModalSaved}
          nameFormat={nameFormat}
        />
      )}

      <div className="max-w-4xl">
        <div className="flex items-center justify-between mb-5">
          <h1 className="font-display font-bold text-2xl text-pb-text">Players</h1>
          <div className="flex items-center gap-3">
            {msg && <span className="font-mono text-[11px] tracking-wide2" style={{ color: 'var(--pb-accent)' }}>{msg.toUpperCase()}</span>}
            <button
              onClick={() => { setShowCreate(v => !v); setCreateMsg('') }}
              className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {showCreate ? 'CANCEL' : '+ ADD PLAYER'}
            </button>
          </div>
        </div>

        {showCreate && (
          <form onSubmit={submitCreate} className="pb-card px-5 py-4 mb-4">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">New Player</p>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label className="font-mono text-[10px] text-pb-faintest block mb-1">First Name *</label>
                <input
                  autoFocus
                  type="text"
                  value={createForm.first_name}
                  onChange={e => setCreateForm(f => ({ ...f, first_name: e.target.value }))}
                  required
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  placeholder="e.g. John"
                />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faintest block mb-1">Last Name *</label>
                <input
                  type="text"
                  value={createForm.last_name}
                  onChange={e => setCreateForm(f => ({ ...f, last_name: e.target.value }))}
                  required
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  placeholder="e.g. Smith"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label className="font-mono text-[10px] text-pb-faintest block mb-1">PlayHQ ID (optional)</label>
                <input
                  type="text"
                  value={createForm.playhq_id}
                  onChange={e => setCreateForm(f => ({ ...f, playhq_id: e.target.value }))}
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm font-mono focus:outline-none focus:border-pb-amber"
                  style={{ '--tw-border-opacity': 1 }}
                  placeholder="e.g. a1b2c3d4-e5f6-..."
                />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faintest block mb-1">Display name override (optional)</label>
                <input
                  type="text"
                  value={createForm.display_name_override}
                  onChange={e => setCreateForm(f => ({ ...f, display_name_override: e.target.value }))}
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  placeholder="Custom display name"
                />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={creating}
                className="px-4 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50"
                style={{ background: 'var(--pb-accent)' }}
              >
                {creating ? 'CREATING…' : 'CREATE PLAYER'}
              </button>
              {createMsg && <span className="font-mono text-[11px] text-pb-red">{createMsg}</span>}
            </div>
          </form>
        )}

        <div className="relative mb-4">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-pb-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Search by name (any order), display name or PHQ ID…"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="w-full bg-pb-surface border pb-hairline rounded pl-9 pr-4 py-2.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent placeholder-pb-faintest"
          />
        </div>

        <p className="font-mono text-[10px] text-pb-faint mb-4">
          Click <span style={{ color: 'var(--pb-accent)' }}>Edit</span> on any player to update their display name, gender, role, PlayHQ ID, or photo.
        </p>

        <div className="pb-card overflow-hidden">
          {filtered.length === 0 && (
            <div className="px-5 py-8 text-center text-pb-faint font-mono text-[11px]">No players found</div>
          )}
          {filtered.map((p, i) => (
            <div key={p.id} className={`px-5 py-3.5 flex items-start justify-between gap-2 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <div className="min-w-0 flex items-center gap-3">
                {p.photo_url && (
                  <img
                    src={p.photo_url}
                    alt=""
                    className="w-8 h-8 rounded-full object-cover shrink-0 border pb-hairline"
                  />
                )}
                <div>
                  <p className="text-pb-text text-sm font-medium">
                    {p.display_name_override || fmt(p.name)}
                    {p.display_name_override && (
                      <span className="ml-2 font-mono text-[10px] text-pb-faint">(raw: {p.name})</span>
                    )}
                  </p>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5">
                    <span className="font-mono text-[10px] text-pb-faintest">{p.id}</span>
                    {p.playhq_id ? (
                      <span className="font-mono text-[10px] text-pb-amber/70">PHQ: {p.playhq_id}</span>
                    ) : (
                      <span className="font-mono text-[10px] text-pb-faintest italic">no PHQ ID</span>
                    )}
                    {p.gender && (
                      <span className="font-mono text-[10px] text-pb-faint">{p.gender}</span>
                    )}
                    {p.player_role && (
                      <span className="font-mono text-[10px] text-pb-faint">{p.player_role}</span>
                    )}
                    {p.is_player === false && (
                      <span className="font-mono text-[10px] text-pb-faintest italic">non-player</span>
                    )}
                  </div>
                </div>
              </div>

              <button
                onClick={() => setEditingPlayer(p)}
                className="font-mono text-[10px] px-3 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text transition-colors shrink-0"
              >
                Edit
              </button>
            </div>
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
