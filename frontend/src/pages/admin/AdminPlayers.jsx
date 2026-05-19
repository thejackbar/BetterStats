import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { nameMatchesSearch, formatPlayerName } from '../../lib/nameFormat'

export default function AdminPlayers() {
  const [players, setPlayers] = useState([])
  const [filter, setFilter] = useState('')
  const [editing, setEditing] = useState(null) // { id, field, value }
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [nameFormat, setNameFormat] = useState('last_first')
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({ first_name: '', last_name: '', playhq_id: '', display_name_override: '' })
  const [creating, setCreating] = useState(false)
  const [createMsg, setCreateMsg] = useState('')
  const [uploadingPhotoFor, setUploadingPhotoFor] = useState(null) // player id

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

  const startEdit = (p, field) => setEditing({
    id: p.id,
    field,
    value: field === 'display_name' ? (p.display_name_override || '') : (p.playhq_id || ''),
  })

  const saveEdit = async () => {
    if (!editing) return
    setSaving(true)
    try {
      const payload = editing.field === 'display_name'
        ? { display_name_override: editing.value }
        : { playhq_id: editing.value }
      const updated = await api.adminPatchPlayer(editing.id, payload)
      setPlayers(ps => ps.map(p => p.id === editing.id ? { ...p, ...updated } : p))
      setEditing(null)
      setMsg('Saved')
      setTimeout(() => setMsg(''), 2000)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  const clearField = async (playerId, field) => {
    setSaving(true)
    try {
      const payload = field === 'display_name' ? { display_name_override: '' } : { playhq_id: '' }
      const updated = await api.adminPatchPlayer(playerId, payload)
      setPlayers(ps => ps.map(p => p.id === playerId ? { ...p, ...updated } : p))
      setMsg('Cleared')
      setTimeout(() => setMsg(''), 2000)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

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

  const handlePhotoUpload = async (playerId, file) => {
    if (!file) return
    setUploadingPhotoFor(playerId)
    try {
      const result = await api.adminUploadPlayerPhoto(playerId, file)
      setPlayers(ps => ps.map(p => p.id === playerId ? { ...p, photo_url: result.photo_url } : p))
      setMsg('Photo saved')
      setTimeout(() => setMsg(''), 2500)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setUploadingPhotoFor(null)
    }
  }

  const handlePhotoDelete = async (playerId) => {
    setUploadingPhotoFor(playerId)
    try {
      await api.adminDeletePlayerPhoto(playerId)
      setPlayers(ps => ps.map(p => p.id === playerId ? { ...p, photo_url: null } : p))
      setMsg('Photo removed')
      setTimeout(() => setMsg(''), 2500)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setUploadingPhotoFor(null)
    }
  }

  return (
    <AdminLayout>
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
          <span style={{ color: 'var(--pb-accent)' }}>Display name</span> adds a suffix without affecting sync.{' '}
          <span style={{ color: 'var(--pb-accent)' }}>PHQ ID</span> links a player to their PlayHQ UUID for precise game-level matching.
        </p>

        <div className="pb-card overflow-hidden">
          {filtered.length === 0 && (
            <div className="px-5 py-8 text-center text-pb-faint font-mono text-[11px]">No players found</div>
          )}
          {filtered.map((p, i) => (
            <div key={p.id} className={`px-5 py-3.5 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              {editing?.id === p.id && editing.field === 'display_name' ? (
                <div className="flex items-center gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-[10px] text-pb-faint mb-1">Display name override</p>
                    <input
                      autoFocus
                      type="text"
                      value={editing.value}
                      onChange={e => setEditing(ed => ({ ...ed, value: e.target.value }))}
                      placeholder="Blank to clear"
                      className="w-full bg-pb-surface2 border rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none"
                      style={{ borderColor: 'var(--pb-accent)' }}
                      onKeyDown={e => { if (e.key === 'Enter') saveEdit(); if (e.key === 'Escape') setEditing(null) }}
                    />
                  </div>
                  <button
                    onClick={saveEdit}
                    disabled={saving}
                    className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50"
                    style={{ background: 'var(--pb-accent)' }}
                  >
                    SAVE
                  </button>
                  <button onClick={() => setEditing(null)} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors">
                    CANCEL
                  </button>
                </div>
              ) : editing?.id === p.id && editing.field === 'playhq_id' ? (
                <div className="flex items-center gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-[10px] text-pb-faint mb-1">PlayHQ ID (UUID)</p>
                    <input
                      autoFocus
                      type="text"
                      value={editing.value}
                      onChange={e => setEditing(ed => ({ ...ed, value: e.target.value }))}
                      placeholder="e.g. a1b2c3d4-e5f6-..."
                      className="w-full bg-pb-surface2 border rounded px-2.5 py-1.5 text-pb-text text-sm font-mono focus:outline-none"
                      style={{ borderColor: 'var(--pb-amber)' }}
                      onKeyDown={e => { if (e.key === 'Enter') saveEdit(); if (e.key === 'Escape') setEditing(null) }}
                    />
                  </div>
                  <button
                    onClick={saveEdit}
                    disabled={saving}
                    className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50"
                    style={{ background: 'var(--pb-accent)' }}
                  >
                    SAVE
                  </button>
                  <button onClick={() => setEditing(null)} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors">
                    CANCEL
                  </button>
                </div>
              ) : (
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
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
                    </div>
                  </div>

                  <div className="flex items-center gap-1 shrink-0 flex-wrap justify-end">
                    <button
                      onClick={() => startEdit(p, 'display_name')}
                      className="font-mono text-[10px] text-pb-faint hover:text-pb-text px-2 py-1 transition-colors"
                    >
                      Name
                    </button>
                    {p.display_name_override && (
                      <button
                        onClick={() => clearField(p.id, 'display_name')}
                        className="font-mono text-[10px] text-pb-faintest hover:text-pb-red px-2 py-1 transition-colors"
                      >
                        ✕ name
                      </button>
                    )}
                    <button
                      onClick={() => startEdit(p, 'playhq_id')}
                      className={`font-mono text-[10px] px-2 py-1 transition-colors ${p.playhq_id ? 'text-pb-amber/70 hover:text-pb-amber' : 'text-pb-faint hover:text-pb-amber'}`}
                    >
                      {p.playhq_id ? 'Edit PHQ' : 'Set PHQ'}
                    </button>
                    {p.playhq_id && (
                      <button
                        onClick={() => clearField(p.id, 'playhq_id')}
                        className="font-mono text-[10px] text-pb-faintest hover:text-pb-red px-2 py-1 transition-colors"
                      >
                        ✕ PHQ
                      </button>
                    )}
                    <label
                      className={`font-mono text-[10px] px-2 py-1 transition-colors cursor-pointer ${p.photo_url ? 'text-pb-accent/70 hover:text-pb-accent' : 'text-pb-faint hover:text-pb-accent'} ${uploadingPhotoFor === p.id ? 'opacity-50 pointer-events-none' : ''}`}
                      title={p.photo_url ? 'Replace photo' : 'Upload photo'}
                    >
                      {uploadingPhotoFor === p.id ? '…' : (p.photo_url ? 'Photo ✓' : 'Photo')}
                      <input
                        type="file"
                        accept=".jpg,.jpeg,.png,.webp,.gif"
                        className="hidden"
                        onChange={e => handlePhotoUpload(p.id, e.target.files?.[0])}
                      />
                    </label>
                    {p.photo_url && (
                      <button
                        onClick={() => handlePhotoDelete(p.id)}
                        disabled={uploadingPhotoFor === p.id}
                        className="font-mono text-[10px] text-pb-faintest hover:text-pb-red px-2 py-1 transition-colors disabled:opacity-50"
                      >
                        ✕ photo
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
