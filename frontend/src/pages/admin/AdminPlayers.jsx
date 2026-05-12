import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

export default function AdminPlayers() {
  const [players, setPlayers] = useState([])
  const [filter, setFilter] = useState('')
  const [editing, setEditing] = useState(null) // { id, field, value }
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.adminListPlayers().then(setPlayers).catch(() => {})
  }, [])

  const filtered = players.filter(p =>
    p.name.toLowerCase().includes(filter.toLowerCase()) ||
    (p.display_name_override || '').toLowerCase().includes(filter.toLowerCase()) ||
    (p.playhq_id || '').toLowerCase().includes(filter.toLowerCase())
  )

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

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-display font-bold text-white">Players</h1>
          {msg && <span className="text-sm text-accent">{msg}</span>}
        </div>

        <input
          type="text"
          placeholder="Filter by name, display name or PHQ ID…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm mb-4 focus:outline-none focus:border-accent"
        />

        <p className="text-slate-500 text-xs mb-3">
          <span className="text-accent font-medium">Display name</span> adds a suffix without affecting sync.{' '}
          <span className="text-accent font-medium">PHQ ID</span> links a player to their PlayHQ UUID for precise game-level matching.
          Use Admin → PHQ ID Match to auto-detect IDs.
        </p>

        <div className="bg-navy-900 border border-navy-700 rounded-lg overflow-hidden">
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-slate-500 text-sm">No players found</div>
          )}
          {filtered.map((p, i) => (
            <div key={p.id} className={`px-4 py-3 ${i > 0 ? 'border-t border-navy-800' : ''}`}>
              {/* Display name edit row */}
              {editing?.id === p.id && editing.field === 'display_name' ? (
                <div className="flex items-center gap-2 mb-2">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-slate-500 mb-1">Display name override</div>
                    <input
                      autoFocus
                      type="text"
                      value={editing.value}
                      onChange={e => setEditing(ed => ({ ...ed, value: e.target.value }))}
                      placeholder="Blank to clear"
                      className="w-full bg-navy-800 border border-accent rounded px-2 py-1 text-white text-sm focus:outline-none"
                      onKeyDown={e => { if (e.key === 'Enter') saveEdit(); if (e.key === 'Escape') setEditing(null) }}
                    />
                  </div>
                  <button onClick={saveEdit} disabled={saving} className="btn-primary text-sm">Save</button>
                  <button onClick={() => setEditing(null)} className="btn-ghost text-sm">Cancel</button>
                </div>
              ) : editing?.id === p.id && editing.field === 'playhq_id' ? (
                <div className="flex items-center gap-2 mb-2">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-slate-500 mb-1">PlayHQ ID (UUID)</div>
                    <input
                      autoFocus
                      type="text"
                      value={editing.value}
                      onChange={e => setEditing(ed => ({ ...ed, value: e.target.value }))}
                      placeholder="e.g. a1b2c3d4-e5f6-..."
                      className="w-full bg-navy-800 border border-amber-500 rounded px-2 py-1 text-white text-sm font-mono focus:outline-none"
                      onKeyDown={e => { if (e.key === 'Enter') saveEdit(); if (e.key === 'Escape') setEditing(null) }}
                    />
                  </div>
                  <button onClick={saveEdit} disabled={saving} className="btn-primary text-sm">Save</button>
                  <button onClick={() => setEditing(null)} className="btn-ghost text-sm">Cancel</button>
                </div>
              ) : (
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    {/* Name row */}
                    <div className="text-white text-sm">
                      {p.display_name}
                      {p.display_name_override && (
                        <span className="ml-2 text-xs text-slate-500">(PlayHQ: {p.name})</span>
                      )}
                    </div>
                    {/* ID row */}
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5">
                      <span className="font-mono text-xs text-slate-700" title="Internal player ID">{p.id}</span>
                      {p.playhq_id ? (
                        <span className="font-mono text-xs text-amber-500/80" title="PlayHQ player UUID">
                          PHQ: {p.playhq_id}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-700 italic">no PHQ ID</span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-1 shrink-0 flex-wrap justify-end">
                    <button
                      onClick={() => startEdit(p, 'display_name')}
                      className="text-slate-400 hover:text-white text-xs px-2 py-1"
                    >
                      Name
                    </button>
                    {p.display_name_override && (
                      <button
                        onClick={() => clearField(p.id, 'display_name')}
                        className="text-slate-600 hover:text-red-400 text-xs px-2 py-1"
                      >
                        ✕ name
                      </button>
                    )}
                    <button
                      onClick={() => startEdit(p, 'playhq_id')}
                      className={`text-xs px-2 py-1 ${p.playhq_id ? 'text-amber-500/70 hover:text-amber-400' : 'text-slate-400 hover:text-amber-400'}`}
                    >
                      {p.playhq_id ? 'Edit PHQ' : 'Set PHQ'}
                    </button>
                    {p.playhq_id && (
                      <button
                        onClick={() => clearField(p.id, 'playhq_id')}
                        className="text-slate-600 hover:text-red-400 text-xs px-2 py-1"
                      >
                        ✕ PHQ
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
