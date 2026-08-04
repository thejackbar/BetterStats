import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../../contexts/AuthContext'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

export default function AflAdminSuperUsers() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const refresh = () => aflApi.superListUsers().then(setUsers).catch(() => setUsers([]))
  useEffect(() => { refresh() }, [])

  if (me && me.role !== 'super_admin') return <Navigate to="/admin" replace />

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

  const toggleRole = async (u) => {
    const nextRole = u.role === 'super_admin' ? 'club_admin' : 'super_admin'
    if (!window.confirm(`Change ${u.display_name || u.username}'s role to ${nextRole}?`)) return
    setBusy(true)
    setError(null)
    try {
      await aflApi.superUpdateUser(u.id, { role: nextRole })
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (users === null) return <p className="text-sm text-pb-faint">Loading…</p>

  return (
    <div className="space-y-4">
      <SectionTitle>Users — platform-wide ({users.length})</SectionTitle>
      <p className="text-sm text-pb-dim max-w-2xl">Every account across every club, including Better HQ staff.</p>

      {error && <p className="pb-card p-3 text-sm text-[var(--pb-negative)]">{error}</p>}

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
                <td className="px-2 py-1.5 font-medium">{u.display_name || u.username}</td>
                <td className="px-2 py-1.5 text-pb-faint">{u.club_name || '—'}</td>
                <td className="px-2 py-1.5">
                  <span className={u.role === 'super_admin' ? 'text-[var(--pb-accent)]' : 'text-pb-faint'}>{u.role || '—'}</span>
                </td>
                <td className="px-2 py-1.5 text-pb-faint">{u.last_login_at ? u.last_login_at.replace('T', ' ').slice(0, 16) : 'Never'}</td>
                <td className="px-2 py-1.5 text-right whitespace-nowrap">
                  <button disabled={busy} onClick={() => toggleRole(u)} className="text-xs text-pb-dim hover:text-pb-text underline mr-3">
                    {u.role === 'super_admin' ? 'Demote' : 'Make super admin'}
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
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
