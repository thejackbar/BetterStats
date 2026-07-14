import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { useAuth } from '../../contexts/AuthContext'

// club_member is retired — every club user is a full admin. super_admin is
// managed from the Super Admin console, not here.
const ROLE_LABELS = {
  super_admin: 'Super Admin',
  club_admin: 'Admin',
  club_member: 'Admin', // legacy rows (pre-migration) — display as Admin
}

// Mirrors backend/app/routers/club_admin.py's _INVITE_EMAIL_RE / _MOBILE_DIGITS_RE
// so a bad format is caught before the round trip, not just after.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const MOBILE_STRIP_RE = /[\s\-()]/g
const MOBILE_DIGITS_RE = /^\+?\d{7,15}$/
const isValidEmail = (v) => EMAIL_RE.test((v || '').trim())
const isValidMobile = (v) => !v.trim() || MOBILE_DIGITS_RE.test(v.replace(MOBILE_STRIP_RE, ''))
// Mirrors backend/app/services/password_policy.py (MIN_LEN=10, upper/digit/special/match).
const PASSWORD_MIN_LEN = 10
const passwordChecks = (password, confirm) => ({
  length: password.length >= PASSWORD_MIN_LEN,
  upper: /[A-Z]/.test(password),
  digit: /\d/.test(password),
  special: /[^A-Za-z0-9]/.test(password),
  match: !!password && password === confirm,
})

function PasswordChecklist({ checks }) {
  return (
    <ul className="font-mono text-[10px] space-y-0.5 mt-1.5">
      <li className={checks.length ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.length ? '✓' : '·'} At least 10 characters</li>
      <li className={checks.upper ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.upper ? '✓' : '·'} One uppercase letter</li>
      <li className={checks.digit ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.digit ? '✓' : '·'} One number</li>
      <li className={checks.special ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.special ? '✓' : '·'} One special character</li>
      <li className={checks.match ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.match ? '✓' : '·'} Passwords match</li>
    </ul>
  )
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

function NewUserForm({ onCreated, onCancel }) {
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [mobileNumber, setMobileNumber] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    if (!username.trim() || !email.trim()) {
      setErr('Username and email are required')
      return
    }
    if (!isValidEmail(email)) {
      setErr('Enter a valid email address')
      return
    }
    if (!isValidMobile(mobileNumber)) {
      setErr('Enter a valid mobile number')
      return
    }
    setBusy(true)
    try {
      await api.adminCreateClubUser({
        username: username.trim(),
        display_name: displayName.trim() || null,
        email: email.trim(),
        mobile_number: mobileNumber.trim() || null,
        role: 'club_admin',
        capabilities: [],
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
      <h2 className="font-display font-bold text-lg text-pb-text">Invite admin</h2>
      <p className="font-mono text-[10px] text-pb-faintest -mt-2">
        New users are full club admins with access to every tool. They'll get an
        email with a link to set their own password and activate the account.
      </p>
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
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Email</span>
          <input value={email} onChange={e => setEmail(e.target.value)} type="email" className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
        </label>
        <label className="block">
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Mobile number</span>
          <input value={mobileNumber} onChange={e => setMobileNumber(e.target.value)} type="tel" className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
        </label>
      </div>

      {err && <div className="font-mono text-[11px]" style={{ color: 'var(--pb-negative)' }}>{err}</div>}

      <div className="flex gap-2 pt-2">
        <button type="submit" disabled={busy} className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded bg-pb-accent text-pb-bg disabled:opacity-50">
          {busy ? 'Sending invite…' : 'Send invite'}
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
  const [displayName, setDisplayName] = useState(user.display_name || '')
  const [email, setEmail] = useState(user.email || '')
  const [mobileNumber, setMobileNumber] = useState(user.mobile_number || '')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [sendingReset, setSendingReset] = useState(false)
  const [err, setErr] = useState(null)
  const [msg, setMsg] = useState(null)

  const checks = passwordChecks(newPassword, confirmPassword)
  const passwordValid = !newPassword || Object.values(checks).every(Boolean)

  const save = async () => {
    setErr(null); setMsg(null)
    if (!isValidEmail(email)) { setErr('Enter a valid email address'); return }
    if (!isValidMobile(mobileNumber)) { setErr('Enter a valid mobile number'); return }
    if (newPassword && !passwordValid) { setErr('New password does not meet the requirements below'); return }
    setBusy(true)
    try {
      const payload = { display_name: displayName, email, mobile_number: mobileNumber }
      if (newPassword) {
        payload.password = newPassword
        payload.confirm_password = confirmPassword
      }
      await api.adminUpdateClubUser(user.id, payload)
      setMsg('Saved')
      setNewPassword('')
      setConfirmPassword('')
      onSaved()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  const sendResetEmail = async () => {
    setErr(null); setMsg(null)
    setSendingReset(true)
    try {
      await api.adminSendPasswordReset(user.id)
      setMsg(`Password reset email sent to ${user.email || 'the user'}`)
    } catch (e) {
      setErr(e.message)
    } finally {
      setSendingReset(false)
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
          <p className="font-mono text-[10px] text-pb-faintest">
            @{user.username} · {ROLE_LABELS[user.role] || user.role} · last login {fmtDate(user.last_login_at)}
          </p>
        </div>
        <button onClick={onClose} className="text-pb-faint hover:text-pb-text">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
        </button>
      </div>

      {isSuperAdmin && (
        <p className="font-mono text-[10px] text-pb-faintest">Super admin — manage role from the Super Admin console.</p>
      )}

      <label className="block">
        <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Display name</span>
        <input value={displayName} onChange={e => setDisplayName(e.target.value)} className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" />
      </label>

      <label className="block">
        <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Email</span>
        <input value={email} onChange={e => setEmail(e.target.value)} type="email" className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
      </label>

      <label className="block">
        <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Mobile number</span>
        <input value={mobileNumber} onChange={e => setMobileNumber(e.target.value)} type="tel" className="mt-1 w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="off" />
      </label>

      <div className="pb-hairline-t pt-3 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-pb-faint text-xs font-mono tracking-wide2 uppercase">Reset password</span>
          <button type="button" onClick={sendResetEmail} disabled={sendingReset || busy || !user.email}
            title={user.email ? 'Email this user a link to reset their password' : 'This user has no email address on file'}
            className="font-mono text-[10px] tracking-wide2 uppercase px-2.5 py-1.5 rounded text-pb-accent hover:bg-pb-accent/10 border pb-hairline disabled:opacity-50 whitespace-nowrap">
            {sendingReset ? 'Sending…' : 'Email reset link'}
          </button>
        </div>
        <label className="block">
          <input value={newPassword} onChange={e => setNewPassword(e.target.value)} type="password" placeholder="Set new password directly (leave blank to keep current)" className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="new-password" />
        </label>
        {newPassword && (
          <>
            <label className="block">
              <input value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} type="password" placeholder="Confirm new password" className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm" autoComplete="new-password" />
            </label>
            <PasswordChecklist checks={checks} />
          </>
        )}
      </div>

      {err && <div className="font-mono text-[11px]" style={{ color: 'var(--pb-negative)' }}>{err}</div>}
      {msg && <div className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>{msg}</div>}

      <div className="flex gap-2 pt-2">
        <button onClick={save} disabled={busy || !passwordValid} className="font-mono text-[10px] tracking-wide3 uppercase px-4 py-2 rounded bg-pb-accent text-pb-bg disabled:opacity-50">
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
          Everyone here is a full club admin with access to every tool. What each club can use is set
          by its plan, not by per-user permissions.
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
                    @{u.username} · last login {fmtDate(u.last_login_at)}
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
