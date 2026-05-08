import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

export default function SuperUsers() {
  const [users, setUsers] = useState([])
  const [clubs, setClubs] = useState([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ username: '', password: '', display_name: '', club_id: '', role: 'club_admin' })
  const [resetTarget, setResetTarget] = useState(null)
  const [newPassword, setNewPassword] = useState('')
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)

  const load = () => {
    api.superListUsers().then(setUsers).catch(() => {})
    api.superListClubs().then(setClubs).catch(() => {})
  }
  useEffect(() => { load() }, [])

  const createUser = async (e) => {
    e.preventDefault()
    setSaving(true)
    setMsg('')
    try {
      await api.superCreateUser(form)
      setMsg('User created')
      setShowCreate(false)
      setForm({ username: '', password: '', display_name: '', club_id: '', role: 'club_admin' })
      load()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  const doResetPassword = async () => {
    if (!resetTarget || newPassword.length < 10) return
    setSaving(true)
    try {
      await api.superResetPassword(resetTarget.id, newPassword)
      setMsg(`Password reset for ${resetTarget.username}`)
      setResetTarget(null)
      setNewPassword('')
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
          <h1 className="text-xl font-display font-bold text-white">Users</h1>
          <div className="flex items-center gap-3">
            {msg && <span className="text-sm text-accent">{msg}</span>}
            <button onClick={() => setShowCreate(s => !s)} className="btn-primary text-sm">
              {showCreate ? 'Cancel' : '+ New User'}
            </button>
          </div>
        </div>

        {showCreate && (
          <form onSubmit={createUser} className="bg-navy-900 border border-navy-700 rounded-lg p-4 mb-4 space-y-3">
            <h2 className="text-sm font-medium text-white">Create New User</h2>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Username *</label>
                <input required type="text" value={form.username}
                  onChange={e => setForm(f => ({ ...f, username: e.target.value.toLowerCase() }))}
                  placeholder="e.g. applecross"
                  className="w-full bg-navy-800 border border-navy-600 rounded px-2 py-1.5 text-white text-sm font-mono focus:outline-none focus:border-accent" />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Password * (min 10 chars)</label>
                <input required type="text" value={form.password}
                  onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  className="w-full bg-navy-800 border border-navy-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-accent" />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Display name</label>
                <input type="text" value={form.display_name}
                  onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))}
                  className="w-full bg-navy-800 border border-navy-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-accent" />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Club *</label>
                <select required value={form.club_id}
                  onChange={e => setForm(f => ({ ...f, club_id: e.target.value }))}
                  className="w-full bg-navy-800 border border-navy-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-accent">
                  <option value="">Select club…</option>
                  {clubs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Role</label>
                <select value={form.role}
                  onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
                  className="bg-navy-800 border border-navy-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-accent">
                  <option value="club_admin">Club Admin</option>
                  <option value="super_admin">Super Admin</option>
                </select>
              </div>
            </div>
            <button type="submit" disabled={saving} className="btn-primary text-sm">
              {saving ? 'Creating…' : 'Create User'}
            </button>
          </form>
        )}

        {resetTarget && (
          <div className="bg-navy-900 border border-amber-cricket/40 rounded-lg p-4 mb-4 space-y-3">
            <h2 className="text-sm font-medium text-white">Reset password for <span className="text-accent">{resetTarget.username}</span></h2>
            <div className="flex gap-2">
              <input
                type="text"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                placeholder="New password (min 10 chars)"
                className="flex-1 bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
              />
              <button onClick={doResetPassword} disabled={saving || newPassword.length < 10} className="btn-primary text-sm disabled:opacity-50">
                Set
              </button>
              <button onClick={() => { setResetTarget(null); setNewPassword('') }} className="btn-ghost text-sm">Cancel</button>
            </div>
            {newPassword.length >= 10 && (
              <p className="text-xs text-amber-cricket">Show this password to the club, then close this screen.</p>
            )}
          </div>
        )}

        <div className="bg-navy-900 border border-navy-700 rounded-lg overflow-hidden">
          {users.length === 0 && (
            <div className="px-4 py-6 text-center text-slate-500 text-sm">No users yet</div>
          )}
          {users.map((u, i) => (
            <div key={u.id} className={`flex items-center justify-between px-4 py-3 ${i > 0 ? 'border-t border-navy-800' : ''}`}>
              <div className="min-w-0">
                <span className="text-white text-sm font-mono">{u.username}</span>
                {u.display_name && <span className="text-slate-400 text-xs ml-2">{u.display_name}</span>}
                <div className="text-xs text-slate-500">
                  {u.club_name || 'No club'} · {u.role}
                  {u.locked && <span className="ml-2 text-red-400">Locked</span>}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {u.last_login_at && (
                  <span className="text-slate-500 text-xs">
                    Last login {new Date(u.last_login_at).toLocaleDateString('en-AU')}
                  </span>
                )}
                <button onClick={() => { setResetTarget(u); setNewPassword('') }} className="text-slate-400 hover:text-white text-xs">
                  Reset password
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
