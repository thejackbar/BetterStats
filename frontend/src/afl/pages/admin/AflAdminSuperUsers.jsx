import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../../contexts/AuthContext'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

const EMPTY_CREATE = { username: '', password: '', display_name: '', club_id: '', role: 'club_admin' }

export default function AflAdminSuperUsers() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState(null)
  const [clubs, setClubs] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState(EMPTY_CREATE)

  const [editId, setEditId] = useState(null)
  const [editForm, setEditForm] = useState({ role: 'club_admin', club_id: '' })

  const refresh = () => {
    aflApi.superListUsers().then(setUsers).catch(() => setUsers([]))
    aflApi.superListClubs().then(res => setClubs(res?.clubs || [])).catch(() => {})
  }
  useEffect(() => { refresh() }, [])

  if (me && me.role !== 'super_admin') return <Navigate to="/admin" replace />

  const createUser = async () => {
    setBusy(true)
    setError(null)
    try {
      await aflApi.superCreateUser(form)
      setForm(EMPTY_CREATE)
      setShowCreate(false)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const startEdit = (u) => {
    setEditId(u.id)
    setEditForm({ role: u.role || 'club_admin', club_id: u.club_id || '' })
  }

  const saveEdit = async (u) => {
    setBusy(true)
    setError(null)
    try {
      await aflApi.superUpdateUser(u.id, editForm)
      setEditId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (u) => {
    if (!window.confirm(`Delete the account for ${u.display_name || u.username}? This can't be undone.`)) return
    setBusy(true)
    setError(null)
    try {
      await aflApi.superDeleteUser(u.id)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const resetPassword = async (u) => {
    const pw = window.prompt(`New password for ${u.display_name || u.username} (min 10 characters):`)
    if (!pw) return
    setBusy(true)
    setError(null)
    try {
      await aflApi.superResetPassword(u.id, pw)
      window.alert('Password reset.')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (users === null) return <p className="text-sm text-pb-faint">Loading…</p>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <SectionTitle>Users — platform-wide ({users.length})</SectionTitle>
        <button onClick={() => setShowCreate(s => !s)} className="px-3 py-1.5 rounded text-sm font-semibold bg-[var(--pb-accent)] text-black">
          {showCreate ? 'Cancel' : '+ New user'}
        </button>
      </div>
      <p className="text-sm text-pb-dim max-w-2xl">Every account across every club, including Better HQ staff.</p>

      {error && <p className="pb-card p-3 text-sm text-[var(--pb-negative)]">{error}</p>}

      {showCreate && (
        <div className="pb-card p-4 space-y-3 max-w-lg">
          <SectionTitle>New user</SectionTitle>
          <div className="grid grid-cols-2 gap-2">
            <input placeholder="Username" value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                   className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
            <input placeholder="Password (min 10 chars)" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                   className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
            <input placeholder="Display name" value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))}
                   className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm col-span-2" />
            <select value={form.club_id} onChange={e => setForm(f => ({ ...f, club_id: e.target.value }))}
                    className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
              <option value="">— select club —</option>
              {clubs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
                    className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
              <option value="club_admin">Club Admin</option>
              <option value="super_admin">Super Admin</option>
            </select>
          </div>
          <p className="text-xs text-pb-faint">
            The password is set here directly and handed to the new user — there's no email invite step yet.
          </p>
          <button disabled={busy || !form.username.trim() || !form.password.trim() || !form.club_id} onClick={createUser}
                  className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
            {busy ? 'Creating…' : 'Create user'}
          </button>
        </div>
      )}

      <div className="pb-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="pb-hairline-b">
            <tr>
              {['Name', 'Club', 'Role', 'Last login', ''].map(h => (
                <th key={h} className="px-2 py-1.5 text-left font-mono text-[10px] uppercase text-pb-faint">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="pb-hairline-b last:border-0">
                {editId === u.id ? (
                  <>
                    <td className="px-2 py-1.5 font-medium">{u.display_name || u.username}</td>
                    <td className="px-2 py-1.5">
                      <select value={editForm.club_id} onChange={e => setEditForm(f => ({ ...f, club_id: e.target.value }))}
                              className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs">
                        <option value="">— select club —</option>
                        {clubs.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    </td>
                    <td className="px-2 py-1.5">
                      <select value={editForm.role} onChange={e => setEditForm(f => ({ ...f, role: e.target.value }))}
                              className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs">
                        <option value="club_admin">Club Admin</option>
                        <option value="super_admin">Super Admin</option>
                      </select>
                    </td>
                    <td className="px-2 py-1.5 text-pb-faint">{u.last_login_at ? u.last_login_at.replace('T', ' ').slice(0, 16) : 'Never'}</td>
                    <td className="px-2 py-1.5 text-right whitespace-nowrap">
                      <button disabled={busy} onClick={() => saveEdit(u)} className="text-xs text-[var(--pb-positive)] underline mr-3">Save</button>
                      <button disabled={busy} onClick={() => setEditId(null)} className="text-xs text-pb-dim hover:text-pb-text underline">Cancel</button>
                    </td>
                  </>
                ) : (
                  <>
                    <td className="px-2 py-1.5 font-medium">{u.display_name || u.username}</td>
                    <td className="px-2 py-1.5 text-pb-faint">{u.club_name || '—'}</td>
                    <td className="px-2 py-1.5">
                      <span className={u.role === 'super_admin' ? 'text-[var(--pb-accent)]' : 'text-pb-faint'}>{u.role || '—'}</span>
                    </td>
                    <td className="px-2 py-1.5 text-pb-faint">{u.last_login_at ? u.last_login_at.replace('T', ' ').slice(0, 16) : 'Never'}</td>
                    <td className="px-2 py-1.5 text-right whitespace-nowrap">
                      <button disabled={busy} onClick={() => startEdit(u)} className="text-xs text-pb-dim hover:text-pb-text underline mr-3">
                        Change role/club
                      </button>
                      <button disabled={busy} onClick={() => resetPassword(u)} className="text-xs text-pb-dim hover:text-pb-text underline mr-3">
                        Reset password
                      </button>
                      {u.id !== me?.id && (
                        <button disabled={busy} onClick={() => remove(u)} className="text-xs text-[var(--pb-negative)] hover:opacity-80 underline">
                          Delete
                        </button>
                      )}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
