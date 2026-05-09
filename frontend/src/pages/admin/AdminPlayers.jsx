import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

export default function AdminPlayers() {
  const [players, setPlayers] = useState([])
  const [filter, setFilter] = useState('')
  const [editing, setEditing] = useState(null) // { id, value }
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.adminListPlayers().then(setPlayers).catch(() => {})
  }, [])

  const filtered = players.filter(p =>
    p.name.toLowerCase().includes(filter.toLowerCase()) ||
    (p.display_name_override || '').toLowerCase().includes(filter.toLowerCase())
  )

  const startEdit = (p) => setEditing({ id: p.id, value: p.display_name_override || '' })

  const saveEdit = async () => {
    if (!editing) return
    setSaving(true)
    try {
      const updated = await api.adminPatchPlayer(editing.id, { display_name_override: editing.value })
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

  const clearOverride = async (playerId) => {
    setSaving(true)
    try {
      const updated = await api.adminPatchPlayer(playerId, { display_name_override: '' })
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
      <div className="max-w-3xl">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-display font-bold text-white">Players</h1>
          {msg && <span className="text-sm text-accent">{msg}</span>}
        </div>

        <input
          type="text"
          placeholder="Filter players…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm mb-4 focus:outline-none focus:border-accent"
        />

        <p className="text-slate-500 text-xs mb-3">
          Player names come from PlayHQ. Use the display name override to add a suffix (e.g. "Senior") without affecting sync.
        </p>

        <div className="bg-navy-900 border border-navy-700 rounded-lg overflow-hidden">
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-slate-500 text-sm">No players found</div>
          )}
          {filtered.map((p, i) => (
            <div key={p.id} className={`px-4 py-3 ${i > 0 ? 'border-t border-navy-800' : ''}`}>
              {editing?.id === p.id ? (
                <div className="flex items-center gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-slate-500 mb-1">PlayHQ name: {p.name}</div>
                    <input
                      autoFocus
                      type="text"
                      value={editing.value}
                      onChange={e => setEditing(ed => ({ ...ed, value: e.target.value }))}
                      placeholder="Display name override (blank to clear)"
                      className="w-full bg-navy-800 border border-accent rounded px-2 py-1 text-white text-sm focus:outline-none"
                      onKeyDown={e => { if (e.key === 'Enter') saveEdit(); if (e.key === 'Escape') setEditing(null) }}
                    />
                  </div>
                  <button onClick={saveEdit} disabled={saving} className="btn-primary text-sm">Save</button>
                  <button onClick={() => setEditing(null)} className="btn-ghost text-sm">Cancel</button>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-white text-sm">
                      {p.display_name}
                      {p.display_name_override && (
                        <span className="ml-2 text-xs text-slate-500">(PlayHQ: {p.name})</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="font-mono text-xs text-slate-600" title="Player ID">{p.id}</span>
                      {p.playhq_id
                        ? <span className="font-mono text-xs text-slate-500" title="PlayHQ ID">PHQ: {p.playhq_id}</span>
                        : <span className="text-xs text-slate-700">no PHQ</span>
                      }
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button onClick={() => startEdit(p)} className="text-slate-400 hover:text-white text-xs">Edit</button>
                    {p.display_name_override && (
                      <button onClick={() => clearOverride(p.id)} className="text-slate-500 hover:text-red-400 text-xs">Clear</button>
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
