import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

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
        <div className="flex items-center justify-between mb-5">
          <h1 className="font-display font-bold text-2xl text-pb-text">Users</h1>
          <div className="flex items-center gap-3">
            {msg && <span className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>{msg}</span>}
            <button
              onClick={() => setShowCreate(s => !s)}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {showCreate ? 'CANCEL' : '+ NEW USER'}
            </button>
          </div>
        </div>

        {showCreate && (
          <form onSubmit={createUser} className="pb-card p-4 mb-5 space-y-3">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Create New User</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Username *</label>
                <input required type="text" value={form.username}
                  onChange={e => setForm(f => ({ ...f, username: e.target.value.toLowerCase() }))}
                  placeholder="e.g. applecross"
                  className={INPUT_CLS + ' font-mono'} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Password * (min 10 chars)</label>
                <input required type="text" value={form.password}
                  onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  className={INPUT_CLS} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Display name</label>
                <input type="text" value={form.display_name}
                  onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))}
                  className={INPUT_CLS} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Club *</label>
                <select required value={form.club_id}
                  onChange={e => setForm(f => ({ ...f, club_id: e.target.value }))}
                  className={INPUT_CLS}>
                  <option value="">Select club…</option>
                  {clubs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Role</label>
                <select value={form.role}
                  onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
                  className="bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
                  <option value="club_admin">Club Admin</option>
                  <option value="super_admin">Super Admin</option>
                </select>
              </div>
            </div>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {saving ? 'Creating…' : 'CREATE USER'}
            </button>
          </form>
        )}

        {resetTarget && (
          <div className="pb-card p-4 mb-5 space-y-3 border-pb-amber/30">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">
              Reset password for <span className="text-pb-amber">{resetTarget.username}</span>
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                placeholder="New password (min 10 chars)"
                className="flex-1 bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
              />
              <button
                onClick={doResetPassword}
                disabled={saving || newPassword.length < 10}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                Set
              </button>
              <button
                onClick={() => { setResetTarget(null); setNewPassword('') }}
                className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
              >
                Cancel
              </button>
            </div>
            {newPassword.length >= 10 && (
              <p className="font-mono text-[10px] text-pb-amber">Show this password to the club, then close this screen.</p>
            )}
          </div>
        )}

        <div className="pb-card overflow-hidden">
          {users.length === 0 && (
            <div className="px-5 py-6 text-center font-mono text-[11px] text-pb-faint">No users yet</div>
          )}
          {users.map((u, i) => (
            <div key={u.id} className={`flex items-center justify-between px-5 py-3 ${i > 0 ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
              <div className="min-w-0">
                <span className="text-pb-text text-sm font-mono">{u.username}</span>
                {u.display_name && <span className="text-pb-faint text-xs ml-2">{u.display_name}</span>}
                <div className="font-mono text-[10px] text-pb-faintest mt-0.5">
                  {u.club_name || 'No club'} · {u.role}
                  {u.locked && <span className="ml-2 text-pb-red">Locked</span>}
                </div>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                {u.last_login_at && (
                  <span className="font-mono text-[10px] text-pb-faintest">
                    Last login {new Date(u.last_login_at).toLocaleDateString('en-AU')}
                  </span>
                )}
                <button
                  onClick={() => { setResetTarget(u); setNewPassword('') }}
                  className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors"
                >
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
