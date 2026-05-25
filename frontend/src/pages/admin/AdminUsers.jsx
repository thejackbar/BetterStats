import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { useAuth } from '../../contexts/AuthContext'
import { CAPABILITY_INFO } from '../../lib/capabilities'

const ROLE_LABELS = {
  super_admin: 'Super Admin',
  club_admin: 'Main Admin',
  club_member: 'Club Member',
}

function fmtDate(iso) {
  if (!iso) return 'never'
  const d = new Date(iso)
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (days === 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days}d ago`
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function CapabilityCheckboxes({ value, onChange, disabled }) {
  const toggle = (key) => {
    if (disabled) return
    onChange(value.includes(key) ? value.filter(k => k !== key) : [...value, key])
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {CAPABILITY_INFO.map(cap => (
        <label
          key={cap.key}
          className={`flex items-start gap-2 px-3 py-2 rounded border pb-hairline cursor-pointer hover:bg-pb-surface2 transition ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <input
            type="checkbox"
            checked={value.includes(cap.key)}
            onChange={() => toggle(cap.key)}
            disabled={disabled}
            className="mt-0.5 shrink-0"
          />
          <div className="min-w-0">
            <div className="text-sm text-pb-text">{cap.label}</div>
            <div className="text-[10px] text-pb-faintest font-mono">{cap.hint}</div>
          </div>
        </label>
      ))}
    </div>
  )
}

function NewUserForm({ onCreated, onCancel }) {
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('club_member')
  const [caps, setCaps] = useState([])
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    if (!username.trim() || password.length < 6) {
      setErr('Username + 6+ char password required')
      return
    }
    setBusy(true)
    try {
      await api.adminCreateClubUser({
        username: username.trim(),
        display_name: displayName.trim() || null,
        password,
        role,
        capabilities: role === 'club_admin' ? [] : caps,
      })
      onCreated()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="pb-card p-5 space-y-4">
      <h2 className="font-display font-bold text-lg text-pb-text">Invite club member</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="block">
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Username</span>
          <input value={username} onChange={e => setUsername(e.target.value)} className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
        </label>
        <label className="block">
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Display name</span>
          <input value={displayName} onChange={e => setDisplayName(e.target.value)} className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
        </label>
        <label className="block">
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Password</span>
          <input value={password} onChange={e => setPassword(e.target.value)} type="password" className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="new-password" />
        </label>
        <label className="block">
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Role</span>
          <select value={role} onChange={e => setRole(e.target.value)} className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm">
            <option value="club_member">Club Member (capability-restricted)</option>
            <option value="club_admin">Main Admin (all capabilities)</option>
          </select>
        </label>
      </div>

      {role === 'club_member' && (
        <div>
          <div className="text-pb-faint text-xs font-mono tracking-wide2 uppercase mb-2">Capabilities</div>
          <CapabilityCheckboxes value={caps} onChange={setCaps} />
        </div>
      )}

      {err && <div className="font-mono text-[11px]" style={{ color: 'var(--pb-negative)' }}>{err}</div>}

      <div className="flex gap-2 pt-2">
        <button type="submit" disabled={busy} className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded bg-pb-accent text-pb-bg disabled:opacity-50">
          {busy ? 'Creating…' : 'Create user'}
        </button>
        <button type="button" onClick={onCancel} className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded text-pb-faint hover:text-pb-text border pb-hairline">
          Cancel
        </button>
      </div>
    </form>
  )
}

function UserEditor({ user, currentUserId, onSaved, onClose }) {
  const isSelf = user.id === currentUserId
  const isSuperAdmin = user.role === 'super_admin'
  const [role, setRole] = useState(user.role)
  const [caps, setCaps] = useState(user.capabilities || [])
  const [displayName, setDisplayName] = useState(user.display_name || '')
  const [newPassword, setNewPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [msg, setMsg] = useState(null)

  const lockedFields = isSelf || isSuperAdmin // can't demote yourself or super admin

  const save = async () => {
    setErr(null); setMsg(null)
    setBusy(true)
    try {
      const payload = { display_name: displayName }
      if (!lockedFields) {
        payload.role = role
        payload.capabilities = role === 'club_admin' ? [] : caps
      }
      if (newPassword) payload.password = newPassword
      await api.adminUpdateClubUser(user.id, payload)
      setMsg('Saved')
      setNewPassword('')
      onSaved()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (isSelf) { setErr("Can't remove yourself"); return }
    if (!confirm(`Remove ${user.username} from this club?`)) return
    setBusy(true)
    try {
      await api.adminDeleteClubUser(user.id)
      onSaved()
      onClose()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pb-card p-5 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-display font-bold text-lg text-pb-text">{user.display_name || user.username}</h2>
          <p className="font-mono text-[10px] text-pb-faintest">@{user.username} · last login {fmtDate(user.last_login_at)}</p>
        </div>
        <button onClick={onClose} className="text-pb-faint hover:text-pb-text">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
        </button>
      </div>

      {isSuperAdmin && (
        <p className="font-mono text-[10px] text-pb-faintest">Super admin — capability/role locked from this UI.</p>
      )}
      {isSelf && !isSuperAdmin && (
        <p className="font-mono text-[10px] text-pb-faintest">You can't change your own role or capabilities — ask another Main Admin.</p>
      )}

      <label className="block">
        <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Display name</span>
        <input value={displayName} onChange={e => setDisplayName(e.target.value)} className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" />
      </label>

      <label className="block">
        <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Role</span>
        <select value={role} onChange={e => setRole(e.target.value)} disabled={lockedFields} className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm disabled:opacity-50">
          <option value="club_member">Club Member</option>
          <option value="club_admin">Main Admin</option>
          {isSuperAdmin && <option value="super_admin">Super Admin</option>}
        </select>
      </label>

      {role === 'club_member' && (
        <div>
          <div className="text-pb-faint text-xs font-mono tracking-wide2 uppercase mb-2">Capabilities</div>
          <CapabilityCheckboxes value={caps} onChange={setCaps} disabled={lockedFields} />
        </div>
      )}
      {role === 'club_admin' && (
        <p className="font-mono text-[10px] text-pb-faintest">Main Admin role implicitly has all capabilities — no checkboxes needed.</p>
      )}

      <label className="block">
        <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Reset password</span>
        <input value={newPassword} onChange={e => setNewPassword(e.target.value)} type="password" placeholder="(leave blank to keep current)" className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="new-password" />
      </label>

      {err && <div className="font-mono text-[11px]" style={{ color: 'var(--pb-negative)' }}>{err}</div>}
      {msg && <div className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>{msg}</div>}

      <div className="flex gap-2 pt-2">
        <button onClick={save} disabled={busy} className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded bg-pb-accent text-pb-bg disabled:opacity-50">
          {busy ? 'Saving…' : 'Save'}
        </button>
        {!isSelf && !isSuperAdmin && (
          <button onClick={remove} disabled={busy} className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded text-pb-red hover:bg-pb-red/10 border pb-hairline ml-auto">
            Remove
          </button>
        )}
      </div>
    </div>
  )
}

export default function AdminUsers() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)
  const [selected, setSelected] = useState(null)
  const [creating, setCreating] = useState(false)

  const reload = async () => {
    setLoading(true)
    try {
      setUsers(await api.adminListClubUsers())
      setErr(null)
    } catch (e) {
      setErr(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { reload() }, [])

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <div className="flex items-start justify-between mb-2">
          <h1 className="font-display font-bold text-2xl text-pb-text">Club Users</h1>
          <button
            onClick={() => { setCreating(true); setSelected(null) }}
            className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded bg-pb-accent text-pb-bg"
          >
            + Add user
          </button>
        </div>
        <p className="text-pb-faint text-sm mb-6 leading-relaxed">
          Main Admins have full access. Club Members get only the capabilities you check below.
        </p>

        {err && <div className="mb-4 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{err}</div>}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="pb-card overflow-hidden">
            {loading && <div className="p-6 text-center font-mono text-[11px] text-pb-faint">Loading…</div>}
            {!loading && users.map((u, i) => (
              <button
                key={u.id}
                onClick={() => { setSelected(u); setCreating(false) }}
                className={`w-full text-left px-5 py-3 flex items-center gap-3 transition ${i > 0 ? 'pb-hairline-t' : ''} ${selected?.id === u.id ? 'bg-pb-surface2' : 'hover:bg-pb-surface2'}`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-pb-text text-sm font-medium truncate">{u.display_name || u.username}</span>
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded border pb-hairline text-pb-faint">{ROLE_LABELS[u.role] || u.role}</span>
                    {u.id === me?.id && <span className="font-mono text-[9px] text-pb-faintest">(you)</span>}
                  </div>
                  <p className="font-mono text-[10px] text-pb-faintest mt-0.5">
                    @{u.username} · {u.role === 'club_member' ? `${u.capabilities.length} caps` : 'all caps'} · last login {fmtDate(u.last_login_at)}
                  </p>
                </div>
              </button>
            ))}
          </div>

          <div>
            {creating && <NewUserForm onCreated={() => { setCreating(false); reload() }} onCancel={() => setCreating(false)} />}
            {!creating && selected && (
              <UserEditor
                key={selected.id}
                user={selected}
                currentUserId={me?.id}
                onSaved={async () => { await reload() }}
                onClose={() => setSelected(null)}
              />
            )}
            {!creating && !selected && (
              <div className="pb-card p-8 text-center font-mono text-[11px] text-pb-faint">
                Select a user to edit, or click + Add user.
              </div>
            )}
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
