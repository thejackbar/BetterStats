import { useEffect, useState } from 'react'
import { useAuth } from '../../../contexts/AuthContext'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

export default function AflAdminUsers() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState(null)
  const [form, setForm] = useState({ username: '', display_name: '', email: '', mobile_number: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [invited, setInvited] = useState(null)

  const refresh = () => aflApi.listClubUsers().then(setUsers).catch(() => setUsers([]))
  useEffect(() => { refresh() }, [])

  const invite = async () => {
    if (!form.username.trim() || !form.email.trim()) return
    setBusy(true)
    setError(null)
    setInvited(null)
    try {
      await aflApi.createClubUser(form)
      setInvited(form.email)
      setForm({ username: '', display_name: '', email: '', mobile_number: '' })
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (u) => {
    if (!window.confirm(`Remove ${u.display_name || u.username} from the club?`)) return
    setBusy(true)
    try {
      await aflApi.deleteClubUser(u.id)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const sendReset = async (u) => {
    setBusy(true)
    setError(null)
    try {
      await aflApi.sendPasswordReset(u.id)
      window.alert(`Password reset link sent to ${u.email}.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (users === null) return <p className="text-sm text-pb-faint">Loading…</p>

  return (
    <div className="space-y-6">
      <SectionTitle>Users ({users.length})</SectionTitle>
      <p className="text-sm text-pb-dim max-w-2xl">Everyone who can log in and manage this club.</p>

      {error && <p className="pb-card p-3 text-sm text-[var(--pb-negative)]">{error}</p>}
      {invited && <p className="pb-card p-3 text-sm text-[var(--pb-positive)]">Invited — a set-your-password link was emailed to {invited}.</p>}

      <div className="pb-card p-4 space-y-3 max-w-lg">
        <SectionTitle>Invite an admin</SectionTitle>
        <div className="grid grid-cols-2 gap-2">
          <input placeholder="Username" value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          <input placeholder="Display name" value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
          <input placeholder="Email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm col-span-2" />
          <input placeholder="Mobile (optional)" value={form.mobile_number} onChange={e => setForm(f => ({ ...f, mobile_number: e.target.value }))}
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm col-span-2" />
        </div>
        <button disabled={busy || !form.username.trim() || !form.email.trim()} onClick={invite}
                className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
          {busy ? 'Sending…' : 'Send invite'}
        </button>
      </div>

      <div className="pb-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="pb-hairline-b">
            <tr>
              {['Name', 'Username', 'Email', 'Last login', ''].map(h => (
                <th key={h} className="px-2 py-1.5 text-left font-mono text-[10px] uppercase text-pb-faint">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="pb-hairline-b last:border-0">
                <td className="px-2 py-1.5 font-medium">{u.display_name || u.username}</td>
                <td className="px-2 py-1.5 text-pb-faint">{u.username}</td>
                <td className="px-2 py-1.5 text-pb-faint">{u.email || '—'}</td>
                <td className="px-2 py-1.5 text-pb-faint">{u.last_login_at ? u.last_login_at.replace('T', ' ').slice(0, 16) : 'Never'}</td>
                <td className="px-2 py-1.5 text-right whitespace-nowrap">
                  {u.email && (
                    <button disabled={busy} onClick={() => sendReset(u)} className="text-xs text-pb-dim hover:text-pb-text underline mr-3">
                      Reset password
                    </button>
                  )}
                  {u.id !== me?.id && (
                    <button disabled={busy} onClick={() => remove(u)} className="text-xs text-[var(--pb-negative)] hover:opacity-80 underline">
                      Remove
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
